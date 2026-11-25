//! The first policy loader measures the three original kernel profile objects
//! before switching to the enforcing host domains. Each consumer checks the
//! live namespace, object identities, modes and both policy generations again.
use super::*;

const PATH: &str = "/run/droidloom-early/kernel-policy/apparmor-epoch";
const ROLES: [&str; 3] = [
    "droidloom-policy-loader",
    "droidloom-production-android",
    "droidloom-production-broker",
];
const CONTEXT: &str = "u:object_r:p4_linux_apparmor_epoch_t:s0";

const REVISION_CONTEXT: &str = "u:object_r:p4_linux_apparmor_revision_t:s0";
const BIRTHS: [u64; 3] = [164, 165, 166];

struct Role {
    directory: CString,
    inode: [u64; 4],
    raw: Option<RawProfile>,
}
struct RawProfile {
    generation: CString,
    bytes_inode: u64,
    hash_inode: u64,
    counter: Option<Counter>,
}
struct Counter {
    inode: u64,
    initial: u64,
    camera: bool,
}

pub(super) struct BoardEpoch {
    seal: Sealed,
    pub(super) boot: String,
    // The acquisition's operation epoch remains immutable for release capture.
    pub(super) revision: i64,
    boot_revision: i64,
    pub(super) selinux_sequence: u32,
    pub(super) policyload: u32,
    mount: u64,
    root: u64,
    profiles: u64,
    roles: Vec<Role>,
    path: &'static str,
    names: &'static [&'static str],
    root_handle: File,
    // O_PATH descriptors retain original dentries/inodes for the authority's life.
    // Fresh READ descriptors are used for every seq_file counter observation.
    held: Vec<File>,
}

fn number(text: &str) -> Result<u64> {
    require(
        !text.is_empty()
            && text.bytes().all(|v| v.is_ascii_digit())
            && (text == "0" || !text.starts_with('0')),
        "canonical unsigned epoch field",
    )?;
    text.parse()
        .map_err(|_| MacError::Rejected("kernel epoch integer overflow"))
}

fn row<const N: usize>(line: Option<&str>) -> Result<[&str; N]> {
    let text = line.ok_or(MacError::Rejected("missing boot measurement line"))?;
    let columns: Vec<_> = text.split(' ').collect();
    columns
        .try_into()
        .map_err(|_| MacError::Rejected("invalid boot measurement column count"))
}

fn packet_file(file: &File) -> Result<()> {
    require(
        kind(file)? == libc::TMPFS_MAGIC as u64,
        "boot measurement requires the original tmpfs",
    )?;
    let mut fs = std::mem::MaybeUninit::<libc::statvfs>::uninit();
    if unsafe { libc::fstatvfs(file.as_raw_fd(), fs.as_mut_ptr()) } < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let flags = libc::ST_RDONLY | libc::ST_NOSUID | libc::ST_NODEV | libc::ST_NOEXEC;
    require(
        unsafe { fs.assume_init() }.f_flag & flags == flags
            && file.metadata()?.mode() & 0o7777 == 0o400,
        "protected read-only boot measurement mount",
    )?;
    let mut raw = [0_u8; 128];
    let size = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            raw.as_mut_ptr().cast(),
            raw.len(),
        )
    };
    if size < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        context_matches(&raw[..size as usize], CONTEXT),
        "fixed board measurement SELinux inode label",
    )
}

// AppArmor's internal filesystem is outside the process mount namespace.
// Only fixed kernel links are followed. File data is read exclusively from
// authenticated original revision objects, under the narrow joint MAC rules.
fn aa_handle(
    parent: &File,
    name: &CStr,
    directory: bool,
    follow_kernel_link: bool,
) -> Result<File> {
    let mut flags = libc::O_PATH | libc::O_CLOEXEC;
    if directory {
        flags |= libc::O_DIRECTORY;
    }
    if !follow_kernel_link {
        flags |= libc::O_NOFOLLOW;
    }
    let fd = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags) };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    require(
        kind(&file)? == AAFS_MAGIC,
        "fixed original AppArmor kernel mount",
    )?;
    Ok(file)
}

