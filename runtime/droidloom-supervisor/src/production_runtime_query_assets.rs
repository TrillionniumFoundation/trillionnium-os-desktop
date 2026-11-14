//! Two private query executables derived from this selected original system.
//!
//! The original input inodes and their xattrs are never changed. New tmpfs
//! inodes receive the one dedicated query entrypoint label, then the owned
//! superblock and idmapped mount are made read-only before any transfer.
//! PreparedRuntime retains all source, mount and reservation custody until
//! actual original-tree retirement. These inputs do not issue Android Ready.
use super::*;
use crate::production_namespace::ApplicationAuthority;

const MAX_QUERY: u64 = 128 * 1024 * 1024;
const QUERY_EXEC: &[u8; 35] = b"u:object_r:droidloom_query_exec:s0\0";
const CMD_ORIGINAL: &[u8; 26] = b"u:object_r:system_file:s0\0";
const TOYBOX_ORIGINAL: &[u8; 27] = b"u:object_r:toolbox_exec:s0\0";
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const INITIAL_TMPFS: &[u8; 20] = b"u:object_r:tmpfs:s0\0";
const FSCONFIG_CMD_RECONFIGURE: u32 = 7;
const FSPICK_CLOEXEC: u32 = 1;
const FSPICK_EMPTY_PATH: u32 = 8;

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct QueryDeclaration {
    scope: String,
    source_system_sha256: String,
    cmd: QuerySource,
    toybox: QuerySource,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct QuerySource {
    original: ImageDeclaration,
    source_path: String,
    interpreter: Option<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum QueryRole {
    Cmd,
    Toybox,
}
impl QueryRole {
    fn name(self) -> &'static CStr {
        match self {
            Self::Cmd => c"cmd",
            Self::Toybox => c"toybox",
        }
    }
    fn original_name(self) -> &'static str {
        match self {
            Self::Cmd => "cmd-original",
            Self::Toybox => "toybox-original",
        }
    }
    fn source_path(self) -> &'static str {
        match self {
            Self::Cmd => "/system/bin/cmd",
            Self::Toybox => "/system/bin/toybox",
        }
    }
    fn parse(name: &CStr) -> Result<Self> {
        if name == c"cmd" {
            Ok(Self::Cmd)
        } else if name == c"toybox" {
            Ok(Self::Toybox)
        } else {
            Err(MountError::Rejected("query executable role is not fixed"))
        }
    }
    fn original_security(self, file: &File) -> Result<()> {
        match self {
            Self::Cmd => require_exact_xattr(file, c"security.selinux", CMD_ORIGINAL)?,
            Self::Toybox => require_exact_xattr(file, c"security.selinux", TOYBOX_ORIGINAL)?,
        }
        require_absent_xattr(file, c"security.capability")
    }
}

impl QueryDeclaration {
    pub(super) fn validate(&self, runtime: &RuntimeDeclaration) -> Result<()> {
        require(
            self.scope == "fixed_application_query_v1"
                && is_digest(&self.source_system_sha256)
                && self.source_system_sha256 == runtime.source_system.sha256,
            "query sources must bind the complete selected original system image",
        )?;
        for (role, declared) in [
            (QueryRole::Cmd, &self.cmd),
            (QueryRole::Toybox, &self.toybox),
        ] {
            require(
                declared.original.file == role.original_name()
                    && declared.source_path == role.source_path()
                    && (64..=MAX_QUERY).contains(&declared.original.bytes)
                    && is_digest(&declared.original.sha256),
                "bounded fixed original query executable role",
            )?;
            require(
                matches!(
                    declared.interpreter.as_deref(),
                    None | Some("/system/bin/bootstrap/linker64")
                        | Some("/system/bin/linker64")
                        | Some("/apex/com.android.runtime/bin/linker64")
                ),
                "query original interpreter must remain an Android role",
            )?;
        }
        require(
            self.cmd.original.sha256 != self.toybox.original.sha256,
            "cmd and toybox must be distinct original executables",
        )
    }
}

