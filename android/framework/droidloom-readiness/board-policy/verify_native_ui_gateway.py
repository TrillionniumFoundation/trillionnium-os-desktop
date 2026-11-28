"""Closed policy boundary for the factory-owned normal native UI commands.

Expected Android inheritance is evaluated from the nine pinned original CIL
inputs with source-owned membership for these four new types. No candidate
allow row for a new UI type becomes an expected permission. Old normal authority
is independently checked by the immutable original projection. The explicit
board additions below are independent of linux-application-roles.cil.
"""
import hashlib
import json
import re

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import _classes, _context
from derive_shared_payload_cgroup_policy import parse_expression
from verify_native_original_projection import (
    ConcreteSets, forms, verify_projection, canonical,
)
from verify_native_engine_observer import aliases as fixed_normal_aliases

UI = "droidloom_native_ui"
READ = "droidloom_native_ui_read"
TEMP = {UI: "droidloom_native_ui_tmpfs", READ: "droidloom_native_ui_read_tmpfs"}
NEW = frozenset({UI, READ, *TEMP.values()})
ACTORS = (UI, READ)
AV = frozenset({"allow", "allowx", "auditallow", "dontaudit", "auditallowx", "dontauditx"})
EXTENDED = frozenset({"allowx", "auditallowx", "dontauditx"})
TRANSITIONS = frozenset({"typetransition", "typechange", "typemember",
                         "roletransition", "rangetransition"})
ORIGINAL_DIRS = (
    "rootfs", "system_file", "system_lib_file", "system_linker_exec",
    "apex_mnt_dir", "linkerconfig_file", "system_data_root_file",
    "system_data_file", "apk_data_file",
)
SOURCE_PATHS = (
    "runtime/droidloom-supervisor/src/control.rs",
    "runtime/droidloom-supervisor/src/control_progress.rs",
    "runtime/droidloom-supervisor/src/control_identity.rs",
    "runtime/droidloom-supervisor/src/native_application_ui_entry.rs",
    "runtime/droidloom-supervisor/src/native_application_ui_protocol.rs",
    "runtime/droidloom-supervisor/src/production_application.rs",
    "runtime/droidloom-supervisor/src/production_application_executable.rs",
    "runtime/droidloom-supervisor/src/production_application_worker.rs",
    "runtime/droidloom-supervisor/src/production_early_application.rs",
    "runtime/droidloom-supervisor/src/production_early_query_assets.rs",
    "runtime/droidloom-supervisor/src/production_early_release.rs",
    "runtime/droidloom-supervisor/src/production_package.rs",
    "runtime/droidloom-supervisor/src/production_package_peer.rs",
    "runtime/droidloom-supervisor/src/lib.rs",
    "runtime/droidloom-supervisor/src/native_application_ui_gateway.rs",
    "runtime/droidloom-supervisor/src/control_identity_native_ui.rs",
    "runtime/droidloom-supervisor/src/production_native_ui_peer.rs",
    "runtime/droidloom-supervisor/src/production_application_native_ui.rs",
    "runtime/droidloom-supervisor/src/production_application_operation.rs",
    "runtime/droidloom-supervisor/src/production_application_factory_query.rs",
    "runtime/droidloom-supervisor/src/production_application_exec_stop.rs",
    "runtime/droidloom-supervisor/src/production_early_application_control.rs",
    "runtime/droidloom-supervisor/src/production_query_input_profile.rs",
    "runtime/droidloom-supervisor/src/production_runtime_query_assets.rs",
    "runtime/droidloom-supervisor/src/production_metadata_observer.rs",
    "runtime/droidloom-early-boot/instance_query.c",
    "tools/droidloom-update/src/coherent_kernel_query.rs",
    "tools/droidloom-ubuntu-fixture/src/boot_query.rs",
    "tools/droidloom-ubuntu-fixture/src/boot_query_image.rs",
)
POLICY_PATHS = (
    "linux-application-roles.cil", "linux-query-owner.cil",
    "linux-fixed-metadata-observer.cil",
    "apparmor/droidloom-production-android",
    "apparmor/droidloom-production-broker",
    "apparmor/droidloom-instance-factory",
)


def pin(path):
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def source_inputs(here):
    return [*(here.parents[3] / p for p in SOURCE_PATHS),
            *(here / p for p in POLICY_PATHS)]


