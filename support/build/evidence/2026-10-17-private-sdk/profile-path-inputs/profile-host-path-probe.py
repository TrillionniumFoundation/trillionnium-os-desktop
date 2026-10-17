#!/usr/bin/env python3
"""Invoke the exact schema4 Python descriptor code, without invoking Rust.

This is a host-only descriptor dependency test. It is not a second-host build,
nor does it establish that Cargo's own salts change under a new Cargo home.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
REPO = BASE.parent / "trillionnium-os-desktop"
COMMIT = "cdf308e751e561328c556ca2ece86056d15809a0"
OUT = BASE / "profile-host-path-results"
OUT.mkdir()
raw = subprocess.check_output(["git", "-C", str(REPO), "show", COMMIT + ":support/build/repro/profile.py"])
source = OUT / "profile.py"
source.write_bytes(raw)
spec = importlib.util.spec_from_file_location("schema4_under_review", source)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)
root = OUT / "kernel"
(root / "pkg").mkdir(parents=True)
(root / "pkg/Cargo.toml").write_text('[package]\nname="pkg"\nversion="0.1.0"\n')
artifact = OUT / "libregistry.rlib"
artifact.write_bytes(b"fixture artifact identity, not a real Rust library")
policy = {"real_root": str(root), "virtual_root": "/workspace/scratch/ae1a8cf05419/full-kernel-profile-v4/virtual-asterinas", "rustc_identity": "fixed-rustc-identity"}
registry_argv = ["rustc", "--crate-name", "registry", "--crate-type", "lib", "src/lib.rs",
                 "-C", "metadata=fixed-original-salt", "-C", "extra-filename=-fixed-file",
                 "--out-dir", str(OUT)]
local_argv = ["rustc", "--crate-name", "pkg", "--crate-type", "lib", "src/lib.rs",
              "-C", "metadata=local-original", "-C", "extra-filename=-local-file",
              "--out-dir", str(root / "target/deps"), "--extern", "registry=" + str(artifact)]
rows = []
for cargo_home in ("/host-a/cargo", "/host-b/cargo"):
    registry_manifest = cargo_home + "/registry/src/index.crates.io-fixed/registry-0.1.0"
    registry_env = {"CARGO_MANIFEST_DIR": registry_manifest, "CARGO_PKG_NAME": "registry", "CARGO_PKG_VERSION": "0.1.0"}
    effective, producer = profile.canonical_compiler_metadata(registry_argv, registry_env, registry_manifest, policy, [])
    assert effective == registry_argv
    history = [{"state": "completed", "returncode": 0, "unit": producer,
                "artifacts": {str(artifact): profile.artifact_identity(artifact)}}]
    local_env = {"CARGO_MANIFEST_DIR": str(root / "pkg"), "CARGO_PKG_NAME": "pkg", "CARGO_PKG_VERSION": "0.1.0"}
    _, consumer = profile.canonical_compiler_metadata(local_argv, local_env, str(root / "pkg"), policy, history)
    rows.append({"cargo_home": cargo_home, "producer": producer, "local_consumer": consumer})
assert rows[0]["producer"]["canonical_id"] != rows[1]["producer"]["canonical_id"]
assert rows[0]["local_consumer"]["canonical_id"] != rows[1]["local_consumer"]["canonical_id"]
report = {"source_commit": COMMIT, "profile_sha256": hashlib.sha256(raw).hexdigest(),
          "scope": __doc__, "virtual_root": policy["virtual_root"],
          "all_non_path_registry_inputs_equal": True,
          "registry_incoming_metadata_equal": True,
          "registry_canonical_identity_equal": False, "local_consumer_metadata_equal": False,
          "cases": rows}
(OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({key: report[key] for key in ("registry_incoming_metadata_equal", "registry_canonical_identity_equal", "local_consumer_metadata_equal")}))
