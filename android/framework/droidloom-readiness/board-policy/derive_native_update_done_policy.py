"""Admit unchanged systemd-update-done and its two fixed atomic markers.

The external normal source readback binds systemd, libselinux and the selected
kernel. This policy producer checks complete binary authority and constraints;
it never executes the utility or writes either marker.
"""
import ctypes
import hashlib
import json
import stat

from derive_native_uevent_policy import ContextPolicy, LEVELS
from derive_native_random_seed_policy import RawPolicy, _bits, _context_role
from derive_preserved_alias_policy import (
    _context, derive_preserved_aliases, verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression

ROLE = "p4_linux_update_done_t"
ENTRY = "p4_linux_update_done_exec_t"
VAR = "p4_linux_update_done_var_dir_t"
ETC_FILE = "p4_linux_update_done_etc_file_t"
VAR_FILE = "p4_linux_update_done_var_file_t"
ETC = "p4_linux_sysusers_etc_root_t"
EXECUTOR = "p4_linux_service_executor_t"
NEW_TYPES = {ROLE, ENTRY, VAR, ETC_FILE, VAR_FILE}
ALIASES = [
    {"source": "p4_linux_setup_exec_t", "target": ENTRY, "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": VAR, "class": "dir"},
    {"source": "p4_linux_native_config_t", "target": ETC_FILE, "class": "file"},
    {"source": "p4_linux_native_data_t", "target": VAR_FILE, "class": "file"},
]
PARENT_PERMISSIONS = {"getattr", "open", "read", "search", "write", "add_name", "remove_name"}
FILE_PERMISSIONS = {"getattr", "open", "read", "write", "create", "setattr", "rename", "unlink"}
SELINUXFS_READ = {"getattr", "open", "read", "map"}
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
OLD_ENTRY = "(typetransition " + EXECUTOR + " p4_linux_setup_exec_t process p4_linux_setup_t)"
COPIED_ENTRY = "(typetransition " + EXECUTOR + " " + ENTRY + " process p4_linux_setup_t)"
SELECTED_ENTRY = "(typetransition " + EXECUTOR + " " + ENTRY + " process " + ROLE + ")"
DIRECTORY_RELABEL_GUARD = "(validatetrans dir (or (neq t3 p4_linux_hardware_label_t) (or (eq t1 device) (eq t1 t2))))"
DIRECTORY_RELABEL_GUARD_SHA256 = "13e95abc68e40d41bd459bcaa270c23b3ce47db852053bc0413ca4038ea506b8"
CONTRACT_PIN = (10554, 'c5f3d92398640e191985934880112b19399b6a323b1969da2f8e6f03cd044271')
# All board data labels retain these existing metadata-only directory-class
# views even when the new inode label is selected only for regular files.
NORMAL_METADATA_PREIMAGE = {
    (target, actor, "dir"): {"getattr", "search"}
    for target in (ENTRY, ETC_FILE, VAR_FILE)
    for actor in ("droidloom_metadata_observer", "droidloom_query_io")
}


def contract(here):
    data = (here / "native-update-done-source.json").read_bytes()
    if (len(data), hashlib.sha256(data).hexdigest()) != CONTRACT_PIN:
        raise ValueError("The fixed normal update-done source contract changed")
    value = json.loads(data)
    if (value["schema"] != "droidloom.native-update-done-source.v1"
            or value["aliases"] != ALIASES or value["role"] != ROLE
            or value["unit"]["argv"] != ["/usr/lib/systemd/systemd-update-done"]
            or [row["path"] for row in value["parents"]] != ["/etc", "/var"]
            or [row["type"] for row in value["parents"]] != [ETC, VAR]
            or any(not row["must_already_exist"] or row["create_permission"] for row in value["parents"])
            or [row["path"] for row in value["outputs"]] != ["/etc/.updated", "/var/.updated"]
            or [row["type"] for row in value["outputs"]] != [ETC_FILE, VAR_FILE]
            or any(row["temporary_basename_regex"] != r"\.#\.updated[0-9a-f]{16}"
                   or row["open_mode"] != "O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOCTTY"
                   or row["fsync_called"] is not False or row["futimens"] is not True
                   for row in value["outputs"])
            or value["label_lookup"]["validation_option"] is not False
            or value["label_lookup"]["security_permissions"] != []
            or value["label_lookup"]["netlink_selinux_permissions"] != []
            or value["label_lookup"]["selinuxfs_file_permissions"] != sorted(SELINUXFS_READ)
            or value["unit_environment_overridden"] is not False
            or value["direct_r13_child_avc_observed"] is not False
            or value["kernel_runtime_qualified"] is not False):
        raise ValueError("The normal fixed update-done lifecycle boundary changed")
    return value


def _base_role():
    read = {"getattr", "open", "read"}
    executable = read | {"execute", "map"}
    return {
        (ENTRY, "file"): executable | {"entrypoint"},
        (ETC_FILE, "file"): FILE_PERMISSIONS,
        (VAR_FILE, "file"): FILE_PERMISSIONS,
        (ETC, "dir"): PARENT_PERMISSIONS,
        (VAR, "dir"): PARENT_PERMISSIONS,
        ("p4_linux_runtime_lib_t", "file"): executable,
        ("p4_linux_elf_interpreter_t", "file"): executable,
        ("p4_linux_console_ld_cache_native_config_t", "file"): read | {"map"},
        ("p4_linux_board_selinux_config_t", "file"): read,
        ("p4_linux_rootdir_t", "dir"): {"getattr", "search"},
        ("p4_linux_etc_dir_t", "dir"): {"getattr", "search"},
        ("device", "dir"): {"getattr", "search"},
        ("p4_linux_native_dev_root_t", "dir"): {"getattr", "search"},
        ("proc", "dir"): {"search"}, ("proc", "lnk_file"): {"read"},
        (ROLE, "dir"): {"search"}, (ROLE, "lnk_file"): {"read"},
        ("sysfs", "dir"): {"search"},
        ("selinuxfs", "dir"): {"search"},
        ("selinuxfs", "file"): SELINUXFS_READ,
        ("selinuxfs", "filesystem"): {"getattr"},
        ("p4_linux_usrmerge_link_t", "lnk_file"): {"getattr", "read"},
        ("p4_linux_timezone_link_t", "lnk_file"): {"getattr", "read"},
        ("init_t", "process"): {"sigchld"},
        (EXECUTOR, "process"): {"sigchld"},
        (ROLE, "process"): {"setfscreate"},
        (ROLE, "fd"): {"use"}, (EXECUTOR, "fd"): {"use"},
        (EXECUTOR, "unix_stream_socket"): {"getattr", "read", "write"},
        ("p4_linux_standardio_t", "chr_file"): {"getattr", "read", "write"},
        ("null_device", "chr_file"): {"getattr", "read", "write"},
    }


def _predecessor_aliases(here):
    rows = []
    if (here / "derive_native_tmpfiles_policy.py").exists():
        from derive_native_tmpfiles_policy import ALIASES as TMPFILES, DEVICE_VIEWS
        fixed = [
            {"source": "p4_linux_setup_exec_t", "target": "p4_linux_tmpfiles_exec_t", "class": "file"},
            {"source": "p4_linux_runtime_lib_t", "target": "p4_linux_tmpfiles_usr_config_t", "class": "file"},
            {"source": "p4_linux_native_config_t", "target": "p4_linux_tmpfiles_etc_config_t", "class": "file"},
            {"source": "p4_linux_rootdir_t", "target": "p4_linux_tmpfiles_config_dir_t", "class": "dir"},
            {"source": "p4_linux_rootdir_t", "target": "p4_linux_tmpfiles_runtime_dir_t", "class": "dir"},
            {"source": "p4_linux_native_data_t", "target": "p4_linux_tmpfiles_nologin_t", "class": "file"},
            {"source": "p4_linux_usrmerge_link_t", "target": "p4_linux_tmpfiles_shm_link_t", "class": "lnk_file"},
        ]
        device_views = [
            {"source": "device", "target": "p4_linux_tmpfiles_static_dir_t", "class": "dir"},
            {"source": "device", "target": "p4_linux_tmpfiles_static_node_t", "class": "chr_file"},
        ]
        if TMPFILES != fixed or DEVICE_VIEWS != device_views:
            raise ValueError("The fixed tmpfiles predecessor views changed")
        # The two device rows preserve ordinary class views only. They are not
        # aliases and do not equate the original relabel identities.
        rows.extend(TMPFILES)
        rows.extend(DEVICE_VIEWS)
    if (here / "derive_native_kmod_static_policy.py").exists():
        from derive_native_kmod_static_policy import ALIASES as KMOD
        fixed = [
            {"source": "p4_linux_rootdir_t", "target": "p4_linux_kmod_tmpfiles_dir_t", "class": "dir"},
            {"source": "p4_linux_native_data_t", "target": "p4_linux_kmod_static_nodes_t", "class": "file"},
        ]
        if KMOD != fixed:
            raise ValueError("The fixed kmod predecessor interface changed")
        rows.extend(KMOD)
    from derive_native_journal_catalog_policy import ALIASES as CATALOG
    fixed = [
        {"source": "p4_linux_rootdir_t", "target": "p4_linux_journal_catalog_dir_t", "class": "dir"},
        {"source": "p4_linux_native_data_t", "target": "p4_linux_journal_catalog_file_t", "class": "file"},
    ]
    if CATALOG != fixed:
        raise ValueError("The fixed catalog predecessor interface changed")
    return rows + CATALOG


def _successor_aliases(here):
    from derive_native_random_seed_policy import ALIASES as SEED, _successor_aliases as after_seed
    fixed = [
        {"source": "p4_linux_setup_exec_t", "target": "p4_linux_random_seed_exec_t", "class": "file"},
        {"source": "p4_linux_native_data_t", "target": "p4_linux_random_seed_file_t", "class": "file"},
    ]
    if SEED != fixed:
        raise ValueError("The fixed seed successor interface changed")
    rows = SEED + after_seed(here)
    keys = [(r["target"], r["class"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("Overlapping update-done successor aliases")
    return rows


def _present(rows, types):
    # A standalone proof may precede integration of these exact declared
    # components. Normal production includes all fixed source components.
    # Report absent fixed targets; never invent a view for an unknown type.
    return [row for row in rows if row["target"] in types]


def _role_map(here, types, final):
    result = {key: set(names) for key, names in _base_role().items()}
    rows = _present(_predecessor_aliases(here), types)
    if final:
        rows += _present(_successor_aliases(here), types)
    for row in rows:
        source, target = (row["source"], row["class"]), (row["target"], row["class"])
        if source in result:
            result.setdefault(target, set()).update(result[source])
    return result


def _check_role(raw, here, final):
    wanted = _role_map(here, raw.types, final)
    actual = raw.actor(ROLE)
    if actual != wanted:
        keys = actual.keys() | wanted.keys()
        delta = [[*key, sorted(actual.get(key, set())), sorted(wanted.get(key, set()))]
                 for key in sorted(keys) if actual.get(key, set()) != wanted.get(key, set())]
        raise ValueError("Update-done complete raw authority changed: " + repr(delta))
    # Independent checks keep the label reader separate from the AVC clients.
    if actual.get(("kernel", "security"), set()):
        raise ValueError("Update-done acquired a security-server query")
    if actual.get(("selinuxfs", "file"), set()) != SELINUXFS_READ:
        raise ValueError("Update-done changed the complete read-only status vector")
    if any(names for (target, cls), names in actual.items() if cls.startswith("netlink_")):
        raise ValueError("Update-done acquired a netlink fallback")
    inbound = {
        ("init_t", "process"): {"getattr", "signull", "signal", "sigkill", "sigstop"},
        (EXECUTOR, "process"): {"transition", "siginh", "rlimitinh"},
        (EXECUTOR, "process2"): {"nnp_transition"},
        (ROLE, "process"): {"setfscreate"},
        (ROLE, "dir"): {"search"}, (ROLE, "lnk_file"): {"read"}, (ROLE, "fd"): {"use"},
    }
    if raw.incoming(ROLE) != inbound:
        raise ValueError("Update-done incoming caller/own-process boundary changed")
    for form in raw.xperms:
        if len(form) != 4 or form[1] not in raw.members:
            raise ValueError("Malformed update-done extended permission form")
        if raw.members[form[1]] & NEW_TYPES:
            raise ValueError("Update-done acquired an extended ioctl filter")
    for target in (VAR, ETC_FILE, VAR_FILE):
        if raw.actor(target) != {("labeledfs", "filesystem"): {"associate"}}:
            raise ValueError("Update-done output type acquired unrelated authority")
    if raw.actor(ENTRY):
        raise ValueError("Update-done entry type acquired outgoing authority")
    return wanted


def _rows(table):
    return [[actor, cls, sorted(names)] for (actor, cls), names in sorted(table.items())]


def _table(rows):
    result = {}
    for actor, cls, names in rows:
        if (actor, cls) in result or names != sorted(set(names)):
            raise ValueError("Repeated or noncanonical update-done vector")
        result[(actor, cls)] = set(names)
    return result


def _effective_role(policy, lines, table, classes):
    result = []
    for (target, cls), names in sorted(table.items()):
        role = _context_role(lines, target)
        for a in LEVELS:
            for b in LEVELS:
                got = policy.context_av(_context("system_r", ROLE, a),
                    _context(role, target, b), cls, classes[cls])
                if a == b == "s0" and got != _bits(policy, cls, names):
                    raise ValueError("The normal s0 update-done operation is not effective: " + target + " " + cls)
                result.append([target, cls, a, b, got])
    return result


def _constraints(lines, raw):
    selected = sorted(line for line in lines if line.startswith(CONSTRAINTS))
    if (selected.count(DIRECTORY_RELABEL_GUARD) != 1
            or hashlib.sha256(DIRECTORY_RELABEL_GUARD.encode()).hexdigest() != DIRECTORY_RELABEL_GUARD_SHA256):
        raise ValueError("The original complete directory relabel guard changed")
    for line in selected:
        if line == DIRECTORY_RELABEL_GUARD:
            # Preserve the complete identity predicate. Only this fixed actor
            # takes its restricted branch, and neither old/new selected dir
            # admits either relabel gate. All other actors take the neq branch.
            hardware = raw.actor("p4_linux_hardware_label_t")
            for label in ("p4_linux_rootdir_t", VAR):
                if hardware.get((label, "dir"), set()) & {"relabelfrom", "relabelto"}:
                    raise ValueError("Update-done exposed the directory identity-guard branch")
            continue
        form = parse_expression(line)
        if form[0] not in ("validatetrans", "mlsvalidatetrans"):
            continue
        for row in ALIASES:
            if row["class"] != form[1]:
                continue
            def substitute(expr, variable, label):
                if not isinstance(expr, list):
                    return expr
                if len(expr) == 3 and expr[0] in ("eq", "neq") and variable in expr[1:]:
                    other = expr[2] if expr[1] == variable else expr[1]
                    if not isinstance(other, str) or other in ("t1", "t2", "t3") or other not in raw.members:
                        raise ValueError("Unmodeled update-done relabel identity predicate")
                    answer = label in raw.members[other]
                    return answer if expr[0] == "eq" else not answer
                return [substitute(child, variable, label) for child in expr]
            for variable in ("t1", "t2"):
                if substitute(form[2], variable, row["source"]) != substitute(form[2], variable, row["target"]):
                    raise ValueError("Update-done alias changed a complete relabel predicate")
    return selected


def _selected_transitions(lines):
    def atoms(value):
        if isinstance(value, str):
            return {value}
        return set().union(*(atoms(child) for child in value)) if value else set()
    return sorted(line for line in lines if line.startswith(TRANSITIONS)
                  and atoms(parse_expression(line)) & NEW_TYPES)


def _metadata_effective(policy, raw, actors):
    """The six fixed off-class metadata views retain all 16 category pairs."""
    roles = {actor: role for role, actor in actors}
    if len(roles) != len(actors):
        raise ValueError("Ambiguous update-done metadata actor roles")
    rows = []
    for (target, actor, cls), names in sorted(NORMAL_METADATA_PREIMAGE.items()):
        if actor not in roles or cls != "dir":
            raise ValueError("Unknown update-done metadata reader")
        alias = next(row for row in ALIASES if row["target"] == target)
        old = alias["source"]
        for label in (old, target):
            if raw.incoming(label).get((actor, cls), set()) != names:
                raise ValueError("Update-done metadata preimage changed its complete raw vector")
        for a in LEVELS:
            for b in LEVELS:
                context = _context(roles[actor], actor, a)
                before = policy.context_av(context, _context("object_r", old, b),
                                           cls, raw.classes[cls])
                after = policy.context_av(context, _context("object_r", target, b),
                                          cls, raw.classes[cls])
                if before != after:
                    raise ValueError("Update-done changed an off-class metadata category decision")
                if a == b == "s0" and before != _bits(policy, cls, names):
                    raise ValueError("Update-done metadata preimage is not the fixed normal s0 vector")
                rows.append([roles[actor], actor, old, target, cls, a, b, before])
    if len(rows) != 6 * len(LEVELS) ** 2:
        raise ValueError("Incomplete update-done metadata category matrix")
    return rows


def derive(library, baseline, exported, here, output, export):
    contract(here)
    expected = derive_preserved_aliases(library, baseline, exported, ALIASES,
        output, export, prefix="p4_update_done_preserved", isolated_roles={ROLE},
        extra_permissions={}, preamble=(
            "; Preserve the original setup/rootdir/config/data view of every other actor.",
            "; Replace only the normal executor's copied update-done entry transition."))
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    raw = RawPolicy(lines)
    base = _check_role(raw, here, False)
    expected["role_before"] = _effective_role(policy, lines, base, raw.classes)
    expected["complete_constraints"] = _constraints(lines, raw)
    expected["normal_metadata_effective"] = _metadata_effective(policy, raw, expected["actors"])
    if (lines.count(OLD_ENTRY) != 1 or lines.count(SELECTED_ENTRY) != 1
            or expected["transitions"].count(COPIED_ENTRY) != 1):
        raise ValueError("The normal update-done entry replacement is absent")
    generated = output.read_text().splitlines()
    if generated.count(COPIED_ENTRY) != 1:
        raise ValueError("Ambiguous copied setup transition")
    generated.remove(COPIED_ENTRY)
    expected["transitions"].remove(COPIED_ENTRY)
    output.write_text("\n".join(generated) + "\n")
    expected["derived_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    expected["entry_replacement"] = [OLD_ENTRY, COPIED_ENTRY, SELECTED_ENTRY]
    expected["selected_transitions"] = sorted(set(expected["transitions"]) | {SELECTED_ENTRY})
    source_raw, final_targets, raw_rows, effective = {}, {}, [], []
    actors = {actor for _, actor in expected["actors"]}
    for row in ALIASES:
        old = raw.incoming(row["source"])
        source_raw[row["source"]] = _rows(old)
        wanted = {key: names for key, names in old.items()
                  if key[1] == row["class"] and key[0] != ROLE}
        wanted[(ROLE, row["class"])] = base[(row["target"], row["class"])]
        for (target, actor, cls), names in NORMAL_METADATA_PREIMAGE.items():
            if target != row["target"]:
                continue
            if old.get((actor, cls), set()) != names:
                raise ValueError("Update-done changed the fixed metadata source preimage")
            wanted[(actor, cls)] = names
        final_targets[row["target"]] = _rows(wanted)
        for key, names in raw.incoming(row["target"]).items():
            if not names.issubset(wanted.get(key, set())):
                raise ValueError("Update-done alias has an unapproved actor/class preimage")
        for role, actor in expected["actors"]:
            before = old.get((actor, row["class"]), set())
            got = policy.context_av(_context(role, actor),
                _context("object_r", row["source"]), row["class"], raw.classes[row["class"]])
            if got != _bits(policy, row["class"], before):
                raise ValueError("Update-done source raw vector cannot be reconstructed at s0")
            raw_rows.append([role, actor, row["source"], row["target"], row["class"], sorted(before)])
            for a in LEVELS:
                for b in LEVELS:
                    got = policy.context_av(_context(role, actor, a),
                        _context("object_r", row["source"], b), row["class"], raw.classes[row["class"]])
                    effective.append([role, actor, row["source"], row["target"], row["class"], a, b, got])
        if any(actor not in actors and actor != ROLE for actor, cls in wanted):
            raise ValueError("Update-done has an unmodeled non-actor permission")
    expected["complete_old_source_raw"] = source_raw
    expected["complete_new_target_raw"] = final_targets
    expected["complete_alias_raw"] = raw_rows
    expected["complete_alias_effective"] = effective
    expected["predecessor_aliases"] = _predecessor_aliases(here)
    expected["successor_aliases"] = _successor_aliases(here)
    expected["contract_sha256"] = CONTRACT_PIN[1]
    return expected


def verify(library, binary, exported, here, expected, export):
    value = contract(here)
    if (expected["contract_sha256"] != CONTRACT_PIN[1]
            or expected["entry_replacement"] != [OLD_ENTRY, COPIED_ENTRY, SELECTED_ENTRY]
            or expected["predecessor_aliases"] != _predecessor_aliases(here)
            or expected["successor_aliases"] != _successor_aliases(here)):
        raise ValueError("Update-done source/derivation lineage changed")
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    raw = RawPolicy(lines)
    if _constraints(lines, raw) != expected["complete_constraints"]:
        raise ValueError("Update-done changed complete ordinary/MLS/relabel constraints")
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    if (_selected_transitions(lines) != expected["selected_transitions"]
            or OLD_ENTRY not in lines or COPIED_ENTRY in lines):
        raise ValueError("Update-done changed an entry or file transition")
    for label, rows in expected["complete_old_source_raw"].items():
        if raw.incoming(label) != _table(rows):
            raise ValueError("Update-done changed a complete old source class vector")
    for label, rows in expected["complete_new_target_raw"].items():
        if raw.incoming(label) != _table(rows):
            raise ValueError("Update-done changed a complete new target class vector")
    incoming = {label: raw.incoming(label) for row in ALIASES
                for label in (row["source"], row["target"])}
    for role, actor, old, new, cls, names in expected["complete_alias_raw"]:
        if any(incoming[label].get((actor, cls), set()) != set(names) for label in (old, new)):
            raise ValueError("Update-done changed a complete old actor raw vector")
    for role, actor, old, new, cls, a, b, wanted in expected["complete_alias_effective"]:
        for target in (old, new):
            got = policy.context_av(_context(role, actor, a),
                _context("object_r", target, b), cls, raw.classes[cls])
            if got != wanted:
                raise ValueError("Update-done changed an old constrained alias vector")
        checks.append([role, actor, old, new, cls, a, b, wanted])
    final = _check_role(raw, here, True)
    own = _effective_role(policy, lines, final, raw.classes)
    before = {(target, cls, a, b): mask for target, cls, a, b, mask in expected["role_before"]}
    wanted = dict(before)
    for row in _present(expected["successor_aliases"], raw.types):
        for a in LEVELS:
            for b in LEVELS:
                key = (row["source"], row["class"], a, b)
                new = (row["target"], row["class"], a, b)
                if key in wanted and new not in before:
                    wanted[new] = wanted.get(new, 0) | wanted[key]
    if {(target, cls, a, b): mask for target, cls, a, b, mask in own} != wanted:
        raise ValueError("Update-done successor changed a complete constrained role vector")
    metadata = _metadata_effective(policy, raw, expected["actors"])
    if metadata != expected["normal_metadata_effective"]:
        raise ValueError("Update-done metadata category preimage changed after derivation")
    checks.extend(metadata)
    checks.extend(own)
    return {
        "schema": "droidloom.native-update-done-policy-proof.v1",
        "source": {"bytes": CONTRACT_PIN[0], "sha256": CONTRACT_PIN[1], "contents": value},
        "source_bound_readback_required": True,
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_raw_vectors": 2 * len(expected["complete_alias_raw"]),
        "preserved_effective_vectors": 2 * len(expected["complete_alias_effective"]),
        "complete_new_target_raw_class_object_pairs": 4 * len(raw.types) * len(raw.classes),
        "role_raw_class_object_pairs": len(raw.types) * len(raw.classes),
        "role_raw_nonzero_vectors": [[*key, sorted(names)] for key, names in sorted(final.items())],
        "role_effective_vectors": len(own), "category_pairs": len(LEVELS) ** 2,
        "metadata_effective_vectors": len(metadata),
        "metadata_source_and_target_comparisons": 2 * len(metadata),
        "normal_metadata_preimage": [[target, actor, cls, sorted(names)]
            for (target, actor, cls), names in sorted(NORMAL_METADATA_PREIMAGE.items())],
        "entry_transition_replacement": expected["entry_replacement"],
        "predecessor_aliases": expected["predecessor_aliases"],
        "successor_aliases": expected["successor_aliases"],
        "absent_fixed_alias_targets": sorted({row["target"] for row in expected["predecessor_aliases"] + expected["successor_aliases"]} - raw.types),
        "parent_permissions": sorted(PARENT_PERMISSIONS),
        "marker_file_permissions": sorted(FILE_PERMISSIONS),
        "normal_create_label": "self process:setfscreate; native LSM attribute API",
        "security_permissions": [], "netlink_permissions": [],
        "selinuxfs_file_permissions": sorted(SELINUXFS_READ),
        "directory_creation": False, "generic_parent_write": False,
        "fsync_added": False, "legacy_procattr_write": False,
        "file_contexts": verify_file_contexts(here, exported.parent),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "kernel_runtime_qualified": False, "production_qualified": False,
    }


def verify_file_contexts(here, work):
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    data = b"".join((here / name).read_bytes() for name in names)
    path = work / "update-done-file-contexts"
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Update-done matcher input changed")
    else:
        with path.open("xb") as f:
            f.write(data)
    class Option(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("value", ctypes.c_char_p)]
    lib = ctypes.CDLL("libselinux.so.1", use_errno=True)
    lib.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(Option), ctypes.c_uint]
    lib.selabel_open.restype = ctypes.c_void_p
    lib.selabel_lookup_raw.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p), ctypes.c_char_p, ctypes.c_int]
    lib.selabel_lookup_raw.restype = ctypes.c_int
    lib.selabel_close.argtypes = [ctypes.c_void_p]
    lib.freecon.argtypes = [ctypes.c_void_p]
    handle = lib.selabel_open(0, ctypes.byref(Option(3, str(path).encode())), 1)
    if not handle:
        raise ValueError("Normal class-aware update-done contexts cannot be opened")
    cases = [
        ("/usr/lib/systemd/systemd-update-done", stat.S_IFREG, ENTRY),
        ("/etc", stat.S_IFDIR, ETC), ("/var", stat.S_IFDIR, VAR),
        ("/usr", stat.S_IFDIR, "p4_linux_rootdir_t"),
        ("/usr/lib/systemd/systemd-user-sessions", stat.S_IFREG, "p4_linux_setup_exec_t"),
    ]
    for parent, target in (("/etc", ETC_FILE), ("/var", VAR_FILE)):
        files = [parent + "/.updated", parent + "/.#.updated0000000000000000",
                 parent + "/.#.updated0123456789abcdef"]
        cases += [(name, stat.S_IFREG, target) for name in files]
        cases += [(name, kind, None) for name in files for kind in (stat.S_IFDIR, stat.S_IFLNK)]
        cases += [(parent + suffix, stat.S_IFREG, None) for suffix in (
            "/.updated-old", "/.updated/child", "/.#.updated0123456789abcde",
            "/.#.updated0123456789abcdef0", "/.#.updated0123456789abcdeg",
            "/.#.updated0123456789ABCDEF", "/.#other0123456789abcdef")]
    cases += [("/var", kind, None) for kind in (stat.S_IFREG, stat.S_IFLNK)]
    cases += [("/var" + suffix, stat.S_IFDIR, None) for suffix in ("-old", "/child")]
    cases += [("/usr/lib/systemd/systemd-update-done", kind, None) for kind in (stat.S_IFDIR, stat.S_IFLNK)]
    cases += [("/usr/lib/systemd/systemd-update-done" + suffix, stat.S_IFREG, None) for suffix in ("-old", ".tmp", "/child")]
    rows = []
    try:
        for name, mode, wanted in cases:
            out = ctypes.c_char_p()
            rc = lib.selabel_lookup_raw(handle, ctypes.byref(out), name.encode(), mode)
            context = None
            if rc == 0:
                try:
                    context = out.value.decode()
                finally:
                    lib.freecon(out)
            elif ctypes.get_errno() != 2:
                raise ValueError("Update-done class-aware lookup failed")
            actual = context.split(":")[2] if context else None
            if wanted is not None and actual != wanted or wanted is None and actual in NEW_TYPES:
                raise ValueError("Update-done exact/adjacent path boundary changed: " + name)
            rows.append([name, mode, context])
    finally:
        lib.selabel_close(handle)
    return {"cases": len(rows), "rows": rows, "composed_sha256": hashlib.sha256(data).hexdigest()}
