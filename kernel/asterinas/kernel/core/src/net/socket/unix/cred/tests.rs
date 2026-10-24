// SPDX-License-Identifier: MPL-2.0

use ostd::prelude::ktest;

use super::*;

#[ktest]
fn socket_identity_captures_distinct_real_effective_ids_without_live_credential_alias() {
    let credentials: Credentials = Credentials::new_root();
    credentials
        .set_resgid(
            Some(Gid::new(60001)),
            Some(Gid::new(60002)),
            Some(Gid::new(60003)),
        )
        .unwrap();
    credentials
        .set_resuid(
            Some(Uid::new(60001)),
            Some(Uid::new(60002)),
            Some(Uid::new(60003)),
        )
        .unwrap();
    let captured = SocketCred::<ReadDupOp>::capture(4242, &credentials.dup().restrict());
    let alias = captured.dup().restrict::<ReadOp>();
    credentials
        .set_resgid(
            Some(Gid::new(60002)),
            Some(Gid::new(60003)),
            Some(Gid::new(60001)),
        )
        .unwrap();
    credentials
        .set_resuid(
            Some(Uid::new(60002)),
            Some(Uid::new(60003)),
            Some(Uid::new(60001)),
        )
        .unwrap();
    assert_eq!(credentials.ruid(), Uid::new(60002));
    assert_eq!(credentials.euid(), Uid::new(60003));
    drop(credentials);
    assert_eq!(
        alias.to_real_c_cred(),
        CUserCred {
            pid: 4242,
            uid: Uid::new(60001),
            gid: Gid::new(60001)
        }
    );
    assert_eq!(
        alias.to_effective_c_cred(),
        CUserCred {
            pid: 4242,
            uid: Uid::new(60002),
            gid: Gid::new(60002)
        }
    );
    drop(captured);
    assert_eq!(alias.to_real_c_cred().uid, Uid::new(60001));
}

#[ktest]
fn socket_group_snapshot_shares_original_immutable_owner_across_fork_replace_and_last_alias() {
    let credentials: Credentials = Credentials::new_root();
    let original: Arc<BTreeSet<Gid>> = Arc::new([Gid::new(60003), Gid::new(60004)].into_iter().collect());
    let old_weak = Arc::downgrade(&original);
    credentials.set_groups(original.clone());
    let fork: Credentials = Credentials::new_from(&credentials);
    let captured = SocketCred::<ReadDupOp>::capture(4243, &credentials.dup().restrict());
    let alias = captured.dup().restrict::<ReadOp>();
    assert!(Arc::ptr_eq(&captured.groups, &original));
    assert!(Arc::ptr_eq(&fork.groups(), &original));
    // Repeated message capture shares the existing owner, without group copying.
    let count = Arc::strong_count(&original);
    for _ in 0..128 {
        let message = SocketCred::<ReadOp>::capture(4243, &credentials.dup().restrict());
        assert!(Arc::ptr_eq(&message.groups, &original));
        assert_eq!(Arc::strong_count(&original), count + 1);
    }
    assert_eq!(Arc::strong_count(&original), count);
    let replacement: Arc<BTreeSet<Gid>> = Arc::new([Gid::new(60005)].into_iter().collect());
    let new_weak = Arc::downgrade(&replacement);
    credentials.set_groups(replacement.clone());
    assert!(Arc::ptr_eq(&credentials.groups(), &replacement));
    assert_eq!(&*captured.groups(), &[Gid::new(60003), Gid::new(60004)]);
    assert!(Arc::ptr_eq(&fork.groups(), &original));
    drop((original, fork, captured));
    assert!(old_weak.upgrade().is_some());
    drop(alias);
    assert!(old_weak.upgrade().is_none());
    drop((replacement, credentials));
    assert!(new_weak.upgrade().is_none());
}
