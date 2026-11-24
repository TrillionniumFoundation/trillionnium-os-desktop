//! Fixed private command roles derived from this selected original system.
//! Optional Contacts inputs add a dedicated app_process entry and nonexecutable
//! content JAR; neither role broadens cmd/toybox executable-label permissions.
//!
//! The original input inodes and their xattrs are never changed. New tmpfs
//! inodes receive their fixed role labels, then the owned
//! superblock and idmapped mount are made read-only before any transfer.
//! PreparedRuntime retains all source, mount and reservation custody until
//! actual original-tree retirement. These inputs do not issue Android Ready.
use super::*;
use crate::production_execution_profile::query_inputs as fixed;
use crate::production_namespace::ApplicationAuthority;

#[path = "production_early_query_assets.rs"]
mod early;
pub(crate) use early::EarlyQueryResources;

const MAX_QUERY: u64 = 128 * 1024 * 1024;
const QUERY_EXEC: &[u8; 35] = b"u:object_r:droidloom_query_exec:s0\0";
const CMD_ORIGINAL: &[u8; 26] = b"u:object_r:system_file:s0\0";
const TOYBOX_ORIGINAL: &[u8; 27] = b"u:object_r:toolbox_exec:s0\0";
const APP_PROCESS_ORIGINAL: &[u8; 26] = b"u:object_r:zygote_exec:s0\0";
const PROVIDER_EXEC: &[u8; 38] = b"u:object_r:droidloom_provider_exec:s0\0";
const PROVIDER_JAR: &[u8; 37] = b"u:object_r:droidloom_provider_jar:s0\0";
const TMPFS_MAGIC: libc::c_long = 0x0102_1994;
const INITIAL_TMPFS: &[u8; 38] = b"u:object_r:droidloom_query_tmpfs_t:s0\0";
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
    contacts: Option<ContactsInputs>,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct ContactsInputs {
    scope: String,
    app_process64: QuerySource,
    content_jar: QuerySource,
}
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct QuerySource {
    original: ImageDeclaration,
    source_path: String,
    interpreter: Option<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum QueryRole {
    Cmd,
    Toybox,
    AppProcess64,
    ContentJar,
}
impl QueryRole {
    fn fixed_input(self) -> fixed::FixedQueryInput {
        fixed::INPUTS[match self {
            Self::Cmd => 0,
            Self::Toybox => 1,
            Self::AppProcess64 => 2,
            Self::ContentJar => 3,
        }]
    }

    fn original_metadata(self, node: FileIdentity, root_uid: u32, root_gid: u32) -> bool {
        let fixed = self.fixed_input();
        node.mode == fixed.original_mode
            && node.uid == root_uid
            && root_gid.checked_add(fixed.original_gid) == Some(node.gid)
            && node.links == 1
            && node.bytes == fixed.bytes
    }

    pub(crate) fn name(self) -> &'static CStr {
        match self {
            Self::Cmd => c"cmd",
            Self::Toybox => c"toybox",
            Self::AppProcess64 => c"app_process64",
            Self::ContentJar => c"content.jar",
        }
    }
    fn original_name(self) -> &'static str {
        match self {
            Self::Cmd => "cmd-original",
            Self::Toybox => "toybox-original",
            Self::AppProcess64 => "contacts-app-process64-original",
            Self::ContentJar => "contacts-content-jar-original",
        }
    }
    fn source_path(self) -> &'static str {
        match self {
            Self::Cmd => "/system/bin/cmd",
            Self::Toybox => "/system/bin/toybox",
            Self::AppProcess64 => "/system/bin/app_process64",
            Self::ContentJar => "/system/framework/content.jar",
        }
    }
    fn parse(name: &CStr) -> Result<Self> {
        if name == c"cmd" {
            Ok(Self::Cmd)
        } else if name == c"toybox" {
            Ok(Self::Toybox)
        } else if name == c"app_process64" {
            Ok(Self::AppProcess64)
        } else {
            Err(MountError::Rejected("query executable role is not fixed"))
        }
    }
    fn original_security(self, file: &File) -> Result<()> {
        match self {
            Self::Cmd => require_exact_xattr(file, c"security.selinux", CMD_ORIGINAL)?,
            Self::Toybox => require_exact_xattr(file, c"security.selinux", TOYBOX_ORIGINAL)?,
            Self::AppProcess64 => {
                require_exact_xattr(file, c"security.selinux", APP_PROCESS_ORIGINAL)?
            }
            Self::ContentJar => require_exact_xattr(file, c"security.selinux", CMD_ORIGINAL)?,
        }
        require_absent_xattr(file, c"security.capability")
    }
    pub(crate) fn mode(self) -> u32 {
        if self == Self::ContentJar {
            0o444
        } else {
            0o555
        }
    }
    pub(crate) fn private_label(self) -> &'static [u8] {
        match self {
            Self::Cmd | Self::Toybox => QUERY_EXEC,
            Self::AppProcess64 => PROVIDER_EXEC,
            Self::ContentJar => PROVIDER_JAR,
        }
    }
    fn verify_format(self, file: &File, bytes: u64, interpreter: &Option<String>) -> Result<()> {
        if self == Self::ContentJar {
            let mut magic = [0_u8; 4];
            file.read_exact_at(&mut magic, 0)?;
            require(
                interpreter.is_none() && magic == *b"PK\x03\x04",
                "Contacts classpath is not its bounded ZIP/JAR role",
            )
        } else {
            require(
                original_init_elf(file, bytes)? == *interpreter,
                "actual original query interpreter differs",
            )
        }
    }
}

