#!/usr/bin/env python3
"""Verify native journal storage decisions in the actual linked policy."""
import ctypes
import hashlib
import json
from pathlib import Path

from derive_shared_payload_cgroup_policy import Decision, Policy


def verify_stream_profile(here):
    """Require the source-owned decimal identities and atomic temporary name."""
    profile = (here / "apparmor/droidloom-ubuntu-journald").read_text()
    lines = {line.strip() for line in profile.splitlines()}
    decimal = "@{droidloom_journal_u64}=" + " ".join("[0-9]" * n for n in range(1, 21))
    wanted = {
        "/run/systemd/journal/streams/ rw,",
        "/run/systemd/journal/streams/@{droidloom_journal_u64}:@{droidloom_journal_u64} rw,",
        '"/run/systemd/journal/streams/.#@{droidloom_journal_u64}:@{droidloom_journal_u64}@{droidloom_journal_hex16}" rw,',
    }
    if decimal not in lines or {line for line in lines if "/run/systemd/journal/streams" in line} != wanted:
        raise ValueError("Journal stream pathname boundary differs")
    if 'audit deny @{PROC}/[0-9]*/{environ,mem,maps,cmdline} r,' not in lines:
        raise ValueError("Journal private process bodies gained an exception")
    return {"directory": "/run/systemd/journal/streams", "decimal_digits": [1, 20],
            "temporary_suffix_hex_digits": 16, "pathname_rules": sorted(wanted),
            "profile_sha256": hashlib.sha256(profile.encode()).hexdigest()}


def verify_stream_file_contexts(here, work):
    """Use the normal libselinux matcher, including wrong names/inode kinds."""
    source = work / "journal-stream-file-contexts"
    source.write_bytes(b"".join((here / name).read_bytes() for name in (
        "ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
        "linux-service-file_contexts", "linux-initial-calibration-file_contexts")))
    class Option(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("value", ctypes.c_char_p)]
    library = ctypes.CDLL("libselinux.so.1", use_errno=True)
    library.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(Option), ctypes.c_uint]
    library.selabel_open.restype = ctypes.c_void_p
    library.selabel_lookup_raw.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p),
                                         ctypes.c_char_p, ctypes.c_int]
    library.selabel_lookup_raw.restype = ctypes.c_int
    library.selabel_close.argtypes = [ctypes.c_void_p]
    library.freecon.argtypes = [ctypes.c_void_p]
    handle = library.selabel_open(0, ctypes.byref(Option(3, str(source).encode())), 1)
    if not handle:
        raise OSError(ctypes.get_errno(), "Cannot open journal stream context matcher")
    import stat
    root = "/run/systemd/journal/streams"
    positives = [(root, stat.S_IFDIR, "p4_linux_journal_stream_dir_t")]
    positives += [(root + "/" + name, stat.S_IFREG, "p4_linux_journal_stream_file_t")
                  for name in ("0:1", "18446744073709551615:18446744073709551615",
                               ".#10:1230123456789abcdef")]
    negatives = [(root + "/" + name, stat.S_IFREG) for name in (
        "", "1", "1:x", "x:1", "1:2/child", "1:123456789012345678901",
        ".#1:20123456789abcde", ".#1:20123456789abcdeG", "1:2.journal")]
    negatives += [(root + "/1:2", kind) for kind in (stat.S_IFDIR, stat.S_IFLNK, stat.S_IFCHR)]
    checked = []
    try:
        for path, kind, expected in positives + [(p, k, None) for p, k in negatives]:
            result = ctypes.c_char_p()
            if library.selabel_lookup_raw(handle, ctypes.byref(result), path.encode(), kind):
                if expected is None and ctypes.get_errno() == 2:
                    checked.append([path, kind, None, None])
                    continue
                raise OSError(ctypes.get_errno(), "Cannot match journal stream path: " + path)
            try:
                actual = result.value.decode().split(":")[2]
            finally:
                library.freecon(result)
            if ((expected is not None and actual != expected) or
                    (expected is None and actual in ("p4_linux_journal_stream_dir_t", "p4_linux_journal_stream_file_t"))):
                raise ValueError("Journal stream context boundary differs: " + path)
            checked.append([path, kind, actual, expected])
    finally:
        library.selabel_close(handle)
    return {"matched_paths_and_inode_kinds": checked}


def verify_journal_storage(library, binary, exported, original_contract):
    stream_profile = verify_stream_profile(Path(__file__).resolve().parent)
    stream_contexts = verify_stream_file_contexts(Path(__file__).resolve().parent, exported.parent)
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
    stream_dir = "u:object_r:p4_linux_journal_stream_dir_t:s0"
    stream_file = "u:object_r:p4_linux_journal_stream_file_t:s0"
    stream_dir_permissions = "create getattr search open read write add_name remove_name".split()
    stream_file_permissions = "create getattr open read write rename unlink".split()
    metadata_readers = {"droidloom_metadata_observer", "droidloom_query_io"}
    for role, actor in actors:
        subject = f"u:{role}:{actor}:s0"
        exact(subject, stream_dir, "dir", dir_permissions,
              stream_dir_permissions if subject == writer else
              ["getattr", "search"] if actor in metadata_readers else [])
        exact(subject, stream_file, "file", file_permissions,
              stream_file_permissions if subject == writer else [])
        exact(subject, stream_dir, "file", file_permissions, [])
        exact(subject, stream_file, "lnk_file", common, [])
    stream_transitions = {
        '(typetransition p4_linux_journald_t p4_linux_journal_runtime_t dir "streams" p4_linux_journal_stream_dir_t)',
        '(typetransition p4_linux_journald_t p4_linux_journal_stream_dir_t file p4_linux_journal_stream_file_t)',
    }
    actual_stream_transitions = {line for line in lines if line.startswith("(typetransition ")
        and line.endswith((" p4_linux_journal_stream_dir_t)", " p4_linux_journal_stream_file_t)"))}
    if actual_stream_transitions != stream_transitions:
        raise ValueError("Journal stream state transitions differ")
    return {
        "process_role_types": len(actors),
        "permission_checks": len(checks),
        "exact_file_transitions": len(actual),
        "only_journald_writes_database_contents_or_changes_lifecycle": True,
        "tmpfiles_metadata_updates": metadata_updates,
        "persistent_store_directories_not_removable": True,
        "stock_flush_role_still_cannot_read_databases": True,
        "stream_state": {**stream_profile, **stream_contexts, "exact_transitions": sorted(stream_transitions),
                         "only_journald_reads_or_writes_state_files": True,
                         "directory_removal_or_relabel_denied": True},
        "access_matrix_sha256": hashlib.sha256(
            json.dumps(checks, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
