"""Verify normal per-UID cgroup ownership against the actual strict link.

The input identities and stock delegation files were read from the selected
normal Ubuntu roots. No generic cgroup, Android payload, or new capability
grant is part of this contract. This is a normal policy-linker component.
"""
import hashlib
import json
import re

from derive_native_uevent_policy import ContextPolicy
from derive_shared_payload_cgroup_policy import parse_expression


PREFIX = "p4_linux_user_"
PID1 = "init_t"
EXECUTOR = "p4_linux_service_executor_t"
MANAGER = "p4_linux_user_manager_t"
USER_EXECUTOR = "p4_linux_user_executor_t"
CREATORS = (PID1, EXECUTOR, MANAGER, USER_EXECUTOR)
ROOT = PREFIX + "slice_t"
UNSELECTED = PREFIX + "unselected_cgroup_t"
SESSION = PREFIX + "session_cgroup_t"
INITIAL = PREFIX + "manager_init_cgroup_t"
DELEGATED = PREFIX + "delegated_cgroup_t"
FILE_NAMES = (
    "system_control_t", "system_tasks_t", "manager_read_t",
    "manager_delegate_t", "manager_tasks_t", "manager_init_control_t",
    "manager_init_tasks_t", "delegated_control_t", "delegated_tasks_t",
)
SOURCE_NAMES = (
    "runtime/droidloom-early-boot/linux_run_label.c",
    "runtime/droidloom-early-boot/board_policy.c",
    "runtime/droidloom-early-boot/board_init.c",
)


def load_contract(here):
    value = json.loads((here / "native-user-cgroups.json").read_text())
    if (set(value) != {"schema", "identities", "systemd_version", "delegate_subgroup",
                      "delegation_attributes", "normal_units", "early_boot_sources"} or
            value["schema"] != "droidloom.native-user-cgroup-contract.v1" or
            value["systemd_version"] != "259.9-0ubuntu0.1+p4gentmp1" or
            value["delegate_subgroup"] != "init.scope"):
        raise ValueError("Unknown native user cgroup source contract")
    identities = value["identities"]
    if len(identities) != 3 or {row["profile"] for row in identities} != {
            "original-ubuntu", "complete-normal-ubuntu", "desktop-user"}:
        raise ValueError("Native user cgroup identities are not the selected three profiles")
    seen = set()
    for row in identities:
        if (set(row) != {"profile", "account", "uid", "gid"} or
                type(row["uid"]) is not int or type(row["gid"]) is not int or
                not 0 < row["uid"] <= 1000 or not 0 < row["gid"] <= 1000 or
                row["uid"] in seen or
                (row["profile"] == "desktop-user" and
                 (row["account"], row["uid"], row["gid"]) != ("alex", 1000, 1000)) or
                (row["profile"] != "desktop-user" and
                 (row["account"] != "gdm" or row["uid"] >= 1000))):
            raise ValueError("Invalid native login UID/GID identity")
        seen.add(row["uid"])
    if value["delegation_attributes"] != [
            "cgroup.procs", "cgroup.subtree_control", "cgroup.threads",
            "memory.oom.group", "memory.reclaim"]:
        raise ValueError("Stock cg_set_access() delegation attributes differ")
    if set(value["early_boot_sources"]) != set(SOURCE_NAMES):
        raise ValueError("Native root-membership FD source set differs")
    if set(value["normal_units"]) != {
            "usr/lib/systemd/system/user.slice",
            "usr/lib/systemd/system/user@.service",
            "usr/lib/systemd/system/user-runtime-dir@.service",
            "usr/lib/systemd/system/user-.slice.d/10-defaults.conf"}:
        raise ValueError("Native login unit source set differs")
    for group in ("early_boot_sources", "normal_units"):
        for pin in value[group].values():
            if (set(pin) != {"bytes", "sha256"} or type(pin["bytes"]) is not int or
                    pin["bytes"] <= 0 or not re.fullmatch("[0-9a-f]{64}", pin["sha256"])):
                raise ValueError("Malformed native user source pin")
    return value


def source_inputs(here):
    contract = load_contract(here)
    return [here.parents[3] / name for name in sorted(contract["early_boot_sources"])]


