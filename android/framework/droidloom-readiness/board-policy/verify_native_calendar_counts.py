"""Complete authority boundary for the fixed original Calendar count factory.

Expected permissions come from the pinned original Android sources and this
independent closed table. The candidate's new-role AV rows are never learned as
expectations. Original normal policy, MLS constraints and all old authorities
remain subject to the immutable projection verifier.
"""
import hashlib
import json
import re
from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import _classes, _context
from verify_native_original_projection import ConcreteSets, forms, verify_projection, canonical
from verify_native_ui_gateway import _original_inputs
from verify_native_engine_observer import aliases as fixed_normal_aliases
from derive_shared_payload_cgroup_policy import parse_expression

QUERY = "droidloom_calendar_counts"
META = "droidloom_calendar_metadata"
TEMP = "droidloom_calendar_tmpfs"
NEW = frozenset((QUERY, META, TEMP))
ACTORS = (QUERY, META)
HIGH = "s0:c512,c768"
AV = frozenset(("allow", "allowx", "auditallow", "dontaudit", "auditallowx", "dontauditx"))
EXTENDED = frozenset(("allowx", "auditallowx", "dontauditx"))
TRANSITIONS = frozenset(("typetransition", "typechange", "typemember", "roletransition", "rangetransition"))
ORIGINAL_DIRS = ("rootfs", "system_file", "system_lib_file", "system_linker_exec",
    "apex_mnt_dir", "linkerconfig_file", "system_data_root_file", "system_data_file", "apk_data_file")
SOURCE_PATHS = (
    "runtime/droidloom-supervisor/src/production_application_calendar_factory.rs",
    "runtime/droidloom-supervisor/src/production_application_factory_query.rs",
    "runtime/droidloom-supervisor/src/production_application_query_io.rs",
    "runtime/droidloom-supervisor/src/production_mac_self_attr.rs",
    "runtime/droidloom-supervisor/src/production_mac.rs",
    "runtime/droidloom-supervisor/src/production_application_protocol.rs",
    "runtime/droidloom-supervisor/src/production_application_exec_stop.rs",
    "runtime/droidloom-supervisor/src/production_metadata_observer.rs",
    "runtime/droidloom-supervisor/src/production_application_calendar_counts.rs",
    "runtime/droidloom-supervisor/src/production_application_operation.rs",
    "runtime/droidloom-supervisor/src/native_calendar_counts.rs",
    "runtime/droidloom-supervisor/src/production_application.rs",
    "runtime/droidloom-early-boot/instance_query.c",
    "runtime/droidloom-early-boot/instance_query.h",
    "android/framework/droidloom-input-bridge/src/com/android/droidloom/calendar/CalendarCounts.java",
)
POLICY_PATHS = ("linux-calendar-counts.cil", "linux-query-owner.cil",
    "linux-fixed-metadata-observer.cil", "ubuntu-dbus.cil", "ubuntu-systemd-unit-status.cil",
    "apparmor/droidloom-instance-factory",
    "apparmor/droidloom-production-android")

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
        raise ValueError("Calendar normal source input is missing or indirect")
    return {
        "schema": "droidloom.calendar-counts-policy-sources.v1",
        "files": {str(p.relative_to(here.parents[3])): pin(p) for p in paths},
        "query_guest_uid": 10017, "fixed_query_context": "u:r:" + QUERY + ":" + HIGH,
        "metadata_context": "u:r:" + META + ":" + HIGH,
        "stdio_origin": "independent actual kernel creator retained by original factory",
        "broker_receives_kernel_stdio_descriptors": False,
        "output_origin": "bounded actual factory pipe capture with complete EOF",
        "query_capabilities": [], "metadata_initial_capabilities": [],
        "metadata_cap_userns": ["sys_admin", "sys_ptrace"],
        "metadata_retained_capability": "SYS_PTRACE after the one held USERNS entry",
        "actual_database_label_observed": False,
        "runtime_qualified": False,
    }

DBUS_HELPER_ATTRIBUTE = "p4_closed_helpers_without_native_bus"
DBUS_CLOSED_HELPERS = frozenset((
    "droidloom_query_io", "droidloom_metadata_observer",
    "droidloom_instance_launcher", "droidloom_policy_loader",
))

