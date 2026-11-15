"""live-gate (the owner's go before Pi acts on the live Chrome or desktop): a stub Pi, no keys, network or model calls."""
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
EXTENSION = ROOT / "home/dot_pi/agent/extensions/live-gate.ts"
NODE = shutil.which("node")
HARNESS = r'''
const s = JSON.parse(process.argv[2]);
const handlers = {}, commands = {};
const seen = {confirms: [], notes: [], results: [], emits: [], sections: {}};
const branch = [...(s.branch ?? [])];
const pi = {
  on: (name, fn) => { handlers[name] = fn; },
  registerCommand: (name, options) => { commands[name] = options.handler; },
  appendEntry: (customType, data) => branch.push({type: "custom", customType, data}),
  events: {emit: (channel, data) => seen.emits.push([channel, data.active])},
};
(await import("./live-gate.ts")).default(pi);
const controller = new AbortController();
const ctx = {
  hasUI: s.hasUI ?? true, signal: controller.signal,
  sessionManager: {getBranch: () => branch},
  ui: {
    notify: (m) => seen.notes.push(m),
    confirm: async (_title, message) => {
      seen.confirms.push(message);
      await new Promise((r) => setTimeout(r, 5));
      if (s.abortWhileAsking) controller.abort();
      return s.answers ? s.answers.shift() : (s.answer ?? true);
    },
  },
};
await handlers.before_agent_start({systemPromptOptions: {sections: seen.sections}}, ctx);
for (const step of s.steps) {
  if (step.command !== undefined) { await commands.live(step.command, ctx); continue; }
  if (step.forget) { branch.length = 0; continue; }
  const calls = Array.isArray(step) ? step : [step];  // an array runs in parallel
  seen.results.push(...await Promise.all(calls.map(async (name) => (await handlers.tool_call({toolName: name, input: {secret: "SYNTHETIC-INPUT"}}, ctx)) ?? null)));
}
seen.branch = branch;
console.log(JSON.stringify(seen));
'''
CLICK, SNAPSHOT = "mcp__chrome__click", "mcp__chrome__take_snapshot"
TYPE, STATE = "computer_use_linux_type_text", "computer_use_linux_get_app_state"


def supports_types():
    if not NODE:
        return False
    version = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.lstrip("v")
    return tuple(map(int, version.split(".")[:2])) >= (23, 6)


