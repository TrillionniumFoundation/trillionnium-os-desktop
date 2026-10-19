"""Host-only provenance/acceptance fixtures; no kernel, C ioctl or QEMU execution."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_queryabi_candidate_guest as candidate


def n0_argv(kernel="/tmp/kernel", initrd="/tmp/initrd", bios="/tmp/bios"):
    return ["qemu-system-x86_64", "-kernel", kernel, "-initrd", initrd, "-append", "console=ttyS0 --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", bios, "-m", "512M", "-smp", "1",
            "-nodefaults", "-no-user-config", "-no-reboot", "-nographic", "-display", "none", "-monitor", "none",
            "-chardev", "stdio,id=serial,signal=off,logfile=qemu.log", "-serial", "chardev:serial",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]


class SourceSnapshot(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="g1-source-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q")
        (self.root / "source.txt").write_text("reviewed source\n")
        (self.root / "link").symlink_to("source.txt")
        self.git("add", "source.txt", "link")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        self.head, self.tree = self.git("rev-parse", "HEAD"), self.git("rev-parse", "HEAD^{tree}")

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.root, stderr=subprocess.STDOUT).decode().strip()

    def test_clean_real_git_bytes_and_reviewed_identity(self):
        snapshot = candidate.source_snapshot(self.root, self.head, self.tree)
        self.assertEqual(set(snapshot["files"]), {"source.txt", "link"})
        for head, tree in (("0" * 40, self.tree), (self.head, "0" * 40)):
            with self.assertRaises(ValueError):
                candidate.source_snapshot(self.root, head, tree)

    def test_changed_bytes_hidden_from_git_status_still_fail(self):
        self.git("update-index", "--assume-unchanged", "source.txt")
        (self.root / "source.txt").write_text("changed bytes\n")
        self.assertEqual(self.git("status", "--porcelain"), "")
        with self.assertRaisesRegex(ValueError, "byte mismatch"):
            candidate.source_snapshot(self.root, self.head, self.tree)

    def test_untracked_source_input_is_not_omitted_from_admission(self):
        (self.root / "unreviewed.rs").write_text("// untracked compile input\n")
        with self.assertRaisesRegex(ValueError, "untracked inputs"):
            candidate.source_snapshot(self.root, self.head, self.tree)

    def test_changed_symlink_target_hidden_from_git_status_fails(self):
        self.git("update-index", "--assume-unchanged", "link")
        (self.root / "link").unlink()
        (self.root / "link").symlink_to("elsewhere")
        with self.assertRaises(ValueError):
            candidate.source_snapshot(self.root, self.head, self.tree)

    def test_executable_mode_drift_is_not_hidden_by_git_filemode_setting(self):
        self.git("config", "core.filemode", "false")
        (self.root / "source.txt").chmod(0o755)
        with self.assertRaisesRegex(ValueError, "mode mismatch"):
            candidate.source_snapshot(self.root, self.head, self.tree)


class CandidateAcceptance(unittest.TestCase):
    def test_n0_profile_cannot_add_hardware_or_change_cpu(self):
        argv = n0_argv()
        self.assertEqual(candidate.verify_n0_argv(argv)["-smp"], "1")
        mutations = [argv + ["-drive", "file=host.img"], argv + ["-nodefaults"], argv[:-2]]
        for option, value in (("-smp", "2"), ("-accel", "kvm"), ("-device", "virtio-net-pci")):
            changed = argv.copy()
            changed[changed.index(option) + 1] = value
            mutations.append(changed)
        for changed in mutations:
            with self.subTest(argv=changed), self.assertRaises(ValueError):
                candidate.verify_n0_argv(changed)

    def test_all_guest_markers_require_exact_single_root_completion(self):
        markers = (*candidate.replay.REQUIRED_SECURITY_MARKERS, candidate.replay.EXPECTED_SUCCESS,
                   *candidate.OP_MARKERS, candidate.CANDIDATE_MARKER, candidate.FINAL_BOOT_MARKER)
        raw = ("\n".join(markers) + "\n").encode()
        self.assertTrue(candidate.evaluate_guest(raw, 33, False)["passed"])
        for marker in markers:
            for changed in (raw.replace(marker.encode(), b"missing"), raw + marker.encode() + b"\n"):
                with self.subTest(marker=marker):
                    self.assertFalse(candidate.evaluate_guest(changed, 33, False)["passed"])
        reversed_root = "\n".join((*markers[:-6], *reversed(markers[-6:]))).encode()
        self.assertFalse(candidate.evaluate_guest(reversed_root, 33, False)["passed"])
        for code, timeout in ((65, False), (33, True), (True, False)):
            self.assertFalse(candidate.evaluate_guest(raw, code, timeout)["passed"])
        self.assertFalse(candidate.evaluate_guest(raw + b"panicked at\n", 33, False)["passed"])

    def test_boot_receipt_rejects_source_lock_and_artifact_substitution(self):
        with tempfile.TemporaryDirectory(prefix="g1-boot-fixture-") as temporary:
            root = Path(temporary)
            boot = root / "boot"
            boot.mkdir()
            target = root / "target"
            lock = target / "osdk/asterinas-run-base/Cargo.lock"
            lock.parent.mkdir(parents=True)
            # This is a parser fixture only, not an admitted real dependency graph.
            lock.write_text("version = 4\n" + "\n".join(
                f'[[package]]\nname = "fixture-{i}"\nversion = "0.1.0"' for i in range(204)))
            minimal = root / "support/build/minimal/Cargo.lock"
            minimal.parent.mkdir(parents=True)
            minimal.write_bytes(lock.read_bytes())
            raw_kernel = bytearray(64)
            raw_kernel[:6] = b"\x7fELF\x02\x01"
            raw_kernel[18:20] = b"\x03\x00"
            paths = {"-kernel": boot / "kernel", "-initrd": boot / "initramfs.cpio.gz", "-bios": boot / "bios"}
            for option, content in (("-kernel", raw_kernel), ("-initrd", b"fixture initrd"), ("-bios", b"fixture bios")):
                paths[option].write_bytes(content)
            serial = "\n".join(candidate.boot_check.MARKERS).encode()
            (boot / "serial.log").write_bytes(serial)
            qemu = {"argv": n0_argv(*(str(paths[o]) for o in ("-kernel", "-initrd", "-bios"))), "cwd": str(root),
                    "raw_exit_code": 33, "timed_out": False, "serial_sha256": candidate.replay.digest(serial),
                    "artifacts": {o: {"path": str(p), "size": p.stat().st_size, "sha256": candidate.replay.digest(p.read_bytes())}
                                  for o, p in paths.items()}}
            candidate.save_json(boot / "qemu.json", qemu)
            snapshot = {"head": "a" * 40}
            (boot / "environment.log").write_text(snapshot["head"] + "\n")
            for name in ("make-exit-code.txt", "log-exit-code.txt", "run-exit-code.txt"):
                (boot / name).write_text("0\n")
            command = ["make", "-C", str(root / "kernel/asterinas"), "-f", "Makefile", "-f", str(root / "support/build/minimal.mk"),
                       "run_kernel", "CARGO_OSDK=/fixture/cargo-osdk", f"A01_INITRAMFS={paths['-initrd']}",
                       f"A01_QEMU_WRAPPER={root / 'support/build/record-qemu.py'}", "TARGET_ARCH=x86_64", "SMP=1", "MEM=512M",
                       "ENABLE_KVM=0", "BOOT_PROTOCOL=multiboot", "INITRAMFS=on", "AUTO_TEST=none"]
            (boot / "command.sh").write_text(candidate.shlex.join(command))
            gate = b'{"passed": true}'
            (boot / "source-inputs.json").write_bytes(gate)
            with mock.patch.object(candidate.subprocess, "check_output", return_value=gate), \
                    mock.patch.object(candidate.replay, "SEABIOS_SHA", qemu["artifacts"]["-bios"]["sha256"]):
                candidate.verify_product_boot(boot, root, snapshot, target)
                for name in ("environment.log", "source-inputs.json", "command.sh", "initramfs.cpio.gz"):
                    p = boot / name
                    original = p.read_bytes()
                    p.write_bytes(b"changed")
                    with self.subTest(input=name), self.assertRaises((ValueError, json.JSONDecodeError)):
                        candidate.verify_product_boot(boot, root, snapshot, target)
                    p.write_bytes(original)
                lock.write_text("changed")
                with self.assertRaisesRegex(ValueError, "generated lock"):
                    candidate.verify_product_boot(boot, root, snapshot, target)


if __name__ == "__main__":
    unittest.main()
