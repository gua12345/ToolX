# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""API 请求处理器

本模块实现动态路由的核心处理逻辑。
"""

import json
import logging
import traceback
import uuid
import time
from typing import Optional, Tuple, Dict, Any, List

import httpx
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import ValidationError

from .models import ChatCompletionRequest
from ..config.loader import config_loader
from ..core.trigger_signal import generate_random_trigger_signal
from ..middleware.message_processor import preprocess_messages, validate_message_structure
from ..function_calling import (
    generate_function_prompt,
    safe_process_tool_choice,
    parse_function_calls_xml,
    StreamingFunctionCallDetector,
    attempt_fc_parse_with_retry
)

logger = logging.getLogger(__name__)

# 全局 HTTP 客户端
http_client = httpx.AsyncClient()

# 全局触发信号（在应用启动时生成）
GLOBAL_TRIGGER_SIGNAL = generate_random_trigger_signal()


def parse_dynamic_route(path: str) -> Optional[Tuple[str, str, str]]:
    """
    解析动态路由格式的 URL 路径
    格式: /{path_key}/{protocol}/{base_url}/{remaining_path}

    Args:
        path: URL 路径

    Returns:
        (path_key, base_url, remaining_path) 或 None
    """
    # 移除开头的斜杠
    path = path.lstrip('/')

    # 分割路径，最多分割3次（path_key, protocol, base_url, remaining_path）
    parts = path.split('/', 3)

    if len(parts) < 4:
        return None

    path_key, protocol, base_url_part, remaining_path = parts

    # 验证协议
    if protocol not in ['http', 'https']:
        return None

    # 构建完整的 base_url
    base_url = f"{protocol}://{base_url_part}"

    # 确保 remaining_path 以斜杠开头
    if not remaining_path.startswith('/'):
        remaining_path = '/' + remaining_path

    return (path_key, base_url, remaining_path)


async def handle_dynamic_routing(
    request: Request,
    path_key: str,
    protocol: str,
    base_url: str
):
    """
    动态路由主入口处理器

    对于 /chat/completions 路径，会应用完整的函数调用注入功能
    对于其他路径，仅作为简单的 HTTP 代理

    Args:
        request: FastAPI 请求对象
        path_key: URL 路径中的认证密钥
        protocol: 协议（http 或 https）
        base_url: 目标服务的基础 URL

    Returns:
        代理后的响应
    """
    app_config = config_loader.config

    # 解析完整路径
    full_path = request.url.path
    parsed = parse_dynamic_route(full_path)

    if parsed is None:
        raise HTTPException(status_code=400, detail="Invalid dynamic routing format")

    parsed_path_key, base_url, remaining_path = parsed

    # 验证路径密钥
    dynamic_routing_keys = config_loader.get_dynamic_routing_keys()
    if parsed_path_key not in dynamic_routing_keys:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid path key")

    # 获取客户端提供的 Authorization header
    authorization = request.headers.get("Authorization", "")
    if not authorization:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing Authorization header")

    # 构建上游请求 URL
    upstream_url = f"{base_url}{remaining_path}"

    logger.info(f"🔀 Dynamic routing: {request.method} {upstream_url}")
    logger.debug(f"🔀 Path key validated: {parsed_path_key[:8]}...")

    # 检查是否是 chat/completions 路径，如果是则应用完整的函数调用功能
    if remaining_path.endswith("/chat/completions") and request.method == "POST":
        return await handle_dynamic_chat_completions(request, base_url, remaining_path, authorization)

    # 其他路径使用简单代理模式
    return await handle_dynamic_simple_proxy(request, upstream_url, authorization)


async def handle_dynamic_chat_completions(
    request: Request,
    base_url: str,
    remaining_path: str,
    authorization: str
):
    """
    处理动态路由的 chat/completions 请求，应用完整的函数调用功能

    Args:
        request: FastAPI 请求对象
        base_url: 目标服务的基础 URL
        remaining_path: API 端点路径
        authorization: 授权头

    Returns:
        处理后的响应
    """
    app_config = config_loader.config

    try:
        # 解析请求体
        body_dict = await request.json()
        body = ChatCompletionRequest(**body_dict)

        logger.debug(f"🔧 Received dynamic routing chat completion request, model: {body.model}")
        logger.debug(f"🔧 Number of messages: {len(body.messages)}")
        logger.debug(f"🔧 Number of tools: {len(body.tools) if body.tools else 0}")
        logger.debug(f"🔧 Streaming: {body.stream}")

        # 构建上游 URL
        upstream_url = f"{base_url}{remaining_path}"

        # 消息预处理
        logger.debug(f"🔧 Starting message preprocessing, original message count: {len(body.messages)}")
        processed_messages = preprocess_messages(body.messages, GLOBAL_TRIGGER_SIGNAL)
        logger.debug(f"🔧 Preprocessing completed, processed message count: {len(processed_messages)}")

        if not validate_message_structure(processed_messages):
            logger.error(f"❌ Message structure validation failed, but continuing processing")

        # 构建请求体
        request_body_dict = body.model_dump(exclude_unset=True)
        request_body_dict["messages"] = processed_messages

        # 检查是否需要函数调用功能
        is_fc_enabled = app_config.features.enable_function_calling
        has_tools_in_request = bool(body.tools)
        has_function_call = is_fc_enabled and has_tools_in_request

        logger.debug(f"🔧 Request body constructed, message count: {len(processed_messages)}")

    except ValidationError as e:
        logger.error(f"❌ Request validation failed: {str(e)}")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": "Invalid request format",
                    "type": "invalid_request_error",
                    "code": "invalid_request"
                }
            }
        )
    except Exception as e:
        logger.error(f"❌ Request preprocessing failed: {str(e)}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": "Invalid request format",
                    "type": "invalid_request_error",
                    "code": "invalid_request"
                }
            }
        )

    # 注入函数调用提示词
    if has_function_call:
        logger.debug(f"🔧 Using global trigger signal for this request: {GLOBAL_TRIGGER_SIGNAL}")

        if body.tools:
            function_prompt, _ = generate_function_prompt(body.tools, GLOBAL_TRIGGER_SIGNAL)

            tool_choice_prompt = safe_process_tool_choice(body.tool_choice, body.tools)
            if tool_choice_prompt:
                function_prompt += tool_choice_prompt

            system_message = {"role": "system", "content": function_prompt}
            request_body_dict["messages"].insert(0, system_message)

            logger.debug(f"🔧 Function call prompt injected, total messages: {len(request_body_dict['messages'])}")

        # 移除 tools 和 tool_choice 字段
        request_body_dict.pop("tools", None)
        request_body_dict.pop("tool_choice", None)

    # 构建请求头
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json"
    }

    # 处理非流式响应
    if not body.stream:
        return await handle_non_streaming_response(
            upstream_url,
            request_body_dict,
            headers,
            body.model,
            has_function_call,
            GLOBAL_TRIGGER_SIGNAL,
            processed_messages
        )
    # 处理流式响应
    else:
        return await handle_streaming_response(
            upstream_url,
            request_body_dict,
            headers,
            body.model,
            has_function_call,
            GLOBAL_TRIGGER_SIGNAL,
            processed_messages
        )


async def handle_non_streaming_response(
    upstream_url: str,
    request_body_dict: Dict[str, Any],
    headers: Dict[str, str],
    model: str,
    has_function_call: bool,
    trigger_signal: str,
    messages: List[Dict[str, Any]]
) -> JSONResponse:
    """
    处理非流式响应

    Args:
        upstream_url: 上游服务 URL
        request_body_dict: 请求体字典
        headers: 请求头
        model: 模型名称
        has_function_call: 是否启用函数调用
        trigger_signal: 触发信号
        messages: 消息列表

    Returns:
        JSON 响应
    """
    app_config = config_loader.config

    try:
        logger.debug(f"🔧 Sending non-streaming request to: {upstream_url}")

        response = await http_client.post(
            upstream_url,
            json=request_body_dict,
            headers=headers,
            timeout=app_config.server.timeout
        )
        response.raise_for_status()
        response_json = response.json()

        logger.debug(f"🔧 Received response from upstream")

        # 如果启用了函数调用，尝试解析和转换
        if has_function_call:
            if response_json.get("choices") and len(response_json["choices"]) > 0:
                original_message = response_json["choices"][0].get("message", {})
                content = original_message.get("content", "")

                if content and trigger_signal in content:
                    logger.debug(f"🔧 Trigger signal detected in response, attempting to parse function calls")

                    # 尝试解析函数调用（带重试）
                    tool_calls = await attempt_fc_parse_with_retry(
                        content,
                        trigger_signal,
                        messages,
                        upstream_url,
                        headers,
                        model,
                        app_config.server.timeout
                    )

                    if tool_calls:
                        # 提取触发信号之前的文本作为前缀
                        prefix_text = content.split(trigger_signal)[0].strip()

                        # 构建新的消息格式
                        new_message = {
                            "role": "assistant",
                            "content": prefix_text if prefix_text else None,
                            "tool_calls": tool_calls,
                        }
                        # 复制其他字段
                        for key in original_message:
                            if key not in ["role", "content", "tool_calls"]:
                                new_message[key] = original_message[key]

                        response_json["choices"][0]["message"] = new_message
                        response_json["choices"][0]["finish_reason"] = "tool_calls"
                        logger.debug(f"🔧 Function call conversion completed")
                    else:
                        logger.debug(f"🔧 No tool calls detected, returning original content")
                else:
                    logger.debug(f"🔧 No function calls detected or conversion conditions not met")

        return JSONResponse(content=response_json)

    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Upstream service response error: status_code={e.response.status_code}")
        logger.error(f"❌ Upstream error details: {e.response.text}")

        try:
            error_json = e.response.json()
            return JSONResponse(status_code=e.response.status_code, content=error_json)
        except:
            return JSONResponse(
                status_code=e.response.status_code,
                content={
                    "error": {
                        "message": e.response.text,
                        "type": "upstream_error",
                        "code": "upstream_error"
                    }
                }
            )
    except httpx.TimeoutException:
        logger.error(f"❌ Request timeout")
        return JSONResponse(
            status_code=504,
            content={
                "error": {
                    "message": "Gateway Timeout",
                    "type": "timeout_error",
                    "code": "timeout"
                }
            }
        )
    except Exception as e:
        logger.error(f"❌ Dynamic routing error: {str(e)}")
        logger.error(f"❌ Error traceback: {traceback.format_exc()}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal Server Error",
                    "type": "server_error",
                    "code": "internal_error"
                }
            }
        )


def _prepare_tool_calls(parsed_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    准备工具调用列表，生成 tool_call_id

    Args:
        parsed_tools: 解析出的工具列表，每个包含 name 和 args

    Returns:
        标准格式的 tool_calls 列表
    """
    tool_calls = []
    for i, tool in enumerate(parsed_tools):
        tool_call_id = f"call_{uuid.uuid4().hex}"
        tool_calls.append({
            "index": i,
            "id": tool_call_id,
            "type": "function",
            "function": {
                "name": tool["name"],
                "arguments": json.dumps(tool["args"], ensure_ascii=False)
            }
        })
    return tool_calls


