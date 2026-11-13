"""No model calls: `claude` and `herdr` are stubs on PATH. Check the agent-name summary hook and its wiring from the tab-title hook."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "home/dot_claude/hooks"
SUMMARY = HOOKS / "executable_herdr-agent-summary.sh"
TAB_TITLE = HOOKS / "executable_herdr-tab-title.sh"

CLAUDE_STUB = r"""#!/bin/sh
T="$STUB_DIR"
printf '%s\n' "$*" >> "$T/claude.log"
printf '%s\n' "$@" > "$T/claude.args"
env > "$T/claude.env"
cat > "$T/claude.stdin"
[ ! -f "$T/claude.sleep" ] || sleep "$(cat "$T/claude.sleep")"
[ ! -f "$T/claude.fail" ] || exit 1
[ ! -f "$T/claude.out" ] || cat "$T/claude.out"
"""

HERDR_STUB = r"""#!/bin/sh
T="$STUB_DIR"
printf '%s\n' "$*" >> "$T/herdr.log"
case "$1 $2" in
  "agent get")
    kind="claude"; [ ! -f "$T/agent.kind" ] || kind="$(cat "$T/agent.kind")"
    name=""; [ ! -f "$T/agent.name" ] || name="$(cat "$T/agent.name")"
    printf '{"result":{"agent":{"agent":"%s","name":"%s"}}}\n' "$kind" "$name" ;;
  "pane get") cat "$T/pane.json" ;;
  "tab get") cat "$T/tab.json" ;;
  "pane report-metadata")
    # 引数をそのまま 1 行 1 個で残す (解釈されていないことの確認用)
    printf '%s\n' "$@" > "$T/report.args"
    printf '%s\n' "$*" >> "$T/report.log" ;;
