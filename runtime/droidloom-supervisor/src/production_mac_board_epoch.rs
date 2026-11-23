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

struct Role {
    directory: CString,
    inode: [u64; 4],
    raw: Option<RawProfile>,
}
struct RawProfile {
    generation: CString,
    bytes_inode: u64,
    hash_inode: u64,
}

pub(super) struct BoardEpoch {
    seal: Sealed,
    pub(super) boot: String,
    pub(super) revision: i64,
    pub(super) selinux_sequence: u32,
    pub(super) policyload: u32,
    mount: u64,
    root: u64,
    profiles: u64,
    roles: [Role; 3],
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

// AppArmor's kernel-internal filesystem is outside the process mount namespace.
// Only fixed links produced by the kernel are followed. Child names have no slashes and come
// from the fixed schema. No file data is read from any disconnected object.
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

impl BoardEpoch {
    pub(super) fn acquire(input_sha256: &str, hashes: [&str; 3]) -> Result<Self> {
        let (seal, data) = Sealed::read(PATH, 4096)?;
        packet_file(&seal.file)?;
        let body = std::str::from_utf8(&data)
            .map_err(|_| MacError::Rejected("invalid boot measurement bytes"))?;
        require(
            body.ends_with('\n') && !body.contains('\r'),
            "complete Linux boot measurement",
        )?;
        let mut lines = body.split_terminator('\n');
        let raw_objects = match lines.next() {
            Some("DLAAREV1") => false,
            Some("DLAAREV2") => true,
            _ => return Err(MacError::Rejected("unsupported boot measurement version")),
        };
        let board_lock: serde_json::Value = serde_json::from_slice(include_bytes!(
            "../../../android/framework/droidloom-readiness/board-policy/pocket4-board-inputs.lock.json"
        ))?;
        let [boot, revision, mount, root, profiles] = row(lines.next())?;
        require(valid_boot(boot), "valid original Linux boot identity")?;
        let mut roles = Vec::with_capacity(3);
        for (name, expected) in ROLES.iter().zip(hashes) {
            let text = lines.next();
            let ([directory, hash, dir, key, mode, sum], raw) = if raw_objects {
                let [
                    directory,
                    hash,
                    dir,
                    key,
                    mode,
                    sum,
                    birth,
                    compiled,
                    raw_bytes,
                    raw_hash,
                ] = row(text)?;
                let expected_raw = &board_lock["files"]["ubuntu-apparmor.profiles"]["board_profiles"]
                    [*name]["compiled_sha256"];
                require(
                    digest(compiled)
                        && expected_raw.as_str() == Some(compiled)
                        && number(birth)? <= number(revision)?,
                    "selected original kernel-exported profile bytes",
                )?;
                let value = RawProfile {
                    generation: CString::new(birth)
                        .map_err(|_| MacError::Rejected("invalid raw policy generation"))?,
                    bytes_inode: number(raw_bytes)?,
                    hash_inode: number(raw_hash)?,
                };
                ([directory, hash, dir, key, mode, sum], Some(value))
            } else {
                (row(text)?, None)
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
        let original = i64::try_from(number(revision)?)
            .map_err(|_| MacError::Rejected("AppArmor revision overflow"))?;
        let security = open_absolute(
            "/sys/kernel/security/apparmor",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let current = aa_revision(&security)?;
        // A new admission may span unrelated Ubuntu reloads only when both
        // original raw profile objects are provably still selected. Existing
        // authorities keep their own stable operation generation.
        require(
            original > 0
                && if raw_objects {
                    current >= original
                } else {
                    current == original
                },
            "original AppArmor revision or its complete raw object evidence is required",
        )?;
        let entry = Self {
            seal,
            boot: boot.to_owned(),
            revision: current,
            selinux_sequence: u32::try_from(number(sequence)?)
                .map_err(|_| MacError::Rejected("SELinux sequence overflow"))?,
            policyload: 1,
            mount: number(mount)?,
            root: number(root)?,
            profiles: number(profiles)?,
            roles: roles
                .try_into()
                .map_err(|_| MacError::Rejected("three original profiles required"))?,
        };
        entry.revalidate()?;
        Ok(entry)
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        self.seal.revalidate()?;
        let path = open_absolute(PATH, libc::O_RDONLY)?;
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
                && aa_revision(&security)? == self.revision,
            "initial AppArmor namespace and captured revision",
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
        let profiles = aa_handle(&ns, c"profiles", true, false)?;
        object(&profiles, self.mount, self.profiles)?;
        let modes = aa_read(&security, c"profiles", SECURITYFS_MAGIC, 1024 * 1024)?;
        let modes = std::str::from_utf8(&modes)
            .map_err(|_| MacError::Rejected("invalid active AppArmor list"))?;
        for (role, name) in self.roles.iter().zip(ROLES) {
            let line = format!("{name} (enforce)");
            require(
                modes.lines().filter(|v| *v == line).count() == 1,
                "selected active enforcing profile",
            )?;
            let directory = aa_handle(&profiles, &role.directory, true, false)?;
            object(&directory, self.mount, role.inode[0])?;
            if let Some(raw) = &role.raw {
                let store = aa_handle(&ns, c"raw_data", true, false)?;
                let birth = aa_handle(&store, &raw.generation, true, false)?;
                for (link, member, inode) in [
                    (c"raw_data", c"raw_data", raw.bytes_inode),
                    (c"raw_sha256", c"sha256", raw.hash_inode),
                ] {
                    // The first lookup follows the live kernel profile proxy.
                    // The second completes a no-symlink walk to its unique
                    // original generation. Both must identify the same node.
                    object(
                        &aa_handle(&directory, link, false, true)?,
                        self.mount,
                        inode,
                    )?;
                    object(&aa_handle(&birth, member, false, false)?, self.mount, inode)?;
                }
            }
            for (field, ino) in [c"name", c"mode", c"sha256"]
                .into_iter()
                .zip(&role.inode[1..])
            {
                object(
                    &aa_handle(&directory, field, false, false)?,
                    self.mount,
                    *ino,
                )?;
            }
        }
        self.seal.revalidate()?;
        require(
            status.read()? == first && aa_revision(&security)? == self.revision,
            "security policy changed during boot measurement verification",
        )
    }
}
