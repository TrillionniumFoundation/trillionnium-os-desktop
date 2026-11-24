//! Normal Debian installation of the two exact reviewed native packages.
//! Stage receipts describe material only. Only the original installation
//! owner's held permit authorizes dpkg to modify the live machine.
use super::{
    Result,
    activation_files::{self as files, FilePin, HeldFile},
    activation_owner::InstallationPermit,
    activation_platform::{
        NativeDefinition, native_definition, native_path_allowed, parse_native_tar,
    },
};
use serde_json::{Value, json};
use std::{
    cell::Cell,
    collections::{BTreeMap, BTreeSet},
    ffi::{CStr, CString},
    fs::{self, File},
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{
            fs::{FileExt, MetadataExt},
            process::CommandExt,
        },
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

const MIB: u64 = 1024 * 1024;
const STAGING: &str = "/var/lib/droidloom/activation-staging";
const STATUS: &str = "/var/lib/dpkg/status";
const INFO: &str = "/var/lib/dpkg/info";
const SHOW: &str = concat!(
    "$",
    "{Package}\t",
    "$",
    "{Version}\t",
    "$",
    "{Architecture}\t",
    "$",
    "{Status}\n"
);

fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn root_file(path: &Path, limit: u64) -> Result<HeldFile> {
    let file = HeldFile::open(&files::pin_file(path)?, limit)?;
    require(
        file.identity().uid == 0 && file.identity().gid == 0,
        "native package input is not owned by root",
    )?;
    files::no_privilege_xattrs(file.file())?;
    Ok(file)
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
                libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
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
            "native package directory has foreign ownership or unsafe mode",
        )?;
        Ok(Self {
            path: path.into(),
            identity: (m.dev(), m.ino(), m.mode(), m.uid(), m.gid()),
            file,
        })
    }
    fn revalidate(&self) -> Result<()> {
        let held = self.file.metadata()?;
        let named = Self::open(&self.path, false)?;
        require(
            (held.dev(), held.ino(), held.mode(), held.uid(), held.gid()) == self.identity
                && named.identity == self.identity,
            "original native package directory was replaced",
        )
    }
}

