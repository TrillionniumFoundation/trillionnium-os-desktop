"""Fixed WindowManager density role over the actual linked binary."""
def verify_fixed_display(lines, check, obj, roles):
    actor = "u:r:droidloom_display_control:s0"
    checks = 0
    def test(source, target, kind, permissions, allowed):
        nonlocal checks
        check(source, target, kind, permissions, allowed)
        checks += len(permissions)
    caps = ("chown dac_override dac_read_search fowner fsetid kill setgid setuid setpcap "
            "linux_immutable net_bind_service net_broadcast net_admin net_raw ipc_lock ipc_owner "
            "sys_module sys_rawio sys_chroot sys_ptrace sys_pacct sys_admin sys_boot sys_nice "
            "sys_resource sys_time sys_tty_config mknod lease audit_write audit_control setfcap").split()
    cap2 = "mac_override mac_admin syslog wake_alarm block_suspend audit_read perfmon bpf checkpoint_restore".split()
    for kind in ("capability", "cap_userns"):
        test(actor, actor, kind, caps, False)
    for kind in ("capability2", "cap2_userns"):
        test(actor, actor, kind, cap2, False)
    test("u:r:droidloom_query_birth:s0", actor, "process", ["transition"], True)
    test("u:r:droidloom_query_birth:s0", actor, "process2", ["nnp_transition","nosuid_transition"], True)
    test("u:r:kernel:s0", actor, "process", ["getattr","ptrace","sigkill","sigstop"], True)
    test("u:r:droidloom_metadata_observer:s0", actor, "file", ["getattr","open","read"], True)
    test(actor, "u:r:kernel:s0", "fd", ["use"], True)
    test(actor, "u:r:droidloom_query_io:s0", "fd", ["use"], True)
    test(actor, "u:r:droidloom_query_io:s0", "fifo_file", ["getattr","write"], True)
    test(actor, obj("droidloom_query_exec"), "file", ["getattr","open","read","map","execute","entrypoint"], True)
    test(actor, obj("droidloom_provider_exec"), "file", ["entrypoint"], False)
    for target in ("servicemanager", "system_server"):
        test(actor, f"u:r:{target}:s0", "binder", ["call","transfer"], True)
    test(actor, obj("window_service"), "service_manager", ["find"], True)
    test(actor, obj("binder_stats_consumer_service"), "service_manager", ["find"], True)
    for target in ("activity_service","package_service","display_service","account_service"):
        test(actor, obj(target), "service_manager", ["find","add"], False)
    for target in ("apk_data_file","app_data_file","privapp_data_file","system_app_data_file",
                   "p4_linux_user_home_t","p4_linux_tmp_t","p4_linux_product_store_t"):
        test(actor, obj(target), "file", ["open","read","map","write","append","create","execute"], False)
    for role, name in roles:
        if role == "system_r" or name == "droidloom_broker":
            test(f"u:{role}:{name}:s0", actor, "process",
                 ["transition","dyntransition","ptrace"], False)
            test(actor, f"u:{role}:{name}:s0", "fd", ["use"], False)
    test(actor, obj("droidloom_query_exec"), "file",
         ["write","append","create","unlink","link","rename","setattr","execute_no_trans","relabelfrom","relabelto"], False)
    test(actor, actor, "process", ["setexec","setcurrent","setfscreate","setsockcreate","execmem"], False)
    test(actor, "u:r:kernel:s0", "security", ["load_policy","setenforce","setbool","setsecparam"], False)
    return {"checks":checks,"fixed_primary_display":0,"capabilities_added":[],
            "fixed_service":"window","arbitrary_argv":False,"runtime_qualified":False}
