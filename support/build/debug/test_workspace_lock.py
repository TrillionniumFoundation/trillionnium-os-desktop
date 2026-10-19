#!/usr/bin/env python3
"""Host model only: public debug entry ordering; no tool, kernel or VM runs."""
import contextlib
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


class DebugWorkspaceTests(unittest.TestCase):
    def test_busy_workspace_does_not_consume_output_then_same_argv_can_retry(self):
        with tempfile.TemporaryDirectory(prefix="a01-debug-lock-") as temporary:
            root = Path(temporary)
            project = root / "checkout"
            script = project / "support/build/debug/run.py"
            script.parent.mkdir(parents=True)
            source = Path(os.environ.get("A01_DEBUG_LOCK_SOURCE", Path(__file__).with_name("run.py")))
            shutil.copyfile(source, script)
            spec = importlib.util.spec_from_file_location("host_debug_workspace", script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            output = root / "unconsumed-parent/output"
            argv = [str(script), "--output", str(output)]
            observations = []
            lock_path = project / "support/build/out-kernel.lock"
            with lock_path.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)
                for phase in ("busy", "retry"):
                    if phase == "retry":
                        fcntl.flock(lock, fcntl.LOCK_UN)
                    message = io.StringIO()
                    # No GDB, Cargo, child process, or VM is launched. Once the
                    # lock becomes available, a missing-tool refusal proves
                    # that the identical argv was able to allocate its output.
                    with patch.object(sys, "argv", argv), patch.object(module.shutil, "which", return_value=None), \
                            patch.dict(os.environ, {}, clear=False), contextlib.redirect_stderr(message), \
                            contextlib.redirect_stdout(message):
                        os.environ.pop("CARGO_ENCODED_RUSTFLAGS", None)
                        try:
                            status = module.main()
                        except OSError as error:
                            status = 1
                            message.write(str(error))
                    observations.append({"phase": phase, "status": status,
                        "output_exists": output.exists(), "parent_exists": output.parent.exists(),
                        "message": message.getvalue()})
                self.assertEqual((lock_path.stat().st_dev, lock_path.stat().st_ino), identity)
            saved = os.environ.get("A01_DEBUG_LOCK_OUT")
            if saved:
                destination = Path(saved)
                destination.mkdir(parents=True, exist_ok=False)
                (destination / "observation.json").write_text(json.dumps({
                    "kind": "host_model_public_debug_entry_no_tools_no_kernel_no_vm",
                    "source_sha256": module.sha256(source), "argv": argv,
                    "observations": observations}, indent=2) + "\n")
            busy, retry = observations
            self.assertEqual(busy["status"], 1)
            self.assertIn("another A01 build", busy["message"])
            self.assertFalse(busy["output_exists"], busy)
            self.assertFalse(busy["parent_exists"], busy)
            self.assertEqual(retry["status"], 1)
            self.assertTrue(retry["output_exists"])
            self.assertIn("GDB and nm", json.loads((output / "result.json").read_text())["error"])
            before = (output / "result.json").read_bytes()
            with patch.object(sys, "argv", argv), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(module.main(), 1)
            self.assertEqual((output / "result.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
