//! Fixed original-machine return entry. This does not install, arm a boot,
//! open or ping a watchdog, grant permanent activation, or claim retirement.
use crate::{
    native_hardware_label as held, native_once_capabilities as caps, native_once_contract as c,
};
use c::{PayloadPin, ReturnConfiguration, reject};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    ffi::{CString, OsString},
    fs::{File, OpenOptions},
    io::{self, Read, Seek, SeekFrom, Write},
    os::{
        fd::AsRawFd,
        unix::{
            ffi::OsStrExt,
            fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
            process::CommandExt,
        },
    },
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, Instant},
};
#[path = "native_working_return.rs"]
mod working;
const ENTRY: &str = "__original-once-return";
const ROLE: &[u8] = b"u:system_r:p4_linux_once_return_t:s0";
const PROFILE: &[u8] = b"droidloom-original-once-return (enforce)";
const CONFIG_LABEL: &[u8] = b"u:object_r:p4_linux_once_config_t:s0";
const EVIDENCE_LABEL: &[u8] = b"u:object_r:p4_linux_once_evidence_t:s0";
// journalctl's 8MiB JSON may expand under Python's ensure_ascii serialization.
const MAX_OUTPUT: u64 = 64 * 1024 * 1024;
#[derive(Clone, Debug, Eq, PartialEq)]
struct Identity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
}
impl From<std::fs::Metadata> for Identity {
    fn from(m: std::fs::Metadata) -> Self {
        Self {
            dev: m.dev(),
            ino: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.size(),
            mtime: m.mtime(),
            mtime_ns: m.mtime_nsec(),
            ctime: m.ctime(),
            ctime_ns: m.ctime_nsec(),
        }
    }
}
fn hash(b: &[u8]) -> String {
    format!("{:x}", Sha256::digest(b))
}
fn root_directory(path: &Path) -> io::Result<File> {
    if !path.is_absolute() {
        return Err(reject("once path must be absolute"));
    }
    let mut f = held::path_at(libc::AT_FDCWD, c"/")?;
    held::directory(&f)?;
    for p in path.components().skip(1) {
        let std::path::Component::Normal(p) = p else {
            return Err(reject("once path is not canonical"));
        };
        f = held::path_at(
            f.as_raw_fd(),
            &CString::new(p.as_bytes()).map_err(io::Error::other)?,
        )?;
        held::directory(&f)?;
    }
    Ok(f)
}
struct Input {
    path: PathBuf,
    file: File,
    identity: Identity,
    pin: PayloadPin,
}
impl Input {
    fn open(
        path: &Path,
        pin: &PayloadPin,
        modes: &[u32],
        label: Option<&[u8]>,
    ) -> io::Result<Self> {
        pin.validate(128 * 1024 * 1024)?;
        let parent = root_directory(
            path.parent()
                .ok_or_else(|| reject("missing input parent"))?,
        )?;
        let leaf = CString::new(
            path.file_name()
                .ok_or_else(|| reject("missing input name"))?
                .as_bytes(),
        )
        .map_err(io::Error::other)?;
        let descriptor = held::path_at(parent.as_raw_fd(), &leaf)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(path)?;
        let identity = Identity::from(file.metadata()?);
        let original = Identity::from(descriptor.metadata()?);
        if identity != original
            || identity.mode & libc::S_IFMT != libc::S_IFREG
            || !modes.contains(&(identity.mode & 0o7777))
            || identity.uid != 0
            || identity.gid != 0
            || identity.links != 1
            || identity.bytes != pin.bytes
        {
            return Err(reject("fixed once input metadata differs"));
        }
        if let Some(label) = label {
            if held::label(&descriptor)? != label {
                return Err(reject("fixed once input label differs"));
            }
        }
        let result = Self {
            path: path.into(),
            file,
            identity,
            pin: pin.clone(),
        };
        result.bytes()?;
        Ok(result)
    }
    fn revalidate(&self) -> io::Result<()> {
        let parent = root_directory(
            self.path
                .parent()
                .ok_or_else(|| reject("input parent changed"))?,
        )?;
        let leaf = CString::new(
            self.path
                .file_name()
                .ok_or_else(|| reject("input leaf changed"))?
                .as_bytes(),
        )
        .map_err(io::Error::other)?;
        let named = held::path_at(parent.as_raw_fd(), &leaf)?;
        if Identity::from(self.file.metadata()?) != self.identity
            || Identity::from(named.metadata()?) != self.identity
        {
            return Err(reject("once input identity changed"));
        }
        Ok(())
    }
    fn bytes(&self) -> io::Result<Vec<u8>> {
        self.revalidate()?;
        let mut f = self.file.try_clone()?;
        f.seek(SeekFrom::Start(0))?;
        let mut b = Vec::new();
        f.take(self.pin.bytes + 1).read_to_end(&mut b)?;
        self.revalidate()?;
        if b.len() as u64 != self.pin.bytes || hash(&b) != self.pin.sha256 {
            return Err(reject("held once input bytes differ"));
        }
        Ok(b)
    }
}
fn text(path: &Path, limit: u64) -> io::Result<String> {
    let mut b = Vec::new();
    File::open(path)?.take(limit + 1).read_to_end(&mut b)?;
    if b.len() as u64 > limit {
        return Err(reject("public once observation exceeds bound"));
    }
    Ok(String::from_utf8(b)
        .map_err(io::Error::other)?
        .trim_end_matches(['\0', '\n'])
        .to_owned())
}
fn monotonic() -> io::Result<u64> {
    let mut t = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t) } != 0 {
        return Err(io::Error::last_os_error());
    }
    u64::try_from(t.tv_sec).map_err(io::Error::other)
}
fn filesystem(f: &File, magic: libc::c_long) -> io::Result<()> {
    let mut v = std::mem::MaybeUninit::<libc::statfs>::uninit();
    if unsafe { libc::fstatfs(f.as_raw_fd(), v.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { v.assume_init() }.f_type != magic {
        return Err(reject("once observation filesystem differs"));
    }
    Ok(())
}
struct Owner {
    root: File,
    boot_id: String,
    pid: u32,
    config: ReturnConfiguration,
    inputs: Vec<Input>,
}
impl Owner {
    fn open() -> io::Result<Self> {
        let root = root_directory(Path::new("/"))?;
        filesystem(&root, 0xef53)?;
        held::namespaces(&root)?;
        let proc = root_directory(Path::new("/proc"))?;
        filesystem(&proc, 0x9fa0)?;
        // The original PID1 owns the recorded mount namespace for this
        // whole boot. A self-MNT bind is deliberately not used: it would form
        // a reference cycle. No foreign /proc/1 namespace/root is inspected.
        let rm = root.metadata()?;
        if rm.ino() != 2 {
            return Err(reject("once return is not the actual ext4 root inode"));
        }
        let block = std::fs::metadata(format!("/dev/disk/by-uuid/{}", c::ROOT_UUID))?;
        if block.mode() & libc::S_IFMT != libc::S_IFBLK || block.rdev() != rm.dev() {
            return Err(reject("once return is not on the original root UUID"));
        }
        if text(Path::new("/proc/sys/kernel/osrelease"), 256)? != c::KERNEL
            || text(Path::new("/sys/fs/selinux/enforce"), 8)? != "1"
        {
            return Err(reject("once return needs its selected enforcing kernel"));
        }
        let args = c::boot_arguments(&text(Path::new("/proc/cmdline"), 32768)?)?;
        let path = Path::new(c::RETURN_CONFIG);
        let size = std::fs::symlink_metadata(path)?.len();
        if size > 65536 {
            return Err(reject("return config exceeds bound"));
        }
        let input = Input::open(
            path,
            &PayloadPin {
                bytes: size,
                sha256: args["droidloom.once.return"].clone(),
            },
            &[0o400],
            Some(CONFIG_LABEL),
        )?;
        let config: ReturnConfiguration =
            serde_json::from_slice(&input.bytes()?).map_err(io::Error::other)?;
        config.validate()?;
        if args["droidloom.once"] != config.intent_sha256
            || args["droidloom.once.config"] != config.early_config_sha256
        {
            return Err(reject("return config differs from the durable boot intent"));
        }
        let boot_id = text(Path::new("/proc/sys/kernel/random/boot_id"), 64)?;
        if !c::uuid(&boot_id) || boot_id == config.original_boot_id {
            return Err(reject("once return did not enter a fresh candidate boot"));
        }
        let executable = Input::open(
            Path::new(c::RETURN_EXECUTABLE),
            &config.executable,
            &[0o755],
            None,
        )?;
        if Identity::from(std::fs::metadata("/proc/self/exe")?) != executable.identity {
            return Err(reject("once return is not its normal executable"));
        }
        let maintenance = Input::open(
            Path::new(c::MAINTENANCE_EXECUTABLE),
            &config.maintenance,
            &[0o755],
            None,
        )?;
        let installation = Input::open(
            Path::new(c::INSTALLATION),
            &config.installation,
            &[0o400, 0o444],
            None,
        )?;
        let cell = Input::open(
            Path::new("/etc/droidloom/cell.json"),
            &config.cell,
            &[0o644],
            None,
        )?;
        let selection = Input::open(
            Path::new("/etc/droidloom/production/selected.json"),
            &config.selection,
            &[0o400],
            None,
        )?;
        let v: Value = serde_json::from_slice(&installation.bytes()?).map_err(io::Error::other)?;
        if v["schema"] != "droidloom-maintenance-installation-v1"
            || v["root_uuid"] != c::ROOT_UUID
            || v["original_kernel"] != c::ORIGINAL_KERNEL
            || v["original_entry"] != c::ORIGINAL_ENTRY
        {
            return Err(reject("maintenance is not bound to the original entry"));
        }
        let witness_path = Path::new("/run/droidloom-early/host-mount-identity.json");
        let witness_parent = root_directory(witness_path.parent().unwrap())?;
        if held::label(&witness_parent)? != b"u:object_r:p4_linux_early_handoff_dir_t:s0" {
            return Err(reject("mount witness parent is not the original publisher"));
        }
        let mut witness_file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(witness_path)?;
        let before = Identity::from(witness_file.metadata()?);
        if before.mode != libc::S_IFREG | 0o400
            || before.uid != 0
            || before.gid != 0
            || before.links != 1
            || before.bytes == 0
            || before.bytes >= 512
        {
            return Err(reject(
                "mount identity witness is not its bounded original inode",
            ));
        }
        let mut body = Vec::new();
        (&mut witness_file).take(512).read_to_end(&mut body)?;
        if Identity::from(witness_file.metadata()?) != before || body.len() as u64 != before.bytes {
            return Err(reject("mount identity witness changed during readback"));
        }
        let witness = Input::open(
            witness_path,
            &PayloadPin {
                bytes: before.bytes,
                sha256: hash(&body),
            },
            &[0o400],
            Some(b"u:object_r:p4_linux_host_mount_identity_t:s0"),
        )?;
        let value = Self {
            root,
            boot_id,
            pid: std::process::id(),
            config,
            inputs: vec![
                input,
                executable,
                maintenance,
                installation,
                cell,
                selection,
                witness,
            ],
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> io::Result<()> {
        caps::revalidate()?;
        if self.pid != std::process::id()
            || held::current(101)? != ROLE
            || held::current(104)? != PROFILE
            || text(Path::new("/proc/sys/kernel/random/boot_id"), 64)? != self.boot_id
            || text(Path::new("/sys/fs/selinux/enforce"), 8)? != "1"
        {
            return Err(reject("once return lost boot, process or MAC custody"));
        }
        held::namespaces(&self.root)?;
        for i in &self.inputs {
            i.revalidate()?;
        }
        self.mount_namespace()?;
        self.watchdog()
    }
    fn mount_namespace(&self) -> io::Result<()> {
        #[derive(serde::Deserialize)]
        #[serde(deny_unknown_fields)]
        struct Witness {
            schema: String,
            boot_id: String,
            joint_policy_sha256: String,
            device: u64,
            inode: u64,
        }
        let w: Witness =
            serde_json::from_slice(&self.inputs[6].bytes()?).map_err(io::Error::other)?;
        if w.schema != "droidloom.host-mount-identity.v1"
            || w.boot_id != self.boot_id
            || w.joint_policy_sha256 != self.config.joint_policy_sha256
        {
            return Err(reject(
                "mount identity is not from this source-bound original boot",
            ));
        }
        let actual = File::open("/proc/self/ns/mnt")?;
        filesystem(&actual, 0x6e736673)?;
        let m = actual.metadata()?;
        if (m.dev(), m.ino()) != (w.device, w.inode)
            || unsafe {
                libc::ioctl(
                    actual.as_raw_fd(),
                    0xb703 as libc::c_ulong,
                    0 as libc::c_ulong,
                )
            } != libc::CLONE_NEWNS
        {
            return Err(reject(
                "once return left the actual original mount namespace",
            ));
        }
        Ok(())
    }

    fn watchdog(&self) -> io::Result<()> {
        let sys = root_directory(Path::new("/sys"))?;
        filesystem(&sys, 0x62656572)?;
        // The exact selected softdog module declares its parameters with
        // sysfs permission 0: no /sys/module/softdog/parameters files exist.
        // Their values are bound by the admitted normal initrd and its exact
        // early helper invocation. Read the kernel's real watchdog attributes
        // here; never claim a readback of nonexistent parameter files.
        let base = Path::new("/sys/devices/virtual/watchdog");
        let parent = root_directory(base)?;
        let mut count = 0;
        let mut total = 0;
        for row in std::fs::read_dir(base)? {
            total += 1;
            if total > 16 {
                return Err(reject("virtual watchdog inventory exceeds bound"));
            }
            let row = row?;
            let name = row.file_name();
            let name = name
                .to_str()
                .ok_or_else(|| reject("invalid watchdog name"))?;
            let n = name
                .strip_prefix("watchdog")
                .ok_or_else(|| reject("unexpected watchdog child"))?;
            if n.is_empty() || n.len() > 3 || !n.bytes().all(|b| b.is_ascii_digit()) {
                return Err(reject("noncanonical watchdog number"));
            }
            let f = held::path_at(
                parent.as_raw_fd(),
                &CString::new(name).map_err(io::Error::other)?,
            )?;
            held::directory(&f)?;
            filesystem(&f, 0x62656572)?;
            if text(&row.path().join("identity"), 128)? == "Software Watchdog" {
                count += 1;
                if text(&row.path().join("state"), 32)? != "active"
                    || text(&row.path().join("nowayout"), 32)? != "1"
                    || text(&row.path().join("timeout"), 32)?
                        != self.config.recovery.watchdog_seconds.to_string()
                {
                    return Err(reject("software watchdog is not actually armed"));
                }
            }
        }
        if count != 1 {
            return Err(reject("software watchdog identity is not unique"));
        }
        Ok(())
    }
    fn wait_until(&self, time: u32) -> io::Result<()> {
        while monotonic()? < u64::from(time) {
            self.revalidate()?;
            thread::sleep(Duration::from_secs(1));
        }
        self.revalidate()
    }
}
struct Evidence {
    path: PathBuf,
    directory: File,
    dev: u64,
    ino: u64,
    lock: File,
    lock_identity: Identity,
}
impl Evidence {
    fn open(owner: &Owner) -> io::Result<Self> {
        Self::open_path(owner.config.runtime_evidence_directory(), EVIDENCE_LABEL)
    }
    fn open_path(path: PathBuf, label: &[u8]) -> io::Result<Self> {
        let held = root_directory(&path)?;
        let st = held.metadata()?;
        if st.mode() & 0o7777 != 0o700 || held::label(&held)? != label {
            return Err(reject("return evidence directory is not prepared"));
        }
        let directory = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)?;
        if (directory.metadata()?.dev(), directory.metadata()?.ino()) != (st.dev(), st.ino()) {
            return Err(reject("evidence directory was replaced"));
        }
        let lock = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(path.join("owner.lock"))?;
        let m = lock.metadata()?;
        if !m.is_file()
            || m.uid() != 0
            || m.gid() != 0
            || m.mode() & 0o7777 != 0o400
            || m.nlink() != 1
            || m.len() != 0
        {
            return Err(reject("once runtime lock is not its prepared inode"));
        }
        if unsafe { libc::flock(lock.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let v = Self {
            path,
            directory,
            dev: st.dev(),
            ino: st.ino(),
            lock,
            lock_identity: Identity::from(m),
        };
        v.revalidate()?;
        Ok(v)
    }
    fn revalidate(&self) -> io::Result<()> {
        let named = root_directory(&self.path)?;
        let st = named.metadata()?;
        if st.dev() != self.dev
            || st.ino() != self.ino
            || st.mode() & 0o7777 != 0o700
            || Identity::from(self.lock.metadata()?) != self.lock_identity
            || Identity::from(std::fs::symlink_metadata(self.path.join("owner.lock"))?)
                != self.lock_identity
        {
            return Err(reject("once runtime owner or directory changed"));
        }
        Ok(())
    }
    fn create(&self, name: &str) -> io::Result<File> {
        self.revalidate()?;
        if name.is_empty()
            || name.len() > 64
            || !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b".-_".contains(&b))
        {
            return Err(reject("invalid evidence member"));
        }
        let f = OpenOptions::new()
            .read(true)
            .write(true)
            .create_new(true)
            .mode(0o600)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(self.path.join(name))?;
        self.directory.sync_all()?;
        Ok(f)
    }
    fn record(&self, name: &str, value: Value) -> io::Result<()> {
        let mut f = self.create(name)?;
        let mut b = serde_json::to_vec(&value).map_err(io::Error::other)?;
        b.push(b'\n');
        if b.len() > 1024 * 1024 {
            return Err(reject("evidence record exceeds bound"));
        }
        f.write_all(&b)?;
        f.sync_all()?;
        f.set_permissions(std::fs::Permissions::from_mode(0o400))?;
        f.sync_all()?;
        self.directory.sync_all()?;
        self.revalidate()
    }
    fn seal(&self, name: &str, mut f: File) -> io::Result<(PayloadPin, Vec<u8>)> {
        f.sync_all()?;
        let before = Identity::from(f.metadata()?);
        if before.bytes > MAX_OUTPUT {
            return Err(reject("maintenance output exceeds bound"));
        }
        f.seek(SeekFrom::Start(0))?;
        let mut b = Vec::new();
        (&mut f).take(MAX_OUTPUT + 1).read_to_end(&mut b)?;
        if b.len() as u64 != before.bytes
            || Identity::from(f.metadata()?) != before
            || Identity::from(std::fs::symlink_metadata(self.path.join(name))?) != before
        {
            return Err(reject("maintenance output changed before sealing"));
        }
        f.set_permissions(std::fs::Permissions::from_mode(0o400))?;
        f.sync_all()?;
        self.directory.sync_all()?;
        Ok((
            PayloadPin {
                bytes: b.len() as u64,
                sha256: hash(&b),
            },
            b,
        ))
    }
}

trait MaintenanceOwner {
    fn revalidate(&self) -> io::Result<()>;
    fn maintenance(&self) -> &Input;
    fn intent(&self) -> &str;
    fn boot(&self) -> &str;
    fn command_schema(&self) -> &'static str;
    fn incomplete_schema(&self) -> &'static str;
}
impl MaintenanceOwner for Owner {
    fn revalidate(&self) -> io::Result<()> { Owner::revalidate(self) }
    fn maintenance(&self) -> &Input { &self.inputs[2] }
    fn intent(&self) -> &str { &self.config.intent_sha256 }
    fn boot(&self) -> &str { &self.boot_id }
    fn command_schema(&self) -> &'static str { "droidloom.original-once-maintenance-command.v1" }
    fn incomplete_schema(&self) -> &'static str { "droidloom.original-once-incomplete-command.v1" }
}
fn command(owner: &impl MaintenanceOwner, e: &Evidence, verb: &'static str, seconds: u64) -> io::Result<Value> {
    if !["collect", "rollback", "reboot"].contains(&verb) {
        return Err(reject("not a fixed maintenance operation"));
    }
    owner.revalidate()?;
    e.revalidate()?;
    let out_name = format!("{verb}.stdout");
    let err_name = format!("{verb}.stderr");
    let out = e.create(&out_name)?;
    let err = e.create(&err_name)?;
    e.record(&format!("{verb}-INTENT.json"),json!({"schema":owner.command_schema(),"intent_sha256":owner.intent(),"boot_id":owner.boot(),"verb":verb,"started_monotonic":monotonic()?,"timeout_seconds":seconds,"completed":false}))?;
    let fd = owner.maintenance().file.as_raw_fd();
    let argv = [
        CString::new(c::MAINTENANCE_EXECUTABLE).unwrap(),
        CString::new(verb).unwrap(),
    ];
    let env = [
        CString::new("PATH=/usr/sbin:/usr/bin:/sbin:/bin").unwrap(),
        CString::new("LC_ALL=C").unwrap(),
    ];
    let mut cmd = Command::new(c::MAINTENANCE_EXECUTABLE);
    cmd.arg(verb)
        .env_clear()
        .stdin(Stdio::null())
        .stdout(out.try_clone()?)
        .stderr(err.try_clone()?);
    // Execute the already pinned normal inode. The fixed C maintenance entry
    // independently checks its own ELF, source interpreter and MAC context.
    unsafe {
        cmd.pre_exec(move || {
            let args = [argv[0].as_ptr(), argv[1].as_ptr(), std::ptr::null()];
            let vars = [env[0].as_ptr(), env[1].as_ptr(), std::ptr::null()];
            libc::syscall(
                libc::SYS_execveat,
                fd,
                c"".as_ptr(),
                args.as_ptr(),
                vars.as_ptr(),
                libc::AT_EMPTY_PATH,
            );
            Err(io::Error::last_os_error())
        });
    }
    let start = Instant::now();
    let mut child = cmd.spawn()?;
    let status = loop {
        if let Some(s) = child.try_wait()? {
            break s;
        }
        if start.elapsed() >= Duration::from_secs(seconds) {
            e.record(&format!("{verb}-TIMEOUT.json"),json!({"schema":owner.incomplete_schema(),"boot_id":owner.boot(),"verb":verb,"child_pid":child.id(),"completed":false,"outputs_sealed":false,"ordinary_shutdown_verified":false}))?;
            // The fixed service owns this child cgroup. Unit failure stops it
            // normally; the already armed software watchdog uses the preserved
            // original default. Never race another maintenance command against
            // an incomplete collector or manufacture a completed output pin.
            return Err(reject(
                "normal maintenance exceeded its bounded source contract",
            ));
        }
        if out.metadata()?.len() > MAX_OUTPUT || err.metadata()?.len() > 65536 {
            return Err(reject("maintenance exceeded its output bound"));
        }
        thread::sleep(Duration::from_millis(50));
    };
    let (out_pin, b) = e.seal(&out_name, out)?;
    let (err_pin, _) = e.seal(&err_name, err)?;
    e.record(&format!("{verb}-RESULT.json"),json!({"schema":owner.command_schema(),"intent_sha256":owner.intent(),"boot_id":owner.boot(),"verb":verb,"exit_code":status.code(),"seconds":start.elapsed().as_secs_f64(),"completed":true,"stdout":out_pin,"stderr":err_pin}))?;
    if !status.success() {
        return Err(reject("normal maintenance returned failure"));
    }
    owner.revalidate()?;
    serde_json::from_slice(&b).map_err(io::Error::other)
}
fn normal_collection(v: &Value, boot: &str) -> bool {
    let status = |s: &Value| {
        s["boot_id"] == boot
            && s["kernel"] == c::KERNEL
            && s["selinux_enforcing"] == true
            && s["selinux_context"] == "u:system_r:p4_linux_maintenance_t:s0"
            && s["system_units"]["exit"] == 0
            && s["user_units"]["exit"] == 0
            && s["system_units"]["observation_failed"] != true
            && s["user_units"]["observation_failed"] != true
    };
    v["schema"] == "droidloom-maintenance-evidence-v1"
        && v["same_boot"] == true
        && v["journal_exit"] == 0
        && v["journal"].is_array()
        && status(v)
        && status(&v["status_after"])
}
// These are the actual fixed normal producer's response fields. A boolean or
// a caller's desired entry is not a substitute for its successful readback.
fn original_selected(v: &Value) -> bool {
    v["schema"] == "droidloom-maintenance-rollback-v1"
        && v["original_entry"] == c::ORIGINAL_ENTRY
        && v["reboot_requested"] == false
}
fn original_reboot_requested(v: &Value) -> bool {
    v["schema"] == "droidloom-maintenance-reboot-v1"
        && v["requested"] == true
        && v["target"] == c::ORIGINAL_ENTRY
        && v["completed"] == false
}
pub fn dispatch(args: &[OsString]) -> io::Result<bool> {
    if working::dispatch(args)? { return Ok(true); }
    let requested = args.first().is_some_and(|v| v == ENTRY);
    let own = held::current(101).as_ref().is_ok_and(|v| v == ROLE);
    if !requested && !own {
        return Ok(false);
    }
    if !requested || args.len() != 1 || !own || held::current(104)? != PROFILE {
        return Err(reject(
            "once return requires its fixed executable and MAC identities",
        ));
    }
    caps::seal()?;
    let owner = Owner::open()?;
    let e = Evidence::open(&owner)?;
    e.record("CANDIDATE-OBSERVED.json",json!({"schema":"droidloom.original-once-candidate-observed.v1","intent_sha256":owner.config.intent_sha256,"candidate_id":owner.config.candidate_id,"boot_id":owner.boot_id,"original_boot_id":owner.config.original_boot_id,"monotonic":monotonic()?,"software_watchdog_active":true,"hardware_hard_hang_coverage":false,"production_ready":false}))?;
    owner.wait_until(owner.config.recovery.collect_at_boot_seconds)?;
    let enough = monotonic()?
        .checked_add(u64::from(c::COLLECT_BUDGET_SECONDS) + 30)
        .is_some_and(|n| n <= u64::from(owner.config.recovery.return_at_boot_seconds));
    let collected = if enough {
        let v = command(&owner, &e, "collect", u64::from(c::COLLECT_BUDGET_SECONDS))?;
        let complete = normal_collection(&v, &owner.boot_id);
        e.record("COLLECTION-OBSERVED.json",json!({"schema":"droidloom.original-once-collection-observed.v1","boot_id":owner.boot_id,"normal_maintenance_collection_complete":complete,"ordinary_shutdown_verified":false,"production_ready":false}))?;
        complete
    } else {
        e.record("COLLECTION-SKIPPED.json",json!({"schema":"droidloom.original-once-failed-collection.v1","boot_id":owner.boot_id,"reason":"entry started too late for the complete normal collector budget","normal_maintenance_collection_complete":false,"production_ready":false}))?;
        false
    };
    owner.wait_until(owner.config.recovery.return_at_boot_seconds)?;
    let rollback = command(&owner, &e, "rollback", 30)?;
    if !original_selected(&rollback) {
        return Err(reject(
            "maintenance did not read back the original next entry",
        ));
    }
    e.record("RETURN-SELECTED.json",json!({"schema":"droidloom.original-once-return-selected.v1","intent_sha256":owner.config.intent_sha256,"boot_id":owner.boot_id,"normal_maintenance_collection_complete":collected,"maintenance":rollback,"original_return_observed":false,"production_ready":false}))?;
    let reboot = command(&owner, &e, "reboot", 30)?;
    if !original_reboot_requested(&reboot) {
        return Err(reject(
            "maintenance did not accept the fixed original return request",
        ));
    }
    e.record("RETURN-REQUESTED.json",json!({"schema":"droidloom.original-once-return-requested.v1","intent_sha256":owner.config.intent_sha256,"boot_id":owner.boot_id,"normal_maintenance_collection_complete":collected,"maintenance":reboot,"original_return_observed":false,"ordinary_shutdown_verified":false,"production_ready":false}))?;
    Ok(true)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn other_role_cannot_select_return_or_supply_a_path() {
        assert!(dispatch(&[ENTRY.into()]).is_err());
        assert!(dispatch(&[ENTRY.into(), "/tmp/return.json".into()]).is_err());
    }
    #[test]
    fn only_actual_fixed_maintenance_protocol_can_select_and_request_return() {
        let mut selection = json!({"schema":"droidloom-maintenance-rollback-v1",
            "original_entry":c::ORIGINAL_ENTRY,"reboot_requested":false});
        assert!(original_selected(&selection));
        assert!(!original_selected(&json!({"next_entry":c::ORIGINAL_ENTRY})));
        selection["reboot_requested"] = json!(true);
        assert!(!original_selected(&selection));
        let mut request = json!({"schema":"droidloom-maintenance-reboot-v1",
            "requested":true,"target":c::ORIGINAL_ENTRY,"completed":false});
        assert!(original_reboot_requested(&request));
        request["completed"] = json!(true);
        assert!(!original_reboot_requested(&request));
        request["completed"] = json!(false);
        request["target"] = json!("another-entry");
        assert!(!original_reboot_requested(&request));
    }
    #[test]
    fn incomplete_or_other_boot_status_never_counts_as_collection() {
        let boot = "11111111-1111-1111-1111-111111111111";
        let status = json!({"boot_id":boot,"kernel":c::KERNEL,"selinux_enforcing":true,"selinux_context":"u:system_r:p4_linux_maintenance_t:s0","system_units":{"exit":0},"user_units":{"exit":0}});
        let mut v = status.clone();
        v["schema"] = json!("droidloom-maintenance-evidence-v1");
        v["same_boot"] = json!(true);
        v["journal_exit"] = json!(0);
        v["journal"] = json!([]);
        v["status_after"] = status;
        assert!(normal_collection(&v, boot));
        v["status_after"]["user_units"]["exit"] = Value::Null;
        assert!(!normal_collection(&v, boot));
        v["status_after"]["user_units"]["exit"] = json!(0);
        assert!(!normal_collection(
            &v,
            "22222222-2222-2222-2222-222222222222"
        ));
    }
}
