import socket
import subprocess
import sys
import textwrap
import time
import unittest

from desktop.hybrid import HybridHost


_ADOPTED_ENGINE = r"""
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

port = int(sys.argv[1])
ignore_shutdown = len(sys.argv) > 2 and sys.argv[2] == 'ignore'
server = None

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return
    def do_GET(self):
        if self.path != '/health':
            self.send_error(404)
            return
        raw = json.dumps({'ok': True, 'desktop_ui': 'hybrid', 'engine_pid': os.getpid()}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_POST(self):
        size = int(self.headers.get('Content-Length', '0'))
        body = json.loads(self.rfile.read(size).decode())
        if self.path != '/api/desktop/action' or body.get('action') != 'shutdown':
            self.send_error(400)
            return
        raw = b'{"ok":true}'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
        if not ignore_shutdown:
            threading.Thread(target=server.shutdown, daemon=True).start()

server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
server.serve_forever()
server.server_close()
"""


class HybridShutdownTests(unittest.TestCase):
    @staticmethod
    def _spawn_engine(port, ignore_shutdown=False):
        arguments = [sys.executable, "-c", textwrap.dedent(_ADOPTED_ENGINE), str(port)]
        if ignore_shutdown:
            arguments.append("ignore")
        return subprocess.Popen(
            arguments,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    @staticmethod
    def _free_port():
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            return int(probe.getsockname()[1])

    def _assert_engine_stops(self, ignore_shutdown=False):
        port = self._free_port()
        process = self._spawn_engine(port, ignore_shutdown=ignore_shutdown)
        host = HybridHost(port=port)
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not host._ready():
                time.sleep(0.05)
            self.assertTrue(host._ready())
            self.assertEqual(host.engine_pid, process.pid)
            self.assertFalse(host.owns_engine)

            host.stop()

            process.wait(timeout=5)
            self.assertIsNotNone(process.returncode)
            self.assertFalse(host._ready())
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    def test_adopted_engine_is_stopped_when_hybrid_window_closes(self):
        self._assert_engine_stops()

    def test_unresponsive_adopted_engine_is_terminated_by_exact_health_pid(self):
        self._assert_engine_stops(ignore_shutdown=True)


if __name__ == "__main__":
    unittest.main()
