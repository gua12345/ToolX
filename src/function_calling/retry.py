# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""函数调用重试模块

本模块提供函数调用解析失败时的自动重试功能。
"""

import re
import json
import logging
import httpx
from typing import List, Dict, Any, Optional

from .parser import parse_function_calls_xml, remove_think_blocks
from ..config.loader import config_loader

logger = logging.getLogger(__name__)

# 全局 HTTP 客户端
http_client = httpx.AsyncClient()


def get_fc_error_retry_prompt(original_response: str, error_details: str) -> str:
    """
    生成函数调用错误重试提示

    Args:
        original_response: 原始响应内容
        error_details: 错误详情

    Returns:
        重试提示字符串
    """
    app_config = config_loader.config
    custom_template = app_config.features.fc_error_retry_prompt_template
    if custom_template:
        return custom_template.format(
            original_response=original_response,
            error_details=error_details
        )

    return f"""Your previous response attempted to make a function call but the format was invalid or could not be parsed.

**Your original response:**
```
{original_response}
```

**Error details:**
{error_details}

**Instructions:**
Please retry and output the function call in the correct XML format. Remember:
1. Start with the trigger signal on its own line
2. Immediately follow with the <function_calls> XML block
3. Use <args_json> with valid JSON for parameters
4. Do not add any text after </function_calls>

Please provide the corrected function call now. DO NOT OUTPUT ANYTHING ELSE."""


def _diagnose_fc_parse_error(content: str, trigger_signal: str) -> str:
    """
    诊断函数调用解析失败的原因并返回错误描述

    Args:
        content: 响应内容
        trigger_signal: 触发信号字符串

    Returns:
        错误描述字符串
    """
    errors = []

    if trigger_signal not in content:
        errors.append(f"Trigger signal '{trigger_signal[:30]}...' not found in response")
        return "; ".join(errors)

    cleaned = remove_think_blocks(content)

    if "<function_calls>" not in cleaned:
        errors.append("Missing <function_calls> tag after trigger signal")
    elif "</function_calls>" not in cleaned:
        errors.append("Missing closing </function_calls> tag")

    if "<function_call>" not in cleaned:
        errors.append("No <function_call> blocks found inside <function_calls>")
    elif "</function_call>" not in cleaned:
        errors.append("Missing closing </function_call> tag")

    fc_match = re.search(r"<function_calls>([\s\S]*?)</function_calls>", cleaned)
    if fc_match:
        fc_content = fc_match.group(1)

        if "<tool>" not in fc_content:
            errors.append("Missing <tool> tag inside function_call")

        if "<args_json>" not in fc_content and "<args>" not in fc_content:
            errors.append("Missing <args_json> or <args> tag inside function_call")

        args_json_match = re.search(r"<args_json>([\s\S]*?)</args_json>", fc_content)
        if args_json_match:
            args_content = args_json_match.group(1).strip()
            cdata_match = re.search(r"<!\[CDATA\[([\s\S]*?)\]\]>", args_content)
            json_to_parse = cdata_match.group(1) if cdata_match else args_content

            try:
                json.loads(json_to_parse)
            except json.JSONDecodeError as e:
                errors.append(f"Invalid JSON in args_json: {str(e)}")

    if not errors:
        errors.append("XML structure appears correct but parsing failed for unknown reason")

    return "; ".join(errors)


async def attempt_fc_parse_with_retry(
    content: str,
    trigger_signal: str,
    messages: List[Dict[str, Any]],
    upstream_url: str,
    headers: Dict[str, str],
    model: str,
    timeout: int
) -> Optional[List[Dict[str, Any]]]:
    """
    尝试从内容中解析函数调用。如果解析失败且启用了重试，
    将错误详情发送回模型进行纠正。

    Args:
        content: 响应内容
        trigger_signal: 触发信号字符串
        messages: 消息历史
        upstream_url: 上游服务URL
        headers: 请求头
        model: 模型名称
        timeout: 超时时间（秒）

    Returns:
        解析出的工具调用列表，如果最终解析失败则返回 None
    """
    app_config = config_loader.config
    if not app_config.features.enable_fc_error_retry:
        return parse_function_calls_xml(content, trigger_signal)

    max_attempts = app_config.features.fc_error_retry_max_attempts
    current_content = content
    current_messages = messages.copy()

    for attempt in range(max_attempts):
        parsed_tools = parse_function_calls_xml(current_content, trigger_signal)

        if parsed_tools:
            if attempt > 0:
                logger.info(f"✅ Function call parsing succeeded on retry attempt {attempt + 1}")
            return parsed_tools

        if trigger_signal not in current_content:
            logger.debug(f"🔧 No trigger signal found in response, not a function call attempt")
            return None

        if attempt >= max_attempts - 1:
            logger.warning(f"⚠️ Function call parsing failed after {max_attempts} attempts")
            return None

        error_details = _diagnose_fc_parse_error(current_content, trigger_signal)
        retry_prompt = get_fc_error_retry_prompt(current_content, error_details)

        logger.info(f"🔄 Function call parsing failed, attempting retry {attempt + 2}/{max_attempts}")
        logger.debug(f"🔧 Error details: {error_details}")

        retry_messages = current_messages + [
            {"role": "assistant", "content": current_content},
            {"role": "user", "content": retry_prompt}
        ]

        try:
            retry_response = await http_client.post(
                upstream_url,
                json={"model": model, "messages": retry_messages, "stream": False},
                headers=headers,
                timeout=timeout
            )
            retry_response.raise_for_status()
            retry_json = retry_response.json()

            if retry_json.get("choices") and len(retry_json["choices"]) > 0:
                current_content = retry_json["choices"][0].get("message", {}).get("content", "")
                current_messages = retry_messages
                logger.debug(f"🔧 Received retry response, length: {len(current_content)}")
            else:
                logger.warning(f"⚠️ Retry response has no valid choices")
                return None

        except Exception as e:
            logger.error(f"❌ Retry request failed: {e}")
            return None

    return None
