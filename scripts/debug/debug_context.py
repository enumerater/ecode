"""上下文调试工具：绕过命令行交互，直接调 graph.stream 看原始流数据。

用法:
    python debug_context.py [thread_id]

一问一答模式，每轮结束后显示上下文使用量分析。
"""
import sys
import os
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from context_manager import estimate_tokens, MAX_TOKENS


def fmt_token(n):
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def bar(pct, width=30):
    filled = int(width * pct / 100)
    empty = width - filled
    if pct < 60:
        color = "\033[32m"
    elif pct < 80:
        color = "\033[33m"
    else:
        color = "\033[31m"
    reset = "\033[0m"
    return f"{color}{'█' * filled}{'░' * empty}{reset} {pct:.1f}%"


def show_context_state(graph, config):
    """显示当前上下文使用量。"""
    state = graph.get_state(config)
    if not state or not state.values:
        print("  (无状态)")
        return
    values = state.values
    messages = values.get("messages", [])
    immutable_ctx = values.get("immutable_context", "")
    compact_summary = values.get("compact_summary", "")

    ctx_tokens = estimate_tokens([SystemMessage(content=immutable_ctx)]) if immutable_ctx else 0
    sum_tokens = estimate_tokens([SystemMessage(content=compact_summary)]) if compact_summary else 0
    compact_at = values.get("compact_at", 0)

    # 与 _build_messages 逻辑一致：compact_summary 替换旧消息
    if compact_summary and compact_at > 0 and compact_at < len(messages):
        new_messages = messages[compact_at:]
        new_msg_tokens = estimate_tokens(new_messages) if new_messages else 0
        total = ctx_tokens + sum_tokens + new_msg_tokens
        pct = min(total / MAX_TOKENS * 100, 100)
        print(f"\n  ┌─ 上下文状态 ─────────────────────────────────")
        print(f"  │ Messages: {len(messages)} 条 (旧 {compact_at} 条已压缩, 新 {len(new_messages)} 条)")
        print(f"  │ Immutable: {len(immutable_ctx)} chars  {fmt_token(ctx_tokens)} tokens")
        print(f"  │ Summary:   {len(compact_summary)} chars  {fmt_token(sum_tokens)} tokens")
        print(f"  │ 新消息:    {fmt_token(new_msg_tokens)} tokens")
        print(f"  │ 实际总计:  {fmt_token(total)} / {fmt_token(MAX_TOKENS)}  {bar(pct)}")
        print(f"  └──────────────────────────────────────────────")
    else:
        msg_tokens = estimate_tokens(messages) if messages else 0
        total = msg_tokens + ctx_tokens
        pct = min(total / MAX_TOKENS * 100, 100)
        print(f"\n  ┌─ 上下文状态 ─────────────────────────────────")
        print(f"  │ Messages: {len(messages)} 条  {fmt_token(msg_tokens)} tokens")
        print(f"  │ Immutable: {len(immutable_ctx)} chars  {fmt_token(ctx_tokens)} tokens")
        print(f"  │ 总计: {fmt_token(total)} / {fmt_token(MAX_TOKENS)}  {bar(pct)}")
        print(f"  └──────────────────────────────────────────────")


def show_state_keys(values):
    """显示 state 中所有 key 及其大小。"""
    print(f"\n  ┌─ State Keys ──────────────────────────────────")
    for k, v in values.items():
        if k == "messages":
            print(f"  │ {k}: list[{len(v)}]")
        elif isinstance(v, str):
            print(f"  │ {k}: str({len(v)} chars)")
        elif isinstance(v, (int, float, bool)):
            print(f"  │ {k}: {v}")
        elif isinstance(v, list):
            print(f"  │ {k}: list[{len(v)}]")
        elif isinstance(v, dict):
            print(f"  │ {k}: dict({list(v.keys())[:5]})")
        else:
            print(f"  │ {k}: {type(v).__name__}")
    print(f"  └──────────────────────────────────────────────")