fn object(file: &File, mount: u64, inode: u64) -> Result<()> {
    let name = CString::new(file.as_raw_fd().to_string()).unwrap();
    let directory = open_at(
        own_proc()?.as_raw_fd(),
        c"fdinfo",
        libc::O_PATH | libc::O_DIRECTORY,
    )?;
    let body = open_at(directory.as_raw_fd(), &name, libc::O_RDONLY)?;
    require(
        kind(&body)? == PROC_MAGIC,
        "kernel procfs descriptor identity",
    )?;
    let bytes = bounded(&body, 4096)?;
    let value =
        std::str::from_utf8(&bytes).map_err(|_| MacError::Rejected("invalid proc fdinfo"))?;
    for (key, expected) in [("mnt_id:\t", mount), ("ino:\t", inode)] {
        let mut fields = value.lines().filter_map(|line| line.strip_prefix(key));
        let actual = number(
            fields
                .next()
                .ok_or(MacError::Rejected("missing descriptor identity"))?,
        )?;
        require(
            expected != 0 && actual == expected && fields.next().is_none(),
            "original AppArmor mount and inode must match the boot measurement",
        )?;
    }
    Ok(())
}

fn counter_identity(file: &File, mount: u64, inode: u64) -> Result<()> {
    counter_identity_as(file, mount, inode, REVISION_CONTEXT)
}
fn counter_identity_as(file: &File, mount: u64, inode: u64, context: &str) -> Result<()> {
    require(
        kind(file)? == AAFS_MAGIC,
        "revision must be the original AppArmor filesystem",
    )?;
    object(file, mount, inode)?;
    let stat = file.metadata()?;
    require(
        stat.is_file()
            && stat.uid() == 0
            && stat.gid() == 0
            && stat.mode() & 0o7777 == 0o444
            && stat.nlink() == 1,
        "original root-owned read-only AppArmor revision inode",
    )?;
    let mut label = [0_u8; 128];
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            label.as_mut_ptr().cast(),
            label.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        context_matches(&label[..count as usize], context),
        "only the dedicated original AppArmor revision type is evidence",
    )
}

fn counter_value(bytes: &[u8], expected: u64) -> Result<()> {
    let body = bytes
        .strip_suffix(b"\n")
        .ok_or(MacError::Rejected("complete AppArmor load revision line"))?;
    let text = std::str::from_utf8(body)
        .map_err(|_| MacError::Rejected("AppArmor load revision UTF-8"))?;
    require(
        number(text)? == expected && expected > 0,
        "protected AppArmor raw policy was resubmitted or replaced",
    )
}

fn read_counter(parent: &File, mount: u64, counter: &Counter) -> Result<File> {
    // Pin first. This fixed name is reached only from the original AAFS root
    // through the sealed birth directory, never from a caller's pathname.
    let held = aa_handle(parent, c"revision", false, false)?;
    object(&held, mount, counter.inode)?;
    let file = open_at(parent.as_raw_fd(), c"revision", libc::O_RDONLY)?;
    // An open is not evidence. Authenticate this very READ descriptor before
    // its first data read; a readable-label alias is still rejected here.
    if counter.camera {
        counter_identity_as(
            &file,
            mount,
            counter.inode,
            "u:object_r:p4_linux_camera_apparmor_revision_t:s0",
        )?;
    } else {
        counter_identity(&file, mount, counter.inode)?;
    }
    counter_value(&bounded(&file, 32)?, counter.initial)?;
    if counter.camera {
        counter_identity_as(
            &file,
            mount,
            counter.inode,
            "u:object_r:p4_linux_camera_apparmor_revision_t:s0",
        )?;
    } else {
        counter_identity(&file, mount, counter.inode)?;
    }
    object(&held, mount, counter.inode)?;
    Ok(held)
}

fn revision_allowed(has_counters: bool, original: i64, observed: i64) -> bool {
    original > 0
        && if has_counters {
            observed >= original
        } else {
            observed == original
        }
}

fn measurement_version(camera: bool, magic: Option<&str>) -> Result<u8> {
    match (camera, magic) {
        (false, Some("DLAAREV1")) => Ok(1),
        (false, Some("DLAAREV2")) => Ok(2),
        (false, Some("DLAAREV3")) | (true, Some("DLAACAM1")) => Ok(3),
        _ => Err(MacError::Rejected("unsupported boot measurement version")),
    }
}

impl BoardEpoch {
    pub(super) fn acquire(input_sha256: &str, hashes: [&str; 3]) -> Result<Self> {
        Self::acquire_selected(input_sha256, &hashes, PATH, &ROLES, &BIRTHS, false)
    }

