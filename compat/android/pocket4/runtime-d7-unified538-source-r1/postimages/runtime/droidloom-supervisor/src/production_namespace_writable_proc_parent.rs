//! Exact parent-side admission for the owned writable-proc preparation.
//! These observations do not grant Android execution or claim an LSM policy.

use super::*;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::{CStr, CString};

const READ_ONLY: [&str; 5] = ["bus", "fs", "irq", "sys", "sysrq-trigger"];
const MASKED: [&str; 10] = [
    "acpi",
    "asound",
    "kcore",
    "keys",
    "latency_stats",
    "timer_list",
    "timer_stats",
    "sched_debug",
    "scsi",
    "interrupts",
];

#[derive(Clone, Debug, Eq, PartialEq)]
pub(super) struct MountRecord {
    pub(super) id: u64,
    pub(super) parent: u64,
    pub(super) device: u64,
    pub(super) root: String,
    pub(super) target: String,
    pub(super) flags: BTreeSet<String>,
    pub(super) filesystem: String,
    pub(super) source: String,
    pub(super) options: String,
}

/// A mount ID identifies one mount; a target may have a retained lower layer.
/// Every layer remains in `records`. `visible` is populated only from statx on
/// the path resolved through this exact held PID 1 root, never row order/ID size.
#[derive(Clone, Debug, Default, Eq, PartialEq)]
pub(super) struct MountInventory {
    pub(super) records: BTreeMap<u64, MountRecord>,
    pub(super) visible: BTreeMap<String, u64>,
}

pub(super) fn mount_records(bytes: &[u8]) -> Result<BTreeMap<u64, MountRecord>> {
    let text = std::str::from_utf8(bytes)
        .map_err(|_| NamespaceError::Rejected("non-text runtime mount inventory"))?;
    if bytes.len() > 65536 || text.is_empty() || !text.ends_with('\n') || text.lines().count() > 256
    {
        return Err(NamespaceError::Rejected(
            "bounded complete runtime mount inventory required",
        ));
    }
    let mut records = BTreeMap::new();
    for line in text.lines() {
        let (left, right) = line
            .split_once(" - ")
            .ok_or(NamespaceError::Rejected("runtime mount separator"))?;
        let left: Vec<_> = left.split_ascii_whitespace().collect();
        let right: Vec<_> = right.split_ascii_whitespace().collect();
        if left.len() != 6
            || right.len() != 3
            || left[3..5]
                .iter()
                .any(|value| !value.starts_with('/') || value.contains('\\'))
        {
            return Err(NamespaceError::Rejected(
                "runtime mount propagation, escape or extra field",
            ));
        }
        if !canonical_target(left[4]) {
            return Err(NamespaceError::Rejected("non-canonical mount target"));
        }
        let number = |value: &str| -> Result<u64> {
            if value.is_empty() || !value.bytes().all(|b| b.is_ascii_digit()) {
                return Err(NamespaceError::Rejected("non-decimal mount identity"));
            }
            value
                .parse()
                .map_err(|_| NamespaceError::Rejected("mount identity overflow"))
        };
        let (major, minor) = left[2]
            .split_once(':')
            .ok_or(NamespaceError::Rejected("mount device"))?;
        let major = u32::try_from(number(major)?)
            .map_err(|_| NamespaceError::Rejected("mount major overflow"))?;
        let minor = u32::try_from(number(minor)?)
            .map_err(|_| NamespaceError::Rejected("mount minor overflow"))?;
        let flags: BTreeSet<_> = left[5].split(',').map(str::to_owned).collect();
        if flags.contains("") || flags.len() != left[5].split(',').count() {
            return Err(NamespaceError::Rejected(
                "duplicate or empty runtime mount flag",
            ));
        }
        let record = MountRecord {
            id: number(left[0])?,
            parent: number(left[1])?,
            device: libc::makedev(major, minor),
            root: left[3].into(),
            target: left[4].into(),
            flags,
            filesystem: right[0].into(),
            source: right[1].into(),
            options: right[2].into(),
        };
        if record.id == 0 || record.parent == 0 || records.insert(record.id, record).is_some() {
            return Err(NamespaceError::Rejected("duplicate or zero mount identity"));
        }
    }
    Ok(records)
}

fn canonical_target(value: &str) -> bool {
    value == "/"
        || (value.starts_with('/')
            && value.len() <= 4096
            && value[1..].split('/').all(|component| {
                !component.is_empty()
                    && component != "."
                    && component != ".."
                    && component
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b"._+-".contains(&b))
            }))
}

pub(super) fn held_mount_id(file: &File) -> Result<u64> {
    // The very same STATX_MNT_ID primitive already used by the admitted mount
    // producer, now applied to a descriptor resolved inside the owned root.
    let mut value: libc::statx = unsafe { std::mem::zeroed() };
    let rc = unsafe {
        libc::syscall(
            libc::SYS_statx,
            file.as_raw_fd(),
            c"".as_ptr(),
            0x1000_u32,
            0x1000_u32,
            &mut value,
        )
    };
    if rc != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if value.stx_mask & 0x1000 == 0 || value.stx_mnt_id == 0 {
        return Err(NamespaceError::Rejected("actual held mount ID unavailable"));
    }
    Ok(value.stx_mnt_id)
}

pub(super) fn target_from_root(root: &File, target: &str) -> Result<File> {
    if !canonical_target(target) {
        return Err(NamespaceError::Rejected("mount target traversal rejected"));
    }
    let mut held = root.try_clone()?;
    if target == "/" {
        return Ok(held);
    }
    for component in target[1..].split('/') {
        if !held.metadata()?.is_dir() {
            return Err(NamespaceError::Rejected(
                "mount target parent is not a directory",
            ));
        }
        let name =
            CString::new(component).map_err(|_| NamespaceError::Rejected("mount target NUL"))?;
        held = optional_path(&held, &name)?
            .ok_or(NamespaceError::Rejected("mount target disappeared"))?;
        if held.metadata()?.mode() & libc::S_IFMT == libc::S_IFLNK {
            return Err(NamespaceError::Rejected("mount target follows a symlink"));
        }
    }
    Ok(held)
}

