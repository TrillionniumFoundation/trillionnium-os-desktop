#!/usr/bin/env python3
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a01_repro_profile", HERE / "profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def fixture():
    root = "path+file:///actual#root@0.1.0"
    child = "path+file:///actual/driver#driver@0.1.0"
    return {"version": 1, "workspace_root": "/actual", "target_directory": "/actual/target",
            "packages": [{"id": root, "name": "root", "dependencies": []},
                         {"id": child, "name": "driver", "dependencies": [{"name": "component"}]}],
            "workspace_members": [root, child], "workspace_default_members": [root],
            "resolve": {"root": root, "nodes": [
                {"id": root, "dependencies": [child], "deps": [{"pkg": child}]},
                {"id": child, "dependencies": [], "deps": []}]}}


class Projection(unittest.TestCase):
    def test_compiler_map_keeps_all_required_osdk_arguments(self):
        incoming = ["/tool/rustc", "--crate-name", "aster_core", "/actual/kernel/core/src/lib.rs",
                    "--target", "x86_64-unknown-none", "--cfg", "ktest", "-C", "relocation-model=static",
                    "-C", "no-redzone=y", "--check-cfg", "cfg(ktest)"]
        effective = profile.compiler_argv(incoming, {"real_root": "/actual", "virtual_root": "/virtual"})
        self.assertEqual(effective[:-1], incoming)
        self.assertEqual(effective[-1], "--remap-path-prefix=/actual=/virtual")

    def test_existing_identical_map_is_not_duplicated(self):
        incoming = ["rustc", "--remap-path-prefix=/actual=/virtual", "--print", "sysroot"]
        self.assertEqual(profile.compiler_argv(incoming, {"real_root": "/actual", "virtual_root": "/virtual"}), incoming)

    def test_other_maps_and_end_of_options_are_preserved(self):
        incoming = ["rustc", "--remap-path-prefix=/other=/kept", "--", "-source.rs"]
        effective = profile.compiler_argv(incoming, {"real_root": "/actual", "virtual_root": "/virtual"})
        self.assertEqual(effective, ["rustc", "--remap-path-prefix=/other=/kept",
                                    "--remap-path-prefix=/actual=/virtual", "--", "-source.rs"])

    def test_conflicting_nested_map_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting"):
            profile.compiler_argv(["rustc", "--remap-path-prefix=/actual/driver=/foreign"],
                                  {"real_root": "/actual", "virtual_root": "/virtual"})

    def test_conflicting_split_option_map_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "conflicting"):
            profile.compiler_argv(["rustc", "--remap-path-prefix", "/actual=/foreign"],
                                  {"real_root": "/actual", "virtual_root": "/virtual"})

    def test_root_fragment_and_every_graph_reference_are_projected(self):
        data = fixture()
        mapped, checks = profile.project_metadata(data, "/actual", "/virtual", b'[components]\na={name="driver"}\n')
        self.assertEqual(mapped["packages"][0]["id"], "path+file:///virtual#root@0.1.0")
        self.assertEqual(mapped["resolve"]["nodes"][0]["deps"][0]["pkg"], mapped["packages"][1]["id"])
        self.assertNotIn("/actual", json.dumps(mapped))
        self.assertEqual(data, fixture())
        self.assertEqual(checks, [{"name": "driver", "in_workspace_before": True,
                                   "in_workspace_after": True, "listed": True}])

    def test_missing_component_is_rejected_before_projection(self):
        with self.assertRaisesRegex(ValueError, "missing from"):
            profile.project_metadata(fixture(), "/actual", "/virtual", b"[components]\n")

    def test_dangling_graph_reference_is_rejected(self):
        data = fixture()
        data["resolve"]["nodes"][0]["deps"][0]["pkg"] = "unresolved"
        with self.assertRaisesRegex(ValueError, "dangling"):
            profile.project_metadata(data, "/actual", "/virtual", b'[components]\na={name="driver"}\n')

    def test_projection_collision_is_rejected(self):
        data = fixture()
        data["packages"].append({"id": "path+file:///virtual#root@0.1.0", "name": "foreign", "dependencies": []})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            profile.project_metadata(data, "/actual", "/virtual", b'[components]\na={name="driver"}\n')

    def test_prefix_neighbor_is_not_rewritten(self):
        data = fixture()
        data["packages"].append({"id": "path+file:///actual-neighbor#other@0.1.0", "name": "other", "dependencies": []})
        mapped, _ = profile.project_metadata(data, "/actual", "/virtual", b'[components]\na={name="driver"}\n')
        self.assertEqual(mapped["packages"][-1], data["packages"][-1])


