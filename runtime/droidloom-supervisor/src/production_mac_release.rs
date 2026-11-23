//! Export the immutable release inputs through the installed, confined loader on the board.
use super::*;
use crate::production_configuration::ConfigurationReadGuard;
use crate::production_selection::EarlyReleaseMedia;
use droidloom_contracts::mac_release::Release;
use serde_json::{Value, json};
use std::path::Path;

const INPUT: &str = "/usr/lib/droidloom/production/current/board-policy/joint.policy";
const AA_INPUT: &str = "/usr/lib/droidloom/production/current/board-policy/ubuntu-apparmor.profiles";
const MANAGER_EXE: &str = "/usr/lib/systemd/systemd";
const LOADER_EXE: &str = "/usr/lib/droidloom/production/current/droidloom-host-mac";
const LOCK: &[u8] = include_bytes!("../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json");

fn bytes(value: &impl serde::Serialize) -> Result<Vec<u8>> {
    let mut encoded = serde_json::to_vec_pretty(value)?;
    encoded.push(b'\n');
    Ok(encoded)
}

fn wanted<'a>(value: &'a Value, field: &str) -> Result<&'a str> {
    value[field].as_str().filter(|v|digest(v)).ok_or(MacError::Rejected("board release needs a fixed original digest"))
}

struct Program {
    path: &'static str,
    installed: File,
    executing: File,
    original: Node,
    digest: String,
}

impl Program {
    fn inspect(path: &'static str, who: &File, label: &str) -> Result<Self> {
        require(kind(who)? == PROC_MAGIC, "executing program must come from actual process procfs")?;
        let fd = unsafe {libc::openat(who.as_raw_fd(),c"exe".as_ptr(),libc::O_RDONLY|libc::O_CLOEXEC)};
        if fd < 0 {return Err(io::Error::last_os_error().into());}
        let executing=unsafe {File::from_raw_fd(fd)};
        let installed=open_absolute(path,libc::O_RDONLY)?;
        let original=Node::of(&installed)?;
        require(original == Node::of(&executing)? && original.mode & libc::S_IFMT == libc::S_IFREG
            && original.mode & 0o6022 == 0 && original.mode & 0o111 != 0 && original.uid == 0
            && original.gid == 0 && original.links == 1 && (64..=64*1024*1024).contains(&original.bytes),
            "the actual executing ELF must be the exact fixed Ubuntu release inode")?;
        let raw=bounded(&installed,64*1024*1024)?;
        require(raw.starts_with(b"\x7fELF") && raw.len() as u64 == original.bytes
            && context_matches(&manager_label::file_context(&installed)?,label), "installed ELF bytes or required execution label differ")?;
        let observed=Self {path, installed, executing, original, digest:sha(&raw)};
        observed.revalidate(who)?;
        Ok(observed)
    }
    fn revalidate(&self, who: &File) -> Result<()> {
        let fd=unsafe {libc::openat(who.as_raw_fd(),c"exe".as_ptr(),libc::O_RDONLY|libc::O_CLOEXEC)};
        if fd<0{return Err(io::Error::last_os_error().into());}
        let actual=unsafe {File::from_raw_fd(fd)};
        require(Node::of(&self.installed)?==self.original && Node::of(&self.executing)?==self.original
            && Node::of(&actual)?==self.original && Node::of(&open_absolute(self.path,libc::O_RDONLY)?)?==self.original,
            "executing process replaced its selected original ELF")
    }
}

fn fixed_role(own: &File, manager: &File) -> Result<()> {
    policy::initial_credentials(own)?;
    loader::fixed_loader_identity(&proc_attr(own,false)?,&proc_attr(own,true)?)?;
    loader::loader_nnp(own)?;
    require(context_matches(&proc_attr(manager,false)?,kernel_first::MANAGER)
           && proc_attr(manager,true)? == b"unconfined\n", "actual Ubuntu PID 1 differs from the board manager role")
}

fn named(root: &File, who: &str, parent: &str, class: &str, name: &str, expected: &str) -> Result<()> {
    let number=class_number(root,class)?;
    let query=format!("{who} {parent} {number} {name}");
    require(context_matches(&transaction(root,"create",query.as_bytes())?,expected),
            "actual kernel named creation differs from the selected protected destination")
}

