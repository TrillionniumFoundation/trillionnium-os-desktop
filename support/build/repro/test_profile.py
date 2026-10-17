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
