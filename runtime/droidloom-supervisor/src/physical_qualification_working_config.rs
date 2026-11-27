//! Held admission of the fixed second-stage configuration from this actual
//! working boot. Parsed JSON describes inputs; the live owner, boot arguments,
//! kernel, labels and original early publisher provide their custody.
use super::{error, f9, layout, sha};
use crate::{native_hardware_label as held, native_working_contract as contract};
use contract::{PayloadPin, WorkingEarlyConfiguration, WorkingReturnConfiguration};
use serde::Deserialize;
use std::cell::RefCell;
use std::collections::BTreeMap;
use std::ffi::{CStr, CString};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum WorkingActor {
    Parent,
    Suite,
}
impl WorkingActor {
    pub(super) fn from_role(role: &[u8]) -> Option<Self> {
        if role == layout::WORKING_PARENT_ROLE {
            Some(Self::Parent)
        } else if role == layout::WORKING_SUITE_ROLE {
            Some(Self::Suite)
        } else {
            None
        }
    }
    pub(super) fn role(self) -> &'static [u8] {
        match self {
            Self::Parent => layout::WORKING_PARENT_ROLE,
            Self::Suite => layout::WORKING_SUITE_ROLE,
        }
    }
    fn profile(self) -> &'static [u8] {
        match self {
            Self::Parent => layout::WORKING_PARENT_PROFILE,
            Self::Suite => layout::WORKING_SUITE_PROFILE,
        }
    }
}
pub(super) const CONFIG_LABEL: &[u8] = b"u:object_r:p4_linux_working_config_t:s0";
pub(super) const PLAN_LABEL: &[u8] = layout::WORKING_PLAN_FILE_LABEL;
pub(super) const EVIDENCE_DIRECTORY_LABEL: &[u8] = layout::WORKING_EVIDENCE_DIRECTORY_LABEL;
pub(super) const MATERIAL_LABEL: &[u8] = layout::WORKING_INPUT_FILE_LABEL;
const WITNESS_PATH: &str = "/run/droidloom-early/host-mount-identity.json";
const WITNESS_LABEL: &[u8] = b"u:object_r:p4_linux_host_mount_identity_t:s0";

/// A source input comparison. This data cannot construct a live working owner.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WorkingPayloadPin {
    /// Whole installed input length.
    pub bytes: u64,
    /// Whole installed input SHA-256.
    pub sha256: String,
}
impl From<&PayloadPin> for WorkingPayloadPin {
    fn from(pin: &PayloadPin) -> Self {
        Self {
            bytes: pin.bytes,
            sha256: pin.sha256.clone(),
        }
    }
}
/// Read-only source comparisons exposed by an already authenticated owner.
/// A caller-created value of this type grants no ownership or completion.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct WorkingSourcePins {
    /// Distinct second-stage candidate.
    pub candidate_id: String,
    /// Exact normal boot intent.
    pub intent_sha256: String,
    /// Ordinary admitted-material manifest commitment.
    pub admitted_materials_sha256: String,
    /// Shared enforcing policy commitment from the original early publisher.
    pub joint_policy_sha256: String,
    /// Normal host source commit.
    pub host_source_commit: String,
    /// Normal host source tree.
    pub host_source_tree: String,
    /// Installed applications executable.
    pub applications: WorkingPayloadPin,
    /// Installed selected release.
    pub selection: WorkingPayloadPin,
    /// Normal maintenance installation descriptor.
    pub installation: WorkingPayloadPin,
    /// Normal cell descriptor.
    pub cell: WorkingPayloadPin,
}
impl From<&WorkingReturnConfiguration> for WorkingSourcePins {
    fn from(c: &WorkingReturnConfiguration) -> Self {
        Self {
            candidate_id: c.candidate_id.clone(),
            intent_sha256: c.intent_sha256.clone(),
            admitted_materials_sha256: c.admitted_materials_sha256.clone(),
            joint_policy_sha256: c.joint_policy_sha256.clone(),
            host_source_commit: c.host_source_commit.clone(),
            host_source_tree: c.host_source_tree.clone(),
            applications: (&c.applications).into(),
            selection: (&c.selection).into(),
            installation: (&c.installation).into(),
            cell: (&c.cell).into(),
        }
    }
}

