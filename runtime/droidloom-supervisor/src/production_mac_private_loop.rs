//! Live private-loop MAC checks; only the four fixed requests below execute.
//! /access does not query xperms. Every concrete ioctl must itself pass the
//! current enforcing kernel; complete binary bitmap absence is an install gate.
use super::*;
use crate::production_private_loop_owner::{LoopConfig, LoopStatus};
const TMPFS: &str = "u:object_r:tmpfs:s0";
const DIRECTORY: &str = "u:object_r:droidloom_apex_device_dir:s0";
const CONTROL: &str = "u:object_r:droidloom_apex_loop_control_device:s0";
const BLOCK: &str = "u:object_r:droidloom_apex_loop_device:s0";
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum PrivateLoopNode {
    Root,
    Directory,
    Control,
    Block,
}
impl PrivateLoopNode {
    fn context(self) -> &'static str {
        match self {
            Self::Root => TMPFS,
            Self::Directory => DIRECTORY,
            Self::Control => CONTROL,
            Self::Block => BLOCK,
        }
    }
    fn class(self) -> &'static str {
        match self {
            Self::Root | Self::Directory => "dir",
            Self::Control => "chr_file",
            Self::Block => "blk_file",
        }
    }
    fn kind(self) -> u32 {
        match self {
            Self::Root | Self::Directory => libc::S_IFDIR,
            Self::Control => libc::S_IFCHR,
            Self::Block => libc::S_IFBLK,
        }
    }
}
fn inode_label(file: &File) -> Result<Vec<u8>> {
    let before = Node::of(file)?;
    let mut bytes = [0_u8; 1024];
    let n = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        n > 0 && n as usize <= bytes.len(),
        "actual private-inode label size",
    )?;
    require(
        Node::of(file)? == before,
        "private inode changed during label observation",
    )?;
    Ok(bytes[..n as usize].to_vec())
}
fn creation(
    root: &File,
    parent: &str,
    class: &str,
    basename: Option<&str>,
    expected: &str,
) -> Result<()> {
    let number = class_number(root, class)?;
    let query = match basename {
        Some(name) => format!("{BROKER} {parent} {number} {name}"),
        None => format!("{BROKER} {parent} {number}"),
    };
    require(
        context_matches(&transaction(root, "create", query.as_bytes())?, expected),
        "actual private-node automatic creation context differs",
    )
}
fn creation_decisions(mac: &MacPreflight) -> Result<()> {
    let root = &mac.loaded.root;
    let mut sequence = Some(mac.loaded.av_sequence);
    for (target, class, permissions) in [
        (BROKER, "capability", &["sys_admin", "mknod"][..]),
        (TMPFS, "filesystem", &["mount", "getattr"][..]),
        (
            TMPFS,
            "dir",
            &[
                "getattr",
                "search",
                "read",
                "open",
                "write",
                "add_name",
                "remove_name",
            ][..],
        ),
        (
            DIRECTORY,
            "dir",
            &[
                "create",
                "getattr",
                "search",
                "read",
                "open",
                "write",
                "add_name",
                "remove_name",
                "rmdir",
            ][..],
        ),
        (
            CONTROL,
            "chr_file",
            &[
                "create", "getattr", "read", "write", "open", "ioctl", "unlink",
            ][..],
        ),
        (
            BLOCK,
            "blk_file",
            &[
                "create", "getattr", "read", "write", "open", "ioctl", "unlink",
            ][..],
        ),
    ] {
        access(
            root,
            BROKER,
            target,
            class,
            permissions,
            true,
            &mut sequence,
        )?;
    }
    for source in [DIRECTORY, CONTROL, BLOCK] {
        access(
            root,
            source,
            TMPFS,
            "filesystem",
            &["associate"],
            true,
            &mut sequence,
        )?;
    }
    for (target, class) in [
        (DIRECTORY, "dir"),
        (CONTROL, "chr_file"),
        (BLOCK, "blk_file"),
    ] {
        for source in [INIT, "u:r:apexd:s0", HOST] {
            access(
                root,
                source,
                target,
                class,
                &["getattr", "read", "write", "open"],
                false,
                &mut sequence,
            )?;
        }
    }
    access(
        root,
        BROKER,
        BROKER,
        "process",
        &["setfscreate"],
        false,
        &mut sequence,
    )?;
    creation(
        root,
        TMPFS,
        "dir",
        Some("droidloom-apex-devices"),
        DIRECTORY,
    )?;
    creation(root, DIRECTORY, "chr_file", Some("loop-control"), CONTROL)?;
    creation(root, DIRECTORY, "blk_file", None, BLOCK)?;
    creation(root, TMPFS, "dir", Some("droidloom-apex-unapproved"), TMPFS)?;
    creation(
        root,
        DIRECTORY,
        "chr_file",
        Some("loop-unapproved"),
        DIRECTORY,
    )?;
    Ok(())
}
/// Real current-epoch decisions; this grants no source ownership or Ready state.
pub(crate) struct MacPrivateLoopWitness {
    provider: ProviderBinding,
    _same_thread: PhantomData<Rc<()>>,
}
impl MacPreflight {
    pub(crate) fn private_loop_creation(
        &self,
        selection: &ProductionSelection,
    ) -> Result<MacPrivateLoopWitness> {
        self.revalidate(selection)?;
        self_attr::require_no_fscreate()?;
        creation_decisions(self)?;
        self.revalidate(selection)?;
        self_attr::require_no_fscreate()?;
        Ok(MacPrivateLoopWitness {
            provider: self.binding(),
            _same_thread: PhantomData,
        })
    }
}
impl MacPrivateLoopWitness {
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        require(
            self.provider == mac.binding(),
            "private loops belong to another provider or epoch",
        )?;
        mac.revalidate(selection)?;
        // Denying setfscreate now cannot clear an override inherited before entry.
        self_attr::require_no_fscreate()
    }
    pub(crate) fn node(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        file: &File,
        role: PrivateLoopNode,
    ) -> Result<()> {
        self.revalidate(mac, selection)?;
        let before = Node::of(file)?;
        require(
            before.mode & libc::S_IFMT == role.kind() && before.uid == 0 && before.gid == 0,
            "actual fixed private-node kind and owner",
        )?;
        require(
            context_matches(&inode_label(file)?, role.context()),
            "actual held private inode has another context",
        )?;
        let mut sequence = Some(mac.loaded.av_sequence);
        access(
            &mac.loaded.root,
            BROKER,
            role.context(),
            role.class(),
            &["getattr", "open"],
            true,
            &mut sequence,
        )?;
        require(
            Node::of(file)? == before,
            "private inode changed during actual MAC decisions",
        )?;
        self.revalidate(mac, selection)
    }
    fn request(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        file: &File,
        operation: Operation,
        argument: *mut libc::c_void,
    ) -> Result<io::Result<i32>> {
        let role = operation.role();
        self.node(mac, selection, file, role)?;
        let before = Node::of(file)?;
        let rdev = file.metadata()?.rdev();
        let mut sequence = Some(mac.loaded.av_sequence);
        access(
            &mac.loaded.root,
            BROKER,
            role.context(),
            role.class(),
            &["ioctl"],
            true,
            &mut sequence,
        )?;
        self.revalidate(mac, selection)?;
        let rc = unsafe { libc::ioctl(file.as_raw_fd(), operation.number(), argument) };
        let error = (rc < 0).then(io::Error::last_os_error);
        self.node(mac, selection, file, role)?;
        require(
            Node::of(file)? == before && file.metadata()?.rdev() == rdev,
            "actual ioctl target changed",
        )?;
        Ok(match error {
            Some(error) => Err(error),
            None => Ok(rc),
        })
    }
    pub(crate) fn get_free(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        file: &File,
    ) -> Result<u32> {
        let value = self.request(
            mac,
            selection,
            file,
            Operation::GetFree,
            std::ptr::null_mut(),
        )??;
        let index = u32::try_from(value).map_err(|_| MacError::Rejected("negative loop index"))?;
        require(index < 1_048_576, "bounded actual free loop index")?;
        Ok(index)
    }
    /// false means only an actual CONFIGURE EBUSY followed by successful MAC rechecks.
    pub(crate) fn configure(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        file: &File,
        config: &LoopConfig,
    ) -> Result<bool> {
        configured_result(self.request(
            mac,
            selection,
            file,
            Operation::Configure,
            std::ptr::from_ref(config).cast_mut().cast(),
        )?)
    }
    pub(crate) fn status(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        file: &File,
    ) -> Result<Option<LoopStatus>> {
        let mut status: LoopStatus = unsafe { std::mem::zeroed() };
        match self.request(
            mac,
            selection,
            file,
            Operation::Status,
            std::ptr::from_mut(&mut status).cast(),
        )? {
            Ok(0) => Ok(Some(status)),
            Err(error) if error.raw_os_error() == Some(libc::ENXIO) => Ok(None),
            Ok(_) => Err(MacError::Rejected("loop status result")),
            Err(error) => Err(error.into()),
        }
    }
    pub(crate) fn clear(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
        file: &File,
    ) -> Result<()> {
        require(
            self.request(mac, selection, file, Operation::Clear, std::ptr::null_mut())?? == 0,
            "loop clear result",
        )
    }
}
fn configured_result(result: io::Result<i32>) -> Result<bool> {
    match result {
        Ok(0) => Ok(true),
        Err(error) if error.raw_os_error() == Some(libc::EBUSY) => Ok(false),
        Ok(_) => Err(MacError::Rejected("loop configure result")),
        Err(error) => Err(error.into()),
    }
}
#[derive(Clone, Copy)]
enum Operation {
    GetFree,
    Configure,
    Status,
    Clear,
}
impl Operation {
    fn number(self) -> libc::c_ulong {
        match self {
            Self::GetFree => 0x4c82,
            Self::Configure => 0x4c0a,
            Self::Status => 0x4c05,
            Self::Clear => 0x4c01,
        }
    }
    fn role(self) -> PrivateLoopNode {
        match self {
            Self::GetFree => PrivateLoopNode::Control,
            _ => PrivateLoopNode::Block,
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn unlabeled_regular_file_is_not_a_private_loop_label() {
        assert!(inode_label(&tempfile::tempfile().unwrap()).is_err());
    }
    #[test]
    fn configure_busy_is_only_a_completed_driver_result() {
        assert!(configured_result(Ok(0)).unwrap());
        assert!(!configured_result(Err(io::Error::from_raw_os_error(libc::EBUSY))).unwrap());
        assert!(configured_result(Err(io::Error::from_raw_os_error(libc::EACCES))).is_err());
        assert!(configured_result(Ok(1)).is_err());
    }
    #[test]
    fn fixed_requests_match_kernel_uapi() {
        let observed: BTreeSet<_> = [
            Operation::GetFree,
            Operation::Configure,
            Operation::Status,
            Operation::Clear,
        ]
        .into_iter()
        .map(Operation::number)
        .collect();
        assert_eq!(observed, BTreeSet::from([0x4c01, 0x4c05, 0x4c0a, 0x4c82]));
        assert_eq!(Operation::GetFree.role(), PrivateLoopNode::Control);
        assert_eq!(Operation::Configure.role(), PrivateLoopNode::Block);
    }
}
