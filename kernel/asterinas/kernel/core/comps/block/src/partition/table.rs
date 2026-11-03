// SPDX-License-Identifier: MPL-2.0

//! Bounded, read-only partition decoding. The same code runs in kernel and host
//! regressions; only the sector reader is supplied by the caller.

use alloc::vec::Vec;

const SECTOR_SIZE: usize = 512;
const GPT_HEADER_SIZE: usize = 92;
const GPT_ENTRY_SIZE: usize = 128;
const MIN_GPT_ARRAY_BYTES: u64 = 16_384;
// Local discovery limits bound I/O, allocation and overlap checks on bad media.
const MAX_GPT_ENTRIES: usize = 4096;
const MAX_GPT_ARRAY_BYTES: u64 = 4 * 1024 * 1024;
const MAX_EBR_SECTORS: usize = 256;

/// Geometry is constructed only after checking the entire table. Keeping the
/// normalized length avoids repeating arithmetic on untrusted GPT endpoints.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct PartitionInfo {
    start_sector: u64,
    total_sectors: u64,
}

impl PartitionInfo {
    pub(super) fn start_sector(&self) -> u64 {
        self.start_sector
    }

    pub(super) fn total_sectors(&self) -> u64 {
        self.total_sectors
    }

    fn end(&self) -> u64 {
        // Construction checked this addition, and the fields never change.
        self.start_sector + self.total_sectors
    }

    fn overlaps(&self, other: &Self) -> bool {
        self.start_sector < other.end() && other.start_sector < self.end()
    }

    fn contains(&self, sector: u64) -> bool {
        self.start_sector <= sector && sector < self.end()
    }
}