def source_contract(here):
    paths = source_inputs(here)
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("Native UI normal source input is missing or indirect")
    return {"schema": "droidloom.native-ui-policy-sources.v1",
            "files": {str(p.relative_to(here.parents[3])): pin(p) for p in paths},
            "fixed_android_roles": {UI: 2000, READ: 0},
            "initial_and_guest_capabilities": [],
            "caller_chosen_argv_path_label_uid": False,
            "runtime_qualified": False}


def _original_inputs(here, paths):
    release = json.loads((here / "cp3a-kernel-handle-inputs.json").read_text())
    if len(paths) != 9 or len({str(p.resolve()) for p in paths}) != 9:
        raise ValueError("Native UI inheritance requires the original nine CIL inputs")
    actual = [{"path": str(p), **pin(p)} for p in paths]
    if sorted(p["sha256"] for p in actual) != sorted(
            p["sha256"] for p in release["android_inputs"]):
        raise ValueError("Native UI Android inheritance source differs")
    text = "\n".join(p.read_text() for p in paths)
    if re.search(r"\((?:booleanif|tunableif)\b", text):
        raise ValueError("Conditional original UI inheritance is not modeled")
    return text, actual


def _expected_membership(original, final):
    """Evaluate new membership from original source, never from final new rows.

    The already-verified old projection supplies the old normal type extension
    to Android attributes. Other normal components retain their own complete
    verifiers. None of the four UI types is admitted through that extension.
    """
    initial = Membership(original)
    sets = ConcreteSets(final)
    lines = [original]
    lines += ["(type " + t + ")" for t in sorted(final.types - initial.types)]
    for attribute in sorted(initial.attributes & final.attributes):
        other = sets.members(attribute) - initial.types - NEW
        if other:
            lines.append("(typeattributeset " + attribute + " (" +
                         " ".join(sorted(other)) + "))")
    lines += [
        "(typeattributeset domain (" + UI + " " + READ + "))",
        "(typeattributeset coredomain (" + UI + " " + READ + "))",
        "(typeattributeset mlstrustedsubject (" + READ + "))",
        "(typeattributeset file_type (" + " ".join(TEMP.values()) + "))",
    ]
    expected = Membership("\n".join(lines))
    for attribute in sorted(initial.attributes & final.attributes):
        for selected in NEW:
            if expected.member(attribute, selected) != final.member(attribute, selected):
                raise ValueError("Native UI original-attribute inheritance differs: " +
                                 repr((attribute, selected)))
    # Board membership is the existing closed Contacts role/file membership,
    # with only the independently declared cmd/UI pair added.
    refs = {UI: "droidloom_contacts_read", READ: "droidloom_contacts_read",
            TEMP[UI]: "droidloom_contacts_tmpfs",
            TEMP[READ]: "droidloom_contacts_tmpfs"}
    if not set(refs.values()) <= final.types:
        raise ValueError("The fixed normal query reference types disappeared")
    for attribute in sorted(final.attributes - initial.attributes):
        for selected, reference in refs.items():
            wanted = final.member(attribute, reference)
            if attribute in ("p4_native_ui_queries", "p4_closed_cmd_queries"):
                wanted = selected in ACTORS
            if final.member(attribute, selected) != wanted:
                raise ValueError("Native UI board membership differs: " +
                                 repr((attribute, selected, wanted)))
    return expected, initial


def _permissions(expression, vocabulary):
    universe = set(vocabulary)
    if isinstance(expression, str):
        if expression not in universe:
            raise ValueError("Unknown native UI permission: " + expression)
        return {expression}
    if not isinstance(expression, list) or not expression:
        raise ValueError("Empty or invalid native UI permission expression")
    op, *args = expression
    if op == "all":
        if args:
            raise ValueError("Invalid all permission expression")
        return universe
    if op == "not":
        if len(args) != 1:
            raise ValueError("Invalid permission complement")
        return universe - _permissions(args[0], vocabulary)
    if op in ("or", "and", "xor"):
        if not args or (op == "xor" and len(args) != 2):
            raise ValueError("Invalid permission Boolean expression")
        values = [_permissions(x, vocabulary) for x in args]
        result = values[0]
        for value in values[1:]:
            result = result | value if op == "or" else (
                result & value if op == "and" else result ^ value)
        return result
    result = set()
    for item in expression:
        result.update(_permissions(item, vocabulary))
    return result


