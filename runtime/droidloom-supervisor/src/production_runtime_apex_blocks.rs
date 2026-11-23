//! Finite original APEX block ownership in the existing runtime guard.
//!
//! Builtins retain their original readonly-system source contract. Compressed
//! roles use a separate typed provider that streams the admitted CAPEX into
//! a kernel-sealed output. A caller's writable /data output cannot enter either.
//! No loop/control FD is sent to Android. Original apexd execution, AVB
//! signature verification, dm ownership and mount publication remain separate.
use super::*;
use crate::production_execution::RuntimeMacOwner;
use crate::production_execution_profile::apex_inputs;
use crate::production_mac::MacPreflight;
use crate::production_namespace::{ExecutedInitGeneration, ExecutedInitWitness};
use crate::production_private_loop_owner::compressed::ImmutableCapex;
use crate::production_private_loop_owner::{PrivateLoopDevice, PrivateLoopOwner};
use std::rc::Rc;
use std::time::Instant;

#[path = "production_runtime_apex_mount_helper.rs"]
mod mount_helper;
#[path = "production_runtime_apex_mounts.rs"]
mod mounts;
use mounts::Publication;
#[path = "production_runtime_init_cleanup.rs"]
mod init_cleanup;
pub(crate) use init_cleanup::OriginalInitCleanup;
#[path = "production_runtime_init_mounts.rs"]
mod init_mounts;
pub(crate) use init_mounts::OriginalInitMount;
#[path = "production_runtime_init_propagation.rs"]
mod init_propagation;
pub(crate) use init_propagation::{OriginalInitPropagation, OriginalInitPropagationKind};
#[path = "production_runtime_init_storage.rs"]
mod init_storage;
pub(crate) use init_storage::{OriginalInitStorage, verify_storage_root};
#[path = "production_runtime_init_bootstrap_bind.rs"]
mod init_bootstrap_bind;
pub(crate) use init_bootstrap_bind::OriginalInitBootstrapBind;
#[path = "production_runtime_init_storage_binds.rs"]
mod init_storage_binds;
pub(crate) use init_storage_binds::{
    OriginalInitStorageBind, OriginalInitStorageBindKind, OriginalInitStorageDirectories,
};

const ORIGINAL_LABEL: &[u8] = b"u:object_r:system_file:s0\0";

fn original_metadata(file: &File, uid: u32, gid: u32, bytes: u64) -> Result<FileIdentity> {
    let meta = file.metadata()?;
    let flags = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    require(
        meta.mode() == libc::S_IFREG | 0o644
            && meta.uid() == uid
            && meta.gid() == gid
            && meta.nlink() == 1
            && meta.len() == bytes
            && flags >= 0
            && flags & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY,
        "exact original builtin APEX metadata and readonly body descriptor",
    )?;
    let mut fs: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut fs) })?;
    require(
        fs.f_flag as u64 & (READONLY_FLAGS | MOUNT_ATTR_NOEXEC) == READONLY_FLAGS,
        "original builtin APEX remains on the admitted readonly system filesystem",
    )?;
    let mut names = [0_u8; 128];
    let count =
        unsafe { libc::flistxattr(file.as_raw_fd(), names.as_mut_ptr().cast(), names.len()) };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        count as usize == b"security.selinux\0".len()
            && &names[..count as usize] == b"security.selinux\0",
        "complete original builtin APEX xattr inventory",
    )?;
    let mut label = [0_u8; 128];
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            label.as_mut_ptr().cast(),
            label.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        count as usize == ORIGINAL_LABEL.len() && &label[..count as usize] == ORIGINAL_LABEL,
        "exact original builtin APEX SELinux label including NUL",
    )?;
    Ok(FileIdentity::of(&meta))
}

#[derive(Debug)]
struct ApexLoop {
    index: usize,
    source: File,
    identity: FileIdentity,
    compressed: Option<Rc<ImmutableCapex>>,
    generation: ExecutedInitGeneration,
    binding: Option<PrivateLoopDevice>,
    publication: Option<Publication>,
    retired_device: Option<u64>,
}

