//! Actual original APEX bytes, their stored ZIP window and AVB layout.
//!
//! The only constructor selects an entry in the compiled complete CP3A profile
//! and hashes both the whole original APEX and its whole payload. A caller
//! cannot supply an accepted hash, offset, filesystem or verity root. This is
//! byte provenance, not a signature verifier or an apexd activation witness.
use super::{PayloadFilesystem, original_inputs};
use sha2::{Digest, Sha256};
use std::fs::{File, Metadata};
use std::io;
use std::os::unix::fs::{FileExt, MetadataExt};
use std::time::Instant;

fn require(ok: bool, message: &'static str) -> io::Result<()> {
    if ok {
        Ok(())
    } else {
        Err(io::Error::new(io::ErrorKind::InvalidData, message))
    }
}
fn check_deadline(end: Instant) -> io::Result<()> {
    if Instant::now() < end {
        Ok(())
    } else {
        Err(io::Error::new(
            io::ErrorKind::TimedOut,
            "original APEX input deadline",
        ))
    }
}
fn part(raw: &[u8], start: usize, bytes: usize) -> io::Result<&[u8]> {
    raw.get(
        start..start.checked_add(bytes).ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "APEX field range overflow")
        })?,
    )
    .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "truncated APEX field"))
}
fn le16(raw: &[u8], offset: usize) -> io::Result<u16> {
    Ok(u16::from_le_bytes(
        part(raw, offset, 2)?.try_into().unwrap(),
    ))
}
fn le32(raw: &[u8], offset: usize) -> io::Result<u32> {
    Ok(u32::from_le_bytes(
        part(raw, offset, 4)?.try_into().unwrap(),
    ))
}
fn be32(raw: &[u8], offset: usize) -> io::Result<u32> {
    Ok(u32::from_be_bytes(
        part(raw, offset, 4)?.try_into().unwrap(),
    ))
}
fn be64(raw: &[u8], offset: usize) -> io::Result<u64> {
    Ok(u64::from_be_bytes(
        part(raw, offset, 8)?.try_into().unwrap(),
    ))
}
fn read(file: &File, offset: u64, bytes: usize, total: u64) -> io::Result<Vec<u8>> {
    require(
        offset
            .checked_add(bytes as u64)
            .is_some_and(|end| end <= total),
        "APEX read must stay in the original held inode",
    )?;
    let mut raw = vec![0; bytes];
    file.read_exact_at(&mut raw, offset)?;
    Ok(raw)
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Identity {
    dev: u64,
    ino: u64,
    mode: u32,
    uid: u32,
    gid: u32,
    links: u64,
    bytes: u64,
    mtime: (i64, i64),
    ctime: (i64, i64),
}
impl Identity {
    fn of(meta: &Metadata) -> Self {
        Self {
            dev: meta.dev(),
            ino: meta.ino(),
            mode: meta.mode(),
            uid: meta.uid(),
            gid: meta.gid(),
            links: meta.nlink(),
            bytes: meta.len(),
            mtime: (meta.mtime(), meta.mtime_nsec()),
            ctime: (meta.ctime(), meta.ctime_nsec()),
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Window {
    offset: u64,
    bytes: u64,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct Central {
    offset: u64,
    bytes: u64,
    entries: u16,
}
fn central_directory(tail: &[u8], total: u64) -> io::Result<Central> {
    require(
        tail.len() >= 22 && tail.len() as u64 <= total,
        "bounded ZIP end record",
    )?;
    let mut found = None;
    for at in 0..=tail.len() - 22 {
        if part(tail, at, 4)? != b"PK\x05\x06"
            || at + 22 + le16(tail, at + 20)? as usize != tail.len()
        {
            continue;
        }
        require(found.is_none(), "ambiguous ZIP end record")?;
        require(
            le16(tail, at + 4)? == 0
                && le16(tail, at + 6)? == 0
                && le16(tail, at + 8)? == le16(tail, at + 10)?
                && (1..=256).contains(&le16(tail, at + 10)?),
            "single-disk bounded original APEX ZIP",
        )?;
        let result = Central {
            offset: u64::from(le32(tail, at + 16)?),
            bytes: u64::from(le32(tail, at + 12)?),
            entries: le16(tail, at + 10)?,
        };
        require(
            result.bytes <= 1024 * 1024
                && result.offset.checked_add(result.bytes)
                    == Some(total - tail.len() as u64 + at as u64),
            "complete original central directory directly precedes ZIP end",
        )?;
        found = Some(result);
    }
    found.ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "original APEX ZIP end absent"))
}

#[derive(Clone, Copy)]
struct PayloadEntry {
    local: u64,
    bytes: u64,
    crc: u32,
}
fn payload_entry(raw: &[u8], entries: u16) -> io::Result<PayloadEntry> {
    let mut cursor = 0;
    let mut payload = None;
    for _ in 0..entries {
        let head = part(raw, cursor, 46)?;
        require(
            part(head, 0, 4)? == b"PK\x01\x02",
            "central directory record signature",
        )?;
        let name_bytes = le16(head, 28)? as usize;
        let extra_bytes = le16(head, 30)? as usize;
        let comment_bytes = le16(head, 32)? as usize;
        let body = part(raw, cursor + 46, name_bytes + extra_bytes + comment_bytes)?;
        require(le16(head, 34)? == 0, "same original ZIP disk")?;
        if part(body, 0, name_bytes)? == b"apex_payload.img" {
            require(payload.is_none(), "exactly one apex_payload.img record")?;
            require(
                le16(head, 8)? == 0x800
                    && le16(head, 10)? == 0
                    && le32(head, 20)? == le32(head, 24)?,
                "original payload is stored, unencrypted and has explicit equal sizes",
            )?;
            payload = Some(PayloadEntry {
                local: u64::from(le32(head, 42)?),
                bytes: u64::from(le32(head, 24)?),
                crc: le32(head, 16)?,
            });
        }
        cursor += 46 + body.len();
    }
    require(cursor == raw.len(), "whole ZIP central directory consumed")?;
    payload.ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "stored APEX payload absent"))
}
fn payload_window(
    head: &[u8],
    name: &[u8],
    entry: PayloadEntry,
    central: u64,
) -> io::Result<Window> {
    require(
        part(head, 0, 4)? == b"PK\x03\x04"
            && le16(head, 6)? == 0x800
            && le16(head, 8)? == 0
            && le32(head, 14)? == entry.crc
            && u64::from(le32(head, 18)?) == entry.bytes
            && u64::from(le32(head, 22)?) == entry.bytes
            && le16(head, 26)? as usize == name.len()
            && name == b"apex_payload.img",
        "local payload header agrees with the central directory",
    )?;
    let offset = entry
        .local
        .checked_add(30 + name.len() as u64 + u64::from(le16(head, 28)?))
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "payload offset overflow"))?;
    require(
        entry.local == 0
            && offset == 16_384
            && entry.bytes >= 8192
            && entry.bytes % 4096 == 0
            && offset
                .checked_add(entry.bytes)
                .is_some_and(|end| end < central),
        "exact selected CP3A stored payload window within the signed original archive",
    )?;
    Ok(Window {
        offset,
        bytes: entry.bytes,
    })
}

