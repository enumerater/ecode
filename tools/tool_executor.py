"""并行工具执行器。

参考 Claude Code 的 StreamingToolExecutor + toolOrchestration 模式：
- 连续的并发安全工具归为一批，用 asyncio.gather 并行执行
- 非并发安全工具单独一批，串行执行
- 错误传播：并发批次中某个工具失败时取消同批兄弟任务
"""

import json
import asyncio
import logging
from dataclasses import dataclass, field

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from tools.streaming import STREAMING_TOOLS, chunk_result

logger = logging.getLogger(__name__)

# 工具结果最大字符数（从8000降到4000，减少token消耗）
MAX_TOOL_RESULT_CHARS = 4000


@dataclass
class ToolCall:
    """待执行的工具调用。"""
    id: str
    name: str
    args: dict


@dataclass
class ToolBatch:
    """一批工具调用。concurrent=True 时并行执行，否则串行。"""
    calls: list[ToolCall] = field(default_factory=list)
    concurrent: bool = False


def partition_tool_calls(tool_calls: list[dict], tool_meta: dict[str, dict]) -> list[ToolBatch]:
    """将工具调用列表分区为可并行/需串行的批次。

    连续的并发安全工具归为一批（并行），非并发工具各自成批（串行）。

    Args:
        tool_calls: LLM 返回的 tool_calls 列表
        tool_meta: 工具名 -> {is_concurrency_safe, is_read_only, is_destructive}
    """
    if not tool_calls:
        return []

    batches: list[ToolBatch] = []
    current_batch = ToolBatch()

    for tc in tool_calls:
        name = tc["name"]
        meta = tool_meta.get(name, {})
        is_safe = meta.get("is_concurrency_safe", False)

        if is_safe:
            # 并发安全工具：追加到当前批次
            if not current_batch.concurrent and current_batch.calls:
                # 前面有非并发工具，先保存，开始新批次
                batches.append(current_batch)
                current_batch = ToolBatch(concurrent=True)
            current_batch.concurrent = True
            current_batch.calls.append(ToolCall(
                id=tc["id"], name=name, args=tc["args"],
            ))
        else:
            # 非并发工具：先保存之前的并发批次
            if current_batch.concurrent and current_batch.calls:
                batches.append(current_batch)
                current_batch = ToolBatch()
            # 非并发工具单独成批
            current_batch.calls.append(ToolCall(
                id=tc["id"], name=name, args=tc["args"],
            ))
            batches.append(current_batch)
            current_batch = ToolBatch()

    if current_batch.calls:
        batches.append(current_batch)

    return batches


def _truncate_result(result: str) -> str:
    """截断过大的工具结果。"""
    if len(result) > MAX_TOOL_RESULT_CHARS:
        keep = MAX_TOOL_RESULT_CHARS // 2
        return result[:keep] + f"\n... [结果已截断，原长 {len(result)} 字符] ...\n" + result[-keep:]
    return result


async def _run_tool_async(tool: BaseTool, args: dict, tool_name: str = "", tool_call_id: str = "") -> str:
    """在线程池中运行同步工具，避免阻塞事件循环。

    对于流式工具（view_file, run_command, search_code），在大结果时自动
    拆分并推入 StreamingEvents 队列，供 UI 层流式展示。
    """
    try:
        # 对 run_command 设置流式上下文，使其在轮询中能实时推流
        if tool_name == "run_command" and tool_call_id:
            try:
                from tools.command_tools import _set_streaming_ctx
                _set_streaming_ctx(tool_call_id)
            except ImportError:
                pass

        result = await asyncio.to_thread(tool.invoke, args)
        truncated = _truncate_result(result)
        # 推流式块：仅当工具是流式工具且结果较大时
        if tool_name and tool_call_id and tool_name in STREAMING_TOOLS:
            chunk_result(tool_call_id, tool_name, result)
        return truncated
    except Exception as e:
        return json.dumps({"success": False, "error": f"工具执行异常: {e}"}, ensure_ascii=False)


