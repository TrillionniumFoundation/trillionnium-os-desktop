// SPDX-License-Identifier: MPL-2.0

use alloc::format;

use aster_util::printer::VmPrinter;

use crate::{
    device::misc::hepta_boot_id,
    fs::{
        file::{InodeType, mkmod},
        procfs::{
            StaticEntry,
            template::{
                ProcDir, ProcDirOps, ProcFile, ProcFileOps, ReaddirEntry,
                listed_entries_from_table, lookup_child_from_table, visit_listed_entries,
            },
        },
        vfs::inode::Inode,
    },
    prelude::*,
};

pub(super) struct RandomDirOps;

impl RandomDirOps {
    pub(super) fn new_inode(parent: Weak<dyn Inode>) -> Arc<dyn Inode> {
        ProcDir::new(Self, parent, mkmod!(a+rx))
    }

    const ENTRIES: &'static [StaticEntry] =
        &[("boot_id", InodeType::File, BootIdFileOps::new_inode)];
}

impl ProcDirOps for RandomDirOps {
    fn lookup_child(&self, this: &ProcDir<Self>, name: &str) -> Result<Arc<dyn Inode>> {
        lookup_child_from_table(name, Self::ENTRIES, |f| f(this.this_weak().clone()))
            .ok_or_else(|| Error::with_message(Errno::ENOENT, "random sysctl is not implemented"))
    }

    fn visit_entries_from_offset<'a, F>(&'a self, offset: usize, visit: F) -> Result<()>
    where
        F: FnMut(ReaddirEntry<'a>) -> Result<()>,
    {
        visit_listed_entries(offset, listed_entries_from_table(Self::ENTRIES), visit)
    }
}

struct BootIdFileOps;

impl BootIdFileOps {
    fn new_inode(parent: Weak<dyn Inode>) -> Arc<dyn Inode> {
        ProcFile::new(Self, parent, mkmod!(a+r))
    }
}

fn format_boot_id(id: &[u8; 16]) -> String {
    format!(
        "{:02x}{:02x}{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}-{:02x}{:02x}{:02x}{:02x}{:02x}{:02x}\n",
        id[0],
        id[1],
        id[2],
        id[3],
        id[4],
        id[5],
        id[6],
        id[7],
        id[8],
        id[9],
        id[10],
        id[11],
        id[12],
        id[13],
        id[14],
        id[15],
    )
}

impl ProcFileOps for BootIdFileOps {
    fn read_at(&self, offset: usize, writer: &mut VmWriter) -> Result<usize> {
        let id = hepta_boot_id()?;
        let mut printer = VmPrinter::new_skip(writer, offset);
        write!(printer, "{}", format_boot_id(&id))?;
        Ok(printer.bytes_written())
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::prelude::ktest;

    use super::*;

    #[ktest]
    fn boot_id_text_preserves_all_original_wire_bytes() {
        assert_eq!(
            format_boot_id(&[0, 1, 2, 3, 4, 5, 0x46, 7, 0x88, 9, 10, 11, 12, 13, 14, 15]),
            "00010203-0405-4607-8809-0a0b0c0d0e0f\n"
        );
        assert_eq!(
            format_boot_id(&[255; 16]),
            "ffffffff-ffff-ffff-ffff-ffffffffffff\n"
        );
    }
}
