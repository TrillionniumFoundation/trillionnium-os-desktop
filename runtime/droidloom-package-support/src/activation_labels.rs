//! Native libselinux matching and the admitted ordinary setfiles producer.
//! Single regular-file/directory writes use their original descriptors.
//! Recursive labeling uses setfiles' ordinary lsetfilecon semantics; it is not
//! described as an atomic descriptor operation on symlinks or the whole tree.
use super::{
    Result,
    activation_files::{self as files, FileIdentity, FilePin, HeldFile},
    activation_owner::InstallationPermit,
};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeSet,
    ffi::{CStr, CString, OsString},
    fs::{self, File, Metadata},
    io::Read,
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{
            ffi::{OsStrExt, OsStringExt},
            fs::MetadataExt,
            process::CommandExt,
        },
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

const SETFILES: (u64, &str) = (
    22920,
    "02597f1eceaa93a877ab8dd2a5fd0dbbd2d5dfdba8481e5421bfb0834783f5a5",
);
const MATCHPATHCON: (u64, &str) = (
    14728,
    "48cdccc40775e3db029b1d20af97f37e13a350d894b86150993cfc71d10ca51a",
);
const SEPOL: (u64, &str) = (
    941928,
    "d96adef8761310b409df7280f0f92aa3083b5eb6b177f6718d7bcdb2b0e64365",
);
const SELINUX: (u64, &str) = (
    199120,
    "4dab059ee57d5be56bdf21db5e5bcc56e881d354010c7b3eaa0027c662692e9b",
);
const BOARD: &[u8] = include_bytes!(
    "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
);
const CONTEXTS: [&[u8]; 4] = [
    include_bytes!(
        "../../../android/framework/droidloom-readiness/board-policy/ubuntu-native-file_contexts"
    ),
    include_bytes!(
        "../../../android/framework/droidloom-readiness/board-policy/ubuntu-real-root-file_contexts"
    ),
    include_bytes!(
        "../../../android/framework/droidloom-readiness/board-policy/linux-service-file_contexts"
    ),
    include_bytes!(
        "../../../android/framework/droidloom-readiness/board-policy/linux-initial-calibration-file_contexts"
    ),
];
const CONTEXT_PATH: &str = "etc/selinux/droidloom/contexts/files/file_contexts";
const LIBRARY_PATH: &str = "usr/lib/x86_64-linux-gnu/libselinux.so.1";
const SKIP_FILES: [&str; 7] = [
    "/etc/droidloom/setup.lock",
    "/etc/droidloom/cell.json",
    "/etc/droidloom/container-launcher.json",
    "/etc/droidloom/production/selected.json",
    "/etc/droidloom/production/package-maintenance.json",
    "/var/lib/droidloom/users/1000/data/data.img",
    "/var/lib/droidloom/users/1000/data/metadata.img",
];
const SKIP_TREES: [&str; 5] = [
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/var/lib/droidloom/activation-staging",
];

fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn fixed_pin(path: PathBuf, fixed: (u64, &str)) -> FilePin {
    FilePin {
        path,
        bytes: fixed.0,
        sha256: fixed.1.into(),
    }
}
fn expected_contexts() -> Vec<u8> {
    CONTEXTS.concat()
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct LabelInputs {
    pub setfiles: FilePin,
    pub matchpathcon: FilePin,
    pub producer_libsepol: FilePin,
}

struct Directory {
    path: PathBuf,
    file: File,
    identity: (u64, u64, u32, u32, u32),
}
impl Directory {
    fn open(path: &Path, private: bool) -> Result<Self> {
        let (parent, name) = files::parent(path)?;
        let raw = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                0,
            )
        };
        if raw < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        let file = unsafe { File::from_raw_fd(raw) };
        let m = file.metadata()?;
        require(
            m.is_dir()
                && m.uid() == 0
                && m.gid() == 0
                && m.mode() & 0o7022 == 0
                && (!private || m.mode() & 0o7777 == 0o700),
            "label directory is not protected root custody",
        )?;
        Ok(Self {
            path: path.into(),
            file,
            identity: (m.dev(), m.ino(), m.mode(), m.uid(), m.gid()),
        })
    }
    fn revalidate(&self) -> Result<()> {
        let named = Self::open(&self.path, false)?;
        let m = self.file.metadata()?;
        require(
            self.identity == named.identity
                && self.identity == (m.dev(), m.ino(), m.mode(), m.uid(), m.gid()),
            "original label directory was replaced or changed",
        )
    }
}
fn generation(root: &Path) -> Result<(PathBuf, PathBuf)> {
    let parent = root.parent().ok_or("label stage has no generation")?;
    require(
        root.file_name().is_some_and(|n| n == "root")
            && parent.parent() == Some(Path::new("/var/lib/droidloom/activation-staging"))
            && parent
                .file_name()
                .and_then(|n| n.to_str())
                .is_some_and(files::valid_digest),
        "labels require the fixed first-activation generation layout",
    )?;
    for path in [
        Path::new("/var"),
        Path::new("/var/lib"),
        Path::new("/var/lib/droidloom"),
        Path::new("/var/lib/droidloom/activation-staging"),
        parent,
        root,
    ] {
        Directory::open(path, path == parent || path == root)?;
    }
    Ok((parent.join("work"), parent.join("work/label-tools")))
}

