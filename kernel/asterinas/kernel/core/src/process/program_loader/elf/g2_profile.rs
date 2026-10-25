// SPDX-License-Identifier: MPL-2.0

//! Bounded, allocation-free prerequisites for the opt-in native Agentd loader.
//! These are candidate loader limits, not a native application qualification.

use core::ops::Range;

pub(super) const MAX_FILE_BYTES: usize = 224 * 1024 * 1024;
pub(super) const MAX_MAPPED_BYTES: usize = 224 * 1024 * 1024;
pub(super) const CHUNK_BYTES: usize = 4096;
const MAX_PHDRS: usize = 64;
const MAX_LOADS: usize = 16;
const MAX_TLS_BYTES: u64 = 64 * 1024;
const MAX_TLS_ALIGN: u64 = 4096;

// xmas-elf/zero borrow the ELF64 header and program headers as aligned typed
// references. include_bytes! alone only guarantees byte alignment. Keep the
// authoritative copy aligned statically without a file-sized heap allocation.
#[repr(align(8))]
pub(super) struct AlignedElf<const N: usize>(pub(super) [u8; N]);

#[derive(Debug, PartialEq)]
pub(super) enum StreamError<E> {
    Read(E),
    Truncated,
    Mismatch,
    InvalidRead,
}

/// Checks every returned byte and an exact EOF before admitting the immutable
/// equal copy. Short reads are allowed. This proves equality of the sequence
/// actually read, not the existence of an atomic inode snapshot at one instant.
pub(super) fn verify_stream<E>(
    expected: &[u8],
    mut read: impl FnMut(usize, &mut [u8]) -> Result<usize, E>,
) -> Result<(), StreamError<E>> {
    let mut chunk = [0u8; CHUNK_BYTES];
    let mut offset = 0;
    while offset < expected.len() {
        let requested = (expected.len() - offset).min(chunk.len());
        let count = read(offset, &mut chunk[..requested]).map_err(StreamError::Read)?;
        if count > requested {
            return Err(StreamError::InvalidRead);
        }
        if count == 0 {
            return Err(StreamError::Truncated);
        }
        if chunk[..count] != expected[offset..offset + count] {
            return Err(StreamError::Mismatch);
        }
        offset += count;
    }
    match read(offset, &mut chunk[..1]).map_err(StreamError::Read)? {
        0 => Ok(()),
        1 => Err(StreamError::Mismatch),
        _ => Err(StreamError::InvalidRead),
    }
}

/// Reproduces the original loader's leading file-page prefix and zeroed BSS /
/// page tail, without allocating an entire LOAD segment.
pub(super) fn fill_load_chunk(
    image: &[u8],
    file: Range<usize>,
    offset: usize,
    destination: &mut [u8],
) -> Result<(), &'static str> {
    destination.fill(0);
    if file.is_empty() {
        return Ok(());
    }
    let source_start = file.start & !(CHUNK_BYTES - 1);
    let source = image
        .get(source_start..file.end)
        .ok_or("invalid LOAD file range")?;
    if offset < source.len() {
        let count = destination.len().min(source.len() - offset);
        destination[..count].copy_from_slice(&source[offset..offset + count]);
    }
    Ok(())
}

#[derive(Clone, Copy, Default)]
struct Load {
    file: u64,
    address: u64,
    file_size: u64,
    end: u64,
    start_page: u64,
    end_page: u64,
}

fn u16_at(image: &[u8], offset: usize) -> Result<u16, &'static str> {
    Ok(u16::from_le_bytes(
        image
            .get(offset..offset + 2)
            .ok_or("truncated ELF field")?
            .try_into()
            .unwrap(),
    ))
}

fn u32_at(image: &[u8], offset: usize) -> Result<u32, &'static str> {
    Ok(u32::from_le_bytes(
        image
            .get(offset..offset + 4)
            .ok_or("truncated ELF field")?
            .try_into()
            .unwrap(),
    ))
}

fn u64_at(image: &[u8], offset: usize) -> Result<u64, &'static str> {
    Ok(u64::from_le_bytes(
        image
            .get(offset..offset + 8)
            .ok_or("truncated ELF field")?
            .try_into()
            .unwrap(),
    ))
}