fn mount_ancestors(records: &BTreeMap<u64, MountRecord>, id: u64) -> Result<Vec<u64>> {
    let mut order = Vec::new();
    let mut seen = BTreeSet::new();
    let mut cursor = id;
    loop {
        let row = records
            .get(&cursor)
            .ok_or(NamespaceError::Rejected("mount ancestor absent"))?;
        if !seen.insert(cursor) {
            return Err(NamespaceError::Rejected("mount ancestry cycle"));
        }
        order.push(cursor);
        if row.parent == cursor && row.target == "/" {
            break;
        }
        match records.get(&row.parent) {
            Some(parent) => {
                if parent.target != "/"
                    && parent.target != row.target
                    && !row
                        .target
                        .strip_prefix(&parent.target)
                        .is_some_and(|rest| rest.starts_with('/'))
                {
                    return Err(NamespaceError::Rejected(
                        "mount outside its recorded ancestor target",
                    ));
                }
                cursor = parent.id;
            }
            None if row.target == "/" => break,
            None => {
                return Err(NamespaceError::Rejected(
                    "non-root mount ancestry incomplete",
                ));
            }
        }
    }
    Ok(order)
}

fn checked_visible(
    records: &BTreeMap<u64, MountRecord>,
    actual: &BTreeMap<String, (u64, u64)>,
) -> Result<BTreeMap<String, u64>> {
    let targets: BTreeSet<_> = records.values().map(|r| r.target.clone()).collect();
    if !targets.contains("/") || actual.keys().cloned().collect::<BTreeSet<_>>() != targets {
        return Err(NamespaceError::Rejected(
            "actual visible mount targets incomplete",
        ));
    }
    let mut visible = BTreeMap::new();
    let mut ancestors = BTreeMap::new();
    for id in records.keys() {
        ancestors.insert(*id, mount_ancestors(records, *id)?);
    }
    for target in targets {
        let (id, device) = actual[&target];
        let record = records.get(&id).ok_or(NamespaceError::Rejected(
            "visible mount ID absent from inventory",
        ))?;
        if record.target != target || record.device != device {
            return Err(NamespaceError::Rejected(
                "visible mount target or filesystem differs",
            ));
        }
        visible.insert(target, id);
    }
    for row in records.values() {
        if visible[&row.target] == row.id {
            continue;
        }
        // A covered mount can be under a covered ancestor: old /dev/pts and
        // new /dev/pts need not be each other's parent. Account for the full
        // ID tree, requiring a genuinely visible covering layer on this path.
        let covered = ancestors[&row.id].iter().any(|id| {
            let parent = &records[id];
            let top = visible[&parent.target];
            top != *id && ancestors[&top].contains(id) && !ancestors[&row.id].contains(&top)
        });
        if !covered {
            return Err(NamespaceError::Rejected(
                "hidden mount has no actual visible covering ancestor",
            ));
        }
    }
    Ok(visible)
}

#[cfg(test)]
fn trace_inventory(stage: &str, bytes: &[u8]) {
    use sha2::Digest;
    let text = std::str::from_utf8(bytes);
    let hex = if text.is_err() {
        Some(bytes.iter().map(|v| format!("{v:02x}")).collect::<String>())
    } else {
        None
    };
    eprintln!(
        "private owned writable-proc mount inventory: {}",
        serde_json::json!({
            "stage": stage, "bytes": bytes.len(), "sha256": format!("{:x}", sha2::Sha256::digest(bytes)),
            "utf8": text.ok(), "non_utf8_hex": hex,
            "source": "held actual owned PID1 proc-directory descriptor"
        })
    );
}

