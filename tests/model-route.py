"""Runtime regression tests use synthetic context and fake native processes only."""
from datetime import datetime
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile
import tomllib
import unittest
from unittest.mock import MagicMock, patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
LOADER = SourceFileLoader("model_route", str(ROOT / "home/dot_local/bin/private_executable_model-route"))
R = module_from_spec(spec_from_loader(LOADER.name, LOADER))
LOADER.exec_module(R)
LOADER = SourceFileLoader("provider_probe", str(ROOT / "home/dot_local/lib/model-routing/provider_probe.py"))
PROBE = module_from_spec(spec_from_loader(LOADER.name, LOADER))
LOADER.exec_module(PROBE)
TASK = json.loads((ROOT / "tests/fixtures/model-route-task.json").read_text())
CONTEXT = json.loads((ROOT / "tests/fixtures/model-route-context.json").read_text())
CONFIG = json.loads((ROOT / "home/private_dot_config/model-routing/private_policy.json").read_text())
NATIVE = {"model": "gpt-6.1-sol", "model_reasoning_effort": "high", "mcp_servers": {}, "plugins": {}}
SUCCESS = '\n'.join(json.dumps(x) for x in [
    {"type": "item.completed", "item": {"type": "agent_message", "text": "OK"}},
    {"type": "turn.completed", "usage": {"input_tokens": 1, "output_tokens": 1}},
])
ORIGINAL_CODEX_AUTH = R.codex_auth
SOL, TERRA = 'gpt-6.1-sol', 'gpt-6.1-terra'
DOWNSHIFT = 'general_codex_window_used_percent_above_50'


def catalog_entry(model, efforts, hidden=False):
    return {'id': model, 'model': model, 'displayName': model, 'description': 'synthetic',
            'hidden': hidden, 'isDefault': False, 'defaultReasoningEffort': efforts[0],
            'supportedReasoningEfforts': [{'reasoningEffort': e, 'description': 'synthetic'} for e in efforts]}


CATALOG = {'data': [catalog_entry(SOL, ['low', 'medium', 'high', 'xhigh', 'max', 'ultra']),
                    catalog_entry(TERRA, ['low', 'medium', 'high', 'xhigh'])], 'complete': True}


def window(used, mins=10080, resets=1793867758):
    return {'usedPercent': used, 'windowDurationMins': mins, 'resetsAt': resets}


def limits(primary=window(7), secondary=None, bucket='codex', by_id=True):
    snapshot = {'limitId': bucket, 'limitName': None, 'primary': primary, 'secondary': secondary,
                'planType': 'pro', 'credits': {'hasCredits': False, 'unlimited': False, 'balance': '0'}}
    response = {'accountId': 'SYNTHETIC_ACCOUNT_ID', 'ordinaryUsageAllowed': True, 'rateLimits': snapshot}
    if by_id:
        response['rateLimitsByLimitId'] = {bucket: snapshot}
    return response


def effective(model, effort, **extra):
    return {'config': {'model': model, 'model_reasoning_effort': effort, 'model_provider': 'openai',
                       'forced_login_method': 'chatgpt', 'forced_chatgpt_workspace_id': 'SYNTHETIC_WORKSPACE_ID',
                       'developer_instructions': 'SYNTHETIC_PRIVATE_INSTRUCTIONS', **extra},
            'origins': {'model': {'name': {'type': 'sessionFlags'}, 'version': 'SYNTHETIC_ORIGIN'}}}


