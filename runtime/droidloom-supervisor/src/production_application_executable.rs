//! Fresh-worker verification of the two fixed original/private query roles.
//! The private executable must be a different, sealed tmpfs inode containing
//! the complete bytes of its actual selected system counterpart. Only fixed
//! root-relative components are opened; no packet supplies a binary pathname.
use super::*;
use crate::production_execution_profile::query_inputs as fixed;
use sha2::{Digest, Sha256};
use std::os::unix::fs::FileExt;

const QUERY_LABEL: &[u8] = b"u:object_r:droidloom_query_exec:s0\0";
const PROVIDER_LABEL: &[u8] = b"u:object_r:droidloom_provider_exec:s0\0";
const JAR_LABEL: &[u8] = b"u:object_r:droidloom_provider_jar:s0\0";
const CATALOG_LABEL: &[u8] = b"u:object_r:droidloom_input_bridge_jar:s0\0";
const MAXIMUM: u64 = 128 * 1024 * 1024;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Node {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
}
fn identity(file: &File) -> Result<Node> {
    let m = file.metadata()?;
    Ok(Node {
        dev: m.dev(),
        ino: m.ino(),
        mode: m.mode(),
        uid: m.uid(),
        gid: m.gid(),
        links: m.nlink(),
        bytes: m.len(),
        mtime: (m.mtime(), m.mtime_nsec()),
        ctime: (m.ctime(), m.ctime_nsec()),
    })
}
fn at(root: &File, path: &[&CStr]) -> Result<File> {
    let mut file = root.try_clone()?;
    for (i, component) in path.iter().enumerate() {
        let raw = unsafe {
            libc::openat(
                file.as_raw_fd(),
                component.as_ptr(),
                libc::O_CLOEXEC
                    | libc::O_NOFOLLOW
                    | libc::O_NONBLOCK
                    | if i + 1 < path.len() {
                        libc::O_PATH | libc::O_DIRECTORY
                    } else {
                        libc::O_RDONLY
                    },
            )
        };
        if raw < 0 {
            return Err(io::Error::last_os_error().into());
        }
        file = unsafe { File::from_raw_fd(raw) };
    }
    Ok(file)
}
fn readonly(file: &File, private: bool) -> Result<()> {
    let mut fs: libc::statfs = unsafe { mem::zeroed() };
    let mut flags: libc::statvfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0
        || unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        if private {
            fs.f_type == 0x0102_1994
        } else {
            [0xef53, 0xe0f5_e1e2_u32 as libc::c_long].contains(&fs.f_type)
        },
        "query executable role came from another filesystem",
    )?;
    require(
        flags.f_flag & 7 == 7 && flags.f_flag & 8 == 0,
        "query executable role is not readonly nosuid nodev and executable",
    )?;
    let access = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    if access < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        access & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY,
        "query executable descriptor is not a readonly body",
    )
}
fn security(file: &File, expected: &[u8]) -> Result<()> {
    let mut label = [0_u8; 128];
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            label.as_mut_ptr().cast(),
            label.len(),
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        &label[..count as usize] == expected,
        "fixed query executable security label differs",
    )?;
    let count = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.capability".as_ptr(),
            std::ptr::null_mut(),
            0,
        )
    };
    require(
        count == -1 && io::Error::last_os_error().raw_os_error() == Some(libc::ENODATA),
        "query executable must have no file capability xattr",
    )
}
fn complete_hash(file: &File, expected: Node, deadline: Instant) -> Result<[u8; 32]> {
    require(
        identity(file)? == expected && (64..=MAXIMUM).contains(&expected.bytes),
        "query executable source changed before hash",
    )?;
    let mut hash = Sha256::new();
    let mut at = 0_u64;
    let mut bytes = [0_u8; 32 * 1024];
    while at < expected.bytes {
        require(
            Instant::now() < deadline,
            "query executable verification deadline",
        )?;
        let length = (expected.bytes - at).min(bytes.len() as u64) as usize;
        let count = match file.read_at(&mut bytes[..length], at) {
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            result => result?,
        };
        require(count != 0, "short original query executable")?;
        hash.update(&bytes[..count]);
        at += count as u64;
    }
    require(
        file.read_at(&mut bytes[..1], at)? == 0 && identity(file)? == expected,
        "query executable changed during complete hash",
    )?;
    Ok(hash.finalize().into())
}

