"""Session-local /loop: fake timers, fake Pi, disposable HOME, no models or network."""
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
EXTENSION = ROOT / "home/dot_pi/agent/extensions/loop.ts"
NODE = shutil.which("node")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi_real

HARNESS = r'''
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const scenario = JSON.parse(process.argv[2]);
const timers = new Map();
let serial = 0;
globalThis.setTimeout = (fn, ms) => {
  const timer = {id: ++serial, unref() {}};
  timers.set(timer, {fn, ms});
  return timer;
};
globalThis.clearTimeout = timer => timers.delete(timer);
const handlers = {}, commands = {}, tools = {};
const seen = {messages: [], notes: [], entries: [], states: [], aborts: 0};
const ctx = {
  cwd: process.cwd(), mode: scenario.mode ?? "tui", hasUI: true,
  model: {provider: "openai", id: "fixture"}, thinkingLevel: "max",
  isProjectTrusted: () => scenario.trusted !== false,
  isIdle: () => !scenario.busy,
  hasPendingMessages: () => Boolean(scenario.pending),
  abort: () => { seen.aborts++; },
  sessionManager: {getSessionId: () => "fixture-session"},
  ui: {setStatus() {}, notify: message => seen.notes.push(message)},
};
if (scenario.arm) {
  const dir = path.join(os.homedir(), ".local/state/pi-loop");
  fs.mkdirSync(dir, {recursive: true});
  fs.writeFileSync(path.join(dir, "fixture-session.json"), JSON.stringify({
    version: 1, sessionId: "fixture-session", cwd: ctx.cwd, intervalMs: 600000,
    task: "fixture authorized work", provider: "openai", model: "fixture", thinkingLevel: "max",
    ...scenario.arm,
  }));
}
const {default: register} = await import("./loop.ts");
register({
  on: (name, fn) => { handlers[name] = fn; },
  registerCommand: (name, def) => { commands[name] = def.handler; },
  registerTool: def => { tools[def.name] = def; },
  appendEntry: (customType, data) => seen.entries.push({customType, data: structuredClone(data)}),
  sendMessage: (message, options) => seen.messages.push({message, options}),
});
seen.factoryTimers = timers.size;
await handlers.session_start({reason: scenario.reason ?? "startup"}, ctx);
for (const step of scenario.steps ?? []) {
  if (step.command !== undefined) await commands.loop(step.command, ctx);
  if (step.context) Object.assign(scenario, step.context);
  if (step.event && handlers[step.event]) await handlers[step.event](step.data ?? {}, ctx);
  if (step.fire) {
    const first = timers.entries().next().value;
    if (first) { timers.delete(first[0]); first[1].fn(); }
  }
  if (step.tool) seen.states.push((await tools.loop_control.execute("x", {action: step.tool}, null, null, ctx)).details);
  seen.states.push({timers: timers.size, delays: [...timers.values()].map(t => t.ms), messages: seen.messages.length});
}
seen.armExists = fs.existsSync(path.join(os.homedir(), ".local/state/pi-loop/fixture-session.json"));
console.log(JSON.stringify(seen));
'''


