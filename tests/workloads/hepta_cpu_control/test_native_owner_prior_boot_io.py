"""Host transport tests only; no QEMU, Hepta or native outcome is simulated."""
import hashlib
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest

import native_owner_prior_boot_io as transport
import native_owner_inputs as inputs


class ActualTwoBootTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.image = self.root / "state.raw"
        with self.image.open("xb") as output:
            output.truncate(transport.original.STATE_BYTES)
        mkfs = shutil.which("mkfs.ext2")
        if mkfs is None:
            self.fail("actual host mkfs.ext2 is required for this transport-only test")
        subprocess.run([mkfs, "-F", "-q", "-b", "4096", "-I", "256", "-m", "0", "-O", "none,filetype",
                        str(self.image)], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.digest = inputs.sha(self.image)

    def tearDown(self):
        self.temp.cleanup()

    def test_identical_copied_bytes_cannot_replace_the_physical_disk_between_boots(self):
        with transport.SameStateDisk(self.image, self.digest) as disk:
            replacement = self.root / "replacement.raw"
            shutil.copyfile(self.image, replacement)
            self.assertEqual(inputs.sha(replacement), self.digest)
            os.replace(replacement, self.image)
            with self.assertRaisesRegex(ValueError, "replace, copy, resize, alias or redirect"):
                disk.observe(self.digest)

    def test_alias_or_changed_stopped_bytes_are_refused(self):
        with transport.SameStateDisk(self.image, self.digest) as disk:
            alias = self.root / "hardlink.raw"
            os.link(self.image, alias)
            with self.assertRaises(ValueError):
                disk.observe(self.digest)
            alias.unlink()
            with self.image.open("r+b") as stream:
                stream.seek(transport.original.STATE_BYTES - 1)
                stream.write(b"\x01")
            with self.assertRaisesRegex(ValueError, "state bytes changed"):
                disk.observe(self.digest)

    def test_real_host_child_is_killed_after_its_observed_line_without_any_native_claim(self):
        # This ordinary host child only exercises pipe delivery and SIGKILL.
        # Its bytes are not a Hepta envelope, terminal, QEMU log or receipt.
        child = self.root / "host_transport_child"
        meta = self.image.stat()
        child.write_text("#!/usr/bin/python3\nimport os, signal, sys\n"
                         "drive=sys.argv[sys.argv.index('-drive')+1].split('file=',1)[1]\n"
                         "fd=os.open(drive,os.O_RDWR); meta=os.fstat(fd)\n"
                         f"assert (meta.st_dev,meta.st_ino)==({meta.st_dev},{meta.st_ino})\n"
                         "print('HOST_TRANSPORT_CUT', flush=True)\nsignal.pause()\n")
        child.chmod(0o555)
        identity = {"path": str(child), "bytes": child.stat().st_size, "sha256": inputs.sha(child)}
        boot = self.root / "boot-1"
        boot.mkdir()
        for target in (self.root / "product-kernel.elf", self.root / "bios.bin", boot / "initramfs.cpio.gz"):
            target.write_bytes(b"host-transport-input-only\n")
        with transport.SameStateDisk(self.image, self.digest) as disk:
            command = transport.qemu_argv(child, self.root, boot, disk)
            raw, result = transport.run_until_actual_cut(command, boot, 5, identity, disk,
                lambda line: {"transport_test_only": True} if line == b"HOST_TRANSPORT_CUT\n" else None)
            self.assertEqual(raw, b"HOST_TRANSPORT_CUT\n")
            self.assertEqual(result["raw_exit_code"], -signal.SIGKILL)
            self.assertIs(result["host_cut"]["guest_time_inferred"], False)
            self.assertEqual(result["pass_fds"], [disk.fd])
            self.assertEqual(result["state_descriptor"]["host_inode"], meta.st_ino)
            self.assertNotIn("passed", result)
            self.assertNotIn("native_owner_verified", result)
            self.assertEqual(disk.observe(self.digest), disk.initial)
            line = result["host_cut"]
            self.assertEqual(line["line_sha256"], hashlib.sha256(raw).hexdigest())
            self.assertLessEqual(line["observed_at_ns"], line["kill_call_before_ns"])
            self.assertLessEqual(line["kill_call_before_ns"], line["kill_call_after_ns"])
            command[command.index("-drive") + 1] += ",snapshot=on"
            with self.assertRaisesRegex(ValueError, "same original physical raw drive"):
                disk.require_drive(command)

    def test_inherited_descriptor_resolves_original_inode_during_path_aba(self):
        with transport.SameStateDisk(self.image, self.digest) as disk:
            original = self.root / "retained-original.raw"
            self.image.rename(original)
            self.image.write_bytes(b"different pathname occupant")
            code = ("import os,sys; fd=os.open(sys.argv[1],os.O_RDWR); s=os.fstat(fd); "
                    "print(s.st_dev,s.st_ino,s.st_size)")
            try:
                child = subprocess.run([sys.executable, "-I", "-B", "-c", code, disk.child_path],
                                       pass_fds=(disk.fd,), check=True, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            finally:
                self.image.unlink()
                original.rename(self.image)
            self.assertEqual(tuple(map(int, child.stdout.split())),
                             (*disk.identity, transport.original.STATE_BYTES))
            self.assertEqual(disk.observe(self.digest), disk.initial)


if __name__ == "__main__":
    unittest.main()
