use super::super::{DEVELOPMENT_UNSHARE_ARGUMENTS, DevelopmentCell, arm_development_parent_death};
use super::*;
use crate::CellSpec;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};

const FIXTURE: &str = "development::owned_process::tests::namespace_init_fixture";
const LAUNCHER: &str = "development::owned_process::tests::namespace_launcher_fixture";
const EARLY: &str = "development::owned_process::tests::namespace_preexec_fixture";
static TERM: AtomicBool = AtomicBool::new(false);

extern "C" fn term_handler(_: libc::c_int) {
    TERM.store(true, Ordering::SeqCst);
}

fn fixture_command(name: &str, directory: &Path, mode: &str) -> Command {
    let mut command = Command::new(std::env::current_exe().unwrap());
    command
        .args([
            "--exact",
            name,
            "--ignored",
            "--nocapture",
            "--test-threads=1",
        ])
        .env("DROIDLOOM_NAMESPACE_TEST_DIR", directory)
        .env("DROIDLOOM_NAMESPACE_TEST_MODE", mode)
        .stdin(Stdio::null())
        .stdout(Stdio::null());
    command
}

fn namespace_command(directory: &Path, mode: &str) -> Command {
    let mut command = Command::new("/usr/bin/unshare");
    command
        .args(DEVELOPMENT_UNSHARE_ARGUMENTS)
        .arg(std::env::current_exe().unwrap())
        .args([
            "--exact",
            FIXTURE,
            "--ignored",
            "--nocapture",
            "--test-threads=1",
        ])
        .env("DROIDLOOM_NAMESPACE_TEST_DIR", directory)
        .env("DROIDLOOM_NAMESPACE_TEST_MODE", mode)
        .stdin(Stdio::null())
        .stdout(Stdio::null());
    arm_development_parent_death(&mut command);
    command
}

struct OwnedFixture {
    child: Child,
    init: Option<OwnedNamespaceChild>,
}

impl Drop for OwnedFixture {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
        if let Some(init) = &self.init {
            let _ = init.retire_after_owner_reaped();
        }
    }
}

struct TestCell(DevelopmentCell);
impl Drop for TestCell {
    fn drop(&mut self) {
        let _ = self.0.stop();
    }
}

fn unused_spec(root: &Path) -> CellSpec {
    CellSpec {
        host_uid: 20001,
        subordinate_uids: crate::IdRange {
            start: 200_000,
            count: 100_000,
        },
        subordinate_gids: crate::IdRange {
            start: 300_000,
            count: 100_000,
        },
        image_dir: root.join("unused-images"),
        image_layout: crate::AndroidImageLayout::default(),
        gapps_dir: None,
        vendor_image: root.join("unused-vendor.img"),
        android_init: None,
        android_file_overrides: Vec::new(),
        android_runtime_directories: Vec::new(),
        shared_storage_directories: Vec::new(),
        data_dir: root.join("unused-data"),
        runtime_dir: root.join("unused-runtime"),
        render_node: "/dev/dri/renderD128".into(),
        graphics_backend: crate::GraphicsBackend::default(),
        denial_socket: root.join("unused-denial.sock"),
    }
}

fn require_root() {
    assert_eq!(
        unsafe { libc::geteuid() },
        0,
        "explicit isolated root control required"
    );
}

fn ready(path: &Path, owner: &mut Child) {
    let deadline = Instant::now() + Duration::from_secs(5);
    while !path.exists() {
        assert!(
            owner.try_wait().unwrap().is_none(),
            "fixture exited before readiness"
        );
        assert!(Instant::now() < deadline, "fixture readiness timed out");
        thread::sleep(Duration::from_millis(5));
    }
}

// Exit notification and retirement are separate kernel events. POLLIN may be
// visible before the actual parent/PID1 has reaped the task. Bind both handles
// while the original parent is still alive; no later numeric PID lookup may
// stand in for the process generation or its namespace membership.
struct RetirementWitness {
    fd: OwnedFd,
    directory: fs::File,
    pid: u32,
    generation: Identity,
}

