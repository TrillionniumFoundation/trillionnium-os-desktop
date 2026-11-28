use crate::{
    Result,
    boot_child::OwnedChild,
    boot_files::{self, FilePin},
    ensure, fs,
};
use rustix::{
    fs::{FileType, Mode, OFlags},
    io::FdFlags,
};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs::File,
    os::{
        fd::{AsFd, AsRawFd, BorrowedFd},
        unix::{fs::MetadataExt, net::UnixListener, process::CommandExt},
    },
    path::{Path, PathBuf},
    process::{Command, Stdio},
};

const SETPRIV: &str = "/usr/bin/setpriv";
pub const SANDBOX: &str = "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny";

/// All privileged opens happen in the root-owned runner. QEMU receives only
/// these particular objects; the original prepared disk is never inherited.
pub struct Launch {
    pub qemu: FilePin,
    pub receipt: Value,
    executable: File,
    executable_identity: crate::model::Identity,
    kvm: File,
    disk_read: File,
    disk_write: File,
    kernel: File,
    initrd: File,
    monitor: UnixListener,
    setpriv: File,
    setpriv_executable: File,
    setpriv_pin: FilePin,
}

fn open(path: &Path, flags: OFlags) -> Result<File> {
    let (parent, name) = fs::absolute_parent(&fs::absolute_string(path)?)?;
    Ok(File::from(rustix::fs::openat(
        &parent,
        name.as_str(),
        flags | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?))
}

fn tool(path: &Path) -> Result<(FilePin, File)> {
    let pin = boot_files::pin_file(path)?;
    let file = boot_files::checked_file(&pin)?;
    let id = fs::stat(&file)?;
    ensure(
        id.uid == 0
            && id.gid == 0
            && id.nlink == 1
            && id.mode & 0o6022 == 0
            && id.mode & 0o111 != 0
            && !fs::xattrs(&file)?.contains_key("security.capability"),
        "VM launcher tool is not an ordinary protected root executable",
    )?;
    Ok((pin, file))
}

fn public_bytes(pin: &FilePin, path: &Path) -> Result<(FilePin, File)> {
    // The directory remains root:root 0700. Only a held read descriptor is
    // inherited. Mode 0444 permits QEMU's plain-open kernel loaders to reopen
    // their own /proc/self/fd leaf without granting a writable description.
    boot_files::copy_pin(pin, path, 0o444)?;
    let result = boot_files::pin_file(path)?;
    Ok((result.clone(), boot_files::checked_file(&result)?))
}

impl Launch {
    pub fn prepare(
        run: &Path,
        disk: &Path,
        kernel: &FilePin,
        initrd: &FilePin,
        monitor: &Path,
    ) -> Result<Self> {
        let tree = fs::Tree::open(&fs::absolute_string(run)?, 0)?;
        ensure(
            fs::stat(&tree.root)?.mode & 0o777 == 0o700,
            "VM run directory must remain private",
        )?;
        let (qemu, original_qemu) = tool(Path::new("/usr/bin/qemu-system-x86_64"))?;
        let (setpriv_pin, setpriv) = tool(Path::new(SETPRIV))?;
        let setpriv_path = run.join("setpriv-original");
        boot_files::copy_pin(&setpriv_pin, &setpriv_path, 0o511)?;
        let private_setpriv_pin = boot_files::pin_file(&setpriv_path)?;
        ensure(
            private_setpriv_pin.sha256 == setpriv_pin.sha256
                && private_setpriv_pin.bytes == setpriv_pin.bytes,
            "private privilege helper differs from its installed bytes",
        )?;
        let setpriv_executable = open(&setpriv_path, OFlags::PATH)?;
        let executable_path = run.join("qemu-original");
        // Execute-only access for the final unprivileged credentials makes
        // Linux's would_dump check preserve non-dumpability across exec.
        // The installed binary and every input ancestor retain their modes.
        boot_files::copy_pin(&qemu, &executable_path, 0o511)?;
        let executable_pin = boot_files::pin_file(&executable_path)?;
        ensure(
            executable_pin.sha256 == qemu.sha256 && executable_pin.bytes == qemu.bytes,
            "private QEMU is not the exact installed executable",
        )?;
        ensure(
            fs::hash(&original_qemu)? == qemu.sha256,
            "installed QEMU changed during private copy",
        )?;
        let executable = open(&executable_path, OFlags::PATH)?;
        let executable_identity = fs::stat(&executable)?;
        ensure(
            executable_identity.uid == 0
                && executable_identity.gid == 0
                && executable_identity.nlink == 1
                && executable_identity.mode & 0o7777 == 0o511,
            "private QEMU execution metadata differs",
        )?;
        let (kernel_pin, kernel) = public_bytes(kernel, &run.join("kernel-readonly"))?;
        let (initrd_pin, initrd) = public_bytes(initrd, &run.join("initrd-readonly"))?;
        let kvm = open(Path::new("/dev/kvm"), OFlags::RDWR)?;
        let kvm_identity = fs::stat(&kvm)?;
        ensure(
            FileType::from_raw_mode(kvm_identity.mode) == FileType::CharacterDevice
                && kvm_identity.uid == 0
                && kvm_identity.mode & 0o002 == 0,
            "KVM is not the protected host character device",
        )?;
        let disk_read = open(disk, OFlags::RDONLY)?;
        let disk_write = open(disk, OFlags::RDWR)?;
        let disk_identity = fs::stat(&disk_write)?;
        ensure(
            fs::stat(&disk_read)? == disk_identity
                && FileType::from_raw_mode(disk_identity.mode) == FileType::RegularFile
                && disk_identity.uid == 0
                && disk_identity.gid == 0
                && disk_identity.nlink == 1
                && disk_identity.mode & 0o7777 == 0o600,
            "working disk descriptors do not refer to the private clone",
        )?;
        let monitor = UnixListener::bind(monitor)?;
        let receipt = json!({
            "schema":"droidloom.qemu-fixed-descriptor-launch.v1",
            "qemu_source":qemu,"private_qemu":executable_pin,
            "private_qemu_identity":executable_identity,
            "privilege_tool":setpriv_pin,"private_privilege_tool":private_setpriv_pin,
            "kernel_readonly":kernel_pin,"initrd_readonly":initrd_pin,
            "working_disk_identity":disk_identity,"kvm_identity":kvm_identity,
            "uid":65534,"gid":65534,"supplementary_groups":[],
            "capabilities":"effective, permitted, inheritable and ambient sets empty",
            "bounding_set":"retained capability limit; no-new-privileges prevents acquisition",
            "no_new_privileges":true,"sandbox":SANDBOX,
            "original_prepared_disk_inherited":false,
            "guest_qualified":false,"production_ready":false
        });
        Ok(Self {
            qemu,
            receipt,
            executable,
            executable_identity,
            kvm,
            disk_read,
            disk_write,
            kernel,
            initrd,
            monitor,
            setpriv,
            setpriv_executable,
            setpriv_pin,
        })
    }

    pub fn fixed_args(&self) -> Vec<String> {
        vec![
            "-accel".into(),
            "kvm,device=/dev/fdset/1".into(),
            "-add-fd".into(),
            format!("fd={},set=1", self.kvm.as_raw_fd()),
            // QEMU probes a raw image read-only before opening its writable
            // node. The same fdset therefore contains both access modes.
            "-add-fd".into(),
            format!("fd={},set=2", self.disk_read.as_raw_fd()),
            "-add-fd".into(),
            format!("fd={},set=2", self.disk_write.as_raw_fd()),
            "-chardev".into(),
            format!(
                "socket,id=control,fd={},server=on,wait=off",
                self.monitor.as_raw_fd()
            ),
            "-mon".into(),
            "chardev=control,mode=control".into(),
            "-sandbox".into(),
            SANDBOX.into(),
        ]
    }

    pub fn kernel_path(&self) -> String {
        format!("/proc/self/fd/{}", self.kernel.as_raw_fd())
    }
    pub fn initrd_path(&self) -> String {
        format!("/proc/self/fd/{}", self.initrd.as_raw_fd())
    }

    pub fn spawn(&self, args: &[String], output: &File) -> Result<OwnedChild> {
        ensure(
            fs::hash(&self.setpriv)? == self.setpriv_pin.sha256
                && boot_files::pin_file(Path::new(SETPRIV))?.sha256 == self.setpriv_pin.sha256,
            "privilege tool changed before execution",
        )?;
        let descriptors = [
            self.executable.as_fd(),
            self.kvm.as_fd(),
            self.disk_read.as_fd(),
            self.disk_write.as_fd(),
            self.kernel.as_fd(),
            self.initrd.as_fd(),
            self.monitor.as_fd(),
            self.setpriv_executable.as_fd(),
        ];
        reject_unexpected_inheritance()?;
        // std::process applies gid, clears supplementary groups and then uid
        // before exec. Its ordinary setuid transition clears active privilege.
        // Both following exact-byte ELF copies are unreadable to uid 65534,
        // so neither exec creates an intervening dumpable same-UID process.
        let mut command = Command::new(format!(
            "/proc/self/fd/{}",
            self.setpriv_executable.as_raw_fd()
        ));
        command
            .gid(65534)
            .uid(65534)
            .args([
                "--no-new-privs",
                "--inh-caps=-all",
                "--ambient-caps=-all",
                "--pdeathsig=KILL",
            ])
            .arg(format!("/proc/self/fd/{}", self.executable.as_raw_fd()))
            .args(args)
            .current_dir("/")
            .env_clear()
            .env("PATH", "/usr/sbin:/usr/bin:/sbin:/bin")
            .env("LC_ALL", "C.UTF-8")
            .stdin(Stdio::null())
            .stdout(Stdio::from(output.try_clone()?))
            .stderr(Stdio::from(output.try_clone()?));
        let mut inheritance = Inheritance::new(&descriptors)?;
        let child = OwnedChild::spawn(&mut command);
        let restored = inheritance.restore();
        // An error after successful spawn drops the owned child and reaps it.
        let child = child?;
        restored?;
        Ok(child)
    }

    pub fn admit_process(&self, pid: u32) -> Result<Value> {
        let proc = PathBuf::from(format!("/proc/{pid}"));
        let status = std::fs::read_to_string(proc.join("status"))?;
        let fields = admit_status(&status)?;
        // The top-level /proc/PID directory deliberately retains euid ownership.
        // A regular proc leaf reflects dumpability; the actual same-UID probe
        // also verifies /proc/PID/exe is inaccessible after this fixed exec.
        let process = std::fs::metadata(proc.join("status"))?;
        ensure(
            process.uid() == 0 && process.gid() == 0,
            "unprivileged QEMU became dumpable across exec",
        )?;
        let executable = std::fs::metadata(proc.join("exe"))?;
        ensure(
            executable.dev() == self.executable_identity.dev
                && executable.ino() == self.executable_identity.ino
                && executable.uid() == 0
                && executable.gid() == 0
                && executable.mode() & 0o7777 == 0o511,
            "live QEMU does not execute the held original-byte private inode",
        )?;
        Ok(json!({
            "process_status":fields,"live_executable_device":executable.dev(),
            "live_executable_inode":executable.ino(),
            "proc_status_owner_for_non_dumpable_exec":[process.uid(),process.gid()],
            "guest_qualified":false
        }))
    }
}

fn admit_status(status: &str) -> Result<BTreeMap<String, String>> {
    let fields: BTreeMap<String, String> = status
        .lines()
        .filter_map(|line| line.split_once(':'))
        .map(|(k, v)| (k.to_owned(), v.trim().to_owned()))
        .collect();
    for key in ["Uid", "Gid"] {
        ensure(
            fields
                .get(key)
                .is_some_and(|s| s.split_whitespace().collect::<Vec<_>>() == ["65534"; 4]),
            "QEMU credentials are not wholly unprivileged",
        )?;
    }
    ensure(
        fields.get("Groups").is_some_and(|s| s.is_empty()),
        "QEMU retained supplementary groups",
    )?;
    for key in ["CapEff", "CapPrm", "CapInh", "CapAmb"] {
        ensure(
            fields
                .get(key)
                .and_then(|s| u64::from_str_radix(s, 16).ok())
                == Some(0),
            "QEMU retained a capability set",
        )?;
    }
    ensure(
        fields.get("NoNewPrivs").map(String::as_str) == Some("1")
            && fields.get("Seccomp").map(String::as_str) == Some("2"),
        "QEMU is missing no-new-privileges or its complete seccomp sandbox",
    )?;
    Ok(fields
        .into_iter()
        .filter(|(k, _)| {
            [
                "Pid",
                "Uid",
                "Gid",
                "Groups",
                "CapEff",
                "CapPrm",
                "CapInh",
                "CapAmb",
                "CapBnd",
                "NoNewPrivs",
                "Seccomp",
            ]
            .contains(&k.as_str())
        })
        .collect())
}

/// Unknown caller descriptors must already close at exec. Refuse a leaked
/// privileged FD instead of silently forwarding it or altering caller state.
fn reject_unexpected_inheritance() -> Result<()> {
    let mut numbers = BTreeSet::new();
    for entry in std::fs::read_dir("/proc/self/fd")? {
        let entry = entry?;
        let n: u32 = entry
            .file_name()
            .to_str()
            .ok_or("invalid self FD name")?
            .parse()?;
        if n > 2 {
            numbers.insert(n);
        }
    }
    for n in numbers {
        match std::fs::read_to_string(format!("/proc/self/fdinfo/{n}")) {
            Ok(info) => {
                let flags = info
                    .lines()
                    .find_map(|line| line.strip_prefix("flags:"))
                    .and_then(|v| u64::from_str_radix(v.trim(), 8).ok())
                    .ok_or("FD flags missing")?;
                ensure(
                    flags & 0o2000000 != 0,
                    "unexpected inherited descriptor in VM runner",
                )?;
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => (),
            Err(e) => return Err(e.into()),
        }
    }
    Ok(())
}

struct Inheritance<'a> {
    entries: Vec<(BorrowedFd<'a>, FdFlags)>,
}
impl<'a> Inheritance<'a> {
    fn new(fds: &[BorrowedFd<'a>]) -> Result<Self> {
        let mut result = Self {
            entries: Vec::new(),
        };
        for fd in fds {
            let old = rustix::io::fcntl_getfd(*fd)?;
            ensure(
                old.contains(FdFlags::CLOEXEC),
                "VM input was already inheritable",
            )?;
            result.entries.push((*fd, old));
            rustix::io::fcntl_setfd(*fd, old & !FdFlags::CLOEXEC)?;
        }
        Ok(result)
    }
    fn restore(&mut self) -> Result<()> {
        let mut failed = None;
        for (fd, flags) in &self.entries {
            if let Err(e) = rustix::io::fcntl_setfd(*fd, *flags) {
                failed = Some(e);
            }
        }
        if let Some(e) = failed {
            return Err(e.into());
        }
        self.entries.clear();
        Ok(())
    }
}
impl Drop for Inheritance<'_> {
    fn drop(&mut self) {
        let _ = self.restore();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn process_admission_rejects_privileged_or_incomplete_states() -> Result<()> {
        let status = "Pid:\t10\nUid:\t65534 65534 65534 65534\nGid:\t65534 65534 65534 65534\nGroups:\t\nCapEff:\t0\nCapPrm:\t0\nCapInh:\t0\nCapAmb:\t0\nCapBnd:\t0\nNoNewPrivs:\t1\nSeccomp:\t2\n";
        admit_status(status)?;
        for (from, to) in [
            ("Uid:\t65534 65534 65534 65534", "Uid:\t65534 0 65534 65534"),
            ("Groups:\t\n", "Groups:\t993\n"),
            ("CapEff:\t0", "CapEff:\t1"),
            ("CapAmb:\t0", "CapAmb:\t1"),
            ("NoNewPrivs:\t1", "NoNewPrivs:\t0"),
            ("Seccomp:\t2", "Seccomp:\t0"),
        ] {
            assert!(admit_status(&status.replace(from, to)).is_err());
        }
        Ok(())
    }
}
