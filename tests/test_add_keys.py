"""The keys command has to keep every key off the screen and write a private .env.

The script runs on a real pseudo-terminal, as it would in a user's terminal, against
local stand-ins for OpenRouter, OpenAI and Google. No real key is involved.
"""

import http.server
import io
import json
import os
import pty
import select
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ballot import keys as add_keys

GOOD_KEY = "sk-or-v1-good-test-key-0123456789"
BAD_KEY = "sk-or-v1-rejected-test-key"


class FakeServices(http.server.BaseHTTPRequestHandler):
    """OpenRouter's key check, OpenAI's model list and Google's model list."""

    paths: list[str] = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        FakeServices.paths.append(self.path)
        bearer = self.headers.get("Authorization") == f"Bearer {GOOD_KEY}"
        if self.path.startswith("/api/v1/key"):
            code, body = (200 if bearer else 401), {"data": {"limit": 50, "limit_remaining": 42.5, "usage": 7.5}}
        elif self.path.startswith("/v1/models"):
            code, body = (200 if bearer else 401), {"data": [{"id": "gpt-6-astra"}, {"id": "gpt-6-luna"}]}
        else:  # Google wants the key in its own header, and answers a bad one with 400
            good = self.headers.get("x-goog-api-key") == GOOD_KEY
            code, body = (200 if good else 400), {"models": [{"name": "models/gemini-4-argon"}, {"name": "models/gemini-3.8-flash"}]}
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


LAUNCHER = """
import dataclasses, pathlib, sys
sys.path.insert(0, {root!r})
sys.argv = {argv!r}
from ballot import keys as add_keys
add_keys.ENV_FILE = pathlib.Path({env!r})
for name, path in (("openrouter", "/api/v1/key"), ("openai", "/v1/models"), ("gemini", "/v1beta/models")):
    add_keys.SERVICES[name] = dataclasses.replace(add_keys.SERVICES[name], url={url!r} + path)
add_keys.main()
"""