/// Additional G2-only checks. The normal ELF parser and final VMAR checks still
/// run afterward; neither host metadata nor userspace digests grant authority.
pub(super) fn validate(image: &[u8], user_limit: u64) -> Result<(), &'static str> {
    if image.len() < 64
        || image.len() > MAX_FILE_BYTES
        || image[..7] != *b"\x7fELF\x02\x01\x01"
        || u16_at(image, 16)? != 2
        || u16_at(image, 18)? != 62
        || u32_at(image, 20)? != 1
        || u16_at(image, 52)? != 64
        || u16_at(image, 54)? != 56
    {
        return Err("G2 requires a bounded x86_64 static ET_EXEC");
    }
    let count = usize::from(u16_at(image, 56)?);
    let table = u64_at(image, 32)?;
    let table_end = table
        .checked_add((count * 56) as u64)
        .ok_or("PHDR overflow")?;
    if count == 0
        || count > MAX_PHDRS
        || table < 64
        || table % 8 != 0
        || table_end > image.len() as u64
    {
        return Err("G2 PHDR bounds");
    }
    let entry = u64_at(image, 24)?;
    let mut loads = [Load::default(); MAX_LOADS];
    let mut load_count = 0;
    let mut mapped = 0u64;
    let mut executable_entry = false;
    let mut tls = None;
    let mut phdr = None;
    for index in 0..count {
        // The checked table bound is within this slice, hence fits usize.
        let position = table as usize + index * 56;
        let kind = u32_at(image, position)?;
        if kind == 2 || kind == 3 {
            return Err("G2 rejects dynamic loading");
        }
        if kind == 0x6474e551 && u32_at(image, position + 4)? & 1 != 0 {
            return Err("G2 rejects executable stack requests");
        }
        if kind != 1 && kind != 6 && kind != 7 {
            continue;
        }
        let flags = u32_at(image, position + 4)?;
        let file = u64_at(image, position + 8)?;
        let address = u64_at(image, position + 16)?;
        let file_size = u64_at(image, position + 32)?;
        let memory_size = u64_at(image, position + 40)?;
        let alignment = u64_at(image, position + 48)?;
        let file_end = file.checked_add(file_size).ok_or("ELF file overflow")?;
        let end = address
            .checked_add(memory_size)
            .ok_or("ELF address overflow")?;
        if file_size > memory_size || file_end > image.len() as u64 || end > user_limit {
            return Err("G2 segment bounds");
        }
        if kind == 6 {
            if phdr.replace((file, address, file_size)).is_some() {
                return Err("G2 duplicate PT_PHDR");
            }
            continue;
        }
        if kind == 7 {
            if tls.is_some()
                || memory_size > MAX_TLS_BYTES
                || !alignment.is_power_of_two()
                || alignment > MAX_TLS_ALIGN
                || file % alignment != address % alignment
            {
                return Err("G2 TLS bounds or alignment");
            }
            tls = Some((file, address, file_size));
            continue;
        }
        let start_page = address & !4095;
        let end_page = end.checked_add(4095).ok_or("LOAD page overflow")? & !4095;
        if memory_size == 0
            || start_page < 65536
            || end_page > user_limit
            || file % 4096 != address % 4096
            || flags & 4 == 0
            || flags & 3 == 3
            || flags & !7 != 0
            || load_count == MAX_LOADS
            || loads[..load_count]
                .iter()
                .any(|old| start_page < old.end_page && old.start_page < end_page)
        {
            return Err("G2 LOAD layout or permissions");
        }
        mapped = mapped
            .checked_add(end_page - start_page)
            .ok_or("G2 mapped byte overflow")?;
        if mapped > MAX_MAPPED_BYTES as u64 {
            return Err("G2 mapped byte limit");
        }
        executable_entry |= flags & 1 != 0 && address <= entry && entry < end;
        loads[load_count] = Load {
            file,
            address,
            file_size,
            end,
            start_page,
            end_page,
        };
        load_count += 1;
    }
    let loads = &loads[..load_count];
    // Match ElfHeaders::find_vaddr_of_phdrs exactly: it selects the FIRST
    // LOAD containing the table's starting file byte. File ranges may overlap
    // even when virtual ranges do not. A later full mapping cannot repair the
    // actual AT_PHDR chosen from an earlier partial mapping.
    let table_load = loads
        .iter()
        .find(|load| load.file <= table && table < load.file + load.file_size)
        .ok_or("G2 readable PHDR mapping missing")?;
    if !executable_entry || table_end > table_load.file + table_load.file_size {
        return Err("G2 entry or complete readable PHDR mapping missing");
    }
    if let Some((file, address, size)) = phdr {
        if file != table
            || size < table_end - table
            || address != table_load.address + (table - table_load.file)
        {
            return Err("G2 PT_PHDR would change the static TLS base");
        }
    }
    if let Some((file, address, size)) = tls {
        // Only initialized TLS bytes must be in a LOAD. Per-thread .tbss is
        // allocated by libc; requiring all p_memsz in a LOAD rejects valid ELF.
        if size != 0
            && !loads.iter().any(|load| {
                file >= load.file
                    && file + size <= load.file + load.file_size
                    && address >= load.address
                    && address + size <= load.end
                    && address - load.address == file - load.file
            })
        {
            return Err("G2 TLS template lacks a matching readable LOAD");
        }
    }
    Ok(())
}

