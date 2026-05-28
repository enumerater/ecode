"""六层上下文压缩管理器。

Layer 1: micro_compact — 每轮自动，替换旧工具结果为占位符
Layer 2: auto_compact  — token 超阈值时调用 LLM 生成摘要
Layer 3: Manual compact — Agent 通过 compact 工具主动触发（见 tools/context_tools.py）
Layer 4: reactive_compact — prompt-too-long 错误时自动触发
Layer 5: snip_compact — 移除对话中间大段内容，保留首尾
Layer 6: truncate_large_results — 截断大段工具输出（新增）
"""

import json
import copy
import logging
from langchain_core.messages import (
    BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage,
)

logger = logging.getLogger(__name__)

# ── 配置 ──────────────────────────────────────────────────────────────
MAX_TOKENS = 80000            # 触发 Auto-Compact 的 token 阈值（从200k降到80k）
KEEP_RECENT_MESSAGES = 15     # 压缩时保留的最近消息数（从20降到15）
MICRO_COMPACT_AFTER_TURNS = 1  # N 轮前的工具结果触发微压缩（从3改为1，更积极压缩）
SUMMARY_MAX_CHARS = 500       # 摘要最大字符数

SUMMARY_PROMPT = """请将以下对话历史压缩为简洁摘要，保留：
- 用户的核心需求和目标
- 已完成的关键操作和结果
- 当前进行中的任务状态
- 重要的上下文信息（文件路径、变量名等）

丢弃：
- 详细的工具输出内容
- 重复的操作记录
- 不影响后续对话的中间步骤

输出格式：一段连贯的中文摘要，不超过 {max_chars} 字。

{instruction_section}

对话历史：
{history}"""


# ── Token 估算 ────────────────────────────────────────────────────────

def estimate_tokens(messages: list[BaseMessage]) -> int:
    """估算 token 数，优先使用 tiktoken，回退到字符启发式。"""
    try:
        from context.token_counter import estimate_messages_tokens
        return estimate_messages_tokens(messages)
    except ImportError:
        pass

    # 回退：字符启发式
    total = 0
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        cn_chars = sum(1 for c in content if '一' <= c <= '鿿')
        other_chars = len(content) - cn_chars
        total += int(cn_chars * 1.5 + other_chars * 0.25) + 4
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            total += len(msg.tool_calls) * 20
        if hasattr(msg, 'tool_call_id') and msg.tool_call_id:
            total += 10
    return total


# ── Layer 1: Micro-Compact ───────────────────────────────────────────

def _make_tool_placeholder(msg: ToolMessage) -> str:
    """根据工具结果内容生成一行占位符。"""
    try:
        data = json.loads(msg.content)
    except (json.JSONDecodeError, TypeError):
        return "[工具结果已压缩]"

    success = data.get("success", True)
    status = "成功" if success else "失败"

    # run_command
    if "command" in data and "exit_code" in data:
        cmd = data["command"][:60]
        return f"[命令已执行: {cmd}, {status}]"

    # search_code
    if "pattern" in data and "total" in data:
        pattern = data["pattern"][:40]
        return f"[搜索完成: {pattern}, 找到 {data['total']} 个匹配]"

    # list_files
    if "total_files" in data:
        return f"[文件列表已列出: {data.get('total_files', 0)} 个文件, {data.get('total_dirs', 0)} 个目录]"

    # view_file — 压缩为摘要（保留文件路径和行数信息）
    if "content" in data and "total_lines" in data:
        path = data.get("path", "未知文件")
        total = data.get("total_lines", 0)
        showing = data.get("showing_lines", "")
        content = data.get("content", "")
        # 计算内容行数
        content_lines = content.count('\n') + 1 if content else 0
        return f"[文件已读取: {path}, 共{total}行, 显示{showing}, 内容{content_lines}行已省略]"

    # edit_file / write_file / create_file / create_directory
    if "path" in data:
        path = data["path"]
        if "lines_removed" in data or "lines_added" in data:
            return f"[文件已修改: {path}]"
        if "bytes_written" in data:
            return f"[文件已写入: {path}]"
        return f"[文件操作完成: {path}]"

    return f"[工具执行{status}]"


