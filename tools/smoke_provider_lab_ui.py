"""Open one raw child WebView2 in the same native SmartFlow-style window."""

import json
import os
import sys
import time
from pathlib import Path

import webview

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from desktop import embedded_provider
from desktop.update_api import UpdateApi


def main():
    if os.environ.get("SMARTFLOW_DEV_BYPASS_MEMBERSHIP") != "1":
        raise SystemExit("Set SMARTFLOW_DEV_BYPASS_MEMBERSHIP=1")
    fixture = ROOT / "build" / "webview2-provider-prototype" / "embedded-smoke.html"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text("<!doctype html><title>Embedded provider fixture</title><main>AI Chat</main>", encoding="utf-8")
    embedded_provider.PROVIDER_URL = fixture.resolve().as_uri()
    html = """<!doctype html><html><body style='background:#08101d;color:white'>
      <aside style='width:180px;float:left'>SmartFlow</aside>
      <main id='ai-chat-host' style='margin-left:190px;height:350px;background:#161b2a'>AI Chat</main>
      </body></html>"""
    api = UpdateApi(None)
    window = webview.create_window("SmartFlow embedded AI Chat smoke", html=html,
                                   js_api=api, width=900, height=520)
    api._window = window
    outcome = {"ok": False, "same_window": False, "hidden_on_leave": False,
               "fixture_loaded": False, "isolated_script": False}

    def check():
        try:
            rect = window.evaluate_js("""(() => {const r=document.getElementById('ai-chat-host').getBoundingClientRect();
              return {left:r.left,top:r.top,width:r.width,height:r.height,
                      viewport_width:innerWidth,viewport_height:innerHeight};})()""")
            result = api.provider_lab_show(rect)
            if not result.get("ok"):
                outcome["error"] = result.get("error")
                return
            control = api._embedded_provider.control
            outcome["same_window"] = control.Parent.Handle == window.native.Handle
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                source = str(control.Source or "")
                if "embedded-smoke.html" in source:
                    outcome["fixture_loaded"] = True
                    break
                time.sleep(0.2)
            if outcome["fixture_loaded"]:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    try:
                        outcome["isolated_script"] = json.loads(api._embedded_provider.evaluate(
                            "document.title")) == "Embedded provider fixture"
                        if outcome["isolated_script"]:
                            break
                    except RuntimeError:
                        pass
                    time.sleep(0.2)
            api.provider_lab_hide()
            outcome["hidden_on_leave"] = not control.Visible
            outcome["ok"] = all(outcome[key] for key in
                                 ("same_window", "fixture_loaded", "isolated_script", "hidden_on_leave"))
        except Exception as exc:
            outcome["error_type"] = type(exc).__name__
            outcome["error"] = str(exc)[:180]
        finally:
            window.destroy()

    webview.start(func=check, gui="edgechromium", private_mode=False,
                  storage_path=str(fixture.parent / "smoke-shell-profile"))
    print(json.dumps(outcome, ensure_ascii=False))
    return 0 if outcome["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
