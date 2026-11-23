//! Validate a candidate service executable before matching it to the published
//! digest. No function here executes code or grants service admission.

use sha2::{Digest, Sha256};
use std::io;

pub(crate) const MAX_SERVICE: usize = 64 * 1024 * 1024;

/// Inspect the actual bytes of an x86_64 Linux service. A successful structural
/// inspection still requires the sealed package publication and actual policy.
///
/// # Errors
/// Rejects stock CP3A init, other architectures and malformed ELF programs.
pub fn inspect_container_service_elf(bytes: &[u8]) -> io::Result<()> {
    let reject = |message| io::Error::new(io::ErrorKind::InvalidData, message);
    if !(64..=MAX_SERVICE).contains(&bytes.len())
        || bytes[..7] != *b"\x7fELF\x02\x01\x01"
        || !matches!(u16::from_le_bytes([bytes[16], bytes[17]]), 2 | 3)
        || bytes[18..20] != [62, 0]
        || bytes[20..24] != [1, 0, 0, 0]
        || bytes[52..54] != [64, 0]
        || bytes[54..56] != [56, 0]
    {
        return Err(reject("expected a bounded x86_64 executable ELF service"));
    }
    if bytes.len() as u64 == crate::production_cp3a_init_identity::INIT_BYTES
        && format!("{:x}", Sha256::digest(bytes))
            == crate::production_cp3a_init_identity::INIT_SHA256
    {
        return Err(reject(
            "the selected CP3A stock init ELF requires kernel entry and cannot supply the host-managed service",
        ));
    }
    let u64_at = |field: &[u8]| u64::from_le_bytes(field.try_into().expect("fixed ELF64 field"));
    let offset = usize::try_from(u64_at(&bytes[32..40]))
        .map_err(|_| reject("invalid program header offset"))?;
    let count = usize::from(u16::from_le_bytes([bytes[56], bytes[57]]));
    if !(1..=128).contains(&count) || offset < 64 || offset > bytes.len() {
        return Err(reject("invalid service program header table"));
    }
    let table = bytes[offset..]
        .get(..count * 56)
        .ok_or_else(|| reject("truncated service program headers"))?;
    let entry = u64_at(&bytes[24..32]);
    let mut executable_entry = false;
    for header in table.chunks_exact(56) {
        if header[..4] != [1, 0, 0, 0] {
            continue;
        }
        let flags = u32::from_le_bytes(header[4..8].try_into().expect("fixed flags"));
        let file_offset = u64_at(&header[8..16]);
        let address = u64_at(&header[16..24]);
        let file_bytes = u64_at(&header[32..40]);
        let memory_bytes = u64_at(&header[40..48]);
        if file_bytes > memory_bytes
            || file_offset
                .checked_add(file_bytes)
                .is_none_or(|end| end > bytes.len() as u64)
            || address.checked_add(memory_bytes).is_none()
            || flags & 3 == 3
        {
            return Err(reject(
                "invalid or writable-executable service load segment",
            ));
        }
        if flags & 1 != 0
            && entry
                .checked_sub(address)
                .is_some_and(|offset| offset < file_bytes)
        {
            executable_entry = true;
        }
    }
    if !executable_entry {
        return Err(reject(
            "service entry is outside the executable file-backed segments",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn actual_host_elf_has_an_entry_but_scripts_truncation_and_other_architectures_do_not() {
        let binary = std::fs::read("/usr/bin/true").unwrap();
        inspect_container_service_elf(&binary).unwrap();
        assert!(inspect_container_service_elf(b"#!/bin/sh\nexit 0\n").is_err());
        assert!(inspect_container_service_elf(&binary[..64]).is_err());
        let mut other = binary.clone();
        other[18] = 183;
        assert!(inspect_container_service_elf(&other).is_err());
        other = binary;
        other[24..32].fill(255);
        assert!(inspect_container_service_elf(&other).is_err());
    }
}
