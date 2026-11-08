"""pi-jev and where Pi is installed. Disposable HOME, fake Pi and op-agent, synthetic op:// references only."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_pi-jev"
IGNORE = ROOT / ".chezmoiignore"
ZSHRC = ROOT / "dot_zshrc"
CHEZMOI = shutil.which("chezmoi")
KEYS = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY")

FAKE_PI = '''#!/usr/bin/env python3
import json, os, pathlib, sys
keys = ("TYPESAFE_API_KEY", "OPENROUTER_API_KEY", "ARTIFICIAL_ANALYSIS_API_KEY", "PI_JEV_WRAPPED")
with (pathlib.Path(os.environ["HOME"])/"pi-runs.jsonl").open("a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "env": {k: os.environ[k] for k in keys if k in os.environ}})+"\\n")
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
        (agents / "model-openrouter.env").write_text(
            "# synthetic\nOPENROUTER_API_KEY=\"op://Agents/synthetic-openrouter/password\"\n"
            "ARTIFICIAL_ANALYSIS_API_KEY=op://Agents/synthetic-aa/password\n")
        self.env = {"HOME": str(self.home), "PATH": str(self.bin) + ":/usr/bin:/bin", "LANG": "C.UTF-8"}

    def run_wrapper(self, *args, **extra):
        result = subprocess.run([str(self.wrapper), *args], env=dict(self.env, **extra),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("SYNTHETIC-VALUE", result.stdout + result.stderr)
        [run] = self.calls("pi-runs.jsonl")
        return run

    def calls(self, name):
        path = self.home / name
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def test_default_puts_no_key_in_pis_environment(self):
        inherited = {key: "SYNTHETIC-INHERITED" for key in KEYS[:2]}
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

    def test_openrouter_flag_without_token_or_op_agent_starts_pi_without_keys(self):
        self.token.unlink()
        self.assertEqual(self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1")["env"], {"PI_JEV_WRAPPED": "1"})
        self.assertEqual(self.calls("op-agent-calls.jsonl"), [])

    def test_nested_launch_keeps_an_allowed_key_and_drops_it_otherwise(self):
        nested = {"PI_JEV_WRAPPED": "1", "OPENROUTER_API_KEY": "SYNTHETIC-INHERITED"}
        self.assertEqual(self.run_wrapper(PI_JEV_ALLOW_OPENROUTER="1", **nested)["env"]["OPENROUTER_API_KEY"],
                         "SYNTHETIC-INHERITED")
        (self.home / "pi-runs.jsonl").unlink()
        self.assertNotIn("OPENROUTER_API_KEY", self.run_wrapper(**nested)["env"])
        self.assertEqual(self.calls("op-agent-calls.jsonl"), [])

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