def verify_sources(here, contract):
    sources = {}
    contents = {}
    for name, expected in contract["early_boot_sources"].items():
        raw = (here.parents[3] / name).read_bytes()
        pin = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        if pin != expected:
            raise ValueError("Native root-membership FD source changed: " + name)
        sources[name] = pin
        contents[name] = raw.decode()
    held = contents[SOURCE_NAMES[0]]
    owner = contents[SOURCE_NAMES[1]]
    entry = contents[SOURCE_NAMES[2]]
    hold = held.split("int droidloom_hold_linux_init_scope(", 1)[1].split(
        "int droidloom_label_linux_init_scope(", 1)[0]
    release = held.split("void droidloom_close_linux_init_scope(", 1)[1]
    activation = owner.split("int droidloom_board_activate_policy(", 1)[1]
    # The original root inode is opened read-only solely for first-load xattrs.
    # Every path out of the activation function closes the held scope, including
    # root_membership, before the separately authenticated exec handoff.
    if ('openat(held->root.fd, "cgroup.procs", O_RDONLY | O_NOFOLLOW | O_CLOEXEC)' not in hold or
            'if (held->root_membership.fd >= 0)\n        close(held->root_membership.fd);' not in release or
            activation.index("droidloom_close_linux_init_scope(&scope);") >=
            activation.index("return rc == 0 ? 0 : reject(error);") or
            entry.index("if (droidloom_board_activate_policy(") >=
            entry.index('execveat(own, "", next, environ, AT_EMPTY_PATH);') or
            "syscall(SYS_close_range,3U,~0U,CLOSE_RANGE_CLOEXEC)" not in entry):
        raise ValueError("Native root-membership descriptor no longer closes before PID 1")
    return sources


def class_names(lines, cls):
    form = parse_expression(next(x for x in lines if x.startswith("(class " + cls + " ")))
    names = list(form[2])
    for raw in lines:
        if raw.startswith("(classcommon " + cls + " "):
            common = parse_expression(raw)[2]
            names = parse_expression(next(x for x in lines if
                x.startswith("(common " + common + " ")))[2] + names
    if not names or len(set(names)) != len(names) or len(names) > 32:
        raise ValueError("Invalid native cgroup class permissions")
    return names


