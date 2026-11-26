"""Verify the reviewed native TCGETS2 audit delta and seven fixed startup bits.

The expected commitments below were generated from the actual R13 normal
binary and its independently retained CIL export. They are never generated
from a candidate. This proof intentionally rejects an unrelated access or
transition change outside the seven source-proven startup bits and one directory
ioctl listed below. Further changes require an independently reviewed baseline
or explicit composition, not a regenerated candidate expectation.
"""
import hashlib
import json

from derive_native_uevent_policy import Membership
from derive_shared_payload_cgroup_policy import parse_expression

SCHEMA = "droidloom.native-tcgets2-audit.v2"
PROBE = 0x542a
AUDIT_OPERATIONS = frozenset({"auditallow", "dontaudit", "auditallowx", "dontauditx"})
TYPE_OPERATIONS = frozenset({
    "type", "typeattribute", "typeattributeset", "typealias",
    "typealiasactual", "expandtypeattribute",
})

# Generation: parse every complete non-comment line using the normal export
# parser; compact ensure_ascii JSON for each AST; lexically sort the rows,
# retaining multiplicity; append LF to every row, then SHA-256. Whole
# conditionals, constraints, role/type statements and transitions remain in
# non_audit. Only top-level allow rows are merged by literal (source, target,
# class), with permission tokens unioned and sorted. All other ASTs remain exact.
# The allow/allowx inventories additionally walk every nested branch.
BASELINE_BINARY = {'bytes': 1378147, 'sha256': '334f85991aa8b821efbd8ee793083d0031ff1ffbb9bddac7e928c5fa2092d42c'}
BASELINE_EXPORT = {'bytes': 11026119, 'sha256': '87199686510833e1f2424e12faa9510b900646adf3ad89628ebc68899be50e39'}
BASELINE_NORMAL_RECEIPT = {'bytes': 88398, 'sha256': '31bc7c974c4ad344d1c83af58d03de965180161a85c4f8ab341286d3edb68b7c'}
BASELINE_COMMITMENTS = {'allow': {'forms': 44569,
           'sha256': 'dffd0f4d69c63bcb4b7c5ca89c8ddb462207ad47c8167e6fb8708036d9a6965b',
           'unique_forms': 44569},
 'allowx': {'forms': 1991,
            'sha256': '2d69e92789d41c373bce63b89b983098572a173b25b4240bd392c306dab08075',
            'unique_forms': 1991},
 'audit': {'forms': 834,
           'sha256': 'f729165a8ab160310b156485df5922c83fc52906e3d386708ed5fea7d95ed748',
           'unique_forms': 834},
 'non_audit': {'forms': 57672,
               'sha256': 'b035503f2603fc449ff8b92b2703423acaef7c37d4e68985ce06f24ffb171254',
               'unique_forms': 57672},
 'type_membership': {'forms': 4261,
                     'sha256': '671818312dfb0bcd46ed769510e77ac9cbf4a5881a9fdcb151e97721959e2117',
                     'unique_forms': 4261}}

# All 28 source/target types were observed as file/0x542a denials in the R13
# serial transcript 10938621 / cfbc84d8463c53df0e88361b3bee46ca2198c02a7a737cf24e68f08648855263.
# The baseline has no raw ioctl allow or any extended-permission rule for any
# of these pairs, including all conditional branches.
EXPECTED_PAIRS = (('init_t', 'droidloom_package_early_unit_file'),
 ('init_t', 'droidloom_package_native_unit_file'),
 ('init_t', 'init_t'),
 ('init_t', 'p4_linux_apparmor_enabled_t'),
 ('init_t', 'p4_linux_cgroup_controller_list_t'),
 ('init_t', 'p4_linux_factory_unit_file_t'),
 ('init_t', 'p4_linux_machine_id_t'),
 ('init_t', 'p4_linux_native_config_t'),
 ('init_t', 'p4_linux_production_unit_file_t'),
 ('init_t', 'p4_linux_runtime_lib_t'),
 ('init_t', 'p4_linux_systemd_config_t'),
 ('init_t', 'p4_linux_systemd_memfd_t'),
 ('init_t', 'p4_linux_unit_cgroup_t'),
 ('init_t', 'proc_cpuinfo'),
 ('init_t', 'proc_pid_max'),
 ('init_t', 'sysfs'),
 ('p4_linux_generator_t', 'p4_linux_native_config_t'),
 ('p4_linux_generator_t', 'sysfs'),
 ('p4_linux_journald_t', 'init_t'),
 ('p4_linux_journald_t', 'p4_linux_journal_config_t'),
 ('p4_linux_remount_t', 'p4_linux_remount_t'),
 ('p4_linux_service_executor_t', 'p4_linux_apparmor_enabled_t'),
 ('p4_linux_setup_t', 'p4_linux_native_config_t'),
 ('p4_linux_setup_t', 'p4_linux_runtime_lib_t'),
 ('p4_linux_setup_t', 'p4_linux_setup_t'),
 ('p4_linux_sysctl_t', 'p4_linux_runtime_lib_t'),
 ('p4_linux_udev_t', 'p4_linux_native_config_t'),
 ('p4_linux_udev_t', 'p4_linux_udev_t'))


