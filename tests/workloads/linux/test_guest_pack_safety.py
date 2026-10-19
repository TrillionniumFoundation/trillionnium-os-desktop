"""Guest rootfs staging provenance and symlink escape negative tests (NO QEMU)."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("a04_guest_pack_safety", HERE/"guest.py")
guest=importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class RootfsInputSafety(unittest.TestCase):
    def setUp(self):
        self.reference=json.loads((HERE/"baselines/linux-debian13-x86_64.json").read_text())

    def inputs(self, td):
        td=Path(td)
        a01=td/"a01.cpio.gz"
        source=("#!/bin/sh\necho TRILLIONNIUM_A01_BOOT_OK\n"
                "exec /bin/busybox poweroff -f\n").encode()
        entries={"bin":(stat.S_IFDIR|0o755,b""),
                 "bin/busybox":(stat.S_IFREG|0o755,b"fake busybox"),
                 "init":(stat.S_IFREG|0o755,source)}
        a01.write_bytes(gzip.compress(guest.make_newc(entries),mtime=0))
        staging=td/"real-rootfs"
        staging.mkdir()
        manifest={"schema":1,"elf":[],"files":[]}
        return a01, staging, manifest

    def run_pack(self, td, a01, root, manifest):
        saved=Path(td)/"manifest.json"
        saved.write_text(json.dumps(manifest))
        return guest.pack(a01,root,saved,self.reference,
                          Path(td)/"out.cpio.gz",Path(td)/"out.json",
                          expected_a01_sha=guest.sha_file(a01))

    def test_rootfs_directory_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            a01,root,manifest=self.inputs(td)
            alias=Path(td)/"alias"
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError,"real directory"):
                self.run_pack(td,a01,alias,manifest)

    def test_internal_symlink_is_refused_even_if_hash_would_match(self):
        with tempfile.TemporaryDirectory() as td:
            a01,root,manifest=self.inputs(td)
            outside=Path(td)/"outside-sensitive"
            outside.write_text("synthetic not private")
            (root/"linked-data").symlink_to(outside)
            with self.assertRaisesRegex(ValueError,"symlink"):
                self.run_pack(td,a01,root,manifest)

    def test_manifest_duplicate_paths_are_refused_before_inclusion(self):
        with tempfile.TemporaryDirectory() as td:
            a01,root,manifest=self.inputs(td)
            record={"path":"/etc/hosts","sha256":"0"*64,"mode":"0444"}
            manifest["files"]=[record,dict(record)]
            with self.assertRaisesRegex(ValueError,"duplicate"):
                self.run_pack(td,a01,root,manifest)


    def test_manifest_elf_claim_cannot_mask_replaced_bytes(self):
        with tempfile.TemporaryDirectory() as td:
            a01, root, manifest = self.inputs(td)
            for stem, name in guest.BINARY_FOR.items():
                path = "/usr/local/bin/a04/" + name
                actual = root / path.lstrip("/")
                actual.parent.mkdir(parents=True, exist_ok=True)
                data = ("wrong executable " + stem).encode()
                actual.write_bytes(data)
                actual.chmod(0o555)
                manifest["files"].append({"path": path, "mode": "0555",
                                           "sha256": hashlib.sha256(data).hexdigest()})
                baseline = self.reference["binaries"][stem]
                manifest["elf"].append({"name": name, "path": path,
                                         "sha256": baseline["sha256"],
                                         "interpreter": baseline["interpreter"],
                                         "needed": baseline["needed"]})
            with self.assertRaisesRegex(ValueError, "ELF bytes not identical"):
                self.run_pack(td, a01, root, manifest)

    def test_guest_case_token_cannot_inject_commands(self):
        from copy import deepcopy
        poisoned = deepcopy(self.reference)
        injected = "dynamic.smoke'; echo A04_BAD_CODE; #"
        poisoned["cases"][injected] = {"status": "pass", "facts": {"ok": True}}
        with self.assertRaisesRegex(ValueError, "unsafe guest ELF case name"):
            guest.reference_elf_cases(poisoned)
        with self.assertRaisesRegex(ValueError, "unsafe guest ELF command token"):
            guest.make_guest_script([(injected, "dynamic", "smoke'; echo A04_BAD_CODE; #")])

if __name__=="__main__":
    unittest.main()
