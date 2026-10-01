import argparse
import os

from core.config import load_config


PAGES = ("dashboard", "guide", "products", "story", "drama", "library", "video", "voice", "subtitle", "audio", "logo", "queue", "logs")


def run_engine(page="dashboard"):
    os.environ["SMARTPOST_HYBRID_ENGINE"] = "1"
    from ui.main_window import MainWindow

    window = MainWindow(load_config())
    window._show_page("story" if page == "drama" else page)
    window.run()


def show_startup_error(message):
    """Explain a Hybrid startup failure without exposing the retired UI."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showerror(
            "SmartFlow AI",
            "เปิดหน้าจอ SmartFlow AI เวอร์ชันปัจจุบันไม่สำเร็จ\n\n"
            + str(message or "กรุณาตรวจสอบ WebView2 และลองเปิดโปรแกรมอีกครั้ง"),
            parent=root,
        )
    finally:
        root.destroy()


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--page", choices=PAGES, default="dashboard")
    parser.add_argument("--engine", action="store_true")
    args, _ = parser.parse_known_args()

    if args.engine:
        run_engine(args.page)
        return

    try:
        from desktop.hybrid import run_hybrid

        if run_hybrid(page=args.page, port=int(load_config().get("bridge_port", 8765))):
            return
        show_startup_error("ไม่พบ Microsoft Edge WebView2 หรือ pywebview")
    except Exception as exc:
        show_startup_error(exc)

if __name__ == "__main__":
    main()