def _canonical(form):
    return json.dumps(form, ensure_ascii=True, separators=(",", ":"))


def _commitment(forms):
    rows = sorted(_canonical(form) for form in forms)
    return {
        "forms": len(rows),
        "unique_forms": len(set(rows)),
        "sha256": hashlib.sha256("".join(row + "\n" for row in rows).encode("ascii")).hexdigest(),
    }


def _forms(text):
    forms = []
    seen = set()
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        form = parse_expression(line)
        if not isinstance(form, list) or not form or not isinstance(form[0], str):
            raise ValueError(f"Invalid final policy form at line {number}")
        key = _canonical(form)
        if key in seen:
            raise ValueError("Duplicate final policy form in TCGETS2 audit proof")
        seen.add(key)
        forms.append(form)
    return forms


def _walk(form):
    yield form
    for item in form:
        if isinstance(item, list):
            yield from _walk(item)


def _ioctl_values(expression):
    if isinstance(expression, str):
        try:
            value = int(expression, 0)
        except ValueError as error:
            raise ValueError("Non-numeric TCGETS2 extended permission") from error
        if not 0 <= value <= 0xffff:
            raise ValueError("TCGETS2 extended permission exceeds the kernel u16 command")
        return {value}
    if not isinstance(expression, list) or not expression:
        raise ValueError("Empty or invalid TCGETS2 extended-permission expression")
    if expression[0] == "range":
        if len(expression) != 3:
            raise ValueError("Invalid TCGETS2 command range")
        first = _ioctl_values(expression[1])
        last = _ioctl_values(expression[2])
        if len(first) != 1 or len(last) != 1 or min(first) > min(last):
            raise ValueError("Invalid TCGETS2 command bounds")
        return set(range(min(first), min(last) + 1))
    result = set()
    for part in expression:
        result.update(_ioctl_values(part))
    return result


def _exact_probe_rule(form):
    return (
        len(form) == 4
        and isinstance(form[3], list)
        and len(form[3]) == 3
        and form[3][:2] == ["ioctl", "file"]
        and _ioctl_values(form[3][2]) == {PROBE}
    )


def _matches(membership, form, source, target):
    return membership.member(form[1], source) and (
        source == target if form[2] == "self" else membership.member(form[2], target)
    )


