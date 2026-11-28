"""Confine the normal journal catalog update to its fixed existing directory.

The unchanged journalctl program opens public input FDs through /proc/self/fd
and atomically replaces the catalog database using an O_RDWR temporary file.
This producer grants no access to persistent or volatile journal bodies.
"""
import ctypes
import hashlib
import json
import stat

from derive_native_uevent_policy import ContextPolicy, LEVELS
from derive_native_random_seed_policy import RawPolicy
from derive_preserved_alias_policy import (
    _context, derive_preserved_aliases, verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression

ROLE = "p4_linux_journalctl_t"
DIRECTORY = "p4_linux_journal_catalog_dir_t"
FILE = "p4_linux_journal_catalog_file_t"
NEW_TYPES = {DIRECTORY, FILE}
ALIASES = [
    {"source": "p4_linux_rootdir_t", "target": DIRECTORY, "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": FILE, "class": "file"},
]
DIRECTORY_PERMISSIONS = {"getattr", "open", "read", "search", "write", "add_name", "remove_name"}
FILE_PERMISSIONS = {"getattr", "open", "read", "write", "create", "setattr", "rename", "unlink"}
SELF_PROC = {"dir": {"search"}, "lnk_file": {"read"}}
SOURCE_VIEW = {"dir": {"getattr", "open", "read", "search"}, "file": set()}
# These two original read-only metadata actors cover every board data type.
# The new regular-file label retains exactly their native_data directory-class
# metadata preimage; no other off-class permission is inferred from a candidate.
NORMAL_METADATA_PREIMAGE = {
    (FILE, "droidloom_metadata_observer", "dir"): {"getattr", "search"},
    (FILE, "droidloom_query_io", "dir"): {"getattr", "search"},
}
CREATION = "(typetransition " + ROLE + " " + DIRECTORY + " file " + FILE + ")"
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
DIRECTORY_RELABEL_GUARD = "(validatetrans dir (or (neq t3 p4_linux_hardware_label_t) (or (eq t1 device) (eq t1 t2))))"
DIRECTORY_RELABEL_GUARD_SHA256 = "13e95abc68e40d41bd459bcaa270c23b3ce47db852053bc0413ca4038ea506b8"
CONTRACT_PIN = (5582, "e9b8ffe2f77bc082b0cb4082688a29d36f2721de2efc945201e80ef0e49ad596")


def contract(here):
    raw = (here / "native-journal-catalog-source.json").read_bytes()
    if (len(raw), hashlib.sha256(raw).hexdigest()) != CONTRACT_PIN:
        raise ValueError("The fixed normal journal catalog source contract changed")
    value = json.loads(raw)
    if (value["schema"] != "droidloom.native-journal-catalog-source.v1"
            or value["aliases"] != ALIASES
            or value["role"] != ROLE
            or value["directory"]["path"] != "/var/lib/systemd/catalog"
            or value["directory"]["must_already_exist"] is not True
            or value["directory"]["create_permission"] is not False
            or value["output"]["path"] != "/var/lib/systemd/catalog/database"
            or value["output"]["temporary_basename_regex"] != r"\.#database[0-9a-f]{16}"
            or value["output"]["open_mode"] != "O_RDWR|O_CREAT|O_EXCL|O_CLOEXEC|O_NOCTTY"
            or value["output"]["fsync_called"] is not False
            or value["self_proc_permissions"] != {k: sorted(v) for k, v in SELF_PROC.items()}
            or value["unit_environment_overridden"] is not False
            or value["direct_r13_avc_observed"] is not False
            or value["kernel_runtime_qualified"] is not False):
        raise ValueError("The fixed catalog source/operation boundary changed")
    return value


def _bits(policy, cls, names):
    return sum(policy.permissions(cls, sorted(names))[1].values()) if names else 0


def _rows(table):
    return [[actor, cls, sorted(names)] for (actor, cls), names in sorted(table.items())]


def _table(rows):
    result = {}
    for actor, cls, names in rows:
        if (actor, cls) in result or names != sorted(set(names)):
            raise ValueError("Repeated or noncanonical catalog vector")
        result[(actor, cls)] = set(names)
    return result


def _own(raw):
    actual = raw.actor(ROLE)
    selected = {key: names for key, names in actual.items()
                if key[0] in NEW_TYPES or key[0] == ROLE and key[1] in SELF_PROC}
    wanted = {
        (DIRECTORY, "dir"): DIRECTORY_PERMISSIONS,
        (FILE, "file"): FILE_PERMISSIONS,
        (ROLE, "dir"): SELF_PROC["dir"],
        (ROLE, "lnk_file"): SELF_PROC["lnk_file"],
    }
    if selected != wanted:
        raise ValueError("Catalog changed a complete own output/proc class vector")
    for row in ALIASES:
        if actual.get((row["source"], row["class"]), set()) != SOURCE_VIEW[row["class"]]:
            raise ValueError("Catalog changed its original generic source vector")
    for label in NEW_TYPES:
        if raw.actor(label) != {("labeledfs", "filesystem"): {"associate"}}:
            raise ValueError("Catalog object label acquired unrelated authority")
    for form in raw.xperms:
        if len(form) != 4 or form[1] not in raw.members:
            raise ValueError("Malformed extended ioctl rule")
        if ROLE not in raw.members[form[1]]:
            continue
        targets = {ROLE} if form[2] == "self" else raw.members.get(form[2])
        if targets is None:
            raise ValueError("Unknown extended ioctl object")
        if (targets & NEW_TYPES or ROLE in targets and isinstance(form[3], list)
                and len(form[3]) > 1 and form[3][1] in SELF_PROC):
            raise ValueError("Catalog acquired an output/proc extended ioctl filter")
    denied = {"create", "open", "read", "write", "append", "map", "unlink", "rename"}
    for target in ("p4_linux_journal_database_t", "p4_linux_volatile_journal_database_t"):
        if actual.get((target, "file"), set()) & denied:
            raise ValueError("Catalog client acquired journal database body access")
    return wanted


def _effective_own(policy, raw):
    rows = []
    for (target, cls), names in sorted(_own(raw).items()):
        role = "system_r" if target == ROLE else "object_r"
        for a in LEVELS:
            for b in LEVELS:
                got = policy.context_av(_context("system_r", ROLE, a),
                    _context(role, target, b), cls, raw.classes[cls])
                if a == b == "s0" and got != _bits(policy, cls, names):
                    raise ValueError("The normal s0 catalog operation is not effective")
                rows.append([target, cls, a, b, got])
    return rows


def _constraints(lines, raw):
    selected = sorted(line for line in lines if line.startswith(CONSTRAINTS))
    if (selected.count(DIRECTORY_RELABEL_GUARD) != 1
            or hashlib.sha256(DIRECTORY_RELABEL_GUARD.encode()).hexdigest() != DIRECTORY_RELABEL_GUARD_SHA256):
        raise ValueError("The exact original directory relabel guard changed")
    for line in selected:
        if line == DIRECTORY_RELABEL_GUARD:
            # The identity predicate cannot be replaced one variable at a time.
            # This exact guard restricts only the fixed hardware labeler. It has
            # neither relabel gate on either selected type; no transition with
            # either old/new object is reachable. Every other actor takes the
            # original neq branch. Keep the complete guard, including t1==t2.
            hardware = raw.actor("p4_linux_hardware_label_t")
            for label in ("p4_linux_rootdir_t", DIRECTORY):
                if hardware.get((label, "dir"), set()) & {"relabelfrom", "relabelto"}:
                    raise ValueError("Catalog exposed the fixed identity-guard relabel branch")
            continue
        form = parse_expression(line)
        if form[0] not in ("validatetrans", "mlsvalidatetrans"):
            continue
        for row in ALIASES:
            if form[1] != row["class"]:
                continue
            def substitute(expr, variable, label):
                if not isinstance(expr, list):
                    return expr
                if len(expr) == 3 and expr[0] in ("eq", "neq") and variable in expr[1:]:
                    other = expr[2] if expr[1] == variable else expr[1]
                    if not isinstance(other, str) or other in ("t1", "t2", "t3") or other not in raw.members:
                        raise ValueError("Unmodeled catalog relabel identity predicate")
                    answer = label in raw.members[other]
                    return answer if expr[0] == "eq" else not answer
                return [substitute(child, variable, label) for child in expr]
            for variable in ("t1", "t2"):
                if substitute(form[2], variable, row["source"]) != substitute(form[2], variable, row["target"]):
                    raise ValueError("Catalog alias changed a complete relabel type predicate")
    return selected


def _selected_transitions(lines):
    def atoms(value):
        if isinstance(value, str):
            return {value}
        return set().union(*(atoms(child) for child in value)) if value else set()
    return sorted(line for line in lines if line.startswith(TRANSITIONS)
                  and atoms(parse_expression(line)) & NEW_TYPES)


def derive(library, baseline, exported, here, output, export):
    contract(here)
    expected = derive_preserved_aliases(library, baseline, exported, ALIASES,
        output, export, prefix="p4_catalog_preserved", isolated_roles={ROLE},
        extra_permissions={}, preamble=(
            "; Preserve the original catalog directory/file views for all other actors.",
            "; Only journalctl has the separate fixed output lifecycle proof."))
    policy = ContextPolicy(library, baseline)
    lines = exported.read_text().splitlines()
    raw = RawPolicy(lines)
    _own(raw)
    expected["complete_constraints"] = _constraints(lines, raw)
    expected["own_effective"] = _effective_own(policy, raw)
    if lines.count(CREATION) != 1:
        raise ValueError("The sole catalog default file transition is absent")
    expected["selected_transitions"] = sorted(set(expected["transitions"]) | {CREATION})
    source_raw = {}
    final_targets = {}
    raw_rows = []
    effective = []
    actors = {actor for _, actor in expected["actors"]}
    for row in ALIASES:
        old = raw.incoming(row["source"])
        source_raw[row["source"]] = _rows(old)
        wanted = {key: names for key, names in old.items()
                  if key[1] == row["class"] and key[0] != ROLE}
        wanted[(ROLE, row["class"])] = DIRECTORY_PERMISSIONS if row["class"] == "dir" else FILE_PERMISSIONS
        for (target, actor, cls), names in NORMAL_METADATA_PREIMAGE.items():
            if target != row["target"]:
                continue
            if old.get((actor, cls), set()) != names:
                raise ValueError("Catalog changed the fixed normal metadata source preimage")
            wanted[(actor, cls)] = names
        final_targets[row["target"]] = _rows(wanted)
        preimage = raw.incoming(row["target"])
        for key, names in preimage.items():
            if not names.issubset(wanted.get(key, set())):
                raise ValueError("Catalog alias has an unapproved class/actor preimage")
        for role, actor in expected["actors"]:
            before = old.get((actor, row["class"]), set())
            at_s0 = policy.context_av(_context(role, actor),
                _context("object_r", row["source"]), row["class"], raw.classes[row["class"]])
            if at_s0 != _bits(policy, row["class"], before):
                raise ValueError("Catalog raw source vector cannot be reconstructed at s0")
            raw_rows.append([role, actor, row["source"], row["target"], row["class"], sorted(before)])
            for a in LEVELS:
                for b in LEVELS:
                    got = policy.context_av(_context(role, actor, a),
                        _context("object_r", row["source"], b), row["class"], raw.classes[row["class"]])
                    effective.append([role, actor, row["source"], row["target"], row["class"], a, b, got])
        if any(actor not in actors and actor != ROLE for actor, cls in wanted):
            raise ValueError("Catalog source contains an unmodeled non-actor permission")
    expected["complete_old_source_raw"] = source_raw
    expected["complete_new_target_raw"] = final_targets
    expected["complete_alias_raw"] = raw_rows
    expected["complete_alias_effective"] = effective
    expected["contract_sha256"] = CONTRACT_PIN[1]
    return expected


def verify(library, binary, exported, here, expected, export):
    value = contract(here)
    if expected["contract_sha256"] != CONTRACT_PIN[1]:
        raise ValueError("Catalog source/derivation lineage changed")
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    raw = RawPolicy(lines)
    if _constraints(lines, raw) != expected["complete_constraints"]:
        raise ValueError("Catalog changed complete ordinary/MLS/relabel constraints")
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    if _selected_transitions(lines) != expected["selected_transitions"]:
        raise ValueError("Catalog changed a default or unrelated alias transition")
    _own(raw)
    for label, rows in expected["complete_old_source_raw"].items():
        if raw.incoming(label) != _table(rows):
            raise ValueError("Catalog changed a complete old source class vector")
    for label, rows in expected["complete_new_target_raw"].items():
        if raw.incoming(label) != _table(rows):
            raise ValueError("Catalog changed a complete new target class vector")
    incoming = {label: raw.incoming(label) for row in ALIASES
                for label in (row["source"], row["target"])}
    for role, actor, old, new, cls, names in expected["complete_alias_raw"]:
        for target in (old, new):
            if incoming[target].get((actor, cls), set()) != set(names):
                raise ValueError("Catalog changed an old actor raw alias vector")
    for role, actor, old, new, cls, a, b, wanted in expected["complete_alias_effective"]:
        for target in (old, new):
            got = policy.context_av(_context(role, actor, a),
                _context("object_r", target, b), cls, raw.classes[cls])
            if got != wanted:
                raise ValueError("Catalog changed an old constrained alias vector")
        checks.append([role, actor, old, new, cls, a, b, wanted])
    own = _effective_own(policy, raw)
    if own != expected["own_effective"]:
        raise ValueError("Catalog changed its complete constrained lifecycle vector")
    checks.extend(own)
    return {
        "schema": "droidloom.native-journal-catalog-policy-proof.v1",
        "source": {"bytes": CONTRACT_PIN[0], "sha256": CONTRACT_PIN[1], "contents": value},
        "source_bound_readback_required": True,
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "preserved_actor_object_vectors": len(expected["samples"]),
        "preserved_raw_vectors": 2 * len(expected["complete_alias_raw"]),
        "preserved_effective_vectors": 2 * len(expected["complete_alias_effective"]),
        "complete_new_target_raw_class_object_pairs": 2 * len(raw.types) * len(raw.classes),
        "category_pairs": len(LEVELS) ** 2,
        "journalctl_effective_vectors": len(own),
        "self_proc_permissions": {k: sorted(v) for k, v in SELF_PROC.items()},
        "catalog_directory_permissions": sorted(DIRECTORY_PERMISSIONS),
        "catalog_file_permissions": sorted(FILE_PERMISSIONS),
        "default_file_transition": CREATION,
        "normal_metadata_preimage": [
            [target, actor, cls, sorted(names)]
            for (target, actor, cls), names in sorted(NORMAL_METADATA_PREIMAGE.items())],
        "directory_relabel_guard": {
            "sha256": DIRECTORY_RELABEL_GUARD_SHA256,
            "restricted_actor": "p4_linux_hardware_label_t",
            "old_type": "p4_linux_rootdir_t", "new_type": DIRECTORY,
            "raw_relabelfrom_and_relabelto": 0,
            "complete_original_form_retained": True},
        "directory_creation": False, "generic_parent_write_added": False,
        "fsync_called": False, "journal_database_body_access": False,
        "direct_r13_avc_observed": False,
        "file_contexts": verify_file_contexts(here, exported.parent),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "kernel_runtime_qualified": False, "production_qualified": False,
    }


def verify_file_contexts(here, work):
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    data = b"".join((here / name).read_bytes() for name in names)
    path = work / "journal-catalog-file-contexts"
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("Catalog matcher input changed")
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
        raise ValueError("Normal class-aware catalog file contexts cannot be opened")
    directory = "/var/lib/systemd/catalog"
    files = [directory + "/database", directory + "/.#database0000000000000000",
             directory + "/.#database0123456789abcdef"]
    cases = [(directory, stat.S_IFDIR, DIRECTORY)]
    cases += [(name, stat.S_IFREG, FILE) for name in files]
    cases += [(directory, kind, None) for kind in (stat.S_IFREG, stat.S_IFLNK)]
    cases += [(name, kind, None) for name in files for kind in (stat.S_IFDIR, stat.S_IFLNK)]
    cases += [(directory + suffix, stat.S_IFREG, None) for suffix in (
        "/database-old", "/database/child", "/.#database0123456789abcde",
        "/.#database0123456789abcdef0", "/.#database0123456789abcdeg",
        "/.#database0123456789ABCDEF", "/.#other0123456789abcdef")]
    cases += [(directory + suffix, stat.S_IFDIR, None) for suffix in ("-old", "/child")]
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
                raise ValueError("Catalog class-aware lookup failed")
            actual = context.split(":")[2] if context else None
            if wanted is not None and actual != wanted or wanted is None and actual in NEW_TYPES:
                raise ValueError("Catalog exact/adjacent path boundary changed: " + name)
            rows.append([name, mode, context])
    finally:
        lib.selabel_close(handle)
    return {"cases": len(rows), "rows": rows, "composed_sha256": hashlib.sha256(data).hexdigest()}
