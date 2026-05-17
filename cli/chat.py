import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uuid
import json
import time

from rich.console import Console
from rich.panel import Panel
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langgraph.types import Command

from agent import build_graph
from session import get_session_manager, switch_storage, get_storage_backend, SUPPORTED_BACKENDS
from permissions.modes import PermissionMode, MODE_DESCRIPTIONS
from .interactions import prompt_input, select_one, confirm, setup_readline, set_slash_commands
from .display import (
    show_banner, show_session_info, show_help,
    format_text, format_usage, format_error, format_time,
    tool_label, format_tool_call_args, format_result_detail,
    _brief_result_summary,
)
from .live_status import QuerySpinner, THINKING, TOOL_USE, RESPONDING

console = Console(force_terminal=True)

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def reset_graph():
    global _graph
    _graph = None


def _process_stream(input_data, config, thread_id, project_root):
    """处理 graph.stream() 的输出。"""
    graph = get_graph()
    accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    spinner = QuerySpinner()
    spinner.start()
    pending_tools = {}

    try:
        for chunk in graph.stream(
            input_data,
            stream_mode=["messages", "updates"],
            config=config,
            version="v2",
        ):
            if isinstance(chunk, dict):
                typ = chunk.get("type", "")
                data = chunk.get("data")
            elif isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
                typ, data = chunk
            else:
                continue

            # ==============================================
            # updates 流：节点更新、用量、中断
            # ==============================================
            if typ == "updates" and isinstance(data, dict):
                if "__interrupt__" in data:
                    spinner.stop()
                    for intr in data["__interrupt__"]:
                        return accumulated_usage, intr.value

                for node_name, node_data in data.items():
                    if not isinstance(node_data, dict):
                        continue

                    if node_name == "think":
                        if "messages" in node_data:
                            spinner.set_state(THINKING)

                    if "messages" in node_data:
                        for msg in node_data["messages"]:
                            if isinstance(msg, ToolMessage):
                                continue
                            if isinstance(msg, AIMessage) and msg.content:
                                content = msg.content
                                if isinstance(content, list):
                                    content = "".join(
                                        block.get("text", "") if isinstance(block, dict) else str(block)
                                        for block in content
                                    )
                                if content:
                                    spinner.set_state(RESPONDING)
                                    spinner.stream_write("\n" + content)

                    if "usage" in node_data:
                        accumulated_usage = node_data["usage"]

            # ==============================================
            # messages 流：工具调用和结果
            # ==============================================
            elif typ == "messages":
                try:
                    msg, metadata = data
                    node = metadata.get("langgraph_node", "")

                    # ── AI 消息：注册工具调用 ──
                    if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
                        spinner.stream_end()  # 结束流式输出
                        for tc in msg.tool_calls:
                            tc_id = tc.get("id", "")
                            tc_name = tc.get("name", "")
                            tc_args = tc.get("args", {})
                            if not tc_id or not tc_name:
                                continue

                            pending_tools[tc_id] = {
                                "name": tc_name,
                                "args": tc_args,
                                "start_time": time.time(),
                            }

                            label = tool_label(tc_name)
                            spinner.set_state(TOOL_USE, label)
                            detail = format_tool_call_args(tc_name, tc_args)
                            if detail:
                                console.print(f"\n  [blue]▸[/blue] [bold]{label}[/bold] [dim]{detail}[/dim]")
                            else:
                                console.print(f"\n  [blue]▸[/blue] [bold]{label}[/bold]")

                    # ── 工具结果 ──
                    elif isinstance(msg, ToolMessage):
                        spinner.stream_end()  # 结束流式输出
                        tc_id = msg.tool_call_id
                        tool_info = pending_tools.pop(tc_id, {})
                        tool_name = tool_info.get("name", "") or getattr(msg, "name", "")
                        elapsed = time.time() - tool_info.get("start_time", time.time())

                        result_content = msg.content
                        try:
                            parsed = json.loads(result_content) if isinstance(result_content, str) else result_content
                            success = parsed.get("success", True) if isinstance(parsed, dict) else True
                        except:
                            success = True
                            parsed = {}

                        icon = "[green]✓[/green]" if success else "[red]✗[/red]"
                        summary = _build_result_summary(tool_name, parsed if isinstance(parsed, dict) else {})
                        console.print(f"  {icon} [dim]⏱ {elapsed:.1f}s[/dim] {summary}")

                        if tool_name in ("view_file", "search_code", "run_command", "list_files"):
                            if success and isinstance(parsed, dict):
                                format_result_detail(tool_name, parsed)

                        spinner.set_state(THINKING)

                    # ── AI 文本回复 ──
                    elif isinstance(msg, AIMessage) and msg.content:
                        content = msg.content
                        if isinstance(content, list):
                            content = "".join(
                                block.get("text", "") if isinstance(block, dict) else str(block)
                                for block in content
                            )
                        if content:
                            spinner.set_state(RESPONDING)
                            spinner.stream_write(content)
                except Exception as e:
                    pass
    finally:
        spinner.stream_end()
        spinner.stop()

    overall_elapsed = spinner.elapsed()
    format_usage(accumulated_usage, overall_elapsed)
    return accumulated_usage, None


