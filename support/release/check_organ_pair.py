#!/usr/bin/env python3
"""Verify one reviewed source pair, then optionally build and test its host lane."""

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

SPEC = importlib.util.spec_from_file_location(
    "organ_release_profile", Path(__file__).with_name("organ_release_profile.py"))
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


def host_product_specs(targets, hepta_profile):
    """Exactly the original V5 products; neither a manifest nor a cache receipt selects them."""
    if hepta_profile not in ("dev", "dev-small"):
        raise profile.ProfileError("unsupported host product profile")
    products = (
        ("trill-ctl", "desktop", "ui-build"),
        ("trill-session", "desktop", "ui-build"),
        ("trill-shell", "desktop", "ui-build"),
        ("trill-app-window", "desktop", "ui-build"),
        ("codex-hepta-agentd", "hepta", "hepta-build"),
        ("codex", "hepta", "hepta-build"),
        ("hepta-authority-host", "hepta", "hepta-root-build"),
        ("hepta-supervisor-intent-recovery", "hepta", "hepta-recovery-build"),
    )
    result = []
    for name, side, stage in products:
        directory = "debug" if side == "desktop" or hepta_profile == "dev" else "dev-small"
        target = Path(targets[side])
        result.append({"name": name, "side": side, "stage": stage,
                       "toolchain": "1.88.0" if side == "desktop" else "1.95.0",
                       "cargo_profile": "dev" if side == "desktop" else hepta_profile,
                       "cargo_target_dir": str(target), "profile_directory": directory,
                       "path": str(target / directory / name)})
    return result


def _product_deadline(deadline):
    if time.monotonic() >= deadline:
        raise profile.ProfileError("host product proof exceeds the final step budget")


def _product_signature(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)


def _directory_identity(fd):
    value = os.fstat(fd)
    if not stat.S_ISDIR(value.st_mode):
        raise profile.ProfileError("host product ancestor is not a directory")
    # Directory mtime/ctime change when this runner writes its own receipt/logs.
    return value.st_dev, value.st_ino, value.st_mode


def _close_product_chain(chain):
    for fd in reversed(chain):
        os.close(fd)


def _open_product_chain(path):
    path = Path(path)
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not path.is_absolute() or ".." in path.parts):
        raise profile.ProfileError("host ELF proof requires absolute descriptor-relative nofollow paths")
    chain = []
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        chain.append(os.open(path.anchor, flags))
        for component in path.parts[1:-1]:
            chain.append(os.open(component, flags, dir_fd=chain[-1]))
        # A FIFO/device must not block before fstat can reject its type.
        chain.append(os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                             | os.O_CLOEXEC, dir_fd=chain[-1]))
        return chain
    except BaseException:
        _close_product_chain(chain)
        raise


def _read_host_product(spec, chain, deadline):
    _product_deadline(deadline)
    fd = chain[-1]
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode) or not before.st_mode & stat.S_IXUSR:
        raise profile.ProfileError(f"host product is not a regular owner-executable ELF: {spec['name']}")
    named = os.stat(Path(spec["path"]).name, dir_fd=chain[-2], follow_symlinks=False)
    if _product_signature(named) != _product_signature(before):
        raise profile.ProfileError(f"host product path changed before hashing: {spec['name']}")
    os.lseek(fd, 0, os.SEEK_SET)
    digest, magic, remaining = hashlib.sha256(), b"", before.st_size
    # Read exactly the observed file size plus EOF; growth cannot create an
    # unbounded stream. Synchronous local reads can still block in the kernel.
    while remaining:
        _product_deadline(deadline)
        block = os.read(fd, min(1024 * 1024, remaining))
        if not block:
            raise profile.ProfileError(f"host product shortened during hashing: {spec['name']}")
        magic += block[:max(0, 4 - len(magic))]
        digest.update(block)
        remaining -= len(block)
    if os.read(fd, 1) or magic != b"\x7fELF":
        raise profile.ProfileError(f"host product is not a complete stable ELF: {spec['name']}")
    after = os.fstat(fd)
    named = os.stat(Path(spec["path"]).name, dir_fd=chain[-2], follow_symlinks=False)
    if _product_signature(before) != _product_signature(after) or _product_signature(named) != _product_signature(after):
        raise profile.ProfileError(f"host product bytes/stat/path changed during hashing: {spec['name']}")
    _product_deadline(deadline)
    return dict(spec, sha256=digest.hexdigest(), bytes=before.st_size,
                mode=oct(stat.S_IMODE(before.st_mode)), magic_hex=magic.hex(),
                identity={"device": before.st_dev, "inode": before.st_ino,
                          "uid": before.st_uid, "gid": before.st_gid,
                          "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns,
                          "nlink": before.st_nlink})


