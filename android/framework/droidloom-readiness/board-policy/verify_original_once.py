"""Check the source-bound, nonprivileged original-return policy entry."""
import ctypes
import hashlib
import json
from derive_shared_payload_cgroup_policy import Decision, Policy
from verify_native_maintenance import CAP1, CAP2, FILE, SECURITY

RETURN = "p4_linux_once_return_t"
MAINTENANCE = "p4_linux_maintenance_t"
EXECUTOR = "p4_linux_service_executor_t"
WITNESS = "p4_linux_host_mount_identity_t"
EVIDENCE = "p4_linux_once_evidence_t"
SOURCE_PATHS = (
    "runtime/droidloom-early-boot/board_policy.c",
    "runtime/droidloom-supervisor/src/native_once_return.rs",
    "runtime/droidloom-supervisor/src/native_once_capabilities.rs",
    "runtime/droidloom-supervisor/src/native_once_contract.rs",
    "packaging/systemd/droidloom-original-once.target",
    "packaging/systemd/droidloom-original-once-return.service",
    "packaging/systemd/droidloom-original-once-return.timer",
    "android/framework/droidloom-readiness/board-policy/apparmor/droidloom-original-once-return",
    "android/framework/droidloom-readiness/board-policy/derive_native_console_policy.py",
    "android/framework/droidloom-readiness/board-policy/native-console-setup.json",
    "android/framework/droidloom-readiness/board-policy/derive_native_kmod_static_policy.py",
    "android/framework/droidloom-readiness/board-policy/derive_native_journal_catalog_policy.py",
    "android/framework/droidloom-readiness/board-policy/derive_native_random_seed_policy.py",
    "android/framework/droidloom-readiness/board-policy/derive_native_timesync_policy.py",
    "android/framework/droidloom-readiness/board-policy/derive_native_ldconfig_policy.py",
    "android/framework/droidloom-readiness/board-policy/derive_native_update_done_policy.py",
    "android/framework/droidloom-readiness/board-policy/derive_native_tmpfiles_policy.py",
    "runtime/droidloom-supervisor/src/native_original_copy_policy.rs",
)
DIRECTORY = ("ioctl read write create getattr setattr lock relabelfrom relabelto "
             "append map unlink link rename execute quotaon mounton audit_access "
             "open execmod watch watch_mount watch_sb watch_with_perm watch_reads "
             "add_name remove_name reparent search rmdir").split()
# These are the existing normal source types, independently stated here.
# The actual final policy is queried, never used to construct its own expected
# permissions. Every normal console alias must retain exactly this vector;
# only the one fixed loader cache has its explicit extra read/map contract.
CONSOLE_SOURCE_AV = {
    ("p4_linux_native_bin_t", "file"): [],
    ("p4_linux_native_config_t", "file"): [],
    ("p4_linux_native_data_t", "file"): [],
    ("p4_linux_runtime_lib_t", "file"): "getattr open read execute map".split(),
    ("p4_linux_rootdir_t", "dir"): ["getattr", "search"],
}


# These original vectors were checked independently against the immutable
# pre-component policy. Keep the eight source/class pairs explicit: the final
# alias policy cannot supply its own expectation. The existing console table
# above also retains its original native_bin:file zero vector.
FIXED_ALIAS_SOURCE_AV = {
    ("p4_linux_setup_exec_t", "file"): [],
    ("p4_linux_native_data_t", "file"): [],
    ("p4_linux_runtime_lib_t", "file"): "getattr open read execute map".split(),
    ("p4_linux_rootdir_t", "dir"): ["getattr", "search"],
    ("p4_linux_native_config_t", "file"): [],
    ("p4_linux_etc_dir_t", "dir"): ["getattr", "search"],
    ("port", "tcp_socket"): [],
    ("p4_linux_usrmerge_link_t", "lnk_file"): ["getattr", "read"],
}
TCP_SOCKET = ("ioctl read write create getattr setattr lock relabelfrom relabelto "
              "append map bind connect listen accept getopt setopt shutdown "
              "recvfrom sendto name_bind node_bind name_connect").split()
