//! Explicit per-call LSM identities; no mutable socket provider is used.
use super::super::query_io;
use super::{Result, reject, require};
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};

pub(super) const SELINUX: u64 = 101;
pub(super) const APPARMOR: u64 = 104;
pub(super) const CAPTURE: &[u8] = b"u:r:droidloom_camera_capture:s0";
pub(super) const PRODUCER: &[u8] = b"u:r:droidloom_camera_producer:s0";
pub(super) const BROKER: &[u8] = b"u:r:droidloom_broker:s0";
const PEER_LSM: i32 = 0x50340001;
#[repr(C)]
struct SelfContext {
    id: u64,
    flags: u64,
    length: u64,
    context_length: u64,
    body: [u8; 480],
}
#[repr(C)]
struct PeerContext {
    size: u32,
    version: u32,
    id: u64,
    flags: u32,
    reserved: u32,
    context_length: u32,
    reserved2: u32,
    body: [u8; 480],
}
fn text(body: &[u8]) -> Result<Vec<u8>> {
    let bytes = body.strip_suffix(&[0]).unwrap_or(body);
    require(
        !bytes.is_empty() && !bytes.contains(&0) && !bytes.contains(&b'\n'),
        "camera native LSM label contains noncanonical bytes",
    )?;
    Ok(bytes.to_vec())
}
pub(super) fn current(provider: u64) -> Result<Vec<u8>> {
    let mut record = SelfContext {
        id: provider,
        flags: 0,
        length: 0,
        context_length: 0,
        body: [0; 480],
    };
    let mut length = mem::size_of_val(&record) as u32;
    let count = unsafe { libc::syscall(459, 100u32, &mut record, &mut length, 1u32) };
    if count < 0 {
        return Err(io::Error::last_os_error().into());
    }
    if count == 0 {
        return Err(io::Error::from_raw_os_error(libc::EOPNOTSUPP).into());
    }
    require(
        count == 1
            && record.id == provider
            && record.flags == 0
            && record.length == u64::from(length)
            && (32..=512).contains(&length)
            && record.context_length > 0
            && record.context_length <= record.length - 32,
        "camera native self label record differs",
    )?;
    text(&record.body[..record.context_length as usize])
}
pub(super) fn peer(socket: RawFd, provider: u64) -> Result<Vec<u8>> {
    let mut record = PeerContext {
        size: 32,
        version: 1,
        id: provider,
        flags: 0,
        reserved: 0,
        context_length: 0,
        reserved2: 0,
        body: [0; 480],
    };
    let mut length = mem::size_of_val(&record) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket,
            libc::SOL_SOCKET,
            PEER_LSM,
            (&mut record as *mut PeerContext).cast(),
            &mut length,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        record.size == 32
            && record.version == 1
            && record.id == provider
            && record.flags == 0
            && record.reserved == 0
            && record.reserved2 == 0
            && record.context_length > 0
            && record.context_length <= 480
            && length == 32 + record.context_length,
        "camera selected peer label record differs",
    )?;
    text(&record.body[..record.context_length as usize])
}
pub(super) fn capture_stack(label: &[u8]) -> bool {
    // The admitted kernel profile_cmp sorts these same-namespace profiles
    // by name. Only its exact canonical enforced intersection is accepted.
    label == b"droidloom-camera-capture//&droidloom-production-broker (enforce)"
}
pub(super) fn own_capture() -> Result<()> {
    query_io::own_root_credentials()?;
    query_io::empty_capabilities()?;
    require(
        current(SELINUX)? == CAPTURE && capture_stack(&current(APPARMOR)?),
        "camera is not the fixed zero-capability enforced profile intersection",
    )
}
pub(super) fn peer_pidfd(socket: RawFd) -> Result<(File, libc::ucred)> {
    let mut credential: libc::ucred = unsafe { mem::zeroed() };
    let mut bytes = mem::size_of_val(&credential) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket,
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut credential as *mut libc::ucred).cast(),
            &mut bytes,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(
        bytes as usize == mem::size_of_val(&credential) && credential.pid > 1,
        "camera peer has no original host PID",
    )?;
    let mut raw = -1i32;
    bytes = mem::size_of_val(&raw) as libc::socklen_t;
    if unsafe {
        libc::getsockopt(
            socket,
            libc::SOL_SOCKET,
            77,
            (&mut raw as *mut i32).cast(),
            &mut bytes,
        )
    } != 0
    {
        return Err(io::Error::last_os_error().into());
    }
    require(raw >= 0, "camera peer PIDFD is absent")?;
    let pidfd = unsafe { File::from_raw_fd(raw) };
    require(
        bytes as usize == mem::size_of_val(&raw),
        "camera peer PIDFD ABI differs",
    )?;
    query_io::alive(&pidfd)?;
    let info = query_io::pidfd_info(&pidfd)?;
    require(
        info.pid == credential.pid as u32 && info.tgid == info.pid,
        "camera peer PIDFD disagrees with native credentials",
    )?;
    Ok((pidfd, credential))
}
pub(super) fn exact_ids(info: &query_io::PidfdInfo, uid: u32, gid: u32) -> Result<()> {
    require(
        [info.ruid, info.euid, info.suid, info.fsuid] == [uid; 4]
            && [info.rgid, info.egid, info.sgid, info.fsgid] == [gid; 4],
        "camera task changed one of its original real/effective/saved/fs identities",
    )
}
pub(super) fn producer(socket: RawFd, original_init: &File, uid: u32, gid: u32) -> Result<File> {
    query_io::alive(original_init)?;
    let original = query_io::pidfd_info(original_init)?;
    exact_ids(&original, uid, gid)?;
    let (pidfd, credentials) = peer_pidfd(socket)?;
    require(
        credentials.uid == uid
            && credentials.gid == gid
            && peer(socket, SELINUX)? == PRODUCER
            && peer(socket, APPARMOR)? == b"droidloom-production-android (enforce)",
        "camera connection is not the selected Android producer",
    )?;
    let info = query_io::pidfd_info(&pidfd)?;
    exact_ids(&info, uid, gid)?;
    require(
        info.ppid == original.pid && info.pid != original.pid,
        "camera producer is not the original Android init's direct child",
    )?;
    query_io::alive(original_init)?;
    query_io::alive(&pidfd)?;
    Ok(pidfd)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_the_exact_enforced_camera_profile_intersection_is_valid() {
        assert!(capture_stack(
            b"droidloom-camera-capture//&droidloom-production-broker (enforce)"
        ));
        assert!(!capture_stack(
            b"droidloom-production-broker//&droidloom-camera-capture (enforce)"
        ));
        for value in [
            b"droidloom-camera-capture (enforce)".as_slice(),
            b"droidloom-production-broker (enforce)".as_slice(),
            b"droidloom-camera-capture//&droidloom-production-broker (complain)".as_slice(),
            b"droidloom-camera-capture//&droidloom-production-broker//&extra (enforce)".as_slice(),
            b"droidloom-camera-capture//&droidloom-production-broker (enforce)\n".as_slice(),
        ] {
            assert!(!capture_stack(value));
        }
    }
}
