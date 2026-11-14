//! Same-selected-runtime custody for the two fixed linkerconfig inputs.
//!
//! The root-sealed runtime declaration selects original and static-trampoline
//! bytes. These are held, hashed executable inputs, never evidence of active
//! APEX mounts, generated linker files, successful execution or Android Ready.
//! PreparedRuntime retains them through actual whole-tree retirement.

use super::*;
use crate::production_namespace::ExecutedInitWitness;

const LINKERCONFIG_LABEL: &[u8; 32] = b"u:object_r:linkerconfig_exec:s0\0";
const MAX_HELPER: u64 = 32 * 1024 * 1024;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct ActivationDeclaration {
    scope: String,
    original: ImageDeclaration,
    original_source_path: String,
    original_source_sha256: String,
    original_interpreter: Option<String>,
    trampoline: ImageDeclaration,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum OriginalLocation {
    System,
    RuntimeApex,
}

impl OriginalLocation {
    fn parse(path: &str) -> Result<Self> {
        match path {
            "/system/bin/linkerconfig" => Ok(Self::System),
            "/apex/com.android.runtime/bin/linkerconfig" => Ok(Self::RuntimeApex),
            _ => Err(MountError::Rejected(
                "original linkerconfig source role is not fixed",
            )),
        }
    }
    fn path(self) -> &'static str {
        match self {
            Self::System => "/system/bin/linkerconfig",
            Self::RuntimeApex => "/apex/com.android.runtime/bin/linkerconfig",
        }
    }
}

impl ActivationDeclaration {
    pub(super) fn validate(&self, runtime: &RuntimeDeclaration) -> Result<()> {
        require(
            self.scope == "original_linkerconfig_trampoline_v1"
                && self.original.file == "linkerconfig-original"
                && self.trampoline.file == "linkerconfig-trampoline"
                && self.original.sha256 != self.trampoline.sha256
                && self.original.sha256 != runtime.init.sha256,
            "distinct fixed original-linkerconfig and trampoline roles",
        )?;
        for image in [&self.original, &self.trampoline] {
            require(
                (64..=MAX_HELPER).contains(&image.bytes) && is_digest(&image.sha256),
                "bounded complete fixed activation input digest",
            )?;
        }
        require(
            matches!(
                self.original_interpreter.as_deref(),
                None | Some("/system/bin/bootstrap/linker64")
                    | Some("/system/bin/linker64")
                    | Some("/apex/com.android.runtime/bin/linker64")
            ),
            "original linkerconfig interpreter must remain an Android role",
        )?;
        let expected = match OriginalLocation::parse(&self.original_source_path)? {
            OriginalLocation::System => &runtime.source_system.sha256,
            OriginalLocation::RuntimeApex => {
                &runtime
                    .apexes
                    .iter()
                    .find(|apex| apex.name == "com.android.runtime")
                    .ok_or(MountError::Rejected(
                        "original runtime APEX lineage is absent",
                    ))?
                    .payload_sha256
            }
        };
        require(
            is_digest(&self.original_source_sha256) && &self.original_source_sha256 == expected,
            "original linkerconfig must bind its selected source filesystem",
        )
    }
}

fn digest(value: &str) -> Result<[u8; 32]> {
    require(is_digest(value), "complete lowercase executable digest")?;
    let nibble = |byte: u8| {
        if byte.is_ascii_digit() {
            byte - b'0'
        } else {
            byte - b'a' + 10
        }
    };
    let mut result = [0_u8; 32];
    for (out, pair) in result.iter_mut().zip(value.as_bytes().chunks_exact(2)) {
        *out = nibble(pair[0]) * 16 + nibble(pair[1]);
    }
    Ok(result)
}

fn security(original: &SealedFile) -> Result<()> {
    original.revalidate()?;
    require_exact_xattr(&original.file, c"security.selinux", LINKERCONFIG_LABEL)?;
    require_absent_xattr(&original.file, c"security.capability")?;
    original.revalidate()
}

#[derive(Debug)]
struct ExecutableMount {
    original: SealedFile,
    mount: File,
    readable: File,
    mapped: FileIdentity,
    mount_id: u64,
    digest: [u8; 32],
}

