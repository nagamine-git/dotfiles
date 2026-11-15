"""auto-reload: an idle interactive Pi reloads when its extensions, MCP servers or tiers changed. Stub Pi, no network."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "home/dot_pi/agent/extensions/auto-reload.ts"
NODE = shutil.which("node")
HARNESS = r'''
import fs from "node:fs";
const s = JSON.parse(process.argv[2]);
const handlers = {}, commands = {}, sent = [], notes = [];
let reloads = 0;
const pi = { on: (n, f) => { handlers[n] = f; }, registerCommand: (n, o) => { commands[n] = o.handler; },
  sendUserMessage: (text, opts) => sent.push([text, opts]) };
(await import("./auto-reload.ts")).default(pi);
const ctx = { mode: s.mode ?? "tui", isIdle: () => s.idle ?? true, ui: { notify: (m) => notes.push(m) }, reload: async () => { reloads++; } };
for (const step of s.steps) {
  if (step.touch) { const t = new Date(Date.now() + 5000); fs.utimesSync(step.touch, t, t); continue; }
  await handlers.agent_settled({ aborted: step.aborted ?? false }, ctx);
}
for (const [text] of sent) await commands[text.slice(1)]("", ctx);
console.log(JSON.stringify({ sent, notes, reloads }));
'''


def supports_types():
    if not NODE:
        return False
    v = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.lstrip("v")
    return tuple(map(int, v.split(".")[:2])) >= (23, 6)


@unittest.skipUnless(supports_types() or os.environ.get("CI"), "Node 23.6 以上が必要")
class AutoReload(unittest.TestCase):
    def setUp(self):
        if not supports_types():
            self.fail("CI requires Node 23.6+")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.work = Path(tmp.name)
        self.agent = self.work / "agent"
        (self.agent / "extensions/pkg").mkdir(parents=True)
        for rel in ("extensions/a.ts", "extensions/pkg/index.ts", "mcp.json", "model-tiers.json", "settings.json"):
            (self.agent / rel).write_text("x")
        (self.work / "package.json").write_text('{"type":"module"}')
        shutil.copyfile(EXTENSION, self.work / "auto-reload.ts")
        (self.work / "run.mjs").write_text(HARNESS)

    def run_ext(self, steps, **s):
        env = {"HOME": str(self.work), "PATH": "/usr/bin:/bin", "PI_CODING_AGENT_DIR": str(self.agent)}
        out = subprocess.run([NODE, "run.mjs", json.dumps(dict(s, steps=steps))], env=env, cwd=self.work, capture_output=True, text=True, timeout=20)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_nothing_changed_nothing_happens(self):
        self.assertEqual(self.run_ext([{}, {}])["reloads"], 0)

    def test_a_changed_watched_file_reloads_once_when_idle(self):
        for rel in ("extensions/a.ts", "extensions/pkg/index.ts", "mcp.json", "model-tiers.json"):
            with self.subTest(rel=rel):
                out = self.run_ext([{"touch": str(self.agent / rel)}, {}, {}])
                self.assertEqual((out["sent"], out["reloads"]), ([["/auto-reload-now", {"expandPromptTemplates": True}]], 1))

    def test_settings_written_by_pi_and_busy_aborted_or_print_runs_do_not_reload(self):
        self.assertEqual(self.run_ext([{"touch": str(self.agent / "settings.json")}, {}])["reloads"], 0)
        touch = {"touch": str(self.agent / "extensions/a.ts")}
        self.assertEqual(self.run_ext([touch, {"aborted": True}])["reloads"], 0)
        self.assertEqual(self.run_ext([touch, {}], idle=False)["reloads"], 0)
        self.assertEqual(self.run_ext([touch, {}], mode="print")["reloads"], 0)


if __name__ == "__main__":
    unittest.main()
