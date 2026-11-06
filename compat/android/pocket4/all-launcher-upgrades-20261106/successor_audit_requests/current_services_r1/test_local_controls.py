#!/usr/bin/env python3
"""Real owned host children and parser boundaries; no Android or Pocket4 reads."""
import ast
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]


def definitions(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


M = definitions(ROOT / "observe_current_services.py", "new_service_candidate_definitions")
T = definitions(ROOT / "readonly_services_transport.py", "closed_readonly_transport_definitions")


def function(text, name):
    node = next(node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef) and node.name == name)
    return ast.get_source_segment(text, node)


class NeverEntered:
    expected = {"pid": 999999}
    helper_sha256 = T.HELD_HELPER_SHA256

    def verify(self):
        raise AssertionError("Rejected operation reached actual target verification")


def rejected_transport(scope=T.EXPLICIT_SCOPE_SHA256, user=0):
    return T.BoundArun(target=NeverEntered(), environment={
        "PATH": "/system/bin", "BOOTCLASSPATH": "/fixture/a.jar", "DEX2OATBOOTCLASSPATH": "/fixture/a.jar",
        "ANDROID_ROOT": "/system", "ANDROID_DATA": "/data", "ANDROID_ART_ROOT": "/apex/com.android.art"},
        guard=lambda **unused: (_ for _ in ()).throw(AssertionError("unexpected guard entry")),
        record=lambda *unused: (_ for _ in ()).throw(AssertionError("unexpected command intent")),
        runner=lambda *unused, **options: (_ for _ in ()).throw(AssertionError("unexpected child")),
        epoch_sha256=T.FRAMEWORK_EPOCH_SHA256, init_pid=999999, app_scope_sha256=scope, user=user)


