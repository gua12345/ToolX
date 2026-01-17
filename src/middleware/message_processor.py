# SPDX-License-Identifier: GPL-3.0-or-later
#
# Toolify: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 FunnyCups (https://github.com/funnycups)

"""消息处理模块

本模块提供消息预处理和验证功能。
"""

import logging
from typing import List, Dict, Any
from fastapi import HTTPException

from ..config.loader import config_loader
from ..function_calling.formatter import format_tool_result_for_ai, format_assistant_tool_calls_for_ai

logger = logging.getLogger(__name__)


def build_tool_call_index_from_messages(messages: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """
    从消息历史中构建 tool_call_id -> {name, arguments} 索引
    通过从助手消息中提取工具调用来替代服务器端映射

    Args:
        messages: 请求中的消息字典列表

    Returns:
        将 tool_call_id 映射到 {name, arguments} 的字典
    """
    import json

    index = {}
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls and isinstance(tool_calls, list):
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        tc_id = tc.get("id")
                        func = tc.get("function", {})
                        if tc_id and isinstance(func, dict):
                            name = func.get("name", "")
                            arguments = func.get("arguments", "{}")
                            if not isinstance(arguments, str):
                                try:
                                    arguments = json.dumps(arguments, ensure_ascii=False)
                                except Exception:
                                    arguments = str(arguments)

                            if name:
                                index[tc_id] = {
                                    "name": name,
                                    "arguments": arguments
                                }
                                logger.debug(f"🔧 Indexed tool_call_id: {tc_id} -> {name}")

    logger.debug(f"🔧 Built tool_call index with {len(index)} entries")
    return index


def preprocess_messages(messages: List[Dict[str, Any]], trigger_signal: str) -> List[Dict[str, Any]]:
    """
    预处理消息:
    - 将 role=tool 的消息转换为 role=user 文本，以便上游兼容
    - 将 assistant.tool_calls 转换为 assistant.content（XML格式），用于上游上下文
    - 如果配置了，将 developer->system

    Args:
        messages: 原始消息列表
        trigger_signal: 触发信号字符串

    Returns:
        处理后的消息列表
    """
    app_config = config_loader.config
    tool_call_index = build_tool_call_index_from_messages(messages)

    processed_messages: List[Dict[str, Any]] = []

    for message in messages:
        if isinstance(message, dict):
            if message.get("role") == "tool":
                tool_call_id = message.get("tool_call_id")
                content = message.get("content")

                if not tool_call_id:
                    raise HTTPException(status_code=400, detail="Tool message missing tool_call_id")

                # content 在某些情况下可能是空字符串；只拒绝 None
                if content is None:
                    raise HTTPException(status_code=400, detail=f"Tool message missing content for tool_call_id={tool_call_id}")

                tool_info = tool_call_index.get(tool_call_id)
                if not tool_info:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"tool_call_id={tool_call_id} not found in conversation history. "
                            f"Ensure the assistant message with this tool_call is included in the messages array."
                        )
                    )

                formatted_content = format_tool_result_for_ai(
                    tool_name=tool_info["name"],
                    tool_arguments=tool_info["arguments"],
                    result_content=content,
                )

                processed_messages.append({
                    "role": "user",
                    "content": formatted_content
                })
                logger.debug(f"🔧 Converted tool message to user message: tool_call_id={tool_call_id}, tool={tool_info['name']}")

            elif message.get("role") == "assistant" and message.get("tool_calls"):
                tool_calls = message.get("tool_calls", [])
                formatted_tool_calls_str = format_assistant_tool_calls_for_ai(tool_calls, trigger_signal)

                original_content = message.get("content") or ""
                final_content = f"{original_content}\n{formatted_tool_calls_str}".strip()

                processed_message = {
                    "role": "assistant",
                    "content": final_content
                }
                for key, value in message.items():
                    if key not in ["role", "content", "tool_calls"]:
                        processed_message[key] = value

                processed_messages.append(processed_message)
                logger.debug("🔧 Converted assistant tool_calls to content.")

            elif message.get("role") == "developer":
                if app_config.features.convert_developer_to_system:
                    processed_message = message.copy()
                    processed_message["role"] = "system"
                    processed_messages.append(processed_message)
                    logger.debug("🔧 Converted developer message to system message for better upstream compatibility")
                else:
                    processed_messages.append(message)
                    logger.debug("🔧 Keeping developer role unchanged (based on configuration)")
            else:
                processed_messages.append(message)
        else:
            processed_messages.append(message)

    return processed_messages


def validate_message_structure(messages: List[Dict[str, Any]]) -> bool:
    """
    验证消息结构的基本有效性

    Args:
        messages: 消息列表

    Returns:
        如果消息结构有效则返回 True
    """
    if not messages:
        logger.warning("⚠️ Empty messages list")
        return False

    for i, msg in enumerate(messages):
        if not isinstance(msg, dict):
            logger.warning(f"⚠️ Message {i} is not a dict")
            return False

        if "role" not in msg:
            logger.warning(f"⚠️ Message {i} missing 'role' field")
            return False

        role = msg.get("role")
        if role not in ["system", "user", "assistant", "tool", "developer"]:
            logger.warning(f"⚠️ Message {i} has invalid role: {role}")
            return False

    return True