#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
enum PoolPhase {
    #[default]
    Fresh,
    Creating,
    Live,
    Retiring,
    Retired,
}

#[derive(Debug, Default)]
pub(super) struct ApexLoops {
    context: Option<RuntimeMacOwner>,
    pool: Option<PrivateLoopOwner>,
    phase: PoolPhase,
    rows: Vec<ApexLoop>,
    // Actual successful retirements survive later failures and retries.
    retired: Vec<u64>,
    requested: Option<RetainedApexdCapexCustody>,
    requested_retired: Vec<capex_custody::RetiredCapexCustody>,
}

impl ApexLoops {
    fn empty_fresh(&self) -> bool {
        self.phase == PoolPhase::Fresh
            && self.requested.is_none()
            && self.requested_retired.is_empty()
            && self.pool.is_none()
            && self.rows.is_empty()
            && self.retired.is_empty()
    }

    pub(super) fn bind_owner(&mut self, context: RuntimeMacOwner) -> Result<()> {
        require(
            self.empty_fresh() && self.context.is_none(),
            "APEX MAC owner binding is single-use before mutation",
        )?;
        context.objects()?;
        self.context = Some(context);
        Ok(())
    }

    fn owner(&self) -> Result<RuntimeMacOwner> {
        let owner = self.context.as_ref().ok_or(MountError::Rejected(
            "original paired APEX MAC/selection owner absent",
        ))?;
        owner.objects()?;
        Ok(owner.clone())
    }

    fn ensure_pool(
        &mut self,
        mac: &MacPreflight,
        selection: &crate::production_selection::ProductionSelection,
    ) -> Result<()> {
        require(
            self.requested.is_none() && self.requested_retired.is_empty(),
            "ordinary pool path rejects requested transaction or retirement history",
        )?;
        let owner = self.owner()?;
        owner.require_pair(mac, selection)?;
        match self.phase {
            PoolPhase::Fresh => {
                require(
                    self.empty_fresh(),
                    "fresh APEX pool has unexplained resource custody",
                )?;
                // Retain the exact context and mark the attempted mutation
                // before even the first private tmpfs/node constructor runs.
                self.phase = PoolPhase::Creating;
                self.pool = Some(PrivateLoopOwner::create(mac, selection)?);
                self.phase = PoolPhase::Live;
            }
            PoolPhase::Live => {}
            _ => {
                return Err(MountError::Rejected(
                    "APEX private pool is incomplete or retiring",
                ));
            }
        }
        self.pool
            .as_ref()
            .ok_or(MountError::Rejected("live private APEX pool absent"))?
            .revalidate(mac, selection)?;
        Ok(())
    }

    pub(super) fn revalidate(&self) -> Result<()> {
        require(
            self.requested.is_none() && self.requested_retired.is_empty(),
            "ordinary APEX readiness rejects pending or retired requested custody",
        )?;
        if self.empty_fresh() {
            if let Some(owner) = &self.context {
                owner.objects()?;
            }
            return Ok(());
        }
        require(
            self.phase == PoolPhase::Live && self.retired.is_empty(),
            "APEX block owner is incomplete or retiring",
        )?;
        let owner = self.owner()?;
        let (mac, selection) = owner.objects()?;
        self.pool
            .as_ref()
            .ok_or(MountError::Rejected("live private APEX pool absent"))?
            .revalidate(mac, selection)?;
        self.revalidate_existing_rows(mac, selection)?;
        owner.objects()?;
        Ok(())
    }