fn original_metadata(node: Node, input: fixed::FixedQueryInput, uid: u32, gid: u32) -> bool {
    node.mode == input.original_mode
        && node.uid == uid
        && gid.checked_add(input.original_gid) == Some(node.gid)
        && node.links == 1
        && node.bytes == input.bytes
}

fn private_role(root: &File, projection: QueryProjection, leaf: &CStr) -> Result<File> {
    match projection {
        QueryProjection::LegacyRoot => at(root, &[c".droidloom-query", leaf]),
        QueryProjection::EarlyDev => at(root, &[c"dev", c"droidloom-query", leaf]),
    }
}

pub(in crate::production_application) fn verify(
    files: &[File],
    query: &ApplicationOperation,
    projection: QueryProjection,
    root_uid: u32,
    root_gid: u32,
    deadline: Instant,
) -> Result<()> {
    let original_input = fixed::INPUTS[match query.binary().to_bytes() {
        b"cmd" => 0,
        b"toybox" => 1,
        b"app_process64" if query.uses_app_process() => 2,
        _ => return Err(reject("unknown fixed query executable role")),
    }];
    let original_label = original_input.original_label;
    let private_label = if query.uses_app_process() {
        PROVIDER_LABEL
    } else {
        QUERY_LABEL
    };
    let original = at(&files[2], &[c"system", c"bin", query.binary()])?;
    let private = private_role(&files[2], projection, query.binary())?;
    let source = identity(&original)?;
    let copy = identity(&private)?;
    require(
        source == identity(&files[protocol::ORIGINAL_EXECUTABLE])?
            && copy == identity(&files[protocol::EXECUTABLE])?
            && (source.dev, source.ino) != (copy.dev, copy.ino)
            && source.bytes == copy.bytes,
        "query executable descriptors are not distinct fixed original/private roles",
    )?;
    require(
        original_metadata(source, original_input, root_uid, root_gid)
            && copy.mode == libc::S_IFREG | 0o555
            && copy.uid == root_uid
            && copy.gid == root_gid
            && copy.links == 1,
        "original or private query executable custody differs",
    )?;
    readonly(&original, false)?;
    readonly(&private, true)?;
    readonly(&files[protocol::ORIGINAL_EXECUTABLE], false)?;
    readonly(&files[protocol::EXECUTABLE], true)?;
    security(&original, original_label)?;
    security(&private, private_label)?;
    require(
        complete_hash(&original, source, deadline)? == complete_hash(&private, copy, deadline)?,
        "private query executable is not byte-identical to the actual original system role",
    )?;
    require(
        identity(&original)? == source && identity(&private)? == copy,
        "query executable generation changed during verification",
    )?;
    security(&original, original_label)?;
    security(&private, private_label)?;
    if query.needs_content_jar() {
        verify_content_jar(files, projection, root_uid, root_gid, deadline)?;
    }
    if let Some(digest) = query.catalog_jar_digest() {
        require(
            projection == QueryProjection::EarlyDev,
            "catalog requires the selected early cohort",
        )?;
        bind_catalog(&files[2], digest, root_uid, root_gid, deadline)?;
    }
    require(
        Instant::now() < deadline,
        "fixed input verification deadline",
    )
}

