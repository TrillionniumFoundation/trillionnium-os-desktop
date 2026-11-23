//! Same-slot custody for one original apexd CAPEX configuration.
//!
//! Only the retained Exclusive actor creates this slot. The slot is stored in
//! the original ApexLoops before its original pool is moved or created.
//! These helpers never call Request/Bound revalidation and never expose a pool,
//! loop descriptor, target association or notification result to callers.
use super::*;
use crate::production_capex_loop_request::MatchedApexdCapexSource;
use crate::production_namespace::ActualApexdRequestBinding;
use crate::production_private_loop_owner::{PrivateLoopDevice, PrivateLoopOwner};
use std::cell::RefCell;
use std::rc::Rc;
use std::time::Instant;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Phase {
    Prepared,
    Registered,
    PoolCreating,
    PoolReady,
    Configuring,
    Configured,
    CommitPending,
    CustodyCommitted,
    DeviceRetiring,
    DeviceRetired,
    RetirementRecorded,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum PoolLocation {
    Unassigned,
    Moving,
    InSlot,
    InLedger,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum DeviceOutcome {
    NeverAttempted,
    Attempting,
    BusyRetired,
    Owned,
    RetiringOwned,
    RetiringUnproven,
    RetiredOwned(u64),
    RetiredAlias(u64),
}

// Used by the actual resource owner and ordinary tests with real owned FDs.
// There is no clone/reopen/reconstruction path for P or D.
struct Resources<P, D> {
    phase: Phase,
    location: PoolLocation,
    pool: Option<P>,
    device: Option<D>,
    outcome: DeviceOutcome,
}
impl<P, D> Resources<P, D> {
    fn new() -> Self {
        Self {
            phase: Phase::Prepared,
            location: PoolLocation::Unassigned,
            pool: None,
            device: None,
            outcome: DeviceOutcome::NeverAttempted,
        }
    }
    fn register(&mut self) -> Result<()> {
        require(
            self.phase == Phase::Prepared
                && self.location == PoolLocation::Unassigned
                && self.pool.is_none()
                && self.device.is_none()
                && self.outcome == DeviceOutcome::NeverAttempted,
            "requested CAPEX slot registers exactly once",
        )?;
        self.phase = Phase::Registered;
        Ok(())
    }
    fn take_existing_pool(&mut self, original: &mut Option<P>) -> Result<()> {
        require(
            self.phase == Phase::Registered
                && self.location == PoolLocation::Unassigned
                && self.pool.is_none()
                && original.is_some(),
            "only the registered slot may receive the original live pool",
        )?;
        self.location = PoolLocation::Moving;
        self.pool = original.take();
        self.location = PoolLocation::InSlot;
        self.phase = Phase::PoolReady;
        Ok(())
    }
    fn begin_create(&mut self) -> Result<()> {
        require(
            self.phase == Phase::Registered
                && self.location == PoolLocation::Unassigned
                && self.pool.is_none(),
            "only the registered empty slot may attempt pool creation",
        )?;
        self.phase = Phase::PoolCreating;
        Ok(())
    }
    fn begin_configure(&mut self) -> Result<()> {
        require(
            self.phase == Phase::PoolReady
                && self.location == PoolLocation::InSlot
                && self.pool.is_some()
                && self.device.is_none()
                && self.outcome == DeviceOutcome::NeverAttempted,
            "requested CAPEX configuration is one attempt in its original pool",
        )?;
        self.phase = Phase::Configuring;
        self.outcome = DeviceOutcome::Attempting;
        Ok(())
    }
    fn begin_commit(&mut self) -> Result<()> {
        require(
            self.phase == Phase::Configured
                && self.outcome == DeviceOutcome::Owned
                && self.device.is_some()
                && self.location == PoolLocation::InSlot,
            "only a retained configured device may begin custody commit",
        )?;
        self.phase = Phase::CommitPending;
        Ok(())
    }
    fn return_pool(&mut self, original: &mut Option<P>) -> Result<()> {
        require(
            matches!(self.phase, Phase::CommitPending | Phase::DeviceRetired),
            "pool return requires exact commit or proven device retirement",
        )?;
        match self.location {
            PoolLocation::InSlot => {
                require(
                    original.is_none() && self.pool.is_some(),
                    "original pool destination must be empty before exact return",
                )?;
                self.location = PoolLocation::Moving;
                *original = self.pool.take();
                self.location = PoolLocation::InLedger;
            }
            PoolLocation::InLedger => {
                require(
                    self.pool.is_none() && original.is_some(),
                    "already returned pool must remain in the original ledger",
                )?;
            }
            _ => return Err(MountError::Rejected("pool custody is incomplete")),
        }
        Ok(())
    }
    fn finish_commit(&mut self) -> Result<()> {
        require(
            self.phase == Phase::CommitPending
                && self.location == PoolLocation::InLedger
                && self.pool.is_none()
                && self.device.is_some()
                && self.outcome == DeviceOutcome::Owned,
            "custody commit requires the same returned pool and owned device",
        )?;
        self.phase = Phase::CustodyCommitted;
        Ok(())
    }
    fn begin_retire(&mut self) -> Result<()> {
        match (self.phase, self.outcome) {
            (Phase::PoolReady, DeviceOutcome::NeverAttempted)
            | (Phase::Configuring, DeviceOutcome::BusyRetired) => {
                require(
                    self.device.is_none(),
                    "unattempted or busy-retired custody differs",
                )?;
                self.phase = Phase::DeviceRetired;
            }
            (
                Phase::Configuring
                | Phase::Configured
                | Phase::CommitPending
                | Phase::CustodyCommitted,
                DeviceOutcome::Owned,
            ) => {
                require(
                    self.device.is_some(),
                    "owned retirement lost its actual device",
                )?;
                self.phase = Phase::DeviceRetiring;
                self.outcome = DeviceOutcome::RetiringOwned;
            }
            (Phase::Configuring, DeviceOutcome::Attempting) => {
                require(
                    self.device.is_some(),
                    "unknown configuration without retained device cannot retire",
                )?;
                self.phase = Phase::DeviceRetiring;
                // This does not declare the device unconfigured. Its original
                // state must prove retirement; Uncertain always rejects.
                self.outcome = DeviceOutcome::RetiringUnproven;
            }
            (
                Phase::DeviceRetiring,
                DeviceOutcome::RetiringOwned | DeviceOutcome::RetiringUnproven,
            ) => {
                require(
                    self.device.is_some(),
                    "retirement retry lost its actual device",
                )?;
            }
            (
                Phase::DeviceRetired,
                DeviceOutcome::NeverAttempted
                | DeviceOutcome::BusyRetired
                | DeviceOutcome::RetiredOwned(_)
                | DeviceOutcome::RetiredAlias(_),
            ) => {
                require(self.device.is_none(), "retired device still present")?;
            }
            _ => {
                return Err(MountError::Rejected(
                    "requested CAPEX mutation outcome is unproven",
                ));
            }
        }
        Ok(())
    }

    // Called only after the real device's original retirement and its exact
    // retired-state proof. rdev alone never supplies owned/unbound credit.
    fn finish_device_retirement(&mut self, number: u64) -> Result<()> {
        require(
            self.phase == Phase::DeviceRetiring && self.device.is_some(),
            "actual retained device retirement is absent",
        )?;
        self.outcome = match self.outcome {
            DeviceOutcome::RetiringOwned => DeviceOutcome::RetiredOwned(number),
            DeviceOutcome::RetiringUnproven => DeviceOutcome::RetiredAlias(number),
            _ => {
                return Err(MountError::Rejected(
                    "original ownership history was not retained",
                ));
            }
        };
        self.phase = Phase::DeviceRetired;
        drop(self.device.take());
        Ok(())
    }
    fn record_retirement(&mut self) -> Result<Option<u64>> {
        require(
            self.phase == Phase::DeviceRetired
                && self.location == PoolLocation::InLedger
                && self.pool.is_none()
                && self.device.is_none(),
            "retirement requires same-pool return and no retained device",
        )?;
        let device = match self.outcome {
            DeviceOutcome::RetiredOwned(device) => Some(device),
            DeviceOutcome::NeverAttempted
            | DeviceOutcome::BusyRetired
            | DeviceOutcome::RetiredAlias(_) => None,
            _ => return Err(MountError::Rejected("actual device retirement is unproven")),
        };
        self.phase = Phase::RetirementRecorded;
        Ok(device)
    }
}

// No issuer exists in this increment. A future real target provider must prove
// the original target block OFD and this configured device before introducing
// an issuer. A bool, rdev number, digest or successful private attach is not one.
#[derive(Clone, Copy)]
enum MissingOriginalTargetIssuer {}
pub(crate) struct OriginalApexdTargetAssociation {
    issuer: MissingOriginalTargetIssuer,
}

// A vacant entry cannot be fabricated outside this module. Exclusive access
// keeps it empty until insertion; insertion retains the value before returning
// a reference for any later fallible operation.
pub(crate) struct VacantResource<'a, T> {
    target: &'a mut Option<T>,
}
fn vacant_resource<T>(target: &mut Option<T>) -> io::Result<VacantResource<'_, T>> {
    if target.is_some() {
        return Err(io::Error::other("requested sink already retains a device"));
    }
    Ok(VacantResource { target })
}
impl<'a, T> VacantResource<'a, T> {
    pub(crate) fn insert(self, value: T) -> &'a mut T {
        *self.target = Some(value);
        // The immediately preceding infallible assignment establishes Some.
        self.target.as_mut().unwrap()
    }
}
pub(crate) struct RequestedVacantDevice<'a> {
    vacant: VacantResource<'a, PrivateLoopDevice>,
    outcome: &'a mut DeviceOutcome,
}
pub(crate) struct RequestedDeviceRef<'a> {
    device: &'a mut PrivateLoopDevice,
    outcome: &'a mut DeviceOutcome,
}
impl<'a> RequestedVacantDevice<'a> {
    pub(crate) fn insert(self, device: PrivateLoopDevice) -> RequestedDeviceRef<'a> {
        RequestedDeviceRef {
            device: self.vacant.insert(device),
            outcome: self.outcome,
        }
    }
}
impl RequestedDeviceRef<'_> {
    pub(crate) fn record_owned_configuration(
        &mut self,
        _actual: crate::production_private_loop_owner::RequestedConfigureSuccess,
    ) {
        // Only the original private-owner module can issue this zero-sized
        // proof, in the actual CONFIGURE Ok(true) branch for this retained ref.
        *self.outcome = DeviceOutcome::Owned;
    }
}
impl std::ops::Deref for RequestedDeviceRef<'_> {
    type Target = PrivateLoopDevice;
    fn deref(&self) -> &Self::Target {
        self.device
    }
}
impl std::ops::DerefMut for RequestedDeviceRef<'_> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.device
    }
}

