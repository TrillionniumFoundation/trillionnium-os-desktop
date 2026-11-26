"""Preserve native policy while admitting the existing normal sysusers lock.

This extends the normal strict policy producer. It neither runs sysusers nor
creates/edits the passwd, group, shadow or lock inodes.
"""
import ctypes
import hashlib
import json
import re
import stat

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import (
    _context, derive_preserved_aliases, verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression, original_xperms

ROLE = "p4_linux_setup_t"
ETC = "p4_linux_sysusers_etc_root_t"
LOCK = "p4_linux_sysusers_passwd_lock_t"
ALIASES = [
    {"source": "p4_linux_etc_dir_t", "target": ETC, "class": "dir"},
    {"source": "p4_linux_native_config_t", "target": LOCK, "class": "file"},
]
EXTRA = {(ROLE, ETC, "dir"): {"write"},
         (ROLE, LOCK, "file"): {"write", "lock"}}
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
SOURCE_FILES = {
    "src/basic/user-util.c": (42576, "d24df80e7a5b91aa0bdc1740a3d9e12a3444758662fa04d89dbed11e86ba2085"),
    "src/basic/user-util.h": (6868, "53840302cac35c769790eeb7215c9aa07b592e9b1b5eb74806c494a53370046c"),
    "src/basic/lock-util.c": (8888, "e0d3430e14a01bb5eac811838d0f1663dfbc551ae3863f185250fbf821682727"),
    "src/sysusers/sysusers.c": (93671, "caf81b4091e9ffdbfabdf6ca1d81450b45d74ede6b6498bb68f441b844ed71a5"),
}
NORMAL_FILES = {
    "/usr/bin/systemd-sysusers": (68224, "a042bcaba44058f73f73d26fc998b6da4bd64a0788e8f65ddde22ee1e18a384c", 0o755, "p4_linux_setup_exec_t"),
    "/usr/lib/systemd/system/systemd-sysusers.service": (1310, "22c1aa54692be4fc17b11c0e77230d88cae5d10794def3b4a9d6070f299a6165", 0o644, "p4_linux_unit_file_t"),
}


def contract(here):
    value = json.loads((here / "native-sysusers-source.json").read_text())
    if (set(value) != {"schema", "package", "version", "aliases", "normal_files",
                       "source_documents", "existing_objects", "runtime_qualified"}
            or value["schema"] != "droidloom.native-sysusers-lock-source.v1"
            or value["package"] != "systemd:amd64"
            or value["version"] != "259.9-0ubuntu0.1+p4gentmp2"
            or value["aliases"] != ALIASES or value["runtime_qualified"] is not False):
        raise ValueError("Unexpected normal sysusers source contract")
    sources = value["source_documents"]
    if (len(sources) != len(SOURCE_FILES) or
            {row.get("path") for row in sources} != set(SOURCE_FILES)):
        raise ValueError("Incomplete normal sysusers source closure")
    for row in sources:
        if (set(row) != {"path", "bytes", "sha256", "admission"} or
                (row["bytes"], row["sha256"]) != SOURCE_FILES[row["path"]] or
                row["admission"] != "normal-dsc-roundtrip"):
            raise ValueError("Sysusers source is not the selected normal roundtrip")
    files = value["normal_files"]
    if (len(files) != len(NORMAL_FILES) or
            {row.get("path") for row in files} != set(NORMAL_FILES)):
        raise ValueError("Incomplete normal sysusers executable/unit closure")
    for row in files:
        if (set(row) != {"path", "bytes", "sha256", "mode", "uid", "gid", "nlink", "type"}
                or (row["bytes"], row["sha256"], row["mode"], row["type"]) != NORMAL_FILES[row["path"]]
                or (row["uid"], row["gid"], row["nlink"]) != (0, 0, 1)):
            raise ValueError("Unexpected normal sysusers executable metadata")
    if value["existing_objects"] != [
            {"path": "/etc", "class": "dir", "mode": 0o755,
             "uid": 0, "gid": 0, "source_type": ALIASES[0]["source"], "target_type": ETC},
            {"path": "/etc/.pwd.lock", "class": "file", "mode": 0o600,
             "uid": 0, "gid": 0, "nlink": 1, "bytes": 0,
             "sha256": hashlib.sha256(b"").hexdigest(),
             "source_type": ALIASES[1]["source"], "target_type": LOCK}]:
        raise ValueError("The sysusers exception is only an existing empty lock below /etc")
    return value


def derive(library, baseline, exported, here, output, export):
    value = contract(here)
    expected = derive_preserved_aliases(library, baseline, exported, ALIASES,
        output, export, prefix="p4_sysusers_preserved", isolated_roles={ROLE, "p4_linux_ldconfig_t"},
        extra_permissions={}, preamble=(
            "; Preserve every other existing actor; setup has a separate full proof.",
            "; Only /etc:dir write and existing .pwd.lock:file write/lock differ."))
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    objects = sorted(set(re.findall(r"\(roletype object_r (\w+)\)", "\n".join(lines))))
    # Record the setup role's complete file/directory vectors over every object,
    # not just successful lock operations. No other target may change.
    vectors = []
    for target in objects:
        for cls in ("file", "dir"):
            alias = next((row for row in ALIASES if
                          (row["target"], row["class"]) == (target, cls)), None)
            source = alias["source"] if alias else target
            names = expected["classes"][cls]
            for level in LEVELS:
                context = _context("system_r", ROLE, level)
                before = policy.context_av(context, _context("object_r", source), cls, names)
                # The explicit new write/lock edge remains subject to the same
                # complete MLS constraints; do not OR an unconstrained bit.
                preimage = policy.context_av(context, _context("object_r", target), cls, names)
                vectors.append([target, cls, level, before | preimage])
    expected["setup_vectors"] = vectors
    expected["setup_raw_vectors"] = _setup_raw_vectors(policy, lines, expected["classes"])
    expected["setup_mcs_vectors"] = []
    for row in ALIASES:
        for source_level in LEVELS:
            for target_level in LEVELS:
                context = _context("system_r", ROLE, source_level)
                old = policy.context_av(context, _context("object_r", row["source"], target_level),
                                        row["class"], expected["classes"][row["class"]])
                new = policy.context_av(context, _context("object_r", row["target"], target_level),
                                        row["class"], expected["classes"][row["class"]])
                expected["setup_mcs_vectors"].append([row["source"], row["target"], row["class"],
                                                    source_level, target_level, old, new])
    expected["setup_xperms"] = {
        row["source"]: original_xperms([exported], [ROLE], row["source"],
                                      class_names=(row["class"],))[row["class"]]
        for row in ALIASES}
    expected["all_constraint_forms"] = sorted(line for line in lines if line.startswith(CONSTRAINTS))
    expected["relabel_constraint_proof"] = _relabel_constraints(policy, lines)

    expected["transition_forms"] = sorted(line for line in lines if line.startswith(TRANSITIONS))
    expected["contract_sha256"] = hashlib.sha256(
        (here / "native-sysusers-source.json").read_bytes()).hexdigest()
    return expected


def _setup_raw_vectors(policy, lines, classes):
    """Prove the existing actor's exact raw TE additions before MLS filtering.

    Both original and new object views have no relabel permission for setup.
    Their unchanged validatetrans rules therefore cannot authorize a new
    relabel. Other actors keep the common alias library's original proof.
    """
    text = "\n".join(lines)
    if re.search(r"\((?:booleanif|tunableif|typebounds)\b", text):
        raise ValueError("Sysusers lock needs unconditional, unbounded TE roles")
    members = Membership(text)
    read = {"dir": {"getattr", "open", "read", "search"},
            "file": {"getattr", "open", "read", "map"}}
    result = []
    for row in ALIASES:
        cls = row["class"]
        for target, wanted in ((row["source"], read[cls]),
                               (row["target"], read[cls] | EXTRA[(ROLE, row["target"], cls)])):
            actual = set()
            count = 0
            for line in lines:
                if not line.startswith("(allow "):
                    continue
                count += 1
                form = parse_expression(line)
                if len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2:
                    raise ValueError("Unmodeled sysusers raw TE rule")
                source, object_type, rule = form[1:]
                rule_class, permissions = rule
                if (rule_class not in classes or not isinstance(permissions, list) or
                        not set(permissions).issubset(classes[rule_class])):
                    raise ValueError("Unknown sysusers raw TE permission")
                if (rule_class == cls and members.member(source, ROLE) and
                        ((object_type == "self" and target == ROLE) or
                         (object_type != "self" and members.member(object_type, target)))):
                    actual.update(permissions)
            if count != text.count("(allow ") or actual != wanted:
                raise ValueError("Sysusers raw TE differs from exact read plus lock: " + target)
            result.append([target, cls, sorted(actual)])
    return result


def _relabel_constraints(policy, lines):
    """Keep the exact existing class constraints and their reachable boundary.

    The file guard has identical target-type predicates for the two aliases.
    The directory guard also contains t1==t2; its sole guarded hardware actor
    is separately forbidden, by actual neverallows and AV checks, from both
    source/alias relabel directions. For every other actor that guard is true.
    No unmodeled class/actor/type-identity constraint is silently dropped.
    """
    members = Membership("\n".join(lines))
    proof = []
    selected = [line for line in lines if line.startswith(("(validatetrans ", "(mlsvalidatetrans "))]
    for line in selected:
        form = parse_expression(line)
        if len(form) != 3:
            raise ValueError("Unmodeled native relabel constraint")
        cls, expression = form[1:]
        if cls not in ("file", "dir"):
            continue
        actor = {"file": "p4_linux_uevent_label_t", "dir": "p4_linux_hardware_label_t"}[cls]
        if (form[0] != "validatetrans" or not isinstance(expression, list) or
                len(expression) != 3 or expression[:2] != ["or", ["neq", "t3", actor]]):
            raise ValueError("Selected sysusers class has an unmodeled relabel actor")
        row = next(row for row in ALIASES if row["class"] == cls)
        for target in (row["source"], row["target"]):
            for source_level in LEVELS:
                for target_level in LEVELS:
                    if policy.context_av(_context("system_r", actor, source_level),
                            _context("object_r", target, target_level), cls,
                            ["relabelfrom", "relabelto"]):
                        raise ValueError("A class-constrained relabel actor can reach a sysusers alias")
        if cls == "dir":
            if expression[2] != ["or", ["eq", "t1", "device"], ["eq", "t1", "t2"]]:
                raise ValueError("Hardware directory relabel predicate changed")
        else:
            def target_atoms(expr, target):
                if not isinstance(expr, list):
                    return expr
                if len(expr) == 3 and expr[0] in ("eq", "neq") and "t2" in expr[1:]:
                    other = expr[2] if expr[1] == "t2" else expr[1]
                    if other in ("t1", "t2", "t3"):
                        raise ValueError("Unmodeled sysusers file relabel identity predicate")
                    equal = members.member(other, target)
                    return equal if expr[0] == "eq" else not equal
                return [target_atoms(child, target) for child in expr]
            if target_atoms(expression, row["source"]) != target_atoms(expression, row["target"]):
                raise ValueError("Sysusers alias changed a file relabel target predicate")
        proof.append({"class": cls, "guarded_actor": actor, "source_type": row["source"],
                      "alias_type": row["target"], "relabel_from_and_to": False,
                      "constraint_sha256": hashlib.sha256(line.encode()).hexdigest()})
    if len(proof) != 2 or {row["class"] for row in proof} != {"dir", "file"}:
        raise ValueError("The exact existing hardware and uevent relabel guards are required")
    # Binary export order is not semantic; bind each complete form by class.
    return sorted(proof, key=lambda row: row["class"])


def verify(library, binary, exported, here, expected, export):
    contract(here)
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    # The common library checks ordinary/MLS constraints; this consumer also
    # binds every complete validatetrans form, without weakening its guard.
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    if sorted(line for line in lines if line.startswith(CONSTRAINTS)) != expected["all_constraint_forms"]:
        raise ValueError("Sysusers changed a complete existing MLS/relabel constraint")
    if _relabel_constraints(policy, lines) != expected["relabel_constraint_proof"]:
        raise ValueError("Sysusers changed reachable relabel constraint predicates")
    if _setup_raw_vectors(policy, lines, expected["classes"]) != expected["setup_raw_vectors"]:
        raise ValueError("Sysusers raw permissions changed after alias derivation")
    for old, new, cls, source_level, target_level, before, after in expected["setup_mcs_vectors"]:
        context = _context("system_r", ROLE, source_level)
        for target, wanted in ((old, before), (new, after)):
            if policy.context_av(context, _context("object_r", target, target_level),
                                 cls, expected["classes"][cls]) != wanted:
                raise ValueError("Sysusers changed constrained source/target access")
        checks.append([ROLE, old, new, cls, source_level, target_level, before, after])
    for row in ALIASES:
        for target in (row["source"], row["target"]):
            actual = original_xperms([exported], [ROLE], target, class_names=(row["class"],))[row["class"]]
            if actual != expected["setup_xperms"][row["source"]]:
                raise ValueError("Sysusers changed original ioctl filters")
    current = {line for line in lines if line.startswith(TRANSITIONS)}
    if current != set(expected["transition_forms"]) | set(expected["transitions"]):
        raise ValueError("Existing sysusers lock acquired an unrelated transition")
    for target, cls, level, wanted in expected["setup_vectors"]:
        actual = policy.context_av(_context("system_r", ROLE, level),
                                   _context("object_r", target), cls, expected["classes"][cls])
        if actual != wanted:
            raise ValueError("Sysusers changed another setup access vector: " + target + " " + cls)
        checks.append([ROLE, target, cls, level, actual])
    # A missing lock must still fail: write on an existing directory is not
    # add_name/create. The account/credential databases remain read-only.
    negatives = [
        (ETC, "dir", ["create", "add_name", "remove_name", "setattr", "rename", "rmdir", "mounton", "relabelfrom", "relabelto"]),
        (LOCK, "file", ["create", "append", "setattr", "unlink", "link", "rename", "execute", "execute_no_trans", "entrypoint", "ioctl", "relabelfrom", "relabelto"]),
        ("p4_linux_etc_dir_t", "dir", ["write", "add_name", "remove_name", "relabelfrom", "relabelto"]),
    ]
    for target in ("p4_linux_public_accounts_t", "p4_linux_auth_data_t", "p4_linux_native_config_t"):
        negatives.append((target, "file", ["write", "append", "create", "setattr", "unlink", "link", "rename", "relabelfrom", "relabelto"]))
    for target, cls, names in negatives:
        for level in LEVELS:
            if policy.context_av(_context("system_r", ROLE, level), _context("object_r", target), cls, names):
                raise ValueError("Sysusers gained lock creation or account mutation: " + target)
            checks.append([ROLE, target, cls, level, names, 0])
    startup_writes = []
    for row in ALIASES:
        _, bits = policy.permissions(row["class"], ["write"])
        for level in LEVELS:
            actual = policy.context_av(_context("system_r", ROLE, level),
                _context("object_r", row["target"]), row["class"], ["write"])
            if actual != (bits["write"] if level == "s0" else 0):
                raise ValueError("Sysusers write escaped its normal s0 startup category")
            startup_writes.append([level, row["target"], row["class"], actual])
    return {
        "schema": "droidloom.native-sysusers-lock-policy-proof.v1",
        "source_contract_sha256": expected["contract_sha256"],
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "alias_preserver_sha256": hashlib.sha256((here / "derive_preserved_alias_policy.py").read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256((here / "derive_native_sysusers_policy.py").read_bytes()).hexdigest(),
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_transitions": len(expected["transitions"]),
        "setup_raw_te_vectors": expected["setup_raw_vectors"],
        "setup_mcs_source_target_samples": len(expected["setup_mcs_vectors"]),
        "all_ranges_constraint_target_checks": expected["constraint_target_checks"],
        "relabel_constraints": expected["relabel_constraint_proof"],
        "complete_setup_vectors": len(expected["setup_vectors"]),
        "extra_permissions": [[*key, sorted(names)] for key, names in sorted(EXTRA.items())],
        "startup_write_vectors": startup_writes,
        "file_contexts": verify_file_contexts(here, exported.parent),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "runtime_qualified": False,
    }


def verify_file_contexts(here, work):
    """Use the normal class-aware matcher on exact and adjacent pathnames."""
    value = contract(here)
    path = work / "sysusers-file-contexts"
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
        raise OSError(ctypes.get_errno(), "Cannot open sysusers file-context matcher")
    checks = []
    def lookup(filename, mode):
        result = ctypes.c_char_p()
        if lib.selabel_lookup_raw(handle, ctypes.byref(result), filename.encode(), mode):
            if ctypes.get_errno() == 2:
                return None
            raise OSError(ctypes.get_errno(), "Sysusers context lookup failed: " + filename)
        try:
            return result.value.decode().split(":")[2]
        finally:
            lib.freecon(result)
    try:
        modes = (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK)
        for filename, selected, wanted in (("/etc", stat.S_IFDIR, ETC), ("/etc/.pwd.lock", stat.S_IFREG, LOCK)):
            for mode in modes:
                actual = lookup(filename, mode)
                if ((mode == selected and actual != wanted) or
                        (mode != selected and actual in (ETC, LOCK))):
                    raise ValueError("Sysusers alias escaped its exact inode class: " + filename)
                checks.append([filename, mode, actual])
        for filename, mode, wanted in [
            ("/etc/selinux", stat.S_IFDIR, "p4_linux_etc_dir_t"),
            ("/etc/selinux/droidloom", stat.S_IFDIR, "p4_linux_etc_dir_t"),
            ("/etc/selinux/droidloom/contexts/files", stat.S_IFDIR, "p4_linux_etc_dir_t"),
            ("/etc/passwd", stat.S_IFREG, "p4_linux_public_accounts_t"),
            ("/etc/group", stat.S_IFREG, "p4_linux_public_accounts_t"),
            ("/etc/shadow", stat.S_IFREG, "p4_linux_auth_data_t"),
            ("/etc/gshadow", stat.S_IFREG, "p4_linux_auth_data_t"),
            *((name, stat.S_IFREG, "p4_linux_native_config_t") for name in
              ("/etc/.pwd.lock.extra", "/etc/.pwdXlock", "/etc/pwd.lock", "/etc/.pwd.lock-",
               "/etc/sub/.pwd.lock", "/etc/.pwd.lock/child")),
        ]:
            actual = lookup(filename, mode)
            if actual != wanted:
                raise ValueError("Sysusers alias changed an unrelated path: " + filename)
            checks.append([filename, mode, actual])
        for row in value["normal_files"]:
            if lookup(row["path"], stat.S_IFREG) != row["type"]:
                raise ValueError("Existing sysusers service entry label changed")
            checks.append([row["path"], stat.S_IFREG, row["type"]])
    finally:
        lib.selabel_close(handle)
    return {"selected_and_negative_cases": len(checks),
            "matrix_sha256": hashlib.sha256(json.dumps(checks).encode()).hexdigest()}
