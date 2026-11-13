"""pi-jev: disposable HOME, fake Pi/op-agent, synthetic references, and no real keys or models.

Pi now runs plain bash. Legacy zsh snapshots must not be created, inherited, or modified.
"""
import json
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "home/dot_local/bin/executable_pi-jev"
IGNORE = ROOT / "home/.chezmoiignore"
ZSHRC = ROOT / "home/dot_zshrc"
CHEZMOI = shutil.which("chezmoi")
KEYS = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")

FAKE_PI = '''#!/usr/bin/env python3
import json, os, pathlib, sys
try:
    tty = os.open("/dev/tty", os.O_RDWR)
    foreground = os.tcgetpgrp(tty) == os.getpgrp()
    os.close(tty)
except OSError:
    foreground = None
keys = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "PI_JEV_WRAPPED")
with (pathlib.Path(os.environ["HOME"])/"pi-runs.jsonl").open("a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "env": {k: os.environ[k] for k in keys if k in os.environ},
                        "snapshot": os.environ.get("PI_ZSH_SNAPSHOT"),
                        "sha256": os.environ.get("PI_ZSH_SNAPSHOT_SHA256"), "foreground": foreground})+"\\n")
'''

FAKE_OP_AGENT = '''#!/usr/bin/env python3
import json, os, pathlib, sys
with (pathlib.Path(os.environ["HOME"])/"op-agent-calls.jsonl").open("a") as f: f.write(json.dumps(sys.argv[1:])+"\\n")
print("SYNTHETIC-VALUE-FOR " + sys.argv[-1])
'''