/// Values read from the original, whole-hash-matched AVB hashtree descriptor.
/// They identify a finite readonly dm-verity table; no signature result is
/// represented here. Original apexd still has to perform VerifyApexVerity.
#[derive(Debug)]
pub(crate) struct VerityLayout {
    image_bytes: u64,
    tree_offset: u64,
    tree_bytes: u64,
    salt: [u8; 32],
    root_digest: [u8; 32],
}
impl VerityLayout {
    pub(crate) fn image_bytes(&self) -> u64 {
        self.image_bytes
    }
    pub(crate) fn tree_offset(&self) -> u64 {
        self.tree_offset
    }
    pub(crate) fn tree_bytes(&self) -> u64 {
        self.tree_bytes
    }
    pub(crate) fn salt(&self) -> &[u8; 32] {
        &self.salt
    }
    pub(crate) fn root_digest(&self) -> &[u8; 32] {
        &self.root_digest
    }
}
fn verity_layout(footer: &[u8], vbmeta: &[u8], payload: u64) -> io::Result<VerityLayout> {
    require(
        footer.len() == 64
            && part(footer, 0, 4)? == b"AVBf"
            && be32(footer, 4)? == 1
            && be32(footer, 8)? == 0
            && part(footer, 36, 28)? == [0; 28]
            && vbmeta.len() >= 256
            && part(vbmeta, 0, 4)? == b"AVB0"
            && be64(footer, 28)? == vbmeta.len() as u64
            && be32(vbmeta, 28)? == 2
            && be64(vbmeta, 12)? == 576,
        "original CP3A AVB footer and SHA256_RSA4096 metadata shape",
    )?;
    let image = be64(footer, 12)?;
    let vbmeta_offset = be64(footer, 20)?;
    let auth = be64(vbmeta, 12)?;
    let aux = be64(vbmeta, 20)?;
    let desc_offset = be64(vbmeta, 96)?;
    let desc_bytes = be64(vbmeta, 104)?;
    require(
        image > 0
            && image % 4096 == 0
            && vbmeta_offset % 4096 == 0
            && 256_u64.checked_add(auth).and_then(|n| n.checked_add(aux))
                == Some(vbmeta.len() as u64)
            && vbmeta_offset
                .checked_add(vbmeta.len() as u64)
                .is_some_and(|end| end <= payload.saturating_sub(64))
            && desc_offset
                .checked_add(desc_bytes)
                .is_some_and(|end| end <= aux),
        "bounded original AVB blocks",
    )?;
    let descriptors = part(
        vbmeta,
        (256 + auth + desc_offset) as usize,
        desc_bytes as usize,
    )?;
    let mut cursor = 0;
    let mut result = None;
    let mut properties = 0;
    while cursor < descriptors.len() {
        let common = part(descriptors, cursor, 16)?;
        let following = be64(common, 8)?;
        require(
            following <= 4096 && following % 8 == 0,
            "finite aligned AVB descriptor",
        )?;
        let desc = part(descriptors, cursor, 16 + following as usize)?;
        match be64(common, 0)? {
            1 => {
                require(
                    result.is_none() && desc.len() == 248,
                    "single original hashtree descriptor",
                )?;
                require(
                    be32(desc, 16)? == 1
                        && be64(desc, 20)? == image
                        && be32(desc, 44)? == 4096
                        && be32(desc, 48)? == 4096
                        && be32(desc, 52)? == 0
                        && be64(desc, 56)? == 0
                        && be64(desc, 64)? == 0
                        && part(desc, 72, 32)?
                            == b"sha256\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0"
                        && be32(desc, 104)? == 0
                        && be32(desc, 108)? == 32
                        && be32(desc, 112)? == 32
                        && be32(desc, 116)? == 0
                        && part(desc, 120, 60)? == [0; 60]
                        && part(desc, 244, 4)? == [0; 4],
                    "exact original SHA256 hashtree dimensions without FEC or flags",
                )?;
                let tree_offset = be64(desc, 28)?;
                let tree_bytes = be64(desc, 36)?;
                require(
                    tree_offset == image
                        && tree_bytes > 0
                        && tree_bytes % 4096 == 0
                        && tree_offset.checked_add(tree_bytes) == Some(vbmeta_offset),
                    "exact data and hashtree extent before original vbmeta",
                )?;
                result = Some(VerityLayout {
                    image_bytes: image,
                    tree_offset,
                    tree_bytes,
                    salt: part(desc, 180, 32)?.try_into().unwrap(),
                    root_digest: part(desc, 212, 32)?.try_into().unwrap(),
                });
            }
            0 => {
                properties += 1;
                require(properties == 1, "one original APEX key property")?;
                let key = be64(desc, 16)?;
                let value = be64(desc, 24)?;
                require(
                    key == 8 && value <= 256,
                    "bounded original apex.key property",
                )?;
                require(
                    part(desc, 32, 9)? == b"apex.key\0"
                        && part(desc, 41 + value as usize, 1)? == [0],
                    "original apex.key descriptor key and terminated value",
                )?;
            }
            _ => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    "unexpected CP3A AVB descriptor",
                ));
            }
        }
        cursor += desc.len();
    }
    require(
        cursor == descriptors.len() && properties == 1,
        "complete original AVB descriptor inventory",
    )?;
    result
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "original APEX hashtree absent"))
}

