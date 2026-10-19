"""Verify public ptrace evidence belongs to the CURRENT fixed ELF/rootfs profile.

This checks evidence integrity and scope, not actual QEMU or Hepta execution.
The ptrace event counts are observations, not stable ABI performance targets.
"""
import hashlib
import json
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FrozenPtraceProvenance(unittest.TestCase):
    def test_real_numeric_trace_inputs_and_current_elf_scope(self):
        reference_file = HERE/'baselines/linux-debian13-x86_64.json'
        manifest_file = ROOT/'support/rootfs/manifest-debian13-x86_64.json'
        tracer = HERE/'ptrace_trace.c'
        trace = json.loads((HERE/'baselines/linux-debian13-x86_64-ptrace.json').read_text())
        reference = json.loads(reference_file.read_text())
        self.assertEqual(trace['reference_sha256'], digest(reference_file))
        self.assertEqual(trace['rootfs_manifest_sha256'], digest(manifest_file))
        self.assertEqual(trace['source_sha256'], digest(tracer))
        self.assertFalse(trace['kernel_guest_verified'])
        self.assertFalse(trace['hepta_profile_verified'])
        self.assertTrue(trace['trace_private'])
        expected = {name for name in reference['cases']
                    if name.startswith(('dynamic.', 'static.', 'sqlite_dynamic.', 'sqlite_static.'))}
        self.assertEqual(set(trace['cases']), expected)
        self.assertEqual(trace['counts'], {'pass': len(expected), 'fail': 0, 'blocked': 0})
        for entry in trace['cases'].values():
            self.assertEqual(entry['status'], 'pass')
            self.assertGreater(entry['syscall_events'], 0)
            self.assertRegex(entry['raw_trace_sha256'], r'^[0-9a-f]{64}$')
        complete = sum(c['syscall_events'] for c in trace['cases'].values())
        self.assertEqual(complete, sum(c['count'] for c in trace['aggregate_syscalls']))
        self.assertEqual(len(trace['aggregate_syscalls']), 62)
        seen = {c['name'] for c in trace['aggregate_syscalls']}
        self.assertTrue({'accept4', 'getsockopt', 'bind', 'set_robust_list', 'futex'}.issubset(seen))
        self.assertNotIn(512, {c['errno'] for c in trace['aggregate_syscall_errno']})
        self.assertTrue(all(c['internal_code'] in range(512, 517)
                            for c in trace['aggregate_internal_restarts']))


if __name__ == '__main__':
    unittest.main()