#[cfg(any(test, ktest))]
mod tests {
    #[cfg(ktest)]
    use ostd::prelude::*;

    use super::*;

    fn fixture() -> [u8; 8192] {
        let mut image = [0u8; 8192];
        image[..7].copy_from_slice(b"\x7fELF\x02\x01\x01");
        image[16..18].copy_from_slice(&2u16.to_le_bytes());
        image[18..20].copy_from_slice(&62u16.to_le_bytes());
        image[20..24].copy_from_slice(&1u32.to_le_bytes());
        image[24..32].copy_from_slice(&0x401000u64.to_le_bytes());
        image[32..40].copy_from_slice(&64u64.to_le_bytes());
        image[52..54].copy_from_slice(&64u16.to_le_bytes());
        image[54..56].copy_from_slice(&56u16.to_le_bytes());
        image[56..58].copy_from_slice(&2u16.to_le_bytes());
        for (index, (flags, offset, address)) in [(4u32, 0u64, 0x400000u64), (5, 4096, 0x401000)]
            .into_iter()
            .enumerate()
        {
            let p = 64 + index * 56;
            image[p..p + 4].copy_from_slice(&1u32.to_le_bytes());
            image[p + 4..p + 8].copy_from_slice(&flags.to_le_bytes());
            image[p + 8..p + 16].copy_from_slice(&offset.to_le_bytes());
            image[p + 16..p + 24].copy_from_slice(&address.to_le_bytes());
            image[p + 32..p + 40].copy_from_slice(&4096u64.to_le_bytes());
            image[p + 40..p + 48].copy_from_slice(&4096u64.to_le_bytes());
        }
        image
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn immutable_elf_and_program_headers_are_aligned() {
        static BYTES: AlignedElf<7> = AlignedElf([1; 7]);
        assert_eq!(BYTES.0.as_ptr() as usize % 8, 0);
        assert_eq!(core::mem::align_of::<AlignedElf<7>>(), 8);
        let mut image = fixture();
        image.copy_within(64..176, 65);
        image[32..40].copy_from_slice(&65u64.to_le_bytes());
        assert_eq!(validate(&image, 1 << 47), Err("G2 PHDR bounds"));
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn stream_short_reads_and_exact_eof() {
        let source = [23u8; 9001];
        let result = verify_stream(&source, |offset, chunk| {
            let count = chunk.len().min(37).min(source.len() - offset);
            chunk[..count].copy_from_slice(&source[offset..offset + count]);
            Ok::<_, ()>(count)
        });
        assert_eq!(result, Ok(()));
        assert_eq!(
            verify_stream(&source, |_, _| Ok::<_, ()>(0)),
            Err(StreamError::Truncated)
        );
        assert_eq!(
            verify_stream(&source, |_, chunk| Ok::<_, ()>(chunk.len() + 1)),
            Err(StreamError::InvalidRead)
        );
        assert_eq!(
            verify_stream(&source, |_, _| Err(17)),
            Err(StreamError::Read(17))
        );
        assert_eq!(
            verify_stream(&[], |_, _| Ok::<_, ()>(1)),
            Err(StreamError::Mismatch)
        );
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn stream_rejects_changed_tail_and_appended_byte() {
        let source = [23u8; 9001];
        for changed in [0, 4095, 4096, 9000, 9001] {
            let result = verify_stream(&source, |offset, chunk| {
                let count = chunk
                    .len()
                    .min((source.len() + usize::from(changed == 9001)) - offset);
                chunk[..count].fill(23);
                if offset <= changed && changed < offset + count {
                    chunk[changed - offset] = 42;
                }
                Ok::<_, ()>(count)
            });
            assert_eq!(result, Err(StreamError::Mismatch));
        }
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn chunks_preserve_file_page_prefix_bss_and_tail() {
        let image = [37u8; 8192];
        let mut chunk = [99u8; 4096];
        fill_load_chunk(&image, 123..4199, 0, &mut chunk).unwrap();
        assert_eq!(chunk, [37u8; 4096]);
        fill_load_chunk(&image, 123..4199, 4096, &mut chunk).unwrap();
        assert_eq!(&chunk[..103], &[37u8; 103]);
        assert!(chunk[103..].iter().all(|byte| *byte == 0));
        fill_load_chunk(&image, 123..4199, 8192, &mut chunk).unwrap();
        assert_eq!(chunk, [0u8; 4096]);
        fill_load_chunk(&image, 123..123, 0, &mut chunk).unwrap();
        assert_eq!(chunk, [0u8; 4096]);
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn elf_bounds_and_phdr_must_be_fully_mapped() {
        let mut image = fixture();
        assert_eq!(validate(&image, 1 << 47), Ok(()));
        image[64 + 32..64 + 40].copy_from_slice(&65u64.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
        let mut image = fixture();
        image[120 + 4..120 + 8].copy_from_slice(&7u32.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
        let mut image = fixture();
        image[120 + 16..120 + 24].copy_from_slice(&0x400000u64.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
        let mut image = fixture();
        image[32..40].copy_from_slice(&u64::MAX.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn tls_template_mapping_and_per_thread_bss() {
        let mut image = fixture();
        image[56..58].copy_from_slice(&3u16.to_le_bytes());
        let p = 176;
        image[p..p + 4].copy_from_slice(&7u32.to_le_bytes());
        image[p + 8..p + 16].copy_from_slice(&4000u64.to_le_bytes());
        image[p + 16..p + 24].copy_from_slice(&0x400fa0u64.to_le_bytes());
        image[p + 32..p + 40].copy_from_slice(&64u64.to_le_bytes());
        image[p + 40..p + 48].copy_from_slice(&65536u64.to_le_bytes());
        image[p + 48..p + 56].copy_from_slice(&8u64.to_le_bytes());
        assert_eq!(validate(&image, 1 << 47), Ok(()));
        image[p + 16..p + 24].copy_from_slice(&0x402fa0u64.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
        image[p + 32..p + 40].copy_from_slice(&0u64.to_le_bytes());
        assert_eq!(validate(&image, 1 << 47), Ok(()));
        image[p + 48..p + 56].copy_from_slice(&3u64.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn runtime_headers_cannot_redirect_static_tls_base() {
        let mut image = fixture();
        image[56..58].copy_from_slice(&3u16.to_le_bytes());
        let p = 176;
        image[p..p + 4].copy_from_slice(&6u32.to_le_bytes());
        image[p + 8..p + 16].copy_from_slice(&64u64.to_le_bytes());
        image[p + 16..p + 24].copy_from_slice(&0x400040u64.to_le_bytes());
        image[p + 32..p + 40].copy_from_slice(&168u64.to_le_bytes());
        image[p + 40..p + 48].copy_from_slice(&168u64.to_le_bytes());
        assert_eq!(validate(&image, 1 << 47), Ok(()));
        image[p + 16..p + 24].copy_from_slice(&0x400048u64.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
        for kind in [2u32, 3] {
            image[p..p + 4].copy_from_slice(&kind.to_le_bytes());
            assert!(validate(&image, 1 << 47).is_err());
        }
        image[p..p + 4].copy_from_slice(&0x6474e551u32.to_le_bytes());
        image[p + 4..p + 8].copy_from_slice(&7u32.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn validated_sequence_does_not_require_later_inode_reads() {
        let manifest = [17u8; 8192];
        let mut file = manifest;
        let result = verify_stream(&manifest, |offset, destination| {
            let count = destination.len().min(file.len() - offset);
            destination[..count].copy_from_slice(&file[offset..offset + count]);
            // Change already-read bytes before the next chunk is requested.
            // Admission concerns the observed sequence; only the immutable
            // equal manifest, never this mutable file, is used afterward.
            file[..offset + count].fill(99);
            Ok::<_, ()>(count)
        });
        assert_eq!(result, Ok(()));
        assert_eq!(manifest, [17u8; 8192]);
        assert_eq!(file, [99u8; 8192]);
    }

    #[cfg_attr(test, test)]
    #[cfg_attr(ktest, ktest)]
    fn phdr_checks_the_first_actual_auxiliary_mapping() {
        let mut image = fixture();
        image[96..104].copy_from_slice(&100u64.to_le_bytes());
        image[128..136].copy_from_slice(&0u64.to_le_bytes());
        image[152..160].copy_from_slice(&8192u64.to_le_bytes());
        image[160..168].copy_from_slice(&8192u64.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
        let mut image = fixture();
        image[128..136].copy_from_slice(&0u64.to_le_bytes());
        image[56..58].copy_from_slice(&3u16.to_le_bytes());
        let p = 176;
        image[p..p + 4].copy_from_slice(&6u32.to_le_bytes());
        image[p + 8..p + 16].copy_from_slice(&64u64.to_le_bytes());
        image[p + 16..p + 24].copy_from_slice(&0x401040u64.to_le_bytes());
        image[p + 32..p + 40].copy_from_slice(&168u64.to_le_bytes());
        image[p + 40..p + 48].copy_from_slice(&168u64.to_le_bytes());
        assert!(validate(&image, 1 << 47).is_err());
        image[p + 16..p + 24].copy_from_slice(&0x400040u64.to_le_bytes());
        assert_eq!(validate(&image, 1 << 47), Ok(()));
    }
}
