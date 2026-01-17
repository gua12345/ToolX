# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2026 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
# with additional dynamic routing functionality.
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""FastAPI 应用入口

本模块是 ToolX 的主入口，负责初始化配置、创建 FastAPI 应用并注册路由。
"""

import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from src.config.loader import config_loader
from src.api import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("🚀 ToolX is starting...")
    yield
    # 关闭时执行
    logger.info("👋 ToolX is shutting down...")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""

    # 加载配置
    try:
        app_config = config_loader.load_config()

        # 配置日志
        log_level_str = app_config.features.log_level
        if log_level_str == "DISABLED":
            log_level = logging.CRITICAL + 1
        else:
            log_level = getattr(logging, log_level_str, logging.INFO)

        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        logger.info(f"✅ Configuration loaded successfully: {config_loader.config_path}")
        logger.info(f"🔑 Configured {len(app_config.dynamic_routing_keys)} dynamic routing keys")
        logger.info(f"🎯 Function calling enabled: {app_config.features.enable_function_calling}")
        logger.info(f"📊 Log level: {log_level_str}")

    except Exception as e:
        print(f"❌ Configuration loading failed: {type(e).__name__}")
        print(f"❌ Error details: {str(e)}")
        print("💡 Please ensure config.yaml file exists and is properly formatted")
        exit(1)

    # 创建 FastAPI 应用
    app = FastAPI(
        title="ToolX",
        description="Empower any LLM with function calling capabilities",
        version="2.0.0",
        lifespan=lifespan
    )

    # 注册路由
    app.include_router(router)

    # 注册异常处理器
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """处理 HTTP 异常"""
        logger.warning(f"⚠️ HTTP Exception: {exc.status_code} - {exc.detail}")

        # 根据状态码确定错误类型
        if exc.status_code == 400:
            err_type = "invalid_request_error"
            code = "bad_request"
        elif exc.status_code == 401:
            err_type = "authentication_error"
            code = "unauthorized"
        elif exc.status_code == 403:
            err_type = "permission_error"
            code = "forbidden"
        elif exc.status_code == 404:
            err_type = "not_found_error"
            code = "not_found"
        elif exc.status_code == 422:
            err_type = "invalid_request_error"
            code = "validation_error"
        elif exc.status_code == 429:
            err_type = "rate_limit_error"
            code = "rate_limit_exceeded"
        elif exc.status_code >= 500:
            err_type = "server_error"
            code = "internal_error"
        else:
            err_type = "api_error"
            code = "unknown_error"

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "message": str(exc.detail),
                    "type": err_type,
                    "code": code,
                }
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """处理所有未捕获的异常"""
        logger.error(f"❌ Unhandled exception: {exc}")
        logger.error(f"❌ Request URL: {request.url}")
        logger.error(f"❌ Exception type: {type(exc).__name__}")
        logger.error(f"❌ Error stack: {traceback.format_exc()}")

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "message": "Internal server error",
                    "type": "server_error",
                    "code": "internal_error"
                }
            }
        )

    logger.info("✅ FastAPI application created successfully")
    return app


# 创建应用实例
app = create_app()


if __name__ == "__main__":
    import uvicorn

    app_config = config_loader.config

    logger.info(f"🌐 Starting server on {app_config.server.host}:{app_config.server.port}")
    logger.info(f"⏱️  Request timeout: {app_config.server.timeout}s")
    logger.info(f"🔧 Features:")
    logger.info(f"   - Function calling: {app_config.features.enable_function_calling}")
    logger.info(f"   - Convert developer to system: {app_config.features.convert_developer_to_system}")
    logger.info(f"   - FC error retry: {app_config.features.enable_fc_error_retry}")
    if app_config.features.enable_fc_error_retry:
        logger.info(f"   - FC retry max attempts: {app_config.features.fc_error_retry_max_attempts}")

    uvicorn.run(
        app,
        host=app_config.server.host,
        port=app_config.server.port,
        log_level=app_config.features.log_level.lower() if app_config.features.log_level != "DISABLED" else "critical"
    )