def _require_fixed_dbus_helpers(here):
    text = (here / "ubuntu-dbus.cil").read_text()
    attribute = re.escape(DBUS_HELPER_ATTRIBUTE)
    if len(re.findall(r"\(\s*typeattribute\s+" + attribute + r"\s*\)", text)) != 1:
        raise ValueError("Fixed normal D-Bus helper declaration differs")
    if len(re.findall(r"\(\s*typeattributeset\s+" + attribute + r"\b", text)) != 1:
        raise ValueError("Fixed normal D-Bus helper definition differs")
    matches = re.findall(r"\(\s*typeattributeset\s+" + attribute +
                         r"\s+\(([^()]*)\)\s*\)", text)
    if len(matches) != 1:
        raise ValueError("Fixed normal D-Bus helper expression differs")
    values = matches[0].split()
    if len(values) != len(DBUS_CLOSED_HELPERS) or frozenset(values) != DBUS_CLOSED_HELPERS:
        raise ValueError("Fixed normal D-Bus helper members differ")

NATIVE_CLASSES = {
    "service": ("start", "stop", "status", "reload", "kill", "load", "enable", "disable"),
    "dbus": ("acquire_svc", "send_msg"),
}
NATIVE_CLASS_SOURCES = {
    "service": "ubuntu-systemd-unit-status.cil",
    "dbus": "ubuntu-dbus.cil",
}

def _require_fixed_native_classes(here):
    for name, permissions in NATIVE_CLASSES.items():
        text = (here / NATIVE_CLASS_SOURCES[name]).read_text()
        declaration = r"\(\s*class\s+" + re.escape(name) + r"\s+\(([^()]*)\)\s*\)"
        matches = re.findall(declaration, text)
        if (len(matches) != 1 or tuple(matches[0].split()) != permissions or
                len(re.findall(r"\(\s*class\s+" + re.escape(name) + r"\b", text)) != 1 or
                re.search(r"\(\s*classcommon\s+" + re.escape(name) + r"\b", text)):
            raise ValueError("Fixed normal native class declaration differs: " + name)

def _classes_after_normal_inputs(original, final):
    expected = _classes(original)
    if expected.keys() & NATIVE_CLASSES.keys():
        raise ValueError("Original Android class vocabulary contains a normal host addition")
    expected.update({name: list(permissions) for name, permissions in NATIVE_CLASSES.items()})
    actual = _classes(final)
    if actual != expected:
        raise ValueError("Calendar class vocabulary differs from original plus fixed normal host classes")
    return actual

def _expected_membership(original, final):
    initial = Membership(original)
    sets = ConcreteSets(final)
    lines = [original]
    lines += ["(type " + t + ")" for t in sorted(final.types - initial.types)]
    for attr in sorted(initial.attributes & final.attributes):
        other = sets.members(attr) - initial.types - NEW
        if other:
            lines.append("(typeattributeset " + attr + " (" + " ".join(sorted(other)) + "))")
    # No Android process inheritance; the one owned anonymous memory type is
    # only a file_type. Original negative-set membership is still evaluated.
    lines.append("(typeattributeset file_type (" + TEMP + "))")
    expected = Membership("\n".join(lines))
    for attr in sorted(initial.attributes & final.attributes):
        for selected in NEW:
            if expected.member(attr, selected) != final.member(attr, selected):
                raise ValueError("Calendar original-attribute membership differs: " + repr((attr, selected)))
    refs = {QUERY: "droidloom_metadata_observer", META: "droidloom_metadata_observer",
            TEMP: "droidloom_contacts_tmpfs"}
    if not set(refs.values()) <= final.types:
        raise ValueError("Calendar fixed normal reference types disappeared")
    for attr in sorted(final.attributes - initial.attributes):
        # ubuntu-dbus.cil names exactly four legacy helpers. The new Calendar
        # actors have their own explicit no-D-Bus boundary and are not aliases
        # of the older low-category metadata observer.
        if attr == DBUS_HELPER_ATTRIBUTE:
            if sets.members(attr) != DBUS_CLOSED_HELPERS:
                raise ValueError("Fixed normal D-Bus helper members changed")
        for selected, ref in refs.items():
            wanted = selected in DBUS_CLOSED_HELPERS if attr == DBUS_HELPER_ATTRIBUTE else final.member(attr, ref)
            if final.member(attr, selected) != wanted:
                raise ValueError("Calendar board membership differs: " + repr((attr, selected)))
    for attr in ("domain", "coredomain", "appdomain", "mlstrustedsubject", "mlstrustedobject"):
        if any(final.member(attr, t) for t in NEW):
            raise ValueError("Calendar acquired forbidden Android or trusted inheritance")
    return expected

