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
OPUS, FABLE, HAIKU, SOL = "claude-opus-5-5", "claude-fable-5-2", "claude-haiku-5-5", "gpt-6.1-sol"
HARNESS = r'''
const s = JSON.parse(process.argv[2]);
const virtual = [], notices = [], statuses = [], classified = [], handlers = {};
const pi = { registerVirtualModel: (d) => virtual.push(d),
  on: (name, fn) => { (handlers[name] ??= []).push(fn); } };
let request;
let clock = s.now ?? 1_800_000_000_000;
Date.now = () => clock;
const ctx = {
  hasUI: true,
  ui: {notify: (m) => notices.push(m), setStatus: (k, v) => statuses.push([k, v])},
  modelRegistry: {
    find: (provider, id) => ({provider, id}),
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
      return {stopReason: "stop", answers: {
        level: {type: "score", score: r.score ?? 1, confidence: 1},
        go: {type: "bool", probability: r.go ?? 0},
        ...(input.questions.asked ? {asked: {type: "bool", probability: r.asked ?? 1}} : {})}};
    },
  },
};
(await import('./jev-router.ts')).default(pi);
const out = {registered: virtual.map((v) => `${v.provider}/${v.id}`), notices, statuses, classified, routes: []};
let state, previous;
for (const r of s.requests ?? []) {
  request = r;
  if (r.now !== undefined) clock = r.now;
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

    def test_registers_jev_auto_only_with_tier_data(self):
        self.assertEqual(self.run_router()["registered"], ["jev/auto"])
        (self.agent / "model-tiers.json").write_text('{"default": {}}')
        self.assertEqual(self.run_router()["registered"], [])
        (self.agent / "model-tiers.json").unlink()
        self.assertEqual(self.run_router()["registered"], [])

    def test_the_score_picks_the_level_and_the_level_the_lowest_effort_that_reaches_its_score(self):
        on_default = {"tier": "default", "effort": "high", "level": "standard"}
        cases = [(0.2, None, (HAIKU, "high")),        # light where nothing is cached: the light tier, 30
                 (0.2, on_default, (OPUS, "low")),    # light later: the model in use, the lowest effort over 30
                 (0.49, on_default, (OPUS, "low")),
                 (0.5, on_default, (OPUS, "high")),   # standard: 52, the default bar
                 (1.49, on_default, (OPUS, "high")),
                 (1.5, on_default, (OPUS, "xhigh")),  # hard: 52 + 5
                 (2.49, on_default, (OPUS, "xhigh")),
                 (2.5, on_default, (FABLE, "high")),  # deep: more than Opus reaches at any effort (59)
                 (3.49, on_default, (FABLE, "high")),
                 (3.5, on_default, (FABLE, "max")),   # critical: the best of the peak model
                 (4.0, None, (FABLE, "max"))]
        for score, state, want in cases:
            with self.subTest(score=score, state=state):
                out = self.run_router(rating={"score": score}, requests=[{"state": state}])["routes"][0]
                self.assertEqual((out["id"], out["thinking"]), want)

    def test_the_selector_low_never_uses_the_peak_model_and_max_leans_up(self):
        self.assertEqual(self.routes(rating={"score": 3.9}, requests=[{"level": "low"}]), [(OPUS, "xhigh")])
        # Fable by name is at least deep; without the peak model that is the highest rung of the default model
        self.assertEqual(self.routes(rating={"asked": 0.9}, requests=[{"level": "low", "user": "fable で"}]),
                         [(OPUS, "xhigh")])
        self.assertEqual(self.routes(rating={"score": 2.3}, requests=[{"level": "high"}, {"level": "max"}]),
                         [(OPUS, "xhigh"), (FABLE, "high")])

    def test_a_light_message_changes_the_model_only_where_nothing_is_cached(self):
        light = {"rating": {"score": 0.1}}
        # a session that starts light stays there, and goes up when the work needs it
        self.assertEqual(self.routes(chain=True, requests=[light, light, {"rating": {"score": 1.0}}, light]),
                         [(HAIKU, "high"), (HAIKU, "high"), (OPUS, "high"), (OPUS, "low")])
        # a session that came to jev/auto from the default model has its cache there
        previous = {"model": {"provider": "anthropic", "id": OPUS}, "thinkingLevel": "high"}
        self.assertEqual(self.routes(requests=[dict(light, previous=previous)]), [(OPUS, "low")])

    def test_the_peak_model_is_left_after_two_messages_in_a_row_that_do_not_need_it(self):
        deep, small = {"rating": {"score": 3.0}}, {"rating": {"score": 1.0}}
        out = self.run_router(chain=True, requests=[deep, small, deep, small, small, small])["routes"]
        self.assertEqual([(r["id"], r["thinking"]) for r in out],
                         [(FABLE, "high"), (FABLE, "low"), (FABLE, "high"), (FABLE, "low"), (OPUS, "high"), (OPUS, "high")])
        self.assertEqual([r["state"] and r["state"]["below"] for r in out], [0, 1, 0, 1, 0, None])

    def test_a_go_ahead_goes_on_where_the_work_is(self):
        go = {"go": 0.9, "score": 0.1}
        cases = [({"tier": "default", "effort": "high", "level": "standard", "below": 0}, (OPUS, "high"), None),
                 ({"tier": "default", "effort": "xhigh", "level": "hard", "below": 0}, (OPUS, "xhigh"), None),
                 ({"tier": "default", "effort": "low", "level": "light", "below": 0}, (OPUS, "high"), "standard"),
                 ({"tier": "light", "effort": "high", "level": "light", "below": 0}, (HAIKU, "high"), None),
                 ({"tier": "peak", "effort": "high", "level": "deep", "below": 0}, (FABLE, "high"), None),
                 ({"tier": "peak", "effort": "max", "level": "critical", "below": 0}, (FABLE, "high"), "deep"),
                 ({"tier": "peak", "effort": "low", "level": "standard", "below": 1}, (FABLE, "low"), None),
                 ({"tier": "strong", "effort": "max", "below": 0}, (SOL, "max"), None),
                 (None, (OPUS, "high"), "standard")]
        for state, want, level in cases:
            with self.subTest(state=state):
                out = self.run_router(rating=go, requests=[{"user": "進めて", "state": state}])["routes"][0]
                self.assertEqual((out["id"], out["thinking"]), want)
                self.assertEqual(out["state"] and out["state"].get("level"), level)  # no new state where nothing changed

    def test_a_model_the_owner_asks_for_is_used_and_the_effort_written_after_its_name(self):
        cases = [("fable で考えて", {"score": 1.0}, (FABLE, "high")),          # Fable by name is at least deep
                 ("ここぞで", {"score": 3.8}, (FABLE, "max")),
                 ("Fable5.2mediumの意見ききたい", {"score": 3.8}, (FABLE, "medium")),
                 ("fable max で", {"score": 1.0}, (FABLE, "max")),
                 ("fable-5-2 high で", {"score": 3.8}, (FABLE, "high")),
                 ("fable で high-level な設計を", {"score": 3.8}, (FABLE, "max")),  # not an effort after the name
                 ("opus でお願い", {"score": 3.8}, (OPUS, "xhigh")),             # the default model, up to hard
                 ("opus xhigh で", {"score": 1.0}, (OPUS, "xhigh")),
                 ("sol に聞いて", {"score": 1.0}, (SOL, "max")),
                 ("haiku で要約", {"score": 1.0}, (HAIKU, "high")),
                 ("軽量で調べて", {"score": 1.0}, (HAIKU, "high"))]
        state = {"tier": "default", "effort": "high", "level": "standard", "below": 0}
        for text, rating, want in cases:
            with self.subTest(text=text):
                out = self.run_router(rating=dict(rating, asked=0.9), requests=[{"user": text, "state": state}])
                self.assertEqual((out["routes"][0]["id"], out["routes"][0]["thinking"]), want)
                self.assertIn("asked", out["classified"][0]["questions"])

    def test_a_model_that_is_only_the_topic_is_not_a_request(self):
        out = self.run_router(rating={"asked": 0.05, "score": 1.8},
                              requests=[{"user": "fableはmaxにする必要あるかな?", "state": {"tier": "default", "effort": "high"}}])
        self.assertEqual((out["routes"][0]["id"], out["routes"][0]["thinking"]), (OPUS, "xhigh"))
        out = self.run_router(rating={"score": 1.0}, requests=[{"user": "状況は?"}])
        self.assertEqual(out["classified"][0]["questions"], ["level", "go"])  # asked only with a name

    def test_without_the_classifier_a_name_alone_decides_and_the_rest_stays(self):
        for scenario in ({"noClassifier": True}, {"classifierThrows": True}):
            with self.subTest(**scenario):
                self.assertEqual(self.routes(**scenario, requests=[
                    {}, {"state": {"tier": "light", "effort": "high", "level": "light"}},
                    {"state": {"tier": "default", "effort": "xhigh", "level": "hard"}},
                    {"user": "fable で"}, {"user": "Fable5.2medium で"}, {"user": "opus で"}, {"user": "haiku で"}]),
                    [(OPUS, "high"), (HAIKU, "high"), (OPUS, "xhigh"),
                     (FABLE, "max"), (FABLE, "medium"), (OPUS, "high"), (HAIKU, "high")])

    def test_a_hanging_classifier_times_out_instead_of_blocking_the_turn(self):
        self.assertEqual(self.routes(timeout=20, hang=True, requests=[{"state": {"tier": "peak", "effort": "max"}}]),
                         [(FABLE, "max")])

    def test_new_scores_move_the_effort_without_a_code_change(self):
        data = json.loads(json.dumps(TIERS))
        data["scores"][HAIKU]["medium"] = 31   # medium now reaches the light bar (30)
        data["scores"][FABLE]["high"] = 59     # no longer more than Opus's best (59): deep is xhigh (62)
        data["scores"][OPUS]["xhigh"] = 52     # nothing below max reaches 57
        (self.agent / "model-tiers.json").write_text(json.dumps(data))
        on_default = {"tier": "default", "effort": "high", "level": "standard"}
        got = [self.routes(rating={"score": score}, requests=[{"state": state}])[0]
               for score, state in ((0.1, None), (3.0, on_default), (2.0, on_default))]
        self.assertEqual(got, [(HAIKU, "medium"), (FABLE, "xhigh"), (OPUS, "max")])

    def test_without_scores_a_tier_keeps_its_configured_effort(self):
        data = {k: v for k, v in TIERS.items() if k != "scores"}
        (self.agent / "model-tiers.json").write_text(json.dumps(data))
        on_default = {"tier": "default", "effort": "high", "level": "standard"}
        got = [self.routes(rating={"score": score}, requests=[{"state": state}])[0]
               for score, state in ((0.1, None), (0.1, on_default), (2.0, on_default), (3.0, on_default), (3.9, on_default))]
        self.assertEqual(got, [(HAIKU, "high"), (OPUS, "high"), (OPUS, "high"), (FABLE, "max"), (FABLE, "max")])

    def test_tool_follow_ups_and_retries_stay_on_the_model_of_the_turn(self):
        prev = {"model": {"provider": "anthropic", "id": FABLE}, "thinkingLevel": "max"}
        failed = {"model": {"provider": "anthropic", "id": HAIKU}, "thinkingLevel": "high",
                  "message": {"stopReason": "error", "errorMessage": "overloaded"}}
        out = self.run_router(rating={"score": 0.1}, requests=[{"reason": "continuation", "previous": prev},
                                                              {"reason": "retry", "failed": failed, "previous": prev}])
        self.assertEqual([(r["id"], r["thinking"]) for r in out["routes"]], [(FABLE, "max"), (HAIKU, "high")])
        self.assertEqual(out["classified"], [])

    def test_requests_outside_the_loop_use_the_default_tier(self):
        self.assertEqual(self.routes(rating={"score": 4}, requests=[{"reason": "direct"}]), [(OPUS, "high")])

    def test_a_peak_tier_without_credentials_is_the_best_of_the_default_model(self):
        self.assertEqual(self.routes(rating={"score": 3.0}, noAuth=[FABLE], requests=[{}]), [(OPUS, "max")])
        out = self.run_router(rating={"score": 3.0}, noAuth=[OPUS], requests=[{}])
        self.assertIn("no credentials", out["routes"][0]["error"])

    def test_going_up_to_the_peak_model_is_told_and_the_state_is_kept(self):
        out = self.run_router(rating={"score": 3.9}, requests=[{}])
        self.assertEqual(out["routes"][0], {"id": FABLE, "thinking": "max",
                                            "state": {"tier": "peak", "effort": "max", "level": "critical", "below": 0}})
        self.assertTrue(any(FABLE in n for n in out["notices"]))

    @staticmethod
    def quota(used=0.95, window="5h", reset=1_800_003_600):
        return {"headers": {f"anthropic-ratelimit-unified-{window}-utilization": str(used),
                            f"anthropic-ratelimit-unified-{window}-reset": str(reset)}}

    def test_95_percent_in_either_claude_window_diverts_to_subscription_sol(self):
        for window in ("5h", "7d"):
            for used, expected in ((0.94999, OPUS), (0.95, SOL), (1.0, SOL)):
                with self.subTest(window=window, used=used):
                    (self.agent / "jev-claude-quota.json").unlink(missing_ok=True)
                    self.assertEqual(self.routes(requests=[{"responses": [self.quota(used, window)]}]),
                                     [(expected, "xhigh" if expected == SOL else "high")])

    def test_quota_keeps_task_depth_and_restores_fable_after_reset_on_a_new_user_message(self):
        out = self.run_router(chain=True, requests=[
            {"rating": {"score": 3.9}, "responses": [self.quota()]},
            {"rating": {"score": 3.0}},
            {"reason": "continuation", "now": 1_800_003_601_000},
            {"user": "進めて", "rating": {"go": 0.9}},
        ])["routes"]
        self.assertEqual([(r["id"], r["thinking"]) for r in out],
                         [(SOL, "max"), (SOL, "max"), (SOL, "max"), (FABLE, "high")])
        self.assertEqual(out[0]["state"]["claude"]["tier"], "peak")
        self.assertEqual(out[0]["state"]["level"], "critical")
        self.assertNotIn("claude", out[-1]["state"])

    def test_missing_or_old_headers_do_not_end_a_detour_and_all_high_windows_must_reset(self):
        self.assertEqual(self.routes(chain=True, requests=[
            {"responses": [self.quota(window="5h"), self.quota(window="7d", reset=1_800_007_200)]},
            {"now": 1_800_001_000_000, "responses": [{"headers": {}}]},  # more than five minutes, not recovery
            {"now": 1_800_003_601_000},  # 5h reset, 7d still high
            {"now": 1_800_007_201_000},
        ]), [(SOL, "xhigh"), (SOL, "xhigh"), (SOL, "xhigh"), (OPUS, "high")])

    def test_new_low_headers_replace_only_the_window_they_report(self):
        self.assertEqual(self.routes(chain=True, requests=[
            {"responses": [self.quota(window="5h"), self.quota(window="7d")]},
            {"now": 1_800_000_001_000, "responses": [self.quota(0.2, "5h")]},
            {"now": 1_800_000_002_000, "responses": [self.quota(0.3, "7d")]},
        ]), [(SOL, "xhigh"), (SOL, "xhigh"), (OPUS, "high")])

    def test_quota_survives_restart_and_never_stores_raw_headers(self):
        q = self.quota()
        q["headers"]["authorization"] = SECRET_TEXT
        self.assertEqual(self.routes(requests=[{"responses": [q]}]), [(SOL, "xhigh")])
        cache = (self.agent / "jev-claude-quota.json").read_text()
        self.assertNotIn(SECRET_TEXT, cache)
        self.assertNotIn(SECRET_TEXT, (self.agent / "jev-router.log.jsonl").read_text())
        self.assertEqual(self.routes(requests=[{}]), [(SOL, "xhigh")])

    def test_only_confirmed_pi_anthropic_subscription_responses_are_quota_evidence(self):
        for scenario, response in [({}, dict(self.quota(), provider="openai", model=SOL)),
                                   ({}, dict(self.quota(), stream=False)),
                                   ({"apiKeyProviders": ["anthropic"]}, self.quota()),
                                   ({"notSubscription": True}, self.quota())]:
            with self.subTest(scenario=scenario, response=response):
                self.assertEqual(self.routes(**scenario, requests=[{"responses": [response]}]), [(OPUS, "high")])
        self.assertFalse((self.agent / "jev-claude-quota.json").exists())

    def test_invalid_usage_values_are_not_evidence(self):
        for value in ("", " ", "NaN", "Infinity", "95", "-0.1", "1.01", "0x1"):
            with self.subTest(value=value):
                q = self.quota()
                q["headers"]["anthropic-ratelimit-unified-5h-utilization"] = value
                self.assertEqual(self.routes(requests=[{"responses": [q]}]), [(OPUS, "high")])
        self.assertFalse((self.agent / "jev-claude-quota.json").exists())

    def test_a_detour_never_uses_api_keys_or_falls_back_to_claude_if_sol_is_unavailable(self):
        for scenario in ({"apiKeyProviders": ["openai"]}, {"noAuth": [SOL]}, {"notSubscriptionProviders": ["openai"]}):
            with self.subTest(**scenario):
                route = self.run_router(**scenario, requests=[{"responses": [self.quota()]}])["routes"][0]
                self.assertIn("Sol subscription", route["error"])

    def test_an_unknown_reset_stays_on_sol_and_a_lost_cache_is_not_recovery(self):
        self.assertEqual(self.routes(chain=True, requests=[
            {"responses": [self.quota(reset=None)]}, {"now": 1_900_000_000_000},
        ]), [(SOL, "xhigh"), (SOL, "xhigh")])
        (self.agent / "jev-claude-quota.json").unlink()
        state = {"tier": "strong", "effort": "max", "level": "deep",
                 "claude": {"tier": "peak", "effort": "high", "level": "deep", "below": 0}}
        self.assertEqual(self.routes(noClassifier=True, requests=[{"state": state}]), [(SOL, "max")])

    def test_a_named_sol_cannot_turn_a_quota_detour_into_paid_api_usage(self):
        route = self.run_router(apiKeyProviders=["openai"], requests=[
            {"user": "sol で", "responses": [self.quota()]},
        ])["routes"][0]
        self.assertIn("Sol subscription", route["error"])

    def test_unknown_or_future_cache_is_not_a_measured_quota(self):
        cache = self.agent / "jev-claude-quota.json"
        for contents in ("not JSON", json.dumps({"source": "claude-code", "windows": {"5h": {"used": 1, "at": 1_800_000_000_000}}}),
                         json.dumps({"source": "pi-anthropic-subscription-v1", "windows": {"5h": {"used": 1, "at": 1_800_000_001_000}}})):
            with self.subTest(contents=contents):
                cache.write_text(contents)
                self.assertEqual(self.routes(requests=[{}]), [(OPUS, "high")])

    def test_quota_overrides_claude_names_and_still_works_without_the_classifier(self):
        self.assertEqual(self.routes(noClassifier=True, requests=[{"user": "fable max で", "responses": [self.quota()]}]),
                         [(SOL, "max")])

    def test_quota_diverts_compaction_and_tool_follow_ups_but_not_arbitrary_failed_retries(self):
        prev = {"model": {"provider": "anthropic", "id": OPUS}, "thinkingLevel": "high"}
        self.assertEqual(self.routes(requests=[
            {"reason": "direct", "responses": [self.quota()]},
            {"reason": "continuation", "previous": prev},
            {"reason": "retry", "failed": dict(prev, message={"stopReason": "error", "errorMessage": "401 unauthorized"})},
            {"reason": "retry", "failed": dict(prev, message={"stopReason": "error", "errorMessage": "overloaded"})},
        ]), [(SOL, "xhigh"), (SOL, "xhigh"), (OPUS, "high"), (OPUS, "high")])

    def test_a_confirmed_subscription_limit_can_divert_a_native_retry_but_generic_429_cannot(self):
        def failed(message):
            return {"model": {"provider": "anthropic", "id": OPUS}, "thinkingLevel": "high",
                    "message": {"stopReason": "error", "errorMessage": message}}
        self.assertEqual(self.routes(requests=[
            {"reason": "retry", "failed": failed("429 rate_limit_error: too many requests")},
            {"reason": "retry", "failed": failed("429 usage limit reached. Try again later.")},
        ]), [(OPUS, "high"), (SOL, "xhigh")])
        for message in ("401 unauthorized: usage limit reached", "billing: usage limit reached", "permission denied",
                        "Safety policy denied", "cancelled", "overloaded", "429 rate_limit_error"):
            with self.subTest(message=message):
                self.assertEqual(self.routes(requests=[{"reason": "retry", "failed": failed(message)}]), [(OPUS, "high")])
        self.assertEqual(self.routes(requests=[{"reason": "retry", "failed": {
            "model": {"provider": "openai", "id": SOL}, "thinkingLevel": "max",
            "message": {"stopReason": "error", "errorMessage": "usage limit reached"}}}]), [(SOL, "max")])

    def test_classifier_sees_bounded_text_and_the_log_never_holds_it(self):
        long_text = SECRET_TEXT + "x" * 20_000
        out = self.run_router(rating={"score": 1.0}, requests=[{"user": long_text, "assistant": "y" * 5_000,
                                                                "state": {"tier": "light", "effort": "high", "level": "light"}}])
        state = out["classified"][0]["state"]
        self.assertEqual(sorted(state), ["owner_message", "previous_answer_tail"])
        self.assertEqual(len(state["owner_message"]), 6_000)
        self.assertEqual(len(state["previous_answer_tail"]), 1_500)
        log = (self.agent / "jev-router.log.jsonl").read_text()
        self.assertNotIn(SECRET_TEXT, log)
        entry = json.loads(log.splitlines()[-1])
        self.assertEqual((entry["tier"], entry["effort"], entry["level"], entry["from"], entry["source"], entry["score"]),
                         ("default", "high", "standard", "light", "classifier", 1.0))


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
