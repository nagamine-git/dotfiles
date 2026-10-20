"""No model calls: derive the Claude auto-memory directory for disposable git repos."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_agent-memory-dir"


def git(cwd, *args):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


def sanitize(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


class AgentMemoryDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name).resolve() / "home"
        (self.home / ".claude/projects").mkdir(parents=True)
        self.repo = self.home / "ghq/github.com/me/repo_x.y"
        self.repo.mkdir(parents=True)
        git(self.repo, "init", "-q")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, cwd, **extra):
        env = {**os.environ, "HOME": str(self.home), **extra}
        if "CLAUDE_CONFIG_DIR" not in extra:
            env.pop("CLAUDE_CONFIG_DIR", None)
        result = subprocess.run(["sh", str(SCRIPT)], cwd=cwd, env=env, capture_output=True, text=True)
        return result.returncode, result.stdout.strip(), result.stderr

    def expected(self, path):
        return str(self.home / ".claude/projects" / sanitize(path) / "memory")

    def test_every_non_alphanumeric_becomes_a_dash(self):
        code, out, _ = self.run_script(self.repo)
        self.assertEqual(code, 0)
        self.assertEqual(out, self.expected(self.repo))
        self.assertIn("repo-x-y", out)

    def test_subdirectory_resolves_to_repo_root(self):
        sub = self.repo / "a/b"
        sub.mkdir(parents=True)
        self.assertEqual(self.run_script(sub)[1], self.expected(self.repo))

    def test_linked_worktree_shares_the_main_repo_directory(self):
        wt = self.home / "wt"
        git(self.repo, "worktree", "add", "-q", str(wt), "-b", "feature")
        self.assertEqual(self.run_script(wt)[1], self.expected(self.repo))

    def test_existing_directory_wins_over_the_derived_one(self):
        wt = self.home / "wt"
        git(self.repo, "worktree", "add", "-q", str(wt), "-b", "feature")
        own = Path(self.expected(wt))
        own.mkdir(parents=True)
        self.assertEqual(self.run_script(wt)[1], str(own))

    def test_submodule_uses_its_own_root_not_the_superproject_git_dir(self):
        sub_src = self.home / "sub-src"
        sub_src.mkdir()
        git(sub_src, "init", "-q")
        git(sub_src, "commit", "-q", "--allow-empty", "-m", "init")
        subprocess.run(["git", "-C", str(self.repo), "-c", "protocol.file.allow=always", "submodule", "add",
                        "-q", str(sub_src), "deps/sub"], check=True, capture_output=True,
                       env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
                            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"})
        sub = self.repo / "deps/sub"
        self.assertEqual(self.run_script(sub)[1], self.expected(sub))

    def test_outside_git_uses_the_current_directory(self):
        plain = self.home / "plain"
        plain.mkdir()
        self.assertEqual(self.run_script(plain)[1], self.expected(plain))

    def test_claude_config_dir_is_honoured(self):
        cfg = self.home / "cfg"
        out = self.run_script(self.repo, CLAUDE_CONFIG_DIR=str(cfg))[1]
        self.assertEqual(out, str(cfg / "projects" / sanitize(self.repo) / "memory"))

    def test_prints_nothing_but_the_path(self):
        code, out, err = self.run_script(self.repo)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(len(out.splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
