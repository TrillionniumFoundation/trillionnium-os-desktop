"""Focused regressions for the R3 native boot policy boundaries."""
import json
import tempfile
import unittest
from pathlib import Path

import derive_native_remount_policy as remount
import derive_native_console_policy as console
import derive_native_timesync_policy as timesync
import verify_native_calibration as calibration
import verify_native_journal_storage as journal
import verify_native_stdio as stdio

HERE = Path(__file__).resolve().parent
VOCABULARY = """(common file_common (ioctl read write create getattr setattr lock relabelfrom relabelto append map unlink link rename execute quotaon mounton audit_access open execmod watch watch_mount watch_sb watch_with_perm watch_reads))
(class dir (add_name remove_name reparent search rmdir))
(classcommon dir file_common)
(class file (execute_no_trans entrypoint))
(classcommon file file_common)
(class lnk_file ())
(classcommon lnk_file file_common)
(type droidloom_policy_loader)
(type p4_linux_product_store_t)
(type unrelated)
"""
TRAVERSE = "(allow droidloom_policy_loader p4_linux_product_store_t (dir (getattr search)))\n"


class ObservedPolicy:
    """An independent observed-vector fixture; raw rules are checked separately."""
    def __init__(self, added=(), omit=()):
        self.added, self.omit = set(added), set(omit)

    def permissions(self, kind, names):
        return 1, {name: 1 << index for index, name in enumerate(names)}

    def context_av(self, actor, target, kind, names):
        wanted = {"getattr", "search"} if kind == "dir" else set()
        wanted |= {name for cls, name in self.added if cls == kind}
        wanted -= {name for cls, name in self.omit if cls == kind}
        return sum(bit for name, bit in self.permissions(kind, names)[1].items() if name in wanted)


class CalibrationParents(unittest.TestCase):
    def verify(self, text, policy=None):
        with tempfile.TemporaryDirectory() as directory:
            exported = Path(directory) / "policy.cil"
            exported.write_text(text)
            return calibration.verify_store_boundary(policy or ObservedPolicy(), text, exported)

    def test_exact_public_parent_metadata(self):
        proof = self.verify(VOCABULARY + TRAVERSE)
        self.assertEqual(proof["raw_permissions"], {"dir": ["getattr", "search"], "file": [], "lnk_file": []})
        self.assertFalse(proof["private_file_access_granted"])

    def test_attribute_grant_cannot_hide_directory_enumeration(self):
        extra = """(typeattribute readers)
(typeattributeset readers (droidloom_policy_loader unrelated))
(typeattribute stores)
(typeattributeset stores (p4_linux_product_store_t unrelated))
(allow readers stores (dir (open read)))
"""
        with self.assertRaisesRegex(ValueError, "store permission/complement"):
            self.verify(VOCABULARY + TRAVERSE + extra)

    def test_private_file_and_symlink_bodies_stay_denied(self):
        for kind in ("file", "lnk_file"):
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "store permission/complement"):
                self.verify(VOCABULARY + TRAVERSE +
                    f"(allow droidloom_policy_loader p4_linux_product_store_t ({kind} (read)))\n")

    def test_missing_traversal_rejected(self):
        with self.assertRaisesRegex(ValueError, "store permission/complement"):
            self.verify(VOCABULARY + TRAVERSE.replace("getattr search", "getattr"))

    def test_effective_binary_vector_cannot_exceed_exported_contract(self):
        with self.assertRaisesRegex(ValueError, "escaped its complement"):
            self.verify(VOCABULARY + TRAVERSE, ObservedPolicy(added=[("dir", "write")]))
        with self.assertRaisesRegex(ValueError, "parent traversal is denied"):
            self.verify(VOCABULARY + TRAVERSE, ObservedPolicy(omit=[("dir", "search")]))

    def test_ioctl_filter_not_mistaken_for_metadata(self):
        with self.assertRaisesRegex(ValueError, "acquired an ioctl filter"):
            self.verify(VOCABULARY + TRAVERSE +
                "(allowx droidloom_policy_loader p4_linux_product_store_t (ioctl dir (0x542a)))\n")


