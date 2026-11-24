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
const MAXIMUM: u64 = 128 * 1024 * 1024;

#[derive(Clone, Copy, PartialEq, Eq)]
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

pub(super) fn verify(
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
        b"app_process64" if query.needs_content_jar() => 2,
        _ => return Err(reject("unknown fixed query executable role")),
    }];
    let original_label = original_input.original_label;
    let private_label = if query.needs_content_jar() {
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
}
