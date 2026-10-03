//! Actual privileged files and independent UID/fork processes; no Servo.
use hepta_peer_attestation::{ApprovedPolicyDocument, ApprovedPolicyError};
use std::{
    ffi::CString,
    fs,
    io::Write,
    os::unix::{fs::PermissionsExt, process::CommandExt},
    path::{Path, PathBuf},
    process::Command,
    thread,
    time::{Duration, Instant},
};
const GOLDEN: &[u8] = include_bytes!("../../../contracts/fixtures/approved-mechanisms.v1.conf");
fn uid() -> u32 {
    unsafe { libc::geteuid() }
}
fn inventory() -> Vec<(u32, PathBuf)> {
    let names: Vec<_> = fs::read_dir("/proc/self/fd")
        .unwrap()
        .map(|p| p.unwrap().file_name())
        .collect();
    let mut out: Vec<_> = names
        .into_iter()
        .filter_map(|n| {
            let fd = n.to_str()?.parse().ok()?;
            Some((fd, fs::read_link(format!("/proc/self/fd/{fd}")).ok()?))
        })
        .collect();
    out.sort();
    out
}
fn chown(p: &Path, id: u32) {
    let n = CString::new(p.as_os_str().as_encoded_bytes()).unwrap();
    assert_eq!(unsafe { libc::chown(n.as_ptr(), id, id) }, 0);
}
struct Fixture(PathBuf);
impl Fixture {
    fn new() -> Self {
        let path = PathBuf::from(format!(
            "/var/lib/hepta-approved-policy-kernel-{}",
            std::process::id()
        ));
        fs::create_dir(&path).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755)).unwrap();
        Self(path)
    }
    fn file(&self, name: &str) -> PathBuf {
        let path = self.0.join(name);
        fs::write(&path, GOLDEN).unwrap();
        fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
        path
    }
}
impl Drop for Fixture {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}
fn load(path: &Path) -> Result<ApprovedPolicyDocument, ApprovedPolicyError> {
    ApprovedPolicyDocument::open_root_owned_before(path, Instant::now() + Duration::from_secs(20))
}
fn refused(path: &Path) {
    assert!(load(path).is_err());
}
fn child_nobody(path: &Path) {
    assert_eq!(uid(), 65534);
    let doc = load(path).unwrap();
    doc.select_control().unwrap();
    doc.select_agent().unwrap();
    doc.ensure_current().unwrap();
    println!("NAMESPACE_LOCAL_ROOT_FILE_READ_ONLY");
}
fn root() {
    assert_eq!(uid(), 0, "required explicit kernel profile, never skip");
    let f = Fixture::new();
    let mut groups = 0;
    macro_rules! case {($name:expr,$body:block)=>{{let before=inventory();$body assert_eq!(inventory(),before,"descriptor ownership at case {}",$name);groups+=1;println!("PASS {} actual files/processes; namespace-local source only",$name);}}}
    case!("valid-closed-golden", {
        let p = f.file("valid");
        let d = load(&p).unwrap();
        d.select_control().unwrap();
        d.select_agent().unwrap();
        d.ensure_current().unwrap();
    });
    case!("missing-and-empty", {
        refused(&f.0.join("absent"));
        let p = f.file("empty");
        fs::write(&p, b"").unwrap();
        refused(&p);
    });
    case!("actual-leaf-symlink", {
        let p = f.file("symlink-target");
        let alias = f.0.join("leaf-alias");
        std::os::unix::fs::symlink(&p, &alias).unwrap();
        refused(&alias);
    });
    case!("actual-ancestor-symlink", {
        let p = f.0.join("dir");
        fs::create_dir(&p).unwrap();
        fs::write(p.join("policy"), GOLDEN).unwrap();
        let alias = f.0.join("dir-alias");
        std::os::unix::fs::symlink(&p, &alias).unwrap();
        refused(&alias.join("policy"));
    });
    case!("actual-hardlink", {
        let p = f.file("hardlink-source");
        fs::hard_link(&p, f.0.join("hardlink-other")).unwrap();
        refused(&p);
    });
    case!("actual-fifo-no-block", {
        let p = f.0.join("fifo");
        let name = CString::new(p.as_os_str().as_encoded_bytes()).unwrap();
        assert_eq!(unsafe { libc::mkfifo(name.as_ptr(), 0o644) }, 0);
        let now = Instant::now();
        refused(&p);
        assert!(now.elapsed() < Duration::from_secs(1));
    });
    case!("group-write-and-nonroot-owner", {
        let p = f.file("group-write");
        fs::set_permissions(&p, fs::Permissions::from_mode(0o664)).unwrap();
        refused(&p);
        let p = f.file("foreign-owned");
        chown(&p, 65534);
        refused(&p);
    });
    case!("actual-writable-ancestor", {
        let d = f.0.join("writable");
        fs::create_dir(&d).unwrap();
        fs::set_permissions(&d, fs::Permissions::from_mode(0o777)).unwrap();
        fs::write(d.join("policy"), GOLDEN).unwrap();
        refused(&d.join("policy"));
    });
    case!("observed-mode-restore-never-revives", {
        let p = f.file("mode-drift");
        let d = load(&p).unwrap();
        fs::set_permissions(&p, fs::Permissions::from_mode(0o666)).unwrap();
        assert!(d.ensure_current().is_err());
        fs::set_permissions(&p, fs::Permissions::from_mode(0o644)).unwrap();
        assert_eq!(d.ensure_current(), Err(ApprovedPolicyError::Changed));
    });
    case!("actual-inplace-byte-restore-never-revives", {
        let p = f.file("byte-drift");
        let d = load(&p).unwrap();
        fs::write(
            &p,
            String::from_utf8(GOLDEN.to_vec())
                .unwrap()
                .replace("fixture-agent", "another-agent"),
        )
        .unwrap();
        assert!(d.ensure_current().is_err());
        fs::write(&p, GOLDEN).unwrap();
        assert_eq!(d.ensure_current(), Err(ApprovedPolicyError::Changed));
    });
    case!("actual-identical-leaf-replacement", {
        let p = f.file("replaced");
        let d = load(&p).unwrap();
        let replacement = f.file("replacement");
        fs::rename(&replacement, &p).unwrap();
        assert!(d.ensure_current().is_err());
    });
    case!("actual-ancestor-rename-to-alias", {
        let d = f.0.join("original-dir");
        fs::create_dir(&d).unwrap();
        let p = d.join("policy");
        fs::write(&p, GOLDEN).unwrap();
        let policy = load(&p).unwrap();
        let moved = f.0.join("moved-dir");
        fs::rename(&d, &moved).unwrap();
        std::os::unix::fs::symlink(&moved, &d).unwrap();
        assert!(policy.ensure_current().is_err());
        fs::remove_file(&d).unwrap();
        fs::rename(&moved, &d).unwrap();
        assert_eq!(policy.ensure_current(), Err(ApprovedPolicyError::Changed));
    });
    case!("actual-nobody-read-root-config", {
        let p = f.file("public-read-only");
        let copied = f.0.join("known-source-fixture");
        let bytes = fs::read(std::env::current_exe().unwrap()).unwrap();
        fs::write(&copied, &bytes).unwrap();
        fs::set_permissions(&copied, fs::Permissions::from_mode(0o555)).unwrap();
        assert_eq!(fs::read(&copied).unwrap(), bytes);
        let result = Command::new(&copied)
            .args(["--nobody"])
            .arg(&p)
            .uid(65534)
            .gid(65534)
            .output()
            .unwrap();
        assert!(
            result.status.success(),
            "{}",
            String::from_utf8_lossy(&result.stderr)
        );
        assert_eq!(result.stdout, b"NAMESPACE_LOCAL_ROOT_FILE_READ_ONLY\n");
    });
    case!("original-fork-guards-and-parent-fds", {
        let p = f.file("fork");
        let policy = load(&p).unwrap();
        let fork = unsafe { libc::fork() };
        assert!(fork >= 0);
        if fork == 0 {
            let correct = policy.ensure_current() == Err(ApprovedPolicyError::ProcessChanged);
            drop(policy);
            unsafe { libc::_exit(if correct { 0 } else { 2 }) }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(fork, &mut status, 0) }, fork);
        assert!(libc::WIFEXITED(status) && libc::WEXITSTATUS(status) == 0);
        policy.ensure_current().unwrap();
    });
    case!("single-absolute-expiry", {
        let p = f.file("expires");
        let deadline = Instant::now() + Duration::from_millis(500);
        let policy = ApprovedPolicyDocument::open_root_owned_before(&p, deadline).unwrap();
        thread::sleep(
            deadline.saturating_duration_since(Instant::now()) + Duration::from_millis(10),
        );
        assert_eq!(
            policy.ensure_current(),
            Err(ApprovedPolicyError::DeadlineExceeded)
        );
        assert!(
            ApprovedPolicyDocument::open_root_owned_before(
                &p,
                Instant::now() + Duration::from_secs(21)
            )
            .is_err()
        );
    });
    case!("actual-mount-namespace-change-and-restore", {
        let p = f.file("namespace-change");
        let pid = unsafe { libc::fork() };
        assert!(pid >= 0);
        if pid == 0 {
            use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
            let old = unsafe {
                libc::open(
                    c"/proc/self/ns/mnt".as_ptr(),
                    libc::O_RDONLY | libc::O_CLOEXEC,
                )
            };
            assert!(old >= 0);
            let old = unsafe { OwnedFd::from_raw_fd(old) };
            // New child-local loaded source first; namespace guard is distinct
            // from the inherited creatorPID refusal covered above.
            let doc = load(&p).unwrap();
            assert_eq!(
                unsafe { libc::unshare(libc::CLONE_NEWNS) },
                0,
                "actual mount namespace capability required"
            );
            assert_eq!(doc.ensure_current(), Err(ApprovedPolicyError::Changed));
            assert_eq!(
                unsafe { libc::setns(old.as_raw_fd(), libc::CLONE_NEWNS) },
                0
            );
            assert_eq!(
                doc.ensure_current(),
                Err(ApprovedPolicyError::Changed),
                "namespace restoration cannot revive source"
            );
            drop(doc);
            drop(old);
            unsafe { libc::_exit(0) }
        }
        let mut status = 0;
        assert_eq!(unsafe { libc::waitpid(pid, &mut status, 0) }, pid);
        assert_eq!(status, 0);
    });
    case!("actual-worker-mount-namespace-guard", {
        let p = f.file("thread-namespace-change");
        let doc = std::sync::Arc::new(load(&p).unwrap());
        let other = std::sync::Arc::clone(&doc);
        thread::spawn(move || {
            assert_eq!(
                unsafe { libc::unshare(libc::CLONE_NEWNS) },
                0,
                "actual worker thread mount namespace capability"
            );
            assert_eq!(other.ensure_current(), Err(ApprovedPolicyError::Changed));
        })
        .join()
        .unwrap();
        assert_eq!(
            doc.ensure_current(),
            Err(ApprovedPolicyError::Changed),
            "one source retirement shared with original process leader"
        );
    });
    assert_eq!(groups, 17);
    println!(
        "17 actual privileged approved-source case groups; no host-root/installed/Servo claim"
    );
}
fn main() {
    let a: Vec<_> = std::env::args_os().collect();
    if a.get(1).is_some_and(|v| v == "--nobody") {
        child_nobody(Path::new(&a[2]));
        return;
    }
    if a.get(1).is_some_and(|v| v == "--root") {
        root();
        return;
    }
    let exe = std::env::current_exe().unwrap();
    let result = Command::new("/usr/bin/sudo")
        .args(["--non-interactive", "--"])
        .arg(&exe)
        .arg("--root")
        .output()
        .expect("actual root fixture required");
    std::io::stdout().write_all(&result.stdout).unwrap();
    std::io::stderr().write_all(&result.stderr).unwrap();
    assert!(result.status.success(), "no missing-capability skip");
}
