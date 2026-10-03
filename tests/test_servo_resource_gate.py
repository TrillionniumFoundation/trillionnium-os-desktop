from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_servo_resource_gate.py"
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("servo_resource_checker", CHECKER)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def source_only_fixture() -> tuple[dict, dict, str]:
    """Verifier input fixture, never an observation of a native Servo process."""
    origin = "http://127.0.0.1:43123"
    generations = []
    runtime = {"status": "PASS_HEADED_LOCAL_FIXTURE_ONLY", "servo_commit": checker.PIN}
    for generation, key in ((1, "initial_page_evidence"), (2, "recovery_page_evidence")):
        dom = {name: True for name in checker.DOM_TRUE}
        dom.update(forbiddenResourceExecuted=False, serviceWorkerProbe="unavailable")
        generations.append({
            "generation": generation, "callbacks": 4, "local_response_finishes": 1,
            "cancel_submissions": 3, "same_origin_script_cancels": 1,
            "wrong_method_fetch_cancels": 1, "external_script_cancels": 1,
            "dom": copy.deepcopy(dom),
        })
        runtime[key] = {"generation": generation, "loaded": True, **dom}
    report = {
        "schema": "trillionnium.desktop.servo-http-resource-gate.v1", "servo_commit": checker.PIN,
        "status": "OBSERVED_HTTP_CALLBACK_REFUSALS", "fixture_origin": origin,
        "fixture_network_requests": 0, "generations": generations,
        "global_cancel_submissions": 0, "global_callback_observed": False,
        "stale_cancel_submissions": 0, "default_resources_admitted": 0,
        "network_continuations_submitted": 0, "callback_bound_exceeded": False,
        "claim_ceiling": {key: False for key in checker.CEILING},
    }
    return report, runtime, origin


