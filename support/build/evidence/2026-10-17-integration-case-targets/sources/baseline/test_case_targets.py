"""Exercise per-case workspace custody; fixture children do not build or boot."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("a01_case_target_runner", HERE / "run.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)

FIRST = "examples_in_book::test_and_run_projects::create_and_run_kernel"
SECOND = "examples_in_book::work_in_workspace::work_in_workspace"
CHILD = r'''
import json,os,sys
from pathlib import Path
case=sys.argv[2]
root=Path(os.environ["A01_FIXTURE_FIXED_ROOT"])
project=root/("myos" if case.endswith("create_and_run_kernel") else "myworkspace/myos")
project.mkdir(parents=True)
(project/"Cargo.toml").write_text("[package]\nname='myos'\nversion='0.1.0'\n")
target=Path(os.environ["CARGO_TARGET_DIR"])
base=target/"osdk/myos-run-base"
base.mkdir(parents=True,exist_ok=True)
manifest=base/"Cargo.toml"
# Explicit fault fixture: retain a stale same-name manifest if output is shared.
# This is not a claim that pinned OSDK normally ignores changed dependencies.
if not manifest.exists():
    manifest.write_text(str(project))
bound=Path(manifest.read_text())
out=Path(os.environ["A01_OSDK_CASE_OUTPUT"])
(out/"child-target.json").write_text(json.dumps({"target":str(target),"project":str(project),"bound":str(bound),"bound_source_exists":(bound/"Cargo.toml").is_file()}))
if bound!=project or not (bound/"Cargo.toml").is_file():
    print("STALE_SAME_NAME_WORKSPACE",str(bound),flush=True)
    raise SystemExit(1)
print("test result: ok. 1 passed; 0 failed;",flush=True)
'''

class PublicRunnerTargetsTests(unittest.TestCase):
    def test_same_name_cases_keep_private_generated_workspaces_and_shared_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="a01 case targets ") as temporary:
            root = Path(temporary)
            project, output = root / "project", root / "output"
            here = project / "support/build/osdk-integration"
            here.mkdir(parents=True)
            (here / "run.py").write_bytes((HERE / "run.py").read_bytes())
            (here.parent / "record-qemu.py").write_text("# dependency fixture\n")
            upstream = project / "kernel/asterinas"
            (upstream / "osdk/tests").mkdir(parents=True)
            (upstream / "osdk/src").mkdir()
            (upstream / "ostd/libs/align_ext").mkdir(parents=True)
            (upstream / "Cargo.lock").write_text("# fixture lock\n")
            output.mkdir()
            target = output / "target"
            (target / "debug").mkdir(parents=True)
            (target / "debug/cache-marker").write_text("retained compilation bytes\n")
            (target / "debug/cargo-osdk").write_text("# fake OSDK, never executed\n")
            harness = output / "fixture-harness"
            harness.write_text("#!" + sys.executable + "\n" + CHILD)
            harness.chmod(0o700)
            fixed = output / "fixed"
            toolbin = root / "rustup/toolchains" / (RUNNER.TOOLCHAIN + "-x86_64-unknown-linux-gnu") / "bin"
            toolbin.mkdir(parents=True)
            for name in ("cargo", "rustc"):
                (toolbin / name).write_text("# only hashed; not executed\n")
            def prepare(_upstream, _output, _cargo, _env, _local):
                fixed.mkdir()
                identity = fixed.stat()
                (output / "fixed-root.json").write_text(json.dumps(
                    {"path": str(fixed), "device": identity.st_dev, "inode": identity.st_ino}))
                h = output / "harness"
                (h / "tests").mkdir(parents=True)
                return h, fixed
            def checked(argv, _cwd, _env, log):
                if argv[-1] == "-Vv" and str(argv[0]).endswith("rustc"):
                    return "commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48\n"
                if argv[-1] == "--list":
                    return "\n".join(x + ": test" for x in [FIRST, SECOND] + [
                        "fixture::unused_" + str(i) for i in range(20)])
                return "fixture\n"
            actual_command = RUNNER.command
            def command(argv, cwd, env, log, timeout):
                if str(argv[0]) == str(harness):
                    return actual_command(argv, cwd, env, log, timeout)
                if "test" in argv:
                    log.write_text(json.dumps({"reason": "compiler-artifact", "executable": str(harness),
                                               "target": {"name": "integration"}}) + "\n")
                else:
                    log.write_text("build intentionally mocked\n")
                return {"raw_exit_code": 0, "duration_seconds": 0, "timed_out": False}
            args = SimpleNamespace(coverage_gdb=False, local_tcp=False, target_dir=None,
                                   case=[FIRST, SECOND], case_timeout=10)
            with mock.patch.dict(os.environ, {"CARGO_HOME": str(root / "cargo"),
                                             "RUSTUP_HOME": str(root / "rustup"),
                                             "A01_FIXTURE_FIXED_ROOT": str(fixed)}), \
                    mock.patch.object(RUNNER, "prepare_harness", side_effect=prepare), \
                    mock.patch.object(RUNNER, "checked_output", side_effect=checked), \
                    mock.patch.object(RUNNER, "command", side_effect=command), \
                    mock.patch.dict(RUNNER.VM_CASES, {FIRST: 0, SECOND: 0}):
                RUNNER.run_locked(args, here, project, upstream, output)
            result = json.loads((output / "result.json").read_text())
            self.assertEqual(result["passed"], 2, result)
            child = [json.loads((output / f"case-{i:02d}/child-target.json").read_text())
                     for i in (1, 2)]
            self.assertNotEqual(child[0]["target"], child[1]["target"])
            self.assertTrue(all(x["bound"] == x["project"] and x["bound_source_exists"] for x in child))
            for item in child:
                case_target = Path(item["target"])
                self.assertFalse((case_target / "osdk").is_symlink())
                self.assertTrue((case_target / "osdk/myos-run-base/Cargo.toml").is_file())
                for name in ("debug", "release", "x86_64-unknown-none"):
                    self.assertTrue((case_target / name).is_symlink())
                    self.assertEqual((case_target / name).resolve(), target / name)
            self.assertEqual((target / "debug/cache-marker").read_text(), "retained compilation bytes\n")
            self.assertFalse((target / "osdk").exists())

class CaseTargetCustodyTests(unittest.TestCase):
    def fixture(self, root):
        cache, case = root / "cache", root / "case"
        cache.mkdir()
        case.mkdir()
        return cache, case

    def test_existing_target_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache, case = self.fixture(Path(tmp))
            (case / "target").mkdir()
            keep = case / "target/keep"
            keep.write_text("foreign\n")
            with self.assertRaises(FileExistsError):
                RUNNER.create_case_target(cache, case)
            self.assertEqual(keep.read_text(), "foreign\n")

    def test_symlink_cache_root_is_rejected_without_touching_foreign(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, case = self.fixture(root)
            alias = root / "alias"
            alias.symlink_to(cache, target_is_directory=True)
            with self.assertRaises(OSError):
                RUNNER.create_case_target(alias, case)
            self.assertEqual(list(cache.iterdir()), [])

    def test_symlink_case_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, case = self.fixture(root)
            alias = root / "alias"
            alias.symlink_to(case, target_is_directory=True)
            with self.assertRaises(OSError):
                RUNNER.create_case_target(cache, alias)
            self.assertEqual(list(case.iterdir()), [])

    def test_foreign_artifact_symlink_and_file_are_preserved(self):
        for kind in ("symlink", "file"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                cache, case = self.fixture(root)
                foreign = root / "foreign"
                foreign.mkdir()
                keep = foreign / "keep"
                keep.write_text("foreign\n")
                if kind == "symlink":
                    (cache / "debug").symlink_to(foreign, target_is_directory=True)
                else:
                    (cache / "debug").write_text("foreign file\n")
                with self.assertRaises(OSError):
                    RUNNER.create_case_target(cache, case)
                self.assertEqual(keep.read_text(), "foreign\n")
                self.assertTrue((cache / "debug").is_symlink() if kind == "symlink" else
                                (cache / "debug").is_file())

    def test_only_three_known_artifact_directories_are_shared_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache, case = self.fixture(root)
            (cache / "osdk").mkdir()
            (cache / "osdk/stale").write_text("preserve\n")
            (cache / "unknown").mkdir()
            target, record = RUNNER.create_case_target(cache, case)
            self.assertEqual(target, case / "target")
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
            self.assertFalse((target / "osdk").is_symlink())
            self.assertEqual(set(x.name for x in target.iterdir()),
                             {"osdk", "debug", "release", "x86_64-unknown-none"})
            self.assertEqual((cache / "osdk/stale").read_text(), "preserve\n")
            self.assertEqual(set(record["shared_artifacts"]), {"debug", "release", "x86_64-unknown-none"})
            for name, item in record["shared_artifacts"].items():
                self.assertEqual(item["inode"], (cache / name).stat().st_ino)
                self.assertEqual(item["device"], (cache / name).stat().st_dev)
            self.assertEqual(record["target"]["inode"], target.stat().st_ino)

if __name__ == "__main__":
    unittest.main()

