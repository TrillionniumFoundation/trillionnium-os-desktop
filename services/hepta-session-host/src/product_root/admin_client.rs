//! Finite local client: connect to an already-live original Root, never reopen.
use super::{Result, admin, fs};
use codex_hepta_agentd::{RootAdminAction, RootAdminInstance, RootAdminRequest};
use std::ffi::OsString;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::net::UnixStream;
use std::path::Path;
use std::time::Instant;

#[path = "admin_grant.rs"]
mod grants;

pub(super) fn run(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    if unsafe { libc::getuid() } != 0 || unsafe { libc::geteuid() } != 0 {
        return Err("actual Root required for original administrative client".into());
    }
    if args.next().as_deref() != Some(std::ffi::OsStr::new("--instance-file")) {
        return Err("admin requires --instance-file <original Root0600 descriptor>".into());
    }
    let path = args.next().ok_or("missing original instance file")?;
    let descriptor: admin::Descriptor = fs::read_root_json(Path::new(&path))?;
    if descriptor.schema != "trill.original-root-admin.v1"
        || descriptor.socket.parent() != Path::new(&path).parent()
        || descriptor.socket.file_name() != Some(std::ffi::OsStr::new("root-admin.sock"))
    {
        return Err("original Root administrative descriptor mismatch".into());
    }
    let command = grants::parse_command(args)?;
    let inode = admin::socket_identity(&descriptor.socket)?;
    let end = Instant::now() + admin::EXCHANGE_TIMEOUT;
    let mut stream = connect_before(&descriptor.socket, end)?;
    let peer = admin::peer(&stream)?;
    if peer.uid != 0 || peer.pid as u32 != descriptor.instance.root_pid {
        return Err("connected peer is not the original Root instance".into());
    }
    verify_birth(&descriptor.instance)?;
    // Pin only the actual SO_PEERCRED peer just observed on this connected
    // channel, with birth checked before and after. A disk PID is never adopted.
    let raw = unsafe { libc::syscall(libc::SYS_pidfd_open, peer.pid, 0) };
    if raw < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    let held = unsafe { OwnedFd::from_raw_fd(raw as i32) };
    verify_live(&held, &descriptor.instance)?;
    if admin::socket_identity(&descriptor.socket)? != inode {
        return Err("admin socket replaced".into());
    }
    let request = RootAdminRequest {
        schema_version: 1,
        expected_instance: descriptor.instance.clone(),
        action: command.action,
    };
    admin::write_frame_before(&mut stream, &serde_json::to_vec(&request)?, end)?;
    let response = admin::read_frame_before(&mut stream, end)?;
    verify_live(&held, &descriptor.instance)?;
    let value: serde_json::Value = serde_json::from_slice(&response)?;
    let returned = value
        .get("instance")
        .or_else(|| {
            value
                .get("observation")
                .and_then(|value| value.get("instance"))
        })
        .ok_or("original Root response instance absent")?;
    if *returned != serde_json::to_value(&descriptor.instance)? {
        return Err("original Root response instance changed".into());
    }
    let outcome = grants::finish_response(&value, command.export.as_deref());
    // Preserve any actual first-store receipt even for partial/unknown outcome.
    println!("{}", serde_json::to_string_pretty(&value)?);
    outcome
}

