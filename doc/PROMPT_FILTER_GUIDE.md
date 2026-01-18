# 提示词过滤器使用指南

## 概述

提示词过滤器是 ToolX 的一个灵活功能，用于处理可能与函数调用提示词冲突的内容。通过 JSON 配置文件，你可以轻松定义过滤规则，无需修改代码。

## 配置文件说明

### 文件位置和作用

- **`prompt_filter_rules.json`**: 实际使用的过滤规则配置文件
  - 该文件已包含在仓库中，存放已验证可用的过滤规则
  - 可以直接编辑此文件来自定义规则
  - 修改后重启服务即可生效

- **`prompt_filter_rules.example.json`**: 过滤规则示例文件
  - 提供更多规则示例和参考
  - 可以从中复制规则到 `prompt_filter_rules.json`

### 为什么 prompt_filter_rules.json 包含在仓库中？

与 `config.yaml`（需要从 `config.example.yaml` 复制）不同，`prompt_filter_rules.json` 直接包含在仓库中，原因如下：

1. **开箱即用**: 提供已验证的默认规则，用户无需额外配置即可使用
2. **规则共享**: 团队成员可以共享和同步已验证的过滤规则

如果你需要使用完全自定义的规则且不想提交到仓库，可以将 `prompt_filter_rules.json` 添加到 `.gitignore` 中。

## 快速开始

### 1. 使用默认规则

过滤器默认启用，仓库中已包含 `prompt_filter_rules.json` 文件，其中存放了已验证可用的过滤规则。克隆仓库后即可直接使用。

### 2. 自定义规则

如需自定义规则，直接编辑 `prompt_filter_rules.json` 文件：

```bash
# 编辑配置文件
vim prompt_filter_rules.json

# 或参考示例文件
cat prompt_filter_rules.example.json
```

### 3. 重启服务

重启 ToolX 服务以加载新的配置：

```bash
python main.py
```

## 配置文件结构

```json
{
  "enabled": true,
  "description": "配置文件描述",
  "rules": [
    {
      "name": "规则名称",
      "description": "规则描述",
      "enabled": true,
      "type": "规则类型",
      "target_roles": ["system", "user"],
      "condition": {
        "type": "匹配类型",
        "patterns": ["关键词1", "关键词2"]
      },
      "action": {
        "replacement": "替换内容"
      }
    }
  ]
}
```

## 规则类型

### 1. remove_system_message

完全删除匹配的消息。

**示例**：删除来自 Roo 的系统提示词

```json
{
  "name": "移除 Roo 系统提示词",
  "enabled": true,
  "type": "remove_system_message",
  "target_roles": ["system"],
  "condition": {
    "type": "contains",
    "patterns": ["You are Roo", "TOOL USE"],
    "case_sensitive": false,
    "match_any": true
  }
}
```

### 2. replace_in_content

替换消息中的特定内容。

**示例**：替换函数调用标签

```json
{
  "name": "替换函数调用关键词",
  "enabled": true,
  "type": "replace_in_content",
  "target_roles": ["system", "user"],
  "condition": {
    "type": "contains",
    "patterns": ["<function_calls>"],
    "case_sensitive": true
  },
  "action": {
    "replacements": [
      {
        "from": "<function_calls>",
        "to": "[function_calls]"
      }
    ]
  }
}
```

### 3. remove_pattern

使用正则表达式删除匹配的内容。

**示例**：删除工具使用指南部分

```json
{
  "name": "移除工具使用指南",
  "enabled": true,
  "type": "remove_pattern",
  "target_roles": ["system"],
  "condition": {
    "type": "regex",
    "pattern": "====\\s*TOOL USE.*?====",
    "flags": "DOTALL"
  },
  "action": {
    "replacement": ""
  }
}
```

### 4. truncate_message

截断过长的消息。

**示例**：截断超过 5000 字符的系统消息

```json
{
  "name": "截断过长的系统消息",
  "enabled": true,
  "type": "truncate_message",
  "target_roles": ["system"],
  "condition": {
    "type": "length_exceeds",
    "threshold": 5000
  },
  "action": {
    "max_length": 3000,
    "append_notice": "\n\n[消息已被截断]"
  }
}
```

## 匹配条件类型

### 1. contains

