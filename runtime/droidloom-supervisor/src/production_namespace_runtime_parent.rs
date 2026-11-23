//! Consume only the same-tree PreparedRuntime capability. This establishes
//! fixed mount roles, not permission to execute Android or a Running state.
use super::*;
use crate::production_runtime_assets::{
    ActivationRootRole, PreparedRuntime, QueryLayout, QueryRole, RuntimeTransfer,
    verify_activation_root,
};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::CStr;

#[path = "production_namespace_runtime_cgroup_projection.rs"]
mod cgroup_projection;
use cgroup_projection::{CGROUP, NativeCgroupObservation, SYS, verify_native_cgroup_projection};

#[path = "production_namespace_initial_mount_projection.rs"]
mod initial_mount_projection;
pub(super) use initial_mount_projection::InitialMountProjection;
#[path = "production_namespace_init_propagation_projection.rs"]
mod initial_propagation_projection;
pub(super) use initial_propagation_projection::{
    InitialPropagationProjection, InitialStorageBindProjection, NativeStorageSnapshot,
};

const RO_IMAGE: u64 = 1 | 2 | 4;
const NOEXEC: u64 = 8;
const QUERY_TARGET: &str = "/.droidloom-query";
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
const NATIVE_ROLES: [(&str, &[&CStr], bool); 3] = [
    (
        "/system/lib64/libprocessgroup.so",
        &[c"lib64", c"libprocessgroup.so"],
        false,
    ),
    (
        "/system/lib64/libprocessgroup_setup.so",
        &[c"lib64", c"libprocessgroup_setup.so"],
        false,
    ),
    (
        "/.droidloom-cgroup-v2-policy",
        &[c"rc", c"cgroup-v2-policy.json"],
        true,
    ),
];
const BOOTSTRAP_ROLES: [(&str, &[&CStr], bool); 1] = [("/bootstrap-apex", &[], true)];

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
    activation: Option<ActivationRootRole>,
}

impl Role {
    fn same_node(&self, file: &File) -> Result<bool> {
        let now = ImmutableNode::of(file)?;
        Ok(if self.activation.is_some() {
            (now.dev, now.ino, now.mode, now.uid, now.gid)
                == (
                    self.node.dev,
                    self.node.ino,
                    self.node.mode,
                    self.node.uid,
                    self.node.gid,
                )
                && now.nlink >= 2
        } else {
            now == self.node
        })
    }
}

pub(super) struct RuntimeObservation {
    roles: Vec<Role>,
    before: writable_proc::MountInventory,
    after: Option<writable_proc::MountInventory>,
    private_root: Node,
    query: Option<QueryProjection>,
    native: bool,
    native_payload: Option<Node>,
    activation_count: usize,
}

struct QueryProjection {
    layout: QueryLayout,
    files: Vec<QueryLeaf>,
}

struct QueryLeaf {
    role: QueryRole,
    file: File,
    node: ImmutableNode,
}

fn query_names(layout: QueryLayout) -> BTreeSet<String> {
    layout
        .roles()
        .iter()
        .map(|role| role.name().to_str().expect("fixed ASCII query role").into())
        .collect()
}

fn query_files(root: &File, layout: QueryLayout, uid: u32, gid: u32) -> Result<Vec<QueryLeaf>> {
    if names(root)? != query_names(layout) {
        return Err(NamespaceError::Rejected(
            "query filesystem differs from the complete declared layout",
        ));
    }
    let mut files = Vec::new();
    let mut inodes = BTreeSet::new();
    for &role in layout.roles() {
        let file = source_path(root, &[role.name()], false)?;
        let node = role_node(&file, uid, gid, false)?;
        if node.mode != libc::S_IFREG | role.mode()
            || !(64..=128 * 1024 * 1024).contains(&node.bytes)
            || !inodes.insert((node.dev, node.ino))
        {
            return Err(NamespaceError::Rejected(
                "private query leaf metadata or distinct role identity differs",
            ));
        }
        files.push(QueryLeaf { role, file, node });
    }
    Ok(files)
}

fn query_flags(file: &File) -> Result<()> {
    if filesystem_kind(file)? != 0x0102_1994 {
        return Err(NamespaceError::Rejected(
            "query role is not the owned private tmpfs",
        ));
    }
    verify_process_statfs(file, 0x0102_1994, RO_IMAGE, NOEXEC)
}

