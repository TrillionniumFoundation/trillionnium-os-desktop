"""Inspect two stopped copies of the one actual no-head campaign disk.

All debugfs input descriptors are read only. SQLite sees a separate private
extraction including the actual WAL. These copies are never boot inputs.
"""
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tomllib

import native_owner_evidence as e
import native_owner_genesis_authority as root
import native_owner_genesis_store as store
import native_owner_genesis_types as t
import native_owner_prior_boot_disk as original
import native_owner_prior_boot_store as journals
import native_owner_prior_boot_types as fixed
import native_owner_state_observations as ext2
import run_native_owner as runner


def control_read(disk, path, maximum):
    """The original Fleet controller is Root with the explicit Host read group."""
    parent, name = str(PurePosixPath(path).parent), PurePosixPath(path).name
    disk.directory(parent)
    entry = disk.entries(parent).get(name)
    e.require(entry is not None, "actual original Fleet controller file is missing")
    raw, _ = disk.command("stat " + disk.physical(path), 65536)
    meta = ext2.inode_stat(raw)
    e.require(meta["kind"] == "regular" and meta["uid"] == 0 and meta["gid"] == 60001
              and meta["mode"] == 0o640 and meta["links"] == 1 and 0 < meta["bytes"] <= maximum
              and entry["inode"] == meta["inode"] and entry["mode"] == stat.S_IFREG | 0o640
              and entry["uid"] == 0 and entry["gid"] == 60001 and entry["bytes"] == meta["bytes"],
              "original Fleet control is not its unique Root-owned/read-group inode")
    raw, retained = disk.command("cat <" + str(meta["inode"]) + ">", maximum)
    e.require(len(raw) == meta["bytes"], "original Fleet controller read is truncated")
    return {"guest_path": path, "physical_path": disk.physical(path), "inode": meta,
            "raw": raw, "sha256": retained["sha256"], "retained_file": retained}


def fleet(disk, transcript, previous=None):
    agent_path = fixed.BASE + "/fleet/agents/" + fixed.AGENT
    agent = disk.directory(agent_path)
    run_path = agent_path + "/run"
    run = disk.directory(run_path)
    e.require((agent["uid"], agent["gid"], agent["mode"]) == (0, 60001, 0o750)
              and (run["uid"], run["gid"], run["mode"]) == (0, 60001, 0o3770),
              "original native Agent/control-directory ownership differs from the actual handoff")
    manifest = control_read(disk, agent_path + "/agent.toml", 65536)
    config = tomllib.loads(manifest["raw"].decode())
    e.require(config == {"schema_version": 1, "agent_id": fixed.AGENT,
                         "workspace": {"root": fixed.BASE + "/workspace"},
                         "resources": {"max_concurrent_turns": 2, "memory_limit_mib": 4096,
                                       "max_tool_processes": 16, "turn_queue_capacity": 256}},
              "actual immutable original Fleet manifest was replaced or reset")
    states = ["stopped"]
    if transcript["cut_mode"] != "before_writer":
        states += ["starting"]
        if previous is not None:
            states += ["failed"]
    if previous is not None:
        states += ["starting", "running", "draining", "stopped"]
    names = ["lifecycle-" + format(index, "020d") + ".json" for index in range(len(states))]
    actual = disk.entries(run_path)
    e.require({name for name in actual if name.startswith("lifecycle-")} == set(names)
              and not any(name.startswith(".lifecycle-") for name in actual),
              "actual original Fleet lifecycle is missing, has a forged future generation or an unfinished publication")
    files = []
    for index, (name, state) in enumerate(zip(names, states)):
        record = control_read(disk, run_path + "/" + name, 16384)
        value = e.json_value(record["raw"])
        t.lifecycle(value, index, state)
        ordered = e.ordered(value, ("schema_version", "agent_id", "generation", "lifecycle"), "original lifecycle serialization")
        e.require(record["raw"] == (e.canonical(ordered) + "\n").encode(),
                  "actual original Fleet lifecycle bytes differ from original publication format")
        files.append(disk.public(record))
    if previous is not None:
        old = previous["fleet"]
        e.require(all(files[index]["sha256"] == record["sha256"] and files[index]["inode"] == record["inode"]
                      for index, record in enumerate(old["lifecycle_files"]))
                  and manifest["sha256"] == old["manifest"]["sha256"] and manifest["inode"] == old["manifest"]["inode"],
                  "cold recovery recreated the original controller manifest or any retained lifecycle generation")
    return {"agent_directory": agent, "run_directory": run, "manifest": disk.public(manifest),
            "lifecycle_files": files, "final_lifecycle": states[-1], "final_generation": len(states) - 1}


