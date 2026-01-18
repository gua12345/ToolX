# ToolX

**为任何 LLM 赋予函数调用能力**

ToolX 是一个轻量级的 LLM 函数调用代理服务，通过动态路由和智能提示注入，让任何不支持原生函数调用的 LLM 都能使用工具。

## 特性

- **动态路由**: 通过 URL 路径灵活配置目标服务，无需修改代码
- **函数调用注入**: 自动将 OpenAI 格式的 tools 转换为提示词注入到消息中
- **智能解析**: 从 LLM 响应中解析 XML 格式的函数调用，转换为标准 OpenAI 格式
- **流式支持**: 完整支持流式和非流式响应
- **错误重试**: 可选的函数调用解析错误自动重试机制
- **消息预处理**: 自动转换 tool 消息和 assistant.tool_calls 为上游兼容格式
- **提示词过滤**: 灵活的规则引擎，处理可能与函数调用冲突的提示词内容
- **模块化架构**: 清晰的代码结构，易于维护和扩展

## 项目结构

```
ToolX/
├── .github/
│   └── workflows/
│       └── docker-build.yaml   # Docker 构建 CI/CD 配置
├── src/
│   ├── __init__.py
│   ├── api/                    # API 路由和处理器
│   │   ├── __init__.py
│   │   ├── routes.py          # 路由定义
│   │   ├── handlers.py        # 请求处理逻辑
│   │   └── models.py          # API 数据模型
│   ├── config/                 # 配置模块
│   │   ├── __init__.py
│   │   ├── loader.py          # 配置加载器
│   │   └── models.py          # 配置数据模型
│   ├── core/                   # 核心功能
│   │   ├── __init__.py
│   │   ├── token_counter.py   # Token 计数器
│   │   └── trigger_signal.py  # 触发信号生成器
│   ├── function_calling/       # 函数调用模块
│   │   ├── __init__.py
│   │   ├── models.py          # 函数调用数据模型
│   │   ├── formatter.py       # 格式化器
│   │   ├── parser.py          # XML 解析器
│   │   ├── prompt.py          # 提示词生成
│   │   └── retry.py           # 错误重试逻辑
│   └── middleware/             # 中间件
│       ├── __init__.py
│       ├── message_processor.py  # 消息预处理
│       └── prompt_filter.py   # 提示词过滤器
├── doc/                        # 文档目录
│   └── PROMPT_FILTER_GUIDE.md # 提示词过滤器使用指南
├── .gitattributes              # Git 属性配置
├── .gitignore                  # Git 忽略文件配置
├── Dockerfile                  # Docker 镜像构建文件
├── main.py                     # 应用入口
├── config.example.yaml         # 配置文件示例
├── prompt_filter_rules.json    # 提示词过滤规则配置
├── prompt_filter_rules.example.json  # 提示词过滤规则示例
├── requirements.txt            # 项目依赖
└── README.md                   # 项目文档
```

## 快速开始

### 方式一：直接运行

#### 1. 安装依赖

```bash
pip install -r requirements.txt
```

#### 2. 配置

将 `config.example.yaml` 复制为 `config.yaml` 并修改配置：

```bash
cp config.example.yaml config.yaml
```

编辑 `config.yaml`：

```yaml
server:
  port: 8000
  host: "0.0.0.0"
  timeout: 180

dynamic_routing_keys:
  - "mykey"      # 你的认证密钥
  - "proxy"
  - "route1"

features:
  enable_function_calling: true
  log_level: "INFO"
  convert_developer_to_system: true
  enable_fc_error_retry: false
  fc_error_retry_max_attempts: 3
```

#### 3. 启动服务

```bash
python main.py
```

或使用 uvicorn：

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 方式二：Docker 部署

#### 1. 使用预构建镜像（推荐）

从 GitHub Container Registry 拉取最新镜像：

```bash
docker pull ghcr.io/gua12345/toolx:latest
```

#### 2. 准备配置文件

创建 `config.yaml` 配置文件（参考 `config.example.yaml`）：

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml 设置你的配置
```

#### 3. 运行容器

```bash
docker run -d \
  --name toolx \
  -p 8000:8000 \
  -v $(pwd)/config.yaml:/app/config.yaml \
  ghcr.io/gua12345/toolx:latest
```

#### 4. 使用 Docker Compose（推荐）

创建 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  toolx:
    image: ghcr.io/gua12345/toolx:latest
    container_name: toolx
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/app/config.yaml
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
```

启动服务：

```bash
docker-compose up -d
```

查看日志：

```bash
docker-compose logs -f
```

停止服务：

```bash
docker-compose down
```

#### 5. 本地构建镜像

如果你想自己构建镜像：

```bash
# 构建镜像
docker build -t toolx:local .

# 运行容器
docker run -d \
  --name toolx \
  -p 8000:8000 \
  -v $(pwd)/config.yaml:/app/config.yaml \
  toolx:local
```

#### Docker 部署注意事项

- **配置文件挂载**：必须将 `config.yaml` 挂载到容器的 `/app/config.yaml`
- **端口映射**：默认端口为 8000，可以根据需要修改
- **健康检查**：镜像内置健康检查，确保服务正常运行
- **日志查看**：使用 `docker logs toolx` 查看容器日志
- **多架构支持**：镜像支持 `linux/amd64` 和 `linux/arm64` 架构