/// The manifest selects one complete fixed layout. These stack-only role
/// descriptions are also consumed by the allocation-free namespace child.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum QueryLayout {
    Commands,
    Contacts,
}
impl QueryLayout {
    pub(crate) fn roles(self) -> &'static [QueryRole] {
        match self {
            Self::Commands => &[QueryRole::Cmd, QueryRole::Toybox],
            Self::Contacts => &[
                QueryRole::Cmd,
                QueryRole::Toybox,
                QueryRole::AppProcess64,
                QueryRole::ContentJar,
            ],
        }
    }
}

impl QueryDeclaration {
    pub(super) fn validate_cp3a(&self) -> Result<()> {
        require(
            self.source_system_sha256 == fixed::SYSTEM_SHA256,
            "fixed query inputs require the exact original CP3A system",
        )?;
        for (role, declared) in self.sources() {
            let fixed = role.fixed_input();
            require(
                declared.original.bytes == fixed.bytes
                    && declared.original.sha256 == fixed.sha256
                    && declared.source_path == fixed.source_path
                    && declared.original.file == fixed.output_name
                    && declared.interpreter.as_deref() == fixed.interpreter,
                "CP3A query requires each exact original code/data role",
            )?;
        }
        Ok(())
    }

    fn layout(&self) -> QueryLayout {
        if self.contacts.is_some() {
            QueryLayout::Contacts
        } else {
            QueryLayout::Commands
        }
    }

    fn sources(&self) -> Vec<(QueryRole, &QuerySource)> {
        let mut sources = vec![
            (QueryRole::Cmd, &self.cmd),
            (QueryRole::Toybox, &self.toybox),
        ];
        if let Some(contacts) = &self.contacts {
            sources.push((QueryRole::AppProcess64, &contacts.app_process64));
            sources.push((QueryRole::ContentJar, &contacts.content_jar));
        }
        sources
    }
    pub(super) fn validate_kernel_first(&self, system: &str) -> Result<()> {
        require(
            self.scope == "fixed_application_query_v1"
                && self.source_system_sha256 == system
                && system == fixed::SYSTEM_SHA256,
            "kernel-first query roles must come from the selected original CP3A system",
        )?;
        let contacts = self.contacts.as_ref().ok_or(MountError::Rejected(
            "kernel-first v2 requires all four fixed query roles",
        ))?;
        require(
            contacts.scope == "fixed_contacts_content_query_v1"
                && contacts.content_jar.interpreter.is_none()
                && self.layout() == QueryLayout::Contacts
                && self.sources().len() == 4,
            "kernel-first query layout must contain the exact commands and Contacts roles",
        )?;
        self.validate_cp3a()
    }

