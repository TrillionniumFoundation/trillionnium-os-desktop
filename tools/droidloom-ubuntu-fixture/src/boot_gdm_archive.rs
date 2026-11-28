//! Bounded read-only selection from the exact normal GDM package archives.
//! No archive namespace is extracted and none of its aliases is followed.
use crate::{Result, ensure};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, PartialEq, Eq)]
pub(super) struct Member {
    pub kind: u8,
    pub mode: u32,
    pub body: Vec<u8>,
    pub link: String,
}

pub(super) fn safe(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && path.split('/').all(|p| {
            !p.is_empty()
                && p != "."
                && p != ".."
                && p.bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._+@-".contains(&b))
        })
}

pub(super) fn read(
    tar: &[u8],
    aliases: &BTreeMap<&str, &str>,
    count: usize,
) -> Result<BTreeMap<String, Member>> {
    ensure(
        tar.len() <= 16 * 1024 * 1024 && count <= 4096,
        "GDM archive bound exceeded",
    )?;
    let mut offset = 0usize;
    let mut entries = BTreeMap::new();
    let mut links = BTreeSet::new();
    loop {
        let h = tar
            .get(offset..offset + 512)
            .ok_or("truncated GDM tar header")?;
        offset += 512;
        if h.iter().all(|b| *b == 0) {
            ensure(
                tar.len() >= offset + 512
                    && tar.len() - offset <= 10752
                    && tar[offset..].iter().all(|b| *b == 0),
                "GDM tar termination differs",
            )?;
            break;
        }
        let checksum: u64 = h
            .iter()
            .enumerate()
            .map(|(i, b)| {
                if (148..156).contains(&i) {
                    32
                } else {
                    u64::from(*b)
                }
            })
            .sum();
        ensure(
            crate::boot_host::octal(&h[148..156])? == checksum,
            "GDM tar checksum differs",
        )?;
        let gnu = &h[257..265] == b"ustar  \0";
        let posix = &h[257..263] == b"ustar\0" && &h[263..265] == b"00";
        ensure(gnu || posix, "GDM archive must be ordinary GNU/POSIX ustar")?;
        ensure(
            !gnu || h[345..500].iter().all(|b| *b == 0),
            "GNU extended metadata refused",
        )?;
        let kind = match h[156] {
            0 | b'0' => b'0',
            v => v,
        };
        ensure(
            [b'0', b'2', b'5'].contains(&kind),
            "GDM special, hard-link or extension member refused",
        )?;
        ensure(
            crate::boot_host::octal(&h[108..116])? == 0
                && crate::boot_host::octal(&h[116..124])? == 0,
            "GDM archive owner differs",
        )?;
        let name = crate::boot_host::text_field(&h[..100])?;
        let prefix = if gnu {
            ""
        } else {
            crate::boot_host::text_field(&h[345..500])?
        };
        let combined = if prefix.is_empty() {
            name.to_owned()
        } else {
            format!("{prefix}/{name}")
        };
        let path = combined
            .strip_prefix("./")
            .unwrap_or(&combined)
            .trim_end_matches('/');
        ensure(
            (path.is_empty() && kind == b'5') || safe(path),
            "unsafe GDM member path",
        )?;
        let link = crate::boot_host::text_field(&h[157..257])?;
        if kind == b'2' {
            ensure(
                aliases.get(path) == Some(&link) && links.insert(path.to_owned()),
                "unreviewed GDM archive alias",
            )?;
        } else {
            ensure(link.is_empty(), "ordinary GDM member has a link target")?;
        }
        let size = usize::try_from(crate::boot_host::octal(&h[124..136])?)?;
        let mode = u32::try_from(crate::boot_host::octal(&h[100..108])?)?;
        // Source packages have their original 0664/0775 metadata; no member is
        // installed from them. Only the fixed selected binary may become 0755.
        ensure(
            mode & !0o777 == 0 && (kind == b'0' || size == 0) && (kind != b'2' || mode == 0o777),
            "GDM archive mode/size differs",
        )?;
        let end = offset.checked_add(size).ok_or("GDM member size overflow")?;
        let body = tar.get(offset..end).ok_or("truncated GDM member")?.to_vec();
        ensure(
            entries.len() < count
                && entries
                    .insert(
                        path.to_owned(),
                        Member {
                            kind,
                            mode,
                            body,
                            link: link.to_owned(),
                        },
                    )
                    .is_none(),
            "duplicate/excessive GDM members",
        )?;
        offset = end;
        let padding = (512 - size % 512) % 512;
        ensure(
            tar.get(offset..offset + padding)
                .is_some_and(|b| b.iter().all(|v| *v == 0)),
            "GDM member padding differs",
        )?;
        offset += padding;
    }
    ensure(
        entries.len() == count
            && links.iter().map(String::as_str).collect::<BTreeSet<_>>()
                == aliases.keys().copied().collect(),
        "GDM archive inventory differs",
    )?;
    Ok(entries)
}