class Runtime(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.state = self.root / "state"
        self.context = self.root / "context.json"
        self.context.write_text(json.dumps(CONTEXT))
        self.native_auth = patch.object(R, "codex_auth", return_value=(self.root / "fake-codex", NATIVE))
        self.native_auth.start()
        self.addCleanup(self.native_auth.stop)
        p = patch.object(R, 'disabled_skill_paths', return_value=[])
        p.start()
        self.addCleanup(p.stop)
        for target in ("socket.socket", "socket.create_connection"):
            p = patch(target, side_effect=AssertionError("No network in tests"))
            p.start()
            self.addCleanup(p.stop)

    def ask(self, task=None):
        return R.ask(CONFIG, task or TASK, self.context, self.state)

    def fake_process(self, output=SUCCESS, exit_code=0, timeout=False):
        proc = SimpleNamespace(pid=999999, returncode=exit_code)
        calls = []
        def communicate(*args, **kwargs):
            calls.append((args, kwargs))
            if timeout and len(calls) == 1:
                proc.returncode = -9
                raise subprocess.TimeoutExpired('synthetic', 1)
            return output, 'SYNTHETIC_SECRET_IN_STDERR'
        proc.communicate = communicate
        return proc

    def test_openai_request_uses_subscription_and_no_api_keys(self):
        with patch.object(R.subprocess, 'Popen', return_value=self.fake_process()) as popen:
            result = self.ask()
        self.assertEqual(result['state'], 'completed')
        self.assertEqual(result['response'], 'OK')
        self.assertEqual(result['executed_route'], 'codex_subscription')
        self.assertEqual(result['paid_api_calls'], 0)
        command = popen.call_args.args[0]
        self.assertIn('forced_login_method="chatgpt"', command)
        self.assertIn('features.shell_tool=false', command)
        self.assertIn('features.apps=false', command)
        self.assertIn('features.hooks=false', command)
        self.assertIn('memories.use_memories=false', command)
        self.assertIn('project_doc_max_bytes=0', command)
        self.assertIn('skills.config=[]', command)
        self.assertIn('model_provider="openai"', command)
        self.assertIn('--ephemeral', command)
        self.assertIn('read-only', command)
        self.assertNotIn('--model', command)
        self.assertIsNone(result['reported_model'])

    def test_api_routes_fail_closed_and_openai_is_explicit_fallback(self):
        for extra, candidate in [({'distinct_failed_hypotheses': 2}, 'opus'),
                                 ({'explicit_fable_exception': True}, 'fable')]:
            self.state = self.root / candidate
            with patch.object(R.subprocess, 'Popen', return_value=self.fake_process()) as popen:
                result = self.ask({**TASK, **extra})
            self.assertEqual(result['requested_route'], candidate)
            self.assertEqual(result['executed_route'], 'codex_subscription')
            self.assertEqual(result['fallback_reason'], 'provider_budget_unverified')
            self.assertEqual(result['paid_api_calls'], 0)
            self.assertNotIn('op-agent', str(popen.call_args))

    def test_refusal_and_pending_approval_do_not_fallback(self):
        for task in [{**TASK, 'authorization': 'denied'}, {**TASK, 'safety_status': 'refused'}]:
            with patch.object(R, 'invoke_text') as invoke, self.assertRaises(R.P.Blocked):
                self.ask(task)
            invoke.assert_not_called()

    def test_context_requires_explicit_review_and_scope(self):
        for envelope in [{**CONTEXT, 'reviewed_no_secrets_or_pii': False},
                         {**CONTEXT, 'scope': 'personal_private'}, {**CONTEXT, 'extra': 'text'}]:
            self.context.write_text(json.dumps(envelope))
            with patch.object(R, 'invoke_text') as invoke, self.assertRaises(R.P.Blocked):
                self.ask()
            invoke.assert_not_called()

    def test_credentials_are_rejected_before_transmission(self):
        for secret in ['sk-ant-api01-SYNTHETIC_NOT_REAL', 'op://Agents/synthetic/password',
                       'Bearer SYNTHETIC_TOKEN_NOT_REAL', 'api_key="SYNTHETIC_KEY_NOT_REAL"',
                       '-----BEGIN PRIVATE KEY-----\nSYNTHETIC\n-----END PRIVATE KEY-----']:  # gitleaks:allow (synthetic test value)
            self.context.write_text(json.dumps({**CONTEXT, 'text': secret}))
            with patch.object(R, 'invoke_text') as invoke, self.assertRaises(R.P.Blocked):
                self.ask()
            invoke.assert_not_called()

    def test_email_phone_and_home_path_are_removed_from_payload(self):
        value = R.sanitize_text('Email person@example.test phone 090-1234-5678 path /home/synthetic/source.py')
        self.assertNotIn('person@example.test', value)
        self.assertNotIn('090-1234-5678', value)
        self.assertNotIn('/home/synthetic', value)

    def test_no_context_or_model_response_is_persisted(self):
        with patch.object(R, 'invoke_text', return_value={'state': 'completed', 'response': 'SYNTHETIC_MODEL_ANSWER', 'exit_code': 0}):
            self.ask()
        stored = ''.join(p.read_text() for p in self.state.iterdir() if p.is_file())
        self.assertNotIn(CONTEXT['text'], stored)
        self.assertNotIn('SYNTHETIC_MODEL_ANSWER', stored)

    def test_duplicate_request_never_executes_again(self):
        with patch.object(R, 'invoke_text', return_value={'state': 'completed', 'response': 'OK'}) as invoke:
            self.ask()
            with self.assertRaises(R.P.Blocked):
                self.ask()
            self.assertEqual(invoke.call_count, 1)

    def test_changed_context_cannot_reuse_request_identifier(self):
        with patch.object(R, 'invoke_text', return_value={'state': 'completed', 'response': 'OK'}) as invoke:
            self.ask()
            self.context.write_text(json.dumps({**CONTEXT, 'text': 'Another synthetic question'}))
            with self.assertRaises(R.P.Blocked):
                self.ask()
            self.assertEqual(invoke.call_count, 1)

    def test_timeout_kills_process_and_blocks_replay(self):
        with patch.object(R.subprocess, 'Popen', return_value=self.fake_process(timeout=True)) as popen, \
                patch.object(R.os, 'killpg') as kill:
            result = self.ask()
            self.assertEqual(result['state'], 'uncertain')
            self.assertEqual(result['reason'], 'timeout_no_replay')
            kill.assert_called_once()
            with self.assertRaises(R.P.Blocked):
                self.ask()
            self.assertEqual(popen.call_count, 1)

    def test_process_exception_leaves_uncertain_reservation(self):
        with patch.object(R, 'invoke_text', side_effect=OSError('synthetic')) as invoke:
            with self.assertRaises(R.P.Blocked):
                self.ask()
            with self.assertRaises(R.P.Blocked):
                self.ask()
            self.assertEqual(invoke.call_count, 1)
        data = json.loads((self.state / 'executions.json').read_text())
        self.assertEqual(data[TASK['task_id']]['state'], 'uncertain')

    def test_nonzero_failed_turn_tool_use_and_unknown_output_reject_success(self):
        cases = [(SUCCESS, 1), ('not JSON', 0),
                 (SUCCESS + '\n' + json.dumps({'type': 'turn.failed'}), 0),
                 (SUCCESS + '\n' + json.dumps({'type': 'item.started', 'item': {'type': 'mcp_tool_call'}}), 0)]
        for output, code in cases:
            with patch.object(R.subprocess, 'Popen', return_value=self.fake_process(output, code)):
                result = R.invoke_text(self.root / 'fake', NATIVE, 'synthetic', 1)
            self.assertNotEqual(result['state'], 'completed')
            self.assertNotIn('SYNTHETIC_SECRET_IN_STDERR', json.dumps(result))

    def test_model_response_credentials_are_not_returned(self):
        out = SUCCESS.replace('OK', 'sk-ant-api01-SYNTHETIC_NOT_REAL')
        with patch.object(R.subprocess, 'Popen', return_value=self.fake_process(out)):
            result = R.invoke_text(self.root / 'fake', NATIVE, 'synthetic', 1)
        self.assertEqual(result['state'], 'failed')
        self.assertIsNone(result['response'])

    def test_cli_identifiers_are_used_without_creating_quoted_phantom_servers(self):
        config = {**NATIVE, 'mcp_servers': {'server-with-dash': {}}, 'plugins': {'name@publisher': {}}}
        command = R.text_command(self.root / 'fake', config)
        self.assertIn('mcp_servers.server-with-dash.enabled=false', command)
        self.assertIn('plugins.name@publisher.enabled=false', command)
        with self.assertRaises(R.P.Blocked):
            R.text_command(self.root / 'fake', {**NATIVE, 'mcp_servers': {'server.with.dots': {}}})

    def test_default_entry_keeps_home_model_and_effort_as_command_overrides(self):
        command = R.base_command(self.root / 'fake', NATIVE)
        self.assertIn('model="gpt-6.1-sol"', command)
        self.assertIn('model_reasoning_effort="high"', command)
        self.assertIn('model_provider="openai"', command)

    def test_project_and_ancestor_endpoint_overrides_are_rejected(self):
        folder = self.root / '.codex'
        folder.mkdir()
        nested = self.root / 'project/src'
        nested.mkdir(parents=True)
        for text in ['chatgpt_base_url="https://synthetic.invalid"',
                     '[profiles.custom]\nopenai_base_url="https://synthetic.invalid"',
                     '[model_providers.openai]\nbase_url="https://synthetic.invalid"',
                     'forced_login_method="api"']:
            (folder / 'config.toml').write_text(text)
            with self.assertRaises(R.P.Blocked):
                R.reject_project_routing(nested)

    def test_project_model_and_effort_settings_cannot_change_pinned_defaults(self):
        folder = self.root / '.codex'
        folder.mkdir()
        (folder / 'config.toml').write_text('model="synthetic"\nmodel_reasoning_effort="low"')
        R.reject_project_routing(self.root)
        command = R.base_command(self.root / 'fake', NATIVE)
        self.assertIn('model="gpt-6.1-sol"', command)
        self.assertIn('model_reasoning_effort="high"', command)

    def test_symlink_or_invalid_project_config_blocks_before_native_exec(self):
        folder = self.root / '.codex'
        folder.mkdir()
        path = folder / 'config.toml'
        path.symlink_to(self.context)
        with self.assertRaises(R.P.Blocked):
            R.reject_project_routing(self.root)
        path.unlink()
        path.write_text('INVALID_TOML')
        with patch.object(R.Path, 'cwd', return_value=self.root), \
                patch.object(R, 'runtime_config', return_value=CONFIG), \
                patch.object(R.os, 'execv') as native_exec, patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(R.main(['start']), 78)
        native_exec.assert_not_called()

    def test_home_profile_cannot_override_official_endpoint(self):
        folder = self.root / '.codex'
        folder.mkdir()
        (folder / 'config.toml').write_text('model="gpt-6.1-sol"\nmodel_reasoning_effort="high"\n'
                                          '[profiles.custom]\nchatgpt_base_url="https://synthetic.invalid"')
        with patch.object(R.Path, 'home', return_value=self.root), self.assertRaises(R.P.Blocked):
            R.codex_config()

    def test_native_cli_overrides_are_valid_toml_even_with_skill_paths(self):
        with patch.object(R, 'disabled_skill_paths', return_value=[{'path': '/tmp/synthetic/skill', 'enabled': False}]):
            command = R.text_command(self.root / 'fake', NATIVE)
        for n, part in enumerate(command):
            if part == '-c':
                # Codex parses the RHS as TOML and splits the LHS on dots;
                # quoted table names would become literal phantom identifiers.
                tomllib.loads('value=' + command[n+1].split('=',1)[1])

    def test_injected_provider_variables_block_subscription_path(self):
        for name in ['ANTHROPIC_API_KEY', 'TYPESAFE_API_KEY', 'OPENAI_API_KEY', 'CODEX_HOME', 'OP_SERVICE_ACCOUNT_TOKEN']:
            with patch.dict(os.environ, {name: 'SYNTHETIC_NOT_REAL'}), self.assertRaises(R.P.Blocked):
                R.no_auth_overrides()

    def test_expanded_or_force_enabled_policy_rejected(self):
        folder = self.root / '.config/model-routing'
        folder.mkdir(parents=True)
        for config in [{**CONFIG, 'monthly_api_limit_cents': 2001},
                       {**CONFIG, 'per_request_target_cents': 501}, {**CONFIG, 'api_enabled': True}]:
            (folder / 'policy.json').write_text(json.dumps(config))
            with patch.object(R.Path, 'home', return_value=self.root), self.assertRaises(R.P.Blocked):
                R.runtime_config()

    def test_diagnostic_filter_drops_remote_text_and_never_accepts_verified_flag(self):
        row = {'provider': 'typesafe', 'paid_requests': 0, 'http_status': 200,
               'provider_cap_verified': True, 'raw_key': 'SYNTHETIC_NOT_REAL',
               'model_ids': ['jev-1.14', 'SYNTHETIC_NOT_REAL']}
        result = R.clean_provider_report(row, 'typesafe')
        self.assertNotIn('SYNTHETIC_NOT_REAL', json.dumps(result))
        self.assertNotIn('provider_cap_verified', result)

    def test_doctor_without_provider_flag_does_not_fetch_keys(self):
        with patch.object(R.subprocess, 'run', side_effect=AssertionError('No secret resolver')):
            result = R.doctor(False)
        self.assertFalse(result['paid_api_paths_ready'])


class Workflow(unittest.TestCase):
    """Synthetic app-server reads; the selection logic never sees a live account."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.binary = self.root / 'fake-codex'
        self.calls = []
        self.rate_limits, self.catalog, self.config = limits(), CATALOG, effective
        for target, kwargs in [('codex_auth', {'return_value': (self.binary, NATIVE)}),
                               ('reject_project_routing', {}), ('app_server_read', {'side_effect': self.fake_read}),
                               ('runtime_config', {'return_value': CONFIG})]:
            p = patch.object(R, target, **kwargs)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(R.Path, 'home', return_value=self.root)
        p.start()
        self.addCleanup(p.stop)
        for target in ('socket.socket', 'socket.create_connection'):
            p = patch(target, side_effect=AssertionError('No network in tests'))
            p.start()
            self.addCleanup(p.stop)

    def fake_read(self, binary, config, model, effort, reads):
        self.calls.append((model, effort, tuple(reads)))
        source = {'rate_limits': lambda: self.rate_limits, 'models': lambda: self.catalog,
                  'config': lambda: self.config(model, effort)}
        return {name: source[name]() for name in reads}

    def check(self, workflow):
        self.calls = []
        return R.check_workflow(workflow)[0]

    def test_deep_review_keeps_max_at_exactly_50(self):
        for primary, secondary in [(window(50), None), (window(7), window(50, 300))]:
            self.rate_limits = limits(primary, secondary)
            record = self.check('deep-review')
            self.assertEqual((record['configured_model'], record['configured_effort']), (SOL, 'max'))
            self.assertEqual((record['effective_model'], record['effective_effort']), (SOL, 'max'))
            self.assertEqual(record['requested_effort'], 'max')
            self.assertIsNone(record['downshift_reason'])
            self.assertEqual(self.calls, [(SOL, 'max', ('rate_limits', 'models', 'config'))])

    def test_deep_review_downshifts_when_any_window_exceeds_50_and_rereads_config(self):
        for primary, secondary in [(window(51), None), (window(7), window(51, 300)), (window(51), window(90, 300))]:
            self.rate_limits = limits(primary, secondary)
            record = self.check('deep-review')
            self.assertEqual((record['configured_effort'], record['effective_effort']), ('xhigh', 'xhigh'))
            self.assertEqual(record['requested_effort'], 'max')
            self.assertEqual(record['downshift_reason'], DOWNSHIFT)
            self.assertEqual(self.calls, [(SOL, 'max', ('rate_limits', 'models', 'config')),
                                          (SOL, 'xhigh', ('config',))])

    def test_weekly_primary_without_secondary_reports_exact_used_and_remaining(self):
        record = self.check('deep-review')
        self.assertEqual(record['quota'], {
            'state': 'known', 'bucket': 'codex', 'secondary': None,
            'primary': {'used_percent': 7, 'remaining_percent': 93,
                        'window_duration_mins': 10080, 'resets_at': 1793867758}})
        self.assertEqual(record['tool_version'], 'codex-cli 0.166.0')
        self.assertIsNotNone(datetime.fromisoformat(record['checked_at']).tzinfo)
        self.assertEqual((record['model_started'], record['thread_started'], record['paid_api_calls']),
                         (False, False, 0))
        # The duration is reported, never relabelled as a five-hour window.
        self.assertNotIn('five', json.dumps(record))

    def test_legacy_single_bucket_view_counts_only_for_general_codex(self):
        self.rate_limits = limits(window(60), by_id=False)
        self.assertEqual(self.check('deep-review')['configured_effort'], 'xhigh')
        self.rate_limits = limits(window(60), bucket='codex_other', by_id=False)
        self.assertEqual(self.check('review')['quota']['state'], 'unknown')

    def test_deep_review_blocks_unknown_wrong_missing_or_malformed_quota(self):
        other = limits(window(10), bucket='codex_other')
        cases = [None, {'rateLimits': {}}, other, limits(window(10), bucket='codex_other', by_id=False),
                 {**limits(), 'rateLimitsByLimitId': {'codex_other': other['rateLimits']}},
                 {**limits(), 'rateLimitsByLimitId': {'codex': {**other['rateLimits'], 'limitId': 'codex_other'}}},
                 {**limits(), 'rateLimitsByLimitId': 'SYNTHETIC'},
                 limits(primary=None, secondary=None),
                 limits(primary={'usedPercent': 7, 'windowDurationMins': '10080', 'resetsAt': 1})]
        cases += [limits(window(value)) for value in ('7', 7.5, -1, 101, True, None)]
        cases += [limits(window(7), window('51', 300))]
        for case in cases:
            self.rate_limits = case
            with self.assertRaises(R.P.Blocked):
                self.check('deep-review')
            self.assertEqual(len(self.calls), 1)

    def test_other_workflows_report_unknown_quota_without_guessing(self):
        self.rate_limits = None
        for workflow, model, effort in [('review', SOL, 'xhigh'), ('code-efficient', TERRA, 'xhigh'),
                                        ('routine', TERRA, 'low')]:
            record = self.check(workflow)
            self.assertEqual(record['quota'], {'state': 'unknown', 'bucket': 'codex',
                                               'primary': None, 'secondary': None})
            self.assertIsNone(record['ordinary_usage_allowed'])
            self.assertEqual((record['configured_model'], record['configured_effort']), (model, effort))

    def test_xhigh_and_low_workflows_are_never_raised_and_nothing_is_persisted(self):
        for used in (0, 50, 51, 100):
            self.rate_limits = limits(window(used))
            for workflow, effort in [('review', 'xhigh'), ('code-efficient', 'xhigh'), ('routine', 'low')]:
                record = self.check(workflow)
                self.assertEqual((record['requested_effort'], record['configured_effort']), (effort, effort))
                self.assertIsNone(record['downshift_reason'])
                self.assertTrue(all(call[1] == effort for call in self.calls))
        # No state file exists that could later restore or raise a selection.
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unsupported_model_or_effort_blocks(self):
        cases = [('code-efficient', {'data': [catalog_entry(SOL, ['xhigh'])], 'complete': True}),
                 ('code-efficient', {'data': [catalog_entry(SOL, ['xhigh'])], 'complete': False}),
                 ('routine', {'data': [catalog_entry(TERRA, ['medium', 'high', 'xhigh'])], 'complete': True}),
                 ('code-efficient', {'data': [catalog_entry(TERRA, ['low', 'xhigh'], hidden=True)], 'complete': True}),
                 ('deep-review', {'data': [catalog_entry(SOL, ['low', 'high', 'xhigh'])], 'complete': True}),
                 ('review', None)]
        for workflow, catalog in cases:
            self.catalog = catalog
            with self.assertRaises(R.P.Blocked):
                self.check(workflow)

    def test_effective_config_mismatch_blocks(self):
        for config in [lambda m, e: effective(SOL, e), lambda m, e: effective(m, 'high'),
                       lambda m, e: effective(m, e, model_provider='synthetic'),
                       lambda m, e: effective(m, e, forced_login_method='api'),
                       lambda m, e: None, lambda m, e: {'config': 'SYNTHETIC'}]:
            self.config = config
            with self.assertRaises(R.P.Blocked):
                self.check('code-efficient')
        # A downshift is not accepted from the earlier max read.
        self.rate_limits, self.config = limits(window(51)), lambda m, e: effective(m, 'max')
        with self.assertRaises(R.P.Blocked):
            self.check('deep-review')

    def test_backend_disallowing_ordinary_usage_blocks(self):
        self.rate_limits = {**limits(), 'ordinaryUsageAllowed': False}
        with self.assertRaises(R.P.Blocked):
            self.check('routine')

    def test_check_output_omits_identifiers_and_raw_config(self):
        with patch('sys.stdout', new_callable=io.StringIO) as out:
            self.assertEqual(R.main(['check', '--workflow', 'code-efficient']), 0)
        text = out.getvalue()
        for secret in ('SYNTHETIC_ACCOUNT_ID', 'SYNTHETIC_WORKSPACE_ID', 'SYNTHETIC_PRIVATE_INSTRUCTIONS',
                       'SYNTHETIC_ORIGIN', 'origins', 'planType', 'credits', 'developer_instructions'):
            self.assertNotIn(secret, text)
        self.assertEqual(set(json.loads(text)), {
            'state', 'workflow', 'tool_version', 'configured_model', 'configured_effort', 'requested_effort',
            'effective_model', 'effective_effort', 'downshift_reason', 'quota', 'ordinary_usage_allowed',
            'checked_at', 'model_started', 'thread_started', 'paid_api_calls'})

    def test_default_start_is_unchanged_and_reads_no_quota(self):
        for argv in ([], ['start']):
            with patch.object(R, 'app_server_read', side_effect=AssertionError('No quota dependency')), \
                    patch.object(R.subprocess, 'Popen', side_effect=AssertionError('No wrapper process')), \
                    patch.object(R.os, 'execv') as native_exec:
                R.main(argv)
            native_exec.assert_called_once_with(str(self.binary), R.base_command(self.binary, NATIVE))
        command = R.base_command(self.binary, NATIVE)
        self.assertEqual(command[:2], [str(self.binary), '--no-daemon'])
        self.assertIn('model="gpt-6.1-sol"', command)
        self.assertIn('model_reasoning_effort="high"', command)

    def test_workflow_start_records_then_runs_native_with_selected_pins(self):
        self.rate_limits = limits(window(51))
        proc = MagicMock()
        proc.__enter__.return_value = proc
        proc.wait.return_value = 3
        err = io.StringIO()
        def popen(command, **kwargs):
            self.assertIn('"workflow_start"', err.getvalue())  # Start record precedes the native process.
            return proc
        with patch('sys.stderr', err), patch('sys.stdout', new_callable=io.StringIO) as out, \
                patch.object(R.subprocess, 'Popen', side_effect=popen) as native, \
                patch.object(R.os, 'execv') as native_exec:
            self.assertEqual(R.main(['start', '--workflow', 'deep-review']), 3)
        native_exec.assert_not_called()
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(native.call_args.args[0], R.base_command(
            self.binary, {**NATIVE, 'model': SOL, 'model_reasoning_effort': 'xhigh'}))
        self.assertEqual(native.call_args.kwargs, {})  # Terminal, environment and cwd are inherited.
        start, finish = [json.loads(line) for line in err.getvalue().splitlines()]
        self.assertEqual((start['record'], start['model'], start['effort'], start['requested_effort']),
                         ('workflow_start', SOL, 'xhigh', 'max'))
        self.assertEqual(start['downshift_reason'], DOWNSHIFT)
        self.assertEqual((finish['record'], finish['exit_code'], finish['tests'], finish['rework'],
                          finish['token_usage']), ('workflow_finish', 3, 'unknown', 'unknown', 'unknown'))
        self.assertGreaterEqual(finish['duration_seconds'], 0)
        self.assertEqual(finish['quota_after']['primary']['used_percent'], 51)
        self.assertEqual(self.calls[-1], (SOL, 'xhigh', ('rate_limits',)))
        self.assertNotIn('SYNTHETIC_ACCOUNT_ID', err.getvalue())

    def test_blocked_workflow_start_never_runs_native(self):
        self.rate_limits = None
        with patch('sys.stdout', new_callable=io.StringIO) as out, \
                patch.object(R.subprocess, 'Popen', side_effect=AssertionError('No native start')):
            self.assertEqual(R.main(['start', '--workflow', 'deep-review']), 78)
        self.assertEqual(json.loads(out.getvalue())['state'], 'blocked')

    def test_exact_reviewed_codex_version_guard_is_retained(self):
        self.assertEqual(R.VERSION, 'codex-cli 0.166.0')
        def native(version):
            def run(command, **kwargs):
                text = version if command[1:] == ['--version'] else 'Logged in using ChatGPT'
                return subprocess.CompletedProcess(command, 0, text + '\n', '')
            return run
        with patch.dict(os.environ, {}, clear=True), patch.object(R, 'codex_config', return_value=NATIVE):
            for version in ('codex-cli 0.163.0', 'codex-cli 0.166.1', 'codex-cli 0.166.0-alpha.1',
                            'codex-cli 0.166', 'codex-cli 0.166.*', ''):
                with patch.object(R.subprocess, 'run', side_effect=native(version)), \
                        self.assertRaises(R.P.Blocked):
                    ORIGINAL_CODEX_AUTH()
            with patch.object(R.subprocess, 'run', side_effect=native('codex-cli 0.166.0')):
                self.assertEqual(ORIGINAL_CODEX_AUTH(), (self.root / '.local/bin/codex', NATIVE))


FAKE_APP_SERVER = r'''
import json, sys, time
mode, log = sys.argv[1], sys.argv[2]
print("SYNTHETIC_STDERR_SECRET", file=sys.stderr, flush=True)
def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()
def entry(model, efforts):
    return {"id": model, "model": model, "displayName": model, "description": "synthetic", "hidden": False,
            "isDefault": False, "defaultReasoningEffort": efforts[0],
            "supportedReasoningEfforts": [{"reasoningEffort": e, "description": "synthetic"} for e in efforts]}
for line in sys.stdin:
    message = json.loads(line)
    with open(log, "a") as out:
        out.write(json.dumps(message) + "\n")
    if mode == "silent":
        time.sleep(30)
    if mode == "huge":
        send({"padding": "x" * 4096})
    ident, method = message.get("id"), message.get("method")
    if ident is None:
        continue
    sys.stdout.write("SYNTHETIC non-protocol line\n")
    send({"method": "account/rateLimits/updated", "params": {"accountId": "SYNTHETIC_ACCOUNT_ID"}})
    send({"id": ident + 1000, "result": {"stray": True}})
    if method == "initialize":
        send({"id": ident, "result": {"userAgent": "synthetic"}})
    elif method == "account/rateLimits/read" and mode == "limits_error":
        send({"id": ident, "error": {"code": -32603, "message": "SYNTHETIC_UPSTREAM_ERROR"}})
    elif method == "account/rateLimits/read":
        snapshot = {"limitId": "codex", "secondary": None,
                    "primary": {"usedPercent": 7, "windowDurationMins": 10080, "resetsAt": 1793867758}}
        send({"id": ident, "result": {"accountId": "SYNTHETIC_ACCOUNT_ID", "rateLimits": snapshot,
                                      "rateLimitsByLimitId": {"codex": snapshot}}})
    elif method == "model/list" and message["params"].get("cursor") is None:
        send({"id": ident, "result": {"data": [entry("gpt-6.1-sol", ["xhigh", "max"])],
                                      "nextCursor": "SYNTHETIC_PAGE_2"}})
    elif method == "model/list":
        send({"id": ident, "result": {"data": [entry("gpt-6.1-terra", ["low", "xhigh"])], "nextCursor": None}})
    elif method == "config/read":
        send({"id": ident, "result": {"config": {"model": "gpt-6.1-terra", "model_reasoning_effort": "low"},
                                      "origins": {}}})
    else:
        send({"id": ident, "error": {"code": -32601, "message": "unexpected"}})
'''


class AppServerProtocol(unittest.TestCase):
    """A synthetic stdio server process; never the installed Codex binary."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.script = self.root / 'fake_app_server.py'
        self.script.write_text(FAKE_APP_SERVER)
        self.log = self.root / 'received.jsonl'

    def read(self, mode, command=None):
        command = command or [sys.executable, '-I', '-B', str(self.script), mode, str(self.log)]
        real_popen, self.procs, self.kwargs = subprocess.Popen, [], {}
        def popen(argv, **kwargs):
            self.kwargs = kwargs
            self.procs.append(real_popen(argv, **kwargs))
            return self.procs[-1]
        with patch.object(R, 'app_server_command', return_value=command) as build, \
                patch.object(R.subprocess, 'Popen', side_effect=popen):
            result = R.app_server_read(self.root / 'fake-codex', NATIVE, TERRA, 'low',
                                       ('rate_limits', 'models', 'config'))
        build.assert_called_once_with(self.root / 'fake-codex', NATIVE, TERRA, 'low')
        self.assertTrue(all(proc.returncode is not None for proc in self.procs))  # Child stopped.
        return result

    def received(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_initialize_then_read_only_methods_with_pagination(self):
        result = self.read('normal')
        messages = self.received()
        self.assertEqual([m['method'] for m in messages], [
            'initialize', 'initialized', 'account/rateLimits/read', 'model/list', 'model/list', 'config/read'])
        self.assertEqual(messages[0]['params'], {'clientInfo': R.CLIENT_INFO})
        self.assertNotIn('jsonrpc', messages[0])
        self.assertNotIn('id', messages[1])
        self.assertEqual(messages[2]['params'], {'supportsLunaReserve': False, 'excludeResetCreditDetails': True})
        self.assertNotIn('cursor', messages[3]['params'])
        self.assertEqual(messages[4]['params']['cursor'], 'SYNTHETIC_PAGE_2')
        self.assertIs(messages[5]['params']['includeLayers'], False)
        self.assertEqual([e['model'] for e in result['models']['data']], [SOL, TERRA])
        self.assertTrue(result['models']['complete'])
        self.assertEqual(R.general_quota(result['rate_limits'])['primary']['used_percent'], 7)
        self.assertEqual(result['config']['config']['model'], TERRA)
        self.assertEqual((self.kwargs['stderr'], self.kwargs['start_new_session']), (subprocess.DEVNULL, True))

    def test_error_reply_is_unknown_without_upstream_text(self):
        result = self.read('limits_error')
        self.assertIsNone(result['rate_limits'])
        self.assertIsNotNone(result['models'])
        self.assertIsNotNone(result['config'])
        self.assertNotIn('SYNTHETIC_UPSTREAM_ERROR', json.dumps(result))

    def test_timeout_oversize_and_spawn_failure_are_unknown(self):
        unknown = dict.fromkeys(('rate_limits', 'models', 'config'))
        with patch.object(R, 'APP_SERVER_SECONDS', 0.5):
            self.assertEqual(self.read('silent'), unknown)
        with patch.object(R, 'APP_SERVER_MAX_LINE', 1024):
            self.assertEqual(self.read('huge'), unknown)
        self.assertEqual(self.read('normal', [str(self.root / 'missing-binary')]), unknown)


class ProviderProbe(unittest.TestCase):
    def test_authentication_is_bound_to_the_correct_service(self):
        with patch.dict(os.environ, {'TYPESAFE_API_KEY': 'SYNTHETIC_TYPESAFE'}), \
                patch.object(PROBE, 'get', return_value=({'http_status': 200}, {'models': [{'name': 'jev-1.14'}]})) as get:
            result = PROBE.probe('typesafe')
        self.assertEqual(get.call_args.args[0], 'https://api.typesafe.ai/v1/models')
        self.assertEqual(get.call_args.args[1]['Authorization'], 'Bearer SYNTHETIC_TYPESAFE')
        self.assertNotIn('SYNTHETIC_TYPESAFE', json.dumps(result))

    def test_anthropic_401_is_not_treated_as_budget_or_model_execution_success(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'SYNTHETIC_ANTHROPIC'}), \
                patch.object(PROBE, 'get', side_effect=[({'http_status': 200}, {'data': [{'id': 'claude-opus-5-5'}]}),
                                                       ({'http_status': 401}, None)]) as get:
            result = PROBE.probe('anthropic')
        self.assertEqual(result[-1]['http_status'], 401)
        self.assertFalse(result[-1]['provider_cap_verified'])
        self.assertEqual(get.call_args.args[1]['anthropic-beta'], 'spend-limit-reads-2026-09-26')
        self.assertNotIn('SYNTHETIC_ANTHROPIC', json.dumps(result))
        self.assertTrue(all(r['paid_requests'] == 0 for r in result))

    def test_redirects_and_unknown_endpoints_cannot_receive_keys(self):
        self.assertIsNone(PROBE.NoRedirect().redirect_request(None, None, None, None, None, None))
        with self.assertRaises(ValueError):
            PROBE.get('https://invalid.test/v1/models', {'Authorization': 'SYNTHETIC'})

    def test_even_200_spend_limits_cannot_attest_account_binding_or_auto_refill(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'SYNTHETIC'}), \
                patch.object(PROBE, 'get', side_effect=[({'http_status': 200}, {}),
                    ({'http_status': 200}, {'data': [{'amount': '2000', 'scope': {'type': 'organization'}}], 'next_page': None})]):
            result = PROBE.probe('anthropic')
        self.assertFalse(result[-1]['provider_cap_verified'])
        self.assertFalse(result[-1]['auto_refill_verified_off'])


if __name__ == '__main__':
    unittest.main()
