"""Local source-binding controls; no Android, Main, NSS or account operations.

These tests execute the adapter's real support/identity/plan admission code.
The business support loader and Main identity collector are explicit inert
fixtures. The three entry inspections execute real Python subprocesses against
temporary source copies, without invoking any Android execution mode.
"""

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


CANDIDATE = Path(__file__).resolve().parents[1]
AUDIT = CANDIDATE.parent
OBSERVED = CANDIDATE / "test-fixtures"
ORIGINAL = OBSERVED / "editor-probe-current-preparation-20261108-r1"
SOURCE = CANDIDATE / "source"
REMOTE = Path("/home/alex/work/pocket4-android-final/qualification")
HOST = REMOTE / "business-support-host-20261108-r1"
CLOCK = REMOTE / "business-support-host-clock-20261108-r1"
OLD = REMOTE / "business-support-frozen-resume-20261107-r9"
OLD_CLOCK = REMOTE / "business-support-frozen-resume-20261107-r10"
HOST_SHA = "8cfa9cb05bb7e7768350dbe04acd4cd6421b9f4e8493746aad49b64c37969e70"
CLOCK_SHA = "0e1ea6f0d3b02c47f240b1aa26ccccf1b05f82bef7edee65331de421965a53ce"
OLD_SHA = "656101c6576a7749a55311750342749660944f0e67d143665bd03cc6c1eeb167"
OLD_CLOCK_SHA = "60d756127dba7e124b8acf39af80330c7d8fc9c6956363a58b631f00b0576612"


def module(path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), value.__dict__)
    return value