pub(super) fn stage(root: &Path, work: &Path, input: &LabelInputs) -> Result<Value> {
    super::require_root()?;
    let (expected_work, tools) = generation(root)?;
    require(
        work == expected_work,
        "label tools are outside this generation's fixed work directory",
    )?;
    Directory::open(work, true)?;
    files::private_dir(&tools)?;
    let mut outputs = Vec::new();
    for (name, pin, fixed, mode) in [
        ("setfiles", &input.setfiles, SETFILES, 0o500),
        ("matchpathcon", &input.matchpathcon, MATCHPATHCON, 0o500),
        ("libsepol.so.2", &input.producer_libsepol, SEPOL, 0o400),
    ] {
        require(
            pin.bytes == fixed.0 && pin.sha256 == fixed.1,
            "label input is not the admitted ordinary producer",
        )?;
        outputs.push(HeldFile::open(pin, fixed.0)?.copy_new(&tools.join(name), mode)?);
    }
    let native = HeldFile::open(&fixed_pin(root.join(LIBRARY_PATH), SELINUX), SELINUX.0)?;
    outputs.push(native.copy_new(&tools.join("libselinux.so.1"), 0o400)?);
    native.revalidate()?;
    let labeler = Labeler::from_stage(root)?;
    labeler.revalidate()?;
    Ok(
        json!({"schema":"droidloom-normal-label-tools-stage-v1","inputs":input,"files":outputs,
        "native_library":native.pin(),"context_source":labeler.contexts.pin(),
        "live_paths_changed":false,"production_ready":false}),
    )
}

#[repr(C)]
struct SelinuxOpt {
    kind: libc::c_int,
    value: *const libc::c_char,
}
type Open =
    unsafe extern "C" fn(libc::c_uint, *const SelinuxOpt, libc::c_uint) -> *mut libc::c_void;
