#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提示词过滤器测试脚本

用于测试提示词过滤器的各种规则是否正常工作。
"""

import json
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.middleware.prompt_filter import PromptFilter


def test_remove_system_message():
    """测试删除系统消息"""
    print("\n=== 测试 1: 删除系统消息 ===")

    messages = [
        {"role": "system", "content": "You are Roo, a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"}
    ]

    filter_config = {
        "enabled": True,
        "rules": [
            {
                "name": "Remove Roo",
                "enabled": True,
                "type": "remove_system_message",
                "target_roles": ["system"],
                "condition": {
                    "type": "contains",
                    "patterns": ["You are Roo"],
                    "case_sensitive": False,
                    "match_any": True
                }
            }
        ]
    }

    # 创建临时配置文件
    temp_config = project_root / "test_filter_config.json"
    with open(temp_config, "w", encoding="utf-8") as f:
        json.dump(filter_config, f, ensure_ascii=False, indent=2)

    # 测试过滤
    prompt_filter = PromptFilter(str(temp_config))
    filtered = prompt_filter.filter_messages(messages)

    print(f"原始消息数: {len(messages)}")
    print(f"过滤后消息数: {len(filtered)}")
    print(f"预期: 2 条消息（删除了 system 消息）")

    assert len(filtered) == 2, f"预期 2 条消息，实际 {len(filtered)} 条"
    assert filtered[0]["role"] == "user", "第一条消息应该是 user"

    # 清理
    temp_config.unlink()

    print("✅ 测试通过")


def test_replace_in_content():
    """测试替换内容"""
    print("\n=== 测试 2: 替换内容 ===")

    messages = [
        {"role": "system", "content": "Use <function_calls> to call functions."},
        {"role": "user", "content": "Hello!"}
    ]

    filter_config = {
        "enabled": True,
        "rules": [
            {
                "name": "Replace tags",
                "enabled": True,
                "type": "replace_in_content",
                "target_roles": ["system"],
                "condition": {
                    "type": "contains",
                    "patterns": ["<function_calls>"],
                    "case_sensitive": True,
                    "match_any": True
                },
                "action": {
                    "replacements": [
                        {"from": "<function_calls>", "to": "[function_calls]"}
                    ]
                }
            }
        ]
    }

    # 创建临时配置文件
    temp_config = project_root / "test_filter_config.json"
    with open(temp_config, "w", encoding="utf-8") as f:
        json.dump(filter_config, f, ensure_ascii=False, indent=2)

    # 测试过滤
    prompt_filter = PromptFilter(str(temp_config))
    filtered = prompt_filter.filter_messages(messages)

    print(f"原始内容: {messages[0]['content']}")
    print(f"过滤后内容: {filtered[0]['content']}")
    print(f"预期: 包含 [function_calls]")

    assert "[function_calls]" in filtered[0]["content"], "应该包含替换后的标签"
    assert "<function_calls>" not in filtered[0]["content"], "不应该包含原始标签"

    # 清理
    temp_config.unlink()

    print("✅ 测试通过")


def test_remove_pattern():
    """测试删除模式"""
    print("\n=== 测试 3: 删除模式（正则表达式）===")

    messages = [
        {
            "role": "system",
            "content": """====

MARKDOWN RULES

ALL responses MUST show ANY `language construct` OR filename reference as clickable, exactly as [`filename OR language.declaration()`](relative/file/path.ext:line); line is required for `syntax` and optional for filename links. This applies to ALL markdown responses and ALSO those in attempt_completion

====

TOOL USE

You have access to a set of tools that are executed upon the user's approval. Use the provider-native tool-calling mechanism. Do not include XML markup or examples. You must use exactly one tool call per assistant response. Do not call zero tools or more than one tool in the same response.

# Tool Use Guidelines

1. Assess what information you already have and what information you need to proceed with the task.
2. Choose the most appropriate tool based on the task and the tool descriptions provided. Assess if you need additional information to proceed, and which of the available tools would be most effective for gathering this information. For example using the list_files tool is more effective than running a command like `ls` in the terminal. It's critical that you think about each available tool and use the one that best fits the current step in the task.
3. If multiple actions are needed, use one tool at a time per message to accomplish the task iteratively, with each tool use being informed by the result of the previous tool use. Do not assume the outcome of any tool use. Each step must be informed by the previous step's result.
4. After each tool use, the user will respond with the result of that tool use. This result will provide you with the necessary information to continue your task or make further decisions. This response may include:
	 - Information about whether the tool succeeded or failed, along with any reasons for failure.
	 - Linter errors that may have arisen due to the changes you made, which you'll need to address.
	 - New terminal output in reaction to the changes, which you may need to consider or act upon.
	 - Any other relevant feedback or information related to the tool use.