    // The legacy row checks are shared without changing their contents.
    // Pending checks must never skip old rows because their pool has moved.
    fn revalidate_existing_rows(
        &self,
        mac: &MacPreflight,
        selection: &crate::production_selection::ProductionSelection,
    ) -> Result<()> {
        for row in &self.rows {
            require(
                row.retired_device.is_none(),
                "retired APEX binding cannot be reused",
            )?;
            require(
                original_metadata(
                    &row.source,
                    row.identity.uid,
                    row.identity.gid,
                    row.identity.bytes,
                )? == row.identity,
                "held original builtin APEX source changed",
            )?;
            if let Some(output) = &row.compressed {
                output.revalidate()?;
                require(
                    output.archive()?.index() == row.index
                        && FileIdentity::of(&output.container()?.metadata()?) == row.identity,
                    "compressed output must retain this exact original system container and role",
                )?;
            } else {
                apex_inputs::original_builtin(row.index).map_err(MountError::Rejected)?;
            }
            let binding = row.binding.as_ref().ok_or(MountError::Rejected(
                "APEX loop preparation did not complete",
            ))?;
            require(
                binding.apex_index() == row.index,
                "private APEX binding fixed role differs",
            )?;
            binding.revalidate(mac, selection)?;
            if let Some(publication) = &row.publication {
                publication.revalidate()?;
            }
        }
        Ok(())
    }

    pub(super) fn require_requested(&self, slot: &RetainedApexdCapexCustody) -> Result<()> {
        let original = self.requested.as_ref().ok_or(MountError::Rejected(
            "original runtime requested slot absent",
        ))?;
        require(
            original.same(slot) && original.binding()? == slot.binding()?,
            "same original runtime slot and opaque apexd request binding",
        )
    }

    // Only the original Exclusive guard may use this separate in-flight gate.
    // Ordinary revalidate() and Shared observers remain strict above.
    pub(super) fn revalidate_requested(&self, slot: &RetainedApexdCapexCustody) -> Result<()> {
        self.require_requested(slot)?;
        require(
            self.phase == PoolPhase::Live
                && self.retired.is_empty()
                && self.requested_retired.is_empty(),
            "requested runtime owner is incomplete or retiring",
        )?;
        let owner = self.owner()?;
        let source = slot.source()?;
        let (mac, selection) = source.owner().objects()?;
        owner.require_pair(mac, selection)?;
        match slot.revalidate_static()? {
            capex_custody::PoolLocation::InSlot => {
                require(
                    self.pool.is_none(),
                    "same pool appears in both ledger and slot",
                )?;
            }
            capex_custody::PoolLocation::InLedger => {
                self.pool
                    .as_ref()
                    .ok_or(MountError::Rejected(
                        "returned original requested pool absent",
                    ))?
                    .revalidate(mac, selection)?;
            }
            _ => return Err(MountError::Rejected("requested pool custody is incomplete")),
        }
        self.revalidate_existing_rows(mac, selection)?;
        owner.objects()?;
        Ok(())
    }

    pub(super) fn begin_requested(&mut self, slot: &RetainedApexdCapexCustody) -> Result<()> {
        self.revalidate()?;
        let source = slot.source()?;
        source.revalidate_static().map_err(MountError::Io)?;
        apex_inputs::original_compressed(source.index()).map_err(MountError::Rejected)?;
        let owner = self.owner()?;
        let (mac, selection) = source.owner().objects()?;
        owner.require_pair(mac, selection)?;
        require(
            self.requested.is_none()
                && !self.rows.iter().any(|row| row.index == source.index())
                && !self
                    .requested_retired
                    .iter()
                    .any(|row| row.index() == source.index() || row.binding() == source.binding())
                && self
                    .rows
                    .iter()
                    .filter(|row| row.compressed.is_some())
                    .count()
                    + self.requested_retired.len()
                    < 28,
            "one requested transaction for this fixed compressed role and request",
        )?;
        require(
            (self.phase == PoolPhase::Live && self.pool.is_some())
                || (self.empty_fresh() && self.pool.is_none()),
            "original requested pool must be exact fresh or live custody",
        )?;
        slot.register()?;
        // Infallible same-Rc retention before pool movement or creation.
        self.requested = Some(slot.retain());
        if self.pool.is_some() {
            slot.take_existing_pool(&mut self.pool)?;
        } else {
            self.phase = PoolPhase::Creating;
            slot.create_pool()?;
            self.phase = PoolPhase::Live;
        }
        self.revalidate_requested(slot)
    }

