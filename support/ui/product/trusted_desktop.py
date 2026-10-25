#!/usr/bin/env python3
"""Root-owned native package deployment, consuming existing Hepta authority.

This installer never creates a human profile, writer, lease or owner pidfd.
Run it from reviewed administrator tooling. Package content is data, never
imported or executed by stage/rollback. The original Root validates authority.
"""
import argparse
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import select
import shutil
import stat
import tempfile

import desktop

require = desktop.require
HEX = re.compile(r"[0-9a-f]{64}\Z")
LOCK = ".native-deployment.lock"
RECORD = "native-deployment.json"


def protected_directory(path, shared_parent=False):
    path = Path(path)
    require(path.is_absolute() and ".." not in path.parts, "Canonical absolute Root path required")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        info = current.lstat()
        # A root-owned sticky parent (e.g. /tmp) cannot let another user rename
        # our root-owned child. A writable non-sticky ancestor can, and is refused.
        sticky_parent = bool(info.st_mode & stat.S_ISVTX) and (current != path or shared_parent)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                and (not info.st_mode & 0o022 or sticky_parent),
                f"Root directory has a symlink, foreign owner or mutable ancestor: {current}")
    return path


def protected_file(path, mode=None):
    path = Path(path)
    protected_directory(path.parent)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
            and not info.st_mode & 0o7022
            and (mode is None or stat.S_IMODE(info.st_mode) == mode),
            f"Expected one linked protected Root regular file: {path}")
    return path


