"""dot_pi/agent/modify_settings.json, rendered by chezmoi from the model tiers in .chezmoidata/pi.yaml.

Each test copies the template and the data into a throwaway source dir and runs `chezmoi execute-template
--with-stdin` with the current settings.json on stdin, as `chezmoi apply` does for a modify-template.
Needs chezmoi (CI installs it; elsewhere the tests skip). The last test hands the result to the installed
Pi (pi_real.py: dummy keys, nothing prompted, so no model call) and skips on hosts without it.
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

TIERS = ("default", "peak", "light")
PI_SETTINGS = {  # Pi が自分で書くキーや本人の設定
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

    def chezmoi(self, *args, stdin=""):
        result = subprocess.run([CHEZMOI, "--source", str(self.source), "--config", str(self.base / "chezmoi.toml"),
                                 "--persistent-state", str(self.base / "state.boltdb"), "execute-template", *args],
                                input=stdin, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def render(self, current):
        return self.chezmoi("--with-stdin", "--file", str(self.source / TEMPLATE), stdin=current)

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

    def test_data_has_three_complete_tiers(self):
        tiers = self.tiers()
        self.assertEqual(sorted(tiers), sorted(TIERS))
        for t in TIERS:
            self.assertEqual(sorted(tiers[t]), ["id", "provider", "thinking"], t)
            self.assertIn(tiers[t]["thinking"], ("off", "minimal", "low", "medium", "high", "xhigh", "max"), t)

    def test_empty_input_starts_from_an_empty_object(self):
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
        self.assertEqual(out["modelThinkingLevels"]["openai/gpt-6-1-terra"], "xhigh")  # 消さない
        for key, level in want["modelThinkingLevels"].items():
            self.assertEqual(out["modelThinkingLevels"][key], level)

    def test_second_pass_changes_nothing(self):
        first = self.render(json.dumps(PI_SETTINGS))
        self.assertEqual(self.render(first), first)

    def test_changing_the_data_changes_the_settings(self):
        (self.source / DATA).write_text(
            "pi:\n  models:\n"
            "    default: {provider: anthropic, id: claude-sonnet-5-5, thinking: low}\n"
            "    peak: {provider: openai, id: gpt-6.1-terra, thinking: xhigh}\n"
            "    light: {provider: anthropic, id: claude-haiku-5-5, thinking: medium}\n")
        out = json.loads(self.render(json.dumps(PI_SETTINGS)))
        self.assertEqual((out["defaultProvider"], out["defaultModel"], out["defaultThinkingLevel"]),
                         ("anthropic", "claude-sonnet-5-5", "low"))
        self.assertEqual(out["enabledModels"], ["anthropic/claude-sonnet-5-5:low", "openai/gpt-6.1-terra:xhigh",
                                                "anthropic/claude-haiku-5-5:medium"])
        self.assertEqual(out["modelThinkingLevels"]["openai/gpt-6.1-terra"], "xhigh")
        self.assertEqual(out["modelThinkingLevels"]["anthropic/claude-opus-5-5"], "xhigh")  # 段から外れたものも残す

    @unittest.skipUnless(pi_real.available(), "Pi が入っていない (am5-itx だけ)")
    def test_real_pi_starts_on_the_default_tier_and_ctrl_p_cycles_the_tiers(self):
        tiers = self.tiers()
        settings = self.render(json.dumps({"lastChangelogVersion": "1.5.0"}))
        commands = [{"type": "get_state"}] + [{"type": "cycle_model"}] * 3
        responses, stderr, _ = pi_real.rpc({"settings.json": settings}, commands)
        seen = [pi_real.model_of(responses.get("c%d" % i, {})) for i in range(4)]
        want = [("%s/%s" % (tiers[t]["provider"], tiers[t]["id"]), tiers[t]["thinking"]) for t in TIERS + ("default",)]
        self.assertEqual(seen, want, stderr)


if __name__ == "__main__":
    unittest.main()
