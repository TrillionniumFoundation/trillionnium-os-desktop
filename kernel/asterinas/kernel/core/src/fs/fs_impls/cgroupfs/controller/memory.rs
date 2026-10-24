// SPDX-License-Identifier: MPL-2.0

use alloc::sync::Arc;

use aster_systree::{Error, MAX_ATTR_SIZE, Result, SysAttrSetBuilder, SysPerms, SysStr};
use aster_util::printer::VmPrinter;
use ostd::mm::{PAGE_SIZE, VmReader, VmWriter};

use crate::{util::ReadCString, vm::user_memory::hierarchy::MemoryDomain};

/// Admission for the original user-data/selected IPC frame metadata. This is
/// intentionally not Linux's complete kernel-memory, reclaim or OOM subsystem.
pub(crate) struct MemoryController {
    pub(super) domain: Arc<MemoryDomain>,
}

impl MemoryController {
    pub(super) fn init_attr_set(builder: &mut SysAttrSetBuilder, is_root: bool) {
        if !is_root {
            for name in ["memory.current", "memory.events"] {
                builder.add(SysStr::from(name), SysPerms::DEFAULT_RO_ATTR_PERMS);
            }
            builder.add(SysStr::from("memory.max"), SysPerms::DEFAULT_RW_ATTR_PERMS);
        }
    }
}

impl super::SubControl for MemoryController {
    fn is_attr_absent(&self, _name: &str) -> bool {
        !self.domain.snapshot().active
    }

    fn read_attr_at(&self, name: &str, offset: usize, writer: &mut VmWriter) -> Result<usize> {
        let snapshot = self.domain.snapshot();
        if !snapshot.active {
            return Err(Error::IsDead);
        }
        let mut printer = VmPrinter::new_skip(writer, offset);
        match name {
            "memory.current" => writeln!(printer, "{}", snapshot.pages * PAGE_SIZE)?,
            "memory.max" => match snapshot.max_pages {
                Some(pages) => writeln!(printer, "{}", pages * PAGE_SIZE)?,
                None => writeln!(printer, "max")?,
            },
            "memory.events" => writeln!(printer, "max {}", snapshot.max_events)?,
            _ => return Err(Error::AttributeError),
        }
        Ok(printer.bytes_written())
    }

    fn write_attr(&self, name: &str, reader: &mut VmReader) -> Result<usize> {
        if name != "memory.max" {
            return Err(Error::AttributeError);
        }
        // User copies, parsing and formatting never occur in the IRQ transaction.
        let (content, len) = reader
            .read_cstring_until_end(MAX_ATTR_SIZE)
            .map_err(|_| Error::PageFault)?;
        let value = content
            .to_str()
            .map_err(|_| Error::InvalidOperation)?
            .trim();
        let pages = parse_max(value).ok_or(Error::InvalidOperation)?;
        if !self.domain.set_max(pages) {
            return Err(Error::ResourceUnavailable);
        }
        Ok(len)
    }
}

fn parse_max(value: &str) -> Option<Option<usize>> {
    if value == "max" {
        return Some(None);
    }
    // Reject signs, empty strings and a rounded byte count that cannot be read
    // back. Linux rounds byte limits to pages; this controller does likewise.
    if value.is_empty() || !value.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    let bytes = value.parse::<usize>().ok()?;
    let rounded = bytes.checked_add(PAGE_SIZE - 1)? / PAGE_SIZE;
    rounded.checked_mul(PAGE_SIZE)?;
    Some(Some(rounded))
}

impl super::SubControlStatic for MemoryController {
    fn new(_is_root: bool, _is_active: bool) -> Self {
        unreachable!("memory identity requires its stable parent domain")
    }
    fn type_() -> super::SubCtrlType {
        super::SubCtrlType::Memory
    }
    fn read_from(controller: &super::Controller) -> Arc<super::SubController<Self>> {
        controller.memory.clone()
    }
}

#[cfg(ktest)]
mod tests;