fn full_digest(file: &File, identity: FileIdentity) -> Result<String> {
    require(
        FileIdentity::of(&file.metadata()?) == identity && identity.bytes <= MAX_QUERY,
        "query body changed before hashing",
    )?;
    let mut hash = Sha256::new();
    let mut at = 0_u64;
    let mut buffer = [0_u8; 32 * 1024];
    while at < identity.bytes {
        let size = (identity.bytes - at).min(buffer.len() as u64) as usize;
        let count = match file.read_at(&mut buffer[..size], at) {
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            result => result?,
        };
        require(count != 0, "query source ended before its declared length")?;
        hash.update(&buffer[..count]);
        at += count as u64;
    }
    require(
        file.read_at(&mut buffer[..1], at)? == 0 && FileIdentity::of(&file.metadata()?) == identity,
        "query body changed during complete hashing",
    )?;
    Ok(format!("{:x}", hash.finalize()))
}

fn label_new_inode(file: &File) -> Result<()> {
    // This function is called only for our freshly created tmpfs inode. It
    // never receives a source input or a bind alias of an original inode.
    // The selected component's actual compute_create for broker/tmpfs dir
    // and file yields this label. Recheck the real fresh inode rather than
    // relying on that offline decision or changing a task-wide fscreate SID.
    require_exact_xattr(file, c"security.selinux", INITIAL_TMPFS)?;
    zero_rc(unsafe {
        libc::fsetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            QUERY_EXEC.as_ptr().cast(),
            QUERY_EXEC.len(),
            0,
        )
    })?;
    require_exact_xattr(file, c"security.selinux", QUERY_EXEC)?;
    require_absent_xattr(file, c"security.capability")
}

fn readonly_mount_node(file: &File, expected: FileIdentity, id: u64) -> Result<()> {
    require(
        FileIdentity::of(&file.metadata()?) == expected
            && fs_type(file)? == TMPFS_MAGIC
            && mount_id(file)? == id,
        "private query inode, filesystem or owned mount changed",
    )?;
    let mut value: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(file.as_raw_fd(), &mut value) })?;
    require(
        value.f_flag as u64 & READONLY_FLAGS == READONLY_FLAGS
            && value.f_flag as u64 & MOUNT_ATTR_NOEXEC == 0,
        "private query mount must be readonly nosuid nodev and executable",
    )?;
    Ok(())
}
fn readonly_private(file: &File, expected: FileIdentity, id: u64) -> Result<()> {
    readonly_mount_node(file, expected, id)?;
    require_exact_xattr(file, c"security.selinux", QUERY_EXEC)?;
    require_absent_xattr(file, c"security.capability")
}

#[derive(Debug)]
struct QueryExecutable {
    role: QueryRole,
    source: SealedFile,
    copy: File,
    identity: FileIdentity,
    digest: String,
    interpreter: Option<String>,
}
#[derive(Debug)]
pub(super) struct QueryResources {
    mount: File,
    root: File,
    root_identity: FileIdentity,
    mount_id: u64,
    executables: [QueryExecutable; 2],
    // This true state has no external/deserializable constructor. Both the
    // initial-root-owned superblock and its only mount were made read-only.
    superblock_readonly: bool,
}

struct Copied {
    role: QueryRole,
    source: SealedFile,
    identity: FileIdentity,
    digest: String,
    interpreter: Option<String>,
}
fn copy_original(
    role: QueryRole,
    declared: &QuerySource,
    parent: &Path,
    root: &File,
    witness: &OwnedNamespaceWitness<'_>,
) -> Result<Copied> {
    let lease = witness.identity_lease()?;
    let source = SealedFile::open_guarded(parent, role.original_name(), 0, MAX_QUERY, |file| {
        lease.broker_reject_backing_body(file)?;
        Ok(())
    })?;
    require(
        source.identity.mode == libc::S_IFREG | 0o555,
        "original query input must be root-sealed 0555",
    )?;
    source.verify_digest(declared.original.bytes, &declared.original.sha256)?;
    role.original_security(&source.file)?;
    require(
        original_init_elf(&source.file, declared.original.bytes)? == declared.interpreter,
        "actual original query interpreter differs",
    )?;
    let copy = syscall_fd(unsafe {
        libc::openat(
            root.as_raw_fd(),
            role.name().as_ptr(),
            libc::O_RDWR | libc::O_CREAT | libc::O_EXCL | O_SAFE,
            0o600_u32,
        )
    } as _)?;
    let initial = FileIdentity::of(&copy.metadata()?);
    require(
        initial.mode == libc::S_IFREG | 0o600
            && initial.uid == 0
            && initial.gid == 0
            && initial.links == 1
            && initial.bytes == 0
            && fs_type(&copy)? == TMPFS_MAGIC
            && (initial.dev, initial.ino) != (source.identity.dev, source.identity.ino),
        "query copy is not a new singleton owned tmpfs inode",
    )?;
    require_exact_xattr(&copy, c"security.selinux", INITIAL_TMPFS)?;
    let mut buffer = [0_u8; 32 * 1024];
    let mut at = 0_u64;
    while at < declared.original.bytes {
        let size = (declared.original.bytes - at).min(buffer.len() as u64) as usize;
        source.file.read_exact_at(&mut buffer[..size], at)?;
        copy.write_all_at(&buffer[..size], at)?;
        at += size as u64;
    }
    copy.sync_all()?;
    // Never label through an original bind mount: this is the new inode
    // created above on our unique, still detached private tmpfs superblock.
    label_new_inode(&copy)?;
    zero_rc(unsafe { libc::fchmod(copy.as_raw_fd(), 0o555) })?;
    let identity = FileIdentity::of(&copy.metadata()?);
    require(
        identity.bytes == declared.original.bytes
            && full_digest(&copy, identity)? == declared.original.sha256,
        "private query copy is not byte-for-byte its complete original",
    )?;
    source.verify_digest(declared.original.bytes, &declared.original.sha256)?;
    role.original_security(&source.file)?;
    drop(copy); // No writable executable FD survives the sealing boundary.
    Ok(Copied {
        role,
        source,
        identity,
        digest: declared.original.sha256.clone(),
        interpreter: declared.interpreter.clone(),
    })
}

