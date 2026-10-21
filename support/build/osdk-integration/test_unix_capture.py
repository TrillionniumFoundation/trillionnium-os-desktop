"""Host-only UNIX endpoint, profile and evidence tests; no kernel/QEMU/GDB run."""
from contextlib import contextmanager
import copy
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


endpoint = module("unix_endpoint_host_test", "unix_endpoint.py")
runner = module("unix_runner_host_test", "run.py")
capture = module("unix_capture_host_test", "capture.py")
recorder = module("unix_recorder_host_test", "record-qemu.py")
binding = module("unix_binding_fixture", "test_coverage_binding.py")


@contextmanager
def owned_endpoint():
    with tempfile.TemporaryDirectory(prefix="a01-unix-test-") as temporary:
        listener, identity = endpoint.reserve_endpoint(temporary)
        try:
            yield listener, identity
        finally:
            listener.close()
            if Path(identity["directory"]["path"]).exists():
                endpoint.release_endpoint(identity)


@contextmanager
def unix_binding_fixture():
    with binding.capture_fixture() as item, owned_endpoint() as (_listener, identity):
        identity["qemu_pid"] = os.getpid()  # Explicit host fixture, not a QEMU claim.
        item.record.update(profile_id=runner.UNIX_CAPTURE_PROFILE, raw_exit_code=33,
                           wrapper_exit_code=33, qemu_pid=os.getpid(),
                           snapshot_verification={"before_qemu": True, "after_qemu": True})
        kernel = Path(item.record["artifacts"]["-kernel"]["path"])
        data = bytearray(64)
        data[:6] = b"\x7fELF\x02\x01"
        data[18:20] = (3).to_bytes(2, "little")
        kernel.write_bytes(data)
        kernel.chmod(0o400)
        item.record["artifacts"]["-kernel"] = recorder.file_record(kernel)
        identity_path = item.guest / "unix-gdb-endpoint.json"
        identity_path.write_text(json.dumps(identity))
        receipt = recorder.file_record(identity_path)
        item.record["unix_gdb_endpoint"] = {"identity": copy.deepcopy(identity), "record": receipt}
        item.capture.update(profile_id=runner.UNIX_CAPTURE_PROFILE, transport="unix",
                            kernel_sha256=binding.digest(data),
                            unix_endpoint_identity=copy.deepcopy(identity), unix_endpoint_record=receipt,
                            unix_endpoint_verified_before_connect=True,
                            unix_endpoint_verified_after_connect=True,
                            unix_endpoint_verified_after_detach=True)
        item.record["artifact_snapshots"] = {"coverage-symbol": copy.deepcopy(item.capture["symbol_elf"])}
        yield item


def bind_unix(item):
    binding.write_capture(item)
    item.record_path.write_text(json.dumps(item.record))
    return binding.OSDK.coverage_binding(item.case, item.raw, runner.UNIX_CAPTURE_PROFILE)


class UnixProfileTests(unittest.TestCase):
    def test_default_is_deterministic_unix_capture_and_legacy_is_explicit(self):
        self.assertEqual(runner.selected_profile(), "osdk-native-unix-gdb-capture-v3")
        self.assertEqual(runner.selected_profile(upstream_coverage_lifecycle=True), "osdk-native-unix-v1")
        self.assertEqual(runner.selected_profile(local_tcp=True), "osdk-native-local-tcp-v1")
        self.assertEqual(runner.selected_profile(local_tcp=True, coverage_gdb=True), capture.PROFILE)
        for flags in ({"coverage_gdb": True},
                      {"local_tcp": True, "upstream_coverage_lifecycle": True},
                      {"local_tcp": True, "coverage_gdb": True, "upstream_coverage_lifecycle": True}):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                runner.selected_profile(**flags)

    def test_unix_coverage_retains_original_monitor_and_never_selects_tcp(self):
        env = {"A01_REAL_OSDK": "/host/fixture-osdk", "A01_OSDK_LOCAL_TCP": "0",
               "A01_OSDK_PROFILE": runner.UNIX_CAPTURE_PROFILE}
        actual = binding.OSDK.adapt_command(["osdk", "run", "--coverage"], env, HERE)
        self.assertFalse(any("tcp" in arg or "--gdb-server" in arg for arg in actual))
        self.assertIn("--coverage", actual)

    def test_existing_debugger_is_rejected_before_allocating_a_capture_endpoint(self):
        for arguments in (["-gdb", "tcp:127.0.0.1:1234"], ["-S"],
                          ["-chardev", "socket,id=a01-unix-gdb0"]):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                recorder.reserve_unix_capture(arguments)


