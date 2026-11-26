//! Qualification-only software watchdog before the shared policy/PID1 handoff.
//! This covers a bounded userspace stall while timer interrupts still run. It
//! does not claim hardware watchdog coverage, kernel hard-lockup recovery, or
//! successful application, data-retirement, or original-machine qualification.
use crate::{Result, boot_files as files, ensure, fs};
use files::FilePin;
use rustix::fs::{FileType, Mode, OFlags};
use serde_json::json;
use std::{
    ffi::CString,
    fs::File,
    io::Read,
    os::fd::AsRawFd,
    path::{Path, PathBuf},
    time::{Duration, Instant},
};

#[path = "../../../runtime/droidloom-supervisor/src/native_once_contract.rs"]
pub(super) mod contract;
use contract::{
    CONFIG_SHA, EARLY_CONFIG, EARLY_EXECUTABLE, KERNEL, KERNEL_SHA, MODULE_BYTES, MODULE_REL,
    MODULE_SHA, ROOT_UUID, boot_arguments,
};
pub(super) use contract::{EarlyConfiguration, RecoveryBootSpec};
const EARLY_RUN: &str = "/run/initramfs/droidloom-original-once";

fn text(path: &Path, limit: u64) -> Result<String> {
    let mut bytes = Vec::new();
    File::open(path)?.take(limit + 1).read_to_end(&mut bytes)?;
    ensure(
        bytes.len() as u64 <= limit,
        "early observation exceeds bound",
    )?;
    Ok(String::from_utf8(bytes)?
        .trim_end_matches(['\0', '\n'])
        .to_owned())
}

/// A real initial initramfs owner, separate from original-machine authority.
/// Once constructed, a later preparation failure may reboot this candidate.
/// Failure to construct it never changes the caller's system.
struct EarlyOwner {
    root: File,
    root_identity: crate::model::Identity,
    boot_id: String,
    intent_sha256: String,
    configuration_sha256: String,
}

impl EarlyOwner {
    fn establish() -> Result<Self> {
        ensure(
            rustix::process::getuid().as_raw() == 0
                && rustix::process::geteuid().as_raw() == 0
                && rustix::process::getgid().as_raw() == 0
                && rustix::process::getegid().as_raw() == 0,
            "early watchdog requires actual initial root",
        )?;
        ensure(
            text(Path::new("/proc/sys/kernel/osrelease"), 256)? == KERNEL,
            "early watchdog is not on the admitted shared kernel",
        )?;
        let proc = fs::Tree::open("/proc", 0)?;
        ensure(
            rustix::fs::fstatfs(&proc.root)?.f_type as u64 == 0x9fa0,
            "early kernel observations are not procfs",
        )?;
        let root = fs::Tree::open("/", 0)?.root;
        let magic = rustix::fs::fstatfs(&root)?.f_type as u64;
        ensure(
            magic == 0x01021994 || magic == 0x858458f6,
            "watchdog entry is only available in the initial RAM root",
        )?;
        let root_identity = fs::stat(&root)?;
        let pid1 = File::from(rustix::fs::open(
            "/proc/1/root",
            OFlags::PATH | OFlags::DIRECTORY | OFlags::CLOEXEC,
            Mode::empty(),
        )?);
        let other = fs::stat(&pid1)?;
        ensure(
            (root_identity.dev, root_identity.ino) == (other.dev, other.ino),
            "early watchdog is chrooted",
        )?;
        for ns in ["user", "pid", "mnt"] {
            let own = std::fs::read_link(format!("/proc/self/ns/{ns}"))?;
            ensure(
                own == std::fs::read_link(format!("/proc/1/ns/{ns}"))?,
                "early watchdog namespace differs from PID1",
            )?;
            if ns == "user" {
                ensure(
                    own == Path::new("user:[4026531837]"),
                    "initial user namespace required",
                )?;
            }
        }
        ensure(
            text(Path::new("/proc/self/uid_map"), 256)?
                .split_whitespace()
                .collect::<Vec<_>>()
                == ["0", "0", "4294967295"],
            "early watchdog uid map differs",
        )?;
        let arguments = boot_arguments(&text(Path::new("/proc/cmdline"), 32768)?)?;
        // The selected kernel's services.c maps pre-policy SECINITSID_INIT
        // to the compatibility string "kernel". This verifies that external
        // representation, not a claim that userspace actually has KERNEL SID.
        // Use the named SELinux provider, never AppArmor's legacy attr slot.
        ensure(
            text(Path::new("/proc/self/attr/selinux/current"), 256)? == "kernel",
            "early watchdog must precede initial joint policy loading",
        )?;
        let uptime = text(Path::new("/proc/uptime"), 128)?;
        let seconds: u64 = uptime
            .split_whitespace()
            .next()
            .ok_or("missing uptime")?
            .split('.')
            .next()
            .ok_or("missing uptime seconds")?
            .parse()?;
        ensure(
            seconds <= 90,
            "watchdog was not armed during bounded early boot",
        )?;
        let boot_id = text(Path::new("/proc/sys/kernel/random/boot_id"), 80)?;
        ensure(boot_id.len() == 36, "early kernel boot ID malformed")?;
        Ok(Self {
            root,
            root_identity,
            boot_id,
            intent_sha256: arguments["droidloom.once"].clone(),
            configuration_sha256: arguments["droidloom.once.config"].clone(),
        })
    }