fn filesystem(file: &File, magic: libc::c_long) -> io::Result<()> {
    let mut value = std::mem::MaybeUninit::<libc::statfs>::uninit();
    // SAFETY: file is held and value is correctly sized writable storage.
    if unsafe { libc::fstatfs(file.as_raw_fd(), value.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    if unsafe { value.assume_init() }.f_type != magic {
        return Err(error("working kernel observation is on another filesystem"));
    }
    Ok(())
}
fn kernel_text(path: &str, magic: libc::c_long, limit: u64) -> io::Result<String> {
    let mut file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
        .open(path)?;
    filesystem(&file, magic)?;
    let mut bytes = Vec::new();
    (&mut file).take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit || bytes.contains(&0) {
        return Err(error(
            "working kernel observation exceeds its exact text bound",
        ));
    }
    String::from_utf8(bytes)
        .map(|text| text.trim_end_matches('\n').to_owned())
        .map_err(|_| error("working kernel observation is not UTF-8"))
}
fn kernel_release() -> io::Result<String> {
    let mut value = std::mem::MaybeUninit::<libc::utsname>::uninit();
    // SAFETY: uname writes the complete fixed-size structure on success.
    if unsafe { libc::uname(value.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error());
    }
    let value = unsafe { value.assume_init() };
    // SAFETY: the successful uname ABI terminates each fixed array with NUL.
    unsafe { CStr::from_ptr(value.release.as_ptr()) }
        .to_str()
        .map(str::to_owned)
        .map_err(|_| error("working uname release is not UTF-8"))
}
pub(super) fn current_actor() -> io::Result<WorkingActor> {
    let actor = WorkingActor::from_role(&held::current(101)?)
        .ok_or_else(|| error("working qualification has neither fixed parent nor suite actor"))?;
    require_actor(actor)?;
    Ok(actor)
}
pub(super) fn require_actor(actor: WorkingActor) -> io::Result<()> {
    if held::current(101)? != actor.role()
        || held::current(104)? != actor.profile()
        || kernel_release()? != contract::KERNEL
        || kernel_text("/sys/fs/selinux/enforce", 0xf97cff8c, 8)? != "1"
    {
        return Err(error(
            "working actor lost its separate enforcing SELinux and AppArmor entry",
        ));
    }
    Ok(())
}

struct SourceInput {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
    digest: String,
    label: &'static [u8],
    parents: Vec<(PathBuf, File, [u64; 9])>,
}
impl SourceInput {
    fn open(
        path: &Path,
        expected: Option<&str>,
        limit: u64,
        label: &'static [u8],
    ) -> io::Result<Self> {
        if !path.is_absolute() || path.canonicalize()? != path {
            return Err(error("working source input alias"));
        }
        let mut parents = Vec::new();
        for parent in path
            .parent()
            .ok_or_else(|| error("working source parent absent"))?
            .ancestors()
        {
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
                .open(parent)?;
            let pin = f9(&file)?;
            if pin[2] & libc::S_IFMT as u64 != libc::S_IFDIR as u64
                || pin[3..5] != [0, 0]
                || pin[2] & 0o022 != 0
            {
                return Err(error("working source parent is not root protected"));
            }
            parents.push((parent.into(), file, pin));
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(path)?;
        let pin = f9(&file)?;
        if pin[2] != u64::from(libc::S_IFREG | 0o400)
            || pin[3..6] != [0, 0, 1]
            || pin[6] == 0
            || pin[6] > limit
            || held::label(&file)? != label
        {
            return Err(error(
                "working source input metadata or original publisher label differs",
            ));
        }
        let mut bytes = vec![0; pin[6] as usize];
        crate::control::physical_qualification_channel::working_runtime::read_exact_at_progress(
            &file, &mut bytes, 0,
        )?;
        if file.read_at(&mut [0; 1], pin[6])? != 0 || f9(&file)? != pin {
            return Err(error(
                "working source input changed during its first complete read",
            ));
        }
        let digest = sha(&bytes);
        if expected.is_some_and(|expected| expected != digest) {
            return Err(error(
                "working source input differs from its actual kernel boot pin",
            ));
        }
        let value = Self {
            path: path.into(),
            file,
            pin,
            digest,
            label,
            parents,
        };
        value.guard()?;
        Ok(value)
    }
    fn guard_parents(&self) -> io::Result<()> {
        for (path, file, pin) in &self.parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
                .open(path)?;
            if f9(file)?[..5] != pin[..5] || f9(&named)?[..5] != pin[..5] {
                return Err(error("working source input parent changed"));
            }
        }
        Ok(())
    }
    fn bytes(&self) -> io::Result<Vec<u8>> {
        self.guard_parents()?;
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK)
            .open(&self.path)?;
        if f9(&self.file)? != self.pin
            || f9(&named)? != self.pin
            || held::label(&self.file)? != self.label
            || held::label(&named)? != self.label
        {
            return Err(error("held working source input changed"));
        }
        let mut bytes = vec![0; self.pin[6] as usize];
        crate::control::physical_qualification_channel::working_runtime::read_exact_at_progress(
            &self.file, &mut bytes, 0,
        )?;
        if self.file.read_at(&mut [0; 1], self.pin[6])? != 0
            || sha(&bytes) != self.digest
            || f9(&self.file)? != self.pin
            || f9(&named)? != self.pin
        {
            return Err(error("held whole working source input changed"));
        }
        self.guard_parents()?;
        Ok(bytes)
    }
    fn guard(&self) -> io::Result<()> {
        self.bytes().map(|_| ())
    }
}

fn bind_boot(
    config: &WorkingReturnConfiguration,
    args: &BTreeMap<String, String>,
    boot: &str,
    release: &str,
) -> io::Result<()> {
    config.validate()?;
    if args.get("droidloom.working") != Some(&config.intent_sha256)
        || args.get("droidloom.working.config") != Some(&config.early_config_sha256)
        || release != contract::KERNEL
        || !contract::uuid(boot)
        || boot == config.original_boot_id
    {
        return Err(error(
            "working configuration is not bound to this fresh selected-kernel boot",
        ));
    }
    Ok(())
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

/// Retain an exact root-private directory and its finite normal MAC type.
/// Child entries may be created; those writes never change the retained inode,
/// owner, mode or label and do not excuse replacement of the named directory.
struct TypedDirectory {
    path: PathBuf,
    file: File,
    stable: [u64; 5],
    label: &'static [u8],
}
impl TypedDirectory {
    fn open(path: &Path, label: &'static [u8]) -> io::Result<Self> {
        if !path.is_absolute() || path.canonicalize()? != path {
            return Err(error("working directory alias"));
        }
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(path)?;
        let pin = f9(&file)?;
        if pin[2] != u64::from(libc::S_IFDIR | 0o700)
            || pin[3..5] != [0, 0]
            || held::label(&file)? != label
        {
            return Err(error(
                "working directory owner, mode or finite label differs",
            ));
        }
        let result = Self {
            path: path.into(),
            file,
            stable: pin[..5]
                .try_into()
                .map_err(|_| error("directory identity"))?,
            label,
        };
        result.guard()?;
        Ok(result)
    }
    fn guard(&self) -> io::Result<()> {
        if self.path.canonicalize()? != self.path {
            return Err(error("working directory alias appeared"));
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(&self.path)?;
        if f9(&self.file)?[..5] != self.stable
            || f9(&named)?[..5] != self.stable
            || held::label(&self.file)? != self.label
            || held::label(&named)? != self.label
        {
            return Err(error(
                "held working directory inode or finite label changed",
            ));
        }
        Ok(())
    }
}

pub(super) struct AdmittedWorkingConfiguration {
    actor: WorkingActor,
    installed_directories: [TypedDirectory; 2],
    config: WorkingReturnConfiguration,
    comparisons: WorkingSourcePins,
    runtime_directory: PathBuf,
    input_directory: PathBuf,
    inputs: [SourceInput; 4],
    boot_id: String,
    command_line: String,
    process: u32,
    mount_namespace: File,
    namespace_identity: (u64, u64),
}
impl AdmittedWorkingConfiguration {
    pub(super) fn acquire() -> io::Result<Self> {
        let actor = current_actor()?;
        let command_line = kernel_text("/proc/cmdline", libc::PROC_SUPER_MAGIC, 32768)?;
        let args = contract::boot_arguments(&command_line)?;
        let input = SourceInput::open(
            Path::new(contract::RETURN_CONFIG),
            Some(&args["droidloom.working.return"]),
            65536,
            CONFIG_LABEL,
        )?;
        let config: WorkingReturnConfiguration = serde_json::from_slice(&input.bytes()?)?;
        let boot_id = kernel_text(
            "/proc/sys/kernel/random/boot_id",
            libc::PROC_SUPER_MAGIC,
            64,
        )?;
        bind_boot(&config, &args, &boot_id, &kernel_release()?)?;
        let early_input = SourceInput::open(
            Path::new(contract::EARLY_CONFIG),
            Some(&config.early_config_sha256),
            65536,
            CONFIG_LABEL,
        )?;
        let early: WorkingEarlyConfiguration = serde_json::from_slice(&early_input.bytes()?)?;
        early.validate()?;
        if early.intent_sha256 != config.intent_sha256
            || serde_json::to_value(&early.recovery)? != serde_json::to_value(&config.recovery)?
        {
            return Err(error(
                "working early and return inputs select different recovery contracts",
            ));
        }
        // This input is authenticated by the original early publisher's label,
        // current boot/policy and actual namespace, never by a saved pass flag.
        let witness = SourceInput::open(Path::new(WITNESS_PATH), None, 512, WITNESS_LABEL)?;
        let value: MountWitness = serde_json::from_slice(&witness.bytes()?)?;
        let mount_namespace = File::open("/proc/self/ns/mnt")?;
        filesystem(&mount_namespace, 0x6e736673)?;
        let namespace_identity = (
            mount_namespace.metadata()?.dev(),
            mount_namespace.metadata()?.ino(),
        );
        if value.schema != "droidloom.host-mount-identity.v1"
            || value.boot_id != boot_id
            || value.joint_policy_sha256 != config.joint_policy_sha256
            || (value.device, value.inode) != namespace_identity
        {
            return Err(error(
                "working boot lacks its original policy and mount-namespace publisher",
            ));
        }
        let comparisons = (&config).into();
        let runtime_directory = config.runtime_evidence_directory();
        let input_directory = runtime_directory
            .parent()
            .ok_or_else(|| error("working candidate root absent"))?
            .join(layout::WORKING_INPUT_DIRECTORY);
        let candidate = runtime_directory
            .parent()
            .ok_or_else(|| error("working candidate absent"))?;
        if layout::working_candidate_directory(&config.candidate_id).as_deref() != Some(candidate) {
            return Err(error(
                "working candidate differs from its fixed source layout",
            ));
        }
        let installed_directories = [
            TypedDirectory::open(candidate, layout::WORKING_CANDIDATE_DIRECTORY_LABEL)?,
            TypedDirectory::open(&input_directory, layout::WORKING_INPUT_DIRECTORY_LABEL)?,
        ];
        let materials = SourceInput::open(
            &input_directory.join(layout::WORKING_ADMITTED_MATERIALS_FILE),
            Some(&config.admitted_materials_sha256),
            16 * 1024 * 1024,
            MATERIAL_LABEL,
        )?;
        let result = Self {
            actor,
            installed_directories,
            config,
            comparisons,
            runtime_directory,
            input_directory,
            inputs: [input, early_input, witness, materials],
            boot_id,
            command_line,
            process: std::process::id(),
            mount_namespace,
            namespace_identity,
        };
        result.guard()?;
        Ok(result)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        require_actor(self.actor)?;
        for directory in &self.installed_directories {
            directory.guard()?;
        }
        if std::process::id() != self.process
            || kernel_text("/proc/cmdline", libc::PROC_SUPER_MAGIC, 32768)? != self.command_line
            || kernel_text(
                "/proc/sys/kernel/random/boot_id",
                libc::PROC_SUPER_MAGIC,
                64,
            )? != self.boot_id
        {
            return Err(error(
                "working input custody lost its actual process or boot",
            ));
        }
        for input in &self.inputs {
            input.guard()?;
        }
        let named = File::open("/proc/self/ns/mnt")?;
        filesystem(&named, 0x6e736673)?;
        for file in [&self.mount_namespace, &named] {
            let meta = file.metadata()?;
            if (meta.dev(), meta.ino()) != self.namespace_identity {
                return Err(error(
                    "working input custody changed its original mount namespace",
                ));
            }
        }
        Ok(())
    }
    pub(super) fn require_same_return(
        &self,
        actual: &WorkingReturnConfiguration,
    ) -> io::Result<()> {
        self.guard()?;
        if serde_json::to_value(actual)? != serde_json::to_value(&self.config)? {
            return Err(error(
                "working boot owners retained different normal return inputs",
            ));
        }
        Ok(())
    }
    pub(super) fn applications_pin(&self) -> &PayloadPin {
        &self.config.applications
    }
    pub(super) fn runtime_evidence_directory(&self) -> &Path {
        &self.runtime_directory
    }
    pub(super) fn source_pins(&self) -> &WorkingSourcePins {
        &self.comparisons
    }
    pub(super) fn schedule(&self) -> &contract::WorkingSchedule {
        &self.config.recovery.schedule
    }
    pub(super) fn input_directory(&self) -> &Path {
        &self.input_directory
    }
    pub(super) fn admitted_materials_path(&self) -> &Path {
        &self.inputs[3].path
    }
    pub(super) fn admitted_materials_pin(&self) -> (u64, &str) {
        (self.inputs[3].pin[6], &self.inputs[3].digest)
    }
}

/// Fresh runtime-only evidence. The original/returned material root is never
/// considered. A nonempty prior attempt is retained and refuses a new run.
pub(super) struct RuntimeDirectory {
    path: PathBuf,
    file: File,
    pin: [u64; 9],
    parents: Vec<(PathBuf, File, [u64; 9])>,
    children: RefCell<BTreeMap<&'static str, TypedDirectory>>,
}
impl RuntimeDirectory {
    pub(super) fn acquire(config: &AdmittedWorkingConfiguration) -> io::Result<Self> {
        config.guard()?;
        let path = config.runtime_evidence_directory().to_owned();
        let candidate = path
            .parent()
            .ok_or_else(|| error("working candidate parent absent"))?;
        let base = candidate
            .parent()
            .ok_or_else(|| error("working evidence root absent"))?;
        if base != Path::new(layout::WORKING_QUALIFICATION_BASE) || base.canonicalize()? != base {
            return Err(error(
                "working evidence is not in the fixed runtime-only root",
            ));
        }
        // Inputs already require this candidate to have been installed by the
        // normal cold producer. Retain every parent before creating any output.
        let mut parents = Vec::new();
        for parent in candidate.ancestors() {
            let file = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
                .open(parent)?;
            let pin = f9(&file)?;
            if pin[2] & libc::S_IFMT as u64 != libc::S_IFDIR as u64
                || pin[3..5] != [0, 0]
                || pin[2] & 0o022 != 0
            {
                return Err(error("working evidence parent is not protected"));
            }
            if parent == candidate && pin[2] != u64::from(libc::S_IFDIR | 0o700) {
                return Err(error(
                    "normal installed working candidate must have mode 0700",
                ));
            }
            parents.push((parent.into(), file, pin));
        }
        let parent = &parents
            .first()
            .ok_or_else(|| error("working candidate parent absent"))?
            .1;
        let name = CString::new(layout::WORKING_EVIDENCE_DIRECTORY).map_err(io::Error::other)?;
        // SAFETY: the held normal candidate and constant source leaf stay live.
        if unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o700) } != 0 {
            let e = io::Error::last_os_error();
            if e.kind() != io::ErrorKind::AlreadyExists {
                return Err(e);
            }
        }
        parent.sync_all()?;
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(&path)?;
        let pin = f9(&file)?;
        if pin[2] != u64::from(libc::S_IFDIR | 0o700)
            || pin[3..5] != [0, 0]
            || fs::read_dir(&path)?.next().is_some()
            || held::label(&file)? != EVIDENCE_DIRECTORY_LABEL
        {
            return Err(error(
                "working evidence is not a fresh correctly labelled attempt",
            ));
        }
        let result = Self {
            path,
            file,
            pin,
            parents,
            children: RefCell::new(BTreeMap::new()),
        };
        result.guard()?;
        // The suite may write its finite claim files, but cannot add children
        // to the parent-only runtime evidence directory. Create this one
        // private source-owned directory before starting any suite process.
        result.create_typed_child(
            layout::WORKING_NATIVE_CLAIMS_DIRECTORY,
            layout::WORKING_NATIVE_CLAIMS_DIRECTORY_LABEL,
        )?;
        config.guard()?;
        Ok(result)
    }
    pub(super) fn guard(&self) -> io::Result<()> {
        for (path, file, pin) in &self.parents {
            let named = OpenOptions::new()
                .read(true)
                .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
                .open(path)?;
            if f9(file)?[..5] != pin[..5] || f9(&named)?[..5] != pin[..5] {
                return Err(error("working runtime parent changed"));
            }
        }
        let named = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(&self.path)?;
        if f9(&self.file)?[..5] != self.pin[..5]
            || f9(&named)?[..5] != self.pin[..5]
            || held::label(&self.file)? != EVIDENCE_DIRECTORY_LABEL
            || held::label(&named)? != EVIDENCE_DIRECTORY_LABEL
        {
            return Err(error("working runtime evidence directory changed"));
        }
        for child in self.children.borrow().values() {
            child.guard()?;
        }
        Ok(())
    }
    pub(super) fn path(&self) -> &Path {
        &self.path
    }
    pub(super) fn create_child(&self, name: &'static str) -> io::Result<PathBuf> {
        let label = layout::preparation_directory_label(name)
            .ok_or_else(|| error("working preparation has no such source directory"))?;
        self.create_typed_child(name, label)
    }
    fn create_typed_child(&self, name: &'static str, label: &'static [u8]) -> io::Result<PathBuf> {
        self.guard()?;
        if self.children.borrow().contains_key(name) {
            return Err(error("working preparation directory was already created"));
        }
        let name_c = CString::new(name).map_err(io::Error::other)?;
        // SAFETY: the held directory and fixed NUL-terminated source leaf are live.
        if unsafe { libc::mkdirat(self.file.as_raw_fd(), name_c.as_ptr(), 0o700) } != 0 {
            return Err(io::Error::last_os_error());
        }
        let path = self.path.join(name);
        let child = TypedDirectory::open(&path, label)?;
        self.children.borrow_mut().insert(name, child);
        self.file.sync_all()?;
        self.guard()?;
        Ok(path)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn configuration() -> WorkingReturnConfiguration {
        let pin = PayloadPin {
            bytes: 4096,
            sha256: "a".repeat(64),
        };
        WorkingReturnConfiguration {
            schema: "droidloom.working-qualification-return.v1".into(),
            intent_sha256: "b".repeat(64),
            candidate_id: "c".repeat(64),
            first_once_candidate: "d".repeat(64),
            original_boot_id: "00000000-0000-0000-0000-000000000001".into(),
            original_kernel: contract::ORIGINAL_KERNEL.into(),
            original_entry: contract::ORIGINAL_ENTRY.into(),
            root_uuid: contract::ROOT_UUID.into(),
            early_config_sha256: "e".repeat(64),
            admitted_materials_sha256: "f".repeat(64),
            joint_policy_sha256: "1".repeat(64),
            host_source_commit: "2".repeat(40),
            host_source_tree: "3".repeat(40),
            recovery: contract::WorkingBootSpec {
                schema: "droidloom.working-qualification-boot.v1".into(),
                kind: contract::KIND.into(),
                candidate_id: "c".repeat(64),
                first_once_candidate: "d".repeat(64),
                helper_bytes: 4096,
                helper_sha256: "4".repeat(64),
                kernel_release: contract::KERNEL.into(),
                kernel_sha256: contract::KERNEL_SHA.into(),
                kernel_config_sha256: contract::CONFIG_SHA.into(),
                module_relative: contract::MODULE_REL.into(),
                module_bytes: contract::MODULE_BYTES,
                module_sha256: contract::MODULE_SHA.into(),
                panic_seconds: contract::PANIC_SECONDS,
                schedule: contract::WorkingSchedule::selected(),
            },
            executable: pin.clone(),
            applications: pin.clone(),
            maintenance: pin.clone(),
            installation: pin.clone(),
            cell: pin.clone(),
            selection: pin,
        }
    }
    #[test]
    fn physical_working_configuration_distinguishes_candidate_and_original_boot() {
        let c = configuration();
        let args = BTreeMap::from([
            ("droidloom.working".into(), c.intent_sha256.clone()),
            (
                "droidloom.working.config".into(),
                c.early_config_sha256.clone(),
            ),
        ]);
        let boot = "00000000-0000-0000-0000-000000000002";
        bind_boot(&c, &args, boot, contract::KERNEL).unwrap();
        assert!(bind_boot(&c, &args, &c.original_boot_id, contract::KERNEL).is_err());
        assert!(bind_boot(&c, &args, boot, contract::ORIGINAL_KERNEL).is_err());
        let mut wrong = args.clone();
        wrong.insert("droidloom.working".into(), "9".repeat(64));
        assert!(bind_boot(&c, &wrong, boot, contract::KERNEL).is_err());
        let mut wrong = args;
        wrong.insert("droidloom.working.config".into(), "9".repeat(64));
        assert!(bind_boot(&c, &wrong, boot, contract::KERNEL).is_err());
    }
    #[test]
    fn physical_working_runtime_plan_stays_outside_original_returned_materials() {
        let c = configuration();
        c.validate().unwrap();
        assert_eq!(
            c.runtime_evidence_directory(),
            Path::new("/var/lib/droidloom/qualification")
                .join(format!("working-qualification-{}", c.candidate_id))
                .join("runtime-evidence")
        );
        assert!(
            !c.runtime_evidence_directory()
                .starts_with("/var/lib/droidloom-qualification")
        );
        let data = WorkingSourcePins::from(&c);
        assert_eq!(data.applications.bytes, c.applications.bytes);
        assert_eq!(data.applications.sha256, c.applications.sha256);
        assert_eq!(data.selection.sha256, c.selection.sha256);
    }
}
