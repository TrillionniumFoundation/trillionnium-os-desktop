"""Exercise real filesystem descriptors; an optional custody APK also exercises apksigner."""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / 'bundle/source/shared/app_common.py'
spec = importlib.util.spec_from_file_location('selected_apk_app_common', SOURCE)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

PACKAGE = 'org.mozilla.firefox'
GUEST = '/data/app/org.mozilla.firefox/base.apk'
FIREFOX = {'bytes': 140689915, 'sha256': '283b19f8313e8ce6e8a913bb178ce4a79c5cecd82c49f821de7fafb068c73fcd'}
CERT = 'a78b62a5165b4494b2fead9e76a280d22d937fee6251aece599446b2ea319b04'
UID = 10123  # Test transport only. Production obtains the actual guest UID from Main.


class FileTarget:
    def __init__(self, source):
        self.source = source

    def open_root(self, path, flags):
        if path != GUEST:
            raise ValueError(path)
        return os.open(self.source, flags)

    def read_file(self, path, limit):
        if path != '/data/system/packages.list' or limit != 1024 * 1024:
            raise AssertionError('Only packages.list may use the buffered metadata reader')
        return f'{PACKAGE} {UID}\n'.encode(), None

    def verify(self):
        pass


def identity(row, pins):
    return {'metadata': {'package': PACKAGE, 'uid': UID}, 'expected': {'apks': pins}, 'artifacts': [row]}


