import uuid

from rich.console import Console
from rich.panel import Panel
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from agent import build_graph
from session import session_manager
from .interactions import prompt_input, select_one, confirm, setup_readline, set_slash_commands
from .display import (
    show_banner, show_session_info, show_help,
    format_text, format_tool_call, format_tool_result,
    format_usage, format_error, format_time,
)

console = Console()

# 全局单例
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def _process_stream(input_data, config, thread_id, project_root):
    """处理 graph.stream() 的输出，返回是否遇到中断。"""
    graph = get_graph()
    accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    interrupted = False

    for chunk in graph.stream(
        input_data,
        stream_mode=["messages", "updates"],
        config=config,
        version="v2",
    ):
        typ = chunk.get("type")
        data = chunk.get("data")

        if typ == "messages":
            msg, metadata = data
            node = metadata.get("langgraph_node", "")

            # 提取文本内容
            content = msg.content
            if isinstance(content, list):
                content = "".join(
                    block.get("text", "") if isinstance(block, dict) else str(block)
                    for block in content
                )
            if not isinstance(content, str):
                content = str(content) if content else ""

            # AI 文本响应
            if node == "think" and content:
                format_text({"chunk": content})

            # 流式 token 用量
            if node == "think" and hasattr(msg, "usage_metadata") and msg.usage_metadata:
                um = msg.usage_metadata
                accumulated_usage = {
                    "prompt_tokens": um.get("input_tokens", 0),
                    "completion_tokens": um.get("output_tokens", 0),
                    "total_tokens": um.get("total_tokens", 0),
                }

            # 工具调用请求
            tool_calls = []
            if hasattr(msg, "tool_call_chunks") and msg.tool_call_chunks:
                tool_calls = msg.tool_call_chunks
            elif hasattr(msg, "tool_calls") and msg.tool_calls:
                tool_calls = msg.tool_calls

            for tc in tool_calls:
                if tc.get("name") and tc.get("args"):
                    format_tool_call({
                        "tool_name": tc["name"],
                        "tool_call_id": tc.get("id", ""),
                        "args": tc["args"],
                    })

            # 工具执行结果
            from langchain_core.messages import ToolMessage
            if isinstance(msg, ToolMessage) and node == "execute_tools":
                format_tool_result({
                    "tool_call_id": msg.tool_call_id,
                    "result": msg.content,
                })

        elif typ == "updates":
            if isinstance(data, dict):
                # 中断（需要审批）
                if "__interrupt__" in data:
                    for intr in data["__interrupt__"]:
                        # 返回中断信息，让调用方处理审批
                        return accumulated_usage, intr.value

                # 从节点更新中提取累积 usage
                for _node_name, node_output in data.items():
                    if isinstance(node_output, dict) and "usage" in node_output:
                        accumulated_usage = node_output["usage"]

    # 发送用量
    format_usage(accumulated_usage)
    return accumulated_usage, None


def _handle_approval(interrupt_data, config, thread_id, project_root):
    """处理审批中断：显示详情，询问用户，递归恢复流。"""
    from .approval import show_approval_details
    show_approval_details(interrupt_data)

    approved = confirm("允许执行此操作？", default=True)
    approval_str = "approved" if approved else "rejected"
    console.print(f"  [dim]{'已批准' if approved else '已拒绝'}，继续...[/dim]")

    # 递归处理流（可能再次中断）
    usage, new_interrupt = _process_stream(
        Command(resume=approval_str), config, thread_id, project_root
    )
    if new_interrupt:
        return _handle_approval(new_interrupt, config, thread_id, project_root)
    return usage


# --- Slash command handlers ---


def cmd_sessions():
    try:
        sessions = session_manager.list_sessions()
        if not sessions:
            console.print("[dim]没有会话记录。[/dim]")
            return
        lines = []
        for s in sessions:
            title = (s.get("title") or "无标题")[:40]
            root = s.get("project_root", "")
            updated = format_time(s.get("updated_at", ""))
            lines.append(f"  [cyan]{title}[/cyan]  [dim]{root}[/dim]  [yellow]{updated}[/yellow]")
        console.print(Panel("\n".join(lines), title=f"共 {len(sessions)} 个会话", expand=False))
    except Exception as err:
        console.print(f"[red]获取失败: {err}[/red]")


