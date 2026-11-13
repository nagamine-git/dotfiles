"""Autonomy's evidence must be trustworthy: shared policy and CI failure propagation.

Uses disposable HOME/source/state and a fake chezmoi for the workflow step. No owner
configuration, secrets, network or models. The real chezmoi only renders text templates.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/chezmoi.yml"
CHEZMOI = shutil.which("chezmoi")
BASH = shutil.which("bash")


def dry_run_step(text):
    """Extract this one known YAML block, not a general YAML parser."""
    match = re.search(r"^      - name: Dry-run apply \(template rendering\)\n((?:(?: {8}[^\n]*|)\n)*)", text, re.M)
    if not match:
        raise AssertionError("CI dry-run step is missing or needs its test updated")
    block = match[1]
    shell = re.search(r"^        shell: (.+)$", block, re.M)
    script = block.split("        run: |\n", 1)[1]
    return shell[1].strip() if shell else None, "\n".join(line[10:] for line in script.splitlines())


@unittest.skipUnless(BASH, "bash is required")
class WorkflowEvidence(unittest.TestCase):
    def execute(self, text, exit_code):
        shell, script = dry_run_step(text)
        self.assertIn(shell, (None, "bash"))
        # GitHub's unspecified Linux shell is bash -e; explicit bash also sets pipefail.
        args = [BASH, "--noprofile", "--norc", "-e"]
        if shell == "bash":
            args += ["-o", "pipefail"]
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home, binary, work = base / "home", base / "bin", base / "work"
            for directory in (home, binary, work):
                directory.mkdir()
            fake = binary / "chezmoi"
            fake.write_text('#!/bin/sh\nprintf "%s\\n" "synthetic rendering result"\nexit "$SYNTHETIC_EXIT"\n')
            fake.chmod(0o700)
            env = {"HOME": str(home), "PATH": str(binary) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
                   "GITHUB_WORKSPACE": str(work), "SYNTHETIC_EXIT": str(exit_code)}
            # Never create the workflow's fixed /tmp destination on the test host.
            script = script.replace("/tmp/chezmoi-dest", str(base / "destination"))
            return subprocess.run([*args, "-c", script], cwd=work, env=env, capture_output=True, text=True, timeout=10)

    def test_successful_render_is_success(self):
        result = self.execute(WORKFLOW.read_text(), 0)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("synthetic rendering result", result.stdout)
        self.assertNotIn("::error::", result.stdout)

    def test_failed_render_is_failure_even_when_tail_succeeds(self):
        result = self.execute(WORKFLOW.read_text(), 42)
        self.assertNotEqual(result.returncode, 0, "tail hid the failed renderer")
        self.assertIn("::error::chezmoi apply dry-run failed", result.stdout)

    def test_removing_the_explicit_bash_reproduces_the_false_success(self):
        text = WORKFLOW.read_text().replace("        shell: bash\n", "")
        self.assertEqual(self.execute(text, 42).returncode, 0, "the negative control must reproduce the original defect")


@unittest.skipUnless(CHEZMOI or os.environ.get("CI"), "chezmoi is required")
class PolicyPropagation(unittest.TestCase):
    def setUp(self):
        if not CHEZMOI:
            self.fail("CI requires chezmoi")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.source, self.home = self.base / "source", self.base / "home"
        self.home.mkdir()
        for name in ("dot_agents/AGENTS.md", "dot_pi/agent/AGENTS.md.tmpl", "private_dot_codex/AGENTS.md.tmpl"):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.config = self.base / "chezmoi.toml"
        self.config.write_text("")
        self.shared = (self.source / "dot_agents/AGENTS.md").read_text().strip()

    def render(self, name):
        env = {"HOME": str(self.home), "PATH": os.environ["PATH"], "LANG": "C.UTF-8"}
        result = subprocess.run([CHEZMOI, "--source", str(self.source), "--config", str(self.config),
                                 "--persistent-state", str(self.base / "state.boltdb"),
                                 "execute-template", "--file", str(self.source / name)],
                                cwd=self.source, env=env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_codex_receives_the_exact_shared_policy(self):
        self.assertEqual(self.render("private_dot_codex/AGENTS.md.tmpl"), self.shared)

    def test_pi_keeps_the_shared_policy_and_its_local_application_boundary(self):
        rendered = self.render("dot_pi/agent/AGENTS.md.tmpl")
        self.assertTrue(rendered.startswith(self.shared + "\n"))
        self.assertTrue(rendered[len(self.shared):].lstrip().startswith("## Pi "))
        self.assertIn("ゲート・フック・権限設定", rendered[len(self.shared):])

    def test_claude_imports_the_same_shared_policy(self):
        self.assertIn("@~/.agents/AGENTS.md", (ROOT / "dot_claude/CLAUDE.md").read_text())


if __name__ == "__main__":
    unittest.main()
