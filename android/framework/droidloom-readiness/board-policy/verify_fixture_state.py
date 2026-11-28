"""Close the normal source-fixed Content.call state reader.

Original Android requires domain/coredomain for Binder/system code. Its
inheritance is evaluated from the nine pinned input CILs, never learned from
the candidate's new-role rows. The separate literal board table admits only
the finite factory/ART/Content transport. Whole original authority remains
subject to the immutable original projection. No runtime pass is inferred.
"""
import hashlib
import json
import re

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import _context
from derive_shared_payload_cgroup_policy import parse_expression
from verify_native_original_projection import ConcreteSets, forms, verify_projection, canonical
from verify_native_ui_gateway import _original_inputs
from verify_native_engine_observer import aliases as fixed_normal_aliases
from verify_native_calendar_counts import (
    _permissions, _commands, _merge, _rule_forms, _table_rows, _compare,
    _classes_after_normal_inputs, _require_fixed_dbus_helpers, _require_fixed_native_classes,
)

QUERY = "droidloom_fixture_state"
TEMP = "droidloom_fixture_state_tmpfs"
NEW = frozenset((QUERY, TEMP))
AV = frozenset(("allow", "allowx", "auditallow", "dontaudit", "auditallowx", "dontauditx"))
EXTENDED = frozenset(("allowx", "auditallowx", "dontauditx"))
TRANSITIONS = frozenset(("typetransition", "typechange", "typemember", "roletransition", "rangetransition"))
ORIGINAL_DIRS = ("rootfs", "system_file", "system_lib_file", "system_linker_exec",
    "apex_mnt_dir", "linkerconfig_file", "system_data_root_file", "system_data_file", "apk_data_file")
PACKAGES = (
    "org.droidloom.qa.saf.r12.na7f1de49e707c7a9",
    "org.droidloom.qa.documents.r12.n98116f3fbefcfc95",
    "org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03",
    "org.droidloom.qa.media.r12.nc92c3d79180955ef",
)
PROVIDER_SOURCE = "tools/droidloom-update/resources/prebuilt-helpers/sources/state/FixedStateProvider.java"
PROVIDER_PIN = {"bytes": 11630, "sha256": "f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545"}
SOURCE_PATHS = (
    "runtime/droidloom-supervisor/src/native_leaf_fixture.rs",
    "runtime/droidloom-supervisor/src/native_leaf_fixture_material.rs",
    "runtime/droidloom-supervisor/src/native_leaf_baseline.rs",
    "runtime/droidloom-supervisor/src/native_leaf_baseline_data.rs",
    "runtime/droidloom-supervisor/src/native_leaf_baseline_channel.rs",
    "runtime/droidloom-supervisor/src/prebuilt_native_helpers.rs",
    "runtime/droidloom-supervisor/src/control_identity_native_fixture.rs",
    "runtime/droidloom-supervisor/src/production_native_leaf_fixture.rs",
    "runtime/droidloom-supervisor/src/production_native_fixture_slot.rs",
    "runtime/droidloom-supervisor/src/production_application.rs",
    "runtime/droidloom-supervisor/src/production_application_worker.rs",
    "runtime/droidloom-supervisor/src/production_application_operation.rs",
    "runtime/droidloom-supervisor/src/production_application_factory_query.rs",
    "runtime/droidloom-supervisor/src/production_application_protocol.rs",
    "runtime/droidloom-supervisor/src/production_application_query_io.rs",
    "runtime/droidloom-supervisor/src/production_application_exec_stop.rs",
    "runtime/droidloom-supervisor/src/production_metadata_observer.rs",
    "runtime/droidloom-supervisor/src/production_query_input_profile.rs",
    "runtime/droidloom-supervisor/src/production_mac_self_attr.rs",
    "runtime/droidloom-supervisor/src/production_mac.rs",
    "runtime/droidloom-early-boot/instance_query.c",
    "runtime/droidloom-early-boot/instance_query.h",
    PROVIDER_SOURCE,
    "tools/droidloom-update/resources/prebuilt-helpers/build.py",
    "tools/droidloom-update/src/working_prebuilt_helpers.rs",
    "tools/droidloom-update/src/working_prebuilt_inputs.rs",
    "tools/droidloom-update/resources/prebuilt-helpers/sources/saf/documents_build.py",
    "tools/droidloom-update/resources/prebuilt-helpers/sources/features/documents_build.py",
    *("tools/droidloom-update/resources/prebuilt-helpers/products/state-r1/" + kind + "/" + name
      for kind in ("saf", "features", "rotation", "video")
      for name in ("MANIFEST.json", "SOURCE.json", "STATE-SOURCE.json")),
)
POLICY_PATHS = ("linux-fixture-state.cil", "linux-query-owner.cil",
    "linux-fixed-metadata-observer.cil", "linux-application-roles.cil",
    "ubuntu-dbus.cil", "ubuntu-systemd-unit-status.cil",
    "apparmor/droidloom-instance-factory", "apparmor/droidloom-production-android")


