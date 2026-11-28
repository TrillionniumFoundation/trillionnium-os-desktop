//! Fixed independent EMPTY diagnostic input. These serialized values are only
//! comparisons. The live storage provider must read both entire readonly
//! images before its first writable open; a selection flag is not authority.
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io,
    os::unix::fs::{FileExt, MetadataExt},
};

pub const SCHEMA: &str = "droidloom.empty-meituan-diagnostic.v1";
pub const PACKAGE: &str = "com.sankuai.meituan.takeoutnew";
pub const VERSION_CODE: u64 = 800_870_002;
pub const VERSION_NAME: &str = "8.87.2";
pub const APK_BYTES: u64 = 64_632_545;
pub const APK_SHA256: &str = "66e5d03668d4bcd34457539fe92c1284c1f4493e4d31cdfacb250d7b71fc9733";
pub const SIGNER_SHA256: &str = "73a611c3a01dc6e11388873daeee1e556ad9e5768e5c222055f508a24c3a8215";
pub const DIRECTORY: &str = "/var/lib/droidloom-qualification/empty-meituan-diagnostic";
pub const APK_PATH: &str = "/var/lib/droidloom-qualification/empty-meituan-diagnostic/official.apk";
pub const UNIT: &str = "droidloom-empty-meituan-diagnostic.service";
pub const PROGRAM: &str = "/usr/bin/droidloomctl";
pub const ARGUMENT: &str = "empty-meituan-diagnostic";
pub const MKFS_BYTES: u64 = 146_136;
pub const MKFS_SHA256: &str = "e42e49656dfc308efeed86f9bfad7746fc22ad1d4a3b0d508b5dba7a4b9a904f";
pub const MKFS_TIME: &str = "1735689600";
pub const JOURNAL_SCHEMA: &str = "droidloom.empty-meituan-journal.v1";
pub const JOURNAL_CHUNK_BYTES: usize = 2048;
pub const JOURNAL_REPORT_LIMIT: usize = 2 * 1024 * 1024;
pub const FEATURES: &str = "none,has_journal,ext_attr,resize_inode,dir_index,filetype,extent,64bit,flex_bg,metadata_csum,metadata_csum_seed,sparse_super,large_file,huge_file,dir_nlink,extra_isize";

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct JournalFrame {
    schema: String,
    index: usize,
    count: usize,
    bytes: usize,
    sha256: String,
    data_hex: String,
}
/// Bounded comparison frames for the ordinary journal. These contain no grant.
pub fn journal_lines(report: &serde_json::Value) -> Result<Vec<String>, String> {
    let body = serde_json::to_vec(report).map_err(|e| e.to_string())?;
    if body.is_empty() || body.len() > JOURNAL_REPORT_LIMIT || report["schema"] != SCHEMA {
        return Err("EMPTY diagnostic report differs from the fixed bounded protocol".into());
    }
    let count = body.len().div_ceil(JOURNAL_CHUNK_BYTES);
    let sha256 = format!("{:x}", Sha256::digest(&body));
    body.chunks(JOURNAL_CHUNK_BYTES)
        .enumerate()
        .map(|(index, chunk)| {
            let data_hex = chunk.iter().map(|v| format!("{v:02x}")).collect::<String>();
            serde_json::to_string(&JournalFrame {
                schema: JOURNAL_SCHEMA.into(),
                index,
                count,
                bytes: body.len(),
                sha256: sha256.clone(),
                data_hex,
            })
            .map_err(|e| e.to_string())
        })
        .collect()
}
/// Reassemble only bytes; successful parsing never establishes runtime authority.
pub fn journal_body(lines: &[String]) -> Result<Vec<u8>, String> {
    if lines.is_empty() || lines.len() > JOURNAL_REPORT_LIMIT.div_ceil(JOURNAL_CHUNK_BYTES) {
        return Err("EMPTY journal frame count invalid".into());
    }
    let mut frames = std::collections::BTreeMap::new();
    let mut header = None;
    for line in lines {
        if line.len() > JOURNAL_CHUNK_BYTES * 2 + 512 {
            return Err("EMPTY journal frame exceeds bound".into());
        }
        let frame: JournalFrame = serde_json::from_str(line).map_err(|e| e.to_string())?;
        if frame.schema != JOURNAL_SCHEMA
            || frame.index >= frame.count
            || frame.count != lines.len()
            || frame.bytes == 0
            || frame.bytes > JOURNAL_REPORT_LIMIT
            || frame.bytes.div_ceil(JOURNAL_CHUNK_BYTES) != frame.count
            || frame.sha256.len() != 64
            || !frame
                .sha256
                .bytes()
                .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
            || frame.data_hex.len() % 2 != 0
            || frame.data_hex.len() > JOURNAL_CHUNK_BYTES * 2
            || !frame
                .data_hex
                .bytes()
                .all(|v| v.is_ascii_digit() || (b'a'..=b'f').contains(&v))
        {
            return Err("EMPTY journal frame has invalid fixed fields".into());
        }
        let key = (frame.count, frame.bytes, frame.sha256.clone());
        if header.as_ref().is_some_and(|v| v != &key) {
            return Err("EMPTY journal generations differ".into());
        }
        header = Some(key);
        let raw = frame
            .data_hex
            .as_bytes()
            .chunks_exact(2)
            .map(|v| {
                u8::from_str_radix(std::str::from_utf8(v).expect("checked ASCII"), 16)
                    .expect("checked hex")
            })
            .collect::<Vec<_>>();
        let expected = (frame.bytes - frame.index * JOURNAL_CHUNK_BYTES).min(JOURNAL_CHUNK_BYTES);
        if raw.len() != expected || frames.insert(frame.index, raw).is_some() {
            return Err("EMPTY journal duplicate or incomplete chunk".into());
        }
    }
    let (_, bytes, digest) = header.ok_or("EMPTY journal header absent")?;
    let body = frames.into_values().flatten().collect::<Vec<_>>();
    if body.len() != bytes || format!("{:x}", Sha256::digest(&body)) != digest {
        return Err("EMPTY journal whole bytes differ".into());
    }
    Ok(body)
}

