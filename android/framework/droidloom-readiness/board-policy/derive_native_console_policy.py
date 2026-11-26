"""Console closure extension of the normal strict policy linker.

The normal package bytes are not rewritten. Selected inodes receive narrower
types; every pre-existing actor's access and transition is preserved, except
the two explicitly declared service/udev entry edges. No runtime is started.
"""
import ctypes
import hashlib
import json
import re
import stat
from collections import defaultdict

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_shared_payload_cgroup_policy import parse_expression, original_xperms

ROLE = "p4_linux_console_setup_t"
SCHEMA = "droidloom.native-console-source-closure.v1"

TTY_TYPES = ("tty_device", "owntty_device", "console_device", "p4_linux_console_t")
IOCTLS = {
    "KDGKBTYPE": 0x4b33, "KDGETMODE": 0x4b3b, "KDGKBMODE": 0x4b44,
    "KDSKBMODE": 0x4b45, "KDSKBENT": 0x4b47, "KDSKBSENT": 0x4b49,
    "GIO_UNIMAP": 0x4b66, "PIO_UNIMAP": 0x4b67, "PIO_UNIMAPCLR": 0x4b68,
    "PIO_CMAP": 0x4b71, "KDFONTOP": 0x4b72, "KDSKBDIACRUC": 0x4bfb,
    "TIOCGWINSZ": 0x5413, "TCGETS2": 0x542a,
}
TRANSITION_OPS = ("(typetransition ", "(typechange ", "(typemember ", "(roletransition ")


def _fixed_transitions():
    rows = set()
    for source, entry in [
        ("p4_linux_service_executor_t", "p4_linux_console_entry_runtime_lib_t"),
        ("p4_linux_service_executor_t", "p4_linux_console_vtrgb_native_bin_t"),
        ("p4_linux_udev_t", "p4_linux_console_cache_exec_native_config_t"),
    ]:
        rows.add("(typetransition " + source + " " + entry + " process " + ROLE + ")")
    for filename in ("cached_setup_keyboard.sh", "cached_setup_font.sh", "cached_setup_terminal.sh"):
        rows.add('(typetransition ' + ROLE + ' p4_linux_console_cache_dir_t file "' +
                 filename + '" p4_linux_console_cache_exec_native_config_t)')
    for filename in ("cached_UTF-8_del.kmap.gz", "cached_Uni2-Fixed16.psf.gz", "cached_rwtest"):
        rows.add('(typetransition ' + ROLE + ' p4_linux_console_cache_dir_t file "' +
                 filename + '" p4_linux_console_cache_native_config_t)')
    for filename in ("boot_completed", "font-loaded", "keymap_loaded"):
        rows.add('(typetransition ' + ROLE + ' p4_linux_console_run_t file "' +
                 filename + '" p4_linux_console_run_t)')
    rows.add('(typetransition ' + ROLE + ' p4_linux_run_t dir "console-setup" p4_linux_console_run_t)')
    rows.add('(typetransition ' + ROLE + ' p4_linux_tmp_t file p4_linux_console_tmp_t)')
    return rows


def _verify_transitions(lines, inherited):
    actual = {line for line in lines if line.startswith(TRANSITION_OPS) and
              "p4_linux_console_" in line}
    expected = _fixed_transitions() | {line for line in inherited if line.startswith(TRANSITION_OPS)}
    if actual != expected:
        raise ValueError("Console transition set differs: missing=" + repr(sorted(expected - actual)) +
                         " extra=" + repr(sorted(actual - expected)))
    return len(actual)