def cmd_switch():
    sessions = session_manager.list_sessions()
    if not sessions:
        console.print("[dim]没有会话记录。[/dim]")
        return None
    options = [
        {"value": s["thread_id"], "label": f"{(s.get('title') or s['thread_id'][:16])}  ({format_time(s.get('updated_at', ''))})"}
        for s in sessions
    ]
    return select_one(options, "选择要切换的会话：")


def cmd_delete(current_id):
    sessions = session_manager.list_sessions()
    if not sessions:
        console.print("[dim]没有会话记录。[/dim]")
        return False
    options = [
        {"value": s["thread_id"], "label": f"{(s.get('title') or s['thread_id'][:16])}  ({format_time(s.get('updated_at', ''))})"}
        for s in sessions
    ]
    choice = select_one(options, "选择要删除的会话：")
    if not choice:
        return False
    if not confirm("确认删除？", default=False):
        console.print("[dim]已取消[/dim]")
        return False
    session_manager.delete_session(choice)
    console.print("[green]会话已删除。[/green]")
    return choice == current_id


def cmd_history(thread_id):
    try:
        graph = get_graph()
        messages = session_manager.get_history(thread_id, graph)
        if not messages:
            console.print("[dim]没有消息记录。[/dim]")
            return
        for msg in messages:
            if msg["type"] == "human":
                console.print(f"\n[cyan][用户] {msg['content']}[/cyan]")
            elif msg["type"] == "ai":
                console.print(f"\n[white][AI] {msg['content']}[/white]")
            elif msg["type"] == "tool":
                preview = (msg.get("content") or "")[:100]
                suffix = "..." if len(msg.get("content") or "") > 100 else ""
                console.print(f"  [dim][工具结果] {preview}{suffix}[/dim]")
        console.print()
    except Exception as err:
        console.print(f"[red]获取历史失败: {err}[/red]")


# --- Main entry point ---


def start_chat():
    # 初始化 readline 历史和 Tab 补全
    setup_readline()
    set_slash_commands(["help", "sessions", "switch", "new", "delete", "history", "clear", "exit"])

    show_banner()

    thread_id = str(uuid.uuid4())
    project_root = __import__("os").getcwd().replace("\\", "/")

    show_session_info(thread_id, project_root)

    while True:
        user_input = prompt_input(">")
        if user_input is None:
            console.print("\n再见！")
            break

        trimmed = user_input.strip()
        if not trimmed:
            continue

        if trimmed.startswith("/"):
            cmd = trimmed.split()[0].lower()
            if cmd == "/help":
                show_help()
            elif cmd == "/sessions":
                cmd_sessions()
            elif cmd == "/switch":
                new_id = cmd_switch()
                if new_id:
                    thread_id = new_id
                    console.print(f"[dim]当前会话: {thread_id[:8]}[/dim]")
            elif cmd == "/new":
                thread_id = str(uuid.uuid4())
                session_manager.create_or_update(thread_id, project_root)
                console.print(f"[green]新会话: {thread_id[:8]}[/green]")
            elif cmd == "/delete":
                deleted = cmd_delete(thread_id)
                if deleted:
                    thread_id = str(uuid.uuid4())
                    session_manager.create_or_update(thread_id, project_root)
                    console.print(f"[dim]已自动创建新会话: {thread_id[:8]}[/dim]")
            elif cmd == "/history":
                cmd_history(thread_id)
            elif cmd == "/clear":
                console.clear()
                show_banner()
                show_session_info(thread_id, project_root)
            elif cmd == "/exit":
                console.print("再见！")
                break
            else:
                console.print(f"[yellow]未知命令: {cmd}，输入 /help 查看可用命令[/yellow]")
            continue

        # 正常对话：直接调用 agent
        session_manager.create_or_update(thread_id, project_root, title=trimmed[:50])
        config = {"configurable": {"thread_id": thread_id}}
        input_data = {
            "messages": [HumanMessage(content=trimmed)],
            "project_root": project_root,
        }

        try:
            usage, interrupt_data = _process_stream(input_data, config, thread_id, project_root)
            if interrupt_data:
                _handle_approval(interrupt_data, config, thread_id, project_root)
        except Exception as err:
            console.print(f"\n[red]错误：[/red]{err}")
        console.print()


def main():
    start_chat()



if __name__ == "__main__":
    main()
