"""Session-local /goal: fake Pi, disposable HOME, no models or network."""
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
# PI_GOAL_EXTENSION lets the owner review a draft before it enters the control path.
EXTENSION = Path(os.environ.get("PI_GOAL_EXTENSION") or ROOT / "home/dot_pi/agent/extensions/goal.ts")
NODE = shutil.which("node")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi_real

HARNESS = r'''
const scenario = JSON.parse(process.argv[2]);
const handlers = {}, commands = {}, tools = {};
const branch = scenario.branch ?? [];
const seen = {notes: [], entries: [], prompts: [], tools: [], events: []};
const ctx = {
  cwd: process.cwd(), hasUI: true,
  sessionManager: {getBranch: () => branch},
  ui: {setStatus() {}, notify: message => seen.notes.push(message)},
};
const {default: register} = await import("./goal.ts");
register({
  on: (name, fn) => { handlers[name] = fn; },
  registerCommand: (name, def) => { commands[name] = def.handler; },
  registerTool: def => { tools[def.name] = def; },
  appendEntry: (customType, data) => {
    seen.entries.push({customType, data: structuredClone(data)});
    branch.push({type: "custom", customType, data: structuredClone(data)});
  },
  events: {emit: (name, data) => seen.events.push({name, data})},
});
seen.toolNames = Object.keys(tools);
await handlers.session_start?.({reason: scenario.reason ?? "startup"}, ctx);
for (const step of scenario.steps ?? []) {
  if (step.command !== undefined) await commands.goal(step.command, ctx);
  if (step.tool) {
    try {
      const r = await tools.goal_control.execute("x", step.tool, null, null, ctx);
      seen.tools.push({ok: true, text: r.content[0].text, details: r.details});
    } catch (error) {
      seen.tools.push({ok: false, error: String(error.message ?? error)});
    }
  }
  if (step.prompt) {
    const r = await handlers.before_agent_start({systemPrompt: "BASE"}, ctx);
    seen.prompts.push(r?.systemPrompt ?? null);
  }
}
console.log(JSON.stringify(seen));
'''


