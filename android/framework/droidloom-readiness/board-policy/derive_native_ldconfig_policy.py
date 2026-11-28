"""Normal static-PIE ldconfig -X and its fixed cache publication lifecycle.

The unchanged libc-bin executable receives a dedicated entry. Existing actors
keep every original alias decision, ioctl filter and transition, except the
one executor entry transition explicitly moved from setup to ldconfig.
"""
import ctypes
import hashlib
import json
import re
import stat

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import (
    _classes, _roles, _context, derive_preserved_aliases, verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression

ROLE = "p4_linux_ldconfig_t"
ENTRY = "p4_linux_ldconfig_exec_t"
CONFIG = "p4_linux_ldconfig_config_t"
CONFIG_DIR = "p4_linux_ldconfig_config_dir_t"
AUX_DIR = "p4_linux_ldconfig_aux_dir_t"
AUX = "p4_linux_ldconfig_aux_t"
CACHE = "p4_linux_console_ld_cache_native_config_t"
ETC = "p4_linux_sysusers_etc_root_t"
VAR_CACHE = "p4_linux_var_cache_t"
EXECUTOR = "p4_linux_service_executor_t"
ALIASES = [
    {"source": "p4_linux_setup_exec_t", "target": ENTRY, "class": "file"},
    {"source": "p4_linux_native_config_t", "target": CONFIG, "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": CONFIG_DIR, "class": "dir"},
    {"source": "p4_linux_rootdir_t", "target": AUX_DIR, "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": AUX, "class": "file"},
]
# Closed source-owned interfaces for components preceding this stage. A
# standalone focused tree may omit a component; it cannot accept an unknown
# target or infer a permission from candidate output. Final reports list the
# concrete entries present for the release contract's exact composition gate.
PRIOR_ALIASES = [
    {"source": "p4_linux_setup_exec_t", "target": "p4_linux_tmpfiles_exec_t", "class": "file"},
    {"source": "p4_linux_runtime_lib_t", "target": "p4_linux_tmpfiles_usr_config_t", "class": "file"},
    {"source": "p4_linux_native_config_t", "target": "p4_linux_tmpfiles_etc_config_t", "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": "p4_linux_tmpfiles_config_dir_t", "class": "dir"},
    {"source": "p4_linux_rootdir_t", "target": "p4_linux_tmpfiles_runtime_dir_t", "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": "p4_linux_tmpfiles_nologin_t", "class": "file"},
    {"source": "p4_linux_usrmerge_link_t", "target": "p4_linux_tmpfiles_shm_link_t", "class": "lnk_file"},
    {"source": "p4_linux_setup_exec_t", "target": "p4_linux_update_done_exec_t", "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": "p4_linux_update_done_var_dir_t", "class": "dir"},
    {"source": "p4_linux_native_config_t", "target": "p4_linux_update_done_etc_file_t", "class": "file"},
    {"source": "p4_linux_native_data_t", "target": "p4_linux_update_done_var_file_t", "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": "p4_linux_kmod_tmpfiles_dir_t", "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": "p4_linux_kmod_static_nodes_t", "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": "p4_linux_journal_catalog_dir_t", "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": "p4_linux_journal_catalog_file_t", "class": "file"},
    {"source": "p4_linux_setup_exec_t", "target": "p4_linux_random_seed_exec_t", "class": "file"},
    {"source": "p4_linux_native_data_t", "target": "p4_linux_random_seed_file_t", "class": "file"},
    {"source": "p4_linux_runtime_lib_t", "target": "p4_linux_timesyncd_exec_t", "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": "p4_linux_timesyncd_run_t", "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": "p4_linux_timesyncd_run_t", "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": "p4_linux_timesyncd_state_t", "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": "p4_linux_timesyncd_state_t", "class": "file"},
    {"source": "p4_linux_native_config_t", "target": "p4_linux_timesyncd_config_t", "class": "file"},
    {"source": "p4_linux_native_config_t", "target": "p4_linux_timesyncd_nsswitch_t", "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": "p4_linux_timesyncd_netif_t", "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": "p4_linux_timesyncd_netif_t", "class": "file"},
]
SOURCE_SHA256 = "6606f3532210d8b119457dc91124081671a8c7810b1bbfdf0e1bb0f6b1db06f9"
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
READ = {"getattr", "open", "read"}
MAP_READ = READ | {"map"}
CACHE_WRITE = {"getattr", "open", "create", "write", "setattr", "rename", "unlink"}
AUX_ACCESS = MAP_READ | {"create", "write", "rename", "unlink"}
ASSOCIATED = (CACHE, AUX_DIR, AUX)


def contract(here):
    raw = (here / "native-ldconfig-source.json").read_bytes()
    value = json.loads(raw)
    if (hashlib.sha256(raw).hexdigest() != SOURCE_SHA256
            or value["schema"] != "droidloom.native-ldconfig-source.v1"
            or value["aliases"] != ALIASES
            or value["command"] != ["/usr/sbin/ldconfig", "-X"]
            or value["runtime_qualified"] is not False
            or value["library_symlink_mutation"] is not False
            or value["helper_execution"] is not False
            or value["elf"] != {"class": 64, "machine": 62, "type": "ET_DYN",
                                "pt_interp": False, "dt_needed": [], "static_pie": True}):
        raise ValueError("The normal fixed ldconfig source closure changed")
    return value


def _rules(lines, classes):
    """Complete unconditional raw TE, independent of effective category AVs."""
    text = "\n".join(lines)
    if re.search(r"\((?:booleanif|tunableif|typebounds)\b", text):
        raise ValueError("Ldconfig proof needs unconditional, unbounded TE")
    result = []
    for line in lines:
        if not line.startswith("(allow "):
            continue
        form = parse_expression(line)
        if (len(form) != 4 or not isinstance(form[3], list)
                or len(form[3]) != 2 or not isinstance(form[3][1], list)):
            raise ValueError("Unmodeled ldconfig TE statement")
        source, target, (cls, names) = form[1:]
        if cls not in classes or not set(names).issubset(classes[cls]):
            raise ValueError("Unknown ldconfig TE permission")
        result.append((source, target, cls, set(names)))
    if len(result) != text.count("(allow "):
        raise ValueError("Ldconfig raw TE statement closure is incomplete")
    return result


def _alias_raw(policy, lines, classes, actors):
    members = Membership("\n".join(lines))
    rules = _rules(lines, classes)
    pairs = sorted({(row[side], row["class"])
                    for row in ALIASES for side in ("source", "target")})
    result = {}
    for target, cls in pairs:
        _, bits = policy.permissions(cls, classes[cls])
        selected = [(source, object_type, sum(bits[n] for n in names))
                    for source, object_type, rule_class, names in rules
                    if rule_class == cls and
                    (object_type == "self" or members.member(object_type, target))]
        for role, actor in actors:
            mask = 0
            for source, object_type, value in selected:
                if ((object_type != "self" or actor == target)
                        and members.member(source, actor)):
                    mask |= value
            result[(role, actor, target, cls)] = mask
    return result


def _extra(actor, target, cls):
    if actor in ("init_t", EXECUTOR) and (target, cls) == (ENTRY, "file"):
        return MAP_READ | {"execute"}
    return set()


def fixed_transitions():
    return sorted([
        "(typetransition " + EXECUTOR + " " + ENTRY + " process " + ROLE + ")",
        '(typetransition ' + ROLE + ' ' + ETC + ' file "ld.so.cache~" ' + CACHE + ')',
        '(typetransition ' + ROLE + ' ' + VAR_CACHE + ' dir "ldconfig" ' + AUX_DIR + ')',
        '(typetransition ' + ROLE + ' ' + AUX_DIR + ' file "aux-cache" ' + AUX + ')',
        '(typetransition ' + ROLE + ' ' + AUX_DIR + ' file "aux-cache~" ' + AUX + ')',
    ])


def _entry_replacement(lines, output, expected):
    old = "(typetransition " + EXECUTOR + " p4_linux_setup_exec_t process p4_linux_setup_t)"
    copied = "(typetransition " + EXECUTOR + " " + ENTRY + " process p4_linux_setup_t)"
    selected = "(typetransition " + EXECUTOR + " " + ENTRY + " process " + ROLE + ")"
    generated = output.read_text().splitlines()
    if (lines.count(old) != 1 or lines.count(selected) != 1
            or copied in lines or generated.count(copied) != 1
            or expected["transitions"].count(copied) != 1):
        raise ValueError("The sole normal executor entry replacement is not exact")
    generated.remove(copied)
    expected["transitions"].remove(copied)
    output.write_text("\n".join(generated) + "\n")
    expected["derived_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    return {"original": old, "mechanically_copied": copied, "selected": selected}


def _relabel_proof(policy, lines):
    """Preserve both original validatetrans guards, including type identity."""
    text = "\n".join(lines)
    members = Membership(text)
    selected = [line for line in lines if line.startswith(
        ("(validatetrans ", "(mlsvalidatetrans "))]
    if len(selected) != len(re.findall(r"\((?:validatetrans|mlsvalidatetrans)\b", text)):
        raise ValueError("Ldconfig relabel constraints are incomplete")
    proof = []
    for line in selected:
        form = parse_expression(line)
        if len(form) != 3:
            raise ValueError("Unmodeled ldconfig relabel constraint")
        cls, expression = form[1:]
        if cls not in ("file", "dir"):
            continue
        actor = {"file": "p4_linux_uevent_label_t",
                 "dir": "p4_linux_hardware_label_t"}[cls]
        if (form[0] != "validatetrans" or not isinstance(expression, list)
                or len(expression) != 3
                or expression[:2] != ["or", ["neq", "t3", actor]]):
            raise ValueError("Unmodeled ldconfig alias relabel actor")
        for row in ALIASES:
            if row["class"] != cls:
                continue
            for target in (row["source"], row["target"]):
                for source_level in LEVELS:
                    for target_level in LEVELS:
                        if policy.context_av(_context("system_r", actor, source_level),
                                _context("object_r", target, target_level), cls,
                                ["relabelfrom", "relabelto"]):
                            raise ValueError("A constrained relabel actor reaches an ldconfig alias")
            if cls == "dir":
                if expression[2] != ["or", ["eq", "t1", "device"], ["eq", "t1", "t2"]]:
                    raise ValueError("Hardware directory relabel identity predicate changed")
            else:
                def atoms(expr, target):
                    if not isinstance(expr, list):
                        if expr == "t2":
                            raise ValueError("Bare relabel target variable")
                        return expr
                    if len(expr) == 3 and expr[0] in ("eq", "neq") and "t2" in expr[1:]:
                        other = expr[2] if expr[1] == "t2" else expr[1]
                        if not isinstance(other, str) or other in ("t1", "t2", "t3"):
                            raise ValueError("Unmodeled file relabel identity")
                        equal = members.member(other, target)
                        return equal if expr[0] == "eq" else not equal
                    return [atoms(child, target) for child in expr]
                if atoms(expression, row["source"]) != atoms(expression, row["target"]):
                    raise ValueError("Ldconfig alias changed a full relabel predicate")
            proof.append({"source": row["source"], "target": row["target"], "class": cls,
                          "guarded_actor": actor, "both_relabel_directions": False,
                          "constraint_sha256": hashlib.sha256(line.encode()).hexdigest()})
    if len(proof) != len(ALIASES):
        raise ValueError("Both exact file/directory relabel guards are required")
    return sorted(proof, key=lambda row: row["target"])


def _successors(here):
    # Local imports avoid module cycles: every table is a closed reviewed
    # source interface, not a target-name pattern or a discovered file roster.
    from derive_native_console_policy import contract as console_contract
    from derive_native_remount_policy import ALIASES as REMOUNT
    from derive_native_logind_state_policy import ALIASES as LOGIND
    from derive_native_netplan_policy import ALIASES as NETPLAN
    from derive_native_sysusers_policy import ALIASES as SYSUSERS
    return (PRIOR_ALIASES + console_contract(here)["aliases"]
            + REMOUNT + LOGIND + NETPLAN + SYSUSERS)


def _own_tables(here, types):
    files = {
        ENTRY: MAP_READ | {"execute", "entrypoint"},
        CONFIG: READ,
        AUX: AUX_ACCESS,
        CACHE: CACHE_WRITE,
        "p4_linux_runtime_lib_t": MAP_READ,
        "p4_linux_elf_interpreter_t": MAP_READ,
    }
    dirs = {
        "p4_linux_rootdir_t": {"getattr", "open", "read", "search"},
        "p4_linux_etc_dir_t": {"getattr", "search"},
        CONFIG_DIR: {"getattr", "open", "read", "search"},
        AUX_DIR: {"getattr", "search", "create", "write", "add_name", "remove_name"},
        ETC: {"getattr", "search", "write", "add_name", "remove_name"},
        VAR_CACHE: {"getattr", "search", "write", "add_name"},
    }
    links = {target: {"getattr", "read"} for target in
             ("p4_linux_usrmerge_link_t", "p4_linux_timezone_link_t")}
    # A later alias copies only its exact source's existing view. An explicit
    # own-role target (cache, /etc) keeps the separately reviewed write edge.
    present = []
    for row in _successors(here):
        if row["target"] not in types:
            if row not in PRIOR_ALIASES:
                raise ValueError("A required ldconfig successor alias is missing")
            continue
        table = {"file": files, "dir": dirs, "lnk_file": links}.get(row["class"])
        if (table is not None and row["source"] in table
                and row["target"] not in table):
            table[row["target"]] = set(table[row["source"]])
        if row in PRIOR_ALIASES:
            present.append(dict(row))
    wanted = {}
    for cls, table in (("file", files), ("dir", dirs), ("lnk_file", links)):
        for target, names in table.items():
            wanted[(target, cls)] = set(names)
    wanted[("p4_linux_standardio_t", "chr_file")] = {"getattr", "read", "write"}
    wanted[(EXECUTOR, "unix_stream_socket")] = {"getattr", "read", "write"}
    wanted[(EXECUTOR, "fd")] = {"use"}
    wanted[(EXECUTOR, "process")] = {"sigchld"}
    wanted[("init_t", "process")] = {"sigchld"}
    return wanted, present


def _own_raw(lines, classes, wanted):
    members = Membership("\n".join(lines))
    # The actor remains outside every broad process/Android/trusted category.
    for attribute in ("domain", "mlstrustedsubject", "p4_linux_native_processes",
                      "p4_native_dev_root_traversers", "p4_native_self_fd_metadata_readers",
                      "p4_linux_dynamic_interpreter_clients"):
        if attribute in members.attributes and members.member(attribute, ROLE):
            raise ValueError("Ldconfig acquired a broad process attribute: " + attribute)
    if not members.member("p4_linux_procs", ROLE):
        raise ValueError("Ldconfig lost the native/Android separation guards")
    actual = {}
    for source, target, cls, names in _rules(lines, classes):
        if not members.member(source, ROLE):
            continue
        chosen = [ROLE] if target == "self" else [
            value for value in sorted(members.types) if members.member(target, value)]
        for value in chosen:
            actual.setdefault((value, cls), set()).update(names)
    expected = {key: value for key, value in wanted.items() if value}
    if actual != expected:
        different = {str(key): {"actual": sorted(actual.get(key, set())),
                               "expected": sorted(expected.get(key, set()))}
                     for key in actual.keys() | expected.keys()
                     if actual.get(key, set()) != expected.get(key, set())}
        raise ValueError("Ldconfig whole raw-TE boundary differs: " + json.dumps(different, sort_keys=True))
    return [[target, cls, sorted(names)] for (target, cls), names in sorted(actual.items())]


def derive(library, baseline, exported, here, output, export):
    contract(here)
    extras = {(actor, ENTRY, "file"): _extra(actor, ENTRY, "file")
              for actor in ("init_t", EXECUTOR)}
    expected = derive_preserved_aliases(library, baseline, exported, ALIASES,
        output, export, prefix="p4_ldconfig_preserved", isolated_roles={ROLE},
        extra_permissions=extras, preamble=(
            "; Preserve all existing actors and their original five source views.",
            "; The new ldconfig actor has a separate complete raw/effective proof."))
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    expected["entry_transition"] = _entry_replacement(lines, output, expected)
    expected["all_constraints"] = sorted(line for line in lines if line.startswith(CONSTRAINTS))
    expected["relabel_constraints"] = _relabel_proof(policy, lines)
    expected["alias_raw"] = []
    expected["alias_mcs"] = []
    raw = _alias_raw(policy, lines, expected["classes"], expected["actors"])
    for row in ALIASES:
        old, new, cls = row["source"], row["target"], row["class"]
        names = expected["classes"][cls]
        _, bits = policy.permissions(cls, names)
        for actor_role, actor in expected["actors"]:
            before = raw[(actor_role, actor, old, cls)]
            preimage = raw[(actor_role, actor, new, cls)]
            extra = sum(bits[name] for name in _extra(actor, new, cls))
            if preimage & ~(before | extra) or extra & ~preimage:
                raise ValueError("Ldconfig alias has an undeclared raw preimage")
            expected["alias_raw"].append([actor_role, actor, old, new, cls, before, before | extra])
            for source_level in LEVELS:
                for target_level in LEVELS:
                    context = _context(actor_role, actor, source_level)
                    old_value = policy.context_av(context, _context("object_r", old, target_level), cls, names)
                    preimage_value = policy.context_av(context, _context("object_r", new, target_level), cls, names)
                    expected["alias_mcs"].append(
                        [actor_role, actor, old, new, cls, source_level, target_level,
                         old_value, old_value | preimage_value])
    own_types = set(re.findall(r"\(type (\w+)\)", "\n".join(lines)))
    wanted, present = _own_tables(here, own_types)
    # At this stage, later aliases have not yet received their preserved
    # ldconfig source view. Check every declared rule now; final checks require
    # the full source-derived successor table.
    pre = dict(wanted)
    late = {row["target"] for row in _successors(here)
            if row not in PRIOR_ALIASES and row["target"] not in {CACHE, ETC}}
    explicit = {"p4_linux_console_entry_runtime_lib_t", "p4_linux_console_library_runtime_lib_t",
                "p4_linux_console_public_runtime_lib_t", "p4_linux_console_locale_runtime_lib_t",
                "p4_linux_console_cache_dir_t"}
    for key in list(pre):
        if key[0] in late and key[0] not in explicit:
            pre.pop(key)
    expected["own_raw_preimage"] = _own_raw(lines, expected["classes"], pre)
    # No actual AV is used as an unreviewed expected grant: raw TE above must
    # match the fixed source-owned table first; unchanged complete constraints
    # then determine the effective category decisions of each declared edge.
    expected["own_mcs"] = []
    for target, cls in ((CACHE, "file"), (AUX, "file"), (ETC, "dir"),
                        (AUX_DIR, "dir"), (VAR_CACHE, "dir")):
        for source_level in LEVELS:
            for target_level in LEVELS:
                names = expected["classes"][cls]
                got = policy.context_av(_context("system_r", ROLE, source_level),
                    _context("object_r", target, target_level), cls, names)
                expected["own_mcs"].append([target, cls, source_level, target_level, got])
    expected["prior_aliases_present"] = present
    expected["source_contract_sha256"] = SOURCE_SHA256
    return expected


def verify(library, binary, exported, here, expected, export):
    value = contract(here)
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    text = "\n".join(lines)
    classes = _classes(text)
    if classes != expected["classes"]:
        raise ValueError("Ldconfig class/permission definitions changed")
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    if sorted(line for line in lines if line.startswith(CONSTRAINTS)) != expected["all_constraints"]:
        raise ValueError("Ldconfig changed a full ordinary/MLS/relabel constraint")
    if _relabel_proof(policy, lines) != expected["relabel_constraints"]:
        raise ValueError("Ldconfig changed a reachable relabel predicate")
    raw = _alias_raw(policy, lines, classes, expected["actors"])
    for actor_role, actor, old, new, cls, before, after in expected["alias_raw"]:
        if (raw[(actor_role, actor, old, cls)] != before or
                raw[(actor_role, actor, new, cls)] != after):
            raise ValueError("Ldconfig changed an existing actor raw alias vector")
        checks.append([actor_role, actor, old, new, cls, before, after])
    for actor_role, actor, old, new, cls, source_level, target_level, before, after in expected["alias_mcs"]:
        context = _context(actor_role, actor, source_level)
        for target, wanted in ((old, before), (new, after)):
            actual = policy.context_av(context, _context("object_r", target, target_level),
                                       cls, classes[cls])
            if actual != wanted:
                raise ValueError("Ldconfig changed an exact category-pair alias decision")
        checks.append([actor_role, actor, old, new, cls, source_level, target_level, before, after])
    transition_lines = {line for line in lines if line.startswith(TRANSITIONS)}
    replacement = expected["entry_transition"]
    if (replacement["original"] not in transition_lines
            or replacement["selected"] not in transition_lines
            or replacement["mechanically_copied"] in transition_lines):
        raise ValueError("Ldconfig entry selected an old setup transition")
    new_types = {ROLE} | {row["target"] for row in ALIASES}
    related = {line for line in transition_lines
               if any(re.search(r"\b" + re.escape(name) + r"\b", line) for name in new_types)}
    if related != set(expected["transitions"]) | set(fixed_transitions()):
        raise ValueError("Ldconfig acquired an unnamed or unrelated transition")
    types = set(re.findall(r"\(type (\w+)\)", text))
    objects = sorted(set(re.findall(r"\(roletype object_r (\w+)\)", text)))
    actors = _roles(lines)
    wanted, present = _own_tables(here, types)
    own_raw = _own_raw(lines, classes, wanted)
    if present != expected["prior_aliases_present"]:
        raise ValueError("Ldconfig source-owned prior alias roster changed")
    def av(actor_role, actor, target_role, target, cls, names, expect):
        got = policy.context_av(_context(actor_role, actor), _context(target_role, target), cls, names)
        _, bits = policy.permissions(cls, names)
        want = sum(bits[name] for name in expect)
        if got != want:
            actual = sorted(name for name, bit in bits.items() if got & bit)
            raise ValueError("Ldconfig effective boundary differs: " + actor + " -> " +
                             target + " " + cls + " " + str(actual) + " != " + str(sorted(expect)))
        checks.append([actor_role, actor, target_role, target, cls, sorted(expect)])
    checked_classes = ("file", "dir", "lnk_file", "chr_file", "blk_file", "filesystem")
    for target in objects:
        for cls in checked_classes:
            av("system_r", ROLE, "object_r", target, cls, classes[cls],
               wanted.get((target, cls), set()))
    for actor_role, actor in actors:
        for cls in ("process", "process2", "fd", "unix_stream_socket"):
            av("system_r", ROLE, actor_role, actor, cls, classes[cls],
               wanted.get((actor, cls), set()))
        for cls, names, expect in (
            ("process", ["transition", "dyntransition"], {"transition"} if actor == EXECUTOR else set()),
            ("process2", ["nnp_transition"], {"nnp_transition"} if actor == EXECUTOR else set())):
            av(actor_role, actor, "system_r", ROLE, cls, names, expect)
    for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
        av("system_r", ROLE, "system_r", ROLE, cls, classes[cls], set())
    av("system_r", ROLE, "r", "kernel", "security", classes["security"], set())
    for target, cls, source_level, target_level, wanted_mask in expected["own_mcs"]:
        got = policy.context_av(_context("system_r", ROLE, source_level),
            _context("object_r", target, target_level), cls, classes[cls])
        if got != wanted_mask:
            raise ValueError("Ldconfig write escaped its declared category-pair decision")
        checks.append([ROLE, target, cls, source_level, target_level, got])
    # Neither ioctl nor nlmsg may appear through an inherited source attribute.
    # The admitted Android binary exports both ordinary extended-permission
    # kinds; rejecting an unrelated actor\'s nlmsg syntax would reject the
    # unchanged original policy instead of checking this role\'s authority.
    members = Membership(text)
    allowx = [line for line in lines if line.startswith("(allowx ")]
    if len(allowx) != text.count("(allowx "):
        raise ValueError("Ldconfig ioctl statement closure is incomplete")
    for line in allowx:
        form = parse_expression(line)
        if (len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 3
                or form[3][0] not in ("ioctl", "nlmsg") or form[3][1] not in classes
                or not isinstance(form[3][2], list)):
            raise ValueError("Unmodeled ldconfig extended-permission statement")
        if members.member(form[1], ROLE):
            raise ValueError("Ldconfig acquired an inherited extended-permission filter")
    associations = []
    for subject in ASSOCIATED:
        for target in objects:
            names = {"associate"} if target == "labeledfs" else set()
            av("object_r", subject, "object_r", target, "filesystem",
               classes["filesystem"], names)
            associations.append([subject, target, sorted(names)])
    socket_classes = [cls for cls in classes if cls == "socket" or cls.endswith("_socket")]
    raw_vector_count = len(types) * len(classes)
    return {
        "schema": "droidloom.native-ldconfig-policy-proof.v1",
        "source": {"bytes": (here / "native-ldconfig-source.json").stat().st_size,
                   "sha256": SOURCE_SHA256, "contents": value},
        "alias_preserver_sha256": hashlib.sha256((here / "derive_preserved_alias_policy.py").read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256((here / "derive_native_ldconfig_policy.py").read_bytes()).hexdigest(),
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_raw_te_vectors": len(expected["alias_raw"]),
        "preserved_mcs_source_target_vectors": len(expected["alias_mcs"]),
        "preserved_transitions": len(expected["transitions"]),
        "entry_transition_replacement": replacement,
        "fixed_transitions": fixed_transitions(),
        "all_ranges_constraint_target_checks": expected["constraint_target_checks"],
        "relabel_constraints": expected["relabel_constraints"],
        "concrete_actors": len(actors), "concrete_types": len(types),
        "concrete_objects": len(objects), "classes": len(classes),
        "own_raw_actor_object_class_vectors": raw_vector_count,
        "own_nonzero_raw_vectors": own_raw,
        "own_mutable_category_pairs": len(expected["own_mcs"]),
        "socket_classes_with_complete_raw_boundary": len(socket_classes),
        "association_vectors": len(associations),
        "extended_permission_rules_checked": len(allowx),
        "prior_aliases_present": present,
        "file_contexts": verify_file_contexts(here, exported.parent),
        "effective_vector_checks": len(checks),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "source_bound_readback_required": True,
        "normal_unit_changed": False,
        "runtime_qualified": False,
    }


def verify_file_contexts(here, work):
    value = contract(here)
    path = work / "ldconfig-file-contexts"
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    path.write_bytes(b"".join((here / name).read_bytes() for name in names))
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
        raise OSError(ctypes.get_errno(), "Cannot open normal ldconfig context matcher")
    checks = []
    def lookup(filename, mode):
        result = ctypes.c_char_p()
        if lib.selabel_lookup_raw(handle, ctypes.byref(result), filename.encode(), mode):
            if ctypes.get_errno() == 2:
                return None
            raise OSError(ctypes.get_errno(), "Ldconfig context lookup failed")
        try:
            return result.value.decode().split(":")[2]
        finally:
            lib.freecon(result)
    expected = [(row["path"], stat.S_IFREG, row["target_type"]) for row in value["normal_files"]]
    expected += [(row["path"], stat.S_IFDIR, row["type"]) for row in value["existing_directories"]]
    expected += [(name, stat.S_IFREG, row["type"]) for row in value["mutable_outputs"]
                 for name in (row["path"], row["temporary"])]
    aliases = {row["target"] for row in ALIASES}
    modes = (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFCHR,
             stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK)
    try:
        for filename, selected, wanted in expected:
            for mode in modes:
                got = lookup(filename, mode)
                if ((mode == selected and got != wanted)
                        or (mode != selected and got in aliases | {CACHE})):
                    raise ValueError("Ldconfig alias escaped its inode class: " + filename)
                checks.append([filename, mode, got])
        for filename, mode, wanted in (
            ("/etc/passwd", stat.S_IFREG, "p4_linux_public_accounts_t"),
            ("/etc/shadow", stat.S_IFREG, "p4_linux_auth_data_t"),
            ("/etc/.pwd.lock", stat.S_IFREG, "p4_linux_sysusers_passwd_lock_t"),
            ("/etc/ld.so.cache.other", stat.S_IFREG, "p4_linux_native_config_t"),
            ("/etc/ld.so.conf.d/other.conf", stat.S_IFREG, "p4_linux_native_config_t"),
            ("/etc/ld.so.conf.d.other", stat.S_IFDIR, "p4_linux_rootdir_t"),
            ("/var/cache/ldconfig/other", stat.S_IFREG, "p4_linux_native_data_t"),
            ("/var/cache/ldconfig.other", stat.S_IFDIR, "p4_linux_rootdir_t"),
            ("/usr/sbin/ldconfig.other", stat.S_IFREG, "p4_linux_native_bin_t")):
            got = lookup(filename, mode)
            if got != wanted:
                raise ValueError("Adjacent ldconfig pathname changed: " + filename)
            checks.append([filename, mode, got])
    finally:
        lib.selabel_close(handle)
    return {"checks": len(checks), "matrix_sha256":
            hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest()}
