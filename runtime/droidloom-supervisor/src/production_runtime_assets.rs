//! Fixed, descriptor-owned runtime inputs for one admitted Android cohort.
//!
//! The installed manifest is selected by a root-owned production selection.
//! Its digest is not itself an admission capability: every preparation and
//! export also requires the same live namespace witness and reservation.
//! The two base roles are a detached read-only runtime filesystem and an
//! idmapped mount of the held original Android init ELF. A manifest with
//! fixed query inputs also exports one owned read-only tmpfs containing only
//! the byte-verified cmd/toybox copies and any declared fixed Contacts ELF/JAR.
//! The JAR has no execute mode and a separate role label. No guest-supplied path is
//! opened here. The mapped child attaches only the fixed roles and reopens
//! their same inodes; it cannot clone an arbitrary host file descriptor.
//!
//! This is a child of production_mounts so its reviewed sealed-file, exact
//! loop-binding and idmapped detached-mount primitives remain private.
use super::*;
use crate::production_execution_profile::apex_inputs::ApexInput;
use std::cell::RefCell;
use std::collections::BTreeSet;

#[path = "production_runtime_apex_blocks.rs"]
mod apex_blocks;
use apex_blocks::ApexLoops;
#[path = "production_runtime_capex_custody.rs"]
mod capex_custody;
#[path = "production_runtime_native_actor.rs"]
mod native_actor;
pub(crate) use apex_blocks::{
    OriginalInitBootstrapBind, OriginalInitCleanup, OriginalInitMount, OriginalInitPropagation,
    OriginalInitPropagationKind, OriginalInitStorage, OriginalInitStorageBind,
    OriginalInitStorageBindKind, OriginalInitStorageDirectories, verify_storage_root,
};
pub(crate) use capex_custody::{
    CommittedApexdCapexCustody, RequestedDeviceCustody, RetainedApexdCapexCustody,
};
pub(crate) use native_actor::NativeMountActorGuard;

#[path = "production_runtime_activation_assets.rs"]
mod activation;
use activation::{ActivationDeclaration, ActivationResources};
#[path = "production_runtime_activation_mounts.rs"]
mod activation_mounts;
use activation_mounts::ActivationRoots;
pub(crate) use activation_mounts::{ACTIVATION_FLAGS, ActivationRootRole, verify_activation_root};
#[path = "production_runtime_execution_assets.rs"]
mod execution;
use execution::ExecutionDeclaration;
pub(crate) use execution::RuntimeExecProfile;
#[path = "production_runtime_query_assets.rs"]
mod query;
pub(crate) use activation::{
    RuntimeLinkerconfigInputs, RuntimeOriginalLinkerconfig, RuntimeTrampoline,
};
use query::{QueryDeclaration, QueryResources};
#[path = "production_runtime_native_assets.rs"]
mod native;
use native::{NativeDeclaration, NativeResources};
pub(crate) use query::{QueryLayout, QueryRole, RuntimeQueryData, RuntimeQueryExecutable};

const RUNTIME_MANIFEST_ROOT: &str = "/etc/droidloom/runtime-cohorts";
const RUNTIME_IMAGE_ROOT: &str = "/var/lib/droidloom/runtime-cohorts";
const MAX_RUNTIME_MANIFEST: u64 = 256 * 1024;
const MAX_RUNTIME_IMAGE: u64 = 16 * 1024 * 1024 * 1024;
const MAX_INIT: u64 = 32 * 1024 * 1024;
// Exact original CP3A init xattr, including its terminating NUL. A matching
// stored label is an input requirement, never proof of a MAC transition.
const ORIGINAL_INIT_SELINUX: &[u8; 24] = b"u:object_r:init_exec:s0\0";
const OPEN_TREE_CLONE: u32 = 1;
const MOUNT_ATTR_NOEXEC: u64 = 8;

pub(crate) type RuntimeError = MountError;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RuntimeDeclaration {
    schema: u32,
    scope: String,
    base_cohort_sha256: String,
    source_system: ImageDeclaration,
    runtime_image: ImageDeclaration,
    init: ImageDeclaration,
    init_source_path: String,
    init_interpreter: Option<String>,
    original_rc_inventory_sha256: String,
    reviewed_adapter_sha256: String,
    runtime_tree_inventory_sha256: String,
    apexes: Vec<ApexInput>,
    #[serde(default)]
    activation: Option<ActivationDeclaration>,
    #[serde(default)]
    query: Option<QueryDeclaration>,
    #[serde(default)]
    native_v2: Option<NativeDeclaration>,
    #[serde(default)]
    execution: Option<ExecutionDeclaration>,
}

fn safe_module_name(name: &str) -> bool {
    (3..=128).contains(&name.len())
        && !name.starts_with('.')
        && !name.ends_with('.')
        && !name.contains("..")
        && name.contains('.')
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
}

