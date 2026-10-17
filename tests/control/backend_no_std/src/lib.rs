//! External no_std compilation fixture for the public namespace-lock seam.
//!
//! This is compilation/model evidence only. Its spin wrapper neither disables
//! interrupts nor proves preemption, SMP, allocator or actual kernel safety.
//! The fixture has no entry point or global allocator and is not a boot image.

#![no_std]

extern crate alloc;

use alloc::sync::Arc;
use core::marker::PhantomData;
use core::ops::{Deref, DerefMut};
use os_control::{
    BootId, CapSpaceId, ControlCoreWith, ControlMutex, DeliveryError, DeliveryObservation,
    DeliveryState, DeliveryViewWith, HistoryAck, LockBackend, LockRole, NativeDeliveryRequest,
    NativeGrant, NativeResourceState, NativeResourceUpdate, NativeTarget,
    OriginalOwnerAuthorityWith, OwnerId, OwnerReceipt, PublishOutcome, PublisherId,
    ReserveTokenWith, ResourceDomainId, StableObjectId, WeakControlCoreWith,
};

/// A downstream backend, with no access to os-control's private lock module.
pub struct FixtureBackend;

pub struct FixtureMutex<T> {
    inner: spin::Mutex<T>,
    role: LockRole,
}

impl<T> FixtureMutex<T> {
    pub const fn role(&self) -> LockRole {
        self.role
    }
}

/// A real kernel guard may retain CPU-local interrupt/preemption state.
/// This marker deliberately forbids transferring our guard to another thread.
pub struct FixtureGuard<'a, T> {
    guard: spin::MutexGuard<'a, T>,
    not_send: PhantomData<*mut ()>,
}

impl<T> Deref for FixtureGuard<'_, T> {
    type Target = T;

    fn deref(&self) -> &Self::Target {
        &self.guard
    }
}

impl<T> DerefMut for FixtureGuard<'_, T> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.guard
    }
}

impl<T: Send> ControlMutex for FixtureMutex<T> {
    type Value = T;
    type Guard<'a>
        = FixtureGuard<'a, T>
    where
        Self: 'a;

    fn lock(&self) -> Self::Guard<'_> {
        FixtureGuard {
            guard: self.inner.lock(),
            not_send: PhantomData,
        }
    }
}

impl LockBackend for FixtureBackend {
    type Mutex<T: Send> = FixtureMutex<T>;

    fn new<T: Send>(value: T, role: LockRole) -> Self::Mutex<T> {
        FixtureMutex {
            inner: spin::Mutex::new(value),
            role,
        }
    }
}

// A compile-time negative assertion, without a dependency or unsafe code.
// If the guard becomes Send, both implementations satisfy the inferred `_`
// argument and this item fails to compile through ambiguous trait selection.
const _: fn() = || {
    trait AmbiguousIfSend<A> {
        fn check() {}
    }
    impl<T: ?Sized> AmbiguousIfSend<()> for T {}
    impl<T: ?Sized + Send> AmbiguousIfSend<u8> for T {}
    let _ = <FixtureGuard<'static, ()> as AmbiguousIfSend<_>>::check;
};

struct Owner {
    state: spin::Mutex<OwnerState>,
}

struct OwnerState {
    metadata: NativeResourceState,
    cap_ns: u64,
}

/// Type-check the actual generic namespace, typed native execution and history.
///
/// The synthetic owner has exactly one cap and one metadata state. This does
/// not authenticate any IDs, meter runtime or implement a real scheduler.
/// A successful bare-target build does not mean this function ran in a kernel.
pub fn exercise_namespace_api() -> Result<DeliveryObservation, DeliveryError> {
    // A !Send guard must not unnecessarily prevent the namespace's owned
    // handles from being shared or handed to a worker between lock calls.
    fn assert_send_sync<T: Send + Sync>() {}
    assert_send_sync::<ControlCoreWith<FixtureBackend>>();
    assert_send_sync::<WeakControlCoreWith<FixtureBackend>>();
    assert_send_sync::<DeliveryViewWith<FixtureBackend>>();
    assert_send_sync::<ReserveTokenWith<FixtureBackend>>();
    assert_send_sync::<OriginalOwnerAuthorityWith<FixtureBackend>>();
    let boot = BootId::from_u128(1);
    let space = CapSpaceId::from_u128(2);
    let history_owner = OwnerId::from_u128(3);
    let publisher = PublisherId::from_u128(4);
    let resource = ResourceDomainId::from_u128(5);
    let object = StableObjectId::from_u128(6);
    let (core, authority) =
        ControlCoreWith::<FixtureBackend>::with_capacity_for_owner(boot, space, 2, history_owner)?;
    // FixtureBackend is deliberately not Clone. Handle cloning depends only
    // on their namespace Arc/Weak, so these methods need no B: Clone bound.
    let core = core.clone();
    let weak = core.downgrade().clone();
    let restored = weak.upgrade().ok_or(DeliveryError::HistoryLost)?;
    if restored.identity() != core.identity() {
        return Err(DeliveryError::InvalidIdentity);
    }
    let view = core.delivery_view_for(history_owner)?.clone();
    let owner = Arc::new(Owner {
        state: spin::Mutex::new(OwnerState {
            metadata: NativeResourceState::new(resource, object)
                .map_err(|_| DeliveryError::InvalidRequest)?,
            cap_ns: 0,
        }),
    });
    let target = NativeTarget::from_owner(Arc::clone(&owner), resource, object)
        .map_err(|_| DeliveryError::InvalidRequest)?;
    let grant = NativeGrant::from_owner(target, publisher, 1, alloc::vec::Vec::new())
        .map_err(|_| DeliveryError::InvalidRequest)?;
    let request = NativeDeliveryRequest::from_wire(1, grant, 1, 10, 7, 1)?;
    let token = core.reserve_native(request, publisher)?;
    let pending = core.query_delivery(&view, 1)?;
    if pending.state != DeliveryState::Reserved {
        return Err(DeliveryError::InvalidPublish);
    }
    let terminal = core.execute_native_reserved::<Owner, _>(&token, publisher, |context| {
        let mut state = context.owner().state.lock();
        let OwnerState { metadata, cap_ns } = &mut *state;
        let binding = context.binding();
        let mut mutation = || *cap_ns = binding.cap_ns;
        match metadata.apply(NativeResourceUpdate::from(binding), 50, 0, &mut mutation) {
            Ok(receipt) => receipt.into_publish_outcome(),
            Err(error) => PublishOutcome::Failure {
                status: error.delivery_status(),
            },
        }
    })?;
    if core.query_delivery(&view, 1)? != terminal {
        return Err(DeliveryError::InvalidPublish);
    }
    let ack = HistoryAck::from_owner_receipt(
        core.identity(),
        1,
        OwnerReceipt::new(history_owner, [0x71; 32]),
    )?;
    core.retire_through(&view, ack, &authority)?;
    if core.query_delivery(&view, 1)?.state != DeliveryState::Retired {
        return Err(DeliveryError::InvalidPublish);
    }
    Ok(terminal)
}