def _ioctl_mask(expression):
    if isinstance(expression, str):
        value = int(expression, 0)
        if not 0 <= value <= 0xffff:
            raise ValueError("Console ioctl number exceeds the kernel ABI")
        return 1 << value
    if expression and expression[0] == "range":
        if len(expression) != 3:
            raise ValueError("Invalid console ioctl range")
        first, last = int(expression[1], 0), int(expression[2], 0)
        if not 0 <= first <= last <= 0xffff:
            raise ValueError("Invalid console ioctl range")
        return ((1 << (last - first + 1)) - 1) << first
    if expression and expression[0] == "not":
        if len(expression) != 2:
            raise ValueError("Invalid console ioctl complement")
        return ((1 << 65536) - 1) ^ _ioctl_mask(expression[1])
    result = 0
    for sub in expression:
        result |= _ioctl_mask(sub)
    return result


def _verify_ioctl_filters(lines, text, objects):
    members = Membership(text)
    result = {target: 0 for target in TTY_TYPES}
    for line in lines:
        if not line.startswith("(allowx "):
            continue
        form = parse_expression(line)
        if len(form) != 4 or len(form[3]) != 3:
            raise ValueError("Unsupported linked console extended permission")
        if not members.member(form[1], ROLE):
            continue
        targets = ({ROLE} if form[2] == "self" else
                   {target for target in objects if members.member(form[2], target)})
        if (form[3][:2] != ["ioctl", "chr_file"] or not targets or
                not targets.issubset(TTY_TYPES)):
            raise ValueError("Console ioctl filter extends beyond the four fixed VT types")
        mask = _ioctl_mask(form[3][2])
        for target in targets:
            result[target] |= mask
    wanted = sum(1 << number for number in IOCTLS.values())
    if any(mask != wanted for mask in result.values()):
        raise ValueError("Console VT ioctl set differs from the normal call closure")
    return {target: sorted(IOCTLS.values()) for target in TTY_TYPES}


