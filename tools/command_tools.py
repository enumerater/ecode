import json
import subprocess
import threading
from langchain_core.tools import tool

# 命令超时时间（秒）
COMMAND_TIMEOUT = 60
# 输出最大长度
MAX_STDOUT_LENGTH = 10000
MAX_STDERR_LENGTH = 5000

# 环境变量：防止子进程 GUI 阻塞 & 确保输出不缓冲
_SUBPROCESS_ENV = {
    'MPLBACKEND': 'Agg',        # matplotlib 使用非交互后端，不弹窗
    'PYTHONUNBUFFERED': '1',     # Python 子进程输出不缓冲
    'GIT_TERMINAL_PROMPT': '0',  # git 禁用交互式认证提示
    'PYTHONIOENCODING': 'utf-8', # 子进程 Python 强制 UTF-8 IO
}


def _auto_respond(line: str) -> str | None:
    """检测交互式提示并返回自动响应。"""
    lower = line.lower()
    # (y/n) 类型
    if '(y/n)' in lower or '(yes/no)' in lower:
        return 'y\n'
    # [Y/n] / [y/N] 类型
    if '[y/n]' in lower or '[yes/no]' in lower:
        return 'y\n'
    # Ok to proceed
    if 'ok to proceed' in lower:
        return 'y\n'
    # 确认类问题
    if 'are you sure' in lower or 'do you want to continue' in lower:
        return 'y\n'
    # Enter 继续
    if 'press enter' in lower or '[enter]' in lower or 'press any key' in lower:
        return '\n'
    # overwrite 确认
    if 'overwrite' in lower and '?' in line:
        return 'y\n'
    # 通用行尾问号（兜底）
    if line.rstrip().endswith('?'):
        return 'y\n'
    return None


def _read_pipe(pipe, buf_list, lock, auto_respond, proc_stdin, label):
    """在独立线程中读取子进程输出，检测交互式提示并自动响应。"""
    try:
        for raw_line in iter(pipe.readline, ''):
            with lock:
                buf_list.append(raw_line)
            if auto_respond and proc_stdin and not proc_stdin.closed:
                stripped = raw_line.rstrip('\r\n')
                response = _auto_respond(stripped)
                if response is not None:
                    try:
                        proc_stdin.write(response)
                        proc_stdin.flush()
                    except (OSError, BrokenPipeError):
                        pass
    finally:
        pipe.close()


@tool
def run_command(command: str, timeout: int = COMMAND_TIMEOUT, auto_respond: bool = True) -> str:
    """在项目目录中执行终端命令。需要用户审批。

    交互式命令处理：
    - 检测 (y/n)、Ok to proceed? 等交互提示并自动响应 y 或回车
    - stdin 默认关闭，无法自动处理的交互式命令会快速失败而非卡住
    - matplotlib 等 GUI 程序自动使用非交互后端，不会弹窗阻塞

    Args:
        command: 要执行的命令
        timeout: 超时时间（秒），默认 60
        auto_respond: 是否自动响应交互式提示，默认 True
    """
    from tools import get_project_root

    timeout = min(max(timeout, 1), 300)

    try:
        env = {**__import__('os').environ, **_SUBPROCESS_ENV}

        proc = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE if auto_respond else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            cwd=get_project_root(),
            env=env,
        )

        stdout_lines, stderr_lines = [], []
        lock = threading.Lock()

        # 使用线程实时读取 stdout/stderr，避免管道缓冲导致死锁
        stdout_thread = threading.Thread(
            target=_read_pipe,
            args=(proc.stdout, stdout_lines, lock, auto_respond, proc.stdin, 'stdout'),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_read_pipe,
            args=(proc.stderr, stderr_lines, lock, False, None, 'stderr'),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            return json.dumps({
                "success": False,
                "error": f"命令超时({timeout}s): {command}",
            }, ensure_ascii=False)
        finally:
            if proc.stdin and not proc.stdin.closed:
                try:
                    proc.stdin.close()
                except (OSError, BrokenPipeError):
                    pass

        stdout_thread.join(timeout=5)
        stderr_thread.join(timeout=5)

        stdout_full = ''.join(stdout_lines)
        stderr_full = ''.join(stderr_lines)

        stdout = stdout_full[-MAX_STDOUT_LENGTH:] if stdout_full else ""
        stderr = stderr_full[-MAX_STDERR_LENGTH:] if stderr_full else ""

        if len(stdout_full) > MAX_STDOUT_LENGTH:
            stdout = f"... (输出已截断，显示最后 {MAX_STDOUT_LENGTH} 字符)\n{stdout}"
        if len(stderr_full) > MAX_STDERR_LENGTH:
            stderr = f"... (输出已截断，显示最后 {MAX_STDERR_LENGTH} 字符)\n{stderr}"

        return json.dumps({
            "success": proc.returncode == 0,
            "command": command,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e),
        }, ensure_ascii=False)