/// The only issuer is the registered runtime slot below. This borrowed sink
/// exposes no constructor, no pool and no way to take a possibly live device.
pub(crate) struct RequestedDeviceCustody<'a> {
    device: &'a mut Option<PrivateLoopDevice>,
    outcome: &'a mut DeviceOutcome,
    source: Rc<MatchedApexdCapexSource>,
}
impl RequestedDeviceCustody<'_> {
    pub(crate) fn require_matched(
        &self,
        mac: &crate::production_mac::MacPreflight,
        selection: &crate::production_selection::ProductionSelection,
        matched: &Rc<crate::production_private_loop_owner::compressed::MatchedDecompressedCapex>,
    ) -> io::Result<()> {
        if !Rc::ptr_eq(self.source.matched(), matched) {
            return Err(io::Error::other(
                "requested sink source differs from its original runtime slot",
            ));
        }
        self.source
            .owner()
            .require_pair(mac, selection)
            .map_err(|error| io::Error::other(error.to_string()))?;
        self.source.revalidate_static()
    }
    pub(crate) fn begin_attempt(&mut self) -> io::Result<()> {
        if self.device.is_some()
            || !matches!(
                *self.outcome,
                DeviceOutcome::Attempting | DeviceOutcome::BusyRetired
            )
        {
            return Err(io::Error::other(
                "requested device attempt is not the original vacant slot",
            ));
        }
        *self.outcome = DeviceOutcome::Attempting;
        Ok(())
    }
    pub(crate) fn vacant(&mut self) -> io::Result<RequestedVacantDevice<'_>> {
        if *self.outcome != DeviceOutcome::Attempting {
            return Err(io::Error::other(
                "requested device attempt was not journaled",
            ));
        }
        Ok(RequestedVacantDevice {
            vacant: vacant_resource(self.device)?,
            outcome: self.outcome,
        })
    }
    pub(crate) fn discard_retired_after_busy(&mut self) -> io::Result<()> {
        let device = self
            .device
            .as_ref()
            .ok_or_else(|| io::Error::other("actual busy alias retirement absent"))?;
        device
            .require_retired_custody()
            .map_err(|error| io::Error::other(error.to_string()))?;
        // Only actual retired alias custody can be removed. This is not a
        // clear of the foreign loop that caused CONFIGURE EBUSY.
        drop(self.device.take());
        *self.outcome = DeviceOutcome::BusyRetired;
        Ok(())
    }
}