def _build_tool_call_sse_chunks(parsed_tools: List[Dict[str, Any]], model_id: str) -> List[str]:
    """
    构建工具调用的 SSE 格式 chunks

    Args:
        parsed_tools: 解析出的工具列表
        model_id: 模型 ID

    Returns:
        SSE 格式的字符串列表
    """
    tool_calls = _prepare_tool_calls(parsed_tools)
    chunks: List[str] = []

    # 初始 chunk：包含 role 和 tool_calls
    initial_chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{
            "index": 0,
            "delta": {
                "role": "assistant",
                "content": None,
                "tool_calls": tool_calls
            },
            "finish_reason": None
        }]
    }
    chunks.append(f"data: {json.dumps(initial_chunk, ensure_ascii=False)}\n\n")

    # 最终 chunk：finish_reason = tool_calls
    final_chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_id,
        "choices": [{
            "index": 0,
            "delta": {},
            "finish_reason": "tool_calls"
        }]
    }
    chunks.append(f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n")
    chunks.append("data: [DONE]\n\n")

    return chunks


async def _attempt_streaming_fc_retry(
    original_content: str,
    trigger_signal: str,
    messages: List[Dict[str, Any]],
    url: str,
    headers: Dict[str, str],
    model: str,
    timeout: int
) -> Optional[List[Dict[str, Any]]]:
    """
    流式函数调用解析失败时的重试逻辑

    Args:
        original_content: 原始响应内容
        trigger_signal: 触发信号
        messages: 消息历史
        url: 上游服务 URL
        headers: 请求头
        model: 模型名称
        timeout: 超时时间

    Returns:
        解析出的工具调用列表，如果失败则返回 None
    """
    return await attempt_fc_parse_with_retry(
        original_content,
        trigger_signal,
        messages,
        url,
        headers,
        model,
        timeout
    )


async def handle_streaming_response(
    upstream_url: str,
    request_body_dict: Dict[str, Any],
    headers: Dict[str, str],
    model: str,
    has_function_call: bool,
    trigger_signal: str,
    messages: List[Dict[str, Any]]
) -> StreamingResponse:
    """
    处理流式响应，支持函数调用检测和转换

    Args:
        upstream_url: 上游服务 URL
        request_body_dict: 请求体字典
        headers: 请求头
        model: 模型名称
        has_function_call: 是否启用函数调用
        trigger_signal: 触发信号
        messages: 消息列表

    Returns:
        流式响应
    """
    app_config = config_loader.config

    async def stream_generator():
        # 如果没有启用函数调用，直接透传
        if not has_function_call:
            try:
                async with http_client.stream(
                    "POST",
                    upstream_url,
                    json=request_body_dict,
                    headers=headers,
                    timeout=app_config.server.timeout
                ) as response:
                    response.raise_for_status()

                    # 直接透传字节流，不要逐行处理
                    async for chunk in response.aiter_bytes():
                        yield chunk

            except httpx.TimeoutException:
                logger.error(f"❌ Streaming timeout")
                error_chunk = {"error": {"message": "Gateway Timeout", "type": "timeout_error", "code": "timeout"}}
                yield f"data: {json.dumps(error_chunk)}\n\n".encode('utf-8')
            except Exception as e:
                logger.error(f"❌ Streaming error: {str(e)}")
                error_chunk = {"error": {"message": str(e), "type": "internal_error", "code": "internal_error"}}
                yield f"data: {json.dumps(error_chunk)}\n\n".encode('utf-8')
            return

        # 启用了函数调用，需要检测和转换
        logger.info(f"📝 Starting streaming response with function calling enabled")
        detector = StreamingFunctionCallDetector(trigger_signal)

        try:
            async with http_client.stream(
                "POST",
                upstream_url,
                json=request_body_dict,
                headers=headers,
                timeout=app_config.server.timeout
            ) as response:
                if response.status_code != 200:
                    error_content = await response.aread()
                    logger.error(f"❌ Upstream service stream response error: status_code={response.status_code}")
                    logger.error(f"❌ Upstream error details: {error_content.decode('utf-8', errors='ignore')}")

                    # 根据状态码返回不同错误消息
                    if response.status_code == 401:
                        error_message = "Authentication failed"
                    elif response.status_code == 403:
                        error_message = "Access forbidden"
                    elif response.status_code == 429:
                        error_message = "Rate limit exceeded"
                    elif response.status_code >= 500:
                        error_message = "Upstream service temporarily unavailable"
                    else:
                        error_message = "Request processing failed"

                    error_chunk = {"error": {"message": error_message, "type": "upstream_error"}}
                    yield f"data: {json.dumps(error_chunk)}\n\n".encode('utf-8')
                    yield b"data: [DONE]\n\n"
                    return

                async for line in response.aiter_lines():
                    # 如果已经进入工具解析状态，继续收集内容
                    if detector.state == "tool_parsing":
                        if line.startswith("data:"):
                            line_data = line[len("data: "):].strip()
                            if line_data and line_data != "[DONE]":
                                try:
                                    chunk_json = json.loads(line_data)
                                    delta_content = chunk_json.get("choices", [{}])[0].get("delta", {}).get("content", "") or ""
                                    detector.content_buffer += delta_content

                                    # 提前终止：一旦出现 </function_calls>，立即解析并完成
                                    if "</function_calls>" in detector.content_buffer:
                                        logger.debug("🔧 Detected </function_calls> in stream, finalizing early...")
                                        parsed_tools = detector.finalize()

                                        if parsed_tools:
                                            logger.debug(f"🔧 Early finalize: parsed {len(parsed_tools)} tool calls")
                                            for sse in _build_tool_call_sse_chunks(parsed_tools, model):
                                                yield sse.encode('utf-8')
                                            return
                                        else:
                                            # 解析失败，尝试重试
                                            if app_config.features.enable_fc_error_retry:
                                                logger.info(f"🔄 Early finalize FC parsing failed, attempting retry...")
                                                retry_parsed = await _attempt_streaming_fc_retry(
                                                    original_content=detector.content_buffer,
                                                    trigger_signal=trigger_signal,
                                                    messages=messages,
                                                    url=upstream_url,
                                                    headers=headers,
                                                    model=model,
                                                    timeout=app_config.server.timeout
                                                )
                                                if retry_parsed:
                                                    logger.info(f"✅ Early finalize FC retry succeeded, parsed {len(retry_parsed)} tool calls")
                                                    for sse in _build_tool_call_sse_chunks(retry_parsed, model):
                                                        yield sse.encode('utf-8')
                                                    return
                                                else:
                                                    logger.warning(f"⚠️ Early finalize FC retry also failed, ending stream")
                                            else:
                                                logger.warning(
                                                    "⚠️ Early finalize detected </function_calls> but failed to parse tool calls; "
                                                    "silently ending stream. buffer_len=%s preview=%r",
                                                    len(detector.content_buffer),
                                                    detector.content_buffer[:200],
                                                )

                                            # 发送 stop chunk
                                            stop_chunk = {
                                                "id": f"chatcmpl-{uuid.uuid4().hex}",
                                                "object": "chat.completion.chunk",
                                                "created": int(time.time()),
                                                "model": model,
                                                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                                            }
                                            yield f"data: {json.dumps(stop_chunk)}\n\n".encode('utf-8')
                                            yield b"data: [DONE]\n\n"
                                            return
                                except (json.JSONDecodeError, IndexError):
                                    pass
                        continue

                    # 正常处理流式数据
                    if line.startswith("data:"):
                        line_data = line[len("data: "):].strip()
                        if not line_data or line_data == "[DONE]":
                            continue

                        try:
                            chunk_json = json.loads(line_data)
                            delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                            delta_content = delta.get("content", "") or ""
                            delta_reasoning = delta.get("reasoning_content", "") or ""
                            finish_reason = chunk_json.get("choices", [{}])[0].get("finish_reason")

                            # 直接转发 reasoning_content（不参与函数调用检测）
                            if delta_reasoning:
                                reasoning_chunk = {
                                    "id": chunk_json.get("id") or f"chatcmpl-passthrough-{uuid.uuid4().hex}",
                                    "object": "chat.completion.chunk",
                                    "created": chunk_json.get("created") or int(time.time()),
                                    "model": model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {"reasoning_content": delta_reasoning},
                                        "finish_reason": None
                                    }]
                                }
                                yield f"data: {json.dumps(reasoning_chunk)}\n\n".encode('utf-8')

                            # 处理普通内容
                            if delta_content:
                                is_tool_call_detected, content_to_yield = detector.process_chunk(delta_content)

                                if is_tool_call_detected:
                                    logger.debug(f"🔧 Tool call detected in streaming response")
                                    # 进入工具解析状态，不再输出内容
                                    continue

                                # 输出应该给用户的内容
                                if content_to_yield:
                                    output_chunk = {
                                        "id": chunk_json.get("id") or f"chatcmpl-passthrough-{uuid.uuid4().hex}",
                                        "object": "chat.completion.chunk",
                                        "created": chunk_json.get("created") or int(time.time()),
                                        "model": model,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {"content": content_to_yield},
                                            "finish_reason": None
                                        }]
                                    }
                                    yield f"data: {json.dumps(output_chunk)}\n\n".encode('utf-8')

                            # 处理 finish_reason
                            if finish_reason and finish_reason != "tool_calls":
                                final_chunk = {
                                    "id": chunk_json.get("id") or f"chatcmpl-final-{uuid.uuid4().hex}",
                                    "object": "chat.completion.chunk",
                                    "created": chunk_json.get("created") or int(time.time()),
                                    "model": model,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {},
                                        "finish_reason": finish_reason
                                    }]
                                }
                                yield f"data: {json.dumps(final_chunk)}\n\n".encode('utf-8')
                                yield b"data: [DONE]\n\n"
                                return

                        except (json.JSONDecodeError, IndexError, KeyError) as e:
                            logger.warning(f"⚠️ Failed to parse streaming chunk: {e}")
                            continue

                # 流结束，检查是否有待处理的函数调用
                if detector.has_trigger_signal():
                    logger.debug(f"🔧 Stream ended with pending function call, finalizing...")
                    parsed_tools = detector.finalize()

                    if parsed_tools:
                        logger.debug(f"🔧 Finalized {len(parsed_tools)} tool calls")
                        for sse in _build_tool_call_sse_chunks(parsed_tools, model):
                            yield sse.encode('utf-8')
                        return
                    else:
                        logger.warning(f"⚠️ Failed to parse function calls at stream end")

                # 正常结束
                yield b"data: [DONE]\n\n"

        except httpx.TimeoutException:
            logger.error(f"❌ Streaming timeout")
            error_chunk = {"error": {"message": "Gateway Timeout", "type": "timeout_error", "code": "timeout"}}
            yield f"data: {json.dumps(error_chunk)}\n\n".encode('utf-8')
        except httpx.RemoteProtocolError:
            logger.debug("🔧 Upstream closed connection prematurely, ending stream response")
        except Exception as e:
            logger.error(f"❌ Streaming error: {str(e)}")
            logger.error(f"❌ Error traceback: {traceback.format_exc()}")
            error_chunk = {"error": {"message": str(e), "type": "internal_error", "code": "internal_error"}}
            yield f"data: {json.dumps(error_chunk)}\n\n".encode('utf-8')

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


