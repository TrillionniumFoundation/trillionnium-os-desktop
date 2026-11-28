//! A two-call Linux descriptor boundary for persistent ext4 inode custody.
//!
//! This crate does not accept paths, mutable flags, arbitrary output buffers,
//! or writable open modes. It is not an authorization API. The caller must
//! bind the persisted handle to its immutable source plan, original filesystem
//! UUID, held mount and the same normally resolved pathname before mutation.
#![deny(unsafe_op_in_unsafe_fn)]

#[cfg(not(all(target_os = "linux", target_arch = "x86_64")))]
compile_error!("the audited descriptor-custody ABI is Linux x86_64 only");

use std::{
    ffi::{c_char, c_int},
    io,
    os::fd::{AsRawFd, BorrowedFd, FromRawFd, OwnedFd},
};

const MAX_HANDLE: usize = 128;
const EXT4_INO32_GEN: c_int = 1;
const AT_EMPTY_PATH: c_int = 0x1000;
const O_PATH: c_int = 0o10_000_000;
const O_NOFOLLOW: c_int = 0o400_000;
const O_CLOEXEC: c_int = 0o2_000_000;

// Linux include/uapi/linux/fcntl.h and userspace bits/fcntl-linux.h agree:
// unsigned int handle_bytes; int handle_type; unsigned char f_handle[].
// The real allocation includes all 128 bytes advertised to the kernel.
#[repr(C)]
struct KernelHandle {
    handle_bytes: u32,
    handle_type: c_int,
    data: [u8; MAX_HANDLE],
}
const _: () = assert!(std::mem::size_of::<KernelHandle>() == 136);
const _: () = assert!(std::mem::align_of::<KernelHandle>() == 4);
const _: () = assert!(std::mem::offset_of!(KernelHandle, data) == 8);

unsafe extern "C" {
    fn name_to_handle_at(
        dirfd: c_int,
        pathname: *const c_char,
        handle: *mut KernelHandle,
        mount_id: *mut c_int,
        flags: c_int,
    ) -> c_int;
    fn open_by_handle_at(mountfd: c_int, handle: *mut KernelHandle, flags: c_int) -> c_int;
}

