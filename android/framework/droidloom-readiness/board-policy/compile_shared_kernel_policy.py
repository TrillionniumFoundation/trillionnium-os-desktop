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
from verify_native_journal_storage import verify_journal_storage
from verify_greeter_home import verify_greeter_home
from verify_native_maintenance import verify_native_maintenance
from verify_native_camera import verify_camera


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



def verify_manager_tmpfs(lines, check, obj, role_types):
    """Measure the complete fresh-filesystem label and temporary-inode boundary."""
    count = 0
    def test(source, target, cls, permissions, allowed):
        nonlocal count
        check(source, target, cls, permissions, allowed)
        count += len(permissions)
    fs = obj("p4_linux_generator_tmpfs_t")
    inode = obj("p4_linux_generator_tmp_t")
    for role, actor in role_types:
        context = f"u:{role}:{actor}:s0"
        manager = role == "system_r" and actor == "init_t"
        generator = role == "system_r" and actor == "p4_linux_generator_t"
        for permission in ("mount", "relabelfrom", "relabelto"):
            test(context, fs, "filesystem", [permission], manager)
        test(context, fs, "filesystem", ["remount", "unmount"], False)
        test(context, inode, "dir", ["open", "read"], manager or generator)
        test(context, inode, "dir",
             ["create", "write", "add_name", "remove_name", "setattr", "rename", "reparent", "rmdir"], generator)
        test(context, inode, "dir", ["mounton", "relabelto", "relabelfrom"], False)
        test(context, inode, "file",
             ["open", "read", "create", "write", "append", "setattr", "rename", "unlink"], generator)
        test(context, inode, "file",
             ["execute", "execute_no_trans", "entrypoint", "map", "mounton", "relabelto", "relabelfrom"], False)
        test(context, inode, "lnk_file",
             ["read", "create", "write", "setattr", "rename", "unlink"], generator)
        test(context, inode, "lnk_file", ["mounton", "relabelto", "relabelfrom"], False)
        for cls in ("chr_file", "blk_file", "sock_file", "fifo_file"):
            test(context, inode, cls, ["create", "open", "read", "write"], False)
    object_types = sorted(line[len("(roletype object_r "):-1] for line in lines
                          if line.startswith("(roletype object_r "))
    for name in object_types:
        if not name or any(c.isspace() or c in "()" for c in name):
            raise ValueError("Unexpected concrete object role in tmpfs verifier")
        target = obj(name)
        test("u:system_r:init_t:s0", target, "filesystem", ["relabelfrom"],
             name in ("tmpfs", "p4_linux_generator_tmpfs_t"))
        test("u:system_r:init_t:s0", target, "filesystem", ["relabelto"],
             name == "p4_linux_generator_tmpfs_t")
        test(target, fs, "filesystem", ["associate"], name == "p4_linux_generator_tmp_t")
    test("u:system_r:init_t:s0", obj("tmpfs"), "filesystem", ["mount", "relabelto"], False)
    test("u:system_r:init_t:s0", obj("p4_linux_tmp_t"), "dir", ["mounton"], True)
    test("u:system_r:p4_linux_generator_t:s0", obj("tmpfs"), "filesystem",
         ["mount", "relabelto", "relabelfrom"], False)
    for actor in ("init_t", "p4_linux_generator_t"):
        test(f"u:system_r:{actor}:s0", fs, "filesystem", ["getattr"], True)
    return {"process_role_types": len(role_types), "concrete_object_types": len(object_types),
            "permission_checks": count, "capabilities_added": [],
            "generic_tmpfs_mount_and_relabel_to_denied": True,
            "original_android_inodes_relabelled": False, "runtime_qualified": False}