def _find_turn_boundaries(messages: list[BaseMessage]) -> list[int]:
    """找到每轮对话的起始索引（HumanMessage 的位置）。"""
    boundaries = []
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            boundaries.append(i)
    return boundaries


def micro_compact(messages: list[BaseMessage], after_turns: int = MICRO_COMPACT_AFTER_TURNS) -> list[BaseMessage]:
    """Layer 1: 将 N 轮前的工具结果替换为占位符。"""
    if len(messages) < 2:
        return messages

    boundaries = _find_turn_boundaries(messages)
    if len(boundaries) <= after_turns:
        return messages  # 轮数不够，不需要压缩

    # 找到 N 轮前的切割点
    cutoff_idx = boundaries[-after_turns] if len(boundaries) >= after_turns else 0

    # 需要一个 map: tool_call_id -> AIMessage（用于查找工具名）
    tool_call_id_to_ai = {}
    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_call_id_to_ai[tc["id"]] = tc["name"]

    result = []
    for i, msg in enumerate(messages):
        if i < cutoff_idx and isinstance(msg, ToolMessage):
            placeholder = _make_tool_placeholder(msg)
            if placeholder is None:
                result.append(msg)  # view_file 等保留原内容
            else:
                # 创建一个轻量的 ToolMessage 替身
                result.append(ToolMessage(
                    content=placeholder,
                    tool_call_id=msg.tool_call_id,
                ))
        else:
            result.append(msg)

    return result


# ── Layer 2: Auto-Compact ────────────────────────────────────────────

def _format_history_for_summary(messages: list[BaseMessage]) -> str:
    """将消息列表格式化为可读的摘要输入。"""
    parts = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            parts.append(f"用户: {content[:200]}")
        elif isinstance(msg, AIMessage):
            if msg.content:
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                parts.append(f"AI: {content[:200]}")
            if hasattr(msg, 'tool_calls') and msg.tool_calls:
                for tc in msg.tool_calls:
                    args_str = json.dumps(tc["args"], ensure_ascii=False)[:80]
                    parts.append(f"AI 调用: {tc['name']}({args_str})")
        elif isinstance(msg, ToolMessage):
            # 已经被 micro_compact 替换过的占位符直接用
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content.startswith("[") and content.endswith("]"):
                parts.append(content)
            else:
                try:
                    data = json.loads(content)
                    success = data.get("success", True)
                    parts.append(f"工具结果: {'成功' if success else '失败'}")
                except (json.JSONDecodeError, TypeError):
                    parts.append(f"工具结果: {content[:100]}")
    return "\n".join(parts)


def auto_compact(
    messages: list[BaseMessage],
    llm,
    instruction: str = "",
    max_tokens: int = MAX_TOKENS,
    keep_recent: int = KEEP_RECENT_MESSAGES,
) -> tuple[list[BaseMessage], str | None]:
    """Layer 2: token 超阈值时调用 LLM 生成摘要。

    Returns:
        (压缩后的消息列表, 摘要文本 或 None)
    """
    estimated = estimate_tokens(messages)
    if estimated <= max_tokens:
        return messages, None

    logger.info(f"Auto-Compact 触发: 估算 {estimated} tokens > 阈值 {max_tokens}")

    # 分割：旧消息 + 最近消息
    split_point = max(1, len(messages) - keep_recent)
    old_messages = messages[:split_point]
    recent_messages = messages[split_point:]

    # 生成摘要
    history_text = _format_history_for_summary(old_messages)
    instruction_section = f"特别关注以下方面：{instruction}" if instruction else ""

    prompt = SUMMARY_PROMPT.format(
        max_chars=SUMMARY_MAX_CHARS,
        instruction_section=instruction_section,
        history=history_text,
    )

    try:
        summary_response = llm.invoke([HumanMessage(content=prompt)])
        summary_text = summary_response.content if isinstance(summary_response.content, str) else str(summary_response.content)
    except Exception as e:
        logger.error(f"Auto-Compact 摘要生成失败: {e}")
        # 降级：直接截断
        return messages[-keep_recent:], None

    logger.info(f"Auto-Compact 完成: {len(messages)} 条消息 -> {len(recent_messages) + 1} 条")

    # 构建压缩后的消息列表
    summary_msg = SystemMessage(content=f"[对话历史摘要]\n{summary_text}")
    return [summary_msg] + recent_messages, summary_text


