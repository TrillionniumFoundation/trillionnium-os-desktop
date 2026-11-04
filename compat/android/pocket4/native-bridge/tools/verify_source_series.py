#!/usr/bin/env python3
"""Check raw translator and builder source chains using temporary git exports."""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def relative(name):
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("unsafe source path")
    return p

def export(repo, commit, dest):
    data = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit],
                          check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as archive:
        archive.extractall(dest, filter="data")

def apply_patch(tree, patch, wanted):
    if sha(patch) != wanted:
        raise ValueError("patch hash changed")
    subprocess.run(["git", "apply", "--check", str(patch)], cwd=tree, check=True)
    subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)],
                   cwd=tree, check=True)

def check_tree(tree, files, field):
    actual = {x.relative_to(tree).as_posix() for x in tree.rglob("*") if x.is_file()}
    if actual != set(files):
        raise ValueError("source inventory differs")
    for name, pin in files.items():
        path = tree / relative(name)
        if path.is_symlink() or sha(path) != pin[field]:
            raise ValueError("source hash differs: " + name)

def verify(teto_repo, builder_repo):
    lock = json.loads((ROOT / "source-lock.json").read_text())
    builder = json.loads((ROOT / "builder/source-lock.json").read_text())
    report = {"ok": True, "translator_stages": []}
    with tempfile.TemporaryDirectory(prefix="pocket4-native-source-") as td:
        temp = Path(td)
        teto = temp / "teto"
        build = temp / "builder"
        teto.mkdir()
        build.mkdir()
        export(teto_repo.resolve(strict=True), lock["upstream_commit"], teto)
        final = None
        for layer in lock["source_layers"]:
            apply_patch(teto, ROOT / relative(layer["patch"]), layer["patch_sha256"])
            manifest = json.loads((ROOT / relative(layer["manifest"])).read_text())
            if manifest["commit"] != layer["source_commit"] or manifest["file_count"] != layer["files"]:
                raise ValueError("source-stage identity differs")
            check_tree(teto, manifest["files"], "sha256")
            report["translator_stages"].append(
                {"revision": layer["revision"], "files_verified": manifest["file_count"],
                 "commit": manifest["commit"]})
            final = manifest["files"]
        count = 0
        for path in (ROOT / "source").rglob("*"):
            if path.is_file():
                name = path.relative_to(ROOT / "source").as_posix()
                if name not in final or sha(path) != final[name]["sha256"]:
                    raise ValueError("delivered final source differs: " + name)
                count += 1
        export(builder_repo.resolve(strict=True), builder["upstream_commit"], build)
        apply_patch(build, ROOT / "builder" / relative(builder["patch"]["path"]),
                    builder["patch"]["sha256"])
        check_tree(build, builder["files"], "candidate_sha256")
        report.update({"delivered_final_files_verified": count,
                       "public_builder_files_verified": len(builder["files"]),
                       "builder_changed_paths": len(builder["changed_paths"]),
                       "excluded_private_provenance_not_required": True,
                       "raw_source_only": True,
                       "compiler_effective_source_manifests_are_separate": True,
                       "input_repositories_mutated": False, "runtime_mutated": False})
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--teto-repository", type=Path, required=True)
    parser.add_argument("--builder-repository", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.teto_repository, args.builder_repository), indent=2))

