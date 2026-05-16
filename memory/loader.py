"""记忆加载器：从 MEMORY.md 文件加载记忆。"""

import logging
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# MEMORY.md 限制
MAX_LINES = 200
MAX_BYTES = 25 * 1024  # 25KB

# 用户级记忆目录
USER_MEMORY_DIR = Path.home() / ".ecode"
USER_MEMORY_FILE = USER_MEMORY_DIR / "MEMORY.md"

# 项目级记忆文件（相对于项目根目录）
PROJECT_MEMORY_FILE = ".ecode/MEMORY.md"


@dataclass
class Memory:
    """一条记忆。"""
    type: str      # user, feedback, project, reference
    content: str
    date: str = ""
    name: str = ""


def _parse_memory_file(content: str) -> list[Memory]:
    """解析 MEMORY.md 文件内容为记忆列表。

    格式：
    ---
    name: memory-slug
    type: user
    ---
    记忆内容...
    """
    memories = []
    current_meta = {}
    current_content = []
    in_frontmatter = False

    for line in content.split("\n"):
        if line.strip() == "---":
            if in_frontmatter:
                # 结束 frontmatter
                if current_meta:
                    memories.append(Memory(
                        type=current_meta.get("type", "project"),
                        content="\n".join(current_content).strip(),
                        date=current_meta.get("date", ""),
                        name=current_meta.get("name", ""),
                    ))
                current_meta = {}
                current_content = []
                in_frontmatter = False
            else:
                # 开始 frontmatter
                in_frontmatter = True
            continue

        if in_frontmatter:
            # 解析 YAML frontmatter
            if ":" in line:
                key, value = line.split(":", 1)
                current_meta[key.strip()] = value.strip()
        else:
            current_content.append(line)

    # 处理最后一个没有 closing --- 的记忆
    if current_content and not in_frontmatter:
        content_text = "\n".join(current_content).strip()
        if content_text:
            memories.append(Memory(
                type=current_meta.get("type", "project"),
                content=content_text,
                date=current_meta.get("date", ""),
                name=current_meta.get("name", ""),
            ))

    return memories


def _load_file(path: Path) -> list[Memory]:
    """加载单个 MEMORY.md 文件。"""
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding="utf-8")
        # 检查大小限制
        if len(content) > MAX_BYTES:
            logger.warning(f"MEMORY.md 超过大小限制 ({len(content)} > {MAX_BYTES}): {path}")
            content = content[:MAX_BYTES]
        return _parse_memory_file(content)
    except Exception as e:
        logger.warning(f"加载 MEMORY.md 失败: {path}: {e}")
        return []


def load_memories(project_root: str) -> str:
    """加载所有记忆并格式化为 system prompt 文本。

    Args:
        project_root: 项目根目录

    Returns:
        格式化的记忆文本，用于 system prompt
    """
    all_memories = []

    # 用户级记忆
    user_memories = _load_file(USER_MEMORY_FILE)
    if user_memories:
        all_memories.extend(user_memories)

    # 项目级记忆
    project_path = Path(project_root) / PROJECT_MEMORY_FILE
    project_memories = _load_file(project_path)
    if project_memories:
        all_memories.extend(project_memories)

    if not all_memories:
        return ""

    # 格式化为文本
    sections = []
    for mem in all_memories:
        if mem.type == "user":
            prefix = "用户偏好"
        elif mem.type == "feedback":
            prefix = "反馈/纠正"
        elif mem.type == "project":
            prefix = "项目上下文"
        elif mem.type == "reference":
            prefix = "参考资源"
        else:
            prefix = "记忆"

        if mem.name:
            sections.append(f"[{prefix}] {mem.name}\n{mem.content}")
        else:
            sections.append(f"[{prefix}]\n{mem.content}")

    return "\n\n---\n\n".join(sections)
