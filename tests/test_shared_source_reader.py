"""Actual file/FD regressions for the shared source reader's owned stages."""
from __future__ import annotations

import ast
import copy
import errno
import gc
import inspect
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

from tools import browser_codec_reference_security as reader

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/shared-source-reader.v1.json"
EXPECTED = {
    "schema": "trillionnium.shared-source-reader.v1",
    "source": "tools/browser_codec_reference_security.py",
    "api": {
        "name": "open_regular_beneath",
        "parameters": ["root", "path", "label", "after_component"],
        "keyword_only": ["label", "after_component"],
        "return": "int",
        "hook": "after current parent open and directory check, before retiring previous parent",
    },
    "ownership": {
        "empty_owner_before_open": True,
        "ordinary_line_walk_cleanup": True,
        "owned_helper_return_cleanup": True,
        "attempted_close_never_retried": True,
        "final_raw_int_delivery_protected": False,
        "caller_fdopen_delivery_protected": False,
        "all_native_opcode_repeated_fault_windows_protected": False,
    },
    "paths": {
        "root_and_parents": "O_DIRECTORY|O_NOFOLLOW",
        "leaf": "O_NOFOLLOW|O_NONBLOCK",
        "regular_file_required": True,
        "root_absolute_ancestors_revalidated": False,
        "single_hardlink_required_by_this_helper": False,
        "pinned_parent_rename_keeps_original_lookup": True,
    },
    "source_index": {
        "module": "hepta-browser-codec",
        "tests": "tests/test_shared_source_reader.py",
        "documentation": "docs/architecture/SHARED_SOURCE_READER.md",
    },
    "claims": {
        "source_io_mechanism_only": True,
        "approved_peer_or_principal_authority": False,
        "durable_or_signature_authority": False,
        "installed_or_native_qualification": False,
        "product_activation_changed": False,
    },
}


def validate_contract(value):
    # Canonical JSON comparison distinguishes bool/int and rejects every
    # missing, additional or changed nested field in this finite profile.
    if json.dumps(value, sort_keys=True) != json.dumps(EXPECTED, sort_keys=True):
        raise ValueError("shared source reader contract differs from closed profile")


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


class SharedSourceReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="shared-reader-")
        self.root = Path(self.temporary.name)
        self.root.chmod(0o700)
        self.parent = self.root / "parent"
        self.parent.mkdir(mode=0o700)
        self.leaf = self.parent / "source.txt"
        self.leaf.write_bytes(b"original source bytes\n")

    def tearDown(self):
        self.temporary.cleanup()

    def assert_owned_trace_cut(self, code, event, line=None):
        before = census()
        fired = []
        def trace(frame, observed, argument):
            if (frame.f_code is code and observed == event and not fired
                    and (line is None or frame.f_lineno == line)):
                fired.append(frame.f_lineno)
                raise KeyboardInterrupt("one actual Python owned-stage interruption")
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt):
                reader.open_regular_beneath(self.root, self.leaf, label="actual source")
        finally:
            sys.settrace(previous)
        gc.collect()
        self.assertEqual(len(fired), 1)
        self.assertEqual(census(), before)

    def test_closed_contract_signature_index_and_exact_scalar_mutations(self):
        value = json.loads(CONTRACT.read_bytes())
        validate_contract(value)
        signature = inspect.signature(reader.open_regular_beneath)
        self.assertEqual(list(signature.parameters), EXPECTED["api"]["parameters"])
        self.assertEqual(signature.return_annotation, "int")
        self.assertEqual([name for name, p in signature.parameters.items()
                          if p.kind == inspect.Parameter.KEYWORD_ONLY], ["label", "after_component"])
        self.assertIsNone(signature.parameters["after_component"].default)
        mutants = []
        missing = copy.deepcopy(value); del missing["ownership"]["final_raw_int_delivery_protected"]; mutants.append(missing)
        extra = copy.deepcopy(value); extra["claims"]["caller_confirmed_safe"] = True; mutants.append(extra)
        for section, key, changed in [("ownership", "final_raw_int_delivery_protected", True),
                                      ("ownership", "ordinary_line_walk_cleanup", 1),
                                      ("claims", "installed_or_native_qualification", 0),
                                      ("api", "return", "OwnedFd")]:
            mutant = copy.deepcopy(value); mutant[section][key] = changed; mutants.append(mutant)
        for mutant in mutants:
            with self.assertRaises(ValueError): validate_contract(mutant)
        module = next(m for m in json.loads((ROOT / "manifests/modules.v1.json").read_bytes())["modules"]
                      if m["id"] == EXPECTED["source_index"]["module"])
        self.assertIn("contracts/shared-source-reader.v1.json", module["contracts"])
        self.assertIn(EXPECTED["source_index"]["tests"], module["tests"])
        self.assertIn(EXPECTED["source_index"]["documentation"], module["architecture"])
        ast.parse((ROOT / EXPECTED["source"]).read_bytes())

    def test_normal_result_is_original_raw_int_owned_by_caller(self):
        before = census()
        descriptor = reader.open_regular_beneath(self.root, self.leaf, label="normal source")
        try:
            self.assertIs(type(descriptor), int)
            self.assertTrue(stat.S_ISREG(os.fstat(descriptor).st_mode))
            self.assertFalse(os.get_inheritable(descriptor))
            self.assertEqual(os.read(descriptor, 1024), b"original source bytes\n")
        finally:
            os.close(descriptor)
        gc.collect()
        self.assertEqual(census(), before)

    def test_original_before_previous_parent_close_cut_retires_new_parent(self):
        lines, first = inspect.getsourcelines(reader._open_regular_owned_beneath)
        target = first + next(i for i, line in enumerate(lines) if line.strip() == "current.close()")
        self.assert_owned_trace_cut(reader._open_regular_owned_beneath.__code__, "line", target)

    def test_owned_open_and_validation_lines_and_constructor_boundaries(self):
        lines, first = inspect.getsourcelines(reader._open_regular_owned_beneath)
        targets = [first + i for i, line in enumerate(lines)
                   if any(marker in line for marker in ["ancestors.append(", "leaf_owner =",
                       "os.fstat(current.fd)", "os.fstat(following.fd)", "os.fstat(leaf_owner.fd)",
                       "current = following", "return leaf_owner"])]
        for target in targets:
            with self.subTest(line=target):
                self.assert_owned_trace_cut(reader._open_regular_owned_beneath.__code__, "line", target)

    def test_private_owned_result_return_loss_closes_retained_leaf(self):
        self.assert_owned_trace_cut(reader._open_regular_owned_beneath.__code__, "return")

    def test_hook_exception_closes_all_actual_opened_directories(self):
        before = census()
        observed = []
        def refuse(index, component, descriptor):
            observed.append((index, component, os.fstat(descriptor).st_ino))
            raise KeyboardInterrupt("actual after_component interruption")
        with self.assertRaises(KeyboardInterrupt):
            reader.open_regular_beneath(self.root, self.leaf, label="hook source", after_component=refuse)
        gc.collect()
        self.assertEqual(observed, [(0, "parent", self.parent.stat().st_ino)])
        self.assertEqual(census(), before)

    def test_parent_and_leaf_close_after_effect_preserve_reused_foreign_fd(self):
        for kind in ("previous_parent", "leaf"):
            with self.subTest(kind=kind):
                before = census(); foreign = []; native = os.close
                def close(descriptor):
                    path = os.readlink(f"/proc/self/fd/{descriptor}")
                    native(descriptor)
                    selected = path == str(self.root if kind == "previous_parent" else self.leaf)
                    if selected and not foreign:
                        replacement = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                        if replacement != descriptor:
                            os.dup2(replacement, descriptor); native(replacement)
                        foreign.append(descriptor)
                        raise KeyboardInterrupt("actual close then integer reuse")
                lines, first = inspect.getsourcelines(reader._open_regular_owned_beneath)
                leaf_line = first + next(i for i, line in enumerate(lines) if "os.fstat(leaf_owner.fd)" in line)
                def trace(frame, event, argument):
                    if kind == "leaf" and frame.f_code is reader._open_regular_owned_beneath.__code__ and event == "line" and frame.f_lineno == leaf_line:
                        raise KeyboardInterrupt("owned leaf cleanup trigger")
                    return trace
                previous = sys.gettrace()
                try:
                    with mock.patch.object(reader.os, "close", side_effect=close):
                        sys.settrace(trace)
                        with self.assertRaises(KeyboardInterrupt):
                            reader.open_regular_beneath(self.root, self.leaf, label="reuse source")
                    sys.settrace(previous); gc.collect()
                    self.assertEqual(len(foreign), 1)
                    current, expected = os.fstat(foreign[0]), os.stat("/dev/null")
                    self.assertEqual((current.st_dev, current.st_ino), (expected.st_dev, expected.st_ino))
                    native(foreign.pop())
                    self.assertEqual(census(), before)
                finally:
                    sys.settrace(previous)
                    for descriptor in foreign: native(descriptor)

    def test_multiple_cleanup_owners_all_attempted_after_first_native_close_interrupt(self):
        before = census(); owners = []; attempted = []; native = os.close
        for _ in range(3):
            owner = reader._SourceDescriptor(); owner.fd = os.open(self.parent, os.O_RDONLY | os.O_DIRECTORY); owners.append(owner)
        originals = [owner.fd for owner in owners]
        def close(descriptor):
            native(descriptor); attempted.append(descriptor)
            if len(attempted) == 1: raise KeyboardInterrupt("first actual cleanup close completed")
        with mock.patch.object(reader.os, "close", side_effect=close):
            with self.assertRaises(KeyboardInterrupt): reader._close_source_descriptors(owners)
        self.assertEqual(attempted, list(reversed(originals)))
        self.assertTrue(all(owner.fd is None for owner in owners))
        gc.collect(); self.assertEqual(census(), before)

    def test_parent_rename_and_symlink_hook_keeps_original_inode_and_bytes(self):
        outside = self.root / "outside"; outside.mkdir(); (outside / self.leaf.name).write_bytes(b"substitution")
        pinned = self.root / "pinned"; observed = []
        def replace(index, component, descriptor):
            observed.append((index, component, os.fstat(descriptor).st_ino))
            self.parent.rename(pinned); self.parent.symlink_to(outside, target_is_directory=True)
        descriptor = reader.open_regular_beneath(self.root, self.leaf, label="pinned source", after_component=replace)
        try:
            self.assertEqual(os.read(descriptor, 1024), b"original source bytes\n")
            self.assertEqual(observed, [(0, "parent", pinned.stat().st_ino)])
            self.assertEqual(os.fstat(descriptor).st_ino, (pinned / self.leaf.name).stat().st_ino)
        finally: os.close(descriptor)

    def test_original_symlink_fifo_missing_root_and_leaf_refusals_do_not_leak(self):
        link = self.root / "link"; link.symlink_to(self.parent, target_is_directory=True)
        leaf_link = self.parent / "link.txt"; leaf_link.symlink_to(self.leaf)
        fifo = self.parent / "fifo"; os.mkfifo(fifo, 0o600)
        paths = [(self.root, link / self.leaf.name), (self.root, leaf_link),
                 (self.root, fifo), (self.root / "absent", self.root / "absent/x"),
                 (self.root, self.parent / "absent"), (self.root, self.parent)]
        for root, path in paths:
            with self.subTest(path=path):
                before = census()
                with self.assertRaises(ValueError): reader.open_regular_beneath(root, path, label="refused source")
                gc.collect(); self.assertEqual(census(), before)

    def test_final_raw_integer_return_loss_remains_outside_owned_stage_guarantee(self):
        # Preserve the ABI and demonstrate the documented final transfer limit.
        # This private probe owns and closes the actual undelivered descriptor.
        before = census(); delivered = []
        def trace(frame, event, argument):
            if frame.f_code is reader.open_regular_beneath.__code__ and event == "return" and not delivered:
                delivered.append(argument)
                raise KeyboardInterrupt("final raw integer delivery loss")
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt): reader.open_regular_beneath(self.root, self.leaf, label="raw delivery")
        finally: sys.settrace(previous)
        gc.collect()
        self.assertEqual(len(delivered), 1)
        self.assertIs(type(delivered[0]), int)
        self.assertEqual(os.fstat(delivered[0]).st_ino, self.leaf.stat().st_ino)
        os.close(delivered[0]); self.assertEqual(census(), before)


if __name__ == "__main__":
    unittest.main()