/// An ext4 FILEID_INO32_GEN value, including the filesystem's generation.
/// Parsing this value does not admit it as the identity of an original inode.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Ext4Handle {
    bytes: [u8; 8],
}
impl Ext4Handle {
    pub fn from_record(handle_type: i32, bytes: &[u8]) -> io::Result<Self> {
        if handle_type != EXT4_INO32_GEN || bytes.len() != 8 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "expected exact ext4 inode/generation handle",
            ));
        }
        let bytes: [u8; 8] = bytes.try_into().expect("length checked");
        if u32::from_ne_bytes(bytes[..4].try_into().expect("fixed prefix")) == 0 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "zero ext4 inode handle",
            ));
        }
        Ok(Self { bytes })
    }
    pub fn handle_type(&self) -> i32 {
        EXT4_INO32_GEN
    }
    pub fn bytes(&self) -> &[u8; 8] {
        &self.bytes
    }
    pub fn inode_number(&self) -> u32 {
        u32::from_ne_bytes(self.bytes[..4].try_into().expect("fixed prefix"))
    }
    pub fn generation(&self) -> u32 {
        u32::from_ne_bytes(self.bytes[4..].try_into().expect("fixed suffix"))
    }

    /// Captures only the inode already held by `inode`; empty-path lookup does
    /// not follow a held O_PATH symlink. No path or flag is caller-controlled.
    pub fn capture(inode: BorrowedFd<'_>) -> io::Result<(Self, i32)> {
        let mut raw = KernelHandle {
            handle_bytes: MAX_HANDLE as u32,
            handle_type: 0,
            data: [0; MAX_HANDLE],
        };
        let mut mount_id: c_int = 0;
        // SAFETY: both output pointers reference fully initialized, correctly
        // aligned allocations valid for this call. raw advertises exactly the
        // allocated data capacity; the pathname is the fixed NUL-terminated
        // empty string. The borrowed descriptor stays alive for the call.
        let result = unsafe {
            name_to_handle_at(
                inode.as_raw_fd(),
                c"".as_ptr(),
                &mut raw,
                &mut mount_id,
                AT_EMPTY_PATH,
            )
        };
        if result < 0 {
            return Err(io::Error::last_os_error());
        }
        if result != 0 || raw.handle_bytes as usize > MAX_HANDLE || mount_id <= 0 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "invalid kernel file-handle result",
            ));
        }
        Ok((
            Self::from_record(raw.handle_type, &raw.data[..raw.handle_bytes as usize])?,
            mount_id,
        ))
    }

    /// Resolves metadata custody only. `mount` must be the admitted ordinary
    /// read-only directory descriptor for the same filesystem; an O_PATH mount
    /// descriptor is rejected by the kernel. This always returns O_PATH with
    /// NOFOLLOW and CLOEXEC, never a descriptor that can read or write contents.
    pub fn reopen(&self, mount: BorrowedFd<'_>) -> io::Result<OwnedFd> {
        let mut raw = KernelHandle {
            handle_bytes: 8,
            handle_type: EXT4_INO32_GEN,
            data: [0; MAX_HANDLE],
        };
        raw.data[..8].copy_from_slice(&self.bytes);
        // SAFETY: raw is fully initialized and holds all advertised bytes.
        // Both the structure and borrowed mount descriptor remain alive for
        // the synchronous call. Flags are fixed to metadata-only custody.
        let result = unsafe {
            open_by_handle_at(mount.as_raw_fd(), &mut raw, O_PATH | O_NOFOLLOW | O_CLOEXEC)
        };
        if result < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: a nonnegative successful open_by_handle_at result is one new
        // owned descriptor. Ownership is transferred exactly once to OwnedFd.
        Ok(unsafe { OwnedFd::from_raw_fd(result) })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        fs::{self, File, OpenOptions},
        os::{
            fd::AsFd,
            unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt, symlink},
        },
        path::Path,
    };
    fn inode(path: &Path) -> File {
        OpenOptions::new()
            .read(true)
            .custom_flags(O_PATH | O_NOFOLLOW | O_CLOEXEC)
            .open(path)
            .unwrap()
    }
    fn f9(f: &File) -> (u64, u64, u32, u32, u32, u64, u64, i64, i64, i64, i64) {
        let m = f.metadata().unwrap();
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.uid(),
            m.gid(),
            m.nlink(),
            m.size(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    }
    #[test]
    fn only_exact_inode_generation_records_are_decoded() {
        assert!(Ext4Handle::from_record(1, &[0; 8]).is_err());
        for length in [0, 7, 9, 128, 129] {
            assert!(Ext4Handle::from_record(1, &vec![1; length]).is_err());
        }
        assert!(Ext4Handle::from_record(2, &[1; 8]).is_err());
        let value = Ext4Handle::from_record(1, &[2, 0, 0, 0, 5, 0, 0, 0]).unwrap();
        assert_eq!((value.inode_number(), value.generation()), (2, 5));
    }
    #[test]
    #[ignore = "requires root; creates only isolated qualification test inodes"]
    fn actual_regular_directory_and_symlink_handles_reject_replaced_named_inodes() {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let base = Path::new("/var/lib/droidloom-qualification")
            .join(format!("p4-filehandle-test-{}-{stamp}", std::process::id()));
        fs::create_dir(&base).unwrap();
        fs::set_permissions(&base, fs::Permissions::from_mode(0o700)).unwrap();
        assert_eq!(fs::metadata(&base).unwrap().uid(), 0);
        fs::write(base.join("regular"), b"ordinary private test body").unwrap();
        fs::create_dir(base.join("directory")).unwrap();
        symlink("regular", base.join("link")).unwrap();
        let mount = File::open("/").unwrap();
        for name in ["regular", "directory", "link"] {
            let path = base.join(name);
            let held = inode(&path);
            let before = f9(&held);
            let (handle, mount_id) = Ext4Handle::capture(held.as_fd()).unwrap();
            let decoded = Ext4Handle::from_record(handle.handle_type(), handle.bytes()).unwrap();
            let reopened = File::from(decoded.reopen(mount.as_fd()).unwrap());
            assert_eq!(f9(&reopened), before);
            assert_eq!(f9(&held), before);
            assert_eq!(
                Ext4Handle::capture(reopened.as_fd()).unwrap(),
                (handle.clone(), mount_id)
            );
            if name == "link" {
                assert_eq!(reopened.metadata().unwrap().mode() & 0o170000, 0o120000);
            }
            fs::rename(&path, base.join(format!("old-{name}"))).unwrap();
            match name {
                "directory" => fs::create_dir(&path).unwrap(),
                "link" => symlink("different-target", &path).unwrap(),
                _ => fs::write(&path, b"replacement").unwrap(),
            }
            let replacement = inode(&path);
            let (new_handle, _) = Ext4Handle::capture(replacement.as_fd()).unwrap();
            assert_ne!(handle, new_handle);
            let old_reopened = File::from(handle.reopen(mount.as_fd()).unwrap());
            assert_eq!(Ext4Handle::capture(old_reopened.as_fd()).unwrap().0, handle);
            assert_ne!(
                Ext4Handle::capture(old_reopened.as_fd()).unwrap().0,
                new_handle
            );
            let old = base.join(format!("old-{name}"));
            if name == "directory" {
                fs::remove_dir(&old).unwrap();
            } else {
                fs::remove_file(&old).unwrap();
            }
            // The old inode may remain decodable while an FD holds it. The
            // admission rule rejects nlink==0 and the mismatched named handle
            // regardless of whether this kernel happens to return ESTALE.
            if let Ok(fd) = handle.reopen(mount.as_fd()) {
                let reopened = File::from(fd);
                assert_eq!(reopened.metadata().unwrap().nlink(), 0);
                assert_ne!(Ext4Handle::capture(reopened.as_fd()).unwrap().0, new_handle);
            }
            println!(
                "verified {name}: type={} bytes={} generation={} mount={mount_id}; replacement rejected; original body never read",
                handle.handle_type(),
                handle.bytes().len(),
                handle.generation()
            );
        }
        fs::remove_dir_all(&base).unwrap();
    }
}
