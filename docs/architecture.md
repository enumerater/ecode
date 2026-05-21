# ecode 架构文档

本文档详细描述 ecode 的系统架构、核心模块、数据流和设计决策。

## 目录

- [系统概览](#系统概览)
- [入口与启动流程](#入口与启动流程)
- [核心智能体（agent.py）](#核心智能体agentpy)
- [工具系统](#工具系统)
- [工具执行引擎](#工具执行引擎)
- [上下文管理](#上下文管理)
- [权限系统](#权限系统)
- [会话与存储](#会话与存储)
- [记忆系统](#记忆系统)
- [Hook 系统](#hook-系统)
- [CLI 终端界面](#cli-终端界面)
- [API 服务](#api-服务)
- [配置体系](#配置体系)
- [关键数据流](#关键数据流)

---

## 系统概览

ecode 是一个基于 LangGraph 的 AI 编程智能体。核心思路是将 LLM 包装为一个具有工具调用能力的自主代理，通过状态机驱动的对话循环，让 LLM 能够读写文件、执行命令、操作 Git，并在终端中以流式方式呈现结果。

```
                        ┌──────────────┐
                        │   用户输入    │
                        └──────┬───────┘
                               │
                    ┌──────────▼──────────┐
                    │     CLI / API       │
                    │  (chat.py / main.py)│
                    └──────────┬──────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Agent StateGraph  │
                    │    (agent.py)       │
                    │                     │
                    │  think ──► execute  │
                    │    ▲         │      │
                    │    └── error ◄┘      │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼─────┐  ┌──────▼──────┐  ┌──────▼──────┐
     │  Tools (27)  │  │ Permissions │  │  Context    │
     │  file/git/   │  │   rules     │  │  Manager    │
     │  cmd/search  │  │   modes     │  │  (5-layer)  │
     └──────────────┘  └─────────────┘  └─────────────┘
```

---

## 入口与启动流程

ecode 有三个入口点，最终都汇聚到同一个智能体循环：

### 1. CLI 入口（主入口）

```
ecode 命令 → cli/chat.py:main() → start_chat()
```

- 通过 `pyproject.toml` 的 `[project.scripts]` 注册 `ecode` 命令
- `main()` 加载配置、检查是否首次运行（触发 `/init` 向导）
- `start_chat()` 启动交互循环：输入 → 处理流 → 显示结果

### 2. API 入口

```
python main.py → FastAPI 应用
```

- `POST /api/chat/stream` — SSE 流式对话
- `POST /api/chat/resume` — 恢复中断的对话（审批/补充输入）
- `GET /api/sessions` — 会话列表
- `DELETE /api/sessions/{id}` — 删除会话
- `GET /api/sessions/{id}/history` — 会话历史

### 3. 直接脚本入口

```
python ecode_cli.py → cli/chat.py:main()
```

---

## 核心智能体（agent.py）

### LangGraph 状态机

ecode 的核心是一个 LangGraph `StateGraph`，由三个节点组成：

```
START → think → [有工具调用?] → execute_tools → handle_error → [重试?] → think
                     │                                                     │
                     ▼                                                     ▼
                    END                                                    END
```

**节点职责：**

| 节点 | 职责 |
|------|------|
| `think` | 构建系统提示、应用上下文压缩、调用 LLM、解析工具调用 |
| `execute_tools` | 批量执行工具、权限检查、人工审批中断、处理特殊信号 |
| `handle_error` | 检查工具结果错误、重试逻辑（最多 3 次） |

### 状态定义（AgentState）

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]    # 对话消息（带 reducer）
    project_root: str                           # 工作目录
    last_error: str                             # 最近错误信息
    retry_count: int                            # 重试计数
    usage: dict                                 # Token 用量累计
    compact_summary: str                        # 压缩摘要
    compact_at: int                             # 下次压缩的消息索引
    immutable_context: str                      # 缓存的系统提示
    immutable_context_key: str                  # 缓存 key（用于 KV cache 优化）
    permission_mode: str                        # 当前权限模式
    plan_mode: bool                             # 是否处于计划模式
    tasks: list                                 # 任务规划列表
    session_approved: bool                      # 用户是否选择了"会话内全部同意"
```

### think 节点详解

1. **构建不可变系统提示** — 项目上下文（`.ecode.md`）+ 记忆 + 工具索引 + 工作规则
2. **应用上下文压缩** — 三层：micro（每轮）、auto（token 超限）、reactive（API 报错）
3. **注入任务进度** — 如果有进行中的任务，将进度信息加入提示
4. **调用 LLM** — 通过 `ChatOpenAI.bind_tools()` 绑定工具集
5. **错误处理** — prompt-too-long 时触发 reactive compact 后重试

### execute_tools 节点详解

1. **工具调用分批** — 通过 `tool_executor.py` 将工具调用分为并行批和串行批
2. **权限检查** — 每个工具调用前检查权限规则
3. **人工审批** — 危险操作通过 LangGraph `interrupt` 暂停，等待用户确认
4. **特殊信号处理** — compact、计划模式切换、任务更新、用户提问

---

## 工具系统

### 工具分类（27 个工具）

| 分类 | 工具 | 安全性 | 只读 | 可并发 |
|------|------|--------|------|--------|
| **文件操作** | `view_file` | safe | Yes | Yes |
| | `edit_file` | dangerous | No | No |
| | `write_file` | dangerous | No | No |
| | `create_file` | dangerous | No | No |
| | `create_directory` | dangerous | No | No |
| **搜索** | `search_code` | safe | Yes | Yes |
| | `list_files` | safe | Yes | Yes |
| **命令** | `run_command` | dangerous | No | No |
| **Git** | `git_status` | safe | Yes | Yes |
| | `git_diff` | safe | Yes | Yes |
| | `git_log` | safe | Yes | Yes |
| | `git_blame` | safe | Yes | Yes |
| | `git_commit` | dangerous | No | No |
| **上下文** | `compact` | safe | Yes | No |
| **工具元信息** | `get_tool_details` | safe | Yes | Yes |
| **记忆** | `save_memory` | dangerous | No | No |
| | `list_memories` | safe | Yes | Yes |
| **计划** | `enter_plan_mode` | dangerous | No | No |
| | `exit_plan_mode` | dangerous | No | No |
| **子智能体** | `run_agent` | dangerous | No | No |
| **后台任务** | `create_background_task` | dangerous | No | No |
| | `get_task_status` | safe | Yes | Yes |
| | `list_background_tasks` | safe | Yes | Yes |
| | `kill_background_task` | dangerous | No | No |
| **任务规划** | `create_task` | safe | No | No |
| | `update_task` | safe | No | No |
| | `list_tasks` | safe | Yes | Yes |
| **用户交互** | `ask_user_question` | dangerous | No | No |

### 工具注册表（tools/__init__.py）

```python
# 工具集合分类
SAFE      = {view_file, search_code, list_files, git_status, git_diff, ...}
DANGEROUS = {edit_file, write_file, run_command, git_commit, ...}
ALL       = SAFE | DANGEROUS
PLAN      = {view_file, search_code, list_files, git_status, ...}  # 只读子集

# 工具元信息
TOOL_META = {
    "tool_name": {
        "description": "...",
        "is_concurrency_safe": True/False,
        "is_read_only": True/False,
        "is_destructive": True/False,
    }
}
```

---

## 工具执行引擎（tools/tool_executor.py）

灵感来自 Claude Code 的 StreamingToolExecutor，核心思想是将工具调用智能分批以最大化并行度。

### 分批策略

```
输入: [view_file, search_code, edit_file, run_command, git_status]

分批结果:
  Batch 1 (并行): [view_file, search_code]     ← 都是 safe + read_only
  Batch 2 (串行): [edit_file]                   ← dangerous
  Batch 3 (串行): [run_command]                 ← dangerous
  Batch 4 (并行): [git_status]                  ← safe + read_only
```

### 执行流程

1. **分批** — 连续的 safe 工具合并为一个并行批，dangerous 工具各自成为串行批
2. **并行批执行** — `asyncio.gather` + `asyncio.to_thread`（同步工具包装为异步）
3. **串行批执行** — 逐个执行，每个工具调用前进行权限检查
4. **结果截断** — 超过 8000 字符的结果自动截断

---

## 上下文管理（context_manager.py）

ecode 实现了 5 层上下文压缩机制，确保长对话不会因 token 超限而中断。

### 第 1 层：Micro Compact（每轮触发）

- **触发时机**：每轮对话开始时
- **行为**：将 3 轮之前的工具调用结果替换为一行占位符
- **保留**：`view_file` 的内容不压缩（文件内容可能持续被引用）

### 第 2 层：Auto Compact（Token 超限触发）

- **触发时机**：估计 token 数超过 60,000
- **行为**：调用 LLM 对旧消息生成摘要，保留最近 20 条消息
- **特点**：生成的摘要作为 `compact_summary` 注入系统提示

### 第 3 层：Manual Compact（智能体主动触发）

- **触发时机**：智能体调用 `compact` 工具
- **行为**：类似 auto compact，但由智能体判断何时需要

### 第 4 层：Reactive Compact（API 错误触发）

- **触发时机**：LLM API 返回 prompt-too-long 错误
- **行为**：紧急压缩，移除更多历史消息后重试

### 第 5 层：Snip Compact（中间截断）

- **触发时机**：上下文管理器判断需要
- **行为**：保留前 3 条 + 后 10 条消息，移除中间部分

### Token 估算

使用 `tiktoken` 库（`context/token_counter.py`）进行 token 计数，基于 `cl100k_base` 编码。

---

## 权限系统（permissions/）

### 权限模式

| 模式 | safe 工具 | dangerous 工具（文件） | dangerous 工具（命令） |
|------|-----------|----------------------|----------------------|
| `default` | 自动执行 | 需要确认 | 需要确认 |
| `plan` | 自动执行 | 禁止 | 禁止 |
| `auto_approve` | 自动执行 | 自动执行 | 需要确认 |
| `yolo` | 自动执行 | 自动执行 | 自动执行 |

### 规则引擎（permissions/rules.py）

规则按优先级从高到低评估：

```
会话级规则 > 项目级规则 > 本地规则 > 用户级规则 > 模式默认规则
```

**规则结构：**

```json
{
    "tool": "run_command",        // 工具名，支持 glob 匹配
    "pattern": "git commit*",     // 参数模式，支持正则匹配
    "behavior": "allow"           // allow / deny
}
```

**评估逻辑：**

1. 收集所有层级的规则
2. 按优先级排序
3. 第一个匹配的规则生效
4. 无匹配时回退到模式默认行为

---

## 会话与存储（session.py）

### 存储后端

| 后端 | 说明 | 持久化 | 用途 |
|------|------|--------|------|
| `MemorySessionManager` | 进程内字典存储 | 否 | 开发 / 测试 / 单次使用 |
| `MySQLSessionManager` | MySQL 数据库 | 是 | 生产环境 / 多设备同步 |

### StorageState

运行时状态管理器，负责：

- 维护当前活跃的存储后端和 checkpointer
- 提供 `/storage` 命令的运行时切换能力
- 模块级 `__getattr__` 实现向后兼容

### LangGraph Checkpointer

会话状态通过 LangGraph 的 checkpointer 机制持久化：

- `MemorySaver` — 内存后端
- `PyMySQLSaver` — MySQL 后端（通过 `langgraph-checkpoint-mysql`）

---

## 记忆系统（memory/）

### 架构

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  extractor   │     │    loader    │     │    writer    │
│  (LLM 提取)  │────►│  (读取解析)  │◄────│  (写入去重)  │
└──────────────┘     └──────┬───────┘     └──────────────┘
                            │
                   ┌────────▼────────┐
                   │   MEMORY.md     │
                   │  (YAML front-   │
                   │   matter +      │
                   │   markdown)     │
                   └─────────────────┘
```

### 存储位置

| 位置 | 作用域 | 用途 |
|------|--------|------|
| `~/.ecode/MEMORY.md` | 用户级 | 用户偏好、通用知识 |
| `.ecode/MEMORY.md` | 项目级 | 项目特定上下文 |

### 记忆格式

```markdown
---
name: user-preference-theme
type: user
date: 2025-01-15
---

用户偏好使用深色主题，终端使用 PowerShell。
```

### 限制

- 最大 200 条记忆
- 单个 MEMORY.md 最大 25KB
- 自动去重（基于 name 字段）

---

## Hook 系统（hooks/）

### 事件类型

| 事件 | 触发时机 |
|------|---------|
| `PreToolUse` | 工具调用前 |
| `PostToolUse` | 工具调用成功后 |
| `PostToolUseFailure` | 工具调用失败后 |
| `SessionStart` | 会话开始 |
| `SessionEnd` | 会话结束 |
| `Stop` | 智能体停止 |
| `UserPromptSubmit` | 用户提交输入 |

### Hook 类型

| 类型 | 说明 |
|------|------|
| `shell` | 执行 Shell 命令，环境变量注入上下文 |
| `prompt` | 注入额外提示到 LLM |
| `callback` | Python 回调函数 |

### 配置示例

```json
{
    "hooks": [
        {
            "event": "PreToolUse",
            "type": "shell",
            "command": "echo 'Calling ${ECODE_TOOL_NAME} with ${ECODE_TOOL_INPUT}'",
            "matcher": "run_command"
        },
        {
            "event": "PostToolUse",
            "type": "shell",
            "command": "npm run lint",
            "matcher": "edit_file"
        }
    ]
}
```

---

## CLI 终端界面（cli/）

### 模块职责

| 文件 | 职责 |
|------|------|
| `chat.py` | 主循环：输入 → 处理流 → 审批 → 显示结果。斜杠命令注册与分发。 |
| `display.py` | Rich 渲染：欢迎横幅、工具调用面板、结果摘要、用量统计、任务列表 |
| `approval.py` | 审批详情视图：edit_file 显示 diff，write_file 显示预览，run_command 显示命令 |
| `interactions.py` | prompt_toolkit 输入：历史记录、Tab 补全、粘贴芯片、单选/多选菜单、确认对话框 |
| `live_status.py` | QuerySpinner：thinking / tool_use / responding 状态指示器 + 计时 |

### 交互特性

- **粘贴芯片** — 多行粘贴自动折叠为一个可展开的芯片，避免刷屏
- **Ctrl+C 补充输入** — 智能体执行中按 Ctrl+C 可以追加指令而不是中断
- **Shift+Tab 计划模式** — 快捷键切换计划模式
- **Tab 补全** — 斜杠命令自动补全
- **审批详情** — 不同工具显示不同的审批视图（diff / 预览 / 命令）

---

## API 服务（main.py）

### 端点

```
POST /api/chat/stream
  Body: ChatRequest { message, project_root, thread_id?, permission_mode? }
  Response: SSE stream (text/event-stream)

POST /api/chat/resume
  Body: ResumeRequest { thread_id, project_root, decision?, extra_input? }
  Response: SSE stream

GET /api/sessions
  Response: Session[]

DELETE /api/sessions/{session_id}
  Response: 204

GET /api/sessions/{session_id}/history
  Response: Message[]
```

### SSE 事件类型

| 事件 | 数据 |
|------|------|
| `text` | LLM 文本输出（流式 token） |
| `tool_call` | 工具调用请求 |
| `tool_result` | 工具执行结果 |
| `usage` | Token 用量统计 |
| `interrupt` | 需要人工审批 |
| `error` | 错误信息 |
| `done` | 对话结束 |

---

## 配置体系

### 配置层级

```
优先级从高到低：

1. 环境变量 (ECODE_API_KEY, ECODE_MODEL, ECODE_BASE_URL)
2. .ecode/config.yaml (项目级 LLM / 数据库配置)
3. .ecode/settings.json (项目级权限 / Hook 规则)
4. ~/.ecode/settings.json (用户级权限 / Hook 规则)
5. 模式默认规则 (permissions/modes.py)
```

### 目录结构

```
.ecode/                    # 项目级配置目录（gitignore）
├── .env                   # API Key 等敏感信息
├── config.yaml            # LLM / 数据库配置
├── settings.json          # 权限 / Hook 规则
├── MEMORY.md              # 项目级记忆
└── plan.md                # 计划模式输出

~/.ecode/                  # 用户级配置目录
├── settings.json          # 用户级权限 / Hook 规则
└── MEMORY.md              # 用户级记忆

.ecode.md                  # 项目上下文文件（项目根目录）
```

---

## 关键数据流

### 一次完整的工具调用流程

```
用户输入: "把 main.py 的 print 改成 logging"
    │
    ▼
[think 节点]
    ├── 加载系统提示（项目上下文 + 记忆 + 工具索引）
    ├── 检查是否需要上下文压缩
    ├── 调用 LLM
    └── LLM 返回: tool_call(view_file, {path: "main.py"})
    │
    ▼
[execute_tools 节点]
    ├── 分批: [view_file] → 并行批（safe）
    ├── 权限检查: view_file → safe → 自动执行
    ├── 执行: view_file("main.py") → 返回文件内容
    └── 结果注入消息
    │
    ▼
[handle_error 节点]
    └── 无错误 → 继续
    │
    ▼
[think 节点]
    ├── LLM 分析文件内容
    └── LLM 返回: tool_call(edit_file, {old: "print(...)", new: "logging.info(...)"})
    │
    ▼
[execute_tools 节点]
    ├── 分批: [edit_file] → 串行批（dangerous）
    ├── 权限检查: edit_file → default 模式 → 需要确认
    ├── interrupt() → 暂停，显示 diff 预览
    ├── 用户确认: "y"
    └── 执行: edit_file(...) → 返回结果
    │
    ▼
[think 节点]
    └── LLM 生成确认文本: "已将 main.py 中的 print 替换为 logging.info"
    │
    ▼
输出: "已将 main.py 中的 print 替换为 logging.info"
```

### 上下文压缩触发流程

```
对话进行中...
    │
    ▼
[micro_compact] 每轮自动触发
    └── 替换 3 轮前的工具结果为占位符
    │
    ▼
[token 估算 > 60,000?]
    ├── 否 → 继续
    └── 是 → [auto_compact]
              ├── 调用 LLM 生成摘要
              ├── 保留最近 20 条消息
              └── 注入 compact_summary 到系统提示
    │
    ▼
[API 返回 prompt-too-long?]
    └── 是 → [reactive_compact]
              ├── 紧急压缩
              └── 重试 LLM 调用
```
