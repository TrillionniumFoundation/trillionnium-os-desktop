//! Exclusive software-watchdog custody for one fixed working-copy owner.
//! The selected kernel's reopen does not feed an already armed timer. Its
//! nowayout close performs one final ping; callers retain that separate 900 s
//! failure bound. No write, timeout change, disable, magic close, or child FD
//! handoff is provided here.
use crate::{native_hardware_label as held, native_working_contract as contract};
use std::{
    ffi::CString,
    fs::{self, File, OpenOptions},
    io,
    os::{
        fd::{AsRawFd, FromRawFd},
        unix::{
            ffi::OsStrExt,
            fs::{FileExt, MetadataExt, OpenOptionsExt},
        },
    },
    path::{Path, PathBuf},
};

// Feed at 90s so the fixed 10s response wait and 15s PID1 query fit
// inside the original 120s progress contract. A late feed is refused.
const FEED_MARGIN_SECONDS: u64 = 30;
const SYSFS: &str = "/sys/devices/virtual/watchdog";
const DEVICE_LABEL: &[u8] = b"u:object_r:p4_linux_working_watchdog_t:s0";
const WDIOC_KEEPALIVE: libc::c_ulong = 0x8004_5705;
const SYSFS_MAGIC: libc::c_long = 0x62656572;
const TMPFS_MAGIC: libc::c_long = 0x01021994;
pub(super) fn monotonic_ns() -> io::Result<u64> {
    let mut time = std::mem::MaybeUninit::<libc::timespec>::uninit();
    // SAFETY: time has the exact clock_gettime output layout.
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, time.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let time = unsafe { time.assume_init() };
    u64::try_from(i128::from(time.tv_sec) * 1_000_000_000 + i128::from(time.tv_nsec))
        .map_err(|_| denied("watchdog monotonic clock is outside the normal range"))
}
fn denied(why: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
fn stable(file: &File) -> io::Result<[u64; 6]> {
    let m = file.metadata()?;
    Ok([
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
        m.nlink(),
    ])
}
fn filesystem(file: &File, expected: libc::c_long) -> io::Result<()> {
    let mut v = std::mem::MaybeUninit::<libc::statfs>::uninit();
    // SAFETY: the descriptor is held and v has the kernel ABI's full size.
    if unsafe { libc::fstatfs(file.as_raw_fd(), v.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { v.assume_init() }.f_type != expected {
        return Err(denied("working watchdog observation filesystem differs"));
    }
    Ok(())
}
fn canonical_number(name: &str) -> io::Result<u16> {
    let number = name
        .strip_prefix("watchdog")
        .ok_or_else(|| denied("working watchdog name differs"))?;
    if number.is_empty()
        || number.len() > 3
        || !number.bytes().all(|v| v.is_ascii_digit())
        || (number.len() > 1 && number.starts_with('0'))
    {
        return Err(denied("working watchdog number is not canonical"));
    }
    number
        .parse()
        .map_err(|_| denied("working watchdog number exceeds bound"))
}
fn dev_number(text: &str) -> io::Result<libc::dev_t> {
    let (major, minor) = text
        .split_once(':')
        .ok_or_else(|| denied("watchdog device pair absent"))?;
    let parse = |s: &str| -> io::Result<u32> {
        if s.is_empty()
            || s.len() > 10
            || !s.bytes().all(|v| v.is_ascii_digit())
            || (s.len() > 1 && s.starts_with('0'))
        {
            return Err(denied("watchdog device number is not canonical"));
        }
        s.parse()
            .map_err(|_| denied("watchdog device number exceeds ABI"))
    };
    let (major, minor) = (parse(major)?, parse(minor)?);
    let device = libc::makedev(major, minor);
    if major == 0 || libc::major(device) != major || libc::minor(device) != minor {
        return Err(denied("watchdog device pair exceeds selected kernel ABI"));
    }
    Ok(device)
}
struct Directory {
    path: PathBuf,
    file: File,
    pin: [u64; 6],
}
impl Directory {
    fn open(path: &Path, magic: Option<libc::c_long>) -> io::Result<Self> {
        if path.canonicalize()? != path {
            return Err(denied("watchdog directory alias"));
        }
        let mut dir = held::path_at(libc::AT_FDCWD, c"/")?;
        held::directory(&dir)?;
        for part in path.components().skip(1) {
            let std::path::Component::Normal(part) = part else {
                return Err(denied("watchdog directory path is not canonical"));
            };
            dir = held::path_at(
                dir.as_raw_fd(),
                &CString::new(part.as_bytes()).map_err(io::Error::other)?,
            )?;
            held::directory(&dir)?;
        }
        if let Some(magic) = magic {
            filesystem(&dir, magic)?;
        }
        let pin = stable(&dir)?;
        let result = Self {
            path: path.into(),
            file: dir,
            pin,
        };
        result.guard()?;
        Ok(result)
    }
    fn guard(&self) -> io::Result<()> {
        if self.path.canonicalize()? != self.path {
            return Err(denied("watchdog directory alias appeared"));
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
            .open(&self.path)?;
        // Child directories may legitimately be born. Directory link count,
        // size and timestamps are not an immutable runtime assertion.
        if stable(&self.file)?[..5] != self.pin[..5] || stable(&named)?[..5] != self.pin[..5] {
            return Err(denied("held watchdog directory changed"));
        }
        Ok(())
    }
}
struct Attribute {
    name: &'static str,
    file: File,
    pin: [u64; 6],
}
impl Attribute {
    fn open(dir: &Directory, name: &'static str) -> io::Result<Self> {
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
            .open(dir.path.join(name))?;
        let pin = stable(&file)?;
        if pin[2] & u64::from(libc::S_IFMT) != u64::from(libc::S_IFREG)
            || pin[2] & 0o022 != 0
            || pin[3..6] != [0, 0, 1]
        {
            return Err(denied("watchdog sysfs attribute is not its root inode"));
        }
        filesystem(&file, SYSFS_MAGIC)?;
        Ok(Self { name, file, pin })
    }
    fn text(&self, dir: &Directory) -> io::Result<String> {
        dir.guard()?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
            .open(dir.path.join(self.name))?;
        if stable(&self.file)? != self.pin || stable(&named)? != self.pin {
            return Err(denied("held watchdog sysfs attribute changed"));
        }
        let mut raw = [0u8; 513];
        let n = self.file.read_at(&mut raw, 0)?;
        if n == 0 || n > 512 {
            return Err(denied("watchdog sysfs text exceeds bound"));
        }
        let value = std::str::from_utf8(&raw[..n])
            .map_err(|_| denied("watchdog sysfs text is not UTF-8"))?;
        if !value.ends_with('\n') || value[..value.len() - 1].contains(['\n', '\r', '\0']) {
            return Err(denied("watchdog sysfs text is not one normal line"));
        }
        if stable(&self.file)? != self.pin || stable(&named)? != self.pin {
            return Err(denied("watchdog attribute changed during read"));
        }
        Ok(value[..value.len() - 1].into())
    }
}
fn unique_software(base: &Directory) -> io::Result<String> {
    base.guard()?;
    let mut found = None;
    let mut count = 0;
    for row in fs::read_dir(&base.path)? {
        count += 1;
        if count > 16 {
            return Err(denied("virtual watchdog inventory exceeds 16"));
        }
        let row = row?;
        let name = row
            .file_name()
            .into_string()
            .map_err(|_| denied("virtual watchdog name is not UTF-8"))?;
        canonical_number(&name)?;
        let dir = Directory::open(&row.path(), Some(SYSFS_MAGIC))?;
        if Attribute::open(&dir, "identity")?.text(&dir)? == "Software Watchdog" {
            if found.replace(name).is_some() {
                return Err(denied("software watchdog identity is not unique"));
            }
        }
        dir.guard()?;
    }
    base.guard()?;
    found.ok_or_else(|| denied("selected software watchdog is absent"))
}

fn armed_values_match(values: &[String], rdev: libc::dev_t) -> bool {
    values
        == [
            "Software Watchdog".to_owned(),
            "active".into(),
            "1".into(),
            contract::WATCHDOG_INTERVAL_SECONDS.to_string(),
            format!("{}:{}", libc::major(rdev), libc::minor(rdev)),
        ]
}
fn require_armed(sys: &Directory, attributes: &[Attribute], rdev: libc::dev_t) -> io::Result<()> {
    if attributes
        .iter()
        .map(|a| a.name)
        .ne(["identity", "state", "nowayout", "timeout", "dev"])
    {
        return Err(denied("software watchdog attribute closure differs"));
    }
    let values = attributes
        .iter()
        .map(|a| a.text(sys))
        .collect::<io::Result<Vec<_>>>()?;
    if !armed_values_match(&values, rdev) {
        return Err(denied("actual software watchdog state differs"));
    }
    sys.guard()
}

fn require_timely(last: Option<u64>, now: u64) -> io::Result<()> {
    if let Some(last) = last {
        let gap = now
            .checked_sub(last)
            .ok_or_else(|| denied("watchdog monotonic clock went backwards"))?;
        if gap > contract::KEEPALIVE_PERIOD_SECONDS * 1_000_000_000 {
            return Err(denied(
                "working owner missed its original 120-second progress bound",
            ));
        }
    }
    Ok(())
}

/// Private, move-only, never Clone/Deserialize. The only body operation is the
/// source-fixed KEEPALIVE ioctl after the owning module's live guards.
pub(super) struct SoftwareWatchdog {
    base: Directory,
    sys: Directory,
    dev: Directory,
    name: String,
    attributes: Vec<Attribute>,
    device: File,
    device_pin: [u64; 6],
    rdev: libc::dev_t,
    last_ping_ns: Option<u64>,
    pings: u64,
    pid: u32,
}
impl SoftwareWatchdog {
    pub(super) fn open() -> io::Result<Self> {
        let base = Directory::open(Path::new(SYSFS), Some(SYSFS_MAGIC))?;
        let name = unique_software(&base)?;
        let sys = Directory::open(&base.path.join(&name), Some(SYSFS_MAGIC))?;
        let attributes = ["identity", "state", "nowayout", "timeout", "dev"]
            .into_iter()
            .map(|n| Attribute::open(&sys, n))
            .collect::<io::Result<Vec<_>>>()?;
        let rdev = dev_number(&attributes[4].text(&sys)?)?;
        let dev = Directory::open(Path::new("/dev"), Some(TMPFS_MAGIC))?;
        let path = dev.path.join(&name);
        let metadata = held::path_at(
            dev.file.as_raw_fd(),
            &CString::new(name.as_bytes()).map_err(io::Error::other)?,
        )?;
        let before = stable(&metadata)?;
        if before[2] != u64::from(libc::S_IFCHR | 0o600)
            || before[3..6] != [0, 0, 1]
            || metadata.metadata()?.rdev() != rdev
            || held::label(&metadata)? != DEVICE_LABEL
        {
            return Err(denied(
                "software watchdog is not the exact normal labelled root device",
            ));
        }
        // Inspect the same held sysfs attributes before an open that could arm
        // a stopped device. Only the early owner's already-active, nowayout,
        // fixed-900-second timer may reach exclusive reopen. The after-open
        // guard below repeats this exact comparison.
        require_armed(&sys, &attributes, rdev)?;
        let device = OpenOptions::new()
            .write(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(&path)?;
        // Exclusive driver open supplies the kernel ownership gate. No write
        // or ioctl is issued by this constructor.
        if stable(&device)? != before || device.metadata()?.rdev() != rdev {
            return Err(denied("watchdog device changed at exclusive open"));
        }
        let duplicate = unsafe { libc::fcntl(device.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 96) };
        if duplicate < 0 {
            return Err(io::Error::last_os_error());
        }
        let retained = unsafe { File::from_raw_fd(duplicate) };
        drop(device);
        let device = retained;
        let flags = unsafe { libc::fcntl(device.as_raw_fd(), libc::F_GETFD) };
        if flags < 0 || flags & libc::FD_CLOEXEC == 0 {
            return Err(denied("watchdog descriptor must remain close-on-exec"));
        }
        let result = Self {
            base,
            sys,
            dev,
            name,
            attributes,
            device,
            device_pin: before,
            rdev,
            last_ping_ns: None,
            pings: 0,
            pid: std::process::id(),
        };
        result.guard()?;
        Ok(result)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        if self.pid != std::process::id() || unique_software(&self.base)? != self.name {
            return Err(denied(
                "watchdog custody left its original process or software device",
            ));
        }
        self.sys.guard()?;
        self.dev.guard()?;
        require_armed(&self.sys, &self.attributes, self.rdev)?;
        let named = held::path_at(
            self.dev.file.as_raw_fd(),
            &CString::new(self.name.as_bytes()).map_err(io::Error::other)?,
        )?;
        if stable(&named)? != self.device_pin
            || stable(&self.device)? != self.device_pin
            || named.metadata()?.rdev() != self.rdev
            || self.device.metadata()?.rdev() != self.rdev
            || held::label(&named)? != DEVICE_LABEL
            || held::label(&self.device)? != DEVICE_LABEL
        {
            return Err(denied(
                "held software watchdog descriptor or device label changed",
            ));
        }
        let flags = unsafe { libc::fcntl(self.device.as_raw_fd(), libc::F_GETFD) };
        if flags < 0 || flags & libc::FD_CLOEXEC == 0 {
            return Err(denied("watchdog FD inheritance changed"));
        }
        Ok(())
    }
    pub(super) fn due(&self, now_ns: u64) -> bool {
        self.last_ping_ns.is_none_or(|last| {
            now_ns.saturating_sub(last)
                >= (contract::KEEPALIVE_PERIOD_SECONDS - FEED_MARGIN_SECONDS) * 1_000_000_000
        })
    }
    // Only the private working runtime calls this after its actual same-owner
    // Main/namespace/storage/source bookends. The end is immutable there and
    // compared to the source schedule here; it is never an extension request.
    pub(super) fn keepalive(&mut self, start_ns: u64, end_ns: u64) -> io::Result<()> {
        self.guard()?;
        let now = monotonic_ns()?;
        contract::WorkingSchedule::selected().check_keepalive_time(end_ns, start_ns, now)?;
        if !self.due(now) {
            return Err(denied("duplicate early watchdog feed"));
        }
        require_timely(self.last_ping_ns, now)?;
        let mut unused: libc::c_int = 0;
        // SAFETY: one held exclusive watchdog FD, the selected Linux UAPI
        // KEEPALIVE command and correctly sized int storage. No generic ioctl.
        if unsafe { libc::ioctl(self.device.as_raw_fd(), WDIOC_KEEPALIVE, &mut unused) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let after = monotonic_ns()?;
        let previous = self.last_ping_ns;
        self.last_ping_ns = Some(after);
        require_timely(previous, after)?;
        self.pings = self
            .pings
            .checked_add(1)
            .ok_or_else(|| denied("watchdog ping count overflow"))?;
        contract::WorkingSchedule::selected().check_keepalive_time(end_ns, start_ns, after)?;
        self.guard()
    }
    /// Pre-exec closes this exact inherited descriptor before the normal child
    /// runs. The parent retains its only open-file description throughout.
    pub(super) fn child_close_fd(&self) -> libc::c_int {
        self.device.as_raw_fd()
    }
    pub(super) fn observation(&self) -> serde_json::Value {
        serde_json::json!({"schema":"droidloom.working-watchdog-custody.v1","device":self.dev.path.join(&self.name),
            "device_identity":self.device_pin,"rdev":[libc::major(self.rdev),libc::minor(self.rdev)],
            "interval_seconds":contract::WATCHDOG_INTERVAL_SECONDS,"successful_keepalives":self.pings,
            "last_keepalive_monotonic_ns":self.last_ping_ns,"same_parent_pid":self.pid,
            "write_calls":0,"set_timeout_calls":0,"disable_calls":0,"descriptor_passed_to_child":false,
            "nowayout_close_final_ping_seconds":contract::WATCHDOG_INTERVAL_SECONDS})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_watchdog_late_progress_never_renews_a_failed_owner() {
        let second = 1_000_000_000;
        require_timely(Some(second), second + 120 * second).unwrap();
        assert!(require_timely(Some(second), second + 120 * second + 1).is_err());
        assert!(require_timely(Some(second), 0).is_err());
        assert_eq!(contract::KEEPALIVE_PERIOD_SECONDS - FEED_MARGIN_SECONDS, 90);
    }
    #[test]
    fn working_watchdog_selected_names_and_device_pairs_are_canonical() {
        assert_eq!(canonical_number("watchdog0").unwrap(), 0);
        assert_eq!(canonical_number("watchdog999").unwrap(), 999);
        for s in [
            "watchdog",
            "watchdog00",
            "watchdog1000",
            "watchdog-1",
            "../watchdog0",
            "watchdog0/x",
        ] {
            assert!(canonical_number(s).is_err(), "{s}");
        }
        let actual = dev_number("10:130").unwrap();
        assert_eq!((libc::major(actual), libc::minor(actual)), (10, 130));
        for s in [
            "0:0",
            "010:130",
            "10:0130",
            "10:1:1",
            "-1:2",
            "10:4294967296",
        ] {
            assert!(dev_number(s).is_err(), "{s}");
        }
    }
    #[test]
    fn working_watchdog_reopen_requires_the_complete_already_armed_preimage() {
        let device = dev_number("10:130").unwrap();
        let values = ["Software Watchdog", "active", "1", "900", "10:130"].map(str::to_owned);
        assert!(armed_values_match(&values, device));
        for (index, wrong) in [
            (0, "other"),
            (1, "inactive"),
            (2, "0"),
            (3, "901"),
            (4, "10:131"),
        ] {
            let mut changed = values.clone();
            changed[index] = wrong.into();
            assert!(!armed_values_match(&changed, device));
        }
        assert!(!armed_values_match(&values[..4], device));
        assert!(!armed_values_match(&values, dev_number("10:131").unwrap()));
    }
    #[test]
    fn working_watchdog_fixed_ioctl_and_expiry_do_not_inherit_once_window() {
        assert_eq!(WDIOC_KEEPALIVE & 0xffff, 0x5705);
        let schedule = contract::WorkingSchedule::selected();
        let start = 100_000_000_000;
        let end = schedule.authorization_end_ns(start).unwrap();
        assert!(schedule.whole_suite_seconds > 65535);
        schedule.check_keepalive_time(end, start, end - 1).unwrap();
        assert!(schedule.check_keepalive_time(end, start, end).is_err());
        assert!(
            schedule
                .check_keepalive_time(end + 1, start, end - 1)
                .is_err()
        );
        assert_eq!(schedule.watchdog_interval_seconds, 900);
    }
}