struct Custody {
    source: Rc<MatchedApexdCapexSource>,
    resources: Resources<PrivateLoopOwner, PrivateLoopDevice>,
}

pub(crate) struct RetainedApexdCapexCustody {
    inner: Rc<RefCell<Custody>>,
}
impl RetainedApexdCapexCustody {
    pub(super) fn new(source: Rc<MatchedApexdCapexSource>) -> Self {
        Self {
            inner: Rc::new(RefCell::new(Custody {
                source,
                resources: Resources::new(),
            })),
        }
    }
    pub(super) fn retain(&self) -> Self {
        Self {
            inner: Rc::clone(&self.inner),
        }
    }
    pub(super) fn same(&self, other: &Self) -> bool {
        Rc::ptr_eq(&self.inner, &other.inner)
    }
    pub(super) fn source(&self) -> Result<Rc<MatchedApexdCapexSource>> {
        Ok(Rc::clone(
            &self
                .inner
                .try_borrow()
                .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?
                .source,
        ))
    }
    pub(super) fn binding(&self) -> Result<ActualApexdRequestBinding> {
        Ok(self.source()?.binding())
    }
    pub(super) fn index(&self) -> Result<usize> {
        Ok(self.source()?.index())
    }
    pub(super) fn register(&self) -> Result<()> {
        self.inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?
            .resources
            .register()
    }
    pub(super) fn take_existing_pool(&self, original: &mut Option<PrivateLoopOwner>) -> Result<()> {
        self.inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?
            .resources
            .take_existing_pool(original)
    }
    pub(super) fn create_pool(&self) -> Result<()> {
        let source = self.source()?;
        source.revalidate_static().map_err(MountError::Io)?;
        require(
            Instant::now() < source.deadline(),
            "original CAPEX deadline expired",
        )?;
        let (mac, selection) = source.owner().objects()?;
        let mut custody = self
            .inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?;
        custody.resources.begin_create()?;
        let pool = PrivateLoopOwner::create(mac, selection)?;
        // No fallible check between the actual resource return and retention.
        custody.resources.pool = Some(pool);
        custody.resources.location = PoolLocation::InSlot;
        custody.resources.phase = Phase::PoolReady;
        drop(custody);
        require(
            Instant::now() < source.deadline(),
            "original CAPEX deadline expired",
        )?;
        self.revalidate_static()?;
        Ok(())
    }
    pub(super) fn configure(&self) -> Result<()> {
        let source = self.source()?;
        source.revalidate_static().map_err(MountError::Io)?;
        require(
            Instant::now() < source.deadline(),
            "original CAPEX deadline expired",
        )?;
        let (mac, selection) = source.owner().objects()?;
        let mut custody = self
            .inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?;
        custody.resources.begin_configure()?;
        {
            let Resources {
                pool,
                device,
                outcome,
                ..
            } = &mut custody.resources;
            let mut retained = RequestedDeviceCustody {
                device,
                outcome,
                source: Rc::clone(&source),
            };
            pool.as_mut()
                .ok_or(MountError::Rejected("registered original pool absent"))?
                .attach_requested_retained(
                    mac,
                    selection,
                    Rc::clone(source.matched()),
                    source.deadline(),
                    &mut retained,
                )?;
        }
        // The actual device was retained before ioctl, including every
        // Uncertain/Owned error. Nothing is moved out for a later check.
        require(
            custody.resources.device.is_some(),
            "successful requested attach lost its retained device",
        )?;
        require(
            custody.resources.outcome == DeviceOutcome::Owned,
            "successful requested configure lost its actual owned-history proof",
        )?;
        custody.resources.phase = Phase::Configured;
        drop(custody);
        require(
            Instant::now() < source.deadline(),
            "original CAPEX deadline expired",
        )?;
        self.revalidate_static()?;
        Ok(())
    }
    // This method has no Request/Bound callback. Its callers separately
    // validate all original rows and whichever side currently owns the pool.
    pub(super) fn revalidate_static(&self) -> Result<PoolLocation> {
        let source = self.source()?;
        source.revalidate_static().map_err(MountError::Io)?;
        let (mac, selection) = source.owner().objects()?;
        let custody = self
            .inner
            .try_borrow()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?;
        let r = &custody.resources;
        match (r.phase, r.outcome) {
            (Phase::PoolReady, DeviceOutcome::NeverAttempted) => {
                require(
                    r.device.is_none() && r.location == PoolLocation::InSlot,
                    "unattempted requested slot has unexplained custody",
                )?;
            }
            (Phase::Configured, DeviceOutcome::Owned) => {
                require(
                    r.device.is_some() && r.location == PoolLocation::InSlot,
                    "configured requested slot lost original custody",
                )?;
            }
            (Phase::CommitPending | Phase::CustodyCommitted, DeviceOutcome::Owned) => {
                require(
                    r.device.is_some() && r.location == PoolLocation::InLedger,
                    "committed requested slot has not returned its original pool",
                )?;
            }
            (
                Phase::DeviceRetired,
                DeviceOutcome::NeverAttempted
                | DeviceOutcome::BusyRetired
                | DeviceOutcome::RetiredOwned(_)
                | DeviceOutcome::RetiredAlias(_),
            ) => {
                require(
                    r.device.is_none(),
                    "retired requested slot retains a device",
                )?;
            }
            _ => {
                return Err(MountError::Rejected(
                    "requested CAPEX slot is incomplete or retiring",
                ));
            }
        }
        match r.location {
            PoolLocation::InSlot => r
                .pool
                .as_ref()
                .ok_or(MountError::Rejected("original requested pool missing"))?
                .revalidate(mac, selection)?,
            PoolLocation::InLedger => require(
                r.pool.is_none(),
                "returned pool also appears in the requested slot",
            )?,
            _ => return Err(MountError::Rejected("requested pool move is incomplete")),
        }
        if let Some(device) = &r.device {
            require(
                device.apex_index() == source.index(),
                "requested device role differs",
            )?;
            device.revalidate(mac, selection)?;
        }
        source.revalidate_static().map_err(MountError::Io)?;
        Ok(r.location)
    }
    pub(super) fn begin_commit_and_return(
        &self,
        original: &mut Option<PrivateLoopOwner>,
    ) -> Result<()> {
        let mut c = self
            .inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?;
        c.resources.begin_commit()?;
        c.resources.return_pool(original)
    }
    pub(super) fn finish_commit(&self) -> Result<()> {
        self.inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?
            .resources
            .finish_commit()
    }
    pub(super) fn retire_device(&self) -> Result<()> {
        let source = self.source()?;
        source.revalidate_static().map_err(MountError::Io)?;
        let (mac, selection) = source.owner().objects()?;
        let mut c = self
            .inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?;
        c.resources.begin_retire()?;
        if c.resources.phase == Phase::DeviceRetiring {
            let device = c.resources.device.as_mut().ok_or(MountError::Rejected(
                "actual requested device absent during retirement",
            ))?;
            require(
                device.apex_index() == source.index(),
                "retiring requested role differs",
            )?;
            if device.require_retired_custody().is_err() {
                // The original device state permits only Owned, Unconfigured
                // or its recorded alias retirement; Uncertain remains denied.
                device.retire(mac, selection)?;
            }
            device.require_retired_custody()?;
            let number = device.device_number();
            c.resources.finish_device_retirement(number)?;
        }
        Ok(())
    }
    pub(super) fn return_after_retire(
        &self,
        original: &mut Option<PrivateLoopOwner>,
    ) -> Result<()> {
        self.inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?
            .resources
            .return_pool(original)
    }
    pub(super) fn finish_retirement(&self) -> Result<RetiredCapexCustody> {
        let source = self.source()?;
        let mut c = self
            .inner
            .try_borrow_mut()
            .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?;
        let device = c.resources.record_retirement()?;
        Ok(RetiredCapexCustody {
            binding: source.binding(),
            index: source.index(),
            device,
            history: c.resources.outcome,
        })
    }
    pub(super) fn committed(&self) -> Result<CommittedApexdCapexCustody> {
        self.revalidate_static()?;
        require(
            self.inner
                .try_borrow()
                .map_err(|_| MountError::Rejected("requested CAPEX slot is active"))?
                .resources
                .phase
                == Phase::CustodyCommitted,
            "only the exact completed custody commit issues its receipt",
        )?;
        Ok(CommittedApexdCapexCustody {
            slot: self.retain(),
            target: None,
        })
    }
}
impl std::fmt::Debug for RetainedApexdCapexCustody {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let phase = self.inner.try_borrow().ok().map(|c| c.resources.phase);
        f.debug_struct("RetainedApexdCapexCustody")
            .field("phase", &phase)
            .finish_non_exhaustive()
    }
}
impl Drop for Custody {
    fn drop(&mut self) {
        if self.resources.device.is_some()
            || self.resources.pool.is_some()
            || matches!(
                self.resources.outcome,
                DeviceOutcome::Attempting
                    | DeviceOutcome::RetiringOwned
                    | DeviceOutcome::RetiringUnproven
            )
            || self.resources.phase == Phase::PoolCreating
            || self.resources.location == PoolLocation::Moving
        {
            // The unchanged private pool/device Drop retains unknown kernel
            // ownership. Keep the inseparable MAC/source/runtime pair with it.
            std::mem::forget(Rc::clone(&self.source));
        }
    }
}