fn named_destinations(root: &File) -> Result<()> {
    const DEV: &str="u:object_r:p4_linux_private_dev_root_t:s0";
    const SOCKET: &str="u:object_r:p4_linux_private_socket_parent_t:s0";
    const MOUNT: &str="u:object_r:p4_linux_readiness_mount_t:s0";
    const ENTRY: &str="u:system_r:droidloom_container_entry_t:s0";
    const RUNDIR: &str="u:object_r:p4_linux_readiness_dir_t:s0";
    const SIGNAL: &str="u:object_r:droidloom_readiness_socket:s0";
    named(root,BROKER,DEV,"dir","socket",SOCKET)?;
    named(root,BROKER,DEV,"dir","unexpected_name",DEV)?;
    named(root,BROKER,SOCKET,"dir","droidloom",MOUNT)?;
    named(root,BROKER,SOCKET,"dir","unexpected_name",SOCKET)?;
    named(root,ENTRY,RUNDIR,"sock_file","droidloom_readiness",SIGNAL)?;
    named(root,ENTRY,RUNDIR,"sock_file","unexpected_name",RUNDIR)?;
    named(root,kernel_first::MANAGER,"u:object_r:p4_linux_systemd_run_t:s0","sock_file","private",kernel_first::INITIAL_SOCKET)
}

fn invocation(own: &File) -> Result<String> {
    let cgroup = open_at(own.as_raw_fd(), c"cgroup",libc::O_RDONLY)?;
    require(kind(&cgroup)?==PROC_MAGIC && bounded(&cgroup, 4096)?==b"0::/system.slice/droidloom-mac-calibration.service\n",
            "calibration requires its fixed systemd unit in the original unified hierarchy")?;
    let id=std::env::var("INVOCATION_ID").map_err(|_|MacError::Rejected("calibration requires the manager invocation ID"))?;
    require(id.len()==32 && id.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)) && id.bytes().any(|b|b!=b'0'),
            "invalid manager invocation ID")?;
    let fd=unsafe{libc::fcntl(libc::STDOUT_FILENO,libc::F_DUPFD_CLOEXEC,3)};
    if fd<0{return Err(io::Error::last_os_error().into());}
    let destination=unsafe{File::from_raw_fd(fd)};
    let node=Node::of(&destination)?;
    require(node.mode == libc::S_IFREG|0o600 && node.uid==0 && node.gid==0 && node.links==1 && node.bytes==0
        && context_matches(&manager_label::file_context(&destination)?,"u:object_r:p4_linux_mac_capture_t:s0"),
        "manager must supply the empty private calibration output")?;
    Ok(id)
}