impl QueryProjection {
    fn before(root: &File, child: &TreeChild, layout: QueryLayout) -> Result<Self> {
        query_flags(root)?;
        if root.metadata()?.mode() != libc::S_IFDIR | 0o555 {
            return Err(NamespaceError::Rejected(
                "query filesystem root mode differs",
            ));
        }
        let files = query_files(root, layout, child.uids.start, child.gids.start)?;
        let mount = writable_proc::held_mount_id(root)?;
        for leaf in &files {
            query_flags(&leaf.file)?;
            if writable_proc::held_mount_id(&leaf.file)? != mount {
                return Err(NamespaceError::Rejected(
                    "query leaf is not on its held private filesystem",
                ));
            }
        }
        Ok(Self { layout, files })
    }

    fn verify(&self, root: &File) -> Result<()> {
        query_flags(root)?;
        if names(root)? != query_names(self.layout) {
            return Err(NamespaceError::Rejected("query filesystem leaves changed"));
        }
        let mount = writable_proc::held_mount_id(root)?;
        for leaf in &self.files {
            let target = source_path(root, &[leaf.role.name()], false)?;
            query_flags(&leaf.file)?;
            query_flags(&target)?;
            if ImmutableNode::of(&leaf.file)? != leaf.node
                || ImmutableNode::of(&target)? != leaf.node
                || writable_proc::held_mount_id(&target)? != mount
                || writable_proc::held_mount_id(&leaf.file)? != mount
            {
                return Err(NamespaceError::Rejected(
                    "query role changed after original-owner projection",
                ));
            }
        }
        Ok(())
    }
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

#[cfg(test)]
fn verify_transition(
    before: &writable_proc::MountInventory,
    after: &writable_proc::MountInventory,
    has_query: bool,
) -> Result<()> {
    verify_transition_roles(before, after, has_query, false)
}
#[cfg(test)]
fn verify_transition_roles(
    before: &writable_proc::MountInventory,
    after: &writable_proc::MountInventory,
    has_query: bool,
    has_native: bool,
) -> Result<()> {
    verify_transition_layout(before, after, has_query, has_native, false)
}

#[cfg(test)]
fn verify_transition_layout(
    before: &writable_proc::MountInventory,
    after: &writable_proc::MountInventory,
    has_query: bool,
    has_native: bool,
    has_activation: bool,
) -> Result<()> {
    verify_transition_roots(
        before,
        after,
        has_query,
        has_native,
        if has_activation { 2 } else { 0 },
    )
}

fn verify_transition_roots(
    before: &writable_proc::MountInventory,
    after: &writable_proc::MountInventory,
    has_query: bool,
    has_native: bool,
    activation_count: usize,
) -> Result<()> {
    if ![0, 2, 3].contains(&activation_count) {
        return Err(NamespaceError::Rejected(
            "runtime activation root layout differs",
        ));
    }
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
    let mut wanted: BTreeSet<_> = ROLES.iter().map(|r| r.0).collect();
    if has_native {
        wanted.extend(NATIVE_ROLES.iter().map(|r| r.0));
    }
    if activation_count == 3 {
        wanted.extend(BOOTSTRAP_ROLES.iter().map(|r| r.0));
    }
    if has_query {
        wanted.insert(QUERY_TARGET);
    }
    if added.len()
        != ROLES.len()
            + usize::from(has_query)
            + (if has_native { NATIVE_ROLES.len() } else { 0 })
            + usize::from(activation_count == 3)
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
    let mut expected_visible = before.visible.clone();
    for row in added {
        let writable = ActivationRootRole::ALL
            .iter()
            .take(activation_count)
            .any(|role| role.target() == row.target);
        if after.visible.get(&row.target) != Some(&row.id)
            || if writable {
                row.filesystem != "tmpfs"
                    || row.root != "/"
                    || !row.options.split(',').any(|option| option == "rw")
                    || row.options.split(',').any(|option| option == "ro")
            } else if row.target == QUERY_TARGET {
                !has_query
                    || row.filesystem != "tmpfs"
                    || row.root != "/"
                    || !row.options.split(',').any(|option| option == "ro")
                    || row.options.split(',').any(|option| option == "rw")
            } else {
                !["ext4", "erofs"].contains(&row.filesystem.as_str())
            }
            || ![if writable { "rw" } else { "ro" }, "nosuid", "nodev"]
                .iter()
                .all(|f| row.flags.contains(*f))
            || row.flags.contains(if writable { "ro" } else { "rw" })
        {
            return Err(NamespaceError::Rejected(
                "runtime mount is not its fixed visible readonly role",
            ));
        }
        let noexec = if writable {
            true
        } else if row.target == QUERY_TARGET {
            false
        } else {
            ROLES
                .iter()
                .chain(NATIVE_ROLES.iter())
                .chain(BOOTSTRAP_ROLES.iter())
                .find(|r| r.0 == row.target)
                .ok_or(NamespaceError::Rejected("unregistered runtime mount role"))?
                .2
        };
        if row.flags.contains("noexec") != noexec {
            return Err(NamespaceError::Rejected(
                "runtime role execute policy differs",
            ));
        }
        expected_visible.insert(row.target.clone(), row.id);
    }
    if after.visible != expected_visible {
        return Err(NamespaceError::Rejected(
            "runtime changed an undeclared visible mount or introduced an alias",
        ));
    }
    Ok(())
}

impl RuntimeObservation {
    pub(super) fn verify_private_root(&self, root: &File) -> Result<()> {
        if Node::of(root)? != self.private_root {
            return Err(NamespaceError::Rejected(
                "original private root identity changed",
            ));
        }
        Ok(())
    }

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

