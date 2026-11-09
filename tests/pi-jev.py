"""pi-jev and where Pi is installed. Disposable HOME, fake Pi and op-agent, synthetic op:// references only.

The zsh snapshot tests run the real zsh on a fixture ~/.zshrc (they skip without zsh, but not in CI) and a
fake zsh for the failure paths.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_pi-jev"
IGNORE = ROOT / ".chezmoiignore"
ZSHRC = ROOT / "dot_zshrc"
CHEZMOI = shutil.which("chezmoi")
ZSH = shutil.which("zsh")
KEYS = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")

FAKE_PI = '''#!/usr/bin/env python3
import json, os, pathlib, sys
keys = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "PI_JEV_WRAPPED")
with (pathlib.Path(os.environ["HOME"])/"pi-runs.jsonl").open("a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "env": {k: os.environ[k] for k in keys if k in os.environ},
                        "snapshot": os.environ.get("PI_ZSH_SNAPSHOT"),
                        "sha256": os.environ.get("PI_ZSH_SNAPSHOT_SHA256")})+"\\n")
'''

# What the owner's ~/.zshrc might hold: plain aliases and functions to keep, and ones the snapshot must leave out.
FIXTURE_ZSHRC = r'''
echo NOISE-FROM-ZSHRC
print -u2 NOISE-ON-STDERR
setopt noclobber
alias gss='git status --short'
alias hello='print -r -- hello-alias'
alias ls='ls --color=always'
alias lsi='eza --icons'
alias lc='ls -l --color=always'
alias cat='bat --paging=never'
myfn () { print -r -- "fn:$1" }
sort () { print -r -- shadowed }
command_not_found_handler () { print -r -- handler }
TRAPEXIT () { : }
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
        self.addCleanup(self.unlock)  # runs before the cleanup above: pi-jev leaves the snapshot read-only
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
        # The gate resolves the TypeSafe key itself; OpenRouter is off without the flag.
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
        self.openrouter_env.mkdir()  # Readable, but sed fails on it.
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

    @unittest.skipUnless(ZSH or os.environ.get("CI"), "zsh が必要")
    def test_zsh_snapshot_keeps_plain_aliases_and_functions_and_leaves_out_noisy_or_shadowing_ones(self):
        (self.home / ".zshrc").write_text(FIXTURE_ZSHRC)
        run = self.run_wrapper()
        snap = self.snapshot()
        self.assertEqual(run["snapshot"], str(snap))
        text = snap.read_text()
        self.assertIn("alias gss='git status --short'", text)
        self.assertIn("myfn () {", text)
        for gone in ("alias ls=", "alias lsi=", "alias lc=", "alias cat=", "sort () {", "command_not_found_handler",
                     "TRAPEXIT", "NOISE"):
            self.assertNotIn(gone, text)
        self.assertEqual(snap.stat().st_mode & 0o777, 0o400)  # read-only until pi-jev rebuilds it
        self.assertEqual(snap.parent.stat().st_mode & 0o777, 0o500)
        self.assertEqual(sorted(p.name for p in snap.parent.iterdir()), ["zsh-snapshot.zsh"])
        out = subprocess.run([ZSH, "-fc", 'source "$1"; myfn x; eval hello', "zsh", str(snap)],
                             capture_output=True, text=True, timeout=10)
        self.assertEqual((out.stdout, out.stderr), ("fn:x\nhello-alias\n", ""))

    @unittest.skipUnless(ZSH or os.environ.get("CI"), "zsh が必要")
    def test_the_next_launch_rebuilds_the_read_only_snapshot(self):
        (self.home / ".zshrc").write_text(FIXTURE_ZSHRC)
        self.run_wrapper()
        (self.home / "pi-runs.jsonl").unlink()
        (self.home / ".zshrc").write_text(FIXTURE_ZSHRC + "alias later='true'\n")
        run = self.run_wrapper()
        self.assertIn("alias later=", self.snapshot().read_text())
        self.assertEqual(run["sha256"], self.sha256())
        self.assertEqual((self.snapshot().stat().st_mode & 0o777, self.snapshot().parent.stat().st_mode & 0o777),
                         (0o400, 0o500))

    @unittest.skipUnless(ZSH or os.environ.get("CI"), "zsh が必要")
    def test_xdg_cache_home_moves_the_snapshot(self):
        (self.home / ".zshrc").write_text(FIXTURE_ZSHRC)
        cache = self.home / "xdg-cache"
        run = self.run_wrapper(XDG_CACHE_HOME=str(cache))
        self.assertEqual(run["snapshot"], str(cache / "pi/zsh-snapshot.zsh"))
        self.assertIn("alias gss=", (cache / "pi/zsh-snapshot.zsh").read_text())
        self.assertFalse(self.snapshot().exists())

    def fake_zsh(self, body):
        zsh = self.bin / "zsh"
        zsh.write_text("#!/bin/sh\necho called >> \"$HOME/zsh-calls\"\n" + body)
        zsh.chmod(0o700)

    def old_snapshot(self):
        self.snapshot().parent.mkdir(parents=True)
        self.snapshot().write_text("alias old='true'\n")

    def test_nested_launch_reuses_the_snapshot_without_running_zsh(self):
        self.fake_zsh("exit 0\n")
        self.old_snapshot()
        run = self.run_wrapper(PI_JEV_WRAPPED="1", PI_ZSH_SNAPSHOT=str(self.snapshot()))
        self.assertEqual(run["snapshot"], str(self.snapshot()))
        self.assertEqual(self.snapshot().read_text(), "alias old='true'\n")
        self.assertFalse((self.home / "zsh-calls").exists())

    def test_failing_or_hanging_zsh_keeps_the_old_snapshot_and_still_starts_pi(self):
        for body in ("echo partial > \"$4\"; exit 1\n", "exec sleep 30\n"):
            with self.subTest(body=body):
                (self.home / "pi-runs.jsonl").unlink(missing_ok=True)
                self.unlock()
                shutil.rmtree(self.home / ".cache", ignore_errors=True)
                self.fake_zsh(body)
                self.old_snapshot()
                started = time.monotonic()
                run = self.run_wrapper()
                self.assertLess(time.monotonic() - started, 9)
                # The old file is left alone but not used: Pi runs without a snapshot.
                self.assertEqual((run["snapshot"], run["sha256"]), (None, None))
                self.assertEqual(self.snapshot().read_text(), "alias old='true'\n")
                self.assertEqual(sorted(p.name for p in self.snapshot().parent.iterdir()), ["zsh-snapshot.zsh"])

    def sha256(self):
        return hashlib.sha256(self.snapshot().read_bytes()).hexdigest()

    @unittest.skipUnless(ZSH or os.environ.get("CI"), "zsh が必要")
    def test_the_snapshot_hash_is_exported_for_the_prefix_and_the_gate(self):
        (self.home / ".zshrc").write_text(FIXTURE_ZSHRC)
        self.assertEqual(self.run_wrapper()["sha256"], self.sha256())

    def test_a_failed_rebuild_runs_without_a_snapshot_even_if_one_was_inherited(self):
        self.fake_zsh("exit 1\n")
        self.old_snapshot()
        run = self.run_wrapper(PI_ZSH_SNAPSHOT=str(self.snapshot()), PI_ZSH_SNAPSHOT_SHA256="SYNTHETIC-STALE")
        self.assertEqual((run["snapshot"], run["sha256"]), (None, None))

    def test_nested_launch_keeps_the_hash_it_inherited(self):
        # A snapshot changed during the session must not become trusted by starting Pi again from inside Pi.
        self.fake_zsh("exit 0\n")
        self.old_snapshot()
        run = self.run_wrapper(PI_JEV_WRAPPED="1", PI_ZSH_SNAPSHOT=str(self.snapshot()),
                               PI_ZSH_SNAPSHOT_SHA256="SYNTHETIC-PARENT-HASH")
        self.assertEqual((run["snapshot"], run["sha256"]), (str(self.snapshot()), "SYNTHETIC-PARENT-HASH"))
        (self.home / "pi-runs.jsonl").unlink()
        self.assertIsNone(self.run_wrapper(PI_JEV_WRAPPED="1")["sha256"])

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