    /// A separate one-role packet preserves the original DLAAREV3 contract.
    pub(super) fn acquire_camera(input_sha256: &str) -> Result<Self> {
        let lock: serde_json::Value = serde_json::from_slice(include_bytes!(
            "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
        ))?;
        let aa = &lock["files"]["ubuntu-apparmor.profiles"];
        let ordered = aa["board_profile_order"]
            .as_array()
            .ok_or(MacError::Rejected("ordered camera profile input missing"))?;
        let position = |name: &str| -> Result<u64> {
            let slots: Vec<_> = ordered
                .iter()
                .enumerate()
                .filter(|(_, item)| item.as_str() == Some(name))
                .map(|(i, _)| i as u64)
                .collect();
            require(slots.len() == 1, "one selected camera epoch role")?;
            Ok(slots[0])
        };
        let birth = BIRTHS[0]
            .checked_sub(position(ROLES[0])?)
            .and_then(|first| first.checked_add(position("droidloom-camera-capture").ok()?))
            .ok_or(MacError::Rejected("camera raw generation overflow"))?;
        let hash = aa["board_profiles"]["droidloom-camera-capture"]["kernel_profile_sha256"]
            .as_str()
            .ok_or(MacError::Rejected("camera kernel profile digest absent"))?;
        Self::acquire_selected(
            input_sha256,
            &[hash],
            "/run/droidloom-early/kernel-policy/camera-apparmor-epoch",
            &["droidloom-camera-capture"],
            &[birth],
            true,
        )
    }

