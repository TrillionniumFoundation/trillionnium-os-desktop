// SPDX-License-Identifier: MPL-2.0

//! Physical page ownership for covered user, stack and IPC allocation paths,
//! not Linux `memory.max`.
//! Kernel heap allocations, DMA and allocations without a process are
//! excluded. A frame keeps its first allocating process's original account.

use aster_systree::{
    Error as AttrError, MAX_ATTR_SIZE, Result as AttrResult, SysAttrSetBuilder, SysPerms, SysStr,
};
use aster_util::printer::VmPrinter;
use ostd::{
    impl_untyped_frame_meta_for,
    mm::{FrameAllocOptions, USegment},
    sync::LocalIrqDisabled,
};

use super::super::{CgroupSysNode, CgroupSystem};
use crate::{prelude::*, process::Process};

/// Distinguishes the physical allocation paths, rather than mapping counts.
#[derive(Clone, Copy, Debug)]
pub(crate) enum PageKind {
    Private = 0,
    AnonymousVmo = 1,
    FileCache = 2,
    PageTable = 3,
    KernelStack = 4,
    Ipc = 5,
}

#[derive(Debug)]
pub(crate) struct PageMemoryBudget {
    parent: Option<Arc<Self>>,
    state: SpinLock<State, LocalIrqDisabled>,
}

#[derive(Debug)]
struct State {
    current: usize,
    kinds: [usize; 6],
    max: usize,
    denied: u64,
}

impl PageMemoryBudget {
    pub(super) fn new(parent: Option<Arc<Self>>) -> Arc<Self> {
        Arc::new(Self {
            parent,
            state: SpinLock::new(State {
                current: 0,
                kinds: [0; 6],
                max: usize::MAX,
                denied: 0,
            }),
        })
    }

    pub(super) fn init_attr_set(builder: &mut SysAttrSetBuilder) {
        for name in ["hepta.page.current", "hepta.page.stat", "hepta.page.events"] {
            builder.add(SysStr::from(name), SysPerms::DEFAULT_RO_ATTR_PERMS);
        }
        builder.add(
            SysStr::from("hepta.page.max"),
            SysPerms::DEFAULT_RW_ATTR_PERMS,
        );
    }

    fn ancestors(&self) -> impl Iterator<Item = &Self> {
        core::iter::successors(Some(self), |node| node.parent.as_deref())
    }

    /// Reserves every ancestor before physical allocation. Lock order is one
    /// account at a time; no allocator, I/O or sleeping operation runs locked.
    /// Partial reservations can only make concurrent admission conservative.
    pub(super) fn charge(self: &Arc<Self>, kind: PageKind, bytes: usize) -> Result<PageCharge> {
        debug_assert!(bytes.is_multiple_of(PAGE_SIZE));
        for node in self.ancestors() {
            let accepted = {
                let mut state = node.state.lock();
                match state.current.checked_add(bytes) {
                    Some(next) if next <= state.max => {
                        state.current = next;
                        // The class count cannot exceed the checked total.
                        state.kinds[kind as usize] += bytes;
                        true
                    }
                    _ => {
                        state.denied = state.denied.saturating_add(1);
                        false
                    }
                }
            };
            if !accepted {
                for charged in self.ancestors().take_while(|n| !core::ptr::eq(*n, node)) {
                    charged.refund(kind, bytes);
                }
                return_errno_with_message!(Errno::ENOMEM, "physical page budget exhausted");
            }
        }
        Ok(PageCharge {
            owner: Some(self.clone()),
            kind,
            bytes,
        })
    }

    fn refund(&self, kind: PageKind, bytes: usize) {
        let mut state = self.state.lock();
        debug_assert!(state.current >= bytes && state.kinds[kind as usize] >= bytes);
        state.current -= bytes;
        state.kinds[kind as usize] -= bytes;
    }

    fn set_max(&self, max: usize) -> AttrResult<()> {
        let mut state = self.state.lock();
        if max < state.current {
            return Err(AttrError::InvalidOperation);
        }
        state.max = max;
        Ok(())
    }

    pub(super) fn read_attr_at(
        &self,
        name: &str,
        offset: usize,
        writer: &mut VmWriter,
    ) -> AttrResult<usize> {
        let (current, kinds, max, denied) = {
            let state = self.state.lock();
            (state.current, state.kinds, state.max, state.denied)
        };
        let mut printer = VmPrinter::new_skip(writer, offset);
        match name {
            "hepta.page.current" => writeln!(printer, "{current}")?,
            "hepta.page.max" if max == usize::MAX => writeln!(printer, "max")?,
            "hepta.page.max" => writeln!(printer, "{max}")?,
            "hepta.page.events" => writeln!(printer, "max {denied}")?,
            "hepta.page.stat" => writeln!(
                printer,
                "private {}\nanonymous_vmo {}\nfile_cache {}\npage_table {}\nkernel_stack {}\nipc {}",
                kinds[0], kinds[1], kinds[2], kinds[3], kinds[4], kinds[5]
            )?,
            _ => return Err(AttrError::AttributeError),
        }
        Ok(printer.bytes_written())
    }

