//! Bind the existing fixed Pocket4 userdata pair without copying or changing it.
use super::{
    Result,
    activation_files::{self as files, FileIdentity, FilePin, HeldFile},
};
use droidloom_supervisor::CellSpec;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    fs::File,
    os::{fd::AsRawFd, unix::fs::FileExt},
    path::Path,
};

const DATA: &str = "/var/lib/droidloom/users/1000/data/data.img";
const METADATA: &str = "/var/lib/droidloom/users/1000/data/metadata.img";
const SPEC: &str = "/etc/droidloom/cell.json";

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct OriginalInputs {
    pub cell: FilePin,
    pub data: FileIdentity,
    pub metadata: FileIdentity,
}

fn require(ok: bool, message: &str) -> Result<()> {
    if ok { Ok(()) } else { Err(message.into()) }
}
fn identity(file: &File) -> Result<FileIdentity> {
    let id = FileIdentity::read(file.metadata()?)?;
    require(
        id.uid == 0 && id.gid == 0 && id.mode & 0o7777 == 0o600,
        "original userdata is not a single root-owned 0600 ordinary file",
    )?;
    files::no_privilege_xattrs(file)?;
    Ok(id)
}

const ORIGINAL_LABEL: &[u8] = b"u:object_r:p4_linux_product_store_t:s0\0";
fn original_label(file: &File) -> Result<Option<Vec<u8>>> {
    let mut value = vec![0; 4096];
    let size = unsafe {
        libc::fgetxattr(
            file.as_raw_fd(),
            c"security.selinux".as_ptr(),
            value.as_mut_ptr().cast(),
            value.len(),
        )
    };
    if size < 0 {
        let e = std::io::Error::last_os_error();
        if e.raw_os_error() == Some(libc::ENODATA) {
            return Ok(None);
        }
        return Err(e.into());
    }
    value.truncate(size as usize);
    require(
        value == ORIGINAL_LABEL,
        "original userdata has an unrelated SELinux label",
    )?;
    Ok(Some(value))
}
fn label_metadata_only(before: &FileIdentity, after: &FileIdentity) -> bool {
    (
        before.device,
        before.inode,
        before.mode,
        before.uid,
        before.gid,
        before.links,
        before.bytes,
        before.modified_sec,
        before.modified_nsec,
    ) == (
        after.device,
        after.inode,
        after.mode,
        after.uid,
        after.gid,
        after.links,
        after.bytes,
        after.modified_sec,
        after.modified_nsec,
    )
}

