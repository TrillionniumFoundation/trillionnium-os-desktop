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
from verify_native_login_audit import verify_login_audit


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
    # This exact root-published selector has no live writer or generic-config grant.
    for reader in ['u:r:kernel:s0', 'u:r:droidloom_instance_launcher:s0', 'u:r:droidloom_broker:s0', 'u:r:droidloom_policy_loader:s0', 'u:system_r:droidloom_container_entry_t:s0', 'u:system_r:p4_linux_early_t:s0', 'u:r:droidloom_package_helper:s0', 'u:system_r:droidloom_public_control_client:s0']:
        check(reader, obj("p4_linux_public_launcher_t"), "file", ["getattr", "open", "read"], True)
        check(reader, obj("p4_linux_public_launcher_t"), "file", ["create", "write", "append", "setattr", "unlink", "link", "rename", "relabelto", "relabelfrom", "execute"], False)
    check("u:system_r:p4_linux_user_session_t:s0", obj("p4_linux_public_launcher_t"), "file", ["create", "write", "append", "setattr", "unlink", "link", "rename", "relabelto", "relabelfrom", "execute"], False)
    check(kernel, obj("p4_linux_native_config_t"), "file", ["getattr", "open", "read"], False)
    # Ordinary native home/state access does not admit Droidloom or Android.
    for role in ["p4_linux_user_session_t", "p4_linux_compositor_t", "p4_linux_audio_t", "p4_linux_desktop_portal_t"]:
        actor = "u:system_r:" + role + ":s0"
        check(actor, obj("p4_linux_user_home_t"), "dir", ["getattr", "search", "open", "read", "create", "write", "add_name", "remove_name", "setattr", "rmdir"], True)
        check(actor, obj("p4_linux_user_home_t"), "file", ["getattr", "open", "read", "write", "append", "create", "setattr", "lock", "map", "rename", "unlink"], True)
    for role in ["p4_linux_user_manager_t", "p4_linux_user_executor_t", "p4_linux_user_dbus_t"]:
        actor = "u:system_r:" + role + ":s0"
        check(actor, obj("p4_linux_user_home_t"), "file", ["getattr", "open", "read", "map"], True)
        check(actor, obj("p4_linux_user_home_t"), "file", ["create", "write", "append", "setattr", "unlink", "rename"], False)
    for role in ["p4_linux_user_session_t", "p4_linux_user_manager_t", "p4_linux_user_executor_t", "p4_linux_user_dbus_t", "p4_linux_compositor_t", "p4_linux_audio_t", "p4_linux_desktop_portal_t"]:
        actor = "u:system_r:" + role + ":s0"
        for target in ["p4_linux_user_home_t", "p4_linux_user_run_t", "p4_linux_tmp_t"]:
            check(actor, obj(target), "file", ["execute", "execute_no_trans", "entrypoint", "relabelto", "relabelfrom"], False)
        for target in ["p4_linux_user_run_t", "p4_linux_tmp_t"]:
            check(actor, obj(target), "dir", ["getattr", "search", "open", "read", "create", "write", "add_name", "remove_name", "setattr", "rmdir"], True)
            check(actor, obj(target), "file", ["getattr", "open", "read", "write", "create", "setattr", "lock", "map", "rename", "unlink"], True)
    for actor in [broker, client]:
        for target in ["p4_linux_user_home_t", "p4_linux_tmp_t"]:
            check(actor, obj(target), "dir", ["getattr", "search", "open", "read", "write", "add_name"], False)
            check(actor, obj(target), "file", ["getattr", "open", "read", "write", "map", "execute"], False)
    check(setup, obj("p4_linux_user_run_t"), "dir", ["getattr", "search", "open", "read", "create", "write", "add_name", "remove_name", "setattr", "rmdir", "mounton"], True)
    check(setup, obj("p4_linux_user_run_t"), "file", ["open", "read", "write", "append", "create", "setattr"], False)
    check(setup, setup, "capability", ["sys_admin"], False)
    check(setup, obj("tmpfs"), "filesystem", ["mount", "remount", "unmount"], False)

    for subject in [helper, client]:
        check(subject, obj("p4_linux_product_store_t"), "file", ["open", "read", "write", "append"], False)
    check(helper, kernel, "security", ["load_policy", "setenforce", "setbool"], False)

    check(client, session, "fifo_file", ["getattr", "write"], True)
    check(client, session, "fifo_file", ["open", "read", "append", "create", "setattr", "map", "execute"], False)

    # Fixed public installer: ordinary inputs stay outside the broker.
    apk = obj("droidloom_public_apk_input")
    payload = obj("droidloom_apk_payload")
    user = session
    check(client, apk, "file", ["getattr", "open", "read"], True)
    check(client, apk, "file", ["write", "append", "create", "setattr", "map", "execute"], False)
    check(user, apk, "file", ["create", "getattr", "open", "read", "write", "setattr", "unlink"], True)
    check(broker, apk, "file", ["getattr", "open", "read", "write", "map", "execute"], False)
    check(broker, client, "fd", ["use"], True)
    check(broker, user, "fd", ["use"], False)
    for kind in ["file", "memfd_file"]:
        check(client, payload, kind, ["create", "getattr", "open", "read", "write", "setattr"], True)
        check(broker, payload, kind, ["getattr", "read"], True)
        check(broker, payload, kind, ["open", "write", "append", "create", "setattr", "map", "execute"], False)
        check(user, payload, kind, ["getattr", "open", "read", "write", "create", "map", "execute"], False)
        check(kernel, payload, kind, ["getattr", "open", "read", "write", "create", "map", "execute"], False)
    check(setup, setup, "capability", ["chown", "fowner"], True)
    check(setup, setup, "capability", ["sys_admin", "sys_ptrace", "dac_override", "dac_read_search"], False)
    # Ordinary user-session home/tmp access is verified by its native component.
    for subject in [broker, client]:
        for private in ["p4_linux_user_home_t", "p4_linux_tmp_t"]:
            check(subject, obj(private), "file", ["getattr", "open", "read", "write", "create"], False)
    check(setup, obj("droidloom_public_apk_root"), "dir", ["getattr", "search", "write", "add_name"], True)
    check(setup, obj("droidloom_public_apk_dir"), "dir", ["getattr", "search", "create", "setattr"], True)
    check(user, obj("droidloom_public_apk_root"), "dir", ["getattr", "search"], True)
    check(user, obj("droidloom_public_apk_root"), "dir", ["write", "add_name", "remove_name", "create", "rmdir"], False)
    check(user, obj("droidloom_public_apk_dir"), "dir", ["search", "open", "read", "write", "add_name", "remove_name"], True)
    check(user, obj("droidloom_public_apk_dir"), "dir", ["create", "rmdir", "relabelto", "relabelfrom"], False)

    # Actual RuntimeDirectory prepare/retire actors, with no file-data access.
    check(executor, executor, "process", ["setfscreate"], True)
    check(manager, manager, "capability", ["dac_override"], False)
    check(executor, executor, "capability", ["chown", "fowner", "setuid", "setgid", "setpcap"], True)
    check(manager, manager, "capability", ["chown", "fowner", "setuid", "setgid", "sys_admin", "sys_ptrace"], False)
    check(executor, executor, "capability", ["dac_override", "dac_read_search", "sys_admin", "sys_ptrace"], False)

    check(manager, obj("p4_linux_user_run_t"), "dir",
          ["getattr", "search", "open", "read", "write", "remove_name", "rmdir"], True)
    for kind, permissions in [
            ("file", ["getattr", "unlink"]), ("lnk_file", ["getattr", "read", "unlink"]),
            ("sock_file", ["getattr", "unlink"]), ("fifo_file", ["getattr", "unlink"])]:
        check(manager, obj("p4_linux_user_run_t"), kind, permissions, True)
    check(manager, obj("p4_linux_session_bus_socket_t"), "sock_file", ["getattr", "unlink"], True)
    for subject in [manager, executor]:
        check(subject, obj("p4_linux_user_run_t"), "file",
              ["open", "read", "write", "create", "setattr", "relabelto", "relabelfrom"], False)
        check(subject, kernel, "security", ["load_policy", "setenforce", "setbool"], False)
        check(subject, subject, "capability2", ["mac_admin", "mac_override"], False)
    check(manager, obj("p4_linux_user_run_t"), "dir", ["create", "add_name", "setattr", "relabelto", "relabelfrom"], False)

    # A fixed immutable utility prepares retirement ACL metadata, without
    # payload reads, unlink authority, DAC override, or MAC-management rights.
    runtime_acl = "u:system_r:p4_linux_runtime_acl_t:s0"
    check(runtime_acl, runtime_acl, "capability", ["fowner"], True)
    check(runtime_acl, executor, "unix_stream_socket", ["getattr", "read", "write"], True)
    check(runtime_acl, executor, "unix_stream_socket", ["create", "bind", "connectto"], False)
    check(runtime_acl, runtime_acl, "capability", ["chown", "dac_override", "dac_read_search", "setuid", "setgid", "sys_admin", "sys_ptrace"], False)
    check(runtime_acl, runtime_acl, "capability2", ["mac_admin", "mac_override"], False)
    for target in ["p4_linux_user_run_t", "droidloom_presenter_runtime"]:
        check(runtime_acl, obj(target), "dir", ["getattr", "search", "open", "read", "setattr"], True)
        check(runtime_acl, obj(target), "dir", ["create", "write", "add_name", "remove_name", "rmdir", "mounton", "relabelto", "relabelfrom"], False)
        for kind in ["file", "fifo_file"]:
            check(runtime_acl, obj(target), kind, ["getattr", "setattr"], True)
            check(runtime_acl, obj(target), kind, ["open", "read", "write", "append", "create", "unlink"], False)
        check(runtime_acl, obj(target), "lnk_file", ["getattr"], True)
        check(runtime_acl, obj(target), "lnk_file", ["read", "setattr", "create", "unlink"], False)
    for target in ["p4_linux_user_run_t", "droidloom_presenter_runtime", "p4_linux_session_bus_socket_t", "p4_linux_wayland_socket_t", "p4_linux_pipewire_socket_t", "p4_linux_pipewire_manager_socket_t"]:
        check(runtime_acl, obj(target), "sock_file", ["getattr", "setattr"], True)
        check(runtime_acl, obj(target), "sock_file", ["write", "create", "unlink", "rename", "relabelto", "relabelfrom"], False)
    for target in ["p4_linux_user_home_t", "p4_linux_tmp_t", "p4_linux_product_store_t", "p4_linux_public_launcher_t"]:
        check(runtime_acl, obj(target), "file", ["getattr", "open", "read", "write", "create", "setattr", "relabelto", "relabelfrom"], False)
    check(runtime_acl, kernel, "security", ["load_policy", "setenforce", "setbool"], False)
    check("u:system_r:p4_linux_user_session_t:s0", runtime_acl, "process", ["transition", "dyntransition"], False)

    # The original native PID 1 alone executes the stock final shutdown ELF.
    check(manager, manager, "capability", ["kill", "sys_boot"], True)
    check(manager, obj("p4_linux_systemd_shutdown_exec_t"), "file",
          ["getattr", "open", "read", "execute", "execute_no_trans", "map"], True)
    for subject in [broker, client, executor, helper,
                    "u:system_r:p4_linux_user_session_t:s0"]:
        check(subject, obj("p4_linux_systemd_shutdown_exec_t"), "file",
              ["execute", "execute_no_trans", "entrypoint"], False)

    # Native transport is bound to fixed peers and socket-activation origin.
    compositor = "u:system_r:p4_linux_compositor_t:s0"
    audio = "u:system_r:p4_linux_audio_t:s0"
    portal = "u:system_r:p4_linux_desktop_portal_t:s0"
    presenter = "u:system_r:droidloom_presenter:s0"
    user_manager = "u:system_r:p4_linux_user_manager_t:s0"
    for subject in [session, portal, presenter, compositor]:
        check(subject, compositor, "unix_stream_socket", ["connectto"], True)
        check(subject, obj("p4_linux_wayland_socket_t"), "sock_file", ["getattr", "write"], True)
        check(subject, compositor, "fd", ["use"], True)
        check(compositor, subject, "fd", ["use"], True)
    for subject in [session, compositor, portal, audio]:
        check(subject, audio, "unix_stream_socket", ["connectto"], True)
        check(subject, user_manager, "unix_stream_socket", ["connectto"], True)
        check(subject, obj("p4_linux_pipewire_socket_t"), "sock_file", ["getattr", "write"], True)
        check(subject, audio, "fd", ["use"], True)
        check(audio, subject, "fd", ["use"], True)
    check(audio, user_manager, "unix_stream_socket", ["getattr", "read", "write", "listen", "accept", "getopt", "setopt"], True)
    check(audio, user_manager, "fd", ["use"], True)
    for subject in [session, portal, presenter]:
        check(subject, obj("p4_linux_pipewire_manager_socket_t"), "sock_file", ["write"], False)
    for subject in [broker, client, helper, "u:r:init:s0", "u:r:untrusted_app:s0"]:
        for target in ["p4_linux_wayland_socket_t", "p4_linux_pipewire_socket_t", "p4_linux_pipewire_manager_socket_t"]:
            check(subject, obj(target), "sock_file", ["create", "getattr", "write", "unlink", "relabelto"], False)
        for kind in ["file", "memfd_file"]:
            check(subject, obj("p4_linux_native_ipc_memfd_t"), kind, ["create", "open", "read", "write", "map", "execute"], False)
    for subject in [session, compositor, portal, audio, presenter]:
        for kind in ["file", "memfd_file"]:
            check(subject, obj("p4_linux_native_ipc_memfd_t"), kind, ["getattr", "read", "write", "map"], True)
            check(subject, obj("p4_linux_native_ipc_memfd_t"), kind, ["execute", "relabelto", "relabelfrom"], False)

    # Real presenter scratch uses its declared native RuntimeDirectory and
    # anonymous NOEXEC SHM, never generic session home/tmp or global proc UUID.
    runtime = obj("droidloom_presenter_runtime")
    user_executor = "u:system_r:p4_linux_user_executor_t:s0"
    check(user_executor, user_executor, "process", ["setfscreate"], True)
    for subject in [presenter, user_executor]:
        check(subject, runtime, "dir", ["getattr", "search", "open", "read", "create", "write", "add_name", "setattr"], True)
    check(presenter, runtime, "file", ["getattr", "create", "open", "read", "write", "unlink"], True)
    for kind in ["file", "memfd_file"]:
        check(presenter, obj("p4_linux_native_ipc_memfd_t"), kind, ["create", "open", "read", "write", "map"], True)
    for subject in [session, portal]:
        check(subject, runtime, "file", ["getattr", "open", "read", "map"], True)
        check(subject, runtime, "file", ["create", "write", "append", "setattr", "unlink"], False)
    for subject in [user_manager, manager, setup]:
        check(subject, runtime, "dir", ["getattr", "search", "open", "read", "write", "remove_name", "rmdir"], True)
        check(subject, runtime, "file", ["getattr", "unlink"], True)
        check(subject, runtime, "file", ["open", "read", "write", "create", "map"], False)
    for subject in [broker, client, helper, "u:r:init:s0", "u:r:untrusted_app:s0"]:
        check(subject, runtime, "dir", ["search", "open", "read", "write", "create"], False)
        check(subject, runtime, "file", ["getattr", "open", "read", "write", "create", "map", "execute"], False)
    for target in ["p4_linux_user_home_t", "p4_linux_tmp_t"]:
        check(presenter, obj(target), "file", ["open", "read", "write", "create", "map", "execute"], False)

    lines = export_binary_policy(policy, binary, export)
    transitions = [
        '(typetransition p4_linux_setup_t droidloom_public_apk_root dir "u1000" droidloom_public_apk_dir)',
        '(typetransition p4_linux_user_session_t droidloom_public_apk_dir file droidloom_public_apk_input)',
        '(typetransition droidloom_public_control_client tmpfs file droidloom_apk_payload)',
        '(typetransition droidloom_public_control_client tmpfs memfd_file droidloom_apk_payload)',
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
        f'(typetransition p4_linux_compositor_t p4_linux_user_run_t sock_file "wayland-{i}" p4_linux_wayland_socket_t)'
        for i in range(33))
    transitions.extend(
        f'(typetransition {actor} p4_linux_user_run_t sock_file "{name}" {label})'
        for actor in ["p4_linux_user_manager_t", "p4_linux_audio_t"]
        for name, label in [("pipewire-0", "p4_linux_pipewire_socket_t"), ("pipewire-0-manager", "p4_linux_pipewire_manager_socket_t")])
    transitions.extend(
        f'(typetransition {actor} p4_linux_user_run_t dir "droidloom-presenter" droidloom_presenter_runtime)'
        for actor in ["p4_linux_user_executor_t", "droidloom_presenter"])
    transitions.extend([
        "(typetransition p4_linux_service_executor_t p4_linux_runtime_acl_exec_t process p4_linux_runtime_acl_t)",
        "(typetransition p4_linux_user_executor_t p4_linux_runtime_acl_exec_t process p4_linux_user_session_t)",
    ])
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