    fn revalidate(&self) -> Result<()> {
        let current = fs::stat(&fs::Tree::open("/", 0)?.root)?;
        let held = fs::stat(&self.root)?;
        ensure(
            (held.dev, held.ino, held.mode, held.uid, held.gid)
                == (
                    self.root_identity.dev,
                    self.root_identity.ino,
                    self.root_identity.mode,
                    self.root_identity.uid,
                    self.root_identity.gid,
                )
                && (current.dev, current.ino) == (held.dev, held.ino)
                && text(Path::new("/proc/sys/kernel/random/boot_id"), 80)? == self.boot_id,
            "early owner root or boot changed",
        )
    }

    fn abort_boot(&self, error: &dyn std::fmt::Display) -> Result<()> {
        self.revalidate()?;
        eprintln!(
            "DROIDLOOM_ONCE_EARLY_FAILED intent={} error={error}",
            self.intent_sha256
        );
        // Initial RAM root only; no original/working data filesystem is opened
        // here. A consumed GRUB one-shot leaves the verified original default.
        rustix::system::reboot(rustix::system::RebootCommand::Restart)?;
        Err("candidate early reboot unexpectedly returned".into())
    }
}

fn protected(pin: &FilePin, mode: u32) -> Result<(File, crate::model::Identity)> {
    fs::Tree::open("/", 0)?.parent(&fs::absolute_string(&pin.path)?)?;
    let (file, id) = files::open_pin(pin)?;
    ensure(
        id.uid == 0 && id.gid == 0 && id.nlink == 1 && id.mode & 0o7777 == mode,
        "early source metadata differs",
    )?;
    ensure(
        fs::hash(&file)? == pin.sha256 && fs::stat(&file)? == id,
        "early source bytes changed",
    )?;
    Ok((file, id))
}

