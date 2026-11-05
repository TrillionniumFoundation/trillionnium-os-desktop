"""Regression for the observed ART20 collection failure; no device calls."""
from pathlib import Path
import hashlib,json,runpy,unittest

HERE=Path(__file__).resolve().parent
API=runpy.run_path(str(HERE/'verify_candidate22.py'))
FIXTURE=(HERE/'fixtures/original-target-window.txt').read_bytes()
assert hashlib.sha256(FIXTURE).hexdigest()=='ca8268b45d3b9ceae7ca87dc0d7164d9bc009c4bfd85adfbb0e6635113fbb3f2'
TEXT=FIXTURE.decode()

class ActualTargetParser(unittest.TestCase):
    def test_actual_verified_class_and_immutable_method(self):
        proof,window=API['target_proof'](TEXT)
        self.assertEqual(proof['status'],'Verified')
        self.assertIn('ImmutableVolumeInfo',proof['method_header'])
        self.assertEqual(window,TEXT)

    def test_unrelated_lookup_rows_do_not_exhaust_target_line_budget(self):
        noise='lookup: com.android.server.storage.StorageSessionController unrelated\n'*1000
        self.assertEqual(API['target_proof'](noise+TEXT),API['target_proof'](TEXT))

    def test_non_verified_statuses_are_rejected(self):
        for status in ('VerifiedNeedsAccessChecks','RetryVerificationAtRuntime','Verifying','Unknown'):
            with self.subTest(status=status),self.assertRaisesRegex(RuntimeError,'NOT_VERIFIED'):
                API['target_proof'](TEXT.replace('(Verified)',f'({status})',1))

    def test_nested_class_cannot_replace_exact_outer_class(self):
        with self.assertRaisesRegex(RuntimeError,'CLASS_NOT_UNIQUE'):
            API['target_proof'](TEXT.replace('Lcom/android/server/storage/StorageSessionController;',
                                           'Lcom/android/server/storage/StorageSessionController$1;',1))

    def test_duplicate_exact_class_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'CLASS_NOT_UNIQUE'):
            API['target_proof'](TEXT+TEXT)

    def test_method_must_belong_to_same_exact_class(self):
        head,rest=TEXT.split('\n',1)
        other='1963: Lcom/android/server/storage/Other; (offset=0x000267f0) (type_idx=4528) (Verified) (NoneCompiled)\n'
        with self.assertRaisesRegex(RuntimeError,'METHOD_NOT_IN_EXACT_CLASS'):
            API['target_proof'](head+'\n'+other+rest)

    def test_duplicate_target_method_is_rejected(self):
        header=TEXT.splitlines()[1]+'\n'
        with self.assertRaisesRegex(RuntimeError,'METHOD_NOT_IN_EXACT_CLASS'):
            API['target_proof'](TEXT+header)

    def test_command_comparison_accepts_only_descriptor_numbers_and_owned_output_name(self):
        argv=json.loads((HERE/'fixtures/original-compiler-argv.json').read_text())['argv']
        altered=[x.replace('/original.odex','/candidate.odex') for x in argv]
        self.assertEqual(API['normalized_argv'](argv),API['normalized_argv'](altered))
        bad=[x.replace('--compiler-filter=verify','--compiler-filter=speed') for x in altered]
        self.assertNotEqual(API['normalized_argv'](argv),API['normalized_argv'](bad))

if __name__=='__main__':unittest.main(verbosity=2)
