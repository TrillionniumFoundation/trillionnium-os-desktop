"""Exercise real cache paths, receipt bytes, process locks and Cargo freshness."""
import copy
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import build_text_product as product

cache = product.target_cache


class TargetCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="trill-target-cache-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.output = self.root / "new-evidence"
        self.target = self.root / "old-evidence/target"
        self.target.mkdir(parents=True)
        self.sentinel = self.target / "unrelated-dependency-artifact"
        self.sentinel.write_bytes(b"original dependency bytes")
        self.prior_path = self.root / "old-evidence/build-receipt.json"
        self.prior = self.receipt(self.prior_path)

    def receipt(self, path, previous=None):
        receipt = copy.deepcopy(previous) if previous else {
            "schema": "trill.linux-text-build-receipt.v1", "status": "failed", "exit_code": 1,
            "source_commit": "a" * 40, "source_tree": "b" * 40,
            "hepta": {"commit": "c" * 40, "tree": "d" * 40},
            "profile": {"toolchain": "1.96.0"}, "profile_sha256": "e" * 64, "cargo_profile": "release",
            "locks": {name: "f" * 64 for name in ("ui/Cargo.lock", "services/hepta-session-host/Cargo.lock",
                "services/hepta-os/Cargo.lock", "support/ui/Cargo.lock", "tests/ui/Cargo.lock")},
            "toolchain_executables": {name: {"path": "/compiler/" + name, "sha256": "1" * 64}
                                     for name in ("cargo", "rustc", "rustdoc")},
            "source_caches": {}, "native_input_paths": {},
            "environment": {key: "" for key in cache.ENVIRONMENT_KEYS}, "commands": [],
        }
        receipt["environment"].update(CARGO_TARGET_DIR=str(self.target), CARGO_PROFILE_DEV_INCREMENTAL="false")
        path.parent.mkdir(exist_ok=True)
        logs = path.parent / "logs"
        logs.mkdir(exist_ok=True)
        receipt["commands"] = []
        for name in ("compiler", "cargo", "native-metadata", "native-ui-tests"):
            command = {"name": name, "exit_code": 101 if name == "native-ui-tests" else 0}
            command["command"] = {
                "compiler": ["/compiler/rustc", "--version", "--verbose"],
                "cargo": ["/compiler/cargo", "--version"],
                "native-metadata": ["/compiler/cargo", "metadata", "--manifest-path", "ui/Cargo.toml"],
                "native-ui-tests": ["/compiler/cargo", "test", "--manifest-path", "ui/Cargo.toml"],
            }[name]
            for stream in ("stdout", "stderr"):
                log = logs / (name + "." + stream)
                log.write_bytes(("unit-test receipt fixture: " + name + stream).encode())
                command[stream] = log.name
                command[stream + "_sha256"] = cache.sha256(log)
            receipt["commands"].append(command)
        path.write_bytes(cache.canonical(receipt))
        return receipt

    def acquire(self, target=None, prior=None, source=None, output=None):
        lease = cache.TargetCache(target or self.target, prior or self.prior_path,
                                  [source or self.source], output or self.output)
        self.addCleanup(lease.close)
        return lease

    def current(self):
        current = copy.deepcopy(self.prior)
        current.update(source_commit="2" * 40, source_tree="3" * 40, execution_uid=os.geteuid())
        current["environment"]["CARGO_INCREMENTAL"] = "0"
        return current

    def test_failed_origin_is_read_only_and_new_identity_is_separate(self):
        old = self.prior_path.read_bytes()
        lease = self.acquire()
        record = lease.validate(self.current(), [])
        self.assertFalse(record["cold_build"])
        self.assertFalse(record["prior_pass_reused"])
        self.assertEqual(record["prior_receipt"]["source_commit"], "a" * 40)
        current_path = self.output / "build-receipt.json"
        self.receipt(current_path, self.current())
        lease.begin(current_path)
        lease.finish()
        lease.close()
        self.assertEqual(self.prior_path.read_bytes(), old)
        self.assertEqual(self.sentinel.read_bytes(), b"original dependency bytes")
        with self.assertRaisesRegex(ValueError, "latest completed"):
            self.acquire()
        self.acquire(prior=current_path)

    def test_actual_second_process_cannot_acquire_or_replace_the_lease(self):
        lease = self.acquire()
        script = (
            "import fcntl, os, sys\n"
            "fd = os.open(sys.argv[1], os.O_RDWR)\n"
            "try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "except BlockingIOError: sys.exit(23)\n"
            "sys.exit(0)\n"
        )
        command = [sys.executable, "-B", "-c", script, str(lease.lock_path)]
        self.assertEqual(subprocess.run(command, check=False).returncode, 23)
        lease.close()
        self.assertEqual(subprocess.run(command, check=False).returncode, 0)

    def test_lease_is_retained_by_a_running_child_if_parent_closes_its_copy(self):
        lease = self.acquire()
        process = subprocess.Popen([sys.executable, "-B", "-c",
            "import sys; print('ready', flush=True); sys.stdin.read(1)"],
            pass_fds=(lease.fd,), stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        self.assertEqual(process.stdout.readline().strip(), "ready")
        lease.close()
        with self.assertRaisesRegex(ValueError, "exclusive lease"):
            self.acquire()
        process.communicate("x", timeout=5)
        self.acquire()

    def test_symlinks_shared_writes_and_source_output_overlap_are_rejected(self):
        alias = self.root / "target-alias"
        alias.symlink_to(self.target, target_is_directory=True)
        receipt_alias = self.root / "receipt-alias"
        receipt_alias.symlink_to(self.prior_path)
        for kwargs in ({"target": alias}, {"prior": receipt_alias}, {"source": self.target},
                       {"source": self.target.parent}, {"source": self.target / "nested-source"},
                       {"output": self.target}, {"output": self.target / "nested-evidence"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.acquire(**kwargs)
        self.target.chmod(0o777)
        with self.assertRaisesRegex(ValueError, "not writable by others"):
            self.acquire()
        self.target.chmod(0o755)
        self.assertEqual(self.sentinel.read_bytes(), b"original dependency bytes")

    @unittest.skipUnless(os.geteuid() == 0, "changing actual ownership requires root")
    def test_another_uid_target_is_rejected_without_changing_it(self):
        try:
            os.chown(self.target, 65534, -1)
        except OSError as error:
            if error.errno in (errno.EPERM, errno.EINVAL, errno.ENOSYS):
                self.skipTest("this environment cannot create an actual differently-owned fixture")
            raise
        try:
            with self.assertRaisesRegex(ValueError, "current UID"):
                self.acquire()
            self.assertEqual(self.target.stat().st_uid, 65534)
        finally:
            os.chown(self.target, os.geteuid(), -1)

    def test_receipt_target_mismatch_and_changed_prior_logs_fail_closed(self):
        self.prior["environment"]["CARGO_TARGET_DIR"] = str(self.root / "some-other-target")
        self.prior_path.write_bytes(cache.canonical(self.prior))
        with self.assertRaisesRegex(ValueError, "exact target"):
            self.acquire()
        self.prior = self.receipt(self.prior_path)
        (self.prior_path.parent / "logs/native-ui-tests.stdout").write_bytes(b"replacement output")
        with self.assertRaisesRegex(ValueError, "log bytes changed"):
            self.acquire()

    def test_incompatible_owner_sdk_compiler_lock_or_profile_never_invalidates_cache(self):
        lease = self.acquire()
        for key, changed in (
            ("hepta", {"commit": "4" * 40, "tree": "5" * 40}),
            ("sdk_source_profile", {"patched_tree": "6" * 40}),
            ("toolchain_executables", {}), ("locks", {}),
            ("profile", {"toolchain": "another"}), ("cargo_profile", "debug"),
            ("native_input_paths", {"LIBRARY_PATH": "/another/library"}),
        ):
            current = self.current()
            current[key] = changed
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "differ"):
                lease.validate(current, [])
        self.assertFalse(lease.state_path.exists())
        self.assertEqual(self.sentinel.read_bytes(), b"original dependency bytes")

    def test_unknown_target_and_unfinished_lease_cannot_be_relabelled(self):
        self.prior["status"] = "running"
        self.prior.pop("exit_code")
        self.prior_path.write_bytes(cache.canonical(self.prior))
        with self.assertRaisesRegex(ValueError, "completed original"):
            self.acquire()
        self.prior = self.receipt(self.prior_path)
        lease = self.acquire()
        path = self.output / "build-receipt.json"
        self.receipt(path, self.current())
        lease.begin(path)
        lease.close()
        with self.assertRaisesRegex(ValueError, "unfinished"):
            self.acquire()

    def test_prior_receipt_replacement_during_run_prevents_finalization(self):
        lease = self.acquire()
        path = self.output / "build-receipt.json"
        self.receipt(path, self.current())
        lease.begin(path)
        self.prior_path.write_bytes(cache.canonical(dict(self.prior, error="changed later")))
        with self.assertRaisesRegex(ValueError, "prior receipt changed"):
            lease.finish()
        self.assertEqual(json.loads(lease.state_path.read_bytes())["phase"], "running")

    def test_failure_during_invalidation_cannot_fall_back_to_older_history(self):
        lease = self.acquire()
        path = self.output / "build-receipt.json"
        current = self.receipt(path, self.current())
        current["commands"] = [entry for entry in current["commands"] if entry["name"] != "native-ui-tests"]
        path.write_bytes(cache.canonical(current))
        lease.begin(path)
        lease.finish()
        lease.close()
        with self.assertRaisesRegex(ValueError, "actual UI compilation/test attempt"):
            self.acquire(prior=path)
        with self.assertRaisesRegex(ValueError, "latest completed"):
            self.acquire()


@unittest.skipUnless(shutil.which("cargo"), "actual Cargo is required for the freshness regression")
class ActualCargoCacheTests(unittest.TestCase):
    def test_local_invalidation_catches_preserved_mtime_without_deleting_dependency(self):
        with tempfile.TemporaryDirectory(prefix="trill-target-cargo-") as temporary:
            root = Path(temporary)
            source, dependency, target = (root / name for name in ("source", "dependency", "target"))
            optional = source / "local"
            for directory in (source, dependency, optional):
                (directory / "src").mkdir(parents=True)
            (dependency / "Cargo.toml").write_text(
                '[package]\nname="cache-dependency"\nversion="0.1.0"\nedition="2021"\n[workspace]\n')
            (dependency / "src/lib.rs").write_text("pub fn value() -> u8 { 1 }\n")
            (optional / "Cargo.toml").write_text(
                '[package]\nname="cache-local"\nversion="0.1.0"\nedition="2021"\n[workspace]\n')
            (optional / "src/lib.rs").write_text("pub fn value() -> u8 { 2 }\n")
            manifest = source / "Cargo.toml"
            manifest.write_text('[package]\nname="cache-product"\nversion="0.1.0"\nedition="2021"\n'
                                '[workspace]\nexclude=["local"]\n[dependencies]\n'
                                'cache-dependency={path="../dependency"}\ncache-local={path="local",optional=true}\n'
                                '[features]\nnative=["dep:cache-local"]\n')
            local = source / "src/lib.rs"
            local.write_text("#[test] fn actual_test() { assert_eq!(cache_dependency::value() + cache_local::value(), 3); }\n")
            environment = dict(os.environ, CARGO_TARGET_DIR=str(target), CARGO_INCREMENTAL="0")

            def run(arguments):
                return subprocess.run(arguments, cwd=source, env=environment, capture_output=True, text=True, timeout=60)

            test = ["cargo", "test", "--manifest-path", str(manifest), "--offline", "--features", "native"]
            first = run(test)
            self.assertEqual(first.returncode, 0, first.stderr)
            metadata = run(["cargo", "metadata", "--manifest-path", str(manifest), "--format-version", "1",
                            "--offline", "--features", "native"])
            self.assertEqual(metadata.returncode, 0, metadata.stderr)
            packages = cache.local_packages(json.loads(metadata.stdout), source)
            self.assertEqual({entry["name"] for entry in packages}, {"cache-product", "cache-local"})
            built_dependency = next((target / "debug/deps").glob("libcache_dependency-*.rlib"))
            before = (cache.sha256(built_dependency), built_dependency.stat().st_mtime_ns)
            unrelated = target / "unrelated-user-cache"
            unrelated.write_bytes(b"keep this")
            previous_time = local.stat()
            local.write_text('compile_error!("changed local source must compile");\n')
            os.utime(local, ns=(previous_time.st_atime_ns, previous_time.st_mtime_ns))
            cleaned = run(cache.clean_command(manifest, packages, ["--locked", "--offline"]))
            self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
            second = run(test)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("changed local source must compile", second.stderr)
            self.assertEqual((cache.sha256(built_dependency), built_dependency.stat().st_mtime_ns), before)
            self.assertEqual(unrelated.read_bytes(), b"keep this")


if __name__ == "__main__":
    unittest.main()