class JournalStreamState(unittest.TestCase):
    def test_real_libselinux_matches_names_and_inode_kinds(self):
        with tempfile.TemporaryDirectory() as directory:
            proof = journal.verify_stream_file_contexts(HERE, Path(directory))
        self.assertEqual(len(proof["matched_paths_and_inode_kinds"]), 16)

    def test_profile_preserves_numeric_names_and_process_privacy(self):
        proof = journal.verify_stream_profile(HERE)
        self.assertEqual(proof["decimal_digits"], [1, 20])
        body = (HERE / "apparmor/droidloom-ubuntu-journald").read_text()
        for changed in (
            body + "\n/run/systemd/journal/streams/** rw,\n",
            body.replace("audit deny @{PROC}/[0-9]*/{environ,mem,maps,cmdline} r,", ""),
            body.replace("@{droidloom_journal_u64}=", "@{unreviewed_u64}="),
        ):
            with self.subTest(change=changed[-80:]), tempfile.TemporaryDirectory() as directory:
                here = Path(directory)
                (here / "apparmor").mkdir()
                (here / "apparmor/droidloom-ubuntu-journald").write_text(changed)
                with self.assertRaises(ValueError):
                    journal.verify_stream_profile(here)


class NativeStartupMetadata(unittest.TestCase):
    def test_fixed_kernel_log_context_uses_real_inode_kind_matcher(self):
        with tempfile.TemporaryDirectory() as directory:
            proof = console.verify_file_contexts(HERE, Path(directory))
        self.assertEqual(proof["original_kernel_log_positive_and_negative_cases"], 6)

    def test_timesync_fatal_path_cannot_rebind_to_different_source_bytes(self):
        contract = timesync.contract(HERE)
        self.assertFalse(contract["runtime_qualified"])
        with tempfile.TemporaryDirectory() as directory:
            here = Path(directory)
            for name in timesync.STARTUP_SOURCE_PINS:
                changed = json.loads(json.dumps(contract))
                row = next(row for row in changed["source_documents"]
                           if row["package"] == "systemd" and row["path"] == name)
                row["sha256"] = "0" * 64
                (here / "native-timesync-source.json").write_text(json.dumps(changed))
                with self.subTest(path=name), self.assertRaisesRegex(
                        ValueError, "Timesync startup source identity differs"):
                    timesync.contract(here)


class NativeMountEntry(unittest.TestCase):
    def test_new_mount_cannot_use_another_caller_or_root_label(self):
        transitions = remount.tmp_mount_transitions()
        changes = (
            {row.replace("p4_linux_service_executor_t", "p4_linux_user_executor_t") for row in transitions},
            {row.replace("p4_linux_tmp_t)", "device)") for row in transitions},
            transitions | {"(typetransition init_t p4_linux_remount_mount_exec_t process p4_linux_tmp_mount_t)"},
            transitions - {"(typetransition p4_linux_tmp_mount_t tmpfs dir p4_linux_tmp_t)"},
        )
        for lines in changes:
            with self.subTest(lines=lines), self.assertRaisesRegex(ValueError, "transition boundary"):
                remount.verify_tmp_mount(None, list(lines), [], {})

    def test_tmpfs_original_label_semantics_required(self):
        for fsuse in (
            "(fsuse xattr tmpfs (u object_r tmpfs ((s0) (s0))))",
            "(fsuse trans tmpfs (u object_r device ((s0) (s0))))",
        ):
            with self.subTest(fsuse=fsuse), self.assertRaisesRegex(ValueError, "original transition-labelled tmpfs"):
                remount.verify_tmp_mount(None, list(remount.tmp_mount_transitions()) + [fsuse], [], {})

    def test_original_mount_files_and_loader_sources(self):
        self.assertEqual(len(calibration.verify_sources(HERE)), 8)
        self.assertEqual(len(stdio.verify_sources(HERE)["executor_logger_sources"]), 2)
        source = remount.contract(HERE)
        unit = next(row for row in source["files"] if row["path"].endswith("/tmp.mount"))
        self.assertEqual((unit["bytes"], unit["mode"], unit["uid"], unit["gid"], unit["nlink"]), (804, 0o644, 0, 0, 1))
        self.assertEqual(unit["sha256"], "4f3830dc0bc712375190fd80e175eafcd2f1c4b381fdd7c1563b5aa475285319")


if __name__ == "__main__":
    unittest.main()
