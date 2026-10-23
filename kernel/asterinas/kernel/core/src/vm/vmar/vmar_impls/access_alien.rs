// SPDX-License-Identifier: MPL-2.0

//! This module enables access to a VMAR
//! from an [_alien thread_] (crate::process::posix_thread::alien_access),
//! which is a non-member of the owner process of the VMAR.

use align_ext::AlignExt;
use ostd::{
    mm::{PageFlags, UFrame, io::util::HasVmReaderWriter, vm_space::VmQueriedItem},
    task::disable_preempt,
};

use super::{Vmar, is_userspace_vaddr};
use crate::{
    prelude::*,
    vm::vmar::{PageFaultInfo, is_userspace_vaddr_range},
};

impl Vmar {
    /// Reads memory in the context of an alien thread.
    ///
    /// This method reads until one of the conditions is met:
    /// 1. The writer has no available space.
    /// 2. Reading from the process user space or writing to the writer encounters some error.
    ///
    /// On success, the number of bytes read is returned;
    /// On error, both the error and the number of bytes read so far are returned.
    ///
    /// The `VmSpace` of the process is not required to be activated on the current CPU.
    pub(crate) fn read_alien(
        &self,
        vaddr: Vaddr,
        writer: &mut VmWriter,
    ) -> Result<usize, (Error, usize)> {
        let len = writer.avail();
        let read = |frame: UFrame, skip_offset: usize| {
            let mut reader = frame.reader();
            reader.skip(skip_offset);
            reader.read_fallible(writer)
        };

        self.access_alien(vaddr, len, PageFlags::R, read)
    }

    /// Writes memory in the context of an alien thread.
    ///
    /// This method writes until one of the conditions is met:
    /// 1. The reader has no remaining data.
    /// 2. Reading from the reader or writing to the process user space encounters some error.
    ///
    /// On success, the number of bytes written is returned;
    /// On error, both the error and the number of bytes written so far are returned.
    ///
    /// The `VmSpace` of the process is not required to be activated on the current CPU.
    pub(crate) fn write_alien(
        &self,
        vaddr: Vaddr,
        reader: &mut VmReader,
    ) -> Result<usize, (Error, usize)> {
        // Check at use, not just /proc/mem open or ptrace attach: a descriptor
        // may already exist or may have been transferred to another Process.
        // The seal is installed before the initial Process can be discovered;
        // it never reverts during this VMAR's lifetime. Do not hold `inner`
        // across page faults, which need to acquire that same lock.
        if self.has_sealed_initial_image() {
            return Err((
                Error::with_message(
                    Errno::EPERM,
                    "alien writes to a trusted initial image are forbidden",
                ),
                0,
            ));
        }
        let len = reader.remain();
        let write = |frame: UFrame, skip_offset: usize| {
            let mut writer = frame.writer();
            writer.skip(skip_offset);
            writer.write_fallible(reader)
        };

        self.access_alien(vaddr, len, PageFlags::W, write)
    }

    /// Writes zeros in the context of an alien thread.
    ///
    /// This method writes at most `len` bytes of zeros to the process user space.
    /// On success, the number of bytes written is returned; on error, both the
    /// error and the number of bytes written so far are returned.
    ///
    /// The `VmSpace` of the process is not required to be activated on the current CPU.
    pub(crate) fn fill_zeros_alien(
        &self,
        vaddr: Vaddr,
        len: usize,
    ) -> Result<usize, (Error, usize)> {
        let mut remain = len;
        let write = |frame: UFrame, skip_offset: usize| {
            let mut writer = frame.writer();
            writer.skip(skip_offset);
            let res = writer.fill_zeros(remain);
            remain -= res;
            Ok(res)
        };

        self.access_alien(vaddr, len, PageFlags::W, write)
    }

