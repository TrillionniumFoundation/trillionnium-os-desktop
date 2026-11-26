"""Admit the unchanged normal random-seed program and preserve its old labels.

This producer creates policy text only. Actual package/source readback is a
separate mandatory normal-controller input. No seed contents are collected.
"""
import ctypes
import hashlib
import json
import re
import stat
from collections import defaultdict

from derive_native_uevent_policy import ContextPolicy, LEVELS
from derive_preserved_alias_policy import (
    _classes, _context, _roles, derive_preserved_aliases,
    verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression

ROLE = "p4_linux_random_seed_t"
ENTRY = "p4_linux_random_seed_exec_t"
FILE = "p4_linux_random_seed_file_t"
NEW_TYPES = {ROLE, ENTRY, FILE}
PARENT = "p4_linux_systemd_state_parent_t"
EXECUTOR = "p4_linux_service_executor_t"
ALIASES = [
    {"source": "p4_linux_setup_exec_t", "target": ENTRY, "class": "file"},
    {"source": "p4_linux_native_data_t", "target": FILE, "class": "file"},
]
CONTRACT_PIN = (5633, "adc71dfc853b03b5bab9bdea755ac5c0a1a8eda4848c1e70b2958adcbe92d228")
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
OLD_ENTRY = "(typetransition " + EXECUTOR + " p4_linux_setup_exec_t process p4_linux_setup_t)"
COPIED_ENTRY = "(typetransition " + EXECUTOR + " " + ENTRY + " process p4_linux_setup_t)"
SELECTED_ENTRY = "(typetransition " + EXECUTOR + " " + ENTRY + " process " + ROLE + ")"
SEED_CREATION = '(typetransition ' + ROLE + ' ' + PARENT + ' file "random-seed" ' + FILE + ')'


def contract(here):
    raw = (here / "native-random-seed-source.json").read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != CONTRACT_PIN:
        raise ValueError("The fixed normal random-seed source contract changed")
    value = json.loads(raw)
    if (value["schema"] != "droidloom.native-random-seed-source.v1"
            or value["aliases"] != ALIASES
            or value["normal_default_credit"] != "environment-unset-NO"
            or value["unit_environment_overridden"] is not False
            or value["entropy_ioctls"] is not False
            or value["sys_admin"] is not False
            or value["kernel_runtime_qualified"] is not False
            or value["cross_boot_credit_qualified"] is not False
            or value["normal_fallbacks"] != {
                "random_pool_size": "proc-read-failure-uses-normal-minimum",
                "log_setup": "normal-journal-or-kmsg-failure-falls-back-to-inherited-stderr",
                "extra_proc_sys_read": False, "new_logging_socket": False,
                "kmsg_write": False}):
        raise ValueError("The random-seed normal/default boundary changed")
    return value


class RawPolicy:
    """Read the complete unconditional export without Cartesian AV queries.

    Binary CIL exports attribute bitmaps as concrete type lists. Reject a source
    expression, conditional or typebounds instead of guessing its semantics.
    """
    def __init__(self, lines):
        text = "\n".join(lines)
        if re.search(r"\((?:booleanif|tunableif|typebounds)\b", text):
            raise ValueError("Random-seed needs unconditional unbounded raw TE")
        self.types = set(re.findall(r"^\(type (\w+)\)$", text, re.M))
        attrs = set(re.findall(r"^\(typeattribute (\w+)\)$", text, re.M))
        self.members = {name: {name} for name in self.types}
        self.members.update({name: set() for name in attrs})
        self.classes = _classes(text)
        assigned = set()
        self.rules = []
        self.xperms = []
        for line in lines:
            if line.startswith("(typeattributeset "):
                form = parse_expression(line)
                if (len(form) != 3 or form[1] not in attrs
                        or form[1] in assigned or not isinstance(form[2], list)
                        or any(not isinstance(t, str) or t not in self.types for t in form[2])
                        or len(form[2]) != len(set(form[2]))):
                    raise ValueError("Non-concrete or repeated binary attribute bitmap")
                assigned.add(form[1])
                self.members[form[1]] = set(form[2])
            elif line.startswith("(allow "):
                form = parse_expression(line)
                if (len(form) != 4 or not isinstance(form[3], list)
                        or len(form[3]) != 2):
                    raise ValueError("Malformed complete raw allow")
                source, target, (cls, names) = form[1:]
                if (source not in self.members or target not in self.members and target != "self"
                        or cls not in self.classes or not isinstance(names, list)
                        or not set(names).issubset(self.classes[cls])
                        or len(names) != len(set(names))):
                    raise ValueError("Unknown raw allow subject, object or permission")
                self.rules.append((source, target, cls, set(names)))
            elif line.startswith("(allowx "):
                self.xperms.append(parse_expression(line))
        if len(self.rules) != text.count("(allow "):
            raise ValueError("Incomplete raw TE export")

    def actor(self, actor):
        result = defaultdict(set)
        for source, target, cls, names in self.rules:
            if actor not in self.members[source]:
                continue
            for concrete in ({actor} if target == "self" else self.members[target]):
                result[(concrete, cls)].update(names)
        return dict(result)

    def incoming(self, target):
        result = defaultdict(set)
        for source, obj, cls, names in self.rules:
            if obj == "self":
                if target in self.members[source]:
                    result[(target, cls)].update(names)
            elif target in self.members[obj]:
                for actor in self.members[source]:
                    result[(actor, cls)].update(names)
        return dict(result)

    def selected(self, actors, targets, cls):
        actors = set(actors)
        targets = set(targets)
        result = defaultdict(set)
        for source, obj, rule_class, names in self.rules:
            if rule_class != cls:
                continue
            sources = self.members[source] & actors
            if obj == "self":
                for actor in sources & targets:
                    result[(actor, actor)].update(names)
            else:
                selected = self.members[obj] & targets
                for actor in sources:
                    for target in selected:
                        result[(actor, target)].update(names)
        return result


def _bits(policy, cls, names):
    return sum(policy.permissions(cls, sorted(names))[1].values()) if names else 0


def _base_role():
    read = {"getattr", "open", "read"}
    executable = read | {"execute", "map"}
    return {
        (ENTRY, "file"): executable | {"entrypoint"},
        (FILE, "file"): read | {"write", "create", "setattr"},
        ("p4_linux_runtime_lib_t", "file"): executable,
        ("p4_linux_elf_interpreter_t", "file"): executable,
        ("p4_linux_console_ld_cache_native_config_t", "file"): read | {"map"},
        ("p4_linux_machine_id_t", "file"): read,
        ("p4_linux_rootdir_t", "dir"): {"getattr", "search"},
        ("p4_linux_etc_dir_t", "dir"): {"getattr", "search"},
        (PARENT, "dir"): {"getattr", "search", "open", "read", "write", "add_name"},
        ("device", "dir"): {"getattr", "search"},
        ("p4_linux_native_dev_root_t", "dir"): {"getattr", "search"},
        ("proc", "dir"): {"search"},
        ("proc", "lnk_file"): {"read"},
        (ROLE, "dir"): {"search"},
        (ROLE, "lnk_file"): {"read"},
        ("p4_linux_usrmerge_link_t", "lnk_file"): {"getattr", "read"},
        ("p4_linux_timezone_link_t", "lnk_file"): {"getattr", "read"},
        ("init_t", "process"): {"sigchld"},
        (EXECUTOR, "process"): {"sigchld"},
        (ROLE, "fd"): {"use"},
        (EXECUTOR, "fd"): {"use"},
        (EXECUTOR, "unix_stream_socket"): {"getattr", "read", "write"},
        ("p4_linux_standardio_t", "chr_file"): {"getattr", "read", "write"},
        ("null_device", "chr_file"): {"getattr", "read", "write"},
        ("random_device", "chr_file"): {"open", "read", "write"},
    }


def _predecessor_aliases(here):
    # Each installed predecessor must retain this actor's exact original
    # source view. No catalog or static-nodes file access is inherited.
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
            raise ValueError("The fixed kmod predecessor alias roster changed")
        rows.extend(KMOD)
    if (here / "derive_native_journal_catalog_policy.py").exists():
        from derive_native_journal_catalog_policy import ALIASES as CATALOG
        fixed = [
            {"source": "p4_linux_rootdir_t", "target": "p4_linux_journal_catalog_dir_t", "class": "dir"},
            {"source": "p4_linux_native_data_t", "target": "p4_linux_journal_catalog_file_t", "class": "file"},
        ]
        if CATALOG != fixed:
            raise ValueError("The fixed catalog predecessor alias roster changed")
        rows.extend(CATALOG)
    if (here / "derive_native_update_done_policy.py").exists():
        from derive_native_update_done_policy import ALIASES as UPDATE_DONE
        fixed = [
            {"source": "p4_linux_setup_exec_t", "target": "p4_linux_update_done_exec_t", "class": "file"},
            {"source": "p4_linux_rootdir_t", "target": "p4_linux_update_done_var_dir_t", "class": "dir"},
            {"source": "p4_linux_native_config_t", "target": "p4_linux_update_done_etc_file_t", "class": "file"},
            {"source": "p4_linux_native_data_t", "target": "p4_linux_update_done_var_file_t", "class": "file"},
        ]
        if UPDATE_DONE != fixed:
            raise ValueError("The fixed update-done predecessor alias roster changed")
        rows.extend(UPDATE_DONE)
    return rows


def _successor_aliases(here):
    from derive_native_console_policy import contract as console_contract
    from derive_native_remount_policy import ALIASES as REMOUNT
    from derive_native_logind_state_policy import ALIASES as LOGIND
    from derive_native_netplan_policy import ALIASES as NETPLAN
    from derive_native_sysusers_policy import ALIASES as SYSUSERS
    rows = []
    # This component is also reviewed alone before the timesync commit is
    # integrated. An installed timesync producer must match this exact roster.
    if (here / "derive_native_timesync_policy.py").exists():
        from derive_native_timesync_policy import ALIASES as TIMESYNC
        fixed = [
            ("p4_linux_runtime_lib_t", "p4_linux_timesyncd_exec_t", "file"),
            ("p4_linux_rootdir_t", "p4_linux_timesyncd_run_t", "dir"),
            ("p4_linux_native_data_t", "p4_linux_timesyncd_run_t", "file"),
            ("p4_linux_rootdir_t", "p4_linux_timesyncd_state_t", "dir"),
            ("p4_linux_native_data_t", "p4_linux_timesyncd_state_t", "file"),
            ("p4_linux_native_config_t", "p4_linux_timesyncd_config_t", "file"),
            ("p4_linux_native_config_t", "p4_linux_timesyncd_nsswitch_t", "file"),
            ("p4_linux_rootdir_t", "p4_linux_timesyncd_netif_t", "dir"),
            ("p4_linux_native_data_t", "p4_linux_timesyncd_netif_t", "file"),
        ]
        if {tuple(row[k] for k in ("source", "target", "class")) for row in TIMESYNC} != set(fixed) or len(TIMESYNC) != len(fixed):
            raise ValueError("The fixed timesync successor alias roster changed")
        rows.extend(TIMESYNC)
    if (here / "derive_native_ldconfig_policy.py").exists():
        from derive_native_ldconfig_policy import ALIASES as LDCONFIG
        fixed = [
            ("p4_linux_setup_exec_t", "p4_linux_ldconfig_exec_t", "file"),
            ("p4_linux_native_config_t", "p4_linux_ldconfig_config_t", "file"),
            ("p4_linux_rootdir_t", "p4_linux_ldconfig_config_dir_t", "dir"),
            ("p4_linux_rootdir_t", "p4_linux_ldconfig_aux_dir_t", "dir"),
            ("p4_linux_native_data_t", "p4_linux_ldconfig_aux_t", "file"),
        ]
        if {tuple(row[k] for k in ("source", "target", "class")) for row in LDCONFIG} != set(fixed) or len(LDCONFIG) != len(fixed):
            raise ValueError("The fixed ldconfig successor alias roster changed")
        rows.extend(LDCONFIG)
    rows.extend(console_contract(here)["aliases"])
    rows.extend(REMOUNT)
    rows.extend(LOGIND)
    rows.extend(NETPLAN)
    rows.extend(SYSUSERS)
    seen = set()
    for row in rows:
        key = (row["target"], row["class"])
        if key in seen or set(row) != {"source", "target", "class"}:
            raise ValueError("Overlapping random-seed successor aliases")
        seen.add(key)
    return rows


def _role_map(here, final):
    result = _base_role()
    for row in _predecessor_aliases(here):
        source = (row["source"], row["class"])
        target = (row["target"], row["class"])
        if source in result:
            result.setdefault(target, set()).update(result[source])
    if final:
        for row in _successor_aliases(here):
            source = (row["source"], row["class"])
            target = (row["target"], row["class"])
            # Explicit seed parent/cache access remains subject to its own
            # complete proof. Successors preserve the original source vector.
            if source in result:
                result.setdefault(target, set()).update(result[source])
    return result


def _context_role(lines, target):
    return "system_r" if "(roletype system_r " + target + ")" in lines else "r" if "(roletype r " + target + ")" in lines else "object_r"


def _effective_role(policy, lines, table, classes):
    rows = []
    for target, cls in sorted(table):
        target_role = _context_role(lines, target)
        for source_level in LEVELS:
            for target_level in LEVELS:
                value = policy.context_av(_context("system_r", ROLE, source_level),
                    _context(target_role, target, target_level), cls, classes[cls])
                if source_level == target_level == "s0" and value != _bits(policy, cls, table[(target, cls)]):
                    raise ValueError("Normal s0 random-seed operation is not effective: " + target + " " + cls)
                rows.append([target, cls, source_level, target_level, value])
    return rows


def _check_role(raw, here, final):
    wanted = _role_map(here, final)
    actual = raw.actor(ROLE)
    if actual != wanted:
        keys = set(actual) | set(wanted)
        delta = [[*key, sorted(actual.get(key, set())), sorted(wanted.get(key, set()))]
                 for key in sorted(keys) if actual.get(key, set()) != wanted.get(key, set())]
        raise ValueError("Random-seed complete raw role boundary changed: " + repr(delta))
    inbound = {
        ("init_t", "process"): {"getattr", "signull", "signal", "sigkill", "sigstop"},
        (EXECUTOR, "process"): {"transition", "siginh", "rlimitinh"},
        (EXECUTOR, "process2"): {"nnp_transition"},
        (ROLE, "dir"): {"search"}, (ROLE, "lnk_file"): {"read"},
        (ROLE, "fd"): {"use"},
    }
    if raw.incoming(ROLE) != inbound:
        raise ValueError("Random-seed incoming caller/proc boundary changed: " + repr(raw.incoming(ROLE)))
    for form in raw.xperms:
        if len(form) != 4 or form[1] not in raw.members:
            raise ValueError("Malformed extended permission rule")
        if ROLE in raw.members[form[1]]:
            raise ValueError("Random-seed acquired an extended ioctl filter")
    associated = raw.actor(FILE)
    if associated != {("labeledfs", "filesystem"): {"associate"}}:
        raise ValueError("Random-seed output label acquired unrelated authority")
    return wanted


def _constraints(lines, raw):
    selected = sorted(line for line in lines if line.startswith(CONSTRAINTS))
    for line in selected:
        form = parse_expression(line)
        if form[0] not in ("validatetrans", "mlsvalidatetrans") or form[1] != "file":
            continue
        def target_atoms(expr, target):
            if not isinstance(expr, list):
                return expr
            if len(expr) == 3 and expr[0] in ("eq", "neq") and "t2" in expr[1:]:
                other = expr[2] if expr[1] == "t2" else expr[1]
                if not isinstance(other, str) or other in ("t1", "t2", "t3") or other not in raw.members:
                    raise ValueError("Unmodeled random-seed relabel type-identity predicate")
                answer = target in raw.members[other]
                return answer if expr[0] == "eq" else not answer
            return [target_atoms(child, target) for child in expr]
        for row in ALIASES:
            if target_atoms(form[2], row["source"]) != target_atoms(form[2], row["target"]):
                raise ValueError("Random-seed alias changed a complete relabel target predicate")
    return selected


def _selected_transitions(lines):
    selected = {ROLE, ENTRY, FILE}
    return sorted(line for line in lines if line.startswith(TRANSITIONS)
                  and any(isinstance(token, str) and token in selected
                          for token in parse_expression(line)[1:]))


def derive(library, baseline, exported, here, output, export):
    contract(here)
    expected = derive_preserved_aliases(library, baseline, exported, ALIASES,
        output, export, prefix="p4_seed_preserved", isolated_roles={ROLE},
        extra_permissions={}, preamble=(
            "; Preserve both original labels for every other concrete actor.",
            "; Replace only the normal executor's copied setup entry transition."))
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    raw = RawPolicy(lines)
    base = _check_role(raw, here, False)
    expected["role_before"] = _effective_role(policy, lines, base, raw.classes)
    expected["complete_constraints"] = _constraints(lines, raw)
    if (lines.count(OLD_ENTRY) != 1 or lines.count(SELECTED_ENTRY) != 1
            or lines.count(SEED_CREATION) != 1
            or expected["transitions"].count(COPIED_ENTRY) != 1):
        raise ValueError("The sole exact normal seed entry replacement is absent")
    generated = output.read_text().splitlines()
    if generated.count(COPIED_ENTRY) != 1:
        raise ValueError("Ambiguous copied setup transition")
    generated.remove(COPIED_ENTRY)
    expected["transitions"].remove(COPIED_ENTRY)
    output.write_text("\n".join(generated) + "\n")
    expected["derived_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    expected["entry_replacement"] = [OLD_ENTRY, COPIED_ENTRY, SELECTED_ENTRY]
    expected["selected_transitions"] = sorted(set(expected["transitions"]) | {SELECTED_ENTRY, SEED_CREATION})
    actor_names = {actor for _, actor in expected["actors"]}
    source_types = {row["source"] for row in ALIASES}
    targets = source_types | {row["target"] for row in ALIASES}
    pairs = raw.selected(actor_names, targets, "file")
    raw_rows = []
    effective = []
    for role, actor in expected["actors"]:
        for row in ALIASES:
            before = pairs[(actor, row["source"])]
            preimage = pairs[(actor, row["target"])]
            if not preimage.issubset(before):
                raise ValueError("Seed alias has an unrelated explicit preimage")
            at_s0 = policy.context_av(_context(role, actor),
                _context("object_r", row["source"]), "file", raw.classes["file"])
            if at_s0 != _bits(policy, "file", before):
                raise ValueError("Seed alias raw TE cannot be reconstructed from its unchanged s0 vector")
            raw_rows.append([role, actor, row["source"], row["target"], sorted(before)])
            for a in LEVELS:
                for b in LEVELS:
                    value = policy.context_av(_context(role, actor, a),
                        _context("object_r", row["source"], b), "file", raw.classes["file"])
                    effective.append([role, actor, row["source"], row["target"], a, b, value])
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
        raise ValueError("Random-seed derivation/source lineage changed")
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    raw = RawPolicy(lines)
    if _constraints(lines, raw) != expected["complete_constraints"]:
        raise ValueError("Random-seed changed complete ordinary/MLS/relabel constraints")
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    if _selected_transitions(lines) != expected["selected_transitions"] or OLD_ENTRY not in lines or COPIED_ENTRY in lines:
        raise ValueError("Random-seed selected entry or named file transition changed")
    actors = {actor for _, actor in expected["actors"]}
    targets = {row[side] for row in ALIASES for side in ("source", "target")}
    pairs = raw.selected(actors, targets, "file")
    for role, actor, old, new, names in expected["complete_alias_raw"]:
        if pairs[(actor, old)] != set(names) or pairs[(actor, new)] != set(names):
            raise ValueError("Random-seed changed an old actor's complete raw alias vector")
    for role, actor, old, new, a, b, wanted in expected["complete_alias_effective"]:
        for target in (old, new):
            got = policy.context_av(_context(role, actor, a),
                _context("object_r", target, b), "file", raw.classes["file"])
            if got != wanted:
                raise ValueError("Random-seed changed an old actor's constrained alias access")
        checks.append([role, actor, old, new, a, b, wanted])
    final = _check_role(raw, here, True)
    role_rows = _effective_role(policy, lines, final, raw.classes)
    before = {(target, cls, a, b): mask for target, cls, a, b, mask in expected["role_before"]}
    wanted = dict(before)
    for row in expected["successor_aliases"]:
        for a in LEVELS:
            for b in LEVELS:
                key = (row["source"], row["class"], a, b)
                new = (row["target"], row["class"], a, b)
                if key in wanted and new not in before:
                    wanted[new] = wanted.get(new, 0) | wanted[key]
    for target, cls, a, b, mask in role_rows:
        if wanted.get((target, cls, a, b)) != mask:
            raise ValueError("Random-seed successor changed a constrained role vector")
    checks.extend(role_rows)
    contexts = verify_file_contexts(here, exported.parent)
    return {
        "schema": "droidloom.native-random-seed-policy-proof.v1",
        "source": {"bytes": CONTRACT_PIN[0], "sha256": CONTRACT_PIN[1], "contents": value},
        "source_bound_readback_required": True,
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_raw_vectors": len(expected["complete_alias_raw"]) * 2,
        "preserved_effective_vectors": len(expected["complete_alias_effective"]) * 2,
        "category_pairs": len(LEVELS) ** 2,
        "predecessor_aliases": expected["predecessor_aliases"],
        "successor_aliases": expected["successor_aliases"],
        "role_raw_class_object_pairs": len(raw.types) * len(raw.classes),
        "role_raw_nonzero_vectors": [[*key, sorted(names)] for key, names in sorted(final.items())],
        "role_effective_vectors": len(role_rows),
        "entry_transition_replacement": expected["entry_replacement"],
        "named_file_transition": SEED_CREATION,
        "seed_parent_permissions": sorted(_base_role()[(PARENT, "dir")]),
        "seed_file_permissions": sorted(_base_role()[(FILE, "file")]),
        "entropy_device_permissions": ["open", "read", "write"],
        "sys_admin": False, "entropy_ioctls": False, "new_network_sockets": False,
        "default_credit": "normal-environment-unset-NO",
        "file_contexts": contexts,
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "runtime_qualified": False, "cross_boot_credit_qualified": False,
    }


def verify_file_contexts(here, work):
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    data = b"".join((here / name).read_bytes() for name in names)
    path = work / "random-seed-file-contexts"
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Random-seed matcher input changed")
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
        raise ValueError("Normal class-aware random-seed file contexts cannot be opened")
    cases = [
        ("/usr/lib/systemd/systemd-random-seed", stat.S_IFREG, ENTRY),
        ("/var/lib/systemd/random-seed", stat.S_IFREG, FILE),
        ("/var/lib/systemd", stat.S_IFDIR, PARENT),
        ("/usr/lib/systemd/systemd-update-done", stat.S_IFREG, "p4_linux_update_done_exec_t"),
    ]
    for base in ("/usr/lib/systemd/systemd-random-seed", "/var/lib/systemd/random-seed"):
        cases.extend((base, kind, None) for kind in (stat.S_IFDIR, stat.S_IFLNK))
        cases.extend((base + tail, stat.S_IFREG, None) for tail in ("-old", ".tmp", "/child"))
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
                raise ValueError("Random-seed class-aware lookup failed")
            actual = context.split(":")[2] if context else None
            if wanted is not None and actual != wanted or wanted is None and actual in (ENTRY, FILE):
                raise ValueError("Random-seed exact/adjacent path boundary changed: " + name)
            rows.append([name, mode, context])
    finally:
        lib.selabel_close(handle)
    return {"cases": len(rows), "rows": rows, "composed_sha256": hashlib.sha256(data).hexdigest()}
