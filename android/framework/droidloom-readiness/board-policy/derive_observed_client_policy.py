"""Preserve the two normal client ELF labels, with one exact new reader.

The preimage is the old object's complete linked authority, including audit
and extended audit vectors. The old type and all of its authority remain in
the final binary. Only the new object receives the broker's three read bits.
This does not derive an expected grant from the new object's candidate output.
"""
import hashlib
import json
from collections import defaultdict

from derive_native_uevent_policy import ContextPolicy
from derive_preserved_alias_policy import derive_preserved_aliases, verify_preserved_aliases
from derive_shared_payload_cgroup_policy import format_xperms
from verify_working_qualification import _Index, _forms, _atoms, _xvalues

SOURCE = "droidloom_public_control_client_exec"
TARGET = "p4_linux_observed_client_exec_t"
BROKER = "droidloom_broker"
ALIASES = [{"source": SOURCE, "target": TARGET, "class": kind} for kind in ("file", "dir")]
READ = frozenset(("getattr", "open", "read"))
FLOW = frozenset(("allow", "auditallow", "dontaudit", "allowx", "auditallowx", "dontauditx"))
TRANSITIONS = frozenset(("typetransition", "typechange", "typemember", "roletransition", "rangetransition"))
SOURCE_ENTRIES = frozenset(
    "(typetransition " + actor + " " + SOURCE + " process droidloom_public_control_client)"
    for actor in ("p4_linux_user_session_t", "p4_linux_user_executor_t"))
CONTEXTS = (
    "/usr/bin/droidloomctl -- u:object_r:" + TARGET + ":s0",
    "/usr/bin/droidloom-applications -- u:object_r:" + TARGET + ":s0",
)


def _canonical(form):
    if isinstance(form, str):
        return form
    return "(" + " ".join(_canonical(part) for part in form) + ")"


def _rows(matrix):
    return [[*key, sorted(values)] for key, values in sorted(matrix.items()) if values]


def _digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def source_inputs(here):
    return [here / "derive_observed_client_policy.py", here / "linux-observed-client.cil",
            here / "linux-public-control.cil", here / "linux-service-file_contexts"]


def contract(here):
    observed = []
    for name in ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
                 "linux-service-file_contexts", "linux-initial-calibration-file_contexts"):
        for line in (here / name).read_text().splitlines():
            if line.strip().startswith("#"):
                continue
            if ":" + TARGET + ":" in line:
                observed.append(line.strip())
            if ":" + SOURCE + ":" in line:
                raise ValueError("Observed normal clients still have a second old file-context rule")
    if sorted(observed) != sorted(CONTEXTS):
        raise ValueError("Observed-client label must select exactly the two fixed ELF paths")
    return {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in source_inputs(here)}


def _matrix(forms, index, selected):
    """All six raw/audit operations, both directions, all classes and types."""
    matrix = defaultdict(set)
    for form in forms:
        tag = form[0]
        if tag in ("booleanif", "tunableif", "typebounds", "typepermissive"):
            raise ValueError("Observed-client proof requires unconditional, enforcing, unbounded types")
        if tag not in FLOW:
            known = {"type", "typeattribute", "typeattributeset", "roletype",
                     "class", "common", "classcommon", "expandtypeattribute",
                     "constrain", "mlsconstrain", "validatetrans", "mlsvalidatetrans"} | TRANSITIONS
            if tag not in known and any(
                    token == selected or (token in index.definitions and selected in index.members(token))
                    for token in _atoms(form)):
                raise ValueError("Unmodeled statement contains observed-client authority")
            continue
        if len(form) != 4 or not isinstance(form[3], list):
            raise ValueError("Unmodeled observed-client flow form")
        sources = index.members(form[1])
        targets = None if form[2] == "self" else index.members(form[2])
        if selected not in sources and (targets is None or selected not in targets):
            continue
        if tag.endswith("x"):
            if len(form[3]) != 3 or form[3][0] != "ioctl" or form[3][1] not in index.classes:
                raise ValueError("Unmodeled observed-client extended audit authority")
            kind, values = form[3][1], _xvalues(form[3][2])
        else:
            if len(form[3]) != 2 or form[3][0] not in index.classes:
                raise ValueError("Unmodeled observed-client authority class")
            kind, names = form[3]
            if not isinstance(names, list) or not set(names) <= index.classes[kind]:
                raise ValueError("Unknown observed-client permission")
            values = set(names)
        if targets is None:
            pairs = [(selected, selected)] if selected in sources else []
        else:
            pairs = ([(selected, target) for target in targets] if selected in sources else [])
            pairs += [(source, selected) for source in sources if source != selected] if selected in targets else []
        for source, target in pairs:
            matrix[(tag, source, target, kind)].update(values)
        if len(matrix) > 20000:
            raise ValueError("Observed-client authority exceeds its fixed proof bound")
    return {key: frozenset(values) for key, values in matrix.items() if values}


