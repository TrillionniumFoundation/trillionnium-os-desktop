//! Both creation routes retain their original generation and the exact mapped user namespace.
use super::*;
use crate::production_identity::IdentityLease;
use crate::production_selection::early_generation::{EarlyBaseAdmission, EarlyBaseRetirement};

pub(super) trait DeviceTree {
    fn revalidate(&self) -> Result<()>;
    fn identity_lease(&self) -> Result<&IdentityLease>;
    fn proc_directory(&self) -> &File;
    fn user_namespace(&self) -> &File;
    fn descendant_pid_namespace(&self) -> Option<&File>;
}

impl DeviceTree for OwnedNamespaceWitness<'_> {
    fn revalidate(&self) -> Result<()> { Ok(OwnedNamespaceWitness::revalidate(self)?) }
    fn identity_lease(&self) -> Result<&IdentityLease> { Ok(OwnedNamespaceWitness::identity_lease(self)?) }
    fn proc_directory(&self) -> &File { OwnedNamespaceWitness::proc_directory(self) }
    fn user_namespace(&self) -> &File { OwnedNamespaceWitness::user_namespace(self) }
    fn descendant_pid_namespace(&self) -> Option<&File> { OwnedNamespaceWitness::descendant_pid_namespace(self) }
}

impl DeviceTree for EarlyBaseAdmission<'_> {
    fn revalidate(&self) -> Result<()> { Ok(EarlyBaseAdmission::revalidate(self)?) }
    fn identity_lease(&self) -> Result<&IdentityLease> {
        EarlyBaseAdmission::revalidate(self)?;
        Ok(EarlyBaseAdmission::identity_lease(self))
    }
    fn proc_directory(&self) -> &File { EarlyBaseAdmission::proc_directory(self) }
    fn user_namespace(&self) -> &File { EarlyBaseAdmission::user_namespace(self) }
    fn descendant_pid_namespace(&self) -> Option<&File> { Some(self.board().pid_namespace()) }
}

fn selected_device_mount(child: &EarlyBaseAdmission<'_>) -> Result<File> {
    let expected = child.board().device_source_identity()?;
    let namespace = child.board().mount_namespace();
    child.revalidate()?;
    let result = std::thread::scope(|scope| {
        scope.spawn(|| -> Result<File> {
            // setns() changes the root and working directory of its fs_struct.
            // This worker keeps its own fs_struct and exits in the child mount namespace.
            zero(unsafe { libc::unshare(libc::CLONE_FS) } as _)?;
            zero(unsafe { libc::setns(namespace.as_raw_fd(), libc::CLONE_NEWNS) } as _)?;
            let root = fd_result(unsafe {
                libc::open(c"/".as_ptr(), libc::O_PATH | libc::O_DIRECTORY | O_SAFE) as _
            })?;
            let run = open_at(&root, c"run", libc::O_PATH | libc::O_DIRECTORY)?;
            let generation = open_at(&run, c"droidloom-early", libc::O_PATH | libc::O_DIRECTORY)?;
            let original = directory(&generation, c"private-dev")?;
            let mut st: libc::statx = unsafe { std::mem::zeroed() };
            const UNIQUE: u32 = 0x4000; // STATX_MNT_ID_UNIQUE
            zero(unsafe { libc::syscall(libc::SYS_statx, original.as_raw_fd(),
                c"".as_ptr(), AT_EMPTY_PATH, UNIQUE, &mut st) })?;
            let id = node(&original)?;
            need(st.stx_mask & UNIQUE != 0 && (id.0, id.1, st.stx_mnt_id) == expected,
                 "original per-generation device filesystem changed")?;
            verify_root(&original, 0, 0)?;
            private_directory_role(&original, c"u:object_r:p4_linux_private_dev_root_t:s0")?;
            need(directory_names(&original)?.is_empty(), "original device filesystem was already claimed")?;
            let mount = fd_result(unsafe {
                libc::syscall(libc::SYS_open_tree, original.as_raw_fd(), c"".as_ptr(),
                              libc::OPEN_TREE_CLONE | libc::O_CLOEXEC as u32 | AT_EMPTY_PATH)
            })?;
            require_detached(&mount)?;
            need(node(&mount)? == id, "detached clone differs from the board device filesystem")?;
            Ok(mount)
        }).join().map_err(|_| DeviceError::Rejected("device mount worker did not finish"))?
    })?;
    child.revalidate()?;
    Ok(result)
}

impl PreparedDevices {
    pub(crate) fn prepare_early(child: &EarlyBaseAdmission<'_>) -> Result<Self> {
        child.revalidate()?;
        let source = selected_device_mount(child)?;
        let devices = Self::create_for_tree(child, Some(source), None)?;
        child.revalidate()?;
        Ok(devices)
    }

    pub(crate) fn early_descriptor_for_transfer<'a>(&'a mut self, child: &EarlyBaseAdmission<'_>) -> Result<BorrowedFd<'a>> {
        require_initial_broker()?;
        child.revalidate()?;
        self.descriptor_after_admission(child)
    }

