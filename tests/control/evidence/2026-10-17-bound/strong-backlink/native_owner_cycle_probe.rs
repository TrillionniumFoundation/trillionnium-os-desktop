use os_control::{BootId, CapSpaceId, ControlCore, NativeDeliveryRequest, NativeGrant,
    NativeTarget, PublisherId, ResourceDomainId, StableObjectId};
use std::sync::{Arc, atomic::{AtomicBool, Ordering}};

struct Owner {
    namespace: ControlCore,
    dropped: Arc<AtomicBool>,
}

impl Drop for Owner {
    fn drop(&mut self) { self.dropped.store(true, Ordering::SeqCst); }
}

fn main() {
    let core = ControlCore::new(BootId::from_u128(1), CapSpaceId::from_u128(2));
    let dropped = Arc::new(AtomicBool::new(false));
    let owner = Arc::new(Owner { namespace: core.clone(), dropped: dropped.clone() });
    let weak_owner = Arc::downgrade(&owner);
    let target = NativeTarget::from_owner(owner.clone(), ResourceDomainId::from_u128(3),
        StableObjectId::from_u128(4)).unwrap();
    let publisher = PublisherId::from_u128(5);
    let grant = NativeGrant::from_owner(target, publisher, 1, vec![]).unwrap();
    let request = NativeDeliveryRequest::from_wire(1, grant, 1, 17, 7, 11).unwrap();
    let token = core.reserve_native(request, publisher).unwrap();
    drop(token);
    drop(owner);
    drop(core);

    let retained_after_all_external_handles = weak_owner.upgrade().is_some();
    println!("owner retained after external core/token/owner drops: {retained_after_all_external_handles}");
    // Rescue and explicitly close the cycle before reporting failure; this
    // probe itself leaves no leaked owner or blocked worker behind.
    if let Some(rescue) = weak_owner.upgrade() {
        rescue.namespace.lose_history();
        drop(rescue);
    }
    assert!(dropped.load(Ordering::SeqCst), "probe cleanup failed");
    assert!(!retained_after_all_external_handles,
        "native owner backreference made namespace destruction unreachable");
}
