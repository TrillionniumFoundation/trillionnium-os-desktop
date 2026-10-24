"""Inspect both actual stopped ext2 images without mutating their bytes.

debugfs receives an inherited read-only descriptor to a retained copy. Every
command/byte output is retained; this copy is never the next boot's drive.
SQLite runs only on a separate private extraction with its actual WAL.
"""
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import time

import native_owner_evidence as e
import native_owner_inputs as inputs
import native_owner_state_observations as ext2
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_store as store
import native_owner_prior_boot_types as t
import run_native_owner as original


def directory_entries(raw):
    """Read ordinary ext2 ancestors, including mkfs's actual lost+found.

    The existing launch-observation parser intentionally permits a narrower
    final record directory. This independent traversal preserves its complete
    slash/field/type checks and allows '+' in ordinary ancestor entry names.
    """
    e.require(type(raw) is bytes and len(raw) <= 65536, "bounded complete original ext2 directory required")
    result = {}
    for line in raw.decode("ascii").splitlines():
        if not line:
            continue
        parts = line.split("/")
        e.require(len(parts) == 8 and parts[0] == parts[-1] == ""
                  and all(re.fullmatch(r"[0-9]+", parts[index]) for index in (1, 3, 4))
                  and re.fullmatch(r"[0-7]{6}", parts[2])
                  and re.fullmatch(r"[A-Za-z0-9_.+-]+", parts[5]) and parts[5] not in result
                  and (parts[6] == "" or re.fullmatch(r"[0-9]+", parts[6])),
                  "original ext2 directory contains ambiguous, repeated or unsupported entries")
        result[parts[5]] = {"inode": int(parts[1]), "mode": int(parts[2], 8), "uid": int(parts[3]),
                            "gid": int(parts[4]), "bytes": None if not parts[6] else int(parts[6])}
    e.require("." in result and ".." in result, "actual original directory entries are incomplete")
    return result


