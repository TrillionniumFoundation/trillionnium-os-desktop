#!/usr/bin/env python3
"""Rebuild the admitted Pocket4 initramfs AppArmor input from installed Ubuntu profiles."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent

def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((HERE / "pocket4-board-inputs.lock.json").read_text())
    expected = lock["files"]["ubuntu-apparmor.profiles"]
    profile_root = Path("/etc/apparmor.d")
    compiler = Path("/usr/sbin/apparmor_parser")
    features = HERE / lock["kernel"]["apparmor_features"]
    if digest(features) != lock["kernel"]["apparmor_features_sha256"] or digest(compiler) != expected["parser_sha256"]:
        raise ValueError("The target kernel features or installed Ubuntu AppArmor parser differ from the product inputs")
    backups = (".dpkg-new", ".dpkg-old", ".dpkg-dist", ".dpkg-bak", ".orig", ".rej", ".pacnew", ".pacsave", "~")
    sources = [p for p in sorted(profile_root.iterdir()) if p.is_file() and not p.name.startswith(".")
               and not p.name.endswith(backups) and not (profile_root / "disable" / p.name).is_symlink()]
    if len(sources) != expected["active_sources"]:
        raise ValueError("The number of active Ubuntu profile sources differs from the product admission")
    with tempfile.TemporaryDirectory(dir=args.output.parent) as temporary:
        work = Path(temporary)
        def compile_profile(source):
            output = work / (source.name + ".bin")
            command = [str(compiler), "-Q", "-K", "--kernel-features", str(features), "-o", str(output), str(source)]
            if (profile_root / "force-complain" / source.name).exists():
                command.insert(1, "-C")
            subprocess.run(command, check=True)
            return output.read_bytes()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as workers:
            profiles = workers.map(compile_profile, sources)
            result = work / "ubuntu-apparmor.profiles"
            with result.open("xb") as target:
                target.write(b"DLAA0001" + struct.pack("<I", len(sources)))
                for profile in profiles:
                    target.write(struct.pack("<I", len(profile)))
                    target.write(profile)
        if result.stat().st_size != expected["size"] or digest(result) != expected["sha256"]:
            raise ValueError("Compiled Ubuntu profiles differ from the admitted product bytes")
        os.link(result, args.output)

if __name__ == "__main__":
    main()
