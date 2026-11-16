//! Bounded read-only ZIP/APEX metadata inspection; no signature qualification.
use crate::util::Result;
use flate2::{Decompress, FlushDecompress, Status};
use serde_json::{Map, Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs::File,
    io::{Read, Seek, SeekFrom},
};

const MAX_APEX: u64 = 256 * 1024 * 1024;
const MAX_DIRECTORY: usize = 256 * 1024;
const MAX_METADATA: usize = 64 * 1024;
const PACKAGE: &str = "com.android.hardware.audio.droidloom";

fn need(value: bool, message: &str) -> Result<()> {
    if value { Ok(()) } else { Err(message.into()) }
}
fn u16_at(raw: &[u8], offset: usize) -> Result<u16> {
    Ok(u16::from_le_bytes(
        raw.get(offset..offset + 2)
            .ok_or("truncated ZIP field")?
            .try_into()?,
    ))
}
fn u32_at(raw: &[u8], offset: usize) -> Result<u32> {
    Ok(u32::from_le_bytes(
        raw.get(offset..offset + 4)
            .ok_or("truncated ZIP field")?
            .try_into()?,
    ))
}
fn read_at(file: &mut File, offset: u64, length: usize, file_bytes: u64) -> Result<Vec<u8>> {
    need(
        length <= MAX_DIRECTORY
            && offset
                .checked_add(length as u64)
                .is_some_and(|n| n <= file_bytes),
        "bounded ZIP read is outside the container",
    )?;
    let mut raw = vec![0u8; length];
    file.seek(SeekFrom::Start(offset))?;
    file.read_exact(&mut raw)?;
    Ok(raw)
}
fn crc32(raw: &[u8]) -> u32 {
    let mut crc = !0u32;
    for &byte in raw {
        crc ^= u32::from(byte);
        for _ in 0..8 {
            crc = (crc >> 1) ^ (0xedb88320 & 0u32.wrapping_sub(crc & 1));
        }
    }
    !crc
}

#[derive(Debug)]
struct Entry {
    name: String,
    flags: u16,
    method: u16,
    crc: u32,
    compressed: u32,
    bytes: u32,
    local: u32,
    data_offset: u64,
}

