import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "browser_extension"
SRC = EXT / "src"


class ExtensionModularArchitectureTests(unittest.TestCase):
    def test_manifest_uses_module_worker_and_least_privilege(self):
        manifest = json.loads((EXT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["background"]["service_worker"], "src/background/service-worker.js")
        self.assertEqual(manifest["background"]["type"], "module")
        self.assertNotIn("<all_urls>", manifest["host_permissions"])
        self.assertNotIn("cookies", manifest["permissions"])
        self.assertNotIn("system.display", manifest["permissions"])

    def test_required_modular_layers_exist_and_are_connected(self):
        required = [
            "background/service-worker.js",
            "background/bootstrap.js",
            "background/job-router.js",
            "background/tab-manager.js",
            "background/window-manager.js",
            "core/bridge-transport.js",
            "core/message-schema.js",
            "core/storage.js",
            "core/logger.js",
            "core/retry.js",
            "core/errors.js",
            "core/media-transfer.js",
            "platforms/platform-adapter.js",
            "platforms/shopee/adapter.js",
            "platforms/ai-web/adapter.js",
            "platforms/google-flow/adapter.js",
            "platforms/google-flow/selectors.js",
            "platforms/google-flow/injected-result-observer.js",
            "platforms/google-flow/result-observer-content.js",
            "ui/overlay.js",
        ]
        missing = [name for name in required if not (SRC / name).is_file()]
        self.assertEqual(missing, [])
        bootstrap = (SRC / "background/bootstrap.js").read_text(encoding="utf-8")
        worker = (SRC / "background/service-worker.js").read_text(encoding="utf-8")
        self.assertIn("router.registerAdapter(adapter)", bootstrap)
        self.assertIn('import "./bootstrap.js";', worker)
        self.assertIn('import "../../background.js";', worker)

    def test_job_router_uses_registry_timeout_and_duplicate_receipts(self):
        source = (SRC / "background/job-router.js").read_text(encoding="utf-8")
        self.assertIn("this.handlers = new Map()", source)
        self.assertIn("this.inflight = new Map()", source)
        self.assertIn("this.completed = new Map()", source)
        self.assertIn("Promise.race", source)
        self.assertIn("serialiseError(error)", source)
        background = (EXT / "background.js").read_text(encoding="utf-8")
        self.assertIn("SmartFlowArchitecture?.router?.assertRegistered(command)", background)

    def test_passive_flow_observer_never_mutates_flow_transport_or_clicks(self):
        injected = (SRC / "platforms/google-flow/injected-result-observer.js").read_text(encoding="utf-8")
        forbidden = (
            "window.fetch =",
            "URL.createObjectURL =",
            "HTMLAnchorElement.prototype.click",
            ".click()",
            "location.reload",
            "chrome.debugger",
        )
        for marker in forbidden:
            self.assertNotIn(marker, injected)
        self.assertIn("PerformanceObserver", injected)
        self.assertIn("MutationObserver", injected)
        self.assertIn("window.postMessage", injected)

    def test_page_bridge_validates_source_namespace_request_and_url(self):
        content = (SRC / "platforms/google-flow/result-observer-content.js").read_text(encoding="utf-8")
        self.assertIn("event.source !== window", content)
        self.assertIn("message.namespace !== NAMESPACE", content)
        self.assertIn("message.requestId", content)
        self.assertIn("validUrl(payload.url)", content)
        background = (EXT / "background.js").read_text(encoding="utf-8")
        self.assertIn('message?.type === "SMARTFLOW_FLOW_EVIDENCE"', background)
        self.assertIn("adapter.captureEvidence(message, sender)", background)

    def test_download_keeps_golden_menu_before_passive_fallback(self):
        source = (EXT / "background.js").read_text(encoding="utf-8")
        method = source.split("async function downloadFlowResult", 1)[1].split(
            "async function inspectFlowResultDom", 1
        )[0]
        self.assertLess(method.index("await openFlowResultCard"), method.index("latestVideoEvidence"))
        self.assertLess(method.index("latestVideoEvidence"), method.index("player_blob"))
        self.assertIn("smartpostFlowDownloadReceipt", method)

    def test_core_modules_execute_in_node(self):
        router_uri = (SRC / "background/job-router.js").as_uri()
        transfer_uri = (SRC / "core/media-transfer.js").as_uri()
        script = f"""
          import assert from 'node:assert/strict';
          import {{ JobRouter }} from {router_uri!r};
          import {{ ChunkTransferStore }} from {transfer_uri!r};
          const router = new JobRouter({{ defaultTimeoutMs: 1000 }});
          router.register('capture_shopee_product', async () => ({{ value: 7 }}));
          const job = {{ id: 'CMD-TEST-1', action: 'capture_shopee_product', client_id: 'client',
            run_id: 'RUN-1', lease_token: 'LEASE-1', shot_index: 0 }};
          const first = await router.dispatch(job);
          const duplicate = await router.dispatch(job);
          assert.equal(first.ok, true);
          assert.deepEqual(first, duplicate);
          const store = new ChunkTransferStore({{ maxBytes: 32, ttlMs: 5000 }});
          store.append({{ transferId: 'TRANSFER_1', sequence: 1, totalChunks: 2, chunk: new Uint8Array([3, 4]) }});
          store.append({{ transferId: 'TRANSFER_1', sequence: 0, totalChunks: 2, chunk: new Uint8Array([1, 2]) }});
          assert.deepEqual([...store.consume('TRANSFER_1')], [1, 2, 3, 4]);
        """
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)

    def test_schema_retry_and_adapters_execute_in_node(self):
        schema_uri = (SRC / "core/message-schema.js").as_uri()
        retry_uri = (SRC / "core/retry.js").as_uri()
        shopee_uri = (SRC / "platforms/shopee/adapter.js").as_uri()
        ai_web_uri = (SRC / "platforms/ai-web/adapter.js").as_uri()
        flow_uri = (SRC / "platforms/google-flow/adapter.js").as_uri()
        script = f"""
          import assert from 'node:assert/strict';
          import {{ validateJobCommand }} from {schema_uri!r};
          import {{ isRetryableStatus, withRetry }} from {retry_uri!r};
          import {{ ShopeeAdapter }} from {shopee_uri!r};
          import {{ AIWebAdapter }} from {ai_web_uri!r};
          import {{ isAllowedMediaUrl }} from {flow_uri!r};

          const command = {{ id: 'CMD-SCHEMA-1', action: 'capture_shopee_product',
            client_id: 'client', run_id: 'RUN-1', lease_token: 'LEASE-1', shot_index: 0 }};
          assert.equal(validateJobCommand(command), command);
          assert.throws(() => validateJobCommand({{ ...command, action: 'executeRawScript' }}));
          assert.equal(isRetryableStatus(429), true);
          assert.equal(isRetryableStatus(401), false);
          let attempts = 0;
          const retryValue = await withRetry(async () => {{
            attempts += 1;
            if (attempts < 3) throw Object.assign(new Error('busy'), {{ status: 429 }});
            return 'ready';
          }}, {{ maxAttempts: 3, initialDelay: 0 }});
          assert.equal(retryValue, 'ready');
          assert.equal(attempts, 3);

          const shopee = new ShopeeAdapter();
          assert.equal(shopee.detect({{ url: 'https://shopee.co.th/item/1' }}), true);
          assert.equal(shopee.detect({{ url: 'https://shopee.co.th.evil.test/item/1' }}), false);
          const aiWeb = new AIWebAdapter();
          assert.equal((await aiWeb.status({{ id: 3, url: 'https://chatgpt.com/' }})).ready, true);
          assert.equal((await aiWeb.status({{ id: 3, url: 'https://accounts.google.com/signin' }})).ready, false);
          assert.equal(isAllowedMediaUrl('https://lh3.googleusercontent.com/media/video.mp4?id=1'), true);
          assert.equal(isAllowedMediaUrl('https://evil.test/video.mp4'), false);
        """
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)


if __name__ == "__main__":
    unittest.main()
