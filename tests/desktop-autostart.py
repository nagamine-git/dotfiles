"""am5-itx のログイン時の ChatGPT と Codex daemon の起動。tmux を通さず直接起動する。描画だけで、アプリは起動しない。"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
HYPR = ROOT / "private_dot_config/hypr/hyprland.lua.tmpl"
DESKTOP = ROOT / "dot_local/share/applications/chatgpt.desktop.tmpl"
CHEZMOI = shutil.which("chezmoi")

CHATGPT = 'hl.exec_cmd("chatgpt --ozone-platform=wayland")'
DAEMON = 'hl.exec_cmd("~/.local/bin/codex app-server daemon start")'


def render(path, hostname):
    """--source が無いと本体のソースを読んでしまう。"""
    return subprocess.run(
        [CHEZMOI, "--source", str(ROOT), "execute-template",
         "--override-data", json.dumps({"chezmoi": {"hostname": hostname}})],
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
        self.assertNotIn("tmux", hypr)

    def test_desktop_entry_is_same_on_all_hosts(self):
        for hostname in ("am5-itx", "fp7-e14"):
            with self.subTest(hostname=hostname):
                entry = render(DESKTOP, hostname)
                self.assertIn("Exec=chatgpt --ozone-platform=wayland %U\n", entry)
                self.assertNotIn("tmux", entry)


if __name__ == "__main__":
    unittest.main()
