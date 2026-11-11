import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

NOTIFY = Path(__file__).resolve().parent.parent / "src" / "hooks" / "notify.py"


class TestNotify(unittest.TestCase):
    """Runs notify.py with stub `ps` and `osascript` first on PATH, so no tty
    is found and no real notification is ever sent."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.bin = Path(cls._tmp.name)
        cls.calls = cls.bin / "osascript.calls"
        stubs = {
            "ps": "#!/bin/sh\necho '?? 1'\n",
            "osascript": f'#!/bin/sh\necho called >> "{cls.calls}"\n',
        }
        for name, body in stubs.items():
            p = cls.bin / name
            p.write_text(body)
            p.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_notify(self, payload, raw=None):
        env = {"PATH": f"{self.bin}:/usr/bin:/bin"}
        return subprocess.run(
            [sys.executable, str(NOTIFY)],
            input=raw if raw is not None else json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            timeout=15,
        )

    def assertSilentOk(self, r):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "")

    def test_events_exit_zero_with_empty_stdout(self):
        events = [
            {"hook_event_name": "PermissionRequest", "tool_name": "Bash",
             "tool_input": {"command": "ls"}, "cwd": "/tmp/proj"},
            {"hook_event_name": "PermissionRequest", "tool_name": "Edit",
             "tool_input": {"file_path": "/tmp/x"}},
            {"hook_event_name": "PermissionRequest"},
            {"hook_event_name": "Notification", "notification_type": "idle_prompt"},
            {"hook_event_name": "Notification", "notification_type": "elicitation_dialog"},
            {"hook_event_name": "Notification", "notification_type": "permission_prompt"},
            {"hook_event_name": "Notification", "message": "custom; message"},
            {"hook_event_name": "Stop", "cwd": "/tmp/proj"},
            {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
             "tool_input": {"questions": [{"question": "Hangisi?"}]}},
            {"hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
             "tool_input": {"questions": ["bad"]}},
            {"hook_event_name": "PreToolUse", "tool_name": "Bash"},
            {"hook_event_name": "SessionStart"},
            {},
        ]
        for ev in events:
            with self.subTest(event=ev):
                self.assertSilentOk(self.run_notify(ev))

    def test_malformed_input(self):
        for raw in ["", "not json", "[]"]:
            with self.subTest(raw=raw):
                self.assertSilentOk(self.run_notify(None, raw=raw))

    def test_uses_stubbed_fallback_only(self):
        self.calls.unlink(missing_ok=True)
        self.assertSilentOk(self.run_notify({"hook_event_name": "Stop"}))
        self.assertTrue(self.calls.exists(), "expected stub osascript fallback")

    def test_ask_user_question_notifies(self):
        self.calls.unlink(missing_ok=True)
        self.assertSilentOk(self.run_notify({
            "hook_event_name": "PreToolUse", "tool_name": "AskUserQuestion",
            "tool_input": {"questions": [{"question": "Hangisi?"}]}}))
        self.assertTrue(self.calls.exists(), "expected a notification for a question")

    def test_other_pre_tool_use_is_silent(self):
        self.calls.unlink(missing_ok=True)
        self.assertSilentOk(self.run_notify({"hook_event_name": "PreToolUse", "tool_name": "Bash"}))
        self.assertFalse(self.calls.exists(), "only AskUserQuestion should notify")


if __name__ == "__main__":
    unittest.main()
