//! Consume only the same-tree PreparedRuntime capability. This establishes
//! fixed mount roles, not permission to execute Android or a Running state.
use super::*;
use crate::production_runtime_assets::PreparedRuntime;
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CStr;

const RO_IMAGE: u64 = 1 | 2 | 4;
const NOEXEC: u64 = 8;
const ROLES: [(&str, &[&CStr], bool); 8] = [
    ("/.droidloom-runtime", &[], false),
    ("/apex", &[c"apex"], false),
    ("/linkerconfig", &[c"linkerconfig"], false),
    ("/system/etc/init/hw/init.rc", &[c"rc", c"init.rc"], true),
    ("/proc/bootconfig", &[c"rc", c"bootconfig"], true),
    ("/system/etc/cgroups.json", &[c"rc", c"cgroups.json"], true),
    (
        "/system/etc/task_profiles.json",
        &[c"rc", c"task_profiles.json"],
        true,
    ),
    ("/system/bin/init", &[], false),
];

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct ImmutableNode {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    nlink: u64,
    bytes: u64,
    mtime: i64,
    mtime_nsec: i64,
    ctime: i64,
    ctime_nsec: i64,
}
impl ImmutableNode {
    fn of(file: &File) -> Result<Self> {
        let m = file.metadata()?;
        Ok(Self {
            dev: m.dev(),
            ino: m.ino(),
            mode: m.mode(),
            uid: m.uid(),
            gid: m.gid(),
            nlink: m.nlink(),
            bytes: m.size(),
            mtime: m.mtime(),
            mtime_nsec: m.mtime_nsec(),
            ctime: m.ctime(),
            ctime_nsec: m.ctime_nsec(),
        })
    }
}

struct Role {
    target: &'static str,
    source: File,
    node: ImmutableNode,
    noexec: bool,
}

pub(super) struct RuntimeObservation {
    roles: Vec<Role>,
    before: writable_proc::MountInventory,
    after: Option<writable_proc::MountInventory>,
    private_root: Node,
}

fn opened(parent: &File, name: &CStr, directory: bool) -> Result<File> {
    let flags = libc::O_PATH
        | libc::O_CLOEXEC
        | libc::O_NOFOLLOW
        | libc::O_NONBLOCK
        | if directory { libc::O_DIRECTORY } else { 0 };
    let raw = unsafe { libc::openat(parent.as_raw_fd(), name.as_ptr(), flags) };
    if raw < 0 {
        return Err(io::Error::last_os_error().into());
    }
    let file = unsafe { File::from_raw_fd(raw) };
    if file.metadata()?.mode() & libc::S_IFMT == libc::S_IFLNK {
        return Err(NamespaceError::Rejected("runtime fixed input is a symlink"));
    }
    Ok(file)
}

fn source_path(root: &File, components: &[&CStr], directory: bool) -> Result<File> {
    let mut file = root.try_clone()?;
    for (i, name) in components.iter().enumerate() {
        file = opened(&file, name, i + 1 < components.len() || directory)?;
    }
    Ok(file)
}

fn names(directory: &File) -> Result<BTreeSet<String>> {
    let before = Node::of(directory)?;
    let mut out = BTreeSet::new();
    // This proc-FD lookup is limited to our own held public runtime directory;
    // it does not enter a caller-chosen process or traverse its pathname.
    for row in std::fs::read_dir(format!("/proc/self/fd/{}", directory.as_raw_fd()))? {
        let name = row?
            .file_name()
            .into_string()
            .map_err(|_| NamespaceError::Rejected("non-text runtime root entry"))?;
        if out.len() == 64 || !out.insert(name) {
            return Err(NamespaceError::Rejected("runtime role directory bound"));
        }
    }
    if Node::of(directory)? != before {
        return Err(NamespaceError::Rejected("runtime role directory changed"));
    }
    Ok(out)
}

fn image_flags(file: &File, noexec: bool) -> Result<()> {
    let kind = filesystem_kind(file)?;
    if ![0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&kind) {
        return Err(NamespaceError::Rejected("runtime tree filesystem type"));
    }
    verify_process_statfs(
        file,
        kind,
        RO_IMAGE | if noexec { NOEXEC } else { 0 },
        if noexec { 0 } else { NOEXEC },
    )
}

fn role_node(file: &File, uid: u32, gid: u32, directory: bool) -> Result<ImmutableNode> {
    let node = ImmutableNode::of(file)?;
    if node.mode & libc::S_IFMT
        != if directory {
            libc::S_IFDIR
        } else {
            libc::S_IFREG
        }
        || node.uid != uid
        || node.gid != gid
        || node.mode & 0o6022 != 0
        || (!directory && node.nlink != 1)
    {
        return Err(NamespaceError::Rejected("fixed runtime role owner or type"));
    }
    Ok(node)
}

