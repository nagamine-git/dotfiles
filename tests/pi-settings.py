"""dot_pi/agent/modify_settings.json, rendered by chezmoi from the model tiers in .chezmoidata/pi.yaml.

Each test copies the template and the data into a throwaway source dir and runs `chezmoi execute-template
--with-stdin` with the current settings.json on stdin, as `chezmoi apply` does for a modify-template.
Needs chezmoi (CI installs it; elsewhere the tests skip). The zsh prefix runs in the real zsh (skips
without it, but not in CI). The real-Pi tests hand the result to the installed Pi (pi_real.py: dummy
keys, nothing prompted, so no model call) and skip on hosts without it.
"""
import hashlib
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
TEMPLATE = "dot_pi/agent/modify_settings.json"
DATA = ".chezmoidata/pi.yaml"
CHEZMOI = shutil.which("chezmoi")
ZSH = shutil.which("zsh")
BASH = shutil.which("bash")
PREFIX = "\n".join([
    '[[ -r "$PI_ZSH_SNAPSHOT" ]] && { if [[ $(command -p sha256sum < "$PI_ZSH_SNAPSHOT") == "$PI_ZSH_SNAPSHOT_SHA256 "* ]];'
    ' then source "$PI_ZSH_SNAPSHOT"; else print -ru2 -- "pi: $PI_ZSH_SNAPSHOT が起動時から変わったので読まない'
    ' (エイリアスと関数なしで続ける)"; fi; }',
    "setopt no_nomatch no_equals",
    """[[ -n $ZSH_EXECUTION_STRING ]] && { eval "${ZSH_EXECUTION_STRING#*$'\\n'*$'\\n'*$'\\n'}"; exit; }""",
])
# A snapshot as pi-jev writes it (alias -L, functions), for the shell tests.
SNAPSHOT = "alias gss='git status --short'\nalias hello='print -r -- hello-alias'\nmyfn () {\n\tprint -r -- \"fn:$1\"\n}\n"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pi_real  # noqa: E402

TIERS = ("default", "peak", "light")
PI_SETTINGS = {  # Pi が自分で書くキーや本人の設定
    "lastChangelogVersion": "1.5.0",
    "deviceId": "d51cf81e-0000-0000-0000-000000000000",
    "theme": "dark",
    "defaultProvider": "anthropic",
    "defaultModel": "claude-haiku-5-5",
    "defaultThinkingLevel": "high",
    "modelThinkingLevels": {"openai/gpt-6-1-terra": "xhigh", "anthropic/claude-opus-5-5": "xhigh"},
    "enabledModels": ["claude-*"],
}


