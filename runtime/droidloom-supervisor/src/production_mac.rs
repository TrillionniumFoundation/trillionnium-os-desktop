//! Kernel-backed MAC preflight for the production Android owner.
//!
//! A root installation record selects exact bytes, not qualification. Issuance
//! also requires the running kernel, both actual LSM identities, a stable
//! enforcing SELinux epoch, complete loaded policy and real kernel decisions.
//! Loader input and the expected kernel export are separately sealed identities:
//! the target kernel serializes its policy database and need not reproduce the
//! loader's byte order. Neither identity may be inferred from the other at runtime.
//! This module never loads policy, relabels a file or changes enforcement.

use crate::production_namespace::{
    ExecutedInitGeneration, ExecutedInitWitness, OwnedActivationPeer,
};
use crate::production_selection::ProductionSelection;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;
use std::ffi::{CStr, CString};
use std::fs::File;
use std::io::{self, Read, Write};
use std::marker::PhantomData;
use std::os::fd::{AsFd, AsRawFd, BorrowedFd, FromRawFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::ptr::NonNull;
use std::rc::Rc;
use std::sync::atomic::{Ordering, fence};
use std::time::{Duration, Instant};
use thiserror::Error;

#[path = "production_mac_apexd_task.rs"]
mod apexd_task;
#[path = "production_mac_host_peer.rs"]
mod host_peer;
#[path = "production_mac_host_peer_control.rs"]
mod host_peer_control;
#[path = "production_mac_host_peer_namespace.rs"]
mod host_peer_namespace;
#[path = "production_mac_host_peer_socket.rs"]
mod host_peer_socket;
#[path = "production_mac_host_proc.rs"]
mod host_proc;
pub(crate) use apexd_task::MacApexdTaskWitness;
pub(crate) use host_peer::{HostPeerIssuer, LoaderHostPeerOwner};
pub(crate) use host_peer_socket::{
    BrokerAcceptedStream, BrokerSelectedListener, ManagerSelectedStream, PackageSelectedStream,
};
#[path = "production_mac_capex_requested.rs"]
mod capex_requested;
#[path = "production_mac_private_loop.rs"]
mod private_loop;
pub(crate) use capex_requested::MacRequestedCapexWitness;
#[path = "production_mac_self_attr.rs"]
mod self_attr;
#[path = "production_mac_self_socket.rs"]
mod self_socket;
pub(crate) use private_loop::{MacPrivateLoopWitness, PrivateLoopNode};
#[path = "production_mac_storage_dirs.rs"]
mod storage_dirs;
pub(crate) use storage_dirs::{MacStorageDirectoryWitness, StorageDirectoryRole};
#[path = "production_mac_netns_provider.rs"]
mod netns_provider;

#[path = "production_mac_netns_control.rs"]
mod netns_control;
#[path = "production_selected_socket.rs"]
mod selected_socket;
pub(crate) use netns_provider::SelectedAndroidNetwork;
pub(crate) use selected_socket::{SelectedAndroidSocket, SelectedAndroidSocketBuilder};

const CONTRACT: &str = "/etc/droidloom/host-mac/contract.json";
const POLICY: &str = "/etc/droidloom/host-mac/policy.bin";
const POLICY_EXPORT: &str = "/etc/droidloom/host-mac/policy-export.bin";
const DERIVATION: &str = "/etc/droidloom/host-mac/derivation.json";
const SELINUX_ROOT: &str = "/sys/fs/selinux";
const SELINUX_MAGIC: u64 = 0xf97c_ff8c;
const PROC_MAGIC: u64 = 0x9fa0;
const SYSFS_MAGIC: u64 = 0x6265_6572;
const SECURITYFS_MAGIC: u64 = 0x7363_6673;
const AAFS_MAGIC: u64 = 0x5a3c_69f0;
const MAX_RECORD: usize = 64 * 1024;
const MAX_DERIVATION: usize = 4 * 1024 * 1024;
const MAX_POLICY: usize = 64 * 1024 * 1024;
const BROKER: &str = "u:r:droidloom_broker:s0";
const HOST: &str = "u:r:droidloom_host:s0";
const HOST_FILE: &str = "u:object_r:droidloom_host_file:s0";
const INIT: &str = "u:r:init:s0";
const INIT_EXEC: &str = "u:object_r:init_exec:s0";
const KERNEL: &str = "u:r:kernel:s0";
const AA_BROKER: &[u8] = b"droidloom-production-broker (enforce)\n";
// The target kernel permits only further confinement after NNP. Retain the
// broker profile and stack the Android profile. The initial-namespace label
// vector is sorted by profile hname; both reviewed profiles must enforce.
// This exact source-derived expectation still requires a real VM observation.
const AA_ANDROID: &[u8] = b"droidloom-production-android//&droidloom-production-broker (enforce)\n";
const LOADER: &str = "u:r:droidloom_policy_loader:s0";
const AA_LOADER: &[u8] = b"droidloom-policy-loader (enforce)\n";
const LINKERCONFIG: &str = "u:r:linkerconfig:s0";
const LINKERCONFIG_EXEC: &str = "u:object_r:linkerconfig_exec:s0";

#[path = "production_mac_policy.rs"]
mod policy;
pub(crate) use policy::LoadedPolicyWitness;
#[path = "production_package_mac.rs"]
mod package;
pub(crate) use package::{PackageMacOwner, PackageMacPreparation, PackageMacWitness};
#[path = "production_mac_loader.rs"]
mod loader;
pub(crate) use loader::LoaderMacWitness;

#[path = "production_mac_manager_label.rs"]
mod manager_label;
pub(crate) use manager_label::ManagerLabelPermit;

#[path = "production_mac_listener.rs"]
mod listener;
pub(crate) use listener::MacListenerWitness;

#[path = "production_mac_systemd.rs"]
mod systemd;
pub(crate) use systemd::MacSystemdWitness;

#[derive(Debug, Error)]
pub(crate) enum MacError {
    #[error("production MAC preflight rejected: {0}")]
    Rejected(&'static str),
    #[error("production MAC selection: {0}")]
    Selection(String),
    #[error("production MAC original process owner: {0}")]
    Owner(String),
    #[error("production MAC observation: {0}")]
    Io(#[from] io::Error),
    #[error("production MAC installation record: {0}")]
    Record(#[from] serde_json::Error),
}
type Result<T> = std::result::Result<T, MacError>;
fn require(value: bool, message: &'static str) -> Result<()> {
    if value {
        Ok(())
    } else {
        Err(MacError::Rejected(message))
    }
}

#[derive(Debug, Clone, Copy, Eq, PartialEq, Deserialize)]
enum ContextRouting {
    #[serde(rename = "selinux_typed_host_scoped_android_v1")]
    TypedHostScopedAndroidV1,
}
fn context_routing_field<'de, D: serde::Deserializer<'de>>(
    deserializer: D,
) -> std::result::Result<Option<ContextRouting>, D::Error> {
    // Missing is legacy only. Explicit null is not an implicit schema upgrade.
    ContextRouting::deserialize(deserializer).map(Some)
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct Declaration {
    schema: u32,
    scope: String,
    base_cohort_sha256: String,
    runtime_manifest_sha256: String,
    kernel_release: String,
    kernel_notes_bytes: u64,
    kernel_notes_sha256: String,
    active_lsms: Vec<String>,
    #[serde(default, deserialize_with = "context_routing_field")]
    context_routing: Option<ContextRouting>,
    apparmor_broker_policy_sha256: String,
    apparmor_android_policy_sha256: String,
    apparmor_loader_policy_sha256: String,
    policy_input_bytes: u64,
    policy_input_sha256: String,
    policy_export_bytes: u64,
    policy_export_sha256: String,
    derivation_bytes: u64,
    derivation_sha256: String,
}
fn digest(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn lsm_list(value: &str) -> Result<Vec<&str>> {
    lsm_list_order(value, false)
}
fn lsm_list_order(value: &str, scoped: bool) -> Result<Vec<&str>> {
    let text = value.strip_suffix('\n').unwrap_or(value);
    let entries: Vec<_> = text.split(',').collect();
    let known = [
        "capability",
        "landlock",
        "lockdown",
        "yama",
        "integrity",
        "ima",
        "evm",
        "selinux",
        "apparmor",
        "bpf",
    ];
    require(
        (2..=known.len()).contains(&entries.len()),
        "bounded complete active LSM list",
    )?;
    let mut seen = BTreeSet::new();
    for entry in &entries {
        require(
            known.contains(entry) && seen.insert(*entry),
            "unknown or repeated active LSM",
        )?;
    }
    let selinux = entries.iter().position(|v| *v == "selinux");
    let apparmor = entries.iter().position(|v| *v == "apparmor");
    if scoped {
        require(
            matches!((selinux, apparmor), (Some(s), Some(a)) if a < s),
            "explicit scoped-context contract requires actual AppArmor-first host",
        )?;
    } else {
        require(
            matches!((selinux, apparmor), (Some(s), Some(a)) if s < a),
            "SELinux must precede AppArmor for original Android context APIs",
        )?;
    }
    if let Some(bpf) = entries.iter().position(|v| *v == "bpf") {
        require(
            bpf > apparmor.unwrap().max(selinux.unwrap()),
            "BPF LSM must follow both identity providers",
        )?;
    }
    Ok(entries)
}
impl Declaration {
    fn scoped_contexts(&self) -> Result<bool> {
        match (self.schema, self.scope.as_str(), self.context_routing) {
            (3, "droidloom_linux_android_mac_v3", None) => Ok(false),
            (
                4,
                "droidloom_linux_android_mac_v4",
                Some(ContextRouting::TypedHostScopedAndroidV1),
            ) => Ok(true),
            _ => Err(MacError::Rejected(
                "fixed explicit MAC context-routing schema",
            )),
        }
    }
    fn context_lsms<'a>(&self, value: &'a str) -> Result<Vec<&'a str>> {
        if self.scoped_contexts()? {
            lsm_list_order(value, true)
        } else {
            lsm_list(value)
        }
    }
    fn validate(&self, selection: &ProductionSelection) -> Result<()> {
        self.validate_shape()?;
        require(
            self.base_cohort_sha256 == selection.base_cohort()
                && self.runtime_manifest_sha256 == selection.runtime_manifest(),
            "installed MAC policy is for another selected runtime",
        )?;
        Ok(())
    }
    fn validate_shape(&self) -> Result<()> {
        self.scoped_contexts()?;
        for value in [
            &self.base_cohort_sha256,
            &self.runtime_manifest_sha256,
            &self.kernel_notes_sha256,
            &self.policy_input_sha256,
            &self.policy_export_sha256,
            &self.derivation_sha256,
            &self.apparmor_broker_policy_sha256,
            &self.apparmor_android_policy_sha256,
            &self.apparmor_loader_policy_sha256,
        ] {
            require(digest(value), "lowercase complete installation digest")?;
        }
        require(
            !self.kernel_release.is_empty()
                && self.kernel_release.len() <= 128
                && self
                    .kernel_release
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(&b)),
            "exact bounded kernel release",
        )?;
        require(
            (16..=1024 * 1024).contains(&self.kernel_notes_bytes),
            "bounded running-kernel notes",
        )?;
        require(
            (1024..=MAX_POLICY as u64).contains(&self.policy_input_bytes)
                && (1024..=MAX_POLICY as u64).contains(&self.policy_export_bytes),
            "bounded complete policy input and kernel export",
        )?;
        require(
            (2..=MAX_DERIVATION as u64).contains(&self.derivation_bytes),
            "bounded complete derivation record",
        )?;
        let joined = self.active_lsms.join(",");
        require(
            self.context_lsms(&joined)?.len() == self.active_lsms.len(),
            "one fixed name per declared LSM",
        )
    }
}

// A sealed installation chooses both complete representations for the selected
// kernel and full derivation. It is not a live-policy witness. In particular,
// using a previously exported policy as a new loader input selects a different
// pair; it must not silently reuse the first input's expected export.
fn exact_policy_bytes(bytes: &[u8], expected_bytes: u64, expected_sha256: &str) -> Result<()> {
    require(
        (1024..=MAX_POLICY as u64).contains(&expected_bytes)
            && digest(expected_sha256)
            && bytes.len() as u64 == expected_bytes
            && sha(bytes) == expected_sha256,
        "complete policy representation differs from its selected identity",
    )
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Node {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: i64,
    mtime_ns: i64,
    ctime: i64,
    ctime_ns: i64,
}
impl Node {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            dev: m.dev(),
            ino: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            links: m.nlink(),
            bytes: m.len(),
            mtime: m.mtime(),
            mtime_ns: m.mtime_nsec(),
            ctime: m.ctime(),
            ctime_ns: m.ctime_nsec(),
        })
    }
    fn same_inode(self, other: Self) -> bool {
        (self.dev, self.ino, self.mode & libc::S_IFMT)
            == (other.dev, other.ino, other.mode & libc::S_IFMT)
    }
}
fn open_at(parent: RawFd, name: &CStr, flags: i32) -> Result<File> {
    let fd = unsafe {
        libc::openat(
            parent,
            name.as_ptr(),
            flags | libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    require(
        file.metadata()?.mode() & libc::S_IFMT != libc::S_IFLNK,
        "symlink is not a MAC input",
    )?;
    Ok(file)
}
fn open_absolute(path: &str, flags: i32) -> Result<File> {
    require(
        path.starts_with('/') && !path.ends_with('/'),
        "fixed absolute MAC path",
    )?;
    let mut current = open_at(libc::AT_FDCWD, c"/", libc::O_PATH | libc::O_DIRECTORY)?;
    let pieces: Vec<_> = path[1..].split('/').collect();
    for (index, part) in pieces.iter().enumerate() {
        require(
            !part.is_empty() && *part != "." && *part != "..",
            "normalized fixed MAC path",
        )?;
        let parent = current.metadata()?;
        require(
            parent.uid() == 0 && parent.mode() & 0o022 == 0,
            "MAC parent must be root owned and not writable by other users",
        )?;
        let name = CString::new(*part).map_err(|_| MacError::Rejected("NUL in fixed MAC path"))?;
        current = open_at(
            current.as_raw_fd(),
            &name,
            if index + 1 == pieces.len() {
                flags
            } else {
                libc::O_PATH | libc::O_DIRECTORY
            },
        )?;
    }
    Ok(current)
}
fn kind(file: &File) -> Result<u64> {
    let mut raw = std::mem::MaybeUninit::<libc::statfs>::uninit();
    if unsafe { libc::fstatfs(file.as_raw_fd(), raw.as_mut_ptr()) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(unsafe { raw.assume_init() }.f_type as u64)
}
fn bounded(file: &File, limit: usize) -> Result<Vec<u8>> {
    let mut bytes = Vec::new();
    file.take((limit + 1) as u64).read_to_end(&mut bytes)?;
    require(bytes.len() <= limit, "MAC record exceeds its fixed bound")?;
    Ok(bytes)
}
fn sha(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
struct Sealed {
    path: &'static str,
    file: File,
    node: Node,
}
impl Sealed {
    fn read(path: &'static str, limit: usize) -> Result<(Self, Vec<u8>)> {
        let file = open_absolute(path, libc::O_RDONLY)?;
        let node = Node::of(&file)?;
        require(
            node.mode & libc::S_IFMT == libc::S_IFREG
                && node.uid == 0
                && node.gid == 0
                && node.links == 1
                && node.mode & 0o7222 == 0,
            "MAC installation must be single-link, root owned and sealed",
        )?;
        require(
            node.bytes > 0 && node.bytes <= limit as u64,
            "bounded complete sealed MAC file",
        )?;
        let bytes = bounded(&file, limit)?;
        require(
            bytes.len() as u64 == node.bytes && Node::of(&file)? == node,
            "MAC installation changed during complete read",
        )?;
        let value = Self { path, file, node };
        value.revalidate()?;
        Ok((value, bytes))
    }
    fn revalidate(&self) -> Result<()> {
        require(
            Node::of(&self.file)? == self.node,
            "held MAC installation inode changed",
        )?;
        require(
            Node::of(&open_absolute(self.path, libc::O_RDONLY)?)? == self.node,
            "MAC installation path was replaced",
        )
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Epoch {
    version: u32,
    sequence: u32,
    enforcing: u32,
    policyload: u32,
    deny_unknown: u32,
}
impl Epoch {
    fn valid(self) -> Result<Self> {
        require(
            self.version == 1
                && self.sequence & 1 == 0
                && self.enforcing == 1
                && self.deny_unknown == 1,
            "stable enforcing SELinux status with unknown permissions denied",
        )?;
        // When first opened after policy load, status policyload may be zero.
        // Nonzero compute_av seqno and the complete loaded policy are separate
        // mandatory observations; zero is never interpreted as their success.
        Ok(self)
    }
}
struct StatusMap {
    address: NonNull<u32>,
    length: usize,
    _file: File,
}
impl StatusMap {
    fn open(root: &File) -> Result<Self> {
        let file = open_at(root.as_raw_fd(), c"status", libc::O_RDONLY)?;
        require(
            kind(&file)? == SELINUX_MAGIC,
            "status must come from actual selinuxfs",
        )?;
        let page = unsafe { libc::sysconf(libc::_SC_PAGESIZE) };
        require(
            (4096..=65536).contains(&page),
            "supported kernel status page size",
        )?;
        let raw = unsafe {
            libc::mmap(
                std::ptr::null_mut(),
                page as usize,
                libc::PROT_READ,
                libc::MAP_SHARED,
                file.as_raw_fd(),
                0,
            )
        };
        if raw == libc::MAP_FAILED {
            return Err(io::Error::last_os_error().into());
        }
        let Some(address) = NonNull::new(raw.cast::<u32>()) else {
            unsafe {
                libc::munmap(raw, page as usize);
            }
            return Err(MacError::Rejected("null SELinux status mapping"));
        };
        Ok(Self {
            address,
            length: page as usize,
            _file: file,
        })
    }
    fn read(&self) -> Result<Epoch> {
        let end = Instant::now() + Duration::from_millis(50);
        loop {
            let base = self.address.as_ptr();
            let first = unsafe { base.add(1).read_volatile() };
            fence(Ordering::Acquire);
            if first & 1 == 0 {
                let value = unsafe {
                    Epoch {
                        version: base.read_volatile(),
                        sequence: first,
                        enforcing: base.add(2).read_volatile(),
                        policyload: base.add(3).read_volatile(),
                        deny_unknown: base.add(4).read_volatile(),
                    }
                };
                fence(Ordering::Acquire);
                if unsafe { base.add(1).read_volatile() } == first {
                    return value.valid();
                }
            }
            require(Instant::now() < end, "SELinux status seqlock deadline")?;
            std::hint::spin_loop();
        }
    }
}
impl Drop for StatusMap {
    fn drop(&mut self) {
        unsafe {
            libc::munmap(self.address.as_ptr().cast(), self.length);
        }
    }
}
/// Check the live kernel interfaces needed by the existing v3/v4 MAC provider.
/// A valid platform is only a prerequisite for validating a service role.
///
/// # Errors
/// Returns the actual missing interface, enforcement or registration error.
pub fn check_installed_mac_platform() -> io::Result<()> {
    let root = open_absolute(SELINUX_ROOT, libc::O_PATH | libc::O_DIRECTORY)
        .map_err(|e| io::Error::other(format!("current MAC backend needs an active selinuxfs at {SELINUX_ROOT}: {e}")))?;
    require(kind(&root).map_err(io::Error::other)? == SELINUX_MAGIC,
        "current backend needs a genuine selinuxfs mount").map_err(io::Error::other)?;
    let status = StatusMap::open(&root).map_err(io::Error::other)?;
    let epoch = status.read().map_err(io::Error::other)?;
    let ordered = kernel_text("/sys/kernel/security/lsm", SECURITYFS_MAGIC, 4096).map_err(io::Error::other)?;
    if !ordered.trim_end().split(',').any(|entry| entry == "apparmor")
        || !ordered.trim_end().split(',').any(|entry| entry == "selinux") {
        return Err(io::Error::other("current MAC backend needs both SELinux and AppArmor registered for this boot"));
    }
    if kernel_bytes("/sys/module/apparmor/parameters/enabled", SYSFS_MAGIC, 16).map_err(io::Error::other)? != b"Y\n"
        || epoch != status.read().map_err(io::Error::other)? {
        return Err(io::Error::other("current MAC backend could not observe a stable enforcing platform"));
    }
    Ok(())
}

fn container_manager_role(selinux: &[u8], apparmor: &[u8]) -> bool {
    // This is the dedicated host service role. The installed platform must
    // actually associate its host-system SELinux user, role and domain.
    [
        "u:system_r:droidloom_container_entry_t:s0",
        "system_u:system_r:droidloom_container_entry_t:s0",
    ]
    .iter()
    .any(|context| context_matches(selinux, context))
        && apparmor == AA_BROKER
}

/// Observe the host service's own typed SELinux context and its original
/// enforcing AppArmor profile on the thread that owns the OCI generation.
///
/// # Errors
/// Requires both live enforcement backends and the dedicated host role.
pub fn check_container_manager_role() -> io::Result<()> {
    check_installed_mac_platform()?;
    let proc = own_proc().map_err(io::Error::other)?;
    let selinux = self_attr::selinux_current().map_err(io::Error::other)?;
    let apparmor = proc_attr(&proc, true).map_err(io::Error::other)?;
    if !container_manager_role(&selinux, &apparmor) {
        return Err(io::Error::other(
            "the host manager lacks its dedicated SELinux service role or original enforcing AppArmor broker profile",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod container_manager_role_tests {
    use super::*;
    #[test]
    fn the_host_role_is_distinct_from_android_and_requires_enforcement() {
        assert!(container_manager_role(
            b"u:system_r:droidloom_container_entry_t:s0\0",
            AA_BROKER
        ));
        assert!(container_manager_role(
            b"system_u:system_r:droidloom_container_entry_t:s0",
            AA_BROKER
        ));
        for denied in [
            &b"u:r:kernel:s0"[..],
            &b"u:r:init:s0"[..],
            &b"u:r:droidloom_container_entry:s0"[..],
            &b"u:system_r:init_t:s0"[..],
        ] {
            assert!(!container_manager_role(denied, AA_BROKER));
        }
        assert!(!container_manager_role(
            b"u:system_r:droidloom_container_entry_t:s0",
            b"unconfined\n"
        ));
    }
}

fn kernel_bytes(path: &str, fs: u64, limit: usize) -> Result<Vec<u8>> {
    let file = open_absolute(path, libc::O_RDONLY)?;
    require(
        kind(&file)? == fs,
        "kernel observation came from another filesystem",
    )?;
    bounded(&file, limit)
}
fn kernel_text(path: &str, fs: u64, limit: usize) -> Result<String> {
    String::from_utf8(kernel_bytes(path, fs, limit)?)
        .map_err(|_| MacError::Rejected("non-UTF8 kernel MAC observation"))
}
fn own_proc() -> Result<File> {
    let proc = open_absolute("/proc", libc::O_PATH | libc::O_DIRECTORY)?;
    require(kind(&proc)? == PROC_MAGIC, "actual procfs required")?;
    // One intentional kernel magic-link follow, for the current thread only.
    let fd = unsafe {
        libc::openat(
            proc.as_raw_fd(),
            c"thread-self".as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    require(
        kind(&file)? == PROC_MAGIC,
        "thread proc directory changed filesystem",
    )?;
    Ok(file)
}
fn proc_attr(proc: &File, apparmor: bool) -> Result<Vec<u8>> {
    require(
        kind(proc)? == PROC_MAGIC,
        "held process directory is not procfs",
    )?;
    let attr = open_at(proc.as_raw_fd(), c"attr", libc::O_PATH | libc::O_DIRECTORY)?;
    let parent = if apparmor {
        open_at(
            attr.as_raw_fd(),
            c"apparmor",
            libc::O_PATH | libc::O_DIRECTORY,
        )?
    } else {
        attr
    };
    let file = open_at(parent.as_raw_fd(), c"current", libc::O_RDONLY)?;
    require(
        kind(&file)? == PROC_MAGIC,
        "process attribute came from another filesystem",
    )?;
    bounded(&file, 1024)
}
fn context_matches(value: &[u8], expected: &str) -> bool {
    value == expected.as_bytes()
        || value.strip_suffix(b"\n") == Some(expected.as_bytes())
        || value.strip_suffix(b"\0") == Some(expected.as_bytes())
}
fn socket_identity() -> Result<()> {
    let mut fds = [-1; 2];
    if unsafe {
        libc::socketpair(
            libc::AF_UNIX,
            libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
            0,
            fds.as_mut_ptr(),
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    let pair = unsafe { [File::from_raw_fd(fds[0]), File::from_raw_fd(fds[1])] };
    for file in &pair {
        let mut bytes = [0_u8; 1024];
        let mut length = bytes.len() as libc::socklen_t;
        if unsafe {
            libc::getsockopt(
                file.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERSEC,
                bytes.as_mut_ptr().cast(),
                &mut length,
            )
        } != 0
        {
            return Err(io::Error::last_os_error().into());
        }
        require(
            length as usize <= bytes.len() && context_matches(&bytes[..length as usize], BROKER),
            "socket peer identity is not the actual broker SELinux context",
        )?;
    }
    Ok(())
}

struct AaProfile {
    name: &'static str,
    directory_name: CString,
    directory: File,
    node: Node,
    policy_sha256: String,
}
struct AaPolicy {
    security: File,
    policy: File,
    profiles_directory: File,
    profiles: [AaProfile; 3],
    revision: i64,
}

fn aa_read(parent: &File, name: &CStr, fs: u64, limit: usize) -> Result<Vec<u8>> {
    let file = open_at(parent.as_raw_fd(), name, libc::O_RDONLY)?;
    require(
        kind(&file)? == fs,
        "AppArmor observation crossed filesystems",
    )?;
    bounded(&file, limit)
}
fn aa_revision(security: &File) -> Result<i64> {
    let mut file = open_at(security.as_raw_fd(), c"revision", libc::O_RDONLY)?;
    require(
        kind(&file)? == SECURITYFS_MAGIC,
        "AppArmor revision is not from securityfs",
    )?;
    // The real revision ABI is an event stream: a second read can block or
    // return EAGAIN. A single bounded read obtains its complete current line.
    let mut raw = [0_u8; 64];
    let count = loop {
        match file.read(&mut raw) {
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            other => break other?,
        }
    };
    require(
        count > 1 && count < raw.len() && raw[count - 1] == b'\n',
        "complete current AppArmor revision",
    )?;
    let text = std::str::from_utf8(&raw[..count - 1])
        .map_err(|_| MacError::Rejected("AppArmor revision UTF-8"))?;
    require(
        text.bytes().all(|b| b.is_ascii_digit()),
        "positive exact AppArmor revision",
    )?;
    let value = text
        .parse::<i64>()
        .map_err(|_| MacError::Rejected("AppArmor revision overflow"))?;
    require(value > 0, "loaded AppArmor policy revision required")?;
    Ok(value)
}
fn aa_policy_root(security: &File) -> Result<File> {
    require(
        kind(security)? == SECURITYFS_MAGIC,
        "actual AppArmor securityfs directory",
    )?;
    require(
        aa_read(security, c".ns_level", SECURITYFS_MAGIC, 16)? == b"0\n"
            && aa_read(security, c".ns_stacked", SECURITYFS_MAGIC, 16)? == b"no\n",
        "initial unstacked AppArmor policy namespace required",
    )?;
    // A second, explicitly fixed kernel magic-link operation: AppArmor's
    // policy link selects the calling task's policy namespace. The above
    // observation requires the initial namespace, and the target must be the
    // actual internal AppArmor filesystem, never a caller's pathname.
    let fd = unsafe {
        libc::openat(
            security.as_raw_fd(),
            c"policy".as_ptr(),
            libc::O_RDONLY | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NONBLOCK,
        )
    };
    if fd < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(fd) };
    require(
        kind(&file)? == AAFS_MAGIC,
        "actual AppArmor policy filesystem required",
    )?;
    Ok(file)
}
struct DirectoryStream(NonNull<libc::DIR>);
impl Drop for DirectoryStream {
    fn drop(&mut self) {
        unsafe {
            libc::closedir(self.0.as_ptr());
        }
    }
}
fn aa_profile_names(directory: &File) -> Result<Vec<CString>> {
    require(
        kind(directory)? == AAFS_MAGIC,
        "AppArmor profile directory filesystem",
    )?;
    // Open '.' to obtain an independent enumeration offset on this held dir.
    let fd = open_at(
        directory.as_raw_fd(),
        c".",
        libc::O_RDONLY | libc::O_DIRECTORY,
    )?;
    let duplicate = unsafe { libc::fcntl(fd.as_raw_fd(), libc::F_DUPFD_CLOEXEC, 3) };
    if duplicate < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let raw = unsafe { libc::fdopendir(duplicate) };
    let Some(pointer) = NonNull::new(raw) else {
        let error = io::Error::last_os_error();
        unsafe {
            libc::close(duplicate);
        }
        return Err(error.into());
    };
    let stream = DirectoryStream(pointer);
    let mut names = Vec::new();
    let mut count = 0;
    loop {
        unsafe {
            *libc::__errno_location() = 0;
        }
        let entry = unsafe { libc::readdir(stream.0.as_ptr()) };
        if entry.is_null() {
            let errno = unsafe { *libc::__errno_location() };
            if errno != 0 {
                return Err(io::Error::from_raw_os_error(errno).into());
            }
            break;
        }
        count += 1;
        require(count <= 4096, "bounded AppArmor profile inventory")?;
        let name = unsafe { CStr::from_ptr((*entry).d_name.as_ptr()) };
        let value = name.to_bytes();
        if value.starts_with(b"droidloom-production-broker.")
            || value.starts_with(b"droidloom-production-android.")
            || value.starts_with(b"droidloom-policy-loader.")
        {
            require(
                value.len() <= 255
                    && value
                        .iter()
                        .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(b)),
                "fixed AppArmor profile directory name",
            )?;
            names.push(name.to_owned());
        }
    }
    Ok(names)
}
impl AaProfile {
    fn revalidate(&self, profiles: &File) -> Result<()> {
        let named = open_at(
            profiles.as_raw_fd(),
            &self.directory_name,
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        require(
            kind(&named)? == AAFS_MAGIC
                && self.node.same_inode(Node::of(&named)?)
                && self.node.same_inode(Node::of(&self.directory)?),
            "held AppArmor profile directory changed",
        )?;
        require(
            aa_read(&named, c"name", AAFS_MAGIC, 256)? == format!("{}\n", self.name).as_bytes(),
            "actual AppArmor profile name changed",
        )?;
        require(
            aa_read(&named, c"mode", AAFS_MAGIC, 32)? == b"enforce\n",
            "actual AppArmor profile is not enforcing",
        )?;
        require(
            aa_read(&named, c"sha256", AAFS_MAGIC, 128)?
                == format!("{}\n", self.policy_sha256).as_bytes(),
            "actual loaded AppArmor profile bytes differ",
        )
    }
}
impl AaPolicy {
    fn acquire(declaration: &Declaration) -> Result<Self> {
        let security = open_absolute(
            "/sys/kernel/security/apparmor",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let policy = aa_policy_root(&security)?;
        let revision = aa_revision(&security)?;
        let profiles_directory = open_at(
            policy.as_raw_fd(),
            c"profiles",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        let mut broker = None;
        let mut android = None;
        let mut loader = None;
        for directory_name in aa_profile_names(&profiles_directory)? {
            let directory = open_at(
                profiles_directory.as_raw_fd(),
                &directory_name,
                libc::O_RDONLY | libc::O_DIRECTORY,
            )?;
            require(
                kind(&directory)? == AAFS_MAGIC,
                "AppArmor profile directory must be kernel owned",
            )?;
            let name = aa_read(&directory, c"name", AAFS_MAGIC, 256)?;
            let (slot, expected, hash) = if name == b"droidloom-production-broker\n" {
                (
                    &mut broker,
                    "droidloom-production-broker",
                    &declaration.apparmor_broker_policy_sha256,
                )
            } else if name == b"droidloom-production-android\n" {
                (
                    &mut android,
                    "droidloom-production-android",
                    &declaration.apparmor_android_policy_sha256,
                )
            } else if name == b"droidloom-policy-loader\n" {
                (
                    &mut loader,
                    "droidloom-policy-loader",
                    &declaration.apparmor_loader_policy_sha256,
                )
            } else {
                continue;
            };
            require(slot.is_none(), "ambiguous current AppArmor profile")?;
            let node = Node::of(&directory)?;
            let profile = AaProfile {
                name: expected,
                directory_name,
                directory,
                node,
                policy_sha256: hash.clone(),
            };
            profile.revalidate(&profiles_directory)?;
            *slot = Some(profile);
        }
        let profiles = [
            broker.ok_or(MacError::Rejected(
                "reviewed broker AppArmor profile absent",
            ))?,
            android.ok_or(MacError::Rejected(
                "reviewed Android AppArmor profile absent",
            ))?,
            loader.ok_or(MacError::Rejected(
                "reviewed loader AppArmor profile absent",
            ))?,
        ];
        let value = Self {
            security,
            policy,
            profiles_directory,
            profiles,
            revision,
        };
        value.revalidate()?;
        Ok(value)
    }
    fn revalidate(&self) -> Result<()> {
        require(
            aa_revision(&self.security)? == self.revision,
            "AppArmor policy load generation changed",
        )?;
        let security = open_absolute(
            "/sys/kernel/security/apparmor",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        require(
            Node::of(&security)?.same_inode(Node::of(&self.security)?),
            "AppArmor securityfs mount changed",
        )?;
        let policy = aa_policy_root(&security)?;
        require(
            Node::of(&policy)?.same_inode(Node::of(&self.policy)?),
            "AppArmor policy namespace changed",
        )?;
        let profiles = open_at(
            policy.as_raw_fd(),
            c"profiles",
            libc::O_RDONLY | libc::O_DIRECTORY,
        )?;
        require(
            Node::of(&profiles)?.same_inode(Node::of(&self.profiles_directory)?),
            "AppArmor profiles root changed",
        )?;
        for profile in &self.profiles {
            profile.revalidate(&profiles)?;
        }
        require(
            aa_revision(&self.security)? == self.revision,
            "AppArmor generation changed during revalidation",
        )
    }
}
fn decimal(bytes: &[u8], maximum: u32) -> Result<u32> {
    let text =
        std::str::from_utf8(bytes).map_err(|_| MacError::Rejected("non-UTF8 kernel number"))?;
    let text = text.strip_suffix('\n').unwrap_or(text);
    require(
        !text.is_empty() && text.len() <= 10 && text.bytes().all(|b| b.is_ascii_digit()),
        "one exact kernel number",
    )?;
    let n: u32 = text
        .parse()
        .map_err(|_| MacError::Rejected("kernel number overflow"))?;
    require(
        (1..=maximum).contains(&n),
        "kernel number outside supported range",
    )?;
    Ok(n)
}
fn relative(root: &File, parts: &[&str], flags: i32) -> Result<File> {
    require(!parts.is_empty(), "nonempty fixed selinuxfs path")?;
    let mut directory = root.try_clone()?;
    for (index, name) in parts.iter().enumerate() {
        require(
            !name.is_empty() && name.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_'),
            "fixed selinuxfs component",
        )?;
        let name = CString::new(*name).unwrap();
        directory = open_at(
            directory.as_raw_fd(),
            &name,
            if index + 1 == parts.len() {
                flags
            } else {
                libc::O_PATH | libc::O_DIRECTORY
            },
        )?;
        require(
            kind(&directory)? == SELINUX_MAGIC,
            "selinuxfs path crossed filesystems",
        )?;
    }
    Ok(directory)
}
fn class_number(root: &File, class: &str) -> Result<u32> {
    decimal(
        &bounded(
            &relative(root, &["class", class, "index"], libc::O_RDONLY)?,
            16,
        )?,
        u16::MAX as u32,
    )
}
fn permission_mask(root: &File, class: &str, permissions: &[&str]) -> Result<u32> {
    let mut mask = 0;
    for permission in permissions {
        let file = relative(root, &["class", class, "perms", permission], libc::O_RDONLY)?;
        let bit = decimal(&bounded(&file, 16)?, 32)? - 1;
        require(mask & (1 << bit) == 0, "repeated kernel permission bit")?;
        mask |= 1 << bit;
    }
    require(mask != 0, "nonempty exact access query")?;
    Ok(mask)
}
fn transaction(root: &File, name: &str, payload: &[u8]) -> Result<Vec<u8>> {
    require(
        !payload.is_empty() && payload.len() <= 1024,
        "bounded fixed kernel MAC query",
    )?;
    let mut file = relative(root, &[name], libc::O_RDWR)?;
    // selinuxfs accepts one request per open. Never retry a short-write tail
    // as though that were a continuation of the original transaction.
    let written = loop {
        match file.write(payload) {
            Err(e) if e.kind() == io::ErrorKind::Interrupted => continue,
            other => break other?,
        }
    };
    require(
        written == payload.len(),
        "incomplete kernel MAC query write",
    )?;
    bounded(&file, 1024)
}
#[derive(Debug, Eq, PartialEq)]
struct Decision {
    allowed: u32,
    decided: u32,
    sequence: u32,
    flags: u32,
}
fn parse_decision(bytes: &[u8]) -> Result<Decision> {
    let text =
        std::str::from_utf8(bytes).map_err(|_| MacError::Rejected("non-UTF8 kernel decision"))?;
    require(
        text.len() <= 128 && !text.contains('\0'),
        "bounded complete kernel access decision",
    )?;
    let parts: Vec<_> = text.split_ascii_whitespace().collect();
    require(
        parts.len() == 6,
        "six complete actual kernel decision fields",
    )?;
    let hex = |index: usize| -> Result<u32> {
        let item = parts[index];
        require(
            !item.is_empty() && item.len() <= 8 && item.bytes().all(|b| b.is_ascii_hexdigit()),
            "kernel hexadecimal field",
        )?;
        u32::from_str_radix(item, 16).map_err(|_| MacError::Rejected("kernel hexadecimal overflow"))
    };
    let allowed = hex(0)?;
    let decided = hex(1)?;
    let _auditallow = hex(2)?;
    let _auditdeny = hex(3)?;
    let sequence = decimal(parts[4].as_bytes(), u32::MAX)?;
    let flags = hex(5)?;
    require(
        decided == u32::MAX && flags == 0,
        "partial, permissive or unknown decision flags",
    )?;
    Ok(Decision {
        allowed,
        decided,
        sequence,
        flags,
    })
}
fn access(
    root: &File,
    source: &str,
    target: &str,
    class: &str,
    permissions: &[&str],
    allowed: bool,
    expected_sequence: &mut Option<u32>,
) -> Result<()> {
    let number = class_number(root, class)?;
    let mask = permission_mask(root, class, permissions)?;
    let query = format!("{source} {target} {number}");
    let decision = parse_decision(&transaction(root, "access", query.as_bytes())?)?;
    match *expected_sequence {
        Some(value) => require(
            value == decision.sequence,
            "policy changed between actual decisions",
        )?,
        None => *expected_sequence = Some(decision.sequence),
    }
    require(
        if allowed {
            decision.allowed & mask == mask
        } else {
            decision.allowed & mask == 0
        },
        "actual kernel decision differs from fixed MAC contract",
    )
}
fn transition(root: &File, source: &str, object: &str, expected: &str) -> Result<()> {
    let number = class_number(root, "process")?;
    let query = format!("{source} {object} {number}");
    require(
        context_matches(&transaction(root, "create", query.as_bytes())?, expected),
        "actual automatic exec context differs from reviewed transition",
    )
}
// This verifies only the closed command-role decisions on the actual loaded
// policy and the same AV sequence as the original preflight. It does not
// qualify task-control sockets, the selected linker closure or ExecutionAdmission.
fn required_launch_decisions(root: &File, sequence: &mut Option<u32>) -> Result<()> {
    const READ: &str = "u:r:droidloom_launch_read:s0";
    const START: &str = "u:r:droidloom_launch_start:s0";
    for (role, other, package_find) in [(READ, START, true), (START, READ, false)] {
        let checks: &[(&str, &str, &str, &[&str], bool)] = &[
            (
                "u:r:droidloom_broker:s0",
                role,
                "process",
                &["getattr", "transition", "ptrace", "sigkill"],
                true,
            ),
            (
                "u:r:droidloom_broker:s0",
                role,
                "process2",
                &["nnp_transition", "nosuid_transition"],
                true,
            ),
            (
                "u:r:droidloom_broker:s0",
                role,
                "dir",
                &["getattr", "search", "read", "open"],
                true,
            ),
            (
                "u:r:droidloom_broker:s0",
                role,
                "file",
                &["getattr", "read", "open"],
                true,
            ),
            (
                "u:r:droidloom_broker:s0",
                role,
                "lnk_file",
                &["getattr", "read"],
                true,
            ),
            (
                "u:r:droidloom_host:s0",
                role,
                "process",
                &["getattr", "signull", "signal", "sigkill", "sigstop"],
                true,
            ),
            (
                role,
                "u:object_r:droidloom_query_exec:s0",
                "dir",
                &["getattr", "search"],
                true,
            ),
            (
                role,
                "u:object_r:droidloom_query_exec:s0",
                "file",
                &["getattr", "read", "open", "map", "execute", "entrypoint"],
                true,
            ),
            (role, role, "process", &["fork"], true),
            (
                role,
                "u:object_r:binder_device:s0",
                "chr_file",
                &["open", "read", "write", "getattr", "ioctl", "map"],
                true,
            ),
            (role, "u:r:servicemanager:s0", "binder", &["call"], true),
            ("u:r:servicemanager:s0", role, "binder", &["transfer"], true),
            (
                role,
                "u:r:system_server:s0",
                "binder",
                &["call", "transfer"],
                true,
            ),
            ("u:r:system_server:s0", role, "binder", &["call"], true),
            (role, "u:r:droidloom_broker:s0", "fd", &["use"], true),
            (
                role,
                "u:r:droidloom_broker:s0",
                "fifo_file",
                &["write", "getattr"],
                true,
            ),
            (
                role,
                "u:object_r:null_device:s0",
                "chr_file",
                &["read"],
                true,
            ),
            (
                role,
                "u:object_r:activity_service:s0",
                "service_manager",
                &["find"],
                true,
            ),
            (
                role,
                "u:object_r:package_service:s0",
                "service_manager",
                &["find"],
                package_find,
            ),
            (
                role,
                "u:r:droidloom_host:s0",
                "process",
                &["transition", "dyntransition", "ptrace", "signal", "sigkill"],
                false,
            ),
            (
                role,
                "u:r:droidloom_broker:s0",
                "process",
                &["transition", "dyntransition", "ptrace", "signal", "sigkill"],
                false,
            ),
            (
                role,
                "u:object_r:droidloom_host_file:s0",
                "file",
                &[
                    "read",
                    "write",
                    "append",
                    "map",
                    "execute",
                    "open",
                    "relabelfrom",
                    "relabelto",
                ],
                false,
            ),
            (
                role,
                "u:object_r:droidloom_host_file:s0",
                "dir",
                &[
                    "read",
                    "write",
                    "search",
                    "add_name",
                    "remove_name",
                    "relabelfrom",
                    "relabelto",
                ],
                false,
            ),
            (
                role,
                "u:r:kernel:s0",
                "security",
                &[
                    "load_policy",
                    "setenforce",
                    "setbool",
                    "setsecparam",
                    "setcheckreqprot",
                ],
                false,
            ),
            (
                role,
                "u:r:droidloom_host:s0",
                "unix_stream_socket",
                &["connectto"],
                false,
            ),
            (
                role,
                "u:object_r:droidloom_manager_private_socket:s0",
                "sock_file",
                &["write"],
                false,
            ),
            (
                role,
                "u:object_r:droidloom_query_exec:s0",
                "file",
                &[
                    "write",
                    "append",
                    "create",
                    "relabelfrom",
                    "relabelto",
                    "execute_no_trans",
                ],
                false,
            ),
            (
                role,
                "u:object_r:droidloom_query_exec:s0",
                "dir",
                &[
                    "write",
                    "add_name",
                    "remove_name",
                    "create",
                    "relabelfrom",
                    "relabelto",
                ],
                false,
            ),
            (
                role,
                "u:object_r:system_file:s0",
                "file",
                &["entrypoint"],
                false,
            ),
            (
                role,
                "u:object_r:toolbox_exec:s0",
                "file",
                &["entrypoint"],
                false,
            ),
            (
                role,
                "u:object_r:tmpfs:s0",
                "filesystem",
                &["mount", "remount", "unmount"],
                false,
            ),
            (
                role,
                role,
                "process",
                &[
                    "setexec",
                    "setfscreate",
                    "setsockcreate",
                    "setcurrent",
                    "dyntransition",
                ],
                false,
            ),
            (
                role,
                "u:r:servicemanager:s0",
                "binder",
                &["transfer", "impersonate", "set_context_mgr"],
                false,
            ),
            ("u:r:servicemanager:s0", role, "binder", &["call"], false),
            ("u:r:system_server:s0", role, "binder", &["transfer"], false),
            (
                role,
                "u:object_r:package_service:s0",
                "service_manager",
                &["add", "list"],
                false,
            ),
            (
                role,
                "u:object_r:activity_service:s0",
                "service_manager",
                &["add", "list"],
                false,
            ),
            (
                role,
                "u:r:servicemanager:s0",
                "service_manager",
                &["list"],
                false,
            ),
            (
                role,
                "u:object_r:netd_service:s0",
                "service_manager",
                &["find"],
                false,
            ),
            (
                role,
                "u:object_r:default_prop:s0",
                "property_service",
                &["set"],
                false,
            ),
            (
                role,
                "u:object_r:hwbinder_device:s0",
                "chr_file",
                &["open", "read", "write", "ioctl", "map"],
                false,
            ),
            (
                role,
                "u:object_r:vndbinder_device:s0",
                "chr_file",
                &["open", "read", "write", "ioctl", "map"],
                false,
            ),
            (role, role, "tcp_socket", &["create", "connect"], false),
            (role, role, "udp_socket", &["create", "connect"], false),
            (role, role, "rawip_socket", &["create"], false),
            (role, role, "packet_socket", &["create"], false),
            (role, role, "netlink_route_socket", &["create"], false),
            (
                role,
                role,
                "capability",
                &[
                    "dac_override",
                    "dac_read_search",
                    "fowner",
                    "chown",
                    "setpcap",
                    "sys_admin",
                ],
                false,
            ),
            (
                role,
                "u:object_r:droidloom_nsfs:s0",
                "file",
                &["getattr", "read", "open", "ioctl"],
                false,
            ),
            (
                role,
                other,
                "process",
                &["transition", "dyntransition", "ptrace", "signal", "sigkill"],
                false,
            ),
            (role, other, "binder", &["call", "transfer"], false),
        ];
        for &(source, target, class, permissions, allowed) in checks {
            access(root, source, target, class, permissions, allowed, sequence)?;
        }
    }
    // Launch does not expand the old package-only Query role.
    access(
        root,
        "u:r:droidloom_query:s0",
        "u:object_r:activity_service:s0",
        "service_manager",
        &["find"],
        false,
        sequence,
    )
}
#[path = "production_mac_activation_roots.rs"]
mod activation_roots;

fn required_decisions(root: &File, sequence: &mut Option<u32>) -> Result<()> {
    access(
        root,
        BROKER,
        INIT,
        "process",
        &["transition"],
        true,
        sequence,
    )?;
    access(
        root,
        BROKER,
        INIT,
        "process2",
        &["nnp_transition", "nosuid_transition"],
        true,
        sequence,
    )?;
    access(
        root,
        BROKER,
        INIT_EXEC,
        "file",
        &["read", "open", "map", "execute"],
        true,
        sequence,
    )?;
    access(
        root,
        INIT,
        INIT_EXEC,
        "file",
        &["entrypoint"],
        true,
        sequence,
    )?;
    for target in ["u:r:apexd:s0", "u:r:linkerconfig:s0"] {
        access(
            root,
            INIT,
            target,
            "process",
            &["transition"],
            true,
            sequence,
        )?;
        access(
            root,
            INIT,
            target,
            "process2",
            &["nnp_transition", "nosuid_transition"],
            true,
            sequence,
        )?;
    }
    access(
        root,
        HOST,
        INIT,
        "process",
        &["transition", "dyntransition"],
        false,
        sequence,
    )?;
    for target in [HOST, BROKER] {
        access(
            root,
            INIT,
            target,
            "process",
            &["transition", "dyntransition", "ptrace", "sigkill", "signal"],
            false,
            sequence,
        )?;
    }
    access(
        root,
        INIT,
        HOST_FILE,
        "file",
        &[
            "read",
            "write",
            "append",
            "map",
            "execute",
            "open",
            "relabelfrom",
            "relabelto",
        ],
        false,
        sequence,
    )?;
    access(
        root,
        INIT,
        HOST_FILE,
        "dir",
        &[
            "read",
            "write",
            "search",
            "add_name",
            "remove_name",
            "relabelfrom",
            "relabelto",
        ],
        false,
        sequence,
    )?;
    for source in [INIT, BROKER] {
        access(
            root,
            source,
            KERNEL,
            "security",
            &[
                "load_policy",
                "setenforce",
                "setbool",
                "setsecparam",
                "setcheckreqprot",
            ],
            false,
            sequence,
        )?;
    }
    transition(root, BROKER, INIT_EXEC, INIT)?;
    transition(root, HOST, INIT_EXEC, HOST)?;
    transition(root, BROKER, HOST_FILE, BROKER)?;
    required_launch_decisions(root, sequence)?;
    activation_roots::required(root, sequence)
}

/// Fixed broker role over a complete current loaded-policy observation.
/// No constructor accepts a role string, PID, supplied proc FD or prior result.
pub(crate) struct MacPreflight {
    loaded: LoadedPolicyWitness,
    host_proc: Option<host_proc::HostProcView>,
    self_socket: Option<self_socket::SelfSocketWitness>,
}
impl MacPreflight {
    pub(crate) fn acquire(selection: &ProductionSelection) -> Result<Self> {
        let loaded = LoadedPolicyWitness::acquire(selection)?;
        let (host_proc, self_socket) = if loaded.declaration.scoped_contexts()? {
            (
                Some(host_proc::HostProcView::create(&loaded, selection)?),
                Some(self_socket::SelfSocketWitness::broker(&loaded, selection)?),
            )
        } else {
            (None, None)
        };
        let value = Self {
            loaded,
            host_proc,
            self_socket,
        };
        value.revalidate(selection)?;
        if !value.scoped_contexts() {
            socket_identity()?;
        }
        value.revalidate(selection)?;
        Ok(value)
    }
    pub(crate) fn revalidate(&self, selection: &ProductionSelection) -> Result<()> {
        self.loaded.revalidate(selection)?;
        let scoped = self.loaded.declaration.scoped_contexts()?;
        require(
            scoped == self.host_proc.is_some() && scoped == self.self_socket.is_some(),
            "original MAC route lost a required live provider",
        )?;
        if let Some(proc) = &self.host_proc {
            proc.revalidate(&self.loaded, selection)?;
            require(
                context_matches(&self_attr::selinux_current()?, BROKER),
                "actual typed broker SELinux identity differs",
            )?;
        } else {
            require(
                context_matches(&proc_attr(&self.loaded.own_proc, false)?, BROKER),
                "actual broker SELinux identity differs",
            )?;
        }
        if let Some(socket) = &self.self_socket {
            socket.revalidate(&self.loaded, selection)?;
        }
        require(
            proc_attr(&self.loaded.own_proc, true)? == AA_BROKER,
            "broker AppArmor profile is not the reviewed enforcing profile",
        )?;
        self.loaded.stable_epoch()
    }
    pub(crate) fn loaded_policy(&self) -> &LoadedPolicyWitness {
        &self.loaded
    }
    pub(crate) fn scoped_contexts(&self) -> bool {
        self.host_proc.is_some() && self.self_socket.is_some()
    }
}
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct DescriptorIdentity {
    device: u64,
    inode: u64,
    kind: u32,
}
fn descriptor_identity(fd: BorrowedFd<'_>) -> Result<DescriptorIdentity> {
    let mut metadata: libc::stat = unsafe { std::mem::zeroed() };
    if unsafe { libc::fstat(fd.as_raw_fd(), &mut metadata) } != 0 {
        return Err(io::Error::last_os_error().into());
    }
    Ok(DescriptorIdentity {
        device: metadata.st_dev,
        inode: metadata.st_ino,
        kind: metadata.st_mode & libc::S_IFMT,
    })
}

/// This is an equality binding for a live provider, never an installation
/// certificate. Only successful observations below can issue a witness.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ProviderBinding {
    contract: Node,
    policy: Node,
    policy_export: Node,
    derivation: Node,
    selinux_root: Node,
    broker_proc: Node,
    tid: libc::pid_t,
    epoch: Epoch,
    av_sequence: u32,
    apparmor_revision: i64,
}

fn original_owner<T>(
    value: std::result::Result<T, crate::production_namespace::NamespaceError>,
) -> Result<T> {
    value.map_err(|error| MacError::Owner(error.to_string()))
}

fn process_execution_state(proc: &File, domain: &str) -> Result<()> {
    require(
        context_matches(&proc_attr(proc, false)?, domain),
        "actual original process SELinux domain differs",
    )?;
    process_confinement_state(proc)
}
fn process_confinement_state(proc: &File) -> Result<()> {
    require(
        proc_attr(proc, true)? == AA_ANDROID,
        "actual Android process AppArmor identity is not the reviewed enforcing profile",
    )?;
    let status = open_at(proc.as_raw_fd(), c"status", libc::O_RDONLY)?;
    require(
        kind(&status)? == PROC_MAGIC,
        "actual process status must remain procfs",
    )?;
    let bytes = bounded(&status, 64 * 1024)?;
    let text = std::str::from_utf8(&bytes)
        .map_err(|_| MacError::Rejected("invalid actual process status bytes"))?;
    for (name, expected) in [("NoNewPrivs:", "1"), ("Seccomp:", "2")] {
        let mut values = text.lines().filter_map(|line| line.strip_prefix(name));
        require(
            values.next().is_some_and(|value| value.trim() == expected) && values.next().is_none(),
            "actual Android process lost NNP or its seccomp filter",
        )?;
    }
    Ok(())
}

fn actual_socket_security(socket: BorrowedFd<'_>) -> Result<Vec<u8>> {
    let mut bytes = [0_u8; 1024];
    let mut length = bytes.len() as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERSEC,
            bytes.as_mut_ptr().cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        length > 0 && length as usize <= bytes.len(),
        "bounded actual socket security identity",
    )?;
    Ok(bytes[..length as usize].to_vec())
}

/// Binds the actual, executed original init to the actual MAC provider. It
/// grants no Ready state, namespace operation, command or helper permission.
pub(crate) struct MacInitWitness {
    generation: ExecutedInitGeneration,
    provider: ProviderBinding,
    _same_thread: PhantomData<Rc<()>>,
}

impl LoadedPolicyWitness {
    fn binding(&self) -> ProviderBinding {
        ProviderBinding {
            contract: self.contract.node,
            policy: self.policy.node,
            policy_export: self.policy_export.node,
            derivation: self.derivation.node,
            selinux_root: self.root_node,
            broker_proc: self.own_proc_node,
            tid: self.tid,
            epoch: self.epoch,
            av_sequence: self.av_sequence,
            apparmor_revision: self.apparmor.revision,
        }
    }
}

impl MacPreflight {
    fn binding(&self) -> ProviderBinding {
        self.loaded.binding()
    }

    fn actual_init(&self, init: &ExecutedInitWitness<'_>) -> Result<ExecutedInitGeneration> {
        // The selection is borrowed by the original executed owner itself;
        // a caller cannot substitute cohort hashes or a separate selection.
        self.revalidate(init.selection())?;
        original_owner(init.revalidate())?;
        let generation = original_owner(init.generation())?;
        if let Some(proc) = &self.host_proc {
            require(
                context_matches(&proc.for_init(&self.loaded, init)?, INIT),
                "selected host proc original init domain differs",
            )?;
            process_confinement_state(init.proc_directory())?;
        } else {
            process_execution_state(init.proc_directory(), INIT)?;
        }
        original_owner(init.revalidate())?;
        require(
            original_owner(init.generation())? == generation,
            "original init generation changed",
        )?;
        self.revalidate(init.selection())?;
        Ok(generation)
    }

    pub(crate) fn observe_init(&self, init: &ExecutedInitWitness<'_>) -> Result<MacInitWitness> {
        let value = MacInitWitness {
            generation: self.actual_init(init)?,
            provider: self.binding(),
            _same_thread: PhantomData,
        };
        value.revalidate(self, init)?;
        Ok(value)
    }

    pub(crate) fn observe_linkerconfig_peer(
        &self,
        init: &ExecutedInitWitness<'_>,
        peer: &OwnedActivationPeer<'_>,
    ) -> Result<MacHelperWitness> {
        let init_mac = self.observe_init(init)?;
        original_owner(peer.revalidate())?;
        require(
            peer.generation() == init_mac.generation,
            "helper is owned by another original init",
        )?;
        let value = MacHelperWitness {
            init: init_mac,
            proc: descriptor_identity(peer.proc_directory().as_fd())?,
            pidfd: descriptor_identity(peer.pidfd())?,
            socket: descriptor_identity(peer.socket())?,
        };
        value.revalidate(self, init, peer)?;
        Ok(value)
    }
}

impl MacInitWitness {
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        init: &ExecutedInitWitness<'_>,
    ) -> Result<()> {
        require(
            self.provider == mac.binding(),
            "post-exec witness belongs to another MAC provider",
        )?;
        require(
            self.generation == mac.actual_init(init)?,
            "post-exec witness belongs to another original init",
        )
    }
}

/// Fixed linkerconfig trampoline observation. No numeric-PID, caller-supplied
/// label, serialized record or previous test result can construct this value.
pub(crate) struct MacHelperWitness {
    init: MacInitWitness,
    proc: DescriptorIdentity,
    pidfd: DescriptorIdentity,
    socket: DescriptorIdentity,
}
impl MacHelperWitness {
    pub(crate) fn revalidate(
        &self,
        mac: &MacPreflight,
        init: &ExecutedInitWitness<'_>,
        peer: &OwnedActivationPeer<'_>,
    ) -> Result<()> {
        self.init.revalidate(mac, init)?;
        original_owner(peer.revalidate())?;
        require(
            peer.generation() == self.init.generation,
            "linkerconfig peer owner changed",
        )?;
        require(
            descriptor_identity(peer.proc_directory().as_fd())? == self.proc
                && descriptor_identity(peer.pidfd())? == self.pidfd
                && descriptor_identity(peer.socket())? == self.socket,
            "original helper proc/PIDFD/socket identity changed",
        )?;
        if let Some(proc) = &mac.host_proc {
            require(
                context_matches(&proc.for_helper(&mac.loaded, init, peer)?, LINKERCONFIG),
                "selected host proc original helper domain differs",
            )?;
            process_confinement_state(peer.proc_directory())?;
        } else {
            process_execution_state(peer.proc_directory(), LINKERCONFIG)?;
        }
        require(
            context_matches(&actual_socket_security(peer.socket())?, LINKERCONFIG),
            "actual socket peer is not in the original linkerconfig domain",
        )?;
        original_owner(peer.revalidate())?;
        self.init.revalidate(mac, init)
    }

    /// The caller separately retains the selected original ELF and its full
    /// byte/metadata custody. This checks that exact passed descriptor's
    /// actual label and loaded-policy execute edge before AUTH or GO; it
    /// neither opens an alternate path nor relabels or executes anything.
    pub(crate) fn revalidate_original(
        &self,
        mac: &MacPreflight,
        init: &ExecutedInitWitness<'_>,
        peer: &OwnedActivationPeer<'_>,
        original: &File,
    ) -> Result<()> {
        self.revalidate(mac, init, peer)?;
        let before = Node::of(original)?;
        require(
            before.mode & libc::S_IFMT == libc::S_IFREG,
            "original linkerconfig must be a regular ELF",
        )?;
        let mut label = [0_u8; 1024];
        let count = unsafe {
            libc::fgetxattr(
                original.as_raw_fd(),
                c"security.selinux".as_ptr(),
                label.as_mut_ptr().cast(),
                label.len(),
            )
        };
        if count < 0 {
            return Err(io::Error::last_os_error().into());
        }
        require(
            count > 0
                && count as usize <= label.len()
                && context_matches(&label[..count as usize], LINKERCONFIG_EXEC),
            "held original linkerconfig ELF has another actual SELinux label",
        )?;
        let mut sequence = Some(mac.loaded.av_sequence);
        access(
            &mac.loaded.root,
            LINKERCONFIG,
            LINKERCONFIG_EXEC,
            "file",
            &[
                "getattr",
                "read",
                "open",
                "map",
                "execute",
                "execute_no_trans",
            ],
            true,
            &mut sequence,
        )?;
        transition(
            &mac.loaded.root,
            LINKERCONFIG,
            LINKERCONFIG_EXEC,
            LINKERCONFIG,
        )?;
        require(
            Node::of(original)? == before,
            "held original linkerconfig changed during MAC validation",
        )?;
        self.revalidate(mac, init, peer)
    }
}

fn valid_boot(value: &str) -> bool {
    let value = value.strip_suffix('\n').unwrap_or(value);
    value.len() == 36
        && value.bytes().enumerate().all(|(i, b)| {
            if [8, 13, 18, 23].contains(&i) {
                b == b'-'
            } else {
                b.is_ascii_digit() || (b'a'..=b'f').contains(&b)
            }
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn loader_profile_contract_is_required_without_implicit_schema_upgrade() {
        // This validates untrusted declaration syntax only. No configuration
        // document can construct either actual role or loaded-policy witness.
        let declared = serde_json::json!({
            "schema": 3,
            "scope": "droidloom_linux_android_mac_v3",
            "base_cohort_sha256": "a".repeat(64),
            "runtime_manifest_sha256": "b".repeat(64),
            "kernel_release": "7.0.14-p4ctx3",
            "kernel_notes_bytes": 32,
            "kernel_notes_sha256": "c".repeat(64),
            "active_lsms": ["capability", "selinux", "apparmor", "bpf"],
            "apparmor_broker_policy_sha256": "d".repeat(64),
            "apparmor_android_policy_sha256": "e".repeat(64),
            "apparmor_loader_policy_sha256": "f".repeat(64),
            "policy_input_bytes": 2048,
            "policy_input_sha256": "1".repeat(64),
            "policy_export_bytes": 2048,
            "policy_export_sha256": "2".repeat(64),
            "derivation_bytes": 2,
            "derivation_sha256": "3".repeat(64),
        });
        let parsed: Declaration = serde_json::from_value(declared.clone()).unwrap();
        assert!(parsed.validate_shape().is_ok());
        let mut missing = declared.clone();
        missing
            .as_object_mut()
            .unwrap()
            .remove("apparmor_loader_policy_sha256");
        assert!(serde_json::from_value::<Declaration>(missing).is_err());
        for (key, value) in [
            ("schema", serde_json::json!(2)),
            ("scope", serde_json::json!("droidloom_linux_android_mac_v2")),
            ("apparmor_loader_policy_sha256", serde_json::json!("")),
            (
                "apparmor_loader_policy_sha256",
                serde_json::json!("F".repeat(64)),
            ),
        ] {
            let mut invalid = declared.clone();
            invalid[key] = value;
            let invalid: Declaration = serde_json::from_value(invalid).unwrap();
            assert!(invalid.validate_shape().is_err());
        }
        let mut supplied_role = declared;
        supplied_role["role"] = serde_json::json!("droidloom_policy_loader");
        assert!(serde_json::from_value::<Declaration>(supplied_role).is_err());
    }
    #[test]
    fn separately_selected_policy_representations_reject_role_swap_and_same_size_change() {
        // The real target serializes an extended-permission table in a different
        // order. Requiring input == export rejected that valid representation;
        // accepting either digest for either role would instead lose identity.
        let mut input = vec![0x41; 2048];
        input[42] = 0x42;
        input[43] = 0x43;
        let mut export = input.clone();
        export[23] = 0x01;
        export.swap(42, 43);
        let input_hash = sha(&input);
        let export_hash = sha(&export);
        assert_ne!(input_hash, export_hash);
        assert!(exact_policy_bytes(&input, input.len() as u64, &input_hash).is_ok());
        assert!(exact_policy_bytes(&export, export.len() as u64, &export_hash).is_ok());
        assert!(exact_policy_bytes(&input, export.len() as u64, &export_hash).is_err());
        assert!(exact_policy_bytes(&export, input.len() as u64, &input_hash).is_err());
        let mut changed = export.clone();
        changed[export.len() - 1] ^= 1;
        assert!(exact_policy_bytes(&changed, export.len() as u64, &export_hash).is_err());
        assert!(
            exact_policy_bytes(
                &export[..export.len() - 1],
                export.len() as u64,
                &export_hash
            )
            .is_err()
        );
        assert!(exact_policy_bytes(&export, 0, &export_hash).is_err());
        assert!(
            exact_policy_bytes(&export, export.len() as u64, &export_hash.to_uppercase()).is_err()
        );
    }
    #[test]
    fn kernel_decision_wire_rejects_permissive_partial_or_zero_epoch() {
        let d = parse_decision(b"2 ffffffff 0 ffffffff 17 0").unwrap();
        assert_eq!(d.sequence, 17);
        assert_eq!(d.allowed, 2);
        for value in [
            b"2 ffffffff 0 ffffffff 0 0".as_slice(),
            b"2 ffffffff 0 ffffffff 17 1",
            b"2 ffffffff 0 ffffffff 17 2",
            b"2 2 0 ffffffff 17 0",
            b"2 ffffffff 0 ffffffff 17",
            b"2 ffffffff 0 ffffffff 17 0 trailing",
            b"2 ffffffff 0 ffffffff 17 0\0",
            b"100000000 ffffffff 0 ffffffff 17 0",
        ] {
            assert!(parse_decision(value).is_err());
        }
    }
    #[test]
    fn status_zero_counter_is_not_confused_with_a_loaded_policy_witness() {
        let e = Epoch {
            version: 1,
            sequence: 0,
            enforcing: 1,
            policyload: 0,
            deny_unknown: 1,
        };
        assert_eq!(e.valid().unwrap(), e);
        for invalid in [
            Epoch { sequence: 1, ..e },
            Epoch { enforcing: 0, ..e },
            Epoch {
                deny_unknown: 0,
                ..e
            },
            Epoch { version: 2, ..e },
        ] {
            assert!(invalid.valid().is_err());
        }
        assert_ne!(e, Epoch { sequence: 2, ..e });
        assert_ne!(e, Epoch { policyload: 1, ..e });
    }
    #[test]
    fn original_context_apis_require_selinux_first_and_exact_context() {
        assert!(lsm_list("capability,selinux,apparmor,bpf\n").is_ok());
        for bad in [
            "apparmor,selinux",
            "selinux,selinux,apparmor",
            "selinux,apparmor,smack",
            "bpf,selinux,apparmor",
            "selinux,apparmor\n\n",
            "selinux,apparmor,",
        ] {
            assert!(lsm_list(bad).is_err(), "{bad}");
        }
        for good in [
            BROKER.as_bytes().to_vec(),
            format!("{BROKER}\n").into_bytes(),
            format!("{BROKER}\0").into_bytes(),
        ] {
            assert!(context_matches(&good, BROKER));
        }
        for bad in [
            b"unconfined".as_slice(),
            b"u:r:droidloom_broker:s0\0extra",
            b"u:r:droidloom_broker:s0\n\n",
            b"u:r:droidloom_host:s0",
        ] {
            assert!(!context_matches(bad, BROKER));
        }
    }
    #[test]
    fn fixed_inode_reader_rejects_real_symlink_and_input_growth() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(temp.path().join("real"), b"abc").unwrap();
        std::os::unix::fs::symlink("real", temp.path().join("alias")).unwrap();
        let directory = File::open(temp.path()).unwrap();
        assert!(open_at(directory.as_raw_fd(), c"alias", libc::O_RDONLY).is_err());
        let file = open_at(directory.as_raw_fd(), c"real", libc::O_RDONLY).unwrap();
        assert!(bounded(&file, 2).is_err());
        let before = Node::of(&file).unwrap();
        std::fs::write(temp.path().join("real"), b"changed").unwrap();
        assert_ne!(Node::of(&file).unwrap(), before);
        assert!(valid_boot("97d9600f-e081-465c-9e6e-62651e09806b\n"));
        assert!(!valid_boot(
            "97d9600f-e081-465c-9e6e-62651e09806b\ntrailing"
        ));
    }
    #[test]
    fn scoped_route_requires_explicit_v4_and_keeps_v3_rejections() {
        let base = serde_json::json!({
            "schema":3,"scope":"droidloom_linux_android_mac_v3",
            "base_cohort_sha256":"a".repeat(64),"runtime_manifest_sha256":"b".repeat(64),
            "kernel_release":"6.18.64-p4ctx1","kernel_notes_bytes":32,"kernel_notes_sha256":"c".repeat(64),
            "active_lsms":["capability","selinux","apparmor","bpf"],
            "apparmor_broker_policy_sha256":"d".repeat(64),"apparmor_android_policy_sha256":"e".repeat(64),
            "apparmor_loader_policy_sha256":"f".repeat(64),
            "policy_input_bytes":2048,"policy_input_sha256":"1".repeat(64),
            "policy_export_bytes":2048,"policy_export_sha256":"2".repeat(64),
            "derivation_bytes":1024,"derivation_sha256":"3".repeat(64)
        });
        let old: Declaration = serde_json::from_value(base.clone()).unwrap();
        assert!(old.validate_shape().is_ok());
        assert!(!old.scoped_contexts().unwrap());
        let mut v4 = base.clone();
        v4["schema"] = 4.into();
        v4["scope"] = "droidloom_linux_android_mac_v4".into();
        v4["active_lsms"] = serde_json::json!([
            "landlock",
            "lockdown",
            "yama",
            "integrity",
            "apparmor",
            "selinux",
            "bpf"
        ]);
        assert!(
            serde_json::from_value::<Declaration>(v4.clone())
                .unwrap()
                .validate_shape()
                .is_err()
        );
        v4["context_routing"] = "selinux_typed_host_scoped_android_v1".into();
        let declared: Declaration = serde_json::from_value(v4.clone()).unwrap();
        assert!(declared.validate_shape().is_ok());
        assert!(declared.scoped_contexts().unwrap());
        for changed in ["scope", "schema", "active_lsms"] {
            let mut invalid = v4.clone();
            invalid[changed] = base[changed].clone();
            assert!(
                serde_json::from_value::<Declaration>(invalid)
                    .unwrap()
                    .validate_shape()
                    .is_err()
            );
        }
        let mut downgrade = base.clone();
        downgrade["context_routing"] = v4["context_routing"].clone();
        assert!(
            serde_json::from_value::<Declaration>(downgrade)
                .unwrap()
                .validate_shape()
                .is_err()
        );
        for raw in [
            serde_json::Value::Null,
            serde_json::json!("auto"),
            serde_json::json!("selinux"),
        ] {
            let mut invalid = v4.clone();
            invalid["context_routing"] = raw;
            assert!(serde_json::from_value::<Declaration>(invalid).is_err());
        }
        assert!(lsm_list("apparmor,selinux,bpf").is_err());
        assert!(lsm_list_order("apparmor,bpf,selinux", true).is_err());
        assert!(lsm_list_order("selinux,apparmor,bpf", true).is_err());
        // Shape controls do not construct a loaded or live runtime provider.
    }
}
