"""Vicinae のランチャー。Hyprland の設定の描画、Vicinae の設定ファイル、Meet に参加するスクリプトコマンド。

Vicinae 本体と gog・xdg-open は呼ばず、偽物だけを使う。
"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HYPR = ROOT / "home/private_dot_config/hypr/hyprland.lua.tmpl"
IGNORE = ROOT / "home/.chezmoiignore"
VICINAE_DIR = ROOT / "home/private_dot_config/vicinae"
MEET = ROOT / "home/dot_local/share/vicinae/scripts/executable_meet-join.sh"
CHEZMOI = shutil.which("chezmoi")
JQ = shutil.which("jq")

# 呼ばれた引数を <名前>.jsonl に残す。gog は FAKE_DIR/events.json を返し、gog-fail があれば失敗する
RECORDER = f'''#!{sys.executable}
import json, os, pathlib, sys
d = pathlib.Path(os.environ['FAKE_DIR']); name = pathlib.Path(sys.argv[0]).name
with (d/(name+'.jsonl')).open('a') as f: f.write(json.dumps({{'args': sys.argv[1:]}})+'\\n')
if name == 'gog':
    if (d/'gog-fail').exists(): sys.exit(1)
    print((d/'events.json').read_text())
'''

# setsid -f は切り離さずにそのまま実行する (記録をテストの中で読むため)
FAKE_SETSID = '''#!/bin/sh
[ "$1" = -f ] && shift
exec "$@"
'''

SYSTEM_TOOLS = ("bash", "date", "timeout", "env", "cat", "printf")

# Vicinae の電源の項目 → customProgram で呼ぶ引数なしのスクリプトと、それが hyprctl に渡す引数
POWER_PROGRAMS = {
    "lock": ("lock-screen", ["dispatch", 'hl.dsp.exec_cmd("hyprlock")']),
    "logout": ("hypr-logout", ["dispatch", "hl.dsp.exit()"]),
}


def render(text, hostname, os_name="linux"):
    """--source が無いと本体のソースを読んでしまう。"""
    return subprocess.run(
        [CHEZMOI, "--source", str(ROOT), "execute-template",
         "--override-data", json.dumps({"chezmoi": {"hostname": hostname, "os": os_name}})],
        input=text, capture_output=True, text=True, check=True).stdout


def iso(epoch):
    return datetime.fromtimestamp(epoch).astimezone().isoformat(timespec="seconds")


def event(summary, start, end, link=None, video=None, attendees=None):
    ev = {"summary": summary, "start": {"dateTime": iso(start)}, "end": {"dateTime": iso(end)}}
    if link:
        ev["hangoutLink"] = link
    if video:
        ev["conferenceData"] = {"entryPoints": [{"entryPointType": "phone", "uri": "tel:+1"},
                                                {"entryPointType": "video", "uri": video}]}
    if attendees is not None:
        ev["attendees"] = attendees
    return ev


@unittest.skipUnless(CHEZMOI, "chezmoi が必要")
class HyprlandBinds(unittest.TestCase):
    def test_launcher_keys_open_vicinae(self):
        for hostname in ("am5-itx", "fp7-e14"):
            with self.subTest(hostname=hostname):
                hypr = render(HYPR.read_text(), hostname)
                self.assertIn('hl.exec_cmd("vicinae server")', hypr)
                # 割り当ての後ろに { description = ... } が付くので、行の頭だけを見る
                self.assertIn('hl.bind(mainMod .. " + space", hl.dsp.exec_cmd("vicinae toggle")', hypr)
                self.assertIn("vicinae 'vicinae://launch/applications?toggle=true'", hypr)
                self.assertIn("vicinae 'vicinae://launch/wm/switch-windows?toggle=true'", hypr)
                self.assertIn('namespace = "vicinae"', hypr)
                self.assertNotIn("unified_launcher", hypr)
                self.assertNotIn("rofi", hypr)   # rofi の用途はすべて vicinae dmenu に移した


class VicinaeConfig(unittest.TestCase):
    def load_jsonc(self, text):
        # 行全体のコメントだけを使っている前提で外す
        text = "\n".join(line for line in text.splitlines() if not re.match(r"\s*//", line))
        return json.loads(text)

    def test_settings_imports_managed_file(self):
        # settings.json は Vicinae が GUI の変更を書き込むので、無いときだけ作る (create_)
        settings = json.loads((VICINAE_DIR / "create_settings.json").read_text())
        for name in settings["imports"]:
            self.assertTrue((VICINAE_DIR / name).is_file() or (VICINAE_DIR / f"{name}.tmpl").is_file(), name)

    @unittest.skipUnless(CHEZMOI, "chezmoi が必要")
    def test_managed_config(self):
        for hostname in ("am5-itx", "fp7-e14"):
            with self.subTest(hostname=hostname):
                cfg = self.load_jsonc(render((VICINAE_DIR / "chezmoi.jsonc.tmpl").read_text(), hostname))
                self.assertIs(cfg["telemetry"]["system_info"], False)
                self.assertIs(cfg["input_server"]["enabled"], False)

    @unittest.skipUnless(CHEZMOI, "chezmoi が必要")
    def test_power_programs_are_single_paths(self):
        # シェルを通さずに分割されても同じに動くよう、引用符・空白・~ を含まない絶対パスだけにする
        for hostname in ("am5-itx", "fp7-e14"):
            home = render("{{ .chezmoi.homeDir }}", hostname)
            cfg = self.load_jsonc(render((VICINAE_DIR / "chezmoi.jsonc.tmpl").read_text(), hostname))
            power = cfg["providers"]["power"]["entrypoints"]
            for entry, (script, _) in POWER_PROGRAMS.items():
                with self.subTest(hostname=hostname, entry=entry):
                    program = power[entry]["preferences"]["customProgram"]
                    self.assertRegex(program, r"\A/[^\s'\"\\~$`;|&]+\Z")
                    self.assertEqual(program, f"{home}/.local/bin/{script}")

    @unittest.skipUnless(CHEZMOI, "chezmoi が必要")
    def test_power_programs_are_installed_executable(self):
        # customProgram の先のスクリプトを空の destination に apply し、実行可能なファイルとして置かれて
        # 引数なしで hyprctl を正しい引数で呼ぶことを確かめる (hyprctl は偽物)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        dest, fake = d / "home", d / "bin"
        (dest / ".local/bin").mkdir(parents=True)  # 対象のファイルだけを apply すると親は作られない
        fake.mkdir()
        (d / "chezmoi.toml").write_text("")
        targets = [dest / ".local/bin" / script for script, _ in POWER_PROGRAMS.values()]
        subprocess.run(
            [CHEZMOI, "--source", str(ROOT), "--destination", str(dest), "--config", str(d / "chezmoi.toml"),
             "--persistent-state", str(d / "state.boltdb"),
             "--override-data", json.dumps({"chezmoi": {"hostname": "fp7-e14", "os": "linux"}}),
             "apply", "--include", "files", *map(str, targets)],
            capture_output=True, text=True, check=True)
        (fake / "bash").symlink_to(shutil.which("bash"))
        (fake / "hyprctl").write_text(RECORDER)
        (fake / "hyprctl").chmod(0o755)
        for script, args in POWER_PROGRAMS.values():
            with self.subTest(script=script):
                path = dest / ".local/bin" / script
                self.assertTrue(path.is_file())
                self.assertTrue(os.access(path, os.X_OK))
                log = d / "hyprctl.jsonl"
                log.unlink(missing_ok=True)
                res = subprocess.run([str(path)], env={"PATH": str(fake), "FAKE_DIR": str(d)},
                                     capture_output=True, text=True)
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual([json.loads(line)["args"] for line in log.read_text().splitlines()], [args])

    @unittest.skipUnless(CHEZMOI, "chezmoi が必要")
    def test_linux_only(self):
        darwin = render(IGNORE.read_text(), "m1pro", "darwin").splitlines()
        linux = render(IGNORE.read_text(), "fp7-e14").splitlines()
        patterns = [".config/vicinae", ".local/share/vicinae"]
        patterns += [f".local/bin/{script}" for script, _ in POWER_PROGRAMS.values()]
        for pattern in patterns:
            self.assertIn(pattern, darwin)
            self.assertNotIn(pattern, linux)


@unittest.skipUnless(JQ, "jq が必要")
class MeetJoin(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name)
        self.bin = self.d / "bin"
        self.home = self.d / "home"
        for path in (self.bin, self.home):
            path.mkdir()
        # 実物の gog と xdg-open を PATH から外すため、必要な道具だけを並べる
        for tool in SYSTEM_TOOLS:
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to(found)
        (self.bin / "jq").symlink_to(JQ)
        for name in ("gog", "xdg-open"):
            self.install(name, RECORDER)
        self.install("setsid", FAKE_SETSID)

    def install(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def events(self, *items):
        (self.d / "events.json").write_text(json.dumps(list(items)))

    def run_meet(self):
        env = {"PATH": str(self.bin), "HOME": str(self.home), "FAKE_DIR": str(self.d), "LANG": "C.UTF-8"}
        return subprocess.run(["bash", str(MEET)], env=env, capture_output=True, text=True)

    def calls(self, name):
        path = self.d / f"{name}.jsonl"
        return [json.loads(line)["args"] for line in path.read_text().splitlines()] if path.exists() else []

    def test_opens_meeting_in_progress_before_later_ones(self):
        now = int(time.time())
        self.events(
            event("終わった会議", now - 3600, now - 600, link="https://meet.google.com/old"),
            event("次の会議", now + 1800, now + 3600, link="https://meet.google.com/next"),
            event("リンクなし", now - 300, now + 600),
            event("定例", now - 300, now + 1500, link="https://meet.google.com/now"),
        )
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines()[0], "進行中  定例")
        self.assertEqual(self.calls("xdg-open"), [["https://meet.google.com/now"]])
        self.assertEqual(self.calls("gog")[0][:2], ["cal", "events"])

    def test_upcoming_meeting_from_conference_data(self):
        now = int(time.time())
        self.events(event("1on1", now + 30 * 60 + 30, now + 3600, video="https://meet.google.com/v"))
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines()[0], "30分後  1on1")
        self.assertEqual(self.calls("xdg-open"), [["https://meet.google.com/v"]])

    def test_ended_within_grace_is_still_opened(self):
        now = int(time.time())
        self.events(event("延長中", now - 3600, now - 120, link="https://meet.google.com/late"))
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.calls("xdg-open"), [["https://meet.google.com/late"]])

    def test_rejects_links_that_are_not_meet(self):
        # 招待は外部の誰でも送れる。先に始まる偽の予定に押しのけられず、本物の Meet だけを開く
        now = int(time.time())
        bad = ("file:///etc/passwd", "https://meet.google.com.evil.tld/abc",
               "https://meet.google.com@evil.tld/abc", "javascript:alert(1)",
               "https://meet.google.com/abc\nfile:///etc/passwd", "http://meet.google.com/abc",
               "https://evil.tld/https://meet.google.com/abc")
        self.events(
            *[event(f"偽{i}", now - 600 + i, now + 600, link=url) for i, url in enumerate(bad)],
            event("偽のビデオ", now - 600, now + 600, video="https://meet.google.com.evil.tld/v"),
            # 秒の境目をまたいでも「30分後」になるよう 30 秒の余裕を持たせる
            event("本物", now + 30 * 60 + 30, now + 3600, link="https://meet.google.com/abc-defg-hij"),
        )
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines()[0], "30分後  本物")
        self.assertEqual(self.calls("xdg-open"), [["https://meet.google.com/abc-defg-hij"]])

    def test_falls_back_to_meet_video_entry_when_hangout_link_is_bad(self):
        now = int(time.time())
        self.events(event("定例", now - 60, now + 600, link="https://meet.google.com@evil.tld/x",
                          video="https://meet.google.com/abc-defg-hij?authuser=0"))
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.calls("xdg-open"), [["https://meet.google.com/abc-defg-hij?authuser=0"]])

    def test_only_rejected_links_opens_nothing_and_says_why(self):
        now = int(time.time())
        self.events(event("Zoom", now - 60, now + 600, video="https://zoom.us/j/1"),
                    event("偽", now - 60, now + 600, link="javascript:alert(1)"))
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("開きません", res.stdout.splitlines()[0])
        self.assertEqual(self.calls("xdg-open"), [])

    def test_skips_meetings_i_declined(self):
        # 自分 (self) が断った予定は、進行中でも開かない。ほかの人が断っただけなら開く
        now = int(time.time())
        me_declined = [{"email": "me@example.com", "self": True, "responseStatus": "declined"},
                       {"email": "a@example.com", "responseStatus": "accepted"}]
        other_declined = [{"email": "me@example.com", "self": True, "responseStatus": "accepted"},
                          {"email": "a@example.com", "responseStatus": "declined"}]
        self.events(
            event("断った定例", now - 300, now + 1500, link="https://meet.google.com/declined", attendees=me_declined),
            event("1on1", now + 30 * 60 + 30, now + 3600, link="https://meet.google.com/ok", attendees=other_declined),
        )
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines()[0], "30分後  1on1")
        self.assertEqual(self.calls("xdg-open"), [["https://meet.google.com/ok"]])

    def test_only_declined_meetings_opens_nothing(self):
        now = int(time.time())
        self.events(event("断った定例", now - 60, now + 600, link="https://meet.google.com/declined",
                          attendees=[{"self": True, "responseStatus": "declined"}]))
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.splitlines()[0], "これからの Meet はありません")
        self.assertEqual(self.calls("xdg-open"), [])

    def test_odd_attendees_do_not_break_parsing(self):
        # attendees が配列でない・要素が文字列でも、予定の読み取りは失敗させない
        now = int(time.time())
        self.events(event("A", now - 60, now + 600, link="https://meet.google.com/a", attendees="me"),
                    event("B", now + 3000, now + 3600, link="https://meet.google.com/b", attendees=["me", None]))
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(self.calls("xdg-open"), [["https://meet.google.com/a"]])

    def test_no_meeting_opens_nothing(self):
        now = int(time.time())
        self.events(event("リンクなし", now, now + 600))
        res = self.run_meet()
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Meet", res.stdout.splitlines()[0])
        self.assertEqual(self.calls("xdg-open"), [])

    def test_calendar_failure_is_reported(self):
        (self.d / "gog-fail").touch()
        res = self.run_meet()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("gog", res.stdout.splitlines()[0])
        self.assertEqual(self.calls("xdg-open"), [])

    def test_missing_gog_is_reported(self):
        (self.bin / "gog").unlink()
        res = self.run_meet()
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("gog", res.stdout.splitlines()[0])

    def test_script_command_directives(self):
        # Vicinae は schemaVersion と title が無いと索引に載せない。silent は 1 行目を HUD に出す
        head = MEET.read_text().splitlines()[:10]
        self.assertIn("# @vicinae.schemaVersion 1", head)
        self.assertTrue(any(line.startswith("# @vicinae.title ") for line in head))
        self.assertIn("# @vicinae.mode silent", head)


if __name__ == "__main__":
    unittest.main()