    pub(super) fn validate(&self, runtime: &RuntimeDeclaration) -> Result<()> {
        require(
            self.scope == "fixed_application_query_v1"
                && is_digest(&self.source_system_sha256)
                && self.source_system_sha256 == runtime.source_system.sha256,
            "query sources must bind the complete selected original system image",
        )?;
        if let Some(contacts) = &self.contacts {
            require(
                contacts.scope == "fixed_contacts_content_query_v1",
                "Contacts runtime input scope differs",
            )?;
            require(
                contacts.content_jar.interpreter.is_none(),
                "Contacts data role cannot declare an ELF interpreter",
            )?;
        }
        for (role, declared) in self.sources() {
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

fn require_private_query_label(file: &File, label: &[u8]) -> Result<()> {
    // Keep each read bounded by the exact fixed label, without turning the
    // variable-length role into a caller-sized allocation or truncated read.
    if label == QUERY_EXEC {
        require_exact_xattr(file, c"security.selinux", QUERY_EXEC)
    } else if label == PROVIDER_EXEC {
        require_exact_xattr(file, c"security.selinux", PROVIDER_EXEC)
    } else if label == PROVIDER_JAR {
        require_exact_xattr(file, c"security.selinux", PROVIDER_JAR)
    } else {
        Err(MountError::Rejected(
            "private query label is not a fixed role",
        ))
    }
}

fn label_new_inode(file: &File, label: &[u8]) -> Result<()> {
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
            label.as_ptr().cast(),
            label.len(),
            0,
        )
    })?;
    require_private_query_label(file, label)?;
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
fn readonly_private(file: &File, expected: FileIdentity, id: u64, label: &[u8]) -> Result<()> {
    readonly_mount_node(file, expected, id)?;
    require_private_query_label(file, label)?;
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
    executables: Vec<QueryExecutable>,
    layout: QueryLayout,
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
    admit: &dyn Fn(&File) -> Result<()>,
) -> Result<Copied> {
    let source = SealedFile::open_guarded(parent, role.original_name(), 0, MAX_QUERY, admit)?;
    require(
        source.identity.mode == libc::S_IFREG | role.mode(),
        "original input must be sealed with its exact executable or data mode",
    )?;
    source.verify_digest(declared.original.bytes, &declared.original.sha256)?;
    role.original_security(&source.file)?;
    role.verify_format(&source.file, declared.original.bytes, &declared.interpreter)?;
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
    label_new_inode(&copy, role.private_label())?;
    zero_rc(unsafe { libc::fchmod(copy.as_raw_fd(), role.mode()) })?;
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
        let admit = |file: &File| -> Result<()> {
            witness.identity_lease()?.broker_reject_backing_body(file)?;
            Ok(())
        };
        let revalidate = || -> Result<()> {
            witness.revalidate_live_admission()?;
            Ok(())
        };
        Self::prepare_admitted(declared, parent, userns, uids, gids, &admit, &revalidate)
    }