@unittest.skipUnless(CHEZMOI or os.environ.get("CI"), "chezmoi が必要")
class PiSettings(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.source = self.base / "source"
        for rel in (TEMPLATE, DATA):
            (self.source / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / rel, self.source / rel)
        (self.base / "chezmoi.toml").write_text("")

    def chezmoi(self, *args, stdin="", path=None):
        env = dict(os.environ, PATH=path) if path is not None else None
        result = subprocess.run([CHEZMOI, "--source", str(self.source), "--config", str(self.base / "chezmoi.toml"),
                                 "--persistent-state", str(self.base / "state.boltdb"), "execute-template", *args],
                                input=stdin, capture_output=True, text=True, timeout=60, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def render(self, current, path=None):
        return self.chezmoi("--with-stdin", "--file", str(self.source / TEMPLATE), stdin=current, path=path)

    def tiers(self):
        return json.loads(self.chezmoi('{{ .pi.models | toJson }}'))

    def expected(self, tiers):
        key = lambda t: "%s/%s" % (tiers[t]["provider"], tiers[t]["id"])
        return {
            "defaultProvider": tiers["default"]["provider"],
            "defaultModel": tiers["default"]["id"],
            "defaultThinkingLevel": tiers["default"]["thinking"],
            "modelThinkingLevels": {key(t): tiers[t]["thinking"] for t in TIERS},
            "enabledModels": ["%s:%s" % (key(t), tiers[t]["thinking"]) for t in TIERS],
            **({"shellPath": ZSH, "shellCommandPrefix": PREFIX} if ZSH else {}),
        }

    def test_data_has_three_complete_tiers(self):
        tiers = self.tiers()
        self.assertEqual(sorted(tiers), sorted(TIERS))
        for t in TIERS:
            self.assertEqual(sorted(tiers[t]), ["id", "provider", "thinking"], t)
            self.assertIn(tiers[t]["thinking"], ("off", "minimal", "low", "medium", "high", "xhigh", "max"), t)

    def test_empty_input_starts_from_an_empty_object(self):
        for current in ("", "\n  \n"):
            with self.subTest(current=current):
                self.assertEqual(json.loads(self.render(current)), self.expected(self.tiers()))

    def test_other_keys_are_kept_and_the_tier_keys_follow_the_data(self):
        out = json.loads(self.render(json.dumps(PI_SETTINGS, indent=2)))
        want = self.expected(self.tiers())
        for key in ("lastChangelogVersion", "deviceId", "theme"):
            self.assertEqual(out[key], PI_SETTINGS[key])
        for key in ("defaultProvider", "defaultModel", "defaultThinkingLevel", "enabledModels"):
            self.assertEqual(out[key], want[key])
        self.assertEqual(out["modelThinkingLevels"]["openai/gpt-6-1-terra"], "xhigh")  # 消さない
        for key, level in want["modelThinkingLevels"].items():
            self.assertEqual(out["modelThinkingLevels"][key], level)

    def test_second_pass_changes_nothing(self):
        first = self.render(json.dumps(PI_SETTINGS))
        self.assertEqual(self.render(first), first)

    def test_changing_the_data_changes_the_settings(self):
        (self.source / DATA).write_text(
            "pi:\n  models:\n"
            "    default: {provider: anthropic, id: claude-sonnet-5-5, thinking: low}\n"
            "    peak: {provider: openai, id: gpt-6.1-terra, thinking: xhigh}\n"
            "    light: {provider: anthropic, id: claude-haiku-5-5, thinking: medium}\n")
        out = json.loads(self.render(json.dumps(PI_SETTINGS)))
        self.assertEqual((out["defaultProvider"], out["defaultModel"], out["defaultThinkingLevel"]),
                         ("anthropic", "claude-sonnet-5-5", "low"))
        self.assertEqual(out["enabledModels"], ["anthropic/claude-sonnet-5-5:low", "openai/gpt-6.1-terra:xhigh",
                                                "anthropic/claude-haiku-5-5:medium"])
        self.assertEqual(out["modelThinkingLevels"]["openai/gpt-6.1-terra"], "xhigh")
        self.assertEqual(out["modelThinkingLevels"]["anthropic/claude-opus-5-5"], "xhigh")  # 段から外れたものも残す

    @unittest.skipUnless(ZSH or os.environ.get("CI"), "zsh が必要")
    def test_zsh_becomes_the_shell_with_the_snapshot_prefix(self):
        out = json.loads(self.render(json.dumps({"shellPath": "/bin/bash", "shellCommandPrefix": "export CI=1"})))
        self.assertEqual((out["shellPath"], out["shellCommandPrefix"]), (ZSH, PREFIX))

    def test_without_zsh_the_shell_keys_are_left_alone(self):
        empty = self.base / "no-zsh-here"
        empty.mkdir()
        out = json.loads(self.render(json.dumps({"shellPath": "/bin/bash", "shellCommandPrefix": "export CI=1"}),
                                     path=str(empty)))
        self.assertEqual((out["shellPath"], out["shellCommandPrefix"]), ("/bin/bash", "export CI=1"))
        self.assertNotIn("shellPath", json.loads(self.render("", path=str(empty))))

    def project_with_snapshot(self):
        repo = self.base / "repo"
        (repo / "src").mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
        (repo / "untracked.txt").write_text("x\n")
        (repo / "src/a.ts").write_text("needle\n")
        (repo / "src/b.js").write_text("needle\n")
        snapshot = self.base / "zsh-snapshot.zsh"
        snapshot.write_text(SNAPSHOT)
        return repo, snapshot

    @unittest.skipUnless(ZSH or os.environ.get("CI"), "zsh が必要")
    def test_prefix_gives_zsh_the_aliases_functions_and_bash_style_globs(self):
        repo, snapshot = self.project_with_snapshot()
        sha = hashlib.sha256(SNAPSHOT.encode()).hexdigest()
        prefix = json.loads(self.render(""))["shellCommandPrefix"]  # 描いた設定のものを試す
        run = lambda shell, cmd, snap=snapshot, sha=sha: subprocess.run(
            [shell, "-c", prefix + "\n" + cmd], cwd=str(repo), timeout=30, capture_output=True, text=True,
            env=dict(os.environ, PI_ZSH_SNAPSHOT=str(snap), PI_ZSH_SNAPSHOT_SHA256=sha))
        cases = {
            "gss": "?? src/\n?? untracked.txt\n",                       # エイリアス (eval で読み直すので効く)
            "myfn x; hello": "fn:x\nhello-alias\n",                     # 関数とエイリアス
            "grep -rn --include=*.ts needle .": "./src/a.ts:1:needle\n",  # 合わないグロブもそのまま (no_nomatch)
            "echo ===; echo =ls": "===\n=ls\n",                         # 語頭の = を展開しない (no_equals)
            "x=$(hello); print -r -- got:$x": "got:hello-alias\n",
            "cat <<'EOF'\nliteral $HOME\nEOF": "literal $HOME\n",
        }
        for cmd, want in cases.items():
            with self.subTest(cmd=cmd):
                result = run(ZSH, cmd)
                self.assertEqual((result.stdout, result.stderr, result.returncode), (want, "", 0))
        result = run(ZSH, "print one; exit 3")
        self.assertEqual((result.stdout, result.returncode), ("one\n", 3))
        # The eval line runs the command once, not again after it.
        self.assertEqual(run(ZSH, "print once").stdout, "once\n")
        # With an unreadable snapshot or another shell the prefix steps aside and the command still runs.
        self.assertEqual(run(ZSH, "print no-snapshot", snap=self.base / "missing.zsh").stdout, "no-snapshot\n")
        bash = run(BASH, "echo bash-ok")
        self.assertEqual(bash.stdout, "bash-ok\n")

    @unittest.skipUnless(ZSH or os.environ.get("CI"), "zsh が必要")
    def test_a_changed_snapshot_is_not_sourced_and_the_command_still_runs(self):
        repo, snapshot = self.project_with_snapshot()
        sha = hashlib.sha256(SNAPSHOT.encode()).hexdigest()
        snapshot.write_text(SNAPSHOT + "git () { print -r -- hijacked }\n")  # 例えば git を乗っ取る関数
        prefix = json.loads(self.render(""))["shellCommandPrefix"]
        for env_sha in (sha, ""):  # 起動時の値と違う、または値が無い
            with self.subTest(env_sha=env_sha):
                result = subprocess.run([ZSH, "-c", prefix + "\n" + "git --version >/dev/null && print ran; myfn x"],
                                        cwd=str(repo), timeout=30, capture_output=True, text=True,
                                        env=dict(os.environ, PI_ZSH_SNAPSHOT=str(snapshot), PI_ZSH_SNAPSHOT_SHA256=env_sha))
                self.assertEqual(result.stdout, "ran\n")
                self.assertEqual(len(result.stderr.splitlines()), 2, result.stderr)  # 警告 1 行と myfn が無いこと
                self.assertIn("変わったので読まない", result.stderr.splitlines()[0])
                self.assertIn("command not found: myfn", result.stderr)

    @unittest.skipUnless(pi_real.available() and ZSH, "Pi と zsh が要る (am5-itx だけ)")
    def test_real_pi_runs_bang_commands_in_zsh_with_the_snapshot(self):
        repo, snapshot = self.project_with_snapshot()
        settings = self.render(json.dumps({"lastChangelogVersion": "1.5.0"}))
        cmd = "cd %s && gss && myfn x && grep -rn --include=*.ts needle . && echo ===" % repo
        responses, stderr, _ = pi_real.rpc({"settings.json": settings}, [{"type": "bash", "command": cmd}],
                                           env={"PI_ZSH_SNAPSHOT": str(snapshot),
                                                "PI_ZSH_SNAPSHOT_SHA256": hashlib.sha256(SNAPSHOT.encode()).hexdigest()})
        data = responses.get("c0", {}).get("data") or {}
        self.assertEqual((data.get("exitCode"), data.get("output")),
                         (0, "?? src/\n?? untracked.txt\nfn:x\n./src/a.ts:1:needle\n===\n"), stderr)

    @unittest.skipUnless(pi_real.available(), "Pi が入っていない (am5-itx だけ)")
    def test_real_pi_starts_on_the_default_tier_and_ctrl_p_cycles_the_tiers(self):
        tiers = self.tiers()
        settings = self.render(json.dumps({"lastChangelogVersion": "1.5.0"}))
        commands = [{"type": "get_state"}] + [{"type": "cycle_model"}] * 3
        responses, stderr, _ = pi_real.rpc({"settings.json": settings}, commands)
        seen = [pi_real.model_of(responses.get("c%d" % i, {})) for i in range(4)]
        want = [("%s/%s" % (tiers[t]["provider"], tiers[t]["id"]), tiers[t]["thinking"]) for t in TIERS + ("default",)]
        self.assertEqual(seen, want, stderr)


if __name__ == "__main__":
    unittest.main()
