"""Skill 加载器：扫描目录、解析 SKILL.md、参数替换。"""

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# frontmatter 正则：匹配 --- 开头和结尾之间的 YAML 块
_FRONTMATTER_RE = re.compile(r"^---\s*\n([\s\S]*?)---\s*\n?([\s\S]*)$")


@dataclass
class Skill:
    """一个已加载的 skill。"""
    name: str
    description: str
    content: str  # markdown body（不含 frontmatter）
    source: str  # "builtin" | "user" | "project"
    path: str  # SKILL.md 文件路径
    argument_hint: str = ""
    arguments: list[str] = field(default_factory=list)
    user_invocable: bool = True
    disable_model_invocation: bool = False
    when_to_use: str = ""
    allowed_tools: str = ""


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML frontmatter + markdown body。

    Returns:
        (frontmatter_dict, body)
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text

    yaml_text = match.group(1)
    body = match.group(2).strip()

    # 简易 YAML 解析（不依赖 PyYAML）
    meta = {}
    current_key = None
    current_list = None

    for line in yaml_text.split("\n"):
        line = line.rstrip()
        if not line:
            continue

        # 列表项
        if line.startswith("  - ") and current_key:
            if current_list is None:
                current_list = []
            current_list.append(line[4:].strip().strip("'\""))
            continue

        # 保存之前的列表
        if current_list is not None and current_key:
            meta[current_key] = current_list
            current_list = None

        # key: value
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("'\"")
            current_key = key

            if value.lower() == "true":
                meta[key] = True
            elif value.lower() == "false":
                meta[key] = False
            elif value:
                meta[key] = value
            else:
                current_list = None  # 可能是多行值的开始
            continue

    # 保存最后的列表
    if current_list is not None and current_key:
        meta[current_key] = current_list

    return meta, body


def load_skill(skill_path: Path, source: str = "user") -> Skill | None:
    """从 SKILL.md 文件加载一个 skill。

    Args:
        skill_path: SKILL.md 文件路径
        source: 来源标识 ("builtin", "user", "project")
    """
    try:
        text = skill_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"无法读取 skill 文件 {skill_path}: {e}")
        return None

    meta, body = parse_frontmatter(text)
    if not body:
        logger.warning(f"skill 文件 {skill_path} 没有内容")
        return None

    # name 默认为父目录名
    name = meta.get("name", skill_path.parent.name)
    description = meta.get("description", "")

    # 解析 arguments
    raw_args = meta.get("arguments", [])
    if isinstance(raw_args, str):
        arguments = [a.strip() for a in raw_args.split(",")]
    elif isinstance(raw_args, list):
        arguments = raw_args
    else:
        arguments = []

    # allowed-tools 支持字符串或列表
    raw_tools = meta.get("allowed-tools", "")
    if isinstance(raw_tools, list):
        allowed_tools = ", ".join(raw_tools)
    else:
        allowed_tools = str(raw_tools)

    return Skill(
        name=name,
        description=description,
        content=body,
        source=source,
        path=str(skill_path),
        argument_hint=meta.get("argument-hint", ""),
        arguments=arguments,
        user_invocable=meta.get("user-invocable", True),
        disable_model_invocation=meta.get("disable-model-invocation", False),
        when_to_use=meta.get("when-to-use", "") or meta.get("when_to_use", ""),
        allowed_tools=allowed_tools,
    )


def substitute_args(content: str, args_str: str, arg_names: list[str]) -> str:
    """参数替换。

    替换规则：
    - $ARGUMENTS → 完整参数字符串
    - $0, $1, ... → 索引参数
    - $foo → 命名参数（如果 foo 在 arg_names 中）
    """
    args = args_str.split() if args_str else []

    # $ARGUMENTS → 完整参数
    content = content.replace("$ARGUMENTS", args_str)

    # $0, $1, ... → 索引参数
    for i, arg in enumerate(args):
        content = content.replace(f"${i}", arg)

    # $foo → 命名参数
    for i, name in enumerate(arg_names):
        value = args[i] if i < len(args) else ""
        content = content.replace(f"${name}", value)

    return content


def scan_skill_dir(dir_path: Path, source: str) -> list[Skill]:
    """扫描一个目录下的所有 skill。

    支持两种格式：
    - 目录格式: skills/commit/SKILL.md
    - 单文件格式: skills/commit.md（向后兼容）
    """
    skills = []

    if not dir_path.is_dir():
        return skills

    for entry in sorted(dir_path.iterdir()):
        if entry.is_dir():
            # 目录格式：skills/<name>/SKILL.md
            skill_file = entry / "SKILL.md"
            if skill_file.exists():
                skill = load_skill(skill_file, source)
                if skill:
                    skills.append(skill)
        elif entry.suffix == ".md" and entry.stem != "README":
            # 单文件格式：skills/<name>.md
            skill = load_skill(entry, source)
            if skill:
                skills.append(skill)

    return skills