impl ExecutableMount {
    fn prepare(
        declared: &ImageDeclaration,
        parent: &Path,
        witness: &OwnedNamespaceWitness<'_>,
        userns: &File,
        uids: IdRange,
        gids: IdRange,
    ) -> Result<Self> {
        let lease = witness.identity_lease()?;
        let original = SealedFile::open_guarded(parent, &declared.file, 0, MAX_HELPER, |file| {
            lease.broker_reject_backing_body(file)?;
            Ok(())
        })?;
        require(
            original.identity.mode == libc::S_IFREG | 0o555,
            "fixed activation executable is root-sealed 0555",
        )?;
        original.verify_digest(declared.bytes, &declared.sha256)?;
        security(&original)?;
        let mount = syscall_fd(unsafe {
            libc::syscall(
                libc::SYS_open_tree,
                original.file.as_raw_fd(),
                c"".as_ptr(),
                OPEN_TREE_CLONE | libc::O_CLOEXEC as u32 | AT_EMPTY_PATH,
            )
        })?;
        require(
            FileIdentity::of(&mount.metadata()?) == original.identity,
            "activation clone must originate in its actual held input",
        )?;
        require_detached(&mount)?;
        let attributes = MountAttr {
            attr_set: READONLY_FLAGS | MOUNT_ATTR_IDMAP,
            attr_clr: 0,
            propagation: 0,
            userns_fd: u64::try_from(userns.as_raw_fd())
                .map_err(|_| MountError::Rejected("activation userns descriptor"))?,
        };
        if unsafe {
            libc::syscall(
                libc::SYS_mount_setattr,
                mount.as_raw_fd(),
                c"".as_ptr(),
                AT_EMPTY_PATH,
                &attributes,
                std::mem::size_of::<MountAttr>(),
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        let mount_id = require_detached(&mount)?;
        // open_tree returns a path FD. Reopen only our actual held detached
        // file mount so the body view retains its idmap and readonly flags.
        let alias = text_name(&format!("/proc/self/fd/{}", mount.as_raw_fd()))?;
        let readable = syscall_fd(unsafe {
            libc::open(
                alias.as_ptr(),
                libc::O_RDONLY | libc::O_CLOEXEC | libc::O_NONBLOCK,
            )
        } as _)?;
        let mut mapped = original.identity;
        mapped.uid = uids.start;
        mapped.gid = gids.start;
        let value = Self {
            original,
            mount,
            readable,
            mapped,
            mount_id,
            digest: digest(&declared.sha256)?,
        };
        value.revalidate(uids, gids)?;
        Ok(value)
    }

    fn revalidate(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        security(&self.original)?;
        require(
            self.mapped.uid == uids.start && self.mapped.gid == gids.start,
            "activation input belongs to the original mapped root",
        )?;
        for file in [&self.mount, &self.readable] {
            require(
                FileIdentity::of(&file.metadata()?) == self.mapped
                    && require_detached(file)? == self.mount_id,
                "original activation mount identity changed",
            )?;
            let kind = fs_type(file)?;
            require(
                [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&kind),
                "activation executable must be on the reviewed image filesystems",
            )?;
            let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
            zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) })?;
            require(
                flags.f_flag as u64 & READONLY_FLAGS == READONLY_FLAGS
                    && flags.f_flag as u64 & MOUNT_ATTR_NOEXEC == 0,
                "activation executable must remain readonly nosuid nodev and executable",
            )?;
        }
        let flags = unsafe { libc::fcntl(self.readable.as_raw_fd(), libc::F_GETFL) };
        if flags < 0 {
            return Err(io::Error::last_os_error().into());
        }
        require(
            flags & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY,
            "activation body view must remain readable only",
        )?;
        require_exact_xattr(&self.readable, c"security.selinux", LINKERCONFIG_LABEL)?;
        require_absent_xattr(&self.readable, c"security.capability")?;
        security(&self.original)
    }
}

#[derive(Debug)]
pub(super) struct ActivationResources {
    original: ExecutableMount,
    trampoline: ExecutableMount,
    interpreter: Option<String>,
    location: OriginalLocation,
}

