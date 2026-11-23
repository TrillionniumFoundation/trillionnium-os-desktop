//! PID 1 of the host-managed cell. Namespace and image ownership belong to
//! the outer manager. This process owns the fixed Android bootstrap child.
#[path = "../production_cp3a_init_identity.rs"]
mod production_cp3a_init_identity;
#[path = "../production_service_elf.rs"]
mod production_service_elf;

use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::net::UnixStream;
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::Path;
use std::process::{Child, Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use sha2::{Digest, Sha256};

const BOOTSTRAP: &str = "/droidloom/bin/container-bootstrap";
const DECLARATION: &str = "/etc/droidloom/container-launcher.json";
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

fn held_file(
    path: &str,
    limit: usize,
    executable: bool,
    group: u32,
) -> io::Result<(File, Vec<u8>)> {
    let f = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    let meta = f.metadata()?;
    if !meta.is_file()
        || meta.uid() != 0
        || meta.gid() != group
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
    let (_, data) = held_file(DECLARATION, 4096, false, 0)?;
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
    let (program, bytes) = held_file(BOOTSTRAP, production_service_elf::MAX_SERVICE, true, 0)?;
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

struct AndroidProbes {
    toolbox: File,
    service: File,
}

impl AndroidProbes {
    fn from_selected_cp3a() -> io::Result<Self> {
        if fs::read_link("/system/bin/getprop")? != Path::new("toolbox") {
            return Err(error(
                "selected CP3A getprop must be the original toolbox applet",
            ));
        }
        let held = |path, length, digest: &str| -> io::Result<File> {
            let (file, bytes) = held_file(path, length, true, 2000)?;
            if bytes.len() != length || format!("{:x}", Sha256::digest(&bytes)) != digest {
                return Err(error(
                    "Android readiness program differs from the original CP3A image",
                ));
            }
            Ok(file)
        };
        Ok(Self {
            toolbox: held(
                "/system/bin/toolbox",
                169856,
                "a1d2b30312db7b099cfc4f25b712420b46574affa0d73709add5bc7630d55ae8",
            )?,
            service: held(
                "/system/bin/service",
                51760,
                "da64083b28a0f1855f0cfb71c27633378e562b926009e21d9fd2ab598504498e",
            )?,
        })
    }
}

fn fixed_probe(program: &File, argv0: &str, args: &[&str], expected: &str) -> io::Result<bool> {
    let result = Command::new(format!("/proc/self/fd/{}", program.as_raw_fd()))
        .arg0(argv0)
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

fn readiness(tools: &AndroidProbes) -> io::Result<Readiness> {
    let binder = fixed_probe(
        &tools.toolbox,
        "/system/bin/getprop",
        &["servicemanager.ready"],
        "true",
    )? && fixed_probe(
        &tools.service,
        "/system/bin/service",
        &["check", "manager"],
        "Service manager: found",
    )?;
    let android = binder
        && fixed_probe(
            &tools.toolbox,
            "/system/bin/getprop",
            &["sys.boot_completed"],
            "1",
        )?
        && fixed_probe(
            &tools.service,
            "/system/bin/service",
            &["check", "activity"],
            "Service activity: found",
        )?;
    Ok(Readiness { binder, android })
}

const HOST_CHANNEL: &str = "/run/droidloom/host-owner.sock";

fn contact_host() -> io::Result<UnixStream> {
    let end = Instant::now() + START_LIMIT;
    loop {
        match UnixStream::connect(HOST_CHANNEL) {
            Ok(stream) => {
                stream.set_write_timeout(Some(Duration::from_secs(2)))?;
                return Ok(stream);
            }
            Err(e)
                if matches!(
                    e.kind(),
                    io::ErrorKind::NotFound | io::ErrorKind::ConnectionRefused
                ) && !STOP.load(Ordering::Relaxed)
                    && Instant::now() < end =>
            {
                thread::sleep(Duration::from_millis(50))
            }
            Err(e) => return Err(e),
        }
    }
}

fn serve(owner: &mut Bootstrap, host: &mut UnixStream, tools: &AndroidProbes) -> io::Result<()> {
    let end = Instant::now() + START_LIMIT;
    let mut established = false;
    let mut next = Instant::now();
    while !STOP.load(Ordering::Relaxed) {
        if let Some(status) = owner.poll()? {
            return Err(io::Error::other(format!(
                "Android bootstrap exited: {status}"
            )));
        }
        if Instant::now() >= next {
            let current = readiness(tools)?;
            if owner.poll()?.is_some() {
                return Err(error("Android bootstrap exited during readiness check"));
            }
            if established && !current.binder {
                return Err(error(
                    "the current Android Binder manager became unavailable",
                ));
            }
            if !current.binder && Instant::now() >= end {
                return Err(error(
                    "Android Binder manager did not become ready before the startup deadline",
                ));
            }
            established |= current.binder;
            host.write_all(&[if current.android {
                2
            } else if current.binder {
                1
            } else {
                0
            }])?;
            next = Instant::now() + Duration::from_secs(1);
        }
        thread::sleep(Duration::from_millis(40));
    }
    Ok(())
}
fn run() -> io::Result<()> {
    if std::env::args_os().len() != 1 {
        return Err(error("container entry accepts no arguments"));
    }
    entry_context()?;
    for sig in [libc::SIGTERM, libc::SIGINT] {
        if unsafe { libc::signal(sig, stopping as *const () as libc::sighandler_t) }
            == libc::SIG_ERR
        {
            return Err(io::Error::last_os_error());
        }
    }
    let tools = AndroidProbes::from_selected_cp3a()?;
    let mut host = contact_host()?;
    let mut owner = Bootstrap {
        child: bootstrap()?,
        exit: None,
    };
    let live = serve(&mut owner, &mut host, &tools);
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
}