async def handle_dynamic_simple_proxy(
    request: Request,
    upstream_url: str,
    authorization: str
):
    """
    处理动态路由的简单代理请求（非 chat/completions 路径）

    Args:
        request: FastAPI 请求对象
        upstream_url: 上游服务 URL
        authorization: 授权头（已通过 request.headers 透传）

    Returns:
        代理后的响应
    """
    app_config = config_loader.config

    # 获取查询参数
    query_params = dict(request.query_params)

    # 读取请求体
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        try:
            body = await request.json()
        except Exception:
            body = await request.body()

    # 构建请求头（透传除特定头之外的所有头）
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ["host", "content-length", "transfer-encoding"]:
            headers[key] = value

    try:
        # 发送请求到上游服务
        if request.method == "GET":
            response = await http_client.get(
                upstream_url,
                headers=headers,
                params=query_params,
                timeout=app_config.server.timeout
            )
        elif request.method == "POST":
            response = await http_client.post(
                upstream_url,
                headers=headers,
                params=query_params,
                json=body if isinstance(body, dict) else None,
                content=body if isinstance(body, bytes) else None,
                timeout=app_config.server.timeout
            )
        elif request.method == "PUT":
            response = await http_client.put(
                upstream_url,
                headers=headers,
                params=query_params,
                json=body if isinstance(body, dict) else None,
                content=body if isinstance(body, bytes) else None,
                timeout=app_config.server.timeout
            )
        elif request.method == "DELETE":
            response = await http_client.delete(
                upstream_url,
                headers=headers,
                params=query_params,
                timeout=app_config.server.timeout
            )
        elif request.method == "PATCH":
            response = await http_client.patch(
                upstream_url,
                headers=headers,
                params=query_params,
                json=body if isinstance(body, dict) else None,
                content=body if isinstance(body, bytes) else None,
                timeout=app_config.server.timeout
            )
        else:
            # 其他方法
            response = await http_client.request(
                request.method,
                upstream_url,
                headers=headers,
                params=query_params,
                timeout=app_config.server.timeout
            )

        response.raise_for_status()

        # 返回响应
        return JSONResponse(
            status_code=response.status_code,
            content=response.json() if response.headers.get("content-type", "").startswith("application/json") else {"data": response.text}
        )

    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Proxy error: status_code={e.response.status_code}")
        try:
            error_json = e.response.json()
            return JSONResponse(status_code=e.response.status_code, content=error_json)
        except:
            return JSONResponse(
                status_code=e.response.status_code,
                content={"error": {"message": e.response.text}}
            )
    except httpx.TimeoutException:
        logger.error(f"❌ Proxy timeout")
        return JSONResponse(
            status_code=504,
            content={"error": {"message": "Gateway Timeout"}}
        )
    except Exception as e:
        logger.error(f"❌ Proxy error: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": {"message": "Internal Server Error"}}
        )
