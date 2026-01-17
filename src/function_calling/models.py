# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""函数调用数据模型

本模块定义函数调用相关的数据模型。
"""

from typing import Dict, Any, Optional, Literal
from pydantic import BaseModel


class ToolFunction(BaseModel):
    """工具函数定义"""
    name: str
    description: Optional[str] = None
    parameters: Dict[str, Any]


class Tool(BaseModel):
    """工具定义"""
    type: Literal["function"]
    function: ToolFunction


class ToolChoice(BaseModel):
    """工具选择定义"""
    type: Literal["function"]
    function: Dict[str, str]
