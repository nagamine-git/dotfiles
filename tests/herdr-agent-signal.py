"""agent-signal の signal.sh。偽の herdr だけを使い、実物は起動しない。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "dot_local/share/herdr-plugins/agent-signal"
CONFIG = ROOT / "private_dot_config/herdr/config.toml"

BLOCKED, DONE, WORKING, IDLE = "\U000F08BE", "\U000F08BD", "\U000F08BC", "\U000F08BF"

FAKE_HERDR = '''#!/usr/bin/env python3
import json, os, pathlib, sys
h = pathlib.Path(os.environ['FAKE_DIR']); args = sys.argv[1:]
if args[:2] == ['agent', 'list']:
    if (h/'agents-fail').exists(): sys.exit(1)
    print(json.dumps({'result': {'agents': json.loads((h/'agents.json').read_text())}}))
elif args[:2] == ['workspace', 'list']:
    if (h/'workspaces-fail').exists(): sys.exit(1)
    print(json.dumps({'result': {'workspaces': json.loads((h/'workspaces.json').read_text())}}))
elif args[:2] == ['pane', 'report-metadata']:
    with (h/'reports.jsonl').open('a') as f: f.write(json.dumps(args[2:])+'\\n')
    if (h/'report-fail').exists(): sys.exit(1)
'''


def agent(pane, status, workspace="w1", tokens=None):
    return {"pane_id": pane, "agent_status": status, "workspace_id": workspace, "tokens": tokens or {}}


class Signal(unittest.TestCase):
    def run_signal(self, agents, workspaces=None, fail=()):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        (d / "herdr").write_text(FAKE_HERDR)
        (d / "herdr").chmod(0o755)
        (d / "agents.json").write_text(json.dumps(agents))
        if workspaces is None:
            workspaces = [{"workspace_id": "w1", "label": "chezmoi"}]
        (d / "workspaces.json").write_text(json.dumps(workspaces))
        for name in fail:
            (d / name).touch()
        env = {"PATH": os.environ["PATH"], "FAKE_DIR": str(d), "HERDR_BIN_PATH": str(d / "herdr")}
        result = subprocess.run(["sh", "signal.sh", "sync"], cwd=PLUGIN, env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        reports = d / "reports.jsonl"
        return [json.loads(x) for x in reports.read_text().splitlines()] if reports.exists() else []

    def report(self, pane, value):
        return [pane, "--source", "dotfiles:agent-signal", "--token", f"signal_workspace={value}",
                "--clear-token", "signal"]

    def test_each_state_gets_its_glyph_and_the_name(self):
        for status, glyph in (("blocked", BLOCKED), ("done", DONE), ("working", WORKING), ("idle", IDLE)):
            self.assertEqual(self.run_signal([agent("w1:p1", status)]),
                             [self.report("w1:p1", f"{glyph} chezmoi")], status)

    def test_unknown_is_name_only(self):
        for status in ("unknown", "", None):
            self.assertEqual(self.run_signal([agent("w1:p1", status)]), [self.report("w1:p1", "chezmoi")])

    def test_name_is_taken_from_the_panes_workspace(self):
        reports = self.run_signal(
            [agent("w1:p1", "idle"), agent("w2:p3", "working", "w2")],
            [{"workspace_id": "w1", "label": "a=b c"}, {"workspace_id": "w2", "label": "日本語"}])
        self.assertEqual(reports, [self.report("w1:p1", f"{IDLE} a=b c"), self.report("w2:p3", f"{WORKING} 日本語")])

    def test_unavailable_name_keeps_existing_value(self):
        self.assertEqual(self.run_signal([agent("w9:p1", "idle", "w9")]), [])
        self.assertEqual(self.run_signal([agent("w1:p1", "idle")], [{"workspace_id": "w1", "label": ""}]), [])
        self.assertEqual(self.run_signal([agent("w1:p1", "idle")], fail=["workspaces-fail"]), [])

    def test_unchanged_value_is_not_reported_again(self):
        tokens = {"signal_workspace": f"{IDLE} chezmoi"}
        self.assertEqual(self.run_signal([agent("w1:p1", "idle", tokens=tokens)]), [])

    def test_old_token_is_cleared_even_if_value_is_current(self):
        tokens = {"signal_workspace": f"{IDLE} chezmoi", "signal": "x"}
        self.assertEqual(self.run_signal([agent("w1:p1", "idle", tokens=tokens)]),
                         [self.report("w1:p1", f"{IDLE} chezmoi")])

    def test_failures_exit_zero(self):
        self.assertEqual(self.run_signal([agent("w1:p1", "idle")], fail=["agents-fail"]), [])
        self.assertEqual(len(self.run_signal([agent("w1:p1", "idle")], fail=["report-fail"])), 1)


class Wiring(unittest.TestCase):
    def test_rows_use_the_combined_token(self):
        agents = tomllib.loads(CONFIG.read_text())["ui"]["sidebar"]["agents"]
        for rows in (agents["rows"], agents["rows_by_agent"]["claude"]):
            first = rows[0]
            self.assertEqual(first[0], "state_icon")
            tokens = [t["token"] if isinstance(t, dict) else t for t in first]
            self.assertIn("$signal_workspace", tokens)
            self.assertNotIn("workspace", tokens)
            self.assertNotIn("$signal", tokens)
            # 名前まで染まるので色の rules は使わない
            self.assertFalse([t for t in first if isinstance(t, dict) and "rules" in t])

    def test_manifest_follows_renames_and_moves(self):
        manifest = tomllib.loads((PLUGIN / "herdr-plugin.toml").read_text())
        events = {e["on"] for e in manifest["events"]}
        self.assertLessEqual({"pane.agent_status_changed", "pane.agent_detected", "workspace.renamed", "pane.moved"},
                             events)
        self.assertEqual(manifest["startup"][0]["command"], ["sh", "signal.sh", "sync"])


if __name__ == "__main__":
    unittest.main()