def database(disk, path, uid, expected_sha, expected_inode, anchor, schema, output, *, kind, unused=False,
             operation=None, release=None):
    e.require(kind in ("initial", "active", "material"), "fixed original database selection required")
    parent = str(PurePosixPath(path).parent)
    base = fixed.BASE + "/fleet/agents/" + fixed.AGENT + "/cognitive"
    e.require(parent == base if kind != "material" else path.startswith(fixed.AUTHORITY + "/material/"),
              "actual database escaped its original owner/material namespace")
    directory = disk.directory(parent, uid, 0o700)
    entries = disk.entries(parent)
    pointer = None
    if kind == "active":
        pointer = disk.read(base + "/.cognitive-active-v1", 60001, 0o600, 256)
        raw = pointer["raw"]
        e.require(re.fullmatch(rb"cognitive_recovered_v1_[0-9a-f]{64}\.sqlite3\n", raw)
                  and path == base + "/" + raw[:-1].decode(),
                  "actual recovered original working database differs from its durable original active pointer")
        pointer = disk.public(pointer)
    elif kind == "initial":
        e.require(path == t.INITIAL_DATABASE, "original initial database identity changed")
    record = disk.read(path, uid, 0o600, journals.MAX_DATABASE_BYTES)
    if expected_sha is not None:
        e.require(record["sha256"] == expected_sha, "original physical material differs from its actual independently retained bytes")
    if expected_inode is not None:
        e.require(record["inode"]["inode"] == expected_inode, "original physical SQLite inode differs from the actual observation")
    name = PurePosixPath(path).name
    e.require(name + "-journal" not in entries, "actual rollback journal cannot be silently ignored")
    wal = disk.read(path + "-wal", uid, 0o600, journals.MAX_DATABASE_BYTES, allow_empty=True) if name + "-wal" in entries else None
    if kind == "material":
        e.require(wal is None or wal["inode"]["bytes"] == 0, "original verified retained material contains unconsolidated WAL bytes")
    shm = disk.read(path + "-shm", uid, 0o600, 8 * 1024**2, allow_empty=True) if name + "-shm" in entries else None
    output = Path(output)
    output.mkdir(mode=0o700)
    extracted = output / "original.sqlite3"
    shutil.copyfile(record["retained_file"]["path"], extracted)
    extracted.chmod(0o444)
    if wal is not None:
        target = extracted.with_name(extracted.name + "-wal")
        shutil.copyfile(wal["retained_file"]["path"], target)
        target.chmod(0o444)
    checked = store.observe(extracted, record["sha256"], None if wal is None else wal["sha256"], schema, anchor,
                            unused=unused, operation=operation, release=release)
    checked.update(physical_database=disk.public(record), physical_wal=None if wal is None else disk.public(wal),
                   physical_shm=None if shm is None else disk.public(shm), actual_directory=directory,
                   physical_active_pointer=pointer, original_shm_used_as_sqlite_input=False,
                   forensic_directory=str(output), original_database_kind=kind)
    runner.save(output / "result.json", checked)
    return checked


def preserved_initial(old, new):
    for name in ("physical_database", "physical_wal"):
        first, second = old[name], new[name]
        e.require((first is None) == (second is None), "cold-open changed the complete initial physical database/WAL selection")
        if first is not None:
            e.require(first["sha256"] == second["sha256"] and first["inode"] == second["inode"],
                      "cold-open rewrote the original initial material or writable source preimage")
    e.require(old["anchor"] == new["anchor"] and old["original_journals"] == new["original_journals"],
              "cold-open reset the complete original initial logical material")


