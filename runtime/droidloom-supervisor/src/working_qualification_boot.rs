//! Fixed live inputs for the returned working-copy qualification boot.
//! A configuration alone is a comparison document. This owner additionally
//! retains the actual installed applications ELF, original host namespace,
//! enforcing selected kernel and this fresh boot's command-line commitments.
use crate::control::MainCustodyObservation;
use crate::control::application_command::application_leaf_unit::qualification::retirement::capabilities as return_caps;
use crate::main_custody::RuntimeMainCustody;
use crate::{native_hardware_label as held, native_working_contract as c};
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    ffi::CString,
    fs::{self, File, OpenOptions},
    io,
    os::{
        fd::AsRawFd,
        unix::{
            ffi::OsStrExt,
            fs::{FileExt, MetadataExt, OpenOptionsExt},
        },
    },
    path::{Path, PathBuf},
};
#[derive(Clone, Copy, Eq, PartialEq)]
enum EntryRole {
    Parent,
    Return,
}
impl EntryRole {
    fn role(self) -> &'static [u8] {
        match self {
            Self::Parent => c::layout::WORKING_PARENT_ROLE,
            Self::Return => c::layout::WORKING_RETURN_ROLE,
        }
    }
    fn profile(self) -> &'static [u8] {
        match self {
            Self::Parent => c::layout::WORKING_PARENT_PROFILE,
            Self::Return => c::layout::WORKING_RETURN_PROFILE,
        }
    }
}