    fn before(child: &TreeChild, transfer: &RuntimeTransfer<'_>) -> Result<Self> {
        child.verify()?;
        let fds = transfer.as_slice();
        let query_layout = transfer.query_layout();
        let activation_count = transfer.activation_root_count();
        if fds.len() != 2 + usize::from(query_layout.is_some()) + activation_count {
            return Err(NamespaceError::Rejected(
                "runtime descriptor role count differs",
            ));
        }
        let runtime = File::from(fds[0].try_clone_to_owned()?);
        let init = File::from(fds[1].try_clone_to_owned()?);
        image_flags(&runtime, false)?;
        role_node(&runtime, child.uids.start, child.gids.start, true)?;
        let root_names = names(&runtime)?;
        let native = root_names.contains("lib64");
        let mut expected_root = BTreeSet::from(["apex".into(), "linkerconfig".into(), "rc".into()]);
        if native {
            expected_root.insert("lib64".into());
        }
        if root_names != expected_root {
            return Err(NamespaceError::Rejected(
                "runtime root has undeclared roles",
            ));
        }
        let rc = source_path(&runtime, &[c"rc"], true)?;
        role_node(&rc, child.uids.start, child.gids.start, true)?;
        let mut expected_rc = BTreeSet::from([
            "init.rc".into(),
            "bootconfig".into(),
            "cgroups.json".into(),
            "task_profiles.json".into(),
        ]);
        if native {
            expected_rc.insert("cgroup-v2-policy.json".into());
        }
        if names(&rc)? != expected_rc {
            return Err(NamespaceError::Rejected("runtime rc has undeclared leaves"));
        }
        if native {
            let library = source_path(&runtime, &[c"lib64"], true)?;
            role_node(&library, child.uids.start, child.gids.start, true)?;
            if names(&library)?
                != BTreeSet::from([
                    "libprocessgroup.so".into(),
                    "libprocessgroup_setup.so".into(),
                ])
            {
                return Err(NamespaceError::Rejected(
                    "native runtime library directory differs",
                ));
            }
        }
        let mut roles = Vec::new();
        for (target, path, noexec) in ROLES
            .into_iter()
            .chain(
                NATIVE_ROLES
                    .into_iter()
                    .take(if native { NATIVE_ROLES.len() } else { 0 }),
            )
            .chain(
                BOOTSTRAP_ROLES
                    .into_iter()
                    .take(usize::from(activation_count == 3)),
            )
        {
            let directory = matches!(
                target,
                "/.droidloom-runtime" | "/apex" | "/linkerconfig" | "/bootstrap-apex"
            );
            let writable = ActivationRootRole::ALL
                .iter()
                .take(activation_count)
                .copied()
                .find(|role| role.target() == target);
            let source = if let Some(role) = writable {
                let original_container = if role == ActivationRootRole::BootstrapApex {
                    let original =
                        writable_proc::target_from_root(&held_child_root(child)?, target)?;
                    role_node(&original, child.uids.start, child.gids.start, true)?;
                    image_flags(&original, false)?;
                    original
                } else {
                    source_path(&runtime, path, true)?
                };
                if !names(&original_container)?.is_empty() {
                    return Err(NamespaceError::Rejected(
                        "activation image container must remain empty before original-init activation",
                    ));
                }
                let index = match role {
                    ActivationRootRole::Apex => 2,
                    ActivationRootRole::Linkerconfig => 3,
                    ActivationRootRole::BootstrapApex => 4,
                };
                File::from(fds[index].try_clone_to_owned()?)
            } else if target == "/system/bin/init" {
                init.try_clone()?
            } else {
                source_path(&runtime, path, directory)?
            };
            let node = role_node(&source, child.uids.start, child.gids.start, directory)?;
            if let Some(role) = writable {
                verify_activation_root(&source, role, child.uids.start, child.gids.start)
                    .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
                if !names(&source)?.is_empty() {
                    return Err(NamespaceError::Rejected(
                        "activation root was not empty at the transfer boundary",
                    ));
                }
            } else {
                image_flags(&source, false)?;
            }
            if target == "/system/bin/init"
                && (node.mode != libc::S_IFREG | 0o555 || node.bytes < 64)
            {
                return Err(NamespaceError::Rejected(
                    "runtime original init identity differs",
                ));
            }
            // Only fixed role-container directories are checked here.
            // Payload roots and all descendants preserve their actual APEX
            // UID/GID/modes/xattrs and are bound by PreparedRuntime's manifest.
            roles.push(Role {
                target,
                source,
                node,
                noexec: writable.is_some() || noexec,
                activation: writable,
            });
        }
        let query = if let Some(layout) = query_layout {
            let source = File::from(
                fds[transfer.query_index().ok_or(NamespaceError::Rejected(
                    "query descriptor role index absent",
                ))?]
                .try_clone_to_owned()?,
            );
            let node = role_node(&source, child.uids.start, child.gids.start, true)?;
            let query = QueryProjection::before(&source, child, layout)?;
            roles.push(Role {
                target: QUERY_TARGET,
                source,
                node,
                noexec: false,
                activation: None,
            });
            Some(query)
        } else {
            None
        };
        let before = writable_proc::MountInventory::observe(child, "before-runtime-transfer")?;
        let private_root = Node::of(&held_child_root(child)?)?;
        child.verify()?;
        Ok(Self {
            roles,
            before,
            after: None,
            private_root,
            query,
            native,
            native_payload: None,
            activation_count,
        })
    }