impl RuntimeDeclaration {
    fn validate(&self, cohort: &str, base: &CohortDeclaration) -> Result<()> {
        require(
            ((self.schema == 1
                && self.scope == "android_runtime_assets_v1"
                && self.native_v2.is_none())
                || (self.schema == 2
                    && self.scope == "android_runtime_assets_v2"
                    && self.native_v2.is_some()))
                && self.base_cohort_sha256 == cohort
                && is_digest(cohort)
                && base.layout == AndroidImageLayout::GsiSystemAsRoot,
            "runtime manifest must bind the admitted base cohort",
        )?;
        require(
            self.source_system.file == "system.img"
                && self.source_system.bytes == base.system.bytes
                && self.source_system.sha256 == base.system.sha256,
            "runtime inputs must originate in the selected original system image",
        )?;
        require(
            self.runtime_image.file == "runtime.img"
                && (4096..=MAX_RUNTIME_IMAGE).contains(&self.runtime_image.bytes)
                && self.runtime_image.bytes % 512 == 0
                && is_digest(&self.runtime_image.sha256)
                && self.init.file == "init"
                && (64..=MAX_INIT).contains(&self.init.bytes)
                && is_digest(&self.init.sha256)
                && self.init_source_path == "/system/bin/init",
            "fixed bounded runtime image and original init roles",
        )?;
        require(
            matches!(
                self.init_interpreter.as_deref(),
                None | Some("/system/bin/bootstrap/linker64")
                    | Some("/system/bin/linker64")
                    | Some("/apex/com.android.runtime/bin/linker64")
            ),
            "only original Android linker locations are supported",
        )?;
        for digest in [
            &self.original_rc_inventory_sha256,
            &self.reviewed_adapter_sha256,
            &self.runtime_tree_inventory_sha256,
        ] {
            require(
                is_digest(digest),
                "complete original-input and adapter provenance",
            )?;
        }
        require(
            (1..=128).contains(&self.apexes.len()),
            "bounded nonempty original APEX inventory",
        )?;
        let mut names = BTreeSet::new();
        let mut containers = BTreeSet::new();
        let mut previous: Option<&str> = None;
        for apex in &self.apexes {
            require(
                safe_module_name(&apex.name)
                    && apex.version > 0
                    && names.insert(apex.name.as_str())
                    && previous.is_none_or(|value| value < apex.name.as_str())
                    && containers.insert(apex.container_file.as_str())
                    && (apex.container_file == format!("{}.apex", apex.name)
                        || apex.container_file == format!("{}.capex", apex.name)),
                "sorted unique original APEX names and fixed container basenames",
            )?;
            previous = Some(&apex.name);
            for (bytes, digest) in [
                (apex.container_bytes, &apex.container_sha256),
                (apex.original_apex_bytes, &apex.original_apex_sha256),
                (apex.payload_bytes, &apex.payload_sha256),
            ] {
                require(
                    (4096..=MAX_RUNTIME_IMAGE).contains(&bytes) && is_digest(digest),
                    "complete bounded original container, APEX and payload lineage",
                )?;
            }
            if apex.container_file.ends_with(".apex") {
                require(
                    apex.container_bytes == apex.original_apex_bytes
                        && apex.container_sha256 == apex.original_apex_sha256,
                    "an uncompressed APEX is the original container itself",
                )?;
            }
        }
        if let Some(activation) = &self.activation {
            activation.validate(self)?;
        }
        if let Some(query) = &self.query {
            query.validate(self)?;
        }
        if let Some(native) = &self.native_v2 {
            native.validate(self)?;
        }
        if let Some(execution) = &self.execution {
            execution.validate(self)?;
            if let Some(activation) = &self.activation {
                activation.validate_cp3a(self)?;
            }
            if let Some(query) = &self.query {
                query.validate_cp3a()?;
            }
        }
        Ok(())
    }
}

fn original_init_elf(file: &File, declared_bytes: u64) -> Result<Option<String>> {
    let mut header = [0u8; 64];
    file.read_exact_at(&mut header, 0)?;
    let u16_at = |offset| u16::from_le_bytes([header[offset], header[offset + 1]]);
    let u64_at = |offset| u64::from_le_bytes(header[offset..offset + 8].try_into().unwrap());
    require(
        &header[..4] == b"\x7fELF"
            && header[4..7] == [2, 1, 1]
            && matches!(u16_at(16), 2 | 3)
            && u16_at(18) == 62
            && u32::from_le_bytes(header[20..24].try_into().unwrap()) == 1
            && u64_at(24) != 0
            && u16_at(52) == 64
            && u16_at(54) == 56,
        "original init must be a complete little-endian x86_64 ELF executable",
    )?;
    let count = u16_at(56) as u64;
    let offset = u64_at(32);
    require(
        (1..=128).contains(&count)
            && offset >= 64
            && offset
                .checked_add(count * 56)
                .is_some_and(|end| end <= declared_bytes),
        "bounded complete original init program headers",
    )?;
    let mut executable_load = false;
    let mut interpreter = None;
    for index in 0..count {
        let mut ph = [0u8; 56];
        file.read_exact_at(&mut ph, offset + index * 56)?;
        let kind = u32::from_le_bytes(ph[..4].try_into().unwrap());
        let flags = u32::from_le_bytes(ph[4..8].try_into().unwrap());
        let file_offset = u64::from_le_bytes(ph[8..16].try_into().unwrap());
        let file_size = u64::from_le_bytes(ph[32..40].try_into().unwrap());
        let memory_size = u64::from_le_bytes(ph[40..48].try_into().unwrap());
        require(
            file_offset
                .checked_add(file_size)
                .is_some_and(|end| end <= declared_bytes),
            "init ELF segment escapes the authenticated file",
        )?;
        if kind == 1 {
            require(file_size <= memory_size, "invalid init load segment")?;
            executable_load |= flags & 1 != 0 && file_size != 0;
        }
        if kind == 3 {
            require(
                interpreter.is_none() && (2..=256).contains(&file_size),
                "single bounded init interpreter",
            )?;
            let mut raw = vec![0u8; file_size as usize];
            file.read_exact_at(&mut raw, file_offset)?;
            require(
                raw.last() == Some(&0) && !raw[..raw.len() - 1].contains(&0),
                "one terminated ELF interpreter",
            )?;
            raw.pop();
            interpreter = Some(
                String::from_utf8(raw)
                    .map_err(|_| MountError::Rejected("init interpreter UTF-8"))?,
            );
        }
    }
    require(executable_load, "init requires an executable load segment")?;
    Ok(interpreter)
}

fn require_exact_xattr<const N: usize>(file: &File, name: &CStr, expected: &[u8; N]) -> Result<()> {
    // One bounded descriptor read: oversized values fail with ERANGE rather
    // than allocating from an untrusted length or truncating a context.
    let mut value = [0u8; N];
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            name.as_ptr(),
            value.as_mut_ptr().cast(),
            value.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        count as usize == N && &value == expected,
        "exact original init security label bytes required",
    )
}

