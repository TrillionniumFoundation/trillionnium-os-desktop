"""Offline tests only: fixed target, readback, immutable staging and timeout receipts."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("beike_install_r2_under_test", HERE / "install_beike_bound_r2.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
c = m.load_base()


def snapshot(version, digest, size, code_path):
    return {"target": {"package": m.PACKAGE, "uid": m.UID, "android_user": 0,
        "version_code": version, "code_path": code_path,
        "package_manager_signing": {"certificate_sha256": [m.SIGNER]}},
        "base_apk": {"bytes": size, "sha256": digest},
        "other_original_package_identities": {"tv.danmaku.bili": {"uid": 10117, "version_code": 9150100}},
        "meituan_location_saved_observations": [{"source": "/saved/access.abx", "coverage": True,
            "entries": [{"name": "android.permission.ACCESS_FINE_LOCATION", "flags": 24576}],
            "effective_grant_state": "UNKNOWN"}]}


class WorkerBoundaries(unittest.TestCase):
    def setUp(self):
        self.before = snapshot(m.OLD_VERSION, m.OLD_SHA, m.OLD_BYTES, m.OLD_CODE_PATH)
        self.after = snapshot(m.NEW_VERSION, m.NEW_SHA, m.NEW_BYTES, "/data/app/new_beike")

    def test_actual_verified_receipt_canonical_pin(self):
        receipt = json.loads((HERE / "reference/beike-official-verification.json").read_text())["result"]
        self.assertEqual(m.sha(m.canonical(receipt)), m.VERIFIER_CANONICAL_SHA)
        self.assertEqual(receipt["manifest"]["version_code"], m.NEW_VERSION)
        self.assertEqual(receipt["apk"]["sha256"], m.NEW_SHA)
        self.assertEqual(receipt["signer_certificate_sha256"], [m.SIGNER])
        changed = copy.deepcopy(receipt)
        changed["manifest"]["package"] = "tv.danmaku.bili"
        self.assertNotEqual(m.sha(m.canonical(changed)), m.VERIFIER_CANONICAL_SHA)

    def test_unsafe_javascript_integer_roundtrip_is_rejected_by_real_verifier(self):
        original = json.loads((HERE / "reference/beike-official-verification.json").read_text())["result"]
        # This fixture was deliberately produced by an actual JavaScript
        # JSON.parse/JSON.stringify roundtrip. It is NOT source evidence.
        raw = (HERE / "testdata/beike-verifier-unsafe-js-roundtrip.json").read_bytes()
        rounded = json.loads(raw)
        self.assertEqual(original["apk"]["stat"]["st_mtime_ns"], 1793958953453465022)
        self.assertEqual(original["apk"]["stat"]["st_ctime_ns"], 1793958953594469952)
        self.assertEqual(rounded["apk"]["stat"]["st_mtime_ns"], 1793958953453465000)
        self.assertEqual(rounded["apk"]["stat"]["st_ctime_ns"], 1793958953594470000)
        self.assertGreater(original["apk"]["stat"]["st_mtime_ns"], 2 ** 53)
        self.assertEqual(original["apk"]["sha256"], rounded["apk"]["sha256"])
        self.assertEqual(original["manifest"], rounded["manifest"])
        self.assertEqual(original["signer_certificate_sha256"], rounded["signer_certificate_sha256"])
        self.assertNotEqual(m.sha(m.canonical(rounded)), m.VERIFIER_CANONICAL_SHA)

        class FakeHost:
            reads = []

            def read(self, path, limit, **kwargs):
                self.reads.append(path)
                if path != m.VERIFIER_DIR + "/result.json":
                    raise AssertionError("Corrupted evidence progressed past the first verifier gate")
                return raw, {"path": path, "bytes": len(raw), "sha256": m.sha(raw)}

        host = FakeHost()
        with self.assertRaisesRegex(m.Rejected, "^ACTUAL_VERIFIER_RESULT_DIFFERS$"):
            m.verifier(c, host)
        self.assertEqual(host.reads, [m.VERIFIER_DIR + "/result.json"])

    def test_exact_old_target_only(self):
        m.validate_pre(self.before)
        for key, value in (("package", "tv.danmaku.bili"), ("uid", 10117),
                           ("version_code", m.NEW_VERSION), ("code_path", "/data/app/replaced")):
            wrong = copy.deepcopy(self.before)
            wrong["target"][key] = value
            with self.subTest(key=key), self.assertRaises(m.Rejected):
                m.validate_pre(wrong)
        wrong = copy.deepcopy(self.before)
        wrong["base_apk"]["sha256"] = "0" * 64
        with self.assertRaises(m.Rejected):
            m.validate_pre(wrong)

    def test_all_new_readback_identities_required(self):
        m.validate_post(self.before, self.after)
        for section, key, value in (("target", "uid", 10144), ("target", "version_code", m.OLD_VERSION),
                                    ("base_apk", "sha256", m.OLD_SHA), ("base_apk", "bytes", m.NEW_BYTES - 1)):
            wrong = copy.deepcopy(self.after)
            wrong[section][key] = value
            with self.subTest(key=key), self.assertRaises(m.Rejected):
                m.validate_post(self.before, wrong)
        wrong = copy.deepcopy(self.after)
        wrong["target"]["package_manager_signing"]["certificate_sha256"] = ["0" * 64]
        with self.assertRaises(m.Rejected):
            m.validate_post(self.before, wrong)

    def test_other_package_or_meituan_change_never_passes(self):
        wrong = copy.deepcopy(self.after)
        wrong["other_original_package_identities"]["tv.danmaku.bili"]["uid"] = 10118
        with self.assertRaises(m.Rejected):
            m.validate_post(self.before, wrong)
        wrong = copy.deepcopy(self.after)
        wrong["meituan_location_saved_observations"][0]["entries"][0]["flags"] = 2
        with self.assertRaises(m.Rejected):
            m.validate_post(self.before, wrong)

    def test_foreign_main_or_failed_native_response_never_passes(self):
        command = {"spawned": True, "joined": True, "timed_out": False,
                   "returncode": 0, "output_capture_complete": True}
        good = {"ok": True, "state": "running", "host_pid": m.MAIN_HOST_PID}
        self.assertEqual(m.checked_response(c, m.canonical(good), command), good)
        for field, value in (("ok", False), ("state", "stopped"), ("host_pid", m.MAIN_HOST_PID + 1)):
            wrong = {**good, field: value}
            with self.subTest(field=field), self.assertRaises(m.Rejected):
                m.checked_response(c, m.canonical(wrong), command)
        with self.assertRaises(m.Rejected):
            m.checked_response(c, m.canonical(good), {**command, "timed_out": True})


class LocalProcessAndArchive(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fds = c.Descriptors()
        self.store = m.Store.__new__(m.Store)
        self.store.c, self.store.fds = c, self.fds
        self.store.fd = self.fds.own(os.open(self.temp.name, os.O_RDONLY | os.O_DIRECTORY))
        self.budget = c.Budget(seconds=60)

    def tearDown(self):
        self.fds.close_remaining()
        self.assertFalse(self.fds.live)
        self.temp.cleanup()

    def test_private_candidate_copy_is_identical_readonly_and_exclusive(self):
        source = Path(self.temp.name) / "source"
        data = b"PK\x03\x04fixed official bytes" * 100
        source.write_bytes(data)
        fd = self.fds.own(os.open(source, os.O_RDONLY))
        digest = hashlib.sha256(data).hexdigest()
        if os.geteuid() == 0:
            held, row = self.store.copy("held.apk", fd, len(data), digest, self.budget)
            self.assertEqual(os.read(held, len(data) + 1), data)
            self.assertEqual(row["sha256"], digest)
            self.assertEqual(row["stat"]["mode"] & 0o777, 0o400)
        else:
            # Keep the runtime root-owner requirement intact on non-root CI.
            with self.assertRaisesRegex(m.Rejected, "PRIVATE_READONLY_ARCHIVE_REQUIRED"):
                self.store.copy("held.apk", fd, len(data), digest, self.budget)
            self.assertEqual((Path(self.temp.name) / "held.apk").read_bytes(), data)
            self.assertEqual((Path(self.temp.name) / "held.apk").stat().st_mode & 0o777, 0o400)
        with self.assertRaises(FileExistsError):
            self.store.copy("held.apk", fd, len(data), digest, self.budget)

    def test_wrong_copy_bytes_rejected_before_use(self):
        source = Path(self.temp.name) / "source"
        source.write_bytes(b"PK\x03\x04wrong")
        fd = self.fds.own(os.open(source, os.O_RDONLY))
        with self.assertRaises(m.Rejected):
            self.store.copy("rejected.apk", fd, source.stat().st_size, "0" * 64, self.budget)

    def test_client_timeout_is_joined_but_never_claims_daemon_join(self):
        executable = self.fds.own(os.open("/usr/bin/sleep", os.O_RDONLY))
        raw, row = m.run_command(self.store, executable,
            ("/usr/bin/sleep", "10"),
            "timeout-test", 0.15, self.budget)
        self.assertEqual(raw, b"")
        self.assertTrue(row["spawned"])
        self.assertTrue(row["joined"])
        self.assertTrue(row["timed_out"])
        self.assertFalse(row["native_daemon_worker_joined_by_this_client"])
        self.assertFalse(row["output_capture_complete"])
        self.assertTrue(row["group_termination_requested"])
        self.assertEqual((Path(self.temp.name) / "timeout-test.stdout").read_bytes(), raw)
        self.assertFalse(row["automatic_retry"])

    def test_fd_passed_to_native_style_child_survives_and_matches_bytes(self):
        executable = self.fds.own(os.open("/usr/bin/cat", os.O_RDONLY))
        source = Path(self.temp.name) / "candidate"
        source.write_bytes(b"PK\x03\x04data")
        candidate = self.fds.own(os.open(source, os.O_RDONLY))
        raw, row = m.run_command(self.store, executable,
            ("/usr/bin/cat", "/proc/self/fd/" + str(candidate)),
            "pass-fd-test", 30, self.budget, extra_fds=(candidate,))
        self.assertEqual(raw, source.read_bytes())
        self.assertTrue(row["joined"])
        self.assertEqual(row["returncode"], 0)
        self.assertTrue(row["output_capture_complete"])


if __name__ == "__main__":
    unittest.main()
