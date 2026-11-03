// SPDX-License-Identifier: MPL-2.0

use super::TidDirOps;
use crate::{
    events::IoEvents,
    fs::{
        file::{AccessMode, PerOpenFileOps, StatusFlags, mkmod},
        procfs::template::{ProcFile, ProcFileOpsByHandle},
        vfs::inode::{FileOps, Inode},
    },
    prelude::*,
    process::{
        VmarSnapshot,
        posix_thread::{AsPosixThread, alien_access::AlienAccessMode},
        signal::{PollHandle, Pollable},
    },
    thread::Thread,
};

/// Represents the inode at `/proc/[pid]/task/[tid]/environ` (and also `/proc/[pid]/environ`).
pub(super) struct EnvironFileOps(TidDirOps);

impl EnvironFileOps {
    pub(super) fn new_inode(dir: &TidDirOps, parent: Weak<dyn Inode>) -> Arc<dyn Inode> {
        // Reference: <https://elixir.bootlin.com/linux/v6.16.5/source/fs/proc/base.c#L3324>
        ProcFile::new(Self(dir.clone()), parent, mkmod!(u+r))
    }
}

impl ProcFileOpsByHandle for EnvironFileOps {
    fn owner_thread(&self) -> Option<Arc<Thread>> {
        self.0.thread()
    }

    fn open(
        &self,
        _access_mode: AccessMode,
        _status_flags: StatusFlags,
    ) -> Result<Box<dyn PerOpenFileOps>> {
        let process = self.0.process().ok_or_else(|| Error::new(Errno::ESRCH))?;
        let vmar = process.lock_vmar();
        let thread = self.0.thread().ok_or_else(|| Error::new(Errno::ESRCH))?;
        let _access = thread
            .as_posix_thread()
            .unwrap()
            .check_alien_access_from(
                current_thread!().as_posix_thread().unwrap(),
                AlienAccessMode::READ_WITH_FS_CREDS,
                &vmar,
            )
            .map_err(|_| Error::with_message(Errno::EACCES, "alien access is denied"))?;
        Ok(Box::new(EnvironFileHandle(self.0.clone(), vmar.snapshot())))
    }
}

struct EnvironFileHandle(TidDirOps, VmarSnapshot);

impl Pollable for EnvironFileHandle {
    fn poll(&self, mask: IoEvents, _poller: Option<&mut PollHandle>) -> IoEvents {
        (IoEvents::IN | IoEvents::OUT) & mask
    }
}

impl FileOps for EnvironFileHandle {
    fn read_at(
        &self,
        offset: usize,
        writer: &mut VmWriter,
        _status_flags: StatusFlags,
    ) -> Result<usize> {
        let Some(process) = self.0.process() else {
            return Ok(0);
        };
        let vmar = process.lock_vmar();
        // An authorized old descriptor never follows exec into the new image.
        if !vmar.is_same_as(&self.1) {
            return Ok(0);
        }
        let Some(reader) = vmar.init_stack_reader() else {
            return Ok(0);
        };
        reader.envp(offset, writer)
    }

    fn write_at(
        &self,
        _offset: usize,
        _reader: &mut VmReader,
        _status_flags: StatusFlags,
    ) -> Result<usize> {
        Err(Error::new(Errno::EPERM))
    }
}

impl PerOpenFileOps for EnvironFileHandle {
    fn check_seekable(&self) -> Result<()> {
        Ok(())
    }
    fn is_offset_aware(&self) -> bool {
        true
    }
}