class PiJev(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.addCleanup(self.unlock)
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)
        self.wrapper = self.bin / "pi-jev"
        shutil.copyfile(SCRIPT, self.wrapper)
        self.wrapper.chmod(0o700)
        for path, content in {self.home / ".pi/agent/bin/pi": FAKE_PI, self.bin / "op-agent": FAKE_OP_AGENT}.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            path.chmod(0o700)
        self.token = self.home / ".config/op/agents-sa-token"
        self.token.parent.mkdir(parents=True)
        self.token.write_text("synthetic-not-a-token")
        agents = self.home / ".config/agents"
        agents.mkdir(parents=True)
        (agents / "model-typesafe.env").write_text("# synthetic\nTYPESAFE_API_KEY=op://Agents/synthetic-typesafe/password\n")
        self.openrouter_env = agents / "model-openrouter.env"
        self.openrouter_env.write_text(
            "# synthetic\nOPENROUTER_API_KEY=\"op://Agents/synthetic-openrouter/password\"\n"
            "ARTIFICIAL_ANALYSIS_API_KEY=op://Agents/synthetic-aa/password\n")
        self.env = {"HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin", "LANG": "C.UTF-8"}

    def run_wrapper(self, *args, **extra):
        result = subprocess.run([str(self.wrapper), *args], env=dict(self.env, **extra), cwd=str(self.home),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("SYNTHETIC-VALUE", result.stdout + result.stderr)
        [run] = self.calls("pi-runs.jsonl")
        return run

    def calls(self, name):
        path = self.home / name
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def test_default_puts_no_key_in_pis_environment(self):
        inherited = {key: "SYNTHETIC-INHERITED" for key in KEYS}
        run = self.run_wrapper("--print", "a b", **inherited)
        self.assertEqual(run["args"], ["--print", "a b"])
        self.assertEqual(run["env"], {"PI_JEV_WRAPPED": "1"})
        self.assertEqual(self.calls("op-agent-calls.jsonl"), [])

    def test_openrouter_flag_resolves_only_the_openrouter_key(self):
        run = self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1")
        self.assertEqual(self.calls("op-agent-calls.jsonl"), [["read", "op://Agents/synthetic-openrouter/password"]])
        self.assertEqual(run["env"], {"OPENROUTER_API_KEY": "SYNTHETIC-VALUE-FOR op://Agents/synthetic-openrouter/password",
                                      "PI_JEV_WRAPPED": "1"})

    def test_openrouter_flag_drops_the_other_inherited_keys(self):
        inherited = {key: "SYNTHETIC-INHERITED" for key in KEYS if key != "OPENROUTER_API_KEY"}
        run = self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1", **inherited)
        self.assertEqual(sorted(run["env"]), ["OPENROUTER_API_KEY", "PI_JEV_WRAPPED"])

    def test_openrouter_flag_without_token_starts_pi_without_keys(self):
        self.token.unlink()
        self.assertEqual(self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1")["env"], {"PI_JEV_WRAPPED": "1"})
        self.assertEqual(self.calls("op-agent-calls.jsonl"), [])

    def test_openrouter_flag_without_op_agent_starts_pi_without_keys(self):
        (self.bin / "op-agent").unlink()
        self.assertEqual(self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1")["env"], {"PI_JEV_WRAPPED": "1"})

    def test_openrouter_reference_may_be_quoted_with_spaces_or_bare(self):
        for line, ref in (('OPENROUTER_API_KEY="op://Agents/synthetic vault/item one/password"  \n',
                           "op://Agents/synthetic vault/item one/password"),
                          ("OPENROUTER_API_KEY=op://Agents/synthetic-bare/password\t\n", "op://Agents/synthetic-bare/password")):
            with self.subTest(ref=ref):
                for name in ("pi-runs.jsonl", "op-agent-calls.jsonl"):
                    (self.home / name).unlink(missing_ok=True)
                self.openrouter_env.write_text("# synthetic\n" + line)
                run = self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1")
                self.assertEqual(self.calls("op-agent-calls.jsonl"), [["read", ref]])
                self.assertEqual(run["env"]["OPENROUTER_API_KEY"], "SYNTHETIC-VALUE-FOR " + ref)

    def test_unreadable_or_malformed_reference_still_starts_pi(self):
        self.openrouter_env.write_text('OPENROUTER_API_KEY="op://Agents/synthetic-unclosed/password\n')
        self.assertEqual(self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1")["env"], {"PI_JEV_WRAPPED": "1"})
        (self.home / "pi-runs.jsonl").unlink()
        self.openrouter_env.unlink()
        self.openrouter_env.mkdir()
        self.assertEqual(self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1")["env"], {"PI_JEV_WRAPPED": "1"})
        self.assertEqual(self.calls("op-agent-calls.jsonl"), [])

    def test_nested_launch_keeps_an_allowed_key_and_drops_it_otherwise(self):
        nested = {"PI_JEV_WRAPPED": "1", "OPENROUTER_API_KEY": "SYNTHETIC-INHERITED"}
        self.assertEqual(self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1", **nested)["env"]["OPENROUTER_API_KEY"],
                         "SYNTHETIC-INHERITED")
        (self.home / "pi-runs.jsonl").unlink()
        self.assertNotIn("OPENROUTER_API_KEY", self.run_wrapper(**nested)["env"])
        self.assertEqual(self.calls("op-agent-calls.jsonl"), [])

    def snapshot(self):
        return self.home / ".cache/pi/zsh-snapshot.zsh"

    def unlock(self):
        if self.snapshot().parent.is_dir():
            self.snapshot().parent.chmod(0o700)

    def fake_zsh(self):
        zsh = self.bin / "zsh"
        zsh.write_text('#!/bin/sh\necho called >> "$HOME/zsh-calls"\nexit 1\n')
        zsh.chmod(0o700)

    def test_launch_does_not_run_zsh_or_load_the_owners_profile(self):
        self.fake_zsh()
        (self.home / ".zshrc").write_text('echo loaded > "$HOME/profile-loaded"\n')
        run = self.run_wrapper()
        self.assertEqual((run["snapshot"], run["sha256"]), (None, None))
        self.assertFalse((self.home / "zsh-calls").exists())
        self.assertFalse((self.home / "profile-loaded").exists())
        self.assertFalse(self.snapshot().exists())

    def test_stale_snapshot_is_not_modified_or_inherited_including_nested_launches(self):
        self.fake_zsh()
        snap = self.snapshot()
        snap.parent.mkdir(parents=True)
        snap.write_text("alias old='false'\n")
        snap.chmod(0o400)
        snap.parent.chmod(0o500)
        for nested in (False, True):
            with self.subTest(nested=nested):
                (self.home / "pi-runs.jsonl").unlink(missing_ok=True)
                run = self.run_wrapper(PI_JEV_WRAPPED="1" if nested else "",
                                       PI_ZSH_SNAPSHOT=str(snap), PI_ZSH_SNAPSHOT_SHA256="SYNTHETIC-STALE")
                self.assertEqual((run["snapshot"], run["sha256"]), (None, None))
                self.assertEqual(snap.read_text(), "alias old='false'\n")
                self.assertEqual((snap.stat().st_mode & 0o777, snap.parent.stat().st_mode & 0o777), (0o400, 0o500))
                self.assertFalse((self.home / "zsh-calls").exists())

    def test_xdg_cache_home_does_not_create_a_snapshot(self):
        cache = self.home / "xdg-cache"
        run = self.run_wrapper(XDG_CACHE_HOME=str(cache))
        self.assertEqual((run["snapshot"], run["sha256"]), (None, None))
        self.assertFalse(cache.exists())

    def test_launch_leaves_the_terminal_to_pi(self):
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.chdir(self.home)
                os.execve(str(self.wrapper), [str(self.wrapper)], self.env)
            finally:
                os._exit(127)
        deadline, status = time.monotonic() + 10, None
        while status is None and time.monotonic() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                try:
                    os.read(fd, 4096)
                except OSError:
                    pass
            done, code = os.waitpid(pid, os.WNOHANG)
            if done:
                status = code
        if status is None:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
        os.close(fd)
        self.assertEqual(status, 0)
        [run] = self.calls("pi-runs.jsonl")
        self.assertEqual((run["snapshot"], run["sha256"]), (None, None))
        self.assertIs(run["foreground"], True)

    def test_without_zsh_pi_starts_with_no_snapshot(self):
        tools = self.home / "tools"
        tools.mkdir()
        for name in ("bash", "python3"):
            (tools / name).symlink_to(shutil.which(name))
        run = self.run_wrapper(PATH="%s:%s" % (self.bin, tools))
        self.assertEqual((run["snapshot"], run["sha256"]), (None, None))
        self.assertFalse(self.snapshot().exists())

    def test_zsh_alias_only_when_pi_jev_is_installed(self):
        zshrc = ZSHRC.read_text()
        self.assertNotIn("\nalias pi='pi-jev'\n", zshrc)
        self.assertIn("[[ -x \"$HOME/.local/bin/pi-jev\" ]] && alias pi='pi-jev'\n", zshrc)


def render(path, hostname, os_name):
    data = {"chezmoi": {"hostname": hostname, "os": os_name, "homeDir": "/fixture"}}
    return subprocess.run([CHEZMOI, "--source", str(ROOT), "execute-template", "--override-data", json.dumps(data)],
                          input=path.read_text(), capture_output=True, text=True, check=True).stdout


@unittest.skipUnless(CHEZMOI, "chezmoi が必要")
class PiHosts(unittest.TestCase):
    def test_pi_files_are_installed_only_on_am5_itx(self):
        targets = [".local/bin/pi-jev", ".pi", ".pi/**", ".config/agents/model-openrouter.env"]
        for hostname, os_name in (("am5-itx", "linux"), ("fp7-e14", "linux"), ("m1pro", "darwin")):
            with self.subTest(hostname=hostname):
                ignored = render(IGNORE, hostname, os_name).splitlines()
                for target in targets:
                    self.assertEqual(target in ignored, hostname != "am5-itx", target)


if __name__ == "__main__":
    unittest.main()