fn verify_transition(
    before: &writable_proc::MountInventory,
    after: &writable_proc::MountInventory,
) -> Result<()> {
    for (id, row) in &before.records {
        if after.records.get(id) != Some(row) {
            return Err(NamespaceError::Rejected(
                "runtime changed an existing mount identity",
            ));
        }
    }
    let added: Vec<_> = after
        .records
        .iter()
        .filter(|(id, _)| !before.records.contains_key(id))
        .map(|(_, r)| r)
        .collect();
    let wanted: BTreeSet<_> = ROLES.iter().map(|r| r.0).collect();
    if added.len() != ROLES.len()
        || added
            .iter()
            .map(|r| r.target.as_str())
            .collect::<BTreeSet<_>>()
            != wanted
    {
        return Err(NamespaceError::Rejected(
            "runtime added an undeclared or duplicate mount",
        ));
    }
    for row in added {
        if after.visible.get(&row.target) != Some(&row.id)
            || !["ext4", "erofs"].contains(&row.filesystem.as_str())
            || !["ro", "nosuid", "nodev"]
                .iter()
                .all(|f| row.flags.contains(*f))
            || row.flags.contains("rw")
        {
            return Err(NamespaceError::Rejected(
                "runtime mount is not its fixed visible readonly role",
            ));
        }
        let noexec = ROLES.iter().find(|r| r.0 == row.target).unwrap().2;
        if row.flags.contains("noexec") != noexec {
            return Err(NamespaceError::Rejected(
                "runtime role execute policy differs",
            ));
        }
    }
    Ok(())
}

impl RuntimeObservation {
    pub(super) fn verify_executable_target(&self, target: &File) -> Result<()> {
        let init = self
            .roles
            .iter()
            .find(|role| role.target == "/system/bin/init")
            .ok_or(NamespaceError::Rejected(
                "held original init role is absent",
            ))?;
        if ImmutableNode::of(&init.source)? != init.node || ImmutableNode::of(target)? != init.node
        {
            return Err(NamespaceError::Rejected(
                "executed image is not the held original init",
            ));
        }
        image_flags(target, false)
    }