type Lookup = unsafe extern "C" fn(
    *mut libc::c_void,
    *mut *mut libc::c_char,
    *const libc::c_char,
    libc::c_int,
) -> libc::c_int;
type Close = unsafe extern "C" fn(*mut libc::c_void);
type Free = unsafe extern "C" fn(*mut libc::c_char);
struct DynamicLibrary(*mut libc::c_void);
impl Drop for DynamicLibrary {
    fn drop(&mut self) {
        unsafe {
            libc::dlclose(self.0);
        }
    }
}
struct NativeMatcher {
    handle: *mut libc::c_void,
    lookup: Lookup,
    close: Close,
    free: Free,
    _library: DynamicLibrary,
}
impl NativeMatcher {
    fn open(library: &HeldFile, contexts: &HeldFile) -> Result<Self> {
        library.revalidate()?;
        contexts.revalidate()?;
        let path = CString::new(format!("/proc/self/fd/{}", library.file().as_raw_fd()))?;
        let raw = unsafe {
            libc::dlopen(
                path.as_ptr(),
                libc::RTLD_NOW | libc::RTLD_LOCAL | libc::RTLD_DEEPBIND,
            )
        };
        require(
            !raw.is_null(),
            "normal native libselinux could not be loaded",
        )?;
        let loaded = DynamicLibrary(raw);
        let mut base: *mut libc::c_void = std::ptr::null_mut();
        let mut symbol = |name: &CStr| -> Result<*mut libc::c_void> {
            let address = unsafe { libc::dlsym(loaded.0, name.as_ptr()) };
            require(
                !address.is_null(),
                "normal libselinux lacks a fixed labeling symbol",
            )?;
            let mut info: libc::Dl_info = unsafe { std::mem::zeroed() };
            require(
                unsafe { libc::dladdr(address, &mut info) } != 0
                    && !info.dli_fbase.is_null()
                    && !info.dli_fname.is_null(),
                "native labeling symbol has no actual library owner",
            )?;
            require(
                unsafe { CStr::from_ptr(info.dli_fname) } == path.as_c_str(),
                "native labeling symbol resolved outside the held library",
            )?;
            if base.is_null() {
                base = info.dli_fbase;
            }
            require(
                base == info.dli_fbase,
                "labeling API symbols do not share their original library",
            )?;
            Ok(address)
        };
        let open: Open = unsafe { std::mem::transmute(symbol(c"selabel_open")?) };
        let lookup: Lookup = unsafe { std::mem::transmute(symbol(c"selabel_lookup_raw")?) };
        let close: Close = unsafe { std::mem::transmute(symbol(c"selabel_close")?) };
        let free: Free = unsafe { std::mem::transmute(symbol(c"freecon")?) };
        let input = CString::new(format!("/proc/self/fd/{}", contexts.file().as_raw_fd()))?;
        // Exact libselinux 3.9 public ABI: FILE=0, BASEONLY=2, PATH=3.
        // The held descriptor name has no .bin/.local/subs siblings.
        let options = [
            SelinuxOpt {
                kind: 2,
                value: c"1".as_ptr(),
            },
            SelinuxOpt {
                kind: 3,
                value: input.as_ptr(),
            },
        ];
        let handle = unsafe { open(0, options.as_ptr(), options.len() as libc::c_uint) };
        require(
            !handle.is_null(),
            "normal file-context backend could not open the held compiled templates",
        )?;
        let result = Self {
            handle,
            lookup,
            close,
            free,
            _library: loaded,
        };
        library.revalidate()?;
        contexts.revalidate()?;
        Ok(result)
    }
    fn lookup(&self, path: &Path, mode: u32) -> Result<Vec<u8>> {
        let path = canonical_path(path)?;
        let mut out = std::ptr::null_mut();
        let rc =
            unsafe { (self.lookup)(self.handle, &mut out, path.as_ptr(), mode as libc::c_int) };
        if rc != 0 {
            if !out.is_null() {
                unsafe { (self.free)(out) };
            }
            return Err(format!(
                "normal native matcher rejected a required filesystem role: {}",
                std::io::Error::last_os_error()
            )
            .into());
        }
        require(!out.is_null(), "normal matcher returned no context")?;
        let size = unsafe { libc::strnlen(out, 4097) };
        let bytes = if size <= 4096 {
            unsafe { std::slice::from_raw_parts(out.cast::<u8>(), size) }.to_vec()
        } else {
            Vec::new()
        };
        unsafe { (self.free)(out) };
        require(
            bytes.starts_with(b"u:object_r:")
                && bytes.ends_with(b":s0")
                && bytes
                    .iter()
                    .all(|b| b.is_ascii_alphanumeric() || b":_".contains(b)),
            "normal matcher returned a noncanonical board file context",
        )?;
        let mut bytes = bytes;
        bytes.push(0);
        Ok(bytes)
    }
}
impl Drop for NativeMatcher {
    fn drop(&mut self) {
        unsafe {
            (self.close)(self.handle);
        }
    }
}
fn canonical_path(path: &Path) -> Result<CString> {
    let raw = path.as_os_str().as_bytes();
    require(
        raw == b"/"
            || (raw.starts_with(b"/")
                && !raw.ends_with(b"/")
                && raw[1..]
                    .split(|b| *b == b'/')
                    .all(|part| !part.is_empty() && part != b"." && part != b"..")),
        "label lookup path is not canonical and absolute",
    )?;
    Ok(CString::new(raw)?)
}
fn stable_metadata(a: &Metadata, b: &Metadata) -> bool {
    (
        a.dev(),
        a.ino(),
        a.mode(),
        a.uid(),
        a.gid(),
        a.nlink(),
        a.len(),
        a.mtime(),
        a.mtime_nsec(),
        a.rdev(),
    ) == (
        b.dev(),
        b.ino(),
        b.mode(),
        b.uid(),
        b.gid(),
        b.nlink(),
        b.len(),
        b.mtime(),
        b.mtime_nsec(),
        b.rdev(),
    )
}
fn fd_label(file: &File) -> Result<Option<Vec<u8>>> {
    let mut bytes = vec![0u8; 4096];
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if count < 0 {
        let e = std::io::Error::last_os_error();
        if e.raw_os_error() == Some(libc::ENODATA) {
            return Ok(None);
        }
        return Err(e.into());
    }
    bytes.truncate(count as usize);
    Ok(Some(bytes))
}
fn link_label(path: &Path) -> Result<Option<Vec<u8>>> {
    let path = canonical_path(path)?;
    let mut bytes = vec![0u8; 4096];
    let count = unsafe {
        libc::lgetxattr(
            path.as_ptr(),
            c"security.selinux".as_ptr(),
            bytes.as_mut_ptr().cast(),
            bytes.len(),
        )
    };
    if count < 0 {
        let e = std::io::Error::last_os_error();
        if e.raw_os_error() == Some(libc::ENODATA) {
            return Ok(None);
        }
        return Err(e.into());
    }
    bytes.truncate(count as usize);
    Ok(Some(bytes))
}

