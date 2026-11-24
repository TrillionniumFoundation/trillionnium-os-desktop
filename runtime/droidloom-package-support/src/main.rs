//! Package setup and pacman lifecycle integration. No shell interpreter is used.
use clap::{Parser, Subcommand};
use droidloom_supervisor::{
    control::package::LivePackageRetirement, production_configuration::PackageConfigurationLock,
};

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    ffi::CStr,
    fs,
    io::{Read, Write},
    os::fd::{AsRawFd, FromRawFd},
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    path::{Component, Path, PathBuf},
    process::{Child, Command, ExitStatus, Stdio},
    time::{Duration, Instant},
};

mod production_retirement;

type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
const BASE: &str = "/etc/droidloom";
const SPEC: &str = "/etc/droidloom/cell.json";
const STATE: &str = "/etc/droidloom/package-state.json";
const ENVIRONMENT: &str = "/etc/droidloom/runtime.env";
const RULE: &str = "/etc/polkit-1/rules.d/49-droidloom.rules";
const HELPER: &str = "/usr/lib/droidloom/droidloom-package-helper";
const RECIPE: &str = "/usr/share/droidloom/cell-template.json";
const VERSION: &str = "/usr/share/droidloom/package.json";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Layout {
    Legacy,
    Production,
}

#[derive(Clone, Copy)]
struct Custody {
    uid: u32,
    gid: u32,
}
const ROOT_CUSTODY: Custody = Custody { uid: 0, gid: 0 };

fn safe_directory(file: &fs::File, custody: Custody) -> Result<()> {
    let m = file.metadata()?;
    if !m.is_dir() || m.uid() != custody.uid || m.gid() != custody.gid || m.mode() & 0o022 != 0 {
        return Err("unsafe package configuration directory".into());
    }
    Ok(())
}

fn directory_at(parent: &fs::File, name: &CStr, custody: Custody) -> Result<Option<fs::File>> {
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        let error = std::io::Error::last_os_error();
        if error.kind() == std::io::ErrorKind::NotFound {
            return Ok(None);
        }
        return Err(error.into());
    }
    let file = unsafe { fs::File::from_raw_fd(fd) };
    safe_directory(&file, custody)?;
    Ok(Some(file))
}

fn host_root() -> Result<fs::File> {
    let root = fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open("/")?;
    safe_directory(&root, ROOT_CUSTODY)?;
    Ok(root)
}

