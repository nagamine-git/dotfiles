"""agent-retro: 失敗した場面を拾い、教訓の台帳にまとめ、2 回起きたものだけを提案する。モデル呼び出しなし。"""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("agent_retro", str(ROOT / "home/dot_local/bin/executable_agent-retro"))
spec = importlib.util.spec_from_loader("agent_retro", loader)
retro = importlib.util.module_from_spec(spec)
loader.exec_module(retro)


def user(text, ts):
    return {"type": "message", "message": {"role": "user", "timestamp": ts, "content": [{"type": "text", "text": text}]}}


def assistant(text, ts):
    return {"type": "message", "message": {"role": "assistant", "timestamp": ts, "content": [{"type": "text", "text": text}]}}


def tool(name, ts, error):
    return {"type": "message", "message": {"role": "toolResult", "toolName": name, "isError": error, "timestamp": ts,
                                           "content": [{"type": "text", "text": "secret output"}]}}


class FlagTest(unittest.TestCase):
    def flags(self, entries, router=()):
        return retro.flag_session("s1", entries, list(router))

    def test_plain_exchange_is_not_flagged(self):
        self.assertEqual(self.flags([user("これを実装して", 1000), assistant("実装しました", 2000), user("ありがとう、次は README", 3000)]), [])

    def test_request_to_restate_is_flagged_with_the_reply_it_refers_to(self):
        eps = self.flags([user("調べて", 1000), assistant("zswap が zram の枠を予約し…", 2000), user("わかりやすくおしえて", 3000)])
        self.assertEqual([(e["signal"], e["ts"]) for e in eps], [("restate", 3000)])
        self.assertIn("zswap", eps[0]["reply"])
        self.assertEqual(eps[0]["said"], "わかりやすくおしえて")

    def test_bro_skill_counts_as_a_request_to_restate(self):
        eps = self.flags([assistant("長い説明", 1), user('<skill name="bro" location="x">Restate your last message.</skill>', 2)])
        self.assertEqual([e["signal"] for e in eps], ["restate"])

    def test_correction_is_flagged_but_ordinary_contrast_is_not(self):
        self.assertEqual([e["signal"] for e in self.flags([assistant("A にしました", 1), user("違う、B にして", 2)])], ["correction"])
        # 「ではなく」は普通の指示にも出るので拾わない
        self.assertEqual(self.flags([assistant("案です", 1), user("広告ではなく、製品デモを見たい", 2)]), [])

    def test_router_failed_judgement_is_joined_by_time(self):
        entries = [assistant("できました", 1000), user("動かないんだけど", 60000)]
        eps = self.flags(entries, router=[{"ts": 60400, "failed": 0.9}, {"ts": 999999, "failed": 0.9}])
        self.assertEqual([e["signal"] for e in eps], ["failed"])
        self.assertEqual(self.flags(entries, router=[{"ts": 60400, "failed": 0.2}]), [])

    def test_one_message_gets_one_episode_even_with_two_signals(self):
        eps = self.flags([assistant("x", 1), user("違う、わかりやすく", 5000)], router=[{"ts": 5000, "failed": 0.8}])
        self.assertEqual(len(eps), 1)

    def test_router_timestamps_may_be_iso_strings(self):
        entries = [assistant("できました", 1000), user("動かないんだけど", "1794745321000")]
        eps = self.flags(entries, router=[{"ts": "2026-11-15T12:22:01.641Z", "failed": 0.9}])
        self.assertEqual([e["signal"] for e in eps], ["failed"])

    def test_errors_with_a_success_in_between_are_not_a_streak(self):
        entries = [user("やって", 1), tool("bash", 2, True), tool("bash", 3, True), tool("bash", 4, False), tool("bash", 5, True), tool("bash", 6, True), assistant("ok", 7)]
        self.assertEqual(self.flags(entries), [])

    def test_three_tool_errors_in_one_turn_are_flagged_without_tool_output(self):
        entries = [user("やって", 1), tool("bash", 2, True), tool("bash", 3, True), tool("edit", 4, True), assistant("直しました", 5)]
        eps = self.flags(entries)
        self.assertEqual([(e["signal"], e["detail"]) for e in eps], [("tool-errors", "bash×2, edit×1")])
        self.assertNotIn("secret output", json.dumps(eps, ensure_ascii=False))
        self.assertEqual(self.flags([user("やって", 1), tool("bash", 2, True), tool("bash", 3, False), assistant("ok", 4)]), [])

    def test_long_pasted_messages_are_ignored(self):
        self.assertEqual(self.flags([assistant("x", 1), user("違う" + "あ" * 600, 2)]), [])


