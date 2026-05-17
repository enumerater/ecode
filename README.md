# ecode

一个基于 LLM 的 AI 编程助手，能够通过自然语言直接读取、搜索、编辑文件，以及执行终端命令。提供 REST API 后端和 CLI 终端两种交互方式。

## 特性

- **对话式编程** -- 用自然语言描述需求，AI 自动完成代码编写和修改
- **文件操作** -- 查看、搜索（正则）、编辑、创建文件和目录
- **命令执行** -- 在项目目录中运行 shell 命令
- **安全审批机制** -- 危险操作（编辑、写入、执行命令）需用户确认后才执行
- **三层上下文压缩** -- 自动管理长对话上下文，保持在 token 限制内
- **会话管理** -- 支持多会话切换，内存/MySQL 双存储后端
- **项目上下文** -- 通过项目根目录的 `ecode.md` 文件注入自定义编码规范
- **多模型支持** -- 通过 `config.yaml` 一键切换 LLM 提供商
- **SSE 流式响应** -- 实时返回 AI 文本、工具调用和结果

## 快速开始

### 环境要求

- Python 3.10+
- 至少一个 LLM 提供商的 API Key

### 安装

```bash
git clone <repo-url> ecode
cd ecode
pip install -e .
```

### 配置（首次运行自动引导）

直接启动 CLI，首次运行会自动进入交互式配置：

```bash
ecode
```

引导流程会让你选择 LLM 提供商（DeepSeek / 阿里通义 / OpenAI / 自定义）并输入 API Key，自动生成 `.env` 和 `config.yaml`。

也可以手动配置：

```bash
# 方式一：环境变量（最简）
export ECODE_API_KEY="your-api-key"
export ECODE_MODEL="deepseek-chat"
export ECODE_BASE_URL="https://api.deepseek.com/v1"

# 方式二：config.yaml（参考 config.yaml.example）
cp config.yaml.example config.yaml
# 编辑 config.yaml，填入 api_key_env 和对应环境变量
```

### 启动

**CLI 终端：**

```bash
ecode
# 或
python -m cli.chat
```

**后端 API 服务（可选）：**

```bash
python main.py
```

服务启动于 `0.0.0.0:8000`。

## CLI 命令

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/init` | 重新初始化配置（LLM 提供商设置） |
| `/sessions` | 列出所有会话 |
| `/switch` | 切换会话 |
| `/new` | 创建新会话 |
| `/delete` | 删除会话 |
| `/history` | 查看当前会话历史 |
| `/mode` | 切换权限模式 |
| `/plan` | 切换计划模式 |
| `/storage` | 切换存储后端 (memory/mysql) |
| `/clear` | 清屏 |
| `/exit` | 退出 |

## 存储后端

默认使用**内存存储**，无需任何数据库配置。会话数据在进程内保存，重启后丢失。

如需持久化，可切换到 **MySQL**：

1. 安装并启动 MySQL
2. 在 `config.yaml` 中配置 database 部分（参考 `config.yaml.example`）
3. 设置环境变量 `ECODE_DB_PASSWORD`
4. 运行 `/storage` 命令切换到 mysql

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
├── model.py                # LLM 工厂：config.yaml 或环境变量，延迟初始化
├── session.py              # 双存储后端：内存/MySQL，运行时可切换
├── schemas.py              # Pydantic 请求/响应模型
├── context_manager.py      # 三层上下文压缩（微压缩、自动压缩、手动压缩）
├── project_context.py      # 加载并缓存 ecode.md 项目上下文
├── config.yaml.example     # 配置模板
├── tools/
│   ├── file_tools.py       # 文件操作工具
│   ├── search_tools.py     # 搜索工具（正则搜索、目录列表）
│   ├── command_tools.py    # 命令执行工具
│   ├── git_tools.py        # Git 工具
│   └── tool_index.py       # 工具索引表
├── cli/
│   ├── chat.py             # CLI 主循环：输入处理、流处理、审批流、/init 引导
│   ├── display.py          # Rich 终端显示格式化
│   └── interactions.py     # 交互组件：补全、选择菜单、确认对话框
└── memory/                 # 记忆系统：文件级持久化
```

## 自定义项目上下文

在项目根目录创建 `ecode.md` 文件，写入编码规范、目录结构说明等信息。Agent 会自动读取并将其作为上下文的一部分。文件上限 8000 字符。

## 架构文档

详细的架构设计文档见 [ecode-architecture-complete.md](docs/ecode-architecture-complete.md)。
