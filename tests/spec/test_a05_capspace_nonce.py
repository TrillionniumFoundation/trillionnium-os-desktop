"""A00/A05 host-only CapSpace identity and guest-test source contract.

This independent spec does not run the Asterinas kernel. Real QueryAbi fork/exec
behavior requires a fixed-nightly source build and QEMU guest verification.
"""
from pathlib import Path
import unittest

from rust_source_contract import block_after, positions, replace_once, require_sequence, rust_tokens


ROOT = Path(__file__).resolve().parents[2]
PROCESS = ROOT / "kernel/asterinas/kernel/core/src/process/process/mod.rs"
IMAGE = PROCESS.with_name("image.rs")
DEVICE = ROOT / "kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs"
GUEST = ROOT / "tests/kernel/control/queryabi_guest.c"
BOOT_IDENTITY = ROOT / "kernel/asterinas/kernel/core/src/util/boot_identity.rs"


def check_device_identity(source):
    tokens = rust_tokens(source)
    value = block_after(tokens, "fn process_session_id(")
    if len(positions(value, "process.hepta_capspace_session()?")) != 1:
        raise AssertionError("open must take exactly one locked Process image key")
    require_sequence(value, "let key = process.hepta_capspace_session()?;",
                     "original Process image owner")
    require_sequence(value, "Ok((image_space_id(key), key))", "one key for fd and wire identity")
    # procfs and HOS2 now intentionally share the canonical boot identity owner.
    # Pin that delegation as well as the full-width nonce; an arbitrary helper
    # called boot_id() must not satisfy the identity boundary on its own.
    boot = block_after(tokens, "fn boot_id(")
    if boot != rust_tokens("boot_identity::boot_id()"):
        raise AssertionError("HOS2 must use the canonical shared boot identity")
    identity = block_after(tokens, "fn image_space_id(")
    require_sequence(identity, "id[..8].copy_from_slice(&boot_id()[..8]);", "boot namespace")
    require_sequence(identity, "id[8..].copy_from_slice(&key.nonce().to_le_bytes());",
                     "full u64 image nonce")
    for method in (value, identity):
        if positions(method, "start_time()") or positions(method, "as u32"):
            raise AssertionError("PID/time truncation cannot replace the image nonce")
    require_sequence(tokens, "let (space_id, image_key) = process_session_id(&process)?;",
                     "open binds the authoritative key")
    session = block_after(tokens, "fn check_session(")
    require_sequence(session, "if !Arc::ptr_eq(&owner, &current)", "exact Process allocation")
    require_sequence(session, "current.check_hepta_capspace_session(self.image_key)",
                     "current image epoch and nonce")


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
        check_device_identity(DEVICE.read_text())
        image = IMAGE.read_text()
        self.assertIn("self.hepta_image.lock().check_session(key)", image)
        check = image.split("fn check_session(", 1)[1].split("fn begin_close(", 1)[0]
        for condition in ("self.phase != ImagePhase::Live", "self.nonce == 0",
                          "self.epoch != key.epoch", "self.nonce != key.nonce"):
            self.assertIn(condition, check)

    def test_shared_boot_owner_is_once_initialized_with_uuid_layout(self):
        tokens = rust_tokens(BOOT_IDENTITY.read_text())
        require_sequence(tokens, "static BOOT_ID: Once<[u8; 16]> = Once::new();",
                         "one stable boot owner")
        boot = block_after(tokens, "fn boot_id(")
        require_sequence(boot, "*BOOT_ID.call_once(||", "stable repeated observations")
        require_sequence(boot, "super::random::getrandom(&mut id);", "boot identity entropy")
        require_sequence(boot, "id[6] = (id[6] & 0x0f) | 0x40;", "UUID version")
        require_sequence(boot, "id[8] = (id[8] & 0x3f) | 0x80;", "UUID variant")

    def test_identity_guards_ignore_layout_but_reject_real_source_mutations(self):
        source = DEVICE.read_text()
        tokens = rust_tokens(source)
        check_device_identity("\n".join(tokens))
        changes = (
            ("boot_identity::boot_id()", "[0; 16]"),
            ("&boot_id()[..8]", "&[0; 8]"),
            ("&key.nonce().to_le_bytes()", "&(key.nonce() as u32).to_le_bytes()"),
            ("let key = process.hepta_capspace_session()?;",
             "let key = process.hepta_capspace_session()?; process.hepta_capspace_session()?;"),
            ("if !Arc::ptr_eq(&owner, &current)", "if false"),
            ("current.check_hepta_capspace_session(self.image_key)", "Ok(())"),
        )
        for before, after in changes:
            with self.subTest(boundary=before):
                self.assertEqual(len(positions(tokens, before)), 1)
                # Retain the removed text in a comment: it cannot fool the guard.
                mutant = " ".join(replace_once(tokens, before, after)) + " /* " + before + " */"
                with self.assertRaises(AssertionError):
                    check_device_identity(mutant)

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