// The production call always starts at the held host / with root custody.
// The explicit custody parameter also lets ordinary tests use an isolated
// temporary filesystem without granting a production alternate-root option.
fn layout_at(root: &fs::File, custody: Custody) -> Result<Layout> {
    safe_directory(root, custody)?;
    let etc = directory_at(root, c"etc", custody)?.ok_or("package configuration /etc is absent")?;
    let Some(base) = directory_at(&etc, c"droidloom", custody)? else {
        return Ok(Layout::Legacy);
    };
    let Some(production) = directory_at(&base, c"production", custody)? else {
        return Ok(Layout::Legacy);
    };
    let fd = unsafe {
        libc::openat(
            production.as_raw_fd(),
            c"selected.json".as_ptr(),
            libc::O_PATH | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(format!(
            "production directory has no safely observable selection; legacy setup refused: {}",
            std::io::Error::last_os_error()
        )
        .into());
    }
    let selected = unsafe { fs::File::from_raw_fd(fd) };
    let m = selected.metadata()?;
    if !m.is_file()
        || m.uid() != custody.uid
        || m.gid() != custody.gid
        || m.nlink() != 1
        || m.mode() & 0o6022 != 0
    {
        return Err("unsafe production selection marker; legacy setup refused".into());
    }
    Ok(Layout::Production)
}

fn layout() -> Result<Layout> {
    layout_at(&host_root()?, ROOT_CUSTODY)
}

fn require_legacy() -> Result<()> {
    legacy_layout(layout()?)
}
fn legacy_layout(value: Layout) -> Result<()> {
    if value != Layout::Legacy {
        return Err("a production selection protects this installation; legacy setup and session startup are refused; selected.json, cell.json and Android data were preserved".into());
    }
    Ok(())
}

#[cfg(test)]
fn setup_lock_at(
    base: &fs::File,
    custody: Custody,
) -> Result<droidloom_supervisor::production_configuration::DirectorySetupLock> {
    Ok(
        droidloom_supervisor::production_configuration::DirectorySetupLock::exclusive_at(
            base,
            custody.uid,
            custody.gid,
        )?,
    )
}

fn setup_lock() -> Result<PackageConfigurationLock> {
    Ok(PackageConfigurationLock::acquire()?)
}

#[derive(Parser)]
#[command(
    version,
    about = "Configure and maintain a pacman-managed Droidloom installation"
)]
struct Cli {
    #[command(subcommand)]
    action: Action,
}
#[derive(Subcommand)]
enum Action {
    /// Perform missing setup as the calling desktop user, explaining authentication.
    Prepare,
    #[command(hide = true)]
    Setup {
        #[arg(long)]
        uid: u32,
        #[arg(long)]
        data_home: Option<PathBuf>,
        #[arg(long)]
        state_home: Option<PathBuf>,
    },
    #[command(hide = true)]
    BeforeUpgrade,
    #[command(hide = true)]
    BeforeRemove,
    #[command(hide = true)]
    AfterInstall,
}
#[derive(Clone, Deserialize, Serialize)]
struct SetupState {
    uid: u32,
    version: Value,
    data_home: PathBuf,
    state_home: PathBuf,
}
struct User {
    name: String,
    home: PathBuf,
}
fn read_json(path: &Path) -> Result<Value> {
    Ok(serde_json::from_slice(&fs::read(path)?)?)
}
fn optional_json(path: &Path) -> Result<Option<Value>> {
    match fs::read(path) {
        Ok(data) => Ok(Some(serde_json::from_slice(&data)?)),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(error) => Err(error.into()),
    }
}
fn run(command: &mut Command) -> Result<()> {
    let status = command.status()?;
    if !status.success() {
        return Err(format!("{command:?} failed: {status}").into());
    }
    Ok(())
}
fn user(uid: u32) -> Result<User> {
    if uid == 0 {
        return Err("Droidloom's desktop owner must be an ordinary user".into());
    }
    let record = Command::new("/usr/bin/getent")
        .args(["passwd", &uid.to_string()])
        .output()?;
    if !record.status.success() {
        return Err(format!("no desktop user exists for UID {uid}").into());
    }
    let record = String::from_utf8(record.stdout)?;
    let fields: Vec<_> = record.trim_end().split(':').collect();
    if fields.len() != 7 || fields[2].parse::<u32>()? != uid || !Path::new(fields[5]).is_absolute()
    {
        return Err("invalid desktop user record".into());
    }
    Ok(User {
        name: fields[0].into(),
        home: fields[5].into(),
    })
}
fn require_root() -> Result<()> {
    if unsafe { libc::geteuid() } != 0 {
        return Err("this operation writes root-owned Droidloom configuration or controls its system service; run through pacman or the authenticated setup operation".into());
    }
    Ok(())
}
fn root_directory(path: &Path, mode: u32) -> Result<()> {
    if path == Path::new("/") {
        return Ok(());
    }
    if !path.is_absolute() || path.components().any(|c| matches!(c, Component::ParentDir)) {
        return Err(
            "administrator-owned directory must be an absolute path without parent traversal"
                .into(),
        );
    }
    if let Some(parent) = path.parent() {
        root_directory(parent, 0o755)?;
    }
    match fs::symlink_metadata(path) {
        Ok(m) if m.is_dir() && m.uid() == 0 && m.mode() & 0o022 == 0 => Ok(()),
        Ok(_) => Err(format!(
            "refusing non-directory, symlink, or writable/non-root-owned setup path {}",
            path.display()
        )
        .into()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            fs::create_dir(path)?;
            fs::set_permissions(path, fs::Permissions::from_mode(mode))?;
            Ok(())
        }
        Err(error) => Err(error.into()),
    }
}
fn atomic_write(path: &Path, value: &[u8], mode: u32) -> Result<()> {
    let parent = path.parent().ok_or("configuration path has no parent")?;
    root_directory(parent, 0o755)?;
    if let Ok(metadata) = fs::symlink_metadata(path) {
        if !metadata.is_file() || metadata.uid() != 0 || metadata.mode() & 0o022 != 0 {
            return Err(format!(
                "refusing to replace unsafe configuration {}",
                path.display()
            )
            .into());
        }
    }
    let mut temporary = tempfile::NamedTempFile::new_in(parent)?;
    temporary.write_all(value)?;
    temporary
        .as_file()
        .set_permissions(fs::Permissions::from_mode(mode))?;
    temporary.as_file().sync_all()?;
    temporary.persist(path)?;
    fs::File::open(parent)?.sync_all()?;
    Ok(())
}
fn render_node(sys: &Path) -> Result<String> {
    let mut nodes = fs::read_dir(sys)?.collect::<std::io::Result<Vec<_>>>()?;
    nodes.sort_by_key(|n| n.file_name());
    for node in nodes {
        let name = node.file_name().to_string_lossy().into_owned();
        if !name
            .strip_prefix("renderD")
            .is_some_and(|tail| !tail.is_empty() && tail.bytes().all(|b| b.is_ascii_digit()))
        {
            continue;
        }
        if let Ok(driver) = fs::canonicalize(node.path().join("device/driver")) {
            if driver
                .file_name()
                .is_some_and(|d| d == "amdgpu" || d == "i915" || d == "xe")
            {
                return Ok(format!("/dev/dri/{name}"));
            }
        }
    }
    Err("This Droidloom package needs an AMD or Intel render node. No matching driver was found; configuration was not changed.".into())
}
fn configuration(
    mut recipe: Value,
    previous: Option<&Value>,
    uid: u32,
    render: &str,
) -> Result<Value> {
    if uid == 0 {
        return Err("desktop UID must be nonzero".into());
    }
    recipe["host_uid"] = json!(uid);
    recipe["render_node"] = json!(render);
    recipe["data_dir"] = json!(format!("/var/lib/droidloom/users/{uid}/data"));
    recipe["runtime_dir"] = json!(format!("/run/droidloom/cells/u{uid}"));
    recipe["denial_socket"] = json!(format!("/run/user/{uid}/droidloom/native-bridge.sock"));
    if let Some(previous) = previous {
        if previous["host_uid"].as_u64() != Some(u64::from(uid)) {
            return Err("this Droidloom installation belongs to another desktop user; existing data and configuration were preserved".into());
        }
        for key in [
            "data_dir",
            "gapps_dir",
            "shared_storage_directories",
            "subordinate_uids",
            "subordinate_gids",
        ] {
            if let Some(value) = previous.get(key) {
                recipe[key] = value.clone();
            }
        }
    }
    let data = Path::new(
        recipe["data_dir"]
            .as_str()
            .ok_or("missing Android data path")?,
    );
    if !data.starts_with("/var/lib/droidloom")
        || data.components().any(|c| matches!(c, Component::ParentDir))
    {
        return Err("Android data must remain below /var/lib/droidloom".into());
    }
    let spec: droidloom_supervisor::CellSpec = serde_json::from_value(recipe.clone())?;
    spec.validate()?;
    Ok(recipe)
}
fn prepare() -> Result<()> {
    require_legacy()?;
    let uid = unsafe { libc::getuid() };
    let account = user(uid)?;
    if unsafe { libc::geteuid() } == 0 {
        return Err("run droidloomctl start as your desktop user, without sudo".into());
    }
    let previous = optional_json(Path::new(SPEC))?;
    if previous
        .as_ref()
        .is_some_and(|s| s["host_uid"].as_u64() != Some(u64::from(uid)))
    {
        return Err("Droidloom is configured for a different desktop user".into());
    }
    let version = read_json(Path::new(VERSION))?;
    let state: Option<SetupState> = optional_json(Path::new(STATE))?
        .map(serde_json::from_value)
        .transpose()?;
    if state
        .as_ref()
        .is_some_and(|s| s.uid == uid && s.version == version)
        && previous.is_some()
        && Path::new(ENVIRONMENT).is_file()
    {
        // Polkit's rules directory is intentionally not traversable by an
        // ordinary user. The root-owned state is published after the rule.
        require_legacy()?;
        return Ok(());
    }
    let data_home = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
        .unwrap_or_else(|| account.home.join(".local/share"));
    let state_home = std::env::var_os("XDG_STATE_HOME")
        .map(PathBuf::from)
        .filter(|p| p.is_absolute())
        .unwrap_or_else(|| account.home.join(".local/state"));
    let data = previous
        .as_ref()
        .and_then(|s| s["data_dir"].as_str())
        .map(str::to_owned)
        .unwrap_or_else(|| format!("/var/lib/droidloom/users/{uid}/data"));
    eprintln!(
        "Administrator authentication is needed to configure Droidloom for {} (UID {uid}).",
        account.name
    );
    eprintln!(
        "The installed helper will write {SPEC}, {ENVIRONMENT}, {STATE}, and {RULE}. These files are administrator-owned."
    );
    eprintln!(
        "It will create missing Android data.img and metadata.img regular files in {data}, initialize only new files as ext4, and preserve existing Android data. It authorizes only start/stop of droidloomd.service for this user."
    );
    eprintln!(
        "That system service needs root to create Android namespaces, mount the image files, and configure Droidloom's network connection."
    );
    require_legacy()?;
    run(Command::new("/usr/bin/pkexec")
        .arg(HELPER)
        .args(["setup", "--uid"])
        .arg(uid.to_string())
        .arg("--data-home")
        .arg(data_home)
        .arg("--state-home")
        .arg(state_home))
}
fn setup(
    uid: u32,
    data_home: Option<PathBuf>,
    state_home: Option<PathBuf>,
    hook: bool,
) -> Result<()> {
    require_root()?;
    require_legacy()?;
    if !hook {
        if let Ok(invoker) = std::env::var("PKEXEC_UID").or_else(|_| std::env::var("SUDO_UID")) {
            if invoker.parse::<u32>()? != uid {
                return Err("setup owner differs from the authenticated caller".into());
            }
        }
    }
    let account = user(uid)?;
    root_directory(Path::new(BASE), 0o755)?;
    let lock = setup_lock()?;
    lock.revalidate()?;
    require_legacy()?;
    let previous = optional_json(Path::new(SPEC))?;
    let renderer = if hook {
        previous
            .as_ref()
            .and_then(|p| p["render_node"].as_str())
            .ok_or("existing setup has no render node")?
            .to_owned()
    } else {
        render_node(Path::new("/sys/class/drm"))?
    };
    let spec = configuration(
        read_json(Path::new(RECIPE))?,
        previous.as_ref(),
        uid,
        &renderer,
    )?;
    let data = Path::new(spec["data_dir"].as_str().unwrap());
    lock.revalidate()?;
    require_legacy()?;
    root_directory(data, 0o700)?;
    for (name, bytes) in [
        ("data.img", 12_u64 * 1024 * 1024 * 1024),
        ("metadata.img", 128_u64 * 1024 * 1024),
    ] {
        let path = data.join(name);
        match fs::symlink_metadata(&path) {
            Ok(m) if m.is_file() && m.uid() == 0 && m.mode() & 0o022 == 0 => continue,
            Ok(_) => {
                return Err(format!("refusing unsafe Android data file {}", path.display()).into());
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
        lock.revalidate()?;
        require_legacy()?;
        let file = tempfile::NamedTempFile::new_in(data)?;
        file.as_file().set_len(bytes)?;
        run(Command::new("/usr/bin/mkfs.ext4")
            .args(["-F", "-q"])
            .arg(file.path()))?;
        file.as_file().sync_all()?;
        lock.revalidate()?;
        require_legacy()?;
        file.persist_noclobber(&path)?;
    }
    let old_state: Option<SetupState> = optional_json(Path::new(STATE))?
        .map(serde_json::from_value)
        .transpose()?;
    let state = SetupState {
        uid,
        version: read_json(Path::new(VERSION))?,
        data_home: data_home
            .or_else(|| old_state.as_ref().map(|s| s.data_home.clone()))
            .unwrap_or_else(|| account.home.join(".local/share")),
        state_home: state_home
            .or_else(|| old_state.as_ref().map(|s| s.state_home.clone()))
            .unwrap_or_else(|| account.home.join(".local/state")),
    };
    if !state.data_home.is_absolute() || !state.state_home.is_absolute() {
        return Err("XDG paths must be absolute".into());
    }
    let username = serde_json::to_string(&account.name)?;
    let rule = format!(
        "// Generated for Droidloom's configured desktop user.\npolkit.addRule(function(action, subject) {{\n  if (action.id === \"org.freedesktop.systemd1.manage-units\" && subject.user === {username} && action.lookup(\"unit\") === \"droidloomd.service\" && (action.lookup(\"verb\") === \"start\" || action.lookup(\"verb\") === \"stop\")) return polkit.Result.YES;\n}});\n"
    );
    lock.revalidate()?;
    require_legacy()?;
    atomic_write(Path::new(SPEC), &serde_json::to_vec_pretty(&spec)?, 0o644)?;
    lock.revalidate()?;
    atomic_write(Path::new(ENVIRONMENT), format!("DROIDLOOM_HOST_PEER_PID=0\nDROIDLOOM_HOST_PEER_UID=1000\nDROIDLOOM_HOST_PEER_GID=1000\nDROIDLOOM_RENDER_NODE={renderer}\n").as_bytes(), 0o644)?;
    lock.revalidate()?;
    atomic_write(Path::new(RULE), rule.as_bytes(), 0o644)?;
    lock.revalidate()?;
    atomic_write(Path::new(STATE), &serde_json::to_vec_pretty(&state)?, 0o644)?;
    lock.revalidate()?;
    println!(
        "Droidloom is configured for {}. Automatic startup remains disabled.",
        account.name
    );
    Ok(())
}
fn user_command(uid: u32, executable: &str) -> Result<Command> {
    let account = user(uid)?;
    let mut command = Command::new("/usr/bin/runuser");
    command
        .args(["-u", &account.name, "--", "/usr/bin/env"])
        .arg(format!("XDG_RUNTIME_DIR=/run/user/{uid}"))
        .arg(format!(
            "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus"
        ))
        .arg(executable);
    Ok(command)
}

#[derive(Clone, Copy, Debug)]
enum NativeUnit {
    Production,
    ManagerLabel,
    Legacy,
}
const NATIVE_UNITS: [NativeUnit; 3] = [
    NativeUnit::Production,
    NativeUnit::ManagerLabel,
    NativeUnit::Legacy,
];
impl NativeUnit {
    fn name(self) -> &'static str {
        match self {
            Self::Production => "droidloom-production.service",
            Self::ManagerLabel => "droidloom-manager-label.service",
            Self::Legacy => "droidloomd.service",
        }
    }
    fn c_name(self) -> &'static CStr {
        match self {
            Self::Production => c"droidloom-production.service",
            Self::ManagerLabel => c"droidloom-manager-label.service",
            Self::Legacy => c"droidloomd.service",
        }
    }
    fn group(self) -> String {
        format!("/system.slice/{}", self.name())
    }
}
enum NativeAction {
    Inspect(NativeUnit),
    Stop(NativeUnit),
}
struct NativeOutput {
    status: ExitStatus,
    stdout: Vec<u8>,
    stderr: Vec<u8>,
}