    // Both callers above/below obtain these closures from their actual original
    // namespace admission. This private helper never receives a public request.
    fn prepare_admitted(
        declared: &QueryDeclaration,
        parent: &Path,
        userns: &File,
        uids: IdRange,
        gids: IdRange,
        admit: &dyn Fn(&File) -> Result<()>,
        revalidate: &dyn Fn() -> Result<()>,
    ) -> Result<Self> {
        revalidate()?;
        let size = declared
            .sources()
            .iter()
            .try_fold(1024_u64 * 1024, |total, (_, source)| {
                total
                    .checked_add(source.original.bytes)
                    .ok_or(MountError::Rejected("query tmpfs size overflow"))
            })?;
        require(
            size <= 4 * MAX_QUERY + 1024 * 1024,
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
        // Creation is confined to this new private filesystem; no ordinary
        // Android tmpfs inode gains a broker relabel permission.
        for name in [c"fscontext", c"rootcontext"] {
            configure(
                &context,
                FSCONFIG_SET_STRING,
                name,
                Some(c"u:object_r:droidloom_query_tmpfs_t:s0"),
            )?;
        }
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
        let mut copied = Vec::new();
        for (role, source) in declared.sources() {
            copied.push(copy_original(role, source, parent, &root, admit)?);
        }
        label_new_inode(&root, QUERY_EXEC)?;
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
            readonly_private(&copy, identity, mount_id, copied.role.private_label())?;
            Ok(QueryExecutable {
                role: copied.role,
                source: copied.source,
                copy,
                identity,
                digest: copied.digest,
                interpreter: copied.interpreter,
            })
        };
        let executables = copied.into_iter().map(reopen).collect::<Result<Vec<_>>>()?;
        let result = Self {
            mount,
            root,
            root_identity,
            mount_id,
            executables,
            layout: declared.layout(),
            superblock_readonly: true,
        };
        result.revalidate(uids, gids)?;
        revalidate()?;
        Ok(result)
    }

    pub(super) fn revalidate(&self, uids: IdRange, gids: IdRange) -> Result<()> {
        require(
            self.executables
                .iter()
                .map(|item| item.role)
                .eq(self.layout.roles().iter().copied()),
            "query inputs differ from the complete declared layout",
        )?;
        require(
            self.superblock_readonly
                && self.root_identity.uid == uids.start
                && self.root_identity.gid == gids.start
                && self.root_identity.mode == libc::S_IFDIR | 0o555,
            "private query superblock or mapped-root custody differs",
        )?;
        readonly_mount_node(&self.mount, self.root_identity, self.mount_id)?;
        readonly_private(&self.root, self.root_identity, self.mount_id, QUERY_EXEC)?;
        require_detached(&self.mount)?;
        let names = std::fs::read_dir(format!("/proc/self/fd/{}", self.root.as_raw_fd()))?
            .take(self.executables.len() + 1)
            .map(|row| row.map(|r| r.file_name()))
            .collect::<io::Result<BTreeSet<_>>>()?;
        require(
            names
                == self
                    .executables
                    .iter()
                    .map(|item| {
                        std::ffi::OsString::from(
                            item.role.name().to_str().expect("fixed ASCII role"),
                        )
                    })
                    .collect::<BTreeSet<_>>(),
            "private query filesystem has undeclared leaves",
        )?;
        for executable in &self.executables {
            executable
                .source
                .verify_digest(executable.identity.bytes, &executable.digest)?;
            executable.role.original_security(&executable.source.file)?;
            let actual = open_leaf(&self.root, executable.role.name(), libc::O_RDONLY)?;
            readonly_private(
                &executable.copy,
                executable.identity,
                self.mount_id,
                executable.role.private_label(),
            )?;
            readonly_private(
                &actual,
                executable.identity,
                self.mount_id,
                executable.role.private_label(),
            )?;
            require(
                full_digest(&actual, executable.identity)? == executable.digest,
                "private query complete digest changed",
            )?;
        }
        Ok(())
    }

    pub(super) fn executable_file_count(&self) -> usize {
        self.executables
            .iter()
            .filter(|item| item.role != QueryRole::ContentJar)
            .count()
    }
    pub(super) fn data_file_count(&self) -> usize {
        self.executables
            .iter()
            .filter(|item| item.role == QueryRole::ContentJar)
            .count()
    }

