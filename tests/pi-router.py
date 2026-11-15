"""jev-router (virtual model jev/auto) and model-radar: a stub Pi and a fake classifier, no keys, network or model calls.

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
    "default": {"provider": "anthropic", "id": "claude-opus-5-5", "thinking": "medium"},
    "strong": {"provider": "openai", "id": "gpt-6.1-sol", "thinking": "max"},
    "peak": {"provider": "anthropic", "id": "claude-fable-5-2", "thinking": "max"},
    "light": {"provider": "anthropic", "id": "claude-haiku-5-5", "thinking": "high"},
    "weights": {"intelligence": 6, "cost": 2, "speed": 1},
}
OPUS, FABLE, HAIKU, SONNET = "claude-opus-5-5", "claude-fable-5-2", "claude-haiku-5-5", "claude-sonnet-5-5"
SOL, TERRA, ASTRA, LUNA = "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-astra", "gpt-6-luna"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
# Artificial Analysis, 2026-11-15: (Intelligence Index, USD per task, median seconds) for low..max, and USD per 1M
# tokens written to the cache. The totals these give (score^6 / cost^2 / seconds) at the start of a session:
#   light    (>= 29.9)  Terra medium 1.10e10, Sol low 5.24e9 (within the A/B ratio), Sol medium 4.57e9
#   standard (>= 48.2)  Sol high 8.99e8, Sol xhigh 2.67e8 (just outside the ratio), Fable low 2.26e8, Opus medium 8.7e7
#   hard     (>= 53.2)  Fable low 2.26e8, Fable medium 9.7e7 (within the ratio), Sol max 6.0e7
#   deep     (>  59.1)  Fable high 1.9e7, Fable xhigh 3.3e6        critical (>= 64.6)  Fable max
AA = {
    FABLE: ("anthropic", 10, [(53.9, 3.0972, 11.3), (56.4, 3.8026, 23.0), (61.8, 9.0784, 35.4), (62.2, 14.8286, 80.0), (64.6, 26.5386, 152.4)]),
    OPUS: ("anthropic", 5, [(34.8, 0.9755, 13.1), (48.2, 2.4511, 23.9), (51.8, 3.4647, 41.7), (57.4, 6.0472, 129.0), (59.1, 10.0364, 598.6)]),
    SONNET: ("anthropic", 2.5, [(25.6, 0.5113, 5.9), (30.8, 0.7807, 6.2), (41.5, 1.6361, 17.3), (49.9, 4.092, 34.2), (54.5, 10.0206, 437.8)]),
    HAIKU: ("anthropic", 0.125, [(18.6, 0.0438, 13.1), (24.6, 0.0918, 13.7), (29.9, 0.1586, 27.4), (34.6, 0.2484, 61.8), (36.5, 0.411, 320.2)]),
    ASTRA: ("openai", 12.5, [(43.3, 1.4237, 14.7), (51.6, 2.7324, 17.1), (54.8, 3.2386, 83.5), (55.3, 3.6589, 173.6), (56.9, 6.2447, 300.5)]),
    SOL: ("openai", 2.5, [(34.8, 0.1615, 13.0), (46.3, 0.3594, 16.7), (50.3, 0.591, 51.6), (52.5, 0.764, 134.5), (54.6, 1.2721, 273.7)]),
    TERRA: ("openai", 1.25, [(29.4, 0.0713, 8.6), (38.2, 0.1688, 9.9), (42.4, 0.2593, 27.0), (45.3, 0.4007, 70.0), (51.3, 0.9611, 280.3)]),
    LUNA: ("openai", 0.125, [(9.7, 0.0051, 7.5), (18.5, 0.0422, 12.5), (21.4, 0.0729, 19.6), (23.5, 0.1041, 33.1), (27.9, 0.152, 106.7)]),
}


def scores(owner=None):
    """model-radar's file for the router. owner: {(model, effort): {level: {"f": factor, "n": judged}}}."""
    models = {}
    for mid, (provider, write, rows) in AA.items():
        efforts = {e: {"score": sc, "cost": c, "seconds": t} for e, (sc, c, t) in zip(EFFORTS, rows)}
        for (m, e), o in (owner or {}).items():
            if m == mid:
                efforts[e]["owner"] = o
        models[mid] = {"provider": provider, "name": mid, "in_pi": True, "price": {"cache_write": write}, "efforts": efforts}
    return {"source": "test", "fetched_at": "2026-11-15T00:00:00+00:00", "models": models}