class PublicCoverageEnvironmentTests(unittest.TestCase):
    """Drive run_locked through a real Python harness, with all builds mocked.

    The child only records its environment. The runner must still report a
    failed native case because no guest or coverage artifact was produced.
    """

    COVERAGE = "commands::run::coverage_feature::basic_coverage"
    DEBUG = "commands::run::qemu_gdb_feature::basic_debug"
    VSC = "commands::run::qemu_gdb_feature::vsc::vsc_launch_file"
    BASIC = "commands::run::basic::new_kernel_and_run"

    def observe_child(self, case, *, local_tcp=False, coverage_gdb=False,
                      upstream_coverage_lifecycle=False, ambient_marker=None):
        with tempfile.TemporaryDirectory(prefix="a01-env-host-") as temporary:
            root = Path(temporary)
            project, output = root / "project", root / "output"
            here = project / "support/build/osdk-integration"
            here.mkdir(parents=True)
            (here / "run.py").write_bytes((HERE / "run.py").read_bytes())
            (here.parent / "record-qemu.py").write_text("# hashed host fixture only\n")
            upstream = project / "kernel/asterinas"
            for name in ("osdk/tests", "osdk/src", "ostd/libs/align_ext"):
                (upstream / name).mkdir(parents=True)
            (upstream / "Cargo.lock").write_text("# no native dependencies\n")
            output.mkdir()
            harness = output / "fixture-harness"
            harness.write_text(
                "#!" + sys.executable + "\n"
                "import json,os\nfrom pathlib import Path\n"
                "out=Path(os.environ['A01_OSDK_CASE_OUTPUT'])\n"
                "(out/'environment-child.json').write_text(json.dumps({"
                "'fixture':'host-python-environment-only','pid':os.getpid(),"
                "'profile':os.environ['A01_OSDK_PROFILE'],"
                "'marker':os.environ.get('A01_OSDK_GDB_READY'),"
                "'expected_owned_marker':str(out/'gdb-ready.json')}))\n"
                "print('test result: ok. 1 passed; 0 failed;',flush=True)\n")
            harness.chmod(0o700)
            toolbin = root / "rustup/toolchains" / (
                runner.TOOLCHAIN + "-x86_64-unknown-linux-gnu") / "bin"
            toolbin.mkdir(parents=True)
            for name in ("cargo", "rustc"):
                (toolbin / name).write_text("# hashed only, never executed\n")

            def prepare(_upstream, _output, _cargo, _env, _local, *, fixed_root):
                harness_root = output / "harness"
                (harness_root / "tests").mkdir(parents=True)
                return harness_root, fixed_root

            def seed(_project, _output):
                path = output / "upstream-root.Cargo.lock"
                path.write_text("# explicit host fixture; no Rust compilation\n")
                return path, {"sha256": runner.digest(path)}

            def checked(argv, _cwd, _env, _log):
                if argv[-1] == "-Vv" and str(argv[0]).endswith("rustc"):
                    return "commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48\n"
                if argv[-1] == "--list":
                    return "\n".join(name + ": test" for name in [case] + [
                        "fixture::unused_" + str(i) for i in range(21)])
                return "explicit host fixture\n"

            actual_command = runner.command

            def command(argv, cwd, env, log, timeout):
                if str(argv[0]) == str(harness):
                    return actual_command(argv, cwd, env, log, timeout)
                if "test" in argv:
                    log.write_text(json.dumps({"reason": "compiler-artifact",
                        "executable": str(harness), "target": {"name": "integration"}}) + "\n")
                else:
                    (output / "target/debug/cargo-osdk").write_text(
                        "# fake OSDK fixture; never executed\n")
                    log.write_text("build intentionally mocked; no native execution\n")
                return {"raw_exit_code": 0, "duration_seconds": 0, "timed_out": False}

            args = SimpleNamespace(local_tcp=local_tcp, coverage_gdb=coverage_gdb,
                upstream_coverage_lifecycle=upstream_coverage_lifecycle,
                target_dir=None, case=[case], case_timeout=10)
            environment = os.environ.copy()
            environment.update(CARGO_HOME=str(root / "cargo"), RUSTUP_HOME=str(root / "rustup"))
            environment.pop("A01_OSDK_GDB_READY", None)
            if ambient_marker is not None:
                environment["A01_OSDK_GDB_READY"] = ambient_marker
            with mock.patch.dict(os.environ, environment, clear=True), \
                    mock.patch.object(runner, "prepare_root_seed", side_effect=seed), \
                    mock.patch.object(runner, "prepare_harness", side_effect=prepare), \
                    mock.patch.object(runner, "checked_output", side_effect=checked), \
                    mock.patch.object(runner, "command", side_effect=command):
                status = runner.run_locked(args, here, project, upstream, output)
            result = json.loads((output / "result.json").read_text())
            # A Python environment fixture must never be presented as a guest pass.
            self.assertEqual(status, 1)
            self.assertEqual(result["failed"], 1)
            self.assertEqual(result["cases"][0]["raw_exit_code"], 0)
            self.assertEqual(result["cases"][0]["guests"], [])
            observed = json.loads((output / "case-01/environment-child.json").read_text())
            self.assertEqual(observed["fixture"], "host-python-environment-only")
            self.assertNotEqual(observed["pid"], os.getpid())
            return observed

    def test_default_unix_coverage_does_not_assign_a_competing_marker(self):
        observed = self.observe_child(self.COVERAGE)
        self.assertEqual(observed["profile"], runner.UNIX_CAPTURE_PROFILE)
        self.assertIsNone(observed["marker"])

    def test_default_unix_coverage_removes_an_ambient_competing_marker(self):
        observed = self.observe_child(self.COVERAGE, ambient_marker="/tmp/foreign-ready.json")
        self.assertEqual(observed["profile"], runner.UNIX_CAPTURE_PROFILE)
        self.assertIsNone(observed["marker"])

    def test_other_case_and_profile_marker_semantics_are_unchanged(self):
        configurations = [
            (self.DEBUG, {}), (self.VSC, {}), (self.BASIC, {}),
            (self.COVERAGE, {"upstream_coverage_lifecycle": True}),
            (self.COVERAGE, {"local_tcp": True}),
            (self.COVERAGE, {"local_tcp": True, "coverage_gdb": True}),
            (self.DEBUG, {"local_tcp": True}),
            (self.VSC, {"local_tcp": True, "coverage_gdb": True}),
        ]
        for case, options in configurations:
            with self.subTest(case=case, options=options):
                observed = self.observe_child(case, ambient_marker="/tmp/foreign-ready.json", **options)
                self.assertEqual(observed["marker"], observed["expected_owned_marker"])
                self.assertNotEqual(observed["marker"], "/tmp/foreign-ready.json")
                self.assertEqual(observed["profile"], runner.selected_profile(**options))

    def test_recorder_still_rejects_a_competing_marker_before_endpoint_or_spawn(self):
        with tempfile.TemporaryDirectory(prefix="a01-env-guard-") as temporary:
            case = Path(temporary)
            arguments = ["-bios", str(case / "never-read-bios")]
            environment = {"A01_OSDK_CASE_OUTPUT": str(case), "A01_OSDK_LOCAL_TCP": "0",
                "A01_OSDK_PROFILE": runner.UNIX_CAPTURE_PROFILE, "A01_OSDK_COVERAGE_GDB": "1",
                "A01_OSDK_GDB_READY": str(case / "competing-marker.json")}
            with mock.patch.dict(os.environ, environment), mock.patch.object(sys, "argv", ["recorder"]), \
                    mock.patch.object(recorder, "transform_args", return_value=(arguments, [], [])), \
                    mock.patch.object(recorder, "select_private_inputs", side_effect=lambda value, _record: value), \
                    mock.patch.object(recorder, "reserve_unix_capture") as reserve, \
                    mock.patch.object(recorder.subprocess, "Popen") as popen, \
                    mock.patch.object(recorder.subprocess, "check_output") as version:
                self.assertEqual(recorder.main(), 125)
            reserve.assert_not_called()
            popen.assert_not_called()
            version.assert_not_called()
            receipt = json.loads((case / "guests/guest-001/qemu.json").read_text())
            self.assertIsNone(receipt["raw_exit_code"])
            self.assertEqual(receipt["error"],
                "ValueError: coverage-owned UNIX GDB cannot reuse another debugger's readiness marker")