def verify(library, binary, here, binary_cil, export):
    contract = load_contract(here)
    source_pins = verify_sources(here, contract)
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, binary_cil)
    types = {x[len("(type "):-1] for x in lines if x.startswith("(type ")}
    roles = sorted({(form[1], form[2])
                    for line in lines if line.startswith("(roletype ")
                    for form in [parse_expression(line)]
                    if form[1] in ("r", "system_r") and form[2] in types})
    uids = sorted(row["uid"] for row in contract["identities"])
    slices = [PREFIX + str(uid) + "_slice_t" for uid in uids]
    managers = [PREFIX + str(uid) + "_manager_t" for uid in uids]
    directories = [ROOT, *slices, *managers, SESSION, INITIAL, DELEGATED]
    files = [PREFIX + name for name in FILE_NAMES]
    all_types = set([*directories, *files, UNSELECTED])
    if not all_types.issubset(types) or not roles:
        raise ValueError("Native user cgroup object or actor types are missing")

    # Read every concrete default/named transition from the linked binary.
    # The selected libsepol exports no create-SID API. Below we evaluate only
    # this source-bound object-context case from the actual transition tables,
    # reject alternate default/role/range semantics, and validate the resulting
    # contexts through that same libsepol's context-to-SID API.
    expected_transitions = set()
    def transition(actor, parent, cls, name, target):
        expected_transitions.add((actor, parent, cls, name, target))
    transition(PID1, "p4_linux_cgroup_root_t", "dir", "-.mount", "p4_linux_unit_cgroup_t")
    transition(PID1, "p4_linux_cgroup_root_t", "dir", "user.slice", ROOT)
    for actor in CREATORS:
        transition(actor, ROOT, "dir", None, UNSELECTED)
    for uid, parent, manager in zip(uids, slices, managers):
        transition(PID1, ROOT, "dir", "user-" + str(uid) + ".slice", parent)
        transition(PID1, parent, "dir", None, SESSION)
        transition(PID1, parent, "dir", "user@" + str(uid) + ".service", manager)
        for actor in (EXECUTOR, MANAGER, USER_EXECUTOR):
            transition(actor, parent, "dir", None, UNSELECTED)
        for actor in (PID1, EXECUTOR, USER_EXECUTOR):
            transition(actor, manager, "dir", None, UNSELECTED)
        transition(MANAGER, manager, "dir", None, DELEGATED)
        for actor in (PID1, EXECUTOR, MANAGER):
            transition(actor, manager, "dir", "init.scope", INITIAL)
    for actor in CREATORS:
        for parent in (SESSION, INITIAL):
            transition(actor, parent, "dir", None, UNSELECTED)
        transition(actor, DELEGATED, "dir", None,
                   DELEGATED if actor == MANAGER else UNSELECTED)
    file_groups = (
        ([ROOT, *slices, SESSION], PREFIX + "system_control_t", PREFIX + "system_tasks_t"),
        (managers, PREFIX + "manager_read_t", PREFIX + "manager_tasks_t"),
        ([INITIAL], PREFIX + "manager_init_control_t", PREFIX + "manager_init_tasks_t"),
        ([DELEGATED], PREFIX + "delegated_control_t", PREFIX + "delegated_tasks_t"),
    )
    for parents, default, tasks in file_groups:
        for parent in parents:
            for actor in CREATORS:
                transition(actor, parent, "file", None, default)
                for name in ("cgroup.procs", "cgroup.threads"):
                    transition(actor, parent, "file", name, tasks)
    for parent in managers:
        for actor in CREATORS:
            for name in ("cgroup.subtree_control", "memory.oom.group", "memory.reclaim"):
                transition(actor, parent, "file", name, PREFIX + "manager_delegate_t")
    actual_transitions = set()
    for line in lines:
        if not line.startswith("(typetransition "):
            continue
        form = parse_expression(line)
        if len(form) not in (5, 6):
            raise ValueError("Unsupported linked type transition")
        _, actor, parent, cls, *tail = form
        name, target = (None, tail[0]) if len(tail) == 1 else (tail[0].strip('"'), tail[1])
        if (parent in all_types or target in all_types or
                (parent == "p4_linux_cgroup_root_t" and cls == "dir")):
            actual_transitions.add((actor, parent, cls, name, target))
    if actual_transitions != expected_transitions:
        raise ValueError("Native user cgroup transition table differs: " + repr({
            "missing": sorted(expected_transitions - actual_transitions, key=repr),
            "extra": sorted(actual_transitions - expected_transitions, key=repr)}))

    permissions = {cls: class_names(lines, cls) for cls in ("dir", "file", "lnk_file")}
    bits = {cls: policy.permissions(cls, names)[1] for cls, names in permissions.items()}
    count = 0
    def expected(actor, target, cls):
        allowed = set()
        if actor == PID1:
            if cls == "dir" and target in directories:
                allowed.update("getattr search open read create write add_name remove_name rmdir setattr".split())
            if cls == "file" and target in files:
                allowed.update("getattr open read write watch".split())
        if actor == EXECUTOR:
            if cls == "dir":
                if target in directories:
                    allowed.update("getattr search open".split())
                if target in managers:
                    allowed.update("write add_name setattr".split())
                if target == INITIAL:
                    allowed.update("create read setattr".split())
            if cls == "file":
                wanted = {
                    "system_tasks_t": "getattr open write",
                    "manager_tasks_t": "getattr setattr",
                    "manager_delegate_t": "getattr setattr",
                    "manager_init_control_t": "getattr setattr",
                    "manager_init_tasks_t": "getattr open write setattr",
                }
                allowed.update(wanted.get(target.removeprefix(PREFIX), "").split())
        if actor == MANAGER:
            if cls == "dir":
                if target in directories:
                    allowed.update("getattr search".split())
                if target in managers:
                    allowed.update("open read write add_name remove_name setattr".split())
                if target in (INITIAL, DELEGATED):
                    allowed.update("open read create write add_name remove_name rmdir setattr".split())
            if cls == "file" and target in files and target != PREFIX + "system_tasks_t":
                allowed.update("getattr open read watch".split())
                if target not in (PREFIX + "system_control_t", PREFIX + "manager_read_t"):
                    allowed.add("write")
        if actor == USER_EXECUTOR:
            if cls == "dir":
                if target in directories:
                    allowed.update("getattr search".split())
                if target == DELEGATED:
                    allowed.add("open")
            if cls == "file":
                if target == PREFIX + "delegated_tasks_t":
                    allowed.update("getattr open write".split())
                if target == PREFIX + "manager_tasks_t":
                    allowed.add("write")
        if actor == "p4_linux_journald_t" and cls == "dir" and target in directories:
            allowed.update("getattr search".split())
        return allowed
    # These two original board-owned r-role observers already traverse every
    # p4_linux_data directory through linux-fixed-metadata-observer.cil and
    # linux-query-owner.cil. Preserve exactly metadata, never any file body,
    # enumeration, mutation, or membership authority on the new inode types.
    metadata_observers = {"droidloom_metadata_observer", "droidloom_query_io"}
    mismatches = []
    for role, actor in roles:
        if actor == "kernel" and role == "r":
            continue
        context = "u:" + role + ":" + actor + ":s0"
        for target in sorted(all_types):
            for cls, names in permissions.items():
                wanted = expected(actor, target, cls) if role == "system_r" else set()
                if role == "r" and actor in metadata_observers and cls == "dir":
                    wanted = {"getattr", "search"}
                mask = sum(bits[cls][name] for name in wanted)
                actual = policy.context_av(context, "u:object_r:" + target + ":s0", cls, names)
                if actual != mask:
                    observed = [name for name in names if actual & bits[cls][name]]
                    mismatches.append({
                        "actor": context, "target": target, "class": cls,
                        "wanted": sorted(wanted), "observed": observed})
                count += len(names)
    if mismatches:
        raise ValueError("Native user cgroup AV differs: " +
                         json.dumps(mismatches, sort_keys=True))

    # In the selected 6.18 security_compute_sid(), an object creation with
    # no class defaults/role transition takes the process user, object_r and
    # the transition type. mls_compute_sid() takes the source low level.
    # Both fixed input contexts are u:*:*:s0. Never substitute change_sid or
    # member_sid: those public libsepol functions use different AVTAB rules.
    object_parents = all_types | {"p4_linux_cgroup_root_t"}
    for line in lines:
        if line.startswith("(boolean"):
            raise ValueError("Conditional cgroup creation is outside this fixed contract")
        if line.startswith("(default"):
            form = parse_expression(line)
            classes = form[1] if isinstance(form[1], list) else [form[1]]
            if set(classes) & {"dir", "file"}:
                raise ValueError("Native object creation acquired class defaults")
        if line.startswith("(roletransition "):
            form = parse_expression(line)
            if form[1] == "system_r" and form[2] in object_parents and form[3] in ("dir", "file"):
                raise ValueError("Native cgroup object role transition is unreviewed")
        if line.startswith("(rangetransition "):
            form = parse_expression(line)
            if form[1] in CREATORS and form[2] in object_parents and form[3] in ("dir", "file"):
                raise ValueError("Native cgroup MLS range transition is unreviewed")
    table = {(actor, parent, cls, name): target
             for actor, parent, cls, name, target in actual_transitions}
    if len(table) != len(actual_transitions):
        raise ValueError("Conflicting linked native cgroup transitions")
    def created_context(actor, parent, cls, name):
        policy.context_sid("u:system_r:" + actor + ":s0")
        policy.context_sid("u:object_r:" + parent + ":s0")
        target = table.get((actor, parent, cls, None), parent)
        if name is not None:
            target = table.get((actor, parent, cls, name), target)
        return "u:object_r:" + target + ":s0"
    default_checks = 0
    context_checks = 0
    for actor, parent, cls, name, target in sorted(expected_transitions, key=repr):
        actual_context = created_context(actor, parent, cls, name)
        if policy.context_sid(actual_context) != policy.context_sid("u:object_r:" + target + ":s0"):
            raise ValueError("Linked native cgroup object context differs")
        context_checks += 1
        default_checks += name is None
    # Unknown UID names take the actual non-creatable default, not the
    # neighboring admitted UID's named transition.
    for uid in (0, 1, 121, 980, 982, 1001):
        context = created_context(PID1, ROOT, "dir", "user-" + str(uid) + ".slice")
        if (context != "u:object_r:" + UNSELECTED + ":s0" or
                policy.context_av("u:system_r:" + PID1 + ":s0", context, "dir", ["create"])):
            raise ValueError("An unselected native UID acquired a creatable cgroup")
        context_checks += 1

    journal_metadata_types = [
        "p4_linux_cgroup_root_t", "p4_linux_cgroup_init_scope_t",
        "p4_linux_system_slice_t", "p4_linux_unit_cgroup_t",
        "p4_linux_factory_unit_cgroup_t", "p4_linux_production_unit_cgroup_t",
        "p4_linux_udevd_unit_cgroup_t",
    ]
    required_unit_genfs = {
        '(genfscon cgroup2 "/system.slice" (u object_r p4_linux_system_slice_t ((s0) (s0))))',
        '(genfscon cgroup2 "/system.slice/" (u object_r p4_linux_unit_cgroup_t ((s0) (s0))))',
        '(genfscon cgroup2 "/system.slice/droidloom-instance-factory.service" (u object_r p4_linux_factory_unit_cgroup_t ((s0) (s0))))',
        '(genfscon cgroup2 "/system.slice/droidloom-production.service" (u object_r p4_linux_production_unit_cgroup_t ((s0) (s0))))',
        '(genfscon cgroup2 "/system.slice/systemd-udevd.service" (u object_r p4_linux_udevd_unit_cgroup_t ((s0) (s0))))',
    }
    def genfs_identity(line):
        form = parse_expression(line)
        return (form[1], form[2].strip('"'), form[-1][2], len(form))
    expected_genfs = {genfs_identity(line) for line in required_unit_genfs}
    actual_genfs = {genfs_identity(line) for line in lines if line.startswith("(genfscon ")}
    if not expected_genfs.issubset(actual_genfs):
        raise ValueError("Original native unit metadata paths changed")
    journal_checks = 0
    for target in journal_metadata_types:
        for cls, names in permissions.items():
            actual = policy.context_av("u:system_r:p4_linux_journald_t:s0",
                "u:object_r:" + target + ":s0", cls, names)
            expected = (bits[cls]["getattr"] | bits[cls]["search"]) if cls == "dir" else 0
            if actual != expected:
                raise ValueError("journald gained more than fixed cgroup directory metadata")
            journal_checks += len(names)

    root_checks = 0
    root_permissions = ("open", "read", "write", "append", "setattr", "map", "ioctl")
    for role, actor in roles:
        if actor == "kernel" and role == "r":
            continue
        for permission in root_permissions:
            actual = policy.context_av("u:" + role + ":" + actor + ":s0",
                "u:object_r:p4_linux_cgroup_root_membership_t:s0", "file", [permission])
            wanted = (role == "system_r" and actor in (PID1, EXECUTOR) and permission == "write")
            if bool(actual) != wanted:
                raise ValueError("Root membership single-permission boundary changed: " +
                                 " ".join((role, actor, permission)))
            root_checks += 1
    boundary_checks = 0
    for actor in (MANAGER, USER_EXECUTOR):
        source = "u:system_r:" + actor + ":s0"
        for target in ("cgroup", "cgroup_v2", "cgroup_app", "p4_android_payload_cgroup_t",
                       "p4_linux_production_subtree_t", "p4_linux_factory_membership_t"):
            for cls, names in (
                    ("file", ("open", "read", "write", "append", "create", "setattr")),
                    ("dir", ("create", "write", "add_name", "remove_name", "rmdir", "setattr"))):
                for permission in names:
                    if policy.context_av(source, "u:object_r:" + target + ":s0", cls, [permission]):
                        raise ValueError("Native user manager escaped its delegated subtree")
                    boundary_checks += 1
    return {
        "contract_sha256": hashlib.sha256((here / "native-user-cgroups.json").read_bytes()).hexdigest(),
        "identities": contract["identities"],
        "normal_unit_source_pins": contract["normal_units"],
        "early_boot_source_pins": source_pins,
        "early_boot_root_membership_fd_closed": True,
        "named_transition_checks": sum(row[3] is not None for row in expected_transitions),
        "default_transition_checks": default_checks,
        "linked_object_context_checks": context_checks,
        "transition_verification": "linked-table-and-fixed-object-context",
        "libsepol_create_sid_api_used": False,
        "role_permission_checks": count,
        "existing_metadata_observers": sorted(metadata_observers),
        "root_membership_permission_checks": root_checks,
        "delegated_boundary_permission_checks": boundary_checks,
        "process_role_types": len(roles),
        "object_types": len(all_types),
        "generic_cgroup_writes_denied": True,
        "android_payload_access_denied": True,
        "journal_cgroup_metadata_only": True,
        "journal_metadata_types": journal_metadata_types,
        "journal_metadata_permission_checks": journal_checks,
        "capabilities_added": [],
        "runtime_qualified": False,
    }
