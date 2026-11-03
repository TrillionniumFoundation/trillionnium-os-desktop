//! Root-only local adapter to the SAME prepared service's opaque capability.
use super::{Result, fs};
use codex_hepta_agentd::{ROOT_ADMIN_FRAME_BOUND, RootAdminCapability, RootAdminInstance};
use serde::{Deserialize, Serialize};
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt};
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, Instant};

pub(super) const EXCHANGE_TIMEOUT: Duration = Duration::from_secs(1);

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Descriptor {
    pub schema: String,
    pub socket: PathBuf,
    pub instance: RootAdminInstance,
}

pub(super) struct Lane {
    listener: UnixListener,
    capability: RootAdminCapability,
    descriptor: Descriptor,
    inode: (u64, u64),
}

impl Lane {
    pub(super) fn bind(directory: &Path, capability: RootAdminCapability) -> Result<Self> {
        fs::root_directory(directory)?;
        if std::fs::metadata(directory)?.mode() & 0o7777 != 0o700 {
            return Err("original Root admin parent must be private".into());
        }
        let descriptor = Descriptor {
            schema: "trill.original-root-admin.v1".into(),
            socket: directory.join("root-admin.sock"),
            instance: capability.instance().clone(),
        };
        let listener = UnixListener::bind(&descriptor.socket)?;
        std::fs::set_permissions(&descriptor.socket, std::fs::Permissions::from_mode(0o600))?;
        let inode = socket_identity(&descriptor.socket)?;
        let lane = Self {
            listener,
            capability,
            descriptor,
            inode,
        };
        lane.listener.set_nonblocking(true)?;
        fs::json_new(
            &directory.join("root-admin-instance.json"),
            &lane.descriptor,
        )?;
        Ok(lane)
    }

    pub(super) fn serve_during(
        &self,
        serve_original: impl FnOnce() -> std::io::Result<()>,
    ) -> std::io::Result<()> {
        let stop = AtomicBool::new(false);
        std::thread::scope(|scope| {
            let worker = scope.spawn(|| {
                while !stop.load(Ordering::Acquire) {
                    match self.listener.accept() {
                        Ok((mut stream, _)) => {
                            let end = Instant::now() + EXCHANGE_TIMEOUT;
                            if self.exchange(&mut stream, end).is_err() {
                                // Never log the request, signed grant, arbitrary
                                // error paths or the human's document content.
                                let raw = serde_json::to_vec(&serde_json::json!({
                                    "status":"unavailable", "instance":self.descriptor.instance,
                                    "outcome":"request refused or outcome unknown; observe original state before any further action"
                                })).unwrap_or_default();
                                let _ = write_frame_before(&mut stream, &raw, end);
                            }
                        }
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            std::thread::sleep(Duration::from_millis(5));
                        }
                        Err(_) => return Err(std::io::Error::other("original Root admin listener failed")),
                    }
                }
                Ok(())
            });
            struct Stop<'a>(&'a AtomicBool);
            impl Drop for Stop<'_> {
                fn drop(&mut self) {
                    self.0.store(true, Ordering::Release);
                }
            }
            let guard = Stop(&stop);
            let original = serve_original();
            drop(guard);
            worker
                .join()
                .map_err(|_| std::io::Error::other("original Root admin adapter panicked"))??;
            original
        })
    }

    fn exchange(&self, stream: &mut UnixStream, end: Instant) -> Result<()> {
        if peer(stream)?.uid != 0 || socket_identity(&self.descriptor.socket)? != self.inode {
            return Err("original Root administrative peer or inode changed".into());
        }
        let raw = read_frame_before(stream, end)?;
        let response = self.capability.exchange(&raw, end)?;
        if peer(stream)?.uid != 0 || socket_identity(&self.descriptor.socket)? != self.inode {
            return Err("original Root administrative peer or inode changed".into());
        }
        write_frame_before(stream, &response, end)
    }
}

