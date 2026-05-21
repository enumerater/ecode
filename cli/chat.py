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
from .interactions import prompt_input, select_one, confirm, set_slash_commands, supplement_input, select_options, set_mode_toggle_callback
from .display import (
    show_banner, show_session_info, show_help,
    format_text, format_usage, format_error, format_time,
    tool_label, format_tool_call_args, format_result_detail,
    _brief_result_summary, show_task_list, show_question_form,
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
    """处理 graph.stream() 的输出。生成器，yield 每个 chunk；遇到中断 yield 中断数据。"""
    graph = get_graph()
    accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    spinner = QuerySpinner()
    spinner.start()
    pending_tools = {}
    last_tasks = None  # 跟踪任务状态变化

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
                        yield {"type": "interrupt", "data": intr.value, "usage": accumulated_usage}
                    return

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

                    # 检测任务状态变化
                    if "tasks" in node_data:
                        new_tasks = node_data["tasks"]
                        if new_tasks != last_tasks:
                            last_tasks = new_tasks
                            spinner.set_task_info(new_tasks)
                            # 暂停 spinner 显示任务列表
                            spinner.stop()
                            show_task_list(new_tasks)
                            spinner.start()

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

        # 流正常结束
        overall_elapsed = spinner.elapsed()
        format_usage(accumulated_usage, overall_elapsed)
        yield {"type": "done", "usage": accumulated_usage}
    finally:
        spinner.stream_end()
        spinner.stop()


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

    elif tool_name == "create_task":
        task = data.get("task", {})
        subject = task.get("subject", "")
        if subject:
            parts.append(subject)

    elif tool_name == "update_task":
        task_id = data.get("task_id", "")
        status = data.get("status", "")
        if status:
            parts.append(f"{task_id} → {status}")
        elif task_id:
            parts.append(task_id)

    elif tool_name == "list_tasks":
        parts.append("查看任务列表")

    elif tool_name == "ask_user_question":
        answers = data.get("answers", {})
        if answers:
            summary_parts = []
            for q, a in list(answers.items())[:3]:
                summary_parts.append(f"{a}")
            parts.append(", ".join(summary_parts))
        else:
            parts.append("等待用户回答")

    else:
        path = data.get("path", "")
        msg = data.get("message", "")
        if path:
            parts.append(path)
        elif msg:
            parts.append(msg[:60])

    return " ".join(parts)


def _handle_approval(interrupt_data, config, thread_id, project_root, session_approved=False):
    """处理审批中断。"""
    # 检查是否为 ask_user_question 中断
    if isinstance(interrupt_data, dict) and interrupt_data.get("type") == "ask_user_question":
        return _handle_question(interrupt_data, config, thread_id, project_root, session_approved)

    from .approval import show_approval_details
    show_approval_details(interrupt_data)

    tool_name = interrupt_data.get("tool_name", "") if isinstance(interrupt_data, dict) else ""
    tool_label_name = tool_label(tool_name) if tool_name else tool_name

    options = [
        {"value": "approved", "label": "允许执行"},
        {"value": "rejected", "label": "拒绝"},
    ]
    options.append({"value": "session_approve", "label": "全部同意（本会话）"})

    choice = select_one(options, message="是否允许此操作？")

    if choice == "session_approve":
        session_approved = True
        choice = "approved"
        console.print("  [dim]已批准，本会话内所有操作将自动执行[/dim]")
    else:
        approved = choice == "approved"
        approval_str = choice or "rejected"
        console.print(f"  [dim]{'已批准' if approved else '已拒绝'}，继续...[/dim]")

    approval_str = choice or "rejected"

    resume_cmd = Command(resume=approval_str)
    if session_approved:
        resume_cmd = Command(resume=approval_str, update={"session_approved": True})

    usage = None
    new_interrupt = None
    for event in _process_stream(resume_cmd, config, thread_id, project_root):
        if event["type"] == "interrupt":
            new_interrupt = event["data"]
            usage = event["usage"]
        elif event["type"] == "done":
            usage = event["usage"]

    if new_interrupt:
        return _handle_approval(new_interrupt, config, thread_id, project_root, session_approved)
    return usage, session_approved


def _handle_question(interrupt_data, config, thread_id, project_root, session_approved=False):
    """处理用户决策问题中断。"""

    questions = interrupt_data.get("questions", [])
    if not questions:
        console.print("[red]错误：未收到问题数据[/red]")
        return None, session_approved

    # 显示问题详情
    show_question_form(questions)

    # 渲染交互式选择表单
    answers = select_options(questions)

    if not answers:
        console.print("[dim]已取消选择，使用默认回复...[/dim]")
        answers = {q.get("question", ""): q.get("options", [{}])[0].get("label", "") for q in questions if q.get("options")}

    # 显示用户的选择
    console.print()
    for q_text, a_text in answers.items():
        console.print(f"  [green]✓[/green] {q_text}: [cyan]{a_text}[/cyan]")

    # 用用户的选择恢复 graph
    usage = None
    new_interrupt = None
    for event in _process_stream(Command(resume=answers), config, thread_id, project_root):
        if event["type"] == "interrupt":
            new_interrupt = event["data"]
            usage = event["usage"]
        elif event["type"] == "done":
            usage = event["usage"]

    if new_interrupt:
        return _handle_approval(new_interrupt, config, thread_id, project_root, session_approved)
    return usage, session_approved


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


# --- /init 配置引导 ---


_PRESETS = {
    "deepseek": {
        "label": "DeepSeek",
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/v1",
    },
    "ali": {
        "label": "阿里通义 (Qwen)",
        "model": "qwen-plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "openai": {
        "label": "OpenAI",
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
    },
}

_API_KEY_ENV = "ECODE_API_KEY"


def cmd_init():
    """交互式配置引导，生成 .env 和 config.yaml。"""
    import os

    console.print(Panel("[bold]ecode 初始配置[/bold]", style="cyan", expand=False))
    console.print("选择 LLM 提供商：\n")

    options = [
        {"value": k, "label": f"{v['label']}  ({v['model']})"}
        for k, v in _PRESETS.items()
    ]
    options.append({"value": "custom", "label": "自定义 (OpenAI 兼容接口)"})

    choice = select_one(options, "选择提供商：")
    if not choice:
        console.print("[dim]已取消[/dim]")
        return False

    if choice == "custom":
        console.print("\n[dim]请输入自定义配置：[/dim]")
        base_url = prompt_input("API Base URL (如 https://api.example.com/v1)")
        if not base_url:
            console.print("[red]Base URL 不能为空[/red]")
            return False
        model = prompt_input("模型名称 (如 gpt-4o)")
        if not model:
            console.print("[red]模型名称不能为空[/red]")
            return False
        label = "自定义"
    else:
        preset = _PRESETS[choice]
        base_url = preset["base_url"]
        model = preset["model"]
        label = preset["label"]

    console.print(f"\n[dim]提供商: {label}[/dim]")
    console.print(f"[dim]模型: {model}[/dim]")
    console.print(f"[dim]地址: {base_url}[/dim]\n")

    api_key = prompt_input(f"请输入 API Key")
    if not api_key:
        console.print("[red]API Key 不能为空[/red]")
        return False

    # 生成文件路径
    project_root = os.getcwd()
    ecode_dir = os.path.join(project_root, ".ecode")
    os.makedirs(ecode_dir, exist_ok=True)
    env_path = os.path.join(ecode_dir, ".env")
    config_path = os.path.join(ecode_dir, "config.yaml")

    # 写 .env
    env_content = f"{_API_KEY_ENV}={api_key}\n"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(env_content)

    # 写 config.yaml
    config_content = f"""# ecode 配置文件
# 由 /init 命令自动生成，可手动编辑

llm:
  active: "{choice if choice != 'custom' else 'custom'}"
  configs:
    {"custom" if choice == "custom" else choice}:
      provider: openai
      model: {model}
      api_key_env: {_API_KEY_ENV}
      base_url: {base_url}
      temperature: 0
      streaming: true
      stream_usage: true
"""
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_content)

    console.print(f"\n[green]配置完成！[/green]")
    console.print(f"  已生成 [cyan].ecode/.env[/cyan] 和 [cyan].ecode/config.yaml[/cyan]")
    console.print(f"\n[dim]请重启 ecode 使配置生效。[/dim]")
    return True