fn arm(owner: &EarlyOwner) -> Result<serde_json::Value> {
    owner.revalidate()?;
    let config_pin = files::pin_file(Path::new(EARLY_CONFIG))?;
    ensure(
        config_pin.bytes <= 65536 && config_pin.sha256 == owner.configuration_sha256,
        "early configuration is not the exact GRUB-selected bytes",
    )?;
    let _config = protected(&config_pin, 0o444)?;
    let config: EarlyConfiguration = serde_json::from_slice(&files::read_pin(&config_pin, 65536)?)?;
    ensure(
        config.schema == "droidloom.original-once-early.v1"
            && config.intent_sha256 == owner.intent_sha256,
        "early configuration does not bind the immutable once intent",
    )?;
    let spec = &config.recovery;
    spec.validate()?;
    let own = FilePin {
        path: EARLY_EXECUTABLE.into(),
        bytes: spec.helper_bytes,
        sha256: spec.helper_sha256.clone(),
    };
    let (own_file, own_id) = protected(&own, 0o555)?;
    let actual_exe = File::open("/proc/self/exe")?;
    ensure(
        fs::stat(&actual_exe)? == own_id && fs::stat(&own_file)? == own_id,
        "early entry is not the normal pinned executable inode",
    )?;
    ensure(
        !Path::new("/sys/module/softdog").try_exists()?,
        "softdog already has an unknown boot owner",
    )?;
    let module = FilePin {
        path: PathBuf::from(format!("/usr/lib/modules/{KERNEL}/{MODULE_REL}")),
        bytes: MODULE_BYTES,
        sha256: MODULE_SHA.into(),
    };
    let (module_file, module_id) = protected(&module, 0o644)?;
    let sys = fs::Tree::open("/sys", 0)?;
    ensure(
        rustix::fs::fstatfs(&sys.root)?.f_type as u64 == 0x62656572,
        "early /sys is not sysfs",
    )?;
    let started = Instant::now();
    // The exact signed admitted module is passed through a held descriptor;
    // no modprobe configuration, shell, search path or caller module is used.
    rustix::system::finit_module(&module_file, &spec.parameters()?, 0)?;
    ensure(
        fs::stat(&module_file)? == module_id,
        "held signed watchdog module changed",
    )?;
    ensure(
        text(Path::new("/sys/module/softdog/initstate"), 64)? == "live",
        "softdog module did not become live",
    )?;
    let mut selected = None;
    let mut count = 0;
    for entry in std::fs::read_dir("/sys/class/watchdog")? {
        count += 1;
        ensure(count <= 32, "watchdog class entry bound exceeded")?;
        let entry = entry?;
        let name = entry
            .file_name()
            .into_string()
            .map_err(|_| "invalid watchdog name")?;
        let digits = name
            .strip_prefix("watchdog")
            .ok_or("unknown watchdog class entry")?;
        ensure(
            !digits.is_empty() && digits.len() <= 3 && digits.bytes().all(|b| b.is_ascii_digit()),
            "invalid watchdog index",
        )?;
        let canonical = PathBuf::from(format!("/sys/devices/virtual/watchdog/{name}"));
        if std::fs::read_link(entry.path())?
            != PathBuf::from(format!("../../devices/virtual/watchdog/{name}"))
        {
            continue;
        }
        let node = fs::Tree::open(&fs::absolute_string(&canonical)?, 0)?;
        ensure(
            rustix::fs::fstatfs(&node.root)?.f_type as u64 == 0x62656572,
            "watchdog node left sysfs",
        )?;
        if text(&canonical.join("identity"), 128)? != "Software Watchdog" {
            continue;
        }
        ensure(selected.is_none(), "multiple software watchdog owners")?;
        selected = Some((name, canonical));
    }
    let (name, sysfs) = selected.ok_or("admitted software watchdog did not register")?;
    let dev = text(&sysfs.join("dev"), 64)?;
    let fields: Vec<_> = dev.split(':').collect();
    ensure(fields.len() == 2, "watchdog device identity malformed")?;
    let major: u32 = fields[0].parse()?;
    let minor: u32 = fields[1].parse()?;
    let devtree = fs::Tree::open("/dev", 0)?;
    ensure(
        rustix::fs::fstatfs(&devtree.root)?.f_type as u64 == 0x01021994,
        "early watchdog target is not normal devtmpfs",
    )?;
    let node = File::from(rustix::fs::openat(
        &devtree.root,
        name.as_str(),
        OFlags::PATH | OFlags::NOFOLLOW | OFlags::CLOEXEC,
        Mode::empty(),
    )?);
    let before = rustix::fs::fstat(&node)?;
    ensure(
        FileType::from_raw_mode(before.st_mode) == FileType::CharacterDevice
            && before.st_uid == 0
            && before.st_gid == 0
            && before.st_nlink == 1
            && before.st_mode & 0o7777 == 0o600
            && rustix::fs::major(before.st_rdev) == major
            && rustix::fs::minor(before.st_rdev) == minor,
        "software watchdog character inode differs from the held sysfs identity",
    )?;
    owner.revalidate()?;
    let watch = File::from(rustix::fs::open(
        format!("/proc/self/fd/{}", node.as_raw_fd()),
        OFlags::WRONLY | OFlags::CLOEXEC | OFlags::NONBLOCK,
        Mode::empty(),
    )?);
    let opened = rustix::fs::fstat(&watch)?;
    ensure(
        fs::identity(&opened) == fs::identity(&before) && opened.st_rdev == before.st_rdev,
        "watchdog open changed device identity",
    )?;
    ensure(
        text(&sysfs.join("state"), 64)? == "active"
            && text(&sysfs.join("timeout"), 64)?.parse::<u32>()? == spec.watchdog_seconds
            && text(&sysfs.join("nowayout"), 64)? == "1",
        "actual watchdog active/timeout/nowayout readback differs",
    )?;
    // No magic close and no keepalive writes: core release pings once, keeps
    // ACTIVE/HW_RUNNING, and softdog's zero max_hw_heartbeat needs no worker.
    drop(watch);
    ensure(
        text(&sysfs.join("state"), 64)? == "active",
        "software watchdog stopped on close",
    )?;
    ensure(
        started.elapsed() < Duration::from_secs(5),
        "early arming exceeded the source-bound timing margin",
    )?;
    owner.revalidate()?;
    let report = json!({"schema":"droidloom.original-once-watchdog-armed.v1",
        "intent_sha256":owner.intent_sha256,"early_configuration":config_pin,"candidate_id":spec.candidate_id,
        "boot_id":owner.boot_id,"kernel":KERNEL,"signed_module":module,
        "module_parameters":spec.parameters()?.to_str()?,"device":format!("/dev/{name}"),
        "rdev":[major,minor],"state_after_close":"active","timeout_seconds":spec.watchdog_seconds,
        "nowayout":true,"normal_reboot_stops_via_kernel_notifier":true,
        "software_timer_requires_running_interrupts":true,"hardware_hang_coverage":false,
        "runtime_qualified":false,"production_ready":false});
    files::private_dir(Path::new(EARLY_RUN))?;
    let mut bytes = serde_json::to_vec_pretty(&report)?;
    bytes.push(b'\n');
    files::write_new(&Path::new(EARLY_RUN).join("ARMED.json"), &bytes, 0o400)?;
    Ok(report)
}

