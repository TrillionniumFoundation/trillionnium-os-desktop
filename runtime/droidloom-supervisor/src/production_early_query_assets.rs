//! Same-owner private query inputs for the initramfs-created Android tree.
//! This borrows the existing base reservation and selected runtime manifests.
//! It never creates a legacy namespace owner or supplies a readiness result.
use super::*;
use crate::production_selection::early_generation::{EarlyBaseAdmission, EarlyBaseRetirement};

pub(crate) struct EarlyQueryResources {
    base_manifest: SealedFile,
    manifest: SealedFile,
    cohort: String,
    runtime: String,
    host_uid: u32,
    userns: File,
    uids: IdRange,
    gids: IdRange,
    query: QueryResources,
}

impl EarlyQueryResources {
    pub(crate) fn prepare(admission: &EarlyBaseAdmission<'_>) -> Result<Self> {
        admission.revalidate()?;
        require(
            unsafe { libc::geteuid() } == 0,
            "actual root early query broker",
        )?;
        let selection = admission.board().selection();
        let cohort = selection.base_cohort().to_owned();
        let runtime = selection.runtime_manifest().to_owned();
        require(
            is_digest(&cohort) && is_digest(&runtime),
            "early query selected manifest digests",
        )?;
        let lease = admission.identity_lease();
        let admit = |file: &File| -> Result<()> {
            lease.broker_reject_backing_body(file)?;
            Ok(())
        };
        let base_manifest = SealedFile::open_guarded(
            Path::new(MANIFEST_ROOT),
            &format!("{cohort}.json"),
            0,
            MAX_MANIFEST,
            &admit,
        )?;
        let raw_base = base_manifest.bounded_bytes(MAX_MANIFEST)?;
        require(
            format!("{:x}", Sha256::digest(&raw_base)) == cohort,
            "early query original base manifest",
        )?;
        let base: CohortDeclaration = serde_json::from_slice(&raw_base)?;
        base.validate()?;
        let manifest = SealedFile::open_guarded(
            Path::new(RUNTIME_MANIFEST_ROOT),
            &format!("{runtime}.json"),
            0,
            MAX_RUNTIME_MANIFEST,
            &admit,
        )?;
        require(
            manifest.identity.mode & 0o7777 == 0o400,
            "early query root-sealed runtime manifest mode",
        )?;
        let raw = manifest.bounded_bytes(MAX_RUNTIME_MANIFEST)?;
        require(
            format!("{:x}", Sha256::digest(&raw)) == runtime,
            "early query selected runtime manifest body",
        )?;
        let selected = crate::production_selection::kernel_first_query_inputs(
            &raw,
            &cohort,
            &base.system.sha256,
        )
        .map_err(|e| MountError::Io(io::Error::other(e)))?;
        let declared: QueryDeclaration = serde_json::from_value(selected)?;
        declared.validate_kernel_first(&base.system.sha256)?;
        let userns = admission.user_namespace().try_clone()?;
        let (uids, gids) = lease.broker_ranges();
        let check = || -> Result<()> {
            admission.revalidate()?;
            Ok(())
        };
        let query = QueryResources::prepare_admitted(
            &declared,
            &Path::new(RUNTIME_IMAGE_ROOT).join(&runtime).join("images"),
            &userns,
            uids,
            gids,
            &admit,
            &check,
        )?;
        let value = Self {
            base_manifest,
            manifest,
            cohort,
            runtime,
            host_uid: selection.spec().host_uid,
            userns,
            uids,
            gids,
            query,
        };
        value.revalidate(admission)?;
        Ok(value)
    }

    pub(crate) fn revalidate(&self, admission: &EarlyBaseAdmission<'_>) -> Result<()> {
        admission.revalidate()?;
        let selection = admission.board().selection();
        let original = self.userns.metadata()?;
        let current = admission.user_namespace().metadata()?;
        require(
            self.cohort == selection.base_cohort()
                && self.runtime == selection.runtime_manifest()
                && admission.identity_lease().broker_ranges() == (self.uids, self.gids)
                && (original.dev(), original.ino()) == (current.dev(), current.ino()),
            "early query owner, selection or namespace changed",
        )?;
        self.base_manifest.revalidate()?;
        self.manifest.revalidate()?;
        self.query.revalidate(self.uids, self.gids)?;
        admission.revalidate()?;
        Ok(())
    }

    /// Read the normal Soong JAR digest from this same original selected base
    /// manifest. A digest computed from an arbitrary runtime JAR is insufficient.
    pub(crate) fn catalog_jar_digest(&self, admission: &EarlyBaseAdmission<'_>) -> Result<String> {
        self.revalidate(admission)?;
        let raw = self.base_manifest.bounded_bytes(MAX_MANIFEST)?;
        let digest = selected_catalog_digest(&raw, &self.cohort)?;
        self.revalidate(admission)?;
        Ok(digest)
    }

