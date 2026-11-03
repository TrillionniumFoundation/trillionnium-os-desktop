#!/usr/bin/env python3
"""User installation and lifecycle for the existing Linux host UI binaries.

This program is packaging/process plumbing. Session remains the application
owner; this program never creates an Objective, authority or effect ledger.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import native_sdk

PROGRAMS = ("trill-session", "trill-shell", "trill-app-window", "trill-ctl", "trill-notes-recovery")
UNIT = "trillionnium-desktop-session.service"
MAX_FILE = 128 * 1024 * 1024
MAX_BUNDLE = 512 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}\Z")
RELEASE = re.compile(r"[0-9a-f]{12}-[0-9a-f]{12}\Z")
OBSERVER_ENV = ("TRILL_HEPTA_AGENTD_SOCKET", "TRILL_HEPTA_AGENT_ID",
                "TRILL_HEPTA_SPAWN_GENERATION", "TRILL_HEPTA_PEER_UID", "TRILL_HEPTA_RUN_ID")
ACCESSKIT_REVISION = "405d578cdfd8496ee79020d24cfaac8c29a8a48f"
ACCESSKIT_CRATES = {"accesskit": "0.17.1", "accesskit_consumer": "0.26.0",
                   "accesskit_atspi_common": "0.10.1", "accesskit_unix": "0.13.1"}
ACCESSKIT_NOTICES = {"dependency-notices/accesskit/" + name for name in (
    "LICENSE-APACHE", "LICENSE-MIT", "LICENSE.chromium", "HEPTA_UPSTREAM.json",
    "HEPTA_PATCH.diff", "HEPTA_PATCH.md")}


class ProductError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ProductError(message)


def unix_socket_path(path, label):
    value = os.fspath(path)
    require(isinstance(value, str) and Path(value).is_absolute() and "\x00" not in value,
            f"{label} must be an absolute pathname without NUL")
    length = len(os.fsencode(value))
    require(length <= 107,
            f"{label} is {length} bytes; Linux AF_UNIX pathnames allow at most 107 bytes "
            "(108 including the terminating NUL). Choose a shorter socket path or XDG_RUNTIME_DIR.")
    return value


def session_socket_path(runtime):
    return unix_socket_path(Path(runtime) / "trillionnium-ui/session.sock", "Session socket from XDG_RUNTIME_DIR")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular_bytes(path, limit=MAX_FILE):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size <= limit,
                f"Not a bounded regular file: {path}")
        data = stream.read(limit + 1)
        require(len(data) <= limit, f"File grew beyond limit: {path}")
        return data


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def read_json(path, limit=4 * 1024 * 1024):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, f"Duplicate JSON key: {key}")
            out[key] = value
        return out
    return json.loads(regular_bytes(path, limit), object_pairs_hook=unique)


def private_dir(path):
    path = Path(path)
    require(path.is_absolute(), f"Absolute directory required: {path}")
    missing = []
    parent = path
    while not parent.exists() and not parent.is_symlink():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
            fsync_dir(directory.parent)
        except FileExistsError:
            pass
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700,
            f"Directory must be owned by this user, real, and 0700: {path}")
    return path


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path, data, mode=0o600):
    path = Path(path)
    if path.exists() or path.is_symlink():
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(),
                f"Refusing to replace a non-owned regular file: {path}")
    fd, name = tempfile.mkstemp(prefix=".trill-", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
        fsync_dir(path.parent)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def current_release(prefix):
    current = Path(prefix) / "current"
    if not current.is_symlink():
        require(not current.exists(), "current is not a release symlink")
        return None
    target = os.readlink(current)
    pieces = target.split("/")
    require(len(pieces) == 2 and pieces[0] == "releases" and RELEASE.fullmatch(pieces[1]),
            "Invalid current release target")
    release = Path(prefix) / target
    require(release.is_dir() and not release.is_symlink(), "Missing real current release")
    return release


def switch_release(prefix, release_id):
    require(RELEASE.fullmatch(release_id), "Invalid release id")
    prefix = Path(prefix)
    path = prefix / (".switch-" + str(os.getpid()))
    try:
        os.symlink("releases/" + release_id, path)
        os.replace(path, prefix / "current")
        fsync_dir(prefix)
    finally:
        if path.is_symlink():
            path.unlink()


def native_resource_files(root, expected_hepta=None, expected_sdk=None):
    """Verify the prepared original bundle; Rust also checks its compiled inventory."""
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "Makepad resource root must be a real directory")
    bundle = read_json(root / "bundle.json", 64 * 1024)
    inventory_bytes = regular_bytes(root / "NATIVE-ASSETS.json", 128 * 1024)
    inventory = read_json(root / "NATIVE-ASSETS.json", 128 * 1024)
    require(bundle["schema"] == "trill.original-makepad-bundle.v1"
            and bundle["inventorySha256"] == digest(inventory_bytes), "Makepad inventory identity mismatch")
    sdk = "337566c8b25d47f7e4fff6a202157b65bf183330"
    require(inventory["schema"] == "hepta.native-embedded-assets.v1"
            and inventory["makepadRevision"] == sdk
            and bundle["makepadSource"] in (
                "git+" + native_sdk.UPSTREAM + "?rev=" + sdk + "#" + sdk,
                native_sdk.SOURCE_ID, native_sdk.PREEDIT_SOURCE_ID)
            and re.search(r"#[0-9a-f]{40}\Z", bundle["heptaSource"]), "Unpinned Makepad resource sources")
    require(len(inventory["assets"]) == bundle["assets"] == 29
            and len(inventory["noticeFileSha256"]) == bundle["notices"] == 15,
            "Incomplete Makepad resource inventory")
    if expected_hepta is not None:
        require(SHA.fullmatch(expected_hepta) and bundle["heptaSource"].endswith("#" + expected_hepta),
                "Native resource Hepta source differs from the binary source profile")
    dependency_bytes = regular_bytes(root / "NATIVE-DEPENDENCIES.json", 128 * 1024)
    dependencies = read_json(root / "NATIVE-DEPENDENCIES.json", 128 * 1024)
    require(bundle.get("dependencyInventorySha256") == digest(dependency_bytes),
            "Native dependency inventory identity mismatch")
    require(dependencies.get("schema") == "hepta.native-dependency-notices.v1"
            and dependencies.get("upstreamRevision") == ACCESSKIT_REVISION
            and dependencies.get("crates") == ACCESSKIT_CRATES,
            "Unsupported native dependency provenance")
    require(bundle.get("accessibilitySources") == {
                name: {"version": version, "source": bundle["heptaSource"]}
                for name, version in ACCESSKIT_CRATES.items()},
            "Native accessibility packages must use the same original Hepta source")
    dependency_files = dependencies.get("files", [])
    require(len(dependency_files) == bundle.get("dependencyNotices") == 6
            and {entry["path"] for entry in dependency_files} == ACCESSKIT_NOTICES,
            "Incomplete or unexpected native dependency notice paths")
    records = [(entry["logical"], entry) for entry in inventory["assets"]]
    records += [(entry["path"], entry) for entry in inventory["noticeFileSha256"]]
    records += [(entry["path"], entry) for entry in dependency_files]
    try:
        records += native_sdk.bundle_records(root, bundle, read_json, regular_bytes, expected_sdk,
                                             bind_binary=expected_hepta is not None)
    except ValueError as error:
        raise ProductError(str(error)) from error
    source = inventory["liberationSource"]
    records.append(("sources/" + source["file"], source))
    names = {"bundle.json", "NATIVE-ASSETS.json", "NATIVE-DEPENDENCIES.json"}
    total = 0
    for name, entry in records:
        require(isinstance(name, str) and not name.startswith("/") and "\\" not in name
                and all(part not in ("", ".", "..") for part in name.split("/"))
                and name not in names, "Unsafe or duplicate resource path")
        names.add(name)
        path = root / name
        require(path.resolve().is_relative_to(root.resolve()), "Resource escaped bundle")
        data = regular_bytes(path)
        total += len(data)
        require(total <= MAX_BUNDLE and len(data) == entry["bytes"]
                and digest(data) == entry["sha256"], "Makepad resource bytes mismatch: " + name)
    actual = set()
    for path in root.rglob("*"):
        require(not path.is_symlink(), "Resource bundle contains a symlink")
        if not path.is_dir():
            actual.add(path.relative_to(root).as_posix())
    require(actual == names, "Unexpected or missing resource file")
    return sorted(names)


def verify_package(package):
    package = Path(package)
    manifest = read_json(package / "manifest.json")
    require(set(manifest) == {"schema_version", "release_id", "desktop_commit", "hepta_commit",
                              "qualification", "effects_authorized", "files"}, "Unknown package schema")
    require(manifest["schema_version"] == 1 and manifest["qualification"] == "linux-host-package"
            and manifest["effects_authorized"] is False, "Unsupported package qualification")
    require(SHA.fullmatch(manifest["desktop_commit"]) and SHA.fullmatch(manifest["hepta_commit"]),
            "Package must bind both full source commits")
    require(RELEASE.fullmatch(manifest["release_id"]), "Invalid package release id")
    files = manifest["files"]
    profile = read_json(package / "source-profile.json")
    require(manifest["release_id"] == manifest["desktop_commit"][:12] + "-" + digest(json_bytes(files))[:12],
            "Release identifier does not bind all package files")
    expected = {"desktop.py", "PRODUCT.md", "source-profile.json", "PROVENANCE.txt"}
    if "native_sdk.py" in files:
        expected.add("native_sdk.py")
    expected.update("bin/" + name for name in PROGRAMS)
    if any(name.startswith("resources/") for name in files):
        expected.update("resources/" + name for name in native_resource_files(
            package / "resources", manifest["hepta_commit"], profile.get("makepad_sdk")))
    require(set(files) == expected, "Unexpected or missing package file")
    total = 0
    for name, record in files.items():
        require(set(record) == {"sha256", "bytes", "mode"}, f"Invalid file record: {name}")
        data = regular_bytes(package / name)
        total += len(data)
        require(total <= MAX_BUNDLE, "Package exceeds total bound")
        require(len(data) == record["bytes"] and digest(data) == record["sha256"],
                f"Package checksum mismatch: {name}")
        want_mode = 0o755 if name.startswith("bin/") or name == "desktop.py" else 0o644
        require(record["mode"] == want_mode, f"Invalid package mode: {name}")
        if name.startswith("bin/"):
            require(data[:4] == b"\x7fELF", f"Not a Linux ELF: {name}")
    require(profile["hepta"]["commit"] == manifest["hepta_commit"], "Hepta profile mismatch")
    if profile.get("makepad_sdk") is not None:
        require("native_sdk.py" in files, "SDK candidate package lacks its exact source validator")
        profile_hash = digest(regular_bytes(package / "resources/NATIVE-SDK-SOURCE.json"))
        require(f"Makepad source profile SHA256: {profile_hash}\n".encode()
                in regular_bytes(package / "PROVENANCE.txt"), "Binary archive lacks SDK source provenance")
    require(f"Source commit: {manifest['desktop_commit']}\n".encode()
            in regular_bytes(package / "PROVENANCE.txt"), "Binary source provenance mismatch")
    return manifest


def pack(archive, expected_desktop, profile_path, output, makepad_resources=None):
    require(SHA.fullmatch(expected_desktop), "Expected Desktop commit must be 40 hex characters")
    profile = read_json(profile_path)
    hepta = profile.get("hepta", {}).get("commit", "")
    require(SHA.fullmatch(hepta), "Source profile must bind a full Hepta commit")
    raw_archive = regular_bytes(archive, MAX_BUNDLE)
    output = Path(output).absolute()
    require(not output.exists(), "Choose a new package path; existing output is not replaced")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".trill-package-", dir=output.parent) as temp:
        package = Path(temp) / "trillionnium-desktop"
        (package / "bin").mkdir(parents=True)
        names = {"a10-linux-host-binaries/" + n for n in (*PROGRAMS, "SHA256SUMS", "PROVENANCE.txt")}
        entries = {}
        with tarfile.open(fileobj=io.BytesIO(raw_archive), mode="r:gz") as tar:
            total = 0
            seen = set()
            for member in tar:
                require(member.name not in seen, "Duplicate archive member")
                seen.add(member.name)
                if member.name == "a10-linux-host-binaries":
                    require(member.isdir(), "Invalid binary archive root")
                    continue
                require(member.name in names and member.isfile() and member.size <= MAX_FILE,
                        "Unsafe or unexpected binary archive entry")
                total += member.size
                require(total <= MAX_BUNDLE, "Unbounded binary archive")
                with tar.extractfile(member) as inp:
                    entries[member.name.rsplit("/", 1)[1]] = inp.read(MAX_FILE + 1)
            require(seen == names | {"a10-linux-host-binaries"}, "Incomplete binary archive")
        sums = {}
        for line in entries["SHA256SUMS"].decode("ascii").splitlines():
            match = re.fullmatch(r"([0-9a-f]{64})  (trill-[a-z-]+)", line)
            require(match and match[2] not in sums, "Invalid inner binary checksum list")
            sums[match[2]] = match[1]
        require(set(sums) == set(PROGRAMS), "Missing binary checksum")
        for name in PROGRAMS:
            require(digest(entries[name]) == sums[name], f"Binary checksum mismatch: {name}")
            (package / "bin" / name).write_bytes(entries[name])
        (package / "PROVENANCE.txt").write_bytes(entries["PROVENANCE.txt"])
        (package / "source-profile.json").write_bytes(regular_bytes(profile_path))
        (package / "desktop.py").write_bytes(regular_bytes(Path(__file__)))
        (package / "native_sdk.py").write_bytes(regular_bytes(Path(__file__).with_name("native_sdk.py")))
        product_doc = Path(__file__).parent.parent / "PRODUCT.md"
        (package / "PRODUCT.md").write_bytes(regular_bytes(product_doc))
        if makepad_resources:
            for name in native_resource_files(makepad_resources, hepta, profile.get("makepad_sdk")):
                target = package / "resources" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(regular_bytes(Path(makepad_resources) / name))
        files = {}
        for path in sorted(package.rglob("*")):
            if path.is_file():
                name = path.relative_to(package).as_posix()
                mode = 0o755 if name.startswith("bin/") or name == "desktop.py" else 0o644
                path.chmod(mode)
                data = path.read_bytes()
                files[name] = {"sha256": digest(data), "bytes": len(data), "mode": mode}
        release_id = expected_desktop[:12] + "-" + digest(json_bytes(files))[:12]
        manifest = {"schema_version": 1, "release_id": release_id,
                    "desktop_commit": expected_desktop, "hepta_commit": hepta,
                    "qualification": "linux-host-package", "effects_authorized": False,
                    "files": files}
        (package / "manifest.json").write_bytes(json_bytes(manifest))
        (package / "manifest.json").chmod(0o644)
        verify_package(package)
        built = Path(temp) / "product.tar.gz"
        with tarfile.open(built, "w:gz") as tar:
            tar.add(package, arcname="trillionnium-desktop")
        os.replace(built, output)
        fsync_dir(output.parent)
    atomic_write(output.with_name(output.name + ".sha256"),
                 (digest(regular_bytes(output, MAX_BUNDLE)) + "  " + output.name + "\n").encode(), 0o644)
    return {"package": str(output), "release_id": release_id, "desktop_commit": expected_desktop,
            "hepta_commit": hepta, "effects_authorized": False,
            "binaries": {name: {key: files["bin/" + name][key] for key in ("sha256", "bytes")}
                         for name in PROGRAMS}}


def systemctl(*args, check=True):
    proc = subprocess.run(["systemctl", "--user", *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=15)
    if check:
        require(proc.returncode == 0, "User service manager: " + proc.stderr.strip())
    return proc


def require_stopped(unit=UNIT):
    result = systemctl("show", unit, "--property=ActiveState", "--value", check=False)
    require(result.returncode == 0, "Cannot verify Session stopped: user service manager unavailable")
    require(result.stdout.strip() in ("", "inactive", "failed"),
            "Session is active; close applications, then run trillionnium-desktop stop before changing releases")
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        endpoint = session_socket_path(runtime)
        probe = socket.socket(socket.AF_UNIX)
        probe.settimeout(0.5)
        try:
            probe.connect(endpoint)
        except (FileNotFoundError, ConnectionRefusedError):
            pass
        else:
            raise ProductError("A Session outside this unit is active; do not mix releases")
        finally:
            probe.close()


@contextlib.contextmanager
def install_lock(prefix):
    private_dir(prefix)
    fd = os.open(Path(prefix) / ".install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(), "Invalid install lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def shell_quote(value):
    # Used only by the generated POSIX wrapper, not for subprocess commands.
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def systemd_quote(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def integrations(prefix, paths):
    require(set(paths) == {"bin_dir", "unit_dir", "applications_dir", "config", "unit_name"},
            "Invalid installation paths")
    for value in [str(prefix), *(paths[name] for name in ("bin_dir", "unit_dir", "applications_dir", "config"))]:
        require(isinstance(value, str) and Path(value).is_absolute()
                and all(ord(character) >= 32 for character in value), "Installation paths must be absolute without control characters")
    unit_name = paths["unit_name"]
    require(re.fullmatch(r"trillionnium-desktop(?:-[a-z0-9-]+)?-session\.service", unit_name), "Invalid dedicated unit name")
    launcher = Path(paths["bin_dir"]) / "trillionnium-desktop"
    prefix = Path(prefix)
    wrapper = ("#!/bin/sh\nexec /usr/bin/env python3 " + shell_quote(prefix / "current/desktop.py")
               + " --prefix " + shell_quote(prefix) + ' "$@"\n').encode()
    unit = ("[Unit]\nDescription=Trillionnium Desktop application Session\nAfter=graphical-session.target\n"
            "PartOf=graphical-session.target\n\n[Service]\nType=simple\nExecStart="
            + systemd_quote(launcher) + " session\nRestart=no\nKillMode=control-group\n"
            "TimeoutStopSec=10\nUMask=0077\nNoNewPrivileges=yes\n").encode()
    # Desktop Exec quoting is not shell expansion; escape each reserved char.
    desktop_exec = '"' + str(launcher).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%") + '" run'
    desktop = ("[Desktop Entry]\nType=Application\nName=Trillionnium Desktop\n"
               "Comment=Hepta workspace and local applications\nExec=" + desktop_exec
               + "\nTerminal=false\nCategories=Utility;\nStartupNotify=true\n").encode()
    return {str(launcher): (wrapper, 0o755),
            str(Path(paths["unit_dir"]) / unit_name): (unit, 0o644),
            str(Path(paths["applications_dir"]) / "trillionnium-desktop.desktop"): (desktop, 0o644)}


def install(package, prefix, paths, activity_probe=require_stopped):
    manifest = verify_package(package)
    package, prefix = Path(package), Path(prefix)
    with install_lock(prefix):
        require_no_pending_rollback(prefix)
        activity_probe(paths["unit_name"])
        generated = integrations(prefix, paths)
        record_path = prefix / "installation.json"
        pending_path = prefix / "installation.pending.json"
        old = read_json(record_path) if record_path.exists() or record_path.is_symlink() else None
        previous = current_release(prefix)
        previous_name = previous.name if previous else None
        pending = None
        if pending_path.exists() or pending_path.is_symlink():
            info = pending_path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                    and stat.S_IMODE(info.st_mode) == 0o600, "Invalid pending installation file")
            pending = read_json(pending_path)
            require(isinstance(pending, dict) and set(pending) == {
                "schema_version", "package_sha256", "paths", "previous_current", "previous_record", "record"
            } and pending["schema_version"] == 1, "Unknown pending installation schema")
            require(pending["package_sha256"] == digest(json_bytes(manifest))
                    and pending["paths"] == paths,
                    "An interrupted installation must be resumed with the same package and paths")
            require(old in (pending["previous_record"], pending["record"]),
                    "Installation record changed during interrupted installation")
            require(previous_name in (pending["previous_current"], manifest["release_id"]),
                    "Current release changed during interrupted installation")
            old = pending["previous_record"]
            previous_name = pending["previous_current"]
        if old is not None:
            require(isinstance(old, dict) and set(old) == {
                "schema_version", "paths", "previous_release", "integration_sha256"
            } and old["schema_version"] == 1, "Unknown installation record")
            require(old["paths"] == paths, "Upgrade must retain installation paths")
            require(isinstance(old["integration_sha256"], dict)
                    and set(old["integration_sha256"]) == set(generated),
                    "Unexpected managed integration path")
        require(previous_name is None or isinstance(previous_name, str) and RELEASE.fullmatch(previous_name),
                "Invalid previous current release")
        record = {"schema_version": 1, "paths": paths,
                  "previous_release": previous_name if previous_name != manifest["release_id"]
                  else (old or {}).get("previous_release"),
                  "integration_sha256": {name: digest(value[0]) for name, value in generated.items()}}
        if pending is not None:
            require(pending["record"] == record, "Pending installation does not match generated integrations")
        for filename, (data, _mode) in generated.items():
            path = Path(filename)
            if path.exists() or path.is_symlink():
                allowed = {(old or {}).get("integration_sha256", {}).get(filename)}
                if pending is not None:
                    allowed.add(digest(data))
                require(digest(regular_bytes(path)) in allowed,
                        f"Refusing to overwrite modified/unmanaged integration: {path}")
        releases = private_dir(prefix / "releases")
        release = releases / manifest["release_id"]
        if release.exists():
            require(verify_package(release) == manifest, "Release identifier collision")
        else:
            stage = Path(tempfile.mkdtemp(prefix=".new-", dir=releases))
            try:
                (stage / "bin").mkdir(mode=0o700)
                for name, file_record in manifest["files"].items():
                    (stage / name).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                    atomic_write(stage / name, regular_bytes(package / name), file_record["mode"])
                atomic_write(stage / "manifest.json", json_bytes(manifest), 0o644)
                verify_package(stage)
                for directory in sorted((p for p in stage.rglob("*") if p.is_dir()),
                                        key=lambda p: len(p.parts), reverse=True):
                    fsync_dir(directory)
                fsync_dir(stage)
                os.replace(stage, release)
                fsync_dir(releases)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        config = Path(paths["config"])
        if not config.exists():
            private_dir(config.parent)
            atomic_write(config, json_bytes(default_config()))
        else:
            load_config(config)
        if pending is None:
            # Persist ownership before the first integration becomes visible.
            # Resume accepts only the original bytes or this exact package's
            # generated bytes, never an arbitrary preexisting launcher.
            pending = {"schema_version": 1, "package_sha256": digest(json_bytes(manifest)),
                       "paths": paths, "previous_current": previous_name,
                       "previous_record": old, "record": record}
            atomic_write(pending_path, json_bytes(pending))
        for filename, (data, mode) in generated.items():
            path = Path(filename)
            path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
            info = path.parent.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
                    and not stat.S_IMODE(info.st_mode) & 0o022,
                    f"Integration directory must be real, owned and not writable by others: {path.parent}")
            atomic_write(path, data, mode)
        atomic_write(record_path, json_bytes(record))
        switch_release(prefix, release.name)
        pending_path.unlink()
        fsync_dir(prefix)
    return {"installed_release": release.name, "previous_release": record["previous_release"],
            "configuration": str(config), "user_data_changed": False}


def default_config():
    return {"schema_version": 1, "renderer": "egui", "makepad_resources": None,
            "cjk_font": None, "observer": None, "draft_recovery": True,
            "notes_state_dir": None, "chat": None,
            "shell_page": "conversation"}


def load_config(path):
    info = Path(path).lstat()
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600,
            "Configuration must be a user-owned 0600 file")
    cfg = read_json(path, 64 * 1024)
    # Optional extension: existing schema-1 installations are read without
    # rewriting their configuration during upgrades or diagnostics.
    require(isinstance(cfg, dict), "Unknown configuration schema")
    cfg.setdefault("chat", None)
    require(set(cfg) == set(default_config()) and cfg["schema_version"] == 1, "Unknown configuration schema")
    require(cfg["renderer"] in ("egui", "makepad"), "Unsupported renderer")
    require(type(cfg["draft_recovery"]) is bool, "draft_recovery must be true or false")
    require(cfg["shell_page"] in ("conversation", "hepta", "tasks", "apps", "workspaces", "console", "settings"), "Unsupported Shell page")
    for key in ("cjk_font", "makepad_resources", "notes_state_dir"):
        value = cfg[key]
        require(value is None or isinstance(value, str) and Path(value).is_absolute(), f"{key} must be an absolute path or null")
    chat = cfg["chat"]
    if chat is not None:
        require(isinstance(chat, dict) and set(chat) == {"socket", "root_pid"}, "Incomplete chat lane configuration")
        require(isinstance(chat["socket"], str) and Path(chat["socket"]).is_absolute()
                and not any(ord(char) < 32 for char in chat["socket"]), "Chat socket must be an absolute path")
        unix_socket_path(chat["socket"], "Chat socket")
        require(type(chat["root_pid"]) is int and 0 < chat["root_pid"] < 2**31, "Invalid chat Root PID")
    observer = cfg["observer"]
    if observer is not None:
        require(isinstance(observer, dict) and set(observer) == {"socket", "agent_id", "spawn_generation", "peer_uid", "run_id"}, "Incomplete observer configuration")
        require(isinstance(observer["socket"], str) and Path(observer["socket"]).is_absolute(), "Observer socket must be absolute")
        unix_socket_path(observer["socket"], "Observer socket")
        require(isinstance(observer["agent_id"], str) and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", observer["agent_id"]), "Invalid observer agent id")
        require(type(observer["spawn_generation"]) is int and 0 < observer["spawn_generation"] < 2**64, "Invalid observer generation")
        require(type(observer["peer_uid"]) is int and 0 <= observer["peer_uid"] < 2**32, "Invalid observer UID")
        require(observer["run_id"] is None or isinstance(observer["run_id"], str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", observer["run_id"]), "Invalid observer run id")
    return cfg


def require_no_pending_rollback(prefix):
    pending = Path(prefix) / "rollback.pending.json"
    require(not pending.exists() and not pending.is_symlink(),
            "Rollback is incomplete; rerun rollback to complete the recorded target")


def validate_installation_record(prefix, record):
    require(isinstance(record, dict)
            and set(record) == {"schema_version", "paths", "previous_release", "integration_sha256"}
            and record["schema_version"] == 1, "Unknown installation record")
    expected = integrations(prefix, record["paths"])
    require(isinstance(record["integration_sha256"], dict)
            and set(record["integration_sha256"]) == set(expected), "Unexpected managed integration path")
    require(all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                for value in record["integration_sha256"].values()), "Invalid managed integration checksum")
    return record


def installed(prefix):
    pending = Path(prefix) / "installation.pending.json"
    require(not pending.exists() and not pending.is_symlink(),
            "Installation is incomplete; rerun install with the same package and paths")
    require_no_pending_rollback(prefix)
    record = validate_installation_record(prefix, read_json(Path(prefix) / "installation.json"))
    release = current_release(prefix)
    require(release is not None, "No installed current release")
    manifest = verify_package(release)
    return record, release, manifest, load_config(record["paths"]["config"])


def runtime_environment(cfg, prepare_state=True, release=None):
    env = dict(os.environ)
    runtime = env.get("XDG_RUNTIME_DIR")
    require(runtime and Path(runtime).is_absolute(), "Run inside an existing user graphical session (XDG_RUNTIME_DIR is missing)")
    session_socket_path(runtime)
    info = Path(runtime).lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "XDG_RUNTIME_DIR must be owned by this user and 0700")
    for key in OBSERVER_ENV:
        env.pop(key, None)
    # The chat worker authenticates the actual Root peer and retained UI pidfd.
    # These two values only locate that lane. An explicit installation setting
    # overrides an inherited pair; a partial inherited pair is an error.
    if cfg.get("chat") is not None:
        env["TRILL_UI_CHAT_SOCKET"] = cfg["chat"]["socket"]
        env["TRILL_UI_CHAT_ROOT_PID"] = str(cfg["chat"]["root_pid"])
    chat_socket = env.get("TRILL_UI_CHAT_SOCKET")
    chat_pid = env.get("TRILL_UI_CHAT_ROOT_PID")
    require((chat_socket is None) == (chat_pid is None), "Chat requires both TRILL_UI_CHAT_SOCKET and TRILL_UI_CHAT_ROOT_PID")
    if chat_socket is not None:
        require(Path(chat_socket).is_absolute() and not any(ord(char) < 32 for char in chat_socket), "Chat socket must be an absolute path")
        unix_socket_path(chat_socket, "Chat socket")
        require(chat_pid.isascii() and chat_pid.isdigit() and 0 < int(chat_pid) < 2**31, "Invalid chat Root PID")
    if cfg["observer"]:
        unix_socket_path(cfg["observer"]["socket"], "Observer socket")
        for key, field in zip(OBSERVER_ENV, ("socket", "agent_id", "spawn_generation", "peer_uid", "run_id")):
            if cfg["observer"][field] is not None:
                env[key] = str(cfg["observer"][field])
    state_root = Path(env.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    require(state_root.is_absolute(), "XDG_STATE_HOME must be absolute")
    notes = Path(cfg["notes_state_dir"] or str(state_root / "trillionnium-ui/notes"))
    # Notes itself creates/fsyncs its root. Ensure its existing parent is owned
    # and private; never chmod a user's preexisting shared directory.
    for directory in {state_root / "trillionnium-ui", notes.parent}:
        if prepare_state or directory.exists() or directory.is_symlink():
            private_dir(directory)
    env["TRILL_NOTES_STATE_DIR"] = str(notes)
    env["TRILL_UI_DRAFT_RECOVERY"] = "1" if cfg["draft_recovery"] else "0"
    for field, key in (("cjk_font", "TRILL_UI_CJK_FONT"), ("makepad_resources", "TRILL_UI_MAKEPAD_RESOURCES")):
        env.pop(key, None)
        if cfg[field]:
            require(Path(cfg[field]).exists(), f"Configured {field} is missing")
            env[key] = cfg[field]
    if cfg["renderer"] == "makepad":
        resources = cfg["makepad_resources"] or (str(Path(release) / "resources") if release else None)
        require(resources, "Makepad resources are required")
        native_resource_files(resources)
        env["TRILL_UI_MAKEPAD_RESOURCES"] = str(resources)
    return env


def require_owned_session(env, unit):
    """A same-UID listener alone is insufficient to identify our installed unit."""
    endpoint = session_socket_path(env["XDG_RUNTIME_DIR"])
    state = systemctl("show", unit, "--property=MainPID", "--value")
    require(state.stdout.strip().isdigit() and int(state.stdout.strip()) > 0,
            "Installed Session service has no live MainPID")
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(0.5)
        peer.connect(endpoint)
        pid, uid, _gid = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    require(pid == int(state.stdout.strip()) and uid == os.geteuid(),
            "Session socket is not owned by the installed user service")
    return pid


def rollback(prefix, activity_probe=require_stopped):
    prefix = Path(prefix)
    with install_lock(prefix):
        installation = prefix / "installation.pending.json"
        require(not installation.exists() and not installation.is_symlink(),
                "Installation is incomplete; rerun install with the same package and paths")
        pending_path = prefix / "rollback.pending.json"
        pending = None
        if pending_path.exists() or pending_path.is_symlink():
            info = pending_path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                    and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600,
                    "Invalid pending rollback file")
            pending = read_json(pending_path)
            require(isinstance(pending, dict) and set(pending) == {
                "schema_version", "before_release", "after_release", "previous_record", "record"
            } and pending["schema_version"] == 1, "Unknown pending rollback schema")
            before, previous = pending["before_release"], pending["after_release"]
            require(isinstance(before, str) and RELEASE.fullmatch(before)
                    and isinstance(previous, str) and RELEASE.fullmatch(previous)
                    and before != previous, "Invalid pending rollback releases")
            original = validate_installation_record(prefix, pending["previous_record"])
            record = validate_installation_record(prefix, pending["record"])
            require(original["previous_release"] == previous
                    and record == dict(original, previous_release=before),
                    "Pending rollback does not match its original target and records")
            actual = validate_installation_record(prefix, read_json(prefix / "installation.json"))
            require(actual in (original, record), "Installation record changed during interrupted rollback")
            current = current_release(prefix)
            require(current is not None and current.name in (before, previous),
                    "Current release changed during interrupted rollback")
            load_config(record["paths"]["config"])
        else:
            original, release, _manifest, _cfg = installed(prefix)
            before, previous = release.name, original["previous_release"]
            require(isinstance(previous, str) and RELEASE.fullmatch(previous) and previous != before,
                    "No previous installed release")
            record = dict(original, previous_release=before)
        for release_id in (before, previous):
            manifest = verify_package(prefix / "releases" / release_id)
            require(manifest["release_id"] == release_id, "Rollback release identity mismatch")
        # Rollback changes the selected release only. Never repair a user's
        # modified launcher, service or desktop entry while recovering it.
        for filename, checksum in record["integration_sha256"].items():
            path = Path(filename)
            if path.exists() or path.is_symlink():
                require(digest(regular_bytes(path)) == checksum,
                        f"Modified integration preserved; resolve it before rollback: {path}")
        activity_probe(record["paths"]["unit_name"])
        if pending is None:
            # Fix the destination before updating either the record or symlink.
            # Resumption must not reinterpret the already-updated previous_release.
            pending = {"schema_version": 1, "before_release": before, "after_release": previous,
                       "previous_record": original, "record": record}
            atomic_write(pending_path, json_bytes(pending))
        atomic_write(prefix / "installation.json", json_bytes(record))
        switch_release(prefix, previous)
        pending_path.unlink()
        fsync_dir(prefix)
        return {"current_release": previous, "user_data_changed": False}


def uninstall(prefix, activity_probe=require_stopped):
    prefix = Path(prefix)
    with install_lock(prefix):
        record, _release, _manifest, _cfg = installed(prefix)
        activity_probe(record["paths"]["unit_name"])
        for filename, checksum in record["integration_sha256"].items():
            path = Path(filename)
            if path.exists() or path.is_symlink():
                require(digest(regular_bytes(path)) == checksum, f"Modified integration preserved; resolve it before uninstall: {path}")
        for filename in record["integration_sha256"]:
            path = Path(filename)
            if path.exists():
                path.unlink()
                fsync_dir(path.parent)
        (prefix / "current").unlink()
        shutil.rmtree(prefix / "releases")
        (prefix / "installation.json").unlink()
        fsync_dir(prefix)
    # Keep the lock inode: replacing it permits two concurrent installers.
    return {"uninstalled": True, "configuration_preserved": record["paths"]["config"],
            "drafts_preserved": True, "state_directory_removed": False}


def doctor(prefix, live=False):
    record, release, manifest, cfg = installed(prefix)
    report = {"release_id": release.name, "desktop_commit": manifest["desktop_commit"],
              "hepta_commit": manifest["hepta_commit"], "package_integrity": "verified",
              "configuration": record["paths"]["config"], "renderer": cfg["renderer"],
              "observer_configured": cfg["observer"] is not None,
              "draft_recovery": cfg["draft_recovery"], "checks": {}, "errors": []}
    try:
        env = runtime_environment(cfg, prepare_state=False, release=release)
        report["chat_lane_configured"] = "TRILL_UI_CHAT_SOCKET" in env
        report["chat_authority_verified"] = False
        report["checks"]["runtime_directory"] = "ready"
        report["checks"]["graphical_environment"] = bool(env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"))
        if not report["checks"]["graphical_environment"]:
            report["errors"].append("No graphical display configured")
        state_root = Path(env.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
        require(state_root.is_absolute(), "XDG_STATE_HOME must be absolute")
        report["draft_directory"] = str(state_root / "trillionnium-ui")
    except (OSError, ProductError) as error:
        env = None
        report["errors"].append(str(error))
    try:
        state = systemctl("show", record["paths"]["unit_name"], "--property=ActiveState", "--value", check=False)
        report["checks"]["user_service_manager"] = state.returncode == 0
        report["checks"]["session_service"] = state.stdout.strip() if state.returncode == 0 else "unavailable"
        if state.returncode != 0:
            report["errors"].append("No user service manager; run from the intended graphical login")
    except (OSError, subprocess.TimeoutExpired) as error:
        report["errors"].append(str(error))
    if live and env:
        try:
            report["checks"]["session_service_pid"] = require_owned_session(env, record["paths"]["unit_name"])
            result = subprocess.run([str(release / "bin/trill-ctl"), "snapshot"], env=env,
                                    capture_output=True, timeout=3, check=True)
            require(len(result.stdout) <= 4 * 1024 * 1024, "Oversized snapshot")
            value = json.loads(result.stdout)
            require(value.get("type") == "snapshot", "Session did not return a snapshot")
            report["live_session"] = {"session_instance": value["session_instance"],
                                      "task_count": len(value["tasks"])}
        except (OSError, ValueError, ProductError, subprocess.SubprocessError) as error:
            report["errors"].append("Live Session snapshot failed: " + str(error))
    report["ready"] = not report["errors"]
    report["production_authority_verified"] = False
    return report


def run(prefix, session=False, _locked=False):
    if not session and not _locked:
        # Serialize start/readiness with upgrades. Python-created descriptors
        # are close-on-exec, so the lock releases when the Shell replaces us.
        with install_lock(prefix):
            return run(prefix, session=False, _locked=True)
    record, release, _manifest, cfg = installed(prefix)
    allowed_environment = {"DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR",
                           "DBUS_SESSION_BUS_ADDRESS", "XDG_CURRENT_DESKTOP", "XDG_STATE_HOME",
                           "WINIT_UNIX_BACKEND", "LIBGL_ALWAYS_SOFTWARE", "LP_NUM_THREADS",
                           "MESA_SHADER_CACHE_DISABLE"}
    if session:
        launch = Path(prefix) / "launch-environment.json"
        info = launch.lstat()
        require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600, "Invalid launch environment ownership")
        values = read_json(launch, 64 * 1024)
        require(isinstance(values, dict) and set(values) <= allowed_environment
                and all(isinstance(v, str) and "\x00" not in v for v in values.values()), "Invalid launch environment")
        for key in allowed_environment:
            os.environ.pop(key, None)
        os.environ.update(values)
    env = runtime_environment(cfg, release=release)
    if session:
        # The authenticated text lane belongs to this Shell process, not to
        # Session or its independent application children.
        env.pop("TRILL_UI_CHAT_SOCKET", None)
        env.pop("TRILL_UI_CHAT_ROOT_PID", None)
        program = release / "bin/trill-session"
        os.execve(program, [str(program)], env)
    require(env.get("WAYLAND_DISPLAY") or env.get("DISPLAY"), "No graphical display configured")
    atomic_write(Path(prefix) / "launch-environment.json",
                 json_bytes({key: env[key] for key in allowed_environment if key in env}))
    systemctl("daemon-reload")
    systemctl("start", record["paths"]["unit_name"])
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            require_owned_session(env, record["paths"]["unit_name"])
            ready = subprocess.run([str(release / "bin/trill-ctl"), "snapshot"], env=env,
                                   capture_output=True, timeout=1)
            if ready.returncode == 0 and json.loads(ready.stdout).get("type") == "snapshot":
                break
        except (OSError, ProductError, subprocess.TimeoutExpired, ValueError):
            pass
        time.sleep(0.1)
    else:
        raise ProductError("Session did not become ready; run doctor --live or inspect the user service journal")
    program = release / "bin/trill-shell"
    args = [str(program), "--page", cfg["shell_page"]]
    if cfg["renderer"] != "egui":
        args.extend(["--renderer", cfg["renderer"]])
    os.execve(program, args, env)


def main():
    home = Path.home()
    data = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share")))
    config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=data / "trillionnium-desktop")
    subs = parser.add_subparsers(dest="command", required=True)
    build = subs.add_parser("pack", help="wrap an existing verified A10 host binary bundle")
    build.add_argument("--host-archive", required=True, type=Path)
    build.add_argument("--expected-desktop", required=True)
    build.add_argument("--source-profile", required=True, type=Path)
    build.add_argument("--makepad-resources", type=Path,
                       help="include a complete bundle from prepare_native_makepad.py")
    build.add_argument("--output", required=True, type=Path)
    setup = subs.add_parser("install", help="install/upgrade this package for the current user")
    setup.add_argument("--package", type=Path, default=Path(__file__).resolve().parent)
    setup.add_argument("--bin-dir", type=Path, default=home / ".local/bin")
    setup.add_argument("--unit-dir", type=Path, default=config / "systemd/user")
    setup.add_argument("--applications-dir", type=Path, default=data / "applications")
    setup.add_argument("--unit-name", default=UNIT)
    setup.add_argument("--config", type=Path, default=config / "trillionnium-desktop/config.json")
    diagnose = subs.add_parser("doctor", help="validate bytes/configuration and report actionable diagnostics")
    diagnose.add_argument("--live", action="store_true")
    for command in ("run", "session", "stop", "rollback", "uninstall"):
        subs.add_parser(command)
    args = parser.parse_args()
    require(args.prefix.is_absolute(), "Installation prefix must be absolute")
    if args.command == "pack":
        result = pack(args.host_archive, args.expected_desktop, args.source_profile, args.output, args.makepad_resources)
    elif args.command == "install":
        paths = {name: str(getattr(args, name).absolute()) for name in ("bin_dir", "unit_dir", "applications_dir", "config")}
        paths["unit_name"] = args.unit_name
        result = install(args.package, args.prefix, paths)
        systemctl("daemon-reload")
    elif args.command == "doctor":
        result = doctor(args.prefix, args.live)
    elif args.command in ("run", "session"):
        run(args.prefix, args.command == "session")
        return 0
    elif args.command == "stop":
        record, _release, _manifest, _cfg = installed(args.prefix)
        systemctl("stop", record["paths"]["unit_name"])
        result = {"session_stopped": True, "note": "The service owns and stops its application process group."}
    elif args.command == "rollback":
        result = rollback(args.prefix)
    else:
        result = uninstall(args.prefix)
        systemctl("daemon-reload")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if args.command == "doctor" and not result["ready"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ProductError, OSError, ValueError, KeyError, TypeError, tarfile.TarError,
            subprocess.SubprocessError) as error:
        print("trillionnium-desktop: " + str(error), file=sys.stderr)
        sys.exit(1)
