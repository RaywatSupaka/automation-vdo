"""Static contract for the UI foundation layer: tokens, status vocabulary, navigation.

Reads source files only. It starts no window, no browser and no provider.
"""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web_ui"


def read(path):
    return Path(path).read_text(encoding="utf-8")


class UiFoundationContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = read(WEB / "index.html")
        cls.vocab = read(WEB / "status_vocabulary.js")
        cls.foundation = read(WEB / "foundation.css")
        cls.nav = cls.html.split('<nav class="navigation"', 1)[1].split("</nav>", 1)[0]

    # ---- asset order -------------------------------------------------------
    def test_foundation_css_loads_last_and_vocabulary_loads_before_its_users(self):
        links = re.findall(r'<link rel="stylesheet" href="/desktop/([\w.-]+)\.css', self.html)
        self.assertEqual(links[-1], "foundation", "foundation.css must win over every other stylesheet")
        scripts = re.findall(r'<script src="/desktop/([\w.-]+)\.js', self.html)
        vocab = scripts.index("status_vocabulary")
        for user in ("app", "creation_queue", "product_continue"):
            self.assertLess(vocab, scripts.index(user), f"status_vocabulary.js must load before {user}.js")

    def test_every_loaded_asset_exists(self):
        for name in re.findall(r'/desktop/([\w.-]+\.(?:js|css))', self.html):
            self.assertTrue((WEB / name).is_file(), f"index.html references missing {name}")

    # ---- one palette -------------------------------------------------------
    @staticmethod
    def _root_tokens(css):
        block = css.split(":root", 1)[1].split("}", 1)[0]
        return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block))

    def test_both_legacy_token_sets_share_one_palette(self):
        tokens = self._root_tokens(self.foundation)
        for legacy, shared in (("--cyan", "--sf-cyan"), ("--surface", "--sf-surface"), ("--line", "--sf-line"),
                               ("--text", "--sf-copy"), ("--muted", "--sf-muted"), ("--violet", "--sf-purple")):
            self.assertEqual(tokens[legacy].strip().lower(), tokens[shared].strip().lower(), f"{legacy} vs {shared}")
        for tone in ("queued", "running", "waiting", "failed", "paused", "done"):
            self.assertIn(f"--st-{tone}-bg", tokens)
            self.assertIn(f"--st-{tone}-fg", tokens)

    def test_no_font_size_below_ten_pixels_in_any_stylesheet(self):
        offenders = []
        for css in sorted(WEB.glob("*.css")):
            for number, line in enumerate(read(css).splitlines(), 1):
                if re.search(r"font-size\s*:\s*[0-9](?:\.\d+)?px", line):
                    offenders.append(f"{css.name}:{number}")
        self.assertEqual(offenders, [], "text below 10px is unreadable for Thai")

    # ---- one status vocabulary ---------------------------------------------
    def test_pages_use_the_shared_vocabulary_instead_of_private_labels(self):
        queue = read(WEB / "creation_queue.js")
        self.assertIn("SmartFlowStatus.label(code)", queue)
        self.assertIn("SmartFlowStatus.pauseReason(queue.pause_reason)", queue)
        self.assertIn("SmartFlowStatus.pill(value", read(WEB / "app.js"))
        # Wording that used to name a *job* status. Sentences that merely contain the same words,
        # such as a per-image state or a scene note, are not job statuses and stay as they are.
        retired = ("รอทำงาน", "หยุดที่ขั้นหนึ่ง", "งานสะดุด • ทำต่อได้", "ยกเลิกไว้ • ทำต่อได้",
                   "ENGINE OFFLINE", "ENGINE BUSY", "AUTOMATION READY", "EXTENSION VERSION MISMATCH", "CHECK CONNECTION")
        for js in sorted(WEB.glob("*.js")):
            text = read(js)
            for phrase in retired:
                self.assertNotIn(phrase, text, f"{js.name} still shows retired wording {phrase!r}")
        self.assertNotIn("ต้องตรวจสอบ", queue, "queue failure label must come from the vocabulary")
        for line in read(WEB / "app.js").splitlines():
            if "story-recovery-badge" in line:
                self.assertNotIn("พร้อมทำต่อ", line, "recovery badge must say หยุดไว้")
                self.assertIn("sf-status", line, "recovery badge must use the shared pill")
        self.assertNotIn("คัดลอก Log สำหรับ Codex", self.html)

    def test_every_backend_pause_reason_has_customer_text(self):
        reasons = set()
        for path in (ROOT / "core" / "creation_queue.py", ROOT / "ui" / "creation_queue.py",
                     ROOT / "ui" / "update_guard.py", ROOT / "ui" / "main_window.py"):
            text = read(path)
            reasons.update(re.findall(r"""story_queue\.pause\(\s*["']([A-Za-z_]+)["']""", text))
            reasons.update(re.findall(r"""pause_reason\s*=\s*["']([A-Za-z_]+)["']""", text))
        self.assertTrue(len(reasons) >= 10, f"expected to find the backend pause reasons, found {sorted(reasons)}")
        block = self.vocab.split("const PAUSE_REASONS = {", 1)[1].split("\n  };", 1)[0]
        explained = set(re.findall(r"^\s+(\w+):", block, re.M))
        self.assertEqual(sorted(reasons - explained), [],
                         "a new pause reason needs customer-facing text in status_vocabulary.js PAUSE_REASONS")

    # ---- navigation --------------------------------------------------------
    def test_navigation_is_grouped_and_every_page_is_reachable(self):
        routes = re.findall(r'<button class="nav-item[^"]*"[^>]*data-page="([\w-]+)"', self.nav)
        self.assertEqual(len(routes), len(set(routes)), "a page appears twice in the sidebar")
        self.assertEqual(self.nav.count('<details class="nav-group"'), 3)
        groups = {
            name: re.findall(r'data-page="([\w-]+)"', body)
            for name, body in re.findall(r'<details class="nav-group" data-nav-group="(\w+)">(.*?)</details>', self.nav, re.S)
        }
        self.assertEqual(groups["publish"], ["queue", "facebook"])
        self.assertEqual(groups["cast"], ["presenter", "presenter-settings", "product-cast", "intro", "green"])
        self.assertEqual(groups["settings"], ["settings", "voice", "subtitle", "audio", "logo", "guide", "logs"])
        # Pages that used to be reachable only from buttons inside other pages.
        for hidden in ("voice", "subtitle", "audio", "logo", "guide"):
            self.assertIn(hidden, routes)
        injected = "".join(read(js) for js in WEB.glob("*.js"))
        for route in routes:
            static = f'data-view="{route}"' in self.html
            created = (f'data-view="{route}"' in injected or f"data-view='{route}'" in injected
                       or re.search(rf"dataset\.view\s*=\s*['\"]{re.escape(route)}['\"]", injected) is not None)
            self.assertTrue(static or created, f"sidebar page {route!r} has no page behind it")

    def test_navigation_keeps_the_hooks_other_code_depends_on(self):
        for hook in ('id="nav-creation-count"', 'id="nav-library-count"', 'id="ai-chat-nav"'):
            self.assertIn(hook, self.nav)
        self.assertIn('<p class="nav-label">สร้าง</p>', self.nav)
        self.assertIn('<p class="nav-label">งานและผลงาน</p>', self.nav)
        self.assertIn("group.querySelector('.nav-item.active')", read(WEB / "app.js"),
                      "the group holding the active page must open on its own")

    def test_page_titles_match_the_sidebar_names(self):
        app = read(WEB / "app.js")
        for nav_name, page in (("คลิปสินค้า Shopee", "products"), ("เสียงพากย์ AI", "voice"), ("ซับไตเติล", "subtitle"),
                               ("เพลงและเสียงประกอบ", "audio"), ("โลโก้", "logo"), ("โพสต์ Shopee", "queue"),
                               ("ค่าเริ่มต้นและคุณภาพ", "settings"), ("ช่วยเหลือและบันทึกระบบ", "logs")):
            self.assertIn(nav_name, self.nav, f"sidebar lacks {nav_name}")
            self.assertRegex(app, rf"{re.escape(page)}: \['[^']+', '{re.escape(nav_name)}'\]", f"page title for {page}")
        self.assertIn("คลิปสินค้า Shopee", read(WEB / "product_story.js"), "runtime rename must not reintroduce the old name")


if __name__ == "__main__":
    unittest.main()
