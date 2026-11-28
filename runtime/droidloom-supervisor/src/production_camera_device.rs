//! Only the selected, root-owned UVC by-id alias can select a device.
use super::{Result, require};
use crate::native_hardware_label as held;
use std::ffi::CString;
use std::fs::File;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
const ALIAS: &std::ffi::CStr = c"usb-SunplusIT_Inc_Integrated_Camera_JX20250923V2-video-index0";
const CONTEXT: &[u8] = b"u:object_r:p4_linux_uvc_device_t:s0";
const DIRECTORY: &[u8] = b"u:object_r:p4_linux_uvc_dir_t:s0";

fn video_leaf(target: &[u8]) -> Option<CString> {
    let digits = target.strip_prefix(b"../../video")?;
    if digits.is_empty()
        || digits.len() > 3
        || !digits.iter().all(u8::is_ascii_digit)
        || (digits.len() > 1 && digits[0] == b'0')
    {
        return None;
    }
    let n = digits
        .iter()
        .fold(0u32, |v, d| 10 * v + u32::from(d - b'0'));
    if n >= 256 {
        return None;
    }
    CString::new(&target[6..]).ok()
}
/// The initial USER/PID authority is the original boot-held namespace objects.
pub(super) fn initial_scope() -> Result<()> {
    let root = held::path_at(libc::AT_FDCWD, c"/")?;
    held::directory(&root)?;
    held::namespaces(&root)?;
    Ok(())
}
pub(super) fn open() -> Result<Option<File>> {
    let root = held::path_at(libc::AT_FDCWD, c"/")?;
    held::directory(&root)?;
    let dev = held::path_at(root.as_raw_fd(), c"dev")?;
    let dev_st = held::directory(&dev)?;
    let (mount, _, fs) = held::mount_identity(&dev)?;
    require(
        fs == b"devtmpfs" && held::label(&dev)? == b"u:object_r:p4_linux_native_dev_root_t:s0",
        "camera /dev is not the native labeled devtmpfs",
    )?;
    let optional = |parent: &File, name: &std::ffi::CStr| -> Result<Option<File>> {
        match held::path_at(parent.as_raw_fd(), name) {
            Ok(file) => Ok(Some(file)),
            Err(error) if matches!(error.raw_os_error(), Some(libc::ENOENT | libc::ENODEV)) => {
                Ok(None)
            }
            Err(error) => Err(error.into()),
        }
    };
    let Some(v4l) = optional(&dev, c"v4l")? else {
        return Ok(None);
    };
    let Some(ids) = optional(&v4l, c"by-id")? else {
        return Ok(None);
    };
    for parent in [&v4l, &ids] {
        let node = held::directory(parent)?;
        require(
            node.st_dev == dev_st.st_dev
                && held::mount_id(parent)? == mount
                && held::label(parent)? == DIRECTORY,
            "camera by-id parent custody differs",
        )?;
    }
    let Some(alias) = optional(&ids, ALIAS)? else {
        return Ok(None);
    };
    let before_alias = held::metadata(&alias)?;
    require(
        before_alias.st_mode & libc::S_IFMT == libc::S_IFLNK
            && before_alias.st_uid == 0
            && before_alias.st_gid == 0
            && before_alias.st_nlink == 1
            && before_alias.st_dev == dev_st.st_dev
            && held::mount_id(&alias)? == mount,
        "camera alias is not the fixed native udev object",
    )?;
    let mut target = [0u8; 64];
    let n = unsafe {
        libc::readlinkat(
            alias.as_raw_fd(),
            c"".as_ptr(),
            target.as_mut_ptr().cast(),
            target.len(),
        )
    };
    if n < 0 {
        return Err(io::Error::last_os_error().into());
    }
    require(
        n > 0 && (n as usize) < target.len(),
        "camera alias target length differs",
    )?;
    let leaf_name = video_leaf(&target[..n as usize])
        .ok_or_else(|| super::reject("camera alias is outside the kernel video grammar"))?;
    let Some(leaf) = optional(&dev, &leaf_name)? else {
        return Ok(None);
    };
    let before = held::metadata(&leaf)?;
    require(
        before.st_mode & libc::S_IFMT == libc::S_IFCHR
            && before.st_uid == 0
            && before.st_nlink == 1
            && libc::major(before.st_rdev) == 81
            && libc::minor(before.st_rdev) < 256
            && before.st_dev == dev_st.st_dev
            && held::mount_id(&leaf)? == mount
            && held::label(&leaf)? == CONTEXT,
        "camera leaf is not the selected labeled video device",
    )?;
    // Target 6.18 deliberately allocates videoN and the minor independently.
    // The trusted udev alias and held original devtmpfs inode bind this object.
    let path = CString::new(format!("/proc/self/fd/{}", leaf.as_raw_fd())).unwrap();
    let raw = unsafe {
        libc::open(
            path.as_ptr(),
            libc::O_RDWR | libc::O_NONBLOCK | libc::O_CLOEXEC,
        )
    };
    if raw < 0 {
        let error = io::Error::last_os_error();
        if matches!(error.raw_os_error(), Some(libc::ENOENT | libc::ENODEV)) {
            return Ok(None);
        }
        return Err(error.into());
    }
    let device = unsafe { File::from_raw_fd(raw) };
    require(
        held::same_inode(&before, &held::metadata(&device)?)
            && held::mount_id(&device)? == mount
            && held::label(&leaf)? == CONTEXT
            && held::same_inode(&before_alias, &held::metadata(&alias)?)
            && held::same_inode(
                &before_alias,
                &held::metadata(&held::path_at(ids.as_raw_fd(), ALIAS)?)?,
            )
            && held::same_inode(
                &before,
                &held::metadata(&held::path_at(dev.as_raw_fd(), &leaf_name)?)?,
            )
            && held::mount_id(&dev)? == mount,
        "camera device or its selected alias changed during open",
    )?;
    Ok(Some(device))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_the_canonical_video_leaf_from_the_fixed_alias_is_admitted() {
        for n in [0, 1, 31, 63, 128, 255] {
            assert_eq!(
                video_leaf(format!("../../video{n}").as_bytes())
                    .unwrap()
                    .to_bytes(),
                format!("video{n}").as_bytes()
            );
        }
        for bad in [
            b"../../video256".as_slice(),
            b"../../video01",
            b"../../../video0",
            b"/dev/video0",
            b"../../video0/other",
            b"../../video",
            b"../../video-1",
            b"../../video0\0x",
        ] {
            assert!(video_leaf(bad).is_none());
        }
    }
}
