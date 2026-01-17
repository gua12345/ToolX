# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""配置数据模型"""

from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class ServerConfig(BaseModel):
    """服务器配置"""
    port: int = Field(default=8000, ge=1, le=65535, description="服务器端口")
    host: str = Field(default="0.0.0.0", description="服务器监听地址")
    timeout: int = Field(default=180, ge=1, description="请求超时时间（秒）")


class FeaturesConfig(BaseModel):
    """功能配置"""
    enable_function_calling: bool = Field(default=True, description="启用函数调用功能")
    log_level: str = Field(default="INFO", description="日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL, DISABLED")
    convert_developer_to_system: bool = Field(default=True, description="将 developer 角色转换为 system 角色")
    prompt_template: Optional[str] = Field(default=None, description="自定义函数调用 prompt 模板")

    # 函数调用错误重试配置
    enable_fc_error_retry: bool = Field(default=False, description="启用函数调用解析错误自动重试")
    fc_error_retry_max_attempts: int = Field(default=3, ge=1, le=10, description="函数调用错误重试最大次数")
    fc_error_retry_prompt_template: Optional[str] = Field(default=None, description="函数调用错误重试 prompt 模板")

    @field_validator('log_level')
    def validate_log_level(cls, v):
        """验证日志级别"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "DISABLED"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level 必须是以下之一: {valid_levels}")
        return v.upper()

    @field_validator('prompt_template')
    def validate_prompt_template(cls, v):
        """验证 prompt 模板"""
        if v:
            if "{tools_list}" not in v or "{trigger_signal}" not in v:
                raise ValueError("prompt_template 必须包含 {tools_list} 和 {trigger_signal} 占位符")
        return v

    @field_validator('fc_error_retry_prompt_template')
    def validate_fc_error_retry_prompt_template(cls, v):
        """验证错误重试 prompt 模板"""
        if v:
            if "{error_details}" not in v or "{original_response}" not in v:
                raise ValueError("fc_error_retry_prompt_template 必须包含 {error_details} 和 {original_response} 占位符")
        return v


class AppConfig(BaseModel):
    """应用完整配置"""
    server: ServerConfig = Field(default_factory=ServerConfig)

    # 动态路由认证密钥列表
    dynamic_routing_keys: List[str] = Field(
        description="动态路由认证密钥列表，用于 URL 路径中的 path_key 验证"
    )

    features: FeaturesConfig = Field(default_factory=FeaturesConfig)

    @field_validator('dynamic_routing_keys')
    def validate_dynamic_routing_keys(cls, v):
        """验证动态路由密钥"""
        if not v or len(v) == 0:
            raise ValueError('dynamic_routing_keys 不能为空')
        for key in v:
            if not key or key.strip() == "":
                raise ValueError('动态路由密钥不能为空字符串')
        return v
