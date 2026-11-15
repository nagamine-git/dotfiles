"""jev-router (virtual model jev/auto): a stub Pi and a fake classifier, no keys, network or model calls.

Node strips TypeScript like the other Pi tests. The real-Pi check (jev/auto is the default selection and
Ctrl+P cycles the tiers) lives in tests/pi-settings.py.
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
EXTENSION = ROOT / "home/dot_pi/agent/extensions/jev-router.ts"
NODE = shutil.which("node")
TIERS = {
    "default": {"provider": "anthropic", "id": "claude-opus-5-5", "thinking": "high"},
    "strong": {"provider": "openai", "id": "gpt-6.1-sol", "thinking": "max"},
    "peak": {"provider": "anthropic", "id": "claude-fable-5-2", "thinking": "max"},
    "light": {"provider": "anthropic", "id": "claude-haiku-5-5", "thinking": "high"},
    # Artificial Analysis Intelligence Index per effort (docs/model-radar/_state.json, 2026-11-15)
    "scores": {
        "claude-opus-5-5": {"low": 35, "medium": 48, "high": 52, "xhigh": 57, "max": 59},
        "claude-fable-5-2": {"low": 54, "medium": 56, "high": 62, "xhigh": 62, "max": 65},
        "claude-haiku-5-5": {"low": 19, "medium": 25, "high": 30, "xhigh": 35, "max": 36},
        "gpt-6.1-sol": {"low": 35, "medium": 46, "high": 50, "xhigh": 52, "max": 55},
    },
}
SECRET_TEXT = "SYNTHETIC-PRIVATE-PROMPT"
HARNESS = r'''
const s = JSON.parse(process.argv[2]);
const virtual = [], notices = [], statuses = [], classified = [];
const pi = { registerVirtualModel: (d) => virtual.push(d) };
const ctx = {
  hasUI: true,
  ui: {notify: (m) => notices.push(m), setStatus: (k, v) => statuses.push([k, v])},
  modelRegistry: {
    find: (provider, id) => ({provider, id}),
    hasConfiguredAuth: (m) => !(s.noAuth ?? []).includes(m.id),
    findOfType: s.noClassifier ? undefined : () => ({id: "jev-latest"}),
    classify: async (model, input, options) => {
      classified.push({state: input.state, hasKey: Boolean(options.apiKey || process.env.TYPESAFE_API_KEY)});
      if (s.hang) return new Promise(() => {});
      if (s.classifierThrows) throw Error("boom");
      return {stopReason: "stop", answers: {tier: {type: "choice", choice: "x", probabilities: s.p}}};
    },
  },
};
(await import('./jev-router.ts')).default(pi);
const out = {registered: virtual.map((v) => `${v.provider}/${v.id}`), notices, statuses, classified, routes: []};
for (const r of s.requests ?? []) {
  const messages = [{role: "user", content: [{type: "text", text: r.user ?? "hi"}]},
                    {role: "assistant", content: [{type: "text", text: r.assistant ?? "previous answer"}]},
                    {role: "user", content: r.content ?? [{type: "text", text: r.user ?? "hi"}]}];
  try {
    const route = await virtual[0].route({reason: r.reason ?? "user", thinkingLevel: r.level ?? "high",
      state: r.state, previous: r.previous, failed: r.failed, messages}, ctx);
    out.routes.push({id: route.model.id, thinking: route.thinkingLevel, state: route.state ?? null});
  } catch (e) { out.routes.push({error: String(e.message)}); }
}
console.log(JSON.stringify(out));
'''


def supports_types():
    if not NODE:
        return False
    version = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.lstrip("v")
    return tuple(map(int, version.split(".")[:2])) >= (23, 6)


@unittest.skipUnless(supports_types() or os.environ.get("CI"), "Node 23.6 以上が必要")
class PiRouter(unittest.TestCase):
    def setUp(self):
        if not supports_types():
            self.fail("CI requires Node 23.6+")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.agent = self.work / "agent"
        self.agent.mkdir()
        (self.agent / "model-tiers.json").write_text(json.dumps(TIERS))
        (self.work / "package.json").write_text('{"type":"module"}')
        shutil.copyfile(EXTENSION, self.work / "jev-router.ts")
        (self.work / "run.mjs").write_text(HARNESS)

    def run_router(self, timeout=15, **scenario):
        env = {"HOME": str(self.work), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
               "PI_CODING_AGENT_DIR": str(self.agent), "TYPESAFE_API_KEY": "dummy-not-a-key"}
        proc = subprocess.run([NODE, "run.mjs", json.dumps(scenario)], env=env, cwd=self.work,
                              capture_output=True, text=True, timeout=timeout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def ids(self, **scenario):
        return [r.get("id") or r.get("error") for r in self.run_router(**scenario)["routes"]]

    def test_registers_jev_auto_only_with_tier_data(self):
        self.assertEqual(self.run_router()["registered"], ["jev/auto"])
        (self.agent / "model-tiers.json").write_text('{"default": {}}')
        self.assertEqual(self.run_router()["registered"], [])
        (self.agent / "model-tiers.json").unlink()
        self.assertEqual(self.run_router()["registered"], [])

    def test_owner_named_model_wins_without_asking_the_classifier(self):
        cases = {"fable で考えて": "claude-fable-5-2", "ここぞで": "claude-fable-5-2",
                 "opus でお願い": "claude-opus-5-5", "sol に聞いて": "gpt-6.1-sol",
                 "haiku で要約": "claude-haiku-5-5", "軽量で調べて": "claude-haiku-5-5"}
        for text, want in cases.items():
            with self.subTest(text=text):
                out = self.run_router(p={"light": 1}, requests=[{"user": text}])
                self.assertEqual(out["routes"][0]["id"], want)
                self.assertEqual(out["classified"], [])

    def test_classifier_tiers_and_thresholds(self):
        cases = [({"deep": 0.7, "standard": 0.3}, "high", "claude-fable-5-2"),
                 ({"deep": 0.4, "standard": 0.6}, "high", "claude-opus-5-5"),
                 ({"deep": 0.4, "standard": 0.6}, "max", "claude-fable-5-2"),
                 ({"deep": 0.9, "standard": 0.1}, "low", "claude-opus-5-5"),
                 ({"light": 0.8, "standard": 0.2}, "high", "claude-haiku-5-5"),
                 ({"light": 0.5, "standard": 0.4, "deep": 0.1}, "high", "claude-opus-5-5"),
                 ({"standard": 0.9}, "high", "claude-opus-5-5")]
        for p, level, want in cases:
            with self.subTest(p=p, level=level):
                self.assertEqual(self.ids(p=p, requests=[{"level": level}]), [want])

    def test_peak_keeps_its_thinking_level_and_records_the_tier(self):
        out = self.run_router(p={"deep": 0.9}, requests=[{}])
        self.assertEqual(out["routes"][0], {"id": "claude-fable-5-2", "thinking": "max", "state": {"tier": "peak", "effort": "max"}})
        self.assertTrue(any("claude-fable-5-2" in n for n in out["notices"]))

    def test_a_go_ahead_stays_on_the_current_tier_and_effort_without_new_state(self):
        out = self.run_router(p={"continue": 0.9, "light": 0.1},
                              requests=[{"user": "OK", "state": {"tier": "default", "effort": "xhigh"}}])
        self.assertEqual(out["routes"][0], {"id": "claude-opus-5-5", "thinking": "xhigh", "state": None})
        out = self.run_router(p={"continue": 0.9}, requests=[{"user": "進めて"}])
        self.assertEqual(out["routes"][0]["id"], "claude-opus-5-5")

    def test_effort_is_the_lowest_that_reaches_the_score_the_kind_needs(self):
        cases = [({"standard": 0.9, "deep": 0.1}, ("claude-opus-5-5", "high")),     # 52 = the default bar
                 ({"standard": 0.6, "deep": 0.3}, ("claude-opus-5-5", "xhigh")),    # 52 + 5 -> 57
                 ({"deep": 0.8, "standard": 0.2}, ("claude-fable-5-2", "max")),     # best score 65
                 ({"light": 0.9, "standard": 0.1}, ("claude-haiku-5-5", "high"))]   # 30 = the light bar
        for p, want in cases:
            with self.subTest(p=p):
                r = self.run_router(p=p, requests=[{}])["routes"][0]
                self.assertEqual((r["id"], r["thinking"]), want)
                self.assertEqual(r["state"]["effort"], want[1])

    def test_new_scores_move_the_effort_without_a_code_change(self):
        TIERS["scores"]["claude-haiku-5-5"]["medium"] = 31
        TIERS["scores"]["claude-fable-5-2"]["max"] = 62
        TIERS["scores"]["claude-opus-5-5"]["xhigh"] = 52
        try:
            (self.agent / "model-tiers.json").write_text(json.dumps(TIERS))
            got = [(r["id"], r["thinking"]) for r in self.run_router(p={"light": 1}, requests=[{}])["routes"]]
            got += [(r["id"], r["thinking"]) for r in self.run_router(p={"deep": 1}, requests=[{}])["routes"]]
            got += [(r["id"], r["thinking"]) for r in self.run_router(p={"standard": 0.7, "deep": 0.3},
                                                                     requests=[{}])["routes"]]
        finally:
            TIERS["scores"]["claude-haiku-5-5"]["medium"] = 25
            TIERS["scores"]["claude-fable-5-2"]["max"] = 65
            TIERS["scores"]["claude-opus-5-5"]["xhigh"] = 57
        # medium now reaches 30; high ties max at 62; nothing below max reaches 57, so max (59)
        self.assertEqual(got, [("claude-haiku-5-5", "medium"), ("claude-fable-5-2", "high"),
                               ("claude-opus-5-5", "max")])

    def test_without_scores_the_tier_keeps_its_configured_effort(self):
        data = {k: v for k, v in TIERS.items() if k != "scores"}
        (self.agent / "model-tiers.json").write_text(json.dumps(data))
        for p, want in (({"light": 1}, "high"), ({"deep": 1}, "max"), ({"standard": 0.6, "deep": 0.3}, "high")):
            with self.subTest(p=p):
                self.assertEqual(self.run_router(p=p, requests=[{}])["routes"][0]["thinking"], want)

    def test_a_named_tier_uses_the_effort_of_its_kind(self):
        for text, want in (("fable で", ("claude-fable-5-2", "max")), ("opus で", ("claude-opus-5-5", "high")),
                           ("haiku で", ("claude-haiku-5-5", "high")), ("sol に", ("gpt-6.1-sol", "max"))):
            with self.subTest(text=text):
                r = self.run_router(p={"light": 1}, requests=[{"user": text}])["routes"][0]
                self.assertEqual((r["id"], r["thinking"]), want)

    def test_tool_follow_ups_and_retries_stay_on_the_model_of_the_turn(self):
        prev = {"model": {"provider": "anthropic", "id": "claude-fable-5-2"}, "thinkingLevel": "max"}
        failed = {"model": {"provider": "anthropic", "id": "claude-haiku-5-5"}, "thinkingLevel": "high",
                  "message": {"stopReason": "error", "errorMessage": "overloaded"}}
        out = self.run_router(p={"light": 1}, requests=[{"reason": "continuation", "previous": prev},
                                                        {"reason": "retry", "failed": failed, "previous": prev}])
        self.assertEqual([r["id"] for r in out["routes"]], ["claude-fable-5-2", "claude-haiku-5-5"])
        self.assertEqual(out["classified"], [])

    def test_requests_outside_the_loop_use_the_default_tier(self):
        self.assertEqual(self.ids(p={"deep": 1}, requests=[{"reason": "direct"}]), ["claude-opus-5-5"])

    def test_no_classifier_keeps_the_current_tier_or_default(self):
        for scenario in ({"noClassifier": True}, {"classifierThrows": True}):
            with self.subTest(**scenario):
                self.assertEqual(self.ids(**scenario, requests=[{}, {"state": {"tier": "light"}}]),
                                 ["claude-opus-5-5", "claude-haiku-5-5"])

    def test_a_hanging_classifier_times_out_instead_of_blocking_the_turn(self):
        self.assertEqual(self.ids(timeout=20, hang=True, requests=[{"state": {"tier": "peak"}}]), ["claude-fable-5-2"])

    def test_a_tier_without_credentials_falls_back_to_default(self):
        self.assertEqual(self.ids(p={"deep": 1}, noAuth=["claude-fable-5-2"], requests=[{}]), ["claude-opus-5-5"])
        out = self.run_router(p={"deep": 1}, noAuth=["claude-opus-5-5"], requests=[{}])
        self.assertIn("no credentials", out["routes"][0]["error"])

    def test_classifier_sees_bounded_text_and_the_log_never_holds_it(self):
        long_text = SECRET_TEXT + "x" * 20_000
        out = self.run_router(p={"standard": 1}, requests=[{"user": long_text, "assistant": "y" * 5_000,
                                                            "state": {"tier": "light"}}])
        state = out["classified"][0]["state"]
        self.assertEqual(len(state["owner_message"]), 6_000)
        self.assertEqual(len(state["previous_answer_tail"]), 1_500)
        self.assertEqual(state["current_tier"], "light")
        log = (self.agent / "jev-router.log.jsonl").read_text()
        self.assertNotIn(SECRET_TEXT, log)
        entry = json.loads(log.splitlines()[-1])
        self.assertEqual((entry["tier"], entry["effort"], entry["from"], entry["source"]),
                         ("default", "high", "light", "classifier"))


@unittest.skipUnless(shutil.which("chezmoi") or os.environ.get("CI"), "chezmoi が必要")
class TierFile(unittest.TestCase):
    def test_the_tier_file_carries_model_radar_s_scores_for_the_four_tier_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "c.toml").write_text("")
            proc = subprocess.run([shutil.which("chezmoi"), "--source", str(ROOT / "home"), "--config", str(Path(tmp) / "c.toml"),
                                   "--persistent-state", str(Path(tmp) / "s.db"), "execute-template", "--file",
                                   str(ROOT / "home/dot_pi/agent/model-tiers.json.tmpl")],
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        state = json.loads((ROOT / "docs/model-radar/_state.json").read_text())
        self.assertEqual(data["scores_as_of"], state["last_run"])
        for tier in ("default", "strong", "peak", "light"):
            model = data[tier]["id"]
            with self.subTest(tier=tier):
                self.assertEqual(data["scores"][model],
                                 {e: v.get("score") for e, v in state["intelligence"][model].items()})


if __name__ == "__main__":
    unittest.main()
