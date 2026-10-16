"""Reconstruct measured harnesses from retained Git commits into fresh scratch."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--repository", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
here = Path(__file__).resolve().parent
args.output.mkdir(parents=True, exist_ok=False)

for name in ("roles.py", "roles_patched.py", "run_probe.py", "run_patched_probe.py",
             "check_measurements.py", "check_patched_measurements.py"):
    shutil.copyfile(here / name, args.output / name)

for variant, provenance_file, commit in (
    ("harness", "source-provenance.json", "76eff6ea87242fedad781899146f96e397427f4e"),
    ("patched-harness", "patched-source-provenance.json", "fb81fec167913827bcddfda15676dc6b26f35965"),
):
    root = args.output / variant
    (root / "src/daemon").mkdir(parents=True)
    for rel in ("Cargo.toml", "Cargo.lock", "src/main.rs"):
        shutil.copyfile(here / variant / rel, root / rel)
    metadata = json.loads((here / provenance_file).read_text())
    for path in metadata["copied_production_files_sha256"]:
        rel = path.split("/osdk/src/", 1)[1]
        content = subprocess.check_output(["git", "show", commit + ":" + path], cwd=args.repository)
        (root / "src" / rel).write_bytes(content)
    if variant == "patched-harness":
        # Final commit added only the documented SIGCHLD/no-auto-reap comment.
        # Restore the exact pre-comment bytes used for these measurements.
        subprocess.run(
            ["patch", "--batch", "--reverse", "-p1", "--directory", str(root / "src")],
            stdin=(here / "patched-to-committed.diff").open("rb"), check=True,
        )
    for path, expected in metadata["copied_production_files_sha256"].items():
        rel = path.split("/osdk/src/", 1)[1]
        assert hashlib.sha256((root / "src" / rel).read_bytes()).hexdigest() == expected, path
print("Both measured source freezes reconstructed and SHA256 verified.")