    pub(super) fn begin_requested_commit(
        &mut self,
        slot: &RetainedApexdCapexCustody,
    ) -> Result<()> {
        self.revalidate_requested(slot)?;
        slot.begin_commit_and_return(&mut self.pool)?;
        self.revalidate_requested(slot)
    }
    pub(super) fn finish_requested_commit(
        &mut self,
        slot: &RetainedApexdCapexCustody,
    ) -> Result<()> {
        self.revalidate_requested(slot)?;
        slot.finish_commit()?;
        self.revalidate_requested(slot)
    }
    pub(super) fn return_requested_pool_after_retire(
        &mut self,
        slot: &RetainedApexdCapexCustody,
    ) -> Result<()> {
        self.require_requested(slot)?;
        slot.return_after_retire(&mut self.pool)?;
        self.revalidate_requested(slot)
    }
    pub(super) fn finish_requested_retirement(
        &mut self,
        slot: &RetainedApexdCapexCustody,
    ) -> Result<()> {
        self.revalidate_requested(slot)?;
        let record = slot.finish_retirement()?;
        if let Some(device) = record.device() {
            self.retired.push(device);
        }
        self.requested_retired.push(record);
        drop(self.requested.take());
        Ok(())
    }

    pub(super) fn cleanup(&mut self) -> Result<()> {
        // An absent context is accepted only for this exact never-mutated,
        // zero-resource state. No alias-bearing state has an unscoped path.
        if self.empty_fresh() {
            return Ok(());
        }
        let owner = self.owner()?;
        let (mac, selection) = owner.objects()?;
        if self.phase == PoolPhase::Retired {
            require(
                self.pool.is_none() && self.rows.is_empty() && self.requested.is_none(),
                "retired private APEX pool still has resources",
            )?;
            return Ok(());
        }
        require(
            matches!(self.phase, PoolPhase::Live | PoolPhase::Retiring),
            "APEX private construction outcome is unproven",
        )?;
        require(
            self.pool.is_some() || self.requested.is_some(),
            "mutated private APEX pool custody absent",
        )?;
        self.phase = PoolPhase::Retiring;
        for row in &mut self.rows {
            if let Some(publication) = row.publication.as_mut() {
                publication.retire_helper()?;
            }
        }
        // The caller has proved original guest exit. These retained namespace
        // and payload views must also release before a loop can become unbound.
        for row in &mut self.rows {
            drop(row.publication.take());
        }
        for row in &mut self.rows {
            if let Some(binding) = row.binding.as_mut() {
                require(
                    row.retired_device.is_none(),
                    "duplicate private APEX retirement",
                )?;
                require(
                    binding.apex_index() == row.index,
                    "retiring private APEX role differs",
                )?;
                binding.retire(mac, selection)?;
                let device = binding.device_number();
                row.retired_device = Some(device);
                self.retired.push(device);
                drop(row.binding.take());
            } else {
                require(
                    row.retired_device.is_some(),
                    "incomplete private APEX binding cannot be claimed retired",
                )?;
            }
        }
        self.rows.clear();
        // Every old publication/binding has retired first. The requested
        // device then retires; only afterward may its same pool return and
        // the original pool itself retire. No Request callback runs here.
        if let Some(slot) = self
            .requested
            .as_ref()
            .map(RetainedApexdCapexCustody::retain)
        {
            slot.retire_device()?;
            slot.return_after_retire(&mut self.pool)?;
            let record = slot.finish_retirement()?;
            if let Some(device) = record.device() {
                self.retired.push(device);
            }
            self.requested_retired.push(record);
            drop(self.requested.take());
        }
        // Borrow the original pool: a failed partial retirement must retain
        // the same typed owner and its finite phase for a possible retry.
        self.pool.as_mut().unwrap().retire(mac, selection)?;
        drop(self.pool.take());
        self.phase = PoolPhase::Retired;
        owner.objects()?;
        Ok(())
    }