def verify_manager_startup(lines, check, obj, role_types):
    """Read generator/status authority from the linked policy for every role."""
    count = 0
    for role, actor in role_types:
        context = f"u:{role}:{actor}:s0"
        owner = actor in ("init_t", "p4_linux_generator_t")
        for permission in ("create", "write", "add_name", "remove_name", "setattr", "rename", "reparent", "rmdir"):
            check(context, obj("p4_linux_generator_run_t"), "dir", [permission], owner)
            count += 1
        for cls in ("file", "lnk_file"):
            for permission in ("create", "write", "setattr", "rename"):
                check(context, obj("p4_linux_generated_unit_t"), cls, [permission],
                      actor == "p4_linux_generator_t")
                count += 1
            check(context, obj("p4_linux_generated_unit_t"), cls, ["unlink"], owner)
            count += 1
        for permission in ("execute", "execute_no_trans", "entrypoint", "relabelto", "relabelfrom", "mounton"):
            check(context, obj("p4_linux_generated_unit_t"), "file", [permission], False)
            count += 1
        for permission in ("create", "write", "setattr", "unlink"):
            check(context, obj("p4_linux_manager_status_t"), "file", [permission], actor == "init_t")
            count += 1
        for permission in ("execute", "execute_no_trans", "entrypoint", "map", "relabelto", "relabelfrom", "mounton"):
            check(context, obj("p4_linux_manager_status_t"), "file", [permission], False)
            count += 1
        for permission in ("write", "create", "add_name", "remove_name", "setattr", "rmdir"):
            check(context, obj("p4_linux_generator_directory_t"), "dir", [permission], False)
            count += 1
    for actor in ("init_t", "p4_linux_generator_t"):
        check(f"u:system_r:{actor}:s0", obj("p4_linux_generator_directory_t"),
              "dir", ["getattr", "search", "open", "read"], True)
        check(f"u:system_r:{actor}:s0", obj("p4_linux_rootdir_t"),
              "dir", ["create", "write", "add_name"], False)
    check("u:system_r:init_t:s0", obj("p4_linux_systemd_run_t"), "file", ["create", "write"], False)
    check("u:system_r:init_t:s0", obj("p4_linux_generated_unit_t"), "file",
          ["getattr", "open", "read", "map"], True)
    check("u:system_r:p4_linux_generator_t:s0", obj("p4_linux_systemd_memfd_t"),
          "file", ["getattr", "read", "write"], True)
    check("u:system_r:p4_linux_generator_t:s0", obj("p4_linux_systemd_memfd_t"),
          "file", ["open", "create", "map", "execute", "entrypoint"], False)
    required = [
        f'(typetransition init_t p4_linux_systemd_run_t dir "{leaf}" p4_linux_generator_run_t)'
        for leaf in ("generator", "generator.early", "generator.late")
    ]
    required += [
        f'(typetransition {actor} p4_linux_generator_run_t dir p4_linux_generator_run_t)'
        for actor in ("init_t", "p4_linux_generator_t")
    ]
    required += [
        f'(typetransition p4_linux_generator_t p4_linux_generator_run_t {cls} p4_linux_generated_unit_t)'
        for cls in ("file", "lnk_file")
    ]
    required += [
        f'(typetransition init_t p4_linux_systemd_run_t file "{leaf}" p4_linux_manager_status_t)'
        for leaf in ("show-status", "systemd-units-load")
    ]
    missing = [line for line in required if line not in lines]
    if missing:
        raise ValueError("Linked policy lacks stock manager creation transitions: " + repr(missing))
    return {"process_role_types": len(role_types), "role_permission_checks": count,
            "fixed_and_nested_transitions": len(required), "capabilities_added": [],
            "generic_root_and_systemd_regular_file_writes_denied": True,
            "native_generator_tmpfs": verify_manager_tmpfs(lines, check, obj, role_types),
            "runtime_qualified": False}


def verify_manager_file_contexts(here, work):
    """Use libselinux's real class-aware matcher in the normal producer order."""
    import stat
    names = ("ubuntu-native-file_contexts", "ubuntu-real-root-file_contexts",
             "linux-service-file_contexts", "linux-initial-calibration-file_contexts")
    source = b"".join((here / name).read_bytes() for name in names)
    path = work / "manager-file-contexts"
    path.write_bytes(source)
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
        raise OSError(ctypes.get_errno(), "Cannot open actual manager file-context matcher")
    cases = []
    for root in ("generator", "generator.early", "generator.late"):
        prefix = "/run/systemd/" + root
        cases.extend([
            (prefix, stat.S_IFDIR, "p4_linux_generator_run_t"),
            (prefix + "/multi-user.target.wants", stat.S_IFDIR, "p4_linux_generator_run_t"),
            (prefix + "/example.service", stat.S_IFREG, "p4_linux_generated_unit_t"),
            (prefix + "/multi-user.target.wants/example.service", stat.S_IFLNK, "p4_linux_generated_unit_t"),
        ])
    cases.extend([
        ("/run/systemd/generatorx", stat.S_IFDIR, "p4_linux_rootdir_t"),
        ("/run/systemd/generator.early-extra", stat.S_IFDIR, "p4_linux_rootdir_t"),
        ("/run/systemd/generatorx/example.service", stat.S_IFREG, "p4_linux_native_data_t"),
        ("/run/systemd/system", stat.S_IFDIR, "p4_linux_systemd_run_t"),
        ("/run/systemd/show-status", stat.S_IFREG, "p4_linux_manager_status_t"),
        ("/run/systemd/systemd-units-load", stat.S_IFREG, "p4_linux_manager_status_t"),
        ("/run/systemd/show-status-extra", stat.S_IFREG, "p4_linux_native_data_t"),
        ("/run/systemd/journal", stat.S_IFDIR, "p4_linux_journal_runtime_t"),
        ("/run/systemd/namespace-example", stat.S_IFDIR, "p4_linux_sandbox_dir_t"),
        ("/run/systemd/inaccessible", stat.S_IFDIR, "p4_linux_inaccessible_t"),
        ("/usr/lib/systemd/system-generators", stat.S_IFDIR, "p4_linux_generator_directory_t"),
        ("/usr/lib/systemd/system-environment-generators", stat.S_IFDIR, "p4_linux_generator_directory_t"),
        ("/usr/lib/systemd/system-environment-generators/snapd-env-generator", stat.S_IFREG, "p4_linux_generator_exec_t"),
        ("/usr/lib/systemd/system-environment-generators/unselected-generator", stat.S_IFREG, "p4_linux_runtime_lib_t"),
        ("/usr/libexec/netplan/generate", stat.S_IFREG, "p4_linux_generator_exec_t"),
        ("/usr/libexec/netplan/unselected-helper", stat.S_IFREG, "p4_linux_native_bin_t"),
    ])
    # Normal debootstrap character nodes survive complete-root capture. Keep the
    # original class-specific labels without assigning device types to other kinds.
    for name, device_type in [
        ("console", "console_device"), ("full", "p4_linux_standardio_t"),
        ("null", "null_device"), ("ptmx", "ptmx_device"),
        ("random", "random_device"), ("tty", "owntty_device"),
        ("urandom", "random_device"), ("zero", "zero_device"),
    ]:
        cases.extend([
            ("/dev/" + name, stat.S_IFCHR, device_type),
            ("/dev/" + name, stat.S_IFREG, "p4_linux_native_data_t"),
            ("/dev/" + name, stat.S_IFDIR, "p4_linux_rootdir_t"),
            ("/dev/" + name, stat.S_IFLNK, "p4_linux_usrmerge_link_t"),
        ])
    actual = []
    try:
        for filename, mode, expected_type in cases:
            value = ctypes.c_char_p()
            if lib.selabel_lookup_raw(handle, ctypes.byref(value), filename.encode(), mode) != 0:
                raise OSError(ctypes.get_errno(), "Actual manager file-context lookup failed: " + filename)
            try:
                context = value.value.decode()
            finally:
                lib.freecon(value)
            expected = "u:object_r:" + expected_type + ":s0"
            if context != expected:
                raise ValueError(f"Wrong stock manager creation label for {filename}: {context} != {expected}")
            actual.append([filename, mode, context])
    finally:
        lib.selabel_close(handle)
    return {"actual_selabel_lookup_raw_checks": len(actual),
            "normal_input_order": list(names),
            "source_sha256": {name: sha256(here / name) for name in names},
            "joined_sha256": hashlib.sha256(source).hexdigest(),
            "case_matrix_sha256": hashlib.sha256(json.dumps(actual, separators=(",", ":")).encode()).hexdigest()}


