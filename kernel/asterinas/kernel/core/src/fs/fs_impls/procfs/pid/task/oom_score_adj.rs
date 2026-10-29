// SPDX-License-Identifier: MPL-2.0

use aster_util::printer::VmPrinter;

use super::TidDirOps;
use crate::{
    fs::{
        file::mkmod,
        procfs::template::{ProcFile, ProcFileOps, read_i32_from},
        vfs::inode::Inode,
    },
    prelude::*,
    process::{OomScoreAdj, posix_thread::AsPosixThread},
    thread::Thread,
};

/// Represents the inode at `/proc/[pid]/task/[tid]/oom_score_adj` (and also `/proc/[pid]/oom_score_adj`).
pub(super) struct OomScoreAdjFileOps(TidDirOps);

impl OomScoreAdjFileOps {
    pub(super) fn new_inode(dir: &TidDirOps, parent: Weak<dyn Inode>) -> Arc<dyn Inode> {
        // Reference: <https://elixir.bootlin.com/linux/v6.16.5/source/fs/proc/base.c#L3386>
        ProcFile::new(Self(dir.clone()), parent, mkmod!(a+r, u+w))
    }
}

impl ProcFileOps for OomScoreAdjFileOps {
    fn owner_thread(&self) -> Option<Arc<Thread>> {
        self.0.thread()
    }

    fn read_at(&self, offset: usize, writer: &mut VmWriter) -> Result<usize> {
        let mut printer = VmPrinter::new_skip(writer, offset);

        let Some(process) = self.0.process() else {
            return_errno_with_message!(Errno::ESRCH, "the process does not exist");
        };
        let oom_score_adj = process.oom_score_adj().read();
        writeln!(printer, "{}", oom_score_adj)?;

        Ok(printer.bytes_written())
    }

    fn write_at(&self, _offset: usize, reader: &mut VmReader) -> Result<usize> {
        let (val, read_bytes) = read_i32_from(reader)?;
        OomScoreAdj::validate_value(val)?;

        let Some(process) = self.0.process() else {
            return_errno_with_message!(Errno::ESRCH, "the process does not exist");
        };
        process
            .oom_score_adj()
            .write_from(val, current_thread!().as_posix_thread().unwrap())?;

        Ok(read_bytes)
    }
}