    pub(super) fn write_attr(&self, name: &str, reader: &mut VmReader) -> AttrResult<usize> {
        if name != "hepta.page.max" {
            return Err(AttrError::AttributeError);
        }
        let (content, len) = reader
            .read_cstring_until_end(MAX_ATTR_SIZE)
            .map_err(|_| AttrError::PageFault)?;
        let value = content
            .to_str()
            .map_err(|_| AttrError::InvalidOperation)?
            .trim();
        let max = if value == "max" {
            usize::MAX
        } else {
            value
                .parse::<usize>()
                .map_err(|_| AttrError::InvalidOperation)?
        };
        self.set_max(max)?;
        Ok(len)
    }
}

/// Owned by frame metadata. A contiguous reservation is split without a heap
/// allocation, so failure drops both initialized frames and the unused tail.
#[derive(Debug)]
pub(crate) struct PageCharge {
    owner: Option<Arc<PageMemoryBudget>>,
    kind: PageKind,
    bytes: usize,
}

impl_untyped_frame_meta_for!(PageCharge);

impl PageCharge {
    pub(super) fn unaccounted(kind: PageKind, bytes: usize) -> Self {
        Self {
            owner: None,
            kind,
            bytes,
        }
    }

    pub(crate) fn split_page(&mut self) -> Self {
        assert!(
            self.bytes >= PAGE_SIZE,
            "frame metadata exceeded its reservation"
        );
        self.bytes -= PAGE_SIZE;
        Self {
            owner: self.owner.clone(),
            kind: self.kind,
            bytes: PAGE_SIZE,
        }
    }
}

impl Drop for PageCharge {
    fn drop(&mut self) {
        if let Some(owner) = &self.owner {
            for node in owner.ancestors() {
                node.refund(self.kind, self.bytes);
            }
        }
    }
}

/// Captures membership before charging; migration changes only later pages.
/// Existing shared pages are not charged again when accessed by another task.
pub(crate) fn charge_current_pages(kind: PageKind, bytes: usize) -> Result<PageCharge> {
    let Some(process) = Process::current() else {
        return Ok(PageCharge::unaccounted(kind, bytes));
    };
    let owner = {
        let membership = process.cgroup();
        match membership.get() {
            Some(node) => node.controller().page_memory.clone(),
            None => CgroupSystem::singleton().controller().page_memory.clone(),
        }
    };
    owner.charge(kind, bytes)
}

/// Allocates real IPC buffer frames after reserving the creating process's
/// original account. Each frame retains its own charge through all peer/FD
/// references; closing one endpoint cannot refund still-live backing memory.
pub(crate) fn alloc_ipc_segment(bytes: usize) -> Result<USegment> {
    if bytes == 0 || !bytes.is_multiple_of(PAGE_SIZE) || bytes > isize::MAX as usize {
        return_errno!(Errno::EINVAL);
    }
    let charge = charge_current_pages(PageKind::Ipc, bytes)?;
    allocate_ipc_segment(charge)
}

fn allocate_ipc_segment(mut charge: PageCharge) -> Result<USegment> {
    let bytes = charge.bytes;
    Ok(FrameAllocOptions::new()
        .zeroed(false)
        .alloc_segment_with(bytes / PAGE_SIZE, |_| charge.split_page())?
        .into())
}

/// Runs under the page-table cursor's atomic guard. Membership reads use RCU;
/// charge locks never sleep or re-enter page-table code. Each token keeps the
/// account captured for this individual physical node until Frame destruction.
pub(crate) fn charge_current_page_table()
-> ostd::Result<Box<dyn ostd::mm::vm_space::PageTableCharge>> {
    let charge =
        charge_current_pages(PageKind::PageTable, PAGE_SIZE).map_err(|_| ostd::Error::NoMemory)?;
    Ok(Box::new(charge))
}

impl ostd::task::StackReservation for PageCharge {
    fn split_page(&mut self) -> Box<dyn ostd::task::StackPageCharge> {
        Box::new(PageCharge::split_page(self))
    }
}

/// Captures one original account for all frames of this stack before any
/// physical allocation; each split token independently refunds its real frame.
pub(crate) fn charge_current_kernel_stack(
    bytes: usize,
) -> ostd::Result<Box<dyn ostd::task::StackReservation>> {
    let charge =
        charge_current_pages(PageKind::KernelStack, bytes).map_err(|_| ostd::Error::NoMemory)?;
    Ok(Box::new(charge))
}

#[cfg(ktest)]
mod tests;
