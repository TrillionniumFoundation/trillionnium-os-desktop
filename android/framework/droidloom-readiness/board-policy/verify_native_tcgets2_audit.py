"""Verify TCGETS2 suppression and the exact source-proven native startup delta.

The five commitments remain those of the actual R13 normal binary/export.
The original concrete types, all 781 original attributes, constraints, transitions,
and permissions retain those commitments after the explicit source-owned subtraction.
New source-owned component families have separate complete role/alias verifiers;
the projection removes only their explicitly declared new-type authority.
No expected commitment is generated from a candidate.
"""
import hashlib
import json

from derive_native_uevent_policy import Membership
from derive_shared_payload_cgroup_policy import parse_expression
from verify_native_original_projection import verify_projection

SCHEMA = "droidloom.native-tcgets2-audit.v5"
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

# The original 28 source/target pairs were observed as file/0x542a denials in R13
# serial transcript 10938621 / cfbc84d8463c53df0e88361b3bee46ca2198c02a7a737cf24e68f08648855263.
# The baseline has no raw ioctl allow or any extended-permission rule for any
# of these pairs, including all conditional branches.
# The additional journalctl/runtime-lib pair was observed in the R3 serial
# transcript SHA256 2ddde1868de78d0d95ac7931c7ac336ca521d254f0bbfd570fc1108882985828.
# It is the same regular-file TCGETS2 probe, not an ioctl permission grant.
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
 ('p4_linux_journalctl_t', 'p4_linux_runtime_lib_t'),
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


def _concrete_pair(membership, form):
    """Match a concrete same-source self spelling without rewriting its AST."""
    source, target = form[1:3]
    if source not in membership.types:
        return None
    if target == "self":
        target = source
    if target not in membership.types:
        return None
    return source, target


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
                or _concrete_pair(membership, xrules[0]) != (source, target)
                or not _exact_probe_rule(xrules[0])):
            raise ValueError("TCGETS2 audit pair has an existing or non-exact xperm rule")
        matrix.append({
            "source": source, "target": target, "class": "file",
            "raw_base_ioctl_allowed": False, "preexisting_xperm_rules": 0,
            "dontaudit_commands": [PROBE],
        })
    return matrix