def pin(path):
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def source_inputs(here):
    return [*(here.parents[3] / p for p in SOURCE_PATHS), *(here / p for p in POLICY_PATHS)]


def source_contract(here):
    _require_fixed_dbus_helpers(here)
    _require_fixed_native_classes(here)
    paths = source_inputs(here)
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("Fixed state normal source is missing or indirect")
    root = here.parents[3]
    if pin(root / PROVIDER_SOURCE) != PROVIDER_PIN:
        raise ValueError("Fixed state provider source differs from its reviewed build")
    c = (root / "runtime/droidloom-early-boot/instance_query.c").read_text()
    if not re.search(r'case\s+15\s*:\s*return\s+"u:r:droidloom_fixture_state:s0"\s*;', c):
        raise ValueError("Fixed state C factory selector differs")
    material = (root / "runtime/droidloom-supervisor/src/native_leaf_fixture_material.rs").read_text()
    if any('"' + p + '"' not in material for p in PACKAGES):
        raise ValueError("Fixed state package roster differs")
    return {
        "schema": "droidloom.fixture-state-policy-source.v1",
        "files": {str(p.relative_to(root)): pin(p) for p in paths},
        "query_context": "u:r:" + QUERY + ":s0", "query_guest_uid": 2000,
        "apparmor": "droidloom-production-android (enforce)", "normal_apparmor_role_added": False,
        "factory_selector": 15, "stdio_creator": "droidloom_query_io",
        "metadata_observer": "droidloom_metadata_observer",
        "packages": list(PACKAGES), "provider_authorities": [p + ".state" for p in PACKAGES],
        "provider_target_sdk": 33, "expected_provider_type": "untrusted_app_32",
        "selected_system_sha256": "dc781249bb4724b7a0777e5077321b84576db46f61abb4b9086b81077bfd0ab4",
        "selected_plat_seapp_contexts": {
            "bytes": 5030, "sha256": "eb24be4624f15413dc51b49635087feff8c49aa7a1870d67488da36bd2364641"},
        "method": "state", "arg": None, "extras": "null or empty Bundle only",
        "output": "one bounded Bundle string; no provider descriptor or CursorWindow",
        "capabilities": [], "caller_selected_authority_argv_path_uid_or_label": False,
        "provider_process_label_actually_observed": False, "runtime_qualified": False,
    }