def verify(image, expected_sha256, tool, tool_identity, transcript, schema, output, previous=None):
    fresh = transcript.get("phase") == "fresh"
    e.require(transcript.get("genesis_transcript_verified") is True and transcript.get("passed") is False
              and ((previous is None) if fresh else type(previous) is dict
                   and previous.get("original_no_head_initial_material_physically_verified") is True),
              "actual no-head transcripts and prior stopped original evidence are required")
    output = Path(output)
    state = transcript["observed_installation"]
    with original.Disk(image, expected_sha256, tool, tool_identity, output) as disk:
        installed = root.installation(disk, transcript)
        checkpoint = root.checkpoint(disk, transcript)
        if not fresh and previous["checkpoint"]["first_signature"] is not None:
            old = previous["checkpoint"]["first_signature"]["record"]
            new = checkpoint["first_signature"]["record"]
            e.require(new["sha256"] == old["sha256"] and new["inode"] == old["inode"],
                      "same-disk recovery overwrote or recreated the original immutable sequence-one proof")
        initial = state["initial_material"]
        retained = database(disk, initial["path"], 0, initial["sha256"], initial["inode"], initial["cut"], schema,
                            output / "initial-material", kind="material", unused=True)
        source = state["source_database"]
        original_source = database(disk, source["path"], 60001, None, source["inode"], initial["cut"], schema,
                                   output / "initial-source", kind="initial", unused=True)
        e.require(retained["anchor"] == original_source["anchor"], "original unused source and independent material differ")
        if fresh:
            e.require(".cognitive-active-v1" not in disk.entries(str(PurePosixPath(source["path"]).parent)),
                      "before-first-writer installation already selected a recovered working generation")
            active = final_material = None
        else:
            preserved_initial(previous["initial_material_database"], retained)
            preserved_initial(previous["initial_source_database"], original_source)
            operation, release = transcript["first_operation"], transcript["release_event"]["receipt"]
            anchor = transcript["final_current"]["head"]["last_current"]
            final_material = database(disk, transcript["final_material_path"], 0, transcript["final_material_sha256"], None,
                                      anchor, schema, output / "released-material", kind="material", operation=operation, release=release)
            actual = transcript["source_database"]
            active = database(disk, actual["database_path"], 60001, None, actual["database_inode"], anchor, schema,
                              output / "released-working-source", kind="active", operation=operation, release=release)
            e.require(active["anchor"] == final_material["anchor"]
                      and active["original_journals"] == final_material["original_journals"],
                      "released Current material and actual writable SQLite/WAL differ on original effect/release state")
        authority = root.authority(disk, transcript, previous, None if fresh else active["original_journals"]["operation"])
        consumers = root.consumers(disk, transcript, previous)
        control = fleet(disk, transcript, previous)
        if not fresh:
            e.require(installed["pin"]["file"]["sha256"] == previous["installation"]["pin"]["file"]["sha256"]
                      and installed["pin"]["file"]["inode"] == previous["installation"]["pin"]["file"]["inode"],
                      "same-disk original public pin was rewritten or recreated")
        result = {"schema": "hepta.original-no-head-physical.v1", "passed": True, "phase": transcript["phase"],
                  "readonly_extraction": True, "state_path": str(image), "state_sha256": expected_sha256,
                  "installation": installed, "checkpoint": checkpoint, "root_authority": authority,
                  "consumers": consumers, "fleet": control, "initial_material_database": retained,
                  "initial_source_database": original_source, "live_database": active, "released_material_database": final_material,
                  "original_no_head_initial_material_physically_verified": fresh,
                  "original_first_writer_released_physically_verified": not fresh,
                  "original_schema_source_sha256": schema["original_source_sha256"],
                  "original_checkpoint_absent": fresh, "original_writer_tables_empty": fresh,
                  "original_initial_material_preserved": not fresh, "private_key_bytes_read_or_exported": False,
                  "native_execution_verified": False, "g2_complete": False, "production_ready": False,
                  "command_count": len(disk.commands), "inspection_tool": tool_identity}
    runner.save(output / "result.json", result)
    return result