    pub(super) fn mount(&self) -> BorrowedFd<'_> {
        self.mount.as_fd()
    }

    pub(super) fn layout(&self) -> QueryLayout {
        self.layout
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
    /// The only data role accepted by the fixed Contacts Java query. It
    /// cannot be parsed by query_executable or used as an executable binding.
    pub(crate) fn contacts_content_jar<'a>(
        &'a self,
        authority: &ApplicationAuthority<'_>,
    ) -> Result<RuntimeQueryData<'a>> {
        let resources = selected(self, authority)?;
        let executable = resources
            .executables
            .iter()
            .find(|item| item.role == QueryRole::ContentJar)
            .ok_or(MountError::Rejected("selected Contacts content JAR absent"))?;
        Ok(RuntimeQueryData {
            held: RuntimeQueryExecutable {
                runtime: self,
                resources,
                executable,
            },
        })
    }
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
        verify_original(self.executable, original, root_uid, root_gid)
    }
    pub(crate) fn verify_projection(&self, target: &File) -> Result<()> {
        verify_projection(self.resources, self.executable, target)
    }
}

fn verify_original(
    executable: &QueryExecutable,
    original: &File,
    root_uid: u32,
    root_gid: u32,
) -> Result<()> {
    let node = FileIdentity::of(&original.metadata()?);
    require(
        executable.role.original_metadata(node, root_uid, root_gid)
            && node.bytes == executable.identity.bytes
            && (node.dev, node.ino) != (executable.identity.dev, executable.identity.ino)
            && [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs_type(original)?),
        "guest original query role does not match its selected image metadata",
    )?;
    let mut flags: libc::statvfs = unsafe { std::mem::zeroed() };
    zero_rc(unsafe { libc::fstatvfs(original.as_raw_fd(), &mut flags) })?;
    require(
        flags.f_flag as u64 & READONLY_FLAGS == READONLY_FLAGS,
        "guest original query executable is not on its readonly system image",
    )?;
    executable.role.original_security(original)?;
    require(
        full_digest(original, node)? == executable.digest,
        "guest original query bytes differ from the complete selected source role",
    )?;
    executable
        .role
        .verify_format(original, node.bytes, &executable.interpreter)
}
fn verify_projection(
    resources: &QueryResources,
    executable: &QueryExecutable,
    target: &File,
) -> Result<()> {
    readonly_private(
        target,
        executable.identity,
        resources.mount_id,
        executable.role.private_label(),
    )?;
    require(
        full_digest(target, executable.identity)? == executable.digest,
        "attached private query role has different bytes",
    )
}

