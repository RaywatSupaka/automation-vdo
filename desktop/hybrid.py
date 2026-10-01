from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8765
WINDOW_TITLE = "SmartFlow AI — AI Clip Creator"
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_WINDOW_ICON_HANDLE: int | None = None


def _apply_windows_window_icon(title: str = WINDOW_TITLE) -> bool:
    """Replace the generic Python/WebView icon after the native window exists."""
    global _WINDOW_ICON_HANDLE
    if os.name != "nt":
        return False
    icon_path = ROOT / "assets" / "smartflow_icon.ico"
    if not icon_path.is_file():
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.SendMessageW.restype = wintypes.LPARAM
        for _ in range(50):
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                icon = user32.LoadImageW(None, str(icon_path), 1, 0, 0, 0x10 | 0x40)
                if not icon:
                    return False
                _WINDOW_ICON_HANDLE = int(icon)
                user32.SendMessageW(hwnd, 0x0080, 0, int(icon))
                user32.SendMessageW(hwnd, 0x0080, 1, int(icon))
                return True
            time.sleep(0.2)
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    return False


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _JobBasicLimit(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _JobExtendedLimit(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _attach_kill_job(process: subprocess.Popen) -> int | None:
    """Ensure the hidden engine cannot survive a crashed WebView owner."""
    if os.name != "nt" or getattr(process, "_handle", None) is None:
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _JobExtendedLimit()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        configured = kernel32.SetInformationJobObject(
            job,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        assigned = configured and kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(int(process._handle)))
        if not assigned:
            kernel32.CloseHandle(job)
            return None
        return int(job)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _close_job(handle: int | None) -> None:
    if os.name != "nt" or not handle:
        return
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(wintypes.HANDLE(handle))
    except (AttributeError, OSError, TypeError, ValueError):
        pass


def _read_json(url: str, timeout: float = 1.0) -> dict:
    request = Request(url, headers={"User-Agent": "SmartPost-Hybrid/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _focus_existing_window(title: str = WINDOW_TITLE) -> bool:
    """Focus an existing visible Hybrid window, never the withdrawn Tk engine."""
    if os.name != "nt":
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowW.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        handle = user32.FindWindowW(None, title)
        if not handle or not user32.IsWindowVisible(wintypes.HWND(handle)):
            return False
        user32.ShowWindow(wintypes.HWND(handle), 9)  # SW_RESTORE
        user32.SetForegroundWindow(wintypes.HWND(handle))
        # The Hybrid window can outlive a hidden-engine restart.  Focusing that
        # existing WebView without reloading used to leave an old HTML form on
        # screen even though the current backend and files were already newer.
        # Refresh after focus so newly added controls (for example the separate
        # Flow / Meta video provider) appear without creating another window.
        try:
            user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
            user32.keybd_event.restype = None
            time.sleep(0.12)
            user32.keybd_event(0x74, 0, 0, 0)  # VK_F5 key down
            user32.keybd_event(0x74, 0, 0x0002, 0)  # KEYEVENTF_KEYUP
        except (AttributeError, OSError, TypeError, ValueError):
            pass
        return True
    except (AttributeError, OSError, TypeError, ValueError):
        return False


class HybridHost:
    def __init__(self, port: int = DEFAULT_PORT, page: str = "dashboard") -> None:
        self.port = int(port)
        self.page = str(page or "dashboard")
        self.process: subprocess.Popen | None = None
        self.job_handle: int | None = None
        self.engine_pid: int | None = None
        self.owns_engine = False
        self._stop_lock = threading.Lock()
        self._stopped = False
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        self._restart_times: list[float] = []
        self._engine_log = None
        self._engine_conflict = ''
        self._isolated_test = bool(os.environ.get('SMARTFLOW_TEST_DATA_ROOT'))
        self._browser_connection_attempted = False
        self._expected_release = None
        if getattr(sys, 'frozen', False):
            from core.app_updates import customer_version
            self._expected_release = customer_version()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _health(self) -> dict:
        try:
            return _read_json(f"{self.base_url}/health", timeout=0.5)
        except (OSError, ValueError):
            return {}

    def _ready(self) -> bool:
        health = self._health()
        # Health is deliberately independent from the Tk UI queue. Asking for
        # the complete desktop state here can time out while a modal or
        # recovery callback owns the UI thread, even though the engine and
        # bridge are already healthy. That false negative used to keep the
        # watchdog in a 40-second restart loop.
        ready = bool(health.get("ok") and health.get("desktop_ui") == "hybrid")
        self._engine_conflict = ''
        if ready:
            try:
                pid = int(health.get("engine_pid") or 0)
            except (TypeError, ValueError):
                pid = 0
            if self._isolated_test and not self.owns_engine:
                self._engine_conflict = 'พอร์ตทดสอบมีโปรแกรมอื่นทำงานอยู่ • เลือกพอร์ตว่าง ไม่เชื่อมต่อหรือปิดโปรแกรมเดิม'
            elif (self._expected_release is not None or self._isolated_test) and self.owns_engine and self.process and pid != self.process.pid:
                self._engine_conflict = 'พอร์ตถูกใช้โดยโปรแกรมอีกชุด • ไม่เชื่อมต่อหรือปิดโปรแกรมเดิม'
            elif self._expected_release is not None and (
                self._expected_release == 'development' or health.get('release_version') != self._expected_release
            ):
                self._engine_conflict = 'พบระบบ SmartFlow คนละรุ่น • รอให้งานเดิมจบแล้วปิดโปรแกรมเดิมก่อนเปิดรุ่นนี้ ไม่ได้หยุดงานเดิมให้'
            if self._engine_conflict:
                return False
            if pid > 0:
                self.engine_pid = pid
        return ready

    def ensure_browser_connection(self) -> bool:
        """Ask this ready desktop to connect Chrome once; startup stays usable on failure."""
        if self._isolated_test or os.environ.get('SMARTFLOW_TEST_DATA_ROOT'):
            return False
        if self._browser_connection_attempted:
            return False
        self._browser_connection_attempted = True
        try:
            if not self._ready() or self._engine_conflict:
                return False
            request = Request(
                f"{self.base_url}/api/desktop/action",
                data=json.dumps({"action": "connect_browser", "payload": {}}).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "SmartPost-Hybrid/1.0"},
                method="POST",
            )
            with urlopen(request, timeout=1.0) as response:
                result = json.loads(response.read().decode("utf-8"))
            return isinstance(result, dict) and result.get("ok") is True
        except (OSError, ValueError, TypeError, AttributeError):
            # A missing/older/busy bridge cannot prevent the desktop UI opening.
            # Do not retry an action whose acknowledgement may have been lost.
            return False

    def start_engine(self) -> None:
        if self._ready():
            return
        if self._engine_conflict:
            raise RuntimeError(self._engine_conflict)
        if self.process and self.process.poll() is not None:
            _close_job(self.job_handle)
            self.job_handle = None
            self.process = None
            self.owns_engine = False
            if self._engine_log:
                try:
                    self._engine_log.close()
                except OSError:
                    pass
                self._engine_log = None
        env = os.environ.copy()
        env.update({"PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1", "SMARTPOST_HYBRID_ENGINE": "1"})
        command = [sys.executable, str(ROOT / "app.py"), "--engine", "--page", self.page]
        if getattr(sys, "frozen", False):
            command = [sys.executable, "--engine", "--page", self.page]
        creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        log_root = ROOT
        if getattr(sys, "frozen", False):
            from core.config import ROOT as customer_data_root
            log_root = customer_data_root
        log_folder = log_root / "logs"
        log_folder.mkdir(parents=True, exist_ok=True)
        self._engine_log = (log_folder / "hybrid_engine.log").open("a", encoding="utf-8", buffering=1)
        self._engine_log.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] START engine page={self.page}\n")
        self.process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=self._engine_log,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
        self.engine_pid = int(self.process.pid)
        self.owns_engine = True
        self.job_handle = _attach_kill_job(self.process)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"ระบบหลักหยุดก่อนเปิดหน้าจอ (รหัส {self.process.returncode})")
            if self._ready():
                return
            if self._engine_conflict:
                raise RuntimeError(self._engine_conflict)
            time.sleep(0.2)
        raise TimeoutError("ระบบหลักใช้เวลาเปิดนานเกินไป")

    def start_watchdog(self) -> None:
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(
            target=self._watch_engine,
            name="smartflow-engine-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

    def _watch_engine(self) -> None:
        while not self._watchdog_stop.wait(2):
            process = self.process
            if not self.owns_engine or not process or process.poll() is None:
                continue
            now = time.monotonic()
            self._restart_times = [item for item in self._restart_times if now - item < 10 * 60]
            if len(self._restart_times) >= 3:
                # Stay bounded. A later manual app restart gets a fresh budget,
                # while a crash loop cannot flash Chrome or spend credits.
                if self._engine_log:
                    self._engine_log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WATCHDOG paused after 3 restarts\n")
                return
            self._restart_times.append(now)
            exit_code = process.returncode
            if self._engine_log:
                self._engine_log.write(
                    f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WATCHDOG engine exited code={exit_code}; restarting\n"
                )
            try:
                self.start_engine()
                if self._engine_log:
                    self._engine_log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WATCHDOG recovery ready\n")
            except Exception as exc:
                if self._engine_log:
                    self._engine_log.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WATCHDOG recovery failed: {exc}\n")
                if self._watchdog_stop.wait(5):
                    return

    def stop(self) -> None:
        # pywebview can invoke the closed callback and then leave its main loop,
        # whose finally block calls stop again. Keep shutdown strictly one-shot
        # so the two paths never race the watchdog or a reused PID.
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True
        self._watchdog_stop.set()
        watchdog = self._watchdog_thread
        if watchdog and watchdog.is_alive() and watchdog is not threading.current_thread():
            watchdog.join(timeout=3)
        self._watchdog_thread = None
        process = self.process
        active_ready = self._ready()
        engine_pid = self.engine_pid
        try:
            # Always request shutdown from the active bridge. A new Hybrid
            # window can adopt an engine left behind after a WebView crash, in
            # which case process is None and owns_engine is False. Restricting
            # this request to owned children was the reason an adopted backend
            # could remain alive after the user closed the app.
            if not self._engine_conflict and ((self.owns_engine and process and process.poll() is None) or active_ready):
                payload = json.dumps({"action": "shutdown", "payload": {}}).encode("utf-8")
                request = Request(
                    f"{self.base_url}/api/desktop/action",
                    data=payload,
                    method="POST",
                    headers={"Content-Type": "application/json", "User-Agent": "SmartPost-Hybrid/1.0"},
                )
                try:
                    urlopen(request, timeout=4).read()
                except OSError:
                    pass
                if process:
                    try:
                        process.wait(timeout=6)
                    except subprocess.TimeoutExpired:
                        pass
                else:
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline and self._ready():
                        time.sleep(0.1)
        finally:
            _close_job(self.job_handle)
            self.job_handle = None
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=4)
                except (OSError, subprocess.SubprocessError):
                    pass
            # If an adopted engine ignored the graceful request, terminate only
            # the exact PID still reported by this SmartFlow health endpoint.
            # Never search for or kill arbitrary Python processes.
            if self._ready():
                current_pid = self.engine_pid
                if current_pid and current_pid == engine_pid and current_pid != os.getpid():
                    try:
                        os.kill(current_pid, signal.SIGTERM)
                    except (OSError, ProcessLookupError):
                        pass
                    deadline = time.monotonic() + 4
                    while time.monotonic() < deadline and self._ready():
                        time.sleep(0.1)
            self.process = None
            self.engine_pid = None
            self.owns_engine = False
            if self._engine_log:
                try:
                    self._engine_log.close()
                except OSError:
                    pass
                self._engine_log = None


def run_hybrid(page: str = "dashboard", port: int = DEFAULT_PORT) -> bool:
    """Start the hidden Tk engine and present the HTML UI in Edge WebView2."""
    try:
        import webview
    except ImportError:
        return False

    host = HybridHost(port=port, page=page)
    if not os.environ.get("SMARTFLOW_TEST_DATA_ROOT"):
        if getattr(sys, 'frozen', False):
            host._ready()
            if host._engine_conflict:
                raise RuntimeError(host._engine_conflict)
        if _focus_existing_window():
            host.ensure_browser_connection()
            return True
    try:
        host.start_engine()
        host.ensure_browser_connection()
        host.start_watchdog()
        initial_url = f"{host.base_url}/desktop/#{page}"
        from desktop.update_api import UpdateApi
        update_api = UpdateApi(host)
        window = webview.create_window(
            WINDOW_TITLE + (" [TEST]" if os.environ.get("SMARTFLOW_TEST_DATA_ROOT") else ""),
            url=initial_url,
            width=1360,
            height=860,
            min_size=(980, 680),
            background_color="#070914",
            js_api=update_api,
        )
        update_api._window = window
        window.events.closed += host.stop
        threading.Thread(
            target=_apply_windows_window_icon,
            name="smartflow-window-icon",
            daemon=True,
        ).start()
        if getattr(sys, "frozen", False):
            from core.config import ROOT as data_root
            marker = data_root / "logs" / "desktop-ready.json"
            def record_ready():
                marker.write_text(json.dumps({"ready": True, "pid": os.getpid(), "engine_pid": host.engine_pid}), encoding="utf-8")
            window.events.loaded += record_ready
            webview.start(debug=False, private_mode=False, gui="edgechromium", storage_path=str(data_root / "webview-profile"))
        else:
            webview.start(debug=False, private_mode=False)
        return True
    finally:
        host.stop()