def file_ref(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def support_ref(directory, sha):
    return {"path": str(directory / "source-manifest.json"), "bytes": 1002, "sha256": sha}


def json_file(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    return file_ref(path)


class BindingControls(unittest.TestCase):
    def setUp(self):
        self.c = module(SOURCE / "app_common.py", "candidate_common")
        self.entry = module(SOURCE / "fixture_entry.py", "candidate_entry")
        self.planner = module(SOURCE / "fixture_plan.py", "candidate_plan")
        self.profiles = module(SOURCE / "fixture_profiles.py", "candidate_profiles")

    def mapped_regular(self, overrides=None):
        original = self.c.regular
        mapping = {str(HOST / "source-manifest.json"):
                       OBSERVED / HOST.name / "source-manifest.json",
                   str(CLOCK / "source-manifest.json"):
                       OBSERVED / CLOCK.name / "source-manifest.json"}
        mapping.update(overrides or {})

        def read(path, maximum=16 * 1024 * 1024, contents=True):
            requested = str(path)
            self.assertIn(requested, mapping, "unexpected source read")
            observed = original(mapping[requested], maximum, contents)
            if contents:
                raw, ref = observed
                return raw, {**ref, "path": requested}
            return {**observed, "path": requested}
        return read

    def test_old_common_refuses_current_host_cohort(self):
        old = module(ORIGINAL / "source/app_common.py", "predecessor_common")
        with patch.object(old, "read_ref", side_effect=AssertionError("must reject before source I/O")):
            with self.assertRaisesRegex(RuntimeError, "EXACT_REVIEWED_BUSINESS_SUPPORT_REQUIRED"):
                old.support(support_ref(HOST, HOST_SHA))

    def test_current_exact_supports_preserve_scope_and_select_matching_manifest(self):
        for directory, sha in [(HOST, HOST_SHA), (CLOCK, CLOCK_SHA)]:
            with self.subTest(cohort=directory.name):
                expected = support_ref(directory, sha)
                scope = types.SimpleNamespace(load_bundle=Mock(return_value={"explicit_host_fixture": True}))
                loader = Mock(return_value=scope)
                with patch.object(self.c, "regular", side_effect=self.mapped_regular()), patch.object(self.c, "module", loader):
                    actual, bundle = self.c.support(expected)
                self.assertIs(actual, scope)
                self.assertEqual(bundle, {"explicit_host_fixture": True})
                scope.load_bundle.assert_called_once_with(expected)
                called = loader.call_args.args[0]
                self.assertEqual(called["path"], str(directory / "business_scope.py"))
                self.assertEqual(called["sha256"], self.c.SCOPE_SHA)

    def test_old_regular_and_clock_cohorts_rejected_before_loading(self):
        with patch.object(self.c, "read_ref", side_effect=AssertionError("must reject before source I/O")):
            for directory, sha in [(OLD, OLD_SHA), (OLD_CLOCK, OLD_CLOCK_SHA)]:
                with self.subTest(cohort=directory.name):
                    with self.assertRaisesRegex(RuntimeError, "EXACT_REVIEWED_BUSINESS_SUPPORT_REQUIRED"):
                        self.c.support(support_ref(directory, sha))

    def test_changed_manifest_reference_rejected_before_loading(self):
        mutations = [dict(self.c.SUPPORT_REF, sha256="0" * 64),
                     dict(self.c.SUPPORT_REF, bytes=1003),
                     dict(self.c.SUPPORT_REF, path=str(HOST / "../source-manifest.json"))]
        with patch.object(self.c, "read_ref", side_effect=AssertionError("must reject before source I/O")):
            for ref in mutations:
                with self.subTest(reference=ref):
                    with self.assertRaisesRegex(RuntimeError, "EXACT_REVIEWED_BUSINESS_SUPPORT_REQUIRED"):
                        self.c.support(ref)

    def test_changed_actual_manifest_bytes_rejected_before_module_execution(self):
        with tempfile.TemporaryDirectory() as temp:
            altered = Path(temp) / "manifest.json"
            altered.write_bytes((OBSERVED / HOST.name / "source-manifest.json").read_bytes() + b"\n")
            loader = Mock(side_effect=AssertionError("changed bytes must never load code"))
            mapping = {str(HOST / "source-manifest.json"): altered}
            with patch.object(self.c, "regular", side_effect=self.mapped_regular(mapping)), patch.object(self.c, "module", loader):
                with self.assertRaisesRegex(RuntimeError, "REFERENCE_CHANGED"):
                    self.c.support()
            loader.assert_not_called()

    def identity(self, cohort, role="editor"):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            qualification = json_file(root / "qualification.json", {"source_manifest": cohort})
            request = {"baseline": {"explicit_fixture": True}, "qualification": qualification}
            req = json_file(root / "request.json", request)
            packet = {"files": [file_ref(SOURCE / "fixture_entry.py")]}
            planner = types.SimpleNamespace(named=Mock(return_value=self.profiles))
            collect = Mock(return_value={"explicit_inert_collector_fixture": True})
            arguments = [str(SOURCE / "fixture_entry.py"), "--preparation", "fixture-only",
                         "--expect-preparation-sha256", "0" * 64, "identity", "--role", role,
                         "--request", req["path"], "--expect-request-sha256", req["sha256"],
                         "--output", str(root / "no-output-created")]
            with patch.object(self.entry, "bootstrap", return_value=(self.c, packet, {}, planner)), \
                 patch.object(self.entry.os, "getuid", return_value=0), \
                 patch.object(self.entry.os, "geteuid", return_value=0), \
                 patch.object(self.c, "collect_identity", collect), \
                 patch.object(sys, "argv", arguments), redirect_stdout(io.StringIO()):
                try:
                    result = self.entry.main()
                except BaseException:
                    collect.assert_not_called()
                    raise
            self.assertFalse((root / "no-output-created").exists())
            return result, collect

    def test_identity_entry_admits_only_the_current_main_cohort(self):
        for role in ("editor", "qa-probe", "native-helper"):
            with self.subTest(role=role):
                result, collect = self.identity(support_ref(HOST, HOST_SHA), role)
                self.assertEqual(result, 0)
                collect.assert_called_once()

    def test_identity_entry_rejects_old_cohort_before_collection(self):
        with self.assertRaisesRegex(RuntimeError, "ACTUAL_HOST_BUSINESS_BASELINE_FOR_THESE_TWO_CASES"):
            self.identity(support_ref(OLD, OLD_SHA))

    def test_identity_entry_rejects_clock_cohort_for_editor_and_probe(self):
        with self.assertRaisesRegex(RuntimeError, "ACTUAL_HOST_BUSINESS_BASELINE_FOR_THESE_TWO_CASES"):
            self.identity(support_ref(CLOCK, CLOCK_SHA))

    def test_plan_rejects_mismatched_baseline_before_identities(self):
        baseline = types.SimpleNamespace(qualification={"source_manifest": support_ref(OLD, OLD_SHA)})
        support = {"business_baseline.py": types.SimpleNamespace(BusinessBaseline=Mock(return_value=baseline))}
        request = {k: {"explicit_fixture": k} for k in
                   ("baseline", "qualification", "target_identity", "helper_identity")}
        with patch.object(self.c, "support", return_value=(None, support)), \
             patch.object(self.c, "read_ref", side_effect=AssertionError("reject before identity I/O")):
            with self.assertRaisesRegex(RuntimeError, "SAME_CURRENT_FROZEN_BASELINE_REQUIRED"):
                self.planner.inputs(self.c, "editor_ui03", request, {})

    def inspect(self, change=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            copied = root / "source"
            shutil.copytree(SOURCE, copied)
            files = [file_ref(p) for p in sorted(copied.glob("*.py"))]
            prep = {"schema": "pocket4-final-editor-probe-preparation-v1",
                    "code_entrypoints_complete": True,
                    "Android_execution_authorized_by_publication": False,
                    "files": files,
                    "origins": [file_ref(ORIGINAL / "preparation.json")],
                    "runtime_qualified": False, "whole_app_business_accepted": False}
            ref = json_file(root / "preparation.json", prep)
            marker = root / "malicious-import-marker"
            if change:
                (copied / change).write_text((copied / change).read_text() +
                    "\nfrom pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('must never execute')\n")
            run = subprocess.run([sys.executable, "-I", "-B", str(copied / "fixture_entry.py"),
                                  "--preparation", ref["path"], "--expect-preparation-sha256", ref["sha256"],
                                  "inspect-source"], capture_output=True, text=True, timeout=15)
            self.assertFalse(marker.exists(), "source change executed before rejecting its seal")
            self.assertFalse(list(copied.rglob("__pycache__")))
            return run

    def test_actual_local_entry_source_inspection_is_inert(self):
        run = self.inspect()
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result["source_files"], 21)
        self.assertIs(result["source_entrypoints_present"], True)
        self.assertEqual(result["Android_UI_actions"], 0)
        self.assertIs(result["source_publication_authorizes_Android"], False)
        self.assertIs(result["whole_app_business_accepted"], False)

    def test_changed_common_source_cannot_execute_before_inspection(self):
        run = self.inspect("app_common.py")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("COMMON_SOURCE_PIN_CHANGED", run.stderr)

    def test_changed_task_source_cannot_execute_before_inspection(self):
        run = self.inspect("fixture_profiles.py")
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("REFERENCE_CHANGED", run.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