class Controls(unittest.TestCase):
    def test_mutating_foreign_user_and_reordered_commands_reject_before_target(self):
        for argv in (["/system/bin/cmd", "package", "grant", "com.sankuai.meituan.takeoutnew", "android.permission.ACCESS_FINE_LOCATION"],
                     ["/system/bin/cmd", "role", "add-role-holder", "android.app.role.DIALER", "fixture.pkg"],
                     ["/system/bin/cmd", "appops", "set", "fixture.pkg", "FINE_LOCATION", "allow"],
                     list(T.READ_ONLY_COMMANDS[3]), ["/system/bin/sh", "-c", "cmd package help"]):
            transport = rejected_transport()
            with self.assertRaisesRegex(T.TransportError, "EXACT_READONLY_COMMAND_SEQUENCE_REQUIRED"):
                transport(argv)
            self.assertTrue(transport._poisoned)
            with self.assertRaisesRegex(T.TransportError, "TRANSPORT_CLOSED_AFTER_FAILURE"):
                transport(list(T.READ_ONLY_COMMANDS[0]))
        for scope, user in (("0"*64, 0), (T.EXPLICIT_SCOPE_SHA256, 10), (T.EXPLICIT_SCOPE_SHA256, True)):
            with self.assertRaisesRegex(T.TransportError, "EXACT_NEW_READONLY_SERVICE_SCOPE_REQUIRED"):
                rejected_transport(scope, user)

    def test_seven_argv_are_closed_and_never_launch(self):
        self.assertEqual(len(T.READ_ONLY_COMMANDS), 7)
        self.assertEqual(T.READ_ONLY_COMMANDS[:3], (("/system/bin/cmd", "package", "help"),
            ("/system/bin/cmd", "appops", "help"), ("/system/bin/cmd", "role", "help")))
        self.assertEqual(T.READ_ONLY_COMMANDS[3:5], T.READ_ONLY_COMMANDS[5:7])
        self.assertEqual(T.READ_ONLY_COMMANDS[3][-2:], ("--user", "0"))
        self.assertEqual(T.READ_ONLY_COMMANDS[4][2], "query-activities")

    def test_actual_reference_Uids_versions_and_multiple_library_versions_preserved(self):
        scope = json.loads((PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json").read_bytes())
        # This serialises real reference metadata into the upstream text schema. It is not a PM observation.
        fixture = b"".join(("package:%s versionCode:%s uid:%s\n" % (name, row["version_code"], row["uid"])).encode()
                            for name, row in scope["apps"].items())
        fixture += b"package:fixture.library versionCode:1 uid:10999\npackage:fixture.library versionCode:2 uid:10999\n"
        rows = M.parse_packages(fixture)
        self.assertEqual(len(rows), 49)
        self.assertEqual([row["version_code"] for row in rows if row["package"] == "fixture.library"], [1, 2])
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_OR_OUT_OF_RANGE_PACKAGE_ROW"):
            M.parse_packages(fixture + fixture.splitlines(keepends=True)[0])
        for damaged in (b"package:fixture.pkg uid:1\n", b"package:fixture.pkg versionCode:1 uid:0\nwarning: partial\n"):
            with self.assertRaises(RuntimeError):
                M.parse_packages(damaged)

    def test_component_aliases_and_unrecognised_resolver_output(self):
        rows = M.parse_resolver(b"fixture.pkg/.Entry\nfixture.pkg/other.namespace.Alias\n")
        self.assertEqual([row["component"] for row in rows], ["fixture.pkg/fixture.pkg.Entry", "fixture.pkg/other.namespace.Alias"])
        self.assertEqual(M.parse_resolver(b"No activities found\n"), [])
        for raw in (b"1 activities found:\nfixture.pkg/.Entry\n", b"fixture.pkg/.Entry\nfixture.pkg/fixture.pkg.Entry\n"):
            with self.assertRaises(RuntimeError):
                M.parse_resolver(raw)

    def test_actual_help_must_expose_every_query_argument(self):
        fixture = b"list packages -U --show-versioncode --match-libraries --user USER_ID [FILTER]\nquery-activities --components INTENT -a <ACTION> -c <CATEGORY>\n"
        proof = M.require_help_for_closed_queries(fixture)
        self.assertEqual(proof["actual_help_sha256"], hashlib.sha256(fixture).hexdigest())
        for token in (b"--match-libraries", b"--components", b"-a <ACTION>"):
            with self.assertRaisesRegex(RuntimeError, "ACTUAL_PACKAGE_HELP_DOES_NOT_SUPPORT"):
                M.require_help_for_closed_queries(fixture.replace(token, b""))

    def test_original_R5_shared_helper_and_classpath_functions_are_identical(self):
        worker = (ROOT / "observe_current_services.py").read_text()
        shared = (PROJECT / "successor_qa/reconstructed/source-generation-r2/recorder/source_contract.py").read_text()
        binding = (PROJECT / "successor_qa/reconstructed/source-generation-r2/recorder/main_binding.py").read_text()
        for name in ("bounded_file", "verify_shared_helper"):
            self.assertEqual(function(worker, name), function(shared, name))
        for name in ("same_epoch_identity", "selected_environment", "main_classpaths"):
            self.assertEqual(function(worker, name), function(binding, name))

    def test_real_owned_child_receives_exact_seven_FDs_and_parent_recovers(self):
        before = len(os.listdir("/proc/self/fd"))
        held = []
        try:
            for unused in range(7):
                held.append(os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC))
            code = "import json,os,sys; print(json.dumps([os.fstat(int(fd)).st_rdev for fd in sys.argv[1:]]))"
            raw, stderr, result = M.held_bounded_child([sys.executable, "-I", "-B", "-c", code, *map(str, held)],
                5, 65536, tuple(held), {"PATH": "/usr/bin:/bin", "LANG": "C"})
            self.assertTrue(result["complete"])
            self.assertTrue(result["joined"])
            self.assertFalse(result["termination_attempted"])
            self.assertEqual(stderr, b"")
            self.assertEqual(json.loads(raw), [os.fstat(fd).st_rdev for fd in held])
        finally:
            for fd in held:
                os.close(fd)
        self.assertEqual(len(os.listdir("/proc/self/fd")), before)


if __name__ == "__main__":
    before = len(os.listdir("/proc/self/fd"))
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Controls))
    after = len(os.listdir("/proc/self/fd"))
    print(json.dumps({"schema": "pocket4-readonly-services-local-controls-v1", "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped),
                      "process_FDs_before": before, "process_FDs_after": after, "actual_Android_queries": 0,
                      "Pocket4_operations": 0, "namespace_entries": 0, "ok": result.wasSuccessful() and before == after}))
    raise SystemExit(0 if result.wasSuccessful() and before == after else 1)
