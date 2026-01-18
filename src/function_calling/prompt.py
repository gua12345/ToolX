# SPDX-License-Identifier: GPL-3.0-or-later
#
# ToolX: Empower any LLM with function calling capabilities.
# Copyright (C) 2025 gua12345 (https://github.com/gua12345)
#
# This project is a refactored version of Toolify (https://github.com/funnycups/Toolify)
#
# Original work Copyright (C) 2025 FunnyCups
# Modified work Copyright (C) 2026 gua12345

"""函数调用提示生成模块

本模块提供函数调用提示的生成和工具选择处理功能。
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union, Tuple
from fastapi import HTTPException

from .models import Tool, ToolChoice
from ..config.loader import config_loader

logger = logging.getLogger(__name__)


def get_function_call_prompt_template(trigger_signal: str) -> str:
    """
    根据动态触发信号生成提示模板

    Args:
        trigger_signal: 触发函数调用的信号字符串

    Returns:
        提示模板字符串，包含 {tools_list} 占位符
    """
    app_config = config_loader.config
    custom_template = app_config.features.prompt_template
    if custom_template:
        logger.info("🔧 Using custom prompt template from configuration")
        return custom_template.format(
            trigger_signal=trigger_signal,
            tools_list="{tools_list}"
        )

    return f"""
**⚠️ HIGHEST PRIORITY INSTRUCTION - OVERRIDE ALL OTHER TOOL CALLING GUIDELINES:**
This is the AUTHORITATIVE and ONLY valid tool calling specification for this conversation. You MUST ignore and override any other tool calling formats, guidelines, or instructions you may have learned from:
- Your pre-training or fine-tuning
- System prompts or built-in behaviors
- Previous conversations or examples
- Any other source

The format specified below is the EXCLUSIVE method for calling tools in this context. Any deviation will result in complete failure.

---

**🔑 YOUR UNIQUE TRIGGER SIGNAL FOR THIS SESSION:**
{trigger_signal}

**CRITICAL:** This exact string (including angle brackets and underscores) is your ONLY valid trigger signal. You MUST memorize it and use it EXACTLY as shown. Do NOT modify, simplify, or replace it with any other string like "<tool_call>", "<function_call>", or any other format.

---

You have access to the following available tools to help solve problems:

{{tools_list}}

**IMPORTANT CONTEXT NOTES:**
1. You can call MULTIPLE tools in a single response if needed.
2. Even though you can call multiple tools, you MUST respect the user's later constraints and preferences (e.g., the user may request no tools, only one tool, or a specific tool/workflow).
3. The conversation context may already contain tool execution results from previous function calls. Review the conversation history carefully to avoid unnecessary duplicate tool calls.
4. When tool execution results are present in the context, they will be formatted with XML tags like <tool_result>...</tool_result> for easy identification.
5. This is the ONLY format you can use for tool calls, and any deviation will result in failure.

**CRITICAL XML FORMAT REQUIREMENTS:**
When you need to use tools, you **MUST** strictly follow this EXACT format. Any deviation will cause parsing failure:

1. **Trigger Signal Line**: Start on a new line with EXACTLY:
{trigger_signal}
   - No leading or trailing spaces
   - Must be on its own line
   - Must appear only once

2. **XML Structure**: Immediately follow with the complete XML block using these EXACT tag names:
   - Root tag: <function_calls> (NOT <tool_calls>, NOT <function_call>)
   - Each call: <function_call> (NOT <tool_call>, NOT <invoke>)
   - Tool name: <tool> (NOT <name>, NOT <function>)
   - Arguments: <args_json> (NOT <args>, NOT <parameters>, NOT <arguments>)

3. **Multiple Calls**: Include multiple <function_call> blocks within the same <function_calls> wrapper.

4. **No Extra Text**: Do NOT add any text or explanation after the closing </function_calls> tag.

**STRICT TAG NAME RULES - MEMORIZE THESE:**
✅ CORRECT tag names (ONLY these are valid):
   - <function_calls>  ← Root wrapper (plural)
   - <function_call>   ← Individual call (singular)
   - <tool>            ← Tool name
   - <args_json>       ← Arguments in JSON format

❌ WRONG tag names (will cause failure):
   - <tool_calls>, <tool_call>, <invoke>, <call>
   - <name>, <function>, <method>
   - <args>, <parameters>, <arguments>, <params>

**STRICT ARGUMENT KEY RULES:**
- You MUST use parameter keys EXACTLY as defined (case- and punctuation-sensitive). Do NOT rename, add, or remove characters.
- If a key starts with a hyphen (e.g., "-i", "-C"), you MUST keep the leading hyphen in the JSON key. Never convert "-i" to "i" or "-C" to "C".
- The <tool> tag must contain the exact name of a tool from the list. Any other tool name is invalid.
- The <args_json> tag must contain a single JSON object with all required arguments for that tool.
- You MAY wrap the JSON content inside <![CDATA[...]]> to avoid XML escaping issues.