pub(super) struct Labeler {
    matcher: NativeMatcher,
    root: Directory,
    work: Directory,
    tools: Directory,
    contexts: HeldFile,
    policy: HeldFile,
    native: HeldFile,
    library: HeldFile,
    setfiles: HeldFile,
    matchpathcon: HeldFile,
    sepol: HeldFile,
}
impl Labeler {
    pub(super) fn from_stage(root: &Path) -> Result<Self> {
        super::require_root()?;
        let (work, tools) = generation(root)?;
        let expected = expected_contexts();
        let contexts = HeldFile::open(
            &FilePin {
                path: root.join(CONTEXT_PATH),
                bytes: expected.len() as u64,
                sha256: files::digest(&expected),
            },
            1024 * 1024,
        )?;
        let board: Value = serde_json::from_slice(BOARD)?;
        let policy = HeldFile::open(
            &FilePin {
                path: root.join("etc/selinux/droidloom/policy/policy.30"),
                bytes: board["files"]["joint.policy"]["size"]
                    .as_u64()
                    .ok_or("board policy has no size")?,
                sha256: board["files"]["joint.policy"]["sha256"]
                    .as_str()
                    .ok_or("board policy has no digest")?
                    .into(),
            },
            32 * 1024 * 1024,
        )?;
        let native = HeldFile::open(&fixed_pin(root.join(LIBRARY_PATH), SELINUX), SELINUX.0)?;
        let library = HeldFile::open(
            &fixed_pin(tools.join("libselinux.so.1"), SELINUX),
            SELINUX.0,
        )?;
        let setfiles = HeldFile::open(&fixed_pin(tools.join("setfiles"), SETFILES), SETFILES.0)?;
        let matchpathcon = HeldFile::open(
            &fixed_pin(tools.join("matchpathcon"), MATCHPATHCON),
            MATCHPATHCON.0,
        )?;
        let sepol = HeldFile::open(&fixed_pin(tools.join("libsepol.so.2"), SEPOL), SEPOL.0)?;
        for file in [
            &contexts,
            &policy,
            &native,
            &library,
            &setfiles,
            &matchpathcon,
            &sepol,
        ] {
            require(
                file.identity().uid == 0 && file.identity().gid == 0,
                "staged normal labeling inputs are not root-owned",
            )?;
            files::no_privilege_xattrs(file.file())?;
        }
        let matcher = NativeMatcher::open(&library, &contexts)?;
        let result = Self {
            matcher,
            root: Directory::open(root, true)?,
            work: Directory::open(&work, true)?,
            tools: Directory::open(&tools, true)?,
            contexts,
            policy,
            native,
            library,
            setfiles,
            matchpathcon,
            sepol,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> Result<()> {
        self.root.revalidate()?;
        self.work.revalidate()?;
        self.tools.revalidate()?;
        for file in [
            &self.contexts,
            &self.policy,
            &self.native,
            &self.library,
            &self.setfiles,
            &self.matchpathcon,
            &self.sepol,
        ] {
            file.revalidate()?;
        }
        Ok(())
    }
    pub(super) fn apply_file(&self, file: &File, final_path: &Path) -> Result<Value> {
        self.revalidate()?;
        let before = file.metadata()?;
        require(
            before.is_file() || before.is_dir(),
            "typed descriptor labeling supports regular files/directories; symlinks use the ordinary setfiles producer",
        )?;
        let expected = self.matcher.lookup(final_path, before.mode())?;
        let old = fd_label(file)?;
        let changed = old.as_ref() != Some(&expected);
        if changed {
            if unsafe {
                libc::fsetxattr(
                    file.as_raw_fd(),
                    c"security.selinux".as_ptr(),
                    expected.as_ptr().cast(),
                    expected.len(),
                    0,
                )
            } != 0
            {
                return Err(std::io::Error::last_os_error().into());
            }
            file.sync_all()?;
        }
        let after = file.metadata()?;
        require(
            stable_metadata(&before, &after) && fd_label(file)?.as_ref() == Some(&expected),
            "original file changed beyond its controlled SELinux xattr or label readback differs",
        )?;
        self.revalidate()?;
        Ok(
            json!({"path":final_path,"operation":"held_fd_fsetxattr_and_readback",
            "device":before.dev(),"inode":before.ino(),"label":String::from_utf8_lossy(&expected[..expected.len()-1]),
            "changed":changed,"ctime_before":[before.ctime(),before.ctime_nsec()],
            "ctime_after":[after.ctime(),after.ctime_nsec()],"readback":true}),
        )
    }
    fn run(
        &self,
        args: &[OsString],
        log: &Path,
        limit: Duration,
        mut check: impl FnMut() -> Result<()>,
    ) -> Result<Value> {
        self.revalidate()?;
        check()?;
        let output = files::new_file(log, 0o600)?;
        let mut command = Command::new(format!(
            "/proc/self/fd/{}",
            self.setfiles.file().as_raw_fd()
        ));
        command
            .arg0("setfiles")
            .args(args)
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("LANG", "C")
            .env("LC_ALL", "C")
            .env("LD_LIBRARY_PATH", &self.tools.path)
            .current_dir(&self.tools.path)
            .stdin(Stdio::null())
            .stdout(Stdio::from(output.try_clone()?))
            .stderr(Stdio::from(output.try_clone()?));
        let mut child = command.spawn()?;
        // The unreaped original Child retains its PID even if the pidfd open
        // fails. Retire that original child before returning any setup error.
        let pidfd = match super::original_actor(child.id()) {
            Ok(Some(fd)) => fd,
            result => {
                let _ = child.kill();
                let _ = child.wait();
                return Err(match result {
                    Err(error) => error,
                    _ => "normal labeling child has no original pidfd".into(),
                });
            }
        };
        let mut owned = Owned {
            child,
            pidfd,
            finished: false,
        };
        let began = Instant::now();
        let deadline = began + limit;
        let mut next = began;
        let status = loop {
            if Instant::now() >= deadline {
                owned.stop()?;
                return Err("normal setfiles exceeded its bounded owned execution window".into());
            }
            if output.metadata()?.len() > 16 * 1024 * 1024 {
                owned.stop()?;
                return Err("normal labeling log exceeded its reviewed bound while the original child was running".into());
            }
            if let Some(status) = owned.child.try_wait()? {
                owned.finished = true;
                require(
                    Instant::now() < deadline,
                    "normal setfiles terminal state was observed after its original deadline",
                )?;
                break status;
            }
            if Instant::now() >= next {
                if let Err(error) = self.revalidate().and_then(|_| check()) {
                    owned.stop()?;
                    return Err(error);
                }
                next = Instant::now() + Duration::from_secs(10);
            }
            std::thread::sleep(Duration::from_millis(100));
        };
        output.sync_all()?;
        self.revalidate()?;
        check()?;
        require(
            Instant::now() < deadline,
            "normal labeling completion validation exceeded its original deadline",
        )?;
        require(
            super::pidfd_exited(&owned.pidfd)?,
            "normal setfiles returned without original pidfd terminal proof",
        )?;
        let logpin = files::pin_file(log)?;
        require(
            logpin.bytes <= 16 * 1024 * 1024,
            "normal labeling log exceeds its reviewed bound",
        )?;
        if !status.success() {
            return Err(format!(
                "normal setfiles failed with {status}; original log {}",
                log.display()
            )
            .into());
        }
        Ok(
            json!({"program":self.setfiles.pin(),"arguments":args,"log":logpin,
            "exit_code":status.code(),"original_pidfd_exit_observed":true,"elapsed_ms":began.elapsed().as_millis(),
            "native_library":self.library.pin(),"producer_libsepol":self.sepol.pin()}),
        )
    }
    fn arguments(
        &self,
        root: &Path,
        dry: bool,
        verbose: bool,
        excluded: &BTreeSet<PathBuf>,
    ) -> Vec<OsString> {
        // -m is required for initial labeling on the old AppArmor-only kernel:
        // its ext4 root is not yet advertised as a loaded SELinux seclabel mount.
        // Every other actual mount is explicitly excluded for the live operation.
        let mut args = vec![
            "-F".into(),
            "-E".into(),
            "-m".into(),
            "-T".into(),
            "1".into(),
        ];
        if dry {
            args.push("-n".into())
        }
        if verbose {
            args.push("-v".into())
        }
        if root != Path::new("/") {
            args.extend(["-r".into(), root.as_os_str().to_owned()]);
        }
        args.extend(["-c".into(), self.policy.pin().path.as_os_str().to_owned()]);
        for path in excluded {
            args.extend(["-e".into(), path.as_os_str().to_owned()]);
        }
        args.push(self.contexts.pin().path.as_os_str().to_owned());
        args.push(root.as_os_str().to_owned());
        args
    }
    pub(super) fn preflight(&self) -> Result<Value> {
        self.revalidate()?;
        let run = tempfile::Builder::new()
            .prefix("label-preflight-")
            .tempdir_in(&self.work.path)?
            .keep();
        let probe = run.join("probe");
        files::private_dir(&probe)?;
        let regular = files::new_file(&probe.join("file"), 0o600)?;
        let skipped = files::new_file(&probe.join("skip"), 0o600)?;
        let skip_before = FileIdentity::read(skipped.metadata()?)?;
        files::private_dir(&probe.join("directory"))?;
        let directory = Directory::open(&probe.join("directory"), true)?;
        std::os::unix::fs::symlink("file", probe.join("link"))?;
        let link_before = fs::symlink_metadata(probe.join("link"))?;
        let typed_file = self.apply_file(&regular, Path::new("/file"))?;
        let typed_directory = self.apply_file(&directory.file, Path::new("/directory"))?;
        let exclusions = BTreeSet::from([probe.join("skip")]);
        let command = self.run(
            &self.arguments(&probe, false, false, &exclusions),
            &run.join("ordinary-private-probe.log"),
            Duration::from_secs(120),
            || Ok(()),
        )?;
        let link_after = fs::symlink_metadata(probe.join("link"))?;
        let link_expected = self
            .matcher
            .lookup(Path::new("/link"), link_before.mode())?;
        require(
            stable_metadata(&link_before, &link_after)
                && link_label(&probe.join("link"))?.as_ref() == Some(&link_expected),
            "ordinary setfiles did not label the private symlink itself",
        )?;
        require(
            fd_label(&regular)?.as_ref()
                == Some(
                    &self
                        .matcher
                        .lookup(Path::new("/file"), regular.metadata()?.mode())?,
                )
                && fd_label(&directory.file)?.as_ref()
                    == Some(
                        &self
                            .matcher
                            .lookup(Path::new("/directory"), directory.file.metadata()?.mode())?,
                    ),
            "normal producer changed the wrong private target or failed actual label readback",
        )?;
        require(
            FileIdentity::read(skipped.metadata()?)? == skip_before
                && fd_label(&skipped)?.is_none(),
            "ordinary setfiles file exclusion did not preserve the original skipped inode and ctime",
        )?;
        // The dry-run checks the complete normal staged input without mutating
        // any of the held source identities that the activation transaction uses.
        let dry = self.run(
            &self.arguments(&self.root.path, true, false, &BTreeSet::new()),
            &run.join("complete-stage-dry-run.log"),
            Duration::from_secs(900),
            || Ok(()),
        )?;
        require(
            fs::symlink_metadata(probe.join("link"))?.ino() == link_before.ino(),
            "private symlink probe was replaced before cleanup",
        )?;
        fs::remove_file(probe.join("link"))?;
        for (name, file) in [("file", &regular), ("skip", &skipped)] {
            require(
                FileIdentity::read(files::open_regular(&probe.join(name))?.metadata()?)?
                    == FileIdentity::read(file.metadata()?)?,
                "private probe file changed before owned cleanup",
            )?;
            fs::remove_file(probe.join(name))?;
        }
        directory.revalidate()?;
        fs::remove_dir(probe.join("directory"))?;
        fs::remove_dir(&probe)?;
        self.revalidate()?;
        Ok(
            json!({"schema":"droidloom-native-label-preflight-v1","typed_file":typed_file,
            "typed_directory":typed_directory,"ordinary_symlink_label_readback":true,
            "excluded_private_file_identity_unchanged":true,"normal_private_probe":command,
            "complete_stage_dry_run":dry,"probe_inodes_removed":true,
            "production_paths_changed":false,"production_ready":false}),
        )
    }
    pub(super) fn apply_live_tree(&self, permit: &InstallationPermit) -> Result<Value> {
        self.revalidate()?;
        permit.revalidate()?;
        let mount_bytes = mountinfo()?;
        let root = File::open("/")?;
        let mount_id = mount_id(&root)?;
        let mut excluded = mount_exclusions(&mount_bytes, mount_id)?;
        excluded.extend(SKIP_TREES.iter().map(PathBuf::from));
        let skip = SKIP_FILES
            .iter()
            .map(|path| SkippedFile::open(Path::new(path)))
            .collect::<Result<Vec<_>>>()?;
        // libselinux 3.9 stops consuming its exclude list at the first missing
        // pathname. An absent first-install selection remains guarded absent;
        // it must not prevent later real userdata/fence exclusions being added.
        excluded.extend(
            skip.iter()
                .filter(|s| s.identity.is_some())
                .map(|s| s.path.clone()),
        );
        excluded = minimal_exclusions(excluded);
        for path in &excluded {
            fs::symlink_metadata(path)?;
        }
        let check = || -> Result<()> {
            permit.revalidate()?;
            require(
                mount_id == self::mount_id(&root)? && mountinfo()? == mount_bytes,
                "native mount namespace changed during ordinary labeling",
            )?;
            for file in &skip {
                file.revalidate()?;
            }
            Ok(())
        };
        check()?;
        let run = tempfile::Builder::new()
            .prefix("label-live-")
            .tempdir_in(&self.work.path)?
            .keep();
        let applied = self.run(
            &self.arguments(Path::new("/"), false, false, &excluded),
            &run.join("ordinary-setfiles.log"),
            Duration::from_secs(1800),
            &check,
        )?;
        // Apply the same native '/' match before the complete no-change check.
        let root_label = self.apply_file(&root, Path::new("/"))?;
        let verified = self.run(
            &self.arguments(Path::new("/"), true, true, &excluded),
            &run.join("ordinary-readback.log"),
            Duration::from_secs(1800),
            &check,
        )?;
        let readback = files::open_regular(&run.join("ordinary-readback.log"))?;
        let mut bytes = Vec::new();
        readback
            .take(16 * 1024 * 1024 + 1)
            .read_to_end(&mut bytes)?;
        require(
            bytes.len() <= 16 * 1024 * 1024
                && !bytes
                    .windows(b"Would relabel ".len())
                    .any(|w| w == b"Would relabel "),
            "normal complete native readback still reports contexts requiring relabeling",
        )?;
        check()?;
        self.revalidate()?;
        Ok(json!({"schema":"droidloom-normal-native-tree-labeling-v1",
            "normal_apply":applied,"normal_readback":verified,"root_label":root_label,
            "effective_exclusions":excluded,"fixed_skipped_files":SKIP_FILES,
            "absent_fixed_files_guarded_absent":skip.iter().filter(|s|s.identity.is_none()).map(|s|&s.path).collect::<Vec<_>>(),
            "original_skipped_file_identities_preserved":true,
            "root_mount_id":mount_id,"mountinfo_sha256":files::digest(&mount_bytes),
            "mount_snapshot_unchanged":true,"bulk_semantics":"ordinary setfiles pathname lsetfilecon, not atomic FD symlink labeling",
            "other_mounts_and_virtual_filesystems_excluded":true,"private_file_contents_read":false,
            "service_state_changed":false,"runtime_ready":false,"production_ready":false}))
    }
}

struct Owned {
    child: Child,
    pidfd: File,
    finished: bool,
}
impl Owned {
    fn signal(&self, signal: i32) -> Result<()> {
        if super::pidfd_exited(&self.pidfd)? {
            return Ok(());
        }
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                signal,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        } < 0
        {
            let e = std::io::Error::last_os_error();
            if e.raw_os_error() != Some(libc::ESRCH) {
                return Err(e.into());
            }
        }
        Ok(())
    }
    fn stop(&mut self) -> Result<()> {
        self.signal(libc::SIGTERM)?;
        let deadline = Instant::now() + Duration::from_secs(15);
        loop {
            if self.child.try_wait()?.is_some() {
                self.finished = true;
                return Ok(());
            }
            if Instant::now() >= deadline {
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        self.signal(libc::SIGKILL)?;
        self.child.wait()?;
        self.finished = true;
        Ok(())
    }
}
impl Drop for Owned {
    fn drop(&mut self) {
        if !self.finished {
            let _ = self.signal(libc::SIGKILL);
            let _ = self.child.wait();
        }
    }
}
struct SkippedFile {
    path: PathBuf,
    file: Option<File>,
    identity: Option<FileIdentity>,
}
impl SkippedFile {
    fn open(path: &Path) -> Result<Self> {
        match files::open_regular(path) {
            Ok(file) => {
                let identity = FileIdentity::read(file.metadata()?)?;
                require(
                    identity.uid == 0 && identity.gid == 0 && identity.links == 1,
                    "typed skipped file is not a unique protected root inode; pathname exclusion cannot protect aliases",
                )?;
                Ok(Self {
                    path: path.into(),
                    file: Some(file),
                    identity: Some(identity),
                })
            }
            Err(error)
                if error
                    .downcast_ref::<std::io::Error>()
                    .is_some_and(|e| e.kind() == std::io::ErrorKind::NotFound) =>
            {
                Ok(Self {
                    path: path.into(),
                    file: None,
                    identity: None,
                })
            }
            Err(error) => Err(error),
        }
    }
    fn revalidate(&self) -> Result<()> {
        let named = Self::open(&self.path)?;
        require(
            named.identity == self.identity,
            "a typed excluded object changed while ordinary labeling ran",
        )?;
        if let Some(file) = &self.file {
            require(
                Some(FileIdentity::read(file.metadata()?)?) == self.identity,
                "original excluded file ctime, bytes or metadata changed",
            )?;
        }
        Ok(())
    }
}
fn mountinfo() -> Result<Vec<u8>> {
    let file = File::open("/proc/self/mountinfo")?;
    let mut stat: libc::statfs = unsafe { std::mem::zeroed() };
    require(
        unsafe { libc::fstatfs(file.as_raw_fd(), &mut stat) } == 0
            && stat.f_type == libc::PROC_SUPER_MAGIC,
        "mount inventory is not the actual kernel proc filesystem",
    )?;
    let mut bytes = Vec::new();
    file.take(4 * 1024 * 1024 + 1).read_to_end(&mut bytes)?;
    require(
        !bytes.is_empty() && bytes.len() <= 4 * 1024 * 1024,
        "native mount inventory exceeds bound",
    )?;
    Ok(bytes)
}
fn mount_id(file: &File) -> Result<u64> {
    let mut st: libc::statx = unsafe { std::mem::zeroed() };
    if unsafe {
        libc::statx(
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH | libc::AT_SYMLINK_NOFOLLOW,
            libc::STATX_MNT_ID,
            &mut st,
        )
    } != 0
    {
        return Err(std::io::Error::last_os_error().into());
    }
    require(
        st.stx_mask & libc::STATX_MNT_ID != 0 && st.stx_mnt_id > 0,
        "root has no actual mount identity",
    )?;
    Ok(st.stx_mnt_id)
}
fn decode_mount_path(raw: &[u8]) -> Result<PathBuf> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < raw.len() {
        if raw[i] == b'\\' {
            require(i + 4 <= raw.len(), "truncated kernel mount escape")?;
            let value = match &raw[i + 1..i + 4] {
                b"040" => b' ',
                b"011" => b'\t',
                b"012" => b'\n',
                b"134" => b'\\',
                _ => return Err("noncanonical kernel mount escape".into()),
            };
            out.push(value);
            i += 4;
        } else {
            out.push(raw[i]);
            i += 1;
        }
    }
    let path = PathBuf::from(OsString::from_vec(out));
    canonical_path(&path)?;
    Ok(path)
}
fn minimal_exclusions(input: BTreeSet<PathBuf>) -> BTreeSet<PathBuf> {
    let mut result = BTreeSet::<PathBuf>::new();
    for path in input {
        if !result.iter().any(|parent| path.starts_with(parent)) {
            result.insert(path);
        }
    }
    result
}
fn mount_exclusions(bytes: &[u8], root_id: u64) -> Result<BTreeSet<PathBuf>> {
    let mut result = BTreeSet::new();
    let mut ids = BTreeSet::new();
    let mut root_seen = false;
    for line in bytes.split(|b| *b == b'\n').filter(|l| !l.is_empty()) {
        let fields = line.split(|b| *b == b' ').collect::<Vec<_>>();
        require(
            fields.len() >= 10
                && fields
                    .iter()
                    .position(|v| *v == b"-")
                    .is_some_and(|n| n >= 6 && n + 3 < fields.len()),
            "malformed actual mount inventory",
        )?;
        let id = std::str::from_utf8(fields[0])?.parse::<u64>()?;
        require(
            id > 0 && ids.insert(id) && ids.len() <= 32768,
            "duplicate or excessive kernel mount identity",
        )?;
        let path = decode_mount_path(fields[4])?;
        if id == root_id {
            require(
                path == Path::new("/"),
                "held root mount is not the native root",
            )?;
            root_seen = true;
        } else {
            require(
                path != Path::new("/"),
                "stacked root mounts are outside first activation",
            )?;
            result.insert(path);
        }
    }
    require(
        root_seen,
        "held native root is absent from actual mountinfo",
    )?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn canonical_lookup_paths_reject_ambiguous_authority() {
        for p in [
            "relative",
            "/usr//bin",
            "/usr/../etc",
            "/./etc",
            "/usr/",
            "/bad\0name",
        ] {
            assert!(canonical_path(Path::new(p)).is_err(), "{p:?}");
        }
        assert!(canonical_path(Path::new("/")).is_ok());
        assert!(canonical_path(Path::new("/home/user/some file")).is_ok());
    }
    #[test]
    fn mount_exclusions_cover_same_filesystem_bind_mounts() {
        let raw=b"10 1 8:1 / / rw - ext4 /dev/root rw\n11 10 8:1 /other /bind rw - ext4 /dev/root rw\n12 10 0:5 / /run rw - tmpfs tmpfs rw\n";
        let excluded = mount_exclusions(raw, 10).unwrap();
        assert!(excluded.contains(Path::new("/bind")));
        assert!(excluded.contains(Path::new("/run")));
        assert!(!excluded.contains(Path::new("/")));
        assert!(mount_exclusions(raw, 99).is_err());
        assert!(
            mount_exclusions(
                b"10 1 8:1 / / rw - ext4 /dev/root rw\n10 1 8:1 / /x rw - ext4 /dev/root rw\n",
                10
            )
            .is_err()
        );
    }
    #[test]
    fn mount_root_identity_cannot_name_a_subtree_or_hide_a_stacked_root() {
        assert!(mount_exclusions(b"10 1 8:1 / /subtree rw - ext4 /dev/root rw\n", 10).is_err());
        assert!(
            mount_exclusions(
                b"10 1 8:1 / / rw - ext4 /dev/root rw\n11 10 8:1 /other / rw - ext4 /dev/root rw\n",
                10
            )
            .is_err()
        );
    }
    #[test]
    fn mount_paths_are_kernel_decoded_without_aliases() {
        assert_eq!(
            decode_mount_path(br"/with\040space/back\134slash").unwrap(),
            Path::new("/with space/back\\slash")
        );
        for bad in [
            br"/bad\000nul".as_slice(),
            br"/bad\04".as_slice(),
            b"/../escape".as_slice(),
            b"relative".as_slice(),
        ] {
            assert!(decode_mount_path(bad).is_err());
        }
    }
    #[test]
    fn covered_mounts_are_pruned_without_excluding_similarly_named_siblings() {
        let exclusions = minimal_exclusions(
            [
                "/proc",
                "/proc/sys",
                "/proc/sys/kernel",
                "/process",
                "/run",
                "/run/user",
            ]
            .into_iter()
            .map(PathBuf::from)
            .collect(),
        );
        assert_eq!(
            exclusions,
            ["/proc", "/process", "/run"]
                .into_iter()
                .map(PathBuf::from)
                .collect()
        );
    }
    #[test]
    fn fixed_skip_set_includes_every_original_typed_owner() {
        assert_eq!(SKIP_FILES.len(), 7);
        for path in [
            "/etc/droidloom/setup.lock",
            "/etc/droidloom/cell.json",
            "/etc/droidloom/production/package-maintenance.json",
            "/var/lib/droidloom/users/1000/data/data.img",
            "/var/lib/droidloom/users/1000/data/metadata.img",
        ] {
            assert!(SKIP_FILES.contains(&path));
        }
        assert!(SKIP_TREES.contains(&"/var/lib/droidloom/activation-staging"));
    }
    #[test]
    fn symlink_and_hardlink_skip_objects_cannot_hide_a_typed_alias() {
        let root = tempfile::tempdir().unwrap();
        let original = root.path().join("original");
        fs::write(&original, b"private").unwrap();
        let alias = root.path().join("alias");
        fs::hard_link(&original, &alias).unwrap();
        assert!(SkippedFile::open(&original).is_err());
        fs::remove_file(&alias).unwrap();
        std::os::unix::fs::symlink("original", &alias).unwrap();
        assert!(SkippedFile::open(&alias).is_err());
    }
}
