# ecode

一个基于 LLM 的 AI 编程助手，能够通过自然语言直接读取、搜索、编辑文件，以及执行终端命令。提供 REST API 后端和 CLI 终端两种交互方式。

## 特性

- **对话式编程** -- 用自然语言描述需求，AI 自动完成代码编写和修改
- **文件操作** -- 查看、搜索（正则）、编辑、创建文件和目录
- **命令执行** -- 在项目目录中运行 shell 命令
- **安全审批机制** -- 危险操作（编辑、写入、执行命令）需用户确认后才执行
- **三层上下文压缩** -- 自动管理长对话上下文，保持在 token 限制内
- **会话管理** -- 支持多会话切换，MySQL 持久化存储
- **项目上下文** -- 通过项目根目录的 `ecode.md` 文件注入自定义编码规范
- **多模型支持** -- 通过 `config.yaml` 一键切换 LLM 提供商
- **SSE 流式响应** -- 实时返回 AI 文本、工具调用和结果

## 快速开始

### 环境要求

- Python 3.10+
- MySQL 服务
- 至少一个 LLM 提供商的 API Key

### 安装

```bash
pip install -r requirements.txt
```

可选：以开发模式安装 CLI 命令

```bash
pip install -e .
```

### 配置

1. 创建 `.env` 文件，填入 API Key 和数据库密码：

```env
ALI=<阿里云 API Key>
MIMO=<小米 MiMo API Key>
SHANG_TANG=<商汤 API Key>
ECODE_DB_PASSWORD=<MySQL 密码>
```

2. 编辑 `config.yaml`，配置数据库连接和 LLM 模型：

```yaml
backend:
  url: "http://127.0.0.1:8000"

database:
  host: "127.0.0.1"
  port: 3306
  user: "root"
  password_env: "ECODE_DB_PASSWORD"
  database: "ecode"

llm:
  active: "shang_tang"  # 可选: shang_tang / ali / mimo
  configs:
    shang_tang:
      provider: "sensenova"
      model: "deepseek-v4-flash"
      # ...
```

### 启动

**后端 API 服务：**

```bash
python main.py
```

服务启动于 `0.0.0.0:8000`。

**CLI 终端：**

```bash
python ecode_cli.py
# 或
ecode  # pip install -e . 后可用
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/sessions` | 列出所有会话 |
| `/switch` | 切换会话 |
| `/new` | 创建新会话 |
| `/delete` | 删除会话 |
| `/history` | 查看当前会话历史 |
| `/clear` | 清屏 |
| `/exit` | 退出 |

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat/stream` | POST | 发送消息，SSE 流式返回 |
| `/api/chat/resume` | POST | 恢复被中断的对话（审批通过/拒绝） |
| `/api/sessions` | GET | 列出所有会话 |
| `/api/sessions/{thread_id}` | DELETE | 删除会话 |
| `/api/sessions/{thread_id}/history` | GET | 获取会话消息历史 |

## 项目结构

```
├── main.py                 # FastAPI 入口，API 路由，SSE 流式响应
├── agent.py                # LangGraph Agent 核心：状态定义、节点逻辑、图构建
├── model.py                # LLM 工厂：读取 config.yaml，创建 ChatOpenAI 实例
├── schemas.py              # Pydantic 请求/响应模型
├── session.py              # MySQL 会话管理 + LangGraph 检查点存储
├── context_manager.py      # 三层上下文压缩（微压缩、自动压缩、手动压缩）
├── project_context.py      # 加载并缓存 ecode.md 项目上下文
├── config.yaml             # 主配置文件
├── requirements.txt        # Python 依赖
├── pyproject.toml          # 构建配置，CLI 入口注册
├── ecode_cli.py            # CLI 入口脚本
├── tools/
│   ├── __init__.py         # 工具注册、安全/危险分类、路径解析
│   ├── file_tools.py       # 文件操作工具
│   ├── search_tools.py     # 搜索工具（正则搜索、目录列表）
│   ├── command_tools.py    # 命令执行工具
│   ├── context_tools.py    # 上下文压缩工具
│   └── tool_index.py       # 工具索引表
├── cli/
│   ├── chat.py             # CLI 主循环：输入处理、流处理、审批流
│   ├── display.py          # Rich 终端显示格式化
│   ├── interactions.py     # 交互组件：补全、选择菜单、确认对话框
│   └── approval.py         # 审批详情面板
└── utils/
    └── sse.py              # SSE 事件格式化工具
```

## 工具安全分类

| 类型 | 工具 | 说明 |
|------|------|------|
| 安全（自动执行） | `view_file` `search_code` `list_files` `compact` `get_tool_details` | 只读操作，无需用户确认 |
| 危险（需审批） | `edit_file` `write_file` `create_file` `create_directory` `run_command` | 写入操作，需用户确认 |

## 自定义项目上下文

在项目根目录创建 `ecode.md` 文件，写入编码规范、目录结构说明等信息。Agent 会自动读取并将其作为上下文的一部分。文件上限 8000 字符。

## 架构文档

详细的架构设计文档见 [ARCHITECTURE.md](ARCHITECTURE.md)。