LNK_FILE = ("ioctl read write create getattr setattr lock relabelfrom relabelto "
            "append map unlink link rename execute quotaon mounton audit_access "
            "open execmod watch watch_mount watch_sb watch_with_perm watch_reads").split()
FIXED_NATIVE_ALIAS_ROWS = (
    ("derive_native_tmpfiles_policy.py", (
        ("p4_linux_setup_exec_t", "p4_linux_tmpfiles_exec_t", "file"),
        ("p4_linux_runtime_lib_t", "p4_linux_tmpfiles_usr_config_t", "file"),
        ("p4_linux_native_config_t", "p4_linux_tmpfiles_etc_config_t", "file"),
        ("p4_linux_rootdir_t", "p4_linux_tmpfiles_config_dir_t", "dir"),
        ("p4_linux_rootdir_t", "p4_linux_tmpfiles_runtime_dir_t", "dir"),
        ("p4_linux_native_data_t", "p4_linux_tmpfiles_nologin_t", "file"),
        ("p4_linux_usrmerge_link_t", "p4_linux_tmpfiles_shm_link_t", "lnk_file"),
    )),
    ("derive_native_kmod_static_policy.py", (
        ("p4_linux_rootdir_t", "p4_linux_kmod_tmpfiles_dir_t", "dir"),
        ("p4_linux_native_data_t", "p4_linux_kmod_static_nodes_t", "file"),
    )),
    ("derive_native_journal_catalog_policy.py", (
        ("p4_linux_rootdir_t", "p4_linux_journal_catalog_dir_t", "dir"),
        ("p4_linux_native_data_t", "p4_linux_journal_catalog_file_t", "file"),
    )),
    ("derive_native_random_seed_policy.py", (
        ("p4_linux_setup_exec_t", "p4_linux_random_seed_exec_t", "file"),
        ("p4_linux_native_data_t", "p4_linux_random_seed_file_t", "file"),
    )),
    ("derive_native_timesync_policy.py", (
        ("p4_linux_runtime_lib_t", "p4_linux_timesyncd_exec_t", "file"),
        ("p4_linux_rootdir_t", "p4_linux_timesyncd_run_t", "dir"),
        ("p4_linux_native_data_t", "p4_linux_timesyncd_run_t", "file"),
        ("p4_linux_rootdir_t", "p4_linux_timesyncd_state_t", "dir"),
        ("p4_linux_native_data_t", "p4_linux_timesyncd_state_t", "file"),
        ("p4_linux_native_config_t", "p4_linux_timesyncd_config_t", "file"),
        ("p4_linux_native_config_t", "p4_linux_timesyncd_nsswitch_t", "file"),
        ("p4_linux_rootdir_t", "p4_linux_timesyncd_netif_t", "dir"),
        ("p4_linux_native_data_t", "p4_linux_timesyncd_netif_t", "file"),
        ("port", "p4_linux_timesyncd_dns_port_t", "tcp_socket"),
    )),
    ("derive_native_ldconfig_policy.py", (
        ("p4_linux_setup_exec_t", "p4_linux_ldconfig_exec_t", "file"),
        ("p4_linux_native_config_t", "p4_linux_ldconfig_config_t", "file"),
        ("p4_linux_rootdir_t", "p4_linux_ldconfig_config_dir_t", "dir"),
        ("p4_linux_rootdir_t", "p4_linux_ldconfig_aux_dir_t", "dir"),
        ("p4_linux_native_data_t", "p4_linux_ldconfig_aux_t", "file"),
    )),
    ("derive_native_update_done_policy.py", (
        ("p4_linux_setup_exec_t", "p4_linux_update_done_exec_t", "file"),
        ("p4_linux_rootdir_t", "p4_linux_update_done_var_dir_t", "dir"),
        ("p4_linux_native_config_t", "p4_linux_update_done_etc_file_t", "file"),
        ("p4_linux_native_data_t", "p4_linux_update_done_var_file_t", "file"),
    )),
)