def _expected_membership(original, final):
    initial = Membership(original)
    sets = ConcreteSets(final)
    if not NEW <= final.types or not NEW <= sets.members("p4_all_board_owned"):
        raise ValueError("Fixed state concrete/board type roster differs")
    lines = [original]
    lines += ["(type " + t + ")" for t in sorted(final.types - initial.types)]
    for attribute in sorted(initial.attributes & final.attributes):
        other = sets.members(attribute) - initial.types - NEW
        if other:
            lines.append("(typeattributeset " + attribute + " (" + " ".join(sorted(other)) + "))")
    lines += ["(typeattributeset domain (" + QUERY + "))",
              "(typeattributeset coredomain (" + QUERY + "))",
              "(typeattributeset file_type (" + TEMP + "))"]
    expected = Membership("\n".join(lines))
    for attribute in sorted(initial.attributes & final.attributes):
        for selected in NEW:
            if expected.member(attribute, selected) != final.member(attribute, selected):
                raise ValueError("Fixed state original membership differs: " + repr((attribute, selected)))
    # Generated native aliases may group this role by its source-derived AV.
    # Their raw effect is checked below against the fixed alias providers;
    # no candidate grouping is used to invent an expected grant.
    for group in ("appdomain", "netdomain", "mlstrustedsubject", "mlstrustedobject",
                  "p4_linux_procs", "p4_linux_data", "p4_linux_native_processes",
                  "p4_linux_mac_roles", "p4_closed_runtime_queries", "p4_native_ui_queries",
                  "p4_fixed_metadata_tasks", "p4_working_actors", "p4_handle_owner",
                  "p4_closed_helpers_without_native_bus"):
        if group in final.attributes and any(final.member(group, t) for t in NEW):
            raise ValueError("Fixed state acquired an unrelated inherited role: " + group)
    return expected


def _raw(text, membership, classes):
    sets = ConcreteSets(membership)
    result = {}
    for form in _rule_forms(text, AV):
        if len(form) != 4:
            raise ValueError("Invalid fixed state raw AV statement")
        op, source, target, value = form
        sources = sets.members(source)
        selected_sources = sources & NEW
        targets = None if target == "self" else sets.members(target)
        selected_targets = set() if targets is None else targets & NEW
        if not selected_sources and not selected_targets:
            continue
        if op in EXTENDED:
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError("Invalid fixed state extended AV statement")
            kind, cls, names = value
            if kind not in ("ioctl", "nlmsg") or cls not in classes:
                raise ValueError("Unknown fixed state extended operation")
            rights = _commands(names)
        else:
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("Invalid fixed state class permission statement")
            cls, names = value
            if cls not in classes:
                raise ValueError("Unknown fixed state class")
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


def _transition_rows(text, membership):
    sets = ConcreteSets(membership)
    out = set()
    for f in _rule_forms(text, TRANSITIONS):
        op = f[0]
        if op in ("typetransition", "typechange", "typemember"):
            if len(f) not in (5, 6):
                raise ValueError("Unmodeled fixed state type transition")
            sources, targets = sets.members(f[1]), sets.members(f[2])
            output = f[-1]
            if not isinstance(output, str) or output not in membership.types:
                raise ValueError("Unmodeled fixed state transition result")
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
                    raise ValueError("Fixed state role/range transition is not a factory entry")
    return out


