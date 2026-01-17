# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""配置加载器"""

import os
import yaml
from typing import Set
from .models import AppConfig


class ConfigLoader:
    """配置加载器"""

    def __init__(self, config_path: str = "config.yaml"):
        self.config_path = config_path
        self._config: AppConfig = None

    def load_config(self) -> AppConfig:
        """加载配置文件"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(
                f"配置文件 '{self.config_path}' 未找到。"
                f"请将 'config.example.yaml' 复制为 '{self.config_path}' 并根据需要修改配置。"
            )

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"配置文件格式错误: {e}")
        except Exception as e:
            raise ValueError(f"读取配置文件失败: {e}")

        if not config_data:
            raise ValueError("配置文件为空")

        try:
            self._config = AppConfig(**config_data)
            return self._config
        except Exception as e:
            raise ValueError(f"配置验证失败: {e}")

    @property
    def config(self) -> AppConfig:
        """获取配置对象"""
        if self._config is None:
            self.load_config()
        return self._config

    def get_log_level(self) -> str:
        """获取配置的日志级别"""
        return self.config.features.log_level

    def get_dynamic_routing_keys(self) -> Set[str]:
        """获取动态路由密钥集合"""
        return set(self.config.dynamic_routing_keys)


# 全局配置加载器实例
config_loader = ConfigLoader()
