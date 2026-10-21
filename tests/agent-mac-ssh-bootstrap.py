#!/usr/bin/env python3
"""Validate the Mac service edit and rollback without touching launchd."""
import contextlib
import importlib.machinery
import importlib.util
import io
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'dot_local/bin/executable_agent-mac-ssh-bootstrap'
loader = importlib.machinery.SourceFileLoader('bootstrap', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
app = importlib.util.module_from_spec(spec)
loader.exec_module(app)


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'service.plist'
        self.service = {'Label': app.LABEL, 'ProgramArguments': [app.DAEMON],
                        'KeepAlive': True, 'StandardErrorPath': '/var/log/unchanged'}
        self.path.write_bytes(plistlib.dumps(self.service))

    def read_fixture(self, service=None, mode=0o100644, uid=0):
        if service is not None:
            self.path.write_bytes(plistlib.dumps(service))
        with patch.object(Path, 'lstat', return_value=SimpleNamespace(st_mode=mode, st_uid=uid)):
            return app.load_service(self.path)

    def test_original_and_userspace_service_are_accepted(self):
        self.assertEqual(self.read_fixture(), self.service)
        self.service['ProgramArguments'].append(app.TUN)
        self.assertEqual(self.read_fixture(self.service), self.service)

    def test_unexpected_service_or_arguments_are_rejected(self):
        for key, value in [('Label', 'different'), ('UserName', 'somebody'),
                           ('Program', '/tmp/daemon'), ('ProgramArguments', [app.DAEMON, '--state=mem:'])]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.read_fixture(dict(self.service, **{key: value}))

    def test_unsafe_file_ownership_or_permissions_are_rejected(self):
        for mode, uid in [(0o120777, 0), (0o100664, 0), (0o100644, 1000)]:
            with self.subTest(mode=mode, uid=uid), self.assertRaises(ValueError):
                self.read_fixture(mode=mode, uid=uid)

    def test_write_preserves_unrelated_fields_and_sets_mode(self):
        changed = dict(self.service, ProgramArguments=[app.DAEMON, app.TUN])
        app.write_service(self.path, changed)
        self.assertEqual(plistlib.loads(self.path.read_bytes()), changed)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o644)
        self.assertEqual(list(self.path.parent.glob('.agent-tailscale-*')), [])

    def test_failed_start_restores_original_before_retry(self):
        failure = subprocess.CalledProcessError(1, ['launchctl', 'bootstrap'])
        with patch.object(app, 'stop_service') as stop, \
                patch.object(app, 'start_service', side_effect=[failure, None]) as start, \
                patch.object(app, 'write_service') as write:
            with self.assertRaisesRegex(RuntimeError, 'previous service restored'):
                app.restart_service({'new': True}, rollback=self.service)
            self.assertEqual(write.call_args_list[-1].args, (app.PLIST, self.service))
            self.assertEqual(stop.call_count, 2)
            self.assertEqual(start.call_count, 2)

    def test_failed_stop_does_not_write_any_service(self):
        with patch.object(app, 'stop_service', side_effect=subprocess.CalledProcessError(1, ['bootout'])), \
                patch.object(app, 'write_service') as write:
            with self.assertRaises(subprocess.CalledProcessError):
                app.restart_service(self.service)
            write.assert_not_called()

    def test_stop_waits_until_job_is_removed(self):
        with patch.object(app, 'service_loaded', side_effect=[True, True, True, False]) as state, \
                patch.object(app, 'run') as run, patch.object(app.time, 'sleep') as sleep:
            app.stop_service()
            run.assert_called_once_with(app.LAUNCHCTL, 'bootout', f'system/{app.LABEL}')
            self.assertEqual(state.call_count, 4)
            self.assertEqual(sleep.call_count, 2)

    def test_unloaded_service_does_not_get_booted_out(self):
        with patch.object(app, 'service_loaded', return_value=False), patch.object(app, 'run') as run:
            app.stop_service()
            run.assert_not_called()

    def test_start_bootstraps_unloaded_service_and_checks_localapi(self):
        with patch.object(app, 'service_loaded', return_value=False), \
                patch.object(app, 'daemon_ready', side_effect=[False, True]) as ready, \
                patch.object(app, 'run') as run, patch.object(app.time, 'sleep'):
            app.start_service()
            run.assert_called_once_with(app.LAUNCHCTL, 'bootstrap', 'system', str(app.PLIST))
            self.assertEqual(ready.call_count, 2)

    def test_loaded_job_is_not_mistaken_for_ready_daemon(self):
        with patch.object(app, 'service_loaded', return_value=True), \
                patch.object(app, 'daemon_ready', side_effect=[False, False, True]) as ready, \
                patch.object(app, 'run') as run, patch.object(app.time, 'sleep'):
            app.start_service()
            run.assert_not_called()
            self.assertEqual(ready.call_count, 3)

    def test_service_state_distinguishes_absence_from_permission_failure(self):
        for code, stderr, expected in [(0, '', True), (113, 'Could not find service "x"', False)]:
            with patch.object(app.subprocess, 'run', return_value=SimpleNamespace(returncode=code, stderr=stderr)):
                self.assertEqual(app.service_loaded(), expected)
        with patch.object(app.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stderr='permission denied')):
            with self.assertRaisesRegex(RuntimeError, 'Cannot determine'):
                app.service_loaded()

    def test_localapi_check_never_falls_back_to_gui(self):
        with patch.object(app.subprocess, 'run', return_value=SimpleNamespace(stdout='')) as run:
            self.assertFalse(app.daemon_ready())
            self.assertEqual(run.call_args.args[0][1], app.SOCKET)
        with patch.object(app.subprocess, 'run', return_value=SimpleNamespace(stdout='{"BackendState":"NeedsLogin"}')):
            self.assertTrue(app.daemon_ready())

    def test_restore_works_when_service_is_unloaded(self):
        with patch.object(app.platform, 'system', return_value='Darwin'), \
                patch.object(app.os, 'geteuid', return_value=0), \
                patch.object(app, 'load_service', return_value=self.service), \
                patch.object(app, 'service_loaded', return_value=False), \
                patch.object(app, 'daemon_ready', return_value=True), \
                patch.object(app, 'write_service') as write, patch.object(app, 'run') as run, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(['--restore']), 0)
            write.assert_called_once_with(app.PLIST, self.service)
            run.assert_called_once_with(app.LAUNCHCTL, 'bootstrap', 'system', str(app.PLIST))

    def test_failed_rollback_reports_both_failures(self):
        with patch.object(app, 'stop_service'), patch.object(app, 'write_service'), \
                patch.object(app, 'start_service', side_effect=[RuntimeError('new failed'), RuntimeError('old failed')]):
            with self.assertRaisesRegex(RuntimeError, 'new failed; restore also failed: old failed'):
                app.restart_service({'new': True}, rollback=self.service)

    def test_stopping_timeout_never_writes_replacement(self):
        with patch.object(app, 'service_loaded', return_value=True), \
                patch.object(app, 'run'), patch.object(app, 'write_service') as write, \
                patch.object(app.time, 'monotonic', side_effect=[0, 21]):
            with self.assertRaisesRegex(RuntimeError, 'service removal'):
                app.restart_service({'new': True}, rollback=self.service)
            write.assert_not_called()

    def test_async_launchd_removal_does_not_race_bootstrap(self):
        state = {'loaded': True, 'removing': 0, 'starts': 0}

        def command(argv, **kwargs):
            if argv[0] == app.CLI:
                return SimpleNamespace(returncode=0, stdout='{"BackendState":"NeedsLogin"}', stderr='')
            action = argv[1]
            if action == 'print':
                if state['removing']:
                    state['removing'] -= 1
                    if not state['removing']:
                        state['loaded'] = False
                return SimpleNamespace(returncode=0 if state['loaded'] else 113, stdout='',
                                       stderr='' if state['loaded'] else 'Could not find service "x"')
            if action == 'bootout':
                state['removing'] = 3
            elif action == 'bootstrap':
                if state['loaded']:
                    raise subprocess.CalledProcessError(5, argv)
                state['loaded'] = True
                state['starts'] += 1
            return SimpleNamespace(returncode=0)

        replacement = dict(self.service, ProgramArguments=[app.DAEMON, app.TUN])
        with patch.object(app, 'PLIST', self.path), patch.object(app.subprocess, 'run', side_effect=command), \
                patch.object(app.time, 'sleep'):
            app.restart_service(replacement, rollback=self.service)
        self.assertEqual(state['starts'], 1)
        self.assertTrue(state['loaded'])
        self.assertEqual(plistlib.loads(self.path.read_bytes()), replacement)

    def test_apply_starts_existing_service_before_changing_preferences(self):
        events = []
        backup = self.path.parent / 'backup.plist'
        with patch.object(app, 'PLIST', self.path), patch.object(app, 'BACKUP', backup), \
                patch.object(app.platform, 'system', return_value='Darwin'), \
                patch.object(app.os, 'geteuid', return_value=0), patch.object(app.os, 'access', return_value=True), \
                patch.object(app, 'load_service', return_value=dict(self.service)), \
                patch.object(app, 'start_service', side_effect=lambda: events.append('start')), \
                patch.object(app, 'run', side_effect=lambda *args: events.append(args[2] if args[0] == app.CLI else 'lint')), \
                patch.object(app, 'restart_service', side_effect=lambda *args, **kwargs: events.append('restart')), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(['--apply', '--hostname', 'automation-node']), 0)
        self.assertEqual(events, ['lint', 'start', 'set', 'restart'])
        self.assertEqual(backup.read_bytes(), self.path.read_bytes())

    def test_check_is_read_only(self):
        with patch.object(app.platform, 'system', return_value='Darwin'), \
                patch.object(app, 'load_service', return_value=self.service), \
                patch.object(app, 'run') as run, patch.object(app, 'write_service') as write, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(app.main([]), 0)
            run.assert_not_called()
            write.assert_not_called()

    def test_invalid_hostname_never_calls_service_commands(self):
        for name in ['', '-bad', 'bad.example', 'bad;cmd', 'a' * 64]:
            with self.subTest(name=name), \
                    patch.object(app.platform, 'system', return_value='Darwin'), \
                    patch.object(app, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    app.main(['--apply', '--hostname', name])
                run.assert_not_called()

    def test_apply_requires_root(self):
        with patch.object(app.platform, 'system', return_value='Darwin'), \
                patch.object(app.os, 'geteuid', return_value=1000), \
                patch.object(app, 'load_service', return_value=self.service), \
                patch.object(app, 'run') as run, contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                app.main(['--apply', '--hostname', 'automation-node'])
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
