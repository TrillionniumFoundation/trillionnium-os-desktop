"""Execute the actual S06 shell guard against real source files and GNU grep.

These are source-boundary checks, not BrowserActor/Servo runtime qualifications.
"""
from __future__ import annotations

import os
import contextlib
import errno
import gc
import io
import inspect
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock
import sys

from tools import scan_s06_public_exports as scanner

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/s06-browser-actor.yml"
GOLDEN_PUBLIC_EXPORTS = [
    "pub use servo_runtime : : { ServoBrowserActor , ServoCompletionDelivery , ServoEventLoopWaker , ServoPumpResult , ServoRuntimeCommand , ServoRuntimeCompletion , ServoRuntimeEndpoint , ServoRuntimeError , ServoRuntimeOperation , ServoRuntimeOwner , closed_immutable_servo_runtime_pair , servo_runtime_pair , } ;",
    "pub use hepta_agent_port : : { AgentPortError , DispatchContext , HandlerOutcome } ;",
    "pub use hepta_agent_transport : : PeerIdentity ;",
    "pub use hepta_browser_codec : : { BrowserRequest , BrowserResponse , ElementReference , JsonObject , JsonValue , NavigationTarget , ObservationField , PageAction , ProfilePersistence , ProfileSpec , WaitCondition , } ;",
    "pub use hepta_peer_attestation : : { AttestedPeer , ProcfsPeerAttestor } ;",
    "pub use hepta_session_core : : ReceiptJournal ;",
    "pub use simulation : : { CancellationToken , PageOwnerSnapshot , ReceiptLifecycleObserver , TaskFlowPrincipal , executable_sha256 , scoped_frame_id , } ;",
]


def actual_guard() -> tuple[str, str]:
    source = WORKFLOW.read_text(encoding="utf-8")
    helpers = re.findall(r"(?ms)^          reject_match\(\) \{\n.*?^          \}", source)
    guards = re.findall(r"(?ms)^          export_inventory=.*?^          reject_match -R -n -E [^\n]*", source)
    if len(helpers) != 2 or helpers[0] != helpers[1] or len(guards) != 2 or guards[0] != guards[1]:
        raise AssertionError("both actual workflow jobs must use the same fail-closed guard")
    dedent = lambda text: "\n".join(line[10:] for line in text.splitlines())
    return dedent(helpers[0]), dedent(guards[0])


def descriptor_inventory():
    result = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            value = os.fstat(int(name))
            result[int(name)] = (value.st_dev, value.st_ino, value.st_mode)
        except OSError as error:
            if error.errno != errno.EBADF:
                raise
    return result


class ActualScandir:
    """Count actual native entries and close the actual underlying iterator."""
    def __init__(self, descriptor, native, observed, fail_after=None):
        self.inner = native(descriptor)
        self.observed = observed
        self.delivered = 0
        self.fail_after = fail_after
        self.closed = False
        observed["opened"] += 1

    def __iter__(self):
        return self

    def __next__(self):
        if self.fail_after is not None and self.delivered >= self.fail_after:
            raise PermissionError(errno.EACCES, "controlled native iterator read error")
        value = next(self.inner)
        self.delivered += 1
        self.observed["entries"] += 1
        return value

    def close(self):
        if not self.closed:
            self.closed = True
            self.observed["closed"] += 1
        self.inner.close()

    def __del__(self):
        self.close()


