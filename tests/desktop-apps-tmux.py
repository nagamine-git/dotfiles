"""Disposable HOME, fake applications and credentials; never start installed apps."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_desktop-apps-tmux"
CONFIG = ROOT / "private_dot_config/desktop-apps/tmux.conf"

FAKE_TMUX = '''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
h = pathlib.Path(os.environ['HOME']); args = sys.argv[1:]
with (h/'tmux-calls.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
if (h/'fail-tmux').exists(): sys.exit(42)
verb = args[4]
state = h/'fake-session'
if verb == 'has-session': sys.exit(0 if state.exists() and args[-1] == '=chatgpt' else 1)
if verb != 'new-session': sys.exit(3)
role = args[args.index('-s')+1]
if role == 'chatgpt': state.touch()
start = args.index('--pane') - 1
sys.exit(subprocess.run(args[start:], env=os.environ).returncode)
'''

FAKE_GUI = '''#!/usr/bin/env python3
import json, os, pathlib, sys, time
h = pathlib.Path(os.environ['HOME']); marker = h/'gui-running'
mode = 'forward' if marker.exists() else 'first'
with (h/'events.jsonl').open('a') as f:
 f.write(json.dumps({'role':'chatgpt','mode':mode,'args':sys.argv[1:],'keys':list(os.environ),'pid':os.getpid()})+'\\n')
if mode == 'first':
 marker.touch()
 while (h/'hold-gui').exists(): time.sleep(.02)
'''

FAKE_CODEX = '''#!/usr/bin/env python3
import json, os, pathlib, sys
h = pathlib.Path(os.environ['HOME']); marker = h/'daemon-running'
mode = 'existing' if marker.exists() else 'first'
marker.touch()
with (h/'events.jsonl').open('a') as f:
 f.write(json.dumps({'role':'codex','mode':mode,'args':sys.argv[1:],'keys':list(os.environ)})+'\\n')
'''


class DesktopAppsTmux(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)
        self.wrapper = self.bin / "desktop-apps-tmux"
        shutil.copyfile(SCRIPT, self.wrapper)
        self.wrapper.chmod(0o700)
        conf = self.home / ".config/desktop-apps/tmux.conf"
        conf.parent.mkdir(parents=True)
        shutil.copyfile(CONFIG, conf)
        self.runtime = self.home / "runtime"
        self.runtime.mkdir(mode=0o700)
        for name, content in {
            "tmux": FAKE_TMUX,
            "chatgpt": FAKE_GUI,
            "codex": FAKE_CODEX,
            "pgrep": '#!/bin/sh\ntest -f "$HOME/gui-running"\n',
            "op": '#!/bin/sh\ntouch "$HOME/unexpected-op"\nexit 99\n',
            "ssh": '#!/bin/sh\ntouch "$HOME/unexpected-ssh"\nexit 99\n',
        }.items():
            target = self.bin / name
            target.write_text(content)
            target.chmod(0o700)
        # Never inherit the real test runner's authentication environment.
        self.env = {
            "HOME": str(self.home), "USER": "fixture", "LOGNAME": "fixture",
            "PATH": str(self.bin) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
            "XDG_RUNTIME_DIR": str(self.runtime), "WAYLAND_DISPLAY": "fixture-wayland",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/fixture-dbus",
            "SSH_AUTH_SOCK": "/fixture-agent.sock",
            "OP_SESSION_fixture": "synthetic-not-a-credential",
            "OP_SERVICE_ACCOUNT_TOKEN": "synthetic-not-a-credential",
            "OPENAI_API_KEY": "synthetic-not-a-credential",
        }

    def run_wrapper(self, *args, env=None):
        return subprocess.run([str(self.wrapper), *args], env=env or self.env,
                              capture_output=True, text=True, timeout=6)

    def events(self):
        path = self.home / "events.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def assert_no_auth_calls(self):
        self.assertFalse((self.home / "unexpected-op").exists())
        self.assertFalse((self.home / "unexpected-ssh").exists())

    def test_autostart_preserves_existing_daemon_command_and_filters_credentials(self):
        result = self.run_wrapper("autostart")
        self.assertEqual(result.returncode, 0, result.stderr)
        gui, daemon = self.events()
        self.assertEqual(gui["args"], ["--ozone-platform=wayland"])
        self.assertEqual(daemon["args"], ["app-server", "daemon", "start"])
        for event in [gui, daemon]:
            for key in ["WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "SSH_AUTH_SOCK"]:
                self.assertIn(key, event["keys"])
            self.assertFalse(any(k.startswith("OP_") for k in event["keys"]))
            self.assertNotIn("OPENAI_API_KEY", event["keys"])
        self.assert_no_auth_calls()

    def test_duplicate_autostart_does_not_duplicate_gui_or_daemon(self):
        self.assertEqual(self.run_wrapper("autostart").returncode, 0)
        self.assertEqual(self.run_wrapper("autostart").returncode, 0)
        self.assertEqual(sum(e["role"] == "chatgpt" for e in self.events()), 1)
        self.assertEqual(sum(e["role"] == "codex" and e["mode"] == "first" for e in self.events()), 1)
        self.assert_no_auth_calls()

    def test_concurrent_first_launch_is_serialized(self):
        procs = [subprocess.Popen([str(self.wrapper), "chatgpt"], env=self.env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for proc in procs:
            proc.communicate(timeout=6)
            self.assertEqual(proc.returncode, 0)
        self.assertEqual(sum(e["mode"] == "first" for e in self.events()), 1)

    def test_first_uri_is_not_interpolated(self):
        uri = 'codex://test?x=$(touch "' + str(self.home / "injected") + '")&y=two words;z=\nnext'
        result = self.run_wrapper("chatgpt", uri, "https://example.invalid/a b")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events()[0]["args"], ["--ozone-platform=wayland", uri, "https://example.invalid/a b"])
        self.assertFalse((self.home / "injected").exists())

    def test_existing_gui_forwards_uri_without_new_session(self):
        (self.home / "gui-running").touch()
        result = self.run_wrapper("chatgpt", "codex://fixture")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events()[0]["mode"], "forward")
        self.assertEqual(self.events()[0]["args"], ["--ozone-platform=wayland", "codex://fixture"])
        self.assertFalse((self.home / "tmux-calls.jsonl").exists())
        self.assert_no_auth_calls()

    def test_pending_gui_does_not_silently_drop_uri(self):
        (self.home / "fake-session").touch()
        result = self.run_wrapper("chatgpt", "codex://fixture")
        self.assertEqual(result.returncode, 1)
        self.assertIn("retry the URI", result.stderr)
        self.assertEqual(self.events(), [])

    def test_invalid_action_and_missing_runtime_fail_before_launch(self):
        self.assertEqual(self.run_wrapper("codex-daemon", "restart").returncode, 2)
        self.assertEqual(self.run_wrapper("--pane", "unknown").returncode, 2)
        env = dict(self.env)
        env.pop("XDG_RUNTIME_DIR")
        self.assertEqual(self.run_wrapper("autostart", env=env).returncode, 1)
        self.assertEqual(self.events(), [])

    def test_tmux_failure_is_reported(self):
        (self.home / "fail-tmux").touch()
        self.assertEqual(self.run_wrapper("autostart").returncode, 42)
        self.assertEqual(self.events(), [])

    def test_host_scoping_and_desktop_uri_entry_with_real_template_renderer(self):
        chezmoi = shutil.which("chezmoi", path="/usr/bin:/bin")
        self.assertIsNotNone(chezmoi)
        desktop = (ROOT / "dot_local/share/applications/chatgpt.desktop.tmpl").read_text()
        hypr = (ROOT / "private_dot_config/hypr/hyprland.conf.tmpl").read_text()
        start = hypr.index('{{ if eq .chezmoi.hostname "am5-itx" -}}')
        finish = hypr.index('{{ end -}}', start) + len('{{ end -}}')
        block = hypr[start:finish]
        for hostname in ["am5-itx", "fp7-e14", "m1pro-mbp14"]:
            context = '{{ with dict "chezmoi" (dict "hostname" "' + hostname + '" "homeDir" "/fixture") }}'
            result = subprocess.run([chezmoi, "execute-template"], input=context + desktop + "{{ end }}",
                                    env=self.env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            if hostname == "am5-itx":
                self.assertIn('Exec="/fixture/.local/bin/desktop-apps-tmux" chatgpt %U', result.stdout)
            else:
                self.assertIn("Exec=chatgpt --ozone-platform=wayland %U", result.stdout)
                self.assertNotIn("desktop-apps-tmux", result.stdout)
            result = subprocess.run([chezmoi, "execute-template"], input=context + block + "{{ end }}",
                                    env=self.env, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual("desktop-apps-tmux autostart" in result.stdout, hostname == "am5-itx")

    def test_real_tmux_disposable_server_preserves_arguments_and_exits_with_dummy(self):
        real_tmux = shutil.which("tmux", path="/usr/bin:/bin")
        if not real_tmux:
            self.skipTest("tmux is not installed")
        (self.bin / "tmux").unlink()
        hold = self.home / "hold-gui"
        hold.touch()
        socket = self.runtime / "desktop-apps-tmux/tmux.sock"
        self.addCleanup(lambda: subprocess.run([real_tmux, "-S", str(socket), "kill-server"],
                                               capture_output=True, timeout=3))
        self.addCleanup(lambda: hold.unlink(missing_ok=True))
        uri = 'codex://fixture?text="a b";$(false)'
        result = self.run_wrapper("chatgpt", uri)
        self.assertEqual(result.returncode, 0, result.stderr)
        deadline = time.monotonic() + 3
        while not self.events() and time.monotonic() < deadline:
            time.sleep(.02)
        first = self.events()[0]
        self.assertEqual(first["args"], ["--ozone-platform=wayland", uri])
        self.assert_no_auth_calls()
        info = subprocess.run([real_tmux, "-S", str(socket), "list-panes", "-t", "=chatgpt", "-F", "#{pane_pid}"],
                              capture_output=True, text=True, timeout=3)
        self.assertEqual(info.returncode, 0, info.stderr)
        self.assertEqual(int(info.stdout), first["pid"])
        self.assertEqual(self.run_wrapper("autostart").returncode, 0)
        self.assertEqual(sum(e["role"] == "chatgpt" for e in self.events()), 1)
        hold.unlink()
        while time.monotonic() < deadline:
            check = subprocess.run([real_tmux, "-S", str(socket), "has-session", "-t", "=chatgpt"], capture_output=True)
            if check.returncode:
                break
            time.sleep(.02)
        self.assertNotEqual(check.returncode, 0)


if __name__ == "__main__":
    unittest.main()