fn held_pid_namespace(directory: &fs::File) -> io::Result<Vec<u8>> {
    let mut name = [0_u8; 128];
    // SAFETY: directory is held open; name is writable for its full length.
    let count = unsafe {
        libc::readlinkat(
            directory.as_raw_fd(),
            c"ns/pid".as_ptr(),
            name.as_mut_ptr().cast(),
            name.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error());
    }
    if count == 0 || count as usize == name.len() {
        return Err(invalid("incomplete held PID namespace identity"));
    }
    Ok(name[..count as usize].to_vec())
}

impl RetirementWitness {
    fn capture(pid: u32, parent: u32) -> Self {
        let generation = identity(pid).unwrap();
        assert_eq!(generation.parent, parent);
        let fd = open_pidfd(pid).unwrap();
        let path = format!("/proc/{pid}");
        let directory = fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&path)
            .unwrap();
        held_pid_namespace(&directory).unwrap();
        let held = directory.metadata().unwrap();
        let current = fs::metadata(&path).unwrap();
        assert_eq!((held.dev(), held.ino()), (current.dev(), current.ino()));
        assert_eq!(identity(pid).unwrap(), generation);
        assert!(
            !pidfd_exited(&fd).unwrap(),
            "bind the original live process"
        );
        Self {
            fd,
            directory,
            pid,
            generation,
        }
    }

    fn wait_retired(&self) {
        self.wait_retired_until(Instant::now() + Duration::from_secs(3))
            .unwrap();
    }

    fn wait_retired_until(&self, deadline: Instant) -> io::Result<()> {
        let timed_out = || {
            io::Error::new(
                io::ErrorKind::TimedOut,
                format!(
                    "original PID {} generation {:?} was not reaped before the deadline",
                    self.pid, self.generation
                ),
            )
        };
        loop {
            let now = Instant::now();
            if now >= deadline {
                return Err(timed_out());
            }
            let remaining = deadline.duration_since(now);
            let milliseconds =
                remaining.as_millis() + u128::from(remaining.subsec_nanos() % 1_000_000 != 0);
            let mut event = libc::pollfd {
                fd: self.fd.as_raw_fd(),
                // Do not subscribe to persistent POLLIN: only HUP proves that
                // the actual parent/PID1 has removed this task from its PID.
                events: 0,
                revents: 0,
            };
            // SAFETY: one live pidfd, one writable event, a bounded timeout.
            let result =
                unsafe { libc::poll(&mut event, 1, milliseconds.min(i32::MAX as u128) as i32) };
            if Instant::now() >= deadline {
                return Err(timed_out());
            }
            if result < 0 {
                let error = io::Error::last_os_error();
                if error.kind() != io::ErrorKind::Interrupted {
                    return Err(error);
                }
            } else {
                if event.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
                    return Err(invalid("held retirement pidfd poll failed"));
                }
                if event.revents & libc::POLLHUP != 0 {
                    let retired = match held_pid_namespace(&self.directory) {
                        // proc_pid_permission returns ESRCH when the original
                        // held proc directory no longer has a task. ENOENT from
                        // a fresh numeric PID lookup is not this contract.
                        Err(error) if error.raw_os_error() == Some(libc::ESRCH) => Ok(()),
                        Err(error) => Err(error),
                        Ok(_) => Err(invalid(
                            "reaped original process still retains PID namespace membership",
                        )),
                    };
                    if Instant::now() >= deadline {
                        return Err(timed_out());
                    }
                    return retired;
                }
            }
        }
    }
}

fn descendant_retirement(init: u32) -> RetirementWitness {
    let mut descendants = Vec::new();
    for entry in fs::read_dir(format!("/proc/{init}/task")).unwrap() {
        let entry = entry.unwrap();
        let value = fs::read_to_string(entry.path().join("children")).unwrap();
        descendants.extend(
            value
                .split_ascii_whitespace()
                .map(|p| p.parse::<u32>().unwrap()),
        );
    }
    descendants.sort_unstable();
    descendants.dedup();
    assert_eq!(
        descendants.len(),
        1,
        "fixture has exactly its owned sleep descendant"
    );
    let pid = descendants[0];
    RetirementWitness::capture(pid, init)
}

