// SPDX-License-Identifier: MPL-2.0

//! Regressions for malformed-media panics (upstream issue #4021) and bounded
//! partition discovery. These use the production decoder and a failing reader,
//! not a second parser. The images are encoded independently of that decoder.

use alloc::{vec, vec::Vec};

#[cfg(ktest)]
use ostd::prelude::ktest;

use super::*;

struct Image {
    sectors: Vec<[u8; SECTOR_SIZE]>,
    failures: Vec<u64>,
    reads: Vec<u64>,
}

impl Image {
    fn blank(sectors: usize) -> Self {
        Self {
            sectors: vec![[0; SECTOR_SIZE]; sectors],
            failures: Vec::new(),
            reads: Vec::new(),
        }
    }

    fn parse(&mut self) -> Result<Option<PartitionTable>, ParseError<u64>> {
        parse(self.sectors.len() as u64, |sector, bytes| {
            self.reads.push(sector);
            if self.failures.contains(&sector) {
                return Err(sector);
            }
            bytes.copy_from_slice(&self.sectors[sector as usize]);
            Ok(())
        })
    }

    fn mbr_entry(&mut self, sector: usize, index: usize, type_: u8, start: u32, len: u32) {
        let bytes = &mut self.sectors[sector];
        bytes[510..].copy_from_slice(&[0x55, 0xaa]);
        let offset = 446 + index * 16;
        bytes[offset + 4] = type_;
        put_u32(bytes, offset + 8, start);
        put_u32(bytes, offset + 12, len);
    }

    fn refresh_header_crc(&mut self, sector: usize) {
        let bytes = &mut self.sectors[sector];
        bytes[16..20].fill(0);
        let crc = reference_crc(&bytes[..GPT_HEADER_SIZE]);
        put_u32(bytes, 16, crc);
    }

    fn refresh_array_crc(&mut self, header_sector: usize) {
        let header = &self.sectors[header_sector];
        let start = le_u64(header, 72) as usize;
        let len = le_u32(header, 80) as usize * le_u32(header, 84) as usize;
        let bytes: Vec<_> = self.sectors[start..]
            .iter()
            .flatten()
            .take(len)
            .copied()
            .collect();
        let crc = reference_crc(&bytes);
        put_u32(&mut self.sectors[header_sector], 88, crc);
        self.refresh_header_crc(header_sector);
    }

    fn invalidate_backup(&mut self) {
        let last = self.sectors.len() - 1;
        self.sectors[last][0] = 0;
    }
}

