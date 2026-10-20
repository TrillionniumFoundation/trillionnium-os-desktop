#!/usr/bin/env python3
"""Exercise the real shell runner with disposable tools, never a real kernel.

The copied runner and boot checker are unmodified. Only its external build
inputs and host tools are fixtures; locking, directory allocation, manifest
installation/cleanup, pipeline status, and boot acceptance remain under test.
"""

import errno
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from unittest import mock


BUILD = Path(__file__).resolve().parents[1]

PREPARE_INITRAMFS = """\
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--upstream', type=Path, required=True)
parser.add_argument('--busybox')
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--manifest', type=Path, required=True)
args = parser.parse_args()
args.output.write_bytes(b'fixture initramfs')
args.manifest.write_text('{}\\n')
if __import__('os').environ.get('MOCK_MANIFEST_ACTION') == 'race_create':
    (args.upstream / 'kernel/OSDK.toml').write_text('foreign race manifest\\n')
"""

MOCK_MAKE = """\
#!/usr/bin/python3
import json
import os
from pathlib import Path
import sys
import time

if '--version' in sys.argv:
    print('GNU Make fixture')
    raise SystemExit(0)

root = Path(os.environ['MOCK_PROJECT'])
(root / 'make-call.json').write_text(json.dumps({
    'argv': sys.argv[1:], 'inherited_initramfs': os.environ.get('INITRAMFS')
}))
manifest = root / 'kernel/asterinas/kernel/OSDK.toml'
if os.environ.get('MOCK_MANIFEST_ACTION') == 'replace':
    replacement = manifest.with_suffix('.replacement')
    replacement.write_text('foreign replacement manifest\\n')
    os.replace(replacement, manifest)
if os.environ.get('MOCK_GATE'):
    gate = Path(os.environ['MOCK_GATE'])
    gate.with_suffix('.ready').touch()
    deadline = time.monotonic() + 10
    while not gate.with_suffix('.release').exists():
        if time.monotonic() >= deadline:
            raise SystemExit('fixture gate was not released')
        time.sleep(0.01)
print('fixture make completed; no kernel or QEMU was executed')
"""


SDK_CARGO_FIXTURE = r'''#!/usr/bin/python3
"""Model Cargo installation/dispatch; no Rust compiler or guest is invoked."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

args = sys.argv[1:]
if args in (["-Vv"], ["--version"]):
    print("Cargo host fixture, not a Rust compiler")
    raise SystemExit(0)
root = Path(os.environ["MOCK_PROJECT"])
def record(value):
    with (root / "cargo-calls.jsonl").open("a") as output:
        output.write(json.dumps(value) + "\n")
record({"operation": "cargo", "argv": args, "cwd": os.getcwd(),
        "cargo_home": os.environ.get("CARGO_HOME"), "path": os.environ["PATH"]})
if args[:1] == ["install"]:
    assert args[:3] == ["install", "--locked", "--root"]
    assert args[4:] == ["cargo-osdk", "--path", "osdk"]
    assert os.environ.get("OSDK_LOCAL_DEV") == "1"
    if os.environ.get("MOCK_INSTALL_EXIT"):
        raise SystemExit(int(os.environ["MOCK_INSTALL_EXIT"]))
    prefix = Path(args[3])
    assert (prefix / "bin").is_dir()
    binary = prefix / "bin/cargo-osdk"
    sdk = """#!/usr/bin/python3
import json, os, sys
from pathlib import Path
root = Path(os.environ['MOCK_PROJECT'])
record = {'operation': 'sdk', 'binary': __file__, 'argv': sys.argv[1:],
          'source_root': SOURCE_ROOT, 'cargo_home': os.environ.get('CARGO_HOME')}
with (root / 'cargo-calls.jsonl').open('a') as output:
    output.write(json.dumps(record) + '\\n')
""".replace("SOURCE_ROOT", repr(str(Path.cwd().resolve())))
    binary.write_text(sdk)
    binary.chmod(0o755)
    if os.environ.get("MOCK_REPLACE_GLOBAL"):
        global_sdk = Path(os.environ["CARGO_HOME"]) / "bin/cargo-osdk"
        global_sdk.write_text("foreign SDK replacement after private installation\n")
elif args[:1] == ["osdk"]:
    binary = shutil.which("cargo-osdk")
    assert binary is not None
    raise SystemExit(subprocess.run([binary, *args]).returncode)
else:
    raise SystemExit("unexpected host fixture Cargo invocation")
'''


class KernelRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="a01-runner-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.build = self.root / "support/build"
        self.kernel = self.root / "kernel/asterinas/kernel"
        self.mock = self.root / "mock-bin"
        self.vdso = self.root / "vdso"
        for directory in (self.build / "minimal", self.kernel, self.mock, self.vdso):
            directory.mkdir(parents=True)
        for name in ("kernel.sh", "kernel-supervisor.py", "check-boot.py", "cleanup-manifest.py"):
            shutil.copyfile(BUILD / name, self.build / name)
        (self.build / "verify-source.py").write_text("print('{}')\n")
        (self.build / "minimal/prepare-initramfs.py").write_text(PREPARE_INITRAMFS)
        (self.build / "minimal/OSDK.toml").write_text("# owned fixture manifest\n")
        (self.build / "minimal/Cargo.lock").write_text("# fixture lock\n")
        (self.vdso / "vdso_x86_64.so").write_bytes(b"fixture vdso")
        for name in ("cargo", "rustc", "rustup", "gcc", "qemu-system-x86_64", "git"):
            self.write_tool(name, "#!/bin/sh\nprintf 'fixture host tool\\n'\n")
        self.write_tool("make", MOCK_MAKE)
        self.environment = {
            key: value for key, value in os.environ.items()
            if not key.startswith(("A01_", "CARGO_", "RUSTUP_", "MOCK_"))
            and key not in ("MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS", "MAKEFILES",
                            "MAKEOVERRIDES", "MAKELEVEL", "VDSO_LIBRARY_DIR", "INITRAMFS")
        }
        self.environment.update({
            "PATH": f"{self.mock}:/usr/bin:/bin",
            "CARGO_HOME": str(self.root / "cargo-home"),
            "VDSO_LIBRARY_DIR": str(self.vdso),
            "MOCK_PROJECT": str(self.root),
        })

    def write_tool(self, name, content):
        path = self.mock / name
        path.write_text(content)
        path.chmod(0o755)

    def run_runner(self, name="evidence", target="kernel", extra=None, pass_fds=()):
        environment = dict(self.environment, A01_RUN_DIR=str(self.root / name))
        environment.update(extra or {})
        return subprocess.run(
            ["bash", str(self.build / "kernel.sh"), target],
            env=environment, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=15, pass_fds=pass_fds,
        )

    def use_real_make(self):
        """Use GNU make's actual environment semantics with tiny host recipes."""
        real_make = shutil.which("make", path="/usr/bin:/bin")
        self.assertIsNotNone(real_make, "the native runner requires GNU make")
        version = subprocess.check_output([real_make, "--version"], text=True)
        self.assertIn("GNU Make", version)
        self.write_tool("make", f"#!/bin/sh\nexec {shlex.quote(real_make)} \"$@\"\n")
        upstream = self.kernel.parent
        (upstream / "Makefile").write_text(
            ".PHONY: kernel\nkernel:\n\t@python3 -I recipe.py\n"
        )
        (self.build / "minimal.mk").write_text("# host fixture overlay\n")
        (upstream / "recipe.py").write_text(
            "import json, os, pathlib, subprocess, sys\n"
            "root = pathlib.Path(os.environ['MOCK_PROJECT'])\n"
            "(root / 'recipe.json').write_text(json.dumps({'makelevel': os.environ.get('MAKELEVEL')}))\n"
            f"subprocess.run([{real_make!r}, '--no-print-directory', '-f', 'nested.mk', 'nested'], check=True)\n"
            "sys.exit(int(os.environ.get('MOCK_RECIPE_EXIT', '0')))\n"
        )
        (upstream / "nested.mk").write_text(
            ".PHONY: nested\nnested:\n"
            "\t@python3 -c 'import json, os, pathlib; "
            "pathlib.Path(os.environ[\"MOCK_PROJECT\"], \"nested.json\").write_text("
            "json.dumps({\"makelevel\": os.environ.get(\"MAKELEVEL\")}))'\n"
        )

    def use_sdk_make(self):
        """Use the full upstream Makefile and real overlay with fixture Cargo."""
        real_make = shutil.which("make", path="/usr/bin:/bin")
        self.assertIsNotNone(real_make)
        self.write_tool("make", f"#!/bin/sh\nexec {shlex.quote(real_make)} \"$@\"\n")
        upstream = self.kernel.parent
        shutil.copyfile(BUILD.parents[1] / "kernel/asterinas/Makefile", upstream / "Makefile")
        shutil.copyfile(BUILD / "minimal.mk", self.build / "minimal.mk")
        (upstream / "osdk/src").mkdir(parents=True)
        for name in ("Cargo.toml", "Cargo.lock", "src/main.rs"):
            path = upstream / "osdk" / name
            path.write_text("host fixture source only\n")
            os.utime(path, (1_600_000_000, 1_600_000_000))
        self.global_sdk = Path(self.environment["CARGO_HOME"]) / "bin/cargo-osdk"
        self.global_sdk.parent.mkdir(parents=True)
        self.global_sdk.write_text("#!/bin/sh\nprintf 'wrong global SDK selected\\n'\nexit 97\n")
        self.global_sdk.chmod(0o755)
        self.global_sdk_original = self.global_sdk.read_bytes()
        self.write_tool("cargo", SDK_CARGO_FIXTURE)

    def sdk_calls(self):
        return [json.loads(line) for line in (self.root / "cargo-calls.jsonl").read_text().splitlines()]

    def test_inherited_workspace_lock_survives_supervisor_without_reopening(self):
        lock_path = self.build / "out-kernel.lock"
        with lock_path.open("a") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            descriptor = fcntl.fcntl(owner.fileno(), fcntl.F_DUPFD_CLOEXEC, 64)
            identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            try:
                result = self.run_runner(name="inherited-lock", pass_fds=(descriptor,),
                                         extra={"A01_KERNEL_LOCK_FD": str(descriptor)})
                self.assertEqual(result.returncode, 0, result.stdout)
                with lock_path.open("a") as competitor:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)
            finally:
                os.close(descriptor)
        self.assertEqual(self.run_runner(name="after-inherited-lock").returncode, 0)

    def test_invalid_or_foreign_inherited_lock_is_rejected_before_output(self):
        lock_path = self.build / "out-kernel.lock"
        lock_path.touch()
        foreign = self.root / "foreign-lock"
        foreign.write_text("untouched host model lock\n")
        with foreign.open("a") as owner:
            descriptor = fcntl.fcntl(owner.fileno(), fcntl.F_DUPFD_CLOEXEC, 64)
            try:
                result = self.run_runner(name="invalid-parent/evidence", pass_fds=(descriptor,),
                                         extra={"A01_KERNEL_LOCK_FD": str(descriptor)})
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("does not match", result.stdout)
                self.assertFalse((self.root / "invalid-parent").exists())
            finally:
                os.close(descriptor)
        for index, value in enumerate(("", "63", "bad", "2147483648")):
            with self.subTest(value=value):
                result = self.run_runner(name=f"invalid-{index}/evidence",
                                         extra={"A01_KERNEL_LOCK_FD": value})
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse((self.root / f"invalid-{index}").exists())
        self.assertEqual(foreign.read_text(), "untouched host model lock\n")

    def test_private_sdk_is_selected_for_every_developer_target(self):
        self.use_sdk_make()
        for target in ("kernel", "run_kernel", "gdb_server"):
            with self.subTest(target=target):
                name = "private-" + target
                before = len(self.sdk_calls()) if (self.root / "cargo-calls.jsonl").exists() else 0
                if target == "gdb_server":
                    with socket.socket() as listener:
                        listener.bind(("127.0.0.1", 0))
                        listener.listen(1)
                        descriptor = fcntl.fcntl(listener.fileno(), fcntl.F_DUPFD_CLOEXEC, 64)
                        try:
                            result = self.run_runner(name=name, target=target, pass_fds=(descriptor,),
                                                     extra={"A01_GDB_FD": str(descriptor),
                                                            "A01_GDB_PORT": str(listener.getsockname()[1])})
                        finally:
                            os.close(descriptor)
                else:
                    result = self.run_runner(name=name, target=target)
                if target == "kernel":
                    self.assertEqual(result.returncode, 0, result.stdout)
                else:
                    # A successful fixture command without a guest is rejected.
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                run = self.root / name
                self.assertEqual((run / "make-exit-code.txt").read_text(), "0\n", result.stdout)
                calls = self.sdk_calls()[before:]
                self.assertEqual([call["operation"] for call in calls], ["cargo", "cargo", "sdk"])
                expected = run / "osdk/bin/cargo-osdk"
                self.assertEqual(calls[-1]["binary"], str(expected))
                self.assertEqual(calls[-1]["source_root"], str(self.kernel.parent))
                self.assertEqual(calls[-1]["argv"][:2], ["osdk", "build" if target == "kernel" else "run"])
                self.assertEqual(calls[0]["path"].split(os.pathsep)[:2],
                                 [str(expected.parent), str(self.global_sdk.parent)])
                self.assertEqual(calls[0]["cargo_home"], self.environment["CARGO_HOME"])
                self.assertEqual(calls[0]["argv"][2:4], ["--root", str(run / "osdk")])
                self.assertEqual((run / "osdk").stat().st_mode & 0o777, 0o700)
                self.assertEqual(expected.parent.stat().st_mode & 0o777, 0o700)
                import hashlib
                self.assertEqual((run / "osdk/cargo-osdk.sha256").read_text().split()[0],
                                 hashlib.sha256(expected.read_bytes()).hexdigest())
                self.assertEqual(self.global_sdk.read_bytes(), self.global_sdk_original)
                self.assertFalse((self.kernel / "OSDK.toml").exists())

    def test_global_sdk_replacement_after_install_does_not_change_private_selection(self):
        self.use_sdk_make()
        result = self.run_runner(extra={"MOCK_REPLACE_GLOBAL": "1"})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(self.sdk_calls()[-1]["binary"], str(self.root / "evidence/osdk/bin/cargo-osdk"))
        self.assertEqual(self.global_sdk.read_text(), "foreign SDK replacement after private installation\n")

    def test_each_run_installs_its_own_sdk_and_preserves_shared_dependency_cache(self):
        self.use_sdk_make()
        cache = Path(self.environment["CARGO_HOME"]) / "registry/retained-cache"
        cache.parent.mkdir()
        cache.write_bytes(b"shared cache fixture")
        for name in ("first-sdk", "second-sdk"):
            result = self.run_runner(name=name)
            self.assertEqual(result.returncode, 0, result.stdout)
        sdk_calls = [call for call in self.sdk_calls() if call["operation"] == "sdk"]
        self.assertEqual([call["binary"] for call in sdk_calls],
                         [str(self.root / name / "osdk/bin/cargo-osdk") for name in ("first-sdk", "second-sdk")])
        self.assertEqual({call["cargo_home"] for call in sdk_calls}, {self.environment["CARGO_HOME"]})
        self.assertEqual(cache.read_bytes(), b"shared cache fixture")
        self.assertEqual(self.global_sdk.read_bytes(), self.global_sdk_original)

    def test_inherited_sdk_prefix_cannot_override_private_installation(self):
        self.use_sdk_make()
        foreign = self.root / "foreign-sdk-prefix"
        foreign.mkdir()
        result = self.run_runner(extra={"A01_OSDK_INSTALL_ROOT": str(foreign)})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(list(foreign.iterdir()), [])
        self.assertEqual(self.sdk_calls()[-1]["binary"], str(self.root / "evidence/osdk/bin/cargo-osdk"))

    def test_g1c_argv_contract_and_exported_private_sdk_root(self):
        # Exercise the caller's fixed product-build argv contract with actual
        # GNU Make. Cargo, the initial image and every host binary are fixtures.
        self.use_sdk_make()
        real_make = shutil.which("make", path="/usr/bin:/bin")
        self.write_tool("make", (
            "#!/usr/bin/python3\nimport json, os, pathlib, sys\n"
            "if '--version' not in sys.argv:\n"
            " pathlib.Path(os.environ['MOCK_PROJECT'], 'make-call.json').write_text(json.dumps({"
            "'argv': sys.argv[1:], 'sdk_root': os.environ.get('A01_OSDK_INSTALL_ROOT'),"
            "'makeflags': os.environ.get('MAKEFLAGS')}))\n"
            f"os.execv({real_make!r}, [{real_make!r}, *sys.argv[1:]])\n"
        ))
        (self.build / "prepare-trusted-image.py").write_text(
            "import argparse, pathlib\n"
            "parser = argparse.ArgumentParser()\n"
            "for name in ('input', 'output', 'manifest'):\n"
            " parser.add_argument('--' + name, type=pathlib.Path, required=True)\n"
            "args = parser.parse_args()\n"
            "args.output.write_bytes(args.input.read_bytes())\n"
            "args.manifest.write_text('{}\\n')\n"
        )
        image = self.root / "fixture-initial.elf"
        image.write_bytes(b"host-only initial image fixture")
        foreign = self.root / "foreign-sdk-prefix"
        foreign.mkdir()
        sentinel = foreign / "keep.txt"
        sentinel.write_text("foreign prefix must remain untouched\n")
        result = self.run_runner(extra={
            "HEPTA_G1C_TRUSTED_OBSERVE": "1",
            "HEPTA_TRUSTED_INITIAL_ELF": str(image),
            "A01_OSDK_INSTALL_ROOT": str(foreign),
            "MAKEFLAGS": "n A01_OSDK_INSTALL_ROOT=" + str(foreign),
        })
        run = self.root / "evidence"
        command = shlex.split((run / "command.sh").read_text())
        expected = ["make", "-C", str(self.kernel.parent), "-f", "Makefile",
                    "-f", str(self.build / "minimal.mk"), "kernel"]
        required = {
            "TARGET_ARCH=x86_64", "SMP=1", "MEM=512M", "ENABLE_KVM=0",
            "BOOT_PROTOCOL=multiboot", "INITRAMFS=on", "AUTO_TEST=none",
            "HEPTA_G1C_TRUSTED_OBSERVE=1", "FEATURES=g1c-trusted-observe",
            "A01_INITRAMFS=" + str(run / "initramfs.cpio.gz"),
            "A01_QEMU_WRAPPER=" + str(self.build / "record-qemu.py"),
        }
        self.assertEqual(command[:8], expected)
        self.assertEqual(len(command), 20)
        private_sdk = run / "osdk/bin/cargo-osdk"
        self.assertEqual(command[8], "CARGO_OSDK=" + str(private_sdk))
        self.assertEqual(set(command[9:]), required)
        called = json.loads((self.root / "make-call.json").read_text())
        self.assertEqual(called["argv"], command[1:], "receipt must match the executed Make argv")
        self.assertEqual(called["sdk_root"], str(run / "osdk"))
        self.assertIsNone(called["makeflags"])
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.sdk_calls()
        self.assertEqual([row["operation"] for row in calls], ["cargo", "cargo", "sdk"])
        self.assertEqual(calls[0]["argv"][2:4], ["--root", str(run / "osdk")])
        self.assertEqual(calls[0]["cwd"], str(self.kernel.parent))
        self.assertEqual(calls[-1]["binary"], str(private_sdk))
        self.assertEqual(calls[-1]["source_root"], str(self.kernel.parent))
        self.assertIn("--features=g1c-trusted-observe", calls[-1]["argv"])
        self.assertEqual(list(foreign.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_text(), "foreign prefix must remain untouched\n")
        self.assertEqual(self.global_sdk.read_bytes(), self.global_sdk_original)
        self.assertIn("A01_OSDK_INSTALL_ROOT=" + str(run / "osdk"),
                      (run / "environment.log").read_text())

    def test_private_install_failure_stops_before_sdk_and_cleans_owned_manifest(self):
        self.use_sdk_make()
        result = self.run_runner(extra={"MOCK_INSTALL_EXIT": "47"})
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertEqual([call["operation"] for call in self.sdk_calls()], ["cargo"])
        self.assertFalse((self.root / "evidence/osdk/bin/cargo-osdk").exists())
        self.assertEqual((self.root / "evidence/make-exit-code.txt").read_text(), "2\n")
        self.assertFalse((self.kernel / "OSDK.toml").exists())
        self.assertEqual(json.loads((self.root / "evidence/manifest-cleanup.json").read_text())["outcome"], "owned_removed")
        self.assertEqual(self.global_sdk.read_bytes(), self.global_sdk_original)

    def test_relative_or_empty_cargo_home_is_rejected_before_lock_or_output(self):
        for value in ("cargo-home", "../cargo-home", ""):
            with self.subTest(value=value):
                result = self.run_runner(name="new-parent/evidence", extra={"CARGO_HOME": value})
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("CARGO_HOME must be an absolute path", result.stdout)
                self.assertFalse((self.root / "new-parent").exists())
                self.assertFalse((self.build / "out-kernel.lock").exists())
        retry = self.run_runner(name="new-parent/evidence")
        self.assertEqual(retry.returncode, 0, retry.stdout)

    def test_unset_cargo_home_explicitly_keeps_default_home_bin_after_private_bin(self):
        self.use_sdk_make()
        home = self.root / "default-home"
        default_bin = home / ".cargo/bin"
        default_bin.mkdir(parents=True)
        global_sdk = default_bin / "cargo-osdk"
        global_sdk.write_bytes(self.global_sdk_original)
        global_sdk.chmod(0o755)
        environment = dict(self.environment, HOME=str(home), A01_RUN_DIR=str(self.root / "evidence"))
        environment.pop("CARGO_HOME")
        result = subprocess.run(["bash", str(self.build / "kernel.sh"), "kernel"], env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.sdk_calls()
        self.assertEqual(calls[0]["path"].split(os.pathsep)[:2],
                         [str(self.root / "evidence/osdk/bin"), str(default_bin)])
        self.assertIsNone(calls[-1]["cargo_home"])
        self.assertEqual(global_sdk.read_bytes(), self.global_sdk_original)

    def test_unset_cargo_home_requires_absolute_default_home_before_output(self):
        for home in ("relative-home", ""):
            with self.subTest(home=home):
                environment = dict(self.environment, HOME=home,
                                   A01_RUN_DIR=str(self.root / "new-parent/evidence"))
                environment.pop("CARGO_HOME")
                result = subprocess.run(["bash", str(self.build / "kernel.sh"), "kernel"], env=environment,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("HOME must be an absolute path", result.stdout)
                self.assertFalse((self.root / "new-parent").exists())
                self.assertFalse((self.build / "out-kernel.lock").exists())

    def test_parent_components_in_cargo_home_are_rejected_before_output(self):
        result = self.run_runner(name="new-parent/evidence",
                                 extra={"CARGO_HOME": str(self.root / "placeholder/../cargo-home")})
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("must not contain '..' components", result.stdout)
        self.assertFalse((self.root / "new-parent").exists())
        self.assertFalse((self.build / "out-kernel.lock").exists())

    def test_parent_components_in_default_home_are_rejected_before_output(self):
        environment = dict(self.environment, HOME=str(self.root / "placeholder/../default-home"),
                           A01_RUN_DIR=str(self.root / "new-parent/evidence"))
        environment.pop("CARGO_HOME")
        result = subprocess.run(["bash", str(self.build / "kernel.sh"), "kernel"], env=environment,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("must not contain '..' components", result.stdout)
        self.assertFalse((self.root / "new-parent").exists())
        self.assertFalse((self.build / "out-kernel.lock").exists())

    def check_encoded_rustflags_rejected_before_output_then_unset_retry(self, value):
        result = self.run_runner(name="new-parent/evidence", extra={"CARGO_ENCODED_RUSTFLAGS": value})
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("unset CARGO_ENCODED_RUSTFLAGS", result.stdout)
        self.assertFalse((self.root / "new-parent").exists())
        self.assertFalse((self.build / "out-kernel.lock").exists())
        self.assertFalse((self.root / "make-call.json").exists())
        retry = self.run_runner(name="new-parent/evidence")
        self.assertEqual(retry.returncode, 0, retry.stdout)
        self.assertTrue((self.root / "make-call.json").is_file())
        self.assertEqual((self.root / "new-parent/evidence/run-exit-code.txt").read_text(), "0\n")

    def test_empty_encoded_rustflags_are_rejected_before_output_then_unset_retry(self):
        self.check_encoded_rustflags_rejected_before_output_then_unset_retry("")

    def test_nonempty_encoded_rustflags_are_rejected_before_output_then_unset_retry(self):
        self.check_encoded_rustflags_rejected_before_output_then_unset_retry("-Cdebuginfo=0")

    def test_inherited_dry_run_touch_and_question_flags_still_execute_real_make_recipes(self):
        self.use_real_make()
        for index, (name, flags) in enumerate((
                ("MAKEFLAGS", "n"), ("MAKEFLAGS", "t"),
                ("MAKEFLAGS", "q"), ("GNUMAKEFLAGS", "--just-print"))):
            with self.subTest(name=name, flags=flags):
                for artifact in ("recipe.json", "nested.json"):
                    (self.root / artifact).unlink(missing_ok=True)
                run_name = f"real-make-{index}"
                result = self.run_runner(name=run_name, extra={name: flags})
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertTrue((self.root / "recipe.json").is_file(), result.stdout)
                self.assertTrue((self.root / "nested.json").is_file(), result.stdout)
                environment = (self.root / run_name / "environment.log").read_text()
                self.assertIn(f"{name}_INHERITED={flags}\n", environment)
                self.assertIn(f"{name}_EFFECTIVE=<unset>\n", environment)

    def test_inherited_ignore_errors_does_not_mask_real_make_recipe_failure(self):
        self.use_real_make()
        result = self.run_runner(extra={"MAKEFLAGS": "i", "MOCK_RECIPE_EXIT": "42"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertTrue((self.root / "recipe.json").is_file(), result.stdout)
        self.assertEqual((self.root / "evidence/make-exit-code.txt").read_text(), "2\n")
        self.assertEqual((self.root / "evidence/run-exit-code.txt").read_text(), "2\n")

    def test_inherited_makefiles_are_not_read_and_normal_retry_can_build(self):
        self.use_real_make()
        injected = self.root / "inherited.mk"
        marker = self.root / "inherited-makefile-was-read"
        injected.write_text(f"$(file >{marker},unexpected inherited makefile)\n")
        result = self.run_runner(extra={"MAKEFILES": str(injected)})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse(marker.exists(), "GNU make read a caller-supplied makefile")
        self.assertTrue((self.root / "recipe.json").is_file(), result.stdout)
        environment = (self.root / "evidence/environment.log").read_text()
        self.assertIn(f"MAKEFILES_INHERITED={injected}\n", environment)
        self.assertIn("MAKEFILES_EFFECTIVE=<unset>\n", environment)
        for artifact in ("recipe.json", "nested.json"):
            (self.root / artifact).unlink()
        retry = self.run_runner(name="retry")
        self.assertEqual(retry.returncode, 0, retry.stdout)
        self.assertTrue((self.root / "recipe.json").is_file(), retry.stdout)
        self.assertFalse(marker.exists())

    def test_outer_make_state_is_recorded_and_children_establish_normal_recursion(self):
        self.use_real_make()
        result = self.run_runner(extra={
            "MAKELEVEL": "73", "MFLAGS": "-n", "MAKEOVERRIDES": "fixture=value",
            "MAKEFLAGS": "", "GNUMAKEFLAGS": "",
        })
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads((self.root / "recipe.json").read_text())["makelevel"], "1")
        self.assertEqual(json.loads((self.root / "nested.json").read_text())["makelevel"], "2")
        environment = (self.root / "evidence/environment.log").read_text()
        for recorded in ("MAKELEVEL_INHERITED=73", "MFLAGS_INHERITED=-n",
                         "MAKEOVERRIDES_INHERITED=fixture=value", "MAKEFLAGS_INHERITED=''",
                         "GNUMAKEFLAGS_INHERITED=''", "MAKEFILES_INHERITED=<unset>"):
            self.assertIn(recorded + "\n", environment)

    def test_existing_directory_and_stale_success_are_rejected(self):
        run = self.root / "evidence"
        run.mkdir()
        stale = {
            "qemu.json": json.dumps({"raw_exit_code": 33, "timed_out": False}),
            "serial.log": "\n".join((
                "OSTD initialized. Preparing components.",
                "TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_CPU_COUNT=1",
                "Successfully booted.", "TRILLIONNIUM_A01_BOOT_OK",
            )),
        }
        for name, content in stale.items():
            (run / name).write_text(content)
        result = self.run_runner(target="run_kernel")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("must be a new directory", result.stdout)
        self.assertFalse((self.root / "make-call.json").exists())
        for name, content in stale.items():
            self.assertEqual((run / name).read_text(), content)

    def test_fresh_make_success_without_qemu_is_not_boot_success(self):
        result = self.run_runner(target="run_kernel")
        run = self.root / "evidence"
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual((run / "make-exit-code.txt").read_text().strip(), "0")
        self.assertNotEqual((run / "run-exit-code.txt").read_text().strip(), "0")
        self.assertFalse((run / "qemu.json").exists())
        self.assertNotIn("PASS:", result.stdout)

    def test_concurrent_runner_refused_and_lock_inode_survives_exit(self):
        gate = self.root / "gate"
        environment = dict(
            self.environment, A01_RUN_DIR=str(self.root / "first"), MOCK_GATE=str(gate)
        )
        first = subprocess.Popen(
            ["bash", str(self.build / "kernel.sh"), "kernel"], env=environment,
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        try:
            deadline = time.monotonic() + 8
            while not gate.with_suffix(".ready").exists():
                if first.poll() is not None:
                    self.fail(f"first runner exited before gate: {first.communicate()[0]}")
                if time.monotonic() >= deadline:
                    self.fail("first runner did not reach the fixture make gate")
                time.sleep(0.01)
            lock = self.build / "out-kernel.lock"
            identity = (lock.stat().st_dev, lock.stat().st_ino)
            second = self.run_runner(name="second")
            self.assertNotEqual(second.returncode, 0, second.stdout)
            self.assertIn("another A01 build", second.stdout)
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
            gate.with_suffix(".release").touch()
            output = first.communicate(timeout=8)[0]
            self.assertEqual(first.returncode, 0, output)
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
            third = self.run_runner(name="third")
            self.assertEqual(third.returncode, 0, third.stdout)
            self.assertEqual((lock.stat().st_dev, lock.stat().st_ino), identity)
        finally:
            gate.with_suffix(".release").touch()
            if first.poll() is None:
                try:
                    first.communicate(timeout=8)
                except subprocess.TimeoutExpired:
                    first.kill()
                    first.communicate(timeout=3)

    def test_busy_lock_preserves_explicit_output_path_for_same_command_retry(self):
        requested = self.root / "new-parent/evidence"
        lock_path = self.build / "out-kernel.lock"
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            result = self.run_runner(name="new-parent/evidence")
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("another A01 build", result.stdout)
            self.assertFalse(requested.parent.exists(), "busy lock consumed the new output parent")
            self.assertFalse((self.root / "make-call.json").exists())
        retry = self.run_runner(name="new-parent/evidence")
        self.assertEqual(retry.returncode, 0, retry.stdout)
        self.assertTrue((requested / "run-exit-code.txt").is_file())
        self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)

    def test_busy_lock_preserves_default_output_for_same_command_retry(self):
        command = ["bash", str(self.build / "kernel.sh"), "kernel"]
        output_parent = self.build / "out"
        lock_path = self.build / "out-kernel.lock"
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
            result = subprocess.run(command, env=self.environment, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("another A01 build", result.stdout)
            self.assertFalse(output_parent.exists(), "busy lock allocated a default evidence directory")
            self.assertFalse((self.root / "make-call.json").exists())
        retry = subprocess.run(command, env=self.environment, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
        self.assertEqual(retry.returncode, 0, retry.stdout)
        runs = list(output_parent.iterdir())
        self.assertEqual(len(runs), 1)
        self.assertEqual((runs[0] / "run-exit-code.txt").read_text(), "0\n")
        self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)

    def test_owned_manifest_removed_after_success(self):
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.kernel / "OSDK.toml").exists())
        self.assertEqual(list(self.kernel.glob(".a01-osdk-*")), [])

    def test_signal_immediately_after_manifest_publication_cleans_owned_inode(self):
        real_ln = shutil.which("ln")
        self.assertIsNotNone(real_ln, "the native runner requires the host ln tool")
        # Publish a real hard link, then interrupt the waiting runner before it
        # executes its next shell statement. This exercises its EXIT trap in
        # the otherwise tiny ownership-registration window.
        self.write_tool("ln", (
            "#!/bin/sh\n"
            f"{shlex.quote(real_ln)} \"$@\" || exit $?\n"
            "kill -TERM \"$PPID\"\n"
        ))
        result = self.run_runner()
        self.assertIn(result.returncode, (-signal.SIGTERM, 128 + signal.SIGTERM), result.stdout)
        self.assertFalse((self.root / "make-call.json").exists())
        self.assertEqual(list(self.kernel.glob(".a01-osdk-*")), [])
        self.assertFalse(
            (self.kernel / "OSDK.toml").exists(),
            "interrupted publication left the runner's owned OSDK manifest behind",
        )

    def test_existing_manifest_is_preserved(self):
        manifest = self.kernel / "OSDK.toml"
        manifest.write_text("preexisting foreign manifest\n")
        identity = manifest.stat().st_ino
        result = self.run_runner()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("already exists", result.stdout)
        self.assertEqual(manifest.read_text(), "preexisting foreign manifest\n")
        self.assertEqual(manifest.stat().st_ino, identity)
        self.assertFalse((self.root / "make-call.json").exists())

    def test_manifest_created_during_preparation_is_preserved(self):
        result = self.run_runner(extra={"MOCK_MANIFEST_ACTION": "race_create"})
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            (self.kernel / "OSDK.toml").read_text(), "foreign race manifest\n"
        )
        self.assertEqual(list(self.kernel.glob(".a01-osdk-*")), [])
        self.assertFalse((self.root / "make-call.json").exists())

    def test_manifest_replaced_during_build_is_preserved(self):
        result = self.run_runner(extra={"MOCK_MANIFEST_ACTION": "replace"})
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(
            (self.kernel / "OSDK.toml").read_text(), "foreign replacement manifest\n"
        )
        self.assertEqual(list(self.kernel.glob(".a01-osdk-*")), [])

    def test_fixed_initramfs_argument_overrides_inherited_off(self):
        result = self.run_runner(extra={"INITRAMFS": "off"})
        self.assertEqual(result.returncode, 0, result.stdout)
        call = json.loads((self.root / "make-call.json").read_text())
        self.assertEqual(call["inherited_initramfs"], "off")
        self.assertIn("INITRAMFS=on", call["argv"])
        self.assertNotIn("INITRAMFS=off", call["argv"])

    def test_log_write_failure_overrides_successful_make(self):
        self.write_tool("tee", "#!/bin/sh\ncat >/dev/null\nexit 17\n")
        result = self.run_runner()
        run = self.root / "evidence"
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("failed to retain the complete command log", result.stdout)
        self.assertEqual((run / "make-exit-code.txt").read_text().strip(), "0")
        self.assertEqual((run / "log-exit-code.txt").read_text().strip(), "17")
        self.assertNotEqual((run / "run-exit-code.txt").read_text().strip(), "0")

    def inject_cleanup_restore_conflict(self):
        """Use the real helper, injecting writers at its atomic boundaries."""
        helper = BUILD / "cleanup-manifest.py"
        (self.build / "cleanup-manifest.py").write_text(
            "import os, runpy\n"
            f"namespace=runpy.run_path({str(helper)!r}, run_name='cleanup_fixture')\n"
            "state=namespace['clean_manifest'].__globals__\n"
            "capture=state['capture_candidate']\n"
            "restore=state['restore_no_replace']\n"
            "def replace_before_capture(manifest, candidate):\n"
            " replacement=manifest.with_name('first-foreign.toml')\n"
            " replacement.write_text('first foreign manifest\\n')\n"
            " os.replace(replacement, manifest)\n"
            " capture(manifest, candidate)\n"
            "def conflict_before_restore(candidate, manifest):\n"
            " with manifest.open('x') as stream: stream.write('second foreign manifest\\n')\n"
            " restore(candidate, manifest)\n"
            "state['capture_candidate']=replace_before_capture\n"
            "state['restore_no_replace']=conflict_before_restore\n"
            "raise SystemExit(namespace['main']())\n"
        )

    def assert_cleanup_retained_foreign(self):
        run = self.root / "evidence"
        cleanup = json.loads((run / "manifest-cleanup.json").read_text())
        self.assertFalse(cleanup["passed"])
        self.assertEqual(cleanup["outcome"], "foreign_retained")
        self.assertEqual(Path(cleanup["retained_path"]).read_text(), "first foreign manifest\n")
        self.assertEqual((self.kernel / "OSDK.toml").read_text(), "second foreign manifest\n")
        self.assertEqual((run / "manifest-cleanup-exit-code.txt").read_text(), "1\n")

    def test_cleanup_restore_conflict_changes_success_to_failure(self):
        self.inject_cleanup_restore_conflict()
        result = self.run_runner()
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assert_cleanup_retained_foreign()
        run = self.root / "evidence"
        self.assertEqual((run / "make-exit-code.txt").read_text(), "0\n")
        self.assertEqual((run / "run-exit-code.txt").read_text(), "1\n")
        self.assertIn("retained for recovery:", result.stdout)

    def test_cleanup_restore_conflict_preserves_original_make_failure(self):
        self.inject_cleanup_restore_conflict()
        self.write_tool("make", MOCK_MAKE + "\nraise SystemExit(37)\n")
        result = self.run_runner()
        self.assertEqual(result.returncode, 37, result.stdout)
        self.assert_cleanup_retained_foreign()
        run = self.root / "evidence"
        self.assertEqual((run / "make-exit-code.txt").read_text(), "37\n")
        self.assertEqual((run / "run-exit-code.txt").read_text(), "37\n")


class ManifestCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="a01-manifest-custody-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manifest = self.root / "OSDK.toml"
        self.manifest.write_text("owned manifest\n")
        self.anchor = self.manifest.open("rb")
        self.addCleanup(self.anchor.close)
        self.owned_identity = (os.fstat(self.anchor.fileno()).st_dev,
                               os.fstat(self.anchor.fileno()).st_ino)
        spec = importlib.util.spec_from_file_location("manifest_cleanup", BUILD / "cleanup-manifest.py")
        self.helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.helper)

    def cleanup_manifest(self):
        return self.helper.clean_manifest(self.manifest, self.anchor.fileno())

    def replace_with_foreign(self, text="foreign manifest\n"):
        replacement = self.root / "replacement.toml"
        replacement.write_text(text)
        identity = replacement.stat().st_dev, replacement.stat().st_ino
        os.replace(replacement, self.manifest)
        self.assertNotEqual(identity, self.owned_identity)
        return identity

    def test_owned_inode_is_removed_from_private_custody(self):
        result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["outcome"], "owned_removed")
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.root.iterdir()), [])
        self.assertEqual(os.fstat(self.anchor.fileno()).st_nlink, 0)

    def test_missing_public_path_is_a_noop(self):
        self.manifest.unlink()
        result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["outcome"], "absent")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_replacement_immediately_before_capture_is_restored(self):
        capture = self.helper.capture_candidate
        identity = []

        def replace_then_capture(manifest, candidate):
            identity.append(self.replace_with_foreign())
            capture(manifest, candidate)

        with mock.patch.object(self.helper, "capture_candidate", side_effect=replace_then_capture):
            result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["outcome"], "foreign_restored")
        self.assertEqual((self.manifest.stat().st_dev, self.manifest.stat().st_ino), identity[0])
        self.assertEqual(self.manifest.read_text(), "foreign manifest\n")

    def test_new_public_entry_after_owned_capture_is_untouched(self):
        capture = self.helper.capture_candidate

        def capture_then_replace(manifest, candidate):
            capture(manifest, candidate)
            manifest.write_text("new public manifest\n")

        with mock.patch.object(self.helper, "capture_candidate", side_effect=capture_then_replace):
            result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["outcome"], "owned_removed")
        self.assertEqual(self.manifest.read_text(), "new public manifest\n")

    def test_foreign_dangling_symlink_is_restored_without_following(self):
        self.manifest.unlink()
        self.manifest.symlink_to("missing-target")
        identity = self.manifest.lstat().st_ino
        result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertTrue(self.manifest.is_symlink())
        self.assertEqual(self.manifest.lstat().st_ino, identity)
        self.assertEqual(os.readlink(self.manifest), "missing-target")
        self.assertFalse((self.root / "missing-target").exists())

    def test_foreign_directory_and_contents_are_restored(self):
        self.manifest.unlink()
        self.manifest.mkdir()
        (self.manifest / "contents").write_text("directory contents\n")
        identity = self.manifest.stat().st_ino
        result = self.cleanup_manifest()
        self.assertTrue(result["passed"], result)
        self.assertEqual(self.manifest.stat().st_ino, identity)
        self.assertEqual((self.manifest / "contents").read_text(), "directory contents\n")

    def test_restore_conflict_retains_both_foreign_entries(self):
        self.replace_with_foreign("first foreign\n")
        restore = self.helper.restore_no_replace

        def concurrent_public_writer(candidate, manifest):
            manifest.write_text("second foreign\n")
            restore(candidate, manifest)

        with mock.patch.object(self.helper, "restore_no_replace", side_effect=concurrent_public_writer):
            result = self.cleanup_manifest()
        self.assertFalse(result["passed"], result)
        self.assertEqual(result["errno"], errno.EEXIST)
        self.assertEqual(Path(result["retained_path"]).read_text(), "first foreign\n")
        self.assertEqual(self.manifest.read_text(), "second foreign\n")
        self.assertEqual(Path(result["custody"]).stat().st_mode & 0o777, 0o700)

    def test_unavailable_noreplace_retains_foreign_candidate(self):
        self.replace_with_foreign()
        with mock.patch.object(self.helper, "restore_no_replace", side_effect=OSError(errno.ENOSYS, "unsupported")):
            result = self.cleanup_manifest()
        self.assertFalse(result["passed"], result)
        self.assertEqual(Path(result["retained_path"]).read_text(), "foreign manifest\n")
        self.assertFalse(self.manifest.exists())

    def test_exception_after_capture_preserves_candidate(self):
        capture = self.helper.capture_candidate

        def capture_then_fail(manifest, candidate):
            capture(manifest, candidate)
            raise RuntimeError("injected after atomic capture")

        with mock.patch.object(self.helper, "capture_candidate", side_effect=capture_then_fail):
            result = self.cleanup_manifest()
        self.assertFalse(result["passed"], result)
        self.assertEqual(Path(result["candidate"]).read_text(), "owned manifest\n")
        self.assertTrue(Path(result["retained_path"]).exists())

    def test_invalid_anchor_never_moves_public_entry(self):
        result = self.helper.clean_manifest(self.manifest, -1)
        self.assertFalse(result["passed"], result)
        self.assertEqual(self.manifest.read_text(), "owned manifest\n")
        self.assertEqual(list(self.root.iterdir()), [self.manifest])


if __name__ == "__main__":
    unittest.main(verbosity=2)