    /// Accesses memory at `vaddr..vaddr+len` in the context of an alien thread using `op`.
    ///
    /// The `VmSpace` of the process is not required to be activated on the current CPU.
    /// If any page in the range is not mapped or does not have the required page
    /// flags, a page fault will be handled to try to make the page accessible.
    fn access_alien<F>(
        &self,
        vaddr: Vaddr,
        len: usize,
        required_page_flags: PageFlags,
        mut op: F,
    ) -> Result<usize, (Error, usize)>
    where
        F: FnMut(UFrame, usize) -> Result<usize, (ostd::Error, usize)>,
    {
        // Cover both write_alien and fill_zeros_alien at the shared write
        // entry. A stale proc-mem VMAR pin cannot bypass this check. Admission
        // keeps only a counter while faults and user copies run below.
        #[cfg(any(ktest, feature = "g1c-trusted-observe"))]
        let _external_write = if required_page_flags.contains(PageFlags::W) {
            Some(self.enter_external_mutation().map_err(|error| (error, 0))?)
        } else {
            None
        };
        if len == 0 {
            return Ok(0);
        }

        if !is_userspace_vaddr_range(vaddr, len) {
            return Err((
                Error::with_message(Errno::EINVAL, "the address range is not in userspace"),
                0,
            ));
        }
        let range = vaddr.align_down(PAGE_SIZE)..(vaddr + len).align_up(PAGE_SIZE);

        let mut current_va = range.start;
        let mut bytes = 0;

        while current_va < range.end {
            let frame = self
                .query_page_with_required_flags(current_va, required_page_flags)
                .map_err(|err| (err, bytes))?;

            let skip_offset = if current_va == range.start {
                vaddr - range.start
            } else {
                0
            };
            match op(frame, skip_offset) {
                Ok(n) => bytes += n,
                Err((err, n)) => return Err((err.into(), bytes + n)),
            }

            current_va += PAGE_SIZE;
        }

        Ok(bytes)
    }

    fn query_page_with_required_flags(
        &self,
        vaddr: Vaddr,
        required_page_flags: PageFlags,
    ) -> Result<UFrame> {
        debug_assert!(is_userspace_vaddr(vaddr) && vaddr.is_multiple_of(PAGE_SIZE));

        let vmspace = self.vm_space();

        loop {
            let preempt_guard = disable_preempt();
            let mut cursor = vmspace.cursor(&preempt_guard, &(vaddr..vaddr + PAGE_SIZE))?;

            match cursor.query()?.1 {
                Some(vm_item) if vm_item.prop().flags.contains(required_page_flags) => {
                    match vm_item {
                        VmQueriedItem::MappedRam { frame, .. } => return Ok((*frame).clone()),
                        VmQueriedItem::MappedIoMem { .. } => {
                            return_errno_with_message!(
                                Errno::EOPNOTSUPP,
                                "accessing alien MMIO memory is not supported currently"
                            );
                        }
                    }
                }
                Some(_) | None => (),
            }

            drop(cursor);
            drop(preempt_guard);

            let page_fault_info = PageFaultInfo::new(vaddr, required_page_flags.into()).force();
            self.handle_page_fault(&page_fault_info)?;

            // Note that we are not holding `self.inner.lock()` here. Therefore, in race conditions
            // (e.g., if the mapping is removed concurrently), we will need to try again. The same
            // is true for real page faults; they may occur more than once at the same address.
        }
    }
}

#[cfg(ktest)]
mod external_fence_tests {
    use ostd::prelude::ktest;

    use super::*;
    use crate::{
        process::test_util,
        vm::{page_cache::VmoOptions, perms::VmPerms, vmar::VmarMapOffset},
    };

    #[ktest]
    fn actual_alien_write_admission_blocks_fencing_until_the_copy_finishes() {
        let (process, _task) = test_util::new_unstarted_process();
        let vmar_guard = process.lock_vmar();
        let vmar = vmar_guard.as_ref().unwrap();
        let base = 0x400000;
        let ram = VmoOptions::new(PAGE_SIZE).alloc().unwrap();
        vmar.new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
            .vmo(ram)
            .offset(VmarMapOffset::FixedNoReplace(base))
            .build()
            .unwrap();
        let mut reader = VmReader::from(&[0x33u8][..]).to_fallible();
        assert_eq!(
            vmar.access_alien(base, 1, PageFlags::W, |frame, _| {
                assert_eq!(
                    vmar.prepare_external_write_fence().err().unwrap().error(),
                    Errno::EBUSY
                );
                frame.writer().write_fallible(&mut reader)
            })
            .unwrap(),
            1
        );
        vmar.prepare_external_write_fence().unwrap().commit();
        let (error, changed) = vmar.fill_zeros_alien(base, 1).unwrap_err();
        assert_eq!(error.error(), Errno::EPERM);
        assert_eq!(changed, 0);
        let mut value = [0u8; 1];
        vmar.read_alien(base, &mut VmWriter::from(&mut value[..]).to_fallible())
            .unwrap();
        assert_eq!(value, [0x33]);
    }
}
