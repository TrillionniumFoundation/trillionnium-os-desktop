//! Read-only configured delegation for the one actual legacy-to-production
//! transition. This does not create a reservation or authorize an ID-map write.
use super::{
    Result, activation_files as files,
    activation_userdata::{self, OriginalData},
};
use droidloom_supervisor::{CellSpec, IdRange, production_identity::IdentityAuthority};
use serde_json::{Value, json};
use std::{fs, os::unix::fs::MetadataExt, path::Path};

const REGISTRY: &str = "/var/lib/droidloom/identity-reservations";
fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
pub(super) fn production_ranges(original: &CellSpec) -> Result<(IdRange, IdRange)> {
    let old = IdRange {
        start: 100000,
        count: 100000,
    };
    require(
        original.host_uid == 1000
            && original.subordinate_uids == old
            && original.subordinate_gids == old,
        "first identity transition is not the observed original Pocket4 mapping",
    )?;
    // Guest IDs on the ext4 image are unchanged. The real runtime applies the
    // dedicated namespace's IDMAP to that original filesystem and verifies its
    // root inode and guest ownership before and after mount_setattr.
    let dedicated = IdRange {
        start: 200000,
        count: 100000,
    };
    Ok((dedicated, dedicated))
}
fn proposed(original: &CellSpec) -> Result<CellSpec> {
    let mut value: CellSpec = serde_json::from_value(serde_json::to_value(original)?)?;
    (value.subordinate_uids, value.subordinate_gids) = production_ranges(original)?;
    value.validate()?;
    Ok(value)
}
fn registry(created: bool) -> Result<Value> {
    match fs::symlink_metadata(REGISTRY) {
        Err(e) if e.kind() == std::io::ErrorKind::NotFound && !created => {
            Ok(json!({"path":REGISTRY,"originally_absent":true}))
        }
        Err(e) => Err(e.into()),
        Ok(m) => {
            require(
                created
                    && m.is_dir()
                    && m.uid() == 0
                    && m.gid() == 0
                    && m.mode() & 0o7777 == 0o700
                    && fs::read_dir(REGISTRY)?.next().is_none(),
                "first activation cannot replace an earlier identity reservation",
            )?;
            let (parent, name) = files::parent(Path::new(REGISTRY))?;
            use std::os::fd::{AsRawFd, FromRawFd};
            let fd = unsafe {
                libc::openat(
                    parent.as_raw_fd(),
                    name.as_ptr(),
                    libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
                )
            };
            if fd < 0 {
                return Err(std::io::Error::last_os_error().into());
            }
            let actual = unsafe { fs::File::from_raw_fd(fd) };
            let a = actual.metadata()?;
            require(
                (m.dev(), m.ino(), m.mode(), m.uid(), m.gid())
                    == (a.dev(), a.ino(), a.mode(), a.uid(), a.gid()),
                "first reservation directory changed during observation",
            )?;
            Ok(json!({"path":REGISTRY,"device":a.dev(),"inode":a.ino(),"root_owned_empty":true}))
        }
    }
}
pub(super) fn preflight(original: &OriginalData, registry_created: bool) -> Result<Value> {
    original.revalidate_data()?;
    let new_spec = proposed(original.cell_spec())?;
    let old = match IdentityAuthority::inspect(original.cell_spec()) {
        Ok(authority) => json!({"admitted":true,"actual":authority.summary()}),
        Err(error) => json!({"admitted":false,"reason":error.to_string()}),
    };
    let authority = IdentityAuthority::inspect(&new_spec)?;
    let registry = registry(registry_created)?;
    original.revalidate_data()?;
    Ok(
        json!({"schema":"droidloom-first-dedicated-identity-transition-v1",
        "original_cell_uids":original.cell_spec().subordinate_uids,
        "original_cell_gids":original.cell_spec().subordinate_gids,
        "original_configured_delegation":old,"selected_configured_delegation":authority.summary(),
        "original_filesystems":original.persistent_policy(),"original_identity_registry":registry,
        "guest_ownership_changed":false,"host_delegation_files_modified":false,
        "identity_reservation_created":false,"namespace_mapping_observed":false,"production_ready":false}),
    )
}
pub(super) fn inspect_original() -> Result<Value> {
    let input = activation_userdata::inspect()?;
    let original = OriginalData::open(&input)?;
    let transition = preflight(&original, false)?;
    let owner = super::activation_owner::preflight(&original)?;
    original.revalidate()?;
    Ok(json!({"original":input,"identity_transition":transition,
        "original_userdata":original.receipt(),"owner_preflight":owner,"live_system_modified":false,"production_ready":false}))
}
#[cfg(test)]
mod tests {
    use super::*;
    fn legacy() -> CellSpec {
        let mut value: CellSpec = serde_json::from_slice(include_bytes!(
            "../../../packaging/cell-spec-x86_64-u1000.json"
        ))
        .unwrap();
        value.subordinate_uids = IdRange {
            start: 100000,
            count: 100000,
        };
        value.subordinate_gids = value.subordinate_uids;
        value
    }
    #[test]
    fn only_the_actual_first_mapping_may_select_the_existing_dedicated_range() {
        let old = legacy();
        let new = proposed(&old).unwrap();
        assert_eq!(
            new.subordinate_uids,
            IdRange {
                start: 200000,
                count: 100000
            }
        );
        assert_eq!(new.subordinate_gids, new.subordinate_uids);
        assert_eq!(new.data_dir, old.data_dir);
        assert_eq!(new.host_uid, old.host_uid);
        assert_eq!(old.subordinate_uids.start, 100000);
        let mut bad = legacy();
        bad.subordinate_uids.count = 65536;
        assert!(production_ranges(&bad).is_err());
        let mut bad = legacy();
        bad.subordinate_uids.start = 200000;
        assert!(production_ranges(&bad).is_err());
        let mut bad = legacy();
        bad.subordinate_gids.start = 200000;
        assert!(production_ranges(&bad).is_err());
        let mut bad = legacy();
        bad.host_uid = 1001;
        assert!(production_ranges(&bad).is_err());
    }
}