class LedgerTest(unittest.TestCase):
    def ep(self, session, ts):
        return {"session": session, "ts": ts, "signal": "restate"}

    def test_new_lesson_then_recurrence_in_another_session_becomes_a_proposal(self):
        ledger = {}
        first = retro.record(ledger, self.ep("s1", 1), {"lesson": "new", "title": "説明が専門的", "situation": "報告", "instead": "平易に", "kind": "instruction"})
        self.assertEqual(retro.proposals(ledger), [])  # 1 回だけでは提案しない
        retro.record(ledger, self.ep("s1", 2), {"lesson": first})
        self.assertEqual(retro.proposals(ledger), [])  # 同じセッションの中の 2 回は 1 回と数える
        retro.record(ledger, self.ep("s2", 3), {"lesson": first})
        self.assertEqual([p["id"] for p in retro.proposals(ledger)], [first])

    def test_same_title_answered_as_new_twice_is_one_lesson(self):
        ledger = {}
        new = {"lesson": "new", "title": "専門用語を説明なしに使わない", "situation": "s", "instead": "i", "kind": "instruction"}
        a = retro.record(ledger, self.ep("s1", 1), dict(new))
        b = retro.record(ledger, self.ep("s2", 2), dict(new))
        self.assertEqual((a, len(ledger), len(ledger[a]["episodes"])), (b, 1, 2))
        self.assertEqual([p["id"] for p in retro.proposals(ledger)], [a])

    def test_not_a_failure_is_counted_but_never_proposed(self):
        ledger = {}
        self.assertIsNone(retro.record(ledger, self.ep("s1", 1), {"lesson": "none"}))
        self.assertEqual(ledger, {})

    def test_unknown_lesson_id_from_the_model_is_dropped(self):
        ledger = {}
        self.assertIsNone(retro.record(ledger, self.ep("s1", 1), {"lesson": "L999"}))
        self.assertEqual(ledger, {})

    def test_proposed_once_and_recurrence_after_adoption_is_tracked(self):
        ledger = {}
        i = retro.record(ledger, self.ep("s1", 1), {"lesson": "new", "title": "t", "situation": "s", "instead": "i", "kind": "mechanical"})
        retro.record(ledger, self.ep("s2", 2), {"lesson": i})
        retro.mark(ledger, i, "proposed", now=10)
        self.assertEqual(retro.proposals(ledger), [])
        retro.mark(ledger, i, "adopted", now=100)
        retro.record(ledger, self.ep("s3", 50), {"lesson": i})   # 採用より前の場面
        retro.record(ledger, self.ep("s4", 200), {"lesson": i})  # 採用の後に再発
        self.assertEqual(retro.recurred_after_adoption(ledger[i]), 1)

    def test_at_most_three_proposals_and_the_most_repeated_first(self):
        ledger = {}
        for n in range(5):
            i = retro.record(ledger, self.ep("a", n), {"lesson": "new", "title": f"t{n}", "situation": "s", "instead": "i", "kind": "instruction"})
            for k in range(n + 1):
                retro.record(ledger, self.ep(f"b{k}", 100 + k), {"lesson": i})
        got = retro.proposals(ledger)
        self.assertEqual(len(got), 3)
        self.assertEqual(got[0]["title"], "t4")


