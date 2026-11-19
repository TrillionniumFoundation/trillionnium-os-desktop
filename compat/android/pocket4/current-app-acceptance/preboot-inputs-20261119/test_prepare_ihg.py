"""Finite host controls for current source rebinding; no Android commands."""
from pathlib import Path
import copy
import importlib.util
import os
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('ihg_preboot', HERE / 'prepare_ihg.py')
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


class CurrentInputBinding(unittest.TestCase):
    def setUp(self):
        self.candidate = helper.parse((HERE / 'ihg-inputs/candidate.json').read_bytes())
        self.receipt = helper.parse((HERE / 'ihg-inputs/receipt.json').read_bytes())
        self.badging = helper.parse((HERE / 'ihg-launcher-observation.json').read_bytes())

    def check(self):
        helper.verify_current(self.candidate, self.receipt, self.badging)

    def test_actual_published_receipt_and_new_badging_join(self):
        self.check()

    def test_current_candidate_cannot_relabel_an_old_version(self):
        self.candidate['version_code'] = 50023496
        with self.assertRaises(ValueError):
            self.check()

    def test_actual_signer_mismatch_rejected(self):
        self.receipt['identities'][0]['signer_certificate_sha256'] = ['0' * 64]
        with self.assertRaises(ValueError):
            self.check()

    def test_failed_actual_signature_rejected(self):
        self.receipt['identities'][0]['tool_exits']['signature'] = 1
        with self.assertRaises(ValueError):
            self.check()

    def test_split_requirement_cannot_be_dropped(self):
        self.receipt['split_closure']['standalone_dependency_absence_verified'] = False
        with self.assertRaises(ValueError):
            self.check()

    def test_new_input_does_not_grant_runtime_credit(self):
        self.receipt['runtime_qualified'] = True
        with self.assertRaises(ValueError):
            self.check()

    def test_stale_badging_digest_rejected(self):
        self.receipt['identities'][0]['tool_output_sha256']['badging'] = '0' * 64
        with self.assertRaises(ValueError):
            self.check()

    def test_coherently_repinned_wrong_launcher_rejected(self):
        self.badging['stdout'] = self.badging['stdout'].replace(
            'com.ihg.apps.android.activity.MainActivity', 'com.ihg.apps.android.activity.OtherActivity')
        digest = helper.sha(self.badging['stdout'].encode())
        self.badging['stdout_sha256'] = digest
        self.receipt['identities'][0]['tool_output_sha256']['badging'] = digest
        with self.assertRaises(ValueError):
            self.check()

    def test_extra_actual_identity_rejected(self):
        self.receipt['identities'] *= 2
        with self.assertRaises(ValueError):
            self.check()

    def test_exact_literal_rebind_preserves_all_other_business_source(self):
        source = HERE.parent / 'business/source'
        before = {p.name: p.read_bytes() for p in source.iterdir()}
        after = helper.transform(before)
        self.assertEqual(len(after), 31)
        self.assertEqual({name for name in before if before[name] != after[name]}, set(helper.CHANGES))
        self.assertEqual(after['timer_flow.py'], before['timer_flow.py'])
        common = helper.module(before['app_common.py'], source / 'app_common.py')
        old = helper.module(before['app_profiles.py'], source / 'app_profiles.py')
        current = helper.module(after['app_profiles.py'], source / 'app_profiles.py')
        raw = b'package:com.ihg.apps.android versionCode:50023808 uid:10137\n'
        with self.assertRaises(RuntimeError):
            common.package_metadata(raw, old.IHG)
        self.assertEqual(common.package_metadata(raw, current.IHG)['version_code'], 50023808)
        with self.assertRaises(RuntimeError):
            common.package_metadata(raw.replace(b'50023808', b'50023496'), current.IHG)
        for key in ('CLOCK', 'CLOCK_HELPER', 'CLOCK_LIMITS', 'IHG_LIMITS'):
            self.assertEqual(getattr(old, key), getattr(current, key))

    def test_incomplete_source_packet_rejected(self):
        source = HERE.parent / 'business/source'
        before = {p.name: p.read_bytes() for p in source.iterdir()}
        before.pop('ihg_case.py')
        with self.assertRaises(ValueError):
            helper.transform(before)

    def test_identical_bytes_with_changed_F9_between_reads_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source'
            raw = b'published source\n'
            path.write_bytes(raw)
            ref = {'path': str(path), 'bytes': len(raw), 'sha256': helper.sha(raw)}
            bookends = {}
            helper.read(ref, bookends=bookends)
            s = path.stat()
            os.utime(path, ns=(s.st_atime_ns, s.st_mtime_ns + 1000000))
            with self.assertRaises(ValueError):
                helper.read(ref, bookends=bookends)


if __name__ == '__main__':
    unittest.main()