    fn verify_original_sys(&self, child: &TreeChild) -> Result<()> {
        let root = held_child_root(child)?;
        self.verify_private_root(&root)?;
        let sys = writable_proc::target_from_root(&root, SYS)?;
        let row = role_node(&sys, child.uids.start, child.gids.start, true)?;
        image_flags(&sys, false)?;
        if row.mode != libc::S_IFDIR | 0o755
            || !names(&sys)?.is_empty()
            || self.before.visible.get(SYS) != Some(&writable_proc::held_mount_id(&sys)?)
        {
            return Err(NamespaceError::Rejected("native lower sys must be the empty admitted base directory"));
        }
        Ok(())
    }

    fn verify_native_cgroup_mounts(
        &self,
        child: &TreeChild,
        root: &File,
        after: &writable_proc::MountInventory,
        payload: Node,
    ) -> Result<writable_proc::MountInventory> {
        let sys = writable_proc::target_from_root(root, SYS)?;
        let fs_dir = writable_proc::target_from_root(root, "/sys/fs")?;
        let cgroup = writable_proc::target_from_root(root, CGROUP)?;
        let sys_id = writable_proc::held_mount_id(&sys)?;
        let device = sys.metadata()?.dev();
        for file in [&sys, &fs_dir] {
            let metadata = file.metadata()?;
            if metadata.mode() != libc::S_IFDIR | 0o755
                || metadata.uid() != child.uids.start
                || metadata.gid() != child.gids.start
                || metadata.dev() != device
                || writable_proc::held_mount_id(file)? != sys_id
            {
                return Err(NamespaceError::Rejected("native sys directory owner or mount differs"));
            }
        }
        let metadata = cgroup.metadata()?;
        let system = child.gids.start.checked_add(1000)
            .ok_or(NamespaceError::Rejected("mapped cgroup owner overflow"))?;
        if metadata.mode() != libc::S_IFDIR | 0o775
            || metadata.uid() != child.uids.start
            || metadata.gid() != system
            || names(&sys)? != BTreeSet::from(["fs".into()])
            || names(&fs_dir)? != BTreeSet::from(["cgroup".into()])
        {
            return Err(NamespaceError::Rejected("native cgroup and sys scaffold shape differs"));
        }
        verify_native_cgroup_projection(
            &self.before,
            after,
            payload,
            NativeCgroupObservation {
                sys_mount_id: sys_id,
                sys_device: device,
                cgroup_mount_id: writable_proc::held_mount_id(&cgroup)?,
                cgroup: Node::of(&cgroup)?,
            },
        )
    }