class AddKeys(unittest.TestCase):
    def setUp(self):
        FakeServices.paths.clear()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeServices)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = Path(self.folder.name) / ".env"

    def code(self, *args: str) -> str:
        return LAUNCHER.format(root=str(ROOT), env=str(self.env), url=f"http://127.0.0.1:{self.server.server_address[1]}",
                               argv=["add_keys.py", *args])

    def type_at_prompt(self, typed: str, service: str = "") -> tuple[int, str]:
        """Run the script on a pseudo-terminal and return its exit code and everything on screen."""
        master, slave = pty.openpty()
        args = [service, "--terminal"] if service else ["--terminal"]
        process = subprocess.Popen([sys.executable, "-c", self.code(*args)], stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        screen = b""
        sent = False
        deadline = time.time() + 20
        while time.time() < deadline:
            ready, _, _ = select.select([master], [], [], 0.1)
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                screen += chunk
            # The prompt only appears after echo is off, so typing here is hidden.
            if not sent and b"stays hidden" in screen:
                os.write(master, typed.encode() + b"\n")
                sent = True
            if process.poll() is not None and not ready:
                break
        os.close(master)
        return process.wait(), screen.decode(errors="replace")

    def test_a_good_key_is_saved_privately_and_never_shown(self):
        code, screen = self.type_at_prompt(GOOD_KEY)
        self.assertEqual(code, 0, screen)
        self.assertNotIn(GOOD_KEY, screen)
        self.assertNotIn("sk-or", screen)
        self.assertIn("OpenRouter accepted it", screen)
        self.assertIn("$42.50", screen)
        self.assertIn(f"OPENROUTER_API_KEY={GOOD_KEY}", self.env.read_text().splitlines())
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)

    def test_existing_settings_survive_and_an_old_key_is_replaced(self):
        self.env.write_text("OPENROUTER_API_KEY=old-key\nTAVILY_API_KEY=keep-me\n# a comment\n")
        self.env.chmod(0o644)
        self.type_at_prompt(GOOD_KEY)
        lines = self.env.read_text().splitlines()
        self.assertIn(f"OPENROUTER_API_KEY={GOOD_KEY}", lines)
        self.assertNotIn("OPENROUTER_API_KEY=old-key", lines)
        self.assertIn("TAVILY_API_KEY=keep-me", lines)
        self.assertIn("# a comment", lines)
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)

    def test_a_rejected_key_changes_nothing(self):
        self.env.write_text("TAVILY_API_KEY=keep-me\n")
        code, screen = self.type_at_prompt(BAD_KEY)
        self.assertNotEqual(code, 0)
        self.assertNotIn(BAD_KEY, screen)
        self.assertIn("rejected", screen)
        self.assertEqual(self.env.read_text(), "TAVILY_API_KEY=keep-me\n")

    def test_empty_input_changes_nothing(self):
        code, _ = self.type_at_prompt("")
        self.assertNotEqual(code, 0)
        self.assertFalse(self.env.exists())

    def test_it_refuses_to_read_a_key_from_a_pipe(self):
        result = subprocess.run([sys.executable, "-c", self.code("--terminal")], input=GOOD_KEY, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Run this in a terminal", result.stderr)
        self.assertFalse(self.env.exists())

    def test_no_temporary_files_are_left_behind(self):
        self.type_at_prompt(GOOD_KEY)
        self.assertEqual([p.name for p in Path(self.folder.name).iterdir()], [".env"])

    def test_invisible_paste_markers_are_removed(self):
        self.type_at_prompt(f"\x1b[200~{GOOD_KEY}\x1b[201~")
        self.assertIn(f"OPENROUTER_API_KEY={GOOD_KEY}", self.env.read_text().splitlines())

    def test_an_openai_key_is_saved_and_models_it_cannot_see_are_named(self):
        self.env.write_text(f"OPENROUTER_API_KEY={GOOD_KEY}\n")
        code, screen = self.type_at_prompt(GOOD_KEY, "openai")
        self.assertEqual(code, 0, screen)
        self.assertNotIn(GOOD_KEY, screen)
        self.assertIn("OpenAI accepted it", screen)
        self.assertIn("can't see gpt-6.1-sol, gpt-6.1-terra", screen)
        lines = self.env.read_text().splitlines()
        self.assertIn(f"OPENAI_API_KEY={GOOD_KEY}", lines)
        self.assertIn(f"OPENROUTER_API_KEY={GOOD_KEY}", lines)

    def test_a_gemini_key_goes_in_a_header_never_the_url(self):
        code, screen = self.type_at_prompt(GOOD_KEY, "gemini")
        self.assertEqual(code, 0, screen)
        self.assertIn("every model the experiment needs", screen)
        self.assertTrue(FakeServices.paths)
        self.assertFalse([p for p in FakeServices.paths if GOOD_KEY in p])
        self.assertIn(f"GEMINI_API_KEY={GOOD_KEY}", self.env.read_text().splitlines())

    def test_google_rejecting_a_key_changes_nothing(self):
        code, screen = self.type_at_prompt(BAD_KEY, "gemini")
        self.assertNotEqual(code, 0)
        self.assertIn("Gemini rejected", screen)
        self.assertFalse(self.env.exists())

    def test_check_reports_every_saved_key_without_showing_any(self):
        self.env.write_text(f"OPENROUTER_API_KEY={GOOD_KEY}\nOPENAI_API_KEY={GOOD_KEY}\nGEMINI_API_KEY={BAD_KEY}\n")
        result = subprocess.run([sys.executable, "-c", self.code("--check")], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OpenRouter: key accepted. Spending limit left on this key: $42.50.", result.stdout)
        self.assertIn("OpenAI: key accepted. It can't see gpt-6.1-sol, gpt-6.1-terra.", result.stdout)
        self.assertIn("Gemini: key REJECTED.", result.stdout)
        self.assertNotIn(GOOD_KEY, result.stdout + result.stderr)
        self.assertNotIn(BAD_KEY, result.stdout + result.stderr)


class Window(unittest.TestCase):
    """The macOS window path. osascript is replaced, so no window ever opens here."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.env = Path(self.folder.name) / ".env"
        self.shown: list[str] = []

    def run_main(self, ask_result: subprocess.CompletedProcess, accepted=True):
        def fake_run(command, **kwargs):
            self.assertEqual(command[:2], ["osascript", "-e"])
            script = command[2]
            self.assertNotIn(GOOD_KEY, script)  # the key must never be in a command line
            if "default answer" in script:
                return ask_result
            self.shown.append(script)
            return subprocess.CompletedProcess(command, 0)

        with (
            mock.patch.object(add_keys, "ENV_FILE", self.env),
            mock.patch.object(add_keys.subprocess, "run", fake_run),
            mock.patch.object(add_keys, "check_key", return_value=(accepted, {"data": {"limit_remaining": 12.5}})),
            mock.patch.object(add_keys.sys, "platform", "darwin"),
            mock.patch.object(add_keys.sys, "argv", ["add_keys.py"]),
            mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
        ):
            add_keys.main()
            return stdout.getvalue()

    def test_a_key_from_the_window_is_saved_and_the_result_is_shown(self):
        output = self.run_main(subprocess.CompletedProcess([], 0, stdout=f"{GOOD_KEY}\n", stderr=""))
        self.assertIn(f"OPENROUTER_API_KEY={GOOD_KEY}", self.env.read_text().splitlines())
        self.assertEqual(stat.S_IMODE(self.env.stat().st_mode), 0o600)
        self.assertIn("OpenRouter accepted it", self.shown[0])
        self.assertIn("$12.50", output)
        self.assertNotIn(GOOD_KEY, output)

    def test_cancel_changes_nothing(self):
        with self.assertRaises(SystemExit) as caught:
            self.run_main(subprocess.CompletedProcess([], 1, stdout="", stderr="User canceled. (-128)"))
        self.assertIn("Cancelled", str(caught.exception))
        self.assertFalse(self.env.exists())

    def test_a_rejected_key_is_reported_in_the_window(self):
        with self.assertRaises(SystemExit):
            self.run_main(subprocess.CompletedProcess([], 0, stdout=f"{GOOD_KEY}\n", stderr=""), accepted=False)
        self.assertIn("rejected", self.shown[0])
        self.assertFalse(self.env.exists())

    def test_if_the_window_cannot_open_it_falls_back_to_the_terminal(self):
        with mock.patch.object(add_keys, "ask_in_terminal", return_value=GOOD_KEY) as terminal:
            self.run_main(subprocess.CompletedProcess([], 1, stdout="", stderr="no user interaction allowed (-1713)"))
        terminal.assert_called_once()
        self.assertIn(f"OPENROUTER_API_KEY={GOOD_KEY}", self.env.read_text().splitlines())


if __name__ == "__main__":
    unittest.main()
