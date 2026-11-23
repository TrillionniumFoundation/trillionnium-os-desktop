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

/// Held public configuration for the shared-kernel service. It is never an
/// execution capability or permission to mutate a systemd unit.
pub struct SharedKernelLauncher {
    sealed: SealedFile,
    selected_digest: String,
    entry_bytes: u64,
    entry_digest: String,
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
        let published = Published::from_bytes(&bytes).map_err(io::Error::other)?;
        Ok(Some(Self {
            sealed,
            selected_digest: published.selection_sha256,
            entry_bytes: published.entry_bytes,
            entry_digest: published.entry_sha256,
        }))
    }

    /// Hold the fixed, byte-verified package entry until the transaction ends.
    ///
    /// # Errors
    /// Rejects a missing, replaced or nonmatching service executable.
    pub fn entry_program(&self) -> io::Result<PublishedServiceProgram> {
        self.revalidate()?;
        let path = Path::new("/usr/lib/droidloom/production/current/droidloom-container-entry");
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
    /// Recheck the original held program and its installed pathname.
    ///
    /// # Errors
    /// Returns an error if the package program changed.
    pub fn revalidate(&self) -> io::Result<()> {
        self.0.revalidate().map_err(io::Error::other)
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
    pub(crate) fn host_managed_launcher(&self) -> Result<Option<SharedKernelLauncher>> {
        self.revalidate()?;
        let launcher = SharedKernelLauncher::read()?;
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
    use super::*;

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