## 使用方法

### 动态路由格式

```
/{path_key}/{protocol}/{base_url}/{remaining_path}
```

- `path_key`: 认证密钥（从 `dynamic_routing_keys` 配置中验证）
- `protocol`: `http` 或 `https`
- `base_url`: 目标服务的基础 URL（如 `api.openai.com/v1`）
- `remaining_path`: API 端点路径（如 `/chat/completions`）

### 示例请求

假设你的配置中有密钥 `mykey`，目标是 OpenAI API：

```bash
curl -X POST http://localhost:8000/mykey/https/api.openai.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_OPENAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [
      {"role": "user", "content": "What is the weather in Beijing?"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_weather",
          "description": "Get the current weather in a location",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {
                "type": "string",
                "description": "The city name"
              }
            },
            "required": ["location"]
          }
        }
      }
    ]
  }'
```

### 工作流程

1. **请求到达**: 客户端发送带有 tools 的请求到 ToolX
2. **路由验证**: 验证 path_key 和 Authorization header
3. **消息预处理**: 转换 tool 消息和 assistant.tool_calls 为文本格式
4. **提示注入**: 将 tools 转换为提示词，注入到消息开头
5. **上游请求**: 移除 tools 字段，发送到目标 LLM
6. **响应解析**: 从 LLM 响应中解析 XML 格式的函数调用
7. **格式转换**: 将解析结果转换为标准 OpenAI tool_calls 格式
8. **返回客户端**: 返回标准格式的响应

## 函数调用格式

LLM 需要按以下 XML 格式输出函数调用：

```xml
<Function_XXXX_Start/>
<function_calls>
  <function_call>
    <tool>get_weather</tool>
    <args_json><![CDATA[{"location": "Beijing"}]]></args_json>
  </function_call>
</function_calls>
```

ToolX 会自动将其转换为：

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": null,
      "tool_calls": [{
        "id": "call_xxx",
        "type": "function",
        "function": {
          "name": "get_weather",
          "arguments": "{\"location\": \"Beijing\"}"
        }
      }]
    },
    "finish_reason": "tool_calls"
  }]
}
```

## 配置说明

### 服务器配置

- `server.port`: 服务器监听端口（默认 8000）
- `server.host`: 服务器监听地址（默认 0.0.0.0）
- `server.timeout`: 请求超时时间，单位秒（默认 180）

### 动态路由密钥

- `dynamic_routing_keys`: 认证密钥列表，用于 URL 路径验证

### 功能配置

- `features.enable_function_calling`: 是否启用函数调用功能（默认 true）
- `features.log_level`: 日志级别（DEBUG/INFO/WARNING/ERROR/CRITICAL/DISABLED）
- `features.convert_developer_to_system`: 是否将 developer 角色转换为 system（默认 true）
- `features.enable_fc_error_retry`: 是否启用函数调用解析错误自动重试（默认 false）
- `features.fc_error_retry_max_attempts`: 函数调用错误重试最大次数（默认 3）

### 自定义提示模板

可以通过 `features.prompt_template` 自定义函数调用提示词模板：

```yaml
features:
  prompt_template: |
    You have access to the following tools:
    {tools_list}

    When you need to use tools, start with:
    {trigger_signal}
```

必须包含 `{tools_list}` 和 `{trigger_signal}` 占位符。

## 提示词过滤器

提示词过滤器用于处理可能与函数调用提示词冲突的内容，例如 IDE 注入的系统提示词、工具使用指南等。

### 配置文件

- `prompt_filter_rules.json`: 实际使用的过滤规则配置文件（已包含在仓库中）
- `prompt_filter_rules.example.json`: 过滤规则示例文件

### 快速启用

过滤器默认启用，使用仓库中的 `prompt_filter_rules.json` 配置。如需自定义规则，直接编辑该文件即可。

### 详细文档

完整的使用指南、规则类型说明和示例配置，请参考：[提示词过滤器使用指南](doc/PROMPT_FILTER_GUIDE.md)

## 架构说明

### 新架构特点

1. **去除上游服务配置**: 不再需要预配置上游服务，完全通过 URL 动态指定
2. **去除客户端认证**: 简化认证逻辑，只保留动态路由密钥验证
3. **保留函数调用核心**: 完整保留函数调用注入、解析、转换功能
4. **模块化设计**: 清晰的模块划分，易于维护和扩展

### 核心模块

- **config**: 配置加载和验证
- **core**: Token 计数、触发信号生成等核心功能
- **function_calling**: 函数调用的完整生命周期（提示生成、解析、格式化、重试）
- **middleware**: 消息预处理和验证
- **api**: 路由定义和请求处理

## 开发

### 代码风格

项目遵循 PEP 8 规范，所有代码包含中文注释。

## 许可证

GPL-3.0-or-later

## 贡献

欢迎提交 Issue 和 Pull Request！

## 致谢

本项目基于原 Toolify 项目重构，保留了核心函数调用功能，简化了架构设计。