@contextlib.contextmanager
def deployment_lock(prefix, create=False):
    require(os.geteuid() == 0, "Native deployment requires the existing Root administrator")
    prefix = Path(prefix)
    if create and not prefix.exists():
        protected_directory(prefix.parent, shared_parent=True)
        prefix.mkdir(mode=0o755)
        desktop.fsync_dir(prefix.parent)
    protected_directory(prefix)
    fd = os.open(prefix / LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        protected_file(prefix / LOCK, 0o600)
        opened, named = os.fstat(fd), (prefix / LOCK).lstat()
        require((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), "Deployment lock was replaced")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise desktop.ProductError("Original native Root is active; end that session before changing releases") from error
        yield fd
    finally:
        os.close(fd)


def read_record(prefix):
    path = protected_file(Path(prefix) / RECORD, 0o600)
    value = desktop.read_json(path)
    require(set(value) == {"schema", "generation", "current", "previous"}
            and value["schema"] == "trill.native-deployment.v1"
            and type(value["generation"]) is int and 0 < value["generation"] < 2**63,
            "Invalid native deployment record")
    for item in (value["current"], value["previous"]):
        if item is not None:
            require(isinstance(item, dict) and set(item) == {"release_id", "manifest_sha256"}
                    and desktop.RELEASE.fullmatch(item["release_id"])
                    and HEX.fullmatch(item["manifest_sha256"]), "Invalid native release selection")
    require(value["current"] is not None, "Native current release is missing")
    return value


def verified_release(prefix, selection):
    release = Path(prefix) / "releases" / selection["release_id"]
    protected_directory(release)
    manifest_path = protected_file(release / "manifest.json", 0o644)
    require(desktop.digest(desktop.regular_bytes(manifest_path)) == selection["manifest_sha256"],
            "Selected native manifest differs from reviewed package")
    manifest = desktop.verify_installed_package(release, selection)
    require(manifest["release_id"] == selection["release_id"], "Native release identifier differs")
    for name, record in manifest["files"].items():
        protected_file(release / name, record["mode"])
    require(any(name.startswith("resources/") for name in manifest["files"]),
            "Native deployment requires the complete bundled Makepad resources")
    return release, manifest


def binding(prefix, record):
    release, manifest = verified_release(prefix, record["current"])
    return {"schema": "trill.native-program-binding.v1", "generation": record["generation"],
            "release_id": release.name, "desktop_commit": manifest["desktop_commit"],
            "hepta_commit": manifest["hepta_commit"], "program": str(release / "bin/trill-shell"),
            "program_sha256": manifest["files"]["bin/trill-shell"]["sha256"],
            "resources": str(release / "resources"), "human_authority_created": False,
            "production_authority_verified": False}


def stage(package, prefix, expected_manifest):
    require(HEX.fullmatch(expected_manifest), "Reviewed manifest SHA256 is required")
    package, prefix = Path(package), Path(prefix)
    manifest_bytes = desktop.regular_bytes(package / "manifest.json")
    require(desktop.digest(manifest_bytes) == expected_manifest, "Package differs from reviewed manifest")
    manifest = desktop.verify_package(package)
    require(any(name.startswith("resources/") for name in manifest["files"]),
            "Native deployment requires bundled resources")
    selection = {"release_id": manifest["release_id"], "manifest_sha256": expected_manifest}
    with deployment_lock(prefix, create=True):
        old = read_record(prefix) if (prefix / RECORD).exists() else None
        if old:
            verified_release(prefix, old["current"])
        releases = prefix / "releases"
        if not releases.exists():
            releases.mkdir(mode=0o755)
            desktop.fsync_dir(prefix)
        protected_directory(releases)
        release = releases / manifest["release_id"]
        if release.exists() or release.is_symlink():
            verified_release(prefix, selection)
        else:
            temporary = Path(tempfile.mkdtemp(prefix=".stage-", dir=releases))
            try:
                for name, info in manifest["files"].items():
                    dest = temporary / name
                    dest.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                    data = desktop.regular_bytes(package / name)
                    require(len(data) == info["bytes"] and desktop.digest(data) == info["sha256"],
                            "Package changed during staging: " + name)
                    desktop.atomic_write(dest, data, info["mode"])
                desktop.atomic_write(temporary / "manifest.json", manifest_bytes, 0o644)
                desktop.verify_package(temporary)
                for directory in sorted((p for p in temporary.rglob("*") if p.is_dir()),
                                        key=lambda p: len(p.parts), reverse=True):
                    directory.chmod(0o755)
                    desktop.fsync_dir(directory)
                temporary.chmod(0o755)
                desktop.fsync_dir(temporary)
                os.rename(temporary, release)
                desktop.fsync_dir(releases)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        verified_release(prefix, selection)
        if old and old["current"] == selection:
            return binding(prefix, old)
        record = {"schema": "trill.native-deployment.v1", "generation": old["generation"] + 1 if old else 1,
                  "current": selection, "previous": old["current"] if old else None}
        desktop.atomic_write(prefix / RECORD, desktop.json_bytes(record))
        return binding(prefix, record)


def rollback(prefix):
    with deployment_lock(prefix):
        record = read_record(prefix)
        require(record["previous"] is not None, "No previous native release")
        verified_release(prefix, record["previous"])
        record["current"], record["previous"] = record["previous"], record["current"]
        record["generation"] += 1
        desktop.atomic_write(Path(prefix) / RECORD, desktop.json_bytes(record))
        return binding(prefix, record)


def launch(prefix, authority, authority_sha256, config, registration, profile):
    """Exec the original Root with its pre-held owner pidfd still on stdin."""
    require(HEX.fullmatch(authority_sha256), "Reviewed original Root executable SHA256 is required")
    with deployment_lock(prefix) as lock:
        selected = binding(prefix, read_record(prefix))
        value = desktop.read_json(protected_file(profile, 0o600))
        require(value.get("program") == selected["program"]
                and value.get("program_sha256") == selected["program_sha256"]
                and value.get("environment", {}).get("TRILL_UI_MAKEPAD_RESOURCES") == selected["resources"],
                "Existing authenticated profile does not name this installed program/resources; obtain it from the original owner")
        for path in (config, registration):
            protected_file(path, 0o600)
        require(os.readlink("/proc/self/fd/0") == "anon_inode:[pidfd]",
                "Original launcher must transfer its pre-held owner pidfd on stdin")
        poller = select.poll()
        poller.register(0, select.POLLIN | select.POLLHUP | select.POLLERR)
        require(not poller.poll(0), "Original owner pidfd has ended")
        authority = protected_file(authority)
        fd = os.open(authority, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read(desktop.MAX_FILE + 1)
            require(len(data) <= desktop.MAX_FILE and data[:4] == b"\x7fELF"
                    and desktop.digest(data) == authority_sha256, "Original Root executable identity mismatch")
            require(os.fstat(fd).st_mode & stat.S_IXUSR, "Original Root executable is not executable")
            os.set_inheritable(lock, True)
            # exec by descriptor consumes exactly the executable just hashed.
            # Root marks the deployment lock CLOEXEC before spawning its UI.
            args = [str(authority), "launch-native", "--config", str(config),
                    "--registration", str(registration), "--native-profile", str(profile),
                    "--owner-pidfd-stdin", "--deployment-lock-fd", str(lock)]
            os.execve(fd, args, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"})
        finally:
            os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=Path("/opt/trillionnium-desktop"))
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("stage")
    install.add_argument("--package", type=Path, required=True)
    install.add_argument("--expected-manifest", required=True)
    commands.add_parser("describe")
    commands.add_parser("rollback")
    start = commands.add_parser("launch")
    for name in ("authority", "config", "registration", "profile"):
        start.add_argument("--" + name, type=Path, required=True)
    start.add_argument("--authority-sha256", required=True)
    args = parser.parse_args()
    if args.command == "stage":
        result = stage(args.package, args.prefix, args.expected_manifest)
    elif args.command == "rollback":
        result = rollback(args.prefix)
    elif args.command == "describe":
        with deployment_lock(args.prefix):
            result = binding(args.prefix, read_record(args.prefix))
    else:
        launch(args.prefix, args.authority, args.authority_sha256, args.config, args.registration, args.profile)
        return
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, desktop.ProductError) as error:
        raise SystemExit("Native deployment refused: " + str(error)) from error