def verify_native_hardware(policy, lines, check, obj):
    """Read the complete linked hardware boundary, including every ioctl bit."""
    from functools import lru_cache
    from derive_shared_payload_cgroup_policy import parse_expression
    forms = [parse_expression(line) for line in lines
             if line.startswith(("(type ", "(typeattributeset ", "(allowx ", "(roletype "))]
    types = {form[1] for form in forms if form[0] == "type"}
    definitions = {}
    for form in forms:
        if form[0] == "typeattributeset":
            definitions.setdefault(form[1], []).append(form[2])
    @lru_cache(None)
    def named(name):
        if name in types:
            return {name}
        if name not in definitions:
            raise ValueError("Unknown hardware binary attribute " + name)
        return set().union(*(members(x) for x in definitions[name]))
    def members(expr):
        if isinstance(expr, str):
            return named(expr)
        if expr and expr[0] == "all":
            return types
        if expr and expr[0] == "not":
            return types - members(expr[1])
        if expr and expr[0] == "and":
            return set.intersection(*(members(x) for x in expr[1:]))
        return set().union(*(members(x) for x in (expr[1:] if expr and expr[0] == "or" else expr)))
    def values(expr):
        if isinstance(expr, str):
            value = int(expr, 0)
            if not 0 <= value <= 65535:
                raise ValueError("Hardware ioctl exceeds u16")
            return {value}
        if expr and expr[0] == "range":
            lo, hi = (int(v, 0) for v in expr[1:])
            if not 0 <= lo <= hi <= 65535:
                raise ValueError("Invalid hardware ioctl range")
            return set(range(lo, hi + 1))
        if expr and expr[0] == "not":
            return set(range(65536)) - values(expr[1])
        return set().union(*(values(x) for x in expr))

    native = lambda name: "u:system_r:" + name + ":s0"
    labeler = native("p4_linux_hardware_label_t")
    dirs = {"p4_linux_drm_dir_t", "p4_linux_input_dir_t", "p4_linux_native_dev_root_t"}
    nodes = {"p4_linux_drm_card_t", "p4_linux_drm_render_t", "p4_linux_input_event_t", "p4_linux_uvc_device_t"}
    for target in sorted(types):
        check(labeler, obj(target), "dir", ["relabelto"], target in dirs)
        check(labeler, obj(target), "chr_file", ["relabelto"], target in nodes)
        check(labeler, obj(target), "file", ["relabelto", "relabelfrom", "write", "create", "execute_no_trans"], False)
    caps = "chown dac_override dac_read_search fowner fsetid kill setgid setuid setpcap linux_immutable net_bind_service net_broadcast net_admin net_raw ipc_lock ipc_owner sys_module sys_rawio sys_chroot sys_ptrace sys_pacct sys_admin sys_boot sys_nice sys_resource sys_time sys_tty_config mknod lease audit_write audit_control setfcap".split()
    for kind in ["capability", "cap_userns"]:
        check(labeler, labeler, kind, caps, False)
    check(labeler, labeler, "capability2", "mac_override mac_admin syslog wake_alarm block_suspend audit_read perfmon bpf checkpoint_restore".split(), False)
    check(native("p4_linux_udev_t"), labeler, "process", ["transition"], True)
    for actor in ["p4_linux_user_session_t", "droidloom_public_control_client", "p4_linux_compositor_t", "p4_linux_service_executor_t"]:
        check(native(actor), labeler, "process", ["transition", "dyntransition", "ptrace"], False)
    check(labeler, obj("device"), "chr_file", ["open", "read", "write", "ioctl", "map"], False)

    render = {0x6400, 0x6409, 0x640c, 0x642d, 0x642e, 0x64cf, 0x64d1}
    for lo, hi in [(0x6440,0x644b),(0x6450,0x6454),(0x6456,0x6459),(0x64bf,0x64c5),(0x64ca,0x64cd)]:
        render.update(range(lo,hi+1))
    card = {0x6400,0x6409,0x640c,0x640d,0x6411,0x641f,0x642d,0x642e,0x643a,0x643b,0x643c}
    for lo, hi in [(0x6440,0x644b),(0x6450,0x6454),(0x6456,0x6459),(0x64a0,0x64a7),(0x64aa,0x64d1)]:
        card.update(range(lo,hi+1))
    input_read = {0x4501,0x4502,0x4503,0x4506,0x4507,0x4508,0x4509,0x450a,0x4518,0x4519,0x451b,0x45a0} | set(range(0x4520,0x4580))
    input_udev = {0x4501,0x4502,0x4504,0x4506,0x4507,0x4508,0x4509} | set(range(0x4520,0x4580)) | set(range(0x45c0,0x4600))
    ioctl_sets = [(actor, "p4_linux_drm_render_t", "chr_file", render)
                  for actor in ["p4_linux_compositor_t", "p4_linux_user_session_t", "droidloom_presenter"]]
    ioctl_sets.extend([
        ("p4_linux_compositor_t", "p4_linux_drm_card_t", "chr_file", card),
        ("p4_linux_logind_t", "p4_linux_drm_card_t", "chr_file", {0x641e,0x641f}),
        ("p4_linux_logind_t", "p4_linux_input_event_t", "chr_file", {0x4506,0x4518,0x451b,0x4520,0x4521,0x4525,0x4591,0x4593}),
        ("p4_linux_compositor_t", "p4_linux_input_event_t", "chr_file", input_read),
        ("p4_linux_udev_t", "p4_linux_input_event_t", "chr_file", input_udev),
        ("p4_linux_hardware_label_t", "p4_kernel_ns_handle_t", "file", {0xb703}),
        ("droidloom_camera_capture", "p4_kernel_ns_handle_t", "file", {0xb703}),
        ("p4_linux_udev_t", "p4_linux_uvc_device_t", "chr_file", {0x5600}),
        ("droidloom_camera_capture", "p4_linux_uvc_device_t", "chr_file", {0x5600, 0x5602, 0x564a, 0x564b, 0x5605, 0x5616, 0x5608, 0x5609, 0x560f, 0x5611, 0x5612, 0x5613}),
    ])
    actual_sets = []
    for actor, target, kind, wanted in ioctl_sets:
        actual = set()
        for form in forms:
            if form[0] != "allowx":
                continue
            source, destination, permission = form[1:]
            if permission[:2] == ["ioctl", kind] and actor in members(source) and destination != "self" and target in members(destination):
                actual |= values(permission[2])
        if actual != wanted:
            raise ValueError(f"Linked hardware ioctl boundary differs for {actor}/{target}: added={sorted(actual-wanted)}, missing={sorted(wanted-actual)}")
        actual_sets.append([actor, target, sorted(actual)])

    body = {"open", "read", "write", "append", "ioctl", "map"}
    role_types = sorted({(form[1], form[2]) for form in forms
                         if form[0] == "roletype" and form[1] in {"r", "system_r"}})
    for role, actor in role_types:
        context = f"u:{role}:{actor}:s0"
        own = actor == "p4_linux_hardware_label_t"
        check(labeler, context, "dir", ["getattr", "search"], own)
        check(labeler, context, "dir", ["open", "read"], False)
        check(labeler, context, "lnk_file", ["getattr", "read"], own)
        check(labeler, context, "file", ["open", "read"], False)
    check(labeler, obj("proc"), "dir", ["getattr", "search"], True)
    check(labeler, obj("proc"), "dir", ["open", "read"], False)
    check(labeler, obj("proc"), "lnk_file", ["getattr", "read"], True)
    check(labeler, obj("proc"), "file", ["open", "read", "write"], False)
    decisions = 0
    for role, actor in role_types:
        context = f"u:{role}:{actor}:s0"
        for target in sorted(nodes):
            wanted = set()
            if actor in {"p4_linux_compositor_t", "p4_linux_user_session_t", "droidloom_presenter"} and target == "p4_linux_drm_render_t":
                wanted = {"open", "read", "write", "ioctl", "map"}
            elif actor == "p4_linux_compositor_t" and target in {"p4_linux_drm_card_t", "p4_linux_input_event_t"}:
                wanted = {"read", "write", "ioctl"} | ({"map"} if target == "p4_linux_drm_card_t" else set())
            elif actor == "p4_linux_logind_t" and target in {"p4_linux_drm_card_t", "p4_linux_input_event_t"}:
                wanted = {"open", "read", "write", "ioctl"}
            elif actor == "p4_linux_dbus_t" and target in {"p4_linux_drm_card_t", "p4_linux_input_event_t"}:
                wanted = {"read", "write"}
            elif actor == "p4_linux_udev_t" and target == "p4_linux_input_event_t":
                wanted = {"open", "read", "write", "ioctl"}
            elif actor == "p4_linux_udev_t" and target == "p4_linux_uvc_device_t":
                wanted = {"open", "read", "ioctl"}
            elif actor == "droidloom_camera_capture" and target == "p4_linux_uvc_device_t":
                wanted = {"open", "read", "write", "ioctl", "map"}
            if wanted:
                check(context, obj(target), "chr_file", sorted(wanted), True)
            check(context, obj(target), "chr_file", sorted(body - wanted), False)
            decisions += len(body)
    return {"concrete_types": len(types), "self_fd_metadata_decisions": len(role_types)*8+9, "relabel_scope_decisions": len(types)*7,
            "hardware_body_decisions": decisions, "original_and_native_role_types": len(role_types),
            "ioctl_u16_decisions": 65536*len(ioctl_sets),
            "ioctl_sets_sha256": hashlib.sha256(json.dumps(actual_sets, separators=(",", ":")).encode()).hexdigest()}


