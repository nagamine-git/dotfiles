"""cc-implement tests: every Claude process and stream is faked; no auth file, model or network.

One test starts a synthetic stand-in script as the native child to check its real session.
"""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import MagicMock, call, patch

REAL_POPEN, REAL_KILL = subprocess.Popen, os.kill  # Before setUp replaces them.
ROOT = Path(__file__).resolve().parents[1]
LOADER = SourceFileLoader("cc_implement", str(ROOT / "home/dot_local/bin/executable_cc-implement"))
CC = module_from_spec(spec_from_loader(LOADER.name, LOADER))
LOADER.exec_module(CC)
PROFILE_SOURCE = ROOT / "home/dot_claude/profiles/coder-opus.json"
# The only four values the launcher adds, both as inline --settings env and in the child's copied env.
FORCED = {"CLAUDE_CODE_SUBAGENT_MODEL": "claude-opus-5-5", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1",
          "CLAUDE_CODE_EFFORT_LEVEL": "xhigh", "CC_IMPLEMENT_USAGE_NO_MODEL_CALL": "1"}
SETTINGS = ('{"env":{"CC_IMPLEMENT_USAGE_NO_MODEL_CALL":"1","CLAUDE_CODE_EFFORT_LEVEL":"xhigh",'
            '"CLAUDE_CODE_SUBAGENT_MODEL":"claude-opus-5-5","CLAUDE_CODE_SUBAGENT_MODEL_FORCE":"1"},'
            '"modelSettings":{"claude-opus-5-5":{"effortLevel":"xhigh"}}}')
SCOPE = {"subagent_model": "claude-opus-5-5", "subagent_effort": "xhigh", "subagent_scope": "all",
         "min_cli_version": "2.1.292"}
AUTH = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "max",
        "email": "synthetic@example.test", "orgId": "SYNTHETIC_ORG_ID"}
PROMPT = "SYNTHETIC_PRIVATE_PROMPT"
# Synthetic stream-json events shaped like native print mode; private-looking values must never leak.
INIT = {"type": "system", "subtype": "init", "model": "claude-opus-5-5", "claude_code_version": "2.1.314",
        "cwd": "/SYNTHETIC_PRIVATE_DIR", "session_id": "SYNTHETIC_SESSION_ID", "tools": ["Edit"]}
ASSISTANT = {"type": "assistant", "parent_tool_use_id": None, "session_id": "SYNTHETIC_SESSION_ID",
             "message": {"model": "claude-opus-5-5", "content": [
                 {"type": "text", "text": "SYNTHETIC_ASSISTANT_TEXT"},
                 {"type": "tool_use", "name": "Edit", "input": {"file_path": "/SYNTHETIC_PRIVATE_DIR/a.py"}}]}}
TOOL_RESULT = {"type": "user", "parent_tool_use_id": None,
               "message": {"content": [{"type": "tool_result", "content": "SYNTHETIC_TOOL_OUTPUT"}]}}
RESULT = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3,
          "result": "SYNTHETIC_FINAL_TEXT", "session_id": "SYNTHETIC_SESSION_ID", "total_cost_usd": 9.87,
          "usage": {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 30,
                    "cache_creation_input_tokens": 40, "service_tier": "SYNTHETIC_TIER"},
          "modelUsage": {"claude-opus-5-5": {"inputTokens": 10, "outputTokens": 20, "cacheReadInputTokens": 30,
                                             "cacheCreationInputTokens": 40, "costUSD": 9.87}}}
PRIVATE = (PROMPT, "SYNTHETIC_PRIVATE_DIR", "SYNTHETIC_SESSION_ID", "SYNTHETIC_ASSISTANT_TEXT",
           "SYNTHETIC_TOOL_OUTPUT", "SYNTHETIC_FINAL_TEXT", "SYNTHETIC_TIER", "9.87", "cost")


def lines(*events):
    return [event if isinstance(event, bytes) else json.dumps(event).encode() + b"\n" for event in events]


def retry(code, status):
    return {"type": "system", "subtype": "api_retry", "attempt": 1, "max_retries": 10, "retry_delay_ms": 500,
            "error_status": status, "error": code}