    fn acquire_selected(
        input_sha256: &str,
        hashes: &[&str],
        path: &'static str,
        names: &'static [&'static str],
        births: &[u64],
        camera: bool,
    ) -> Result<Self> {
        require(
            hashes.len() == names.len() && births.len() == names.len(),
            "fixed epoch role vectors",
        )?;
        let (seal, data) = Sealed::read(path, 4096)?;
        packet_file(&seal.file)?;
        let body = std::str::from_utf8(&data)
            .map_err(|_| MacError::Rejected("invalid boot measurement bytes"))?;
        require(
            body.ends_with('\n') && !body.contains('\r'),
            "complete Linux boot measurement",
        )?;
        let mut lines = body.split_terminator('\n');
        let version = measurement_version(camera, lines.next())?;
        let board_lock: serde_json::Value = serde_json::from_slice(include_bytes!(
            "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
        ))?;
        let [boot, revision, mount, root, profiles] = row(lines.next())?;
        require(valid_boot(boot), "valid original Linux boot identity")?;
        let original = i64::try_from(number(revision)?)
            .map_err(|_| MacError::Rejected("AppArmor revision overflow"))?;
        let mut roles = Vec::with_capacity(names.len());
        for (index, (name, expected)) in names.iter().zip(hashes.iter().copied()).enumerate() {
            let line = lines
                .next()
                .ok_or(MacError::Rejected("missing original role"))?;
            let fields: Vec<_> = line.split(' ').collect();
            let width = match version {
                1 => 6,
                2 => 10,
                _ => 12,
            };
            require(fields.len() == width, "exact boot role measurement width")?;
            let [directory, hash, dir, key, mode, sum]: [&str; 6] = fields[..6].try_into().unwrap();
            let raw = if version >= 2 {
                let [birth, compiled, raw_bytes, raw_hash]: [&str; 4] =
                    fields[6..10].try_into().unwrap();
                let expected_raw = &board_lock["files"]["ubuntu-apparmor.profiles"]["board_profiles"]
                    [*name]["compiled_sha256"];
                require(
                    digest(compiled)
                        && expected_raw.as_str() == Some(compiled)
                        && number(birth)? <= number(revision)?,
                    "selected original kernel-exported profile bytes",
                )?;
                let counter = if version == 3 {
                    let birth_number = number(birth)?;
                    let initial = number(fields[11])?;
                    require(
                        birth_number == births[index]
                            && initial == birth_number + 1
                            && initial <= number(revision)?,
                        "original fixed early profile load counter",
                    )?;
                    let inode = number(fields[10])?;
                    require(inode != 0, "nonzero original counter inode")?;
                    Some(Counter {
                        inode,
                        initial,
                        camera,
                    })
                } else {
                    None
                };
                Some(RawProfile {
                    generation: CString::new(birth)
                        .map_err(|_| MacError::Rejected("invalid raw policy generation"))?,
                    bytes_inode: number(raw_bytes)?,
                    hash_inode: number(raw_hash)?,
                    counter,
                })
            } else {
                None
            };
            let suffix = directory
                .strip_prefix(name)
                .and_then(|x| x.strip_prefix('.'))
                .ok_or(MacError::Rejected("unselected AppArmor directory"))?;
            require(
                !suffix.is_empty()
                    && suffix.len() <= 20
                    && suffix.bytes().all(|v| v.is_ascii_digit())
                    && digest(expected)
                    && hash == expected,
                "original loaded profile and pinned digest",
            )?;
            roles.push(Role {
                directory: CString::new(directory)
                    .map_err(|_| MacError::Rejected("invalid profile name"))?,
                inode: [number(dir)?, number(key)?, number(mode)?, number(sum)?],
                raw,
            });
        }
        let [footer, input, sequence, enforce, load] = row(lines.next())?;
        require(
            footer == "SELINUX1"
                && digest(input_sha256)
                && input == input_sha256
                && enforce == "1"
                && load == "1"
                && lines.next().is_none(),
            "first joint SELinux input and enforcement",
        )?;
        let security = open_absolute(
            "/sys/kernel/security/apparmor",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let current = aa_revision(&security)?;
        require(
            revision_allowed(version == 3, original, current),
            "AppArmor advance requires sealed original raw-load counters",
        )?;
        let root_handle = aa_handle(&security, c"policy", true, true)?;
        object(&root_handle, number(mount)?, number(root)?)?;
        let mut entry = Self {
            seal,
            boot: boot.to_owned(),
            revision: current,
            boot_revision: original,
            selinux_sequence: u32::try_from(number(sequence)?)
                .map_err(|_| MacError::Rejected("SELinux sequence overflow"))?,
            policyload: 1,
            mount: number(mount)?,
            root: number(root)?,
            profiles: number(profiles)?,
            roles,
            path,
            names,
            root_handle,
            held: Vec::new(),
        };
        entry.held = entry.observe(current)?;
        entry.revalidate()?;
        Ok(entry)
    }

    pub(super) fn has_counters(&self) -> bool {
        self.roles
            .iter()
            .all(|r| r.raw.as_ref().is_some_and(|raw| raw.counter.is_some()))
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        self.revalidate_at(self.revision)
    }

    pub(super) fn revalidate_at(&self, current: i64) -> Result<()> {
        self.observe(current).map(|_| ())
    }

    fn observe(&self, current: i64) -> Result<Vec<File>> {
        require(
            revision_allowed(self.has_counters(), self.boot_revision, current)
                && current >= self.revision,
            "original monotonic AppArmor operation epoch",
        )?;
        self.seal.revalidate()?;
        let path = open_absolute(self.path, libc::O_RDONLY)?;
        packet_file(&path)?;
        let boot = kernel_text("/proc/sys/kernel/random/boot_id", PROC_MAGIC, 64)?;
        require(
            boot.strip_suffix('\n').unwrap_or(&boot) == self.boot,
            "boot epoch changed",
        )?;
        let security = open_absolute(
            "/sys/kernel/security/apparmor",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        require(
            kind(&security)? == SECURITYFS_MAGIC
                && aa_read(&security, c".ns_level", SECURITYFS_MAGIC, 16)? == b"0\n"
                && aa_read(&security, c".ns_stacked", SECURITYFS_MAGIC, 16)? == b"no\n"
                && aa_revision(&security)? == current,
            "initial AppArmor namespace and current operation revision",
        )?;
        let selinux = open_absolute(SELINUX_ROOT, libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            kind(&selinux)? == SELINUX_MAGIC,
            "original SELinux filesystem",
        )?;
        let status = StatusMap::open(&selinux)?;
        let first = status.read()?;
        require(
            first.sequence == self.selinux_sequence && first.policyload == self.policyload,
            "joint SELinux load differs from the witnessed first load",
        )?;
        let ns = aa_handle(&security, c"policy", true, true)?;
        object(&ns, self.mount, self.root)?;
        object(&self.root_handle, self.mount, self.root)?;
        // Every member walk starts from the held initial namespace, even after
        // checking that the caller's fixed kernel magic link still names it.
        let profiles = aa_handle(&self.root_handle, c"profiles", true, false)?;
        object(&profiles, self.mount, self.profiles)?;
        let modes = aa_read(&security, c"profiles", SECURITYFS_MAGIC, 1024 * 1024)?;
        let modes = std::str::from_utf8(&modes)
            .map_err(|_| MacError::Rejected("invalid active AppArmor list"))?;
        let mut held = Vec::new();
        for (role, name) in self.roles.iter().zip(self.names.iter().copied()) {
            let line = format!("{name} (enforce)");
            require(
                modes.lines().filter(|v| *v == line).count() == 1,
                "selected active enforcing profile",
            )?;
            let directory = aa_handle(&profiles, &role.directory, true, false)?;
            object(&directory, self.mount, role.inode[0])?;
            if let Some(raw) = &role.raw {
                let store = aa_handle(&self.root_handle, c"raw_data", true, false)?;
                let birth = aa_handle(&store, &raw.generation, true, false)?;
                for (link, member, inode) in [
                    (c"raw_data", c"raw_data", raw.bytes_inode),
                    (c"raw_sha256", c"sha256", raw.hash_inode),
                ] {
                    let live = aa_handle(&directory, link, false, true)?;
                    let original = aa_handle(&birth, member, false, false)?;
                    object(&live, self.mount, inode)?;
                    object(&original, self.mount, inode)?;
                    held.push(live);
                    held.push(original);
                }
                if let Some(counter) = &raw.counter {
                    held.push(read_counter(&birth, self.mount, counter)?);
                }
                held.push(birth);
                held.push(store);
            }
            for (field, ino) in [c"name", c"mode", c"sha256"]
                .into_iter()
                .zip(&role.inode[1..])
            {
                let file = aa_handle(&directory, field, false, false)?;
                object(&file, self.mount, *ino)?;
                held.push(file);
            }
            held.push(directory);
        }
        held.push(profiles);
        held.push(ns);
        self.seal.revalidate()?;
        require(
            status.read()? == first && aa_revision(&security)? == current,
            "security policy changed during boot measurement verification",
        )?;
        Ok(held)
    }
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    #[test]
    fn camera_and_original_epoch_packets_cannot_substitute_for_each_other() {
        assert_eq!(measurement_version(true, Some("DLAACAM1")).unwrap(), 3);
        for (magic, version) in [("DLAAREV1", 1), ("DLAAREV2", 2), ("DLAAREV3", 3)] {
            assert_eq!(measurement_version(false, Some(magic)).unwrap(), version);
            assert!(measurement_version(true, Some(magic)).is_err());
        }
        assert!(measurement_version(false, Some("DLAACAM1")).is_err());
        for magic in [
            None,
            Some("DLAACAM2"),
            Some("DLAACAM1 "),
            Some("DLAAREV3\r"),
        ] {
            assert!(measurement_version(true, magic).is_err());
            assert!(measurement_version(false, magic).is_err());
        }
    }
    #[test]
    fn only_counter_sealed_epochs_accept_unrelated_monotonic_changes() {
        assert!(revision_allowed(true, 167, 200));
        assert!(revision_allowed(true, 167, 167));
        for legacy in [false] {
            assert!(revision_allowed(legacy, 167, 167));
            assert!(!revision_allowed(legacy, 167, 168));
        }
        assert!(!revision_allowed(true, 167, 166));
        assert!(!revision_allowed(true, 0, 0));
    }
    #[test]
    fn raw_counter_rejects_reloads_aba_and_noncanonical_lines() {
        assert!(counter_value(b"165\n", 165).is_ok());
        for bytes in [
            b"169\n".as_slice(),
            b"171\n",
            b"164\n",
            b"0165\n",
            b"165",
            b" 165\n",
            b"+165\n",
            b"-165\n",
            b"165\n165\n",
            b"18446744073709551616\n",
            b"\n",
        ] {
            assert!(counter_value(bytes, 165).is_err());
        }
    }

    #[test]
    fn readable_non_apparmor_descriptor_is_rejected_before_data_read() {
        use std::io::{Seek, Write};
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(b"165\n").unwrap();
        file.rewind().unwrap();
        assert!(counter_identity(&file, 1, file.metadata().unwrap().ino()).is_err());
        assert_eq!(file.stream_position().unwrap(), 0);
    }

    /// Runs only in an isolated selected kernel with the real admitted joint
    /// policy, the real enforcing loader/broker profile, and an early V3 seal.
    #[test]
    #[ignore = "requires the isolated Pocket4 target-kernel epoch fixture"]
    fn actual_joint_kernel_counter_evidence_and_aliases() {
        check_actual_joint_kernel_counter_evidence_and_aliases();
    }

    pub(crate) fn check_actual_joint_kernel_counter_evidence_and_aliases() {
        use std::io::Seek;
        let lock: serde_json::Value = serde_json::from_slice(include_bytes!(
            "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
        )).unwrap();
        let mut uts = std::mem::MaybeUninit::<libc::utsname>::uninit();
        assert_eq!(unsafe { libc::uname(uts.as_mut_ptr()) }, 0);
        let uts = unsafe { uts.assume_init() };
        assert_eq!(
            unsafe { CStr::from_ptr(uts.release.as_ptr()) }.to_bytes(),
            lock["kernel"]["release"].as_str().unwrap().as_bytes()
        );
        let selected_case = std::env::var("DROIDLOOM_EPOCH_FIXTURE_CASE").unwrap();
        let case = selected_case.as_str();
        assert!(["unrelated", "samebytes", "aba", "nested"].contains(&case));
        let hashes = ROLES.map(|name| {
            lock["files"]["ubuntu-apparmor.profiles"]["board_profiles"]
            [name]["kernel_profile_sha256"].as_str().unwrap()
        });
        let result = BoardEpoch::acquire(
            lock["files"]["joint.policy"]["sha256"].as_str().unwrap(),
            hashes,
        );
        if case != "unrelated" {
            let rejection = match result {
                Err(error) => error,
                Ok(_) => panic!("changed protected policy or namespace became authority"),
            };
            let expected = match (case, &rejection) {
                (
                    "samebytes" | "aba",
                    MacError::Rejected("protected AppArmor raw policy was resubmitted or replaced"),
                ) => true,
                (
                    "aba" | "nested",
                    MacError::Rejected(
                        "original AppArmor mount and inode must match the boot measurement",
                    ),
                ) => true,
                // An A→B→A replacement may retire the original raw birth inode
                // before the second A is submitted. Its absence is rejection.
                ("aba", MacError::Io(error)) => error.raw_os_error() == Some(libc::ENOENT),
                _ => false,
            };
            assert!(
                expected,
                "unrelated failure is not a valid negative result: {rejection}"
            );
            return;
        }
        let epoch = result.unwrap();
        // The initial PID remains the kernel bootstrap role in this fixture.
        // A proc link read grant must not expose that foreign task's executable.
        let foreign = std::fs::read_link("/proc/1/exe").unwrap_err();
        assert!(matches!(
            foreign.raw_os_error(),
            Some(libc::EACCES | libc::EPERM)
        ));
        assert!(epoch.has_counters());
        assert!(epoch.revision > epoch.boot_revision);
        epoch.revalidate().unwrap();
        // These regular files deliberately have the same synthetic names as
        // authorized counters. One carries an already-readable library type.
        // Rejecting that alias is an object check, not a claimed MAC denial.
        let mut readable =
            File::open("/.droidloom-kernel-apparmorfs/raw_data/165/revision").unwrap();
        let raw = epoch.roles[1].raw.as_ref().unwrap();
        assert!(
            counter_identity(&readable, epoch.mount, raw.counter.as_ref().unwrap().inode).is_err()
        );
        assert_eq!(readable.stream_position().unwrap(), 0);
        match File::open("/.droidloom-kernel-apparmorfs/raw_data/164/revision") {
            Ok(mut default_label) => {
                assert!(
                    counter_identity(
                        &default_label,
                        epoch.mount,
                        epoch.roles[0]
                            .raw
                            .as_ref()
                            .unwrap()
                            .counter
                            .as_ref()
                            .unwrap()
                            .inode
                    )
                    .is_err()
                );
                assert_eq!(default_label.stream_position().unwrap(), 0);
            }
            Err(error) => assert_eq!(error.raw_os_error(), Some(libc::EACCES)),
        }
        // Reopening the actual object still succeeds; an alias never updates
        // the seal, the held authority, or the next counter expectation.
        epoch.revalidate().unwrap();
    }
}