def fixed_native_aliases():
    # Import only the seven reviewed providers, then compare their complete
    # rows to this independent list. Unknown providers, added rows, changed
    # source types/classes and repeated target/class pairs all fail closed.
    from derive_native_kmod_static_policy import ALIASES as kmod
    from derive_native_journal_catalog_policy import ALIASES as catalog
    from derive_native_random_seed_policy import ALIASES as seed
    from derive_native_timesync_policy import ALIASES as timesync, PORT_ALIAS
    from derive_native_ldconfig_policy import ALIASES as ldconfig
    from derive_native_update_done_policy import ALIASES as update_done
    from derive_native_tmpfiles_policy import ALIASES as tmpfiles
    actual = {
        "derive_native_tmpfiles_policy.py": tmpfiles,
        "derive_native_kmod_static_policy.py": kmod,
        "derive_native_journal_catalog_policy.py": catalog,
        "derive_native_random_seed_policy.py": seed,
        "derive_native_timesync_policy.py": timesync + [PORT_ALIAS],
        "derive_native_ldconfig_policy.py": ldconfig,
        "derive_native_update_done_policy.py": update_done,
    }
    expected = {
        provider: [{"source": source, "target": target, "class": cls}
                   for source, target, cls in aliases]
        for provider, aliases in FIXED_NATIVE_ALIAS_ROWS
    }
    if actual != expected:
        raise ValueError("The fixed original-return native alias providers differ")
    rows = [row for aliases in expected.values() for row in aliases]
    seen = set()
    for row in rows:
        source = row["source"], row["class"]
        target = row["target"], row["class"]
        if source not in FIXED_ALIAS_SOURCE_AV or target in seen:
            raise ValueError("Unknown or repeated original-return native alias")
        seen.add(target)
    return rows


def source_inputs(here):
    return [here.parents[3] / path for path in SOURCE_PATHS]


def verify_sources(here):
    contract = json.loads((here / "original-once-source.json").read_text())
    if (contract["schema"] != "droidloom.original-once-source-contract.v1" or
            set(contract["files"]) != set(SOURCE_PATHS)):
        raise ValueError("The original-once source closure differs")
    actual = {}
    for relative, path in zip(SOURCE_PATHS, source_inputs(here)):
        body = path.read_bytes()
        pin = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        if pin != contract["files"][relative]:
            raise ValueError("Changed original-once source: " + relative)
        actual[relative] = pin
    c = source_inputs(here)[0].read_text()
    begin = c.index("int droidloom_board_activate_policy(")
    end = c.index("/* Reopen the typed, read-only first-load receipt", begin)
    call = c[begin:end]
    ordered = (
        "initial_ubuntu_kernel()",
        "hold_host_mount_identity(&mount_identity)",
        'submit(SELINUX_DIR "/load", policy.data, policy.size)',
        "droidloom_label_readiness_paths(&paths)",
        "publish_host_mount_identity(&mount_identity, paths.handoff.fd, policy.digest)",
        "droidloom_publish_apparmor_epoch(epoch_directory, status, policy.digest, &observation)",
        "close(mount_identity.fd)",
    )
    positions = [call.index(value) for value in ordered]
    if positions != sorted(positions) or any(call.count(v) != 1 for v in ordered):
        raise ValueError("Mount identity custody left the original first-load sequence")
    # Full source bytes above remain pinned, including comments. Inspect only
    # active rules here: a comment explaining why Px is forbidden is not Px.
    profile = "\n".join(line.split("#", 1)[0] for line in
                        source_inputs(here)[7].read_text().splitlines())
    for path in ("/usr/lib/droidloom/production/current/droidloom-maintenance", "/usr/bin/python3.14"):
        if profile.count(path + " mrix,") != 1:
            raise ValueError("NNP maintenance must keep the actual original AppArmor profile")
    if any(token in profile for token in (" Px", " px", " Ux", " ux", "complain")):
        raise ValueError("The fixed original-return AppArmor entry may not escape its NNP profile")
    return actual


