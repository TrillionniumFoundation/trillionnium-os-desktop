"""Keep Netplan's normal network trigger behind ordinary coldplug preparation.

This verifier adds no policy. The existing held-inode labeler and the original
udevadm program retain their exact six-object boundary. Dependency activation
does not qualify a later hotplug inode or prove that Netplan's post command ran.
"""
import hashlib
import json
import re

from derive_native_uevent_policy import ContextPolicy
from derive_shared_payload_cgroup_policy import parse_expression

ROLE = "p4_linux_udev_t"
REQUIRED_UNIT = "systemd-udev-trigger.service"
DESTINATION = "usr/lib/systemd/system/netplan-configure.service.d/50-droidloom-uevent-order.conf"
DROPIN = (
    "# Finish ordinary coldplug and its fixed native uevent preparation first.\n"
    "# Netplan keeps its original configure, reload, and network-trigger commands.\n"
    "[Unit]\n"
    "Requires=systemd-udev-trigger.service\n"
    "After=systemd-udev-trigger.service\n"
).encode()
COMMON = (
    "ioctl read write create getattr setattr lock relabelfrom relabelto append "
    "map unlink link rename execute quotaon mounton audit_access open execmod "
    "watch watch_mount watch_sb watch_with_perm watch_reads"
).split()
PERMISSIONS = {
    "dir": COMMON + "add_name remove_name reparent search rmdir".split(),
    "file": COMMON + ["execute_no_trans", "entrypoint"],
    "lnk_file": COMMON,
}
SOURCES = (
    "sysfs", "sysfs_devices_system_cpu", "sysfs_hwrandom",
    "sysfs_loop", "sysfs_net", "sysfs_uprobe",
)
GIT_INPUTS = (
    "android/framework/droidloom-readiness/board-policy/ubuntu-udev-trigger-label.conf",
    "android/framework/droidloom-readiness/board-policy/ubuntu-native-uevent.cil",
    "android/framework/droidloom-readiness/board-policy/native-uevent-labels.json",
    "android/framework/droidloom-readiness/board-policy/native-netplan-source.json",
    "runtime/droidloom-supervisor/src/native_uevent_label.rs",
    "runtime/droidloom-supervisor/src/native_hardware_label.rs",
)
PACKAGERS = tuple("tools/droidloom-update/src/" + name for name in (
    "early_boot_package.rs", "host_archive.rs", "package.rs",
))
NORMAL_UNITS = {
    "netplan-configure.service": (879, "6893fca2c14d53951c73f396f7528b0b1baa9f570ca9cf099dc1c71df1aa2724"),
    "systemd-udev-trigger.service": (787, "42e585c2859b76e4106b64b915dc900f1e5390bf32686a9181acd95eea1c7064"),
}
POST = ["udevadm control --reload", "udevadm trigger --action=add --subsystem-match=net"]
SOURCE_DOCUMENTS = frozenset((
    "src/analyze/analyze-verify-util.c", "src/core/load-fragment.c",
    "src/core/service.c", "src/core/transaction.c",
    "src/libsystemd/sd-device/sd-device.c", "src/udev/udevadm-trigger.c",
))
NORMAL_FILES = frozenset((
    "usr/bin/udevadm", "usr/libexec/netplan/configure",
    "usr/lib/systemd/system/netplan-configure.service",
    "usr/lib/systemd/system/systemd-udev-trigger.service",
))


def pin(path):
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def source_inputs(here):
    root = here.parents[3]
    return [here / "native-netplan-trigger-source.json",
            here / "ubuntu-netplan-trigger-order.conf",
            *(root / name for name in GIT_INPUTS),
            *(root / name for name in PACKAGERS)]


def unit_fields(body):
    result = {}
    section = None
    pending = ""
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        pending += line
        if pending.endswith("\\"):
            pending = pending[:-1] + " "
            continue
        line, pending = pending, ""
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if section is None or "=" not in line:
            raise ValueError("Malformed fixed normal unit source")
        key, value = line.split("=", 1)
        result.setdefault((section, key), []).append(value.strip())
    if pending:
        raise ValueError("Incomplete fixed normal unit continuation")
    return result


