"""herdr-git-diff の分岐。偽の herdr と lazygit だけを使い、実物は起動しない。"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_herdr-git-diff"
CONFIG = ROOT / "private_dot_config/herdr/config.toml"
MANIFEST = ROOT / "dot_local/share/herdr-plugins/git-diff/herdr-plugin.toml"
NVIM_INIT = ROOT / "private_dot_config/nvim/init.lua.tmpl"

FAKE_HERDR = '''#!/usr/bin/env python3
import json, os, pathlib, sys
h = pathlib.Path(os.environ['FAKE_DIR']); args = sys.argv[1:]
with (h/'herdr.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
if args[:2] == ['pane', 'process-info']:
    if (h/'info-fail').exists(): sys.exit(1)
    procs = json.loads((h/'procs.json').read_text())
    print(json.dumps({'result': {'process_info': {'foreground_processes': procs}}}))
elif args[:2] == ['pane', 'get']:
    if (h/'get-fail').exists(): sys.exit(1)
    print(json.dumps({'result': {'pane': {'foreground_cwd': '/fg/cwd'}}}))
elif args[:2] == ['pane', 'send-text']:
    if (h/'send-fail').exists(): sys.exit(1)
'''

FAKE_LAZYGIT = '''#!/bin/sh
echo run >> "$FAKE_DIR/lazygit.log"
'''


class HerdrGitDiff(unittest.TestCase):
    def run_script(self, procs, pane="w1:p1", info_fail=False, send_fail=False, get_fail=False,
                   active_cwd="/active/cwd"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        for name, body in (("herdr", FAKE_HERDR), ("lazygit", FAKE_LAZYGIT)):
            (d / name).write_text(body)
            (d / name).chmod(0o755)
        (d / "procs.json").write_text(json.dumps(procs))
        for flag, name in ((info_fail, "info-fail"), (send_fail, "send-fail"), (get_fail, "get-fail")):
            if flag:
                (d / name).touch()
        env = {"PATH": f"{d}:{os.environ['PATH']}", "FAKE_DIR": str(d),
               "HERDR_BIN_PATH": str(d / "herdr")}
        if pane:
            env["HERDR_ACTIVE_PANE_ID"] = pane
        if active_cwd:
            env["HERDR_ACTIVE_PANE_CWD"] = active_cwd
        result = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, cwd="/")
        calls = [json.loads(x) for x in (d / "herdr.jsonl").read_text().splitlines()] \
            if (d / "herdr.jsonl").exists() else []
        sent = [c for c in calls if c[:2] == ["pane", "send-text"]]
        popup = [c for c in calls if c[:3] == ["plugin", "pane", "open"]]
        # lazygit はプラグインの入口が起動するので、スクリプトが直接動かしてはいけない
        self.assertFalse((d / "lazygit.log").exists())
        return result, sent, popup

    def assert_popup(self, popup, cwd):
        self.assertEqual(popup, [["plugin", "pane", "open", "--plugin", "nagamine.git-diff",
                                  "--entrypoint", "lazygit", "--cwd", cwd]])

    def test_nvim_gets_toggle_without_popup(self):
        r, sent, popup = self.run_script([{"name": "nvim", "argv": ["nvim", "a.txt"]}])
        self.assertEqual(r.returncode, 0)
        self.assertEqual(popup, [])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][2], "w1:p1")
        # C-\ C-n で始め、挿入モードなどでも文字が入らない。最後は Enter
        self.assertEqual(sent[0][3], "\x1c\x0e:LazygitFloatToggle\r")

    def test_nvim_by_argv0_path(self):
        _, sent, popup = self.run_script([{"name": "x", "argv": ["/usr/bin/nvim"]}])
        self.assertEqual(len(sent), 1)
        self.assertEqual(popup, [])

    def test_sim_and_shell_open_popup_in_foreground_cwd(self):
        for procs in ([{"name": "sim", "argv": ["sim", "a"]}], [{"name": "zsh", "argv": ["zsh"]}],
                      [{"name": "nvim-qt", "argv": ["nvim-qt"]}], []):
            _, sent, popup = self.run_script(procs)
            self.assertEqual(sent, [])
            self.assert_popup(popup, "/fg/cwd")

    def test_detection_failure_opens_popup(self):
        _, sent, popup = self.run_script([{"name": "nvim", "argv": ["nvim"]}], info_fail=True)
        self.assertEqual(sent, [])
        self.assert_popup(popup, "/fg/cwd")

    def test_no_pane_id_uses_active_cwd(self):
        _, sent, popup = self.run_script([{"name": "nvim", "argv": ["nvim"]}], pane="")
        self.assertEqual(sent, [])
        self.assert_popup(popup, "/active/cwd")

    def test_send_failure_opens_popup(self):
        _, sent, popup = self.run_script([{"name": "nvim", "argv": ["nvim"]}], send_fail=True)
        self.assertEqual(len(sent), 1)
        self.assert_popup(popup, "/fg/cwd")

    def test_cwd_falls_back_to_active_then_pwd(self):
        procs = [{"name": "zsh", "argv": ["zsh"]}]
        _, _, popup = self.run_script(procs, get_fail=True)
        self.assert_popup(popup, "/active/cwd")
        # プラグインの既定の cwd (プラグインのディレクトリ) にはしない
        _, _, popup = self.run_script(procs, get_fail=True, active_cwd="")
        self.assert_popup(popup, "/")


class Wiring(unittest.TestCase):
    """スクリプトが呼ぶ名前と、それを定義する設定を揃える。"""

    def test_alt_g_is_shell_command(self):
        commands = tomllib.loads(CONFIG.read_text())["keys"]["command"]
        alt_g = [c for c in commands if c["key"] == "alt+g"]
        self.assertEqual(len(alt_g), 1)
        self.assertEqual(alt_g[0]["type"], "shell")
        self.assertIn("herdr-git-diff", alt_g[0]["command"])

    def test_plugin_entrypoint_is_90_percent_popup(self):
        manifest = tomllib.loads(MANIFEST.read_text())
        self.assertEqual(manifest["id"], "nagamine.git-diff")
        pane = manifest["panes"][0]
        self.assertEqual((pane["id"], pane["placement"], pane["width"], pane["height"]),
                         ("lazygit", "popup", "90%", "90%"))
        self.assertEqual(pane["command"], ["lazygit"])

    def test_nvim_defines_the_command_it_is_sent(self):
        init = NVIM_INIT.read_text()
        self.assertIn("nvim_create_user_command('LazygitFloatToggle'", init)
        self.assertNotIn("nvim_create_user_command('DiffviewToggle'", init)
        self.assertIn("'lazygit', 'status'", init)


if __name__ == "__main__":
    unittest.main()