def _build_result_summary(tool_name: str, data: dict) -> str:
    """构建工具结果的一行摘要（Rich markup）。"""
    if not data:
        return ""

    success = data.get("success", True)
    if not success:
        error = data.get("error", "未知错误")
        return f"[red]{error[:60]}[/red]"

    parts = []

    if tool_name == "view_file":
        path = data.get("path", "")
        total = data.get("total_lines", 0)
        if path:
            parts.append(path)
        if total:
            parts.append(f"{total} 行")

    elif tool_name == "edit_file":
        path = data.get("path", "")
        removed = data.get("lines_removed", 0)
        added = data.get("lines_added", 0)
        if path:
            parts.append(path)
        parts.append(f"-{removed} +{added}")

    elif tool_name in ("write_file", "create_file"):
        path = data.get("path", "")
        size = data.get("bytes_written", 0)
        if path:
            parts.append(path)
        if size:
            parts.append(f"{size} bytes")

    elif tool_name == "create_directory":
        path = data.get("path", "")
        if path:
            parts.append(path)

    elif tool_name == "search_code":
        matches = data.get("matches", [])
        total = data.get("total", len(matches))
        parts.append(f"{total} 处匹配")

    elif tool_name == "list_files":
        files = data.get("total_files", 0)
        dirs = data.get("total_dirs", 0)
        parts.append(f"{files} 文件, {dirs} 目录")

    elif tool_name == "run_command":
        exit_code = data.get("exit_code")
        if exit_code is not None:
            if exit_code == 0:
                parts.append("[green]exit 0[/green]")
            else:
                parts.append(f"[red]exit {exit_code}[/red]")

    elif tool_name == "git_status":
        branch = data.get("branch", "")
        is_clean = data.get("is_clean", False)
        if branch:
            parts.append(f"branch: {branch}")
        if is_clean:
            parts.append("[green]clean[/green]")

    elif tool_name == "git_diff":
        has_changes = data.get("has_changes", False)
        parts.append("有变更" if has_changes else "无变更")

    elif tool_name == "git_log":
        commits = data.get("commits", [])
        parts.append(f"{len(commits)} 条提交")

    elif tool_name == "git_commit":
        hash_val = data.get("hash", "")
        if hash_val:
            parts.append(f"commit {hash_val}")

    elif tool_name == "compact":
        msg = data.get("message", "已压缩")
        parts.append(msg)

    else:
        path = data.get("path", "")
        msg = data.get("message", "")
        if path:
            parts.append(path)
        elif msg:
            parts.append(msg[:60])

    return " ".join(parts)


def _handle_approval(interrupt_data, config, thread_id, project_root):
    """处理审批中断。"""
    from .approval import show_approval_details
    show_approval_details(interrupt_data)

    choice = select_one(
        [
            {"value": "approved", "label": "允许执行"},
            {"value": "rejected", "label": "拒绝"},
        ],
        message="是否允许此操作？",
    )
    approved = choice == "approved"
    approval_str = choice or "rejected"
    console.print(f"  [dim]{'已批准' if approved else '已拒绝'}，继续...[/dim]")

    usage, new_interrupt = _process_stream(
        Command(resume=approval_str), config, thread_id, project_root
    )
    if new_interrupt:
        return _handle_approval(new_interrupt, config, thread_id, project_root)
    return usage


