"""Real regular-file/FD custody tests; no runtime or authority qualification."""
from __future__ import annotations

import ast
import copy
import errno
import gc
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

from tools import artifact_evidence as artifact
from tools import browser_codec_reference_security as reader

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "schema": "trillionnium.shared-managed-reader.v1",
    "implementation": {"shared": "tools/browser_codec_reference_security.py", "artifact": "tools/artifact_evidence.py"},
    "public_api": {
        "open_managed_regular_beneath": "(root: 'Path', path: 'Path', *, label: 'str', after_component: 'AfterComponentHook | None' = None) -> 'ManagedSourceReader'",
        "ManagedSourceReader.__init__": "(self) -> 'None'",
        "ManagedSourceReader.read": "(self, size: 'int' = -1) -> 'bytes'",
        "ManagedSourceReader.stat": "(self) -> 'os.stat_result'",
        "ManagedSourceReader.close": "(self) -> 'None'",
        "ManagedSourceReader.__enter__": "(self) -> 'ManagedSourceReader'",
        "ManagedSourceReader.__exit__": "(self, exc_type, exc_value, traceback) -> 'None'",
        "open_managed_file": "(path: 'Path') -> 'ManagedSourceReader'",
    },
    "migrated": {
        "shared": ["read_bytes_beneath", "read_bytes_nofollow", "read_text_nofollow", "load_json_nofollow", "regular_file_exists_nofollow"],
        "artifact": ["file_size", "digest", "load", "artifact_file"],
    },
    "read": {
        "size": "exact int -1 or 0..sys.maxsize; bool and other negative values refused",
        "short_read": "continue until requested count or actual EOF", "native_interrupt": "propagate; retain owner for cleanup",
        "shared_existing_unbounded_reads": True, "artifact_json_bytes_maximum": 8388608,
        "artifact_file_bytes_maximum": 8589934592, "utf8_and_universal_newlines_preserved": True,
    },
    "custody": {
        "same_private_descriptor_owner": True, "public_raw_fd_extraction": False,
        "creator_pid_and_thread_operations": True, "reentrant_read_stat_and_close_refused": True,
        "reentrant_public_context_exit_refused": True, "active_operation_stack_frames_maximum": 1024,
        "last_reference_foreign_thread_descriptor_cleanup": True,
        "owning_fdopen_transfer": False, "managed_object_return_loss_cleanup": True,
        "ordinary_line_and_data_return_cleanup": True, "attempted_close_never_retried": True,
        "all_c_opcode_and_repeated_cleanup_faults": False,
    },
    "compatibility": {
        "open_regular_beneath_returns_int": True, "open_file_returns_int": True,
        "raw_result_delivery_protected": False, "external_raw_fdopen_consumers_migrated": False,
        "old_path_regular_and_artifact_single_link_checks_preserved": True,
        "old_readback_and_byte_bounds_preserved": True,
    },
    "source_index": {"module": "hepta-browser-codec", "tests": "tests/test_shared_managed_reader.py",
                     "context_tests": "tests/test_shared_managed_context.py",
                     "documentation": "docs/architecture/SHARED_MANAGED_READER.md"},
    "claims": {"source_file_io_only": True, "peer_principal_or_signature_authority": False,
               "installed_native_or_boot_qualification": False, "product_activation_changed": False,
               "production_ready": False},
}


def validate_contract(value):
    if json.dumps(value, sort_keys=True) != json.dumps(EXPECTED, sort_keys=True):
        raise ValueError("managed source contract differs from the closed profile")


def census():
    result = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            value = os.fstat(int(name))
            result[int(name)] = (value.st_dev, value.st_ino, value.st_mode)
        except OSError as error:
            if error.errno != errno.EBADF:
                raise
    return result


class SharedManagedReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="managed-reader-")
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.parent = self.root / "parent"; self.parent.mkdir(mode=0o700)
        self.path = self.parent / "file.json"; self.path.write_bytes(b'{"original":true}\r\n')

    def tearDown(self):
        self.temporary.cleanup()

    def acquire(self):
        return reader.open_managed_regular_beneath(self.root, self.path, label="actual managed source")

    def consume(self):
        with self.acquire() as owned:
            return owned.read()

    def cut(self, operation, code, event, line=None):
        before = census(); fired = []
        def trace(frame, observed, value):
            if frame.f_code is code and observed == event and not fired and (line is None or frame.f_lineno == line):
                fired.append(frame.f_lineno)
                raise KeyboardInterrupt("one ordinary managed-reader interruption")
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt): operation()
        finally:
            sys.settrace(previous)
        gc.collect()
        self.assertEqual(len(fired), 1)
        self.assertEqual(census(), before)

    def test_closed_contract_catalog_bounds_claims_and_module_index(self):
        value = json.loads((ROOT / "contracts/shared-managed-reader.v1.json").read_bytes())
        validate_contract(value)
        objects = {"open_managed_regular_beneath": reader.open_managed_regular_beneath,
                   "open_managed_file": artifact.open_managed_file}
        for name in EXPECTED["public_api"]:
            if name.startswith("ManagedSourceReader."):
                objects[name] = getattr(reader.ManagedSourceReader, name.split(".")[1])
        self.assertEqual({name: str(inspect.signature(value)) for name, value in objects.items()}, EXPECTED["public_api"])
        self.assertEqual(artifact.MAX_JSON_BYTES, EXPECTED["read"]["artifact_json_bytes_maximum"])
        self.assertEqual(artifact.MAX_ARTIFACT_FILE_BYTES, EXPECTED["read"]["artifact_file_bytes_maximum"])
        for section, field, value in [("claims", "production_ready", True), ("claims", "source_file_io_only", 1),
                                      ("read", "artifact_json_bytes_maximum", 8388608.0),
                                      ("compatibility", "raw_result_delivery_protected", True)]:
            mutant = copy.deepcopy(EXPECTED); mutant[section][field] = value
            with self.assertRaises(ValueError): validate_contract(mutant)
        missing = copy.deepcopy(EXPECTED); del missing["custody"]["all_c_opcode_and_repeated_cleanup_faults"]
        with self.assertRaises(ValueError): validate_contract(missing)
        extra = copy.deepcopy(EXPECTED); extra["claims"]["caller_confirmed_safe"] = True
        with self.assertRaises(ValueError): validate_contract(extra)
        index = json.loads((ROOT / "manifests/modules.v1.json").read_bytes())
        module = next(v for v in index["modules"] if v["id"] == EXPECTED["source_index"]["module"])
        for key, value in [("contracts", "contracts/shared-managed-reader.v1.json"),
                           ("tests", EXPECTED["source_index"]["tests"]),
                           ("architecture", EXPECTED["source_index"]["documentation"])]:
            self.assertIn(value, module[key])

    def test_managed_object_has_no_public_fd_transfer_and_preserves_actual_bytes(self):
        before = census()
        with self.acquire() as owned:
            self.assertIs(type(owned), reader.ManagedSourceReader)
            self.assertFalse(hasattr(owned, "fileno"))
            self.assertFalse(hasattr(owned, "detach"))
            self.assertEqual(owned.stat().st_ino, self.path.stat().st_ino)
            self.assertEqual(owned.read(), self.path.read_bytes())
            self.assertEqual(owned.read(), b"")
        with self.assertRaises(ValueError): owned.read()
        owned.close(); gc.collect(); self.assertEqual(census(), before)

    def test_read_size_types_zero_negative_overflow_short_reads_and_actual_eof(self):
        with self.acquire() as owned:
            for value in [True, False, 1.0, None, "1"]:
                with self.subTest(value=value), self.assertRaises(TypeError): owned.read(value)
            with self.assertRaises(ValueError): owned.read(-2)
            with self.assertRaises(OverflowError): owned.read(sys.maxsize + 1)
            self.assertEqual(owned.read(0), b"")
            native = os.read
            with mock.patch.object(reader.os, "read", side_effect=lambda fd, count: native(fd, min(count, 2))):
                self.assertEqual(owned.read(5), self.path.read_bytes()[:5])
                self.assertEqual(owned.read(-1), self.path.read_bytes()[5:])
            self.assertEqual(owned.read(3), b"")

    def test_empty_constructor_and_utf8_universal_newline_compatibility(self):
        before = census()
        closed = reader.ManagedSourceReader()
        for operation in [closed.read, closed.stat, closed.__enter__]:
            with self.assertRaises(ValueError): operation()
        closed.close(); self.assertEqual(census(), before)
        self.path.write_bytes("α\r\nbeta\rgamma\n".encode("utf-8"))
        with mock.patch.object(reader, "ROOT", self.root):
            self.assertEqual(reader.read_text_nofollow(self.path), "α\nbeta\ngamma\n")
            self.path.write_bytes(b"\xff")
            with self.assertRaises(UnicodeDecodeError): reader.read_text_nofollow(self.path)
        gc.collect(); self.assertEqual(census(), before)

    def test_new_acquisition_enter_and_private_owned_return_loss_do_not_leak(self):
        for code, operation in [(reader.ManagedSourceReader.__init__.__code__, self.consume),
                                (reader._open_regular_owned_beneath.__code__, self.consume),
                                (reader.open_managed_regular_beneath.__code__, self.consume),
                                (reader.ManagedSourceReader.__enter__.__code__, self.consume),
                                (artifact.open_managed_file.__code__, lambda: artifact.load(self.path))]:
            with self.subTest(code=code.co_name): self.cut(operation, code, "return")

    def test_all_observed_managed_ordinary_lines_and_data_return_cuts_keep_owner(self):
        codes = {reader.open_managed_regular_beneath.__code__, reader.ManagedSourceReader.__init__.__code__,
                 reader.ManagedSourceReader.read.__code__, reader.ManagedSourceReader.stat.__code__,
                 reader.ManagedSourceReader.__enter__.__code__, reader.ManagedSourceReader.__exit__.__code__,
                 reader.ManagedSourceReader.close.__code__}
        observed = set()
        def record(frame, event, value):
            if event == "line" and frame.f_code in codes: observed.add((frame.f_code, frame.f_lineno))
            return record
        previous = sys.gettrace()
        try:
            sys.settrace(record)
            with self.acquire() as owned: owned.stat(); owned.read()
        finally: sys.settrace(previous)
        self.assertGreater(len(observed), 15)
        def operation():
            with self.acquire() as owned: owned.stat(); return owned.read()
        for code, line in sorted(observed, key=lambda v: (v[0].co_name, v[1])):
            with self.subTest(code=code.co_name, line=line): self.cut(operation, code, "line", line)
        self.cut(self.consume, reader.ManagedSourceReader.read.__code__, "return")

    def test_migrated_shared_read_routes_never_acquire_or_fdopen_a_raw_result(self):
        with mock.patch.object(reader, "ROOT", self.root), mock.patch.object(reader, "open_regular_beneath", side_effect=AssertionError("raw result")), mock.patch.object(reader.os, "fdopen", side_effect=AssertionError("owning stream")):
            self.assertEqual(reader.read_bytes_beneath(self.root, self.path), self.path.read_bytes())
            self.assertEqual(reader.read_bytes_nofollow(self.path), self.path.read_bytes())
            self.assertEqual(reader.read_text_nofollow(self.path), '{"original":true}\n')
            self.assertEqual(reader.load_json_nofollow(self.path), {"original": True})
            self.assertTrue(reader.regular_file_exists_nofollow(self.path, label="actual exists"))
            self.assertEqual(reader.sha256(self.path), hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_migrated_artifact_read_hash_size_and_reference_never_use_raw_opener(self):
        with mock.patch.object(artifact, "open_file", side_effect=AssertionError("raw result")), mock.patch.object(artifact.os, "fdopen", side_effect=AssertionError("owning stream")):
            self.assertEqual(artifact.load(self.path), {"original": True})
            self.assertEqual(artifact.file_size(self.path), self.path.stat().st_size)
            self.assertEqual(artifact.digest(self.path), hashlib.sha256(self.path.read_bytes()).hexdigest())
            self.assertEqual(artifact.artifact_file(self.root, "parent/file.json"), self.path)
        for code, operation in [(artifact.load.__code__, lambda: artifact.load(self.path)),
                                (artifact.digest.__code__, lambda: artifact.digest(self.path)),
                                (artifact.file_size.__code__, lambda: artifact.file_size(self.path))]:
            self.cut(operation, code, "return")

    def test_native_read_failure_and_lost_bytes_result_close_actual_fd(self):
        native = os.read; before = census(); observed = []
        def interrupted(fd, count):
            observed.append(os.fstat(fd).st_ino)
            native(fd, count)
            raise InterruptedError("actual read before interruption")
        with mock.patch.object(reader.os, "read", side_effect=interrupted):
            with self.assertRaises(InterruptedError): self.consume()
        gc.collect(); self.assertEqual(observed, [self.path.stat().st_ino]); self.assertEqual(census(), before)

    def test_native_close_after_effect_and_integer_reuse_survives_gc(self):
        for factory in [self.consume, lambda: artifact.load(self.path)]:
            before = census(); foreign = []; native = os.close
            def close(fd):
                is_leaf = os.fstat(fd).st_ino == self.path.stat().st_ino
                native(fd)
                if is_leaf and not foreign:
                    replacement = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                    if replacement != fd: os.dup2(replacement, fd); native(replacement)
                    foreign.append(fd)
                    raise KeyboardInterrupt("actual leaf close then reuse")
            try:
                with mock.patch.object(reader.os, "close", side_effect=close):
                    with self.assertRaises(KeyboardInterrupt): factory()
                gc.collect(); self.assertEqual(len(foreign), 1)
                self.assertEqual(os.fstat(foreign[0]).st_ino, os.stat("/dev/null").st_ino)
                native(foreign.pop()); self.assertEqual(census(), before)
            finally:
                for fd in foreign: native(fd)

    def test_same_pinned_parent_rename_and_symlink_uses_original_inode(self):
        outside = self.root / "outside"; outside.mkdir(mode=0o700)
        (outside / self.path.name).write_bytes(b"wrong bytes")
        def swap(index, component, fd):
            if component == "parent":
                self.parent.rename(self.root / "saved")
                self.parent.symlink_to(outside, target_is_directory=True)
        with reader.open_managed_regular_beneath(self.root, self.path, label="managed rename", after_component=swap) as owned:
            self.assertEqual(owned.read(), b'{"original":true}\r\n')
        with self.assertRaises(ValueError): self.acquire()

    def test_original_size_single_link_nonregular_and_strict_json_refusals(self):
        for limit, operation in [(artifact.MAX_JSON_BYTES, artifact.load), (artifact.MAX_ARTIFACT_FILE_BYTES, artifact.digest)]:
            with self.subTest(limit=limit):
                with self.path.open("wb") as stream: stream.truncate(limit + 1)
                with mock.patch.object(reader.os, "read", side_effect=AssertionError("oversize admission")):
                    with self.assertRaises(ValueError): operation(self.path)
        self.path.write_bytes(b'{"key":1,"key":2}')
        with self.assertRaises(ValueError): artifact.load(self.path)
        linked = self.parent / "link"; os.link(self.path, linked)
        with self.assertRaises(ValueError): artifact.load(linked)
        linked.unlink(); self.path.unlink(); os.mkfifo(self.path)
        with self.assertRaises(ValueError): artifact.load(self.path)

    def test_actual_same_fd_metadata_readback_detects_file_change(self):
        native = os.read; mutated = []
        def change(fd, count):
            data = native(fd, count)
            if not mutated:
                self.path.write_bytes(b'{"changed":true,"grown":true}')
                mutated.append(True)
            return data
        for operation in [artifact.load, artifact.digest]:
            self.path.write_bytes(b'{"original":true}'); mutated.clear()
            with mock.patch.object(reader.os, "read", side_effect=change):
                with self.assertRaisesRegex(ValueError, "changed while"): operation(self.path)

    def test_actual_foreign_thread_operations_cannot_close_and_reuse_an_active_read(self):
        before = census()
        original = b"A" * (1024 * 1024) + b"original tail"
        self.path.write_bytes(original)
        foreign_path = self.root / "foreign"; foreign_path.write_bytes(b"B" * (2 * 1024 * 1024))
        ready = threading.Event(); resume = threading.Event(); shared = {}; failures = []
        read_line = next(number for number, text in enumerate(inspect.getsource(reader.ManagedSourceReader.read).splitlines(),
                         reader.ManagedSourceReader.read.__code__.co_firstlineno) if "chunk = os.read" in text)
        def worker():
            count = 0
            def trace(frame, event, value):
                nonlocal count
                if frame.f_code is reader.ManagedSourceReader.read.__code__ and event == "line" and frame.f_lineno == read_line:
                    count += 1
                    if count == 2:
                        ready.set()
                        if not resume.wait(5): raise AssertionError("test reader barrier timed out")
                return trace
            try:
                with self.acquire() as owned:
                    shared["reader"] = owned
                    shared["descriptor"] = owned._owner.fd
                    sys.settrace(trace)
                    try: shared["result"] = owned.read()
                    finally: sys.settrace(None)
            except BaseException as error: failures.append(error); ready.set()
        thread = threading.Thread(target=worker); thread.start()
        foreign = None
        try:
            self.assertTrue(ready.wait(5)); self.assertFalse(failures)
            owned = shared["reader"]
            for operation in [owned.read, owned.stat, owned.__enter__, owned.close, lambda: owned.__exit__(None, None, None)]:
                with self.assertRaisesRegex(ValueError, "creator process and thread"): operation()
            foreign = os.open(foreign_path, os.O_RDONLY | os.O_CLOEXEC)
            self.assertNotEqual(foreign, shared["descriptor"])
            self.assertEqual(os.fstat(shared["descriptor"]).st_ino, self.path.stat().st_ino)
        finally:
            resume.set(); thread.join(5)
            if foreign is not None: os.close(foreign)
        self.assertFalse(thread.is_alive()); self.assertFalse(failures)
        self.assertEqual(shared["result"], original)
        shared.clear(); gc.collect(); self.assertEqual(census(), before)

    def test_actual_last_reference_foreign_thread_gc_closes_only_its_owned_descriptor(self):
        before = census()
        for previously_closed in [False, True]:
            with self.subTest(previously_closed=previously_closed):
                owned = self.acquire(); descriptor = owned._owner.fd; holder = [owned]
                foreign = None
                if previously_closed:
                    owned.close()
                    foreign = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                    if foreign != descriptor:
                        os.dup2(foreign, descriptor); os.close(foreign); foreign = descriptor
                del owned
                def discard():
                    holder.clear(); gc.collect()
                thread = threading.Thread(target=discard); thread.start(); thread.join(5)
                self.assertFalse(thread.is_alive())
                try:
                    if previously_closed:
                        self.assertEqual(os.fstat(foreign).st_ino, os.stat("/dev/null").st_ino)
                    else:
                        with self.assertRaises(OSError) as observed: os.fstat(descriptor)
                        self.assertEqual(observed.exception.errno, errno.EBADF)
                finally:
                    if foreign is not None: os.close(foreign)
                self.assertEqual(census(), before)

    def test_actual_same_thread_reentry_cannot_release_a_borrowed_read_descriptor(self):
        before = census(); self.path.write_bytes(b"A" * (1024 * 1024) + b"original tail")
        observed = []
        with self.acquire() as owned:
            def trace(frame, event, value):
                if frame.f_code is reader.ManagedSourceReader.read.__code__ and event == "line" and not observed and frame.f_lineno == read_line:
                    observed.append(frame.f_lineno)
                    for operation in [owned.read, owned.stat, owned.__enter__, owned.close]:
                        with self.assertRaisesRegex(ValueError, "reentrant"): operation()
                return trace
            read_line = next(number for number, text in enumerate(inspect.getsource(reader.ManagedSourceReader.read).splitlines(),
                             reader.ManagedSourceReader.read.__code__.co_firstlineno) if "chunk = os.read" in text)
            previous = sys.gettrace()
            try:
                sys.settrace(trace); result = owned.read()
            finally: sys.settrace(previous)
            self.assertEqual(result, self.path.read_bytes()); self.assertEqual(len(observed), 1)
        gc.collect(); self.assertEqual(census(), before)

    def test_actual_fork_rejects_before_thread_access_and_child_gc_preserves_parent_fd(self):
        before = census(); owned = self.acquire(); descriptor = owned._owner.fd
        pipe_read, pipe_write = os.pipe(); child = os.fork()
        if child == 0:
            try:
                os.close(pipe_read)
                def forbidden_thread_access(): raise AssertionError("foreign process reached thread lookup")
                reader.threading.current_thread = forbidden_thread_access
                refused = 0
                for operation in [owned.read, owned.stat, owned.__enter__, owned.close]:
                    try: operation()
                    except ValueError: refused += 1
                del operation; del owned; gc.collect()
                try: os.fstat(descriptor); closed = False
                except OSError as error: closed = error.errno == errno.EBADF
                os.write(pipe_write, json.dumps({"refused": refused, "child_descriptor_closed": closed}).encode("ascii"))
                os._exit(0)
            except BaseException: os._exit(1)
        os.close(pipe_write)
        try:
            packet = os.read(pipe_read, 4096)
            self.assertEqual(os.waitpid(child, 0)[1], 0)
            self.assertEqual(json.loads(packet), {"refused": 4, "child_descriptor_closed": True})
            self.assertEqual(os.fstat(descriptor).st_ino, self.path.stat().st_ino)
            self.assertEqual(owned.read(), self.path.read_bytes())
        finally:
            os.close(pipe_read); owned.close()
        gc.collect(); self.assertEqual(census(), before)


if __name__ == "__main__":
    unittest.main()