/// Opaque, same-owner classpath data. No path/FD/digest can construct it.
pub(crate) struct RuntimeQueryData<'a> {
    held: RuntimeQueryExecutable<'a>,
}
impl RuntimeQueryData<'_> {
    pub(crate) fn file(&self) -> &File {
        self.held.file()
    }
    pub(crate) fn revalidate(&self, authority: &ApplicationAuthority<'_>) -> Result<()> {
        self.held.revalidate(authority)
    }
    pub(crate) fn verify_original(&self, file: &File, uid: u32, gid: u32) -> Result<()> {
        self.held.verify_original(file, uid, gid)
    }
    pub(crate) fn verify_projection(&self, file: &File) -> Result<()> {
        self.held.verify_projection(file)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cp3a_query_original_metadata_retains_shell_group_and_nonexecutable_jar() {
        let file = tempfile::tempfile().unwrap();
        let root_uid = 200_000;
        let root_gid = 300_000;
        for role in QueryLayout::Contacts.roles() {
            let fixed = role.fixed_input();
            let mut node = FileIdentity::of(&file.metadata().unwrap());
            node.mode = fixed.original_mode;
            node.uid = root_uid;
            node.gid = root_gid + fixed.original_gid;
            node.bytes = fixed.bytes;
            node.links = 1;
            assert!(role.original_metadata(node, root_uid, root_gid));
            let mut wrong = node;
            wrong.gid = if fixed.original_gid == 0 {
                root_gid + 2000
            } else {
                root_gid
            };
            assert!(!role.original_metadata(wrong, root_uid, root_gid));
            wrong = node;
            wrong.mode ^= 0o111;
            assert!(!role.original_metadata(wrong, root_uid, root_gid));
            wrong = node;
            wrong.mode |= 0o4000;
            assert!(!role.original_metadata(wrong, root_uid, root_gid));
            wrong = node;
            wrong.links = 2;
            assert!(!role.original_metadata(wrong, root_uid, root_gid));
            wrong = node;
            wrong.bytes += 1;
            assert!(!role.original_metadata(wrong, root_uid, root_gid));
            assert!(!role.original_metadata(node, root_uid, u32::MAX));
        }
    }

    #[test]
    fn cp3a_query_declaration_rejects_code_role_and_interpreter_substitution() {
        let source = |role: QueryRole| {
            let fixed = role.fixed_input();
            serde_json::json!({"original":{"file":fixed.output_name,"bytes":fixed.bytes,"sha256":fixed.sha256},
                "source_path":fixed.source_path,"interpreter":fixed.interpreter})
        };
        let value = serde_json::json!({"scope":"fixed_application_query_v1",
            "source_system_sha256":fixed::SYSTEM_SHA256,
            "cmd":source(QueryRole::Cmd),"toybox":source(QueryRole::Toybox),
            "contacts":{"scope":"fixed_contacts_content_query_v1",
                "app_process64":source(QueryRole::AppProcess64),"content_jar":source(QueryRole::ContentJar)}});
        serde_json::from_value::<QueryDeclaration>(value.clone())
            .unwrap()
            .validate_cp3a()
            .unwrap();
        for path in [
            "/cmd/original/sha256",
            "/toybox/original/sha256",
            "/contacts/app_process64/original/sha256",
            "/contacts/content_jar/original/sha256",
            "/source_system_sha256",
        ] {
            let mut changed = value.clone();
            *changed.pointer_mut(path).unwrap() = serde_json::json!("0".repeat(64));
            assert!(
                serde_json::from_value::<QueryDeclaration>(changed)
                    .unwrap()
                    .validate_cp3a()
                    .is_err()
            );
        }
        for path in ["/cmd/interpreter", "/contacts/content_jar/interpreter"] {
            let mut changed = value.clone();
            *changed.pointer_mut(path).unwrap() =
                serde_json::json!("/system/bin/bootstrap/linker64");
            assert!(
                serde_json::from_value::<QueryDeclaration>(changed)
                    .unwrap()
                    .validate_cp3a()
                    .is_err()
            );
        }
        let mut changed = value;
        changed["cmd"]["source_path"] = serde_json::json!("/system/bin/toybox");
        assert!(
            serde_json::from_value::<QueryDeclaration>(changed)
                .unwrap()
                .validate_cp3a()
                .is_err()
        );
    }

    #[test]
    fn contacts_classpath_is_nonexecutable_and_its_separate_label_cannot_select_a_binary() {
        assert!(QueryRole::parse(c"content.jar").is_err());
        assert!(QueryRole::parse(c"app_process").is_err());
        assert!(QueryRole::parse(c"/system/bin/app_process64").is_err());
        assert_eq!(
            QueryRole::parse(c"app_process64").unwrap(),
            QueryRole::AppProcess64
        );
        assert_eq!(QueryRole::ContentJar.mode(), 0o444);
        assert_ne!(
            QueryRole::ContentJar.private_label(),
            QueryRole::Cmd.private_label()
        );
        assert_ne!(
            QueryRole::AppProcess64.private_label(),
            QueryRole::Cmd.private_label()
        );
        let file = tempfile::tempfile().unwrap();
        file.write_all_at(&[0_u8; 64], 0).unwrap();
        assert!(
            QueryRole::ContentJar
                .verify_format(&file, 64, &None)
                .is_err()
        );
        file.write_all_at(b"PK\x03\x04", 0).unwrap();
        QueryRole::ContentJar
            .verify_format(&file, 64, &None)
            .unwrap();
        assert!(
            QueryRole::ContentJar
                .verify_format(&file, 64, &Some("/system/bin/linker64".into()))
                .is_err()
        );
        assert!(
            QueryRole::AppProcess64
                .verify_format(&file, 64, &None)
                .is_err()
        );
    }
}
