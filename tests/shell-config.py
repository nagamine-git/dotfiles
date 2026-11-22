"""シェルの初期化順・chezmoi 標準機能への置き換え・パッケージ取得の待機期間。外部へは接続しない。"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "home"
CHEZMOI = shutil.which("chezmoi")
HOSTS = (("am5-itx", "linux"), ("fp7-e14", "linux"), ("m1pro-mbp14", "darwin"))


def render(text, hostname, os_name):
    data = {"chezmoi": {"hostname": hostname, "os": os_name, "homeDir": "/fixture"}}
    return subprocess.run(
        [CHEZMOI, "--source", str(ROOT), "execute-template", "--override-data", json.dumps(data)],
        input=text, capture_output=True, text=True, check=True).stdout


class ShellInit(unittest.TestCase):
    def test_compinit_runs_after_completions_and_before_compdef_users(self):
        # zsh-completions は fpath に入るだけなので、その後で compinit しないと補完が登録されない。
        # omz-git は compdef を呼ぶので、compinit より後でなければならない。
        plugins = list(tomllib.loads((HOME / "private_dot_config/sheldon/plugins.toml").read_text())["plugins"])
        self.assertLess(plugins.index("zsh-completions"), plugins.index("compinit"))
        self.assertLess(plugins.index("compinit"), plugins.index("omz-git"))
        zshrc = (HOME / "dot_zshrc").read_text()
        self.assertIsNone(re.search(r"^\s*compinit\b", zshrc, re.M), "compinit を .zshrc で先に実行しない")
        self.assertLess(zshrc.index("sheldon source"), zshrc.index("atuin init"))

    def test_retired_launchers_are_gone(self):
        zshrc = (HOME / "dot_zshrc").read_text()
        for stale in ("ccr-start", "ccnim", "/usr/bin/cursor", "_cc_is_pro_available"):
            self.assertNotIn(stale, zshrc)
        removed = (HOME / ".chezmoiremove").read_text()
        for target in (".local/bin/ccr-start.sh", ".local/bin/mic-snr.sh"):
            self.assertIn(target, removed)
        self.assertTrue((HOME / "dot_local/bin/executable_blender-guard").is_file())
        self.assertIn(".config/systemd/user/aa-coding-snapshot.timer", removed)


@unittest.skipUnless(CHEZMOI, "chezmoi が必要")
class ChezmoiNative(unittest.TestCase):
    def test_home_agents_is_a_plain_symlink_entry(self):
        for hostname, os_name in HOSTS:
            with self.subTest(hostname=hostname):
                target = render((HOME / "symlink_AGENTS.md.tmpl").read_text(), hostname, os_name)
                self.assertEqual(target, "/fixture/.config/agents/home-AGENTS.md\n")
        self.assertTrue((HOME / "private_dot_config/agents/home-AGENTS.md").is_file())
        self.assertFalse(list((HOME / ".chezmoiscripts").glob("*home-agents-link*")))

    def test_externals_need_no_network_outside_am5(self):
        # chezmoi の external は登録後の最初の apply で git pull する (2026-11 に TPM で確認)。
        # fp7-e14 は非対話の SSH から GitHub へ届かないので、am5-itx 以外には external を置かない。
        # TPM は run_once のスクリプトで入れる (無いときだけ clone し、あとは触らない)。
        for hostname, os_name in HOSTS:
            with self.subTest(hostname=hostname):
                externals = tomllib.loads(render((HOME / ".chezmoiexternal.toml.tmpl").read_text(), hostname, os_name))
                self.assertEqual(sorted(externals), [".local/share/agent-tools"] if hostname == "am5-itx" else [])
        self.assertTrue((HOME / ".chezmoiscripts/run_once_install-tpm.sh").is_file())


class ReleaseCooldown(unittest.TestCase):
    def test_npm_and_bun_wait_the_same_three_days(self):
        npm = dict(line.split("=", 1) for line in (HOME / "dot_npmrc").read_text().splitlines()
                   if line and not line.startswith("#"))
        self.assertEqual(npm, {"min-release-age": "3"})  # 認証情報などを置かない
        bun = tomllib.loads((HOME / "dot_bunfig.toml").read_text())
        self.assertEqual(bun, {"install": {"minimumReleaseAge": 3 * 24 * 60 * 60}})


if __name__ == "__main__":
    unittest.main()