#[test]
fn pidfd_retirement_requires_reaping_of_original_process() {
    let child = Command::new("/usr/bin/sleep").arg("60").spawn().unwrap();
    let mut fixture = OwnedFixture { child, init: None };
    let original = RetirementWitness::capture(fixture.child.id(), std::process::id());
    fixture.child.kill().unwrap();
    let mut event = libc::pollfd {
        fd: original.fd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: one held pidfd and one writable event; never an unbounded wait.
    assert_eq!(unsafe { libc::poll(&mut event, 1, 3000) }, 1);
    assert_ne!(event.revents & libc::POLLIN, 0);
    assert_eq!(
        event.revents & (libc::POLLHUP | libc::POLLERR | libc::POLLNVAL),
        0
    );
    let mut info: libc::siginfo_t = unsafe { std::mem::zeroed() };
    // Observe this owned child's exit without consuming its wait status.
    // SAFETY: the original pidfd remains held and info is writable.
    assert_eq!(
        unsafe {
            libc::waitid(
                libc::P_PIDFD,
                original.fd.as_raw_fd() as libc::id_t,
                &mut info,
                libc::WEXITED | libc::WNOWAIT | libc::WNOHANG,
            )
        },
        0
    );
    assert_eq!(unsafe { info.si_pid() }, fixture.child.id() as libc::pid_t);
    assert!(
        pidfd_exited(&original.fd).unwrap(),
        "actual POLLIN exit observed"
    );
    assert_eq!(
        original
            .wait_retired_until(Instant::now() + Duration::from_millis(1))
            .unwrap_err()
            .kind(),
        io::ErrorKind::TimedOut,
        "an exited but unreaped task cannot satisfy retirement",
    );
    assert_eq!(fixture.child.wait().unwrap().signal(), Some(libc::SIGKILL));
    original.wait_retired();
}

#[test]
#[ignore = "private entry for the explicitly selected namespace controls"]
fn namespace_init_fixture() {
    assert_eq!(unsafe { libc::getpid() }, 1);
    let directory = PathBuf::from(std::env::var_os("DROIDLOOM_NAMESPACE_TEST_DIR").unwrap());
    let mode = std::env::var("DROIDLOOM_NAMESPACE_TEST_MODE").unwrap();
    // No Android entry function is called. The real parent-death control kills
    // the unshare parent and observes this process and its descendant exit.
    // libtest runs this function on a new thread: PR_GET_PDEATHSIG on that
    // thread would not observe the guard armed on init's original main task.
    let mut action: libc::sigaction = unsafe { std::mem::zeroed() };
    action.sa_sigaction = if mode == "term" {
        term_handler as *const () as usize
    } else {
        libc::SIG_IGN
    };
    assert_eq!(unsafe { libc::sigemptyset(&mut action.sa_mask) }, 0);
    assert_eq!(
        unsafe { libc::sigaction(libc::SIGTERM, &action, std::ptr::null_mut()) },
        0
    );
    let _descendant = Command::new("/usr/bin/sleep").arg("60").spawn().unwrap();
    fs::write(
        directory.join("ready"),
        b"PID1;pre-Android-enter;actual-parent-death-control\n",
    )
    .unwrap();
    loop {
        if TERM.load(Ordering::SeqCst) {
            fs::write(directory.join("term-observed"), b"TERM\n").unwrap();
            std::process::exit(0);
        }
        thread::sleep(Duration::from_millis(5));
    }
}

#[test]
#[ignore = "private entry for the explicitly selected namespace controls"]
fn namespace_launcher_fixture() {
    let directory = PathBuf::from(std::env::var_os("DROIDLOOM_NAMESPACE_TEST_DIR").unwrap());
    let child = namespace_command(&directory, "park").spawn().unwrap();
    let mut owned = OwnedFixture { child, init: None };
    owned.init =
        Some(OwnedNamespaceChild::capture(&mut owned.child, Duration::from_secs(5)).unwrap());
    ready(&directory.join("ready"), &mut owned.child);
    fs::write(
        directory.join("owner-pids"),
        format!(
            "{} {}\n",
            owned.child.id(),
            owned.init.as_ref().unwrap().pid
        ),
    )
    .unwrap();
    loop {
        thread::sleep(Duration::from_secs(1));
    }
}

#[test]
#[ignore = "private entry for the explicitly selected namespace controls"]
fn namespace_preexec_fixture() {
    let directory = PathBuf::from(std::env::var_os("DROIDLOOM_NAMESPACE_TEST_DIR").unwrap());
    let ready_file = fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(directory.join("preexec-pid"))
        .unwrap();
    let fd = ready_file.as_raw_fd();
    let mut command = namespace_command(&directory, "park");
    // The real arm_development_parent_death hook runs first. Stop before exec
    // using only async-signal-safe syscalls, so unshare cannot yet have forked.
    unsafe {
        command.pre_exec(move || {
            let pid = libc::getpid();
            let written = libc::write(
                fd,
                (&pid as *const libc::pid_t).cast(),
                std::mem::size_of::<libc::pid_t>(),
            );
            if written != std::mem::size_of::<libc::pid_t>() as isize {
                return Err(io::Error::last_os_error());
            }
            loop {
                libc::pause();
            }
        });
    }
    let _unexpected = command.spawn().unwrap();
    panic!("pre-exec fixture must not complete spawn");
}

#[test]
#[ignore = "requires root and actual private Linux namespaces; no Android inputs"]
fn actual_namespace_term_and_force_retire_owned_processes() {
    require_root();
    let namespaces = ["mnt", "pid", "cgroup", "ipc", "uts"];
    let before: Vec<_> = namespaces
        .iter()
        .map(|name| fs::read_link(format!("/proc/self/ns/{name}")).unwrap())
        .collect();
    for mode in ["term", "force"] {
        let directory = tempfile::tempdir().unwrap();
        let child = namespace_command(directory.path(), mode).spawn().unwrap();
        let mut fixture = OwnedFixture { child, init: None };
        fixture.init =
            Some(OwnedNamespaceChild::capture(&mut fixture.child, Duration::from_secs(5)).unwrap());
        ready(&directory.path().join("ready"), &mut fixture.child);
        let init = fixture.init.as_ref().unwrap();
        let init_pid = init.pid;
        let owner = RetirementWitness::capture(fixture.child.id(), std::process::id());
        let init_retirement = RetirementWitness::capture(init_pid, fixture.child.id());
        let descendant = descendant_retirement(init_pid);
        for (name, original) in namespaces.iter().zip(&before) {
            assert_ne!(
                fs::read_link(format!("/proc/{init_pid}/ns/{name}")).unwrap(),
                *original,
                "{name} must be private"
            );
        }
        let outer_pid = fixture.child.id();
        let dummy = Command::new("/usr/bin/true").spawn().unwrap();
        let child = std::mem::replace(&mut fixture.child, dummy);
        let mut guard = TestCell(DevelopmentCell::owned_process_for_lifecycle_test(
            unused_spec(directory.path()),
            child,
        ));
        let cell = &mut guard.0;
        cell.namespace_child = fixture.init.take();
        let started = Instant::now();
        cell.stop().unwrap();
        let elapsed = started.elapsed();
        let status = cell.child.wait().unwrap();
        owner.wait_retired();
        init_retirement.wait_retired();
        descendant.wait_retired();
        if mode == "term" {
            assert!(status.success());
            assert!(directory.path().join("term-observed").exists());
            assert!(elapsed < Duration::from_secs(5));
        } else {
            assert_eq!(status.signal(), Some(libc::SIGKILL));
            assert!(!directory.path().join("term-observed").exists());
            assert!(elapsed >= Duration::from_secs(10) && elapsed < Duration::from_secs(13));
        }
        println!(
            "{}",
            serde_json::json!({"control":mode,"outer_pid":outer_pid,"outer_reaped":true,"init_pid":init_pid,"init_exited":true,"descendant_exited":true,"private_namespaces":namespaces,"seconds":elapsed.as_secs_f64(),"android_started":false})
        );
    }
    for (name, original) in namespaces.iter().zip(before) {
        assert_eq!(
            fs::read_link(format!("/proc/self/ns/{name}")).unwrap(),
            original
        );
    }
}

#[test]
#[ignore = "requires root and actual private Linux namespaces; no Android inputs"]
fn actual_daemon_death_after_fork_before_android_enter() {
    require_root();
    let directory = tempfile::tempdir().unwrap();
    let child = fixture_command(LAUNCHER, directory.path(), "park")
        .spawn()
        .unwrap();
    let mut launcher = OwnedFixture { child, init: None };
    ready(&directory.path().join("owner-pids"), &mut launcher.child);
    let pids: Vec<u32> = fs::read_to_string(directory.path().join("owner-pids"))
        .unwrap()
        .split_ascii_whitespace()
        .map(|p| p.parse().unwrap())
        .collect();
    assert_eq!(pids.len(), 2);
    let owner = RetirementWitness::capture(pids[0], launcher.child.id());
    let init = RetirementWitness::capture(pids[1], pids[0]);
    // On a test assertion failure, the guard still kills this exact bound init
    // after reaping our launcher; it never selects any process by name.
    launcher.init = Some(OwnedNamespaceChild {
        fd: init.fd.try_clone().unwrap(),
        pid: pids[1],
    });
    let descendant = descendant_retirement(pids[1]);
    launcher.child.kill().unwrap();
    launcher.child.wait().unwrap();
    owner.wait_retired();
    init.wait_retired();
    descendant.wait_retired();
    println!(
        "{}",
        serde_json::json!({"control":"daemon-death-after-fork-before-enter","launcher_reaped":true,"owner_exited":true,"init_exited":true,"descendant_exited":true,"android_started":false})
    );
}

#[test]
#[ignore = "requires root for the actual namespace command; no Android inputs"]
fn actual_daemon_death_before_unshare_exec_and_fork() {
    require_root();
    let directory = tempfile::tempdir().unwrap();
    let child = fixture_command(EARLY, directory.path(), "park")
        .spawn()
        .unwrap();
    let mut launcher = OwnedFixture { child, init: None };
    let path = directory.path().join("preexec-pid");
    let deadline = Instant::now() + Duration::from_secs(5);
    while !fs::metadata(&path).is_ok_and(|s| s.len() == 4) {
        assert!(launcher.child.try_wait().unwrap().is_none());
        assert!(Instant::now() < deadline);
        thread::sleep(Duration::from_millis(5));
    }
    let bytes: [u8; 4] = fs::read(&path).unwrap().try_into().unwrap();
    let pid = u32::from_ne_bytes(bytes);
    let original = RetirementWitness::capture(pid, launcher.child.id());
    assert_eq!(
        fs::read_link(format!("/proc/{pid}/exe")).unwrap(),
        std::env::current_exe().unwrap()
    );
    assert_eq!(
        fs::read_to_string(format!("/proc/{pid}/task/{pid}/children"))
            .unwrap()
            .trim(),
        ""
    );
    launcher.child.kill().unwrap();
    launcher.child.wait().unwrap();
    original.wait_retired();
    assert!(!directory.path().join("ready").exists());
    println!(
        "{}",
        serde_json::json!({"control":"daemon-death-before-exec-and-fork","launcher_reaped":true,"preexec_child_exited":true,"unshare_exec_observed":false,"namespace_init_created":false,"android_started":false})
    );
}
