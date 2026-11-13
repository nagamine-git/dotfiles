"""The Pi delegate extension, loaded by Node with stub Pi modules and fake claude / codex executables.

Needs Node 23.6 or later, which runs TypeScript by stripping its types. Elsewhere it skips, but
not in CI (the CI environment variable): there an older Node fails the run. Never calls a model.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "dot_pi/agent/extensions/delegate.ts"
NODE = shutil.which("node")
HERDR = {"HERDR_ENV": "1", "HERDR_PANE_ID": "p1", "HERDR_TAB_ID": "t1", "HERDR_WORKSPACE_ID": "w1",
         "HERDR_SOCKET_PATH": "/tmp/herdr.sock", "HERDR_BIN_PATH": "/usr/bin/herdr"}

STUBS = {
    "@earendil-works/pi-ai": "export const StringEnum = (values) => ({ type: 'string', enum: values });\n",
    "typebox": "export const Type = { Object: (p) => ({ type: 'object', properties: p }),\n"
               "  String: (o) => ({ type: 'string', ...o }), Boolean: (o) => ({ type: 'boolean', ...o }),\n"
               "  Optional: (s) => ({ ...s, optional: true }) };\n",
}

# Registers the extension, runs the delegate tool once (aborting it when asked) and prints the result.
HARNESS = '''
const scenario = JSON.parse(process.argv[2]);
const tools = {};
(await import("./delegate.ts")).default({ registerTool: (tool) => { tools[tool.name] = tool; } });
const controller = new AbortController();
if (scenario.abortAfterMs) setTimeout(() => controller.abort(), scenario.abortAfterMs);
const started = Date.now();
const result = await tools.delegate.execute("call-1", scenario.params, controller.signal, undefined, { cwd: scenario.cwd });
console.log(JSON.stringify({ result, ms: Date.now() - started, tool: { ...tools.delegate, execute: undefined } }));
'''

# Records how it was started, then answers like the real CLI would for FAKE_MODE.
FAKE = '''#!/usr/bin/env python3
import json, os, sys, time
name = os.path.basename(sys.argv[0])
env = {k: v for k, v in os.environ.items() if k.startswith("HERDR_") or k in ("CLAUDE_NOTIFY_PHONE", "KEEP_ME")}
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"name": name, "argv": sys.argv[1:], "cwd": os.getcwd(), "env": env, "pid": os.getpid()}) + "\\n")
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "sleep":
    time.sleep(60)
if name == "claude":
    if mode == "garbage":
        print("not json"); sys.exit(1)
    if mode == "error":
        print("rate limited", file=sys.stderr)
        print(json.dumps({"type": "result", "is_error": True, "result": "API Error"})); sys.exit(1)
    result = "完了しました。" * 20000 if mode == "big" else "done"
    if mode == "secrets":
        result = open(os.environ["FAKE_SECRETS"]).read()
    print(json.dumps({"type": "result", "is_error": False, "result": result, "total_cost_usd": 0.0123}))
else:
    if mode == "fail":
        print("sandbox: denied", file=sys.stderr); sys.exit(2)
    out = sys.argv[sys.argv.index("-o") + 1]
    with open(out, "w") as f:
        f.write("codex answer\\n")
'''


def node_strips_types():
    if not NODE:
        return False
    version = subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    major, minor = (int(x) for x in version.split(".")[:2])
    return (major, minor) >= (23, 6)


@unittest.skipUnless(node_strips_types() or os.environ.get("CI"), "Node 23.6 以上 (TypeScript の型を外して実行できる) が必要")
class Delegate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not node_strips_types():
            raise AssertionError("CI では Node 23.6 以上が必要 (TypeScript の型を外して読み込む)")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.work, self.bin, self.cwd = base / "work", base / "bin", base / "project"
        for name, code in STUBS.items():
            pkg = self.work / "node_modules" / name
            pkg.mkdir(parents=True)
            (pkg / "package.json").write_text(json.dumps({"name": name, "type": "module", "main": "index.js"}))
            (pkg / "index.js").write_text(code)
        (self.work / "package.json").write_text('{"type": "module"}')
        shutil.copyfile(EXTENSION, self.work / "delegate.ts")
        (self.work / "run.mjs").write_text(HARNESS)
        self.bin.mkdir()
        for name in ("claude", "codex"):
            (self.bin / name).write_text(FAKE)
            (self.bin / name).chmod(0o755)
        (self.cwd / "sub").mkdir(parents=True)
        self.log = base / "calls.jsonl"
        self.tmpdir = base / "tmp"
        self.tmpdir.mkdir()
        self.env = dict(HERDR, PATH="%s:%s:/usr/bin:/bin" % (self.bin, Path(NODE).parent), HOME=str(base),
                        FAKE_LOG=str(self.log), KEEP_ME="1", TMPDIR=str(self.tmpdir), LANG="C.UTF-8")

    def delegate(self, harness, task="fix it", timeout=60, abort_after_ms=None, ctx_cwd=None, **extra):
        params = {"harness": harness, "task": task}
        for key in ("cwd", "chrome"):
            if key in extra:
                params[key] = extra.pop(key)
        scenario = {"params": params, "cwd": str(ctx_cwd or self.cwd), "abortAfterMs": abort_after_ms}
        result = subprocess.run([NODE, "--disable-warning=ExperimentalWarning", "run.mjs", json.dumps(scenario)],
                                cwd=self.work, env=dict(self.env, **extra), capture_output=True, text=True, timeout=timeout)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])

    def calls(self):
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def text(self, out):
        return out["result"]["content"][0]["text"]

    def test_claude_gets_the_task_and_no_model_effort_or_permission_flags(self):
        out = self.delegate("claude", task="--permission-mode=bypassPermissions はタスクの一部")
        [call] = self.calls()
        self.assertEqual(call["argv"], ["-p", "Task: --permission-mode=bypassPermissions はタスクの一部", "--output-format", "json"])
        self.assertEqual(call["cwd"], str(self.cwd))
        self.assertEqual(call["env"], {"CLAUDE_NOTIFY_PHONE": "never", "KEEP_ME": "1"})  # herdr の変数は渡らない
        self.assertFalse(out["result"]["isError"])
        self.assertTrue(self.text(out).startswith("done"))
        self.assertIn("見積もり: $0.0123", self.text(out))
        self.assertEqual(out["result"]["details"]["costUsd"], 0.0123)

    def test_chrome_adds_the_flag_only_when_asked_and_only_for_claude(self):
        out = self.delegate("claude", chrome=True)
        [call] = self.calls()
        self.assertEqual(call["argv"], ["-p", "Task: fix it", "--output-format", "json", "--chrome"])
        self.assertTrue(out["result"]["details"]["chrome"])
        self.delegate("claude", chrome=False)
        self.assertNotIn("--chrome", self.calls()[-1]["argv"])
        out = self.delegate("codex", chrome=True)
        self.assertTrue(out["result"]["isError"])
        self.assertIn("chrome is for claude only", self.text(out))
        self.assertEqual(len(self.calls()), 2)  # codex は起動しない

    def test_codex_runs_in_workspace_write_and_returns_its_last_message(self):
        out = self.delegate("codex", cwd="sub")
        [call] = self.calls()
        sub = str(self.cwd / "sub")
        self.assertEqual(call["argv"][:5], ["exec", "-s", "workspace-write", "-C", sub])
        self.assertEqual((call["argv"][5], call["argv"][7:]), ("-o", ["Task: fix it"]))
        self.assertEqual(call["cwd"], sub)
        self.assertEqual(call["env"], {"CLAUDE_NOTIFY_PHONE": "never", "KEEP_ME": "1"})
        self.assertEqual(self.text(out), "codex answer")
        self.assertFalse(out["result"]["isError"])
        self.assertEqual(list(self.tmpdir.iterdir()), [])  # -o の一時ディレクトリは消える

    def test_failures_return_the_reason_and_stderr(self):
        out = self.delegate("codex", FAKE_MODE="fail")
        self.assertTrue(out["result"]["isError"])
        self.assertIn("exited with 2", self.text(out))
        self.assertIn("sandbox: denied", self.text(out))
        out = self.delegate("claude", FAKE_MODE="error")
        self.assertTrue(out["result"]["isError"])
        self.assertIn("API Error", self.text(out))
        self.assertIn("rate limited", self.text(out))
        out = self.delegate("claude", FAKE_MODE="garbage")
        self.assertTrue(out["result"]["isError"])
        self.assertIn("not json", self.text(out))

    def test_missing_harness_or_directory_is_explained(self):
        (self.bin / "claude").unlink()
        out = self.delegate("claude")
        self.assertTrue(out["result"]["isError"])
        self.assertIn("claude is not on PATH", self.text(out))
        out = self.delegate("codex", cwd="missing")
        self.assertIn("is not a directory", self.text(out))
        self.assertEqual(self.calls(), [])

    def refused(self, out, why):
        self.assertTrue(out["result"]["isError"])
        self.assertIn(why, self.text(out))

    def test_cwd_must_stay_inside_pis_working_directory(self):
        home = Path(self.env["HOME"])
        (home / "elsewhere").mkdir()
        (self.cwd / "out").symlink_to(home / "elsewhere")
        for cwd in ("..", str(home / "elsewhere"), "/tmp", "out", "sub/../.."):
            with self.subTest(cwd=cwd):
                self.refused(self.delegate("codex", cwd=cwd), "outside")
        self.assertEqual(self.calls(), [])

    def test_at_and_file_paths_are_refused(self):
        # jev-gate checks the directory as ~ expanded and realpath'd; delegate.ts resolves only that way.
        for cwd in ("@sub", "file://%s" % (self.cwd / "sub"), "file:sub"):
            with self.subTest(cwd=cwd):
                self.refused(self.delegate("codex", cwd=cwd), "@ or file:")
        self.assertEqual(self.calls(), [])

    def test_home_and_the_dot_directories_under_it_are_refused(self):
        home = Path(self.env["HOME"])
        (home / ".ssh").mkdir()
        self.refused(self.delegate("codex", ctx_cwd=home), "home directory")
        self.refused(self.delegate("codex", ctx_cwd=home, cwd=".ssh"), ".ssh")
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.delegate("codex", ctx_cwd=home, cwd="project")["result"]["isError"])

    def test_inside_a_dot_directory_pis_own_tree_is_allowed(self):
        home = Path(self.env["HOME"])
        repo = home / ".local/share/chezmoi"
        (repo / "sub").mkdir(parents=True)
        for cwd in (".", "sub"):
            with self.subTest(cwd=cwd):
                self.assertFalse(self.delegate("codex", ctx_cwd=repo, cwd=cwd)["result"]["isError"])
        self.refused(self.delegate("codex", ctx_cwd=repo, cwd=".."), "outside")

    def test_keys_and_tokens_in_the_answer_are_masked(self):
        # Synthetic look-alikes, assembled here so no real-looking secret sits in the repository.
        block_body = "synthetic-not-a-real-block-" + "x" * 20
        secrets = ["-----BEGIN OPENSSH " + "PRIVATE KEY-----\n" + block_body + "\n-----END OPENSSH " + "PRIVATE KEY-----",
                   "gh" + "p_" + "A" * 36, "gh" + "o_" + "B" * 36, "github" + "_pat_" + "C" * 40,
                   "sk" + "-ant-" + "D" * 40, "sk" + "-" + "E" * 40, "op" + "s_" + "eyJ" + "F" * 60,
                   "xo" + "xb-" + "1234-5678-" + "G" * 20, "AK" + "IA" + "H" * 16]
        path = Path(self.env["HOME"]) / "answer.txt"
        path.write_text("見つけた値:\n" + "\n".join(secrets) + "\nふつうの文 sk-learn と task-runner は残る\n")
        out = self.delegate("claude", FAKE_MODE="secrets", FAKE_SECRETS=str(path))
        shown = self.text(out)
        for secret in secrets[1:]:
            self.assertNotIn(secret, shown)
        self.assertNotIn(block_body, shown)
        self.assertIn("ふつうの文 sk-learn と task-runner は残る", shown)
        self.assertIn("9 か所", shown)
        self.assertEqual(out["result"]["details"]["redacted"], 9)
        self.assertNotIn("伏せ", self.text(self.delegate("claude")))

    def test_long_answers_are_cut_at_about_50_kb_on_a_character_boundary(self):
        out = self.delegate("claude", FAKE_MODE="big")
        answer = self.text(out).split("\n…(")[0]
        self.assertLessEqual(len(answer.encode("utf-8")), 50 * 1024)
        self.assertGreater(len(answer.encode("utf-8")), 50 * 1024 - 3)
        self.assertNotIn("\ufffd", answer)
        self.assertIn("more bytes cut", self.text(out))

    def test_abort_stops_the_child(self):
        for harness in ("claude", "codex"):
            with self.subTest(harness=harness):
                self.log.unlink(missing_ok=True)
                out = self.delegate(harness, FAKE_MODE="sleep", abort_after_ms=500, timeout=30)
                self.assertTrue(out["result"]["isError"])
                self.assertIn("aborted", self.text(out))
                self.assertLess(out["ms"], 10_000)
                with self.assertRaises(ProcessLookupError):
                    os.kill(self.calls()[0]["pid"], 0)

    def test_description_says_when_to_pick_each_harness(self):
        tool = self.delegate("codex")["tool"]
        guidelines = " ".join(tool["promptGuidelines"])
        for word in ("claude.ai connectors", "Slack", "Google", "Claude Docs", "Chrome", "independent review", "OS sandbox"):
            self.assertIn(word, guidelines)
        self.assertEqual(tool["parameters"]["properties"]["harness"]["enum"], ["claude", "codex"])


if __name__ == "__main__":
    unittest.main()