fn directory(file: &mut File) -> Result<Vec<Entry>> {
    let bytes = file.metadata()?.len();
    need(
        (22..=MAX_APEX).contains(&bytes),
        "APEX container size is outside the bounded format",
    )?;
    let tail_size = bytes.min(65557) as usize;
    let tail = read_at(file, bytes - tail_size as u64, tail_size, bytes)?;
    let end = tail
        .windows(4)
        .rposition(|v| v == b"PK\x05\x06")
        .ok_or("APEX ZIP end record absent")?;
    need(end + 22 <= tail.len(), "truncated ZIP end record")?;
    let row = &tail[end..];
    let count = u16_at(row, 10)? as usize;
    let directory_bytes = u32_at(row, 12)? as usize;
    let directory_offset = u32_at(row, 16)? as u64;
    let end_offset = bytes - tail_size as u64 + end as u64;
    need(
        end + 22 + u16_at(row, 20)? as usize == tail.len()
            && u16_at(row, 4)? == 0
            && u16_at(row, 6)? == 0
            && u16_at(row, 8)? as usize == count
            && (4..=256).contains(&count)
            && directory_bytes <= MAX_DIRECTORY
            && directory_offset + directory_bytes as u64 == end_offset,
        "unbounded or unsupported APEX ZIP directory",
    )?;
    let central = read_at(file, directory_offset, directory_bytes, bytes)?;
    let mut offset = 0usize;
    let mut names = BTreeSet::new();
    let mut entries = Vec::with_capacity(count);
    for _ in 0..count {
        let header = central
            .get(offset..offset + 46)
            .ok_or("truncated central ZIP header")?;
        need(
            u32_at(header, 0)? == 0x02014b50,
            "central ZIP signature differs",
        )?;
        let name_bytes = u16_at(header, 28)? as usize;
        let extra = u16_at(header, 30)? as usize;
        let comment = u16_at(header, 32)? as usize;
        let next = offset
            .checked_add(46 + name_bytes + extra + comment)
            .ok_or("central ZIP length overflow")?;
        need(
            next <= central.len(),
            "central ZIP record exceeds directory",
        )?;
        let name = std::str::from_utf8(&central[offset + 46..offset + 46 + name_bytes])?.to_owned();
        need(
            !name.is_empty()
                && !name.starts_with('/')
                && !name.contains('\\')
                && !name.contains('\0')
                && name
                    .split('/')
                    .all(|v| !v.is_empty() && v != "." && v != ".."),
            "noncanonical APEX ZIP entry",
        )?;
        need(names.insert(name.clone()), "duplicate APEX ZIP entry")?;
        let flags = u16_at(header, 8)?;
        let method = u16_at(header, 10)?;
        let kind = (u32_at(header, 38)? >> 16) & 0o170000;
        need(
            flags & !0x080e == 0 && u16_at(header, 34)? == 0 && (kind == 0 || kind == 0o100000),
            "encrypted, nonregular or unsupported APEX ZIP entry",
        )?;
        need(
            method == 0 || method == 8,
            "unsupported APEX compression method",
        )?;
        let entry = Entry {
            name,
            flags,
            method,
            crc: u32_at(header, 16)?,
            compressed: u32_at(header, 20)?,
            bytes: u32_at(header, 24)?,
            local: u32_at(header, 42)?,
            data_offset: 0,
        };
        need(
            u64::from(entry.compressed) <= MAX_APEX
                && u64::from(entry.bytes) <= MAX_APEX
                && u64::from(entry.local) < directory_offset,
            "oversized or ZIP64 APEX entry",
        )?;
        if entry.method == 0 {
            need(
                entry.compressed == entry.bytes,
                "stored ZIP entry size mismatch",
            )?;
        }
        entries.push(entry);
        offset = next;
    }
    need(
        offset == central.len(),
        "unparsed central ZIP directory bytes",
    )?;
    let mut intervals = Vec::with_capacity(entries.len());
    for entry in &mut entries {
        let header = read_at(file, u64::from(entry.local), 30, directory_offset)?;
        need(
            u32_at(&header, 0)? == 0x04034b50
                && u16_at(&header, 6)? == entry.flags
                && u16_at(&header, 8)? == entry.method,
            "local and central ZIP header differ",
        )?;
        let name_bytes = u16_at(&header, 26)? as usize;
        let extra = u16_at(&header, 28)? as usize;
        let name = read_at(
            file,
            u64::from(entry.local) + 30,
            name_bytes,
            directory_offset,
        )?;
        need(
            name == entry.name.as_bytes(),
            "local and central ZIP name differ",
        )?;
        entry.data_offset = u64::from(entry.local) + 30 + name_bytes as u64 + extra as u64;
        let mut data_end = entry.data_offset + u64::from(entry.compressed);
        need(
            data_end <= directory_offset,
            "ZIP payload overlaps central directory",
        )?;
        for (index, expected) in [(14, entry.crc), (18, entry.compressed), (22, entry.bytes)] {
            let local = u32_at(&header, index)?;
            need(
                local == expected || (entry.flags & 8 != 0 && local == 0),
                "local ZIP size or CRC differs",
            )?;
        }
        if entry.flags & 8 != 0 {
            let descriptor = read_at(
                file,
                data_end,
                (directory_offset - data_end).min(16) as usize,
                directory_offset,
            )?;
            let start = if u32_at(&descriptor, 0)? == 0x08074b50 {
                4
            } else {
                0
            };
            need(
                u32_at(&descriptor, start)? == entry.crc
                    && u32_at(&descriptor, start + 4)? == entry.compressed
                    && u32_at(&descriptor, start + 8)? == entry.bytes,
                "ZIP data descriptor differs",
            )?;
            data_end += (start + 12) as u64;
        }
        intervals.push((u64::from(entry.local), data_end));
    }
    intervals.sort_unstable();
    for pair in intervals.windows(2) {
        need(pair[0].1 <= pair[1].0, "overlapping ZIP entries")?;
    }
    Ok(entries)
}

fn decode_metadata(file: &mut File, entry: &Entry) -> Result<Vec<u8>> {
    need(
        entry.bytes > 0
            && entry.bytes as usize <= MAX_METADATA
            && entry.compressed as usize <= 2 * MAX_METADATA,
        "invalid APEX metadata size",
    )?;
    let packed = read_at(
        file,
        entry.data_offset,
        entry.compressed as usize,
        file.metadata()?.len(),
    )?;
    let raw = if entry.method == 0 {
        packed
    } else {
        let mut decoder = Decompress::new(false);
        let mut output = vec![0; entry.bytes as usize + 1];
        let status = decoder.decompress(&packed, &mut output, FlushDecompress::Finish)?;
        need(
            status == Status::StreamEnd
                && decoder.total_in() == packed.len() as u64
                && decoder.total_out() == u64::from(entry.bytes),
            "incomplete or oversized DEFLATE metadata",
        )?;
        output.truncate(entry.bytes as usize);
        output
    };
    need(
        raw.len() == entry.bytes as usize && crc32(&raw) == entry.crc,
        "APEX metadata CRC or length differs",
    )?;
    Ok(raw)
}

fn varint(raw: &[u8], offset: &mut usize) -> Result<u64> {
    let mut result = 0u64;
    for shift in (0..70).step_by(7) {
        let byte = *raw.get(*offset).ok_or("truncated manifest varint")?;
        *offset += 1;
        need(shift < 63 || byte <= 1, "oversized manifest varint")?;
        result |= u64::from(byte & 127) << shift;
        if byte & 128 == 0 {
            return Ok(result);
        }
    }
    Err("oversized manifest varint".into())
}

