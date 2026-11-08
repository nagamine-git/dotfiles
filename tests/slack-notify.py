"""No network: verify slack-notify builds the chat.postMessage payload per kind and never prints the token."""
from contextlib import redirect_stderr, redirect_stdout
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_slack-notify"
SHIPPED_KINDS = ROOT / "private_dot_config/slack-notify/kinds.json"
sys.dont_write_bytecode = True
LOADER = SourceFileLoader("slack_notify", str(SCRIPT))
M = module_from_spec(spec_from_loader("slack_notify", LOADER))
LOADER.exec_module(M)

TOKEN = "xoxb-test-secret"
CONFIG = {
    "default_channel": "CDEFAULT",
    "kinds": {
        "preship": {"username": "Preship 広告", "icon_emoji": ":chart_with_upwards_trend:"},
        "ops": {"username": "運用", "icon_emoji": ":gear:", "channel": "COPS"},
        "logo": {"username": "ロゴ", "icon_url": "https://example.com/logo.png"},
        "both": {"username": "両方", "icon_emoji": ":wave:", "icon_url": "https://example.com/x.png"},
    },
}
PRESHIP = {"channel": "CDEFAULT", "text": "本文", "username": "Preship 広告",
           "icon_emoji": ":chart_with_upwards_trend:", "unfurl_links": False}


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeUrlopen:
    """urlopen の代わり。受けたリクエストを覚え、決めた応答を返す。"""

    def __init__(self, body=None, error=None):
        self.requests = []
        self.body = {"ok": True, "channel": "CDEFAULT", "ts": "1700000000.000100"} if body is None else body
        self.error = error

    def __call__(self, request, timeout=None):
        self.requests.append({"url": request.full_url, "method": request.get_method(),
                              "headers": {k.lower(): v for k, v in request.header_items()},
                              "payload": json.loads(request.data.decode("utf-8")), "timeout": timeout})
        if self.error:
            raise self.error(request)
        return Response(json.dumps(self.body).encode("utf-8"))


class Notify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.kinds = Path(self.tmp.name) / "kinds.json"
        self.write_kinds(CONFIG)
        self.urlopen = FakeUrlopen()

    def tearDown(self):
        self.tmp.cleanup()

    def write_kinds(self, config):
        self.kinds.write_text(config if isinstance(config, str) else json.dumps(config, ensure_ascii=False))

    def run_main(self, *argv, stdin="", token=TOKEN):
        env = {"SLACK_NOTIFY_KINDS": str(self.kinds)}
        if token is not None:
            env["SLACK_BOT_TOKEN"] = token
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = M.main(list(argv), env, io.StringIO(stdin), self.urlopen)
        return code, out.getvalue(), err.getvalue()

    def sent(self):
        self.assertEqual(len(self.urlopen.requests), 1)
        return self.urlopen.requests[0]["payload"]

    def test_posts_with_the_kind_name_icon_and_default_channel(self):
        code, out, err = self.run_main("--kind", "preship", "--text", "本文")
        self.assertEqual((code, err), (0, ""))
        request = self.urlopen.requests[0]
        self.assertEqual((request["url"], request["method"]), ("https://slack.com/api/chat.postMessage", "POST"))
        self.assertTrue(request["timeout"])
        self.assertEqual(self.sent(), PRESHIP)
        self.assertEqual(out, "CDEFAULT 1700000000.000100\n")

    def test_channel_comes_from_the_flag_then_the_kind_then_the_default(self):
        self.run_main("--kind", "ops", "--text", "x")
        self.run_main("--kind", "ops", "--channel", "CFLAG", "--text", "x")
        self.run_main("--kind", "preship", "--channel", "CFLAG", "--text", "x")
        self.assertEqual([r["payload"]["channel"] for r in self.urlopen.requests], ["COPS", "CFLAG", "CFLAG"])

    def test_token_goes_only_into_the_authorization_header(self):
        code, out, err = self.run_main("--kind", "preship", "--text", "本文")
        headers = self.urlopen.requests[0]["headers"]
        self.assertEqual(headers["authorization"], "Bearer " + TOKEN)
        self.assertIn("charset=utf-8", headers["content-type"])
        self.assertNotIn(TOKEN, json.dumps(self.sent()) + out + err)

    def test_unknown_kind_exits_2_and_lists_the_known_kinds(self):
        code, out, err = self.run_main("--kind", "prehsip", "--text", "本文")
        self.assertEqual((code, out, self.urlopen.requests), (2, "", []))
        self.assertIn("prehsip", err)
        for kind in CONFIG["kinds"]:
            self.assertIn(kind, err)

    def test_missing_token_exits_2_with_a_clear_message(self):
        for token in (None, ""):
            code, out, err = self.run_main("--kind", "preship", "--text", "本文", token=token)
            self.assertEqual((code, out), (2, ""), token)
            self.assertIn("SLACK_BOT_TOKEN", err)
        self.assertEqual(self.urlopen.requests, [])

    def test_slack_error_exits_1_and_prints_only_the_error_code(self):
        self.urlopen = FakeUrlopen({"ok": False, "error": "not_in_channel", "warning": "superfluous_charset",
                                    "response_metadata": {"warnings": ["superfluous_charset"]}})
        code, out, err = self.run_main("--kind", "preship", "--text", "本文")
        self.assertEqual((code, out), (1, ""))
        self.assertEqual(err, "slack-notify: not_in_channel\n")

    def test_network_error_exits_1_without_the_token(self):
        def refused(request):
            return OSError("connection refused for %s" % request.get_header("Authorization"))

        self.urlopen = FakeUrlopen(error=refused)
        code, out, err = self.run_main("--kind", "preship", "--text", "本文")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("OSError", err)
        self.assertNotIn(TOKEN, err)

    def test_dry_run_prints_the_payload_and_sends_nothing(self):
        for token in (TOKEN, None):
            code, out, err = self.run_main("--kind", "preship", "--text", "本文", "--dry-run", token=token)
            self.assertEqual((code, err), (0, ""))
            self.assertEqual(json.loads(out), PRESHIP)
            self.assertNotIn(TOKEN, out)
        self.assertEqual(self.urlopen.requests, [])

    def test_text_is_read_from_stdin_when_the_flag_is_absent(self):
        self.assertEqual(self.run_main("--kind", "preship", stdin="一行目\n二行目\n")[0], 0)
        self.run_main("--kind", "preship", "--text", "引数", stdin="標準入力")
        self.assertEqual([r["payload"]["text"] for r in self.urlopen.requests], ["一行目\n二行目", "引数"])

    def test_empty_text_fails_without_sending(self):
        for argv, stdin in ((("--text", ""), "標準入力"), (("--text", " \n"), ""), ((), ""), ((), "  \n\n")):
            code, out, err = self.run_main("--kind", "preship", *argv, stdin=stdin)
            self.assertEqual((code, out), (2, ""), (argv, stdin))
            self.assertIn("本文", err)
        self.assertEqual(self.urlopen.requests, [])

    def test_icon_url_is_used_only_without_icon_emoji(self):
        self.run_main("--kind", "logo", "--text", "x")
        self.run_main("--kind", "both", "--text", "x")
        logo, both = (r["payload"] for r in self.urlopen.requests)
        self.assertEqual((logo.get("icon_url"), logo.get("icon_emoji")), ("https://example.com/logo.png", None))
        self.assertEqual((both.get("icon_emoji"), both.get("icon_url")), (":wave:", None))

    def test_missing_or_broken_config_exits_2_naming_the_file(self):
        for content in (None, "{not json", "[]", '{"kinds": 3}'):
            if content is None:
                self.kinds.unlink(missing_ok=True)
            else:
                self.write_kinds(content)
            code, out, err = self.run_main("--kind", "preship", "--text", "x")
            self.assertEqual((code, out), (2, ""), content)
            self.assertIn(str(self.kinds), err)
        self.assertEqual(self.urlopen.requests, [])

    def test_kind_without_a_username_is_refused(self):
        self.write_kinds({"default_channel": "C1", "kinds": {"anon": {"icon_emoji": ":ghost:"}, "bad": "x"}})
        for kind in ("anon", "bad"):
            code, out, err = self.run_main("--kind", kind, "--text", "x")
            self.assertEqual((code, out), (2, ""), kind)
            self.assertIn("username", err)
        self.assertEqual(self.urlopen.requests, [])

    def test_no_channel_anywhere_exits_2(self):
        self.write_kinds({"kinds": {"preship": CONFIG["kinds"]["preship"]}})
        code, out, err = self.run_main("--kind", "preship", "--text", "x")
        self.assertEqual((code, out, self.urlopen.requests), (2, "", []))
        self.assertIn("--channel", err)