def _explicit_board():
    out = {}
    def add(source, target, kind, rights):
        _merge(out, ("allow", source, target, kind, ""), set(rights.split()))
    add("droidloom_query_birth", QUERY, "process", "transition")
    add("droidloom_query_birth", QUERY, "process2", "nnp_transition nosuid_transition")
    add("kernel", QUERY, "process", "getattr ptrace sigkill sigstop")
    add(QUERY, "droidloom_provider_exec", "file", "getattr open read map execute entrypoint")
    add(QUERY, "droidloom_provider_jar", "file", "getattr open read map")
    add(QUERY, "kernel", "fd", "use")
    add(QUERY, "kernel", "process", "sigchld")
    add(QUERY, "droidloom_query_io", "fd", "use")
    add(QUERY, "droidloom_query_io", "fifo_file", "getattr write")
    add(QUERY, "null_device", "chr_file", "getattr read")
    add(QUERY, QUERY, "process", "fork sigchld getcap")
    add(QUERY, QUERY, "dir", "getattr search")
    add(QUERY, QUERY, "file", "getattr open read")
    add(QUERY, QUERY, "lnk_file", "getattr read")
    add(QUERY, "proc", "dir", "getattr search")
    add(QUERY, "proc", "lnk_file", "getattr read")
    for target in ("device", "p4_linux_query_mount_t", "droidloom_query_tmpfs_t", *ORIGINAL_DIRS):
        add(QUERY, target, "dir", "getattr search")
    for target in ("droidloom_query_tmpfs_t", "labeledfs"):
        add(QUERY, target, "filesystem", "getattr")
    for target in ("rootfs", "system_file", "apex_mnt_dir"):
        add(QUERY, target, "lnk_file", "getattr read")
    for target in ("system_file", "system_lib_file", "system_linker_exec"):
        add(QUERY, target, "file", "getattr open read map execute")
    for target in ("linkerconfig_file", "properties_serial", "default_prop",
                   "exported_default_prop", "servicemanager_prop", "dalvik_prop"):
        add(QUERY, target, "file", "getattr open read map")
    add(QUERY, "apex_info_file", "file", "getattr open read")
    add(QUERY, "properties_device", "dir", "getattr search")
    add(QUERY, "binder_device", "chr_file", "getattr open read write map ioctl")
    add(QUERY, "servicemanager", "binder", "call transfer")
    add("servicemanager", QUERY, "binder", "transfer")
    for target in ("system_server", "untrusted_app_32"):
        add(QUERY, target, "binder", "call transfer")
        add(target, QUERY, "binder", "call transfer")
    add(QUERY, "activity_service", "service_manager", "find")
    add(TEMP, "tmpfs", "filesystem", "associate")
    for kind in ("file", "memfd_file"):
        add(QUERY, TEMP, kind, "create getattr open read write map")
    add("droidloom_metadata_observer", QUERY, "process", "getattr")
    add("droidloom_metadata_observer", QUERY, "dir", "getattr search open read")
    add("droidloom_metadata_observer", QUERY, "file", "getattr open read")
    add("droidloom_metadata_observer", QUERY, "lnk_file", "getattr read")
    return out


def _add_aliases(table, here):
    before = dict(table)
    for alias in fixed_normal_aliases(here):
        source, target, cls = alias["source"], alias["target"], alias["class"]
        for key, rights in before.items():
            op, actor, obj, kind, extended = key
            if actor == QUERY and obj == source and kind == cls and (
                    op == "allow" or (op == "allowx" and extended == "ioctl")):
                _merge(table, (op, actor, target, cls, extended), rights)


def _shape(text, members):
    roles = set(re.findall(r"^\(roletype ([A-Za-z0-9_]+) ([A-Za-z0-9_]+)\)$", text, re.MULTILINE))
    for t in NEW:
        wanted = {("object_r", t)} | ({("r", t)} if t == QUERY else set())
        if {(r, x) for r, x in roles if x == t} != wanted:
            raise ValueError("Fixed state role assignment differs: " + t)
    context_tags = {"genfscon", "filecon", "portcon", "nodecon", "netifcon", "fsuse",
                    "pirqcon", "iomemcon", "ioportcon", "pcidevicecon", "devicetreecon", "sidcontext"}
    def atoms(value):
        if isinstance(value, str):
            return {value}
        return set().union(*(atoms(x) for x in value))
    for f in forms(text):
        if f[0] in ("booleanif", "tunableif"):
            raise ValueError("Conditional fixed state authority is unmodeled")
        if f[0] in context_tags | {"typepermissive", "typebounds"} and atoms(f) & NEW:
            raise ValueError("Fixed state acquired a context, permissive or bounded role")
        if f[0] in ("constrain", "mlsconstrain", "validatetrans", "mlsvalidatetrans"):
            if atoms(f) & NEW or any(x.startswith("p4_fixture_state_") for x in atoms(f)):
                raise ValueError("Fixed state introduced a constraint exception")
    return roles


