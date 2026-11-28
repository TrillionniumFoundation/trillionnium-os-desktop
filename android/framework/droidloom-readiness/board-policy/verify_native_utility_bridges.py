"""Verify the normal held-config and typed udev control bridges."""
import hashlib
import json
import re

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_shared_payload_cgroup_policy import parse_expression
from verify_native_stdio import class_permissions

MODULE = "p4_linux_module_loader_t"
UDEV = "p4_linux_udev_t"
LISTENER = "p4_linux_udev_listener_t"
COMPUTED_TRANSITION = "(typetransition init_t p4_linux_udev_exec_t process p4_linux_udev_t)"
BASELINE = {
    "binary": {"bytes": 1378147, "sha256": "334f85991aa8b821efbd8ee793083d0031ff1ffbb9bddac7e928c5fa2092d42c"},
    "exported": {"bytes": 11026119, "sha256": "87199686510833e1f2424e12faa9510b900646adf3ad89628ebc68899be50e39"},
}
DOCUMENTS = {
    "src/modules-load/modules-load.c", "src/basic/fd-util.c", "src/basic/fd-util.h",
    "src/udev/udevadm-control.c", "src/udev/udev-varlink.c",
    "src/core/service.c", "src/core/socket.c", "src/shared/selinux-util.c",
}
NORMAL_FILES = {
    "usr/lib/systemd/system/systemd-modules-load.service",
    "usr/lib/systemd/system/netplan-configure.service",
    "usr/lib/systemd/system/systemd-udevd.service",
    "usr/lib/systemd/system/systemd-udevd-control.socket",
    "usr/lib/systemd/system/systemd-udevd-varlink.socket",
    "usr/lib/systemd/systemd-modules-load", "usr/bin/udevadm",
}
# The existing listener type labels both normal udev control endpoints.
# The proc type is a symlink type, not a new permission to read other PID bodies.
PERMISSIONS = {
    (MODULE, "proc", "lnk_file"): {"read"},
    (MODULE, "proc", "dir"): {"getattr", "search"},
    (MODULE, MODULE, "dir"): {"getattr", "search", "open", "read"},
    (MODULE, MODULE, "lnk_file"): {"getattr", "read"},
    (MODULE, "p4_linux_native_config_t", "file"): {"getattr", "open", "read", "map"},
    (MODULE, "p4_linux_usrmerge_link_t", "lnk_file"): {"getattr", "read"},
    (UDEV, LISTENER, "sock_file"): {"write"},
    (UDEV, LISTENER, "dir"): set(),
    (UDEV, LISTENER, "file"): set(),
    (UDEV, LISTENER, "lnk_file"): set(),
    (UDEV, UDEV, "unix_stream_socket"): {
        "accept", "bind", "connect", "connectto", "create", "getattr",
        "getopt", "listen", "read", "setopt", "shutdown", "write",
    },
    (UDEV, "init_t", "unix_stream_socket"): {
        "accept", "getattr", "getopt", "listen", "read", "setopt", "write",
    },
    (UDEV, "init_t", "lnk_file"): set(),
    (UDEV, "sysfs", "file"): {"getattr", "open", "read"},
    (UDEV, "sysfs_net", "file"): {"getattr", "open", "read"},
}
NEW_BITS = (
    (MODULE, "proc", "lnk_file", "read"),
    (UDEV, LISTENER, "sock_file", "write"),
    (UDEV, UDEV, "unix_stream_socket", "connectto"),
)


def source_contract(here):
    path = here / "native-utility-bridges-source.json"
    body = path.read_bytes()
    obj = json.loads(body)
    if set(obj) != {"schema", "baseline", "module_configuration", "udev_control",
                    "source_documents", "normal_files"}:
        raise ValueError("Utility bridge source fields differ")
    if (obj["schema"] != "droidloom.native-utility-bridges-source.v1"
            or obj["baseline"] != BASELINE
            or obj["module_configuration"] != {
                "actor": MODULE,
                "operation": "apply_conf_file -> fopen(FORMAT_PROC_FD_PATH(c->fd), re)",
                "descriptor_path": "/proc/self/fd/<already-held-config-fd>",
                "printed_path_is_original_name": True,
                "new_permission": ["proc", "lnk_file", "read"],
                "new_configuration_body_access": False,
            }
            or obj["udev_control"] != {
                "actor": UDEV, "command": ["udevadm", "control", "--reload"],
                "socket_paths": ["/run/udev/control", "/run/udev/io.systemd.Udev"],
                "listener_type": LISTENER, "peer_type": UDEV,
                "computed_transition": COMPUTED_TRANSITION,
                "new_permissions": [[LISTENER, "sock_file", "write"],
                                    [UDEV, "unix_stream_socket", "connectto"]],
                "new_socket_creation": False, "manager_peer_connectto": False,
                "sysfs_trigger_qualified": False,
            }):
        raise ValueError("Utility bridge source semantics differ")
    for group, names in (("source_documents", DOCUMENTS), ("normal_files", NORMAL_FILES)):
        pins = obj[group]
        if not isinstance(pins, dict) or set(pins) != names:
            raise ValueError("Utility bridge normal source roster differs")
        for pin in pins.values():
            if (not isinstance(pin, dict) or set(pin) != {"bytes", "sha256"}
                    or type(pin["bytes"]) is not int or pin["bytes"] <= 0
                    or not isinstance(pin["sha256"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])):
                raise ValueError("Malformed utility bridge normal source pin")
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "contents": obj}