fn nonblocking(fd: i32) -> Result<()> {
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    Ok(())
}
fn drain<R: Read>(input: &mut R, bytes: &mut Vec<u8>) -> Result<bool> {
    let mut block = [0u8; 4096];
    loop {
        match input.read(&mut block) {
            Ok(0) => return Ok(true),
            Ok(n) => {
                if bytes.len() + n > 64 * 1024 {
                    return Err("native systemctl output exceeded its limit".into());
                }
                bytes.extend_from_slice(&block[..n]);
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => return Ok(false),
            Err(error) if error.kind() == std::io::ErrorKind::Interrupted => continue,
            Err(error) => return Err(error.into()),
        }
    }
}
fn retire_command(child: &mut Child, pidfd: Option<&fs::File>) -> Result<()> {
    if child.try_wait()?.is_some() {
        return Ok(());
    }
    if let Some(pidfd) = pidfd {
        if unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                pidfd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0,
            )
        } != 0
        {
            let error = std::io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::ESRCH) {
                return Err(error.into());
            }
        }
    } else {
        // Only this direct, still unreaped Popen-equivalent child. No PID
        // received from systemctl, JSON or the caller is signalled here.
        child.kill()?;
    }
    let end = Instant::now() + Duration::from_secs(5);
    loop {
        if child.try_wait()?.is_some() {
            return Ok(());
        }
        if Instant::now() >= end {
            return Err("native command retirement was not observed".into());
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}
fn native_command(action: NativeAction, deadline: Instant) -> Result<NativeOutput> {
    if Instant::now() >= deadline {
        return Err("native stop deadline expired".into());
    }
    let mut command = Command::new("/usr/bin/systemctl");
    command
        .env_clear()
        .env("PATH", "/usr/bin:/bin")
        .env("LC_ALL", "C")
        .env("SYSTEMD_PAGER", "cat")
        .env("SYSTEMD_COLORS", "0")
        .args(["--system", "--no-pager", "--no-ask-password"])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    match action {
        NativeAction::Inspect(unit) => {
            command.args(["show", "--all", unit.name(),
            "--property=Id,LoadState,ActiveState,SubState,MainPID,ControlPID,InvocationID,ControlGroup,Job"]);
        }
        NativeAction::Stop(unit) => {
            command.args(["stop", unit.name()]);
        }
    }
    let mut child = command.spawn()?;
    let mut pidfd = None;
    let result = (|| -> Result<NativeOutput> {
        let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, child.id(), 0) };
        if raw < 0 {
            return Err(std::io::Error::last_os_error().into());
        }
        pidfd = Some(unsafe { fs::File::from_raw_fd(raw as i32) });
        let mut out = child.stdout.take().ok_or("native stdout absent")?;
        let mut err = child.stderr.take().ok_or("native stderr absent")?;
        nonblocking(out.as_raw_fd())?;
        nonblocking(err.as_raw_fd())?;
        let mut stdout = Vec::new();
        let mut stderr = Vec::new();
        let mut status = None;
        loop {
            if Instant::now() >= deadline {
                return Err("native command exceeded stop deadline".into());
            }
            let out_eof = drain(&mut out, &mut stdout)?;
            let err_eof = drain(&mut err, &mut stderr)?;
            if status.is_none() {
                status = child.try_wait()?;
            }
            if let Some(status) = status {
                if out_eof && err_eof {
                    return Ok(NativeOutput {
                        status,
                        stdout,
                        stderr,
                    });
                }
            }
            let mut fds = [
                libc::pollfd {
                    fd: if out_eof { -1 } else { out.as_raw_fd() },
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: if err_eof { -1 } else { err.as_raw_fd() },
                    events: libc::POLLIN,
                    revents: 0,
                },
                libc::pollfd {
                    fd: if status.is_some() {
                        -1
                    } else {
                        pidfd.as_ref().unwrap().as_raw_fd()
                    },
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let ms = deadline
                .saturating_duration_since(Instant::now())
                .as_millis()
                .clamp(1, 100) as i32;
            let rc = unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, ms) };
            if rc < 0 && std::io::Error::last_os_error().kind() != std::io::ErrorKind::Interrupted {
                return Err(std::io::Error::last_os_error().into());
            }
            if fds.iter().any(|fd| fd.revents & libc::POLLNVAL != 0) {
                return Err("native command descriptor became invalid".into());
            }
        }
    })();
    if result.is_err() {
        if let Err(cleanup) = retire_command(&mut child, pidfd.as_ref()) {
            return Err(format!(
                "native command failed: {}; original child cleanup failed: {cleanup}",
                result.err().unwrap()
            )
            .into());
        }
    }
    result
}