# These are the separately reviewed normal startup fixes, not caller input.
# The baseline raw bit is zero for every listed permission. The directory
# tuple also has no prior allowx/auditallowx/dontauditx entry.
REVIEWED_NATIVE_GRANTS = (
    ("droidloom_policy_loader", "init_t", "dir", ("getattr", "search")),
    ("droidloom_policy_loader", "init_t", "file", ("getattr", "open", "read")),
    ("droidloom_policy_loader", "init_t", "lnk_file", ("read",)),
    ("droidloom_policy_loader", "p4_linux_product_store_t", "dir", ("getattr", "search")),
    ("droidloom_policy_loader", "p4_linux_console_ld_cache_native_config_t", "file", ("getattr", "open", "read", "map")),
    ("p4_linux_service_executor_t", "p4_linux_service_executor_t", "unix_dgram_socket", ("create", "connect", "write", "getopt", "setopt")),
    ("p4_linux_service_executor_t", "p4_linux_journald_t", "unix_dgram_socket", ("sendto",)),
    ("p4_linux_service_executor_t", "p4_linux_journal_native_socket_t", "sock_file", ("write",)),
    ("p4_linux_service_executor_t", "p4_linux_credentials_root_t", "dir", ("relabelto",)),
    ("p4_linux_service_executor_t", "p4_linux_remount_mount_exec_t", "file", ("getattr", "open", "read", "execute", "map")),
    ("p4_linux_service_executor_t", "p4_linux_logind_state_t", "dir", ("ioctl",)),
    ("p4_linux_service_executor_t", "p4_linux_resolved_run_t", "sock_file", ("getattr", "setattr")),
    ("p4_linux_early_t", "random_device", "chr_file", ("getattr", "relabelto")),
    ("random_device", "device", "filesystem", ("associate",)),
    ("p4_linux_early_t", "kmsg_device", "chr_file", ("getattr", "relabelto")),
    ("kmsg_device", "device", "filesystem", ("associate",)),
    ("p4_linux_module_loader_t", "proc", "lnk_file", ("read",)),
    ("p4_linux_udev_t", "p4_linux_udev_listener_t", "sock_file", ("write",)),
    ("p4_linux_udev_t", "p4_linux_udev_t", "unix_stream_socket", ("connectto",)),
    ("p4_linux_console_ld_cache_native_config_t", "labeledfs", "filesystem", ("associate",)),
    ("p4_linux_journalctl_t", "p4_linux_journalctl_t", "dir", ("search",)),
    ("p4_linux_journalctl_t", "p4_linux_journalctl_t", "lnk_file", ("read",)),
    # The fixed user production-unit status reader needs its original unit
    # inode. The retained before/after unit-status binaries independently gave
    # the full file vector 0 -> {getattr, open, read} at all four source levels;
    # verify_working_qualification also rejects every additional old-type edge.
    ("p4_linux_user_manager_t", "p4_linux_production_unit_file_t", "file", ("getattr", "open", "read")),
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


def _split_reviewed_derived_source_grant(
        forms, membership, source, target, permissions, require_literal, zero_attribute):
    """Restore a fixed producer's virtual preimage without changing authority.

    Only the two source-owned callers below select a tuple. The nonzero group
    must have one bounded flat definition and one exact AV use in the complete
    AST. Its original zero-vector group must have no use beyond declaration and
    definition. The generators move the reviewed actor between those groups;
    the virtual preimage moves it back and retains its exact concrete grant.
    Original commitments still gate the later exact subtraction.
    """
    normal = _normalise_allow(forms)
    literal = ["allow", source, target, ["file", permissions]]
    concrete = [f for f in normal if f[0] == "allow" and f[1:3] == [source, target]
                and f[3][0] == "file"]
    if require_literal:
        if concrete != [literal]:
            raise ValueError("The reviewed remount delta lacks its exact explicit row")
    elif concrete:
        return normal, membership, {"present": False}
    candidates = [f for f in normal
                  if f[0] == "allow" and f[1] in membership.attributes
                  and f[2] == target and f[3] == ["file", permissions]
                  and membership.member(f[1], source)]
    if not candidates and require_literal:
        return normal, membership, {"present": False}
    if len(candidates) != 1:
        raise ValueError("The reviewed grant has no unique derived source")
    rule = candidates[0]
    attribute = rule[1]
    declaration = ["typeattribute", attribute]
    definitions = [f for f in normal
                   if f[0] == "typeattributeset" and f[1] == attribute]
    if len(definitions) != 1:
        raise ValueError("The reviewed derived source has repeated definitions")
    definition = definitions[0]
    members = definition[2]
    if (not isinstance(members, list) or not 2 <= len(members) <= 128
            or any(not isinstance(v, str) or v not in membership.types for v in members)
            or len(set(members)) != len(members) or source not in members):
        raise ValueError("The reviewed derived source is not a bounded concrete set")
    uses = [f for f in normal
            if any(value == attribute for nested in _walk(f)
                   for value in nested if isinstance(value, str))]
    if (len(uses) != 3 or sum(f == declaration for f in uses) != 1
            or sum(f == definition for f in uses) != 1
            or sum(f == rule for f in uses) != 1):
        raise ValueError("The reviewed derived source is used outside its sole allow")

    zero_declaration = ["typeattribute", zero_attribute]
    zero_definitions = [f for f in normal
                        if f[0] == "typeattributeset" and f[1] == zero_attribute]
    if (zero_attribute == attribute or zero_attribute not in membership.attributes
            or len(zero_definitions) != 1):
        raise ValueError("The reviewed zero-vector group lacks one fixed definition")
    zero_definition = zero_definitions[0]
    zero_members = zero_definition[2]
    if (not isinstance(zero_members, list) or not 1 <= len(zero_members) <= 4096
            or any(not isinstance(v, str) or v not in membership.types for v in zero_members)
            or len(set(zero_members)) != len(zero_members) or source in zero_members):
        raise ValueError("The reviewed zero-vector group is not a bounded concrete preimage")
    zero_uses = [f for f in normal
                 if any(value == zero_attribute for nested in _walk(f)
                        for value in nested if isinstance(value, str))]
    if (len(zero_uses) != 2 or sum(f == zero_declaration for f in zero_uses) != 1
            or sum(f == zero_definition for f in zero_uses) != 1):
        raise ValueError("The reviewed zero-vector group has an authority-bearing use")

    remaining = sorted(set(members) - {source})
    restored_zero_members = sorted([*zero_members, source])
    virtual = []
    for form in normal:
        if form is definition:
            virtual.append(["typeattributeset", attribute, remaining])
        elif form is zero_definition:
            virtual.append(["typeattributeset", zero_attribute, restored_zero_members])
        else:
            virtual.append(form)
    if not concrete:
        virtual.append(literal)
    def cil(value):
        if isinstance(value, str):
            return value
        return "(" + " ".join(cil(part) for part in value) + ")"
    # Rebuild a separate membership resolver from the complete virtual type
    # vocabulary. The actual resolver remains intact for the final raw matrix.
    virtual_membership = Membership("\n".join(
        cil(f) for f in virtual if f[0] in {"type", "typeattribute", "typeattributeset"}))
    if (virtual_membership.types != membership.types
            or virtual_membership.attributes != membership.attributes
            or virtual_membership.member(attribute, source)
            or not virtual_membership.member(zero_attribute, source)):
        raise ValueError("The reviewed virtual membership changed its vocabulary")
    return virtual, virtual_membership, {
        "present": True, "attribute": attribute, "source": source, "target": target,
        "class": "file", "permissions": permissions, "sole_attribute_use": True,
        "members_before": len(members), "members_after": len(remaining),
        "members_before_commitment": _commitment(["type", name] for name in members),
        "members_after_commitment": _commitment(["type", name] for name in remaining),
        "restored_zero_attribute": zero_attribute,
        "zero_group_has_no_authority_use": True,
        "zero_members_before": len(zero_members),
        "zero_members_after": len(restored_zero_members),
        "zero_members_before_commitment": _commitment(["type", name] for name in zero_members),
        "zero_members_after_commitment": _commitment(["type", name] for name in restored_zero_members),
        "effective_authority_preserved_before_exact_subtraction": True,
        "existing_concrete_row_retained": bool(concrete),
    }


def _split_reviewed_loader_cache_grant(forms, membership):
    return _split_reviewed_derived_source_grant(
        forms, membership, "droidloom_policy_loader",
        "p4_linux_console_ld_cache_native_config_t",
        ["getattr", "map", "open", "read"], False, "p4_console_preserved_12_0")


def _split_reviewed_executor_mount_grant(forms, membership):
    return _split_reviewed_derived_source_grant(
        forms, membership, "p4_linux_service_executor_t",
        "p4_linux_remount_mount_exec_t",
        ["execute", "getattr", "map", "open", "read"], True, "p4_remount_preserved_1_0")


def _subtract_native_grants(forms, membership):
    """Remove only the fixed concrete source-proven delta; return its preimage."""
    normal = _normalise_allow(forms)
    rows = {(form[1], form[2], form[3][0]): form
            for form in normal if form[0] == "allow"}
    matrix = []
    for source, target, cls, permissions in REVIEWED_NATIVE_GRANTS:
        key = (source, target, cls)
        keys = [key]
        if source == target:
            keys.append((source, "self", cls))
        matching = [rows[candidate] for candidate in keys if candidate in rows]
        if len(matching) > 1:
            raise ValueError("Duplicate semantic concrete reviewed native grant")
        if source not in membership.types or target not in membership.types or not matching:
            raise ValueError("Missing concrete reviewed native grant")
        row = matching[0]
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
    if len(expected) != 29:
        raise ValueError("The reviewed TCGETS2 audit roster changed")
    added = {}
    remaining = []
    for form in forms:
        if form[0] == "dontauditx":
            if len(form) != 4 or any(not isinstance(x, str) for x in form[1:3]):
                raise ValueError("Non-concrete or malformed TCGETS2 audit rule")
            pair = _concrete_pair(membership, form)
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
        raise ValueError("The final policy lacks the exact 29 TCGETS2 audit rules")
    virtual, virtual_membership, derived_split = _split_reviewed_loader_cache_grant(
        remaining, membership)
    virtual, virtual_membership, remount_split = _split_reviewed_executor_mount_grant(
        virtual, virtual_membership)
    baseline, grants = _subtract_native_grants(virtual, virtual_membership)
    projection = verify_projection(baseline, virtual_membership)
    actual = projection["canonical_original_commitments"]
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
        "all_original_type_non_audit_forms_preserved": True,
        "original_authority_projection": projection,
        "new_component_runtime_qualified": False,
        "all_original_audit_forms_preserved": True,
        "new_dontaudit_pairs": len(matrix),
        "ioctl_u16": PROBE,
        "class": "file",
        "matrix": matrix,
        "matrix_sha256": hashlib.sha256(
            json.dumps(matrix, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "reviewed_native_grants": grants,
        "reviewed_derived_source_split": derived_split,
        "reviewed_remount_source_split": remount_split,
        "reviewed_directory_ioctl": {
            "source": QUOTA_PAIR[0], "target": QUOTA_PAIR[1], "class": "dir",
            "commands": [QUOTA_COMMAND], "baseline_xperm_rules": 0,
        },
        "runtime_audit_suppression_observed": False,
    }
