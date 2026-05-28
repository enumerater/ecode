# 任务系统架构

本文档描述 ecode 任务规划系统的设计原理、数据流和与 Claude Code 的架构对比。

## 目录

- [设计背景](#设计背景)
- [核心架构](#核心架构)
- [TaskStore：事件总线](#taskstore事件总线)
- [工具层：纯 CRUD](#工具层纯-crud)
- [UI 层：独立订阅](#ui层独立订阅)
- [SSE 事件：Web API](#sse-事件web-api)
- [与 Claude Code 的对比](#与-claude-code-的对比)
- [旧架构的问题](#旧架构的问题)

---

## 设计背景

ecode 的任务系统让 LLM 能将复杂任务分解为多个步骤，并实时向前端展示执行进度。设计参考了 Claude Code 的 TaskCreate/TaskUpdate 机制，核心原则是：

> **工具只负责"做事"，通知 UI 是独立的基础设施。**

---

## 核心架构

```
LLM 调用工具
    │
    ▼
┌─────────────────────┐
│  task_plan_tools.py │   工具层：纯 CRUD 操作
│  create_task()      │   调用 TaskStore，返回简单文本
│  update_task()      │   不返回 JSON 信号
│  list_tasks()       │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   task_store.py     │   存储层：内存状态 + 事件通知
│   TaskStore         │
│   ├─ _tasks (dict)  │   线程安全的内存存储
│   ├─ _lock          │   threading.Lock
│   └─ _subscribers   │   订阅者列表
└────────┬────────────┘
         │ _notify()
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│  CLI  │ │  SSE  │   UI 层：独立订阅
│callback│ │ event │
└───────┘ └───────┘
```

### 关键设计决策

1. **工具返回值 ≠ UI 信号** — 工具返回的是操作结果文本，不是控制信号
2. **事件总线解耦** — TaskStore 的 `subscribe/notify` 机制让 UI 与工具完全独立
3. **无 LangGraph 状态依赖** — 任务状态不存入 LangGraph State，避免 agent 循环耦合
4. **线程安全** — `threading.Lock` 保护共享状态，支持并发工具执行

---

## TaskStore：事件总线

`task_store.py` 是整个任务系统的核心，提供两个能力：**状态管理** 和 **事件通知**。

### 数据模型

```python
@dataclass
class Task:
    id: str           # 自增 ID（"1", "2", "3"...）
    subject: str      # 任务标题
    active_form: str  # 执行中显示的文本（如 "正在分析项目结构"）
    status: str       # pending | in_progress | completed
```

### API

| 方法 | 说明 | 触发通知 |
|------|------|---------|
| `create(subject, active_form)` | 创建任务，返回 Task | Yes |
| `update(task_id, status, subject, active_form)` | 更新任务字段 | Yes |
| `list()` | 返回所有任务（按 ID 排序） | No |
| `get(task_id)` | 获取单个任务 | No |
| `reset()` | 清空所有任务 | Yes |
| `subscribe(callback)` | 订阅变化，返回 unsubscribe 函数 | — |

### 通知机制

```python
# 订阅
unsubscribe = task_store.subscribe(callback)

# 当 create/update/reset 被调用时：
def _notify(self):
    tasks = self.list()          # 获取当前快照
    for cb in self._subscribers: # 遍历订阅者
        cb(tasks)                # 回调，传入任务列表

# 取消订阅
unsubscribe()
```

与 Claude Code 的对比：

| | Claude Code | ecode |
|---|---|---|
| 存储 | 文件系统（`~/.claude/tasks/`） | 内存（dict） |
| 通知 | `createSignal()` + `fs.watch()` | `subscribe/notify` 回调 |
| 持久化 | 是（JSON 文件） | 否（会话级） |
| 并发 | file lock | threading.Lock |

---

## 工具层：纯 CRUD

`tools/task_plan_tools.py` 中的三个工具是纯粹的 CRUD 操作：

```python
@tool
def create_task(subject: str, active_form: str = "") -> str:
    task = task_store.create(subject, active_form)
    return f"任务已创建: {task.subject} (id: {task.id})"

@tool
def update_task(task_id: str, status: str = "", ...) -> str:
    task = task_store.update(task_id, status=status, ...)
    if not task:
        return f"任务 {task_id} 不存在"
    return f"任务 {task_id} 已更新, 状态: {status}"

@tool
def list_tasks() -> str:
    tasks = task_store.list()
    # 格式化为文本列表
    ...
```

### 与旧实现的对比

**旧实现（信号劫持）：**
```python
@tool
def create_task(subject, active_form):
    return json.dumps({
        "signal": "TASK_UPDATE",    # ← 控制信号混入工具返回值
        "action": "create",
        "task": {"id": ..., "subject": ..., "status": "pending"}
    })
```

agent.py 必须解析这个 JSON 信号：
```python
# 旧代码：80+ 行信号检测
elif tc["name"] in ("create_task", "update_task", "list_tasks"):
    for msg in results:
        signal_data = json.loads(msg.content)
        if signal_data.get("signal") == TASK_SIGNAL:
            task_updates.append(signal_data)
# ... 然后手动更新 LangGraph state
```

**新实现（CRUD + 事件总线）：**
```python
@tool
def create_task(subject, active_form):
    task = task_store.create(subject, active_form)  # 直接操作存储
    return f"任务已创建: {task.subject}"              # 返回简单文本
```

agent.py 不需要任何任务相关代码 — 通知由 TaskStore 自动完成。

---

## UI 层：独立订阅

### CLI（cli/chat.py）

```python
def _process_stream(input_data, config, thread_id, project_root):
    # 新查询时清空上一轮任务
    task_store.reset()

    # 订阅 TaskStore
    def _on_task_update(tasks):
        spinner.set_task_info(tasks)   # 更新 spinner 显示
        spinner.stop()
        show_task_list(tasks)          # 渲染任务列表面板
        spinner.start()

    unsubscribe_tasks = task_store.subscribe(_on_task_update)
    try:
        # ... 处理 graph stream ...
    finally:
        unsubscribe_tasks()
```

**关键变化：** 任务更新不再从 graph `updates` 流中检测，而是通过 TaskStore 回调直接接收。

### Spinner 联动（cli/live_status.py）

`QuerySpinner` 的 `_make_text()` 方法会检查是否有进行中的任务：

```python
def _make_text(self):
    if self._current_task:
        # 用任务的 activeForm 替代默认的 "思考中"
        task_text = self._current_task.get("activeForm")
        state_text = task_text
    # ...
```

当 TaskStore 通知到达时，`set_task_info()` 自动找到 `in_progress` 状态的任务，spinner 实时显示其 `activeForm`。

---

## SSE 事件：Web API

`main.py` 中的 `stream_graph()` 通过 `asyncio.Queue` 桥接线程回调到 async 生成器：

```python
async def stream_graph(input_data, config):
    task_queue = asyncio.Queue()

    def _on_task_update(tasks):
        task_queue.put_nowait(tasks)  # 线程 → queue

    unsubscribe_tasks = task_store.subscribe(_on_task_update)
    try:
        async for chunk in graph.astream(...):
            # ... 处理 messages/updates ...

            # drain 任务更新事件
            while not task_queue.empty():
                tasks = task_queue.get_nowait()
                yield sse("task_update", {
                    "tasks": [{"id": t.id, "subject": t.subject,
                               "activeForm": t.active_form,
                               "status": t.status} for t in tasks],
                })
    finally:
        unsubscribe_tasks()
```

### SSE 事件类型

| 事件 | 数据 | 说明 |
|------|------|------|
| `text` | `{chunk: string}` | LLM 文本输出 |
| `tool_call` | `{tool_name, tool_call_id, args}` | 工具调用请求 |
| `tool_result` | `{tool_call_id, result}` | 工具执行结果 |
| `tool_result_chunk` | `{content, seq, ...}` | 流式工具结果 |
| **`task_update`** | `{tasks: [{id, subject, activeForm, status}]}` | **任务状态变化** |
| `approval_required` | `{...}` | 需要人工审批 |
| `usage` | `{prompt_tokens, ...}` | Token 用量 |
| `done` | `{status}` | 对话结束 |

---

## 与 Claude Code 的对比

### 数据流对比

```
Claude Code:
  LLM → TaskCreateTool → writeFile() → notifyTasksUpdated()
                                              ↓
                                     fs.watch() + useSyncExternalStore
                                              ↓
                                     TaskListV2.tsx (React/Ink)

ecode:
  LLM → create_task() → task_store.create() → _notify()
                                                    ↓
                                            subscribe callback
                                                    ↓
                                         CLI spinner / SSE event
```

### 架构决策对比

| 维度 | Claude Code | ecode |
|------|-------------|-------|
| 任务存储 | 文件系统 | 内存 |
| 通知机制 | Signal + fs.watch | 回调函数 |
| UI 框架 | React/Ink (useSyncExternalStore) | Rich (callback) |
| 工具审批 | 不需要 | 不需要 |
| 多进程支持 | 是（file lock） | 否（单进程） |
| 持久化 | 是 | 否 |

### 相同的设计原则

1. **工具是纯 CRUD** — 不返回控制信号
2. **UI 通知是独立基础设施** — 不依赖 agent 循环
3. **任务工具不需要审批** — 在 SAFE_TOOLS 中
4. **任务上下文注入 LLM** — think() 调用前将任务列表加入系统提示

---

## 旧架构的问题

### 问题 1：信号劫持

```python
# 旧：工具返回值被劫持为 UI 控制信号
return json.dumps({"signal": "TASK_UPDATE", "action": "create", ...})
```

工具的返回值应该是操作结果，不是给 agent 的控制指令。这违反了关注点分离。

### 问题 2：agent 耦合

```python
# 旧：agent.py 中 80+ 行信号解析代码
elif tc["name"] in ("create_task", "update_task", "list_tasks"):
    for msg in results:
        signal_data = json.loads(msg.content)
        if signal_data.get("signal") == TASK_SIGNAL:
            task_updates.append(signal_data)
# ... 还要手动替换 ToolMessage 为友好结果
```

agent 应该专注于编排（think → execute → error），不应该知道 UI 更新的细节。

### 问题 3：前端被动等待

```
旧：任务状态存在 LangGraph state 中
    → 只有 agent 循环推进时才能更新
    → 前端必须等 graph stream 吐出 tasks 字段
    → 无法独立获取任务状态
```

### 问题 4：状态耦合

```python
# 旧：tasks 是 LangGraph State 的一部分
class State(TypedDict):
    tasks: list  # ← 与 messages、project_root 等混在一起
```

任务状态是 UI 层的概念，不应该污染 agent 的核心状态。

---

## 工具分类

任务规划工具已移入 `SAFE_TOOLS`，不需要用户审批：

| 工具 | 分类 | 说明 |
|------|------|------|
| `create_task` | SAFE | 创建任务步骤 |
| `update_task` | SAFE | 更新任务状态 |
| `list_tasks` | SAFE | 列出所有任务 |

这是因为任务工具只操作内存中的 TaskStore，没有文件写入或命令执行等副作用。
