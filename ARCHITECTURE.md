# AI Coding Agent 后端架构文档

## 技术栈

- **Web框架**: FastAPI
- **AI框架**: LangChain + LangGraph
- **LLM**: mimo-v2.5-pro (小米MiMo)
- **状态管理**: LangGraph InMemorySaver
- **通信方式**: SSE (Server-Sent Events)

---

## 项目结构

```
ecode_back/
├── main.py           # FastAPI 入口，API路由定义
├── agent.py          # LangGraph 智能体核心逻辑
├── model.py          # LLM模型配置
├── schemas.py        # Pydantic 数据模型
├── session.py        # 会话管理器
├── tools/            # 工具集
│   ├── __init__.py       # 工具注册与分类
│   ├── file_tools.py     # 文件操作工具
│   ├── search_tools.py   # 搜索工具
│   └── command_tools.py  # 命令执行工具
└── utils/
    └── sse.py        # SSE 格式化工具
```

---

## 核心模块说明

### 1. `main.py` - API接口层

提供5个REST API接口：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/chat/stream` | POST | 发送消息，返回SSE流 |
| `/api/chat/resume` | POST | 恢复被中断的对话（审批） |
| `/api/sessions` | GET | 获取所有会话列表 |
| `/api/sessions/{thread_id}` | DELETE | 删除指定会话 |
| `/api/sessions/{thread_id}/history` | GET | 获取会话历史消息 |

### 2. `agent.py` - 智能体核心

#### 状态定义 (State)

```python
class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # 消息列表
    project_root: str       # 项目根目录
    last_error: str         # 最近错误信息
    retry_count: int        # 重试次数
```

#### 工作流节点

| 节点 | 函数 | 职责 |
|------|------|------|
| `think` | `think()` | 调用LLM生成响应或工具调用 |
| `execute_tools` | `execute_tools()` | 执行工具调用，处理审批 |
| `handle_error` | `handle_error()` | 处理错误，决定是否重试 |

#### 工作流程图

```
                    ┌──────────────────────────────────────────────────────────┐
                    │                                                          │
                    ▼                                                          │
               ┌─────────┐                                                    │
    START ───▶ │  think  │                                                    │
               └────┬────┘                                                    │
                    │                                                         │
          ┌────────┴────────┐                                                │
          │                 │                                                │
          ▼                 ▼                                                │
    有工具调用          无工具调用                                             │
          │                 │                                                │
          ▼                 ▼                                                │
  ┌──────────────┐        END                                                │
  │execute_tools │                                                            │
  └──────┬───────┘                                                            │
         │                                                                    │
         ▼                                                                    │
  ┌──────────────┐     retry_count > 3                                       │
  │handle_error  │ ──────────────────────────▶ END                           │
  └──────┬───────┘                                                            │
         │                                                                    │
         │ retry_count <= 3                                                   │
         └────────────────────────────────────────────────────────────────────┘
```

#### 审批机制 (Interrupt)

当调用危险工具时，`execute_tools` 会触发 `interrupt` 暂停执行：

```python
if tool_name in DANGEROUS_TOOLS:
    approval = interrupt({
        "type": "tool_approval",
        "tool_name": tool_name,
        "tool_call_id": tc["id"],
        "args": tc["args"],
    })
```

暂停后需要前端调用 `/api/chat/resume` 接口恢复执行。

### 3. `model.py` - LLM配置

当前使用小米MiMo模型：

```python
llm = ChatOpenAI(
    model="mimo-v2.5-pro",
    api_key=MIMO,
    base_url="https://token-plan-cn.xiaomimimo.com/v1",
    streaming=True,
)
```

支持切换为阿里千问（已注释）。

### 4. `session.py` - 会话管理

`SessionManager` 类负责：

- 创建/更新会话元数据
- 列出所有会话（按更新时间排序）
- 获取会话信息
- 删除会话
- 获取会话历史消息（从LangGraph checkpointer）

会话数据存储在内存字典 `_sessions` 中。

### 5. `tools/` - 工具集

#### 工具分类

| 类型 | 工具 | 是否需要审批 |
|------|------|-------------|
| 安全 | `view_file`, `search_code`, `list_files` | ❌ |
| 危险 | `edit_file`, `write_file`, `create_file`, `create_directory`, `run_command` | ✅ |

#### 工具说明

**只读工具（免审批）**

- **view_file(path, start_line?, end_line?)**: 读取文件内容，支持行范围
- **search_code(pattern, path?, include_pattern?)**: 正则搜索代码，支持文件过滤
- **list_files(path?, pattern?, max_depth?)**: 列出目录文件和子目录

**可写工具（需审批）**

- **edit_file(path, old_string, new_string)**: 局部修改文件，将 old_string 替换为 new_string（唯一匹配）
- **write_file(path, content)**: 覆盖写入文件全部内容，不存在则创建
- **create_file(path, content)**: 创建新文件，已存在则失败
- **create_directory(path)**: 创建目录（递归创建，类似 mkdir -p）
- **run_command(command, timeout?)**: 执行终端命令，支持自定义超时

---

## SSE 事件协议

后端通过SSE向前端推送事件，格式：

```
event: {事件类型}
data: {JSON数据}
```

### 事件类型

| 事件 | 数据 | 说明 |
|------|------|------|
| `text` | `{"chunk": "..."}` | AI文本响应（流式） |
| `tool_call` | `{"tool_name", "tool_call_id", "args"}` | 工具调用请求 |
| `tool_result` | `{"tool_call_id", "result"}` | 工具执行结果 |
| `approval_required` | `{"type", "tool_name", "tool_call_id", "args"}` | 需要用户审批 |
| `done` | `{"status": "ok"/"error"}` | 完成 |
| `error` | `{"message"}` | 错误信息 |

---

## 前端适配要求

### 1. 消息发送

```javascript
// POST /api/chat/stream
{
  "prompt": "用户消息",
  "project_root": ".",
  "thread_id": "uuid"  // 可选，不传则新建会话
}
```

### 2. 审批流程

```javascript
// 1. 监听 approval_required 事件
eventSource.addEventListener('approval_required', (e) => {
  const data = JSON.parse(e.data);
  // 显示审批弹窗
});

// 2. 用户审批后调用 resume
// POST /api/chat/resume
{
  "thread_id": "xxx",
  "approval": "approved"  // 或 "rejected"
}
```

### 3. 完整SSE处理示例

```javascript
function handleSSE(event, data) {
  switch (event) {
    case 'text':
      appendText(data.chunk);
      break;
    case 'tool_call':
      showToolCall(data.tool_name, data.args);
      break;
    case 'tool_result':
      showToolResult(data.tool_call_id, data.result);
      break;
    case 'approval_required':
      showApprovalDialog(data);
      break;
    case 'done':
      if (data.status === 'error') showError();
      break;
    case 'error':
      showError(data.message);
      break;
  }
}
```

---

## 配置项

环境变量（`.env`）：

```env
ALI=阿里千问API Key
MIMO=小米MiMo API Key
```

---

## 待优化项

1. **持久化存储**: 当前会话和checkpointer都在内存中，重启丢失
2. **并发控制**: 多请求同时操作同一会话可能导致状态冲突
3. **错误重试**: 当前最多重试3次，可考虑指数退避
4. **工具权限**: 可增加更细粒度的权限控制
5. **流式优化**: tool_call和tool_result可增加进度信息