By carefully considering the user's response after tool executions, you can react accordingly and make informed decisions about how to proceed with the task. This iterative process helps ensure the overall success and accuracy of your work.



====
"""
        },
        {"role": "user", "content": "Hello!"}
    ]

    filter_config = {
        "enabled": True,
        "rules": [
            {
                "name": "Remove tool instructions",
                "enabled": True,
                "type": "remove_pattern",
                "target_roles": ["system"],
                "condition": {
                    "type": "regex",
                    "pattern": "====\\s*TOOL USE.*?(?====)",
                    "flags": "DOTALL"
                },
                "action": {
                    "replacement": ""
                }
            }
        ]
    }

    # 创建临时配置文件
    temp_config = project_root / "test_filter_config.json"
    with open(temp_config, "w", encoding="utf-8") as f:
        json.dump(filter_config, f, ensure_ascii=False, indent=2)

    # 测试过滤
    prompt_filter = PromptFilter(str(temp_config))
    filtered = prompt_filter.filter_messages(messages)

    print(f"原始内容长度: {len(messages[0]['content'])}")
    print(f"过滤后内容长度: {len(filtered[0]['content'])}")
    print(f"过滤后内容: {filtered[0]['content']}")

    assert "TOOL USE" not in filtered[0]["content"], "不应该包含 TOOL USE"
    assert "MARKDOWN RULES" in filtered[0]["content"], "应该保留 MARKDOWN RULES"
    assert filtered[0]["content"].count("====") == 2, "应该保留两个 ===="

    # 清理
    temp_config.unlink()

    print("✅ 测试通过")


def test_truncate_message():
    """测试截断消息"""
    print("\n=== 测试 4: 截断消息 ===")

    long_content = "A" * 1000
    messages = [
        {"role": "system", "content": long_content},
        {"role": "user", "content": "Hello!"}
    ]

    filter_config = {
        "enabled": True,
        "rules": [
            {
                "name": "Truncate long messages",
                "enabled": True,
                "type": "truncate_message",
                "target_roles": ["system"],
                "condition": {
                    "type": "length_exceeds",
                    "threshold": 500
                },
                "action": {
                    "max_length": 300,
                    "append_notice": "...[truncated]"
                }
            }
        ]
    }

    # 创建临时配置文件
    temp_config = project_root / "test_filter_config.json"
    with open(temp_config, "w", encoding="utf-8") as f:
        json.dump(filter_config, f, ensure_ascii=False, indent=2)

    # 测试过滤
    prompt_filter = PromptFilter(str(temp_config))
    filtered = prompt_filter.filter_messages(messages)

    print(f"原始内容长度: {len(messages[0]['content'])}")
    print(f"过滤后内容长度: {len(filtered[0]['content'])}")
    print(f"预期长度: 300 + len('[truncated]')")

    assert len(filtered[0]["content"]) <= 320, "内容应该被截断"
    assert "[truncated]" in filtered[0]["content"], "应该包含截断提示"

    # 清理
    temp_config.unlink()

    print("✅ 测试通过")


def test_disabled_filter():
    """测试禁用过滤器"""
    print("\n=== 测试 5: 禁用过滤器 ===")

    messages = [
        {"role": "system", "content": "You are Roo, a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ]

    filter_config = {
        "enabled": False,
        "rules": [
            {
                "name": "Remove Roo",
                "enabled": True,
                "type": "remove_system_message",
                "target_roles": ["system"],
                "condition": {
                    "type": "contains",
                    "patterns": ["You are Roo"]
                }
            }
        ]
    }

    # 创建临时配置文件
    temp_config = project_root / "test_filter_config.json"
    with open(temp_config, "w", encoding="utf-8") as f:
        json.dump(filter_config, f, ensure_ascii=False, indent=2)

    # 测试过滤
    prompt_filter = PromptFilter(str(temp_config))
    filtered = prompt_filter.filter_messages(messages)

    print(f"原始消息数: {len(messages)}")
    print(f"过滤后消息数: {len(filtered)}")
    print(f"预期: 2 条消息（过滤器被禁用）")

    assert len(filtered) == 2, "过滤器被禁用时不应该删除消息"

    # 清理
    temp_config.unlink()

    print("✅ 测试通过")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("提示词过滤器测试")
    print("=" * 60)

    try:
        test_remove_system_message()
        test_replace_in_content()
        test_remove_pattern()
        test_truncate_message()
        test_disabled_filter()

        print("\n" + "=" * 60)
        print("✅ 所有测试通过！")
        print("=" * 60)

    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
