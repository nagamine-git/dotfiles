"""Pi usage guidance: stubbed read-only helpers, no keys, network or model calls.

Node strips TypeScript like the other Pi tests. The installed-Pi smoke test uses
pi_real's isolated HOME/agent dir and never submits a prompt to a model.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi_real  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "dot_pi/agent/extensions/usage-aware.ts"
NODE = shutil.which("node")
HARNESS = r'''
const s = JSON.parse(process.argv[2]);
let now = 2_000_000_000_000;
Date.now = () => now;
const handlers = {}, commands = {}, tools = {}, calls = [], notices = [], statuses = [];
const pi = {
  on: (name, fn) => { handlers[name] = fn; },
  registerCommand: (name, c) => { commands[name] = c; },
  registerTool: (tool) => { tools[tool.name] = tool; },
  getSettings: () => s.settings ?? {},
  exec: async (file, args, options) => {
    calls.push({file, args, options});
    if (s.throws) throw Error("SYNTHETIC-SECRET");
    return s.responses[file.split('/').pop()] ?? {code: 127, stdout: "", stderr: "SYNTHETIC-SECRET"};
  },
};
const ctx = {cwd: "/work", mode: "tui", hasUI: true, model: s.model,
  ui: {notify: (msg) => notices.push(msg), setStatus: (key, value) => statuses.push([key, value])}};
(await import('./usage-aware.ts')).default(pi);
const outputs = [];
await handlers.session_start?.({}, ctx);
const startupCalls = calls.length;
for (const step of s.steps ?? ["tool"]) {
  if (step.advance) { now += step.advance; continue; }
  if (step.cwd) { ctx.cwd = step.cwd; continue; }
  if (step === "command") await commands.usage.handler("", ctx);
  else if (step === "parallel") outputs.push(...await Promise.all([1,2].map(() =>
    tools.usage_status.execute("id", {}, undefined, undefined, ctx))));
  else if (step === "tool") outputs.push(await tools.usage_status.execute("id", {}, undefined, undefined, ctx));
}
console.log(JSON.stringify({calls, startupCalls, outputs, notices, statuses,
  guidelines: tools.usage_status.promptGuidelines}));
'''


def supports_types():
    if not NODE:
        return False
    version = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.lstrip("v")
    return tuple(map(int, version.split(".")[:2])) >= (23, 6)


def result(value, code=0, **extra):
    return {"code": code, "stdout": json.dumps(value), "stderr": "SYNTHETIC-SECRET", **extra}


def responses():
    return {
        "claude-usage-cache": result({"state": "cached", "fetched_at": 2_000_000_000,
            "expires_at": 2_000_000_300, "windows": {
                "5h": {"used_percent": 72, "remaining_percent": 28, "resets_at": 2_000_003_600},
                "7d": {"used_percent": 18, "remaining_percent": 82, "resets_at": None}}}),
        "model-route": result({"state": "ready", "workflow": "review", "tool_version": "codex-cli 0.166.0",
            "model_started": False, "thread_started": False, "paid_api_calls": 0,
            "checked_at": "2033-05-18T03:33:20+00:00", "ordinary_usage_allowed": True,
            "quota": {"state": "known", "bucket": "codex",
                "primary": {"used_percent": 12, "remaining_percent": 88,
                    "window_duration_mins": 300, "resets_at": 2_000_003_600},
                "secondary": {"used_percent": 65, "remaining_percent": 35,
                    "window_duration_mins": 10080, "resets_at": 2_000_086_400}}}),
    }


@unittest.skipUnless(supports_types() or os.environ.get("CI"), "Node 23.6 以上が必要")
class PiUsage(unittest.TestCase):
    def setUp(self):
        if not supports_types():
            self.fail("CI requires Node 23.6+")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        stub = self.work / "node_modules/typebox"
        stub.mkdir(parents=True)
        (stub / "package.json").write_text('{"type":"module","main":"index.js"}')
        (stub / "index.js").write_text('export const Type = {Object: (properties) => ({type:"object",properties})};')
        (self.work / "package.json").write_text('{"type":"module"}')
        shutil.copyfile(EXTENSION, self.work / "usage-aware.ts")
        (self.work / "run.mjs").write_text(HARNESS)

    def run_extension(self, **scenario):
        scenario.setdefault("responses", responses())
        env = {"HOME": str(self.work), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        proc = subprocess.run([NODE, "run.mjs", json.dumps(scenario)], env=env, cwd=self.work,
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("SYNTHETIC-SECRET", proc.stdout)
        return json.loads(proc.stdout)

    def test_startup_never_runs_helpers_and_reads_are_fixed_and_bounded(self):
        out = self.run_extension()
        self.assertEqual(out["startupCalls"], 0)
        self.assertEqual([(Path(c["file"]).name, c["args"]) for c in out["calls"]], [
            ("claude-usage-cache", ["--json"]), ("model-route", ["check", "--workflow", "review"])])
        for c in out["calls"]:
            self.assertEqual(Path(c["file"]).parent, self.work / ".local/bin")
            self.assertEqual(c["options"]["cwd"], "/work")
            self.assertGreater(c["options"]["timeout"], 0)
            self.assertLessEqual(c["options"]["timeout"], 45000)
            self.assertLessEqual(c["options"]["maxBuffer"], 16384)
        report = out["outputs"][0]["details"]
        self.assertEqual(report["claude"]["state"], "cached")
        self.assertEqual(report["codex"]["state"], "known")
        self.assertEqual(report["codex"]["windows"]["primary"]["remaining_percent"], 88)
        self.assertTrue(report["compaction"]["enabled"])

    def test_blocked_codex_never_bypasses_the_existing_guard(self):
        r = responses()
        r["model-route"] = result({"state": "blocked", "reason": "SYNTHETIC-SECRET"}, code=78)
        out = self.run_extension(responses=r)
        self.assertEqual(out["outputs"][0]["details"]["codex"]["state"], "blocked")
        self.assertEqual(len(out["calls"]), 2)

    def test_missing_broken_or_terminated_helpers_are_unknown(self):
        for response in ({"code": 0, "stdout": "broken", "stderr": "SYNTHETIC-SECRET"},
                         {"code": 127, "stdout": "", "stderr": "SYNTHETIC-SECRET"},
                         result({}, killed=True), result({}, truncated=True)):
            with self.subTest(response=response):
                out = self.run_extension(responses={key: response for key in responses()})
                for key in ("claude", "codex"):
                    self.assertEqual(out["outputs"][0]["details"][key]["state"], "unknown")
        out = self.run_extension(throws=True)
        self.assertEqual(out["outputs"][0]["details"]["codex"]["state"], "unknown")

    def test_ordinary_usage_denied_or_unknown_never_claims_spare_capacity(self):
        for allowed in (False, None, "true"):
            with self.subTest(allowed=allowed):
                r = responses()
                data = json.loads(r["model-route"]["stdout"])
                data["ordinary_usage_allowed"] = allowed
                r["model-route"] = result(data)
                report = self.run_extension(responses=r)["outputs"][0]["details"]["codex"]
                self.assertEqual(report["state"], "blocked" if allowed is False else "unknown")
                self.assertEqual(report["windows"], {})

    def test_wrong_bucket_bad_numbers_future_and_stale_observations(self):
        mutations = [lambda d: d["quota"].update(bucket="fable"),
                     lambda d: d["quota"]["primary"].update(used_percent=-1),
                     lambda d: d["quota"]["primary"].update(used_percent=101),
                     lambda d: d["quota"]["primary"].update(remaining_percent=1),
                     lambda d: d["quota"]["primary"].update(window_duration_mins=None),
                     lambda d: d["quota"]["primary"].update(resets_at=1e300),
                     lambda d: d.update(checked_at="2033-05-18T04:00:00+00:00")]
        for mutate in mutations:
            r = responses()
            data = json.loads(r["model-route"]["stdout"])
            mutate(data)
            r["model-route"] = result(data)
            self.assertEqual(self.run_extension(responses=r)["outputs"][0]["details"]["codex"]["state"], "unknown")
        r = responses()
        data = json.loads(r["model-route"]["stdout"])
        data["checked_at"] = "2033-05-18T03:00:00+00:00"
        r["model-route"] = result(data)
        self.assertEqual(self.run_extension(responses=r)["outputs"][0]["details"]["codex"]["state"], "stale")

    def test_helper_output_cannot_inject_extra_fields_or_invent_a_missing_window(self):
        r = responses()
        for key in r:
            data = json.loads(r[key]["stdout"])
            data["injected_instruction"] = "SYNTHETIC-SECRET"
            windows = data["windows"] if key == "claude-usage-cache" else data["quota"]
            windows.pop("7d" if key == "claude-usage-cache" else "secondary")
            r[key] = result(data)
        out = self.run_extension(responses=r)["outputs"][0]["details"]
        self.assertNotIn("7d", out["claude"]["windows"])
        self.assertNotIn("secondary", out["codex"]["windows"])

    def test_repeated_tool_calls_cache_codex_but_command_cwd_change_and_ttl_refresh(self):
        out = self.run_extension(steps=["tool", "tool", "command", {"cwd": "/another"}, "tool",
                                       {"advance": 301000}, "tool"])
        calls = [Path(c["file"]).name for c in out["calls"]]
        self.assertEqual(calls.count("claude-usage-cache"), 5)
        self.assertEqual(calls.count("model-route"), 4)
        self.assertEqual(len(out["notices"]), 1)
        self.assertEqual(out["outputs"][-1]["details"]["claude"]["state"], "stale")
        self.assertEqual(out["outputs"][-1]["details"]["codex"]["state"], "stale")

    def test_parallel_reads_share_one_codex_check(self):
        out = self.run_extension(steps=["parallel"])
        self.assertEqual([Path(c["file"]).name for c in out["calls"]].count("model-route"), 1)
        self.assertEqual(len(out["outputs"]), 2)

    def test_a_reset_inside_the_cache_ttl_marks_both_observations_stale(self):
        r = responses()
        for key in r:
            data = json.loads(r[key]["stdout"])
            w = data["windows"]["5h"] if key == "claude-usage-cache" else data["quota"]["primary"]
            w["resets_at"] = 2_000_000_001
            r[key] = result(data)
        out = self.run_extension(responses=r, steps=["tool", {"advance": 2000}, "tool"])
        for key in ("claude", "codex"):
            self.assertEqual(out["outputs"][-1]["details"][key]["state"], "stale")

    def test_compaction_uses_the_active_models_override(self):
        settings = {"compaction": {"reserveTokens": 12345,
            "modelOverrides": {"other/model": {"reserveTokens": 99999}}}}
        out = self.run_extension(settings=settings)
        self.assertEqual(out["outputs"][0]["details"]["compaction"]["reserveTokens"], 12345)
        out = self.run_extension(settings=settings, model={"provider": "other", "id": "model"})
        self.assertEqual(out["outputs"][0]["details"]["compaction"]["reserveTokens"], 99999)

    def test_command_reports_effective_compaction_without_changing_it(self):
        out = self.run_extension(steps=["command"], settings={"compaction": {"enabled": False,
            "reserveTokens": 12345, "keepRecentTokens": 54321}})
        self.assertIn("OFF", out["notices"][0])
        self.assertIn("12345", out["notices"][0])
        self.assertIn("54321", out["notices"][0])

    def test_routing_guidance_preserves_capabilities_consent_and_cost_boundaries(self):
        text = "\n".join(self.run_extension()["guidelines"])
        for needle in ("usage_status", "delegate", "subagent", "不明", "Fable", "API", "拒否", "sandbox"):
            self.assertIn(needle, text)


@unittest.skipUnless(pi_real.available(), "Pi が入っていない (am5-itx だけ)")
class RealPiUsage(unittest.TestCase):
    def test_real_pi_loads_the_tool_and_command_without_executing_a_helper(self):
        probe = '''
import {writeFileSync} from "node:fs";
import {join} from "node:path";
export default function(pi) {
  pi.on("session_start", () => writeFileSync(join(process.env.PROBE_DIR, "probe.json"),
    JSON.stringify(pi.getActiveTools())));
}
'''
        responses, stderr, files = pi_real.rpc({"extensions/usage-aware.ts": EXTENSION.read_text(),
                                              "extensions/zz-usage-probe.ts": probe},
                                             [{"type": "get_commands"}, {"type": "get_state"}],
                                             read_back=["probe.json"])
        self.assertNotIn("Failed to load", stderr)
        self.assertTrue(any(c["name"] == "usage" for c in responses["c0"]["data"]["commands"]), stderr)
        self.assertTrue(responses["c1"]["data"]["autoCompactionEnabled"], stderr)
        self.assertIn("usage_status", json.loads(files["probe.json"]))


if __name__ == "__main__":
    unittest.main()