impl Drop for Lane {
    fn drop(&mut self) {
        if socket_identity(&self.descriptor.socket).ok() == Some(self.inode) {
            let _ = std::fs::remove_file(&self.descriptor.socket);
        }
    }
}

pub(super) fn socket_identity(path: &Path) -> Result<(u64, u64)> {
    fs::root_directory(path.parent().ok_or("admin socket parent missing")?)?;
    let metadata = std::fs::symlink_metadata(path)?;
    if !metadata.file_type().is_socket()
        || metadata.uid() != 0
        || metadata.nlink() != 1
        || metadata.mode() & 0o7777 != 0o600
        || std::fs::metadata(path.parent().ok_or("missing parent")?)?.mode() & 0o7777 != 0o700
    {
        return Err("Root admin socket custody differs".into());
    }
    Ok((metadata.dev(), metadata.ino()))
}

pub(super) fn peer(stream: &UnixStream) -> Result<libc::ucred> {
    let mut value = libc::ucred {
        pid: 0,
        uid: 0,
        gid: 0,
    };
    let mut length = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    // SAFETY: both output pointers refer to exactly initialized local storage.
    if unsafe {
        libc::getsockopt(
            stream.as_raw_fd(),
            libc::SOL_SOCKET,
            libc::SO_PEERCRED,
            (&mut value as *mut libc::ucred).cast(),
            &mut length,
        )
    } != 0
        || length as usize != std::mem::size_of::<libc::ucred>()
        || value.pid <= 1
    {
        return Err("actual Root admin peer credentials unavailable".into());
    }
    Ok(value)
}

#[cfg(test)]
pub(super) fn read_frame(stream: &mut UnixStream) -> Result<Vec<u8>> {
    read_frame_before(stream, Instant::now() + EXCHANGE_TIMEOUT)
}

pub(super) fn read_frame_before(stream: &mut UnixStream, end: Instant) -> Result<Vec<u8>> {
    let mut prefix = [0; 4];
    read_before(stream, &mut prefix, end)?;
    let length = u32::from_be_bytes(prefix) as usize;
    if length == 0 || length > ROOT_ADMIN_FRAME_BOUND {
        return Err("Root admin request bound".into());
    }
    let mut bytes = vec![0; length];
    read_before(stream, &mut bytes, end)?;
    Ok(bytes)
}

fn read_before(stream: &mut UnixStream, mut bytes: &mut [u8], end: Instant) -> Result<()> {
    while !bytes.is_empty() {
        stream.set_read_timeout(Some(remaining(end)?))?;
        let count = stream.read(bytes)?;
        if count == 0 {
            return Err("original Root admin channel ended".into());
        }
        bytes = &mut bytes[count..];
    }
    remaining(end)?;
    Ok(())
}

#[cfg(test)]
pub(super) fn write_frame(stream: &mut UnixStream, raw: &[u8]) -> Result<()> {
    write_frame_before(stream, raw, Instant::now() + EXCHANGE_TIMEOUT)
}

pub(super) fn write_frame_before(stream: &mut UnixStream, raw: &[u8], end: Instant) -> Result<()> {
    if raw.is_empty() || raw.len() > ROOT_ADMIN_FRAME_BOUND {
        return Err("Root admin response bound".into());
    }
    let prefix = (raw.len() as u32).to_be_bytes();
    for mut bytes in [prefix.as_slice(), raw] {
        while !bytes.is_empty() {
            stream.set_write_timeout(Some(remaining(end)?))?;
            let count = stream.write(bytes)?;
            if count == 0 {
                return Err("original Root admin write ended".into());
            }
            bytes = &bytes[count..];
        }
    }
    remaining(end)?;
    Ok(())
}

pub(super) fn remaining(end: Instant) -> Result<Duration> {
    end.checked_duration_since(Instant::now())
        .filter(|value| !value.is_zero())
        .ok_or_else(|| "original Root admin cumulative deadline elapsed".into())
}