#[derive(Debug, Eq, PartialEq)]
pub(super) enum ParseError<E> {
    Io(E),
    NoSignature,
    Invalid(&'static str),
    Limit(&'static str),
    NoMemory,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(super) enum TableSource {
    Mbr,
    GptBoth,
    GptPrimaryOnly,
    GptBackupOnly,
}

#[derive(Debug, Eq, PartialEq)]
pub(super) struct PartitionTable {
    pub(super) partitions: Vec<Option<PartitionInfo>>,
    pub(super) source: TableSource,
}

struct Disk<R> {
    nr_sectors: u64,
    reader: R,
}

impl<E, R: FnMut(u64, &mut [u8; SECTOR_SIZE]) -> Result<(), E>> Disk<R> {
    fn read(&mut self, sector: u64) -> Result<[u8; SECTOR_SIZE], ParseError<E>> {
        if sector >= self.nr_sectors {
            return Err(ParseError::Invalid("sector outside device"));
        }
        let mut bytes = [0; SECTOR_SIZE];
        (self.reader)(sector, &mut bytes).map_err(ParseError::Io)?;
        Ok(bytes)
    }
}

pub(super) fn parse<E>(
    nr_sectors: u64,
    reader: impl FnMut(u64, &mut [u8; SECTOR_SIZE]) -> Result<(), E>,
) -> Result<Option<PartitionTable>, ParseError<E>> {
    if nr_sectors == 0 {
        return Ok(None);
    }
    let mut disk = Disk { nr_sectors, reader };
    let mbr = disk.read(0)?;
    let entries = mbr_entries(&mbr);
    if has_mbr_signature(&mbr) && !entries.iter().any(|entry| entry.type_ == 0xee) {
        // A real legacy MBR wins over a stale backup GPT left by reformatting.
        return parse_mbr(&mut disk, entries).map(Some);
    }
    if nr_sectors < 3 {
        return Err(ParseError::Invalid("device too small for GPT"));
    }

    // Never follow an unvalidated AlternateLBA. Both locations are fixed by
    // UEFI 2.11, section 5.3. A surviving copy is used without writing repairs.
    let primary = parse_gpt(&mut disk, 1);
    let last_sector = nr_sectors - 1;
    let backup = parse_gpt(&mut disk, last_sector);
    let (table, source) = match (primary, backup) {
        (Ok(primary), Ok(backup)) => {
            if !primary.agrees_with(&backup) {
                return Err(ParseError::Invalid("valid GPT copies disagree"));
            }
            (primary, TableSource::GptBoth)
        }
        (Ok(primary), Err(_)) => (primary, TableSource::GptPrimaryOnly),
        (Err(_), Ok(backup)) => (backup, TableSource::GptBackupOnly),
        (Err(ParseError::NoSignature), Err(ParseError::NoSignature)) => return Ok(None),
        (Err(ParseError::NoSignature), Err(error)) => return Err(error),
        (Err(error), Err(_)) => return Err(error),
    };
    Ok(Some(PartitionTable {
        partitions: table.partitions,
        source,
    }))
}

#[derive(Clone, Copy)]
struct MbrEntry {
    type_: u8,
    start: u64,
    len: u64,
}

impl MbrEntry {
    fn is_extended(&self) -> bool {
        matches!(self.type_, 0x05 | 0x0f | 0x85)
    }

    fn is_unused(&self) -> bool {
        self.type_ == 0 || self.len == 0
    }
}

fn has_mbr_signature(bytes: &[u8; SECTOR_SIZE]) -> bool {
    bytes[510..] == [0x55, 0xaa]
}

fn mbr_entries(bytes: &[u8; SECTOR_SIZE]) -> [MbrEntry; 4] {
    core::array::from_fn(|index| {
        let offset = 446 + index * 16;
        MbrEntry {
            type_: bytes[offset + 4],
            start: le_u32(bytes, offset + 8) as u64,
            len: le_u32(bytes, offset + 12) as u64,
        }
    })
}

fn geometry<E>(start: u64, len: u64, limit: u64) -> Result<PartitionInfo, ParseError<E>> {
    if start == 0 || len == 0 || start.checked_add(len).is_none_or(|end| end > limit) {
        return Err(ParseError::Invalid("partition outside allowed range"));
    }
    Ok(PartitionInfo {
        start_sector: start,
        total_sectors: len,
    })
}

fn parse_mbr<E>(
    disk: &mut Disk<impl FnMut(u64, &mut [u8; SECTOR_SIZE]) -> Result<(), E>>,
    entries: [MbrEntry; 4],
) -> Result<PartitionTable, ParseError<E>> {
    let mut partitions = Vec::new();
    partitions
        .try_reserve_exact(4 + MAX_EBR_SECTORS)
        .map_err(|_| ParseError::NoMemory)?;
    for entry in &entries {
        if entry.is_unused() {
            partitions.push(None);
            continue;
        }
        let info = geometry(entry.start, entry.len, disk.nr_sectors)?;
        if partitions
            .iter()
            .flatten()
            .any(|prior| info.overlaps(prior))
        {
            return Err(ParseError::Invalid("overlapping MBR partitions"));
        }
        partitions.push(Some(info));
    }

    let mut visited = Vec::new();
    visited
        .try_reserve_exact(MAX_EBR_SECTORS)
        .map_err(|_| ParseError::NoMemory)?;
    for entry in &entries {
        if !entry.is_extended() || entry.is_unused() {
            continue;
        }
        // This entry was validated above. Extended containers remain visible
        // primary partitions; only logical partitions are checked against them.
        let container = geometry(entry.start, entry.len, disk.nr_sectors)?;
        let mut sector = container.start_sector;
        loop {
            if visited.contains(&sector) {
                return Err(ParseError::Invalid("cyclic EBR chain"));
            }
            if visited.len() == MAX_EBR_SECTORS {
                return Err(ParseError::Limit("too many EBR sectors"));
            }
            if !container.contains(sector)
                || partitions[4..]
                    .iter()
                    .flatten()
                    .any(|part| part.contains(sector))
            {
                return Err(ParseError::Invalid("EBR outside container or inside data"));
            }
            visited.push(sector);
            let bytes = disk.read(sector)?;
            if !has_mbr_signature(&bytes) {
                return Err(ParseError::Invalid("missing EBR signature"));
            }
            let ebr = mbr_entries(&bytes);
            if ebr[2..].iter().any(|entry| !entry.is_unused()) {
                return Err(ParseError::Invalid("unsupported extra EBR entries"));
            }
            if !ebr[0].is_unused() {
                if ebr[0].is_extended() || ebr[0].start == 0 {
                    return Err(ParseError::Invalid("invalid logical partition"));
                }
                let start = sector
                    .checked_add(ebr[0].start)
                    .ok_or(ParseError::Invalid("logical partition start overflow"))?;
                let info = geometry(start, ebr[0].len, container.end())?;
                if visited.iter().any(|sector| info.contains(*sector))
                    || partitions[4..]
                        .iter()
                        .flatten()
                        .any(|prior| info.overlaps(prior))
                {
                    return Err(ParseError::Invalid("overlapping logical partition"));
                }
                partitions.push(Some(info));
            }
            let link = ebr[1];
            if link.type_ == 0 {
                break;
            }
            if !link.is_extended() || link.len == 0 {
                return Err(ParseError::Invalid("invalid EBR link"));
            }
            sector = container
                .start_sector
                .checked_add(link.start)
                .ok_or(ParseError::Invalid("EBR link overflow"))?;
            geometry(sector, link.len, container.end())?;
        }
    }
    Ok(PartitionTable {
        partitions,
        source: TableSource::Mbr,
    })
}

#[derive(Debug)]
struct GptHeader {
    first_usable: u64,
    last_usable: u64,
    disk_guid: [u8; 16],
    entries_lba: u64,
    nr_entries: usize,
    entry_size: usize,
    array_bytes: u64,
    array_crc: u32,
}

struct GptTable {
    header: GptHeader,
    partitions: Vec<Option<PartitionInfo>>,
}

impl GptTable {
    fn agrees_with(&self, other: &Self) -> bool {
        self.header.first_usable == other.header.first_usable
            && self.header.last_usable == other.header.last_usable
            && self.header.disk_guid == other.header.disk_guid
            && self.header.nr_entries == other.header.nr_entries
            && self.header.entry_size == other.header.entry_size
            && self.header.array_crc == other.header.array_crc
            && self.partitions == other.partitions
    }
}

fn gpt_header<E>(
    bytes: &mut [u8; SECTOR_SIZE],
    sector: u64,
    nr_sectors: u64,
) -> Result<GptHeader, ParseError<E>> {
    if &bytes[..8] != b"EFI PART" {
        return Err(ParseError::NoSignature);
    }
    let size = le_u32(bytes, 12) as usize;
    if le_u32(bytes, 8) != 0x0001_0000
        || !(GPT_HEADER_SIZE..=SECTOR_SIZE).contains(&size)
        || le_u32(bytes, 20) != 0
    {
        return Err(ParseError::Invalid("unsupported GPT header"));
    }
    let expected_crc = le_u32(bytes, 16);
    bytes[16..20].fill(0);
    if crc32(&bytes[..size]) != expected_crc {
        return Err(ParseError::Invalid("GPT header CRC mismatch"));
    }
    let alternate = if sector == 1 { nr_sectors - 1 } else { 1 };
    if le_u64(bytes, 24) != sector || le_u64(bytes, 32) != alternate {
        return Err(ParseError::Invalid("GPT header location mismatch"));
    }
    let mut disk_guid = [0; 16];
    disk_guid.copy_from_slice(&bytes[56..72]);
    let mut header = GptHeader {
        first_usable: le_u64(bytes, 40),
        last_usable: le_u64(bytes, 48),
        disk_guid,
        entries_lba: le_u64(bytes, 72),
        nr_entries: le_u32(bytes, 80) as usize,
        entry_size: le_u32(bytes, 84) as usize,
        array_bytes: 0,
        array_crc: le_u32(bytes, 88),
    };
    // Older GPT revisions permit multiples of eight. Keep those layouts while
    // also handling current 128 * 2^n entries, including entries > one sector.
    if header.nr_entries == 0
        || header.entry_size < GPT_ENTRY_SIZE
        || !header.entry_size.is_multiple_of(8)
    {
        return Err(ParseError::Invalid("invalid GPT entry dimensions"));
    }
    header.array_bytes = (header.nr_entries as u64)
        .checked_mul(header.entry_size as u64)
        .ok_or(ParseError::Invalid("GPT array size overflow"))?;
    if header.nr_entries > MAX_GPT_ENTRIES || header.array_bytes > MAX_GPT_ARRAY_BYTES {
        return Err(ParseError::Limit("GPT array exceeds discovery limits"));
    }
    let reserved = header
        .array_bytes
        .max(MIN_GPT_ARRAY_BYTES)
        .div_ceil(SECTOR_SIZE as u64);
    let minimum_first = 2 + reserved;
    let maximum_last = nr_sectors
        .checked_sub(2 + reserved)
        .ok_or(ParseError::Invalid("device too small for GPT arrays"))?;
    if header.first_usable < minimum_first
        || header.last_usable > maximum_last
        || header.first_usable > header.last_usable
    {
        return Err(ParseError::Invalid("invalid GPT usable range"));
    }
    let array_end = header
        .entries_lba
        .checked_add(header.array_bytes.div_ceil(SECTOR_SIZE as u64))
        .ok_or(ParseError::Invalid("GPT array location overflow"))?;
    let valid_location = if sector == 1 {
        header.entries_lba > sector && array_end <= header.first_usable
    } else {
        header.entries_lba > header.last_usable && array_end <= sector
    };
    if !valid_location {
        return Err(ParseError::Invalid(
            "GPT array overlaps header or usable range",
        ));
    }
    Ok(header)
}

fn parse_gpt<E>(
    disk: &mut Disk<impl FnMut(u64, &mut [u8; SECTOR_SIZE]) -> Result<(), E>>,
    sector: u64,
) -> Result<GptTable, ParseError<E>> {
    let mut bytes = disk.read(sector)?;
    let header = gpt_header(&mut bytes, sector, disk.nr_sectors)?;
    let mut partitions = Vec::new();
    partitions
        .try_reserve_exact(header.nr_entries)
        .map_err(|_| ParseError::NoMemory)?;
    let mut entry = [0; GPT_ENTRY_SIZE];
    let mut entry_offset = 0;
    let mut remaining = header.array_bytes;
    let mut lba = header.entries_lba;
    let mut crc = !0u32;
    while remaining > 0 {
        let bytes = disk.read(lba)?;
        let used = remaining.min(SECTOR_SIZE as u64) as usize;
        crc = crc32_update(crc, &bytes[..used]);
        let mut offset = 0;
        while offset < used {
            let copied = (header.entry_size - entry_offset).min(used - offset);
            if entry_offset < GPT_ENTRY_SIZE {
                let prefix = copied.min(GPT_ENTRY_SIZE - entry_offset);
                entry[entry_offset..entry_offset + prefix]
                    .copy_from_slice(&bytes[offset..offset + prefix]);
            }
            entry_offset += copied;
            offset += copied;
            if entry_offset == header.entry_size {
                let info = if entry[..16] == [0; 16] {
                    None
                } else {
                    let start = le_u64(&entry, 32);
                    let end = le_u64(&entry, 40);
                    if start < header.first_usable || end > header.last_usable || end < start {
                        return Err(ParseError::Invalid("GPT partition outside usable range"));
                    }
                    let info = geometry(start, end - start + 1, disk.nr_sectors)?;
                    if partitions
                        .iter()
                        .flatten()
                        .any(|prior| info.overlaps(prior))
                    {
                        return Err(ParseError::Invalid("overlapping GPT partitions"));
                    }
                    Some(info)
                };
                partitions.push(info);
                entry_offset = 0;
            }
        }
        remaining -= used as u64;
        // Header validation already bounded the complete array by nr_sectors.
        lba += 1;
    }
    if !crc != header.array_crc {
        return Err(ParseError::Invalid("GPT entry array CRC mismatch"));
    }
    debug_assert_eq!(partitions.len(), header.nr_entries);
    Ok(GptTable { header, partitions })
}

fn le_u32(bytes: &[u8], offset: usize) -> u32 {
    u32::from_le_bytes(core::array::from_fn(|i| bytes[offset + i]))
}

fn le_u64(bytes: &[u8], offset: usize) -> u64 {
    u64::from_le_bytes(core::array::from_fn(|i| bytes[offset + i]))
}

// IEEE CRC-32 used by GPT, not CRC-32C. A compile-time table keeps bounded
// discovery cheap without adding a new dependency or changing audited locks.
const CRC32_TABLE: [u32; 256] = {
    let mut table = [0; 256];
    let mut index = 0;
    while index < table.len() {
        let mut value = index as u32;
        let mut bit = 0;
        while bit < 8 {
            value = (value >> 1) ^ if value & 1 != 0 { 0xedb8_8320 } else { 0 };
            bit += 1;
        }
        table[index] = value;
        index += 1;
    }
    table
};

fn crc32_update(mut crc: u32, bytes: &[u8]) -> u32 {
    for byte in bytes {
        crc = CRC32_TABLE[((crc as u8) ^ byte) as usize] ^ (crc >> 8);
    }
    crc
}

fn crc32(bytes: &[u8]) -> u32 {
    !crc32_update(!0, bytes)
}

#[cfg(any(test, ktest))]
#[path = "table/tests.rs"]
mod tests;