class CcImplement(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.profile = self.root / "coder-opus.json"
        self.profile.write_text(PROFILE_SOURCE.read_text())
        self.auth, self.auth_code, self.version, self.version_code = AUTH, 0, "2.1.314 (Claude Code)", 0
        self.stderr_at_auth = None
        self.proc = MagicMock()
        self.proc.__enter__.return_value = self.proc
        self.proc.__exit__.return_value = False
        self.proc.wait.return_value = 0
        no_other_process = AssertionError("Only the faked native claude may be started or signalled")
        patches = [patch.object(CC, "PROFILE", self.profile),
                   patch.object(CC, "find_claude", return_value="/synthetic/claude"),
                   patch.dict(os.environ, {"PATH": "/synthetic/bin", "HOME": str(self.root)}, clear=True),
                   patch("socket.socket", side_effect=AssertionError("No network in tests")),
                   patch("socket.create_connection", side_effect=AssertionError("No network in tests")),
                   *[patch.object(CC.os, name, side_effect=no_other_process)
                     for name in ("kill", "killpg", "system", "execv", "execvp", "execvpe", "posix_spawn",
                                  "posix_spawnp")],
                   patch.object(CC.subprocess, "run", side_effect=self.fake_run),
                   patch.object(CC.subprocess, "Popen", return_value=self.proc)]
        started = []
        for p in patches:
            started.append(p.start())
            self.addCleanup(p.stop)
        self.run_native, self.popen = started[-2:]

    def fake_run(self, command, **kwargs):
        if command[1:] == ["auth", "status", "--json"]:
            self.stderr_at_auth = sys.stderr.getvalue()  # What was reported before the read started.
            if isinstance(self.auth, Exception):
                raise self.auth
            text = self.auth if isinstance(self.auth, str) else json.dumps(self.auth)
            return subprocess.CompletedProcess(command, self.auth_code, text, "")
        if command[1:] == ["--version"]:
            if isinstance(self.version, Exception):
                raise self.version
            return subprocess.CompletedProcess(command, self.version_code, self.version + "\n", "")
        raise AssertionError("Unexpected native command")

    def main(self, argv):
        # A byte-backed stdout, since --observe passes native bytes through unchanged.
        out, err = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=True), io.StringIO()
        with patch("sys.stdout", out), patch("sys.stderr", err):
            code = CC.main(argv)
        return code, out.buffer.getvalue().decode(), err.getvalue()

    def observe(self, stream, raw=0):
        self.proc.stdout = iter(stream) if isinstance(stream, list) else stream
        self.proc.wait.return_value = raw
        code, out, err = self.main(["--observe", "-p", PROMPT])
        for private in PRIVATE:
            self.assertNotIn(private, err)
        self.assertNotIn("unavailable", err.lower())
        return code, out, err, [json.loads(line) for line in err.splitlines()]

    def fixed(self):
        return ["--agent", "coder", "--model", "claude-opus-5-5", "--effort", "xhigh", "--settings", SETTINGS]

    def child_env(self):
        """What the native child must get: the caller's environment at launch with only FORCED set."""
        return {**os.environ, **FORCED}

    def test_profile_source_contains_only_per_model_xhigh(self):
        data = json.loads(PROFILE_SOURCE.read_text())
        self.assertEqual(data, {"modelSettings": {"claude-opus-5-5": {"effortLevel": "xhigh"}}})
        self.assertEqual(data, CC.PROFILE_CONTENT)

    def test_dry_run_prints_only_fixed_selection_and_starts_nothing(self):
        code, out, err = self.main(["--dry-run", "-p", PROMPT, "--add-dir", "/SYNTHETIC_PRIVATE_DIR"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {
            "dry_run": True, "tool": "claude", "agent": "coder", "model": "claude-opus-5-5",
            "effort": "xhigh", **SCOPE, "profile": str(self.profile), "selection_flags": self.fixed()})
        self.assertNotIn(PROMPT, out + err)
        self.assertNotIn("SYNTHETIC_PRIVATE_DIR", out + err)
        self.run_native.assert_not_called()
        self.popen.assert_not_called()

    def test_conflicting_selection_session_and_subcommand_arguments_are_rejected(self):
        cases = [["--model", "SYNTHETIC_VALUE"], ["--model=SYNTHETIC_VALUE"], ["--effort", "max"],
                 ["--effort=high"], ["--fallback-model", "sonnet"], ["--agent", "other"], ["--agent=other"],
                 ["--agents", "{}"], ["--settings", "SYNTHETIC_VALUE.json"], ["--settings={}"],
                 ["--setting-sources", "user"], ["--setting-sources=user"], ["--resume"],
                 ["--resume=SYNTHETIC_VALUE"], ["-r"], ["-rSYNTHETIC_VALUE"], ["-r=SYNTHETIC_VALUE"],
                 ["--continue"], ["-c"], ["-pc"], ["-vr"], ["--fork-session"], ["--from-pr", "1"],
                 ["--teleport"], ["--cloud"], ["--bare"], ["--safe-mode"], ["update"], ["auth"],
                 ["--dry-run", PROMPT, "--model", "opus"]]
        for argv in cases:
            code, out, err = self.main(argv)
            self.assertEqual(code, 2, argv)
            self.assertEqual(json.loads(err)["state"], "conflict")
            self.assertEqual(out, "")
            self.assertNotIn("SYNTHETIC_VALUE", err)
            self.assertNotIn(PROMPT, err)
        self.run_native.assert_not_called()
        self.popen.assert_not_called()

    def test_ordinary_options_and_prompt_are_forwarded_after_fixed_flags(self):
        argv = ["-p", "--add-dir", "/tmp/synthetic", "--debug=mcp", "-dc", "-n", "name",
                "--permission-mode", "plan", PROMPT, "--", "-c and --model are prompt text"]
        code, out, err = self.main(argv)
        self.assertEqual(code, 0)
        self.assertEqual(self.popen.call_args.args[0], ["/synthetic/claude", *self.fixed(), *argv])
        # Only the copied environment changes; terminal, stdin/stdout and cwd are inherited.
        self.assertEqual(self.popen.call_args.kwargs, {"env": self.child_env()})
        start, finish = [json.loads(line) for line in err.splitlines()]
        self.assertEqual((start["record"], start["model"], start["effort"], start["agent"], start["version"]),
                         ("cc_implement_start", "claude-opus-5-5", "xhigh", "coder", "2.1.314 (Claude Code)"))
        self.assertEqual({key: start[key] for key in SCOPE}, SCOPE)
        self.assertIs(start["subscription_auth"], True)
        self.assertIn("started_at", start)
        self.assertEqual((finish["record"], finish["exit_code"], finish["tests"], finish["rework"]),
                         ("cc_implement_finish", 0, "unknown", "unknown"))
        self.assertGreaterEqual(finish["duration_seconds"], 0)
        for private in (PROMPT, "/tmp/synthetic", "synthetic@example.test", "SYNTHETIC_ORG_ID"):
            self.assertNotIn(private, out + err)

    def test_effort_environment_conflict_is_reported_not_unset(self):
        for level in ("max", "high", "XHIGH"):
            with patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": level}):
                code, _, err = self.main([])
                self.assertEqual(code, 2)
                self.assertIn("CLAUDE_CODE_EFFORT_LEVEL", err)
                self.assertEqual(os.environ["CLAUDE_CODE_EFFORT_LEVEL"], level)
        self.popen.assert_not_called()
        for level in ("xhigh", ""):
            with patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": level}):
                self.assertEqual(self.main([])[0], 0)

    def test_unverified_subscription_or_auth_override_blocks_without_switching(self):
        for auth in [{**AUTH, "apiProvider": "bedrock"}, {**AUTH, "authMethod": "api_key"},
                     {**AUTH, "subscriptionType": None}, {**AUTH, "loggedIn": False}, "not json"]:
            self.auth = auth
            code, _, err = self.main([PROMPT])
            self.assertEqual(code, 78)
            self.assertNotIn("synthetic@example.test", err)
            self.assertNotIn(PROMPT, err)
        self.auth = AUTH
        for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CONFIG_DIR"):
            with patch.dict(os.environ, {name: "SYNTHETIC_SECRET_VALUE"}):
                code, _, err = self.main(["--dry-run"])
            self.assertEqual(code, 78)
            self.assertIn(name, err)
            self.assertNotIn("SYNTHETIC_SECRET_VALUE", err)
        self.popen.assert_not_called()

    def test_profile_must_be_the_exact_regular_file(self):
        valid = self.profile.read_text()
        for content in [{**CC.PROFILE_CONTENT, "permissions": {"allow": ["Bash"]}},
                        {"modelSettings": {"claude-opus-5-5": {"effortLevel": "max"}}}, {}]:
            self.profile.write_text(json.dumps(content))
            self.assertEqual(self.main(["--dry-run"])[0], 78)
        self.profile.unlink()
        self.assertEqual(self.main(["--dry-run"])[0], 78)
        target = self.root / "target.json"
        target.write_text(valid)
        self.profile.symlink_to(target)
        self.assertEqual(self.main(["--dry-run"])[0], 78)
        self.popen.assert_not_called()

    def test_native_exit_and_signal_status_are_reported(self):
        self.proc.wait.return_value = -2
        code, _, err = self.main([])
        self.assertEqual(code, 130)
        self.assertEqual(json.loads(err.splitlines()[-1])["exit_code"], 130)

    def test_option_values_are_not_mistaken_for_subcommands(self):
        for argv in (["--debug", "mcp", PROMPT], ["--name", "update", PROMPT], ["-n", "update"], ["-d", "mcp"],
                     ["--add-dir", "/tmp/synthetic", "update"], ["-p", PROMPT, "update"], ["-p", "--", "x", "mcp"]):
            self.popen.reset_mock()
            code, _, err = self.main(argv)
            self.assertEqual(code, 0, argv)
            self.assertEqual(self.popen.call_args.args[0], ["/synthetic/claude", *self.fixed(), *argv])
        # A real subcommand is the first operand after flags that take no value.
        for argv in (["update"], ["-p", "mcp"], ["--verbose", "doctor"], ["--debug=SYNTHETIC_VALUE", "auth"],
                     ["-dSYNTHETIC_VALUE", "install"], ["--name=SYNTHETIC_VALUE", "plugin"], ["-p", "--", "update"]):
            self.popen.reset_mock()
            code, out, err = self.main(argv)
            self.assertEqual(code, 2, argv)
            record = json.loads(err)
            self.assertEqual((record["state"], record["fallback_allowed"]), ("conflict", False))
            self.assertIn(argv[-1], record["reason"])
            self.assertNotIn("SYNTHETIC_VALUE", err)
            self.popen.assert_not_called()

    def test_subcommand_after_option_values_is_rejected_before_anything_starts(self):
        # Each option consumes exactly its native values; the operand after them is still checked.
        self.assertEqual(CC.parse_forwarded(["--name", "example", "update"]), (["update"], False, []))
        self.assertEqual(CC.parse_forwarded(["--debug", "mcp", "auth"]), (["auth"], False, []))
        for argv in (["--name", "SYNTHETIC_VALUE", "update"], ["--debug", "SYNTHETIC_VALUE", "auth"],
                     ["-n", "SYNTHETIC_VALUE", "doctor"], ["-pn", "SYNTHETIC_VALUE", "mcp"],
                     ["--debug", "--verbose", "install"], ["-w", "-p", "plugin"],
                     ["--add-dir", "/SYNTHETIC_VALUE", "-p", "update"], ["--add-dir=/SYNTHETIC_VALUE", "update"],
                     ["--name", "--", "update"], ["-p", "--permission-mode", "plan", "--", "auth"]):
            code, out, err = self.main(argv)
            record = json.loads(err)
            self.assertEqual((code, out, record["state"], record["fallback_allowed"]), (2, "", "conflict", False),
                             argv)
            self.assertIn(argv[-1], record["reason"])
            self.assertNotIn("SYNTHETIC_VALUE", err)
        self.run_native.assert_not_called()  # Not even the auth metadata read ran.
        self.popen.assert_not_called()
        # The same words as option values stay native arguments.
        for argv in (["--name", "update", "-p", PROMPT], ["-p", "--debug", "mcp", PROMPT], ["-n", "auth", "-d", "mcp"],
                     ["-pw", "update"], ["--append-system-prompt", "auth", PROMPT],
                     ["--add-dir", "/tmp/synthetic", "update", "mcp"]):
            self.popen.reset_mock()
            self.assertEqual(self.main(argv)[0], 0, argv)
            self.assertEqual(self.popen.call_args, call(["/synthetic/claude", *self.fixed(), *argv],
                                                        env=self.child_env()))

    def test_unknown_native_option_forms_fail_closed_without_echo(self):
        for argv in (["--SYNTHETIC_VALUE", "update"], ["-p", PROMPT, "--SYNTHETIC_VALUE=x"], ["--mcp-debug"],
                     ["-x"], ["-pSYNTHETIC_VALUE"], ["--print=SYNTHETIC_VALUE"], ["-p", "--verbose=SYNTHETIC_VALUE"]):
            code, out, err = self.main(argv)
            record = json.loads(err)
            self.assertEqual((code, out, record["state"], record["model_started"]), (2, "", "conflict", False), argv)
            self.assertIn("known claude 2.1.314 options", record["reason"])
            for private in ("SYNTHETIC_VALUE", PROMPT, "mcp-debug"):
                self.assertNotIn(private, err)
        self.run_native.assert_not_called()
        self.popen.assert_not_called()

    def test_wrapper_options_count_only_as_leading_arguments(self):
        for argv in (["-p", "--observe", PROMPT], ["--name", "--observe", "-p", PROMPT],
                     ["--observe", "-p", "--append-system-prompt", "--observe", PROMPT],
                     ["--dry-run", "-n", "--dry-run"], ["-p", "--add-dir", "/tmp/synthetic", "--dry-run"],
                     ["-p", "--observe=SYNTHETIC_VALUE"]):
            code, out, err = self.main(argv)
            record = json.loads(err)  # One line: no auth check, launch or dry-run plan happened.
            self.assertEqual((code, out, record["state"]), (2, "", "conflict"), argv)
            self.assertIn("leading arguments", record["reason"])
            for private in ("SYNTHETIC_VALUE", PROMPT):
                self.assertNotIn(private, err)
        self.run_native.assert_not_called()
        self.popen.assert_not_called()
        # Literal text after `--` and an attached value stay native arguments; observation stays off.
        for argv in (["-p", "--", "--observe"], ["-p", "--append-system-prompt=--observe", PROMPT]):
            self.popen.reset_mock()
            self.assertEqual(self.main(argv)[0], 0)
            self.assertEqual(self.popen.call_args, call(["/synthetic/claude", *self.fixed(), *argv],
                                                        env=self.child_env()))

    def test_observe_requires_print_and_rejects_another_output_format(self):
        for argv in (["--observe", PROMPT], ["--observe", "-np", PROMPT], ["--observe", "--", "-p"],
                     ["--observe", "-p", "--output-format", "SYNTHETIC_VALUE", PROMPT],
                     ["--observe", "--print", "--output-format=SYNTHETIC_VALUE"]):
            code, out, err = self.main(argv)
            self.assertEqual(code, 2, argv)
            self.assertEqual((json.loads(err)["state"], out), ("conflict", ""))
            for private in (PROMPT, "SYNTHETIC_VALUE"):
                self.assertNotIn(private, err)
        self.popen.assert_not_called()
        code, out, _ = self.main(["--dry-run", "--observe", "-p", PROMPT])
        self.assertEqual(code, 0)
        plan = json.loads(out)
        self.assertEqual((plan["observe"], plan["observe_flags"]), (True, ["--output-format", "stream-json", "--verbose"]))
        self.assertNotIn(PROMPT, out)
        self.proc.stdout = iter(lines(INIT, RESULT))
        self.assertEqual(self.main(["--observe", "-vp", "--output-format", "stream-json", PROMPT])[0], 0)

    def test_observe_reports_init_model_running_and_cli_completion(self):
        stream = lines(INIT, ASSISTANT, TOOL_RESULT, b"not json\n", RESULT)
        code, out, err, records = self.observe(stream)
        self.assertEqual(code, 0)
        self.assertEqual(out.encode(), b"".join(stream))  # Native stdout passes through unchanged.
        self.assertEqual(self.popen.call_args, call(
            ["/synthetic/claude", *self.fixed(), "--output-format", "stream-json", "--verbose", "-p", PROMPT],
            stdout=subprocess.PIPE, start_new_session=True, env=self.child_env()))
        checking, start, waiting, initialized, running, finish = records
        self.assertEqual((checking["phase"], checking["state"]), ("auth_check", "checking"))
        self.assertEqual((start["record"], start["observe"], start["phase"], start["auth_check"],
                          start["idle_timeout"], start["launcher_retries"]),
                         ("cc_implement_start", True, "launch", "passed", None, 0))
        self.assertEqual((waiting["phase"], waiting["idle_timeout"]), ("waiting", None))
        self.assertEqual(initialized, {"record": "cc_implement_phase", "phase": "initialized",
                                       "configured_model": "claude-opus-5-5", "actual_model": "claude-opus-5-5",
                                       "model_match": True, "cli_version": "2.1.314"})
        self.assertEqual((running["phase"], running["first_event"]), ("running", "assistant"))
        tokens = {"input_tokens": 10, "output_tokens": 20, "cache_read_input_tokens": 30,
                  "cache_creation_input_tokens": 40}
        self.assertEqual({key: finish[key] for key in (
            "record", "outcome", "reason", "exit_code", "native_exit_code", "cli_completed",
            "implementation_verified", "tests", "rework", "fallback_allowed", "configured_model", "actual_model",
            "result_subtype", "num_turns", "usage", "model_usage", "observed", "observed_error_classes")}, {
            "record": "cc_implement_finish", "outcome": "completed", "reason": "cli_completed", "exit_code": 0,
            "native_exit_code": 0, "cli_completed": True, "implementation_verified": False, "tests": "unknown",
            "rework": "unknown", "fallback_allowed": False, "configured_model": "claude-opus-5-5",
            "actual_model": "claude-opus-5-5", "result_subtype": "success", "num_turns": 3, "usage": tokens,
            "model_usage": {"claude-opus-5-5": tokens},
            "observed": {"assistant_messages": 1, "tool_uses": 1, "api_retries": 0, "unparsed_lines": 1},
            "observed_error_classes": []})
        # No nested agent ran; effort is configured only, never inferred from env or modelUsage.
        self.assertEqual({key: finish[key] for key in (
            "mismatch_source", "subagent_models", "configured_effort", "actual_effort")},
            {"mismatch_source": None, "subagent_models": {}, "configured_effort": "xhigh",
             "actual_effort": "unknown"})
        self.assertEqual({key: start[key] for key in SCOPE}, SCOPE)

    def test_observe_keeps_waiting_through_silence_without_any_timer(self):
        clock = [1000.0]

        def silent_then_output():
            clock[0] += 3600  # An hour with no native output while the child is still running.
            self.proc.wait.assert_not_called()
            for stop in (self.proc.terminate, self.proc.kill, self.proc.send_signal):
                stop.assert_not_called()
            yield from lines(INIT, ASSISTANT, RESULT)

        timer = AssertionError("No idle or inference timer")
        with patch.object(CC.time, "monotonic", lambda: clock[0]), patch("signal.alarm", side_effect=timer), \
                patch("signal.setitimer", side_effect=timer), patch("threading.Timer", side_effect=timer):
            code, _, _, records = self.observe(silent_then_output())
        self.assertEqual(code, 0)
        self.assertEqual([record.get("phase") for record in records],
                         ["auth_check", "launch", "waiting", "initialized", "running", "terminal"])
        self.assertEqual(records[-1]["outcome"], "completed")
        self.assertGreaterEqual(records[-1]["duration_seconds"], 3600)
        self.assertEqual(self.proc.wait.call_args_list, [call()])  # Waited without a timeout.
        self.assertEqual(self.popen.call_count, 1)

    def test_observe_native_sigint_keeps_130_and_is_interrupted(self):
        before = signal.getsignal(signal.SIGINT)

        def interrupted():
            yield from lines(INIT, ASSISTANT)
            signal.raise_signal(signal.SIGINT)  # Ctrl-C or a parent's SIGINT reaching the launcher.

        for raw in (-signal.SIGINT, 130):
            self.proc.send_signal.reset_mock()
            code, _, _, records = self.observe(interrupted(), raw)
            self.assertEqual(code, 130)
            finish = records[-1]
            self.assertEqual((finish["outcome"], finish["native_exit_code"], finish["cli_completed"],
                              finish["implementation_verified"], finish["fallback_allowed"]),
                             ("interrupted", 130, False, False, False))
            self.proc.send_signal.assert_called_once_with(signal.SIGINT)  # Relayed to its own child only.
            self.proc.terminate.assert_not_called()
        self.assertIs(signal.getsignal(signal.SIGINT), before)

        # A SIGINT arriving while the child is still starting is sent once, right after it starts.
        def starting(*_args, **_kwargs):
            signal.raise_signal(signal.SIGINT)
            return self.proc

        self.popen.side_effect = starting
        self.proc.send_signal.reset_mock()
        self.assertEqual(self.observe(lines(INIT), -signal.SIGINT)[0], 130)
        self.proc.send_signal.assert_called_once_with(signal.SIGINT)
        self.assertIs(signal.getsignal(signal.SIGINT), before)

    def test_observed_child_has_its_own_session_and_gets_the_parent_sigint_once(self):
        # A synthetic stand-in for native claude reports its session, makes the launcher receive SIGINT
        # as a parent or terminal would, then waits; it exits 0 only if that SIGINT is never relayed.
        script = self.root / "synthetic-claude"
        script.write_text(f"#!{sys.executable} -I\n" + textwrap.dedent("""\
            import json, os, signal, time
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            print(json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5-5"}), flush=True)
            print(json.dumps({"type": "probe", "pid": os.getpid(), "sid": os.getsid(0), "pgid": os.getpgid(0)}),
                  flush=True)
            os.kill(os.getppid(), signal.SIGINT)
            time.sleep(10)
            """))
        script.chmod(0o700)
        started, relayed = [], []

        def spawn(command, **kwargs):
            started.append(REAL_POPEN(command, **kwargs))
            return started[-1]

        def own_child_only(pid, number):
            if not started or pid != started[0].pid:
                raise AssertionError("Only the observed child may be signalled")
            relayed.append(number)
            REAL_KILL(pid, number)

        before = signal.getsignal(signal.SIGINT)
        with patch.object(CC, "find_claude", return_value=str(script)), \
                patch.object(CC.subprocess, "Popen", side_effect=spawn), patch.object(CC.os, "kill", own_child_only):
            code, out, err = self.main(["--observe", "-p", PROMPT])
        probe = json.loads(out.splitlines()[1])
        self.assertEqual(len(started), 1)
        self.assertEqual((probe["sid"], probe["pgid"]), (started[0].pid, started[0].pid))  # Own session and group.
        self.assertNotEqual(probe["sid"], os.getsid(0))
        self.assertEqual(relayed, [signal.SIGINT])  # Once, and only to this child.
        finish = json.loads(err.splitlines()[-1])
        self.assertEqual((code, finish["outcome"], finish["native_exit_code"], finish["cli_completed"],
                          finish["fallback_allowed"]), (130, "interrupted", 130, False, False))
        self.assertNotIn(PROMPT, err)
        self.assertIs(signal.getsignal(signal.SIGINT), before)

    def test_observe_reports_auth_checking_first_and_unreadable_metadata_as_unverified(self):
        self.proc.stdout = iter(lines(INIT, RESULT))
        self.assertEqual(self.main(["--observe", "-p", PROMPT])[0], 0)
        # The checking phase is already on stderr when the bounded metadata read starts.
        self.assertEqual(json.loads(self.stderr_at_auth), {
            "record": "cc_implement_phase", "phase": "auth_check", "state": "checking",
            "metadata_timeout_seconds": 15})
        self.popen.reset_mock()
        cases = [(subprocess.TimeoutExpired(["claude"], 15), 0, "unverified"),
                 (OSError("SYNTHETIC_RAW_ERROR"), 0, "unverified"), ("not json", 0, "unverified"),
                 ("[]", 0, "unverified"), (AUTH, 1, "unverified"),
                 ({**AUTH, "subscriptionType": None}, 0, "not_subscription")]
        for auth, status, state in cases:
            self.auth, self.auth_code = auth, status
            code, out, err = self.main(["--observe", "-p", PROMPT])
            checking, result, blocked = [json.loads(line) for line in err.splitlines()]
            self.assertEqual((code, out, checking["state"], result["phase"], result["state"]),
                             (78, "", "checking", "auth_check", state))
            self.assertEqual((blocked["state"], blocked["model_started"], blocked["fallback_allowed"]),
                             ("blocked", False, False))
            if state == "unverified":
                self.assertIn("unverified, not judged as failed", blocked["reason"])
            # A failed or unreadable read is not turned into an authentication failure or error class.
            for absent in ("error_class", "authentication_failed", "SYNTHETIC_RAW_ERROR", "synthetic@example.test",
                           PROMPT):
                self.assertNotIn(absent, err)
        self.popen.assert_not_called()
        self.auth, self.auth_code = "not json", 0
        code, _, err = self.main([PROMPT])  # Without --observe, only the blocked line, as before.
        self.assertEqual((code, len(err.splitlines())), (78, 1))

    def test_observe_eof_or_exit0_without_terminal_result_is_incomplete(self):
        cases = [("missing_init", lines()), ("missing_init", lines(ASSISTANT, RESULT)),
                 ("missing_result", lines(INIT, ASSISTANT, b"not json\n", b'{"type": "result", "subtype": "succ')),
                 ("malformed_result", lines(INIT, {"type": "result", "subtype": "success", "num_turns": 1}))]
        for reason, stream in cases:
            code, _, _, records = self.observe(stream)
            self.assertEqual(code, 3, reason)
            finish = records[-1]
            self.assertEqual((finish["outcome"], finish["reason"], finish["cli_completed"], finish["fallback_allowed"]),
                             ("incomplete", reason, False, False))
            # Silence, EOF and unparsed text are not turned into connection or availability errors.
            self.assertEqual([record for record in records if "error_class" in record], [])
            self.assertEqual(finish["observed_error_classes"], [])
            self.assertEqual(finish["observed"]["unparsed_lines"], 2 if reason == "missing_result" else 0)
        failures = [(1, "result_error", lines(INIT, {**RESULT, "is_error": True}), 0),
                    (1, "native_exit_nonzero", lines(INIT, ASSISTANT), 1)]
        for expected, reason, stream, raw in failures:
            code, _, _, records = self.observe(stream, raw)
            self.assertEqual((code, records[-1]["outcome"], records[-1]["reason"]), (expected, "error", reason))

    def test_observe_classifies_only_known_error_codes_without_raw_text(self):
        raw_text = "SYNTHETIC_RAW_ERROR_TEXT"
        stream = lines(INIT, {"type": "assistant", "parent_tool_use_id": None, "error": "rate_limit",
                              "message": {"model": "<synthetic>", "content": [{"type": "text", "text": raw_text}]}},
                       retry("authentication_failed", 401), retry("connection_error", None), retry("overloaded", 529),
                       retry("unknown", None), retry("SYNTHETIC_RAW_CODE", None), retry(None, 503),
                       {"type": "result", "subtype": "success", "is_error": True, "num_turns": 1,
                        "result": raw_text, "errors": [raw_text]})
        code, _, err, records = self.observe(stream, raw=1)
        self.assertEqual(code, 1)
        self.assertEqual([(r["phase"], r["error_code"], r["error_class"], r.get("http_status"))
                          for r in records if "error_class" in r], [
            ("api_error", "rate_limit", "rate_limit", None),
            ("api_retry_observed", "authentication_failed", "auth", 401),
            ("api_retry_observed", "connection_error", "connection", None),
            ("api_retry_observed", "overloaded", "server", 529),
            ("api_retry_observed", "unknown", "unclassified", None),
            ("api_retry_observed", "unrecognized", "unclassified", None),
            ("api_retry_observed", "unknown", "server", 503)])
        self.assertTrue(all(r["launcher_retries"] == 0 for r in records if r.get("phase") == "api_retry_observed"))
        finish = records[-1]
        self.assertEqual((finish["outcome"], finish["reason"], finish["observed"]["api_retries"]),
                         ("error", "native_exit_nonzero", 6))
        self.assertEqual(finish["observed_error_classes"],
                         ["auth", "connection", "rate_limit", "server", "unclassified"])
        self.assertNotIn("model_mismatch", err)  # The native <synthetic> marker is not a model claim.
        for private in (raw_text, "SYNTHETIC_RAW_CODE"):
            self.assertNotIn(private, err)
        self.assertEqual(self.popen.call_count, 1)  # Native retries are only reported; none are added.

    def test_observe_model_mismatch_fails_closed_and_stops_only_its_own_child(self):
        other, pinned, dated_id = "claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5-5-20261015"

        def main_on(model):
            return {**ASSISTANT, "message": {**ASSISTANT["message"], "model": model}}

        def sub_on(model, **ids):  # A nested agent's message, marked as native marks it.
            return {**main_on(model), **(ids or {"parent_tool_use_id": "toolu_SYNTHETIC"})}

        # (stream, lines passed through, source, main model kept in actual_model, mismatched model)
        cases = [(lines({**INIT, "model": other}, ASSISTANT, RESULT), 0, "init", other, other),
                 (lines(INIT, main_on(other), RESULT), 1, "assistant", other, other),
                 (lines(INIT, ASSISTANT, sub_on(other), RESULT), 2, "subagent", pinned, other),
                 (lines(INIT, sub_on(other, parent_tool_use_id=None, agent_id="SYNTHETIC_AGENT_ID"), RESULT), 1,
                  "subagent", pinned, other),
                 (lines(INIT, sub_on("claude-opus-5-5-2026101"), RESULT), 1, "subagent", pinned,
                  "claude-opus-5-5-2026101")]
        for stream, forwarded, source, main, bad in cases:
            self.proc.terminate.reset_mock()
            code, out, err, records = self.observe(stream, raw=-signal.SIGTERM)
            self.assertEqual(code, 4, source)
            self.proc.terminate.assert_called_once_with()
            self.assertEqual(out.encode(), b"".join(stream[:forwarded]))  # Nothing passes after the mismatch.
            mismatch = [r for r in records if r.get("phase") == "model_mismatch"]
            self.assertEqual([(r["source"], r["configured_model"], r["actual_model"], r["mismatched_model"])
                              for r in mismatch], [(source, pinned, main, bad)])
            finish = records[-1]
            self.assertEqual((finish["outcome"], finish["reason"], finish["actual_model"], finish["mismatch_source"],
                              finish["cli_completed"], finish["native_exit_code"]),
                             ("error", "model_mismatch", main, source, False, 143))
            self.assertEqual(finish["subagent_models"], {bad: 1} if source == "subagent" else {})
            for private in ("toolu_SYNTHETIC", "SYNTHETIC_AGENT_ID"):
                self.assertNotIn(private, err)
        # Nested agents on the pinned ID or a dated snapshot of it pass and are counted by sanitized
        # model only; a nested <synthetic> message and one without a model are no model claim.
        self.proc.terminate.reset_mock()
        nested_synthetic = {"type": "assistant", "parent_tool_use_id": "toolu_SYNTHETIC", "error": "rate_limit",
                            "message": {"model": "<synthetic>", "content": []}}
        nested_no_model = {"type": "assistant", "agent_id": "SYNTHETIC_AGENT_ID", "message": {"content": []}}
        code, _, err, records = self.observe(lines(
            INIT, sub_on(pinned), sub_on(dated_id), sub_on(dated_id, agent_id="SYNTHETIC_AGENT_ID"),
            nested_synthetic, nested_no_model, main_on(dated_id), RESULT))
        self.assertEqual(code, 0)
        self.proc.terminate.assert_not_called()
        finish = records[-1]
        self.assertEqual((finish["outcome"], finish["actual_model"], finish["mismatch_source"], finish["subagent_models"]),
                         ("completed", pinned, None, {pinned: 1, dated_id: 2}))
        self.assertNotIn("model_mismatch", err)
        for private in ("toolu_SYNTHETIC", "SYNTHETIC_AGENT_ID"):
            self.assertNotIn(private, err)

    def test_both_launches_get_the_same_four_values_and_the_caller_environment_is_untouched(self):
        # Caller values for the four names are replaced in the child's copy only; everything else is kept.
        caller = {"SYNTHETIC_UNRELATED": "SYNTHETIC_UNRELATED_VALUE", "TERM": "xterm-synthetic", "LANG": "C.UTF-8",
                  "CLAUDE_CODE_SUBAGENT_MODEL": "sonnet", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "0",
                  "CC_IMPLEMENT_USAGE_NO_MODEL_CALL": "0", "CLAUDE_CODE_EFFORT_LEVEL": "xhigh"}
        profile = self.profile.read_bytes()
        with patch.dict(os.environ, caller):
            before = dict(os.environ)
            self.assertEqual(self.main(["-p", PROMPT])[0], 0)
            self.proc.stdout = iter(lines(INIT, RESULT))
            self.assertEqual(self.main(["--observe", "-p", PROMPT])[0], 0)
            self.assertEqual(dict(os.environ), before)  # The launcher's own environment was never changed.
        self.assertEqual(self.profile.read_bytes(), profile)
        plain, observed = self.popen.call_args_list
        self.assertEqual(plain.kwargs, {"env": {**before, **FORCED}})
        self.assertEqual(observed.kwargs, {"stdout": subprocess.PIPE, "start_new_session": True,
                                           "env": {**before, **FORCED}})
        self.assertIsNot(plain.kwargs["env"], observed.kwargs["env"])  # A fresh copy per launch.
        for launch in (plain, observed):
            command = launch.args[0]
            self.assertEqual(command[1:len(self.fixed()) + 1], self.fixed())
            # The same four values ride in command-line settings, which outrank the user, project and
            # local settings files, so a lower settings env cannot put another subagent model back.
            self.assertEqual(json.loads(command[command.index("--settings") + 1]),
                             {**CC.PROFILE_CONTENT, "env": FORCED})
            self.assertFalse([token for token in command if "SYNTHETIC_UNRELATED" in token or "sonnet" in token])
        self.assertEqual(CC.MODEL_ENV, FORCED)
        self.assertEqual(CC.selection_flags(), CC.selection_flags())  # Deterministic text.
        # The auth and version probes still inherit the caller's environment as before.
        self.assertTrue(self.run_native.call_args_list)
        for probe in self.run_native.call_args_list:
            self.assertNotIn("env", probe.kwargs)

    def test_cli_version_below_2_1_292_unknown_or_unparseable_blocks_before_launch(self):
        bad = ["2.1.291 (Claude Code)", "2.0.999 (Claude Code)", "1.99.999 (Claude Code)", "2.1 (Claude Code)",
               "2.1.314", "2.1.314 (Claude Code) SYNTHETIC_VALUE", "v2.1.314 (Claude Code)", "", "SYNTHETIC_VALUE",
               "1234567.1.1 (Claude Code)", OSError("SYNTHETIC_RAW_ERROR"), subprocess.TimeoutExpired(["claude"], 10)]
        for version in bad:
            self.version = version
            for argv in ([PROMPT], ["--observe", "-p", PROMPT]):
                code, out, err = self.main(argv)
                blocked = json.loads(err.splitlines()[-1])
                self.assertEqual((code, out, blocked["state"], blocked["model_started"], blocked["fallback_allowed"]),
                                 (78, "", "blocked", False, False), version)
                self.assertIn("2.1.292", blocked["reason"])
                self.assertNotIn("cc_implement_start", err)
                for private in ("SYNTHETIC_VALUE", "SYNTHETIC_RAW_ERROR", PROMPT):
                    self.assertNotIn(private, err)
        self.version, self.version_code = "2.1.314 (Claude Code)", 1  # A failed read is unknown, not 2.1.314.
        self.assertEqual(self.main([PROMPT])[0], 78)
        self.popen.assert_not_called()
        self.version_code = 0
        for version in ("2.1.292 (Claude Code)", "2.1.1000 (Claude Code)", "2.2.0 (Claude Code)",
                        "10.0.0 (Claude Code)"):  # Compared as numbers, not text.
            self.version = version
            self.popen.reset_mock()
            self.run_native.reset_mock()
            code, _, err = self.main([PROMPT])
            self.assertEqual(code, 0, version)
            self.assertEqual(json.loads(err.splitlines()[0])["version"], version)
            self.popen.assert_called_once()
            # One version read per launch, reused for the start record; no install or upgrade command.
            self.assertEqual([c.args[0][1:] for c in self.run_native.call_args_list],
                             [["auth", "status", "--json"], ["--version"]])
        # Dry-run starts no model and needs no CLI, so an unusable version does not affect it.
        self.version = "SYNTHETIC_VALUE"
        self.run_native.reset_mock()
        with patch.object(CC, "find_claude", side_effect=AssertionError("Dry-run must not look for the CLI")):
            self.assertEqual(self.main(["--dry-run", "--observe", "-p", PROMPT])[0], 0)
        self.run_native.assert_not_called()

    def test_forced_values_open_no_protection_or_option_bypass(self):
        for name in FORCED:  # Neither auth/provider names nor anything the caller may pass as a selection.
            self.assertNotIn(name, CC.AUTH_ENV)
            self.assertFalse(name.startswith("CLAUDE_CODE_USE_"))
        for argv in (["--settings", SETTINGS], ["--settings=" + SETTINGS], ["--agents", "{}"],
                     ["--setting-sources", "user"], ["-p", "--model", "SYNTHETIC_VALUE", PROMPT]):
            code, out, err = self.main(argv)
            self.assertEqual((code, out, json.loads(err)["state"]), (2, "", "conflict"), argv)
        # A caller's other effort level is still a conflict, not silently replaced by the forced xhigh.
        with patch.dict(os.environ, {"CLAUDE_CODE_EFFORT_LEVEL": "high"}):
            self.assertEqual(self.main(["-p", PROMPT])[0], 2)
        # Auth and provider overrides still block before anything starts, the forced names notwithstanding.
        with patch.dict(os.environ, {**FORCED, "ANTHROPIC_BASE_URL": "SYNTHETIC_SECRET_VALUE"}):
            code, _, err = self.main(["-p", PROMPT])
        self.assertEqual(code, 78)
        self.assertNotIn("SYNTHETIC_SECRET_VALUE", err)
        self.auth = {**AUTH, "apiProvider": "bedrock"}
        self.assertEqual(self.main(["-p", PROMPT])[0], 78)
        self.auth = AUTH
        # The on-disk profile is still checked exactly; it must not gain the env passed inline.
        self.profile.write_text(json.dumps({**CC.PROFILE_CONTENT, "env": FORCED}))
        for argv in (["--dry-run"], ["-p", PROMPT]):
            self.assertEqual(self.main(argv)[0], 78)
        self.popen.assert_not_called()

    def test_failures_never_start_another_implementer_or_claim_success(self):
        self.proc.stdout = iter(())
        self.proc.wait.return_value = 1
        _, _, err = self.main([PROMPT])
        finish = json.loads(err.splitlines()[-1])
        self.assertEqual((finish["outcome"], finish["implementation_verified"], finish["fallback_allowed"]),
                         ("error", False, False))
        self.auth = {**AUTH, "subscriptionType": None}
        self.assertEqual(json.loads(self.main(["--observe", "-p", PROMPT])[2].splitlines()[-1])["fallback_allowed"],
                         False)
        self.auth = AUTH
        self.assertEqual(json.loads(self.main(["--observe", PROMPT])[2])["fallback_allowed"], False)
        for stream, raw in ((lines(INIT, {**RESULT, "is_error": True}), 0), (lines(INIT), 0),
                            (lines(INIT, ASSISTANT), -signal.SIGINT), (lines({**INIT, "model": "other"}), 0)):
            finish = self.observe(stream, raw)[3][-1]
            self.assertNotEqual(finish["exit_code"], 0)
            self.assertEqual((finish["cli_completed"], finish["implementation_verified"], finish["fallback_allowed"]),
                             (False, False, False))
        # One faked native claude per launch; no Codex, alternate model or retry was ever started.
        self.assertEqual(self.popen.call_count, 5)
        for launch in self.popen.call_args_list:
            command = launch.args[0]
            self.assertEqual(command[:len(self.fixed()) + 1], ["/synthetic/claude", *self.fixed()])
            self.assertFalse([token for token in command if "codex" in token.lower()])
        self.assertTrue(all(c.args[0][1:] in (["auth", "status", "--json"], ["--version"])
                            for c in self.run_native.call_args_list))


if __name__ == "__main__":
    unittest.main()
