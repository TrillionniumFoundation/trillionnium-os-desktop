use super::{EarlyBoardResources, invalid};
use std::fs::{File, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};

const REQUEST: &str = "/run/droidloom-early/readiness/shutdown-request";
const LABEL: &[u8] = b"u:object_r:p4_android_shutdown_request_t:s0";

unsafe extern "C" {
    fn droidloom_board_storage_id(fd: i32, id: *mut u64) -> i32;
    fn droidloom_board_storage_state(nsfd: i32, id: u64, present: i32) -> i32;
}

fn result(rc: i32) -> io::Result<()> {
    if rc == 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

pub(super) struct StopRequest {
    request: File,
    gid: u32,
    mounts: [u64; 2],
}

impl StopRequest {
    pub(super) fn acquire(
        board: &EarlyBoardResources,
        gid: u32,
        data: &File,
        metadata: &File,
    ) -> io::Result<Self> {
        board.revalidate()?;
        let request = OpenOptions::new()
            .read(true)
            .write(true)
            .custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK | libc::O_CLOEXEC)
            .open(REQUEST)?;
        let mut mounts = [0u64; 2];
        for (slot, fd) in mounts.iter_mut().zip([data, metadata]) {
            result(unsafe { droidloom_board_storage_id(fd.as_raw_fd(), slot) })?;
        }
        if mounts[0] == mounts[1] {
            return Err(invalid("Android has aliased persistent mount IDs"));
        }
        let value = Self {
            request,
            gid,
            mounts,
        };
        value.check_request(b'0')?;
        value.check_mounts(board, true)?;
        Ok(value)
    }

    fn check_request(&self, wanted: u8) -> io::Result<()> {
        let file = self.request.metadata()?;
        let named = std::fs::symlink_metadata(REQUEST)?;
        let mut ts = std::mem::MaybeUninit::<libc::statfs>::uninit();
        result(unsafe { libc::fstatfs(self.request.as_raw_fd(), ts.as_mut_ptr()) })?;
        let mut context = [0u8; 127];
        let bytes = unsafe {
            libc::fgetxattr(
                self.request.as_raw_fd(),
                c"security.selinux".as_ptr(),
                context.as_mut_ptr().cast(),
                context.len(),
            )
        };
        if bytes < 0 {
            return Err(io::Error::last_os_error());
        }
        let label = &context[..bytes as usize];
        let mut state = [0u8; 2];
        if !file.is_file()
            || file.dev() != named.dev()
            || file.ino() != named.ino()
            || file.mode() & 0o7777 != 0o640
            || file.uid() != 0
            || file.gid() != self.gid
            || file.nlink() != 1
            || file.len() != 1
            || unsafe { ts.assume_init().f_type } != libc::TMPFS_MAGIC
            || label.strip_suffix(&[0]).unwrap_or(label) != LABEL
            || self.request.read_at(&mut state, 0)? != 1
            || state[0] != wanted
        {
            return Err(invalid(
                "wrong Android shutdown request inode, identity or state",
            ));
        }
        Ok(())
    }

    pub(super) fn deliver(&self, board: &EarlyBoardResources) -> io::Result<()> {
        board.revalidate()?;
        self.check_request(b'0')?;
        self.check_mounts(board, true)?;
        if self.request.write_at(b"1", 0)? != 1 {
            return Err(invalid("short Android shutdown request"));
        }
        self.check_request(b'1')
    }

    pub(super) fn check_mounts(
        &self,
        board: &EarlyBoardResources,
        present: bool,
    ) -> io::Result<()> {
        for id in self.mounts {
            result(unsafe {
                droidloom_board_storage_state(
                    board.mount_namespace().as_raw_fd(),
                    id,
                    i32::from(present),
                )
            })?;
        }
        Ok(())
    }
}
