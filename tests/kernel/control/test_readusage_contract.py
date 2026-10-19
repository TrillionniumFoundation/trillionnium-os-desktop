"""Fail-closed source contract for the unimplemented A05 ReadUsage operation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[3]
CONTROL = ROOT / "kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs"
CPU_NATIVE = ROOT / "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs"
IMAGE = ROOT / "kernel/asterinas/kernel/core/src/process/process/image.rs"
ABI = ROOT / "libs/os-abi/src/lib.rs"


class ReadUsageContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.control = CONTROL.read_text()
        cls.cpu_native = CPU_NATIVE.read_text()
        cls.image = IMAGE.read_text()
        cls.abi = ABI.read_text()

    def test_queryabi_is_the_only_advertised_operation(self):
        self.assertIn("supported_ops: 1u64 << Opcode::QueryAbi.as_u16()", self.control)
        self.assertIn("request.opcode != Opcode::QueryAbi", self.control)
        self.assertIn('Errno::EOPNOTSUPP', self.control)
        self.assertIn("recognized HOS2 resource operation not implemented", self.control)

    def test_known_resource_operations_remain_explicitly_fail_closed(self):
        for opcode in ("ReadUsage", "InstallBudget", "QueryDelivery", "RetireThrough"):
            self.assertIn(f"Opcode::{opcode}", self.abi)
        self.assertNotIn("ResponsePayload::ReadUsage", self.control)
        self.assertNotIn("NativeGrant", self.control)
        self.assertNotIn("reserve_native", self.control)
        self.assertNotIn("execute_native_reserved", self.control)

    def test_process_image_is_identity_only_and_exec_fences_old_sessions(self):
        self.assertIn("process.hepta_capspace_session()", self.control)
        self.assertIn("Arc::ptr_eq(&owner, &current)", self.control)
        self.assertIn("current.check_hepta_capspace_session(self.image_key)", self.control)
        self.assertIn("pub(crate) fn hepta_capspace_session", self.image)
        self.assertIn("pub(crate) fn check_hepta_capspace_session", self.image)
        self.assertIn("pub(in crate::process) fn commit_hepta_exec_image", self.image)

    def test_real_cpu_owner_seam_stays_private_and_n0_guarded(self):
        self.assertIn("fn read_native_cpu_usage_for_owner", self.cpu_native)
        self.assertIn("fn bind_native_cpu_once_for_owner", self.cpu_native)
        self.assertIn("ostd::cpu::all_cpus().count() != 1", self.cpu_native)
        self.assertIn("Arc::ptr_eq(&current.get(), owner)", self.cpu_native)
        self.assertIn("control.max.lock().sample_usage(now)", self.cpu_native)
        self.assertIn("Production bootstrap does not call this seam yet", self.cpu_native)


if __name__ == "__main__":
    unittest.main()
