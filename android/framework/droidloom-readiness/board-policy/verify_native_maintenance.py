"""Read back the closed native maintenance boundary from the linked binary."""
import ctypes
import hashlib
import json
from derive_shared_payload_cgroup_policy import Decision, Policy

ACTORS = {
    "p4_linux_sudo_t": {"chown","fowner","setuid","setgid","kill","audit_write"},
    "p4_linux_maintenance_t": {"setuid","setgid","kill"},
    "p4_linux_maintenance_journal_t": set(),
}
CAP1 = ("chown dac_override dac_read_search fowner fsetid kill setgid setuid setpcap "
        "linux_immutable net_bind_service net_broadcast net_admin net_raw ipc_lock ipc_owner "
        "sys_module sys_rawio sys_chroot sys_ptrace sys_pacct sys_admin sys_boot sys_nice "
        "sys_resource sys_time sys_tty_config mknod lease audit_write audit_control setfcap").split()
CAP2 = "mac_override mac_admin syslog wake_alarm block_suspend audit_read perfmon bpf checkpoint_restore".split()
FILE = "ioctl read write create getattr setattr lock relabelfrom relabelto append map unlink link rename execute quotaon mounton audit_access open execmod watch watch_mount watch_sb watch_with_perm watch_reads entrypoint execute_no_trans".split()
SECURITY = "compute_av compute_create compute_member check_context load_policy compute_relabel compute_user setenforce setbool setsecparam setcheckreqprot read_policy validate_trans".split()
def verify_native_maintenance(library, binary, export, export_binary_policy):
    policy = Policy(library,binary)
    lines = export_binary_policy(policy,binary,export)
    cached, checks = {},[]
    def sid(c):
        if c not in cached:
            raw=c.encode();n=ctypes.c_uint32()
            if policy.lib.sepol_context_to_sid(raw,len(raw)+1,ctypes.byref(n)):
                raise ValueError("Invalid maintenance context: "+c)
            cached[c]=n.value
        return cached[c]
    def context(n):return "u:system_r:"+n+":s0"
    def obj(n):return "u:object_r:"+n+":s0"
    def exact(s,t,k,perms,want):
        cls,bits=policy.permissions(k,perms);mask=0
        for bit in bits.values():mask|=bit
        av=Decision()
        if policy.lib.sepol_compute_av(sid(s),sid(t),cls,mask,ctypes.byref(av)):
            raise ValueError("Maintenance binary AV query failed")
        got={p for p,b in bits.items() if av.allowed & b}
        if got!=set(want):
            raise ValueError(f"Maintenance boundary differs: {s}->{t} {k}: {sorted(got)} != {sorted(want)}")
        checks.extend([s,t,k,p,p in got] for p in perms)
    for name,caps in ACTORS.items():
        c=context(name)
        for k,p in (("capability",CAP1),("capability2",CAP2),("cap_userns",CAP1),("cap2_userns",CAP2)):
            exact(c,c,k,p,caps if k=="capability" else set())
        exact(c,"u:r:kernel:s0","security",SECURITY,[])
        exact(c,c,"process","setcurrent dyntransition setexec setfscreate setkeycreate setsockcreate".split(),[])
        for t in ("p4_linux_user_home_t","p4_linux_product_store_t"):
            exact(c,obj(t),"file","open read write append create unlink rename link setattr".split(),[])
    session=context("p4_linux_user_session_t");sudo=context("p4_linux_sudo_t")
    maint=context("p4_linux_maintenance_t");journal=context("p4_linux_maintenance_journal_t")
    for s,t,e in [(session,sudo,"p4_linux_sudo_exec_t"),(sudo,maint,"p4_linux_maintenance_exec_t"),(maint,journal,"p4_linux_journalctl_exec_t")]:
        exact(s,t,"process",["transition"],["transition"])
        exact(s,obj(e),"file",["read","open","execute","execute_no_trans"],["read","open","execute"])
        exact(t,obj(e),"file",["entrypoint"],["entrypoint"])
    exact(maint,journal,"process2",["nnp_transition","nosuid_transition"],["nnp_transition","nosuid_transition"])
    exact(sudo,obj("p4_linux_native_bin_t"),"file",["execute","execute_no_trans","entrypoint"],[])
    exact(sudo,obj("p4_linux_runtime_lib_t"),"file",["execute_no_trans","entrypoint"],[])
    exact(session,obj("p4_linux_maintenance_exec_t"),"file",["execute","execute_no_trans","entrypoint"],[])
    exact(maint,obj("p4_linux_maintenance_grubenv_t"),"file",FILE,["getattr","open","read","write"])
    exact(maint,obj("p4_linux_maintenance_grubcfg_t"),"file",FILE,["getattr","open","read"])
    exact(journal,obj("p4_linux_journal_database_t"),"file",FILE,["getattr","open","read","map","lock"])
    for t in ("p4_linux_maintenance_script_t","p4_linux_maintenance_config_t","p4_linux_maintenance_release_t"):
        exact(maint,obj(t),"file",FILE,["getattr","open","read"])
    services="start stop status reload kill load enable disable".split()
    exact(maint,obj("p4_linux_maintenance_reboot_unit_t"),"service",services,["status","start"])
    exact(maint,obj("p4_linux_production_unit_file_t"),"service",services,["status"])
    exact(maint,obj("p4_linux_factory_unit_file_t"),"service",services,["status"])
    exact(maint,obj("p4_linux_maintenance_exec_t"),"file",["execute_no_trans"],[])
    sources=[]
    for line in sorted(lines):
        for role in ("r","system_r"):
            prefix=f"(roletype {role} "
            if line.startswith(prefix):
                n=line[len(prefix):-1]
                if not n or any(x.isspace() for x in n) or "(" in n:raise ValueError("Nonconcrete maintenance role")
                c=f"u:{role}:{n}:s0";sources.append(c)
                for target,allowed in [(maint,sudo),(journal,maint)]:
                    exact(c,target,"process",["transition","dyntransition"],["transition"] if c==allowed else [])
    transitions=(
      "(typetransition p4_linux_user_session_t p4_linux_sudo_exec_t process p4_linux_sudo_t)",
      "(typetransition p4_linux_sudo_t p4_linux_maintenance_exec_t process p4_linux_maintenance_t)",
      "(typetransition p4_linux_maintenance_t p4_linux_journalctl_exec_t process p4_linux_maintenance_journal_t)",
    )
    missing=[t for t in transitions if t not in lines]
    if missing:raise ValueError("Maintenance binary transitions missing: "+repr(missing))
    return {"actor_count":len(ACTORS),"original_role_contexts":len(sources),
            "actual_binary_decisions":len(checks),"exact_transitions":len(transitions),
            "generic_sudo_shell_denied":True,"no_mac_management":True,
            "readonly_journal_distinct_from_flush":True,
            "matrix_sha256":hashlib.sha256(json.dumps(checks,separators=(",",":")).encode()).hexdigest(),
            "binary_export_sha256":hashlib.sha256(export.read_bytes()).hexdigest()}
