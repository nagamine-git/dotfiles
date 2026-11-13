"""Offline behavioral checks. Never starts a model, reads auth, or calls an API."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
LOADER = SourceFileLoader("model_route_plan", str(ROOT / "home/dot_local/bin/executable_model-route-plan"))
ROUTER = module_from_spec(spec_from_loader(LOADER.name, LOADER))
LOADER.exec_module(ROUTER)
POLICY = json.loads((ROOT / "docs/model-routing-policy.example.json").read_text())
TASK = json.loads((ROOT / "tests/fixtures/model-route-task.json").read_text())
NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


class RoutingPlan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"
        # Any accidental outbound connection, subprocess or model launch fails.
        for target in ("socket.socket", "socket.create_connection", "subprocess.Popen", "subprocess.run"):
            guard = patch(target, side_effect=AssertionError("External access forbidden in offline tests"))
            guard.start()
            self.addCleanup(guard.stop)

    def plan(self, task=None, policy=None, fixture=None, **kwargs):
        return ROUTER.prepare(policy or POLICY, task or TASK, self.state, fixture, now=NOW, **kwargs)

    def hard(self, **kwargs):
        return {**TASK, "task_id": str(uuid.uuid4()), "distinct_failed_hypotheses": 2, **kwargs}

    def api(self, **kwargs):
        return {**POLICY, "claude_auth_mode": "anthropic_api", "per_call_limit_cents": 50,
                "daily_limit_cents": 100, "monthly_limit_cents": 150, **kwargs}

    def test_original_seven_scenarios(self):
        cases = [
            ({}, "codex"),
            ({"distinct_failed_hypotheses": 2}, "opus"),
            ({"important_independent_review": True}, "opus"),
            ({"explicit_fable_exception": True}, "fable"),
            ({"distinct_failed_hypotheses": 2, "non_confidential": False}, "codex"),
            ({"authorization": "pending", "distinct_failed_hypotheses": 2}, "stop"),
            ({"safety_status": "refused", "explicit_fable_exception": True}, "stop"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes):
                result = self.plan({**TASK, "task_id": str(uuid.uuid4()), **changes})
                self.assertEqual(result["route"], expected)
                for key in ("execution_enabled", "ready_to_execute", "model_started"):
                    self.assertIs(result[key], False)
                self.assertEqual(result["external_calls"], 0)

    def test_one_failed_hypothesis_does_not_escalate(self):
        self.assertEqual(self.plan(self.hard(distinct_failed_hypotheses=1))["route"], "codex")

    def test_no_enable_switch(self):
        with self.assertRaises(ROUTER.Blocked):
            self.plan(policy={**POLICY, "execution_enabled": True})
        self.assertFalse(self.state.exists())

    def test_unknown_pending_or_denied_task_never_routes_to_claude(self):
        for status in ("pending", "denied"):
            self.assertEqual(self.plan(self.hard(authorization=status))["route"], "stop")
        for status in ("pending", "refused"):
            self.assertEqual(self.plan(self.hard(safety_status=status))["route"], "stop")

    def test_unavailable_classifier_falls_back_to_openai(self):
        for status in ("unknown", "timeout", "unavailable", "error"):
            with self.subTest(status=status):
                result = self.plan(self.hard(explicit_fable_exception=True), fixture={"status": status, "recommendation": "fable"})
                self.assertEqual(result["route"], "codex")
                self.assertEqual(result["reason"], "classifier_unavailable_use_openai")

    def test_invalid_classifier_output_cannot_choose_models_or_endpoints(self):
        for fixture in ("bad JSON", {}, {"status": "ok", "recommendation": "fable", "base_url": "https://invalid.test"},
                        {"status": "ok", "recommendation": "arbitrary-model"}):
            self.assertEqual(self.plan(self.hard(), fixture=fixture)["route"], "codex")

    def test_classifier_cannot_create_an_escalation(self):
        self.assertEqual(self.plan(fixture={"status": "ok", "recommendation": "fable"})["route"], "codex")
        self.assertEqual(self.plan(self.hard(), fixture={"status": "ok", "recommendation": "fable"})["route"], "codex")

    def test_classifier_can_confirm_but_not_override_the_local_gate(self):
        self.assertEqual(self.plan(self.hard(), fixture={"status": "ok", "recommendation": "opus"})["route"], "opus")
        self.assertEqual(self.plan(self.hard(authorization="denied"), fixture={"status": "ok", "recommendation": "opus"})["route"], "stop")

    def test_auth_modes_never_silently_switch(self):
        subscription = self.plan(self.hard(estimated_cost_cents=99999))
        self.assertEqual(subscription["auth_mode"], "claude_subscription")
        self.assertEqual(subscription["cost_guard"], "live_subscription_check_required")
        self.assertEqual(subscription["reserved_cents"], 0)
        api = self.plan(self.hard(estimated_cost_cents=25), self.api())
        self.assertEqual(api["auth_mode"], "anthropic_api")
        self.assertEqual(api["reserved_cents"], 25)
        self.assertFalse(api["ready_to_execute"])

    def test_default_zero_api_budget_blocks_paid_route(self):
        result = self.plan(self.hard(estimated_cost_cents=1), self.api(per_call_limit_cents=0, daily_limit_cents=0, monthly_limit_cents=0))
        self.assertEqual((result["route"], result["candidate_route"]), ("codex", "opus"))
        self.assertEqual(result["reason"], "api_budget_guard")

    def test_per_call_budget_and_zero_or_unknown_quote_block_api(self):
        for quote in (0, 51):
            result = self.plan(self.hard(estimated_cost_cents=quote), self.api())
            self.assertEqual(result["reason"], "api_budget_guard")
            self.assertEqual(result["reserved_cents"], 0)

    def test_daily_budget_is_aggregate_and_includes_fable(self):
        policy = self.api(daily_limit_cents=75)
        self.assertEqual(self.plan(self.hard(estimated_cost_cents=50), policy)["route"], "opus")
        result = self.plan(self.hard(estimated_cost_cents=26, explicit_fable_exception=True), policy)
        self.assertEqual(result["reason"], "api_budget_guard")

    def test_monthly_budget_survives_day_boundary(self):
        policy = self.api(monthly_limit_cents=75)
        self.plan(self.hard(estimated_cost_cents=50), policy)
        result = ROUTER.prepare(policy, self.hard(estimated_cost_cents=26), self.state,
                                now=datetime(2026, 10, 24, tzinfo=timezone.utc))
        self.assertEqual(result["reason"], "api_budget_guard")

    def test_new_month_does_not_consume_previous_month_budget(self):
        policy = self.api(monthly_limit_cents=50)
        self.plan(self.hard(estimated_cost_cents=50), policy)
        result = ROUTER.prepare(policy, self.hard(estimated_cost_cents=50), self.state,
                                now=datetime(2026, 11, 1, tzinfo=timezone.utc))
        self.assertEqual(result["route"], "opus")

    def test_no_float_bool_negative_or_overflow_budget(self):
        for value in (-1, 1.5, True, "50", 100000001):
            with self.subTest(value=value), self.assertRaises(ROUTER.Blocked):
                self.plan(policy=self.api(daily_limit_cents=value))

    def test_duplicate_id_is_idempotent_and_reserves_once(self):
        task, policy = self.hard(estimated_cost_cents=25), self.api()
        first, second = self.plan(task, policy), self.plan(task, policy)
        self.assertFalse(first["deduplicated"])
        self.assertTrue(second["deduplicated"])
        records = json.loads((self.state / "proposals.json").read_text())["records"]
        self.assertEqual(len(records), 1)
        self.assertEqual(sum(x["reserved_cents"] for x in records.values()), 25)

    def test_changed_task_policy_or_classifier_cannot_reuse_id(self):
        self.plan()
        changes = [({**TASK, "explicit_fable_exception": True}, POLICY, None),
                   (TASK, {**POLICY, "timeout_ms": 500}, None),
                   (TASK, POLICY, {"status": "ok", "recommendation": "codex"})]
        for task, policy, fixture in changes:
            with self.assertRaises(ROUTER.Blocked):
                self.plan(task, policy, fixture)

    def test_content_paths_keys_and_arbitrary_text_are_excluded(self):
        secret = "SYNTHETIC_SECRET_NOT_A_REAL_CREDENTIAL"
        for key in ("context", "api_key", "prompt", "code", "path", "base_url", "notes"):
            with self.subTest(key=key), self.assertRaises(ROUTER.Blocked):
                self.plan({**TASK, key: secret})
        self.assertFalse(self.state.exists())
        features = ROUTER.classifier_features(TASK)
        self.assertEqual(set(features), {"distinct_failed_hypotheses", "important_independent_review", "explicit_fable_exception"})
        self.assertNotIn("task_id", features)

    def test_secret_like_task_identifier_is_rejected(self):
        with self.assertRaises(ROUTER.Blocked):
            self.plan({**TASK, "task_id": "sk-synthetic-not-a-real-key"})

    def test_invalid_boolean_or_count_is_not_a_gate(self):
        for changes in ({"non_confidential": "true"}, {"distinct_failed_hypotheses": True},
                        {"distinct_failed_hypotheses": -1}, {"important_independent_review": 1}):
            with self.assertRaises(ROUTER.Blocked):
                self.plan({**TASK, **changes})

    def test_deadline_expiry_before_reservation(self):
        ticks = iter([0, 2])
        with self.assertRaises(ROUTER.Blocked):
            self.plan(clock=lambda: next(ticks))
        self.assertFalse(self.state.exists())

    def test_deadline_expiry_after_lock_does_not_reserve(self):
        ticks = iter([0, 0, 2])
        with self.assertRaises(ROUTER.Blocked):
            self.plan(clock=lambda: next(ticks))
        self.assertFalse((self.state / "proposals.json").exists())

    def test_lock_contention_is_nonblocking_and_never_retries(self):
        with ROUTER.state_lock(self.state):
            with self.assertRaises(ROUTER.Blocked):
                self.plan()

    def test_concurrent_same_id_creates_at_most_one_reservation(self):
        self.state.mkdir(mode=0o700)
        task, policy = self.hard(estimated_cost_cents=25), self.api()
        def attempt(_):
            try:
                return self.plan(task, policy)["deduplicated"]
            except ROUTER.Blocked:
                return "busy"
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(16)))
        self.assertEqual(outcomes.count(False), 1)
        records = json.loads((self.state / "proposals.json").read_text())["records"]
        self.assertEqual(sum(x["reserved_cents"] for x in records.values()), 25)

    def test_concurrent_different_ids_cannot_oversubscribe_budget(self):
        self.state.mkdir(mode=0o700)
        policy = self.api(daily_limit_cents=50)
        def attempt(_):
            try:
                return self.plan(self.hard(estimated_cost_cents=50), policy)["route"]
            except ROUTER.Blocked:
                return "busy"
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(attempt, range(16)))
        self.assertEqual(results.count("opus"), 1)
        records = json.loads((self.state / "proposals.json").read_text())["records"]
        self.assertEqual(sum(x["reserved_cents"] for x in records.values()), 50)

    def test_symlinks_and_world_readable_state_are_rejected(self):
        target = self.root / "target"
        target.mkdir(mode=0o700)
        self.state.symlink_to(target)
        with self.assertRaises(ROUTER.Blocked):
            self.plan()
        self.state.unlink()
        self.state.mkdir(mode=0o755)
        self.state.chmod(0o755)
        with self.assertRaises(ROUTER.Blocked):
            self.plan()

    def test_corrupt_ledger_is_not_reset(self):
        self.state.mkdir(mode=0o700)
        ledger = self.state / "proposals.json"
        ledger.write_text('{"version": 1, "records": {"bad": {}}}')
        before = ledger.read_bytes()
        with self.assertRaises(ROUTER.Blocked):
            self.plan()
        self.assertEqual(ledger.read_bytes(), before)

    def test_duplicate_json_keys_symlink_fifo_and_large_input_rejected(self):
        path = self.root / "input.json"
        path.write_text('{"execution_enabled":false,"execution_enabled":true}')
        with self.assertRaises(ROUTER.Blocked):
            ROUTER.read_json(path)
        path.unlink()
        path.symlink_to(ROOT / "docs/model-routing-policy.example.json")
        with self.assertRaises(ROUTER.Blocked):
            ROUTER.read_json(path)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(ROUTER.Blocked):
            ROUTER.read_json(path)
        path.unlink()
        path.write_bytes(b" " * 65537)
        with self.assertRaises(ROUTER.Blocked):
            ROUTER.read_json(path)

    def test_cli_errors_never_echo_unknown_fields_or_values(self):
        path = self.root / "input.json"
        path.write_text(json.dumps({**TASK, "secret": "SYNTHETIC_PRIVATE_TEXT"}))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = ROUTER.main(["--policy", str(ROOT / "docs/model-routing-policy.example.json"),
                                "--task", str(path), "--state-dir", str(self.state)])
        self.assertEqual(code, 78)
        self.assertNotIn("SYNTHETIC_PRIVATE_TEXT", output.getvalue())
        self.assertNotIn("secret", output.getvalue())

    def test_poisoned_cached_output_is_rejected_instead_of_echoed(self):
        self.plan()
        ledger = self.state / "proposals.json"
        data = json.loads(ledger.read_text())
        data["records"][TASK["task_id"]]["decision"]["untrusted_text"] = "SYNTHETIC_PRIVATE_TEXT"
        ledger.write_text(json.dumps(data))
        with self.assertRaises(ROUTER.Blocked):
            self.plan()

    def test_cli_malformed_classifier_fixture_falls_back_without_echoing_it(self):
        task_path = self.root / "task.json"
        task_path.write_text(json.dumps(self.hard()))
        fixture = self.root / "fixture.json"
        fixture.write_text('invalid JSON SYNTHETIC_PRIVATE_TEXT')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = ROUTER.main(["--policy", str(ROOT / "docs/model-routing-policy.example.json"),
                                "--task", str(task_path), "--state-dir", str(self.state),
                                "--classifier-fixture", str(fixture)])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["route"], "codex")
        self.assertNotIn('SYNTHETIC_PRIVATE_TEXT', output.getvalue())

    def test_cli_lock_conflict_reports_the_stop_without_retry(self):
        output = io.StringIO()
        with ROUTER.state_lock(self.state), contextlib.redirect_stdout(output):
            code = ROUTER.main(["--policy", str(ROOT / "docs/model-routing-policy.example.json"),
                                "--task", str(ROOT / "tests/fixtures/model-route-task.json"),
                                "--state-dir", str(self.state)])
        self.assertEqual(code, 78)
        self.assertIn('no retry attempted', json.loads(output.getvalue())["reason"])

    def test_proposal_state_is_private_and_contains_no_original_task_text(self):
        self.plan()
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        ledger = self.state / "proposals.json"
        self.assertEqual(ledger.stat().st_mode & 0o777, 0o600)
        data = json.loads(ledger.read_text())
        self.assertEqual(set(data['records'][TASK['task_id']]),
                         {'fingerprint', 'day', 'month', 'reserved_cents', 'decision'})


if __name__ == "__main__":
    unittest.main()