def _expected(preimage):
    if preimage.get(("allow", BROKER, SOURCE, "file"), frozenset()):
        raise ValueError("The old broker/client-executable boundary changed")
    result = defaultdict(set)
    for (tag, source, target, kind), values in preimage.items():
        result[(tag, TARGET if source == SOURCE else source,
                TARGET if target == SOURCE else target, kind)].update(values)
    result[("allow", BROKER, TARGET, "file")].update(READ)
    return {key: frozenset(values) for key, values in result.items() if values}


def _require_subset(actual, expected):
    for key, values in actual.items():
        if values - expected.get(key, frozenset()):
            raise ValueError("New observed-client preimage contains unreviewed authority: " + str(key))


def _emit(matrix):
    lines = []
    for (tag, source, target, kind), values in sorted(matrix.items()):
        if tag.endswith("x"):
            mask = sum(1 << number for number in values)
            permissions = "(ioctl " + kind + " " + format_xperms(mask) + ")"
        else:
            permissions = "(" + kind + " (" + " ".join(sorted(values)) + "))"
        lines.append("(" + tag + " " + source + " " + target + " " + permissions + ")")
    return lines


def _entries(forms, index, selected):
    result = set()
    for form in forms:
        if form[0] not in TRANSITIONS:
            continue
        # The concrete exporter must retain the two fixed process entries.
        # Any other participation, including output/range transitions, fails.
        tokens = set(_atoms(form))
        participates = selected in tokens or any(
            token in index.definitions and selected in index.members(token)
            for token in tokens)
        if participates:
            result.add(_canonical(form))
    return result


def _object_only(forms, index):
    if index.roles[SOURCE] != {"object_r"} or index.roles[TARGET] != {"object_r"}:
        raise ValueError("Observed-client alias is not an object-only label")
    for form in forms:
        if form[0] in ("genfscon", "filecon", "fsuse", "portcon", "nodecon", "netifcon",
                       "ibpkeycon", "ibendportcon", "typealias", "typealiasactual"):
            if TARGET in set(_atoms(form)):
                raise ValueError("Observed-client alias escaped its two external file-context paths")


