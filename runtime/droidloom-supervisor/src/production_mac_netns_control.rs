//! Finite detached control alias for the built-in p4_lsm_context driver.
//! No host /dev inode is opened, relabeled or used as a fallback. The two
//! automatic transitions and both actual inode labels are mandatory. No
//! control, filesystem or namespace FD is exported outside this MAC owner.
//! SET is immutable state in the separately owned netns: closing this alias
//! never claims to undo SET or to prove the original tree has retired.
use super::netns_provider::{NamespaceIdentity, namespace};
use super::*;

const DIRECTORY: &CStr = c"droidloom-context";
const CONTROL: &CStr = c"p4_lsm_context";
const DIRECTORY_CONTEXT: &str = "u:object_r:droidloom_lsm_context_dir:s0";
const CONTROL_CONTEXT: &str = "u:object_r:droidloom_lsm_context_device:s0";
const TMPFS: u64 = 0x0102_1994;
const MAX_MOUNTS: usize = 16 * 1024 * 1024;
const SET: libc::c_ulong = 0x4020_b701;
const GET: libc::c_ulong = 0xc020_b702;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum SetOutcome {
    NotAttempted,
    Entered,
    Applied,
    Rejected(i32),
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Stage {
    Prepared,
    Creating,
    Live,
    Closing,
    Closed,
}
#[repr(C)]
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Request {
    size: u32,
    version: u32,
    netns_fd: i32,
    lsm_id: u32,
    expected_ns_inum: u64,
    flags: u32,
    reserved: u32,
}
const _: () = assert!(std::mem::size_of::<Request>() == 32 && std::mem::align_of::<Request>() == 8);
#[cfg(test)]
pub(super) fn request_for_test(netns_fd: RawFd, expected_ns_inum: u64) -> impl Sized {
    Request {
        size: 32,
        version: 1,
        netns_fd,
        lsm_id: 101,
        expected_ns_inum,
        flags: 0,
        reserved: 0,
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) struct SelectorState {
    pub(super) lsm_id: u32,
    pub(super) flags: u32,
}

fn file(rc: libc::c_long) -> Result<File> {
    if rc < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let raw =
        i32::try_from(rc).map_err(|_| MacError::Rejected("private context descriptor overflow"))?;
    Ok(unsafe { File::from_raw_fd(raw) })
}
fn zero(rc: libc::c_long) -> Result<()> {
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error().into())
    }
}
fn duplicate(source: &File) -> Result<File> {
    file(unsafe { libc::fcntl(source.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 3) } as libc::c_long)
}
fn fs(file: &File) -> Result<(libc::statfs, [u8; 8], u64)> {
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    zero(unsafe { libc::fstatfs(file.as_raw_fd(), &mut stat) } as libc::c_long)?;
    const _: () = assert!(std::mem::size_of::<libc::fsid_t>() == 8);
    let id = unsafe { std::mem::transmute::<libc::fsid_t, [u8; 8]>(stat.f_fsid) };
    let mut v: libc::statvfs = unsafe { std::mem::zeroed() };
    zero(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut v) } as libc::c_long)?;
    Ok((stat, id, v.f_flag as u64))
}
fn mount_id(file: &File) -> Result<u64> {
    let mut s: libc::statx = unsafe { std::mem::zeroed() };
    zero(unsafe {
        libc::syscall(
            libc::SYS_statx,
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH,
            0x1000_u32,
            &mut s,
        )
    })?;
    require(
        s.stx_mask & 0x1000 != 0 && s.stx_mnt_id > 0,
        "actual private context mount ID",
    )?;
    Ok(s.stx_mnt_id)
}
fn absent_mount(raw: &[u8], id: u64) -> Result<()> {
    require(
        !raw.is_empty() && raw.len() <= MAX_MOUNTS && raw.ends_with(b"\n"),
        "complete bounded host mount inventory",
    )?;
    let text =
        std::str::from_utf8(raw).map_err(|_| MacError::Rejected("mount inventory encoding"))?;
    let mut ids = BTreeSet::new();
    for row in text.lines() {
        let parts: Vec<_> = row.split_ascii_whitespace().collect();
        require(
            parts.len() >= 10 && parts.iter().filter(|v| **v == "-").count() == 1,
            "complete host mount inventory row",
        )?;
        let value = parts[0]
            .parse::<u64>()
            .map_err(|_| MacError::Rejected("mount inventory ID"))?;
        require(
            value > 0 && value != id && ids.insert(value),
            "private context mount is attached or inventory repeated",
        )?;
    }
    Ok(())
}
fn host_mount_namespace() -> Result<File> {
    // Only the fixed current-thread kernel namespace link is followed.
    let file = File::open("/proc/thread-self/ns/mnt")?;
    namespace(&file, libc::CLONE_NEWNS)?;
    Ok(file)
}
fn detached(mount: &File, expected: u64) -> Result<()> {
    require(
        mount_id(mount)? == expected,
        "same original private context mount",
    )?;
    let f = open_at(
        libc::AT_FDCWD,
        c"/proc/thread-self/mountinfo",
        libc::O_RDONLY,
    )?;
    require(
        kind(&f)? == PROC_MAGIC,
        "actual host thread mount inventory",
    )?;
    absent_mount(&bounded(&f, MAX_MOUNTS)?, expected)?;
    require(
        mount_id(mount)? == expected,
        "private mount changed during complete inventory",
    )
}
fn bounded_tmpfs(mount: &File) -> Result<[u8; 8]> {
    let (s, id, flags) = fs(mount)?;
    require(
        s.f_type as u64 == TMPFS
            && s.f_bsize > 0
            && (s.f_blocks as u64).checked_mul(s.f_bsize as u64) == Some(65536)
            && s.f_files == 8
            && flags & 15 == 10,
        "private context tmpfs must be 64KiB/eight inodes, nosuid/noexec with devices enabled",
    )?;
    Ok(id)
}
fn label(file: &File, expected: &str) -> Result<()> {
    let before = Node::of(file)?;
    let mut raw = [0_u8; 1024];
    let n = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            raw.as_mut_ptr().cast(),
            raw.len(),
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        n > 0
            && n as usize <= raw.len()
            && context_matches(&raw[..n as usize], expected)
            && Node::of(file)? == before,
        "actual automatic private context inode label differs",
    )
}
fn names(directory: &File) -> Result<BTreeSet<Vec<u8>>> {
    let file = open_at(
        directory.as_raw_fd(),
        c".",
        libc::O_RDONLY | libc::O_DIRECTORY,
    )?;
    let raw = unsafe { libc::fdopendir(file.as_raw_fd()) };
    if raw.is_null() {
        return Err(io::Error::last_os_error().into());
    }
    std::mem::forget(file);
    struct Stream(*mut libc::DIR);
    impl Drop for Stream {
        fn drop(&mut self) {
            unsafe {
                libc::closedir(self.0);
            }
        }
    }
    let stream = Stream(raw);
    let mut values = BTreeSet::new();
    let mut count = 0;
    loop {
        unsafe {
            *libc::__errno_location() = 0;
        }
        let entry = unsafe { libc::readdir(stream.0) };
        if entry.is_null() {
            let e = io::Error::last_os_error();
            if e.raw_os_error() != Some(0) {
                return Err(e.into());
            }
            break;
        }
        count += 1;
        require(count <= 8, "bounded finite private control directory")?;
        let raw = unsafe { &(*entry).d_name };
        let n = raw
            .iter()
            .position(|v| *v == 0)
            .ok_or(MacError::Rejected("private directory name terminator"))?;
        let name: Vec<u8> = raw[..n].iter().map(|v| *v as u8).collect();
        if name == b"." || name == b".." {
            continue;
        }
        require(
            !name.is_empty() && !name.contains(&b'/') && values.insert(name),
            "unique private context directory entry",
        )?;
    }
    Ok(values)
}
pub(super) fn parse_device(raw: &[u8]) -> Result<u32> {
    require(
        !raw.is_empty() && raw.len() <= 32 && raw.ends_with(b"\n"),
        "complete fixed misc-device sysfs record",
    )?;
    let body = std::str::from_utf8(&raw[..raw.len() - 1])
        .map_err(|_| MacError::Rejected("misc-device number encoding"))?;
    let (major, minor) = body
        .split_once(':')
        .ok_or(MacError::Rejected("misc-device major/minor separator"))?;
    require(
        major == "10"
            && !minor.is_empty()
            && minor.len() <= 7
            && minor.bytes().all(|v| v.is_ascii_digit())
            && (minor.len() == 1 || !minor.starts_with('0')),
        "canonical fixed misc-device number",
    )?;
    let minor = minor
        .parse::<u32>()
        .map_err(|_| MacError::Rejected("misc-device minor overflow"))?;
    require(minor < (1 << 20), "Linux misc-device minor bound")?;
    Ok(minor)
}
fn driver_minor() -> Result<u32> {
    let f = open_at(
        libc::AT_FDCWD,
        c"/sys/devices/virtual/misc/p4_lsm_context/dev",
        libc::O_RDONLY,
    )?;
    let before = Node::of(&f)?;
    require(
        kind(&f)? == SYSFS_MAGIC
            && before.mode & libc::S_IFMT == libc::S_IFREG
            && before.uid == 0
            && before.gid == 0,
        "actual fixed built-in context driver sysfs publication",
    )?;
    let minor = parse_device(&bounded(&f, 32)?)?;
    require(
        Node::of(&f)? == before,
        "fixed context driver publication changed",
    )?;
    Ok(minor)
}
fn creation_decisions(mac: &MacPreflight) -> Result<()> {
    let mut seq = Some(mac.loaded.av_sequence);
    access(
        &mac.loaded.root,
        BROKER,
        BROKER,
        "capability",
        &["sys_admin", "mknod"],
        true,
        &mut seq,
    )?;
    access(
        &mac.loaded.root,
        BROKER,
        "u:object_r:tmpfs:s0",
        "filesystem",
        &["mount", "getattr"],
        true,
        &mut seq,
    )?;
    access(
        &mac.loaded.root,
        BROKER,
        "u:object_r:tmpfs:s0",
        "dir",
        &["getattr", "open", "read", "search", "write", "add_name"],
        true,
        &mut seq,
    )?;
    for target in [DIRECTORY_CONTEXT, CONTROL_CONTEXT] {
        access(
            &mac.loaded.root,
            target,
            "u:object_r:tmpfs:s0",
            "filesystem",
            &["associate"],
            true,
            &mut seq,
        )?;
    }
    access(
        &mac.loaded.root,
        BROKER,
        DIRECTORY_CONTEXT,
        "dir",
        &[
            "create", "getattr", "open", "read", "search", "write", "add_name",
        ],
        true,
        &mut seq,
    )?;
    access(
        &mac.loaded.root,
        BROKER,
        CONTROL_CONTEXT,
        "chr_file",
        &["create", "getattr", "open", "read", "ioctl"],
        true,
        &mut seq,
    )
}
/// Constructed read-only, then retained in the original network guard before
/// any fsopen/mkdir/mknod. Every successful syscall's resource is journaled
/// before the next fallible check, including a successful immutable SET.
pub(super) struct PrivateNetnsControl {
    provider: ProviderBinding,
    creator: i64,
    host_mnt: File,
    host_mnt_id: NamespaceIdentity,
    target: Option<File>,
    target_id: NamespaceIdentity,
    minor: u32,
    context: Option<File>,
    context_created: bool,
    mount: Option<File>,
    root: Option<File>,
    directory: Option<File>,
    control: Option<File>,
    directory_created: bool,
    control_created: bool,
    mount_id: Option<u64>,
    fsid: Option<[u8; 8]>,
    root_stamp: Option<Node>,
    dir_stamp: Option<Node>,
    control_stamp: Option<Node>,
    stage: Stage,
    set_outcome: SetOutcome,
    _same_thread: PhantomData<Rc<()>>,
}
impl PrivateNetnsControl {
    pub(super) fn prepare(
        mac: &MacPreflight,
        selection: &ProductionSelection,
        target: &File,
        id: NamespaceIdentity,
    ) -> Result<Self> {
        mac.revalidate(selection)?;
        require(
            mac.scoped_contexts(),
            "private selector requires actual scoped host route",
        )?;
        self_attr::require_no_fscreate()?;
        creation_decisions(mac)?;
        require(
            namespace(target, libc::CLONE_NEWNET)? == id,
            "original private-selector target namespace",
        )?;
        let target = duplicate(target)?;
        let host_mnt = host_mount_namespace()?;
        let host_mnt_id = namespace(&host_mnt, libc::CLONE_NEWNS)?;
        let minor = driver_minor()?;
        let creator = unsafe { libc::syscall(libc::SYS_gettid) };
        require(
            creator == mac.loaded.tid as i64,
            "original private-selector creator thread",
        )?;
        let value = Self {
            provider: mac.binding(),
            creator,
            host_mnt,
            host_mnt_id,
            target: Some(target),
            target_id: id,
            minor,
            context: None,
            context_created: false,
            mount: None,
            root: None,
            directory: None,
            control: None,
            directory_created: false,
            control_created: false,
            mount_id: None,
            fsid: None,
            root_stamp: None,
            dir_stamp: None,
            control_stamp: None,
            stage: Stage::Prepared,
            set_outcome: SetOutcome::NotAttempted,
            _same_thread: PhantomData,
        };
        value.original(mac, selection)?;
        Ok(value)
    }
    fn original(&self, mac: &MacPreflight, selection: &ProductionSelection) -> Result<()> {
        mac.revalidate(selection)?;
        require(
            mac.binding() == self.provider
                && unsafe { libc::syscall(libc::SYS_gettid) } == self.creator,
            "private context alias belongs to another original MAC creator",
        )?;
        self_attr::require_no_fscreate()?;
        require(
            namespace(&self.host_mnt, libc::CLONE_NEWNS)? == self.host_mnt_id
                && namespace(&host_mount_namespace()?, libc::CLONE_NEWNS)? == self.host_mnt_id,
            "private context creator left its original mount namespace",
        )?;
        let target = self
            .target
            .as_ref()
            .ok_or(MacError::Rejected("private context target already retired"))?;
        require(
            namespace(target, libc::CLONE_NEWNET)? == self.target_id
                && driver_minor()? == self.minor,
            "original private context target/driver changed",
        )?;
        creation_decisions(mac)?;
        mac.revalidate(selection)
    }
    pub(super) fn create(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        require(
            self.stage == Stage::Prepared,
            "private context creation cannot be replayed",
        )?;
        self.original(mac, selection)?;
        self.stage = Stage::Creating;
        self.context = Some(file(unsafe {
            libc::syscall(libc::SYS_fsopen, c"tmpfs".as_ptr(), 1_u32)
        })?);
        let context = self.context.as_ref().unwrap();
        for (key, value) in [
            (c"mode", c"0700"),
            (c"uid", c"0"),
            (c"gid", c"0"),
            (c"size", c"65536"),
            (c"nr_inodes", c"8"),
        ] {
            zero(unsafe {
                libc::syscall(
                    libc::SYS_fsconfig,
                    context.as_raw_fd(),
                    1_u32,
                    key.as_ptr(),
                    value.as_ptr(),
                    0,
                )
            })?;
        }
        zero(unsafe {
            libc::syscall(
                libc::SYS_fsconfig,
                context.as_raw_fd(),
                6_u32,
                std::ptr::null::<libc::c_char>(),
                std::ptr::null::<libc::c_char>(),
                0,
            )
        })?;
        self.context_created = true;
        self.mount = Some(file(unsafe {
            libc::syscall(libc::SYS_fsmount, context.as_raw_fd(), 1_u32, 2_u32 | 8_u32)
        })?);
        let mount = self.mount.as_ref().unwrap();
        self.mount_id = Some(mount_id(mount)?);
        self.fsid = Some(bounded_tmpfs(mount)?);
        detached(mount, self.mount_id.unwrap())?;
        self.root = Some(open_at(
            mount.as_raw_fd(),
            c".",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?);
        let root = self.root.as_ref().unwrap();
        let before = Node::of(root)?;
        require(
            before == Node::of(mount)?
                && before.mode == libc::S_IFDIR | 0o700
                && before.uid == 0
                && before.gid == 0
                && names(root)?.is_empty(),
            "original fresh bounded context tmpfs root",
        )?;
        label(root, "u:object_r:tmpfs:s0")?;
        self.original(mac, selection)?;
        zero(
            unsafe { libc::mkdirat(root.as_raw_fd(), DIRECTORY.as_ptr(), 0o700) } as libc::c_long,
        )?;
        self.directory_created = true;
        self.directory = Some(open_at(
            root.as_raw_fd(),
            DIRECTORY,
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?);
        let directory = self.directory.as_ref().unwrap();
        let d = Node::of(directory)?;
        require(
            d.dev == before.dev
                && d.mode == libc::S_IFDIR | 0o700
                && d.uid == 0
                && d.gid == 0
                && d.links == 2
                && names(directory)?.is_empty(),
            "actual new fixed private context directory",
        )?;
        label(directory, DIRECTORY_CONTEXT)?;
        self.original(mac, selection)?;
        zero(unsafe {
            libc::mknodat(
                directory.as_raw_fd(),
                CONTROL.as_ptr(),
                libc::S_IFCHR | 0o600,
                libc::makedev(10, self.minor),
            )
        } as libc::c_long)?;
        self.control_created = true;
        self.control = Some(open_at(directory.as_raw_fd(), CONTROL, libc::O_RDONLY)?);
        self.root_stamp = Some(Node::of(root)?);
        self.dir_stamp = Some(Node::of(directory)?);
        self.control_stamp = Some(Node::of(self.control.as_ref().unwrap())?);
        self.layout()?;
        self.original(mac, selection)?;
        self.stage = Stage::Live;
        Ok(())
    }
    fn layout(&self) -> Result<()> {
        let mount = self
            .mount
            .as_ref()
            .ok_or(MacError::Rejected("private context mount absent"))?;
        let root = self
            .root
            .as_ref()
            .ok_or(MacError::Rejected("private context root absent"))?;
        let directory = self
            .directory
            .as_ref()
            .ok_or(MacError::Rejected("private context directory absent"))?;
        let control = self
            .control
            .as_ref()
            .ok_or(MacError::Rejected("private context control absent"))?;
        let id = self
            .mount_id
            .ok_or(MacError::Rejected("private context mount identity absent"))?;
        let root_stamp = self
            .root_stamp
            .ok_or(MacError::Rejected("private context root identity absent"))?;
        let dir_stamp = self.dir_stamp.ok_or(MacError::Rejected(
            "private context directory identity absent",
        ))?;
        let control_stamp = self.control_stamp.ok_or(MacError::Rejected(
            "private context control identity absent",
        ))?;
        require(
            self.context_created
                && self.directory_created
                && self.control_created
                && Node::of(root)? == root_stamp
                && Node::of(mount)? == root_stamp
                && Node::of(directory)? == dir_stamp
                && Node::of(control)? == control_stamp
                && bounded_tmpfs(root)? == self.fsid.unwrap(),
            "complete original private context resource identities",
        )?;
        require(
            root_stamp.mode == libc::S_IFDIR | 0o700
                && root_stamp.uid == 0
                && root_stamp.gid == 0
                && root_stamp.links == 3
                && dir_stamp.dev == root_stamp.dev
                && dir_stamp.mode == libc::S_IFDIR | 0o700
                && dir_stamp.uid == 0
                && dir_stamp.gid == 0
                && dir_stamp.links == 2
                && control_stamp.dev == root_stamp.dev
                && control_stamp.mode == libc::S_IFCHR | 0o600
                && control_stamp.uid == 0
                && control_stamp.gid == 0
                && control_stamp.links == 1
                && control.metadata()?.rdev() == libc::makedev(10, self.minor),
            "actual private context types/modes/credentials/dev_t",
        )?;
        for file in [root, directory, control] {
            require(
                mount_id(file)? == id,
                "private context files crossed original mount",
            )?;
        }
        detached(mount, id)?;
        require(
            names(root)? == BTreeSet::from([DIRECTORY.to_bytes().to_vec()])
                && names(directory)? == BTreeSet::from([CONTROL.to_bytes().to_vec()]),
            "complete exact private context two-name inventory",
        )?;
        let named_dir = open_at(
            root.as_raw_fd(),
            DIRECTORY,
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let named_ctrl = open_at(directory.as_raw_fd(), CONTROL, libc::O_RDONLY)?;
        require(
            Node::of(&named_dir)? == dir_stamp
                && Node::of(&named_ctrl)? == control_stamp
                && named_ctrl.metadata()?.rdev() == libc::makedev(10, self.minor),
            "original private context names replaced",
        )?;
        for (file, name) in [
            (root, "u:object_r:tmpfs:s0"),
            (directory, DIRECTORY_CONTEXT),
            (control, CONTROL_CONTEXT),
        ] {
            label(file, name)?;
        }
        require(
            Node::of(root)? == root_stamp
                && Node::of(directory)? == dir_stamp
                && Node::of(control)? == control_stamp,
            "original private context layout changed during complete observation",
        )
    }
    pub(super) fn revalidate(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        require(
            self.stage == Stage::Live,
            "private context alias has no active complete creation",
        )?;
        self.original(mac, selection)?;
        self.layout()?;
        self.original(mac, selection)
    }
    fn request(&self, set: bool) -> Result<Request> {
        let target = self
            .target
            .as_ref()
            .ok_or(MacError::Rejected("original context namespace retired"))?;
        Ok(Request {
            size: 32,
            version: 1,
            netns_fd: target.as_raw_fd(),
            lsm_id: if set { 101 } else { 0 },
            expected_ns_inum: self.target_id.node.ino,
            flags: 0,
            reserved: 0,
        })
    }
    pub(super) fn get(
        &self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<SelectorState> {
        self.revalidate(mac, selection)?;
        let mut request = self.request(false)?;
        let before = request;
        let control = self.control.as_ref().unwrap();
        zero(unsafe { libc::ioctl(control.as_raw_fd(), GET, &mut request) } as libc::c_long)?;
        require(
            request.size == before.size
                && request.version == before.version
                && request.netns_fd == before.netns_fd
                && request.expected_ns_inum == before.expected_ns_inum
                && request.reserved == 0
                && request.flags & !3 == 0,
            "exact complete original private selector GET result",
        )?;
        self.revalidate(mac, selection)?;
        Ok(SelectorState {
            lsm_id: request.lsm_id,
            flags: request.flags,
        })
    }
    pub(super) fn set(
        &mut self,
        mac: &MacPreflight,
        selection: &ProductionSelection,
    ) -> Result<()> {
        require(
            self.set_outcome == SetOutcome::NotAttempted,
            "original private selector SET cannot be retried",
        )?;
        self.revalidate(mac, selection)?;
        let mut request = self.request(true)?;
        let before = request;
        self.set_outcome = SetOutcome::Entered;
        let rc = unsafe {
            libc::ioctl(
                self.control.as_ref().unwrap().as_raw_fd(),
                SET,
                &mut request,
            )
        };
        if rc != 0 {
            let error = io::Error::last_os_error();
            self.set_outcome = SetOutcome::Rejected(error.raw_os_error().unwrap_or(libc::EIO));
            return Err(error.into());
        }
        // Record the actual syscall result BEFORE any post-ioctl observation.
        self.set_outcome = SetOutcome::Applied;
        require(
            request == before,
            "private selector SET unexpectedly modified the original request",
        )?;
        self.revalidate(mac, selection)
    }
    pub(super) fn set_outcome(&self) -> SetOutcome {
        self.set_outcome
    }
    /// Close only this object's original never-exported detached resources.
    /// No unlink by a guessed name, host mutation, SET rollback or namespace
    /// destruction claim is made. The outer original tree owner still retires
    /// the netns and every process/socket that may retain it.
    pub(super) fn retire(&mut self) -> Result<()> {
        require(
            unsafe { libc::syscall(libc::SYS_gettid) } == self.creator,
            "private context retirement must keep original thread",
        )?;
        if self.stage == Stage::Closed {
            return Ok(());
        }
        require(
            namespace(&self.host_mnt, libc::CLONE_NEWNS)? == self.host_mnt_id
                && namespace(&host_mount_namespace()?, libc::CLONE_NEWNS)? == self.host_mnt_id,
            "original context mount namespace changed before retirement",
        )?;
        if self.stage == Stage::Live {
            self.layout()?;
        }
        if let Some(mount) = &self.mount {
            let id = mount_id(mount)?;
            require(
                self.mount_id.is_none_or(|v| v == id),
                "partial context creation lost original mount",
            )?;
            bounded_tmpfs(mount)?;
            detached(mount, id)?;
        }
        self.stage = Stage::Closing;
        self.control.take();
        self.directory.take();
        self.root.take();
        self.mount.take();
        self.context.take();
        self.target.take();
        self.stage = Stage::Closed;
        Ok(())
    }
}
impl Drop for PrivateNetnsControl {
    fn drop(&mut self) {
        if self.stage != Stage::Closed && self.stage != Stage::Prepared {
            // The outer pending/selected resource must explicitly retire. Incomplete
            // creation or SET is not converted to cleanup by losing the Rust handle.
            for file in [
                &mut self.control,
                &mut self.directory,
                &mut self.root,
                &mut self.mount,
                &mut self.context,
                &mut self.target,
            ] {
                if let Some(file) = file.take() {
                    std::mem::forget(file);
                }
            }
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn private_selector_mount_inventory_refuses_attached_or_ambiguous_mounts() {
        let raw = b"1 0 0:1 / / rw - tmpfs tmpfs rw\n2 1 0:2 / /proc ro - proc proc rw\n";
        absent_mount(raw, 99).unwrap();
        assert!(absent_mount(raw, 1).is_err());
        assert!(
            absent_mount(
                b"1 0 0:1 / / rw - tmpfs tmpfs rw\n1 0 0:1 / / rw - tmpfs tmpfs rw\n",
                99
            )
            .is_err()
        );
        assert!(absent_mount(b"1 0 0:1 / / rw - tmpfs tmpfs rw", 99).is_err());
    }
    #[test]
    fn ordinary_file_cannot_be_a_bounded_private_selector_mount() {
        let file = tempfile::tempfile().unwrap();
        assert!(bounded_tmpfs(&file).is_err());
        assert!(namespace(&file, libc::CLONE_NEWNET).is_err());
    }
}
