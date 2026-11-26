"""Fixed normal netplan configure branch in the strict policy producer.

The package ELF is unchanged. The complete-root admission still selects only
the public global renderer. A separate fixed private-input contract records the
original seven NetworkManager profiles; neither source check claims runtime.
"""
import ctypes
import hashlib
import json
import re
import stat

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_native_console_policy import contract as console_contract
from derive_native_sysusers_policy import ALIASES as SYSUSERS_ALIASES
from derive_native_logind_state_policy import ALIASES as LOGIND_ALIASES
from derive_native_timesync_policy import ALIASES as TIMESYNC_ALIASES
from derive_native_kmod_static_policy import ALIASES as KMOD_ALIASES
from derive_preserved_alias_policy import (
    _roles, _context, _preserved_xperm_rules,
    derive_preserved_aliases, verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression, original_xperms

ROLE = "p4_linux_netplan_t"
ENTRY = "p4_linux_netplan_exec_t"
LIBRARY = "p4_linux_netplan_library_t"
YAML = "p4_linux_netplan_yaml_t"
INPUT_DIR = "p4_linux_netplan_input_dir_t"
OUTPUT = "p4_linux_netplan_output_t"
DENIED_DIR = "p4_linux_netplan_unselected_dir_t"
EXECUTOR = "p4_linux_service_executor_t"
NM_RUN = "p4_linux_network_manager_run_t"
CACHE = "p4_linux_console_ld_cache_native_config_t"
SHARED_LIBRARY = "p4_linux_console_library_runtime_lib_t"
BASE_ALIASES = [
    {"source": "p4_linux_native_bin_t", "target": ENTRY, "class": "file"},
    {"source": "p4_linux_runtime_lib_t", "target": LIBRARY, "class": "file"},
    {"source": "p4_linux_runtime_lib_t", "target": YAML, "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": INPUT_DIR, "class": "dir"},
    {"source": NM_RUN, "target": OUTPUT, "class": "file"},
]
PRIVATE_INPUT = "p4_linux_netplan_private_config_t"
PROFILE_DIR = "p4_linux_netplan_profiles_dir_t"
LINK_DIR = "p4_linux_netplan_link_dir_t"
RULE_DIR = "p4_linux_netplan_rule_dir_t"
GENERATED = "p4_linux_netplan_link_rule_t"
PRIVATE_ALIASES = [
    {"source": "p4_linux_native_config_t", "target": PRIVATE_INPUT, "class": "file"},
    {"source": NM_RUN, "target": PROFILE_DIR, "class": "dir"},
    {"source": "p4_linux_rootdir_t", "target": LINK_DIR, "class": "dir"},
    {"source": "p4_linux_rootdir_t", "target": RULE_DIR, "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": GENERATED, "class": "file"},
]
ALIASES = BASE_ALIASES + PRIVATE_ALIASES
LIBDIR = "/usr/lib/x86_64-linux-gnu/"
ELF_NAMES = (
    "ld-linux-x86-64.so.2", "libatomic.so.1.2.0", "libblkid.so.1.1.0",
    "libc.so.6", "libffi.so.8.2.0", "libgio-2.0.so.0.8800.0",
    "libglib-2.0.so.0.8800.0", "libgmodule-2.0.so.0.8800.0",
    "libgobject-2.0.so.0.8800.0", "libm.so.6", "libmount.so.1.1.0",
    "libnetplan.so.1", "libpcre2-8.so.0.14.0", "libselinux.so.1",
    "libuuid.so.1.3.0", "libyaml-0.so.2.0.9", "libz.so.1.3.1",
)
ELF_PATHS = {"/usr/libexec/netplan/configure", *(LIBDIR + n for n in ELF_NAMES)}
YAML_PATH = "/usr/lib/netplan/00-network-manager-all.yaml"
UNIT_PATH = "/usr/lib/systemd/system/netplan-configure.service"
OUTPUT_PATH = "/run/NetworkManager/conf.d/10-globally-managed-devices.conf"
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")


def contract(here):
    value = json.loads((here / "native-netplan-source.json").read_text())
    keys = {"schema", "packages", "aliases", "files", "directories", "command_links",
            "elf_paths", "needed_edges", "shared_library_paths", "unit_argv",
            "selected_configuration", "output_path", "output_sha256", "file_packages",
            "source_documents", "runtime_qualified", "other_yaml_profiles_qualified"}
    if (set(value) != keys or
            value["schema"] != "droidloom.native-netplan-source-closure.v1" or
            value["aliases"] != BASE_ALIASES or value["runtime_qualified"] is not False or
            value["other_yaml_profiles_qualified"] is not False or
            value["selected_configuration"] != "global-NetworkManager-without-netdefs" or
            value["unit_argv"] != ["/usr/libexec/netplan/configure"] or
            value["output_path"] != OUTPUT_PATH or
            value["output_sha256"] != hashlib.sha256(b"").hexdigest() or
            set(value["elf_paths"]) != ELF_PATHS or len(value["elf_paths"]) != 18):
        raise ValueError("Netplan contract is not the fixed normal no-netdefs branch")
    console = console_contract(here)
    shared = {row["paths"][0]: row for row in console["files"] if row["category"] == "library"}
    if (len(shared) != 9 or set(value["shared_library_paths"]) != set(shared) or
            len(value["shared_library_paths"]) != 9):
        raise ValueError("Netplan shared library type is not the full pinned console group")
    paths = ELF_PATHS | set(shared) | {YAML_PATH, UNIT_PATH, "/etc/ld.so.cache"}
    if len(value["files"]) != len(paths) or {row["path"] for row in value["files"]} != paths:
        raise ValueError("Netplan dependency/source inode set differs")
    file_keys = {"path", "bytes", "sha256", "mode", "uid", "gid", "nlink",
                 "category", "source_type", "target_type"}
    for row in value["files"]:
        path = row["path"]
        if (set(row) != file_keys or row["uid"] != 0 or row["gid"] != 0 or
                row["nlink"] != 1 or row["mode"] not in (0o600, 0o644, 0o755) or
                not 0 < row["bytes"] <= 16 * 1024 * 1024 or
                not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise ValueError("Netplan normal file identity is incomplete")
        expected = (row["source_type"], row["target_type"], row["category"])
        if path == "/usr/libexec/netplan/configure":
            wanted = ("p4_linux_native_bin_t", ENTRY, "entry")
        elif path == YAML_PATH:
            wanted = ("p4_linux_runtime_lib_t", YAML, "config")
            if (row["bytes"], row["sha256"], row["mode"]) != (
                    49, "d0fa4fd1b88a52f9b8eae641c7c84b7843197155c08df46c0057a4ea23094411", 0o600):
                raise ValueError("Netplan selected public YAML changed")
        elif path == UNIT_PATH:
            wanted = ("p4_linux_unit_file_t", "p4_linux_unit_file_t", "unit")
            if (row["bytes"], row["sha256"]) != (
                    879, "6893fca2c14d53951c73f396f7528b0b1baa9f570ca9cf099dc1c71df1aa2724"):
                raise ValueError("Netplan normal unit or command arguments changed")
        elif path == "/etc/ld.so.cache":
            wanted = (CACHE, CACHE, "cache")
            source = next(r for r in console["files"] if r["paths"] == [path])
            if any(row[k] != source[k] for k in ("bytes", "sha256", "mode", "uid", "gid", "nlink")):
                raise ValueError("Netplan loader cache differs from the admitted normal cache")
        elif path == LIBDIR + "ld-linux-x86-64.so.2":
            wanted = ("p4_linux_elf_interpreter_t", "p4_linux_elf_interpreter_t", "loader")
        elif path in shared:
            wanted = (SHARED_LIBRARY, SHARED_LIBRARY,
                      "library" if path in ELF_PATHS else "shared_label_member")
            if any(row[k] != shared[path][k] for k in ("bytes", "sha256", "mode", "uid", "gid", "nlink")):
                raise ValueError("Netplan shared library bytes differ from normal console closure")
        else:
            wanted = ("p4_linux_runtime_lib_t", LIBRARY, "library")
        if expected != wanted:
            raise ValueError("Netplan source category or file type differs: " + path)
    expected_dirs = [
        ("/usr/lib/netplan", ["00-network-manager-all.yaml", "PLACEHOLDER"]),
        ("/etc/netplan", []), ("/run/netplan", []),
    ]
    if value["directories"] != [
            {"path": p, "mode": 0o755, "uid": 0, "gid": 0, "nlink": 2, "names": names,
             "source_type": "p4_linux_rootdir_t", "target_type": INPUT_DIR}
            for p, names in expected_dirs]:
        raise ValueError("Netplan input directories contain another configuration profile")
    packages = value["packages"]
    if (len(packages) != 19 or packages.get("netplan-generator:amd64") != "1.2-1ubuntu5.1" or
            packages.get("libnetplan1:amd64") != "1.2-1ubuntu5.1" or
            packages.get("libsystemd0:amd64") != "259.9-0ubuntu0.1+p4gentmp2" or
            set(value["file_packages"]) != paths - {"/etc/ld.so.cache"} or
            set(value["file_packages"].values()) != set(packages)):
        raise ValueError("Netplan full normal package ownership roster differs")
    links = value["command_links"]
    if (len(links) != 15 or len({r["path"] for r in links}) != 15 or
            any(set(r) != {"path", "target", "uid", "gid", "nlink"} or
                (r["uid"], r["gid"], r["nlink"]) != (0, 0, 1) or
                not r["path"].startswith(("/usr/lib/", "/usr/lib64/", "/lib")) or
                not r["target"] or r["target"].startswith("/") or
                "\n" in r["target"] for r in links)):
        raise ValueError("Netplan normal loader link closure differs")
    if not value["needed_edges"] or not value["source_documents"]:
        raise ValueError("Netplan normal dependency/source evidence is absent")
    return value


def private_contract(here):
    value = json.loads((here / "native-netplan-private-source.json").read_text())
    required = {"schema", "normal_source_contract_sha256", "selection", "profiles",
                "public_inputs", "public_account_paths", "account_lookup",
                "normal_unit_argv", "normal_service_umask", "source_documents",
                "observation", "private_contents_included", "runtime_qualified",
                "policy_enforcement_qualified"}
    names = {
        "50-cloud-init.yaml",
        "90-NM-3c797701-51cb-45c5-a632-00f213232095.yaml",
        "90-NM-899dbbd2-d128-4d5b-8001-5d3cad80b503.yaml",
        "90-NM-c61cd9fc-00ef-49aa-8ed2-7bfd641c7097.yaml",
        "90-NM-d732669d-d34a-4baa-b97e-bd2563bdd648.yaml",
        "90-NM-e80414a4-1077-49d3-953e-aaccddb3bf21.yaml",
        "90-NM-f84d0c1a-dcde-4634-bf39-13ace1617de3.yaml",
    }
    if (set(value) != required or
            value["schema"] != "droidloom.native-netplan-private-source.v1" or
            value["normal_source_contract_sha256"] != hashlib.sha256(
                (here / "native-netplan-source.json").read_bytes()).hexdigest() or
            value["selection"] != "pocket4-existing-seven-NetworkManager-profiles" or
            value["normal_unit_argv"] != ["/usr/libexec/netplan/configure"] or
            value["normal_service_umask"] != 0o022 or
            value["public_account_paths"] != ["/etc/passwd", "/etc/group"] or
            value["account_lookup"] != "unique-root-uid0-gid0-and-files-first" or
            value["private_contents_included"] is not False or
            value["runtime_qualified"] is not False or
            value["policy_enforcement_qualified"] is not False or
            len(value["profiles"]) != 7 or
            {row["path"] for row in value["profiles"]} !=
                {"/etc/netplan/" + name for name in names}):
        raise ValueError("Netplan private scope is not the existing seven-profile selection")
    fields = {"path", "bytes", "sha256", "mode", "uid", "gid", "nlink"}
    for row in value["profiles"] + value["public_inputs"]:
        if (set(row) != fields or
                (row["uid"], row["gid"], row["nlink"]) != (0, 0, 1) or
                row["mode"] not in (0o600, 0o644) or
                not 0 < row["bytes"] <= 1024 * 1024 or
                not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise ValueError("Netplan private/source metadata changed")
    if (any(row["mode"] != 0o600 for row in value["profiles"]) or
            len(value["public_inputs"]) != 3 or
            {row["path"] for row in value["public_inputs"]} !=
                {YAML_PATH, "/usr/lib/netplan/PLACEHOLDER", "/etc/nsswitch.conf"} or
            len(value["source_documents"]) != 5 or
            value["observation"]["schema"] !=
                "droidloom.netplan-private-profile-public-observation.v2"):
        raise ValueError("Netplan private/public input boundary differs")
    return value


NM_ROLE = "p4_linux_network_manager_t"
FIXED_OLD_ACTORS = ("init_t", EXECUTOR, NM_ROLE)
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")


def _actor_raw(policy, lines, classes, actor):
    """Complete fixed old actor file/directory TE, before category filtering."""
    if actor not in FIXED_OLD_ACTORS:
        raise ValueError("Netplan raw preservation requires a fixed old actor")
    text = "\n".join(lines)
    if re.search(r"\((?:booleanif|tunableif|typebounds)\b", text):
        raise ValueError("Netplan alias preservation needs unconditional, unbounded TE")
    members = Membership(text)
    objects = sorted(set(re.findall(r"\(roletype object_r (\w+)\)", text)))
    selected = []
    count = 0
    for line in lines:
        if not line.startswith("(allow "):
            continue
        count += 1
        form = parse_expression(line)
        if (len(form) != 4 or not isinstance(form[3], list) or
                len(form[3]) != 2 or not isinstance(form[3][1], list)):
            raise ValueError("Unmodeled fixed native actor TE rule")
        source, target, (cls, permissions) = form[1:]
        if cls not in classes or not set(permissions).issubset(classes[cls]):
            raise ValueError("Unknown fixed native actor TE class/permission")
        if cls in ("file", "dir") and members.member(source, actor):
            selected.append((target, cls, set(permissions)))
    if count != text.count("(allow "):
        raise ValueError("Fixed native actor TE statements are incomplete")
    result = []
    for target in objects:
        for cls in ("file", "dir"):
            actual = set()
            for object_type, rule_class, permissions in selected:
                if rule_class == cls and (
                        (object_type == "self" and target == actor) or
                        (object_type != "self" and members.member(object_type, target))):
                    actual.update(permissions)
            result.append([target, cls, sorted(actual)])
    return result


def _relabel_constraints(policy, lines):
    """Bind the unchanged hardware/uevent guards and every alias predicate."""
    text = "\n".join(lines)
    members = Membership(text)
    proof = []
    selected = [line for line in lines if line.startswith(
        ("(validatetrans ", "(mlsvalidatetrans "))]
    if len(selected) != len(re.findall(r"\((?:validatetrans|mlsvalidatetrans)\b", text)):
        raise ValueError("Netplan relabel constraints are not complete statements")
    for line in selected:
        form = parse_expression(line)
        if len(form) != 3:
            raise ValueError("Unmodeled Netplan relabel constraint")
        cls, expression = form[1:]
        if cls not in ("file", "dir"):
            continue
        actor = {"file": "p4_linux_uevent_label_t",
                 "dir": "p4_linux_hardware_label_t"}[cls]
        if (form[0] != "validatetrans" or not isinstance(expression, list) or
                len(expression) != 3 or expression[:2] != ["or", ["neq", "t3", actor]]):
            raise ValueError("Netplan selected class has an unmodeled relabel actor")
        for row in ALIASES:
            if row["class"] != cls:
                continue
            for target in (row["source"], row["target"]):
                for source_level in LEVELS:
                    for target_level in LEVELS:
                        if policy.context_av(_context("system_r", actor, source_level),
                                _context("object_r", target, target_level), cls,
                                ["relabelfrom", "relabelto"]):
                            raise ValueError("A constrained relabel actor reaches a Netplan alias")
            if cls == "dir":
                if expression[2] != ["or", ["eq", "t1", "device"], ["eq", "t1", "t2"]]:
                    raise ValueError("Hardware directory relabel predicate changed")
            else:
                def target_atoms(expr, target):
                    if not isinstance(expr, list):
                        if expr == "t2":
                            raise ValueError("Unmodeled bare relabel target variable")
                        return expr
                    if len(expr) == 3 and expr[0] in ("eq", "neq") and "t2" in expr[1:]:
                        other = expr[2] if expr[1] == "t2" else expr[1]
                        if not isinstance(other, str) or other in ("t1", "t2", "t3"):
                            raise ValueError("Unmodeled file relabel identity predicate")
                        equal = members.member(other, target)
                        return equal if expr[0] == "eq" else not equal
                    return [target_atoms(child, target) for child in expr]
                if target_atoms(expression, row["source"]) != target_atoms(expression, row["target"]):
                    raise ValueError("Netplan alias changed a complete file relabel predicate")
            proof.append({"class": cls, "guarded_actor": actor,
                          "source_type": row["source"], "alias_type": row["target"],
                          "relabel_from_and_to": False,
                          "constraint_sha256": hashlib.sha256(line.encode()).hexdigest()})
    if (len(proof) != len(ALIASES) or
            {row["alias_type"] for row in proof} != {row["target"] for row in ALIASES}):
        raise ValueError("The exact existing file/directory relabel guards are required")
    return sorted(proof, key=lambda row: row["alias_type"])


def _actor_extra(actor, target, cls):
    """Only the two already-declared fixed entry readers have extra raw TE."""
    if actor not in FIXED_OLD_ACTORS:
        raise ValueError("Netplan preservation requires a fixed old actor")
    if actor in ("init_t", EXECUTOR) and (target, cls) == (ENTRY, "file"):
        return {"getattr", "open", "read", "execute", "map"}
    return set()


def _actor_allowed_raw(actor, target, cls, source, preimage):
    extra = _actor_extra(actor, target, cls)
    wanted = set(source) | extra
    if not set(preimage).issubset(wanted) or not extra.issubset(preimage):
        raise ValueError("Fixed native actor alias has an unexplained preimage")
    return wanted


def _actor_effective(policy, actor, original, target, cls,
                     source_level, target_level, names):
    """Compare one category pair; never union decisions across categories."""
    if actor not in FIXED_OLD_ACTORS:
        raise ValueError("Netplan effective proof requires a fixed old actor")
    source_context = _context("system_r", actor, source_level)
    before = policy.context_av(source_context,
        _context("object_r", original, target_level), cls, names)
    preimage = policy.context_av(source_context,
        _context("object_r", target, target_level), cls, names)
    return before, before | preimage


def _preserve_actor(policy, lines, exported, classes, output, actor):
    """Preserve every old object and alias, with only the fixed entry extras."""
    raw = _actor_raw(policy, lines, classes, actor)
    raw_map = {(target, cls): set(names) for target, cls, names in raw}
    all_aliases = ALIASES + SYSUSERS_ALIASES
    mapping = {(row["target"], row["class"]): row["source"] for row in all_aliases}
    expected_raw, effective, declared_extras, additional_raw = [], [], [], []
    for target, cls, preimage in raw:
        original = mapping.get((target, cls), target)
        source = raw_map[(original, cls)]
        wanted = _actor_allowed_raw(actor, target, cls, source, preimage)
        expected_raw.append([target, cls, sorted(wanted)])
        extra = _actor_extra(actor, target, cls)
        if extra:
            declared_extras.append([target, cls, sorted(extra)])
            additional_raw.append([target, cls, sorted(extra - source)])
        for level in LEVELS:
            _, vector = _actor_effective(policy, actor, original, target, cls,
                level, "s0", classes[cls])
            effective.append([target, cls, level, vector])
    mcs = []
    for row in ALIASES:
        if raw_map[(row["source"], row["class"])] & {"relabelfrom", "relabelto"}:
            raise ValueError("Fixed native actor can relabel a selected source")
        for source_level in LEVELS:
            for target_level in LEVELS:
                before, wanted = _actor_effective(policy, actor,
                    row["source"], row["target"], row["class"],
                    source_level, target_level, classes[row["class"]])
                mcs.append([row["source"], row["target"], row["class"],
                            source_level, target_level, before, wanted])
    xperms, rules = _preserved_xperm_rules(exported, ALIASES, [("system_r", actor)])
    for row in ALIASES:
        cls = row["class"]
        names = raw_map[(row["source"], cls)] | _actor_extra(actor, row["target"], cls)
        for op, selected in (("allow", names), ("neverallow", set(classes[cls]) - names)):
            if selected:
                rules.append("(" + op + " " + actor + " " + row["target"] +
                             " (" + cls + " (" + " ".join(sorted(selected)) + ")))")
    with output.open("a") as stream:
        stream.write("; Fixed existing actor " + actor + ": complete raw TE and exact entry extras.\n")
        stream.write("\n".join(sorted(set(rules))) + "\n")
    return {"actor": actor, "raw_vectors": expected_raw, "effective_vectors": effective,
            "mcs_vectors": mcs, "xperms": xperms,
            "declared_extra_permissions": declared_extras,
            "additional_raw_permissions": additional_raw,
            "constraint_forms": sorted(line for line in lines if line.startswith(CONSTRAINTS)),
            "relabel_constraints": _relabel_constraints(policy, lines)}


def _verify_actor(policy, lines, exported, classes, expected, actor):
    if actor not in FIXED_OLD_ACTORS or expected["actor"] != actor:
        raise ValueError("Netplan changed the fixed original actor")
    if sorted(line for line in lines if line.startswith(CONSTRAINTS)) != expected["constraint_forms"]:
        raise ValueError("Netplan changed a complete existing MLS/relabel constraint")
    if _relabel_constraints(policy, lines) != expected["relabel_constraints"]:
        raise ValueError("Netplan changed the reachable relabel target predicates")
    actual_raw = _actor_raw(policy, lines, classes, actor)
    if actual_raw != expected["raw_vectors"]:
        raise ValueError("Netplan changed the fixed old actor complete raw TE boundary")
    raw_map = {(target, cls): set(names) for target, cls, names in actual_raw}
    additional = [[row["target"], row["class"],
                   sorted(_actor_extra(actor, row["target"], row["class"]) -
                          raw_map[(row["source"], row["class"])])]
                  for row in ALIASES if _actor_extra(actor, row["target"], row["class"])]
    if sorted(additional) != expected["additional_raw_permissions"]:
        raise ValueError("Netplan changed the measured fixed entry additions")
    declared = [[row["target"], row["class"],
                 sorted(_actor_extra(actor, row["target"], row["class"]))]
                for row in ALIASES if _actor_extra(actor, row["target"], row["class"])]
    if sorted(declared) != expected["declared_extra_permissions"]:
        raise ValueError("Netplan changed the declared fixed entry extras")
    checks = []
    for target, cls, level, wanted in expected["effective_vectors"]:
        actual = policy.context_av(_context("system_r", actor, level),
            _context("object_r", target), cls, classes[cls])
        if actual != wanted:
            raise ValueError("Netplan changed the fixed old actor object view: " + actor + " " + target)
        checks.append([actor, target, cls, level, actual])
    for old, new, cls, source_level, target_level, before, wanted in expected["mcs_vectors"]:
        for target, expected_vector in ((old, before), (new, wanted)):
            actual = policy.context_av(_context("system_r", actor, source_level),
                _context("object_r", target, target_level), cls, classes[cls])
            if actual != expected_vector:
                raise ValueError("Netplan changed a constrained fixed old actor alias view")
        checks.append([actor, old, new, cls, source_level, target_level, before, wanted])
    for row in ALIASES:
        for target in (row["source"], row["target"]):
            actual = original_xperms([exported], [actor], target,
                class_names=(row["class"],))[row["class"]]
            if actual != expected["xperms"][row["source"]][row["class"]]:
                raise ValueError("Netplan changed the fixed old actor complete ioctl mask")
    return checks


def derive(library, baseline, exported, here, output, export):
    contract(here)
    private_contract(here)
    expected = derive_preserved_aliases(
        library, baseline, exported, ALIASES, output, export,
        prefix="p4_netplan_preserved", isolated_roles={ROLE, *FIXED_OLD_ACTORS},
        extra_permissions={
            ("p4_linux_udev_t", LINK_DIR, "dir"): {"getattr", "open", "read", "search"},
            ("p4_linux_udev_t", RULE_DIR, "dir"): {"getattr", "open", "read", "search"},
        }, preamble=("; Preserve the original actors on fixed normal netplan inodes.",))
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    expected["normal_network_manager"] = _preserve_actor(
        policy, lines, exported, expected["classes"], output, NM_ROLE)
    expected["normal_native_consumers"] = {
        actor: _preserve_actor(policy, lines, exported, expected["classes"], output, actor)
        for actor in ("init_t", EXECUTOR)}
    expected["derived_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    expected["contract_sha256"] = hashlib.sha256((here / "native-netplan-source.json").read_bytes()).hexdigest()
    expected["private_contract_sha256"] = hashlib.sha256((here / "native-netplan-private-source.json").read_bytes()).hexdigest()
    return expected


def fixed_transitions():
    return {
        "(typetransition " + EXECUTOR + " " + ENTRY + " process " + ROLE + ")",
        '(typetransition ' + ROLE + ' p4_linux_run_t dir "NetworkManager" ' + NM_RUN + ')',
        "(typetransition " + ROLE + " " + NM_RUN + " dir " + DENIED_DIR + ")",
        '(typetransition ' + ROLE + ' ' + NM_RUN + ' dir "conf.d" ' + NM_RUN + ')',
        "(typetransition " + ROLE + " " + NM_RUN + " file " + OUTPUT + ")",
        '(typetransition ' + ROLE + ' ' + NM_RUN + ' dir "system-connections" ' + PROFILE_DIR + ')',
        "(typetransition " + ROLE + " " + PROFILE_DIR + " dir " + DENIED_DIR + ")",
        "(typetransition " + ROLE + " " + PROFILE_DIR + " file " + OUTPUT + ")",
        '(typetransition ' + ROLE + ' p4_linux_systemd_run_t dir "network" ' + LINK_DIR + ')',
        "(typetransition " + ROLE + " " + LINK_DIR + " dir " + DENIED_DIR + ")",
        "(typetransition " + ROLE + " " + LINK_DIR + " file " + GENERATED + ")",
        '(typetransition ' + ROLE + ' p4_linux_udev_run_t dir "rules.d" ' + RULE_DIR + ')',
        "(typetransition " + ROLE + " " + RULE_DIR + " dir " + DENIED_DIR + ")",
        "(typetransition " + ROLE + " " + RULE_DIR + " file " + GENERATED + ")",

    }


def verify(library, binary, exported, here, expected, export):
    value = contract(here)
    private = private_contract(here)
    if expected["private_contract_sha256"] != hashlib.sha256((here / "native-netplan-private-source.json").read_bytes()).hexdigest():
        raise ValueError("Netplan private contract changed during linking")
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    text = exported.read_text()
    classes = expected["classes"]
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    manager_checks = _verify_actor(policy, lines, exported, classes,
                                   expected["normal_network_manager"], NM_ROLE)
    checks.extend(manager_checks)
    if set(expected["normal_native_consumers"]) != {"init_t", EXECUTOR}:
        raise ValueError("Netplan fixed native consumer set changed")
    native_consumer_checks = {}
    for actor in ("init_t", EXECUTOR):
        native_consumer_checks[actor] = _verify_actor(policy, lines, exported, classes,
            expected["normal_native_consumers"][actor], actor)
        checks.extend(native_consumer_checks[actor])
    objects = sorted(set(re.findall(r"\(roletype object_r (\w+)\)", text)))
    actors = _roles(lines)
    def av(target, cls, wanted, target_role="object_r", actor=ROLE,
           actor_role="system_r", names=None):
        names = classes[cls] if names is None else names
        got = policy.context_av(_context(actor_role, actor), _context(target_role, target), cls, names)
        _, bits = policy.permissions(cls, names)
        actual = {n for n, bit in bits.items() if got & bit}
        if actual != set(wanted):
            raise ValueError("Netplan boundary differs: " + actor + " -> " +
                             target_role + ":" + target + " " + cls + " " +
                             repr(sorted(actual)) + "/" + repr(sorted(wanted)))
        checks.append([actor_role, actor, target_role, target, cls, sorted(wanted)])

    selected = {ROLE, ENTRY, LIBRARY, YAML, INPUT_DIR, OUTPUT, DENIED_DIR,
                PRIVATE_INPUT, PROFILE_DIR, LINK_DIR, RULE_DIR, GENERATED}
    observed = {line for line in lines if line.startswith(TRANSITIONS) and
                any(isinstance(token, str) and token in selected
                    for token in parse_expression(line)[1:])}
    wanted = {line for line in expected["transitions"] if line.startswith(TRANSITIONS)} | fixed_transitions()
    if observed != wanted:
        raise ValueError("Netplan executable or filename transition set changed")

    read = {"getattr", "open", "read"}
    executable = read | {"execute", "map"}
    file_access = {
        ENTRY: executable | {"entrypoint"}, LIBRARY: executable,
        SHARED_LIBRARY: executable, "p4_linux_elf_interpreter_t": executable,
        CACHE: read | {"map"}, YAML: read,
        OUTPUT: read | {"write", "create", "rename", "unlink", "setattr"},
        PRIVATE_INPUT: read, "p4_linux_public_accounts_t": read,
        "p4_linux_timesyncd_nsswitch_t": read,
        GENERATED: read | {"write", "create", "rename", "unlink", "setattr"},
    }
    directories = {
        "p4_linux_rootdir_t": {"getattr", "search"},
        "p4_linux_etc_dir_t": {"getattr", "search"},
        INPUT_DIR: {"getattr", "open", "read", "search"},
        "p4_linux_run_t": {"getattr", "search", "write", "add_name"},
        NM_RUN: {"getattr", "search", "create", "write", "add_name", "remove_name"},
        PROFILE_DIR: {"getattr", "search", "open", "read", "create", "write", "add_name", "remove_name"},
        LINK_DIR: {"getattr", "search", "open", "read", "create", "write", "add_name", "remove_name"},
        RULE_DIR: {"getattr", "search", "open", "read", "create", "write", "add_name", "remove_name"},
        "p4_linux_systemd_run_t": {"getattr", "search", "write", "add_name"},
        "p4_linux_udev_run_t": {"getattr", "search", "write", "add_name"},
        "sysfs": {"search"}, "selinuxfs": {"search"},
    }
    # These are explicit, source-owned alias sets, never a discovered directory
    # or an automatic permit for a previously unknown type.
    from derive_native_ldconfig_policy import ALIASES as LDCONFIG_ALIASES
    from derive_native_journal_catalog_policy import ALIASES as CATALOG_ALIASES
    from derive_native_update_done_policy import ALIASES as UPDATE_DONE_ALIASES
    for row in (console_contract(here)["aliases"] + SYSUSERS_ALIASES + LOGIND_ALIASES
                + TIMESYNC_ALIASES + LDCONFIG_ALIASES + CATALOG_ALIASES + KMOD_ALIASES + UPDATE_DONE_ALIASES):
        table = file_access if row["class"] == "file" else directories if row["class"] == "dir" else {}
        if row["source"] in table:
            table.setdefault(row["target"], set()).update(table[row["source"]])
    for target in objects:
        av(target, "file", file_access.get(target, set()))
        av(target, "dir", directories.get(target, set()))
        av(target, "lnk_file", {"getattr", "read"} if target in
           ("p4_linux_usrmerge_link_t", "p4_linux_timezone_link_t") else set())
        av(target, "chr_file", {"getattr", "read", "write"} if target in
           ("null_device", "p4_linux_standardio_t") else set())
        av(target, "blk_file", set())
        av(target, "filesystem", {"getattr"} if target == "selinuxfs" else set())
    for role, actor in actors:
        av(ROLE, "process", {"transition"} if actor == EXECUTOR else set(),
           target_role="system_r", actor=actor, actor_role=role,
           names=["transition", "dyntransition"])
        av(ROLE, "process2", {"nnp_transition"} if actor == EXECUTOR else set(),
           target_role="system_r", actor=actor, actor_role=role, names=["nnp_transition"])
        for cls in ("file", "dir", "lnk_file"):
            av(actor, cls, set(), target_role=role)
        av(actor, "process", {"sigchld"} if role == "system_r" and actor in
           ("init_t", EXECUTOR) else set(), target_role=role)
        av(actor, "fd", {"use"} if role == "system_r" and actor in
           (ROLE, EXECUTOR) else set(), target_role=role)
    for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
        av(ROLE, cls, set(), target_role="system_r")
    av("kernel", "security", set(), target_role="r")
    socket_classes = sorted(cls for cls in classes if cls == "socket" or cls.endswith("_socket"))
    for cls in socket_classes:
        for role, target in [("object_r", t) for t in objects] + actors:
            wanted = {"getattr", "read", "write"} if cls == "unix_stream_socket" and target == EXECUTOR else set()
            av(target, cls, wanted, target_role=role)
    return {
        "schema": "droidloom.native-netplan-policy-proof.v1",
        "source_contract_sha256": expected["contract_sha256"],
        "private_profile_contract_sha256": expected["private_contract_sha256"],
        "private_profile_selection": private["selection"],
        "private_profile_runtime_qualified": False,
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_transitions": len(expected["transitions"]),
        "normal_network_manager_raw_vectors": len(expected["normal_network_manager"]["raw_vectors"]),
        "normal_network_manager_effective_vectors": len(manager_checks),
        "normal_network_manager_mcs_vectors": len(expected["normal_network_manager"]["mcs_vectors"]),
        "normal_network_manager_extra_permissions": expected["normal_network_manager"]["declared_extra_permissions"],
        "normal_native_consumers": {
            actor: {
                "raw_vectors": len(expected["normal_native_consumers"][actor]["raw_vectors"]),
                "effective_vectors": len(native_consumer_checks[actor]),
                "mcs_vectors": len(expected["normal_native_consumers"][actor]["mcs_vectors"]),
                "declared_extra_permissions": expected["normal_native_consumers"][actor]["declared_extra_permissions"],
                "additional_raw_permissions": expected["normal_native_consumers"][actor]["additional_raw_permissions"],
            } for actor in ("init_t", EXECUTOR)},
        "whole_object_vector_checks": len(checks),
        "concrete_actors": len(actors), "concrete_objects": len(objects),
        "socket_classes": len(socket_classes), "elf_inputs": len(value["elf_paths"]),
        "shared_label_members": len(value["shared_library_paths"]),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "file_contexts": verify_file_contexts(here, exported.parent),
        "capabilities": [], "child_exec_allowed": False, "network_socket_creation_allowed": False,
        "selected_configuration": value["selected_configuration"],
        "other_yaml_profiles_qualified": False, "runtime_qualified": False,
    }


def verify_file_contexts(here, work):
    value = contract(here)
    path = work / "netplan-file-contexts"
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
        raise OSError(ctypes.get_errno(), "Cannot open normal netplan file contexts")
    checked = []
    def lookup(filename, mode):
        result = ctypes.c_char_p()
        if lib.selabel_lookup_raw(handle, ctypes.byref(result), filename.encode(), mode):
            raise OSError(ctypes.get_errno(), "Netplan file-context lookup failed")
        try:
            return result.value.decode().split(":")[2]
        finally:
            lib.freecon(result)
    try:
        for row in value["files"]:
            if lookup(row["path"], stat.S_IFREG) != row["target_type"]:
                raise ValueError("Netplan input file has a different label: " + row["path"])
            checked.append([row["path"], stat.S_IFREG, row["target_type"]])
        for row in value["directories"]:
            if lookup(row["path"], stat.S_IFDIR) != INPUT_DIR:
                raise ValueError("Netplan input directory label differs")
            checked.append([row["path"], stat.S_IFDIR, INPUT_DIR])
        private = private_contract(here)
        for row in private["profiles"]:
            if lookup(row["path"], stat.S_IFREG) != PRIVATE_INPUT:
                raise ValueError("Netplan private input file label differs")
            checked.append([row["path"], stat.S_IFREG, PRIVATE_INPUT])
        nss = "p4_linux_timesyncd_nsswitch_t"
        if lookup("/etc/nsswitch.conf", stat.S_IFREG) != nss:
            raise ValueError("Netplan public NSS input file label differs")
        checked.append(["/etc/nsswitch.conf", stat.S_IFREG, nss])
        for filename, wanted in [
                ("/run/NetworkManager/system-connections", PROFILE_DIR),
                ("/run/systemd/network", LINK_DIR),
                ("/run/udev/rules.d", RULE_DIR)]:
            if lookup(filename, stat.S_IFDIR) != wanted:
                raise ValueError("Netplan runtime output directory label differs")
            checked.append([filename, stat.S_IFDIR, wanted])
        for filename, mode, wanted in [
            (OUTPUT_PATH, stat.S_IFREG, OUTPUT),
            ("/run/NetworkManager/conf.d/netplan.conf", stat.S_IFREG, OUTPUT),
            ("/run/NetworkManager/conf.d/netplan.conf.2EQNZ3", stat.S_IFREG, OUTPUT),
            ("/run/NetworkManager/system-connections/netplan-selected.nmconnection", stat.S_IFREG, OUTPUT),
            ("/run/NetworkManager/system-connections/netplan-selected.nmconnection.2EQNZ3", stat.S_IFREG, OUTPUT),
            ("/run/NetworkManager/system-connections/other.nmconnection", stat.S_IFREG, NM_RUN),
            ("/run/systemd/network/10-netplan-selected.link", stat.S_IFREG, GENERATED),
            ("/run/systemd/network/10-netplan-selected.link.2EQNZ3", stat.S_IFREG, GENERATED),
            ("/run/systemd/network/other.link", stat.S_IFREG, "p4_linux_native_data_t"),
            ("/run/udev/rules.d/90-netplan.rules", stat.S_IFREG, GENERATED),
            ("/run/udev/rules.d/90-netplan.rules.2EQNZ3", stat.S_IFREG, GENERATED),
            ("/run/udev/rules.d/other.rules", stat.S_IFREG, "p4_linux_native_data_t"),

            (OUTPUT_PATH + ".2EQNZ3", stat.S_IFREG, OUTPUT),
            ("/usr/libexec/netplan/generate", stat.S_IFREG, "p4_linux_generator_exec_t"),
            ("/usr/libexec/netplan/configure-extra", stat.S_IFREG, "p4_linux_native_bin_t"),
            ("/usr/lib/netplan/new.yaml", stat.S_IFREG, "p4_linux_runtime_lib_t"),
            ("/etc/netplan/new.yaml", stat.S_IFREG, "p4_linux_native_config_t"),
            (OUTPUT_PATH + ".outside", stat.S_IFREG, NM_RUN),
            ("/run/NetworkManager/conf.d/unselected.conf", stat.S_IFREG, NM_RUN),
            ("/run/NetworkManager/private", stat.S_IFREG, NM_RUN),
        ]:
            if lookup(filename, mode) != wanted:
                raise ValueError("Netplan path matcher selected an unadmitted file")
            checked.append([filename, mode, wanted])
        selected_file_types = {ENTRY, LIBRARY, YAML, PRIVATE_INPUT, OUTPUT, GENERATED}
        selected_file_paths = [
            row["path"] for row in value["files"]
            if row["target_type"] in {ENTRY, LIBRARY, YAML}]
        selected_file_paths += [row["path"] for row in private["profiles"]]
        selected_file_paths += ["/etc/nsswitch.conf",
            "/run/NetworkManager/conf.d/netplan.conf",
            "/run/NetworkManager/system-connections/netplan-selected.nmconnection",
            "/run/systemd/network/10-netplan-selected.link",
            "/run/udev/rules.d/90-netplan.rules"]
        for filename in selected_file_paths:
            for mode in (stat.S_IFDIR, stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK):
                try:
                    actual = lookup(filename, mode)
                except OSError as error:
                    if error.errno != 2:
                        raise
                    actual = None
                if actual in selected_file_types:
                    raise ValueError("Netplan file label accepted another inode class")
                checked.append([filename, mode, actual])
    finally:
        lib.selabel_close(handle)
    return {"selected_and_negative_cases": len(checked),
            "matrix_sha256": hashlib.sha256(json.dumps(checked, sort_keys=True).encode()).hexdigest()}
