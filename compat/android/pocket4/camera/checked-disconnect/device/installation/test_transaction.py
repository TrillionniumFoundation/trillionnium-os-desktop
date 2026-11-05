#!/usr/bin/env python3
"""Offline failure injection for the installer. No host/device commands are run."""
from contextlib import contextmanager
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import select
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('camera_transaction_test_subject', HERE / 'camera_transaction.py')
tx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tx)


def snapshot(digest):
    return {'identity': {'uid': tx.UID, 'ce_inode': 131469, 'de_inode': 131472,
                         'version': tx.VERSION, 'runtime_permissions': {'CAMERA': True}},
            'directories': {'ce': {'inode': 131469}, 'de': {'inode': 131472}},
            'epoch_sha256': tx.EPOCH_SHA,
            'apk': {'sha256': digest, 'bytes': 3, 'guest_path': '/data/app/test/base.apk'}}


def acknowledged(**changes):
    result = {'rc': 0, 'timed_out': False, 'joined': True, 'guard_after': True,
              'stdout': b'{"ok":true}'}
    result.update(changes)
    return result


class TransactionScenarios(unittest.TestCase):
    def run_scenario(self, after_data_change=False, responses=None, final_status_fails=False,
                     wrong_apk=False, preimage_wrong=False):
        commands = []
        old, new = tx.sha(b'old'), tx.sha(b'new')
        before, after = snapshot(old), snapshot(new)
        restored = snapshot(old)
        if preimage_wrong:
            before['apk']['sha256'] = 'unowned-preimage'
        if after_data_change:
            after['identity']['runtime_permissions']['CAMERA'] = False
        if wrong_apk:
            after['apk']['sha256'] = 'unowned-apk'
        responses = list(responses or [acknowledged(), acknowledged()])

        class Target:
            def read_file(self, *args, **kwargs):
                return b'old', {}

        class FakeSession:
            def __init__(self, folder):
                self.journal_dir = Path(folder)
                self.target = Target()

            def __enter__(self):
                self.journal_dir.mkdir()
                return self

            def __exit__(self, *args):
                return None

            def snapshot(self, label):
                return deepcopy({'before': before, 'after': after, 'rollback-after': restored}[label])

            def android(self, argv, timeout=20):
                if argv != ['/system/bin/cmd', 'activity', 'stack', 'list']:
                    raise AssertionError('Unexpected command in test')
                return b''

            def caller_status(self, label):
                if final_status_fails:
                    raise RuntimeError('Injected final Main/caller mismatch')

            def guard(self):
                return None

        @contextmanager
        def lock():
            yield

        def dispatch(session, path, digest, label):
            # Even the mocked command must consume the exact retained/staged bytes.
            self.assertEqual(tx.sha(Path(path).read_bytes()), digest)
            commands.append((label, digest))
            return responses.pop(0)

        with tempfile.TemporaryDirectory(prefix='camera-install08-offline-') as temporary:
            root = Path(temporary)
            (root / 'candidate.apk').write_bytes(b'new')
            with patch.multiple(tx, RUN=root / 'install-01', CANDIDATE=root / 'candidate.apk',
                                OLD_SHA=old, NEW_SHA=new, APK_BYTES=3,
                                CameraSession=FakeSession, ui_lock=lock, install_once=dispatch), \
                    patch.object(tx, 'verify_signature'), patch.object(tx, 'verify_payload'), \
                    patch.object(tx.os, 'chown'), patch.object(tx.os, 'fchown'):
                result = tx.execute_update()
                archived = json.loads((tx.RUN / 'result.json').read_text())
                self.assertEqual(result, archived)
                with self.assertRaises(FileExistsError):
                    tx.execute_update()
                count_after_reinvocation = len(commands)
        self.assertEqual(count_after_reinvocation, len(commands))
        return result, commands, old, new

    def test_known_success_has_one_dispatch_and_preserves_data(self):
        result, calls, _, new = self.run_scenario()
        self.assertEqual(result['state'], 'INSTALLED_VERIFIED')
        self.assertEqual(calls, [('install', new)])
        self.assertTrue(result['data_identity_preserved'])

    def test_response_loss_with_new_apk_visible_never_replays_or_rolls_back(self):
        for failed in [acknowledged(timed_out=True, rc=-9), acknowledged(stdout=b''),
                       acknowledged(stdout=b'{"ok":false}')]:
            with self.subTest(response=failed):
                result, calls, _, _ = self.run_scenario(responses=[failed])
                self.assertEqual(result['state'], 'INSTALL_OUTCOME_UNKNOWN')
                self.assertEqual(len(calls), 1)

    def test_unknown_response_plus_data_difference_cannot_trigger_rollback(self):
        result, calls, _, _ = self.run_scenario(after_data_change=True,
            responses=[acknowledged(timed_out=True, rc=-9)])
        self.assertEqual(result['state'], 'INSTALL_OUTCOME_UNKNOWN')
        self.assertEqual(len(calls), 1)

    def test_known_data_mismatch_allows_one_exact_preimage_rollback(self):
        result, calls, old, new = self.run_scenario(after_data_change=True)
        self.assertEqual(result['state'], 'ROLLED_BACK_VERIFIED')
        self.assertEqual(calls, [('install', new), ('rollback-after-data-check', old)])

    def test_unknown_rollback_is_not_retried(self):
        result, calls, _, _ = self.run_scenario(after_data_change=True,
            responses=[acknowledged(), acknowledged(stdout=b'not-json')])
        self.assertEqual(result['state'], 'ROLLBACK_NOT_FULLY_VERIFIED')
        self.assertEqual(len(calls), 2)

    def test_final_caller_failure_invalidates_success(self):
        result, calls, _, _ = self.run_scenario(final_status_fails=True)
        self.assertEqual(result['state'], 'FINAL_IDENTITY_CHECK_FAILED')
        self.assertEqual(result['state_before_final_guard_failure'], 'INSTALLED_VERIFIED')
        self.assertEqual(len(calls), 1)

    def test_unexpected_readback_apk_is_not_overwritten(self):
        result, calls, _, _ = self.run_scenario(wrong_apk=True)
        self.assertEqual(result['state'], 'POST_INSTALL_APK_DIFFERS')
        self.assertEqual(len(calls), 1)

    def test_wrong_preimage_never_dispatches(self):
        result, calls, _, _ = self.run_scenario(preimage_wrong=True)
        self.assertEqual(result['state'], 'NOT_DISPATCHED')
        self.assertEqual(calls, [])

    def test_busy_lock_does_not_consume_unique_transaction(self):
        @contextmanager
        def busy():
            raise BlockingIOError('owned elsewhere')
            yield
        with tempfile.TemporaryDirectory(prefix='camera-lock-offline-') as temporary:
            run = Path(temporary) / 'install-01'
            with patch.multiple(tx, RUN=run, ui_lock=busy):
                with self.assertRaises(BlockingIOError):
                    tx.execute_update()
            self.assertFalse(run.exists())

    def test_present_host_pid_must_match(self):
        self.assertTrue(tx.verified_response(acknowledged()))
        for value in [{'ok': True, 'host_pid': tx.MAIN_HOST + 1}, [], None]:
            self.assertFalse(tx.verified_response(acknowledged(stdout=json.dumps(value).encode())))

    def test_timeout_stops_actual_owned_child_group_without_retry(self):
        # Real local subprocess control, never a device or privileged entry.
        # Killing only the leader leaves this child's sleep alive and fails.
        with tempfile.TemporaryDirectory(prefix='camera-command-offline-') as temporary:
            session = tx.CameraSession(temporary)
            session.guard = lambda: None
            code = ('import os,time\n'
                    'p=os.fork()\n'
                    'if p: print("forked",flush=True)\n'
                    'time.sleep(4)\n')
            reader, writer = os.pipe()
            try:
                result = session.run_host('owned-timeout', [sys.executable, '-c', code],
                                          timeout=0.5, pass_fds=(writer,))
                os.close(writer)
                writer = -1
                self.assertEqual(result['stdout'].strip(), b'forked')
                self.assertTrue(result['timed_out'])
                self.assertTrue(result['joined'])
                self.assertFalse(result['automatic_retry'])
                # EOF proves both holders of this private inherited FD exited;
                # this avoids making assumptions about the cloud /proc view.
                ready, _, _ = select.select([reader], [], [], 1)
                self.assertEqual(ready, [reader], 'owned child still holds inherited descriptor')
                self.assertEqual(os.read(reader, 1), b'')
            finally:
                if writer >= 0:
                    os.close(writer)
                os.close(reader)

    def test_hidden_factory_package_cannot_contaminate_active_identity(self):
        permissions = '\n'.join('        ' + p + ': granted=' +
            ('true' if p == 'android.permission.CAMERA' else 'false') + ', flags=[]'
            for p in sorted(tx.PERMISSIONS))
        # Synthetic fixture, using current package values. This is deliberately
        # not claimed to be an actual device package dump.
        active = ('Packages:\n  Package [com.android.camera2] (abc):\n'
                  '    appId=10062\n    codePath=/data/app/active\n'
                  '    versionCode=20002000 minSdk=37 targetSdk=1000\n'
                  '    User 0: ceDataInode=131469 deDataInode=131472 installed=true hidden=false suspended=false\n'
                  '      dataDir=/data/user/0/com.android.camera2\n'
                  '      firstInstallTime=2026-10-07 03:30:59\n' + permissions + '\n')
        hidden = 'Hidden system packages:\n' + active.replace('Packages:\n', '').replace('appId=10062', 'appId=12345')
        identity = tx.parse_identity(active + hidden, '/data/app/active/base.apk')
        self.assertEqual(identity['uid'], 10062)
        self.assertEqual(identity['ce_inode'], 131469)
        with self.assertRaisesRegex(RuntimeError, 'ACTIVE_PACKAGE_SECTION_AMBIGUOUS'):
            tx.parse_identity(active + active, '/data/app/active/base.apk')
        with self.assertRaisesRegex(RuntimeError, 'CAMERA_PERMISSION_SET_DIFFERS'):
            tx.parse_identity(active.replace('android.permission.CAMERA', 'android.permission.UNKNOWN'),
                              '/data/app/active/base.apk')


if __name__ == '__main__':
    unittest.main(verbosity=2)