pub(super) fn early() -> Result<()> {
    // A caller outside this precise initial qualification boot gets an error
    // before any module load, device open or reboot is available.
    let owner = EarlyOwner::establish()?;
    match arm(&owner) {
        Ok(report) => {
            println!("{}", serde_json::to_string(&report)?);
            Ok(())
        }
        Err(error) => owner.abort_boot(&error),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn spec() -> RecoveryBootSpec {
        RecoveryBootSpec {
            schema: "droidloom.original-once-recovery-boot.v1".into(),
            candidate_id: "c".repeat(64),
            helper_bytes: 10000,
            helper_sha256: "d".repeat(64),
            kernel_release: KERNEL.into(),
            kernel_sha256: KERNEL_SHA.into(),
            kernel_config_sha256: CONFIG_SHA.into(),
            module_relative: MODULE_REL.into(),
            module_bytes: MODULE_BYTES,
            module_sha256: MODULE_SHA.into(),
            watchdog_seconds: 1200,
            collect_at_boot_seconds: 600,
            return_at_boot_seconds: 900,
            panic_seconds: 10,
        }
    }
    fn cmdline() -> String {
        format!(
            "root=UUID={ROOT_UUID} panic=10 droidloom.once={} droidloom.once.config={} droidloom.once.return={} {}",
            "a".repeat(64),
            "b".repeat(64),
            "c".repeat(64),
            contract::SUSPEND_TARGETS
                .iter()
                .chain(contract::PACKAGE_WRITERS.iter())
                .map(|t| format!("systemd.mask={t}"))
                .collect::<Vec<_>>()
                .join(" ")
        )
    }
    #[test]
    fn recovery_contract_keeps_exact_kernel_module_and_separate_deadlines() -> Result<()> {
        let mut s = spec();
        s.validate()?;
        assert_eq!(
            s.parameters()?.to_str()?,
            "soft_margin=1200 nowayout=1 soft_active_on_boot=1 soft_noboot=0 soft_panic=0"
        );
        s.return_at_boot_seconds = 1100;
        assert!(s.validate().is_err());
        s = spec();
        s.module_sha256 = "a".repeat(64);
        assert!(s.validate().is_err());
        s = spec();
        s.panic_seconds = 0;
        assert!(s.validate().is_err());
        Ok(())
    }
    #[test]
    fn early_boot_arguments_reject_duplicate_owner_root_panic_and_sleep_escape() -> Result<()> {
        let c = cmdline();
        let actual = boot_arguments(&c)?;
        assert_eq!(actual["droidloom.once"], "a".repeat(64));
        assert!(boot_arguments(&(c.clone() + " droidloom.once=" + &"a".repeat(64))).is_err());
        assert!(boot_arguments(&c.replace("panic=10", "panic=0")).is_err());
        assert!(boot_arguments(&c.replace("systemd.mask=sleep.target", "")).is_err());
        assert!(
            boot_arguments(&c.replace(ROOT_UUID, "11111111-1111-4111-8111-111111111111")).is_err()
        );
        Ok(())
    }
}
