use crate::{AnyError, MARKER_PATH, PROFILE, SOCKET_FD_NAME, SOCKET_PATH, invalid};
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::{FromRawFd, RawFd};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::Path;

const LISTEN_FD: RawFd = 3;

#[derive(Debug)]
pub(crate) struct MarkerGuard {
    _file: File,
}

pub(crate) fn require_profile(arguments: &[String]) -> Result<(), AnyError> {
    let mut profiles = 0_u8;
    let mut index = 0;
    while index < arguments.len() {
        match arguments[index].as_str() {
            "--self-check" => index += 1,
            "--profile" if arguments.get(index + 1).map(String::as_str) == Some(PROFILE) => {
                profiles = profiles.saturating_add(1);
                index += 2;
            }
            _ => return Err(invalid("expected exactly '--profile development'").into()),
        }
    }
    if profiles != 1 {
        return Err(invalid("expected exactly one development profile selector").into());
    }
    Ok(())
}

pub(crate) fn require_marker() -> Result<MarkerGuard, AnyError> {
    let path = Path::new(MARKER_PATH);
    let parent = path
        .parent()
        .ok_or_else(|| invalid("development marker has no parent"))?;
    let parent_metadata = fs::symlink_metadata(parent)?;
    if parent_metadata.file_type().is_symlink()
        || !parent_metadata.is_dir()
        || parent_metadata.uid() != 0
        || parent_metadata.permissions().mode() & 0o022 != 0
    {
        return Err(invalid("development marker parent is unsafe").into());
    }
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file()
        || metadata.uid() != 0
        || metadata.permissions().mode() & 0o022 != 0
    {
        return Err(invalid("development marker is unsafe").into());
    }
    Ok(MarkerGuard { _file: file })
}

pub(crate) fn inherited_listener() -> Result<UnixListener, AnyError> {
    if required_env("LISTEN_PID")?.parse::<u32>()? != std::process::id()
        || required_env("LISTEN_FDS")? != "1"
        || required_env("LISTEN_FDNAMES")? != SOCKET_FD_NAME
    {
        return Err(invalid("invalid systemd socket activation identity").into());
    }
    if socket_option(LISTEN_FD, libc::SO_DOMAIN)? != libc::AF_UNIX
        || socket_option(LISTEN_FD, libc::SO_TYPE)? != libc::SOCK_STREAM
        || socket_option(LISTEN_FD, libc::SO_ACCEPTCONN)? != 1
    {
        return Err(invalid("fd 3 is not an accepting AF_UNIX stream listener").into());
    }
    // SAFETY: validated LISTEN_PID/LISTEN_FDS transfer exactly fd 3 from
    // systemd to this process; the descriptor is consumed exactly once.
    let listener = unsafe { UnixListener::from_raw_fd(LISTEN_FD) };
    let actual = listener
        .local_addr()?
        .as_pathname()
        .ok_or_else(|| invalid("inherited listener has no pathname"))?
        .to_owned();
    if actual != Path::new(SOCKET_PATH) {
        return Err(invalid("inherited listener pathname mismatch").into());
    }
    listener.set_nonblocking(false)?;
    Ok(listener)
}

pub(crate) fn verify_stream_path(stream: &UnixStream) -> Result<(), AnyError> {
    let actual = stream
        .local_addr()?
        .as_pathname()
        .ok_or_else(|| invalid("connected socket has no pathname"))?
        .to_owned();
    if actual != Path::new(SOCKET_PATH) {
        return Err(invalid("connected socket pathname mismatch").into());
    }
    Ok(())
}

pub(crate) fn required_env(name: &'static str) -> Result<String, AnyError> {
    std::env::var(name).map_err(|_| invalid(name).into())
}

fn socket_option(fd: RawFd, option: libc::c_int) -> Result<libc::c_int, AnyError> {
    let mut value = 0;
    let mut length = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
    // SAFETY: both pointers address initialized writable storage and
    // getsockopt retains neither pointer.
    let status = unsafe {
        libc::getsockopt(
            fd,
            libc::SOL_SOCKET,
            option,
            std::ptr::addr_of_mut!(value).cast(),
            std::ptr::addr_of_mut!(length),
        )
    };
    if status != 0 {
        return Err(io::Error::last_os_error().into());
    }
    if usize::try_from(length)? != std::mem::size_of::<libc::c_int>() {
        return Err(invalid("socket option returned an invalid length").into());
    }
    Ok(value)
}
