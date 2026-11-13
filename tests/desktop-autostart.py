"""am5-itx のログイン時の ChatGPT と Codex daemon の起動。tmux を通さず、ChatGPT は chatgpt-launch から起動する。描画だけで、アプリは起動しない。"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HYPR = ROOT / "home/private_dot_config/hypr/hyprland.lua.tmpl"
DESKTOP = ROOT / "home/dot_local/share/applications/chatgpt.desktop.tmpl"
IGNORE = ROOT / "home/.chezmoiignore"
CHEZMOI = shutil.which("chezmoi")

CHATGPT = 'hl.exec_cmd("~/.local/bin/chatgpt-launch")'
DAEMON = 'hl.exec_cmd("~/.local/bin/codex app-server daemon start")'


def render(path, hostname, os="linux"):
    """--source が無いと本体のソースを読んでしまう。"""
    data = {"chezmoi": {"hostname": hostname, "os": os, "homeDir": "/fixture"}}
    return subprocess.run(
        [CHEZMOI, "--source", str(ROOT), "execute-template",
         "--override-data", json.dumps(data)],
        input=path.read_text(), capture_output=True, text=True, check=True).stdout


@unittest.skipUnless(CHEZMOI, "chezmoi が必要")
class DesktopAutostart(unittest.TestCase):
    def test_am5_itx_starts_apps_directly(self):
        hypr = render(HYPR, "am5-itx")
        self.assertIn(CHATGPT, hypr)
        self.assertIn(DAEMON, hypr)
        self.assertNotIn("tmux", hypr)

    def test_other_hosts_do_not_start_apps(self):
        hypr = render(HYPR, "fp7-e14")
        self.assertNotIn(CHATGPT, hypr)
        self.assertNotIn(DAEMON, hypr)
        self.assertNotIn("chatgpt-launch", hypr)
        self.assertNotIn("tmux", hypr)

    def test_desktop_entry_uses_chatgpt_launch_only_on_am5_itx(self):
        for hostname in ("am5-itx", "fp7-e14"):
            with self.subTest(hostname=hostname):
                entry = render(DESKTOP, hostname)
                if hostname == "am5-itx":
                    self.assertIn('Exec="/fixture/.local/bin/chatgpt-launch" %U\n', entry)
                else:
                    self.assertIn("Exec=chatgpt --ozone-platform=wayland %U\n", entry)
                    self.assertNotIn("chatgpt-launch", entry)
                self.assertEqual(entry.count("Exec="), 1)
                self.assertIn("MimeType=x-scheme-handler/codex;", entry)
                self.assertNotIn("tmux", entry)

    def test_chatgpt_launch_is_installed_only_on_am5_itx(self):
        for hostname, os in (("am5-itx", "linux"), ("fp7-e14", "linux"), ("m1pro", "darwin")):
            with self.subTest(hostname=hostname):
                ignored = render(IGNORE, hostname, os).splitlines()
                self.assertEqual(".local/bin/chatgpt-launch" in ignored, hostname != "am5-itx")


if __name__ == "__main__":
    unittest.main()
