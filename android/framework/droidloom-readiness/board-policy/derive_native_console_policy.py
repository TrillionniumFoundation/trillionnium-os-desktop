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

from derive_native_uevent_policy import ContextPolicy, Membership, LEVELS
from derive_preserved_alias_policy import (
    _roles, _context, derive_preserved_aliases, verify_preserved_aliases)
from derive_shared_payload_cgroup_policy import parse_expression

ROLE = "p4_linux_console_setup_t"
SCHEMA = "droidloom.native-console-source-closure.v1"

TTY_TYPES = ("tty_device", "owntty_device", "console_device", "p4_linux_console_t",
             "p4_linux_console_vt_t")
IOCTLS = {
    "KDGKBTYPE": 0x4b33, "KDGETMODE": 0x4b3b, "KDGKBMODE": 0x4b44,
    "KDSKBMODE": 0x4b45, "KDSKBENT": 0x4b47, "KDSKBSENT": 0x4b49,
    "GIO_UNIMAP": 0x4b66, "PIO_UNIMAP": 0x4b67, "PIO_UNIMAPCLR": 0x4b68,
    "PIO_CMAP": 0x4b71, "KDFONTOP": 0x4b72, "KDSKBDIACRUC": 0x4bfb,
    "TIOCGWINSZ": 0x5413, "TCGETS2": 0x542a,
}
# These normal host ELFs already use the admitted native dynamic loader.
# Keep this list explicit: an unrelated actor never gains cache access merely
# by joining an attribute. Existing native-service cache permissions are kept.
# These isolated, source-bound normal ELFs already have the exact cache edge.
# Their generic native-config file authority remains zero.
ISOLATED_CACHE_LOADERS = {
    "p4_linux_working_payload_birth_t",
    "p4_linux_production_commit_t", "p4_linux_production_verify_t",
}
CACHE_LOADERS = {
    *ISOLATED_CACHE_LOADERS,
    "droidloom_engine_observer",
    # The fixed normal calibration ELF uses the same admitted dynamic loader.
    "droidloom_policy_loader",
    "p4_linux_tmpfiles_t",
    "p4_linux_update_done_t",
    "p4_linux_random_seed_t",
    "p4_linux_early_t", "p4_linux_service_executor_t",
    "p4_linux_journald_t", "p4_linux_journalctl_t", "p4_linux_udev_t",
    "p4_linux_hardware_label_t", "p4_linux_uevent_label_t",
    "p4_linux_maintenance_journal_t", "droidloom_container_entry_t",
    "p4_linux_remount_t", "p4_linux_netplan_t", "p4_linux_once_return_t",
    "p4_linux_tmp_mount_t",
    "p4_linux_timesyncd_t",
}
INTERPRETER_OPENERS = {"p4_linux_service_executor_t", "p4_linux_udev_t"}
NULL_TYPES = ("null_device", "p4_linux_standardio_t")
IOCTL_TARGETS = {target: set(IOCTLS.values()) for target in TTY_TYPES}
IOCTL_TARGETS.update({target: {IOCTLS["TCGETS2"]} for target in NULL_TYPES})
VT_TYPE = "p4_linux_console_vt_t"
PID1_IOCTLS = {0x4b45, 0x540b, 0x540d, 0x5413, 0x542a, 0x542b}
LOGIND_IOCTLS = {0x4b3a, 0x4b45, 0x542a, 0x5602, 0x5603, 0x5605, 0x5606}
VT_PERMISSIONS = {
    "kernel": set(),
    "p4_linux_early_t": {"getattr", "relabelto"},
    "init_t": set("getattr open read write lock ioctl".split()),
    "p4_linux_service_executor_t": set("getattr open read write ioctl".split()),
    ROLE: set("getattr open read write ioctl".split()),
    "p4_linux_udev_t": set("getattr setattr relabelfrom relabelto".split()),
    "p4_linux_logind_t": set("getattr open read write setattr ioctl".split()),
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
    # The normal ldconfig producer already publishes this shared console cache.
    # Its source contract fixes /etc, the temporary basename, class and result
    # type; the complete transition set must require this existing edge too.
    rows.add('(typetransition p4_linux_ldconfig_t p4_linux_sysusers_etc_root_t '
             'file "ld.so.cache~" p4_linux_console_ld_cache_native_config_t)')
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
    result = {target: 0 for target in IOCTL_TARGETS}
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
                not targets.issubset(IOCTL_TARGETS)):
            raise ValueError("Console ioctl filter extends beyond the fixed VT and null types")
        mask = _ioctl_mask(form[3][2])
        for target in targets:
            result[target] |= mask
    if any(mask != sum(1 << number for number in IOCTL_TARGETS[target])
           for target, mask in result.items()):
        raise ValueError("Console ioctl set differs from the normal VT/null call closure")
    return {target: sorted(numbers) for target, numbers in IOCTL_TARGETS.items()}