async def _execute_concurrent_batch(
    batch: ToolBatch,
    tool_map: dict[str, BaseTool],
    interrupt_fn=None,
    dangerous_tools: set[str] = None,
) -> list[ToolMessage]:
    """并发执行一批工具。"""
    dangerous_tools = dangerous_tools or set()

    # 先检查权限（串行），再并发执行
    tasks = []
    task_meta = []  # (ToolCall, 需要审批?)

    for tc in batch.calls:
        needs_approval = tc.name in dangerous_tools
        task_meta.append((tc, needs_approval))

    # 对需要审批的工具先 interrupt（串行）
    approved_calls = []
    for tc, needs_approval in task_meta:
        if needs_approval and interrupt_fn:
            approval = interrupt_fn({
                "type": "tool_approval",
                "tool_name": tc.name,
                "tool_call_id": tc.id,
                "args": tc.args,
            })
            if approval == "rejected":
                # 拒绝的工具直接生成结果
                continue
        approved_calls.append(tc)

    # 并发执行所有已批准的工具
    if not approved_calls:
        return []

    async_tasks = []
    for tc in approved_calls:
        tool = tool_map.get(tc.name)
        if tool is None:
            async_tasks.append(asyncio.coroutine(lambda: json.dumps(
                {"success": False, "error": f"未知工具: {tc.name}"},
                ensure_ascii=False,
            ))())
        else:
            async_tasks.append(_run_tool_async(tool, tc.args, tool_name=tc.name, tool_call_id=tc.id))

    results_raw = await asyncio.gather(*async_tasks, return_exceptions=True)

    results = []
    for tc, result in zip(approved_calls, results_raw):
        if isinstance(result, Exception):
            result = json.dumps(
                {"success": False, "error": f"工具执行异常: {result}"},
                ensure_ascii=False,
            )
        results.append(ToolMessage(content=result, tool_call_id=tc.id))

    return results


async def _execute_serial_batch(
    batch: ToolBatch,
    tool_map: dict[str, BaseTool],
    interrupt_fn=None,
    dangerous_tools: set[str] = None,
    permission_checker=None,
) -> list[ToolMessage]:
    """串行执行一批工具。"""
    dangerous_tools = dangerous_tools or set()
    results = []

    for tc in batch.calls:
        # 检查工具是否存在
        if tc.name not in tool_map:
            results.append(ToolMessage(
                content=json.dumps({
                    "success": False,
                    "error": f"未知工具: {tc.name}。可用工具: {', '.join(tool_map.keys())}",
                }, ensure_ascii=False),
                tool_call_id=tc.id,
            ))
            continue

        # ask_user_question: 先执行工具获取问题数据，再 interrupt 让用户回答
        if tc.name == "ask_user_question" and interrupt_fn:
            # 先执行工具获取问题数据
            try:
                tool_result = await _run_tool_async(tool_map[tc.name], tc.args)
            except Exception as e:
                results.append(ToolMessage(
                    content=json.dumps({"success": False, "error": f"工具执行异常: {e}"}, ensure_ascii=False),
                    tool_call_id=tc.id,
                ))
                continue

            try:
                signal_data = json.loads(tool_result)
            except (json.JSONDecodeError, TypeError):
                results.append(ToolMessage(content=tool_result, tool_call_id=tc.id))
                continue

            if signal_data.get("signal") == "ASK_USER_QUESTION":
                # interrupt 暂停 graph，将问题数据传给 CLI
                # 如果是 resume（graph 从 checkpoint 恢复），interrupt_fn 会直接返回用户的选择
                user_answers = interrupt_fn({
                    "type": "ask_user_question",
                    "questions": signal_data.get("questions", []),
                })
                # 用户的回答作为工具结果返回给 LLM
                results.append(ToolMessage(
                    content=json.dumps({
                        "success": True,
                        "answers": user_answers,
                    }, ensure_ascii=False),
                    tool_call_id=tc.id,
                ))
            else:
                results.append(ToolMessage(content=tool_result, tool_call_id=tc.id))
            continue

        # 权限检查
        permission = "ask"
        if permission_checker:
            permission = permission_checker(tc.name, tc.args)
        elif tc.name in dangerous_tools:
            permission = "ask"
        else:
            permission = "allow"

        if permission == "deny":
            results.append(ToolMessage(
                content=json.dumps({"success": False, "error": "权限拒绝：此操作被权限规则禁止"}, ensure_ascii=False),
                tool_call_id=tc.id,
            ))
            continue
        elif permission == "ask" and interrupt_fn:
            approval = interrupt_fn({
                "type": "tool_approval",
                "tool_name": tc.name,
                "tool_call_id": tc.id,
                "args": tc.args,
            })
            if approval == "rejected":
                results.append(ToolMessage(
                    content=json.dumps({"success": False, "error": "用户拒绝了此操作"}, ensure_ascii=False),
                    tool_call_id=tc.id,
                ))
                continue

        try:
            result = await _run_tool_async(tool_map[tc.name], tc.args, tool_name=tc.name, tool_call_id=tc.id)
            results.append(ToolMessage(content=result, tool_call_id=tc.id))
        except Exception as e:
            results.append(ToolMessage(
                content=json.dumps({"success": False, "error": f"工具执行异常: {e}"}, ensure_ascii=False),
                tool_call_id=tc.id,
            ))

    return results


