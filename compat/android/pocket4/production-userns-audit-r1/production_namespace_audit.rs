//! Existing active user-namespace map occupancy, read from the running kernel.
//!
//! This module grants no delegation, reservation, or Android launch authority.
//! It requires the initial host user/PID namespaces and effective CAP_SYS_ADMIN/CAP_SYS_PTRACE,
//! uses listns(USER_NS, owner=0), holds typed nsfs handles, and reads each
//! noninitial namespace's maps through an owned, pidfd-bound collector child.
//! Reads are performed by the parent in the initial user namespace: map column
//! two is therefore the host-ID range, including for nested user namespaces.
//!
//! Linux listns enumerates ACTIVE namespace objects. Kernel active references
//! propagate through owning user namespaces, and include nsfs and namespace-FD
//! holders. Purely inactive internal references and future namespace creation
//! are not a reservation lock or proof of permanent range release. A clean
//! active snapshot therefore returns CoverageIncomplete and issues no guard.
//! Durable leases, NSS/subid checks and a writer policy remain independent
//! prerequisites; none substitutes for the missing inactive-map coverage.
//!
//! There is no alternate proc root, injected inventory, serialized guard,
//! caller-provided witness PID, or exclusion list in the production API.

use std::collections::BTreeSet;
use std::ffi::CString;
use std::fmt;
use std::fs::File;
use std::io::{self, Read};
use std::mem::{self, MaybeUninit};
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::time::{Duration, Instant};

use serde::Serialize;

use crate::IdRange;

const NS_GET_NSTYPE: libc::c_ulong = 0xb703;
const NS_GET_PARENT: libc::c_ulong = 0xb702;
const NS_GET_ID: libc::c_ulong = 0x8008_b70d;
const NSFS_MAGIC: libc::c_long = 0x6e73_6673;
const PROC_MAGIC: libc::c_long = 0x9fa0;
const INITIAL_USER_INODE: u64 = 0xefff_fffd;
const INITIAL_PID_INODE: u64 = 0xefff_fffc;
const FD_NSFS_ROOT: libc::c_int = -10003;
const FILEID_NSFS: libc::c_int = 0xf1;
const MAX_NAMESPACES: usize = 256;
const MAX_MAP_BYTES: usize = 64 * 1024;
const MAX_EXTENTS: usize = 340;
const MAX_TOTAL_MAP_BYTES: usize = 16 * 1024 * 1024;
const MAX_AUDIT_TIME: Duration = Duration::from_secs(45);
const RETIRE_RESERVE: Duration = Duration::from_secs(2);
const CAP_SYS_ADMIN_BIT: u64 = 1 << 21;
const CAP_SYS_PTRACE_BIT: u64 = 1 << 19;

#[repr(C)]
struct NamespaceRequest {
    size: u32,
    spare: u32,
    last_id: u64,
    namespace_type: u32,
    spare2: u32,
    owner_id: u64,
}

#[repr(C)]
struct NamespaceFileHandle {
    handle_bytes: u32,
    handle_type: i32,
    namespace_id: u64,
    namespace_type: u32,
    inode: u32,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(super) struct NamespaceIdentity {
    pub(super) device: u64,
    pub(super) inode: u64,
    pub(super) namespace_id: u64,
    pub(super) namespace_type: i32,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub(super) struct MapExtent {
    pub(super) inside_start: u32,
    pub(super) host_start: u32,
    pub(super) count: u32,
}

#[derive(Clone, Debug, Serialize)]
pub(super) struct AuditIssue {
    pub(super) code: &'static str,
    pub(super) namespace_id: Option<u64>,
    pub(super) errno: Option<i32>,
}

impl AuditIssue {
    fn new(code: &'static str) -> Self {
        Self {
            code,
            namespace_id: None,
            errno: None,
        }
    }

    fn io(code: &'static str, error: io::Error) -> Self {
        Self {
            code,
            namespace_id: None,
            errno: error.raw_os_error(),
        }
    }

    fn for_namespace(mut self, id: u64) -> Self {
        self.namespace_id = Some(id);
        self
    }
}

type Observation<T> = std::result::Result<T, AuditIssue>;

#[derive(Clone, Debug, Serialize)]
pub(super) struct ChildTerminal {
    pub(super) pid: i32,
    pub(super) tid: i32,
    pub(super) starttime: Option<u64>,
    pub(super) namespace_id: u64,
    pub(super) exit_code: i32,
    pub(super) reaped: bool,
}

#[derive(Clone, Debug, Serialize)]
pub(super) struct NamespaceMaps {
    pub(super) namespace: NamespaceIdentity,
    pub(super) parent: NamespaceIdentity,
    pub(super) uid_map: Vec<MapExtent>,
    pub(super) gid_map: Vec<MapExtent>,
    pub(super) uid_map_bytes: usize,
    pub(super) gid_map_bytes: usize,
    pub(super) witness_pid: i32,
    pub(super) witness_tid: i32,
    pub(super) witness_starttime: u64,
    pub(super) witness_proc_device: u64,
    pub(super) witness_proc_inode: u64,
}

#[derive(Clone, Debug, Serialize)]
pub(super) struct NamespaceConflict {
    pub(super) namespace_id: u64,
    pub(super) axis: &'static str,
    pub(super) existing_host_start: u32,
    pub(super) existing_count: u32,
    pub(super) requested_start: u32,
    pub(super) requested_count: u32,
}

#[derive(Clone, Debug, Serialize)]
pub(super) struct NamespaceAuditReport {
    pub(super) schema: &'static str,
    pub(super) status: &'static str,
    pub(super) enumeration: &'static str,
    pub(super) active_owner_chain_included: bool,
    pub(super) inactive_kernel_only_references_included: bool,
    pub(super) future_writer_lock: bool,
    pub(super) namespace_mapping_authorized: bool,
    pub(super) uid_map_host_view: bool,
    pub(super) initial_namespace: Option<NamespaceIdentity>,
    pub(super) initial_pid_namespace: Option<NamespaceIdentity>,
    pub(super) initial_namespace_excluded_from_occupancy: bool,
    pub(super) enumerated_namespace_ids: Vec<u64>,
    pub(super) namespace_maps: Vec<NamespaceMaps>,
    pub(super) conflicts: Vec<NamespaceConflict>,
    pub(super) unknown: Vec<AuditIssue>,
    pub(super) children_created: usize,
    pub(super) children_reaped: usize,
    pub(super) child_terminals: Vec<ChildTerminal>,
    pub(super) final_enumeration_matches: bool,
    pub(super) parent_identity_unchanged: bool,
    pub(super) parent_user_namespace_unchanged: bool,
    pub(super) parent_mount_namespace_unchanged: bool,
    pub(super) uid_or_gid_map_writes: u32,
    pub(super) android_actions: u32,
}

impl NamespaceAuditReport {
    fn new() -> Self {
        Self {
            schema: "droidloom-active-userns-occupancy-v1",
            status: "UNKNOWN",
            enumeration: "Linux listns USER_NS, owner=0; held nsfs handles",
            active_owner_chain_included: false,
            inactive_kernel_only_references_included: false,
            future_writer_lock: false,
            namespace_mapping_authorized: false,
            uid_map_host_view: false,
            initial_namespace: None,
            initial_pid_namespace: None,
            initial_namespace_excluded_from_occupancy: false,
            enumerated_namespace_ids: Vec::new(),
            namespace_maps: Vec::new(),
            conflicts: Vec::new(),
            unknown: Vec::new(),
            children_created: 0,
            children_reaped: 0,
            child_terminals: Vec::new(),
            final_enumeration_matches: false,
            parent_identity_unchanged: false,
            parent_user_namespace_unchanged: false,
            parent_mount_namespace_unchanged: false,
            uid_or_gid_map_writes: 0,
            android_actions: 0,
        }
    }
}

/// Every variant refuses creation. UNKNOWN retains already observed conflicts.
#[derive(Debug)]
pub(super) enum AuditError {
    Conflict(NamespaceAuditReport),
    Unknown(NamespaceAuditReport),
    /// Active enumeration cannot prove absence of resurrectable inactive maps.
    CoverageIncomplete(NamespaceAuditReport),
}

impl AuditError {
    pub(super) fn report(&self) -> &NamespaceAuditReport {
        match self {
            Self::Conflict(report) | Self::Unknown(report) | Self::CoverageIncomplete(report) => {
                report
            }
        }
    }
}

impl fmt::Display for AuditError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let report = self.report();
        write!(
            f,
            "user namespace occupancy {}: {} conflicts, {} unknown conditions",
            report.status,
            report.conflicts.len(),
            report.unknown.len()
        )
    }
}

