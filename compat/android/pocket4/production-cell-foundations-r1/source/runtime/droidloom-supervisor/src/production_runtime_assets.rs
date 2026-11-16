//! Fixed, descriptor-owned runtime inputs for one admitted Android cohort.
//!
//! The installed manifest is selected by a root-owned production selection.
//! Its digest is not itself an admission capability: every preparation and
//! export also requires the same live namespace witness and reservation.
//! The two exported roles are a detached read-only runtime filesystem and
//! the held original Android init ELF. No guest-supplied path is opened here.
//!
//! This is a child of production_mounts so its reviewed sealed-file, exact
//! loop-binding and idmapped detached-mount primitives remain private.
use super::*;
use std::collections::BTreeSet;

const RUNTIME_MANIFEST_ROOT: &str = "/etc/droidloom/runtime-cohorts";
const RUNTIME_IMAGE_ROOT: &str = "/var/lib/droidloom/runtime-cohorts";
const MAX_RUNTIME_MANIFEST: u64 = 256 * 1024;
const MAX_RUNTIME_IMAGE: u64 = 16 * 1024 * 1024 * 1024;
const MAX_INIT: u64 = 32 * 1024 * 1024;

pub(crate) type RuntimeError = MountError;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ApexInput {
    name: String,
    version: u64,
    container_file: String,
    container_bytes: u64,
    container_sha256: String,
    original_apex_bytes: u64,
    original_apex_sha256: String,
    payload_bytes: u64,
    payload_sha256: String,
}

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
            self.schema == 1
                && self.scope == "android_runtime_assets_v1"
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

#[derive(Debug)]
struct RuntimeResources {
    base_manifest: SealedFile,
    manifest: SealedFile,
    image: SealedFile,
    init: SealedFile,
    mount: Option<File>,
    binding: Option<LoopBinding>,
    filesystem: Filesystem,
    mount_id: u64,
    userns: File,
    userns_identity: (u64, u64),
    uids: IdRange,
    gids: IdRange,
    host_uid: u32,
    cohort: String,
    // This duplicate shares the actual flock description, not a JSON claim.
    _reservation_retention: File,
}

impl RuntimeResources {
    fn matches_witness(&self, witness: &OwnedNamespaceWitness<'_>) -> Result<()> {
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
        Ok(())
    }
    fn cleanup(&mut self) -> Result<Vec<u64>> {
        drop(self.mount.take());
        let mut released = Vec::new();
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

#[derive(Debug, Serialize)]
pub(crate) struct RuntimeRetirement {
    detached_runtime_descriptor_closed: bool,
    original_init_descriptor_closed: bool,
    owned_loop_devices_observed_unbound: Vec<u64>,
    after_owned_tree_exit: bool,
}

impl PreparedRuntime {
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
                mount: None,
                binding: None,
                mount_id: 0,
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
        resources.matches_witness(witness)?;
        Ok(result)
    }

    pub(crate) fn descriptors_for_transfer<'a>(
        &'a mut self,
        witness: &OwnedNamespaceWitness<'_>,
    ) -> Result<[BorrowedFd<'a>; 2]> {
        require(!self.exported, "single runtime descriptor transfer")?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("runtime already retired"))?;
        resources.matches_witness(witness)?;
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
        self.exported = true;
        Ok([mount.as_fd(), resources.init.file.as_fd()])
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
        let released = resources.cleanup()?;
        drop(self.resources.take());
        Ok(RuntimeRetirement {
            detached_runtime_descriptor_closed: true,
            original_init_descriptor_closed: true,
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
