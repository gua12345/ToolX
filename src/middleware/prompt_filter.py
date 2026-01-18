# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)

"""提示词过滤器

本模块实现基于 JSON 配置的提示词过滤功能，用于处理可能与函数调用提示词冲突的内容。
"""

import json
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class PromptFilterRule:
    """提示词过滤规则"""

    def __init__(self, rule_config: Dict[str, Any]):
        """
        初始化过滤规则

        Args:
            rule_config: 规则配置字典
        """
        self.name = rule_config.get("name", "Unnamed Rule")
        self.description = rule_config.get("description", "")
        self.enabled = rule_config.get("enabled", True)
        self.rule_type = rule_config.get("type", "remove_system_message")
        self.target_roles = rule_config.get("target_roles", ["system"])
        self.condition = rule_config.get("condition", {})
        self.action = rule_config.get("action", {})

    def matches(self, message: Dict[str, Any]) -> bool:
        """
        检查消息是否匹配此规则

        Args:
            message: 消息字典

        Returns:
            是否匹配
        """
        if not self.enabled:
            return False

        # 检查角色是否匹配
        role = message.get("role", "")
        if role not in self.target_roles:
            return False

        content = message.get("content", "")
        if not content:
            return False

        condition_type = self.condition.get("type", "contains")

        # contains 匹配
        if condition_type == "contains":
            patterns = self.condition.get("patterns", [])
            case_sensitive = self.condition.get("case_sensitive", False)
            match_any = self.condition.get("match_any", True)

            if not case_sensitive:
                content = content.lower()
                patterns = [p.lower() for p in patterns]

            if match_any:
                # 匹配任意一个模式
                return any(pattern in content for pattern in patterns)
            else:
                # 匹配所有模式
                return all(pattern in content for pattern in patterns)

        # starts_with 匹配
        elif condition_type == "starts_with":
            patterns = self.condition.get("patterns", [])
            case_sensitive = self.condition.get("case_sensitive", False)

            if not case_sensitive:
                content = content.lower()
                patterns = [p.lower() for p in patterns]

            return any(content.startswith(pattern) for pattern in patterns)

        # regex 匹配
        elif condition_type == "regex":
            pattern = self.condition.get("pattern", "")
            flags_str = self.condition.get("flags", "")

            # 解析正则表达式标志
            flags = 0
            if "IGNORECASE" in flags_str or "I" in flags_str:
                flags |= re.IGNORECASE
            if "DOTALL" in flags_str or "S" in flags_str:
                flags |= re.DOTALL
            if "MULTILINE" in flags_str or "M" in flags_str:
                flags |= re.MULTILINE

            try:
                return bool(re.search(pattern, content, flags))
            except re.error as e:
                logger.error(f"❌ 正则表达式错误 in rule '{self.name}': {e}")
                return False

        # length_exceeds 匹配
        elif condition_type == "length_exceeds":
            threshold = self.condition.get("threshold", 0)
            return len(content) > threshold

        return False

    def apply(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        应用过滤规则到消息

        Args:
            message: 消息字典

        Returns:
            处理后的消息，如果返回 None 表示删除该消息
        """
        if not self.matches(message):
            return message

        # remove_system_message: 删除整个消息
        if self.rule_type == "remove_system_message":
            logger.info(f"🗑️ 应用规则 '{self.name}': 删除消息")
            return None

        # replace_in_content: 替换内容
        elif self.rule_type == "replace_in_content":
            replacements = self.action.get("replacements", [])
            content = message.get("content", "")

            for replacement in replacements:
                from_text = replacement.get("from", "")
                to_text = replacement.get("to", "")
                content = content.replace(from_text, to_text)

            message["content"] = content
            logger.info(f"🔄 应用规则 '{self.name}': 替换内容")
            return message

        # remove_pattern: 删除匹配的模式
        elif self.rule_type == "remove_pattern":
            pattern = self.condition.get("pattern", "")
            flags_str = self.condition.get("flags", "")
            replacement = self.action.get("replacement", "")

            # 解析正则表达式标志
            flags = 0
            if "IGNORECASE" in flags_str or "I" in flags_str:
                flags |= re.IGNORECASE
            if "DOTALL" in flags_str or "S" in flags_str:
                flags |= re.DOTALL
            if "MULTILINE" in flags_str or "M" in flags_str:
                flags |= re.MULTILINE

            try:
                content = message.get("content", "")
                new_content = re.sub(pattern, replacement, content, flags=flags)
                message["content"] = new_content
                logger.info(f"✂️ 应用规则 '{self.name}': 删除匹配模式")
                return message
            except re.error as e:
                logger.error(f"❌ 正则表达式错误 in rule '{self.name}': {e}")
                return message

        # truncate_message: 截断消息
        elif self.rule_type == "truncate_message":
            max_length = self.action.get("max_length", 1000)
            append_notice = self.action.get("append_notice", "")

            content = message.get("content", "")
            if len(content) > max_length:
                message["content"] = content[:max_length] + append_notice
                logger.info(f"✂️ 应用规则 '{self.name}': 截断消息 ({len(content)} -> {max_length})")

            return message

        return message


class PromptFilter:
    """提示词过滤器"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化过滤器

        Args:
            config_path: 配置文件路径，如果为 None 则使用默认路径
        """
        if config_path is None:
            # 默认配置文件路径
            config_path = Path(__file__).parent.parent.parent / "prompt_filter_rules.json"
        else:
            config_path = Path(config_path)

        self.config_path = config_path
        self.enabled = False
        self.rules: List[PromptFilterRule] = []

        self._load_config()

    def _load_config(self):
        """加载配置文件"""
        if not self.config_path.exists():
            logger.warning(f"⚠️ 提示词过滤规则配置文件不存在: {self.config_path}")
            logger.info(f"💡 提示词过滤功能已禁用，如需启用请创建配置文件")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.enabled = config.get("enabled", False)

            if not self.enabled:
                logger.info(f"🔕 提示词过滤功能已禁用（配置文件中 enabled=false）")
                return

            rules_config = config.get("rules", [])
            self.rules = [PromptFilterRule(rule) for rule in rules_config]

            enabled_rules = [rule for rule in self.rules if rule.enabled]
            logger.info(f"✅ 加载提示词过滤规则: {len(enabled_rules)}/{len(self.rules)} 个规则已启用")

            for rule in enabled_rules:
                logger.debug(f"  - {rule.name}: {rule.description}")

        except json.JSONDecodeError as e:
            logger.error(f"❌ 提示词过滤规则配置文件 JSON 解析错误: {e}")
            self.enabled = False
        except Exception as e:
            logger.error(f"❌ 加载提示词过滤规则配置文件失败: {e}")
            self.enabled = False

    def filter_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        过滤消息列表

        Args:
            messages: 消息列表

        Returns:
            过滤后的消息列表
        """
        if not self.enabled or not self.rules:
            return messages

        filtered_messages = []
        removed_count = 0
        modified_count = 0

        for idx, message in enumerate(messages):
            current_message = message.copy()
            was_modified = False

            # 应用所有规则
            for rule in self.rules:
                if not rule.enabled:
                    continue

                result = rule.apply(current_message)

                if result is None:
                    # 消息被删除
                    removed_count += 1
                    logger.debug(f"🗑️ 消息 #{idx} 被规则 '{rule.name}' 删除")
                    break
                elif result != current_message:
                    # 消息被修改
                    current_message = result
                    was_modified = True

            else:
                # 消息未被删除，添加到结果列表
                if was_modified:
                    modified_count += 1
                    logger.debug(f"🔄 消息 #{idx} 被修改")

                filtered_messages.append(current_message)

        if removed_count > 0 or modified_count > 0:
            logger.info(
                f"📊 提示词过滤统计: 删除 {removed_count} 条消息, 修改 {modified_count} 条消息, "
                f"保留 {len(filtered_messages)} 条消息"
            )

        return filtered_messages

    def reload_config(self):
        """重新加载配置文件"""
        logger.info(f"🔄 重新加载提示词过滤规则配置")
        self.rules.clear()
        self._load_config()


# 全局过滤器实例
_global_filter: Optional[PromptFilter] = None


def get_prompt_filter() -> PromptFilter:
    """
    获取全局提示词过滤器实例

    Returns:
        提示词过滤器实例
    """
    global _global_filter
    if _global_filter is None:
        _global_filter = PromptFilter()
    return _global_filter


def filter_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    过滤消息列表（便捷函数）

    Args:
        messages: 消息列表

    Returns:
        过滤后的消息列表
    """
    return get_prompt_filter().filter_messages(messages)