class PreviewTest(unittest.TestCase):
    def ledger(self):
        ledger = {}
        new = {"lesson": "new", "title": "平易な言葉で言い直す", "situation": "報告", "instead": "短い文で書く", "kind": "instruction"}
        i = retro.record(ledger, {"session": "s1", "ts": 1, "signal": "restate"}, dict(new))
        retro.record(ledger, {"session": "s2", "ts": 2, "signal": "restate"}, dict(new))
        episodes = [{"session": "s1", "ts": 1, "signal": "restate", "reply": "古い返答", "said": "わかりやすく"},
                    {"session": "s2", "ts": 2, "signal": "restate", "reply": "zswap が zram の枠を予約する二重構成です", "said": "わかりやすくおしえて"}]
        return ledger, i, episodes

    def test_proposal_shows_what_was_said_before_and_how_it_would_read_after(self):
        ledger, i, episodes = self.ledger()
        answer = '[{"n": 1, "after": "メモリの節約機能が二重に動いていて、片方が無駄になっています", "change": "AGENTS.md に「内部の名前は言い換える」を足す"}]'
        retro.add_previews(ledger, [i], episodes, lambda prompt: answer)
        text = retro.render(i, ledger[i])
        self.assertIn("▼ これまで\n  zswap が zram", text)       # いちばん新しい場面の実際の返答
        self.assertIn("▼ あなた\n  わかりやすくおしえて", text)
        self.assertIn("▼ これから\n  メモリの節約機能が二重", text)
        self.assertIn("反映のしかた (指示に 1 行足す)\n" + retro.FENCE + "\nAGENTS.md に", text)
        self.assertEqual(text.count(retro.FENCE) % 2, 0)

    def test_skill_invocation_is_shown_by_meaning_and_the_model_sees_only_the_excerpt(self):
        ledger, i, episodes = self.ledger()
        episodes[1]["said"] = '<skill name="bro" location="/x/SKILL.md"> Restate your last message.'
        seen = []
        retro.add_previews(ledger, [i], episodes, lambda prompt: seen.append(prompt) or "[]")
        self.assertIn("/bro (もっと簡単に言って)", retro.render(i, ledger[i]))
        self.assertNotIn("SKILL.md", seen[0])

    def test_long_lines_wrap_and_backticks_cannot_break_the_block(self):
        text = retro.wrap("あ" * 40 + "abc" + retro.FENCE + "def")
        self.assertEqual(len(text.split("\n")[0].strip()), 34)
        self.assertNotIn(retro.FENCE, text)

    def test_model_failure_still_shows_the_real_exchange(self):
        ledger, i, episodes = self.ledger()

        def broken(prompt):
            raise RuntimeError("no model")
        retro.add_previews(ledger, [i], episodes, broken)
        text = retro.render(i, ledger[i])
        self.assertIn("▼ これまで\n  zswap", text)
        self.assertNotIn("これから", text)
        self.assertIn(retro.FENCE + "\n短い文で書く\n" + retro.FENCE, text)

    def test_preview_is_made_once_and_notify_sends_it(self):
        ledger, i, episodes = self.ledger()
        calls = []

        def ask(prompt):
            calls.append(prompt)
            return '[{"n": 1, "after": "あと", "change": "かえる"}]'
        retro.add_previews(ledger, [i], episodes, ask)
        retro.add_previews(ledger, [i], episodes, ask)
        self.assertEqual(len(calls), 1)
        self.assertNotIn("古い返答", calls[0])  # 見せるのは 1 場面だけ
        with tempfile.TemporaryDirectory() as tmp:
            retro._write_private(str(Path(tmp) / "ledger.json"), json.dumps(ledger, ensure_ascii=False))
            sent = []
            self.assertEqual(retro.notify(state=tmp, send=sent.append, ask=ask), "1 件を送った")
            self.assertIn("▼ これから\n  あと", sent[0])
            self.assertIn("「L1 を採用」", sent[0])


class StateTest(unittest.TestCase):
    def test_collect_is_incremental_and_keeps_private_files_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sessions = tmp / "sessions/proj"
            sessions.mkdir(parents=True)
            log = sessions / "a.jsonl"
            log.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in [assistant("x", 1000), user("わかりやすく", 2000)]) + "\n")
            state = tmp / "state"
            self.assertEqual(retro.collect(str(tmp / "sessions"), str(tmp / "none.jsonl"), str(state)), 1)
            self.assertEqual(retro.collect(str(tmp / "sessions"), str(tmp / "none.jsonl"), str(state)), 0)  # 2 回目は増えない
            with log.open("a") as f:
                f.write(json.dumps(assistant("y", 3000)) + "\n" + json.dumps(user("違う", 4000), ensure_ascii=False) + "\n")
            self.assertEqual(retro.collect(str(tmp / "sessions"), str(tmp / "none.jsonl"), str(state)), 1)
            self.assertEqual((state / "episodes.jsonl").stat().st_mode & 0o777, 0o600)

    def test_diagnosis_answer_is_parsed_strictly(self):
        ok = retro.parse_answer('前置き [{"n": 1, "lesson": "new", "title": "t", "situation": "s", "instead": "i", "kind": "skill"}, {"n": 2, "lesson": "none"}] 後書き', 2)
        self.assertEqual([a["lesson"] for a in ok], ["new", "none"])
        self.assertEqual(retro.parse_answer("JSON が無い", 2), [])
        self.assertEqual(retro.parse_answer('[{"n": 9, "lesson": "new", "title": "t"}]', 2), [])  # 番号が範囲外


if __name__ == "__main__":
    unittest.main()