def _check_first_run():
    """首次运行检测：无配置时自动触发 /init。"""
    import os
    from model import has_llm_config

    if has_llm_config():
        return

    console.print("[yellow]未检测到 LLM 配置，进入初始设置...[/yellow]\n")
    if cmd_init():
        console.print("\n[dim]配置完成，请重启 ecode。[/dim]")
        raise SystemExit(0)
    else:
        console.print("[red]未完成配置，ecode 无法启动。[/red]")
        console.print("[dim]你可以手动创建 .ecode/config.yaml（参考 config.yaml.example）或设置环境变量。[/dim]")
        raise SystemExit(1)


# --- Main entry point ---


def start_chat():
    set_slash_commands(["help", "init", "sessions", "switch", "new", "delete", "history", "clear", "exit", "mode", "plan", "storage"])

    _check_first_run()

    show_banner()

    thread_id = str(uuid.uuid4())
    project_root = __import__("os").getcwd().replace("\\", "/")
    permission_mode = "default"
    plan_mode = False
    session_approved = False  # 用户选择"全部同意"后，会话内所有工具自动批准

    # 注册 Shift+Tab 模式切换回调
    def _toggle_plan_mode():
        nonlocal plan_mode, permission_mode
        plan_mode = not plan_mode
        if plan_mode:
            permission_mode = "plan"
            console.print("\n[green]已进入计划模式 (Shift+Tab)[/green]")
        else:
            permission_mode = "default"
            console.print("\n[green]已退出计划模式 (Shift+Tab)[/green]")
        from agent import reset_tool_llm
        reset_tool_llm()

    set_mode_toggle_callback(_toggle_plan_mode)

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
            elif cmd == "/init":
                if cmd_init():
                    console.print("[dim]请重启 ecode 使新配置生效[/dim]")
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
            "session_approved": session_approved,
        }

        # 主对话循环：支持 Ctrl+C 补充信息后继续
        while True:
            interrupt_data = None
            usage = None
            gen = _process_stream(input_data, config, thread_id, project_root)
            try:
                for event in gen:
                    if event["type"] == "interrupt":
                        interrupt_data = event["data"]
                        usage = event["usage"]
                    elif event["type"] == "done":
                        usage = event["usage"]
            except KeyboardInterrupt:
                gen.close()
                console.print()
                supplement = supplement_input()
                if supplement:
                    console.print(f"[dim]已收到补充信息，继续运行...[/dim]")
                    input_data = {
                        "messages": [HumanMessage(content=supplement)],
                        "project_root": project_root,
                        "permission_mode": permission_mode,
                        "plan_mode": plan_mode,
                        "session_approved": session_approved,
                    }
                    continue  # 用补充信息重新启动流
                else:
                    console.print("[dim]已取消补充，中断当前任务。[/dim]")
                    break
            except Exception as err:
                gen.close()
                console.print(f"\n[red]错误：[/red]{err}")
                break

            # 正常结束或遇到 graph interrupt（审批）
            if interrupt_data:
                _, session_approved = _handle_approval(interrupt_data, config, thread_id, project_root, session_approved)
            break
        console.print()


def main():
    start_chat()


if __name__ == "__main__":
    main()
