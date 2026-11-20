"""Finite release admission controls; these do not build or qualify binaries."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('release19_under_test', HERE / 'run_release.py')
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)
CI = None
LEGACY = None
INVENTORY = None


class ReleaseAdmissionTests(unittest.TestCase):
    def test_original_19_and_49_rosters_remain_complete(self):
        tests = R.expected_targets(R.fixed(LEGACY / 'EXPECTED-TARGETS.json', R.LEGACY_PINS['EXPECTED-TARGETS.json']), 49)
        bins = R.expected_targets(R.fixed(LEGACY / 'EXPECTED-BINS.json', R.LEGACY_PINS['EXPECTED-BINS.json']), 19)
        self.assertEqual(len({key[0] for key in tests}), 28)
        self.assertEqual(len(bins), 19)
        self.assertTrue(set(bins) <= set(tests))

    def test_omitted_or_duplicated_original_target_is_rejected(self):
        rows = json.loads(R.regular(LEGACY / 'EXPECTED-BINS.json'))
        for changed in (rows[:-1], [*rows[:-1], rows[0]]):
            with self.subTest(count=len(changed)), self.assertRaises(ValueError):
                R.expected_targets(json.dumps(changed).encode(), 19)

    def test_historical_packet_and_current_packet_remain_distinct(self):
        manifest = R.verify_packet(INVENTORY)
        self.assertEqual(manifest['source']['tree'], R.SOURCE_TREE)
        self.assertEqual(manifest['source']['files'], 2352)
        self.assertNotEqual(R.LEGACY_INVENTORY, R.LEAF_INVENTORY)
        with self.assertRaises(ValueError):
            R.verify_packet('0' * 64)

    def test_missing_extra_and_corrupted_packet_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'packet'
            shutil.copytree(HERE, root)
            original = (root / 'README.md').read_bytes()
            (root / 'README.md').unlink()
            with self.assertRaises(ValueError):
                R.verify_packet(INVENTORY, root)
            (root / 'README.md').write_bytes(original)
            (root / 'unexpected').write_bytes(b'extra')
            with self.assertRaises(ValueError):
                R.verify_packet(INVENTORY, root)
            (root / 'unexpected').unlink()
            (root / 'README.md').write_bytes(original[:-1] + b'!')
            with self.assertRaises(ValueError):
                R.verify_packet(INVENTORY, root)

    def test_cargo_profile_and_compiler_injection_are_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            env = R.clean_environment({'PATH': '/untrusted', 'CARGO_PROFILE_RELEASE_OPT_LEVEL': '0',
                'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS': '--cfg test',
                'RUSTFLAGS': '--cfg test', 'RUSTC_WRAPPER': '/untrusted/wrapper', 'LD_PRELOAD': '/untrusted.so',
                'CFLAGS': '-O0', 'MAKEFLAGS': '-j32', 'CC': '/untrusted/cc'}, Path(directory), Path('/trusted/cargo/bin'))
            for key in ('CARGO_PROFILE_RELEASE_OPT_LEVEL', 'CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_RUSTFLAGS',
                        'RUSTFLAGS', 'RUSTC_WRAPPER', 'LD_PRELOAD', 'CFLAGS', 'MAKEFLAGS'):
                self.assertNotIn(key, env)
            self.assertEqual(env['CC'], '/usr/bin/x86_64-linux-gnu-gcc-13')
            self.assertEqual(env['CARGO_BUILD_JOBS'], '1')
            self.assertEqual(env['RAYON_NUM_THREADS'], '1')
            self.assertNotIn('/untrusted', env['PATH'])

    def test_whole_build_budget_cannot_exceed_1200_seconds_or_restart_job(self):
        start = 10**18
        end = start + R.JOB_INTERVAL_SECONDS * 10**9
        self.assertEqual(R.admitted_budget(start, end, start), 1200)
        self.assertEqual(R.admitted_budget(start, end, end - 300 * 10**9), 240)
        for now, deadline in ((end, end), (start - 1, end), (start, end + 10**9), (end - 100 * 10**9, end)):
            with self.subTest(now=now, deadline=deadline), self.assertRaises(ValueError):
                R.admitted_budget(start, deadline, now)

    def test_each_command_preserves_the_final_retirement_window(self):
        self.assertEqual(R.command_timeout(1200, 600, 0), 600)
        self.assertEqual(R.command_timeout(1200, 600, 1000), 140)
        for maximum, now in ((601, 0), (0, 0), (600, 1140), (600, 1201)):
            with self.subTest(maximum=maximum, now=now), self.assertRaises(ValueError):
                R.command_timeout(1200, maximum, now)

    def cargo_fixture(self, directory):
        root = Path(directory)
        producer, target = root / 'producer', root / 'target'
        source = producer / 'src' / 'main.rs'
        source.parent.mkdir(parents=True)
        source.write_text('fn main() {}\n')
        expected = {('example', 'example'): {'package': 'example', 'target': 'example', 'kind': ['bin'],
            'source_path': 'src/main.rs', 'required_features': [], 'test': True}}
        item = {'reason': 'compiler-artifact', 'package_id': 'example-id',
            'target': {'name': 'example', 'kind': ['bin'], 'src_path': str(source), 'test': True},
            'profile': {'test': False}, 'fresh': False, 'executable': str(target / 'release' / 'example')}
        return producer, target, expected, item

    def test_original_artifact_gate_rejects_fresh_cache_missing_and_extra_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            producer, target, expected, item = self.cargo_fixture(directory)
            def parse(items):
                raw = ''.join(json.dumps(row) + '\n' for row in [*items, {'reason': 'build-finished', 'success': True}]).encode()
                return CI.artifacts(raw, {'example-id': 'example'}, producer, target, expected, False)
            self.assertEqual(set(parse([item])), set(expected))
            for changed in ([], [dict(item, fresh=True)], [item, item]):
                with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                    parse(changed)

    def test_original_artifact_gate_rejects_debug_output_or_test_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            producer, target, expected, item = self.cargo_fixture(directory)
            for changed in (dict(item, executable=str(target / 'debug' / 'example')),
                            dict(item, profile={'test': True})):
                raw = (json.dumps(changed) + '\n' + json.dumps({'reason': 'build-finished', 'success': True}) + '\n').encode()
                with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                    CI.artifacts(raw, {'example-id': 'example'}, producer, target, expected, False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--legacy-packet', type=Path, required=True)
    parser.add_argument('--inventory-sha256', required=True)
    args, rest = parser.parse_known_args()
    LEGACY = args.legacy_packet.absolute()
    INVENTORY = args.inventory_sha256
    CI = R.load_legacy(LEGACY)
    unittest.main(argv=[__file__, *rest])