impl QueryResources {
    pub(super) fn prepare(
        declared: &QueryDeclaration,
        parent: &Path,
        witness: &OwnedNamespaceWitness<'_>,
        userns: &File,
        uids: IdRange,
        gids: IdRange,
    ) -> Result<Self> {
        witness.revalidate_live_admission()?;
        let actual_userns = witness.user_namespace().metadata()?;
        let selected_userns = userns.metadata()?;
        require(
            (actual_userns.dev(), actual_userns.ino())
                == (selected_userns.dev(), selected_userns.ino())
                && witness.identity_lease()?.broker_ranges() == (uids, gids),
            "private query assets require the actual same owned user namespace",
        )?;
        let size = declared
            .cmd
            .original
            .bytes
            .checked_add(declared.toybox.original.bytes)
            .and_then(|v| v.checked_add(1024 * 1024))
            .ok_or(MountError::Rejected("query tmpfs size overflow"))?;
        require(
            size <= 2 * MAX_QUERY + 1024 * 1024,
            "private query tmpfs bound",
        )?;
        let context = syscall_fd(unsafe {
            libc::syscall(libc::SYS_fsopen, c"tmpfs".as_ptr(), FSOPEN_CLOEXEC)
        })?;
        configure(
            &context,
            FSCONFIG_SET_STRING,
            c"size",
            Some(&text_name(&size.to_string())?),
        )?;
        configure(&context, FSCONFIG_SET_STRING, c"nr_inodes", Some(c"16"))?;
        configure(&context, FSCONFIG_SET_STRING, c"mode", Some(c"0755"))?;
        configure(&context, FSCONFIG_SET_STRING, c"uid", Some(c"0"))?;
        configure(&context, FSCONFIG_SET_STRING, c"gid", Some(c"0"))?;
        zero_rc(unsafe {
            libc::syscall(
                libc::SYS_fsconfig,
                context.as_raw_fd(),
                FSCONFIG_CMD_CREATE,
                std::ptr::null::<libc::c_char>(),
                std::ptr::null::<libc::c_char>(),
                0,
            )
        } as i32)?;
        let mount = syscall_fd(unsafe {
            libc::syscall(
                libc::SYS_fsmount,
                context.as_raw_fd(),
                FSMOUNT_CLOEXEC,
                (MOUNT_ATTR_NOSUID | MOUNT_ATTR_NODEV) as u32,
            )
        })?;
        drop(context); // No filesystem configuration FD is ever exported.
        require_detached(&mount)?;
        let root = open_leaf(&mount, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
        require(
            fs_type(&root)? == TMPFS_MAGIC
                && root.metadata()?.uid() == 0
                && root.metadata()?.gid() == 0,
            "initial-root-owned private query tmpfs",
        )?;
        require_exact_xattr(&root, c"security.selinux", INITIAL_TMPFS)?;
        let cmd = copy_original(QueryRole::Cmd, &declared.cmd, parent, &root, witness)?;
        let toybox = copy_original(QueryRole::Toybox, &declared.toybox, parent, &root, witness)?;
        label_new_inode(&root)?;
        zero_rc(unsafe { libc::fchmod(root.as_raw_fd(), 0o555) })?;
        let mut root_identity = FileIdentity::of(&root.metadata()?);
        drop(root);
        // A per-mount readonly bit alone is insufficient against mapped init.
        // Seal the initial-root-owned superblock too. Target fsopen.c requires
        // CAP_SYS_ADMIN in sb->s_user_ns before any later reconfiguration;
        // mapped Android root does not possess that initial-userns authority.
        let reconfigure = syscall_fd(unsafe {
            libc::syscall(
                libc::SYS_fspick,
                mount.as_raw_fd(),
                c"".as_ptr(),
                FSPICK_CLOEXEC | FSPICK_EMPTY_PATH,
            )
        })?;
        configure(&reconfigure, FSCONFIG_SET_FLAG, c"ro", None)?;
        zero_rc(unsafe {
            libc::syscall(
                libc::SYS_fsconfig,
                reconfigure.as_raw_fd(),
                FSCONFIG_CMD_RECONFIGURE,
                std::ptr::null::<libc::c_char>(),
                std::ptr::null::<libc::c_char>(),
                0,
            )
        } as i32)?;
        drop(reconfigure);
        let attributes = MountAttr {
            attr_set: READONLY_FLAGS | MOUNT_ATTR_IDMAP,
            attr_clr: 0,
            propagation: 0,
            userns_fd: u64::try_from(userns.as_raw_fd())
                .map_err(|_| MountError::Rejected("query user namespace descriptor"))?,
        };
        zero_rc(unsafe {
            libc::syscall(
                libc::SYS_mount_setattr,
                mount.as_raw_fd(),
                c"".as_ptr(),
                AT_EMPTY_PATH,
                &attributes,
                std::mem::size_of::<MountAttr>(),
            )
        } as i32)?;
        let mount_id = require_detached(&mount)?;
        root_identity.uid = uids.start;
        root_identity.gid = gids.start;
        let root = open_leaf(&mount, c".", libc::O_RDONLY | libc::O_DIRECTORY)?;
        let reopen = |copied: Copied| -> Result<QueryExecutable> {
            let copy = open_leaf(&root, copied.role.name(), libc::O_RDONLY)?;
            let mut identity = copied.identity;
            identity.uid = uids.start;
            identity.gid = gids.start;
            readonly_private(&copy, identity, mount_id)?;
            Ok(QueryExecutable {
                role: copied.role,
                source: copied.source,
                copy,
                identity,
                digest: copied.digest,
                interpreter: copied.interpreter,
            })
        };
        let executables = [reopen(cmd)?, reopen(toybox)?];
        let result = Self {
            mount,
            root,
            root_identity,
            mount_id,
            executables,
            superblock_readonly: true,
        };
        result.revalidate(uids, gids)?;
        witness.revalidate_live_admission()?;
        Ok(result)
    }

    pub(super) fn revalidate(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        require(
            self.superblock_readonly
                && self.root_identity.uid == uids.start
                && self.root_identity.gid == gids.start
                && self.root_identity.mode == libc::S_IFDIR | 0o555,
            "private query superblock or mapped-root custody differs",
        )?;
        readonly_mount_node(&self.mount, self.root_identity, self.mount_id)?;
        readonly_private(&self.root, self.root_identity, self.mount_id)?;
        require_detached(&self.mount)?;
        let names = std::fs::read_dir(format!("/proc/self/fd/{}", self.root.as_raw_fd()))?
            .take(3)
            .map(|row| row.map(|r| r.file_name()))
            .collect::<io::Result<BTreeSet<_>>>()?;
        require(
            names
                == BTreeSet::from([
                    std::ffi::OsString::from("cmd"),
                    std::ffi::OsString::from("toybox"),
                ]),
            "private query filesystem has undeclared leaves",
        )?;
        for executable in &self.executables {
            executable
                .source
                .verify_digest(executable.identity.bytes, &executable.digest)?;
            executable.role.original_security(&executable.source.file)?;
            let actual = open_leaf(&self.root, executable.role.name(), libc::O_RDONLY)?;
            readonly_private(&executable.copy, executable.identity, self.mount_id)?;
            readonly_private(&actual, executable.identity, self.mount_id)?;
            require(
                full_digest(&actual, executable.identity)? == executable.digest,
                "private query complete digest changed",
            )?;
        }
        Ok(())
    }

    pub(super) fn mount(&self) -> BorrowedFd<'_> {
        self.mount.as_fd()
    }
}