class UnixEndpointTests(unittest.TestCase):
    def test_prebound_listener_is_private_exclusive_and_has_separate_identities(self):
        with owned_endpoint() as (listener, identity):
            self.assertTrue(endpoint.verify_endpoint(identity, listener))
            self.assertEqual(identity["directory"]["identity"]["mode"] & 0o777, 0o700)
            self.assertEqual(listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN), 1)
            self.assertEqual(identity["listener_fd"]["inode"], os.fstat(listener.fileno()).st_ino)
            self.assertEqual(identity["socket"]["inode"], Path(identity["path"]).lstat().st_ino)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as other:
                with self.assertRaises(OSError):
                    other.bind(identity["path"])

    def test_real_host_child_inherits_listener_after_parent_closes_it(self):
        # This proves FD handoff using a Python echo fixture, not a VM or GDB.
        with owned_endpoint() as (listener, identity):
            descriptor = listener.fileno()
            source = (
                "import json,os,socket,sys; s=socket.socket(fileno=int(sys.argv[1])); "
                "s.settimeout(3); c,_=s.accept(); "
                "c.sendall(json.dumps({'fixture':'host-python-echo','pid':os.getpid(),"
                "'listener_inode':os.fstat(s.fileno()).st_ino}).encode()); c.close(); s.close()"
            )
            child = subprocess.Popen([sys.executable, "-I", "-c", source, str(descriptor)],
                                     pass_fds=(descriptor,), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                listener.close()
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.settimeout(3)
                    client.connect(identity["path"])
                    observed = json.loads(client.recv(4096))
                    credentials = struct.unpack("3i", client.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                stdout, stderr = child.communicate(timeout=3)
                self.assertEqual(child.returncode, 0, (stdout, stderr))
                self.assertEqual(observed["pid"], child.pid)
                self.assertEqual(observed["fixture"], "host-python-echo")
                self.assertEqual(observed["listener_inode"], identity["listener_fd"]["inode"])
                self.assertEqual(credentials[0], os.getpid())
                self.assertNotEqual(credentials[0], child.pid)
                self.assertTrue(endpoint.verify_endpoint(identity))
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=2)
                child.stdout.close()
                child.stderr.close()

    def test_changed_socket_path_is_rejected_and_cleanup_preserves_replacement(self):
        with owned_endpoint() as (listener, identity):
            path = Path(identity["path"])
            path.unlink()
            path.write_text("replacement owned by a separate fixture")
            with self.assertRaises(ValueError):
                endpoint.verify_endpoint(identity, listener)
            with self.assertRaises(ValueError):
                endpoint.release_endpoint(identity)
            self.assertEqual(path.read_text(), "replacement owned by a separate fixture")
            path.unlink()  # Fixture owner removes its own replacement.

    def test_changed_private_directory_permissions_are_rejected(self):
        with owned_endpoint() as (_listener, identity):
            parent = Path(identity["directory"]["path"])
            parent.chmod(0o755)
            try:
                with self.assertRaises(ValueError):
                    endpoint.verify_endpoint(identity)
            finally:
                parent.chmod(0o700)

    def test_long_path_fails_before_child_spawn_without_leaving_owned_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / ("x" * 110)
            parent.mkdir()
            with self.assertRaises(ValueError):
                endpoint.reserve_endpoint(parent)
            self.assertEqual(list(parent.iterdir()), [])


class UnixEvidenceTests(unittest.TestCase):
    def test_complete_bound_fixture_is_accepted(self):
        with unix_binding_fixture() as item:
            self.assertTrue(bind_unix(item)["passed"])

    def test_socket_pid_receipt_or_connection_observation_mismatch_is_rejected(self):
        for mutation in ("pid", "receipt", "before", "after", "detach", "transport"):
            with self.subTest(mutation=mutation), unix_binding_fixture() as item:
                if mutation == "pid":
                    item.capture["unix_endpoint_identity"]["qemu_pid"] += 1
                elif mutation == "receipt":
                    item.capture["unix_endpoint_record"] = dict(item.capture["unix_endpoint_record"], sha256="0" * 64)
                elif mutation == "transport":
                    item.capture["transport"] = "tcp"
                else:
                    field = {"before": "before_connect", "after": "after_connect", "detach": "after_detach"}[mutation]
                    item.capture["unix_endpoint_verified_" + field] = False
                self.assertFalse(bind_unix(item)["passed"])

    def test_changed_loaded_elf_symbol_binding_or_real_exit_is_rejected(self):
        for mutation in ("kernel", "symbol", "raw_exit", "wrapper_exit", "argv", "snapshots"):
            with self.subTest(mutation=mutation), unix_binding_fixture() as item:
                if mutation == "kernel":
                    path = Path(item.record["artifacts"]["-kernel"]["path"])
                    path.chmod(0o600)
                    path.write_bytes(path.read_bytes() + b"changed")
                    path.chmod(0o400)
                elif mutation == "symbol":
                    item.record["artifact_snapshots"]["coverage-symbol"]["sha256"] = "0" * 64
                elif mutation == "raw_exit":
                    item.record["raw_exit_code"] = 65
                elif mutation == "wrapper_exit":
                    item.record["wrapper_exit_code"] = 0
                elif mutation == "argv":
                    item.record["argv"][-1] = "/different/kernel.elf"
                else:
                    item.record["snapshot_verification"]["after_qemu"] = False
                self.assertFalse(bind_unix(item)["passed"])

    def test_existing_pc_serial_raw_and_panic_gates_apply_to_unix_profile(self):
        for mutation in ("pc", "serial", "raw", "panic"):
            with self.subTest(mutation=mutation), unix_binding_fixture() as item:
                if mutation == "pc":
                    item.capture["breakpoint"]["actual_pc"] = "0x8001"
                elif mutation == "raw":
                    item.raw.write_bytes(b"wrong")
                else:
                    data = item.serial.read_bytes() + (b"panicked at fixture.rs:1\n" if mutation == "panic" else b"changed\n")
                    item.serial.write_bytes(data)
                    if mutation == "panic":
                        item.record["serial_logs"][0].update(size=len(data), sha256=binding.digest(data))
                        item.capture["serial_sha256"] = binding.digest(data)
                        item.capture["serial_prefix"] = {"size": len(data), "sha256": binding.digest(data)}
                self.assertFalse(bind_unix(item)["passed"])

    def test_unix_gdb_script_checks_endpoint_around_the_actual_connection(self):
        with owned_endpoint() as (_listener, identity):
            _helper, receipt = capture.load_unix_helpers()
            settings = {"endpoint": identity["path"], "transport": "unix", "symbol": capture.SYMBOL,
                        "address": "0xffffffff88001000", "serial": "/owned/serial.log",
                        "raw": "/owned/fresh.profraw", "observations": "/owned/observations.json",
                        "prefix": "/owned/prefix.log", "unix_endpoint_identity": identity, "unix_helper": receipt}
            script = capture.gdb_script(settings)
            python = script.split("python\n", 1)[1].rsplit("\nend\n", 1)[0]
            compile(python, "host-only-generated-unix-capture.gdb", "exec")
            for phase in ("before_connect", "after_connect", "after_detach"):
                self.assertIn("unix_endpoint_verified_" + phase, script)
            self.assertIn('gdb.execute("target remote " + settings["endpoint"])', script)
            self.assertIn("gdb.BP_HARDWARE_BREAKPOINT", script)


if __name__ == "__main__":
    unittest.main()
