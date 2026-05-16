"""Token 计数器：使用 tiktoken 进行精确 token 估算。"""

import logging
from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)

# tiktoken 编码器（懒加载）
_encoder = None


def _get_encoder():
    """获取 tiktoken 编码器（懒加载）。"""
    global _encoder
    if _encoder is None:
        try:
            import tiktoken
            _encoder = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            logger.warning("tiktoken 未安装，使用字符启发式估算")
            _encoder = False
    return _encoder


def estimate_tokens_tiktoken(text: str) -> int:
    """使用 tiktoken 精确估算 token 数。"""
    encoder = _get_encoder()
    if encoder and encoder is not False:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass
    # 回退到字符启发式
    return _estimate_tokens_heuristic(text)


def _estimate_tokens_heuristic(text: str) -> int:
    """字符启发式估算（回退方案）。"""
    cn_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - cn_chars
    return int(cn_chars * 1.5 + other_chars * 0.25) + 4


def estimate_messages_tokens(messages: list[BaseMessage]) -> int:
    """估算消息列表的 token 数。

    优先使用 tiktoken，不可用时回退到字符启发式。
    """
    total = 0
    for msg in messages:
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        total += estimate_tokens_tiktoken(content)

        # 工具调用的额外 token
        if hasattr(msg, 'tool_calls') and msg.tool_calls:
            for tc in msg.tool_calls:
                # 工具名和参数的 token
                args_str = str(tc.get("args", ""))
                total += estimate_tokens_tiktoken(tc.get("name", "")) + estimate_tokens_tiktoken(args_str) + 10

        # 工具结果的额外 token
        if hasattr(msg, 'tool_call_id') and msg.tool_call_id:
            total += 10

    return total
