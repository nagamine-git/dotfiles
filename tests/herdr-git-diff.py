"""herdr-git-diff の分岐。偽の herdr と lazygit だけを使い、実物は起動しない。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_herdr-git-diff"

FAKE_HERDR = '''#!/usr/bin/env python3
import json, os, pathlib, sys
h = pathlib.Path(os.environ['FAKE_DIR']); args = sys.argv[1:]
with (h/'herdr.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
if args[:2] == ['pane', 'process-info']:
    if (h/'info-fail').exists(): sys.exit(1)
    procs = json.loads((h/'procs.json').read_text())
    print(json.dumps({'result': {'process_info': {'foreground_processes': procs}}}))
elif args[:2] == ['pane', 'send-text']:
    if (h/'send-fail').exists(): sys.exit(1)
'''

FAKE_LAZYGIT = '''#!/bin/sh
echo run >> "$FAKE_DIR/lazygit.log"
'''


class HerdrGitDiff(unittest.TestCase):
    def run_script(self, procs, pane="w1:p1", info_fail=False, send_fail=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        for name, body in (("herdr", FAKE_HERDR), ("lazygit", FAKE_LAZYGIT)):
            (d / name).write_text(body)
            (d / name).chmod(0o755)
        (d / "procs.json").write_text(json.dumps(procs))
        if info_fail:
            (d / "info-fail").touch()
        if send_fail:
            (d / "send-fail").touch()
        env = {"PATH": f"{d}:{os.environ['PATH']}", "FAKE_DIR": str(d),
               "HERDR_BIN_PATH": str(d / "herdr")}
        if pane:
            env["HERDR_ACTIVE_PANE_ID"] = pane
        result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True)
        calls = [json.loads(x) for x in (d / "herdr.jsonl").read_text().splitlines()] \
            if (d / "herdr.jsonl").exists() else []
        sent = [c for c in calls if c[:2] == ["pane", "send-text"]]
        lazygit = (d / "lazygit.log").exists()
        return result, sent, lazygit

    def test_nvim_gets_toggle_without_popup_command(self):
        r, sent, lazygit = self.run_script([{"name": "nvim", "argv": ["nvim", "a.txt"]}])
        self.assertEqual(r.returncode, 0)
        self.assertFalse(lazygit)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][2], "w1:p1")
        # C-\ C-n で始め、挿入モードなどでも文字が入らない。最後は Enter
        self.assertEqual(sent[0][3], "\x1c\x0e:DiffviewToggle\r")

    def test_nvim_by_argv0_path(self):
        _, sent, lazygit = self.run_script([{"name": "x", "argv": ["/usr/bin/nvim"]}])
        self.assertEqual(len(sent), 1)
        self.assertFalse(lazygit)

    def test_sim_and_shell_fall_back_to_lazygit(self):
        for procs in ([{"name": "sim", "argv": ["sim", "a"]}], [{"name": "zsh", "argv": ["zsh"]}],
                      [{"name": "nvim-qt", "argv": ["nvim-qt"]}], []):
            _, sent, lazygit = self.run_script(procs)
            self.assertEqual(sent, [])
            self.assertTrue(lazygit)

    def test_detection_failure_falls_back(self):
        _, sent, lazygit = self.run_script([{"name": "nvim", "argv": ["nvim"]}], info_fail=True)
        self.assertEqual(sent, [])
        self.assertTrue(lazygit)

    def test_no_pane_id_falls_back(self):
        _, sent, lazygit = self.run_script([{"name": "nvim", "argv": ["nvim"]}], pane="")
        self.assertEqual(sent, [])
        self.assertTrue(lazygit)

    def test_send_failure_falls_back(self):
        _, sent, lazygit = self.run_script([{"name": "nvim", "argv": ["nvim"]}], send_fail=True)
        self.assertEqual(len(sent), 1)
        self.assertTrue(lazygit)


if __name__ == "__main__":
    unittest.main()
