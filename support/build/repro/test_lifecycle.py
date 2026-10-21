#!/usr/bin/env python3
"""Actual repro CLI lifecycle with owned Python host models; never a kernel/VM."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent


class ReproLifecycleTests(unittest.TestCase):
    def fixture(self, root, status=None):
        checkout = root / "checkout"
        (checkout / "support/build").mkdir(parents=True)
        source = checkout / "kernel/asterinas"
        source.mkdir(parents=True)
        (source / "Components.toml").write_text("[components]\n")
        (source / "Cargo.toml").write_text("[workspace]\n")
        child = ("import os,signal,time;from pathlib import Path;"
                 "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                 f"Path({str(root / 'descendant.pid')!r}).write_text(str(os.getpid()));time.sleep(60)")
        driver = root / "host-driver.py"
        driver.write_text(
            "import json,os,signal,subprocess,sys,time\nfrom pathlib import Path\n"
            f"root=Path({str(root)!r})\n"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
            f"child=subprocess.Popen([sys.executable,'-I','-c',{child!r}])\n"
            "while not (root/'descendant.pid').exists():time.sleep(.01)\n"
            "(root/'ready.json').write_text(json.dumps({'leader':os.getpid(),'group':os.getpgrp(),"
            "'descendant':int((root/'descendant.pid').read_text()),"
            "'worker_route':os.environ.get('A01_KERNEL_WORKER'),"
            "'lock_fd':os.environ.get('A01_KERNEL_LOCK_FD')}))\n"
            + (f"raise SystemExit({status})\n" if status is not None else "time.sleep(60)\n"))
        script = checkout / "support/build/kernel.sh"
        script.write_text(f"#!/bin/sh\nexec {sys.executable} -I {str(driver)!r}\n")
        script.chmod(0o700)
        launcher = Path(os.environ.get("A01_REPRO_LIFECYCLE_SOURCE", HERE / "run.py"))
        wrapper = root / "host-entry.py"
        wrapper.write_text(
            "import importlib.util,os,signal,sys\n"
            f"spec=importlib.util.spec_from_file_location('host_repro',{str(launcher)!r})\n"
            "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
            "# Host model: version metadata is injected; no Rust/Cargo executes.\n"
            "module.fixed_rustc_version=lambda *args: b'rustc host lifecycle model\\n'\n"
            "# Metadata binding itself is exercised by test_metadata.py's subprocess fixtures.\n"
            "module.profile.metadata_receipts=lambda *args: {'passed':True,'count':1,'host_model':True}\n"
            "if os.environ.get('A01_REPRO_HOST_POSTCHECK_SIGNAL') == '1':\n"
            " original=module.profile.snapshot\n calls=[0]\n"
            " def snapshot(root):\n"
            "  value=original(root);calls[0]+=1\n"
            "  if calls[0]==3:os.kill(os.getpid(),signal.SIGTERM)\n"
            "  return value\n"
            " module.profile.snapshot=snapshot\n"
            "try: raise SystemExit(module.main())\n"
            "except (OSError,ValueError,KeyError) as error:\n"
            " print('host repro refusal: '+str(error),file=sys.stderr);raise SystemExit(2)\n")
        output, profile = root / "output", root / "profile"
        command = [sys.executable, "-B", "-I", *( ["-O"] if sys.flags.optimize else []), str(wrapper),
                   "--checkout", str(checkout), "--profile-root", str(profile), "--output", str(output)]
        env = {key: value for key, value in os.environ.items()
               if key not in ("CARGO_ENCODED_RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS")}
        return checkout, output, profile, command, env, launcher

    def save(self, name, record, root):
        setting = os.environ.get("A01_REPRO_LIFECYCLE_OUT")
        if setting:
            output = Path(setting) / name
            output.mkdir(parents=True, exist_ok=False)
            (output / "observation.json").write_text(json.dumps(record, indent=2) + "\n")
            for filename in ("console.log", "output/result.json", "output/console.log.command.json",
                             "ready.json"):
                source = root / filename
                if source.is_file():
                    (output / filename.replace("/", "-")).write_bytes(source.read_bytes())

    def test_busy_workspace_does_not_create_profile_or_output(self):
        with tempfile.TemporaryDirectory(prefix="a01-repro-busy-") as temporary:
            root = Path(temporary)
            checkout, output, profile, command, env, launcher = self.fixture(root, status=0)
            (checkout / "support/build/kernel.sh").write_text("#!/bin/sh\nexit 0\n")
            lock_path = checkout / "support/build/out-kernel.lock"
            with lock_path.open("a") as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=5)
            record = {"kind": "host_model_repro_cli_no_rust_no_kernel_no_vm",
                      "argv": command, "returncode": result.returncode,
                      "source_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
                      "output_exists": output.exists(), "profile_exists": profile.exists(),
                      "message": result.stdout.decode(errors="replace")}
            (root / "console.log").write_bytes(result.stdout)
            self.save("busy", record, root)
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn(b"another A01 build", result.stdout)
            self.assertFalse(output.exists())
            self.assertFalse(profile.exists())
            retry = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=5)
            self.assertEqual(retry.returncode, 0, retry.stdout)
            self.assertTrue(output.is_dir())
            self.assertTrue(profile.is_dir())

    def test_compatible_profile_reuses_but_existing_output_and_foreign_owner_are_preserved(self):
        with tempfile.TemporaryDirectory(prefix="a01-repro-reuse-") as temporary:
            root = Path(temporary)
            checkout, output, profile, command, env, _ = self.fixture(root, status=0)
            (checkout / "support/build/kernel.sh").write_text("#!/bin/sh\nexit 0\n")
            first = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, timeout=5)
            self.assertEqual(first.returncode, 0, first.stdout)
            original = (output / "result.json").read_bytes()
            existing = subprocess.run(command, env=env, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, timeout=5)
            self.assertEqual(existing.returncode, 2, existing.stdout)
            self.assertEqual((output / "result.json").read_bytes(), original)
            next_command = [*command[:-1], str(root / "output-next")]
            compatible = subprocess.run(next_command, env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=5)
            self.assertEqual(compatible.returncode, 0, compatible.stdout)
            owner_path = profile / "owner.json"
            owner = json.loads(owner_path.read_text())
            owner["embedded_builder"]["hostname"] = "foreign host model"
            changed = (json.dumps(owner) + "\n").encode()
            owner_path.write_bytes(changed)
            refused = subprocess.run([*command[:-1], str(root / "refused-output")], env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
            self.assertEqual(refused.returncode, 2, refused.stdout)
            self.assertIn(b"foreign or incompatible", refused.stdout)
            self.assertFalse((root / "refused-output").exists())
            self.assertEqual(owner_path.read_bytes(), changed)

    def test_inherited_compiler_override_is_rejected_without_output_or_profile(self):
        with tempfile.TemporaryDirectory(prefix="a01-repro-invalid-") as temporary:
            root = Path(temporary)
            _, output, profile, command, env, _ = self.fixture(root)
            for name, value in (("CARGO_ENCODED_RUSTFLAGS", ""), ("RUSTFLAGS", "--cfg=host_model"),
                                ("RUSTC_WRAPPER", "/host-model-wrapper"),
                                ("RUSTC_WORKSPACE_WRAPPER", "/host-model-wrapper")):
                with self.subTest(name=name):
                    refused = subprocess.run(command, env=dict(env, **{name: value}), stdout=subprocess.PIPE,
                                             stderr=subprocess.STDOUT, timeout=5)
                    self.assertEqual(refused.returncode, 2, refused.stdout)
                    self.assertIn(b"unset inherited compiler", refused.stdout)
                    self.assertFalse(output.exists())
                    self.assertFalse(profile.exists())

    def test_signal_during_postcheck_retains_cancel_status_after_successful_child(self):
        with tempfile.TemporaryDirectory(prefix="a01-repro-postcheck-") as temporary:
            root = Path(temporary)
            checkout, output, _, command, env, launcher = self.fixture(root, status=0)
            (checkout / "support/build/kernel.sh").write_text("#!/bin/sh\nexit 0\n")
            result = subprocess.run(command, env=dict(env, A01_REPRO_HOST_POSTCHECK_SIGNAL="1"),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
            receipt = json.loads((output / "result.json").read_text())
            (root / "console.log").write_bytes(result.stdout)
            self.save("postcheck-sigterm", {"kind": "host_model_sigterm_in_postcheck_no_kernel_no_vm",
                "argv": command, "returncode": result.returncode, "result": receipt,
                "source_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest()}, root)
            self.assertEqual(result.returncode, 143)
            self.assertEqual(receipt["returncode"], 143)
            self.assertEqual(receipt["child_returncode"], 0)
            self.assertEqual(receipt["interrupted_by"], "SIGTERM")

    def lifecycle(self, name, signum=None, status=None):
        with tempfile.TemporaryDirectory(prefix="a01-repro-life-") as temporary:
            root = Path(temporary)
            checkout, output, profile, command, env, launcher = self.fixture(root, status=status)
            process, descriptors = None, {}
            record = {"kind": "host_model_actual_repro_cli_python_descendants_no_rust_no_kernel_no_vm",
                      "argv": command, "signal": signum, "requested_status": status,
                      "source_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest()}
            try:
                with (root / "console.log").open("wb") as log:
                    process = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
                    deadline = time.monotonic() + 6
                    while not (root / "ready.json").exists():
                        self.assertLess(time.monotonic(), deadline)
                        self.assertIsNone(process.poll(), (root / "console.log").read_text())
                        time.sleep(.01)
                    ready = json.loads((root / "ready.json").read_text())
                    for role in ("leader", "descendant"):
                        try:
                            descriptors[role] = os.pidfd_open(ready[role])
                        except ProcessLookupError:
                            if role != "leader" or status is None:
                                raise
                    if signum is not None:
                        process.send_signal(signum)
                    process.wait(timeout=5)
                exited = {role: bool(select.select([descriptor], [], [], 2)[0])
                          for role, descriptor in descriptors.items()}
                result = json.loads((output / "result.json").read_text()) if (output / "result.json").exists() else None
                record.update(returncode=process.returncode, ready=ready, pidfd_exited=exited, result=result)
                with (checkout / "support/build/out-kernel.lock").open("a") as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    record["workspace_lock_released"] = True
                self.assertEqual(process.returncode, 128 + signum if signum else status,
                                 (root / "console.log").read_text())
                self.assertTrue(all(exited.values()), exited)
                self.assertEqual(ready["worker_route"], "1")
                self.assertGreaterEqual(int(ready["lock_fd"]), 64)
                self.assertTrue(result["owned_session_cleanup"]["leader_reaped"])
                if signum:
                    self.assertEqual(result["interrupted_by"], signal.Signals(signum).name)
                else:
                    self.assertEqual(result["child_returncode"], status)
                record["passed"] = True
            finally:
                for descriptor in descriptors.values():
                    try:
                        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    select.select([descriptor], [], [], 2)
                    os.close(descriptor)
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
                self.save(name, record, root)

    def test_sigterm_cleans_owned_group_and_retains_receipt(self):
        self.lifecycle("sigterm", signum=signal.SIGTERM)

    def test_original_nonzero_status_survives_descendant_cleanup(self):
        self.lifecycle("status37", status=37)


if __name__ == "__main__":
    unittest.main()
