//! Real root files/default-proc/self pidfd; FOUNDATION continuity, not health.
//! All forks are from this single-thread harness. No proc mount or fake attestor.
use hepta_peer_attestation::{ApprovedPolicyError, ApprovedServicePolicyDocument};
use sha2::{Digest, Sha256};
use std::{
    ffi::CString,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::fd::AsRawFd,
    os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    process::Command,
    time::{Duration, Instant},
};

const GROUPS: usize = 12;
const CONTINUITY: Duration = Duration::from_secs(61);

fn unavailable(name: &str) -> ! {
    eprintln!("UNAVAILABLE {name}; actual kernel corpus NOT PASSED");
    std::process::exit(77)
}
fn descriptors() -> Vec<(u32, PathBuf)> {
    let names: Vec<_> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|entry| entry.unwrap().file_name())
        .collect();
    let mut values: Vec<_> = names
        .into_iter()
        .filter_map(|name| {
            let fd = name.to_str()?.parse().ok()?;
            Some((fd, fs::read_link(format!("/proc/self/fd/{fd}")).ok()?))
        })
        .collect();
    values.sort();
    values
}
fn wait(pid: libc::pid_t) {
    let mut status = 0;
    assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
    if libc::WIFEXITED(status) && libc::WEXITSTATUS(status) == 77 {
        unavailable("child namespace capability");
    }
    assert_eq!(status, 0, "specific child completed successfully");
}
fn fork() -> libc::pid_t {
    let pid = unsafe { libc::fork() };
    assert!(pid >= 0);
    pid
}
fn metadata(path: &Path) -> (u64, u64, u32, u64, i64, i64, i64, i64) {
    let value = fs::metadata(path).unwrap();
    (
        value.dev(),
        value.ino(),
        value.mode(),
        value.size(),
        value.mtime(),
        value.mtime_nsec(),
        value.ctime(),
        value.ctime_nsec(),
    )
}
fn namespace(name: &str) -> (u64, u64) {
    let value = fs::metadata(format!("/proc/thread-self/ns/{name}")).unwrap();
    (value.dev(), value.ino())
}
struct Fixture {
    directory: PathBuf,
    golden: Vec<u8>,
}
impl Fixture {
    fn file(&self, name: &str) -> PathBuf {
        let path = self.directory.join(name);
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&path)
            .unwrap();
        file.write_all(&self.golden).unwrap();
        file.sync_all().unwrap();
        path
    }
}
fn load(path: &Path) -> ApprovedServicePolicyDocument {
    ApprovedServicePolicyDocument::open_root_owned(path).unwrap()
}
fn refuse(path: &Path) {
    assert!(ApprovedServicePolicyDocument::open_root_owned(path).is_err());
}

