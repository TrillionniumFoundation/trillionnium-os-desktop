//! Explicit SELinux self observation on x86-64 Linux 6.18.
//! This read-only API does not depend on legacy proc LSM ordering, a guest
//! mount, supplied PID/context, libselinux or an installation record.
use super::{Result, require};
use std::io;
const SELINUX_ID: u64 = 101;
const SINGLE: u32 = 1;
const GET_SELF_ATTR: libc::c_long = 459;
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
const _: () =
    assert!(std::mem::size_of::<Context>() == 1056 && std::mem::align_of::<Context>() == 8);
#[derive(Clone, Copy)]
enum Attribute {
    Current,
    FsCreate,
}
impl Attribute {
    fn value(self) -> u32 {
        match self {
            Self::Current => 100,
            Self::FsCreate => 102,
        }
    }
}
fn decode(raw: &Context, count: libc::c_long, size: u32, attribute: Attribute) -> Result<Vec<u8>> {
    require(
        count == 1 && raw.id == SELINUX_ID && raw.flags == 0,
        "one actual explicitly selected SELinux context",
    )?;
    require(
        raw.ctx_len <= raw.ctx.len() as u64,
        "bounded complete typed SELinux context",
    )?;
    let length = raw.ctx_len as usize;
    let aligned = (32 + length + 7) & !7;
    require(
        raw.len == aligned as u64
            && size as usize == aligned
            && aligned <= std::mem::size_of::<Context>(),
        "complete exact aligned kernel context record",
    )?;
    require(
        raw.ctx[length..aligned - 32].iter().all(|b| *b == 0),
        "zero kernel context alignment padding",
    )?;
    if length == 0 {
        require(
            matches!(attribute, Attribute::FsCreate) && size == 32,
            "only unset fscreate has an empty context",
        )?;
    } else {
        require(
            raw.ctx[length - 1] == 0 && !raw.ctx[..length - 1].contains(&0),
            "one complete NUL-terminated SELinux context",
        )?;
        require(
            std::str::from_utf8(&raw.ctx[..length - 1]).is_ok(),
            "typed SELinux context encoding",
        )?;
    }
    Ok(raw.ctx[..length].to_vec())
}
fn observe(attribute: Attribute) -> Result<Vec<u8>> {
    let mut raw = Context {
        id: SELINUX_ID,
        flags: 0,
        len: 0,
        ctx_len: 0,
        ctx: [0; 1024],
    };
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
pub(super) fn selinux_current() -> Result<Vec<u8>> {
    observe(Attribute::Current)
}
pub(super) fn require_no_fscreate() -> Result<()> {
    // Empty create_sid yields ONE record: id101,flags0,len32,ctx_len0.
    // Error, unsupported provider, count0 and an empty CURRENT all remain errors.
    require(
        observe(Attribute::FsCreate)?.is_empty(),
        "inherited SELinux fscreate override is present",
    )
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
}