    fn observe_verified(&self, child: &TreeChild) -> Result<writable_proc::MountInventory> {
        child.verify()?;
        let now = writable_proc::MountInventory::observe(child, "after-runtime-ready")?;
        let root = held_child_root(child)?;
        self.verify_private_root(&root)?;
        let ordinary_roles = match (self.native, self.native_payload) {
            (true, Some(payload)) => Some(self.verify_native_cgroup_mounts(child, &root, &now, payload)?),
            (false, None) => None,
            _ => return Err(NamespaceError::Rejected("native cgroup attachment lacks its original active payload")),
        };
        verify_transition_roots(
            &self.before,
            ordinary_roles.as_ref().unwrap_or(&now),
            self.query.is_some(),
            self.native,
            self.activation_count,
        )?;
        if self.after.as_ref().is_some_and(|old| old != &now) {
            return Err(NamespaceError::Rejected(
                "prepared runtime mount inventory changed",
            ));
        }
        for role in &self.roles {
            if !role.same_node(&role.source)? {
                return Err(NamespaceError::Rejected("held runtime input changed"));
            }
            let target = writable_proc::target_from_root(&root, role.target)?;
            if !role.same_node(&target)?
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
            if let Some(activation) = role.activation {
                for file in [&role.source, &target] {
                    verify_activation_root(file, activation, child.uids.start, child.gids.start)
                        .map_err(|error| NamespaceError::RuntimeResource(error.to_string()))?;
                }
            } else if role.target == QUERY_TARGET {
                self.query
                    .as_ref()
                    .ok_or(NamespaceError::Rejected("query role lost owner custody"))?
                    .verify(&target)?;
            } else {
                image_flags(&target, role.noexec)?;
            }
        }
        child.verify()?;
        Ok(now)
    }

    pub(super) fn verify(&mut self, child: &TreeChild) -> Result<()> {
        self.after = Some(self.observe_verified(child)?);
        Ok(())
    }

