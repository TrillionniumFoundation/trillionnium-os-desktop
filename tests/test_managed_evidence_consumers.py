"""Actual local evidence-reader custody; no Servo/image/runtime qualification."""
from __future__ import annotations

import ast
import copy
import errno
import gc
import hashlib
import inspect
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import textwrap
import unittest
from unittest import mock

from tools import artifact_evidence as artifact
from tools import browser_codec_reference_security as managed
from tools import check_servo_resource_gate as resource
from tools import d1_evidence_semantics as semantics
from tools import prepare_native_product_owner as native
from tools import verify_d2i_artifact as d2i
from tools import verify_s08_semantic_custody as s08
from tests.d1.test_artifact_evidence import d2i_fixture
from tests.test_shared_managed_reader import census

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "schema": "trillionnium.managed-evidence-consumers.v1",
    "dependency": "contracts/shared-managed-reader.v1.json",
    "migrated": {
        "tools/d1_evidence_semantics.py": {
            "_Snapshot.read": "(self, name: 'str') -> 'bytes'",
            "_Snapshot.finish": "(self) -> 'None'",
            "validate_contract": "(value: 'object | None' = None) -> 'None'",
        },
        "tools/verify_d2i_artifact.py": {
            "verify_source": "(root: 'Path', receipt: 'dict[str, Any]') -> 'dict[str, Any]'",
        },
        "tools/check_servo_resource_gate.py": {
            "read_bounded": "(path: 'Path', limit: 'int') -> 'bytes'",
        },
        "tools/prepare_native_product_owner.py": {"read": "(path: 'Path') -> 'bytes'"},
        "tools/verify_s08_semantic_custody.py": {
            "read": "(path: 'Path', maximum: 'int' = 1048576) -> 'bytes'",
        },
    },
    "limits": {
        "d1_payload_bytes": 8388608, "d1_contract_bytes": 65536,
        "d2i_whole_source_archive_bytes": 67108864,
        "resource_evidence_bytes": 131072, "resource_origin_bytes": 64,
        "native_source_bytes": 2097152, "s08_source_bytes": 1048576,
        "s08_patch_bytes": 262144, "s08_result_bytes": 4096,
        "artifact_json_bytes": 8388608, "artifact_hash_bytes": 8589934592,
    },
    "custody": {
        "same_managed_owner_through_read_stat_and_close": True,
        "raw_fdopen_or_public_descriptor_transfer": False,
        "d1_complete_readback_retains_all_owners": True,
        "d2i_parse_and_archive_digest_use_same_immutable_bytes": True,
        "d2i_tarfile_seek_uses_bytesio": True,
        "original_single_link_path_and_readback_checks_preserved": True,
        "creator_pid_thread_and_public_context_reentry_guard_inherited": True,
        "ordinary_return_loss_and_attempted_close_reuse_tested": True,
        "all_native_call_opcode_or_repeated_fault_windows": False,
    },
    "compatibility": {
        "old_reader_signatures_preserved": True,
        "raw_open_file_and_open_regular_beneath_abi_preserved": True,
        "legacy_raw_result_delivery_protected": False,
        "other_namespace_input_checkpoint_shell_release_consumers_migrated": False,
        "d2i_archive_previously_streamed_now_whole_bytes_bounded": True,
    },
    "source_index": {
        "module": "hepta-browser-codec",
        "tests": "tests/test_managed_evidence_consumers.py",
        "documentation": "docs/architecture/MANAGED_EVIDENCE_CONSUMERS.md",
    },
    "claims": {
        "source_file_io_only": True, "production_ready": False,
        "peer_principal_or_signing_authority": False,
        "installed_native_or_boot_qualification": False,
        "activation_or_workflow_stimulus_changed": False,
    },
}


def closed(value):
    if json.dumps(value, sort_keys=True) != json.dumps(EXPECTED, sort_keys=True):
        raise ValueError("managed evidence contract differs from the closed source profile")


class ManagedEvidenceConsumersTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="managed-evidence-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.root.chmod(0o700)
        self.path = self.root / "payload"; self.path.write_bytes(b"ORIGINAL")
        self.foreign = self.root / "foreign"; self.foreign.write_bytes(b"FOREIGN_RESULT")

    def routes(self):
        payload = self.path.read_bytes()
        snapshot = semantics._Snapshot(self.root, {self.path.name: hashlib.sha256(payload).hexdigest()})
        snapshot.read(self.path.name)
        return [
            ("d1-read", lambda: snapshot.read(self.path.name)),
            ("d1-complete-readback", snapshot.finish),
            ("d1-contract", semantics.validate_contract),
            ("d2i-archive", lambda: d2i._read_source_archive(self.path)),
            ("resource", lambda: resource.read_bounded(self.path, resource.MAX_BYTES)),
            ("native-source", lambda: native.read(self.path)),
            ("s08-source", lambda: s08.read(self.path)),
        ]

    @staticmethod
    def line(function, text):
        return next(number for number, source in enumerate(inspect.getsource(function).splitlines(),
                    function.__code__.co_firstlineno) if text in source)

    def test_contract_exact_catalog_limits_source_index_and_no_raw_reader_calls(self):
        value = json.loads((ROOT / "contracts/managed-evidence-consumers.v1.json").read_bytes())
        closed(value)
        modules = {module.__file__.split("/")[-1]: module for module in (semantics, d2i, resource, native, s08)}
        for path, catalog in value["migrated"].items():
            module = modules[Path(path).name]
            for name, signature in catalog.items():
                target = module
                for part in name.split("."): target = getattr(target, part)
                self.assertEqual(str(inspect.signature(target)), signature)
        readers = [semantics._Snapshot.read, semantics._Snapshot.finish, semantics.validate_contract,
                   d2i._read_source_archive, d2i.verify_source, resource.read_bounded, native.read, s08.read]
        for function in readers:
            with self.subTest(function=function.__qualname__):
                tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
                calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
                self.assertFalse(any(isinstance(call, ast.Name) and call.id == "open_file" for call in calls))
                self.assertFalse(any(isinstance(call, ast.Attribute) and call.attr in {"fdopen", "fileno", "detach"} for call in calls))
        self.assertEqual(d2i.MAX_SOURCE_ARCHIVE_BYTES, value["limits"]["d2i_whole_source_archive_bytes"])
        self.assertEqual(semantics.MAX_JSON_BYTES, value["limits"]["d1_payload_bytes"])
        self.assertEqual(resource.MAX_BYTES, value["limits"]["resource_evidence_bytes"])
        self.assertEqual(native.MAX_SOURCE, value["limits"]["native_source_bytes"])
        self.assertEqual(s08.MAX_SOURCE_BYTES, value["limits"]["s08_source_bytes"])
        self.assertEqual(artifact.MAX_JSON_BYTES, value["limits"]["artifact_json_bytes"])
        self.assertEqual(artifact.MAX_ARTIFACT_FILE_BYTES, value["limits"]["artifact_hash_bytes"])
        index = json.loads((ROOT / "manifests/modules.v1.json").read_bytes())
        module = next(item for item in index["modules"] if item["id"] == value["source_index"]["module"])
        for key, path in [("tests", value["source_index"]["tests"]), ("contracts", "contracts/managed-evidence-consumers.v1.json"),
                          ("architecture", value["source_index"]["documentation"])]:
            self.assertIn(path, module[key])
        self.assertEqual(inspect.signature(artifact.open_file).return_annotation, "int")

    def test_closed_contract_refuses_unknown_fields_type_aliases_and_broadened_claims(self):
        for key in EXPECTED:
            changed = copy.deepcopy(EXPECTED); del changed[key]
            with self.assertRaises(ValueError): closed(changed)
        changed = copy.deepcopy(EXPECTED); changed["new_authority"] = True
        with self.assertRaises(ValueError): closed(changed)
        for section in ("claims", "custody", "compatibility", "limits"):
            for key, original in EXPECTED[section].items():
                changed = copy.deepcopy(EXPECTED)
                changed[section][key] = int(original) if type(original) is bool else float(original)
                with self.subTest(section=section, key=key), self.assertRaises(ValueError): closed(changed)

    def test_each_managed_opener_RETURN_loss_releases_actual_descriptor(self):
        for name, operation in self.routes():
            with self.subTest(route=name):
                before = census(); observed = []
                def trace(frame, event, value):
                    if frame.f_code is artifact.open_managed_file.__code__ and event == "return" and not observed:
                        observed.append(value.stat().st_ino)
                        raise KeyboardInterrupt("actual managed object delivery lost")
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaisesRegex(KeyboardInterrupt, "actual managed object delivery lost"): operation()
                finally: sys.settrace(previous)
                gc.collect(); self.assertEqual(len(observed), 1); self.assertEqual(census(), before)

    def test_each_data_RETURN_loss_or_final_context_close_keeps_owner_cleanup(self):
        functions = [semantics._Snapshot.read, semantics._Snapshot.finish, d2i._read_source_archive,
                     resource.read_bounded, native.read, s08.read]
        selected = dict(self.routes())
        for name, function in zip(["d1-read", "d1-complete-readback", "d2i-archive", "resource", "native-source", "s08-source"], functions):
            with self.subTest(route=name):
                before = census(); seen = []
                def trace(frame, event, value):
                    if frame.f_code is function.__code__ and event == "return" and not seen:
                        seen.append(True); raise KeyboardInterrupt("actual evidence result delivery lost")
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaisesRegex(KeyboardInterrupt, "actual evidence result delivery lost"): selected[name]()
                finally: sys.settrace(previous)
                gc.collect(); self.assertEqual(seen, [True]); self.assertEqual(census(), before)

    def test_each_actual_close_effect_interrupt_and_native_reuse_does_not_reclose_foreign(self):
        close_line = self.line(managed._SourceDescriptor.close, "os.close(descriptor)")
        for name, operation in self.routes():
            with self.subTest(route=name):
                before = census(); selected = []; foreign_fd = None
                def trace(frame, event, value):
                    nonlocal foreign_fd
                    if frame.f_code is managed._SourceDescriptor.close.__code__ and event in {"line", "return"}:
                        descriptor = frame.f_locals.get("descriptor")
                        if event == "line" and frame.f_lineno == close_line and descriptor is not None and not selected:
                            try: info = os.fstat(descriptor)
                            except OSError: return trace
                            if info.st_ino == self.path.stat().st_ino or (name == "d1-contract" and info.st_ino == (ROOT / "contracts/d1-portable-evidence.v1.json").stat().st_ino):
                                selected.append(descriptor)
                        elif selected and descriptor == selected[0] and foreign_fd is None:
                            with self.assertRaises(OSError) as failure: os.fstat(descriptor)
                            self.assertEqual(failure.exception.errno, errno.EBADF)
                            # Occupy lower free integers, then duplicate our actual foreign file
                            # into the just-closed integer. No native syscall is patched.
                            opened = os.open(self.foreign, os.O_RDONLY | os.O_CLOEXEC)
                            if opened != descriptor:
                                os.dup2(opened, descriptor); os.close(opened)
                            foreign_fd = descriptor
                            raise KeyboardInterrupt("actual native close already succeeded")
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaisesRegex(KeyboardInterrupt, "actual native close already succeeded"): operation()
                finally: sys.settrace(previous)
                try:
                    self.assertEqual(len(selected), 1); self.assertIsNotNone(foreign_fd)
                    gc.collect(); self.assertEqual(os.fstat(foreign_fd).st_ino, self.foreign.stat().st_ino)
                    self.assertEqual(os.read(foreign_fd, 64), b"FOREIGN_RESULT")
                finally:
                    if foreign_fd is not None: os.close(foreign_fd)
                self.assertEqual(census(), before)

    def test_each_public_exceptional_exit_reentry_is_refused_during_actual_read(self):
        self.path.write_bytes(b"A" * (1024 * 1024) + b"ORIGINAL_TAIL")
        # Only routes whose existing bound admits this payload; resource origin/result
        # smaller routes are independently covered by the same dependency guard.
        operations = dict(self.routes())
        for name in ["d1-read", "d1-complete-readback", "d2i-archive", "native-source"]:
            with self.subTest(route=name):
                before = census(); hits = 0; seen = []; foreign_fd = None
                line = self.line(managed.ManagedSourceReader.read, "chunk = os.read")
                def trace(frame, event, value):
                    nonlocal hits, foreign_fd
                    if frame.f_code is managed.ManagedSourceReader.read.__code__ and event == "line" and frame.f_lineno == line:
                        hits += 1
                        if hits == 2:
                            reader = frame.f_locals["self"]
                            try: raise RuntimeError("actual public context callback")
                            except RuntimeError:
                                with self.assertRaisesRegex(ValueError, "reentrant"): reader.__exit__(*sys.exc_info())
                            foreign_fd = os.open(self.foreign, os.O_RDONLY | os.O_CLOEXEC)
                            self.assertNotEqual(foreign_fd, frame.f_locals["descriptor"])
                            seen.append(True)
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace); result = operations[name]()
                finally: sys.settrace(previous)
                try:
                    self.assertEqual(seen, [True]); gc.collect()
                    self.assertEqual(os.fstat(foreign_fd).st_ino, self.foreign.stat().st_ino)
                    if name != "d1-complete-readback": self.assertEqual(result, self.path.read_bytes())
                finally:
                    if foreign_fd is not None: os.close(foreign_fd)
                self.assertEqual(census(), before)

    def test_each_borrowed_stat_RETURN_public_exit_reentry_cannot_switch_inode(self):
        for name, operation in self.routes():
            with self.subTest(route=name):
                before = census(); seen = []
                def trace(frame, event, value):
                    if frame.f_code is managed.ManagedSourceReader._descriptor.__code__ and event == "return" and not seen:
                        reader = frame.f_locals["self"]
                        try: raise RuntimeError("actual stat callback")
                        except RuntimeError:
                            with self.assertRaisesRegex(ValueError, "reentrant"): reader.__exit__(*sys.exc_info())
                        seen.append(os.fstat(value).st_ino)
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace); operation()
                finally: sys.settrace(previous)
                self.assertEqual(len(seen), 1); gc.collect(); self.assertEqual(census(), before)

    def test_all_seven_routes_refuse_public_exceptional_exit_before_native_chunk_read(self):
        for name, operation in self.routes():
            with self.subTest(route=name):
                before = census(); seen = []; foreign_fd = None
                line = self.line(managed.ManagedSourceReader.read, "chunk = os.read")
                def trace(frame, event, value):
                    nonlocal foreign_fd
                    if frame.f_code is managed.ManagedSourceReader.read.__code__ and event == "line" and frame.f_lineno == line and not seen:
                        reader = frame.f_locals["self"]
                        try: raise RuntimeError("actual exceptional context before native read")
                        except RuntimeError:
                            with self.assertRaisesRegex(ValueError, "reentrant"): reader.__exit__(*sys.exc_info())
                        foreign_fd = os.open(self.foreign, os.O_RDONLY | os.O_CLOEXEC)
                        self.assertNotEqual(foreign_fd, frame.f_locals["descriptor"])
                        seen.append(True)
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace); operation()
                finally: sys.settrace(previous)
                try:
                    self.assertEqual(seen, [True]); gc.collect()
                    self.assertEqual(os.fstat(foreign_fd).st_ino, self.foreign.stat().st_ino)
                finally:
                    if foreign_fd is not None: os.close(foreign_fd)
                self.assertEqual(census(), before)

    def test_observed_consumer_ordinary_line_interruptions_keep_descriptor_cleanup(self):
        functions = [semantics._Snapshot.read, semantics._Snapshot.finish, semantics.validate_contract,
                     d2i._read_source_archive, resource.read_bounded, native.read, s08.read]
        for (name, operation), function in zip(self.routes(), functions):
            with self.subTest(route=name):
                observed = set()
                def observe(frame, event, value):
                    if frame.f_code is function.__code__ and event == "line": observed.add(frame.f_lineno)
                    return observe
                previous = sys.gettrace()
                try: sys.settrace(observe); operation()
                finally: sys.settrace(previous)
                self.assertGreater(len(observed), 2)
                for line in sorted(observed):
                    with self.subTest(line=line):
                        before = census(); seen = []
                        def trace(frame, event, value):
                            if frame.f_code is function.__code__ and event == "line" and frame.f_lineno == line and not seen:
                                seen.append(line); raise KeyboardInterrupt("actual consumer ordinary line")
                            return trace
                        try:
                            sys.settrace(trace)
                            with self.assertRaisesRegex(KeyboardInterrupt, "actual consumer ordinary line"): operation()
                        finally: sys.settrace(previous)
                        self.assertEqual(seen, [line]); gc.collect(); self.assertEqual(census(), before)

    def test_bounded_routes_refuse_actual_sparse_oversize_before_payload_read(self):
        for name, module, function, maximum in [
            ("d1", semantics, lambda: semantics._Snapshot(self.root, {}).read(self.path.name), semantics.MAX_JSON_BYTES),
            ("d2i", d2i, lambda: d2i._read_source_archive(self.path), d2i.MAX_SOURCE_ARCHIVE_BYTES),
            ("resource", resource, lambda: resource.read_bounded(self.path, 64), 64),
            ("native", native, lambda: native.read(self.path), native.MAX_SOURCE),
            ("s08", s08, lambda: s08.read(self.path), s08.MAX_SOURCE_BYTES),
        ]:
            with self.subTest(route=name):
                with self.path.open("wb") as stream: stream.truncate(maximum + 1)
                before = census()
                with mock.patch.object(managed.ManagedSourceReader, "read", side_effect=AssertionError("oversize payload read")):
                    with self.assertRaisesRegex(ValueError, "bound"): function()
                gc.collect(); self.assertEqual(census(), before)

    def test_managed_routes_reject_symlink_parent_hardlink_and_fifo_without_blocking(self):
        operations = [lambda: semantics._Snapshot(self.root, {}).read(self.path.name),
                      lambda: d2i._read_source_archive(self.path),
                      lambda: resource.read_bounded(self.path, 64), lambda: native.read(self.path), lambda: s08.read(self.path)]
        for kind in ["symlink", "hardlink", "fifo", "parent"]:
            with self.subTest(kind=kind):
                self.path.unlink()
                if kind == "symlink": self.path.symlink_to(self.foreign)
                elif kind == "hardlink": os.link(self.foreign, self.path)
                elif kind == "fifo": os.mkfifo(self.path, 0o600)
                else:
                    real = self.root / "real"; real.mkdir(mode=0o700)
                    (real / "payload").write_bytes(b"data")
                    alias = self.root / "alias"; alias.symlink_to(real, target_is_directory=True)
                    saved = self.path; self.path = alias / "payload"
                before = census()
                for operation in operations:
                    with self.assertRaises(ValueError): operation()
                gc.collect(); self.assertEqual(census(), before)
                if kind == "parent": self.path = saved
                else: self.path.unlink()
                self.path.write_bytes(b"ORIGINAL")

    def test_actual_mid_read_mutation_preserves_existing_rejection_checks(self):
        functions = [lambda: semantics._Snapshot(self.root, {}).read(self.path.name),
                     lambda: d2i._read_source_archive(self.path), lambda: resource.read_bounded(self.path, 64),
                     lambda: native.read(self.path), lambda: s08.read(self.path)]
        for function in functions:
            with self.subTest(function=function):
                self.path.write_bytes(b"ORIGINAL"); seen = []
                def trace(frame, event, value):
                    if frame.f_code is managed.ManagedSourceReader.read.__code__ and event == "return" and not seen:
                        self.path.write_bytes(b"CHANGED!"); seen.append(True)
                    return trace
                before = census(); previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaisesRegex(ValueError, "changed"): function()
                finally: sys.settrace(previous)
                self.assertEqual(seen, [True]); gc.collect(); self.assertEqual(census(), before)

    def test_original_git_archive_builder_and_selector_remain_positive(self):
        packet = self.root / "packet"; packet.mkdir(mode=0o700)
        receipt = d2i_fixture(packet)
        before = census()
        result = d2i.verify_artifact(packet)
        self.assertEqual(result["schema"], receipt["schema"])
        gc.collect(); self.assertEqual(census(), before)

    def test_d2i_archive_hash_is_bound_to_parsed_bytes_after_real_path_replacement(self):
        packet = self.root / "packet"; packet.mkdir(mode=0o700)
        receipt = d2i_fixture(packet); archive = packet / "source/source.tar"
        original = archive.read_bytes(); seen = []
        def trace(frame, event, value):
            if frame.f_code is d2i._read_source_archive.__code__ and event == "return" and not seen:
                archive.rename(archive.with_suffix(".original")); archive.write_bytes(b"DIFFERENT_ARCHIVE")
                seen.append(True)
            return trace
        before = census(); previous = sys.gettrace()
        try:
            sys.settrace(trace); result = d2i.verify_source(packet, receipt)
        finally: sys.settrace(previous)
        self.assertEqual(len(seen), 1)
        self.assertEqual(hashlib.sha256(original).hexdigest(), receipt["source"]["archive_sha256"])
        self.assertEqual(result["tree_sha"], receipt["tree_sha"])
        # The full packet verifier still independently checks all current output
        # digests and refuses this later path replacement.
        with self.assertRaises(ValueError): d2i.verify_artifact(packet)
        gc.collect(); self.assertEqual(census(), before)

    def test_d2i_archive_selector_still_refuses_links_traversal_duplicate_and_bad_mode(self):
        for kind in ["symlink", "traversal", "duplicate", "mode"]:
            with self.subTest(kind=kind):
                packet = self.root / kind; packet.mkdir(mode=0o700); receipt = d2i_fixture(packet)
                archive_path = packet / "source/source.tar"
                payload = archive_path.read_bytes()
                with tarfile.open(fileobj=io.BytesIO(payload), mode="r:") as source:
                    entries = [(member, source.extractfile(member).read()) for member in source if member.isfile()]
                with tarfile.open(archive_path, "w") as output:
                    for member, data in entries:
                        if kind == "mode": member.mode = 0o600
                        output.addfile(member, io.BytesIO(data))
                    if kind != "mode":
                        member = tarfile.TarInfo(entries[0][0].name if kind == "duplicate" else ("../escape" if kind == "traversal" else "link"))
                        if kind == "symlink": member.type = tarfile.SYMTYPE; member.linkname = entries[0][0].name
                        output.addfile(member, io.BytesIO())
                before = census()
                with self.assertRaises(ValueError): d2i.verify_source(packet, receipt)
                gc.collect(); self.assertEqual(census(), before)


if __name__ == "__main__":
    unittest.main()