impl ActivationResources {
    pub(super) fn prepare(
        declared: &ActivationDeclaration,
        parent: &Path,
        witness: &OwnedNamespaceWitness<'_>,
        userns: &File,
        uids: IdRange,
        gids: IdRange,
    ) -> Result<Self> {
        witness.revalidate_live_admission()?;
        let actual = witness.user_namespace().metadata()?;
        let selected = userns.metadata()?;
        require(
            (actual.dev(), actual.ino()) == (selected.dev(), selected.ino())
                && witness.identity_lease()?.broker_ranges() == (uids, gids),
            "activation inputs require the actual same owned user namespace",
        )?;
        let original =
            ExecutableMount::prepare(&declared.original, parent, witness, userns, uids, gids)?;
        let trampoline =
            ExecutableMount::prepare(&declared.trampoline, parent, witness, userns, uids, gids)?;
        require(
            (original.mapped.dev, original.mapped.ino)
                != (trampoline.mapped.dev, trampoline.mapped.ino),
            "original linkerconfig and trampoline cannot alias",
        )?;
        require(
            original_init_elf(&original.readable, declared.original.bytes)?
                == declared.original_interpreter,
            "actual original linkerconfig interpreter differs",
        )?;
        require(
            original_init_elf(&trampoline.readable, declared.trampoline.bytes)?.is_none(),
            "trampoline input must have no interpreter",
        )?;
        let value = Self {
            original,
            trampoline,
            interpreter: declared.original_interpreter.clone(),
            location: OriginalLocation::parse(&declared.original_source_path)?,
        };
        value.revalidate(uids, gids)?;
        witness.revalidate_live_admission()?;
        Ok(value)
    }
    pub(super) fn revalidate(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        self.original.revalidate(uids, gids)?;
        self.trampoline.revalidate(uids, gids)
    }
}

fn selected_runtime<'a>(
    runtime: &'a PreparedRuntime,
    init: &ExecutedInitWitness<'_>,
) -> Result<&'a ActivationResources> {
    init.revalidate()?;
    require(
        std::ptr::eq(runtime, init.runtime_owner()?),
        "activation inputs must belong to this actual original init owner",
    )?;
    let resources = runtime
        .resources
        .as_ref()
        .ok_or(MountError::Rejected("activation runtime has retired"))?;
    let selected = init.selection();
    require(
        runtime.exported
            && resources.runtime_manifest_sha256 == selected.runtime_manifest()
            && resources.cohort == selected.base_cohort()
            && resources.host_uid == selected.spec().host_uid
            && (resources.uids.start, resources.gids.start) == init.mapped_root_ids(),
        "activation input selection or runtime transfer differs",
    )?;
    let user = init.user_namespace().metadata()?;
    require(
        (user.dev(), user.ino()) == resources.userns_identity,
        "activation inputs do not belong to the executed original user namespace",
    )?;
    for file in [
        &resources.base_manifest,
        &resources.manifest,
        &resources.image,
        &resources.init,
    ] {
        file.revalidate()?;
    }
    let activation = resources.activation.as_ref().ok_or(MountError::Rejected(
        "selected runtime has no fixed activation inputs",
    ))?;
    activation.revalidate(resources.uids, resources.gids)?;
    init.revalidate()?;
    Ok(activation)
}

/// Borrowed input roles with no caller-file/digest constructor, Clone,
/// Deserialize or ability to export a mount. They never issue Ready.
pub(crate) struct RuntimeLinkerconfigInputs<'a> {
    runtime: &'a PreparedRuntime,
    inputs: &'a ActivationResources,
}
pub(crate) struct RuntimeTrampoline<'a> {
    runtime: &'a PreparedRuntime,
    inputs: &'a ActivationResources,
}
pub(crate) struct RuntimeOriginalLinkerconfig<'a> {
    runtime: &'a PreparedRuntime,
    inputs: &'a ActivationResources,
}

impl PreparedRuntime {
    pub(crate) fn linkerconfig_inputs<'a>(
        &'a self,
        init: &ExecutedInitWitness<'_>,
    ) -> Result<RuntimeLinkerconfigInputs<'a>> {
        Ok(RuntimeLinkerconfigInputs {
            runtime: self,
            inputs: selected_runtime(self, init)?,
        })
    }
}

