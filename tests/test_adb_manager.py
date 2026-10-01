import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.adb_manager import AdbManager


def completed(stdout="", stderr="", code=0):
    return subprocess.CompletedProcess([], code, stdout=stdout, stderr=stderr)


class AdbManagerTests(unittest.TestCase):
    def test_parses_connected_unauthorized_and_offline(self):
        output = "List of devices attached\nAAA device product:x model:Phone_A\nBBB unauthorized transport_id:2\nCCC offline transport_id:3\n"
        manager = AdbManager("adb.exe")
        with patch.object(manager, "run", return_value=completed(output)):
            devices = manager.devices()
        self.assertEqual([(item.serial, item.state) for item in devices], [("AAA", "device"), ("BBB", "unauthorized"), ("CCC", "offline")])

    def test_requires_serial_for_device_command(self):
        manager = AdbManager("adb.exe")
        with self.assertRaises(RuntimeError): manager.shell("getprop", "ro.product.model")

    def test_reads_device_information(self):
        manager = AdbManager("adb.exe", "SERIAL")
        values = {
            ("dumpsys", "battery"): "level: 82\n",
            ("getprop", "ro.product.manufacturer"): "samsung\n",
            ("getprop", "ro.product.model"): "SM-TEST\n",
            ("getprop", "ro.build.version.release"): "16\n",
            ("wm", "size"): "Physical size: 1080x2340\n",
        }
        with patch.object(manager, "shell", side_effect=lambda *args, **kwargs: completed(values[args])):
            info = manager.info()
        self.assertEqual(info["battery"], "82%")
        self.assertEqual(info["screen"], "1080x2340")
        self.assertEqual(info["model"], "SM-TEST")

    def test_does_not_save_failed_screenshot(self):
        with tempfile.TemporaryDirectory() as temp:
            manager = AdbManager("adb.exe", "SERIAL", Path(temp))
            with patch.object(manager, "run", return_value=completed(b"", b"device offline", 1)):
                with self.assertRaises(RuntimeError): manager.screenshot()
            self.assertFalse(list((Path(temp) / "screenshots").glob("*.png")))


if __name__ == "__main__": unittest.main()
