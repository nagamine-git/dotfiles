"""No model calls: verify service arguments and status display with disposable homes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATEWAY = ROOT / "dot_local/bin/executable_agent-gateway"
STATUS = ROOT / "dot_local/bin/executable_claude-statusline"


class AgentLifecycle(unittest.TestCase):
    def test_gateway_inherits_settings_and_isolates_one_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            executable = home / ".local/bin/claude"
            executable.parent.mkdir(parents=True)
            executable.write_text('#!/usr/bin/env python3\nimport json, sys\nprint(json.dumps(sys.argv[1:]))\n')
            executable.chmod(0o700)
            result = subprocess.run(["bash", str(GATEWAY), "host/dotfiles/ops"],
                                    env={**os.environ, "HOME": tmp}, capture_output=True, text=True, check=True)
            args = json.loads(result.stdout)
            self.assertEqual(args, ["remote-control", "--name", "host/dotfiles/ops", "--spawn",
                                    "worktree", "--capacity", "1", "--no-create-session-in-dir"])

    def test_gateway_rejects_missing_name_before_start(self):
        result = subprocess.run(["bash", str(GATEWAY)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_status_uses_native_name_without_starting_a_model_or_reading_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            trap = home / "claude"
            trap.write_text('#!/bin/sh\ntouch "$HOME/unexpected-model-call"\nexit 1\n')
            trap.chmod(0o700)
            payload = {"model": {"display_name": "Opus 5.5"}, "effort": {"level": "max"},
                       "context_window": {"used_percentage": 72.8}, "session_id": "same-id",
                       "session_name": "host/lab/ops/整理\u001b\n", "transcript_path": "/unreadable"}
            env = {**os.environ, "HOME": tmp, "NO_COLOR": "1", "PATH": tmp + ":" + os.environ["PATH"]}
            result = subprocess.run(["bash", str(STATUS)], input=json.dumps(payload), env=env,
                                    capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, "Opus 5.5 max | ctx 72% | host/lab/ops/整理\n")
            self.assertFalse((home / "unexpected-model-call").exists())
            self.assertFalse((home / ".cache/claude-statusline").exists())
            payload.pop("session_name")
            result = subprocess.run(["bash", str(STATUS)], input=json.dumps(payload), env=env,
                                    capture_output=True, text=True, check=True)
            self.assertIn("same-id", result.stdout)

    def test_status_handles_malformed_input(self):
        result = subprocess.run(["bash", str(STATUS)], input="invalid", capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
