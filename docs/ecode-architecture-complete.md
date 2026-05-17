# ecode 项目架构完整文档

> 生成日期：2026-05-16  
> 项目版本：1.0.0  
> 技术栈：Python 3.10+ / LangGraph / LangChain / Rich

---

## 目录

1. [项目概述](#一项目概述)
2. [目录结构](#二目录结构)
3. [核心工作流（agent.py）](#三核心工作流agentpy)
4. [工具系统（tools/）](#四工具系统tools)
5. [权限系统（permissions/）](#五权限系统permissions)
6. [记忆系统（memory/）](#六记忆系统memory)
7. [上下文管理（context_manager.py）](#七上下文管理context_managerpy)
8. [会话管理（session.py）](#八会话管理sessionpy)
9. [CLI 终端界面（cli/）](#九cli-终端界面cli)
10. [Hook 系统（hooks/）](#十hook-系统hooks)
11. [后台任务（tasks/）](#十一后台任务tasks)
12. [模型配置（model.py + config.yaml）](#十二模型配置modelpy--configyaml)
13. [配置与入口](#十三配置与入口)
14. [数据流全景](#十四数据流全景)

---

## 一、项目概述

**ecode** 是一个基于 **LangGraph** 构建的 AI 编码助手，核心能力是让 LLM 通过工具直接操作项目文件系统。它采用**有状态图工作流**架构，支持：

| 特性 | 说明 |
|------|------|
| 文件操作 | 查看、编辑、创建、写入文件 |
| 代码搜索 | 正则搜索、文件列表 |
| 命令执行 | 在项目目录中运行 shell 命令 |
| Git 集成 | status / diff / log / commit / blame |
| 记忆系统 | 跨会话持久化知识（用户级 + 项目级） |
| 三层上下文压缩 | 微压缩 → 自动摘要 → 手动压缩 |
| 权限控制 | 4 种模式 + 可编程规则引擎 |
| Hook 系统 | 生命周期钩子（PreToolUse / PostToolUse 等） |
| 后台任务 | 异步执行长时间运行的命令 |
| 子 Agent | 派生只读子 agent 执行聚焦分析 |
| Plan 模式 | 先分析规划，再执行修改 |
| 审批流程 | 危险操作需要用户确认 |
| 多模型支持 | 通过 config.yaml 切换 LLM 后端 |

---

## 二、目录结构

```
ecode/
├── agent.py                  # 核心：LangGraph 状态图定义 + 工作流编排
├── main.py                   # FastAPI 服务入口（SSE 流式输出）
├── model.py                  # LLM 模型初始化
├── schemas.py                # Pydantic 数据模型
├── session.py                # 会话管理器 + Checkpointer
├── context_manager.py        # 三层上下文压缩引擎
├── project_context.py        # 项目上下文（ecode.md）加载
├── settings.py               # 全局设置加载
├── ecode_cli.py              # CLI 入口脚本
├── config.yaml               # 模型/数据库/后端配置
├── pyproject.toml            # 项目元数据
│
├── cli/                      # 终端交互界面
│   ├── chat.py               # 主聊天循环
│   ├── display.py            # Rich 显示组件
│   ├── approval.py           # 审批详情展示
│   ├── interactions.py       # 交互组件（菜单/输入/确认）
│   ├── live_status.py        # Spinner 动画
│   ├── config.py             # CLI 配置加载
│   └── widgets/              # 预留：自定义组件
│
├── tools/                    # 工具系统
│   ├── __init__.py           # 工具注册 + 元数据 + 路径安全
│   ├── file_tools.py         # 文件操作工具（view/edit/write/create）
│   ├── search_tools.py       # 搜索工具（search_code/list_files）
│   ├── command_tools.py      # 命令执行工具（run_command）
│   ├── context_tools.py      # 上下文工具（compact）
│   ├── tool_index.py         # 工具索引表 + get_tool_details
│   ├── tool_executor.py      # 并行工具执行器
│   ├── git_tools.py          # Git 工具集
│   ├── memory_tools.py       # 记忆工具（save_memory/list_memories）
│   ├── plan_tools.py         # Plan 模式工具
│   ├── agent_tool.py         # 子 Agent 工具
│   └── task_tools.py         # 后台任务工具
│
├── permissions/              # 权限系统
│   ├── __init__.py           # 权限检查入口
│   ├── modes.py              # 权限模式定义
│   └── rules.py              # 权限规则引擎
│
├── memory/                   # 记忆系统
│   ├── __init__.py           # 记忆系统入口
│   ├── loader.py             # 记忆加载器（解析 MEMORY.md）
│   ├── writer.py             # 记忆写入器（保存/列出）
│   └── extractor.py          # 记忆提取器（LLM 自动提取）
│
├── hooks/                    # Hook 系统
│   ├── __init__.py           # Hook 系统入口
│   ├── types.py              # Hook 类型定义
│   └── executor.py           # Hook 执行引擎
│
├── tasks/                    # 后台任务管理器
│   └── __init__.py           # TaskManager + asyncio 实现
│
├── context/                  # 上下文工具
│   └── token_counter.py      # Token 计数器（tiktoken + 启发式回退）
│
├── utils/                    # 工具函数
│   └── sse.py                # SSE 格式化
│
├── test/                     # 测试
│   ├── __init__.py
│   └── stream_test.py        # 流式输出测试
│
├── test_cli.py               # CLI 组件测试
├── test_e2e.py               # 端到端测试
├── debug_stream.py           # 流式调试脚本
├── debug_stream2.py          # 流式调试脚本 v2
├── debug_stream3.py          # 流式调试脚本 v3
│
└── docs/                     # 文档
    ├── memory-architecture.md # 记忆架构文档
    └── ecode-architecture-complete.md  # 本文档
```

---

## 三、核心工作流（agent.py）

### 3.1 状态图架构

ecode 的核心是一个 **LangGraph StateGraph**，包含 3 个节点：

```
                    ┌──────────────┐
                    │    __start__ │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │    think     │  ← LLM 调用节点
                    │  (调用 LLM)  │
                    └──────┬───────┘
                           │
                    ┌──────▼──────────┐
                    │  tool_executor  │  ← 工具执行节点
                    │  (执行工具调用)  │
                    └──────┬──────────┘
                           │
                    ┌──────▼───────┐
                    │   respond    │  ← 回复节点
                    │  (生成回复)   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │   __end__    │
                    └──────────────┘
```

**路由逻辑**：
- `think → tool_executor`：当 LLM 返回工具调用时
- `think → respond`：当 LLM 直接返回文本回复时
- `tool_executor → think`：工具执行完成后，继续下一轮思考
- `respond → __end__`：回复完成后结束

### 3.2 State 定义

```python
class AgentState(TypedDict):
    messages:          Annotated[list, add_messages]  # 对话消息列表
    project_root:      str                            # 项目根目录
    permission_mode:   str                            # 权限模式
    plan_mode:         bool                           # 是否计划模式
    last_error:        str                            # 最近错误信息
    retry_count:       int                            # 重试次数
    usage:             dict                           # token 用量统计
    compact_summary:   str                            # 最近一次压缩的摘要
    compact_at:        int                            # 压缩时的消息数量指针
    immutable_context: str                            # 不可变上下文
```

### 3.3 不可变上下文（KV Cache 优化）

**设计目标**：让 system prompt 在每轮 LLM 调用中保持完全相同的字符串，以命中 LLM provider 的 KV cache。

**构建时机**：每个 session 首次 `think()` 时构建，存入 `state["immutable_context"]`，后续轮次直接复用。

**内容组成**：
```
你是一个 AI 编码助手，可以直接操作项目文件系统。
项目根目录: {project_root}

--- 项目上下文 (ecode.md) ---
{ecode.md 内容}

--- 可用工具一览 ---
{工具索引表}

--- 工作规则 ---
{静态工作规则文本}
```

### 3.4 审批流程（中断机制）

当工具调用需要审批时，LangGraph 的 `NodeInterrupt` 机制被触发：

1. `think` 节点检测到需要审批的工具调用
2. 抛出 `NodeInterrupt`，图执行暂停
3. CLI 层捕获中断，显示审批详情
4. 用户批准/拒绝后，通过 `Command(resume=...)` 恢复执行
5. 图从断点继续运行

---

## 四、工具系统（tools/）

### 4.1 工具注册

所有工具在 `tools/__init__.py` 中统一注册，导出为 `ALL_TOOLS` 列表：

| 工具名 | 类型 | 并发安全 | 只读 | 破坏性 | 文件 |
|--------|------|:--------:|:----:|:------:|------|
| `view_file` | 安全 | ✅ | ✅ | ❌ | `file_tools.py` |
| `edit_file` | 危险 | ❌ | ❌ | ✅ | `file_tools.py` |
| `write_file` | 危险 | ❌ | ❌ | ✅ | `file_tools.py` |
| `create_file` | 危险 | ❌ | ❌ | ✅ | `file_tools.py` |
| `create_directory` | 危险 | ❌ | ❌ | ✅ | `file_tools.py` |
| `search_code` | 安全 | ✅ | ✅ | ❌ | `search_tools.py` |
| `list_files` | 安全 | ✅ | ✅ | ❌ | `search_tools.py` |
| `run_command` | 危险 | ❌ | ❌ | ✅ | `command_tools.py` |
| `compact` | 安全 | ❌ | ✅ | ❌ | `context_tools.py` |
| `get_tool_details` | 安全 | ✅ | ✅ | ❌ | `tool_index.py` |
| `git_status` | 安全 | ✅ | ✅ | ❌ | `git_tools.py` |
| `git_diff` | 安全 | ✅ | ✅ | ❌ | `git_tools.py` |
| `git_log` | 安全 | ✅ | ✅ | ❌ | `git_tools.py` |
| `git_commit` | 危险 | ❌ | ❌ | ✅ | `git_tools.py` |
| `git_blame` | 安全 | ✅ | ✅ | ❌ | `git_tools.py` |
| `save_memory` | 安全 | ❌ | ❌ | ❌ | `memory_tools.py` |
| `list_memories` | 安全 | ✅ | ✅ | ❌ | `memory_tools.py` |
| `enter_plan_mode` | 危险 | ❌ | ❌ | ✅ | `plan_tools.py` |
| `exit_plan_mode` | 危险 | ❌ | ❌ | ✅ | `plan_tools.py` |
| `run_agent` | 危险 | ❌ | ✅ | ✅ | `agent_tool.py` |
| `create_background_task` | 危险 | ❌ | ❌ | ✅ | `task_tools.py` |
| `get_task_status` | 安全 | ✅ | ✅ | ❌ | `task_tools.py` |
| `list_background_tasks` | 安全 | ✅ | ✅ | ❌ | `task_tools.py` |
| `kill_background_task` | 危险 | ❌ | ❌ | ✅ | `task_tools.py` |

### 4.2 工具执行器（tool_executor.py）

**并行执行引擎**，核心逻辑：

1. 接收 LLM 返回的多个工具调用
2. 根据 `TOOL_META` 判断每个工具的并发安全性
3. 并发安全的工具并行执行（`ThreadPoolExecutor`）
4. 非并发安全的工具串行执行
5. 收集所有结果，返回给 LLM

```python
# 执行策略
concurrent_tools = [t for t in tool_calls if is_concurrency_safe(t.name)]
serial_tools    = [t for t in tool_calls if not is_concurrency_safe(t.name)]

# 并发执行
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = {executor.submit(execute_one, tc): tc for tc in concurrent_tools}
    for future in as_completed(futures):
        results.append(future.result())

# 串行执行
for tc in serial_tools:
    results.append(execute_one(tc))
```

### 4.3 路径安全

`tools/__init__.py` 中的 `resolve_safe_path()` 确保所有文件操作不会逃逸项目根目录：

```python
def resolve_safe_path(project_root: str, path: str) -> tuple[Path, str | None]:
    root = Path(project_root).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        return target, f"Path '{path}' escapes project root"
    return target, None
```

### 4.4 子 Agent 系统（agent_tool.py）

子 agent 是一个独立的 LLM 调用链，只能使用只读工具：

- **可用工具**：`view_file`, `search_code`, `list_files`, `git_status`, `git_diff`, `git_log`
- **最大轮次**：5 轮工具调用
- **用途**：代码分析、架构理解、模式搜索

---

## 五、权限系统（permissions/）

### 5.1 权限模式（modes.py）

| 模式 | 值 | 说明 |
|------|-----|------|
| **Default** | `default` | 危险操作需要审批，安全操作自动执行 |
| **AutoApprove** | `auto_approve` | 所有操作自动批准 |
| **Strict** | `strict` | 所有操作都需要审批 |
| **Plan** | `plan` | 只读模式，禁止任何修改操作 |

### 5.2 规则引擎（rules.py）

支持可编程的权限规则，规则来源优先级：

```
session (最高) > project > local > user > mode (最低)
```

每条规则包含：
- `tool`：工具名（支持 glob 模式，如 `edit_*`）
- `pattern`：可选，匹配工具参数的正则表达式
- `behavior`：`allow` / `deny` / `ask`
- `source`：自动填充的规则来源

**评估流程**：
1. 按优先级排序所有规则
2. 遍历规则，第一个匹配的规则决定行为
3. 无匹配时使用模式默认行为

### 5.3 权限检查入口（__init__.py）

```python
def check_permission(tool_name, tool_args, permission_mode, rules):
    # 1. Plan 模式：只读工具放行，修改工具拒绝
    # 2. 规则引擎评估
    # 3. 模式默认行为
    # 返回: allow / deny / ask
```

---

## 六、记忆系统（memory/）

### 6.1 架构

```
┌─────────────────────────────────────────────────────┐
│                    记忆系统                           │
├─────────────────────────────────────────────────────┤
│                                                     │
│  用户级记忆                                         │
│  ~/.ecode/MEMORY.md                                 │
│                                                     │
│  项目级记忆                                         │
│  {project_root}/.ecode/MEMORY.md                    │
│                                                     │
│  记忆格式 (YAML frontmatter + Markdown):            │
│  ---                                                │
│  name: my-memory                                    │
│  type: project                                      │
│  date: 2025-07-17                                   │
│  ---                                                │
│  记忆内容...                                        │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 6.2 三个核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **Loader** | `loader.py` | 解析 MEMORY.md 文件，格式化为 system prompt 文本 |
| **Writer** | `writer.py` | 保存新记忆、更新现有记忆、列出所有记忆 |
| **Extractor** | `extractor.py` | 用 LLM 自动分析对话，提取值得保存的记忆 |

### 6.3 记忆类型

| 类型 | 用途 | 示例 |
|------|------|------|
| `user` | 用户偏好/角色 | "用户是 Python 后端开发者" |
| `feedback` | 用户纠正/确认 | "用户不喜欢自动格式化" |
| `project` | 项目上下文 | "项目截止日期是下周五" |
| `reference` | 外部资源 | "API 文档地址: https://..." |

### 6.4 限制

- 最大行数：200 行
- 最大大小：25KB
- 超出时自动截断，保留最新内容

---

## 七、上下文管理（context_manager.py）

### 7.1 三层压缩架构

```
Layer 1: Micro-Compact (微压缩)
  ├─ 触发：每轮 think() 自动执行
  ├─ 位置：context_manager.py → micro_compact()
  └─ 操作：将 N 轮前的 ToolMessage 替换为一行占位符

Layer 2: Auto-Compact (自动摘要)
  ├─ 触发：token 数超过阈值 (默认 60000)
  ├─ 位置：context_manager.py → auto_compact()
  └─ 操作：调用 LLM 生成摘要，替换旧消息

Layer 3: Manual Compact (手动压缩)
  ├─ 触发：Agent 调用 compact(instruction="...") 工具
  ├─ 位置：tools/context_tools.py + context_manager.py
  └─ 操作：Agent 自主决策，支持自定义指令
```

### 7.2 Micro-Compact 占位符规则

| 工具类型 | 占位符格式 |
|----------|-----------|
| `view_file` | 不替换，保留原内容 |
| `run_command` | `[命令已执行: {cmd[:60]}, 成功/失败]` |
| `search_code` | `[搜索完成: {pattern}, 找到 N 个匹配]` |
| `list_files` | `[文件列表已列出: N 个文件, M 个目录]` |
| `edit_file` | `[文件已修改: {path}]` |
| `write_file` | `[文件已写入: {path}]` |
| `create_file/directory` | `[文件操作完成: {path}]` |
| 其他 | `[工具执行成功/失败]` |

### 7.3 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_TOKENS` | 60000 | 触发 Auto-Compact 的 token 阈值 |
| `KEEP_RECENT_MESSAGES` | 20 | Auto-Compact 保留的最近消息数 |
| `MICRO_COMPACT_AFTER_TURNS` | 3 | 多少轮前的工具结果触发微压缩 |
| `SUMMARY_MAX_CHARS` | 500 | 摘要最大字符数 |
| `MAX_TOOL_RESULT_CHARS` | 8000 | 工具结果最大字符数 |
| `MAX_ECODE_MD_CHARS` | 8000 | ecode.md 最大字符数 |

### 7.4 Token 计数器（context/token_counter.py）

- 优先使用 `tiktoken`（`cl100k_base` 编码器）进行精确估算
- 回退方案：字符启发式（中文字符 ×1.5 + 其他字符 ×0.25）
- 支持消息列表整体估算（含工具调用和工具结果的额外 token）

---

## 八、会话管理（session.py）

### 8.1 组件

| 组件 | 说明 |
|------|------|
| **InMemorySaver** | LangGraph 内置的内存 Checkpointer，每次图执行后自动保存 State 快照 |
| **SessionManager** | 会话元数据管理器，提供 CRUD 接口 |

### 8.2 SessionManager 接口

```python
class SessionManager:
    def create_or_update(thread_id, project_root, title="") -> Session
    def get_session(thread_id) -> Session | None
    def list_sessions() -> list[Session]
    def delete_session(thread_id) -> bool
    def get_history(thread_id) -> list[dict]
```

### 8.3 会话元数据

```python
@dataclass
class Session:
    id: str              # thread_id
    project_root: str    # 项目根目录
    title: str           # 会话标题（自动从首条消息生成）
    created_at: str      # 创建时间
    updated_at: str      # 最后更新时间
    message_count: int   # 消息数
```

### 8.4 持久化

- **Checkpointer**：纯内存存储（`InMemorySaver`），服务重启后丢失
- **SessionManager**：JSON 文件存储（`~/.ecode/sessions.json`），重启后恢复

---

## 九、CLI 终端界面（cli/）

### 9.1 组件架构

```
cli/
├── chat.py           # 主聊天循环 + 流式处理
├── display.py        # Rich 显示组件（格式化输出）
├── approval.py       # 审批详情展示
├── interactions.py   # 交互组件（菜单/输入/确认）
├── live_status.py    # Spinner 动画
└── config.py         # CLI 配置加载
```

### 9.2 聊天循环（chat.py）

```
启动 → 显示 Banner → 进入主循环:
  ├─ 用户输入
  ├─ 斜杠命令处理 (/help, /sessions, /switch, /new, /delete, /history, /clear, /mode, /plan, /exit)
  ├─ 正常对话:
  │   ├─ 构建输入数据 (messages + project_root + permission_mode + plan_mode)
  │   ├─ graph.stream() 流式处理
  │   │   ├─ messages 流: 打字机输出 AI 回复
  │   │   ├─ updates 流: 显示节点执行状态
  │   │   └─ 中断处理: 显示审批详情
  │   └─ 审批处理: 用户批准/拒绝后 resume
  └─ 显示用量统计
```

### 9.3 流式处理

`_process_stream()` 函数处理 `graph.stream()` 的输出：

- **stream_mode=["messages", "updates"]**：同时接收消息流和节点更新流
- **messages 流**：实时打字机效果输出 AI 回复
- **updates 流**：显示节点执行状态、工具调用、中断信息
- **pending_tools 字典**：跟踪正在执行的工具调用，匹配结果

### 9.4 Spinner 动画（live_status.py）

```
状态机:
  THINKING  →  "思考中 {elapsed}s"
  TOOL_USE  →  "执行工具: {tool_name} {elapsed}s"
  RESPONDING → "回复中 {elapsed}s"
```

- 使用 Rich `Status` 组件实现 spinner 动画
- 后台线程每 300ms 更新计时器
- 流式输出时暂停 spinner，输出结束后恢复

### 9.5 交互组件（interactions.py）

| 组件 | 功能 |
|------|------|
| `prompt_input()` | 带历史记录的单行输入 |
| `select_one()` | 单选菜单（↑↓移动，Enter 确认） |
| `select_multi()` | 多选菜单（空格切换，Enter 确认） |
| `confirm()` | y/n 确认对话 |
| `text_input()` | 多行文本输入（END 结束） |
| `setup_readline()` | readline 历史加载/保存 |
| `set_slash_commands()` | Tab 补全斜杠命令 |

### 9.6 审批详情（approval.py）

针对不同工具类型显示不同的审批详情：

- **edit_file**：显示 diff 风格变更（红色 - 旧行，绿色 + 新行）
- **write_file/create_file**：显示路径和内容预览
- **run_command**：显示命令和超时时间
- **git_commit**：显示提交信息

---

## 十、Hook 系统（hooks/）

### 10.1 事件类型

| 事件 | 触发时机 |
|------|----------|
| `PreToolUse` | 工具执行前 |
| `PostToolUse` | 工具执行成功后 |
| `PostToolUseFailure` | 工具执行失败后 |
| `SessionStart` | 会话开始时 |
| `SessionEnd` | 会话结束时 |
| `Stop` | 停止时 |
| `UserPromptSubmit` | 用户提交提示时 |

### 10.2 Hook 类型

| 类型 | 说明 |
|------|------|
| `shell` | 执行 shell 命令，输出期望 JSON 格式 |
| `prompt` | 注入提示文本到 system prompt |
| `callback` | Python 回调函数（预留） |

### 10.3 配置方式

Hook 配置存储在 JSON 文件中：

- **用户级**：`~/.ecode/settings.json`
- **项目级**：`{project_root}/.ecode/settings.json`

```json
{
  "hooks": [
    {
      "event": "PreToolUse",
      "type": "shell",
      "command": "python scripts/validate.py",
      "matcher": "edit_*",
      "timeout": 30,
      "async": false
    }
  ]
}
```

### 10.4 Hook 执行结果

```python
@dataclass
class HookResult:
    success: bool = True
    continue_execution: bool = True   # 是否继续执行
    decision: str = ""                # approve / block / ""
    system_message: str = ""          # 注入的系统消息
    output: str = ""                  # hook 输出
    error: str = ""                   # 错误信息
```

---

## 十一、后台任务（tasks/）

### 11.1 架构

基于 `asyncio` 实现的后台任务管理器：

```python
class TaskManager:
    def create_task(description, command, task_type) -> Task
    def get_task(task_id) -> Task | None
    def list_tasks(status=None) -> list[Task]
    def update_task(task_id, **kwargs) -> Task | None
    def kill_task(task_id) -> bool
    async def run_bash_task(task, cwd)  # 异步执行
    def start_bash_task(task, cwd)      # 启动后台任务
```

### 11.2 任务状态

```
PENDING → RUNNING → COMPLETED
                  → FAILED
                  → KILLED (取消)
```

### 11.3 工具接口

| 工具 | 功能 |
|------|------|
| `create_background_task` | 创建并启动后台任务 |
| `get_task_status` | 查询任务状态和输出 |
| `list_background_tasks` | 列出所有任务 |
| `kill_background_task` | 终止任务 |

---

## 十二、模型配置（model.py + config.yaml）

### 12.1 模型初始化（model.py）

```python
def init_llm(config_path: str = "config.yaml") -> BaseChatModel:
    # 1. 加载 config.yaml
    # 2. 读取 llm.active 确定当前使用的模型
    # 3. 从 llm.configs 获取对应配置
    # 4. 从环境变量读取 API Key
    # 5. 初始化 ChatOpenAI（兼容所有 OpenAI 协议的后端）
    # 6. 绑定工具列表
    return llm.bind_tools(ALL_TOOLS)
```

### 12.2 配置示例（config.yaml）

```yaml
llm:
  active: "shang_tang"  # 切换模型只需改此值
  configs:
    ali:
      provider: openai
      model: qwen-plus
      api_key_env: ALI
      base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
      temperature: 0
      streaming: true
      stream_usage: true

    shang_tang:
      provider: openai
      model: deepseek-v4-flash
      api_key_env: SHANG_TANG
      base_url: https://token.sensenova.cn/v1
      temperature: 0
      streaming: true
      stream_usage: true
```

### 12.3 多模型切换

只需修改 `config.yaml` 中的 `llm.active` 值，无需改代码：

```yaml
llm:
  active: "ali"  # 切换到阿里通义千问
```

---

## 十三、配置与入口

### 13.1 入口点

| 入口 | 文件 | 说明 |
|------|------|------|
| CLI 模式 | `ecode_cli.py` → `cli.chat:main()` | 终端交互界面 |
| API 服务 | `main.py` → FastAPI | SSE 流式 API（预留） |

### 13.2 配置文件

| 文件 | 用途 |
|------|------|
| `config.yaml` | 模型、数据库、后端配置 |
| `pyproject.toml` | 项目元数据、依赖、入口脚本 |
| `~/.ecode/settings.json` | 用户级 Hook 和权限规则 |
| `{project}/.ecode/settings.json` | 项目级 Hook 和权限规则 |
| `~/.ecode/MEMORY.md` | 用户级记忆 |
| `{project}/.ecode/MEMORY.md` | 项目级记忆 |
| `~/.ecode/sessions.json` | 会话元数据持久化 |

### 13.3 依赖

```toml
[project]
dependencies = [
    "rich",          # 终端富文本
    "langchain-core", # LangChain 核心
    "langgraph",     # LangGraph 状态图
]
```

---

## 十四、数据流全景

### 14.1 一次完整对话的数据流

```
用户输入: "查看 README.md 并告诉我内容"
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  CLI (chat.py)                                       │
│  1. 构建 input_data (messages + 元数据)              │
│  2. 调用 graph.stream(input_data, config)            │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  LangGraph StateGraph                                │
│                                                      │
│  ┌─ think ────────────────────────────────────────┐  │
│  │  1. 构建不可变上下文 (首次)                      │  │
│  │  2. 执行 Micro-Compact (Layer 1)                │  │
│  │  3. 检查 token 数，触发 Auto-Compact (Layer 2)  │  │
│  │  4. 调用 LLM                                    │  │
│  │  5. LLM 返回工具调用 → 路由到 tool_executor     │  │
│  │  LLM 返回文本回复 → 路由到 respond              │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ tool_executor ────────────────────────────────┐  │
│  │  1. 权限检查 (permissions/)                     │  │
│  │  2. Hook 检查 (PreToolUse)                      │  │
│  │  3. 需要审批 → 抛出 NodeInterrupt               │  │
│  │  4. 并行/串行执行工具                           │  │
│  │  5. Hook 检查 (PostToolUse)                     │  │
│  │  6. 返回结果 → 路由到 think                     │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ respond ──────────────────────────────────────┐  │
│  │  1. 生成最终回复                                │  │
│  │  2. 记忆提取 (可选)                             │  │
│  │  3. 返回结果 → 结束                             │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  CLI (chat.py)                                       │
│  1. 流式输出 AI 回复 (打字机效果)                    │
│  2. 显示工具调用结果                                 │
│  3. 显示 token 用量                                  │
│  4. 处理中断 (审批流程)                              │
└─────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  持久化                                              │
│  1. InMemorySaver 保存 State 快照                    │
│  2. SessionManager 更新会话元数据                    │
└─────────────────────────────────────────────────────┘
```

### 14.2 审批流程

```
LLM 返回工具调用 (如 edit_file)
    │
    ▼
权限检查 → 需要审批 (ask)
    │
    ▼
抛出 NodeInterrupt
    │
    ▼
CLI 捕获中断 → 显示审批详情
    │
    ▼
用户选择: [批准] 或 [拒绝]
    │
    ▼
graph.stream(Command(resume=result))
    │
    ▼
从断点恢复执行
```

### 14.3 三层压缩触发流程

```
每轮 think() 开始
    │
    ▼
Layer 1: Micro-Compact
  ├─ 检查是否有 N 轮前的 ToolMessage
  ├─ 有 → 替换为占位符
  └─ 无 → 跳过
    │
    ▼
估算当前消息总 token 数
    │
    ▼
超过 MAX_TOKENS (60000)?
  ├─ 是 → Layer 2: Auto-Compact
  │   ├─ 分割: 旧消息 + 最近 KEEP_RECENT_MESSAGES 条
  │   ├─ 调用 LLM 生成摘要
  │   ├─ 替换为 SystemMessage(摘要) + 最近消息
  │   └─ 失败时降级: 直接截断
  └─ 否 → 跳过
    │
    ▼
Agent 可随时调用 compact() 工具
  └─ Layer 3: Manual Compact
      ├─ 支持自定义 instruction