impl<'a> RuntimeLinkerconfigInputs<'a> {
    pub(crate) fn into_roles(self) -> (RuntimeTrampoline<'a>, RuntimeOriginalLinkerconfig<'a>) {
        (
            RuntimeTrampoline {
                runtime: self.runtime,
                inputs: self.inputs,
            },
            RuntimeOriginalLinkerconfig {
                runtime: self.runtime,
                inputs: self.inputs,
            },
        )
    }
}

impl<'a> RuntimeTrampoline<'a> {
    pub(crate) fn revalidate(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        require(
            std::ptr::eq(self.inputs, selected_runtime(self.runtime, init)?),
            "original trampoline runtime custody changed",
        )
    }
    pub(crate) fn file(&self) -> &'a File {
        &self.inputs.trampoline.readable
    }
    pub(crate) fn bytes(&self) -> u64 {
        self.inputs.trampoline.mapped.bytes
    }
    pub(crate) fn digest(&self) -> [u8; 32] {
        self.inputs.trampoline.digest
    }
}

impl<'a> RuntimeOriginalLinkerconfig<'a> {
    pub(crate) fn revalidate(&self, init: &ExecutedInitWitness<'_>) -> Result<()> {
        require(
            std::ptr::eq(self.inputs, selected_runtime(self.runtime, init)?),
            "original linkerconfig runtime custody changed",
        )
    }
    pub(crate) fn file(&self) -> &'a File {
        &self.inputs.original.readable
    }
    pub(crate) fn bytes(&self) -> u64 {
        self.inputs.original.mapped.bytes
    }
    pub(crate) fn digest(&self) -> [u8; 32] {
        self.inputs.original.digest
    }
    pub(crate) fn interpreter(&self) -> Option<&'a str> {
        self.inputs.interpreter.as_deref()
    }
    pub(crate) fn original_source_path(&self) -> &'static str {
        self.inputs.location.path()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn declaration() -> serde_json::Value {
        serde_json::json!({"scope":"original_linkerconfig_trampoline_v1",
            "original":{"file":"linkerconfig-original","bytes":4096,"sha256":"8".repeat(64)},
            "original_source_path":"/system/bin/linkerconfig","original_source_sha256":"a".repeat(64),
            "original_interpreter":"/system/bin/linker64",
            "trampoline":{"file":"linkerconfig-trampoline","bytes":4096,"sha256":"9".repeat(64)}})
    }

    fn accepted(activation: serde_json::Value) -> bool {
        let base: CohortDeclaration = serde_json::from_value(serde_json::json!({
            "schema":1,"scope":"android_base_images_v1","layout":"gsi_system_as_root",
            "system":{"file":"system.img","bytes":8192,"sha256":"a".repeat(64)},
            "vendor":{"file":"vendor.img","bytes":8192,"sha256":"b".repeat(64)}
        }))
        .unwrap();
        let value = serde_json::json!({
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
                "payload_bytes":4096,"payload_sha256":"4".repeat(64)}],
            "activation":activation});
        serde_json::from_value::<RuntimeDeclaration>(value)
            .is_ok_and(|runtime| runtime.validate(&"c".repeat(64), &base).is_ok())
    }

    #[test]
    fn fixed_activation_declaration_rejects_other_source_or_command_roles() {
        assert!(accepted(declaration()));
        for path in [
            "/host/bin/linkerconfig",
            "../linkerconfig",
            "/system/bin/init",
        ] {
            let mut changed = declaration();
            changed["original_source_path"] = serde_json::json!(path);
            assert!(!accepted(changed));
        }
        for field in ["original", "trampoline"] {
            let mut changed = declaration();
            changed[field]["file"] = serde_json::json!("../replacement");
            assert!(!accepted(changed));
        }
        let mut changed = declaration();
        changed["original_source_sha256"] = serde_json::json!("7".repeat(64));
        assert!(!accepted(changed));
        let mut changed = declaration();
        changed["activated"] = serde_json::json!(true);
        assert!(!accepted(changed));
        let mut changed = declaration();
        changed["original_source_path"] =
            serde_json::json!("/apex/com.android.runtime/bin/linkerconfig");
        assert!(!accepted(changed.clone()));
        changed["original_source_sha256"] = serde_json::json!("4".repeat(64));
        assert!(accepted(changed));
    }
}
