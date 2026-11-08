"""Disposable HOME and fake ChatGPT / systemctl / notify-send; never start installed apps."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_chatgpt-launch"

FAKE_GUI = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
h = pathlib.Path(os.environ['HOME']); marker = h/'gui-running'
mode = 'forward' if marker.exists() else 'first'
with (h/'events.jsonl').open('a') as f:
 f.write(json.dumps({'mode':mode,'args':sys.argv[1:],'pid':os.getpid()})+'\\n')
if mode == 'first':
 marker.touch()
 # Like Chromium, the first instance creates its app scope once it is running.
 if (h/'gui-creates-scope').exists(): (h/'scope-ready').touch()
 while (h/'hold-gui').exists(): time.sleep(.02)
'''

FAKE_SYSTEMCTL = '''#!/usr/bin/env python3
import json, os, pathlib, sys
h = pathlib.Path(os.environ['HOME']); args = sys.argv[1:]
with (h/'systemctl-calls.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
if args[1] == 'list-units' and (h/'scope-ready').exists():
 print(args[-1].replace('app-*-', 'app-org.example.Fixture-') + ' loaded active running fixture')
elif args[1] == 'set-property': sys.exit(1 if (h/'fail-set-property').exists() else 0)
elif args[1] == 'is-active': sys.exit(1 if (h/'scope-inactive').exists() else 0)
elif args[1] == 'show':
 current = h/'memory-current'
 print(current.read_text().strip() if current.exists() else '0')
'''

FAKE_NOTIFY = '''#!/usr/bin/env python3
import json, os, pathlib, sys
with (pathlib.Path(os.environ['HOME'])/'notify-calls.jsonl').open('a') as f: f.write(json.dumps(sys.argv[1:], ensure_ascii=False)+'\\n')
'''

GIB = 1024 ** 3


class ChatgptLaunch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)
        self.launcher = self.bin / "chatgpt-launch"
        shutil.copyfile(SCRIPT, self.launcher)
        self.launcher.chmod(0o700)
        # Registered after tmp.cleanup, so it runs first: no watcher writes into a removed HOME.
        self.addCleanup(lambda: self.wait_for(lambda: not self.watchers()))
        for name, content in {
            "chatgpt": FAKE_GUI,
            "systemctl": FAKE_SYSTEMCTL,
            "notify-send": FAKE_NOTIFY,
            "pgrep": '#!/bin/sh\ntest -f "$HOME/gui-running"\n',
        }.items():
            target = self.bin / name
            target.write_text(content)
            target.chmod(0o700)
        self.runtime = self.home / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.lock = self.runtime / "chatgpt-launch.lock"
        self.env = {
            "HOME": str(self.home), "USER": "fixture", "LOGNAME": "fixture",
            "PATH": str(self.bin) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
            "XDG_RUNTIME_DIR": str(self.runtime), "CHATGPT_WATCH_INTERVAL": "0.05",
        }

    def run_launcher(self, *args):
        return subprocess.run([str(self.launcher), *args], env=self.env,
                              capture_output=True, text=True, timeout=6)

    def events(self):
        return self.calls("events.jsonl")

    def calls(self, name):
        path = self.home / name
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def watchers(self):
        """Processes running this test's copy of the launcher in --watch-chatgpt mode."""
        found = []
        for proc in Path("/proc").iterdir():
            try:
                argv = (proc / "cmdline").read_bytes().split(b"\0")
            except OSError:
                continue
            if str(self.launcher).encode() in argv and b"--watch-chatgpt" in argv:
                found.append(int(proc.name))
        return found

    def holds_lock(self, pid):
        held = False
        for fd in Path("/proc/%d/fd" % pid).glob("*"):
            try:
                held = held or os.readlink(fd) == str(self.lock)
            except OSError:
                continue
        return held

    def parent(self, pid):
        status = Path("/proc/%d/status" % pid).read_text()
        return int(next(line.split()[1] for line in status.splitlines() if line.startswith("PPid:")))

    def wait_for(self, condition, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = condition()
            if value:
                return value
            time.sleep(.02)
        self.fail("condition not met in time")

    def start_watcher(self):
        target = subprocess.Popen(["sleep", "30"])
        self.addCleanup(target.wait)
        self.addCleanup(target.kill)
        watcher = subprocess.Popen([str(self.launcher), "--watch-chatgpt", str(target.pid)], env=self.env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(watcher.wait)
        self.addCleanup(watcher.kill)
        return target, watcher

    def test_first_launch_execs_chatgpt_and_watches_its_app_scope(self):
        (self.home / "hold-gui").touch()
        launch = subprocess.Popen([str(self.launcher), "codex://fixture"], env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(launch.wait)
        self.addCleanup(launch.kill)
        event = self.wait_for(lambda: self.events() and self.events()[0])
        self.assertEqual(event["mode"], "first")
        self.assertEqual(event["args"], ["--ozone-platform=wayland", "codex://fixture"])
        # exec keeps the pid, which is the one in the app-*-<pid>.scope name.
        self.assertEqual(event["pid"], launch.pid)
        pattern = "app-*-%d.scope" % launch.pid
        self.wait_for(lambda: any(c[-1] == pattern for c in self.calls("systemctl-calls.jsonl")))
        # The watcher is detached from ChatGPT and alone keeps the launch lock until the scope appears.
        [watcher] = self.watchers()
        self.assertNotEqual(self.parent(watcher), launch.pid)
        self.assertTrue(self.holds_lock(watcher))
        self.assertFalse(self.holds_lock(launch.pid))
        (self.home / "hold-gui").unlink()
        launch.communicate(timeout=3)
        self.assertEqual(launch.returncode, 0)
        self.wait_for(lambda: not self.watchers())
        self.assertEqual(self.calls("notify-calls.jsonl"), [])

    def test_uri_is_passed_without_interpolation(self):
        uri = 'codex://test?x=$(touch "' + str(self.home / "injected") + '")&y=two words;z=\nnext'
        result = self.run_launcher(uri, "https://example.invalid/a b")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events()[0]["args"], ["--ozone-platform=wayland", uri, "https://example.invalid/a b"])
        self.assertFalse((self.home / "injected").exists())

    def test_existing_gui_forwards_uri_without_watcher(self):
        (self.home / "gui-running").touch()
        result = self.run_launcher("codex://fixture")
        self.assertEqual(result.returncode, 0, result.stderr)
        [event] = self.events()
        self.assertEqual(event["mode"], "forward")
        self.assertEqual(event["args"], ["--ozone-platform=wayland", "codex://fixture"])
        time.sleep(.3)
        self.assertEqual(self.watchers(), [])
        self.assertFalse((self.home / "systemctl-calls.jsonl").exists())

    def test_concurrent_first_launches_start_one_instance(self):
        (self.home / "hold-gui").touch()
        (self.home / "gui-creates-scope").touch()
        launches = [subprocess.Popen([str(self.launcher), "codex://%d" % n], env=self.env,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE) for n in range(2)]
        for launch in launches:
            self.addCleanup(launch.wait)
            self.addCleanup(launch.kill)
        self.wait_for(lambda: len(self.events()) == 2, timeout=5)
        self.assertEqual(sorted(e["mode"] for e in self.events()), ["first", "forward"])
        (self.home / "hold-gui").unlink()
        for launch in launches:
            launch.communicate(timeout=3)
            self.assertEqual(launch.returncode, 0)
        self.wait_for(lambda: not self.watchers())
        self.assertEqual(sum(c[1] == "set-property" for c in self.calls("systemctl-calls.jsonl")), 1)

    def test_launches_without_a_runtime_dir(self):
        env = dict(self.env)
        env.pop("XDG_RUNTIME_DIR")
        result = subprocess.run([str(self.launcher)], env=env, capture_output=True, text=True, timeout=6)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events()[0]["mode"], "first")
        self.assertFalse(self.lock.exists())

    def test_missing_chatgpt_fails_before_starting_a_watcher(self):
        (self.bin / "chatgpt").unlink()
        # Without /usr/bin in PATH, an installed ChatGPT cannot be found and started instead.
        result = subprocess.run([shutil.which("bash"), str(self.launcher)], env=dict(self.env, PATH=str(self.bin)),
                                capture_output=True, text=True, timeout=6)
        self.assertEqual(result.returncode, 127)
        self.assertIn("chatgpt is not installed", result.stderr)
        self.assertEqual(self.watchers(), [])

    def test_invalid_watch_arguments_fail_before_launch(self):
        self.assertEqual(self.run_launcher("--watch-chatgpt").returncode, 2)
        self.assertEqual(self.run_launcher("--watch-chatgpt", "not-a-pid").returncode, 2)
        self.assertEqual(self.run_launcher("--watch-chatgpt", "1", "2").returncode, 2)
        self.assertEqual(self.events(), [])
        self.assertFalse((self.home / "systemctl-calls.jsonl").exists())

    def test_watcher_limits_the_app_scope_and_warns_once_per_threshold(self):
        (self.home / "scope-ready").touch()
        target, watcher = self.start_watcher()
        scope = "app-org.example.Fixture-%d.scope" % target.pid
        self.wait_for(lambda: any(c[1] == "set-property" for c in self.calls("systemctl-calls.jsonl")))
        [call] = [c for c in self.calls("systemctl-calls.jsonl") if c[1] == "set-property"]
        self.assertEqual(call, ["--user", "set-property", "--runtime", scope,
                                "MemoryHigh=16G", "MemoryMax=24G", "MemorySwapMax=8G"])
        time.sleep(.3)
        self.assertEqual(self.calls("notify-calls.jsonl"), [])
        (self.home / "memory-current").write_text(str(15 * GIB))
        self.wait_for(lambda: len(self.calls("notify-calls.jsonl")) == 1)
        time.sleep(.3)
        [near_high] = self.calls("notify-calls.jsonl")
        self.assertEqual(near_high[:4], ["-u", "normal", "-a", "ChatGPT"])
        self.assertIn("上限に近づいています", near_high[4])
        self.assertIn("15.0 / 16 GiB", near_high[5])
        (self.home / "memory-current").write_text(str(22 * GIB))
        self.wait_for(lambda: len(self.calls("notify-calls.jsonl")) == 2)
        time.sleep(.3)
        near_max = self.calls("notify-calls.jsonl")[1]
        self.assertEqual(len(self.calls("notify-calls.jsonl")), 2)
        self.assertEqual(near_max[:4], ["-u", "critical", "-a", "ChatGPT"])
        self.assertIn("強制終了", near_max[4])
        self.assertIn("22.0 / 24 GiB", near_max[5])
        target.kill()
        target.wait()
        self.assertEqual(watcher.wait(timeout=3), 0)

    def test_watcher_stops_when_its_scope_is_no_longer_active(self):
        (self.home / "scope-ready").touch()
        target, watcher = self.start_watcher()
        self.wait_for(lambda: any(c[1] == "show" for c in self.calls("systemctl-calls.jsonl")))
        (self.home / "scope-inactive").touch()
        self.assertEqual(watcher.wait(timeout=3), 0)
        self.assertIsNone(target.poll())

    def test_watcher_reports_when_limits_cannot_be_applied(self):
        (self.home / "scope-ready").touch()
        (self.home / "fail-set-property").touch()
        _, watcher = self.start_watcher()
        self.assertEqual(watcher.wait(timeout=3), 0)
        [note] = self.calls("notify-calls.jsonl")
        self.assertEqual(note[:2], ["-u", "critical"])
        self.assertIn("設定できませんでした", note[4])
        self.assertFalse(any(c[1] == "show" for c in self.calls("systemctl-calls.jsonl")))

    def test_watcher_stays_quiet_when_chatgpt_exits_before_its_scope_appears(self):
        target, watcher = self.start_watcher()
        self.wait_for(lambda: self.calls("systemctl-calls.jsonl"))
        target.kill()
        target.wait()
        self.assertEqual(watcher.wait(timeout=3), 0)
        self.assertEqual(self.calls("notify-calls.jsonl"), [])
        self.assertFalse(any(c[1] == "set-property" for c in self.calls("systemctl-calls.jsonl")))


if __name__ == "__main__":
    unittest.main()