#[derive(Clone, Copy, Debug)]
pub struct ImageRecipe {
    pub name: &'static str,
    pub bytes: u64,
    pub inodes: u64,
    pub uuid: &'static str,
    pub sha256: &'static str,
}

// Actual reviewed mke2fs 1.47.2 outputs, each reproduced on two different
// create-exclusive held files and completely read back before any mount.
pub const IMAGES: [ImageRecipe; 2] = [
    ImageRecipe {
        name: "data",
        bytes: 8_589_934_592,
        inodes: 524_288,
        uuid: "7d640e40-54a1-4a68-812c-68da216ec069",
        sha256: "0ae0f001415943649e8d9c177b4a36c186549daad04b793429f87212d071902d",
    },
    ImageRecipe {
        name: "metadata",
        bytes: 134_217_728,
        inodes: 8192,
        uuid: "9e7db93f-833e-41b6-b9bf-49df7b3c0124",
        sha256: "6d43c4636a165d4306c0d08c7c8dca9ab9bfac1b958fbac25933c1d08f7ca398",
    },
];

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Selection {
    pub schema: String,
}
impl Selection {
    pub fn requested() -> Self {
        Self {
            schema: SCHEMA.into(),
        }
    }
    pub fn validate(&self) -> Result<(), &'static str> {
        if self.schema == SCHEMA {
            Ok(())
        } else {
            Err("unrecognized independent EMPTY diagnostic selection")
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Origin {
    pub schema: String,
    pub initial_sha256: [String; 2],
    pub backings: [[u64; 7]; 2],
}
impl Origin {
    pub(crate) fn validate(&self, actual: [[u64; 7]; 2]) -> Result<(), &'static str> {
        if self.schema != SCHEMA
            || self.backings != actual
            || self.initial_sha256 != IMAGES.map(|v| v.sha256.to_owned())
            || actual[0][0..2] == actual[1][0..2]
            || actual.iter().zip(IMAGES).any(|(n, v)| {
                n[1] == 0
                    || n[2] != 0o100600
                    || n[3] != 0
                    || n[4] != 0
                    || n[5] != 1
                    || n[6] != v.bytes
            })
        {
            return Err(
                "EMPTY origin comparison differs from the fixed initial bodies and actual pair",
            );
        }
        Ok(())
    }
}

fn identity(m: &std::fs::Metadata) -> [u64; 11] {
    [
        m.dev(),
        m.ino(),
        u64::from(m.mode()),
        u64::from(m.uid()),
        u64::from(m.gid()),
        m.nlink(),
        m.len(),
        m.mtime() as u64,
        m.mtime_nsec() as u64,
        m.ctime() as u64,
        m.ctime_nsec() as u64,
    ]
}
/// Full-byte comparison against a compile-time recipe. The caller separately
/// owns and verifies its readonly descriptor; this helper constructs no grant. No expected
/// digest, pathname, receipt or caller-selected role is accepted as a grant.
pub fn verify_initial_image(
    file: &File,
    role: usize,
    mut fence: impl FnMut() -> io::Result<()>,
) -> io::Result<()> {
    let recipe = IMAGES
        .get(role)
        .ok_or_else(|| io::Error::other("fixed EMPTY image role required"))?;
    fence()?;
    let before = file.metadata()?;
    if before.mode() != 0o100600
        || before.uid() != 0
        || before.gid() != 0
        || before.nlink() != 1
        || before.len() != recipe.bytes
    {
        return Err(io::Error::other(
            "root-private readonly complete independent EMPTY image required",
        ));
    }
    let mut hash = Sha256::new();
    let mut buffer = vec![0u8; 1024 * 1024];
    let mut offset = 0;
    while offset < recipe.bytes {
        if offset % (64 * 1024 * 1024) == 0 {
            fence()?;
        }
        let count = buffer.len().min((recipe.bytes - offset) as usize);
        file.read_exact_at(&mut buffer[..count], offset)?;
        hash.update(&buffer[..count]);
        offset += count as u64;
    }
    fence()?;
    if file.read_at(&mut buffer[..1], offset)? != 0
        || identity(&before) != identity(&file.metadata()?)
        || format!("{:x}", hash.finalize()) != recipe.sha256
    {
        return Err(io::Error::other(
            "image is not the complete untouched reviewed EMPTY generation",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_meituan_journal_pair_preserves_large_unicode_and_rejects_missing_duplicate_changed_frames()
     {
        let report = serde_json::json!({"schema":SCHEMA,"ok":false,"production_ready":false,"note":"原始正文".repeat(2500)});
        let mut lines = journal_lines(&report).unwrap();
        assert!(lines.len() > 2);
        assert!(lines.iter().all(|v| v.len() < 8192));
        lines.reverse();
        let raw = journal_body(&lines).unwrap();
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&raw).unwrap(),
            report
        );
        assert!(journal_body(&lines[1..]).is_err());
        let mut duplicate = lines.clone();
        duplicate[0] = duplicate[1].clone();
        assert!(journal_body(&duplicate).is_err());
        let mut changed = lines.clone();
        let mut value: serde_json::Value = serde_json::from_str(&changed[0]).unwrap();
        let mut data = value["data_hex"].as_str().unwrap().to_owned();
        data.replace_range(0..2, "00");
        value["data_hex"] = data.into();
        changed[0] = value.to_string();
        assert!(journal_body(&changed).is_err());
    }
    #[test]
    fn empty_meituan_selection_cannot_carry_a_caller_digest_or_acceptance() {
        Selection::requested().validate().unwrap();
        for extra in ["sha256", "production_ready", "original_copy", "path"] {
            let mut raw = serde_json::json!({"schema": SCHEMA});
            raw[extra] = true.into();
            assert!(serde_json::from_value::<Selection>(raw).is_err());
        }
        assert!(
            Selection {
                schema: "ordinary-empty".into()
            }
            .validate()
            .is_err()
        );
    }
    #[test]
    fn empty_meituan_origin_checks_both_distinct_actual_roles() {
        let nodes = IMAGES.map(|v| {
            [
                12,
                if v.name == "data" { 41 } else { 42 },
                0o100600,
                0,
                0,
                1,
                v.bytes,
            ]
        });
        let value = Origin {
            schema: SCHEMA.into(),
            initial_sha256: IMAGES.map(|v| v.sha256.into()),
            backings: nodes,
        };
        value.validate(nodes).unwrap();
        for index in 0..7 {
            let mut different = nodes;
            different[0][index] ^= 1;
            assert!(value.validate(different).is_err());
        }
        let mut alias = value.clone();
        alias.backings[1][1] = alias.backings[0][1];
        assert!(alias.validate(alias.backings).is_err());
        let mut swapped = value.clone();
        swapped.initial_sha256.swap(0, 1);
        assert!(swapped.validate(nodes).is_err());
    }
}
