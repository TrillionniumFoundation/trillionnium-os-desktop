//! PID 1 of the host-managed cell. Namespace and image ownership belong to
//! the outer manager. This process owns the fixed Android bootstrap child.
#[path = "../production_cp3a_init_identity.rs"]
mod production_cp3a_init_identity;
#[path = "../production_service_elf.rs"]
mod production_service_elf;

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::AsRawFd;
use std::os::linux::net::SocketAddrExt;
use std::os::unix::fs::{FileTypeExt, MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{SocketAddr, UnixDatagram, UnixListener, UnixStream};
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use sha2::{Digest, Sha256};

const BOOTSTRAP: &str = "/droidloom/bin/container-bootstrap";
const DECLARATION: &str = "/etc/droidloom/container-launcher.json";
const CONTROL: &str = "/run/droidloom/control.sock";
const START_LIMIT: Duration = Duration::from_secs(240);
static STOP: AtomicBool = AtomicBool::new(false);

fn error(s: &str) -> io::Error {
    io::Error::other(s)
}

extern "C" fn stopping(_: libc::c_int) {
    STOP.store(true, Ordering::Relaxed);
}

fn kernel_text(path: &str) -> io::Result<String> {
    let f = File::open(path)?;
    let mut stat = std::mem::MaybeUninit::<libc::statfs>::uninit();
    if unsafe { libc::fstatfs(f.as_raw_fd(), stat.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { stat.assume_init().f_type } != libc::PROC_SUPER_MAGIC {
        return Err(error("cell identity must come from procfs"));
    }
    let mut text = String::new();
    f.take(65537).read_to_string(&mut text)?;
    if text.len() > 65536 {
        return Err(error("oversized kernel state"));
    }
    Ok(text)
}

fn mapped_range(value: &str) -> bool {
    let rows: Vec<_> = value.lines().collect();
    if rows.len() != 1 {
        return false;
    }
    let fields: Vec<_> = rows[0].split_whitespace().map(str::parse::<u32>).collect();
    matches!(fields.as_slice(), [Ok(0), Ok(base), Ok(count)] if *base >= 65536 && *count >= 65536 && base.checked_add(*count).is_some())
}

fn entry_context() -> io::Result<()> {
    if std::process::id() != 1 {
        return Err(error("container entry must be PID 1 in its prepared cell"));
    }
    if !mapped_range(&kernel_text("/proc/self/uid_map")?)
        || !mapped_range(&kernel_text("/proc/self/gid_map")?)
    {
        return Err(error(
            "host-managed cell needs its subordinate user and group namespace maps",
        ));
    }
    let status = kernel_text("/proc/self/status")?;
    let field = |name| {
        status
            .lines()
            .find_map(|line| line.strip_prefix(name))
            .map(str::trim)
    };
    if field("NoNewPrivs:") != Some("1") || field("Seccomp:") != Some("2") {
        return Err(error(
            "the admitted cell seccomp filter and no_new_privs must be active",
        ));
    }
    let selinux = kernel_text("/proc/self/attr/selinux/current")?;
    let apparmor = kernel_text("/proc/self/attr/apparmor/current")?;
    if selinux.trim_end_matches(['\0', '\n']) != "u:r:droidloom_container_entry:s0"
        || apparmor.trim_end() != "droidloom-container-entry (enforce)"
    {
        return Err(error(
            "the fixed host-managed service role must be active before Android execution",
        ));
    }
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BootstrapRelease {
    schema: String,
    launcher: String,
    selection_sha256: String,
    entry_bytes: usize,
    entry_sha256: String,
    bootstrap_bytes: usize,
    bootstrap_sha256: String,
}

fn held_file(path: &str, limit: usize, executable: bool) -> io::Result<(File, Vec<u8>)> {
    let f = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    let meta = f.metadata()?;
    if !meta.is_file()
        || meta.uid() != 0
        || meta.gid() != 0
        || meta.nlink() != 1
        || meta.mode() & 0o6022 != 0
        || executable && meta.mode() & 0o111 == 0
        || meta.len() == 0
        || meta.len() > limit as u64
    {
        return Err(error("invalid immutable bootstrap package member"));
    }
    let mut fsstat = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    if unsafe { libc::fstatvfs(f.as_raw_fd(), fsstat.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { fsstat.assume_init().f_flag } & libc::ST_RDONLY == 0 {
        return Err(error(
            "bootstrap inputs require a read-only mounted filesystem",
        ));
    }
    let mut data = Vec::new();
    (&f).take(limit as u64 + 1).read_to_end(&mut data)?;
    if data.len() as u64 != meta.len() {
        return Err(error("bootstrap package member changed during inspection"));
    }
    Ok((f, data))
}

fn bootstrap() -> io::Result<Child> {
    let (_, data) = held_file(DECLARATION, 4096, false)?;
    let release: BootstrapRelease = serde_json::from_slice(&data).map_err(io::Error::other)?;
    let digest = |s: &str| {
        s.len() == 64
            && s.bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    };
    if release.schema != "droidloom-public-launcher-v3"
        || release.launcher != "host_managed_shared_kernel_v1"
        || !digest(&release.selection_sha256)
        || !digest(&release.entry_sha256)
        || !digest(&release.bootstrap_sha256)
        || !(64..=production_service_elf::MAX_SERVICE).contains(&release.entry_bytes)
    {
        return Err(error(
            "the cell requires the same published host-managed launch selection as the host",
        ));
    }
    let own = File::open("/proc/self/exe")?;
    if own.metadata()?.len() != release.entry_bytes as u64 {
        return Err(error("provider size differs from the published generation"));
    }
    let mut digest = Sha256::new();
    let mut stream = own.take(release.entry_bytes as u64 + 1);
    if io::copy(&mut stream, &mut digest)? != release.entry_bytes as u64
        || format!("{:x}", digest.finalize()) != release.entry_sha256
    {
        return Err(error(
            "running provider differs from the published generation",
        ));
    }
    let (program, bytes) = held_file(BOOTSTRAP, production_service_elf::MAX_SERVICE, true)?;
    if release.bootstrap_bytes != bytes.len()
        || release.bootstrap_sha256 != format!("{:x}", Sha256::digest(&bytes))
    {
        return Err(error(
            "dedicated Android bootstrap does not match its immutable release",
        ));
    }
    production_service_elf::inspect_container_service_elf(&bytes)?;
    let mut cmd = Command::new(format!("/proc/self/fd/{}", program.as_raw_fd()));
    cmd.arg0(BOOTSTRAP)
        .current_dir("/")
        .env_clear()
        .env("PATH", "/system/bin:/system/xbin")
        .env("ANDROID_ROOT", "/system")
        .env("ANDROID_DATA", "/data")
        .env("ANDROID_RUNTIME_ROOT", "/apex/com.android.runtime")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
}

struct Bootstrap {
    child: Child,
    exit: Option<ExitStatus>,
}

impl Bootstrap {
    fn poll(&mut self) -> io::Result<Option<ExitStatus>> {
        if self.exit.is_some() {
            return Ok(self.exit);
        }
        loop {
            let mut status = 0;
            let pid = unsafe { libc::waitpid(-1, &mut status, libc::WNOHANG) };
            if pid > 0 {
                if pid as u32 == self.child.id() {
                    self.exit = Some(ExitStatus::from_raw(status));
                }
                continue;
            }
            if pid == 0 {
                return Ok(self.exit);
            }
            let e = io::Error::last_os_error();
            if e.kind() == io::ErrorKind::Interrupted {
                continue;
            }
            if e.raw_os_error() == Some(libc::ECHILD) && self.exit.is_some() {
                return Ok(self.exit);
            }
            return Err(e);
        }
    }
    fn stop(&mut self) -> io::Result<()> {
        if self.poll()?.is_some() {
            return Ok(());
        }
        if unsafe { libc::kill(self.child.id() as i32, libc::SIGTERM) } < 0
            && io::Error::last_os_error().raw_os_error() != Some(libc::ESRCH)
        {
            return Err(io::Error::last_os_error());
        }
        let end = Instant::now() + Duration::from_secs(5);
        while Instant::now() < end {
            if self.poll()?.is_some() {
                return Ok(());
            }
            thread::sleep(Duration::from_millis(25));
        }
        self.child.kill()?;
        self.exit = Some(self.child.wait()?);
        Ok(())
    }
}

fn fixed_probe(program: &str, args: &[&str], expected: &str) -> io::Result<bool> {
    let result = Command::new(program)
        .args(args)
        .env_clear()
        .env("PATH", "/system/bin")
        .env("ANDROID_ROOT", "/system")
        .env("ANDROID_DATA", "/data")
        .env("ANDROID_RUNTIME_ROOT", "/apex/com.android.runtime")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn();
    let mut child = match result {
        Ok(child) => child,
        Err(e) if e.kind() == io::ErrorKind::NotFound => return Ok(false),
        Err(e) => return Err(e),
    };
    let end = Instant::now() + Duration::from_secs(2);
    loop {
        if let Some(status) = child.try_wait()? {
            let mut output = Vec::new();
            if status.success() {
                let stream = child.stdout.take().unwrap();
                let fd = stream.as_raw_fd();
                let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
                if flags < 0
                    || unsafe { libc::fcntl(fd, libc::F_SETFL, flags | libc::O_NONBLOCK) } < 0
                {
                    return Err(io::Error::last_os_error());
                }
                match stream.take(513).read_to_end(&mut output) {
                    Ok(_) => {}
                    Err(e) if e.kind() == io::ErrorKind::WouldBlock => return Ok(false),
                    Err(e) => return Err(e),
                }
            }
            return Ok(output.len() <= 512
                && std::str::from_utf8(&output).is_ok_and(|s| s.trim_end() == expected));
        }
        if STOP.load(Ordering::Relaxed) || Instant::now() >= end {
            child.kill()?;
            child.wait()?;
            return Ok(false);
        }
        thread::sleep(Duration::from_millis(20));
    }
}

#[derive(Default)]
struct Readiness {
    binder: bool,
    android: bool,
}

fn readiness() -> io::Result<Readiness> {
    let binder = fixed_probe("/system/bin/getprop", &["servicemanager.ready"], "true")?
        && fixed_probe(
            "/system/bin/service",
            &["check", "manager"],
            "Service manager: found",
        )?;
    let android = binder
        && fixed_probe("/system/bin/getprop", &["sys.boot_completed"], "1")?
        && fixed_probe(
            "/system/bin/service",
            &["check", "activity"],
            "Service activity: found",
        )?;
    Ok(Readiness { binder, android })
}

fn notify_main() -> io::Result<()> {
    let dest = std::env::var_os("NOTIFY_SOCKET")
        .ok_or_else(|| error("missing system manager notification socket"))?;
    use std::os::unix::ffi::OsStrExt;
    let buf = dest.as_bytes();
    let addr = if let Some(name) = buf.strip_prefix(b"@") {
        SocketAddr::from_abstract_name(name)?
    } else {
        SocketAddr::from_pathname(PathBuf::from(dest))?
    };
    UnixDatagram::unbound()?.send_to_addr(b"READY=1", &addr)?;
    Ok(())
}

struct Control {
    listener: UnixListener,
    identity: (u64, u64),
}
impl Control {
    fn bind() -> io::Result<Self> {
        let parent = Path::new(CONTROL).parent().unwrap();
        let dir = fs::symlink_metadata(parent)?;
        if !dir.is_dir() || dir.uid() != unsafe { libc::geteuid() } || dir.mode() & 0o022 != 0 {
            return Err(error("fixed control socket directory lacks cell ownership"));
        }
        let listener = UnixListener::bind(CONTROL)?;
        let node = fs::symlink_metadata(CONTROL)?;
        let owner = Self {
            listener,
            identity: (node.dev(), node.ino()),
        };
        fs::set_permissions(CONTROL, fs::Permissions::from_mode(0o660))?;
        owner.listener.set_nonblocking(true)?;
        Ok(owner)
    }
}
impl Drop for Control {
    fn drop(&mut self) {
        if let Ok(n) = fs::symlink_metadata(CONTROL) {
            if n.file_type().is_socket() && (n.dev(), n.ino()) == self.identity {
                let _ = fs::remove_file(CONTROL);
            }
        }
    }
}

fn reply(stream: &mut UnixStream, ok: bool, ready: bool, message: &str) -> io::Result<()> {
    let frame =
        serde_json::json!({"ok":ok,"state":if ready{"running"}else{"starting"},"message":message});
    serde_json::to_writer(&mut *stream, &frame).map_err(io::Error::other)?;
    stream.write_all(b"\n")
}

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
enum Query {
    Status,
    Readiness,
    WaitReady,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    command: Query,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Progress {
    request: Request,
}
#[derive(Deserialize)]
#[serde(untagged)]
enum Incoming {
    Direct(Request),
    Progress(Progress),
}

fn request(stream: &mut UnixStream) -> io::Result<Query> {
    stream.set_write_timeout(Some(Duration::from_millis(200)))?;
    let end = Instant::now() + Duration::from_millis(200);
    let mut bytes = Vec::new();
    let mut chunk = [0; 256];
    loop {
        let remaining = end
            .checked_duration_since(Instant::now())
            .filter(|v| !v.is_zero())
            .ok_or_else(|| error("readiness request deadline"))?;
        stream.set_read_timeout(Some(remaining))?;
        let n = stream.read(&mut chunk)?;
        if n == 0 {
            break;
        }
        bytes.extend_from_slice(&chunk[..n]);
        if bytes.len() > 1024 {
            return Err(error("oversized readiness request"));
        }
    }
    let frame: Incoming = serde_json::from_slice(&bytes).map_err(io::Error::other)?;
    Ok(match frame {
        Incoming::Direct(req) => req.command,
        Incoming::Progress(msg) => msg.request.command,
    })
}

fn serve(owner: &mut Bootstrap, control: &Control) -> io::Result<()> {
    let end = Instant::now() + START_LIMIT;
    let mut next = Instant::now();
    let mut notified = false;
    let mut current = Readiness::default();
    let mut pending: Vec<(UnixStream, Instant)> = Vec::new();
    while !STOP.load(Ordering::Relaxed) {
        if let Some(status) = owner.poll()? {
            return Err(io::Error::other(format!(
                "Android bootstrap exited: {status}"
            )));
        }
        if Instant::now() >= next {
            current = readiness()?;
            if owner.poll()?.is_some() {
                return Err(error("Android bootstrap exited during readiness check"));
            }
            if notified && !current.binder {
                return Err(error(
                    "the current Android Binder manager became unavailable",
                ));
            }
            if current.binder && !notified {
                notify_main()?;
                notified = true;
            }
            next = Instant::now() + Duration::from_secs(1);
        }
        if !notified && Instant::now() >= end {
            return Err(error(
                "Android Binder manager did not become ready before the startup deadline",
            ));
        }
        pending.retain_mut(|(socket, deadline)| {
            if current.android || Instant::now() >= *deadline {
                let _ = reply(
                    socket,
                    current.android,
                    current.android,
                    if current.android {
                        "Android boot completed and ActivityManager answers Binder"
                    } else {
                        "Android readiness deadline expired"
                    },
                );
                false
            } else {
                true
            }
        });
        match control.listener.accept() {
            Ok((mut socket, _)) => match request(&mut socket) {
                Ok(Query::WaitReady) if !current.android && pending.len() < 8 => {
                    pending.push((socket, Instant::now() + START_LIMIT))
                }
                Ok(Query::WaitReady) if !current.android => {
                    let _ = reply(&mut socket, false, false, "Readiness request queue is full");
                }
                Ok(_) => {
                    let _ = reply(
                        &mut socket,
                        true,
                        current.android,
                        if current.android {
                            "Android boot completed and ActivityManager answers Binder"
                        } else {
                            "Waiting for Android boot"
                        },
                    );
                }
                Err(_) => {
                    let _ = reply(&mut socket, false, false, "Unsupported readiness request");
                }
            },
            Err(e) if e.kind() == io::ErrorKind::WouldBlock => {
                thread::sleep(Duration::from_millis(40))
            }
            Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
            Err(e) => return Err(e),
        }
    }
    Ok(())
}

fn run() -> io::Result<()> {
    if std::env::args_os().len() != 1 {
        return Err(error("container entry accepts no arguments"));
    }
    entry_context()?;
    for sig in [libc::SIGTERM, libc::SIGINT] {
        if unsafe { libc::signal(sig, stopping as libc::sighandler_t) } == libc::SIG_ERR {
            return Err(io::Error::last_os_error());
        }
    }
    let control = Control::bind()?;
    let mut owner = Bootstrap {
        child: bootstrap()?,
        exit: None,
    };
    let live = serve(&mut owner, &control);
    let retired = owner.stop();
    retired.and(live)
}

fn main() {
    if let Err(e) = run() {
        eprintln!("droidloom-container-entry: {e}");
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn actual_child_is_terminated_and_reaped() {
        let child = Command::new("/usr/bin/sleep").arg("30").spawn().unwrap();
        let mut owner = Bootstrap { child, exit: None };
        assert!(owner.poll().unwrap().is_none());
        owner.stop().unwrap();
        assert!(owner.poll().unwrap().is_some());
    }
    #[test]
    fn original_pid1_and_subordinate_namespace_are_required() {
        assert!(entry_context().is_err());
        assert!(mapped_range("0 200000 65536\n"));
        assert!(!mapped_range("0 0 4294967295\n"));
        assert!(!mapped_range("0 1000 1\n"));
    }
    #[test]
    fn only_fixed_readonly_requests_are_accepted() {
        for (body, allowed) in [
            (r#"{"request":{"command":"wait_ready"}}"#, true),
            (r#"{"command":"readiness"}"#, true),
            (r#"{"command":"launch"}"#, false),
            (r#"{"command":"status","path":"/other"}"#, false),
        ] {
            let (mut client, mut server) = UnixStream::pair().unwrap();
            client.write_all(body.as_bytes()).unwrap();
            client.shutdown(std::net::Shutdown::Write).unwrap();
            assert_eq!(request(&mut server).is_ok(), allowed);
        }
    }
}
