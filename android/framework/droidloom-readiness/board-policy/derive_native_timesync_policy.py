"""Normal timesyncd closure; old actors retain the selected inode/port view.

Expected permissions come from source-owned tables and pre-link binaries.
The final binary is only a readback. No DNS, service or kernel action is run.
"""
import ctypes
import hashlib
import json
import re
import stat
from collections import defaultdict

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import _classes, _roles, _context, _constraint_targets
from derive_shared_payload_cgroup_policy import parse_expression, original_xperms, format_xperms

ROLE = "p4_linux_timesyncd_t"
ENTRY = "p4_linux_timesyncd_exec_t"
RUN = "p4_linux_timesyncd_run_t"
STATE = "p4_linux_timesyncd_state_t"
CONFIG = "p4_linux_timesyncd_config_t"
NSS = "p4_linux_timesyncd_nsswitch_t"
NETIF = "p4_linux_timesyncd_netif_t"
DNS = "p4_linux_timesyncd_dns_port_t"
EXECUTOR = "p4_linux_service_executor_t"
NETPLAN = "p4_linux_netplan_t"
ALIASES = [
    {"source": "p4_linux_runtime_lib_t", "target": ENTRY, "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": RUN, "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": RUN, "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": STATE, "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": STATE, "class": "file"},
    {"source": "p4_linux_native_config_t", "target": CONFIG, "class": "file"},
    {"source": "p4_linux_native_config_t", "target": NSS, "class": "file"},
    {"source": "p4_linux_rootdir_t", "target": NETIF, "class": "dir"},
    {"source": "p4_linux_native_data_t", "target": NETIF, "class": "file"},
]
PORT_ALIAS = {"source": "port", "target": DNS, "class": "tcp_socket"}
TRANSITIONS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")
CONSTRAINTS = ("(constrain ", "(mlsconstrain ", "(validatetrans ", "(mlsvalidatetrans ")
FULL_XPERMS = (1 << 65536) - 1
SOURCE_SCHEMA = "droidloom.native-timesync-source-closure.v1"

NEW_TYPES = {ROLE, ENTRY, RUN, STATE, CONFIG, NSS, NETIF, DNS}
FIXED_TRANSITIONS = {
    f"(typetransition {EXECUTOR} {ENTRY} process {ROLE})",
    f'(typetransition {EXECUTOR} p4_linux_systemd_run_t dir "timesync" {RUN})',
    f'(typetransition {EXECUTOR} p4_linux_systemd_state_parent_t dir "timesync" {STATE})',
    f"(typetransition {ROLE} {RUN} file p4_linux_native_data_t)",
    f'(typetransition {ROLE} {RUN} file "synchronized" {RUN})',
    f"(typetransition {ROLE} {STATE} file p4_linux_native_data_t)",
    f'(typetransition {ROLE} {STATE} file "clock" {STATE})',
}


def _new_transitions(lines):
    return {line for line in lines if line.startswith(TRANSITIONS) and
            set(re.findall(r"\b[a-zA-Z0-9_]+\b", line)) & NEW_TYPES}


def words(value):
    return set(value.split())


EXTRAS = {
    ("init_t", ENTRY, "file"): words("getattr open read execute map"),
    (EXECUTOR, ENTRY, "file"): words("getattr open read execute map"),
    (EXECUTOR, RUN, "dir"): words("getattr search open read create setattr"),
    (EXECUTOR, STATE, "dir"): words("getattr search open read create setattr ioctl"),
    (EXECUTOR, RUN, "file"): words("getattr setattr"),
    (EXECUTOR, STATE, "file"): words("getattr setattr"),
    ("init_t", RUN, "dir"): words("getattr search open read write remove_name rmdir"),
    ("init_t", RUN, "file"): words("getattr unlink"),
    (NETPLAN, NSS, "file"): words("getattr open read"),
}
XPERM_EXTRAS = {(EXECUTOR, STATE, "dir"): 1 << 0x581f}


def source_inputs(here):
    return [here / "native-timesync-source.json"]