fn connect_before(path: &Path, end: Instant) -> Result<UnixStream> {
    admin::remaining(end)?;
    let bytes = path.as_os_str().as_bytes();
    let mut address = libc::sockaddr_un {
        sun_family: libc::AF_UNIX as _,
        sun_path: [0; 108],
    };
    if bytes.is_empty() || bytes.len() >= address.sun_path.len() || bytes.contains(&0) {
        return Err("original Root socket path bound".into());
    }
    for (slot, byte) in address.sun_path.iter_mut().zip(bytes) {
        *slot = *byte as libc::c_char;
    }
    // SAFETY: creates a fresh local descriptor, never an inherited authority FD.
    let raw = unsafe {
        libc::socket(
            libc::AF_UNIX,
            libc::SOCK_STREAM | libc::SOCK_CLOEXEC | libc::SOCK_NONBLOCK,
            0,
        )
    };
    if raw < 0 {
        return Err(std::io::Error::last_os_error().into());
    }
    // SAFETY: takes ownership of precisely the successful socket return value.
    let fd = unsafe { OwnedFd::from_raw_fd(raw) };
    let length =
        (std::mem::offset_of!(libc::sockaddr_un, sun_path) + bytes.len() + 1) as libc::socklen_t;
    // SAFETY: address has a bounded NUL-terminated pathname, and length lies in it.
    let connected = unsafe {
        libc::connect(
            fd.as_raw_fd(),
            (&address as *const libc::sockaddr_un).cast(),
            length,
        )
    };
    if connected != 0 {
        let error = std::io::Error::last_os_error();
        if error.raw_os_error() != Some(libc::EINPROGRESS) {
            return Err(error.into());
        }
        let mut poll = libc::pollfd {
            fd: fd.as_raw_fd(),
            events: libc::POLLOUT,
            revents: 0,
        };
        let milliseconds = i32::try_from(admin::remaining(end)?.as_millis().max(1))?;
        // SAFETY: exactly one initialized local poll descriptor is borrowed.
        if unsafe { libc::poll(&mut poll, 1, milliseconds) } <= 0 {
            return Err("original Root connect deadline or error".into());
        }
        let mut error: libc::c_int = 0;
        let mut size = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
        // SAFETY: the two output pointers refer to correctly sized local storage.
        if unsafe {
            libc::getsockopt(
                fd.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_ERROR,
                (&mut error as *mut libc::c_int).cast(),
                &mut size,
            )
        } != 0
            || error != 0
            || size as usize != std::mem::size_of::<libc::c_int>()
        {
            return Err("original Root connect failed".into());
        }
    }
    admin::remaining(end)?;
    let stream = UnixStream::from(fd);
    stream.set_nonblocking(false)?;
    Ok(stream)
}

fn parse_action(mut args: impl Iterator<Item = OsString>) -> Result<RootAdminAction> {
    let action = args.next().ok_or("missing original Root admin action")?;
    let selected = match action.to_str() {
        Some("observe") => RootAdminAction::Observe {},
        Some("revoke-writer") => {
            if args.next().as_deref() != Some(std::ffi::OsStr::new("--expected-revision")) {
                return Err("missing expected revision".into());
            }
            let revision: u64 = args
                .next()
                .ok_or("missing revision")?
                .into_string()
                .map_err(|_| "revision must be UTF8")?
                .parse()?;
            if revision == 0 {
                return Err("expected original nonzero revision".into());
            }
            if args.next().as_deref() != Some(std::ffi::OsStr::new("--reason-sha256")) {
                return Err("missing reason digest".into());
            }
            let digest = args
                .next()
                .ok_or("missing digest")?
                .into_string()
                .map_err(|_| "digest must be UTF8")?;
            RootAdminAction::RevokeWriter {
                expected_revision: revision,
                reason_sha256: reason(&digest)?,
            }
        }
        _ => return Err("unknown original Root admin action".into()),
    };
    if args.next().is_some() {
        return Err("unexpected or duplicate original Root admin argument".into());
    }
    Ok(selected)
}

fn reason(raw: &str) -> Result<[u8; 32]> {
    if raw.len() != 64
        || !raw
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err("noncanonical reason SHA256".into());
    }
    let mut digest = [0; 32];
    for (index, slot) in digest.iter_mut().enumerate() {
        *slot = u8::from_str_radix(&raw[index * 2..index * 2 + 2], 16)?;
    }
    if digest == [0; 32] {
        return Err("nonzero reason digest required".into());
    }
    Ok(digest)
}

fn verify_birth(instance: &RootAdminInstance) -> Result<()> {
    if instance.episode_nonce == [0; 32]
        || std::fs::read_to_string("/proc/sys/kernel/random/boot_id")?.trim() != instance.boot_id
    {
        return Err("original Root administrative boot or nonce changed".into());
    }
    let stat = std::fs::read_to_string(format!("/proc/{}/stat", instance.root_pid))?;
    let start = stat
        .rsplit_once(") ")
        .and_then(|(_, fields)| fields.split_whitespace().nth(19))
        .and_then(|value| value.parse::<u64>().ok());
    if start != Some(instance.process_start_ticks) {
        return Err("original Root administrative birth changed".into());
    }
    Ok(())
}

fn verify_live(held: &OwnedFd, instance: &RootAdminInstance) -> Result<()> {
    verify_birth(instance)?;
    let mut descriptor = libc::pollfd {
        fd: held.as_raw_fd(),
        events: libc::POLLIN,
        revents: 0,
    };
    if unsafe { libc::poll(&mut descriptor, 1, 0) } != 0 {
        return Err("original Root administrative peer ended".into());
    }
    Ok(())
}

#[cfg(test)]
#[path = "admin_client_tests.rs"]
mod tests;
