"""Identity gates for the actual installed-product qualification harness."""

import hashlib
import os
from pathlib import Path
import re
import select
import stat

import desktop


LANE_PREFIXES = ("TRILL_", "HEPTA_")
LOCAL_UI_ENV = {"TRILL_NOTES_STATE_DIR", "TRILL_UI_DRAFT_RECOVERY",
                "TRILL_UI_MAKEPAD_RESOURCES", "TRILL_UI_CJK_FONT"}
KNOWN_EXECUTION_LANES = set(desktop.OBSERVER_ENV) | {
    "TRILL_UI_CHAT_SOCKET", "TRILL_UI_CHAT_ROOT_PID",
    "TRILL_OBJECTIVE_HOST_SOCKET", "TRILL_OBJECTIVE_HOST_PID",
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def pinned_package(package, manifest_sha256):
    require(re.fullmatch("[0-9a-f]{64}", manifest_sha256) is not None,
            "expected manifest pin must be 64 lowercase hex characters")
    path = Path(package) / "manifest.json"
    before = desktop.regular_bytes(path)
    require(desktop.digest(before) == manifest_sha256, "package differs from its supplied build manifest pin")
    manifest = desktop.verify_package(package)
    require(desktop.regular_bytes(path) == before, "package manifest changed during verification")
    return manifest


def isolated_environment(source):
    """Remove lane locators from our children, retaining the original user bus."""
    return {key: value for key, value in source.items() if not key.startswith(LANE_PREFIXES)}


def manager_lane_names(raw):
    # The user manager API returns values; consume only names and never retain,
    # print or put those private values into the qualification evidence.
    require(len(raw) <= 4 * 1024 * 1024, "user manager environment exceeds inspection bound")
    names = set()
    for line in raw.splitlines():
        encoded = line.partition(b"=")[0]
        if encoded.startswith((b"TRILL_", b"HEPTA_")):
            name = encoded.decode("ascii", "strict")
            require(re.fullmatch("[A-Za-z_][A-Za-z0-9_]*", name), "invalid manager lane variable name")
            names.add(name)
    return names


def process_identity(pid, binary, expected_sha256):
    """Inspect a live actual process, not a self-reported PID in a JSON reply."""
    require(type(pid) is int and pid > 1 and hasattr(os, "pidfd_open"), "live Linux pidfd identity required")
    binary = Path(binary).resolve(strict=True)
    handle = os.pidfd_open(pid)
    try:
        proc = Path("/proc") / str(pid)
        raw = (proc / "stat").read_text()
        start = raw.rsplit(")", 1)[1].split()[19]
        require(start.isdigit(), "invalid actual process start time")
        require(os.readlink(proc / "exe") == str(binary), "actual process did not execute the installed binary")
        wanted = binary.stat()
        checksum = hashlib.sha256()
        count = 0
        with (proc / "exe").open("rb") as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_size <= desktop.MAX_FILE
                    and (info.st_dev, info.st_ino) == (wanted.st_dev, wanted.st_ino),
                    "actual process image differs from the installed inode")
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                count += len(chunk)
                require(count <= desktop.MAX_FILE, "actual process image grew beyond its bound")
                checksum.update(chunk)
        require(checksum.hexdigest() == expected_sha256, "actual process image failed its package hash")
        require((proc / "stat").read_text().rsplit(")", 1)[1].split()[19] == start
                and not select.select([handle], [], [], 0)[0], "actual process exited or changed during observation")
        raw_environment = (proc / "environ").read_bytes()
        require(len(raw_environment) <= 4 * 1024 * 1024, "process environment exceeds inspection bound")
        native = {}
        for entry in raw_environment.split(b"\0"):
            key, sep, value = entry.partition(b"=")
            if sep and key.startswith((b"TRILL_", b"HEPTA_")):
                native[key.decode("ascii")] = value.decode("utf-8", "strict")
        require(set(native) <= LOCAL_UI_ENV, "isolated product inherited a host execution lane")
        command = (proc / "cmdline").read_bytes().decode("utf-8", "strict").rstrip("\0").split("\0")
        require(not select.select([handle], [], [], 0)[0], "actual process exited before identity completed")
        return {"pid": pid, "start_ticks": start, "executable": str(binary),
                "executable_sha256": checksum.hexdigest(), "device": info.st_dev, "inode": info.st_ino,
                "argv": command, "local_ui_environment": native}
    finally:
        os.close(handle)