impl std::error::Error for AuditError {}

struct NamespaceHandle {
    file: File,
    identity: NamespaceIdentity,
}

impl NamespaceHandle {
    fn from_file(file: File, expected_type: i32) -> Observation<Self> {
        let identity = namespace_identity(&file)?;
        if identity.namespace_type != expected_type {
            return Err(AuditIssue::new("namespace_type_mismatch"));
        }
        Ok(Self { file, identity })
    }

    fn revalidate(&self) -> Observation<()> {
        if namespace_identity(&self.file)? != self.identity {
            return Err(AuditIssue::new("held_namespace_identity_changed"));
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct Credentials {
    uids: [u32; 3],
    gids: [u32; 3],
    groups: Vec<u32>,
    effective_capabilities: u64,
}

struct HostIdentity {
    user: NamespaceHandle,
    pid_namespace: NamespaceHandle,
    mount: NamespaceHandle,
    proc_root: File,
    pid: i32,
    tid: i32,
    starttime: u64,
    credentials: Credentials,
    creator_thread_pidfd: File,
    signal_mask: u64,
    suid_dumpable: u32,
}

/// A real-kernel, non-serializable occupancy observation with retained nsfs FDs.
///
/// Not a lease or permission to write maps. A broker must call revalidate
/// immediately before its own map transaction and preserve all independent
/// delegation, NSS, durable-reservation and child-custody guards.
pub(super) struct NamespaceAuditGuard {
    requested_uids: IdRange,
    requested_gids: IdRange,
    host: HostIdentity,
    held: Vec<NamespaceHandle>,
    report: NamespaceAuditReport,
}

impl fmt::Debug for NamespaceAuditGuard {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("NamespaceAuditGuard")
            .field("namespace_count", &self.held.len())
            .field("status", &self.report.status)
            .finish_non_exhaustive()
    }
}

impl NamespaceAuditGuard {
    pub(super) fn report(&self) -> &NamespaceAuditReport {
        &self.report
    }

    /// Repeat real inventory/maps and replace retained evidence only on success.
    /// A changed caller, unsupported API, new conflict or incomplete evidence
    /// fails closed. Call before creating the broker's own unmapped userns:
    /// empty maps are UNKNOWN and there is no own-namespace exclusion.
    /// No externally asserted namespace exclusion is accepted.
    pub(super) fn revalidate(&mut self, deadline: Instant) -> Result<(), AuditError> {
        if let Err(issue) = self.host.revalidate() {
            let mut report = self.report.clone();
            report.status = "UNKNOWN";
            report.unknown.push(issue);
            return Err(AuditError::Unknown(report));
        }
        for handle in &self.held {
            if let Err(issue) = handle.revalidate() {
                let mut report = self.report.clone();
                report.status = "UNKNOWN";
                report.unknown.push(issue);
                return Err(AuditError::Unknown(report));
            }
        }
        let fresh =
            audit_existing_user_namespaces(self.requested_uids, self.requested_gids, deadline)?;
        for old in &self.held {
            if !fresh.held.iter().any(|new| new.identity == old.identity) {
                let mut report = fresh.report.clone();
                report.status = "UNKNOWN";
                report.unknown.push(
                    AuditIssue::new("held_namespace_missing_from_fresh_enumeration")
                        .for_namespace(old.identity.namespace_id),
                );
                return Err(AuditError::Unknown(report));
            }
        }
        for old in &self.report.namespace_maps {
            let same = fresh.report.namespace_maps.iter().any(|new| {
                new.namespace == old.namespace
                    && new.parent == old.parent
                    && new.uid_map == old.uid_map
                    && new.gid_map == old.gid_map
            });
            if !same {
                let mut report = fresh.report.clone();
                report.status = "UNKNOWN";
                report.unknown.push(
                    AuditIssue::new("committed_maps_changed")
                        .for_namespace(old.namespace.namespace_id),
                );
                return Err(AuditError::Unknown(report));
            }
        }
        *self = fresh;
        Ok(())
    }
}

/// Audit actual active namespace mappings. This never writes an ID map.
///
/// A clean active snapshot still returns CoverageIncomplete: v7.0 listns
/// excludes inactive, potentially resurrectable namespaces. This API presently
/// issues no production guard without stronger coverage/provenance. Definite
/// active overlaps are retained as Conflict; other failures remain Unknown.
///
/// The running kernel must support listns and nsfs export handles. There is
/// deliberately no proc-only "clean" fallback when those APIs are unavailable.
pub(super) fn audit_existing_user_namespaces(
    uids: IdRange,
    gids: IdRange,
    deadline: Instant,
) -> Result<NamespaceAuditGuard, AuditError> {
    let mut report = NamespaceAuditReport::new();
    let result = observe(uids, gids, deadline, &mut report);
    match result {
        Ok((_host, _held)) if report.unknown.is_empty() && report.conflicts.is_empty() => {
            // listns intentionally omits inactive objects, including network
            // namespaces still held by sockets and later resurrectable through
            // SIOCGSKNS. Current grants or a new lease are not historical proof.
            // Until stronger kernel coverage/range provenance exists, never
            // mint a guard that could let the production broker write maps.
            report.status = "COVERAGE_INCOMPLETE";
            report.unknown.push(AuditIssue::new(
                "inactive_kernel_namespace_maps_not_enumerated",
            ));
            Err(AuditError::CoverageIncomplete(report))
        }
        Ok(_) | Err(_) => {
            if let Err(issue) = result {
                report.unknown.push(issue);
            }
            if report.unknown.is_empty() && !report.conflicts.is_empty() {
                report.status = "CONFLICT";
                Err(AuditError::Conflict(report))
            } else {
                report.status = "UNKNOWN";
                Err(AuditError::Unknown(report))
            }
        }
    }
}

fn observe(
    uids: IdRange,
    gids: IdRange,
    deadline: Instant,
    report: &mut NamespaceAuditReport,
) -> Observation<(HostIdentity, Vec<NamespaceHandle>)> {
    let now = Instant::now();
    if deadline <= now + RETIRE_RESERVE || deadline > now + MAX_AUDIT_TIME {
        return Err(AuditIssue::new("invalid_or_exhausted_audit_deadline"));
    }
    checked_range(uids.start, uids.count)?;
    checked_range(gids.start, gids.count)?;
    if uids.start == 0 || gids.start == 0 {
        return Err(AuditIssue::new("host_root_is_not_a_candidate_range"));
    }
    let host = HostIdentity::capture()?;
    report.initial_namespace = Some(host.user.identity.clone());
    report.initial_pid_namespace = Some(host.pid_namespace.identity.clone());
    report.initial_namespace_excluded_from_occupancy = true;
    report.uid_map_host_view = true;
    let ids = list_user_namespaces(deadline)?;
    report.enumerated_namespace_ids = ids.clone();
    if !ids.contains(&host.user.identity.namespace_id) {
        return Err(AuditIssue::new(
            "initial_namespace_missing_from_global_inventory",
        ));
    }
    let mut held = Vec::with_capacity(ids.len());
    for id in &ids {
        check_time(deadline)?;
        let handle = open_namespace_handle(*id)?;
        if handle.identity.device != host.user.identity.device {
            return Err(AuditIssue::new("namespace_device_changed").for_namespace(*id));
        }
        held.push(handle);
    }
    let unique: BTreeSet<_> = held
        .iter()
        .map(|n| (n.identity.device, n.identity.inode))
        .collect();
    if unique.len() != held.len() {
        return Err(AuditIssue::new("duplicate_namespace_object"));
    }
    let mut total_map_bytes = 0usize;
    for handle in &held {
        check_time(deadline)?;
        if handle.identity == host.user.identity {
            continue;
        }
        let parent = parent_namespace(handle)?;
        if !held.iter().any(|known| known.identity == parent.identity) {
            return Err(AuditIssue::new("owner_chain_missing_from_global_inventory")
                .for_namespace(handle.identity.namespace_id));
        }
        // Retained handles make the parent chain stable; require it to reach
        // the one proved initial user namespace, within Linux's nesting bound.
        verify_ancestry(handle, &held, &host.user.identity)?;
        let attempt = collect_maps(handle, &parent.identity, &host, deadline);
        report.children_created += usize::from(attempt.created);
        if let Some(terminal) = attempt.terminal {
            report.children_reaped += usize::from(terminal.reaped);
            report.child_terminals.push(terminal);
        }
        match attempt.result {
            Ok(maps) => {
                total_map_bytes = total_map_bytes
                    .checked_add(maps.uid_map_bytes + maps.gid_map_bytes)
                    .ok_or_else(|| AuditIssue::new("map_byte_budget_overflow"))?;
                if total_map_bytes > MAX_TOTAL_MAP_BYTES {
                    return Err(AuditIssue::new("aggregate_map_byte_bound"));
                }
                add_conflicts(&maps, uids, gids, &mut report.conflicts);
                report.namespace_maps.push(maps);
            }
            Err(issue) => report
                .unknown
                .push(issue.for_namespace(handle.identity.namespace_id)),
        }
    }
    report.active_owner_chain_included = true;
    for handle in &held {
        handle.revalidate()?;
    }
    let final_ids = list_user_namespaces(deadline)?;
    report.final_enumeration_matches = final_ids == ids;
    if !report.final_enumeration_matches {
        report
            .unknown
            .push(AuditIssue::new("active_namespace_set_changed"));
    }
    host.revalidate()?;
    report.parent_identity_unchanged = true;
    report.parent_user_namespace_unchanged = true;
    report.parent_mount_namespace_unchanged = true;
    if report.children_created != report.children_reaped {
        report
            .unknown
            .push(AuditIssue::new("owned_collector_not_reaped"));
    }
    Ok((host, held))
}

fn check_time(deadline: Instant) -> Observation<()> {
    if Instant::now() + RETIRE_RESERVE >= deadline {
        return Err(AuditIssue::new("audit_deadline_exhausted"));
    }
    Ok(())
}

fn checked_range(start: u32, count: u32) -> Observation<(u64, u64)> {
    let end = u64::from(start) + u64::from(count);
    if count == 0 || end > u64::from(u32::MAX) {
        return Err(AuditIssue::new("invalid_or_overflowing_id_range"));
    }
    Ok((u64::from(start), end))
}

fn decimal(text: &str) -> Observation<u32> {
    if text.is_empty() || !text.bytes().all(|b| b.is_ascii_digit()) {
        return Err(AuditIssue::new("invalid_map_decimal"));
    }
    text.parse()
        .map_err(|_| AuditIssue::new("map_decimal_overflow"))
}

fn parse_map(raw: &[u8]) -> Observation<Vec<MapExtent>> {
    let text = std::str::from_utf8(raw).map_err(|_| AuditIssue::new("non_utf8_id_map"))?;
    if raw.len() > MAX_MAP_BYTES {
        return Err(AuditIssue::new("id_map_byte_bound"));
    }
    let mut extents = Vec::new();
    for line in text.lines() {
        let fields: Vec<_> = line.split_ascii_whitespace().collect();
        if fields.len() != 3 || extents.len() >= MAX_EXTENTS {
            return Err(AuditIssue::new("invalid_id_map_shape_or_extent_bound"));
        }
        let extent = MapExtent {
            inside_start: decimal(fields[0])?,
            host_start: decimal(fields[1])?,
            count: decimal(fields[2])?,
        };
        checked_range(extent.inside_start, extent.count)?;
        checked_range(extent.host_start, extent.count)?;
        extents.push(extent);
    }
    if extents.is_empty() {
        return Err(AuditIssue::new("empty_uncommitted_id_map"));
    }
    for host_axis in [false, true] {
        let mut ranges: Vec<_> = extents
            .iter()
            .map(|extent| {
                let start = if host_axis {
                    extent.host_start
                } else {
                    extent.inside_start
                };
                (u64::from(start), u64::from(start) + u64::from(extent.count))
            })
            .collect();
        ranges.sort_unstable();
        if ranges.windows(2).any(|pair| pair[0].1 > pair[1].0) {
            return Err(AuditIssue::new("overlapping_id_map_extents"));
        }
    }
    Ok(extents)
}

fn overlaps(start: u32, count: u32, requested: IdRange) -> bool {
    u64::from(start) < u64::from(requested.start) + u64::from(requested.count)
        && u64::from(requested.start) < u64::from(start) + u64::from(count)
}

fn add_conflicts(
    maps: &NamespaceMaps,
    uids: IdRange,
    gids: IdRange,
    conflicts: &mut Vec<NamespaceConflict>,
) {
    for (axis, extents, requested) in [("uid", &maps.uid_map, uids), ("gid", &maps.gid_map, gids)] {
        for extent in extents {
            if overlaps(extent.host_start, extent.count, requested) {
                conflicts.push(NamespaceConflict {
                    namespace_id: maps.namespace.namespace_id,
                    axis,
                    existing_host_start: extent.host_start,
                    existing_count: extent.count,
                    requested_start: requested.start,
                    requested_count: requested.count,
                });
            }
        }
    }
}

fn fstype(file: &File) -> Observation<libc::c_long> {
    let mut value = MaybeUninit::<libc::statfs>::uninit();
    // SAFETY: fstatfs initializes the supplied statfs on success; FD is held.
    if unsafe { libc::fstatfs(file.as_raw_fd(), value.as_mut_ptr()) } != 0 {
        return Err(AuditIssue::io("fstatfs_failed", io::Error::last_os_error()));
    }
    // SAFETY: the preceding successful syscall initialized the value.
    Ok(unsafe { value.assume_init() }.f_type)
}

fn namespace_identity(file: &File) -> Observation<NamespaceIdentity> {
    if fstype(file)? != NSFS_MAGIC {
        return Err(AuditIssue::new("namespace_fd_is_not_nsfs"));
    }
    let meta = file
        .metadata()
        .map_err(|error| AuditIssue::io("namespace_fstat_failed", error))?;
    // SAFETY: no output pointer for NS_GET_NSTYPE; file is a retained nsfs FD.
    let kind = unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_NSTYPE) };
    if kind < 0 {
        return Err(AuditIssue::io(
            "namespace_type_ioctl_failed",
            io::Error::last_os_error(),
        ));
    }
    let mut id = 0u64;
    // SAFETY: NS_GET_ID writes one u64 into the valid supplied pointer.
    if unsafe { libc::ioctl(file.as_raw_fd(), NS_GET_ID, &mut id) } != 0 || id == 0 {
        return Err(AuditIssue::io(
            "namespace_id_ioctl_failed",
            io::Error::last_os_error(),
        ));
    }
    Ok(NamespaceIdentity {
        device: meta.dev(),
        inode: meta.ino(),
        namespace_id: id,
        namespace_type: kind,
    })
}