async def _execute_concurrent_batch(
    batch: ToolBatch,
    tool_map: dict[str, BaseTool],
    interrupt_fn=None,
    dangerous_tools: set[str] = None,
    permission_checker=None,
) -> list[ToolMessage]:
    """并发执行一批工具。"""
    dangerous_tools = dangerous_tools or set()
    approved_calls = []

    for tc in batch.calls:
        # 权限检查
        permission = "ask"
        if permission_checker:
            permission = permission_checker(tc.name, tc.args)
        elif tc.name in dangerous_tools:
            permission = "ask"
        else:
            permission = "allow"

        if permission == "deny":
            # 拒绝的工具直接生成结果
            continue
        elif permission == "ask" and interrupt_fn:
            approval = interrupt_fn({
                "type": "tool_approval",
                "tool_name": tc.name,
                "tool_call_id": tc.id,
                "args": tc.args,
            })
            if approval == "rejected":
                continue
        approved_calls.append(tc)

    if not approved_calls:
        return []

    async_tasks = []
    for tc in approved_calls:
        tool = tool_map.get(tc.name)
        if tool is None:
            async_tasks.append(asyncio.coroutine(lambda: json.dumps(
                {"success": False, "error": f"未知工具: {tc.name}"},
                ensure_ascii=False,
            ))())
        else:
            async_tasks.append(_run_tool_async(tool, tc.args))

    results_raw = await asyncio.gather(*async_tasks, return_exceptions=True)

    results = []
    for tc, result in zip(approved_calls, results_raw):
        if isinstance(result, Exception):
            result = json.dumps(
                {"success": False, "error": f"工具执行异常: {result}"},
                ensure_ascii=False,
            )
        results.append(ToolMessage(content=result, tool_call_id=tc.id))

    return results


async def execute_tool_batches(
    tool_calls: list[dict],
    tool_map: dict[str, BaseTool],
    tool_meta: dict[str, dict],
    interrupt_fn=None,
    dangerous_tools: set[str] = None,
    permission_checker=None,
) -> list[ToolMessage]:
    """执行工具调用列表：分区 -> 批次顺序执行，批次内并发/串行。

    Args:
        tool_calls: LLM 返回的 tool_calls 列表
        tool_map: 工具名 -> BaseTool 实例
        tool_meta: 工具名 -> {is_concurrency_safe, is_read_only, is_destructive}
        interrupt_fn: 审批函数（LangGraph interrupt），可选
        dangerous_tools: 需要审批的工具名集合
        permission_checker: 权限检查函数 (tool_name, tool_args) -> 'allow'|'deny'|'ask'

    Returns:
        ToolMessage 列表，顺序与输入 tool_calls 一致
    """
    batches = partition_tool_calls(tool_calls, tool_meta)

    if not batches:
        return []

    all_results = []

    for batch in batches:
        if batch.concurrent and len(batch.calls) > 1:
            results = await _execute_concurrent_batch(
                batch, tool_map, interrupt_fn, dangerous_tools, permission_checker,
            )
        else:
            results = await _execute_serial_batch(
                batch, tool_map, interrupt_fn, dangerous_tools, permission_checker,
            )
        all_results.extend(results)

    return all_results
