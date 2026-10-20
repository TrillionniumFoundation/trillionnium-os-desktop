#!/usr/bin/env python3
"""Verify host-only private debug SDK records without executing archived tools."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

def require(value, message):
    if not value:
        raise ValueError(message)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repo", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parent
expected = {}
for line in (root / "SHA256SUMS").read_text().splitlines():
    sha, name = line.split("  ", 1)
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and str(path) == name and name not in expected,
            "invalid checksum member")
    expected[name] = sha
actual = {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file() and path != root / "SHA256SUMS"}
require(actual == set(expected), "payload file set differs from checksum list")
for name, sha in expected.items():
    path = root / name
    require(not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == sha, "changed payload: " + name)
read = lambda name: json.loads((root / name).read_text())
manifest = read("manifest.json")
ready = read("logs/source-validation-ready.json")
require(ready["source_sha256"] == manifest["source_sha256"], "source receipt differs from manifest")
require(ready["status"] == "ready_after_independent_approval", "source validation is not ready")
for name, sha in manifest["source_sha256"].items():
    require(hashlib.sha256((root / "source/final" / name).read_bytes()).hexdigest() == sha, "archived source mismatch")
    if args.repo:
        raw = subprocess.check_output(["git", "-C", str(args.repo), "show", manifest["published_code_commit"] + ":" + name])
        require(hashlib.sha256(raw).hexdigest() == sha, "published source mismatch")
for result in ready["tests"]:
    log = root / "logs" / result["log"]
    require(hashlib.sha256(log.read_bytes()).hexdigest() == result["log_sha256"], "test log mismatch")
    require(result["tests"] == 16 and result["observed_tool_returncode"] == 0,
            "full debug host suite did not pass")
    require("Ran 16 tests" in log.read_text() and log.read_text().rstrip().endswith("OK"), "missing passing summary")
require([item["command"][1:-2] for item in ready["tests"]] == [["-I"], ["-I", "-O"]], "test modes differ")
require("FAILED (failures=4)" in (root / "logs/before-I.log").read_text(), "missing original negative control")
review = read("independent-review/review.json")
require(review["passed"] and all(review["checks"].values()), "independent review did not approve")
require({"support/build/debug/" + key: value for key, value in review["source_sha256"].items()} == manifest["source_sha256"],
        "independent review source differs")
archive = manifest["archive"]
raw = (root / archive["name"]).read_bytes()
require(len(raw) == archive["size"] and len(raw) <= 4 * 1024 * 1024, "archive size invalid")
require(hashlib.sha256(raw).hexdigest() == archive["sha256"], "archive hash invalid")
index = read("host-fixtures.index.json")["regular_files"]
require(len(index) == archive["regular_members"] and len(index) <= 2000, "archive member count invalid")
lookup = {row["name"]: row for row in index}
require(len(lookup) == len(index), "duplicate archive index entry")
payload = {}
with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as handle:
    members = handle.getmembers()
    require(len(members) == len(index), "archive member set invalid")
    require(sum(member.size for member in members) <= 8 * 1024 * 1024, "archive expansion exceeds host fixture limit")
    for member in members:
        path = PurePosixPath(member.name)
        require(member.isfile() and not member.sparse and not path.is_absolute() and ".." not in path.parts
                and str(path) == member.name and member.name in lookup and member.name not in payload,
                "invalid archive member")
        require(0 <= member.size <= 1024 * 1024 and member.size == lookup[member.name]["size"], "member size invalid")
        content = handle.extractfile(member).read()
        require(len(content) == member.size and hashlib.sha256(content).hexdigest() == lookup[member.name]["sha256"],
                "member hash invalid")
        payload[member.name] = content
require(set(payload) == set(lookup), "archive/index member names differ")
for group in ("owner/after-I", "owner/after-I-O", "independent/final/new-I", "independent/final/new-IO"):
    for case in ("global-missing", "global-foreign", "private-missing", "private-receipt-mismatch"):
        prefix = group + "/" + case
        observation = json.loads(payload[prefix + "/observation.json"])
        positive = case.startswith("global-")
        require(observation["returncode"] == (0 if positive else 1), "incorrect fixed-source case result")
        record = observation["installed_osdk"]
        require((record is not None) == positive, "private SDK record exists at wrong stage")
        if positive:
            binary = payload[prefix + "/debug-output/boot/osdk/bin/cargo-osdk"]
            receipt = payload[prefix + "/debug-output/boot/osdk/cargo-osdk.sha256"]
            require(record["path"] == observation["private_binary"], "recorded SDK path differs")
            require(record["sha256"] == hashlib.sha256(binary).hexdigest() and record["size"] == len(binary), "SDK bytes differ")
            require(record["matches_installation_receipt"] and record["installation_receipt"]["sha256"] == hashlib.sha256(receipt).hexdigest(),
                    "SDK receipt differs")
            require("cargo-home" not in json.dumps(record), "global SDK leaked into private record")
for group in ("owner/before-I", "independent/final/old-I", "independent/final/old-IO"):
    observations = {case: json.loads(payload[group + "/" + case + "/observation.json"])
                    for case in ("global-missing", "global-foreign", "private-missing", "private-receipt-mismatch")}
    require(observations["global-missing"]["returncode"] == 1, "old missing-global failure missing")
    require("cargo-home/bin/cargo-osdk" in observations["global-foreign"]["installed_osdk"]["path"], "old global misrecord missing")
    require(observations["private-missing"]["returncode"] == 0 and observations["private-receipt-mismatch"]["returncode"] == 0,
            "old bad-private false acceptances missing")
require(not manifest["actual_sdk_compilation"] and not manifest["actual_kernel_compilation"]
        and not manifest["actual_gdb_or_qemu_execution"] and not manifest["immutable_executed_sdk_custody_claimed"],
        "host phase scope broadened")
print(json.dumps({"evidence_integrity_passed": True, "source_commit": manifest["published_code_commit"],
                  "files": len(expected), "archive_members": len(index), "owner_suite_passes": 32,
                  "independent_focused_subset_repeats": 8, "scope": "host-only; no real SDK/Rust/GDB/QEMU"}, sort_keys=True))