fn open_namespace_handle(id: u64) -> Observation<NamespaceHandle> {
    let handle = NamespaceFileHandle {
        handle_bytes: 16,
        handle_type: FILEID_NSFS,
        namespace_id: id,
        namespace_type: 0,
        inode: 0,
    };
    // SAFETY: the exact 8-byte file_handle header and 16-byte nsfs payload are
    // repr(C). Both optional type/inode selectors are zero as required by UAPI.
    let fd = unsafe {
        libc::syscall(
            libc::SYS_open_by_handle_at,
            FD_NSFS_ROOT,
            &handle as *const NamespaceFileHandle,
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(
            AuditIssue::io("namespace_handle_open_failed", io::Error::last_os_error())
                .for_namespace(id),
        );
    }
    // SAFETY: successful open_by_handle_at returned a new owned descriptor.
    let file = unsafe { File::from_raw_fd(fd as RawFd) };
    let result = NamespaceHandle::from_file(file, libc::CLONE_NEWUSER)?;
    if result.identity.namespace_id != id {
        return Err(AuditIssue::new("namespace_handle_id_mismatch").for_namespace(id));
    }
    Ok(result)
}

fn list_user_namespaces(deadline: Instant) -> Observation<Vec<u64>> {
    check_time(deadline)?;
    #[cfg(not(target_arch = "x86_64"))]
    return Err(AuditIssue::new("listns_architecture_not_qualified"));
    #[cfg(target_arch = "x86_64")]
    {
        // x86_64 syscall 470 is pinned by Linux v7.0 syscall_64.tbl and the
        // running host's UAPI. Unknown kernels return ENOSYS -> UNKNOWN.
        let request = NamespaceRequest {
            size: 32,
            spare: 0,
            last_id: 0,
            namespace_type: libc::CLONE_NEWUSER as u32,
            spare2: 0,
            owner_id: 0,
        };
        let mut ids = vec![0u64; MAX_NAMESPACES + 1];
        // One bounded complete request avoids treating a partial page or an
        // inactive pagination boundary as a complete global observation.
        // SAFETY: request and output buffer match the published listns ABI.
        let count = unsafe {
            libc::syscall(
                470 as libc::c_long,
                &request as *const NamespaceRequest,
                ids.as_mut_ptr(),
                ids.len(),
                0u32,
            )
        };
        if count < 0 {
            return Err(AuditIssue::io(
                "global_listns_unavailable_or_denied",
                io::Error::last_os_error(),
            ));
        }
        if count as usize > MAX_NAMESPACES {
            return Err(AuditIssue::new("global_namespace_bound"));
        }
        ids.truncate(count as usize);
        if ids.is_empty()
            || ids.iter().any(|id| *id == 0)
            || ids.windows(2).any(|pair| pair[0] >= pair[1])
        {
            return Err(AuditIssue::new("invalid_global_namespace_order"));
        }
        Ok(ids)
    }
}

fn parent_namespace(handle: &NamespaceHandle) -> Observation<NamespaceHandle> {
    // SAFETY: NS_GET_PARENT returns a newly owned descriptor on success.
    let fd = unsafe { libc::ioctl(handle.file.as_raw_fd(), NS_GET_PARENT) };
    if fd < 0 {
        return Err(AuditIssue::io(
            "namespace_parent_unavailable",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: fd is newly returned, not borrowed.
    NamespaceHandle::from_file(unsafe { File::from_raw_fd(fd) }, libc::CLONE_NEWUSER)
}

fn verify_ancestry(
    first: &NamespaceHandle,
    held: &[NamespaceHandle],
    initial: &NamespaceIdentity,
) -> Observation<()> {
    let mut current = first;
    let mut seen = BTreeSet::new();
    for _ in 0..=32 {
        if &current.identity == initial {
            return Ok(());
        }
        if !seen.insert(current.identity.namespace_id) {
            return Err(AuditIssue::new("namespace_parent_cycle"));
        }
        let parent = parent_namespace(current)?;
        current = held
            .iter()
            .find(|item| item.identity == parent.identity)
            .ok_or_else(|| AuditIssue::new("uncovered_namespace_ancestor"))?;
    }
    Err(AuditIssue::new("namespace_parent_depth_bound"))
}

fn open_at(parent: &File, name: &str, flags: i32) -> Observation<File> {
    let name = CString::new(name).map_err(|_| AuditIssue::new("nul_proc_component"))?;
    // SAFETY: parent is held; CString is terminated; flags never create files.
    let fd = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(AuditIssue::io(
            "held_proc_open_failed",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: openat returned a new owned descriptor.
    Ok(unsafe { File::from_raw_fd(fd) })
}

fn open_proc_root() -> Observation<File> {
    let name = c"/proc";
    // SAFETY: fixed terminated pathname; directory opened without following symlinks.
    let fd = unsafe {
        libc::open(
            name.as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if fd < 0 {
        return Err(AuditIssue::io(
            "proc_open_failed",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: new owned descriptor.
    let file = unsafe { File::from_raw_fd(fd) };
    if fstype(&file)? != PROC_MAGIC {
        return Err(AuditIssue::new("proc_filesystem_mismatch"));
    }
    Ok(file)
}

fn read_at(parent: &File, name: &str, limit: usize) -> Observation<Vec<u8>> {
    let mut file = open_at(parent, name, libc::O_RDONLY)?;
    let mut raw = Vec::new();
    (&mut file)
        .take((limit + 1) as u64)
        .read_to_end(&mut raw)
        .map_err(|error| AuditIssue::io("proc_read_failed", error))?;
    if raw.len() > limit {
        return Err(AuditIssue::new("proc_read_bound"));
    }
    Ok(raw)
}

fn open_task_ns(task: &File, name: &str, kind: i32) -> Observation<NamespaceHandle> {
    let directory = open_at(task, "ns", libc::O_RDONLY | libc::O_DIRECTORY)?;
    let name = CString::new(name).map_err(|_| AuditIssue::new("nul_namespace_name"))?;
    // SAFETY: the only followed link is a named procfs namespace magic link in
    // a retained, identity-checked task directory. This is never an arbitrary path.
    let fd = unsafe {
        libc::openat(
            directory.as_raw_fd(),
            name.as_ptr(),
            libc::O_RDONLY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(AuditIssue::io(
            "task_namespace_open_failed",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: successful openat returned an owned descriptor.
    NamespaceHandle::from_file(unsafe { File::from_raw_fd(fd) }, kind)
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct TaskIdentity {
    pid: i32,
    ppid: i32,
    state: u8,
    starttime: u64,
}

fn task_identity(task: &File) -> Observation<TaskIdentity> {
    parse_stat(&read_at(task, "stat", 8192)?)
}

fn parse_stat(raw: &[u8]) -> Observation<TaskIdentity> {
    let text =
        std::str::from_utf8(raw).map_err(|_| AuditIssue::new("invalid_task_stat_encoding"))?;
    let start = text
        .find('(')
        .ok_or_else(|| AuditIssue::new("invalid_task_stat"))?;
    let finish = text
        .rfind(')')
        .ok_or_else(|| AuditIssue::new("invalid_task_stat"))?;
    if start >= finish {
        return Err(AuditIssue::new("invalid_task_stat"));
    }
    let pid = text[..start]
        .trim()
        .parse::<i32>()
        .map_err(|_| AuditIssue::new("invalid_task_pid"))?;
    let rest: Vec<_> = text[finish + 1..].split_ascii_whitespace().collect();
    if pid <= 0 || rest.len() < 20 || rest[0].len() != 1 {
        return Err(AuditIssue::new("invalid_task_stat_fields"));
    }
    Ok(TaskIdentity {
        pid,
        ppid: rest[1]
            .parse()
            .map_err(|_| AuditIssue::new("invalid_task_ppid"))?,
        state: rest[0].as_bytes()[0],
        starttime: rest[19]
            .parse()
            .map_err(|_| AuditIssue::new("invalid_task_starttime"))?,
    })
}

fn same_task(first: &TaskIdentity, last: &TaskIdentity) -> bool {
    first.pid == last.pid
        && first.ppid == last.ppid
        && first.starttime == last.starttime
        && !matches!(first.state, b'Z' | b'X')
        && !matches!(last.state, b'Z' | b'X')
}

fn thread_ids(task_directory: &File) -> Observation<Vec<i32>> {
    let path = format!("/proc/self/fd/{}", task_directory.as_raw_fd());
    let mut ids = Vec::new();
    for entry in
        std::fs::read_dir(path).map_err(|error| AuditIssue::io("task_enumeration_failed", error))?
    {
        let entry = entry.map_err(|error| AuditIssue::io("task_entry_failed", error))?;
        let name = entry.file_name();
        let text = name
            .to_str()
            .ok_or_else(|| AuditIssue::new("invalid_task_entry"))?;
        let id = text
            .parse::<i32>()
            .map_err(|_| AuditIssue::new("invalid_task_entry"))?;
        if id <= 0 || ids.len() > 1 {
            return Err(AuditIssue::new("collector_not_single_threaded"));
        }
        ids.push(id);
    }
    ids.sort_unstable();
    Ok(ids)
}

fn credentials() -> Observation<Credentials> {
    let mut uids = [0u32; 3];
    let mut gids = [0u32; 3];
    // SAFETY: pointers address distinct initialized uid_t/gid_t slots.
    let [real_uid, effective_uid, saved_uid] = &mut uids;
    let [real_gid, effective_gid, saved_gid] = &mut gids;
    if unsafe { libc::getresuid(real_uid, effective_uid, saved_uid) } != 0
        || unsafe { libc::getresgid(real_gid, effective_gid, saved_gid) } != 0
    {
        return Err(AuditIssue::io(
            "credentials_unavailable",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: zero-sized group query accepts a null pointer.
    let count = unsafe { libc::getgroups(0, std::ptr::null_mut()) };
    if !(0..=4096).contains(&count) {
        return Err(AuditIssue::new("supplementary_group_bound"));
    }
    let mut groups = vec![0u32; count as usize];
    // SAFETY: buffer has exactly count gid_t slots (including zero).
    if unsafe { libc::getgroups(count, groups.as_mut_ptr()) } != count {
        return Err(AuditIssue::io("groups_changed", io::Error::last_os_error()));
    }
    #[repr(C)]
    struct CapHeader {
        version: u32,
        pid: i32,
    }
    #[repr(C)]
    #[derive(Clone, Copy)]
    struct CapData {
        effective: u32,
        permitted: u32,
        inheritable: u32,
    }
    let mut header = CapHeader {
        version: 0x2008_0522,
        pid: 0,
    };
    let mut data = [CapData {
        effective: 0,
        permitted: 0,
        inheritable: 0,
    }; 2];
    // SAFETY: Linux capability ABI version 3 uses a header and two data entries.
    if unsafe { libc::syscall(libc::SYS_capget, &mut header, data.as_mut_ptr()) } != 0 {
        return Err(AuditIssue::io(
            "effective_capabilities_unavailable",
            io::Error::last_os_error(),
        ));
    }
    Ok(Credentials {
        uids,
        gids,
        groups,
        effective_capabilities: u64::from(data[0].effective) | (u64::from(data[1].effective) << 32),
    })
}

impl HostIdentity {
    fn capture() -> Observation<Self> {
        // SAFETY: getpid/gettid do not dereference caller memory.
        let pid = unsafe { libc::getpid() };
        let tid = unsafe { libc::syscall(libc::SYS_gettid) } as i32;
        let proc_root = open_proc_root()?;
        let process = open_at(
            &proc_root,
            &pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let tasks = open_at(&process, "task", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let task = open_at(&tasks, &tid.to_string(), libc::O_RDONLY | libc::O_DIRECTORY)?;
        let identity = task_identity(&task)?;
        if identity.pid != tid {
            return Err(AuditIssue::new("caller_tid_mismatch"));
        }
        let user = open_task_ns(&task, "user", libc::CLONE_NEWUSER)?;
        let pid_namespace = open_task_ns(&task, "pid", libc::CLONE_NEWPID)?;
        let mount = open_task_ns(&task, "mnt", libc::CLONE_NEWNS)?;
        let creds = credentials()?;
        require_sigchld_policy()?;
        let signal_mask = current_signal_mask()?;
        let sys = open_at(&proc_root, "sys", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let fs = open_at(&sys, "fs", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let dumpable_raw = read_at(&fs, "suid_dumpable", 16)?;
        let dumpable_text = std::str::from_utf8(&dumpable_raw)
            .map_err(|_| AuditIssue::new("invalid_suid_dumpable"))?;
        let suid_dumpable = decimal(dumpable_text.trim())?;
        if !matches!(suid_dumpable, 0 | 2) {
            return Err(AuditIssue::new("suid_dumpable_could_expose_collector"));
        }
        // PIDFD_THREAD is O_EXCL in the pinned Linux UAPI. Only the actual
        // calling TID is accepted, while it is necessarily still executing.
        // SAFETY: pidfd_open returns a new owned descriptor for this thread.
        let creator_fd = unsafe { libc::syscall(libc::SYS_pidfd_open, tid, libc::O_EXCL as u32) };
        if creator_fd < 0 {
            return Err(AuditIssue::io(
                "creating_thread_pidfd_unavailable",
                io::Error::last_os_error(),
            ));
        }
        // SAFETY: new descriptor returned by pidfd_open(PIDFD_THREAD).
        let creator_thread_pidfd = unsafe { File::from_raw_fd(creator_fd as RawFd) };
        require_live_pidfd(&creator_thread_pidfd, "creating_thread_not_live")?;
        if creds.uids != [0, 0, 0]
            || creds.gids != [0, 0, 0]
            || creds.effective_capabilities & (CAP_SYS_ADMIN_BIT | CAP_SYS_PTRACE_BIT)
                != (CAP_SYS_ADMIN_BIT | CAP_SYS_PTRACE_BIT)
            || user.identity.inode != INITIAL_USER_INODE
            || pid_namespace.identity.inode != INITIAL_PID_INODE
            || user.identity.device != pid_namespace.identity.device
        {
            return Err(AuditIssue::new(
                "initial_host_namespace_and_privilege_required",
            ));
        }
        let initial_map = vec![MapExtent {
            inside_start: 0,
            host_start: 0,
            count: u32::MAX,
        }];
        if parse_map(&read_at(&task, "uid_map", MAX_MAP_BYTES)?)? != initial_map
            || parse_map(&read_at(&task, "gid_map", MAX_MAP_BYTES)?)? != initial_map
        {
            return Err(AuditIssue::new("initial_identity_maps_required"));
        }
        let init = open_at(&proc_root, "1", libc::O_RDONLY | libc::O_DIRECTORY)?;
        if open_task_ns(&init, "user", libc::CLONE_NEWUSER)?.identity != user.identity
            || open_task_ns(&init, "pid", libc::CLONE_NEWPID)?.identity != pid_namespace.identity
        {
            return Err(AuditIssue::new(
                "proc_does_not_expose_initial_host_pid_namespace",
            ));
        }
        if !same_task(&identity, &task_identity(&task)?) {
            return Err(AuditIssue::new("caller_identity_changed"));
        }
        Ok(Self {
            user,
            pid_namespace,
            mount,
            proc_root,
            pid,
            tid,
            starttime: identity.starttime,
            credentials: creds,
            creator_thread_pidfd,
            signal_mask,
            suid_dumpable,
        })
    }

    fn revalidate(&self) -> Observation<()> {
        let fresh = Self::capture()?;
        if fresh.pid != self.pid
            || fresh.tid != self.tid
            || fresh.starttime != self.starttime
            || fresh.user.identity != self.user.identity
            || fresh.pid_namespace.identity != self.pid_namespace.identity
            || fresh.mount.identity != self.mount.identity
            || fresh.credentials != self.credentials
            || fresh.signal_mask != self.signal_mask
            || fresh.suid_dumpable != self.suid_dumpable
        {
            return Err(AuditIssue::new("parent_identity_or_namespace_changed"));
        }
        require_live_pidfd(&self.creator_thread_pidfd, "creating_thread_not_live")?;
        self.user.revalidate()?;
        self.pid_namespace.revalidate()?;
        self.mount.revalidate()?;
        Ok(())
    }
}

struct WitnessAttempt {
    created: bool,
    result: Observation<NamespaceMaps>,
    terminal: Option<ChildTerminal>,
}

struct OwnedCollector {
    pid: i32,
    namespace_id: u64,
    pidfd: File,
    ready: File,
    release: File,
    preparation_error: Option<AuditIssue>,
    starttime: Option<u64>,
    reaped: bool,
    terminal_unavailable: bool,
}

#[repr(C)]
#[derive(Default)]
struct CloneArguments {
    flags: u64,
    pidfd: u64,
    child_tid: u64,
    parent_tid: u64,
    exit_signal: u64,
    stack: u64,
    stack_size: u64,
    tls: u64,
    set_tid: u64,
    set_tid_size: u64,
    cgroup: u64,
}

const KERNEL_SIGNAL_BYTES: usize = 8;
const BLOCKABLE_SIGNALS: u64 = u64::MAX & !(1 << (libc::SIGKILL - 1)) & !(1 << (libc::SIGSTOP - 1));

fn current_signal_mask() -> Observation<u64> {
    let mut old = 0u64;
    // SAFETY: Linux x86_64 rt_sigprocmask uses an 8-byte kernel signal set.
    // A null new-set pointer reads this calling thread's current mask.
    if unsafe {
        libc::syscall(
            libc::SYS_rt_sigprocmask,
            libc::SIG_SETMASK,
            std::ptr::null::<u64>(),
            &mut old,
            KERNEL_SIGNAL_BYTES,
        )
    } != 0
    {
        return Err(AuditIssue::io(
            "signal_mask_read_failed",
            io::Error::last_os_error(),
        ));
    }
    Ok(old)
}

fn require_sigchld_policy() -> Observation<()> {
    let mut disposition = MaybeUninit::<libc::sigaction>::uninit();
    // SAFETY: null input reads the process disposition into a valid output.
    if unsafe { libc::sigaction(libc::SIGCHLD, std::ptr::null(), disposition.as_mut_ptr()) } != 0 {
        return Err(AuditIssue::io(
            "sigchld_policy_read_failed",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: successful sigaction initialized the output.
    let disposition = unsafe { disposition.assume_init() };
    if disposition.sa_sigaction != libc::SIG_DFL || disposition.sa_flags & libc::SA_NOCLDWAIT != 0 {
        return Err(AuditIssue::new("sigchld_reaper_policy_not_qualified"));
    }
    Ok(())
}

struct BlockedSignals {
    previous: u64,
    active: bool,
}

impl BlockedSignals {
    fn new() -> Observation<Self> {
        let mut previous = 0u64;
        let full = u64::MAX;
        // SAFETY: valid 8-byte kernel masks; only this calling thread changes.
        // Raw syscall also blocks glibc's reserved signals 32/33, which the
        // pthread wrapper intentionally leaves untouched.
        if unsafe {
            libc::syscall(
                libc::SYS_rt_sigprocmask,
                libc::SIG_SETMASK,
                &full,
                &mut previous,
                KERNEL_SIGNAL_BYTES,
            )
        } != 0
        {
            return Err(AuditIssue::io(
                "signal_mask_block_failed",
                io::Error::last_os_error(),
            ));
        }
        Ok(Self {
            previous,
            active: true,
        })
    }

    fn restore(&mut self) -> Observation<()> {
        if !self.active {
            return Ok(());
        }
        // SAFETY: exact previously read kernel mask, same calling thread.
        if unsafe {
            libc::syscall(
                libc::SYS_rt_sigprocmask,
                libc::SIG_SETMASK,
                &self.previous,
                std::ptr::null_mut::<u64>(),
                KERNEL_SIGNAL_BYTES,
            )
        } != 0
        {
            return Err(AuditIssue::io(
                "parent_signal_mask_restore_failed",
                io::Error::last_os_error(),
            ));
        }
        self.active = false;
        if current_signal_mask()? != self.previous {
            return Err(AuditIssue::new("parent_signal_mask_restore_mismatch"));
        }
        Ok(())
    }
}

impl Drop for BlockedSignals {
    fn drop(&mut self) {
        if self.active {
            // SAFETY: best-effort exact restoration on a parent error path;
            // the child only calls _exit and never runs this destructor.
            unsafe {
                libc::syscall(
                    libc::SYS_rt_sigprocmask,
                    libc::SIG_SETMASK,
                    &self.previous,
                    std::ptr::null_mut::<u64>(),
                    KERNEL_SIGNAL_BYTES,
                );
            }
        }
    }
}

fn require_live_pidfd(pidfd: &File, code: &'static str) -> Observation<()> {
    let mut descriptor = libc::pollfd {
        fd: pidfd.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    // SAFETY: one initialized pollfd, zero timeout.
    let result = unsafe { libc::poll(&mut descriptor, 1, 0) };
    if result != 0 {
        return Err(AuditIssue::new(code));
    }
    Ok(())
}

fn pipe_pair() -> Observation<[File; 2]> {
    let mut fds = [-1; 2];
    // SAFETY: valid array of two ints; new descriptors are CLOEXEC.
    if unsafe { libc::pipe2(fds.as_mut_ptr(), libc::O_CLOEXEC) } != 0 {
        return Err(AuditIssue::io(
            "collector_pipe_failed",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: pipe2 initialized two distinct owned descriptors.
    Ok(unsafe { [File::from_raw_fd(fds[0]), File::from_raw_fd(fds[1])] })
}

fn socket_pair() -> Observation<[File; 2]> {
    let mut fds = [-1; 2];
    // SAFETY: two output slots for a private Unix socket pair.
    if unsafe {
        libc::socketpair(
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_CLOEXEC,
            0,
            fds.as_mut_ptr(),
        )
    } != 0
    {
        return Err(AuditIssue::io(
            "collector_control_socket_failed",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: socketpair returned two distinct owned descriptors.
    Ok(unsafe { [File::from_raw_fd(fds[0]), File::from_raw_fd(fds[1])] })
}

fn monotonic_ms() -> Observation<i64> {
    let mut value = MaybeUninit::<libc::timespec>::uninit();
    // SAFETY: clock_gettime initializes value on success.
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, value.as_mut_ptr()) } != 0 {
        return Err(AuditIssue::io(
            "monotonic_clock_failed",
            io::Error::last_os_error(),
        ));
    }
    // SAFETY: initialized by successful clock_gettime.
    let value = unsafe { value.assume_init() };
    Ok(value.tv_sec * 1000 + value.tv_nsec / 1_000_000)
}

// clone3 does not share VM/thread group and does not exec. mm->user_ns thus
// remains the proved initial namespace. Before publishing foreign credentials,
// dumpability is zero; commit_creds may only reset it to the verified host 0/2,
// never SUID_DUMP_USER. Foreign-userns CAP_SYS_PTRACE therefore cannot bypass
// the initial-mm-userns check in __ptrace_may_access / pidfd_getfd.
// Only direct libc/syscall operations and stack storage run after clone.
unsafe fn collector_child(
    namespace_fd: RawFd,
    creator_thread_fd: RawFd,
    ready: RawFd,
    release: RawFd,
    parent: i32,
    until_ms: i64,
) -> ! {
    // SAFETY: all descriptors are pre-clone owned objects; signals remain
    // blocked in this child, which never executes inherited async handlers.
    unsafe {
        if libc::prctl(libc::PR_SET_DUMPABLE, 0 as libc::c_ulong) != 0
            || libc::prctl(libc::PR_GET_DUMPABLE) != 0
        {
            libc::_exit(119);
        }
        let mut creator = libc::pollfd {
            fd: creator_thread_fd,
            events: libc::POLLIN,
            revents: 0,
        };
        if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL as libc::c_ulong) != 0
            || libc::getppid() != parent
            || libc::poll(&mut creator, 1, 0) != 0
        {
            libc::_exit(120);
        }
        if libc::setns(namespace_fd, libc::CLONE_NEWUSER) != 0 {
            libc::_exit(121);
        }
        if libc::prctl(libc::PR_SET_DUMPABLE, 0 as libc::c_ulong) != 0
            || libc::prctl(libc::PR_GET_DUMPABLE) != 0
        {
            libc::_exit(118);
        }
        creator.revents = 0;
        if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL as libc::c_ulong) != 0
            || libc::getppid() != parent
            || libc::poll(&mut creator, 1, 0) != 0
        {
            libc::_exit(122);
        }
        let mut signal = 0i32;
        if libc::prctl(libc::PR_GET_PDEATHSIG, &mut signal) != 0 || signal != libc::SIGKILL {
            libc::_exit(123);
        }
        let ready_byte = b'R';
        if libc::write(ready, (&ready_byte as *const u8).cast(), 1) != 1 {
            libc::_exit(124);
        }
        loop {
            let mut clock = mem::zeroed::<libc::timespec>();
            if libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut clock) != 0 {
                libc::_exit(125);
            }
            let now = clock.tv_sec * 1000 + clock.tv_nsec / 1_000_000;
            if now >= until_ms {
                libc::_exit(126);
            }
            let mut descriptor = libc::pollfd {
                fd: release,
                events: libc::POLLIN,
                revents: 0,
            };
            let timeout = (until_ms - now).min(1000) as i32;
            let result = libc::poll(&mut descriptor, 1, timeout);
            if result < 0 {
                continue;
            }
            if result > 0 {
                let mut byte = 0u8;
                if libc::read(release, (&mut byte as *mut u8).cast(), 1) == 1 && byte == b'X' {
                    libc::_exit(0);
                }
                libc::_exit(127);
            }
        }
    }
}

impl OwnedCollector {
    fn spawn(
        namespace: &NamespaceHandle,
        host: &HostIdentity,
        deadline: Instant,
    ) -> Observation<Self> {
        check_time(deadline)?;
        host.revalidate()?;
        let [ready_read, ready_write] = pipe_pair()?;
        let [release_read, release_write] = socket_pair()?;
        let remaining = deadline.saturating_duration_since(Instant::now());
        let until_ms = monotonic_ms()?
            + i64::try_from(remaining.as_millis())
                .map_err(|_| AuditIssue::new("collector_deadline_overflow"))?;
        let mut pidfd_raw = -1i32;
        let arguments = CloneArguments {
            flags: libc::CLONE_PIDFD as u64,
            pidfd: (&mut pidfd_raw as *mut i32) as u64,
            exit_signal: libc::SIGCHLD as u64,
            ..CloneArguments::default()
        };
        let mut blocked = BlockedSignals::new()?;
        // SAFETY: fork-like clone3 without CLONE_VM/THREAD/FS/FILES; the kernel
        // atomically supplies this child's pidfd, or creates no child on error.
        let pid = unsafe {
            libc::syscall(
                libc::SYS_clone3,
                &arguments as *const CloneArguments,
                mem::size_of::<CloneArguments>(),
            )
        };
        if pid == 0 {
            // SAFETY: close only the child's copies of parent endpoints.
            unsafe {
                libc::close(ready_read.as_raw_fd());
                libc::close(release_write.as_raw_fd());
                collector_child(
                    namespace.file.as_raw_fd(),
                    host.creator_thread_pidfd.as_raw_fd(),
                    ready_write.as_raw_fd(),
                    release_read.as_raw_fd(),
                    host.pid,
                    until_ms,
                );
            }
        }
        let clone_error = if pid < 0 {
            Some(io::Error::last_os_error())
        } else {
            None
        };
        let restore_error = blocked.restore().err();
        if let Some(error) = clone_error {
            return Err(restore_error
                .unwrap_or_else(|| AuditIssue::io("atomic_clone_pidfd_unavailable", error)));
        }
        if pidfd_raw < 0 || pid > i64::from(i32::MAX) as libc::c_long {
            // Broken kernel ABI: no numeric-PID signal/reap fallback. Closing
            // the private control socket makes the bounded child retire.
            return Err(AuditIssue::new("atomic_clone_pidfd_contract_violation"));
        }
        drop(ready_write);
        drop(release_read);
        // SAFETY: successful CLONE_PIDFD supplied a new owned descriptor.
        let pidfd = unsafe { File::from_raw_fd(pidfd_raw) };
        Ok(Self {
            pid: pid as i32,
            namespace_id: namespace.identity.namespace_id,
            pidfd,
            ready: ready_read,
            release: release_write,
            preparation_error: restore_error,
            starttime: None,
            reaped: false,
            terminal_unavailable: false,
        })
    }

    fn live(&self) -> Observation<()> {
        require_live_pidfd(&self.pidfd, "collector_no_longer_live")
    }

    fn wait_ready(&mut self, deadline: Instant) -> Observation<()> {
        if let Some(issue) = self.preparation_error.take() {
            return Err(issue);
        }
        loop {
            check_time(deadline)?;
            self.live()?;
            let mut descriptor = libc::pollfd {
                fd: self.ready.as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            // SAFETY: one valid pollfd slot.
            let result = unsafe { libc::poll(&mut descriptor, 1, 20) };
            if result < 0 {
                if io::Error::last_os_error().raw_os_error() == Some(libc::EINTR) {
                    continue;
                }
                return Err(AuditIssue::io(
                    "collector_ready_poll_failed",
                    io::Error::last_os_error(),
                ));
            }
            if result > 0 {
                let mut byte = [0u8; 1];
                self.ready
                    .read_exact(&mut byte)
                    .map_err(|error| AuditIssue::io("collector_ready_read_failed", error))?;
                if byte != [b'R'] {
                    return Err(AuditIssue::new("collector_ready_protocol"));
                }
                self.live()?;
                return Ok(());
            }
        }
    }

    fn kill_owned(&self) {
        // SAFETY: only the atomic clone3 pidfd is signaled; never a numeric PID.
        unsafe {
            libc::syscall(
                libc::SYS_pidfd_send_signal,
                self.pidfd.as_raw_fd(),
                libc::SIGKILL,
                std::ptr::null::<libc::siginfo_t>(),
                0u32,
            );
        }
    }

    fn wait_owned(&mut self, nonblocking: bool) -> Observation<Option<i32>> {
        let mut information = MaybeUninit::<libc::siginfo_t>::zeroed();
        let flags = libc::WEXITED | if nonblocking { libc::WNOHANG } else { 0 };
        // SAFETY: waitid(P_PIDFD) cannot adopt a different process after PID
        // reuse. Output is a complete siginfo_t, initialized to detect no event.
        let result = unsafe {
            libc::waitid(
                libc::P_PIDFD,
                self.pidfd.as_raw_fd() as u32,
                information.as_mut_ptr(),
                flags,
            )
        };
        if result != 0 {
            let error = io::Error::last_os_error();
            if error.raw_os_error() == Some(libc::EINTR) {
                return Ok(None);
            }
            if error.raw_os_error() == Some(libc::ECHILD) {
                self.terminal_unavailable = true;
            }
            return Err(AuditIssue::io(
                "collector_pidfd_terminal_unavailable",
                error,
            ));
        }
        // SAFETY: waitid success initialized the siginfo_t (or retained zeros).
        let information = unsafe { information.assume_init() };
        // SAFETY: SI_CHLD fields are valid for waitid output.
        let observed_pid = unsafe { information.si_pid() };
        if observed_pid == 0 {
            return Ok(None);
        }
        if observed_pid != self.pid {
            return Err(AuditIssue::new("collector_pidfd_terminal_identity"));
        }
        // SAFETY: SI_CHLD status accessor.
        let status = unsafe { information.si_status() };
        let exit_code = match information.si_code {
            libc::CLD_EXITED => status,
            libc::CLD_KILLED | libc::CLD_DUMPED => -status,
            _ => return Err(AuditIssue::new("collector_nonterminal_wait_event")),
        };
        self.reaped = true;
        Ok(Some(exit_code))
    }

    fn retire(&mut self, deadline: Instant) -> Observation<ChildTerminal> {
        let byte = b'X';
        // SAFETY: private one-byte socket control, no SIGPIPE to the broker.
        let sent = unsafe {
            libc::send(
                self.release.as_raw_fd(),
                (&byte as *const u8).cast(),
                1,
                libc::MSG_NOSIGNAL,
            )
        } == 1;
        if !sent {
            self.kill_owned();
        }
        let exit_code = 'retirement: loop {
            if let Some(code) = self.wait_owned(true)? {
                break code;
            }
            if Instant::now() >= deadline {
                self.kill_owned();
                // Positive retirement is mandatory. This final kernel wait
                // makes the stated deadline cooperative, not hard real-time.
                loop {
                    if let Some(code) = self.wait_owned(false)? {
                        break 'retirement code;
                    }
                }
            } else {
                std::thread::sleep(Duration::from_millis(1));
                continue;
            }
        };
        Ok(ChildTerminal {
            pid: self.pid,
            tid: self.pid,
            starttime: self.starttime,
            namespace_id: self.namespace_id,
            exit_code,
            reaped: true,
        })
    }
}

impl Drop for OwnedCollector {
    fn drop(&mut self) {
        if self.reaped {
            return;
        }
        self.kill_owned();
        if !self.terminal_unavailable {
            loop {
                match self.wait_owned(false) {
                    Ok(Some(_)) | Err(_) => break,
                    Ok(None) => {}
                }
            }
        }
        if !self.reaped {
            // An external reaper / changed SIGCHLD policy can make the exit
            // status unavailable. Kill only our pidfd and observe its death;
            // ECHILD is never promoted to a successful reaping receipt.
            loop {
                let mut descriptor = libc::pollfd {
                    fd: self.pidfd.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                };
                // SAFETY: retained exact child pidfd, no numeric-PID fallback.
                let result = unsafe { libc::poll(&mut descriptor, 1, 100) };
                if result > 0 {
                    break;
                }
                if result < 0 && io::Error::last_os_error().raw_os_error() != Some(libc::EINTR) {
                    break;
                }
            }
        }
    }
}

fn require_collector_signal_mask(task: &File) -> Observation<()> {
    let raw = read_at(task, "status", 16 * 1024)?;
    let text =
        std::str::from_utf8(&raw).map_err(|_| AuditIssue::new("collector_status_encoding"))?;
    let fields: Vec<_> = text
        .lines()
        .filter_map(|line| line.strip_prefix("SigBlk:"))
        .collect();
    if fields.len() != 1 {
        return Err(AuditIssue::new("collector_signal_mask_missing"));
    }
    let value = u64::from_str_radix(fields[0].trim(), 16)
        .map_err(|_| AuditIssue::new("collector_signal_mask_invalid"))?;
    if value != BLOCKABLE_SIGNALS {
        return Err(AuditIssue::new("collector_signal_handlers_not_blocked"));
    }
    Ok(())
}

fn collect_maps(
    namespace: &NamespaceHandle,
    parent: &NamespaceIdentity,
    host: &HostIdentity,
    deadline: Instant,
) -> WitnessAttempt {
    let mut child = match OwnedCollector::spawn(namespace, host, deadline) {
        Ok(child) => child,
        Err(issue) => {
            return WitnessAttempt {
                created: false,
                result: Err(issue),
                terminal: None,
            };
        }
    };
    let observed = (|| {
        child.wait_ready(deadline)?;
        host.revalidate()?;
        let process = open_at(
            &host.proc_root,
            &child.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let task_directory = open_at(&process, "task", libc::O_RDONLY | libc::O_DIRECTORY)?;
        if thread_ids(&task_directory)? != [child.pid] {
            return Err(AuditIssue::new("collector_tid_set_changed"));
        }
        let task = open_at(
            &task_directory,
            &child.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let metadata = task
            .metadata()
            .map_err(|error| AuditIssue::io("collector_proc_fstat_failed", error))?;
        let first = task_identity(&task)?;
        child.starttime = Some(first.starttime);
        if first.pid != child.pid || first.ppid != host.pid || matches!(first.state, b'Z' | b'X') {
            return Err(AuditIssue::new("collector_process_identity_mismatch"));
        }
        let actual = open_task_ns(&task, "user", libc::CLONE_NEWUSER)?;
        if actual.identity != namespace.identity
            || open_task_ns(&task, "pid", libc::CLONE_NEWPID)?.identity
                != host.pid_namespace.identity
            || open_task_ns(&task, "mnt", libc::CLONE_NEWNS)?.identity != host.mount.identity
        {
            return Err(AuditIssue::new("collector_namespace_identity_mismatch"));
        }
        require_collector_signal_mask(&task)?;
        let uid_raw = read_at(&task, "uid_map", MAX_MAP_BYTES)?;
        let gid_raw = read_at(&task, "gid_map", MAX_MAP_BYTES)?;
        let uid_map = parse_map(&uid_raw)?;
        let gid_map = parse_map(&gid_raw)?;
        child.live()?;
        if uid_raw != read_at(&task, "uid_map", MAX_MAP_BYTES)?
            || gid_raw != read_at(&task, "gid_map", MAX_MAP_BYTES)?
            || !same_task(&first, &task_identity(&task)?)
            || thread_ids(&task_directory)? != [child.pid]
            || open_task_ns(&task, "user", libc::CLONE_NEWUSER)?.identity != namespace.identity
        {
            return Err(AuditIssue::new("collector_map_or_identity_changed"));
        }
        let final_metadata = task
            .metadata()
            .map_err(|error| AuditIssue::io("collector_proc_refstat_failed", error))?;
        if metadata.dev() != final_metadata.dev() || metadata.ino() != final_metadata.ino() {
            return Err(AuditIssue::new("collector_proc_descriptor_changed"));
        }
        let named = open_at(
            &task_directory,
            &child.pid.to_string(),
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let named_meta = named
            .metadata()
            .map_err(|error| AuditIssue::io("collector_named_proc_fstat_failed", error))?;
        if metadata.dev() != named_meta.dev()
            || metadata.ino() != named_meta.ino()
            || !same_task(&first, &task_identity(&named)?)
        {
            return Err(AuditIssue::new("collector_named_proc_changed"));
        }
        require_collector_signal_mask(&task)?;
        actual.revalidate()?;
        child.live()?;
        host.revalidate()?;
        Ok(NamespaceMaps {
            namespace: namespace.identity.clone(),
            parent: parent.clone(),
            uid_map,
            gid_map,
            uid_map_bytes: uid_raw.len(),
            gid_map_bytes: gid_raw.len(),
            witness_pid: child.pid,
            witness_tid: child.pid,
            witness_starttime: first.starttime,
            witness_proc_device: metadata.dev(),
            witness_proc_inode: metadata.ino(),
        })
    })();
    match child.retire(deadline) {
        Ok(terminal) => {
            let result = if terminal.exit_code != 0 {
                Err(AuditIssue::new("collector_nonzero_terminal"))
            } else {
                observed
            };
            WitnessAttempt {
                created: true,
                result,
                terminal: Some(terminal),
            }
        }
        Err(issue) => WitnessAttempt {
            created: true,
            result: Err(issue),
            terminal: None,
        },
    }
}

#[cfg(test)]
#[path = "production_namespace_audit_tests.rs"]
mod tests;
