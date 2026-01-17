# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""函数调用解析模块

本模块提供函数调用的XML解析和流式检测功能。
"""

import re
import json
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def remove_think_blocks(text: str) -> str:
    """
    临时移除所有 <think>...</think> 块以便进行XML解析
    支持嵌套的think标签
    注意：此函数仅用于临时解析，不影响返回给用户的原始内容

    Args:
        text: 包含think块的文本

    Returns:
        移除think块后的文本
    """
    while '<think>' in text and '</think>' in text:
        start_pos = text.find('<think>')
        if start_pos == -1:
            break

        pos = start_pos + 7
        depth = 1

        while pos < len(text) and depth > 0:
            if text[pos:pos+7] == '<think>':
                depth += 1
                pos += 7
            elif text[pos:pos+8] == '</think>':
                depth -= 1
                pos += 8
            else:
                pos += 1

        if depth == 0:
            text = text[:start_pos] + text[pos:]
        else:
            break

    return text


def find_last_trigger_signal_outside_think(text: str, trigger_signal: str) -> int:
    """
    查找不在任何 <think>...</think> 块内的最后一个 trigger_signal 出现位置

    Args:
        text: 要搜索的文本
        trigger_signal: 触发信号字符串

    Returns:
        最后一个触发信号的位置，如果未找到则返回-1
    """
    if not text or not trigger_signal:
        return -1

    i = 0
    think_depth = 0
    last_pos = -1

    while i < len(text):
        if text.startswith("<think>", i):
            think_depth += 1
            i += 7
            continue

        if text.startswith("</think>", i):
            think_depth = max(0, think_depth - 1)
            i += 8
            continue

        if think_depth == 0 and text.startswith(trigger_signal, i):
            last_pos = i
            # 向前移动1个字符以允许重叠搜索（虽然不太可能，但更安全）
            i += 1
            continue

        i += 1

    return last_pos


class StreamingFunctionCallDetector:
    """增强的流式函数调用检测器，支持动态触发信号，避免在 <think> 标签内误判

    核心特性：
    1. 避免在 <think> 块内触发工具调用检测
    2. 正常输出 <think> 块内容给用户
    3. 支持嵌套的think标签
    """

    def __init__(self, trigger_signal: str):
        """
        初始化检测器

        Args:
            trigger_signal: 触发函数调用的信号字符串
        """
        self.trigger_signal = trigger_signal
        self.reset()

    def reset(self):
        """重置检测器状态"""
        self.content_buffer = ""
        self.state = "detecting"  # detecting, tool_parsing
        self.in_think_block = False
        self.think_depth = 0
        self.signal = self.trigger_signal
        self.signal_len = len(self.signal)

    def process_chunk(self, delta_content: str) -> tuple[bool, str]:
        """
        处理流式内容块

        Args:
            delta_content: 新接收到的内容块

        Returns:
            (is_tool_call_detected, content_to_yield):
            - is_tool_call_detected: 是否检测到工具调用
            - content_to_yield: 应该输出给用户的内容
        """
        if not delta_content:
            return False, ""

        self.content_buffer += delta_content
        content_to_yield = ""

        if self.state == "tool_parsing":
            return False, ""

        if delta_content:
            logger.debug(f"🔧 Processing chunk: {repr(delta_content[:50])}{'...' if len(delta_content) > 50 else ''}, buffer length: {len(self.content_buffer)}, think state: {self.in_think_block}")

        i = 0
        while i < len(self.content_buffer):
            skip_chars = self._update_think_state(i)
            if skip_chars > 0:
                for j in range(skip_chars):
                    if i + j < len(self.content_buffer):
                        content_to_yield += self.content_buffer[i + j]
                i += skip_chars
                continue

            if not self.in_think_block and self._can_detect_signal_at(i):
                if self.content_buffer[i:i+self.signal_len] == self.signal:
                    logger.debug(f"🔧 Improved detector: detected trigger signal in non-think block! Signal: {self.signal[:20]}...")
                    logger.debug(f"🔧 Trigger signal position: {i}, think state: {self.in_think_block}, think depth: {self.think_depth}")
                    self.state = "tool_parsing"
                    self.content_buffer = self.content_buffer[i:]
                    return True, content_to_yield

            remaining_len = len(self.content_buffer) - i
            if remaining_len < self.signal_len or remaining_len < 8:
                break

            content_to_yield += self.content_buffer[i]
            i += 1

        self.content_buffer = self.content_buffer[i:]
        return False, content_to_yield

    def _update_think_state(self, pos: int):
        """
        更新think标签状态，支持嵌套

        Args:
            pos: 当前位置

        Returns:
            需要跳过的字符数
        """
        remaining = self.content_buffer[pos:]

        if remaining.startswith('<think>'):
            self.think_depth += 1
            self.in_think_block = True
            logger.debug(f"🔧 Entering think block, depth: {self.think_depth}")
            return 7

        elif remaining.startswith('</think>'):
            self.think_depth = max(0, self.think_depth - 1)
            self.in_think_block = self.think_depth > 0
            logger.debug(f"🔧 Exiting think block, depth: {self.think_depth}")
            return 8

        return 0

    def _can_detect_signal_at(self, pos: int) -> bool:
        """
        检查是否可以在指定位置检测信号

        Args:
            pos: 要检查的位置

        Returns:
            是否可以检测信号
        """
        return (pos + self.signal_len <= len(self.content_buffer) and
                not self.in_think_block)

    def feed(self, content: str):
        """
        喂入内容（兼容旧接口，内部调用 process_chunk）

        Args:
            content: 要处理的内容
        """
        self.process_chunk(content)

    def has_trigger_signal(self) -> bool:
        """
        检查是否检测到触发信号

        Returns:
            如果检测到触发信号则返回 True
        """
        return self.state == "tool_parsing"

    def finalize(self) -> Optional[List[Dict[str, Any]]]:
        """
        流结束时的最终处理

        Returns:
            解析出的函数调用列表，如果没有则返回None
        """
        if self.state == "tool_parsing":
            return parse_function_calls_xml(self.content_buffer, self.trigger_signal)
        return None


def parse_function_calls_xml(xml_string: str, trigger_signal: str) -> Optional[List[Dict[str, Any]]]:
    """
    增强的XML解析函数，支持动态触发信号

    功能：
    1. 保留 <think>...</think> 块（它们应该正常返回给用户）
    2. 仅在解析 function_calls 时临时移除 think 块，防止 think 内容干扰 XML 解析
    3. 查找触发信号的最后一次出现
    4. 从最后一个触发信号开始解析 function_calls

    Args:
        xml_string: 包含函数调用的XML字符串
        trigger_signal: 触发信号字符串

    Returns:
        解析出的函数调用列表，每个调用包含 name 和 args 字段
        如果解析失败则返回 None
    """
    logger.debug(f"🔧 Improved parser starting processing, input length: {len(xml_string) if xml_string else 0}")
    logger.debug(f"🔧 Using trigger signal: {trigger_signal[:20]}...")

    if not xml_string or trigger_signal not in xml_string:
        logger.debug(f"🔧 Input is empty or doesn't contain trigger signal")
        return None

    # 临时移除think块以便解析
    cleaned_content = remove_think_blocks(xml_string)
    logger.debug(f"🔧 Content length after temporarily removing think blocks: {len(cleaned_content)}")

    # 查找所有触发信号位置
    signal_positions = []
    start_pos = 0
    while True:
        pos = cleaned_content.find(trigger_signal, start_pos)
        if pos == -1:
            break
        signal_positions.append(pos)
        start_pos = pos + 1

    if not signal_positions:
        logger.debug(f"🔧 No trigger signal found in cleaned content")
        return None

    logger.debug(f"🔧 Found {len(signal_positions)} trigger signal positions: {signal_positions}")

    # 从最后一个触发信号开始查找有效的 function_calls
    chosen_signal_index = None
    chosen_signal_pos = None
    calls_content_match = None

    for idx in range(len(signal_positions) - 1, -1, -1):
        pos = signal_positions[idx]
        sub = cleaned_content[pos:]
        m = re.search(r"<function_calls>([\s\S]*?)</function_calls>", sub)
        if m:
            chosen_signal_index = idx
            chosen_signal_pos = pos
            calls_content_match = m
            logger.debug(f"🔧 Using trigger signal index {idx} at pos {pos}; content preview: {repr(sub[:100])}")
            break

    if calls_content_match is None:
        logger.debug(f"🔧 No function_calls tag found after any trigger signal (triggers={len(signal_positions)})")
        return None

    calls_xml = calls_content_match.group(0)
    calls_content = calls_content_match.group(1)
    logger.debug(f"🔧 function_calls content: {repr(calls_content)}")

    def _coerce_value(v: str):
        """尝试将字符串转换为JSON值"""
        try:
            return json.loads(v)
        except Exception:
            return v

    def _parse_args_json_payload(payload: str) -> Dict[str, Any]:
        """解析args_json中的JSON payload"""
        if payload is None:
            return {}
        s = payload.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
            return {"raw_arguments": parsed}
        except Exception:
            return {"raw_arguments": s}

    def _extract_cdata_text(raw: str) -> str:
        """从CDATA块中提取文本"""
        if raw is None:
            return ""
        if "<![CDATA[" not in raw:
            return raw
        parts = re.findall(r"<!\[CDATA\[(.*?)\]\]>", raw, flags=re.DOTALL)
        return "".join(parts) if parts else raw

    results: List[Dict[str, Any]] = []

    # 主要路径：严格的XML解析（要求模型输出有效的XML）
    try:
        root = ET.fromstring(calls_xml)
        for i, fc in enumerate(root.findall("function_call")):
            tool_el = fc.find("tool")
            name = (tool_el.text or "").strip() if tool_el is not None else ""
            if not name:
                logger.debug(f"🔧 No tool tag found in function_call #{i+1}")
                continue

            args: Dict[str, Any] = {}

            # 优先使用 args_json
            args_json_el = fc.find("args_json")
            if args_json_el is not None:
                args = _parse_args_json_payload(args_json_el.text or "")
            else:
                # 遗留回退：<args><k>json</k></args>
                args_el = fc.find("args")
                if args_el is not None:
                    for child in list(args_el):
                        args[child.tag] = _coerce_value(child.text or "")

            result = {"name": name, "args": args}
            results.append(result)
            logger.debug(f"🔧 Added tool call: {result}")

        logger.debug(f"🔧 Final parsing result (XML): {results}")
        return results if results else None
    except Exception as e:
        logger.debug(f"🔧 XML library parse failed, falling back to regex parser: {type(e).__name__}: {e}")

    # 回退路径：正则表达式解析（对格式错误的XML更宽容）
    call_blocks = re.findall(r"<function_call>([\s\S]*?)</function_call>", calls_content)
    logger.debug(f"🔧 Found {len(call_blocks)} function_call blocks")

    for i, block in enumerate(call_blocks):
        logger.debug(f"🔧 Processing function_call #{i+1}: {repr(block)}")

        tool_match = re.search(r"<tool>(.*?)</tool>", block)
        if not tool_match:
            logger.debug(f"🔧 No tool tag found in block #{i+1}")
            continue

        name = tool_match.group(1).strip()
        args: Dict[str, Any] = {}

        # 优先使用 args_json
        args_json_match = re.search(r"<args_json>([\s\S]*?)</args_json>", block)
        if args_json_match:
            raw_payload = args_json_match.group(1)
            payload = _extract_cdata_text(raw_payload)
            args = _parse_args_json_payload(payload)
        else:
            # 遗留回退
            args_block_match = re.search(r"<args>([\s\S]*?)</args>", block)
            if args_block_match:
                args_content_inner = args_block_match.group(1)
                arg_matches = re.findall(r"<([^\s>/]+)>([\s\S]*?)</\1>", args_content_inner)
                for k, v in arg_matches:
                    args[k] = _coerce_value(v)

        result = {"name": name, "args": args}
        results.append(result)
        logger.debug(f"🔧 Added tool call: {result}")

    logger.debug(f"🔧 Final parsing result (regex): {results}")
    return results if results else None