def _verify_native_terminals(policy, lines, text, classes):
    """All concrete actors and every chr permission on the new Linux-only VT."""
    members = Membership(text)
    names = classes["chr_file"]
    _, bits = policy.permissions("chr_file", names)
    vectors = []
    for role, actor in _roles(lines):
        actual = policy.context_av(_context(role, actor),
            _context("object_r", VT_TYPE), "chr_file", names)
        permissions = {name for name, bit in bits.items() if actual & bit}
        expected = VT_PERMISSIONS.get(actor)
        if expected is None:
            # Pre-existing metadata observers may retain only getattr.
            if permissions - {"getattr"}:
                raise ValueError("Unselected actor has Linux VT authority: " + actor)
        elif permissions != expected:
            raise ValueError("Linux VT actor permission differs: " + actor + " " +
                             repr(sorted(permissions)) + "/" + repr(sorted(expected)))
        vectors.append([role, actor, sorted(permissions)])
    filters = {}
    for actor, targets, wanted in (
        ("init_t", ("p4_linux_console_t", VT_TYPE), PID1_IOCTLS),
        ("p4_linux_service_executor_t", ("p4_linux_console_t", VT_TYPE), {0x542a}),
        ("p4_linux_logind_t", (VT_TYPE,), LOGIND_IOCTLS),
    ):
        for target in targets:
            actual = 0
            for line in lines:
                if not line.startswith("(allowx "):
                    continue
                form = parse_expression(line)
                if (members.member(form[1], actor) and members.member(form[2], target) and
                        form[3][:2] == ["ioctl", "chr_file"]):
                    actual |= _ioctl_mask(form[3][2])
            if actual != sum(1 << number for number in wanted):
                raise ValueError("Native terminal ioctl boundary differs: " + actor + " " + target)
            filters[actor + ":" + target] = sorted(wanted)
    return {"fixed_kernel_nodes": 65, "all_actor_vectors": len(vectors),
            "vector_sha256": hashlib.sha256(json.dumps(vectors, sort_keys=True).encode()).hexdigest(),
            "fixed_ioctl_filters": filters,
            "runtime_qualified": False}