    /// Reobserve the complete original prepared mount generation. An executed
    /// caller cannot use this to accept an init-created mount transition.
    pub(super) fn verify_current(
        &self,
        child: &TreeChild,
    ) -> Result<writable_proc::MountInventory> {
        if self.after.is_none() {
            return Err(NamespaceError::Rejected(
                "runtime transfer has not been observed",
            ));
        }
        self.observe_verified(child)
    }
}

impl IsolatedNamespaces {
    /// Consume exactly one PreparedRuntime for the same opaque identity. A send
    /// failure retains its resources until actual tree reap or quarantine.
    pub(crate) fn attach_runtime(mut self, mut runtime: PreparedRuntime) -> Result<Self> {
        self.verify_live_admission()?;
        self.require_cgroup_hierarchy_ready()?;
        if self.runtime.is_some()
            || self.retirement.prepared.runtime.is_some()
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
            let mut observation = RuntimeObservation::before(child, &fds)?;
            if observation.native {
                observation.verify_original_sys(child)?;
                observation.native_payload = Some(self.prepare_native_payload_projection()?);
            }
            let phase = if fds.activation_root_count() == 3 {
                if fds.query_layout() == Some(QueryLayout::Contacts) {
                    Phase::MountRuntimeBootstrapActivationContacts
                } else {
                    Phase::MountRuntimeBootstrapActivation
                }
            } else if fds.activation_roots() {
                if fds.query_layout() == Some(QueryLayout::Contacts) {
                    Phase::MountRuntimeActivationContacts
                } else {
                    Phase::MountRuntimeActivation
                }
            } else if fds.query_layout() == Some(QueryLayout::Contacts) {
                Phase::MountRuntimeContacts
            } else {
                Phase::MountRuntime
            };
            let packet = Packet::new(child.nonce, phase, 0, child.parent_pid);
            match fds {
                RuntimeTransfer::Base(files) => {
                    send_base_fds(child.control.as_raw_fd(), &packet, files)?
                }
                RuntimeTransfer::WithQuery { files, .. } => {
                    send_extended_runtime_fds(child.control.as_raw_fd(), &packet, files)?
                }
                RuntimeTransfer::WithActivation(files) => {
                    send_extended_runtime_fds(child.control.as_raw_fd(), &packet, files)?
                }
                RuntimeTransfer::WithActivationQuery { files, .. } => {
                    send_extended_runtime_fds(child.control.as_raw_fd(), &packet, files)?
                }
                RuntimeTransfer::WithBootstrapActivation(files) => {
                    send_extended_runtime_fds(child.control.as_raw_fd(), &packet, files)?
                }
                RuntimeTransfer::WithBootstrapActivationQuery { files, .. } => {
                    send_extended_runtime_fds(child.control.as_raw_fd(), &packet, files)?
                }
            }
            Ok(observation)
        })();
        self.retirement.prepared.runtime = Some(ResourcePreparation::Admitted);
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

fn send_extended_runtime_fds<const N: usize>(
    socket: RawFd,
    packet: &Packet,
    files: [BorrowedFd<'_>; N],
) -> Result<()> {
    // Only the fixed extended layouts have an issuer. The original
    // two-descriptor transport remains separate.
    if !match (packet.phase, N) {
        (phase, 3) => {
            phase == Phase::MountRuntime as u32 || phase == Phase::MountRuntimeContacts as u32
        }
        (phase, 4) => phase == Phase::MountRuntimeActivation as u32,
        (phase, 5) => {
            phase == Phase::MountRuntimeActivation as u32
                || phase == Phase::MountRuntimeActivationContacts as u32
                || phase == Phase::MountRuntimeBootstrapActivation as u32
        }
        (phase, 6) => {
            phase == Phase::MountRuntimeBootstrapActivation as u32
                || phase == Phase::MountRuntimeBootstrapActivationContacts as u32
        }
        _ => false,
    } {
        return Err(NamespaceError::Rejected(
            "runtime transfer phase and fixed descriptor count differ",
        ));
    }
    let mut iov = libc::iovec {
        iov_base: (packet as *const Packet).cast_mut().cast(),
        iov_len: std::mem::size_of::<Packet>(),
    };
    let mut control = [0_usize; 8];
    let mut message: libc::msghdr = unsafe { std::mem::zeroed() };
    message.msg_iov = &mut iov;
    message.msg_iovlen = 1;
    message.msg_control = control.as_mut_ptr().cast();
    message.msg_controllen = unsafe { libc::CMSG_SPACE((N * 4) as u32) } as usize;
    let header = unsafe { libc::CMSG_FIRSTHDR(&message) };
    if header.is_null() {
        return Err(NamespaceError::Rejected(
            "query runtime ancillary header absent",
        ));
    }
    unsafe {
        (*header).cmsg_level = libc::SOL_SOCKET;
        (*header).cmsg_type = libc::SCM_RIGHTS;
        (*header).cmsg_len = libc::CMSG_LEN((N * 4) as u32) as usize;
        let data = libc::CMSG_DATA(header).cast::<i32>();
        for (i, file) in files.iter().enumerate() {
            std::ptr::write_unaligned(data.add(i), file.as_raw_fd());
        }
    }
    let sent = unsafe { libc::sendmsg(socket, &message, libc::MSG_NOSIGNAL | libc::MSG_DONTWAIT) };
    if sent < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if sent as usize != std::mem::size_of::<Packet>() {
        return Err(NamespaceError::Rejected(
            "incomplete fixed query-runtime descriptor transfer",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contacts_projection_rejects_partial_roles_exec_jar_and_actual_aliases() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let make = |name: &str, mode: u32| {
            let path = dir.path().join(name);
            std::fs::write(&path, [0_u8; 64]).unwrap();
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(mode)).unwrap();
        };
        make("cmd", 0o555);
        make("toybox", 0o555);
        let root = File::open(dir.path()).unwrap();
        let meta = root.metadata().unwrap();
        let read = |layout| query_files(&root, layout, meta.uid(), meta.gid());
        assert_eq!(read(QueryLayout::Commands).unwrap().len(), 2);
        assert!(read(QueryLayout::Contacts).is_err());

        make("app_process64", 0o555);
        make("content.jar", 0o444);
        let complete = read(QueryLayout::Contacts).unwrap();
        assert_eq!(complete.len(), 4);
        assert_eq!(complete[2].role, QueryRole::AppProcess64);
        assert_eq!(complete[3].role, QueryRole::ContentJar);
        assert_eq!(complete[3].node.mode, libc::S_IFREG | 0o444);
        assert!(read(QueryLayout::Commands).is_err());

        let jar = dir.path().join("content.jar");
        std::fs::set_permissions(&jar, std::fs::Permissions::from_mode(0o555)).unwrap();
        assert!(read(QueryLayout::Contacts).is_err());
        std::fs::set_permissions(&jar, std::fs::Permissions::from_mode(0o444)).unwrap();
        make("undeclared", 0o444);
        assert!(read(QueryLayout::Contacts).is_err());
        std::fs::remove_file(dir.path().join("undeclared")).unwrap();

        let app = dir.path().join("app_process64");
        std::fs::remove_file(&app).unwrap();
        std::os::unix::fs::symlink("cmd", &app).unwrap();
        assert!(read(QueryLayout::Contacts).is_err());
        std::fs::remove_file(&app).unwrap();
        std::fs::hard_link(dir.path().join("cmd"), &app).unwrap();
        assert!(read(QueryLayout::Contacts).is_err());
    }

    fn base_roles() -> writable_proc::MountInventory {
        let mut after = writable_proc::MountInventory::default();
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
        after
    }
    #[test]
    fn writable_activation_roles_require_two_exact_mount_targets_and_flags() {
        let before = writable_proc::MountInventory::default();
        let mut after = base_roles();
        for role in ActivationRootRole::LEGACY {
            let id = after.visible[role.target()];
            let row = after.records.get_mut(&id).unwrap();
            row.filesystem = "tmpfs".into();
            row.flags = ["rw", "nosuid", "nodev", "noexec"]
                .into_iter()
                .map(str::to_owned)
                .collect();
            row.options = format!("rw,size={},nr_inodes={}", role.bytes(), role.inodes());
        }
        verify_transition_layout(&before, &after, false, false, true).unwrap();
        assert!(verify_transition_layout(&before, &after, false, false, false).is_err());
        assert!(verify_transition_layout(&before, &base_roles(), false, false, true).is_err());
        for role in ActivationRootRole::LEGACY {
            let id = after.visible[role.target()];
            for flag in ["rw", "nosuid", "nodev", "noexec"] {
                let mut wrong = after.clone();
                wrong.records.get_mut(&id).unwrap().flags.remove(flag);
                assert!(verify_transition_layout(&before, &wrong, false, false, true).is_err());
            }
            for mutation in 0..5 {
                let mut wrong = after.clone();
                let row = wrong.records.get_mut(&id).unwrap();
                match mutation {
                    0 => row.flags.insert("ro".into()),
                    1 => {
                        row.options = "ro".into();
                        true
                    }
                    2 => {
                        row.root = "/subtree".into();
                        true
                    }
                    3 => {
                        row.filesystem = "ext4".into();
                        true
                    }
                    _ => {
                        row.target = "/system".into();
                        true
                    }
                };
                assert!(verify_transition_layout(&before, &wrong, false, false, true).is_err());
            }
        }
        let mut wrong = after.clone();
        wrong.visible.insert("/extra".into(), 2);
        assert!(verify_transition_layout(&before, &wrong, false, false, true).is_err());
    }

    #[test]
    fn bootstrap_activation_requires_its_third_exact_mount_without_legacy_widening() {
        let before = writable_proc::MountInventory::default();
        let mut after = base_roles();
        let id = after.records.keys().next_back().unwrap() + 1;
        let mut bootstrap = after.records[&after.visible["/apex"]].clone();
        bootstrap.id = id;
        bootstrap.target = "/bootstrap-apex".into();
        after.records.insert(id, bootstrap);
        after.visible.insert("/bootstrap-apex".into(), id);
        for role in ActivationRootRole::ALL {
            let row = after
                .records
                .get_mut(&after.visible[role.target()])
                .unwrap();
            row.filesystem = "tmpfs".into();
            row.flags = ["rw", "nosuid", "nodev", "noexec"]
                .into_iter()
                .map(str::to_owned)
                .collect();
            row.options = format!("rw,size={},nr_inodes={}", role.bytes(), role.inodes());
        }
        verify_transition_roots(&before, &after, false, false, 3).unwrap();
        for count in [0, 1, 2, 4, usize::MAX] {
            assert!(verify_transition_roots(&before, &after, false, false, count).is_err());
        }
        assert!(verify_transition_roots(&before, &base_roles(), false, false, 3).is_err());
        for role in ActivationRootRole::ALL {
            let id = after.visible[role.target()];
            let mut absent = after.clone();
            absent.records.remove(&id);
            absent.visible.remove(role.target());
            assert!(verify_transition_roots(&before, &absent, false, false, 3).is_err());
            for flag in ["rw", "nosuid", "nodev", "noexec"] {
                let mut wrong = after.clone();
                wrong.records.get_mut(&id).unwrap().flags.remove(flag);
                assert!(verify_transition_roots(&before, &wrong, false, false, 3).is_err());
            }
            for mutation in 0..6 {
                let mut wrong = after.clone();
                let row = wrong.records.get_mut(&id).unwrap();
                match mutation {
                    0 => {
                        row.target = "/undeclared".into();
                    }
                    1 => {
                        row.root = "/subtree".into();
                    }
                    2 => {
                        row.filesystem = "ext4".into();
                    }
                    3 => {
                        row.options = "ro".into();
                    }
                    4 => {
                        row.flags.insert("ro".into());
                    }
                    _ => {
                        row.target = "/system".into();
                    }
                }
                assert!(verify_transition_roots(&before, &wrong, false, false, 3).is_err());
            }
        }
        let mut alias = after.clone();
        alias.visible.insert("/bootstrap-alias".into(), id);
        assert!(verify_transition_roots(&before, &alias, false, false, 3).is_err());
        let mut duplicate = after.clone();
        let mut row = duplicate.records[&id].clone();
        row.id = id + 1;
        duplicate.records.insert(row.id, row);
        assert!(verify_transition_roots(&before, &duplicate, false, false, 3).is_err());
    }

    #[test]
    fn writable_activation_observation_keeps_the_original_root_inode_and_metadata() {
        use std::os::unix::fs::PermissionsExt;
        let directory = tempfile::tempdir().unwrap();
        let held = File::open(directory.path()).unwrap();
        let role = Role {
            target: "/linkerconfig",
            node: ImmutableNode::of(&held).unwrap(),
            source: held.try_clone().unwrap(),
            noexec: true,
            activation: Some(ActivationRootRole::Linkerconfig),
        };
        std::fs::create_dir(directory.path().join("bootstrap")).unwrap();
        std::fs::write(
            directory.path().join("bootstrap/ld.config.txt"),
            b"ordinary inode-control fixture",
        )
        .unwrap();
        assert!(role.same_node(&held).unwrap());
        let replacement = tempfile::tempdir().unwrap();
        assert!(
            !role
                .same_node(&File::open(replacement.path()).unwrap())
                .unwrap()
        );
        let before = held.metadata().unwrap().permissions();
        std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o711)).unwrap();
        assert!(!role.same_node(&held).unwrap());
        std::fs::set_permissions(directory.path(), before).unwrap();
        assert!(role.same_node(&held).unwrap());
        // Inode predicates alone do not qualify this ordinary directory as
        // the bounded, idmapped and labelled activation mount.
        assert!(
            verify_activation_root(
                &held,
                ActivationRootRole::Linkerconfig,
                unsafe { libc::geteuid() },
                unsafe { libc::getegid() }
            )
            .is_err()
        );
    }

    #[test]
    fn production_runtime_roles_reject_extra_targets_and_mutated_existing_ids() {
        let before = writable_proc::MountInventory::default();
        let after = base_roles();
        verify_transition(&before, &after, false).unwrap();
        let mut bad = after.clone();
        bad.records.get_mut(&1).unwrap().target = "/arbitrary".into();
        assert!(verify_transition(&before, &bad, false).is_err());
        let mut bad = after.clone();
        bad.visible.insert("/apex".into(), 99);
        assert!(verify_transition(&before, &bad, false).is_err());
        let mut bad = after.clone();
        bad.records
            .get_mut(&8)
            .unwrap()
            .flags
            .insert("noexec".into());
        assert!(verify_transition(&before, &bad, false).is_err());
        let mut existing = before;
        existing.records.insert(99, after.records[&1].clone());
        assert!(verify_transition(&existing, &after, false).is_err());
    }
    #[test]
    fn production_runtime_query_mount_requires_selected_fixed_readonly_tmpfs() {
        let before = writable_proc::MountInventory::default();
        let mut after = base_roles();
        // Declaring query roles cannot silently accept a base-only mount set.
        assert!(verify_transition(&before, &after, true).is_err());
        after.visible.insert(QUERY_TARGET.into(), 9);
        after.records.insert(
            9,
            writable_proc::MountRecord {
                id: 9,
                parent: 1,
                device: 2,
                root: "/".into(),
                target: QUERY_TARGET.into(),
                flags: BTreeSet::from(["ro".into(), "nosuid".into(), "nodev".into()]),
                filesystem: "tmpfs".into(),
                source: "owned-query".into(),
                options: "ro".into(),
            },
        );
        verify_transition(&before, &after, true).unwrap();
        assert!(verify_transition(&before, &after, false).is_err());
        for flag in ["ro", "nosuid", "nodev"] {
            let mut bad = after.clone();
            bad.records.get_mut(&9).unwrap().flags.remove(flag);
            assert!(verify_transition(&before, &bad, true).is_err());
        }
        let mut bad = after.clone();
        bad.records
            .get_mut(&9)
            .unwrap()
            .flags
            .insert("noexec".into());
        assert!(verify_transition(&before, &bad, true).is_err());
        let mut bad = after.clone();
        bad.records.get_mut(&9).unwrap().filesystem = "ext4".into();
        assert!(verify_transition(&before, &bad, true).is_err());
        let mut bad = after.clone();
        bad.records.get_mut(&9).unwrap().options = "rw,size=1048576".into();
        assert!(verify_transition(&before, &bad, true).is_err());
        let mut bad = after.clone();
        bad.records.get_mut(&9).unwrap().root = "/subtree".into();
        assert!(verify_transition(&before, &bad, true).is_err());
        let mut bad = after.clone();
        bad.records.get_mut(&9).unwrap().target = "/system/bin".into();
        assert!(verify_transition(&before, &bad, true).is_err());
        let mut bad = after;
        bad.visible.insert("/undeclared-query".into(), 9);
        assert!(verify_transition(&before, &bad, true).is_err());
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
