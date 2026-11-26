"""Source-owned remount admission in the normal strict shared-kernel linker.

The two unmodified package inodes receive narrower executable types; the fixed
fstab and root-device custody outputs receive separate metadata-only types.
The common alias derivation preserves every old actor's complete AV, MCS,
transition, constraint and ioctl view; this module proves the new role itself.
"""
import ctypes
import hashlib
import json
import re
import stat

from derive_native_uevent_policy import ContextPolicy
from derive_native_console_policy import contract as console_contract
from derive_native_sysusers_policy import ALIASES as SYSUSERS_ALIASES
from derive_preserved_alias_policy import (
    _roles, _context, derive_preserved_aliases, verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression

ROLE = "p4_linux_remount_t"
ENTRY = "p4_linux_remount_exec_t"
MOUNT = "p4_linux_remount_mount_exec_t"
FSTAB = "p4_linux_remount_fstab_native_config_t"
ROOT_LINK = "p4_linux_root_uuid_link_t"
ROOT_BLOCK = "p4_linux_root_block_t"
EARLY = "p4_linux_early_t"
EXECUTOR = "p4_linux_service_executor_t"
ALIASES = [
    {"source": "p4_linux_runtime_lib_t", "target": ENTRY, "class": "file"},
    {"source": "p4_linux_native_bin_t", "target": MOUNT, "class": "file"},
    {"source": "p4_linux_native_config_t", "target": FSTAB, "class": "file"},
    {"source": "device", "target": ROOT_LINK, "class": "lnk_file"},
    {"source": "device", "target": ROOT_BLOCK, "class": "blk_file"},
]
FILES = {
    "/usr/lib/systemd/systemd-remount-fs": (0o755, "p4_linux_runtime_lib_t", ENTRY),
    "/usr/bin/mount": (0o4755, "p4_linux_native_bin_t", MOUNT),
    "/usr/lib/systemd/system/systemd-remount-fs.service":
        (0o644, "p4_linux_unit_file_t", "p4_linux_unit_file_t"),
}
TRANSITION_OPS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")


def contract(here):
    value = json.loads((here / "native-remount-source.json").read_text())
    if (set(value) != {"schema", "packages", "aliases", "files", "command_links",
                       "source_documents", "runtime_qualified"} or
            value["schema"] != "droidloom.native-remount-source-closure.v1" or
            value["runtime_qualified"] is not False or
            value["packages"] != {
                "systemd:amd64": "259.9-0ubuntu0.1+p4gentmp2",
                "mount:amd64": "2.41.3-3ubuntu2.2"} or
            value["aliases"] != ALIASES or len(value["files"]) != len(FILES) or
            not value["source_documents"]):
        raise ValueError("Remount source contract differs from the normal package selection")
    seen = set()
    keys = {"path", "bytes", "sha256", "mode", "uid", "gid", "nlink",
            "source_type", "target_type"}
    for row in value["files"]:
        path = row.get("path")
        if (set(row) != keys or path not in FILES or path in seen or
                (row["mode"], row["source_type"], row["target_type"]) != FILES[path] or
                row["uid"] != 0 or row["gid"] != 0 or row["nlink"] != 1 or
                not 0 < row["bytes"] <= 16 * 1024 * 1024 or
                not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise ValueError("Unexpected normal remount inode or executable metadata")
        seen.add(path)
    if value["command_links"] != [
            {"path": "/etc/mtab", "target": "../proc/self/mounts", "uid": 0, "gid": 0}]:
        raise ValueError("Remount mount-table alias is not the distribution link")
    repository = here.parents[3]
    paths = {
        "runtime/droidloom-early-boot/linux_run_label.c",
        "runtime/droidloom-early-boot/linux_run_label.h",
        "runtime/droidloom-early-boot/board_init.c",
    }
    rows = [row for row in value["source_documents"]
            if row.get("admission") == "repository-source-bytes"]
    if len(rows) != len(paths) or {row.get("path") for row in rows} != paths:
        raise ValueError("Root-device custody source roster differs")
    for row in rows:
        if (set(row) != {"package", "version", "path", "bytes", "sha256", "admission"}
                or row["package"] != "droidloom-early-boot"
                or row["version"] != "source"):
            raise ValueError("Unexpected root-device custody source metadata")
        data = (repository / row["path"]).read_bytes()
        if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
            raise ValueError("Root-device custody source bytes differ: " + row["path"])
    return value


def derive(library, baseline, exported, here, output, export):
    value = contract(here)
    entry_read = {"getattr", "open", "read", "execute", "map"}
    expected = derive_preserved_aliases(library, baseline, exported,
        value["aliases"], output, export, prefix="p4_remount_preserved",
        isolated_roles={ROLE}, extra_permissions={
            ("init_t", ENTRY, "file"): entry_read,
            (EXECUTOR, ENTRY, "file"): entry_read,
            (EARLY, FSTAB, "file"): {"getattr", "open", "read"},
            (EARLY, ROOT_LINK, "lnk_file"): {"relabelto"},
            (EARLY, ROOT_BLOCK, "blk_file"): {"relabelto"},
        }, preamble=("; Preserve the real pre-remount-alias access of all existing actors.",),
        mcs_aliases={(ROOT_LINK, "lnk_file"), (ROOT_BLOCK, "blk_file")})
    expected["contract_sha256"] = hashlib.sha256(
        (here / "native-remount-source.json").read_bytes()).hexdigest()
    return expected


def verify(library, binary, exported, here, expected, export):
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    text = exported.read_text()
    value = contract(here)
    aliases = console_contract(here)["aliases"] + SYSUSERS_ALIASES
    checks = verify_preserved_aliases(policy, exported, value["aliases"], expected)
    objects = sorted(set(re.findall(r"\(roletype object_r (\w+)\)", text)))
    actors = _roles(lines)
    classes = expected["classes"]

    def av(target, cls, wanted, target_role="object_r", actor=ROLE, actor_role="system_r",
           permissions=None):
        names = classes[cls] if permissions is None else permissions
        got = policy.context_av(_context(actor_role, actor),
                                _context(target_role, target), cls, names)
        _, bits = policy.permissions(cls, names)
        want = sum(bits[p] for p in wanted)
        if got != want:
            actual = sorted(name for name, bit in bits.items() if got & bit)
            raise ValueError("Remount boundary mismatch: " + actor + " -> " +
                target_role + ":" + target + " " + cls + " " +
                str(actual) + " != " + str(sorted(wanted)))
        checks.append([actor_role, actor, target_role, target, cls, sorted(wanted)])

    # The FINISH writer may only inspect and relabel the two held root-device
    # inodes. Compare full class vectors, including absence of every body,
    # mutation and ioctl permission, from the final linked policy.
    root_custody = [
        ("device", "lnk_file", {"getattr", "read", "relabelfrom"}),
        ("device", "blk_file", {"getattr", "relabelfrom"}),
        (ROOT_LINK, "lnk_file", {"getattr", "read", "relabelfrom", "relabelto"}),
        (ROOT_BLOCK, "blk_file", {"getattr", "relabelfrom", "relabelto"}),
        (FSTAB, "file", {"getattr", "open", "read"}),
    ]
    for target, cls, wanted in root_custody:
        av(target, cls, wanted, actor=EARLY)

    # The complete old/source transition forms are already compared above.
    # Any new transition involving either narrower entry or the new role must
    # be one of those preserved forms or the one fixed service transition.
    observed = set()
    for line in lines:
        if line.startswith(TRANSITION_OPS):
            form = parse_expression(line)
            if any(isinstance(token, str) and token in (ROLE, ENTRY, MOUNT, FSTAB, ROOT_LINK, ROOT_BLOCK)
                   for token in form[1:]):
                observed.add(line)
    fixed = "(typetransition " + EXECUTOR + " " + ENTRY + " process " + ROLE + ")"
    wanted = {line for line in expected["transitions"] if line.startswith(TRANSITION_OPS)}
    wanted.add(fixed)
    if observed != wanted:
        raise ValueError("Remount gained or lost an executable/role transition")
    for role, actor in actors:
        av(ROLE, "process", ["transition"] if actor == EXECUTOR else [],
           target_role="system_r", actor=actor, actor_role=role,
           permissions=["transition", "dyntransition"])
        av(ROLE, "process2", ["nnp_transition"] if actor == EXECUTOR else [],
           target_role="system_r", actor=actor, actor_role=role,
           permissions=["nnp_transition"])

    read = {"getattr", "open", "read"}
    executable = read | {"execute", "map"}
    file_access = {
        "p4_linux_runtime_lib_t": executable,
        "p4_linux_elf_interpreter_t": executable,
        "p4_linux_native_config_t": read,
        FSTAB: read,
        "proc_cmdline": read,
        # object_r also admits process types; AV rules select the concrete type.
        # The same fixed own-proc view is checked under every admitted role.
        ROLE: read,
        ENTRY: executable | {"entrypoint"},
        MOUNT: executable | {"execute_no_trans"},
        "p4_linux_console_ld_cache_native_config_t": read | {"map"},
    }
    # These original aliases retain this role's exact pre-alias view. They do
    # not permit executing a helper in this role or entering it through a script.
    for row in aliases:
        if row["class"] == "file" and row["source"] in file_access:
            file_access.setdefault(row["target"], set()).update(file_access[row["source"]])
    for target in objects:
        av(target, "file", file_access.get(target, set()))
        av(target, "chr_file", {
            "p4_linux_standardio_t": {"getattr", "read", "write"},
            "null_device": {"getattr", "open", "read", "write"},
        }.get(target, set()))
        av(target, "blk_file", {"getattr"} if target == ROOT_BLOCK else set())
        av(target, "filesystem", {
            "labeledfs": {"getattr", "remount"}, "proc": {"getattr"},
            "selinuxfs": {"getattr"},
        }.get(target, set()))

    directories = {
        "p4_linux_rootdir_t", "p4_linux_etc_dir_t", "p4_linux_run_t",
        "p4_linux_mount_monitor_dir_t",
        "device", "p4_linux_native_dev_root_t", "proc", ROLE,
    }
    links = {"p4_linux_usrmerge_link_t", "p4_linux_timezone_link_t",
             "p4_linux_native_config_t", "proc", ROLE, ROOT_LINK}
    for row in aliases:
        if row["class"] == "dir" and row["source"] in directories:
            directories.add(row["target"])
    for target in objects:
        av(target, "dir", ({"search"} if target in
            {"sysfs", "selinuxfs", "p4_linux_systemd_run_t"} else
            {"getattr", "search"} if target in directories else set()))
        av(target, "lnk_file", {"getattr", "read"} if target in links else set())
    for role, target in actors:
        own = role == "system_r" and target == ROLE
        av(target, "file", read if own else set(), target_role=role)
        av(target, "dir", {"getattr", "search"} if own else set(), target_role=role)
        av(target, "lnk_file", {"getattr", "read"} if own else set(), target_role=role)
        av(target, "process", {
            ROLE: {"fork", "getattr", "getcap", "setcap", "sigchld", "signal"},
            "init_t": {"sigchld"}, EXECUTOR: {"sigchld"},
        }.get(target, set()) if role == "system_r" else set(), target_role=role)
        av(target, "fd", {"use"} if role == "system_r" and target in (ROLE, EXECUTOR)
           else set(), target_role=role)
    for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
        av(ROLE, cls, {"sys_admin"} if cls == "capability" else set(),
           target_role="system_r")
    av("kernel", "security", set(), target_role="r")

    # Every concrete actor and object is checked against every socket class.
    # Only the already inherited executor stream has read/write/getattr.
    targets = [("object_r", target) for target in objects] + actors
    socket_classes = sorted(cls for cls in classes
                            if cls == "socket" or cls.endswith("_socket"))
    for cls in socket_classes:
        for role, target in targets:
            wanted = ({"getattr", "read", "write"} if
                      cls == "unix_stream_socket" and
                      target == EXECUTOR else set())
            av(target, cls, wanted, target_role=role)
    return {
        "schema": "droidloom.native-remount-policy-proof.v1",
        "source_contract_sha256": expected["contract_sha256"],
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "alias_preserver_sha256": hashlib.sha256(
            (here / "derive_preserved_alias_policy.py").read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256(
            (here / "derive_native_remount_policy.py").read_bytes()).hexdigest(),
        "fixed_service_transition": fixed,
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_transitions": len(expected["transitions"]),
        "raw_te_vectors_preserved": len(expected["raw_te_samples"]),
        "mcs_source_target_samples_preserved": len(expected["mcs_effective_samples"]),
        "all_ranges_constraint_target_checks": expected["constraint_target_checks"],
        "whole_object_classes_checked": ["file", "dir", "lnk_file", "chr_file",
                                         "blk_file", "filesystem"],
        "concrete_objects": len(objects), "concrete_actors": len(actors),
        "socket_classes": len(socket_classes), "vector_checks": len(checks),
        "file_contexts": verify_file_contexts(here, exported.parent),
        "matrix_sha256": hashlib.sha256(
            json.dumps(checks, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "root_device_custody_vectors": [[target, cls, sorted(wanted)]
            for target, cls, wanted in root_custody],
        "runtime_qualified": False,
    }


def verify_file_contexts(here, work):
    value = contract(here)
    path = work / "remount-file-contexts"
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    path.write_bytes(b"".join((here / name).read_bytes() for name in names))

    class Option(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("value", ctypes.c_char_p)]
    lib = ctypes.CDLL("libselinux.so.1", use_errno=True)
    lib.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(Option), ctypes.c_uint]
    lib.selabel_open.restype = ctypes.c_void_p
    lib.selabel_lookup_raw.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p),
                                      ctypes.c_char_p, ctypes.c_int]
    lib.selabel_lookup_raw.restype = ctypes.c_int
    lib.selabel_close.argtypes = [ctypes.c_void_p]
    lib.freecon.argtypes = [ctypes.c_void_p]
    handle = lib.selabel_open(0, ctypes.byref(Option(3, str(path).encode())), 1)
    if not handle:
        raise OSError(ctypes.get_errno(), "Cannot open remount file-context matcher")
    checked = []
    def lookup(filename, mode):
        result = ctypes.c_char_p()
        if lib.selabel_lookup_raw(handle, ctypes.byref(result), filename.encode(), mode):
            raise OSError(ctypes.get_errno(), "Remount context lookup failed: " + filename)
        try:
            return result.value.decode().split(":")[2]
        finally:
            lib.freecon(result)
    try:
        for row in value["files"]:
            if lookup(row["path"], stat.S_IFREG) != row["target_type"]:
                raise ValueError("Normal remount inode has the wrong execution label")
            checked.append([row["path"], stat.S_IFREG, row["target_type"]])
            for mode in (stat.S_IFDIR, stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK):
                try:
                    actual = lookup(row["path"], mode)
                except OSError as error:
                    if error.errno != 2:
                        raise
                    actual = None
                if actual in (ENTRY, MOUNT):
                    raise ValueError("Remount execution label accepted another inode class")
                checked.append([row["path"], mode, actual])
        if lookup("/etc/fstab", stat.S_IFREG) != FSTAB:
            raise ValueError("The fixed root fstab lacks its data-only label")
        checked.append(["/etc/fstab", stat.S_IFREG, FSTAB])
        for filename, expected in [
            ("/usr/lib/systemd/systemd-remount-fs.extra", "p4_linux_runtime_lib_t"),
            ("/usr/lib/systemd/systemd-remount-fs/child", "p4_linux_runtime_lib_t"),
            ("/usr/bin/mount-extra", "p4_linux_native_bin_t"),
            ("/usr/bin/umount", "p4_linux_native_bin_t"),
            ("/etc/fstab.extra", "p4_linux_native_config_t"),
        ]:
            if lookup(filename, stat.S_IFREG) != expected:
                raise ValueError("Remount execution label extends to an unselected file")
            checked.append([filename, stat.S_IFREG, expected])
        for filename, mode in [("/etc/fstab", stat.S_IFLNK),
                ("/etc/fstab", stat.S_IFDIR),
                ("/dev/disk/by-uuid/01c27223-3933-481e-9836-7bd0ef1be8c9", stat.S_IFLNK),
                ("/dev/vda", stat.S_IFBLK), ("/dev/nvme0n1p2", stat.S_IFBLK)]:
            try:
                actual = lookup(filename, mode)
            except OSError as error:
                if error.errno != 2: raise
                actual = None
            if actual in (FSTAB, ROOT_LINK, ROOT_BLOCK):
                raise ValueError("Root-device custody escaped its held-inode transaction")
            checked.append([filename, mode, actual])
    finally:
        lib.selabel_close(handle)
    return {"selected_and_negative_cases": len(checked),
            "matrix_sha256": hashlib.sha256(json.dumps(checked).encode()).hexdigest()}