const CONFIG_LABEL: &[u8] = b"u:object_r:p4_linux_working_config_t:s0";
const WITNESS: &str = "/run/droidloom-early/host-mount-identity.json";
fn reject(why: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::PermissionDenied, why)
}
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
#[derive(Clone, Debug, Eq, PartialEq)]
struct Node {
    stable: [u64; 7],
    modified: [i64; 2],
    changed: [i64; 2],
}
impl Node {
    fn from(m: &fs::Metadata) -> Self {
        Self {
            stable: [
                m.dev(),
                m.ino(),
                u64::from(m.mode()),
                u64::from(m.uid()),
                u64::from(m.gid()),
                m.nlink(),
                m.len(),
            ],
            modified: [m.mtime(), m.mtime_nsec()],
            changed: [m.ctime(), m.ctime_nsec()],
        }
    }
    fn of(file: &File) -> io::Result<Self> {
        Ok(Self::from(&file.metadata()?))
    }
}
fn node_f9(node: &Node) -> io::Result<[u64; 9]> {
    let ns = |pair: [i64; 2]| {
        u64::try_from(i128::from(pair[0]) * 1_000_000_000 + i128::from(pair[1]))
            .map_err(|_| reject("working normal input timestamp is outside the source range"))
    };
    let mut value = [0; 9];
    value[..7].copy_from_slice(&node.stable);
    value[7] = ns(node.modified)?;
    value[8] = ns(node.changed)?;
    Ok(value)
}
fn root_directory(path: &Path) -> io::Result<File> {
    if !path.is_absolute() {
        return Err(reject("working boot path must be absolute"));
    }
    let mut root = held::path_at(libc::AT_FDCWD, c"/")?;
    held::directory(&root)?;
    for part in path.components().skip(1) {
        let std::path::Component::Normal(part) = part else {
            return Err(reject("working boot path is not canonical"));
        };
        root = held::path_at(
            root.as_raw_fd(),
            &CString::new(part.as_bytes()).map_err(io::Error::other)?,
        )?;
        held::directory(&root)?;
    }
    Ok(root)
}
fn filesystem(file: &File, magic: libc::c_long) -> io::Result<()> {
    let mut info = std::mem::MaybeUninit::<libc::statfs>::uninit();
    // SAFETY: full statfs output storage and the held input descriptor.
    if unsafe { libc::fstatfs(file.as_raw_fd(), info.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { info.assume_init() }.f_type != magic {
        return Err(reject("working boot filesystem differs"));
    }
    Ok(())
}
fn text(path: &str, limit: usize) -> io::Result<String> {
    let file = File::open(path)?;
    let mut bytes = vec![0; limit + 1];
    let n = file.read_at(&mut bytes, 0)?;
    if n > limit {
        return Err(reject("working boot public observation exceeds bound"));
    }
    let v = std::str::from_utf8(&bytes[..n])
        .map_err(|_| reject("working boot observation is not UTF-8"))?;
    Ok(v.trim_end_matches(['\n', '\0']).into())
}
struct Input {
    path: PathBuf,
    file: File,
    node: Node,
    pin: c::PayloadPin,
    parents: Vec<(PathBuf, File, [u64; 5])>,
    label: Option<&'static [u8]>,
}
impl Input {
    fn open(
        path: &Path,
        pin: &c::PayloadPin,
        modes: &[u32],
        label: Option<&'static [u8]>,
    ) -> io::Result<Self> {
        pin.validate(128 * 1024 * 1024)?;
        let mut parents = Vec::new();
        for parent in path
            .parent()
            .ok_or_else(|| reject("working input parent absent"))?
            .ancestors()
        {
            let file = root_directory(parent)?;
            let stable = Node::of(&file)?.stable;
            let identity = stable[..5]
                .try_into()
                .map_err(|_| reject("working input parent identity"))?;
            parents.push((parent.into(), file, identity));
        }
        let parent = root_directory(
            path.parent()
                .ok_or_else(|| reject("working input parent absent"))?,
        )?;
        let leaf = CString::new(
            path.file_name()
                .ok_or_else(|| reject("working input leaf absent"))?
                .as_bytes(),
        )
        .map_err(io::Error::other)?;
        let descriptor = held::path_at(parent.as_raw_fd(), &leaf)?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(path)?;
        let node = Node::of(&file)?;
        if node != Node::of(&descriptor)?
            || node.stable[2] & u64::from(libc::S_IFMT) != u64::from(libc::S_IFREG)
            || !modes.contains(&((node.stable[2] as u32) & 0o7777))
            || node.stable[3..6] != [0, 0, 1]
            || node.stable[6] != pin.bytes
        {
            return Err(reject("working input is not its exact normal root inode"));
        }
        let value = Self {
            path: path.into(),
            file,
            node,
            pin: pin.clone(),
            parents,
            label,
        };
        value.bytes()?;
        Ok(value)
    }
    fn guard(&self) -> io::Result<()> {
        for (path, file, pin) in &self.parents {
            let named = root_directory(path)?;
            if Node::of(file)?.stable[..5] != *pin || Node::of(&named)?.stable[..5] != *pin {
                return Err(reject("working input held root parent changed"));
            }
        }
        let parent = root_directory(
            self.path
                .parent()
                .ok_or_else(|| reject("working input parent changed"))?,
        )?;
        let leaf = CString::new(
            self.path
                .file_name()
                .ok_or_else(|| reject("working input leaf changed"))?
                .as_bytes(),
        )
        .map_err(io::Error::other)?;
        let named = held::path_at(parent.as_raw_fd(), &leaf)?;
        if Node::of(&named)? != self.node || Node::of(&self.file)? != self.node {
            return Err(reject("working input held/named identity changed"));
        }
        if let Some(label) = self.label {
            if held::label(&named)? != label || held::label(&self.file)? != label {
                return Err(reject("working input normal MAC label changed"));
            }
        }
        Ok(())
    }
    fn bytes(&self) -> io::Result<Vec<u8>> {
        self.guard()?;
        let mut raw = vec![0; self.pin.bytes as usize];
        super::read_exact_at_progress(&self.file, &mut raw, 0)?;
        if self.file.read_at(&mut [0u8; 1], self.pin.bytes)? != 0 || sha(&raw) != self.pin.sha256 {
            return Err(reject("working input full body differs"));
        }
        self.guard()?;
        Ok(raw)
    }
}
fn selection_binding(selected: &Input, cell: &Input, cohort: &str, runtime: &str) -> String {
    // Exact normal ProductionSelection::package_binding byte order. The two
    // actual held inodes (including original clocks), not just JSON SHA fields,
    // must describe the same early owner's real selection.
    let mut hash = Sha256::new();
    hash.update(b"droidloom-package-selection-v1\0");
    for file in [selected, cell] {
        for n in file.node.stable {
            hash.update(n.to_le_bytes());
        }
        for n in file.node.modified.into_iter().chain(file.node.changed) {
            hash.update(n.to_le_bytes());
        }
        hash.update(file.pin.sha256.as_bytes());
    }
    hash.update(cohort.as_bytes());
    hash.update(runtime.as_bytes());
    format!("{:x}", hash.finalize())
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct MountWitness {
    schema: String,
    boot_id: String,
    joint_policy_sha256: String,
    device: u64,
    inode: u64,
}

struct ReturnInputs {
    executable: Input,
    maintenance: Input,
    installation: Input,
}
/// Opaque current-boot custody. Return construction is a separate actual MAC
/// entry; it cannot be selected by a caller-supplied role or configuration.
pub(crate) struct BootOwner {
    role: EntryRole,
    return_inputs: Option<ReturnInputs>,
    root: File,
    root_identity: [u64; 5],
    boot_id: String,
    pid: u32,
    config: c::WorkingReturnConfiguration,
    config_input: Input,
    applications: Input,
    cell: Input,
    selection: Input,
    witness: Input,
    selected: Value,
}
impl BootOwner {
    pub(super) fn open() -> io::Result<Self> {
        Self::open_role(EntryRole::Parent)
    }
    pub(crate) fn for_return() -> io::Result<Self> {
        Self::open_role(EntryRole::Return)
    }
    fn open_role(role: EntryRole) -> io::Result<Self> {
        if unsafe {
            (
                libc::getuid(),
                libc::geteuid(),
                libc::getgid(),
                libc::getegid(),
            )
        } != (0, 0, 0, 0)
            || held::current(101)? != role.role()
            || held::current(104)? != role.profile()
        {
            return Err(reject(
                "working owner requires its exact normal root and MAC entry",
            ));
        }
        let root = root_directory(Path::new("/"))?;
        filesystem(&root, 0xef53)?;
        held::namespaces(&root)?;
        let root_node = Node::of(&root)?;
        let block = fs::metadata(format!("/dev/disk/by-uuid/{}", c::ROOT_UUID))?;
        if root_node.stable[1] != 2
            || block.mode() & libc::S_IFMT != libc::S_IFBLK
            || block.rdev() != root_node.stable[0]
        {
            return Err(reject(
                "working owner is not on the original root filesystem",
            ));
        }
        let proc = root_directory(Path::new("/proc"))?;
        filesystem(&proc, 0x9fa0)?;
        if text("/proc/sys/kernel/osrelease", 256)? != c::KERNEL
            || text("/sys/fs/selinux/enforce", 8)? != "1"
        {
            return Err(reject(
                "working owner requires the selected enforcing shared kernel",
            ));
        }
        let args = c::boot_arguments(&text("/proc/cmdline", 32768)?)?;
        let size = fs::symlink_metadata(c::RETURN_CONFIG)?.len();
        if size == 0 || size > 65536 {
            return Err(reject("working boot configuration exceeds normal bound"));
        }
        let config_input = Input::open(
            Path::new(c::RETURN_CONFIG),
            &c::PayloadPin {
                bytes: size,
                sha256: args["droidloom.working.return"].clone(),
            },
            &[0o400],
            Some(CONFIG_LABEL),
        )?;
        let config: c::WorkingReturnConfiguration =
            serde_json::from_slice(&config_input.bytes()?).map_err(io::Error::other)?;
        config.validate()?;
        if args["droidloom.working"] != config.intent_sha256
            || args["droidloom.working.config"] != config.early_config_sha256
        {
            return Err(reject(
                "working root configuration differs from this boot intent",
            ));
        }
        let boot_id = text("/proc/sys/kernel/random/boot_id", 64)?;
        if !c::uuid(&boot_id) || boot_id == config.original_boot_id {
            return Err(reject("working owner did not enter a fresh H2 boot"));
        }
        let applications = Input::open(
            Path::new(c::APPLICATIONS_EXECUTABLE),
            &config.applications,
            &[0o755],
            None,
        )?;
        let return_inputs = if role == EntryRole::Return {
            return_caps::revalidate()?;
            let executable = Input::open(
                Path::new(c::RETURN_EXECUTABLE),
                &config.executable,
                &[0o755],
                None,
            )?;
            let maintenance = Input::open(
                Path::new(c::MAINTENANCE_EXECUTABLE),
                &config.maintenance,
                &[0o755],
                None,
            )?;
            let installation = Input::open(
                Path::new(c::INSTALLATION),
                &config.installation,
                &[0o400, 0o444],
                None,
            )?;
            let installed: Value =
                serde_json::from_slice(&installation.bytes()?).map_err(io::Error::other)?;
            if installed["schema"] != "droidloom-maintenance-installation-v1"
                || installed["root_uuid"] != c::ROOT_UUID
                || installed["original_kernel"] != c::ORIGINAL_KERNEL
                || installed["original_entry"] != c::ORIGINAL_ENTRY
            {
                return Err(reject(
                    "working return maintenance has another original entry",
                ));
            }
            Some(ReturnInputs {
                executable,
                maintenance,
                installation,
            })
        } else {
            None
        };
        let executing = return_inputs
            .as_ref()
            .map_or(&applications, |v| &v.executable);
        if Node::from(&fs::metadata("/proc/self/exe")?) != executing.node {
            return Err(reject(
                "working entry is not its boot-admitted normal executable",
            ));
        }
        let cell = Input::open(
            Path::new("/etc/droidloom/cell.json"),
            &config.cell,
            &[0o644],
            None,
        )?;
        let selection = Input::open(
            Path::new("/etc/droidloom/production/selected.json"),
            &config.selection,
            &[0o400],
            None,
        )?;
        let selected: Value =
            serde_json::from_slice(&selection.bytes()?).map_err(io::Error::other)?;
        let witness_parent = root_directory(
            Path::new(WITNESS)
                .parent()
                .ok_or_else(|| reject("mount witness parent absent"))?,
        )?;
        if held::label(&witness_parent)? != b"u:object_r:p4_linux_early_handoff_dir_t:s0" {
            return Err(reject(
                "working mount witness is outside its actual early publisher",
            ));
        }
        let mut raw = [0u8; 513];
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(WITNESS)?;
        let before = Node::of(&file)?;
        let count = file.read_at(&mut raw, 0)?;
        if count == 0
            || count > 512
            || before.stable[6] != count as u64
            || Node::of(&file)? != before
        {
            return Err(reject(
                "working actual mount witness changed or exceeds bound",
            ));
        }
        let witness = Input::open(
            Path::new(WITNESS),
            &c::PayloadPin {
                bytes: count as u64,
                sha256: sha(&raw[..count]),
            },
            &[0o400],
            Some(b"u:object_r:p4_linux_host_mount_identity_t:s0"),
        )?;
        let root_identity = root_node.stable[..5]
            .try_into()
            .map_err(|_| reject("root identity"))?;
        let value = Self {
            role,
            return_inputs,
            root,
            root_identity,
            boot_id,
            pid: std::process::id(),
            config,
            config_input,
            applications,
            cell,
            selection,
            witness,
            selected,
        };
        value.guard()?;
        Ok(value)
    }
    pub(crate) fn guard(&self) -> io::Result<()> {
        if self.pid != std::process::id()
            || held::current(101)? != self.role.role()
            || held::current(104)? != self.role.profile()
            || text("/proc/sys/kernel/random/boot_id", 64)? != self.boot_id
            || text("/proc/sys/kernel/osrelease", 256)? != c::KERNEL
            || text("/sys/fs/selinux/enforce", 8)? != "1"
            || Node::of(&self.root)?.stable[..5] != self.root_identity
            || Node::of(&root_directory(Path::new("/"))?)?.stable[..5] != self.root_identity
        {
            return Err(reject("working owner lost its exact boot/process/MAC/root"));
        }
        held::namespaces(&self.root)?;
        for input in [
            &self.config_input,
            &self.applications,
            &self.cell,
            &self.selection,
            &self.witness,
        ] {
            input.guard()?;
        }
        if let Some(inputs) = &self.return_inputs {
            return_caps::revalidate()?;
            for input in [
                &inputs.executable,
                &inputs.maintenance,
                &inputs.installation,
            ] {
                input.guard()?;
            }
        }
        let executing = self
            .return_inputs
            .as_ref()
            .map_or(&self.applications, |v| &v.executable);
        if Node::from(&fs::metadata("/proc/self/exe")?) != executing.node {
            return Err(reject("working normal executable changed"));
        }
        let witness: MountWitness =
            serde_json::from_slice(&self.witness.bytes()?).map_err(io::Error::other)?;
        if witness.schema != "droidloom.host-mount-identity.v1"
            || witness.boot_id != self.boot_id
            || witness.joint_policy_sha256 != self.config.joint_policy_sha256
        {
            return Err(reject(
                "working mount witness does not belong to this selected policy boot",
            ));
        }
        let actual = File::open("/proc/self/ns/mnt")?;
        filesystem(&actual, 0x6e736673)?;
        let metadata = actual.metadata()?;
        // NS_GET_NSTYPE on the same held original namespace, not setns.
        if (metadata.dev(), metadata.ino()) != (witness.device, witness.inode)
            || unsafe {
                libc::ioctl(
                    actual.as_raw_fd(),
                    0xb703 as libc::c_ulong,
                    0 as libc::c_ulong,
                )
            } != libc::CLONE_NEWNS
        {
            return Err(reject(
                "working owner left its original host mount namespace",
            ));
        }
        Ok(())
    }
    pub(super) fn compare_main(&self, main: &MainCustodyObservation) -> io::Result<()> {
        self.guard()?;
        self.compare_facts(main.facts())?;
        self.guard()
    }
    fn compare_facts(&self, main: &RuntimeMainCustody) -> io::Result<()> {
        let record = &self.selected;
        let get = |key: &str| {
            record[key]
                .as_str()
                .ok_or_else(|| reject("working selected source field absent"))
        };
        let cohort = get("base_cohort_sha256")?;
        let runtime = get("runtime_manifest_sha256")?;
        if main.epoch.boot_id != self.boot_id
            || main.owner.host_uid != 1000
            || record["host_uid"] != 1000
            || !c::digest(cohort)
            || !c::digest(runtime)
            || main.owner.base_cohort_sha256 != cohort
            || main.owner.runtime_manifest_sha256 != runtime
            || main.owner.selection_binding_sha256
                != selection_binding(&self.selection, &self.cell, cohort, runtime)
            || record["cell_spec_bytes"] != self.cell.pin.bytes
            || record["cell_spec_sha256"] != self.cell.pin.sha256
        {
            return Err(reject(
                "actual Main is not this boot's held normal selection",
            ));
        }
        let normal: crate::normal_host_release::NormalHostRelease =
            serde_json::from_value(record["normal_host_release"].clone())
                .map_err(io::Error::other)?;
        normal.validate().map_err(reject)?;
        if main.normal_host_release != normal {
            return Err(reject(
                "Main normal host release differs from this held selection",
            ));
        }
        let original: crate::native_once_contract::OriginalCopyPolicy =
            serde_json::from_value(record["persistent_data"]["original_copy"].clone())
                .map_err(io::Error::other)?;
        original.validate().map_err(io::Error::other)?;
        let actual = main
            .persistent_data
            .original_copy_origin
            .as_ref()
            .ok_or_else(|| reject("working Main has no actual source-admitted copy origin"))?;
        if actual.schema != original.schema
            || actual.working_copy_sha256 != original.working_copy_sha256
            || actual.cold_clone_sha256 != original.cold_clone_sha256
            || actual.original != original.original
            || actual.working != original.working
            || [
                main.persistent_data.backings[0].backing.stable7(),
                main.persistent_data.backings[1].backing.stable7(),
            ] != original.working
        {
            return Err(reject(
                "actual Main mounts differ from the retained returned working pair",
            ));
        }
        // Origin identity is not account contents, successful business, or
        // permanent production qualification.
        Ok(())
    }
    pub(crate) fn config(&self) -> &c::WorkingReturnConfiguration {
        &self.config
    }
    pub(crate) fn boot_id(&self) -> &str {
        &self.boot_id
    }
    pub(crate) fn require_return(&self) -> io::Result<()> {
        if self.role != EntryRole::Return || self.return_inputs.is_none() {
            return Err(reject(
                "working retirement requires the independent return entry",
            ));
        }
        self.guard()
    }
    pub(crate) fn maintenance_executable(&self) -> io::Result<&File> {
        self.require_return()?;
        Ok(&self
            .return_inputs
            .as_ref()
            .ok_or_else(|| reject("return inputs absent"))?
            .maintenance
            .file)
    }
    pub(crate) fn applications_identity(&self) -> io::Result<[u64; 9]> {
        node_f9(&self.applications.node)
    }
    /// Comparison only, used after the independent return factory has held a
    /// normal parent-only CAPTURE inode and the actual stopped PID1 invocation.
    /// It never deserializes a live MainCustodyObservation.
    pub(super) fn compare_protected_main(&self, main: &RuntimeMainCustody) -> io::Result<()> {
        self.require_return()?;
        main.validate(&main.epoch)
            .map_err(|_| reject("protected Main comparison shape differs"))?;
        self.compare_facts(main)?;
        self.guard()
    }
    pub(super) fn observation(&self) -> Value {
        json!({"schema":"droidloom.working-boot-source-custody.v1","candidate_id":self.config.candidate_id,
            "first_once_candidate":self.config.first_once_candidate,"actual_boot_id":self.boot_id,
            "host_source_commit":self.config.host_source_commit,"host_source_tree":self.config.host_source_tree,
            "admitted_materials_sha256":self.config.admitted_materials_sha256,
            "joint_policy_sha256":self.config.joint_policy_sha256,
            "applications":self.config.applications,"selection":self.config.selection,"cell":self.config.cell,
            "private_original_data_opened":false,"account_business_accepted":false,"production_ready":false})
    }
}
