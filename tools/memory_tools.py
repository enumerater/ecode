"""记忆工具：让 agent 能主动保存和查看记忆。"""

import json
from langchain_core.tools import tool


@tool
def save_memory(content: str, memory_type: str = "project", name: str = "", scope: str = "project") -> str:
    """保存一条跨会话记忆。

    在以下情况调用：
    - 用户表达了偏好或纠正了你的做法
    - 用户分享了项目的重要上下文
    - 发现有价值的信息需要跨会话记住

    Args:
        content: 记忆内容
        memory_type: 记忆类型 (user, feedback, project, reference)
        name: 可选名称（自动生成如果留空）
        scope: 保存范围 (user=用户级, project=项目级)
    """
    from memory.writer import save_memory as _save_memory
    from tools import get_project_root

    result = _save_memory(
        content=content,
        memory_type=memory_type,
        name=name,
        scope=scope,
        project_root=get_project_root(),
    )
    return json.dumps(result, ensure_ascii=False)


@tool
def list_memories() -> str:
    """列出所有已保存的记忆。

    用于查看当前有哪些跨会话记忆。
    """
    from memory.writer import list_memories as _list_memories
    from tools import get_project_root

    result = _list_memories(project_root=get_project_root())
    return json.dumps(result, ensure_ascii=False)