/// A borrowed same-owner role. It cannot be deserialized, cloned, built from
/// a pathname/digest or used to export a new mount after runtime readiness.
pub(crate) struct RuntimeQueryExecutable<'a> {
    runtime: &'a PreparedRuntime,
    resources: &'a QueryResources,
    executable: &'a QueryExecutable,
}

fn selected<'a>(
    runtime: &'a PreparedRuntime,
    authority: &ApplicationAuthority<'_>,
) -> Result<&'a QueryResources> {
    authority.revalidate()?;
    require(
        std::ptr::eq(runtime, authority.runtime_owner()?),
        "query inputs must belong to this actual original runtime owner",
    )?;
    let resources = runtime
        .resources
        .as_ref()
        .ok_or(MountError::Rejected("query runtime has retired"))?;
    let (cohort, manifest, host_uid, userns, mapped) = authority.query_runtime_binding()?;
    require(
        runtime.exported
            && resources.cohort == cohort
            && resources.runtime_manifest_sha256 == manifest
            && resources.host_uid == host_uid
            && resources.userns_identity == userns
            && (resources.uids.start, resources.gids.start) == mapped,
        "query runtime selection, namespace or reservation differs",
    )?;
    for input in [
        &resources.base_manifest,
        &resources.manifest,
        &resources.image,
        &resources.init,
    ] {
        input.revalidate()?;
    }
    let query = resources.query.as_ref().ok_or(MountError::Rejected(
        "selected runtime has no fixed query inputs",
    ))?;
    query.revalidate(resources.uids, resources.gids)?;
    authority.revalidate()?;
    Ok(query)
}

