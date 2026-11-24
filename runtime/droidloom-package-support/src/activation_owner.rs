//! A first activation can publish only while its original owner proof stays live.
//! None of these objects can be deserialized. Drop deliberately preserves the
//! original failure fence; a path, inactive-unit assertion or JSON is no permit.
use super::{
    NativeRetirement, PackageConfigurationLock, Result,
    activation_files::{self as files, FileIdentity, HeldFile},
    activation_labels::Labeler,
    activation_userdata::OriginalData,
};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    fs::{self, File},
    io::Read,
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::fs::{MetadataExt, OpenOptionsExt},
    },
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

const PRODUCTION: &str = "/etc/droidloom/production";
const FENCE: &str = "/etc/droidloom/production/package-maintenance.json";
fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn open_dir(path: &Path) -> Result<File> {
    let (parent, name) = files::parent(path)?;
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    super::safe_directory(&file, super::ROOT_CUSTODY)?;
    Ok(file)
}
fn kernel_file(path: &Path, magic: libc::c_long, limit: u64) -> Result<Vec<u8>> {
    let file = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut stat) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    require(
        stat.f_type == magic,
        "kernel observation is not on its actual kernel filesystem",
    )?;
    let mut bytes = Vec::new();
    file.take(limit + 1).read_to_end(&mut bytes)?;
    require(
        bytes.len() as u64 <= limit,
        "kernel observation exceeds its fixed bound",
    )?;
    Ok(bytes)
}
fn boot_id() -> Result<Vec<u8>> {
    let raw = kernel_file(
        Path::new("/proc/sys/kernel/random/boot_id"),
        libc::PROC_SUPER_MAGIC,
        64,
    )?;
    require(
        raw.len() == 37
            && raw[36] == b'\n'
            && raw[..36].iter().enumerate().all(|(i, b)| {
                if [8, 13, 18, 23].contains(&i) {
                    *b == b'-'
                } else {
                    b.is_ascii_digit() || (b'a'..=b'f').contains(b)
                }
            }),
        "actual boot identity is malformed",
    )?;
    Ok(raw)
}
fn ns(path: &str) -> Result<File> {
    let f = File::open(path)?;
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(f.as_raw_fd(), &mut stat) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    require(
        stat.f_type == 0x6e736673,
        "namespace handle is not an actual nsfs object",
    )?;
    Ok(f)
}
fn inode(file: &File) -> Result<(u64, u64)> {
    let m = file.metadata()?;
    Ok((m.dev(), m.ino()))
}
struct Manager {
    pidfd: File,
    proc: File,
    exe: File,
    installed: File,
    identity: FileIdentity,
    sha256: String,
    namespaces: Vec<(&'static str, File)>,
    boot: Vec<u8>,
}
impl Manager {
    fn acquire() -> Result<Self> {
        super::require_root()?;
        require(
            unsafe { libc::getuid() } == 0
                && unsafe { libc::getgid() } == 0
                && unsafe { libc::getegid() } == 0,
            "first activation requires original root credentials",
        )?;
        let own_map = kernel_file(Path::new("/proc/self/uid_map"), libc::PROC_SUPER_MAGIC, 128)?;
        let tokens = std::str::from_utf8(&own_map)?
            .split_whitespace()
            .collect::<Vec<_>>();
        require(
            tokens == ["0", "0", "4294967295"],
            "first activation cannot run in a mapped user namespace",
        )?;
        let proc = fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open("/proc/1")?;
        let pidfd = super::original_actor(1)?.ok_or("original manager process missing")?;
        let fd = unsafe {
            libc::openat(
                proc.as_raw_fd(),
                c"exe".as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let exe = unsafe { File::from_raw_fd(fd) };
        let installed = files::open_regular(Path::new("/usr/lib/systemd/systemd"))?;
        let identity = FileIdentity::read(installed.metadata()?)?;
        require(
            identity.uid == 0
                && identity.gid == 0
                && identity.mode & 0o111 != 0
                && (64..=64 * 1024 * 1024).contains(&identity.bytes)
                && FileIdentity::read(exe.metadata()?)? == identity,
            "PID 1 is not the original fixed protected systemd executable",
        )?;
        let sha256 = files::hash_file(&exe, identity.bytes)?;
        let mut namespaces = Vec::new();
        for name in ["mnt", "pid", "user", "cgroup"] {
            let original = ns(&format!("/proc/1/ns/{name}"))?;
            require(
                inode(&original)? == inode(&ns(&format!("/proc/self/ns/{name}"))?)?,
                "activation and the original manager do not share their native namespaces",
            )?;
            namespaces.push((name, original));
        }
        let value = Self {
            pidfd,
            proc,
            exe,
            installed,
            identity,
            sha256,
            namespaces,
            boot: boot_id()?,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        require(
            !super::pidfd_exited(&self.pidfd)? && boot_id()? == self.boot,
            "original system manager or boot changed during activation",
        )?;
        let fd = unsafe {
            libc::openat(
                self.proc.as_raw_fd(),
                c"exe".as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let actual = unsafe { File::from_raw_fd(fd) };
        let named = files::open_regular(Path::new("/usr/lib/systemd/systemd"))?;
        for file in [&self.exe, &self.installed, &actual, &named] {
            let now = FileIdentity::read(file.metadata()?)?;
            files::no_privilege_xattrs(file)?;
            // Applying the reviewed SELinux xattr changes ctime. Keep the actual
            // executable inode, ordinary owner/mode, size and full bytes fixed.
            require(
                (
                    now.device,
                    now.inode,
                    now.mode,
                    now.uid,
                    now.gid,
                    now.links,
                    now.bytes,
                    now.modified_sec,
                    now.modified_nsec,
                ) == (
                    self.identity.device,
                    self.identity.inode,
                    self.identity.mode,
                    self.identity.uid,
                    self.identity.gid,
                    self.identity.links,
                    self.identity.bytes,
                    self.identity.modified_sec,
                    self.identity.modified_nsec,
                ) && files::hash_file(file, now.bytes)? == self.sha256,
                "original executing systemd or its installed inode changed",
            )?;
        }
        for (name, held) in &self.namespaces {
            require(
                inode(held)? == inode(&ns(&format!("/proc/1/ns/{name}"))?)?
                    && inode(held)? == inode(&ns(&format!("/proc/self/ns/{name}"))?)?,
                "original native manager namespace changed",
            )?;
        }
        Ok(())
    }
}
struct FirstFence {
    directory: File,
    directory_inode: (u64, u64),
    file: HeldFile,
}
impl FirstFence {
    fn create(plan: &str, labels: &Labeler) -> Result<Self> {
        require(
            files::valid_digest(plan),
            "invalid first activation generation",
        )?;
        // The parent setup lock is already held. Existing production directories
        // or fences are never reclaimed, even if they look old or incomplete.
        super::require_legacy()?;
        let base = open_dir(Path::new("/etc/droidloom"))?;
        if unsafe { libc::mkdirat(base.as_raw_fd(), c"production".as_ptr(), 0o755) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        base.sync_all()?;
        let directory = open_dir(Path::new(PRODUCTION))?;
        labels.apply_file(&directory, Path::new(PRODUCTION))?;
        let bytes = serde_json::to_vec_pretty(
            &json!({"schema":"droidloom-first-activation-maintenance-v1",
            "plan_sha256":plan,"operation":"first_shared_kernel_activation",
            "production_admission":"denied_until_original_transaction_commits"}),
        )?;
        let pin = files::write_new(Path::new(FENCE), &bytes, 0o400)?;
        labels.apply_file(&files::open_regular(Path::new(FENCE))?, Path::new(FENCE))?;
        directory.sync_all()?;
        let file = HeldFile::open(&pin, 4096)?;
        let value = Self {
            directory_inode: inode(&directory)?,
            directory,
            file,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        require(
            inode(&self.directory)? == self.directory_inode
                && inode(&open_dir(Path::new(PRODUCTION))?)? == self.directory_inode,
            "original first activation fence directory changed",
        )?;
        require(
            self.file.identity().uid == 0
                && self.file.identity().gid == 0
                && self.file.identity().mode & 0o7777 == 0o400,
            "first activation fence lost its sealed identity",
        )?;
        self.file.revalidate()
    }
    fn consume(self) -> Result<()> {
        self.revalidate()?;
        if unsafe {
            libc::unlinkat(
                self.directory.as_raw_fd(),
                c"package-maintenance.json".as_ptr(),
                0,
            )
        } != 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
        self.directory.sync_all()?;
        require(
            self.file.file().metadata()?.nlink() == 0,
            "original first activation fence was not actually unlinked",
        )?;
        match fs::symlink_metadata(FENCE) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
            _ => Err("a replacement maintenance fence appeared".into()),
        }
    }
}
#[repr(C)]
struct LoopInfo {
    device: u64,
    inode: u64,
    rdevice: u64,
    offset: u64,
    sizelimit: u64,
    number: u32,
    encrypt_type: u32,
    encrypt_key_size: u32,
    flags: u32,
    file_name: [u8; 64],
    crypt_name: [u8; 64],
    encrypt_key: [u8; 32],
    init: [u64; 2],
}
fn encoded_device(device: u64) -> Result<u64> {
    let major = libc::major(device);
    let minor = libc::minor(device);
    require(
        major < 4096 && minor < 1048576,
        "backing device does not fit the kernel loop ABI",
    )?;
    Ok(u64::from(
        (minor & 0xff) | (major << 8) | ((minor & !0xff) << 12),
    ))
}
fn loop_names() -> Result<BTreeSet<String>> {
    let dir = File::open("/sys/devices/virtual/block")?;
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(dir.as_raw_fd(), &mut stat) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    require(
        stat.f_type == libc::SYSFS_MAGIC,
        "loop directory is not actual sysfs",
    )?;
    let mut names = BTreeSet::new();
    for row in fs::read_dir("/sys/devices/virtual/block")? {
        let row = row?;
        let name = row
            .file_name()
            .into_string()
            .map_err(|_| "non-UTF8 block name")?;
        if let Some(n) = name.strip_prefix("loop") {
            require(
                !n.is_empty()
                    && n.bytes().all(|b| b.is_ascii_digit())
                    && (n == "0" || !n.starts_with('0')),
                "noncanonical kernel loop name",
            )?;
            names.insert(name);
        }
        require(names.len() <= 8192, "loop inventory exceeds bound")?;
    }
    Ok(names)
}
fn backing_name(name: &str) -> Result<Option<Vec<u8>>> {
    match kernel_file(
        &PathBuf::from("/sys/devices/virtual/block")
            .join(name)
            .join("loop/backing_file"),
        libc::SYSFS_MAGIC,
        4096,
    ) {
        Ok(raw) => Ok(Some(raw)),
        Err(e)
            if e.downcast_ref::<std::io::Error>()
                .is_some_and(|e| e.kind() == std::io::ErrorKind::NotFound) =>
        {
            Ok(None)
        }
        Err(e) => Err(e),
    }
}
fn no_owned_loops(original: &OriginalData) -> Result<()> {
    let expected = original
        .backing_inodes()
        .iter()
        .map(|(dev, ino)| Ok((encoded_device(*dev)?, *ino)))
        .collect::<Result<BTreeSet<_>>>()?;
    let names = loop_names()?;
    for name in &names {
        let backing = backing_name(name)?;
        if let Some(raw) = &backing {
            let raw = raw.strip_prefix(b"/").unwrap_or(raw);
            require(
                !raw.starts_with(b"var/lib/droidloom/") && !raw.starts_with(b"usr/lib/droidloom/"),
                "a legacy Droidloom image still owns an actual loop attachment",
            )?;
        }
        let index: u32 = name[4..].parse()?;
        let path = Path::new("/dev").join(name);
        let (parent, leaf) = files::parent(&path)?;
        let raw = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                leaf.as_ptr(),
                libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK,
            )
        };
        if raw < 0 {
            let e = std::io::Error::last_os_error();
            if e.kind() == std::io::ErrorKind::NotFound && backing.is_none() {
                continue;
            }
            return Err(e.into());
        }
        let file = unsafe { File::from_raw_fd(raw) };
        let m = file.metadata()?;
        require(
            m.mode() & libc::S_IFMT == libc::S_IFBLK
                && m.uid() == 0
                && libc::major(m.rdev()) == 7
                && libc::minor(m.rdev()) == index,
            "named loop device differs from the actual kernel block role",
        )?;
        let mut info: LoopInfo = unsafe { std::mem::zeroed() };
        if unsafe { libc::ioctl(file.as_raw_fd(), 0x4c05 as libc::c_ulong, &mut info) } != 0 {
            let error = std::io::Error::last_os_error();
            require(
                error.raw_os_error() == Some(libc::ENXIO) && backing.is_none(),
                "loop attachment could not be observed as actually released",
            )?;
        } else {
            require(
                info.number == index && !expected.contains(&(info.device, info.inode)),
                "original userdata still has a kernel loop owner",
            )?;
        }
        require(
            backing_name(name)? == backing,
            "loop ownership changed during observation",
        )?;
    }
    require(
        loop_names()? == names,
        "loop namespace changed during retirement verification",
    )
}
fn no_legacy_user_actors() -> Result<()> {
    // PID 1 owns user.slice and the per-user slice. systemd legitimately
    // delegates user@1000.service itself to that exact ordinary user.
    let mut chain = vec![super::cgroup_root()?];
    let mut base = PathBuf::from("/sys/fs/cgroup");
    for (name, delegated) in [
        (c"user.slice", false),
        (c"user-1000.slice", false),
        (c"user@1000.service", true),
    ] {
        let raw = unsafe {
            libc::openat(
                chain.last().unwrap().as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if raw < 0 {
            let error = std::io::Error::last_os_error();
            if error.kind() == std::io::ErrorKind::NotFound {
                return Ok(());
            }
            return Err(error.into());
        }
        let file = unsafe { File::from_raw_fd(raw) };
        let m = file.metadata()?;
        let owner = (m.uid(), m.gid());
        let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
        if unsafe { libc::fstatfs(file.as_raw_fd(), &mut stat) } != 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        require(
            m.is_dir()
                && m.mode() & 0o7022 == 0
                && (owner == (0, 0) || (delegated && owner == (1000, 1000)))
                && stat.f_type == libc::CGROUP2_SUPER_MAGIC,
            "native user cgroup is outside the fixed systemd delegation",
        )?;
        chain.push(file);
        base.push(name.to_str()?);
    }
    let mut pending = vec![base];
    let mut count = 0;
    while let Some(path) = pending.pop() {
        count += 1;
        require(count <= 4096, "native user cgroup inventory exceeds bound")?;
        for row in fs::read_dir(&path)? {
            let row = row?;
            if row.file_type()?.is_dir() {
                let name = row.file_name();
                if ["droidloom.service", "droidloom-applications.service"]
                    .iter()
                    .any(|v| name == *v)
                {
                    let bytes = kernel_file(
                        &row.path().join("cgroup.events"),
                        libc::CGROUP2_SUPER_MAGIC,
                        4096,
                    )?;
                    require(
                        !super::population(&bytes)?,
                        "a legacy user Droidloom actor remains; first native activation cannot replace it",
                    )?;
                }
                pending.push(row.path());
            }
        }
    }
    // Reopen each component from its original held parent: user ownership is
    // normal delegation, never permission to replace the observed kernel tree.
    let current_root = super::cgroup_root()?;
    require(
        inode(&current_root)? == inode(&chain[0])?,
        "native cgroup root changed during user-actor observation",
    )?;
    for (index, name) in [c"user.slice", c"user-1000.slice", c"user@1000.service"]
        .into_iter()
        .enumerate()
    {
        let raw = unsafe {
            libc::openat(
                chain[index].as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if raw < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let named = unsafe { File::from_raw_fd(raw) };
        let a = chain[index + 1].metadata()?;
        let b = named.metadata()?;
        require(
            (a.dev(), a.ino(), a.mode(), a.uid(), a.gid())
                == (b.dev(), b.ino(), b.mode(), b.uid(), b.gid()),
            "original delegated user cgroup changed during observation",
        )?;
    }
    Ok(())
}

pub(super) struct DataLabelPermit<'a> {
    lock: &'a PackageConfigurationLock,
    manager: &'a Manager,
    native: &'a NativeRetirement,
    fence: &'a FirstFence,
    inodes: [(u64, u64); 2],
}
impl DataLabelPermit<'_> {
    pub(super) fn revalidate(&self, original: &OriginalData) -> Result<()> {
        self.lock.revalidate()?;
        self.fence.revalidate()?;
        self.manager.revalidate()?;
        self.native
            .revalidate(Instant::now() + Duration::from_secs(30))?;
        require(
            original.backing_inodes() == self.inodes,
            "userdata label permit crossed original objects",
        )?;
        original.revalidate_data()?;
        no_owned_loops(original)?;
        no_legacy_user_actors()
    }
}

pub(super) struct InstallationPermit {
    lock: PackageConfigurationLock,
    manager: Manager,
    native: NativeRetirement,
    original: OriginalData,
    fence: FirstFence,
    plan: String,
    published: Option<[HeldFile; 3]>,
}
impl InstallationPermit {
    pub(super) fn retire(original: OriginalData, plan: &str, labels: &Labeler) -> Result<Self> {
        super::require_root()?;
        require(files::valid_digest(plan), "invalid first activation plan")?;
        let mut lock = super::setup_lock()?;
        lock.revalidate()?;
        super::require_legacy()?;
        original.revalidate()?;
        // An existing launcher with no private selection is ambiguous. It is not
        // treated as the ordinary first-install state.
        match fs::symlink_metadata("/etc/droidloom/container-launcher.json") {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
            _ => {
                return Err(
                    "first activation requires absence of an earlier launcher publication".into(),
                );
            }
        }
        let manager = Manager::acquire()?;
        no_legacy_user_actors()?;
        let fence = FirstFence::create(plan, labels)?;
        lock.seal_first_activation_label(&fence.file.read_all(4096)?)?;
        lock.revalidate()?;
        fence.revalidate()?;
        manager.revalidate()?;
        let native =
            super::retain_native_retirement(Instant::now() + Duration::from_secs(120), None, true)?;
        original.revalidate()?;
        no_owned_loops(&original)?;
        let result = Self {
            lock,
            manager,
            native,
            original,
            fence,
            plan: plan.into(),
            published: None,
        };
        result.revalidate()?;
        Ok(result)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.lock.revalidate()?;
        self.fence.revalidate()?;
        self.manager.revalidate()?;
        self.native
            .revalidate(Instant::now() + Duration::from_secs(30))?;
        no_legacy_user_actors()?;
        if let Some(files) = &self.published {
            for file in files {
                file.revalidate()?;
            }
        } else {
            self.original.original_cell().revalidate()?;
        }
        self.original.revalidate_data()?;
        no_owned_loops(&self.original)
    }
    pub(super) fn label_userdata(&mut self, labels: &Labeler) -> Result<Value> {
        self.revalidate()?;
        let gate = DataLabelPermit {
            lock: &self.lock,
            manager: &self.manager,
            native: &self.native,
            fence: &self.fence,
            inodes: self.original.backing_inodes(),
        };
        let value = self.original.apply_labels(labels, &gate)?;
        self.revalidate()?;
        Ok(value)
    }
    pub(super) fn original(&self) -> &OriginalData {
        &self.original
    }
    pub(super) fn plan(&self) -> &str {
        &self.plan
    }
    pub(super) fn receipt(&self) -> Value {
        json!({"schema":"droidloom-first-activation-owner-observation-v1","plan_sha256":self.plan,
            "original_boot_id":String::from_utf8_lossy(&self.manager.boot).trim(),
            "native_originals":self.native.observation(),"original_userdata":self.original.receipt(),
            "fence":self.fence.file.pin(),"original_owner_retired":true,
            "production_ready":false})
    }
    pub(super) fn publish_configuration(
        &mut self,
        staged: &super::activation_android::StagedSelection,
        backup: &Path,
        labels: &Labeler,
    ) -> Result<super::activation_android::CommittedSelection> {
        self.revalidate()?;
        require(
            self.published.is_none(),
            "selection was already published by this transaction",
        )?;
        let pins = staged.files();
        let root = Path::new("/var/lib/droidloom/activation-staging")
            .join(&self.plan)
            .join("root");
        for (pin, relative) in pins.iter().zip([
            "etc/droidloom/cell.json",
            "etc/droidloom/production/selected.json",
            "etc/droidloom/container-launcher.json",
        ]) {
            require(
                pin.path == root.join(relative),
                "configuration publication crossed the original permit generation",
            )?;
        }
        let cell = super::activation_commit::replace_file(
            &HeldFile::open(&pins[0], 1024 * 1024)?,
            Path::new("/etc/droidloom/cell.json"),
            &backup.join("cell.json"),
            0o644,
            Some(labels),
        )?;
        let selected = super::activation_commit::publish_new_file(
            &HeldFile::open(&pins[1], 16 * 1024)?,
            Path::new("/etc/droidloom/production/selected.json"),
            0o400,
            Some(labels),
        )?;
        let launcher = super::activation_commit::publish_new_file(
            &HeldFile::open(&pins[2], 16 * 1024)?,
            Path::new("/etc/droidloom/container-launcher.json"),
            0o644,
            Some(labels),
        )?;
        let files = [
            HeldFile::open(&cell, 1024 * 1024)?,
            HeldFile::open(&selected, 16 * 1024)?,
            HeldFile::open(&launcher, 16 * 1024)?,
        ];
        let selection = staged.observe_committed(&files)?;
        self.published = Some(files);
        self.revalidate()?;
        selection.revalidate()?;
        Ok(selection)
    }
    pub(super) fn finish(
        self,
        boot: &super::activation_boot::CommittedBoot,
        selection: &super::activation_android::CommittedSelection,
    ) -> Result<()> {
        self.revalidate()?;
        require(
            self.published.is_some(),
            "installation has no committed selection",
        )?;
        selection.revalidate()?;
        boot.revalidate()?;
        // Only the original fence created by this exact first transaction is
        // consumed. There is no generic unfence/remove-override operation.
        self.fence.consume()
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn loop_identity_uses_actual_kernel_dev_encoding() {
        assert_eq!(std::mem::size_of::<LoopInfo>(), 232);
        assert_eq!(encoded_device(libc::makedev(259, 2)).unwrap(), 66306);
        assert_eq!(encoded_device(libc::makedev(8, 257)).unwrap(), 0x100801);
        assert_ne!(
            encoded_device(libc::makedev(259, 2)).unwrap(),
            encoded_device(libc::makedev(259, 3)).unwrap()
        );
    }
    #[test]
    fn original_pidfd_observes_its_own_exit_without_accepting_a_pid_number() {
        struct Owned(std::process::Child);
        impl Drop for Owned {
            fn drop(&mut self) {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
        let mut child = Owned(
            std::process::Command::new("/usr/bin/sleep")
                .arg("30")
                .spawn()
                .unwrap(),
        );
        let held = super::super::original_actor(child.0.id()).unwrap().unwrap();
        assert!(!super::super::pidfd_exited(&held).unwrap());
        child.0.kill().unwrap();
        child.0.wait().unwrap();
        assert!(super::super::pidfd_exited(&held).unwrap());
    }
}

pub(super) fn preflight(original: &OriginalData) -> Result<Value> {
    original.revalidate()?;
    let manager = Manager::acquire()?;
    no_legacy_user_actors()?;
    no_owned_loops(original)?;
    let root = super::cgroup_root()?;
    let deadline = Instant::now() + Duration::from_secs(30);
    let mut rows = Vec::new();
    for unit in [
        super::NativeUnit::Production,
        super::NativeUnit::ManagerLabel,
        super::NativeUnit::Legacy,
        super::NativeUnit::Factory,
        super::NativeUnit::Launcher,
        super::NativeUnit::Observer,
        super::NativeUnit::Calibration,
    ] {
        let state = super::inspect_unit(unit, deadline)?;
        super::terminal_unit(&state, &state)?;
        let group = super::HeldCgroup::capture(&root, unit, &state)?;
        group.verify_retired(&state)?;
        let again = super::inspect_unit(unit, deadline)?;
        super::same_stop_generation(&state, &again)?;
        group.verify_retired(&again)?;
        rows.push(
            json!({"unit":unit.name(),"load":state.load,"active":state.active,
            "sub":state.sub,"original_invocation":state.invocation,"actual_cgroup_retired":true}),
        );
    }
    original.revalidate()?;
    manager.revalidate()?;
    no_owned_loops(original)?;
    Ok(
        json!({"schema":"droidloom-first-activation-owner-preflight-v1",
        "actual_boot_id":String::from_utf8_lossy(&manager.boot).trim(),"native_units":rows,
        "original_userdata_loop_attachments":0,"legacy_user_actors":0,
        "services_stopped":false,"fence_created":false,"installation_authority_issued":false}),
    )
}
