# 智能体记忆架构

## 一、架构总览

本智能体采用 **两层分离 + 三层压缩 + LangGraph Checkpointer 持久化** 的记忆架构，参照 Claude 的上下文管理设计。

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           记忆架构总览                                    │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │              Layer 1: 不可变上下文 (SystemMessage)                │    │
│  │              构建一次，跨轮完全一致 → KV cache HIT               │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │    │
│  │  │ ecode.md     │  │ 工具索引表    │  │ 工作规则 (静态文本)   │  │    │
│  │  │ 项目上下文   │  │ name+desc    │  │ 先读后写/局部修改/..  │  │    │
│  │  └──────────────┘  └──────────────┘  └──────────────────────┘  │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │              Layer 2: 可变消息 (messages)                        │    │
│  │              每轮变化 → cache MISS，三层压缩作用于此             │    │
│  │  ┌──────────────────┐  ┌──────────────────────────────────────┐│    │
│  │  │ compact_summary  │  │ 近期消息                             ││    │
│  │  │ (压缩时生成)     │  │ HumanMessage/AIMessage/ToolMessage   ││    │
│  │  └──────────────────┘  └──────────────────────────────────────┘│    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │              按需工具详情                                        │    │
│  │  get_tool_details(tool_name) → 完整 docstring + 参数 schema     │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  ┌──────────────────┐  ┌───────────┐                                    │
│  │ InMemorySaver    │  │  Session  │                                    │
│  │ (Checkpointer)   │  │  Manager  │                                    │
│  └──────────────────┘  └───────────┘                                    │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

### 核心文件

| 文件 | 职责 |
|------|------|
| `agent.py` | State 定义、不可变上下文构建、工作流编排、三层压缩调用入口 |
| `project_context.py` | 加载并缓存 ecode.md 项目上下文 |
| `tools/tool_index.py` | 工具索引表构建 + `get_tool_details` 按需查询 |
| `context_manager.py` | Layer 1 (Micro) + Layer 2 (Auto) 压缩实现 |
| `tools/context_tools.py` | Layer 3 (Manual) 的 compact 工具定义 |
| `session.py` | Checkpointer 初始化、会话元数据管理 |

---

## 二、两层分离设计

### Layer 1: 不可变上下文

**构建时机**：每个 session 的首次 `think()` 调用。

**存储位置**：`state["immutable_context"]`，后续轮次直接复用。

**内容组成**：

```
你是一个 AI 编码助手，可以直接操作项目文件系统。

项目根目录: {project_root}

---

## 项目上下文 (ecode.md)
{ecode.md 的内容，如果存在}

---

## 可用工具一览

| Tool | Description | Type |
|------|-------------|------|
| view_file | 读取并返回文件内容。可选行范围 | safe |
| edit_file | 局部修改文件：old_string → new_string | dangerous |
| ... | ... | ... |

使用 `get_tool_details` 工具获取某个工具的完整文档。

---

## 工作规则
...（先读后写、局部修改优先、错误处理、路径规则等）

### 工具详情
工具一览表已在上方列出。当你不确定某个工具的参数或用法时，先调用 get_tool_details 获取完整文档。

## 沟通
简洁直接，匹配用户语言，不确定时先问。
```

**缓存效果**：每轮 LLM 调用的 `[SystemMessage(immutable_ctx)]` 前缀完全一致，LLM provider 可命中 KV cache。

### Layer 2: 可变消息

**内容**：对话历史摘要 + 近期消息（HumanMessage, AIMessage, ToolMessage）。

**处理方式**：三层压缩（micro, auto, manual）只作用于此层。

**组装方式**：

```
[SystemMessage(immutable_ctx)]  ← 每轮相同 → KV cache HIT
[compact summary (如有)]        ← 压缩时变化 → cache MISS
[近期消息]                      ← 每轮变化 → cache MISS
```

---

## 三、ecode.md 项目上下文

**位置**：`project_context.py`

**加载规则**：
- 从项目根目录读取 `ecode.md` 文件
- 按 `project_root` 路径缓存，每个项目只读一次
- 文件不存在时优雅降级（跳过该 section）
- 超过 8000 字符时截断并记录警告

**内容建议**：
- 项目代码风格和规范
- 目录结构说明
- 常用约定和模式
- 特殊注意事项

---

## 四、工具索引（多级索引）

### Level 1: 索引表（在不可变上下文中）

**位置**：`tools/tool_index.py` → `build_tool_index()`

自动生成 markdown 表格，包含每个工具的：
- 名称
- 一行描述（docstring 首行，截断至 60 字符）
- 类型（safe / dangerous / meta）

约 600-800 字符，足够 LLM 选择正确的工具。

### Level 2: 完整文档（按需获取）

**位置**：`tools/tool_index.py` → `get_tool_details()`

LLM 在不确定某个工具的参数或用法时调用：

```
get_tool_details(tool_name="edit_file")
```

