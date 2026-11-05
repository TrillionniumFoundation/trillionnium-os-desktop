//! Reentrant preparation before the original recovery can spawn any child.
//! These files coordinate one attempt; original owners still decide authority,
//! generation, Current and operation outcomes. A consumed spawn is never retried.
use super::{Result, fs};
use serde::Serialize;
use serde_json::Value;
use std::fs::{File, OpenOptions};
use std::io::Read;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

const ADMITTED: &str = "00-admitted.json";
const ISSUER_PLANNED: &str = "02-issuer-renewal-plan.json";
const ISSUER_COMMITTED: &str = "03-issuer-renewal-committed.json";
const SOCKETS_RETIRED: &str = "05-old-sockets-retired.json";
const SPAWN_CONSUMED: &str = "06-spawn-consumed.json";

pub(super) struct RecoveryPreparation {
    pub directory: PathBuf,
    _lock: File,
}

impl RecoveryPreparation {
    /// Acquire before reading the old deployment or changing its mount/socket
    /// state. The descriptor stays live through the entire recovered Root run.
    pub(super) fn acquire(admin: &Path, previous_generation: u64) -> Result<Self> {
        fs::root_directory(admin)?;
        Self::lock_generation(admin, previous_generation)
    }

    fn lock_generation(admin: &Path, previous_generation: u64) -> Result<Self> {
        let mut locked = Self::lock_directory(admin)?;
        // Old fixed-directory attempts have no authenticated generation
        // locator. Preserve them; never reinterpret or rearm their spawn.
        if std::fs::symlink_metadata(admin.join("recovery")).is_ok() {
            return Err(
                "legacy recovery preparation requires original-owner reconciliation".into(),
            );
        }
        let next = super::recovery_selection::successor_generation(previous_generation)?;
        locked.directory = super::recovery_selection::generation_directory(admin, next)?;
        Ok(locked)
    }

    fn lock_directory(admin: &Path) -> Result<Self> {
        let parent = std::fs::symlink_metadata(admin)?;
        if !parent.is_dir() || parent.mode() & 0o7777 != 0o700 {
            return Err("original recovery administration must be a private directory".into());
        }
        let path = admin.join("recovery.lock");
        let lock = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .mode(0o600)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
            .open(&path)?;
        let metadata = lock.metadata()?;
        if !metadata.is_file()
            || metadata.uid() != parent.uid()
            || metadata.mode() & 0o7777 != 0o600
            || metadata.nlink() != 1
            || metadata.len() != 0
            || path.canonicalize()? != path
        {
            return Err("original recovery lock custody differs".into());
        }
        lock.try_lock()
            .map_err(|_| "another original recovery still holds its preparation lock")?;
        let current = std::fs::symlink_metadata(&path)?;
        if (metadata.dev(), metadata.ino()) != (current.dev(), current.ino()) {
            return Err("original recovery lock changed while acquiring it".into());
        }
        lock.sync_all()?;
        File::open(admin)?.sync_all()?;
        Ok(Self {
            directory: admin.join("recovery-2"),
            _lock: lock,
        })
    }