检查内容是否包含指定的关键词。

**参数**：
- `patterns`: 关键词列表
- `case_sensitive`: 是否区分大小写（默认 false）
- `match_any`: 匹配任意一个（true）或全部（false）

### 2. starts_with

检查内容是否以指定文本开头。

**参数**：
- `patterns`: 文本列表
- `case_sensitive`: 是否区分大小写（默认 false）

### 3. regex

使用正则表达式匹配。

**参数**：
- `pattern`: 正则表达式
- `flags`: 正则标志（IGNORECASE, DOTALL, MULTILINE）

### 4. length_exceeds

检查内容长度是否超过阈值。

**参数**：
- `threshold`: 长度阈值

## 常见使用场景

### 场景 1：移除 IDE 注入的系统提示词

许多 AI 编程助手（如 Roo、Cursor）会在请求中注入自己的系统提示词，这可能与 ToolX 的函数调用提示词冲突。

**解决方案**：

```json
{
  "name": "移除 IDE 系统提示词",
  "enabled": true,
  "type": "remove_system_message",
  "target_roles": ["system"],
  "condition": {
    "type": "contains",
    "patterns": ["You are Roo", "You are Cursor"],
    "match_any": true
  }
}
```

### 场景 2：清理工具使用指南

某些工具会在系统消息中添加详细的工具使用指南，这些内容可能干扰函数调用。

**解决方案**：

```json
{
  "name": "移除工具使用指南",
  "enabled": true,
  "type": "remove_pattern",
  "target_roles": ["system"],
  "condition": {
    "type": "regex",
    "pattern": "====.*?TOOL USE.*?====",
    "flags": "DOTALL"
  },
  "action": {
    "replacement": ""
  }
}
```

### 场景 3：避免标签冲突

如果用户消息中包含与函数调用格式相同的标签，可能导致解析错误。

**解决方案**：

```json
{
  "name": "转义函数调用标签",
  "enabled": true,
  "type": "replace_in_content",
  "target_roles": ["user"],
  "condition": {
    "type": "contains",
    "patterns": ["<function_calls>", "</function_calls>"]
  },
  "action": {
    "replacements": [
      {"from": "<function_calls>", "to": "&lt;function_calls&gt;"},
      {"from": "</function_calls>", "to": "&lt;/function_calls&gt;"}
    ]
  }
}
```

## 调试技巧

### 1. 查看过滤日志

将日志级别设置为 `DEBUG`，可以看到详细的过滤过程：

```yaml
# config.yaml
logging:
  level: DEBUG
```

### 2. 测试规则

在启用规则前，可以先设置 `enabled: false`，然后逐个启用测试。

### 3. 查看原始请求

在日志中查找 `📋 原始请求体` 标记，可以看到完整的原始请求内容。

## 注意事项

1. **配置文件位置**：`prompt_filter_rules.json` 必须放在项目根目录
2. **默认配置**：仓库中已包含该文件，存放已验证的规则，可直接使用
3. **JSON 格式**：确保 JSON 格式正确，否则过滤器会被禁用
4. **规则顺序**：规则按照配置文件中的顺序执行
5. **性能影响**：过多的正则表达式规则可能影响性能
6. **版本控制**：该文件已纳入版本控制，修改会被 Git 追踪
7. **备份配置**：修改配置前建议备份原文件

## 故障排除

### 问题：过滤器没有生效

**检查**：
1. 确认 `prompt_filter_rules.json` 文件存在（仓库中已包含）
2. 确认配置文件中 `enabled: true`
3. 检查日志中是否有加载错误
4. 确认规则的 `enabled: true`
5. 重启服务以加载最新配置

### 问题：消息被错误删除

**解决**：
1. 检查匹配条件是否过于宽泛
2. 使用 `match_any: false` 要求匹配所有关键词
3. 增加更具体的关键词

### 问题：正则表达式不工作

**解决**：
1. 检查正则表达式语法
2. 确认使用了正确的 flags（如 DOTALL）
3. 在在线工具中测试正则表达式

## 示例配置

完整的示例配置请参考 `prompt_filter_rules.example.json` 文件。

## 贡献

如果你发现了新的需要过滤的提示词模式，欢迎提交 Issue 或 Pull Request！
