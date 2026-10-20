"""All Claude calls are mocked; never invokes an installed model or reads auth files."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_claude-delegate"
LOADER = SourceFileLoader("claude_delegate", str(SCRIPT))
BRIDGE = module_from_spec(spec_from_loader(LOADER.name, LOADER))
LOADER.exec_module(BRIDGE)
TASK = {
    "objective": "Explain a synthetic parser failure.",
    "scope": "Only the supplied toy example.",
    "context": "parse('2') returned None; expected integer 2.",
    "acceptance": "Explain one fix and propose a regression test.",
    "reason": "Sol repeated the same failure after a changed hypothesis.",
    "attempts": [{"failure": "expected 2, got None"}, {"failure": "expected 2, got None"}],
    "authorization": "allowed", "non_confidential": True, "safety_status": "clear",
}
ANSWER = {"answer": "Convert the supplied string.", "proposed_diff": "--- a/toy.py\n+++ b/toy.py\n",
          "suggested_tests": ["Run the caller's parser regression test."], "unresolved": []}
SUCCESS = {"type": "result", "subtype": "success", "is_error": False,
           "structured_output": ANSWER, "permission_denials": []}
USAGE = """Settings Status Config Usage Stats
Session
Total duration (API):  0s
Usage: 0 input, 0 output, 0 cache read, 0 cache write
Current session
25% 25% used
Current week (all models)
26% 26% used
Usage credits
Usage credits are off · /usage-credits to turn them on
Esc to cancel
"""


def billing_snapshot():
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "usage_credits_enabled": False}


class ClaudeDelegate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "task.json"
        self.run_dir = self.root / "run"
        self.source.write_text(json.dumps(TASK))
        BRIDGE.prepare(self.source, self.run_dir)

    def status(self):
        return json.loads((self.run_dir / "status.json").read_text())

    def fake(self, payload=SUCCESS, exit_code=0, delay=0):
        exe = self.root / "fake-claude"
        exe.write_text("#!/usr/bin/env python3\nimport json,sys,time\n"
                       "from pathlib import Path\n"
                       f"Path({str(self.root / 'received.json')!r}).write_text(json.dumps("
                       "{'args':sys.argv[1:],'prompt':sys.stdin.read(),'cwd':str(Path.cwd()),"
                       "'files':list(str(p.name) for p in Path.cwd().iterdir())}))\n"
                       f"time.sleep({delay})\n"
                       f"print({json.dumps(payload)!r})\n"
                       f"sys.exit({exit_code})\n")
        exe.chmod(0o700)
        return str(exe)

    def execute_fake(self, payload=SUCCESS, exit_code=0, delay=0, timeout=3):
        # No public --mock/--force/billing-attestation flag exists in the installed CLI.
        # Only this test process replaces the internal authoritative billing gate.
        with patch.object(BRIDGE, "find_claude", return_value=self.fake(payload, exit_code, delay)), \
                patch.object(BRIDGE, "verify_contract", side_effect=lambda *args: billing_snapshot()):
            return BRIDGE.run(self.run_dir, timeout)

    def test_prepare_reports_failures_without_calling_claude(self):
        self.assertEqual(self.status()["state"], "prepared")
        self.assertTrue(self.status()["repeated_failure"])
        self.assertFalse(self.status()["model_started"])
        self.assertEqual(self.run_dir.stat().st_mode & 0o777, 0o700)

    def test_success_collects_structured_answer_patch_and_process_status(self):
        self.assertEqual(self.execute_fake(), 0)
        self.assertEqual(self.status()["state"], "completed")
        self.assertEqual(self.status()["process_exit"], 0)
        self.assertFalse(self.status()["tests_executed"])
        self.assertEqual(json.loads((self.run_dir / "result.json").read_text()), ANSWER)
        self.assertEqual((self.run_dir / "proposed.patch").read_text(), ANSWER["proposed_diff"])
        received = json.loads((self.root / "received.json").read_text())
        args = received["args"]
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", args)
        self.assertIn("--no-session-persistence", args)
        self.assertNotIn("--dangerously-skip-permissions", args)
        self.assertNotIn("--model", args)
        self.assertNotIn("--effort", args)
        self.assertEqual(received["files"], [])
        self.assertIn(TASK["objective"], received["prompt"])
        self.assertFalse((self.run_dir / "toy.py").exists())

    def test_nonzero_exit_is_failure_even_with_success_json(self):
        self.assertEqual(self.execute_fake(exit_code=7), 1)
        self.assertEqual(self.status()["state"], "failed")
        self.assertEqual(self.status()["process_exit"], 7)

    def test_error_result_with_exit_zero_is_failure(self):
        self.assertEqual(self.execute_fake({**SUCCESS, "is_error": True}), 1)
        self.assertEqual(self.status()["state"], "failed")

    def test_permission_denial_is_never_success(self):
        self.assertEqual(self.execute_fake({**SUCCESS, "permission_denials": [{"tool": "Bash"}]}), 1)
        self.assertEqual(self.status()["state"], "permission_denied")

    def test_invalid_structured_output_is_failure(self):
        self.assertEqual(self.execute_fake({**SUCCESS, "structured_output": {"answer": "missing fields"}}), 1)
        self.assertEqual(self.status()["state"], "invalid_output")

    def test_timeout_stops_our_child_and_collects_partial_output(self):
        self.assertEqual(self.execute_fake(delay=10, timeout=1), 1)
        self.assertEqual(self.status()["state"], "timeout")
        self.assertTrue((self.run_dir / "stdout.json").exists())

    def test_no_automatic_retry(self):
        self.execute_fake()
        with self.assertRaises(ValueError):
            BRIDGE.run(self.run_dir, 3)

    def test_attempt_marker_stops_concurrent_or_interrupted_retry(self):
        (self.run_dir / "attempted").touch()
        with self.assertRaises(FileExistsError):
            BRIDGE.run(self.run_dir, 3)

    def test_changed_task_is_blocked_before_authentication(self):
        task = {**TASK, "objective": "A changed question"}
        (self.run_dir / "task.json").write_text(json.dumps(task))
        with patch.object(BRIDGE, "find_claude") as lookup:
            with self.assertRaises(BRIDGE.Blocked):
                BRIDGE.run(self.run_dir, 3)
            lookup.assert_not_called()

    def test_pending_denied_confidential_tasks_cannot_prepare(self):
        for field, value in (("authorization", "pending"), ("authorization", "denied"),
                             ("non_confidential", False), ("safety_status", "refused")):
            with self.subTest(field=field, value=value):
                self.source.write_text(json.dumps({**TASK, field: value}))
                with self.assertRaises(BRIDGE.Blocked):
                    BRIDGE.prepare(self.source, self.root / "rejected")
                self.assertFalse((self.root / "rejected").exists())

    def test_cannot_overwrite_prepared_run(self):
        with self.assertRaises(FileExistsError):
            BRIDGE.prepare(self.source, self.run_dir)

    def test_max_login_alone_fails_closed_without_model_call(self):
        auth = subprocess.CompletedProcess([], 0, json.dumps({
            "loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty",
            "subscriptionType": "max", "email": "PRIVATE_NOT_REPORTED"}), "")
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(BRIDGE, "find_claude", return_value="fake-claude"), \
                patch.object(BRIDGE.subprocess, "run", return_value=auth) as status, \
                patch.object(BRIDGE, "invoke") as model:
            self.assertEqual(BRIDGE.run(self.run_dir, 3), 78)
            self.assertEqual(status.call_args_list[0].args[0], ["fake-claude", "auth", "status", "--json"])
            model.assert_not_called()
        self.assertEqual(self.status()["state"], "blocked")
        self.assertNotIn("PRIVATE_NOT_REPORTED", (self.run_dir / "status.json").read_text())

    def test_api_provider_override_blocks_before_any_cli_call(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "TEST_ONLY"}, clear=True), \
                patch.object(BRIDGE.subprocess, "run") as cli:
            with self.assertRaises(BRIDGE.Blocked):
                BRIDGE.verify_contract("fake-claude", self.root)
            cli.assert_not_called()

    def test_live_usage_requires_explicit_disabled_credits_and_available_limits(self):
        result = BRIDGE.parse_usage(USAGE)
        self.assertFalse(result["usage_credits_enabled"])
        self.assertEqual(result["observed_usage_percentages"], [25, 26])
        for bad in (USAGE.replace("are off", "are on"),
                    USAGE.replace("25% 25%", "100% 100%"),
                    USAGE + "Showing last-known usage from 1m ago",
                    USAGE.replace("0 output", "1 output"),
                    USAGE.replace("Current week (all models)", "Other section"),
                    USAGE.replace("26% 26% used", "unrecognized bar")):
            with self.subTest(bad=bad):
                with self.assertRaises(BRIDGE.Blocked):
                    BRIDGE.parse_usage(bad)

    def test_fresh_login_and_live_usage_pass_but_version_changes_block(self):
        auth = subprocess.CompletedProcess([], 0, json.dumps({
            "loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty",
            "subscriptionType": "max"}), "")
        version = subprocess.CompletedProcess([], 0, BRIDGE.VERIFIED_VERSION, "")
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(BRIDGE.subprocess, "run", side_effect=[auth, version]), \
                patch.object(BRIDGE, "read_live_usage", return_value=billing_snapshot()) as live:
            self.assertFalse(BRIDGE.verify_contract("fake", self.root)["usage_credits_enabled"])
            live.assert_called_once()
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(BRIDGE.subprocess, "run", side_effect=[auth, auth]), \
                patch.object(BRIDGE, "read_live_usage") as live:
            with self.assertRaises(BRIDGE.Blocked):
                BRIDGE.verify_contract("fake", self.root)
            live.assert_not_called()

    def test_usage_tui_sends_only_builtin_usage_and_stops_child(self):
        trusted = self.root / ".local/share/chezmoi"
        trusted.mkdir(parents=True)
        fake = self.root / "fake-usage-cli"
        received = self.root / "usage-input.txt"
        fake.write_text("#!/usr/bin/env python3\nimport sys,time\nfrom pathlib import Path\n"
                        "print('Claude Code v2.1.301\\n$',flush=True)\n"
                        "line=sys.stdin.readline()\n"
                        f"Path({str(received)!r}).write_text(line)\n"
                        f"print({USAGE!r},flush=True)\n"
                        "time.sleep(10)\n")
        fake.chmod(0o700)
        with patch.object(BRIDGE.Path, "home", return_value=self.root):
            snapshot = BRIDGE.read_live_usage(str(fake))
        self.assertEqual(received.read_text(), "/usage\n")
        self.assertFalse(snapshot["usage_credits_enabled"])

    def test_expired_check_never_invokes_model(self):
        with patch.object(BRIDGE, "find_claude", return_value="fake"), \
                patch.object(BRIDGE, "verify_contract", return_value={"checked_at": "2020-01-01T00:00:00+00:00"}), \
                patch.object(BRIDGE, "invoke") as model:
            self.assertEqual(BRIDGE.run(self.run_dir, 3), 78)
            model.assert_not_called()
        self.assertEqual(self.status()["state"], "blocked")


if __name__ == "__main__":
    unittest.main()