fn require_absent_xattr(file: &File, name: &CStr) -> Result<()> {
    let count =
        unsafe { libc::fgetxattr(file.as_raw_fd(), name.as_ptr(), std::ptr::null_mut(), 0) };
    if count >= 0 {
        return Err(MountError::Rejected(
            "original init must not carry a file capability, including an empty attribute",
        ));
    }
    let error = io::Error::last_os_error();
    // Unsupported or denied reads do not establish original absence.
    if error.raw_os_error() != Some(libc::ENODATA) {
        return Err(error.into());
    }
    Ok(())
}

fn require_init_security_xattrs(file: &File) -> Result<()> {
    require_exact_xattr(file, c"security.selinux", ORIGINAL_INIT_SELINUX)?;
    require_absent_xattr(file, c"security.capability")
}

fn verify_init_security_metadata(original: &SealedFile) -> Result<()> {
    // The complete held-inode and path identity, including ctime, brackets
    // both xattr reads. No path is reopened to obtain the attribute values.
    original.revalidate()?;
    require_init_security_xattrs(&original.file)?;
    original.revalidate()
}

fn verify_init_mount(
    mount: &File,
    original: &SealedFile,
    uids: IdRange,
    gids: IdRange,
    id: u64,
) -> Result<()> {
    verify_init_security_metadata(original)?;
    let meta = mount.metadata()?;
    require(
        meta.is_file()
            && (
                meta.dev(),
                meta.ino(),
                meta.len(),
                meta.nlink(),
                meta.mode(),
            ) == (
                original.identity.dev,
                original.identity.ino,
                original.identity.bytes,
                original.identity.links,
                original.identity.mode,
            )
            && meta.uid() == uids.start
            && meta.gid() == gids.start
            && fs_type(mount)? == fs_type(&original.file)?
            && require_detached(mount)? == id,
        "detached original init inode with this namespace's root mapping",
    )?;
    let mut vfs: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(mount.as_raw_fd(), &mut vfs) })?;
    require(
        vfs.f_flag as u64 & READONLY_FLAGS == READONLY_FLAGS
            && vfs.f_flag as u64 & MOUNT_ATTR_NOEXEC == 0,
        "original init mount is read-only, nosuid, nodev and executable",
    )?;
    Ok(())
}

fn detached_init_mount(
    original: &SealedFile,
    userns: &File,
    uids: IdRange,
    gids: IdRange,
) -> Result<File> {
    original.revalidate()?;
    let mount = syscall_fd(unsafe {
        libc::syscall(
            libc::SYS_open_tree,
            original.file.as_raw_fd(),
            c"".as_ptr(),
            OPEN_TREE_CLONE | libc::O_CLOEXEC as u32 | AT_EMPTY_PATH,
        )
    })?;
    let before = mount.metadata()?;
    require(
        before.is_file() && FileIdentity::of(&before) == original.identity,
        "clone originates in the held original init inode",
    )?;
    require_detached(&mount)?;
    let attr = MountAttr {
        attr_set: READONLY_FLAGS | MOUNT_ATTR_IDMAP,
        attr_clr: 0,
        propagation: 0,
        userns_fd: u64::try_from(userns.as_raw_fd())
            .map_err(|_| MountError::Rejected("init userns descriptor"))?,
    };
    let rc = unsafe {
        libc::syscall(
            libc::SYS_mount_setattr,
            mount.as_raw_fd(),
            c"".as_ptr(),
            AT_EMPTY_PATH,
            &attr,
            std::mem::size_of::<MountAttr>(),
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error().into());
    }
    let id = require_detached(&mount)?;
    verify_init_mount(&mount, original, uids, gids, id)?;
    Ok(mount)
}

#[derive(Debug)]
struct RuntimeResources {
    base_manifest: SealedFile,
    manifest: SealedFile,
    image: SealedFile,
    init: SealedFile,
    mount: Option<File>,
    init_mount: Option<File>,
    binding: Option<LoopBinding>,
    filesystem: Filesystem,
    mount_id: u64,
    init_mount_id: u64,
    userns: File,
    userns_identity: (u64, u64),
    uids: IdRange,
    gids: IdRange,
    host_uid: u32,
    cohort: String,
    runtime_manifest_sha256: String,
    activation: Option<ActivationResources>,
    activation_roots: Option<ActivationRoots>,
    query: Option<QueryResources>,
    native: Option<NativeResources>,
    execution: Option<ExecutionDeclaration>,
    // This duplicate shares the actual flock description, not a JSON claim.
    apex_loops: RefCell<ApexLoops>,
    _reservation_retention: File,
}

impl RuntimeResources {
    // The exclusive original actor already holds this resource's ledger.
    // Keep all other live namespace/input checks available without asking
    // RefCell for a second borrow of that same original ledger.
    fn matches_input_witness(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        witness.revalidate_live_admission()?;
        require_complete_namespace(witness)?;
        let lease = witness.identity_lease()?;
        let meta = witness.user_namespace().metadata()?;
        require(
            (meta.dev(), meta.ino()) == self.userns_identity
                && lease.host_uid() == self.host_uid
                && lease.broker_cohort() == self.cohort
                && lease.broker_ranges() == (self.uids, self.gids),
            "runtime belongs to this live namespace, user and base cohort",
        )?;
        for sealed in [&self.base_manifest, &self.manifest, &self.image, &self.init] {
            lease.broker_reject_backing_body(&sealed.file)?;
            sealed.revalidate()?;
        }
        verify_init_security_metadata(&self.init)?;
        if let Some(activation) = &self.activation {
            activation.revalidate(self.uids, self.gids)?;
        }
        if let Some(roots) = &self.activation_roots {
            roots.revalidate(self.uids, self.gids)?;
        }
        if let Some(query) = &self.query {
            query.revalidate(self.uids, self.gids)?;
        }
        if let Some(native) = &self.native {
            native.revalidate()?;
        }
        Ok(())
    }

