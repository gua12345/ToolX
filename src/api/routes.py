# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""API 路由定义

本模块定义动态路由端点。
"""

import logging
from fastapi import APIRouter, Request

from .handlers import handle_dynamic_routing
from ..config.loader import config_loader

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def read_root():
    """根路径，返回服务状态"""
    app_config = config_loader.config
    return {
        "status": "Toolify is running",
        "version": "2.0.0",
        "config": {
            "dynamic_routing_keys_count": len(app_config.dynamic_routing_keys),
            "features": {
                "function_calling": app_config.features.enable_function_calling,
                "log_level": app_config.features.log_level,
                "convert_developer_to_system": app_config.features.convert_developer_to_system,
                "random_trigger": True
            }
        }
    }


@router.api_route(
    "/{path_key}/{protocol}/{base_url:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
)
async def dynamic_routing_handler(
    request: Request,
    path_key: str,
    protocol: str,
    base_url: str
):
    """
    动态路由处理器
    格式: /{path_key}/{protocol}/{base_url}/{remaining_path}

    - path_key: 认证密钥（从 dynamic_routing_keys 配置中验证）
    - protocol: http 或 https
    - base_url: 目标服务的基础 URL（如 api.openai.com/v1）
    - remaining_path: API 端点路径（如 /chat/completions）

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
    return await handle_dynamic_routing(request, path_key, protocol, base_url)
