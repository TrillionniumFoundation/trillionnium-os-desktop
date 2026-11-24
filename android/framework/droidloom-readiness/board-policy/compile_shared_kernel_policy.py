#!/usr/bin/env python3
"""Link the Pocket4 shared-kernel policy using the original Android assertions."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from derive_shared_payload_cgroup_policy import Decision, Policy, derive, verify


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def add_namespace_to_board_guard(source):
    original = "(typeattributeset p4_nonboard_except_kernel_cmdline (and (p4_all_nonboard) (not (proc_cmdline))))"
    registered = "(typeattributeset p4_nonboard_except_kernel_cmdline (and (p4_all_nonboard) (not (or (proc_cmdline) (p4_kernel_ns_handle_t)))))"
    if source.count(original) != 1:
        raise ValueError("Expected the board's single Linux PID 1 command-line guard")
    return source.replace(original, registered).replace(
        "p4_nonboard_except_kernel_cmdline", "p4_nonboard_except_kernel_cmdline_and_pidns_handle"
    )


def compile_policy(compiler, inputs, output, contexts, environment):
    subprocess.run(
        [str(compiler), "-m", "-M", "true", "-G", "-c", "30", "-o", str(output),
         "-f", str(contexts), *(str(path) for path in inputs)],
        env=environment,
        check=True,
    )


def export_binary_policy(policy, binary, output):
    """Read transitions back from the linked binary using the pinned libsepol."""
    lib = policy.lib
    lib.sepol_policydb_create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
    lib.sepol_policydb_create.restype = ctypes.c_int
    lib.sepol_policydb_free.argtypes = [ctypes.c_void_p]
    lib.sepol_policydb_free.restype = None
    lib.sepol_policydb_from_image.argtypes = [
        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
    lib.sepol_policydb_from_image.restype = ctypes.c_int
    lib.sepol_kernel_policydb_to_cil.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    lib.sepol_kernel_policydb_to_cil.restype = ctypes.c_int
    database = ctypes.c_void_p()
    if lib.sepol_policydb_create(ctypes.byref(database)) != 0:
        raise ValueError("Cannot allocate linked policy readback")
    stream = None
    try:
        raw = binary.read_bytes()
        image = ctypes.create_string_buffer(raw)
        if lib.sepol_policydb_from_image(None, image, len(raw), database) != 0:
            raise ValueError("Cannot parse linked policy for transition readback")
        stream = policy.libc.fopen(str(output).encode(), b"wb")
        if not stream:
            raise ValueError("Cannot open private binary-policy readback output")
        # The admitted AOSP libsepol's public sepol_policydb wrapper contains
        # exactly one policydb member. Both interfaces use that original object.
        if lib.sepol_kernel_policydb_to_cil(stream, database) != 0:
            raise ValueError("Cannot export linked policy transitions")
        if policy.libc.fclose(stream) != 0:
            stream = None
            raise ValueError("Cannot finish linked policy readback")
        stream = None
    finally:
        if stream:
            policy.libc.fclose(stream)
        lib.sepol_policydb_free(database)
    return {line.strip() for line in output.read_text().splitlines()}


def verify_public_apk_payload(check, obj, client, broker):
    """Observe real linked decisions for the immutable public APK transport."""
    payload = obj("droidloom_public_apk_payload")
    for class_name in ("file", "memfd_file"):
        check(client, payload, class_name,
              ["create", "getattr", "open", "read", "write", "setattr"], True)
        check(broker, payload, class_name, ["getattr", "read"], True)
        check(broker, payload, class_name,
              ["open", "write", "append", "create", "setattr", "map", "execute"], False)
        check(client, payload, class_name, ["map", "execute"], False)
    check(broker, client, "fd", ["use"], True)
    check(broker, obj("tmpfs"), "filesystem", ["getattr"], True)
    for subject in (client, broker):
        for target in ("p4_linux_user_home_t", "p4_linux_tmp_t"):
            check(subject, obj(target), "file",
                  ["open", "read", "write", "append", "create"], False)
            check(subject, obj(target), "dir",
                  ["search", "open", "read", "write", "add_name"], False)
    check(client, obj("p4_linux_native_data_t"), "file", ["getattr", "open", "read"], True)
    check(broker, obj("p4_linux_native_data_t"), "file", ["open", "read", "write"], False)
    check(client, obj("proc"), "dir", ["getattr", "search"], True)
    check(client, obj("proc"), "dir", ["open", "read", "write"], False)
    check(client, obj("proc"), "file", ["open", "read", "write"], False)
    check(client, "u:system_r:p4_linux_user_session_t:s0", "dir", ["search", "open", "read"], False)
    check(client, "u:system_r:p4_linux_user_session_t:s0", "lnk_file", ["read"], False)


def verify_host_control(library, binary, export):
    """Verify fixed host entrypoints and positive/negative binary AV decisions."""
    policy = Policy(library, binary)
    sids = {}

    def sid(context):
        if context not in sids:
            value = ctypes.c_uint32()
            raw = context.encode()
            if policy.lib.sepol_context_to_sid(
                    raw, len(raw) + 1, ctypes.byref(value)) != 0:
                raise ValueError("Invalid linked host-control context: " + context)
            sids[context] = value.value
        return sids[context]

    checks = []

    def check(subject, target, class_name, permissions, expected):
        number, bits = policy.permissions(class_name, permissions)
        mask = 0
        for bit in bits.values():
            mask |= bit
        decision = Decision()
        if policy.lib.sepol_compute_av(
                sid(subject), sid(target), number, mask, ctypes.byref(decision)) != 0:
            raise ValueError("Cannot evaluate linked host-control AV decision")
        actual = decision.allowed & mask
        wanted = mask if expected else 0
        if actual != wanted:
            raise ValueError(
                f"Linked host-control decision differs: {subject} -> {target} "
                f"{class_name} {permissions}, expected {wanted:#x}, actual {actual:#x}")
        checks.append([subject, target, class_name, permissions, expected, actual])

    def obj(name):
        return f"u:object_r:{name}:s0"

    helper = "u:r:droidloom_package_helper:s0"
    client = "u:system_r:droidloom_public_control_client:s0"
    session = "u:system_r:p4_linux_user_session_t:s0"
    setup = "u:system_r:p4_linux_setup_t:s0"
    executor = "u:system_r:p4_linux_service_executor_t:s0"
    manager = "u:system_r:init_t:s0"
    broker = "u:r:droidloom_broker:s0"
    loader = "u:r:droidloom_policy_loader:s0"
    kernel = "u:r:kernel:s0"
    socket = obj("droidloom_public_control_socket")
    directory = obj("droidloom_public_control_dir")
    helper_exec = obj("droidloom_package_helper_exec")
    client_exec = obj("droidloom_public_control_client_exec")

    # The held startup lock is born on tmpfs before the first policy load.
    # Only the original kernel-domain boot owner labels that inode once.
    check(kernel, obj("tmpfs"), "file", ["relabelfrom"], True)
    check(kernel, obj("p4_linux_instance_lock_t"), "file",
          ["getattr", "relabelto", "open", "read", "lock"], True)
    for subject in [helper, client, broker]:
        check(subject, obj("tmpfs"), "file", ["relabelfrom"], False)

    check(session, helper, "process", ["transition"], True)
    check(session, helper, "process", ["dyntransition", "ptrace"], False)
    check(session, helper_exec, "file", ["execute", "read", "open", "map"], True)
    check(session, helper_exec, "file", ["execute_no_trans"], False)
    check(helper, helper_exec, "file", ["entrypoint"], True)
    check(session, client, "process", ["transition"], True)
    check(session, client_exec, "file", ["execute_no_trans"], False)
    check(client, client_exec, "file", ["entrypoint"], True)
    for subject in [client, setup, manager, executor, broker]:
        check(subject, helper, "process", ["transition", "dyntransition", "ptrace"], False)
    check(session, loader, "process", ["transition", "dyntransition", "ptrace"], False)
    for subject in [helper, client]:
        check(subject, broker, "unix_stream_socket", ["connectto"], True)
        check(subject, socket, "sock_file", ["getattr", "write"], True)
        check(subject, directory, "dir", ["getattr", "search"], True)
        check(subject, directory, "dir", ["write", "add_name", "remove_name"], False)
        check(subject, socket, "sock_file", ["create", "unlink", "rename", "relabelto"], False)
    check(session, broker, "unix_stream_socket", ["connectto"], False)
    check(session, socket, "sock_file", ["write"], False)
    for subject in ["u:r:init:s0", "u:r:untrusted_app:s0"]:
        check(subject, broker, "unix_stream_socket", ["connectto"], False)
        check(subject, socket, "sock_file", ["write"], False)
        check(subject, helper, "process", ["transition", "dyntransition", "ptrace"], False)
        check(helper, subject, "process", ["transition", "dyntransition", "ptrace", "signal"], False)
    check(broker, broker, "unix_stream_socket",
          ["create", "bind", "listen", "accept", "read", "write", "getattr", "getopt", "setopt"], True)
    check(broker, socket, "sock_file", ["create", "getattr", "setattr", "write", "unlink"], True)
    check(setup, obj("p4_linux_run_t"), "dir", ["write", "add_name"], True)
    check(setup, directory, "dir", ["create", "getattr", "search", "setattr"], True)
    check(setup, setup, "process", ["setfscreate"], True)
    check(setup, setup, "file", ["write", "append"], False)
    check(setup, kernel, "security", ["check_context", "compute_create"], True)
    check(setup, kernel, "security", ["load_policy", "setenforce", "setbool", "read_policy"], False)
    check(executor, obj("p4_linux_run_t"), "dir", ["write", "add_name", "remove_name"], False)
    check(helper, manager, "unix_stream_socket", ["connectto"], True)
    for unit in ["p4_linux_production_unit_file_t", "droidloom_package_native_unit_file"]:
        check(helper, obj(unit), "service", ["status", "stop"], True)
        check(helper, obj(unit), "service", ["start", "reload", "kill", "load", "enable", "disable"], False)
    check(helper, obj("p4_linux_unit_file_t"), "service", ["stop"], False)
    for unit in ["p4_linux_factory_unit_file_t", "droidloom_package_early_unit_file"]:
        check(helper, obj(unit), "service", ["status", "stop"], True)
        check(helper, obj(unit), "service", ["start", "reload", "kill", "load", "enable", "disable"], False)
        check(helper, obj(unit), "file", ["getattr", "open", "read", "write", "append", "map", "execute"], False)
    check(manager, obj("droidloom_package_early_unit_file"), "file", ["getattr", "open", "read", "map"], True)
    for subject in [broker, kernel, "u:r:droidloom_instance_launcher:s0"]:
        check(subject, obj("droidloom_package_early_unit_file"), "file", ["getattr", "open", "read", "write", "map", "execute"], False)
        check(subject, obj("droidloom_package_early_unit_file"), "service", ["start", "stop", "reload", "kill", "load", "enable", "disable"], False)
    check(helper, obj("p4_linux_factory_unit_cgroup_t"), "dir", ["getattr", "search"], True)
    check(helper, obj("p4_linux_factory_unit_cgroup_t"), "dir", ["open", "read", "write", "add_name", "remove_name", "create", "rmdir"], False)
    for target in ["p4_linux_factory_membership_t", "p4_linux_unit_cgroup_t"]:
        check(helper, obj(target), "file", ["getattr", "open", "read", "write", "append"], False)
    check(helper, obj("p4_linux_mac_setup_lock_t"), "file", ["open", "read", "lock"], True)
    check(helper, obj("p4_linux_mac_setup_lock_t"), "file", ["write", "append", "unlink"], False)
    check(broker, obj("p4_linux_mac_setup_lock_t"), "file", ["open", "read", "lock"], True)
    check(broker, obj("p4_linux_mac_setup_lock_t"), "file", ["write", "append"], False)
    fence = obj("droidloom_package_fence")
    check(helper, fence, "file", ["create", "open", "write", "read", "setattr"], True)
    check(helper, fence, "file", ["unlink", "rename", "append", "relabelfrom", "relabelto"], False)
    check(broker, fence, "file", ["open", "read"], True)
    check(broker, fence, "file", ["write", "append", "unlink", "rename"], False)
    check(helper, obj("droidloom_package_cgroup_events"), "file", ["getattr", "open", "read"], True)
    check(helper, obj("droidloom_package_cgroup_events"), "file", ["write", "append", "setattr"], False)
    check(client, obj("p4_linux_mac_release_input_t"), "file", ["getattr", "open", "read"], True)
    for subject in [helper, client]:
        check(subject, obj("p4_linux_product_store_t"), "file", ["open", "read", "write", "append"], False)
    check(helper, kernel, "security", ["load_policy", "setenforce", "setbool"], False)

    verify_public_apk_payload(check, obj, client, broker)

    # The native manager's actual FSCREATE and runtime-directory contract.
    check(manager, manager, "process", ["setfscreate"], True)
    check(manager, manager, "process", ["setcurrent", "dyntransition"], False)
    check(manager, kernel, "security", ["load_policy", "setenforce", "setbool"], False)
    check(manager, obj("p4_linux_systemd_run_t"), "dir",
          ["getattr", "open", "read", "search", "create", "write", "add_name", "remove_name"], True)
    check(manager, obj("p4_linux_systemd_run_t"), "dir", ["relabelfrom", "relabelto"], False)
    check(manager, obj("p4_linux_rootdir_t"), "dir",
          ["create", "write", "add_name", "remove_name", "relabelfrom", "relabelto"], False)
    check(manager, obj("p4_linux_etc_dir_t"), "dir", ["getattr", "open", "read", "search", "watch"], True)
    check(manager, obj("p4_linux_etc_dir_t"), "dir", ["write", "add_name", "remove_name"], False)
    check(manager, obj("p4_linux_systemd_config_t"), "dir", ["getattr", "open", "read", "search"], True)
    check(manager, obj("p4_linux_systemd_config_t"), "dir", ["create", "write", "add_name", "remove_name"], False)
    check(manager, obj("p4_linux_systemd_config_t"), "file", ["getattr", "open", "read"], True)
    check(manager, obj("p4_linux_systemd_config_t"), "file", ["create", "write", "append", "setattr"], False)
    check(manager, obj("p4_linux_credentials_root_t"), "dir", ["getattr", "open", "read", "search"], True)
    check(manager, obj("p4_linux_credentials_root_t"), "dir", ["create", "write", "add_name", "remove_name", "setattr"], False)
    for subject in [helper, client, broker, loader]:
        check(subject, subject, "process", ["setfscreate"], False)
    for subject in ["u:r:init:s0", "u:r:untrusted_app:s0"]:
        check(subject, obj("p4_linux_systemd_run_t"), "dir", ["open", "read", "search", "create", "write"], False)

    # Real native generator output custody and inherited stdout transport.
    generator = "u:system_r:p4_linux_generator_t:s0"
    output = obj("p4_linux_generator_output_t")
    inputs = obj("p4_linux_generator_directory_t")
    status = obj("p4_linux_systemd_status_t")
    for subject in [manager, generator]:
        check(subject, inputs, "dir", ["getattr", "search", "open", "read"], True)
        check(subject, inputs, "dir", ["create", "write", "add_name", "remove_name", "setattr"], False)
        check(subject, output, "dir",
              ["getattr", "search", "open", "read", "create", "write", "add_name", "remove_name", "rmdir"], True)
        check(subject, output, "file", ["getattr", "open", "read", "unlink"], True)
        check(subject, output, "lnk_file", ["getattr", "read", "unlink"], True)
        check(subject, output, "dir", ["relabelfrom", "relabelto", "mounton"], False)
        check(subject, output, "file",
              ["execute", "execute_no_trans", "entrypoint", "relabelfrom", "relabelto"], False)
        check(subject, obj("p4_linux_unit_file_t"), "file", ["write", "append", "create", "setattr"], False)
    check(generator, output, "file", ["write", "append", "create", "setattr", "rename"], True)
    check(generator, output, "lnk_file", ["write", "create", "setattr", "rename"], True)
    check(manager, output, "file", ["write", "append", "create", "setattr", "rename"], False)
    check(generator, obj("p4_linux_systemd_memfd_t"), "file", ["getattr", "read", "write"], True)
    check(generator, obj("p4_linux_systemd_memfd_t"), "file",
          ["open", "create", "map", "execute", "execute_no_trans", "entrypoint"], False)
    check(generator, obj("p4_linux_tmp_t"), "dir", ["create", "write", "add_name"], False)
    check(manager, status, "file", ["getattr", "open", "write", "create", "setattr", "unlink"], True)
    check(manager, obj("p4_linux_usrmerge_link_t"), "lnk_file", ["getattr", "read", "watch"], True)
    check(manager, obj("p4_linux_usrmerge_link_t"), "lnk_file",
          ["write", "create", "setattr", "rename", "unlink", "relabelfrom", "relabelto"], False)
    for subject in [helper, client, broker, loader, "u:system_r:p4_linux_user_session_t:s0",
                    "u:r:init:s0", "u:r:untrusted_app:s0"]:
        check(subject, output, "dir", ["create", "write", "add_name", "remove_name", "rmdir"], False)
        check(subject, output, "file", ["create", "write", "append", "setattr", "rename", "unlink"], False)
        check(subject, output, "lnk_file", ["create", "write", "setattr", "rename", "unlink"], False)
        check(subject, status, "file", ["open", "read", "write", "create", "setattr", "unlink"], False)

    # Original native service credentials and typed manager metadata.
    check(manager, obj("labeledfs"), "filesystem", ["getattr"], True)
    check(manager, obj("labeledfs"), "filesystem", ["mount", "remount", "unmount", "relabelfrom", "relabelto"], False)
    check(manager, obj("p4_linux_rootdir_t"), "dir", ["getattr", "search", "open", "read"], True)
    check(executor, executor, "process", ["setfscreate"], True)
    check(executor, executor, "process", ["setcurrent", "dyntransition"], False)
    check(executor, executor, "file", ["write", "append"], False)
    check(executor, kernel, "security", ["load_policy", "setenforce", "setbool"], False)
    credentials = [
        (setup, obj("p4_linux_setup_credentials_t")),
        ("u:system_r:p4_linux_sysctl_t:s0", obj("p4_linux_sysctl_credentials_t")),
        ("u:system_r:p4_linux_udev_t:s0", obj("p4_linux_udev_credentials_t")),
    ]
    for consumer, directory in credentials:
        check(executor, directory, "dir",
              ["getattr", "search", "open", "read", "create", "write", "setattr", "rename", "reparent", "rmdir"], True)
        check(consumer, directory, "dir", ["getattr", "search", "open", "read"], True)
        check(consumer, directory, "dir", ["create", "write", "add_name", "remove_name", "setattr"], False)
        check(executor, directory, "dir", ["add_name", "remove_name", "relabelfrom", "relabelto", "mounton"], False)
        check(executor, directory, "file", ["create", "open", "read", "write", "execute"], False)
        for other, _ in credentials:
            if consumer != other:
                check(other, directory, "dir", ["open", "read", "write", "create"], False)
        for subject in [helper, client, broker, loader, "u:r:init:s0", "u:r:untrusted_app:s0"]:
            check(subject, directory, "dir", ["open", "read", "write", "create", "setattr"], False)
    ask_directory = obj("p4_linux_ask_password_directory_t")
    invocation = obj("p4_linux_unit_invocation_t")
    check(manager, ask_directory, "dir", ["create", "getattr", "search", "open", "read", "watch"], True)
    check(manager, ask_directory, "dir", ["write", "add_name", "remove_name", "relabelfrom", "relabelto"], False)
    check(manager, invocation, "lnk_file", ["create", "getattr", "read", "rename", "unlink"], True)
    check(manager, invocation, "file", ["create", "open", "read", "write", "execute"], False)
    for subject in [helper, client, broker, loader, setup, executor, "u:r:init:s0", "u:r:untrusted_app:s0"]:
        check(subject, ask_directory, "dir", ["open", "read", "write", "create", "setattr"], False)
        check(subject, invocation, "lnk_file", ["create", "write", "rename", "unlink", "setattr"], False)
    for subject in [manager, executor]:
        check(subject, obj("p4_kernel_pid_handle_t"), "filesystem", ["getattr"], True)
        check(subject, obj("p4_kernel_ns_handle_t"), "filesystem", ["getattr"], False)
        check(subject, obj("p4_kernel_ns_handle_t"), "file", ["open", "read", "ioctl"], False)
        check(subject, obj("p4_kernel_pid_handle_t"), "file", ["open", "read", "ioctl"], False)
        check(subject, obj("p4_kernel_pid_handle_t"), "filesystem", ["mount", "remount", "unmount", "relabelfrom", "relabelto"], False)

    lines = export_binary_policy(policy, binary, export)
    transitions = [
        "(typetransition droidloom_public_control_client tmpfs file droidloom_public_apk_payload)",
        "(typetransition droidloom_public_control_client tmpfs memfd_file droidloom_public_apk_payload)",
        "(roletransition system_r droidloom_package_helper_exec process r)",
        "(typetransition p4_linux_user_session_t droidloom_package_helper_exec process droidloom_package_helper)",
        "(typetransition p4_linux_user_session_t droidloom_public_control_client_exec process droidloom_public_control_client)",
        "(typetransition p4_linux_user_executor_t droidloom_public_control_client_exec process droidloom_public_control_client)",
        '(typetransition p4_linux_setup_t p4_linux_run_t dir "droidloom" droidloom_public_control_dir)',
        '(typetransition droidloom_broker droidloom_public_control_dir sock_file "control.sock" droidloom_public_control_socket)',
        '(typetransition droidloom_package_helper droidloom_package_config_dir file "setup.lock" p4_linux_mac_setup_lock_t)',
        '(typetransition droidloom_package_helper droidloom_package_selection_dir file "package-maintenance.json" droidloom_package_fence)',
    ]
    transitions.extend(
        f'(genfscon cgroup2 "/system.slice/{unit}/cgroup.events" (u object_r droidloom_package_cgroup_events ((s0) (s0))))'
        for unit in ["droidloom-instance-factory.service", "droidloom-instance-launcher.service",
                     "droidloom-early-observer.service"])
    transitions.extend(
        f'(typetransition init_t p4_linux_systemd_run_t dir "{name}" p4_linux_generator_output_t)'
        for name in ["generator", "generator.early", "generator.late"])
    transitions.extend([
        '(typetransition init_t p4_linux_systemd_run_t file "show-status" p4_linux_systemd_status_t)',
        '(typetransition init_t p4_linux_generator_exec_t process p4_linux_generator_t)',
    ])
    transitions.append('(typetransition init_t p4_linux_systemd_run_t dir "ask-password" p4_linux_ask_password_directory_t)')
    for directory, units in [
        ("p4_linux_setup_credentials_t", ["systemd-tmpfiles-setup-dev-early.service", "systemd-tmpfiles-setup-dev.service", "systemd-tmpfiles-setup.service", "systemd-sysusers.service"]),
        ("p4_linux_sysctl_credentials_t", ["systemd-sysctl.service"]),
        ("p4_linux_udev_credentials_t", ["systemd-udev-load-credentials.service"]),
    ]:
        for unit in units:
            for parent in ["p4_linux_credentials_root_t", "p4_linux_credential_staging_t"]:
                transitions.append(f'(typetransition p4_linux_service_executor_t {parent} dir "{unit}" {directory})')
    missing = [line for line in transitions if line not in lines]
    if missing:
        raise ValueError("Linked binary lacks exact automatic transitions: " + repr(missing))
    return {
        "binary_access_checks": len(checks),
        "exact_automatic_transitions": len(transitions),
        "access_matrix_sha256": hashlib.sha256(
            json.dumps(checks, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "binary_export_sha256": sha256(export),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--secilc", type=Path, required=True)
    parser.add_argument("--sepol-library", type=Path, required=True)
    parser.add_argument("--android-cil", type=Path, action="append", required=True)
    parser.add_argument("--linux-board-cil", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    release = json.loads((here / "cp3a-kernel-handle-inputs.json").read_text())
    actual = sorted(sha256(path) for path in args.android_cil)
    expected = sorted(item["sha256"] for item in release["android_inputs"])
    if actual != expected:
        raise ValueError("The supplied Android policy inputs do not match the selected CP3A image")
    compiler = args.secilc.resolve(strict=True)
    library = args.sepol_library.resolve(strict=True)
    library_entry = args.sepol_library.absolute().parent / "libsepol.so.2"
    if (sha256(compiler) != release["secilc_sha256"] or
            sha256(library) != release["libsepol_sha256"] or
            library_entry.resolve(strict=True) != library):
        raise ValueError("The selected compiler and libsepol do not match the admitted build tools")
    environment = os.environ.copy()
    for key in ("LD_PRELOAD", "LD_AUDIT"):
        environment.pop(key, None)
    environment.update(LC_ALL="C", LD_LIBRARY_PATH=str(library_entry.parent))
    output = args.output.absolute()
    component_names = (
        "readiness-observer-android.cil", "readiness-host-challenge-interface.cil",
        "kernel-namespace-custody.cil", "cp3a-kernel-handle-access.cil",
        "early-readiness-inode-owner.cil", "linux-host-service-roles.cil",
        "linux-initial-calibration.cil", "protected-device-readiness-target.cil", "orderly-android-shutdown.cil",
        "ubuntu-real-root-interpreter.cil", "ubuntu-mounted-api-metadata.cil",
        "ubuntu-native-pid1-startup.cil", "ubuntu-native-generators.cil",
        "ubuntu-native-credential-directories.cil", "ubuntu-native-unit-metadata.cil",
        "ubuntu-core-cgroup-ownership.cil", "ubuntu-native-services.cil",
        "frontend-android-interface.cil", "linux-frontend-observer.cil", "instance-launcher.cil",
        "linux-query-owner.cil", "linux-fixed-metadata-observer.cil",
        "instance-factory-cgroup.cil", "ubuntu-systemd-unit-status.cil",
        "linux-application-roles.cil", "linux-install-catalog.cil",
        "ubuntu-dbus.cil", "ubuntu-native-selinux-query.cil",
        "ubuntu-native-pam.cil",
        "linux-package-maintenance.cil", "linux-public-control.cil",
    )
    components = [here / name for name in component_names]
    sources = [compiler, library, args.linux_board_cil, *args.android_cil, *components,
               here / "cp3a-kernel-handle-inputs.json", Path(__file__),
               here / "derive_shared_payload_cgroup_policy.py"]
    if any(output.resolve() == path.resolve() for path in sources):
        raise ValueError("The output path is a policy input or build tool")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix="pocket4-sepolicy-") as private:
        work = Path(private)
        original = work / "original.policy"
        contexts = work / "contexts"
        compile_policy(compiler, args.android_cil, original, contexts, environment)
        if sha256(original) != release["original_binary_sha256"]:
            raise ValueError("The linked original Android policy differs from its release digest")
        shared = work / "shared-payload.cil"
        contract = derive(library, original, args.android_cil, shared)
        board = work / "linux-board.cil"
        board.write_text(add_namespace_to_board_guard(args.linux_board_cil.read_text()))
        linked = work / "combined.policy"
        compile_policy(compiler, [*args.android_cil, board, *components, shared], linked, contexts, environment)
        shared_access = verify(library, linked, contract)
        host_control = verify_host_control(library, linked, work / "host-control-binary.cil")
        result = {
            "android_original": sha256(original),
            "secilc": sha256(compiler),
            "libsepol": sha256(library),
            "linux_board_source": sha256(args.linux_board_cil),
            "original_input_count": len(actual),
            "components": {part.name: sha256(part) for part in components},
            "output": sha256(linked),
            "shared_payload_android_access": shared_access,
            "host_control_binary_access": host_control,
            "shared_payload_deriver": sha256(here / "derive_shared_payload_cgroup_policy.py"),
        }
        os.replace(linked, output)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
