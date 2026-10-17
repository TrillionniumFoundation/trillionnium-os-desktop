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


class Custody(unittest.TestCase):
    def test_fifo_input_is_rejected_without_blocking(self):
        with tempfile.TemporaryDirectory() as temp:
            fifo = Path(temp) / "fifo"
            os.mkfifo(fifo)
            script = ("import importlib.util; from pathlib import Path; "
                      f"s=importlib.util.spec_from_file_location('p',{str(HERE / 'profile.py')!r}); "
                      "p=importlib.util.module_from_spec(s); s.loader.exec_module(p); "
                      f"p.regular(Path({str(fifo)!r}))")
            result = subprocess.run([sys.executable, "-I", "-c", script],
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
            result = subprocess.run([sys.executable, "-I", str(HERE / "run.py"),
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
            result = subprocess.run([sys.executable, "-I", str(HERE / "run.py"),
                                     "--checkout", str(root / "checkout"),
                                     "--profile-root", str(owned), "--output", str(owned / "nested")],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2)
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"disjoint", result.stderr)
            self.assertFalse(owned.exists())


if __name__ == "__main__":
    unittest.main()