    fn before(child: &TreeChild, fds: [BorrowedFd<'_>; 2]) -> Result<Self> {
        child.verify()?;
        let runtime = File::from(fds[0].try_clone_to_owned()?);
        let init = File::from(fds[1].try_clone_to_owned()?);
        image_flags(&runtime, false)?;
        role_node(&runtime, child.uids.start, child.gids.start, true)?;
        if names(&runtime)? != BTreeSet::from(["apex".into(), "linkerconfig".into(), "rc".into()]) {
            return Err(NamespaceError::Rejected(
                "runtime root has undeclared roles",
            ));
        }
        let rc = source_path(&runtime, &[c"rc"], true)?;
        role_node(&rc, child.uids.start, child.gids.start, true)?;
        if names(&rc)?
            != BTreeSet::from([
                "init.rc".into(),
                "bootconfig".into(),
                "cgroups.json".into(),
                "task_profiles.json".into(),
            ])
        {
            return Err(NamespaceError::Rejected("runtime rc has undeclared leaves"));
        }
        let mut roles = Vec::new();
        for (target, path, noexec) in ROLES {
            let directory = matches!(target, "/.droidloom-runtime" | "/apex" | "/linkerconfig");
            let source = if target == "/system/bin/init" {
                init.try_clone()?
            } else {
                source_path(&runtime, path, directory)?
            };
            let node = role_node(&source, child.uids.start, child.gids.start, directory)?;
            image_flags(&source, false)?;
            if target == "/system/bin/init"
                && (node.mode != libc::S_IFREG | 0o555 || node.bytes < 64)
            {
                return Err(NamespaceError::Rejected(
                    "runtime original init identity differs",
                ));
            }
            // Only the three role-container directories are checked here.
            // Payload roots and all descendants preserve their actual APEX
            // UID/GID/modes/xattrs and are bound by PreparedRuntime's manifest.
            roles.push(Role {
                target,
                source,
                node,
                noexec,
            });
        }
        let before = writable_proc::MountInventory::observe(child, "before-runtime-transfer")?;
        let private_root = Node::of(&held_child_root(child)?)?;
        child.verify()?;
        Ok(Self {
            roles,
            before,
            after: None,
            private_root,
        })
    }

    pub(super) fn verify(&mut self, child: &TreeChild) -> Result<()> {
        child.verify()?;
        let now = writable_proc::MountInventory::observe(child, "after-runtime-ready")?;
        verify_transition(&self.before, &now)?;
        if self.after.as_ref().is_some_and(|old| old != &now) {
            return Err(NamespaceError::Rejected(
                "prepared runtime mount inventory changed",
            ));
        }
        let root = held_child_root(child)?;
        if Node::of(&root)? != self.private_root {
            return Err(NamespaceError::Rejected("private runtime root changed"));
        }
        for role in &self.roles {
            if ImmutableNode::of(&role.source)? != role.node {
                return Err(NamespaceError::Rejected("held runtime input changed"));
            }
            let target = writable_proc::target_from_root(&root, role.target)?;
            if ImmutableNode::of(&target)? != role.node
                || writable_proc::held_mount_id(&target)?
                    != *now
                        .visible
                        .get(role.target)
                        .ok_or(NamespaceError::Rejected("visible runtime role absent"))?
            {
                return Err(NamespaceError::Rejected(
                    "runtime projection differs from held input",
                ));
            }
            image_flags(&target, role.noexec)?;
        }
        child.verify()?;
        self.after = Some(now);
        Ok(())
    }
}

impl IsolatedNamespaces {
    /// Consume exactly one PreparedRuntime for the same opaque identity. A send
    /// failure retains its resources until actual tree reap or quarantine.
    pub(crate) fn attach_runtime(mut self, mut runtime: PreparedRuntime) -> Result<Self> {
        self.verify_live_admission()?;
        if self.runtime.is_some()
            || self.runtime_observation.is_some()
            || self.writable_proc.is_none()
        {
            return Err(NamespaceError::Rejected(
                "runtime requires one writable-proc barrier",
            ));
        }
        let transferred: Result<RuntimeObservation> = (|| {
            let child = self
                .init
                .as_ref()
                .ok_or(NamespaceError::Rejected("PID1 absent"))?;
            self.writable_proc.as_mut().unwrap().verify(child)?;
            let witness = self.witness()?;
            let fds = runtime
                .descriptors_for_transfer(&witness)
                .map_err(|e| NamespaceError::RuntimeResource(e.to_string()))?;
            let observation = RuntimeObservation::before(child, fds)?;
            send_base_fds(
                child.control.as_raw_fd(),
                &Packet::new(child.nonce, Phase::MountRuntime, 0, child.parent_pid),
                fds,
            )?;
            Ok(observation)
        })();
        self.runtime = Some(runtime);
        let mut observation = transferred?;
        let child = self
            .init
            .as_ref()
            .ok_or(NamespaceError::Rejected("PID1 absent"))?;
        child.receive_phase(Phase::RuntimeReady)?;
        observation.verify(child)?;
        self.runtime_observation = Some(observation);
        self.verify_live_admission()?;
        Ok(self)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn production_runtime_roles_reject_extra_targets_and_mutated_existing_ids() {
        let before = writable_proc::MountInventory::default();
        let mut after = before.clone();
        for (i, (target, _, noexec)) in ROLES.iter().enumerate() {
            let id = i as u64 + 1;
            let mut flags = BTreeSet::from(["ro".into(), "nosuid".into(), "nodev".into()]);
            if *noexec {
                flags.insert("noexec".into());
            }
            after.visible.insert((*target).into(), id);
            after.records.insert(
                id,
                writable_proc::MountRecord {
                    id,
                    parent: 1,
                    device: 1,
                    root: "/".into(),
                    target: (*target).into(),
                    flags,
                    filesystem: "ext4".into(),
                    source: "owned".into(),
                    options: "ro".into(),
                },
            );
        }
        verify_transition(&before, &after).unwrap();
        let mut bad = after.clone();
        bad.records.get_mut(&1).unwrap().target = "/arbitrary".into();
        assert!(verify_transition(&before, &bad).is_err());
        let mut bad = after.clone();
        bad.visible.insert("/apex".into(), 99);
        assert!(verify_transition(&before, &bad).is_err());
        let mut bad = after.clone();
        bad.records
            .get_mut(&8)
            .unwrap()
            .flags
            .insert("noexec".into());
        assert!(verify_transition(&before, &bad).is_err());
        let mut existing = before;
        existing.records.insert(99, after.records[&1].clone());
        assert!(verify_transition(&existing, &after).is_err());
    }
    #[test]
    fn production_runtime_fixed_component_walk_rejects_actual_symlinks() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir(dir.path().join("rc")).unwrap();
        std::fs::write(dir.path().join("rc/init.rc"), b"fixed").unwrap();
        std::os::unix::fs::symlink("init.rc", dir.path().join("rc/alias")).unwrap();
        let root = File::open(dir.path()).unwrap();
        let held = source_path(&root, &[c"rc", c"init.rc"], false).unwrap();
        assert_eq!(held.metadata().unwrap().len(), 5);
        assert!(source_path(&root, &[c"rc", c"alias"], false).is_err());
        assert!(source_path(&root, &[c"rc", c"init.rc"], true).is_err());
    }
}
