# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""函数调用模块"""

from .parser import (
    parse_function_calls_xml,
    StreamingFunctionCallDetector,
    remove_think_blocks,
    find_last_trigger_signal_outside_think
)
from .formatter import (
    format_tool_result_for_ai,
    format_assistant_tool_calls_for_ai
)
from .prompt import (
    generate_function_prompt,
    get_function_call_prompt_template,
    safe_process_tool_choice
)
from .retry import (
    attempt_fc_parse_with_retry,
    get_fc_error_retry_prompt
)
from .models import Tool, ToolFunction, ToolChoice

__all__ = [
    # 解析器
    "parse_function_calls_xml",
    "StreamingFunctionCallDetector",
    "remove_think_blocks",
    "find_last_trigger_signal_outside_think",
    # 格式化器
    "format_tool_result_for_ai",
    "format_assistant_tool_calls_for_ai",
    # 提示生成
    "generate_function_prompt",
    "get_function_call_prompt_template",
    "safe_process_tool_choice",
    # 重试
    "attempt_fc_parse_with_retry",
    "get_fc_error_retry_prompt",
    # 模型
    "Tool",
    "ToolFunction",
    "ToolChoice",
]