pub(super) struct RetiredCapexCustody {
    binding: ActualApexdRequestBinding,
    index: usize,
    device: Option<u64>,
    history: DeviceOutcome,
}
impl RetiredCapexCustody {
    pub(super) fn index(&self) -> usize {
        self.index
    }
    pub(super) fn binding(&self) -> ActualApexdRequestBinding {
        self.binding
    }
    pub(super) fn device(&self) -> Option<u64> {
        self.device
    }
}
impl std::fmt::Debug for RetiredCapexCustody {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("RetiredCapexCustody")
            .field("index", &self.index)
            .field("device", &self.device)
            .field("history", &self.history)
            .finish_non_exhaustive()
    }
}

/// Retention evidence only. It exposes no FD, private device or successful
/// result. The actual original-target association has no issuer in this stage.
pub(crate) struct CommittedApexdCapexCustody {
    slot: RetainedApexdCapexCustody,
    target: Option<OriginalApexdTargetAssociation>,
}
impl CommittedApexdCapexCustody {
    pub(crate) fn require_original_target(&self) -> Result<()> {
        let target = self.target.as_ref().ok_or(MountError::Rejected(
            "original target block OFD and configured private device are not yet associated",
        ))?;
        match target.issuer {}
    }
    pub(crate) fn role_index(&self) -> Result<usize> {
        self.slot.index()
    }
    pub(crate) fn request_binding(&self) -> Result<ActualApexdRequestBinding> {
        self.slot.binding()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::MetadataExt;

    #[test]
    fn requested_pool_moves_same_real_description_and_returns_without_replacing_old_users() {
        let pool = tempfile::tempfile().unwrap();
        let old_user = pool.try_clone().unwrap();
        let original_fd = pool.as_raw_fd();
        let original_inode = pool.metadata().unwrap().ino();
        let mut original = Some(pool);
        let mut r: Resources<File, File> = Resources::new();
        r.register().unwrap();
        r.take_existing_pool(&mut original).unwrap();
        assert!(original.is_none());
        assert_eq!(r.pool.as_ref().unwrap().as_raw_fd(), original_fd);
        assert_eq!(
            r.pool.as_ref().unwrap().metadata().unwrap().ino(),
            original_inode
        );
        old_user.write_all_at(b"original pool custody", 0).unwrap();
        let mut body = [0; 21];
        r.pool
            .as_ref()
            .unwrap()
            .read_exact_at(&mut body, 0)
            .unwrap();
        assert_eq!(&body, b"original pool custody");
        r.begin_retire().unwrap();
        r.return_pool(&mut original).unwrap();
        assert_eq!(original.as_ref().unwrap().as_raw_fd(), original_fd);
        assert_eq!(
            original.as_ref().unwrap().metadata().unwrap().ino(),
            original_inode
        );
        assert_eq!(r.record_retirement().unwrap(), None);
        assert!(r.record_retirement().is_err());
        assert_eq!(old_user.metadata().unwrap().ino(), original_inode);
    }

    #[test]
    fn requested_post_configure_failure_keeps_actual_device_in_original_shared_slot() {
        let mut original = Some(tempfile::tempfile().unwrap());
        let slot = Rc::new(RefCell::new(Resources::<File, File>::new()));
        slot.borrow_mut().register().unwrap();
        slot.borrow_mut().take_existing_pool(&mut original).unwrap();
        let operation = Rc::clone(&slot);
        operation.borrow_mut().begin_configure().unwrap();
        let device = tempfile::tempfile().unwrap();
        let inode = device.metadata().unwrap().ino();
        let weak = Rc::downgrade(&operation);
        {
            let mut r = operation.borrow_mut();
            r.device = Some(device);
            r.outcome = DeviceOutcome::Owned;
            r.phase = Phase::Configured;
        }
        // Model a later source/MAC check returning an error after retention.
        let postcheck: Result<()> = Err(MountError::Rejected("ordinary injected postcheck"));
        assert!(postcheck.is_err());
        drop(operation);
        assert!(weak.upgrade().is_some());
        assert_eq!(
            slot.borrow()
                .device
                .as_ref()
                .unwrap()
                .metadata()
                .unwrap()
                .ino(),
            inode
        );
        slot.borrow_mut().begin_commit().unwrap();
        slot.borrow_mut().return_pool(&mut original).unwrap();
        slot.borrow_mut().finish_commit().unwrap();
        assert!(original.is_some());
        assert!(slot.borrow().pool.is_none());
        assert_eq!(
            slot.borrow()
                .device
                .as_ref()
                .unwrap()
                .metadata()
                .unwrap()
                .ino(),
            inode
        );
    }

    #[test]
    fn requested_unknown_create_and_configure_are_not_empty_or_successful_retirements() {
        let mut creating: Resources<File, File> = Resources::new();
        creating.register().unwrap();
        creating.begin_create().unwrap();
        assert_eq!(creating.phase, Phase::PoolCreating);
        assert!(creating.begin_retire().is_err());
        assert!(creating.record_retirement().is_err());
        assert_eq!(creating.phase, Phase::PoolCreating);

        let mut original = Some(tempfile::tempfile().unwrap());
        let mut configuring: Resources<File, File> = Resources::new();
        configuring.register().unwrap();
        configuring.take_existing_pool(&mut original).unwrap();
        configuring.begin_configure().unwrap();
        assert!(configuring.device.is_none());
        assert!(configuring.begin_retire().is_err());
        assert!(configuring.record_retirement().is_err());
        assert_eq!(configuring.outcome, DeviceOutcome::Attempting);
        assert_eq!(configuring.phase, Phase::Configuring);
        assert!(configuring.pool.is_some());
        assert!(original.is_none());
    }

    #[test]
    fn requested_pool_return_rejects_replacement_and_keeps_both_real_resources() {
        let mut original = Some(tempfile::tempfile().unwrap());
        let mut r: Resources<File, File> = Resources::new();
        r.register().unwrap();
        r.take_existing_pool(&mut original).unwrap();
        let first = r.pool.as_ref().unwrap().metadata().unwrap().ino();
        r.begin_retire().unwrap();
        original = Some(tempfile::tempfile().unwrap());
        let unrelated = original.as_ref().unwrap().metadata().unwrap().ino();
        assert!(r.return_pool(&mut original).is_err());
        assert_eq!(r.pool.as_ref().unwrap().metadata().unwrap().ino(), first);
        assert_eq!(
            original.as_ref().unwrap().metadata().unwrap().ino(),
            unrelated
        );
        assert_eq!(r.location, PoolLocation::InSlot);
        assert!(r.record_retirement().is_err());
    }
    #[test]
    fn requested_vacant_sink_retains_actual_fd_before_fallible_followup() {
        let file = tempfile::tempfile().unwrap();
        let fd = file.as_raw_fd();
        let inode = file.metadata().unwrap().ino();
        let mut stored: Option<File> = None;
        let result: io::Result<()> = (|| {
            let actual = vacant_resource(&mut stored)?.insert(file);
            actual.write_all_at(b"held before error", 0)?;
            Err(io::Error::other("actual later ordinary check failed"))
        })();
        assert!(result.is_err());
        assert_eq!(stored.as_ref().unwrap().as_raw_fd(), fd);
        assert_eq!(stored.as_ref().unwrap().metadata().unwrap().ino(), inode);
        assert!(vacant_resource(&mut stored).is_err());
        drop(stored.take());
        assert_eq!(unsafe { libc::fcntl(fd, libc::F_GETFD) }, -1);
        assert_eq!(io::Error::last_os_error().raw_os_error(), Some(libc::EBADF));
    }

    #[test]
    fn requested_alias_retirement_never_becomes_owned_unbound_evidence() {
        for was_owned in [false, true] {
            let mut original = Some(tempfile::tempfile().unwrap());
            let mut r: Resources<File, File> = Resources::new();
            r.register().unwrap();
            r.take_existing_pool(&mut original).unwrap();
            r.begin_configure().unwrap();
            r.device = Some(tempfile::tempfile().unwrap());
            if was_owned {
                // Production sets this only with RequestedConfigureSuccess
                // in the actual private-owner CONFIGURE Ok(true) arm.
                r.outcome = DeviceOutcome::Owned;
            }
            r.begin_retire().unwrap();
            let before_retry = r.outcome;
            r.begin_retire().unwrap();
            assert_eq!(r.outcome, before_retry);
            r.finish_device_retirement(0x701).unwrap();
            if was_owned {
                assert_eq!(r.outcome, DeviceOutcome::RetiredOwned(0x701));
            } else {
                assert_eq!(r.outcome, DeviceOutcome::RetiredAlias(0x701));
            }
            r.return_pool(&mut original).unwrap();
            assert_eq!(r.record_retirement().unwrap(), was_owned.then_some(0x701));
        }
    }
}
