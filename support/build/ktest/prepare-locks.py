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
SEED_TREE = "96605cf64aeae2d34f29b97e85eff9315fe10a8e"
SEED_BLOB = "77d8f4be4cdc7365cd73a2e9f7638d46f3608b40"
SEED_SHA256 = "6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316"
CRATES = {"ostd": "ostd", "aster-core": "kernel/core"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def original_seed(upstream):
    """Use the fixed upstream Git object, never the derived working root lock."""
    blob = subprocess.check_output(
        ["git", "rev-parse", f"{SEED_TREE}:Cargo.lock"], cwd=upstream, text=True
    ).strip()
    if blob != SEED_BLOB:
        raise SystemExit("fixed upstream tree root-lock blob changed")
    seed_bytes = subprocess.check_output(["git", "cat-file", "blob", SEED_BLOB], cwd=upstream)
    if hashlib.sha256(seed_bytes).hexdigest() != SEED_SHA256:
        raise SystemExit("original upstream root lock seed differs from the fixed v0.19.0 input")
    return seed_bytes


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
        forwarded = values if name == "default" else [crate + "/" + name]
        if crate == "aster-core" and name == "permission-attr-smp-ktest":
            forwarded.append("osdk-test-kernel/external-entry")
        text.append(f'{name} = {atom(forwarded)}')
    return '\n'.join(text) + '\n'


def checked_cargo(command, *, cwd, label):
    """Preserve Cargo stderr when a cold-runner preflight fails."""
    try:
        result = subprocess.run(command, cwd=cwd, check=False,
                                capture_output=True, text=True)
    except OSError as error:
        raise SystemExit(f"{label}: cannot start Cargo: {error}") from error
    if result.returncode:
        stdout = (result.stdout or "")[-8192:]
        stderr = (result.stderr or "")[-16384:]
        raise SystemExit(
            f"{label}: Cargo exit {result.returncode}, command={command!r}\n"
            f"stdout (last 8192 chars):\n{stdout}\n"
            f"stderr (last 16384 chars):\n{stderr}"
        )
    return result


def package_key(package):
    return (package["name"], package["version"], package.get("source", ""), package.get("checksum", ""))


def audit_packages(packages, seed_set, crate):
    """Permit the OSDK base plus one exact local G1-a package, no external drift."""
    expected = [(f"{crate}-osdk-bin", "0.1.0" if crate == "aster-core" else "0.19.0", "", "")]
    if crate == "aster-core":
        expected.append(("os-control", "0.1.0", "", ""))
        native = [p for p in packages if p["name"] == "os-control"]
        if native != [{"name": "os-control", "version": "0.1.0", "dependencies": ["spin"]}]:
            raise SystemExit("aster-core: expected only the local os-control package and pinned spin")
        core = next(p for p in packages if p["name"] == "aster-core")
        if core.get("dependencies", []).count("os-control") != 1:
            raise SystemExit("aster-core: missing its sole local os-control dependency")
    added = sorted({package_key(p) for p in packages} - seed_set)
    if added != sorted(expected):
        raise SystemExit(f"{crate}: dependency drift from fixed upstream: {added!r}")
    return expected


def audit_native_metadata(metadata, upstream, crate):
    native = [p for p in metadata["packages"] if p["name"] == "os-control"]
    if crate != "aster-core":
        if native:
            raise SystemExit("ostd must not resolve os-control")
        return
    manifest = (upstream.parents[1] / "libs/os-control/Cargo.toml").resolve()
    if len(native) != 1 or native[0]["source"] is not None or Path(native[0]["manifest_path"]).resolve() != manifest:
        raise SystemExit("aster-core: os-control must resolve from this checkout's libs/os-control")
    node = next(n for n in metadata["resolve"]["nodes"] if n["id"] == native[0]["id"])
    if node["features"] != ["portable-spin"]:
        raise SystemExit(f"aster-core: unexpected os-control features: {node['features']!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    here = Path(__file__).resolve().parent
    parser.add_argument("--upstream", type=Path, default=here.parents[2] / "kernel/asterinas")
    parser.add_argument("--output-dir", type=Path, default=here / "locks")
    parser.add_argument("--crate", choices=CRATES, action="append")
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    seed_bytes = original_seed(upstream)
    seed_packages = tomllib.loads(seed_bytes.decode())["package"]
    seed_set = {package_key(p) for p in seed_packages}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for crate in args.crate or CRATES:
        manifest = generated_manifest(upstream, crate)
        with tempfile.TemporaryDirectory(prefix=f"a01-ktest-{crate}-lock-") as temporary:
            work = Path(temporary)
            (work / "Cargo.toml").write_text(manifest)
            (work / "src").mkdir()
            (work / "src/main.rs").write_text("#![no_std]\n#![no_main]\n")
            # The original Git seed stays fixed. The working root lock is an
            # explicit local derivative, not the source of this normalization.
            # Fetch only the audited test graph here, with Cargo still --locked.
            bootstrap = (here / "locks" / f"{crate}.Cargo.lock").read_bytes()
            audit_packages(tomllib.loads(bootstrap.decode())["package"], seed_set, crate)
            (work / "Cargo.lock").write_bytes(bootstrap)
            prefetch = ["cargo", f"+{TOOLCHAIN}", "fetch", "--locked"]
            checked_cargo(prefetch, cwd=work, label=f"{crate} prefetch audited derived lock")
            if (work / "Cargo.lock").read_bytes() != bootstrap:
                raise SystemExit(f"{crate}: locked prefetch changed its input lock")
            (work / "Cargo.lock").write_bytes(seed_bytes)
            command = ["cargo", f"+{TOOLCHAIN}", "metadata", "--offline",
                       "--format-version", "1", "--filter-platform", "x86_64-unknown-none"]
            result = checked_cargo(command, cwd=work,
                                   label=f"{crate} offline metadata normalization")
            locked = checked_cargo([*command, "--locked"], cwd=work,
                                   label=f"{crate} locked offline metadata audit")
            normalized = (work / "Cargo.lock").read_bytes()
            packages = tomllib.loads(normalized.decode())["package"]
            expected = audit_packages(packages, seed_set, crate)
            metadata = json.loads(locked.stdout)
            audit_native_metadata(metadata, upstream, crate)
            output = args.output_dir / f"{crate}.Cargo.lock"
            output.write_bytes(normalized)
            report = {"schema": 3, "crate": crate, "toolchain": TOOLCHAIN,
                      "seed_tree": SEED_TREE, "seed_blob": SEED_BLOB,
                      "seed_sha256": hashlib.sha256(seed_bytes).hexdigest(),
                      "working_root_lock_sha256": digest(upstream / "Cargo.lock"),
                      "normalized_sha256": digest(output),
                      "seed_package_count": len(seed_packages), "package_count": len(packages),
                      "added_local_package": expected[0][0], "external_drift": [],
                      "added_local_packages": [p[0] for p in expected],
                      "prefetch_lock_sha256": hashlib.sha256(bootstrap).hexdigest(),
                      "metadata_exit": result.returncode, "locked_metadata_exit": locked.returncode,
                      "commands": [prefetch, command, [*command, "--locked"]],
                      "generated_manifest": manifest.replace(str(upstream), "${ASTERINAS}"),
                      "resolved_features": {node["id"].replace(str(upstream), "${ASTERINAS}").replace(str(upstream.parents[1]), "${PROJECT}").replace(str(work), "${TEST_BASE}"): node["features"]
                                            for node in metadata["resolve"]["nodes"]},
                      "generator_inputs_sha256": {name: digest(upstream / name) for name in
                          ("osdk/src/base_crate/mod.rs", "osdk/src/base_crate/Cargo.toml.template",
                           "osdk/src/commands/test.rs", "Cargo.toml", f"{CRATES[crate]}/Cargo.toml")}}
            (args.output_dir / f"{crate}.json").write_text(json.dumps(report, indent=2) + "\n")
            print(f"{crate}: {len(packages)} packages, sha256={digest(output)}, no external drift")


if __name__ == "__main__":
    main()
