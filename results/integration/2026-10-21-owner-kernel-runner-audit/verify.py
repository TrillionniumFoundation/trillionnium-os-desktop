"""Verify the retained source and job evidence without network access."""

import gzip
import hashlib
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent
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
        if len(entries) != 9226 or sum(row["type"] == "blob" for row in entries) != 7531:
            raise ValueError("full tree denominator mismatch")
        mapping = {row["path"]: row for row in entries}
        if len(mapping) != len(entries):
            raise ValueError("duplicate source tree path")
        trees.append(mapping)
    old, new = trees
    if set(old) != set(new):
        raise ValueError("unexpected added or removed source paths")
    changed = {
        path for path in old
        if old[path]["type"] == "blob" and old[path]["sha"] != new[path]["sha"]
    }
    differences = json.loads((root / "kernel/exact-tree-differences.json").read_text())
    if len(changed) != 12 or changed != {row["path"] for row in differences}:
        raise ValueError("source difference coverage mismatch")
    for row in differences:
        if (row["old"], row["new"]) != (old[row["path"]]["sha"], new[row["path"]]["sha"]):
            raise ValueError("changed source blob identity mismatch")
    assessment = json.loads((root / "kernel/assessment.json").read_text())
    if assessment["pr224_native_gate"]["conclusion"] != "failure":
        raise ValueError("failed owner evidence was lost")
    if assessment["pr225_native_gate"]["conclusion"] != "success":
        raise ValueError("qualified owner evidence was lost")
    jobs = json.loads((root / "desktop/run-39526325715-jobs.json").read_text())["jobs"]
    if len(jobs) != 1:
        raise ValueError("desktop job denominator differs")
    job = jobs[0]
    if (job["id"], job["status"], job["runner_id"], job["runner_name"], job["steps"]) != (
        118981704826, "queued", 0, "", []
    ):
        raise ValueError("desktop snapshot is not the retained queued job")
    print(f"Verified {len(files)} bounded artifacts; 9226 entries per tree, 12 file differences; desktop unassigned.")


if __name__ == "__main__":
    main()