#[derive(Debug)]
struct UnitState {
    load: String,
    active: String,
    sub: String,
    main: u32,
    control: u32,
    invocation: String,
    group: String,
    job_empty: bool,
}
fn parse_unit(unit: NativeUnit, bytes: &[u8]) -> Result<UnitState> {
    let text = std::str::from_utf8(bytes)?;
    let mut values = BTreeMap::new();
    for line in text.lines() {
        let (key, value) = line
            .split_once('=')
            .ok_or("invalid native unit property row")?;
        if values.insert(key, value).is_some() {
            return Err("duplicate native unit property".into());
        }
    }
    let expected = [
        "ActiveState",
        "ControlGroup",
        "ControlPID",
        "Id",
        "InvocationID",
        "Job",
        "LoadState",
        "MainPID",
        "SubState",
    ];
    if values.keys().copied().collect::<Vec<_>>() != expected || values["Id"] != unit.name() {
        return Err("native unit identity or property membership differs".into());
    }
    let invocation = values["InvocationID"];
    if !invocation.is_empty()
        && (invocation.len() != 32
            || !invocation.bytes().all(|b| b.is_ascii_hexdigit())
            || invocation.bytes().all(|b| b == b'0'))
    {
        return Err("invalid native unit invocation identity".into());
    }
    let group = values["ControlGroup"];
    if !group.is_empty() && group != unit.group() {
        return Err("native unit cgroup is outside its fixed system.slice role".into());
    }
    let load = values["LoadState"];
    if !matches!(load, "loaded" | "masked" | "not-found") {
        return Err("native unit could not be loaded or observed".into());
    }
    Ok(UnitState {
        load: load.into(),
        active: values["ActiveState"].into(),
        sub: values["SubState"].into(),
        main: values["MainPID"].parse()?,
        control: values["ControlPID"].parse()?,
        invocation: invocation.into(),
        group: group.into(),
        job_empty: matches!(values["Job"], "" | "0"),
    })
}
fn inspect_unit(unit: NativeUnit, deadline: Instant) -> Result<UnitState> {
    let result = native_command(NativeAction::Inspect(unit), deadline)?;
    if !result.status.success() {
        return Err(format!(
            "cannot observe {}: {}",
            unit.name(),
            String::from_utf8_lossy(&result.stderr)
        )
        .into());
    }
    parse_unit(unit, &result.stdout)
}
fn terminal_unit(before: &UnitState, after: &UnitState) -> Result<()> {
    if !matches!(
        (after.active.as_str(), after.sub.as_str()),
        ("inactive", "dead") | ("failed", "failed")
    ) || after.main != 0
        || after.control != 0
        || !after.job_empty
    {
        return Err("native unit still has an actor, pending job or nonterminal state".into());
    }
    if !after.invocation.is_empty() && after.invocation != before.invocation {
        return Err("native unit changed invocation during package stop".into());
    }
    if after.load == "not-found"
        && (!after.group.is_empty()
            || !after.invocation.is_empty()
            || after.active != "inactive"
            || after.sub != "dead")
    {
        return Err("not-found native unit has inconsistent residual identity".into());
    }
    Ok(())
}

fn stable_stop_state(state: &UnitState) -> Result<()> {
    if !state.job_empty {
        return Err("native unit has a pending job; fixed-name stop refused".into());
    }
    match (state.active.as_str(), state.sub.as_str()) {
        ("active", "running") => {
            if state.load == "not-found"
                || state.invocation.is_empty()
                || state.group.is_empty()
                || state.control != 0
            {
                return Err("active native unit has no stable complete original identity".into());
            }
        }
        ("active", "exited") => {
            if state.load == "not-found"
                || state.invocation.is_empty()
                || state.main != 0
                || state.control != 0
            {
                return Err(
                    "exited native unit has a live actor or missing original identity".into(),
                );
            }
            // A completed RemainAfterExit service may have no cgroup. The
            // original held-group and fresh-path checks still run before Stop;
            // an empty group is accepted there only when both remain absent.
        }
        ("inactive", "dead") | ("failed", "failed") => {
            terminal_unit(state, state)?;
        }
        _ => {
            return Err(
                "native unit is changing state or its state is unknown; stop refused".into(),
            );
        }
    }
    Ok(())
}

