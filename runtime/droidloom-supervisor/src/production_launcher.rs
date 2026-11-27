//! Public launch selection contains only the private selection's digest. The
//! desktop never opens cell.json, mutable Android data or the setup lock.

use super::*;

const LAUNCHER: &str = "/etc/droidloom/container-launcher.json";

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Published {
    schema: String,
    launcher: String,
    selection_sha256: String,
    entry_bytes: u64,
    entry_sha256: String,
    bootstrap_bytes: u64,
    bootstrap_sha256: String,
}

impl Published {
    fn from_bytes(bytes: &[u8]) -> Result<Self> {
        let result: Self = serde_json::from_slice(bytes)?;
        if result.schema != "droidloom-public-launcher-v3"
            || result.launcher != SHARED_LAUNCHER
            || !digest(&result.selection_sha256)
            || !digest(&result.entry_sha256)
            || !digest(&result.bootstrap_sha256)
            || !(64..=crate::production_service_elf::MAX_SERVICE as u64)
                .contains(&result.bootstrap_bytes)
            || result.bootstrap_sha256 == result.entry_sha256
            || result.bootstrap_sha256 == crate::production_execution_profile::INIT_SHA256
            || !(64..=crate::production_service_elf::MAX_SERVICE as u64)
                .contains(&result.entry_bytes)
        {
            return Err(SelectionError::Rejected(
                "unsupported public container launcher",
            ));
        }
        Ok(result)
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct EarlyPublished {
    schema:String, launcher:String, selection_sha256:String, manager_sha256:String, manager_bytes:u64,
}
impl EarlyPublished {
    pub(super) fn owner(&self)->(&str,&str,u64) {(&self.selection_sha256,&self.manager_sha256,self.manager_bytes)}
    pub(super) fn parse(bytes:&[u8])->Result<Self> {
        let value:Self=serde_json::from_slice(bytes)?;
        if value.schema!="droidloom-public-early-launcher-v1" || value.launcher!=EARLY_LAUNCHER ||
           !digest(&value.selection_sha256) || !digest(&value.manager_sha256) ||
           !(64..=crate::production_service_elf::MAX_SERVICE as u64).contains(&value.manager_bytes) {
            return Err(SelectionError::Rejected("unsupported public kernel-first Android owner"));
        }
        Ok(value)
    }
}

/// Held public configuration for the shared-kernel service. It is never an
/// execution capability or permission to mutate a systemd unit.
pub struct SharedKernelLauncher {
    sealed: SealedFile,
    selected_digest: String,
    entry_bytes: u64,
    entry_digest: String,
    early: bool,
}

impl SharedKernelLauncher {
    /// Read the fixed root-owned, publicly readable launch selector. Its
    /// absence leaves existing development and production layouts untouched.
    ///
    /// # Errors
    /// Rejects malformed content, unsafe file custody or concurrent changes.
    pub fn read() -> io::Result<Option<Self>> {
        let (sealed, bytes) = match SealedFile::read(Path::new(LAUNCHER), SELECTION_LIMIT) {
            Ok(value) => value,
            Err(SelectionError::Io(error)) if error.kind() == io::ErrorKind::NotFound => {
                return Ok(None);
            }
            Err(error) => return Err(io::Error::other(error)),
        };
        if !matches!(sealed.node.mode & 0o7777, 0o444 | 0o644) {
            return Err(io::Error::other(
                "public container launcher must have mode 0444 or 0644",
            ));
        }
        let schema:serde_json::Value=serde_json::from_slice(&bytes)?;
        if schema["schema"]=="droidloom-public-early-launcher-v1" {
            let published=EarlyPublished::parse(&bytes).map_err(io::Error::other)?;
            return Ok(Some(Self{sealed,selected_digest:published.selection_sha256,entry_bytes:published.manager_bytes,
                entry_digest:published.manager_sha256,early:true}));
        }
        let published = Published::from_bytes(&bytes).map_err(io::Error::other)?;
        Ok(Some(Self {
            sealed,
            selected_digest: published.selection_sha256,
            entry_bytes: published.entry_bytes,
            entry_digest: published.entry_sha256,
            early:false,
        }))
    }

    /// Route the normal system service only after checking both installed selectors.
    /// The selected resource owner subsequently holds its full private configuration lock.
    pub fn early_service_selected() -> io::Result<bool> {
        let public = Self::read()?;
        let private = match SealedFile::read(Path::new(SELECTION), SELECTION_LIMIT) {
            Ok(value) => Some(value),
            Err(SelectionError::Io(error)) if error.kind() == io::ErrorKind::NotFound => None,
            Err(error) => return Err(io::Error::other(error)),
        };
        let record = private.as_ref().map(|(_, bytes)| -> Result<Record> {
            let row = serde_json::from_slice(bytes)?;
            validate_record(&row)?;
            Ok(row)
        }).transpose().map_err(io::Error::other)?;
        let selection = record.as_ref().zip(private.as_ref()).map(|(row, (file, _))| {
            (row.schema.as_str(), file.sha256.as_str(), file.node.mode & 0o7777)
        });
        let publication = public.as_ref().map(|p| (p.early, p.selected_digest.as_str()));
        let early = service_route(selection, publication).map_err(io::Error::other)?;
        if early {
            let release = record.as_ref().and_then(|r| r.normal_host_release.as_ref())
                .ok_or_else(|| io::Error::other("early service has no normal host release"))?;
            let launcher = public.as_ref().ok_or_else(|| io::Error::other("public early launcher absent"))?;
            if (release.manager.bytes, release.manager.sha256.as_str())
                != (launcher.entry_bytes, launcher.entry_digest.as_str()) {
                return Err(io::Error::other("public manager differs from the same private normal host release"));
            }
        }
        if let Some((file, _)) = private { file.revalidate().map_err(io::Error::other)?; }
        if let Some(file) = public { file.revalidate()?; }
        Ok(early)
    }

    /// True when Android PID 1 was created during the host kernel boot.
    pub fn early_kernel_boot(&self)->bool {self.early}
    pub(crate) fn public_selector_sha256(&self) -> &str { &self.sealed.sha256 }
    pub(super) fn matches_private_early(&self,digest:&str)->bool {self.early && self.selected_digest==digest}

    /// Hold the fixed, byte-verified package entry until the transaction ends.
    ///
    /// # Errors
    /// Rejects a missing, replaced or nonmatching service executable.
    pub fn entry_program(&self) -> io::Result<PublishedServiceProgram> {
        self.revalidate()?;
        let path=Path::new(if self.early {"/usr/lib/droidloom/production/current/droidloomd"} else {"/usr/lib/droidloom/production/current/droidloom-container-entry"});
        let (file, bytes) =
            SealedFile::read(path, crate::production_service_elf::MAX_SERVICE as u64)
                .map_err(io::Error::other)?;
        if file.node.bytes != self.entry_bytes
            || file.sha256 != self.entry_digest
            || file.node.mode & 0o7777 != 0o755
        {
            return Err(io::Error::other(
                "fixed service ELF differs from its root-published size, mode or digest",
            ));
        }
        crate::production_service_elf::inspect_container_service_elf(&bytes)?;
        file.revalidate_path().map_err(io::Error::other)?;
        self.revalidate()?;
        Ok(PublishedServiceProgram(file))
    }

    /// Verify that the original public selector is still installed.
    ///
    /// # Errors
    /// Returns an error if its name, owner, inode or contents changed.
    pub fn revalidate(&self) -> io::Result<()> {
        self.sealed.revalidate().map_err(io::Error::other)
    }
}

/// A fixed non-writable program retained for a systemd transaction.
pub struct PublishedServiceProgram(SealedFile);

impl PublishedServiceProgram {
    pub(crate) fn held_file(&self) -> &File { &self.0.file }

    /// Full bytes were checked at acquisition. Subsequent local progress
    /// retains those descriptors and checks all inode fields and the name.
    pub(crate) fn revalidate_metadata(&self) -> io::Result<()> {
        self.0.revalidate_path().map_err(io::Error::other)
    }
    pub(crate) fn matches_executable(&self, actual: &File) -> io::Result<bool> {
        self.revalidate()?;
        let matches = Node::from(&actual.metadata()?) == self.0.node;
        self.revalidate()?;
        Ok(matches)
    }
    pub(crate) fn content_identity(&self) -> (u64, String) {
        (self.0.node.bytes, self.0.sha256.clone())
    }

    pub(super) fn matches_current_process(&self)->io::Result<bool> {
        let active=std::fs::metadata("/proc/self/exe")?;
        Ok((active.dev(),active.ino())==(self.0.node.device,self.0.node.inode))
    }

    /// Recheck the original held program and its installed pathname.
    ///
    /// # Errors
    /// Returns an error if the package program changed.
    pub fn revalidate(&self) -> io::Result<()> {
        self.0.revalidate().map_err(io::Error::other)
    }
}

fn service_route(private: Option<(&str, &str, u32)>, public: Option<(bool, &str)>) -> Result<bool> {
    match (private, public) {
        (Some((EARLY_SCHEMA, private, 0o400)), Some((true, public))) if private == public => Ok(true),
        (Some((SHARED_SCHEMA, private, _)), Some((false, public))) if private == public => Ok(false),
        (Some((SCHEMA | PERSISTENT_SCHEMA, _, _)) | None, None) => Ok(false),
        _ => Err(SelectionError::Rejected("system service launch selectors are incomplete or belong to different releases")),
    }
}

fn paired(host_managed: bool, selection_sha256: &str, published: Option<&str>) -> Result<bool> {
    match (host_managed, published) {
        (false, None) => Ok(false),
        (true, Some(digest)) if digest == selection_sha256 => Ok(true),
        _ => Err(SelectionError::Rejected(
            "private and public launch selections are incomplete or belong to different generations",
        )),
    }
}

impl ProductionSelection {
    pub(crate) fn normal_presenter(&self) -> Result<PublishedServiceProgram> {
        let release = self.normal_host_release()?;
        let pin = &release.presenter;
        let (file, _) = SealedFile::read(
            Path::new(crate::normal_host_release::PRESENTER),
            crate::normal_host_release::MAX_PROGRAM_BYTES,
        )?;
        if file.node.mode != libc::S_IFREG | 0o755
            || file.node.bytes != pin.bytes || file.sha256 != pin.sha256 {
            return Err(SelectionError::Rejected("presenter differs from the same private normal host release"));
        }
        file.revalidate_path()?;
        self.revalidate()?;
        Ok(PublishedServiceProgram(file))
    }

    pub(crate) fn host_managed_launcher(&self) -> Result<Option<SharedKernelLauncher>> {
        self.revalidate()?;
        if self.early_boot {return Err(SelectionError::Rejected("kernel-created Android requires its independent early-generation owner"));}
        let launcher = SharedKernelLauncher::read()?;
        if launcher.as_ref().is_some_and(SharedKernelLauncher::early_kernel_boot) {
            return Err(SelectionError::Rejected("early kernel launcher requires its matching private v4 selection"));
        }
        paired(
            self.host_managed,
            &self.selected.sha256,
            launcher.as_ref().map(|l| l.selected_digest.as_str()),
        )?;
        self.revalidate()?;
        Ok(launcher)
    }
}

/// The real service-side read-only preparation phase, under the same root
/// configuration lock used by package maintenance and the production broker.
pub struct PreparedContainerSelection {
    lock: ConfigurationReadGuard,
    selection: ProductionSelection,
    public: SharedKernelLauncher,
}

impl PreparedContainerSelection {
    /// Hold the versioned cohort, original cell specification and matching
    /// public launch selection. No namespace, process or readiness is created.
    ///
    /// # Errors
    /// Requires the existing configuration authority and a complete matched pair.
    pub fn acquire() -> io::Result<Self> {
        let lock = ConfigurationReadGuard::acquire()?;
        let selection = ProductionSelection::load(&lock, Path::new(SPECIFICATION), 0)
            .map_err(io::Error::other)?;
        let public = selection
            .host_managed_launcher()
            .map_err(io::Error::other)?
            .ok_or_else(|| io::Error::other("shared-kernel container launch was not selected"))?;
        let owner = Self {
            lock,
            selection,
            public,
        };
        owner.revalidate()?;
        Ok(owner)
    }

    /// Digest of the private choice bound to this held public release.
    pub fn selection_digest(&self) -> &str {
        &self.public.selected_digest
    }

    /// Pin the release executable for comparison with the kernel's live peer.
    ///
    /// # Errors
    /// Rejects a different service binary or release.
    pub fn entry_program(&self) -> io::Result<PublishedServiceProgram> {
        self.revalidate()?;
        self.public.entry_program()
    }

    /// Match the original delegated ranges, role and durable data reservation
    /// to the two kernel-held processes for this release.
    ///
    /// # Errors
    /// Rejects a mismatched map, missing owner lease or changed selection.
    pub fn verify_oci_identities(&self, guest_proc: &File, owner_proc: &File) -> io::Result<()> {
        self.revalidate()?;
        let spec = self.selection.spec();
        let authority = crate::production_identity::IdentityAuthority::inspect(spec)
            .map_err(io::Error::other)?;
        authority
            .verify_oci_owner_lease(spec, self.selection.base_cohort(), owner_proc)
            .map_err(io::Error::other)?;
        crate::production_namespace::verify_container_peer_maps(
            guest_proc,
            spec.subordinate_uids,
            spec.subordinate_gids,
        )
        .map_err(io::Error::other)?;
        self.revalidate()
    }

    /// Hold the exact effective library mount before allowing the guest bootstrap to start.
    pub fn observe_library_mount(&self,guest:&File,owner:&File)->io::Result<ContainerLibraryMount> {
        self.revalidate()?;
        let spec=self.selection.spec();
        let authority=crate::production_identity::IdentityAuthority::inspect(spec).map_err(io::Error::other)?;
        let excluded=authority.oci_owner_protected_inodes(spec,self.selection.base_cohort(),owner).map_err(io::Error::other)?;
        let observed=crate::production_mounts::system_ext::ObservedExtension::from_guest(self.selection.base_cohort(),guest,&excluded,(spec.subordinate_uids,spec.subordinate_gids)).map_err(io::Error::other)?;
        authority.verify_oci_owner_lease(spec,self.selection.base_cohort(),owner).map_err(io::Error::other)?;
        self.revalidate()?;
        Ok(ContainerLibraryMount(observed))
    }
    /// Borrow only the sealed public release file for projection as a
    /// read-only mount at /etc/droidloom/container-launcher.json in the cell.
    /// The private selection and original data descriptors never leave the broker.
    ///
    /// # Errors
    /// Requires the same private configuration lock and original public file.
    pub fn public_release_file(&self) -> io::Result<std::os::fd::BorrowedFd<'_>> {
        use std::os::fd::AsFd;
        self.revalidate()?;
        Ok(self.public.sealed.file.as_fd())
    }

    /// Read the selected root-owned startup manifest and report its actual
    /// execution ABI. No image body or mutable data is opened.
    ///
    /// # Errors
    /// Rejects a changed choice, unsealed manifest, wrong digest or unknown ABI.
    pub fn runtime_entry_description(&self) -> io::Result<&'static str> {
        self.revalidate()?;
        let hash = self.selection.runtime_manifest();
        let path = Path::new("/etc/droidloom/runtime-cohorts").join(format!("{hash}.json"));
        let (file, bytes) = SealedFile::read(&path, 256 * 1024).map_err(io::Error::other)?;
        if file.node.mode & 0o7777 != 0o400 || file.sha256 != hash {
            return Err(io::Error::other(
                "runtime manifest must match the sealed private selection",
            ));
        }
        let entry = crate::production_runtime_assets::declared_boot_entry(
            &bytes,
            self.selection.base_cohort(),
        )
        .map_err(io::Error::other)?;
        file.revalidate().map_err(io::Error::other)?;
        self.revalidate()?;
        Ok(entry)
    }

