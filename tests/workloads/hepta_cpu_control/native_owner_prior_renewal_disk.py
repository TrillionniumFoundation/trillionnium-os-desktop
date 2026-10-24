"""Physical evidence for Unknown retention through original finite releases.

Only stopped copies of the one raw campaign disk are inspected. Every original
released material is bound to its exact Current anchor and journal prefix; the
last writable DB plus its actual WAL must contain the same final logical cut.
"""
from pathlib import Path, PurePosixPath
import re
import shutil

import native_owner_activation_witness_disk as activation
import native_owner_evidence as e
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_disk as original
import native_owner_prior_boot_store as old_store
import native_owner_prior_boot_types as fixed
import native_owner_prior_renewal_files as files
import native_owner_prior_renewal_store as store
import run_native_owner as runner


def database(disk, path, uid, expected_sha, expected_inode, current, schema, cut, output,
             *, kind, previous=None, operations=None, releases=None, partial=False):
    e.require(kind in ("initial", "active", "material"), "fixed original physical database kind required")
    parent = str(PurePosixPath(path).parent)
    working = fixed.BASE + "/fleet/agents/" + fixed.AGENT + "/cognitive"
    e.require((parent == working) if kind != "material" else path == original.material_path(current),
              "original physical database escaped its actual writable owner or exact material cut")
    directory = disk.directory(parent, uid, 0o700)
    entries = disk.entries(parent)
    pointer = None
    if kind == "active":
        pointer = disk.read(working + "/.cognitive-active-v1", 60001, 0o600, 256)
        raw = pointer["raw"]
        e.require(re.fullmatch(rb"cognitive_recovered_v1_[0-9a-f]{64}\.sqlite3\n", raw)
                  and path == working + "/" + raw[:-1].decode(),
                  "final physical database differs from the original durable active-generation pointer")
        pointer = disk.public(pointer)
    elif kind == "initial":
        e.require(path == working + "/cognitive_1.sqlite3" and ".cognitive-active-v1" not in entries,
                  "first actual source is not its original initial database")
    record = disk.read(path, uid, 0o600, old_store.MAX_DATABASE_BYTES)
    if expected_sha is not None:
        e.require(record["sha256"] == expected_sha, "original physical material bytes differ from the actual Root observation")
    if expected_inode is not None:
        e.require(record["inode"]["inode"] == expected_inode, "original writable database inode differs from its actual Host")
    name = PurePosixPath(path).name
    e.require(name + "-journal" not in entries, "actual rollback journal cannot be silently omitted")
    wal = (disk.read(path + "-wal", uid, 0o600, old_store.MAX_DATABASE_BYTES, allow_empty=True)
           if name + "-wal" in entries else None)
    if kind == "material":
        e.require(wal is None or wal["inode"]["bytes"] == 0,
                  "original verified material is not a consolidated independent physical database")
    shm = (disk.read(path + "-shm", uid, 0o600, 8 * 1024**2, allow_empty=True)
           if name + "-shm" in entries else None)
    output = Path(output)
    output.mkdir(mode=0o700)
    extracted = output / "original.sqlite3"
    shutil.copyfile(record["retained_file"]["path"], extracted)
    extracted.chmod(0o444)
    if wal is not None:
        retained_wal = extracted.with_name(extracted.name + "-wal")
        shutil.copyfile(wal["retained_file"]["path"], retained_wal)
        retained_wal.chmod(0o444)
    result = store.observe(extracted, record["sha256"], None if wal is None else wal["sha256"], schema,
                           current["head"]["last_current"], cut, previous=previous, operations=operations,
                           releases=releases, partial=partial)
    result.update(physical_database=disk.public(record), physical_wal=None if wal is None else disk.public(wal),
                  physical_shm=None if shm is None else disk.public(shm), actual_directory=directory,
                  physical_active_pointer=pointer, original_shm_used_as_sqlite_input=False,
                  forensic_directory=str(output), original_database_kind=kind)
    runner.save(output / "result.json", result)
    return result


def released_bindings(events):
    # These are projections of actual original receipts and Current, never
    # serialized producer events or substitute lease/authority records.
    return [{"receipt": event["receipt"], "binding": event["current"]["head"]["writer_binding"]} for event in events]


