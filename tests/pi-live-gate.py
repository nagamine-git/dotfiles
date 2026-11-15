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
CLICK, SNAPSHOT = "mcp__chrome__browser_click", "mcp__chrome__browser_snapshot"
TYPE, STATE = "computer_use_linux_type_text", "computer_use_linux_get_app_state"
ASK = [{"type": "custom", "customType": "live-gate", "data": {"surface": "chrome", "mode": "ask"}},
       {"type": "custom", "customType": "live-gate", "data": {"surface": "desktop", "mode": "ask"}}]


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
        (self.work / "run.mjs").write_text(HARNESS.replace('console.log(JSON.stringify(seen));',
            'seen.background = process.env.COMPUTER_USE_LINUX_HYPRLAND_BACKGROUND ?? null;\nconsole.log(JSON.stringify(seen));'))

    def run_gate(self, steps, env=None, **scenario):
        full = {"HOME": str(self.work), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", **(env or {})}
        proc = subprocess.run([NODE, "run.mjs", json.dumps(dict(scenario, steps=steps))], env=full, cwd=self.work,
                              capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def blocked(self, result):
        return bool(result and result.get("block"))

    ACTING = [CLICK, "mcp__chrome__browser_type", "mcp__chrome__browser_navigate", "mcp__chrome__browser_evaluate",
              "mcp__chrome__browser_file_upload", "mcp__chrome__browser_tabs", "mcp__chrome__some_new_tool",
              TYPE, "computer_use_linux_click", "computer_use_linux_press_key", "computer_use_linux_activate_window",
              "computer_use_linux_run_shell"]

    def test_by_default_pi_acts_without_asking_even_without_a_ui(self):
        for has_ui in (True, False):
            with self.subTest(has_ui=has_ui):
                seen = self.run_gate(self.ACTING, hasUI=has_ui, answer=False)
                self.assertEqual(seen["results"], [None] * len(self.ACTING))
                self.assertEqual((seen["confirms"], seen["emits"]), ([], []))
        self.assertIn("unless the owner asked for exactly that", seen["sections"]["live_gate"])

    def test_desktop_input_does_not_take_focus_unless_the_owner_set_otherwise(self):
        self.assertEqual(self.run_gate([])["background"], "1")
        self.assertEqual(self.run_gate([], env={"COMPUTER_USE_LINUX_HYPRLAND_BACKGROUND": "0"})["background"], "0")

    def test_looking_runs_in_every_mode_and_other_tools_are_not_this_gate_s_business(self):
        looking = [SNAPSHOT, "mcp__chrome__browser_take_screenshot", "mcp__chrome__browser_network_requests",
                   STATE, "computer_use_linux_tools", "computer_use_linux_doctor", "computer_use_linux_list_windows",
                   "computer_use_linux_screenshot"]
        other = ["bash", "write", "mcp__linear__save_issue", "mcp__playwright__browser_click", "mcp__chromex__browser_click"]
        for steps in ([{"command": "all off"}], [{"command": "all ask"}]):
            seen = self.run_gate(steps + looking + other, hasUI=False)
            self.assertEqual(seen["results"], [None] * (len(looking) + len(other)))
            self.assertEqual(seen["confirms"], [])

    def test_off_blocks_acting_and_auto_turns_it_back_on(self):
        seen = self.run_gate([{"command": "chrome off"}, CLICK, TYPE, {"command": "all off"}, TYPE, {"command": "chrome auto"}, CLICK,
                              {"command": "desktop on"}, TYPE])
        self.assertEqual([self.blocked(r) for r in seen["results"]], [True, False, True, False, False])
        self.assertIn("another harness", seen["results"][0]["reason"])
        self.assertEqual(seen["confirms"], [])
        self.assertIn("自動", seen["notes"][-1])

    def test_ask_asks_once_per_surface_and_keeps_the_answer(self):
        seen = self.run_gate(self.ACTING, branch=ASK)
        self.assertEqual(seen["results"], [None] * len(self.ACTING))
        self.assertEqual(len(seen["confirms"]), 2)
        self.assertIn("browser_click", seen["confirms"][0])
        self.assertNotIn("SYNTHETIC-INPUT", json.dumps(seen["confirms"]))
        self.assertEqual([e["data"] for e in seen["branch"][2:]], [{"surface": "chrome", "mode": "auto"}, {"surface": "desktop", "mode": "auto"}])
        seen = self.run_gate([CLICK, CLICK, TYPE], branch=ASK, answers=[False, True])
        self.assertEqual([self.blocked(r) for r in seen["results"]], [True, True, False])
        self.assertEqual(len(seen["confirms"]), 2)

    def test_ask_shares_one_dialog_blocks_without_a_ui_and_escape_decides_nothing(self):
        seen = self.run_gate([[CLICK, "mcp__chrome__browser_type", "mcp__chrome__browser_press_key"]], branch=ASK)
        self.assertEqual((seen["results"], len(seen["confirms"])), ([None, None, None], 1))
        seen = self.run_gate([CLICK, TYPE], branch=ASK, hasUI=False)
        self.assertTrue(all(self.blocked(r) for r in seen["results"]))
        seen = self.run_gate([CLICK], branch=ASK, abortWhileAsking=True, answer=False)
        self.assertTrue(self.blocked(seen["results"][0]))
        self.assertEqual(seen["branch"], ASK)

    def test_the_mode_lives_on_the_branch_and_old_entries_still_read(self):
        old = [{"type": "custom", "customType": "live-gate", "data": {"surface": "chrome", "allow": False}}]
        seen = self.run_gate([CLICK, {"forget": True}, CLICK], branch=old, hasUI=False)
        self.assertEqual([self.blocked(r) for r in seen["results"]], [True, False])  # another branch: the default, auto

    def test_no_environment_variable_grants_or_withholds_acting(self):
        self.assertNotIn("process.env.LIVE", EXTENSION.read_text())
        for env in ({"LIVE_GATE": "off"}, {"PI_LIVE": "ask"}):
            with self.subTest(env=env):
                self.assertEqual(self.run_gate([CLICK], hasUI=False, env=env)["results"], [None])

    def test_the_log_holds_the_decision_and_never_the_input(self):
        self.run_gate([CLICK, {"command": "desktop off"}, TYPE])
        lines = [json.loads(l) for l in (self.work / ".pi/agent/jev-gate.log.jsonl").read_text().splitlines()]
        self.assertEqual([(l["layer"], l["surface"], l.get("decision"), l.get("mode"), l["via"]) for l in lines],
                         [("live", "chrome", "allow", None, "auto"), ("live", "desktop", None, "off", "command"),
                          ("live", "desktop", "deny", None, "off")])
        self.assertNotIn("SYNTHETIC-INPUT", json.dumps(lines))


if __name__ == "__main__":
    unittest.main()
