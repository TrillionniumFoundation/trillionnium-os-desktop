"""Real Linux sealed archive custody and borrowed-path host lifecycle tests."""
from __future__ import annotations

import copy
import errno
import fcntl
import gc
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from tools import mozjs_secondary_input as archive
from tools import build_mozjs_locked_native as build


def setUpModule():
    if sys.platform != "linux" or not hasattr(os, "memfd_create"):
        raise RuntimeError("actual Linux memfd/procfs/fork required; no skipped qualification")


def descriptors():
    return set(os.listdir("/proc/self/fd"))


class StopHere(BaseException):
    pass


class SecondaryArchiveLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mozjs-input-host-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "archive"
        self.raw = b"real bounded archive fixture\0" * 307
        self.path.write_bytes(self.raw)
        self.digest = hashlib.sha256(self.raw).hexdigest()

    def lease(self):
        return archive._lease_archive(self.path, len(self.raw), self.digest)

    def test_manifest_exact_profile_and_no_attestation_claim(self):
        value = archive.load_manifest()
        self.assertEqual(value, archive.PROFILE)
        self.assertFalse(value["correspondence"]["attestation_verified"])
        self.assertFalse(value["build_profile"]["actual_cargo_archive_consumption_proven"])
        self.assertEqual(value["secondary_input"]["bytes"], 19381534)

    def test_closed_manifest_rejects_unknown_bool_size_digest_profile_drift(self):
        for mutate in [lambda x: x.update(extra=True),
                       lambda x: x["secondary_input"].update(bytes=True),
                       lambda x: x["secondary_input"].update(sha256="0" * 64),
                       lambda x: x["claims"].update(artifact_attestation=True),
                       lambda x: x["build_profile"].update(features="bundled")]:
            value = copy.deepcopy(archive.PROFILE); mutate(value)
            with self.assertRaises(ValueError): archive.check_manifest(value)

    def test_real_sealed_bytes_proc_path_and_close_inventory(self):
        before = descriptors()
        with self.lease() as value:
            path = value.stable_path()
            self.assertTrue(path.startswith(f"/proc/{os.getpid()}/fd/"))
            self.assertEqual(Path(path).read_bytes(), self.raw)
            self.assertEqual(value.readback(), {"bytes": len(self.raw), "sha256": self.digest, "sealed": True})
            self.assertEqual(fcntl.fcntl(value._owner.fd, fcntl.F_GET_SEALS), archive.SEALS)
        self.assertEqual(descriptors(), before)
        self.assertFalse(Path(path).exists())

    def test_real_write_shrink_grow_and_seal_removal_refused(self):
        with self.lease() as value:
            for operation in [lambda: os.pwrite(value._owner.fd, b"x", 0),
                              lambda: os.ftruncate(value._owner.fd, 0),
                              lambda: os.ftruncate(value._owner.fd, len(self.raw) + 1),
                              lambda: fcntl.fcntl(value._owner.fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE)]:
                with self.assertRaises(OSError) as refused: operation()
                self.assertEqual(refused.exception.errno, errno.EPERM)
            self.assertEqual(value.readback()["sha256"], self.digest)

    def test_actual_child_reads_same_snapshot_after_original_name_replaced(self):
        with self.lease() as value:
            path = value.stable_path(); self.path.unlink(); self.path.write_bytes(b"replacement")
            child = subprocess.run([sys.executable, "-c", "import hashlib,os;print(hashlib.sha256(open(os.environ['MOZJS_ARCHIVE'],'rb').read()).hexdigest())"],
                                   env={"MOZJS_ARCHIVE": path}, capture_output=True, text=True, timeout=5)
            self.assertEqual(child.returncode, 0, child.stderr)
            self.assertEqual(child.stdout.strip(), self.digest)
            self.assertEqual(value.readback()["sha256"], self.digest)

    def test_wrong_size_digest_and_byte_bound_refused_without_fd_leak(self):
        before = descriptors()
        for size, digest in [(len(self.raw) - 1, self.digest), (len(self.raw), "0" * 64),
                             (0, self.digest), (True, self.digest), (archive.MAX_ARCHIVE_BYTES + 1, self.digest)]:
            with self.assertRaises(ValueError): archive._lease_archive(self.path, size, digest)
        gc.collect(); self.assertEqual(descriptors(), before)

    def test_actual_symlink_hardlink_directory_fifo_refused(self):
        before = descriptors(); symlink = self.root / "symlink"; symlink.symlink_to(self.path)
        hardlink = self.root / "hardlink"; os.link(self.path, hardlink)
        fifo = self.root / "fifo"; os.mkfifo(fifo)
        for path in [self.path, symlink, hardlink, self.root, fifo]:
            with self.assertRaises((ValueError, OSError)): archive._lease_archive(path, len(self.raw), self.digest)
        gc.collect(); self.assertEqual(descriptors(), before)

    def test_source_name_replacement_during_actual_read_refused(self):
        from tools import browser_codec_reference_security as source
        actual = source.ManagedSourceReader.read_some; replaced = False; before = descriptors()
        def read(reader, size):
            nonlocal replaced
            raw = actual(reader, size)
            if not replaced:
                self.path.unlink(); self.path.write_bytes(self.raw); replaced = True
            return raw
        with patch.object(source.ManagedSourceReader, "read_some", read), self.assertRaises(ValueError): self.lease()
        gc.collect(); self.assertEqual(descriptors(), before)

    def test_real_partial_write_interruption_releases_owner(self):
        actual = archive.os.write; before = descriptors()
        def write(fd, data):
            actual(fd, data[:3]); raise StopHere()
        with patch.object(archive.os, "write", write), self.assertRaises(StopHere): self.lease()
        gc.collect(); self.assertEqual(descriptors(), before)

    def test_undelivered_archive_factory_return_releases_owner(self):
        before = descriptors()
        def trace(frame, event, arg):
            if frame.f_code is archive._lease_archive.__code__ and event == "return": raise StopHere()
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(StopHere): self.lease()
        finally: sys.settrace(None)
        gc.collect(); self.assertEqual(descriptors(), before)

    def test_real_proc_read_then_interruption_releases_borrowed_fd(self):
        with self.lease() as value:
            before = descriptors(); actual = archive.os.pread
            def read(fd, size, offset):
                actual(fd, size, offset); raise StopHere()
            with patch.object(archive.os, "pread", read), self.assertRaises(StopHere): value.readback()
            self.assertEqual(descriptors(), before)
            self.assertEqual(value.readback()["sha256"], self.digest)

    def test_proc_read_callback_reentry_refused_without_retirement(self):
        with self.lease() as value:
            actual = archive.os.pread; refused = []
            def read(fd, size, offset):
                for operation in [value.close, value.stable_path, value.readback, value.__enter__]:
                    try: operation()
                    except ValueError: refused.append(True)
                    else: refused.append(False)
                return actual(fd, size, offset)
            with patch.object(archive.os, "pread", read): value.readback()
            self.assertTrue(refused); self.assertTrue(all(refused))
            self.assertEqual(value.readback()["sha256"], self.digest)

    def test_actual_foreign_thread_cannot_read_borrow_or_close(self):
        with self.lease() as value:
            results = []
            def use():
                for method in [value.readback, value.stable_path, value.close, value.__enter__]:
                    try: method()
                    except ValueError: results.append(True)
                    else: results.append(False)
            thread = threading.Thread(target=use); thread.start(); thread.join(5)
            self.assertFalse(thread.is_alive()); self.assertEqual(results, [True] * 4)
            self.assertEqual(value.readback()["sha256"], self.digest)

    def test_actual_fork_cannot_use_creator_lease_parent_remains_current(self):
        with self.lease() as value:
            read, write = os.pipe(); pid = os.fork()
            if pid == 0:
                os.close(read)
                try:
                    count = 0
                    for method in [value.readback, value.stable_path, value.close]:
                        try: method()
                        except ValueError: count += 1
                    os.write(write, str(count).encode())
                finally: os._exit(0)
            os.close(write)
            try:
                self.assertTrue(select.select([read], [], [], 5)[0]); self.assertEqual(os.read(read, 8), b"3")
            finally: os.close(read); os.waitpid(pid, 0)
            self.assertEqual(value.readback()["sha256"], self.digest)

    def test_actual_descriptor_close_reuse_refused_never_closes_foreign_fd(self):
        value = self.lease(); original = value._owner.fd; os.close(original)
        foreign = os.open(self.path, os.O_RDONLY | os.O_CLOEXEC)
        if foreign != original: os.dup2(foreign, original)
        try:
            with self.assertRaises(ValueError): value.readback()
            value.close(); self.assertEqual(os.read(original, len(self.raw)), self.raw)
            del value; gc.collect(); os.fstat(original)
        finally:
            os.close(original)
            if foreign != original: os.close(foreign)

    def test_closed_borrowed_path_and_incomplete_public_constructor_refused(self):
        value = self.lease(); path = value.stable_path(); value.close(); value.close()
        for method in [value.readback, value.stable_path, value.__enter__]:
            with self.assertRaises(ValueError): method()
        with self.assertRaises(FileNotFoundError): Path(path).read_bytes()
        with self.assertRaises(ValueError): archive.SealedArchiveLease().stable_path()

    def test_new_fixed_compile_profile_keeps_original_features_targets_and_bounds(self):
        for profile, target in [("native-owner", "trillionnium_product_owner"), ("approved-startup", "trillionnium_approved_connected")]:
            self.assertEqual(build.compile_argv(profile), ["cargo", "test", "--locked", "--profile", "checked-release", "-p", "servo", "--no-default-features", "--features", "bundled,js_jit", "--test", target, "--no-run", "--message-format=json"])
        with self.assertRaises(ValueError): build.compile_argv("unreviewed")
        self.assertEqual(build.TIMEOUT_SECONDS, 10800); self.assertEqual(build.GRACE_SECONDS, 5)

    def test_all_inherited_archive_feature_wrapper_target_overrides_refused(self):
        for key in ["MOZJS_FROM_SOURCE", "MOZJS_CREATE_ARCHIVE", "MOZJS_ARCHIVE", "MOZJS_ATTESTATION", "MOZJS_UNKNOWN", "CARGO_FEATURE_INTL", "CARGO_PROFILE_CHECKED_RELEASE_DEBUG", "CARGO_TARGET_DIR", "CARGO_BUILD_TARGET", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTC", "RUSTUP_TOOLCHAIN", "CARGO_INCREMENTAL", "CARGO_BUILD_JOBS"]:
            with self.assertRaises(ValueError): build.profile_environment({key: ""}, "/proc/unused", self.root)
        env = build.profile_environment({"PATH": "/usr/bin", "CARGO_BUILD_JOBS": "2", "RUSTUP_TOOLCHAIN": "1.97.1"}, "/proc/fixed", self.root)
        self.assertEqual(env["MOZJS_ARCHIVE"], "/proc/fixed")
        self.assertEqual(env["CARGO_TARGET_DIR"], str(self.root))
        self.assertEqual(env["RUSTUP_TOOLCHAIN"], "1.97.1")

    def test_real_process_consumes_sealed_path_and_finishes_before_close(self):
        before = descriptors()
        with self.lease() as value:
            path = value.stable_path(); receipt = self.root / "receipt"
            argv = [sys.executable, "-c", "import hashlib,os,pathlib;pathlib.Path(os.environ['RECEIPT']).write_text(hashlib.sha256(open(os.environ['MOZJS_ARCHIVE'],'rb').read()).hexdigest())"]
            env = {"MOZJS_ARCHIVE": path, "RECEIPT": str(receipt)}
            self.assertEqual(build._run_with_lease(value, argv, self.root, env, 5, 0.1), 0)
            self.assertEqual(receipt.read_text(), self.digest)
            self.assertEqual(value.readback()["sha256"], self.digest)
        self.assertEqual(descriptors(), before); self.assertFalse(Path(path).exists())

    def test_actual_nonzero_child_exit_has_bounded_reap_and_current_lease(self):
        with self.lease() as value:
            result = build._run_with_lease(value, [sys.executable, "-c", "raise SystemExit(7)"], self.root, {}, 5, 0.1)
            self.assertEqual(result, 7); self.assertEqual(value.readback()["sha256"], self.digest)

    def test_actual_timeout_kills_reaps_child_before_releasing_archive(self):
        before = descriptors()
        with self.lease() as value:
            receipt = self.root / "pid"
            code = "import os,pathlib,signal,time;pathlib.Path(os.environ['PID']).write_text(str(os.getpid()));signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(20)"
            with self.assertRaises(subprocess.TimeoutExpired):
                build._run_with_lease(value, [sys.executable, "-c", code], self.root, {"PID": str(receipt)}, 3, 0.5)
            pid = int(receipt.read_text())
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
            self.assertFalse(build._group_exists(pid))
            self.assertEqual(value.readback()["sha256"], self.digest)
        self.assertEqual(descriptors(), before)

    def test_actual_started_child_then_cancel_still_killed_and_waited(self):
        with self.lease() as value:
            actual = build._BuildProcess.start; pids = []
            def start(owner, *args):
                actual(owner, *args); pids.append(owner.process.pid); raise StopHere()
            with patch.object(build._BuildProcess, "start", start), self.assertRaises(StopHere):
                build._run_with_lease(value, [sys.executable, "-c", "import time;time.sleep(20)"], self.root, {}, 5, 0.1)
            self.assertEqual(len(pids), 1)
            with self.assertRaises(ProcessLookupError): os.kill(pids[0], 0)
            self.assertFalse(build._group_exists(pids[0]))
            self.assertEqual(value.readback()["sha256"], self.digest)

    def test_actual_child_and_grandchild_group_end_before_lease_release(self):
        with self.lease() as value:
            receipt = self.root / "pids"
            code = """import os,pathlib,signal,subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])
def stop(signum,frame):
    child.wait(timeout=2)
    raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
pathlib.Path(os.environ['PIDS']).write_text(str(os.getpid())+' '+str(child.pid))
time.sleep(20)
"""
            with self.assertRaises(subprocess.TimeoutExpired):
                build._run_with_lease(value, [sys.executable, "-c", code], self.root, {"PIDS": str(receipt)}, 3, 0.5)
            pids = [int(x) for x in receipt.read_text().split()]
            self.assertEqual(len(pids), 2)
            for pid in pids:
                with self.assertRaises(ProcessLookupError): os.kill(pid, 0)
            self.assertFalse(build._group_exists(pids[0]))
            self.assertEqual(value.readback()["sha256"], self.digest)

    def test_actual_supervisor_SIGTERM_unwinds_wait_before_archive_close(self):
        ready = self.root / "ready"; done = self.root / "done"
        code = """import hashlib,os,pathlib,signal,sys
from tools import mozjs_secondary_input as a,build_mozjs_locked_native as b
path=pathlib.Path(sys.argv[1]);raw=path.read_bytes()
with a._lease_archive(path,len(raw),hashlib.sha256(raw).hexdigest()) as lease:
    borrowed=lease.stable_path()
    original=b._BuildProcess.start
    def start(owner,*args):
        original(owner,*args)
        pathlib.Path(sys.argv[2]).write_text(str(owner.process.pid))
    b._BuildProcess.start=start
    signal.signal(signal.SIGTERM,b._cancel_from_signal)
    try:
        b._run_with_lease(lease,[sys.executable,'-c','import time;time.sleep(20)'],path.parent,{},10,.1)
    except KeyboardInterrupt:
        assert lease.readback()['sha256']==hashlib.sha256(raw).hexdigest()
pathlib.Path(sys.argv[3]).write_text(str(pathlib.Path(borrowed).exists()))
"""
        child = subprocess.Popen([sys.executable, "-c", code, str(self.path), str(ready), str(done)], cwd=archive.ROOT)
        try:
            import time
            end = time.monotonic() + 5
            while not ready.exists() and child.poll() is None and time.monotonic() < end: time.sleep(.01)
            self.assertTrue(ready.exists()); launched = int(ready.read_text())
            os.kill(child.pid, signal.SIGTERM)
            self.assertEqual(child.wait(timeout=5), 0)
            with self.assertRaises(ProcessLookupError): os.kill(launched, 0)
            self.assertFalse(build._group_exists(launched)); self.assertEqual(done.read_text(), "False")
        finally:
            if child.poll() is None: child.kill()
            child.wait(timeout=5)


if __name__ == "__main__": unittest.main()
