"""dot_zshrc の hgh / hd / hm / ha / hs。偽の herdr・ghq・fzf・zoxide だけを使い、実物は起動しない。"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ZSHRC = ROOT / "home/dot_zshrc"
ZSH = shutil.which("zsh")
JQ = shutil.which("jq")

FAKE_HERDR = f'''#!{sys.executable}
import json, os, pathlib, sys
h = pathlib.Path(os.environ['FAKE_DIR']); args = sys.argv[1:]
with (h/'herdr.jsonl').open('a') as f: f.write(json.dumps({{'args': args, 'cwd': os.getcwd()}})+'\\n')
cfg = json.loads((h/'cfg.json').read_text())
key = ' '.join(args[:2])
if key in cfg['fail'] or (not args and 'attach' in cfg['fail']):
    print(json.dumps({{'error': {{'code': 'boom', 'message': 'fake failure: ' + key}}}}), file=sys.stderr)
    sys.exit(3)
if key == 'status server':
    print(cfg.get('status_raw') or json.dumps({{'status': 'x', 'running': cfg['running']}}))
elif key == 'pane list':
    print(cfg.get('panes_raw') or json.dumps({{'result': {{'panes': cfg['panes']}}}}))
elif key == 'workspace list':
    print(json.dumps({{'result': {{'workspaces': cfg['spaces']}}}}))
elif key in ('workspace create', 'workspace focus'):
    print(json.dumps({{'id': 'cli', 'result': {{'type': 'noise'}}}}))
'''

FAKE_GHQ = f'''#!{sys.executable}
import os, pathlib, sys
h = pathlib.Path(os.environ['FAKE_DIR']); root = (h/'ghq-root.txt').read_text()
repos = (h/'ghq-repos.txt').read_text().split()
if sys.argv[1] == 'root': print(root)
elif '-p' in sys.argv: print('\\n'.join(f'{{root}}/{{r}}' for r in repos))
else: print('\\n'.join(repos))
'''

FAKE_ZOXIDE = f'''#!{sys.executable}
import os, pathlib
print((pathlib.Path(os.environ['FAKE_DIR'])/'zoxide.txt').read_text(), end='')
'''

# 標準入力の候補を保存し、FZF_PICK を含む行を返す。cancel なら Esc と同じ 130 で終わる
FAKE_FZF = f'''#!{sys.executable}
import json, os, pathlib, sys
h = pathlib.Path(os.environ['FAKE_DIR']); lines = sys.stdin.read().splitlines()
(h/'fzf.json').write_text(json.dumps({{'argv': sys.argv[1:], 'lines': lines}}))
pick = (h/'pick.txt').read_text()
if pick == 'cancel': sys.exit(130)
hits = [x for x in lines if pick in x]
if not hits: sys.exit(1)
print(hits[0])
'''

FORBIDDEN = f'''#!{sys.executable}
import os, pathlib, sys
with (pathlib.Path(os.environ['FAKE_DIR'])/'forbidden.log').open('a') as f: f.write(sys.argv[0]+'\\n')
'''


def function_definitions():
    """cgh と herdr 系の関数定義だけを dot_zshrc から取り出す。"""
    text = ZSHRC.read_text()
    names = ["cgh", "hgh", "hd", "hm", "ha", "hs"] + re.findall(r"^(_herdr_\w+)\(\) \{$", text, re.M)
    blocks = []
    for name in names:
        match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.M | re.S)
        if match is None:
            raise AssertionError(f"{name} の定義が dot_zshrc にありません")
        blocks.append(match.group(0))
    return "\n".join(blocks)


class Result:
    def __init__(self, proc, d):
        self.rc = proc.returncode
        self.stdout = proc.stdout
        self.stderr = proc.stderr
        path = d / "herdr.jsonl"
        self.records = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
        self.calls = [r["args"] for r in self.records]
        self.fzf = json.loads((d / "fzf.json").read_text()) if (d / "fzf.json").exists() else None
        self.forbidden = (d / "forbidden.log").read_text() if (d / "forbidden.log").exists() else ""
        state = (d / "state.txt").read_text().split("\n") if (d / "state.txt").exists() else ["", "", ""]
        self.pwd, self.oldpwd, self.hook_leak = state[:3]

    @property
    def mutations(self):
        return [c for c in self.calls if c[:2] in (["workspace", "create"], ["workspace", "focus"])]


@unittest.skipUnless(ZSH and JQ, "zsh と jq が必要")
class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.d = Path(tmp.name).resolve()
        self.bin = self.d / "bin"
        self.bin.mkdir()
        self.home = self.d / "home"
        self.root = self.home / "ghq"
        self.repo = self.root / "github.com/o/repo"
        self.other = self.root / "github.com/o/other"
        self.start = self.home / "work"
        for path in (self.repo, self.other, self.start):
            path.mkdir(parents=True)

    def install(self, name, body):
        path = self.bin / name
        path.write_text(body)
        path.chmod(0o755)

    def run_zsh(self, call, *, inside=True, running=True, panes=(), spaces=(), fail=(), pick="repo",
                without=(), zoxide=(), start=None, status_raw=None, panes_raw=None, root=None,
                workspace="w1", pane="w1:p1"):
        fakes = {"herdr": FAKE_HERDR, "ghq": FAKE_GHQ, "fzf": FAKE_FZF, "zoxide": FAKE_ZOXIDE,
                 "tmux": FORBIDDEN, "sesh": FORBIDDEN, "fzf-tmux": FORBIDDEN}
        for name, body in fakes.items():
            if name not in without:
                self.install(name, body)
        if "jq" not in without:
            (self.bin / "jq").symlink_to(JQ)
        (self.d / "cfg.json").write_text(json.dumps({
            "running": running, "panes": list(panes), "spaces": list(spaces), "fail": list(fail),
            "status_raw": status_raw, "panes_raw": panes_raw}))
        (self.d / "ghq-root.txt").write_text(str(root or self.root))
        (self.d / "ghq-repos.txt").write_text("github.com/o/repo github.com/o/other")
        (self.d / "zoxide.txt").write_text("".join(f"{z}\n" for z in zoxide))
        (self.d / "pick.txt").write_text(pick)
        script = f'''{function_definitions()}
_t_hook() {{ print hook-noise; HOOK_LEAK=leaked; }}
chpwd_functions=(_t_hook)
OLDPWD=/old/pwd
{call}
rc=$?
print -rl -- "$PWD" "$OLDPWD" "${{HOOK_LEAK:-none}}" > "$FAKE_DIR/state.txt"
exit $rc
'''
        env = {"PATH": str(self.bin), "HOME": str(self.home), "FAKE_DIR": str(self.d), "LC_ALL": "C.UTF-8"}
        if inside:
            env.update({"HERDR_ENV": "1", "HERDR_WORKSPACE_ID": workspace, "HERDR_PANE_ID": pane})
        proc = subprocess.run([ZSH, "-f", "-c", script], env=env, cwd=start or self.start,
                              capture_output=True, text=True, encoding="utf-8", stdin=subprocess.DEVNULL)
        return Result(proc, self.d)

    def pane(self, workspace, cwd, pane_id=None, foreground_cwd=None):
        return {"pane_id": pane_id or f"{workspace}:p9", "workspace_id": workspace, "cwd": str(cwd),
                "foreground_cwd": str(foreground_cwd or cwd), "focused": False}

    def space(self, workspace, number, label):
        return {"workspace_id": workspace, "number": number, "label": label, "focused": False}

    def assert_caller_untouched(self, r):
        self.assertEqual(r.pwd, str(self.start))
        self.assertEqual(r.oldpwd, "/old/pwd")
        self.assertEqual(r.hook_leak, "none", "chpwd フックの変更が呼び出し元に残っている")

    def create_call(self, path):
        return ["workspace", "create", "--cwd", str(path), "--focus"]


class Hgh(Base):
    def test_creates_workspace_without_label(self):
        r = self.run_zsh("hgh")
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [self.create_call(self.repo)])
        self.assertEqual(r.stdout, "", "CLI の JSON やフックの出力を画面に出さない")
        self.assert_caller_untouched(r)

    def test_passes_query_to_fzf_through_cgh(self):
        r = self.run_zsh("hgh my query")
        self.assertIn("--query=my query", r.fzf["argv"])

    def test_focuses_existing_workspace(self):
        r = self.run_zsh("hgh", panes=[self.pane("w3", self.repo)])
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [["workspace", "focus", "w3"]])
        self.assertEqual(r.stdout, "")
        self.assert_caller_untouched(r)

    def test_foreground_cwd_alone_does_not_match(self):
        # スペース名は cwd に追従し foreground_cwd には追従しないので、一時的な子プロセスでは一致させない
        r = self.run_zsh("hgh", panes=[self.pane("w3", self.start, foreground_cwd=self.repo)])
        self.assertEqual(r.mutations, [self.create_call(self.repo)])

    def test_several_matches_prefer_current_workspace(self):
        panes = [self.pane("w2", self.repo), self.pane("w3", self.repo), self.pane("w3", self.repo, "w3:p2")]
        r = self.run_zsh("hgh", panes=panes, workspace="w3")
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [["workspace", "focus", "w3"]])

    def test_several_matches_elsewhere_use_first(self):
        panes = [self.pane("w2", self.repo), self.pane("w3", self.repo)]
        r = self.run_zsh("hgh", panes=panes, workspace="w1")
        self.assertEqual(r.mutations, [["workspace", "focus", "w2"]])

    def test_cancel_does_nothing(self):
        r = self.run_zsh("hgh", pick="cancel")
        self.assertNotEqual(r.rc, 0)
        self.assertEqual(r.calls, [])
        self.assert_caller_untouched(r)

    def test_resolves_symlink_before_comparing(self):
        # ペインの cwd はリンクを解決した値で返るので、論理パスのままだと既存を見落とす
        link = self.home / "ghq-link"
        link.symlink_to(self.root)
        r = self.run_zsh("hgh", panes=[self.pane("w3", self.repo)], root=link)
        self.assertEqual(r.mutations, [["workspace", "focus", "w3"]])

    def test_outside_running_creates_then_attaches(self):
        r = self.run_zsh("hgh", inside=False)
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.calls, [["status", "server", "--json"], ["pane", "list"],
                                   self.create_call(self.repo), []])
        self.assert_caller_untouched(r)

    def test_outside_running_focuses_then_attaches(self):
        r = self.run_zsh("hgh", inside=False, panes=[self.pane("w3", self.repo)])
        self.assertEqual(r.calls[-2:], [["workspace", "focus", "w3"], []])

    def test_outside_stopped_starts_in_selected_directory(self):
        r = self.run_zsh("hgh", inside=False, running=False)
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.calls, [["status", "server", "--json"], []])
        self.assertEqual(r.records[-1]["cwd"], str(self.repo))
        self.assert_caller_untouched(r)

    def test_outside_status_failure(self):
        r = self.run_zsh("hgh", inside=False, fail=["status server"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hgh:", r.stderr)
        self.assertEqual(r.calls, [["status", "server", "--json"]])

    def test_outside_status_unreadable(self):
        r = self.run_zsh("hgh", inside=False, status_raw="not json")
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hgh:", r.stderr)
        self.assertEqual(r.calls, [["status", "server", "--json"]])

    def test_outside_attach_failure(self):
        r = self.run_zsh("hgh", inside=False, fail=["attach"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hgh:", r.stderr)

    def test_outside_start_failure(self):
        r = self.run_zsh("hgh", inside=False, running=False, fail=["attach"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hgh:", r.stderr)
        self.assert_caller_untouched(r)

    def test_inside_never_attaches(self):
        r = self.run_zsh("hgh")
        self.assertNotIn([], r.calls)
        self.assertNotIn(["status", "server", "--json"], r.calls)

    def test_pane_list_failure(self):
        r = self.run_zsh("hgh", fail=["pane list"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hgh:", r.stderr)
        self.assertIn("fake failure", r.stderr, "herdr 自身のエラーも見せる")
        self.assertEqual(r.mutations, [])
        self.assert_caller_untouched(r)

    def test_pane_list_garbage(self):
        r = self.run_zsh("hgh", panes_raw="not json")
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hgh:", r.stderr)
        self.assertEqual(r.mutations, [])

    def test_create_failure(self):
        r = self.run_zsh("hgh", fail=["workspace create"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hgh:", r.stderr)

    def test_focus_failure(self):
        r = self.run_zsh("hgh", panes=[self.pane("w3", self.repo)], fail=["workspace focus"], inside=False)
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hgh:", r.stderr)
        self.assertNotIn([], r.calls, "移動に失敗したら接続しない")

    def test_missing_herdr(self):
        r = self.run_zsh("hgh", without=["herdr"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("herdr", r.stderr)
        self.assertIsNone(r.fzf, "選ばせる前に止める")

    def test_missing_jq(self):
        r = self.run_zsh("hgh", without=["jq"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("jq", r.stderr)
        self.assertIsNone(r.fzf)
        self.assertEqual(r.calls, [])


class Hd(Base):
    def setUp(self):
        super().setUp()
        self.notes = self.home / "notes"
        self.notes.mkdir()

    def test_directory_argument_opens_it_without_picking(self):
        r = self.run_zsh(f"hd {self.notes}", without=["ghq", "zoxide", "fzf"])
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [self.create_call(self.notes)])
        self.assertIsNone(r.fzf)
        self.assertEqual(r.stdout, "")
        self.assert_caller_untouched(r)

    def test_relative_directory_argument(self):
        r = self.run_zsh("hd ../notes", without=["ghq", "zoxide", "fzf"])
        self.assertEqual(r.mutations, [self.create_call(self.notes)])

    def test_no_argument_opens_current_directory_without_picking(self):
        r = self.run_zsh("hd", panes=[self.pane("w1", self.start, "w1:p1")],
                         zoxide=[self.notes], pick="notes")
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertIsNone(r.fzf)
        self.assertEqual(r.mutations, [self.create_call(self.start)])
        self.assertEqual(r.stdout, "")
        self.assert_caller_untouched(r)

    def test_no_argument_does_not_need_directory_selection_tools(self):
        r = self.run_zsh("hd", without=["ghq", "zoxide", "fzf"])
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [self.create_call(self.start)])
        self.assert_caller_untouched(r)

    def test_focuses_other_workspace_with_current_directory(self):
        panes = [self.pane("w1", self.start, "w1:p1"), self.pane("w3", self.start)]
        r = self.run_zsh("hd", panes=panes)
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertIsNone(r.fzf)
        self.assertEqual(r.mutations, [["workspace", "focus", "w3"]])
        self.assert_caller_untouched(r)

    def test_explicit_current_directory_also_excludes_caller(self):
        r = self.run_zsh("hd .", panes=[self.pane("w1", self.start, "w1:p1")])
        self.assertEqual(r.mutations, [self.create_call(self.start)])
        self.assertIsNone(r.fzf)

    def test_directory_argument_with_spaces(self):
        notes = self.home / "my notes"
        notes.mkdir()
        r = self.run_zsh(f'hd "{notes}"', without=["ghq", "zoxide", "fzf"])
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [self.create_call(notes)])
        self.assert_caller_untouched(r)

    def test_missing_directory_is_not_a_search_query(self):
        r = self.run_zsh(f"hd {self.d}/gone", zoxide=[self.notes], pick="notes")
        self.assertNotEqual(r.rc, 0)
        self.assertIn("gone", r.stderr)
        self.assertIsNone(r.fzf)
        self.assertEqual(r.calls, [])
        self.assert_caller_untouched(r)

    def test_rejects_multiple_arguments_without_picking(self):
        r = self.run_zsh("hd my query")
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hd:", r.stderr)
        self.assertIn("使い方", r.stderr)
        self.assertIsNone(r.fzf)
        self.assertEqual(r.calls, [])

    def test_outside_running_opens_current_directory_and_attaches(self):
        r = self.run_zsh("hd", inside=False, without=["ghq", "zoxide", "fzf"])
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.calls[-2:], [self.create_call(self.start), []])
        self.assert_caller_untouched(r)

    def test_outside_stopped_starts_in_current_directory(self):
        r = self.run_zsh("hd", inside=False, running=False, without=["ghq", "zoxide", "fzf"])
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.calls[-1], [])
        self.assertEqual(r.records[-1]["cwd"], str(self.start))
        self.assert_caller_untouched(r)

    def test_missing_jq(self):
        r = self.run_zsh("hd", without=["jq"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hd: jq", r.stderr)
        self.assertIsNone(r.fzf)
        self.assertEqual(r.calls, [])

    def test_missing_herdr(self):
        r = self.run_zsh(f"hd {self.notes}", without=["herdr"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("herdr", r.stderr)


class OpenDir(Base):
    def test_rejects_missing_directory(self):
        # workspace create は存在しない cwd を黙ってホームに置き換える
        r = self.run_zsh(f"_herdr_open_dir {self.d}/gone")
        self.assertNotEqual(r.rc, 0)
        self.assertIn("gone", r.stderr)
        self.assertEqual(r.mutations, [])


class Hm(Base):
    def test_creates_for_current_directory_without_ui(self):
        # 自分のペインは必ず同じ cwd なので、数えると新規作成に届かない
        r = self.run_zsh("hm", panes=[self.pane("w1", self.start, "w1:p1")])
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [self.create_call(self.start)])
        self.assertIsNone(r.fzf)
        self.assertEqual(r.stdout, "")
        self.assert_caller_untouched(r)

    def test_moves_to_other_pane_with_same_cwd(self):
        panes = [self.pane("w1", self.start, "w1:p1"), self.pane("w3", self.start, "w3:p1")]
        r = self.run_zsh("hm", panes=panes)
        self.assertEqual(r.mutations, [["workspace", "focus", "w3"]])
        self.assert_caller_untouched(r)

    def test_outside_running(self):
        r = self.run_zsh("hm", inside=False)
        self.assertEqual(r.calls[-2:], [self.create_call(self.start), []])

    def test_outside_stopped(self):
        r = self.run_zsh("hm", inside=False, running=False)
        self.assertEqual(r.calls[-1], [])
        self.assertEqual(r.records[-1]["cwd"], str(self.start))
        self.assert_caller_untouched(r)

    def test_missing_jq(self):
        r = self.run_zsh("hm", without=["jq"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("jq", r.stderr)


class Ha(Base):
    def test_outside_attaches(self):
        r = self.run_zsh("ha", inside=False)
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.calls, [[]])
        self.assert_caller_untouched(r)

    def test_outside_attaches_named_session(self):
        r = self.run_zsh("ha work", inside=False)
        self.assertEqual(r.calls, [["session", "attach", "work"]])
        self.assert_caller_untouched(r)

    def test_inside_without_argument_refuses(self):
        r = self.run_zsh("ha")
        self.assertNotEqual(r.rc, 0)
        self.assertIn("ha:", r.stderr)
        self.assertEqual(r.calls, [], "入れ子にしない")

    def test_inside_with_argument_uses_session_attach(self):
        r = self.run_zsh("ha work")
        self.assertEqual(r.calls, [["session", "attach", "work"]])

    def test_session_attach_failure(self):
        r = self.run_zsh("ha work", inside=False, fail=["session attach"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("ha:", r.stderr)

    def test_attach_failure(self):
        r = self.run_zsh("ha", inside=False, fail=["attach"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("ha:", r.stderr)

    def test_missing_herdr(self):
        r = self.run_zsh("ha", inside=False, without=["herdr"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("herdr", r.stderr)

    def test_does_not_need_jq(self):
        r = self.run_zsh("ha", inside=False, without=["jq"])
        self.assertEqual(r.rc, 0, r.stderr)


class Hs(Base):
    def candidates(self, r):
        return [line.split("\t") for line in r.fzf["lines"]]

    def test_lists_spaces_repos_and_zoxide_without_duplicates(self):
        extra = self.home / "notes"
        extra.mkdir()
        r = self.run_zsh("hs", spaces=[self.space("w2", 1, "my label")], zoxide=[self.repo, extra],
                         pick="cancel")
        found = self.candidates(r)
        self.assertEqual([(x[0], x[1]) for x in found], [
            ("space", "w2"), ("dir", str(self.repo)), ("dir", str(self.other)), ("dir", str(extra))])
        self.assertIn("my label", found[0][2])
        self.assertIn("~/ghq/github.com/o/repo", found[1][2])
        self.assertEqual(r.forbidden, "", "tmux / sesh / fzf-tmux に依存しない")

    def test_pick_space_focuses(self):
        r = self.run_zsh("hs", spaces=[self.space("w2", 1, "my label")], pick="my label")
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [["workspace", "focus", "w2"]])
        self.assertEqual(r.stdout, "")
        self.assert_caller_untouched(r)

    def test_pick_directory_creates(self):
        r = self.run_zsh("hs", pick="o/other")
        self.assertEqual(r.mutations, [self.create_call(self.other)])
        self.assert_caller_untouched(r)

    def test_pick_directory_with_existing_pane_focuses(self):
        r = self.run_zsh("hs", pick="o/other", panes=[self.pane("w3", self.other)])
        self.assertEqual(r.mutations, [["workspace", "focus", "w3"]])

    def test_works_without_ghq(self):
        extra = self.home / "notes"
        extra.mkdir()
        r = self.run_zsh("hs", without=["ghq"], zoxide=[extra], pick="notes")
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [self.create_call(extra)])

    def test_works_without_zoxide(self):
        r = self.run_zsh("hs", without=["zoxide"], pick="o/repo")
        self.assertEqual(r.rc, 0, r.stderr)
        self.assertEqual(r.mutations, [self.create_call(self.repo)])

    def test_spaces_only(self):
        r = self.run_zsh("hs", without=["ghq", "zoxide"], spaces=[self.space("w2", 1, "lab")], pick="lab")
        self.assertEqual(r.mutations, [["workspace", "focus", "w2"]])

    def test_no_candidates(self):
        r = self.run_zsh("hs", without=["ghq", "zoxide"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hs:", r.stderr)
        self.assertIsNone(r.fzf)

    def test_cancel_does_nothing(self):
        r = self.run_zsh("hs", spaces=[self.space("w2", 1, "lab")], pick="cancel")
        self.assertNotEqual(r.rc, 0)
        self.assertEqual(r.mutations, [])
        self.assertNotIn([], r.calls)
        self.assert_caller_untouched(r)

    def test_outside_running_pick_space_attaches(self):
        r = self.run_zsh("hs", inside=False, spaces=[self.space("w2", 1, "lab")], pick="lab")
        self.assertEqual(r.calls[-2:], [["workspace", "focus", "w2"], []])

    def test_outside_running_pick_directory_attaches(self):
        r = self.run_zsh("hs", inside=False, pick="o/other")
        self.assertEqual(r.calls[-2:], [self.create_call(self.other), []])

    def test_outside_stopped_lists_directories_only(self):
        r = self.run_zsh("hs", inside=False, running=False, pick="o/other")
        self.assertNotIn(["workspace", "list"], r.calls)
        self.assertEqual(r.calls[-1], [])
        self.assertEqual(r.records[-1]["cwd"], str(self.other))
        self.assert_caller_untouched(r)

    def test_workspace_list_failure(self):
        r = self.run_zsh("hs", fail=["workspace list"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hs:", r.stderr)
        self.assertIsNone(r.fzf)

    def test_outside_status_failure(self):
        r = self.run_zsh("hs", inside=False, fail=["status server"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hs:", r.stderr)
        self.assertIsNone(r.fzf)

    def test_missing_fzf(self):
        r = self.run_zsh("hs", without=["fzf"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("hs: fzf", r.stderr)
        self.assertEqual(r.calls, [], "候補を集める前に止める")

    def test_missing_jq(self):
        r = self.run_zsh("hs", without=["jq"])
        self.assertNotEqual(r.rc, 0)
        self.assertIn("jq", r.stderr)


class TmuxVersionsRemoved(unittest.TestCase):
    """herdr 版に一本化した。tmux 版の tgh / tm / ta / s を zsh の入口に戻さない。"""

    def test_tmux_versions_are_not_defined(self):
        text = ZSHRC.read_text()
        for name in ("tgh", "tm", "s"):
            self.assertIsNone(re.search(rf"^{name}\(\) \{{", text, re.M), f"{name} が残っている")
        self.assertIsNone(re.search(r"^alias ta=", text, re.M), "ta が残っている")

    def test_zshrc_does_not_run_tmux(self):
        # cc の画面監視 (tmux capture-pane) のように、herdr の中では動かない処理を残さない
        code = "\n".join(line for line in ZSHRC.read_text().splitlines() if not line.lstrip().startswith("#"))
        self.assertNotRegex(code, r"\b(tmux|sesh|fzf-tmux|TMUX\w*)\b")


if __name__ == "__main__":
    unittest.main()