    fn matches_witness(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
        self.matches_input_witness(witness)?;
        self.apex_loops
            .try_borrow()
            .map_err(|_| MountError::Rejected("APEX block provider is already active"))?
            .revalidate()?;
        Ok(())
    }
    fn cleanup(&mut self) -> Result<Vec<u64>> {
        // A builtin loop retains a file on the base system mount. Retire all
        // these consumers before the namespace owner can retire base images.
        self.apex_loops.get_mut().cleanup()?;
        let mut released = self.apex_loops.get_mut().retired_devices().to_vec();
        drop(self.activation.take());
        drop(self.activation_roots.take());
        drop(self.query.take());
        drop(self.native.take());
        drop(self.mount.take());
        drop(self.init_mount.take());
        if let Some(binding) = self.binding.as_mut() {
            if binding.file.is_some() {
                released.push(binding.retire()?);
            }
        }
        Ok(released)
    }
}

/// A live reservation and verified fixed inputs are the only constructors.
/// This object is neither Clone nor Deserialize and exports exactly once.
#[derive(Debug)]
pub(crate) struct PreparedRuntime {
    resources: Option<RuntimeResources>,
    exported: bool,
}

/// The selected manifest alone determines whether the one fixed query
/// filesystem is present. A base-only runtime cannot issue query input roles.
pub(crate) enum RuntimeTransfer<'a> {
    Base([BorrowedFd<'a>; 2]),
    WithQuery {
        files: [BorrowedFd<'a>; 3],
        layout: QueryLayout,
    },
    WithActivation([BorrowedFd<'a>; 4]),
    WithActivationQuery {
        files: [BorrowedFd<'a>; 5],
        layout: QueryLayout,
    },
    WithBootstrapActivation([BorrowedFd<'a>; 5]),
    WithBootstrapActivationQuery {
        files: [BorrowedFd<'a>; 6],
        layout: QueryLayout,
    },
}
impl RuntimeTransfer<'_> {
    pub(crate) fn as_slice(&self) -> &[BorrowedFd<'_>] {
        match self {
            Self::Base(files) => files,
            Self::WithQuery { files, .. } => files,
            Self::WithActivation(files) => files,
            Self::WithActivationQuery { files, .. } => files,
            Self::WithBootstrapActivation(files) => files,
            Self::WithBootstrapActivationQuery { files, .. } => files,
        }
    }

    pub(crate) fn query_layout(&self) -> Option<QueryLayout> {
        match self {
            Self::Base(_) => None,
            Self::WithQuery { layout, .. } => Some(*layout),
            Self::WithActivation(_) => None,
            Self::WithActivationQuery { layout, .. } => Some(*layout),
            Self::WithBootstrapActivation(_) => None,
            Self::WithBootstrapActivationQuery { layout, .. } => Some(*layout),
        }
    }

    pub(crate) fn activation_roots(&self) -> bool {
        self.activation_root_count() != 0
    }
    pub(crate) fn activation_root_count(&self) -> usize {
        match self {
            Self::Base(_) | Self::WithQuery { .. } => 0,
            Self::WithActivation(_) | Self::WithActivationQuery { .. } => 2,
            Self::WithBootstrapActivation(_) | Self::WithBootstrapActivationQuery { .. } => 3,
        }
    }

    pub(crate) fn query_index(&self) -> Option<usize> {
        self.query_layout()
            .map(|_| 2 + self.activation_root_count())
    }
}

#[derive(Debug, Serialize)]
pub(crate) struct RuntimeRetirement {
    detached_runtime_descriptor_closed: bool,
    detached_init_mount_descriptor_closed: bool,
    original_init_descriptor_closed: bool,
    activation_executable_mounts_closed: usize,
    activation_writable_filesystems_closed: usize,
    query_executable_files_closed: usize,
    query_data_files_closed: usize,
    query_private_filesystem_closed: bool,
    owned_loop_devices_observed_unbound: Vec<u64>,
    after_owned_tree_exit: bool,
}

impl PreparedRuntime {
    /// Retain the original paired MAC/selection owner before any APEX alias
    /// mutation. The resource guard can then verify the same objects during
    /// successful retirement and error cleanup without reacquiring a provider.
    pub(crate) fn bind_activation_context(
        &self,
        witness: &OwnedNamespaceWitness<'_>,
        selection: &crate::production_selection::ProductionSelection,
        prepared: &crate::production_execution::PreparedExecution,
    ) -> Result<()> {
        let context = prepared.runtime_mac_owner(selection, witness)?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("runtime owner retired"))?;
        resources.matches_witness(witness)?;
        {
            let mut loops = resources
                .apex_loops
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("APEX block provider is already active"))?;
            loops.bind_owner(context)?;
        }
        resources.matches_witness(witness)
    }

    pub(crate) fn prepare(
        witness: &OwnedNamespaceWitness<'_>,
        runtime_manifest_sha256: &str,
    ) -> Result<Self> {
        require(
            unsafe { libc::geteuid() } == 0,
            "actual root runtime broker",
        )?;
        require(
            is_digest(runtime_manifest_sha256),
            "selected complete runtime-manifest digest",
        )?;
        witness.revalidate_live_admission()?;
        require_complete_namespace(witness)?;
        let lease = witness.identity_lease()?;
        let cohort = lease.broker_cohort().to_owned();
        require(is_digest(&cohort), "reserved base-cohort digest")?;
        let admit = |file: &File| -> Result<()> {
            lease.broker_reject_backing_body(file)?;
            Ok(())
        };
        let base_manifest = SealedFile::open_guarded(
            Path::new(MANIFEST_ROOT),
            &format!("{cohort}.json"),
            0,
            MAX_MANIFEST,
            admit,
        )?;
        let raw_base = base_manifest.bounded_bytes(MAX_MANIFEST)?;
        require(
            format!("{:x}", Sha256::digest(&raw_base)) == cohort,
            "original base-cohort manifest bytes",
        )?;
        let base: CohortDeclaration = serde_json::from_slice(&raw_base)?;
        base.validate()?;
        let manifest = SealedFile::open_guarded(
            Path::new(RUNTIME_MANIFEST_ROOT),
            &format!("{runtime_manifest_sha256}.json"),
            0,
            MAX_RUNTIME_MANIFEST,
            admit,
        )?;
        require(
            manifest.identity.mode & 0o7777 == 0o400,
            "root-sealed runtime manifest mode",
        )?;
        let raw = manifest.bounded_bytes(MAX_RUNTIME_MANIFEST)?;
        require(
            format!("{:x}", Sha256::digest(&raw)) == runtime_manifest_sha256,
            "root-selected full runtime manifest bytes",
        )?;
        let declaration: RuntimeDeclaration = serde_json::from_slice(&raw)?;
        declaration.validate(&cohort, &base)?;
        let native = declaration.native_v2.as_ref().ok_or(MountError::Rejected(
            "production runtime requires complete fixed native v2 inputs",
        ))?;
        require(
            declaration.activation.is_some(),
            "production runtime requires fixed original activation inputs",
        )?;
        let execution = declaration.execution.as_ref().ok_or(MountError::Rejected(
            "production runtime requires an explicit exact-image execution policy",
        ))?;
        execution.validate(&declaration)?;
        let parent = Path::new(RUNTIME_IMAGE_ROOT).join(runtime_manifest_sha256);
        let image = SealedFile::open_guarded(&parent, "runtime.img", 0, MAX_RUNTIME_IMAGE, admit)?;
        let init = SealedFile::open_guarded(&parent, "init", 0, MAX_INIT, admit)?;
        require(
            image.identity.mode & 0o7777 == 0o400
                && init.identity.mode & 0o7777 == 0o555
                && (image.identity.dev, image.identity.ino)
                    != (init.identity.dev, init.identity.ino),
            "sealed distinct image and executable original init inodes",
        )?;
        image.verify_digest(
            declaration.runtime_image.bytes,
            &declaration.runtime_image.sha256,
        )?;
        init.verify_digest(declaration.init.bytes, &declaration.init.sha256)?;
        require(
            original_init_elf(&init.file, declaration.init.bytes)? == declaration.init_interpreter,
            "exact original init ELF interpreter",
        )?;
        verify_init_security_metadata(&init)?;
        let filesystem = Filesystem::detect(&image.file)?;
        let userns = witness.user_namespace().try_clone()?;
        let meta = userns.metadata()?;
        let (uids, gids) = lease.broker_ranges();
        let mut result = Self {
            exported: false,
            resources: Some(RuntimeResources {
                base_manifest,
                manifest,
                image,
                init,
                filesystem,
                userns,
                userns_identity: (meta.dev(), meta.ino()),
                uids,
                gids,
                host_uid: lease.host_uid(),
                cohort,
                runtime_manifest_sha256: runtime_manifest_sha256.to_owned(),
                activation: None,
                activation_roots: None,
                query: None,
                native: None,
                execution: None,
                apex_loops: RefCell::new(ApexLoops::default()),
                mount: None,
                init_mount: None,
                binding: None,
                mount_id: 0,
                init_mount_id: 0,
                _reservation_retention: lease.broker_retain_reservation()?,
            }),
        };
        let resources = result
            .resources
            .as_mut()
            .ok_or(MountError::Rejected("runtime custody absent"))?;
        resources.matches_witness(witness)?;
        resources.binding = Some(LoopBinding::attach(&resources.image)?);
        let binding = resources
            .binding
            .as_ref()
            .ok_or(MountError::Rejected("runtime loop absent"))?;
        // APEX binaries must remain executable. The shared primitive sets
        // RDONLY|NOSUID|NODEV and IDMAP, without adding NOEXEC.
        let mount = detached_mount(binding, filesystem, &resources.userns, uids, gids)?;
        resources.mount_id = require_detached(&mount)?;
        resources.mount = Some(mount);
        resources.native = Some(NativeResources::prepare(
            resources
                .mount
                .as_ref()
                .ok_or(MountError::Rejected("runtime mount absent"))?,
            native,
            uids,
            gids,
        )?);
        // Only the initial-root broker may clone a file from the host mount
        // namespace. It does so from the authenticated held descriptor; the
        // guest receives an already detached, read-only mount capability.
        let init_mount = detached_init_mount(&resources.init, &resources.userns, uids, gids)?;
        resources.init_mount_id = require_detached(&init_mount)?;
        resources.init_mount = Some(init_mount);
        if let Some(activation) = &declaration.activation {
            resources.activation = Some(ActivationResources::prepare(
                activation,
                &parent,
                witness,
                &resources.userns,
                uids,
                gids,
            )?);
        }
        resources.activation_roots = Some(ActivationRoots::prepare(
            witness,
            &resources.userns,
            uids,
            gids,
        )?);
        if let Some(query) = &declaration.query {
            resources.query = Some(QueryResources::prepare(
                query,
                &parent,
                witness,
                &resources.userns,
                uids,
                gids,
            )?);
        }
        resources.execution = declaration.execution;
        resources.matches_witness(witness)?;
        Ok(result)
    }

    pub(crate) fn descriptors_for_transfer<'a>(
        &'a mut self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<RuntimeTransfer<'a>> {
        require(!self.exported, "single runtime descriptor transfer")?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("runtime already retired"))?;
        resources.matches_witness(witness)?;
        require(
            resources.native.is_some(),
            "fixed native roles absent before production transfer",
        )?;
        resources
            .binding
            .as_ref()
            .ok_or(MountError::Rejected("runtime loop absent"))?
            .verify()?;
        let mount = resources
            .mount
            .as_ref()
            .ok_or(MountError::Rejected("detached runtime root absent"))?;
        require(
            require_detached(mount)? == resources.mount_id,
            "runtime root remains detached before transfer",
        )?;
        verify_readonly_mount(
            mount,
            resources.filesystem,
            resources.uids,
            resources.gids,
            resources.mount_id,
        )?;
        let init_mount = resources
            .init_mount
            .as_ref()
            .ok_or(MountError::Rejected("detached original init mount absent"))?;
        verify_init_mount(
            init_mount,
            &resources.init,
            resources.uids,
            resources.gids,
            resources.init_mount_id,
        )?;
        let roots = resources
            .activation_roots
            .as_ref()
            .ok_or(MountError::Rejected(
                "fixed activation writable roots absent before production transfer",
            ))?
            .for_transfer(resources.uids, resources.gids)?;
        self.exported = true;
        Ok(match resources.query.as_ref() {
            Some(query) => RuntimeTransfer::WithBootstrapActivationQuery {
                files: [
                    mount.as_fd(),
                    init_mount.as_fd(),
                    roots[0],
                    roots[1],
                    roots[2],
                    query.mount(),
                ],
                layout: query.layout(),
            },
            None => RuntimeTransfer::WithBootstrapActivation([
                mount.as_fd(),
                init_mount.as_fd(),
                roots[0],
                roots[1],
                roots[2],
            ]),
        })
    }

    pub(crate) fn retire_untransferred(mut self) -> Result<RuntimeRetirement> {
        require(
            !self.exported,
            "transferred runtime requires actual owned-tree retirement",
        )?;
        self.cleanup(false)
    }

    pub(crate) fn retire_after_tree(
        mut self,
        retired: &RetiredTreeWitness<'_>,
    ) -> Result<RuntimeRetirement> {
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("runtime already retired"))?;
        retired.verify_mount_retirement(
            &resources.userns,
            resources.host_uid,
            &resources.cohort,
        )?;
        self.cleanup(true)
    }

    fn cleanup(&mut self, after_owned_tree_exit: bool) -> Result<RuntimeRetirement> {
        let resources = self
            .resources
            .as_mut()
            .ok_or(MountError::Rejected("runtime already retired"))?;
        let activation_executable_mounts_closed =
            if resources.activation.is_some() { 2 } else { 0 };
        let activation_writable_filesystems_closed = if resources.activation_roots.is_some() {
            3
        } else {
            0
        };
        let query_executable_files_closed = resources
            .query
            .as_ref()
            .map_or(0, QueryResources::executable_file_count);
        let query_data_files_closed = resources
            .query
            .as_ref()
            .map_or(0, QueryResources::data_file_count);
        let query_private_filesystem_closed = resources.query.is_some();
        let released = resources.cleanup()?;
        drop(self.resources.take());
        Ok(RuntimeRetirement {
            detached_runtime_descriptor_closed: true,
            detached_init_mount_descriptor_closed: true,
            original_init_descriptor_closed: true,
            activation_executable_mounts_closed,
            activation_writable_filesystems_closed,
            query_executable_files_closed,
            query_data_files_closed,
            query_private_filesystem_closed,
            owned_loop_devices_observed_unbound: released,
            after_owned_tree_exit,
        })
    }
}

impl Drop for PreparedRuntime {
    fn drop(&mut self) {
        if !self.exported {
            if let Some(resources) = self.resources.as_mut() {
                if resources.cleanup().is_ok() {
                    drop(self.resources.take());
                    return;
                }
            }
        }
        // Unknown delivery/exit retains real file, loop, mount, namespace and
        // flock custody. A receipt can never manufacture retirement.
        if let Some(resources) = self.resources.take() {
            std::mem::forget(resources);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Seek, SeekFrom, Write};

    fn set_xattr(file: &File, name: &CStr, value: &[u8]) {
        let result = unsafe {
            libc::fsetxattr(
                file.as_raw_fd(),
                name.as_ptr(),
                value.as_ptr().cast(),
                value.len(),
                0,
            )
        };
        assert_eq!(result, 0, "{}", io::Error::last_os_error());
    }

    #[test]
    fn runtime_init_xattr_requires_complete_exact_bytes() {
        let file = tempfile::tempfile().unwrap();
        let name = c"user.droidloom-init-label";
        assert!(require_exact_xattr(&file, name, ORIGINAL_INIT_SELINUX).is_err());
        set_xattr(&file, name, ORIGINAL_INIT_SELINUX);
        require_exact_xattr(&file, name, ORIGINAL_INIT_SELINUX).unwrap();
        for value in [
            b"".as_slice(),
            b"u:object_r:init_exec:s0", // Missing original terminating NUL.
            b"u:object_r:init_exec:s0\0\0",
            b"u:object_r:init_exec:s1\0", // Same length, different context.
            b"u:object_r:system_linker_exec:s0\0",
        ] {
            set_xattr(&file, name, value);
            assert!(require_exact_xattr(&file, name, ORIGINAL_INIT_SELINUX).is_err());
        }
    }

    #[test]
    fn runtime_init_xattr_follows_held_descriptor_after_path_replacement() {
        let parent = tempfile::tempdir().unwrap();
        let path = parent.path().join("init");
        let file = File::create(&path).unwrap();
        let name = c"user.droidloom-init-label";
        set_xattr(&file, name, ORIGINAL_INIT_SELINUX);
        std::fs::rename(&path, parent.path().join("held-init")).unwrap();
        let replacement = File::create(&path).unwrap();
        set_xattr(&replacement, name, b"u:object_r:init_exec:s1\0");
        require_exact_xattr(&file, name, ORIGINAL_INIT_SELINUX).unwrap();
        assert!(require_exact_xattr(&replacement, name, ORIGINAL_INIT_SELINUX).is_err());
    }

    #[test]
    fn runtime_init_capability_absence_rejects_present_empty_and_binary_values() {
        let file = tempfile::tempfile().unwrap();
        let name = c"user.droidloom-init-capability";
        require_absent_xattr(&file, name).unwrap();
        for value in [b"".as_slice(), &[0u8; 20], b"\x01\0\x02\0"] {
            set_xattr(&file, name, value);
            assert!(require_absent_xattr(&file, name).is_err());
        }
        let result = unsafe { libc::fremovexattr(file.as_raw_fd(), name.as_ptr()) };
        assert_eq!(result, 0, "{}", io::Error::last_os_error());
        require_absent_xattr(&file, name).unwrap();
    }

    #[test]
    fn runtime_init_xattr_read_errors_do_not_establish_absence() {
        let file = tempfile::NamedTempFile::new().unwrap();
        let path_only = std::fs::OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_NOFOLLOW)
            .open(file.path())
            .unwrap();
        assert!(matches!(
            require_absent_xattr(&path_only, c"user.droidloom-init-capability"),
            Err(MountError::Io(error)) if error.raw_os_error() == Some(libc::EBADF)
        ));
        assert!(
            require_exact_xattr(
                &path_only,
                c"user.droidloom-init-label",
                ORIGINAL_INIT_SELINUX,
            )
            .is_err()
        );
    }

    #[test]
    fn runtime_init_metadata_cannot_be_supplied_by_user_attributes() {
        let file = tempfile::tempfile().unwrap();
        set_xattr(&file, c"user.security.selinux", ORIGINAL_INIT_SELINUX);
        require_exact_xattr(&file, c"user.security.selinux", ORIGINAL_INIT_SELINUX).unwrap();
        // Ordinary xattr storage controls neither relabel an input nor grant
        // SELinux authority. Production always reads the fixed security names.
        assert!(require_init_security_xattrs(&file).is_err());
    }

    fn base() -> CohortDeclaration {
        serde_json::from_value(serde_json::json!({
            "schema":1,"scope":"android_base_images_v1","layout":"gsi_system_as_root",
            "system":{"file":"system.img","bytes":8192,"sha256":"a".repeat(64)},
            "vendor":{"file":"vendor.img","bytes":8192,"sha256":"b".repeat(64)}
        }))
        .unwrap()
    }
    fn declaration() -> serde_json::Value {
        serde_json::json!({
            "schema":1,"scope":"android_runtime_assets_v1","base_cohort_sha256":"c".repeat(64),
            "source_system":{"file":"system.img","bytes":8192,"sha256":"a".repeat(64)},
            "runtime_image":{"file":"runtime.img","bytes":8192,"sha256":"d".repeat(64)},
            "init":{"file":"init","bytes":4096,"sha256":"e".repeat(64)},
            "init_source_path":"/system/bin/init","init_interpreter":null,
            "original_rc_inventory_sha256":"f".repeat(64),
            "reviewed_adapter_sha256":"1".repeat(64),"runtime_tree_inventory_sha256":"2".repeat(64),
            "apexes":[{"name":"com.android.runtime","version":1,"container_file":"com.android.runtime.apex",
                "container_bytes":8192,"container_sha256":"3".repeat(64),
                "original_apex_bytes":8192,"original_apex_sha256":"3".repeat(64),
                "payload_bytes":4096,"payload_sha256":"4".repeat(64)}]
        })
    }
    fn accepted(value: serde_json::Value) -> bool {
        serde_json::from_value::<RuntimeDeclaration>(value)
            .is_ok_and(|decl| decl.validate(&"c".repeat(64), &base()).is_ok())
    }
    #[test]
    fn runtime_inputs_reject_other_base_or_original_system() {
        assert!(accepted(declaration()));
        for path in ["base_cohort_sha256", "source_system"] {
            let mut value = declaration();
            if path == "source_system" {
                value[path]["sha256"] = serde_json::json!("9".repeat(64));
            } else {
                value[path] = serde_json::json!("9".repeat(64));
            }
            assert!(!accepted(value));
        }
    }
    #[test]
    fn runtime_manifest_rejects_paths_aliases_and_lineage_substitution() {
        for path in [
            "../runtime.img",
            "/var/lib/droidloom/users/1000/data/data.img",
            "runtime.img/child",
        ] {
            let mut value = declaration();
            value["runtime_image"]["file"] = serde_json::json!(path);
            assert!(!accepted(value));
        }
        let mut value = declaration();
        let duplicate = value["apexes"][0].clone();
        value["apexes"].as_array_mut().unwrap().push(duplicate);
        assert!(!accepted(value));
        let mut value = declaration();
        value["apexes"][0]["original_apex_sha256"] = serde_json::json!("8".repeat(64));
        assert!(!accepted(value));
        let mut value = declaration();
        value["init_interpreter"] = serde_json::json!("/host/ld-linux-x86-64.so.2");
        assert!(!accepted(value));
    }
    #[test]
    fn runtime_schema_rejects_boolean_integer_and_unknown_authority_fields() {
        let mut value = declaration();
        value["schema"] = serde_json::json!(true);
        assert!(!accepted(value));
        let mut value = declaration();
        value["apexes"][0]["version"] = serde_json::json!(true);
        assert!(!accepted(value));
        let mut value = declaration();
        value["admission"] = serde_json::json!({"passed":true});
        assert!(!accepted(value));
        let mut value = declaration();
        value["reviewed_adapter_sha256"] = serde_json::json!("");
        assert!(!accepted(value));
    }
    #[test]
    fn runtime_query_sources_bind_fixed_roles_and_complete_selected_system() {
        let mut value = declaration();
        value["query"] = serde_json::json!({
            "scope":"fixed_application_query_v1", "source_system_sha256":"a".repeat(64),
            "cmd":{"original":{"file":"cmd-original","bytes":4096,"sha256":"5".repeat(64)},
                "source_path":"/system/bin/cmd","interpreter":"/system/bin/linker64"},
            "toybox":{"original":{"file":"toybox-original","bytes":8192,"sha256":"6".repeat(64)},
                "source_path":"/system/bin/toybox","interpreter":null}
        });
        assert!(accepted(value.clone()));
        let mut changed = value.clone();
        changed["query"]["source_system_sha256"] = serde_json::json!("9".repeat(64));
        assert!(!accepted(changed));
        for (field, replacement) in [
            ("source_path", serde_json::json!("/system/bin/sh")),
            ("interpreter", serde_json::json!("/host/ld.so")),
            ("preverified", serde_json::json!(true)),
        ] {
            let mut changed = value.clone();
            changed["query"]["cmd"][field] = replacement;
            assert!(!accepted(changed));
        }
        for (field, replacement) in [
            ("file", serde_json::json!("../cmd-original")),
            ("bytes", serde_json::json!(0)),
            ("bytes", serde_json::json!(128 * 1024 * 1024 + 1_u64)),
            ("bytes", serde_json::json!(true)),
            ("sha256", serde_json::json!("6".repeat(64))),
        ] {
            let mut changed = value.clone();
            changed["query"]["cmd"]["original"][field] = replacement;
            assert!(!accepted(changed));
        }
    }
    #[test]
    fn contacts_runtime_inputs_require_complete_fixed_source_roles_and_nonexecutable_classpath() {
        let mut value = declaration();
        value["query"] = serde_json::json!({
            "scope":"fixed_application_query_v1", "source_system_sha256":"a".repeat(64),
            "cmd":{"original":{"file":"cmd-original","bytes":4096,"sha256":"5".repeat(64)},
                "source_path":"/system/bin/cmd","interpreter":"/system/bin/linker64"},
            "toybox":{"original":{"file":"toybox-original","bytes":8192,"sha256":"6".repeat(64)},
                "source_path":"/system/bin/toybox","interpreter":null},
            "contacts":{
                "scope":"fixed_contacts_content_query_v1",
                "app_process64":{
                    "original":{"file":"contacts-app-process64-original","bytes":4096,"sha256":"7".repeat(64)},
                    "source_path":"/system/bin/app_process64","interpreter":"/system/bin/linker64"},
                "content_jar":{
                    "original":{"file":"contacts-content-jar-original","bytes":8192,"sha256":"8".repeat(64)},
                    "source_path":"/system/framework/content.jar","interpreter":null}
            }
        });
        assert!(accepted(value.clone()));
        for (role, field, replacement) in [
            (
                "app_process64",
                "source_path",
                serde_json::json!("/system/bin/sh"),
            ),
            (
                "app_process64",
                "interpreter",
                serde_json::json!("/host/ld.so"),
            ),
            (
                "content_jar",
                "source_path",
                serde_json::json!("/data/local/tmp/other.jar"),
            ),
            (
                "content_jar",
                "interpreter",
                serde_json::json!("/system/bin/linker64"),
            ),
            ("content_jar", "preverified", serde_json::json!(true)),
        ] {
            let mut changed = value.clone();
            changed["query"]["contacts"][role][field] = replacement;
            assert!(!accepted(changed));
        }
        for role in ["app_process64", "content_jar"] {
            let mut changed = value.clone();
            changed["query"]["contacts"]
                .as_object_mut()
                .unwrap()
                .remove(role);
            assert!(!accepted(changed));
            let mut changed = value.clone();
            changed["query"]["contacts"][role]["original"]["bytes"] = serde_json::json!(0);
            assert!(!accepted(changed));
            let mut changed = value.clone();
            changed["query"]["contacts"][role]["original"]["file"] =
                serde_json::json!("../unbound");
            assert!(!accepted(changed));
        }
        let mut changed = value.clone();
        changed["query"]["contacts"]["scope"] = serde_json::json!("arbitrary_java_query");
        assert!(!accepted(changed));
        let mut changed = value;
        changed["query"]["source_system_sha256"] = serde_json::json!("0".repeat(64));
        assert!(!accepted(changed));
    }
    fn elf() -> Vec<u8> {
        let mut bytes = vec![0u8; 4096];
        bytes[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
        bytes[16..18].copy_from_slice(&3u16.to_le_bytes());
        bytes[18..20].copy_from_slice(&62u16.to_le_bytes());
        bytes[20..24].copy_from_slice(&1u32.to_le_bytes());
        bytes[24..32].copy_from_slice(&128u64.to_le_bytes());
        bytes[32..40].copy_from_slice(&64u64.to_le_bytes());
        bytes[52..54].copy_from_slice(&64u16.to_le_bytes());
        bytes[54..56].copy_from_slice(&56u16.to_le_bytes());
        bytes[56..58].copy_from_slice(&1u16.to_le_bytes());
        bytes[64..68].copy_from_slice(&1u32.to_le_bytes());
        bytes[68..72].copy_from_slice(&5u32.to_le_bytes());
        bytes[96..104].copy_from_slice(&4096u64.to_le_bytes());
        bytes[104..112].copy_from_slice(&4096u64.to_le_bytes());
        bytes
    }
    fn inspect(bytes: &[u8]) -> Result<Option<String>> {
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(bytes).unwrap();
        file.seek(SeekFrom::Start(0)).unwrap();
        original_init_elf(&file, bytes.len() as u64)
    }
    #[test]
    fn held_init_rejects_foreign_architecture_and_overflowing_segments() {
        assert_eq!(inspect(&elf()).unwrap(), None);
        let mut bytes = elf();
        bytes[18..20].copy_from_slice(&183u16.to_le_bytes());
        assert!(inspect(&bytes).is_err());
        let mut bytes = elf();
        bytes[32..40].copy_from_slice(&u64::MAX.to_le_bytes());
        assert!(inspect(&bytes).is_err());
        let mut bytes = elf();
        bytes[72..80].copy_from_slice(&u64::MAX.to_le_bytes());
        assert!(inspect(&bytes).is_err());
        assert!(inspect(&elf()[..80]).is_err());
    }
}