def _verify_early_vt_metadata(policy, lines, text, classes, objects):
    """The source-owned FINISH path has no generic device body or MAC authority."""
    actor = "p4_linux_early_t"
    rows = []
    def exact(target, cls, wanted, source=actor, source_role="system_r",
              target_role="object_r", level="s0"):
        names = classes[cls]
        _, bits = policy.permissions(cls, names)
        actual = policy.context_av(_context(source_role, source, level),
            _context(target_role, target, level), cls, names)
        got = {name for name, bit in bits.items() if actual & bit}
        if got != set(wanted):
            raise ValueError("FINISH metadata boundary differs: " + source + " " +
                target + " " + cls + " " + repr(sorted(got)) + "/" + repr(sorted(wanted)))
        rows.append([source, target, cls, level, sorted(got)])
    for level in ("s0", "s0:c0,c1", "s0:c0.c1023"):
        # This independent check includes kernel, which the existing Android
        # userspace preservation walk deliberately does not enumerate.
        exact("device", "chr_file", {"getattr"}, source="kernel", source_role="r", level=level)
        exact("device", "chr_file", {"getattr", "relabelfrom"}, level=level)
        exact(VT_TYPE, "chr_file", {"getattr", "relabelto"}, level=level)
        exact("kmsg_device", "chr_file", {"getattr", "relabelto"}, level=level)
    for target, wanted in {
        "device": {"getattr", "search"},
        "p4_linux_native_dev_root_t": {"getattr", "search"},
        "proc": {"search"}, actor: {"getattr", "search"},
        "sysfs": {"search"}, "selinuxfs": {"search"},
        "p4_linux_run_t": {"search"},
        "p4_linux_early_handoff_dir_t": {"getattr", "search", "open", "read"},
        "p4_linux_policy_epoch_dir_t": {"getattr", "search", "open", "read"},
    }.items():
        exact(target, "dir", wanted, target_role="system_r" if target == actor else "object_r")
    exact(actor, "lnk_file", {"read"}, target_role="system_r")
    for target in ("device", "proc", "tmpfs", "selinuxfs",
                   "p4_kernel_ns_handle_t", "p4_kernel_pid_handle_t"):
        exact(target, "filesystem", {"getattr"})
    exact("selinuxfs", "file", {"getattr", "open", "read"})
    exact("p4_linux_apparmor_epoch_t", "file", {"getattr", "open", "read"})
    exact("p4_kernel_ns_handle_t", "file", {"getattr", "open", "read", "ioctl"})
    # The selected pidfs inode is S_PRIVATE. Its SELinux open/ioctl hook returns
    # before AV checks; never grant PID handle body or command rights anyway.
    exact("p4_kernel_pid_handle_t", "file", set())
    exact("kernel", "security", set(), target_role="r")
    exact("device", "filesystem", {"associate"}, source=VT_TYPE, source_role="object_r")
    exact("tmpfs", "filesystem", set(), source=VT_TYPE, source_role="object_r")
    exact("device", "filesystem", {"associate"}, source="kmsg_device", source_role="object_r")
    members = Membership(text)
    nonboard_reads = 0
    names = classes["file"]
    _, bits = policy.permissions("file", names)
    for target in objects:
        if not members.member("p4_all_nonboard", target):
            continue
        actual = policy.context_av(_context("system_r", actor),
            _context("object_r", target), "file", names)
        wanted = {"open", "read"} if target in ("selinuxfs", "p4_kernel_ns_handle_t") else set()
        got = {name for name in ("open", "read", "write", "append", "execute",
                "execute_no_trans", "entrypoint", "map") if actual & bits[name]}
        if got != wanted:
            raise ValueError("FINISH acquired an unrelated original file body: " + target)
        nonboard_reads += 1
    ioctl = 0
    for line in lines:
        if not line.startswith("(allowx "):
            continue
        form = parse_expression(line)
        if members.member(form[1], actor):
            if (form[3][:2] != ["ioctl", "file"] or
                    not members.member(form[2], "p4_kernel_ns_handle_t")):
                raise ValueError("FINISH has an unrelated ioctl filter")
            ioctl |= _ioctl_mask(form[3][2])
    if ioctl != (1 << 0xb703):
        raise ValueError("FINISH namespace ioctl is not only NS_GET_NSTYPE")
    return {"phase": "post_self_exec_early_before_systemd",
            "kernel_device_chr_permissions": ["getattr"],
            "fixed_metadata_vectors": len(rows),
            "fixed_metadata_vector_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
            "original_file_objects_checked": nonboard_reads,
            "pidfd_private_inode_additional_file_permissions": [],
            "namespace_ioctl": [0xb703],
            "cross_exec_vt_descriptors": False,
            "cross_exec_kmsg_descriptors": False,
            "kmsg_body_access": False,
            "runtime_qualified": False}

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
        if row["category"] == "interpreter" and not (
                row["paths"] == ["/usr/bin/dash"] and row["mode"] == 0o755 and
                row["nlink"] == 1 and row["source_type"] == "p4_linux_native_bin_t" and
                row["target_type"] == "p4_linux_console_interpreter_native_bin_t"):
            raise ValueError("Console interpreter is not the fixed normal dash inode")
        if row["category"] == "mmap_data":
            cache = (row["paths"] == ["/etc/ld.so.cache"] and
                     row["source_type"] == "p4_linux_native_config_t" and
                     row["target_type"] == "p4_linux_console_ld_cache_native_config_t")
            locale = (len(row["paths"]) == 1 and
                      (row["paths"][0] == "/usr/lib/locale/locale-archive" or
                       row["paths"][0].startswith("/usr/lib/locale/C.utf8/")) and
                      row["source_type"] == "p4_linux_runtime_lib_t" and
                      row["target_type"] == "p4_linux_console_locale_runtime_lib_t")
            if not (row["mode"] == 0o644 and row["nlink"] == 1 and (cache or locale)):
                raise ValueError("Mapped console data selects an executable or arbitrary path")
        for path in row["paths"]:
            if (not path.startswith(("/usr/", "/etc/")) or "/../" in path or
                    path in seen):
                raise ValueError("Repeated or escaping console inode alias")
            seen.add(path)
    return value