def verify_native_utility_bridges(library, binary, exported, here):
    source = source_contract(here)
    text = exported.read_text()
    lines = text.splitlines()
    members = Membership(text)
    vocabulary = {kind: class_permissions(lines, kind)
                  for _, _, kind in PERMISSIONS}
    raw = {key: set() for key in PERMISSIONS}
    manager_transition = set()

    def matches(actor, target, source_type, target_type):
        return (members.member(actor, source_type)
                and ((target == "self" and source_type == target_type)
                     or (target != "self" and members.member(target, target_type))))

    for line in lines:
        if line.startswith("(allow "):
            form = parse_expression(line)
            if (len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2):
                raise ValueError("Unmodeled utility bridge allow")
            actor, target, (kind, names) = form[1:]
            for key in raw:
                s, t, k = key
                if k == kind and matches(actor, target, s, t):
                    if not isinstance(names, list) or not set(names).issubset(vocabulary[k]):
                        raise ValueError("Unmodeled utility bridge permission")
                    raw[key].update(names)
            if kind == "process" and matches(actor, target, "init_t", UDEV):
                manager_transition.update(names)
        elif line.startswith("(allowx "):
            form = parse_expression(line)
            if (len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 3):
                raise ValueError("Unmodeled utility bridge extended permission")
            actor, target, (_, kind, _) = form[1:]
            if any(kind == k and matches(actor, target, s, t) for s, t, k in raw):
                raise ValueError("Utility bridge acquired an extended permission")
    if raw != PERMISSIONS:
        raise ValueError("Utility bridge permission or full class complement differs")
    if manager_transition & {"transition", "dyntransition"}:
        raise ValueError("Computed udev service SID authorized manager execution")
    if lines.count(COMPUTED_TRANSITION) != 1:
        raise ValueError("Normal udev computed service SID differs")

    # libsepol has process-global state: construct one policy and consume every
    # query before any other ContextPolicy object is constructed.
    policy = ContextPolicy(library, binary)
    rows = []
    count = 0
    for source_level in LEVELS:
        for target_level in LEVELS:
            for (s, t, kind), names in PERMISSIONS.items():
                _, bits = policy.permissions(kind, vocabulary[kind])
                permitted = sum(bits[p] for p in names)
                target_role = "system_r" if t in (s, "init_t") else "object_r"
                value = policy.context_av(
                    f"u:system_r:{s}:{source_level}",
                    f"u:{target_role}:{t}:{target_level}", kind, vocabulary[kind])
                if value & ~permitted:
                    raise ValueError("Utility bridge category pair escaped its complement")
                if source_level == target_level == "s0" and value != permitted:
                    raise ValueError("Normal utility bridge is denied")
                rows.append([s, t, kind, source_level, target_level, value])
                count += len(vocabulary[kind])
    process = class_permissions(lines, "process")
    _, bits = policy.permissions("process", process)
    for sl in LEVELS:
        for tl in LEVELS:
            value = policy.context_av(f"u:system_r:init_t:{sl}",
                                      f"u:system_r:{UDEV}:{tl}", "process", process)
            if value & (bits["transition"] | bits["dyntransition"]):
                raise ValueError("Manager acquired an effective udev process transition")
    return {
        "schema": "droidloom.native-utility-bridges-proof.v1",
        "source": source, "new_te_permission_bits": len(NEW_BITS),
        "new_permissions": [list(row) for row in NEW_BITS],
        "raw_permissions": [[s, t, k, sorted(v)] for (s, t, k), v in raw.items()],
        "category_pairs": len(LEVELS) ** 2,
        "full_class_permission_checks": count,
        "effective_vectors": rows,
        "matrix_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
        "computed_service_transition": COMPUTED_TRANSITION,
        "manager_process_transition": False,
        "source_bound_readback_required": True,
        "sysfs_trigger_qualified": False,
        "runtime_qualified": False,
    }