def _commands(value):
    if isinstance(value, str):
        number = int(value, 0)
        if not 0 <= number <= 0xffff:
            raise ValueError("UI extended command exceeds the 16-bit ABI")
        return 1 << number
    if not isinstance(value, list) or not value:
        raise ValueError("Invalid UI extended command expression")
    if value[0] == "range":
        if len(value) != 3:
            raise ValueError("Invalid UI extended range")
        first, last = int(value[1], 0), int(value[2], 0)
        if not 0 <= first <= last <= 0xffff:
            raise ValueError("Invalid UI extended range limits")
        return ((1 << (last - first + 1)) - 1) << first
    if value[0] == "not":
        if len(value) != 2:
            raise ValueError("Invalid UI extended complement")
        return ((1 << 65536) - 1) ^ _commands(value[1])
    result = 0
    for item in value:
        result |= _commands(item)
    return result


def _merge(table, key, value):
    if not value:
        return
    if isinstance(value, int):
        table[key] = table.get(key, 0) | value
    else:
        table.setdefault(key, set()).update(value)


def _rule_forms(text, operations):
    count = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if not any(line.startswith("(" + op + " ") for op in operations):
            continue
        form = parse_expression(line)
        count += 1
        yield form
    expected = sum(text.count("(" + op + " ") for op in operations)
    if count != expected:
        raise ValueError("Native UI authority contains an unmodeled nested rule")


def _raw(text, membership, classes):
    sets = ConcreteSets(membership)
    result = {}
    for form in _rule_forms(text, AV):
        if len(form) != 4:
            raise ValueError("Invalid native UI raw AV statement")
        op, source, target, value = form
        sources = sets.members(source)
        selected_sources = sources & NEW
        targets = None if target == "self" else sets.members(target)
        selected_targets = set() if targets is None else targets & NEW
        if not selected_sources and not selected_targets:
            continue
        if op in EXTENDED:
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError("Invalid native UI extended AV statement")
            kind, cls, names = value
            if kind not in ("ioctl", "nlmsg") or cls not in classes:
                raise ValueError("Unknown native UI extended operation")
            rights = _commands(names)
        else:
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("Invalid native UI class permission statement")
            cls, names = value
            if cls not in classes:
                raise ValueError("Unknown native UI class")
            kind = ""
            rights = _permissions(names, classes[cls])
        for s in selected_sources:
            for t in ({s} if targets is None else targets):
                _merge(result, (op, s, t, cls, kind), rights)
        if targets is not None:
            for s in sources - NEW:
                for t in selected_targets:
                    _merge(result, (op, s, t, cls, kind), rights)
    return result


def _explicit_board():
    result = {}
    def add(s, t, cls, names):
        _merge(result, ("allow", s, t, cls, ""), set(names.split()))
    for actor in ACTORS:
        add("droidloom_query_birth", actor, "process", "transition")
        add("droidloom_query_birth", actor, "process2", "nnp_transition nosuid_transition")
        add("kernel", actor, "process", "getattr ptrace sigkill sigstop")
        add(actor, "kernel", "fd", "use")
        add(actor, "kernel", "process", "sigchld")
        add(actor, "droidloom_query_io", "fd", "use")
        add(actor, "droidloom_query_io", "fifo_file", "getattr write")
        add(actor, "null_device", "chr_file", "getattr read")
        add(actor, actor, "process", "fork sigchld getcap")
        add(actor, actor, "dir", "getattr search")
        add(actor, actor, "file", "getattr open read")
        add(actor, actor, "lnk_file", "getattr read")
        for target in ("proc", "device", "p4_linux_query_mount_t",
                       "droidloom_query_tmpfs_t", *ORIGINAL_DIRS):
            add(actor, target, "dir", "getattr search")
        for target in ("proc", "rootfs", "system_file", "apex_mnt_dir"):
            add(actor, target, "lnk_file", "getattr read")
        for target in ("droidloom_query_tmpfs_t", "labeledfs"):
            add(actor, target, "filesystem", "getattr")
        for target in ("system_file", "system_lib_file", "system_linker_exec"):
            add(actor, target, "file", "getattr open read map execute")
        for target in ("droidloom_query_exec", "droidloom_provider_exec"):
            add(actor, target, "file", "getattr open read map execute entrypoint")
        for target in ("droidloom_provider_jar", "linkerconfig_file",
                       "properties_serial", "default_prop",
                       "exported_default_prop", "servicemanager_prop", "dalvik_prop"):
            add(actor, target, "file", "getattr open read map")
        for target in ("apex_info_file", "apk_data_file"):
            add(actor, target, "file", "getattr open read")
        add(actor, "properties_device", "dir", "getattr search")
        add(actor, "binder_device", "chr_file", "getattr open read write map ioctl")
        add(actor, "servicemanager", "binder", "call transfer")
        add("servicemanager", actor, "binder", "transfer")
        add(actor, "system_server", "binder", "call transfer")
        add("system_server", actor, "binder", "call transfer")
        for target in ("activity_service", "package_service"):
            add(actor, target, "service_manager", "find")
        add("droidloom_metadata_observer", actor, "process", "getattr")
        add("droidloom_metadata_observer", actor, "dir", "getattr search open read")
        add("droidloom_metadata_observer", actor, "file", "getattr open read")
        add("droidloom_metadata_observer", actor, "lnk_file", "getattr read")
        temp = TEMP[actor]
        add(temp, "tmpfs", "filesystem", "associate")
        for cls in ("file", "memfd_file"):
            add(actor, temp, cls, "create getattr open read write map")
    add(UI, "input_service", "service_manager", "find")
    for target in ("window_service", "display_service", "surfaceflinger_service"):
        add(READ, target, "service_manager", "find")
    for target in ("surfaceflinger", "mediaprovider", "mediaprovider_app"):
        add(READ, target, "binder", "call transfer")
        add(target, READ, "binder", "call transfer")
        add(READ, target, "fd", "use")
    add(READ, "appdomain_tmpfs", "file", "getattr read map")
    return result