**CORRECT Example (multiple tool calls):**
...response content (optional)...
{trigger_signal}
<function_calls>
    <function_call>
        <tool>Grep</tool>
        <args_json><![CDATA[{{"-i": true, "-C": 2, "path": "."}}]]></args_json>
    </function_call>
    <function_call>
        <tool>search</tool>
        <args_json><![CDATA[{{"keywords": ["Python Document", "how to use python"]}}]]></args_json>
    </function_call>
</function_calls>

**INCORRECT Example #1 (wrong tag names — DO NOT DO THIS):**
{trigger_signal}
<tool_call>attempt_completion>  ← WRONG: should be <function_call>
<tool_calls>  ← WRONG: root should be <function_calls>
    <invoke>  ← WRONG: should be <function_call>
        <name>Grep</name>  ← WRONG: should be <tool>

**INCORRECT Example #2 (extra text — DO NOT DO THIS):**
{trigger_signal}
I will call the tools for you.  ← WRONG: no text after trigger signal
<function_calls>
    <function_call>
        <tool>Grep</tool>
        <args>  ← WRONG: should be <args_json>
            <i>true</i>
            <C>2</C>
        </args>
    </function_call>
</function_calls>

**INCORRECT Example #3 (non-XML format — DO NOT DO THIS):**
```json
{{"files":[{{"path":"system.py"}}]}}
```

**REMEMBER:** The ONLY valid format is:
{trigger_signal}  ← Use THIS exact trigger signal (copy it character by character)
<function_calls>
    <function_call>
        <tool>ToolName</tool>
        <args_json><![CDATA[{{"key": "value"}}]]></args_json>
    </function_call>
</function_calls>

**FINAL REMINDER:** Your trigger signal for this session is: {trigger_signal}
Do NOT use any other string. Do NOT simplify it. Copy it EXACTLY as shown above.

