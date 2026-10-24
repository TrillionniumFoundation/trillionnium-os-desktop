//! Independent recovery for a terminated Notes incarnation. The original
//! owner supplies one connected private datagram on stdin. There is no
//! listener, effect endpoint, signer, new grant or replacement operation.

use std::io;
use std::os::fd::BorrowedFd;
use std::os::unix::net::UnixDatagram;
use std::path::PathBuf;
use std::time::Duration;
use trill_ui_core::notes::{
    NotesTargetIdentity, MAX_NOTES_REQUEST_BYTES, MAX_NOTES_RESPONSE_BYTES,
};
use trill_ui_core::notes_store::NotesStore;

fn run() -> io::Result<()> {
    let mut args = std::env::args().skip(1);
    let mut root = None;
    let mut session_instance = None;
    let mut incarnation = None;
    let mut task_id = None;
    while let Some(flag) = args.next() {
        let value = args
            .next()
            .ok_or_else(|| io::Error::other("missing recovery argument"))?;
        match flag.as_str() {
            "--state-dir" if root.is_none() => root = Some(PathBuf::from(value)),
            "--notes-session" if session_instance.is_none() => session_instance = Some(value),
            "--notes-incarnation" if incarnation.is_none() => incarnation = Some(value),
            "--task-id" if task_id.is_none() => task_id = value.parse().ok(),
            _ => return Err(io::Error::other("invalid recovery argument")),
        }
    }
    let target = NotesTargetIdentity {
        session_instance: session_instance.ok_or_else(|| io::Error::other("missing session"))?,
        incarnation: incarnation.ok_or_else(|| io::Error::other("missing incarnation"))?,
        task_id: task_id.ok_or_else(|| io::Error::other("missing task"))?,
    };
    let root = root.ok_or_else(|| io::Error::other("missing Notes state directory"))?;
    // Duplicate the process-owned descriptor. No arbitrary descriptor number,
    // path discovery or reconnectable public socket is accepted.
    let fd = unsafe { BorrowedFd::borrow_raw(0) }.try_clone_to_owned()?;
    let channel = UnixDatagram::from(fd);
    if !channel.local_addr()?.is_unnamed() || !channel.peer_addr()?.is_unnamed() {
        return Err(io::Error::other("recovery requires a private socket pair"));
    }
    channel.set_write_timeout(Some(Duration::from_secs(1)))?;
    let mut store = NotesStore::recover(&root, &target).map_err(|error| {
        io::Error::new(error.kind(), format!("open saved incarnation: {error}"))
    })?;
    let mut bytes = [0_u8; MAX_NOTES_REQUEST_BYTES + 1];
    loop {
        let length = channel.recv(&mut bytes).map_err(|error| {
            io::Error::new(error.kind(), format!("private recovery receive: {error}"))
        })?;
        if length == 0 || length > MAX_NOTES_REQUEST_BYTES {
            continue;
        }
        match store.recovery_exact(&bytes[..length]) {
            Ok(raw) if !raw.is_empty() && raw.len() <= MAX_NOTES_RESPONSE_BYTES => {
                // Lost datagrams are reconciled by another exact observation
                // or retirement request; they never trigger an effect retry.
                let _ = channel.send(&raw);
            }
            _ if store.is_frozen() => {
                return Err(io::Error::other("Notes storage requires recovery"))
            }
            _ => {}
        }
    }
}

fn main() {
    if let Err(error) = run() {
        eprintln!("trill-notes-recovery: {error}");
        std::process::exit(1);
    }
}
