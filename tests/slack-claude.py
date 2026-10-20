"""No network, no claude: verify event selection, sessions, command line, splitting and the reply flow."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import logging
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "dot_local/bin/executable_slack-claude"
sys.dont_write_bytecode = True
logging.disable(logging.CRITICAL)  # 失敗系テストの traceback を出さない
LOADER = SourceFileLoader("slack_claude", str(SCRIPT))
M = module_from_spec(spec_from_loader("slack_claude", LOADER))
sys.modules["slack_claude"] = M  # dataclasses が型注釈の解決でモジュールを引く
LOADER.exec_module(M)

OWNER = "U03L2HM8Q4X"
TEAM = "T03LKHSP0TW"
BOT = "UBOT0001"


def ev(**kw):
    event = {"type": "message", "user": OWNER, "team": TEAM, "channel": "D1", "channel_type": "im",
             "ts": "100.1", "event_ts": "100.1", "text": "hello", "client_msg_id": "m1"}
    event.update(kw)
    return event


def select(event, active=(), envelope_team=None):
    return M.select_request(event, BOT, lambda key: key in active, envelope_team)


class SelectRequest(unittest.TestCase):
    def test_dm_is_always_accepted_without_mention(self):
        req = select(ev())
        self.assertEqual((req.channel, req.ts, req.thread_ts, req.text), ("D1", "100.1", "100.1", "hello"))
        self.assertEqual(req.key, "D1:100.1")

    def test_ignores_everyone_but_the_owner_in_the_owner_team(self):
        self.assertIsNone(select(ev(user="UOTHER")))
        self.assertIsNone(select(ev(team="TOTHER")))
        self.assertIsNone(select(ev(user_team="TOTHER")))
        self.assertIsNone(select(ev(user=None)))

    def test_team_falls_back_to_the_envelope_and_unknown_team_is_ignored(self):
        self.assertIsNotNone(select(ev(team=None), envelope_team=TEAM))
        self.assertIsNone(select(ev(team=None), envelope_team="TOTHER"))
        self.assertIsNone(select(ev(team=None)))

    def test_ignores_bots_own_messages_and_any_subtype(self):
        self.assertIsNone(select(ev(user=BOT)))
        self.assertIsNone(select(ev(bot_id="B1")))
        for subtype in ("message_changed", "message_deleted", "bot_message", "file_share", "thread_broadcast"):
            self.assertIsNone(select(ev(subtype=subtype)), subtype)

    def test_ignores_other_event_types_and_malformed_events(self):
        self.assertIsNone(select(ev(type="reaction_added")))
        self.assertIsNone(select(ev(channel=None)))
        self.assertIsNone(select(ev(ts=None)))
        self.assertIsNone(select(ev(channel_type="app_home")))

    def test_channel_needs_a_mention_or_an_active_thread(self):
        channel = ev(channel="C1", channel_type="channel")
        self.assertIsNone(select(channel))
        self.assertIsNotNone(select({**channel, "text": "<@%s> hi" % BOT}))
        reply = {**channel, "ts": "101.0", "thread_ts": "100.1"}
        self.assertIsNone(select(reply))
        self.assertIsNone(select(reply, active={"C9:100.1"}))
        self.assertEqual(select(reply, active={"C1:100.1"}).key, "C1:100.1")

    def test_private_channel_and_group_dm_follow_the_channel_rule(self):
        for ctype in ("group", "mpim"):
            event = ev(channel="G1", channel_type=ctype)
            self.assertIsNone(select(event), ctype)
            self.assertIsNotNone(select({**event, "text": "<@%s>やって" % BOT}), ctype)
            self.assertIsNotNone(select({**event, "thread_ts": "50.0"}, active={"G1:50.0"}), ctype)

    def test_mention_event_is_accepted_and_the_mention_is_removed(self):
        event = {"type": "app_mention", "user": OWNER, "channel": "C1", "ts": "5.5",
                 "event_ts": "5.5", "text": "<@%s>  ビルドして <@%s|bot>" % (BOT, BOT)}
        req = select(event, envelope_team=TEAM)
        self.assertEqual(req.text, "ビルドして")
        self.assertEqual(req.thread_ts, "5.5")

    def test_mention_of_somebody_else_is_kept(self):
        req = select(ev(text="<@UOTHER> に聞いて"))
        self.assertEqual(req.text, "<@UOTHER> に聞いて")

    def test_text_that_is_empty_after_removing_the_mention_is_ignored(self):
        self.assertIsNone(select(ev(channel="C1", channel_type="channel", text="<@%s>" % BOT)))
        self.assertIsNone(select(ev(text="   ")))
        self.assertIsNone(select(ev(text=None)))

    def test_thread_reply_is_keyed_by_thread_ts(self):
        req = select(ev(ts="9.9", thread_ts="1.1"))
        self.assertEqual((req.thread_ts, req.key), ("1.1", "D1:1.1"))

    def test_slack_escapes_are_decoded_for_the_model(self):
        self.assertEqual(select(ev(text="a &lt; b &amp;&amp; c &gt; d &amp;lt;")).text, "a < b && c > d &lt;")


class Dedup(unittest.TestCase):
    def test_same_message_through_two_events_is_seen_once(self):
        mention = select({"type": "app_mention", "user": OWNER, "channel": "C1", "ts": "5.5", "event_ts": "5.5",
                          "text": "<@%s> x" % BOT}, envelope_team=TEAM)
        message = select(ev(channel="C1", channel_type="channel", ts="5.5", event_ts="5.5",
                            text="<@%s> x" % BOT, client_msg_id="m5"))
        seen = M.Dedup()
        self.assertFalse(seen.check_and_add(mention.dedup_keys))
        self.assertTrue(seen.check_and_add(message.dedup_keys))

    def test_client_msg_id_alone_is_enough(self):
        seen = M.Dedup()
        self.assertFalse(seen.check_and_add(select(ev(ts="1.0", event_ts="1.0")).dedup_keys))
        self.assertTrue(seen.check_and_add(select(ev(ts="2.0", event_ts="2.0")).dedup_keys))

    def test_different_messages_are_not_duplicates(self):
        seen = M.Dedup()
        self.assertFalse(seen.check_and_add(select(ev(ts="1.0", event_ts="1.0", client_msg_id="a")).dedup_keys))
        self.assertFalse(seen.check_and_add(select(ev(ts="2.0", event_ts="2.0", client_msg_id="b")).dedup_keys))
        self.assertFalse(seen.check_and_add(select(ev(channel="D2", ts="1.0", event_ts="1.0", client_msg_id="c")).dedup_keys))

    def test_memory_is_bounded(self):
        seen = M.Dedup(capacity=3)
        for i in range(10):
            seen.check_and_add((("c", "D1", str(i)),))
        self.assertFalse(seen.check_and_add((("c", "D1", "0"),)))
        self.assertTrue(seen.check_and_add((("c", "D1", "9"),)))


class SessionStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state" / "sessions.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_round_trip_survives_a_restart(self):
        store = M.SessionStore(self.path)
        self.assertIsNone(store.get("D1:1.1"))
        self.assertNotIn("D1:1.1", store)
        store.set("D1:1.1", "sess-a")
        store.set("C1:2.2", "sess-b")
        store.set("D1:1.1", "sess-c")
        again = M.SessionStore(self.path)
        self.assertEqual(again.get("D1:1.1"), "sess-c")
        self.assertEqual(again.get("C1:2.2"), "sess-b")
        self.assertIn("C1:2.2", again)

    def test_write_is_atomic_private_and_leaves_no_temp_files(self):
        store = M.SessionStore(self.path)
        store.set("D1:1.1", "sess-a")
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ["sessions.json"])
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        json.loads(self.path.read_text())

    def test_corrupt_or_wrong_shaped_file_is_treated_as_empty(self):
        self.path.parent.mkdir(parents=True)
        for content in ("{not json", "[]", '{"threads": 3}', ""):
            self.path.write_text(content)
            store = M.SessionStore(self.path)
            self.assertIsNone(store.get("D1:1.1"))
            store.set("D1:1.1", "x")
            self.assertEqual(M.SessionStore(self.path).get("D1:1.1"), "x")

    def test_concurrent_writers_do_not_lose_updates(self):
        store = M.SessionStore(self.path)
        threads = [threading.Thread(target=store.set, args=("K:%d" % i, "s%d" % i)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        again = M.SessionStore(self.path)
        self.assertEqual([again.get("K:%d" % i) for i in range(20)], ["s%d" % i for i in range(20)])


class ClaudeCommand(unittest.TestCase):
    def test_first_message_starts_a_json_print_session(self):
        cmd = M.build_claude_command("/bin/claude", "やって")
        self.assertEqual(cmd[:2], ["/bin/claude", "-p"])
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json")
        self.assertNotIn("--resume", cmd)
        self.assertEqual(cmd[-2:], ["--", "やって"])

    def test_next_message_resumes_the_stored_session(self):
        cmd = M.build_claude_command("/bin/claude", "続き", "sess-1")
        self.assertEqual(cmd[cmd.index("--resume") + 1], "sess-1")
        self.assertEqual(cmd[-2:], ["--", "続き"])

    def test_prompt_that_looks_like_an_option_stays_one_argument(self):
        cmd = M.build_claude_command("/bin/claude", "--help me")
        self.assertEqual(cmd[-2:], ["--", "--help me"])

    def test_no_permission_flag_is_widened_and_nobody_is_asked(self):
        cmd = M.build_claude_command("/bin/claude", "x", "s")
        for flag in ("--dangerously-skip-permissions", "--allow-dangerously-skip-permissions",
                     "--permission-mode", "--allowedTools", "--allowed-tools"):
            self.assertNotIn(flag, cmd)
        self.assertEqual(cmd[cmd.index("--permission-prompts") + 1], "none")

    def test_slack_and_op_tokens_are_not_handed_to_claude(self):
        env = {"PATH": "/bin", "SLACK_APP_TOKEN": "a", "SLACK_BOT_TOKEN": "b", "OP_SERVICE_ACCOUNT_TOKEN": "c"}
        self.assertEqual(M.claude_env(env), {"PATH": "/bin"})
        self.assertIn("SLACK_BOT_TOKEN", env)


class ParseResult(unittest.TestCase):
    def test_success(self):
        out = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                          "result": "完了", "session_id": "s1"})
        self.assertEqual(M.parse_claude_result(out, 0, ""), M.ClaudeResult("s1", "完了", False))

    def test_error_result_keeps_the_session_and_message(self):
        out = json.dumps({"type": "result", "subtype": "error_max_turns", "is_error": True,
                          "result": "上限", "session_id": "s2"})
        self.assertEqual(M.parse_claude_result(out, 1, ""), M.ClaudeResult("s2", "上限", True))

    def test_nonzero_exit_is_an_error_even_if_json_says_ok(self):
        out = json.dumps({"type": "result", "is_error": False, "result": "x", "session_id": "s"})
        self.assertTrue(M.parse_claude_result(out, 1, "").is_error)

    def test_array_output_uses_the_result_entry(self):
        out = json.dumps([{"type": "system"}, {"type": "result", "is_error": False, "result": "r", "session_id": "s3"}])
        self.assertEqual(M.parse_claude_result(out, 0, ""), M.ClaudeResult("s3", "r", False))

    def test_non_json_output_becomes_an_error_summary_from_stderr(self):
        res = M.parse_claude_result("", 1, "No conversation found with session ID: x\n  more")
        self.assertEqual((res.session_id, res.is_error), (None, True))
        self.assertIn("No conversation found", res.text)
        self.assertNotIn("\n", res.text)
        self.assertIn("2", M.parse_claude_result("", 2, "").text)

    def test_error_summary_is_short(self):
        self.assertLessEqual(len(M.summarize_error("x" * 5000)), 300)
        self.assertEqual(M.summarize_error("a \n\n b\tc"), "a b c")


class RunClaude(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake = Path(self.tmp.name) / "claude"

    def tearDown(self):
        self.tmp.cleanup()

    def write_fake(self, body):
        self.fake.write_text("#!%s\nimport json, os, sys, time\n%s\n" % (sys.executable, body))
        self.fake.chmod(0o700)

    def test_runs_in_cwd_with_scrubbed_env_and_parses_the_result(self):
        self.write_fake('print(json.dumps({"type": "result", "is_error": False, "session_id": "sid",'
                        ' "result": json.dumps([sys.argv[1:], os.getcwd(), "SLACK_BOT_TOKEN" in os.environ,'
                        ' os.environ.get("KEEP")])}))')
        env = {**os.environ, "SLACK_BOT_TOKEN": "secret", "KEEP": "yes"}
        cwd = Path(self.tmp.name).resolve()
        res = M.run_claude(str(self.fake), "本文", "old", str(cwd), 30, env)
        args, seen_cwd, leaked, keep = json.loads(res.text)
        self.assertEqual(res.session_id, "sid")
        self.assertEqual(args, M.build_claude_command("claude", "本文", "old")[1:])
        self.assertEqual((Path(seen_cwd).resolve(), leaked, keep), (cwd, False, "yes"))

    def test_timeout_kills_the_process_group_and_reports(self):
        marker = Path(self.tmp.name) / "child-survived"
        child = "import time, pathlib\ntime.sleep(2)\npathlib.Path(%r).write_text('x')" % str(marker)
        self.write_fake("import subprocess\n"
                        "subprocess.Popen([sys.executable, '-c', %r])\n"
                        "time.sleep(60)" % child)
        res = M.run_claude(str(self.fake), "x", None, self.tmp.name, 0.5, os.environ)
        self.assertTrue(res.is_error)
        self.assertIn("タイムアウト", res.text)
        self.assertIsNone(res.session_id)
        import time
        time.sleep(2.5)
        self.assertFalse(marker.exists())

    def test_missing_binary_is_reported_as_an_error_result(self):
        res = M.run_claude(str(Path(self.tmp.name) / "none"), "x", None, self.tmp.name, 5, os.environ)
        self.assertTrue(res.is_error)


class SplitMessage(unittest.TestCase):
    def check(self, text, limit):
        chunks = M.split_message(text, limit)
        self.assertTrue(all(0 < len(c) <= limit for c in chunks), [len(c) for c in chunks])
        self.assertEqual("".join("".join(c.split()) for c in chunks), "".join(text.split()))
        return chunks

    def test_short_text_is_one_chunk(self):
        self.assertEqual(M.split_message("abc", 10), ["abc"])
        self.assertEqual(M.split_message("x" * 10, 10), ["x" * 10])

    def test_prefers_paragraph_then_line_boundaries(self):
        text = "a" * 40 + "\n\n" + "b" * 40 + "\n\n" + "c" * 40
        self.assertEqual(self.check(text, 90), ["a" * 40 + "\n\n" + "b" * 40, "c" * 40])
        lines = "\n".join("l%02d" % i + "x" * 7 for i in range(30))
        chunks = self.check(lines, 50)
        self.assertTrue(all(c.startswith("l") and c.endswith("x") for c in chunks))

    def test_long_line_without_breaks_is_cut_at_the_limit(self):
        self.assertEqual([len(c) for c in self.check("あ" * 25, 10)], [10, 10, 5])

    def test_long_words_split_at_a_space_when_possible(self):
        chunks = self.check(" ".join(["hello"] * 30), 20)
        self.assertTrue(all(c == c.strip() for c in chunks))

    def test_mixed_content(self):
        text = "\n\n".join(["p" * 5000, "q\n" * 3000, "r" * 10, ""])
        self.check(text, M.SLACK_CHUNK_LIMIT)
        self.assertLessEqual(M.SLACK_CHUNK_LIMIT, 4000)


class SerialRunner(unittest.TestCase):
    def test_same_key_runs_in_order_one_at_a_time(self):
        runner, order, active, overlap, done = M.SerialRunner(), [], [0], [], threading.Event()

        def task(i, last=False):
            def run():
                active[0] += 1
                overlap.append(active[0])
                threading.Event().wait(0.02)
                order.append(i)
                active[0] -= 1
                if last:
                    done.set()
            return run

        for i in range(5):
            runner.submit("K", task(i, last=i == 4))
        self.assertTrue(done.wait(10))
        self.assertEqual(order, [0, 1, 2, 3, 4])
        self.assertEqual(max(overlap), 1)

    def test_different_keys_run_in_parallel(self):
        runner, a_started, b_ran, result = M.SerialRunner(), threading.Event(), threading.Event(), []

        def a():
            a_started.set()
            result.append(b_ran.wait(10))

        runner.submit("A", a)
        self.assertTrue(a_started.wait(10))
        runner.submit("B", b_ran.set)
        deadline = threading.Event()
        for _ in range(100):
            if result:
                break
            deadline.wait(0.1)
        self.assertEqual(result, [True])

    def test_a_failing_task_does_not_stop_the_queue(self):
        runner, done = M.SerialRunner(), threading.Event()

        def boom():
            raise RuntimeError("x")

        runner.submit("K", boom)
        runner.submit("K", done.set)
        self.assertTrue(done.wait(10))


class FakeSlack:
    def __init__(self):
        self.calls = []

    def react(self, channel, ts, name):
        self.calls.append(("react", channel, ts, name))

    def unreact(self, channel, ts, name):
        self.calls.append(("unreact", channel, ts, name))

    def post(self, channel, thread_ts, text):
        self.calls.append(("post", channel, thread_ts, text))

    def posts(self):
        return [c for c in self.calls if c[0] == "post"]


class FakeWebClient:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def _record(self, method, kwargs):
        self.calls.append((method, kwargs))
        if self.fail:
            raise self.fail

    def reactions_add(self, **kw):
        self._record("reactions_add", kw)

    def reactions_remove(self, **kw):
        self._record("reactions_remove", kw)

    def chat_postMessage(self, **kw):
        self._record("chat_postMessage", kw)


class BoltSlack(unittest.TestCase):
    def test_maps_the_three_operations_onto_the_web_client(self):
        client = FakeWebClient()
        slack = M.BoltSlack(client)
        slack.react("C1", "1.0", "eyes")
        slack.unreact("C1", "1.0", "eyes")
        slack.post("C1", "0.5", "本文")
        self.assertEqual(client.calls, [
            ("reactions_add", {"channel": "C1", "timestamp": "1.0", "name": "eyes"}),
            ("reactions_remove", {"channel": "C1", "timestamp": "1.0", "name": "eyes"}),
            ("chat_postMessage", {"channel": "C1", "thread_ts": "0.5", "text": "本文"})])

    def test_api_errors_are_swallowed(self):
        slack = M.BoltSlack(FakeWebClient(fail=RuntimeError("already_reacted")))
        slack.react("C1", "1.0", "eyes")
        slack.unreact("C1", "1.0", "eyes")
        slack.post("C1", "0.5", "x")


class InlineRunner:
    def submit(self, key, fn):
        fn()


class DeferredRunner:
    def __init__(self):
        self.tasks = []

    def submit(self, key, fn):
        self.tasks.append((key, fn))

    def run_all(self):
        while self.tasks:
            self.tasks.pop(0)[1]()


class BotFlow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.slack = FakeSlack()
        self.store = M.SessionStore(Path(self.tmp.name) / "sessions.json")
        self.claude_calls = []
        self.reply = M.ClaudeResult("sess-1", "こんにちは", False)

    def tearDown(self):
        self.tmp.cleanup()

    def claude(self, prompt, session_id):
        self.claude_calls.append((prompt, session_id))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply

    def bot(self, runner=None):
        return M.Bot(self.slack, self.store, self.claude, BOT, runner or InlineRunner())

    def test_dm_gets_eyes_then_reply_in_thread_then_check(self):
        self.bot().handle_event(ev())
        self.assertEqual(self.claude_calls, [("hello", None)])
        self.assertEqual(self.slack.calls[0], ("react", "D1", "100.1", "eyes"))
        self.assertEqual(self.slack.posts(), [("post", "D1", "100.1", "こんにちは")])
        self.assertEqual(self.slack.calls[-1], ("react", "D1", "100.1", "white_check_mark"))
        self.assertIn(("unreact", "D1", "100.1", "eyes"), self.slack.calls)
        self.assertEqual(self.store.get("D1:100.1"), "sess-1")

    def test_reply_goes_to_the_thread_of_a_threaded_message(self):
        self.bot().handle_event(ev(channel="C1", channel_type="channel", ts="200.2", thread_ts="100.1",
                                   text="<@%s> hi" % BOT))
        self.assertEqual(self.claude_calls, [("hi", None)])
        self.assertEqual(self.slack.posts(), [("post", "C1", "100.1", "こんにちは")])
        self.assertEqual(self.slack.calls[0], ("react", "C1", "200.2", "eyes"))
        self.assertEqual(self.store.get("C1:100.1"), "sess-1")

    def test_second_message_resumes_and_follow_up_without_mention_is_accepted(self):
        bot = self.bot()
        bot.handle_event(ev(channel="C1", channel_type="channel", text="<@%s> start" % BOT))
        self.reply = M.ClaudeResult("sess-2", "続き", False)
        bot.handle_event(ev(channel="C1", channel_type="channel", ts="101.0", event_ts="101.0",
                            thread_ts="100.1", text="続けて", client_msg_id="m2"))
        self.assertEqual(self.claude_calls, [("start", None), ("続けて", "sess-1")])
        self.assertEqual(self.store.get("C1:100.1"), "sess-2")

    def test_thread_is_active_as_soon_as_it_is_accepted(self):
        runner = DeferredRunner()
        bot = self.bot(runner)
        bot.handle_event(ev(channel="C1", channel_type="channel", text="<@%s> start" % BOT))
        bot.handle_event(ev(channel="C1", channel_type="channel", ts="101.0", event_ts="101.0",
                            thread_ts="100.1", text="追伸", client_msg_id="m2"))
        self.assertEqual(len(runner.tasks), 2)
        self.assertEqual({key for key, _ in runner.tasks}, {"C1:100.1"})
        runner.run_all()
        self.assertEqual([c[0] for c in self.claude_calls], ["start", "追伸"])
        self.assertEqual(self.claude_calls[1][1], "sess-1")

    def test_unrelated_events_do_nothing(self):
        bot = self.bot()
        bot.handle_event(ev(channel="C1", channel_type="channel"))
        bot.handle_event(ev(user="UOTHER"))
        bot.handle_event(ev(subtype="message_changed"))
        self.assertEqual((self.claude_calls, self.slack.calls), ([], []))

    def test_mention_and_message_for_the_same_post_run_once(self):
        bot = self.bot()
        bot.handle_event({"type": "app_mention", "user": OWNER, "channel": "C1", "ts": "5.5", "event_ts": "5.5",
                          "text": "<@%s> x" % BOT}, TEAM)
        bot.handle_event(ev(channel="C1", channel_type="channel", ts="5.5", event_ts="5.5",
                            text="<@%s> x" % BOT, client_msg_id="m5"), TEAM)
        self.assertEqual(len(self.claude_calls), 1)
        self.assertEqual(len(self.slack.posts()), 1)

    def test_failure_marks_x_and_posts_a_summary(self):
        self.reply = M.ClaudeResult("sess-9", "token limit\nexceeded", True)
        self.bot().handle_event(ev())
        self.assertEqual(self.slack.calls[-1], ("react", "D1", "100.1", "x"))
        post = self.slack.posts()[0]
        self.assertEqual(post[:3], ("post", "D1", "100.1"))
        self.assertIn(":x:", post[3])
        self.assertIn("token limit exceeded", post[3])
        self.assertNotIn(("react", "D1", "100.1", "white_check_mark"), self.slack.calls)
        self.assertEqual(self.store.get("D1:100.1"), "sess-9")

    def test_exception_in_claude_runner_is_reported_not_raised(self):
        self.reply = RuntimeError("spawn failed")
        self.bot().handle_event(ev())
        self.assertEqual(self.slack.calls[-1], ("react", "D1", "100.1", "x"))
        self.assertIn("spawn failed", self.slack.posts()[0][3])

    def test_empty_result_still_answers(self):
        self.reply = M.ClaudeResult("s", "", False)
        self.bot().handle_event(ev())
        self.assertEqual(len(self.slack.posts()), 1)
        self.assertTrue(self.slack.posts()[0][3].strip())

    def test_long_reply_is_split_into_thread_posts(self):
        self.reply = M.ClaudeResult("s", "\n\n".join("段落%d " % i + "あ" * 1500 for i in range(8)), False)
        self.bot().handle_event(ev())
        posts = self.slack.posts()
        self.assertGreater(len(posts), 1)
        self.assertTrue(all(p[2] == "100.1" and len(p[3]) <= M.SLACK_CHUNK_LIMIT for p in posts))


class SlackApi(unittest.TestCase):
    def test_slack_api_posts_json_with_a_bearer_token(self):
        seen = {}

        class Response(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        def fake_urlopen(request, timeout=None):
            seen.update(url=request.full_url, headers={k.lower(): v for k, v in request.header_items()},
                        body=json.loads(request.data.decode()), timeout=timeout)
            return Response(b'{"ok": true, "ts": "1.0"}')

        out = M.slack_api("xoxb-secret", "chat.postMessage", {"channel": "D1", "text": "テスト"}, fake_urlopen)
        self.assertEqual(out["ts"], "1.0")
        self.assertEqual(seen["url"], "https://slack.com/api/chat.postMessage")
        self.assertEqual(seen["headers"]["authorization"], "Bearer xoxb-secret")
        self.assertIn("charset=utf-8", seen["headers"]["content-type"])
        self.assertEqual(seen["body"], {"channel": "D1", "text": "テスト"})
        self.assertTrue(seen["timeout"])

    def test_send_dm_opens_the_conversation_with_the_owner_then_posts(self):
        calls = []

        def api(token, method, payload):
            calls.append((token, method, payload))
            return {"ok": True, "channel": {"id": "D9"}}

        M.send_dm("xoxb-secret", "通知テスト", api)
        self.assertEqual(calls, [("xoxb-secret", "conversations.open", {"users": OWNER}),
                                 ("xoxb-secret", "chat.postMessage", {"channel": "D9", "text": "通知テスト"})])

    def test_slack_errors_never_contain_the_token(self):
        def api(token, method, payload):
            return {"ok": False, "error": "not_authed"}

        with self.assertRaises(M.SlackError) as ctx:
            M.send_dm("xoxb-secret", "x", api)
        self.assertIn("not_authed", str(ctx.exception))
        self.assertNotIn("xoxb-secret", str(ctx.exception))

        def broken_urlopen(request, timeout=None):
            raise OSError("connection refused for %s" % request.get_header("Authorization"))

        with self.assertRaises(M.SlackError) as ctx:
            M.slack_api("xoxb-secret", "chat.postMessage", {}, broken_urlopen)
        self.assertNotIn("xoxb-secret", str(ctx.exception))


class Cli(unittest.TestCase):
    def run_cli(self, *args, **env):
        base = {k: v for k, v in os.environ.items() if not k.startswith("SLACK_")}
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args], env={**base, **env},
                              capture_output=True, text=True, timeout=30)

    def test_help_works_without_slack_bolt(self):
        result = self.run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("serve", result.stdout)
        self.assertIn("dm", result.stdout)

    def test_no_subcommand_is_a_usage_error(self):
        self.assertEqual(self.run_cli().returncode, 2)

    def test_serve_without_tokens_fails_naming_the_variables_only(self):
        result = self.run_cli("serve")
        self.assertEqual(result.returncode, 1)
        self.assertIn("SLACK_APP_TOKEN", result.stderr)
        self.assertIn("SLACK_BOT_TOKEN", result.stderr)

    def test_serve_with_one_token_names_the_missing_one(self):
        result = self.run_cli("serve", SLACK_APP_TOKEN="xapp-secret")
        self.assertEqual(result.returncode, 1)
        self.assertIn("SLACK_BOT_TOKEN", result.stderr)
        self.assertNotIn("xapp-secret", result.stdout + result.stderr)

    def test_dm_without_token_fails(self):
        result = self.run_cli("dm", "テスト")
        self.assertEqual(result.returncode, 1)
        self.assertIn("SLACK_BOT_TOKEN", result.stderr)


if __name__ == "__main__":
    unittest.main()