def _add_aliases(table, here):
    # These are fixed normal alias source/class vectors; the provider contract
    # is checked independently, and no final UI grant is consulted.
    for alias in fixed_normal_aliases(here):
        source, target, cls = alias["source"], alias["target"], alias["class"]
        for key, rights in list(table.items()):
            op, actor, obj, kind, extended = key
            if (actor in ACTORS and obj == source and kind == cls and
                    (op == "allow" or (op == "allowx" and extended == "ioctl"))):
                _merge(table, (op, actor, target, cls, extended), rights)


def _transition_rows(text, membership):
    sets = ConcreteSets(membership)
    out = set()
    for f in _rule_forms(text, TRANSITIONS):
        op = f[0]
        if op in ("typetransition", "typechange", "typemember"):
            if len(f) not in (5, 6):
                raise ValueError("Unmodeled native UI type transition")
            sources, targets = sets.members(f[1]), sets.members(f[2])
            output = f[-1]
            if not isinstance(output, str) or output not in membership.types:
                raise ValueError("Unmodeled native UI transition result")
            suffix = canonical(f[3:])
            if output in NEW:
                for s in sources:
                    for t in targets:
                        out.add((op, s, t, suffix))
            else:
                for s in sources & NEW:
                    for t in targets:
                        out.add((op, s, t, suffix))
                for s in sources - NEW:
                    for t in targets & NEW:
                        out.add((op, s, t, suffix))
        else:
            def names(x):
                if isinstance(x, str):
                    return {x}
                result = set()
                for y in x:
                    result.update(names(y))
                return result
            for name in names(f[1:]):
                if name in membership.types | membership.attributes and sets.members(name) & NEW:
                    raise ValueError("UI role/range transition is not a fixed factory entry")
    return out


def _table_rows(table):
    return [list(k) + [hex(v) if isinstance(v, int) else sorted(v)]
            for k, v in sorted(table.items())]


def _compare(actual, expected, name):
    if actual == expected:
        return
    differences = []
    for key in sorted(actual.keys() | expected.keys()):
        a, e = actual.get(key), expected.get(key)
        if a != e:
            def describe(v):
                return hex(v) if isinstance(v, int) else sorted(v or ())
            differences.append({"key": key, "actual": describe(a), "expected": describe(e)})
    raise ValueError("Native UI complete " + name + " differs: " +
                     json.dumps(differences[:80], sort_keys=True))


