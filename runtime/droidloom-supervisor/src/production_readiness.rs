//! Read-only, bounded observation of Android's versioned public property ABI.
//!
//! A boot property is readiness evidence, never namespace or execution
//! authority. The caller must first bind the original init executable, its
//! actual live PIDFD and the private root. No property is written, no shell is
//! executed, and a parked preparation cannot acquire a Running state here.
//!
//! Layout sources: AOSP bionic prop_area.h blob 089cf527484c5e75acf7c0f03d371db6dc951de8,
//! prop_info.h e2236b0cc690e9c41ac16caaefb9d882a8381dd3 and prop_area.cpp
//! faa3edf0052fa7830d33df06a85e5c3bc1e76c3e. Runtime checks require their
//! explicit version and bounded offsets; an unknown ABI never becomes ready.
//! Publication ordering is also checked against source-lock Bionic commit
//! 06356e41c5ed7b12220b24c05ba4fdb873b126a7, system_properties.cpp and prop_area.cpp.

use std::cmp::Ordering;
use std::collections::BTreeSet;
use std::fs::File;
use std::io;
use std::os::unix::fs::{FileExt, MetadataExt};

use thiserror::Error;

const HEADER: usize = 128;
const NODE: usize = 20;
const INFO: usize = 96;
const MAGIC: u32 = 0x504f_5250;
const VERSION: u32 = 0xfc6e_d0ab;
const NAME: &[u8] = b"sys.boot_completed";
const PARTS: [&[u8]; 2] = [b"sys", b"boot_completed"];
const MAX_STEPS: usize = 4096;
const MAX_SNAPSHOT_ATTEMPTS: usize = 3;

