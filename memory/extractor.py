"""记忆提取器：从对话中提取值得保存的记忆。"""

import json
import logging
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """分析以下对话，判断是否有值得跨会话保存的信息。

值得保存的类型：
- user: 用户的角色、偏好、技术栈、工作习惯
- feedback: 用户对 AI 的纠正或确认（如"不要这样做"、"对，就是这样"）
- project: 项目的重要上下文（截止日期、架构决策、团队约定）
- reference: 外部资源链接、文档地址、API 端点

不值得保存的：
- 一次性的代码修改细节
- 已经在代码或 git 历史中的信息
- 临时的调试信息
- 通用的编程知识

如果有值得保存的记忆，返回 JSON 数组：
[{{"type": "user|feedback|project|reference", "content": "记忆内容", "name": "可选名称"}}]

如果没有值得保存的，返回空数组：[]

只返回 JSON，不要其他文字。

对话：
{conversation}"""


def extract_memories(messages: list, llm, max_messages: int = 10) -> list[dict]:
    """从对话消息中提取记忆。

    Args:
        messages: 消息列表
        llm: LLM 实例
        max_messages: 最多分析的消息数

    Returns:
        记忆列表 [{"type": "...", "content": "...", "name": "..."}]
    """
    # 只分析最近的消息
    recent = messages[-max_messages:]
    if not recent:
        return []

    # 格式化对话
    conversation_parts = []
    for msg in recent:
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            conversation_parts.append(f"用户: {content[:300]}")
        elif hasattr(msg, 'content') and msg.content:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content:
                conversation_parts.append(f"AI: {content[:300]}")

    conversation = "\n".join(conversation_parts)
    if not conversation.strip():
        return []

    # 调用 LLM 提取
    prompt = EXTRACTION_PROMPT.format(conversation=conversation)
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        content = response.content if isinstance(response.content, str) else str(response.content)
        content = content.strip()

        # 解析 JSON
        if content.startswith("```"):
            # 移除 markdown 代码块
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        memories = json.loads(content)
        if isinstance(memories, list):
            # 验证格式
            valid = []
            for mem in memories:
                if isinstance(mem, dict) and "type" in mem and "content" in mem:
                    if mem["type"] in ("user", "feedback", "project", "reference"):
                        valid.append(mem)
            return valid
    except (json.JSONDecodeError, Exception) as e:
        logger.debug(f"记忆提取失败（可忽略）: {e}")

    return []