def validate_sources(here):
    contract = json.loads((here / "native-netplan-trigger-source.json").read_text())
    if (contract["schema"] != "droidloom.native-netplan-trigger-source.v1" or
            contract["systemd_version"] != "259.9-0ubuntu0.1+p4gentmp2" or
            contract["required_unit"] != REQUIRED_UNIT or
            contract["old_policy"]["sha256"] !=
            "334f85991aa8b821efbd8ee793083d0031ff1ffbb9bddac7e928c5fa2092d42c" or
            contract["permission_layout"] != PERMISSIONS):
        raise ValueError("Fixed Netplan trigger source contract differs")
    if (set(contract["source_documents"]) != SOURCE_DOCUMENTS or
            set(contract["normal_files"]) != NORMAL_FILES):
        raise ValueError("Fixed normal Netplan trigger source roster differs")
    for group in ("source_documents", "normal_files"):
        for name, record in contract[group].items():
            if (set(record) != {"bytes", "sha256"} or
                    type(record["bytes"]) is not int or record["bytes"] <= 0 or
                    not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
                raise ValueError("Invalid normal source pin: " + name)
    root = here.parents[3]
    if set(contract["git_sources"]) != set(GIT_INPUTS):
        raise ValueError("Netplan trigger Git source roster differs")
    for name, expected in contract["git_sources"].items():
        if pin(root / name) != expected:
            raise ValueError("Netplan trigger source bytes differ: " + name)
    body = (here / "ubuntu-netplan-trigger-order.conf").read_bytes()
    dropin = contract["dropin"]
    if (body != DROPIN or dropin["source"] != "ubuntu-netplan-trigger-order.conf" or
            dropin["path"] != DESTINATION or dropin["mode"] != 0o444 or
            {key: dropin[key] for key in ("bytes", "sha256")} !=
            pin(here / "ubuntu-netplan-trigger-order.conf") or
            unit_fields(body.decode()) != {
                ("Unit", "Requires"): [REQUIRED_UNIT],
                ("Unit", "After"): [REQUIRED_UNIT]}):
        raise ValueError("Netplan drop-in may only require and follow ordinary coldplug")
    if set(contract["normal_unit_bodies"]) != set(NORMAL_UNITS):
        raise ValueError("Normal trigger unit roster differs")
    units = {}
    for name, (size, digest) in NORMAL_UNITS.items():
        text = contract["normal_unit_bodies"][name]
        if (len(text.encode()), hashlib.sha256(text.encode()).hexdigest()) != (size, digest):
            raise ValueError("The fixed normal unit body changed: " + name)
        if contract["normal_files"]["usr/lib/systemd/system/" + name] != {
                "bytes": size, "sha256": digest}:
            raise ValueError("Normal unit source pin differs: " + name)
        units[name] = unit_fields(text)
    netplan = units["netplan-configure.service"]
    if (netplan.get(("Service", "ExecStart")) != ["/usr/libexec/netplan/configure"] or
            netplan.get(("Service", "ExecStartPost")) != POST or
            contract["normal_commands"] != {
                "ExecStart": ["/usr/libexec/netplan/configure"], "ExecStartPost": POST}):
        raise ValueError("The normal Netplan command sequence changed")
    if (netplan.get(("Unit", "DefaultDependencies")) != ["no"] or
            units[REQUIRED_UNIT].get(("Unit", "DefaultDependencies")) != ["no"] or
            "netplan-configure.service" in " ".join(
                units[REQUIRED_UNIT].get(("Unit", "After"), []))):
        raise ValueError("The fixed coldplug ordering premise changed")
    mapping = {"schema": "droidloom.native-uevent-label-map.v1",
               "labels": [{"source": name, "target": "p4_native_uevent_" + name}
                          for name in SOURCES]}
    if (contract["uevent_map"] != mapping or
            json.loads((here / "native-uevent-labels.json").read_text()) != mapping):
        raise ValueError("Netplan must use the existing six-object uevent preparation")
    expected_views = []
    source_views = {"dir": {"getattr", "open", "read", "search"},
                    "file": {"getattr", "open", "read"},
                    "lnk_file": {"getattr", "read"}}
    for source in SOURCES:
        for kind, target in (("source", source), ("target", "p4_native_uevent_" + source)):
            for cls, names in PERMISSIONS.items():
                wanted = source_views[cls] if kind == "source" else (
                    {"getattr", "open", "read", "write"} if cls == "file" else set())
                expected_views.append((target, kind, cls, [name for name in names if name in wanted]))
    observed = [(row["target"], row["kind"], row["class"], row["allowed"])
                for row in contract["fixed_udev_views"]]
    if observed != expected_views:
        raise ValueError("Historical udev views differ from the fixed source boundary")
    for name in PACKAGERS:
        text = (root / name).read_text()
        pattern = (r'\(\s*"' + re.escape(DESTINATION) +
                   r'",\s*include_bytes!\("\.\./\.\./\.\./android/framework/'
                   r'droidloom-readiness/board-policy/ubuntu-netplan-trigger-order\.conf"\)'
                   r'\.as_slice\(\),\s*\)')
        if len(re.findall(pattern, text)) != 1:
            raise ValueError("Netplan drop-in is not in the normal package path: " + name)
    return contract


def permission_layout(text):
    classes, common, bases = {}, {}, {}
    for line in text.splitlines():
        if line.startswith(("(class ", "(common ", "(classcommon ")):
            row = parse_expression(line)
            if row[0] == "class":
                classes[row[1]] = row[2]
            elif row[0] == "common":
                common[row[1]] = row[2]
            else:
                bases[row[1]] = row[2]
    return {name: common.get(bases.get(name), []) + classes[name] for name in PERMISSIONS}


def verify_native_netplan_trigger(library, linked, binary_cil, here):
    contract = validate_sources(here)
    if permission_layout(binary_cil.read_text()) != PERMISSIONS:
        raise ValueError("The original file/dir/link permission layout changed")
    policy = ContextPolicy(library, linked)
    vectors = []
    for row in contract["fixed_udev_views"]:
        cls = row["class"]
        names = PERMISSIONS[cls]
        _, bits = policy.permissions(cls, names)
        wanted = sum(bits[name] for name in row["allowed"])
        actual = policy.context_av("u:system_r:" + ROLE + ":s0",
                                   "u:object_r:" + row["target"] + ":s0", cls, names)
        if actual != wanted:
            raise ValueError("Netplan udev object boundary differs: " + row["target"] + ":" + cls)
        vectors.append({"target": row["target"], "class": cls, "mask": actual})
    return {
        "schema": "droidloom.native-netplan-trigger-proof.v1",
        "source_contract": pin(here / "native-netplan-trigger-source.json"),
        "dropin": contract["dropin"],
        "required_unit": REQUIRED_UNIT,
        "ordering_after": REQUIRED_UNIT,
        "normal_commands": contract["normal_commands"],
        "command_order_preserved": True,
        "normal_service_capabilities_overridden": False,
        "new_policy_permissions": 0,
        "uevent_sources": 6,
        "effective_vectors": len(vectors),
        "matrix_context": "s0",
        "permission_checks": 12 * sum(map(len, PERMISSIONS.values())),
        "vectors": vectors,
        "normal_unit_files": 2,
        "source_inputs": len(source_inputs(here)),
        "runtime_netplan_trigger_qualified": False,
        "later_hotplug_qualified": False,
    }
