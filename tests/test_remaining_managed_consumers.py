"""Actual FD interruption checks for the seven remaining source consumers."""
from __future__ import annotations

import ast
import gc
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from tools import browser_codec_reference_security as reader
from tools import artifact_evidence as evidence
from tools import native_input_checkpoints as native
from tools import servo_namespace_qualification as namespace
from tools import validate_platform_mechanisms as platform
from tools import verify_s12_release_qualification as release

ROOT = Path(__file__).resolve().parents[1]
with mock.patch.object(sys, "path", [str(ROOT / "tools"), *sys.path]):
    from tools import _validate_repository_impl as repository
    import browser_codec_reference_security as repository_reader

SOURCES = [
    ("tools/_validate_repository_impl.py", "load_json", "open_managed_regular_beneath"),
    ("tools/validate_platform_mechanisms.py", "read", "open_managed_regular_beneath"),
    ("tools/verify_s12_release_qualification.py", "_regular_bytes", "open_managed_regular_beneath"),
    ("tools/native_input_checkpoints.py", "load_private", "open_managed_regular_beneath"),
    ("tools/servo_namespace_qualification.py", "hash_regular", "open_managed_file"),
    ("tools/servo_namespace_qualification.py", "Packet.read", "open_managed_file"),
    ("tools/servo_namespace_qualification.py", "validate_contract", "open_managed_file"),
]


def census():
    result = {}
    for path in tuple(Path("/proc/self/fd").iterdir()):
        try:
            metadata = os.fstat(int(path.name))
            result[int(path.name)] = (metadata.st_dev, metadata.st_ino)
        except (OSError, FileNotFoundError):
            pass
    return result


class RemainingManagedConsumerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="managed-consumer-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.path = self.root / "source.json"
        self.payload = b'{"probe":true}\n'
        self.path.write_bytes(self.payload)
        self.path.chmod(0o600)
        self.identity = native.root_identity(self.root)

    def cases(self):
        return [
            ("repository JSON", lambda: repository.load_json(self.path), {"probe": True}),
            ("platform registry", lambda: platform.read(self.root, self.path.name), self.payload.decode()),
            ("release evidence", lambda: release._regular_bytes(self.path, "probe", 1024), self.payload),
            ("native checkpoint", lambda: native.load_private(self.root, self.path.name, self.identity),
             ({"probe": True}, hashlib.sha256(self.payload).hexdigest())),
            ("namespace hash", lambda: namespace.hash_regular(self.path), hashlib.sha256(self.payload).hexdigest()),
            ("namespace packet", lambda: namespace.Packet(self.root).read(self.path.name), self.payload),
            ("namespace contract", lambda: namespace.validate_contract(), None),
        ]

    def run_faults(self, event, names, *, metadata_consumers_only=False):
        # Retain only booleans, never the returned owner, traceback, or raw FD.
        # The frame belongs to the real called factory/read/stat method.
        for label, operation, _ in self.cases():
            # Repository load_json originally reads bytes without a public
            # stat call; preserve that API and do not invent a metadata path.
            if metadata_consumers_only and label == "repository JSON":
                continue
            with self.subTest(route=label, fault=event):
                before = census()
                fired = []
                previous = sys.gettrace()
                def trace(frame, kind, argument):
                    if kind == event and frame.f_code.co_name in names and not fired:
                        source = Path(frame.f_code.co_filename).name
                        if source in {"browser_codec_reference_security.py", "artifact_evidence.py"}:
                            fired.append(True)
                            raise KeyboardInterrupt("managed consumer delivery interruption")
                    return trace
                try:
                    with mock.patch.object(repository, "ROOT", self.root):
                        sys.settrace(trace)
                        with self.assertRaises(KeyboardInterrupt):
                            operation()
                finally:
                    sys.settrace(previous)
                gc.collect()
                after = census()
                try:
                    self.assertEqual(fired, [True])
                    self.assertEqual(after, before)
                finally:
                    # If this test is run on the raw predecessor, preserve a
                    # failing assertion and close only its observed extra FDs.
                    for descriptor in after.keys() - before.keys():
                        os.close(descriptor)

    def test_all_seven_actual_consumers_preserve_positive_results_and_close_fds(self):
        for label, operation, expected in self.cases():
            with self.subTest(route=label):
                before = census()
                with mock.patch.object(repository, "ROOT", self.root):
                    self.assertEqual(operation(), expected)
                gc.collect()
                self.assertEqual(census(), before)

    def test_all_seven_factory_result_delivery_interruptions_retain_cleanup(self):
        self.run_faults("return", {"open_managed_regular_beneath", "open_managed_file", "open_regular_beneath"})

    def test_all_seven_read_result_delivery_interruptions_retain_cleanup(self):
        self.run_faults("return", {"read", "read_some"})

    def test_all_six_existing_metadata_result_delivery_interruptions_retain_cleanup(self):
        self.run_faults("return", {"stat"}, metadata_consumers_only=True)

    def test_actual_os_read_then_interruption_preserves_all_seven_fd_censuses(self):
        original = os.read
        for label, operation, _ in self.cases():
            with self.subTest(route=label):
                before = census()
                reads = []
                def read_then_interrupt(descriptor, size):
                    data = original(descriptor, size)
                    reads.append(len(data))
                    raise KeyboardInterrupt("actual read completed before interruption")
                with mock.patch.object(repository, "ROOT", self.root), mock.patch.object(os, "read", side_effect=read_then_interrupt):
                    with self.assertRaises(KeyboardInterrupt):
                        operation()
                gc.collect()
                self.assertEqual(len(reads), 1)
                self.assertEqual(census(), before)

    def test_closed_versioned_consumer_inventory_refuses_raw_transfer_in_each_function(self):
        contract = json.loads((ROOT / "contracts/remaining-managed-consumers.v1.json").read_text())
        self.assertEqual(contract["schema"], "trillionnium.remaining-managed-consumers.v1")
        self.assertEqual([(row["source"], row["function"], row["reader_factory"]) for row in contract["consumers"]], SOURCES)
        self.assertIs(contract["fault_scope"]["legacy_raw_integer_delivery_protected"], False)
        self.assertIs(contract["claims"]["production_ready"], False)
        self.assertEqual(str(inspect.signature(reader.ManagedSourceReader.read_some)), contract["added_api"]["ManagedSourceReader.read_some"]["signature"])
        for source, name, factory in SOURCES:
            tree = ast.parse((ROOT / source).read_text())
            parts = name.split(".")
            container = tree
            if len(parts) == 2:
                container = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == parts[0])
            function = next(node for node in container.body if isinstance(node, ast.FunctionDef) and node.name == parts[-1])
            calls = [node.func.id for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
            attributes = [node.func.attr for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
            with self.subTest(route=name):
                self.assertIn(factory, calls)
                self.assertTrue({"open_file", "open_regular_beneath"}.isdisjoint(calls))
                self.assertNotIn("fdopen", attributes)
                self.assertNotIn("fileno", attributes)

    def test_single_read_preserves_short_read_types_creator_closed_and_reentry_rules(self):
        original = os.read
        before = census()
        with reader.open_managed_regular_beneath(self.root, self.path, label="single-read API") as owned:
            for size in [True, False, 1.0, None, "1"]:
                with self.subTest(size=size), self.assertRaises(TypeError): owned.read_some(size)
            with self.assertRaises(ValueError): owned.read_some(-1)
            with self.assertRaises(OverflowError): owned.read_some(sys.maxsize + 1)
            with mock.patch.object(reader.os, "getpid", return_value=os.getpid()+1):
                with self.assertRaises(ValueError): owned.read_some(1)
            reentries = []
            def short_read(descriptor, size):
                for operation in (lambda: owned.read(1), lambda: owned.read_some(1), owned.stat,
                                  owned.close, lambda: owned.__exit__(None, None, None)):
                    with self.assertRaises(ValueError): operation()
                    reentries.append(True)
                return original(descriptor, min(size, 1))
            with mock.patch.object(os, "read", side_effect=short_read):
                self.assertEqual(owned.read_some(1024), self.payload[:1])
            self.assertEqual(len(reentries), 5)
            self.assertEqual(owned.read_some(0), b"")
        with self.assertRaises(ValueError): owned.read_some(1)
        gc.collect(); self.assertEqual(census(), before)

    def test_each_actual_one_byte_hash_read_checks_original_sixty_second_deadline(self):
        self.path.write_bytes(b"a" * 4096)
        original = os.read
        clock = [0]
        def single(descriptor, size):
            data = original(descriptor, min(size, 1))
            clock[0] += 1
            return data
        before = census()
        with mock.patch.object(os, "read", side_effect=single), mock.patch.object(namespace.time, "monotonic", side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(ValueError, "hash exceeded bounds"):
                namespace.hash_regular(self.path)
        self.assertEqual(clock[0], 60)
        gc.collect(); self.assertEqual(census(), before)


if __name__ == "__main__":
    unittest.main()