def _permissions(expression, vocabulary):
    universe = set(vocabulary)
    if isinstance(expression, str):
        if expression not in universe:
            raise ValueError("Unknown Calendar permission: " + expression)
        return {expression}
    if not isinstance(expression, list) or not expression:
        raise ValueError("Empty or invalid Calendar permission expression")
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
        raise ValueError("Calendar authority contains an unmodeled nested rule")


def _raw(text, membership, classes):
    sets = ConcreteSets(membership)
    result = {}
    for form in _rule_forms(text, AV):
        if len(form) != 4:
            raise ValueError("Invalid Calendar raw AV statement")
        op, source, target, value = form
        sources = sets.members(source)
        selected_sources = sources & NEW
        targets = None if target == "self" else sets.members(target)
        selected_targets = set() if targets is None else targets & NEW
        if not selected_sources and not selected_targets:
            continue
        if op in EXTENDED:
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError("Invalid Calendar extended AV statement")
            kind, cls, names = value
            if kind not in ("ioctl", "nlmsg") or cls not in classes:
                raise ValueError("Unknown Calendar extended operation")
            rights = _commands(names)
        else:
            if not isinstance(value, list) or len(value) != 2:
                raise ValueError("Invalid Calendar class permission statement")
            cls, names = value
            if cls not in classes:
                raise ValueError("Unknown Calendar class")
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
                raise ValueError("Unmodeled Calendar type transition")
            sources, targets = sets.members(f[1]), sets.members(f[2])
            output = f[-1]
            if not isinstance(output, str) or output not in membership.types:
                raise ValueError("Unmodeled Calendar transition result")
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
    raise ValueError("Calendar complete " + name + " differs: " +
                     json.dumps(differences[:80], sort_keys=True))


def _explicit_board():
    out = {}
    def add(s, t, cls, rights):
        _merge(out, ("allow", s, t, cls, ""), set(rights.split()))
    add("droidloom_query_birth", QUERY, "process", "transition")
    add("droidloom_query_birth", QUERY, "process2", "nnp_transition nosuid_transition")
    add("kernel", QUERY, "process", "getattr ptrace sigkill sigstop")
    add(QUERY, "droidloom_provider_exec", "file", "getattr open read map execute entrypoint")
    add(QUERY, "droidloom_provider_jar", "file", "getattr open read map")
    add(QUERY, "kernel", "fd", "use")
    add(QUERY, "kernel", "process", "sigchld")
    add(QUERY, "kernel", "fifo_file", "getattr write")
    add(QUERY, "null_device", "chr_file", "getattr read")
    add(QUERY, QUERY, "process", "fork sigchld getcap")
    for actor in ACTORS:
        add(actor, actor, "dir", "getattr search")
        add(actor, actor, "file", "getattr open read")
        add(actor, actor, "lnk_file", "getattr read")
        add(actor, "proc", "dir", "getattr search")
        add(actor, "proc", "lnk_file", "getattr read")
        for t in ("labeledfs", "droidloom_query_tmpfs_t"):
            add(actor, t, "filesystem", "getattr")
    for t in ("device", "p4_linux_query_mount_t", "droidloom_query_tmpfs_t", *ORIGINAL_DIRS):
        add(QUERY, t, "dir", "getattr search")
    for t in ("rootfs", "system_file", "apex_mnt_dir"):
        add(QUERY, t, "lnk_file", "getattr read")
    for t in ("system_file", "system_lib_file", "system_linker_exec"):
        add(QUERY, t, "file", "getattr open read map execute")
    for t in ("linkerconfig_file", "properties_serial", "default_prop",
              "exported_default_prop", "dalvik_prop"):
        add(QUERY, t, "file", "getattr open read map")
    add(QUERY, "properties_device", "dir", "getattr search")
    add(QUERY, "binder_device", "chr_file", "getattr open read write map ioctl")
    add(QUERY, "privapp_data_file", "dir", "getattr search")
    add(QUERY, "privapp_data_file", "file", "getattr open read lock map")
    add(TEMP, "tmpfs", "filesystem", "associate")
    for cls in ("file", "memfd_file"):
        add(QUERY, TEMP, cls, "create getattr open read write map")
    add("kernel", META, "process", "dyntransition getattr sigkill")
    add(META, "kernel", "process", "getattr sigchld")
    add(META, "kernel", "fd", "use")
    add(META, "kernel", "file", "getattr open read")
    add(META, "kernel", "lnk_file", "getattr read")
    add(META, "kernel", "fifo_file", "getattr read")
    add(META, "kernel", "unix_stream_socket", "getattr getopt read write")
    add("kernel", META, "fd", "use")
    add("droidloom_broker", META, "fd", "use")
    add(META, META, "process", "getcap setcap")
    add(META, META, "cap_userns", "sys_admin sys_ptrace")
    add(META, QUERY, "process", "getattr")
    add(META, QUERY, "dir", "getattr search open read")
    add(META, QUERY, "file", "getattr open read")
    add(META, QUERY, "lnk_file", "getattr read")
    add(META, "droidloom_provider_exec", "file", "getattr open read")
    add(META, "rootfs", "dir", "getattr open read")
    add(META, "system_file", "dir", "getattr")
    add(META, "p4_kernel_ns_handle_t", "file", "getattr open read ioctl")
    _merge(out, ("allowx", META, "p4_kernel_ns_handle_t", "file", "ioctl"), 1 << 0xb703)
    add(META, "p4_kernel_pid_handle_t", "file", "getattr")
    for t in ("p4_kernel_ns_handle_t", "proc", "tmpfs"):
        add(META, t, "filesystem", "getattr")
    return out

