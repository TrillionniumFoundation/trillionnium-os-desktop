"""Closed native camera ownership over the actually linked policy."""
import json
from pathlib import Path

def verify_camera(policy, lines, check, obj, source):
    roles = []
    for line in sorted(lines):
        for role in ("r", "system_r"):
            prefix = f"(roletype {role} "
            if line.startswith(prefix):
                name = line[len(prefix):-1]
                if not name or "(" in name or any(c.isspace() for c in name):
                    raise ValueError("Unexpected camera role expansion")
                roles.append((role, name))
    broker = "u:r:droidloom_broker:s0"
    capture = "u:r:droidloom_camera_capture:s0"
    producer = "u:r:droidloom_camera_producer:s0"
    init = "u:r:init:s0"
    full_caps = (
        "chown dac_override dac_read_search fowner fsetid kill setgid setuid setpcap "
        "linux_immutable net_bind_service net_broadcast net_admin net_raw ipc_lock ipc_owner "
        "sys_module sys_rawio sys_chroot sys_ptrace sys_pacct sys_admin sys_boot sys_nice "
        "sys_resource sys_time sys_tty_config mknod lease audit_write audit_control setfcap"
    ).split()
    cap2 = "mac_override mac_admin syslog wake_alarm block_suspend audit_read perfmon bpf checkpoint_restore".split()
    for actor in (capture, producer):
        for kind in ("capability", "cap_userns"):
            check(actor, actor, kind, full_caps, False)
        for kind in ("capability2", "cap2_userns"):
            check(actor, actor, kind, cap2, False)
    for role, name in roles:
        actor = f"u:{role}:{name}:s0"
        check(actor, capture, "process", ["transition"], actor == broker)
        check(actor, capture, "process", ["dyntransition", "ptrace"], False)
        check(actor, producer, "process", ["transition"], actor == init)
        check(actor, producer, "process", ["dyntransition"], False)
        if name != "kernel":
            check(actor, obj("p4_linux_camera_apparmor_revision_t"), "file",
                  ["open", "read"], actor == broker)
        check(actor, obj("p4_linux_camera_apparmor_revision_t"), "file",
              ["write", "append", "create", "setattr", "relabelto", "relabelfrom", "execute", "map"], False)
    check(broker, capture, "process2", ["nnp_transition", "nosuid_transition"], True)
    check(capture, capture, "process", ["fork", "setexec", "setcurrent", "setfscreate", "setsockcreate"], False)
    check(capture, broker, "fd", ["use"], True)
    check(broker, capture, "fd", ["use"], True)
    check(capture, broker, "unix_stream_socket",
          ["accept", "getattr", "getopt", "setopt", "read", "write", "shutdown"], True)
    check(producer, broker, "unix_stream_socket", ["connectto"], True)
    check(producer, broker, "fd", ["use"], False)
    check(producer, capture, "fd", ["use"], False)
    check(producer, obj("droidloom_camera_socket"), "sock_file", ["getattr", "write"], True)
    check(broker, obj("droidloom_camera_socket"), "sock_file", ["create", "getattr", "setattr", "unlink"], True)
    check(producer, "u:r:virtual_camera:s0", "binder", ["call", "transfer"], True)
    check(producer, "u:r:hal_graphics_allocator_default:s0", "binder", ["call", "transfer"], True)
    check(producer, obj("hal_graphics_allocator_service"), "service_manager", ["find"], True)
    check(producer, obj("hal_graphics_mapper_service"), "service_manager", ["find"], True)
    check(producer, obj("same_process_hal_file"), "file", ["getattr", "open", "read", "map", "execute"], True)
    for node in ("p4_linux_uvc_device_t", "p4_linux_drm_card_t", "p4_linux_drm_render_t",
                 "p4_linux_input_event_t", "dmabuf_system_heap_device", "dmabuf_system_secure_heap_device"):
        check(producer, obj(node), "chr_file", ["open", "read", "write", "ioctl", "map"], False)
    for actor in (broker, capture):
        check(actor, producer, "binder", ["call", "transfer", "impersonate"], False)
        for target in ("p4_linux_user_home_t", "p4_linux_tmp_t", "p4_linux_greeter_home_t"):
            check(actor, obj(target), "file", ["open", "read", "write", "create", "execute"], False)
    lock = json.loads((Path(source) / "pocket4-board-inputs.lock.json").read_text())
    aa = lock["files"]["ubuntu-apparmor.profiles"]
    names = aa["board_profile_order"]
    if names.count("droidloom-policy-loader") != 1 or names.count("droidloom-camera-capture") != 1:
        raise ValueError("Camera profile must have one original ordered load")
    birth = 164 - names.index("droidloom-policy-loader") + names.index("droidloom-camera-capture")
    wanted = [
        '(typetransition droidloom_broker droidloom_frontend_android_dir sock_file "camera" droidloom_camera_socket)',
        '(typetransition kernel p4_linux_policy_epoch_dir_t file "camera-apparmor-epoch" p4_linux_apparmor_epoch_t)',
        '(typetransition p4_linux_udev_t p4_linux_native_dev_root_t dir "v4l" p4_linux_uvc_dir_t)',
        '(typetransition p4_linux_udev_t p4_linux_uvc_dir_t dir "by-id" p4_linux_uvc_dir_t)',
        '(typetransition p4_linux_udev_t p4_linux_uvc_dir_t dir "by-path" p4_linux_uvc_dir_t)',
        f'(genfscon apparmorfs "/raw_data/{birth}/revision" (u object_r p4_linux_camera_apparmor_revision_t ((s0) (s0))))',
    ]
    missing = [item for item in wanted if item not in lines]
    if missing:
        raise ValueError("Camera exact linked transitions differ: " + json.dumps(missing))
    return {"process_contexts": len(roles), "zero_capability_checks": 164,
            "exact_transitions_and_counter": len(wanted), "camera_raw_generation": birth,
            "original_three_profile_epoch_unchanged": True}
