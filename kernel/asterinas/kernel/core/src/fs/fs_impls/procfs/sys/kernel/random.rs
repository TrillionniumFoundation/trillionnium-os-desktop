// SPDX-License-Identifier: MPL-2.0

#![short_vis_path::add(procfs)]

use aster_util::printer::VmPrinter;

use crate::{
    fs::{
        file::{InodeType, mkmod},
        procfs::{
            StaticEntry,
            template::{ProcDir, ProcDirOps, ProcFile, ProcFileOps},
        },
        vfs::inode::Inode,
    },
    prelude::*,
    util::boot_identity,
};

/// The existing kernel boot UUID, exposed without creating another identity.
pub(super) struct RandomDirOps;

impl RandomDirOps {
    pub(super) fn new_inode(parent: Weak<dyn Inode>) -> Arc<dyn Inode> {
        ProcDir::new(Self, parent, mkmod!(a+rx))
    }

    const STATIC_ENTRIES: &'static [StaticEntry] =
        &[("boot_id", InodeType::File, BootIdFileOps::new_inode)];
}

impl ProcDirOps for RandomDirOps {
    fn lookup_child(&self, this_dir: &ProcDir<Self>, name: &str) -> Result<Arc<dyn Inode>> {
        use crate::fs::procfs::template::lookup_child_from_table;

        lookup_child_from_table(name, Self::STATIC_ENTRIES, |f| {
            (f)(this_dir.this_weak().clone())
        })
        .ok_or_else(|| Error::new(Errno::ENOENT))
    }

    fn visit_entries_from_offset<'a, F>(&'a self, offset: usize, visit_fn: F) -> Result<()>
    where
        F: FnMut(crate::fs::procfs::template::ReaddirEntry<'a>) -> Result<()>,
    {
        use crate::fs::procfs::template::{listed_entries_from_table, visit_listed_entries};

        visit_listed_entries(
            offset,
            listed_entries_from_table(Self::STATIC_ENTRIES),
            visit_fn,
        )
    }
}

struct BootIdFileOps;

impl BootIdFileOps {
    fn new_inode(parent: Weak<dyn Inode>) -> Arc<dyn Inode> {
        ProcFile::new(Self, parent, mkmod!(a+r))
    }
}

impl ProcFileOps for BootIdFileOps {
    fn read_at(&self, offset: usize, writer: &mut VmWriter) -> Result<usize> {
        let mut printer = VmPrinter::new_skip(writer, offset);
        for (index, byte) in boot_identity::boot_id().iter().enumerate() {
            if matches!(index, 4 | 6 | 8 | 10) {
                write!(printer, "-")?;
            }
            write!(printer, "{byte:02x}")?;
        }
        writeln!(printer)?;
        Ok(printer.bytes_written())
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::*;

    use super::*;

    #[ktest]
    fn proc_boot_id_partial_reads_preserve_the_same_uuid() {
        let mut complete = [0; 37];
        assert_eq!(
            BootIdFileOps
                .read_at(0, &mut VmWriter::from(&mut complete[..]).to_fallible())
                .unwrap(),
            37
        );
        assert_eq!(complete[36], b'\n');
        for (offset, expected) in complete.iter().enumerate() {
            let mut byte = [0];
            assert_eq!(
                BootIdFileOps
                    .read_at(offset, &mut VmWriter::from(&mut byte[..]).to_fallible())
                    .unwrap(),
                1
            );
            assert_eq!(byte[0], *expected);
        }
        let mut eof = [0];
        assert_eq!(
            BootIdFileOps
                .read_at(37, &mut VmWriter::from(&mut eof[..]).to_fallible())
                .unwrap(),
            0
        );
    }

    #[ktest]
    fn proc_boot_id_rejects_mutation() {
        let original = boot_identity::boot_id();
        let result = BootIdFileOps.write_at(0, &mut VmReader::from(&b"changed"[..]).to_fallible());
        assert_eq!(result.unwrap_err().error(), Errno::EPERM);
        assert_eq!(boot_identity::boot_id(), original);
    }
}
