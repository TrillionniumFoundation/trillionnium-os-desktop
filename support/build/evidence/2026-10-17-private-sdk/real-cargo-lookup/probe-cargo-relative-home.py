#!/usr/bin/env python3
"""An actual Cargo lookup counterexample for a relative CARGO_HOME."""
import json
import os
from pathlib import Path
import subprocess

base = Path(__file__).resolve().parent
root = base / "cargo-relative-lookup-results"
root.mkdir()
home = root / "cargo-home"
private = root / "sdk/bin"
for directory, marker in ((home / "bin", "GLOBAL"), (private, "PRIVATE")):
    directory.mkdir(parents=True)
    tool = directory / "cargo-osdk"
    tool.write_text("#!/bin/sh\nprintf '" + marker + "\\n'\n")
    tool.chmod(0o755)
cargo = base.parent / "toolchains/rustup/toolchains/nightly-2026-07-21-x86_64-unknown-linux-gnu/bin/cargo"
env = dict(os.environ, CARGO_HOME="cargo-home", PATH=str(private) + ":cargo-home/bin:/usr/bin:/bin")
result = subprocess.run([str(cargo), "osdk", "--version"], cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
assert result.returncode == 0 and result.stdout == b"GLOBAL\n", (result.returncode, result.stdout, result.stderr)
report = {"scope": "real fixed Cargo lookup, fake SDKs, no compilation", "command": [str(cargo), "osdk", "--version"],
          "cwd": str(root), "CARGO_HOME": env["CARGO_HOME"], "PATH": env["PATH"], "returncode": result.returncode,
          "stdout": result.stdout.decode(), "stderr": result.stderr.decode(),
          "conclusion": "relative Cargo home bin in PATH does not suppress Cargo's absolute home/bin default prepend"}
(root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