def _add_aliases(table, here):
    for alias in fixed_normal_aliases(here):
        source, target, cls = alias["source"], alias["target"], alias["class"]
        for key, rights in list(table.items()):
            op, actor, obj, kind, extended = key
            if actor in ACTORS and obj == source and kind == cls and (
                    op == "allow" or (op == "allowx" and extended == "ioctl")):
                _merge(table, (op, actor, target, cls, extended), rights)

def verify_calendar_counts(library, binary, exported, here, android_inputs):
    source = source_contract(here)
    text = exported.read_text()
    if re.search(r"\((?:booleanif|tunableif)\b", text):
        raise ValueError("Conditional Calendar authority is not modeled")
    members = Membership(text)
    if not NEW <= members.types:
        raise ValueError("Calendar type inventory is incomplete")
    original_proof = verify_projection(forms(text), members)
    original, original_pins = _original_inputs(here, android_inputs)
    expected_members = _expected_membership(original, members)
    classes = _classes_after_normal_inputs(original, text)
    roles = set(re.findall(r"^\(roletype ([A-Za-z0-9_]+) ([A-Za-z0-9_]+)\)$", text, re.MULTILINE))
    for t in NEW:
        wanted = {("object_r", t)} | ({("r", t)} if t in ACTORS else set())
        if {(r, x) for r, x in roles if x == t} != wanted:
            raise ValueError("Calendar role assignment differs: " + t)
    expected = _raw(original, expected_members, classes)
    for key, rights in _explicit_board().items():
        _merge(expected, key, rights)
    _add_aliases(expected, here)
    actual = _raw(text, members, classes)
    _compare(actual, expected, "raw allow/audit/extended authority")
    transitions = _transition_rows(text, members)
    wanted_transitions = _transition_rows(original, expected_members)
    for cls in ("file", "memfd_file"):
        wanted_transitions.add(("typetransition", QUERY, "tmpfs", canonical([cls, TEMP])))
    if transitions != wanted_transitions:
        raise ValueError("Calendar complete transition closure differs")
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
            raise ValueError("Calendar effective MLS boundary differs: " +
                repr((s, t, cls, sl, tl, got, wanted, exact)))
        vectors.append([s, t, cls, sl, tl, got])
        return got
    allow = {(s,t,c):v for (op,s,t,c,k),v in expected.items() if op == "allow"}
    levels = tuple(dict.fromkeys((*LEVELS, HIGH, "s0:c512", "s0:c513,c769")))
    for sl in levels:
        for tl in levels:
            for (s,t,cls),rights in sorted(allow.items()):
                check(s,t,cls,sl,tl,rights,sl == tl)
            for actor in ACTORS:
                for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
                    rights = {"sys_admin", "sys_ptrace"} if actor == META and cls == "cap_userns" else set()
                    check(actor,actor,cls,sl,tl,rights)
                for target in ("app_data_file","privapp_data_file","system_app_data_file"):
                    if actor == QUERY and target == "privapp_data_file":
                        # Android's original MLS rules require dominance for
                        # this open. Do not assert equality that the policy
                        # does not enforce; the source path/UID remain fixed.
                        forbidden = set(classes["file"]) - {"getattr","open","read","lock","map","audit_access"}
                    else:
                        forbidden = set(classes["file"]) - {"getattr","audit_access"}
                    got = policy.context_av(ctx(actor,sl),ctx(target,tl),"file",sorted(forbidden))
                    if got:
                        raise ValueError("Calendar gained unreviewed private-body authority")
                    vectors.append([actor,target,"forbidden-file",sl,tl,got])
    # Real runtime category directions, including the pre-exec high birth.
    check("kernel",META,"process","s0",HIGH,allow[("kernel",META,"process")])
    check("droidloom_query_birth",QUERY,"process",HIGH,HIGH,{"transition"})
    check(META,QUERY,"process",HIGH,HIGH,{"getattr"})
    check(META,QUERY,"process","s0",HIGH,set())
    check(QUERY,"kernel","fifo_file",HIGH,"s0",{"getattr","write"})
    check(META,"kernel","fifo_file",HIGH,"s0",{"getattr","read"})

    original_members = Membership(original)
    for device in ("binder_device", "null_device"):
        if not original_members.member("mlstrustedobject", device):
            raise ValueError("Original Calendar driver/null MLS exemption disappeared")
    check(QUERY,"binder_device","chr_file",HIGH,"s0",{"getattr","open","read","write","map","ioctl"})
    check(QUERY,"null_device","chr_file",HIGH,"s0",{"getattr","read"})
    for cls in ("file", "memfd_file"):
        check(QUERY,TEMP,cls,HIGH,HIGH,{"create","getattr","open","read","write","map"})
    # The original memfd_file class is not assumed to share file's write-down
    # constraint. The owned type, fixed transition and no FD export remain the
    # boundary; exact private-DB categories are observed by the Java producer.

    check(QUERY,"privapp_data_file","file",HIGH,HIGH,{"getattr","open","read","lock","map"})
    _, file_bits = policy.permissions("file", classes["file"])
    if policy.context_av(ctx(QUERY,"s0"),ctx("privapp_data_file",HIGH),"file",classes["file"]) & file_bits["open"]:
        raise ValueError("Calendar low category can open the high private database")
    if policy.context_av(ctx(QUERY,HIGH),ctx("privapp_data_file","s0:c513,c769"),"file",classes["file"]) & file_bits["open"]:
        raise ValueError("Calendar unrelated categories can open the private database")
    for cls in ("capability","capability2"):
        check("kernel","kernel",cls,"s0","s0",
              set(policy.permissions(cls, classes[cls])[1]) - {"sys_ptrace"}, False)
    return {
        "schema":"droidloom.calendar-counts-policy-proof.v1",
        "source":source,"original_android_inputs":original_pins,
        "original_authority_projection":original_proof,
        "new_types":sorted(NEW),
        "expected_authority":"pinned original nine sources plus independent literal board table",
        "candidate_new_role_rows_used_as_expected":False,
        "raw_and_extended_sha256":hashlib.sha256(json.dumps(_table_rows(actual),separators=(",",":")).encode()).hexdigest(),
        "nonzero_raw_vectors":len(actual),"transitions":sorted(transitions),
        "category_pairs":len(levels)**2,"effective_vectors_checked":len(vectors),
        "effective_matrix_sha256":hashlib.sha256(json.dumps(vectors,separators=(",",":")).encode()).hexdigest(),
        "query_capabilities":[],
        "metadata_initial_capabilities":[],
        "metadata_cap_userns":["sys_admin","sys_ptrace"],
        "host_private_database_read":False,
        "actual_database_label_observed":False,
        "runtime_qualified":False,"production_ready":False,
    }