def contract(here):
    value = json.loads((here / "native-timesync-source.json").read_text())
    if (value.get("schema") != SOURCE_SCHEMA or value.get("aliases") != ALIASES or
            value.get("port_alias") != PORT_ALIAS or
            value.get("actor") != ROLE or value.get("uid_gid") != [996, 996] or
            value.get("capabilities") != ["CAP_SYS_TIME"] or
            value.get("address_families") != ["AF_UNIX", "AF_INET", "AF_INET6"] or
            value.get("unit") != "/usr/lib/systemd/system/systemd-timesyncd.service" or
            value.get("unit_changed") is not False or
            value.get("normal_udp_bind") != ["0.0.0.0:0", "[::]:0"] or
            value.get("normal_ntp_destination_port") != 123 or
            value.get("dns_tcp_fallback_port") != 53 or
            value.get("netlink_probe_can_fail") is not True or
            value.get("runtime_qualified") is not False or
            value.get("original_policy_sha256") !=
            "334f85991aa8b821efbd8ee793083d0031ff1ffbb9bddac7e928c5fa2092d42c"):
        raise ValueError("Timesync normal source/role contract differs")
    sources = {
        "systemd": ("259.9-0ubuntu0.1+p4gentmp2", "normal-dsc-roundtrip-source", {
            "src/timesync/timesyncd.c", "src/timesync/timesyncd-manager.c",
            "src/timesync/timesyncd-conf.c", "src/timesync/timesyncd-bus.c",
            "src/libsystemd/sd-resolve/sd-resolve.c", "src/libsystemd/sd-network/sd-network.c",
            "src/libsystemd/sd-bus/sd-bus.c", "src/libsystemd/sd-bus/bus-socket.c",
            "src/libsystemd/sd-daemon/sd-daemon.c", "src/libsystemd/sd-event/sd-event.c",
            "src/shared/main-func.h", "src/shared/main-func.c", "src/shared/clock-util.c",
            "src/shared/bus-util.c", "src/shared/selinux-util.c", "src/shared/mkdir-label.c",
            "src/basic/log.c", "src/basic/fs-util.c", "src/basic/socket-util.c",
            "src/basic/mkdir.c", "src/shared/chown-recursive.c", "src/core/exec-invoke.c",
            "src/basic/chattr-util.c", "src/basic/errno-util.h", "src/basic/xattr-util.c"}),
        "linux": ("6.18.64-p4ctx6181-fusectl-aafs-peer-r1", "selected-kernel-source",
                  {"security/selinux/hooks.c"}),
        "glibc": ("2.43-2ubuntu2.7", "normal-signed-apt-quilt-source",
                  {"resolv/res_send.c", "nss/nss_database.c", "nss/getaddrinfo.c",
                   "sysdeps/unix/sysv/linux/check_pf.c"}),
    }
    rows = value["source_documents"]
    expected = {(package, path) for package, (_, _, paths) in sources.items() for path in paths}
    if len(rows) != len(expected) or {(r["package"], r["path"]) for r in rows} != expected:
        raise ValueError("Missing, extra or duplicate timesync source")
    for row in rows:
        version, admission, _ = sources[row["package"]]
        if row["version"] != version or row["admission"] != admission:
            raise ValueError("Timesync source provenance differs")
    normal = {
        "/usr/lib/systemd/systemd-timesyncd",
        "/usr/lib/systemd/system/systemd-timesyncd.service",
        "/usr/lib/sysusers.d/systemd-timesync.conf",
        "/usr/share/dbus-1/system.d/org.freedesktop.timesync1.conf",
        "/etc/systemd/timesyncd.conf", "/etc/nsswitch.conf", "/etc/hosts",
        "/etc/host.conf", "/etc/gai.conf", "/etc/passwd", "/etc/group",
        "/usr/lib/x86_64-linux-gnu/libc.so.6",
        "/usr/lib/x86_64-linux-gnu/libselinux.so.1",
        "/usr/lib/x86_64-linux-gnu/systemd/libsystemd-shared-259.so",
    }
    if (len(value["normal_files"]) != len(normal) or
            {r["path"] for r in value["normal_files"]} != normal):
        raise ValueError("Missing, extra or duplicate timesync normal file")
    for row in value["normal_files"]:
        if (row["uid"], row["gid"], row["nlink"]) != (0, 0, 1) or row["mode"] not in (0o644, 0o755):
            raise ValueError("Timesync normal file ownership/mode differs")
    for row in rows + value["normal_files"]:
        if (type(row["bytes"]) is not int or row["bytes"] <= 0 or
                not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise ValueError("Invalid timesync source pin")
    if value.get("normal_account") != {
        "name": "systemd-timesync",
        "passwd": ["systemd-timesync", "x", "996", "996", "systemd Time Synchronization", "/", "/usr/sbin/nologin"],
        "group": ["systemd-timesync", "x", "996", ""],
    }:
        raise ValueError("Normal systemd-timesync account differs")
    if value.get("dns_normal_elf_proof") != {
        "bytes": 5875, "sha256": "280af455c5f5c0415b05cad573dd4bf1bb2a9838942cc1340de77cc9e92fea2f"
    } or value.get("glibc_source_admission") != {
        "bytes": 19073, "sha256": "8b1d42efa9e602dbf104c7ca3b255c1e846f85f3e77e0eac10166095cad10081"
    }:
        raise ValueError("Normal DNS/glibc evidence lineage differs")
    return value


def _raw(lines, classes, pairs, actors):
    """Complete unconditional concrete TE for an explicit bounded pair set."""
    text = "\n".join(lines)
    if re.search(r"\((?:booleanif|tunableif|typebounds)\b", text):
        raise ValueError("Timesync preservation requires unconditional unbounded TE")
    members = Membership(text)
    targets = {target for target, _ in pairs}
    actors = {actor for _, actor in actors}
    result = {(actor, target, cls): set() for actor in actors for target, cls in pairs}
    actor_cache, object_cache = {}, {}
    selected_classes = {c for _, c in pairs}
    count = 0
    for line in lines:
        if not line.startswith("(allow "):
            continue
        count += 1
        form = parse_expression(line)
        if (len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2 or
                not isinstance(form[3][1], list)):
            raise ValueError("Unmodeled timesync raw TE statement")
        subject, target, (cls, names) = form[1:]
        if cls not in classes or not set(names).issubset(classes[cls]):
            raise ValueError("Unknown timesync raw TE class or permission")
        if cls not in selected_classes:
            continue
        selected = actor_cache.setdefault(subject, None)
        if selected is None:
            selected = actor_cache[subject] = [a for a in actors if members.member(subject, a)]
        if not selected:
            continue
        if target == "self":
            for actor in selected:
                if (actor, cls) in pairs:
                    result[(actor, actor, cls)].update(names)
        else:
            selected_targets = object_cache.setdefault(target, None)
            if selected_targets is None:
                selected_targets = object_cache[target] = [t for t in targets if members.member(target, t)]
            for actor in selected:
                for obj in selected_targets:
                    if (obj, cls) in pairs:
                        result[(actor, obj, cls)].update(names)
    if count != text.count("(allow "):
        raise ValueError("Incomplete timesync raw TE export")
    return result


def _relabel_constraints(policy, lines):
    """Retain the actual hardware/uevent relabel constraints unchanged."""
    members = Membership("\n".join(lines))
    proof = []
    for line in lines:
        if not line.startswith(("(validatetrans ", "(mlsvalidatetrans ")):
            continue
        form = parse_expression(line)
        if len(form) != 3:
            raise ValueError("Unmodeled timesync relabel constraint")
        cls, expression = form[1:]
        if cls not in ("file", "dir"):
            if cls == "tcp_socket":
                raise ValueError("Unexpected TCP port relabel constraint")
            continue
        actor = {"file": "p4_linux_uevent_label_t", "dir": "p4_linux_hardware_label_t"}[cls]
        if (form[0] != "validatetrans" or not isinstance(expression, list) or
                len(expression) != 3 or expression[:2] != ["or", ["neq", "t3", actor]]):
            raise ValueError("Timesync alias has an unmodeled relabel actor")
        for row in ALIASES:
            if row["class"] != cls:
                continue
            for target in (row["source"], row["target"]):
                for source_level in LEVELS:
                    for target_level in LEVELS:
                        if policy.context_av(_context("system_r", actor, source_level),
                                _context("object_r", target, target_level), cls,
                                ["relabelfrom", "relabelto"]):
                            raise ValueError("A constrained relabel actor reaches timesync inputs")
            if cls == "dir":
                if expression[2] != ["or", ["eq", "t1", "device"], ["eq", "t1", "t2"]]:
                    raise ValueError("Hardware directory relabel predicate changed")
            else:
                def atoms(expr, target):
                    if not isinstance(expr, list):
                        if expr == "t2":
                            raise ValueError("Bare relabel target variable")
                        return expr
                    if len(expr) == 3 and expr[0] in ("eq", "neq") and "t2" in expr[1:]:
                        other = expr[2] if expr[1] == "t2" else expr[1]
                        if not isinstance(other, str) or other in ("t1", "t2", "t3"):
                            raise ValueError("Unmodeled relabel identity predicate")
                        equal = members.member(other, target)
                        return equal if expr[0] == "eq" else not equal
                    return [atoms(child, target) for child in expr]
                if atoms(expression, row["source"]) != atoms(expression, row["target"]):
                    raise ValueError("Timesync alias changed file relabel predicates")
            proof.append([row["source"], row["target"], cls, hashlib.sha256(line.encode()).hexdigest()])
    if len(proof) != len(ALIASES):
        raise ValueError("Missing original file/directory relabel guards")
    return sorted(proof)


def _port_contexts(lines):
    expected = "(portcon tcp 53 (u object_r " + DNS + " ((s0) (s0))))"
    ports = sorted(line for line in lines if line.startswith("(portcon "))
    if ports != [expected]:
        raise ValueError("Only the fixed DNS TCP/53 network-context addition is allowed")
    if "(sidcontext port (u object_r port ((s0) (s0))))" not in lines:
        raise ValueError("The original default port SID changed")
    if any(line.startswith(("(nodecon ", "(netifcon ")) for line in lines):
        raise ValueError("Timesync cannot replace node or interface context selection")
    members = Membership("\n".join(lines))
    if not members.member("port_type", "port") or not members.member("port_type", DNS):
        raise ValueError("The DNS port must preserve original port constraint membership")
    return ports


def derive(library, baseline, exported, here, output, export):
    contract(here)
    policy = ContextPolicy(library, baseline)
    lines = export(policy, baseline, exported)
    classes = _classes(exported.read_text())
    actors = [(r, a) for r, a in _roles(lines) if a != ROLE]
    aliases = ALIASES + [PORT_ALIAS]
    pairs = {(row[k], row["class"]) for row in aliases for k in ("source", "target")}
    if len({(row["target"], row["class"]) for row in aliases}) != len(aliases):
        raise ValueError("Repeated timesync alias/class pair")
    constraints, constraint_checks = _constraint_targets(lines, aliases)
    relabel = _relabel_constraints(policy, lines)
    port_contexts = _port_contexts(lines)
    if _new_transitions(lines) != FIXED_TRANSITIONS:
        raise ValueError("Timesync entry and exact-name creation preimages differ")
    raw = _raw(lines, classes, pairs, actors)
    generated, samples, effective, xperms = [], [], [], []
    formatted_xperms = {}
    def format_mask(mask):
        if mask not in formatted_xperms:
            formatted_xperms[mask] = format_xperms(mask)
        return formatted_xperms[mask]
    for index, row in enumerate(aliases):
        old, new, cls = row["source"], row["target"], row["class"]
        names = classes[cls]
        groups = defaultdict(list)
        for role, actor in actors:
            before, preimage = raw[(actor, old, cls)], raw[(actor, new, cls)]
            extra = EXTRAS.get((actor, new, cls), set())
            wanted = before | extra
            if preimage - wanted or extra - preimage:
                raise ValueError("Timesync alias lacks its exact explicit preimage: " + str((actor, new, cls)))
            groups[tuple(sorted(wanted))].append(actor)
            samples.append([role, actor, old, new, cls, sorted(before), sorted(wanted)])
            for source_level in LEVELS:
                for target_level in LEVELS:
                    source = _context(role, actor, source_level)
                    old_av = policy.context_av(source, _context("object_r", old, target_level), cls, names)
                    new_av = policy.context_av(source, _context("object_r", new, target_level), cls, names)
                    effective.append([role, actor, old, new, cls, source_level, target_level, old_av, old_av | new_av])
        for ordinal, (allowed, selected) in enumerate(sorted(groups.items())):
            attr = "p4_timesync_preserved_" + str(index) + "_" + str(ordinal)
            generated += ["(typeattribute " + attr + ")",
                          "(typeattributeset " + attr + " (" + " ".join(sorted(set(selected))) + "))"]
            for op, chosen in (("allow", set(allowed)), ("neverallow", set(names) - set(allowed))):
                if chosen:
                    generated.append("(" + op + " " + attr + " " + new +
                                     " (" + cls + " (" + " ".join(sorted(chosen)) + ")))")
        if cls in ("file", "dir"):
            old_x = original_xperms([exported], [a for _, a in actors], old, class_names=(cls,))[cls]
            new_x = original_xperms([exported], [a for _, a in actors], new, class_names=(cls,))[cls]
            ioctl_groups = defaultdict(list)
            for role, actor in actors:
                before = old_x[actor]
                extra = XPERM_EXTRAS.get((actor, new, cls), 0)
                wanted = before | extra
                if new_x[actor] & ~wanted or extra & ~new_x[actor]:
                    raise ValueError("Unexpected timesync alias ioctl preimage")
                xperms.append([actor, old, new, cls, hex(before), hex(wanted)])
                ioctl_groups[wanted].append(actor)
            # Equal complete 65536-bit vectors share one assertion. Every
            # actor remains explicitly enumerated; no permission is merged.
            for ordinal, (wanted, selected) in enumerate(sorted(ioctl_groups.items())):
                attr = "p4_timesync_ioctl_" + str(index) + "_" + str(ordinal)
                generated += ["(typeattribute " + attr + ")",
                              "(typeattributeset " + attr + " (" + " ".join(sorted(selected)) + "))"]
                if wanted:
                    generated.append("(allowx " + attr + " " + new +
                                     " (ioctl " + cls + " " + format_mask(wanted) + "))")
                generated.append("(neverallowx " + attr + " " + new +
                                 " (ioctl " + cls + " " + format_mask(FULL_XPERMS ^ wanted) + "))")
    copies = set()
    for row in aliases:
        for line in lines:
            if line.startswith(TRANSITIONS) and parse_expression(line)[2] == row["source"]:
                copied = line.replace(" " + row["source"] + " ", " " + row["target"] + " ", 1)
                generated.append(copied)
                copies.add(copied)
    output.write_text("\n".join(sorted(set(generated))) + "\n")
    return {
        "schema": "droidloom.native-timesync-prelink-contract.v1",
        "aliases": aliases, "classes": classes, "actors": actors,
        "raw_vectors": samples, "effective_vectors": effective, "xperm_vectors": xperms,
        "constraint_forms": sorted(line for line in lines if line.startswith(CONSTRAINTS)),
        "constraint_target_checks": constraint_checks, "relabel_constraints": relabel,
        "port_contexts": port_contexts, "transitions_copied": sorted(copies),
        "new_type_transition_forms": sorted(FIXED_TRANSITIONS | copies),
        "selected_transition_forms": sorted({line for line in lines if line.startswith(TRANSITIONS) and
            parse_expression(line)[2] in {r["target"] for r in aliases}} | copies),
        "source_contract_sha256": hashlib.sha256((here / "native-timesync-source.json").read_bytes()).hexdigest(),
        "derived_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def _own_tables(here):
    """Source-owned role vectors, including every later fixed alias consumer."""
    from derive_native_console_policy import contract as console_contract
    from derive_native_remount_policy import ALIASES as REMOUNT_ALIASES
    from derive_native_logind_state_policy import ALIASES as LOGIND_ALIASES
    from derive_native_netplan_policy import ALIASES as NETPLAN_ALIASES
    from derive_native_sysusers_policy import ALIASES as SYSUSERS_ALIASES
    from derive_native_ldconfig_policy import ALIASES as LDCONFIG_ALIASES
    from derive_native_journal_catalog_policy import ALIASES as CATALOG_ALIASES
    from derive_native_kmod_static_policy import ALIASES as KMOD_ALIASES
    from derive_native_update_done_policy import ALIASES as UPDATE_DONE_ALIASES
    file_access = {
        ROLE: words("getattr open read"),
        ENTRY: words("getattr open read execute map entrypoint"),
        "p4_linux_runtime_lib_t": words("getattr open read execute map"),
        "p4_linux_elf_interpreter_t": words("getattr open read execute map"),
        "p4_linux_console_ld_cache_native_config_t": words("getattr open read map"),
        CONFIG: words("getattr open read"), NSS: words("getattr open read"),
        NETIF: words("getattr open read"),
        "p4_linux_resolved_run_t": words("getattr open read"),
        RUN: words("getattr open write create setattr"),
        STATE: words("getattr open read write create setattr"),
    }
    directories = {
        ROLE: words("getattr search open read"),
        "p4_linux_rootdir_t": words("getattr search open read watch"),
        "p4_linux_etc_dir_t": words("getattr search open read"),
        "p4_linux_run_t": words("getattr search watch"),
        "p4_linux_systemd_run_t": words("getattr search watch"),
        "p4_linux_var_lib_t": words("getattr search"),
        "p4_linux_systemd_state_parent_t": words("getattr search"),
        "p4_linux_dbus_run_t": words("getattr search watch"),
        "p4_linux_resolved_run_t": words("getattr search"),
        "p4_linux_journal_runtime_t": words("getattr search"),
        "selinuxfs": words("search"), "sysfs": words("search"),
        NETIF: words("getattr search open read watch"),
        RUN: words("getattr search write add_name"),
        STATE: words("getattr search write add_name"),
    }
    links = {ROLE: words("getattr read"), "p4_linux_usrmerge_link_t": words("getattr read"),
             "p4_linux_timezone_link_t": words("getattr read")}
    tables = {"file": file_access, "dir": directories, "lnk_file": links}
    successors = (console_contract(here)["aliases"] + REMOUNT_ALIASES +
                  LOGIND_ALIASES + NETPLAN_ALIASES + SYSUSERS_ALIASES + LDCONFIG_ALIASES + CATALOG_ALIASES + KMOD_ALIASES + UPDATE_DONE_ALIASES)
    for row in successors:
        table = tables.get(row["class"], {})
        if row["source"] in table:
            table.setdefault(row["target"], set()).update(table[row["source"]])
    tables["sock_file"] = {
        "p4_linux_system_bus_socket_t": words("getattr write watch"),
        "p4_linux_journal_native_socket_t": words("write"),
        "p4_linux_systemd_notify_t": words("write"),
    }
    tables["chr_file"] = {"p4_linux_standardio_t": words("getattr read write")}
    tables["blk_file"] = {}
    tables["filesystem"] = {"selinuxfs": words("getattr")}
    return tables


def verify(library, binary, exported, here, expected, export):
    contract(here)
    if expected["aliases"] != ALIASES + [PORT_ALIAS]:
        raise ValueError("Timesync derivation does not identify the fixed ten class/type pairs")
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    text = exported.read_text()
    classes = _classes(text)
    if classes != expected["classes"]:
        raise ValueError("Timesync class/permission bit layout changed")
    actors = _roles(lines)
    if [(r, a) for r, a in actors if a != ROLE] != [tuple(x) for x in expected["actors"]]:
        raise ValueError("Timesync actor roster changed after derivation")
    _port_contexts(lines)
    if _new_transitions(lines) != set(expected["new_type_transition_forms"]):
        raise ValueError("Timesync changed a complete entry/name transition")
    if sorted(line for line in lines if line.startswith(CONSTRAINTS)) != expected["constraint_forms"]:
        raise ValueError("Timesync changed an original constraint")
    _constraint_targets(lines, ALIASES + [PORT_ALIAS])
    if _relabel_constraints(policy, lines) != expected["relabel_constraints"]:
        raise ValueError("Timesync relabel proof changed")
    selected_transitions = sorted(line for line in lines if line.startswith(TRANSITIONS) and
        parse_expression(line)[2] in {r["target"] for r in expected["aliases"]})
    if selected_transitions != expected["selected_transition_forms"]:
        raise ValueError("Timesync changed the complete selected transition set")
    pairs = {(row[k], row["class"]) for row in expected["aliases"] for k in ("source", "target")}
    raw = _raw(lines, classes, pairs, expected["actors"])
    for role, actor, old, new, cls, before, wanted in expected["raw_vectors"]:
        if raw[(actor, old, cls)] != set(before) or raw[(actor, new, cls)] != set(wanted):
            raise ValueError("Timesync changed a complete old actor raw vector")
    checks = []
    for role, actor, old, new, cls, source_level, target_level, before, wanted in expected["effective_vectors"]:
        source = _context(role, actor, source_level)
        for target, value in ((old, before), (new, wanted)):
            actual = policy.context_av(source, _context("object_r", target, target_level), cls, classes[cls])
            if actual != value:
                raise ValueError("Timesync changed a same-category-pair old actor vector")
        checks.append([actor, new, cls, source_level, target_level, wanted])
    xcache = {}
    for actor, old, new, cls, before, wanted in expected["xperm_vectors"]:
        for target, value in ((old, int(before, 16)), (new, int(wanted, 16))):
            key = target, cls
            if key not in xcache:
                xcache[key] = original_xperms([exported], [a for _, a in expected["actors"]],
                                              target, class_names=(cls,))[cls]
            if xcache[key][actor] != value:
                raise ValueError("Timesync changed an original/aliased ioctl vector")
    # nsswitch was formerly the selected Netplan private-config alias.
    # Require equality with that actual final alias, not just our earlier
    # native_config preimage; this includes Netplan's explicit three read bits.
    private = "p4_linux_netplan_private_config_t"
    nss_raw = _raw(lines, classes, {(NSS, "file"), (private, "file")}, expected["actors"])
    nss_checks = []
    for role, actor in expected["actors"]:
        if nss_raw[(actor, NSS, "file")] != nss_raw[(actor, private, "file")]:
            raise ValueError("Public NSS changed an old actor's final private-config raw view")
        for source_level in LEVELS:
            for target_level in LEVELS:
                source = _context(role, actor, source_level)
                left = policy.context_av(source, _context("object_r", NSS, target_level), "file", classes["file"])
                right = policy.context_av(source, _context("object_r", private, target_level), "file", classes["file"])
                if left != right:
                    raise ValueError("Public NSS changed an old actor's final private-config MCS view")
                nss_checks.append([role, actor, source_level, target_level, left])
    left_x = original_xperms([exported], [a for _, a in expected["actors"]], NSS, class_names=("file",))
    right_x = original_xperms([exported], [a for _, a in expected["actors"]], private, class_names=("file",))
    if left_x != right_x:
        raise ValueError("Public NSS changed an old actor's final private-config ioctl view")
    objects = sorted(set(re.findall(r"\(roletype object_r (\w+)\)", text)))
    tables = _own_tables(here)
    targets = [("object_r", target) for target in objects] + actors
    socket_classes = sorted(c for c in classes if c == "socket" or c.endswith("_socket"))
    # Raw TE includes every class and declared target, including classes with
    # no source-proven operation. An effective s0 denial cannot conceal an
    # unexpected category-dependent grant.
    own_pairs = {(t, c) for t in Membership(text).types for c in classes}
    own_raw = _raw(lines, classes, own_pairs, [("system_r", ROLE)])
    own_checked = set()
    def av(target, cls, wanted, target_role="object_r"):
        names = classes[cls]
        _, bits = policy.permissions(cls, names)
        expected_mask = sum(bits[name] for name in wanted)
        actual = policy.context_av(_context("system_r", ROLE), _context(target_role, target), cls, names)
        if own_raw[(ROLE, target, cls)] != set(wanted):
            raise ValueError("Timesync raw boundary differs: " +
                             str((target, cls, sorted(own_raw[(ROLE, target, cls)]), sorted(wanted))))
        if actual != expected_mask:
            raise ValueError("Timesync boundary differs: " + str((target, cls, actual, expected_mask)))
        own_checked.add((target, cls))
        checks.append([ROLE, target, cls, sorted(wanted)])
    for cls, table in tables.items():
        for target in objects:
            av(target, cls, table.get(target, set()))
        av(ROLE, cls, table.get(ROLE, set()), "system_r")
    for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
        av(ROLE, cls, {"sys_time"} if cls == "capability" else set(), "system_r")
    av("kernel", "security", set(), "r")
    av("kernel", "system", set(), "r")
    targets = [("object_r", target) for target in objects] + actors
    for target_role, target in targets:
        av(target, "process", words("fork getattr getcap") if target == ROLE else
           {"sigchld"} if target == "init_t" else set(), target_role)
        av(target, "process2", set(), target_role)
        av(target, "key", set(), target_role)
        av(target, "fd", {"use"} if target in (ROLE, "init_t", EXECUTOR) else set(), target_role)
    self_sockets = {
        "udp_socket": words("create getattr bind connect read write getopt setopt"),
        "tcp_socket": words("create getattr connect read write getopt setopt shutdown"),
        "unix_dgram_socket": words("create getattr read write sendto bind connect getopt setopt"),
        "unix_stream_socket": words("create getattr bind connect read write getopt setopt shutdown"),
    }
    for cls in sorted(c for c in classes if c == "socket" or c.endswith("_socket")):
        for target_role, target in targets:
            wanted = set(self_sockets.get(cls, set())) if target == ROLE else set()
            if cls == "udp_socket" and target == "node":
                wanted = {"node_bind"}
            if cls == "tcp_socket" and target == DNS:
                wanted = {"name_connect"}
            if cls == "unix_stream_socket" and target == EXECUTOR:
                wanted = words("getattr read write")
            if cls == "unix_stream_socket" and target in ("init_t", "p4_linux_dbus_t"):
                wanted = {"connectto"}
            if cls == "unix_dgram_socket" and target == "init_t":
                wanted = {"sendto"}
            av(target, cls, wanted, target_role)
    # No broad/native/private membership can conceal an undeclared authority.
    members = Membership(text)
    for target_role, target in targets:
        wanted = {"send_msg"} if members.member("p4_native_system_bus_clients", target) else set()
        if target == "p4_linux_dbus_t":
            wanted.update({"acquire_svc", "send_msg"})
        av(target, "dbus", wanted, target_role)
    for attr in ("domain", "p4_linux_native_processes", "p4_native_selinux_query_clients",
                 "p4_native_selinux_label_readers"):
        if members.member(attr, ROLE):
            raise ValueError("Timesync joined a broader authority attribute")
    unmodeled = [[target, cls, sorted(names)] for (_, target, cls), names in own_raw.items()
                 if names and (target, cls) not in own_checked]
    if unmodeled:
        raise ValueError("Timesync acquired an undeclared raw class/target: " + str(unmodeled[:5]))
    own_forms = [line for line in lines if line.startswith("(allowx ") and
                 members.member(parse_expression(line)[1], ROLE)]
    if own_forms:
        raise ValueError("Timesync cannot acquire any device/file ioctl filter")
    return {
        "schema": "droidloom.native-timesync-policy-proof.v1",
        "source_contract_sha256": expected["source_contract_sha256"],
        "derived_alias_policy_sha256": expected["derived_sha256"],
        "verifier_sha256": hashlib.sha256((here / "derive_native_timesync_policy.py").read_bytes()).hexdigest(),
        "aliases": expected["aliases"], "port_contexts": expected["port_contexts"],
        "preserved_raw_vectors": len(expected["raw_vectors"]),
        "preserved_mcs_vectors": len(expected["effective_vectors"]),
        "preserved_ioctl_vectors": len(expected["xperm_vectors"]),
        "preserved_transition_count": len(expected["transitions_copied"]),
        "constraint_target_checks": expected["constraint_target_checks"],
        "objects": len(objects), "actors": len(actors),
        "new_role_raw_class_target_vectors": len(own_raw),
        "final_public_nss_old_actor_vectors": len(nss_checks),
        "final_public_nss_matrix_sha256": hashlib.sha256(json.dumps(nss_checks).encode()).hexdigest(),
        "vector_checks": len(checks),
        "file_contexts": verify_file_contexts(here, exported.parent),
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest(),
        "runtime_qualified": False,
    }

def verify_file_contexts(here, work):
    """Use the real libselinux matcher, including inode-kind and sibling cases."""
    path = work / "timesync-file-contexts"
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    data = b"".join((here / name).read_bytes() for name in names)
    path.write_bytes(data)

    class Option(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("value", ctypes.c_char_p)]
    lib = ctypes.CDLL("libselinux.so.1", use_errno=True)
    lib.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(Option), ctypes.c_uint]
    lib.selabel_open.restype = ctypes.c_void_p
    lib.selabel_lookup_raw.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p),
                                      ctypes.c_char_p, ctypes.c_int]
    lib.selabel_close.argtypes = [ctypes.c_void_p]
    lib.freecon.argtypes = [ctypes.c_void_p]
    handle = lib.selabel_open(0, ctypes.byref(Option(3, str(path).encode())), 1)
    if not handle:
        raise OSError(ctypes.get_errno(), "Cannot open timesync file contexts")
    checks = []
    def lookup(filename, mode, *, absent=False):
        result = ctypes.c_char_p()
        if lib.selabel_lookup_raw(handle, ctypes.byref(result), filename.encode(), mode):
            error = ctypes.get_errno()
            if absent and error == 2:
                return None
            raise OSError(error, "Timesync context lookup: " + filename)
        try:
            return result.value.decode().split(":")[2]
        finally:
            lib.freecon(result)
    selected = [
        ("/usr/lib/systemd/systemd-timesyncd", stat.S_IFREG, ENTRY),
        ("/usr/lib/systemd/system/systemd-timesyncd.service", stat.S_IFREG, "p4_linux_unit_file_t"),
        ("/run/systemd/timesync", stat.S_IFDIR, RUN),
        ("/run/systemd/timesync/synchronized", stat.S_IFREG, RUN),
        ("/var/lib/systemd/timesync", stat.S_IFDIR, STATE),
        ("/var/lib/systemd/timesync/clock", stat.S_IFREG, STATE),
        ("/etc/systemd/timesyncd.conf", stat.S_IFREG, CONFIG),
        ("/etc/systemd/timesyncd.conf.d/10-normal.conf", stat.S_IFREG, CONFIG),
        ("/etc/hosts", stat.S_IFREG, CONFIG),
        ("/etc/host.conf", stat.S_IFREG, CONFIG),
        ("/etc/gai.conf", stat.S_IFREG, CONFIG),
        ("/etc/adjtime", stat.S_IFREG, CONFIG),
        ("/etc/nsswitch.conf", stat.S_IFREG, NSS),
        ("/run/systemd/netif", stat.S_IFDIR, NETIF),
        ("/run/systemd/netif/links", stat.S_IFDIR, NETIF),
        ("/run/systemd/netif/state", stat.S_IFREG, NETIF),
        ("/run/systemd/netif/links/2", stat.S_IFREG, NETIF),
    ]
    new_types = {ENTRY, RUN, STATE, CONFIG, NSS, NETIF}
    try:
        for filename, mode, wanted in selected:
            actual = lookup(filename, mode)
            if actual != wanted:
                raise ValueError("Timesync selected inode label differs: " + filename)
            checks.append([filename, mode, actual])
            if wanted in new_types:
                for other in (stat.S_IFREG, stat.S_IFDIR, stat.S_IFLNK, stat.S_IFCHR, stat.S_IFBLK):
                    if other == mode:
                        continue
                    actual = lookup(filename, other, absent=True)
                    if actual in new_types:
                        raise ValueError("Timesync selected an unintended inode kind")
                    checks.append([filename, other, actual])
        for filename, wanted in [
            ("/usr/lib/systemd/systemd-timesyncd.extra", "p4_linux_runtime_lib_t"),
            ("/run/systemd/timesync/other", "p4_linux_native_data_t"),
            ("/var/lib/systemd/timesync/other", "p4_linux_native_data_t"),
            ("/etc/nsswitch.conf.extra", "p4_linux_native_config_t"),
            ("/run/systemd/netif/links/not-a-number", "p4_linux_native_data_t"),
        ]:
            actual = lookup(filename, stat.S_IFREG)
            if actual != wanted:
                raise ValueError("Timesync changed an unselected sibling")
            checks.append([filename, stat.S_IFREG, actual])
        private = json.loads((here / "native-netplan-private-source.json").read_text())
        for row in private["profiles"]:
            if lookup(row["path"], stat.S_IFREG) != "p4_linux_netplan_private_config_t":
                raise ValueError("Timesync relabeled a private Netplan input")
        if lookup("/etc/resolv.conf", stat.S_IFLNK) != "p4_linux_usrmerge_link_t":
            raise ValueError("The normal resolver symlink changed label")
        if lookup("/run/systemd/resolve/stub-resolv.conf", stat.S_IFREG) != "p4_linux_resolved_run_t":
            raise ValueError("The normal resolver output changed label")
    finally:
        lib.selabel_close(handle)
    return {"checks": checks, "private_netplan_profiles_preserved": len(private["profiles"]),
            "composed_bytes": len(data), "composed_sha256": hashlib.sha256(data).hexdigest()}
