// SPDX-License-Identifier: MPL-2.0

//! Physical anonymous/COW page accounting. This is intentionally a private
//! extension, not Linux memory.max: page cache, shared VMO, page tables and
//! kernel/device allocations are outside its coverage.

use aster_systree::{
    Error as AttrError, MAX_ATTR_SIZE, Result as AttrResult, SysAttrSetBuilder, SysPerms, SysStr,
};
use aster_util::printer::VmPrinter;
use ostd::{
    impl_untyped_frame_meta_for,
    mm::{FrameAllocOptions, UFrame},
    sync::LocalIrqDisabled,
};

use super::{
    super::{CgroupSysNode, CgroupSystem},
    page_memory::{PageCharge as MemoryPageCharge, PageKind, PageMemoryBudget},
};
use crate::{prelude::*, process::Process};

/// A stable account survives controller activation, migration and node deletion.
/// A frame retains its original account; COW charges the allocating process.
#[derive(Debug)]
pub(crate) struct AnonBudget {
    parent: Option<Arc<Self>>,
    state: SpinLock<State, LocalIrqDisabled>,
}

#[derive(Debug)]
struct State {
    current: usize,
    max: usize,
    denied: u64,
}

impl AnonBudget {
    pub(super) fn new(parent: Option<Arc<Self>>) -> Arc<Self> {
        Arc::new(Self {
            parent,
            state: SpinLock::new(State {
                current: 0,
                max: usize::MAX,
                denied: 0,
            }),
        })
    }

    pub(super) fn init_attr_set(builder: &mut SysAttrSetBuilder) {
        builder.add(
            SysStr::from("hepta.anon.max"),
            SysPerms::DEFAULT_RW_ATTR_PERMS,
        );
        builder.add(
            SysStr::from("hepta.anon.current"),
            SysPerms::DEFAULT_RO_ATTR_PERMS,
        );
        builder.add(
            SysStr::from("hepta.anon.events"),
            SysPerms::DEFAULT_RO_ATTR_PERMS,
        );
    }

    fn ancestors(&self) -> impl Iterator<Item = &Self> {
        core::iter::successors(Some(self), |node| node.parent.as_deref())
    }

    /// Reserves one physical page at every level. Check and increment share a
    /// lock with limit updates. Never holds two locks, allocates or sleeps.
    /// Partial reservations are conservative and roll back before returning an
    /// error, so concurrent allocators cannot exceed any ancestor's ceiling.
    fn charge(self: &Arc<Self>) -> Result<PageCharge> {
        for node in self.ancestors() {
            let accepted = {
                let mut state = node.state.lock();
                match state.current.checked_add(PAGE_SIZE) {
                    Some(next) if next <= state.max => {
                        state.current = next;
                        true
                    }
                    _ => {
                        state.denied = state.denied.saturating_add(1);
                        false
                    }
                }
            };
            if !accepted {
                for charged in self
                    .ancestors()
                    .take_while(|charged| !core::ptr::eq(*charged, node))
                {
                    charged.refund_one();
                }
                return_errno_with_message!(Errno::ENOMEM, "anonymous/COW page budget exhausted");
            }
        }
        Ok(PageCharge {
            owner: Some(self.clone()),
            memory: MemoryPageCharge::unaccounted(PageKind::Private, PAGE_SIZE),
        })
    }

    fn refund_one(&self) {
        let mut state = self.state.lock();
        debug_assert!(state.current >= PAGE_SIZE);
        state.current -= PAGE_SIZE;
    }

    fn set_max(&self, max: usize) -> AttrResult<()> {
        let mut state = self.state.lock();
        // No reclaim implementation: reject a reduction below committed use.
        // There is no interval where a successful update violates the ceiling.
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
        let (current, max, denied) = {
            let state = self.state.lock();
            (state.current, state.max, state.denied)
        };
        let mut printer = VmPrinter::new_skip(writer, offset);
        match name {
            "hepta.anon.current" => writeln!(printer, "{current}")?,
            "hepta.anon.max" if max == usize::MAX => writeln!(printer, "max")?,
            "hepta.anon.max" => writeln!(printer, "{max}")?,
            "hepta.anon.events" => writeln!(printer, "max {denied}")?,
            _ => return Err(AttrError::AttributeError),
        }
        Ok(printer.bytes_written())
    }

    pub(super) fn write_attr(&self, name: &str, reader: &mut VmReader) -> AttrResult<usize> {
        if name != "hepta.anon.max" {
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

/// The frame metadata is the charge owner, not the mapping or the allocating
/// task. Failed physical allocation drops it too. Shared fork references do
/// not duplicate charges; the final frame reference refunds exactly once.
#[derive(Debug)]
struct PageCharge {
    owner: Option<Arc<AnonBudget>>,
    memory: MemoryPageCharge,
}
impl_untyped_frame_meta_for!(PageCharge);

impl Drop for PageCharge {
    fn drop(&mut self) {
        if let Some(owner) = &self.owner {
            for node in owner.ancestors() {
                node.refund_one();
            }
        }
    }
}

fn allocate(owner: Option<&Arc<AnonBudget>>, zeroed: bool) -> Result<UFrame> {
    let charge = match owner {
        Some(owner) => owner.charge()?,
        None => PageCharge {
            owner: None,
            memory: MemoryPageCharge::unaccounted(PageKind::Private, PAGE_SIZE),
        },
    };
    Ok(FrameAllocOptions::new()
        .zeroed(zeroed)
        .alloc_frame_with(charge)?
        .into())
}

/// Called at the actual private-anonymous and COW allocation sites. A snapshot
/// of the allocating process's cgroup is the ownership linearization point.
/// Boot/test allocations without a process have no workload account.
pub(crate) fn alloc_anon_frame(zeroed: bool) -> Result<UFrame> {
    let Some(process) = Process::current() else {
        return allocate(None, zeroed);
    };
    let owner = {
        let membership = process.cgroup();
        match membership.get() {
            Some(node) => (
                node.controller().anon.clone(),
                node.controller().page_memory.clone(),
            ),
            None => {
                let controller = CgroupSystem::singleton().controller();
                (controller.anon.clone(), controller.page_memory.clone())
            }
        }
    };
    allocate_accounted(&owner.0, &owner.1, zeroed)
}

fn allocate_accounted(
    anon: &Arc<AnonBudget>,
    pages: &Arc<PageMemoryBudget>,
    zeroed: bool,
) -> Result<UFrame> {
    let memory = pages.charge(PageKind::Private, PAGE_SIZE)?;
    let mut charge = anon.charge()?;
    charge.memory = memory;
    Ok(FrameAllocOptions::new()
        .zeroed(zeroed)
        .alloc_frame_with(charge)?
        .into())
}

#[cfg(ktest)]
mod tests;
