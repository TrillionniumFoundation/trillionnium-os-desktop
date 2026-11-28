//! Explicit SELinux self observation and closed pre-exec selection on x86-64 Linux 6.18.
//! Neither path depends on legacy proc LSM ordering, a guest mount, supplied
//! PID/context, libselinux or an installation record. Foreign tasks require a
//! separately held, explicitly selected proc view; SELF is never their witness.
use super::{Result, require};
use std::io;
const SELINUX_ID: u64 = 101;
const SINGLE: u32 = 1;
const GET_SELF_ATTR: libc::c_long = 459;
const SET_SELF_ATTR: libc::c_long = 460;
#[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
compile_error!("typed production MAC self observation requires selected x86-64 Linux UAPI");
#[repr(C)]
struct Context {
    id: u64,
    flags: u64,
    len: u64,
    ctx_len: u64,
    ctx: [u8; 1024],
}
impl Context {
    const fn empty() -> Self {
        Self {
            id: SELINUX_ID,
            flags: 0,
            len: 0,
            ctx_len: 0,
            ctx: [0; 1024],
        }
    }
}
const _: () =
    assert!(std::mem::size_of::<Context>() == 1056 && std::mem::align_of::<Context>() == 8);
#[derive(Clone, Copy)]
enum Attribute {
    Current,
    Exec,
    FsCreate,
}
impl Attribute {
    fn value(self) -> u32 {
        match self {
            Self::Current => 100,
            Self::Exec => 101,
            Self::FsCreate => 102,
        }
    }
}
fn record_body(
    raw: &Context,
    count: libc::c_long,
    size: u32,
    attribute: Attribute,
) -> Option<&[u8]> {
    if count != 1 || raw.id != SELINUX_ID || raw.flags != 0 || raw.ctx_len > raw.ctx.len() as u64 {
        return None;
    }
    let length = raw.ctx_len as usize;
    let aligned = (32 + length + 7) & !7;
    if raw.len != aligned as u64
        || size as usize != aligned
        || aligned > std::mem::size_of::<Context>()
        || raw.ctx[length..aligned - 32].iter().any(|b| *b != 0)
    {
        return None;
    }
    if length == 0 {
        if !matches!(attribute, Attribute::Exec | Attribute::FsCreate) || size != 32 {
            return None;
        }
    } else if raw.ctx[length - 1] != 0
        || raw.ctx[..length - 1].contains(&0)
        || std::str::from_utf8(&raw.ctx[..length - 1]).is_err()
    {
        return None;
    }
    Some(&raw.ctx[..length])
}
fn decode(raw: &Context, count: libc::c_long, size: u32, attribute: Attribute) -> Result<Vec<u8>> {
    record_body(raw, count, size, attribute)
        .map(<[u8]>::to_vec)
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "incomplete or noncanonical explicit SELinux self record",
            )
            .into()
        })
}
fn observe(attribute: Attribute) -> Result<Vec<u8>> {
    let mut raw = Context::empty();
    let mut size = std::mem::size_of::<Context>() as u32;
    let tid = unsafe { libc::syscall(libc::SYS_gettid) };
    require(tid > 0, "actual calling thread identity")?;
    let count = unsafe {
        libc::syscall(
            GET_SELF_ATTR,
            attribute.value(),
            &mut raw,
            &mut size,
            SINGLE,
        )
    };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        unsafe { libc::syscall(libc::SYS_gettid) } == tid,
        "typed context remains on original calling thread",
    )?;
    decode(&raw, count, size, attribute)
}
/// A successful CURRENT contains exactly one final NUL, as returned by SELinux.
pub(crate) fn selinux_current() -> Result<Vec<u8>> {
    observe(Attribute::Current)
}
/// An unset EXEC is the one complete empty kernel record, never a missing provider.
pub(crate) fn selinux_exec() -> Result<Vec<u8>> {
    observe(Attribute::Exec)
}
pub(super) fn require_no_fscreate() -> Result<()> {
    require(
        observe(Attribute::FsCreate)?.is_empty(),
        "inherited SELinux fscreate override is present",
    )
}

