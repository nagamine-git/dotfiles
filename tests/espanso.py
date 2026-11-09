"""Test local Espanso imports and deployment without real vault or clipboard access."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "private_dot_config/espanso"
SYNC = CONFIG / "scripts/onepassword-sync.py"


class LocalImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="espanso-import-")
        self.root = Path(self.tmp.name)
        self.config = self.root / "config"
        self.config.mkdir()
        self.output = self.config / "match/private.local.yml"
        self.references = {
            "zwork": "op://Example/Work/name",
            "zhome": "op://Example/Home/address",
        }
        (self.config / "onepassword-references.json").write_text(json.dumps(self.references))
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.calls = self.root / "op-calls"
        self.restarts = self.root / "restarts"
        op = self.bin / "op"
        op.write_text('''#!/bin/bash
set -eu
[ "$#" -eq 3 ] && [ "$1" = read ] && [ "$2" = --no-newline ] || exit 2
[ -z "${OP_SERVICE_ACCOUNT_TOKEN+x}" ] || exit 3
[ -z "${OP_CONNECT_TOKEN+x}" ] || exit 3
[ -z "${OP_CONNECT_HOST+x}" ] || exit 3
printf '%s\n' "$3" >> "$TEST_CALLS"
if [ "${TEST_MODE:-success}" = fail ] || { [ "${TEST_MODE:-success}" = partial ] && [ "$3" = 'op://Example/Home/address' ]; }; then
  printf 'PRIVATE-PARTIAL'; printf 'PRIVATE-ERROR' >&2; exit 1
fi
printf '%s' "$TEST_VALUE"
''')
        op.chmod(0o700)
        espanso = self.bin / "espanso"
        espanso.write_text('''#!/bin/bash
set -eu
[ "$#" -eq 1 ] && [ "$1" = restart ] || exit 2
printf 'restart\n' >> "$TEST_RESTARTS"
exit "${TEST_RESTART_FAIL:-0}"
''')
        espanso.chmod(0o700)

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self, *flags, mode="success", value='Example "quoted" value\nSecond line', restart_fail=False):
        env = {
            **os.environ,
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "TEST_CALLS": str(self.calls),
            "TEST_RESTARTS": str(self.restarts),
            "TEST_MODE": mode,
            "TEST_VALUE": value,
            "TEST_RESTART_FAIL": "1" if restart_fail else "0",
            "OP_SERVICE_ACCOUNT_TOKEN": "test-only",
            "OP_CONNECT_TOKEN": "test-only",
            "OP_CONNECT_HOST": "https://example.invalid",
        }
        return subprocess.run([
            sys.executable, str(SYNC), "--config-dir", str(self.config), *flags,
        ], env=env, capture_output=True, text=True, check=False)

    def matches(self):
        return {m["trigger"]: m["replace"] for m in json.loads(self.output.read_text())["matches"]}

    def test_first_import_is_private_static_and_does_not_print_values(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(self.matches(), {key: 'Example "quoted" value\nSecond line' for key in self.references})
        for match in json.loads(self.output.read_text())["matches"]:
            self.assertIs(match["word"], True)
            self.assertNotIn("vars", match)
        self.assertNotIn('Example "quoted"', result.stdout + result.stderr)
        self.assertEqual(len(self.calls.read_text().splitlines()), 2)
        self.assertEqual(self.restarts.read_text(), "restart\n")

    def test_existing_manual_yaml_is_reused_without_any_op_calls(self):
        self.output.parent.mkdir()
        content = 'matches:\n  - trigger: zwork\n    replace: "Locally edited value"\n'
        self.output.write_text(content)
        result = self.run_sync(mode="fail")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertEqual(self.output.read_text(), content)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(self.restarts.read_text(), "restart\n")

    def test_refresh_is_explicit_and_can_replace_local_values(self):
        self.assertEqual(self.run_sync("--no-restart", value="Original").returncode, 0)
        result = self.run_sync("--refresh", "--no-restart", value="Refreshed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.matches(), {key: "Refreshed" for key in self.references})
        self.assertEqual(len(self.calls.read_text().splitlines()), 4)
        self.assertFalse(self.restarts.exists())

    def test_partial_import_keeps_failed_trigger_for_manual_editing_and_restarts(self):
        result = self.run_sync(mode="partial", value="Imported")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.matches(), {"zwork": "Imported", "zhome": "zhome"})
        self.assertIn("zhome", result.stderr)
        self.assertNotIn("PRIVATE", result.stdout + result.stderr + self.output.read_text())
        self.assertEqual(self.restarts.read_text(), "restart\n")

    def test_partial_refresh_preserves_previous_value_for_failed_field(self):
        self.assertEqual(self.run_sync("--no-restart", value="Original").returncode, 0)
        result = self.run_sync("--refresh", "--no-restart", mode="partial", value="Updated")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.matches(), {"zwork": "Updated", "zhome": "Original"})

    def test_refresh_preserves_local_matches_outside_the_manifest(self):
        self.output.parent.mkdir()
        local = [
            {"trigger": "zadd", "word": True, "replace": "Local company address"},
            {"trigger": "zpadd", "word": True, "replace": "Local home address"},
        ]
        self.output.write_text(json.dumps({"matches": local}))
        result = self.run_sync("--refresh", "--no-restart", value="Imported")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.matches(), {
            "zadd": "Local company address", "zpadd": "Local home address",
            "zwork": "Imported", "zhome": "Imported",
        })

    def test_total_failure_does_not_create_or_replace_a_cache(self):
        result = self.run_sync(mode="fail")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.output.exists())
        self.assertNotIn("PRIVATE", result.stdout + result.stderr)
        self.assertEqual(self.run_sync("--no-restart", value="Original").returncode, 0)
        before = self.output.read_bytes()
        result = self.run_sync("--refresh", mode="fail")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.output.read_bytes(), before)

    def test_refresh_of_manually_written_yaml_refuses_to_overwrite(self):
        self.output.parent.mkdir()
        content = 'matches:\n  - trigger: zwork\n    replace: "Keep this"\n'
        self.output.write_text(content)
        result = self.run_sync("--refresh")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.output.read_text(), content)
        self.assertFalse(self.calls.exists())

    def test_restart_failure_is_reported_but_import_is_preserved(self):
        result = self.run_sync(value="Imported", restart_fail=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.matches(), {key: "Imported" for key in self.references})
        self.assertIn("restart failed", result.stderr)

    def test_symlink_cache_is_rejected_without_changing_its_target(self):
        self.output.parent.mkdir()
        other = self.root / "other-file"
        other.write_text("Do not change")
        self.output.symlink_to(other)
        result = self.run_sync()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(other.read_text(), "Do not change")
        self.assertTrue(self.output.is_symlink())
        self.assertFalse(self.calls.exists())

    def test_directory_cache_path_is_rejected_before_authentication(self):
        self.output.mkdir(parents=True)
        result = self.run_sync()
        self.assertEqual(result.returncode, 1)
        self.assertTrue(self.output.is_dir())
        self.assertFalse(self.calls.exists())

    @unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is required for setup integration")
    def test_onchange_setup_reuses_existing_cache_without_authentication(self):
        home = self.root / "home"
        installed = home / ".config/espanso"
        shutil.copytree(CONFIG, installed)
        cache = installed / "match/private.local.yml"
        content = '{"matches": [{"trigger": "zhome", "replace": "cached-only-value"}]}\n'
        cache.write_text(content)
        rendered = subprocess.run([
            "chezmoi", "--config", "/dev/null", "--config-format", "toml",
            "--source", str(ROOT), "execute-template",
        ], input=(ROOT / "run_onchange_after_espanso.sh.tmpl").read_text(),
            text=True, capture_output=True, check=True)
        environment = {
            **os.environ, "HOME": str(home), "PATH": f"{self.bin}:{os.environ['PATH']}",
            "TEST_CALLS": str(self.calls), "TEST_RESTARTS": str(self.restarts),
            "TEST_MODE": "fail", "TEST_VALUE": "synthetic-only",
        }
        result = subprocess.run(["/bin/bash"], input=rendered.stdout, text=True,
                                capture_output=True, env=environment, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.calls.exists())
        self.assertEqual(cache.read_text(), content)
        self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o600)
        self.assertEqual(self.restarts.read_text(), "restart\n")
        self.assertNotIn("cached-only-value", result.stdout + result.stderr)

    def test_atomic_write_failure_keeps_existing_file_and_removes_temporary(self):
        spec = importlib.util.spec_from_file_location("espanso_sync_under_test", SYNC)
        module = importlib.util.module_from_spec(spec)
        with mock.patch.object(sys, "dont_write_bytecode", True):
            spec.loader.exec_module(module)
        self.output.parent.mkdir()
        self.output.write_text("original")
        with mock.patch.object(module.os, "replace", side_effect=OSError):
            with self.assertRaises(OSError):
                module.write_matches(self.output, [])
        self.assertEqual(self.output.read_text(), "original")
        self.assertEqual(list(self.output.parent.glob(".espanso-local-*.tmp")), [])


@unittest.skipIf(yaml is None, "PyYAML is required for configuration tests")
class SourceConfiguration(unittest.TestCase):
    def test_runtime_matches_do_not_call_op(self):
        base = yaml.safe_load((CONFIG / "match/base.yml").read_text())["matches"]
        self.assertEqual(base, [{"trigger": "znam", "word": True, "replace": "永峰 剛志"}])
        self.assertEqual(yaml.safe_load((CONFIG / "match/secrets.yml").read_text())["matches"], [])
        self.assertFalse((CONFIG / "scripts/onepassword.sh").exists())

    def test_reference_manifest_preserves_the_supplied_mapping(self):
        company = "op://Private/EFG technologies"
        personal = "op://Private/slsj3yhmvqzwbxher55scxsmji"
        self.assertEqual(json.loads((CONFIG / "onepassword-references.json").read_text()), {
            "zefg": f"{company}/name/firstname",
            "zph": f"{company}/address/defphone",
            "zadden": f"{company}/Adress/fg5psb4hw3zm73vmhsuq5tgztq",
            "zema": f"{personal}/internet/k2y5ab2v3y4xnkk2wbd4rtevk4",
            "zsal": f"{company}/internet/ujcrdtplmsh4oto3zjljuv4lwy",
            "zpma": f"{personal}/internet/email",
            "zpph": f"{personal}/name/phone",
        })


@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is required for deployment tests")
class ChezmoiDeployment(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="espanso-deployment-")
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.target = self.home / ".config/espanso"
        self.target.mkdir(parents=True)
        self.source = self.root / "source"
        self.config_source = self.source / "private_dot_config/espanso"
        shutil.copytree(CONFIG, self.config_source)
        shutil.copyfile(ROOT / ".chezmoiignore", self.source / ".chezmoiignore")
        self.config = self.root / "chezmoi.toml"
        self.config.write_text("")

    def tearDown(self):
        self.tmp.cleanup()

    def run_chezmoi(self, *args, input_text=None):
        return subprocess.run([
            shutil.which("chezmoi"), "--config", str(self.config),
            "--source", str(self.source), "--destination", str(self.home),
            "--persistent-state", str(self.root / "state.db"),
            "--cache", str(self.root / "cache"), "--no-tty", *args,
        ], env={"HOME": str(self.home), "PATH": os.defpath},
            input=input_text, capture_output=True, text=True, check=False)

    def apply(self, *flags):
        return self.run_chezmoi("apply", "--recursive", *flags, str(self.target))

    def test_target_directory_apply_deploys_every_managed_file(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        for source in self.config_source.rglob("*"):
            if source.is_file():
                target = self.target / source.relative_to(self.config_source)
                expected = source.read_bytes()
                if source.suffix == ".tmpl":
                    target = target.with_suffix("")
                    rendered = self.run_chezmoi("execute-template", input_text=source.read_text())
                    self.assertEqual(rendered.returncode, 0, rendered.stderr)
                    expected = rendered.stdout.encode()
                with self.subTest(file=source.name):
                    self.assertTrue(target.is_file())
                    self.assertEqual(target.read_bytes(), expected)

    def test_dry_run_reports_missing_files_without_deploying(self):
        result = self.apply("--dry-run", "--verbose")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(".config/espanso/scripts/onepassword-sync.py", result.stdout)
        self.assertIn(".config/espanso/onepassword-references.json", result.stdout)
        self.assertFalse((self.target / "onepassword-references.json").exists())

    def test_local_values_survive_reapply_and_cannot_be_added_to_source(self):
        output = self.target / "match/private.local.yml"
        output.parent.mkdir()
        output.write_text('{"matches": [{"trigger": "zhome", "replace": "Keep local"}]}\n')
        output.chmod(0o600)
        original = output.read_bytes()
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        added = self.run_chezmoi("add", str(output))
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertFalse(list(self.config_source.rglob("*local.yml*")))
        second = self.apply("--dry-run", "--verbose")
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout, "")


@unittest.skipIf(yaml is None, "PyYAML is required for platform configuration tests")
@unittest.skipUnless(shutil.which("chezmoi"), "chezmoi is required to render configuration")
class PlatformConfiguration(unittest.TestCase):
    def render(self, os_name):
        template = '{{ $_ := set .chezmoi "os" "' + os_name + '" }}\n' + (CONFIG / "config/default.yml.tmpl").read_text()
        result = subprocess.run([
            shutil.which("chezmoi"), "--config", "/dev/null", "--config-format", "toml",
            "--source", str(ROOT), "execute-template",
        ], input=template, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return yaml.safe_load(result.stdout)

    def test_linux_detects_colemak_and_pastes_into_terminals(self):
        config = self.render("linux")
        self.assertEqual(config["backend"], "Clipboard")
        self.assertIs(config["preserve_clipboard"], True)
        self.assertEqual(config["keyboard_layout"], {"layout": "us", "variant": "colemak"})
        self.assertEqual(config["paste_shortcut"], "CTRL+SHIFT+V")

    def test_macos_uses_native_paste_without_wayland_layout_override(self):
        config = self.render("darwin")
        self.assertEqual(config["backend"], "Clipboard")
        self.assertEqual(config["paste_shortcut"], "CMD+V")
        self.assertNotIn("keyboard_layout", config)


@unittest.skipUnless(shutil.which("git"), "git is required for ignore tests")
class GitIgnore(unittest.TestCase):
    def test_plaintext_cache_and_chezmoi_private_names_are_ignored(self):
        paths = [
            "private_dot_config/espanso/match/private.local.yml",
            "private_dot_config/espanso/match/private_private.local.yml",
            "private_dot_config/espanso/match/private.local.yml.bak",
        ]
        result = subprocess.run([
            "git", "-C", str(ROOT), "check-ignore", "--no-index", "--stdin",
        ], input="\n".join(paths) + "\n", capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), paths)


if __name__ == "__main__":
    unittest.main()
