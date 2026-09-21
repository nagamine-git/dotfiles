"""Offline checks: routing, argv integrity, failure handling and native config data."""
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "dot_local/bin/executable_ai-code"
PRESETS = ("standard", "routine", "deep", "review")


class LauncherTests(unittest.TestCase):
    def run_cli(self, *args, env=None):
        return subprocess.run(
            ["bash", str(LAUNCHER), *args], env=env,
            capture_output=True, text=True, check=False,
        )

    def dry(self, *args):
        result = self.run_cli("--dry-run", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return shlex.split(result.stdout)

    def test_all_claude_routes(self):
        for preset, model, effort in (
            ("standard", "opus", "high"),
            ("routine", "sonnet", "medium"),
            ("deep", "claude-fable-5-1", "high"),
            ("review", "opus", "xhigh"),
        ):
            with self.subTest(preset=preset):
                argv = self.dry("claude", preset, "a prompt")
                self.assertEqual(argv[:5], ["claude", "--model", model, "--effort", effort])
                self.assertEqual(argv[-1], "a prompt")
                self.assertNotIn("--fallback-model", argv)
        review = self.dry("claude", "review")
        self.assertEqual(review[review.index("--tools") + 1], "Read,Grep,Glob")
        self.assertIn("--strict-mcp-config", review)

    def test_all_codex_routes(self):
        for preset in PRESETS:
            with self.subTest(preset=preset):
                argv = self.dry("codex", preset)
                self.assertEqual(argv[:3], ["codex", "--profile", f"quality-{preset}"])
        review = self.dry("codex", "review", "--base", "main")
        self.assertEqual(review[-3:], ["review", "--base", "main"])
        self.assertIn('approval_policy="never"', review)
        self.assertEqual(review[review.index("--sandbox") + 1], "read-only")

    def test_default_and_end_of_options(self):
        self.assertEqual(self.dry("claude", "a prompt"), self.dry("claude", "standard", "a prompt"))
        self.assertEqual(self.dry("codex", "--", "deep")[-1], "deep")
        self.assertEqual(self.dry("codex", "standard", "exec", "hello")[-2:], ["exec", "hello"])

    def test_invalid_client_and_help(self):
        for args in ((), ("unknown",), ("--dry-run",)):
            self.assertEqual(self.run_cli(*args).returncode, 2)
        self.assertEqual(self.run_cli("--help").returncode, 0)

    def mock_env(self, directory, client, version, status=0):
        # Only child processes see these directories; never access live auth or models.
        mock = directory / client
        mock.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            f"version = {version!r}\n"
            "if sys.argv[1:] == ['--version']:\n"
            "    print(version)\n"
            "else:\n"
            "    with open(os.environ['AI_TEST_CAPTURE'], 'a') as f:\n"
            "        f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
            f"    sys.exit({status})\n"
        )
        mock.chmod(0o700)
        config_dir = directory / "config"
        config_dir.mkdir()
        for preset in PRESETS:
            (config_dir / f"quality-{preset}.config.toml").write_text("")
        (config_dir / "agents").mkdir()
        (config_dir / "agents/reviewer.md").write_text("mock")
        env = dict(os.environ)
        env.update(
            PATH=f"{directory}{os.pathsep}{env['PATH']}",
            CODEX_HOME=str(config_dir), CLAUDE_CONFIG_DIR=str(config_dir),
            AI_TEST_CAPTURE=str(directory / "calls.jsonl"),
        )
        return env

    def test_argv_is_literal_and_exit_is_propagated_without_retry(self):
        for client, version in (("claude", "2.1.273 (Claude Code)"), ("codex", "codex-cli 0.155.1")):
            with self.subTest(client=client), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                env = self.mock_env(directory, client, version, status=17)
                marker = directory / "should-not-exist"
                prompt = f'日本語 spaces; $(touch {marker}) `touch {marker}` "quotes"'
                result = self.run_cli(client, "standard", prompt, env=env)
                self.assertEqual(result.returncode, 17, result.stderr)
                calls = (directory / "calls.jsonl").read_text().splitlines()
                self.assertEqual(len(calls), 1)
                self.assertEqual(json.loads(calls[0])[-1], prompt)
                self.assertFalse(marker.exists())

    def test_old_or_unknown_version_stops_before_model_call(self):
        for client, version in (("claude", "2.1.256"), ("codex", "0.133.0"), ("codex", "unknown")):
            with self.subTest(client=client, version=version), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                env = self.mock_env(directory, client, version)
                result = self.run_cli(client, env=env)
                self.assertEqual(result.returncode, 2)
                self.assertFalse((directory / "calls.jsonl").exists())

    def test_missing_native_config_stops_before_model_call(self):
        for client in ("claude", "codex"):
            with self.subTest(client=client), tempfile.TemporaryDirectory() as tmp:
                directory = Path(tmp)
                version = "2.1.273" if client == "claude" else "0.155.1"
                env = self.mock_env(directory, client, version)
                config = directory / "config"
                missing = config / ("agents/reviewer.md" if client == "claude" else "quality-review.config.toml")
                missing.unlink()
                result = self.run_cli(client, "review", env=env)
                self.assertEqual(result.returncode, 2)
                self.assertIn("missing", result.stderr)
                self.assertFalse((directory / "calls.jsonl").exists())


class ConfigTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("chezmoi"), "chezmoi not installed; deployment check is optional")
    def test_scoped_apply_preserves_auth_and_base_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "destination"
            (destination / ".codex").mkdir(parents=True)
            (destination / ".claude").mkdir()
            untouched = {
                ".codex/config.toml": 'model = "existing-choice"\n',
                ".codex/auth.json": '{"sentinel": "test-only"}\n',
                ".claude/settings.json": '{"sentinel": "existing-hooks"}\n',
            }
            for name, content in untouched.items():
                (destination / name).write_text(content)
            isolated_config = Path(tmp) / "chezmoi.toml"
            isolated_config.write_text("")
            targets = [
                ".local/bin/ai-code", ".claude/CLAUDE.md", ".claude/agents",
                ".codex/AGENTS.md", ".codex/agents",
                *(f".codex/quality-{preset}.config.toml" for preset in PRESETS),
            ]
            result = subprocess.run(
                ["chezmoi", "--source", str(ROOT), "--destination", str(destination),
                 "--config", str(isolated_config), "--persistent-state", str(Path(tmp) / "state.boltdb"),
                 "--skip-secrets", "apply", "--parent-dirs", "--include=files,dirs", "--",
                 *(str(destination / name) for name in targets)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.access(destination / ".local/bin/ai-code", os.X_OK))
            for name, content in untouched.items():
                self.assertEqual((destination / name).read_text(), content)
            for preset in PRESETS:
                self.assertTrue((destination / f".codex/quality-{preset}.config.toml").is_file())
            self.assertTrue((destination / ".claude/agents/reviewer.md").is_file())
            self.assertTrue((destination / ".codex/agents/dotfiles-reviewer.toml").is_file())

    @unittest.skipUnless(shutil.which("codex"), "Codex CLI not installed; native check is optional")
    def test_native_codex_profile_loading_without_auth_or_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            for source in (ROOT / "private_dot_codex").glob("*.config.toml"):
                shutil.copyfile(source, config_dir / source.name)
            shutil.copytree(ROOT / "private_dot_codex/agents", config_dir / "agents")
            env = dict(os.environ)
            env["CODEX_HOME"] = str(config_dir)
            for preset in PRESETS:
                with self.subTest(preset=preset):
                    result = subprocess.run(
                        ["codex", "--profile", f"quality-{preset}", "mcp", "list", "--json"],
                        cwd=config_dir, env=env, capture_output=True, text=True, timeout=15,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
            # A negative control proves the CLI actually reads the selected layer.
            (config_dir / "quality-broken.config.toml").write_text('model = [')
            broken = subprocess.run(
                ["codex", "--profile", "quality-broken", "mcp", "list", "--json"],
                cwd=config_dir, env=env, capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(broken.returncode, 0)

    def test_codex_profiles_are_standalone_and_bounded(self):
        expected = {
            "standard": ("gpt-5.6-sol", "high"),
            "routine": ("gpt-5.6-terra", "medium"),
            "deep": ("gpt-6-astra", "high"),
            "review": ("gpt-6-astra", "high"),
        }
        for preset, pair in expected.items():
            with self.subTest(preset=preset):
                cfg = tomllib.loads((ROOT / f"private_dot_codex/quality-{preset}.config.toml").read_text())
                self.assertEqual((cfg["model"], cfg["model_reasoning_effort"]), pair)
                self.assertNotIn("profiles", cfg)
                if preset == "review":
                    self.assertEqual(cfg["review_model"], pair[0])
                    self.assertEqual(cfg["sandbox_mode"], "read-only")
                    self.assertEqual(cfg["approval_policy"], "never")
                    self.assertFalse(cfg["agents"]["enabled"])
                else:
                    self.assertEqual(cfg["agents"]["max_concurrent_threads_per_session"], 2)
                    self.assertNotIn("sandbox_mode", cfg)
                    self.assertNotIn("approval_policy", cfg)

    def test_codex_agents_have_required_metadata(self):
        for path in (ROOT / "private_dot_codex/agents").glob("*.toml"):
            cfg = tomllib.loads(path.read_text())
            self.assertEqual(cfg["name"], path.stem)
            self.assertTrue(cfg["description"])
            self.assertTrue(cfg["developer_instructions"])
            if path.stem != "dotfiles-implementer":
                self.assertEqual(cfg["sandbox_mode"], "read-only")

    def test_claude_agents_have_required_metadata_and_no_shell_for_readers(self):
        for role in ("implementer", "researcher", "reviewer"):
            text = (ROOT / f"dot_claude/agents/{role}.md").read_text()
            self.assertTrue(text.startswith("---\n"))
            frontmatter = text.split("---", 2)[1]
            fields = dict(line.split(":", 1) for line in frontmatter.splitlines() if ":" in line)
            self.assertEqual(fields["name"].strip(), role)
            self.assertTrue(fields["description"].strip())
            self.assertLessEqual(int(fields["maxTurns"]), 30)
            if role != "implementer":
                tools = {tool.strip() for tool in fields["tools"].split(",")}
                self.assertTrue(tools.isdisjoint({"Bash", "Write", "Edit", "NotebookEdit", "Agent"}))


if __name__ == "__main__":
    unittest.main()