NATIVE_SERVICE_CAPABILITIES = {'p4_linux_sshd_t': ['chown', 'fowner', 'kill', 'setgid', 'setuid', 'net_bind_service', 'sys_chroot', 'audit_write'], 'p4_linux_gdm_t': ['chown', 'fowner', 'setgid', 'setuid'], 'p4_linux_gdm_worker_t': ['kill', 'setgid', 'setuid', 'sys_tty_config', 'audit_write'], 'p4_linux_network_manager_t': ['net_bind_service', 'net_admin', 'net_raw'], 'p4_linux_wpa_t': ['net_admin', 'net_raw'], 'p4_linux_resolved_t': ['net_bind_service', 'net_raw'], 'p4_linux_logind_t': ['chown', 'sys_admin', 'sys_tty_config']}
NATIVE_SERVICE_CAPABILITY_CLASSES = {'capability': ['chown', 'dac_override', 'dac_read_search', 'fowner', 'fsetid', 'kill', 'setgid', 'setuid', 'setpcap', 'linux_immutable', 'net_bind_service', 'net_broadcast', 'net_admin', 'net_raw', 'ipc_lock', 'ipc_owner', 'sys_module', 'sys_rawio', 'sys_chroot', 'sys_ptrace', 'sys_pacct', 'sys_admin', 'sys_boot', 'sys_nice', 'sys_resource', 'sys_time', 'sys_tty_config', 'mknod', 'lease', 'audit_write', 'audit_control', 'setfcap'], 'capability2': ['mac_override', 'mac_admin', 'syslog', 'wake_alarm', 'block_suspend', 'audit_read', 'perfmon', 'bpf', 'checkpoint_restore'], 'cap_userns': ['chown', 'dac_override', 'dac_read_search', 'fowner', 'fsetid', 'kill', 'setgid', 'setuid', 'setpcap', 'linux_immutable', 'net_bind_service', 'net_broadcast', 'net_admin', 'net_raw', 'ipc_lock', 'ipc_owner', 'sys_module', 'sys_rawio', 'sys_chroot', 'sys_ptrace', 'sys_pacct', 'sys_admin', 'sys_boot', 'sys_nice', 'sys_resource', 'sys_time', 'sys_tty_config', 'mknod', 'lease', 'audit_write', 'audit_control', 'setfcap'], 'cap2_userns': ['mac_override', 'mac_admin', 'syslog', 'wake_alarm', 'block_suspend', 'audit_read', 'perfmon', 'bpf', 'checkpoint_restore']}
NATIVE_SERVICE_CAPABILITY_PROTECTED_BASE = {'u:r:droidloom_broker:s0': {'capability': ['setgid', 'setuid'], 'capability2': [], 'cap_userns': ['setgid', 'setuid', 'sys_admin'], 'cap2_userns': []}, 'u:system_r:droidloom_public_control_client:s0': {'capability': [], 'capability2': [], 'cap_userns': [], 'cap2_userns': []}, 'u:system_r:p4_linux_user_session_t:s0': {'capability': [], 'capability2': [], 'cap_userns': [], 'cap2_userns': []}}

