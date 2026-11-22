"""loop-watch: 定期処理の止まり方を見分け、同じ知らせを繰り返さない。systemd と Slack は呼ばない。"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("loop_watch", str(ROOT / "home/dot_local/bin/executable_loop-watch"))
spec = importlib.util.spec_from_loader("loop_watch", loader)
watch = importlib.util.module_from_spec(spec)
loader.exec_module(watch)
NOW = 1_800_000_000


def unit(load="loaded", result="success", ran_h_ago=1):
    return lambda name: (load, result, None if ran_h_ago is None else int(NOW - ran_h_ago * 3600))


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.dir.name, "out.json")
        Path(self.out).write_text("{}")
        os.utime(self.out, (NOW - 3600, NOW - 3600))

    def tearDown(self):
        self.dir.cleanup()

    def loop(self, **extra):
        return {"name": "x", "unit": "x.service", "max_age_h": 3, **extra}

    def test_unit_missing_on_this_host_is_skipped(self):
        self.assertIsNone(watch.check(self.loop(), NOW, unit(load="not-found")))

    def test_healthy_loop_has_no_problems(self):
        self.assertEqual(watch.check(self.loop(output={"path": self.out, "max_age_h": 2, "say": "古い"}), NOW, unit()), [])

    def test_failed_or_stale_run_is_reported(self):
        self.assertEqual(len(watch.check(self.loop(), NOW, unit(result="exit-code"))), 1)
        self.assertEqual(len(watch.check(self.loop(), NOW, unit(ran_h_ago=5))), 1)
        self.assertEqual(len(watch.check(self.loop(), NOW, unit(ran_h_ago=None))), 1)

    def test_success_exit_without_fresh_output_is_reported(self):
        problems = watch.check(self.loop(output={"path": self.out, "max_age_h": 0.5, "say": "結果が古い"}), NOW, unit())
        self.assertEqual(problems, ["結果が古い"])

    def test_stop_marker_counts_only_in_the_latest_cycle(self):
        log = os.path.join(self.dir.name, "cycle.log")
        bad = {"path": log, "since": "=== start ===", "pattern": "保留", "say": "止まった"}
        Path(log).write_text("=== start ===\n補充まで保留\n=== start ===\n予約した\n")
        self.assertEqual(watch.check(self.loop(bad_tail=bad), NOW, unit()), [])
        Path(log).write_text("=== start ===\n予約した\n=== start ===\n補充まで保留\n")
        self.assertEqual(watch.check(self.loop(bad_tail=bad), NOW, unit()), ["止まった"])


class DecideTest(unittest.TestCase):
    def test_new_problem_is_sent_and_repeat_waits_a_day(self):
        self.assertEqual(watch.decide("A", {}, NOW), "A")
        self.assertIsNone(watch.decide("A", {"message": "A", "sent_at": NOW - 3600}, NOW))
        self.assertEqual(watch.decide("A", {"message": "A", "sent_at": NOW - 25 * 3600}, NOW), "A")
        self.assertEqual(watch.decide("B", {"message": "A", "sent_at": NOW - 60}, NOW), "B")

    def test_recovery_is_sent_once(self):
        self.assertIn("戻りました", watch.decide("", {"message": "A", "sent_at": NOW}, NOW))
        self.assertIsNone(watch.decide("", {"message": "", "sent_at": NOW}, NOW))
        self.assertIsNone(watch.decide("", {}, NOW))

    def test_shipped_config_names_real_fields(self):
        loops = json.loads((ROOT / "home/private_dot_config/loop-watch/loops.json").read_text())["loops"]
        for loop in loops:
            self.assertTrue(loop["unit"].endswith(".service") and loop["max_age_h"] > 0, loop["name"])
            if "output" in loop:
                self.assertIn("say", loop["output"])


if __name__ == "__main__":
    unittest.main()
