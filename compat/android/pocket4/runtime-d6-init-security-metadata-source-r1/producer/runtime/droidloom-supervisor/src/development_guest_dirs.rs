//! Explicit modes for new directories on the cell's private tmpfs trees.
//!
//! The host daemon may use umask 0077. Android's non-root services still need
//! to traverse the /dev and synthetic /sys directories normally provided by
//! first-stage init. Never change the host umask or chmod an existing object.

use std::ffi::CString;
use std::fs::{File, OpenOptions};
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt};
use std::path::{Component, Path, PathBuf};

/// Create only missing directories beneath a newly mounted, private tree.
/// Existing directories retain their mode; symlinks and mounted filesystems
/// are rejected before descending. All permission writes use a held new fd.
pub(super) fn create_under(base: &Path, relative: &Path) -> io::Result<PathBuf> {
    let names = relative
        .components()
        .map(|component| match component {
            Component::Normal(name) => CString::new(name.as_bytes())
                .map_err(|_| invalid("NUL in private guest directory name")),
            _ => Err(invalid(
                "private guest directory must be a relative normal path",
            )),
        })
        .collect::<io::Result<Vec<_>>>()?;
    let mut parent = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(base)?;
    let device = parent.metadata()?.dev();
    for name in names {
        // SAFETY: parent is held, and name is a validated single C component.
        let result = unsafe { libc::mkdirat(parent.as_raw_fd(), name.as_ptr(), 0o755) };
        let created = if result == 0 {
            true
        } else {
            let error = io::Error::last_os_error();
            if error.raw_os_error() != Some(libc::EEXIST) {
                return Err(error);
            }
            false
        };
        // SAFETY: openat returns a new fd or -1. No symlink is followed.
        let fd = unsafe {
            libc::openat(
                parent.as_raw_fd(),
                name.as_ptr(),
                libc::O_RDONLY | libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            )
        };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: the successful openat transferred this new descriptor.
        let directory = unsafe { File::from_raw_fd(fd) };
        if directory.metadata()?.dev() != device {
            return Err(io::Error::new(
                io::ErrorKind::PermissionDenied,
                "private guest directory would cross a mounted filesystem",
            ));
        }
        if created {
            // mkdir applies umask. Correct only the inode this call created;
            // existing host bind targets and outer control paths are untouched.
            // SAFETY: directory is a held, same-filesystem new directory fd.
            if unsafe { libc::fchmod(directory.as_raw_fd(), 0o755) } != 0 {
                return Err(io::Error::last_os_error());
            }
        }
        parent = directory;
    }
    Ok(base.join(relative))
}

fn invalid(message: &str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message)
}

pub(super) fn device_directories(dev: &Path) -> io::Result<()> {
    for relative in ["pts", "binderfs", "block", "dri", "socket/droidloom"] {
        create_under(dev, Path::new(relative))?;
    }
    Ok(())
}

pub(super) fn sysfs_mount_points(sys: &Path) -> io::Result<()> {
    for relative in ["fs/cgroup", "fs/bpf", "fs/fuse/connections"] {
        create_under(sys, Path::new(relative))?;
    }
    Ok(())
}

#[cfg(test)]
#[path = "development_guest_dirs_tests.rs"]
mod tests;