def verify_native_service_capabilities(library, binary):
    """Read every capability bit back; no permission follows a unit bounding set."""
    policy = Policy(library, binary)
    cache = {}
    checks = []
    def sid(context):
        if context not in cache:
            value = ctypes.c_uint32()
            raw = context.encode()
            if policy.lib.sepol_context_to_sid(raw, len(raw) + 1, ctypes.byref(value)) != 0:
                raise ValueError("Invalid native capability context: " + context)
            cache[context] = value.value
        return cache[context]
    def actual(subject, target, kind, permissions):
        number, bits = policy.permissions(kind, permissions)
        mask = 0
        for bit in bits.values():
            mask |= bit
        value = Decision()
        if policy.lib.sepol_compute_av(sid(subject), sid(target), number, mask, ctypes.byref(value)) != 0:
            raise ValueError("Cannot read native service capability decisions")
        return {name for name, bit in bits.items() if value.allowed & bit}
    groups = NATIVE_SERVICE_CAPABILITY_CLASSES
    for name, allowed in NATIVE_SERVICE_CAPABILITIES.items():
        context = "u:system_r:" + name + ":s0"
        for kind, permissions in groups.items():
            expected = set(allowed) if kind == "capability" else set()
            observed = actual(context, context, kind, permissions)
            if observed != expected:
                raise ValueError(f"Native service capability boundary differs: {name} {kind}: {sorted(observed)} != {sorted(expected)}")
            checks.extend([name, kind, permission, permission in observed] for permission in permissions)
        denied = actual(context, "u:r:kernel:s0", "security", ["load_policy", "setenforce", "setbool"])
        if denied:
            raise ValueError("Native service gained MAC-management permission: " + name)
        checks.extend([name, "security", permission, False] for permission in ["load_policy", "setenforce", "setbool"])
    # The three protected public roles must retain their actual base84d777d
    # vector exactly; this component cannot lend them a service's capability.
    for context, expected_groups in NATIVE_SERVICE_CAPABILITY_PROTECTED_BASE.items():
        for kind, permissions in groups.items():
            observed = actual(context, context, kind, permissions)
            if observed != set(expected_groups[kind]):
                raise ValueError(f"Native service component changed protected role {context} {kind}")
            checks.extend([context, kind, permission, permission in observed] for permission in permissions)
    return {
        "service_roles": len(NATIVE_SERVICE_CAPABILITIES),
        "capability_bit_decisions": sum(len(x) for x in groups.values()) * (len(NATIVE_SERVICE_CAPABILITIES) + len(NATIVE_SERVICE_CAPABILITY_PROTECTED_BASE)),
        "mac_management_denials": len(NATIVE_SERVICE_CAPABILITIES) * 3,
        "service_capabilities": NATIVE_SERVICE_CAPABILITIES,
        "protected_base_commit": "84d777db3e8dc8e1436e7a1025d39429fea0681b",
        "matrix_sha256": hashlib.sha256(json.dumps(checks, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
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
        "ubuntu-core-cgroup-ownership.cil", "ubuntu-native-services.cil",
        "ubuntu-native-service-capabilities.cil",
        "ubuntu-native-login-audit.cil",
        "frontend-android-interface.cil", "linux-frontend-observer.cil", "instance-launcher.cil",
        "linux-query-owner.cil", "linux-fixed-metadata-observer.cil",
        "instance-factory-cgroup.cil", "ubuntu-systemd-unit-status.cil",
        "linux-application-roles.cil", "linux-install-catalog.cil",
        "ubuntu-dbus.cil", "ubuntu-native-selinux-query.cil",
        "ubuntu-native-pam.cil", "ubuntu-native-session-storage.cil", "ubuntu-native-session-ipc.cil",
        "ubuntu-native-runtime-retirement.cil",

        "ubuntu-native-manager-lifecycle.cil",
        "ubuntu-presenter-runtime.cil",
        "linux-package-maintenance.cil", "linux-public-control.cil",
    )
    components = [here / name for name in component_names]
    sources = [compiler, library, args.linux_board_cil, *args.android_cil, *components,
               here / "cp3a-kernel-handle-inputs.json", Path(__file__),
               here / "derive_shared_payload_cgroup_policy.py",
               here / "verify_native_login_audit.py"]
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
        native_capabilities = verify_native_service_capabilities(library, linked)
        login_audit = verify_login_audit(library, linked, work / "login-audit-binary.cil", export_binary_policy)
        result = {
            "native_service_capabilities": native_capabilities,
            "native_login_audit": login_audit,
            "native_login_audit_verifier": sha256(here / "verify_native_login_audit.py"),
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
