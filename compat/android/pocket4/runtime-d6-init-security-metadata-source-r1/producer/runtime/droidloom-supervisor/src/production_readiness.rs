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

#[derive(Debug, Eq, PartialEq)]
struct Parsed {
    value: BootProperty,
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
                    value: BootProperty::Absent,
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
            value: BootProperty::Absent,
            area_serial: serial,
            property_serial: None,
        });
    }
    let at = bounded_offset(data, info, INFO + NAME.len() + 1)?;
    if &data[at + INFO..at + INFO + NAME.len()] != NAME || data[at + INFO + NAME.len()] != 0 {
        return Err(ReadinessError::Rejected("property leaf full name differs"));
    }
    let property_serial = u32_at(data, at)?;
    let value = if property_serial & 1 != 0 {
        BootProperty::Updating
    } else {
        if property_serial & (1 << 16) != 0 {
            return Err(ReadinessError::Rejected(
                "boot bool cannot be a long property",
            ));
        }
        let length = (property_serial >> 24) as usize;
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
    Ok(Parsed {
        value,
        area_serial: serial,
        property_serial: Some(((HEADER + at) as u64, property_serial)),
    })
}

fn read_u32(file: &File, offset: u64) -> Result<u32> {
    let mut bytes = [0_u8; 4];
    file.read_exact_at(&mut bytes, offset)?;
    Ok(u32::from_le_bytes(bytes))
}

/// The file is obtained only by the ExecutedTreeWitness caller through its
/// held private DEV/property directory. The numeric owner pair is a comparison
/// against that witness, never permission to adopt an external PID or file.
pub(crate) fn read_boot_complete(
    file: &File,
    expected_uid: u32,
    expected_gid: u32,
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
    let first_serial = read_u32(file, 4)?;
    let mut bytes = vec![0; before.len() as usize];
    file.read_exact_at(&mut bytes, 0)?;
    let parsed = parse(&bytes)?;
    if first_serial != parsed.area_serial || read_u32(file, 4)? != first_serial {
        return Err(ReadinessError::Changed);
    }
    if let Some((offset, serial)) = parsed.property_serial {
        if read_u32(file, offset)? != serial || read_u32(file, 4)? != first_serial {
            return Err(ReadinessError::Changed);
        }
    }
    let after = file.metadata()?;
    // Property updates happen through MAP_SHARED: times are not an immutable
    // input seal. The actual Bionic serials and fixed inode/size/owner are used.
    if (
        before.dev(),
        before.ino(),
        before.mode(),
        before.uid(),
        before.gid(),
        before.nlink(),
        before.len(),
    ) != (
        after.dev(),
        after.ino(),
        after.mode(),
        after.uid(),
        after.gid(),
        after.nlink(),
        after.len(),
    ) {
        return Err(ReadinessError::Changed);
    }
    Ok(parsed.value)
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

    #[test]
    fn production_readiness_follows_exact_trie_instead_of_searching_value_bytes() {
        let mut b = area();
        assert_eq!(parse(&b).unwrap().value, BootProperty::Complete);
        set(&mut b, HEADER + 16, 0);
        assert_eq!(parse(&b).unwrap().value, BootProperty::Absent);
        b = area();
        b[HEADER + 172 + INFO] = b'x';
        assert!(parse(&b).is_err());
    }

    #[test]
    fn production_readiness_rejects_cycles_escapes_unknown_abi_and_dirty_success() {
        let mut b = area();
        set(&mut b, HEADER + 112, 4);
        b[HEADER + 135] = b'x';
        set(&mut b, HEADER + 112 + 8, 112);
        assert!(parse(&b).is_err());
        b = area();
        set(&mut b, HEADER + 16, u32::MAX);
        assert!(parse(&b).is_err());
        b = area();
        set(&mut b, 12, 0);
        assert!(parse(&b).is_err());
        b = area();
        set(&mut b, HEADER + 172, (1 << 24) | 1);
        assert_eq!(parse(&b).unwrap().value, BootProperty::Updating);
        set(&mut b, HEADER + 172, (1 << 24) | (1 << 16));
        assert!(parse(&b).is_err());
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
}