fn put_u32(bytes: &mut [u8], offset: usize, value: u32) {
    bytes[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
}

fn put_u64(bytes: &mut [u8], offset: usize, value: u64) {
    bytes[offset..offset + 8].copy_from_slice(&value.to_le_bytes());
}

// A bitwise encoder deliberately independent of the production lookup table.
fn reference_crc(bytes: &[u8]) -> u32 {
    let mut crc = !0u32;
    for byte in bytes {
        crc ^= *byte as u32;
        for _ in 0..8 {
            let carry = crc & 1;
            crc >>= 1;
            if carry != 0 {
                crc ^= 0xedb8_8320;
            }
        }
    }
    !crc
}

fn gpt_image(entry_size: usize, nr_entries: usize) -> Image {
    let mut image = Image::blank(256);
    image.mbr_entry(0, 0, 0xee, 1, 255);
    let array_bytes = entry_size * nr_entries;
    let array_sectors = array_bytes.div_ceil(SECTOR_SIZE);
    let reserved = array_sectors.max(32);
    let first_usable = 2 + reserved;
    let last_usable = 254 - reserved;
    let backup_array = 255 - array_sectors;
    let mut entries = vec![0; array_sectors * SECTOR_SIZE];
    for (index, start) in [(0, 64), (nr_entries - 1, 128)] {
        let offset = index * entry_size;
        entries[offset] = 0x83;
        entries[offset + 16] = index as u8 + 1;
        put_u64(&mut entries, offset + 32, start);
        put_u64(&mut entries, offset + 40, start + 7);
    }
    for (index, chunk) in entries.chunks_exact(SECTOR_SIZE).enumerate() {
        image.sectors[2 + index].copy_from_slice(chunk);
        image.sectors[backup_array + index].copy_from_slice(chunk);
    }
    let array_crc = reference_crc(&entries[..array_bytes]);
    for (sector, alternate, array) in [(1, 255, 2), (255, 1, backup_array)] {
        let header = &mut image.sectors[sector];
        header[..8].copy_from_slice(b"EFI PART");
        put_u32(header, 8, 0x0001_0000);
        put_u32(header, 12, GPT_HEADER_SIZE as u32);
        put_u64(header, 24, sector as u64);
        put_u64(header, 32, alternate);
        put_u64(header, 40, first_usable as u64);
        put_u64(header, 48, last_usable as u64);
        header[56] = 0xa5;
        put_u64(header, 72, array as u64);
        put_u32(header, 80, nr_entries as u32);
        put_u32(header, 84, entry_size as u32);
        put_u32(header, 88, array_crc);
        image.refresh_header_crc(sector);
    }
    image
}

fn assert_partition(table: &PartitionTable, slot: usize, start: u64, len: u64) {
    let info = table.partitions[slot].as_ref().unwrap();
    assert_eq!(info.start_sector(), start);
    assert_eq!(info.total_sectors(), len);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn ieee_crc_matches_known_vectors_and_incremental_updates() {
    assert_eq!(crc32(b""), 0);
    assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
    assert_eq!(
        !crc32_update(crc32_update(!0, b"1234"), b"56789"),
        0xcbf4_3926
    );
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn valid_gpt_preserves_slots_and_last_partial_sector() {
    let mut image = gpt_image(128, 5);
    let table = image.parse().unwrap().unwrap();
    assert_eq!(table.source, TableSource::GptBoth);
    assert_eq!(table.partitions.len(), 5);
    assert_partition(&table, 0, 64, 8);
    assert!(table.partitions[1..4].iter().all(Option::is_none));
    assert_partition(&table, 4, 128, 8);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn entries_crossing_sectors_and_larger_than_sectors_are_supported() {
    for size in [136, 256, 512, 1024] {
        let mut image = gpt_image(size, 5);
        let table = image.parse().unwrap().unwrap();
        assert_eq!(table.source, TableSource::GptBoth);
        assert_eq!(table.partitions.len(), 5);
        assert_partition(&table, 4, 128, 8);
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn unused_array_padding_is_not_part_of_gpt_crc() {
    let mut image = gpt_image(128, 5);
    image.sectors[3][128..].fill(0xa5);
    image.sectors[254][128..].fill(0x5a);
    assert_eq!(image.parse().unwrap().unwrap().source, TableSource::GptBoth);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn zero_short_and_misaligned_entry_sizes_are_rejected_without_array_reads() {
    for size in [0, 1, 64, 127, 129, 513] {
        let mut image = gpt_image(128, 5);
        image.invalidate_backup();
        put_u32(&mut image.sectors[1], 84, size);
        image.refresh_header_crc(1);
        assert!(matches!(image.parse(), Err(ParseError::Invalid(_))));
        assert_eq!(image.reads, [0, 1, 255]);
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn oversized_array_dimensions_are_bounded_before_io_or_allocation() {
    for (count, size) in [(0, 128), (4097, 128), (128, u32::MAX - 7), (4096, 2048)] {
        let mut image = gpt_image(128, 5);
        image.invalidate_backup();
        put_u32(&mut image.sectors[1], 80, count);
        put_u32(&mut image.sectors[1], 84, size);
        image.refresh_header_crc(1);
        assert!(image.parse().is_err());
        assert_eq!(image.reads, [0, 1, 255]);
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn invalid_header_size_revision_reserved_and_crc_are_rejected() {
    for (offset, value) in [(12, 0), (12, 91), (12, 513), (8, 0x20000), (20, 1)] {
        let mut image = gpt_image(128, 5);
        image.invalidate_backup();
        put_u32(&mut image.sectors[1], offset, value);
        image.refresh_header_crc(1);
        assert!(matches!(image.parse(), Err(ParseError::Invalid(_))));
        assert_eq!(image.reads, [0, 1, 255]);
    }
    let mut image = gpt_image(128, 5);
    image.invalidate_backup();
    image.sectors[1][56] ^= 1;
    assert_eq!(
        image.parse(),
        Err(ParseError::Invalid("GPT header CRC mismatch"))
    );
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn gpt_locations_usable_ranges_and_overflow_are_rejected_before_array_io() {
    for (offset, value) in [
        (24, 2),
        (32, 254),
        (40, 1),
        (48, 255),
        (40, 223),
        (72, 0),
        (72, 1),
        (72, 34),
        (72, u64::MAX),
    ] {
        let mut image = gpt_image(128, 5);
        image.invalidate_backup();
        put_u64(&mut image.sectors[1], offset, value);
        image.refresh_header_crc(1);
        assert!(matches!(image.parse(), Err(ParseError::Invalid(_))));
        assert_eq!(image.reads, [0, 1, 255]);
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn gpt_reversed_outside_and_overlapping_partitions_are_rejected() {
    for (start, end) in [(64, 63), (1, 8), (220, 255), (u64::MAX, u64::MAX)] {
        let mut image = gpt_image(128, 5);
        image.invalidate_backup();
        put_u64(&mut image.sectors[2], 32, start);
        put_u64(&mut image.sectors[2], 40, end);
        image.refresh_array_crc(1);
        assert!(matches!(image.parse(), Err(ParseError::Invalid(_))));
    }
    let mut image = gpt_image(128, 5);
    image.invalidate_backup();
    put_u64(&mut image.sectors[3], 32, 68);
    put_u64(&mut image.sectors[3], 40, 75);
    image.refresh_array_crc(1);
    assert_eq!(
        image.parse(),
        Err(ParseError::Invalid("overlapping GPT partitions"))
    );
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn corrupt_primary_header_or_array_uses_valid_backup_without_writes() {
    for (sector, byte) in [(1, 0), (1, 56), (2, 64)] {
        let mut image = gpt_image(128, 5);
        image.sectors[sector][byte] ^= 1;
        let original = image.sectors.clone();
        let table = image.parse().unwrap().unwrap();
        assert_eq!(table.source, TableSource::GptBackupOnly);
        assert_partition(&table, 4, 128, 8);
        assert_eq!(image.sectors, original);
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn corrupt_backup_uses_valid_primary_without_writes() {
    let mut image = gpt_image(128, 5);
    image.sectors[255][56] ^= 1;
    let original = image.sectors.clone();
    let table = image.parse().unwrap().unwrap();
    assert_eq!(table.source, TableSource::GptPrimaryOnly);
    assert_partition(&table, 4, 128, 8);
    assert_eq!(image.sectors, original);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn two_valid_but_conflicting_gpt_copies_are_rejected() {
    let mut image = gpt_image(128, 5);
    put_u64(&mut image.sectors[253], 32, 72);
    put_u64(&mut image.sectors[253], 40, 79);
    image.refresh_array_crc(255);
    assert_eq!(
        image.parse(),
        Err(ParseError::Invalid("valid GPT copies disagree"))
    );
    let mut image = gpt_image(128, 5);
    image.sectors[255][56] ^= 1;
    image.refresh_header_crc(255);
    assert_eq!(
        image.parse(),
        Err(ParseError::Invalid("valid GPT copies disagree"))
    );
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn crc_covers_unused_entries_and_large_entry_extensions() {
    for (size, sector, byte) in [(128, 2, 192), (1024, 3, 16)] {
        let mut image = gpt_image(size, 5);
        image.invalidate_backup();
        image.sectors[sector][byte] ^= 1;
        assert_eq!(
            image.parse(),
            Err(ParseError::Invalid("GPT entry array CRC mismatch"))
        );
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn io_failure_is_propagated_or_recovered_only_from_a_valid_gpt_copy() {
    let mut image = gpt_image(128, 5);
    image.failures.push(0);
    assert_eq!(image.parse(), Err(ParseError::Io(0)));
    assert_eq!(image.reads, [0]);
    let mut image = gpt_image(128, 5);
    image.sectors[1][0] = 0;
    image.failures.push(255);
    assert_eq!(image.parse(), Err(ParseError::Io(255)));
    for failed in [1, 2, 3] {
        let mut image = gpt_image(128, 5);
        image.failures.push(failed);
        assert_eq!(
            image.parse().unwrap().unwrap().source,
            TableSource::GptBackupOnly
        );
        let mut image = gpt_image(128, 5);
        image.invalidate_backup();
        image.failures.push(failed);
        assert_eq!(image.parse(), Err(ParseError::Io(failed)));
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn protective_mbr_in_another_slot_still_selects_gpt() {
    let mut image = gpt_image(128, 5);
    image.sectors[0][446..510].fill(0);
    image.mbr_entry(0, 3, 0xee, 1, 255);
    assert_eq!(image.parse().unwrap().unwrap().source, TableSource::GptBoth);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn valid_legacy_mbr_with_zero_chs_wins_over_stale_backup_gpt() {
    let mut image = gpt_image(128, 5);
    image.sectors[0][446..510].fill(0);
    image.mbr_entry(0, 1, 0x83, 32, 20);
    let table = image.parse().unwrap().unwrap();
    assert_eq!(table.source, TableSource::Mbr);
    assert_eq!(table.partitions.len(), 4);
    assert!(table.partitions[0].is_none());
    assert_partition(&table, 1, 32, 20);
    assert_eq!(image.reads, [0]);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn mbr_out_of_device_and_overlapping_ranges_are_rejected() {
    for (start, len) in [(0, 1), (250, 7), (u32::MAX, u32::MAX)] {
        let mut image = Image::blank(256);
        image.mbr_entry(0, 0, 0x83, start, len);
        assert!(matches!(image.parse(), Err(ParseError::Invalid(_))));
    }
    let mut image = Image::blank(256);
    image.mbr_entry(0, 0, 0x83, 16, 32);
    image.mbr_entry(0, 1, 0x0f, 32, 128);
    assert_eq!(
        image.parse(),
        Err(ParseError::Invalid("overlapping MBR partitions"))
    );
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn valid_ebr_chain_uses_base_relative_links_and_sector_relative_data() {
    for extended_type in [0x05, 0x0f, 0x85] {
        let mut image = Image::blank(256);
        image.mbr_entry(0, 1, extended_type, 16, 200);
        image.mbr_entry(16, 0, 0x83, 1, 10);
        image.mbr_entry(16, 1, extended_type, 32, 100);
        image.mbr_entry(48, 0, 0x83, 2, 20);
        let table = image.parse().unwrap().unwrap();
        assert_eq!(table.partitions.len(), 6);
        assert_partition(&table, 1, 16, 200);
        assert_partition(&table, 4, 17, 10);
        assert_partition(&table, 5, 50, 20);
        assert_eq!(image.reads, [0, 16, 48]);
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn self_and_multi_sector_ebr_cycles_terminate_without_partial_results() {
    let mut image = Image::blank(256);
    image.mbr_entry(0, 0, 0x0f, 16, 200);
    image.mbr_entry(16, 0, 0x83, 1, 10);
    image.mbr_entry(16, 1, 0x0f, 0, 200);
    assert_eq!(image.parse(), Err(ParseError::Invalid("cyclic EBR chain")));
    assert_eq!(image.reads, [0, 16]);
    let mut image = Image::blank(256);
    image.mbr_entry(0, 0, 0x0f, 16, 200);
    image.mbr_entry(16, 1, 0x0f, 32, 100);
    image.mbr_entry(48, 1, 0x0f, 0, 200);
    assert_eq!(image.parse(), Err(ParseError::Invalid("cyclic EBR chain")));
    assert_eq!(image.reads, [0, 16, 48]);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn oversized_ebr_chain_stops_at_the_discovery_limit() {
    let mut image = Image::blank(600);
    image.mbr_entry(0, 0, 0x0f, 1, 599);
    for sector in 1..=257 {
        image.mbr_entry(sector, 1, 0x0f, sector as u32, 1);
    }
    assert_eq!(
        image.parse(),
        Err(ParseError::Limit("too many EBR sectors"))
    );
    assert_eq!(image.reads.len(), 1 + MAX_EBR_SECTORS);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn ebr_bad_signature_io_and_links_are_rejected() {
    let mut image = Image::blank(256);
    image.mbr_entry(0, 0, 0x0f, 16, 200);
    assert_eq!(
        image.parse(),
        Err(ParseError::Invalid("missing EBR signature"))
    );
    image.failures.push(16);
    assert_eq!(image.parse(), Err(ParseError::Io(16)));
    for (type_, start, len) in [
        (0x83, 32, 1),
        (0x0f, 32, 0),
        (0x0f, 250, 10),
        (0x0f, u32::MAX, 1),
    ] {
        let mut image = Image::blank(256);
        image.mbr_entry(0, 0, 0x0f, 16, 200);
        image.mbr_entry(16, 1, type_, start, len);
        assert!(matches!(image.parse(), Err(ParseError::Invalid(_))));
        assert_eq!(image.reads, [0, 16]);
    }
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn ebr_data_must_stay_in_container_and_not_cover_metadata_or_other_data() {
    for (start, len) in [(0, 10), (190, 20), (u32::MAX, u32::MAX)] {
        let mut image = Image::blank(256);
        image.mbr_entry(0, 0, 0x0f, 16, 200);
        image.mbr_entry(16, 0, 0x83, start, len);
        assert!(matches!(image.parse(), Err(ParseError::Invalid(_))));
    }
    let mut image = Image::blank(256);
    image.mbr_entry(0, 0, 0x0f, 16, 200);
    image.mbr_entry(16, 0, 0x83, 1, 50);
    image.mbr_entry(16, 1, 0x0f, 32, 100);
    assert_eq!(
        image.parse(),
        Err(ParseError::Invalid("EBR outside container or inside data"))
    );
    assert_eq!(image.reads, [0, 16]);
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn empty_devices_and_unpartitioned_media_have_no_partitions() {
    assert_eq!(Image::blank(0).parse(), Ok(None));
    assert_eq!(Image::blank(256).parse(), Ok(None));
    let mut image = Image::blank(1);
    image.mbr_entry(0, 0, 0, 0, 0);
    assert!(
        image
            .parse()
            .unwrap()
            .unwrap()
            .partitions
            .iter()
            .all(Option::is_none)
    );
}

#[cfg_attr(ktest, ktest)]
#[cfg_attr(test, test)]
fn malformed_headers_never_request_a_sector_outside_the_device() {
    // Deterministic mutations of disk-controlled header words cover extremes
    // with valid header checksums; the reader itself asserts every I/O bound.
    let mut seed = 0x735a_24c9u32;
    for _ in 0..128 {
        let mut image = gpt_image(128, 5);
        image.invalidate_backup();
        seed = seed.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
        let offset = [24, 32, 40, 48, 72][seed as usize % 5];
        let value = match seed % 4 {
            0 => u64::MAX - seed as u64,
            1 => seed as u64,
            2 => 256,
            _ => 0,
        };
        put_u64(&mut image.sectors[1], offset, value);
        image.refresh_header_crc(1);
        assert!(image.parse().is_err());
        assert!(image.reads.iter().all(|sector| *sector < 256));
        assert!(image.reads.len() <= 3);
    }
}
