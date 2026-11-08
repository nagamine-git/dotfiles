"""The Pi subagent loader (dot_pi/agent/extensions/subagent.ts) and the agents agents-sync writes for it.

Stub tests load the extension with Node and a stub Pi module. They need Node 23.6 or later, which runs
TypeScript by stripping its types; elsewhere they skip, but not in CI (the CI environment variable).
The real-Pi tests start the installed Pi (pi_real.py: throwaway agent dir, dummy keys, no prompt, so no
model call) and skip on hosts without it. They check that Pi's jiti loads the official example through
subagent.ts, that delegate.ts loads too, that the example reads the generated agents, and that Pi accepts
each generated model string.
"""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
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
EXTENSIONS = ROOT / "dot_pi/agent/extensions"
NODE = shutil.which("node")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi_real  # noqa: E402

LOADER = SourceFileLoader("agents_sync", str(ROOT / "dot_local/bin/executable_agents-sync"))
SYNC = module_from_spec(spec_from_loader(LOADER.name, LOADER))
LOADER.exec_module(SYNC)

STUB_PI = "export const getExamplesPath = () => process.env.FAKE_EXAMPLES;\n"

HARNESS = '''
const tools = [];
const handlers = {};
const notes = [];
const pi = { registerTool: (tool) => tools.push(tool.name), on: (name, fn) => { (handlers[name] ??= []).push(fn); } };
await (await import("./subagent.ts")).default(pi);
for (const fn of handlers.session_start ?? []) await fn({}, { ui: { notify: (message, level) => notes.push([message, level]) } });
console.log(JSON.stringify({ tools, notes }));
'''

# Loaded by the real Pi next to subagent.ts and delegate.ts. Records the tools and the agents the official
# example's own discovery code finds, then Pi answers get_state so the test knows the session started.
PROBE = '''
import { type ExtensionAPI, getExamplesPath } from "@earendil-works/pi-coding-agent";
import * as fs from "node:fs";
import * as path from "node:path";

export default function (pi: ExtensionAPI) {
  pi.on("session_start", async (_event, ctx) => {
    const { discoverAgents } = await import(path.join(getExamplesPath(), "extensions/subagent/agents.ts"));
    const agents = discoverAgents(ctx.cwd, "user").agents
      .map((a: any) => ({ name: a.name, description: a.description, tools: a.tools ?? null, model: a.model ?? null }));
    fs.writeFileSync(path.join(process.env.PROBE_DIR!, "probe.json"),
      JSON.stringify({ all: pi.getAllTools().map((t) => t.name), active: pi.getActiveTools(), agents }));
  });
}
'''


def node_strips_types():
    if not NODE:
        return False
    version = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    major, minor = (int(x) for x in version.split(".")[:2])
    return (major, minor) >= (23, 6)


@unittest.skipUnless(node_strips_types() or os.environ.get("CI"), "Node 23.6 以上 (TypeScript の型を外して実行できる) が必要")
class SubagentLoaderStub(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not node_strips_types():
            raise AssertionError("CI では Node 23.6 以上が必要 (TypeScript の型を外して読み込む)")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.work, self.examples = base / "work", base / "examples"
        stub = self.work / "node_modules/@earendil-works/pi-coding-agent"
        stub.mkdir(parents=True)
        (stub / "package.json").write_text('{"name": "@earendil-works/pi-coding-agent", "type": "module", "main": "index.js"}')
        (stub / "index.js").write_text(STUB_PI)
        (self.work / "package.json").write_text('{"type": "module"}')
        shutil.copyfile(EXTENSIONS / "subagent.ts", self.work / "subagent.ts")
        (self.work / "run.mjs").write_text(HARNESS)
        self.example = self.examples / "extensions/subagent"

    def load(self):
        result = subprocess.run([NODE, "--disable-warning=ExperimentalWarning", "run.mjs"], cwd=self.work, timeout=60,
                                env={"PATH": os.environ["PATH"], "FAKE_EXAMPLES": str(self.examples)},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_the_example_registers_its_tool_with_its_own_relative_imports(self):
        self.example.mkdir(parents=True)
        (self.example / "agents.ts").write_text('export const toolName = (): string => "subagent";\n')
        (self.example / "index.ts").write_text('import { toolName } from "./agents.ts";\n'
                                               'export default async function (pi: any) { pi.registerTool({ name: toolName() }); }\n')
        self.assertEqual(self.load(), {"tools": ["subagent"], "notes": []})

    def test_a_missing_or_broken_example_warns_and_registers_nothing(self):
        out = self.load()
        self.assertEqual(out["tools"], [])
        [(message, level)] = out["notes"]
        self.assertEqual(level, "warning")
        self.assertIn(str(self.example / "index.ts"), message)
        self.example.mkdir(parents=True)
        (self.example / "index.ts").write_text('export default function () { throw new Error("example changed"); }\n')
        out = self.load()
        self.assertEqual(out["tools"], [])
        self.assertIn("example changed", out["notes"][0][0])


@unittest.skipUnless(pi_real.available(), "Pi が入っていない (am5-itx だけ)")
class SubagentWithRealPi(unittest.TestCase):
    def generated_agents(self):
        out = {}
        for md in sorted((ROOT / "dot_claude/agents").glob("*.md")):
            meta, body = SYNC.parse_agent_md(md.read_text(encoding="utf-8"))
            out[md.stem] = (meta, SYNC.render_pi_agent(meta, body, md.name)[0])
        return out

    def test_pi_loads_the_official_example_and_reads_the_generated_agents(self):
        agents = self.generated_agents()
        files = {"extensions/subagent.ts": (EXTENSIONS / "subagent.ts").read_text(),
                 "extensions/delegate.ts": (EXTENSIONS / "delegate.ts").read_text(),
                 "extensions/zz-probe.ts": PROBE}
        files.update({"agents/%s.md" % name: text for name, (_meta, text) in agents.items()})
        responses, stderr, back = pi_real.rpc(files, [{"type": "get_state"}], read_back=["probe.json"])
        self.assertTrue(responses.get("c0", {}).get("success"), stderr)
        self.assertIsNotNone(back["probe.json"], stderr)
        probe = json.loads(back["probe.json"])
        self.assertIn("subagent", probe["active"])
        self.assertIn("delegate", probe["active"])
        found = {a["name"]: a for a in probe["agents"]}
        self.assertEqual(sorted(found), sorted(meta["name"] for meta, _text in agents.values()))
        for meta, _text in agents.values():
            self.assertEqual(found[meta["name"]]["description"], meta["description"])
        self.assertEqual(found["Explore"]["tools"], ["read", "bash", "grep", "find", "ls"])  # disallowedTools を守る
        self.assertEqual(found["coder"]["model"], "anthropic/claude-opus-5-5:xhigh")
        self.assertIsNone(found["general-purpose"]["tools"])

    def test_pi_accepts_every_generated_model_with_its_thinking(self):
        models = {json.loads(line.split(": ", 1)[1]) for _meta, text in self.generated_agents().values()
                  for line in text.splitlines() if line.startswith("model: ")}
        self.assertTrue(models)
        for model in models:
            with self.subTest(model=model):
                responses, stderr, _ = pi_real.rpc({}, [{"type": "get_state"}], args=["--model", model])
                self.assertEqual(pi_real.model_of(responses["c0"]), tuple(model.rsplit(":", 1)), stderr)


if __name__ == "__main__":
    unittest.main()
