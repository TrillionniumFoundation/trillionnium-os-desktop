// SPDX-License-Identifier: MIT
// Pure finite protocol model for review. This file has NO syscall, ioctl,
// filesystem, process, device or network operation. It is NOT a kernel driver,
// Rust target issuer, native errno observation, or production qualification.
// Inputs named Fact are assumptions supplied to a model; they are not evidence.
// This deliberately models only the sealed-CAPEX target sequence. Builtin image
// source custody, actual loop-control allocation, MAC, AVB and dm are separate.

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct Binding {
    epoch: u64,
    actor_generation: u64,
    namespace_generation: u64,
    kernel_target_generation: u64,
    ofd_identity: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct SourceFact {
    identity: u64,
    bytes: u64,
    original_readonly_ofd_preserved: bool,
    complete_match: bool,
    immutable_sealed_backing: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
struct Geometry {
    offset: u64,
    payload_bytes: u64,
    block_size: u32,
    original_flags: u32,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
enum Phase { Reserved, Opened, ProbePending, Probed, Armed, ConfigurePending,
             Configured, Revoking, Retired }

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
enum Operation { Probe, Configure }

#[derive(Clone, Copy, Debug, Eq, PartialEq, Hash)]
enum KernelBinding { Unbound, Bound, Unknown }

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum Error { OrdinaryHostDevice, WrongBinding, WrongPhase, Replay, InvalidProbe,
             InvalidSource, InvalidGeometry, Revoked, NativeFailure, Unknown,
             Busy, Incomplete }

type Result<T> = std::result::Result<T, Error>;

#[derive(Clone, Debug, Eq, PartialEq, Hash)]
struct Model {
    binding: Binding,
    phase: Phase,
    live: bool,
    target_held: bool,
    controller_held: bool,
    alias_present: bool,
    source: Option<SourceFact>,
    geometry: Option<Geometry>,
    pending: Option<(Operation, u64)>,
    used_notifications: Vec<u64>,
    genuine_probe_assumed: bool,
    native_success_assumed: bool,
    success_reply_sent: bool,
    kernel_binding: KernelBinding,
    io_refs: u8,
    graph_refs: u8,
}

impl Model {
    fn new(binding: Binding, kernel_private_instance_assumed: bool) -> Result<Self> {
        if !kernel_private_instance_assumed { return Err(Error::OrdinaryHostDevice); }
        Ok(Self { binding, phase: Phase::Reserved, live: true,
            target_held: true, controller_held: true, alias_present: true,
            source: None, geometry: None, pending: None,
            used_notifications: Vec::new(), genuine_probe_assumed: false,
            native_success_assumed: false, success_reply_sent: false,
            kernel_binding: KernelBinding::Unbound, io_refs: 0, graph_refs: 0 })
    }
    fn require_binding(&self, binding: Binding) -> Result<()> {
        if self.binding != binding { return Err(Error::WrongBinding); }
        if !self.live || self.phase == Phase::Retired { return Err(Error::Revoked); }
        Ok(())
    }
    fn new_notification(&mut self, id: u64, operation: Operation) -> Result<()> {
        if id == 0 || self.used_notifications.contains(&id) { return Err(Error::Replay); }
        if self.pending.is_some() { return Err(Error::Busy); }
        self.used_notifications.push(id);
        self.pending = Some((operation, id));
        Ok(())
    }
    fn open_original(&mut self, binding: Binding) -> Result<()> {
        self.require_binding(binding)?;
        if self.phase != Phase::Reserved { return Err(Error::WrongPhase); }
        self.phase = Phase::Opened;
        Ok(())
    }
    fn begin_probe(&mut self, binding: Binding, id: u64,
                   zero_body_with_fd_minus_one_assumed: bool) -> Result<()> {
        self.require_binding(binding)?;
        if self.phase != Phase::Opened { return Err(Error::WrongPhase); }
        if !zero_body_with_fd_minus_one_assumed { return Err(Error::InvalidProbe); }
        self.new_notification(id, Operation::Probe)?;
        self.phase = Phase::ProbePending;
        Ok(())
    }
    fn complete_probe(&mut self, rc: i64, errno: i32) -> Result<()> {
        if !matches!(self.pending, Some((Operation::Probe, _))) {
            return Err(Error::WrongPhase);
        }
        self.pending = None;
        if !self.live { self.phase = Phase::Revoking; return Err(Error::Revoked); }
        if rc != -1 || errno != 9 {
            self.revoke(); return Err(Error::NativeFailure);
        }
        self.genuine_probe_assumed = true;
        self.phase = Phase::Probed;
        Ok(())
    }
    fn arm(&mut self, binding: Binding, source: SourceFact, geometry: Geometry) -> Result<()> {
        self.require_binding(binding)?;
        if self.phase != Phase::Probed || self.source.is_some() {
            return Err(Error::WrongPhase);
        }
        if !source.original_readonly_ofd_preserved || !source.complete_match
            || !source.immutable_sealed_backing {
            return Err(Error::InvalidSource);
        }
        if geometry.block_size != 4096 || geometry.original_flags != 4
            || geometry.payload_bytes == 0
            || !geometry.offset.checked_add(geometry.payload_bytes)
                .is_some_and(|end| end <= source.bytes) {
            return Err(Error::InvalidGeometry);
        }
        self.source = Some(source);
        self.geometry = Some(geometry);
        self.phase = Phase::Armed;
        Ok(())
    }
    fn begin_configure(&mut self, binding: Binding, id: u64,
                       source: SourceFact, geometry: Geometry) -> Result<()> {
        self.require_binding(binding)?;
        if self.phase != Phase::Armed || self.source != Some(source)
            || self.geometry != Some(geometry) { return Err(Error::WrongPhase); }
        self.new_notification(id, Operation::Configure)?;
        self.kernel_binding = KernelBinding::Unknown;
        self.phase = Phase::ConfigurePending;
        Ok(())
    }
    // None models a lost/unknown result. An error is not proof of an empty device.
    fn complete_configure(&mut self, native_rc_assumed: Option<i64>) -> Result<()> {
        if !matches!(self.pending, Some((Operation::Configure, _))) {
            return Err(Error::WrongPhase);
        }
        self.pending = None;
        if native_rc_assumed == Some(0) {
            self.kernel_binding = KernelBinding::Bound;
            self.native_success_assumed = true;
            if self.live { self.phase = Phase::Configured; return Ok(()); }
            self.phase = Phase::Revoking;
            return Err(Error::Revoked);
        }
        self.kernel_binding = KernelBinding::Unknown;
        self.revoke();
        Err(if native_rc_assumed.is_none() { Error::Unknown } else { Error::NativeFailure })
    }
    fn reply_success(&mut self, binding: Binding) -> Result<()> {
        self.require_binding(binding)?;
        if self.phase != Phase::Configured || !self.native_success_assumed
            || !self.genuine_probe_assumed || self.pending.is_some() {
            return Err(Error::Incomplete);
        }
        if self.success_reply_sent { return Err(Error::Replay); }
        self.success_reply_sent = true;
        Ok(())
    }
    fn borrow_graph(&mut self, binding: Binding) -> Result<()> {
        self.require_binding(binding)?;
        if self.phase != Phase::Configured { return Err(Error::WrongPhase); }
        self.graph_refs = self.graph_refs.checked_add(1).ok_or(Error::Busy)?;
        Ok(())
    }
    fn return_graph(&mut self) -> Result<()> {
        self.graph_refs = self.graph_refs.checked_sub(1).ok_or(Error::Incomplete)?;
        Ok(())
    }
    fn begin_io(&mut self, binding: Binding) -> Result<()> {
        self.require_binding(binding)?;
        if self.phase != Phase::Configured || self.graph_refs == 0 {
            return Err(Error::WrongPhase);
        }
        self.io_refs = self.io_refs.checked_add(1).ok_or(Error::Busy)?;
        Ok(())
    }
    fn complete_io(&mut self) -> Result<()> {
        self.io_refs = self.io_refs.checked_sub(1).ok_or(Error::Incomplete)?;
        Ok(())
    }
    fn revoke(&mut self) { self.live = false; self.phase = Phase::Revoking; }
    // Models a real post-drain kernel query/clear result, never a local bool witness.
    fn observe_unbound_after_drain(&mut self, exact_kernel_result_assumed: bool) -> Result<()> {
        if self.phase != Phase::Revoking || self.pending.is_some()
            || self.io_refs != 0 || self.graph_refs != 0 { return Err(Error::Busy); }
        if !exact_kernel_result_assumed { return Err(Error::Unknown); }
        self.kernel_binding = KernelBinding::Unbound;
        Ok(())
    }
    fn release_source(&mut self) -> Result<()> {
        if self.phase != Phase::Revoking || self.pending.is_some()
            || self.io_refs != 0 || self.graph_refs != 0
            || self.kernel_binding != KernelBinding::Unbound { return Err(Error::Busy); }
        self.source = None;
        self.geometry = None;
        Ok(())
    }
    fn close_target_and_remove_alias(&mut self) -> Result<()> {
        if self.phase != Phase::Revoking || self.pending.is_some()
            || self.io_refs != 0 || self.graph_refs != 0
            || self.kernel_binding != KernelBinding::Unbound { return Err(Error::Busy); }
        self.target_held = false;
        self.alias_present = false;
        Ok(())
    }
    fn finish_retirement(&mut self, kernel_no_remaining_refs_assumed: bool) -> Result<()> {
        if self.phase != Phase::Revoking || self.target_held || self.alias_present
            || self.source.is_some() || self.pending.is_some()
            || self.kernel_binding != KernelBinding::Unbound
            || self.io_refs != 0 || self.graph_refs != 0
            || !kernel_no_remaining_refs_assumed { return Err(Error::Incomplete); }
        self.controller_held = false;
        self.phase = Phase::Retired;
        Ok(())
    }
    fn invariants(&self) -> bool {
        let configured = self.phase != Phase::Configured ||
            (self.live && self.genuine_probe_assumed && self.native_success_assumed
             && self.kernel_binding == KernelBinding::Bound && self.source.is_some()
             && self.target_held && self.controller_held && self.pending.is_none());
        let unknown_retained = self.kernel_binding != KernelBinding::Unknown ||
            (self.source.is_some() && self.target_held && self.controller_held);
        let reply_has_native_fact = !self.success_reply_sent ||
            (self.genuine_probe_assumed && self.native_success_assumed);
        let retired_empty = self.phase != Phase::Retired ||
            (!self.live && !self.target_held && !self.controller_held && !self.alias_present
             && self.source.is_none() && self.pending.is_none() && self.io_refs == 0
             && self.graph_refs == 0 && self.kernel_binding == KernelBinding::Unbound);
        configured && unknown_retained && reply_has_native_fact && retired_empty
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const B: Binding = Binding { epoch: 1, actor_generation: 2, namespace_generation: 3,
        kernel_target_generation: 4, ofd_identity: 5 };
    const S: SourceFact = SourceFact { identity: 7, bytes: 16384,
        original_readonly_ofd_preserved: true, complete_match: true,
        immutable_sealed_backing: true };
    const G: Geometry = Geometry { offset: 4096, payload_bytes: 8192,
        block_size: 4096, original_flags: 4 };
    fn opened() -> Model { let mut m = Model::new(B, true).unwrap(); m.open_original(B).unwrap(); m }
    fn probed() -> Model { let mut m = opened(); m.begin_probe(B, 11, true).unwrap();
        m.complete_probe(-1, 9).unwrap(); m }
    fn armed() -> Model { let mut m = probed(); m.arm(B, S, G).unwrap(); m }
    fn pending() -> Model { let mut m = armed(); m.begin_configure(B, 12, S, G).unwrap(); m }
    fn configured() -> Model { let mut m = pending(); m.complete_configure(Some(0)).unwrap(); m }
    #[test] fn ordinary_global_device_is_never_an_issuer() {
        assert_eq!(Model::new(B, false), Err(Error::OrdinaryHostDevice));
    }
    #[test] fn original_native_probe_then_same_ofd_configure_and_retire() {
        let mut m = configured(); m.reply_success(B).unwrap(); m.revoke();
        m.observe_unbound_after_drain(true).unwrap(); m.release_source().unwrap();
        m.close_target_and_remove_alias().unwrap(); m.finish_retirement(true).unwrap();
        assert!(m.invariants()); assert_eq!(m.phase, Phase::Retired);
    }
    #[test] fn every_identity_component_is_required() {
        let variants = [Binding { epoch: 9, ..B }, Binding { actor_generation: 9, ..B },
            Binding { namespace_generation: 9, ..B }, Binding { kernel_target_generation: 9, ..B },
            Binding { ofd_identity: 9, ..B }];
        for b in variants { let mut m = armed();
            assert_eq!(m.begin_configure(b, 12, S, G), Err(Error::WrongBinding));
            assert_eq!(m.phase, Phase::Armed); }
    }
    #[test] fn fd_number_reuse_does_not_preserve_ofd_identity() {
        let mut m = opened(); assert_eq!(m.begin_probe(Binding { ofd_identity: 99, ..B },
            11, true), Err(Error::WrongBinding));
    }
    #[test] fn probe_requires_the_exact_zero_body() {
        assert_eq!(opened().begin_probe(B, 11, false), Err(Error::InvalidProbe));
    }
    #[test] fn enotty_eacces_or_fake_success_are_not_probe_success() {
        for (rc, errno) in [(-1, 25), (-1, 13), (0, 0), (-1, 22)] {
            let mut m = opened(); m.begin_probe(B, 11, true).unwrap();
            assert_eq!(m.complete_probe(rc, errno), Err(Error::NativeFailure));
            assert!(!m.genuine_probe_assumed); assert!(m.target_held); assert!(m.invariants());
        }
    }
    #[test] fn no_configure_before_probe() {
        assert_eq!(opened().arm(B, S, G), Err(Error::WrongPhase));
    }
    #[test] fn original_readonly_complete_and_sealed_custody_are_all_required() {
        for source in [SourceFact { original_readonly_ofd_preserved: false, ..S },
            SourceFact { complete_match: false, ..S },
            SourceFact { immutable_sealed_backing: false, ..S }] {
            assert_eq!(probed().arm(B, source, G), Err(Error::InvalidSource));
        }
    }
    #[test] fn geometry_cannot_overflow_or_silently_change() {
        for g in [Geometry { offset: u64::MAX, ..G }, Geometry { payload_bytes: 16385, ..G },
            Geometry { payload_bytes: 0, ..G }, Geometry { block_size: 512, ..G },
            Geometry { original_flags: 5, ..G }] {
            assert_eq!(probed().arm(B, S, g), Err(Error::InvalidGeometry));
        }
    }
    #[test] fn a_new_request_needs_a_new_notification() {
        assert_eq!(armed().begin_configure(B, 11, S, G), Err(Error::Replay));
    }
    #[test] fn source_or_geometry_cannot_be_swapped_after_arm() {
        assert_eq!(armed().begin_configure(B, 12, SourceFact { identity: 99, ..S }, G),
            Err(Error::WrongPhase));
        assert_eq!(armed().begin_configure(B, 12, S, Geometry { offset: 0, ..G }),
            Err(Error::WrongPhase));
    }
    #[test] fn no_success_reply_without_native_success() {
        assert_eq!(pending().reply_success(B), Err(Error::Incomplete));
        assert_eq!(armed().reply_success(B), Err(Error::Incomplete));
    }
    #[test] fn native_failure_and_unknown_result_keep_full_custody() {
        for outcome in [None, Some(-1)] { let mut m = pending();
            assert!(m.complete_configure(outcome).is_err());
            assert_eq!(m.kernel_binding, KernelBinding::Unknown);
            assert_eq!(m.release_source(), Err(Error::Busy));
            assert_eq!(m.close_target_and_remove_alias(), Err(Error::Busy));
            assert!(m.invariants()); }
    }
    #[test] fn owner_exit_after_submission_cannot_turn_native_success_into_guest_success() {
        let mut m = pending(); m.revoke();
        assert_eq!(m.complete_configure(Some(0)), Err(Error::Revoked));
        assert_eq!(m.kernel_binding, KernelBinding::Bound);
        assert_eq!(m.reply_success(B), Err(Error::Revoked)); assert!(m.invariants());
    }
    #[test] fn success_reply_is_single_use() {
        let mut m = configured(); m.reply_success(B).unwrap();
        assert_eq!(m.reply_success(B), Err(Error::Replay));
    }
    #[test] fn revocation_drains_graph_and_async_io_before_unbind() {
        let mut m = configured(); m.borrow_graph(B).unwrap(); m.begin_io(B).unwrap(); m.revoke();
        assert_eq!(m.begin_io(B), Err(Error::Revoked));
        assert_eq!(m.observe_unbound_after_drain(true), Err(Error::Busy));
        m.complete_io().unwrap();
        assert_eq!(m.observe_unbound_after_drain(true), Err(Error::Busy));
        m.return_graph().unwrap(); m.observe_unbound_after_drain(true).unwrap();
        m.release_source().unwrap(); m.close_target_and_remove_alias().unwrap();
        assert_eq!(m.finish_retirement(false), Err(Error::Incomplete));
        m.finish_retirement(true).unwrap(); assert!(m.invariants());
    }
    #[test] fn an_alias_unlink_or_closed_fd_is_not_retirement() {
        let mut m = configured(); m.revoke();
        assert_eq!(m.finish_retirement(true), Err(Error::Incomplete));
    }
    #[test] fn retirement_does_not_allow_reactivation() {
        let mut m = opened(); m.revoke(); m.release_source().unwrap();
        m.close_target_and_remove_alias().unwrap(); m.finish_retirement(true).unwrap();
        assert_eq!(m.open_original(B), Err(Error::Revoked));
        assert_eq!(m.begin_probe(B, 99, true), Err(Error::Revoked));
    }
    #[test] fn bounded_event_exploration_preserves_safety_invariants() {
        use std::collections::HashSet;
        let mut seen = HashSet::new();
        let mut frontier = vec![Model::new(B, true).unwrap()];
        seen.insert(frontier[0].clone());
        let mut transitions = 0_u64;
        let mut reached_fixed_point = false;
        for _depth in 0..18 {
            let mut next = Vec::new();
            for initial in frontier {
                for event in 0..19 {
                    let mut m = initial.clone();
                    let _ = match event {
                        0 => m.open_original(B),
                        1 => m.begin_probe(B, 11, true),
                        2 => m.complete_probe(-1, 9),
                        3 => m.arm(B, S, G),
                        4 => m.begin_configure(B, 12, S, G),
                        5 => m.complete_configure(Some(0)),
                        6 => m.complete_configure(None),
                        7 => m.reply_success(B),
                        8 => { if m.phase != Phase::Retired { m.revoke(); } Ok(()) },
                        9 => m.observe_unbound_after_drain(true),
                        10 => m.release_source(),
                        11 => m.close_target_and_remove_alias(),
                        12 => m.finish_retirement(true),
                        13 => { if m.graph_refs < 2 { m.borrow_graph(B) } else { Err(Error::Busy) } },
                        14 => m.return_graph(),
                        15 => { if m.io_refs < 2 { m.begin_io(B) } else { Err(Error::Busy) } },
                        16 => m.complete_io(),
                        17 => m.complete_probe(-1, 25),
                        _ => m.begin_configure(Binding { ofd_identity: 99, ..B }, 13, S, G),
                    };
                    transitions += 1;
                    assert!(m.invariants(), "failed model invariant after event {event}: {m:?}");
                    if seen.insert(m.clone()) { next.push(m); }
                }
            }
            if next.is_empty() { reached_fixed_point = true; break; }
            frontier = next;
        }
        println!("MODEL_ONLY distinct_states={} transitions={}", seen.len(), transitions);
        assert!(reached_fixed_point, "bounded state search did not reach a fixed point");
        for phase in [Phase::Reserved, Phase::Opened, Phase::ProbePending,
            Phase::Probed, Phase::Armed, Phase::ConfigurePending,
            Phase::Configured, Phase::Revoking, Phase::Retired] {
            assert!(seen.iter().any(|m| m.phase == phase), "unreached phase: {phase:?}");
        }
        assert!(seen.iter().any(|m| m.success_reply_sent));
        assert!(seen.iter().any(|m| m.kernel_binding == KernelBinding::Unknown));
        assert!(seen.iter().any(|m| m.graph_refs == 2 && m.io_refs == 2));
    }
}