    pub(super) fn admit(&self, observation: &impl Serialize) -> Result<()> {
        match std::fs::symlink_metadata(&self.directory) {
            Ok(metadata) => {
                let parent = std::fs::symlink_metadata(
                    self.directory.parent().ok_or("recovery parent absent")?,
                )?;
                if !metadata.is_dir()
                    || metadata.uid() != parent.uid()
                    || metadata.mode() & 0o7777 != 0o700
                    || self.directory.canonicalize()? != self.directory
                {
                    return Err("original recovery preparation custody differs".into());
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                fs::directory_new(&self.directory, 0o700, None)?;
            }
            Err(error) => return Err(error.into()),
        }
        // Old versions left Session logs or writer files once child creation
        // began. Refuse those too, even without this version's consume marker.
        for entry in std::fs::read_dir(&self.directory)? {
            let entry = entry?;
            if !matches!(
                entry.file_name().to_str(),
                Some(ADMITTED | ISSUER_PLANNED | ISSUER_COMMITTED | SOCKETS_RETIRED)
            ) {
                return Err(
                    "original recovery may have started: original-owner reconciliation is required"
                        .into(),
                );
            }
        }
        if self.directory.join(ISSUER_COMMITTED).try_exists()?
            && !self.directory.join(ISSUER_PLANNED).try_exists()?
        {
            return Err("original issuer commit observation has no fixed plan".into());
        }
        if (self.directory.join(SOCKETS_RETIRED).try_exists()?
            || self.directory.join(ISSUER_PLANNED).try_exists()?)
            && !self.directory.join(ADMITTED).try_exists()?
        {
            return Err("original recovery socket observation has no admission".into());
        }
        self.record(ADMITTED, observation)
    }

    pub(super) fn issuer_plan(
        &self,
    ) -> Result<Option<codex_hepta_agentd::HostIssuerLeaseRenewalPlan>> {
        match std::fs::symlink_metadata(self.directory.join(ISSUER_PLANNED)) {
            Ok(_) => Ok(Some(serde_json::from_value(self.read(ISSUER_PLANNED)?)?)),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(error) => Err(error.into()),
        }
    }

    pub(super) fn issuer_planned(
        &self,
        plan: &codex_hepta_agentd::HostIssuerLeaseRenewalPlan,
    ) -> Result<()> {
        self.read(ADMITTED)?;
        self.record(ISSUER_PLANNED, plan)
    }

    pub(super) fn issuer_committed(
        &self,
        lease: &codex_hepta_contracts::authority_lease::AuthorityLease,
    ) -> Result<()> {
        self.read(ADMITTED)?;
        let plan = self.issuer_plan()?.ok_or("original issuer plan absent")?;
        if plan.renewed_lease != *lease {
            return Err("issuer commit differs from the immutable original plan".into());
        }
        self.record(ISSUER_COMMITTED, lease)
    }

    pub(super) fn sockets_retired(&self, observation: &impl Serialize) -> Result<()> {
        self.read(ADMITTED)?;
        self.record(SOCKETS_RETIRED, observation)
    }

    /// Persist before Session::spawn or any successor Supervisor action. Even
    /// an incomplete marker forbids re-entry: loss of its reply proves nothing
    /// about whether process creation, rotation or handoff subsequently happened.
    pub(super) fn consume_spawn(&self) -> Result<()> {
        let admitted = self.read(ADMITTED)?;
        self.read(SOCKETS_RETIRED)?;
        if let Some(plan) = self.issuer_plan()? {
            let committed: codex_hepta_contracts::authority_lease::AuthorityLease =
                serde_json::from_value(self.read(ISSUER_COMMITTED)?)?;
            if committed != plan.renewed_lease {
                return Err("unconfirmed issuer plan cannot consume a successor spawn".into());
            }
        }
        fs::json_new(
            &self.directory.join(SPAWN_CONSUMED),
            &serde_json::json!({
                "schema":"trill.original-root.recovery-spawn.v1",
                "original_admission":admitted,
                "scope":"one original child-creation attempt consumed; no spawn, authority or effect success asserted"
            }),
        )
    }

    fn record(&self, name: &str, observation: &impl Serialize) -> Result<()> {
        match std::fs::symlink_metadata(self.directory.join(SPAWN_CONSUMED)) {
            Ok(_) => return Err("original recovery spawn attempt was already consumed".into()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(error.into()),
        }
        let expected = serde_json::to_value(observation)?;
        match std::fs::symlink_metadata(self.directory.join(name)) {
            Ok(_) if self.read(name)? == expected => Ok(()),
            Ok(_) => Err("original recovery observation or operation selector changed".into()),
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                fs::json_new(&self.directory.join(name), &expected)
            }
            Err(error) => Err(error.into()),
        }
    }

    fn read(&self, name: &str) -> Result<Value> {
        let path = self.directory.join(name);
        let file = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK)
            .open(&path)?;
        let metadata = file.metadata()?;
        if !metadata.is_file()
            || metadata.uid() != std::fs::symlink_metadata(&self.directory)?.uid()
            || metadata.mode() & 0o7777 != 0o600
            || metadata.nlink() != 1
            || metadata.len() == 0
            || metadata.len() > 65_536
            || path.canonicalize()? != path
        {
            return Err("original recovery observation custody or bound differs".into());
        }
        let mut bytes = Vec::new();
        file.take(65_537).read_to_end(&mut bytes)?;
        if bytes.len() > 65_536 {
            return Err("original recovery observation exceeds its bound".into());
        }
        Ok(serde_json::from_slice(&bytes)?)
    }
}

#[cfg(test)]
#[path = "recovery_preparation_tests.rs"]
mod tests;
