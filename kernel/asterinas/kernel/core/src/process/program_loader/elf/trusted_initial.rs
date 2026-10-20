// SPDX-License-Identifier: MPL-2.0

//! The deliberately narrow, compile-time selected G1-c initial image profile.
//!
//! Path, PID, UID and userspace digests are not inputs to the authorization
//! decision. The bytes read exactly once from the opened executable must match
//! the reviewed bytes included in this kernel. Those same bytes initialize
//! private RAM VMOs; final mappings are read back and sealed before a token is
//! returned. Ordinary exec uses the unchanged general ELF loader.

use core::ops::Range;

use align_ext::AlignExt;

use super::{
    ElfHeaders, ElfLoadInfo,
    load_elf::init_aux_vec,
    relocate::RelocatedRange,
};
use crate::{
    fs::file::FileLike,
    prelude::*,
    process::process_vm::AuxKey,
    vm::{
        page_cache::VmoOptions,
        perms::VmPerms,
        vmar::{VMAR_LOWEST_ADDR, Vmar, VmarMapOffset},
    },
};

const EXPECTED_ELF: &[u8] = include_bytes!(env!("HEPTA_TRUSTED_INITIAL_ELF"));
#[cfg(not(target_arch = "x86_64"))]
compile_error!("g1c-trusted-observe is an explicitly x86_64-only experiment");
const MAX_FILE_BYTES: usize = 8 * 1024 * 1024;
const MAX_MAPPED_BYTES: usize = 16 * 1024 * 1024;
const MAX_LOAD_SEGMENTS: usize = 16;

/// Consumed only by the unique, stopped initial Process transaction.
/// No public constructor, Clone implementation or userspace representation.
pub(in crate::process) struct LoadedInitialImage {
    vmar: Arc<Vmar>,
    entry_point: Vaddr,
}

impl LoadedInitialImage {
    pub(in crate::process) fn consume(self, vmar: &Arc<Vmar>, entry: Vaddr) -> Result<()> {
        if !Arc::ptr_eq(&self.vmar, vmar)
            || self.entry_point != entry
            || !vmar.has_sealed_initial_image()
        {
            return_errno_with_message!(Errno::ESTALE, "trusted initial image binding changed")
        }
        Ok(())
    }
}

