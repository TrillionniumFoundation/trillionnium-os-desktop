"""Identity gates for the actual installed-product qualification harness."""

import hashlib
import os
from pathlib import Path
import re
import select
import stat
import time

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


def runtime_root_identity(path):
    """Check the caller's short private root without creating or deleting it."""
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path,
            "--runtime-root must be an existing absolute canonical directory")
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid()
            and stat.S_IMODE(info.st_mode) == 0o700,
            "--runtime-root must be a real user-owned 0700 directory")
    socket_path = desktop.session_socket_path(path)
    # Reserve room for a temporary bus name beneath the private TMPDIR too.
    # The real user-manager bus remains the inherited, unchanged endpoint.
    desktop.unix_socket_path(path / "tmp" / ("dbus-" + "x" * 32), "Temporary bus socket budget under --runtime-root")
    return {"path": str(path), "device": info.st_dev, "inode": info.st_ino,
            "session_socket": socket_path, "session_socket_bytes": len(os.fsencode(socket_path))}


def pinned_package(package, manifest_sha256):
    require(re.fullmatch("[0-9a-f]{64}", manifest_sha256) is not None,
            "expected manifest pin must be 64 lowercase hex characters")
    path = Path(package) / "manifest.json"
    before = desktop.regular_bytes(path)
    require(desktop.digest(before) == manifest_sha256, "package differs from its supplied build manifest pin")
    manifest = desktop.verify_package(package)
    require(desktop.regular_bytes(path) == before, "package manifest changed during verification")
    return manifest


def native_package_identity(package, manifest_sha256, build):
    """Join the real distribution ELF and resources to one completed build.

    This checks input identity, not compiler execution or native UI behavior.
    The caller must run the existing input tests and repeat this check afterward.
    """
    manifest = pinned_package(package, manifest_sha256)
    require(build.get("schema") == "trill.linux-text-build-receipt.v1"
            and build.get("status") == "passed" and build.get("exit_code") == 0,
            "native package requires a successful original text product build receipt")
    require(build.get("source_commit") == manifest["desktop_commit"]
            and build.get("hepta", {}).get("commit") == manifest["hepta_commit"],
            "package and build receipt have different Desktop/Hepta sources")
    require(build.get("profile", {}).get("renderer") == "makepad"
            and build.get("package", {}).get("release_id") == manifest["release_id"],
            "package is not the exact Makepad release in the build receipt")
    binaries = {name: {key: manifest["files"]["bin/" + name][key]
                       for key in ("sha256", "bytes")} for name in desktop.PROGRAMS}
    require(build.get("packaged_binaries") == binaries,
            "package programs differ from the build's distribution ELF inventory")
    resources = {name.removeprefix("resources/"): record["sha256"]
                 for name, record in manifest["files"].items() if name.startswith("resources/")}
    require(bool(resources) and resources == build.get("resources"),
            "package resources differ from the build's complete native inventory")
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


def remaining_timeout(deadline, maximum):
    """Spend one existing deadline; a retry never creates another budget."""
    remaining = deadline - time.monotonic()
    require(remaining > 0, "owned-window startup deadline expired")
    return min(remaining, maximum)


def window_identity(observation, pid, expected_window=None):
    require(type(observation.get("matched")) is bool, "invalid original XRes observation")
    if not observation["matched"]:
        require(observation.get("window") is None, "unmatched XRes observation contains a window")
        return None
    window = observation.get("window")
    require(isinstance(window, dict) and type(window.get("pid")) is int
            and window["pid"] == pid, "XRes returned a foreign window owner")
    xid = window.get("xid")
    require(type(xid) is int and 0 < xid <= 0xFFFFFFFF, "invalid XRes window resource ID")
    require(expected_window is None or xid == expected_window, "owned X11 window changed during observation")
    return xid


def nonuniform_window_frame(frame, window):
    require(type(frame.get("window")) is int and frame["window"] == window,
            "capture did not use the verified owned X11 window")
    require(type(frame.get("nonuniform_rgb")) is bool, "capture omitted its RGB content observation")
    return frame["nonuniform_rgb"]


def require_live_pidfd(handle, pid):
    require(not select.select([handle], [], [], 0)[0], "owned process exited during window observation")
    fdinfo = dict(line.split(":", 1) for line in Path(f"/proc/self/fdinfo/{handle}").read_text().splitlines())
    # fdinfo's Pid is relative to the procfs mount, which can be outside our
    # PID namespace. Select our namespace's entry, including for nested children.
    own_depth = next(len(line.split(":", 1)[1].split())
                     for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("NSpid:"))
    namespace_pids = fdinfo.get("NSpid", "").split()
    require(own_depth > 0 and len(namespace_pids) >= own_depth
            and namespace_pids[own_depth - 1] == str(pid), "pidfd belongs to a different process")


def require_same_process(handle, identity):
    """Recheck the live pidfd retained throughout XRes and pixel observation."""
    require_live_pidfd(handle, identity["pid"])
    proc = Path("/proc") / str(identity["pid"])
    require((proc / "stat").read_text().rsplit(")", 1)[1].split()[19] == identity["start_ticks"],
            "owned process start time changed during window observation")
    info = (proc / "exe").stat()
    require((info.st_dev, info.st_ino) == (identity["device"], identity["inode"])
            and os.readlink(proc / "exe") == identity["executable"],
            "owned process image changed during window observation")
    command = (proc / "cmdline").read_bytes().decode("utf-8", "strict").rstrip("\0").split("\0")
    require(command == identity["argv"], "owned process arguments changed during window observation")
    require(not select.select([handle], [], [], 0)[0], "owned process exited before window observation completed")


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