class ShippedKinds(unittest.TestCase):
    def test_the_four_initial_kinds_post_to_n_efg_claude(self):
        config = json.loads(SHIPPED_KINDS.read_text(encoding="utf-8"))
        self.assertEqual(config["default_channel"], "C0CDQP2MLN9")
        looks = {k: (v["username"], v["icon_emoji"]) for k, v in config["kinds"].items()}
        self.assertEqual(looks, {
            "preship": ("Preship 広告", ":chart_with_upwards_trend:"),
            "tower": ("tower", ":building_construction:"),
            "runway": ("資金繰り", ":moneybag:"),
            "blocker": ("要対応", ":rotating_light:"),
        })
        self.assertTrue(all("channel" not in v for v in config["kinds"].values()))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, input=None, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith("SLACK_")}
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], env={**base, **env}, input=input,
                              capture_output=True, text=True, timeout=30)

    def test_help_describes_the_flags(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        for flag in ("--kind", "--channel", "--text", "--dry-run"):
            self.assertIn(flag, result.stdout)

    def test_kind_is_required(self):
        self.assertEqual(self.run_cli("--text", "x").returncode, 2)

    def test_default_config_is_read_from_home_and_stdin_feeds_the_dry_run(self):
        config_dir = Path(self.tmp.name) / ".config/slack-notify"
        config_dir.mkdir(parents=True)
        (config_dir / "kinds.json").write_text(SHIPPED_KINDS.read_text(encoding="utf-8"), encoding="utf-8")
        result = self.run_cli("--kind", "runway", "--dry-run", input="残高\n", HOME=self.tmp.name)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        self.assertEqual(json.loads(result.stdout), {"channel": "C0CDQP2MLN9", "text": "残高", "username": "資金繰り",
                                                     "icon_emoji": ":moneybag:", "unfurl_links": False})

    def test_missing_token_and_unknown_kind_fail_with_2(self):
        env = {"SLACK_NOTIFY_KINDS": str(SHIPPED_KINDS)}
        result = self.run_cli("--kind", "tower", "--text", "x", **env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("SLACK_BOT_TOKEN", result.stderr)
        result = self.run_cli("--kind", "towr", "--text", "x", SLACK_BOT_TOKEN=TOKEN, **env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("blocker", result.stderr)
        self.assertNotIn(TOKEN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
