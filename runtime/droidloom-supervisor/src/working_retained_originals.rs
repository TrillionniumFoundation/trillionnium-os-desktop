//! Actual read-only custody of the two preserved original images.
//! The comparison spec cannot construct this lease. Only the current enforcing
//! helper, with a freshly observed working Main, can open and retain it.
use crate::control::MainCustodyObservation;
use crate::main_custody::RuntimeMainCustody;
use crate::native_working_contract::retained_data as c;
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    ffi::{CStr, CString},
    fs::{self, File, Metadata, OpenOptions},
    io,
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{
            ffi::OsStrExt,
            fs::{FileExt, MetadataExt, OpenOptionsExt},
        },
    },
    path::PathBuf,
    time::{Duration, Instant},
};
fn reject(why: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why.into())
}
fn identity(m: &Metadata) -> c::Identity {
    c::Identity {
        dev: m.dev(),
        ino: m.ino(),
        mode: m.mode(),
        uid: m.uid(),
        gid: m.gid(),
        nlink: m.nlink(),
        size: m.len(),
        mtime_sec: m.mtime(),
        mtime_nsec: m.mtime_nsec(),
        ctime_sec: m.ctime(),
        ctime_nsec: m.ctime_nsec(),
    }
}
fn stable(i: &c::Identity) -> [u64; 7] {
    [
        i.dev,
        i.ino,
        u64::from(i.mode),
        u64::from(i.uid),
        u64::from(i.gid),
        i.nlink,
        i.size,
    ]
}
fn open_at(parent: i32, name: &CStr, directory: bool) -> io::Result<File> {
    let flags = libc::O_RDONLY
        | libc::O_NOFOLLOW
        | libc::O_CLOEXEC
        | libc::O_NONBLOCK
        | libc::O_NOATIME
        | if directory { libc::O_DIRECTORY } else { 0 };
    let fd = unsafe { libc::openat(parent, name.as_ptr(), flags) };
    if fd < 0 {
        return Err(io::Error::last_os_error());
    }
    Ok(unsafe { File::from_raw_fd(fd) })
}
#[repr(C)]
struct Handle {
    bytes: u32,
    kind: i32,
    value: [u8; 128],
}
fn handle(file: &File) -> io::Result<c::PersistentHandle> {
    let mut stat = std::mem::MaybeUninit::<libc::statfs>::uninit();
    if unsafe { libc::fstatfs(file.as_raw_fd(), stat.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { stat.assume_init() }.f_type != 0xef53 {
        return Err(reject("retained originals require actual ext4"));
    }
    let mut raw = Handle {
        bytes: 128,
        kind: 0,
        value: [0; 128],
    };
    let mut mount_id = 0i32;
    let rc = unsafe {
        libc::syscall(
            libc::SYS_name_to_handle_at,
            file.as_raw_fd(),
            c"".as_ptr(),
            &mut raw as *mut Handle,
            &mut mount_id as *mut i32,
            libc::AT_EMPTY_PATH,
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error());
    }
    if raw.kind != 1
        || raw.bytes != 8
        || u64::from(u32::from_ne_bytes(
            raw.value[..4].try_into().expect("handle length"),
        )) != file.metadata()?.ino()
    {
        return Err(reject("retained ext4 inode/generation handle differs"));
    }
    Ok(c::PersistentHandle {
        handle_type: raw.kind,
        bytes: raw.value[..8].to_vec(),
    })
}
fn attributes(file: &File) -> io::Result<BTreeMap<String, Vec<u8>>> {
    // ext4 flistxattr enumerates on-disk keys. Do not unconditionally request
    // security.selinux: enforcing SELinux may synthesize its default inode SID
    // even when the preserved on-disk set is empty.
    let mut names = vec![0u8; 65536];
    let n = unsafe { libc::flistxattr(file.as_raw_fd(), names.as_mut_ptr().cast(), names.len()) };
    if n < 0 {
        return Err(io::Error::last_os_error());
    }
    names.truncate(n as usize);
    if !names.is_empty() && names.last() != Some(&0) {
        return Err(reject("retained xattr name list malformed"));
    }
    let mut result = BTreeMap::new();
    let mut total = 0usize;
    for name in names.split(|b| *b == 0).filter(|s| !s.is_empty()) {
        let key =
            std::str::from_utf8(name).map_err(|_| reject("retained xattr key is not UTF-8"))?;
        if name.len() > 255 || result.len() >= 32 {
            return Err(reject("retained xattr set exceeds source bound"));
        }
        let key_c = CString::new(name).map_err(io::Error::other)?;
        let mut value = vec![0u8; 16384];
        let n = unsafe {
            libc::fgetxattr(
                file.as_raw_fd(),
                key_c.as_ptr(),
                value.as_mut_ptr().cast(),
                value.len(),
            )
        };
        if n < 0 {
            return Err(io::Error::last_os_error());
        }
        value.truncate(n as usize);
        total = total
            .checked_add(name.len() + value.len())
            .ok_or_else(|| reject("retained xattr size overflow"))?;
        if total > 65536 || result.insert(key.into(), value).is_some() {
            return Err(reject("retained xattr set differs"));
        }
    }
    Ok(result)
}
fn snapshot(file: &File) -> io::Result<c::Snapshot> {
    let before = identity(&file.metadata()?);
    let value = c::Snapshot {
        identity: before.clone(),
        handle: handle(file)?,
        attributes: attributes(file)?,
    };
    if identity(&file.metadata()?) != before {
        return Err(reject("retained inode changed during full snapshot"));
    }
    Ok(value)
}
struct Parent {
    path: PathBuf,
    file: File,
    snapshot: c::Snapshot,
    exact: bool,
}
struct Original {
    file: File,
    expected: c::RetainedOriginal,
}
pub(crate) struct RetainedOriginalLease {
    parents: Vec<Parent>,
    files: [Original; 2],
    spec: c::RetainedOriginalsSpec,
    working: [[u64; 7]; 2],
    working_loops: [u64; 2],
    pid: u32,
}
fn compare_main(
    spec: &c::RetainedOriginalsSpec,
    main: &RuntimeMainCustody,
) -> io::Result<[[u64; 7]; 2]> {
    let origin = main
        .persistent_data
        .original_copy_origin
        .as_ref()
        .ok_or_else(|| reject("actual Main has no original/working lineage"))?;
    let original = [
        stable(&spec.files[0].snapshot.identity),
        stable(&spec.files[1].snapshot.identity),
    ];
    let working = [
        main.persistent_data.backings[0].backing.stable7(),
        main.persistent_data.backings[1].backing.stable7(),
    ];
    if origin.original != original
        || origin.working != working
        || original
            .iter()
            .any(|o| working.iter().any(|w| o[..2] == w[..2]))
    {
        return Err(reject(
            "preserved original pair aliases or differs from the actual working Main",
        ));
    }
    Ok(working)
}
impl RetainedOriginalLease {
    pub(crate) fn capture(
        spec: c::RetainedOriginalsSpec,
        main: &MainCustodyObservation,
        end: Instant,
    ) -> io::Result<Self> {
        spec.validate().map_err(reject)?;
        if Instant::now() >= end {
            return Err(reject("retention admission exhausted original end"));
        }
        let working = compare_main(&spec, main.facts())?;
        let working_loops = [
            main.facts().persistent_data.backings[0]
                .loop_binding
                .block_device,
            main.facts().persistent_data.backings[1]
                .loop_binding
                .block_device,
        ];
        if working_loops[0] == working_loops[1]
            || working_loops.iter().any(|d| libc::major(*d) != 7)
        {
            return Err(reject(
                "actual working pair does not have two distinct real loop devices",
            ));
        }
        let mut parents = Vec::new();
        let mut path = PathBuf::from("/");
        let mut file = open_at(libc::AT_FDCWD, c"/", true)?;
        let parts = spec.directory.path.components().skip(1).collect::<Vec<_>>();
        for (index, part) in parts.iter().enumerate() {
            let snap = snapshot(&file)?;
            if snap.identity.mode & libc::S_IFMT != libc::S_IFDIR
                || snap.identity.uid != 0
                || snap.identity.gid != 0
                || snap.identity.mode & 0o022 != 0
            {
                return Err(reject(
                    "retained original parent is not protected normal root",
                ));
            }
            parents.push(Parent {
                path: path.clone(),
                file,
                snapshot: snap,
                exact: index + 1 >= parts.len(),
            });
            let std::path::Component::Normal(name) = part else {
                return Err(reject("retained path is not canonical"));
            };
            let name = CString::new(name.as_bytes()).map_err(io::Error::other)?;
            file = open_at(
                parents.last().expect("parent").file.as_raw_fd(),
                &name,
                true,
            )?;
            path.push(part.as_os_str());
        }
        let directory = snapshot(&file)?;
        let wanted = &spec.directory;
        if stable(&directory.identity)
            != [
                wanted.identity.dev,
                wanted.identity.ino,
                u64::from(wanted.identity.mode),
                u64::from(wanted.identity.uid),
                u64::from(wanted.identity.gid),
                wanted.identity.nlink,
                wanted.identity.size,
            ]
            || directory.handle != wanted.handle
            || directory.attributes != wanted.attributes
        {
            return Err(reject(
                "actual retained original directory differs from cold-held generation",
            ));
        }
        parents.push(Parent {
            path,
            file,
            snapshot: directory,
            exact: true,
        });
        let dir = &parents.last().expect("directory").file;
        let open = |expected: &c::RetainedOriginal| -> io::Result<Original> {
            let name = CString::new(expected.name.as_bytes()).map_err(io::Error::other)?;
            let file = open_at(dir.as_raw_fd(), &name, false)?;
            // The cold pair uses flock on these same open-file descriptions.
            // A different fcntl record-lock family would not exclude that owner.
            if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
                return Err(io::Error::last_os_error());
            }
            if snapshot(&file)? != expected.snapshot {
                return Err(reject(
                    "actual original complete inode/generation/xattrs differ",
                ));
            }
            Ok(Original {
                file,
                expected: expected.clone(),
            })
        };
        let files = [open(&spec.files[0])?, open(&spec.files[1])?];
        let result = Self {
            parents,
            files,
            spec,
            working,
            working_loops,
            pid: std::process::id(),
        };
        result.guard(main, end)?;
        result.hash_pair(end)?;
        result.guard(main, end)?;
        Ok(result)
    }
    fn local_guard(&self, end: Instant) -> io::Result<()> {
        if std::process::id() != self.pid || Instant::now() >= end {
            return Err(reject(
                "retained actual lease left its process/original end",
            ));
        }
        for (i, parent) in self.parents.iter().enumerate() {
            let actual = snapshot(&parent.file)?;
            let named = if i == 0 {
                open_at(libc::AT_FDCWD, c"/", true)?
            } else {
                open_at(
                    self.parents[i - 1].file.as_raw_fd(),
                    &CString::new(
                        parent
                            .path
                            .file_name()
                            .ok_or_else(|| reject("retained parent name"))?
                            .as_bytes(),
                    )
                    .map_err(io::Error::other)?,
                    true,
                )?
            };
            for value in [actual, snapshot(&named)?] {
                let okay = if parent.exact {
                    value == parent.snapshot
                } else {
                    stable(&value.identity)[..5] == stable(&parent.snapshot.identity)[..5]
                        && value.handle == parent.snapshot.handle
                        && value.attributes == parent.snapshot.attributes
                };
                if !okay {
                    return Err(reject("retained original parent/handle/xattrs changed"));
                }
            }
        }
        let directory = &self.parents.last().expect("retained directory").file;
        for original in &self.files {
            let name = CString::new(original.expected.name.as_bytes()).map_err(io::Error::other)?;
            let named = open_at(directory.as_raw_fd(), &name, false)?;
            let flags = unsafe { libc::fcntl(original.file.as_raw_fd(), libc::F_GETFL) };
            if flags < 0
                || flags & libc::O_ACCMODE != libc::O_RDONLY
                || snapshot(&original.file)? != original.expected.snapshot
                || snapshot(&named)? != original.expected.snapshot
            {
                return Err(reject(
                    "preserved original read-only OFD/named generation changed",
                ));
            }
        }
        if Instant::now() >= end {
            return Err(reject("retention guard exhausted original end"));
        }
        Ok(())
    }
    pub(crate) fn guard(&self, main: &MainCustodyObservation, end: Instant) -> io::Result<()> {
        self.local_guard(end)?;
        if compare_main(&self.spec, main.facts())? != self.working {
            return Err(reject("retention moved to another working pair"));
        }
        prove_no_loop_alias(&self.spec.files, &self.working, &self.working_loops)?;
        self.local_guard(end)
    }
    pub(crate) fn hash_pair(&self, overall: Instant) -> io::Result<()> {
        let end = Instant::now()
            .checked_add(Duration::from_secs(c::RETAINED_PAIR_HASH_SECONDS))
            .ok_or_else(|| reject("retention hash deadline overflow"))?
            .min(overall);
        self.local_guard(end)?;
        prove_no_loop_alias(&self.spec.files, &self.working, &self.working_loops)?;
        for original in &self.files {
            let got = hash_file(
                &original.file,
                original.expected.snapshot.identity.size,
                end,
                &mut || self.local_guard(end),
            )?;
            if got != original.expected.sha256 {
                return Err(reject("preserved original full content commitment differs"));
            }
        }
        prove_no_loop_alias(&self.spec.files, &self.working, &self.working_loops)?;
        self.local_guard(end)
    }
}
fn hash_file(
    file: &File,
    bytes: u64,
    end: Instant,
    guard: &mut dyn FnMut() -> io::Result<()>,
) -> io::Result<String> {
    let mut hash = Sha256::new();
    let mut buf = vec![0u8; 1024 * 1024];
    let mut offset = 0u64;
    while offset < bytes {
        if Instant::now() >= end {
            return Err(reject("retained pair full hash expired"));
        }
        guard()?;
        let n =
            usize::try_from((bytes - offset).min(buf.len() as u64)).map_err(io::Error::other)?;
        crate::working_retained_read::read_exact_at(file, &mut buf[..n], offset, end, guard)?;
        hash.update(&buf[..n]);
        offset += n as u64;
        guard()?;
        if Instant::now() >= end {
            return Err(reject("retained pair full hash expired"));
        }
    }
    if file.read_at(&mut [0u8; 1], bytes)? != 0 {
        return Err(reject("retained original has uncommitted trailing bytes"));
    }
    Ok(format!("{:x}", hash.finalize()))
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
impl Default for LoopInfo {
    fn default() -> Self {
        unsafe { std::mem::zeroed() }
    }
}
fn same_backing(info: &LoopInfo, originals: &[c::RetainedOriginal; 2]) -> bool {
    originals
        .iter()
        .any(|o| info.device == o.snapshot.identity.dev && info.inode == o.snapshot.identity.ino)
}
fn prove_no_loop_alias(
    originals: &[c::RetainedOriginal; 2],
    working: &[[u64; 7]; 2],
    working_loops: &[u64; 2],
) -> io::Result<()> {
    let sys = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open("/sys/devices/virtual/block")?;
    let mut stat = std::mem::MaybeUninit::<libc::statfs>::uninit();
    if unsafe { libc::fstatfs(sys.as_raw_fd(), stat.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { stat.assume_init() }.f_type != 0x62656572 {
        return Err(reject("actual loop roster is not kernel sysfs"));
    }
    let sys_identity = identity(&sys.metadata()?);
    if sys_identity.uid != 0 || sys_identity.gid != 0 || sys_identity.mode & 0o022 != 0 {
        return Err(reject("actual loop roster root differs"));
    }
    let mut present = [false; 2];

    let mut seen = 0usize;
    for entry in fs::read_dir("/sys/devices/virtual/block")? {
        let entry = entry?;
        let name = entry.file_name();
        let Some(name) = name.to_str() else { continue };
        let Some(number) = name.strip_prefix("loop") else {
            continue;
        };
        let index = number
            .parse::<u32>()
            .map_err(|_| reject("actual loop name malformed"))?;
        if index.to_string() != number {
            return Err(reject("actual loop number is not canonical"));
        }
        seen += 1;
        if seen > 4096 {
            return Err(reject("actual loop roster exceeds fixed bound"));
        }
        let sys = open_at(
            libc::AT_FDCWD,
            &CString::new(format!("/sys/devices/virtual/block/{name}/dev"))
                .map_err(io::Error::other)?,
            false,
        )?;
        let mut raw = [0u8; 64];
        let n = sys.read_at(&mut raw, 0)?;
        if &raw[..n] != format!("7:{index}\n").as_bytes() {
            return Err(reject("actual sysfs loop device number differs"));
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(format!("/dev/{name}"))?;
        let m = file.metadata()?;
        if m.mode() & libc::S_IFMT != libc::S_IFBLK
            || m.rdev() != libc::makedev(7, index)
            || m.uid() != 0
        {
            return Err(reject("actual loop node differs from sysfs"));
        }
        let mut info = LoopInfo::default();
        if unsafe { libc::ioctl(file.as_raw_fd(), 0x4c05 as libc::c_ulong, &mut info) } != 0 {
            let error = io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::ENXIO) {
                return Err(error);
            }
        } else if info.number != index || same_backing(&info, originals) {
            return Err(reject("preserved original is referenced by an actual loop"));
        }
        for i in 0..2 {
            if m.rdev() == working_loops[i] {
                if info.number != index
                    || info.device != working[i][0]
                    || info.inode != working[i][1]
                {
                    return Err(reject(
                        "actual working loop no longer references the independently observed Main backing",
                    ));
                }
                present[i] = true;
            }
        }

        // Close immediately: retaining unrelated loop OFDs could postpone their
        // normal autoclear. No SET_FD, CLR_FD, CONFIGURE or write is performed.
    }
    if present != [true, true] {
        return Err(reject(
            "actual kernel loop roster omitted one of this Main's working backings",
        ));
    }
    let named = fs::metadata("/sys/devices/virtual/block")?;
    if identity(&sys.metadata()?) != sys_identity || identity(&named) != sys_identity {
        return Err(reject(
            "actual kernel loop roster changed during complete metadata observation",
        ));
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn full_hash_reads_every_byte_and_checks_trailing_content_and_expiry() {
        let root = std::env::var_os("CARGO_TARGET_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|| std::env::current_dir().unwrap());
        let dir = tempfile::tempdir_in(root).unwrap();
        let path = dir.path().join("original");
        fs::write(&path, b"original user data").unwrap();
        let file = File::open(&path).unwrap();
        let end = Instant::now() + Duration::from_secs(5);
        let mut checks = 0;
        assert_eq!(
            hash_file(&file, 18, end, &mut || {
                checks += 1;
                Ok(())
            })
            .unwrap(),
            format!("{:x}", Sha256::digest(b"original user data"))
        );
        assert!(checks >= 2);
        assert!(hash_file(&file, 17, end, &mut || Ok(())).is_err());
        assert!(hash_file(&file, 18, Instant::now(), &mut || Ok(())).is_err());
        assert!(
            hash_file(&file, 18, end, &mut || Err(reject(
                "actual generation changed"
            )))
            .is_err()
        );
    }
    #[test]
    fn original_flock_conflicts_with_an_independent_open_description() {
        let file = tempfile::NamedTempFile::new().unwrap();
        let a = File::open(file.path()).unwrap();
        let b = File::open(file.path()).unwrap();
        assert_eq!(
            unsafe { libc::flock(a.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        assert_ne!(
            unsafe { libc::flock(b.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        assert_eq!(
            io::Error::last_os_error().raw_os_error(),
            Some(libc::EWOULDBLOCK)
        );
        drop(a);
        assert_eq!(
            unsafe { libc::flock(b.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
    }
    #[test]
    fn real_original_inode_guard_detects_content_change_and_equal_byte_replacement() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("original");
        fs::write(&path, b"retained contents").unwrap();
        let file = File::open(&path).unwrap();
        let initial = identity(&file.metadata().unwrap());
        fs::write(&path, b"mutated contents now longer").unwrap();
        assert_ne!(identity(&file.metadata().unwrap()), initial);
        fs::rename(&path, root.path().join("moved")).unwrap();
        fs::write(&path, b"retained contents").unwrap();
        assert_ne!(identity(&fs::metadata(&path).unwrap()), initial);
        assert_ne!(
            fs::metadata(&path).unwrap().ino(),
            file.metadata().unwrap().ino()
        );
    }
    #[test]
    fn actual_loop_status_layout_is_kernel_loop_info64() {
        assert_eq!(std::mem::size_of::<LoopInfo>(), 232);
    }
}