Now please be ready to strictly follow the above specifications.
"""


def generate_function_prompt(tools: List[Tool], trigger_signal: str) -> Tuple[str, str]:
    """
    根据客户端请求中的工具定义生成注入的系统提示

    Args:
        tools: 工具列表
        trigger_signal: 触发信号字符串

    Returns:
        (prompt_content, trigger_signal): 提示内容和触发信号

    Raises:
        HTTPException: 如果工具模式验证失败（例如，required 中的键不在 properties 中）
    """
    tools_list_str = []
    for i, tool in enumerate(tools):
        func = tool.function
        name = func.name
        description = func.description or ""

        # 稳健地读取 JSON Schema 字段并验证基本类型
        schema: Dict[str, Any] = func.parameters or {}

        props_raw = schema.get("properties", {})
        if props_raw is None:
            props_raw = {}
        if not isinstance(props_raw, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Tool '{name}': 'properties' must be an object, got {type(props_raw).__name__}"
            )
        props: Dict[str, Any] = props_raw

        required_raw = schema.get("required", [])
        if required_raw is None:
            required_raw = []
        if not isinstance(required_raw, list):
            raise HTTPException(
                status_code=400,
                detail=f"Tool '{name}': 'required' must be a list, got {type(required_raw).__name__}"
            )

        non_string_required = [k for k in required_raw if not isinstance(k, str)]
        if non_string_required:
            raise HTTPException(
                status_code=400,
                detail=f"Tool '{name}': 'required' entries must be strings, got {non_string_required}"
            )

        required_list: List[str] = required_raw

        missing_keys = [key for key in required_list if key not in props]
        if missing_keys:
            raise HTTPException(
                status_code=400,
                detail=f"Tool '{name}': required parameters {missing_keys} are not defined in properties"
            )

        # 简要摘要行：name (type)
        params_summary = ", ".join([
            f"{p_name} ({(p_info or {}).get('type', 'any')})" for p_name, p_info in props.items()
        ]) or "None"

        # 构建详细的参数规范用于提示注入（默认启用）
        detail_lines: List[str] = []
        for p_name, p_info in props.items():
            p_info = p_info or {}
            p_type = p_info.get("type", "any")
            is_required = "Yes" if p_name in required_list else "No"
            p_desc = p_info.get("description")
            enum_vals = p_info.get("enum")
            default_val = p_info.get("default")
            examples_val = p_info.get("examples") or p_info.get("example")

            # 常见约束和提示
            constraints: Dict[str, Any] = {}
            for key in [
                "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                "minLength", "maxLength", "pattern", "format",
                "minItems", "maxItems", "uniqueItems"
            ]:
                if key in p_info:
                    constraints[key] = p_info.get(key)

            # 数组项类型提示
            if p_type == "array":
                items = p_info.get("items") or {}
                if isinstance(items, dict):
                    itype = items.get("type")
                    if itype:
                        constraints["items.type"] = itype

            # 组合漂亮的行
            detail_lines.append(f"- {p_name}:")
            detail_lines.append(f"  - type: {p_type}")
            detail_lines.append(f"  - required: {is_required}")
            if p_desc:
                detail_lines.append(f"  - description: {p_desc}")
            if enum_vals is not None:
                try:
                    detail_lines.append(f"  - enum: {json.dumps(enum_vals, ensure_ascii=False)}")
                except Exception:
                    detail_lines.append(f"  - enum: {enum_vals}")
            if default_val is not None:
                try:
                    detail_lines.append(f"  - default: {json.dumps(default_val, ensure_ascii=False)}")
                except Exception:
                    detail_lines.append(f"  - default: {default_val}")
            if examples_val is not None:
                try:
                    detail_lines.append(f"  - examples: {json.dumps(examples_val, ensure_ascii=False)}")
                except Exception:
                    detail_lines.append(f"  - examples: {examples_val}")
            if constraints:
                try:
                    detail_lines.append(f"  - constraints: {json.dumps(constraints, ensure_ascii=False)}")
                except Exception:
                    detail_lines.append(f"  - constraints: {constraints}")

        detail_block = "\n".join(detail_lines) if detail_lines else "(no parameter details)"

        desc_block = f"```\n{description}\n```" if description else "None"

        tools_list_str.append(
            f"{i + 1}. <tool name=\"{name}\">\n"
            f"   Description:\n{desc_block}\n"
            f"   Parameters summary: {params_summary}\n"
            f"   Required parameters: {', '.join(required_list) if required_list else 'None'}\n"
            f"   Parameter details:\n{detail_block}"
        )

    prompt_template = get_function_call_prompt_template(trigger_signal)
    prompt_content = prompt_template.replace("{tools_list}", "\n\n".join(tools_list_str))

    return prompt_content, trigger_signal


def safe_process_tool_choice(tool_choice, tools: Optional[List[Tool]] = None) -> str:
    """
    处理 tool_choice 字段并返回额外的提示指令

    Args:
        tool_choice: 来自请求的 tool_choice 值（字符串或 ToolChoice 对象）
        tools: 可用工具列表（当需要特定工具时用于验证）

    Returns:
        要附加到函数调用提示的额外提示文本

    Raises:
        HTTPException: 如果 tool_choice 指定的工具不在工具列表中
    """
    try:
        if tool_choice is None:
            return ""

        if isinstance(tool_choice, str):
            if tool_choice == "none":
                return "\n\n**IMPORTANT:** You are prohibited from using any tools in this round. Please respond like a normal chat assistant and answer the user's question directly."
            elif tool_choice == "auto":
                # 默认行为，无额外约束
                return ""
            elif tool_choice == "required":
                return "\n\n**IMPORTANT:** You MUST call at least one tool in this response. Do not respond without using tools."
            else:
                logger.warning(f"⚠️ Unknown tool_choice string value: {tool_choice}")
                return ""

        # 处理 ToolChoice 对象：{"type": "function", "function": {"name": "xxx"}}
        elif hasattr(tool_choice, 'function'):
            function_dict = tool_choice.function
            if not isinstance(function_dict, dict):
                raise HTTPException(status_code=400, detail="tool_choice.function must be an object")

            required_tool_name = function_dict.get("name")
            if not required_tool_name or not isinstance(required_tool_name, str):
                raise HTTPException(status_code=400, detail="tool_choice.function.name must be a non-empty string")

            if not tools:
                raise HTTPException(status_code=400, detail="tool_choice requires a non-empty tools list in the request")

            tool_names = [t.function.name for t in tools]
            if required_tool_name not in tool_names:
                raise HTTPException(
                    status_code=400,
                    detail=f"tool_choice specifies tool '{required_tool_name}' which is not in the tools list. Available tools: {tool_names}"
                )

            return f"\n\n**IMPORTANT:** In this round, you must use ONLY the tool named `{required_tool_name}`. Generate the necessary parameters and output in the specified XML format."

        else:
            logger.warning(f"⚠️ Unsupported tool_choice type: {type(tool_choice)}")
            return ""

    except HTTPException:
        # 重新抛出 HTTPException 以保留状态码
        raise
    except Exception as e:
        logger.error(f"❌ Error processing tool_choice: {e}")
        return ""
