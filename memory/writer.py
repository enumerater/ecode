"""记忆写入器：保存和列出记忆。"""

import re
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 用户级记忆目录
USER_MEMORY_DIR = Path.home() / ".ecode"
USER_MEMORY_FILE = USER_MEMORY_DIR / "MEMORY.md"

# 项目级记忆文件（相对于项目根目录）
PROJECT_MEMORY_FILE = ".ecode/MEMORY.md"

# 记忆大小限制
MAX_LINES = 200
MAX_BYTES = 25 * 1024  # 25KB


def _slugify(text: str) -> str:
    """生成简单的 slug。"""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    return text[:50].strip('-')


def save_memory(
    content: str,
    memory_type: str = "project",
    name: str = "",
    scope: str = "project",
    project_root: str = ".",
) -> dict:
    """保存一条记忆到 MEMORY.md。

    Args:
        content: 记忆内容
        memory_type: 记忆类型 (user, feedback, project, reference)
        name: 记忆名称（可选，自动生成）
        scope: 保存范围 (user 或 project)
        project_root: 项目根目录

    Returns:
        {"success": True/False, ...}
    """
    if not content.strip():
        return {"success": False, "error": "记忆内容不能为空"}

    # 确定文件路径
    if scope == "user":
        memory_file = USER_MEMORY_FILE
        memory_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        memory_file = Path(project_root) / PROJECT_MEMORY_FILE
        memory_file.parent.mkdir(parents=True, exist_ok=True)

    # 生成名称
    if not name:
        name = _slugify(content[:50])
    if not name:
        name = f"memory-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # 构建新记忆条目
    date_str = datetime.now().strftime("%Y-%m-%d")
    new_entry = f"---\nname: {name}\ntype: {memory_type}\ndate: {date_str}\n---\n{content.strip()}\n"

    # 读取现有内容
    existing = ""
    if memory_file.exists():
        try:
            existing = memory_file.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"读取 MEMORY.md 失败: {e}")

    # 检查是否已存在同名记忆
    if f"name: {name}" in existing:
        # 更新现有记忆
        lines = existing.split("\n")
        new_lines = []
        skip = False
        for i, line in enumerate(lines):
            if line.strip() == "---" and i + 1 < len(lines) and f"name: {name}" in lines[i + 1]:
                skip = True
                continue
            if skip and line.strip() == "---":
                skip = False
                continue
            if not skip:
                new_lines.append(line)
        existing = "\n".join(new_lines)

    # 追加新记忆
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_content = existing + "\n" + new_entry

    # 检查大小限制
    lines = new_content.split("\n")
    if len(lines) > MAX_LINES:
        # 保留最新的记忆（文件末尾）
        new_content = "\n".join(lines[-MAX_LINES:])
        logger.warning(f"MEMORY.md 超过行数限制，已截断到最新 {MAX_LINES} 行")

    try:
        memory_file.write_text(new_content, encoding="utf-8")
        return {
            "success": True,
            "name": name,
            "type": memory_type,
            "scope": scope,
            "file": str(memory_file),
        }
    except Exception as e:
        return {"success": False, "error": f"写入失败: {e}"}


def list_memories(project_root: str = ".") -> dict:
    """列出所有记忆。

    Args:
        project_root: 项目根目录

    Returns:
        {"success": True, "memories": [...]}
    """
    from memory.loader import _load_file

    all_memories = []

    # 用户级记忆
    if USER_MEMORY_FILE.exists():
        user_memories = _load_file(USER_MEMORY_FILE)
        for mem in user_memories:
            all_memories.append({
                "name": mem.name,
                "type": mem.type,
                "content": mem.content[:100],
                "date": mem.date,
                "scope": "user",
            })

    # 项目级记忆
    project_path = Path(project_root) / PROJECT_MEMORY_FILE
    if project_path.exists():
        project_memories = _load_file(project_path)
        for mem in project_memories:
            all_memories.append({
                "name": mem.name,
                "type": mem.type,
                "content": mem.content[:100],
                "date": mem.date,
                "scope": "project",
            })

    return {
        "success": True,
        "memories": all_memories,
        "total": len(all_memories),
    }