class HostProductSeal:
    """Retain the actual eight ELF descriptors across the final source recheck."""

    def __init__(self, targets, hepta_profile, deadline):
        self.bindings, self.records, self.deadline = [], [], deadline
        try:
            for spec in host_product_specs(targets, hepta_profile):
                _product_deadline(deadline)
                chain = _open_product_chain(spec["path"])
                try:
                    ancestors = tuple(_directory_identity(fd) for fd in chain[:-1])
                except BaseException:
                    _close_product_chain(chain)
                    raise
                self.bindings.append((spec, chain, ancestors))
                self.records.append(_read_host_product(spec, chain, deadline))
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def verify(self):
        actual = []
        for spec, chain, ancestors in self.bindings:
            self._check_binding(spec, chain, ancestors)
            actual.append(_read_host_product(spec, chain, self.deadline))
            self._check_binding(spec, chain, ancestors)
        if actual != self.records:
            raise profile.ProfileError("host product identity changed across source verification")
        return actual

    def _check_binding(self, spec, chain, ancestors):
        _product_deadline(self.deadline)
        fresh = _open_product_chain(spec["path"])
        try:
            if (tuple(_directory_identity(fd) for fd in fresh[:-1]) != ancestors
                    or tuple(_directory_identity(fd) for fd in chain[:-1]) != ancestors
                    or _product_signature(os.fstat(fresh[-1])) != _product_signature(os.fstat(chain[-1]))):
                raise profile.ProfileError(f"host product path/ancestor replaced: {spec['name']}")
        finally:
            _close_product_chain(fresh)

    def close(self):
        for _, chain, _ in reversed(self.bindings):
            _close_product_chain(chain)
        self.bindings.clear()

    def __exit__(self, *_):
        self.close()


def host_steps(os_root, hepta_root, offline, hepta_profile="dev-small", schema_version=1):
    """Commands are code-owned; a manifest cannot inject an executable or flags."""
    network = ["--offline"] if offline else []
    owning_packages = ["codex-hepta-agentd", "codex-hepta-memory", "codex-hepta-cognitive-store"]
    if schema_version in (3, 4, 5):
        owning_packages += ["codex-hepta-contracts", "codex-state",
                            "codex-hepta-agent-protocol", "codex-hepta-learning-ledger",
                            "codex-git-utils", "codex-hepta-memory-extension",
                            "codex-hepta-automation", "codex-hepta-fleet", "codex-hepta-supervisor",
                            "codex-arg0"]
    if schema_version in (4, 5):
        owning_packages += ["codex-app-server-protocol", "codex-thread-store", "codex-core-plugins",
                            "codex-rollout", "codex-file-system"]
    if schema_version == 5:
        owning_packages.append("codex-rmcp-client")
    hepta_build_targets = ["-p", "codex-hepta-agentd", "--bin", "codex-hepta-agentd"]
    if schema_version == 5:
        # The original RMCP remote tests execute the real `codex exec-server`.
        # Cargo does not build this other package's binary as a test dependency.
        hepta_build_targets += ["-p", "codex-cli", "--bin", "codex"]
    package_flags = [flag for package in owning_packages for flag in ("-p", package)]
    steps = [
        ("ui-build", os_root, "1.88.0",
         ["cargo", "build", "--manifest-path", "ui/Cargo.toml", "--workspace",
          "--bins", "--locked", *network]),
        ("ui-tests", os_root, "1.88.0",
         ["cargo", "test", "--manifest-path", "ui/Cargo.toml", "--workspace",
          "--locked", *network]),
        ("adapter-tests", os_root, "1.88.0",
         ["cargo", "test", "--manifest-path", "services/hepta-os/Cargo.toml",
          "--features", "cpu-history", "--locked", *network]),
        ("hepta-build", hepta_root, "1.95.0",
         ["cargo", "build", "--manifest-path", "codex-rs/Cargo.toml",
          *hepta_build_targets,
          "--profile", hepta_profile, "--locked", *network]),
        ("hepta-tests", hepta_root, "1.95.0",
         ["just", "test", "--locked", *network, *package_flags,
          "--test-threads", "2", "--retries", "0", "--cargo-profile", hepta_profile]),
    ]
    if schema_version in (3, 4, 5):
        steps.insert(4, ("hepta-root-build", hepta_root, "1.95.0",
                         ["cargo", "build", "--manifest-path", "codex-rs/Cargo.toml",
                          "-p", "codex-hepta-agentd", "--bin", "hepta-authority-host",
                          "--profile", hepta_profile, "--locked", *network]))
        steps.insert(5, ("hepta-recovery-build", hepta_root, "1.95.0",
                         ["cargo", "build", "--manifest-path", "codex-rs/Cargo.toml",
                          "-p", "codex-hepta-supervisor", "--bin", "hepta-supervisor-intent-recovery",
                          "--profile", hepta_profile, "--locked", *network]))
    return steps