fn same_stop_generation(before: &UnitState, current: &UnitState) -> Result<()> {
    stable_stop_state(before)?;
    stable_stop_state(current)?;
    if current.invocation != before.invocation
        || current.group != before.group
        || current.load != before.load
        || current.main != before.main
        || current.control != before.control
        || current.active != before.active
        || current.sub != before.sub
    {
        return Err("native unit changed since original capture; fixed-name stop refused".into());
    }
    Ok(())
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct CgroupNode {
    dev: u64,
    ino: u64,
}
fn node(file: &fs::File) -> Result<CgroupNode> {
    let m = file.metadata()?;
    Ok(CgroupNode {
        dev: m.dev(),
        ino: m.ino(),
    })
}
fn cgroup_filesystem(file: &fs::File) -> Result<()> {
    let mut value: libc::statfs = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut value) } != 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    if value.f_type as u64 != 0x6367_7270 {
        return Err("native unit observation requires the actual cgroup2 filesystem".into());
    }
    Ok(())
}
fn cgroup_root() -> Result<fs::File> {
    let mut directory = host_root()?;
    for part in [c"sys", c"fs", c"cgroup"] {
        directory =
            directory_at(&directory, part, ROOT_CUSTODY)?.ok_or("native cgroup2 root is absent")?;
    }
    cgroup_filesystem(&directory)?;
    Ok(directory)
}
fn fixed_group(root: &fs::File, unit: NativeUnit) -> Result<Option<fs::File>> {
    cgroup_filesystem(root)?;
    let Some(slice) = directory_at(root, c"system.slice", ROOT_CUSTODY)? else {
        return Ok(None);
    };
    cgroup_filesystem(&slice)?;
    let value = directory_at(&slice, unit.c_name(), ROOT_CUSTODY)?;
    if let Some(file) = value.as_ref() {
        cgroup_filesystem(file)?;
    }
    Ok(value)
}
fn population(bytes: &[u8]) -> Result<bool> {
    let text = std::str::from_utf8(bytes)?;
    let mut values = BTreeMap::new();
    for line in text.lines() {
        let words = line.split_ascii_whitespace().collect::<Vec<_>>();
        if words.len() != 2
            || !matches!(words[1], "0" | "1")
            || !matches!(words[0], "populated" | "frozen")
            || values.insert(words[0], words[1]).is_some()
        {
            return Err("invalid complete cgroup.events observation".into());
        }
    }
    if values.len() != 2 {
        return Err("native unit descendants are unobserved".into());
    }
    Ok(values["populated"] == "1")
}
fn unpopulated(bytes: &[u8]) -> Result<()> {
    if population(bytes)? {
        return Err("native unit descendants are still populated".into());
    }
    Ok(())
}
fn open_events(file: &fs::File) -> Result<fs::File> {
    cgroup_filesystem(file)?;
    let fd = unsafe {
        libc::openat(
            file.as_raw_fd(),
            c"cgroup.events".as_ptr(),
            libc::O_RDONLY | libc::O_NONBLOCK | libc::O_NOFOLLOW | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let input = unsafe { fs::File::from_raw_fd(fd) };
    cgroup_filesystem(&input)?;
    if !input.metadata()?.is_file() {
        return Err("cgroup.events is not a regular kernel file".into());
    }
    Ok(input)
}
fn events_bytes(input: &fs::File) -> std::io::Result<Vec<u8>> {
    if unsafe { libc::lseek(input.as_raw_fd(), 0, libc::SEEK_SET) } < 0 {
        return Err(std::io::Error::last_os_error());
    }
    let mut bytes = Vec::new();
    input.take(4097).read_to_end(&mut bytes)?;
    if bytes.len() > 4096 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "cgroup.events exceeded its bound",
        ));
    }
    Ok(bytes)
}
struct OriginalCgroup {
    directory: fs::File,
    node: CgroupNode,
    events: fs::File,
    events_node: CgroupNode,
}
struct HeldCgroup {
    root: fs::File,
    unit: NativeUnit,
    original: Option<OriginalCgroup>,
}
impl HeldCgroup {
    fn capture(root: &fs::File, unit: NativeUnit, before: &UnitState) -> Result<Self> {
        let original = if let Some(directory) = fixed_group(root, unit)? {
            let events = open_events(&directory)?;
            Some(OriginalCgroup {
                node: node(&directory)?,
                events_node: node(&events)?,
                directory,
                events,
            })
        } else {
            None
        };
        if (!before.group.is_empty() || before.main != 0 || before.control != 0)
            && original.is_none()
        {
            return Err("reported native unit has no observable original cgroup".into());
        }
        if before.load == "not-found" && original.is_some() {
            return Err("unloaded native unit has an ambiguous cgroup at its fixed path".into());
        }
        Ok(Self {
            root: root.try_clone()?,
            unit,
            original,
        })
    }
    fn revalidate_stop_target(&self, state: &UnitState) -> Result<()> {
        let current = fixed_group(&self.root, self.unit)?;
        match (&self.original, current) {
            (None, None) if state.group.is_empty() && state.main == 0 && state.control == 0 => {
                Ok(())
            }
            (Some(held), Some(now)) => {
                if node(&held.directory)? != held.node
                    || node(&now)? != held.node
                    || node(&held.events)? != held.events_node
                    || state.group != self.unit.group()
                {
                    return Err("original native cgroup identity changed before stop".into());
                }
                // Missing, removed or malformed observations through the
                // original held file cannot authorize a later generation.
                population(&events_bytes(&held.events)?)?;
                Ok(())
            }
            _ => Err("native cgroup appeared or disappeared before stop".into()),
        }
    }
    fn verify_retired(&self, after: &UnitState) -> Result<()> {
        let current = fixed_group(&self.root, self.unit)?;
        match (&self.original, current) {
            (None, None) if after.group.is_empty() => Ok(()),
            (Some(held), Some(now)) => {
                if node(&held.directory)? != held.node
                    || node(&now)? != held.node
                    || node(&held.events)? != held.events_node
                {
                    return Err("native cgroup path was replaced during stop".into());
                }
                unpopulated(&events_bytes(&held.events)?)
            }
            (Some(held), None) => {
                if node(&held.directory)? != held.node
                    || node(&held.events)? != held.events_node
                    || !after.group.is_empty()
                {
                    return Err("original cgroup removal is not proven".into());
                }
                // Target kernfs refreshes a directory's link count from its
                // child count even after removal; st_nlink==0 is not a valid
                // retirement requirement. Its held seq_file instead returns
                // ENODEV once kernfs_get_active_of can no longer acquire it.
                match events_bytes(&held.events) {
                    Err(error) if error.raw_os_error() == Some(libc::ENODEV) => Ok(()),
                    _ => Err(
                        "original cgroup has not proved inactive through its held events file"
                            .into(),
                    ),
                }
            }
            _ => Err("native cgroup appeared or changed during stop".into()),
        }
    }
}

