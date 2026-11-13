"""The Pi notify extension, loaded by Node with a stub Pi module and a fake claude-notify.

Needs Node 23.6 or later, which runs TypeScript by stripping its types. Elsewhere it skips, but
not in CI (the CI environment variable): there an older Node fails the run. Never calls a model.
The last test loads jev-gate.ts beside it, so a confirm prompt is followed from the gate to claude-notify.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = ROOT / "home/dot_pi/agent/extensions"
INJECTION_GUARD = ROOT / "home/dot_claude/hooks/executable_injection-guard.sh"
NODE = shutil.which("node")
JQ = shutil.which("jq")

STUB_PI = 'export function isToolCallEventType(name, event) { return event.toolName === name; }\n'

# Loads the extensions on one shared event bus, starts a session and plays the steps in order.
HARNESS = '''
const scenario = JSON.parse(process.argv[2]);
const handlers = {};
const bus = {};
const pi = {
  on: (name, fn) => { (handlers[name] ??= []).push(fn); },
  registerCommand() {},
  events: {
    on: (channel, fn) => { (bus[channel] ??= []).push(fn); return () => {}; },
    emit: (channel, data) => { for (const fn of bus[channel] ?? []) fn(data); },
  },
};
for (const file of scenario.extensions) (await import("./" + file)).default(pi);
const fire = async (name, event) => { for (const fn of handlers[name] ?? []) await fn(event, ctx); };
const ctx = {
  mode: scenario.mode,
  hasUI: scenario.mode === "tui" || scenario.mode === "rpc",
  cwd: process.cwd(),
  isIdle: () => scenario.idle,
  ui: { notify() {}, setStatus() {}, confirm: async () => true },
  sessionManager: { getBranch: () => scenario.branch },
  modelRegistry: {
    findOfType: () => ({ id: "jev-latest" }),
    classify: async () => ({ stopReason: "stop",
      answers: { verdict: { type: "choice", choice: "confirm", probabilities: {}, confidence: 0.9 } } }),
  },
};
await fire("session_start", { type: "session_start", reason: "startup" });
for (const step of scenario.steps) {
  if (step.emit) pi.events.emit(step.emit[0], step.emit[1]);
  if (step.settled) await fire("agent_settled", { type: "agent_settled", aborted: step.settled.aborted });
  if (step.tool) await fire("tool_call", step.tool);
}
console.log("done");
'''

FAKE_NOTIFY = '''#!/usr/bin/env python3
import json, os, pathlib, sys
with (pathlib.Path(os.environ["HOME"])/"notify-calls.jsonl").open("a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "app": os.environ.get("CLAUDE_NOTIFY_APP")})+"\\n")
'''

BLOCKED = ["herdr:blocked", {"active": True, "label": "jev-gate: 承認待ち"}]
UNBLOCKED = ["herdr:blocked", {"active": False}]


def node_strips_types():
    if not NODE:
        return False
    version = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    major, minor = (int(x) for x in version.split(".")[:2])
    return (major, minor) >= (23, 6)


def message(role, *blocks):
    return {"type": "message", "message": {"role": role, "content": list(blocks)}}


def text(value):
    return {"type": "text", "text": value}


@unittest.skipUnless(node_strips_types() or os.environ.get("CI"), "Node 23.6 以上 (TypeScript の型を外して実行できる) が必要")
class PiNotify(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not node_strips_types():
            raise AssertionError("CI では Node 23.6 以上が必要 (TypeScript の型を外して読み込む)")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.home = base / "home"
        self.work = base / "work"
        stub = self.work / "node_modules/@earendil-works/pi-coding-agent"
        stub.mkdir(parents=True)
        (stub / "package.json").write_text('{"name": "@earendil-works/pi-coding-agent", "type": "module", "main": "index.js"}')
        (stub / "index.js").write_text(STUB_PI)
        (self.work / "package.json").write_text('{"type": "module"}')
        for name in ("notify.ts", "jev-gate.ts"):
            shutil.copyfile(EXTENSIONS / name, self.work / name)
        (self.work / "run.mjs").write_text(HARNESS)
        self.notify = self.home / ".local/bin/claude-notify"
        self.notify.parent.mkdir(parents=True)
        self.notify.write_text(FAKE_NOTIFY)
        self.notify.chmod(0o700)
        self.calls_file = self.home / "notify-calls.jsonl"
        search = ":".join(dict.fromkeys([str(Path(JQ).parent) if JQ else "/usr/bin", "/usr/bin", "/bin"]))
        self.env = {"HOME": str(self.home), "PATH": search, "LANG": "C.UTF-8", "JEV_GATE_MODE": "ask"}

    def run_pi(self, steps, mode="tui", idle=True, branch=(), extensions=("notify.ts",), **extra):
        scenario = {"steps": steps, "mode": mode, "idle": idle, "branch": list(branch), "extensions": list(extensions)}
        result = subprocess.run([NODE, "--disable-warning=ExperimentalWarning", "run.mjs", json.dumps(scenario)],
                                cwd=self.work, env=dict(self.env, **extra), capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines()[-1], "done")

    def notified(self, expected):
        """claude-notify runs detached, so wait for the calls that should come, then a little longer."""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            calls = [json.loads(x) for x in self.calls_file.read_text().splitlines()] if self.calls_file.exists() else []
            if len(calls) >= len(expected):
                break
            time.sleep(0.05)
        time.sleep(0.3)
        calls = [json.loads(x) for x in self.calls_file.read_text().splitlines()] if self.calls_file.exists() else []
        self.assertEqual(calls, [{"args": args, "app": "Pi"} for args in expected])

    def test_waiting_for_the_owner_is_notified(self):
        self.run_pi([{"emit": BLOCKED}, {"emit": UNBLOCKED}])
        self.notified([["notification", "jev-gate: 承認待ち"]])

    def test_settled_run_sends_the_last_reply(self):
        reply = "直しました。\n\n" + "テスト " * 60
        branch = [message("user", text("直して")), message("assistant", text("前の返事")),
                  {"type": "message", "message": {"role": "toolResult", "content": [text("ok")]}},
                  message("assistant", {"type": "thinking", "thinking": "..."}, text(reply))]
        self.run_pi([{"settled": {"aborted": False}}], branch=branch)
        self.notified([["stop", " ".join(reply.split())[:160]]])

    def test_reply_falls_back_to_the_last_assistant_text(self):
        # A run that ends on a tool call (for example one jev-gate terminated) has no text of its own.
        branch = [message("assistant", text("前の返事")), message("assistant", {"type": "toolCall", "name": "bash"})]
        self.run_pi([{"settled": {"aborted": False}}], branch=branch)
        self.notified([["stop", "前の返事"]])
        self.calls_file.unlink()
        self.run_pi([{"settled": {"aborted": False}}])
        self.notified([["stop", ""]])  # claude-notify fills in its default body

    def test_aborted_or_busy_runs_are_not_notified(self):
        self.run_pi([{"settled": {"aborted": True}}], branch=[message("assistant", text("途中"))])
        self.run_pi([{"settled": {"aborted": False}}], idle=False, branch=[message("assistant", text("途中"))])
        self.run_pi([{"emit": UNBLOCKED}])
        self.notified([])

    def test_only_the_tui_notifies(self):
        for mode in ("print", "json", "rpc"):
            with self.subTest(mode=mode):
                self.run_pi([{"emit": BLOCKED}, {"settled": {"aborted": False}}], mode=mode,
                            branch=[message("assistant", text("done"))])
        self.notified([])

    def test_missing_claude_notify_does_not_break_the_agent(self):
        self.notify.unlink()
        self.run_pi([{"emit": BLOCKED}, {"settled": {"aborted": False}}], branch=[message("assistant", text("done"))])

    def test_jev_gate_confirm_reaches_claude_notify(self):
        self.run_pi([{"tool": {"toolName": "bash", "input": {"command": "rm -r build"}}}],
                    extensions=("jev-gate.ts", "notify.ts"), TYPESAFE_API_KEY="SYNTHETIC-ENV",
                    JEV_GATE_INJECTION_GUARD=str(INJECTION_GUARD))
        self.notified([["notification", "jev-gate: 承認待ち"]])


if __name__ == "__main__":
    unittest.main()