impl PreparedRuntime {
    pub(crate) fn query_executable<'a>(
        &'a self,
        authority: &ApplicationAuthority<'_>,
        binary: &CStr,
    ) -> Result<RuntimeQueryExecutable<'a>> {
        let role = QueryRole::parse(binary)?;
        let resources = selected(self, authority)?;
        let executable = resources
            .executables
            .iter()
            .find(|item| item.role == role)
            .ok_or(MountError::Rejected("fixed query executable role absent"))?;
        Ok(RuntimeQueryExecutable {
            runtime: self,
            resources,
            executable,
        })
    }
}

impl RuntimeQueryExecutable<'_> {
    pub(crate) fn revalidate(&self, authority: &ApplicationAuthority<'_>) -> Result<()> {
        require(
            std::ptr::eq(self.resources, selected(self.runtime, authority)?),
            "borrowed private query resource custody changed",
        )
    }
    pub(crate) fn file(&self) -> &File {
        &self.executable.copy
    }
    pub(crate) fn verify_original(
        &self,
        original: &File,
        root_uid: u32,
        root_gid: u32,
    ) -> Result<()> {
        let node = FileIdentity::of(&original.metadata()?);
        require(
            node.mode & libc::S_IFMT == libc::S_IFREG
                && node.mode & 0o6022 == 0
                && node.mode & 0o111 != 0
                && node.uid == root_uid
                && node.gid == root_gid
                && node.bytes == self.executable.identity.bytes
                && (node.dev, node.ino)
                    != (self.executable.identity.dev, self.executable.identity.ino)
                && [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs_type(original)?),
            "guest original query role does not match its selected image metadata",
        )?;
        let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
        zero_rc(unsafe { libc::fstatvfs(original.as_raw_fd(), &mut flags) })?;
        require(
            flags.f_flag as u64 & READONLY_FLAGS == READONLY_FLAGS,
            "guest original query executable is not on its readonly system image",
        )?;
        self.executable.role.original_security(original)?;
        require(
            full_digest(original, node)? == self.executable.digest
                && original_init_elf(original, node.bytes)? == self.executable.interpreter,
            "guest original query bytes differ from the complete selected source role",
        )
    }
    pub(crate) fn verify_projection(&self, target: &File) -> Result<()> {
        readonly_private(target, self.executable.identity, self.resources.mount_id)?;
        require(
            full_digest(target, self.executable.identity)? == self.executable.digest,
            "attached private query role has different bytes",
        )
    }
}