class Disk:
    def __init__(self, image, expected_sha256, tool, tool_identity, output):
        self.image, self.tool, self.output = Path(image), Path(tool), Path(output)
        e.require(self.image.is_absolute() and self.image.resolve(strict=True) == self.image and not self.image.is_symlink()
                  and self.tool.is_absolute() and not self.output.exists() and self.output.is_absolute(),
                  "new private stopped-image extraction and canonical input required")
        e.require(tool_identity["path"] == str(self.tool) and inputs.sha(self.tool) == tool_identity["sha256"],
                  "actual read-only ext2 inspection binary differs")
        self.expected, self.tool_identity = e.digest(expected_sha256, "stopped physical image"), tool_identity
        e.require(inputs.sha(self.image) == self.expected and self.image.stat().st_size == original.STATE_BYTES,
                  "stopped physical image bytes differ before independent inspection")
        self.output.mkdir(mode=0o700)
        self.fd = os.open(self.image, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        metadata = os.fstat(self.fd)
        e.require(stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1, "unique stopped physical image required")
        self.identity = (metadata.st_dev, metadata.st_ino, metadata.st_size)
        self.commands, self.dirs, self.listings = [], {}, {}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        try:
            held, named = os.fstat(self.fd), self.image.lstat()
            e.require((held.st_dev, held.st_ino, held.st_size) == (named.st_dev, named.st_ino, named.st_size) == self.identity
                      and inputs.sha(self.image) == self.expected and inputs.sha(self.tool) == self.tool_identity["sha256"],
                      "actual read-only extraction changed its stopped image or selected tool")
        finally:
            os.close(self.fd)
            self.fd = None

    @staticmethod
    def physical(path):
        e.text(path, "actual guest physical path", 4096)
        if path == "/state":
            return "/"
        e.require(path.startswith(t.BASE + "/") or path == t.BASE,
                  "physical observation escaped the fixed native installation")
        e.require(re.fullmatch(r"/[A-Za-z0-9_.:/-]+", path) and all(part not in ("", ".", "..") for part in path.split("/")[1:]),
                  "ambiguous guest filesystem path")
        if path == t.PROTECTED or path.startswith(t.PROTECTED + "/"):
            path = t.BASE + "/protected-source" + path[len(t.PROTECTED):]
        return path.removeprefix("/state")

    def command(self, query, maximum):
        e.require(type(query) is str and re.fullmatch(r"(?:stat |ls -p |cat )(?:/[A-Za-z0-9_.:/-]*|<[1-9][0-9]*>)", query),
                  "only the fixed read-only ext2 observation verbs are allowed")
        index = len(self.commands)
        out, err = self.output / f"{index:03d}.stdout", self.output / f"{index:03d}.stderr"
        argv = [str(self.tool), "-R", query, "/proc/self/fd/" + str(self.fd)]
        receipt = {"argv": argv, "source_image": str(self.image), "source_sha256": self.expected,
                   "pass_fds": [self.fd], "source_host_device": self.identity[0], "source_host_inode": self.identity[1],
                   "exit_code": None, "timed_out": False, "tool": self.tool_identity}
        started = time.monotonic()
        with out.open("xb") as stdout, err.open("xb") as stderr:
            try:
                child = subprocess.run(argv, env=original.ENV, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                       pass_fds=(self.fd,), timeout=20, check=False)
                receipt["exit_code"] = child.returncode
            except subprocess.TimeoutExpired:
                receipt["timed_out"] = True
        receipt["elapsed_seconds"] = time.monotonic() - started
        for key, path in (("stdout", out), ("stderr", err)):
            path.chmod(0o444)
            receipt[key] = {"path": str(path), "bytes": path.stat().st_size, "sha256": inputs.sha(path)}
        self.commands.append(receipt)
        original.save(self.output / f"{index:03d}.json", receipt)
        e.require(receipt["exit_code"] == 0 and not receipt["timed_out"]
                  and out.stat().st_size <= maximum and err.stat().st_size <= 256
                  and ext2.BANNER.fullmatch(err.read_bytes()),
                  "actual read-only ext2 command failed, exceeded its bound or reported a path/filesystem error")
        return out.read_bytes(), receipt["stdout"]

    def directory(self, path, uid=None, mode=None):
        physical = self.physical(path)
        parts = PurePosixPath(physical).parts
        for size in range(1, len(parts) + 1):
            current = str(PurePosixPath(*parts[:size]))
            if current not in self.dirs:
                raw, _ = self.command("stat " + current, 65536)
                metadata = ext2.inode_stat(raw)
                e.require(metadata["kind"] == "directory", "original physical ancestor is not a directory")
                if (current in ("/", "/hepta-native", "/hepta-native/protected-source")
                        or current.startswith("/hepta-native/protected-source/")):
                    e.require(metadata["uid"] == 0 and metadata["mode"] & 0o022 == 0,
                              "original protected ancestor changed its Root ownership or write boundary")
                if current != "/":
                    parent = str(PurePosixPath(current).parent)
                    entry = self.entries_physical(parent).get(PurePosixPath(current).name)
                    e.require(entry is not None and entry["inode"] == metadata["inode"]
                              and entry["mode"] == (stat.S_IFDIR | metadata["mode"])
                              and entry["uid"] == metadata["uid"] and entry["gid"] == metadata["gid"],
                              "original ancestor is a symlink, alias or a different physical directory entry")
                self.dirs[current] = metadata
        metadata = self.dirs[physical]
        if uid is not None:
            e.require(metadata["uid"] == uid and metadata["gid"] == uid,
                      "original private directory changed its actual owner/group")
        if mode is not None:
            e.require(metadata["mode"] == mode, "original private directory mode changed")
        return metadata

    def entries_physical(self, physical):
        if physical not in self.listings:
            e.require(physical in self.dirs, "directory must be independently identified before listing")
            raw, _ = self.command("ls -p <" + str(self.dirs[physical]["inode"]) + ">", 65536)
            result = directory_entries(raw)
            e.require(result["."]["inode"] == self.dirs[physical]["inode"], "original directory self identity differs")
            if physical != "/":
                parent = str(PurePosixPath(physical).parent)
                e.require(result[".."]["inode"] == self.dirs[parent]["inode"], "original physical directory parent differs")
            self.listings[physical] = result
        return self.listings[physical]

    def entries(self, path):
        self.directory(path)
        return self.entries_physical(self.physical(path))

    def regular(self, path, uid, mode, maximum, minimum=0):
        parent, name = str(PurePosixPath(path).parent), PurePosixPath(path).name
        self.directory(parent)
        entry = self.entries(parent).get(name)
        e.require(entry is not None, "original physical file is missing: " + path)
        raw, _ = self.command("stat " + self.physical(path), 65536)
        metadata = ext2.inode_stat(raw)
        e.require(metadata["kind"] == "regular" and metadata["uid"] == uid and metadata["gid"] == uid
                  and metadata["mode"] == mode and metadata["links"] == 1
                  and minimum <= metadata["bytes"] <= maximum
                  and entry["inode"] == metadata["inode"] and entry["mode"] == (stat.S_IFREG | mode)
                  and entry["uid"] == uid and entry["gid"] == uid and entry["bytes"] == metadata["bytes"],
                  "actual original file is not its exact unique private regular inode: " + path)
        return metadata

    def read(self, path, uid, mode, maximum, allow_empty=False):
        inode = self.regular(path, uid, mode, maximum, 0 if allow_empty else 1)
        raw, retained = self.command("cat <" + str(inode["inode"]) + ">", maximum)
        e.require(len(raw) == inode["bytes"], "original physical file read was truncated")
        return {"guest_path": path, "physical_path": self.physical(path), "inode": inode,
                "raw": raw, "sha256": retained["sha256"], "retained_file": retained}

    @staticmethod
    def public(record):
        return {key: value for key, value in record.items() if key != "raw"}


def material_path(current):
    cut = e.ordered(current["head"]["last_current"], e.CUT_KEYS, "actual exact material cut")
    digest = hashlib.sha256(e.canonical(cut).encode()).hexdigest()
    return t.AUTHORITY + "/material/" + digest + "/agents/" + t.AGENT + "/cognitive/cognitive_1.sqlite3"


def saved_observation(disk, transcript):
    value = transcript["cut_event"] if transcript["phase"] == "fresh" else transcript["adoption_event"]
    directory = disk.directory(t.OBSERVATIONS, 0, 0o700)
    name = t.cut_filename(value["observation_id"])
    e.require(set(disk.entries(t.OBSERVATIONS)) == {".", "..", name, name + ".lock"},
              "same-disk prior-boot case contains missing or unexpected original Root observations")
    lock = disk.read(t.OBSERVATIONS + "/" + name + ".lock", 0, 0o600, 0, allow_empty=True)
    record = disk.read(t.OBSERVATIONS + "/" + name, 0, 0o600, 16384)
    wrapper = e.obj(e.json_value(record["raw"]), ("schema_version", "observation_id", "payload"), "actual original stored Root cut")
    expected = {"schema_version": 1, "observation_id": value["observation_id"],
                "payload": list(value["durable_payload_json"].encode())}
    e.require(wrapper == expected and record["raw"] == e.canonical(expected).encode()
              and hashlib.sha256(bytes(wrapper["payload"])).hexdigest() == value["durable_payload_sha256"],
              "physical original Root observation differs from the actual serialized cut bytes")
    return {"directory": directory, "record": disk.public(record), "lock": disk.public(lock)}


def database(disk, path, uid, expected_sha256, expected_inode, old, output, live):
    base = t.BASE + "/fleet/agents/" + t.AGENT + "/cognitive"
    if live:
        e.require(str(PurePosixPath(path).parent) == base, "actual writable database escaped its one original Agent")
        directory = disk.directory(base, 60001, 0o700)
        entries = disk.entries(base)
        if ".cognitive-active-v1" in entries:
            pointer = disk.read(base + "/.cognitive-active-v1", 60001, 0o600, 256)
            target = pointer["raw"].decode("utf-8").strip()
            e.require(re.fullmatch(r"cognitive_recovered_v1_[0-9a-f]{64}\.sqlite3", target)
                      and path == base + "/" + target, "physical active-generation pointer differs from actual writer database")
            pointer = disk.public(pointer)
        else:
            e.require(path == base + "/cognitive_1.sqlite3", "missing original pointer cannot select a recovered generation")
            pointer = None
    else:
        directory = disk.directory(str(PurePosixPath(path).parent), 0, 0o700)
        pointer = None
        entries = disk.entries(str(PurePosixPath(path).parent))
    record = disk.read(path, uid, 0o600, store.MAX_DATABASE_BYTES)
    if expected_sha256 is not None:
        e.require(record["sha256"] == expected_sha256, "actual original retained material bytes do not bind Current")
    if expected_inode is not None:
        e.require(record["inode"]["inode"] == expected_inode, "actual original writer changed its physical database inode")
    name, parent = PurePosixPath(path).name, str(PurePosixPath(path).parent)
    e.require(name + "-journal" not in entries, "actual rollback journal must not be silently ignored")
    wal = None
    if name + "-wal" in entries:
        wal = disk.read(path + "-wal", uid, 0o600, store.MAX_DATABASE_BYTES, allow_empty=True)
        if not live:
            e.require(wal["inode"]["bytes"] == 0, "original consolidated retained material unexpectedly has a live WAL")
    shm = None
    if name + "-shm" in entries:
        shm = disk.read(path + "-shm", uid, 0o600, 8 * 1024**2, allow_empty=True)
    output = Path(output)
    output.mkdir(mode=0o700)
    sql = output / "original.sqlite3"
    shutil.copyfile(record["retained_file"]["path"], sql)
    sql.chmod(0o444)
    if wal is not None:
        target = sql.with_name(sql.name + "-wal")
        shutil.copyfile(wal["retained_file"]["path"], target)
        target.chmod(0o444)
    checked = store.observe_extracted_database(sql, record["sha256"], None if wal is None else wal["sha256"],
                                               t.AGENT, old["occurrence_key"], old["payload_json"])
    checked.update(physical_database=disk.public(record), actual_directory=directory,
                   physical_wal=None if wal is None else disk.public(wal),
                   physical_shm=None if shm is None else disk.public(shm), physical_active_pointer=pointer,
                   original_shm_used_as_sqlite_input=False, forensic_directory=str(output))
    original.save(output / "result.json", checked)
    return checked


def verify(image, expected_sha256, tool, tool_identity, transcript, output, previous=None):
    e.require(transcript.get("prior_boot_transcript_verified") is True and transcript["passed"] is False,
              "actual source-bound prior-boot transcript is required before physical acceptance")
    fresh = transcript["phase"] == "fresh"
    e.require((previous is None) if fresh else type(previous) is dict and previous.get("old_unknown_physically_verified") is True,
              "second stopped disk needs the actual first physical inspection")
    output = Path(output)
    with Disk(image, expected_sha256, tool, tool_identity, output) as disk:
        original_boot = transcript["native_boot_id"] if fresh else transcript["cut"]["kernel_boot"]
        pin = authority.installed_pin(disk, transcript["installation"], original_boot, transcript["original_owner"]["agent_id"])
        observation = saved_observation(disk, transcript)
        old = transcript["cut"]
        current = transcript["cut_current"] if fresh else transcript["final_current"]
        path = transcript["cut_material_path"] if fresh else transcript["final_material_path"]
        material_digest = transcript["cut_material_sha256"] if fresh else transcript["final_material_sha256"]
        e.require(path == material_path(current), "physical retained material path does not bind the exact original Current cut")
        material = database(disk, path, 0, material_digest, None, old, output / "retained-sqlite", False)
        transport = transcript["source_database"]
        e.require(transport["database_inode"] == transcript["actual_state"]["store_inode"],
                  "actual original readiness and writer observations name different writable database inodes")
        live = database(disk, transport["database_path"], 60001, None, transport["database_inode"], old,
                        output / "active-sqlite", True)
        e.require(material["operation"] == live["operation"] and material["admission"] == live["admission"]
                  and material["outbox"] == live["outbox"] and material["claims"] == live["claims"],
                  "retained Current and actual live SQLite/WAL disagree on immutable old operation identity")
        store.preserved_unknown(material, live)
        expected_frontiers = old["frontiers"] if fresh else [transcript["final_old_observation"]["observation"][key]
                                                            for key in e.FRONTIER_LANES]
        consumers = authority.consumers(disk, expected_frontiers, transcript["installation"], transcript["phase"],
                                        None if fresh else previous["consumers"])
        root = authority.root_authority(disk, transcript, None if fresh else previous["root_authority"])
        preservation = None
        if not fresh:
            preservation = store.preserved_unknown(previous["live_database"], live)
            store.preserved_unknown(previous["material_database"], material)
            e.require(pin["file"]["sha256"] == previous["installation"]["file"]["sha256"]
                      and pin["file"]["inode"] == previous["installation"]["file"]["inode"]
                      and observation["record"]["sha256"] == previous["saved_observation"]["record"]["sha256"]
                      and observation["record"]["inode"] == previous["saved_observation"]["record"]["inode"]
                      and observation["lock"]["inode"] == previous["saved_observation"]["lock"]["inode"],
                      "second original installation or saved cut was copied, replaced or recreated")
        result = {"schema": "hepta.native-prior-boot-physical.v1", "passed": False,
                  "old_unknown_physically_verified": True, "phase": transcript["phase"],
                  "image": str(image), "image_sha256": expected_sha256, "installation": pin,
                  "saved_observation": observation, "material_database": material, "live_database": live,
                  "consumers": consumers, "root_authority": root, "old_rows_preserved": preservation,
                  "readonly_extraction": True, "debugfs": tool_identity, "command_count": len(disk.commands),
                  "original_shm_used_as_sqlite_input": False, "native_execution_verified": False,
                  "power_loss_verified": False, "kill_within_guest_callback_window_proven": False}
    original.save(output / "result.json", result)
    return result