fn verify_content_jar(
    files: &[File],
    projection: QueryProjection,
    uid: u32,
    gid: u32,
    deadline: Instant,
) -> Result<()> {
    let original = at(&files[2], &[c"system", c"framework", c"content.jar"])?;
    let private = private_role(&files[2], projection, c"content.jar")?;
    let source = identity(&original)?;
    let copy = identity(&private)?;
    require(
        source == identity(&files[protocol::ORIGINAL_CONTENT_JAR])?
            && copy == identity(&files[protocol::CONTENT_JAR])?
            && (source.dev, source.ino) != (copy.dev, copy.ino)
            && source.bytes == copy.bytes
            && original_metadata(source, fixed::INPUTS[3], uid, gid)
            && copy.mode == libc::S_IFREG | 0o444
            && copy.uid == uid
            && copy.gid == gid
            && copy.links == 1,
        "fixed Contacts classpath is not the original and distinct owned readonly copy",
    )?;
    for file in [&original, &files[protocol::ORIGINAL_CONTENT_JAR]] {
        readonly(file, false)?;
    }
    for file in [&private, &files[protocol::CONTENT_JAR]] {
        readonly(file, true)?;
    }
    let label = b"u:object_r:system_file:s0\0";
    security(&original, label)?;
    security(&private, JAR_LABEL)?;
    let mut magic = [0_u8; 4];
    private.read_exact_at(&mut magic, 0)?;
    require(
        magic == *b"PK\x03\x04",
        "fixed Contacts classpath is not a ZIP/JAR",
    )?;
    require(
        complete_hash(&original, source, deadline)? == complete_hash(&private, copy, deadline)?,
        "Contacts classpath bytes differ from the complete selected original",
    )?;
    require(
        identity(&original)? == source && identity(&private)? == copy,
        "Contacts classpath changed during verification",
    )?;
    security(&original, label)?;
    security(&private, JAR_LABEL)?;
    require(
        Instant::now() < deadline,
        "Contacts classpath verification deadline",
    )
}

