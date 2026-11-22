"""Real-process lock regressions; permission/I/O faults are injected explicitly."""
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QLockFile, QSysInfo

from app.core.instance import InstanceLockError, SingleInstance


HELPER = r'''
import json, os, sys, time
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from app.core.instance import SingleInstance, InstanceLockError
app = QCoreApplication([])
directory, mode, tag = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
if mode == 'race':
    (directory / (tag + '.ready')).touch()
    while not (directory / 'go').exists(): time.sleep(.01)
try:
    with SingleInstance(directory):
        result = {'kind': 'acquired', 'pid': os.getpid()}
        (directory / (tag + '.result')).write_text(json.dumps(result))
        if mode == 'crash': os._exit(73)
        while not (directory / 'stop').exists(): time.sleep(.01)
except InstanceLockError as exc:
    (directory / (tag + '.result')).write_text(json.dumps({'kind': exc.kind, 'message': str(exc)}))
    sys.exit(3)
'''

APP_HELPER = r'''
import json, os, sys
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox
from app.main import main, CompanionController
if os.environ.get('COMPANION_TEST_TRAY_EXIT'):
    original_start = CompanionController.start
    def start_with_tray_exit(self):
        original_start(self)
        QTimer.singleShot(150, self.controls.exit_action.trigger)
    CompanionController.start = start_with_tray_exit
def dialog(parent, title, message):
    print(json.dumps({'title': title, 'message': message}), flush=True)
    return QMessageBox.StandardButton.Ok
with patch.object(QMessageBox, 'information', dialog), patch.object(QMessageBox, 'critical', dialog):
    sys.exit(main(sys.argv[1:]))
'''


class InstanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.children = []

    def tearDown(self):
        (self.directory / 'stop').touch()
        (self.directory / 'go').touch()
        for child in self.children:
            # Only subprocess handles created by this test; never a PID from a lock.
            child.communicate(timeout=15)
        self.temp.cleanup()

    def launch(self, mode='hold', tag='owner'):
        child = subprocess.Popen([sys.executable, '-u', '-c', HELPER, str(self.directory), mode, tag],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(child)
        return child

    def wait_file(self, name):
        path = self.directory / name
        deadline = time.monotonic() + 10
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue(path.exists(), f'Timed out waiting for {name}')
        return path

    def result(self, tag):
        path = self.wait_file(tag + '.result')
        # A file can become visible just before the tiny write completes.
        deadline = time.monotonic() + 2
        while True:
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                if time.monotonic() >= deadline: raise
                time.sleep(.01)

    def test_running_owner_rejected_without_changing_lock_or_settings(self):
        settings = self.directory / 'settings.json'
        settings.write_text('{"user-data":"preserve"}')
        child = self.launch()
        owner = self.result('owner')
        lock_path = self.directory / 'application.lock'
        original = lock_path.read_bytes()
        with self.assertRaises(InstanceLockError) as caught:
            with SingleInstance(self.directory): self.fail('Concurrent owner admitted')
        self.assertEqual(caught.exception.kind, 'active')
        self.assertIn(str(owner['pid']), str(caught.exception))
        self.assertIn(str(lock_path), str(caught.exception))
        self.assertEqual(lock_path.read_bytes(), original)
        self.assertEqual(settings.read_text(), '{"user-data":"preserve"}')
        self.assertIsNone(child.poll())

    def test_simultaneous_launches_admit_exactly_one(self):
        self.launch('race', 'one'); self.launch('race', 'two')
        self.wait_file('one.ready'); self.wait_file('two.ready')
        (self.directory / 'go').touch()
        self.assertEqual(sorted([self.result('one')['kind'], self.result('two')['kind']]), ['acquired', 'active'])

    def test_crashed_owner_lock_recovers_automatically(self):
        child = self.launch('crash')
        self.result('owner')
        self.assertEqual(child.wait(timeout=10), 73)
        path = self.directory / 'application.lock'
        self.assertTrue(path.exists(), 'Crash must leave a real stale lock')
        with SingleInstance(self.directory) as acquired:
            self.assertTrue(acquired.lock.isLocked())
            self.assertEqual(acquired.lock.getLockInfo()[0], os.getpid())
        self.assertFalse(path.exists())

    @unittest.skipUnless(sys.platform == 'win32', 'Windows read-only attribute test')
    def test_readonly_stale_lock_reports_real_windows_access_failure(self):
        child = self.launch('crash'); self.result('owner')
        self.assertEqual(child.wait(timeout=10), 73)
        path = self.directory / 'application.lock'; original = path.read_bytes()
        path.chmod(stat.S_IREAD)
        try:
            with self.assertRaises(InstanceLockError) as caught:
                with SingleInstance(self.directory): pass
            self.assertEqual(caught.exception.kind, 'permission')
            self.assertIn('read-only', str(caught.exception))
            self.assertEqual(path.read_bytes(), original)
        finally:
            path.chmod(stat.S_IWRITE)
        with SingleInstance(self.directory): pass

    def test_normal_shutdown_releases_and_allows_relaunch(self):
        child = self.launch(); self.result('owner')
        (self.directory / 'stop').touch()
        self.assertEqual(child.wait(timeout=10), 0)
        self.assertFalse((self.directory / 'application.lock').exists())
        with SingleInstance(self.directory): pass
        self.assertFalse((self.directory / 'application.lock').exists())

    def test_exception_releases_lock_and_close_is_idempotent(self):
        instance = SingleInstance(self.directory)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            with instance:
                self.assertEqual(instance.lock.staleLockTime(), 0)
                raise RuntimeError('cleanup failed')
        instance.close(); instance.close()
        with SingleInstance(self.directory): pass

    def test_corrupt_owner_is_preserved_and_not_reported_as_active(self):
        path = self.directory / 'application.lock'
        original = b'incomplete owner record\n'
        path.write_bytes(original)
        with self.assertRaises(InstanceLockError) as caught:
            with SingleInstance(self.directory): pass
        self.assertEqual(caught.exception.kind, 'unverified')
        self.assertEqual(path.read_bytes(), original)

    def test_permission_and_io_errors_have_distinct_diagnostics(self):
        for code, kind in [(QLockFile.LockError.PermissionError, 'permission'),
                           (QLockFile.LockError.UnknownError, 'filesystem')]:
            with self.subTest(code=code), patch('app.core.instance.QLockFile') as factory:
                factory.LockError = QLockFile.LockError
                factory.return_value.tryLock.return_value = False
                factory.return_value.error.return_value = code
                with self.assertRaises(InstanceLockError) as caught:
                    with SingleInstance(self.directory): pass
                self.assertEqual(caught.exception.kind, kind)
                self.assertIn(code.name, str(caught.exception))
                factory.return_value.getLockInfo.assert_not_called()

    def test_folder_permission_denial_preserves_settings(self):
        path = self.directory / 'settings.json'; path.write_text('unchanged')
        with patch.object(Path, 'mkdir', side_effect=PermissionError('injected access denied')):
            with self.assertRaises(InstanceLockError) as caught:
                with SingleInstance(self.directory): pass
        self.assertEqual(caught.exception.kind, 'permission')
        self.assertEqual(path.read_text(), 'unchanged')

    def test_directory_at_lock_path_is_filesystem_error(self):
        (self.directory / 'application.lock').mkdir()
        with self.assertRaises(InstanceLockError) as caught:
            with SingleInstance(self.directory): pass
        self.assertEqual(caught.exception.kind, 'filesystem')

    def test_dead_owner_not_recoverable_has_specific_diagnostic(self):
        import psutil
        with patch('app.core.instance.QLockFile') as factory, patch('psutil.Process', side_effect=psutil.NoSuchProcess(123)):
            factory.LockError = QLockFile.LockError
            factory.return_value.tryLock.return_value = False
            factory.return_value.error.return_value = QLockFile.LockError.LockFailedError
            factory.return_value.getLockInfo.return_value = (123, QSysInfo.machineHostName(), 'python')
            with self.assertRaises(InstanceLockError) as caught:
                with SingleInstance(self.directory): pass
            self.assertEqual(caught.exception.kind, 'stale')
            factory.return_value.removeStaleLockFile.assert_not_called()

    def run_app(self, *args, tray_exit=False):
        environment = os.environ.copy()
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        if tray_exit:
            environment['COMPANION_TEST_TRAY_EXIT'] = '1'
        return subprocess.run([sys.executable, '-c', APP_HELPER, '--data-dir', str(self.directory), *args],
                              capture_output=True, text=True, timeout=15, env=environment)

    def test_duplicate_application_reports_owner_and_path_before_loading_settings(self):
        self.launch(); owner = self.result('owner')
        settings = self.directory / 'settings.json'; settings.write_text('do not read or overwrite this')
        result = self.run_app()
        self.assertEqual(result.returncode, 3, result.stderr)
        dialog = json.loads(result.stdout)
        self.assertEqual(dialog['title'], 'Companion already running')
        self.assertIn(str(owner['pid']), dialog['message'])
        self.assertIn(str(self.directory / 'application.lock'), dialog['message'])
        self.assertNotIn('permissions', dialog['message'])
        self.assertEqual(settings.read_text(), 'do not read or overwrite this')

    def test_application_log_startup_failure_releases_lock(self):
        (self.directory / 'companion.log').mkdir()
        result = self.run_app()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('Cannot create log file', result.stdout)
        self.assertFalse((self.directory / 'application.lock').exists())
        with SingleInstance(self.directory): pass

    def test_application_corrupt_settings_failure_releases_lock_and_preserves_data(self):
        path = self.directory / 'settings.json'; path.write_text('invalid JSON')
        result = self.run_app()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse((self.directory / 'application.lock').exists())
        self.assertEqual(path.read_text(), 'invalid JSON')

    def test_application_event_loop_exit_and_restart_release_lock(self):
        for _ in range(2):
            result = self.run_app('--benchmark-seconds', '3')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((self.directory / 'application.lock').exists())
            self.assertIsNotNone(json.loads((self.directory / 'benchmark.json').read_text())['startup_entry_to_first_paint_ms'])
            self.assertTrue((self.directory / 'settings.json').exists())

    def test_application_tray_exit_saves_and_releases_lock(self):
        result = self.run_app(tray_exit=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.directory / 'application.lock').exists())
        self.assertTrue((self.directory / 'settings.json').exists())
        with SingleInstance(self.directory): pass


if __name__ == '__main__': unittest.main()
