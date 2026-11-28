//! Narrow adapter for an actual original apexd LOOP_CONFIGURE request.
//!
//! Namespace code alone issues OriginalApexdIoctlRequest and its single-use
//! bound request. This adapter does not create a task, choose a caller FD,
//! manufacture a guest loop handle, reply to a notification, or grant an APEX
//! mount/AVB/dm-verity result. The original runtime ledger must retain the sealed slot before configure().
//! Custody commit does not associate the original target or permit a reply.
use crate::production_execution::RuntimeMacOwner;
use crate::production_mac::MacRequestedCapexWitness;
use crate::production_namespace::{
    ActualApexdRequestBinding, BoundApexdCapexRequest, DefaultMountBinding,
    ObservedApexdLoopConfigure, OriginalApexdIoctlRequest,
};
use crate::production_private_loop_owner::compressed::MatchedDecompressedCapex;
use crate::production_runtime_assets::{CommittedApexdCapexCustody, RetainedApexdCapexCustody};
use std::io;
use std::rc::Rc;
use std::time::Instant;

type Result<T> = io::Result<T>;
fn need(value: bool, reason: &'static str) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(io::Error::new(io::ErrorKind::InvalidData, reason))
    }
}
fn observed_error(error: impl std::fmt::Display) -> io::Error {
    // Controller observation failure is never translated into an original
    // apexd syscall errno or a synthetic successful notification response.
    io::Error::other(error.to_string())
}
fn before(end: Instant) -> Result<()> {
    need(
        Instant::now() < end,
        "original apexd request deadline expired",
    )
}
fn u32_at(bytes: &[u8; 304], at: usize) -> u32 {
    u32::from_le_bytes(bytes[at..at + 4].try_into().unwrap())
}
fn u64_at(bytes: &[u8; 304], at: usize) -> u64 {
    u64::from_le_bytes(bytes[at..at + 8].try_into().unwrap())
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ConfigureShape {
    source_fd: u32,
    offset: u64,
    bytes: u64,
}
impl ConfigureShape {
    fn parse(raw: &[u8; 304]) -> Result<Self> {
        // Exact Linux 6.18 loop_config layout and actual fixed CP3A call site:
        // d3fc4 flags=4, d4016 block_size=4096, d4034 LOOP_CONFIGURE.
        // The invalid-fd support probe is a separate real-kernel operation.
        let source_fd = u32_at(raw, 0);
        need(
            source_fd <= i32::MAX as u32,
            "actual configure requires a nonnegative source FD",
        )?;
        need(u32_at(raw, 4) == 4096, "original CP3A logical block size")?;
        need(
            u32_at(raw, 60) == 4,
            "original CP3A AUTOCLEAR-only requested flags",
        )?;
        need(
            raw[8..32].iter().all(|x| *x == 0)
                && raw[48..60].iter().all(|x| *x == 0)
                && raw[64..304].iter().all(|x| *x == 0),
            "all readonly, encryption, filename, initialization and reserved fields remain zero",
        )?;
        let offset = u64_at(raw, 32);
        let bytes = u64_at(raw, 40);
        need(
            bytes > 0 && offset.checked_add(bytes).is_some(),
            "bounded nonempty original payload extent",
        )?;
        Ok(Self {
            source_fd,
            offset,
            bytes,
        })
    }
    fn require_extent(&self, offset: u64, bytes: u64) -> Result<()> {
        need(
            self.offset == offset && self.bytes == bytes,
            "original requested extent is not the exact fixed-role APEX payload",
        )
    }
    fn require_matched(&self, matched: &MatchedDecompressedCapex) -> Result<()> {
        matched.revalidate()?;
        let archive = matched.sealed_backing()?.archive()?;
        need(
            archive.index() == matched.index(),
            "same original compressed role",
        )?;
        self.require_extent(archive.offset(), archive.payload_bytes())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Phase {
    Prepared,
    Registering,
    Registered,
    Configuring,
    Configured,
    Committing,
    CustodyCommitted,
    Retiring,
    Retired,
}

/// Lifetime-independent byte/MAC custody. It contains no Request or Bound
/// reference and never calls their validators from revalidate_static().
/// Only prepare(), after the original bound request is issued, constructs it.
pub(crate) struct MatchedApexdCapexSource {
    mac: MacRequestedCapexWitness,
    matched: Rc<MatchedDecompressedCapex>,
    owner: RuntimeMacOwner,
    request: ActualApexdRequestBinding,
    request_address: usize,
    default_binding: DefaultMountBinding,
    shape: ConfigureShape,
    end: Instant,
}
impl MatchedApexdCapexSource {
    pub(crate) fn binding(&self) -> ActualApexdRequestBinding {
        self.request
    }
    pub(crate) fn index(&self) -> usize {
        self.matched.index()
    }
    pub(crate) fn deadline(&self) -> Instant {
        self.end
    }
    pub(crate) fn owner(&self) -> &RuntimeMacOwner {
        &self.owner
    }
    pub(crate) fn matched(&self) -> &Rc<MatchedDecompressedCapex> {
        &self.matched
    }

    // Safe inside the retained ledger/slot: no Request/Bound callback.
    pub(crate) fn revalidate_static(&self) -> Result<()> {
        self.shape.require_matched(&self.matched)?;
        self.mac
            .require_matched(&self.owner, &self.matched)
            .map_err(observed_error)?;
        self.owner.objects().map_err(observed_error)?;
        self.matched.revalidate()
    }

    // Only outside all inner ledger and mutable slot borrows.
    pub(crate) fn require_request(&self, request: &OriginalApexdIoctlRequest<'_>) -> Result<()> {
        before(self.end)?;
        request.revalidate().map_err(observed_error)?;
        need(
            request as *const _ as usize == self.request_address
                && request.deadline() == self.end
                && request.default_binding() == self.default_binding
                && request.custody_binding().map_err(observed_error)? == self.request,
            "same original apexd request object, generation, default graph and deadline",
        )?;
        request.require_owner(&self.owner).map_err(observed_error)?;
        self.revalidate_static()?;
        request.revalidate().map_err(observed_error)?;
        before(self.end)
    }
}

pub(crate) struct PreparedApexdCapexLoop<'request> {
    // The lifetime-bearing Bound stays here. The runtime ledger owns only the
    // separate static source Rc and its sealed resource slot.
    bound: BoundApexdCapexRequest<'request>,
    source: Rc<MatchedApexdCapexSource>,
    slot: Option<RetainedApexdCapexCustody>,
    phase: Phase,
}
impl<'request> PreparedApexdCapexLoop<'request> {
    /// Sole normal entry: the actual Request observes its own 304 bytes and
    /// identifies/matches the original readonly system CAPEX internally.
    /// No caller-supplied role, container path, requested FD or Matched value.
    pub(crate) fn prepare_registered<'task>(
        request: &'request OriginalApexdIoctlRequest<'task>,
        owner: &RuntimeMacOwner,
    ) -> Result<Self> {
        request.require_owner(owner).map_err(observed_error)?;
        let observed = request.original_loop_configure().map_err(observed_error)?;
        let matched = request
            .match_original_compressed(&observed)
            .map_err(observed_error)?;
        let mut value = Self::prepare_matched(request, &observed, matched, owner)?;
        value.register(request)?;
        Ok(value)
    }

    fn prepare_matched<'task>(
        request: &'request OriginalApexdIoctlRequest<'task>,
        observed: &ObservedApexdLoopConfigure,
        matched: Rc<MatchedDecompressedCapex>,
        owner: &RuntimeMacOwner,
    ) -> Result<Self> {
        let end = request.deadline();
        before(end)?;
        request.revalidate().map_err(observed_error)?;
        request.require_owner(owner).map_err(observed_error)?;
        observed.revalidate(request).map_err(observed_error)?;
        let default_binding = request.default_binding();
        let shape = ConfigureShape::parse(observed.bytes())?;
        matched.require_requested(observed.source())?;
        shape.require_matched(&matched)?;
        let mac = MacRequestedCapexWitness::observe(owner, Rc::clone(&matched))
            .map_err(observed_error)?;
        before(end)?;
        let bound = request
            .bind_matched_capex(observed, &matched)
            .map_err(observed_error)?;
        observed.revalidate(request).map_err(observed_error)?;
        request.revalidate().map_err(observed_error)?;
        let binding = request.custody_binding().map_err(observed_error)?;
        need(
            request.default_binding() == default_binding && request.deadline() == end,
            "same original default epoch and deadline",
        )?;
        let value = Self {
            bound,
            source: Rc::new(MatchedApexdCapexSource {
                mac,
                matched,
                owner: owner.clone(),
                request: binding,
                request_address: request as *const _ as usize,
                default_binding,
                shape,
                end,
            }),
            slot: None,
            phase: Phase::Prepared,
        };
        value.revalidate_request(request)?;
        Ok(value)
    }

    fn revalidate_request(&self, request: &OriginalApexdIoctlRequest<'_>) -> Result<()> {
        before(self.source.end)?;
        self.bound.revalidate().map_err(observed_error)?;
        self.source.require_request(request)?;
        self.bound.revalidate().map_err(observed_error)?;
        before(self.source.end)
    }

    /// The guard stores the original slot before moving/creating its pool.
    /// If this call fails after insertion, the original runtime still owns it.
    fn register(&mut self, request: &OriginalApexdIoctlRequest<'_>) -> Result<()> {
        need(
            self.phase == Phase::Prepared && self.slot.is_none(),
            "one runtime slot registration for this actual request",
        )?;
        self.revalidate_request(request)?;
        let ledger = request.actor_ledger().map_err(observed_error)?;
        request
            .require_actor_ledger(ledger)
            .map_err(observed_error)?;
        self.phase = Phase::Registering;
        let slot = ledger
            .register_capex_custody(request, &self.bound, Rc::clone(&self.source))
            .map_err(observed_error)?;
        self.slot = Some(slot);
        self.phase = Phase::Registered;
        self.revalidate_request(request)
    }

    /// No bare pool parameter and no unregistered mutation lane remains.
    pub(crate) fn configure(&mut self, request: &OriginalApexdIoctlRequest<'_>) -> Result<()> {
        need(
            self.phase == Phase::Registered,
            "configuration requires the original registered runtime slot",
        )?;
        self.revalidate_request(request)?;
        let slot = self
            .slot
            .as_ref()
            .ok_or_else(|| observed_error("runtime slot absent"))?;
        let ledger = request.actor_ledger().map_err(observed_error)?;
        request
            .require_actor_ledger(ledger)
            .map_err(observed_error)?;
        self.phase = Phase::Configuring;
        ledger
            .configure_capex_custody(request, &self.bound, slot)
            .map_err(observed_error)?;
        self.phase = Phase::Configured;
        self.revalidate_request(request)
    }

    /// This returns custody evidence only. All actual devices remain in the
    /// original runtime slot; there is no guest FD or ioctl-success result.
    pub(crate) fn commit_to_runtime(
        &mut self,
        request: &OriginalApexdIoctlRequest<'_>,
    ) -> Result<CommittedApexdCapexCustody> {
        need(
            self.phase == Phase::Configured,
            "custody commit requires the same configured operation",
        )?;
        self.revalidate_request(request)?;
        let slot = self
            .slot
            .as_ref()
            .ok_or_else(|| observed_error("runtime slot absent"))?;
        let ledger = request.actor_ledger().map_err(observed_error)?;
        request
            .require_actor_ledger(ledger)
            .map_err(observed_error)?;
        self.phase = Phase::Committing;
        let receipt = ledger
            .commit_capex_custody(request, &self.bound, slot)
            .map_err(observed_error)?;
        self.phase = Phase::CustodyCommitted;
        self.revalidate_request(request)?;
        Ok(receipt)
    }

    /// Retire only this private device and return the same pool. The pool is
    /// never retired here while existing builtin rows may still use it.
    pub(crate) fn retire(&mut self, request: &OriginalApexdIoctlRequest<'_>) -> Result<()> {
        need(
            matches!(
                self.phase,
                Phase::Registered | Phase::Configured | Phase::CustodyCommitted
            ),
            "incomplete mutation is retained for the original runtime cleanup",
        )?;
        self.revalidate_request(request)?;
        let slot = self
            .slot
            .as_ref()
            .ok_or_else(|| observed_error("runtime slot absent"))?;
        let ledger = request.actor_ledger().map_err(observed_error)?;
        request
            .require_actor_ledger(ledger)
            .map_err(observed_error)?;
        self.phase = Phase::Retiring;
        ledger
            .retire_capex_custody(request, &self.bound, slot)
            .map_err(observed_error)?;
        self.phase = Phase::Retired;
        // Retirement is not reissuance of ordinary runtime/request readiness.
        Ok(())
    }
}
impl std::fmt::Debug for PreparedApexdCapexLoop<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PreparedApexdCapexLoop")
            .field("phase", &self.phase)
            .field("role_index", &self.source.index())
            .finish_non_exhaustive()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn configuration() -> [u8; 304] {
        let mut raw = [0; 304];
        raw[0..4].copy_from_slice(&19_u32.to_le_bytes());
        raw[4..8].copy_from_slice(&4096_u32.to_le_bytes());
        raw[32..40].copy_from_slice(&4096_u64.to_le_bytes());
        raw[40..48].copy_from_slice(&8192_u64.to_le_bytes());
        raw[60..64].copy_from_slice(&4_u32.to_le_bytes());
        raw
    }
    #[test]
    fn actual_configuration_rejects_every_nonzero_reserved_or_encryption_byte() {
        let raw = configuration();
        let parsed = ConfigureShape::parse(&raw).unwrap();
        parsed.require_extent(4096, 8192).unwrap();
        for index in (8..32).chain(48..60).chain(64..304) {
            let mut changed = raw;
            changed[index] = 1;
            assert!(ConfigureShape::parse(&changed).is_err(), "offset {index}");
        }
    }
    #[test]
    fn actual_configuration_keeps_probe_flags_geometry_and_role_extent_separate() {
        let raw = configuration();
        for flags in [0_u32, 1, 5, 8, 16, 20, u32::MAX] {
            let mut changed = raw;
            changed[60..64].copy_from_slice(&flags.to_le_bytes());
            assert!(ConfigureShape::parse(&changed).is_err());
        }
        for size in [0_u32, 512, 8192, u32::MAX] {
            let mut changed = raw;
            changed[4..8].copy_from_slice(&size.to_le_bytes());
            assert!(ConfigureShape::parse(&changed).is_err());
        }
        let mut probe = [0; 304];
        probe[0..4].copy_from_slice(&u32::MAX.to_le_bytes());
        assert!(ConfigureShape::parse(&probe).is_err());
        let parsed = ConfigureShape::parse(&raw).unwrap();
        assert!(parsed.require_extent(0, 8192).is_err());
        assert!(parsed.require_extent(4096, 4096).is_err());
        let mut changed = raw;
        changed[32..40].copy_from_slice(&u64::MAX.to_le_bytes());
        assert!(ConfigureShape::parse(&changed).is_err());
        changed = raw;
        changed[40..48].fill(0);
        assert!(ConfigureShape::parse(&changed).is_err());
    }
}
