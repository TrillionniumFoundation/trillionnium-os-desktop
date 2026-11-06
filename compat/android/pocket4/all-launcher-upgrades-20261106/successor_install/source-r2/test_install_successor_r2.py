#!/usr/bin/env python3
"""Offline controls for revision 2. No Main reads, root claims, native CLI or Android."""
import sys
sys.dont_write_bytecode = True
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("successor_install_r2", ROOT / "install_successor_native.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
BASE = b"""N: android=http://schemas.android.com/apk/res/android
  E: manifest (line=1)
    A: android:versionCode(0x0101021b)=(type 0x10)0x102811
    A: package="com.jingdong.app.mall" (Raw: "com.jingdong.app.mall")
    E: uses-sdk (line=2)
      A: android:minSdkVersion(0x0101020c)=(type 0x10)0x18
    E: application (line=3)
"""
CONTROL = {}
def jd():
    path = "/data/app/~~owned-fixture/com.jingdong.app.mall-test"
    return {"package": "com.jingdong.app.mall", "uid": 10126, "version_code": 102810, "code_path": path,
            "apks": [{"path": path + "/" + name, "bytes": size, "sha256": digest}
                     for name, (size, digest) in worker.REVIEWED_JD_OLD_APKS.items()]}

def command(**changes):
    row = {"spawned": True, "joined": True, "returncode": 0, "timed_out": False, "output_capture_complete": True}
    row.update(changes)
    return row

class FixtureStore:
    def __init__(self, path):
        self.path = path
    def write(self, name, raw):
        path = self.path / name
        with path.open("xb") as handle:
            handle.write(raw)
        return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    def json(self, name, value):
        return self.write(name, worker.canonical(value) + b"\n")

class Boundaries(unittest.TestCase):
    def test_exact_jd_pair_retains_both_and_sums_capacity(self):
        current = jd()
        current["apks"].reverse()
        rows = worker.reviewed_previous_apks("com.jingdong.app.mall", current)
        self.assertEqual([Path(row["path"]).name for row in rows], ["base.apk", "split_config.arm64_v8a.apk"])
        self.assertEqual(sum(row["bytes"] for row in rows), 294389107)
        self.assertEqual(len(rows), 2)

    def test_other_package_cannot_borrow_jd_split_shape(self):
        current = jd(); current["package"] = "com.taobao.taobao"
        with self.assertRaises(worker.Rejected):
            worker.reviewed_previous_apks("com.taobao.taobao", current)

    def test_unreviewed_jd_uid_version_hash_size_and_name_rejected(self):
        cases = []
        row = jd(); row["uid"] += 1; cases.append(row)
        row = jd(); row["version_code"] += 1; cases.append(row)
        row = jd(); row["apks"][1]["sha256"] = "0"*64; cases.append(row)
        row = jd(); row["apks"][1]["bytes"] += 1; cases.append(row)
        row = jd(); row["apks"][1]["path"] = row["code_path"] + "/split_config.x86.apk"; cases.append(row)
        for row in cases:
            with self.subTest(row=row), self.assertRaises(worker.Rejected):
                worker.reviewed_previous_apks("com.jingdong.app.mall", row)

    def test_extra_duplicate_or_outside_old_apk_rejected(self):
        cases = []
        row = jd(); row["apks"].append(copy.deepcopy(row["apks"][0])); cases.append(row)
        row = jd(); row["apks"][1]["path"] = row["apks"][0]["path"]; cases.append(row)
        row = jd(); row["apks"][1]["path"] = "/other/split_config.arm64_v8a.apk"; cases.append(row)
        for row in cases:
            with self.subTest(row=row), self.assertRaises(worker.Rejected):
                worker.reviewed_previous_apks("com.jingdong.app.mall", row)

    def test_existing_single_base_path_preserved(self):
        row = jd(); row["apks"] = [row["apks"][0]]
        self.assertEqual(worker.reviewed_previous_apks("com.jingdong.app.mall", row), row["apks"])
        row["apks"][0]["path"] = row["code_path"] + "/one-other.apk"
        with self.assertRaises(worker.Rejected):
            worker.reviewed_previous_apks("com.jingdong.app.mall", row)

    def test_full_candidate_manifest_and_false_split_flags(self):
        self.assertTrue(worker.complete_manifest_command(BASE, command())["uses_split_element_absent"])
        false_flag = BASE.replace(b"    E: uses-sdk", b"    A: android:isSplitRequired(0x0101064e)=(type 0x12)0x0\n    E: uses-sdk")
        self.assertTrue(worker.complete_single_apk_manifest(false_flag)["required_splits_not_requested"])

    def test_split_marker_and_uses_split_requirements_rejected(self):
        split = BASE.replace(b"    E: uses-sdk", b'    A: split="config.arm64_v8a" (Raw: "config.arm64_v8a")\n    E: uses-sdk')
        uses = BASE + b'    E: uses-split (line=4)\n      A: android:name(0x01010003)="base" (Raw: "base")\n'
        required = BASE.replace(b"    E: uses-sdk", b"    A: android:isSplitRequired(0x0101064e)=(type 0x12)0xffffffff\n    E: uses-sdk")
        feature = BASE.replace(b"    E: uses-sdk", b"    A: android:isFeatureSplit(0x0101055b)=(type 0x12)0x1\n    E: uses-sdk")
        for raw in (split, uses, required, feature):
            with self.subTest(raw=raw), self.assertRaises(worker.Rejected):
                worker.complete_single_apk_manifest(raw)

    def test_missing_malformed_or_duplicate_manifest_rejected(self):
        for raw in (b"", b"E: not-manifest (line=1)\n", BASE + b"  E: manifest (line=9)\n",
                    BASE.replace(b"E: uses-sdk (line=2)", b"E: uses-sdk ???"),
                    BASE.replace(b"    E: uses-sdk", b'    A: package="duplicate"\n    E: uses-sdk')):
            with self.subTest(raw=raw), self.assertRaises(worker.Rejected):
                worker.complete_single_apk_manifest(raw)

    def test_tool_failed_truncated_or_unjoined_output_cannot_authorize_install(self):
        for changes in ({"spawned": False}, {"joined": False}, {"returncode": 1}, {"timed_out": True},
                        {"output_capture_complete": False}, {"error": {"code": "OWNED_CHILD_ERROR"}}):
            with self.subTest(changes=changes), self.assertRaises(worker.Rejected):
                worker.complete_manifest_command(BASE, command(**changes))

    def test_douyin_origin_is_one_reviewed_host(self):
        self.assertEqual(worker.ALLOWED["com.ss.android.ugc.aweme"], ("imtt.dd.qq.com",))
        self.assertEqual(len(worker.ALLOWED), 7)
        self.assertNotIn("com.sankuai.meituan.takeoutnew", worker.ALLOWED)

    def test_real_owned_host_child_fd_transport_and_exit_join(self):
        before = len(os.listdir("/proc/self/fd"))
        executable = str(Path(sys.executable).resolve())
        fd = os.open(executable, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            with tempfile.TemporaryDirectory(prefix="p4-install-r2-host-fixture-") as folder:
                fixture = FixtureStore(Path(folder))
                raw, row = worker.run_command(fixture, fd,
                    [executable, "-I", "-c", "import sys;sys.stdout.buffer.write(" + repr(BASE) + ")"],
                    "fixture-host-manifest", 5, worker.Budget(), host_tool_path=executable, output_limit=4*1024*1024)
                self.assertEqual(raw, BASE)
                self.assertTrue(row["joined"])
                self.assertFalse(row["execution_from_held_cli_fd"])
                self.assertEqual(row["executable"], executable)
                self.assertTrue(worker.complete_manifest_command(raw, row)["manifest_root_observed"])
                raw, failed = worker.run_command(fixture, fd,
                    [executable, "-I", "-c", "import sys;sys.stdout.write('incomplete');sys.exit(3)"],
                    "fixture-host-failure", 5, worker.Budget(), host_tool_path=executable)
                self.assertTrue(failed["joined"])
                self.assertEqual(failed["returncode"], 3)
                with self.assertRaises(worker.Rejected):
                    worker.complete_manifest_command(raw, failed)
        finally:
            os.close(fd)
        after = len(os.listdir("/proc/self/fd"))
        self.assertEqual(before, after)
        CONTROL.update(actual_owned_host_children=2, joined_children=2,
                       FD_count_before=before, FD_count_after=after,
                       native_cli_executed=False, Android_commands=0, Main_process_reads=0)

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Boundaries)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    receipt = {"schema": "pocket4-successor-install-r2-offline-controls-v1",
               "ok": result.wasSuccessful(), "tests_run": result.testsRun,
               "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
               "caller_uid": os.getuid(), "caller_euid": os.geteuid(), "owned_host_child_control": CONTROL,
               "Main_process_reads": 0, "Main_locks_acquired": 0, "native_cli_commands": 0,
               "Android_commands": 0, "installs": 0, "runtime_worker_invoked": False,
               "fixture_XML_is_not_actual_APK_evidence": True}
    print(json.dumps(receipt, sort_keys=True, separators=(",", ":")), flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