struct OriginalImage {
    path: &'static str,
    file: File,
    initial: FileIdentity,
    identity: FileIdentity,
    policy: Value,
}
impl OriginalImage {
    fn open(path: &'static str, expected: &FileIdentity) -> Result<Self> {
        let file = files::open_regular(Path::new(path))?;
        let actual = identity(&file)?;
        require(
            &actual == expected,
            "original fixed userdata inode changed since planning",
        )?;
        let policy = read_ext4(&file, actual.bytes)?;
        original_label(&file)?;
        let result = Self {
            path,
            file,
            initial: actual.clone(),
            identity: actual,
            policy,
        };
        result.revalidate()?;
        Ok(result)
    }
    fn revalidate(&self) -> Result<()> {
        require(
            identity(&self.file)? == self.identity
                && identity(&files::open_regular(Path::new(self.path))?)? == self.identity
                && read_ext4(&self.file, self.identity.bytes)? == self.policy,
            "original userdata identity or ext4 metadata changed; replacement refused",
        )
    }
}
pub(super) struct OriginalData {
    cell: HeldFile,
    data: OriginalImage,
    metadata: OriginalImage,
    cell_spec: CellSpec,
}
impl OriginalData {
    pub(super) fn open(input: &OriginalInputs) -> Result<Self> {
        require(
            input.cell.path == Path::new(SPEC),
            "first activation binds only the fixed original cell",
        )?;
        let cell = HeldFile::open(&input.cell, 1024 * 1024)?;
        require(
            cell.identity().uid == 0 && cell.identity().gid == 0,
            "original cell is not controlled by root",
        )?;
        let spec: CellSpec = serde_json::from_slice(&cell.read_all(1024 * 1024)?)?;
        spec.validate()?;
        require(
            spec.host_uid == 1000
                && spec.data_dir == Path::new("/var/lib/droidloom/users/1000/data"),
            "this first activation only supports the existing Pocket4 user 1000 data store",
        )?;
        let data = OriginalImage::open(DATA, &input.data)?;
        let metadata = OriginalImage::open(METADATA, &input.metadata)?;
        require(
            (data.identity.device, data.identity.inode)
                != (metadata.identity.device, metadata.identity.inode)
                && data.policy["filesystem_uuid"] != metadata.policy["filesystem_uuid"],
            "original data and metadata must be distinct images and filesystems",
        )?;
        let result = Self {
            cell,
            data,
            metadata,
            cell_spec: spec,
        };
        result.revalidate()?;
        Ok(result)
    }
    pub(super) fn revalidate(&self) -> Result<()> {
        self.cell.revalidate()?;
        self.revalidate_data()
    }
    pub(super) fn revalidate_data(&self) -> Result<()> {
        self.data.revalidate()?;
        self.metadata.revalidate()
    }
    pub(super) fn apply_labels(
        &mut self,
        labels: &super::activation_labels::Labeler,
        permit: &super::activation_owner::DataLabelPermit<'_>,
    ) -> Result<Value> {
        permit.revalidate(self)?;
        let mut receipts = Vec::new();
        for image in [&mut self.data, &mut self.metadata] {
            image.revalidate()?;
            original_label(&image.file)?;
            let before = image.identity.clone();
            receipts.push(labels.apply_file(&image.file, Path::new(image.path))?);
            let observed = identity(&image.file)?;
            require(
                label_metadata_only(&before, &observed)
                    && identity(&files::open_regular(Path::new(image.path))?)? == observed
                    && read_ext4(&image.file, observed.bytes)? == image.policy
                    && original_label(&image.file)?.as_deref() == Some(ORIGINAL_LABEL),
                "userdata label changed more than the original same-inode SELinux metadata",
            )?;
            image.identity = observed;
            image.revalidate()?;
        }
        permit.revalidate(self)?;
        Ok(json!({"files":receipts,"original_inode_preserved":true,"userdata_bytes_written":0}))
    }
    pub(super) fn original_cell(&self) -> &HeldFile {
        &self.cell
    }
    pub(super) fn cell_spec(&self) -> &CellSpec {
        &self.cell_spec
    }
    pub(super) fn backing_inodes(&self) -> [(u64, u64); 2] {
        [
            (self.data.identity.device, self.data.identity.inode),
            (self.metadata.identity.device, self.metadata.identity.inode),
        ]
    }
    pub(super) fn persistent_policy(&self) -> Value {
        json!({"mode":"original-ext4-v1","data":self.data.policy,"metadata":self.metadata.policy})
    }
    pub(super) fn receipt(&self) -> Value {
        json!({"cell":self.cell.pin(),"data":{"path":DATA,"initial_identity":self.data.initial,"identity":self.data.identity,"policy":self.data.policy},
            "metadata":{"path":METADATA,"initial_identity":self.metadata.initial,"identity":self.metadata.identity,"policy":self.metadata.policy},
            "original_userdata_preserved":true,"userdata_bytes_written":0,"userdata_copied":false,
            "runtime_qualified":false})
    }
}
pub(super) fn inspect() -> Result<OriginalInputs> {
    super::require_root()?;
    super::require_legacy()?;
    let cell = files::pin_file(Path::new(SPEC))?;
    let data = identity(&files::open_regular(Path::new(DATA))?)?;
    let metadata = identity(&files::open_regular(Path::new(METADATA))?)?;
    let result = OriginalInputs {
        cell,
        data,
        metadata,
    };
    OriginalData::open(&result)?.revalidate()?;
    Ok(result)
}
fn u16_at(bytes: &[u8], offset: usize) -> Result<u16> {
    Ok(u16::from_le_bytes(
        bytes
            .get(offset..offset + 2)
            .ok_or("truncated ext4 field")?
            .try_into()?,
    ))
}
fn u32_at(bytes: &[u8], offset: usize) -> Result<u32> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .ok_or("truncated ext4 field")?
            .try_into()?,
    ))
}
fn uuid(raw: &[u8]) -> Result<String> {
    require(
        raw.len() == 16 && raw.iter().any(|b| *b != 0),
        "empty ext4 UUID",
    )?;
    let h: String = raw.iter().map(|b| format!("{b:02x}")).collect();
    Ok(format!(
        "{}-{}-{}-{}-{}",
        &h[..8],
        &h[8..12],
        &h[12..16],
        &h[16..20],
        &h[20..]
    ))
}
/// Read only the original superblock, group-zero inode table and root inode.
/// No mount, journal replay, debugfs write, mkfs or working copy is involved.
fn read_ext4(file: &File, bytes: u64) -> Result<Value> {
    require(
        (16 * 1024 * 1024..=256 * 1024 * 1024 * 1024).contains(&bytes) && bytes % 4096 == 0,
        "original userdata size is outside the reviewed ext4 profile",
    )?;
    let mut sb = [0u8; 1024];
    file.read_exact_at(&mut sb, 1024)?;
    require(
        u16_at(&sb, 56)? == 0xef53
            && u32_at(&sb, 24)? == 2
            && u16_at(&sb, 88)? == 256
            && u32_at(&sb, 20)? == 0
            && u32_at(&sb, 40)? >= 2
            && u16_at(&sb, 58)? & 3 == 1,
        "original userdata needs a clean ordinary 4096/256 ext4 filesystem",
    )?;
    let compat = u32_at(&sb, 92)?;
    let incompat = u32_at(&sb, 96)?;
    let ro = u32_at(&sb, 100)?;
    require(
        compat & !0x103c == 0
            && compat & 4 == 4
            && incompat & !0x22c2 == 0
            && incompat & 0x42 == 0x42
            && ro & !0x846b == 0
            && ro & 0x400 == 0x400,
        "original userdata has recovery pending or an unreviewed ext4 feature",
    )?;
    let blocks = u64::from(u32_at(&sb, 4)?) | (u64::from(u32_at(&sb, 0x150)?) << 32);
    require(
        blocks.checked_mul(4096).is_some_and(|n| n == bytes),
        "original ext4 geometry differs from the complete backing file",
    )?;
    let desc_size = if incompat & 0x80 != 0 {
        u16_at(&sb, 254)? as usize
    } else {
        32
    };
    require(
        [32, 64].contains(&desc_size),
        "unsupported original ext4 group descriptor",
    )?;
    let mut gd = vec![0; desc_size];
    file.read_exact_at(&mut gd, 4096)?;
    let table = u64::from(u32_at(&gd, 8)?)
        | (if desc_size == 64 {
            u64::from(u32_at(&gd, 40)?) << 32
        } else {
            0
        });
    let offset = table
        .checked_mul(4096)
        .and_then(|v| v.checked_add(256))
        .ok_or("root inode offset overflow")?;
    require(
        table > 1 && offset.checked_add(256).is_some_and(|n| n <= bytes),
        "original ext4 root inode lies outside the backing image",
    )?;
    let mut inode = [0; 256];
    file.read_exact_at(&mut inode, offset)?;
    let mode = u16_at(&inode, 0)? as u32;
    let uid = u32::from(u16_at(&inode, 2)?) | (u32::from(u16_at(&inode, 120)?) << 16);
    let gid = u32::from(u16_at(&inode, 24)?) | (u32::from(u16_at(&inode, 122)?) << 16);
    require(
        mode & libc::S_IFMT == libc::S_IFDIR
            && mode & 0o700 == 0o700
            && mode & 0o7002 == 0
            && uid < 100000
            && gid < 100000,
        "original filesystem root cannot be mapped by the selected normal cell",
    )?;
    Ok(
        json!({"image_bytes":bytes,"filesystem_uuid":uuid(&sb[104..120])?,
        "feature_compat":compat,"feature_incompat":incompat,"feature_ro_compat":ro,
        "guest_root_uid":uid,"guest_root_gid":gid,"guest_root_mode":mode & 0o777}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> (tempfile::TempDir, File) {
        use std::os::unix::fs::FileExt;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("image");
        let file = std::fs::OpenOptions::new()
            .create_new(true)
            .read(true)
            .write(true)
            .open(path)
            .unwrap();
        file.set_len(16 * 1024 * 1024).unwrap();
        let mut sb = [0u8; 1024];
        sb[4..8].copy_from_slice(&4096u32.to_le_bytes());
        sb[24..28].copy_from_slice(&2u32.to_le_bytes());
        sb[40..44].copy_from_slice(&4096u32.to_le_bytes());
        sb[56..58].copy_from_slice(&0xef53u16.to_le_bytes());
        sb[58..60].copy_from_slice(&1u16.to_le_bytes());
        sb[88..90].copy_from_slice(&256u16.to_le_bytes());
        sb[92..96].copy_from_slice(&0x3cu32.to_le_bytes());
        sb[96..100].copy_from_slice(&0x22c2u32.to_le_bytes());
        sb[100..104].copy_from_slice(&0x46bu32.to_le_bytes());
        sb[104..120].copy_from_slice(&[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]);
        sb[254..256].copy_from_slice(&64u16.to_le_bytes());
        file.write_all_at(&sb, 1024).unwrap();
        let mut gd = [0u8; 64];
        gd[8..12].copy_from_slice(&5u32.to_le_bytes());
        file.write_all_at(&gd, 4096).unwrap();
        let mut ino = [0u8; 256];
        ino[..2].copy_from_slice(&(libc::S_IFDIR as u16 | 0o755).to_le_bytes());
        file.write_all_at(&ino, 5 * 4096 + 256).unwrap();
        (dir, file)
    }
    #[test]
    fn reads_original_ext4_identity_without_mutation() {
        let (_dir, file) = fixture();
        let before = FileIdentity::read(file.metadata().unwrap()).unwrap();
        let policy = read_ext4(&file, 16 * 1024 * 1024).unwrap();
        assert_eq!(
            policy["filesystem_uuid"],
            "01020304-0506-0708-090a-0b0c0d0e0f10"
        );
        assert_eq!(policy["guest_root_mode"], 0o755);
        assert_eq!(
            FileIdentity::read(file.metadata().unwrap()).unwrap(),
            before
        );
    }
    #[test]
    fn refuses_recovery_geometry_alias_and_unmappable_root() {
        for mutation in 0..5 {
            let (_dir, file) = fixture();
            match mutation {
                0 => file
                    .write_all_at(&0x22c6u32.to_le_bytes(), 1024 + 96)
                    .unwrap(),
                1 => file.write_all_at(&0u16.to_le_bytes(), 1024 + 58).unwrap(),
                2 => file.write_all_at(&4097u32.to_le_bytes(), 1024 + 4).unwrap(),
                3 => file.write_all_at(&[0; 16], 1024 + 104).unwrap(),
                _ => file
                    .write_all_at(
                        &(libc::S_IFREG as u16 | 0o755).to_le_bytes(),
                        5 * 4096 + 256,
                    )
                    .unwrap(),
            }
            assert!(read_ext4(&file, 16 * 1024 * 1024).is_err());
        }
    }
}