fn stop_native_units(
    deadline: Instant,
    original_production: Option<&LivePackageRetirement<'_>>,
) -> Result<()> {
    if let Some(original) = original_production {
        original.revalidate()?;
    }
    let root = cgroup_root()?;
    let mut original = Vec::new();
    for unit in NATIVE_UNITS {
        let state = inspect_unit(unit, deadline)?;
        stable_stop_state(&state)?;
        let group = HeldCgroup::capture(&root, unit, &state)?;
        original.push((unit, state, group));
    }
    for (unit, before, group) in &original {
        // Stopping another unit may let this original retire or acquire a
        // new InvocationID. Re-observe before each mutating native call.
        let current = inspect_unit(*unit, deadline)?;
        stable_stop_state(&current)?;
        if matches!(unit, NativeUnit::Production)
            && let Some(original) = original_production
        {
            // Bind this Stop to the RPC's original broker, in addition to
            // the native snapshot. An unexpected exit also refuses before
            // attempting to stop either of the remaining native actors.
            original.revalidate()?;
        }
        if matches!(current.active.as_str(), "inactive" | "failed") {
            terminal_unit(before, &current)?;
            group.verify_retired(&current)?;
            continue;
        }
        same_stop_generation(before, &current)?;
        group.revalidate_stop_target(&current)?;
        let output = native_command(NativeAction::Stop(*unit), deadline)?;
        if !output.status.success() {
            return Err(format!(
                "native stop of {} failed; package replacement refused: {}",
                unit.name(),
                String::from_utf8_lossy(&output.stderr)
            )
            .into());
        }
        if matches!(unit, NativeUnit::Production)
            && let Some(original) = original_production
        {
            // The original broker's PIDFD/normal exit is checked again inside
            // this opaque phase. Finish its retained observer, launcher and
            // persistent factory before stopping manager-label or legacy units.
            original.stop_early_native_actors()?;
        }
    }
    for (unit, before, group) in &original {
        let after = inspect_unit(*unit, deadline)?;
        terminal_unit(before, &after)?;
        group.verify_retired(&after)?;
        let final_state = inspect_unit(*unit, deadline)?;
        terminal_unit(before, &final_state)?;
        group.verify_retired(&final_state)?;
    }
    Ok(())
}
fn system_manager_present() -> Result<bool> {
    let mut directory = host_root()?;
    for name in [c"run", c"systemd", c"system"] {
        let Some(next) = directory_at(&directory, name, ROOT_CUSTODY)? else {
            return Ok(false);
        };
        directory = next;
    }
    Ok(true)
}
fn manager_required(present: bool, protected: bool) -> Result<bool> {
    if !present && protected {
        return Err(
            "production upgrade/removal requires an actual native systemd quiescence proof".into(),
        );
    }
    Ok(present)
}
fn stop_runtime(spec: Option<&Value>, protected: bool) -> Result<()> {
    if !manager_required(system_manager_present()?, protected)? {
        return Ok(());
    }
    if let Some(uid) = spec
        .and_then(|s| s["host_uid"].as_u64())
        .and_then(|v| u32::try_from(v).ok())
    {
        if Path::new(&format!("/run/user/{uid}/bus")).exists() {
            run(user_command(uid, "/usr/bin/systemctl")?.args([
                "--user",
                "stop",
                "droidloom.service",
                "droidloom-applications.service",
            ]))?;
        }
    }
    stop_native_units(Instant::now() + Duration::from_secs(120), None)
}

fn require_production_resource_retirement(
    lock: &PackageConfigurationLock,
    remove: bool,
) -> Result<()> {
    production_retirement::retire(lock, remove)
}