def verify_host_control(library, binary, export, original_contract):
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
    check(manager, manager, "capability", ["chown", "fowner", "setuid", "setgid", "sys_ptrace"], False)
    check(executor, executor, "capability", ["dac_override", "dac_read_search", "sys_ptrace"], False)

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

    # Native namespace authority is paired with the actual bounded filesystems.
    journal = "u:system_r:p4_linux_journald_t:s0"
    udev = "u:system_r:p4_linux_udev_t:s0"
    module_loader = "u:system_r:p4_linux_module_loader_t:s0"
    check(executor, executor, "capability", ["sys_admin", "sys_chroot"], True)
    check(manager, manager, "capability", ["sys_admin"], True)
    check(executor, executor, "capability", ["mknod"], False)
    for fs in ["labeledfs", "tmpfs", "device", "proc", "sysfs", "cgroup_v2",
               "devpts", "mqueue", "selinuxfs", "securityfs", "debugfs",
               "debugfs_tracing_debug", "fusectlfs", "fs_bpf", "pstorefs",
               "binfmt_miscfs", "rootfs"]:
        check(executor, obj(fs), "filesystem", ["getattr", "remount", "unmount"], True)
        check(executor, obj(fs), "filesystem", ["relabelto", "relabelfrom"], False)
    check(executor, obj("tmpfs"), "filesystem", ["mount"], True)
    check(executor, obj("selinuxfs"), "filesystem", ["mount"], False)
    for fs in ["labeledfs", "tmpfs"]:
        check(manager, obj(fs), "filesystem", ["getattr", "remount", "unmount"], True)
    check(manager, obj("selinuxfs"), "filesystem", ["mount", "remount", "unmount"], False)
    check(executor, obj("p4_linux_cgroup_root_t"), "dir", ["mounton"], True)
    check(executor, obj("p4_linux_cgroup_init_scope_t"), "dir", ["mounton", "relabelto", "relabelfrom"], False)
    check(executor, obj("p4_linux_cgroup_init_tasks_t"), "file", ["open", "write", "relabelto", "relabelfrom"], False)
    check(executor, obj("tmpfs"), "dir", ["relabelfrom"], True)
    check(executor, obj("tmpfs"), "dir", ["open", "read", "write", "add_name", "remove_name", "relabelto"], False)
    for private in ["droidloom_public_apk_input", "p4_linux_product_store_t"]:
        check(executor, obj(private), "file", ["open", "read", "write", "create", "relabelto"], False)
    for actor in [session, udev, setup]:
        check(actor, actor, "capability", ["sys_admin"], False)
        check(actor, obj("tmpfs"), "filesystem", ["mount", "remount", "unmount"], False)
    # The new socket label is computed by stock PID 1, not permission to bypass
    # the executor or to connect to arbitrary manager sockets.
    check(manager, manager, "process", ["setsockcreate", "setfscreate"], True)
    check(manager, kernel, "security", ["compute_create"], True)
    check(manager, journal, "process", ["transition", "dyntransition"], False)
    check(executor, journal, "unix_stream_socket", ["connectto"], True)
    check(executor, manager, "unix_stream_socket", ["connectto", "accept"], False)
    check(journal, journal, "capability2", ["syslog"], True)
    check(journal, kernel, "system", ["syslog_read"], True)
    check(journal, kernel, "system", ["syslog_mod", "syslog_console"], False)
    check(journal, journal, "capability", ["sys_ptrace", "audit_control"], False)
    check(journal, obj("kmsg_device"), "chr_file", ["getattr", "open", "read", "write"], True)
    for actor in [module_loader, udev]:
        check(actor, actor, "capability", ["sys_module"], True)
        check(actor, actor, "system", ["module_load"], False)
        check(actor, obj("p4_linux_kernel_modules_t"), "system", ["module_load"], False)
        check(actor, obj("sysfs"), "file", ["getattr", "open", "read"], True)
        check(actor, obj("sysfs"), "file", ["write", "append", "map", "execute", "setattr"], False)
        check(actor, executor, "unix_stream_socket", ["getattr", "read", "write"], True)
        check(actor, executor, "unix_stream_socket", ["create", "connectto", "bind", "listen", "accept"], False)
    check(kernel, module_loader, "process", ["transition"], True)
    check(udev, obj("binder_device"), "chr_file", ["read", "write", "open", "setattr"], False)

    # Global native /dev directory semantics apply both before and after normal
    # path labeling. This adds only two directory metadata bits, never device I/O.
    native_device_readers = [
        "p4_linux_setup_t", "p4_linux_generator_t", "p4_linux_dbus_t",
        "p4_linux_network_manager_t", "p4_linux_wpa_t", "p4_linux_resolved_t",
        "p4_linux_logind_t", "p4_linux_accounts_t", "p4_linux_polkit_t",
        "p4_linux_rtkit_t", "p4_linux_bluetooth_t", "p4_linux_gdm_t",
        "p4_linux_gdm_worker_t", "p4_linux_sshd_t", "p4_linux_snapd_t",
        "p4_linux_apparmor_updater_t", "p4_linux_module_loader_t",
        "p4_linux_sysctl_t", "p4_linux_user_session_t", "p4_linux_compositor_t",
        "p4_linux_audio_t", "p4_linux_desktop_portal_t", "p4_linux_user_manager_t",
        "p4_linux_user_executor_t", "p4_linux_user_dbus_t", "droidloom_presenter",
        "p4_linux_udev_t", "p4_linux_journald_t",
    ]
    for name in native_device_readers:
        actor = f"u:system_r:{name}:s0"
        for directory_type in ["device", "p4_linux_native_dev_root_t"]:
            check(actor, obj(directory_type), "dir", ["getattr", "search"], True)
            check(actor, obj(directory_type), "dir",
                  ["open", "read", "create", "write", "add_name", "remove_name", "mounton"], False)
    for actor in [manager, broker]:
        check(actor, obj("p4_linux_native_dev_root_t"), "dir", ["getattr", "search"], True)
    check(kernel, obj("p4_linux_native_dev_root_t"), "dir", ["getattr", "open", "read", "search"], True)
    check("u:system_r:p4_linux_early_t:s0", obj("p4_linux_native_dev_root_t"), "dir", ["search"], True)
    for actor in [session, compositor, presenter, udev]:
        check(actor, obj("device"), "chr_file", ["open", "read", "write", "ioctl", "map"], False)
        check(actor, obj("p4_linux_native_dev_root_t"), "dir", ["relabelfrom", "relabelto"], False)
    # All selected socket units compute the exact native service SID. Actual
    # service execution remains exclusively through the original executor.
    activated = ["p4_linux_journald_t", "p4_linux_udev_t", "p4_linux_dbus_t",
                 "p4_linux_snapd_t", "p4_linux_resolved_t", "p4_linux_logind_t"]
    for name in activated:
        actor = f"u:system_r:{name}:s0"
        check(manager, actor, "process", ["transition", "dyntransition"], False)
        check(manager, actor, "unix_stream_socket",
              ["create", "getattr", "bind", "listen", "read", "write", "getopt", "setopt"], True)
        check(executor, actor, "unix_stream_socket", ["getattr", "read", "write"], True)
        if name != "p4_linux_journald_t":
            check(executor, actor, "unix_stream_socket", ["connectto", "accept"], False)
    sshd = "u:system_r:p4_linux_sshd_t:s0"
    check(manager, sshd, "process", ["transition", "dyntransition"], False)
    check(manager, manager, "capability", ["net_bind_service"], True)
    check(manager, sshd, "tcp_socket", ["create", "bind", "listen", "getattr", "read", "write", "getopt", "setopt"], True)
    check(manager, obj("port"), "tcp_socket", ["name_bind"], True)
    check(manager, obj("node"), "tcp_socket", ["node_bind"], True)
    check(executor, sshd, "tcp_socket", ["getattr", "read", "write"], True)
    check(executor, sshd, "tcp_socket", ["create", "bind", "listen", "accept", "connect", "name_connect"], False)
    for actor in [manager, journal]:
        check(actor, actor, "capability2", ["audit_read"], True)
    for actor in [manager, executor, journal]:
        check(actor, journal, "netlink_audit_socket", ["getattr", "read", "write"], True)
        check(actor, journal, "netlink_audit_socket",
              ["nlmsg", "nlmsg_read", "nlmsg_write", "nlmsg_relay", "nlmsg_readpriv", "nlmsg_tty_audit", "sendto", "connect"], False)
    check(journal, journal, "capability", ["audit_control", "audit_write"], False)
    check(manager, udev, "netlink_kobject_uevent_socket", ["create", "bind", "getattr", "read", "write", "getopt", "setopt"], True)
    for actor in [executor, udev]:
        check(actor, udev, "netlink_kobject_uevent_socket", ["getattr", "read", "write"], True)
    check(executor, udev, "netlink_kobject_uevent_socket", ["create", "bind", "sendto"], False)

    lines = export_binary_policy(policy, binary, export)
    # Read every original Android and every native process-role type back from
    # the binary. This explicitly accounts for the public module classification:
    # only original init's existing system_dlkm read set and the two native
    # file-backed loaders may access these new immutable public leaves.
    module_context = obj("p4_shared_kernel_module_t")
    role_types = []
    for line in sorted(lines):
        for role in ["r", "system_r"]:
            prefix = f"(roletype {role} "
            if line.startswith(prefix):
                name = line[len(prefix):-1]
                if not name or any(char.isspace() for char in name) or "(" in name:
                    raise ValueError("Unexpected binary process-role declaration: " + line)
                role_types.append((role, name))
    if not set(original_contract["subjects"]).issubset({name for role, name in role_types if role == "r"}):
        raise ValueError("Original Android subjects are absent from native module review")
    file_permissions = original_contract["classes"]["file"]
    for role, name in role_types:
        context = f"u:{role}:{name}:s0"
        if role == "r" and name == "init":
            allowed = ["ioctl", "read", "getattr", "lock", "map", "open", "watch", "watch_reads"]
        elif role == "system_r" and name in ["p4_linux_module_loader_t", "p4_linux_udev_t"]:
            allowed = ["read", "getattr", "map", "open"]
        else:
            allowed = []
        if allowed:
            check(context, module_context, "file", allowed, True)
        check(context, module_context, "file", [p for p in file_permissions if p not in allowed], False)
        check(context, module_context, "system", ["module_load"],
              role == "system_r" and name in ["p4_linux_module_loader_t", "p4_linux_udev_t"])
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
    transitions.extend([
        "(typetransition init_t p4_linux_journald_exec_t process p4_linux_journald_t)",
        "(typetransition kernel p4_linux_module_loader_exec_t process p4_linux_module_loader_t)",
        "(roletransition r p4_linux_module_loader_exec_t process system_r)",
        '(typetransition init_t p4_linux_systemd_run_t dir "mount-rootfs" p4_linux_sandbox_dir_t)',
        '(typetransition init_t p4_linux_systemd_run_t dir "inaccessible" p4_linux_inaccessible_t)',
    ])
    transitions.extend(
        f"(typetransition init_t {executable} process {actor})"
        for executable, actor in [
            ("p4_linux_udev_exec_t", "p4_linux_udev_t"),
            ("p4_linux_dbus_exec_t", "p4_linux_dbus_t"),
            ("p4_linux_sshd_exec_t", "p4_linux_sshd_t"),
            ("p4_linux_snapd_exec_t", "p4_linux_snapd_t"),
            ("p4_linux_resolved_exec_t", "p4_linux_resolved_t"),
            ("p4_linux_logind_exec_t", "p4_linux_logind_t"),
        ])
    transitions.extend([
        '(typetransition init_t p4_linux_run_t sock_file "snapd.socket" p4_linux_snapd_run_t)',
        '(typetransition init_t p4_linux_run_t sock_file "snapd-snap.socket" p4_linux_snapd_run_t)',
        '(typetransition init_t p4_linux_systemd_run_t sock_file "io.systemd.Login" p4_linux_logind_run_t)',
        '(typetransition init_t p4_linux_resolved_run_t sock_file "io.systemd.Resolve" p4_linux_resolved_run_t)',
        '(typetransition init_t p4_linux_resolved_run_t sock_file "io.systemd.Resolve.Monitor" p4_linux_resolved_run_t)',
    ])
    transitions.append("(typetransition p4_linux_udev_t droidloom_container_entry_exec_t process p4_linux_hardware_label_t)")
    hardware = verify_native_hardware(policy, lines, check, obj)
    manager_startup = verify_manager_startup(lines, check, obj, role_types)
    camera = verify_camera(policy, lines, check, obj, Path(__file__).resolve().parent)
    # The exact timezone symlink retains the prior read-only public-link
    # contract, while only PID 1 may place its stock IN_DONT_FOLLOW watch.
    timezone_decisions = 0
    for role, actor in role_types:
        context = f"u:{role}:{actor}:s0"
        for permission in ["getattr", "read"]:
            number, bits = policy.permissions("lnk_file", [permission])
            old = Decision()
            bit = bits[permission]
            if policy.lib.sepol_compute_av(sid(context), sid(obj("p4_linux_usrmerge_link_t")),
                                           number, bit, ctypes.byref(old)) != 0:
                raise ValueError("Cannot read original public-symlink access")
            check(context, obj("p4_linux_timezone_link_t"), "lnk_file", [permission], bool(old.allowed & bit))
        check(context, obj("p4_linux_timezone_link_t"), "lnk_file", ["watch"], actor == "init_t")
        check(context, obj("p4_linux_timezone_link_t"), "lnk_file",
              ["write", "create", "unlink", "rename", "setattr", "relabelto", "relabelfrom"], False)
        timezone_decisions += 10
    check("u:system_r:init_t:s0", obj("p4_linux_usrmerge_link_t"), "lnk_file", ["watch"], False)
    check("u:system_r:init_t:s0", obj("p4_linux_rootdir_t"), "dir", ["create", "write", "add_name"], False)
    check("u:system_r:init_t:s0", obj("p4_linux_systemd_run_t"), "dir",
          ["create", "getattr", "search", "write", "add_name"], True)
    missing = [line for line in transitions if line not in lines]
    if missing:
        raise ValueError("Linked binary lacks exact automatic transitions: " + repr(missing))
    return {
        "native_hardware": hardware,
        "native_manager_startup": manager_startup,
        "native_camera": camera,
        "timezone_link_decisions": timezone_decisions + 9,
        "binary_access_checks": len(checks),
        "public_module_role_types": len(role_types),
        "public_module_original_android_subjects": len(original_contract["subjects"]),
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



def verify_native_auxiliary_sockets(library, binary, exported, original_contract):
    """Read back every role's complete socket-inode vector and fixed transitions."""
    policy = Policy(library, binary)
    lines = set(exported.read_text().splitlines())
    actors = sorted({
        (role, line[len(f"(roletype {role} "):-1])
        for role in ["r", "system_r"] for line in lines
        if line.startswith(f"(roletype {role} ")
    })
    if not set(original_contract["subjects"]).issubset(
            {name for role, name in actors if role == "r"}):
        raise ValueError("Original Android subjects missing from auxiliary socket review")
    names = [
        ("AskPassword", "p4_linux_ask_password_socket_t"),
        ("Credentials", "p4_linux_credentials_socket_t"),
        ("FactoryReset", "p4_linux_factory_reset_socket_t"),
        ("Hostname", "p4_linux_hostnamed_socket_t"),
        ("MuteConsole", "p4_linux_mute_console_socket_t"),
        ("sysext", "p4_linux_sysext_socket_t"),
    ]
    sids = {}
    checks = []

    def sid(context):
        if context not in sids:
            value = ctypes.c_uint32()
            raw = context.encode()
            if policy.lib.sepol_context_to_sid(
                    raw, len(raw) + 1, ctypes.byref(value)) != 0:
                raise ValueError("Invalid auxiliary socket context: " + context)
            sids[context] = value.value
        return sids[context]

    def exact(subject, target, kind, permissions, expected):
        number, bits = policy.permissions(kind, permissions)
        mask = 0
        for bit in bits.values():
            mask |= bit
        decision = Decision()
        if policy.lib.sepol_compute_av(
                sid(subject), sid(target), number, mask, ctypes.byref(decision)) != 0:
            raise ValueError("Cannot read auxiliary socket decision")
        actual = {name for name, bit in bits.items() if decision.allowed & bit}
        if actual != set(expected):
            raise ValueError(
                f"Auxiliary socket boundary differs: {subject} -> {target} "
                f"{kind}: {sorted(actual)} != {sorted(expected)}")
        checks.extend([subject, target, kind, name, name in actual] for name in permissions)

    # Original admitted plat_sepolicy.cil: common file, inherited unchanged
    # by (class sock_file ()). The shared-payload contract selects fewer classes.
    sock_file_permissions = (
        "ioctl read write create getattr setattr lock relabelfrom relabelto append "
        "map unlink link rename execute quotaon mounton audit_access open execmod "
        "watch watch_mount watch_sb watch_with_perm watch_reads").split()
    manager = "u:system_r:init_t:s0"
    transitions = []
    for leaf, target in names:
        for role, actor in actors:
            expected = (["getattr", "create", "setattr", "write", "unlink"]
                        if (role, actor) == ("system_r", "init_t") else [])
            exact(f"u:{role}:{actor}:s0", f"u:object_r:{target}:s0", "sock_file",
                  sock_file_permissions, expected)
        transitions.append(
            f'(typetransition init_t p4_linux_systemd_run_t sock_file "io.systemd.{leaf}" {target})')
    exact(manager, "u:object_r:p4_linux_native_bin_t:s0", "file",
          original_contract["classes"]["file"], ["getattr"])
    if any(line not in lines for line in transitions):
        raise ValueError("Missing fixed auxiliary listener transition")
    return {
        "listener_types": len(names),
        "process_role_types": len(actors),
        "permission_checks": len(checks),
        "exact_automatic_transitions": len(transitions),
        "access_matrix_sha256": hashlib.sha256(
            json.dumps(checks, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
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
        "ubuntu-native-journal-storage.cil",
        "ubuntu-core-cgroup-ownership.cil", "ubuntu-native-services.cil",
        "ubuntu-native-service-capabilities.cil",
        "ubuntu-native-login-audit.cil",
        "ubuntu-native-service-runtime.cil", "ubuntu-native-sandbox.cil",
        "ubuntu-native-maintenance.cil",
        "frontend-android-interface.cil", "native-camera-interface.cil", "linux-frontend-observer.cil", "instance-launcher.cil",
        "linux-query-owner.cil", "linux-fixed-metadata-observer.cil",
        "instance-factory-cgroup.cil", "ubuntu-systemd-unit-status.cil",
        "linux-application-roles.cil", "linux-install-catalog.cil",
        "ubuntu-dbus.cil", "ubuntu-native-selinux-query.cil",
        "ubuntu-native-pam.cil", "ubuntu-native-session-storage.cil", "ubuntu-native-session-ipc.cil",
        "ubuntu-native-runtime-retirement.cil",
        "ubuntu-native-greeter-home.cil",

        "ubuntu-native-manager-lifecycle.cil",
        "ubuntu-native-hardware.cil",
        "ubuntu-presenter-runtime.cil",
        "linux-package-maintenance.cil", "linux-public-control.cil",
    )
    components = [here / name for name in component_names]
    sources = [compiler, library, args.linux_board_cil, *args.android_cil, *components,
               here / "cp3a-kernel-handle-inputs.json", Path(__file__),
               here / "derive_shared_payload_cgroup_policy.py",
               here / "verify_native_login_audit.py", here / "verify_native_journal_storage.py",
               here / "verify_greeter_home.py", here / "verify_native_maintenance.py",
               here / "ubuntu-native-file_contexts", here / "ubuntu-real-root-file_contexts",
               here / "linux-service-file_contexts", here / "linux-initial-calibration-file_contexts"]
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
        host_control = verify_host_control(library, linked, work / "host-control-binary.cil", contract)
        native_capabilities = verify_native_service_capabilities(library, linked)
        login_audit = verify_login_audit(library, linked, work / "login-audit-binary.cil", export_binary_policy)
        auxiliary_sockets = verify_native_auxiliary_sockets(
            library, linked, work / "host-control-binary.cil", contract)
        journal_storage = verify_journal_storage(
            library, linked, work / "host-control-binary.cil", contract)
        greeter_home = verify_greeter_home(library, linked, work / "host-control-binary.cil", contract, here / "ubuntu-native-file_contexts")
        native_maintenance = verify_native_maintenance(library, linked, work / "maintenance-binary.cil", export_binary_policy)
        manager_file_contexts = verify_manager_file_contexts(here, work)
        result = {
            "native_manager_file_contexts": manager_file_contexts,
            "native_maintenance": native_maintenance,
            "native_maintenance_verifier": sha256(here / "verify_native_maintenance.py"),
            "native_journal_storage": journal_storage,
            "native_journal_storage_verifier": sha256(here / "verify_native_journal_storage.py"),
            "native_greeter_home": greeter_home,
            "native_greeter_home_verifier": sha256(here / "verify_greeter_home.py"),
            "native_service_capabilities": native_capabilities,
            "native_login_audit": login_audit,
            "native_auxiliary_sockets": auxiliary_sockets,
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
