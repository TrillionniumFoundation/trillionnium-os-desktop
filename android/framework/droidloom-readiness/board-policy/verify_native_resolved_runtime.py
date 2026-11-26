"""The normal executor may prepare only resolved's typed socket metadata."""
import hashlib
import json
import re

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_shared_payload_cgroup_policy import parse_expression, original_xperms
from verify_native_stdio import class_permissions

ROLE = "p4_linux_service_executor_t"
TARGET = "p4_linux_resolved_run_t"
SOCKETS = (
    "/run/systemd/resolve/io.systemd.Resolve",
    "/run/systemd/resolve/io.systemd.Resolve.Monitor",
)
PERMISSIONS = {
    "sock_file": {"getattr", "setattr"},
    "dir": {"getattr", "search", "open", "read", "create", "setattr"},
    "file": set(),
    "lnk_file": set(),
}
DOCUMENTS = {
    "src/core/exec-invoke.c",
    "src/core/socket.c",
    "src/shared/chown-recursive.c",
    "src/basic/fs-util.c",
    "src/basic/xattr-util.c",
}
KERNEL_DOCUMENTS = {"security/selinux/hooks.c", "fs/posix_acl.c"}
NORMAL_FILES = {
    "usr/lib/systemd/system/systemd-resolved.service",
    "usr/lib/systemd/system/systemd-resolved-varlink.socket",
    "usr/lib/systemd/system/systemd-resolved-monitor.socket",
}


def source_contract(here):
    path = here / "native-resolved-runtime-source.json"
    body = path.read_bytes()
    obj = json.loads(body)
    if set(obj) != {"schema", "actor", "target", "runtime_directory", "socket_paths",
                    "normal_socket_owner", "consumer_user", "source_documents",
                    "kernel_documents", "normal_files", "operation", "old_raw"}:
        raise ValueError("Resolved runtime source contract fields differ")
    if (obj["schema"] != "droidloom.native-resolved-runtime-source.v1"
            or obj["actor"] != ROLE or obj["target"] != TARGET
            or obj["runtime_directory"] != "/run/systemd/resolve"
            or obj["socket_paths"] != list(SOCKETS)
            or obj["normal_socket_owner"] != {"uid": 0, "gid": 0}
            or obj["consumer_user"] != "systemd-resolve"
            or obj["operation"] != {
                "path": "setup_exec_directory -> path_chown_recursive -> chown_one",
                "metadata": ["fstat", "remove_posix_acl", "fchownat", "fchmod"],
                "acl_lsm_check_precedes_absence_result": True,
                "socket_io": False, "socket_create": False,
            }
            or obj["old_raw"] != {"sock_file": [], "file": [], "lnk_file": [],
                                 "dir": sorted(PERMISSIONS["dir"])}):
        raise ValueError("Resolved runtime source semantics differ")
    for group, names in (("source_documents", DOCUMENTS),
                         ("kernel_documents", KERNEL_DOCUMENTS),
                         ("normal_files", NORMAL_FILES)):
        pins = obj[group]
        if not isinstance(pins, dict) or set(pins) != names:
            raise ValueError("Resolved fixed normal input set differs")
        for pin in pins.values():
            if (not isinstance(pin, dict) or set(pin) != {"bytes", "sha256"}
                    or not isinstance(pin["bytes"], int) or pin["bytes"] <= 0
                    or not isinstance(pin["sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])):
                raise ValueError("Malformed resolved normal input pin")
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "contents": obj}


def verify_native_resolved_runtime(library, binary, exported, here):
    source = source_contract(here)
    text = exported.read_text()
    lines = text.splitlines()
    members = Membership(text)
    policy = ContextPolicy(library, binary)
    vocabulary = {kind: class_permissions(lines, kind) for kind in PERMISSIONS}
    raw = {kind: set() for kind in PERMISSIONS}
    for line in lines:
        if not line.startswith("(allow "):
            continue
        form = parse_expression(line)
        if (len(form) != 4 or not isinstance(form[3], list)
                or len(form[3]) != 2):
            raise ValueError("Unmodeled resolved metadata rule")
        actor, target, (kind, names) = form[1:]
        if (kind in raw and members.member(actor, ROLE)
                and target != "self" and members.member(target, TARGET)):
            if not isinstance(names, list) or not set(names).issubset(vocabulary[kind]):
                raise ValueError("Unknown resolved metadata permission")
            raw[kind].update(names)
    if raw != PERMISSIONS:
        raise ValueError("Resolved metadata permission or full complement differs")
    masks = original_xperms([exported], [ROLE], TARGET,
                           class_names=("dir", "file", "lnk_file"))
    if any(masks[kind][ROLE] for kind in masks):
        raise ValueError("Resolved metadata acquired an ioctl filter")
    # The shared filesystem helper intentionally does not model sock_file.
    # No extended ioctl rule at all may cover this exact socket metadata pair.
    for line in lines:
        if not line.startswith("(allowx "):
            continue
        form = parse_expression(line)
        if len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 3:
            raise ValueError("Unmodeled resolved extended permission")
        actor, target, (operation, kind, values) = form[1:]
        if (kind == "sock_file" and members.member(actor, ROLE)
                and target != "self" and members.member(target, TARGET)):
            raise ValueError("Resolved socket metadata acquired an ioctl filter")
    masks["sock_file"] = {ROLE: 0}
    rows = []
    count = 0
    for source_level in LEVELS:
        for target_level in LEVELS:
            for kind, names in PERMISSIONS.items():
                _, bits = policy.permissions(kind, vocabulary[kind])
                permitted = sum(bits[p] for p in names)
                value = policy.context_av(
                    f"u:system_r:{ROLE}:{source_level}",
                    f"u:object_r:{TARGET}:{target_level}", kind, vocabulary[kind])
                if value & ~permitted:
                    raise ValueError("Resolved category pair escaped its complement")
                if source_level == target_level == "s0" and value != permitted:
                    raise ValueError("Normal resolved metadata preparation is denied")
                rows.append([source_level, target_level, kind, value])
                count += len(vocabulary[kind])
    return {
        "schema": "droidloom.native-resolved-runtime-proof.v1",
        "source": source, "actor": ROLE, "target": TARGET,
        "socket_paths": list(SOCKETS), "new_te_permission_bits": 2,
        "raw_permissions": {k: sorted(v) for k, v in raw.items()},
        "directory_permissions_unchanged": sorted(PERMISSIONS["dir"]),
        "ioctls": {kind: [] for kind in masks},
        "category_pairs": len(LEVELS) ** 2,
        "full_class_permission_checks": count, "effective_vectors": rows,
        "matrix_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        "source_bound_readback_required": True,
        "runtime_qualified": False,
    }