@unittest.skipUnless(NODE, "Node is required")
class PiGoal(unittest.TestCase):
    def probe(self, steps=(), **scenario):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            home = Path(tmp) / "home"
            work.mkdir()
            home.mkdir()
            shutil.copyfile(EXTENSION, work / "goal.ts")
            (work / "run.mjs").write_text(HARNESS)
            stub = work / "node_modules/typebox"
            stub.mkdir(parents=True)
            (stub / "package.json").write_text('{"type":"module","main":"index.js"}')
            (stub / "index.js").write_text(
                'export const Type = {Object: x=>x, Union: x=>x, Literal: x=>x, String: x=>x, Optional: x=>x};')
            result = subprocess.run([NODE, "--disable-warning=ExperimentalWarning", "run.mjs",
                                     json.dumps(dict(scenario, steps=steps))], cwd=work,
                                    env={"HOME": str(home), "PATH": os.environ["PATH"]},
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_no_goal_leaves_prompt_unchanged(self):
        seen = self.probe([{"prompt": True}])
        self.assertIsNone(seen["prompts"][0])

    def test_owner_sets_goal_and_every_run_sees_it(self):
        seen = self.probe([{"command": "Ship 7 eligible videos"}, {"prompt": True}, {"prompt": True}])
        self.assertEqual(seen["entries"][-1]["data"]["status"], "active")
        for prompt in seen["prompts"]:
            self.assertTrue(prompt.startswith("BASE"))
            self.assertIn("Ship 7 eligible videos", prompt)
            self.assertIn("goal_control", prompt)

    def test_status_command_does_not_change_goal(self):
        seen = self.probe([{"command": "status"}, {"command": ""}])
        self.assertEqual(seen["entries"], [])
        self.assertEqual(len(seen["notes"]), 2)

    def test_clear_removes_prompt_section(self):
        seen = self.probe([{"command": "A goal"}, {"command": "clear"}, {"prompt": True}])
        self.assertEqual(seen["entries"][-1]["data"]["status"], "cleared")
        self.assertIsNone(seen["prompts"][0])

    def test_owner_done_marks_achieved(self):
        seen = self.probe([{"command": "A goal"}, {"command": "done"}, {"prompt": True}])
        self.assertEqual(seen["entries"][-1]["data"]["status"], "achieved")
        self.assertIsNone(seen["prompts"][0])

    def test_model_can_complete_with_evidence(self):
        seen = self.probe([{"command": "A goal"},
                           {"tool": {"action": "complete", "evidence": "7 videos admitted, verified"}},
                           {"prompt": True}])
        self.assertTrue(seen["tools"][0]["ok"])
        last = seen["entries"][-1]["data"]
        self.assertEqual(last["status"], "achieved")
        self.assertEqual(last["evidence"], "7 videos admitted, verified")
        self.assertIsNone(seen["prompts"][0])
        self.assertEqual(seen["events"][0]["name"], "pi-goal:achieved")

    def test_complete_requires_evidence_and_active_goal(self):
        seen = self.probe([{"tool": {"action": "complete", "evidence": "x"}},
                           {"command": "A goal"},
                           {"tool": {"action": "complete"}},
                           {"tool": {"action": "complete", "evidence": "   "}}])
        self.assertTrue(all(not t["ok"] for t in seen["tools"]))
        self.assertEqual(seen["entries"][-1]["data"]["status"], "active")

    def test_model_cannot_set_or_change_goal(self):
        seen = self.probe([{"tool": {"action": "set", "goal": "model goal"}}, {"prompt": True}])
        self.assertEqual(seen["toolNames"], ["goal_control"])
        self.assertFalse(seen["tools"][0]["ok"])
        self.assertIsNone(seen["prompts"][0])

    def test_status_tool_reports_goal(self):
        seen = self.probe([{"command": "A goal"}, {"tool": {"action": "status"}}])
        self.assertEqual(seen["tools"][0]["details"]["goal"], "A goal")
        self.assertEqual(seen["tools"][0]["details"]["status"], "active")

    def test_restores_latest_goal_from_branch(self):
        branch = [{"type": "custom", "customType": "pi-goal", "data": {"goal": "old", "status": "active"}},
                  {"type": "custom", "customType": "pi-goal", "data": {"goal": "new", "status": "active"}}]
        seen = self.probe([{"prompt": True}], branch=branch, reason="reload")
        self.assertIn("new", seen["prompts"][0])
        self.assertNotIn("old", seen["prompts"][0])

    def test_malformed_branch_entry_is_ignored(self):
        branch = [{"type": "custom", "customType": "pi-goal", "data": {"goal": 5, "status": "active"}}]
        seen = self.probe([{"prompt": True}], branch=branch)
        self.assertIsNone(seen["prompts"][0])

    def test_overlong_goal_rejected(self):
        seen = self.probe([{"command": "x" * 2001}])
        self.assertEqual(seen["entries"], [])


@unittest.skipUnless(pi_real.available(), "Installed Pi is required")
class RealPiGoal(unittest.TestCase):
    def test_installed_pi_registers_command_without_a_model_request(self):
        responses, stderr, _ = pi_real.rpc({"extensions/goal.ts": EXTENSION.read_text()}, [
            {"type": "get_commands"}, {"type": "prompt", "message": "/goal status"},
            {"type": "get_state"},
        ])
        commands = responses["c0"]["data"]["commands"]
        self.assertIn("goal", [x["name"] for x in commands], stderr)
        self.assertEqual(responses["c1"]["data"]["disposition"], "handled")
        self.assertEqual(responses["c2"]["data"]["messageCount"], 0)


if __name__ == "__main__":
    unittest.main()
