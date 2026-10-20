// SPDX-License-Identifier: MPL-2.0

use core::ops::Range;

use super::{Vmar, VmarInner};
use crate::prelude::*;

#[cfg(any(ktest, feature = "g1c-trusted-observe"))]
use super::Interval;
#[cfg(any(ktest, feature = "g1c-trusted-observe"))]
use crate::vm::perms::VmPerms;

impl Vmar {
    /// Seals the initial image before its sole task is published or run.
    ///
    /// The loader must already have verified the private RAM contents, final
    /// permissions and entry point. Every executable mapping is included here,
    /// including the kernel's vDSO text. The ranges remain sealed until VMAR
    /// teardown, even after the associated Process image loses its authority.
    /// A fork creates another VMAR without this seal and without a grant.
    ///
    /// Installation requires an unpublished, single-handle VMAR. Consequently
    /// no alien access can have passed a pre-seal check and still be in flight.
    /// After installation this field only changes when the VMAR is destroyed.
    /// Mapping checks and mutations share `inner`; no Process or CPU owner lock
    /// is acquired while holding it.
    #[cfg(any(ktest, feature = "g1c-trusted-observe"))]
    pub(crate) fn seal_initial_image(&self, mut ranges: Vec<Range<Vaddr>>) -> Result<()> {
        if self.has_multiple_handles() || ranges.is_empty() {
            return_errno_with_message!(Errno::EINVAL, "initial image is not exclusively prepared")
        }
        let mut inner = self.inner.write();
        if inner.sealed_initial_ranges.is_some() {
            return_errno_with_message!(Errno::EPERM, "initial image is already sealed")
        }
        for range in &ranges {
            if range.is_empty()
                || !range.start.is_multiple_of(PAGE_SIZE)
                || !range.end.is_multiple_of(PAGE_SIZE)
            {
                return_errno_with_message!(Errno::EINVAL, "invalid initial image seal range")
            }
            let mut end = range.start;
            for mapping in inner.vm_mappings.find(range) {
                if mapping.map_to_addr() > end {
                    return_errno_with_message!(Errno::EINVAL, "initial image contains an unmapped hole")
                }
                end = mapping.map_end();
            }
            if end < range.end {
                return_errno_with_message!(Errno::EINVAL, "initial image contains an unmapped hole")
            }
        }
        for mapping in inner.vm_mappings.iter() {
            if mapping.perms().contains(VmPerms::EXEC) {
                if mapping.perms().contains(VmPerms::WRITE) {
                    return_errno_with_message!(Errno::EPERM, "initial image contains writable executable pages")
                }
                ranges.push(mapping.range());
            }
        }
        inner.sealed_initial_ranges = Some(ranges);
        Ok(())
    }

    pub(crate) fn has_sealed_initial_image(&self) -> bool {
        self.inner.read().sealed_initial_ranges.is_some()
    }
}

#[cfg(ktest)]
mod tests {
    use ostd::{prelude::ktest, task::Task};

    use super::*;
    use crate::{
        process::{Process, test_util},
        vm::{page_cache::VmoOptions, vmar::{RemapOldMappingAction, VmarMapOffset}},
    };

    const BASE: usize = 0x400000;

    fn fixture(perms: VmPerms) -> (Arc<Process>, Arc<Task>, Arc<Vmar>) {
        let (process, task) = test_util::new_unstarted_process();
        let vmar = process.lock_vmar().unwrap().weak_self.upgrade().unwrap();
        let ram = VmoOptions::new(PAGE_SIZE).alloc().unwrap();
        ram.write(0, &mut VmReader::from(&[0x5au8][..]).to_fallible()).unwrap();
        vmar.new_map(PAGE_SIZE, perms).vmo(ram)
            .offset(VmarMapOffset::FixedNoReplace(BASE)).build().unwrap();
        (process, task, vmar)
    }

    fn byte(vmar: &Vmar) -> u8 {
        let mut byte = [0u8; 1];
        assert_eq!(vmar.read_alien(BASE, &mut VmWriter::from(&mut byte[..]).to_fallible()).unwrap(), 1);
        byte[0]
    }

    fn denied<T>(result: Result<T>) {
        assert_eq!(result.err().unwrap().error(), Errno::EPERM);
    }

