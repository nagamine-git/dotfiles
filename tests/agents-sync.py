"""No model calls: agents-sync runs against disposable homes and fake claude/codex executables."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

try:
    import tomllib
except ImportError:  # Python < 3.11 (macOS system python): skip the TOML round-trip checks
    tomllib = None

sys.dont_write_bytecode = True  # dot_local/bin に __pycache__ を作ると chezmoi が ~/.local/bin へ配ってしまう
ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_agents-sync"
LOADER = SourceFileLoader("agents_sync", str(SCRIPT))
SYNC = module_from_spec(spec_from_loader(LOADER.name, LOADER))
LOADER.exec_module(SYNC)

AGENT_MD = """---
name: Explore
description: Read-only search agent — use "medium" or "very thorough".
disallowedTools: Agent, Edit, Write, NotebookEdit
effort: low
---

読み取り専用の調査エージェント。

- 見つからなかったものは「見つからなかった」と書く
"""


def write(path, text="", mode=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode:
        path.chmod(mode)
    return path


class Subagents(unittest.TestCase):
    def test_frontmatter_keeps_colons_and_quotes_in_values(self):
        meta, body = SYNC.parse_agent_md(AGENT_MD)
        self.assertEqual(meta["name"], "Explore")
        self.assertEqual(meta["description"], 'Read-only search agent — use "medium" or "very thorough".')
        self.assertEqual(meta["effort"], "low")
        self.assertTrue(body.startswith("読み取り専用"))

    def test_quoted_yaml_scalars_are_unwrapped(self):
        meta, _ = SYNC.parse_agent_md("---\nname: 'a'\ndescription: \"b: c\"\n---\nbody\n")
        self.assertEqual((meta["name"], meta["description"]), ("a", "b: c"))

    def test_no_frontmatter_uses_the_whole_text_as_body(self):
        meta, body = SYNC.parse_agent_md("just text\n")
        self.assertEqual((meta, body), ({}, "just text\n"))

    def test_render_maps_effort_and_never_sets_a_model(self):
        meta, body = SYNC.parse_agent_md(AGENT_MD.replace("effort: low", "effort: xhigh\nmodel: claude-sonnet-5-5"))
        out = SYNC.render_codex_agent(meta, body, "Explore.md")
        self.assertTrue(out.startswith(SYNC.GENERATED_MARK))
        self.assertIn('model_reasoning_effort = "xhigh"', out)
        self.assertNotIn("\nmodel =", out)
        self.assertIn("disallowedTools", out)  # 対応のない項目はコメントで残す

    def test_max_effort_is_capped_at_xhigh(self):
        meta, body = SYNC.parse_agent_md(AGENT_MD.replace("effort: low", "effort: max"))
        self.assertIn('model_reasoning_effort = "xhigh"', SYNC.render_codex_agent(meta, body, "x.md"))

    @unittest.skipIf(tomllib is None, "tomllib needs Python 3.11+")
    def test_generated_toml_round_trips_awkward_text(self):
        body = "手順:\n\n- パス C:\\temp と \"\"\" と ''' を含む\n- 末尾の空白なし\n"
        meta = {"name": "Awk", "description": 'He said "hi" \\ bye', "effort": "medium"}
        data = tomllib.loads(SYNC.render_codex_agent(meta, body, "Awk.md"))
        self.assertEqual(data["name"], "Awk")
        self.assertEqual(data["description"], 'He said "hi" \\ bye')
        self.assertEqual(data["developer_instructions"].strip(), body.strip())
        self.assertEqual(data["model_reasoning_effort"], "medium")

    @unittest.skipIf(tomllib is None, "tomllib needs Python 3.11+")
    def test_real_claude_agents_all_convert_to_valid_toml(self):
        names = []
        for md in sorted((ROOT / "dot_claude/agents").glob("*.md")):
            meta, body = SYNC.parse_agent_md(md.read_text(encoding="utf-8"))
            data = tomllib.loads(SYNC.render_codex_agent(meta, body, md.name))
            self.assertEqual(data["name"], meta["name"])
            self.assertTrue(data["developer_instructions"].strip())
            self.assertNotIn("model", data)
            names.append(data["name"])
        self.assertIn("coder", names)

    def test_sync_writes_new_overwrites_generated_and_backs_up_foreign_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src, dest = tmp / "claude-agents", tmp / "codex-agents"
            write(src / "Explore.md", AGENT_MD)
            write(src / "coder.md", AGENT_MD.replace("name: Explore", "name: coder"))
            write(dest / "coder.toml", 'name = "coder"\n')  # 別ツールが作った手書き/取り込みのファイル
            first = SYNC.sync_subagents(src, dest)
            self.assertTrue((dest / "Explore.toml").read_text().startswith(SYNC.GENERATED_MARK))
            self.assertTrue((dest / "coder.toml.pre-agents-sync.bak").exists())
            self.assertEqual((dest / "coder.toml.pre-agents-sync.bak").read_text(), 'name = "coder"\n')
            self.assertTrue(any("coder" in line for line in first))
            # 2 回目は何も変わらず、バックアップも作り直さない
            before = (dest / "coder.toml").stat().st_mtime_ns
            second = SYNC.sync_subagents(src, dest)
            self.assertEqual(second, [])
            self.assertEqual((dest / "coder.toml").stat().st_mtime_ns, before)
            # 元を直すと生成物だけ更新される
            write(src / "Explore.md", AGENT_MD.replace("effort: low", "effort: high"))
            SYNC.sync_subagents(src, dest)
            self.assertIn('"high"', (dest / "Explore.toml").read_text())
            self.assertFalse((dest / "Explore.toml.pre-agents-sync.bak").exists())

    def test_stale_generated_files_are_reported_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            src, dest = tmp / "a", tmp / "b"
            write(src / "Keep.md", AGENT_MD.replace("Explore", "Keep"))
            write(dest / "Gone.toml", SYNC.GENERATED_MARK + "\nname = \"Gone\"\n")
            write(dest / "Mine.toml", 'name = "Mine"\n')
            messages = SYNC.sync_subagents(src, dest)
            self.assertTrue((dest / "Gone.toml").exists())
            self.assertTrue(any("Gone" in m and "stale" in m for m in messages))
            self.assertFalse(any("Mine" in m for m in messages))

    def test_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            write(tmp / "a/Explore.md", AGENT_MD)
            messages = SYNC.sync_subagents(tmp / "a", tmp / "b", dry_run=True)
            self.assertTrue(messages)
            self.assertFalse((tmp / "b").exists())


class Skills(unittest.TestCase):
    def make(self, tmp):
        tmp = Path(tmp)
        agents, claude = tmp / "home/.agents/skills", tmp / "home/.claude/skills"
        claude.mkdir(parents=True)
        return agents, claude

    def skill(self, base, name, body="x"):
        write(base / name / "SKILL.md", "---\nname: %s\ndescription: d\n---\n%s\n" % (name, body))

    def test_missing_links_are_created_relative_and_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents, claude = self.make(tmp)
            self.skill(agents, "alpha")
            SYNC.sync_skills(agents, claude)
            link = claude / "alpha"
            self.assertTrue(link.is_symlink())
            self.assertFalse(os.path.isabs(os.readlink(link)))
            self.assertEqual(link.resolve(), (agents / "alpha").resolve())
            self.assertTrue((link / "SKILL.md").exists())

    def test_identical_real_directory_is_replaced_and_different_one_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents, claude = self.make(tmp)
            self.skill(agents, "same")
            self.skill(claude, "same")
            self.skill(agents, "diverged", "codex flavour")
            self.skill(claude, "diverged", "claude flavour")
            messages = SYNC.sync_skills(agents, claude)
            self.assertTrue((claude / "same").is_symlink())
            self.assertFalse((claude / "diverged").is_symlink())
            self.assertIn("claude flavour", (claude / "diverged/SKILL.md").read_text())
            self.assertTrue(any("diverged" in m for m in messages))

    def test_foreign_symlinks_hidden_and_import_artifacts_are_not_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents, claude = self.make(tmp)
            self.skill(agents, "other")
            self.skill(agents, "source-command-foo")
            self.skill(agents, "synced")
            write(agents / ".system/SKILL.md", "x")
            write(agents / "no-skill-md/readme.txt", "x")
            elsewhere = Path(tmp) / "elsewhere"
            self.skill(elsewhere, "other")
            (claude / "other").symlink_to(elsewhere / "other")
            SYNC.sync_skills(agents, claude)
            self.assertEqual((claude / "other").resolve(), (elsewhere / "other").resolve())
            for name in ("source-command-foo", "synced", ".system", "no-skill-md"):
                self.assertFalse((claude / name).exists() or (claude / name).is_symlink(), name)

    def test_second_run_is_a_no_op_and_dry_run_changes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            agents, claude = self.make(tmp)
            self.skill(agents, "alpha")
            self.assertTrue(SYNC.sync_skills(agents, claude, dry_run=True))
            self.assertFalse((claude / "alpha").exists())
            SYNC.sync_skills(agents, claude)
            self.assertEqual(SYNC.sync_skills(agents, claude), [])

    def test_missing_agents_dir_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(SYNC.sync_skills(Path(tmp) / "none", Path(tmp) / "claude"), [])


class McpPlanning(unittest.TestCase):
    SHARED = {
        "ctx": {"command": "npx", "args": ["-y", "ctx"]},
        "web": {"type": "http", "url": "https://example.com/mcp"},
        "key": {"command": "npx", "args": ["key"], "secrets": ["API_KEY"]},
    }

    def test_normalisation_makes_both_tools_comparable(self):
        shared = SYNC.norm_shared(self.SHARED["ctx"])
        self.assertEqual(shared, ("stdio", "npx", ("-y", "ctx")))
        self.assertEqual(SYNC.norm_claude({"type": "stdio", "command": "npx", "args": ["-y", "ctx"], "env": {}}), shared)
        self.assertEqual(SYNC.norm_claude({"command": "npx", "args": ["-y", "ctx"]}), shared)
        self.assertEqual(SYNC.norm_codex({"transport": {"type": "stdio", "command": "npx", "args": ["-y", "ctx"]}}), shared)
        http = SYNC.norm_shared(self.SHARED["web"])
        self.assertEqual(SYNC.norm_claude({"type": "http", "url": "https://example.com/mcp"}), http)
        self.assertEqual(SYNC.norm_codex({"transport": {"type": "streamable_http", "url": "https://example.com/mcp"}}), http)

    def test_plan_add_ok_fix_and_drift(self):
        current = {
            "ctx": {"kind": ("stdio", "npx", ("-y", "OLD")), "has_env": False},
            "key": {"kind": ("stdio", "npx", ("key", "--extra")), "has_env": True},
        }
        plan = SYNC.plan_mcp(self.SHARED, current)
        self.assertEqual(plan["ctx"], "fix")        # 秘密も env も無いので入れ替えてよい
        self.assertEqual(plan["web"], "add")
        self.assertEqual(plan["key"], "drift")      # env を持つものは触らず報告だけ
        again = SYNC.plan_mcp(self.SHARED, {"ctx": {"kind": SYNC.norm_shared(self.SHARED["ctx"]), "has_env": False}})
        self.assertEqual(again["ctx"], "ok")

    def test_secret_servers_are_never_added_with_values(self):
        plan = SYNC.plan_mcp(self.SHARED, {})
        self.assertEqual(plan["key"], "needs-secret")

    def test_servers_only_in_the_tool_are_ignored(self):
        plan = SYNC.plan_mcp(self.SHARED, {"extra": {"kind": ("stdio", "x", ()), "has_env": False}})
        self.assertNotIn("extra", plan)


FAKE_CLAUDE = """#!/bin/sh
echo "claude $*" >> "$FAKE_LOG"
exit 0
"""

FAKE_CODEX = """#!/bin/sh
echo "codex $*" >> "$FAKE_LOG"
if [ "$1" = mcp ] && [ "$2" = list ]; then cat "$FAKE_CODEX_LIST"; fi
exit 0
"""


class McpEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name).resolve()
        self.home = tmp / "home"
        self.bin = tmp / "bin"
        self.log = tmp / "log.txt"
        self.codex_list = tmp / "codex-list.json"
        write(self.bin / "claude", FAKE_CLAUDE, 0o755)
        write(self.bin / "codex", FAKE_CODEX, 0o755)
        write(self.home / ".agents/mcp.json", json.dumps({"mcpServers": {
            "ctx": {"command": "npx", "args": ["-y", "ctx"]},
            "web": {"type": "http", "url": "https://example.com/mcp"},
            "key": {"command": "npx", "args": ["key"], "secrets": ["API_KEY"]},
            "pw": {"command": "npx", "args": ["@playwright/mcp@latest"]},
        }}))
        write(self.home / ".claude.json", json.dumps({"mcpServers": {
            "ctx": {"type": "stdio", "command": "npx", "args": ["-y", "ctx"], "env": {}},
            "key": {"type": "stdio", "command": "npx", "args": ["key"], "env": {"API_KEY": "SECRET-VALUE-1"}},
            "pw": {"type": "stdio", "command": "npx", "args": ["@playwright/mcp@latest"]},
        }}))
        write(self.codex_list, json.dumps([
            {"name": "ctx", "transport": {"type": "stdio", "command": "npx", "args": ["-y", "ctx"], "env": None}},
            {"name": "key", "transport": {"type": "stdio", "command": "npx", "args": ["key"],
                                          "env": {"API_KEY": "SECRET-VALUE-2"}}},
            {"name": "pw", "transport": {"type": "stdio", "command": "npx", "args": ["server-playwright-typo"]}},
            {"name": "internal", "transport": {"type": "stdio", "command": "/opt/x", "args": []}},
        ]))

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self, *args):
        env = {**os.environ, "HOME": str(self.home), "PATH": "%s:%s" % (self.bin, os.environ["PATH"]),
               "FAKE_LOG": str(self.log), "FAKE_CODEX_LIST": str(self.codex_list)}
        for var in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
            env.pop(var, None)
        result = subprocess.run([sys.executable, str(SCRIPT), "mcp", *args], env=env, capture_output=True,
                                text=True, cwd=str(self.home))
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return result, calls

    def test_adds_missing_fixes_drift_and_never_touches_secrets(self):
        result, calls = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('claude mcp add-json -s user web {"type": "http", "url": "https://example.com/mcp"}', calls)
        self.assertIn("codex mcp add web --url https://example.com/mcp", calls)
        self.assertIn("codex mcp remove pw", calls)
        self.assertIn("codex mcp add pw -- npx @playwright/mcp@latest", calls)
        self.assertFalse([c for c in calls if " key" in c and ("add" in c or "remove" in c)])
        self.assertFalse([c for c in calls if "internal" in c])
        everything = result.stdout + result.stderr + "".join(calls)
        self.assertNotIn("SECRET-VALUE", everything)

    def test_dry_run_calls_neither_tool_for_changes(self):
        result, calls = self.run_sync("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([c for c in calls if " add" in c or " remove" in c], [])
        self.assertIn("web", result.stdout)

    def test_missing_executables_are_skipped_without_failing(self):
        (self.bin / "codex").unlink()
        env = {**os.environ, "HOME": str(self.home), "PATH": str(self.bin),
               "FAKE_LOG": str(self.log), "FAKE_CODEX_LIST": str(self.codex_list)}
        for var in ("CLAUDE_CONFIG_DIR", "CODEX_HOME"):
            env.pop(var, None)
        result = subprocess.run([sys.executable, str(SCRIPT), "mcp"], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("codex", result.stdout + result.stderr)


class Cli(unittest.TestCase):
    def test_unknown_subcommand_fails(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "nope"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
