"""Verify the retained source and job evidence without network access."""

import gzip
import hashlib
import json
from pathlib import Path
import re


def one(items, description):
    if len(items) != 1:
        raise ValueError(f"expected exactly one {description}")
    return items[0]


def verify_native_log(raw, head, gate, artifact_bytes):
    # Keep only actual timestamped output. In particular, colored command
    # echoes containing JSON are not structured command results.
    lines = [
        match[1]
        for line in raw.decode("utf-8").splitlines()
        if (match := re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z (.*)", line))
    ]
    checked_out = [
        lines[index + 1]
        for index, line in enumerate(lines[:-1])
        if line == "[command]/usr/bin/git log -1 --format=%H"
    ]
    if checked_out != [head]:
        raise ValueError("native log candidate checkout identity mismatch")
    run, artifact = gate["run_id"], gate["artifact_id"]
    expected_uploads = [
        f"Artifact a06-exact-kernel-ktest-{run}.zip successfully finalized. Artifact ID {artifact}",
        f"Artifact a06-exact-kernel-ktest-{run} has been successfully uploaded! Final size is {artifact_bytes} bytes. Artifact ID is {artifact}",
        "Artifact download URL: https://github.com/TrillionniumFoundation/"
        f"trillionnium-os-desktop/actions/runs/{run}/artifacts/{artifact}",
    ]
    uploads = [
        line
        for line in lines
        if line.startswith(
            ("Artifact a06-exact-kernel-ktest-", "Artifact download URL:")
        )
    ]
    if uploads != expected_uploads:
        raise ValueError("native log run/artifact identity mismatch")
    if (
        lines.count(
            "PASS: real kernel-mode tests; evidence: /home/runner/work/_temp/a06-ktest"
        )
        != 1
    ):
        raise ValueError("native kernel completion marker missing or duplicated")
    records = []
    for line in lines:
        if line.startswith("{"):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue  # Multi-line diagnostic output is not a verdict.
            if isinstance(record, dict):
                records.append(record)
    candidates = [record for record in records if "candidate_head" in record]
    if len(candidates) != 8 or any(
        record["candidate_head"] != head for record in candidates
    ):
        raise ValueError("native log structured candidate identity mismatch")
    owners = [
        record
        for record in records
        if record.get("schema") == "a06.cpu-owner-negative.v1"
    ]
    if len(owners) != 7 or any(
        record.get("passed") is not True
        or record.get("negative_control_detected") is not True
        or record.get("total_core_tests") != 262
        for record in owners
    ):
        raise ValueError("native core negative-control markers mismatch")
    smp = one(
        [
            record
            for record in records
            if record.get("schema") == "a06.permission-attr-smp.v1"
        ],
        "SMP record",
    )
    if smp.get("passed") is not True or smp.get("positive", {}).get("declared") != 265:
        raise ValueError("native compiled SMP denominator mismatch")
    guest = one(
        [
            record
            for record in records
            if isinstance(record.get("verdict"), dict)
            and record["verdict"].get("guest") is True
            and record["verdict"].get("negative_control") is False
        ],
        "guest verdict",
    )
    verdict = guest["verdict"]
    passed = gate["conclusion"] == "success"
    cases = ["root_mode", "file_mode", "directory_mode", "exec_normal", "exec_nnp"]
    observations = verdict.get("observations", {})
    if (
        guest.get("passed") is not passed
        or verdict.get("passed") is not passed
        or verdict.get("expected_cases") != cases
        or observations.get("complete") != {"total": 5, "passed": 5, "failed": 0}
        or any(
            observations.get(case + "_case", {}).get("result") != "PASS"
            for case in cases
        )
        or verdict.get("failed_conditions") != gate.get("observed_failures", [])
    ):
        raise ValueError("native guest failure/success markers mismatch")
    errors = [line for line in lines if line.startswith("##[error]")]
    if errors != ([] if passed else ["##[error]Process completed with exit code 1."]):
        raise ValueError("native command failure marker mismatch")
    mutations = [
        record
        for record in records
        if record.get("schema") == "a06.exfat-one-line-negative.v1"
    ]
    if not passed and mutations:
        raise ValueError(
            "failed owner unexpectedly claims production mutation completion"
        )
    if passed:
        mutation = one(mutations, "production mutation result")
        if (
            mutation.get("passed") is not True
            or mutation.get("positive_source_head") != head
            or mutation.get("negative_parent") != head
            or mutation.get("mutation_path")
            != "kernel/asterinas/kernel/core/src/fs/fs_impls/exfat/inode.rs"
            or mutation.get("negative_source_inputs_unchanged") is not True
            or mutation.get("positive_source_inputs_unchanged") is not True
        ):
            raise ValueError("native production mutation identity/result mismatch")


def main(root=None):
    root = Path(__file__).resolve().parent if root is None else Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    files = manifest["files"]
    actual = {
        str(path.relative_to(root))
        for path in root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual != set(files):
        raise ValueError("retained file inventory differs from manifest")
    for name, expected in files.items():
        data = (root / name).read_bytes()
        if len(data) != expected["bytes"] or len(data) >= 400 * 1024:
            raise ValueError(f"file size mismatch: {name}")
        if hashlib.sha256(data).hexdigest() != expected["sha256"]:
            raise ValueError(f"file checksum mismatch: {name}")
        if name.endswith(".gz"):
            decoded = gzip.decompress(data)
            if len(decoded) != expected["uncompressed_bytes"]:
                raise ValueError(f"uncompressed size mismatch: {name}")
            if hashlib.sha256(decoded).hexdigest() != expected["uncompressed_sha256"]:
                raise ValueError(f"uncompressed checksum mismatch: {name}")
    trees = []
    for number, commit in manifest["tree_commits"].items():
        path = root / "kernel" / f"pr{number}-complete-tree.json.gz"
        tree = json.loads(gzip.decompress(path.read_bytes()))
        if tree["sha"] != commit or tree["truncated"] is not False:
            raise ValueError("tree identity or completeness mismatch")
        entries = tree["tree"]
        if (
            len(entries) != 9226
            or sum(row["type"] == "blob" for row in entries) != 7531
        ):
            raise ValueError("full tree denominator mismatch")
        mapping = {row["path"]: row for row in entries}
        if len(mapping) != len(entries):
            raise ValueError("duplicate source tree path")
        trees.append(mapping)
    old, new = trees
    if set(old) != set(new):
        raise ValueError("unexpected added or removed source paths")
    changed = {
        path
        for path in old
        if old[path]["type"] == "blob" and old[path]["sha"] != new[path]["sha"]
    }
    differences = json.loads((root / "kernel/exact-tree-differences.json").read_text())
    if len(changed) != 12 or changed != {row["path"] for row in differences}:
        raise ValueError("source difference coverage mismatch")
    for row in differences:
        if (row["old"], row["new"]) != (
            old[row["path"]]["sha"],
            new[row["path"]]["sha"],
        ):
            raise ValueError("changed source blob identity mismatch")
    assessment = json.loads((root / "kernel/assessment.json").read_text())
    if assessment["pr224_native_gate"]["conclusion"] != "failure":
        raise ValueError("failed owner evidence was lost")
    if assessment["pr225_native_gate"]["conclusion"] != "success":
        raise ValueError("qualified owner evidence was lost")
    if (assessment["old_head"], assessment["qualified_head"]) != (
        manifest["tree_commits"]["224"],
        manifest["tree_commits"]["225"],
    ):
        raise ValueError("assessment source identity mismatch")
    for number, job_id, artifact_bytes in (
        (224, 118984639491, 191206920),
        (225, 119118562629, 206210111),
    ):
        gate = assessment[f"pr{number}_native_gate"]
        if (
            gate["job_id"] != job_id
            or gate.get("artifact_bytes", artifact_bytes) != artifact_bytes
        ):
            raise ValueError("native job/artifact metadata mismatch")
        log = root / "kernel" / f"pr{number}-kernel-job-{job_id}.log.gz"
        verify_native_log(
            gzip.decompress(log.read_bytes()),
            manifest["tree_commits"][str(number)],
            gate,
            artifact_bytes,
        )
    jobs = json.loads((root / "desktop/run-39526325715-jobs.json").read_text())["jobs"]
    if len(jobs) != 1:
        raise ValueError("desktop job denominator differs")
    job = jobs[0]
    if (
        job["id"],
        job["status"],
        job["runner_id"],
        job["runner_name"],
        job["steps"],
    ) != (118981704826, "queued", 0, "", []):
        raise ValueError("desktop snapshot is not the retained queued job")
    print(
        f"Verified {len(files)} bounded artifacts; 9226 entries per tree, 12 file differences; both native log identities/results; desktop unassigned."
    )


if __name__ == "__main__":
    main()
