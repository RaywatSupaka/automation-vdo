"""DEV-only raw WebView2 child inside the SmartFlow WinForms window.

The provider control deliberately does not use pywebview's EdgeChrome wrapper:
that wrapper injects the SmartFlow JavaScript API into every navigation.
"""

import math
import threading
from pathlib import Path


PROFILE = Path(__file__).resolve().parents[1] / "build" / "webview2-provider-prototype" / "profile-embedded-chatgpt"
PROVIDER_URL = "https://chatgpt.com/"


def bounds_from_css(rect, client_width, client_height):
    """Map viewport CSS coordinates into WinForms client pixels, clamped to the form."""
    if not isinstance(rect, dict):
        raise ValueError("invalid host bounds")
    values = [rect.get(key) for key in ("left", "top", "width", "height", "viewport_width", "viewport_height")]
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in values):
        raise ValueError("invalid host bounds")
    left, top, width, height, viewport_width, viewport_height = values
    if viewport_width <= 0 or viewport_height <= 0 or width <= 0 or height <= 0:
        raise ValueError("empty host bounds")
    sx, sy = client_width / viewport_width, client_height / viewport_height
    x1 = max(0, min(client_width, round(left * sx)))
    y1 = max(0, min(client_height, round(top * sy)))
    x2 = max(0, min(client_width, round((left + width) * sx)))
    y2 = max(0, min(client_height, round((top + height) * sy)))
    if x2 - x1 < 20 or y2 - y1 < 20:
        raise ValueError("host is outside the visible window")
    return x1, y1, x2 - x1, y2 - y1


class EmbeddedProvider:
    def __init__(self, window):
        self.window = window
        self.control = None
        self._lock = threading.Lock()

    def show(self, rect):
        form = getattr(self.window, "native", None)
        if form is None or form.IsDisposed:
            return {"ok": False, "error": "หน้าต่าง SmartFlow ยังไม่พร้อม"}
        try:
            bounds = bounds_from_css(rect, form.ClientSize.Width, form.ClientSize.Height)
        except ValueError:
            self.hide()
            return {"ok": False, "error": "พื้นที่ AI Chat ยังไม่พร้อม"}
        try:
            from System import Action, Uri
            from System.Drawing import Rectangle
            from Microsoft.Web.WebView2.WinForms import WebView2, CoreWebView2CreationProperties

            def update():
                if form.IsDisposed:
                    return
                with self._lock:
                    if self.control is None or self.control.IsDisposed:
                        PROFILE.mkdir(parents=True, exist_ok=True)
                        control = WebView2()
                        properties = CoreWebView2CreationProperties()
                        properties.UserDataFolder = str(PROFILE)
                        control.CreationProperties = properties
                        control.Bounds = Rectangle(*bounds)
                        form.Controls.Add(control)
                        self.control = control
                        control.Source = Uri(PROVIDER_URL)
                    else:
                        self.control.Bounds = Rectangle(*bounds)
                    self.control.Visible = True
                    self.control.BringToFront()

            form.Invoke(Action(update))
            return {"ok": True}
        except Exception:
            return {"ok": False, "error": "ฝัง WebView2 ในหน้าต่างนี้ไม่สำเร็จ"}

    def hide(self):
        form = getattr(self.window, "native", None)
        if form is None or form.IsDisposed:
            return {"ok": True}
        try:
            from System import Action

            def update():
                if self.control is not None and not self.control.IsDisposed:
                    self.control.Visible = False

            form.Invoke(Action(update))
        except Exception:
            pass
        return {"ok": True}

    def evaluate(self, script, timeout_ms=10000):
        """Run a script only in the isolated provider control, never the shell."""
        form = getattr(self.window, "native", None)
        if form is None or form.IsDisposed or self.control is None or self.control.IsDisposed:
            raise RuntimeError("provider_not_open")
        from System import Func, Object

        def begin():
            if self.control.CoreWebView2 is None:
                raise RuntimeError("provider_not_ready")
            return self.control.CoreWebView2.ExecuteScriptAsync(script)

        task = form.Invoke(Func[Object](begin))
        if not task.Wait(timeout_ms):
            raise TimeoutError("provider_script_timeout")
        return task.Result
