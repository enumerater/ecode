<div align="center">

# ecode

**基于 LangGraph 的 AI 编程智能体**

在终端中用自然语言操作你的项目 —— 读写文件、执行命令、管理 Git，全程自主完成

[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![LangGraph](https://img.shields.io/badge/LangGraph-Powered-orange?logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Server-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)

[English](#english) | 中文

</div>

---

## 为什么选择 ecode？

ecode 是一个开源的终端 AI 编程智能体，类似于 Claude Code / Cursor / Aider，但完全可控 —— 你可以接入任何 OpenAI 兼容的 LLM（DeepSeek、通义千问、MiMo、商汤、OpenAI 等），数据不离开你的本地环境。

<!-- 如果有终端录屏 GIF，放在这里 -->
<!-- ![ecode demo](./docs/demo.gif) -->

---

## 功能特性

<table>
<tr>
<td width="50%">

### 文件与代码
- 读取、编辑、写入、创建文件和目录
- 正则搜索 + glob 过滤，快速定位代码
- 基于 diff 的精准编辑，不重写整个文件

### 命令与 Git
- 执行任意 Shell 命令，支持超时控制
- Git 全流程：status / diff / log / blame / commit
- 交互式命令自动应答

### 智能上下文
- 5 层上下文压缩，长对话不丢上下文
- Token 实时估算，自动触发压缩
- KV Cache 优化，减少重复计算

</td>
<td width="50%">

### 权限与安全
- 4 种权限模式：default / plan / auto_approve / yolo
- 细粒度规则引擎，glob + 正则匹配
- 逐工具审批，diff 预览后再确认

### 协作与记忆
- 跨会话记忆系统，持久化用户偏好
- 项目上下文文件（`.ecode.md`）
- LLM 自动提取对话中的关键信息

### 扩展性
- Hook 系统：工具调用前后自定义脚本
- 子智能体：生成只读子代理聚焦分析
- SSE 流式 API，接入自定义前端

</td>
</tr>
</table>

---

## 快速开始

### 安装

```bash
git clone https://github.com/your-username/ecode.git
cd ecode
pip install -e .
```

### 首次运行

```bash
cd your-project
ecode
```

首次运行自动弹出初始化向导，选择 LLM 提供商、输入 API Key，即刻开始。

### 手动配置

<details>
<summary>点击展开配置方式</summary>

**方式一：config.yaml**

```yaml
# .ecode/config.yaml
llm:
  active: "deepseek"
  configs:
    deepseek:
      provider: openai
      model: deepseek-chat
      api_key_env: DEEPSEEK
      base_url: https://api.deepseek.com/v1
      temperature: 0
      streaming: true
      stream_usage: true
```

**方式二：环境变量**

```bash
export ECODE_API_KEY="your-api-key"
export ECODE_MODEL="deepseek-chat"
export ECODE_BASE_URL="https://api.deepseek.com/v1"
```

</details>

---

## 使用方法

### CLI 交互

```bash
ecode
```

直接用自然语言对话：

```
> 帮我看看 src/ 下有哪些文件
> 把 main.py 里的 print 改成 logging
> 运行 pytest 并告诉我结果
> 分析一下这个项目的架构，写到 docs/ 里
```

### 斜杠命令

| 命令 | 说明 |
|:-----|:-----|
| `/help` | 显示帮助信息 |
| `/init` | 重新运行初始化向导 |
| `/plan` | 切换计划模式（`Shift+Tab` 快捷键） |
| `/mode` | 切换权限模式 |
| `/sessions` | 查看历史会话列表 |
| `/switch <id>` | 切换到指定会话 |
| `/new` | 创建新会话 |
| `/storage` | 切换存储后端（内存 / MySQL） |
| `/clear` | 清屏 |
| `/exit` | 退出 |

### 权限模式

| 模式 | safe 工具 | 文件编辑 | Shell 命令 |
|:-----|:---------|:---------|:-----------|
| `default` | 自动 | 需确认 | 需确认 |
| `plan` | 自动 | 禁止 | 禁止 |
| `auto_approve` | 自动 | 自动 | 需确认 |
| `yolo` | 自动 | 自动 | 自动 |

### API 服务

```bash
python main.py
```

| 端点 | 方法 | 说明 |
|:-----|:-----|:-----|
| `/api/chat/stream` | `POST` | SSE 流式对话 |
| `/api/chat/resume` | `POST` | 恢复中断的对话 |
| `/api/sessions` | `GET` | 会话列表 |
| `/api/sessions/{id}` | `DELETE` | 删除会话 |
| `/api/sessions/{id}/history` | `GET` | 会话历史 |

---

## 支持的 LLM

ecode 通过 OpenAI 兼容接口连接 LLM，接入任何兼容服务商只需改配置：

| 提供商 | 推荐模型 | `base_url` |
|:-------|:---------|:-----------|
| **DeepSeek** | `deepseek-chat` / `deepseek-coder` | `https://api.deepseek.com/v1` |
| **通义千问** | `qwen-plus` / `qwen-max` | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| **小米 MiMo** | `mimo-v2.5-pro` | `https://token-plan-cn.xiaomimimo.com/v1` |
| **商汤日日新** | `deepseek-v4-flash` | `https://token.sensenova.cn/v1` |
| **OpenAI** | `gpt-4o` / `gpt-4o-mini` | `https://api.openai.com/v1` |
| **任意兼容服务** | — | 对应 API 地址 |

---

## 项目结构

```
ecode/
├── agent.py                    # 核心 LangGraph 状态机
├── main.py                     # FastAPI 服务入口
├── model.py                    # LLM 工厂，配置加载
├── session.py                  # 会话管理（内存 / MySQL）
├── context_manager.py          # 5 层上下文压缩
├── settings.py                 # 多层级设置合并
├── project_context.py          # .ecode.md 项目上下文
├── schemas.py                  # Pydantic 数据模型
├── cli/                        # CLI 终端界面
│   ├── chat.py                 #   主循环、斜杠命令、审批
│   ├── display.py              #   Rich 渲染引擎
│   ├── approval.py             #   审批详情（diff / 预览）
│   ├── interactions.py         #   输入、菜单、粘贴处理
│   └── live_status.py          #   实时状态指示器
├── tools/                      # 工具集（27 个工具）
│   ├── file_tools.py           #   文件操作
│   ├── search_tools.py         #   搜索与浏览
│   ├── command_tools.py        #   Shell 命令
│   ├── git_tools.py            #   Git 操作
│   ├── agent_tool.py           #   子智能体
│   ├── memory_tools.py         #   记忆存取
│   ├── task_plan_tools.py      #   任务规划
│   ├── tool_executor.py        #   并行执行引擎
│   └── tool_index.py           #   工具索引表
├── permissions/                # 权限系统
│   ├── modes.py                #   4 种权限模式
│   └── rules.py                #   规则引擎
├── hooks/                      # Hook 系统
│   ├── executor.py             #   Hook 执行引擎
│   └── types.py                #   事件类型定义
├── memory/                     # 记忆系统
│   ├── loader.py               #   记忆加载
│   ├── writer.py               #   记忆写入
│   └── extractor.py            #   LLM 记忆提取
├── tasks/                      # 后台任务管理
├── context/                    # Token 计数
└── utils/                      # 工具函数
```

---

## 配置参考

<details>
<summary>config.yaml 完整配置</summary>

```yaml
# API 服务
backend:
  url: "http://127.0.0.1:8000"
  timeout: 30000

# 数据库（可选，持久化会话）
database:
  host: localhost
  port: 3306
  user: root
  password_env: ECODE_DB_PASSWORD
  database: ecode

# LLM 模型
llm:
  active: "model-name"
  configs:
    model-name:
      provider: openai
      model: deepseek-chat
      api_key_env: API_KEY
      base_url: https://...
      temperature: 0
      streaming: true
      stream_usage: true
```

</details>

<details>
<summary>settings.json 权限与 Hook</summary>

```json
{
  "permissions": [
    {"tool": "run_command", "pattern": "git commit*", "behavior": "allow"},
    {"tool": "edit_file", "pattern": "*.test.py", "behavior": "allow"}
  ],
  "hooks": [
    {
      "event": "PreToolUse",
      "type": "shell",
      "command": "echo 'Calling ${ECODE_TOOL_NAME}'",
      "matcher": "run_command"
    }
  ]
}
```

</details>

<details>
<summary>项目上下文 .ecode.md</summary>

在项目根目录创建 `.ecode.md`，ecode 会将其加载为系统提示的一部分（最多 8000 字符），用于告知 AI 项目背景、编码规范等：

```markdown
# 项目说明

这是一个 Python Web 项目，使用 FastAPI + SQLAlchemy。

## 编码规范
- 使用 type hints
- 函数命名用 snake_case
- 测试文件放在 tests/ 目录
```

</details>

---

## 架构文档

详细的系统架构、模块设计、数据流分析请参阅 [docs/architecture.md](docs/architecture.md)。

---

## 开发

```bash
# 安装
pip install -e .

# 运行 CLI
ecode

# 运行 API 服务
python main.py
```

---

## License

[MIT](LICENSE)

---

<div id="english"></div>

<details>
<summary><strong>English</strong></summary>

**ecode** is an open-source AI coding agent powered by LangGraph. Interact with your codebase through natural language in the terminal — read, search, edit files, run commands, manage Git, all autonomously.

**Features:** File operations, shell execution, Git integration, 5-layer context compression, 4 permission modes, plan mode, task planning, sub-agents, background tasks, cross-session memory, hook system, and SSE streaming API.

**Quick Start:**
```bash
git clone https://github.com/your-username/ecode.git
cd ecode
pip install -e .
cd your-project && ecode
```

Supports any OpenAI-compatible LLM: DeepSeek, Qwen, MiMo, SenseNova, OpenAI, and more.

</details>