/// The factory owns these original file descriptions for the full app_process
/// lifetime. None is sent to Android or read by the broker. The native child
/// closes all non-admitted descriptions before its fixed exec.
pub(in crate::production_application) struct ArtInputs {
    root: File,
    root_node: (u64, u64),
    root_mount: u64,
    inputs: Vec<ArtInput>,
    uid: u32,
    gid: u32,
}
struct ArtInput {
    file: File,
    node: Node,
    mount: u64,
}
fn art_mount(file: &File) -> Result<u64> {
    let mut st: libc::statx = unsafe { mem::zeroed() };
    if unsafe {
        libc::statx(
            file.as_raw_fd(),
            c"".as_ptr(),
            libc::AT_EMPTY_PATH | libc::AT_SYMLINK_NOFOLLOW,
            libc::STATX_MNT_ID,
            &mut st,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        st.stx_mask & libc::STATX_MNT_ID != 0 && st.stx_mnt_id > 0,
        "original ART input has no actual mount identity",
    )?;
    Ok(st.stx_mnt_id)
}
fn art_metadata(
    node: Node,
    input: &crate::production_application::art_profile::ArtJar,
    uid: u32,
    gid: u32,
) -> bool {
    node.mode == libc::S_IFREG | 0o644
        && uid.checked_add(input.original_uid) == Some(node.uid)
        && gid.checked_add(input.original_gid) == Some(node.gid)
        && node.links == 1
        && node.bytes == input.bytes
}

fn art_mount_contract(
    input: &crate::production_application::art_profile::ArtJar,
    filesystem: libc::c_long,
    flags: libc::c_ulong,
    access: i32,
) -> bool {
    // The original apexd.cpp mounts RDONLY|NODEV|NOATIME|DIRSYNC, without
    // NOSUID; nocode modules additionally use NOEXEC. These are data-only
    // JAR reads, not native executable admission. The actual fixed 0644 mode
    // and absent capability xattr are verified independently.
    filesystem == input.original_filesystem
        && flags & 5 == 5
        && (!input.path.starts_with("/system/") || flags & 2 == 2)
        && access >= 0
        && access & (libc::O_ACCMODE | libc::O_PATH) == libc::O_RDONLY
}
fn readonly_art(
    file: &File,
    input: &crate::production_application::art_profile::ArtJar,
) -> Result<()> {
    let mut fs: libc::statfs = unsafe { mem::zeroed() };
    let mut flags: libc::statvfs = unsafe { mem::zeroed() };
    if unsafe { libc::fstatfs(file.as_raw_fd(), &mut fs) } != 0
        || unsafe { libc::fstatvfs(file.as_raw_fd(), &mut flags) } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    let access = unsafe { libc::fcntl(file.as_raw_fd(), libc::F_GETFL) };
    require(
        art_mount_contract(input, fs.f_type, flags.f_flag, access),
        "ART JAR is not its original readonly nodev filesystem and readonly description",
    )
}

fn verify_art(
    file: &File,
    node: Node,
    input: &crate::production_application::art_profile::ArtJar,
    uid: u32,
    gid: u32,
    deadline: Instant,
) -> Result<()> {
    require(
        Instant::now() < deadline && art_metadata(node, input, uid, gid),
        "fixed ART input ownership, links, size, mode or deadline differs",
    )?;
    readonly_art(file, input)?;
    security(file, input.original_label)?;
    let mut magic = [0_u8; 4];
    file.read_exact_at(&mut magic, 0)?;
    require(magic == *b"PK\x03\x04", "fixed ART input is not a ZIP/JAR")?;
    require(
        complete_hash(file, node, deadline)? == input.sha256,
        "complete ART JAR differs from its original selected CP3A bytes",
    )?;
    require(
        identity(file)? == node && Instant::now() < deadline,
        "original ART input changed during verification",
    )?;
    readonly_art(file, input)?;
    security(file, input.original_label)?;
    Ok(())
}
impl ArtInputs {
    pub(in crate::production_application) fn revalidate(&self, deadline: Instant) -> Result<()> {
        let root = self.root.metadata()?;
        require(
            Instant::now() < deadline
                && (root.dev(), root.ino()) == self.root_node
                && art_mount(&self.root)? == self.root_mount
                && self.inputs.len() == crate::production_application::art_profile::INPUTS.len(),
            "original ART root or complete input set changed",
        )?;
        for (held, input) in self
            .inputs
            .iter()
            .zip(&crate::production_application::art_profile::INPUTS)
        {
            require(Instant::now() < deadline, "original ART input deadline")?;
            let current = at(&self.root, input.components)?;
            require(
                identity(&held.file)? == held.node
                    && art_mount(&held.file)? == held.mount
                    && identity(&current)? == held.node
                    && art_mount(&current)? == held.mount,
                "fixed ART path no longer names its retained original inode and mount",
            )?;
            verify_art(&held.file, held.node, input, self.uid, self.gid, deadline)?;
            require(
                identity(&current)? == held.node && art_mount(&current)? == held.mount,
                "fixed ART input path changed during complete revalidation",
            )?;
        }
        require(Instant::now() < deadline, "original ART input deadline")
    }
}
pub(in crate::production_application) fn bind_art(
    root: &File,
    uid: u32,
    gid: u32,
    deadline: Instant,
) -> Result<ArtInputs> {
    require(
        crate::production_application::art_profile::consistent(),
        "ART environment is not the complete selected CP3A input profile",
    )?;
    let root = root.try_clone()?;
    let metadata = root.metadata()?;
    require(metadata.is_dir(), "original ART root is not a directory")?;
    let root_node = (metadata.dev(), metadata.ino());
    let root_mount = art_mount(&root)?;
    let mut inputs = Vec::with_capacity(crate::production_application::art_profile::INPUTS.len());
    for input in &crate::production_application::art_profile::INPUTS {
        require(Instant::now() < deadline, "original ART input deadline")?;
        // Every component is compiled into the fixed profile. Intermediate
        // directories are O_PATH and symlinks are never followed.
        let file = at(&root, input.components)?;
        let node = identity(&file)?;
        let mount = art_mount(&file)?;
        verify_art(&file, node, input, uid, gid, deadline)?;
        require(art_mount(&file)? == mount, "original ART mount changed")?;
        inputs.push(ArtInput { file, node, mount });
    }
    Ok(ArtInputs {
        root,
        root_node,
        root_mount,
        inputs,
        uid,
        gid,
    })
}

/// Retain the actual fixed normal-JAR inode for the complete query lifetime.
pub(in crate::production_application) struct CatalogJar {
    file: File,
    node: Node,
}
impl CatalogJar {
    pub(in crate::production_application) fn revalidate(
        &self,
        root: &File,
        digest: &str,
        uid: u32,
        gid: u32,
        deadline: Instant,
    ) -> Result<()> {
        let current = bind_catalog(root, digest, uid, gid, deadline)?;
        require(
            identity(&self.file)? == self.node && current.node == self.node,
            "catalog normal JAR path no longer names the retained original inode",
        )
    }
}
pub(in crate::production_application) fn bind_catalog(
    root: &File,
    digest: &str,
    uid: u32,
    gid: u32,
    deadline: Instant,
) -> Result<CatalogJar> {
    require(
        digest.len() == 64
            && digest
                .bytes()
                .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "catalog normal JAR digest shape differs",
    )?;
    // This is READINESS_TARGETS[2], without following the /system_ext alias.
    let file = at(
        root,
        &[
            c"system",
            c"system_ext",
            c"framework",
            c"droidloom-input-bridge.jar",
        ],
    )?;
    let node = identity(&file)?;
    require(
        node.mode == libc::S_IFREG | 0o644
            && node.uid == uid
            && node.gid == gid
            && node.links == 1
            && (64..=MAXIMUM).contains(&node.bytes),
        "catalog normal JAR ownership, mode, links or size differs",
    )?;
    readonly(&file, false)?;
    security(&file, CATALOG_LABEL)?;
    let mut magic = [0_u8; 4];
    file.read_exact_at(&mut magic, 0)?;
    require(
        magic == *b"PK\x03\x04",
        "catalog normal JAR is not a ZIP/JAR",
    )?;
    let actual = complete_hash(&file, node, deadline)?
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect::<String>();
    require(
        actual == digest,
        "catalog whole JAR does not match the selected normal cohort",
    )?;
    require(
        identity(&file)? == node,
        "catalog normal JAR changed while binding",
    )?;
    readonly(&file, false)?;
    security(&file, CATALOG_LABEL)?;
    Ok(CatalogJar { file, node })
}

#[cfg(test)]
mod metadata_tests {
    use super::*;
    #[test]
    fn worker_uses_the_original_shell_group_instead_of_private_root_ownership() {
        let fixed = crate::production_execution_profile::query_inputs::INPUTS;
        let file = tempfile::tempfile().unwrap();
        for input in fixed {
            let mut original = identity(&file).unwrap();
            original.mode = input.original_mode;
            original.uid = 200_000;
            original.gid = 300_000 + input.original_gid;
            original.links = 1;
            original.bytes = input.bytes;
            assert!(original_metadata(original, input, 200_000, 300_000));
            let mut wrong = original;
            wrong.gid = if input.original_gid == 0 {
                302_000
            } else {
                300_000
            };
            assert!(!original_metadata(wrong, input, 200_000, 300_000));
            wrong = original;
            wrong.mode ^= 0o111;
            assert!(!original_metadata(wrong, input, 200_000, 300_000));
            assert!(!original_metadata(original, input, 200_000, u32::MAX));
        }
    }
    #[test]
    fn fixed_art_metadata_keeps_original_system_and_root_owners_and_rejects_drift() {
        let file = tempfile::tempfile().unwrap();
        for input in &crate::production_application::art_profile::INPUTS {
            let mut original = identity(&file).unwrap();
            original.mode = libc::S_IFREG | 0o644;
            original.uid = 200_000 + input.original_uid;
            original.gid = 300_000 + input.original_gid;
            original.links = 1;
            original.bytes = input.bytes;
            assert!(art_metadata(original, input, 200_000, 300_000));
            let mut wrong = original;
            wrong.uid += 1;
            assert!(!art_metadata(wrong, input, 200_000, 300_000));
            wrong = original;
            wrong.gid += 1;
            assert!(!art_metadata(wrong, input, 200_000, 300_000));
            wrong = original;
            wrong.mode |= 0o111;
            assert!(!art_metadata(wrong, input, 200_000, 300_000));
            wrong = original;
            wrong.links = 2;
            assert!(!art_metadata(wrong, input, 200_000, 300_000));
            wrong = original;
            wrong.bytes += 1;
            assert!(!art_metadata(wrong, input, 200_000, 300_000));
            assert!(!art_metadata(original, input, u32::MAX, u32::MAX));
        }
    }

    #[test]
    fn original_art_handles_detect_replaced_or_symlinked_fixed_paths() {
        use std::io::Write;
        let root = tempfile::tempdir().unwrap();
        let input = &crate::production_application::art_profile::INPUTS[0];
        let path = root.path().join(input.path.trim_start_matches('/'));
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        let mut first = File::create(&path).unwrap();
        first.write_all(&[7_u8; 64]).unwrap();
        let directory = File::open(root.path()).unwrap();
        let retained = at(&directory, input.components).unwrap();
        let original = identity(&retained).unwrap();
        let original_mount = art_mount(&retained).unwrap();
        std::fs::rename(&path, path.with_extension("retained")).unwrap();
        std::fs::write(&path, [7_u8; 64]).unwrap();
        let replacement = at(&directory, input.components).unwrap();
        assert_eq!(art_mount(&replacement).unwrap(), original_mount);
        assert_ne!(identity(&replacement).unwrap().ino, original.ino);
        let held = identity(&retained).unwrap();
        assert_eq!(
            (held.dev, held.ino, held.bytes),
            (original.dev, original.ino, original.bytes)
        );
        std::fs::remove_file(&path).unwrap();
        std::os::unix::fs::symlink(path.with_extension("retained"), &path).unwrap();
        assert!(at(&directory, input.components).is_err());
    }

    #[test]
    fn complete_art_hash_checks_the_last_byte_and_the_original_deadline() {
        use std::io::Write;
        let mut file = tempfile::tempfile().unwrap();
        let mut original = vec![0_u8; 70_001];
        original[..4].copy_from_slice(b"PK\x03\x04");
        file.write_all(&original).unwrap();
        let deadline = Instant::now() + std::time::Duration::from_secs(2);
        let before = identity(&file).unwrap();
        let digest = complete_hash(&file, before, deadline).unwrap();
        assert_eq!(digest, <[u8; 32]>::from(Sha256::digest(&original)));
        assert!(complete_hash(&file, before, Instant::now()).is_err());
        file.write_all_at(&[1_u8], original.len() as u64 - 1)
            .unwrap();
        let current = identity(&file).unwrap();
        assert_ne!(complete_hash(&file, current, deadline).unwrap(), digest);
        assert!(complete_hash(&file, before, deadline).is_err());
    }
    #[test]
    fn original_art_mount_contract_matches_stock_apex_flags_without_weakening_elf_roles() {
        let inputs = &crate::production_application::art_profile::INPUTS;
        let apex = inputs
            .iter()
            .find(|i| i.path.starts_with("/apex/") && i.original_filesystem == 0xef53)
            .unwrap();
        let system = inputs
            .iter()
            .find(|i| i.path.starts_with("/system/"))
            .unwrap();
        let virt = inputs
            .iter()
            .find(|i| i.original_filesystem != 0xef53)
            .unwrap();
        assert!(art_mount_contract(apex, 0xef53, 5, libc::O_RDONLY));
        assert!(art_mount_contract(apex, 0xef53, 5 | 8, libc::O_RDONLY));
        assert!(art_mount_contract(system, 0xef53, 7, libc::O_RDONLY));
        assert!(!art_mount_contract(system, 0xef53, 5, libc::O_RDONLY));
        assert!(art_mount_contract(
            virt,
            0xe0f5_e1e2_u32 as libc::c_long,
            5,
            libc::O_RDONLY
        ));
        for invalid in [0, 1, 4, 8] {
            assert!(!art_mount_contract(apex, 0xef53, invalid, libc::O_RDONLY));
        }
        for invalid in [libc::O_WRONLY, libc::O_RDWR, libc::O_PATH, -1] {
            assert!(!art_mount_contract(apex, 0xef53, 5, invalid));
        }
        assert!(!art_mount_contract(apex, 0x0102_1994, 5, libc::O_RDONLY));
        assert!(!art_mount_contract(virt, 0xef53, 5, libc::O_RDONLY));
    }
}
