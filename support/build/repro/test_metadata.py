#!/usr/bin/env python3
"""Actual helper subprocesses with an explicit fake Cargo; no Rust or guest."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a01_repro_metadata_profile", HERE / "profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
LOCKED = ["metadata", "--locked", "--format-version", "1"]


def fake_metadata(source):
    root = "path+file://" + str(source) + "#root@0.1.0"
    driver = "path+file://" + str(source / "driver") + "#driver@0.1.0"
    return {"version": 1, "workspace_root": str(source), "target_directory": str(source / "target"),
            "packages": [{"id": root, "name": "root", "dependencies": []},
                         {"id": driver, "name": "driver", "dependencies": [{"name": "component"}]}],
            "workspace_members": [root, driver], "workspace_default_members": [root],
            "resolve": {"root": root, "nodes": [
                {"id": root, "dependencies": [driver], "deps": [{"pkg": driver}]},
                {"id": driver, "dependencies": [], "deps": []}]}}


def fake_cargo(root, source):
    cargo = root / "cargo/bin/cargo"
    cargo.parent.mkdir(parents=True)
    data = root / "fake-metadata.json"
    data.write_text(json.dumps(fake_metadata(source)) + "\n")
    calls = root / "fake-cargo-calls.jsonl"
    cargo.write_text(f"#!{sys.executable} -I\n"
                     "import json,os,sys\nfrom pathlib import Path\n"
                     f"with Path({str(calls)!r}).open('a') as log: log.write(json.dumps(sys.argv[1:])+'\\n')\n"
                     f"sys.stdout.buffer.write(Path({str(data)!r}).read_bytes())\n"
                     "raise SystemExit(int(os.environ.get('A01_FAKE_CARGO_EXIT','0')))\n")
    cargo.chmod(0o700)
    return cargo, data, calls


class MetadataSubprocessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="a01-metadata-host-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        checkout = self.root / "checkout"
        self.source = checkout / "kernel/asterinas"
        self.source.mkdir(parents=True)
        (self.source / "Cargo.toml").write_text("[workspace]\n")
        components = b'[components]\ndriver={name="driver"}\n'
        (self.source / "Components.toml").write_bytes(components)
        self.owned = self.root / "profile"
        virtual = self.owned / "virtual-asterinas"
        virtual.mkdir(parents=True)
        profile.exclusive(virtual / "Components.toml", components, 0o400)
        profile.materialize_helpers(self.owned / "helpers", HERE)
        profile.exclusive(self.owned / "owner.json", b"{}\n")
        profile.exclusive(self.owned / "lock", b"")
        self.output = self.root / "output"
        (self.output / "metadata").mkdir(parents=True)
        self.cargo, self.metadata, self.calls = fake_cargo(self.root, self.source)
        inputs, states = profile.project_inputs(checkout, self.source)
        self.policy = {"project_root": str(checkout), "real_root": str(self.source),
                       "virtual_root": str(virtual), "profile_root": str(self.owned),
                       "output": str(self.output), "real_cargo": str(self.cargo),
                       "components_sha256": profile.digest(components),
                       "project_inputs": inputs, "project_input_states": states,
                       "profile_snapshot": profile.snapshot(self.owned)}
        self.policy_path = self.output / "policy.json"
        self.policy_path.write_text(json.dumps(self.policy))

    def invoke(self, args=LOCKED, **extra):
        return subprocess.run([sys.executable, "-B", "-I",
                               str(self.owned / "helpers/cargo-metadata-wrapper.py"), *args],
                              env=dict(os.environ, A01_REPRO_POLICY=str(self.policy_path), **extra),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)

    def test_current_locked_macro_call_projects_and_preserves_actual_lock_argument(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.calls.read_text()), LOCKED)
        mapped = json.loads(result.stdout)
        self.assertEqual(mapped["workspace_root"], self.policy["virtual_root"])
        self.assertEqual(mapped["packages"][1]["id"],
                         "path+file://" + self.policy["virtual_root"] + "/driver#driver@0.1.0")
        receipt = profile.metadata_receipts(self.output, self.policy)
        self.assertTrue(receipt["passed"])
        self.assertEqual(receipt["count"], 1)
        binding = json.loads(Path(receipt["receipts"][0]["binding"]).read_text())
        self.assertEqual(binding["argv"], [str(self.cargo), *LOCKED])
        self.assertEqual(binding["component_membership"], [{"name": "driver",
            "in_workspace_before": True, "in_workspace_after": True, "listed": True}])

    def test_other_metadata_commands_remain_original_and_cannot_satisfy_projection_gate(self):
        for args in (["metadata", "--format-version", "1"], LOCKED + ["--no-deps"],
                     ["metadata", "--locked", "--format-version", "2"]):
            with self.subTest(args=args):
                result = self.invoke(args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, self.metadata.read_bytes())
                self.assertEqual(list((self.output / "metadata").iterdir()), [])
                with self.assertRaisesRegex(ValueError, "no completed"):
                    profile.metadata_receipts(self.output, self.policy)

    def test_real_cargo_failure_is_retained_without_a_success_binding(self):
        result = self.invoke(A01_FAKE_CARGO_EXIT="37")
        self.assertEqual(result.returncode, 37)
        self.assertEqual(json.loads(self.calls.read_text()), LOCKED)
        self.assertEqual(len(list((self.output / "metadata").glob("*.original.json"))), 1)
        self.assertEqual(list((self.output / "metadata").glob("*.binding.json")), [])
        with self.assertRaises(OSError):
            profile.metadata_receipts(self.output, self.policy)

    def test_missing_component_is_rejected_by_the_real_helper(self):
        data = json.loads(self.metadata.read_text())
        data["packages"][1]["name"] = "undeclared-driver"
        self.metadata.write_text(json.dumps(data))
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        refusals = list((self.output / "metadata").glob("*.refusal.json"))
        self.assertEqual(len(refusals), 1)
        self.assertIn("missing from Components", json.loads(refusals[0].read_text())["message"])

    def test_partial_extra_altered_or_unbound_receipts_are_refused(self):
        self.assertEqual(self.invoke().returncode, 0)
        directory = self.output / "metadata"
        original = {path.name: path.read_bytes() for path in directory.iterdir()}
        binding_name = next(name for name in original if name.endswith(".binding.json"))
        mapped_name = next(name for name in original if name.endswith(".mapped.json"))
        for mutation in ("missing", "extra", "mapped", "command", "membership", "source_identity"):
            with self.subTest(mutation=mutation):
                for path in directory.iterdir():path.unlink()
                for name, data in original.items():(directory / name).write_bytes(data)
                if mutation == "missing":
                    (directory / binding_name).unlink()
                elif mutation == "extra":
                    (directory / "999-999.refusal.json").write_text("{}")
                else:
                    binding = json.loads(original[binding_name])
                    if mutation == "mapped":
                        mapped = json.loads(original[mapped_name])
                        mapped["packages"][1]["id"] = "path+file:///foreign#driver@0.1.0"
                        raw = (json.dumps(mapped, separators=(",", ":")) + "\n").encode()
                        (directory / mapped_name).write_bytes(raw)
                        binding["mapped_sha256"] = profile.digest(raw)
                    elif mutation == "command":binding["argv"].remove("--locked")
                    elif mutation == "membership":binding["component_membership"][0]["in_workspace_after"] = False
                    else:binding["source_identity"]["st_ino"] += 1
                    (directory / binding_name).write_text(json.dumps(binding))
                with self.assertRaises((OSError, ValueError)):
                    profile.metadata_receipts(self.output, self.policy)

    def test_empty_component_graph_cannot_count_as_a_bound_component_projection(self):
        data = json.loads(self.metadata.read_text())
        data["packages"][1]["dependencies"] = []
        self.metadata.write_text(json.dumps(data))
        self.assertEqual(self.invoke().returncode, 0)
        with self.assertRaisesRegex(ValueError, "no bound workspace component"):
            profile.metadata_receipts(self.output, self.policy)


class LauncherMetadataGateTests(unittest.TestCase):
    def run_case(self, emit_metadata, child_exit=0):
        temporary = tempfile.TemporaryDirectory(prefix="a01-launcher-metadata-host-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        checkout = root / "checkout"
        source = checkout / "kernel/asterinas"
        source.mkdir(parents=True)
        (source / "Cargo.toml").write_text("[workspace]\n")
        (source / "Components.toml").write_text('[components]\ndriver={name="driver"}\n')
        cargo, _data, _calls = fake_cargo(root, source)
        spec = importlib.util.spec_from_file_location("a01_launcher_metadata_gate", HERE / "run.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        def child(_command, **kwargs):
            if emit_metadata:
                policy = json.loads(Path(kwargs["env"]["A01_REPRO_POLICY"]).read_text())
                result = subprocess.run([sys.executable, "-B", "-I",
                    str(Path(policy["profile_root"]) / "helpers/cargo-metadata-wrapper.py"), *LOCKED],
                    env=kwargs["env"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=3)
                self.assertEqual(result.returncode, 0, result.stderr)
            return {"exit_code": child_exit, "raw_exit_code": child_exit}
        with patch.dict(os.environ, {"CARGO_HOME": str(cargo.parent.parent)}), \
                patch.object(launcher, "fixed_rustc_version", return_value=b"host-only fake version\n"), \
                patch.object(launcher, "owned_command", side_effect=child):
            status = launcher.run_locked(SimpleNamespace(action="kernel"), checkout, source,
                root / "profile", root / "profile/virtual-asterinas", root / "output",
                SimpleNamespace(signum=None), 0)
        return status, json.loads((root / "output/result.json").read_text())

    def test_successful_child_without_projection_cannot_report_launcher_success(self):
        status, receipt = self.run_case(False)
        self.assertEqual(status, 1)
        self.assertEqual(receipt["child_returncode"], 0)
        self.assertFalse(receipt["metadata_projection"]["passed"])
        self.assertIn("no completed", receipt["metadata_projection"]["error"])

    def test_subprocess_projection_and_components_binding_allow_launcher_success(self):
        status, receipt = self.run_case(True)
        self.assertEqual(status, 0)
        self.assertTrue(receipt["metadata_projection"]["passed"])
        self.assertEqual(receipt["metadata_projection"]["count"], 1)

    def test_original_nonzero_child_status_survives_missing_projection(self):
        status, receipt = self.run_case(False, child_exit=37)
        self.assertEqual(status, 37)
        self.assertEqual(receipt["child_returncode"], 37)
        self.assertFalse(receipt["metadata_projection"]["passed"])


if __name__ == "__main__":
    unittest.main()