    pub(crate) fn retire_after_early_tree(mut self, retired: &EarlyBaseRetirement) -> Result<DeviceRetirement> {
        let r = self.resources.as_ref().ok_or(DeviceError::Rejected("early private device owner was retired"))?;
        retired.verify_mount_retirement(&r.userns, r.host_uid, &r.cohort)?;
        self.cleanup(true)
    }
}

fn directory(parent: &File, name: &CStr) -> Result<File> {
    open_at(parent, name, libc::O_RDONLY | libc::O_DIRECTORY)
}

fn private_directory_role(directory: &File, expected: &CStr) -> Result<()> {
    let readable = open_at(directory, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
    need(node(&readable)? == node(directory)? && mount_id(&readable)? == mount_id(directory)?,
         "opened a different device directory for its SELinux role")?;
    let mut value = [0u8; 128];
    let length = unsafe {
        libc::fgetxattr(
            readable.as_raw_fd(),
            c"security.selinux".as_ptr(),
            value.as_mut_ptr().cast(),
            value.len(),
        )
    };
    if length < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let value = &value[..length as usize];
    need(
        value == expected.to_bytes() || value == expected.to_bytes_with_nul(),
        "selected SELinux type on the original private device directory",
    )
}

pub(super) fn create_readiness_directories(root: &File, nodes: &[DeviceIdentity]) -> Result<()> {
    fn create(parent: &File, name: &CStr) -> Result<File> {
        zero(unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o755) } as _)?;
        let child = directory(parent, name)?;
        zero(unsafe { libc::fchmod(child.as_raw_fd(), 0o755) } as _)?;
        Ok(child)
    }
    private_directory_role(root, c"u:object_r:p4_linux_private_dev_root_t:s0")?;
    let socket = create(root, c"socket")?;
    private_directory_role(&socket, c"u:object_r:p4_linux_private_socket_parent_t:s0")?;
    let target = create(&socket, c"droidloom")?;
    private_directory_role(&target, c"u:object_r:p4_linux_readiness_mount_t:s0")?;
    verify_readiness_directories(root, 0, 0, nodes)
}

pub(super) fn verify_readiness_directories(root: &File, uid: u32, gid: u32, nodes: &[DeviceIdentity]) -> Result<()> {
    let mut expected: Vec<_> = DEVICES.iter().map(|spec| spec.name.to_bytes().to_vec()).collect();
    expected.push(b"socket".to_vec());
    expected.sort();
    need(directory_names_bounded(root, expected.len())? == expected, "only seven fixed devices and the readiness parent")?;
    verify_device_nodes(root, uid, gid, nodes)?;
    let socket = directory(root, c"socket")?;
    let target = directory(&socket, c"droidloom")?;
    private_directory_role(root, c"u:object_r:p4_linux_private_dev_root_t:s0")?;
    private_directory_role(&socket, c"u:object_r:p4_linux_private_socket_parent_t:s0")?;
    private_directory_role(&target, c"u:object_r:p4_linux_readiness_mount_t:s0")?;
    let filesystem = root.metadata()?.dev();
    let original_mount = mount_id(root)?;
    for dir in [&socket, &target] {
        let m = dir.metadata()?;
        need(m.dev() == filesystem && m.uid() == uid && m.gid() == gid
            && m.mode() == libc::S_IFDIR | 0o755 && mount_id(dir)? == original_mount,
            "readiness directories require the same private mount, mode and mapped identities")?;
    }
    need(directory_names_bounded(&socket, 1)? == [b"droidloom".to_vec()] && directory_names_bounded(&target, 0)?.is_empty(),
        "only one empty fixed readiness target may exist before transfer")
}

#[cfg(test)]
mod hardware {
    use super::*;

    #[test]
    #[ignore = "requires the actual initial broker, a fresh mapped PID 1 and its kernel userns"]
    fn actual_device_filesystem_retains_the_empty_readiness_target_across_idmap() -> Result<()> {
        require_initial_broker()?;
        let duplicate = |n| fd_result(unsafe { libc::fcntl(n, libc::F_DUPFD_CLOEXEC, 20) } as _);
        let proc = duplicate(9)?;
        let user = duplicate(10)?;
        let range = IdRange { start: 200000, count: 100000 };
        for n in [c"uid_map", c"gid_map"] {
            map_is_exact(&bounded(open_at(&proc, n, libc::O_RDONLY)?, PROC_LIMIT)?,range)?;
        }
        namespace(&user, libc::CLONE_NEWUSER)?;
        let child_user = unsafe { libc::openat(proc.as_raw_fd(), c"ns/user".as_ptr(), libc::O_RDONLY|libc::O_CLOEXEC) };
        let child_user = fd_result(child_user as _)?;
        need(node(&child_user)? == node(&user)?, "original child user namespace")?;
        let mount = fresh_tmpfs()?;
        let before = require_detached(&mount)?;
        let devices = create_devices(&mount)?;
        create_readiness_directories(&mount, &devices)?;
        idmap_mount(&mount, &user)?;
        need(require_detached(&mount)? == before, "same private device mount after idmapping")?;
        verify_root(&mount, range.start, range.start)?;
        verify_readiness_directories(&mount, range.start, range.start, &devices)
    }
}