impl MountInventory {
    pub(super) fn observe(child: &TreeChild, stage: &str) -> Result<Self> {
        child.verify()?;
        let raw = read_proc(&child.proc_dir, "mountinfo")?;
        #[cfg(test)]
        trace_inventory(stage, &raw);
        #[cfg(not(test))]
        let _ = stage;
        let records = mount_records(&raw)?;
        let root = held_child_root(child)?;
        let targets: BTreeSet<_> = records.values().map(|r| r.target.clone()).collect();
        let mut held_targets = Vec::new();
        let mut actual = BTreeMap::new();
        for target in targets {
            let file = target_from_root(&root, &target)?;
            let id = held_mount_id(&file)?;
            let device = file.metadata()?.dev();
            actual.insert(target.clone(), (id, device));
            held_targets.push((target, file, id, device));
        }
        let visible = checked_visible(&records, &actual)?;
        // The held FDs prevent ID reuse. Re-resolve every fixed path too; a
        // new covering mount must not hide behind an unchanged earlier FD.
        for (target, file, id, device) in &held_targets {
            let named = target_from_root(&root, target)?;
            if held_mount_id(file)? != *id
                || held_mount_id(&named)? != *id
                || file.metadata()?.dev() != *device
                || Node::of(file)? != Node::of(&named)?
            {
                return Err(NamespaceError::Rejected(
                    "visible mount changed during observation",
                ));
            }
        }
        let after = read_proc(&child.proc_dir, "mountinfo")?;
        if after != raw {
            #[cfg(test)]
            trace_inventory("changed-during-observation", &after);
            return Err(NamespaceError::Rejected(
                "owned mount inventory changed during observation",
            ));
        }
        child.verify()?;
        Ok(Self { records, visible })
    }
    fn at(&self, target: &str) -> Result<&MountRecord> {
        self.visible
            .get(target)
            .and_then(|id| self.records.get(id))
            .ok_or(NamespaceError::Rejected("required visible mount absent"))
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ProtectedNode {
    node: Node,
    kind: u32,
}

#[derive(Clone, Debug)]
pub(super) struct WritableProc {
    before: MountInventory,
    readonly: BTreeMap<String, ProtectedNode>,
    masked: BTreeMap<String, ProtectedNode>,
    pub(super) after: MountInventory,
    mask_file: Option<Node>,
    mask_directory: Option<Node>,
}

fn optional_path(parent: &File, name: &CStr) -> Result<Option<File>> {
    let raw = unsafe {
        libc::openat(
            parent.as_raw_fd(),
            name.as_ptr(),
            libc::O_PATH | libc::O_CLOEXEC | libc::O_NOFOLLOW,
        )
    };
    if raw < 0 {
        let error = io::Error::last_os_error();
        if error.raw_os_error() == Some(libc::ENOENT) {
            return Ok(None);
        }
        return Err(error.into());
    }
    Ok(Some(unsafe { File::from_raw_fd(raw) }))
}

fn fixed_nodes(
    proc: &File,
    names: &[&str],
    device: u64,
) -> Result<BTreeMap<String, ProtectedNode>> {
    let mut nodes = BTreeMap::new();
    for name in names {
        let component =
            CString::new(*name).map_err(|_| NamespaceError::Rejected("fixed proc component"))?;
        if let Some(file) = optional_path(proc, &component)? {
            let m = file.metadata()?;
            let kind = m.mode() & libc::S_IFMT;
            if m.dev() != device || ![libc::S_IFDIR, libc::S_IFREG].contains(&kind) {
                return Err(NamespaceError::Rejected(
                    "global proc target type or filesystem differs",
                ));
            }
            nodes.insert(
                (*name).into(),
                ProtectedNode {
                    node: Node::of(&file)?,
                    kind,
                },
            );
        }
    }
    Ok(nodes)
}

fn flags(flags: &BTreeSet<String>, required: &[&str], forbidden: &[&str]) -> bool {
    required.iter().all(|x| flags.contains(*x)) && forbidden.iter().all(|x| !flags.contains(*x))
}

fn changed_proc_root(before: &MountRecord, after: &MountRecord) -> bool {
    let mut expected = before.clone();
    if !expected.flags.remove("ro") || !expected.flags.insert("rw".into()) {
        return false;
    }
    &expected == after && flags(&after.flags, &["rw", "nosuid", "nodev", "noexec"], &["ro"])
}

fn verify_old_layers(before: &MountInventory, after: &MountInventory) -> Result<()> {
    let original_proc = before.at("/proc")?;
    for (id, original) in &before.records {
        let current = after
            .records
            .get(id)
            .ok_or(NamespaceError::Rejected("an original mount disappeared"))?;
        if if *id == original_proc.id {
            !changed_proc_root(original, current)
        } else {
            original != current
        } {
            return Err(NamespaceError::Rejected("an original mount layer changed"));
        }
    }
    for (target, id) in &before.visible {
        if after.visible.get(target) != Some(id) {
            return Err(NamespaceError::Rejected(
                "an existing visible mount was covered or replaced",
            ));
        }
    }
    Ok(())
}

impl WritableProc {
    fn before(child: &TreeChild) -> Result<Self> {
        let root = held_child_root(child)?;
        let proc = root_subdirectory(&root, c"proc")?;
        let before = MountInventory::observe(child, "before-writable-command")?;
        let original = before.at("/proc")?;
        if original.root != "/"
            || original.filesystem != "proc"
            || original.device != proc.metadata()?.dev()
            || !flags(
                &original.flags,
                &["ro", "nosuid", "nodev", "noexec"],
                &["rw"],
            )
        {
            return Err(NamespaceError::Rejected(
                "read-only original private proc required",
            ));
        }
        let readonly = fixed_nodes(&proc, &READ_ONLY, original.device)?;
        let masked = fixed_nodes(&proc, &MASKED, original.device)?;
        Ok(Self {
            before,
            readonly,
            masked,
            after: MountInventory::default(),
            mask_file: None,
            mask_directory: None,
        })
    }

    pub(super) fn verify(&mut self, child: &TreeChild) -> Result<()> {
        child.verify()?;
        let root = held_child_root(child)?;
        let proc = root_subdirectory(&root, c"proc")?;
        let metadata = root_subdirectory(&root, c"metadata")?;
        let current = MountInventory::observe(child, "after-writable-ready")?;
        let original = self.before.at("/proc")?;
        let changed = current.at("/proc")?;
        if !changed_proc_root(original, changed) || Node::of(&proc)?.device != original.device {
            return Err(NamespaceError::Rejected(
                "only proc per-mount read-only flag may change",
            ));
        }
        verify_process_statfs(&proc, 0x9fa0, 2 | 4 | 8, 1)?;
        let mask_file = optional_path(&metadata, c"proc-mask-file")?
            .ok_or(NamespaceError::Rejected("private empty mask file absent"))?;
        let mask_dir = optional_path(&metadata, c"proc-mask-directory")?.ok_or(
            NamespaceError::Rejected("private empty mask directory absent"),
        )?;
        for (file, kind) in [(&mask_file, libc::S_IFREG), (&mask_dir, libc::S_IFDIR)] {
            let m = file.metadata()?;
            if m.mode() != kind
                || m.dev() != metadata.metadata()?.dev()
                || m.uid() != child.uids.start
                || m.gid() != child.gids.start
                || (kind == libc::S_IFREG && (m.len() != 0 || m.nlink() != 1))
            {
                return Err(NamespaceError::Rejected("private zero mask inode differs"));
            }
        }
        let file_node = Node::of(&mask_file)?;
        let dir_node = Node::of(&mask_dir)?;
        if self.mask_file.is_some_and(|prior| prior != file_node)
            || self.mask_directory.is_some_and(|prior| prior != dir_node)
        {
            return Err(NamespaceError::Rejected("private masks replaced"));
        }
        // The current fixed mask directory must remain empty. Reopen the exact
        // held inode for bounded enumeration, never a supplied external path.
        let entries = std::fs::read_dir(format!("/proc/self/fd/{}", mask_dir.as_raw_fd()))?;
        if entries.take(1).next().is_some() {
            return Err(NamespaceError::Rejected(
                "private mask directory is not empty",
            ));
        }
        // Every old mount, including a covered immutable lower layer, must
        // remain byte-for-byte identical except the actual visible proc's RO.
        verify_old_layers(&self.before, &current)?;
        let mut targets: BTreeSet<String> = self.before.visible.keys().cloned().collect();
        let mut expected_new = BTreeSet::new();
        for (name, node) in &self.readonly {
            let target = format!("/proc/{name}");
            targets.insert(target.clone());
            let record = current.at(&target)?;
            if self.before.records.contains_key(&record.id) || !expected_new.insert(record.id) {
                return Err(NamespaceError::Rejected(
                    "readonly projection must be one new mount",
                ));
            }
            if record.parent != original.id
                || record.device != original.device
                || record.root != format!("/{name}")
                || record.filesystem != original.filesystem
                || record.source != original.source
                || record.options != original.options
                || !flags(&record.flags, &["ro", "nosuid", "nodev", "noexec"], &["rw"])
            {
                return Err(NamespaceError::Rejected("global readonly mount differs"));
            }
            let leaf = optional_path(&proc, &CString::new(name.as_str()).unwrap())?
                .ok_or(NamespaceError::Rejected("global readonly inode absent"))?;
            if Node::of(&leaf)? != node.node || leaf.metadata()?.mode() & libc::S_IFMT != node.kind
            {
                return Err(NamespaceError::Rejected("global readonly inode differs"));
            }
            verify_process_statfs(&leaf, 0x9fa0, 1 | 2 | 4 | 8, 0)?;
        }
        let meta_record = self.before.at("/metadata")?;
        for (name, node) in &self.masked {
            let target = format!("/proc/{name}");
            targets.insert(target.clone());
            let record = current.at(&target)?;
            if self.before.records.contains_key(&record.id) || !expected_new.insert(record.id) {
                return Err(NamespaceError::Rejected(
                    "mask projection must be one new mount",
                ));
            }
            let (expected, mask_name) = if node.kind == libc::S_IFREG {
                (file_node, "/proc-mask-file")
            } else {
                (dir_node, "/proc-mask-directory")
            };
            if record.parent != original.id
                || record.device != expected.device
                || record.root != mask_name
                || record.filesystem != "tmpfs"
                || record.source != meta_record.source
                || record.options != meta_record.options
                || !flags(&record.flags, &["ro", "nosuid", "nodev", "noexec"], &["rw"])
            {
                return Err(NamespaceError::Rejected("private masked mount differs"));
            }
            let leaf = optional_path(&proc, &CString::new(name.as_str()).unwrap())?
                .ok_or(NamespaceError::Rejected("private masked inode absent"))?;
            if Node::of(&leaf)? != expected || leaf.metadata()?.mode() != node.kind {
                return Err(NamespaceError::Rejected("private masked inode differs"));
            }
            verify_process_statfs(&leaf, 0x0102_1994, 1 | 2 | 4 | 8, 0)?;
        }
        let actual_new: BTreeSet<_> = current
            .records
            .keys()
            .filter(|id| !self.before.records.contains_key(id))
            .copied()
            .collect();
        if current.visible.keys().cloned().collect::<BTreeSet<_>>() != targets
            || actual_new != expected_new
        {
            return Err(NamespaceError::Rejected(
                "unexpected writable-proc mount target",
            ));
        }
        if !self.after.records.is_empty() && self.after != current {
            return Err(NamespaceError::Rejected(
                "writable-proc mount identity changed",
            ));
        }
        self.mask_file = Some(file_node);
        self.mask_directory = Some(dir_node);
        self.after = current;
        // The existing process namespace/owner checks remain required; mount
        // projection success is not a substitute for exact held PIDNS/userns.
        let one = root_subdirectory(&proc, c"1")?;
        let ns = optional_path(&one, c"ns")?
            .ok_or(NamespaceError::Rejected("PID1 namespace directory absent"))?;
        for (name, kind, expected) in [
            (c"pid", libc::CLONE_NEWPID, child.pid_namespace()),
            (c"user", libc::CLONE_NEWUSER, &child.namespaces.userns),
        ] {
            let held = fixed_namespace_link(&ns, name, kind)?;
            if Node::of(&held)? != Node::of(expected)? {
                return Err(NamespaceError::Rejected(
                    "writable proc exposes a foreign namespace",
                ));
            }
        }
        child.verify()
    }
}

impl IsolatedNamespaces {
    pub(crate) fn prepare_writable_proc(mut self) -> Result<Self> {
        self.verify_live_admission()?;
        if self.writable_proc.is_some() || self.binder.is_none() {
            return Err(NamespaceError::Rejected(
                "writable proc requires one private Binder barrier",
            ));
        }
        let child = self
            .init
            .as_ref()
            .ok_or(NamespaceError::Rejected("PID1 absent"))?;
        child.verify_empty_root_mounts_with_binder(
            self.base_devices
                .ok_or(NamespaceError::Rejected("base absent"))?,
            self.device_node,
            self.process_filesystems,
            self.binder,
        )?;
        let mut observation = WritableProc::before(child)?;
        send_packet(
            child.control.as_raw_fd(),
            &Packet::new(child.nonce, Phase::PrepareWritableProc, 0, child.parent_pid),
        )?;
        child.receive_phase(Phase::WritableProcReady)?;
        observation.verify(child)?;
        self.writable_proc = Some(observation);
        self.verify_live_admission()?;
        Ok(self)
    }
}

#[cfg(test)]
pub(super) fn receive_xattr_observation(child: &TreeChild) -> Result<i32> {
    // Both records share the original three-second protocol budget. The
    // metadata record never satisfies the original success barrier.
    let deadline = Instant::now() + PROTOCOL_TIMEOUT;
    wait_readable_until(&child.control, &child.pidfd, deadline)?;
    let dumpable = receive_dumpability_record(
        child.control.as_raw_fd(),
        child.nonce,
        child.identity.pid,
        child.uids.start,
        child.gids.start,
    )?;
    eprintln!(
        "private owned writable-proc dumpability: {}",
        serde_json::json!({
            "source": "authenticated fixed raw PID1 PR_GET_DUMPABLE",
            "dumpable": dumpable, "credentials_changed": false,
            "dumpability_changed": false, "authority_issued": false
        })
    );
    wait_readable_until(&child.control, &child.pidfd, deadline)?;
    let observed = receive_xattr_record(
        child.control.as_raw_fd(),
        child.nonce,
        child.identity.pid,
        child.uids.start,
        child.gids.start,
        || child.verify(),
    )?;
    if Instant::now() >= deadline {
        return Err(
            io::Error::new(io::ErrorKind::TimedOut, "private proc observation deadline").into(),
        );
    }
    Ok(observed)
}

#[cfg(test)]
fn receive_xattr_record(
    control: RawFd,
    nonce: [u8; 16],
    host_pid: u32,
    uid: u32,
    gid: u32,
    verify_live: impl FnOnce() -> Result<()>,
) -> Result<i32> {
    let packet = authenticated_private_record(control, nonce, host_pid, uid, gid)?;
    if packet.phase != Phase::WritableProcChecked as u32 || !(0..4096).contains(&packet.errno) {
        return Err(NamespaceError::Rejected(
            "fixed xattr observation phase or errno",
        ));
    }
    // Success still requires the exact held PIDFD/proc/start/namespace checks.
    verify_live()?;
    Ok(packet.errno)
}

#[cfg(test)]
fn authenticated_private_record(
    control: RawFd,
    nonce: [u8; 16],
    host_pid: u32,
    uid: u32,
    gid: u32,
) -> Result<Packet> {
    // The shared receiver requires exactly one kernel credential record and
    // closes/rejects every received descriptor. Authenticate before decoding a
    // failure, including when its exact owned sender has already exited.
    let (packet, creds) = receive_packet(control)?;
    if !packet.matches(nonce, 1)
        || creds.pid != host_pid as i32
        || creds.uid != uid
        || creds.gid != gid
    {
        return Err(NamespaceError::Rejected(
            "fixed xattr observation authentication",
        ));
    }
    if packet.phase == Phase::Failed as u32 {
        let (stage, line, errno) = child::writable_proc_private_failure(packet.errno).ok_or(
            NamespaceError::Rejected("fixed writable-proc failure encoding"),
        )?;
        // This is a test-only error, never a successful observation or an
        // authority grant. A later live-PID check must not erase the consumed
        // authenticated stage/line/errno. Actual retirement remains mandatory.
        return Err(io::Error::other(format!(
            "authenticated private writable-proc Failed: stage={stage} source-line={line} errno={errno}"
        )).into());
    }
    Ok(packet)
}

#[cfg(test)]
fn receive_dumpability_record(
    control: RawFd,
    nonce: [u8; 16],
    host_pid: u32,
    uid: u32,
    gid: u32,
) -> Result<i32> {
    let packet = authenticated_private_record(control, nonce, host_pid, uid, gid)?;
    if packet.phase != Phase::PrivateProcDumpability as u32 || !(0..=2).contains(&packet.errno) {
        return Err(NamespaceError::Rejected(
            "fixed proc dumpability observation",
        ));
    }
    Ok(packet.errno)
}

#[cfg(test)]
pub(super) fn private_status_fields(
    raw: &[u8],
    uid: u32,
    gid: u32,
) -> Result<BTreeMap<String, String>> {
    const FIELDS: [&str; 10] = [
        "Uid",
        "Gid",
        "Groups",
        "CapInh",
        "CapPrm",
        "CapEff",
        "CapBnd",
        "CapAmb",
        "NoNewPrivs",
        "Seccomp",
    ];
    let text =
        std::str::from_utf8(raw).map_err(|_| NamespaceError::Rejected("proc status encoding"))?;
    if raw.len() > 65536 || text.is_empty() || !text.ends_with('\n') {
        return Err(NamespaceError::Rejected(
            "bounded complete proc status required",
        ));
    }
    let mut fields = BTreeMap::new();
    for line in text.lines() {
        let Some((name, body)) = line.split_once(':') else {
            continue;
        };
        if FIELDS.contains(&name)
            && fields
                .insert(name.to_owned(), body.trim().to_owned())
                .is_some()
        {
            return Err(NamespaceError::Rejected(
                "duplicate proc status authority field",
            ));
        }
    }
    if fields.len() != FIELDS.len() {
        return Err(NamespaceError::Rejected(
            "incomplete proc status authority fields",
        ));
    }
    for (name, expected) in [("Uid", uid), ("Gid", gid)] {
        let values = fields[name]
            .split_ascii_whitespace()
            .map(|x| x.parse::<u32>())
            .collect::<std::result::Result<Vec<_>, _>>()
            .map_err(|_| NamespaceError::Rejected("proc credential numeric encoding"))?;
        if values != [expected; 4] {
            return Err(NamespaceError::Rejected("owned proc credential differs"));
        }
    }
    if !fields["Groups"].is_empty()
        || fields["NoNewPrivs"] != "1"
        || !["0", "1", "2"].contains(&fields["Seccomp"].as_str())
    {
        return Err(NamespaceError::Rejected(
            "owned proc groups or execution metadata differs",
        ));
    }
    for name in ["CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb"] {
        if fields[name].len() != 16 || !fields[name].bytes().all(|b| b.is_ascii_hexdigit()) {
            return Err(NamespaceError::Rejected("proc capability numeric encoding"));
        }
    }
    Ok(fields)
}

#[cfg(test)]
pub(super) fn trace_private_proc_authority(child: &TreeChild) -> Result<()> {
    child.verify()?;
    let before = private_status_fields(
        &read_proc(&child.proc_dir, "status")?,
        child.uids.start,
        child.gids.start,
    )?;
    let root = held_child_root(child)?;
    let proc = target_from_root(&root, "/proc")?;
    verify_process_statfs(&proc, 0x9fa0, 2 | 4 | 8, 1)?;
    let one = target_from_root(&root, "/proc/1")?;
    let ns = optional_path(&one, c"ns")?.ok_or(NamespaceError::Rejected("owned PID1 ns absent"))?;
    for (name, kind, expected) in [
        (c"pid", libc::CLONE_NEWPID, child.pid_namespace()),
        (c"user", libc::CLONE_NEWUSER, &child.namespaces.userns),
    ] {
        let actual = fixed_namespace_link(&ns, name, kind)?;
        if Node::of(&actual)? != Node::of(expected)? {
            return Err(NamespaceError::Rejected(
                "diagnostic proc exposes foreign namespace",
            ));
        }
    }
    // This is an O_PATH-only handle: no score body is read or written here.
    let score = target_from_root(&root, "/proc/1/oom_score_adj")?;
    let m = score.metadata()?;
    let mount_id = held_mount_id(&score)?;
    let snapshot = (m.dev(), m.ino(), m.mode(), m.uid(), m.gid(), m.nlink());
    if m.mode() != libc::S_IFREG | 0o644
        || m.dev() != proc.metadata()?.dev()
        || mount_id != held_mount_id(&proc)?
    {
        return Err(NamespaceError::Rejected(
            "fixed owned score inode or mount differs",
        ));
    }
    let named = target_from_root(&root, "/proc/1/oom_score_adj")?;
    let now = named.metadata()?;
    if snapshot
        != (
            now.dev(),
            now.ino(),
            now.mode(),
            now.uid(),
            now.gid(),
            now.nlink(),
        )
        || mount_id != held_mount_id(&named)?
        || before
            != private_status_fields(
                &read_proc(&child.proc_dir, "status")?,
                child.uids.start,
                child.gids.start,
            )?
    {
        return Err(NamespaceError::Rejected(
            "owned proc authority changed during observation",
        ));
    }
    child.verify()?;
    eprintln!(
        "private owned writable-proc authority metadata: {}",
        serde_json::json!({
            "source": "held owned PIDFD/proc-directory/root; O_PATH/statx only",
            "score_path": "/proc/1/oom_score_adj", "score_inode": {
                "device": m.dev(), "inode": m.ino(), "mode": m.mode(),
                "host_uid": m.uid(), "host_gid": m.gid(), "nlink": m.nlink(), "mount_id": mount_id },
            "expected_mapped_host_uid": child.uids.start, "expected_mapped_host_gid": child.gids.start,
            "status": before, "score_body_read": false, "score_body_written": false,
            "credentials_changed": false, "dumpability_changed": false, "authority_issued": false
        })
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    const PROC: &str = "9 2 0:8 / /proc ro,nosuid,nodev,noexec,relatime - proc proc rw,gid=203009,hidepid=invisible\n";
    #[test]
    fn production_runtime_proc_mount_parser_rejects_duplicate_alias_and_shared_inventory() {
        assert_eq!(mount_records(PROC.as_bytes()).unwrap().len(), 1);
        assert!(mount_records(format!("{PROC}{PROC}").as_bytes()).is_err());
        assert!(mount_records(PROC.replace(" - proc", " shared:12 - proc").as_bytes()).is_err());
        assert!(mount_records(PROC.replace("/proc ", "/proc\\040alias ").as_bytes()).is_err());
        assert!(mount_records(PROC.trim_end().as_bytes()).is_err());
        assert!(mount_records(PROC.replace("ro,nosuid", "ro,ro,nosuid").as_bytes()).is_err());
    }
    #[test]
    fn production_runtime_proc_transition_preserves_all_other_mount_identity_fields() {
        let before = mount_records(PROC.as_bytes()).unwrap().remove(&9).unwrap();
        let mut after = before.clone();
        after.flags.remove("ro");
        after.flags.insert("rw".into());
        assert!(changed_proc_root(&before, &after));
        let mut changed = after.clone();
        changed.device += 1;
        assert!(!changed_proc_root(&before, &changed));
        changed = after.clone();
        changed.options = "rw,gid=0,hidepid=off".into();
        assert!(!changed_proc_root(&before, &changed));
        changed = after.clone();
        changed.flags.remove("nodev");
        assert!(!changed_proc_root(&before, &changed));
        changed = after;
        changed.id += 1;
        assert!(!changed_proc_root(&before, &changed));
    }
    #[test]
    fn production_runtime_proc_fixed_mask_roles_never_include_process_or_network_entries() {
        let ro: BTreeSet<_> = READ_ONLY.into_iter().collect();
        let masked: BTreeSet<_> = MASKED.into_iter().collect();
        assert_eq!(ro.len(), 5);
        assert_eq!(masked.len(), 10);
        assert!(ro.is_disjoint(&masked));
        for value in ro.union(&masked) {
            assert!(
                !value.contains('/')
                    && !value.contains('.')
                    && !["1", "self", "thread-self", "net", "fd"].contains(value)
            );
        }
    }
    const STACK: &str = "1 1 0:1 / / rw,nosuid,nodev - tmpfs tmpfs rw\n30 1 7:1 /proc /proc ro,nosuid,nodev,relatime - ext4 /dev/loop1 ro\n20 30 0:8 / /proc ro,nosuid,nodev,noexec,relatime - proc proc rw,gid=203009,hidepid=invisible\n";
    fn stack_actual(id: u64, dev: u64) -> BTreeMap<String, (u64, u64)> {
        BTreeMap::from([
            ("/".into(), (1, libc::makedev(0, 1))),
            ("/proc".into(), (id, dev)),
        ])
    }
    #[test]
    fn production_runtime_proc_keeps_all_stacked_layers_and_uses_actual_visible_id() {
        let records = mount_records(STACK.as_bytes()).unwrap();
        assert_eq!(records.len(), 3);
        let actual = stack_actual(20, libc::makedev(0, 8));
        assert_eq!(checked_visible(&records, &actual).unwrap()["/proc"], 20);
        let reverse = STACK
            .lines()
            .rev()
            .map(|s| format!("{s}\n"))
            .collect::<String>();
        assert_eq!(mount_records(reverse.as_bytes()).unwrap(), records);
        assert_eq!(
            checked_visible(&mount_records(reverse.as_bytes()).unwrap(), &actual).unwrap()["/proc"],
            20
        );
        let root = mount_records(b"5 5 0:1 / / rw,nosuid,nodev - tmpfs tmpfs rw\n").unwrap();
        assert_eq!(
            checked_visible(
                &root,
                &BTreeMap::from([("/".into(), (5, libc::makedev(0, 1)))])
            )
            .unwrap()["/"],
            5
        );
        let hidden=mount_records(b"1 1 0:1 / / rw - tmpfs tmpfs rw\n2 1 7:1 /dev /dev ro - ext4 /dev/loop1 ro\n3 2 0:3 / /dev/pts rw - devpts devpts rw\n4 2 0:4 / /dev rw - tmpfs tmpfs rw\n5 4 0:5 / /dev/pts rw - devpts devpts rw\n").unwrap();
        let actual = BTreeMap::from([
            ("/".into(), (1, libc::makedev(0, 1))),
            ("/dev".into(), (4, libc::makedev(0, 4))),
            ("/dev/pts".into(), (5, libc::makedev(0, 5))),
        ]);
        assert_eq!(checked_visible(&hidden, &actual).unwrap()["/dev/pts"], 5);
        let mut wrong = actual;
        wrong.insert("/dev/pts".into(), (3, libc::makedev(0, 3)));
        assert!(checked_visible(&hidden, &wrong).is_err());
    }
    #[test]
    fn production_runtime_proc_rejects_duplicate_id_wrong_visible_layer_and_stack_forks() {
        let records = mount_records(STACK.as_bytes()).unwrap();
        for (id, dev) in [
            (30, libc::makedev(7, 1)),
            (99, libc::makedev(0, 8)),
            (20, libc::makedev(7, 1)),
        ] {
            assert!(checked_visible(&records, &stack_actual(id, dev)).is_err());
        }
        assert!(
            mount_records(format!("{STACK}{}\n", STACK.lines().next().unwrap()).as_bytes())
                .is_err()
        );
        let fork = mount_records(STACK.replace("20 30 ", "20 1 ").as_bytes()).unwrap();
        assert!(checked_visible(&fork, &stack_actual(20, libc::makedev(0, 8))).is_err());
        let cycle = mount_records(STACK.replace("30 1 ", "30 20 ").as_bytes()).unwrap();
        assert!(checked_visible(&cycle, &stack_actual(20, libc::makedev(0, 8))).is_err());
    }
    #[test]
    fn production_runtime_proc_transition_preserves_hidden_layers_and_visible_selection() {
        let records = mount_records(STACK.as_bytes()).unwrap();
        let before = MountInventory {
            records,
            visible: BTreeMap::from([("/".into(), 1), ("/proc".into(), 20)]),
        };
        let mut after = before.clone();
        let proc = after.records.get_mut(&20).unwrap();
        proc.flags.remove("ro");
        proc.flags.insert("rw".into());
        assert!(verify_old_layers(&before, &after).is_ok());
        let mut changed = after.clone();
        changed.records.get_mut(&30).unwrap().source = "/dev/foreign".into();
        assert!(verify_old_layers(&before, &changed).is_err());
        changed = after.clone();
        changed.records.remove(&30);
        assert!(verify_old_layers(&before, &changed).is_err());
        changed = after;
        changed.visible.insert("/proc".into(), 30);
        assert!(verify_old_layers(&before, &changed).is_err());
    }
    #[test]
    fn production_runtime_proc_held_statx_matches_real_descriptor_and_rejects_wrong_identity() {
        let temp = tempfile::tempdir().unwrap();
        let root = OpenOptions::new()
            .read(true)
            .custom_flags(libc::O_PATH | libc::O_DIRECTORY | libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(temp.path())
            .unwrap();
        let file = target_from_root(&root, "/").unwrap();
        let id = held_mount_id(&file).unwrap();
        let dev = file.metadata().unwrap().dev();
        assert_eq!(held_mount_id(&root).unwrap(), id);
        assert_eq!(Node::of(&root).unwrap(), Node::of(&file).unwrap());
        let record = MountRecord {
            id,
            parent: id + 1,
            device: dev,
            root: "/".into(),
            target: "/".into(),
            flags: BTreeSet::new(),
            filesystem: "controlled".into(),
            source: "controlled".into(),
            options: "controlled".into(),
        };
        let records = BTreeMap::from([(id, record)]);
        assert!(checked_visible(&records, &BTreeMap::from([("/".into(), (id, dev))])).is_ok());
        assert!(checked_visible(&records, &BTreeMap::from([("/".into(), (id + 1, dev))])).is_err());
        std::os::unix::fs::symlink("/", temp.path().join("outside")).unwrap();
        assert!(target_from_root(&root, "/outside").is_err());
        for target in ["/../", "/./x", "//proc", "/proc/", "relative"] {
            assert!(target_from_root(&root, target).is_err());
        }
    }
    fn observation_channel(passcred: bool) -> (OwnedFd, OwnedFd) {
        let mut raw = [-1_i32; 2];
        assert_eq!(
            unsafe {
                libc::socketpair(
                    libc::AF_UNIX,
                    libc::SOCK_SEQPACKET | libc::SOCK_CLOEXEC,
                    0,
                    raw.as_mut_ptr(),
                )
            },
            0
        );
        let receiver = unsafe { OwnedFd::from_raw_fd(raw[0]) };
        let sender = unsafe { OwnedFd::from_raw_fd(raw[1]) };
        if passcred {
            let one = 1_i32;
            assert_eq!(
                unsafe {
                    libc::setsockopt(
                        receiver.as_raw_fd(),
                        libc::SOL_SOCKET,
                        libc::SO_PASSCRED,
                        (&one as *const i32).cast(),
                        std::mem::size_of::<i32>() as libc::socklen_t,
                    )
                },
                0
            );
        }
        (receiver, sender)
    }

    #[test]
    fn production_runtime_proc_authenticated_failure_survives_closed_peer() {
        let nonce = [0x73; 16];
        let (receiver, sender) = observation_channel(true);
        let encoded = (0x3000_0000_u32 | (4 << 24) | (511 << 12) | libc::EACCES as u32) as i32;
        send_packet(
            sender.as_raw_fd(),
            &Packet::new(nonce, Phase::Failed, encoded, 1),
        )
        .unwrap();
        drop(sender);
        let live_calls = std::cell::Cell::new(0);
        let error = receive_xattr_record(
            receiver.as_raw_fd(),
            nonce,
            unsafe { libc::getpid() } as u32,
            unsafe { libc::getuid() },
            unsafe { libc::getgid() },
            || {
                live_calls.set(live_calls.get() + 1);
                Err(NamespaceError::Rejected("PID 1 exited"))
            },
        )
        .unwrap_err();
        assert!(
            error
                .to_string()
                .contains("stage=4 source-line=511 errno=13")
        );
        assert_eq!(live_calls.get(), 0);
    }

    #[test]
    fn production_runtime_proc_success_keeps_actual_live_verification() {
        let nonce = [0x74; 16];
        for observed in [0, libc::EPERM, libc::EOPNOTSUPP, 4095] {
            let (receiver, sender) = observation_channel(true);
            send_packet(
                sender.as_raw_fd(),
                &Packet::new(nonce, Phase::WritableProcChecked, observed, 1),
            )
            .unwrap();
            let calls = std::cell::Cell::new(0);
            let value = receive_xattr_record(
                receiver.as_raw_fd(),
                nonce,
                unsafe { libc::getpid() } as u32,
                unsafe { libc::getuid() },
                unsafe { libc::getgid() },
                || {
                    calls.set(calls.get() + 1);
                    Ok(())
                },
            )
            .unwrap();
            assert_eq!(value, observed);
            assert_eq!(calls.get(), 1);
        }
        let (receiver, sender) = observation_channel(true);
        send_packet(
            sender.as_raw_fd(),
            &Packet::new(nonce, Phase::WritableProcChecked, 0, 1),
        )
        .unwrap();
        let error = receive_xattr_record(
            receiver.as_raw_fd(),
            nonce,
            unsafe { libc::getpid() } as u32,
            unsafe { libc::getuid() },
            unsafe { libc::getgid() },
            || Err(NamespaceError::Rejected("PID 1 exited")),
        )
        .unwrap_err();
        assert!(error.to_string().contains("PID 1 exited"));
    }

    #[test]
    fn production_runtime_proc_observation_rejects_wrong_peer_phase_and_encoding() {
        let nonce = [0x75; 16];
        let pid = unsafe { libc::getpid() } as u32;
        let uid = unsafe { libc::getuid() };
        let gid = unsafe { libc::getgid() };
        for case in 0..11 {
            let (receiver, sender) = observation_channel(true);
            let mut packet = Packet::new(nonce, Phase::WritableProcChecked, 0, 1);
            let (mut expected_pid, mut expected_uid, mut expected_gid) = (pid, uid, gid);
            match case {
                0 => packet = Packet::new([0x99; 16], Phase::WritableProcChecked, 0, 1),
                1 => packet = Packet::new(nonce, Phase::WritableProcChecked, 0, 2),
                2 => expected_pid += 1,
                3 => expected_uid += 1,
                4 => expected_gid += 1,
                5 => packet.phase = Phase::WritableProcReady as u32,
                6 => packet.errno = -1,
                7 => packet.errno = 4096,
                8 => {
                    packet.phase = Phase::Failed as u32;
                    packet.errno = 0;
                }
                9 => {
                    packet.phase = Phase::Failed as u32;
                    packet.errno = libc::EACCES;
                }
                10 => {
                    packet.phase = Phase::Failed as u32;
                    packet.errno = 0x3500_1001;
                }
                _ => unreachable!(),
            }
            send_packet(sender.as_raw_fd(), &packet).unwrap();
            let calls = std::cell::Cell::new(0);
            assert!(
                receive_xattr_record(
                    receiver.as_raw_fd(),
                    nonce,
                    expected_pid,
                    expected_uid,
                    expected_gid,
                    || {
                        calls.set(calls.get() + 1);
                        Ok(())
                    }
                )
                .is_err()
            );
            assert_eq!(calls.get(), 0);
        }
    }

    #[test]
    fn production_runtime_proc_observation_rejects_rights_and_missing_credentials() {
        let nonce = [0x76; 16];
        let packet = Packet::new(nonce, Phase::WritableProcChecked, 0, 1);
        let (receiver, sender) = observation_channel(true);
        let file = File::open("/dev/null").unwrap();
        let count = || std::fs::read_dir("/proc/self/fd").unwrap().count();
        let before = count();
        send_one_fd(sender.as_raw_fd(), &packet, file.as_fd()).unwrap();
        assert!(
            receive_xattr_record(
                receiver.as_raw_fd(),
                nonce,
                unsafe { libc::getpid() } as u32,
                unsafe { libc::getuid() },
                unsafe { libc::getgid() },
                || panic!("descriptor response must not reach live-success check")
            )
            .is_err()
        );
        assert_eq!(count(), before);
        let (receiver, sender) = observation_channel(false);
        send_packet(sender.as_raw_fd(), &packet).unwrap();
        assert!(
            receive_xattr_record(
                receiver.as_raw_fd(),
                nonce,
                unsafe { libc::getpid() } as u32,
                unsafe { libc::getuid() },
                unsafe { libc::getgid() },
                || panic!("missing credentials must not reach live-success check")
            )
            .is_err()
        );
    }

    #[test]
    fn production_runtime_proc_authority_status_rejects_duplicate_missing_and_drift() {
        let valid = b"Name:\tprivate\nUid:\t200000\t200000\t200000\t200000\nGid:\t200000\t200000\t200000\t200000\nGroups:\t\nCapInh:\t0000000000000000\nCapPrm:\t00000000002800e4\nCapEff:\t00000000002800e4\nCapBnd:\t00000000002800e4\nCapAmb:\t0000000000000080\nNoNewPrivs:\t1\nSeccomp:\t2\n";
        assert_eq!(
            private_status_fields(valid, 200000, 200000).unwrap().len(),
            10
        );
        let text = std::str::from_utf8(valid).unwrap();
        for bad in [
            format!("{text}Uid:\t200000\t200000\t200000\t200000\n"),
            text.replace("CapAmb:\t0000000000000080\n", ""),
            text.replace("NoNewPrivs:\t1", "NoNewPrivs:\t0"),
            text.replace("Groups:\t\n", "Groups:\t1\n"),
            text.replace("00000000002800e4", "00000000002800g4"),
            text.replace("Uid:\t200000", "Uid:\t0"),
            text.trim_end().to_owned(),
        ] {
            assert!(private_status_fields(bad.as_bytes(), 200000, 200000).is_err());
        }
        assert!(private_status_fields(valid, 0, 200000).is_err());
    }

    #[test]
    fn production_runtime_proc_dumpability_keeps_original_authenticated_failure() {
        let nonce = [0x77; 16];
        let (receiver, sender) = observation_channel(true);
        send_packet(
            sender.as_raw_fd(),
            &Packet::new(nonce, Phase::PrivateProcDumpability, 0, 1),
        )
        .unwrap();
        let encoded = (0x3000_0000_u32 | (4 << 24) | (472 << 12) | libc::EACCES as u32) as i32;
        send_packet(
            sender.as_raw_fd(),
            &Packet::new(nonce, Phase::Failed, encoded, 1),
        )
        .unwrap();
        drop(sender);
        let pid = unsafe { libc::getpid() } as u32;
        let uid = unsafe { libc::getuid() };
        let gid = unsafe { libc::getgid() };
        assert_eq!(
            receive_dumpability_record(receiver.as_raw_fd(), nonce, pid, uid, gid).unwrap(),
            0
        );
        let error = receive_xattr_record(receiver.as_raw_fd(), nonce, pid, uid, gid, || {
            panic!("metadata and failure cannot grant success")
        })
        .unwrap_err();
        assert!(
            error
                .to_string()
                .contains("stage=4 source-line=472 errno=13")
        );
    }

    #[test]
    fn production_runtime_proc_dumpability_rejects_wrong_peer_repeat_range_and_rights() {
        let nonce = [0x78; 16];
        let pid = unsafe { libc::getpid() } as u32;
        let uid = unsafe { libc::getuid() };
        let gid = unsafe { libc::getgid() };
        for case in 0..8 {
            let (receiver, sender) = observation_channel(case != 7);
            let mut packet = Packet::new(nonce, Phase::PrivateProcDumpability, 0, 1);
            let mut expected_pid = pid;
            match case {
                0 => packet.errno = -1,
                1 => packet.errno = 3,
                2 => packet.phase = Phase::WritableProcChecked as u32,
                3 => packet = Packet::new([0x99; 16], Phase::PrivateProcDumpability, 0, 1),
                4 => expected_pid += 1,
                _ => (),
            }
            let file = File::open("/dev/null").unwrap();
            let count = || std::fs::read_dir("/proc/self/fd").unwrap().count();
            let before = count();
            if case == 6 {
                send_one_fd(sender.as_raw_fd(), &packet, file.as_fd()).unwrap();
            } else {
                send_packet(sender.as_raw_fd(), &packet).unwrap();
            }
            if case == 5 {
                assert_eq!(
                    receive_dumpability_record(receiver.as_raw_fd(), nonce, expected_pid, uid, gid)
                        .unwrap(),
                    0
                );
                send_packet(sender.as_raw_fd(), &packet).unwrap();
                assert!(
                    receive_xattr_record(receiver.as_raw_fd(), nonce, pid, uid, gid, || panic!(
                        "repeated metadata cannot grant success"
                    ))
                    .is_err()
                );
            } else {
                assert!(
                    receive_dumpability_record(receiver.as_raw_fd(), nonce, expected_pid, uid, gid)
                        .is_err()
                );
            }
            assert_eq!(count(), before);
        }
    }
}