fn root_corpus(policy: &Path) {
    assert_eq!(
        unsafe { libc::geteuid() },
        0,
        "root static mechanism fixture required"
    );
    let before_policy = metadata(policy);
    let golden = fs::read(policy).unwrap();
    assert_eq!(golden.split(|byte| *byte == b'\n').count() - 1, 19);
    let f = Fixture {
        directory: policy.parent().unwrap().to_owned(),
        golden,
    };
    let mut groups = 0;
    macro_rules! case {
        ($name:expr, $body:block) => {{
            let before = descriptors();
            $body
            assert_eq!(descriptors(), before, "exact FD inventory after {}", $name);
            groups += 1;
            println!("PASS {} FOUNDATION kernel group; no request/native/health authority", $name);
        }};
    }
    case!("fixed-root-selected-live-default-proc-owner", {
        let document = load(policy);
        let owner = document.select_current_owner().unwrap();
        document.ensure_current().unwrap();
        owner.ensure_current().unwrap();
        owner.verifier().unwrap().ensure_current().unwrap();
    });
    case!("source-continuity-greater-than-sixty-seconds", {
        let document = load(policy);
        let owner = document.select_current_owner().unwrap();
        let first = owner.verifier().unwrap();
        let second = owner.verifier().unwrap();
        let start = Instant::now();
        while start.elapsed() < CONTINUITY {
            document.ensure_current().unwrap();
            owner.ensure_current().unwrap();
            first.ensure_current().unwrap();
            second.ensure_current().unwrap();
            std::thread::sleep(Duration::from_millis(100));
        }
        assert!(start.elapsed() >= CONTINUITY);
        first.ensure_current().unwrap();
        second.ensure_current().unwrap();
        println!(
            "SOURCE_CONTINUITY elapsed_ns={} NativeHealth=false",
            start.elapsed().as_nanos()
        );
    });
    case!("drop-binding-revokes-all-issued-verifiers", {
        let document = load(policy);
        let owner = document.select_current_owner().unwrap();
        let first = owner.verifier().unwrap();
        let second = owner.verifier().unwrap();
        drop(owner);
        assert_eq!(
            first.ensure_current(),
            Err(ApprovedPolicyError::PeerRefused)
        );
        assert!(second.ensure_current().is_err());
        assert_eq!(first.ensure_current(), Err(ApprovedPolicyError::Changed));
    });
    case!("drop-document-and-verifier-retains-original-owner", {
        let document = load(policy);
        let owner = document.select_current_owner().unwrap();
        let verifier = owner.verifier().unwrap();
        drop(document);
        verifier.ensure_current().unwrap();
        drop(verifier);
        owner.ensure_current().unwrap();
        let verifier = owner.verifier().unwrap();
        drop(owner);
        assert!(verifier.ensure_current().is_err());
    });
    case!("one-selection-per-source-not-global-singleton", {
        let document = load(policy);
        let owner = document.select_current_owner().unwrap();
        assert!(matches!(
            document.select_current_owner(),
            Err(ApprovedPolicyError::PeerRefused)
        ));
        owner.ensure_current().unwrap();
        drop(owner);
        assert!(matches!(
            document.select_current_owner(),
            Err(ApprovedPolicyError::PeerRefused)
        ));
        let separate = load(policy);
        separate
            .select_current_owner()
            .unwrap()
            .ensure_current()
            .unwrap();
    });
    case!("ordinary-fork-creator-first-parent-preserved", {
        let document = load(policy);
        let owner = document.select_current_owner().unwrap();
        let verifier = owner.verifier().unwrap();
        let child = fork();
        if child == 0 {
            assert_eq!(
                document.ensure_current(),
                Err(ApprovedPolicyError::ProcessChanged)
            );
            assert_eq!(
                owner.ensure_current(),
                Err(ApprovedPolicyError::ProcessChanged)
            );
            assert_eq!(
                verifier.ensure_current(),
                Err(ApprovedPolicyError::ProcessChanged)
            );
            unsafe { libc::_exit(0) }
        }
        wait(child);
        owner.ensure_current().unwrap();
        verifier.ensure_current().unwrap();
    });
    case!(
        "nested-pid-one-actual-document-refuses-numeric-collision",
        {
            let controller = fork();
            if controller == 0 {
                if unsafe { libc::unshare(libc::CLONE_NEWPID) } != 0 {
                    unavailable("CLONE_NEWPID outer");
                }
                let outer = fork();
                if outer == 0 {
                    assert_eq!(std::process::id(), 1);
                    let old = [namespace("user"), namespace("mnt"), namespace("time")];
                    let original_pid_namespace = namespace("pid");
                    let document = load(policy);
                    // Do not select a default-proc Owner inside an unmounted PID
                    // namespace: host /proc numeric lookup is intentionally not
                    // promoted into a false successful identity observation.
                    if unsafe { libc::unshare(libc::CLONE_NEWPID) } != 0 {
                        unavailable("CLONE_NEWPID inner");
                    }
                    let inner = fork();
                    if inner == 0 {
                        assert_eq!(std::process::id(), 1);
                        assert_eq!(
                            [namespace("user"), namespace("mnt"), namespace("time")],
                            old
                        );
                        assert_ne!(namespace("pid"), original_pid_namespace);
                        assert_eq!(
                            document.ensure_current(),
                            Err(ApprovedPolicyError::ProcessChanged)
                        );
                        assert_eq!(
                            document.ensure_current(),
                            Err(ApprovedPolicyError::ProcessChanged)
                        );
                        println!("NESTED_PID_1 actual_Doc=ProcessChanged new_proc_mount=false");
                        std::io::stdout().flush().unwrap();
                        unsafe { libc::_exit(0) }
                    }
                    wait(inner);
                    document.ensure_current().unwrap();
                    unsafe { libc::_exit(0) }
                }
                wait(outer);
                unsafe { libc::_exit(0) }
            }
            wait(controller);
        }
    );
    case!("wrong-static-owner-fields-refuse-and-retire", {
        let source = String::from_utf8(f.golden.clone()).unwrap();
        for (index, key) in ["uid", "gid", "unit", "cgroup", "elf_sha256"]
            .iter()
            .enumerate()
        {
            let prefix = format!("owner.{key}=");
            let original = source
                .lines()
                .find(|line| line.starts_with(&prefix))
                .unwrap();
            let wrong = match *key {
                "uid" | "gid" => "1".to_owned(),
                "unit" => "hepta-wrong-owner.service".to_owned(),
                "cgroup" => format!(
                    "/different.slice/{}",
                    original
                        .trim_start_matches(&prefix)
                        .rsplit('/')
                        .next()
                        .unwrap()
                ),
                "elf_sha256" => "0".repeat(64),
                _ => unreachable!(),
            };
            let path = f.file(&format!("wrong-owner-{index}"));
            let changed = source.replace(original, &format!("{prefix}{wrong}"));
            // Wrong unit needs matching cgroup syntax so runtime identity,
            // rather than the parser, actually refuses this root profile.
            let changed = if *key == "unit" {
                let group = source
                    .lines()
                    .find(|line| line.starts_with("owner.cgroup="))
                    .unwrap();
                changed.replace(
                    group,
                    "owner.cgroup=/system.slice/hepta-wrong-owner.service",
                )
            } else {
                changed
            };
            fs::write(&path, changed).unwrap();
            let document = load(&path);
            assert!(matches!(
                document.select_current_owner(),
                Err(ApprovedPolicyError::PeerRefused)
            ));
            assert_eq!(document.ensure_current(), Err(ApprovedPolicyError::Changed));
            fs::write(&path, &f.golden).unwrap();
            assert_eq!(document.ensure_current(), Err(ApprovedPolicyError::Changed));
        }
    });
    case!("strict-nineteen-fields-and-root-leaf-negatives", {
        let source = String::from_utf8(f.golden.clone()).unwrap();
        for (index, bytes) in [
            Vec::new(),
            vec![0xff],
            vec![b'x'; 8193],
            source.replace('\n', "\r\n").into_bytes(),
            source.as_bytes()[..source.len() - 1].to_vec(),
            format!("{source}owner.callers_preapproved=true\n").into_bytes(),
            source
                .replace(
                    "trillionnium.approved-mechanisms.v2",
                    "trillionnium.approved-mechanisms.v1",
                )
                .into_bytes(),
        ]
        .iter()
        .enumerate()
        {
            let path = f.file(&format!("bad-source-bytes-{index}"));
            fs::write(&path, bytes).unwrap();
            refuse(&path);
        }
        for (index, line) in source.lines().enumerate() {
            for (variant, bytes) in [
                source.replace(&format!("{line}\n"), ""),
                format!("{source}{line}\n"),
            ]
            .iter()
            .enumerate()
            {
                let path = f.file(&format!("bad-fields-{index}-{variant}"));
                fs::write(&path, bytes).unwrap();
                refuse(&path);
            }
        }
        let alias = f.directory.join("leaf-alias");
        std::os::unix::fs::symlink(policy, &alias).unwrap();
        refuse(&alias);
        let linked = f.file("linked");
        fs::hard_link(&linked, f.directory.join("other-link")).unwrap();
        refuse(&linked);
        let fifo = f.directory.join("fifo");
        let name = CString::new(fifo.as_os_str().as_encoded_bytes()).unwrap();
        assert_eq!(unsafe { libc::mkfifo(name.as_ptr(), 0o600) }, 0);
        let start = Instant::now();
        refuse(&fifo);
        assert!(start.elapsed() < Duration::from_secs(1));
        let writable = f.file("writable");
        fs::set_permissions(&writable, fs::Permissions::from_mode(0o666)).unwrap();
        refuse(&writable);
    });
    case!("named-leaf-and-root-ancestor-drift-stay-retired", {
        let path = f.file("leaf-replacement");
        let document = load(&path);
        let saved = f.directory.join("leaf-saved");
        fs::rename(&path, &saved).unwrap();
        fs::write(&path, &f.golden).unwrap();
        assert!(document.ensure_current().is_err());
        fs::remove_file(&path).unwrap();
        fs::rename(&saved, &path).unwrap();
        assert_eq!(document.ensure_current(), Err(ApprovedPolicyError::Changed));
        let path = f.file("mode-restoration");
        let document = load(&path);
        fs::set_permissions(&path, fs::Permissions::from_mode(0o666)).unwrap();
        assert!(document.ensure_current().is_err());
        fs::set_permissions(&path, fs::Permissions::from_mode(0o600)).unwrap();
        assert_eq!(document.ensure_current(), Err(ApprovedPolicyError::Changed));
        let path = f.file("same-inode-rewrite");
        let document = load(&path);
        let changed = String::from_utf8(f.golden.clone())
            .unwrap()
            .replace("fixture-owner", "changed-owner");
        assert_ne!(changed.as_bytes(), f.golden);
        fs::write(&path, changed).unwrap();
        assert!(document.ensure_current().is_err());
        fs::write(&path, &f.golden).unwrap();
        assert_eq!(document.ensure_current(), Err(ApprovedPolicyError::Changed));
    });
    case!("ancestor-path-and-foreign-owner-source-refuse", {
        let dir = f.directory.join("ancestor");
        fs::create_dir(&dir).unwrap();
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        let path = dir.join("policy");
        fs::write(&path, &f.golden).unwrap();
        let document = load(&path);
        let saved = f.directory.join("ancestor-saved");
        fs::rename(&dir, &saved).unwrap();
        fs::create_dir(&dir).unwrap();
        fs::write(&path, &f.golden).unwrap();
        assert!(document.ensure_current().is_err());
        fs::remove_dir_all(&dir).unwrap();
        fs::rename(&saved, &dir).unwrap();
        assert_eq!(document.ensure_current(), Err(ApprovedPolicyError::Changed));
        let alias = f.directory.join("ancestor-alias");
        std::os::unix::fs::symlink(&dir, &alias).unwrap();
        refuse(&alias.join("policy"));
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o777)).unwrap();
        refuse(&path);
        fs::set_permissions(&dir, fs::Permissions::from_mode(0o700)).unwrap();
        let foreign = f.file("foreign-root-file");
        let name = CString::new(foreign.as_os_str().as_encoded_bytes()).unwrap();
        assert_eq!(unsafe { libc::chown(name.as_ptr(), 65534, 65534) }, 0);
        refuse(&foreign);
    });
    case!("mount-namespace-change-return-cannot-revive-source", {
        let child = fork();
        if child == 0 {
            let document = load(policy);
            let original = File::open("/proc/thread-self/ns/mnt").unwrap();
            if unsafe { libc::unshare(libc::CLONE_NEWNS) } != 0 {
                unavailable("CLONE_NEWNS");
            }
            assert_eq!(document.ensure_current(), Err(ApprovedPolicyError::Changed));
            assert_eq!(
                unsafe { libc::setns(original.as_raw_fd(), libc::CLONE_NEWNS) },
                0
            );
            assert_eq!(document.ensure_current(), Err(ApprovedPolicyError::Changed));
            unsafe { libc::_exit(0) }
        }
        wait(child);
    });
    assert_eq!(groups, GROUPS);
    assert_eq!(
        metadata(policy),
        before_policy,
        "original nineteen-field root input stays exact"
    );
    println!(
        "12 actual FOUNDATION kernel groups; NativeHealth=false installed=false production_ready=false"
    );
}