@unittest.skipUnless(supports_types() or os.environ.get("CI"), "Node 23.6 以上が必要")
class LiveGate(unittest.TestCase):
    def setUp(self):
        if not supports_types():
            self.fail("CI requires Node 23.6+")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        (self.work / ".pi/agent").mkdir(parents=True)
        (self.work / "package.json").write_text('{"type":"module"}')
        shutil.copyfile(EXTENSION, self.work / "live-gate.ts")
        (self.work / "run.mjs").write_text(HARNESS)

    def run_gate(self, steps, env=None, **scenario):
        full = {"HOME": str(self.work), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **(env or {})}
        proc = subprocess.run([NODE, "run.mjs", json.dumps(dict(scenario, steps=steps))], env=full, cwd=self.work,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def blocked(self, result):
        return bool(result and result.get("block"))

    def test_looking_runs_and_other_tools_are_not_this_gate_s_business(self):
        looking = [SNAPSHOT, "mcp__chrome__list_pages", "mcp__chrome__take_screenshot", "mcp__chrome__list_network_requests",
                   STATE, "computer_use_linux_tools", "computer_use_linux_doctor", "computer_use_linux_list_windows",
                   "computer_use_linux_screenshot"]
        other = ["bash", "write", "mcp__linear__save_issue", "mcp__playwright__browser_click", "mcp__chromex__click"]
        seen = self.run_gate(looking + other, hasUI=False)
        self.assertEqual(seen["results"], [None] * (len(looking) + len(other)))
        self.assertEqual(seen["confirms"], [])

    def test_the_first_action_asks_once_per_surface_and_the_go_covers_the_session(self):
        acting = [CLICK, "mcp__chrome__fill", "mcp__chrome__navigate_page", "mcp__chrome__evaluate_script", "mcp__chrome__upload_file",
                  TYPE, "computer_use_linux_click", "computer_use_linux_press_key", "computer_use_linux_activate_window"]
        seen = self.run_gate(acting)
        self.assertEqual(seen["results"], [None] * len(acting))
        self.assertEqual(len(seen["confirms"]), 2)  # chrome once, desktop once
        self.assertIn("Chrome", seen["confirms"][0])
        self.assertIn("click", seen["confirms"][0])
        self.assertNotIn("SYNTHETIC-INPUT", json.dumps(seen["confirms"]))
        self.assertEqual([e["data"] for e in seen["branch"]], [{"surface": "chrome", "allow": True}, {"surface": "desktop", "allow": True}])
        self.assertEqual(seen["emits"], [["herdr:blocked", True], ["herdr:blocked", False]] * 2)
        self.assertIn("mcp__chrome__", seen["sections"]["live_gate"])

    def test_a_tool_this_gate_does_not_know_counts_as_acting(self):
        seen = self.run_gate(["mcp__chrome__some_new_tool", "computer_use_linux_run_shell"], answer=False)
        self.assertTrue(all(self.blocked(r) for r in seen["results"]))
        self.assertEqual(len(seen["confirms"]), 2)

    def test_a_decline_is_final_until_the_owner_turns_the_surface_on(self):
        seen = self.run_gate([CLICK, CLICK, SNAPSHOT, TYPE, {"command": "chrome on"}, CLICK, {"command": "all off"}, CLICK, TYPE],
                             answers=[False, True])
        self.assertEqual([self.blocked(r) for r in seen["results"]], [True, True, False, False, False, True, True])
        self.assertEqual(len(seen["confirms"]), 2)  # chrome (declined) and desktop (allowed); never again
        self.assertIn("another harness", seen["results"][0]["reason"])
        self.assertIn("停止", seen["notes"][-1])

    def test_parallel_actions_share_one_dialog(self):
        seen = self.run_gate([[CLICK, "mcp__chrome__fill", "mcp__chrome__press_key"]])
        self.assertEqual((seen["results"], len(seen["confirms"])), ([None, None, None], 1))
        seen = self.run_gate([[CLICK, "mcp__chrome__fill"]], answer=False)
        self.assertEqual(([self.blocked(r) for r in seen["results"]], len(seen["confirms"])), ([True, True], 1))

    def test_without_a_ui_acting_is_blocked_and_no_environment_variable_grants_the_go(self):
        for env in ({}, {"LIVE_GATE": "chrome,desktop", "PI_LIVE": "all"}):
            with self.subTest(env=env):
                seen = self.run_gate([CLICK, TYPE], hasUI=False, env=env)
                self.assertTrue(all(self.blocked(r) for r in seen["results"]))
                self.assertEqual((seen["confirms"], seen["branch"]), ([], []))
        self.assertNotIn("process.env", EXTENSION.read_text())

    def test_the_go_lives_on_the_branch_and_an_aborted_question_decides_nothing(self):
        allowed = [{"type": "custom", "customType": "live-gate", "data": {"surface": "chrome", "allow": True}}]
        seen = self.run_gate([CLICK, {"forget": True}, CLICK], branch=allowed, answer=False)
        self.assertEqual([self.blocked(r) for r in seen["results"]], [False, True])  # another branch asks again
        seen = self.run_gate([CLICK], abortWhileAsking=True, answer=False)
        self.assertTrue(self.blocked(seen["results"][0]))
        self.assertEqual(seen["branch"], [])  # Escape is not a decline

    def test_the_log_holds_the_decision_and_never_the_input(self):
        self.run_gate([CLICK, {"command": "desktop off"}])
        lines = [json.loads(l) for l in (self.work / ".pi/agent/jev-gate.log.jsonl").read_text().splitlines()]
        self.assertEqual([(l["layer"], l["surface"], l["decision"], l["via"]) for l in lines],
                         [("live", "chrome", "allow", "confirm"), ("live", "desktop", "deny", "command")])
        self.assertNotIn("SYNTHETIC-INPUT", json.dumps(lines))


if __name__ == "__main__":
    unittest.main()
