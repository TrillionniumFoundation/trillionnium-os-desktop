#!/usr/bin/env python3
"""Verify native journal storage decisions in the actual linked policy."""
import ctypes
import hashlib
import json

from derive_shared_payload_cgroup_policy import Decision, Policy


def verify_journal_storage(library, binary, exported, original_contract):
    policy = Policy(library, binary)
    lines = set(exported.read_text().splitlines())
    actors = sorted({
        (role, line[len(f"(roletype {role} "):-1])
        for role in ("r", "system_r") for line in lines
        if line.startswith(f"(roletype {role} ")
    })
    if not set(original_contract["subjects"]).issubset(
            {name for role, name in actors if role == "r"}):
        raise ValueError("Original Android roles absent from journal storage review")
    sids, checks = {}, []

    def sid(context):
        if context not in sids:
            value = ctypes.c_uint32()
            raw = context.encode()
            if policy.lib.sepol_context_to_sid(
                    raw, len(raw) + 1, ctypes.byref(value)) != 0:
                raise ValueError("Invalid journal storage context: " + context)
            sids[context] = value.value
        return sids[context]

    def exact(subject, target, kind, permissions, expected):
        number, bits = policy.permissions(kind, permissions)
        mask = 0
        for bit in bits.values():
            mask |= bit
        result = Decision()
        if policy.lib.sepol_compute_av(
                sid(subject), sid(target), number, mask, ctypes.byref(result)) != 0:
            raise ValueError("Cannot read linked journal storage decision")
        actual = {name for name, bit in bits.items() if result.allowed & bit}
        if actual != set(expected):
            raise ValueError(
                f"Journal storage boundary differs: {subject} -> {target} "
                f"{kind}: {sorted(actual)} != {sorted(expected)}")
        checks.extend([subject, target, kind, name, name in actual] for name in permissions)

    # Complete inherited common-file permissions from the original Android CIL.
    common = (
        "ioctl read write create getattr setattr lock relabelfrom relabelto append "
        "map unlink link rename execute quotaon mounton audit_access open execmod "
        "watch watch_mount watch_sb watch_with_perm watch_reads").split()
    file_permissions = common + ["execute_no_trans", "entrypoint"]
    dir_permissions = common + ["add_name", "remove_name", "reparent", "search", "rmdir"]
    writer = "u:system_r:p4_linux_journald_t:s0"
    metadata_editor = "u:system_r:p4_linux_tmpfiles_t:s0"
    if ("system_r", "p4_linux_tmpfiles_t") not in actors:
        raise ValueError("The fixed normal tmpfiles journal metadata role is absent")
    metadata_updates = []
    file_writes = "create write append setattr link unlink rename".split()
    dir_writes = "create write setattr add_name remove_name rename reparent rmdir".split()
    file_expected = "create getattr read write append open lock map setattr rename unlink".split()
    dir_expected = "create getattr open read search write add_name remove_name".split()
    for prefix in ("p4_linux_journal", "p4_linux_volatile_journal"):
        database = f"u:object_r:{prefix}_database_t:s0"
        machine = f"u:object_r:{prefix}_machine_t:s0"
        exact(writer, database, "file", file_permissions, file_expected)
        exact(writer, machine, "dir", dir_permissions,
              dir_expected + (["rmdir"] if "volatile" in prefix else []))
        for role, actor in actors:
            subject = f"u:{role}:{actor}:s0"
            if subject != writer:
                # Normal systemd.conf applies z/a+ to the persistent machine and
                # system.journal, and recursive Z/A+ to the volatile machine.
                # tmpfiles.c dispatches A through glob_item_recursively and
                # fd_set_acls, including the volatile regular journal database.
                # These four metadata updates do not confer content writes or
                # any create/link/unlink/rename/directory-entry operation.
                expected_metadata = ["setattr"] if subject == metadata_editor else []
                exact(subject, database, "file", file_writes, expected_metadata)
                exact(subject, machine, "dir", dir_writes, expected_metadata)
                if expected_metadata:
                    metadata_updates.extend([
                        {"actor": "p4_linux_tmpfiles_t",
                         "target": f"{prefix}_database_t", "class": "file",
                         "permissions": ["setattr"]},
                        {"actor": "p4_linux_tmpfiles_t",
                         "target": f"{prefix}_machine_t", "class": "dir",
                         "permissions": ["setattr"]},
                    ])
        # The existing stock journalctl flush role never reads a database.
        exact("u:system_r:p4_linux_journalctl_t:s0", database, "file",
              ["open", "read", "map", *file_writes], [])
    exact(writer, "u:object_r:p4_linux_journal_store_t:s0", "dir",
          ["remove_name", "rmdir", "rename", "reparent", "relabelfrom", "relabelto"], [])
    exact(writer, "u:object_r:p4_linux_journal_machine_t:s0", "dir",
          ["rmdir", "rename", "reparent", "relabelfrom", "relabelto"], [])
    expected = {
        "(typetransition p4_linux_journald_t p4_linux_journal_machine_t file p4_linux_journal_database_t)",
        '(typetransition p4_linux_journald_t p4_linux_journal_machine_t file "system.journal" p4_linux_journal_database_t)',
        '(typetransition p4_linux_journald_t p4_linux_volatile_journal_machine_t file "system.journal" p4_linux_volatile_journal_database_t)',
    }
    targets = (" p4_linux_journal_database_t)", " p4_linux_volatile_journal_database_t)")
    actual = {line for line in lines if line.startswith("(typetransition ")
              and any(line.endswith(target) for target in targets)}
    if actual != expected:
        raise ValueError("Journal file transitions differ from the single fixed writer contract")
    return {
        "process_role_types": len(actors),
        "permission_checks": len(checks),
        "exact_file_transitions": len(actual),
        "only_journald_writes_database_contents_or_changes_lifecycle": True,
        "tmpfiles_metadata_updates": metadata_updates,
        "persistent_store_directories_not_removable": True,
        "stock_flush_role_still_cannot_read_databases": True,
        "access_matrix_sha256": hashlib.sha256(
            json.dumps(checks, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
