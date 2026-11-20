import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import launch


class TestLaunch(unittest.TestCase):
    def test_browser_command_windows_prefers_app_mode(self):
        cmd = launch.browser_command("http://localhost:8601", "win32", exists=lambda p: p.endswith("msedge.exe"))
        self.assertTrue(cmd[0].endswith("msedge.exe"))
        self.assertIn("--app=http://localhost:8601", cmd)
        self.assertIsNone(launch.browser_command("http://x", "win32", exists=lambda p: False))  # default browser

    def test_free_port_skips_a_busy_port(self):
        with socket.socket() as busy:
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            self.assertNotEqual(launch.free_port(port), port)

    def test_running_port_ignores_stale_file(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(launch, "PORT_FILE", Path(tmp) / "app.port"):
            self.assertIsNone(launch.running_port())  # no file
            launch.PORT_FILE.write_text("1")  # nothing serves on port 1
            self.assertIsNone(launch.running_port())

    def test_icon(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(launch, "ROOT", Path(tmp)):
            out = launch.make_icon()
            self.assertGreater((out / "icon.png").stat().st_size, 0)
            self.assertGreater((out / "icon.ico").stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