fn prepare() -> i32 {
    assert_eq!(unsafe { libc::geteuid() }, 0);
    let before = descriptors();
    let source = std::env::current_exe().unwrap();
    let initial = metadata(&source);
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&source)
        .unwrap();
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(256 * 1024 * 1024 + 1)
        .read_to_end(&mut bytes)
        .unwrap();
    assert!(!bytes.is_empty() && bytes.len() <= 256 * 1024 * 1024);
    assert_eq!(metadata(&source), initial);
    let digest = format!("{:x}", Sha256::digest(&bytes));
    let directory = PathBuf::from(format!(
        "/var/lib/hepta-service-owner-v2-kernel-{}",
        std::process::id()
    ));
    fs::create_dir(&directory).unwrap();
    fs::set_permissions(&directory, fs::Permissions::from_mode(0o700)).unwrap();
    let binary = directory.join("source-kernel");
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o500)
        .open(&binary)
        .unwrap();
    output.write_all(&bytes).unwrap();
    output.sync_all().unwrap();
    drop(output);
    assert_eq!(fs::read(&binary).unwrap(), bytes);
    let binary_identity = metadata(&binary);
    assert_eq!(fs::metadata(&binary).unwrap().uid(), 0);
    assert_eq!(fs::metadata(&binary).unwrap().nlink(), 1);
    assert_eq!(fs::metadata(&binary).unwrap().mode() & 0o777, 0o500);
    let unit = format!(
        "hepta-service-owner-v2-kernel-{}.service",
        std::process::id()
    );
    let mut policy = String::from("schema=trillionnium.approved-mechanisms.v2\n");
    for role in ["control", "agent", "owner"] {
        let role_unit = if role == "owner" {
            unit.clone()
        } else {
            format!("hepta-unconsumed-{role}-fixture.service")
        };
        let pin = if role == "owner" {
            digest.clone()
        } else {
            "0".repeat(64)
        };
        policy.push_str(&format!("{role}.uid=0\n{role}.gid=0\n{role}.unit={role_unit}\n{role}.cgroup=/system.slice/{role_unit}\n{role}.elf_sha256={pin}\n{role}.principal_id=fixture-{role}\n"));
    }
    let policy_path = directory.join("approved-mechanisms.v2.conf");
    let mut policy_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(&policy_path)
        .unwrap();
    policy_file.write_all(policy.as_bytes()).unwrap();
    policy_file.sync_all().unwrap();
    drop(policy_file);
    println!("ROOT_STATIC_PROFILE unit={unit} binary_sha256={digest} ControlAgentConsumed=false");
    let result = Command::new("/usr/bin/systemd-run")
        .args([
            "--quiet",
            "--wait",
            "--pipe",
            "--property=Type=oneshot",
            "--property=User=0",
            "--property=Group=0",
            "--property=RuntimeMaxSec=90",
            "--property=TimeoutStartSec=90",
        ])
        .arg(format!("--unit={unit}"))
        .arg(&binary)
        .arg("--policy")
        .arg(&policy_path)
        .output()
        .unwrap();
    std::io::stdout().write_all(&result.stdout).unwrap();
    std::io::stderr().write_all(&result.stderr).unwrap();
    assert_eq!(
        fs::read(&binary).unwrap(),
        bytes,
        "root-selected ELF full readback"
    );
    assert_eq!(
        metadata(&binary),
        binary_identity,
        "same root selected ELF inode/mode/metadata"
    );
    assert_eq!(fs::read(&policy_path).unwrap(), policy.as_bytes());
    drop(file);
    fs::remove_dir_all(&directory).unwrap();
    assert!(
        !directory.exists(),
        "root fixture directory removed after unit completion"
    );
    assert_eq!(descriptors(), before, "root preparation FD cleanup");
    result.status.code().unwrap_or(1)
}

fn main() {
    let arguments: Vec<_> = std::env::args_os().collect();
    if arguments.len() == 3 && arguments[1] == "--policy" {
        root_corpus(Path::new(&arguments[2]));
    } else if arguments.len() == 2 && arguments[1] == "--prepare" {
        std::process::exit(prepare());
    } else if arguments.len() == 1 {
        let result = Command::new("/usr/bin/sudo")
            .args(["--non-interactive", "--"])
            .arg(std::env::current_exe().unwrap())
            .arg("--prepare")
            .output()
            .unwrap();
        std::io::stdout().write_all(&result.stdout).unwrap();
        std::io::stderr().write_all(&result.stderr).unwrap();
        std::process::exit(result.status.code().unwrap_or(1));
    } else {
        eprintln!("INVALID source kernel profile arguments");
        std::process::exit(2);
    }
}
