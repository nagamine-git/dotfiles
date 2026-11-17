"""Linux導入スクリプトを3ホスト分描画し、構文とOS・機器分岐だけを検査する。

導入スクリプト自体は実行しない。パッケージ・サービス・ネットワーク設定を変えない。
"""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "home/.chezmoiscripts/linux"
CHEZMOI = shutil.which("chezmoi")


@unittest.skipUnless(CHEZMOI, "chezmoi が必要")
class LinuxBootstrap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rendered = {}
        for hostname, os_name in (("am5-itx", "linux"), ("fp7-e14", "linux"), ("m1pro-mbp14", "darwin")):
            cls.rendered[hostname] = {}
            for source in sorted(SCRIPTS.glob("*.sh.tmpl")):
                cls.rendered[hostname][source.name] = subprocess.run(
                    [CHEZMOI, "--source", str(ROOT), "execute-template", "--override-data",
                     json.dumps({"chezmoi": {"hostname": hostname, "os": os_name}})],
                    input=source.read_text(), capture_output=True, text=True, check=True,
                ).stdout

    def test_linux_sources_render_as_valid_bash_without_running(self):
        for host in ("am5-itx", "fp7-e14"):
            self.assertTrue(self.rendered[host])
            for name, script in self.rendered[host].items():
                with self.subTest(host=host, script=name):
                    self.assertTrue(script.lstrip().startswith("#!/usr/bin/env bash"))
                    subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True, check=True)

    def test_linux_sources_are_empty_on_macos(self):
        self.assertTrue(self.rendered["m1pro-mbp14"])
        for name, script in self.rendered["m1pro-mbp14"].items():
            with self.subTest(script=name):
                self.assertEqual(script.strip(), "")

    def test_desktop_tuning_stays_off_the_laptop(self):
        name = "run_onchange_after_20-system.sh.tmpl"
        for desktop_only in ("etc/systemd/zram-generator.conf", "etc/scx_loader/config.toml", "etc/tmpfiles.d/cpu-epp.conf"):
            with self.subTest(config=desktop_only):
                self.assertIn(desktop_only, self.rendered["am5-itx"][name])
                self.assertNotIn(desktop_only, self.rendered["fp7-e14"][name])


if __name__ == "__main__":
    unittest.main()