def _verify_raw_pairs(forms, membership):
    permission_forms = [
        nested for form in forms for nested in _walk(form)
        if nested and isinstance(nested[0], str)
        and nested[0] in {"allow", "allowx", "auditallowx", "dontauditx"}
    ]
    matrix = []
    for source, target in EXPECTED_PAIRS:
        if source not in membership.types or target not in membership.types:
            raise ValueError("TCGETS2 audit pair is not a concrete type pair")
        xrules = []
        for form in permission_forms:
            if len(form) != 4 or not isinstance(form[3], list):
                raise ValueError("Unknown permission form in TCGETS2 audit proof")
            if form[0] == "allow":
                if len(form[3]) != 2:
                    raise ValueError("Unknown base permission shape")
                cls, permissions = form[3]
                if cls != "file":
                    continue
                if not isinstance(permissions, list) or any(not isinstance(p, str) for p in permissions):
                    raise ValueError("Non-expanded file permission vector")
                if "ioctl" in permissions and _matches(membership, form, source, target):
                    raise ValueError("TCGETS2 audit pair already has raw base ioctl access")
            else:
                if len(form[3]) != 3:
                    raise ValueError("Unknown extended permission shape")
                if form[3][:2] != ["ioctl", "file"]:
                    continue
                if _matches(membership, form, source, target):
                    xrules.append(form)
        if (len(xrules) != 1 or xrules[0][0] != "dontauditx"
                or xrules[0][1:3] != [source, target] or not _exact_probe_rule(xrules[0])):
            raise ValueError("TCGETS2 audit pair has an existing or non-exact xperm rule")
        matrix.append({
            "source": source, "target": target, "class": "file",
            "raw_base_ioctl_allowed": False, "preexisting_xperm_rules": 0,
            "dontaudit_commands": [PROBE],
        })
    return matrix


# These are the separately reviewed normal startup fixes, not caller input.
# The baseline raw bit is zero for each of the seven permissions. The directory
# tuple also has no prior allowx/auditallowx/dontauditx entry.
REVIEWED_NATIVE_GRANTS = (
    ("droidloom_policy_loader", "init_t", "dir", ("getattr", "search")),
    ("droidloom_policy_loader", "init_t", "file", ("getattr", "open", "read")),
    ("droidloom_policy_loader", "init_t", "lnk_file", ("read",)),
    ("p4_linux_service_executor_t", "p4_linux_logind_state_t", "dir", ("ioctl",)),
)
QUOTA_PAIR = ("p4_linux_service_executor_t", "p4_linux_logind_state_t")
QUOTA_COMMAND = 0x581f


def _normalise_allow(forms):
    merged = {}
    result = []
    for form in forms:
        if form[0] != "allow":
            result.append(form)
            continue
        if len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2:
            raise ValueError("Unknown base allow AST in native audit proof")
        key = (form[1], form[2], form[3][0])
        permissions = form[3][1]
        if (any(not isinstance(value, str) for value in key)
                or not isinstance(permissions, list)
                or any(not isinstance(value, str) for value in permissions)):
            raise ValueError("Non-expanded base allow AST in native audit proof")
        merged.setdefault(key, set()).update(permissions)
    result.extend(["allow", source, target, [cls, sorted(permissions)]]
                  for (source, target, cls), permissions in sorted(merged.items()))
    return result


def _base_permissions(forms, membership, source, target, cls):
    result = set()
    for form in forms:
        for nested in _walk(form):
            if not nested or nested[0] != "allow":
                continue
            if len(nested) != 4 or not isinstance(nested[3], list) or len(nested[3]) != 2:
                raise ValueError("Unknown nested raw allow AST")
            if nested[3][0] == cls and _matches(membership, nested, source, target):
                permissions = nested[3][1]
                if not isinstance(permissions, list) or any(not isinstance(p, str) for p in permissions):
                    raise ValueError("Non-expanded nested raw allow permissions")
                result.update(permissions)
    return result


def _subtract_native_grants(forms, membership):
    """Remove only the fixed concrete source-proven delta; return its preimage."""
    normal = _normalise_allow(forms)
    rows = {(form[1], form[2], form[3][0]): form
            for form in normal if form[0] == "allow"}
    matrix = []
    for source, target, cls, permissions in REVIEWED_NATIVE_GRANTS:
        key = (source, target, cls)
        if source not in membership.types or target not in membership.types or key not in rows:
            raise ValueError("Missing concrete reviewed native grant")
        row = rows[key]
        if not set(permissions).issubset(row[3][1]):
            raise ValueError("Missing reviewed native permission bit")
        final = _base_permissions(normal, membership, source, target, cls)
        if not set(permissions).issubset(final):
            raise ValueError("Reviewed native final raw bit is absent")
        row[3][1] = sorted(set(row[3][1]) - set(permissions))
        for permission in permissions:
            matrix.append({
                "source": source, "target": target, "class": cls,
                "permission": permission, "baseline_raw_allowed": False,
                "final_raw_allowed": True,
            })
    normal = [form for form in normal if form[0] != "allow" or form[3][1]]
    for source, target, cls, permissions in REVIEWED_NATIVE_GRANTS:
        if set(permissions) & _base_permissions(normal, membership, source, target, cls):
            raise ValueError("Reviewed native bit was already granted by another baseline rule")
    xrules = [
        nested for form in normal for nested in _walk(form)
        if nested and isinstance(nested[0], str)
        and nested[0] in {"allowx", "auditallowx", "dontauditx"}
        and len(nested) == 4 and isinstance(nested[3], list)
        and len(nested[3]) == 3 and nested[3][:2] == ["ioctl", "dir"]
        and _matches(membership, nested, *QUOTA_PAIR)
    ]
    if (len(xrules) != 1 or xrules[0][0] != "allowx"
            or xrules[0][1:3] != list(QUOTA_PAIR)
            or _ioctl_values(xrules[0][3][2]) != {QUOTA_COMMAND}
            or xrules[0] not in normal):
        raise ValueError("The reviewed directory ioctl has a non-exact or pre-existing xperm")
    normal.remove(xrules[0])
    return normal, matrix


