"""Explicit, exclusively leased reuse of one original product builder target.

This is a local cache on a trusted build host, not attestation of old objects.
No previous test result is reusable. The caller must invalidate local packages
and execute every current source check, test, lint, build and packaging stage.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat

import desktop


SCHEMA = "trill.linux-text-target-cache.v1"
LOCK_NAME = ".trill-product-target.lock"
STATE_NAME = ".trill-product-target.json"
ENVIRONMENT_KEYS = (
    "RUSTUP_TOOLCHAIN", "CARGO_PROFILE_DEV_DEBUG", "CARGO_PROFILE_DEV_INCREMENTAL",
    "RUSTC", "RUSTDOC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "RUSTFLAGS",
    "RUSTDOCFLAGS", "CARGO_ENCODED_RUSTFLAGS", "CARGO_ENCODED_RUSTDOCFLAGS",
)


def require(condition, message):
    if not condition:
        raise ValueError("Target cache: " + message)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def owned_path(value, *, directory=False):
    path = Path(value)
    require(path.is_absolute() and path == path.resolve(strict=True),
            "path must be absolute, canonical and free of symlinks: " + str(path))
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    require(kind(info.st_mode) and info.st_uid == os.geteuid()
            and not (info.st_mode & 0o022),
            "path must be owned by the current UID and not writable by others: " + str(path))
    require(directory or info.st_nlink == 1, "receipt/lease files must not be hard links")
    return path, info


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result

    path, info = owned_path(path)
    require(info.st_size <= 8 * 1024 * 1024, "receipt/state exceeds the bounded read limit")
    value = json.loads(path.read_bytes(), object_pairs_hook=unique)
    require(isinstance(value, dict), "receipt/state must be an object")
    return value


def isolated(path, roots):
    for root in roots:
        root = Path(root).resolve()
        require(not path.is_relative_to(root) and not root.is_relative_to(path),
                "target must not overlap source or current output: " + str(root))


def compatibility(receipt):
    """Desktop bytes may change; owner, SDK, toolchain and locks may not."""
    for key in ("hepta", "profile", "locks", "toolchain_executables", "source_caches", "native_input_paths", "environment"):
        require(isinstance(receipt.get(key), dict), "receipt lacks a typed " + key + " record")
    return {
        "hepta": {key: receipt["hepta"][key] for key in ("commit", "tree")},
        **{key: receipt[key] for key in (
            "profile", "profile_sha256", "cargo_profile", "locks",
            "toolchain_executables", "source_caches", "native_input_paths",
        )},
        "sdk_source_profile": receipt.get("sdk_source_profile"),
        "sdk_helper": receipt.get("sdk_helper"),
        "environment": {key: receipt["environment"][key] for key in ENVIRONMENT_KEYS},
    }


def local_packages(metadata, source_root):
    """Select all current in-repository path packages, including local deps."""
    source_root = Path(source_root).resolve(strict=True)
    result = {}
    for package in metadata["packages"]:
        manifest = Path(package["manifest_path"])
        if package.get("source") is not None or not manifest.resolve().is_relative_to(source_root):
            continue
        require(manifest.is_absolute() and manifest == manifest.resolve(strict=True)
                and manifest.is_file() and not manifest.is_symlink(), "invalid local package manifest")
        identity = package["id"]
        require(isinstance(identity, str) and identity and identity not in result,
                "duplicate or invalid local package identity")
        result[identity] = {"id": identity, "name": package["name"], "manifest": str(manifest)}
    require(result, "metadata selected no local packages to invalidate")
    return [result[key] for key in sorted(result)]


def clean_command(manifest, packages, common):
    require(packages, "refusing an unscoped cargo clean")
    return ["cargo", "clean", "--manifest-path", str(manifest), *common,
            *[argument for package in packages for argument in ("--package", package["id"])]]


class TargetCache:
    def __init__(self, path, prior_receipt, source_roots, output):
        self.fd = None
        self.begun = False
        self.path, self.info = owned_path(path, directory=True)
        isolated(self.path, [*source_roots, output])
        self.prior_path, _ = owned_path(prior_receipt)
        require(not self.prior_path.is_relative_to(self.path), "prior receipt must be outside its target")
        self.prior = load_json(self.prior_path)
        require(self.prior.get("schema") == "trill.linux-text-build-receipt.v1"
                and type(self.prior.get("exit_code")) is int
                and (self.prior.get("status"), self.prior.get("exit_code")) in (("passed", 0), ("failed", 1)),
                "a completed original builder receipt is required, including a failed attempt")
        compatibility(self.prior)
        require(self.prior.get("environment", {}).get("CARGO_TARGET_DIR") == str(self.path),
                "prior builder receipt does not identify this exact target directory")
        for key in ("source_commit", "source_tree"):
            require(re.fullmatch(r"[0-9a-f]{40}", self.prior.get(key, "")) is not None,
                    "prior receipt lacks a full Desktop source identity")
        if "execution_uid" in self.prior:
            require(self.prior["execution_uid"] == os.geteuid(), "prior builder used another UID")
        self.prior_hash = sha256(self.prior_path)
        self.state_path = self.path / STATE_NAME
        self.lock_path = self.path / LOCK_NAME
        try:
            self.fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            _, lock_info = owned_path(self.lock_path)
            require((lock_info.st_dev, lock_info.st_ino) == self._fd_identity(), "lease file changed while opening")
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError("Target cache: another builder holds the exclusive lease") from error
            self._check_identity()
            if self.state_path.exists() or self.state_path.is_symlink():
                state = load_json(self.state_path)
                require(state.get("schema") == SCHEMA and state.get("phase") == "finished"
                        and state.get("target") == str(self.path) and state.get("uid") == os.geteuid()
                        and state.get("device") == self.info.st_dev and state.get("inode") == self.info.st_ino,
                        "cache has an unfinished or incompatible lease record; use a fresh build")
                require(state.get("receipt") == str(self.prior_path)
                        and state.get("receipt_sha256") == self.prior_hash,
                        "supply the latest completed receipt for this cache, not older history")
            self._verify_prior_logs()
        except BaseException:
            self.close()
            raise

    def _fd_identity(self):
        info = os.fstat(self.fd)
        return info.st_dev, info.st_ino

    def _check_identity(self):
        _, info = owned_path(self.path, directory=True)
        _, lock = owned_path(self.lock_path)
        require((info.st_dev, info.st_ino) == (self.info.st_dev, self.info.st_ino)
                and (lock.st_dev, lock.st_ino) == self._fd_identity(), "leased target or lock was replaced")
        owned_path(self.prior_path)
        require(sha256(self.prior_path) == self.prior_hash, "prior receipt changed during reuse")

    def _verify_prior_logs(self):
        entries = self.prior.get("commands", [])
        require(isinstance(entries, list) and entries, "prior builder has no recorded commands")
        completed = {}
        for entry in entries:
            require(isinstance(entry, dict) and type(entry.get("exit_code")) is int,
                    "prior command has no completed exit status")
            name = entry.get("name")
            command = entry.get("command")
            require(isinstance(name, str) and name not in completed and isinstance(command, list)
                    and command and all(isinstance(part, str) for part in command),
                    "prior command lacks a unique name or actual argument vector")
            for stream in ("stdout", "stderr"):
                filename = entry.get(stream)
                require(isinstance(filename, str) and Path(filename).name == filename and filename not in (".", ".."),
                        "invalid prior log filename")
                path, _ = owned_path(self.prior_path.parent / "logs" / filename)
                require(sha256(path) == entry.get(stream + "_sha256"), "prior command log bytes changed")
            completed[name] = entry
        for name in ("compiler", "cargo", "native-metadata"):
            require(completed.get(name, {}).get("exit_code") == 0,
                    "prior builder did not complete " + name)
        require("native-ui-tests" in completed, "prior target has no actual UI compilation/test attempt")
        for name in ("compiler", "cargo", "native-metadata", "native-ui-tests"):
            tool = "rustc" if name == "compiler" else "cargo"
            require(completed[name]["command"][0] == self.prior["toolchain_executables"][tool]["path"],
                    "prior command is not bound to its recorded compiler tool")
        require("metadata" in completed["native-metadata"]["command"]
                and "test" in completed["native-ui-tests"]["command"]
                and all("ui/Cargo.toml" in completed[name]["command"]
                        for name in ("native-metadata", "native-ui-tests")),
                "prior target is not bound to the original UI metadata/test attempt")

    def validate(self, current, source_roots):
        self._check_identity()
        isolated(self.path, source_roots)
        require(compatibility(self.prior) == compatibility(current),
                "Hepta/SDK/compiler/locks/profile/native inputs differ; use a fresh target")
        require(current["environment"].get("CARGO_INCREMENTAL") == "0",
                "this invocation must explicitly disable Rust incremental compilation")
        return {
            "mode": "reuse-builder-target", "target": str(self.path),
            "cold_build": False, "incremental_compilation": False, "prior_pass_reused": False,
            "execution_uid": os.geteuid(), "device": self.info.st_dev, "inode": self.info.st_ino,
            "ownership_basis": "current receipt/target/lease ownership and original builder path/log bytes; not historical creator attestation",
            "compatibility": "same Hepta, SDK, compiler, locks, profile and native inputs; local Desktop packages invalidated",
            "prior_receipt": {"path": str(self.prior_path), "sha256": self.prior_hash,
                              "status": self.prior["status"],
                              "source_commit": self.prior["source_commit"], "source_tree": self.prior["source_tree"],
                              "hepta": compatibility(self.prior)["hepta"]},
            "exclusive_lock": str(self.lock_path),
            "prior_global_incremental": self.prior["environment"].get("CARGO_INCREMENTAL", "unrecorded by legacy builder"),
        }

    def begin(self, receipt_path):
        self._check_identity()
        self.receipt_path = Path(receipt_path)
        self._write_state("running")
        self.begun = True

    def _write_state(self, phase):
        state = {"schema": SCHEMA, "phase": phase, "target": str(self.path), "uid": os.geteuid(),
                 "device": self.info.st_dev, "inode": self.info.st_ino,
                 "receipt": str(self.receipt_path), "receipt_sha256": sha256(self.receipt_path)}
        desktop.atomic_write(self.state_path, canonical(state))

    def finish(self):
        if self.begun:
            self._check_identity()
            current = load_json(self.receipt_path)
            require((current.get("status"), current.get("exit_code")) in (("passed", 0), ("failed", 1)),
                    "unfinished builds cannot release a reusable receipt")
            self._write_state("finished")
            self.begun = False

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