pub(crate) fn capture() -> Result<Release> {
    let own=own_proc()?;
    let manager=open_absolute("/proc/1",libc::O_PATH|libc::O_DIRECTORY)?;
    fixed_role(&own,&manager)?;
    let invocation=invocation(&own)?;
    let guard=ConfigurationReadGuard::inspect_existing().map_err(|e| MacError::Selection(e.to_string()))?;
    let selection=ProductionSelection::load(&guard,Path::new("/etc/droidloom/cell.json"),unsafe {libc::getuid()})
        .map_err(|e|MacError::Selection(e.to_string()))?;
    require(selection.is_kernel_first(),"a real private kernel-first generation is required")?;
    let media=EarlyReleaseMedia::acquire(&selection).map_err(|e|MacError::Selection(e.to_string()))?;
    let manager_exe=Program::inspect(MANAGER_EXE,&manager,"u:object_r:init_exec_t:s0")?;
    let loader_exe=Program::inspect(LOADER_EXE,&own,"u:object_r:droidloom_policy_loader_exec:s0")?;
    let lock:Value=serde_json::from_slice(LOCK)?;
    let (input_file,input)=Sealed::read(INPUT,MAX_POLICY)?;
    let (aa_file,aa)=Sealed::read(AA_INPUT,MAX_POLICY)?;
    let sources=&lock["files"];
    require(sources["joint.policy"]["size"]==input.len() && sources["joint.policy"]["sha256"]==sha(&input)
            && sources["ubuntu-apparmor.profiles"]["size"]==aa.len()
            && sources["ubuntu-apparmor.profiles"]["sha256"]==sha(&aa),"inputs differ from the compiled Pocket4 release lock")?;
    let roles=&sources["ubuntu-apparmor.profiles"]["board_profiles"];
    let hashes=[
        wanted(&roles["droidloom-policy-loader"],"kernel_profile_sha256")?,
        wanted(&roles["droidloom-production-android"],"kernel_profile_sha256")?,
        wanted(&roles["droidloom-production-broker"],"kernel_profile_sha256")?,
    ];
    let input_sha=sha(&input);
    let observed=board_epoch::BoardEpoch::acquire(&input_sha, hashes)?;
    let root=open_absolute(SELINUX_ROOT,libc::O_PATH|libc::O_DIRECTORY)?;
    require(kind(&root)?==SELINUX_MAGIC,"real enforcing selinuxfs is required")?;
    let status=StatusMap::open(&root)?;
    let epoch=status.read()?;
    require(epoch.policyload==1 && epoch.policyload==observed.policyload && epoch.sequence==observed.selinux_sequence,
            "loaded SELinux generation differs from the board parent's original policy load")?;
    let export=bounded(&relative(&root,&["policy"],libc::O_RDONLY)?,MAX_POLICY)?;
    require(export.len()>=1024,"original complete kernel policy export required")?;
    let release=kernel_text("/proc/sys/kernel/osrelease",PROC_MAGIC,256)?.trim_end_matches('\n').to_owned();
    let notes=kernel_bytes("/sys/kernel/notes",SYSFS_MAGIC,1024*1024)?;
    let active=kernel_text("/sys/kernel/security/lsm",SECURITYFS_MAGIC,4096)?;
    let lsms=lsm_list(&active)?.iter().map(|v|(*v).to_owned()).collect();
    let mut sequence=None;
    kernel_first::required(&root,&mut sequence)?;
    named_destinations(&root)?;
    require(sequence==Some(epoch.policyload),"actual kernel AV sequence differs from the original board load")?;
    let base=selection.base_cohort();
    let runtime=selection.runtime_manifest();
    let export_sha=sha(&export);
    let derivation=bytes(&json!({
        "schema":1,"scope":"android_kernel_first_mac_observation_v1","base_cohort_sha256":base,"runtime_manifest_sha256":runtime,
        "board_lock_sha256":sha(LOCK),"boot_id":observed.boot,"systemd_invocation_id":invocation,"apparmor_revision":observed.revision,
        "selinux":{"version":epoch.version,"sequence":epoch.sequence,"policyload":epoch.policyload,"enforcing":epoch.enforcing,"deny_unknown":epoch.deny_unknown},
        "policy_input_bytes":input.len(),"policy_input_sha256":input_sha,"policy_export_bytes":export.len(),"policy_export_sha256":export_sha,
        "kernel_notes_bytes":notes.len(),"kernel_notes_sha256":sha(&notes),"loader_role":LOADER,"manager_role":kernel_first::MANAGER,
        "manager_elf_bytes":manager_exe.original.bytes,"manager_elf_sha256":manager_exe.digest,"labeler_elf_bytes":loader_exe.original.bytes,"labeler_elf_sha256":loader_exe.digest,
        "kernel_named_create_checks":7,"original_four_images_read":4,"android_business_qualified":false}))?;
    let declaration=Declaration {schema:5,scope:"droidloom_linux_android_mac_v5".into(),base_cohort_sha256:base.into(),
        runtime_manifest_sha256:runtime.into(),kernel_release:release,kernel_notes_bytes:notes.len() as u64,kernel_notes_sha256:sha(&notes),
        active_lsms:lsms,context_routing:Some(ContextRouting::KernelEarlyAndroid),apparmor_loader_policy_sha256:hashes[0].into(),
        apparmor_android_policy_sha256:hashes[1].into(),apparmor_broker_policy_sha256:hashes[2].into(), policy_input_bytes:input.len() as u64,
        policy_input_sha256:input_sha,policy_export_bytes:export.len() as u64,policy_export_sha256:export_sha,derivation_bytes:derivation.len() as u64,derivation_sha256:sha(&derivation)};
    declaration.validate(&selection)?;
    let own_namespaces=policy::initial_namespaces(&own,&declaration)?;
    let host_namespaces=policy::initial_namespaces(&manager,&declaration)?;
    for (a,b) in own_namespaces.iter().zip(&host_namespaces) {
        require(Node::of(a)?.same_inode(Node::of(b)?),"loader and manager must remain in the original namespaces")?;
    }
    let label=bytes(&json!({"schema":"droidloom-original-systemd-label-v1","base_cohort_sha256":base,"runtime_manifest_sha256":runtime,
        "policy_input_bytes":declaration.policy_input_bytes,"policy_input_sha256":declaration.policy_input_sha256,
        "policy_export_bytes":declaration.policy_export_bytes,"policy_export_sha256":declaration.policy_export_sha256,
        "manager_elf_bytes":manager_exe.original.bytes,"manager_elf_sha256":manager_exe.digest,"labeler_elf_bytes":loader_exe.original.bytes,"labeler_elf_sha256":loader_exe.digest,
        "original_server_context":kernel_first::INITIAL_SOCKET}))?;
    let contract=bytes(&declaration)?;
    let package=Release::from_files(base,runtime,&observed.boot,&invocation,[&contract,&label,&input,&export,&derivation]).map_err(MacError::Rejected)?;
    observed.revalidate()?;
    require(status.read()?==epoch && Node::of(&root)?.same_inode(Node::of(&open_absolute(SELINUX_ROOT,libc::O_PATH|libc::O_DIRECTORY)?)?),
            "kernel policy or SELinux mount changed during release capture")?;
    manager_exe.revalidate(&manager)?;loader_exe.revalidate(&own)?;
    fixed_role(&own,&manager)?;
    for source in [&input_file,&aa_file]{source.revalidate()?;}
    media.revalidate().map_err(|e|MacError::Selection(e.to_string()))?;
    selection.revalidate().map_err(|e|MacError::Selection(e.to_string()))?;
    guard.revalidate().map_err(|e|MacError::Selection(e.to_string()))?;
    Ok(package)
}
