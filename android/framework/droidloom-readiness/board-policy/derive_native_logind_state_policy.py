"""Preserve the original parent while admitting normal logind StateDirectory.

This is a component of the existing strict producer. It never creates a host
directory, executes a service, changes a distribution unit or loads policy.
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

ROLE = "p4_linux_service_executor_t"
PARENT = "p4_linux_systemd_state_parent_t"
STATE = "p4_linux_logind_state_t"
ALIASES = [{"source": "p4_linux_rootdir_t", "target": PARENT, "class": "dir"}]
ORIGINAL = {"getattr", "search", "mounton"}
ADDITIONS = {"write", "add_name"}
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
SOURCE_FILES = {
    "src/core/executor.c": (11487, "3cc97598a5d6bc2f0c78f971c5b9a5151ba47ace976ca01395a47453f99abafb"),
    "src/core/exec-invoke.c": (276788, "24eda88ee0914d0c43d30ebfb13f0f3aadd00391b5820fb6d6509278f0925dfe"),
    "src/core/execute.c": (111938, "3fdc25491919ccbe96812a8d56d20e34bbf367a29555b304b5fa0b06838c8a26"),
    "src/basic/mkdir.c": (9880, "88a9ce00bc2c05c0c5d329653c29846622356efcbc207639a5877b323d102756"),
    "src/shared/mkdir-label.c": (1389, "cb5470df867959d3668f22c41ef2d6a514e996f6c2348b8eee3f1c07800d6e5a"),
    "src/shared/selinux-util.c": (25770, "241a1cdb353d954a1a771e4b33709860a2df729bb7512130b5fb985fe1105df7"),
    "src/basic/fs-util.c": (52249, "de38f495f3be7fc9e80051487bac1242c71f2f38cffa4fba2d8f11380d3794d4"),
}
NORMAL_FILES = {
    "/usr/lib/systemd/systemd-executor": (154176, "afdc9afa0073871b5b303c7eae2857da727abec5d9cfa5bcb63df96ac53da12f", 0o755, "p4_linux_systemd_executor_t"),
    "/usr/lib/systemd/systemd-logind": (338512, "37761fa22f4afd30d13bcfa90df3917681180f5c63d8fa534d493f716208aa6d", 0o755, "p4_linux_logind_exec_t"),
    "/usr/lib/systemd/system/systemd-logind.service": (2088, "37563c6df1a510141bfd0777c20dfcc1c17087cdb56d3f71971a57d3cd380e64", 0o644, "p4_linux_unit_file_t"),
}


def contract(here):
    value = json.loads((here / "native-logind-state-source.json").read_text())
    if (set(value) != {"schema", "package", "version", "aliases", "normal_files",
                       "source_documents", "parent", "state_directory", "runtime_qualified"}
            or value["schema"] != "droidloom.native-logind-state-source.v1"
            or value["package"] != "systemd:amd64"
            or value["version"] != "259.9-0ubuntu0.1+p4gentmp2"
            or value["aliases"] != ALIASES or value["runtime_qualified"] is not False):
        raise ValueError("Unexpected normal logind directory source contract")
    sources = value["source_documents"]
    if (len(sources) != len(SOURCE_FILES) or
            {row.get("path") for row in sources} != set(SOURCE_FILES)):
        raise ValueError("Incomplete normal logind source closure")
    for row in sources:
        if (set(row) != {"path", "bytes", "sha256", "admission"} or
                (row["bytes"], row["sha256"]) != SOURCE_FILES[row["path"]] or
                row["admission"] != "normal-dsc-roundtrip"):
            raise ValueError("Logind source is not the selected normal roundtrip")
    files = value["normal_files"]
    if (len(files) != len(NORMAL_FILES) or
            {row.get("path") for row in files} != set(NORMAL_FILES)):
        raise ValueError("Incomplete normal executor/logind/unit closure")
    for row in files:
        if (set(row) != {"path", "bytes", "sha256", "mode", "uid", "gid", "nlink", "type"}
                or (row["bytes"], row["sha256"], row["mode"], row["type"]) != NORMAL_FILES[row["path"]]
                or (row["uid"], row["gid"], row["nlink"]) != (0, 0, 1)):
            raise ValueError("Unexpected normal logind executable metadata")
    if value["parent"] != {"path": "/var/lib/systemd", "class": "dir", "mode": 0o755,
            "uid": 0, "gid": 0, "source_type": ALIASES[0]["source"], "target_type": PARENT}:
        raise ValueError("Logind parent alias must select one existing directory")
    if value["state_directory"] != {
            "unit": "systemd-logind.service", "setting": "StateDirectory=systemd/linger",
            "path": "/var/lib/systemd/linger", "type": STATE, "mode": 0o755,
            "uid": 0, "gid": 0, "creator": ROLE, "operation": "mkdir_label",
            "normal_mode_and_ownership": "unchanged", "fallback_transition": False}:
        raise ValueError("Logind directory must follow the unmodified normal unit")
    return value


def _executor_raw(lines, classes):
    text = "\n".join(lines)
    if re.search(r"\((?:booleanif|tunableif|typebounds)\b", text):
        raise ValueError("Logind directory needs unconditional unbounded TE roles")
    members = Membership(text)
    result = []
    for target, wanted in ((ALIASES[0]["source"], ORIGINAL), (PARENT, ORIGINAL | ADDITIONS)):
        actual, count = set(), 0
        for line in lines:
            if not line.startswith("(allow "):
                continue
            count += 1
            form = parse_expression(line)
            if len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2:
                raise ValueError("Unmodeled logind raw TE rule")
            source, object_type, (cls, names) = form[1:]
            if cls not in classes or not isinstance(names, list) or not set(names).issubset(classes[cls]):
                raise ValueError("Unknown logind raw TE permission")
            if (cls == "dir" and members.member(source, ROLE) and
                    ((object_type == "self" and target == ROLE) or
                     (object_type != "self" and members.member(object_type, target)))):
                actual.update(names)
        if count != text.count("(allow ") or actual != wanted:
            raise ValueError("Logind parent raw vector is not exact: " + target)
        result.append([target, "dir", sorted(actual)])
    return result


def _relabel_constraint(policy, lines):
    forms = [line for line in lines if line.startswith(("(validatetrans ", "(mlsvalidatetrans "))
             and parse_expression(line)[1] == "dir"]
    wanted = ["validatetrans", "dir", ["or", ["neq", "t3", "p4_linux_hardware_label_t"],
                ["or", ["eq", "t1", "device"], ["eq", "t1", "t2"]]]]
    if len(forms) != 1 or parse_expression(forms[0]) != wanted:
        raise ValueError("Normal hardware directory relabel constraint changed")
    for target in (ALIASES[0]["source"], PARENT):
        for source_level in LEVELS:
            for target_level in LEVELS:
                if policy.context_av(_context("system_r", "p4_linux_hardware_label_t", source_level),
                        _context("object_r", target, target_level), "dir", ["relabelfrom", "relabelto"]):
                    raise ValueError("Hardware actor can reach a logind parent relabel")
    return {"class": "dir", "guarded_actor": "p4_linux_hardware_label_t",
            "source_type": ALIASES[0]["source"], "alias_type": PARENT,
            "constraint_sha256": hashlib.sha256(forms[0].encode()).hexdigest(),
            "relabel_from_and_to": False}


def derive(library, baseline, exported, here, output, export):
    contract(here)
    expected = derive_preserved_aliases(library, baseline, exported, ALIASES,
        output, export, prefix="p4_logind_parent_preserved", isolated_roles={ROLE},
        extra_permissions={}, preamble=(
            "; Preserve every original actor; executor has a separate complete proof.",
            "; Only its exact /var/lib/systemd parent write/add_name bits differ."))
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    objects = sorted(set(re.findall(r"\(roletype object_r (\w+)\)", "\n".join(lines))))
    expected["executor_vectors"] = []
    for target in objects:
        for cls in ("file", "dir"):
            old = ALIASES[0]["source"] if (target, cls) == (PARENT, "dir") else target
            for level in LEVELS:
                source = _context("system_r", ROLE, level)
                before = policy.context_av(source, _context("object_r", old), cls, expected["classes"][cls])
                preimage = policy.context_av(source, _context("object_r", target), cls, expected["classes"][cls])
                expected["executor_vectors"].append([target, cls, level, before | preimage])
    expected["executor_raw_vectors"] = _executor_raw(lines, expected["classes"])
    expected["executor_mcs_vectors"] = []
    for source_level in LEVELS:
        for target_level in LEVELS:
            source = _context("system_r", ROLE, source_level)
            expected["executor_mcs_vectors"].append([source_level, target_level,
                *[policy.context_av(source, _context("object_r", target, target_level),
                    "dir", expected["classes"]["dir"]) for target in (ALIASES[0]["source"], PARENT)]])
    expected["executor_xperms"] = original_xperms([exported], [ROLE], ALIASES[0]["source"],
                                                class_names=("dir",))["dir"]
    expected["all_constraint_forms"] = sorted(line for line in lines if line.startswith(CONSTRAINTS))
    expected["relabel_constraint_proof"] = _relabel_constraint(policy, lines)
    expected["transition_forms"] = sorted(line for line in lines if line.startswith(TRANSITIONS))
    expected["contract_sha256"] = hashlib.sha256((here / "native-logind-state-source.json").read_bytes()).hexdigest()
    return expected


def verify(library, binary, exported, here, expected, export):
    contract(here)
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    if sorted(line for line in lines if line.startswith(CONSTRAINTS)) != expected["all_constraint_forms"]:
        raise ValueError("Logind parent changed a complete existing MLS/relabel constraint")
    if _relabel_constraint(policy, lines) != expected["relabel_constraint_proof"]:
        raise ValueError("Logind parent changed reachable relabel predicates")
    if _executor_raw(lines, expected["classes"]) != expected["executor_raw_vectors"]:
        raise ValueError("Logind parent changed raw executor access")
    for source_level, target_level, before, after in expected["executor_mcs_vectors"]:
        for target, wanted in ((ALIASES[0]["source"], before), (PARENT, after)):
            actual = policy.context_av(_context("system_r", ROLE, source_level),
                _context("object_r", target, target_level), "dir", expected["classes"]["dir"])
            if actual != wanted:
                raise ValueError("Logind parent changed constrained category access")
        checks.append([ROLE, source_level, target_level, before, after])
    for target in (ALIASES[0]["source"], PARENT):
        if original_xperms([exported], [ROLE], target, class_names=("dir",))["dir"] != expected["executor_xperms"]:
            raise ValueError("Logind parent changed executor ioctl filters")
    if ({line for line in lines if line.startswith(TRANSITIONS)} !=
            set(expected["transition_forms"]) | set(expected["transitions"])):
        raise ValueError("Logind parent changed an unrelated or fallback transition")
    for target, cls, level, wanted in expected["executor_vectors"]:
        actual = policy.context_av(_context("system_r", ROLE, level),
            _context("object_r", target), cls, expected["classes"][cls])
        if actual != wanted:
            raise ValueError("Logind parent changed another executor object: " + target + " " + cls)
        checks.append([ROLE, target, cls, level, actual])
    negatives = [
        (PARENT, "dir", set(expected["classes"]["dir"]) - ORIGINAL - ADDITIONS),
        (PARENT, "file", expected["classes"]["file"]),
        (ALIASES[0]["source"], "dir", ["write", "add_name", "remove_name", "create", "setattr", "rename", "rmdir", "relabelfrom", "relabelto"]),
        (STATE, "file", ["open", "read", "write", "append", "create", "setattr", "unlink", "rename"]),
    ]
    for target, cls, names in negatives:
        for level in LEVELS:
            if policy.context_av(_context("system_r", ROLE, level), _context("object_r", target), cls, names):
                raise ValueError("Logind parent acquired unrelated mutation/body access: " + target)
            checks.append([ROLE, target, cls, level, sorted(names), 0])
    startup = []
    for level in LEVELS:
        got = policy.context_av(_context("system_r", ROLE, level), _context("object_r", PARENT), "dir", sorted(ADDITIONS))
        _, bits = policy.permissions("dir", sorted(ADDITIONS))
        if got != (sum(bits.values()) if level == "s0" else 0):
            raise ValueError("Logind parent write escaped its normal startup category")
        startup.append([level, got])
    existing = {"getattr", "search", "open", "read", "create", "setattr"}
    got = policy.context_av(_context("system_r", ROLE), _context("object_r", STATE), "dir", expected["classes"]["dir"])
    _, bits = policy.permissions("dir", sorted(existing))
    if got != sum(bits.values()):
        raise ValueError("Existing normal logind directory metadata permissions changed")
    return {"schema": "droidloom.native-logind-state-policy-proof.v1",
        "source_contract_sha256": expected["contract_sha256"],
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "alias_preserver_sha256": hashlib.sha256((here / "derive_preserved_alias_policy.py").read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256((here / "derive_native_logind_state_policy.py").read_bytes()).hexdigest(),
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_transitions": len(expected["transitions"]),
        "executor_raw_te_vectors": expected["executor_raw_vectors"],
        "executor_mcs_source_target_samples": len(expected["executor_mcs_vectors"]),
        "all_ranges_constraint_target_checks": expected["constraint_target_checks"],
        "relabel_constraint": expected["relabel_constraint_proof"],
        "complete_executor_vectors": len(expected["executor_vectors"]),
        "extra_permissions": [[ROLE, PARENT, "dir", sorted(ADDITIONS)]],
        "startup_write_vectors": startup,
        "normal_state_directory_permissions": sorted(existing),
        "file_contexts": verify_file_contexts(here, exported.parent),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "runtime_qualified": False}


def verify_file_contexts(here, work):
    value = contract(here)
    path = work / "logind-state-file-contexts"
    path.write_bytes(b"".join((here / name).read_bytes() for name in (
        "ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
        "linux-service-file_contexts", "linux-initial-calibration-file_contexts")))
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
        raise OSError(ctypes.get_errno(), "Cannot open normal logind file-context matcher")
    checks = []
    def lookup(filename, mode):
        result = ctypes.c_char_p()
        if lib.selabel_lookup_raw(handle, ctypes.byref(result), filename.encode(), mode):
            if ctypes.get_errno() == 2:
                return None
            raise OSError(ctypes.get_errno(), "Logind context lookup failed: " + filename)
        try:
            return result.value.decode().split(":")[2]
        finally:
            lib.freecon(result)
    try:
        for mode in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK):
            actual = lookup("/var/lib/systemd", mode)
            if (actual == PARENT) != (mode == stat.S_IFDIR):
                raise ValueError("Logind parent alias escaped its exact inode class")
            checks.append(["/var/lib/systemd", mode, actual])
        for filename in ("/var", "/var/lib", "/var/lib/systemd-extra", "/var/lib/systemdx",
                         "/var/lib/other/systemd", "/var/lib/systemd/unselected",
                         "/var/lib/systemd/linger-extra", "/var/lib/systemd/lingers"):
            actual = lookup(filename, stat.S_IFDIR)
            if actual != ALIASES[0]["source"]:
                raise ValueError("Logind parent alias changed another directory: " + filename)
            checks.append([filename, stat.S_IFDIR, actual])
        for filename, mode in (("/var/lib/systemd/linger", stat.S_IFDIR),
                               ("/var/lib/systemd/linger/user", stat.S_IFREG)):
            if lookup(filename, mode) != STATE:
                raise ValueError("Normal logind StateDirectory label changed")
            checks.append([filename, mode, STATE])
        for row in value["normal_files"]:
            if lookup(row["path"], stat.S_IFREG) != row["type"]:
                raise ValueError("Normal logind service executable/unit label changed")
            checks.append([row["path"], stat.S_IFREG, row["type"]])
    finally:
        lib.selabel_close(handle)
    return {"selected_and_negative_cases": len(checks),
            "matrix_sha256": hashlib.sha256(json.dumps(checks).encode()).hexdigest()}