@unittest.skipUnless(NODE, "Node is required")
class PiLoop(unittest.TestCase):
    def probe(self, steps=(), **scenario):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home, work = base / "home", base / "work"
            home.mkdir()
            work.mkdir()
            shutil.copyfile(EXTENSION, work / "loop.ts")
            (work / "run.mjs").write_text(HARNESS)
            stub = work / "node_modules/typebox"
            stub.mkdir(parents=True)
            (stub / "package.json").write_text('{"type":"module","main":"index.js"}')
            (stub / "index.js").write_text('export const Type = {Object: x=>x, Union: x=>x, Literal: x=>x};')
            result = subprocess.run([NODE, "--disable-warning=ExperimentalWarning", "run.mjs",
                                     json.dumps(dict(scenario, steps=steps))], cwd=work,
                                    env={"HOME": str(home), "PATH": os.environ["PATH"]},
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

    def test_factory_and_normal_startup_do_not_schedule(self):
        seen = self.probe([{"tool": "status"}])
        self.assertEqual(seen["factoryTimers"], 0)
        self.assertFalse(seen["states"][0]["active"])
        self.assertEqual(seen["messages"], [])

    def test_first_tick_is_extension_authored_not_owner_input(self):
        seen = self.probe([{"command": "start 10m approved task"}, {"fire": True}])
        self.assertEqual(len(seen["messages"]), 1)
        message = seen["messages"][0]
        self.assertEqual(message["message"]["customType"], "pi-loop-tick")
        self.assertIn("approved task", message["message"]["content"])
        self.assertTrue(message["options"]["triggerTurn"])
        self.assertEqual(seen["states"][-1]["timers"], 0)

    def test_waits_for_settled_not_low_level_end(self):
        seen = self.probe([{"command": "start 10m"}, {"fire": True},
                           {"event": "agent_end"}, {"event": "agent_settled", "data": {"aborted": False}}])
        self.assertEqual(seen["states"][-2]["timers"], 0)
        self.assertEqual(seen["states"][-1]["delays"], [600000])

    def test_busy_or_pending_tick_does_not_queue_a_prompt(self):
        for flag in ("busy", "pending"):
            seen = self.probe([{"command": "start 10m"}, {"context": {flag: True}, "fire": True}])
            self.assertEqual(seen["messages"], [])
            self.assertEqual(seen["states"][-1]["timers"], 1)

    def test_repeated_start_keeps_only_one_timer(self):
        seen = self.probe([{"command": "start 10m"}, {"command": "start 5m"}])
        self.assertEqual(seen["states"][-1]["timers"], 1)

    def test_stop_cancels_wait_and_settled_cannot_restart_it(self):
        seen = self.probe([{"command": "start"}, {"command": "stop"},
                           {"event": "agent_settled", "data": {"aborted": False}}, {"fire": True}, {"tool": "status"}])
        self.assertEqual(seen["messages"], [])
        self.assertFalse(seen["states"][-2]["active"])

    def test_agent_start_defers_until_the_user_work_finishes(self):
        seen = self.probe([{"command": "start"}, {"event": "agent_start"},
                           {"event": "agent_settled", "data": {"aborted": False}}])
        self.assertEqual(seen["states"][-2]["timers"], 0)
        self.assertEqual(seen["states"][-1]["delays"], [600000])

    def test_abort_approval_tool_error_and_session_changes_stop(self):
        cases = [("agent_settled", {"aborted": True}), ("ui_prompt_start", {}),
                 ("tool_execution_end", {"isError": True}), ("session_tree", {}),
                 ("session_shutdown", {"reason": "reload"}), ("model_select", {}),
                 ("thinking_level_select", {})]
        for event, data in cases:
            with self.subTest(event=event):
                seen = self.probe([{"command": "start"}, {"event": event, "data": data},
                                   {"event": "agent_settled", "data": {"aborted": False}}, {"fire": True}])
                self.assertEqual(seen["messages"], [])
                self.assertEqual(seen["states"][-1]["timers"], 0)

    def test_provider_error_aborts_and_never_resends(self):
        seen = self.probe([{"command": "start"}, {"event": "message_end", "data": {
            "message": {"role": "assistant", "stopReason": "error"}}},
            {"event": "agent_settled", "data": {"aborted": False}}, {"fire": True}])
        self.assertEqual(seen["aborts"], 1)
        self.assertEqual(seen["messages"], [])

    def test_readonly_tool_can_only_stop_not_start(self):
        seen = self.probe([{"command": "start"}, {"tool": "stop"}, {"fire": True}])
        self.assertEqual(seen["messages"], [])
        self.assertFalse(next(s for s in seen["states"] if "active" in s)["active"])

    def test_invalid_intervals_do_not_create_a_timer(self):
        for args in ("start 0s", "start -1m", "start 999999999h", "start 0.1s", "nonsense"):
            with self.subTest(args=args):
                seen = self.probe([{"command": args}])
                self.assertEqual(seen["states"][-1]["timers"], 0)

    def test_print_json_and_untrusted_projects_cannot_start(self):
        for options in ({"mode": "print"}, {"mode": "json"}, {"trusted": False}):
            seen = self.probe([{"command": "start"}], **options)
            self.assertEqual(seen["states"][-1]["timers"], 0)

    def test_only_reload_consumes_a_matching_one_shot_start(self):
        seen = self.probe([{"fire": True}], arm={}, reason="reload")
        self.assertFalse(seen["armExists"])
        self.assertEqual(len(seen["messages"]), 1)
        for reason in ("startup", "new", "resume", "fork"):
            seen = self.probe([{"fire": True}], arm={}, reason=reason)
            self.assertTrue(seen["armExists"])
            self.assertEqual(seen["messages"], [])

    def test_arm_for_another_project_session_or_model_is_not_consumed(self):
        for arm in ({"cwd": "/other"}, {"sessionId": "other"}, {"provider": "other"},
                    {"model": "other"}, {"thinkingLevel": "high"}, {"intervalMs": 0}, {"task": ""}):
            with self.subTest(arm=arm):
                seen = self.probe([{"fire": True}], arm=arm, reason="reload")
                self.assertTrue(seen["armExists"])
                self.assertEqual(seen["messages"], [])


@unittest.skipUnless(pi_real.available(), "Installed Pi is required")
class RealPiLoop(unittest.TestCase):
    def test_installed_pi_registers_commands_without_a_model_request(self):
        responses, stderr, _ = pi_real.rpc({"extensions/loop.ts": EXTENSION.read_text()}, [
            {"type": "get_commands"}, {"type": "prompt", "message": "/loop status"},
            {"type": "prompt", "message": "/loop stop"}, {"type": "get_state"},
        ])
        commands = responses["c0"]["data"]["commands"]
        self.assertIn("loop", [x["name"] for x in commands], stderr)
        self.assertEqual(responses["c1"]["data"]["disposition"], "handled")
        self.assertEqual(responses["c2"]["data"]["disposition"], "handled")
        self.assertFalse(responses["c3"]["data"]["isStreaming"])
        self.assertEqual(responses["c3"]["data"]["messageCount"], 0)


if __name__ == "__main__":
    unittest.main()