def run_one_turn(graph, config, user_input):
    """执行一轮对话，打印所有流事件。"""
    input_data = {
        "messages": [HumanMessage(content=user_input)],
        "project_root": os.getcwd().replace("\\", "/"),
        "permission_mode": "default",
        "plan_mode": False,
        "session_approved": True,
    }

    print(f"\n{'─' * 60}")
    print(f"  >>> 发送: {user_input[:80]}")
    print(f"{'─' * 60}")

    accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    event_count = 0
    ai_content_parts = []
    tool_calls_seen = []
    start_time = time.time()

    for chunk in graph.stream(
        input_data,
        stream_mode=["messages", "updates"],
        config=config,
        version="v2",
    ):
        event_count += 1

        # 解析 chunk
        if isinstance(chunk, dict):
            typ = chunk.get("type", "")
            data = chunk.get("data")
        elif isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
            typ, data = chunk
        else:
            print(f"  [?] 未知 chunk 格式: {type(chunk)}")
            continue

        # ── updates 流 ──
        if typ == "updates" and isinstance(data, dict):
            if "__interrupt__" in data:
                print(f"\n  [INTERRUPT] 中断触发")
                for intr in data["__interrupt__"]:
                    print(f"    中断值: {str(intr.value)[:200]}")
                break

            for node_name, node_data in data.items():
                if not isinstance(node_data, dict):
                    print(f"  [updates] {node_name}: {type(node_data).__name__}")
                    continue

                print(f"\n  [updates] 节点: {node_name}")

                # messages
                if "messages" in node_data:
                    for msg in node_data["messages"]:
                        if isinstance(msg, AIMessage):
                            content = msg.content
                            if isinstance(content, list):
                                content = "".join(
                                    b.get("text", "") if isinstance(b, dict) else str(b)
                                    for b in content
                                )
                            if content:
                                ai_content_parts.append(content)
                                print(f"    AI 内容: {content[:200]}{'...' if len(content) > 200 else ''}")
                            if getattr(msg, 'tool_calls', None):
                                for tc in msg.tool_calls:
                                    tool_calls_seen.append(tc)
                                    args_str = json.dumps(tc.get("args", {}), ensure_ascii=False)
                                    print(f"    工具调用: {tc.get('name')}({args_str[:150]})")
                        elif isinstance(msg, ToolMessage):
                            preview = msg.content[:150] if isinstance(msg.content, str) else str(msg.content)[:150]
                            print(f"    工具结果[{msg.tool_call_id[:8]}]: {preview}")
                        elif isinstance(msg, SystemMessage):
                            print(f"    System: {str(msg.content)[:100]}")
                        elif isinstance(msg, HumanMessage):
                            print(f"    Human: {str(msg.content)[:100]}")

                # usage
                if "usage" in node_data:
                    accumulated_usage = node_data["usage"]
                    print(f"    Usage: {accumulated_usage}")

                # 其他 keys
                other_keys = [k for k in node_data.keys() if k not in ("messages", "usage")]
                for k in other_keys:
                    v = node_data[k]
                    if isinstance(v, str):
                        print(f"    {k}: {v[:100]}")
                    elif isinstance(v, (int, float, bool)):
                        print(f"    {k}: {v}")
                    elif isinstance(v, list):
                        print(f"    {k}: list[{len(v)}]")
                    elif isinstance(v, dict):
                        print(f"    {k}: dict({list(v.keys())[:5]})")

        # ── messages 流 ──
        elif typ == "messages":
            try:
                msg, metadata = data
                node = metadata.get("langgraph_node", "")
                if isinstance(msg, AIMessage):
                    tc = getattr(msg, 'tool_calls', None)
                    if tc:
                        for t in tc:
                            args_str = json.dumps(t.get("args", {}), ensure_ascii=False)
                            print(f"  [messages] AI -> {t.get('name')}({args_str[:150]})")
                    if msg.content:
                        content = msg.content
                        if isinstance(content, list):
                            content = "".join(
                                b.get("text", "") if isinstance(b, dict) else str(b)
                                for b in content
                            )
                        if content:
                            # 流式 chunk，不换行打印
                            print(content, end="", flush=True)
                elif isinstance(msg, ToolMessage):
                    preview = msg.content[:100] if isinstance(msg.content, str) else str(msg.content)[:100]
                    print(f"\n  [messages] 工具结果[{msg.tool_call_id[:8]}]: {preview}")
            except Exception as e:
                print(f"  [messages] 解析错误: {e}")
        else:
            print(f"  [?] 未知类型: {typ}")

    elapsed = time.time() - start_time
    print(f"\n{'─' * 60}")
    print(f"  轮次结束 | 事件数: {event_count} | 耗时: {elapsed:.1f}s")
    print(f"  累计 Usage: {accumulated_usage}")
    if ai_content_parts:
        full_response = "".join(ai_content_parts)
        print(f"  AI 回复总长度: {len(full_response)} chars")
    if tool_calls_seen:
        print(f"  工具调用: {[tc.get('name') for tc in tool_calls_seen]}")
    print(f"{'─' * 60}")


def main():
    import uuid
    from agent import build_graph

    graph = build_graph()
    project_root = os.getcwd().replace("\\", "/")

    if len(sys.argv) > 1:
        thread_id = sys.argv[1]
    else:
        thread_id = str(uuid.uuid4())
        print(f"新建会话: {thread_id}")

    config = {"configurable": {"thread_id": thread_id}}

    # 显示初始状态
    state = graph.get_state(config)
    if state and state.values:
        show_state_keys(state.values)
        show_context_state(graph, config)
    else:
        print(f"  会话 {thread_id[:16]} 无历史数据（新会话）")

    print(f"\n输入消息进行调试，输入 quit 退出，输入 /state 查看状态，输入 /compact 测试压缩")
    print(f"{'=' * 60}")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出")
            break

        if not user_input:
            continue
        if user_input == "quit":
            break

        if user_input == "/state":
            state = graph.get_state(config)
            if state and state.values:
                show_state_keys(state.values)
                show_context_state(graph, config)
            continue

        if user_input == "/compact":
            state = graph.get_state(config)
            if state and state.values:
                messages = state.values.get("messages", [])
                print(f"  压缩 {len(messages)} 条消息...")
                try:
                    import model as _model
                    from context_manager import manual_compact
                    llm = _model.create_llm()
                    _, summary = manual_compact(messages, llm)
                    if summary:
                        graph.update_state(config, {
                            "compact_summary": summary,
                            "compact_at": len(messages),
                        })
                        print(f"  压缩完成，摘要: {summary[:200]}")
                    else:
                        print(f"  压缩失败: 无摘要")
                except Exception as e:
                    print(f"  压缩失败: {e}")
                    import traceback
                    traceback.print_exc()
            continue

        run_one_turn(graph, config, user_input)
        show_context_state(graph, config)


if __name__ == "__main__":
    main()
