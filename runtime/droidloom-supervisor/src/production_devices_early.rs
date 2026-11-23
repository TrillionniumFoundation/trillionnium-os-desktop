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

impl PreparedDevices {
    pub(crate) fn prepare_early(child: &EarlyBaseAdmission<'_>) -> Result<Self> {
        child.revalidate()?;
        let devices = Self::create_for_tree(child, true, None)?;
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

pub(super) fn create_readiness_directories(root: &File, nodes: &[DeviceIdentity]) -> Result<()> {
    fn create(parent: &File, name: &CStr) -> Result<File> {
        zero(unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o755) } as _)?;
        let child = directory(parent, name)?;
        zero(unsafe { libc::fchmod(child.as_raw_fd(), 0o755) } as _)?;
        Ok(child)
    }
    let socket = create(root, c"socket")?;
    create(&socket, c"droidloom")?;
    verify_readiness_directories(root, 0, 0, nodes)
}

pub(super) fn verify_readiness_directories(root: &File, uid: u32, gid: u32, nodes: &[DeviceIdentity]) -> Result<()> {
    let mut expected: Vec<_> = DEVICES.iter().map(|spec| spec.name.to_bytes().to_vec()).collect();
    expected.push(b"socket".to_vec());
    expected.sort();
    need(directory_names(root)? == expected, "only seven fixed devices and the readiness parent")?;
    verify_device_nodes(root, uid, gid, nodes)?;
    let socket = directory(root, c"socket")?;
    let target = directory(&socket, c"droidloom")?;
    let filesystem = root.metadata()?.dev();
    let original_mount = mount_id(root)?;
    for dir in [&socket, &target] {
        let m = dir.metadata()?;
        need(m.dev() == filesystem && m.uid() == uid && m.gid() == gid
            && m.mode() == libc::S_IFDIR | 0o755 && mount_id(dir)? == original_mount,
            "readiness directories require the same private mount, mode and mapped identities")?;
    }
    need(directory_names(&socket)? == [b"droidloom".to_vec()] && directory_names(&target)?.is_empty(),
        "only one empty fixed readiness target may exist before transfer")
}