fn apex_identity(raw: &[u8]) -> Result<Value> {
    let mut offset = 0usize;
    let mut name = None;
    let mut version = None;
    while offset < raw.len() {
        let key = varint(raw, &mut offset)?;
        let number = key >> 3;
        let wire = key & 7;
        need(
            number > 0 && number < (1 << 29),
            "invalid manifest field number",
        )?;
        let mut integer = None;
        let mut data = None;
        if wire == 0 {
            integer = Some(varint(raw, &mut offset)?);
        } else {
            let bytes = match wire {
                1 => 8usize,
                5 => 4,
                2 => usize::try_from(varint(raw, &mut offset)?)?,
                _ => return Err("unsupported manifest wire type".into()),
            };
            let end = offset.checked_add(bytes).ok_or("manifest size overflow")?;
            data = Some(raw.get(offset..end).ok_or("truncated manifest bytes")?);
            offset = end;
        }
        match number {
            1 => {
                need(
                    name.is_none() && wire == 2,
                    "duplicate or invalid APEX name",
                )?;
                name = data;
            }
            2 => {
                need(
                    version.is_none() && wire == 0,
                    "duplicate or invalid APEX version",
                )?;
                version = integer;
            }
            3 | 4 => need(
                wire == 2 && data == Some(&[][..]),
                "unexpected Audio APEX install hook",
            )?,
            _ => {}
        }
    }
    need(
        name == Some(PACKAGE.as_bytes()),
        "APEX package identity differs",
    )?;
    let version = version.ok_or("APEX version absent")?;
    need(
        version > 0 && version <= i64::MAX as u64,
        "invalid APEX version",
    )?;
    Ok(json!({"name": PACKAGE, "version": version}))
}

pub(super) fn inspect(file: &mut File) -> Result<Value> {
    let entries = directory(file)?;
    need(
        !entries.iter().any(|v| v.name == "original_apex"),
        "compressed APEX is outside the vendor staging contract",
    )?;
    let payload = entries
        .iter()
        .find(|v| v.name == "apex_payload.img")
        .ok_or("APEX payload absent")?;
    need(
        payload.method == 0 && payload.bytes > 0,
        "invalid APEX payload storage",
    )?;
    let mut metadata = Map::new();
    let mut identity = None;
    for name in ["apex_manifest.pb", "apex_pubkey", "AndroidManifest.xml"] {
        let entry = entries
            .iter()
            .find(|v| v.name == name)
            .ok_or("APEX metadata absent")?;
        let raw = decode_metadata(file, entry)?;
        metadata.insert(
            name.to_owned(),
            json!({"bytes": raw.len(), "sha256": hex::encode(Sha256::digest(&raw))}),
        );
        if name == "apex_manifest.pb" {
            identity = Some(apex_identity(&raw)?);
        }
    }
    Ok(
        json!({"identity": identity.ok_or("APEX identity absent")?, "metadata": metadata,
        "payload_declared_bytes": payload.bytes, "container_signature_verified": false,
        "payload_avb_signature_verified": false, "payload_filesystem_verified": false}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use flate2::{Compression, write::DeflateEncoder};
    use std::io::Write;

    #[test]
    fn crc32_known_reference_values() {
        assert_eq!(crc32(b"123456789"), 0xcbf43926);
        assert_eq!(crc32(b""), 0);
    }

    #[test]
    fn bounded_deflate_requires_complete_single_stream_and_exact_length() {
        let plain = b"real DEFLATE framing control";
        let mut encoder = DeflateEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(plain).unwrap();
        let packed = encoder.finish().unwrap();
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(&packed).unwrap();
        let entry = Entry {
            name: "metadata".into(),
            flags: 0,
            method: 8,
            crc: crc32(plain),
            compressed: packed.len() as u32,
            bytes: plain.len() as u32,
            local: 0,
            data_offset: 0,
        };
        assert_eq!(decode_metadata(&mut file, &entry).unwrap(), plain);
        let mut bad = entry;
        bad.bytes -= 1;
        assert!(decode_metadata(&mut file, &bad).is_err());
        bad.bytes += 1;
        bad.compressed -= 1;
        assert!(decode_metadata(&mut file, &bad).is_err());
        bad.compressed += 2;
        file.seek(SeekFrom::End(0)).unwrap();
        file.write_all(&[0]).unwrap();
        assert!(decode_metadata(&mut file, &bad).is_err());
    }

    #[test]
    fn manifest_identity_rejects_duplicates_hooks_and_overflow() {
        let mut plain = vec![10, PACKAGE.len() as u8];
        plain.extend_from_slice(PACKAGE.as_bytes());
        plain.extend_from_slice(&[16, 1]);
        assert!(apex_identity(&plain).is_ok());
        let mut duplicate = plain.clone();
        duplicate.extend_from_slice(&[16, 2]);
        assert!(apex_identity(&duplicate).is_err());
        let mut hook = plain.clone();
        hook.extend_from_slice(&[26, 1, b'x']);
        assert!(apex_identity(&hook).is_err());
        let mut overflow = vec![10, PACKAGE.len() as u8];
        overflow.extend_from_slice(PACKAGE.as_bytes());
        overflow.push(16);
        overflow.extend_from_slice(&[255; 10]);
        assert!(apex_identity(&overflow).is_err());
    }
}
