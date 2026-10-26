"""Verify the declared prepared-SDK lock in a disposable source copy.

The original checkout keeps its Git SDK lock for ordinary CI. Only a second
lock tracked in that same commit may replace ui/Cargo.lock in the copy. The
receipt names that exact input; no Rust source may differ.
"""
from pathlib import Path
import hashlib
import subprocess

LOCK = "support/ui/preedit-sdk/Cargo.lock"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(repository, identity, lock_bytes):
    require(repository.git("rev-parse", "HEAD^{commit}").decode().strip() == identity["commit"]
            and repository.git("rev-parse", "HEAD^{tree}").decode().strip() == identity["tree"],
            "Prepared build source identity changed")
    flags = repository.git("ls-files", "-v", "-z").split(b"\0")
    require(not any(item and (item[:1].islower() or item[:1] == b"S") for item in flags),
            "Prepared build source has hidden tracked changes")
    status = repository.git("status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none")
    require(status == b" M ui/Cargo.lock\n", "Prepared build changed source beyond its declared UI lock")
    path = repository.path / "ui/Cargo.lock"
    require(path.is_file() and not path.is_symlink() and path.read_bytes() == lock_bytes,
            "Prepared build lock differs from its committed input")


def prepare(original, destination, identity, repository_type, log):
    lock_bytes, record = original.file(LOCK)
    require(lock_bytes != (original.path / "ui/Cargo.lock").read_bytes(),
            "Prepared lock must be distinct from the original Git SDK lock")
    destination = Path(destination)
    require(not destination.exists(), "Prepared build source destination exists")
    with Path(log).open("xb") as stream:
        for arguments in (
            ["git", "-c", "core.hooksPath=/dev/null", "clone", "--shared", "--no-checkout",
             str(original.path), str(destination)],
            ["git", "-c", "core.hooksPath=/dev/null", "-C", str(destination),
             "checkout", "--detach", identity["commit"]],
        ):
            subprocess.run(arguments, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream, check=True)
    copy = repository_type(destination, "prepared Desktop source")
    copy.check(identity["commit"], identity["tree"])
    (destination / "ui/Cargo.lock").write_bytes(lock_bytes)
    verify(copy, identity, lock_bytes)
    return copy, lock_bytes, {
        "schema": "trill.declared-preedit-build-source.v1",
        "base": identity,
        "root": str(destination),
        "only_changed_path": "ui/Cargo.lock",
        "committed_lock": record,
        "compiled_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "rust_sources_changed": False,
    }