    pub(super) fn retired_devices(&self) -> &[u64] {
        &self.retired
    }
}

impl PreparedRuntime {
    /// Perform the actual LOOP_CONFIGURE operation for one compiled builtin
    /// role. The resource is inserted in the same runtime/lease guard before
    /// the first kernel mutation and has no guest descriptor export.
    pub(crate) fn prepare_original_builtin_apex_loop(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        index: usize,
        end: Instant,
    ) -> Result<()> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        init.revalidate_capability_contract()?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "APEX block owner must be this executed init's original runtime",
        )?;
        let fixed = apex_inputs::original_builtin(index).map_err(MountError::Rejected)?;
        let source = init.original_builtin_apex(index)?;
        let (uid, gid) = init.mapped_root_ids();
        let identity = original_metadata(&source, uid, gid, fixed.input.original_apex_bytes)?;
        let archive = VerifiedArchive::inspect(&source, index, end)?;
        archive.matches(&source)?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("runtime owner retired"))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        let generation = init.generation()?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        require(
            Instant::now() < end,
            "same APEX input deadline expired before kernel operation",
        )?;
        {
            let mut loops = resources
                .apex_loops
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("APEX block provider is already active"))?;
            loops.ensure_pool(mac, init.selection())?;
            require(
                loops.rows.iter().filter(|r| r.compressed.is_none()).count() < 10
                    && !loops.rows.iter().any(|r| r.index == index),
                "each of the ten original builtin roles may bind only once",
            )?;
            require(
                loops.rows.iter().all(|r| r.generation == generation),
                "same original init generation for all APEX blocks",
            )?;
            loops.rows.push(ApexLoop {
                index,
                source,
                identity,
                compressed: None,
                generation,
                binding: None,
                publication: None,
                retired_device: None,
            });
            let ApexLoops { rows, pool, .. } = &mut *loops;
            let row = rows
                .last_mut()
                .ok_or(MountError::Rejected("APEX custody insertion failed"))?;
            row.binding = Some(
                pool.as_mut()
                    .ok_or(MountError::Rejected("original private pool absent"))?
                    .attach(mac, init.selection(), &row.source, archive)?,
            );
            row.binding
                .as_ref()
                .unwrap()
                .revalidate(mac, init.selection())?;
            require(
                FileIdentity::of(&row.source.metadata()?) == row.identity,
                "original APEX changed across atomic readonly loop configuration",
            )?;
        }
        init.revalidate()?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        require(
            Instant::now() < end,
            "same APEX input deadline expired after kernel operation",
        )
    }

    /// Decode the exact system CAPEX into a sealed non-executable anonymous
    /// inode, then retain it through the same loop/device retirement owner.
    /// This prepares a block source only; no CAPEX mount or apexd result is
    /// synthesized, and the original builtin publication path stays strict.
    pub(crate) fn prepare_original_compressed_apex_loop(
        &self,
        init: &ExecutedInitWitness<'_>,
        mac: &MacPreflight,
        index: usize,
        end: Instant,
    ) -> Result<()> {
        crate::production_devices::require_initial_broker()
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        init.revalidate_capability_contract()?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        require(
            std::ptr::eq(self, init.runtime_owner()?),
            "APEX block owner must be this executed init's original runtime",
        )?;
        let fixed = apex_inputs::original_compressed(index).map_err(MountError::Rejected)?;
        let source = init.original_compressed_apex(index)?;
        let (uid, gid) = init.mapped_root_ids();
        let identity = original_metadata(&source, uid, gid, fixed.input.container_bytes)?;
        let output = Rc::new(ImmutableCapex::decode(source, index, end)?);
        let source = output.container()?.try_clone()?;
        require(
            FileIdentity::of(&source.metadata()?) == identity,
            "same original system CAPEX across complete decoding and kernel sealing",
        )?;
        let resources = self
            .resources
            .as_ref()
            .ok_or(MountError::Rejected("runtime owner retired"))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        let generation = init.generation()?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        require(
            Instant::now() < end,
            "same APEX input deadline expired before kernel operation",
        )?;
        {
            let mut loops = resources
                .apex_loops
                .try_borrow_mut()
                .map_err(|_| MountError::Rejected("APEX block provider is already active"))?;
            loops.ensure_pool(mac, init.selection())?;
            require(
                loops.rows.iter().filter(|r| r.compressed.is_some()).count() < 28
                    && !loops.rows.iter().any(|r| r.index == index),
                "each of the 28 original compressed roles may bind only once",
            )?;
            require(
                loops.rows.iter().all(|r| r.generation == generation),
                "same original init generation for all APEX blocks",
            )?;
            loops.rows.push(ApexLoop {
                index,
                source,
                identity,
                compressed: Some(output),
                generation,
                binding: None,
                publication: None,
                retired_device: None,
            });
            let ApexLoops { rows, pool, .. } = &mut *loops;
            let row = rows
                .last_mut()
                .ok_or(MountError::Rejected("APEX custody insertion failed"))?;
            row.binding = Some(
                pool.as_mut()
                    .ok_or(MountError::Rejected("original private pool absent"))?
                    .attach_compressed(
                        mac,
                        init.selection(),
                        Rc::clone(row.compressed.as_ref().ok_or(MountError::Rejected(
                            "sealed compressed output custody absent",
                        ))?),
                    )?,
            );
            row.binding
                .as_ref()
                .unwrap()
                .revalidate(mac, init.selection())?;
            require(
                FileIdentity::of(&row.source.metadata()?) == row.identity,
                "original APEX changed across atomic readonly loop configuration",
            )?;
        }
        init.revalidate()?;
        mac.revalidate(init.selection())
            .map_err(|e| MountError::Io(io::Error::other(e.to_string())))?;
        resources.matches_witness(&init.namespace_witness()?)?;
        require(
            Instant::now() < end,
            "same APEX input deadline expired after kernel operation",
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_apex_private_pool_missing_context_cannot_masquerade_as_an_empty_retirement() {
        let original_mounts = std::fs::read("/proc/self/mountinfo").unwrap();
        for phase in [
            PoolPhase::Creating,
            PoolPhase::Live,
            PoolPhase::Retiring,
            PoolPhase::Retired,
        ] {
            let mut owner = ApexLoops {
                phase,
                ..ApexLoops::default()
            };
            assert!(!owner.empty_fresh());
            assert!(owner.revalidate().is_err());
            assert!(owner.cleanup().is_err());
            assert_eq!(owner.phase, phase);
            assert!(owner.retired_devices().is_empty());
        }
        assert_eq!(
            std::fs::read("/proc/self/mountinfo").unwrap(),
            original_mounts
        );
    }

    #[test]
    fn original_apex_private_pool_unexplained_retirement_record_blocks_fresh_bypass() {
        let mut owner = ApexLoops::default();
        owner.retired.push(libc::makedev(7, 0));
        assert!(!owner.empty_fresh());
        assert!(owner.revalidate().is_err());
        assert!(owner.cleanup().is_err());
        assert_eq!(owner.retired_devices(), &[libc::makedev(7, 0)]);
    }

    #[test]
    fn original_apex_block_provider_rejects_ordinary_or_writable_host_files() {
        let file = tempfile::tempfile().unwrap();
        assert!(
            original_metadata(
                &file,
                unsafe { libc::geteuid() },
                unsafe { libc::getegid() },
                0
            )
            .is_err()
        );
        let special = File::open("/dev/null").unwrap();
        assert!(original_metadata(&special, 0, 0, 0).is_err());
        let mut empty = ApexLoops::default();
        empty.revalidate().unwrap();
        empty.cleanup().unwrap();
        assert!(empty.retired_devices().is_empty());
    }
}
