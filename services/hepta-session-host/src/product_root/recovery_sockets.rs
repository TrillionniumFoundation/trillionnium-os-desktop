//! Retire only stale original rendezvous under immutable Root-owned parents.
//! No PID from disk is signalled, and a live stream is never replaced.
use super::{Result, config::Inputs, fs, geometry::Product, recovery::Existing};
use std::os::unix::fs::{FileTypeExt, MetadataExt};
use std::os::unix::net::UnixStream;
use std::path::Path;

pub(super) fn retire(inputs: &Inputs, product: &Product, old: &Existing) -> Result<()> {
    let paths = [
        (
            product.record.layout.agentd_control_socket().to_path_buf(),
            inputs.uid,
            0o600,
        ),
        (
            product.record.layout.app_server_socket().to_path_buf(),
            inputs.uid,
            0o600,
        ),
        (
            product
                .record
                .layout
                .run_root()
                .join("notes-objective.sock"),
            inputs.uid,
            0o600,
        ),
        (old.config.sockets.observation.clone(), 0, 0o660),
        (old.config.sockets.issuer.clone(), 0, 0o660),
        (old.config.sockets.checkpoint.clone(), 0, 0o660),
        (
            old.config
                .sockets
                .device_frontier
                .clone()
                .ok_or("Device lane absent")?,
            0,
            0o660,
        ),
        (
            old.config
                .sockets
                .notes_frontier
                .clone()
                .ok_or("Notes lane absent")?,
            0,
            0o660,
        ),
        (product.prefix.join("r/root-text.sock"), 0, 0o660),
    ];
    for (path, uid, mode) in &paths {
        stale(path, *uid, inputs.gid, *mode)?;
    }
    old.stage(product, "05-old-sockets-retired", &serde_json::json!({
        "scope":"only ConnectionRefused sockets under original Root parents removed; no PID signalled",
        "paths":paths.iter().map(|(path,_,_)| path).collect::<Vec<_>>()
    }))
}

fn stale(path: &Path, uid: u32, gid: u32, mode: u32) -> Result<()> {
    fs::root_directory(path.parent().ok_or("socket parent absent")?)?;
    let before = match std::fs::symlink_metadata(path) {
        Ok(value) => value,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error.into()),
    };
    if !before.file_type().is_socket()
        || before.uid() != uid
        || before.gid() != gid
        || before.mode() & 0o7777 != mode
        || before.nlink() != 1
        || path.canonicalize()? != path
    {
        return Err("original stale rendezvous custody differs".into());
    }
    match UnixStream::connect(path) {
        Ok(_) => return Err("an actual live endpoint cannot be replaced during recovery".into()),
        Err(error) if error.kind() == std::io::ErrorKind::ConnectionRefused => {}
        Err(error) => return Err(error.into()),
    }
    let after = std::fs::symlink_metadata(path)?;
    if (
        before.dev(),
        before.ino(),
        before.uid(),
        before.gid(),
        before.mode(),
    ) != (
        after.dev(),
        after.ino(),
        after.uid(),
        after.gid(),
        after.mode(),
    ) {
        return Err("original socket identity changed before retirement".into());
    }
    // Root retains every ancestor; the non-Root old owner cannot replace this
    // directory entry between the final identity observation and unlink.
    std::fs::remove_file(path)?;
    std::fs::File::open(path.parent().ok_or("socket parent absent")?)?.sync_all()?;
    Ok(())
}
