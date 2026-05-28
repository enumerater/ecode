"""Git 集成工具。

提供 5 个核心 Git 操作工具：
- git_status: 工作树状态
- git_diff: 差异查看
- git_log: 提交历史
- git_commit: 创建提交
- git_blame: 文件逐行修改信息
"""

import json
import subprocess
from langchain_core.tools import tool


def _run_git(args: list[str], cwd: str) -> dict:
    """执行 git 命令并返回结构化结果。"""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "git 命令超时 (30s)"}
    except FileNotFoundError:
        return {"success": False, "error": "git 未安装或不在 PATH 中"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def git_status() -> str:
    """显示 Git 工作树状态（分支、暂存、修改、未跟踪文件）。

    安全工具，可并发执行。
    """
    from tools import get_project_root
    cwd = get_project_root()

    # 获取当前分支
    branch_result = _run_git(["branch", "--show-current"], cwd)
    branch = branch_result.get("stdout", "unknown") if branch_result.get("success") else "unknown"

    # 获取状态
    status_result = _run_git(["status", "--porcelain", "-b"], cwd)
    if not status_result.get("success"):
        return json.dumps(status_result, ensure_ascii=False)

    lines = status_result["stdout"].split("\n") if status_result["stdout"] else []

    staged = []
    modified = []
    untracked = []

    for line in lines[1:]:  # 跳过第一行（分支信息）
        if not line.strip():
            continue
        status_code = line[:2]
        file_path = line[3:].strip()

        if status_code[0] in ("A", "M", "D", "R", "C"):
            staged.append({"status": status_code[0], "file": file_path})
        if status_code[1] == "M":
            modified.append(file_path)
        elif status_code == "??":
            untracked.append(file_path)

    return json.dumps({
        "success": True,
        "branch": branch,
        "staged": staged,
        "modified": modified,
        "untracked": untracked,
        "is_clean": not staged and not modified and not untracked,
    }, ensure_ascii=False)


@tool
def git_diff(path: str = "", cached: bool = False) -> str:
    """显示 Git 差异。

    Args:
        path: 可选，指定文件路径查看特定文件的差异
        cached: 是否查看暂存区差异（--cached）

    安全工具，可并发执行。
    """
    from tools import get_project_root
    cwd = get_project_root()

    args = ["diff", "--no-color"]
    if cached:
        args.append("--cached")
    if path:
        args.extend(["--", path])

    result = _run_git(args, cwd)
    if not result.get("success"):
        return json.dumps(result, ensure_ascii=False)

    diff = result.get("stdout", "")
    # 截断过长的 diff（减少token消耗）
    if len(diff) > 5000:  # 从10000降到5000
        diff = diff[:2500] + f"\n\n... [diff 已截断，原长 {len(diff)} 字符] ...\n\n" + diff[-2500:]

    return json.dumps({
        "success": True,
        "diff": diff,
        "has_changes": bool(diff.strip()),
        "cached": cached,
        "path": path or None,
    }, ensure_ascii=False)


@tool
def git_log(count: int = 10, path: str = "") -> str:
    """显示 Git 提交历史。

    Args:
        count: 显示的提交数量，默认 10
        path: 可选，过滤特定文件的提交

    安全工具，可并发执行。
    """
    from tools import get_project_root
    cwd = get_project_root()

    count = min(max(count, 1), 20)  # 从50降到20，减少token消耗
    args = [
        "log", f"--max-count={count}",
        "--format=%H|%an|%at|%s",  # 移除email字段，减少输出
        "--no-color",
    ]
    if path:
        args.extend(["--", path])

    result = _run_git(args, cwd)
    if not result.get("success"):
        return json.dumps(result, ensure_ascii=False)

    commits = []
    for line in result.get("stdout", "").split("\n"):
        if not line.strip():
            continue
        parts = line.split("|", 3)
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0][:8],
                "author": parts[1],
                "timestamp": int(parts[2]),
                "message": parts[3][:100],  # 限制提交信息长度
            })

    return json.dumps({
        "success": True,
        "commits": commits,
        "total": len(commits),
        "path": path or None,
    }, ensure_ascii=False)


@tool
def git_commit(message: str) -> str:
    """创建 Git 提交。

    Args:
        message: 提交信息

    需要用户审批。会自动添加所有已修改文件（git add -A）。
    """
    from tools import get_project_root
    cwd = get_project_root()

    if not message.strip():
        return json.dumps({"success": False, "error": "提交信息不能为空"}, ensure_ascii=False)

    # 先添加所有修改
    add_result = _run_git(["add", "-A"], cwd)
    if not add_result.get("success"):
        return json.dumps({
            "success": False,
            "error": f"git add 失败: {add_result.get('stderr', '')}",
        }, ensure_ascii=False)

    # 创建提交
    commit_result = _run_git(["commit", "-m", message], cwd)
    if not commit_result.get("success"):
        stderr = commit_result.get("stderr", "")
        if "nothing to commit" in stderr or "no changes added" in stderr:
            return json.dumps({
                "success": False,
                "error": "没有可提交的修改",
            }, ensure_ascii=False)
        return json.dumps({
            "success": False,
            "error": f"git commit 失败: {stderr}",
        }, ensure_ascii=False)

    # 获取提交 hash
    hash_result = _run_git(["rev-parse", "HEAD"], cwd)
    commit_hash = hash_result.get("stdout", "unknown")[:8] if hash_result.get("success") else "unknown"

    return json.dumps({
        "success": True,
        "hash": commit_hash,
        "message": message,
    }, ensure_ascii=False)


@tool
def git_blame(path: str, start_line: int = 0, end_line: int = 0) -> str:
    """显示文件的逐行修改信息。

    Args:
        path: 文件路径（相对于项目根目录）
        start_line: 起始行号（可选，从 1 开始）
        end_line: 结束行号（可选）

    安全工具，可并发执行。
    """
    from tools import get_project_root, resolve_safe_path
    cwd = get_project_root()

    resolved, err = resolve_safe_path(cwd, path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if not resolved.is_file():
        return json.dumps({"success": False, "error": f"文件不存在: {path}"}, ensure_ascii=False)

    args = ["blame", "--porcelain", "--no-color"]
    if start_line > 0:
        if end_line > 0:
            args.extend([f"-L{start_line},{end_line}"])
        else:
            args.extend([f"-L{start_line},{start_line}"])
    args.extend(["--", path])

    result = _run_git(args, cwd)
    if not result.get("success"):
        return json.dumps({
            "success": False,
            "error": f"git blame 失败: {result.get('stderr', '')}",
        }, ensure_ascii=False)

    # 解析 porcelain 格式
    authors = {}
    lines_info = []
    current_commit = None

    for line in result.get("stdout", "").split("\n"):
        if not line.strip():
            continue
        parts = line.split(" ", 3)
        if len(parts) >= 4 and len(parts[0]) == 40:
            commit_hash = parts[0][:8]
            lineno = int(parts[2])
            current_commit = commit_hash
            lines_info.append({"line": lineno, "commit": commit_hash})
        elif line.startswith("author ") and current_commit:
            author = line[7:].strip()
            if current_commit not in authors:
                authors[current_commit] = author
        elif line.startswith("summary ") and current_commit:
            summary = line[8:].strip()
            if current_commit in authors:
                # 可以附加到作者信息
                pass

    return json.dumps({
        "success": True,
        "path": path,
        "lines": lines_info[:100],  # 限制返回行数
        "authors": authors,
        "total_lines": len(lines_info),
    }, ensure_ascii=False)
