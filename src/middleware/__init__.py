# SPDX-License-Identifier: GPL-3.0-or-later
#
# Toolify: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 FunnyCups (https://github.com/funnycups)

"""消息处理中间件模块"""

from .message_processor import (
    preprocess_messages,
    validate_message_structure,
    build_tool_call_index_from_messages
)

__all__ = [
    "preprocess_messages",
    "validate_message_structure",
    "build_tool_call_index_from_messages",
]
