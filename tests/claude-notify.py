"""claude-notify と claude-notify-focus。偽の notify-send・osascript・curl・herdr・hyprctl だけを使い、実物は呼ばない。

herdr の中のエージェントの完了と承認待ちは herdr ([ui.toast]) が通知するので、claude-notify はデスクトップに出さない。
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
NOTIFY = ROOT / "dot_local/bin/executable_claude-notify"
FOCUS = ROOT / "dot_local/bin/executable_claude-notify-focus"
HERDR_CONFIG = ROOT / "private_dot_config/herdr/config.toml.tmpl"
SETTINGS = ROOT / "dot_claude/private_settings.json.tmpl"
HYPR = ROOT / "private_dot_config/hypr/hyprland.lua.tmpl"
CHEZMOI = shutil.which("chezmoi")
JQ = shutil.which("jq")

# 呼ばれた引数と標準入力を <名前>.jsonl に残す。hyprctl clients -j だけはウィンドウの一覧を返す
RECORDER = f'''#!{sys.executable}
import json, os, pathlib, sys
d = pathlib.Path(os.environ['FAKE_DIR']); name = pathlib.Path(sys.argv[0]).name
data = sys.stdin.read() if name == 'curl' else ''
with (d/(name+'.jsonl')).open('a') as f: f.write(json.dumps({{'args': sys.argv[1:], 'stdin': data}})+'\\n')
if name == 'hostname': print('testhost')
if name == 'hyprctl' and sys.argv[1:3] == ['clients', '-j']:
    print(json.dumps([{{'class': 'firefox', 'title': 'chezmoi', 'address': '0x1'}},
                      {{'class': 'ghostty', 'title': 'fp7: other', 'address': '0x2'}},
                      {{'class': 'ghostty', 'title': 'fp7: chezmoi', 'address': '0x3'}}]))
'''

# herdr-fail.txt に書いた「サブコマンド 2 語」は失敗させる
FAKE_HERDR = f'''#!{sys.executable}
import json, os, pathlib, sys
d = pathlib.Path(os.environ['FAKE_DIR']); args = sys.argv[1:]
with (d/'herdr.jsonl').open('a') as f: f.write(json.dumps({{'args': args, 'stdin': ''}})+'\\n')
fail = (d/'herdr-fail.txt').read_text().splitlines() if (d/'herdr-fail.txt').exists() else []
if ' '.join(args[:2]) in fail: sys.exit(1)
if args[:2] == ['pane', 'current']:
    print(json.dumps({{'result': {{'pane': {{'workspace_id': 'w1', 'tab_id': 'w1:t1', 'pane_id': 'w1:p1'}}}}}}))
elif args[:2] == ['workspace', 'get']:
    print(json.dumps({{'result': {{'workspace': {{'workspace_id': 'w1', 'number': 2, 'label': 'chez\\u0007moi'}}}}}}))
'''

SYSTEM_TOOLS = ("bash", "cat", "mkdir", "tail", "grep", "tr", "cut", "basename", "sed", "rm", "head",
                "pgrep", "uname", "env")


@unittest.skipUnless(JQ, "jq が必要")
class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.bin = self.d / "bin"
        self.sys = self.d / "sys"
        for path in (self.bin, self.sys, self.d / "home", self.d / "run", self.d / "config"):
            path.mkdir()
        # 実物の notify-send などを PATH から外すため、必要な道具だけを並べる
        for tool in SYSTEM_TOOLS:
            found = shutil.which(tool)
            if found:
                (self.sys / tool).symlink_to(found)
        (self.sys / "jq").symlink_to(JQ)
        for name in ("notify-send", "osascript", "curl", "hyprctl", "hostname", "tmux"):
            self.install(name, RECORDER)
        self.install("herdr", FAKE_HERDR)

    def install(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def run_script(self, script, *args, inside=False, stdin="", env=None):
        full = {"PATH": f"{self.bin}:{self.sys}", "HOME": str(self.d / "home"), "FAKE_DIR": str(self.d),
                "XDG_RUNTIME_DIR": str(self.d / "run"), "XDG_CONFIG_HOME": str(self.d / "config"),
                "LC_ALL": "C.UTF-8", "TMUX_PANE": "%1", "TMUX": "/tmp/tmux-1000/default,1,0"}
        if inside:
            full.update({"HERDR_ENV": "1", "HERDR_BIN_PATH": str(self.bin / "herdr"),
                         "HERDR_PANE_ID": "w9:p9"})
        full.update(env or {})
        proc = subprocess.run(["bash", str(script), *args], env=full, input=stdin, capture_output=True,
                              text=True, encoding="utf-8", cwd=self.d)
        self.assertEqual(self.calls("tmux"), [], "tmux を呼ばない")
        return proc

    def calls(self, name):
        path = self.d / f"{name}.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    @property
    def last(self):
        return self.d / "run/claude-code-notify/last_herdr"


# transcript の最後の発言から作る本文。末尾の改行は空白になる
LAST = "テストを直しました "


class Notify(Base):
    def hook(self, text="テストを直しました"):
        transcript = self.d / "t.jsonl"
        transcript.write_text(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": text}]}}) + "\n")
        return json.dumps({"cwd": "/work/chezmoi", "transcript_path": str(transcript),
                           "message": "Claude needs your permission", "title": "許可"})

    def test_stop_outside_herdr_notifies_desktop(self):
        r = self.run_script(NOTIFY, "stop", stdin=self.hook())
        self.assertEqual(r.returncode, 0, r.stderr)
        sent = self.calls("notify-send")
        self.assertEqual(len(sent), 1)
        args = sent[0]["args"]
        self.assertIn("Claude Code: 完了", args)
        self.assertEqual(args[-1], LAST + "\\ncwd: /work/chezmoi")
        # 移動先が無いので、押して待つ通知 (-A / --wait) にしない
        self.assertFalse([a for a in args if a.startswith("-A") or a == "--wait"])
        self.assertEqual(self.calls("herdr"), [])
        self.assertFalse(self.last.exists())

    def test_stop_inside_herdr_leaves_desktop_to_herdr(self):
        r = self.run_script(NOTIFY, "stop", inside=True, stdin=self.hook())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls("notify-send"), [])
        self.assertEqual(self.calls("osascript"), [])
        # Super+Shift+R の移動先を、環境変数ではなく herdr に聞いた今の所属で残す
        self.assertEqual(self.last.read_text().splitlines(), ["w1", "w1:t1", "w1:p1", "chezmoi"])

    def test_notification_inside_herdr_leaves_desktop_to_herdr(self):
        r = self.run_script(NOTIFY, "notification", inside=True, stdin=self.hook())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls("notify-send"), [])
        self.assertTrue(self.last.exists())

    def test_notification_outside_herdr_uses_hook_message(self):
        r = self.run_script(NOTIFY, "notification", stdin=self.hook())
        self.assertEqual(r.returncode, 0, r.stderr)
        args = self.calls("notify-send")[0]["args"]
        self.assertIn("Claude Code: 許可", args)
        self.assertEqual(args[-1], "Claude needs your permission\\ncwd: /work/chezmoi")

    def test_other_callers_still_notify_inside_herdr(self):
        # security-update-check.sh は zsh から裏で動くので、herdr の環境変数を引き継ぐことがある
        r = self.run_script(NOTIFY, "security-update", "公式更新 3 / AUR 0 / 要対応CVE 0", inside=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        sent = self.calls("notify-send")
        self.assertEqual(len(sent), 1)
        self.assertTrue(sent[0]["args"][-1].startswith("公式更新 3 / AUR 0 / 要対応CVE 0"))
        self.assertFalse(self.last.exists(), "エージェント以外の通知は移動先にしない")

    def test_phone_push_stays_inside_herdr(self):
        conf = self.d / "config/claude-notify"
        conf.mkdir()
        (conf / "config").write_text("NTFY_SERVER=https://ntfy.example\nNTFY_TOPIC=topic\n")
        r = self.run_script(NOTIFY, "stop", inside=True, stdin=self.hook(),
                            env={"CLAUDE_NOTIFY_PHONE": "always"})
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls("notify-send"), [])
        pushed = self.calls("curl")
        self.assertEqual(len(pushed), 1)
        self.assertIn("Title: Claude Code: 完了 [chezmoi @ testhost]", pushed[0]["args"])
        self.assertEqual(pushed[0]["args"][-1], "https://ntfy.example/topic")
        self.assertEqual(pushed[0]["stdin"], LAST)

    def test_herdr_lookup_failure_still_leaves_desktop_to_herdr(self):
        (self.d / "herdr-fail.txt").write_text("pane current\n")
        r = self.run_script(NOTIFY, "stop", inside=True, stdin=self.hook())
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls("notify-send"), [])
        self.assertFalse(self.last.exists())

    def test_app_name_comes_from_claude_notify_app(self):
        # Pi's notify.ts passes CLAUDE_NOTIFY_APP=Pi and its text as arguments, with no hook JSON on stdin.
        app = {"CLAUDE_NOTIFY_APP": "Pi"}
        r = self.run_script(NOTIFY, "stop", "直しました", env=app)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_script(NOTIFY, "notification", "jev-gate: 承認待ち", env=app)
        self.assertEqual(r.returncode, 0, r.stderr)
        stop, waiting = (c["args"] for c in self.calls("notify-send"))
        self.assertIn("--app-name=Pi", stop)
        self.assertIn("Pi: 完了", stop)
        self.assertTrue(stop[-1].startswith("直しました"))
        self.assertIn("--app-name=Pi", waiting)
        self.assertIn("Pi: 入力待ち", waiting)
        self.assertTrue(waiting[-1].startswith("jev-gate: 承認待ち"))

    def test_app_name_reaches_the_phone_and_defaults_to_claude_code(self):
        conf = self.d / "config/claude-notify"
        conf.mkdir()
        (conf / "config").write_text("NTFY_SERVER=https://ntfy.example\nNTFY_TOPIC=topic\n")
        phone = {"CLAUDE_NOTIFY_PHONE": "always"}
        r = self.run_script(NOTIFY, "stop", inside=True, stdin=self.hook(), env=dict(phone, CLAUDE_NOTIFY_APP="Pi"))
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_script(NOTIFY, "stop", stdin=self.hook(), env=dict(phone, CLAUDE_NOTIFY_APP=""))
        self.assertEqual(r.returncode, 0, r.stderr)
        titles = [a for c in self.calls("curl") for a in c["args"] if a.startswith("Title: ")]
        self.assertEqual(sorted(titles), ["Title: Claude Code: 完了 [chezmoi @ testhost]",
                                          "Title: Pi: 完了 [chezmoi @ testhost]"])
        self.assertIn("--app-name=Claude Code", self.calls("notify-send")[0]["args"])

    def test_macos_uses_osascript(self):
        (self.bin / "notify-send").unlink()
        r = self.run_script(NOTIFY, "stop", stdin=self.hook())
        self.assertEqual(r.returncode, 0, r.stderr)
        args = self.calls("osascript")[0]["args"]
        self.assertEqual(args[-2:], ["Claude Code: 完了", LAST + "\ncwd: /work/chezmoi"])


class Focus(Base):
    def assert_focused(self, calls, expected):
        self.assertEqual([c["args"] for c in calls], expected)

    def assert_window(self, address):
        dispatch = [c["args"] for c in self.calls("hyprctl") if c["args"][0] == "dispatch"]
        self.assertEqual(dispatch, [["dispatch", f"hl.dsp.focus({{ window = 'address:{address}' }})"]])

    def test_herdr_target(self):
        r = self.run_script(FOCUS, "--herdr", "w1", "w1:t1", "w1:p1", "chezmoi")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_focused(self.calls("herdr"), [["agent", "focus", "w1:p1"]])
        self.assert_window("0x3")

    def test_last_target_from_notify(self):
        self.last.parent.mkdir(parents=True)
        self.last.write_text("w1\nw1:t1\nw1:p1\nchezmoi\n")
        r = self.run_script(FOCUS, "--last")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_focused(self.calls("herdr"), [["agent", "focus", "w1:p1"]])
        self.assert_window("0x3")

    def test_last_without_record_does_nothing(self):
        r = self.run_script(FOCUS, "--last")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.calls("herdr"), [])
        self.assertEqual(self.calls("hyprctl"), [])

    def test_falls_back_to_tab_then_workspace(self):
        (self.d / "herdr-fail.txt").write_text("agent focus\ntab focus\n")
        r = self.run_script(FOCUS, "--herdr", "w1", "w1:t1", "w1:p1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assert_focused(self.calls("herdr"), [["agent", "focus", "w1:p1"], ["tab", "focus", "w1:t1"],
                                                  ["workspace", "focus", "w1"]])
        # space 名が無ければ最初の Ghostty を前に出す
        self.assert_window("0x2")

    def test_tmux_target_is_rejected(self):
        r = self.run_script(FOCUS, "main", "1", "0")
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)
        self.assertEqual(self.calls("herdr"), [])


def render(path, data):
    """--source が無いと本体のソースを読んでしまう。"""
    return subprocess.run(
        [CHEZMOI, "--source", str(ROOT), "execute-template", "--override-data", json.dumps(data)],
        input=path.read_text(), capture_output=True, text=True, check=True).stdout


class Wiring(unittest.TestCase):
    """claude-notify が herdr に任せる通知と、herdr の設定・フック・Hyprland の呼び出しを揃える。"""

    @unittest.skipUnless(CHEZMOI, "chezmoi が必要")
    def test_herdr_delivers_agent_notifications(self):
        # Linux は notify-send (swaync)。Mac は terminal-notifier が無いと osascript になるので Ghostty に任せる
        for os_name, delivery in (("linux", "system"), ("darwin", "terminal")):
            with self.subTest(os=os_name):
                config = tomllib.loads(render(HERDR_CONFIG, {"chezmoi": {"os": os_name}}))
                self.assertEqual(config["ui"]["toast"]["delivery"], delivery)

    @unittest.skipUnless(CHEZMOI, "chezmoi が必要")
    def test_hooks_call_claude_notify(self):
        hooks = json.loads(render(SETTINGS, {}))["hooks"]
        for event, mode in (("Stop", "stop"), ("Notification", "notification")):
            with self.subTest(event=event):
                commands = [h["command"] for group in hooks[event] for h in group["hooks"]]
                self.assertEqual([c for c in commands if "claude-notify" in c],
                                 [f"{Path.home()}/.local/bin/claude-notify {mode} >/dev/null 2>&1"])

    def test_hyprland_focuses_last_target(self):
        binds = [line for line in HYPR.read_text().splitlines() if "claude-notify-focus" in line]
        self.assertEqual(len(binds), 1)
        self.assertIn('hl.dsp.exec_cmd("~/.local/bin/claude-notify-focus --last")', binds[0])
        self.assertTrue(re.search(r'mainMod \.\. " \+ SHIFT \+ R"', binds[0]))


if __name__ == "__main__":
    unittest.main()
