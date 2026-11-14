"""Host-only controls; synthetic binding is explicitly not Main qualification."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("shared_rebind", HERE / "rebind_shared.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def source_inputs():
    root = HERE / "shared-r6-private"
    old_raw = (root / "source-manifest.json").read_bytes()
    manifest = r.parse(old_raw)
    old = {name: (root / name).read_bytes() for name in manifest["files"]}
    app = old["references/android_app.py"].decode()
    app = app.replace("[CTL,'status','--json']", "[CTL,'readiness','--json']")
    app = app.replace("    # the already isolated QA cell through android-app-qa.\n", "")
    app = app.replace("'target':'qa_cell_u1984','qa_cli':'android-app-qa',", "")
    backend = old["references/android_backend.py"].replace(
        b"[CTL,'status','--json']", b"[CTL,'readiness','--json']")
    # Native template substituted with visibly synthetic hashes. No template
    # functions are invoked; no /proc, services or Android access is performed.
    guard = (HERE.parent / "pocket4-r7-baseline/templates/current_baseline_guard.template.py").read_text()
    substitutions = {"BASELINE_SHA": "1" * 64, "QUALIFICATION_SHA": "2" * 64,
                     "CURRENT_EPOCH": "3" * 64, "MANIFEST_SHA": "4" * 64,
                     "BASELINE_BYTES": "101", "QUALIFICATION_BYTES": "102"}
    for name, value in substitutions.items():
        guard = guard.replace("@@" + name + "@@", value)
    guard = guard.encode()
    binding = {"schema": "pocket4-shared-r7-rebind-binding-v1", "epoch": "3" * 64,
        "baseline": {"path": str(r.BASELINE_ROOT / "baseline.private.json"), "bytes": 101,
                     "sha256": "1" * 64},
        "qualification": {"path": str(r.BASELINE_ROOT / "qualification.json"), "bytes": 102,
                          "sha256": "2" * 64},
        "guard": r.reference(r.BASELINE_ROOT / "current_baseline_guard.py", guard),
        "deployed_cohort": {"schema": "pocket4-shared-deployed-cohort-binding-v1",
            "manifest_sha256": r.DEPLOYMENT_MANIFEST_SHA, "source_commit": r.SOURCE_COMMIT,
            "target_count": 11, "final_pair": "candidate", "job_id": "HOST-CONTROL-ONLY",
            "references": {
                "manifest": {"path": "/HOST-CONTROL-ONLY/manifest.json", "bytes": 1,
                             "sha256": r.DEPLOYMENT_MANIFEST_SHA},
                "result": {"path": "/HOST-CONTROL-ONLY/result.json", "bytes": 1,
                           "sha256": "5" * 64},
                "terminal": {"path": "/HOST-CONTROL-ONLY/terminal.json", "bytes": 1,
                             "sha256": "6" * 64}}}}
    return old_raw, old, binding, app.encode(), backend, guard


class SharedRebindControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inputs = source_inputs()
        cls.files, cls.manifest_raw = r.render(*cls.inputs)

    def rendered_contract(self, directory):
        root = Path(directory)
        for name, raw in self.files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        (root / "source-manifest.json").write_bytes(self.manifest_raw)
        mod = r.load_module(self.files["source_contract.py"], root / "source_contract.py", "control_contract")
        contract = mod.SourceContract(root / "source-manifest.json", r.sha(self.manifest_raw))
        return mod, contract

    def test_real_old_source_and_installed_consumer_pins(self):
        old_raw, old, binding, app, backend, guard = self.inputs
        self.assertEqual(r.sha(old_raw), r.OLD_MANIFEST_SHA)
        self.assertEqual((len(app), r.sha(app)), (r.APP_BYTES, r.APP_SHA))
        self.assertEqual((len(backend), r.sha(backend)), (r.BACKEND_BYTES, r.BACKEND_SHA))

    def test_actual_complete_source_contract_and_frozen_history(self):
        with tempfile.TemporaryDirectory() as directory:
            mod, contract = self.rendered_contract(directory)
            contract.verify()
            self.assertEqual(len(contract.files), 14)
            self.assertEqual(mod.BASELINE_SCHEMA, r.BASELINE_SCHEMA)
            self.assertNotEqual(mod.MAIN_EPOCH, r.OLD_EPOCH)
            self.assertEqual(contract.files["references/android_app.py"],
                             {"bytes": r.APP_BYTES, "sha256": r.APP_SHA})
        old = self.inputs[1]
        unchanged = {"main_binding.py", "existing_ui_entry.py",
            "references/original_recorder.py", "references/framework_epoch.py",
            "references/task_scope_baseline.py", "references/held_runtime_r5.py",
            "references/bound_android_transport_r3.py"}
        self.assertEqual({n for n in self.files if self.files[n] == old[n]}, unchanged)

    def test_source_contract_detects_mutated_active_source(self):
        with tempfile.TemporaryDirectory() as directory:
            mod, contract = self.rendered_contract(directory)
            path = Path(directory) / "recorder.py"
            path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaisesRegex(RuntimeError, "ADAPTER_SOURCE_CHANGED:recorder.py"):
                contract.verify()

    def test_source_contract_detects_changed_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            mod, contract = self.rendered_contract(directory)
            path = Path(directory) / "source-manifest.json"
            path.write_bytes(path.read_bytes() + b"\n")
            with self.assertRaisesRegex(RuntimeError, "ADAPTER_MANIFEST_CHANGED_MID_FLOW"):
                contract.verify()

    def test_transport_real_length_and_sha_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            mod, contract = self.rendered_contract(directory)
            transport = contract.load("bound_android_transport.py", "control_transport")
            app = Path(directory) / "references/android_app.py"
            self.assertEqual(transport.source_bytes(app), self.inputs[3])
            app.write_bytes(self.inputs[1]["references/android_app.py"])
            with self.assertRaisesRegex(RuntimeError, "ANDROID_APP_SOURCE_SHAPE_DIFFERS"):
                transport.source_bytes(app)
            changed = bytearray(self.inputs[3]); changed[-1] ^= 1
            app.write_bytes(changed)
            with self.assertRaisesRegex(RuntimeError, "ANDROID_APP_SOURCE_PIN_DIFFERS"):
                transport.source_bytes(app)

    def test_old_epoch_refused(self):
        args = list(self.inputs); args[2] = copy.deepcopy(args[2]); args[2]["epoch"] = r.OLD_EPOCH
        with self.assertRaisesRegex(RuntimeError, "OLD_MAIN_EPOCH_MUST_REMAIN_RETIRED"):
            r.render(*args)

    def test_other_baseline_root_refused(self):
        args = list(self.inputs); args[2] = copy.deepcopy(args[2])
        args[2]["baseline"]["path"] = "/home/alex/work/pocket4-main-current-baseline-02/baseline.private.json"
        with self.assertRaisesRegex(RuntimeError, "EXACT_NEW_BASELINE_REFERENCE_REQUIRED"):
            r.render(*args)

    def test_wrong_cohort_content_count_and_result_refused(self):
        for key, value in (("manifest_sha256", "0" * 64), ("source_commit", "0" * 40),
                           ("target_count", 10), ("final_pair", "rollback")):
            with self.subTest(key=key):
                args = list(self.inputs); args[2] = copy.deepcopy(args[2])
                args[2]["deployed_cohort"][key] = value
                with self.assertRaisesRegex(RuntimeError, "EXACT_APPLIED_COHORT_REQUIRED"):
                    r.render(*args)

    def test_exact_old_source_and_new_guard_required(self):
        for index, code in ((0, "EXACT_OLD_MANIFEST_REQUIRED"),
                            (3, "EXACT_DEPLOYED_APP_REQUIRED"),
                            (4, "EXACT_DEPLOYED_BACKEND_REQUIRED"),
                            (5, "EXACT_V3_GUARD_BYTES_REQUIRED")):
            with self.subTest(index=index):
                args = list(self.inputs); args[index] += b"\n"
                with self.assertRaisesRegex(RuntimeError, code):
                    r.render(*args)
        args = list(self.inputs); args[1] = dict(args[1]); args[1]["main_binding.py"] += b"\n"
        with self.assertRaisesRegex(RuntimeError, "OLD_SOURCE_PIN_CHANGED:main_binding.py"):
            r.render(*args)

    def test_explicit_v3_guard_literals(self):
        guard = r.load_module(self.inputs[5], r.BASELINE_ROOT / "current_baseline_guard.py", "control_guard")
        r.verify_guard_literals(guard, self.inputs[2])
        guard.SOURCE_SCHEMA = "pocket4-current-baseline-source-v2"
        with self.assertRaisesRegex(RuntimeError, "EXACT_NATIVE_V3_GUARD_REQUIRED"):
            r.verify_guard_literals(guard, self.inputs[2])

    def test_scope_requires_same_deployed_cohort_and_v3(self):
        with tempfile.TemporaryDirectory() as directory:
            mod, contract = self.rendered_contract(directory)
            scope = {"schema": "pocket4-current-recorder-scope-v2", "current_baseline_schema": r.BASELINE_SCHEMA,
                "package": mod.PACKAGE, "component": mod.COMPONENT, "uid": mod.UID, "user": 0,
                "automatic_retry": False, "epoch_sha256": mod.MAIN_EPOCH, "current_baseline_sha256": mod.BASELINE_SHA,
                "current_baseline_qualification_sha256": mod.BASELINE_QUALIFICATION_SHA,
                "historical_activation_sha256": mod.HISTORICAL_ACTIVATION_SHA,
                "historical_verified_sha256": mod.HISTORICAL_VERIFIED_SHA,
                "adapter_manifest_sha256": contract.sha256,
                "recorder_sha256": contract.files["recorder.py"]["sha256"]}
            activation = {"schema": r.BASELINE_SCHEMA, "kind": "current-cell-generation",
                "deployment_performed": False, "framework_epoch": {"sha256": mod.MAIN_EPOCH},
                "historical_deployment": {"activation_sha256": mod.HISTORICAL_ACTIVATION_SHA,
                                          "verification_sha256": mod.HISTORICAL_VERIFIED_SHA},
                "framework_exit_cause_resolved": False, "whole_app_production_ready": False,
                "deployed_cohort_observed": True, "deployed_cohort": copy.deepcopy(self.inputs[2]["deployed_cohort"])}
            mod.verify_scope(scope, activation, contract)
            for which, mutate, code in (
                ("activation", lambda x: x.update(deployed_cohort_observed=False), "ACTUAL_CURRENT_SHARED_COHORT_REQUIRED"),
                ("activation", lambda x: x["deployed_cohort"].update(target_count=10), "ACTUAL_CURRENT_SHARED_COHORT_REQUIRED"),
                ("activation", lambda x: x["deployed_cohort"]["references"]["result"].update(sha256="0" * 64), "ACTUAL_CURRENT_SHARED_COHORT_REQUIRED"),
                ("scope", lambda x: x.update(current_baseline_schema="pocket4-main-current-baseline-v2"), "CURRENT_BILIBILI_SCOPE_REQUIRED")):
                with self.subTest(code=code):
                    a, s = copy.deepcopy(activation), copy.deepcopy(scope)
                    mutate(a if which == "activation" else s)
                    with self.assertRaisesRegex(RuntimeError, code):
                        mod.verify_scope(s, a, contract)

    def test_recorder_and_coordinator_logic_unchanged(self):
        constants = {"recorder.py": {"APP_SHA", "BACKEND_SHA"},
                     "current_coordinator.py": {"BASELINE", "QUALIFICATION", "BASELINE_SHA", "QUALIFICATION_SHA", "EPOCH", "GUARD_SOURCE_SHA"}}
        for name, names in constants.items():
            def structural(raw):
                tree = ast.parse(raw)
                tree.body = [n for n in tree.body if not (isinstance(n, ast.Assign)
                    and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                    and n.targets[0].id in names)]
                return ast.dump(tree, include_attributes=False)
            self.assertEqual(structural(self.inputs[1][name]), structural(self.files[name]))

    def test_rebind_manifest_is_explicitly_not_flow_admission(self):
        m = r.parse(self.manifest_raw)
        self.assertEqual(m["revision"], 7)
        self.assertEqual(m["parent_R6_manifest_sha256"], r.OLD_MANIFEST_SHA)
        self.assertNotIn("actual_baseline_result", m)
        self.assertTrue(m["source_fork_is_not_deployment"])
        for flag in ("old_flows_reauthorized", "old_helpers_and_tasks_reauthorized", "whole_app_production_ready"):
            self.assertIs(m[flag], False)

    def test_json_precision_and_duplicate_rejection(self):
        self.assertEqual(r.parse(b'{"n":1792775615719352105}')["n"], 1792775615719352105)
        with self.assertRaisesRegex(RuntimeError, "DUPLICATE_JSON_KEY"):
            r.parse(b'{"n":1,"n":2}')


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SharedRebindControls)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"schema": "pocket4-shared-r7-host-controls-v1", "tests_run": result.testsRun,
              "failures": len(result.failures), "errors": len(result.errors), "state": "PASS" if result.wasSuccessful() else "FAIL",
              "synthetic_Main_binding": True, "Main_reads": 0, "Android_commands": 0,
              "runtime_or_flow_admitted": False, "rebind_source_sha256": r.sha((HERE / "rebind_shared.py").read_bytes())}
    (HERE / "shared-rebind-host-controls.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if result.wasSuccessful() else 1)
