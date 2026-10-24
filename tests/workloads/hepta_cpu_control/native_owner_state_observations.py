"""Read original Root launch observations from the actual retained ext2 image.

debugfs is opened without -w. The complete disk, selected tool, raw command
outputs and extracted records are hashed before/after. This checks retained
post-run bytes, ownership and path identity; it does not simulate a boot,
mint a Root receipt, or qualify power-loss/cross-boot recovery.
"""
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import time

from native_owner_evidence import byte_id, integer, require
from native_owner_root_observation import (MAX_OBSERVATION_BYTES, ROOT_OBSERVATION_DIRECTORY,
                                           inspect_saved_launch, launch_observation_filename)


ENV = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}
HEADER = re.compile(r"^Inode: ([0-9]+)\s+Type: (regular|directory)\s+Mode:\s+([0-7]{4})\s+Flags: (0x[0-9a-fA-F]+)$", re.M)
OWNER = re.compile(r"^User:\s+([0-9]+)\s+Group:\s+([0-9]+)(?:\s+Project:\s+[0-9]+)?\s+Size:\s+([0-9]+)$", re.M)
LINKS = re.compile(r"^Links:\s+([0-9]+)\s+Blockcount:\s+([0-9]+)$", re.M)
BANNER = re.compile(rb"debugfs [^\r\n]{1,160}\n")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
    path.chmod(0o444)


def inode_stat(raw):
    require(type(raw) is bytes and 0 < len(raw) <= 65_536, "bounded complete debugfs inode observation required")
    decoded = raw.decode("ascii")
    headers, owners, links = HEADER.findall(decoded), OWNER.findall(decoded), LINKS.findall(decoded)
    require(len(headers) == len(owners) == len(links) == 1, "debugfs did not return one actual inode identity")
    number, kind, mode, flags = headers[0]
    uid, gid, size = owners[0]
    count, blocks = links[0]
    return {"inode": integer(int(number), "retained inode", 1), "kind": kind, "mode": int(mode, 8),
            "flags": int(flags, 16), "uid": int(uid), "gid": int(gid), "bytes": int(size),
            "links": int(count), "blocks": int(blocks)}


def directory_entries(raw):
    require(type(raw) is bytes and len(raw) <= 65_536, "bounded complete debugfs directory listing required")
    entries = {}
    for line in raw.decode("ascii").splitlines():
        if not line:
            continue
        parts = line.split("/")
        require(len(parts) == 8 and parts[0] == parts[-1] == ""
                and all(re.fullmatch(r"[0-9]+", parts[index]) for index in (1, 3, 4))
                and re.fullmatch(r"[0-7]{6}", parts[2])
                and re.fullmatch(r"[A-Za-z0-9_.-]+", parts[5]) and parts[5] not in entries
                and (parts[6] == "" or re.fullmatch(r"[0-9]+", parts[6])),
                "retained Root directory contains ambiguous or unexpected names")
        entries[parts[5]] = {"inode": int(parts[1]), "mode": int(parts[2], 8),
                            "uid": int(parts[3]), "gid": int(parts[4]),
                            "bytes": None if not parts[6] else int(parts[6])}
    require("." in entries and ".." in entries, "actual Root directory entries are incomplete")
    return entries


