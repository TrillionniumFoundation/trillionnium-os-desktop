"""Tests of guest packaging and serial evidence parsing. SYNTHETIC, NOT QEMU."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a04_guest", HERE / "guest.py")
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class GuestPackAndParse(unittest.TestCase):
    def setUp(self):
        self.reference = json.loads((HERE / "baselines/linux-debian13-x86_64.json").read_text())

    def synthetic_cpio(self):
        init = b"#!/bin/sh\necho TRILLIONNIUM_A01_INIT_BEGIN\necho TRILLIONNIUM_A01_BOOT_OK\nexec /bin/busybox poweroff -f\n"
        data = guest.make_newc({"bin": (stat.S_IFDIR | 0o755, b""),
                                "bin/busybox": (stat.S_IFREG | 0o755, b"synthetic"),
                                "init": (stat.S_IFREG | 0o755, init)})
        return gzip.compress(data,mtime=0)

    def test_newc_roundtrip_and_reject_corrupt(self):
        archive = guest.make_newc({"bin": (stat.S_IFDIR | 0o755, b""),
                                   "bin/link": (stat.S_IFLNK | 0o777, b"busybox"),
                                   "x": (stat.S_IFREG | 0o555, b"123")})
        self.assertEqual(guest.parse_newc(archive)["bin/link"][1], b"busybox")
        with self.assertRaises(ValueError):
            guest.parse_newc(archive[:-512])
        with self.assertRaises(ValueError):
            guest.add_file({}, "../../etc/shadow", b"forbidden")

    def test_boot_script_preserves_prior_checks(self):
        init = guest.parse_newc(gzip.decompress(self.synthetic_cpio()))["init"][1]
        injected = guest.inject_a01_init(init).decode()
        self.assertEqual(injected.count("TRILLIONNIUM_A01_BOOT_OK"),1)
        self.assertLess(injected.index("TRILLIONNIUM_A01_BOOT_OK"),
                        injected.index("TRILLIONNIUM_A04_WORKLOAD_BEGIN"))
        self.assertTrue(injected.endswith("exec /bin/busybox poweroff -f\n"))
        with self.assertRaises(ValueError):
            guest.inject_a01_init(b"echo bootstrap\n")

    def test_serial_requires_real_guest_markers_and_distinguishes_failures(self):
        cases = guest.reference_elf_cases(self.reference)
        manifest = {"cases": [name for name,_,_ in cases],
                    "a04_initramfs_sha256": "image-verified"}
        def serial(fail=None):
            out = ["TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_BOOT_OK",
                   "TRILLIONNIUM_A04_WORKLOAD_BEGIN"]
            for name,_,_ in cases:
                out.append(f"A04_CASE_BEGIN={name}")
                out.append(json.dumps(self.reference["cases"][name]["facts"],sort_keys=True))
                out.append(f"A04_CASE_END={name}:" + ("20" if name==fail else "0"))
            out.extend(["TRILLIONNIUM_A04_RUNNER_STATUS=" + ("1" if fail else "0"),
                        "TRILLIONNIUM_A04_WORKLOAD_END"])
            return "\n".join(out)+"\n"
        verified = guest.parse_serial(serial(),self.reference,manifest,qemu_exit=33,
                                      kernel_sha=guest.A01_KERNEL_SHA,image_sha="image-verified")
        self.assertTrue(verified["guest_execution_verified"])
        self.assertTrue(verified["guest_compatibility_passed"])
        self.assertEqual(verified["counts"]["pass"],len(cases))
        self.assertEqual(verified["counts"]["not_run"], len(self.reference["cases"])-len(cases))
        failure = guest.parse_serial(serial(cases[0][0]),self.reference,manifest,qemu_exit=33,
                                     kernel_sha=guest.A01_KERNEL_SHA,image_sha="image-verified")
        self.assertTrue(failure["guest_execution_verified"])
        self.assertFalse(failure["guest_compatibility_passed"])
        self.assertEqual(failure["counts"]["fail"],1)
        wrong_kernel = guest.parse_serial(serial(),self.reference,manifest,qemu_exit=33,
                                          kernel_sha="bad",image_sha="image-verified")
        self.assertFalse(wrong_kernel["guest_execution_verified"])
        wrong_exit = guest.parse_serial(serial(),self.reference,manifest,qemu_exit=65,
                                        kernel_sha=guest.A01_KERNEL_SHA,image_sha="image-verified")
        self.assertFalse(wrong_exit["guest_execution_verified"])
        no_cases = guest.parse_serial("TRILLIONNIUM_A01_BOOT_OK\n",self.reference,manifest,
                                      qemu_exit=33,kernel_sha=guest.A01_KERNEL_SHA,
                                      image_sha="image-verified")
        self.assertEqual(no_cases["counts"]["not_run"],len(self.reference["cases"]))
        self.assertFalse(no_cases["guest_execution_verified"])

    def test_zero_exit_but_wrong_errno_facts_is_not_guest_compatibility(self):
        """Regression: reported ok=true must not mask real ABI divergence."""
        cases = guest.reference_elf_cases(self.reference)
        manifest = {"cases": [name for name, _, _ in cases],
                    "a04_initramfs_sha256": "verified-image"}
        stdout = ["TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_BOOT_OK",
                  "TRILLIONNIUM_A04_WORKLOAD_BEGIN"]
        victim = "dynamic.errno"
        for name, _, _ in cases:
            facts = dict(self.reference["cases"][name]["facts"])
            if name == victim:
                facts["ENOENT"] = 38  # guest ENOSYS instead of Linux ENOENT
            stdout.extend(("A04_CASE_BEGIN=" + name, json.dumps(facts),
                           "A04_CASE_END=" + name + ":0"))
        stdout.extend(("TRILLIONNIUM_A04_RUNNER_STATUS=0",
                       "TRILLIONNIUM_A04_WORKLOAD_END"))
        report = guest.parse_serial("\n".join(stdout) + "\n", self.reference,
                                    manifest, qemu_exit=33,
                                    kernel_sha=guest.A01_KERNEL_SHA,
                                    image_sha="verified-image")
        self.assertTrue(report["guest_execution_verified"])
        self.assertFalse(report["guest_compatibility_passed"])
        self.assertEqual(report["cases"][victim]["status"], "fail")
        self.assertIn("differ from reference", report["cases"][victim]["error"])
        self.assertEqual(report["counts"]["fail"], 1)

    def test_ordered_boot_and_runner_markers_reject_replayed_or_damaged_serial(self):
        """A successful-looking line set outside the boot phase is not evidence."""
        cases = guest.reference_elf_cases(self.reference)
        manifest = {"cases": [name for name, _, _ in cases],
                    "a04_initramfs_sha256": "TEST_IMAGE"}
        def qualify(lines):
            return guest.parse_serial("\n".join(lines) + "\n", self.reference, manifest,
                                      qemu_exit=33, kernel_sha=guest.A01_KERNEL_SHA,
                                      image_sha="TEST_IMAGE")
        serial = ["TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_BOOT_OK",
                  "TRILLIONNIUM_A04_WORKLOAD_BEGIN"]
        for name, _, _ in cases:
            serial += ["A04_CASE_BEGIN=" + name,
                       json.dumps(self.reference["cases"][name]["facts"], sort_keys=True),
                       "A04_CASE_END=" + name + ":0"]
        serial += ["TRILLIONNIUM_A04_RUNNER_STATUS=0", "TRILLIONNIUM_A04_WORKLOAD_END"]
        self.assertTrue(qualify(serial)["guest_compatibility_passed"])
        corrupt = [
            serial[:1] + [serial[0]] + serial[1:],  # duplicate A01 BEGIN
            [serial[1], serial[0], *serial[2:]],  # wrong boot order
            serial[:3] + ["TRILLIONNIUM_A04_RUNNER_STATUS=0"] + serial[3:],
            serial + ["A04_CASE_BEGIN=dynamic.smoke"],  # case after runner end
            serial + ["TRILLIONNIUM_A04_RUNNER_STATUS=0"],  # duplicate status
            serial + ["Uncaught panic: guest failure despite exit 33"],
            serial[:3] + ["A04_CASE_BEGIN=unknown.thing"] + serial[3:],
            serial[:-5] + serial[-2:-1] + serial[-5:-2] + serial[-1:],
        ]
        for index, lines in enumerate(corrupt):
            with self.subTest(corruption=index):
                report = qualify(lines)
                self.assertFalse(report["guest_execution_verified"])
                self.assertFalse(report["guest_compatibility_passed"])
                self.assertTrue(report["boot_evidence"]["anomalies"])

    def test_ambiguous_guest_json_does_not_qualify(self):
        cases = guest.reference_elf_cases(self.reference)
        manifest = {"cases": [name for name, _, _ in cases],
                    "a04_initramfs_sha256": "TEST_IMAGE"}
        for poison in ('{"ok":false,"ok":true}', '{"ok":true,"n":NaN}'):
            with self.subTest(poison=poison):
                serial = ["TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_BOOT_OK",
                          "TRILLIONNIUM_A04_WORKLOAD_BEGIN"]
                for name, _, _ in cases:
                    output = poison if name == "dynamic.smoke" else json.dumps(
                        self.reference["cases"][name]["facts"])
                    serial += ["A04_CASE_BEGIN=" + name, output, "A04_CASE_END=" + name + ":0"]
                serial += ["TRILLIONNIUM_A04_RUNNER_STATUS=0", "TRILLIONNIUM_A04_WORKLOAD_END"]
                r = guest.parse_serial("\n".join(serial) + "\n", self.reference, manifest,
                                       qemu_exit=33, kernel_sha=guest.A01_KERNEL_SHA,
                                       image_sha="TEST_IMAGE")
                self.assertFalse(r["guest_compatibility_passed"])
                self.assertEqual(r["cases"]["dynamic.smoke"]["status"], "fail")
                self.assertTrue(any("invalid or ambiguous guest JSON" in a for a in r["boot_evidence"]["anomalies"]))

    def test_pack_selfcontained_synthetic_inputs_no_qemu(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            image = td / "a01.cpio.gz"
            image.write_bytes(self.synthetic_cpio())
            rootfs = td / "rootfs"
            rootfs.mkdir()
            manifest = {"schema": 1, "elf": [], "files": []}
            from copy import deepcopy
            reference = deepcopy(self.reference)
            for stem, binary in guest.BINARY_FOR.items():
                contents = ("synthetic-ELF-"+stem).encode()
                dest = "/usr/local/bin/a04/"+binary
                staged = rootfs / dest.lstrip("/")
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(contents)
                staged.chmod(0o555)
                digest = hashlib.sha256(contents).hexdigest()
                reference["binaries"][stem]["sha256"] = digest
                reference["binaries"][stem]["size"] = len(contents)
                manifest["elf"].append({"name": binary, "path": dest, "sha256": digest,
                                        "interpreter": reference["binaries"][stem]["interpreter"],
                                        "needed": reference["binaries"][stem]["needed"]})
                manifest["files"].append({"path": dest, "sha256": digest, "mode": "0555"})
            manifest_path = td / "rootfs.json"
            manifest_path.write_text(json.dumps(manifest))
            derived, metadata = td / "new.cpio.gz", td / "new.json"
            result = guest.pack(image,rootfs,manifest_path,reference,
                                derived,metadata,expected_a01_sha=guest.sha_file(image))
            self.assertEqual(result["case_count"],len(guest.reference_elf_cases(reference)))
            self.assertFalse(result["guest_execution_verified"])
            unpacked = guest.parse_newc(gzip.decompress(derived.read_bytes()))
            self.assertIn("test/a04/guest-run.sh",unpacked)
            self.assertIn("usr/local/bin/a04/probe_static",unpacked)
            self.assertEqual(unpacked["test/a04/a01-init-original.sh"][1],
                             guest.parse_newc(gzip.decompress(image.read_bytes()))["init"][1])
            result2 = guest.pack(image,rootfs,manifest_path,reference,
                                 td/"new2.cpio.gz",td/"new2.json",
                                 expected_a01_sha=guest.sha_file(image))
            self.assertEqual(result["a04_initramfs_sha256"], result2["a04_initramfs_sha256"])
            with self.assertRaises(ValueError):
                guest.pack(image,rootfs,manifest_path,reference,
                           derived,td/"second.json",expected_a01_sha=guest.sha_file(image))
            with self.assertRaises(ValueError):
                guest.pack(image,rootfs,manifest_path,reference,
                           td/"bad.cpio.gz",td/"bad.json")
            first_elf = rootfs / "usr/local/bin/a04/probe_static"
            # The staged rootfs is intentionally read-only.  Make the test
            # fixture writable before tampering so this negative check also
            # runs in user namespaces without CAP_DAC_OVERRIDE.
            first_elf.chmod(0o755)
            first_elf.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                guest.pack(image,rootfs,manifest_path,reference,
                           td/"tampered.cpio.gz",td/"tampered.json",
                           expected_a01_sha=guest.sha_file(image))


if __name__ == "__main__":
    unittest.main()