fn digest_window(file: &File, offset: u64, bytes: u64, end: Instant) -> io::Result<String> {
    let mut hash = Sha256::new();
    let mut buffer = vec![0; 1024 * 1024];
    let mut at = 0;
    while at < bytes {
        check_deadline(end)?;
        let amount = (bytes - at).min(buffer.len() as u64) as usize;
        file.read_exact_at(&mut buffer[..amount], offset + at)?;
        hash.update(&buffer[..amount]);
        at += amount as u64;
    }
    check_deadline(end)?;
    Ok(format!("{:x}", hash.finalize()))
}

/// Non-serializable and non-Clone. Its held descriptor excludes fd reuse. This
/// witness alone does not make a writable decompression output immutable;
/// the block provider must additionally hold the admitted immutable source.
#[derive(Debug)]
pub(crate) struct VerifiedArchive {
    file: File,
    identity: Identity,
    index: usize,
    window: Window,
    filesystem: PayloadFilesystem,
    verity: VerityLayout,
}
impl VerifiedArchive {
    pub(crate) fn inspect(file: &File, index: usize, end: Instant) -> io::Result<Self> {
        check_deadline(end)?;
        let profile = original_inputs().map_err(io::Error::other)?;
        let fixed = profile
            .get(index)
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "fixed APEX role index"))?;
        let file = file.try_clone()?;
        let meta = file.metadata()?;
        let identity = Identity::of(&meta);
        require(
            meta.is_file() && meta.len() == fixed.input.original_apex_bytes,
            "actual original APEX regular inode and size",
        )?;
        require(
            digest_window(&file, 0, meta.len(), end)? == fixed.input.original_apex_sha256
                && Identity::of(&file.metadata()?) == identity,
            "whole original APEX bytes and stable full identity",
        )?;
        let tail_bytes = meta.len().min(65_557) as usize;
        let tail = read(
            &file,
            meta.len() - tail_bytes as u64,
            tail_bytes,
            meta.len(),
        )?;
        let central = central_directory(&tail, meta.len())?;
        let directory = read(&file, central.offset, central.bytes as usize, meta.len())?;
        let entry = payload_entry(&directory, central.entries)?;
        let head = read(&file, entry.local, 30, meta.len())?;
        let name = read(
            &file,
            entry.local + 30,
            le16(&head, 26)? as usize,
            meta.len(),
        )?;
        let window = payload_window(&head, &name, entry, central.offset)?;
        require(
            window.bytes == fixed.input.payload_bytes,
            "same original payload byte count",
        )?;
        require(
            digest_window(&file, window.offset, window.bytes, end)? == fixed.input.payload_sha256,
            "whole stored original payload SHA256",
        )?;
        let filesystem =
            if read(&file, window.offset + 1024, 4, meta.len())? == [0xe2, 0xe1, 0xf5, 0xe0] {
                PayloadFilesystem::Erofs
            } else {
                require(
                    read(&file, window.offset + 1080, 2, meta.len())? == [0x53, 0xef],
                    "actual ext4 or EROFS superblock",
                )?;
                PayloadFilesystem::Ext4
            };
        require(
            filesystem == fixed.filesystem,
            "actual selected original payload filesystem",
        )?;
        let footer = read(&file, window.offset + window.bytes - 64, 64, meta.len())?;
        let vbmeta_bytes = be64(&footer, 28)?;
        let vbmeta_offset = be64(&footer, 20)?;
        require(
            vbmeta_bytes <= 65_536
                && vbmeta_offset
                    .checked_add(vbmeta_bytes)
                    .is_some_and(|n| n <= window.bytes - 64),
            "bounded original vbmeta read",
        )?;
        let vbmeta = read(
            &file,
            window.offset + vbmeta_offset,
            vbmeta_bytes as usize,
            meta.len(),
        )?;
        let verity = verity_layout(&footer, &vbmeta, window.bytes)?;
        check_deadline(end)?;
        let result = Self {
            file,
            identity,
            index,
            window,
            filesystem,
            verity,
        };
        result.revalidate()?;
        Ok(result)
    }
    pub(crate) fn revalidate(&self) -> io::Result<()> {
        require(
            Identity::of(&self.file.metadata()?) == self.identity,
            "original APEX inode changed after full-byte verification",
        )
    }
    pub(crate) fn matches(&self, file: &File) -> io::Result<()> {
        self.revalidate()?;
        require(
            Identity::of(&file.metadata()?) == self.identity,
            "loop source must be the same whole-byte-verified APEX inode",
        )
    }
    pub(crate) fn index(&self) -> usize {
        self.index
    }
    pub(crate) fn offset(&self) -> u64 {
        self.window.offset
    }
    pub(crate) fn payload_bytes(&self) -> u64 {
        self.window.bytes
    }
    pub(crate) fn filesystem(&self) -> PayloadFilesystem {
        self.filesystem
    }
    pub(crate) fn verity(&self) -> &VerityLayout {
        &self.verity
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn central_record() -> Vec<u8> {
        let mut row = vec![0; 46];
        row[..4].copy_from_slice(b"PK\x01\x02");
        row[8..10].copy_from_slice(&0x800_u16.to_le_bytes());
        row[20..24].copy_from_slice(&8192_u32.to_le_bytes());
        row[24..28].copy_from_slice(&8192_u32.to_le_bytes());
        row[28..30].copy_from_slice(&16_u16.to_le_bytes());
        row.extend_from_slice(b"apex_payload.img");
        row
    }
    #[test]
    fn apex_window_rejects_duplicate_compressed_encrypted_or_incomplete_zip_records() {
        let row = central_record();
        assert_eq!(payload_entry(&row, 1).unwrap().bytes, 8192);
        let mut duplicate = row.clone();
        duplicate.extend_from_slice(&row);
        assert!(payload_entry(&duplicate, 2).is_err());
        for offset in [0, 8, 10, 20, 28, 34] {
            let mut changed = row.clone();
            changed[offset] ^= 1;
            assert!(payload_entry(&changed, 1).is_err(), "offset {offset}");
        }
        for bytes in [0, 45, row.len() - 1] {
            assert!(payload_entry(&row[..bytes], 1).is_err());
        }
        assert!(payload_entry(&row, 0).is_err());
        assert!(payload_entry(&duplicate, 1).is_err());
    }
    #[test]
    fn apex_window_rejects_zip_boundary_aliases_and_mismatched_local_headers() {
        let mut end = vec![0; 22];
        end[..4].copy_from_slice(b"PK\x05\x06");
        end[8..10].copy_from_slice(&1_u16.to_le_bytes());
        end[10..12].copy_from_slice(&1_u16.to_le_bytes());
        end[12..16].copy_from_slice(&62_u32.to_le_bytes());
        end[16..20].copy_from_slice(&30_000_u32.to_le_bytes());
        assert_eq!(central_directory(&end, 30_084).unwrap().offset, 30_000);
        for offset in [4, 6, 8, 12, 16, 20] {
            let mut changed = end.clone();
            changed[offset] ^= 1;
            assert!(
                central_directory(&changed, 30_084).is_err(),
                "offset {offset}"
            );
        }
        let entry = payload_entry(&central_record(), 1).unwrap();
        let mut local = vec![0; 30];
        local[..4].copy_from_slice(b"PK\x03\x04");
        local[6..8].copy_from_slice(&0x800_u16.to_le_bytes());
        local[18..22].copy_from_slice(&8192_u32.to_le_bytes());
        local[22..26].copy_from_slice(&8192_u32.to_le_bytes());
        local[26..28].copy_from_slice(&16_u16.to_le_bytes());
        local[28..30].copy_from_slice(&16_338_u16.to_le_bytes());
        assert_eq!(
            payload_window(&local, b"apex_payload.img", entry, 30_000)
                .unwrap()
                .offset,
            16_384
        );
        assert!(payload_window(&local, b"apex_payload.img", entry, 24_576).is_err());
        for offset in [0, 6, 8, 14, 18, 22, 26, 28] {
            let mut changed = local.clone();
            changed[offset] ^= 1;
            assert!(
                payload_window(&changed, b"apex_payload.img", entry, 30_000).is_err(),
                "offset {offset}"
            );
        }
    }
    #[test]
    fn apex_archive_cannot_admit_unknown_role_or_expired_deadline() {
        let file = File::open("/dev/null").unwrap();
        assert!(
            VerifiedArchive::inspect(
                &file,
                38,
                Instant::now() + std::time::Duration::from_secs(1)
            )
            .is_err()
        );
        assert!(VerifiedArchive::inspect(&file, 0, Instant::now()).is_err());
        assert!(
            VerifiedArchive::inspect(&file, 0, Instant::now() + std::time::Duration::from_secs(1))
                .is_err()
        );
    }

    #[test]
    fn apex_verity_layout_rejects_foreign_extents_fec_flags_and_descriptor_substitution() {
        let mut footer = vec![0; 64];
        footer[..4].copy_from_slice(b"AVBf");
        footer[4..8].copy_from_slice(&1_u32.to_be_bytes());
        footer[12..20].copy_from_slice(&8192_u64.to_be_bytes());
        footer[20..28].copy_from_slice(&12_288_u64.to_be_bytes());
        footer[28..36].copy_from_slice(&2176_u64.to_be_bytes());
        let mut vbmeta = vec![0; 2176];
        vbmeta[..4].copy_from_slice(b"AVB0");
        vbmeta[12..20].copy_from_slice(&576_u64.to_be_bytes());
        vbmeta[20..28].copy_from_slice(&1344_u64.to_be_bytes());
        vbmeta[28..32].copy_from_slice(&2_u32.to_be_bytes());
        vbmeta[104..112].copy_from_slice(&312_u64.to_be_bytes());
        let at = 256 + 576;
        let desc = &mut vbmeta[at..at + 248];
        desc[..8].copy_from_slice(&1_u64.to_be_bytes());
        desc[8..16].copy_from_slice(&232_u64.to_be_bytes());
        desc[16..20].copy_from_slice(&1_u32.to_be_bytes());
        desc[20..28].copy_from_slice(&8192_u64.to_be_bytes());
        desc[28..36].copy_from_slice(&8192_u64.to_be_bytes());
        desc[36..44].copy_from_slice(&4096_u64.to_be_bytes());
        desc[44..48].copy_from_slice(&4096_u32.to_be_bytes());
        desc[48..52].copy_from_slice(&4096_u32.to_be_bytes());
        desc[72..78].copy_from_slice(b"sha256");
        desc[108..112].copy_from_slice(&32_u32.to_be_bytes());
        desc[112..116].copy_from_slice(&32_u32.to_be_bytes());
        let property = &mut vbmeta[at + 248..at + 312];
        property[8..16].copy_from_slice(&48_u64.to_be_bytes());
        property[16..24].copy_from_slice(&8_u64.to_be_bytes());
        property[24..32].copy_from_slice(&1_u64.to_be_bytes());
        property[32..41].copy_from_slice(b"apex.key\0");
        property[41] = b'x';
        let layout = verity_layout(&footer, &vbmeta, 16_384).unwrap();
        assert_eq!(
            (
                layout.image_bytes(),
                layout.tree_offset(),
                layout.tree_bytes()
            ),
            (8192, 8192, 4096)
        );
        for offset in [0, 4, 12, 20, 28, 36] {
            let mut changed = footer.clone();
            changed[offset] ^= 1;
            assert!(
                verity_layout(&changed, &vbmeta, 16_384).is_err(),
                "footer offset {offset}"
            );
        }
        for offset in [
            0,
            12,
            20,
            28,
            96,
            104,
            at,
            at + 8,
            at + 16,
            at + 20,
            at + 28,
            at + 36,
            at + 44,
            at + 48,
            at + 52,
            at + 56,
            at + 64,
            at + 72,
            at + 104,
            at + 108,
            at + 112,
            at + 116,
            at + 120,
            at + 244,
            at + 248,
            at + 248 + 32,
        ] {
            let mut changed = vbmeta.clone();
            changed[offset] ^= 1;
            assert!(
                verity_layout(&footer, &changed, 16_384).is_err(),
                "vbmeta offset {offset}"
            );
        }
        assert!(verity_layout(&footer, &vbmeta, 8192).is_err());
    }
}
