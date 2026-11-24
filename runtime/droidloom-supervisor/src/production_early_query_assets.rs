//! Same-owner private query inputs for the initramfs-created Android tree.
//! This borrows the existing base reservation and selected runtime manifests.
//! It never creates a legacy namespace owner or supplies a readiness result.
use super::*;
use crate::production_selection::early_generation::EarlyBaseAdmission;

pub(crate) struct EarlyQueryResources {
    base_manifest: SealedFile,
    manifest: SealedFile,
    cohort: String,
    runtime: String,
    userns: File,
    uids: IdRange,
    gids: IdRange,
    query: QueryResources,
}

impl EarlyQueryResources {
    pub(crate) fn prepare(admission: &EarlyBaseAdmission<'_>) -> Result<Self> {
        admission.revalidate()?;
        require(unsafe { libc::geteuid() } == 0, "actual root early query broker")?;
        let selection = admission.board().selection();
        let cohort = selection.base_cohort().to_owned();
        let runtime = selection.runtime_manifest().to_owned();
        require(is_digest(&cohort) && is_digest(&runtime), "early query selected manifest digests")?;
        let lease = admission.identity_lease();
        let admit = |file: &File| -> Result<()> {
            lease.broker_reject_backing_body(file)?;
            Ok(())
        };
        let base_manifest = SealedFile::open_guarded(
            Path::new(MANIFEST_ROOT), &format!("{cohort}.json"), 0, MAX_MANIFEST, &admit,
        )?;
        let raw_base = base_manifest.bounded_bytes(MAX_MANIFEST)?;
        require(format!("{:x}", Sha256::digest(&raw_base)) == cohort, "early query original base manifest")?;
        let base: CohortDeclaration = serde_json::from_slice(&raw_base)?;
        base.validate()?;
        let manifest = SealedFile::open_guarded(
            Path::new(RUNTIME_MANIFEST_ROOT), &format!("{runtime}.json"), 0,
            MAX_RUNTIME_MANIFEST, &admit,
        )?;
        require(manifest.identity.mode & 0o7777 == 0o400, "early query root-sealed runtime manifest mode")?;
        let raw = manifest.bounded_bytes(MAX_RUNTIME_MANIFEST)?;
        require(format!("{:x}", Sha256::digest(&raw)) == runtime, "early query selected runtime manifest body")?;
        let selected = crate::production_selection::kernel_first_query_inputs(
            &raw, &cohort, &base.system.sha256,
        ).map_err(|e| MountError::Io(io::Error::other(e)))?;
        let declared: QueryDeclaration = serde_json::from_value(selected)?;
        declared.validate_kernel_first(&base.system.sha256)?;
        let userns = admission.user_namespace().try_clone()?;
        let (uids, gids) = lease.broker_ranges();
        let check = || -> Result<()> { admission.revalidate()?; Ok(()) };
        let query = QueryResources::prepare_admitted(
            &declared, &Path::new(RUNTIME_IMAGE_ROOT).join(&runtime).join("images"),
            &userns, uids, gids, &admit, &check,
        )?;
        let value = Self { base_manifest, manifest, cohort, runtime, userns, uids, gids, query };
        value.revalidate(admission)?;
        Ok(value)
    }

    pub(crate) fn revalidate(&self, admission: &EarlyBaseAdmission<'_>) -> Result<()> {
        admission.revalidate()?;
        let selection = admission.board().selection();
        let original = self.userns.metadata()?;
        let current = admission.user_namespace().metadata()?;
        require(
            self.cohort == selection.base_cohort() && self.runtime == selection.runtime_manifest()
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

    pub(crate) fn mount(&self, admission: &EarlyBaseAdmission<'_>) -> Result<BorrowedFd<'_>> {
        self.revalidate(admission)?;
        Ok(self.query.mount())
    }

    /// Return only the real projected private role and its selected counterpart.
    /// Every component below is fixed by the code; no caller path is resolved.
    pub(crate) fn descriptors(
        &self, admission: &EarlyBaseAdmission<'_>, root: &File, binary: &CStr,
    ) -> Result<[File; 2]> {
        self.role(admission, root, QueryRole::parse(binary)?)
    }

    pub(crate) fn content(
        &self, admission: &EarlyBaseAdmission<'_>, root: &File,
    ) -> Result<[File; 2]> {
        self.role(admission, root, QueryRole::ContentJar)
    }

    fn role(
        &self, admission: &EarlyBaseAdmission<'_>, root: &File, role: QueryRole,
    ) -> Result<[File; 2]> {
        self.revalidate(admission)?;
        let system = open_leaf(root, c"system", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let directory = open_leaf(
            &system, if role == QueryRole::ContentJar { c"framework" } else { c"bin" },
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let original = open_leaf(&directory, role.name(), libc::O_RDONLY)?;
        let dev = open_leaf(root, c"dev", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let private = open_leaf(&dev, c"droidloom-query", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let copy = open_leaf(&private, role.name(), libc::O_RDONLY)?;
        let executable = self.query.executables.iter().find(|item| item.role == role)
            .ok_or(MountError::Rejected("early query fixed role absent"))?;
        verify_original(executable, &original, self.uids.start, self.gids.start)?;
        verify_projection(&self.query, executable, &copy)?;
        require(
            (copy.metadata()?.dev(), copy.metadata()?.ino()) ==
                (executable.copy.metadata()?.dev(), executable.copy.metadata()?.ino()),
            "early query projected inode differs from retained original role",
        )?;
        self.revalidate(admission)?;
        Ok([copy, original])
    }
}
