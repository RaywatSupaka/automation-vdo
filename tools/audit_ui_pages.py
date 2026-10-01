import json
import sys
import time
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageGrab, ImageOps


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import load_config
from ui.main_window import MainWindow


PAGES = (
    "dashboard",
    "guide",
    "products",
    "story",
    "library",
    "video",
    "voice",
    "subtitle",
    "audio",
    "logo",
    "queue",
    "logs",
)

VIEWPORTS = (
    ("standard", "1280x820"),
    ("compact", "1080x700"),
)

ISSUE_KEYS = ("overflow", "parent_clipped", "text_clipped", "zero_sized", "undersized", "unmapped")

INTERACTIVE_TYPES = (
    tk.Button,
    tk.Checkbutton,
    tk.Entry,
    tk.Label,
    tk.Scale,
    tk.Text,
    ttk.Button,
    ttk.Checkbutton,
    ttk.Combobox,
    ttk.Label,
    ttk.Scale,
    ttk.Treeview,
)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def widget_label(widget):
    try:
        text = str(widget.cget("text") or "").strip()
    except (tk.TclError, AttributeError):
        text = ""
    if not text:
        try:
            variable = str(widget.cget("textvariable") or "").strip()
            text = str(widget.getvar(variable) if variable else "").strip()
        except (tk.TclError, AttributeError):
            text = ""
    return text or widget.winfo_class()


def scrollable_ancestor(widget, stop):
    parent = getattr(widget, "master", None)
    while parent is not None and parent != stop:
        if getattr(parent, "_smartpost_scroll_body", False):
            return parent
        parent = getattr(parent, "master", None)
    return None


def clipping_parent(widget, page):
    if scrollable_ancestor(widget, page):
        return None
    left, top = widget.winfo_rootx(), widget.winfo_rooty()
    right, bottom = left + widget.winfo_width(), top + widget.winfo_height()
    parent = getattr(widget, "master", None)
    while parent is not None and parent != page:
        if parent.winfo_ismapped() and parent.winfo_width() > 2 and parent.winfo_height() > 2:
            parent_left, parent_top = parent.winfo_rootx(), parent.winfo_rooty()
            parent_right = parent_left + parent.winfo_width()
            parent_bottom = parent_top + parent.winfo_height()
            if left < parent_left - 2 or top < parent_top - 2 or right > parent_right + 2 or bottom > parent_bottom + 2:
                return widget_label(parent)
        parent = getattr(parent, "master", None)
    return None


def inspect_page(page):
    page.update_idletasks()
    px, py = page.winfo_rootx(), page.winfo_rooty()
    pw, ph = page.winfo_width(), page.winfo_height()
    overflow = []
    parent_clipped = []
    text_clipped = []
    zero_sized = []
    undersized = []
    unmapped = []
    interactive_count = 0
    for widget in descendants(page):
        if not isinstance(widget, INTERACTIVE_TYPES):
            continue
        inside_scrollable = bool(scrollable_ancestor(widget, page))
        if not widget.winfo_ismapped():
            if widget.winfo_manager() and not inside_scrollable:
                unmapped.append(widget_label(widget))
            continue
        interactive_count += 1
        width, height = widget.winfo_width(), widget.winfo_height()
        if width <= 2 or height <= 2:
            zero_sized.append(widget_label(widget))
            continue
        if isinstance(widget, (tk.Button, ttk.Button)) and width >= 90 and height < 24:
            undersized.append({"widget": widget_label(widget), "size": [width, height]})
        clipping_container = clipping_parent(widget, page)
        if clipping_container:
            parent_clipped.append({
                "widget": widget_label(widget),
                "container": clipping_container,
                "size": [width, height],
            })
        if isinstance(widget, (tk.Button, ttk.Button, tk.Label, ttk.Label, ttk.Checkbutton, tk.Checkbutton)):
            try:
                wraplength = int(float(widget.cget("wraplength") or 0))
            except (tk.TclError, ValueError, TypeError):
                wraplength = 0
            requested_width, requested_height = widget.winfo_reqwidth(), widget.winfo_reqheight()
            if (not wraplength and width + 24 < requested_width) or height + 12 < requested_height:
                text_clipped.append({
                    "widget": widget_label(widget),
                    "actual": [width, height],
                    "requested": [requested_width, requested_height],
                })
        left = widget.winfo_rootx() - px
        top = widget.winfo_rooty() - py
        right = left + width
        bottom = top + height
        if not inside_scrollable and (left < -2 or top < -2 or right > pw + 2 or bottom > ph + 2):
            overflow.append({
                "widget": widget_label(widget),
                "box": [left, top, right, bottom],
                "page": [pw, ph],
            })
    return {
        "size": [pw, ph],
        "interactive_count": interactive_count,
        "overflow": overflow,
        "parent_clipped": parent_clipped,
        "text_clipped": text_clipped,
        "zero_sized": zero_sized,
        "undersized": undersized,
        "unmapped": unmapped,
    }


def make_contact_sheet(records, target, columns=2):
    thumb_size = (640, 410)
    label_height = 30
    rows = (len(records) + columns - 1) // columns
    sheet = Image.new("RGB", (thumb_size[0] * columns, (thumb_size[1] + label_height) * rows), "#070B16")
    draw = ImageDraw.Draw(sheet)
    for index, record in enumerate(records):
        image = Image.open(record["screenshot"]).convert("RGB")
        image = ImageOps.contain(image, thumb_size)
        x = (index % columns) * thumb_size[0]
        y = (index // columns) * (thumb_size[1] + label_height)
        sheet.paste(image, (x + (thumb_size[0] - image.width) // 2, y))
        issues = sum(len(record["audit"][key]) for key in ISSUE_KEYS)
        draw.text((x + 10, y + thumb_size[1] + 7), f"{record['profile']} / {record['page']}  |  layout issues: {issues}", fill="#7DF9FF" if not issues else "#FF7893")
    sheet.save(target)


def main():
    output = ROOT / "workspace" / "diagnostics" / f"ui-audit-{datetime.now():%Y%m%d-%H%M%S}"
    output.mkdir(parents=True, exist_ok=True)
    window = MainWindow(load_config())
    records = []
    try:
        for profile, geometry in VIEWPORTS:
            window.root.geometry(geometry)
            window.root.update_idletasks()
            window.root.update()
            hwnd = window.root.winfo_id()
            for page_name in PAGES:
                window._show_page(page_name)
                window.root.update_idletasks()
                window.root.update()
                time.sleep(0.08)
                screenshot = output / f"{profile}-{page_name}.png"
                ImageGrab.grab(window=hwnd).convert("RGB").save(screenshot)
                audit = inspect_page(window.pages[page_name])
                records.append({"profile": profile, "page": page_name, "screenshot": str(screenshot), "audit": audit})
    finally:
        try:
            window.bridge.stop()
        except Exception:
            pass
        window.root.destroy()

    report = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "page_count": len(PAGES),
        "viewport_count": len(VIEWPORTS),
        "check_count": len(records),
        "issue_count": sum(sum(len(row["audit"][key]) for key in ISSUE_KEYS) for row in records),
        "pages": records,
    }
    report_path = output / "audit.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for index in range(0, len(records), 6):
        make_contact_sheet(records[index:index + 6], output / f"contact-{index // 6 + 1}.jpg")
    print(json.dumps({"output": str(output), "report": str(report_path), "page_count": report["page_count"], "viewport_count": report["viewport_count"], "check_count": report["check_count"], "issue_count": report["issue_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
