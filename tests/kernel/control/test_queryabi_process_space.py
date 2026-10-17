"""Regression for boot-local QueryAbi identity after PID/start-time reuse.

CPU-only source/identity contract. It does not simulate actual kernel process
allocation or prove CapSpace authorization. Run the real fixed-nightly/QEMU
fork/exec tests independently before merging the A05 owner patch.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROCESS = ROOT / "kernel/asterinas/kernel/core/src/process/process/mod.rs"
DEVICE = ROOT / "kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs"


def legacy_space(boot8, pid, start_jiffies):
    return (boot8 + pid.to_bytes(4, "little")
            + (start_jiffies & 0xFFFFFFFF).to_bytes(4, "little"))


def fixed_space(boot8, unique_process_number):
    return boot8 + unique_process_number.to_bytes(8, "little")


class ProcessSpaceIdentity(unittest.TestCase):
    def test_old_pid_start_truncation_collides_after_32bit_wrap(self):
        boot = bytes(range(8))
        self.assertEqual(
            legacy_space(boot, 123, 12345),
            legacy_space(boot, 123, 2**32 + 12345),
        )
        # A unique per-Process number cannot collide merely because a PID or
        # a start-time low32 value repeats in the same boot.
        self.assertNotEqual(fixed_space(boot, 1), fixed_space(boot, 2))

    def test_source_allocates_fenced_nonwrapping_process_sequence(self):
        source = PROCESS.read_text(encoding="utf-8")
        self.assertIn("static NEXT_HEPTA_PROCESS_SPACE: AtomicU64 = AtomicU64::new(1)", source)
        self.assertIn("hepta_process_space: AtomicU64::new(0)", source)
        self.assertIn("next.checked_add(1)", source)
        self.assertIn("self.hepta_process_space.compare_exchange(", source)
        self.assertIn("Errno::ENOSPC", source)

    def test_wire_identity_never_truncates_process_start_time(self):
        source = DEVICE.read_text(encoding="utf-8")
        self.assertIn("process.hepta_process_space()?.to_le_bytes()", source)
        self.assertNotIn("process.start_time().as_u64() as u32", source)
        self.assertIn("space_id: process_session_id(&process)?", source)
        self.assertIn("self.check_session()?", source)


if __name__ == "__main__":
    unittest.main()