class S06PublicExportGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.source = self.directory / "src"
        self.source.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def run_guard(self, text: str | None = None, directory: Path | None = None):
        if text is not None:
            (self.source / "sample.rs").write_text(text, encoding="utf-8")
        helper, guard = actual_guard()
        guard = guard.replace("crates/hepta-browser-actor/src", shlex.quote(str(directory or self.source)))
        return subprocess.run(
            ["bash", "-c", "set -euo pipefail\n" + helper + "\n" + guard],
            cwd=ROOT, env={**os.environ, "RUNNER_TEMP": str(self.directory)},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
        )

    def test_actual_product_exports_match_closed_golden_and_guard(self):
        source = ROOT / "crates/hepta-browser-actor/src"
        self.assertEqual(scanner.inventory(source), GOLDEN_PUBLIC_EXPORTS)
        result = self.run_guard(directory=source)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_private_restricted_imports_and_literals_are_not_public_exports(self):
        source = r'''use simulation::{CallbackPageRuntime, RuntimeReply, PageRuntime};
pub(crate) use simulation::RuntimeReply;
pub(super) use simulation::PageRuntime;
pub(self) type PrincipalBinding = u8;
pub(in crate::private) use simulation::RequestControl;
// pub use simulation::MechanismIdentity;
/* pub use simulation::RuntimeReply; /* nested pub use simulation::PageRuntime; */ */
const MESSAGE: &str = "pub/*comment*/use simulation::RuntimeReply;";
const RAW: &str = r###"pub use simulation::PrincipalBinding;"###;
const BYTE: &[u8] = br##"pub use simulation::RequestControl;"##;
const C: &std::ffi::CStr = c"pub use simulation::PageRuntime;";
const CHARACTER: char = '\u{70}';
fn lifetime<'a>(value: &'a str) -> &'a str { value }
pub use safe::{PageRuntimeSuffix, OtherRuntimeReply, MechanismIdentityContainer};
pub type RuntimeReplyBox = u8;
'''
        result = self.run_guard(source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(scanner.public_exports(source)), 2)

    def test_single_multiline_commented_and_aliased_public_exports_are_refused(self):
        for name in ["PrincipalBinding", "MechanismIdentity", "PageRuntime", "CallbackPageRuntime", "RequestControl", "RuntimeReply"]:
            for source in [
                f"pub use simulation::{name};",
                f"pub\nuse simulation::{{\n{name} as Innocent,\n}};",
                f"pub/* nested /* comment */ here */use simulation::{{{name}}};",
                f"pub // comment\nuse simulation::{name} as Innocent;",
                f"pub use simulation::r#{name};",
            ]:
                with self.subTest(name=name, source=source):
                    result = self.run_guard(source)
                    self.assertEqual(result.returncode, 1, result.stderr)
                    self.assertIn("forbidden source match", result.stderr)

    def test_public_type_aliases_and_wildcard_exports_are_refused(self):
        for source in [
            "pub type Innocent = simulation::RuntimeReply;",
            "pub\n/*c*/type\nInnocent<'a> = &'a simulation::RequestControl;",
            "pub type r#PrincipalBinding = u8;",
            "pub use simulation::*;",
            "pub use simulation::{Allowed, nested::*};",
        ]:
            with self.subTest(source=source):
                result = self.run_guard(source)
                self.assertEqual(result.returncode, 1, result.stderr)

    def test_native_grep_match_absence_and_read_error_remain_distinct(self):
        helper, _ = actual_guard()
        fixture = self.directory / "grep-input"
        fixture.write_text("authority\n", encoding="utf-8")
        cases = [("authority", fixture, 1), ("absent", fixture, 0), ("authority", self.directory / "missing", 2)]
        for pattern, path, expected in cases:
            with self.subTest(pattern=pattern, path=path):
                result = subprocess.run(
                    ["bash", "-c", "set -euo pipefail\n" + helper + '\nreject_match -n -E "$PATTERN" "$SOURCE"'],
                    env={**os.environ, "PATTERN": pattern, "SOURCE": str(path)},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=15,
                )
                self.assertEqual(result.returncode, expected, result.stderr)
                if expected == 2:
                    self.assertIn("source absence scan failed with status 2", result.stderr)

    def test_source_error_is_not_converted_into_empty_success(self):
        for source in ['/* unclosed', 'const VALUE: &str = "unclosed', 'const VALUE: &str = r##"unclosed', "r#"]:
            with self.subTest(source=source):
                result = self.run_guard(source)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("public export source scan failed", result.stderr)
        result = self.run_guard(directory=self.directory / "missing-source")
        self.assertEqual(result.returncode, 2)

    def test_real_ancestor_symlink_and_hardlink_are_refused(self):
        original = self.source / "sample.rs"
        original.write_text("pub use safe::Allowed;", encoding="utf-8")
        alias = self.directory / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        self.assertEqual(self.run_guard(directory=alias).returncode, 2)
        os.link(original, self.source / "hardlink.rs")
        self.assertEqual(self.run_guard().returncode, 2)

    def test_bounded_inventory_and_read_fail_before_any_declaration_output(self):
        for index in range(scanner.MAX_FILES + 1):
            (self.source / f"{index:03d}.rs").write_text("pub use safe::Allowed;", encoding="utf-8")
        result = self.run_guard()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_symlinked_module_directory_is_not_silently_omitted(self):
        (self.source / "sample.rs").write_text("mod nested;", encoding="utf-8")
        foreign = self.directory / "outside-module"
        foreign.mkdir()
        (foreign / "mod.rs").write_text("pub use secret::PageRuntime;", encoding="utf-8")
        (self.source / "nested").symlink_to(foreign, target_is_directory=True)
        result = self.run_guard()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_actual_wide_directory_stops_at_first_global_excess_entry(self):
        count = scanner.MAX_ENTRIES * 2
        for number in range(count):
            (self.source / f"{number:05d}.ignored").write_bytes(b"")
        (self.source / "sample.rs").write_text("pub use safe::Allowed;\n", encoding="utf-8")
        before_files = {path.name: scanner._identity(path.lstat()) for path in self.source.iterdir()}
        before_fds = descriptor_inventory()
        observed = {"entries": 0, "opened": 0, "closed": 0}
        native = os.scandir
        with mock.patch.object(scanner.os, "scandir", side_effect=lambda fd: ActualScandir(fd, native, observed)):
            with self.assertRaisesRegex(ValueError, "entry bound"):
                scanner.inventory(self.source)
        gc.collect()
        self.assertEqual(observed["entries"], scanner.MAX_ENTRIES + 1)
        self.assertEqual(observed["opened"], observed["closed"])
        self.assertEqual(descriptor_inventory(), before_fds)
        self.assertEqual({path.name: scanner._identity(path.lstat()) for path in self.source.iterdir()}, before_files)

    def test_global_bound_covers_nested_entries_without_per_directory_prefetch(self):
        for number in range(8):
            nested = self.source / f"{number:02d}"
            nested.mkdir()
            for entry in range(160):
                (nested / f"{entry:03d}.ignored").write_bytes(b"")
        (self.source / "sample.rs").write_text("pub use safe::Allowed;\n", encoding="utf-8")
        observed = {"entries": 0, "opened": 0, "closed": 0}
        native = os.scandir
        before = descriptor_inventory()
        with mock.patch.object(scanner.os, "scandir", side_effect=lambda fd: ActualScandir(fd, native, observed)):
            with self.assertRaisesRegex(ValueError, "entry bound"):
                scanner.inventory(self.source)
        gc.collect()
        self.assertEqual(observed["entries"], scanner.MAX_ENTRIES + 1)
        self.assertEqual(observed["opened"], observed["closed"])
        self.assertEqual(descriptor_inventory(), before)

    def test_iterator_read_error_refuses_cli_without_partial_declarations(self):
        (self.source / "allowed.rs").write_text("pub use safe::Allowed;\n", encoding="utf-8")
        (self.source / "forbidden.rs").write_text("pub use forbidden::PageRuntime;\n", encoding="utf-8")
        observed = {"entries": 0, "opened": 0, "closed": 0}
        native = os.scandir
        before = descriptor_inventory()
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(scanner.os, "scandir", side_effect=lambda fd: ActualScandir(fd, native, observed, fail_after=1)):
            with mock.patch.object(sys, "argv", ["scanner", str(self.source)]):
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    self.assertEqual(scanner.main(), 2)
        gc.collect()
        self.assertEqual(output.getvalue(), "")
        self.assertIn("[Errno 13] controlled native iterator read error", errors.getvalue())
        self.assertEqual(observed["entries"], 1)
        self.assertEqual(observed["opened"], observed["closed"])
        self.assertEqual(descriptor_inventory(), before)

    def test_inaccessible_child_scandir_error_is_propagated_and_all_parents_close(self):
        (self.source / "allowed.rs").write_text("pub use safe::Allowed;\n", encoding="utf-8")
        private = self.source / "private"
        private.mkdir()
        (private / "mod.rs").write_text("pub use forbidden::PageRuntime;\n", encoding="utf-8")
        native = os.scandir
        observed = {"entries": 0, "opened": 0, "closed": 0}
        before = descriptor_inventory()
        def scan(fd):
            if os.readlink(f"/proc/self/fd/{fd}") == str(private):
                raise PermissionError(errno.EACCES, "controlled child enumeration denial")
            return ActualScandir(fd, native, observed)
        with mock.patch.object(scanner.os, "scandir", side_effect=scan):
            with self.assertRaises(PermissionError):
                scanner.inventory(self.source)
        gc.collect()
        self.assertEqual(observed["opened"], observed["closed"])
        self.assertEqual(descriptor_inventory(), before)

    def test_actual_entry_disappearing_before_stat_refuses_scan(self):
        path = self.source / "allowed.rs"
        path.write_text("pub use safe::Allowed;\n", encoding="utf-8")
        native = os.scandir
        observed = {"entries": 0, "opened": 0, "closed": 0}
        class RemovingScandir(ActualScandir):
            def __next__(self):
                value = super().__next__()
                (self_source / value.name).unlink()
                return value
        self_source = self.source
        before = descriptor_inventory()
        with mock.patch.object(scanner.os, "scandir", side_effect=lambda fd: RemovingScandir(fd, native, observed)):
            with self.assertRaises(FileNotFoundError):
                scanner.inventory(self.source)
        gc.collect()
        self.assertEqual(observed["opened"], observed["closed"])
        self.assertEqual(descriptor_inventory(), before)

    def test_fixed_depth_refuses_deep_real_tree_without_descriptor_leak(self):
        nested = self.source
        for number in range(scanner.MAX_DEPTH):
            nested = nested / f"{number:02d}"
            nested.mkdir()
        (nested / "mod.rs").write_text("pub use forbidden::PageRuntime;\n", encoding="utf-8")
        before = descriptor_inventory()
        with self.assertRaisesRegex(ValueError, "depth bound"):
            scanner.inventory(self.source)
        gc.collect()
        self.assertEqual(descriptor_inventory(), before)

    def test_total_read_bound_refuses_next_file_before_consuming_its_bytes(self):
        content = b"//" + b"x" * (scanner.MAX_SOURCE_BYTES - 2)
        for number in range(5):
            (self.source / f"{number}.rs").write_bytes(content)
        native = os.read
        observed = {"bytes": 0}
        def read(fd, count):
            data = native(fd, count)
            observed["bytes"] += len(data)
            return data
        before = descriptor_inventory()
        with mock.patch.object(scanner.os, "read", side_effect=read):
            with self.assertRaisesRegex(ValueError, "total byte bound"):
                scanner.inventory(self.source)
        gc.collect()
        self.assertEqual(observed["bytes"], scanner.MAX_TOTAL_BYTES)
        self.assertEqual(descriptor_inventory(), before)

    def test_retained_directory_line_interruptions_leave_no_descriptor_leak(self):
        (self.source / "sample.rs").write_text("pub use safe::Allowed;\n", encoding="utf-8")
        source_lines, first = inspect.getsourcelines(scanner._Descriptor.close)
        detach = first + next(i for i, line in enumerate(source_lines) if "descriptor, self.fd =" in line)
        native_call = first + next(i for i, line in enumerate(source_lines) if "attempted = True; os.close" in line)
        walk_lines, first_walk = inspect.getsourcelines(scanner._directory)
        walk_close = first_walk + next(i for i, line in enumerate(walk_lines) if "current.close()" in line)
        for target in (detach, native_call, walk_close):
            with self.subTest(line=target):
                before = descriptor_inventory()
                fired = []
                def trace(frame, event, argument):
                    if event == "line" and frame.f_code.co_filename == scanner.__file__ and frame.f_lineno == target and not fired:
                        fired.append(True)
                        raise KeyboardInterrupt("controlled ordinary Python line interruption")
                    return trace
                previous = sys.gettrace()
                try:
                    sys.settrace(trace)
                    with self.assertRaises(KeyboardInterrupt):
                        scanner.inventory(self.source)
                finally:
                    sys.settrace(previous)
                gc.collect()
                self.assertTrue(fired)
                self.assertEqual(descriptor_inventory(), before)

    def test_close_after_effect_does_not_retry_reused_foreign_descriptor(self):
        owner = scanner._Descriptor()
        owner.fd = os.open(self.source, os.O_RDONLY | os.O_DIRECTORY)
        original = owner.fd
        native = os.close
        foreign = []
        def close(fd):
            native(fd)
            replacement = os.open("/dev/null", os.O_RDONLY)
            if replacement != fd:
                os.dup2(replacement, fd)
                native(replacement)
            foreign.append(fd)
            raise KeyboardInterrupt("actual close completed before interruption")
        try:
            with mock.patch.object(scanner.os, "close", side_effect=close):
                with self.assertRaises(KeyboardInterrupt):
                    owner.close()
            self.assertEqual(foreign, [original])
            self.assertIsNone(owner.fd)
            owner.close()
            del owner
            gc.collect()
            self.assertEqual(os.fstat(original).st_ino, os.stat("/dev/null").st_ino)
        finally:
            native(original)

    def test_final_cleanup_line_interrupt_keeps_managed_iterator_and_descriptor_cleanup(self):
        (self.source / "sample.rs").write_text("pub use safe::Allowed;\n", encoding="utf-8")
        source_lines, first = inspect.getsourcelines(scanner.inventory)
        target = first + next(i for i, line in enumerate(source_lines) if "_close_all(owned)" in line)
        before = descriptor_inventory()
        observed = {"entries": 0, "opened": 0, "closed": 0}
        native = os.scandir
        fired = []
        def trace(frame, event, argument):
            if event == "line" and frame.f_code.co_filename == scanner.__file__ and frame.f_lineno == target and not fired:
                fired.append(True)
                raise KeyboardInterrupt("controlled final cleanup line interruption")
            return trace
        previous = sys.gettrace()
        try:
            with mock.patch.object(scanner.os, "scandir", side_effect=lambda fd: ActualScandir(fd, native, observed, fail_after=1)):
                sys.settrace(trace)
                with self.assertRaises(KeyboardInterrupt):
                    scanner.inventory(self.source)
        finally:
            sys.settrace(previous)
        gc.collect()
        self.assertTrue(fired)
        self.assertEqual(observed["opened"], observed["closed"])
        self.assertEqual(descriptor_inventory(), before)

    def test_source_leaf_parent_walk_line_cut_owns_the_new_descriptor_until_close(self):
        (self.source / "sample.rs").write_text("pub use safe::Allowed;\n", encoding="utf-8")
        lines, first = inspect.getsourcelines(scanner._directory)
        target = first + next(i for i, line in enumerate(lines) if "current.close()" in line)
        before = descriptor_inventory()
        fired = []
        def trace(frame, event, argument):
            if (event == "line" and frame.f_code is scanner._directory.__code__
                    and frame.f_lineno == target and frame.f_back.f_code is scanner._source.__code__ and not fired):
                fired.append((frame.f_locals["current"].fd, frame.f_locals["following"].fd))
                raise KeyboardInterrupt("actual source leaf walk interrupted before native parent close")
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt):
                scanner.inventory(self.source)
        finally:
            sys.settrace(previous)
        gc.collect()
        self.assertEqual(len(fired), 1)
        self.assertNotEqual(*fired[0])
        self.assertEqual(descriptor_inventory(), before)

    def test_owned_leaf_return_interruption_does_not_lose_its_descriptor(self):
        path = self.source / "sample.rs"
        path.write_text("pub use safe::Allowed;\n", encoding="utf-8")
        before = descriptor_inventory()
        fired = []
        def trace(frame, event, argument):
            if event == "return" and frame.f_code is scanner._source.__code__ and not fired:
                fired.append(frame.f_locals["leaf"].fd)
                raise KeyboardInterrupt("controlled owned leaf result delivery interruption")
            return trace
        previous = sys.gettrace()
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt):
                scanner.inventory(self.source)
        finally:
            sys.settrace(previous)
        gc.collect()
        self.assertEqual(len(fired), 1)
        self.assertEqual(descriptor_inventory(), before)

    def test_leaf_parent_actual_close_then_interrupt_preserves_reused_foreign_fd(self):
        path = self.source / "sample.rs"
        path.write_text("pub use safe::Allowed;\n", encoding="utf-8")
        lines, first = inspect.getsourcelines(scanner._source)
        target = first + next(i for i, line in enumerate(lines) if "parent.close()" in line)
        before = descriptor_inventory()
        closing = []
        foreign = []
        native = os.close
        def trace(frame, event, argument):
            if event == "line" and frame.f_code is scanner._source.__code__ and frame.f_lineno == target and not closing:
                closing.append(frame.f_locals["parent"].fd)
            return trace
        def close(fd):
            native(fd)
            if closing == [fd] and not foreign:
                replacement = os.open("/dev/null", os.O_RDONLY)
                if replacement != fd:
                    os.dup2(replacement, fd)
                    native(replacement)
                foreign.append(fd)
                raise KeyboardInterrupt("actual leaf parent close completed before interruption")
        previous = sys.gettrace()
        try:
            with mock.patch.object(scanner.os, "close", side_effect=close):
                sys.settrace(trace)
                with self.assertRaises(KeyboardInterrupt):
                    scanner._source(path)
            sys.settrace(previous)
            gc.collect()
            self.assertEqual(foreign, closing)
            self.assertEqual(len(foreign), 1)
            self.assertEqual(os.fstat(foreign[0]).st_ino, os.stat("/dev/null").st_ino)
            native(foreign.pop())
            self.assertEqual(descriptor_inventory(), before)
        finally:
            sys.settrace(previous)
            for fd in foreign:
                native(fd)

    def test_source_and_directory_drift_after_real_read_are_refused(self):
        path = self.source / "sample.rs"
        original = "pub use safe::Allowed;\n"
        native = os.read
        for kind in ("source", "directory"):
            with self.subTest(kind=kind):
                path.write_text(original, encoding="utf-8")
                late = self.source / "late.rs"
                late.unlink(missing_ok=True)
                fired = []
                def read(fd, count):
                    value = native(fd, count)
                    if value and not fired:
                        fired.append(True)
                        if kind == "source":
                            with path.open("ab") as stream:
                                stream.write(b"pub use forbidden::PageRuntime;\n")
                        else:
                            late.write_text("pub use forbidden::PageRuntime;\n", encoding="utf-8")
                    return value
                before = descriptor_inventory()
                with mock.patch.object(scanner.os, "read", side_effect=read):
                    with self.assertRaisesRegex(ValueError, "changed"):
                        scanner.inventory(self.source)
                gc.collect()
                self.assertTrue(fired)
                self.assertEqual(descriptor_inventory(), before)


if __name__ == "__main__":
    unittest.main()