    /// Check the live lock and both original file identities.
    ///
    /// # Errors
    /// A replaced selection or invalid configuration/maintenance state stops startup.
    pub fn revalidate(&self) -> io::Result<()> {
        self.lock.revalidate()?;
        self.selection.revalidate().map_err(io::Error::other)?;
        self.public.revalidate()?;
        self.lock.revalidate()
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn production_service_preserves_legacy_and_requires_a_matching_kernel_first_pair() {
        use super::*;
        let selected = "same";
        assert!(!service_route(None, None).unwrap());
        for old in [SCHEMA, PERSISTENT_SCHEMA] {
            assert!(!service_route(Some((old, selected, 0o400)), None).unwrap());
        }
        assert!(!service_route(Some((SHARED_SCHEMA, selected, 0o400)), Some((false, selected))).unwrap());
        let v4 = Some((EARLY_SCHEMA, selected, 0o400));
        assert!(service_route(v4, Some((true, selected))).unwrap());
        for invalid in [None, Some((true, "other")), Some((false, selected))] {
            assert!(service_route(v4, invalid).is_err());
        }
        for invalid in [None, Some((EARLY_SCHEMA, selected, 0o644)), Some((SCHEMA, selected, 0o400))] {
            assert!(service_route(invalid, Some((true, selected))).is_err());
        }
    }
    use super::*;

    #[test]
    fn early_selector_requires_its_own_exact_manager_contract() {
        let row = serde_json::json!({"schema":"droidloom-public-early-launcher-v1","launcher":EARLY_LAUNCHER,
            "selection_sha256":"a".repeat(64),"manager_sha256":"b".repeat(64),"manager_bytes":32768});
        let valid = serde_json::to_vec(&row).unwrap();
        assert!(EarlyPublished::parse(&valid).is_ok());
        assert!(Published::from_bytes(&valid).is_err());
        for (field, value) in [("schema","droidloom-public-launcher-v3"),("launcher",SHARED_LAUNCHER),
                               ("selection_sha256","unknown"),("manager_sha256","invalid"),("ExecStart","/tmp/elf")] {
            let mut wrong = row.clone();
            wrong[field]=value.into();
            assert!(EarlyPublished::parse(&serde_json::to_vec(&wrong).unwrap()).is_err());
        }
    }

    #[test]
    fn published_choice_is_versioned_and_cannot_supply_a_command() {
        let input = serde_json::json!({"schema":"droidloom-public-launcher-v3","launcher":SHARED_LAUNCHER,"selection_sha256":"a".repeat(64),"entry_sha256":"b".repeat(64),"entry_bytes":32768,"bootstrap_sha256":"c".repeat(64),"bootstrap_bytes":65536});
        assert!(Published::from_bytes(input.to_string().as_bytes()).is_ok());
        for (key, value) in [
            ("schema", "v2"),
            ("launcher", "/system/bin/init"),
            ("selection_sha256", "wrong"),
            ("command", "/bin/sh"),
        ] {
            let mut changed = input.clone();
            changed[key] = serde_json::json!(value);
            assert!(
                Published::from_bytes(changed.to_string().as_bytes()).is_err(),
                "{key}"
            );
        }
    }

    #[test]
    fn mixed_missing_and_stale_publication_cannot_select_either_backend() {
        let p = "a".repeat(64);
        let q = "b".repeat(64);
        assert!(!paired(false, &p, None).unwrap());
        assert!(paired(true, &p, Some(&p)).unwrap());
        assert!(paired(false, &p, Some(&p)).is_err());
        assert!(paired(true, &p, None).is_err());
        assert!(paired(true, &p, Some(&q)).is_err());
    }
}

/// Release-bound keeper of the effective immutable library mount.
pub struct ContainerLibraryMount(crate::production_mounts::system_ext::ObservedExtension);
impl ContainerLibraryMount {
    /// Check the still-held effective mount and kernel loop sources.
    pub fn revalidate(&self)->io::Result<()> {self.0.revalidate().map_err(io::Error::other)}
}