# ── Layer 3: Manual Compact（工具调用入口）────────────────────────────

def manual_compact(
    messages: list[BaseMessage],
    llm,
    instruction: str = "",
) -> tuple[list[BaseMessage], str]:
    """Layer 3: Agent 主动调用的压缩。

    Returns:
        (压缩后的消息列表, 摘要文本)
    """
    keep_recent = min(KEEP_RECENT_MESSAGES, len(messages) // 2)
    keep_recent = max(keep_recent, 4)  # 至少保留 4 条

    old_messages = messages[:-keep_recent] if len(messages) > keep_recent else messages[:1]
    recent_messages = messages[-keep_recent:] if len(messages) > keep_recent else messages[1:]

    history_text = _format_history_for_summary(old_messages)
    instruction_section = f"特别关注以下方面：{instruction}" if instruction else ""

    prompt = SUMMARY_PROMPT.format(
        max_chars=SUMMARY_MAX_CHARS,
        instruction_section=instruction_section,
        history=history_text,
    )

    try:
        summary_response = llm.invoke([HumanMessage(content=prompt)])
        summary_text = summary_response.content if isinstance(summary_response.content, str) else str(summary_response.content)
    except Exception as e:
        logger.error(f"Manual Compact 摘要生成失败: {e}")
        return recent_messages, f"压缩失败: {e}"

    summary_msg = SystemMessage(content=f"[对话历史摘要]\n{summary_text}")
    return [summary_msg] + recent_messages, summary_text


# ── Layer 4: Reactive Compact（prompt-too-long 错误时触发）─────────────

def reactive_compact(
    messages: list[BaseMessage],
    llm,
    keep_recent: int = KEEP_RECENT_MESSAGES,
) -> tuple[list[BaseMessage], str | None]:
    """Layer 4: 当 prompt-too-long 错误发生时自动触发压缩。

    强制压缩，不检查 token 阈值。

    Returns:
        (压缩后的消息列表, 摘要文本 或 None)
    """
    if len(messages) <= 4:
        return messages, None

    logger.info(f"Reactive Compact 触发: {len(messages)} 条消息")

    # 分割：旧消息 + 最近消息
    split_point = max(1, len(messages) - keep_recent)
    old_messages = messages[:split_point]
    recent_messages = messages[split_point:]

    # 生成摘要
    history_text = _format_history_for_summary(old_messages)
    prompt = SUMMARY_PROMPT.format(
        max_chars=SUMMARY_MAX_CHARS,
        instruction_section="",
        history=history_text,
    )

    try:
        summary_response = llm.invoke([HumanMessage(content=prompt)])
        summary_text = summary_response.content if isinstance(summary_response.content, str) else str(summary_response.content)
    except Exception as e:
        logger.error(f"Reactive Compact 摘要生成失败: {e}")
        # 降级：直接截断
        return messages[-keep_recent:], None

    logger.info(f"Reactive Compact 完成: {len(messages)} 条消息 -> {len(recent_messages) + 1} 条")
    summary_msg = SystemMessage(content=f"[对话历史摘要]\n{summary_text}")
    return [summary_msg] + recent_messages, summary_text


# ── Layer 5: Snip Compact（移除中间大段内容）──────────────────────────

def snip_compact(
    messages: list[BaseMessage],
    llm,
    keep_first: int = 3,
    keep_last: int = 10,
) -> tuple[list[BaseMessage], str | None]:
    """Layer 5: 移除对话中间的大段内容，保留首尾。

    适用于对话很长但中间内容不再相关的情况。

    Args:
        messages: 消息列表
        llm: LLM 实例
        keep_first: 保留前 N 条消息
        keep_last: 保留后 N 条消息

    Returns:
        (压缩后的消息列表, 摘要文本 或 None)
    """
    total = len(messages)
    if total <= keep_first + keep_last + 5:
        return messages, None  # 消息太少，不需要 snip

    logger.info(f"Snip Compact 触发: {total} 条消息，保留前 {keep_first} + 后 {keep_last}")

    first_part = messages[:keep_first]
    middle_part = messages[keep_first:total - keep_last]
    last_part = messages[total - keep_last:]

    # 对中间部分生成摘要
    history_text = _format_history_for_summary(middle_part)
    prompt = SUMMARY_PROMPT.format(
        max_chars=SUMMARY_MAX_CHARS,
        instruction_section="",
        history=history_text,
    )

    try:
        summary_response = llm.invoke([HumanMessage(content=prompt)])
        summary_text = summary_response.content if isinstance(summary_response.content, str) else str(summary_response.content)
    except Exception as e:
        logger.error(f"Snip Compact 摘要生成失败: {e}")
        # 降级：直接拼接首尾
        return first_part + last_part, None

    summary_msg = SystemMessage(content=f"[中间对话摘要]\n{summary_text}")
    result = first_part + [summary_msg] + last_part

    logger.info(f"Snip Compact 完成: {total} 条消息 -> {len(result)} 条")
    return result, summary_text


# ── Layer 6: Truncate Large Results（截断大段工具输出）────────────────

# 工具结果最大字符数（超过则截断）
MAX_TOOL_RESULT_CHARS = 3000


def truncate_large_results(messages: list[BaseMessage], max_chars: int = MAX_TOOL_RESULT_CHARS) -> list[BaseMessage]:
    """Layer 6: 截断大段的工具输出内容。

    对于当前轮次之前的工具结果，如果内容过长则截断为摘要。
    当前轮次的工具结果保留原内容，确保 AI 能看到最新结果。

    Args:
        messages: 消息列表
        max_chars: 工具结果最大字符数

    Returns:
        处理后的消息列表
    """
    if len(messages) < 2:
        return messages

    # 找到最后一个 HumanMessage 的位置（当前轮次的开始）
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break

    if last_human_idx < 0:
        return messages

    result = []
    for i, msg in enumerate(messages):
        # 只处理当前轮次之前的 ToolMessage
        if i < last_human_idx and isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            # 如果内容过长，截断为摘要
            if len(content) > max_chars:
                # 尝试解析 JSON 获取工具类型
                try:
                    data = json.loads(content)
                    if "content" in data and "total_lines" in data:
                        # view_file 结果
                        path = data.get("path", "未知文件")
                        total = data.get("total_lines", 0)
                        truncated_content = content[:500] + f"\n... [已截断，原长 {len(content)} 字符]"
                        new_data = {
                            "success": True,
                            "path": path,
                            "total_lines": total,
                            "content_preview": truncated_content,
                            "truncated": True,
                        }
                        result.append(ToolMessage(
                            content=json.dumps(new_data, ensure_ascii=False),
                            tool_call_id=msg.tool_call_id,
                        ))
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
                # 其他类型的结果直接截断
                truncated = content[:max_chars // 2] + f"\n... [已截断，原长 {len(content)} 字符] ...\n" + content[-max_chars // 2:]
                result.append(ToolMessage(
                    content=truncated,
                    tool_call_id=msg.tool_call_id,
                ))
                continue
        result.append(msg)

    return result
