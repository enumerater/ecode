"""子 Agent 工具：派生子 agent 执行聚焦任务。"""

import json
import logging
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

logger = logging.getLogger(__name__)

# 子 agent 可用的工具（只读工具）
SUBAGENT_TOOLS = ["view_file", "search_code", "list_files", "git_status", "git_diff", "git_log"]

# 子 agent 工具结果最大字符数（限制token消耗）
SUBAGENT_MAX_TOOL_RESULT_CHARS = 2000


def _truncate_subagent_result(result: str) -> str:
    """截断子 agent 工具结果。"""
    if len(result) > SUBAGENT_MAX_TOOL_RESULT_CHARS:
        keep = SUBAGENT_MAX_TOOL_RESULT_CHARS // 2
        return result[:keep] + f"\n... [结果已截断，原长 {len(result)} 字符] ...\n" + result[-keep:]
    return result


@tool
def run_agent(task: str, context: str = "") -> str:
    """派生一个子 agent 执行聚焦任务。

    子 agent 有独立的上下文，只能使用只读工具（查看文件、搜索代码、Git 查看）。
    适用于：
    - 分析代码库的某个部分
    - 搜索特定模式或实现
    - 理解代码架构

    Args:
        task: 子 agent 要执行的任务描述
        context: 可选的额外上下文信息
    """
    from model import llm
    from tools import ALL_TOOLS

    # 只选择只读工具
    tool_map = {t.name: t for t in ALL_TOOLS}
    subagent_tools = [tool_map[name] for name in SUBAGENT_TOOLS if name in tool_map]

    if not subagent_tools:
        return json.dumps({
            "success": False,
            "error": "没有可用的子 agent 工具",
        }, ensure_ascii=False)

    # 绑定工具
    sub_llm = llm.bind_tools(subagent_tools)

    # 构建子 agent 的系统提示（更简洁，减少token消耗）
    system_prompt = """你是代码分析助手。只使用只读工具分析代码，不要修改文件。
完成后提供简洁总结（不超过500字）。"""

    if context:
        system_prompt += f"\n\n上下文：{context[:500]}"  # 限制上下文长度

    # 执行子 agent（最多 3 轮工具调用，从5轮减少到3轮）
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=task[:1000]),  # 限制任务描述长度
    ]

    try:
        for _ in range(3):  # 从5轮减少到3轮
            response = sub_llm.invoke(messages)
            messages.append(response)

            # 如果没有工具调用，结束
            if not hasattr(response, 'tool_calls') or not response.tool_calls:
                break

            # 执行工具
            for tc in response.tool_calls:
                tool_name = tc["name"]
                if tool_name in tool_map:
                    try:
                        result = tool_map[tool_name].invoke(tc["args"])
                        # 截断工具结果，减少token消耗
                        truncated_result = _truncate_subagent_result(result)
                        messages.append(ToolMessage(content=truncated_result, tool_call_id=tc["id"]))
                    except Exception as e:
                        error_msg = json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
                        messages.append(ToolMessage(content=error_msg, tool_call_id=tc["id"]))

        # 提取最终回复
        final_response = messages[-1]
        content = final_response.content if hasattr(final_response, 'content') else str(final_response)

        # 限制返回结果长度
        if len(content) > 2000:
            content = content[:2000] + "\n... [结果已截断]"

        return json.dumps({
            "success": True,
            "task": task,
            "result": content,
            "messages_count": len(messages),
        }, ensure_ascii=False)

    except Exception as e:
        logger.error(f"子 agent 执行失败: {e}")
        return json.dumps({
            "success": False,
            "error": f"子 agent 执行失败: {e}",
        }, ensure_ascii=False)