#[derive(Debug, Error)]
pub(crate) enum ReadinessError {
    #[error("unsupported or malformed Android property area: {0}")]
    Rejected(&'static str),
    #[error("Android property area changed during observation")]
    Changed,
    #[error(transparent)]
    Io(#[from] io::Error),
}

type Result<T> = std::result::Result<T, ReadinessError>;

#[derive(Debug, Eq, PartialEq)]
pub(crate) enum BootProperty {
    Absent,
    Updating,
    Incomplete,
    Complete,
}

#[derive(Debug)]
struct Parsed {
    // Keep a malformed value attached to its observed serial. A concurrent
    // update must be ruled out before that error can retire the owned cell.
    value: Result<BootProperty>,
    area_serial: u32,
    property_serial: Option<(u64, u32)>,
}

fn u32_at(bytes: &[u8], offset: usize) -> Result<u32> {
    let end = offset
        .checked_add(4)
        .ok_or(ReadinessError::Rejected("integer overflow"))?;
    let value = bytes
        .get(offset..end)
        .ok_or(ReadinessError::Rejected("integer outside area"))?;
    Ok(u32::from_le_bytes(value.try_into().unwrap()))
}

fn bounded_offset(data: &[u8], offset: u32, size: usize) -> Result<usize> {
    let at = offset as usize;
    if at % 4 != 0 || at.checked_add(size).is_none_or(|end| end > data.len()) {
        return Err(ReadinessError::Rejected(
            "unaligned or escaped property offset",
        ));
    }
    Ok(at)
}

fn parse(bytes: &[u8]) -> Result<Parsed> {
    if ![128 * 1024, 1024 * 1024].contains(&bytes.len())
        || u32_at(bytes, 8)? != MAGIC
        || u32_at(bytes, 12)? != VERSION
        || bytes[16..HEADER].iter().any(|b| *b != 0)
    {
        return Err(ReadinessError::Rejected("property ABI header or area size"));
    }
    let used = u32_at(bytes, 0)? as usize;
    if used < NODE || used % 4 != 0 || used > bytes.len() - HEADER {
        return Err(ReadinessError::Rejected("property used-size boundary"));
    }
    let serial = u32_at(bytes, 4)?;
    let data = &bytes[HEADER..HEADER + used];
    if u32_at(data, 0)? != 0 {
        return Err(ReadinessError::Rejected(
            "property root is not the empty trie node",
        ));
    }
    let mut current = 0_usize;
    let mut visited = BTreeSet::new();
    for wanted in PARTS {
        let mut next = u32_at(data, current + 16)?;
        loop {
            if next == 0 {
                return Ok(Parsed {
                    value: Ok(BootProperty::Absent),
                    area_serial: serial,
                    property_serial: None,
                });
            }
            if visited.len() == MAX_STEPS || !visited.insert(next) {
                return Err(ReadinessError::Rejected(
                    "property trie cycle or traversal limit",
                ));
            }
            let at = bounded_offset(data, next, NODE)?;
            let length = u32_at(data, at)? as usize;
            if length == 0 || length > 256 {
                return Err(ReadinessError::Rejected("property token length"));
            }
            let name_start = at + NODE;
            let name_end = name_start
                .checked_add(length)
                .ok_or(ReadinessError::Rejected("property token overflow"))?;
            if data.get(name_end) != Some(&0) {
                return Err(ReadinessError::Rejected("property token terminator"));
            }
            let name = data
                .get(name_start..name_end)
                .ok_or(ReadinessError::Rejected("property token outside area"))?;
            if name.contains(&0) || name.contains(&b'.') {
                return Err(ReadinessError::Rejected(
                    "property token contains a separator",
                ));
            }
            // Bionic's cmp_prop_name sorts by length first, then byte order.
            // Lexicographic-only lookup would miss legitimate sibling trees.
            match wanted.len().cmp(&length).then_with(|| wanted.cmp(name)) {
                Ordering::Equal => {
                    current = at;
                    break;
                }
                Ordering::Less => next = u32_at(data, at + 8)?,
                Ordering::Greater => next = u32_at(data, at + 12)?,
            }
        }
    }
    let info = u32_at(data, current + 4)?;
    if info == 0 {
        return Ok(Parsed {
            value: Ok(BootProperty::Absent),
            area_serial: serial,
            property_serial: None,
        });
    }
    let at = bounded_offset(data, info, INFO + NAME.len() + 1)?;
    if &data[at + INFO..at + INFO + NAME.len()] != NAME || data[at + INFO + NAME.len()] != 0 {
        return Err(ReadinessError::Rejected("property leaf full name differs"));
    }
    let property_serial = u32_at(data, at)?;
    Ok(Parsed {
        value: property_value(data, at, property_serial),
        area_serial: serial,
        property_serial: Some(((HEADER + at) as u64, property_serial)),
    })
}

fn property_value(data: &[u8], at: usize, serial: u32) -> Result<BootProperty> {
    let value = if serial & 1 != 0 {
        BootProperty::Updating
    } else {
        if serial & (1 << 16) != 0 {
            return Err(ReadinessError::Rejected(
                "boot bool cannot be a long property",
            ));
        }
        let length = (serial >> 24) as usize;
        if length >= 92 || data[at + 4 + length] != 0 {
            return Err(ReadinessError::Rejected("boot value bounds or terminator"));
        }
        match &data[at + 4..at + 4 + length] {
            b"1" => BootProperty::Complete,
            b"" | b"0" => BootProperty::Incomplete,
            _ => {
                return Err(ReadinessError::Rejected(
                    "boot property is not the expected bool encoding",
                ));
            }
        }
    };
    Ok(value)
}

fn read_u32(file: &File, offset: u64) -> Result<u32> {
    let mut bytes = [0_u8; 4];
    file.read_exact_at(&mut bytes, offset)?;
    Ok(u32::from_le_bytes(bytes))
}

fn read_mutable_header(file: &File) -> Result<[u8; 8]> {
    let mut bytes = [0_u8; 8];
    file.read_exact_at(&mut bytes, 0)?;
    Ok(bytes)
}

fn same_file(before: &std::fs::Metadata, after: &std::fs::Metadata) -> bool {
    (
        before.dev(),
        before.ino(),
        before.mode(),
        before.uid(),
        before.gid(),
        before.nlink(),
        before.len(),
    ) == (
        after.dev(),
        after.ino(),
        after.mode(),
        after.uid(),
        after.gid(),
        after.nlink(),
        after.len(),
    )
}

/// The file is obtained only by the ExecutedTreeWitness caller through its
/// held private DEV/property directory. The numeric owner pair is a comparison
/// against that witness, never permission to adopt an external PID or file.
pub(crate) fn read_boot_complete(
    file: &File,
    expected_uid: u32,
    expected_gid: u32,
) -> Result<BootProperty> {
    read_boot_complete_with(file, expected_uid, expected_gid, |file, bytes| {
        file.read_exact_at(bytes, 0)
    })
}

fn read_boot_complete_with(
    file: &File,
    expected_uid: u32,
    expected_gid: u32,
    mut read_area: impl FnMut(&File, &mut [u8]) -> io::Result<()>,
) -> Result<BootProperty> {
    let before = file.metadata()?;
    if !before.is_file()
        || before.nlink() != 1
        || before.uid() != expected_uid
        || before.gid() != expected_gid
        || before.mode() & 0o6022 != 0
        || ![128 * 1024, 1024 * 1024].contains(&before.len())
    {
        return Err(ReadinessError::Rejected(
            "private property file identity, owner, type or bound",
        ));
    }
    let mut rejected_snapshot: Option<Vec<u8>> = None;
    for _ in 0..MAX_SNAPSHOT_ATTEMPTS {
        // Bionic increments bytes_used before publishing newly initialized
        // trie nodes. Its global update serial is in a different property
        // area, so this context's offset 4 alone cannot guard allocation.
        let first_header = read_mutable_header(file)?;
        let mut bytes = vec![0; before.len() as usize];
        read_area(file, &mut bytes)?;
        let parsed = parse(&bytes);
        if bytes[..8] != first_header || read_mutable_header(file)? != first_header {
            rejected_snapshot = None;
            continue;
        }
        if !same_file(&before, &file.metadata()?) {
            return Err(ReadinessError::Changed);
        }
        let parsed = match parsed {
            Ok(parsed) => parsed,
            Err(error) => {
                // A copied trie has no single seqlock covering construction.
                // Confirm an identical rejected snapshot before treating it
                // as stable corruption. Continual changes remain non-ready.
                if rejected_snapshot.as_deref() == Some(bytes.as_slice()) {
                    return Err(error);
                }
                rejected_snapshot = Some(bytes);
                continue;
            }
        };
        rejected_snapshot = None;
        if let Some((offset, serial)) = parsed.property_serial {
            if read_u32(file, offset)? != serial {
                continue;
            }
            // A whole-file pread is not an atomic property snapshot. Recheck
            // the small leaf under explicit serial reads as well, so a copy
            // that observed a new serial with older value bytes also retries.
            let mut leaf = [0_u8; INFO];
            file.read_exact_at(&mut leaf, offset)?;
            let at = offset as usize; // parse bounded it inside the <=1 MiB area.
            if u32_at(&leaf, 0)? != serial
                || leaf.as_slice() != &bytes[at..at + INFO]
                || read_u32(file, offset)? != serial
            {
                continue;
            }
        }
        // The value parser deliberately retained errors until this point:
        // dirty -> value bytes -> new leaf serial is Bionic's publication
        // order. A torn old-serial/new-value copy is a retry, not corruption.
        let value = parsed.value;
        if let Some((offset, serial)) = parsed.property_serial
            && read_u32(file, offset)? != serial
        {
            continue;
        }
        if read_mutable_header(file)? != first_header
            || parsed.area_serial != u32::from_le_bytes(first_header[4..8].try_into().unwrap())
        {
            continue;
        }
        // MAP_SHARED updates do not provide immutable timestamps. Preserve
        // the original inode/size/owner checks independently of the serials.
        if !same_file(&before, &file.metadata()?) {
            return Err(ReadinessError::Changed);
        }
        return value;
    }
    // The caller already maps Changed to Updating under its original boot
    // deadline. Do not wait here or extend that deadline with a new budget.
    Err(ReadinessError::Changed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn set(bytes: &mut [u8], offset: usize, value: u32) {
        bytes[offset..offset + 4].copy_from_slice(&value.to_le_bytes());
    }

    fn area() -> Vec<u8> {
        let mut b = vec![0; 128 * 1024];
        set(&mut b, 0, 288);
        set(&mut b, 4, 2);
        set(&mut b, 8, MAGIC);
        set(&mut b, 12, VERSION);
        set(&mut b, HEADER + 16, 112);
        set(&mut b, HEADER + 112, 3);
        b[HEADER + 132..HEADER + 135].copy_from_slice(b"sys");
        set(&mut b, HEADER + 112 + 16, 136);
        set(&mut b, HEADER + 136, 14);
        b[HEADER + 156..HEADER + 170].copy_from_slice(b"boot_completed");
        set(&mut b, HEADER + 136 + 4, 172);
        set(&mut b, HEADER + 172, 1 << 24);
        b[HEADER + 176] = b'1';
        b[HEADER + 172 + INFO..HEADER + 172 + INFO + NAME.len()].copy_from_slice(NAME);
        b
    }

    fn decoded(bytes: &[u8]) -> Result<BootProperty> {
        parse(bytes)?.value
    }

    #[test]
    fn production_readiness_follows_exact_trie_instead_of_searching_value_bytes() {
        let mut b = area();
        assert_eq!(decoded(&b).unwrap(), BootProperty::Complete);
        set(&mut b, HEADER + 16, 0);
        assert_eq!(decoded(&b).unwrap(), BootProperty::Absent);
        b = area();
        b[HEADER + 172 + INFO] = b'x';
        assert!(decoded(&b).is_err());
    }

    #[test]
    fn production_readiness_rejects_cycles_escapes_unknown_abi_and_dirty_success() {
        let mut b = area();
        set(&mut b, HEADER + 112, 4);
        b[HEADER + 135] = b'x';
        set(&mut b, HEADER + 112 + 8, 112);
        assert!(decoded(&b).is_err());
        b = area();
        set(&mut b, HEADER + 16, u32::MAX);
        assert!(decoded(&b).is_err());
        b = area();
        set(&mut b, 12, 0);
        assert!(decoded(&b).is_err());
        b = area();
        set(&mut b, HEADER + 172, (1 << 24) | 1);
        assert_eq!(decoded(&b).unwrap(), BootProperty::Updating);
        set(&mut b, HEADER + 172, (1 << 24) | (1 << 16));
        assert!(decoded(&b).is_err());
    }

    #[test]
    fn production_readiness_real_file_is_bounded_and_checks_mapped_owner() {
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(&area()).unwrap();
        let m = file.metadata().unwrap();
        // Anonymous tempfile nlink0 is not a published Android property area.
        assert!(read_boot_complete(&file, m.uid(), m.gid()).is_err());
        let mut named = tempfile::NamedTempFile::new().unwrap();
        named.write_all(&area()).unwrap();
        let m = named.as_file().metadata().unwrap();
        assert_eq!(
            read_boot_complete(named.as_file(), m.uid(), m.gid()).unwrap(),
            BootProperty::Complete
        );
        assert!(
            read_boot_complete(named.as_file(), m.uid().checked_add(1).unwrap(), m.gid()).is_err()
        );
        named.as_file().set_len(4 * 1024 * 1024).unwrap();
        assert!(read_boot_complete(named.as_file(), m.uid(), m.gid()).is_err());
    }

    #[test]
    fn production_readiness_retries_value_publication_without_context_serial_change() {
        let mut bytes = area();
        set(&mut bytes, 4, 0);
        set(&mut bytes, HEADER + 172, 0);
        bytes[HEADER + 176] = 0;
        let mut named = tempfile::NamedTempFile::new().unwrap();
        named.write_all(&bytes).unwrap();
        let file = named.as_file();
        let metadata = file.metadata().unwrap();
        let mut copies = 0;
        let observed =
            read_boot_complete_with(file, metadata.uid(), metadata.gid(), |file, out| {
                copies += 1;
                if copies == 1 {
                    // Model a kernel copy straddling the serial/value boundary.
                    // These are actual reads and writes to one held regular file.
                    let split = HEADER + 176;
                    file.read_exact_at(&mut out[..split], 0)?;
                    file.write_all_at(&1_u32.to_le_bytes(), (HEADER + 172) as u64)?;
                    file.write_all_at(b"1\0", split as u64)?;
                    file.write_all_at(&((1_u32 << 24) | 2).to_le_bytes(), (HEADER + 172) as u64)?;
                    file.read_exact_at(&mut out[split..], split as u64)
                } else {
                    file.read_exact_at(out, 0)
                }
            });
        assert_eq!(observed.unwrap(), BootProperty::Complete);
        assert_eq!(copies, 2);
        assert_eq!(read_u32(file, 4).unwrap(), 0);
    }

    #[test]
    fn production_readiness_retries_new_serial_with_older_copied_value() {
        let mut bytes = area();
        set(&mut bytes, 4, 0);
        set(&mut bytes, HEADER + 172, 0);
        bytes[HEADER + 176] = 0;
        let mut named = tempfile::NamedTempFile::new().unwrap();
        named.write_all(&bytes).unwrap();
        let file = named.as_file();
        let metadata = file.metadata().unwrap();
        let mut copies = 0;
        let observed =
            read_boot_complete_with(file, metadata.uid(), metadata.gid(), |file, out| {
                copies += 1;
                if copies == 1 {
                    // Do not make correctness depend on copy-to-user ordering.
                    let split = HEADER + 176;
                    file.read_exact_at(&mut out[split..], split as u64)?;
                    file.write_all_at(&1_u32.to_le_bytes(), (HEADER + 172) as u64)?;
                    file.write_all_at(b"1\0", split as u64)?;
                    file.write_all_at(&((1_u32 << 24) | 2).to_le_bytes(), (HEADER + 172) as u64)?;
                    file.read_exact_at(&mut out[..split], 0)
                } else {
                    file.read_exact_at(out, 0)
                }
            });
        assert_eq!(observed.unwrap(), BootProperty::Complete);
        assert_eq!(copies, 2);
        assert_eq!(read_u32(file, 4).unwrap(), 0);
    }

    #[test]
    fn production_readiness_retries_trie_publication_after_old_allocation_header() {
        let mut complete = area();
        set(&mut complete, 4, 0);
        let mut empty = vec![0; complete.len()];
        empty[..HEADER].copy_from_slice(&complete[..HEADER]);
        set(&mut empty, 0, 112);
        let mut named = tempfile::NamedTempFile::new().unwrap();
        named.write_all(&empty).unwrap();
        let file = named.as_file();
        let metadata = file.metadata().unwrap();
        let mut copies = 0;
        let observed =
            read_boot_complete_with(file, metadata.uid(), metadata.gid(), |file, out| {
                copies += 1;
                if copies == 1 {
                    file.read_exact_at(&mut out[..HEADER], 0)?;
                    // Bionic reserves storage before constructing a node, then
                    // publishes its initialized trie link with release ordering.
                    file.write_all_at(&complete[..4], 0)?;
                    file.write_all_at(&complete[HEADER + 112..], (HEADER + 112) as u64)?;
                    file.write_all_at(&112_u32.to_le_bytes(), (HEADER + 16) as u64)?;
                    file.read_exact_at(&mut out[HEADER..], HEADER as u64)
                } else {
                    file.read_exact_at(out, 0)
                }
            });
        assert_eq!(observed.unwrap(), BootProperty::Complete);
        assert_eq!(copies, 2);
        assert_eq!(read_u32(file, 4).unwrap(), 0);
    }

    #[test]
    fn production_readiness_bounds_continuous_allocation_changes() {
        let mut named = tempfile::NamedTempFile::new().unwrap();
        named.write_all(&area()).unwrap();
        let file = named.as_file();
        let metadata = file.metadata().unwrap();
        let mut copies = 0;
        let observed =
            read_boot_complete_with(file, metadata.uid(), metadata.gid(), |file, out| {
                copies += 1;
                file.read_exact_at(out, 0)?;
                let used = u32::from_le_bytes(out[..4].try_into().unwrap());
                file.write_all_at(&(used + 4).to_le_bytes(), 0)
            });
        assert!(matches!(observed, Err(ReadinessError::Changed)));
        assert_eq!(copies, MAX_SNAPSHOT_ATTEMPTS);
        assert_eq!(read_u32(file, 4).unwrap(), 2);
    }

    #[test]
    fn production_readiness_preserves_stable_corruption_and_dirty_value_distinction() {
        for kind in ["unknown_abi", "cycle", "invalid_bool", "dirty_bool"] {
            let mut bytes = area();
            match kind {
                "unknown_abi" => set(&mut bytes, 12, 0),
                "cycle" => {
                    set(&mut bytes, HEADER + 112, 4);
                    bytes[HEADER + 135] = b'x';
                    set(&mut bytes, HEADER + 112 + 8, 112);
                }
                "invalid_bool" | "dirty_bool" => {
                    bytes[HEADER + 176] = b'2';
                    if kind == "dirty_bool" {
                        set(&mut bytes, HEADER + 172, (1 << 24) | 1);
                    }
                }
                _ => unreachable!(),
            }
            let mut named = tempfile::NamedTempFile::new().unwrap();
            named.write_all(&bytes).unwrap();
            let file = named.as_file();
            let metadata = file.metadata().unwrap();
            let mut copies = 0;
            let observed =
                read_boot_complete_with(file, metadata.uid(), metadata.gid(), |file, out| {
                    copies += 1;
                    file.read_exact_at(out, 0)
                });
            match kind {
                "dirty_bool" => assert_eq!(observed.unwrap(), BootProperty::Updating),
                _ => assert!(
                    matches!(observed, Err(ReadinessError::Rejected(_))),
                    "{kind}"
                ),
            }
            assert_eq!(
                copies,
                if matches!(kind, "unknown_abi" | "cycle") {
                    2
                } else {
                    1
                }
            );
        }
    }

    #[test]
    fn production_readiness_retries_do_not_accept_changed_file_custody() {
        use std::os::unix::fs::PermissionsExt;
        let mut named = tempfile::NamedTempFile::new().unwrap();
        named.write_all(&area()).unwrap();
        let file = named.as_file();
        let metadata = file.metadata().unwrap();
        let observed =
            read_boot_complete_with(file, metadata.uid(), metadata.gid(), |file, out| {
                file.read_exact_at(out, 0)?;
                file.set_permissions(std::fs::Permissions::from_mode(0o666))
            });
        assert!(matches!(observed, Err(ReadinessError::Changed)));
        assert!(matches!(
            read_boot_complete(file, metadata.uid(), metadata.gid()),
            Err(ReadinessError::Rejected(_))
        ));
    }

    #[test]
    fn production_readiness_concurrent_property_writer_keeps_partial_updates_nonfatal() {
        use std::sync::{Arc, Barrier};
        let mut named = tempfile::NamedTempFile::new().unwrap();
        let mut bytes = area();
        set(&mut bytes, 4, 0);
        named.write_all(&bytes).unwrap();
        let file = named.as_file();
        let metadata = file.metadata().unwrap();
        let writer = file.try_clone().unwrap();
        let start = Arc::new(Barrier::new(2));
        let writer_start = start.clone();
        let thread = std::thread::spawn(move || {
            writer_start.wait();
            let mut serial = 1_u32 << 24;
            for iteration in 0..2000 {
                writer
                    .write_all_at(&(serial | 1).to_le_bytes(), (HEADER + 172) as u64)
                    .unwrap();
                let value: &[u8] = if iteration % 2 == 0 { b"\0" } else { b"1\0" };
                writer.write_all_at(value, (HEADER + 176) as u64).unwrap();
                serial = (((value.len() - 1) as u32) << 24) | ((serial + 2) & 0x00ff_ffff);
                writer
                    .write_all_at(&serial.to_le_bytes(), (HEADER + 172) as u64)
                    .unwrap();
            }
        });
        start.wait();
        let mut fatal = None;
        for _ in 0..500 {
            if let Err(error) = read_boot_complete(file, metadata.uid(), metadata.gid())
                && !matches!(error, ReadinessError::Changed)
            {
                fatal = Some(error);
                break;
            }
        }
        thread.join().unwrap();
        assert!(
            fatal.is_none(),
            "a concurrent property update became fatal: {fatal:?}"
        );
        assert_eq!(
            read_boot_complete(file, metadata.uid(), metadata.gid()).unwrap(),
            BootProperty::Complete
        );
        assert_eq!(read_u32(file, 4).unwrap(), 0);
    }
}
