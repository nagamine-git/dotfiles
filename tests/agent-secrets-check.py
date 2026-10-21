"""No network or real secrets: check metadata, reference validation and safe resolution."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_agent-secrets-check"
SECRET = "top-secret-do-not-log"

FAKE_OP = """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys

args = sys.argv[1:]
with Path(os.environ['FAKE_CALLS']).open('a') as calls:
    calls.write(json.dumps(args) + '\\n')
config = json.loads(Path(os.environ['FAKE_CONFIG']).read_text())
action = args[0] if args else ''
if action == config.get('fail'):
    print('top-secret-do-not-log')
    print('top-secret-do-not-log', file=sys.stderr)
    raise SystemExit(1)
if action == 'whoami':
    print(json.dumps({'user_type': config.get('type', 'SERVICE_ACCOUNT'), 'email': 'hidden-email'}))
elif args[:2] == ['vault', 'list']:
    print(json.dumps([{'id': 'hidden-vault-id', 'name': name} for name in config.get('vaults', ['Agents'])]))
elif args[:2] == ['item', 'list']:
    print(json.dumps([{'id': 'hidden-item-id', 'title': 'hidden-item-title'}]))
elif action == 'run':
    if config.get('noise'):
        print('top-secret-do-not-log')
    env = dict(os.environ)
    env.update(config.get('resolved', {}))
    raise SystemExit(subprocess.run(args[args.index('--') + 1:], env=env).returncode)
else:
    raise SystemExit(2)
"""


class SecretsCheck(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        fake = self.directory / "op-agent"
        fake.write_text(FAKE_OP)
        fake.chmod(0o700)
        self.env_file = self.directory / "service.env"
        self.env_file.write_text('TOKEN="op://Agents/example/credential"\n')
        self.config_file = self.directory / "config.json"
        self.calls_file = self.directory / "calls.jsonl"

    def run_check(self, *args, **config):
        self.config_file.write_text(json.dumps(config))
        self.calls_file.write_text("")
        env = {**os.environ, "PATH": str(self.directory) + os.pathsep + os.environ["PATH"],
               "FAKE_CALLS": str(self.calls_file), "FAKE_CONFIG": str(self.config_file)}
        result = subprocess.run([sys.executable, str(SCRIPT), "--env-file", str(self.env_file), *args],
                                env=env, capture_output=True, text=True)
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        calls = [json.loads(line) for line in self.calls_file.read_text().splitlines()]
        return result, calls

    def test_default_reports_only_metadata_and_variable_names(self):
        result, calls = self.run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SERVICE_ACCOUNT", result.stdout)
        self.assertIn("Agents: 1 item(s)", result.stdout)
        self.assertIn("TOKEN: Agents reference", result.stdout)
        for hidden in ("hidden-email", "hidden-vault-id", "hidden-item-id", "hidden-item-title",
                       "example", "credential"):
            self.assertNotIn(hidden, result.stdout + result.stderr)
        self.assertNotIn("run", [call[0] for call in calls])

    def test_resolve_reports_only_presence_and_returns_failure_for_empty_values(self):
        self.env_file.write_text('TOKEN=op://Agents/example/credential\nEMPTY=op://Agents/other/password\n')
        result, calls = self.run_check("--resolve", resolved={"TOKEN": SECRET, "EMPTY": ""})
        self.assertEqual(result.returncode, 1)
        self.assertIn("TOKEN: present", result.stdout)
        self.assertIn("EMPTY: absent", result.stdout)
        run = next(call for call in calls if call[0] == "run")
        self.assertEqual(run[:3], ["run", "--env-file", str(self.env_file)])
        self.assertIn("-I", run)

    def test_successful_resolution(self):
        result, _ = self.run_check("--resolve", resolved={"TOKEN": SECRET})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TOKEN: present", result.stdout)

    def test_errors_never_echo_subprocess_output(self):
        for action in ("whoami", "vault", "item", "run"):
            with self.subTest(action=action):
                result, _ = self.run_check("--resolve", fail=action)
                self.assertEqual(result.returncode, 1)

    def test_unexpected_resolver_output_is_hidden(self):
        result, _ = self.run_check("--resolve", noise=True, resolved={"TOKEN": SECRET})
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("TOKEN: present", result.stdout)

    def test_invalid_references_are_rejected_before_resolution(self):
        for value in (SECRET, "op://Personal/example/credential", "op://Agents/example",
                      "op://Agents//credential", "op://Agents/example/credential?attribute=otp",
                      "op://Agents/example/credential\"", "op://Agents/example/field/extra/invalid"):
            with self.subTest(value=value):
                self.env_file.write_text("TOKEN=" + value + "\n")
                result, calls = self.run_check("--resolve")
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("run", [call[0] for call in calls])

    def test_quoted_references_with_spaces_and_sections_are_supported(self):
        self.env_file.write_text("# comment\nexport TOKEN='op://Agents/Service token/API/credential'\n")
        result, _ = self.run_check("--resolve", resolved={"TOKEN": SECRET})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_extra_vault_or_wrong_account_type_prevents_resolution(self):
        for config in ({"vaults": ["Agents", "Personal"]}, {"type": "USER"}):
            with self.subTest(config=config):
                result, calls = self.run_check("--resolve", **config)
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("run", [call[0] for call in calls])

    def test_empty_reference_file_cannot_resolve(self):
        self.env_file.write_text("# add references when a task needs them\n")
        result, calls = self.run_check("--resolve")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("run", [call[0] for call in calls])

    def test_duplicate_variables_and_invalid_assignments_are_rejected(self):
        for content in ("TOKEN=op://Agents/one/password\nTOKEN=op://Agents/two/password\n",
                        "not-an-env-assignment\n"):
            with self.subTest(content=content):
                self.env_file.write_text(content)
                result, calls = self.run_check("--resolve")
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("run", [call[0] for call in calls])


if __name__ == "__main__":
    unittest.main()
