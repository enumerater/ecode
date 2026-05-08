import json
from langchain_core.tools import tool

# 特殊标记，execute_tools 节点会识别并触发实际压缩
COMPACT_SIGNAL = "__COMPACT__"


@tool
def compact(instruction: str = "") -> str:
    """压缩当前对话上下文，释放 token 空间。

    在以下情况调用：
    - 切换到一个完全不同的任务
    - 感觉上下文中有大量不再相关的历史信息
    - 接连完成多个独立小任务后
    - 上下文过长影响响应质量时

    Args:
        instruction: 可选的压缩指令，说明需要保留哪方面的上下文，
                     如"保留关于 auth.py 的修改记录"、"只保留当前任务的上下文"
    """
    signal = {"signal": COMPACT_SIGNAL}
    if instruction:
        signal["instruction"] = instruction
    return json.dumps(signal, ensure_ascii=False)
