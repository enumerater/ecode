"""项目上下文加载器，读取并缓存 ecode.md。"""

from pathlib import Path
import logging

logger = logging.getLogger(__name__)

ECODE_MD_FILENAME = "ecode.md"
MAX_ECODE_MD_CHARS = 8000

# project_root -> content (or None)
_cache: dict[str, str | None] = {}


def load_project_context(project_root: str) -> str | None:
    """加载项目根目录下的 ecode.md，按 project_root 缓存。"""
    if project_root in _cache:
        return _cache[project_root]

    md_path = Path(project_root) / ECODE_MD_FILENAME
    if md_path.is_file():
        try:
            content = md_path.read_text(encoding="utf-8").strip()
            if len(content) > MAX_ECODE_MD_CHARS:
                logger.warning(
                    f"{ECODE_MD_FILENAME} 过长 ({len(content)} chars)，截断至 {MAX_ECODE_MD_CHARS}"
                )
                content = content[:MAX_ECODE_MD_CHARS]
            _cache[project_root] = content
            logger.info(f"Loaded {ECODE_MD_FILENAME} ({len(content)} chars)")
            return content
        except Exception as e:
            logger.warning(f"Failed to read {md_path}: {e}")
            _cache[project_root] = None
            return None
    else:
        _cache[project_root] = None
        return None


def clear_cache():
    """清空缓存（测试用）。"""
    _cache.clear()