class StreamedIdentity(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root / 'source.apk'
        self.source.write_bytes(b'apk test bytes')
        self.target = FileTarget(self.source)
        self.pin = {'bytes': self.source.stat().st_size, 'sha256': app.sha(self.source.read_bytes())}

    def test_large_sized_selection_is_streamed_and_held(self):
        with self.source.open('wb') as handle:
            handle.truncate(128 * 1024 * 1024 + 1)
        with self.source.open('rb') as handle:
            pin = {'bytes': self.source.stat().st_size, 'sha256': hashlib.file_digest(handle, 'sha256').hexdigest()}
        real_read = os.read
        requests = []
        def bounded_read(fd, size):
            self.assertLessEqual(size, 65536)
            requests.append(size)
            return real_read(fd, size)
        with mock.patch.object(app.os, 'read', bounded_read):
            row = app.stream_apk(self.target, GUEST, [pin])
            held = app.HeldArtifacts(self.target, [identity(row, [pin])])
            try:
                held.revalidate()
            finally:
                held.close()
        self.assertGreater(len(requests), 3 * pin['bytes'] // 65536)
        self.assertEqual(row['sha256'], pin['sha256'])

    def test_wrong_size_and_unbounded_legacy_refused_before_read(self):
        with mock.patch.object(app.os, 'read', side_effect=AssertionError('unexpected read')):
            with self.assertRaisesRegex(RuntimeError, 'APK_SIZE_OUTSIDE_SELECTED_INPUTS'):
                app.stream_apk(self.target, GUEST, [{**self.pin, 'bytes': self.pin['bytes'] + 1}])
            with self.source.open('wb') as handle:
                handle.truncate(128 * 1024 * 1024 + 1)
            with self.assertRaisesRegex(RuntimeError, 'APK_SIZE_OUTSIDE_SELECTED_INPUTS'):
                app.stream_apk(self.target, GUEST, [{'sha256': self.pin['sha256']}])

    def test_wrong_hash_output_and_existing_destination(self):
        out = self.root / 'signer-input.apk'
        with self.assertRaisesRegex(RuntimeError, 'SELECTED_COMPLETE_APK_HASH_OR_SIZE_CHANGED'):
            app.stream_apk(self.target, GUEST, [{**self.pin, 'sha256': '0' * 64}], out)
        self.assertEqual(set(self.root.iterdir()), {self.source})
        out.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            app.stream_apk(self.target, GUEST, [self.pin], out)
        self.assertEqual(out.read_bytes(), b'existing')
        self.assertEqual(set(self.root.iterdir()), {self.source, out})

    def test_exact_rows_and_legacy_hash_only_at_small_size(self):
        other = {**self.pin, 'sha256': 'a' * 64}
        row = app.stream_apk(self.target, GUEST, [other, self.pin], self.root / 'verified.apk')
        self.assertEqual(app.regular(row['private_copy']['path'], contents=False), row['private_copy'])
        legacy = identity(row, [])
        del legacy['expected']
        app.current_artifacts(self.target, legacy)
        app.validate_artifacts([row], {'apks': [{'sha256': self.pin['sha256']}]})
        with self.assertRaisesRegex(RuntimeError, 'EXPECTED_APK_BYTES_CHANGED'):
            app.validate_artifacts([row, row], {'apks': [other, self.pin]})

    def test_named_file_replaced_by_same_content(self):
        original_open = self.target.open_root
        opens = 0
        def replace_before_second_open(path, flags):
            nonlocal opens
            opens += 1
            if opens == 2:
                replacement = self.root / 'replacement'
                replacement.write_bytes(self.source.read_bytes())
                os.replace(replacement, self.source)
            return original_open(path, flags)
        with mock.patch.object(self.target, 'open_root', replace_before_second_open):
            with self.assertRaisesRegex(RuntimeError, 'COMPLETE_APK_FD_OR_NAMED_IDENTITY_CHANGED'):
                app.stream_apk(self.target, GUEST, [self.pin], self.root / 'verified.apk')
        self.assertEqual(set(self.root.iterdir()), {self.source})

    def test_multi_link_data_apk_refused(self):
        os.link(self.source, self.root / 'other.apk')
        with self.assertRaisesRegex(RuntimeError, 'SAME_REGULAR_APK_BACKING_REQUIRED'):
            app.stream_apk(self.target, GUEST, [self.pin])

    @unittest.skipUnless(os.environ.get('POCKET4_FIREFOX_APK'), 'supply the selected Mozilla custody APK')
    def test_selected_firefox_signature_and_full_identity_entry(self):
        # Only guest transport is a fixture. Read the custody APK through real FDs
        # and verify its actual private copy with the production-pinned apksigner.
        target = FileTarget(os.environ['POCKET4_FIREFOX_APK'])
        self.assertEqual(Path(target.source).stat().st_size, FIREFOX['bytes'])
        for pin, error in (({**FIREFOX, 'bytes': FIREFOX['bytes'] - 1}, 'APK_SIZE_OUTSIDE_SELECTED_INPUTS'),
                           ({**FIREFOX, 'sha256': '0' * 64}, 'SELECTED_COMPLETE_APK_HASH_OR_SIZE_CHANGED')):
            with self.assertRaisesRegex(RuntimeError, error):
                app.stream_apk(target, GUEST, [pin], self.root / 'rejected.apk')
            self.assertFalse((self.root / 'rejected.apk').exists())
        source = app.write_new(self.root / 'source.json', {})
        request = {'baseline': app.write_new(self.root / 'baseline.json', {}),
                   'qualification': app.write_new(self.root / 'qualification.json', {'source_manifest': app.SUPPORT_REF})}
        expected = {'package': PACKAGE, 'uid': UID, 'version_code': 2016196678, 'apks': [FIREFOX],
                    'certificate_sha256': CERT}
        def record(journal, name, argv, raw, stderr=b'', code=0):
            obj = {'argv': argv, 'host_retirement_proved': True, 'evidence_complete': True,
                   'returncode': code, 'timed_out': False, 'errors': [],
                   'stdout': app.write_new(journal / (name + '.out'), raw),
                   'stderr': app.write_new(journal / (name + '.err'), stderr)}
            return app.write_new(journal / (name + '.result.json'), obj)
        def sign(name, argv, timeout, journal, guard, **kwargs):
            proc = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=True)
            record(journal, name, argv, proc.stdout, proc.stderr, proc.returncode)
            return proc
        class TestView:
            def __init__(self, baseline, qualification, journal, admission, support_ref):
                self.target = target
                self.journal, self.admission, self.n = journal, admission, 0
                self.baseline = types.SimpleNamespace(value={'framework_epoch': {'sha256': 'test'}}, protected_pids={})
                self.commands = types.SimpleNamespace(run_recorded=sign)
            def command(self, argv, timeout):
                self.admission(argv, timeout, False, False)
                name = 'pm-' + str(self.n)
                self.n += 1
                logical = {'argv': argv, 'root_read': False, 'private_output': False, 'Android_mutation': False}
                raw = (f'package:{GUEST}\n' if argv[2] == 'path' else
                       f'package:{PACKAGE} versionCode:2016196678 uid:{UID}\n').encode()
                result = record(self.journal, name, argv, raw)
                transport = app.write_new(self.journal / (name + '-transport.json'), {
                    'schema': 'pocket4-final-app-read-transport-v1', 'logical': logical,
                    'lease_entered': True, 'lease_released': True, 'host_retirement_proved': True, 'error_type': None,
                    'post_guard': {'business_baseline_sha256': request['baseline']['sha256'],
                                   'business_qualification_sha256': request['qualification']['sha256']}})
                return raw, {'path': result['path'], 'command_observation': {}, 'transport': transport, 'logical': logical}
            def guard(self):
                pass
            def close(self):
                pass
        with mock.patch.object(app, 'MainView', TestView), mock.patch.object(app, 'GATES', source):
            ref = app.collect_identity(request, self.root / 'identity', expected, source)
            receipt = app.parse(app.read_ref(ref))
            app.validate_identity(receipt, expected, **{k + '_ref': v for k, v in request.items()})
        witness = app.EvidenceWitness([ref])
        try:
            witness.verify()
        finally:
            witness.close()
        # The same large file outside a semantically checked identity stays bounded.
        with self.assertRaisesRegex(RuntimeError, 'BOUNDED_SINGLE_LINK_FILE_REQUIRED'):
            app.EvidenceWitness([receipt['artifacts'][0]['private_copy']])
        self.assertEqual(receipt['artifacts'][0]['signature']['certificate_sha256'], CERT)
        held = app.HeldArtifacts(target, [receipt])
        try:
            held.revalidate()
        finally:
            held.close()


if __name__ == '__main__':
    unittest.main()
