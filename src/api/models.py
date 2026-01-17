# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""API 数据模型

本模块定义 API 请求和响应的数据模型。
"""

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel

from ..function_calling.models import Tool, ToolChoice


class Message(BaseModel):
    """消息模型"""
    role: str
    content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

    class Config:
        extra = "allow"


class ChatCompletionRequest(BaseModel):
    """聊天补全请求模型"""
    model: str
    messages: List[Dict[str, Any]]
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[Union[str, ToolChoice]] = None
    stream: Optional[bool] = False
    stream_options: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    n: Optional[int] = None
    stop: Optional[Union[str, List[str]]] = None

    class Config:
        extra = "allow"
