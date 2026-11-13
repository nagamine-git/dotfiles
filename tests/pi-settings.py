"""Pi's modify-template: model tiers, preserved user settings and removal of the owned zsh prefix.

Uses a disposable chezmoi source. Real-Pi tests use dummy keys and RPC without model prompts.
No actual user settings, credentials or permission configuration are changed.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = "dot_pi/agent/modify_settings.json"
DATA = ".chezmoidata/pi.yaml"
CHEZMOI = shutil.which("chezmoi")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi_real  # noqa: E402

TIERS = ("default", "strong", "peak", "light")
LEGACY_PREFIX = '[[ -r "$PI_ZSH_SNAPSHOT" ]] && source "$PI_ZSH_SNAPSHOT"\nsetopt no_nomatch no_equals'
PI_SETTINGS = {
    "lastChangelogVersion": "1.5.0",
    "deviceId": "d51cf81e-0000-0000-0000-000000000000",
    "theme": "dark",
    "defaultProvider": "anthropic",
    "defaultModel": "claude-haiku-5-5",
    "defaultThinkingLevel": "high",
    "modelThinkingLevels": {"openai/gpt-6-1-terra": "xhigh", "anthropic/claude-opus-5-5": "xhigh"},
    "enabledModels": ["claude-*"],
}


@unittest.skipUnless(CHEZMOI or os.environ.get("CI"), "chezmoi が必要")
class PiSettings(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.source = self.base / "source"
        for rel in (TEMPLATE, DATA):
            (self.source / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, self.source / rel)
        (self.base / "chezmoi.toml").write_text("")

    def chezmoi(self, *args, stdin="", path=None):
        env = dict(os.environ, PATH=path) if path is not None else None
        result = subprocess.run([CHEZMOI, "--source", str(self.source), "--config", str(self.base / "chezmoi.toml"),
                                 "--persistent-state", str(self.base / "state.boltdb"), "execute-template", *args],
                                input=stdin, capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def render(self, current, path=None):
        return self.chezmoi("--with-stdin", "--file", str(self.source / TEMPLATE), stdin=current, path=path)

    def tiers(self):
        return json.loads(self.chezmoi('{{ .pi.models | toJson }}'))

    def expected(self, tiers):
        key = lambda t: "%s/%s" % (tiers[t]["provider"], tiers[t]["id"])
        return {
            "defaultProvider": tiers["default"]["provider"],
            "defaultModel": tiers["default"]["id"],
            "defaultThinkingLevel": tiers["default"]["thinking"],
            "modelThinkingLevels": {key(t): tiers[t]["thinking"] for t in TIERS},
            "enabledModels": ["%s:%s" % (key(t), tiers[t]["thinking"]) for t in TIERS],
        }

    def test_data_has_four_complete_tiers(self):
        tiers = self.tiers()
        self.assertEqual(sorted(tiers), sorted(TIERS))
        for t in TIERS:
            self.assertEqual(sorted(tiers[t]), ["id", "provider", "thinking"], t)
            self.assertIn(tiers[t]["thinking"], ("off", "minimal", "low", "medium", "high", "xhigh", "max"), t)

    def test_empty_input_starts_from_an_empty_object_without_shell_overrides(self):
        for current in ("", "\n  \n"):
            with self.subTest(current=current):
                self.assertEqual(json.loads(self.render(current)), self.expected(self.tiers()))

    def test_other_keys_are_kept_and_the_tier_keys_follow_the_data(self):
        out = json.loads(self.render(json.dumps(PI_SETTINGS, indent=2)))
        want = self.expected(self.tiers())
        for key in ("lastChangelogVersion", "deviceId", "theme"):
            self.assertEqual(out[key], PI_SETTINGS[key])
        for key in ("defaultProvider", "defaultModel", "defaultThinkingLevel", "enabledModels"):
            self.assertEqual(out[key], want[key])
        self.assertEqual(out["modelThinkingLevels"]["openai/gpt-6-1-terra"], "xhigh")
        for key, level in want["modelThinkingLevels"].items():
            self.assertEqual(out["modelThinkingLevels"][key], level)

    def test_second_pass_changes_nothing(self):
        first = self.render(json.dumps(PI_SETTINGS))
        self.assertEqual(self.render(first), first)

    def test_changing_the_data_changes_the_settings(self):
        (self.source / DATA).write_text(
            "pi:\n  models:\n"
            "    default: {provider: anthropic, id: claude-sonnet-5-5, thinking: low}\n"
            "    strong: {provider: openai, id: gpt-6.1-sol, thinking: high}\n"
            "    peak: {provider: openai, id: gpt-6.1-terra, thinking: xhigh}\n"
            "    light: {provider: anthropic, id: claude-haiku-5-5, thinking: medium}\n")
        out = json.loads(self.render(json.dumps(PI_SETTINGS)))
        self.assertEqual((out["defaultProvider"], out["defaultModel"], out["defaultThinkingLevel"]),
                         ("anthropic", "claude-sonnet-5-5", "low"))
        self.assertEqual(out["enabledModels"], ["anthropic/claude-sonnet-5-5:low", "openai/gpt-6.1-sol:high",
                                                "openai/gpt-6.1-terra:xhigh", "anthropic/claude-haiku-5-5:medium"])
        self.assertEqual(out["modelThinkingLevels"]["openai/gpt-6.1-terra"], "xhigh")
        self.assertEqual(out["modelThinkingLevels"]["anthropic/claude-opus-5-5"], "xhigh")

    def test_legacy_snapshot_prefix_removes_only_the_owned_shell_overrides(self):
        old = dict(PI_SETTINGS, shellPath="/fixture/bin/zsh", shellCommandPrefix=LEGACY_PREFIX)
        out = json.loads(self.render(json.dumps(old)))
        self.assertNotIn("shellPath", out)
        self.assertNotIn("shellCommandPrefix", out)
        self.assertEqual(out["theme"], PI_SETTINGS["theme"])
        self.assertEqual(out["deviceId"], PI_SETTINGS["deviceId"])

    def test_legacy_prefix_is_removed_even_without_a_shell_path(self):
        out = json.loads(self.render(json.dumps({"shellCommandPrefix": LEGACY_PREFIX})))
        self.assertEqual(out, self.expected(self.tiers()))

    def test_custom_shell_path_and_prefix_are_preserved(self):
        for settings in ({"shellPath": "/bin/bash", "shellCommandPrefix": "export CI=1"},
                         {"shellPath": "/custom/zsh"}, {"shellCommandPrefix": "export CI=1"}):
            with self.subTest(settings=settings):
                out = json.loads(self.render(json.dumps(settings)))
                for key, value in settings.items():
                    self.assertEqual(out[key], value)

    def test_shell_migration_does_not_depend_on_zsh_being_installed(self):
        empty = self.base / "empty-path"
        empty.mkdir()
        old = json.dumps({"shellPath": "/fixture/bin/zsh", "shellCommandPrefix": LEGACY_PREFIX})
        self.assertEqual(self.render(old, path=str(empty)), self.render(old))

    def test_migrating_the_legacy_prefix_is_idempotent(self):
        old = json.dumps(dict(PI_SETTINGS, shellPath="/fixture/bin/zsh", shellCommandPrefix=LEGACY_PREFIX))
        first = self.render(old)
        self.assertEqual(self.render(first), first)

    @unittest.skipUnless(pi_real.available(), "Pi が入っていない (am5-itx だけ)")
    def test_real_pi_uses_bash_and_does_not_load_an_inherited_snapshot(self):
        snapshot = self.base / "legacy-snapshot.zsh"
        snapshot.write_text('touch "%s"\n' % (self.base / "snapshot-ran"))
        old = dict(PI_SETTINGS, shellPath="/fixture/bin/zsh", shellCommandPrefix=LEGACY_PREFIX)
        settings = self.render(json.dumps(old))
        cmd = "names=(ALPHA BETA); mapfile -t values < <(printf 'one\\ntwo\\n'); printf '%s:%s\\n' \"${names[0],,}\" \"${values[1]}\""
        responses, stderr, _ = pi_real.rpc({"settings.json": settings}, [{"type": "bash", "command": cmd}],
                                           env={"PI_ZSH_SNAPSHOT": str(snapshot), "PI_ZSH_SNAPSHOT_SHA256": "SYNTHETIC-STALE"})
        data = responses.get("c0", {}).get("data") or {}
        self.assertEqual((data.get("exitCode"), data.get("output")), (0, "alpha:two\n"), stderr)
        self.assertFalse((self.base / "snapshot-ran").exists())

    @unittest.skipUnless(pi_real.available(), "Pi が入っていない (am5-itx だけ)")
    def test_real_pi_starts_on_the_default_tier_and_ctrl_p_cycles_the_tiers(self):
        tiers = self.tiers()
        settings = self.render(json.dumps({"lastChangelogVersion": "1.5.0"}))
        commands = [{"type": "get_state"}] + [{"type": "cycle_model"}] * len(TIERS)
        responses, stderr, _ = pi_real.rpc({"settings.json": settings}, commands)
        seen = [pi_real.model_of(responses.get("c%d" % i, {})) for i in range(len(TIERS) + 1)]
        want = [("%s/%s" % (tiers[t]["provider"], tiers[t]["id"]), tiers[t]["thinking"]) for t in TIERS + ("default",)]
        self.assertEqual(seen, want, stderr)


if __name__ == "__main__":
    unittest.main()