def execute_step(step, output, environment, timeout, targets=None):
    name, cwd, toolchain, argv = step
    log_path = output / f"{name}.log"
    target_name = "hepta" if name.startswith("hepta-") else "desktop"
    target = targets[target_name] if targets else output / f"{target_name}-target"
    env = dict(environment, RUSTUP_TOOLCHAIN=toolchain,
               CARGO_TARGET_DIR=str(target),
               CARGO_INCREMENTAL="0",
               CARGO_BUILD_JOBS=environment.get("CARGO_BUILD_JOBS", "2"))
    started = time.monotonic()
    record = {"name": name, "argv": argv, "toolchain": toolchain,
              "log": log_path.name, "exit_code": None}
    with log_path.open("xb") as stream:
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                record["exit_code"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                record["error"] = "step_timeout"
                # Bound only this invocation and its children; never select by name.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        except OSError as exc:
            record["error"] = str(exc)
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    record["log_sha256"] = hashlib.sha256(log_path.read_bytes()).hexdigest()
    return record


def output_directory(path, repositories):
    target = Path(path).resolve()
    if any(target.is_relative_to(repo.path) for repo in repositories):
        raise profile.ProfileError("output directory must be outside both source repositories")
    try:
        target.mkdir(mode=0o700)
    except OSError as exc:
        raise profile.ProfileError(f"require a new output directory: {exc}") from exc
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--os-repo", required=True)
    parser.add_argument("--hepta-repo", required=True)
    parser.add_argument("--os-head", required=True)
    parser.add_argument("--os-tree", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--required-schema", type=int, choices=(1, 2, 3, 4, 5),
                        help="require one schema for a current release; historical verification otherwise remains available")
    parser.add_argument("--output-dir", required=True)
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument("--execute-host", action="store_true",
                        help="build/test the real host packages; never enables production authority")
    execution.add_argument("--build-host", action="store_true",
                           help="build real host binaries only; never claims test qualification")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--desktop-target-dir", help="optional existing external Cargo cache")
    parser.add_argument("--hepta-target-dir", help="optional existing external Cargo cache")
    parser.add_argument("--hepta-profile", choices=("dev-small", "dev"), default="dev-small",
                        help="recorded original Cargo profile; dev can reuse an existing test cache")
    parser.add_argument("--step-timeout", type=int, default=3600)
    args = parser.parse_args(argv)
    if not 1 <= args.step_timeout <= 14_400:
        parser.error("step timeout must be 1..14400 seconds")
    receipt = {"schema_version": 1, "qualification": "none", "steps": [],
               "production_authority": "not_configured_by_this_tool",
               "notes_runtime": "not_run_by_this_tool", "native_kernel": "not_run_by_this_tool"}
    output = None
    try:
        os_repo = profile.Repository(args.os_repo, "os")
        hepta_repo = profile.Repository(args.hepta_repo, "hepta")
        if os_repo.path == hepta_repo.path:
            raise profile.ProfileError("os and hepta must be distinct repository roots")
        raw_manifest = Path(args.manifest).read_bytes()
        manifest = profile.load_json_bytes(raw_manifest, args.manifest)
        if not isinstance(manifest, dict):
            raise profile.ProfileError("manifest must be an object")
        if args.required_schema is not None and manifest.get("schema_version") != args.required_schema:
            raise profile.ProfileError(f"current release requires schema {args.required_schema}")
        mapping = profile.load_json(os_repo.path / "support/release" /
                                    profile.source_map_name(manifest.get("schema_version")))
        before = profile.verify_manifest(manifest, os_repo, hepta_repo, args.os_head,
                                         args.os_tree, mapping)
        output = output_directory(args.output_dir, (os_repo, hepta_repo))
        (output / "source-manifest.json").write_bytes(raw_manifest)
        targets = {}
        for name, supplied in (("desktop", args.desktop_target_dir), ("hepta", args.hepta_target_dir)):
            target = Path(supplied).resolve() if supplied else output / f"{name}-target"
            if any(target.is_relative_to(repo.path) for repo in (os_repo, hepta_repo)):
                raise profile.ProfileError("Cargo target directories must be outside both source repositories")
            targets[name] = target
        receipt["source"] = before
        receipt["cargo_targets"] = {name: str(path) for name, path in targets.items()}
        receipt["manifest_sha256"] = profile.sha256(raw_manifest)
        receipt["qualification"] = "source-only"
        if args.execute_host or args.build_host:
            if manifest["schema_version"] == 5:
                receipt["schema_version"] = 2
            receipt["qualification"] = "none"
            receipt["passed"] = False
            (output / "pair-receipt.json").write_bytes(profile.canonical(receipt))
            final_step_deadline = None
            for step in host_steps(os_repo.path, hepta_repo.path, args.offline, args.hepta_profile,
                                   manifest["schema_version"]):
                if args.build_host and not step[0].endswith("-build"):
                    continue
                print(f"Running {step[0]}; log: {output / (step[0] + '.log')}", flush=True)
                final_step_deadline = time.monotonic() + args.step_timeout
                result = execute_step(step, output, os.environ, args.step_timeout, targets)
                receipt["steps"].append(result)
                (output / "pair-receipt.json").write_bytes(profile.canonical(receipt))
                if result["exit_code"] != 0:
                    raise profile.ProfileError(f"host step failed: {step[0]}")
            if manifest["schema_version"] == 5:
                expected = ["ui-build", "hepta-build", "hepta-root-build", "hepta-recovery-build"]
                if args.execute_host:
                    expected = ["ui-build", "ui-tests", "adapter-tests", "hepta-build",
                                "hepta-root-build", "hepta-recovery-build", "hepta-tests"]
                if [step["name"] for step in receipt["steps"]] != expected:
                    raise profile.ProfileError("V5 host proof requires every original selected stage")
            products = (HostProductSeal(targets, args.hepta_profile, final_step_deadline)
                        if manifest["schema_version"] == 5 else contextlib.nullcontext())
            with products as sealed:
                # A build may run generators. Retain actual ELFs while rejecting
                # source/lock drift, then reread their complete bytes and names.
                after = profile.verify_manifest(manifest, os_repo, hepta_repo, args.os_head,
                                                args.os_tree, mapping)
                if before != after:
                    raise profile.ProfileError("source identity changed during host execution")
                if sealed is not None:
                    receipt["host_products"] = sealed.verify()
                    receipt["host_products_verified_after_source_recheck"] = True
            receipt["qualification"] = "host-builds" if args.build_host else "host-build-tests"
        receipt["passed"] = True
        return_code = 0
    except (profile.ProfileError, OSError, ValueError) as exc:
        receipt["passed"] = False
        receipt["qualification"] = "none"
        receipt["error"] = str(exc)
        return_code = 1
    raw = profile.canonical(receipt)
    if output is not None:
        (output / "pair-receipt.json").write_bytes(raw)
    sys.stdout.buffer.write(raw)
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
