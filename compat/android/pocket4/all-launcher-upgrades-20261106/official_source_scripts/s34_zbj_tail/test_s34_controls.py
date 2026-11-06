#!/usr/bin/env python3
"""Local s34 controls: no curl, network, Android, or Main; only owned host children."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("s34_candidate", HERE / "resume_zbj_tail_s34_once.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

def census():
    result = {}
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        try:
            st = os.fstat(fd)
            result[fd] = (os.readlink("/proc/self/fd/" + name), st.st_dev, st.st_ino, st.st_mode)
        except FileNotFoundError:
            continue
        except OSError as error:
            if error.errno == 9:
                continue
            raise
    return result

def rejected(call, reason):
    try:
        call()
    except RuntimeError as error:
        if str(error) != reason:
            raise AssertionError((str(error), reason)) from error
    else:
        raise AssertionError("unexpected acceptance: " + reason)

class Controls(unittest.TestCase):
    events = []
    def setUp(self):
        self.initial = census()
        worker.DEADLINE = time.monotonic() + 60
    def tearDown(self):
        self.assertEqual(self.initial, census())

    def test_actual_failed_range_excluded_and_full_tail_coverage(self):
        raw = (HERE / "actual-s28-package-result.json").read_bytes()
        self.assertEqual(len(raw), 28307)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
            "d4bac41dee796ae163b4dabeccc87153d6f95c2191cde4a3eeac71fd9c2b3dde")
        previous = json.loads(raw)
        self.assertEqual([r["index"] for r in previous["segment_receipts"] if r["status"] == "COMPLETE"],
                         list(range(41)))
        self.assertEqual(previous["segment_receipts"][41]["status"], "FAILED")
        failed = json.loads((PROJECT / "reference/official-s24-s33-restored/s28/0041.json").read_bytes())
        self.assertEqual(failed["partial_bytes"], 147456)
        self.assertEqual(failed["returncode"], 18)
        rejected(lambda: worker.validate_origin(worker.CANDIDATES[0], failed, "/unused", 41),
                 "EXACT_OLD_COMPLETE_RANGE_REQUIRED")
        plan = worker.tail_plan(worker.CANDIDATES[0])
        self.assertEqual(len(plan), 41)
        self.assertEqual(plan[0], (0, 124370944, 125419519))
        self.assertEqual(plan[-1], (40, 166313984, 166873621))
        self.assertEqual(plan[-1][2] - plan[-1][1] + 1, 559638)
        self.assertEqual(sum(e-s+1 for _, s, e in plan), 42502678)
        self.assertTrue(all(0 < e-s+1 <= 1048576 for _, s, e in plan))
        self.assertTrue(all(a[2] + 1 == b[1] for a, b in zip(plan, plan[1:])))
        self.assertEqual(38387712 + 41 * 2097152, plan[0][1])
        changed = dict(worker.CANDIDATES[0], total_bytes=166873623)
        rejected(lambda: worker.tail_plan(changed), "EXACT_TOTAL_REQUIRED")
        self.events.append({"name": "actual_failed_147456_bytes_excluded_and_tail_exact",
                            "ranges": 41, "tail_bytes": 42502678, "result": "PASS"})

    def test_response_boundaries(self):
        c = copy.deepcopy(worker.CANDIDATES[0])
        start, end = 124370944, 125419519
        item = {"start": start, "end": end, "bytes": 1048576, "returncode": 0,
                "joined": True, "timed_out": False,
                "curl": {"http_code": 206, "url_effective": c["url"], "num_redirects": 0,
                         "num_retries": 0, "ssl_verify_result": 0, "exitcode": 0,
                         "size_download": 1048576}}
        header = ("HTTP/2 206\r\nContent-Range: bytes 124370944-125419519/166873622\r\n"
                  "Content-Length: 1048576\r\nETag: \"fixture-entity\"\r\n\r\n")
        self.assertEqual(worker.validate_response(c, item, header), ['"fixture-entity"'])
        self.assertEqual(worker.validate_response(c, item, header.replace("Content-Length: 1048576\r\n", "")),
                         ['"fixture-entity"'])
        rejected(lambda: worker.validate_response(c, item, header.replace("/166873622", "/166873623")),
                 "EXACT_CONTENT_RANGE_REQUIRED")
        rejected(lambda: worker.validate_response(c, item, header.replace("Content-Length: 1048576", "Content-Length: 1")),
                 "CONTENT_LENGTH_CONTRADICTS_COMPLETE_RANGE")
        rejected(lambda: worker.validate_response(c, item, header + "Retry-After: 120\r\n"),
                 "RETRY_AFTER_REFUSAL_RESPECTED")
        short = copy.deepcopy(item); short["bytes"] = 147456
        rejected(lambda: worker.validate_response(c, short, header), "COMPLETE_RANGE_BODY_REQUIRED")
        for key, value in (("http_code", 403), ("http_code", 429), ("ssl_verify_result", 9),
                           ("num_retries", 1), ("num_redirects", 1), ("url_effective", "https://invalid.example/")):
            bad = copy.deepcopy(item); bad["curl"][key] = value
            rejected(lambda bad=bad: worker.validate_response(c, bad, header),
                     "EXACT_SECURE_RANGE_RESPONSE_REQUIRED")
        rejected(lambda: worker.header_etags(header + "ETag: \"other\"\r\n"),
                 "AMBIGUOUS_ENTITY_TAG")
        self.events.append({"name": "exact_range_tls_origin_retry_and_short_body_refusals",
                            "synthetic_response_fixture": True, "result": "PASS"})

    def test_refusal_sets_abort_and_next_range_starts_no_child(self):
        c = copy.deepcopy(worker.CANDIDATES[0]); c["expected_etags"] = []
        calls = []
        actual_own_curl = worker.own_curl
        fixture = ("import json,pathlib,sys\n"
                   "pathlib.Path(sys.argv[1]).write_bytes(b'HTTP/2 429\\r\\nRetry-After: 60\\r\\nContent-Length: 0\\r\\n\\r\\n')\n"
                   "print(json.dumps(dict(http_code=429,url_effective=sys.argv[2],content_type='application/octet-stream',"
                   "size_download=0,time_total=0,speed_download=0,num_redirects=0,num_retries=0,"
                   "ssl_verify_result=0,errormsg='synthetic host-only refusal',exitcode=22)))\n"
                   "raise SystemExit(22)\n")
        def fixture_child(argv, fd, metrics, errors, record, seconds):
            calls.append(list(argv))
            header = argv[argv.index("--dump-header") + 1]
            return actual_own_curl([sys.executable, "-I", "-B", "-c", fixture, header, c["url"]],
                                   fd, metrics, errors, record, seconds)
        with tempfile.TemporaryDirectory(prefix="s34-refusal-control-") as temp:
            folder = Path(temp); abort = worker.threading.Event()
            with mock.patch.object(worker, "own_curl", fixture_child), mock.patch.object(worker.time, "sleep", lambda _: None):
                with contextlib.redirect_stdout(io.StringIO()):
                    first = worker.one_segment(c, folder, 0, 124370944, 125419519, abort)
                    second = worker.one_segment(c, folder, 1, 125419520, 126468095, abort)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][:2], ["/usr/bin/curl", "--disable"])
            self.assertEqual(calls[0][calls[0].index("--retry") + 1], "0")
            self.assertEqual(calls[0][calls[0].index("--user-agent") + 1], "Mozilla/5.0")
            self.assertEqual(calls[0][-1], c["url"])
            self.assertEqual(first["status"], "FAILED")
            self.assertTrue(first["http_refusal_respected"] and first["joined"] and first["pidfd_exit_observed"])
            self.assertTrue(first["pidfd_closed"])
            self.assertEqual(first["owned_curl_signal_count"], 0)
            self.assertTrue(abort.is_set())
            self.assertEqual(second["status"], "SKIPPED_AFTER_OTHER_RANGE_FAILURE")
            self.assertEqual(second["request_attempts"], 0)
            self.assertNotIn("pid", second)
            self.events.append({"name": "synthetic_http429_actual_owned_host_child_then_no_next_child",
                                "pid": first["pid"], "returncode": 22,
                                "pidfd_exit_observed": True, "pidfd_closed": True, "result": "PASS"})

    def test_normal_owned_child_join_and_close(self):
        with tempfile.TemporaryDirectory(prefix="s34-child-control-") as temp:
            base = Path(temp); fd = os.open(base/"body", os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            record = {}
            try:
                result = worker.own_curl([sys.executable, "-I", "-B", "-c", "print('owned local fixture')"],
                                        fd, base/"metrics", base/"stderr", record, 5)
            finally:
                os.close(fd)
            self.assertEqual(result, 0)
            self.assertTrue(record["joined"] and record["pidfd_acquired"] and record["pidfd_closed"]
                            and record["pidfd_exit_observed"])
            self.assertFalse(record["outcome_unknown"] or record["timed_out"])
            self.assertEqual(record["owned_curl_signal_count"], 0)
            self.events.append({"name": "owned_child_normal_exit", "pid": record["pid"],
                                "joined": True, "pidfd_closed": True, "signal_count": 0, "result": "PASS"})

    def test_timeout_only_owned_pidfd_and_join(self):
        with tempfile.TemporaryDirectory(prefix="s34-timeout-control-") as temp:
            base = Path(temp); fd = os.open(base/"body", os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            record = {}; worker.DEADLINE = time.monotonic() + 10.4
            try:
                rejected(lambda: worker.own_curl(
                    [sys.executable, "-I", "-B", "-c", "import time; time.sleep(30)"],
                    fd, base/"metrics", base/"stderr", record, .01), "OWNED_CURL_DEADLINE")
            finally:
                os.close(fd)
            self.assertTrue(record["joined"] and record["pidfd_exit_observed"] and record["pidfd_closed"])
            self.assertTrue(record["timed_out"])
            self.assertFalse(record["outcome_unknown"])
            self.assertEqual(record["owned_curl_signal_count"], 1)
            self.assertEqual(record["returncode"], -signal.SIGKILL)
            self.events.append({"name": "owned_child_timeout_pidfd_signal_once_then_join",
                                "pid": record["pid"], "signal_count": 1,
                                "pidfd_exit_observed": True, "pidfd_closed": True, "result": "PASS"})

    def test_real_owned_file_path_replacement_detected(self):
        self.assertEqual(os.getuid(), 1000)
        self.assertEqual(os.geteuid(), 1000)
        with tempfile.TemporaryDirectory(prefix="s34-file-control-") as temp:
            path = Path(temp)/"piece"; path.write_bytes(b"owned fixture only")
            fd, before = worker.opened(path)
            try:
                self.assertEqual(worker.hashes(fd)[:2], (18, hashlib.sha256(b"owned fixture only").hexdigest()))
                worker.verify_path(path, before)
                moved = Path(temp)/"retained-original"; path.rename(moved); path.write_bytes(b"owned fixture only")
                rejected(lambda: worker.verify_path(path, before), "DECLARED_PATH_REPLACED")
                self.assertEqual(worker.identity(fd)["st_ino"], before["st_ino"])
            finally:
                os.close(fd)
        self.events.append({"name": "same_bytes_replaced_path_rejected_without_closing_held_source",
                            "actual_uid": 1000, "result": "PASS"})

if __name__ == "__main__":
    before = census()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Controls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = census()
    report = {"schema": "pocket4-zbj-s34-local-controls-v1", "success": result.wasSuccessful() and before == after,
              "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
              "skips": len(result.skipped), "cases": Controls.events, "fd_before": len(before), "fd_after": len(after),
              "full_fd_identity_restored": before == after, "Main_actions": 0, "network_requests": 0,
              "curl_executions": 0, "actual_download_status": "NOT_RUN",
              "source_sha256": hashlib.sha256((HERE/"resume_zbj_tail_s34_once.py").read_bytes()).hexdigest()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["success"] else 1)