def _summaries(forms):
    normal = _normalise_allow(forms)
    flat = [nested for form in normal for nested in _walk(form)
            if nested and isinstance(nested[0], str)]
    return {
        "non_audit": _commitment(form for form in normal if form[0] not in AUDIT_OPERATIONS),
        "audit": _commitment(form for form in normal if form[0] in AUDIT_OPERATIONS),
        "type_membership": _commitment(form for form in normal if form[0] in TYPE_OPERATIONS),
        "allow": _commitment(form for form in flat if form[0] == "allow"),
        "allowx": _commitment(form for form in flat if form[0] == "allowx"),
    }


def verify_native_tcgets2_audit(export):
    """Read the normal final binary export; no baseline or expected caller input."""
    text = export.read_text()
    return _verify_text(text)


def _verify_text(text):
    forms = _forms(text)
    membership = Membership(text)
    expected = set(EXPECTED_PAIRS)
    if len(expected) != 28:
        raise ValueError("The reviewed TCGETS2 audit roster changed")
    added = {}
    remaining = []
    for form in forms:
        if form[0] == "dontauditx":
            if len(form) != 4 or any(not isinstance(x, str) for x in form[1:3]):
                raise ValueError("Non-concrete or malformed TCGETS2 audit rule")
            pair = tuple(form[1:3])
            if pair in expected:
                if pair in added:
                    raise ValueError("Duplicate concrete TCGETS2 audit pair")
                if pair[0] not in membership.types or pair[1] not in membership.types:
                    raise ValueError("Non-concrete TCGETS2 audit rule")
                if not _exact_probe_rule(form):
                    raise ValueError("TCGETS2 audit rule expands its class or command")
                added[pair] = form
                continue
        remaining.append(form)
    if set(added) != expected:
        raise ValueError("The final policy lacks the exact 28 TCGETS2 audit rules")
    baseline, grants = _subtract_native_grants(remaining, membership)
    actual = _summaries(baseline)
    for name, wanted in BASELINE_COMMITMENTS.items():
        if actual[name] != wanted:
            raise ValueError("TCGETS2/native grant delta changed baseline " + name)
    matrix = _verify_raw_pairs(forms, membership)
    return {
        "schema": SCHEMA,
        "baseline_binary": BASELINE_BINARY,
        "baseline_export": BASELINE_EXPORT,
        "baseline_normal_receipt": BASELINE_NORMAL_RECEIPT,
        "canonical_commitments_after_exact_subtraction": actual,
        "all_other_non_audit_forms_preserved": True,
        "all_original_audit_forms_preserved": True,
        "new_dontaudit_pairs": len(matrix),
        "ioctl_u16": PROBE,
        "class": "file",
        "matrix": matrix,
        "matrix_sha256": hashlib.sha256(
            json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "reviewed_native_grants": grants,
        "reviewed_directory_ioctl": {
            "source": QUOTA_PAIR[0], "target": QUOTA_PAIR[1], "class": "dir",
            "commands": [QUOTA_COMMAND], "baseline_xperm_rules": 0,
        },
        "runtime_audit_suppression_observed": False,
    }
