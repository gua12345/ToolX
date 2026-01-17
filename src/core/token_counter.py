# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""Token 计数器"""

import logging
import tiktoken
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class TokenCounter:
    """使用 tiktoken 的 Token 计数器"""

    # 模型前缀到编码的映射（来自 tiktoken 源码）
    MODEL_PREFIX_TO_ENCODING = {
        "o1-": "o200k_base",
        "o3-": "o200k_base",
        "o4-mini-": "o200k_base",
        # chat
        "gpt-5-": "o200k_base",
        "gpt-4.5-": "o200k_base",
        "gpt-4.1-": "o200k_base",
        "chatgpt-4o-": "o200k_base",
        "gpt-4o-": "o200k_base",
        "gpt-4-": "cl100k_base",
        "gpt-3.5-turbo-": "cl100k_base",
        "gpt-35-turbo-": "cl100k_base",  # Azure 部署名称
        "gpt-oss-": "o200k_harmony",
        # fine-tuned
        "ft:gpt-4o": "o200k_base",
        "ft:gpt-4": "cl100k_base",
        "ft:gpt-3.5-turbo": "cl100k_base",
        "ft:davinci-002": "cl100k_base",
        "ft:babbage-002": "cl100k_base",
    }

    def __init__(self):
        self.encoders = {}

    def get_encoder(self, model: str):
        """获取或创建模型的编码器"""
        if model not in self.encoders:
            encoding = None

            # 首先尝试直接从模型名称获取编码
            try:
                self.encoders[model] = tiktoken.encoding_for_model(model)
                return self.encoders[model]
            except KeyError:
                pass

            # 尝试通过前缀匹配查找编码
            for prefix, enc_name in self.MODEL_PREFIX_TO_ENCODING.items():
                if model.startswith(prefix):
                    encoding = enc_name
                    break

            # 对于较新的模型，默认使用 o200k_base
            if encoding is None:
                logger.warning(f"模型 {model} 未在前缀映射中找到，使用 o200k_base 编码")
                encoding = "o200k_base"

            try:
                self.encoders[model] = tiktoken.get_encoding(encoding)
            except Exception as e:
                logger.warning(f"获取模型 {model} 的编码 {encoding} 失败: {e}。回退到 cl100k_base")
                self.encoders[model] = tiktoken.get_encoding("cl100k_base")

        return self.encoders[model]

    def count_tokens(self, messages: List[Dict[str, Any]], model: str = "gpt-3.5-turbo") -> int:
        """计算消息列表中的 token 数量"""
        encoder = self.get_encoder(model)

        # 所有现代聊天模型使用类似的 token 计数方式
        return self._count_chat_tokens(messages, encoder, model)

    def _count_chat_tokens(self, messages: List[Dict[str, Any]], encoder, model: str) -> int:
        """
        聊天模型的精确 token 计算

        基于 OpenAI 的 token 计数文档:
        - 每条消息有固定的开销
        - 每条消息的内容 token 单独计算
        - 消息格式的特殊 token
        """
        # Token 开销因模型而异
        if model.startswith(("gpt-3.5-turbo", "gpt-35-turbo")):
            # gpt-3.5-turbo 使用不同的消息开销
            tokens_per_message = 4  # <|start|>role<|separator|>content<|end|>
            tokens_per_name = -1    # 如果不存在则省略名称
        else:
            # 大多数模型包括 gpt-4, gpt-4o, o1 等
            tokens_per_message = 3
            tokens_per_name = 1

        num_tokens = 0
        for message in messages:
            num_tokens += tokens_per_message

            # 计算消息中每个字段的 token
            for key, value in message.items():
                if key == "content":
                    # 处理内容可能是列表的情况（多模态消息）
                    if isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict) and item.get("type") == "text":
                                content_text = item.get("text", "")
                                num_tokens += len(encoder.encode(content_text, disallowed_special=()))
                            # 注意: 图像 token 在这里不计算，因为它们有固定成本
                    elif isinstance(value, str):
                        num_tokens += len(encoder.encode(value, disallowed_special=()))
                elif key == "name":
                    num_tokens += tokens_per_name
                    if isinstance(value, str):
                        num_tokens += len(encoder.encode(value, disallowed_special=()))
                elif key == "role":
                    # 角色已在 tokens_per_message 中计算
                    pass
                elif isinstance(value, str):
                    # 其他字符串字段
                    num_tokens += len(encoder.encode(value, disallowed_special=()))

        # 每个回复都以 assistant 角色开始
        num_tokens += 3
        return num_tokens

    def count_text_tokens(self, text: str, model: str = "gpt-3.5-turbo") -> int:
        """计算纯文本中的 token 数量"""
        encoder = self.get_encoder(model)
        return len(encoder.encode(text, disallowed_special=()))


# 全局 token 计数器实例
token_counter = TokenCounter()
