"""流式结果传输基础设施。

为大型工具结果（大文件读取、长命令输出）提供分块流式传输支持。
使用 queue.Queue（线程安全）在工具执行线程和主事件循环之间传递流式事件。

设计原则：
- 零侵入：不改变已有工具的执行流程和返回值
- 仅附加：流式块仅用于 UI 展示，不进入 LLM 上下文
- 线程安全：使用 queue.Queue 跨线程传递
"""

import json
import queue
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── 流式块数据模型 ─────────────────────────────────────────────────────────

# 哪些工具的结果会被流式分块传输
STREAMING_TOOLS = {"view_file", "run_command", "search_code"}

# 单个块的最大字符数
DEFAULT_CHUNK_SIZE = 2000

# 命令工具实时轮询间隔（秒）
COMMAND_POLL_INTERVAL = 0.3

# 命令工具实时推送的最小行数积累
COMMAND_MIN_LINES_BEFORE_PUSH = 50


@dataclass
class StreamChunk:
    """一个流式数据块。"""
    tool_call_id: str
    tool_name: str
    content: str              # 块内容
    seq: int = 0              # 序号（从 0 开始）
    is_final: bool = False    # 是否为最终块
    total_chunks: int = 0     # 总块数（仅在 final=True 时有效）
    meta: dict = field(default_factory=dict)  # 额外元数据（行号、进度等）


class StreamingEvents:
    """线程安全的流式事件队列。

    使用方式：
        # 在工具执行线程中：
        StreamingEvents.push(chunk)

        # 在主事件循环中：
        events = StreamingEvents.drain()
        for event in events:
            ...
    """

    _queue: queue.Queue = queue.Queue()

    @classmethod
    def push(cls, chunk: StreamChunk):
        """推入一个流式块（线程安全）。"""
        cls._queue.put_nowait(chunk)

    @classmethod
    def drain(cls) -> list[StreamChunk]:
        """耗尽队列，返回当前所有未消费的块。"""
        chunks = []
        while not cls._queue.empty():
            try:
                chunks.append(cls._queue.get_nowait())
            except queue.Empty:
                break
        return chunks

    @classmethod
    def clear(cls):
        """清空队列（测试用）。"""
        while not cls._queue.empty():
            try:
                cls._queue.get_nowait()
            except queue.Empty:
                break


def _chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE) -> list[str]:
    """将文本按字符数拆分为多个块。

    在自然边界（换行符）处拆分，尽可能保证每块以完整行结束。
    """
    if not text:
        return [""]

    chunks = []
    pos = 0
    while pos < len(text):
        # 计算本块的结束位置
        end = pos + chunk_size
        if end >= len(text):
            # 最后一块
            chunks.append(text[pos:])
            break

        # 尝试在换行处断开
        newline_pos = text.rfind("\n", pos, end)
        if newline_pos > pos:
            end = newline_pos + 1  # 包含换行符
        else:
            # 没有换行符，在 chunk_size 处硬断
            pass

        chunks.append(text[pos:end])
        pos = end

    return chunks


def chunk_result(
    tool_call_id: str,
    tool_name: str,
    result_json: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> list[StreamChunk]:
    """将工具结果（JSON 字符串）拆分为多个 StreamChunk 并推入队列。

    拆分策略：
    - 解析 JSON 提取 "content" 或 "stdout" 字段（大块文本）
    - 将大文本拆分为多块
    - 每个块携带进度信息（行号/块数）

    Args:
        tool_call_id: 工具调用 ID
        tool_name: 工具名
        result_json: 工具返回的原始 JSON 字符串
        chunk_size: 每块最大字符数

    Returns:
        所有推入的 StreamChunk 列表
    """
    try:
        data = json.loads(result_json)
    except (json.JSONDecodeError, TypeError):
        # 无法解析的 JSON，不流式传输
        return []

    if not data.get("success", True):
        return []

    chunks: list[StreamChunk] = []

    if tool_name == "view_file":
        content = data.get("content", "")
        total_lines = data.get("total_lines", 0)
        path = data.get("path", "")
        if content and len(content) > chunk_size:
            parts = _chunk_text(content, chunk_size)
            total_chunks = len(parts)
            lines_per_chunk = max(1, total_lines // total_chunks) if total_lines else 0
            for i, part in enumerate(parts):
                start_line = i * lines_per_chunk + 1
                end_line = min((i + 1) * lines_per_chunk, total_lines) if total_lines else 0
                chunk = StreamChunk(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    content=part,
                    seq=i,
                    is_final=(i == total_chunks - 1),
                    total_chunks=total_chunks,
                    meta={
                        "path": path,
                        "total_lines": total_lines,
                        "showing_lines": f"{start_line}-{end_line}",
                    },
                )
                chunks.append(chunk)
                StreamingEvents.push(chunk)

    elif tool_name == "run_command":
        stdout = data.get("stdout", "")
        stderr = data.get("stderr", "")
        command = data.get("command", "")
        combined = stdout
        if stderr:
            combined += "\n" + stderr

        if combined and len(combined) > chunk_size:
            parts = _chunk_text(combined, chunk_size)
            total_chunks = len(parts)
            for i, part in enumerate(parts):
                chunk = StreamChunk(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    content=part,
                    seq=i,
                    is_final=(i == total_chunks - 1),
                    total_chunks=total_chunks,
                    meta={
                        "command": command,
                        "exit_code": data.get("exit_code"),
                    },
                )
                chunks.append(chunk)
                StreamingEvents.push(chunk)

    elif tool_name == "search_code":
        results = data.get("results", data.get("matches", []))
        total = data.get("count", data.get("total", len(results)))
        pattern = data.get("pattern", "")
        if results and len(results) > 20:  # 仅在结果较多时分块
            parts = _chunk_text(json.dumps(results, ensure_ascii=False), chunk_size)
            total_chunks = len(parts)
            for i, part in enumerate(parts):
                chunk = StreamChunk(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    content=part,
                    seq=i,
                    is_final=(i == total_chunks - 1),
                    total_chunks=total_chunks,
                    meta={
                        "pattern": pattern,
                        "total": total,
                    },
                )
                chunks.append(chunk)
                StreamingEvents.push(chunk)

    return chunks


def push_command_stream(
    tool_call_id: str,
    command: str,
    lines: list[str],
    is_final: bool = False,
    exit_code: int = -1,
):
    """从命令工具实时推送输出流。

    由 command_tools.py 的实时轮询线程调用。

    Args:
        tool_call_id: 工具调用 ID
        command: 命令名称（用于显示）
        lines: stdout 行列表（此次推送的新行）
        is_final: 是否为最终推送
        exit_code: 退出码（final=True 时有效）
    """
    if not lines and not is_final:
        return

    content = "".join(lines)
    if not content and not is_final:
        return

    chunk = StreamChunk(
        tool_call_id=tool_call_id,
        tool_name="run_command",
        content=content,
        is_final=is_final,
        meta={
            "command": command[:80],
            "exit_code": exit_code if is_final else None,
        },
    )
    StreamingEvents.push(chunk)