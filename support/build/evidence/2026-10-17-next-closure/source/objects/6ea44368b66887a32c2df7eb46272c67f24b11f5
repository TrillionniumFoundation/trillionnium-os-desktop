#!/usr/bin/env python3
"""Normalize each OSDK test-base lock from the fixed complete upstream lock."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

TOOLCHAIN = "nightly-2026-07-21"
SEED_SHA256 = "6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316"
CRATES = {"ostd": "ostd", "aster-core": "kernel/core"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atom(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    return json.dumps(value)


def generated_manifest(upstream, crate):
    """Mirror the pinned OSDK new_base_crate(..., Test, ..., true) manifest.

    This is preparation only: execution still uses the real upstream generator.
    In particular its final unconditional ostd dependency replaces the target
    dependency when testing ostd itself, including the default-features flag.
    """
    root = tomllib.loads((upstream / "Cargo.toml").read_text())
    target = tomllib.loads((upstream / CRATES[crate] / "Cargo.toml").read_text())
    package = target["package"]
    version = package["version"]
    if isinstance(version, dict):
        version = root["workspace"]["package"]["version"]
    text = ['[workspace]', '', '[package]', f'name = "{crate}-osdk-bin"',
            f'version = "{version}"', 'edition = "2024"', '']
    dependencies = {crate: {"path": str(upstream / CRATES[crate]), "default-features": False}}
    for name, relative in (("osdk-test-kernel", "osdk/deps/test-kernel"),
                           ("osdk-frame-allocator", "osdk/deps/frame-allocator"),
                           ("osdk-heap-allocator", "osdk/deps/heap-allocator"),
                           ("ostd", "ostd")):
        dependencies[name] = {"path": str(upstream / relative)}
    for name, values in dependencies.items():
        text.append(f'[dependencies.{name}]')
        text.extend(f'{key} = {atom(value)}' for key, value in values.items())
        text.append('')
    for name, values in root.get("profile", {}).items():
        text.append(f'[profile.{name}]')
        text.extend(f'{key} = {atom(value)}' for key, value in values.items())
        text.append('')
    text.append('[features]')
    for name, values in target.get("features", {}).items():
        text.append(f'{name} = {atom(values if name == "default" else [crate + "/" + name])}')
    return '\n'.join(text) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument("--upstream", type=Path, default=here.parents[2] / "kernel/asterinas")
    parser.add_argument("--output-dir", type=Path, default=here / "locks")
    parser.add_argument("--crate", choices=CRATES, action="append")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    seed = upstream / "Cargo.lock"
    seed_bytes = seed.read_bytes()
    if hashlib.sha256(seed_bytes).hexdigest() != SEED_SHA256:
        raise SystemExit("upstream root lock differs from the fixed v0.19.0 input")
    seed_packages = tomllib.loads(seed_bytes.decode())["package"]
    key = lambda p: (p["name"], p["version"], p.get("source", ""), p.get("checksum", ""))
    seed_set = {key(p) for p in seed_packages}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for crate in args.crate or CRATES:
        manifest = generated_manifest(upstream, crate)
        with tempfile.TemporaryDirectory(prefix=f"a01-ktest-{crate}-lock-") as temporary:
            work = Path(temporary)
            (work / "Cargo.toml").write_text(manifest)
            (work / "src").mkdir()
            (work / "src/main.rs").write_text("#![no_std]\n#![no_main]\n")
            (work / "Cargo.lock").write_bytes(seed_bytes)
            command = ["cargo", f"+{TOOLCHAIN}", "metadata", "--offline",
                       "--format-version", "1", "--filter-platform", "x86_64-unknown-none"]
            result = subprocess.run(command, cwd=work, check=True, capture_output=True, text=True)
            locked = subprocess.run([*command, "--locked"], cwd=work, check=True,
                                    capture_output=True, text=True)
            normalized = (work / "Cargo.lock").read_bytes()
            packages = tomllib.loads(normalized.decode())["package"]
            added = sorted({key(p) for p in packages} - seed_set)
            expected = [(f"{crate}-osdk-bin", next(p["version"] for p in packages
                                                 if p["name"] == f"{crate}-osdk-bin"), "", "")]
            if added != expected:
                raise SystemExit(f"{crate}: dependency drift from fixed upstream: {added!r}")
            output = args.output_dir / f"{crate}.Cargo.lock"
            output.write_bytes(normalized)
            metadata = json.loads(result.stdout)
            report = {"schema": 1, "crate": crate, "toolchain": TOOLCHAIN,
                      "seed_sha256": digest(seed), "normalized_sha256": digest(output),
                      "seed_package_count": len(seed_packages), "package_count": len(packages),
                      "added_local_package": expected[0][0], "external_drift": [],
                      "metadata_exit": result.returncode, "locked_metadata_exit": locked.returncode,
                      "commands": [command, [*command, "--locked"]],
                      "generated_manifest": manifest.replace(str(upstream), "${ASTERINAS}"),
                      "resolved_features": {node["id"].replace(str(upstream), "${ASTERINAS}").replace(str(work), "${TEST_BASE}"): node["features"]
                                            for node in metadata["resolve"]["nodes"]},
                      "generator_inputs_sha256": {name: digest(upstream / name) for name in
                          ("osdk/src/base_crate/mod.rs", "osdk/src/base_crate/Cargo.toml.template",
                           "osdk/src/commands/test.rs", "Cargo.toml", f"{CRATES[crate]}/Cargo.toml")}}
            (args.output_dir / f"{crate}.json").write_text(json.dumps(report, indent=2) + "\n")
            print(f"{crate}: {len(packages)} packages, sha256={digest(output)}, no external drift")


if __name__ == "__main__":
    main()
