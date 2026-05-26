import json
import subprocess
import threading
import time
from langchain_core.tools import tool

from tools.streaming import (
    COMMAND_POLL_INTERVAL,
    COMMAND_MIN_LINES_BEFORE_PUSH,
    push_command_stream,
)

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


# 线程局部变量：由 tool_executor 在执行前设置，用于流式传输
_thread_local = threading.local()


def _set_streaming_ctx(tool_call_id: str):
    """设置当前线程的流式上下文（由 tool_executor 调用）。"""
    _thread_local.tool_call_id = tool_call_id


def _get_streaming_ctx() -> str:
    """获取当前线程的流式上下文。"""
    return getattr(_thread_local, "tool_call_id", "")


@tool
def run_command(command: str, timeout: int = COMMAND_TIMEOUT, auto_respond: bool = True) -> str:
    """在项目目录中执行终端命令。需要用户审批。

    交互式命令处理：
    - 检测 (y/n)、Ok to proceed? 等交互提示并自动响应 y 或回车
    - stdin 默认关闭，无法自动处理的交互式命令会快速失败而非卡住
    - matplotlib 等 GUI 程序自动使用非交互后端，不会弹窗阻塞

    流式输出：
    - 长时间运行的命令会实时推流 stdout/stderr
    - 客户端可以通过 SSE tool_result_chunk 事件查看实时进度

    Args:
        command: 要执行的命令
        timeout: 超时时间（秒），默认 60
        auto_respond: 是否自动响应交互式提示，默认 True
    """
    from tools import get_project_root

    timeout = min(max(timeout, 1), 300)
    tool_call_id = _get_streaming_ctx()

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

        # 记录上次推送时的累积行数，用于增量推送
        last_pushed_count = 0
        poll_start = time.time()

        try:
            # 轮询等待命令完成，同时实时推送流式输出
            while proc.poll() is None:
                # 检查总超时
                if time.time() - poll_start > timeout:
                    proc.kill()
                    proc.wait()
                    stdout_thread.join(timeout=2)
                    stderr_thread.join(timeout=2)
                    return json.dumps({
                        "success": False,
                        "error": f"命令超时({timeout}s): {command}",
                    }, ensure_ascii=False)

                try:
                    proc.wait(timeout=COMMAND_POLL_INTERVAL)
                except subprocess.TimeoutExpired:
                    # 超时是正常的：进程还在运行，推送实时输出
                    if tool_call_id:
                        with lock:
                            new_lines = stdout_lines[last_pushed_count:]
                            last_pushed_count = len(stdout_lines)
                        if new_lines:
                            push_command_stream(tool_call_id, command, new_lines, is_final=False)
        except OSError as e:
            proc.kill()
            proc.wait()
            stdout_thread.join(timeout=2)
            stderr_thread.join(timeout=2)
            return json.dumps({
                "success": False,
                "error": f"命令执行异常: {e}",
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

        # 推送最终块
        if tool_call_id:
            final_lines = stdout_lines[last_pushed_count:]
            if final_lines:
                push_command_stream(tool_call_id, command, final_lines, is_final=True, exit_code=proc.returncode)

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