def verify_original_once(library, binary, export, export_binary_policy, here):
    sources = verify_sources(here)
    policy = Policy(library, binary)
    lines = export_binary_policy(policy, binary, export)
    cached, checks = {}, []

    def sid(context):
        if context not in cached:
            encoded = context.encode()
            value = ctypes.c_uint32()
            if policy.lib.sepol_context_to_sid(encoded, len(encoded) + 1, ctypes.byref(value)):
                raise ValueError("Invalid original-once context: " + context)
            cached[context] = value.value
        return cached[context]

    def actor(name):
        return "u:system_r:" + name + ":s0"

    def obj(name):
        return "u:object_r:" + name + ":s0"

    def exact(source, target, cls, permissions, expected):
        number, bits = policy.permissions(cls, permissions)
        mask = 0
        for bit in bits.values():
            mask |= bit
        decision = Decision()
        if policy.lib.sepol_compute_av(sid(source), sid(target), number, mask, ctypes.byref(decision)):
            raise ValueError("Original-once binary AV query failed")
        got = {name for name, bit in bits.items() if decision.allowed & bit}
        if got != set(expected):
            raise ValueError(f"Original-once AV differs: {source}->{target} {cls}: {sorted(got)} != {sorted(expected)}")
        checks.extend([source, target, cls, name, name in got] for name in permissions)

    own, maint, executor = actor(RETURN), actor(MAINTENANCE), actor(EXECUTOR)
    for cls, permissions in (("capability", CAP1), ("capability2", CAP2),
                             ("cap_userns", CAP1), ("cap2_userns", CAP2)):
        exact(own, own, cls, permissions, [])
    exact(own, "u:r:kernel:s0", "security", SECURITY, [])
    exact(own, own, "process", "fork getattr getcap setcap sigchld setexec setcurrent dyntransition ptrace signal sigkill sigstop".split(),
          "fork getattr getcap setcap sigchld".split())
    exact(executor, own, "process", ["transition", "dyntransition"], ["transition"])
    exact(own, maint, "process", ["transition", "dyntransition", "ptrace", "signal", "sigkill"], ["transition"])
    exact(own, maint, "process2", ["nnp_transition", "nosuid_transition"], ["nnp_transition"])
    exact(own, obj("p4_linux_maintenance_exec_t"), "file", FILE, "getattr open read execute map".split())
    exact(own, obj("p4_linux_once_return_exec_t"), "file", FILE, "getattr open read execute map entrypoint".split())
    exact(own, obj("p4_linux_once_config_t"), "file", FILE, "getattr open read".split())
    exact(own, obj("p4_linux_mac_release_input_t"), "file", FILE, "getattr open read".split())
    for target in ("droidloom_package_config_dir", "droidloom_package_selection_dir"):
        exact(own, obj(target), "dir", DIRECTORY, ["getattr", "search"])
    exact(own, obj("p4_linux_systemd_state_parent_t"), "dir", DIRECTORY, ["getattr", "search"])
    exact(own, obj(WITNESS), "file", FILE, "getattr open read".split())
    exact("u:r:kernel:s0", obj(WITNESS), "file", FILE, "create getattr open read write setattr".split())
    exact(own, obj(EVIDENCE), "file", FILE, "getattr open read write create setattr lock".split())
    exact(maint, obj(EVIDENCE), "file", FILE, "getattr read write".split())
    for target in ("p4_linux_maintenance_grubenv_t", "p4_linux_maintenance_grubcfg_t",
                   "p4_linux_user_home_t", "p4_linux_product_store_t", "p4_linux_native_bin_t",
                   "p4_linux_host_config_t", "p4_linux_journal_database_t",
                   "p4_linux_volatile_journal_database_t"):
        exact(own, obj(target), "file", "open read write create execute execute_no_trans".split(), [])
    exact(own, obj("p4_linux_runtime_lib_t"), "file", FILE, "getattr open read execute map".split())
    aliases = json.loads((here / "native-console-setup.json").read_text())["aliases"]
    alias_names = set()
    for row in aliases:
        key = row["source"], row["class"]
        if key not in CONSOLE_SOURCE_AV or row["target"] in alias_names:
            raise ValueError("Unknown or repeated original-return console alias")
        alias_names.add(row["target"])
        expected = CONSOLE_SOURCE_AV[key]
        if row["target"] == "p4_linux_console_ld_cache_native_config_t":
            if key != ("p4_linux_native_config_t", "file"):
                raise ValueError("The fixed loader cache changed source or class")
            expected = ["getattr", "open", "read", "map"]
        exact(own, obj(row["target"]), row["class"],
              FILE if row["class"] == "file" else DIRECTORY, expected)
    native_aliases = fixed_native_aliases()
    permissions_by_class = {"file": FILE, "dir": DIRECTORY, "tcp_socket": TCP_SOCKET,
                            "lnk_file": LNK_FILE}
    for (source, cls), expected in FIXED_ALIAS_SOURCE_AV.items():
        exact(own, obj(source), cls, permissions_by_class[cls], expected)
    for row in native_aliases:
        exact(own, obj(row["target"]), row["class"],
              permissions_by_class[row["class"]],
              FIXED_ALIAS_SOURCE_AV[row["source"], row["class"]])
    exact(own, obj("p4_linux_root_block_t"), "blk_file", "getattr open read write ioctl map".split(), ["getattr"])
    exact(own, own, "unix_stream_socket", "create connect connectto bind listen accept".split(), [])
    exact(own, own, "unix_dgram_socket", "create connect bind sendto".split(), [])
    names = set()
    for line in lines:
        for role in ("r", "system_r"):
            prefix = f"(roletype {role} "
            if line.startswith(prefix):
                name = line[len(prefix):-1]
                if not name or any(c.isspace() or c in "()" for c in name):
                    raise ValueError("Nonconcrete original-once role")
                context = f"u:{role}:{name}:s0"
                if context in names:
                    continue
                names.add(context)
                exact(context, own, "process", ["transition", "dyntransition"],
                      ["transition"] if context == executor else [])
                exact(context, obj(WITNESS), "file", "create write append setattr unlink rename link relabelto relabelfrom".split(),
                      ["create", "write", "setattr"] if context == "u:r:kernel:s0" else [])
                exact(context, obj(EVIDENCE), "file", "create write append setattr unlink rename link".split(),
                      ["create", "write", "setattr"] if context == own else ["write"] if context == maint else [])
                if context != own:
                    exact(own, context, "dir", ["open", "read", "search"], [])
                    exact(own, context, "file", ["getattr", "open", "read"], [])
    required = (
        f'(typetransition {EXECUTOR} p4_linux_once_return_exec_t process {RETURN})',
        f'(typetransition {RETURN} p4_linux_maintenance_exec_t process {MAINTENANCE})',
        f'(typetransition kernel p4_linux_early_handoff_dir_t file "host-mount-identity.json" {WITNESS})',
        f'(typetransition {RETURN} {EVIDENCE} file {EVIDENCE})',
    )
    missing = [value for value in required if value not in lines]
    if missing:
        raise ValueError("Missing exact original-once transitions: " + repr(missing))
    return {"schema": "droidloom.original-once-policy-readback.v1", "source_files": sources,
            "actor_contexts_checked": len(names), "permission_checks": len(checks),
            "normal_console_aliases_checked": len(alias_names),
            "fixed_native_aliases_checked": len(native_aliases),
            "fixed_native_alias_sources_checked": len(FIXED_ALIAS_SOURCE_AV),
            "fixed_native_alias_providers": [name for name, _ in FIXED_NATIVE_ALIAS_ROWS],
            "exact_transitions": len(required), "matrix_sha256": hashlib.sha256(
                json.dumps(checks, separators=(",", ":")).encode()).hexdigest(),
            "runtime_qualified": False, "physical_arm_authorized": False}
