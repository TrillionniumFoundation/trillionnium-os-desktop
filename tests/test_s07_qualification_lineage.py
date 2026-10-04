"""Actual private Git objects test lineage metadata; no Servo execution claims."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools import verify_s07_qualification_lineage as lineage

ROOT = Path(__file__).resolve().parents[1]


class S07QualificationLineageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git('init', '-q')
        # Exact captured official commit/root-tree bytes, no remote access and
        # no complete historical checkout/runtime qualification from fixtures.
        golden = lineage.load(ROOT / 'contracts/golden/s07-historical-git-metadata.v1.json')
        self.assertEqual(set(golden), {'schema', 'scope', 'objects'})
        self.assertEqual(golden['schema'], 'trillionnium.s07-historical-git-metadata-fixture.v1')
        self.assertEqual(golden['scope'], 'raw_commit_and_root_tree_only_no_child_objects_runtime_or_ancestry_qualification')
        self.assertEqual(len(golden['objects']), 2)
        for item, kind, sha in zip(golden['objects'], ('commit', 'tree'),
                (lineage.HISTORICAL['commit'], lineage.HISTORICAL['tree'])):
            self.assertEqual(set(item), {'type', 'sha1', 'size', 'data_base64'})
            self.assertEqual(item['type'], kind)
            self.assertEqual(item['sha1'], sha)
            self.assertIs(type(item['size']), int)
            data = base64.b64decode(item['data_base64'], validate=True)
            self.assertEqual(len(data), item['size'])
            self.assertEqual(hashlib.sha1(f'{kind} {len(data)}\0'.encode() + data).hexdigest(), sha)
            created = subprocess.check_output(['git', '-C', str(self.root), 'hash-object', '-w', '-t', kind, '--stdin'], input=data).decode().strip()
            self.assertEqual(created, sha)
        self.write_contract(lineage.EXPECTED)
        self.manifest = json.loads((ROOT / lineage.MANIFEST).read_text())
        self.write_manifest(self.manifest)
        self.head = self.record('current source fixture')

    def git(self, *args):
        return subprocess.check_output([
            'git', '-C', str(self.root), '-c', 'user.name=Codex',
            '-c', 'user.email=codex@users.noreply.github.com', *args], text=True).strip()

    def write_contract(self, value):
        target = self.root / lineage.CONTRACT
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))

    def write_manifest(self, value):
        target = self.root / lineage.MANIFEST
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(value))

    def record(self, message):
        self.git('add', '-A')
        self.git('commit', '-q', '--allow-empty', '-m', message)
        return self.git('rev-parse', 'HEAD')

    def test_genuine_historical_metadata_cannot_claim_ancestry_or_execution(self):
        result = lineage.verify(self.root, 'exact-head', self.head)
        self.assertEqual(result['current']['commit'], self.head)
        self.assertEqual(result['historical_carrier'], {
            'commit': lineage.HISTORICAL['commit'], 'tree': lineage.HISTORICAL['tree'],
            'parents': lineage.HISTORICAL['parents']})
        self.assertEqual(result['status'], 'PASS_GIT_METADATA_AND_SOURCE_CONTRACT_ONLY')
        for name in ('actual_s06_execution_observed', 'actual_servo_execution_observed',
                     'historical_ancestry_asserted', 'installed_qualification', 'production_activation'):
            self.assertIs(result[name], False)

    def test_actual_merge_requires_exact_event_and_ordered_two_parents(self):
        base = self.head
        self.git('checkout', '-q', '-b', 'head')
        head = self.record('head independent change')
        self.git('checkout', '-q', '-b', 'base', base)
        base = self.record('base independent change')
        tree = self.git('rev-parse', 'HEAD^{tree}')
        merged = self.git('commit-tree', tree, '-p', base, '-p', head, '-m', 'prospective')
        self.git('reset', '--hard', merged)
        result = lineage.verify(self.root, 'prospective-merge', merged, base, head)
        self.assertEqual(result['current']['parents'], [base, head])
        with self.assertRaisesRegex(ValueError, 'parents'):
            lineage.verify(self.root, 'prospective-merge', merged, head, base)
        with self.assertRaisesRegex(ValueError, 'exact expected'):
            lineage.verify(self.root, 'prospective-merge', head, base, head)
        with self.assertRaisesRegex(ValueError, 'parents'):
            lineage.verify(self.root, 'prospective-merge', merged, None, head)
        self.git('reset', '--hard', head)
        with self.assertRaisesRegex(ValueError, 'parents'):
            lineage.verify(self.root, 'prospective-merge', head, base, head)

    def test_event_sha_is_complete_and_exact_mode_has_no_parent_assertions(self):
        for bad in (self.head[:12], self.head.upper(), 'HEAD', '0' * 40, True, 1):
            with self.subTest(identity=bad), self.assertRaises(ValueError):
                lineage.verify(self.root, 'exact-head', bad)
        with self.assertRaisesRegex(ValueError, 'parent assertions'):
            lineage.verify(self.root, 'exact-head', self.head, self.head, self.head)
        with self.assertRaisesRegex(ValueError, 'unknown'):
            lineage.verify(self.root, 'caller-runtime-pass', self.head)

    def test_dirty_actual_tracked_and_untracked_checkout_is_refused(self):
        (self.root / lineage.CONTRACT).write_text((self.root / lineage.CONTRACT).read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'not clean'):
            lineage.verify(self.root, 'exact-head', self.head)
        self.git('checkout', '--', lineage.CONTRACT)
        (self.root / 'untracked').write_text('actual untracked bytes')
        with self.assertRaisesRegex(ValueError, 'not clean'):
            lineage.verify(self.root, 'exact-head', self.head)

    def test_closed_nested_contract_types_and_claim_promotions_refused(self):
        for path, value in (
            (('status',), 'PRODUCTION_READY'),
            (('historical_carrier', 'commit'), self.head),
            (('historical_carrier', 'tree'), '0' * 40),
            (('historical_carrier', 'parents'), []),
            (('historical_carrier', 'repository_url'), 'https://example.invalid/other.git'),
            (('current_qualification', 'historical_ancestor_required'), True),
            (('current_qualification', 'external_expected_event_sha_required'), 1),
            (('current_qualification', 'servo_commit'), '0' * 40),
            (('non_claims', 'metadata_verifier_is_servo_execution'), True),
            (('non_claims', 'production_activation_or_release_authorized'), 0),
        ):
            with self.subTest(path=path):
                contract = copy.deepcopy(lineage.EXPECTED)
                target = contract
                for part in path[:-1]:
                    target = target[part]
                target[path[-1]] = value
                self.write_contract(contract)
                head = self.record('hostile contract')
                with self.assertRaises(ValueError):
                    lineage.verify(self.root, 'exact-head', head)
        self.write_contract(lineage.EXPECTED)
        for section in ('historical_carrier', 'current_qualification', 'non_claims'):
            contract = copy.deepcopy(lineage.EXPECTED)
            contract[section]['unknown_authority'] = True
            self.write_contract(contract)
            head = self.record('unknown field')
            with self.assertRaisesRegex(ValueError, 'unknown fields'):
                lineage.verify(self.root, 'exact-head', head)

    def test_manifest_lineage_and_original_identities_cannot_drift(self):
        for section, key, value in (
            (None, 'carrier_base_commit', self.head),
            (None, 'carrier_branch', 'another-branch'),
            (None, 'carrier_parent_binding', 'caller-reported-ancestry'),
            ('upstream', 'commit', '0' * 40),
            ('qualification_lineage', 'status', 'INSTALLED_READY'),
        ):
            manifest = copy.deepcopy(self.manifest)
            (manifest if section is None else manifest[section])[key] = value
            self.write_contract(lineage.EXPECTED)
            self.write_manifest(manifest)
            head = self.record('hostile manifest')
            with self.subTest(section=section, key=key), self.assertRaises(ValueError):
                lineage.verify(self.root, 'exact-head', head)

    def test_missing_historical_object_is_not_empty_success(self):
        sha = lineage.HISTORICAL['commit']
        (self.root / '.git/objects' / sha[:2] / sha[2:]).unlink()
        with self.assertRaises(subprocess.CalledProcessError):
            lineage.verify(self.root, 'exact-head', self.head)

    def test_duplicate_symlink_and_hardlink_contract_reads_refused(self):
        contract = self.root / lineage.CONTRACT
        raw = contract.read_text()
        contract.write_text(raw[:-1] + ',"status":"SOURCE_METADATA_AND_CI_CONTRACT_ONLY"}')
        head = self.record('duplicate contract member')
        with self.assertRaises(ValueError):
            lineage.verify(self.root, 'exact-head', head)
        contract.write_text(raw)
        self.record('restore')
        contract.rename(self.root / 'foreign.json')
        contract.symlink_to(self.root / 'foreign.json')
        head = self.record('symlink contract')
        with self.assertRaises((ValueError, OSError)):
            lineage.verify(self.root, 'exact-head', head)
        contract.unlink()
        contract.hardlink_to(self.root / 'foreign.json')
        head = self.record('hardlinked contract')
        with self.assertRaises((ValueError, OSError)):
            lineage.verify(self.root, 'exact-head', head)

    def test_cli_emits_no_partial_success_for_wrong_event(self):
        completed = subprocess.run(['python3', '-B', str(ROOT / 'tools/verify_s07_qualification_lineage.py'),
            '--root', str(self.root), '--mode', 'exact-head', '--expected-sha', '0' * 40],
            capture_output=True, text=True)
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stdout, '')
        completed = subprocess.run(['python3', '-B', str(ROOT / 'tools/verify_s07_qualification_lineage.py'),
            '--root', str(self.root), '--mode', 'exact-head', '--expected-sha', self.head],
            capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIs(json.loads(completed.stdout)['actual_servo_execution_observed'], False)

    def test_current_guard_bytes_and_complete_direct_dependency_filters_stay_bound(self):
        from tests.test_ci_absence_guards import blocks
        current = blocks('.github/workflows/s06-browser-actor.yml',
                         'Reconfirm sealed product API and claim ceiling')
        copied = blocks('.github/workflows/s07-servo-retained-node.yml',
                        'Verify current sealed S06 source and compile-fail boundary')
        # The line extractor includes inter-step YAML blank lines; compare the
        # actual literal block's clipped trailing newline, retaining code bytes.
        current = [body.rstrip('\n') + '\n' for body in current]
        copied = [body.rstrip('\n') + '\n' for body in copied]
        self.assertEqual(len(current), 2)
        self.assertEqual(current[0], current[1])
        self.assertEqual(len(copied), 2)
        self.assertEqual(copied[0], copied[1])
        self.assertTrue(copied[0].endswith(current[0].removeprefix('set -euo pipefail\n')))
        self.assertIn('RUSTUP_TOOLCHAIN=1.93.0 cargo test --locked -p hepta-browser-actor --doc', copied[0])
        self.assertIn('tests.test_s06_browser_actor tests.test_s06_contract_paths tests.test_s06_public_exports -v', copied[0])
        dependencies = ['tools/verify_s07_qualification_lineage.py',
            'contracts/s07-qualification-lineage.v1.json', 'tools/scan_s06_public_exports.py',
            'tests/test_s07_qualification_lineage.py', 'tests/test_s06_public_exports.py',
            'contracts/golden/s07-historical-git-metadata.v1.json',
            'tools/artifact_evidence.py', 'tools/browser_codec_reference_security.py',
            '.github/workflows/s06-browser-actor.yml']
        self.assertEqual(self.manifest['qualification']['lineage_sources'], dependencies)
        workflow = (ROOT / '.github/workflows/s07-servo-retained-node.yml').read_text()
        for path in dependencies:
            self.assertEqual(workflow.count('      - "' + path + '"'), 2, path)
        workflow = (ROOT / '.github/workflows/s06-browser-actor.yml').read_text()
        for path in ('tools/scan_s06_public_exports.py', 'tools/artifact_evidence.py',
                     'tools/browser_codec_reference_security.py'):
            self.assertEqual(workflow.count('      - "' + path + '"'), 2, path)


if __name__ == '__main__':
    unittest.main()