def verify(image, expected_sha256, tool, tool_identity, transcript, schema, output, previous=None):
    e.require(transcript.get("prior_renewal_transcript_verified") is True and transcript.get("passed") is False,
              "the actual source-bound new two-boot transcript is required before physical acceptance")
    fresh = transcript["phase"] == "fresh"
    e.require((previous is None) if fresh else type(previous) is dict
              and previous.get("old_unknown_physically_verified") is True
              and previous.get("complete_original_material_verified") is True,
              "continued recovery requires the complete actual first stopped physical cut")
    output = Path(output)
    with original.Disk(image, expected_sha256, tool, tool_identity, output) as disk:
        original_boot = transcript["native_boot_id"] if fresh else transcript["cut"]["kernel_boot"]
        pin = authority.installed_pin(disk, transcript["installation"], original_boot, fixed.AGENT)
        observations = files.saved_observations(disk, transcript)
        cut = transcript["cut"]
        if fresh:
            current = transcript["cut_current"]
            e.require(transcript["cut_material_path"] == original.material_path(current),
                      "original first retained material is not its independently observed exact Current cut")
            material = database(disk, transcript["cut_material_path"], 0, transcript["cut_material_sha256"], None,
                                current, schema, cut, output / "cut-material", kind="material")
            transport = transcript["source_database"]
            e.require(transport["database_inode"] == transcript["actual_state"]["store_inode"],
                      "original first readiness and source observation identify different physical databases")
            live = database(disk, transport["database_path"], 60001, None, transport["database_inode"], current,
                            schema, cut, output / "cut-working-source", kind="initial")
            old_store.preserved_unknown(material, live)
            e.require(material["lease_rows"] == live["lease_rows"]
                      and material["exact_material"] == live["exact_material"],
                      "first live DB/WAL and independent retained Current material differ")
            expected_frontiers = cut["frontiers"]
            consumers = files.consumers(disk, expected_frontiers, transcript["installation"], 0)
            root = authority.root_authority(disk, transcript)
            released = []
            preservation = None
        else:
            e.require(transcript.get("bounded_prior_unknown_renewal_transcript_verified") is True,
                      "actual finite releases and the conservative 330-second effect bound are missing")
            operations, events = transcript["original_new_operations"], transcript["original_releases"]
            bindings = released_bindings(events)
            e.require(len(events) == 2 * len(operations) - 1 and 3 <= len(operations) <= 64,
                      "actual Manager/Recovery release sequence is incomplete")
            released, material_inodes, material_paths = [], set(), set()
            for index, event in enumerate(events):
                path = original.material_path(event["current"])
                count = index // 2 + 1
                checked = database(disk, path, 0, event["material_sha256"], None, event["current"], schema, cut,
                    output / ("released-material-" + format(index + 1, "03d")), kind="material",
                    previous=previous["live_database"], operations=operations[:count], releases=bindings[:index + 1],
                    partial=index + 1 < len(events))
                inode = checked["physical_database"]["inode"]["inode"]
                e.require(inode not in material_inodes and path not in material_paths,
                          "an actual released physical cut reused another generation's material")
                material_inodes.add(inode)
                material_paths.add(path)
                released.append(checked)
            material = released[-1]
            e.require(events[-1]["current"] == transcript["final_current"]
                      and events[-1]["material_sha256"] == transcript["final_material_sha256"],
                      "the actual final release was replaced by an earlier terminal Current")
            transport = transcript["source_database"]
            live = database(disk, transport["database_path"], 60001, None, transport["database_inode"],
                            transcript["final_current"], schema, cut, output / "final-working-source", kind="active",
                            previous=previous["live_database"], operations=operations, releases=bindings)
            for name in ("old_unknown", "new_committed_operations", "released_generations", "actual_release_head_digests", "exact_material"):
                e.require(live[name] == material[name], "final live DB/WAL and actual released material disagree on " + name)
            preservation = old_store.preserved_unknown(previous["live_database"], live["old_unknown"])
            expected_frontiers = [transcript["final_old_observation"]["observation"][key] for key in e.FRONTIER_LANES]
            consumers = files.consumers(disk, expected_frontiers, transcript["installation"], len(operations), previous["consumers"])
            root = authority.verify_observed_root(disk, transcript, transcript["final_current"],
                                                  transcript["final_authority"], transcript["final_original_owner"],
                                                  previous["root_authority"])
        witnesses = activation.verify_open(disk, transcript["activation_witnesses_expected"],
                                           transcript["genesis_initial_expected"])
        activation.accept_expected(transcript, witnesses)
        if not fresh:
            files.preserved_records(previous, pin, observations, witnesses)
        result = {"schema": "hepta.native-prior-unknown-renewal-physical.v1", "passed": False,
                  "phase": transcript["phase"], "image": str(image), "image_sha256": expected_sha256,
                  "old_unknown_physically_verified": True, "complete_original_material_verified": True,
                  "all_actual_releases_physically_verified": not fresh,
                  "same_boot_kernel_launch_files_verified": not fresh,
                  "installation": pin, "saved_observation": observations, "material_database": material,
                  "live_database": live, "released_materials": released, "consumers": consumers,
                  "root_authority": root, "old_rows_preserved": preservation,
                  "activation_witnesses": witnesses, "activation_witness_files_verified": True,
                  "readonly_extraction": True, "debugfs": tool_identity, "command_count": len(disk.commands),
                  "original_shm_used_as_sqlite_input": False, "native_execution_verified": False,
                  "kill_within_guest_callback_window_proven": False, "power_loss_verified": False,
                  "unbounded_persistent_cpu_verified": False, "g2_complete": False, "production_ready": False}
    runner.save(output / "result.json", result)
    return result
