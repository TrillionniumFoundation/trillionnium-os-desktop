"""Source guard for A06's deferred final CPU debit.

This is intentionally a narrow source contract.  The full scheduler and QEMU
tests remain the authority for runtime behavior; the guard prevents a future
cleanup from reintroducing the known Weak<Process> early-return hole.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CPU_RS = ROOT / "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs"
CGROUP_RS = ROOT / "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs"


class A06FinalAccountingSource(unittest.TestCase):
    def test_process_death_path_charges_thread_owned_snapshot(self):
        source = CPU_RS.read_text()
        start = source.index("pub(crate) fn charge_task_cpu")
        body = source[start:]
        self.assertIn("thread.weak_process().upgrade()", body)
        self.assertIn("if let Some(cgroup) = thread.cpu_cgroup()", body)
        self.assertIn("charge_bandwidth_hierarchy(from, until)", body)
        self.assertIn("CgroupSystem::singleton().controller().cpu.read()", body)
        # The Weak<Process> failure must not immediately return before the
        # fallback charge is attempted.
        failure = body.index("let Some(process) = thread.weak_process().upgrade() else")
        fallback = body.index("thread.cpu_cgroup()", failure)
        self.assertLess(failure, fallback)

    def test_migration_updates_all_live_thread_snapshots(self):
        source = CGROUP_RS.read_text()
        self.assertGreaterEqual(
            source.count("set_cpu_cgroup_for_tasks("),
            3,
            "node migration, fork inheritance, and root migration must update the snapshot",
        )
        self.assertIn("if !process.status().is_zombie()", source)
        self.assertIn("deferred scheduler", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