    pub(crate) fn mount(&self, admission: &EarlyBaseAdmission<'_>) -> Result<BorrowedFd<'_>> {
        self.revalidate(admission)?;
        Ok(self.query.mount())
    }

    /// No query loop exists in the kernel-first layout. Its retained tmpfs,
    /// projected files and original source files may close only after the real
    /// Android root has detached and the original PIDFD has ended.
    pub(crate) fn retire_after_early_tree(self, retired: &EarlyBaseRetirement) -> Result<EarlyQueryRetirement> {
        retired.verify_mount_retirement(&self.userns, self.host_uid, &self.cohort)?;
        self.query.revalidate(self.uids, self.gids)?;
        let value = EarlyQueryRetirement { cohort: self.cohort.clone(), runtime: self.runtime.clone() };
        drop(self);
        Ok(value)
    }

    /// Return only the real projected private role and its selected counterpart.
    /// Every component below is fixed by the code; no caller path is resolved.
    pub(crate) fn descriptors(
        &self,
        admission: &EarlyBaseAdmission<'_>,
        root: &File,
        binary: &CStr,
    ) -> Result<[File; 2]> {
        self.role(admission, root, QueryRole::parse(binary)?)
    }

    pub(crate) fn content(
        &self,
        admission: &EarlyBaseAdmission<'_>,
        root: &File,
    ) -> Result<[File; 2]> {
        self.role(admission, root, QueryRole::ContentJar)
    }

    fn role(
        &self,
        admission: &EarlyBaseAdmission<'_>,
        root: &File,
        role: QueryRole,
    ) -> Result<[File; 2]> {
        self.revalidate(admission)?;
        let system = open_leaf(root, c"system", libc::O_PATH | libc::O_DIRECTORY)?;
        let directory = open_leaf(
            &system,
            if role == QueryRole::ContentJar {
                c"framework"
            } else {
                c"bin"
            },
            libc::O_PATH | libc::O_DIRECTORY,
        )?;
        let original = open_leaf(&directory, role.name(), libc::O_RDONLY)?;
        let dev = open_leaf(root, c"dev", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let private = open_leaf(&dev, c"droidloom-query", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let copy = open_leaf(&private, role.name(), libc::O_RDONLY)?;
        let executable = self
            .query
            .executables
            .iter()
            .find(|item| item.role == role)
            .ok_or(MountError::Rejected("early query fixed role absent"))?;
        verify_original(executable, &original, self.uids.start, self.gids.start)?;
        verify_projection(&self.query, executable, &copy)?;
        require(
            (copy.metadata()?.dev(), copy.metadata()?.ino())
                == (
                    executable.copy.metadata()?.dev(),
                    executable.copy.metadata()?.ino(),
                ),
            "early query projected inode differs from retained original role",
        )?;
        self.revalidate(admission)?;
        Ok([copy, original])
    }
}

/// Only the actual retained query owner can issue this result. It cannot be
/// deserialized or replaced with a package manifest/retirement assertion.
pub(crate) struct EarlyQueryRetirement {
    cohort: String,
    runtime: String,
}
impl EarlyQueryRetirement {
    pub(crate) fn verify_selection(&self, cohort: &str, runtime: &str) -> Result<()> {
        require(self.cohort == cohort && self.runtime == runtime,
            "retired early query belongs to another selected release")
    }
}

fn selected_catalog_digest(raw: &[u8], selected_cohort: &str) -> Result<String> {
    require(
        raw.len() as u64 <= MAX_MANIFEST
            && is_digest(selected_cohort)
            && format!("{:x}", Sha256::digest(raw)) == selected_cohort,
        "catalog original selected base manifest body differs",
    )?;
    let observer = crate::production_mounts::selected_early_observer(raw)?;
    Ok(observer.frontend.input_bridge_jar_sha256)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn catalog_jar_requires_the_exact_selected_four_image_chain_and_normal_frontend_declaration() {
        use droidloom_contracts::system_ext as contract;
        let normal = serde_json::json!({
            "schema":3,"scope":"android_base_images_v3","layout":"gsi_system_as_root",
            "system":{"file":"system.img","bytes":4096,"sha256":contract::SYSTEM_SHA256},
            "vendor":{"file":"vendor.img","bytes":4096,"sha256":"1".repeat(64)},
            "system_ext_lib64":{"file":contract::FILE,"bytes":4096,"sha256":"2".repeat(64),
                "target":contract::TARGET,"source_system_sha256":contract::SYSTEM_SHA256,
                "source_vendor_sha256":"1".repeat(64)},
            "system_ext_readiness":{"file":contract::READINESS_FILE,"bytes":4096,"sha256":"3".repeat(64),
                "targets":contract::READINESS_TARGETS,"source_system_sha256":contract::SYSTEM_SHA256,
                "source_vendor_sha256":"1".repeat(64),"source_system_ext_lib64_sha256":"2".repeat(64),
                "observer_sha256":"4".repeat(64),"init_rc_sha256":contract::OBSERVER_ONLY_RC_SHA256,
                "frontend":{"input_bridge_wrapper_sha256":"5".repeat(64),"input_bridge_jar_sha256":"6".repeat(64),
                    "input_bridge_init_rc_sha256":"7".repeat(64),"task_launcher_sha256":"8".repeat(64)}}});
        let bytes = serde_json::to_vec(&normal).unwrap();
        let cohort = format!("{:x}", Sha256::digest(&bytes));
        assert_eq!(
            selected_catalog_digest(&bytes, &cohort).unwrap(),
            "6".repeat(64)
        );
        assert!(selected_catalog_digest(&bytes, &"9".repeat(64)).is_err());
        for mutation in 0..4 {
            let mut changed = normal.clone();
            match mutation {
                0 => {
                    changed["system_ext_readiness"]["source_vendor_sha256"] =
                        serde_json::json!("9".repeat(64))
                }
                1 => {
                    changed["system_ext_readiness"]["targets"][2] =
                        serde_json::json!("/data/arbitrary")
                }
                2 => {
                    changed["system_ext_readiness"]
                        .as_object_mut()
                        .unwrap()
                        .remove("frontend");
                }
                _ => {
                    changed["system_ext_readiness"]["frontend"]["classpath"] =
                        serde_json::json!("/data/arbitrary.jar")
                }
            }
            let bytes = serde_json::to_vec(&changed).unwrap();
            assert!(
                selected_catalog_digest(&bytes, &format!("{:x}", Sha256::digest(&bytes))).is_err()
            );
        }
    }
}
