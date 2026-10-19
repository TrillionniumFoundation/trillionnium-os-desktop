"""QEMU invocation and provenance guards; synthetic unit tests are NOT guest runs."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import gzip
import copy
import json
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("a04_qemu_replay",HERE/"replay_qemu.py")
replay=importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)

class QemuReplayPreflight(unittest.TestCase):
    def test_fixed_no_host_disk_no_network_tcg_command(self):
        argv=replay.command_for_qemu("/usr/bin/qemu-system-x86_64", "/seabios", "/kernel", "/image")
        self.assertIn("tcg", argv)
        self.assertIn("-nodefaults", argv)
        self.assertIn("-no-user-config", argv)
        self.assertIn("-no-reboot", argv)
        self.assertEqual(argv[argv.index("-smp")+1], "1")
        self.assertEqual(argv[argv.index("-m")+1], "512M")
        self.assertEqual(argv[argv.index("-append")+1], "earlycon console=ttyS0 loglevel=info --")
        self.assertNotIn("-drive", argv)
        self.assertNotIn("-netdev", argv)
        self.assertNotIn("-enable-kvm", argv)

    def test_false_kernel_or_firmware_rejected_before_guest_execution(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            kernel=root/"fake-kernel.gz"
            kernel.write_bytes(gzip.compress(b"not actually kernel",mtime=0))
            with self.assertRaisesRegex(ValueError,"kernel.*SHA"):
                replay.load_kernel(kernel)
            firmware=root/"firmware"
            firmware.write_bytes(b"not actual SeaBIOS")
            with self.assertRaisesRegex(ValueError,"SeaBIOS"):
                replay.check_firmware(firmware)

    def test_preflight_refuses_missing_qemu(self):
        with self.assertRaisesRegex(ValueError,"QEMU executable unavailable"):
            replay.preflight(Path("/missing"),Path("/missing"),Path("/missing"),None)

    def test_version_spoofing_qemu_binary_is_not_a_trusted_emulator(self):
        # Run an actual, independently written executable. Without the fixed
        # SHA check, this fake passed the old `-version` verification.
        with tempfile.TemporaryDirectory() as td:
            exe = Path(td) / "qemu-system-x86_64"
            exe.write_text('#!/bin/sh\nprintf "QEMU emulator version 8.2.2 (fake)\\n"\n')
            exe.chmod(0o755)
            with patch.object(replay, "check_firmware"), patch.object(
                    replay, "load_kernel", return_value=b"ELF"):
                with self.assertRaisesRegex(ValueError, "QEMU executable SHA-256 mismatch"):
                    replay.preflight(Path("/not_a_kernel.gz"), Path("/not_an_initramfs"),
                                     Path("/not_a_firmware"), exe)

    def test_qemu_digest_is_the_acceptance_artifact_sha(self):
        self.assertEqual(replay.A01_QEMU_SHA256,
                         "8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854")

    def test_c_elf_qualification_rejects_hidden_errno_divergence(self):
        reference = json.loads((HERE / "baselines/linux-debian13-x86_64.json").read_text())
        cases = [name for name, _, _ in replay.guest.reference_elf_cases(reference)]
        manifest = {"cases": cases}
        candidate = copy.deepcopy(reference)
        for name in reference["cases"]:
            if name not in cases:
                candidate["cases"][name] = {"status": "not_run"}
        candidate.update({"suite": "a04-linux-guest-differential",
                          "guest_execution_verified": True,
                          "guest_compatibility_passed": True,
                          "boot_evidence": {"a01_kernel_elf_sha256_matches": True,
                                            "a04_initramfs_sha256_matches": True,
                                            "qemu_exit_code": 33}})
        first = replay.differential.compare(reference, candidate)
        qualified = replay.qualify_c_elf_reference(reference, manifest, candidate, first)
        self.assertEqual(qualified["matched"], len(cases))
        self.assertEqual(first["verdict"], "incomplete")  # Python/Tokio still missing
        self.assertTrue(qualified["passed"])  # but exactly matched C ELF subset
        # Forged success: an app may exit 0 and report ok=true with errno wrong.
        divergent = copy.deepcopy(candidate)
        divergent["cases"]["dynamic.errno"]["facts"]["ENOENT"] = 38
        mismatch = replay.differential.compare(reference, divergent)
        self.assertEqual(mismatch["verdict"], "fail")
        self.assertFalse(replay.qualify_c_elf_reference(reference, manifest,
                                                        divergent, mismatch)["passed"])
        # The provenance must not come solely from copied facts / case JSON.
        no_boot = copy.deepcopy(candidate)
        no_boot["boot_evidence"]["qemu_exit_code"] = 65
        no_boot_diff = replay.differential.compare(reference, no_boot)
        self.assertFalse(replay.qualify_c_elf_reference(reference, manifest,
                                                        no_boot, no_boot_diff)["passed"])
        # Duplicate, missing and fabricated case manifests can never pass.
        self.assertFalse(replay.qualify_c_elf_reference(reference,
                         {"cases": cases + [cases[0]]}, candidate, first)["passed"])
        self.assertFalse(replay.qualify_c_elf_reference(reference,
                         {"cases": cases[:-1]}, candidate, first)["passed"])

    def test_reference_and_rootfs_manifest_are_byte_pinned(self):
        reference = HERE / "baselines/linux-debian13-x86_64.json"
        manifest = HERE.parents[2] / "support/rootfs/manifest-debian13-x86_64.json"
        fixed = replay.load_fixed_reference(reference, manifest)
        self.assertEqual(len(replay.guest.reference_elf_cases(fixed)), 28)
        with tempfile.TemporaryDirectory() as td:
            mutated = Path(td) / "mutated-reference.json"
            data = copy.deepcopy(fixed)
            data["cases"]["static.smoke"]["status"] = "not_run"
            mutated.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "reference SHA-256 mismatch"):
                replay.load_fixed_reference(mutated, manifest)
            modified_manifest = Path(td) / "manifest.json"
            modified_manifest.write_text(manifest.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "rootfs manifest SHA-256 mismatch"):
                replay.load_fixed_reference(reference, modified_manifest)

    def test_c_elf_qualification_cannot_shrink_the_case_denominator(self):
        reference = json.loads((HERE / "baselines/linux-debian13-x86_64.json").read_text())
        reduced = copy.deepcopy(reference)
        reduced["cases"]["static.smoke"]["status"] = "not_run"
        expected = [name for name, _, _ in replay.guest.reference_elf_cases(reduced)]
        fake_candidate = {"cases": {name: {"status": "pass", "exit_code": obs["exit_code"],
                                     "facts": obs["facts"]}
                                    for name, obs in reduced["cases"].items() if name in expected},
                          "guest_execution_verified": True, "guest_compatibility_passed": True}
        fake_diff = {"matched": expected, "blocked": [], "differences": [],
                     "kernel_boot_verified": True}
        self.assertFalse(replay.qualify_c_elf_reference(reduced, {"cases": expected},
                                                        fake_candidate, fake_diff)["passed"])

    def test_status_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"status.json"
            replay.write_json(p,{"qualification":"blocked"})
            with self.assertRaisesRegex(ValueError,"refusing to overwrite"):
                replay.write_json(p,{"qualification":"pass"})

if __name__=="__main__":
    unittest.main()
