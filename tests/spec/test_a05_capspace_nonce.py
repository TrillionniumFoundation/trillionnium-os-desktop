"""A00/A05 host-only CapSpace identity and guest-test source contract.

This independent spec does not run the Asterinas kernel. Real QueryAbi fork/exec
behavior requires a fixed-nightly source build and QEMU guest verification.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PROCESS = ROOT / "kernel/asterinas/kernel/core/src/process/process/mod.rs"
IMAGE = PROCESS.with_name("image.rs")
DEVICE = ROOT / "kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs"
GUEST = ROOT / "tests/kernel/control/queryabi_guest.c"


class CapSpaceIdentityContract(unittest.TestCase):
    def test_old_pid_and_32bit_jiffy_identity_would_alias(self):
        boot = bytes.fromhex("0123456789abcdef" * 2)
        pid = 1234
        tick = 42
        old = lambda when: (
            boot[:8] + pid.to_bytes(4, "little")
            + (when & 0xFFFFFFFF).to_bytes(4, "little")
        )
        self.assertEqual(old(tick), old(tick + (1 << 32)))

        new = lambda nonce: boot[:8] + nonce.to_bytes(8, "little")
        for value in (1, 2, 1 << 32, (1 << 64) - 1):
            self.assertEqual(len(new(value)), 16)
            self.assertNotEqual(new(value), bytes(16))
        self.assertEqual(len({new(1), new(2), new(1 << 32), new((1 << 64) - 1)}), 4)

    def test_process_uses_checked_unique_nonwrapping_image_nonce(self):
        process = PROCESS.read_text()
        source = IMAGE.read_text()
        self.assertIn("static NEXT_HEPTA_CAPSPACE_NONCE: AtomicU64 = AtomicU64::new(1)", source)
        self.assertIn("hepta_image: Mutex<ProcessImageState>", process)
        self.assertIn("hepta_image: Mutex::new(ProcessImageState::new())", process)
        self.assertNotIn("hepta_exec_epoch: AtomicU64", process)
        method = source.split("fn session(", 1)[1].split("fn check_session(", 1)[0]
        self.assertRegex(method, r"fetch_update\(\s*Ordering::AcqRel,\s*Ordering::Acquire,")
        self.assertIn("current.checked_add(1)", method)
        self.assertIn("Errno::ENOSPC", method)
        self.assertIn("self.phase != ImagePhase::Live", method)
        self.assertIn("self.phase = ImagePhase::Closed", method)
        commit = source.split("fn commit_exec(", 1)[1].split("fn claim_unprepared_run(", 1)[0]
        self.assertRegex(commit, r"self\s*\.epoch\s*\.checked_add\(1\)")
        self.assertIn("Errno::EOVERFLOW", commit)
        self.assertIn("self.nonce = 0", commit)

    def test_open_uses_one_locked_image_key_and_no_truncated_ticks(self):
        source = DEVICE.read_text()
        value = source.split("fn process_session_id(", 1)[1].split("\n}", 1)[0]
        self.assertIn("process.hepta_capspace_session()?", value)
        self.assertIn("key.nonce().to_le_bytes()", value)
        self.assertNotIn("start_time()", value)
        self.assertNotIn("as u32", value)
        self.assertIn("let (space_id, image_key) = process_session_id(&process)?", source)
        self.assertIn("Arc::ptr_eq(&owner, &current)", source)
        self.assertIn("current.check_hepta_capspace_session(self.image_key)", source)
        image = IMAGE.read_text()
        self.assertIn("self.hepta_image.lock().check_session(key)", image)
        check = image.split("fn check_session(", 1)[1].split("fn begin_close(", 1)[0]
        for condition in ("self.phase != ImagePhase::Live", "self.nonce == 0",
                          "self.epoch != key.epoch", "self.nonce != key.nonce"):
            self.assertIn(condition, check)

    def test_guest_asserts_fresh_child_and_exec_images_do_not_reuse_id(self):
        source = GUEST.read_text()
        self.assertIn("HEPTA_FORK_CAPSPACE_DISTINCT", source)
        self.assertIn("HEPTA_EXEC_CAPSPACE_ROTATED", source)
        self.assertIn("exec_capspace_reused", source)
        self.assertIn("fork_fresh_capspace_alias", source)
        self.assertIn("HEPTA_FORK_INHERITED_FD_DENIED", source)
        self.assertIn("HEPTA_EXEC_EPOCH_DENIED", source)


if __name__ == "__main__":
    unittest.main()