fn before(remove: bool) -> Result<()> {
    require_root()?;
    root_directory(Path::new(BASE), 0o755)?;
    let lock = setup_lock()?;
    lock.revalidate()?;
    // Production Start/Restart and manager-label activation share this lock.
    // Selection publication and the live retirement RPC remain separate gates.
    let protected = layout()? == Layout::Production;
    // Retire through the original resource owner before any native Stop.
    // This branch never reads legacy state or removes selection/data/fence;
    // even an ambiguous RPC or partial native stop must leave maintenance
    // admission denied until a separately qualified installation can resume.
    if protected {
        return require_production_resource_retirement(&lock, remove);
    }
    let spec = optional_json(Path::new(SPEC))?;
    lock.revalidate()?;
    stop_runtime(spec.as_ref(), protected)?;
    lock.revalidate()?;
    require_legacy()?;
    if remove {
        if let Some(value) = optional_json(Path::new(STATE))? {
            let state: SetupState = serde_json::from_value(value)?;
            let account = user(state.uid)?;
            run(Command::new("/usr/bin/runuser")
                .args(["-u", &account.name, "--", "/usr/bin/env"])
                .arg(format!("XDG_DATA_HOME={}", state.data_home.display()))
                .arg(format!("XDG_STATE_HOME={}", state.state_home.display()))
                .args(["/usr/bin/droidloom-applications", "--remove-managed"]))?;
        }
        for path in [RULE, ENVIRONMENT, STATE] {
            match fs::remove_file(path) {
                Ok(()) => {}
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                Err(e) => return Err(e.into()),
            }
        }
        println!(
            "Droidloom stopped. Android application data and personal configuration were retained."
        );
    }
    Ok(())
}
fn after_install() -> Result<()> {
    require_root()?;
    root_directory(Path::new(BASE), 0o755)?;
    let lock = setup_lock()?;
    lock.revalidate()?;
    if layout()? == Layout::Production {
        println!(
            "Package update preserved the production selection, cell configuration and Android data."
        );
        return Ok(());
    }
    // setup takes the same lock and rechecks the marker inside it. A future
    // production selector still has to join this shared lock contract.
    drop(lock);
    if let Some(spec) = optional_json(Path::new(SPEC))? {
        let uid = u32::try_from(
            spec["host_uid"]
                .as_u64()
                .ok_or("invalid existing desktop owner")?,
        )?;
        setup(uid, None, None, true)?;
    }
    println!("Droidloom is installed and stopped. Run droidloomctl start as your desktop user.");
    println!(
        "First start may request administrator authentication to create /etc/droidloom configuration, the service authorization rule, and Android data files under /var/lib/droidloom. Builds and subsequent starts do not need sudo."
    );
    Ok(())
}
fn execute() -> Result<()> {
    match Cli::parse().action {
        Action::Prepare => prepare(),
        Action::Setup {
            uid,
            data_home,
            state_home,
        } => setup(uid, data_home, state_home, false),
        Action::BeforeUpgrade => before(false),
        Action::BeforeRemove => before(true),
        Action::AfterInstall => after_install(),
    }
}
fn main() {
    if let Err(error) = execute() {
        eprintln!("Droidloom package setup failed: {error}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn recipe() -> Value {
        let mut recipe: Value = serde_json::from_str(include_str!(
            "../../../packaging/cell-spec-x86_64-u1000.json"
        ))
        .unwrap();
        recipe["image_dir"] = json!("/usr/lib/droidloom/images");
        recipe["vendor_image"] = json!("/usr/lib/droidloom/images/images/vendor.raw.img");
        recipe["shared_storage_directories"] = json!([]);
        recipe
    }
    #[test]
    fn setup_uses_target_user_and_retains_personal_state_during_upgrade() {
        let mut previous = configuration(recipe(), None, 1234, "/dev/dri/renderD129").unwrap();
        assert_eq!(
            previous["denial_socket"],
            "/run/user/1234/droidloom/native-bridge.sock"
        );
        assert_eq!(previous["runtime_dir"], "/run/droidloom/cells/u1234");
        assert_eq!(previous["data_dir"], "/var/lib/droidloom/users/1234/data");
        previous["data_dir"] = json!("/var/lib/droidloom/preserved-data");
        previous["gapps_dir"] = json!("/usr/lib/droidloom/addons/gapps");
        previous["android_file_overrides"] = json!([]);
        let updated =
            configuration(recipe(), Some(&previous), 1234, "/dev/dri/renderD128").unwrap();
        assert_eq!(updated["data_dir"], previous["data_dir"]);
        assert_eq!(updated["gapps_dir"], previous["gapps_dir"]);
        assert!(
            !updated["android_file_overrides"]
                .as_array()
                .unwrap()
                .is_empty()
        );
        assert!(configuration(recipe(), Some(&previous), 1000, "/dev/dri/renderD128").is_err());
    }
    #[test]
    fn setup_rejects_root_and_data_path_escape() {
        assert!(configuration(recipe(), None, 0, "/dev/dri/renderD128").is_err());
        let mut previous = configuration(recipe(), None, 1000, "/dev/dri/renderD128").unwrap();
        previous["data_dir"] = json!("/var/lib/droidloom/../../../home/test");
        assert!(configuration(recipe(), Some(&previous), 1000, "/dev/dri/renderD128").is_err());
    }

    fn guarded_fixture() -> (tempfile::TempDir, fs::File, Custody) {
        let temp = tempfile::tempdir().unwrap();
        fs::create_dir_all(temp.path().join("etc/droidloom")).unwrap();
        let root = fs::File::open(temp.path()).unwrap();
        let custody = Custody {
            uid: unsafe { libc::geteuid() },
            gid: unsafe { libc::getegid() },
        };
        (temp, root, custody)
    }
    fn fingerprint(path: &Path) -> (u64, u64, u32, u64, i64, i64, i64, i64) {
        let m = fs::symlink_metadata(path).unwrap();
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.len(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    }
    #[test]
    fn production_guard_preserves_actual_selection_cell_and_data() {
        let (temp, root, custody) = guarded_fixture();
        assert_eq!(layout_at(&root, custody).unwrap(), Layout::Legacy);
        assert!(legacy_layout(Layout::Legacy).is_ok());
        let base = temp.path().join("etc/droidloom");
        fs::create_dir(base.join("production")).unwrap();
        let paths = [
            base.join("production/selected.json"),
            base.join("cell.json"),
            base.join("data.img"),
        ];
        for path in &paths {
            fs::write(path, b"selected original bytes\n").unwrap();
        }
        let before = paths
            .iter()
            .map(|p| (fingerprint(p), fs::read(p).unwrap()))
            .collect::<Vec<_>>();
        for _ in 0..3 {
            let mode = layout_at(&root, custody).unwrap();
            assert_eq!(mode, Layout::Production);
            assert!(legacy_layout(mode).is_err());
        }
        let after = paths
            .iter()
            .map(|p| (fingerprint(p), fs::read(p).unwrap()))
            .collect::<Vec<_>>();
        assert_eq!(before, after);
    }
    #[test]
    fn production_guard_refuses_dangling_and_redirected_marker_parents() {
        let (temp, root, custody) = guarded_fixture();
        let base = temp.path().join("etc/droidloom");
        fs::create_dir(base.join("production")).unwrap();
        std::os::unix::fs::symlink("missing", base.join("production/selected.json")).unwrap();
        assert!(layout_at(&root, custody).is_err());
        fs::remove_file(base.join("production/selected.json")).unwrap();
        fs::remove_dir(base.join("production")).unwrap();
        std::os::unix::fs::symlink("missing", base.join("production")).unwrap();
        assert!(layout_at(&root, custody).is_err());
        fs::remove_file(base.join("production")).unwrap();
        let external = temp.path().join("other");
        fs::create_dir(&external).unwrap();
        fs::write(external.join("selected.json"), b"original").unwrap();
        std::os::unix::fs::symlink(&external, base.join("production")).unwrap();
        assert!(layout_at(&root, custody).is_err());
        assert_eq!(
            fs::read(external.join("selected.json")).unwrap(),
            b"original"
        );
    }
    #[test]
    fn production_guard_refuses_partial_special_writable_and_hardlinked_markers() {
        let (temp, root, custody) = guarded_fixture();
        let directory = temp.path().join("etc/droidloom/production");
        fs::create_dir(&directory).unwrap();
        assert!(layout_at(&root, custody).is_err());
        let marker = directory.join("selected.json");
        fs::create_dir(&marker).unwrap();
        assert!(layout_at(&root, custody).is_err());
        fs::remove_dir(&marker).unwrap();
        fs::write(&marker, b"original").unwrap();
        fs::set_permissions(&marker, fs::Permissions::from_mode(0o666)).unwrap();
        assert!(layout_at(&root, custody).is_err());
        fs::set_permissions(&marker, fs::Permissions::from_mode(0o600)).unwrap();
        fs::hard_link(&marker, directory.join("second-link")).unwrap();
        assert!(layout_at(&root, custody).is_err());
        fs::remove_file(directory.join("second-link")).unwrap();
        fs::set_permissions(&directory, fs::Permissions::from_mode(0o777)).unwrap();
        assert!(layout_at(&root, custody).is_err());
    }
    #[test]
    fn setup_lock_is_nonfollowing_single_link_and_exclusively_held() {
        let (temp, _, custody) = guarded_fixture();
        let path = temp.path().join("etc/droidloom");
        let directory = fs::File::open(&path).unwrap();
        let original = setup_lock_at(&directory, custody).unwrap();
        assert!(setup_lock_at(&directory, custody).is_err());
        drop(original);
        drop(setup_lock_at(&directory, custody).unwrap());
        fs::hard_link(path.join("setup.lock"), path.join("other-lock-link")).unwrap();
        assert!(setup_lock_at(&directory, custody).is_err());
        fs::remove_file(path.join("other-lock-link")).unwrap();
        fs::remove_file(path.join("setup.lock")).unwrap();
        std::os::unix::fs::symlink("missing-lock", path.join("setup.lock")).unwrap();
        assert!(setup_lock_at(&directory, custody).is_err());
        assert!(!path.join("missing-lock").exists());
    }
    fn terminal_properties() -> String {
        format!(
            "Id=droidloom-production.service\nLoadState=loaded\nActiveState=inactive\nSubState=dead\nMainPID=0\nControlPID=0\nInvocationID={}\nControlGroup=\nJob=\n",
            "a".repeat(32)
        )
    }
    #[test]
    fn native_unit_observation_refuses_incomplete_duplicate_and_foreign_identity() {
        let good = terminal_properties();
        assert!(parse_unit(NativeUnit::Production, good.as_bytes()).is_ok());
        for bad in [
            good.replace("MainPID=0\n", ""),
            good.clone() + "MainPID=0\n",
            good.replace("Id=droidloom-production.service", "Id=another.service"),
            good.replace(
                "ControlGroup=\n",
                "ControlGroup=/user.slice/other.service\n",
            ),
            good.replace("LoadState=loaded", "LoadState=error"),
            good.replace(&"a".repeat(32), "not-an-invocation"),
        ] {
            assert!(parse_unit(NativeUnit::Production, bad.as_bytes()).is_err());
        }
    }
    #[test]
    fn native_stop_refuses_pending_jobs_live_actors_and_new_invocations() {
        let good = terminal_properties();
        let before = parse_unit(NativeUnit::Production, good.as_bytes()).unwrap();
        assert!(terminal_unit(&before, &before).is_ok());
        for bad in [
            good.replace("MainPID=0", "MainPID=42"),
            good.replace("ControlPID=0", "ControlPID=43"),
            good.replace("Job=\n", "Job=44\n"),
            good.replace("ActiveState=inactive", "ActiveState=deactivating"),
            good.replace("SubState=dead", "SubState=failed"),
            good.replace(&"a".repeat(32), &"b".repeat(32)),
        ] {
            let after = parse_unit(NativeUnit::Production, bad.as_bytes()).unwrap();
            assert!(terminal_unit(&before, &after).is_err());
        }
        let failed = good
            .replace("ActiveState=inactive", "ActiveState=failed")
            .replace("SubState=dead", "SubState=failed");
        assert!(
            terminal_unit(
                &before,
                &parse_unit(NativeUnit::Production, failed.as_bytes()).unwrap()
            )
            .is_ok()
        );
        assert!(unpopulated(b"populated 1\nfrozen 0\n").is_err());
    }
    #[test]
    fn cgroup_quiescence_requires_complete_actual_populated_zero() {
        assert!(unpopulated(b"populated 0\nfrozen 0\n").is_ok());
        for invalid in [
            b"".as_slice(),
            b"frozen 0\n",
            b"populated 1\nfrozen 0\n",
            b"populated 0\npopulated 0\nfrozen 0\n",
            b"populated false\nfrozen 0\n",
            b"populated 0\nfrozen 0\nunknown 0\n",
        ] {
            assert!(unpopulated(invalid).is_err());
        }
    }
    #[test]
    fn native_command_bounds_refuse_expired_execution_and_oversized_output() {
        assert!(
            native_command(
                NativeAction::Stop(NativeUnit::Production),
                Instant::now() - Duration::from_secs(1)
            )
            .is_err()
        );
        let mut input = std::io::Cursor::new(vec![b'x'; 64 * 1024 + 1]);
        let mut output = Vec::new();
        assert!(drain(&mut input, &mut output).is_err());
        assert!(output.len() <= 64 * 1024);
    }
    #[test]
    fn selected_production_cannot_use_the_legacy_offline_upgrade_shortcut() {
        assert!(manager_required(false, true).is_err());
        assert!(!manager_required(false, false).unwrap());
        assert!(manager_required(true, true).unwrap());
    }
    #[test]
    fn native_stop_revalidates_original_generation_before_each_stop() {
        let live = terminal_properties()
            .replace("ActiveState=inactive", "ActiveState=active")
            .replace("SubState=dead", "SubState=running")
            .replace("MainPID=0", "MainPID=42")
            .replace(
                "ControlGroup=\n",
                "ControlGroup=/system.slice/droidloom-production.service\n",
            );
        let before = parse_unit(NativeUnit::Production, live.as_bytes()).unwrap();
        assert!(same_stop_generation(&before, &before).is_ok());
        for changed in [
            live.replace(&"a".repeat(32), &"b".repeat(32)),
            live.replace("MainPID=42", "MainPID=43"),
            live.replace("ControlPID=0", "ControlPID=44"),
            live.replace("Job=\n", "Job=45\n"),
            live.replace("ActiveState=active", "ActiveState=activating"),
            live.replace("SubState=running", "SubState=unknown"),
            live.replace(
                "ControlGroup=/system.slice/droidloom-production.service\n",
                "ControlGroup=\n",
            ),
            live.replace(
                &format!("InvocationID={}\n", "a".repeat(32)),
                "InvocationID=\n",
            ),
        ] {
            let current = parse_unit(NativeUnit::Production, changed.as_bytes()).unwrap();
            assert!(same_stop_generation(&before, &current).is_err());
        }
        assert!(population(b"populated 1\nfrozen 0\n").unwrap());
        assert!(population(b"populated 1\n").is_err());
    }
    #[test]
    fn native_stop_accepts_original_exited_oneshot_and_rejects_identity_changes() {
        // The active/exited, MainPID=0, absent-group and InvocationID shape is
        // observed in the Pocket4 MAC carrier's original retirement evidence.
        // ControlPID=0 and an empty Job remain additional required observations.
        let exited = terminal_properties()
            .replace(
                "Id=droidloom-production.service",
                "Id=droidloom-manager-label.service",
            )
            .replace("ActiveState=inactive", "ActiveState=active")
            .replace("SubState=dead", "SubState=exited")
            .replace(&"a".repeat(32), "03c26bb6e98941cdbb45ef79cbbecafc");
        let original = parse_unit(NativeUnit::ManagerLabel, exited.as_bytes()).unwrap();
        assert!(original.group.is_empty());
        assert!(stable_stop_state(&original).is_ok());
        assert!(same_stop_generation(&original, &original).is_ok());
        for changed in [
            exited.replace("MainPID=0", "MainPID=42"),
            exited.replace("ControlPID=0", "ControlPID=43"),
            exited.replace("Job=\n", "Job=44\n"),
            exited.replace("03c26bb6e98941cdbb45ef79cbbecafc", &"b".repeat(32)),
            exited.replace(
                "InvocationID=03c26bb6e98941cdbb45ef79cbbecafc",
                "InvocationID=",
            ),
            exited.replace(
                "ControlGroup=\n",
                "ControlGroup=/system.slice/droidloom-manager-label.service\n",
            ),
            exited.replace("SubState=exited", "SubState=running"),
        ] {
            let current = parse_unit(NativeUnit::ManagerLabel, changed.as_bytes()).unwrap();
            assert!(same_stop_generation(&original, &current).is_err());
        }
        let with_group = exited.replace(
            "ControlGroup=\n",
            "ControlGroup=/system.slice/droidloom-manager-label.service\n",
        );
        let with_group = parse_unit(NativeUnit::ManagerLabel, with_group.as_bytes()).unwrap();
        assert!(same_stop_generation(&with_group, &with_group).is_ok());
        // These state checks alone cannot prove the held cgroup/absence gates
        // or authorize production replacement; those checks are unchanged.
    }
}
