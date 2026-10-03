"""Actual public context reentry/FD tests; no native product qualification."""
import errno
import gc
import inspect
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest

from tools import browser_codec_reference_security as module
from tests.test_shared_managed_reader import census


class SharedManagedContextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="managed-context-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.root.chmod(0o700)
        self.path = self.root / "original"
        self.path.write_bytes(b"A" * (1024 * 1024) + b"ORIGINAL_TAIL")
        self.foreign = self.root / "foreign"; self.foreign.write_bytes(b"FOREIGN_RESULT")

    def acquire(self):
        return module.open_managed_regular_beneath(self.root, self.path, label="actual public context")

    @staticmethod
    def line(function, text):
        return next(number for number, source in enumerate(inspect.getsource(function).splitlines(),
                    function.__code__.co_firstlineno) if text in source)

    def test_closed_context_bound_contract_and_source_index(self):
        root = Path(__file__).resolve().parents[1]
        value = json.loads((root / "contracts/shared-managed-reader.v1.json").read_bytes())
        self.assertIs(value["custody"]["reentrant_public_context_exit_refused"], True)
        self.assertIs(type(value["custody"]["active_operation_stack_frames_maximum"]), int)
        self.assertEqual(value["custody"]["active_operation_stack_frames_maximum"], 1024)
        self.assertEqual(module.ManagedSourceReader._MAX_OPERATION_FRAMES, 1024)
        self.assertEqual(value["source_index"]["context_tests"], "tests/test_shared_managed_context.py")
        index = json.loads((root / "manifests/modules.v1.json").read_bytes())
        self.assertIn(value["source_index"]["context_tests"], next(m for m in index["modules"] if m["id"] == "hepta-browser-codec")["tests"])

    def test_actual_public_exit_read_line_and_borrowed_RETURN_stat_reentry_refuse(self):
        for operation, event in [("read", "line"), ("read", "return"), ("stat", "return")]:
            for exceptional in [False, True]:
                with self.subTest(operation=operation, event=event, exceptional=exceptional):
                    before = census(); observed = []; foreign_fd = None
                    with self.acquire() as reader:
                        descriptor = reader._owner.fd; hits = 0
                        read_line = self.line(module.ManagedSourceReader.read, "chunk = os.read")
                        def trace(frame, kind, value):
                            nonlocal hits, foreign_fd
                            matched = (event == "line" and kind == "line" and frame.f_code is module.ManagedSourceReader.read.__code__ and frame.f_lineno == read_line)
                            matched |= (event == "return" and kind == "return" and frame.f_code is module.ManagedSourceReader._descriptor.__code__)
                            if matched and not observed:
                                hits += 1
                                if event == "line" and hits != 2: return trace
                                try:
                                    if exceptional: raise RuntimeError("actual callback exception")
                                    args = (None, None, None)
                                except RuntimeError:
                                    args = sys.exc_info()
                                with self.assertRaisesRegex(ValueError, "reentrant"):
                                    reader.__exit__(*args)
                                observed.append(frame.f_lineno)
                                self.assertEqual(os.fstat(descriptor).st_ino, self.path.stat().st_ino)
                                foreign_fd = os.open(self.foreign, os.O_RDONLY | os.O_CLOEXEC)
                                self.assertNotEqual(foreign_fd, descriptor)
                            return trace
                        prior = sys.gettrace()
                        try:
                            sys.settrace(trace)
                            result = reader.read() if operation == "read" else reader.stat()
                        finally: sys.settrace(prior)
                        self.assertEqual(len(observed), 1)
                        if operation == "read": self.assertEqual(result, self.path.read_bytes())
                        else: self.assertEqual(result.st_ino, self.path.stat().st_ino)
                    try:
                        gc.collect(); self.assertEqual(os.fstat(foreign_fd).st_ino, self.foreign.stat().st_ino)
                    finally: os.close(foreign_fd)
                    self.assertEqual(census(), before)

    def test_actual_SIGUSR1_exceptional_context_callback_preserves_original_read(self):
        before = census(); observed = []
        with self.acquire() as reader:
            descriptor = reader._owner.fd
            def callback(signum, frame):
                try: raise RuntimeError("actual native signal callback")
                except RuntimeError:
                    with self.assertRaisesRegex(ValueError, "reentrant"): reader.__exit__(*sys.exc_info())
                observed.append(os.fstat(descriptor).st_ino)
            previous_handler = signal.signal(signal.SIGUSR1, callback)
            read_line = self.line(module.ManagedSourceReader.read, "chunk = os.read"); hits = 0
            def trace(frame, event, value):
                nonlocal hits
                if frame.f_code is module.ManagedSourceReader.read.__code__ and event == "line" and frame.f_lineno == read_line:
                    hits += 1
                    if hits == 2: os.kill(os.getpid(), signal.SIGUSR1)
                return trace
            previous_trace = sys.gettrace()
            try:
                sys.settrace(trace); result = reader.read()
            finally:
                sys.settrace(previous_trace); signal.signal(signal.SIGUSR1, previous_handler)
            self.assertEqual(result, self.path.read_bytes()); self.assertEqual(observed, [self.path.stat().st_ino])
        gc.collect(); self.assertEqual(census(), before)

    def test_actual_deep_stack_exceeds_fixed_bound_and_refuses_context_exit(self):
        before = census(); seen = []; recursion_limit = sys.getrecursionlimit()
        with self.acquire() as reader:
            def nested(depth):
                if depth: return nested(depth - 1)
                with self.assertRaisesRegex(ValueError, "stack exceeds its check bound"):
                    reader.__exit__(RuntimeError, RuntimeError("deep callback"), None)
                seen.append(True)
            line = self.line(module.ManagedSourceReader.read, "chunk = os.read")
            def trace(frame, event, value):
                if frame.f_code is module.ManagedSourceReader.read.__code__ and event == "line" and frame.f_lineno == line and not seen:
                    nested(1100)
                return trace
            previous = sys.gettrace()
            try:
                sys.setrecursionlimit(max(recursion_limit, 3000)); sys.settrace(trace); result = reader.read()
            finally:
                sys.settrace(previous); sys.setrecursionlimit(recursion_limit)
            self.assertEqual(result, self.path.read_bytes()); self.assertEqual(seen, [True])
        gc.collect(); self.assertEqual(census(), before)

    def test_actual_unwound_busy_cleanup_preserves_original_KeyboardInterrupt(self):
        for function in [module.ManagedSourceReader.read, module.ManagedSourceReader.stat]:
            with self.subTest(function=function.__name__):
                before = census(); observed = []; line = self.line(function, "self._active = False")
                def trace(frame, event, value):
                    if frame.f_code is function.__code__ and event == "line" and frame.f_lineno == line and not observed:
                        observed.append(frame.f_lineno); raise KeyboardInterrupt("actual busy cleanup interruption")
                    return trace
                reader = self.acquire(); descriptor = reader._owner.fd; previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaisesRegex(KeyboardInterrupt, "actual busy cleanup interruption"):
                        with reader: getattr(reader, function.__name__)()
                finally: sys.settrace(previous)
                self.assertEqual(len(observed), 1)
                with self.assertRaises(OSError) as error: os.fstat(descriptor)
                self.assertEqual(error.exception.errno, errno.EBADF)
                reader.close(); del reader; gc.collect(); self.assertEqual(census(), before)

    def test_actual_observed_busy_guard_ordinary_line_interruptions_keep_descriptor_owner(self):
        guard = module.ManagedSourceReader._ensure_idle.__code__; observed = set()
        line = self.line(module.ManagedSourceReader.read, "chunk = os.read")
        def operation(cut=None):
            fired = []; callback_done = []; reader = self.acquire()
            def trace(frame, event, value):
                if frame.f_code is guard and event == "line":
                    observed.add(frame.f_lineno)
                    if cut == frame.f_lineno and not fired:
                        fired.append(True); raise KeyboardInterrupt("ordinary active guard interruption")
                if frame.f_code is module.ManagedSourceReader.read.__code__ and event == "line" and frame.f_lineno == line and not callback_done:
                    callback_done.append(True)
                    def callback():
                        with self.assertRaisesRegex(ValueError, "reentrant"):
                            reader.__exit__(RuntimeError, RuntimeError("real callback"), None)
                    sys.call_tracing(callback, ())
                return trace
            prior = sys.gettrace()
            try:
                sys.settrace(trace)
                with reader: reader.read()
            finally: sys.settrace(prior)
        before = census(); operation(); gc.collect(); self.assertEqual(census(), before)
        self.assertGreater(len(observed), 7)
        for target in sorted(observed):
            with self.subTest(line=target):
                with self.assertRaisesRegex(KeyboardInterrupt, "ordinary active guard interruption"): operation(target)
                gc.collect(); self.assertEqual(census(), before)


if __name__ == "__main__":
    unittest.main()