def verify(image, tool, tool_identity, expected_state_sha256, observations, output):
    """Require independent actual filesystem bytes for every saved generation."""
    image, tool, output = Path(image), Path(tool), Path(output)
    require(image.is_absolute() and tool.is_absolute() and output.is_absolute()
            and not image.is_symlink() and stat.S_ISREG(image.stat().st_mode)
            and not output.exists() and not output.is_symlink(), "new retained observation directory and actual state image required")
    require(type(observations) is list and 1 <= len(observations) <= 64,
            "actual bounded original launch observations are required")
    require(tool_identity["path"] == str(tool) and sha(tool) == tool_identity["sha256"]
            and sha(image) == expected_state_sha256, "actual state or read-only tool changed before extraction")
    output.mkdir(mode=0o700)
    commands = []

    def command(query, maximum=65_536):
        # query contains only a fixed path/verb or an already-validated integer
        # inode/hex filename. There is no shell and never debugfs write mode.
        number = len(commands)
        argv = [str(tool), "-R", query, str(image)]
        out, err = output / f"{number:03d}.stdout", output / f"{number:03d}.stderr"
        receipt = {"argv": argv, "exit_code": None, "timed_out": False, "tool": tool_identity}
        started = time.monotonic()
        with out.open("xb") as stdout, err.open("xb") as stderr:
            try:
                result = subprocess.run(argv, env=ENV, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                        timeout=15, check=False)
                receipt["exit_code"] = result.returncode
            except subprocess.TimeoutExpired:
                receipt["timed_out"] = True
        receipt["elapsed_seconds"] = time.monotonic() - started
        for name, path in (("stdout", out), ("stderr", err)):
            path.chmod(0o444)
            receipt[name] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}
        commands.append(receipt)
        save(output / f"{number:03d}.json", receipt)
        require(receipt["exit_code"] == 0 and not receipt["timed_out"]
                and out.stat().st_size <= maximum and err.stat().st_size <= 256,
                "actual read-only debugfs command failed or exceeded its observation bound")
        # debugfs can return exit zero on a missing path; accept only its normal
        # version banner and a complete independently parsed inode/list result.
        require(BANNER.fullmatch(err.read_bytes()) is not None,
                "debugfs reported a filesystem/path error despite its exit status")
        return out.read_bytes()

    verified = []
    try:
        relative = ROOT_OBSERVATION_DIRECTORY.removeprefix("/state")
        parts = Path(relative).parts[1:]
        ancestors = []
        for count in range(0, len(parts) + 1):
            path = "/" + "/".join(parts[:count])
            metadata = inode_stat(command("stat " + path))
            require(metadata["kind"] == "directory" and metadata["uid"] == 0 and metadata["mode"] & 0o022 == 0,
                    "Root observation ancestor changed its actual Root ownership or write boundary")
            ancestors.append({"path": path, **metadata})
        parent = ancestors[-1]
        require(parent["uid"] == 0 and parent["mode"] == 0o700,
                "actual Root observation directory is not Root-owned mode 0700")
        entries = directory_entries(command("ls -p <" + str(parent["inode"]) + ">"))
        expected = {}
        for value in observations:
            boot = byte_id(value["boot_id"], "actual saved native boot")
            generation = integer(value["launch_generation"], "actual saved launch generation", 1)
            name = launch_observation_filename(value["observation_id"])
            require(name not in expected, "one actual Root observation was counted twice")
            expected[name] = (boot, generation, value)
        lock_names = {name + ".lock" for name in expected}
        require(set(entries) == {".", "..", *expected, *lock_names}
                and entries["."]["inode"] == parent["inode"]
                and entries[".."]["inode"] == ancestors[-2]["inode"],
                "actual retained Root directory contains missing/extra observations or a different parent")
        seen_inodes = set()
        locks = []
        for name in sorted(lock_names):
            metadata = inode_stat(command("stat " + relative + "/" + name))
            entry = entries[name]
            require(metadata["kind"] == "regular" and metadata["uid"] == 0 and metadata["mode"] == 0o600
                    and metadata["links"] == 1 and metadata["bytes"] == 0
                    and metadata["inode"] not in seen_inodes and entry["inode"] == metadata["inode"]
                    and entry["mode"] == (stat.S_IFREG | 0o600) and entry["uid"] == 0
                    and entry["gid"] == metadata["gid"] and entry["bytes"] == 0,
                    "original Root lock inode differs from the retained protected storage primitive")
            seen_inodes.add(metadata["inode"])
            locks.append({"filename": name, **metadata})
        for name, (boot, generation, value) in expected.items():
            metadata = inode_stat(command("stat " + relative + "/" + name))
            entry = entries[name]
            require(metadata["kind"] == "regular" and metadata["uid"] == 0 and metadata["mode"] == 0o600
                    and metadata["links"] == 1 and 0 < metadata["bytes"] <= MAX_OBSERVATION_BYTES
                    and metadata["inode"] not in seen_inodes and entry["inode"] == metadata["inode"]
                    and entry["mode"] == (stat.S_IFREG | 0o600) and entry["uid"] == metadata["uid"]
                    and entry["gid"] == metadata["gid"] and entry["bytes"] == metadata["bytes"],
                    "saved original Root record is not the exact unique regular Root 0600 inode")
            seen_inodes.add(metadata["inode"])
            raw = command("cat <" + str(metadata["inode"]) + ">", MAX_OBSERVATION_BYTES)
            require(len(raw) == metadata["bytes"], "actual Root record length differs from its retained inode")
            checked = inspect_saved_launch(raw, boot, generation, value["durable_payload_json"])
            require(checked["filename"] == name and checked["payload_sha256"] == value["durable_payload_sha256"],
                    "physical Root record differs from the actual saved payload identity")
            target = output / name
            with target.open("xb") as stream:
                stream.write(raw)
            target.chmod(0o444)
            verified.append({**checked, "path": str(target), "guest_path": ROOT_OBSERVATION_DIRECTORY + "/" + name,
                             "actual_inode": metadata})
        result = {"schema": "hepta.native-root-retained-observations.v1", "passed": True,
                  "state_path": str(image), "state_sha256": expected_state_sha256,
                  "tool": tool_identity, "directory": parent, "ancestors": ancestors, "original_lock_inodes": locks,
                  "actual_files": verified, "command_count": len(commands),
                  "readonly_extraction": True, "cross_boot_verified": False, "power_loss_verified": False}
    finally:
        require(sha(image) == expected_state_sha256 and sha(tool) == tool_identity["sha256"],
                "actual state or extraction tool changed during read-only evidence collection")
    save(output / "result.json", result)
    return result


def accept_retained_observations(transcript, files):
    """Add the filesystem gate to an already checked actual native transcript."""
    require(transcript.get("continuity_transcript_verified") is True and transcript.get("passed") is False
            and files.get("passed") is True and files.get("readonly_extraction") is True,
            "both actual transcript and independent retained-file checks are required")
    expected = transcript["root_launch_observations_expected"]
    require(len(files["actual_files"]) == len(expected)
            and {(item["observation_id"], item["payload_sha256"]) for item in files["actual_files"]}
                == {(item["observation_id"], item["durable_payload_sha256"]) for item in expected},
            "retained-file acceptance refers to another actual native run")
    transcript.update(passed=True, root_launch_files_verified=True, original_native_owner_cycle_verified=True,
                      same_boot_authenticated_successor_verified=True,
                      grant_renewal_verified=transcript.get("bounded_renewal_transcript_verified") is True,
                      history_only_recovery_verified=transcript.get("history_only_transcript_verified") is True,
                      unbounded_persistent_cpu_verified=False, cross_boot_unknown_preservation_verified=False,
                      power_loss_verified=False, g2_complete=False, production_ready=False)
    return transcript
