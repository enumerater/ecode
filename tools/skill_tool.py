"""Skill 工具：让 LLM 调用 skill。"""

from langchain_core.tools import tool

from skills.loader import substitute_args


@tool
def skill(name: str, arguments: str = "") -> str:
    """调用一个 skill（预定义的提示词模板）。

    当用户请求与某个 skill 描述匹配的操作时使用此工具。
    例如：用户说"帮我提交代码"时调用 commit skill。

    Args:
        name: skill 名称（如 "commit", "review", "test"）
        arguments: 传递给 skill 的参数（空格分隔）
    """
    from skills.store import skill_store

    s = skill_store.get_enabled(name)
    if not s:
        if skill_store.get(name):
            return f"skill '{name}' 已被禁用。用户可通过 /skills 命令启用。"
        available = ", ".join(skill_store.get_skill_names())
        return f"skill '{name}' 不存在。可用的 skill: {available}"

    # 参数替换
    content = substitute_args(s.content, arguments, s.arguments)

    return f"[Skill: {s.name}] {s.description}\n\n{content}"