/// Only reviewed source roles can select a next image. No context or origin
/// string, numeric role, arbitrary attribute, or foreign PID is accepted.
#[derive(Clone, Copy)]
pub(crate) enum ExecTarget {
    QueryIo,
    MetadataObserver,
    EngineObserver,
    NativeCamera,
    NativeLeafApkReader,
    WorkingApkPayloadCreator,
    WorkingOriginalPayloadBirth,
    WorkingPreparation,
    WorkingApplication,
}
impl ExecTarget {
    fn contexts(self) -> (&'static [u8], &'static [u8]) {
        let broker = b"u:r:droidloom_broker:s0\0".as_slice();
        let working = b"u:system_r:p4_linux_working_qualification_t:s0\0".as_slice();
        match self {
            Self::QueryIo => (broker, b"u:r:droidloom_query_io:s0\0"),
            Self::MetadataObserver => (broker, b"u:r:droidloom_metadata_observer:s0\0"),
            Self::EngineObserver => (broker, b"u:r:droidloom_engine_observer:s0\0"),
            Self::NativeCamera => (broker, b"u:r:droidloom_camera_capture:s0\0"),
            Self::NativeLeafApkReader => (broker, b"u:r:droidloom_native_leaf_apk_reader:s0\0"),
            Self::WorkingApkPayloadCreator => (broker, b"u:r:droidloom_working_apk_payload_creator:s0\0"),
            Self::WorkingOriginalPayloadBirth => (
                b"u:system_r:p4_linux_working_privateprep_t:s0\0",
                b"u:system_r:p4_linux_working_payload_birth_t:s0\0",
            ),
            Self::WorkingPreparation => {
                (working, b"u:system_r:p4_linux_working_privateprep_t:s0\0")
            }
            Self::WorkingApplication => {
                (working, b"u:system_r:p4_linux_working_application_t:s0\0")
            }
        }
    }
}
unsafe fn raw_matches(attribute: Attribute, expected: &[u8]) -> bool {
    let mut raw = Context::empty();
    let mut size = std::mem::size_of::<Context>() as u32;
    let tid = unsafe { libc::syscall(libc::SYS_gettid) };
    if tid <= 0 {
        return false;
    }
    let count = unsafe {
        libc::syscall(
            GET_SELF_ATTR,
            attribute.value(),
            &mut raw,
            &mut size,
            SINGLE,
        )
    };
    count >= 0
        && unsafe { libc::syscall(libc::SYS_gettid) } == tid
        && record_body(&raw, count, size, attribute) == Some(expected)
}
/// Allocation-free fixed SELF bookend after the working owner's AppArmor EXEC
/// selection. This cannot inspect a foreign process or accept a caller SID.
pub(crate) unsafe fn working_parent_current() -> bool {
    unsafe { raw_matches(Attribute::Current, b"u:system_r:p4_linux_working_qualification_t:s0\0") }
}
/// Allocation-free, fixed-label bootstrap for an already owned child.
/// The caller retains its original end, ELF, PIDFD, credentials and AppArmor
/// checks, calls this before installing seccomp, and exits on false. This
/// function cannot change CURRENT or grant a foreign task observation.
pub(crate) unsafe fn prepare_selinux_exec(target: ExecTarget) -> bool {
    let (origin, expected) = target.contexts();
    let tid = unsafe { libc::syscall(libc::SYS_gettid) };
    if tid <= 0
        || !unsafe { raw_matches(Attribute::Current, origin) }
        || !unsafe { raw_matches(Attribute::Exec, b"") }
    {
        return false;
    }
    let mut raw = Context::empty();
    raw.len = (32 + expected.len()) as u64;
    raw.ctx_len = expected.len() as u64;
    raw.ctx[..expected.len()].copy_from_slice(expected);
    unsafe {
        libc::syscall(
            SET_SELF_ATTR,
            Attribute::Exec.value(),
            &raw,
            raw.len as u32,
            0_u32,
        ) == 0
            && libc::syscall(libc::SYS_gettid) == tid
            && raw_matches(Attribute::Current, origin)
            && raw_matches(Attribute::Exec, expected)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn record(body: &[u8]) -> (Context, u32) {
        let length = (32 + body.len() + 7) & !7;
        let mut c = Context {
            id: 101,
            flags: 0,
            len: length as u64,
            ctx_len: body.len() as u64,
            ctx: [0; 1024],
        };
        c.ctx[..body.len()].copy_from_slice(body);
        (c, length as u32)
    }
    #[test]
    fn empty_fscreate_is_one_complete_header() {
        let (c, n) = record(b"");
        assert!(decode(&c, 1, n, Attribute::FsCreate).unwrap().is_empty());
        assert!(decode(&c, 0, n, Attribute::FsCreate).is_err());
        assert!(decode(&c, 1, n, Attribute::Current).is_err());
    }
    #[test]
    fn another_provider_and_nonzero_flags_are_rejected() {
        let (mut c, n) = record(b"u:r:droidloom_broker:s0\0");
        assert_eq!(
            decode(&c, 1, n, Attribute::Current).unwrap(),
            b"u:r:droidloom_broker:s0\0"
        );
        c.id = 104;
        assert!(decode(&c, 1, n, Attribute::Current).is_err());
        c.id = 101;
        c.flags = 1;
        assert!(decode(&c, 1, n, Attribute::Current).is_err());
    }
    #[test]
    fn count_truncation_and_extra_record_bytes_are_rejected() {
        let (c, n) = record(b"u:r:droidloom_broker:s0\0");
        for count in [0, 2, -1] {
            assert!(decode(&c, count, n, Attribute::Current).is_err());
        }
        assert!(decode(&c, 1, n - 1, Attribute::Current).is_err());
        assert!(decode(&c, 1, n + 8, Attribute::Current).is_err());
    }
    #[test]
    fn context_terminator_padding_and_unbounded_size_are_rejected() {
        let (mut c, n) = record(b"a\0");
        c.ctx[2] = 1;
        assert!(decode(&c, 1, n, Attribute::Current).is_err());
        let (mut c, n) = record(b"a");
        assert!(decode(&c, 1, n, Attribute::Current).is_err());
        c.ctx_len = u64::MAX;
        assert!(decode(&c, 1, n, Attribute::Current).is_err());
        let (c, n) = record(b"a\0b\0");
        assert!(decode(&c, 1, n, Attribute::Current).is_err());
    }
    #[test]
    fn exec_empty_and_fixed_targets_preserve_source_origins() {
        let (empty, size) = record(b"");
        assert!(decode(&empty, 1, size, Attribute::Exec).unwrap().is_empty());
        assert!(decode(&empty, 1, size, Attribute::Current).is_err());
        let mut seen = std::collections::BTreeSet::new();
        for target in [
            ExecTarget::QueryIo,
            ExecTarget::MetadataObserver,
            ExecTarget::EngineObserver,
            ExecTarget::NativeCamera,
            ExecTarget::NativeLeafApkReader,
            ExecTarget::WorkingApkPayloadCreator,
            ExecTarget::WorkingOriginalPayloadBirth,
            ExecTarget::WorkingPreparation,
            ExecTarget::WorkingApplication,
        ] {
            let (origin, expected) = target.contexts();
            assert_ne!(origin, expected);
            assert!(seen.insert(expected));
            let (raw, size) = record(expected);
            assert_eq!(record_body(&raw, 1, size, Attribute::Exec), Some(expected));
            assert_ne!(record_body(&raw, 1, size, Attribute::Exec), Some(origin));
            assert!(record_body(&raw, 2, size, Attribute::Exec).is_none());
        }
        assert_eq!(
            ExecTarget::WorkingPreparation.contexts().0,
            b"u:system_r:p4_linux_working_qualification_t:s0\0"
        );
        assert_eq!(
            ExecTarget::WorkingApplication.contexts().0,
            ExecTarget::WorkingPreparation.contexts().0
        );
        assert_eq!(ExecTarget::WorkingOriginalPayloadBirth.contexts().0,
            b"u:system_r:p4_linux_working_privateprep_t:s0\0");
        assert_eq!(ExecTarget::WorkingOriginalPayloadBirth.contexts().1,
            b"u:system_r:p4_linux_working_payload_birth_t:s0\0");
        assert_eq!(
            ExecTarget::QueryIo.contexts().0,
            b"u:r:droidloom_broker:s0\0"
        );
    }
}