# --- Slash command handlers ---


def cmd_sessions():
    try:
        sessions = get_session_manager().list_sessions()
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
    sessions = get_session_manager().list_sessions()
    if not sessions:
        console.print("[dim]没有会话记录。[/dim]")
        return None
    options = [
        {"value": s["thread_id"], "label": f"{(s.get('title') or s['thread_id'][:16])}  ({format_time(s.get('updated_at', ''))})"}
        for s in sessions
    ]
    return select_one(options, "选择要切换的会话：")


def cmd_delete(current_id):
    sessions = get_session_manager().list_sessions()
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
    get_session_manager().delete_session(choice)
    console.print("[green]会话已删除。[/green]")
    return choice == current_id


def cmd_history(thread_id):
    try:
        graph = get_graph()
        messages = get_session_manager().get_history(thread_id, graph)
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
    setup_readline()
    set_slash_commands(["help", "sessions", "switch", "new", "delete", "history", "clear", "exit", "mode", "plan", "storage"])

    show_banner()

    thread_id = str(uuid.uuid4())
    project_root = __import__("os").getcwd().replace("\\", "/")
    permission_mode = "default"
    plan_mode = False

    show_session_info(thread_id, project_root, get_storage_backend())

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
                get_session_manager().create_or_update(thread_id, project_root)
                console.print(f"[green]新会话: {thread_id[:8]}[/green]")
            elif cmd == "/delete":
                deleted = cmd_delete(thread_id)
                if deleted:
                    thread_id = str(uuid.uuid4())
                    get_session_manager().create_or_update(thread_id, project_root)
                    console.print(f"[dim]已自动创建新会话: {thread_id[:8]}[/dim]")
            elif cmd == "/history":
                cmd_history(thread_id)
            elif cmd == "/clear":
                console.clear()
                show_banner()
                show_session_info(thread_id, project_root, get_storage_backend())
            elif cmd == "/mode":
                console.print(f"[dim]当前权限模式: {permission_mode}[/dim]")
                options = [
                    {"value": m.value, "label": f"{m.value} - {MODE_DESCRIPTIONS.get(m, '')}"}
                    for m in PermissionMode
                ]
                new_mode = select_one(options, "选择权限模式：")
                if new_mode:
                    permission_mode = new_mode
                    console.print(f"[green]已切换到: {permission_mode}[/green]")
            elif cmd == "/plan":
                plan_mode = not plan_mode
                if plan_mode:
                    permission_mode = "plan"
                    console.print("[green]已进入计划模式。Agent 将只分析规划，不执行修改。[/green]")
                else:
                    permission_mode = "default"
                    console.print("[green]已退出计划模式。现在可以执行修改操作。[/green]")
            elif cmd == "/storage":
                current = get_storage_backend()
                console.print(f"[dim]当前存储后端: {current}[/dim]")
                options = [
                    {"value": b, "label": f"{b}{'  (当前)' if b == current else ''}"}
                    for b in SUPPORTED_BACKENDS
                ]
                new_backend = select_one(options, "选择存储后端：")
                if new_backend and new_backend != current:
                    try:
                        switch_storage(new_backend)
                        reset_graph()  # 重置 graph，下次调用时用新 checkpointer 重新编译
                        console.print(f"[green]已切换到: {new_backend}[/green]")
                        console.print("[dim]注意：切换后之前的会话数据在新后端中不可见[/dim]")
                    except ConnectionError as e:
                        console.print(f"[red]{e}[/red]")
            elif cmd == "/exit":
                console.print("再见！")
                break
            else:
                console.print(f"[yellow]未知命令: {cmd}，输入 /help 查看可用命令[/yellow]")
            continue

        # 正常对话
        get_session_manager().create_or_update(thread_id, project_root, title=trimmed[:50])
        config = {"configurable": {"thread_id": thread_id}}
        input_data = {
            "messages": [HumanMessage(content=trimmed)],
            "project_root": project_root,
            "permission_mode": permission_mode,
            "plan_mode": plan_mode,
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
