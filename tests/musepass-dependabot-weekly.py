"""No network: verify musepass-dependabot-weekly aggregates alerts, keeps state only after a post, and never prints the webhook."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_musepass-dependabot-weekly"
sys.dont_write_bytecode = True
LOADER = SourceFileLoader("musepass_dependabot_weekly", str(SCRIPT))
M = module_from_spec(spec_from_loader("musepass_dependabot_weekly", LOADER))
LOADER.exec_module(M)

WEBHOOK = "https://hooks.slack.com/services/T000/B000/secret-part"
NOW = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)


def alert(number, sev, pkg, created, fixed=None):
    return {"number": number, "security_advisory": {"severity": sev},
            "dependency": {"package": {"ecosystem": "npm", "name": pkg}},
            "created_at": created, "fixed_at": fixed}


FRONT_OPEN = [
    alert(1, "high", "minimatch", "2026-09-01T00:00:00Z"),
    alert(2, "medium", "minimatch", "2026-09-02T00:00:00Z"),
    alert(3, "low", "tar", "2026-10-01T00:00:00Z"),
    alert(4, "critical", "next", "2026-11-10T00:00:00Z"),
]
FRONT_FIXED = [
    alert(5, "high", "axios", "2026-11-06T00:00:00Z", "2026-11-08T00:00:00Z"),
    alert(6, "low", "axios", "2026-08-01T00:00:00Z", "2026-11-01T00:00:00Z"),
]
FRONT_PRS = [{"number": 42, "title": "fix(deps): update a & <b>", "createdAt": "2026-11-02T00:00:00Z",
              "url": "https://github.com/Machitsuku-inc/musepass-frontend/pull/42"}]


class Result:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class FakeRun:
    """subprocess.run の代わり。gh には決めた応答を返し、curl への入力を覚える。"""

    def __init__(self, gh_fail=False, curl=None):
        self.calls = []
        self.gh_fail = gh_fail
        self.curl = curl or Result(0, "ok\n200")

    def __call__(self, cmd, input=None, **kwargs):
        call = {"cmd": cmd, "input": input}
        if cmd[0] == "curl":
            call["payload"] = json.loads(Path(cmd[cmd.index("--data-binary") + 1][1:]).read_text("utf-8"))
        self.calls.append(call)
        if cmd[0] == "curl":
            return self.curl
        if self.gh_fail:
            return Result(1, "", "HTTP 403: Resource not accessible")
        joined = " ".join(cmd)
        front = "musepass-frontend" in joined
        if cmd[1] == "pr":
            return Result(0, json.dumps(FRONT_PRS if front else []))
        if "state=open" in joined:
            # 2 ページに分かれた --paginate の出力
            return Result(0, json.dumps(FRONT_OPEN[:2]) + json.dumps(FRONT_OPEN[2:]) if front else "[]")
        return Result(0, json.dumps(FRONT_FIXED) if front else "[]")


def run_main(argv, environ, fake):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = M.main(argv, environ=environ, run=fake, now=NOW)
    return code, out.getvalue(), err.getvalue()


class Summarize(unittest.TestCase):
    def test_counts(self):
        s = M.summarize(FRONT_OPEN, FRONT_FIXED, FRONT_PRS, NOW)
        self.assertEqual(s["open_total"], 4)
        self.assertEqual(s["open"], {"critical": 1, "high": 1, "medium": 1, "low": 1, "unknown": 0})
        self.assertEqual(s["created_recent"], 2)  # #4 (open) と #5 (fixed)
        self.assertEqual(s["fixed_recent"], 1)  # #5 だけ。#6 は 11/01 に fixed
        self.assertEqual(s["stale_total"], 3)
        self.assertEqual(s["stale_packages"], [("minimatch", 2), ("tar", 1)])
        self.assertEqual(s["prs"][0]["days"], 10)

    def test_paginated_output_is_joined(self):
        self.assertEqual(len(M.parse_pages("[1,2]\n[3]")), 3)
        with self.assertRaises(M.FetchError):
            M.parse_pages('{"message": "x"}')


class Main(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {"XDG_STATE_HOME": self.tmp.name}
        self.state = Path(self.tmp.name) / "musepass-dependabot/last.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_dry_run_prints_without_posting_or_state(self):
        fake = FakeRun()
        code, out, _ = run_main(["--dry-run"], self.env, fake)
        self.assertEqual(code, 0)
        self.assertFalse([c for c in fake.calls if c["cmd"][0] == "curl"])
        self.assertFalse(self.state.exists())
        self.assertIn("<https://github.com/Machitsuku-inc/musepass-frontend/security/dependabot|", out)
        self.assertIn("未対応 4件 (critical 1 / high 1 / medium 1 / low 1) （前回の記録なし）", out)
        self.assertIn("30日以上未対応 3件 (上位: minimatch 2件, tar 1件)", out)
        self.assertIn("<https://github.com/Machitsuku-inc/musepass-frontend/pull/42|#42> 10日経過"
                      " fix(deps): update a &amp; &lt;b&gt;", out)
        self.assertIn("未対応 0件", out)

    def test_missing_webhook_fails_before_fetching(self):
        fake = FakeRun()
        code, _, err = run_main([], self.env, fake)
        self.assertEqual(code, 2)
        self.assertIn(M.WEBHOOK_ENV, err)
        self.assertEqual(fake.calls, [])

    def test_gh_failure_does_not_post(self):
        fake = FakeRun(gh_fail=True)
        code, _, err = run_main([], dict(self.env, **{M.WEBHOOK_ENV: WEBHOOK}), fake)
        self.assertEqual(code, 1)
        self.assertIn("403", err)
        self.assertFalse([c for c in fake.calls if c["cmd"][0] == "curl"])
        self.assertFalse(self.state.exists())

    def test_post_saves_state_and_hides_webhook(self):
        fake = FakeRun()
        env = dict(self.env, **{M.WEBHOOK_ENV: WEBHOOK})
        code, out, err = run_main([], env, fake)
        self.assertEqual(code, 0)
        curl = [c for c in fake.calls if c["cmd"][0] == "curl"][0]
        self.assertNotIn(WEBHOOK, " ".join(curl["cmd"]))
        self.assertIn(WEBHOOK, curl["input"])
        self.assertIn("未対応 4件", curl["payload"]["text"])
        self.assertNotIn(WEBHOOK, out + err)
        state = json.loads(self.state.read_text("utf-8"))
        self.assertEqual(state["repos"]["musepass-frontend"]["open_total"], 4)

        # 2 回目は前回比を出す
        FRONT_OPEN.append(alert(7, "high", "vite", "2026-11-11T00:00:00Z"))
        try:
            code, out, _ = run_main(["--dry-run"], env, FakeRun())
        finally:
            FRONT_OPEN.pop()
        self.assertEqual(code, 0)
        self.assertIn("（前回 2026-11-12 比 +1件: high +1）", out)
        self.assertIn("未対応 0件 (critical 0 / high 0 / medium 0 / low 0) （前回 2026-11-12 比 ±0件）", out)

    def test_slack_error_keeps_state_and_hides_webhook(self):
        fake = FakeRun(curl=Result(0, "no_service\n404"))
        code, out, err = run_main([], dict(self.env, **{M.WEBHOOK_ENV: WEBHOOK}), fake)
        self.assertEqual(code, 1)
        self.assertIn("HTTP 404: no_service", err)
        self.assertNotIn(WEBHOOK, out + err)
        self.assertFalse(self.state.exists())

    def test_curl_error_message_is_masked(self):
        fake = FakeRun(curl=Result(6, "", "curl: (6) Could not resolve %s" % WEBHOOK))
        code, out, err = run_main([], dict(self.env, **{M.WEBHOOK_ENV: WEBHOOK}), fake)
        self.assertEqual(code, 1)
        self.assertNotIn(WEBHOOK, out + err)
        self.assertIn("<webhook>", err)


class RealCurl(unittest.TestCase):
    """本物の curl で、-K - の設定と @file のペイロードが組み合わさって POST になることを確かめる (ローカルの HTTP サーバー)。"""

    def test_post_reaches_local_server(self):
        import http.server
        import threading

        received = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                received["path"] = self.path
                received["type"] = self.headers.get("Content-Type")
                received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            M.post("http://127.0.0.1:%d/services/x" % server.server_port, "本文 \"引用\" \\ <a>", subprocess.run)
        finally:
            thread.join(10)
            server.server_close()
        self.assertEqual(received["path"], "/services/x")
        self.assertTrue(received["type"].startswith("application/json"))
        self.assertEqual(received["body"], {"text": "本文 \"引用\" \\ <a>"})


if __name__ == "__main__":
    unittest.main()