class ResourceGateBehaviorTests(unittest.TestCase):
    def test_actual_standalone_rust_policy_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "resource-tests"
            environment = dict(os.environ, RUSTUP_TOOLCHAIN="1.93.0")
            version = subprocess.run(["rustc", "--version"], env=environment,
                                     capture_output=True, text=True, timeout=30, check=True)
            self.assertTrue(version.stdout.startswith("rustc 1.93.0 "), version.stdout)
            compiled = subprocess.run([
                "rustc", "--edition=2024", "--test",
                str(ROOT / "experiments/servo-headed-runtime/src/resource_gate.rs"), "-o", str(binary),
            ], env=environment, capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            self.assertEqual(executed.returncode, 0, executed.stdout + executed.stderr)
            self.assertIn("10 passed", executed.stdout)

    def test_both_actual_callback_paths_cancel_and_owned_view_identity_is_checked(self):
        source = (ROOT / "experiments/servo-headed-runtime/src/main.rs").read_text()
        global_start = source.index("impl ServoDelegate for GlobalResourceDelegate")
        global_end = source.index("fn cancel_resource", global_start)
        self.assertIn("cancel_resource(load)", source[global_start:global_end])
        self.assertNotIn("LocalFixture", source[global_start:global_end])
        start = source.index("impl WebViewDelegate for RuntimeDelegate")
        end = source.index("fn notify_load_status_changed", start)
        callback = source[start:end]
        self.assertIn("owned.id() == webview.id()", callback)
        self.assertIn("self.current()", callback)
        self.assertIn("active_owned_webview", callback)
        cancel_start = source.index("fn cancel_resource")
        cancel_end = source.index("fn respond_to_resource", cancel_start)
        self.assertIn("load.intercept(response).cancel()", source[cancel_start:cancel_end])
        self.assertNotIn("DoNotIntercept", source)
        self.assertLess(source.index("servo.set_delegate("), source.index("state.create_webview()"))
        self.assertIn("interception.send_body_data(bytes.to_vec())", source)
        self.assertIn("interception.finish()", source)
        self.assertIn('"resource-gate-result.json"', source)

    def test_ci_copies_tests_and_restores_gate_and_verifies_actual_evidence(self):
        workflow = (ROOT / ".github/workflows/servo-headed-runtime.yml").read_text()
        runner = (ROOT / "tools/run_servo_headed_runtime_gate.sh").read_text()
        for content in (workflow, runner):
            self.assertIn("src/resource_gate.rs", content)
            self.assertIn("examples/resource_gate.rs", content)
            self.assertIn("check_servo_resource_gate.py", content)
            self.assertIn("--runtime-dir", content)
            self.assertIn("--servo-source", content)
        # Existing native input and failure/recovery thresholds remain explicit.
        self.assertIn("report['native_button_events'] >= 4", workflow)
        self.assertIn("report['input_handled_callbacks'] >= 6", workflow)
        self.assertIn("report['synthetic_ime_composition_events'] == 3", workflow)
        self.assertIn("run-held-gestures-v1", workflow)


class ResourceGateVerifierTests(unittest.TestCase):
    def test_workflow_checker_runs_in_a_fresh_step_shell_without_output_variable(self):
        workflow = (ROOT / ".github/workflows/servo-headed-runtime.yml").read_text()
        section = workflow.split("- name: Enforce evidence and claim ceiling", 1)[1].split("- name:", 1)[0]
        command = next(line.strip() for line in section.splitlines()
                       if "python3 tools/check_servo_resource_gate.py --runtime-dir" in line)
        environment = dict(os.environ)
        environment.pop("output", None)
        with tempfile.TemporaryDirectory() as temporary:
            working = Path(temporary)
            root = working / "artifacts/servo-headed-runtime/runtime"
            root.mkdir(parents=True)
            self.write_package(root, *source_only_fixture())
            command = command.replace("tools/check_servo_resource_gate.py", str(CHECKER))
            result = subprocess.run(["bash", "-euc", command], env=environment, cwd=working,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIs(json.loads(result.stdout)["product_ready"], False)
            self.assertFalse((root / "resource-gate-evidence.json").exists())

    def test_source_fixture_binds_each_actual_file_hash_without_native_claim(self):
        report, runtime, origin = source_only_fixture()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.write_package(root, report, runtime, origin)
            result = subprocess.run(["python3", str(CHECKER), "--runtime-dir", str(root)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            for field, name in (("resource_result_sha256", "resource-gate-result.json"),
                                ("runtime_result_sha256", "runtime-result.json"),
                                ("fixture_origin_sha256", "fixture-origin.txt")):
                self.assertEqual(receipt[field], hashlib.sha256((root / name).read_bytes()).hexdigest())
            self.assertIs(receipt["product_ready"], False)
            self.assertIs(receipt["global_callback_observed"], False)
            self.assertFalse((root / "resource-gate-evidence.json").exists())

    def test_default_cli_is_read_only_even_with_existing_output_leaf_or_symlink(self):
        for symlink in (False, True):
            with self.subTest(symlink=symlink), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write_package(root, *source_only_fixture())
                victim = root / "victim"
                victim.write_bytes(b"existing private bytes")
                leaf = root / "resource-gate-evidence.json"
                if symlink:
                    leaf.symlink_to(victim)
                else:
                    leaf.write_bytes(b"existing receipt bytes")
                before = {path.name: path.read_bytes() for path in root.iterdir()}
                result = subprocess.run(["python3", str(CHECKER), "--runtime-dir", str(root)],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIs(json.loads(result.stdout)["product_ready"], False)
                self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)
                self.assertEqual(leaf.is_symlink(), symlink)

    @staticmethod
    def write_package(root, report, runtime, origin):
        (root / "resource-gate-result.json").write_text(json.dumps(report) + "\n")
        (root / "runtime-result.json").write_text(json.dumps(runtime) + "\n")
        (root / "fixture-origin.txt").write_text(origin + "\n")

    def test_real_cli_refuses_negative_claims_even_with_matching_rewritten_dom(self):
        mutations = []
        for key in ("fixture_network_requests", "default_resources_admitted", "network_continuations_submitted"):
            mutations.extend((key, value) for value in (True, False, 1, 0.0, "0"))
        mutations.extend(("global_callback_observed", value) for value in (True, 0, "false"))
        mutations.extend(("callback_bound_exceeded", value) for value in (True, 0, "false"))
        mutations.extend(("generations", value) for value in ([], None, {}, [source_only_fixture()[0]["generations"][0]]))
        for key, value in mutations:
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as temporary:
                report, runtime, origin = source_only_fixture()
                report[key] = value
                root = Path(temporary)
                self.write_package(root, report, runtime, origin)
                result = subprocess.run(["python3", str(CHECKER), "--runtime-dir", str(root)],
                                        capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((root / "resource-gate-evidence.json").exists())
        for generation in range(2):
            for key in checker.DOM_TRUE + ("forbiddenResourceExecuted",):
                for value in (False if key != "forbiddenResourceExecuted" else True, 1, "true", None):
                    with self.subTest(generation=generation, key=key, value=value):
                        report, runtime, origin = source_only_fixture()
                        report["generations"][generation]["dom"][key] = value
                        runtime[("initial_page_evidence", "recovery_page_evidence")[generation]][key] = value
                        with self.assertRaises(ValueError):
                            checker.validate(report, runtime, origin)

    def test_strict_counts_generation_binding_and_totals(self):
        fields = ("callbacks", "local_response_finishes", "cancel_submissions",
                  "same_origin_script_cancels", "wrong_method_fetch_cancels", "external_script_cancels", "generation")
        for generation in range(2):
            for key in fields:
                for value in (True, False, -1, 0, 65, 1.0, "1", None):
                    with self.subTest(generation=generation, key=key, value=value):
                        report, runtime, origin = source_only_fixture()
                        report["generations"][generation][key] = value
                        with self.assertRaises(ValueError):
                            checker.validate(report, runtime, origin)
        report, runtime, origin = source_only_fixture()
        runtime["recovery_page_evidence"]["generation"] = 1
        with self.assertRaises(ValueError):
            checker.validate(report, runtime, origin)
        report, runtime, origin = source_only_fixture()
        report["generations"][0]["callbacks"] = 5
        with self.assertRaises(ValueError):
            checker.validate(report, runtime, origin)

    def test_closed_fields_authority_and_worker_availability(self):
        for key in checker.CEILING:
            report, runtime, origin = source_only_fixture()
            report["claim_ceiling"][key] = True
            with self.assertRaises(ValueError):
                checker.validate(report, runtime, origin)
        for worker in ("pending", "unexpectedly-registered", True, None):
            report, runtime, origin = source_only_fixture()
            report["generations"][0]["dom"]["serviceWorkerProbe"] = worker
            runtime["initial_page_evidence"]["serviceWorkerProbe"] = worker
            with self.assertRaises(ValueError):
                checker.validate(report, runtime, origin)
        report, runtime, origin = source_only_fixture()
        report["extra_authority"] = True
        with self.assertRaises(ValueError):
            checker.validate(report, runtime, origin)
        report, runtime, origin = source_only_fixture()
        report["global_cancel_submissions"] = 1
        with self.assertRaises(ValueError):
            checker.validate(report, runtime, origin)
        report["global_callback_observed"] = True
        checker.validate(report, runtime, origin)

    def test_actual_file_reader_refuses_duplicate_json_size_and_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "bad.json"
            for data in ('{"status":"PASS","status":"FAIL"}', " " * (checker.MAX_BYTES + 1)):
                path.write_text(data)
                with self.assertRaises(ValueError):
                    checker.load(path)
            link = root / "linked.json"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                checker.load(link)

    def test_retained_json_and_origin_fd_prevent_real_leaf_symlink_substitution(self):
        for name in ("resource-gate-result.json", "runtime-result.json", "fixture-origin.txt"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.write_package(root, *source_only_fixture())
                original_bytes = (root / name).read_bytes()
                attacker = root / "attacker"
                attacker.write_bytes(b'{}' if name.endswith(".json") else b"http://127.0.0.1:1")
                real_open = checker.open_managed_file
                def swapped_open(path):
                    descriptor = real_open(path)
                    if path.name == name:
                        path.rename(root / "saved")
                        path.symlink_to(attacker)
                    return descriptor
                with patch.object(checker, "open_managed_file", swapped_open):
                    receipt = checker.verify_runtime(root)
                field = {"resource-gate-result.json": "resource_result_sha256",
                         "runtime-result.json": "runtime_result_sha256",
                         "fixture-origin.txt": "fixture_origin_sha256"}[name]
                self.assertEqual(receipt[field], hashlib.sha256(original_bytes).hexdigest())
                with self.assertRaises(ValueError):
                    checker.verify_runtime(root)

    def test_real_parent_swap_during_walk_cannot_redirect_json_or_origin_read(self):
        import artifact_evidence
        for name in ("record.json", "fixture-origin.txt"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                evidence = root / "evidence"
                outside = root / "outside"
                evidence.mkdir(); outside.mkdir()
                original = b'{"original":true}' if name.endswith(".json") else b"http://127.0.0.1:43123"
                (evidence / name).write_bytes(original)
                (outside / name).write_bytes(b"attacker")
                real_open = artifact_evidence.open_managed_regular_beneath
                def after_component(index, component, descriptor):
                    if component == "evidence":
                        evidence.rename(root / "saved")
                        evidence.symlink_to(outside, target_is_directory=True)
                def swapped_open(*args, **kwargs):
                    return real_open(*args, **kwargs, after_component=after_component)
                with patch.object(artifact_evidence, "open_managed_regular_beneath", swapped_open):
                    self.assertEqual(checker.read_bounded(evidence / name, checker.MAX_BYTES), original)
                with self.assertRaises(ValueError):
                    checker.read_bounded(evidence / name, checker.MAX_BYTES)

    def test_regular_single_link_nofollow_bounds_for_json_and_origin(self):
        for name, limit in (("record.json", checker.MAX_BYTES), ("fixture-origin.txt", 64)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                file = root / name
                file.write_bytes(b"x" * (limit + 1))
                with self.assertRaises(ValueError):
                    checker.read_bounded(file, limit)
                file.write_bytes(b"x")
                link = root / "hard-link"
                os.link(file, link)
                with self.assertRaises(ValueError):
                    checker.read_bounded(file, limit)
                link.unlink(); file.unlink()
                os.mkfifo(file)
                with self.assertRaises(ValueError):
                    checker.read_bounded(file, limit)

    def test_real_file_mutation_between_same_fd_metadata_checks_refuses(self):
        for name, limit in (("record.json", checker.MAX_BYTES), ("fixture-origin.txt", 64)):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / name
                path.write_bytes(b"original")
                real_fstat = checker.os.fstat
                metadata_calls = 0
                def mutate_after_initial_snapshot(descriptor):
                    nonlocal metadata_calls
                    value = real_fstat(descriptor)
                    if value.st_ino == path.stat().st_ino:
                        metadata_calls += 1
                        # open_regular_beneath and open_file each inspect leaf;
                        # the third snapshot is this reader's before fstat.
                        if metadata_calls == 3:
                            path.write_bytes(b"changed-and-grown")
                    return value
                with patch.object(checker.os, "fstat", mutate_after_initial_snapshot):
                    with self.assertRaises(ValueError):
                        checker.read_bounded(path, limit)
                self.assertEqual(path.read_bytes(), b"changed-and-grown")


if __name__ == "__main__":
    unittest.main()
