//! Source compatibility at the public namespace result boundary.
//!
//! `ReserveAttempt` must remain an enum re-export, since Rust does not permit
//! importing variants through a type alias. Unconstrained Existing constructors
//! need an expected backend type after this enum became generic.

use os_control::ReserveAttempt::{Existing, Reserved};
use os_control::ReserveAttemptWith::{Existing as WithExisting, Reserved as WithReserved};
use os_control::{
    BootId, CapSpaceId, ControlCore, ControlCoreWith, ControlMutex, DefaultLockBackend,
    DeliveryObservation, DeliveryState, LockBackend, LockRole, NativeDeliveryRequest, NativeGrant,
    NativeTarget, PublisherId, ReserveAttempt, ReserveAttemptWith, ResourceDomainId,
    StableObjectId,
};
use std::sync::{Arc, Mutex};

fn request() -> NativeDeliveryRequest {
    let target = NativeTarget::from_owner(
        Arc::new(()),
        ResourceDomainId::from_u128(4),
        StableObjectId::from_u128(5),
    )
    .unwrap();
    let grant = NativeGrant::from_owner(target, publisher(), 1, vec![]).unwrap();
    NativeDeliveryRequest::from_wire(1, grant, 1, 10, 7, 1).unwrap()
}

fn publisher() -> PublisherId {
    PublisherId::from_u128(3)
}

fn old_to_with<B: LockBackend>(value: ReserveAttempt<B>) -> ReserveAttemptWith<B> {
    value
}

fn with_to_old<B: LockBackend>(value: ReserveAttemptWith<B>) -> ReserveAttempt<B> {
    value
}

#[test]
fn original_variant_imports_match_actual_default_core_results() {
    let core = ControlCore::new(BootId::from_u128(1), CapSpaceId::from_u128(2));
    let request = request();
    let first: ReserveAttempt = core
        .reserve_native_or_get(request.clone(), publisher())
        .unwrap();
    match first {
        Reserved(token) => assert_eq!(token.id().sequence(), 1),
        Existing(_) => panic!("new delivery returned history"),
    }
    let retry: ReserveAttempt = core.reserve_native_or_get(request, publisher()).unwrap();
    match retry {
        Existing(observation) => assert_eq!(observation.state, DeliveryState::Reserved),
        Reserved(_) => panic!("retry acquired a second token"),
    }
}

#[test]
fn both_variant_import_names_preserve_one_default_enum_identity() {
    let core = ControlCore::new(BootId::from_u128(1), CapSpaceId::from_u128(2));
    let value = core.reserve_native_or_get(request(), publisher()).unwrap();
    let value: ReserveAttemptWith<DefaultLockBackend> = old_to_with(value);
    let token = match value {
        WithReserved(token) => token,
        WithExisting(_) => panic!("new delivery returned history"),
    };
    let observation = core
        .query_delivery(&core.delivery_view(), token.id().sequence())
        .unwrap();
    // The expected type retains default-backend construction for both names.
    let value: ReserveAttempt = Existing(observation);
    let value = old_to_with(value);
    match value {
        WithExisting(found) => assert_eq!(found, observation),
        WithReserved(_) => panic!("observation became authority"),
    }
    let qualified: ReserveAttempt = ReserveAttempt::Existing(observation);
    match qualified {
        Existing(found) => assert_eq!(found, observation),
        Reserved(_) => panic!("qualified observation became authority"),
    }
    let value: ReserveAttemptWith<DefaultLockBackend> = WithExisting(observation);
    match with_to_old(value) {
        Existing(found) => assert_eq!(found, observation),
        Reserved(_) => panic!("observation became authority"),
    }
}

struct AlternateBackend;

struct AlternateMutex<T>(Mutex<T>);

impl<T: Send> ControlMutex for AlternateMutex<T> {
    type Value = T;
    type Guard<'a>
        = std::sync::MutexGuard<'a, T>
    where
        Self: 'a;

    fn lock(&self) -> Self::Guard<'_> {
        self.0.lock().unwrap_or_else(|error| error.into_inner())
    }
}

impl LockBackend for AlternateBackend {
    type Mutex<T: Send> = AlternateMutex<T>;

    fn new<T: Send>(value: T, _role: LockRole) -> Self::Mutex<T> {
        AlternateMutex(Mutex::new(value))
    }
}

fn existing_for_old_name<B: LockBackend>(observation: DeliveryObservation) -> ReserveAttempt<B> {
    Existing(observation)
}

#[test]
fn reexport_and_with_names_preserve_custom_backend_result_identity() {
    let core =
        ControlCoreWith::<AlternateBackend>::new(BootId::from_u128(1), CapSpaceId::from_u128(2));
    let result = core.reserve_native_or_get(request(), publisher()).unwrap();
    let token = match with_to_old(result) {
        Reserved(token) => token,
        Existing(_) => panic!("new delivery returned history"),
    };
    let observation = core
        .query_delivery(&core.delivery_view(), token.id().sequence())
        .unwrap();
    let value = existing_for_old_name::<AlternateBackend>(observation);
    match old_to_with(value) {
        WithExisting(found) => assert_eq!(found, observation),
        WithReserved(_) => panic!("observation became authority"),
    }
}
