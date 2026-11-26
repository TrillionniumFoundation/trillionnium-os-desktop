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
            "exact_transitions": len(required), "matrix_sha256": hashlib.sha256(
                json.dumps(checks, separators=(",", ":")).encode()).hexdigest(),
            "runtime_qualified": False, "physical_arm_authorized": False}