def verify_native_ui_gateway(library, binary, exported, here, android_inputs):
    source = source_contract(here)
    text = exported.read_text()
    if re.search(r"\((?:booleanif|tunableif)\b", text):
        raise ValueError("Conditional final native UI authority is not modeled")
    members = Membership(text)
    if not NEW <= members.types:
        raise ValueError("Normal native UI type inventory is incomplete")
    original_proof = verify_projection(forms(text), members)
    original, original_pins = _original_inputs(here, android_inputs)
    expected_members, _ = _expected_membership(original, members)
    classes = _classes(text)
    if classes != _classes(original):
        raise ValueError("Native UI changed the original class vocabulary")
    if any(len(v) != len(set(v)) or len(v) > 32 for v in classes.values()):
        raise ValueError("Invalid full native UI class vocabulary")
    actual_roles = set(re.findall(r'^\(roletype ([A-Za-z0-9_]+) ([A-Za-z0-9_]+)\)$', text, re.MULTILINE))
    for selected in NEW:
        wanted = {("object_r", selected)}
        if selected in ACTORS:
            wanted.add(("r", selected))
        if {(r, t) for r, t in actual_roles if t == selected} != wanted:
            raise ValueError("Native UI type gained an unreviewed role: " + selected)
    expected = _raw(original, expected_members, classes)
    for key, rights in _explicit_board().items():
        _merge(expected, key, rights)
    _add_aliases(expected, here)
    actual = _raw(text, members, classes)
    _compare(actual, expected, "raw allow/audit/extended authority")
    expected_transitions = _transition_rows(original, expected_members)
    for actor, temp in TEMP.items():
        for cls in ("file", "memfd_file"):
            expected_transitions.add(("typetransition", actor, "tmpfs",
                                      canonical([cls, temp])))
    transitions = _transition_rows(text, members)
    if transitions != expected_transitions:
        raise ValueError("Native UI complete transition closure differs: " +
                         repr((sorted(transitions - expected_transitions),
                               sorted(expected_transitions - transitions))))
    policy = ContextPolicy(library, binary)
    process_roles = {}
    for role, target in actual_roles:
        if role != "object_r":
            if target in process_roles and process_roles[target] != role:
                # Android types may also be authorized for system_r. The fixed
                # runtime query contexts use r; Linux services use system_r.
                process_roles[target] = "r" if ("r", target) in actual_roles else role
            else:
                process_roles[target] = role
    process_roles.update({UI: "r", READ: "r"})
    vectors = []
    def context(target, level):
        return _context(process_roles.get(target, "object_r"), target, level)
    def check(s, t, cls, sl, tl, rights, exact):
        vocabulary = classes[cls]
        _, bits = policy.permissions(cls, vocabulary)
        wanted = sum(bits[x] for x in rights)
        got = policy.context_av(context(s, sl), context(t, tl), cls, vocabulary)
        if got & ~wanted or (exact and got != wanted):
            raise ValueError("Native UI effective MLS boundary differs: " +
                             repr((s, t, cls, sl, tl, got, wanted, exact)))
        vectors.append([s, t, cls, sl, tl, got])
    allow = {(s, t, cls): rights
             for (op, s, t, cls, kind), rights in expected.items() if op == "allow"}
    for sl in LEVELS:
        for tl in LEVELS:
            for (s, t, cls), rights in sorted(allow.items()):
                exact = sl == tl == "s0"
                if s == READ and t == "appdomain_tmpfs" and cls == "file":
                    exact = True
                check(s, t, cls, sl, tl, rights, exact)
            for actor in ACTORS:
                for cls in sorted(classes):
                    if (actor, actor, cls) not in allow:
                        check(actor, actor, cls, sl, tl, set(), True)
                for target in ("app_data_file", "privapp_data_file", "system_app_data_file"):
                    body = set(classes["file"]) - {"getattr", "audit_access"}
                    _, bits = policy.permissions("file", sorted(body))
                    got = policy.context_av(context(actor, sl), context(target, tl),
                                            "file", sorted(body))
                    if got:
                        raise ValueError("Native UI gained application-private body access")
                    vectors.append([actor, target, "private-file-complement", sl, tl, got])
                for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
                    check(actor, actor, cls, sl, tl, set(), True)
    return {
        "schema": "droidloom.native-ui-gateway-policy-proof.v1",
        "source": source, "original_android_inputs": original_pins,
        "original_authority_projection": original_proof,
        "new_types": sorted(NEW), "fixed_query_roles": {UI: 2000, READ: 0},
        "expected_inheritance": "nine pinned original CIL inputs plus independent board table",
        "candidate_new_role_rows_used_as_expected": False,
        "complete_raw_vectors": len(NEW) * len(members.types) * len(classes) * 2,
        "nonzero_raw_and_extended_vectors": len(actual),
        "raw_and_extended_sha256": hashlib.sha256(
            json.dumps(_table_rows(actual), separators=(",", ":")).encode()).hexdigest(),
        "transitions": sorted(transitions),
        "category_pairs": len(LEVELS) ** 2,
        "effective_vectors_checked": len(vectors),
        "effective_matrix_sha256": hashlib.sha256(
            json.dumps(vectors, separators=(",", ":")).encode()).hexdigest(),
        "guest_capabilities": [], "private_app_data_bodies_allowed": False,
        "runtime_qualified": False, "production_ready": False,
    }
