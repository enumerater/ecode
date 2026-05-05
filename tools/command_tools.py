import json
import subprocess
from langchain_core.tools import tool

# 命令超时时间（秒）
COMMAND_TIMEOUT = 60
# 输出最大长度
MAX_STDOUT_LENGTH = 10000
MAX_STDERR_LENGTH = 5000


@tool
def run_command(command: str, timeout: int = COMMAND_TIMEOUT) -> str:
    """在项目目录中执行终端命令。需要用户审批。

    Args:
        command: 要执行的命令
        timeout: 超时时间（秒），默认 60
    """
    from tools import get_project_root

    # 限制超时范围
    timeout = min(max(timeout, 1), 300)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=get_project_root(),
        )

        stdout = result.stdout[-MAX_STDOUT_LENGTH:] if result.stdout else ""
        stderr = result.stderr[-MAX_STDERR_LENGTH:] if result.stderr else ""

        # 截断时添加提示
        if result.stdout and len(result.stdout) > MAX_STDOUT_LENGTH:
            stdout = f"... (输出已截断，显示最后 {MAX_STDOUT_LENGTH} 字符)\n{stdout}"
        if result.stderr and len(result.stderr) > MAX_STDERR_LENGTH:
            stderr = f"... (输出已截断，显示最后 {MAX_STDERR_LENGTH} 字符)\n{stderr}"

        return json.dumps({
            "success": result.returncode == 0,
            "command": command,
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "error": f"命令超时({timeout}s): {command}",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)