def verify_fixture_state(library, binary, exported, here, android_inputs):
    source = source_contract(here)
    text = exported.read_text()
    members = Membership(text)
    original_proof = verify_projection(forms(text), members)
    original, original_pins = _original_inputs(here, android_inputs)
    expected_members = _expected_membership(original, members)
    classes = _classes_after_normal_inputs(original, text)
    roles = _shape(text, members)
    expected = _raw(original, expected_members, classes)
    # Preserve the full independently derived original table before merging
    # the finite board additions. In particular the original core-domain
    # Binder statistics service grant must remain visible to reviewers.
    inherited_rows = _table_rows(expected)
    for key, rights in _explicit_board().items():
        _merge(expected, key, rights)
    _add_aliases(expected, here)
    actual = _raw(text, members, classes)
    _compare(actual, expected, "fixed state raw/audit/extended authority")
    transitions = _transition_rows(text, members)
    wanted_transitions = _transition_rows(original, expected_members)
    for kind in ("file", "memfd_file"):
        wanted_transitions.add(("typetransition", QUERY, "tmpfs", canonical([kind, TEMP])))
    if transitions != wanted_transitions:
        raise ValueError("Fixed state complete transition closure differs")
    policy = ContextPolicy(library, binary)
    process_roles = {}
    for role, t in roles:
        if role != "object_r":
            process_roles[t] = "r" if ("r", t) in roles else role
    def ctx(t, level):
        return _context(process_roles.get(t, "object_r"), t, level)
    vectors = []
    def check(s, t, cls, sl, tl, rights, exact=True):
        vocabulary = classes[cls]
        _, bits = policy.permissions(cls, vocabulary)
        wanted = sum(bits[x] for x in rights)
        got = policy.context_av(ctx(s, sl), ctx(t, tl), cls, vocabulary)
        if got & ~wanted or (exact and got != wanted):
            raise ValueError("Fixed state effective MLS boundary differs: " + repr((s,t,cls,sl,tl,got,wanted)))
        vectors.append([s,t,cls,sl,tl,got])
        return got
    allow = {(s,t,c):v for (op,s,t,c,k),v in expected.items() if op == "allow"}
    levels = tuple(dict.fromkeys((*LEVELS, "s0:c512,c768", "s0:c513,c769")))
    for sl in levels:
        for tl in levels:
            for (s,t,cls),rights in sorted(allow.items()):
                check(s,t,cls,sl,tl,rights,sl == tl)
            for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
                check(QUERY,QUERY,cls,sl,tl,set())
            for target in ("app_data_file", "privapp_data_file", "system_app_data_file", "appdomain_tmpfs"):
                forbidden = [x for x in ("open","read","write","append","map","execute","execute_no_trans","entrypoint")
                             if x in classes["file"]]
                got = policy.context_av(ctx(QUERY,sl),ctx(target,tl),"file",forbidden)
                if got:
                    raise ValueError("Fixed state acquired private or CursorWindow body access")
                vectors.append([QUERY,target,"forbidden-file",sl,tl,got])
            check(QUERY,"untrusted_app_32","fd",sl,tl,set())
    # Actual direction is shell s0 -> provider's UID-derived categories.
    for level in levels:
        check(QUERY,"untrusted_app_32","binder","s0",level,{"call","transfer"})
        check("untrusted_app_32",QUERY,"binder",level,"s0",{"call","transfer"})
    return {
        "schema": "droidloom.fixture-state-policy-proof.v1", "source": source,
        "original_android_inputs": original_pins, "original_authority_projection": original_proof,
        "new_types": sorted(NEW), "expected_authority": "nine original inputs plus independent literal board table",
        "candidate_new_role_rows_used_as_expected": False,
        "original_inherited_raw_and_extended_rows": inherited_rows,
        "original_inherited_raw_and_extended_sha256": hashlib.sha256(
            json.dumps(inherited_rows,separators=(",",":")).encode()).hexdigest(),
        "raw_and_extended_sha256": hashlib.sha256(json.dumps(_table_rows(actual),separators=(",",":")).encode()).hexdigest(),
        "nonzero_raw_vectors": len(actual), "transitions": sorted(transitions),
        "category_pairs": len(levels)**2, "effective_vectors_checked": len(vectors),
        "effective_matrix_sha256": hashlib.sha256(json.dumps(vectors,separators=(",",":")).encode()).hexdigest(),
        "provider_private_body_read": False, "provider_descriptors_received": False,
        "provider_process_label_actually_observed": False, "runtime_qualified": False, "production_ready": False,
    }
