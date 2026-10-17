#!/usr/bin/env python3
"""Use the fixed real Cargo to test private external-command lookup only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--cargo", required=True, type=Path)
args = parser.parse_args()
cargo = args.cargo.resolve(strict=True)
base = Path(__file__).resolve().parent / "cargo-lookup-results"
base.mkdir()
home = base / "cargo-home"
global_bin = home / "bin"
private_bin = base / "run-sdk/bin"
for directory in (global_bin, private_bin):
    directory.mkdir(parents=True)
for directory, marker in ((global_bin, "GLOBAL"), (private_bin, "PRIVATE")):
    tool = directory / "cargo-osdk"
    tool.write_text("#!/usr/bin/python3\nimport json,sys\nprint(json.dumps({\"selected\":" + repr(marker) + ",\"argv\":sys.argv}))\n")
    tool.chmod(0o755)
env = dict(os.environ, CARGO_HOME=str(home))
for key in ("CARGO", "CARGO_ENCODED_RUSTFLAGS", "RUSTFLAGS", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER"):
    env.pop(key, None)
report = {"scope": "real fixed Cargo custom-subcommand lookup; fake SDKs only; no compilation/QEMU/global SDK mutation",
          "cargo": str(cargo), "cargo_sha256": hashlib.sha256(cargo.read_bytes()).hexdigest(),
          "cargo_version": subprocess.check_output([str(cargo), "-Vv"], env=env).decode(), "cases": []}
variants = (("unlisted-home-default-prepend", [private_bin, Path("/usr/bin"), Path("/bin")], "GLOBAL"),
            ("explicit-home-after-private", [private_bin, global_bin, Path("/usr/bin"), Path("/bin")], "PRIVATE"),
            ("explicit-home-before-private", [global_bin, private_bin, Path("/usr/bin"), Path("/bin")], "GLOBAL"))
for name, directories, expected in variants:
    case_env = dict(env, PATH=os.pathsep.join(map(str, directories)))
    command = [str(cargo), "osdk", "--version", "literal argument"]
    result = subprocess.run(command, cwd=base, env=case_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (base / (name + ".stdout")).write_bytes(result.stdout)
    (base / (name + ".stderr")).write_bytes(result.stderr)
    assert result.returncode == 0, result.stderr.decode()
    record = json.loads(result.stdout)
    assert record["selected"] == expected, record
    assert record["argv"][1:] == ["osdk", "--version", "literal argument"], record
    report["cases"].append({"name": name, "command": command, "PATH": case_env["PATH"],
                            "CARGO_HOME": case_env["CARGO_HOME"], "returncode": result.returncode, "result": record})
(base / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"cargo_version": report["cargo_version"], "cases": len(report["cases"]), "all_expected": True}))
