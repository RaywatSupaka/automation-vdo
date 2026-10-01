import subprocess
import time


class OperationCancelled(RuntimeError):
    """Raised when the user stops an active SmartPost pipeline."""


def check_cancelled(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise OperationCancelled("ผู้ใช้ยกเลิกการทำงาน")


def hidden_process_kwargs():
    """Keep background CLI tools from flashing console windows on Windows."""
    if not hasattr(subprocess, "CREATE_NO_WINDOW"):
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


def run_cancellable(command, *, cancel_event=None, timeout=3600, on_wait=None, on_start=None):
    """Run a child process while allowing a UI cancellation event to stop it."""
    check_cancelled(cancel_event)
    if cancel_event is None and on_wait is None and on_start is None:
        return subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout, **hidden_process_kwargs(),
        )
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace", **hidden_process_kwargs(),
    )
    started = time.monotonic()
    last_notice = started
    try:
        if on_start is not None:
            on_start(process.pid)
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.25)
                return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                if cancel_event is not None and cancel_event.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    process.communicate()
                    raise OperationCancelled("ผู้ใช้ยกเลิกการทำงาน")
                if time.monotonic() - started >= timeout:
                    process.kill()
                    process.communicate()
                    raise subprocess.TimeoutExpired(command, timeout)
                now = time.monotonic()
                if on_wait is not None and now - last_notice >= 5:
                    on_wait(now - started)
                    last_notice = now
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
