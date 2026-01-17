# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""函数调用格式化模块

本模块提供工具调用结果和助手工具调用的格式化功能。
"""

import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def format_tool_result_for_ai(tool_name: str, tool_arguments: str, result_content: str) -> str:
    """
    格式化工具调用结果，使AI能够理解完整的上下文

    Args:
        tool_name: 被调用的工具名称
        tool_arguments: 传递给工具的参数（JSON字符串）
        result_content: 工具的执行结果

    Returns:
        格式化后的文本，用于上游模型
    """
    formatted_text = f"""Tool execution result:
- Tool name: {tool_name}
- Tool arguments: {tool_arguments}
- Execution result:
<tool_result>
{result_content}
</tool_result>"""

    logger.debug(f"🔧 Formatted tool result for {tool_name}")
    return formatted_text


def format_assistant_tool_calls_for_ai(tool_calls: List[Dict[str, Any]], trigger_signal: str) -> str:
    """
    将助手的工具调用格式化为AI可读的字符串格式

    Args:
        tool_calls: 工具调用列表，每个调用包含 function 字段
        trigger_signal: 触发信号字符串

    Returns:
        格式化后的XML字符串，包含所有工具调用
    """
    logger.debug(f"🔧 Formatting assistant tool calls. Count: {len(tool_calls)}")

    def _wrap_cdata(text: str) -> str:
        """将文本包装在CDATA块中，避免XML转义问题"""
        # 避免CDATA内部出现非法的 ']]>' 序列，通过分割处理
        safe = (text or "").replace("]]>", "]]]]><![CDATA[>")
        return f"<![CDATA[{safe}]]>"

    xml_calls_parts = []
    for tool_call in tool_calls:
        function_info = tool_call.get("function", {})
        name = function_info.get("name", "")
        arguments_json = function_info.get("arguments", "{}")

        try:
            # 首先尝试作为JSON加载。如果是有效的JSON字符串，我们解析它
            args_dict = json.loads(arguments_json)
        except (json.JSONDecodeError, TypeError):
            # 如果不是有效的JSON字符串，将其视为简单字符串
            args_dict = {"raw_arguments": arguments_json}

        args_payload = json.dumps(args_dict, ensure_ascii=False)
        xml_call = (
            f"<function_call>\n"
            f"<tool>{name}</tool>\n"
            f"<args_json>{_wrap_cdata(args_payload)}</args_json>\n"
            f"</function_call>"
        )
        xml_calls_parts.append(xml_call)

    all_calls = "\n".join(xml_calls_parts)
    final_str = f"{trigger_signal}\n<function_calls>\n{all_calls}\n</function_calls>"

    logger.debug("🔧 Assistant tool calls formatted successfully.")
    return final_str