esac
exit 0
"""


class Harness(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.stub = self.root / "stub"
        self.bin = self.root / "bin"
        self.run_dir = self.root / "run"
        self.stub.mkdir()
        self.bin.mkdir()
        self.run_dir.mkdir(mode=0o700)
        for name, text in (("claude", CLAUDE_STUB), ("herdr", HERDR_STUB)):
            path = self.bin / name
            path.write_text(text)
            path.chmod(0o700)
        (self.stub / "claude.out").write_text("認証まわりの修正\n")
        self.transcript = self.root / "transcript.jsonl"
        self.write_transcript()
        env = {k: v for k, v in os.environ.items() if not k.startswith(("HERDR_", "CLAUDE", "ANTHROPIC"))}
        self.env = {**env, "HOME": str(self.root), "XDG_RUNTIME_DIR": str(self.run_dir),
                    "PATH": str(self.bin) + ":" + env["PATH"], "STUB_DIR": str(self.stub),
                    "HERDR_ENV": "1", "HERDR_PANE_ID": "w1:p1"}

    def tearDown(self):
        time.sleep(0.2)

    def write_transcript(self):
        lines = [
            {"type": "user", "message": {"role": "user", "content": "herdr のサイドバーの名前を要約にしたい"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "SECRET-THINKING"},
                {"type": "text", "text": "まず hook を調べます"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "SECRET-TOOL-INPUT"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "x", "content": "SECRET-TOOL-OUTPUT"}]}},
            {"type": "assistant", "isSidechain": True, "message": {"role": "assistant",
                                                                    "content": [{"type": "text", "text": "SECRET-SIDECHAIN"}]}},
            {"type": "user", "message": {"role": "user", "content": "最後の依頼です"}},
        ]
        self.transcript.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n")

    def stop(self, session="s1", extra_env=None, script=SUMMARY, **fields):
        payload = {"session_id": session, "transcript_path": str(self.transcript), "hook_event_name": "Stop"}
        payload.update(fields)
        env = {**self.env, **(extra_env or {})}
        started = time.monotonic()
        result = subprocess.run(["bash", str(script)], input=json.dumps(payload), env=env,
                                capture_output=True, text=True, timeout=20)
        self.elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def lines(self, name):
        path = self.stub / name
        return path.read_text().splitlines() if path.exists() else []

    def wait_for(self, name, count=1, timeout=6):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if len(self.lines(name)) >= count:
                return
            time.sleep(0.05)
        self.fail(f"{name} did not reach {count} lines: {self.lines(name)}")

    def settle(self):
        time.sleep(0.8)

    def reported_title(self):
        args = self.lines("report.args")
        self.assertIn("--display-agent", args)
        return args[args.index("--display-agent") + 1]


class SummaryHook(Harness):
    # --- 基本: 要約が display_agent に報告される ---
    def test_first_stop_reports_summary_as_display_agent(self):
        self.stop()
        self.wait_for("report.log")
        args = self.lines("report.args")
        self.assertEqual(args[:2], ["pane", "report-metadata"])
        self.assertEqual(args[2], "w1:p1")  # ペイン ID は --source の前
        self.assertLess(args.index("w1:p1"), args.index("--source"))
        self.assertEqual(args[args.index("--source") + 1], "dotfiles:claude-summary")
        self.assertEqual(args[args.index("--agent") + 1], "claude")
        self.assertEqual(self.reported_title(), "認証まわりの修正")

    def test_model_input_is_a_minimal_tail_without_tools_or_thinking(self):
        self.stop()
        self.wait_for("report.log")
        sent = (self.stub / "claude.stdin").read_text()
        self.assertIn("最後の依頼です", sent)
        self.assertIn("まず hook を調べます", sent)
        for secret in ("SECRET-THINKING", "SECRET-TOOL-INPUT", "SECRET-TOOL-OUTPUT", "SECRET-SIDECHAIN"):
            self.assertNotIn(secret, sent)
        self.assertLess(len(sent), 2300)

    def test_large_transcript_is_cut_to_the_cap(self):
        lines = [json.dumps({"type": "user", "message": {"role": "user", "content": "長文" * 5000}}) for _ in range(20)]
        self.transcript.write_text("\n".join(lines) + "\n")
        self.stop()
        self.wait_for("report.log")
        self.assertLess(len((self.stub / "claude.stdin").read_text()), 2300)

    # --- 再帰の防止 ---
    def test_sentinel_stops_the_hook(self):
        self.stop(extra_env={"HERDR_AGENT_SUMMARY_RUNNING": "1"})
        self.settle()
        self.assertEqual(self.lines("claude.log"), [])
        self.assertEqual(self.lines("herdr.log"), [])

    def test_summary_claude_is_launched_without_hooks_and_herdr_env(self):
        self.stop()
        self.wait_for("report.log")
        args = (self.stub / "claude.args").read_text().split("\n")
        self.assertIn("-p", args)
        self.assertIn("--safe-mode", args)
        self.assertIn("--no-session-persistence", args)
        self.assertNotIn("--bare", args)  # --bare は OAuth を読まず API 従量になる
        self.assertEqual(args[args.index("--model") + 1], "claude-haiku-5-5")
        self.assertEqual(args[args.index("--settings") + 1], '{"disableAllHooks":true}')
        env = dict(line.split("=", 1) for line in (self.stub / "claude.env").read_text().splitlines() if "=" in line)
        self.assertEqual(env.get("HERDR_AGENT_SUMMARY_RUNNING"), "1")
        self.assertFalse([k for k in env if k.startswith("HERDR_") and k != "HERDR_AGENT_SUMMARY_RUNNING"])

    def test_stop_hook_active_is_ignored(self):
        self.stop(stop_hook_active=True)
        self.settle()
        self.assertEqual(self.lines("claude.log"), [])

    # --- 呼び出しの間引き ---
    def test_default_throttle_calls_once_per_session(self):
        for _ in range(12):
            self.stop()
        self.settle()
        self.assertEqual(len(self.lines("claude.log")), 1)
        self.stop(session="another")
        self.settle()
        self.assertEqual(len(self.lines("claude.log")), 2)

    def test_every_n_turns_with_min_interval_and_cap(self):
        knobs = {"HERDR_AGENT_SUMMARY_EVERY_TURNS": "3", "HERDR_AGENT_SUMMARY_MIN_INTERVAL": "0",
                 "HERDR_AGENT_SUMMARY_MAX_CALLS": "3"}
        for _ in range(12):
            self.stop(extra_env=knobs)
        self.settle()
        self.assertEqual(len(self.lines("claude.log")), 3)  # 1, 4, 7 ターン目。上限で止まる

    def test_min_interval_blocks_even_when_turns_are_enough(self):
        knobs = {"HERDR_AGENT_SUMMARY_EVERY_TURNS": "2", "HERDR_AGENT_SUMMARY_MIN_INTERVAL": "3600"}
        for _ in range(6):
            self.stop(extra_env=knobs)
        self.settle()
        self.assertEqual(len(self.lines("claude.log")), 1)

    def test_state_file_has_only_counters_and_lives_under_runtime_dir(self):
        self.stop()
        files = list((self.run_dir / "herdr-agent-summary").iterdir())
        self.assertEqual([f.name for f in files], ["s1.state"])
        self.assertRegex(files[0].read_text(), r"^\d+ \d+ \d+ \d+\n$")
        self.assertEqual((self.run_dir / "herdr-agent-summary").stat().st_mode & 0o777, 0o700)

    def test_refuses_a_state_dir_that_is_a_symlink(self):
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        (self.run_dir / "herdr-agent-summary").symlink_to(elsewhere)
        self.stop()
        self.settle()
        self.assertEqual(self.lines("claude.log"), [])
        self.assertEqual(list(elsewhere.iterdir()), [])

    # --- 手で付けた名前の保護 ---
    def test_manual_agent_name_is_not_overridden(self):
        for name in ("reviewer", "ui-keys", "claude-x", "claude-2-extra"):
            with self.subTest(name=name):
                (self.stub / "agent.name").write_text(name)
                self.stop(session="m-" + name)
                self.settle()
                self.assertEqual(self.lines("claude.log"), [])
                self.assertEqual(self.lines("report.log"), [])

    def test_auto_generated_names_are_replaced(self):
        for i, name in enumerate(("", "claude", "claude-2", "claude-13")):
            with self.subTest(name=name):
                (self.stub / "agent.name").write_text(name)
                self.stop(session=f"a{i}")
                self.wait_for("report.log", i + 1)

    def test_other_agent_kinds_are_not_touched(self):
        (self.stub / "agent.kind").write_text("codex")
        self.stop()
        self.settle()
        self.assertEqual(self.lines("claude.log"), [])

    def test_name_changed_while_model_runs_is_not_overridden(self):
        (self.stub / "claude.sleep").write_text("1")
        self.stop()
        (self.stub / "agent.name").write_text("reviewer")
        self.wait_for("claude.log")
        time.sleep(1.6)
        self.assertEqual(self.lines("report.log"), [])

    # --- 失敗時は何も変えない・本体を止めない ---
    def test_claude_failure_changes_nothing(self):
        (self.stub / "claude.fail").write_text("1")
        self.stop()
        self.wait_for("claude.log")
        self.settle()
        self.assertEqual(self.lines("report.log"), [])

    def test_empty_or_garbage_output_changes_nothing(self):
        for i, out in enumerate(("", "\n\n", "   ", "\x1b[0m\n", "x" * 500)):
            with self.subTest(out=out):
                (self.stub / "claude.out").write_text(out)
                self.stop(session=f"g{i}")
                self.wait_for("claude.log", i + 1)
        self.settle()
        self.assertEqual(self.lines("report.log"), [])

    def test_missing_prerequisites_exit_zero(self):
        for extra in ({"HERDR_ENV": "0"}, {"HERDR_PANE_ID": ""}):
            with self.subTest(extra=extra):
                self.stop(extra_env=extra)
        broken = self.root / "broken.jsonl"
        for fields in ({"transcript_path": str(broken)}, {"session_id": ""}, {"transcript_path": ""}):
            with self.subTest(fields=fields):
                self.stop(**fields)
        result = subprocess.run(["bash", str(SUMMARY)], input="not json", env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.settle()
        self.assertEqual(self.lines("claude.log"), [])

    def test_hook_does_not_wait_for_the_model(self):
        (self.stub / "claude.sleep").write_text("2")
        self.stop()
        self.assertLess(self.elapsed, 1.5)
        self.wait_for("report.log", timeout=8)

    def test_hung_model_is_cut_by_timeout(self):
        (self.stub / "claude.sleep").write_text("5")
        self.stop(extra_env={"HERDR_AGENT_SUMMARY_TIMEOUT": "1"})
        time.sleep(2.5)
        self.assertEqual(self.lines("report.log"), [])

    # --- 出力の無害化 ---
    def reported_for(self, out):
        (self.stub / "claude.out").write_text(out)
        (self.stub / "report.log").unlink(missing_ok=True)
        self.n = getattr(self, "n", 0) + 1
        self.stop(session=f"r{self.n}")
        self.wait_for("report.log")
        return self.reported_title()

    def test_control_chars_newlines_and_quotes_are_removed(self):
        self.assertEqual(self.reported_for("\x1b[31m「認証の\x07修正」\n2 行目は捨てる\n"), "認証の修正")
        self.assertEqual(self.reported_for('"quoted title"\n'), "quoted title")

    def test_bidi_and_zero_width_chars_are_removed(self):
        self.assertEqual(self.reported_for("a\u202eb\u200bc\n"), "abc")

    def test_title_is_cut_to_20_chars(self):
        title = self.reported_for("あ" * 60 + "\n")
        self.assertEqual(title, "あ" * 19 + "…")
        self.assertEqual(len(title), 20)

    def test_leading_dashes_cannot_become_options(self):
        title = self.reported_for("--display-agent evil\n")
        self.assertFalse(title.startswith("-"))
        self.assertEqual(title, "display-agent evil")

    def test_output_is_never_run_as_a_command(self):
        marker = self.root / "pwned"
        title = self.reported_for(f"x$(touch {marker}) `touch {marker}`; touch {marker}\n")
        self.assertIn("touch", title)
        self.settle()
        self.assertFalse(marker.exists())
        self.assertEqual(self.lines("report.args").count("--display-agent"), 1)


class TabTitleChain(Harness):
    """The wired entry point is herdr-tab-title.sh, which must keep protecting hand-made tab names."""

    def setUp(self):
        super().setUp()
        self.set_tab("1", 1)
        # 配備後の名前 (executable_ を外したもの) で並べる。tab-title は同じディレクトリの summary を呼ぶ
        self.deployed = self.root / "deployed"
        self.deployed.mkdir()
        for src in (TAB_TITLE, SUMMARY):
            (self.deployed / src.name.removeprefix("executable_")).write_text(src.read_text())
        self.tab_script = self.deployed / "herdr-tab-title.sh"

    def set_tab(self, label, panes, title="既存機能の動作復旧"):
        (self.stub / "pane.json").write_text(json.dumps(
            {"result": {"pane": {"tab_id": "w1:t1", "terminal_title_stripped": title}}}))
        (self.stub / "tab.json").write_text(json.dumps(
            {"result": {"tab": {"label": label, "pane_count": panes}}}))

    def tab_stop(self, **kw):
        return self.stop(script=self.tab_script, **kw)

    def renames(self):
        return [line for line in self.lines("herdr.log") if line.startswith("tab rename")]

    def test_summary_runs_from_tab_title_hook(self):
        self.tab_stop()
        self.wait_for("report.log")
        self.assertEqual(self.reported_title(), "認証まわりの修正")

    def test_numeric_tab_is_renamed_to_terminal_title(self):
        self.tab_stop()
        self.assertEqual(self.renames(), ["tab rename w1:t1 既存機能の動作復旧"])

    def test_hand_made_tab_name_is_kept(self):
        self.set_tab("my tab", 1)
        self.tab_stop()
        self.wait_for("report.log")
        self.assertEqual(self.renames(), [])

    def test_split_tab_is_kept(self):
        self.set_tab("1", 2)
        self.tab_stop()
        self.assertEqual(self.renames(), [])

    def test_tab_title_exits_zero_when_summary_is_missing(self):
        # 配備先に summary スクリプトが無くても (古い配備) 既存の動作は変わらない
        copy = self.root / "hooks"
        copy.mkdir()
        target = copy / "herdr-tab-title.sh"
        target.write_text(TAB_TITLE.read_text())
        self.stop(script=target)
        self.assertEqual(self.renames(), ["tab rename w1:t1 既存機能の動作復旧"])
        self.assertEqual(self.lines("claude.log"), [])

    def test_tab_title_exits_zero_when_herdr_env_is_missing(self):
        self.tab_stop(extra_env={"HERDR_ENV": "0"})
        self.assertEqual(self.lines("herdr.log"), [])



if __name__ == "__main__":
    unittest.main()