class CompilerMetadata(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "pkg").mkdir()
        (self.root / "pkg/Cargo.toml").write_text('[package]\nname="pkg"\nversion="0.1.0"\n')
        self.env = {"CARGO_MANIFEST_DIR": str(self.root / "pkg"),
                    "CARGO_PKG_NAME": "pkg", "CARGO_PKG_VERSION": "0.1.0"}
        self.policy = {"real_root": str(self.root), "virtual_root": "/virtual"}
        self.argv = ["rustc", "--crate-name", "pkg", "--crate-type", "lib", "src/lib.rs",
                     "--edition=2024", "--cfg", 'feature="one"', "-C", "metadata=original",
                     "-C", "extra-filename=-cargo-file", "-C", "opt-level=3", "-C", "panic=abort",
                     "-C", "lto=thin", "--out-dir", str(self.root / "target/deps")]

    def project(self, argv=None, env=None, history=None):
        return profile.canonical_compiler_metadata(argv or self.argv, env or self.env,
                                                   str(self.root / "pkg"), self.policy, history or [])

    def test_only_metadata_changes_and_all_other_execution_flags_survive(self):
        result, unit = self.project()
        changed = [index for index, pair in enumerate(zip(self.argv, result)) if pair[0] != pair[1]]
        self.assertEqual(changed, [self.argv.index("metadata=original")])
        self.assertEqual(result[changed[0]], "metadata=" + unit["canonical_id"])
        for flag in ("-Copt-level=3", "-Cpanic=abort", "-Clto=thin"):
            self.assertIn(flag, unit["descriptor"]["arguments"])

    def test_feature_target_profile_and_unknown_codegen_flags_do_not_merge(self):
        _, baseline = self.project()
        for extra in (["--cfg", 'feature="two"'], ["--target", "x86_64-unknown-none"],
                      ["-C", "opt-level=2"], ["-C", "panic=unwind"], ["-C", "lto=fat"],
                      ["-C", "future-behavior-option=yes"]):
            with self.subTest(extra=extra):
                _, unit = self.project(self.argv + extra)
                self.assertNotEqual(baseline["canonical_id"], unit["canonical_id"])

    def test_version_package_and_canonical_source_identity_do_not_merge(self):
        _, baseline = self.project()
        for key, value in (("CARGO_PKG_VERSION", "0.2.0"), ("CARGO_PKG_NAME", "other")):
            _, unit = self.project(env=dict(self.env, **{key: value}))
            self.assertNotEqual(baseline["canonical_id"], unit["canonical_id"])
        (self.root / "other").mkdir()
        (self.root / "other/Cargo.toml").write_bytes((self.root / "pkg/Cargo.toml").read_bytes())
        _, unit = self.project(env=dict(self.env, CARGO_MANIFEST_DIR=str(self.root / "other")))
        self.assertNotEqual(baseline["canonical_id"], unit["canonical_id"])

    def test_nonlocal_metadata_and_every_argument_are_unchanged(self):
        result, unit = self.project(env=dict(self.env, CARGO_MANIFEST_DIR="/registry/pkg-0.1.0"))
        self.assertEqual(result, self.argv)
        self.assertEqual(unit["scope"], "cargo-original")
        self.assertEqual(unit["effective_metadata"], "original")

    def test_cargo_print_probe_with_many_crate_types_remains_a_probe(self):
        argv = ["rustc", "-", "--crate-name", "___", "--print=file-names",
                "--crate-type", "bin", "--crate-type", "rlib", "--crate-type", "proc-macro"]
        self.assertEqual(self.project(argv), (argv, None))

    def test_unsupported_metadata_alias_and_duplicate_salt_are_refused(self):
        for argv in (self.argv + ["--codegen", "metadata=other"],
                     self.argv + ["--codegen=metadata=other"], self.argv + ["-Cmetadata=other"]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                self.project(argv)

    def test_only_known_implicit_sysroot_proc_macro_is_allowed_with_fixed_compiler(self):
        self.policy["rustc_identity"] = "fixed-nightly-version"
        _, unit = self.project(self.argv + ["--extern", "proc_macro"])
        self.assertIn("proc_macro=<fixed-sysroot:fixed-nightly-version>", unit["descriptor"]["arguments"])
        with self.assertRaisesRegex(ValueError, "implicit extern"):
            self.project(self.argv + ["--extern", "unknown"])
        del self.policy["rustc_identity"]
        with self.assertRaisesRegex(ValueError, "implicit extern"):
            self.project(self.argv + ["--extern", "proc_macro"])

    def test_prefix_neighbors_and_quoted_cfg_strings_keep_their_identity(self):
        argument = "--cfg=literal=\"" + str(self.root) + "/semantic\""
        neighbor = str(self.root) + "-neighbor/src/lib.rs"
        _, unit = self.project(self.argv + [argument, neighbor])
        self.assertIn(argument, unit["descriptor"]["arguments"])
        self.assertIn(neighbor, unit["descriptor"]["arguments"])

    def test_local_build_script_outputs_are_explicitly_outside_the_pinned_scope(self):
        with self.assertRaisesRegex(ValueError, "OUT_DIR"):
            self.project(env=dict(self.env, OUT_DIR=str(self.root / "target/build/pkg-12345678/out")))
        with self.assertRaisesRegex(ValueError, "build-script artifact paths"):
            self.project(self.argv + ["-L", "native=" + str(self.root / "target/release/build/pkg-12345678/out")])

    def test_different_opaque_salts_cannot_alias_one_descriptor(self):
        _, unit = self.project()
        different = ["metadata=another" if value == "metadata=original" else value for value in self.argv]
        with self.assertRaisesRegex(ValueError, "distinct Cargo units collide"):
            self.project(different, history=[{"state": "started", "unit": unit}])
        self.project(history=[{"state": "started", "unit": unit}])

    def producer(self, canonical="dependency-one", state="completed", returncode=0):
        artifact = self.root / "dependency.rlib"
        artifact.write_bytes(b"one")
        return artifact, {"state": state, "returncode": returncode,
                          "unit": {"canonical_id": canonical},
                          "artifacts": {str(artifact): profile.artifact_identity(artifact)}}

    def test_dependency_identity_is_bound_and_changes_descriptor(self):
        artifact, first = self.producer()
        argv = self.argv + ["--extern", "dependency=" + str(artifact)]
        _, baseline = self.project(argv, history=[first])
        second = copy.deepcopy(first)
        second["unit"]["canonical_id"] = "dependency-two"
        _, changed = self.project(argv, history=[second])
        self.assertNotEqual(baseline["canonical_id"], changed["canonical_id"])
        self.assertIn("dependency=<producer:dependency-one>", baseline["descriptor"]["arguments"])

    def test_missing_failed_unfinished_changed_and_ambiguous_producers_are_rejected(self):
        artifact, producer = self.producer()
        argv = self.argv + ["--extern", "dependency=" + str(artifact)]
        unfinished = dict(producer, state="started")
        failed = dict(producer, returncode=1)
        ambiguous = copy.deepcopy(producer)
        ambiguous["unit"]["canonical_id"] = "different"
        for history in ([], [unfinished], [failed], [producer, ambiguous]):
            with self.subTest(history=history), self.assertRaisesRegex(ValueError, "successful producer"):
                self.project(argv, history=history)
        artifact.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "successful producer"):
            self.project(argv, history=[producer])

    def test_launcher_queries_fixed_nightly_even_when_caller_defaults_to_stable(self):
        spec = importlib.util.spec_from_file_location("a01_repro_run", HERE / "run.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        cargo_home = self.root / "cargo"
        (cargo_home / "bin").mkdir(parents=True)
        shim = cargo_home / "bin/rustc"
        shim.write_text('#!/usr/bin/python3 -I\nimport json,os,sys\n'
                        'print(json.dumps({"argv":sys.argv[1:],"caller":os.environ.get("RUSTUP_TOOLCHAIN")}))\n')
        shim.chmod(0o500)
        original = os.environ.get("RUSTUP_TOOLCHAIN")
        os.environ["RUSTUP_TOOLCHAIN"] = "stable"
        try:
            observed = json.loads(launcher.fixed_rustc_version(cargo_home))
        finally:
            if original is None:
                del os.environ["RUSTUP_TOOLCHAIN"]
            else:
                os.environ["RUSTUP_TOOLCHAIN"] = original
        self.assertEqual(observed, {"argv": ["+nightly-2026-07-21", "-vV"], "caller": "stable"})

    def test_opt_in_launcher_overrides_parallel_caller_without_mutating_it(self):
        spec = importlib.util.spec_from_file_location("a01_repro_run", HERE / "run.py")
        launcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        caller = dict(os.environ, CARGO_BUILD_JOBS="2", A01_FIXTURE_UNRELATED="kept")
        effective = launcher.proof_environment(caller)
        result = subprocess.run([sys.executable, "-B", "-I", "-c",
                                 'import json,os;print(json.dumps([os.environ["CARGO_BUILD_JOBS"],os.environ["A01_FIXTURE_UNRELATED"]]))'],
                                env=effective, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        self.assertEqual(json.loads(result.stdout), ["1", "kept"])
        self.assertEqual(caller["CARGO_BUILD_JOBS"], "2")
        self.assertEqual(launcher.PROOF_CARGO_JOBS, 1)


class ProjectDependency(unittest.TestCase):
    """Current main's outside-kernel os-control edge; no compiler execution."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.virtual = self.root / "profile/virtual-asterinas"

    def fixture(self, name):
        checkout = self.root / name
        source, control = checkout / "kernel/asterinas", checkout / "libs/os-control"
        (source / "kernel/core").mkdir(parents=True)
        (control / "src").mkdir(parents=True)
        # This is the current derived workspace's exact path/feature edge.
        (source / "Cargo.toml").write_text('[workspace.dependencies]\nos-control = '
            '{ path = "../../libs/os-control", default-features = false, features = ["portable-spin"] }\n')
        (source / "Components.toml").write_text('[components]\ncore={name="core"}\n')
        (source / "kernel/core/Cargo.toml").write_text('[package]\nname="core"\nversion="0.1.0"\n')
        (control / "Cargo.toml").write_text('[package]\nname="os-control"\nversion="0.1.0"\n'
            '[lib]\npath="src/lib.rs"\n[features]\nportable-spin=[]\n'
            '[dev-dependencies]\nhos2-os-abi={path="../os-abi"}\n'
            '[[test]]\nname="control_conformance"\npath="../../tests/control/control_conformance.rs"\n')
        (control / "src/lib.rs").write_text('// controlled source-identity fixture; never compiled\n')
        inputs, states = profile.project_inputs(checkout, source)
        policy = {"project_root": str(checkout), "real_root": str(source),
                  "virtual_root": str(self.virtual), "project_inputs": inputs,
                  "project_input_states": states, "rustc_identity": "fixed-rustc-identity"}
        return checkout, source, control, policy

    def compiler(self, control, source, salt="original"):
        env = {"CARGO_MANIFEST_DIR": str(control), "CARGO_PKG_NAME": "os-control", "CARGO_PKG_VERSION": "0.1.0"}
        args = ["rustc", "--crate-name", "os_control", "--crate-type", "lib", "src/lib.rs",
                "--edition=2021", "--cfg", 'feature="portable-spin"', "--target", "x86_64-unknown-none",
                "-C", "metadata=" + salt, "-C", "extra-filename=-" + salt,
                "-C", "panic=abort", "-C", "lto=thin", "--out-dir", str(source / "target/deps")]
        return args, env

    def project(self, control, source, policy, salt="original", extra=(), env_changes=None, history=()):
        args, env = self.compiler(control, source, salt)
        env.update(env_changes or {})
        effective = profile.compiler_argv(args + list(extra), policy)
        result, unit = profile.canonical_compiler_metadata(effective, env, str(control), policy, list(history))
        return effective, result, unit

    def test_current_outside_kernel_dependency_matches_across_two_checkouts(self):
        first, second = self.fixture("A"), self.fixture("B")
        outputs = [self.project(control, source, policy, salt=name)
                   for name, (_checkout, source, control, policy) in zip(("cargo-A", "cargo-B"), (first, second))]
        self.assertEqual(first[3]["project_inputs"], second[3]["project_inputs"])
        self.assertNotEqual(first[3]["project_input_states"], second[3]["project_input_states"])
        self.assertEqual(outputs[0][2]["descriptor"], outputs[1][2]["descriptor"])
        self.assertEqual(outputs[0][2]["canonical_id"], outputs[1][2]["canonical_id"])
        for effective, result, unit in outputs:
            self.assertEqual(unit["scope"], "canonical-local")
            self.assertEqual(sum(a != b for a, b in zip(effective, result)), 1)
            self.assertEqual(unit["descriptor"]["manifest"], str(self.virtual.with_name("virtual-os-control")))
            self.assertIn("source_sha256", unit["descriptor"]["project_source"])
            self.assertEqual(len([a for a in effective if a.startswith("--remap-path-prefix=")]), 2)

    def test_kernel_consumer_binds_same_successful_control_producer(self):
        consumers = []
        for name in ("A", "B"):
            _checkout, source, control, policy = self.fixture(name)
            _effective, _result, dependency = self.project(control, source, policy, salt=name)
            artifact = source / "fixture-control.rlib"
            artifact.write_bytes(b"controlled artifact identity; no compiler")
            history = [{"state": "completed", "returncode": 0, "unit": dependency,
                        "artifacts": {str(artifact): profile.artifact_identity(artifact)}}]
            args, _env = self.compiler(control, source, salt="core-" + name)
            args[args.index("os_control")] = "core"
            args += ["--extern", "os_control=" + str(artifact)]
            env = {"CARGO_MANIFEST_DIR": str(source / "kernel/core"), "CARGO_PKG_NAME": "core", "CARGO_PKG_VERSION": "0.1.0"}
            _result, unit = profile.canonical_compiler_metadata(profile.compiler_argv(args, policy), env,
                str(source / "kernel/core"), policy, history)
            consumers.append(unit)
        self.assertEqual(consumers[0]["descriptor"], consumers[1]["descriptor"])
        self.assertEqual(consumers[0]["canonical_id"], consumers[1]["canonical_id"])

    def test_foreign_registry_and_toolchain_units_keep_original_identity(self):
        _checkout, source, control, policy = self.fixture("A")
        for foreign in ("/registry/os-control-0.1.0", "/fixed-toolchain/library/core"):
            effective, result, unit = self.project(control, source, policy,
                env_changes={"CARGO_MANIFEST_DIR": foreign})
            self.assertEqual(result, effective)
            self.assertEqual(unit["scope"], "cargo-original")
            self.assertEqual(unit["manifest"], foreign)
            self.assertEqual(unit["effective_metadata"], "original")

    def test_unknown_checkout_packages_and_nested_manifests_are_refused(self):
        checkout, source, control, policy = self.fixture("A")
        for relative in ("libs/os-abi", "libs/foreign", "libs/os-control-neighbor", "libs/os-control/nested"):
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "undeclared project local"):
                self.project(control, source, policy, env_changes={"CARGO_MANIFEST_DIR": str(checkout / relative)})
        with self.assertRaisesRegex(ValueError, "noncanonical manifest"):
            self.project(control, source, policy, env_changes={"CARGO_MANIFEST_DIR": str(source) + "/../../libs/foreign"})

    def test_package_identity_and_unknown_projection_binding_are_refused(self):
        _checkout, source, control, policy = self.fixture("A")
        for change in ({"CARGO_PKG_NAME": "foreign"}, {"CARGO_PKG_VERSION": "9.0.0"}):
            with self.assertRaisesRegex(ValueError, "declared local package identity"):
                self.project(control, source, policy, env_changes=change)
        altered = copy.deepcopy(policy)
        altered["project_inputs"]["os-control"]["relative_root"] = "libs/foreign"
        with self.assertRaisesRegex(ValueError, "unknown project local"):
            self.project(control, source, altered)

    def test_manifest_or_source_change_cannot_reuse_selected_inputs(self):
        for name in ("Cargo.toml", "src/lib.rs"):
            _checkout, source, control, policy = self.fixture(name.replace("/", "-"))
            with (control / name).open("a") as stream:
                stream.write("\n# changed bytes\n" if name == "Cargo.toml" else "\n// changed bytes\n")
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                self.project(control, source, policy)

    def test_new_source_binding_changes_identity_even_with_same_manifest(self):
        checkout, source, control, policy = self.fixture("A")
        _effective, _result, before = self.project(control, source, policy)
        (control / "src/lib.rs").write_text("// different implementation bytes\n")
        refreshed = dict(policy)
        refreshed["project_inputs"], refreshed["project_input_states"] = profile.project_inputs(checkout, source)
        _effective, _result, after = self.project(control, source, refreshed)
        self.assertNotEqual(before["canonical_id"], after["canonical_id"])

    def test_escape_and_symlink_dependency_roots_are_refused(self):
        checkout, source, control, _policy = self.fixture("A")
        (source / "Cargo.toml").write_text('[workspace.dependencies]\nos-control={path="../../foreign"}\n')
        with self.assertRaisesRegex(ValueError, "exact same-checkout"):
            profile.project_inputs(checkout, source)
        checkout, source, control, _policy = self.fixture("B")
        moved = control.with_name("original-control")
        control.rename(moved)
        control.symlink_to(moved, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            profile.project_inputs(checkout, source)

    def test_extra_root_conflicting_remap_and_codegen_differences_remain_visible(self):
        _checkout, source, control, policy = self.fixture("A")
        with self.assertRaisesRegex(ValueError, "conflicting"):
            self.project(control, source, policy, extra=["--remap-path-prefix=" + str(control / "src") + "=/foreign"])
        _effective, _result, baseline = self.project(control, source, policy)
        for extra in (["--cfg", 'feature="other"'], ["-C", "panic=unwind"], ["-C", "lto=fat"],
                      ["-C", "future-behavior-option=yes"]):
            _effective, _result, unit = self.project(control, source, policy, extra=extra)
            self.assertNotEqual(baseline["canonical_id"], unit["canonical_id"])
        args, env = self.compiler(control, source)
        args[args.index("x86_64-unknown-none")] = "x86_64-unknown-linux-gnu"
        _result, unit = profile.canonical_compiler_metadata(profile.compiler_argv(args, policy),env,str(control),policy,[])
        self.assertNotEqual(baseline["canonical_id"], unit["canonical_id"])

    def metadata(self, checkout, source, control):
        data = json.loads(json.dumps(fixture()).replace("/actual", str(source)))
        pid = "path+file://" + str(control) + "#os-control@0.1.0"
        data["packages"].append({"id": pid, "name": "os-control", "version": "0.1.0", "source": None,
            "manifest_path": str(control / "Cargo.toml"),
            "targets": [{"src_path": str(control / "src/lib.rs")},
                        {"src_path": str(checkout / "tests/control/control_conformance.rs")}],
            "dependencies": [{"name": "component"}, {"name": "hos2-os-abi", "path": str(checkout / "libs/os-abi"), "kind": "dev"}]})
        data["resolve"]["nodes"][0]["dependencies"].append(pid)
        data["resolve"]["nodes"][0]["deps"].append({"pkg": pid})
        data["resolve"]["nodes"].append({"id": pid, "dependencies": [], "deps": []})
        return data

    def test_metadata_graph_is_coherent_without_changing_component_membership(self):
        checkout, source, control, policy = self.fixture("A")
        data = self.metadata(checkout, source, control)
        mapped, checks = profile.project_metadata(data, str(source), str(self.virtual),
            b'[components]\na={name="driver"}\n', policy)
        original, projected = data["packages"][-1], mapped["packages"][-1]
        expected = str(self.virtual.with_name("virtual-os-control"))
        self.assertEqual(projected["id"], "path+file://" + expected + "#os-control@0.1.0")
        self.assertEqual(mapped["resolve"]["nodes"][0]["deps"][-1]["pkg"], projected["id"])
        self.assertEqual(projected["targets"][0]["src_path"], expected + "/src/lib.rs")
        self.assertEqual(projected["targets"][1], original["targets"][1])
        self.assertEqual(projected["dependencies"][-1], original["dependencies"][-1])
        self.assertEqual(checks[-1], {"name":"os-control","in_workspace_before":False,
            "in_workspace_after":False,"listed":False})
        with self.assertRaisesRegex(ValueError, "missing from"):
            profile.project_metadata(data, str(source), str(self.virtual), b'[components]\n', policy)

    def test_projected_metadata_rejects_identity_drift_collisions_and_dangling_ids(self):
        checkout, source, control, policy = self.fixture("A")
        data = self.metadata(checkout, source, control)
        for field, value in (("name", "foreign"), ("version", "9.0.0"), ("manifest_path", str(control / "nested/Cargo.toml"))):
            changed = copy.deepcopy(data);changed["packages"][-1][field] = value
            with self.assertRaisesRegex(ValueError, "local package|declared manifest"):
                profile.project_metadata(changed,str(source),str(self.virtual),b'[components]\na={name="driver"}\n',policy)
        changed = copy.deepcopy(data)
        changed["packages"].append({"id":"path+file://" + str(self.virtual.with_name("virtual-os-control")) + "#os-control@0.1.0",
                                   "name":"foreign","dependencies":[]})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            profile.project_metadata(changed,str(source),str(self.virtual),b'[components]\na={name="driver"}\n',policy)
        changed = copy.deepcopy(data);changed["resolve"]["nodes"][-1]["deps"].append({"pkg":"missing"})
        with self.assertRaisesRegex(ValueError, "dangling"):
            profile.project_metadata(changed,str(source),str(self.virtual),b'[components]\na={name="driver"}\n',policy)

    def test_real_launcher_owner_reuses_equal_sources_across_checkouts(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location("a01_repro_run_project", HERE / "run.py")
        launcher = importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)
        first, second = self.fixture("A"), self.fixture("B")
        root = self.virtual.parent
        for i, (checkout, source, _control, _policy) in enumerate((first, second)):
            with patch.object(launcher,"fixed_rustc_version",return_value=b"host-only fixed compiler identity\n"), \
                    patch.object(launcher,"owned_command",return_value={"exit_code":0,"raw_exit_code":0}), \
                    patch.object(launcher.profile,"metadata_receipts",return_value={"passed":True,"count":1,"host_model":True}):
                self.assertEqual(launcher.run_locked(SimpleNamespace(action="kernel"),checkout,source,root,
                    self.virtual,self.root/str(i),SimpleNamespace(signum=None),0),0)
        policies = [json.loads((self.root/str(i)/"policy.json").read_text()) for i in (0,1)]
        self.assertEqual(policies[0]["project_inputs"],policies[1]["project_inputs"])
        self.assertNotEqual(policies[0]["project_input_states"],policies[1]["project_input_states"])
        owner = json.loads((root/"owner.json").read_text())
        self.assertNotIn(str(first[0]),json.dumps(owner));self.assertNotIn(str(second[0]),json.dumps(owner))
        (second[2]/"src/lib.rs").write_text("// changed after the successful pair\n")
        with self.assertRaisesRegex(ValueError,"foreign or incompatible"):
            launcher.run_locked(SimpleNamespace(action="kernel"),second[0],second[1],root,self.virtual,
                self.root/"changed-output",SimpleNamespace(signum=None),0)
        self.assertFalse((self.root/"changed-output").exists())


class Custody(unittest.TestCase):
    def test_fifo_input_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as temp:
            fifo = Path(temp) / "fifo"
            os.mkfifo(fifo)
            script = ("import importlib.util; from pathlib import Path; "
                      f"s=importlib.util.spec_from_file_location('p',{str(HERE / 'profile.py')!r}); "
                      "p=importlib.util.module_from_spec(s); s.loader.exec_module(p); "
                      f"p.regular(Path({str(fifo)!r}))")
            result = subprocess.run([sys.executable, "-B", "-I", "-c", script],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b"private regular file", result.stderr)

    def test_both_materialized_wrappers_are_directly_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            policy = root / "policy.json"
            policy.write_text(json.dumps({"output": str(root), "real_cargo": "/bin/true",
                              "real_root": "/actual", "virtual_root": "/virtual",
                              "embedded_builder": {"username": "fixture", "hostname": "fixture"}}))
            env = dict(os.environ, A01_REPRO_POLICY=str(policy))
            profile.materialize_helpers(root / "helpers", HERE)
            for name, args in (("rustc-wrapper.py", ["/bin/true"]),
                               ("cargo-metadata-wrapper.py", ["--version"])):
                result = subprocess.run([str(root / "helpers" / name), *args], env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(set(os.listdir(root / "helpers")), set(profile.HELPERS))
            self.assertEqual(profile.helper_hashes(root),
                             {name: profile.digest(profile.regular(HERE / name)[0]) for name in profile.HELPERS})

    def test_exclusive_write_preserves_foreign_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "foreign"
            path.write_bytes(b"foreign")
            with self.assertRaises(FileExistsError):
                profile.exclusive(path, b"replacement")
            self.assertEqual(path.read_bytes(), b"foreign")

    def test_symlink_and_hardlink_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            original = root / "input"
            original.write_bytes(b"data")
            (root / "symlink").symlink_to(original)
            with self.assertRaises(OSError):
                profile.regular(root / "symlink")
            os.link(original, root / "hardlink")
            with self.assertRaisesRegex(ValueError, "private"):
                profile.regular(original)

    def test_foreign_profile_directory_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            foreign = root / "foreign"
            foreign.mkdir()
            (foreign / "keep").write_bytes(b"sentinel")
            with self.assertRaisesRegex(ValueError, "foreign"):
                profile.snapshot(foreign)
            self.assertEqual((foreign / "keep").read_bytes(), b"sentinel")

    def test_replaced_then_restored_component_entry_changes_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "virtual-asterinas").mkdir()
            profile.materialize_helpers(root / "helpers", HERE)
            for name in ("owner.json", "lock", "virtual-asterinas/Components.toml"):
                (root / name).write_bytes(b"original")
            before = profile.snapshot(root)
            entry = root / "virtual-asterinas/Components.toml"
            saved = root / "saved"
            entry.rename(saved)
            entry.write_bytes(b"foreign")
            entry.unlink()
            saved.rename(entry)
            self.assertNotEqual(profile.snapshot(root), before)

    def test_workspace_target_and_wrapper_guards_do_not_consume_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "checkout/kernel/asterinas"
            source.mkdir(parents=True)
            (source / "Components.toml").write_bytes(b"[components]\n")
            target = source / "target"
            target.mkdir()
            output = root / "output"
            result = subprocess.run([sys.executable, "-B", "-I", str(HERE / "run.py"),
                                     "--checkout", str(root / "checkout"),
                                     "--profile-root", str(root / "profile"), "--output", str(output)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"absent kernel target", result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse((root / "profile").exists())

    def test_nested_output_is_rejected_before_creating_any_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "checkout/kernel/asterinas"
            source.mkdir(parents=True)
            (source / "Components.toml").write_bytes(b"[components]\n")
            owned = root / "profile"
            result = subprocess.run([sys.executable, "-B", "-I", str(HERE / "run.py"),
                                     "--checkout", str(root / "checkout"),
                                     "--profile-root", str(owned), "--output", str(owned / "nested")],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"disjoint", result.stderr)
            self.assertFalse(owned.exists())


if __name__ == "__main__":
    unittest.main()