    #[ktest]
    fn initial_image_seal_preserves_bytes_across_mapping_replacement_attempts() {
        let (_process, _task, vmar) = fixture(VmPerms::READ | VmPerms::EXEC);
        vmar.seal_initial_image(vec![BASE..BASE + PAGE_SIZE]).unwrap();
        denied(vmar.new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE)
            .offset(VmarMapOffset::FixedReplace(BASE)).build());
        denied(vmar.remove_mapping(BASE..BASE + PAGE_SIZE));
        denied(vmar.discard_pages(BASE..BASE + PAGE_SIZE));
        denied(vmar.remap(BASE, PAGE_SIZE, Some(BASE + 2 * PAGE_SIZE), PAGE_SIZE, RemapOldMappingAction::Unmap));
        denied(vmar.resize_mapping(BASE, PAGE_SIZE, PAGE_SIZE * 2, true));
        assert_eq!(byte(&vmar), 0x5a);
        assert!(vmar.query(BASE..BASE + PAGE_SIZE).is_fully_mapped());
    }

    #[ktest]
    fn initial_image_seal_allows_relro_but_never_readds_permissions() {
        let (_process, _task, vmar) = fixture(VmPerms::READ | VmPerms::WRITE);
        vmar.seal_initial_image(vec![BASE..BASE + PAGE_SIZE]).unwrap();
        vmar.protect(VmPerms::READ, BASE..BASE + PAGE_SIZE).unwrap();
        denied(vmar.protect(VmPerms::READ | VmPerms::WRITE, BASE..BASE + PAGE_SIZE));
        denied(vmar.protect(VmPerms::READ | VmPerms::EXEC, BASE..BASE + PAGE_SIZE));
        denied(vmar.new_map(PAGE_SIZE, VmPerms::READ | VmPerms::EXEC).build());
        let heap = vmar.new_map(PAGE_SIZE, VmPerms::READ | VmPerms::WRITE).build().unwrap();
        denied(vmar.protect(VmPerms::READ | VmPerms::EXEC, heap..heap + PAGE_SIZE));
        vmar.remove_mapping(heap..heap + PAGE_SIZE).unwrap();
        assert_eq!(byte(&vmar), 0x5a);
    }

    #[ktest]
    fn initial_image_seal_rechecks_alien_write_using_an_earlier_vmar_pin() {
        let (_process, _task, vmar) = fixture(VmPerms::READ | VmPerms::WRITE);
        // This pin models the original VMAR captured when a proc-mem file is
        // opened. The production write method must independently reject it.
        let opened_before_seal = vmar.clone();
        assert_eq!(byte(&opened_before_seal), 0x5a);
        vmar.seal_initial_image(vec![BASE..BASE + PAGE_SIZE]).unwrap();
        let (error, written) = opened_before_seal.write_alien(
            BASE, &mut VmReader::from(&[0x33u8][..]).to_fallible(),
        ).unwrap_err();
        assert_eq!(error.error(), Errno::EPERM);
        assert_eq!(written, 0);
        assert_eq!(byte(&vmar), 0x5a);
    }

    #[ktest]
    fn initial_image_seal_does_not_turn_fork_into_a_shared_writable_alias() {
        let (process, _task, vmar) = fixture(VmPerms::READ | VmPerms::EXEC);
        test_util::initialize_heap_for_fork(&process, BASE + 2 * PAGE_SIZE);
        assert_eq!(byte(&vmar), 0x5a);
        vmar.seal_initial_image(vec![BASE..BASE + PAGE_SIZE]).unwrap();
        let child = Vmar::fork_from(&vmar);
        assert!(!child.has_sealed_initial_image());
        child.protect(VmPerms::READ | VmPerms::WRITE, BASE..BASE + PAGE_SIZE).unwrap();
        child.write_alien(BASE, &mut VmReader::from(&[0x33u8][..]).to_fallible()).unwrap();
        assert_eq!(byte(&child), 0x33);
        assert_eq!(byte(&vmar), 0x5a);
    }
}

impl VmarInner {
    pub(super) fn intersects_initial_image(&self, range: &Range<Vaddr>) -> bool {
        self.sealed_initial_ranges.as_ref().is_some_and(|ranges| {
            ranges.iter().any(|sealed| range.start < sealed.end && sealed.start < range.end)
        })
    }

    pub(super) fn check_initial_image_not_replaced(&self, range: &Range<Vaddr>) -> Result<()> {
        if self.intersects_initial_image(range) {
            return_errno_with_message!(Errno::EPERM, "trusted initial image mapping is sealed")
        }
        Ok(())
    }

    pub(super) fn check_initial_image_no_remap(&self) -> Result<()> {
        if self.sealed_initial_ranges.is_some() {
            return_errno_with_message!(Errno::EPERM, "trusted initial profile does not allow remap aliases")
        }
        Ok(())
    }
}