SECRET_TEXT = "SYNTHETIC-PRIVATE-PROMPT"
HARNESS = r'''
const s = JSON.parse(process.argv[2]);
const virtual = [], notices = [], statuses = [], classified = [], handlers = {};
const pi = { registerVirtualModel: (d) => virtual.push(d),
  on: (name, fn) => { (handlers[name] ??= []).push(fn); } };
let request;
let clock = s.now ?? 1_800_000_000_000;
Date.now = () => clock;
Math.random = () => request?.random ?? s.random ?? 0;  // 0: the first arm of an A/B pair
const ctx = {
  hasUI: true,
  getContextUsage: () => (request?.tokens ?? s.tokens) === undefined ? undefined : {tokens: request?.tokens ?? s.tokens},
  ui: {notify: (m) => notices.push(m), setStatus: (k, v) => statuses.push([k, v])},
  modelRegistry: {
    find: (provider, id) => ({provider, id, contextWindow: (s.windows ?? {})[id]}),
    hasConfiguredAuth: (m) => !(s.noAuth ?? []).includes(m.id),
    isUsingOAuth: (m) => !(s.apiKeyProviders ?? []).includes(m.provider),
    getProvider: (provider) => ({auth: {oauth: {isSubscription: !s.notSubscription
      && !(s.notSubscriptionProviders ?? []).includes(provider)}}}),
    findOfType: s.noClassifier ? undefined : () => ({id: "jev-latest"}),
    classify: async (model, input, options) => {
      classified.push({state: input.state, questions: Object.keys(input.questions),
        hasKey: Boolean(options.apiKey || process.env.TYPESAFE_API_KEY)});
      if (s.hang) return new Promise(() => {});
      if (s.classifierThrows) throw Error("boom");
      const r = {...(s.rating ?? {}), ...(request.rating ?? {})};
      const bool = (k, fallback) => (input.questions[k] ? {[k]: {type: "bool", probability: r[k] ?? fallback}} : {});
      return {stopReason: "stop", answers: {
        level: {type: "score", score: r.score ?? 1, confidence: 1},
        go: {type: "bool", probability: r.go ?? 0},
        ...bool("asked", 1), ...bool("failed", 0), ...bool("done", 0), ...bool("shipped", 0)}};
    },
  },
};
(await import('./jev-router.ts')).default(pi);
const out = {registered: virtual.map((v) => `${v.provider}/${v.id}`), notices, statuses, classified, routes: []};
let state, previous;
for (const r of s.requests ?? []) {
  request = r;
  if (r.now !== undefined) clock = r.now;
  if (r.scoresFile !== undefined) {
    const fs = await import("node:fs");
    fs.writeFileSync(process.env.PI_CODING_AGENT_DIR + "/model-scores.json", JSON.stringify(r.scoresFile));
    fs.utimesSync(process.env.PI_CODING_AGENT_DIR + "/model-scores.json", new Date(), new Date(Date.now() + (r.mtime ?? 0)));
  }
  for (const response of r.responses ?? []) {
    for (const fn of handlers.after_provider_response ?? []) await fn({status: response.status ?? 200, headers: response.headers}, ctx);
    if (response.stream !== false) {
      for (const fn of handlers.provider_stream_event ?? []) await fn({provider: response.provider ?? "anthropic",
        model: response.model ?? "claude-opus-5-5"}, ctx);
    }
  }
  const messages = [{role: "user", content: [{type: "text", text: "hi"}]},
                    {role: "assistant", content: [{type: "text", text: r.assistant ?? "previous answer"}]},
                    {role: "user", content: [{type: "text", text: r.user ?? "hi"}]}];
  try {
    // chain: the state and the model of one request are the next one's, as in a session
    const route = await virtual[0].route({reason: r.reason ?? "user", thinkingLevel: r.level ?? "high",
      state: s.chain ? state : r.state, previous: s.chain ? previous : r.previous, failed: r.failed, messages}, ctx);
    if (route.state) state = route.state;
    previous = {model: route.model, thinkingLevel: route.thinkingLevel};
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
        (self.agent / "model-scores.json").write_text(json.dumps(scores()))
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

    def routes(self, **scenario):
        return [(r["id"], r["thinking"]) if "id" in r else r["error"] for r in self.run_router(**scenario)["routes"]]

    def log(self):
        return [json.loads(line) for line in (self.agent / "jev-router.log.jsonl").read_text().splitlines()]

    @staticmethod
    def on(model, effort, level="standard", **more):
        provider = AA[model][0] if model in AA else "openai"
        return dict({"model": f"{provider}/{model}", "effort": effort, "level": level}, **more)

    def test_registers_jev_auto_only_with_tier_data(self):
        self.assertEqual(self.run_router()["registered"], ["jev/auto"])
        (self.agent / "model-tiers.json").write_text('{"default": {}}')
        self.assertEqual(self.run_router()["registered"], [])
        (self.agent / "model-tiers.json").unlink()
        self.assertEqual(self.run_router()["registered"], [])

    # --- the choice: floors and the total score ---

    def test_each_level_gets_the_best_total_among_all_models_that_reach_its_floor(self):
        cases = [(0.2, (TERRA, "medium")), (0.49, (TERRA, "medium")),   # light: >= Haiku high (29.9)
                 (0.5, (SOL, "high")), (1.49, (SOL, "high")),           # standard: >= Opus medium (48.2), the owner's base
                 (1.5, (FABLE, "low")), (2.49, (FABLE, "low")),         # hard: 5 more
                 (2.5, (FABLE, "high")), (3.49, (FABLE, "high")),       # deep: more than Opus reaches at any effort (59.1)
                 (3.5, (FABLE, "max")), (4.0, (FABLE, "max"))]          # critical: the best of the peak model
        for score, want in cases:
            with self.subTest(score=score):
                self.assertEqual(self.routes(rating={"score": score}, requests=[{}]), [want])

    def test_the_weights_of_the_total_come_from_the_tier_file(self):
        # Only intelligence counts: the highest score, whatever it costs.
        (self.agent / "model-tiers.json").write_text(json.dumps(dict(TIERS, weights={"intelligence": 6, "cost": 0, "speed": 0})))
        self.assertEqual(self.routes(rating={"score": 1.0}, requests=[{}]), [(FABLE, "max")])
        # Only cost counts: the cheapest that reaches the floor.
        (self.agent / "model-tiers.json").write_text(json.dumps(dict(TIERS, weights={"intelligence": 0, "cost": 2, "speed": 0})))
        self.assertEqual(self.routes(rating={"score": 1.0}, random=0, requests=[{}]), [(SOL, "high")])
        (self.agent / "model-tiers.json").write_text(json.dumps(dict(TIERS, weights={"intelligence": 0, "cost": 0, "speed": 1})))
        self.assertEqual(self.routes(rating={"score": 1.0}, requests=[{}]), [(FABLE, "low")])  # 11.3 s

    def test_a_scarce_model_counts_as_dearer_and_its_top_efforts_are_only_for_the_owner_to_name(self):
        spare = dict(TIERS, scarce={FABLE: {"cost_factor": 2, "max_effort": "high"}})
        (self.agent / "model-tiers.json").write_text(json.dumps(spare))
        # hard: Fable low at twice its cost (5.7e7) is now behind Sol max (6.0e7): the two are tested against each other.
        # critical: the best Fable effort that may be chosen is high. standard on Fable: back to Sol at once (16x).
        got = [self.routes(rating={"score": sc}, random=rnd, requests=[{"state": st, "tokens": 50_000 if st else 0}])[0]
               for sc, rnd, st in ((2.0, 0, None), (2.0, 0.9, None), (3.0, 0, None), (3.9, 0, None), (1.0, 0, self.on(FABLE, "low", "hard")))]
        self.assertEqual(got, [(SOL, "max"), (FABLE, "low"), (FABLE, "high"), (FABLE, "high"), (SOL, "high")])
        named = [self.routes(rating={"score": 3.9, "asked": 0.9}, requests=[{"user": text}])[0] for text in ("fable で", "fable max で")]
        self.assertEqual(named, [(FABLE, "high"), (FABLE, "max")])
        self.assertEqual(self.routes(noClassifier=True, requests=[{"user": "fable で"}]), [(FABLE, "high")])

    def test_the_owner_s_factor_changes_the_ranking_but_not_who_reaches_the_floor(self):
        enough = {"f": 1.0, "n": 30}
        owner = {(SOL, "high"): {"standard": {"f": 0.9, "n": 30}}, (FABLE, "low"): {"standard": {"f": 1.1, "n": 30}},
                 (SOL, "xhigh"): {"standard": enough}}
        (self.agent / "model-scores.json").write_text(json.dumps(scores(owner)))
        # Sol high 8.99e8 x 0.9^6 = 4.8e8 < Fable low 2.26e8 x 1.1^6 = 4.0e8? No: still ahead. With Fable's 1.1 and
        # Sol's 0.9 the ratio 3.97 shrinks to 1.19, and it is the factor on Sol xhigh (1.0) that stays behind.
        self.assertEqual(self.routes(rating={"score": 1.0}, requests=[{}]), [(SOL, "high")])
        owner[(SOL, "high")] = {"standard": {"f": 0.85, "n": 30}}  # model-radar keeps to 0.9..1.1; the router takes what it is given
        (self.agent / "model-scores.json").write_text(json.dumps(scores(owner)))
        self.assertEqual(self.routes(rating={"score": 1.0}, requests=[{}]), [(FABLE, "low")])
        # A factor never lifts a model over a floor: Opus max (59.1) is not deep (> 59.1) even at 1.1.
        (self.agent / "model-scores.json").write_text(json.dumps(scores({(OPUS, "max"): {"deep": {"f": 1.1, "n": 30}}})))
        self.assertEqual(self.routes(rating={"score": 3.0}, requests=[{}]), [(FABLE, "high")])

    def test_without_score_data_each_level_uses_its_own_tier(self):
        (self.agent / "model-scores.json").unlink()
        on_default = self.on(OPUS, "medium")
        got = [self.routes(rating={"score": score}, requests=[{"state": state}])[0]
               for score, state in ((0.1, None), (0.1, on_default), (1.0, None), (2.0, on_default), (3.0, on_default), (3.9, None))]
        self.assertEqual(got, [(HAIKU, "high"), (OPUS, "medium"), (OPUS, "medium"), (OPUS, "medium"), (FABLE, "max"), (FABLE, "max")])

    def test_model_radar_s_file_is_read_again_when_it_changes_and_excluded_efforts_are_left_out(self):
        changed = scores()
        changed["models"][SOL]["efforts"]["high"]["excluded"] = True  # failed its benchmark in Pi
        self.assertEqual(self.routes(rating={"score": 1.0}, requests=[{}, {"scoresFile": changed, "mtime": 5000}]),
                         [(SOL, "high"), (SOL, "xhigh")])
        not_in_pi = scores()
        not_in_pi["models"][SOL]["in_pi"] = False
        (self.agent / "model-scores.json").write_text(json.dumps(not_in_pi))
        self.assertEqual(self.routes(rating={"score": 1.0}, requests=[{}]), [(FABLE, "low")])

    def test_a_model_whose_context_window_is_too_small_for_the_conversation_is_not_a_candidate(self):
        windows = {SOL: 272_000, TERRA: 272_000, ASTRA: 272_000, LUNA: 272_000}
        self.assertEqual(self.routes(rating={"score": 1.0}, windows=windows, requests=[{"tokens": 200_000}, {"tokens": 250_000}]),
                         [(SOL, "high"), (FABLE, "low")])  # 80% of 272k is 217.6k

    def test_other_providers_are_candidates_only_with_a_subscription(self):
        # OpenAI on an API key: never chosen automatically. The default's provider is used as it is set up.
        self.assertEqual(self.routes(rating={"score": 1.0}, apiKeyProviders=["openai"], requests=[{}]), [(FABLE, "low")])
        self.assertEqual(self.routes(rating={"score": 1.0}, apiKeyProviders=["openai", "anthropic"], requests=[{}]), [(FABLE, "low")])
        self.assertEqual(self.routes(rating={"score": 1.0}, noAuth=[SOL, TERRA, ASTRA, LUNA, FABLE], requests=[{}]), [(OPUS, "medium")])

    # --- changing the model ---

    def test_the_model_in_use_is_left_only_for_twice_the_total_after_the_cache_is_paid_for_both_ways(self):
        on_sol = self.on(SOL, "high")
        # hard: Fable low 2.26e8 against staying on Sol max 6.0e7. Writing 50k tokens there and back adds $0.63.
        for tokens, want in ((50_000, (FABLE, "low")), (300_000, (SOL, "max"))):
            with self.subTest(tokens=tokens):
                self.assertEqual(self.routes(rating={"score": 2.0}, requests=[{"state": on_sol, "tokens": tokens}]), [want])
        # standard, on Fable: Sol high 8.99e8 against staying on Fable low 2.26e8 (x2).
        on_fable = self.on(FABLE, "low", "hard")
        for tokens, want in ((10_000, (SOL, "high")), (50_000, (FABLE, "low"))):
            with self.subTest(tokens=tokens):
                self.assertEqual(self.routes(rating={"score": 1.0}, requests=[{"state": on_fable, "tokens": tokens}]), [want])
        # A change of effort is free: light on Sol stays there at its best effort for light.
        self.assertEqual(self.routes(rating={"score": 0.1}, requests=[{"state": on_sol, "tokens": 50_000}]), [(SOL, "low")])

    def test_a_session_that_came_from_another_model_has_its_cache_there(self):
        previous = {"model": {"provider": "anthropic", "id": FABLE}, "thinkingLevel": "high"}
        self.assertEqual(self.routes(rating={"score": 1.0}, requests=[{"previous": previous, "tokens": 50_000}]), [(FABLE, "low")])

    # --- silent A/B tests ---

    def test_a_near_tie_gives_the_session_one_of_the_two_at_random_and_the_session_keeps_it(self):
        out = self.run_router(rating={"score": 0.1}, chain=True, requests=[{"random": 0.9}, {"random": 0}, {"random": 0.9, "rating": {"score": 2.0}}])
        # light: Terra medium | Sol low. hard: Fable low | Fable medium, but the arm drawn (medium, 9.7e7) is not twice
        # staying on Sol max (6.0e7), so the session stays; the draw is kept for when it does move.
        self.assertEqual([(r["id"], r["thinking"]) for r in out["routes"]], [(SOL, "low"), (SOL, "low"), (SOL, "max")])
        self.assertEqual(out["routes"][0]["state"]["ab"], {"light": f"openai/{SOL}:low"})
        self.assertEqual(out["routes"][2]["state"]["ab"], {"light": f"openai/{SOL}:low", "hard": f"anthropic/{FABLE}:medium"})
        fresh = self.run_router(rating={"score": 2.0}, random=0.9, requests=[{}])["routes"][0]
        self.assertEqual((fresh["id"], fresh["thinking"], fresh["state"]["ab"]), (FABLE, "medium", {"hard": f"anthropic/{FABLE}:medium"}))
        entries = [e for e in self.log() if "kind" not in e]
        self.assertEqual(entries[0]["ab"], [f"openai/{TERRA}:medium", f"openai/{SOL}:low"])
        self.assertNotIn("ab", entries[1])  # no new draw
        self.assertEqual(out["notices"], [])  # nothing is announced
        self.assertEqual(self.routes(rating={"score": 0.1}, random=0, requests=[{}]), [(TERRA, "medium")])

    def test_no_test_where_the_gap_is_wide_or_both_have_been_judged_enough(self):
        self.assertEqual(self.routes(rating={"score": 3.0}, random=0.9, requests=[{}]), [(FABLE, "high")])  # xhigh is 5.8x behind
        enough = {"light": {"f": 1.0, "n": 30}}
        (self.agent / "model-scores.json").write_text(json.dumps(scores({(TERRA, "medium"): enough, (SOL, "low"): enough})))
        out = self.run_router(rating={"score": 0.1}, random=0.9, requests=[{}])
        self.assertEqual((out["routes"][0]["id"], out["routes"][0]["thinking"]), (TERRA, "medium"))
        self.assertNotIn("ab", out["routes"][0]["state"])
        one = {(TERRA, "medium"): enough, (SOL, "low"): {"light": {"f": 1.0, "n": 29}}}
        (self.agent / "model-scores.json").write_text(json.dumps(scores(one)))
        self.assertEqual(self.routes(rating={"score": 0.1}, random=0.9, requests=[{}]), [(SOL, "low")])

    # --- outcomes ---

    def test_the_owner_s_next_message_is_logged_as_the_outcome_of_the_model_that_answered(self):
        out = self.run_router(chain=True, random=0.9, requests=[
            {"rating": {"score": 0.1}},
            {"rating": {"score": 1.0, "failed": 0.9, "done": 0.05, "shipped": 0.02}, "user": SECRET_TEXT},
            {"rating": {"score": 1.0, "done": 0.95, "shipped": 0.9}, "user": "マージして"}])
        self.assertEqual(out["classified"][0]["questions"], ["level", "go"])  # nothing to judge before the first answer
        self.assertEqual(out["classified"][1]["questions"], ["level", "go", "failed", "done", "shipped"])
        outcomes = [e for e in self.log() if e.get("kind") == "outcome"]
        self.assertEqual([(e["model"], e["effort"], e["level"], e["failed"], e["done"], e["shipped"], e["ab"]) for e in outcomes],
                         [(f"openai/{SOL}", "low", "light", 0.9, 0.05, 0.02, True),
                          (f"openai/{SOL}", "high", "standard", 0, 0.95, 0.9, False)])
        self.assertNotIn(SECRET_TEXT, (self.agent / "jev-router.log.jsonl").read_text())

    # --- go-aheads, names, no classifier ---

    def test_a_go_ahead_goes_on_where_the_work_is(self):
        go = {"go": 0.9, "score": 0.1}
        cases = [(self.on(SOL, "high"), (SOL, "high"), None),
                 (self.on(OPUS, "xhigh", "hard"), (OPUS, "xhigh"), None),
                 (self.on(OPUS, "high"), (OPUS, "medium"), self.on(OPUS, "medium")),      # its best effort for the level
                 (self.on(FABLE, "max", "critical"), (FABLE, "high"), self.on(FABLE, "high", "deep")),
                 (self.on(TERRA, "medium", "light"), (TERRA, "medium"),                     # after a light exchange: routed as light
                  self.on(TERRA, "medium", "light", ab={"light": f"openai/{TERRA}:medium"})),
                 (self.on(TERRA, "max", "hard"), (FABLE, "low"), None),                    # Terra does not reach hard: a real choice
                 ({"model": "openai/gpt-9-nova", "effort": "high", "level": "standard"}, ("gpt-9-nova", "high"), None),  # no data on it
                 (None, (TERRA, "medium"), None)]
        for state, want, new_state in cases:
            with self.subTest(state=state):
                out = self.run_router(rating=go, requests=[{"user": "進めて", "state": state}])["routes"][0]
                self.assertEqual((out["id"], out["thinking"]), want)
                if new_state or (state and want == (state["model"].split("/")[1], state["effort"])):
                    self.assertEqual(out["state"], new_state)  # no new state where nothing changed

    def test_a_model_the_owner_asks_for_is_used_and_the_effort_written_after_its_name(self):
        cases = [("fable で考えて", {"score": 1.0}, (FABLE, "high")),          # Fable by name is at least deep
                 ("ここぞで", {"score": 3.8}, (FABLE, "max")),
                 ("Fable5.2mediumの意見ききたい", {"score": 3.8}, (FABLE, "medium")),
                 ("fable max で", {"score": 1.0}, (FABLE, "max")),
                 ("fable-5-2 high で", {"score": 3.8}, (FABLE, "high")),
                 ("fable で high-level な設計を", {"score": 3.8}, (FABLE, "max")),  # not an effort after the name
                 ("opus でお願い", {"score": 3.8}, (OPUS, "xhigh")),             # the default model, up to hard
                 ("opus でお願い", {"score": 1.0}, (OPUS, "medium")),
                 ("opus xhigh で", {"score": 1.0}, (OPUS, "xhigh")),
                 ("sol に聞いて", {"score": 1.0}, (SOL, "high")),
                 ("sol に聞いて", {"score": 3.0}, (SOL, "max")),                 # it does not reach deep: its best
                 ("haiku で要約", {"score": 1.0}, (HAIKU, "high")),
                 ("軽量で調べて", {"score": 1.0}, (HAIKU, "high"))]
        for text, rating, want in cases:
            with self.subTest(text=text, rating=rating):
                out = self.run_router(rating=dict(rating, asked=0.9), requests=[{"user": text, "state": self.on(SOL, "high")}])
                self.assertEqual((out["routes"][0]["id"], out["routes"][0]["thinking"]), want)
                self.assertIn("asked", out["classified"][0]["questions"])

    def test_a_model_that_is_only_the_topic_is_not_a_request(self):
        out = self.run_router(rating={"asked": 0.05, "score": 1.0},
                              requests=[{"user": "fableはmaxにする必要あるかな?", "state": self.on(SOL, "high")}])
        self.assertEqual((out["routes"][0]["id"], out["routes"][0]["thinking"]), (SOL, "high"))
        out = self.run_router(rating={"score": 1.0}, requests=[{"user": "状況は?"}])
        self.assertEqual(out["classified"][0]["questions"], ["level", "go"])  # asked only with a name

    def test_the_selector_low_stops_at_hard_and_max_leans_up(self):
        self.assertEqual(self.routes(rating={"score": 3.9}, requests=[{"level": "low"}]), [(FABLE, "low")])
        self.assertEqual(self.routes(rating={"asked": 0.9, "score": 3.9}, requests=[{"level": "low", "user": "fable で"}]), [(FABLE, "low")])
        self.assertEqual(self.routes(rating={"score": 2.3}, requests=[{"level": "high"}, {"level": "max"}]),
                         [(FABLE, "low"), (FABLE, "high")])

    def test_without_the_classifier_a_name_alone_decides_and_the_rest_stays(self):
        for scenario in ({"noClassifier": True}, {"classifierThrows": True}):
            with self.subTest(**scenario):
                self.assertEqual(self.routes(**scenario, requests=[
                    {}, {"state": self.on(SOL, "high")}, {"state": self.on(FABLE, "xhigh", "deep")},
                    {"previous": {"model": {"provider": "anthropic", "id": HAIKU}, "thinkingLevel": "low"}},
                    {"user": "fable で"}, {"user": "Fable5.2medium で"}, {"user": "opus で"}, {"user": "haiku で"}]),
                    [(OPUS, "medium"), (SOL, "high"), (FABLE, "xhigh"), (HAIKU, "high"),
                     (FABLE, "max"), (FABLE, "medium"), (OPUS, "medium"), (HAIKU, "high")])
        self.assertEqual([e for e in self.log() if e.get("kind") == "outcome"], [])

    def test_a_hanging_classifier_times_out_instead_of_blocking_the_turn(self):
        self.assertEqual(self.routes(timeout=20, hang=True, requests=[{"state": self.on(FABLE, "max", "critical")}]),
                         [(FABLE, "max")])

    def test_states_written_before_the_tiers_were_opened_up_are_understood(self):
        out = self.run_router(rating={"go": 0.9}, requests=[{"user": "進めて", "state": {"tier": "peak", "effort": "high", "level": "deep", "below": 1}}])
        self.assertEqual(out["routes"][0], {"id": FABLE, "thinking": "high", "state": self.on(FABLE, "high", "deep")})

    # --- the turn ---

    def test_tool_follow_ups_and_retries_stay_on_the_model_of_the_turn(self):
        prev = {"model": {"provider": "anthropic", "id": FABLE}, "thinkingLevel": "max"}
        failed = {"model": {"provider": "anthropic", "id": HAIKU}, "thinkingLevel": "high",
                  "message": {"stopReason": "error", "errorMessage": "overloaded"}}
        out = self.run_router(rating={"score": 0.1}, requests=[{"reason": "continuation", "previous": prev},
                                                              {"reason": "retry", "failed": failed, "previous": prev}])
        self.assertEqual([(r["id"], r["thinking"]) for r in out["routes"]], [(FABLE, "max"), (HAIKU, "high")])
        self.assertEqual(out["classified"], [])

    def test_requests_outside_the_loop_use_the_default_tier(self):
        self.assertEqual(self.routes(rating={"score": 4}, requests=[{"reason": "direct"}]), [(OPUS, "medium")])

    def test_without_the_peak_model_the_best_score_there_is_and_without_the_default_an_error(self):
        self.assertEqual(self.routes(rating={"score": 3.0}, noAuth=[FABLE], requests=[{}]), [(OPUS, "max")])
        out = self.run_router(rating={"score": 3.0}, noAuth=[OPUS], requests=[{}])
        self.assertIn("no credentials", out["routes"][0]["error"])

    def test_the_state_and_the_log_hold_the_decision_and_never_the_text(self):
        long_text = SECRET_TEXT + "x" * 20_000
        out = self.run_router(rating={"score": 1.0}, requests=[{"user": long_text, "assistant": "y" * 5_000,
                                                                "state": self.on(TERRA, "medium", "light"), "tokens": 1234}])
        self.assertEqual(out["routes"][0], {"id": SOL, "thinking": "high", "state": self.on(SOL, "high")})
        self.assertEqual(out["statuses"][-1], ["jev-router", "auto→gpt-6.1-sol high"])
        state = out["classified"][0]["state"]
        self.assertEqual(sorted(state), ["owner_message", "previous_answer_tail"])
        self.assertEqual(len(state["owner_message"]), 6_000)
        self.assertEqual(len(state["previous_answer_tail"]), 1_500)
        self.assertNotIn(SECRET_TEXT, (self.agent / "jev-router.log.jsonl").read_text())
        entry = [e for e in self.log() if "kind" not in e][-1]
        self.assertEqual((entry["model"], entry["effort"], entry["level"], entry["from"], entry["source"], entry["score"], entry["tokens"]),
                         (f"openai/{SOL}", "high", "standard", f"openai/{TERRA}", "classifier", 1.0, 1234))

    # --- a used-up subscription ---

    @staticmethod
    def quota(used=0.95, window="5h", reset=1_800_003_600):
        headers = {f"anthropic-ratelimit-unified-{window}-utilization": str(used)}
        if reset is not None:
            headers[f"anthropic-ratelimit-unified-{window}-reset"] = str(reset)
        return {"headers": headers}

    DEEP = {"score": 3.0}  # Fable high; without Claude nothing reaches deep, and the best score left is Astra max

    def test_95_percent_in_either_claude_window_leaves_claude_out(self):
        for window in ("5h", "7d"):
            for used, want in ((0.94999, (FABLE, "high")), (0.95, (ASTRA, "max")), (1.0, (ASTRA, "max"))):
                with self.subTest(window=window, used=used):
                    (self.agent / "jev-claude-quota.json").unlink(missing_ok=True)
                    self.assertEqual(self.routes(rating=self.DEEP, requests=[{"responses": [self.quota(used, window)]}]), [want])
        out = self.run_router(rating={"score": 2.0}, requests=[{"responses": [self.quota()]}])
        self.assertEqual((out["routes"][0]["id"], out["routes"][0]["thinking"]), (SOL, "max"))  # hard: the best total that reaches it
        self.assertEqual(out["routes"][0]["state"]["detour"], True)
        self.assertTrue(any("利用枠" in n for n in out["notices"]))

    def test_the_level_is_kept_and_claude_is_back_after_the_reset_on_a_new_user_message(self):
        out = self.run_router(chain=True, requests=[
            {"rating": {"score": 3.9}, "responses": [self.quota()]},
            {"rating": {"score": 3.0}},
            {"reason": "continuation", "now": 1_800_003_601_000},
            {"user": "進めて", "rating": {"go": 0.9}},
        ])["routes"]
        self.assertEqual([(r["id"], r["thinking"]) for r in out],
                         [(ASTRA, "max"), (ASTRA, "max"), (ASTRA, "max"), (FABLE, "high")])
        self.assertEqual(out[0]["state"]["level"], "critical")
        self.assertEqual(out[-1]["state"], self.on(FABLE, "high", "deep"))

    def test_missing_or_old_headers_do_not_end_it_and_all_high_windows_must_reset(self):
        self.assertEqual(self.routes(chain=True, rating=self.DEEP, requests=[
            {"responses": [self.quota(window="5h"), self.quota(window="7d", reset=1_800_007_200)]},
            {"now": 1_800_001_000_000, "responses": [{"headers": {}}]},  # more than five minutes, not recovery
            {"now": 1_800_003_601_000},  # 5h reset, 7d still high
            {"now": 1_800_007_201_000},
        ]), [(ASTRA, "max"), (ASTRA, "max"), (ASTRA, "max"), (FABLE, "high")])

    def test_new_low_headers_replace_only_the_window_they_report(self):
        self.assertEqual(self.routes(chain=True, rating=self.DEEP, requests=[
            {"responses": [self.quota(window="5h"), self.quota(window="7d")]},
            {"now": 1_800_000_001_000, "responses": [self.quota(0.2, "5h")]},
            {"now": 1_800_000_002_000, "responses": [self.quota(0.3, "7d")]},
        ]), [(ASTRA, "max"), (ASTRA, "max"), (FABLE, "high")])

    def test_quota_survives_restart_and_never_stores_raw_headers(self):
        q = self.quota()
        q["headers"]["authorization"] = SECRET_TEXT
        self.assertEqual(self.routes(rating=self.DEEP, requests=[{"responses": [q]}]), [(ASTRA, "max")])
        self.assertNotIn(SECRET_TEXT, (self.agent / "jev-claude-quota.json").read_text())
        self.assertNotIn(SECRET_TEXT, (self.agent / "jev-router.log.jsonl").read_text())
        self.assertEqual(self.routes(rating=self.DEEP, requests=[{}]), [(ASTRA, "max")])

    def test_a_window_used_ahead_of_its_time_makes_its_models_dearer(self):
        # 7d reset 4 days away (3/7 elapsed). Fable's own window 7d_oi at 0.78: 1.82x pace -> 3.3x cost -> Fable low
        # (2.26e8 / 3.3^2 = 2.1e7) falls behind Sol max (6.0e7) for hard. The account window at 0.40 is behind pace: nothing.
        reset = 1_800_000_000 + 4 * 86400
        fable = {"model": FABLE, "headers": {"anthropic-ratelimit-unified-7d-utilization": "0.40", "anthropic-ratelimit-unified-7d-reset": str(reset),
                                             "anthropic-ratelimit-unified-7d_oi-utilization": "0.78", "anthropic-ratelimit-unified-7d_oi-reset": str(reset),
                                             "anthropic-ratelimit-unified-7d_oi-surpassed-threshold": "0.75"}}
        self.assertEqual(self.routes(rating={"score": 2.0}, requests=[{}]), [(FABLE, "low")])
        self.assertEqual(self.routes(rating={"score": 2.0}, requests=[{"responses": [fable]}, {}]), [(SOL, "max"), (SOL, "max")])
        cache = json.loads((self.agent / "jev-claude-quota.json").read_text())["windows"]
        self.assertEqual((cache["7d_oi"]["model"], "model" in cache["7d"]), (FABLE, False))
        entry = [e for e in self.log() if "kind" not in e][-1]
        self.assertEqual(entry["model"], f"openai/{SOL}")
        # Opus is not held by Fable's window: without GPT, standard is Opus medium, with no pace on it.
        self.assertEqual(self.routes(rating={"score": 1.0}, noAuth=[SOL, TERRA, ASTRA, LUNA], requests=[{}]), [(OPUS, "medium")])
        self.assertNotIn("pace", self.log()[-1])
        self.assertEqual(self.routes(rating={"score": 2.0}, noAuth=[SOL, TERRA, ASTRA, LUNA], requests=[{}]), [(FABLE, "low")])
        self.assertAlmostEqual(self.log()[-1]["pace"], (0.78 / (3 / 7)) ** 2, places=2)
        # On pace or behind: no change. Far ahead: at most PACE_MAX.
        (self.agent / "jev-claude-quota.json").unlink()
        on_pace = {"model": FABLE, "headers": {"anthropic-ratelimit-unified-7d_oi-utilization": "0.42", "anthropic-ratelimit-unified-7d_oi-reset": str(reset)}}
        self.assertEqual(self.routes(rating={"score": 2.0}, requests=[{"responses": [on_pace]}]), [(FABLE, "low")])

    def test_a_model_s_own_window_at_95_percent_leaves_out_that_model_only(self):
        spent = {"model": FABLE, "headers": {"anthropic-ratelimit-unified-7d_oi-utilization": "0.95",
                                             "anthropic-ratelimit-unified-7d_oi-reset": "1800003600"}}
        out = self.run_router(rating=self.DEEP, requests=[{"responses": [spent]}, {"rating": {"score": 2.0}}])
        # deep: nothing reaches it without Fable, so the best score left (Opus max); hard: Sol max as before Fable's window
        self.assertEqual([(r["id"], r["thinking"]) for r in out["routes"]], [(OPUS, "max"), (SOL, "max")])
        self.assertEqual(self.log()[0]["quota"], [f"{FABLE} 7d_oi"])
        self.assertNotIn("detour", out["routes"][0]["state"])  # Claude itself is still there
        self.assertEqual(self.routes(rating=self.DEEP, requests=[{"now": 1_800_003_601_000}]), [(FABLE, "high")])  # after the reset

    def test_only_confirmed_pi_anthropic_subscription_responses_are_quota_evidence(self):
        for scenario, response in [({}, dict(self.quota(), provider="openai", model=SOL)),
                                   ({}, dict(self.quota(), stream=False)),
                                   ({"apiKeyProviders": ["anthropic"]}, self.quota()),
                                   ({"notSubscriptionProviders": ["anthropic"]}, self.quota())]:
            with self.subTest(scenario=scenario, response=response):
                self.assertEqual(self.routes(rating=self.DEEP, **scenario, requests=[{"responses": [response]}]), [(FABLE, "high")])
        self.assertFalse((self.agent / "jev-claude-quota.json").exists())

    def test_invalid_usage_values_are_not_evidence(self):
        for value in ("", " ", "NaN", "Infinity", "95", "-0.1", "1.01", "0x1"):
            with self.subTest(value=value):
                q = self.quota()
                q["headers"]["anthropic-ratelimit-unified-5h-utilization"] = value
                self.assertEqual(self.routes(rating=self.DEEP, requests=[{"responses": [q]}]), [(FABLE, "high")])
        self.assertFalse((self.agent / "jev-claude-quota.json").exists())

    def test_a_used_up_subscription_never_becomes_a_paid_api_or_a_way_back_to_claude(self):
        gpt = [SOL, TERRA, ASTRA, LUNA]
        for scenario in ({"apiKeyProviders": ["openai"]}, {"noAuth": gpt}, {"notSubscriptionProviders": ["openai"]}):
            for request in ({}, {"user": "sol で"}, {"reason": "direct"}):
                with self.subTest(scenario=scenario, request=request):
                    route = self.run_router(**scenario, requests=[dict(request, responses=[self.quota()])])["routes"][0]
                    self.assertIn("no API fallback", route["error"])

    def test_an_unknown_reset_stays_out_and_a_lost_cache_is_not_recovery(self):
        self.assertEqual(self.routes(chain=True, rating=self.DEEP, requests=[
            {"responses": [self.quota(reset=None)]}, {"now": 1_900_000_000_000},
        ]), [(ASTRA, "max"), (ASTRA, "max")])
        (self.agent / "jev-claude-quota.json").unlink()
        state = {"model": f"openai/{ASTRA}", "effort": "max", "level": "deep", "detour": True}
        self.assertEqual(self.routes(noClassifier=True, requests=[{"state": state}]), [(ASTRA, "max")])
        self.assertEqual(self.routes(rating=self.DEEP, requests=[{"state": state}]), [(ASTRA, "max")])

    def test_unknown_or_future_cache_is_not_a_measured_quota(self):
        cache = self.agent / "jev-claude-quota.json"
        for contents in ("not JSON", json.dumps({"source": "claude-code", "windows": {"5h": {"used": 1, "at": 1_800_000_000_000}}}),
                         json.dumps({"source": "pi-anthropic-subscription-v1", "windows": {"5h": {"used": 1, "at": 1_800_000_001_000}}})):
            with self.subTest(contents=contents):
                cache.write_text(contents)
                self.assertEqual(self.routes(rating=self.DEEP, requests=[{}]), [(FABLE, "high")])

    def test_quota_overrides_claude_names_and_still_works_without_the_classifier(self):
        self.assertEqual(self.routes(noClassifier=True, requests=[{"user": "fable max で", "responses": [self.quota()]}]),
                         [(ASTRA, "max")])

    def test_quota_moves_compaction_and_tool_follow_ups_but_not_arbitrary_failed_retries(self):
        prev = {"model": {"provider": "anthropic", "id": OPUS}, "thinkingLevel": "high"}
        self.assertEqual(self.routes(requests=[
            {"reason": "direct", "responses": [self.quota()]},
            {"reason": "continuation", "previous": prev},
            {"reason": "retry", "failed": dict(prev, message={"stopReason": "error", "errorMessage": "401 unauthorized"})},
            {"reason": "retry", "failed": dict(prev, message={"stopReason": "error", "errorMessage": "overloaded"})},
        ]), [(SOL, "high"), (SOL, "high"), (OPUS, "high"), (OPUS, "high")])

    def test_only_an_explicit_subscription_cap_moves_a_retry_and_either_provider_can_be_the_one(self):
        def failed(model, message):
            return {"model": {"provider": AA[model][0], "id": model}, "thinkingLevel": "high",
                    "message": {"stopReason": "error", "errorMessage": message}}
        self.assertEqual(self.routes(requests=[
            {"reason": "retry", "failed": failed(OPUS, "429 rate_limit_error: too many requests")},
            {"reason": "retry", "failed": failed(OPUS, "429 usage limit reached. Try again later.")},
        ]), [(OPUS, "high"), (SOL, "high")])
        # The error carries no reset: Claude is tried again an hour later.
        self.assertEqual(self.routes(rating=self.DEEP, requests=[{"now": 1_800_000_000_000 + 3_599_000},
                                                                  {"now": 1_800_000_000_000 + 3_601_000}]),
                         [(ASTRA, "max"), (FABLE, "high")])
        (self.agent / "jev-claude-quota.json").unlink()
        for message in ("401 unauthorized: usage limit reached", "billing: usage limit reached", "permission denied",
                        "Safety policy denied", "cancelled", "overloaded", "429 rate_limit_error"):
            with self.subTest(message=message):
                self.assertEqual(self.routes(requests=[{"reason": "retry", "failed": failed(OPUS, message)}]), [(OPUS, "high")])
        # OpenAI sends no reset: it is left out for an hour, then tried again.
        self.assertEqual(self.routes(rating={"score": 1.0}, requests=[
            {"reason": "retry", "failed": failed(SOL, "subscription_sharing_usage_limit_exceeded")},
            {"now": 1_800_000_000_000 + 3_599_000},
            {"now": 1_800_000_000_000 + 3_601_000},
        ]), [(FABLE, "low"), (FABLE, "low"), (SOL, "high")])


def load_radar(state=None):
    import importlib.machinery, importlib.util
    path = str(ROOT / "home/dot_local/bin/executable_model-radar")
    loader = importlib.machinery.SourceFileLoader("model_radar", path)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader("model_radar", loader))
    loader.exec_module(module)
    module.catalog = lambda: set(AA)  # never start Pi from a test
    if state:
        module.STATE, module.BENCH_FILE, module.QUOTA = str(state), str(Path(state) / "bench.jsonl"), str(Path(state) / "quota.json")
    return module


def aa_row(slug, name, score, cost=1.0, seconds=10.0):
    return {"slug": slug, "name": name, "release_date": "2026-09-22",
            "evaluations": {"artificial_analysis_intelligence_index": score},
            "artificial_analysis_intelligence_index_cost": {"cost_per_task": {"total_cost": cost}},
            "performance": {"median_end_to_end_response_time_seconds": seconds},
            "pricing": {"price_1m_input_tokens": 4, "price_1m_output_tokens": 20, "price_1m_cache_write_tokens": 5}}


def outcome(model, effort, level, failed=0.0, done=0.0, shipped=0.0):
    return {"kind": "outcome", "model": f"{AA[model][0]}/{model}", "effort": effort, "level": level,
            "failed": failed, "done": done, "shipped": shipped, "ab": True}


MEDIAN_FIX = ("return (s[mid] + s[mid + 1]) / 2", "return (s[mid - 1] + s[mid]) / 2")
PERCENTILE_FIX = ("return s[int(len(s) * p / 100)]", "import math\n    return s[max(0, math.ceil(len(s) * p / 100) - 1)]")
AVERAGE_FIX = ("range(len(values) - window)", "range(len(values) - window + 1)")
DURATION = """import re
def parse_duration(text):
    m = re.fullmatch(r"(?:(\\d+)d)? ?(?:(\\d+)h)? ?(?:(\\d+)m)? ?(?:(\\d+)s)?", text.strip())
    if not m or not any(g is not None for g in m.groups()) or "  " in text.strip():
        raise ValueError(text)
    d, h, mi, s = (int(g or 0) for g in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s
"""


class ModelRadar(unittest.TestCase):
    """model-radar makes the file jev-router.ts reads. No network, no model: Pi is replaced by a function."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state = Path(tmp.name)
        self.radar = load_radar(self.state)

    def test_aa_slugs_become_pi_ids_and_efforts_and_only_the_newest_version_stays(self):
        snap = self.radar.build_aa([
            aa_row("claude-opus-5-5-medium", "Claude Opus 5.5 (Medium, Default Fallback)", 48.2, 2.45),
            aa_row("claude-opus-5-5", "Claude Opus 5.5 (Max, Default Fallback)", 59.1, 10.04),
            aa_row("claude-opus-5", "Claude Opus 5 (Max)", 50.0),
            aa_row("gpt-6-1-sol-xhigh", "GPT-6.1 Sol (Xhigh)", 52.5, 0.76),
            aa_row("gpt-6-1-terra-non-reasoning", "GPT-6.1 Terra (Non-reasoning)", 30.5),
            aa_row("gpt-6-sol-daybreak-blue", "GPT-6 Sol (Daybreak Blue, max)", 40.0),
            aa_row("gemini-4-carbon", "Gemini 4 Carbon (High)", 60.0),
        ], "2026-11-15T00:00:00+00:00")
        self.assertEqual(sorted(snap["models"]), ["claude-opus-5-5", "gpt-6.1-sol"])
        self.assertEqual(snap["models"]["claude-opus-5-5"]["efforts"],
                         {"medium": {"score": 48.2, "cost": 2.45, "seconds": 10.0}, "max": {"score": 59.1, "cost": 10.04, "seconds": 10.0}})
        self.assertEqual((snap["models"]["gpt-6.1-sol"]["in_pi"], snap["models"]["gpt-6.1-sol"]["provider"]), (True, "openai"))
        self.assertEqual(snap["models"]["claude-opus-5-5"]["price"]["cache_write"], 5)

    def test_the_report_s_choice_is_the_router_s(self):
        radar, snap = self.radar, scores()
        picks = {lv: radar.choice(snap, TIERS, lv) for lv in radar.LEVELS}
        self.assertEqual(picks, {"light": (TERRA, "medium", (SOL, "low")), "standard": (SOL, "high", None),
                                 "hard": (FABLE, "low", (FABLE, "medium")), "deep": (FABLE, "high", None), "critical": (FABLE, "max", None)})
        self.assertAlmostEqual(radar.AB_RATIO, (1.1 / 0.9) ** 6)
        spare = dict(TIERS, scarce={FABLE: {"cost_factor": 2, "max_effort": "high"}})
        self.assertEqual([radar.choice(snap, spare, lv) for lv in ("hard", "deep", "critical")],
                         [(SOL, "max", (FABLE, "low")), (FABLE, "high", None), (FABLE, "high", None)])
        page = radar.report(radar.compose(snap, {}, {}), TIERS)
        for text in ("jev/auto の選び方", "<svg", "A/B テスト中", "あなたの成果スコア"):
            self.assertIn(text, page)
        case = PiRouter("test_registers_jev_auto_only_with_tier_data")
        case.setUp()
        try:  # the router at the start of a conversation: the same pairs; with the other draw, the rivals
            first = [case.routes(rating={"score": sc}, random=0, requests=[{}])[0] for sc in (0.2, 1.0, 2.0, 3.0, 3.9)]
            second = [case.routes(rating={"score": sc}, random=0.9, requests=[{}])[0] for sc in (0.2, 2.0)]
        finally:
            case.doCleanups()
        self.assertEqual(first, [picks[lv][:2] for lv in radar.LEVELS])
        self.assertEqual(second, [picks["light"][2], picks["hard"][2]])

    def test_outcomes_become_the_owner_s_factor_per_level(self):
        radar = self.radar
        self.assertEqual(radar.learn([outcome(SOL, "high", "standard", done=0.9)] * 3), {})  # too little to tell a rate
        events = ([outcome(SOL, "high", "standard", failed=0.9)] * 8 + [outcome(SOL, "high", "standard", done=0.9)] * 4
                  + [outcome(FABLE, "low", "standard", done=0.9, shipped=0.9)] * 6 + [outcome(FABLE, "low", "standard", done=0.9)] * 6
                  + [outcome(FABLE, "low", "hard", done=0.9)] * 10 + [{"model": "x", "effort": "y", "level": "standard"}]
                  + [outcome(OPUS, "medium", "standard", done=0.2, failed=0.1)] * 3)
        got = radar.learn(events)
        sol, fable, opus = got[(SOL, "high")]["standard"], got[(FABLE, "low")]["standard"], got[(OPUS, "medium")]["standard"]
        self.assertLess(sol["f"], 1)
        self.assertGreater(fable["f"], 1)
        self.assertTrue(all(radar.F_MIN <= f["f"] <= radar.F_MAX for f in (sol, fable, opus)))
        self.assertEqual((sol["n"], fable["n"], opus["n"]), (12, 12, 0))  # judged: the message said something about the answer
        self.assertAlmostEqual(fable["good"], 6 * 1.8 + 6 * 0.9)  # a result put to use counts double
        self.assertAlmostEqual(sol["bad"], 8 * 1.8)                # and a failure double against
        self.assertEqual(got[(FABLE, "low")]["hard"]["f"], 1.0)    # alone at its level: nothing to compare with
        # Twenty good answers beside a pair that fails one time in five move the factor a little: the prior holds it back.
        mild = radar.learn([outcome(SOL, "high", "standard", done=1.0)] * 20
                           + [outcome(OPUS, "medium", "standard", done=1.0)] * 8 + [outcome(OPUS, "medium", "standard", failed=1.0)] * 2)
        self.assertAlmostEqual(mild[(SOL, "high")]["standard"]["f"], 1.0312, places=3)
        self.assertAlmostEqual(mild[(OPUS, "medium")]["standard"]["f"], 0.9609, places=3)
        # A pair that always fails beside one that never does: both at the bound.
        far = radar.learn([outcome(SOL, "high", "standard", done=1.0)] * 20 + [outcome(OPUS, "medium", "standard", failed=1.0)] * 10)
        self.assertEqual((far[(SOL, "high")]["standard"]["f"], far[(OPUS, "medium")]["standard"]["f"]), (radar.F_MAX, radar.F_MIN))

    def test_the_benchmark_s_tasks_fail_as_given_and_pass_when_solved(self):
        tasks = {t["name"]: t for t in self.radar.tasks()}
        solved = {"bugfix": {"stats.py": self.radar.STATS.replace(*MEDIAN_FIX).replace(*PERCENTILE_FIX).replace(*AVERAGE_FIX)},
                  "lookup": {"answer.txt": "auth,queue\n"}, "implement": {"duration.py": DURATION}}
        # Half done: one of three bugs, every dependency without the owner filter, upper case accepted.
        half = {"bugfix": {"stats.py": self.radar.STATS.replace(*MEDIAN_FIX)}, "lookup": {"answer.txt": "auth,queue,shipping\n"},
                "implement": {"duration.py": DURATION.replace("text.strip())", "text.strip().lower())", 1)}}
        for name, task in tasks.items():
            for label, extra, want in (("as given", {}, False), ("half done", half[name], False), ("solved", solved[name], True)):
                with self.subTest(task=name, state=label), tempfile.TemporaryDirectory() as d:
                    for rel, text in {**task["files"], **extra}.items():
                        (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
                        (Path(d) / rel).write_text(text)
                    self.assertEqual(task["check"](d), want)

    def test_a_benchmark_run_measures_pi_and_keeps_our_key_out_of_it(self):
        radar, seen = self.radar, {}

        def pi(cmd, cwd, env, **kwargs):
            seen.update(cmd=cmd, env=env, kwargs=kwargs)
            (Path(cwd) / "answer.txt").write_text("auth, queue\n")
            end = lambda cost, **m: json.dumps({"type": "message_end", "message": {"role": "assistant", "usage": {"cost": {"total": cost}}, **m}})
            return subprocess.CompletedProcess(cmd, 0, stdout="\n".join(["not json", end(0.02), json.dumps({"type": "tool"}), end(0.03)]), stderr="")
        os.environ["ARTIFICIAL_ANALYSIS_API_KEY"] = "SYNTHETIC-KEY"
        self.addCleanup(os.environ.pop, "ARTIFICIAL_ANALYSIS_API_KEY", None)
        lookup = [t for t in radar.tasks() if t["name"] == "lookup"][0]
        r = radar.run_task(lookup, "openai", SOL, "high", pi)
        self.assertEqual((r["passed"], r["cost"], "error" in r), (True, 0.05, False))
        self.assertIn(f"openai/{SOL}:high", seen["cmd"])
        self.assertIn("-ne", seen["cmd"])            # no notifications, router or MCP in the measured Pi
        self.assertNotIn("--no-session", seen["cmd"])  # the run stays on record
        self.assertNotIn("SYNTHETIC-KEY", json.dumps(seen["env"]))
        self.assertEqual(seen["env"]["CLAUDE_NOTIFY_PHONE"], "never")
        failing = lambda cmd, cwd, env, **k: subprocess.CompletedProcess(cmd, 0, stderr="", stdout=json.dumps(
            {"type": "message_end", "message": {"role": "assistant", "stopReason": "error", "errorMessage": "usage limit reached"}}))
        self.assertEqual(radar.run_task(lookup, "openai", SOL, "high", failing)["error"], "usage limit reached")

        def hangs(cmd, **k):
            raise subprocess.TimeoutExpired(cmd, 1)
        self.assertEqual(radar.run_task(lookup, "openai", SOL, "high", hangs)["error"], "timeout")

    def test_only_close_races_between_models_are_measured_and_each_pair_once(self):
        radar, snap = self.radar, scores()
        names = sorted(t["name"] for t in radar.tasks())
        want = radar.bench_candidates(snap, TIERS, {})
        pairs = [(m, e) for m, e, _ in want]
        for pair in [(TERRA, "medium"), (SOL, "low"), (SOL, "high"), (FABLE, "low"), (SOL, "max"), (OPUS, "medium"), (HAIKU, "high")]:
            self.assertIn(pair, pairs)
        for pair in [(FABLE, "high"), (FABLE, "max"), (FABLE, "xhigh"), (LUNA, "max"), (OPUS, "max")]:  # one model in the race, or far behind
            self.assertNotIn(pair, pairs)
        self.assertTrue(all(missing == names for _, _, missing in want))
        runs = []

        def pi(cmd, cwd, env, **kwargs):
            runs.append(cmd[cmd.index("--model") + 1])
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"type": "message_end", "message": {"role": "assistant", "usage": {"cost": {"total": 0.01}}}}), stderr="")
        self.assertEqual(radar.run_bench(snap, TIERS, max_runs=4, runner=pi, out=lambda *_: None), 4)
        self.assertEqual(len(runs), 4)
        stats = radar.bench_stats(radar.lines(radar.BENCH_FILE))
        first = pairs[0]
        self.assertEqual((stats[first]["n"], stats[first]["pass"]), (3, 0))  # the stub solved nothing
        again = radar.bench_candidates(snap, TIERS, stats)
        self.assertNotIn(first, [(m, e) for m, e, _ in again])              # measured: not run again
        self.assertEqual(again[0][2], names[1:])                             # the second pair lacks the tasks not run yet
        # Claude pairs wait while Claude's quota is high; a cap error stops a provider for this run.
        (self.state / "quota.json").write_text(json.dumps({"windows": {"7d": {"used": 0.85, "at": 1}}}))
        runs.clear()
        radar.run_bench(snap, TIERS, max_runs=50, runner=pi, out=lambda *_: None)
        self.assertTrue(runs and all(r.startswith("openai/") for r in runs))

    def test_measurements_correct_cost_and_speed_only_with_three_pairs_and_a_failing_pair_is_left_out(self):
        radar, snap = self.radar, scores()
        names = [t["name"] for t in radar.tasks()]
        run = lambda n_pass, cost, seconds: {"n": 3, "pass": n_pass, "cost": cost, "seconds": seconds, "tasks": names}
        two = radar.compose(snap, {(SOL, "high"): run(3, 0.05, 100), (OPUS, "medium"): run(3, 0.2, 50)}, {})
        self.assertIsNone(two["bench_scale"])
        self.assertEqual(two["models"][SOL]["efforts"]["high"]["cost"], 0.591)   # AA's
        bench = {(SOL, "high"): run(3, 0.0591, 258.0), (OPUS, "medium"): run(3, 0.24511, 23.9), (FABLE, "low"): run(1, 0.30972, 11.3),
                 (TERRA, "medium"): {"n": 1, "pass": 1, "cost": 9, "seconds": 9, "tasks": names[:1]}}
        three = radar.compose(snap, bench, {(SOL, "high"): {"standard": {"f": 0.95, "n": 7, "good": 3, "bad": 4}}})
        sol = three["models"][SOL]["efforts"]["high"]
        # Every pair costs a tenth of AA's here, and Sol alone is five times slower: the scale takes the common part out.
        self.assertAlmostEqual(sol["cost"], 0.591, places=2)
        self.assertAlmostEqual(sol["seconds"] / three["models"][OPUS]["efforts"]["medium"]["seconds"], (258.0 / 51.6) * 51.6 / 23.9, places=1)
        self.assertEqual((sol["aa_cost"], sol["aa_seconds"], sol["bench"]["pass"], sol["owner"]["standard"]["n"]), (0.591, 51.6, 3, 7))
        self.assertTrue(three["models"][FABLE]["efforts"]["low"]["excluded"])      # 1 of 3
        self.assertNotIn("excluded", three["models"][TERRA]["efforts"]["medium"])  # not run in full: no verdict, AA's values
        self.assertEqual(three["models"][TERRA]["efforts"]["medium"]["cost"], 0.1688)
        self.assertEqual(radar.choice(three, TIERS, "hard")[:2], (FABLE, "medium"))  # the failing pair is out of the race
        (self.state / "bench.jsonl").write_text("\n".join(json.dumps(r) for r in [
            {"at": 1, "v": radar.BENCH_VERSION, "model": SOL, "effort": "high", "task": "lookup", "passed": True, "seconds": 9, "cost": 1},   # too old
            {"at": 2e9, "v": 0, "model": SOL, "effort": "high", "task": "lookup", "passed": True, "seconds": 9, "cost": 1},                    # other tasks
            {"at": 2e9, "v": radar.BENCH_VERSION, "model": SOL, "effort": "high", "task": "lookup", "passed": False, "seconds": 9, "cost": 1, "error": "quota"},
            {"at": 2e9, "v": radar.BENCH_VERSION, "model": SOL, "effort": "high", "task": "bugfix", "passed": False, "seconds": 30, "cost": 0.5},
            {"at": 2e9 + 1, "v": radar.BENCH_VERSION, "model": SOL, "effort": "high", "task": "bugfix", "passed": True, "seconds": 20, "cost": 0.3}])
            + "\nnot json\n")
        self.assertEqual(radar.bench_stats(radar.lines(radar.BENCH_FILE), now=2e9 + 5),
                         {(SOL, "high"): {"n": 1, "pass": 1, "cost": 0.3, "seconds": 20.0, "tasks": ["bugfix"]}})


@unittest.skipUnless(shutil.which("chezmoi") or os.environ.get("CI"), "chezmoi が必要")
class TierFile(unittest.TestCase):
    def test_the_tier_file_carries_the_four_tiers_and_the_owner_s_weights(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "c.toml").write_text("")
            proc = subprocess.run([shutil.which("chezmoi"), "--source", str(ROOT / "home"), "--config", str(Path(tmp) / "c.toml"),
                                   "--persistent-state", str(Path(tmp) / "s.db"), "execute-template", "--file",
                                   str(ROOT / "home/dot_pi/agent/model-tiers.json.tmpl")],
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        data = json.loads(proc.stdout)
        self.assertEqual(sorted(data), ["default", "light", "peak", "scarce", "strong", "weights"])
        self.assertEqual(data["scarce"], {FABLE: {"cost_factor": 2, "max_effort": "high"}})  # the owner, 2026-11-15
        self.assertEqual(data["weights"], {"intelligence": 6, "cost": 2, "speed": 1})
        self.assertEqual((data["default"]["id"], data["default"]["thinking"]), (OPUS, "medium"))  # the owner's base (2026-11-15)
        for tier in ("default", "strong", "peak", "light"):
            self.assertEqual(sorted(data[tier]), ["id", "provider", "thinking"])


if __name__ == "__main__":
    unittest.main()
