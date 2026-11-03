"""Real file boundary and build-receipt checks; no product execution claims."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

import desktop
import root_bundle as root


class RootBundleTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"desktop_commit": "a" * 40, "hepta_commit": "b" * 40,
                         "files": {"bin/" + name: {"sha256": "c" * 64, "bytes": 64}
                                   for name in desktop.PROGRAMS}}
        self.ui = {"schema": "trill.linux-text-build-receipt.v1", "status": "passed", "exit_code": 0,
                   "source_commit": "a" * 40, "source_tree": "d" * 40,
                   "hepta": {"commit": "b" * 40, "tree": "e" * 40},
                   "packaged_binaries": {name: {"sha256": "c" * 64, "bytes": 64}
                                         for name in desktop.PROGRAMS}}
        self.receipt = {"schema": "trill.linux-root-build-receipt.v1", "status": "passed",
                        "source_clean_after": True, "production_ready": False,
                        "sources": root.ui_identity(self.ui, self.manifest),
                        "commands": [{"name": name, "exit_code": 0} for name in
                                     ("hepta-build", "desktop-root-build", "root-metadata")],
                        "binaries": {name: {} for name in root.PROGRAMS},
                        "desktop_manifest_sha256": desktop.digest(desktop.json_bytes(self.manifest))}

    def test_same_commits_cannot_hide_different_distribution_bytes(self):
        original = root.ui_identity(self.ui, self.manifest)
        changed = copy.deepcopy(self.ui)
        changed["packaged_binaries"]["trill-shell"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(desktop.ProductError, "distribution ELF differs"):
            root.ui_identity(changed, self.manifest)
        self.assertEqual(root.build_identity(self.receipt, self.manifest), original)

    def test_root_tools_cannot_use_another_owner_or_desktop_payload(self):
        changed = copy.deepcopy(self.receipt)
        changed["sources"]["hepta"]["commit"] = "f" * 40
        with self.assertRaisesRegex(desktop.ProductError, "source combinations differ"):
            root.build_identity(changed, self.manifest)
        changed = copy.deepcopy(self.receipt)
        changed["desktop_manifest_sha256"] = "f" * 64
        with self.assertRaisesRegex(desktop.ProductError, "different Desktop payload"):
            root.build_identity(changed, self.manifest)

    def test_missing_failed_and_dirty_builds_never_qualify(self):
        for mutate in (lambda r: r["commands"].pop(),
                       lambda r: r["commands"][0].update(exit_code=1),
                       lambda r: r.update(source_clean_after=False),
                       lambda r: r.update(status="running"),
                       lambda r: r["binaries"].pop("codex-app-server")):
            candidate = copy.deepcopy(self.receipt)
            mutate(candidate)
            with self.assertRaises(desktop.ProductError):
                root.build_identity(candidate, self.manifest)

    def test_real_file_inventory_refuses_symlinks_and_hardlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "plain").write_bytes(b"package metadata")
            (folder / "link").symlink_to("plain")
            with self.assertRaisesRegex(desktop.ProductError, "link or a special object"):
                root.inventory(folder)
            (folder / "link").unlink()
            os.link(folder / "plain", folder / "hard")
            with self.assertRaisesRegex(desktop.ProductError, "link or a special object"):
                root.inventory(folder)

    def test_root_installation_cannot_live_below_shared_tmp(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(desktop.ProductError, "Root custody"):
                root.root_directory(Path(directory))

    def test_empty_directories_cannot_escape_the_package_object_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            for index in range(513):
                (Path(directory) / str(index)).mkdir()
            with self.assertRaisesRegex(desktop.ProductError, "object count or depth"):
                root.inventory(Path(directory))

    def test_elf_magic_alone_does_not_establish_the_host_architecture(self):
        for data in (b"\x7fELF", b"\x7fELF\x02\x01\x01" + b"\0" * 80):
            with self.assertRaisesRegex(desktop.ProductError, "x86_64 Linux ELF"):
                root.elf(data, "unqualified fixture")


if __name__ == "__main__":
    unittest.main()
