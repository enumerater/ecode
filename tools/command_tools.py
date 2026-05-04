import json
import subprocess
from langchain_core.tools import tool


@tool
def run_command(command: str) -> str:
    """在项目目录中执行终端命令。需要用户审批。"""
    from tools import get_project_root

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=get_project_root(),
        )
        return json.dumps({
            "success": result.returncode == 0,
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout[-5000:] if result.stdout else "",
            "stderr": result.stderr[-2000:] if result.stderr else "",
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "error": f"命令超时(30s): {command}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)