def _constraints(forms, index):
    """Fixed regular-file predicates remain equal at every MLS level.

    Every global constraint is retained byte-for-byte. Only file predicates
    participate in this alias: its entire materialization roster is two `--`
    file-context entries, and a new genfs/fsuse or other label mapping is
    rejected separately. Hardware chr_file/dir identity gates are unchanged.
    """
    result = []
    def reduce(expr, variable, selected):
        if not isinstance(expr, list):
            return expr
        if len(expr) == 3 and expr[0] in ("eq", "neq") and variable in expr[1:]:
            other = expr[2] if expr[1] == variable else expr[1]
            if isinstance(other, str) and other in ("t1", "t2", "t3"):
                raise ValueError("Observed-client alias needs an unmodeled direct type identity proof")
            value = selected in index.members(other)
            return value if expr[0] == "eq" else not value
        return [reduce(child, variable, selected) for child in expr]
    for form in forms:
        if form[0] not in ("constrain", "mlsconstrain", "validatetrans", "mlsvalidatetrans"):
            continue
        kind = form[1][0] if isinstance(form[1], list) else form[1]
        if kind not in index.classes:
            raise ValueError("Unknown observed-client constraint class")
        result.append(_canonical(form))
        if kind != "file":
            continue
        # The three-context relabel constraints retain the same complete
        # expression too. Substituting this object for either old/new context
        # or the task context cannot alter any type predicate. User, role and
        # MLS variables are untouched; the object-only role is checked above.
        for variable in ("t1", "t2", "t3"):
            if reduce(form, variable, SOURCE) != reduce(form, variable, TARGET):
                raise ValueError("Observed-client alias changes a full source/target constraint predicate")
    return sorted(result)


def derive(library, baseline, exported, here, output, export):
    sources = contract(here)
    expected = derive_preserved_aliases(library, baseline, exported, ALIASES, output, export,
        prefix="p4_observed_client_preserved", isolated_roles=set(),
        extra_permissions={(BROKER, TARGET, "file"): READ},
        preamble=("; Normal public-client ELF alias; original authority remains unchanged.",))
    forms = _forms(exported.read_text())
    index = _Index(forms)
    _object_only(forms, index)
    before = _matrix(forms, index, SOURCE)
    wanted = _expected(before)
    _require_subset(_matrix(forms, index, TARGET), wanted)
    if _entries(forms, index, SOURCE) != SOURCE_ENTRIES:
        raise ValueError("Original public-client automatic entries differ")
    if _entries(forms, index, TARGET):
        raise ValueError("Observed-client alias was populated before normal derivation")
    constraints = _constraints(forms, index)
    with output.open("a") as file:
        file.write("\n".join(_emit(wanted)) + "\n")
    expected.update({"source_contract": sources, "complete_preimage": _rows(before),
        "complete_alias": _rows(wanted), "all_constraints": constraints,
        "derived_sha256": hashlib.sha256(output.read_bytes()).hexdigest()})
    return expected


def verify(library, binary, exported, here, expected):
    if contract(here) != expected["source_contract"]:
        raise ValueError("Observed-client source inputs changed during the normal link")
    policy = ContextPolicy(library, binary)
    checks = verify_preserved_aliases(policy, exported, ALIASES, expected)
    forms = _forms(exported.read_text())
    index = _Index(forms)
    _object_only(forms, index)
    before = _rows(_matrix(forms, index, SOURCE))
    actual = _rows(_matrix(forms, index, TARGET))
    if before != expected["complete_preimage"]:
        raise ValueError("Observed-client alias changed original raw or audit authority")
    if actual != expected["complete_alias"]:
        raise ValueError("Observed-client complete alias raw or audit authority differs")
    if _constraints(forms, index) != expected["all_constraints"]:
        raise ValueError("Observed-client alias changed original full constraint expressions")
    entries = {row.replace(SOURCE, TARGET) for row in SOURCE_ENTRIES}
    if _entries(forms, index, SOURCE) != SOURCE_ENTRIES or _entries(forms, index, TARGET) != entries:
        raise ValueError("Observed-client exact original/aliased transitions differ")
    return {"schema": "droidloom.observed-client-alias-proof.v1",
        "fixed_paths": list(CONTEXTS), "old_raw_audit_rows": len(before),
        "new_raw_audit_rows": len(actual), "complete_old_rows": before,
        "complete_new_rows": actual, "old_authority_sha256": _digest(before),
        "new_authority_sha256": _digest(actual), "av_mcs_ioctl_checks": len(checks),
        "all_original_authority_preserved": True, "runtime_qualified": False}