def contract(here):
    value = json.loads((here / "native-console-setup.json").read_text())
    if (value["schema"] != SCHEMA or value["runtime_qualified"] is not False or
            value["selected_keymap"] != ["us", "pc105", "UTF-8", "del"] or
            value["ioctls"] != IOCTLS):
        raise ValueError("Unexpected fixed console source contract")
    seen = set()
    for row in value["files"]:
        if (row["nlink"] != len(row["paths"]) or not row["paths"] or
                row["uid"] != 0 or row["gid"] != 0 or row["mode"] & 0o022 or
                not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
            raise ValueError("Invalid normal console inode identity")
        for path in row["paths"]:
            if (not path.startswith(("/usr/", "/etc/")) or "/../" in path or
                    path in seen):
                raise ValueError("Repeated or escaping console inode alias")
            seen.add(path)
    return value


def _classes(text):
    common = dict((n, body.split()) for n, body in
                  re.findall(r"\(common (\w+) \(([^()]*)\)\)", text))
    result = dict((n, body.split()) for n, body in
                  re.findall(r"\(class (\w+) \(([^()]*)\)\)", text))
    for name, parent in re.findall(r"\(classcommon (\w+) (\w+)\)", text):
        result[name] = common[parent] + result[name]
    return result


def _roles(lines):
    return sorted({(role, line[len("(roletype " + role + " "):-1])
                   for role in ("r", "system_r") for line in lines
                   if line.startswith("(roletype " + role + " ")})


def _context(role, actor, level="s0"):
    return "u:" + role + ":" + actor + ":" + level


def _extra(actor, target):
    """Only fixed entrypoints and their exact script interpreter may differ."""
    if (target == "p4_linux_console_interpreter_native_bin_t" and
            actor == "p4_linux_service_executor_t"):
        return {"open", "read", "execute"}
    if target in ("p4_linux_console_entry_runtime_lib_t",
                  "p4_linux_console_vtrgb_native_bin_t"):
        if actor in ("init_t", "p4_linux_service_executor_t"):
            return {"getattr", "open", "read", "execute", "map"}
    if (target == "p4_linux_console_cache_exec_native_config_t" and
            actor == "p4_linux_udev_t"):
        return {"getattr", "open", "read", "execute", "map"}
    return set()


def derive(library, baseline, exported, here, output, export):
    value = contract(here)
    policy = ContextPolicy(library, baseline)
    lines = export(policy, baseline, exported)
    text = exported.read_text()
    members = Membership(text)
    classes = _classes(text)
    actors = [(r, a) for r, a in _roles(lines) if a != ROLE]
    generated = ["; Derived from the actual normal pre-console-alias binary.",
                 "; Preserve all existing concrete actors; no generic execute grant."]
    samples, transitions = [], set()
    for index, row in enumerate(value["aliases"]):
        old, new, cls = row["source"], row["target"], row["class"]
        names = classes[cls]
        _, bits = policy.permissions(cls, names)
        groups = defaultdict(list)
        for role, actor in actors:
            vals = [policy.context_av(_context(role, actor, level),
                                      "u:object_r:" + old + ":s0", cls, names)
                    for level in LEVELS]
            # Native private types are not category-dependent Android storage.
            # Reject a new object family needing a stronger derivation.
            if len(set(vals)) != 1:
                raise ValueError("Console source access depends on MCS: " + old)
            extra = _extra(actor, new) if cls == "file" else set()
            allowed = vals[0] | sum(bits[n] for n in extra)
            groups[allowed].append(actor)
            samples.append([role, actor, old, new, cls, vals, allowed])
        for group, (allowed, selected) in enumerate(sorted(groups.items())):
            attr = "p4_console_preserved_" + str(index) + "_" + str(group)
            generated += ["(typeattribute " + attr + ")",
                          "(typeattributeset " + attr + " (" + " ".join(sorted(set(selected))) + "))"]
            for op, choose in (("allow", True), ("neverallow", False)):
                chosen = [name for name in names if bool(allowed & bits[name]) == choose]
                if chosen:
                    generated.append("(" + op + " " + attr + " " + new +
                                     " (" + cls + " (" + " ".join(chosen) + ")))")
        # Match the original exported transition, including named transitions.
        # The source policy's macros have already expanded to concrete types.
        for line in lines:
            if line.startswith(("(typetransition ", "(typechange ", "(typemember ",
                                "(roletransition ", "(allowx ")):
                form = parse_expression(line)
                if len(form) >= 4 and form[2] == old:
                    copied = line.replace(" " + old + " ", " " + new + " ", 1)
                    generated.append(copied)
                    transitions.add(copied)
        # Preserve constraint target atoms for every possible MLS range.
        for line in lines:
            if not line.startswith(("(constrain ", "(mlsconstrain ")):
                continue
            form = parse_expression(line)
            if form[1][0] != cls:
                continue
            def visit(expr):
                if not isinstance(expr, list):
                    return
                if len(expr) == 3 and expr[0] in ("eq", "neq") and "t2" in expr[1:]:
                    other = expr[2] if expr[1] == "t2" else expr[1]
                    if other in ("t1", "t2", "t3"):
                        raise ValueError("Console alias needs a direct type-identity constraint proof")
                    if members.member(other, old) != members.member(other, new):
                        raise ValueError("Console alias changed constraint membership: " + new + " " + other)
                for sub in expr[1:]:
                    visit(sub)
            visit(form[2])
    output.write_text("\n".join(sorted(set(generated))) + "\n")
    return {"samples": samples, "classes": classes, "actors": actors,
            "transitions": sorted(transitions),
            "source_xperms": {row["source"]: original_xperms([exported],
                sorted({a for _, a in actors}), row["source"])
                for row in {r["source"]:r for r in value["aliases"]}.values()},
            "contract_sha256": hashlib.sha256((here / "native-console-setup.json").read_bytes()).hexdigest(),
            "derived_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def verify(library, binary, exported, here, expected, export):
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    value = contract(here)
    transitions = _verify_transitions(lines, expected["transitions"])
    text = exported.read_text()
    objects = sorted(re.findall(r"\(roletype object_r (\w+)\)", text))
    ioctls = _verify_ioctl_filters(lines, text, objects)
    checks = []
    for role, actor, old, new, cls, vals, wanted in expected["samples"]:
        names = expected["classes"][cls]
        for i, level in enumerate(LEVELS):
            before = policy.context_av(_context(role, actor, level), "u:object_r:" + old + ":s0", cls, names)
            after = policy.context_av(_context(role, actor, level), "u:object_r:" + new + ":s0", cls, names)
            if before != vals[i] or after != wanted:
                raise ValueError("Console changed existing access: " + actor + " " + new)
        checks.append([role, actor, new, cls, wanted])
    actor_names = sorted({a for _, a in expected["actors"]})
    for row in value["aliases"]:
        wanted = expected["source_xperms"][row["source"]][row["class"]]
        actual = original_xperms([exported], actor_names, row["target"])[row["class"]]
        if actual != wanted:
            raise ValueError("Console alias changed existing ioctl filters: " + row["target"])
    def av(target, cls, permissions, wanted, role="object_r"):
        got = policy.context_av(_context("system_r", ROLE), _context(role, target), cls, permissions)
        _, bits = policy.permissions(cls, permissions)
        want = sum(bits[p] for p in wanted)
        if got != want:
            raise ValueError("Console boundary mismatch: " + target + " " + cls + " " + str(got) + "/" + str(want))
        checks.append([ROLE, target, cls, sorted(wanted)])
    for source in ("p4_linux_runtime_lib_t", "p4_linux_native_bin_t",
                   "p4_linux_native_config_t", "p4_linux_native_data_t"):
        av(source, "file", ["execute", "execute_no_trans", "entrypoint", "write", "append"], [])
    for row in value["files"]:
        target = row["target_type"]
        category = row["category"]
        if category in ("helper", "entry", "vtrgb", "cache_exec"):
            av(target, "file", ["open", "read", "execute", "execute_no_trans", "map"],
               ["open", "read", "execute", "execute_no_trans", "map"])
        elif category == "library":
            av(target, "file", ["open", "read", "execute", "execute_no_trans", "map"],
               ["open", "read", "execute", "map"])
        else:
            av(target, "file", ["open", "read", "execute", "execute_no_trans"], ["open", "read"])
    # Whole-class readback rejects inheritance to every other character device.
    # Null/random retain only the exact normal helper operations; no serial,
    # input, DRM, framebuffer body or arbitrary ioctl access is added.
    for target in objects:
        wanted = {
            "device": ["getattr"],
            "null_device": ["getattr", "open", "read", "write"],
            "p4_linux_standardio_t": ["read", "write"],
            "random_device": ["getattr", "open", "read"],
        }.get(target, [])
        if target in TTY_TYPES:
            wanted = ["getattr", "open", "read", "write", "ioctl"]
        av(target, "chr_file", expected["classes"]["chr_file"], wanted)
    for cls in ("capability", "capability2", "cap_userns", "cap2_userns"):
        names = expected["classes"][cls]
        av(ROLE, cls, names, ["sys_tty_config"] if cls == "capability" else [], role="system_r")
    for cls in ("tcp_socket", "udp_socket", "rawip_socket", "packet_socket",
                "netlink_route_socket", "netlink_kobject_uevent_socket"):
        av(ROLE, cls, ["create"], [], role="system_r")
    for target in ("p4_linux_runtime_lib_t", "p4_linux_native_bin_t"):
        av(target, "file", ["execute_no_trans"], [])
    av("p4_linux_console_tmp_t", "file", ["execute", "execute_no_trans", "entrypoint"], [])
    av("p4_linux_console_run_t", "file", ["execute", "execute_no_trans", "entrypoint"], [])
    for target in ("p4_linux_user_home_t", "p4_linux_auth_data_t"):
        # No account, key, password or personal home file contents enter this role.
        av(target, "file", ["open", "read", "write", "execute"], [])
    return {"schema": "droidloom.native-console-policy-proof.v1",
            "source_contract_sha256": expected["contract_sha256"],
            "derived_alias_policy_sha256": expected["derived_sha256"],
            "verifier_sha256": hashlib.sha256((here / "derive_native_console_policy.py").read_bytes()).hexdigest(),
            "complete_console_transition_count": transitions,
            "fixed_vt_ioctl_filters": ioctls,
            "all_character_device_objects_checked": len(objects),
            "preserved_actor_object_vectors": len(expected["samples"]),
            "preserved_transitions": len(expected["transitions"]),
            "selected_inode_groups": len(value["files"]),
            "selected_regular_aliases": sum(len(r["paths"]) for r in value["files"]),
            "runtime_qualified": False,
            "file_contexts": verify_file_contexts(here, exported.parent),
            "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest()}

def verify_file_contexts(here, work):
    """Check every selected alias with libselinux's actual class-aware matcher."""
    value = contract(here)
    path = work / "console-file-contexts"
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    path.write_bytes(b"".join((here / name).read_bytes() for name in names))
    class Option(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("value", ctypes.c_char_p)]
    lib = ctypes.CDLL("libselinux.so.1", use_errno=True)
    lib.selabel_open.argtypes = [ctypes.c_uint, ctypes.POINTER(Option), ctypes.c_uint]
    lib.selabel_open.restype = ctypes.c_void_p
    lib.selabel_lookup_raw.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p),
                                      ctypes.c_char_p, ctypes.c_int]
    lib.selabel_lookup_raw.restype = ctypes.c_int
    lib.selabel_close.argtypes = [ctypes.c_void_p]
    lib.freecon.argtypes = [ctypes.c_void_p]
    handle = lib.selabel_open(0, ctypes.byref(Option(3, str(path).encode())), 1)
    if not handle:
        raise OSError(ctypes.get_errno(), "Cannot open normal console file-context matcher")
    checked = []
    try:
        def lookup(filename, mode):
            result = ctypes.c_char_p()
            if lib.selabel_lookup_raw(handle, ctypes.byref(result), filename.encode(), mode):
                raise OSError(ctypes.get_errno(), "Console context lookup failed: " + filename)
            try:
                return result.value.decode().split(":")[2]
            finally:
                lib.freecon(result)
        for row in value["files"]:
            for filename in row["paths"]:
                actual = lookup(filename, stat.S_IFREG)
                if actual != row["target_type"]:
                    raise ValueError("Console alias labels disagree: " + filename)
                for other in (stat.S_IFLNK, stat.S_IFDIR):
                    if lookup(filename, other).startswith("p4_linux_console_"):
                        raise ValueError("Console executable context matched a different inode class")
                checked.append([filename, actual])
        for filename, mode, expected in [
            ("/etc/console-setup", stat.S_IFDIR, "p4_linux_console_cache_dir_t"),
            ("/etc/console-setup/unselected.sh", stat.S_IFREG, "p4_linux_native_config_t"),
            ("/usr/bin/coreutils-extra", stat.S_IFREG, "p4_linux_native_bin_t"),
            ("/usr/lib/cargo/bin/coreutils/unselected", stat.S_IFREG, "p4_linux_native_bin_t"),
            ("/run/console-setup", stat.S_IFDIR, "p4_linux_console_run_t"),
            ("/run/console-setup/font-loaded", stat.S_IFREG, "p4_linux_console_run_t"),
            ("/run/console-setup/unselected", stat.S_IFREG, "p4_linux_native_data_t"),
        ]:
            if lookup(filename, mode) != expected:
                raise ValueError("Console context boundary expanded: " + filename)
            checked.append([filename, expected])
    finally:
        lib.selabel_close(handle)
    return {"selected_alias_and_negative_cases": len(checked),
            "matrix_sha256": hashlib.sha256(json.dumps(checked).encode()).hexdigest()}