返回完整 docstring + 参数 schema（名称、类型、是否必填、默认值、描述）。

这是一个标准的 `@tool` 函数，属于 `SAFE_TOOLS`，不需要用户审批。

---

## 五、State：记忆的数据结构

```python
class State(TypedDict):
    messages:           Annotated[list[BaseMessage], add_messages]  # 可变消息流
    project_root:       str                                         # 项目根目录
    last_error:         str                                         # 最近错误信息
    retry_count:        int                                         # 重试次数
    usage:              dict                                        # token 用量统计
    compact_summary:    str                                         # 最近一次压缩的摘要文本
    compact_at:         int                                         # 压缩时的消息数量（位置指针）
    immutable_context:  str                                         # 不可变上下文（构建一次跨轮复用）
```

关键设计点：

- **`immutable_context`** — 首次 `think()` 时构建并存入 state，后续轮次直接读取，确保内容完全一致
- **`messages`** — 使用 `add_messages` reducer，只包含可变的对话消息
- **`compact_summary` + `compact_at`** — 压缩指针，标记哪些消息已被摘要化

---

## 六、三层上下文压缩

压缩只作用于 Layer 2（可变消息），不影响不可变上下文。

### Layer 1: Micro-Compact（微压缩）

**触发时机**：每轮 `think()` 调用 LLM 之前，自动执行。

**位置**：`context_manager.py` → `micro_compact()`

**做什么**：将 N 轮之前的 `ToolMessage` 替换为一行占位符。

| 工具类型 | 占位符格式 | 是否保留原内容 |
|----------|-----------|:------------:|
| `view_file` | 不替换，保留原内容 | ✅ |
| `run_command` | `[命令已执行: {cmd[:60]}, 成功/失败]` | ❌ |
| `search_code` | `[搜索完成: {pattern}, 找到 N 个匹配]` | ❌ |
| `list_files` | `[文件列表已列出: N 个文件, M 个目录]` | ❌ |
| `edit_file` | `[文件已修改: {path}]` | ❌ |
| `write_file` | `[文件已写入: {path}]` | ❌ |
| `create_file/directory` | `[文件操作完成: {path}]` | ❌ |
| 其他 | `[工具执行成功/失败]` | ❌ |

### Layer 2: Auto-Compact（自动摘要）

**触发时机**：估算 token 数超过阈值时自动触发。

**位置**：`context_manager.py` → `auto_compact()`

**流程**：分割旧消息/最近消息 → 调用 LLM 生成摘要 → 替换为 SystemMessage + 最近消息。

**降级策略**：LLM 调用失败时直接截断只保留最近消息。

### Layer 3: Manual Compact（手动压缩）

**触发方式**：Agent 调用 `compact(instruction="...")` 工具。

**位置**：`tools/context_tools.py` + `context_manager.py` → `manual_compact()`

**特点**：Agent 自主决策何时压缩，支持自定义指令指定保留重点。

---

## 七、持久化层

### 1. LangGraph InMemorySaver（Checkpointer）

```python
from langgraph.checkpoint.memory import InMemorySaver
checkpointer = InMemorySaver()
```

- 每次图执行后自动保存 State 快照（包括 `immutable_context`）
- 支持通过 `thread_id` 恢复任意历史状态
- 用于中断恢复（审批流程）和历史消息查询

**局限**：纯内存存储，服务重启后丢失。

### 2. SessionManager（会话元数据）

提供 `create_or_update()`, `list_sessions()`, `get_session()`, `delete_session()`, `get_history()` 接口。

---

## 八、配置参数汇总

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `MAX_TOKENS` | 60000 | 触发 Auto-Compact 的 token 阈值 |
| `KEEP_RECENT_MESSAGES` | 20 | Auto-Compact 保留的最近消息数 |
| `MICRO_COMPACT_AFTER_TURNS` | 3 | 多少轮前的工具结果触发微压缩 |
| `SUMMARY_MAX_CHARS` | 500 | 摘要最大字符数 |
| `MAX_TOOL_RESULT_CHARS` | 8000 | 工具结果最大字符数（超长截断） |
| `MAX_ECODE_MD_CHARS` | 8000 | ecode.md 最大字符数（超长截断） |

---

## 九、缓存优化说明

### 变更前

```
每轮 LLM 调用:
  SystemMessage(system_prompt.format(project_root=...))  ← 每轮重建，内容相同但对象不同
  + messages                                              ← 每轮变化
```

问题：虽然 system prompt 内容相同，但每轮都重新 format 生成新字符串对象，部分 LLM provider 无法命中前缀缓存。

### 变更后

```
每轮 LLM 调用:
  SystemMessage(immutable_context)  ← 同一个字符串，从 state 读取 → KV cache HIT
  + messages                        ← 每轮变化 → cache MISS
```

不可变上下文（ecode.md + 工具索引 + 工作规则）通常占 1000-3000 tokens，缓存命中可显著减少长会话的计算开销和延迟。