pub(super) fn regular<'a>(
    entries: &'a BTreeMap<String, Member>,
    path: &str,
    mode: Option<u32>,
) -> Result<&'a [u8]> {
    let member = entries
        .get(path)
        .ok_or("required GDM archive member absent")?;
    ensure(
        member.kind == b'0' && mode.is_none_or(|v| v == member.mode),
        "selected GDM member is not the required regular file",
    )?;
    Ok(&member.body)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn tar(path: &str, kind: u8, body: &[u8], target: &str) -> Vec<u8> {
        let mut h = [0u8; 512];
        h[..path.len()].copy_from_slice(path.as_bytes());
        h[100..108].copy_from_slice(b"0000755\0");
        h[108..116].copy_from_slice(b"0000000\0");
        h[116..124].copy_from_slice(b"0000000\0");
        h[124..136].copy_from_slice(format!("{:011o}\0", body.len()).as_bytes());
        h[148..156].fill(b' ');
        h[156] = kind;
        h[157..157 + target.len()].copy_from_slice(target.as_bytes());
        h[257..265].copy_from_slice(
            b"ustar\0"
                .iter()
                .copied()
                .chain(*b"00")
                .collect::<Vec<_>>()
                .as_slice(),
        );
        let sum: u64 = h.iter().map(|b| u64::from(*b)).sum();
        h[148..156].copy_from_slice(format!("{sum:06o}\0 ").as_bytes());
        let mut t = h.to_vec();
        t.extend(body);
        t.resize((t.len() + 511) / 512 * 512 + 1024, 0);
        t
    }
    #[test]
    fn archive_rejects_path_alias_special_duplicate_and_truncation() -> Result<()> {
        let good = tar("usr/sbin/gdm3", b'0', b"actual bytes", "");
        assert_eq!(
            regular(
                &read(&good, &BTreeMap::new(), 1)?,
                "usr/sbin/gdm3",
                Some(0o755)
            )?,
            b"actual bytes"
        );
        for (name, kind, link) in [
            ("../gdm3", b'0', ""),
            ("/usr/sbin/gdm3", b'0', ""),
            ("usr/sbin/gdm3", b'2', "../other"),
            ("usr/sbin/gdm3", b'3', ""),
        ] {
            assert!(read(&tar(name, kind, b"", link), &BTreeMap::new(), 1).is_err());
        }
        let mut duplicate = good[..1024].to_vec();
        duplicate.extend_from_slice(&good);
        assert!(read(&duplicate, &BTreeMap::new(), 2).is_err());
        assert!(read(&good[..700], &BTreeMap::new(), 1).is_err());
        let mut corrupt = good.clone();
        corrupt[600] = 1;
        assert!(read(&corrupt, &BTreeMap::new(), 1).is_err());
        assert!(read(&good, &BTreeMap::new(), 2).is_err());
        Ok(())
    }
}
