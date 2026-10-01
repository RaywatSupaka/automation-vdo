import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExtensionBrowserCleanupTests(unittest.TestCase):
    def test_extension_close_only_uses_registered_automation_tabs(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        body = source.split("async function closeAutomationBrowser", 1)[1].split("function bytesToBase64", 1)[0]
        self.assertIn("const candidates = await rememberedAutomationTabIds()", body)
        self.assertIn("isAutomationTabUrl(tab?.url)", body)
        self.assertNotIn("const liveTabs = await chrome.tabs.query({})", body)

    def test_extension_close_keeps_tab_ids_until_remove_finishes(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        body = source.split("async function closeAutomationBrowser", 1)[1].split("function bytesToBase64", 1)[0]
        remove_tabs = body.index("await chrome.tabs.remove(tabIds)")
        forget_tabs = body.index("await chrome.storage.local.remove(keys)")
        self.assertLess(remove_tabs, forget_tabs)

    def test_fresh_ai_job_adopts_the_desktop_bootstrap_tab(self):
        source = (ROOT / "browser_extension" / "background.js").read_text(encoding="utf-8")
        body = source.split("async function startAIWebJob", 1)[1].split("async function cancelChatGPTJob", 1)[0]
        self.assertIn("const bootstrapTabs = await chrome.tabs.query", body)
        self.assertIn("await rememberAutomationTabs(tabId)", body)
        self.assertLess(body.index("const bootstrapTabs = await chrome.tabs.query"), body.rindex("tabId = await openAIWebTab(provider)"))


if __name__ == "__main__":
    unittest.main()
