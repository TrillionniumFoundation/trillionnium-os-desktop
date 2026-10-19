"""Source guard for A06's deferred final CPU debit.

This is intentionally a narrow source contract.  The full scheduler and QEMU
tests remain the authority for runtime behavior; the guard prevents a future
cleanup from dropping the retained final-charge path. Behavioral regression
coverage lives in cpu/final_charge_regressions.rs and
cpu/owner_retention_regressions.rs and runs in real kernel ktest.
"""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
CPU_RS = ROOT / "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs"
CGROUP_RS = ROOT / "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs"
POSIX_RS = ROOT / "kernel/asterinas/kernel/core/src/process/posix_thread/mod.rs"
INODE_RS = ROOT / "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/inode.rs"
SCHED_RS = ROOT / "kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs"


class A06FinalAccountingSource(unittest.TestCase):
    def test_process_death_path_charges_thread_owned_snapshot(self):
        source = CPU_RS.read_text()
        start = source.index("impl CpuChargeOwner {")
        end = source.index("impl Clone for CpuChargeOwner", start)
        body = source[start:end]
        self.assertIn("thread.retained_cpu_charge_owner()", body)
        self.assertIn("thread.weak_process().upgrade()", body)
        self.assertLess(
            body.index("thread.retained_cpu_charge_owner()"),
            body.index("thread.weak_process().upgrade()"),
            "exit resumption must retain its incarnation before resolving a live Process",
        )
        self.assertIn("Self::from_cgroup(thread.cpu_cgroup())", body)
        self.assertIn("self.cpu.charge_bandwidth_hierarchy(from, until)", body)
        self.assertIn("CgroupSystem::singleton()", body)
        self.assertIn("guard.get().is_some() || !process.status().is_zombie()", body)
        scheduler = SCHED_RS.read_text()
        self.assertIn("bandwidth_owner: Option<CpuChargeOwner>", scheduler)
        start = scheduler.index("fn settle_bandwidth(&mut self, task: &Task,")
        end = scheduler.index("fn with_bandwidth_settled", start)
        settlement = scheduler[start:end]
        self.assertIn(
            "match (self.bandwidth_accounted_through_ns, now.boottime_ns)",
            settlement,
        )
        self.assertIn("let Some(owner) = &self.bandwidth_owner", settlement)
        self.assertLess(
            settlement.index("owner.charge(from, until)"),
            settlement.index("self.bandwidth_owner = CpuChargeOwner::for_task(task)"),
            "the retained owner must receive its settled nanoseconds before rebinding",
        )

    def test_migration_updates_all_live_thread_snapshots(self):
        source = CGROUP_RS.read_text()
        self.assertGreaterEqual(
            source.count("set_cpu_cgroup_for_tasks("),
            3,
            "node migration, fork inheritance, and root migration must update the snapshot",
        )
        self.assertIn("if !process.status().is_zombie()", source)
        self.assertIn("deferred scheduler", source)

    def test_zombie_final_debit_lease_blocks_cgroup_deletion(self):
        posix = POSIX_RS.read_text()
        cgroup = CGROUP_RS.read_text()
        inode = INODE_RS.read_text()
        self.assertIn("struct CpuCgroupLease", posix)
        self.assertIn("impl Drop for CpuCgroupLease", posix)
        self.assertIn("retain_cpu_charge_lease", posix)
        self.assertIn("release_cpu_charge_lease", posix)
        self.assertIn("cpu_charge_leases", cgroup)
        self.assertIn("deferred CPU accounting leases", cgroup)
        self.assertIn("CgroupMembership::write_lock()", inode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
