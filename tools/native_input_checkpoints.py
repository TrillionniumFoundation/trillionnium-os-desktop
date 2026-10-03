#!/usr/bin/env python3
"""Exact three-pair native qualification stimulus; no event retry or cleanup Up.

Checkpoints come from current-generation Servo InputEventId callbacks in the
explicit host profile. This driver does not qualify installed or hardware input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

try:
    from .browser_codec_reference_security import load_json_strict, open_managed_regular_beneath
except ImportError:
    from browser_codec_reference_security import load_json_strict, open_managed_regular_beneath

MAX_BYTES = 4096
POINTS = ((200, 68), (400, 100), (200, 68))
NONCE = re.compile(r"[0-9a-f]{32}\Z")
EVENT_ID = re.compile(r"InputEventId\([0-9]{1,20}\)\Z")
FIELDS = {"schema", "nonce", "owner_pid", "owner_start_time", "generation", "sequence",
          "phase", "content_point", "pointer_event_id", "down_event_id", "up_event_id",
          "pointer_dispatch_accepted", "down_dispatch_accepted", "up_dispatch_accepted",
          "completed_pairs", "product_ready"}
CHECKPOINT_NAMES = {"input-pair-0-chrome_ready.json", "input-pair-0-prelude_ready.json"} | {
    f"input-pair-{sequence}-{phase}.json" for sequence in range(1, 4)
    for phase in ("ready", "down_accepted", "up_accepted")}
STIMULI = [
    ["mousemove", "200", "132"], ["mousemove", "10", "10"],
    ["mousedown", "1"], ["mouseup", "1"], ["click", "5"], ["key", "x"],
    ["mousemove", "200", "132"], ["mousedown", "1"], ["mouseup", "1"], ["key", "k"],
    ["mousemove", "400", "164"], ["mousedown", "1"], ["mouseup", "1"], ["click", "5"],
    ["mousemove", "200", "132"], ["mousedown", "1"], ["mouseup", "1"],
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def root_identity(root: Path) -> tuple[int, int]:
    for parent in (root, *root.parents):
        require(stat.S_ISDIR(parent.stat(follow_symlinks=False).st_mode),
                "input output root traverses an unsafe parent")
    metadata = root.stat(follow_symlinks=False)
    require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == os.getuid()
            and stat.S_IMODE(metadata.st_mode) == 0o700, "input output root is not a private directory")
    return metadata.st_dev, metadata.st_ino


def metadata_identity(item: os.stat_result) -> tuple[int, ...]:
    return (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns,
            item.st_ctime_ns, item.st_nlink, item.st_mode, item.st_uid)


def check_snapshots(root: Path, identity: tuple[int, int], snapshots: dict[str, tuple[int, ...]]) -> None:
    require(root_identity(root) == identity, "native input snapshot root changed")
    for name, expected in snapshots.items():
        require(metadata_identity((root / name).stat(follow_symlinks=False)) == expected,
                "an earlier native input checkpoint changed")
    require(root_identity(root) == identity, "native input snapshot root changed")


def load_private(root: Path, name: str, identity: tuple[int, int], *,
                 snapshots: dict[str, tuple[int, ...]] | None = None) -> tuple[dict, str]:
    require(root_identity(root) == identity, "input output root was replaced")
    try:
        reader = open_managed_regular_beneath(Path("/"), root.absolute() / name, label="native input checkpoint")
    except ValueError as error:
        if isinstance(error.__cause__, FileNotFoundError) and error.__cause__.filename == name:
            raise error.__cause__ from error
        raise
    with reader:
        before = reader.stat()
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_uid == os.getuid() and stat.S_IMODE(before.st_mode) == 0o600
                and 0 < before.st_size <= MAX_BYTES, "input checkpoint is not private bounded regular data")
        data = reader.read_some(MAX_BYTES + 1)
        after = reader.stat()
        try:
            named = (root / name).stat(follow_symlinks=False)
        except OSError as error:
            raise ValueError("input checkpoint disappeared after opening") from error
        require(len(data) == before.st_size
                and metadata_identity(before) == metadata_identity(after) == metadata_identity(named)
                and root_identity(root) == identity, "input checkpoint changed while reading")
        value = load_json_strict(data.decode("utf-8", "strict"))
        require(isinstance(value, dict), "input checkpoint must be a JSON object")
        if snapshots is not None:
            snapshots[name] = metadata_identity(after)
        return value, hashlib.sha256(data).hexdigest()


def process_start(pid: int) -> int:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    require(fields[0] not in {"Z", "X"}, "native owner already exited")
    return int(fields[19])


def validate_checkpoint(value: dict, *, nonce: str, pid: int, start: int,
                        sequence: int, phase: str) -> None:
    require(set(value) == FIELDS, "input checkpoint has unknown or missing fields")
    require(value["schema"] == "trillionnium.desktop.native-input-checkpoint.v1"
            and value["nonce"] == nonce, "input checkpoint belongs to another qualification run")
    for field, expected in (("owner_pid", pid), ("owner_start_time", start),
                            ("generation", 1), ("sequence", sequence)):
        require(type(value[field]) is int and value[field] == expected, "input checkpoint identity changed")
    require(value["phase"] == phase and value["product_ready"] is False,
            "input checkpoint phase or claim changed")
    chrome = phase == "chrome_ready"
    point = POINTS[0] if phase == "prelude_ready" else POINTS[sequence - 1]
    require(value["content_point"] is None if chrome else
            value["content_point"] == list(point)
            and all(type(item) is int for item in value["content_point"]),
            "input checkpoint is for another content point")
    expected = (not chrome, phase in {"down_accepted", "up_accepted"}, phase == "up_accepted")
    for field, accepted in zip(("pointer_dispatch_accepted", "down_dispatch_accepted",
                                "up_dispatch_accepted"), expected):
        require(value[field] is accepted, "input checkpoint has no matching accepted dispatch")
    for field, present in zip(("pointer_event_id", "down_event_id", "up_event_id"), expected):
        item = value[field]
        require(isinstance(item, str) and EVENT_ID.fullmatch(item) is not None if present
                else item is None, "input checkpoint has an invalid actual event identifier")
    ids = [value[field] for field in ("pointer_event_id", "down_event_id", "up_event_id")
           if value[field] is not None]
    require(len(set(ids)) == len(ids), "input checkpoint reuses an event identifier")
    completed = sequence if phase == "up_accepted" else max(0, sequence - 1)
    require(type(value["completed_pairs"]) is int and value["completed_pairs"] == completed,
            "input checkpoint completed-pair count does not bind its event sequence")


class Driver:
    def __init__(self, root: Path, pid: int, window: int, nonce: str, timeout: float = 30):
        require(NONCE.fullmatch(nonce) is not None and type(pid) is int and pid > 1
                and type(window) is int and window > 0 and 0 < timeout <= 60,
                "invalid native stimulus owner, nonce, window or deadline")
        self.root = root.absolute()
        self.identity = root_identity(self.root)
        # A repeated invocation cannot consume old current-generation markers.
        # The source owner also refuses replay; this guard prevents stimuli
        # before discovering that refusal from a later callback or result.
        for name in CHECKPOINT_NAMES | {"input-stimulus.json"}:
            try:
                (self.root / name).stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise ValueError("native stimulus already has a checkpoint or receipt; replay is refused")
        self.pid, self.window, self.nonce = pid, window, nonce
        self.start = process_start(pid)
        self.deadline = time.monotonic() + timeout
        self.commands: list[list[str]] = []
        self.digests: dict[str, str] = {}
        self.records: dict[str, dict] = {}
        self.snapshots: dict[str, tuple[int, ...]] = {}

    def remaining(self) -> float:
        require(time.monotonic() < self.deadline, "native stimulus absolute deadline expired")
        require(process_start(self.pid) == self.start, "native stimulus owner incarnation changed")
        require(root_identity(self.root) == self.identity, "native stimulus output root changed")
        check_snapshots(self.root, self.identity, self.snapshots)
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "native stimulus absolute deadline expired")
        return remaining

    def command(self, arguments: list[str]) -> str:
        return subprocess.run(["xdotool", *arguments], check=True, capture_output=True,
                              text=True, timeout=min(5, self.remaining())).stdout.strip()

    def focus(self) -> None:
        require(self.command(["getwindowpid", str(self.window)]) == str(self.pid),
                "native X11 window belongs to another process")
        require(self.command(["getwindowfocus"]) == str(self.window), "native window lost actual X11 focus")

    def stimulus(self, arguments: list[str]) -> None:
        self.focus()
        # Record an attempted command before any possible XTest effect. Failure
        # terminates this sequence; nothing resends it or injects a cleanup Up.
        self.commands.append(arguments)
        actual = arguments if arguments[0] != "mousemove" else [
            "mousemove", "--sync", "--window", str(self.window), *arguments[1:]]
        self.command(actual)

    def wait(self, sequence: int, phase: str) -> dict:
        name = f"input-pair-{sequence}-{phase}.json"
        while True:
            self.remaining()
            try:
                value, digest = load_private(self.root, name, self.identity, snapshots=self.snapshots)
            except FileNotFoundError:
                time.sleep(min(0.01, self.remaining()))
                continue
            validate_checkpoint(value, nonce=self.nonce, pid=self.pid, start=self.start,
                                sequence=sequence, phase=phase)
            self.focus()
            self.records[name], self.digests[name] = value, digest
            return value

    def run(self) -> None:
        self.stimulus(STIMULI[0])
        self.wait(0, "prelude_ready")
        self.stimulus(STIMULI[1])
        self.wait(0, "chrome_ready")
        for arguments in STIMULI[2:6]:
            self.stimulus(arguments)
        for sequence, offset in ((1, 6), (2, 10), (3, 14)):
            self.stimulus(STIMULI[offset])
            ready = self.wait(sequence, "ready")
            self.stimulus(STIMULI[offset + 1])
            down = self.wait(sequence, "down_accepted")
            require(down["pointer_event_id"] == ready["pointer_event_id"], "Down did not bind the ready pointer")
            self.stimulus(STIMULI[offset + 2])
            up = self.wait(sequence, "up_accepted")
            require(up["pointer_event_id"] == ready["pointer_event_id"]
                    and up["down_event_id"] == down["down_event_id"], "Up did not bind this issued pair")
            if sequence < 3:
                self.stimulus(STIMULI[offset + 3])
        require(self.commands == STIMULI, "native stimulus did not issue exactly the original sequence")

    def receipt(self, status: str) -> None:
        value = {"schema": "trillionnium.desktop.native-input-stimulus.v1", "status": status,
                 "nonce": self.nonce, "owner_pid": self.pid, "owner_start_time": self.start,
                 "window_id": self.window, "commands": self.commands,
                 "checkpoint_sha256": self.digests, "product_ready": False}
        require(root_identity(self.root) == self.identity, "native receipt output root changed")
        directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            metadata = os.fstat(directory)
            require((metadata.st_dev, metadata.st_ino) == self.identity
                    and root_identity(self.root) == self.identity, "native receipt root custody changed")
            descriptor = os.open("input-stimulus.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                 | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory)
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
            require(root_identity(self.root) == self.identity, "native receipt root changed during publication")
        finally:
            os.close(directory)


def verify(root: Path, nonce: str, pid: int, *, expected_identity: tuple[int, int] | None = None) -> None:
    identity = root_identity(root)
    require(expected_identity is None or identity == expected_identity, "native verification output root changed")
    snapshots: dict[str, tuple[int, ...]] = {}
    receipt, _ = load_private(root, "input-stimulus.json", identity, snapshots=snapshots)
    fields = {"schema", "status", "nonce", "owner_pid", "owner_start_time", "window_id",
              "commands", "checkpoint_sha256", "product_ready"}
    require(set(receipt) == fields and receipt["schema"] == "trillionnium.desktop.native-input-stimulus.v1"
            and receipt["status"] == "HOST_STIMULUS_COMPLETE" and receipt["nonce"] == nonce
            and type(receipt["owner_pid"]) is int and receipt["owner_pid"] == pid
            and type(receipt["owner_start_time"]) is int and receipt["owner_start_time"] > 0
            and type(receipt["window_id"]) is int and receipt["window_id"] > 0
            and receipt["commands"] == STIMULI and receipt["product_ready"] is False,
            "native input stimulus is incomplete or for another owner")
    names = CHECKPOINT_NAMES
    require(isinstance(receipt["checkpoint_sha256"], dict) and set(receipt["checkpoint_sha256"]) == names,
            "native input stimulus has an incomplete checkpoint inventory")
    records = {}
    for name in sorted(names):
        value, digest = load_private(root, name, identity, snapshots=snapshots)
        sequence, phase = name.removeprefix("input-pair-").removesuffix(".json").split("-", 1)
        validate_checkpoint(value, nonce=nonce, pid=pid, start=receipt["owner_start_time"],
                            sequence=int(sequence), phase=phase)
        require(digest == receipt["checkpoint_sha256"][name], "input checkpoint changed after actual stimulus")
        records[name] = value
    all_ids = [records["input-pair-0-prelude_ready.json"]["pointer_event_id"]]
    for sequence in range(1, 4):
        ready, down, up = [records[f"input-pair-{sequence}-{phase}.json"]
                           for phase in ("ready", "down_accepted", "up_accepted")]
        require(ready["pointer_event_id"] == down["pointer_event_id"] == up["pointer_event_id"]
                and down["down_event_id"] == up["down_event_id"], "native input pair identity changed")
        all_ids.extend(up[field] for field in ("pointer_event_id", "down_event_id", "up_event_id"))
    require(len(set(all_ids)) == 10, "native input sequences reuse actual event identifiers")
    check_snapshots(root, identity, snapshots)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("drive", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--window", type=int)
    args = parser.parse_args()
    if args.mode == "verify":
        require(NONCE.fullmatch(args.nonce) is not None and args.pid > 1, "invalid verification owner")
        verify(args.output.absolute(), args.nonce, args.pid)
        return
    driver = Driver(args.output, args.pid, args.window, args.nonce)
    try:
        driver.run()
    except BaseException:
        try:
            driver.receipt("FAILED_NO_REPLAY")
        except (OSError, ValueError):
            pass
        raise
    driver.receipt("HOST_STIMULUS_COMPLETE")
    verify(args.output.absolute(), args.nonce, args.pid, expected_identity=driver.identity)


if __name__ == "__main__":
    main()