def _extra(actor, target):
    """Only fixed entry/interpreter/cache operations differ for old actors."""
    if (target == "p4_linux_console_interpreter_native_bin_t" and
            actor in INTERPRETER_OPENERS):
        # open_exec under the old SID; bprm still selects the script's SID.
        # No execute_no_trans, entrypoint, or arbitrary helper execution.
        return {"getattr", "open", "read", "execute"}
    if actor == "p4_linux_netplan_t" and target == "p4_linux_console_library_runtime_lib_t":
        # Explicit fixed shared-library dependency, not all runtime_lib files.
        return {"getattr", "open", "read", "execute", "map"}
    if target == "p4_linux_console_ld_cache_native_config_t" and actor in CACHE_LOADERS:
        return {"getattr", "open", "read", "map"}
    if target in ("p4_linux_console_entry_runtime_lib_t",
                  "p4_linux_console_vtrgb_native_bin_t"):
        if actor in ("init_t", "p4_linux_service_executor_t"):
            return {"getattr", "open", "read", "execute", "map"}
    if (target == "p4_linux_console_cache_exec_native_config_t" and
            actor == "p4_linux_udev_t"):
        return {"getattr", "open", "read", "execute", "map"}
    return set()


def _cache_loader_preimages(policy, lines, classes):
    """Admit only existing raw cache edges; never manufacture a missing grant."""
    text = "\n".join(lines)
    if re.search(r"\((?:booleanif|tunableif)\b", text):
        raise ValueError("Console cache preimage requires unconditional raw authority")
    members = Membership(text)
    roles = set(_roles(lines))
    actors = sorted({actor for _, actor in roles})
    cache = "p4_linux_console_ld_cache_native_config_t"
    original = "p4_linux_native_config_t"
    interpreter = "p4_linux_elf_interpreter_t"
    targets = (original, cache, interpreter)
    raw = {(actor, target): set() for actor in actors for target in targets}
    parsed = 0
    for line in lines:
        if not line.startswith("(allow "):
            continue
        parsed += 1
        form = parse_expression(line)
        if len(form) != 4 or not isinstance(form[3], list) or len(form[3]) != 2:
            raise ValueError("Unsupported console cache raw statement")
        source, target, (cls, names) = form[1:]
        if cls not in classes or not isinstance(names, list) or not set(names) <= set(classes[cls]):
            raise ValueError("Unknown console cache raw class or permission")
        if cls != "file":
            continue
        selected = [t for t in targets if target != "self" and members.member(target, t)]
        if not selected:
            continue
        for actor in actors:
            if members.member(source, actor):
                for obj in selected:
                    raw[(actor, obj)].update(names)
    if parsed != text.count("(allow "):
        raise ValueError("Console cache raw authority is incomplete")
    # Every non-isolated actor retains its source vector. Only the existing
    # concrete loader roster can contribute an independently reviewed delta.
    for actor in actors:
        if actor in (ROLE, "p4_linux_ldconfig_t"):
            continue
        before, preimage = raw[(actor, original)], raw[(actor, cache)]
        extra = _extra(actor, cache)
        if not preimage <= before | extra:
            raise ValueError("Console cache lacks its exact explicit preimage: " + actor)
    production = {"p4_linux_production_commit_t", "p4_linux_production_verify_t"}
    if {t for t in members.types if members.member("p4_production_commit_actors", t)} != production:
        raise ValueError("Console cache production actor attribute differs")
    wanted = {
        original: set(),
        cache: {"getattr", "open", "read", "map"},
        interpreter: {"getattr", "open", "read", "execute", "map"},
    }
    _, bits = policy.permissions("file", classes["file"])
    checks = []
    for actor in sorted(ISOLATED_CACHE_LOADERS):
        if {(role, name) for role, name in roles if name == actor} != {("system_r", actor)}:
            raise ValueError("Console isolated cache loader role differs: " + actor)
        for target, permissions in wanted.items():
            if raw[(actor, target)] != permissions:
                raise ValueError("Console isolated loader raw preimage differs: " + actor + " " + target)
            mask = sum(bits[name] for name in permissions)
            for level in LEVELS:
                actual = policy.context_av(_context("system_r", actor, level),
                    _context("object_r", target), "file", classes["file"])
                if actual != mask:
                    raise ValueError("Console isolated loader constrained preimage differs: " + actor + " " + target)
                checks.append([actor, target, level, sorted(permissions)])
    return {"fixed_isolated_loaders": sorted(ISOLATED_CACHE_LOADERS),
            "all_concrete_cache_actor_preimages_checked": len(actors) - 2,
            "raw_and_constrained_vectors": len(checks),
            "vector_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True).encode()).hexdigest()}


def derive(library, baseline, exported, here, output, export):
    value = contract(here)
    extras = {}
    actors = {"init_t", "p4_linux_service_executor_t", "p4_linux_udev_t",
              *CACHE_LOADERS}
    for row in value["aliases"]:
        for actor in sorted(actors):
            names = _extra(actor, row["target"]) if row["class"] == "file" else set()
            if names:
                extras[(actor, row["target"], row["class"])] = names
    expected = derive_preserved_aliases(library, baseline, exported,
        value["aliases"], output, export, prefix="p4_console_preserved",
        isolated_roles={ROLE, "p4_linux_ldconfig_t"}, extra_permissions=extras, preamble=(
            "; Derived from the actual normal pre-console-alias binary.",
            "; Preserve all existing concrete actors; no generic execute grant."))
    # The generated file cannot be linked until its three new concrete deltas
    # are proved against the actual pre-console binary, including denied bits.
    expected["cache_loader_preimages"] = _cache_loader_preimages(
        ContextPolicy(library, baseline), exported.read_text().splitlines(),
        expected["classes"])
    expected["contract_sha256"] = hashlib.sha256(
        (here / "native-console-setup.json").read_bytes()).hexdigest()
    return expected


def verify(library, binary, exported, here, expected, export):
    policy = ContextPolicy(library, binary)
    lines = export(policy, binary, exported)
    value = contract(here)
    transitions = _verify_transitions(lines, expected["transitions"])
    text = exported.read_text()
    objects = sorted(re.findall(r"\(roletype object_r (\w+)\)", text))
    ioctls = _verify_ioctl_filters(lines, text, objects)
    native_terminals = _verify_native_terminals(policy, lines, text, expected["classes"])
    finish_metadata = _verify_early_vt_metadata(policy, lines, text, expected["classes"], objects)
    checks = verify_preserved_aliases(policy, exported, value["aliases"], expected)
    cache_preimages = _cache_loader_preimages(policy, lines, expected["classes"])
    if cache_preimages != expected["cache_loader_preimages"]:
        raise ValueError("Console fixed loader cache preimages changed during linking")
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
        if category in ("helper", "interpreter", "entry", "vtrgb", "cache_exec"):
            av(target, "file", ["open", "read", "execute", "execute_no_trans", "map"],
               ["open", "read", "execute", "execute_no_trans", "map"])
        elif category == "mmap_data":
            av(target, "file", ["open", "read", "map", "execute", "execute_no_trans",
                                "entrypoint", "write", "append"], ["open", "read", "map"])
        elif category == "library":
            av(target, "file", ["open", "read", "execute", "execute_no_trans", "map"],
               ["open", "read", "execute", "map"])
        else:
            av(target, "file", ["open", "read", "execute", "execute_no_trans"], ["open", "read"])
    # Exact old-actor interpreter gates: a direct dash exec cannot stay in
    # the executor/udev domain; only the initial fixed script chooses console.
    for actor in sorted(INTERPRETER_OPENERS):
        target = "p4_linux_console_interpreter_native_bin_t"
        names = ["execute", "execute_no_trans", "entrypoint", "write", "append"]
        actual = policy.context_av(_context("system_r", actor),
                                   _context("object_r", target), "file", names)
        _, bits = policy.permissions("file", names)
        if actual != bits["execute"]:
            raise ValueError("Console interpreter permits a direct shell or write: " + actor)
        checks.append([actor, target, "file", ["execute"]])
    for actor in sorted(CACHE_LOADERS):
        # The exception is justified by the already admitted loader edge.
        names = ["open", "read", "execute", "map"]
        role = "r" if actor in ("droidloom_engine_observer", "droidloom_policy_loader") else "system_r"
        actual = policy.context_av(_context(role, actor),
            _context("object_r", "p4_linux_elf_interpreter_t"), "file", names)
        _, bits = policy.permissions("file", names)
        if actual != sum(bits.values()):
            raise ValueError("Cache reader is not an admitted native loader: " + actor)
    from derive_native_tmpfiles_policy import DEVICE_VIEWS
    fixed_device_views = [
        {"source": "device", "target": "p4_linux_tmpfiles_static_dir_t", "class": "dir"},
        {"source": "device", "target": "p4_linux_tmpfiles_static_node_t", "class": "chr_file"},
    ]
    if DEVICE_VIEWS != fixed_device_views:
        raise ValueError("The two fixed tmpfiles device class views changed")
    # The fresh static-node type preserves the original device getattr only;
    # it is not a relabel-identity alias. Whole-class checks retain every denial.
    # Whole-class readback rejects inheritance to every other character device.
    # Null/random retain only the exact normal helper operations; no serial,
    # input, DRM, framebuffer body or arbitrary ioctl access is added.
    for target in objects:
        wanted = {
            "device": ["getattr"],
            "p4_linux_tmpfiles_static_node_t": ["getattr"],
            "null_device": ["getattr", "open", "read", "write", "ioctl"],
            "p4_linux_standardio_t": ["getattr", "open", "read", "write", "ioctl"],
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
            "alias_preserver_sha256": hashlib.sha256(
                (here / "derive_preserved_alias_policy.py").read_bytes()).hexdigest(),
            "verifier_sha256": hashlib.sha256((here / "derive_native_console_policy.py").read_bytes()).hexdigest(),
            "complete_console_transition_count": transitions,
            "fixed_vt_ioctl_filters": {target: ioctls[target] for target in TTY_TYPES},
            "fixed_null_ioctl_filters": {target: ioctls[target] for target in NULL_TYPES},
            "fixed_interpreter_openers": sorted(INTERPRETER_OPENERS),
            "fixed_native_cache_readers": sorted(CACHE_LOADERS),
            "fixed_isolated_cache_loader_preimages": cache_preimages,
            "fixed_linux_vt_inventory": native_terminals,
            "postload_vt_metadata": finish_metadata,
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
        for filename in ["/dev/tty", *("/dev/tty" + str(n) for n in range(64))]:
            if lookup(filename, stat.S_IFCHR) != VT_TYPE:
                raise ValueError("Linux VT context missing: " + filename)
            for other in (stat.S_IFREG, stat.S_IFLNK, stat.S_IFDIR):
                try:
                    actual = lookup(filename, other)
                except OSError as error:
                    if error.errno != 2:
                        raise
                else:
                    if actual == VT_TYPE:
                        raise ValueError("Linux VT context accepted a non-character inode")
            checked.append([filename, VT_TYPE])
        for filename in ("/dev/tty64", "/dev/ttyS0", "/dev/tty063",
                         "/dev/tty-1", "/dev/tty/child", "/dev/pts/0"):
            try:
                actual = lookup(filename, stat.S_IFCHR)
            except OSError as error:
                if error.errno != 2:
                    raise
            else:
                if actual == VT_TYPE:
                    raise ValueError("Linux VT context extends to an unselected node")
        if lookup("/dev/kmsg", stat.S_IFCHR) != "kmsg_device":
            raise ValueError("Original Linux kernel-log context missing")
        checked.append(["/dev/kmsg", "kmsg_device"])
        for filename, mode in [
            ("/dev/kmsg", stat.S_IFREG), ("/dev/kmsg", stat.S_IFDIR),
            ("/dev/kmsg", stat.S_IFLNK), ("/dev/kmsg0", stat.S_IFCHR),
            ("/dev/kmsg/child", stat.S_IFCHR),
        ]:
            try:
                actual = lookup(filename, mode)
            except OSError as error:
                if error.errno != 2:
                    raise
            else:
                if actual == "kmsg_device":
                    raise ValueError("Original kernel-log context accepted a different path or inode kind")
            checked.append([filename, mode, "not_kmsg_device"])
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
            "original_kernel_log_positive_and_negative_cases": 6,
            "matrix_sha256": hashlib.sha256(json.dumps(checked).encode()).hexdigest()}
