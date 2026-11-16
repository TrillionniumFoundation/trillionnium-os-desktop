#!/usr/bin/env python3
"""Offline qualification-verifier regressions; never run systemd or a syscall control.

The real driver AST is loaded with only its final main() call removed. Source
custody checks use real root-owned files; unit output and protected-host snapshots
are explicitly fixtures. Run as root under both python3 and python3 -O.
"""
import ast
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
GOOD_OUTPUT = b"1 passed; 0 failed; 0 ignored\nmapped supplementary groups set/read/cleared\n"
ORIGINAL_REPRODUCED = []


def load_driver(original=False, optimize=None):
    name = "run_private_userns_controls.original.py" if original else "run_private_userns_controls.py"
    tree = ast.parse((HERE / name).read_bytes(), filename=name)
    last = tree.body.pop()
    if not (isinstance(last, ast.Expr) and isinstance(last.value, ast.Call)
            and isinstance(last.value.func, ast.Name) and last.value.func.id == "main"
            and not last.value.args and not last.value.keywords):
        raise RuntimeError("expected exact final main() call")
    namespace = {"__name__": "offline_private_control_driver"}
    exec(compile(tree, name, "exec", optimize=sys.flags.optimize if optimize is None else optimize), namespace)
    return namespace


class Fixture:
    def __init__(self, original=False, optimize=None):
        self.temp = tempfile.TemporaryDirectory(prefix="p4-driver-fixture-")
        self.base = Path(self.temp.name)
        self.root = self.base / "source"
        self.root.mkdir(mode=0o700)
        self.out = self.base / "out"
        self.cgroup = self.base / "fixture-cgroup"
        self.cgroup.mkdir(mode=0o700)
        self.member = self.root / "member.rs"
        self.member.write_bytes(b"reviewed fixture source\n")
        self.member.chmod(0o600)
        self.binary = self.root / "never-executed-test-binary"
        self.binary.write_bytes(b"offline fixture; not an executable\n")
        self.binary.chmod(0o600)
        self.ns = load_driver(original, optimize)
        self.manifest = {"schema": "pocket4-owned-userns-source-custody-v1",
                         "members": [self.ref(self.member), self.ref(self.binary)],
                         "test_binary": self.ref(self.binary)}
        self.save_manifest()
        self.fields = {"ActiveState": "inactive", "SubState": "dead", "MainPID": "0",
                       "Result": "success", "ExecMainCode": "1", "ExecMainStatus": "0",
                       "ControlGroup": "/fixture-unit", "InvocationID": "1234567890abcdef" * 2}
        self.control_rc = 0
        self.control_stdout = GOOD_OUTPUT
        self.show_rc = 0
        self.show_stderr = b""
        self.show_raw = None
        self.calls = []
        self.snapshot_count = 0
        self.snapshot = {"public_authority": [{"path": "fixture-authority", "sha256": "a"}],
                         "data_metadata_only": [{"identity": [1, 2, 3]}],
                         "boot_id": "fixture-boot", "host_kernel": "fixture-kernel",
                         "parent_ns": [{"kind": "user", "ino": 1}]}
        self.change_authority = False
        self.change_metadata = False
        self.change_member_after = False
        self.ns.update(ROOT=self.root, OUT=self.out,
                       sys=types.SimpleNamespace(argv=["offline-fixture", "--run"]),
                       subprocess=types.SimpleNamespace(run=self.run), protected=self.protected,
                       Path=self.path)
        self.printed = ""

    @staticmethod
    def ref(path):
        raw = path.read_bytes()
        return {"path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    def save_manifest(self):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))

    def path(self, *args):
        p = Path(*args)
        return self.cgroup if str(p) == "/sys/fs/cgroup" else p

    def run(self, argv, **kwargs):
        # This stub has no route to real subprocess.run, even for malformed argv.
        self.calls.append(list(argv))
        if argv[0] == "/usr/bin/systemd-run" and len(self.calls) == 1:
            if str(self.binary) not in argv:
                raise RuntimeError("fixture binary binding lost")
            return types.SimpleNamespace(returncode=self.control_rc, stdout=self.control_stdout, stderr=b"")
        if argv[0] == "/usr/bin/systemctl" and len(self.calls) == 2:
            raw = self.show_raw
            if raw is None:
                raw = "".join(k + "=" + v + "\n" for k, v in self.fields.items()).encode()
            return types.SimpleNamespace(returncode=self.show_rc, stdout=raw, stderr=self.show_stderr)
        raise RuntimeError("unexpected attempted fixture command")

    def protected(self):
        self.snapshot_count += 1
        value = copy.deepcopy(self.snapshot)
        if self.snapshot_count == 2:
            if self.change_authority:
                value["public_authority"][0]["sha256"] = "changed"
            if self.change_metadata:
                value["data_metadata_only"][0]["identity"] = [4, 5, 6]
            if self.change_member_after:
                self.member.write_bytes(b"changed after fixture execution\n")
        return value

    def invoke(self):
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                self.ns["main"]()
        finally:
            self.printed = out.getvalue()

    def result(self):
        return json.loads((self.out / "result.json").read_text())

    def close(self):
        self.temp.cleanup()


class GuardTests(unittest.TestCase):
    def setUp(self):
        if os.geteuid() != 0:
            self.fail("root required to verify actual root-owned source custody")
        self.f = Fixture()
        self.addCleanup(self.f.close)

    def rejects(self, after_run=False):
        with self.assertRaises((RuntimeError, OSError, ValueError, KeyError)):
            self.f.invoke()
        self.assertNotIn('"actual_private_control_passed": true', self.f.printed)
        if after_run:
            self.assertEqual(len(self.f.calls), 2)
            self.assertTrue((self.f.out / "result.json").is_file())
            self.assertFalse(self.f.result()["production_admission"])
        else:
            self.assertEqual(self.f.calls, [])

    def test_positive_fixture_has_no_production_admission(self):
        self.f.invoke()
        output = json.loads(self.f.printed)
        self.assertTrue(output["actual_private_control_passed"])
        self.assertFalse(output["production_admission"])
        self.assertEqual(len(self.f.calls), 2)
        self.assertFalse(self.f.result()["host_accounts_or_grants_changed"])

    def test_wrong_cli_refuses_before_any_command(self):
        self.f.ns["sys"].argv = ["fixture", "--unexpected"]
        self.rejects()

    def test_wrong_effective_uid_refuses_before_any_command(self):
        self.f.ns["os"] = types.SimpleNamespace(geteuid=lambda: 1000)
        self.rejects()

    def test_wrong_manifest_schema_refuses(self):
        self.f.manifest["schema"] = "untrusted"
        self.f.save_manifest()
        self.rejects()

    def test_existing_output_refuses(self):
        self.f.out.mkdir()
        self.rejects()

    def test_wrong_hash_refuses(self):
        self.f.manifest["members"][0]["sha256"] = "0" * 64
        self.f.save_manifest()
        self.rejects()

    def test_wrong_length_refuses(self):
        self.f.manifest["members"][0]["bytes"] += 1
        self.f.save_manifest()
        self.rejects()

    def test_group_writable_member_refuses(self):
        self.f.member.chmod(0o620)
        self.rejects()

    def test_nonroot_stat_fixture_refuses(self):
        # Cloud's one-ID namespace cannot chown to 1000. This single stat field
        # is explicitly synthetic; mode/link/FIFO/path checks use real files.
        real_fstat = os.fstat
        def fstat(fd):
            value = real_fstat(fd)
            return types.SimpleNamespace(st_mode=value.st_mode, st_uid=1000,
                                         st_nlink=value.st_nlink)
        proxy = {name: getattr(os, name) for name in dir(os)}
        proxy["fstat"] = fstat
        self.f.ns["os"] = types.SimpleNamespace(**proxy)
        self.rejects()

    def test_hardlink_member_refuses(self):
        os.link(self.f.member, self.f.root / "alias")
        self.rejects()

    def test_symlink_member_refuses(self):
        moved = self.f.root / "moved"
        self.f.member.rename(moved)
        self.f.member.symlink_to(moved)
        self.rejects()

    def test_fifo_member_refuses_without_blocking(self):
        self.f.member.unlink()
        os.mkfifo(self.f.member, 0o600)
        self.rejects()

    def test_read_limit_refuses(self):
        with self.assertRaises(RuntimeError):
            self.f.ns["exact"](self.f.ref(self.f.member), limit=1)
        self.assertEqual(self.f.calls, [])

    def test_path_replacement_during_read_refuses(self):
        original_read = os.read
        done = []
        def read(fd, count):
            raw = original_read(fd, count)
            if not done:
                replacement = self.f.root / "replacement"
                replacement.write_bytes(self.f.member.read_bytes())
                replacement.chmod(0o600)
                replacement.replace(self.f.member)
                done.append(True)
            return raw
        proxy = {name: getattr(os, name) for name in dir(os)}
        proxy["read"] = read
        self.f.ns["os"] = types.SimpleNamespace(**proxy)
        self.rejects()

    def test_control_failure_is_preserved_and_refused(self):
        self.f.control_rc = 17
        self.rejects(True)
        self.assertEqual(self.f.result()["returncode"], 17)

    def test_missing_test_count_refuses(self):
        self.f.control_stdout = b"mapped supplementary groups set/read/cleared\n"
        self.rejects(True)

    def test_missing_supplementary_control_refuses(self):
        self.f.control_stdout = b"1 passed; 0 failed; 0 ignored\n"
        self.rejects(True)

    def test_unit_readback_failure_refuses(self):
        self.f.show_rc = 1
        self.rejects(True)

    def test_unit_readback_stderr_refuses(self):
        self.f.show_stderr = b"readback warning\n"
        self.rejects(True)

    def test_missing_unit_property_refuses(self):
        del self.f.fields["ControlGroup"]
        self.rejects(True)

    def test_duplicate_unit_property_refuses(self):
        self.f.show_raw = ("".join(k + "=" + v + "\n" for k, v in self.f.fields.items()) + "MainPID=0\n").encode()
        self.rejects(True)

    def test_invalid_utf8_unit_readback_is_preserved(self):
        self.f.show_raw = b"\xff\n"
        self.rejects(True)
        self.assertTrue(self.f.result()["unit_field_errors"])

    def test_active_unit_refuses(self):
        self.f.fields["ActiveState"] = "active"
        self.rejects(True)

    def test_nonzero_main_pid_refuses(self):
        self.f.fields["MainPID"] = "1234"
        self.rejects(True)

    def test_failed_execution_refuses(self):
        self.f.fields["ExecMainStatus"] = "1"
        self.rejects(True)

    def test_non_dead_substate_refuses(self):
        self.f.fields["SubState"] = "running"
        self.rejects(True)

    def test_missing_invocation_identity_refuses(self):
        self.f.fields["InvocationID"] = "0" * 32
        self.rejects(True)

    def test_noncanonical_cgroup_refuses(self):
        self.f.fields["ControlGroup"] = "/fixture/../outside"
        self.rejects(True)

    def test_live_cgroup_refuses(self):
        (self.f.cgroup / "fixture-unit").mkdir()
        self.rejects(True)

    def test_authority_change_is_recorded_truthfully_and_refused(self):
        self.f.change_authority = True
        self.rejects(True)
        self.assertTrue(self.f.result()["host_accounts_or_grants_changed"])
        self.assertFalse(self.f.result()["protected_host_metadata_unchanged"])

    def test_protected_data_metadata_change_refuses(self):
        self.f.change_metadata = True
        self.rejects(True)
        self.assertFalse(self.f.result()["host_accounts_or_grants_changed"])
        self.assertFalse(self.f.result()["protected_host_metadata_unchanged"])

    def test_source_change_after_execution_refuses(self):
        self.f.change_member_after = True
        self.rejects(True)

    def test_original_optimized_driver_reproduces_five_false_qualifications(self):
        cases = ["wrong_cli", "wrong_hash", "failed_control", "live_cgroup", "changed_authority"]
        reproduced = []
        for case in cases:
            with self.subTest(case=case):
                f = Fixture(original=True, optimize=1)
                try:
                    if case == "wrong_cli":
                        f.ns["sys"].argv = ["fixture", "--unexpected"]
                    elif case == "wrong_hash":
                        f.manifest["members"][0]["sha256"] = "0" * 64
                        f.save_manifest()
                    elif case == "failed_control":
                        f.control_rc = 17
                    elif case == "live_cgroup":
                        (f.cgroup / "fixture-unit").mkdir()
                    elif case == "changed_authority":
                        f.change_authority = True
                    f.invoke()
                    self.assertTrue(json.loads(f.printed)["actual_private_control_passed"])
                    reproduced.append(case)
                    ORIGINAL_REPRODUCED.append(case)
                finally:
                    f.close()
        self.assertEqual(reproduced, cases)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    print(json.dumps({"fixture_only": True, "privileged_control_executed": False,
                      "production_admission": False, "android_actions": 0,
                      "optimization": sys.flags.optimize, "tests_run": result.testsRun,
                      "failures": len(result.failures), "errors": len(result.errors),
                      "nonroot_stat_is_synthetic": True,
                      "original_optimized_false_qualification_fixtures": len(ORIGINAL_REPRODUCED)}, sort_keys=True))
    sys.exit(0 if result.wasSuccessful() else 1)