pub(in crate::process) fn load_trusted_initial(
    file: Arc<dyn FileLike>,
    vmar: Arc<Vmar>,
    argv: Vec<CString>,
    envp: Vec<CString>,
) -> Result<(ElfLoadInfo, LoadedInitialImage)> {
    if EXPECTED_ELF.is_empty() || EXPECTED_ELF.len() > MAX_FILE_BYTES {
        return_errno_with_message!(Errno::ENOEXEC, "trusted initial manifest exceeds profile bounds")
    }
    let mut snapshot = vec![0u8; EXPECTED_ELF.len()];
    let mut offset = 0;
    while offset < snapshot.len() {
        let read = file.read_bytes_at(offset, &mut snapshot[offset..])?;
        if read == 0 {
            println!("[hepta-g1c] rejected initial image: truncated-snapshot");
            return_errno_with_message!(Errno::ENOEXEC, "trusted initial image snapshot is truncated")
        }
        offset += read;
    }
    let mut extra = [0u8; 1];
    if file.read_bytes_at(snapshot.len(), &mut extra)? != 0 || snapshot.as_slice() != EXPECTED_ELF {
        println!("[hepta-g1c] rejected initial image: manifest-byte-mismatch");
        return_errno_with_message!(Errno::ENOEXEC, "trusted initial image bytes do not match kernel manifest")
    }
    // No later read, fault or mapping refers to the opened input or its inode.
    drop(file);
    let headers = ElfHeaders::parse(&snapshot)?;
    let segments = headers.loadable_phdrs();
    if headers.is_shared_object()
        || headers.interp_phdr().is_some()
        || headers.ph_count() > 64
        || segments.len() > MAX_LOAD_SEGMENTS
    {
        return_errno_with_message!(Errno::ENOEXEC, "trusted initial profile requires a static ET_EXEC")
    }

    let mut ranges: Vec<Range<Vaddr>> = Vec::with_capacity(segments.len() + 1);
    let mut total = 0usize;
    let mut entry_is_executable = false;
    for segment in segments {
        let virt = segment.virt_range();
        let range = virt.start.align_down(PAGE_SIZE)..virt.end.align_up(PAGE_SIZE);
        let perms = segment.vm_perms();
        total = total.checked_add(range.len()).ok_or_else(|| {
            Error::with_message(Errno::ENOEXEC, "trusted initial mapping size overflow")
        })?;
        if range.start < VMAR_LOWEST_ADDR
            || total > MAX_MAPPED_BYTES
            || segment.file_range().end > snapshot.len()
            || !perms.contains(VmPerms::READ)
            || perms.contains(VmPerms::WRITE | VmPerms::EXEC)
            || ranges.iter().any(|old| old.start < range.end && range.start < old.end)
        {
            return_errno_with_message!(
                Errno::ENOEXEC,
                "trusted initial LOAD pages violate the static profile"
            )
        }
        entry_is_executable |= perms.contains(VmPerms::EXEC) && virt.contains(&headers.entry_point());
        ranges.push(range);
    }
    if !entry_is_executable {
        return_errno_with_message!(Errno::ENOEXEC, "trusted initial entry is not executable")
    }

    for (segment, range) in segments.iter().zip(&ranges) {
        let mut expected = vec![0u8; range.len()];
        let file_range = segment.file_range();
        if !file_range.is_empty() {
            let source = file_range.start.align_down(PAGE_SIZE)..file_range.end;
            expected[..source.len()].copy_from_slice(&snapshot[source]);
        }
        let ram = VmoOptions::new(range.len()).alloc()?;
        ram.write(0, &mut VmReader::from(expected.as_slice()).to_fallible())?;
        vmar.new_map(range.len(), segment.vm_perms())
            .vmo(ram)
            .offset(VmarMapOffset::FixedNoReplace(range.start))
            .build()?;
    }

    let full = headers.calc_total_vaddr_bounds();
    let relocated = RelocatedRange::new(full.clone(), full.start).ok_or_else(|| {
        Error::with_message(Errno::ENOEXEC, "trusted initial address overflow")
    })?;
    let mut aux = init_aux_vec(&headers, &relocated, None)?;
    aux.set(AuxKey::AT_SECURE, 1);
    let boot = map_boot_page(&vmar)?;
    ranges.push(boot..boot + PAGE_SIZE);
    aux.set(AuxKey::AT_HEPTA_BOOT, boot as u64);
    #[cfg(not(target_arch = "loongarch64"))]
    if let Some(vdso_text) = super::load_elf::map_vdso_to_vmar(&vmar) {
        #[cfg(any(target_arch = "riscv64", target_arch = "aarch64"))]
        vmar.process_vm().set_vdso_base(vdso_text);
        aux.set(AuxKey::AT_SYSINFO_EHDR, vdso_text as u64);
    }
    let code = segments.iter().filter(|segment| segment.vm_perms().contains(VmPerms::EXEC))
        .map(|segment| segment.virt_range().clone())
        .reduce(|a, b| a.start.min(b.start)..a.end.max(b.end)).unwrap();
    let data = segments.iter().filter(|segment| segment.vm_perms().contains(VmPerms::WRITE))
        .map(|segment| segment.virt_range().clone())
        .reduce(|a, b| a.start.min(b.start)..a.end.max(b.end)).unwrap_or(full.end..full.end);
    vmar.process_vm().set_code_range(code);
    vmar.process_vm().set_data_range(data.clone());
    vmar.process_vm().map_and_write_init_stack(&vmar, argv, envp, aux)?;
    vmar.process_vm().map_and_init_heap(&vmar, data.len(), full.end.align_up(PAGE_SIZE))?;
    // Verify only after *all* loader mappings and initialization have finished.
    // In particular, a hostile ELF layout must not let stack/heap setup replace
    // a previously verified page between verification and token creation.
    for (segment, range) in segments.iter().zip(&ranges) {
        let mut expected = vec![0u8; range.len()];
        if !segment.file_range().is_empty() {
            let source = segment.file_range().start.align_down(PAGE_SIZE)..segment.file_range().end;
            expected[..source.len()].copy_from_slice(&snapshot[source]);
        }
        verify_mapping(&vmar, range.clone(), segment.vm_perms(), &expected)?;
    }
    verify_mapping(&vmar, boot..boot + PAGE_SIZE, VmPerms::READ, boot_page_bytes().as_slice())?;
    // All operations above precede publication. No later VM operation can
    // change the verified executable pages or introduce another executable.
    vmar.seal_initial_image(ranges)?;
    let entry_point = headers.entry_point();
    let info = ElfLoadInfo {
        entry_point,
        user_stack_top: vmar.process_vm().init_stack().user_stack_top(),
    };
    println!(
        "[hepta-g1c] trusted initial image committed: bytes={} entry={:#x}",
        snapshot.len(), entry_point
    );
    Ok((info, LoadedInitialImage { vmar, entry_point }))
}

fn boot_page_bytes() -> Box<[u8; PAGE_SIZE]> {
    let mut bytes = Box::new([0u8; PAGE_SIZE]);
    bytes[..8].copy_from_slice(b"HOS2BOOT");
    bytes[8..16].copy_from_slice(&1u64.to_le_bytes());
    bytes[16..24].copy_from_slice(&1u64.to_le_bytes());
    bytes[24..32].copy_from_slice(&1u64.to_le_bytes());
    bytes
}

fn map_boot_page(vmar: &Vmar) -> Result<Vaddr> {
    let bytes = boot_page_bytes();
    let ram = VmoOptions::new(PAGE_SIZE).alloc()?;
    ram.write(0, &mut VmReader::from(bytes.as_slice()).to_fallible())?;
    let addr = vmar.new_map(PAGE_SIZE, VmPerms::READ).vmo(ram).build()?;
    Ok(addr)
}

fn verify_mapping(vmar: &Vmar, range: Range<Vaddr>, perms: VmPerms, expected: &[u8]) -> Result<()> {
    {
        let query = vmar.query(range.clone());
        if !query.is_fully_mapped()
            || query.iter().any(|mapping| mapping.perms() & VmPerms::ALL_PERMS != perms)
        {
            return_errno_with_message!(Errno::ENOEXEC, "trusted initial final mapping permissions differ")
        }
    }
    let mut actual = vec![0u8; range.len()];
    let read = vmar.read_alien(range.start, &mut VmWriter::from(actual.as_mut_slice()).to_fallible())
        .map_err(|(error, _)| error)?;
    if read != actual.len() || actual.as_slice() != expected {
        return_errno_with_message!(Errno::ENOEXEC, "trusted initial final mapped bytes differ")
    }
    Ok(())
}