#[derive(Clone, Copy)]
enum Tool {
    Deb,
    Dpkg,
    Query,
}
impl Tool {
    fn path(self) -> &'static str {
        match self {
            Self::Deb => "/usr/bin/dpkg-deb",
            Self::Dpkg => "/usr/bin/dpkg",
            Self::Query => "/usr/bin/dpkg-query",
        }
    }
}
struct OwnedCommand {
    child: Child,
    pidfd: File,
    reaped: bool,
}
impl OwnedCommand {
    fn exited(&self) -> Result<Option<bool>> {
        let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
        if unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as u32,
                &mut info,
                libc::WEXITED | libc::WNOHANG | libc::WNOWAIT,
            )
        } != 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
        if unsafe { info.si_pid() } == 0 {
            return Ok(None);
        }
        Ok(Some(
            info.si_code == libc::CLD_EXITED && unsafe { info.si_status() } == 0,
        ))
    }
    fn retire(&mut self) -> Result<()> {
        if self.reaped {
            return Ok(());
        }
        let pid = i32::try_from(self.child.id())?;
        // The original leader remains unreaped until its original process
        // group has been retired. A recycled numeric process is never used.
        if unsafe { libc::kill(-pid, libc::SIGKILL) } != 0
            && std::io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
        {
            return Err(std::io::Error::last_os_error().into());
        }
        self.child.wait()?;
        self.reaped = true;
        Ok(())
    }
}
impl Drop for OwnedCommand {
    fn drop(&mut self) {
        if !self.reaped {
            let _ = unsafe {
                libc::syscall(
                    libc::SYS_pidfd_send_signal,
                    self.pidfd.as_raw_fd(),
                    libc::SIGKILL,
                    std::ptr::null::<libc::siginfo_t>(),
                    0,
                )
            };
            let _ = self.retire();
        }
    }
}
struct Output {
    bytes: Vec<u8>,
    receipt: Value,
}
fn command(
    area: &Path,
    name: &str,
    tool: Tool,
    args: &[String],
    permit: Option<&InstallationPermit>,
    limit: u64,
) -> Result<Output> {
    if let Some(owner) = permit {
        owner.revalidate()?;
    }
    let executable = root_file(Path::new(tool.path()), 32 * MIB)?;
    require(
        executable.identity().mode & 0o111 != 0,
        "normal Debian tool is not executable",
    )?;
    let mut elf = [0u8; 20];
    executable.file().read_exact_at(&mut elf, 0)?;
    require(
        &elf[..6] == b"\x7fELF\x02\x01" && elf[18..20] == [62, 0],
        "normal Debian tool is not its native amd64 ELF",
    )?;
    let out_path = area.join(format!("{name}.stdout"));
    let err_path = area.join(format!("{name}.stderr"));
    let out = files::new_file(&out_path, 0o600)?;
    let err = files::new_file(&err_path, 0o600)?;
    let mut process = Command::new(format!("/proc/self/fd/{}", executable.file().as_raw_fd()));
    process
        .args(args)
        .env_clear()
        .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
        .env("LANG", "C")
        .env("LC_ALL", "C")
        .env("DEBIAN_FRONTEND", "noninteractive")
        .current_dir("/")
        .stdin(Stdio::null())
        .stdout(out.try_clone()?)
        .stderr(err.try_clone()?);
    unsafe {
        process.pre_exec(|| {
            if libc::setsid() < 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
    executable.revalidate()?;
    let mut child = process.spawn()?;
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
    if raw < 0 {
        let error = std::io::Error::last_os_error();
        let _ = unsafe { libc::kill(-(child.id() as i32), libc::SIGKILL) };
        let _ = child.wait();
        return Err(error.into());
    }
    let mut owned = OwnedCommand {
        child,
        pidfd: unsafe { File::from_raw_fd(raw as i32) },
        reaped: false,
    };
    let started = Instant::now();
    let deadline = started + Duration::from_secs(180);
    let mut next_owner_check = started;
    loop {
        require(
            Instant::now() < deadline,
            "normal Debian operation exceeded its original deadline",
        )?;
        require(
            out.metadata()?.len() <= limit && err.metadata()?.len() <= MIB,
            "normal Debian operation exceeded its output bound",
        )?;
        if let Some(owner) = permit {
            if Instant::now() >= next_owner_check {
                owner.revalidate()?;
                next_owner_check = Instant::now() + Duration::from_millis(250);
            }
        }
        if let Some(success) = owned.exited()? {
            require(
                Instant::now() < deadline,
                "normal Debian operation completed after its deadline",
            )?;
            owned.retire()?;
            out.sync_all()?;
            err.sync_all()?;
            executable.revalidate()?;
            if let Some(owner) = permit {
                owner.revalidate()?;
            }
            let stdout = root_file(&out_path, limit)?;
            let stderr = root_file(&err_path, MIB)?;
            require(
                success,
                &format!(
                    "normal Debian operation {name} failed; inspect {}",
                    err_path.display()
                ),
            )?;
            let bytes = stdout.read_all(limit)?;
            return Ok(Output {
                bytes,
                receipt: json!({
                    "tool":executable.pin(),"arguments":args,"exit_code":0,
                    "stdout":stdout.pin(),"stderr":stderr.pin(),"elapsed_ms":started.elapsed().as_millis()
                }),
            });
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}

struct Alias {
    path: PathBuf,
    parent: File,
    leaf: CString,
    identity: (u64, u64, u32, u32, u32, u64, i64, i64, i64, i64),
}
impl Alias {
    fn facts(
        parent: &File,
        leaf: &CStr,
    ) -> Result<(u64, u64, u32, u32, u32, u64, i64, i64, i64, i64)> {
        let mut m: libc::stat = unsafe { std::mem::zeroed() };
        if unsafe {
            libc::fstatat(
                parent.as_raw_fd(),
                leaf.as_ptr(),
                &mut m,
                libc::AT_SYMLINK_NOFOLLOW,
            )
        } != 0
        {
            return Err(std::io::Error::last_os_error().into());
        }
        require(
            m.st_mode & libc::S_IFMT == libc::S_IFLNK
                && m.st_uid == 0
                && m.st_gid == 0
                && m.st_nlink == 1
                && m.st_mode & 0o7777 == 0o777,
            "native SONAME alias is not the original root-owned symbolic link",
        )?;
        Ok((
            m.st_dev,
            m.st_ino,
            m.st_mode,
            m.st_uid,
            m.st_gid,
            m.st_nlink,
            m.st_mtime,
            m.st_mtime_nsec,
            m.st_ctime,
            m.st_ctime_nsec,
        ))
    }
    fn target(parent: &File, leaf: &CStr) -> Result<()> {
        let mut bytes = [0u8; 256];
        let n = unsafe {
            libc::readlinkat(
                parent.as_raw_fd(),
                leaf.as_ptr(),
                bytes.as_mut_ptr().cast(),
                bytes.len(),
            )
        };
        if n < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        require(
            &bytes[..usize::try_from(n)?] == b"libapparmor.so.1.30.7",
            "native AppArmor SONAME alias has a foreign target",
        )
    }
    fn open(path: &Path) -> Result<Self> {
        let (parent, leaf) = files::parent(path)?;
        let identity = Self::facts(&parent, &leaf)?;
        Self::target(&parent, &leaf)?;
        require(
            Self::facts(&parent, &leaf)? == identity,
            "native SONAME alias changed while observed",
        )?;
        Ok(Self {
            path: path.into(),
            parent,
            leaf,
            identity,
        })
    }
    fn revalidate(&self) -> Result<()> {
        let fresh = Self::open(&self.path)?;
        require(
            fresh.identity == self.identity
                && Self::facts(&self.parent, &self.leaf)? == self.identity,
            "original native SONAME alias was replaced",
        )?;
        Self::target(&self.parent, &self.leaf)
    }
}

struct ExpectedFile {
    path: String,
    mode: u32,
    bytes: u64,
    sha256: String,
}
struct Package {
    definition: NativeDefinition,
    archive: HeldFile,
    staged: Vec<HeldFile>,
    staged_alias: Option<Alias>,
    files: Vec<ExpectedFile>,
    directories: BTreeSet<String>,
    control: BTreeMap<String, ExpectedFile>,
    control_receipt: Value,
}
fn control_fields(bytes: &[u8]) -> Result<BTreeMap<String, String>> {
    let text = std::str::from_utf8(bytes)?;
    require(
        !text.contains('\0') && text.ends_with('\n') && text.len() <= 65536,
        "native Debian control text is incomplete",
    )?;
    let mut result = BTreeMap::new();
    let mut previous = None::<String>;
    for line in text.lines() {
        if line.starts_with([' ', '\t']) {
            require(
                previous.as_deref().is_some_and(|name| {
                    ![
                        "Package",
                        "Version",
                        "Architecture",
                        "Multi-Arch",
                        "Maintainer",
                    ]
                    .contains(&name)
                }),
                "native identity metadata cannot use a continuation",
            )?;
            continue;
        }
        if line.is_empty() {
            continue;
        }
        let (name, value) = line
            .split_once(':')
            .ok_or("malformed native Debian control field")?;
        require(
            !name.is_empty()
                && name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-')
                && !result.contains_key(name),
            "duplicate or invalid native Debian control field",
        )?;
        result.insert(name.into(), value.trim_start().into());
        previous = Some(name.into());
    }
    Ok(result)
}
fn package(root: &Path, work: &Path, area: &Path, row: &Value, selinux: bool) -> Result<Package> {
    let definition = native_definition(selinux);
    let pin: FilePin = serde_json::from_value(row["normal_deb"].clone())?;
    let expected = work.join(definition.package).join(format!(
        "{}_{}_amd64.deb",
        definition.package, definition.version
    ));
    require(
        row["package"] == definition.package
            && row["version"] == definition.version
            && row["architecture"] == "amd64"
            && row["library_member"] == definition.member
            && pin.path == expected
            && pin.bytes == definition.deb.0
            && pin.sha256 == definition.deb.1,
        "native stage receipt differs from the fixed reviewed package",
    )?;
    let archive = root_file(&expected, MIB)?;
    require(
        archive.pin().bytes == definition.deb.0
            && archive.pin().sha256 == definition.deb.1
            && archive.identity().mode & 0o7777 == 0o400,
        "staged native Debian archive differs",
    )?;
    let archive_path = expected
        .to_str()
        .ok_or("non-UTF8 native archive")?
        .to_owned();
    let payload = command(
        area,
        &format!("{}-payload", definition.package),
        Tool::Deb,
        &["--fsys-tarfile".into(), archive_path.clone()],
        None,
        16 * MIB,
    )?;
    let mut files_out = Vec::new();
    let mut staged = Vec::new();
    let mut directories = BTreeSet::new();
    let mut staged_alias = None;
    let mut listed = BTreeMap::new();
    for value in row["payload"]
        .as_array()
        .ok_or("native payload receipt is not an array")?
    {
        let pin: FilePin = serde_json::from_value(value.clone())?;
        require(
            listed.insert(pin.path.clone(), pin).is_none(),
            "duplicate native payload receipt",
        )?;
    }
    for member in parse_native_tar(&payload.bytes)? {
        require(
            native_path_allowed(&member.name, definition.package, member.kind == b'5'),
            "native package member is outside its fixed namespace",
        )?;
        let path = root.join(&member.name);
        match member.kind {
            b'5' => {
                require(
                    member.mode == 0o755,
                    "native package directory mode differs",
                )?;
                if !member.name.is_empty() {
                    directories.insert(member.name);
                }
            }
            0 | b'0' => {
                require(
                    [0o644, 0o755].contains(&member.mode),
                    "native package file mode differs",
                )?;
                let bytes = member.bytes.len() as u64;
                let sha256 = files::digest(&member.bytes);
                let pin = listed
                    .remove(&path)
                    .ok_or("native payload receipt omitted an actual package file")?;
                require(
                    pin.bytes == bytes && pin.sha256 == sha256,
                    "native payload receipt differs from the actual archive",
                )?;
                let held = root_file(&path, 4 * MIB)?;
                require(
                    held.pin().bytes == bytes
                        && held.pin().sha256 == sha256
                        && held.identity().mode & 0o7777 == member.mode,
                    "staged native file differs from the actual archive",
                )?;
                if member.name == definition.member {
                    require(
                        (bytes, sha256.as_str()) == definition.library,
                        "native library differs from its compiled pin",
                    )?;
                }
                staged.push(held);
                files_out.push(ExpectedFile {
                    path: member.name,
                    mode: member.mode,
                    bytes,
                    sha256,
                });
            }
            b'2' => {
                require(
                    !selinux
                        && member.name == "usr/lib/x86_64-linux-gnu/libapparmor.so.1"
                        && member.target == "libapparmor.so.1.30.7"
                        && member.mode == 0o777
                        && staged_alias.is_none(),
                    "native package has an unreviewed alias",
                )?;
                staged_alias = Some(Alias::open(&path)?);
            }
            _ => return Err("native package contains a hardlink or special object".into()),
        }
    }
    require(
        listed.is_empty()
            && files_out.iter().any(|f| f.path == definition.member)
            && staged_alias.is_some() != selinux,
        "native package namespace is incomplete",
    )?;
    let controls = command(
        area,
        &format!("{}-control", definition.package),
        Tool::Deb,
        &["--ctrl-tarfile".into(), archive_path],
        None,
        MIB,
    )?;
    let mut control = BTreeMap::new();
    let mut fields = None;
    for member in parse_native_tar(&controls.bytes)? {
        if member.kind == b'5' {
            require(
                member.name.is_empty() && member.mode == 0o755,
                "foreign native control directory",
            )?;
            continue;
        }
        require(
            matches!(member.kind, 0 | b'0')
                && [
                    "control", "md5sums", "postinst", "shlibs", "symbols", "triggers",
                ]
                .contains(&member.name.as_str())
                && member.mode
                    == if member.name == "postinst" {
                        0o755
                    } else {
                        0o644
                    },
            "foreign native maintainer control object",
        )?;
        if member.name == "control" {
            fields = Some(control_fields(&member.bytes)?);
        }
        control.insert(
            member.name.clone(),
            ExpectedFile {
                path: member.name,
                mode: member.mode,
                bytes: member.bytes.len() as u64,
                sha256: files::digest(&member.bytes),
            },
        );
    }
    let fields = fields.ok_or("native Debian control stanza missing")?;
    let maintainer = if selinux {
        "Debian SELinux maintainers <selinux-devel@lists.alioth.debian.org>"
    } else {
        "Ubuntu Developers <ubuntu-devel-discuss@lists.ubuntu.com>"
    };
    for (name, value) in [
        ("Package", definition.package),
        ("Version", definition.version),
        ("Architecture", "amd64"),
        ("Multi-Arch", "same"),
        ("Maintainer", maintainer),
    ] {
        require(
            fields.get(name).map(String::as_str) == Some(value),
            "native Debian control metadata differs",
        )?;
    }
    let mut expected_control: BTreeSet<String> =
        ["control", "md5sums", "shlibs", "symbols", "triggers"]
            .into_iter()
            .map(str::to_owned)
            .collect();
    if selinux {
        expected_control.insert("postinst".into());
    }
    require(
        control.keys().cloned().collect::<BTreeSet<_>>() == expected_control,
        "native maintainer metadata set differs",
    )?;
    archive.revalidate()?;
    let control_receipt = json!({"fields":fields,"control":control.iter().map(|(name,f)|
        json!({"name":name,"mode":f.mode,"bytes":f.bytes,"sha256":f.sha256})).collect::<Vec<_>>(),
        "payload_reader":payload.receipt,"control_reader":controls.receipt});
    Ok(Package {
        definition,
        archive,
        staged,
        staged_alias,
        files: files_out,
        directories,
        control,
        control_receipt,
    })
}

pub(super) struct NativeInstaller {
    root: Directory,
    work: Directory,
    generation: Directory,
    operations: Directory,
    packages: Vec<Package>,
    attempted: Cell<bool>,
    completed: Cell<bool>,
}
impl NativeInstaller {
    pub(super) fn from_stage(root: &Path, work: &Path, platform: &Value) -> Result<Self> {
        require(
            unsafe { libc::geteuid() } == 0
                && root.file_name().is_some_and(|n| n == "root")
                && work.file_name().is_some_and(|n| n == "work")
                && root.parent() == work.parent(),
            "native installer requires the fixed private root/work stage",
        )?;
        let generation = root.parent().ok_or("native stage has no generation")?;
        require(
            generation.parent() == Some(Path::new(STAGING))
                && generation
                    .file_name()
                    .and_then(|s| s.to_str())
                    .is_some_and(files::valid_digest)
                && platform["schema"] == "droidloom.pocket4-platform-staged.v1",
            "native installer stage generation or material schema differs",
        )?;
        let generation = Directory::open(generation, true)?;
        let root = Directory::open(root, true)?;
        let work = Directory::open(work, true)?;
        let operations_path = work.path.join("native-install");
        match fs::symlink_metadata(&operations_path) {
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                files::private_dir(&operations_path)?
            }
            Err(e) => return Err(e.into()),
            Ok(_) => {}
        }
        let operations = Directory::open(&operations_path, true)?;
        let area = fresh_area(&operations)?;
        let rows = platform["native_packages"]
            .as_array()
            .ok_or("native package material list missing")?;
        require(
            rows.len() == 2,
            "exactly the two compiled native packages are required",
        )?;
        let mut packages = Vec::new();
        for selinux in [true, false] {
            let name = native_definition(selinux).package;
            let matched: Vec<_> = rows.iter().filter(|r| r["package"] == name).collect();
            require(
                matched.len() == 1,
                "native package material set has a duplicate or omission",
            )?;
            packages.push(package(&root.path, &work.path, &area, matched[0], selinux)?);
        }
        let value = Self {
            root,
            work,
            generation,
            operations,
            packages,
            attempted: Cell::new(false),
            completed: Cell::new(false),
        };
        value.revalidate_stage()?;
        Ok(value)
    }
    fn revalidate_stage(&self) -> Result<()> {
        self.root.revalidate()?;
        self.work.revalidate()?;
        self.generation.revalidate()?;
        self.operations.revalidate()?;
        for package in &self.packages {
            package.archive.revalidate()?;
            for file in &package.staged {
                file.revalidate()?;
            }
            if let Some(alias) = &package.staged_alias {
                alias.revalidate()?;
            }
        }
        Ok(())
    }
    fn install_arguments(&self, dry: bool) -> Result<Vec<String>> {
        let mut args = Vec::new();
        if dry {
            args.push("--no-act".into());
        }
        args.push("--install".into());
        for package in &self.packages {
            args.push(
                package
                    .archive
                    .pin()
                    .path
                    .to_str()
                    .ok_or("non-UTF8 native archive")?
                    .into(),
            );
        }
        Ok(args)
    }
    /// Performs normal dependency and architecture checks before a failure
    /// fence exists. This does not grant installation authority.
    pub(super) fn preflight(&self) -> Result<Value> {
        require(
            !self.attempted.get(),
            "native installation has already been attempted",
        )?;
        self.revalidate_stage()?;
        let area = fresh_area(&self.operations)?;
        let arch = command(
            &area,
            "architecture",
            Tool::Dpkg,
            &["--print-architecture".into()],
            None,
            65536,
        )?;
        require(
            arch.bytes == b"amd64\n",
            "live dpkg native architecture is not amd64",
        )?;
        let dry = command(
            &area,
            "no-act-install",
            Tool::Dpkg,
            &self.install_arguments(true)?,
            None,
            MIB,
        )?;
        self.revalidate_stage()?;
        Ok(
            json!({"schema":"droidloom.native-package-preflight.v1","architecture":arch.receipt,
            "normal_dpkg_no_act":dry.receipt,"packages":self.packages.iter().map(|p|
                json!({"package":p.definition.package,"version":p.definition.version,"archive":p.archive.pin(),
                    "normal_control":p.control_receipt})).collect::<Vec<_>>(),
            "live_system_modified":false,"installation_authority_issued":false}),
        )
    }
    /// The original permit stays held throughout the normal dpkg transaction.
    /// Any failure keeps the caller's original maintenance fence in place.
    pub(super) fn install(&self, permit: &InstallationPermit) -> Result<Value> {
        require(
            self.generation.path.file_name().and_then(|n| n.to_str()) == Some(permit.plan()),
            "installation permit belongs to another original stage generation",
        )?;
        require(
            !self.attempted.replace(true),
            "native installation cannot be replayed",
        )?;
        permit.revalidate()?;
        self.revalidate_stage()?;
        let area = fresh_area(&self.operations)?;
        let installed = command(
            &area,
            "install",
            Tool::Dpkg,
            &self.install_arguments(false)?,
            Some(permit),
            4 * MIB,
        )?;
        self.revalidate_stage()?;
        permit.revalidate()?;
        self.completed.set(true);
        Ok(
            json!({"schema":"droidloom.native-package-install.v1","normal_dpkg":installed.receipt,
            "normal_package_install_completed":true,"final_readback_required":true,"production_ready":false}),
        )
    }
    /// Called after all live file labels have been applied. Captures the final
    /// observed ctime and original inodes; no earlier snapshot is relaxed.
    pub(super) fn observe_installed(&self, permit: &InstallationPermit) -> Result<InstalledNative> {
        require(
            self.generation.path.file_name().and_then(|n| n.to_str()) == Some(permit.plan()),
            "installed observation crossed the original stage generation",
        )?;
        require(
            self.completed.get(),
            "normal native installation did not complete successfully",
        )?;
        permit.revalidate()?;
        self.revalidate_stage()?;
        let area = fresh_area(&self.operations)?;
        let status = root_file(Path::new(STATUS), 32 * MIB)?;
        let mut held = Vec::new();
        let mut directories = BTreeMap::new();
        let mut alias = None;
        let mut rows = Vec::new();
        let mut info_sets = BTreeMap::new();
        let info = Directory::open(Path::new(INFO), false)?;
        for package in &self.packages {
            let name = package.definition.package;
            let qualified = format!("{name}:amd64");
            let show = command(
                &area,
                &format!("{name}-status"),
                Tool::Query,
                &[
                    "--show".into(),
                    format!("--showformat={SHOW}"),
                    qualified.clone(),
                ],
                Some(permit),
                65536,
            )?;
            require(
                show.bytes
                    == format!(
                        "{name}\t{}\tamd64\tinstall ok installed\n",
                        package.definition.version
                    )
                    .as_bytes(),
                "live native package version or dpkg configuration status differs",
            )?;
            let listed = command(
                &area,
                &format!("{name}-files"),
                Tool::Query,
                &["--listfiles".into(), qualified.clone()],
                Some(permit),
                MIB,
            )?;
            let expected_list = package_list(package);
            require(
                parse_list(&listed.bytes)? == expected_list,
                "normal dpkg installed file namespace differs",
            )?;
            for expected in &package.files {
                let path = Path::new("/").join(&expected.path);
                let file = root_file(&path, 4 * MIB)?;
                require(
                    file.pin().bytes == expected.bytes
                        && file.pin().sha256 == expected.sha256
                        && file.identity().mode & 0o7777 == expected.mode,
                    "actual installed native payload differs",
                )?;
                held.push(file);
            }
            for name in &package.directories {
                let path = Path::new("/").join(name);
                if !directories.contains_key(&path) {
                    let directory = Directory::open(&path, false)?;
                    require(
                        directory.identity.2 & 0o7777 == 0o755,
                        "installed native directory mode differs",
                    )?;
                    directories.insert(path, directory);
                }
            }
            if package.staged_alias.is_some() {
                require(alias.is_none(), "duplicate native SONAME alias")?;
                alias = Some(Alias::open(Path::new(
                    "/usr/lib/x86_64-linux-gnu/libapparmor.so.1",
                ))?);
            }
            let mut expected_info = BTreeSet::from([format!("{qualified}.list")]);
            for (name, expected) in &package.control {
                if name == "control" {
                    continue;
                }
                let basename = format!("{qualified}.{name}");
                let file = root_file(&Path::new(INFO).join(&basename), MIB)?;
                require(
                    file.pin().bytes == expected.bytes
                        && file.pin().sha256 == expected.sha256
                        && file.identity().mode & 0o7777 == expected.mode,
                    "installed normal maintainer metadata differs",
                )?;
                held.push(file);
                expected_info.insert(basename);
            }
            require(
                info_names(&qualified)? == expected_info,
                "installed native maintainer namespace differs",
            )?;
            info_sets.insert(qualified.clone(), expected_info);
            let list = root_file(&Path::new(INFO).join(format!("{qualified}.list")), MIB)?;
            require(
                parse_list(&list.read_all(MIB)?)? == expected_list,
                "actual dpkg file list differs",
            )?;
            held.push(list);
            rows.push(json!({"package":package.definition.package,"version":package.definition.version,
                "status":show.receipt,"file_list":listed.receipt,"normal_control":package.control_receipt}));
        }
        require(alias.is_some(), "installed native SONAME alias is absent")?;
        status.revalidate()?;
        info.revalidate()?;
        self.revalidate_stage()?;
        permit.revalidate()?;
        let receipt = json!({"schema":"droidloom.native-package-installed.v1","packages":rows,
            "dpkg_status":status.pin(),"files":held.iter().map(|f|json!({"pin":f.pin(),"identity":f.identity()})).collect::<Vec<_>>(),
            "native_package_installed":true,"maintainer_metadata_verified":true,"all_payload_bytes_verified":true,
            "runtime_qualified":false,"production_ready":false});
        let result = InstalledNative {
            held,
            directories: directories.into_values().collect(),
            alias: alias.unwrap(),
            status,
            info,
            info_sets,
            receipt,
        };
        result.revalidate()?;
        Ok(result)
    }
}
fn fresh_area(directory: &Directory) -> Result<PathBuf> {
    directory.revalidate()?;
    for index in 0..4096 {
        let path = directory.path.join(format!("operation-{index:04}"));
        let (parent, name) = files::parent(&path)?;
        if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } == 0 {
            Directory::open(&path, true)?.revalidate()?;
            directory.revalidate()?;
            return Ok(path);
        }
        let error = std::io::Error::last_os_error();
        if error.raw_os_error() != Some(libc::EEXIST) {
            return Err(error.into());
        }
        Directory::open(&path, true)?.revalidate()?;
    }
    Err("native package operation directory bound exhausted".into())
}
fn package_list(package: &Package) -> BTreeSet<String> {
    let mut expected = BTreeSet::from(["/.".into()]);
    expected.extend(package.directories.iter().map(|name| format!("/{name}")));
    expected.extend(package.files.iter().map(|file| format!("/{}", file.path)));
    if package.staged_alias.is_some() {
        expected.insert("/usr/lib/x86_64-linux-gnu/libapparmor.so.1".into());
    }
    expected
}
fn parse_list(bytes: &[u8]) -> Result<BTreeSet<String>> {
    let text = std::str::from_utf8(bytes)?;
    require(
        text.ends_with('\n') && !text.contains('\0') && text.len() <= MIB as usize,
        "normal dpkg file list is incomplete",
    )?;
    let mut names = BTreeSet::new();
    for line in text.lines() {
        require(
            line == "/."
                || (line.starts_with('/')
                    && !line.ends_with('/')
                    && line[1..]
                        .split('/')
                        .all(|s| !s.is_empty() && s != "." && s != "..")),
            "normal dpkg file list has a foreign path",
        )?;
        require(
            names.insert(line.into()),
            "normal dpkg file list has duplicate paths",
        )?;
    }
    Ok(names)
}
fn info_names(qualified: &str) -> Result<BTreeSet<String>> {
    let prefix = format!("{qualified}.");
    let mut names = BTreeSet::new();
    for (index, entry) in fs::read_dir(INFO)?.enumerate() {
        require(
            index < 65536,
            "normal dpkg metadata directory exceeds its bound",
        )?;
        let entry = entry?;
        let name = entry.file_name();
        if let Some(name) = name.to_str().filter(|n| n.starts_with(&prefix)) {
            names.insert(name.into());
        }
    }
    Ok(names)
}
pub(super) struct InstalledNative {
    held: Vec<HeldFile>,
    directories: Vec<Directory>,
    alias: Alias,
    status: HeldFile,
    info: Directory,
    info_sets: BTreeMap<String, BTreeSet<String>>,
    receipt: Value,
}
impl InstalledNative {
    pub(super) fn revalidate(&self) -> Result<()> {
        self.status.revalidate()?;
        self.info.revalidate()?;
        self.alias.revalidate()?;
        for directory in &self.directories {
            directory.revalidate()?;
        }
        for file in &self.held {
            file.revalidate()?;
        }
        for (package, expected) in &self.info_sets {
            require(
                &info_names(package)? == expected,
                "installed native maintainer namespace changed",
            )?;
        }
        Ok(())
    }
    pub(super) fn receipt(&self) -> Value {
        self.receipt.clone()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_control_rejects_duplicate_identity_and_hidden_bytes() {
        let valid=b"Package: libselinux1\nVersion: 3.9-4build1+p4lsmexec3\nDescription: test\n continuation\n";
        assert_eq!(control_fields(valid).unwrap()["Package"], "libselinux1");
        assert!(control_fields(b"Package: first\nPackage: second\n").is_err());
        assert!(control_fields(b"Package: x\0y\n").is_err());
        assert!(control_fields(b" continuation\n").is_err());
        assert!(control_fields(b"Package: first\n second\n").is_err());
    }
    #[test]
    fn native_file_list_requires_exact_normal_unique_paths() {
        assert_eq!(
            parse_list(b"/.\n/usr\n/usr/lib/libx.so\n").unwrap().len(),
            3
        );
        for input in [
            b"/usr\n/usr\n".as_slice(),
            b"/usr/../etc\n",
            b"relative\n",
            b"/usr//lib\n",
            b"/usr/lib/\n",
            b"/usr",
        ] {
            assert!(parse_list(input).is_err());
        }
    }
}
