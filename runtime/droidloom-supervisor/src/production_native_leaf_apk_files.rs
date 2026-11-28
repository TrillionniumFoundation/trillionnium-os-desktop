//! Original APK file custody inside the separately born read-only helper.
//!
//! The broker's authenticated private plan contains fresh normal PM paths.
//! This module never opens a caller-selected file or returns an original APK
//! descriptor. It transfers at most one sealed public copy per operation.
use super::apk_protocol::{self as protocol, Begin, Copy, FileIdentity, Original, PackageFiles};
use crate::control::application_probe::{ApplicationInspection, ApplicationMetadata, InstalledApk};
use sha2::{Digest, Sha256};
use std::ffi::CString;
use std::fs::File;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::fs::FileExt;
use std::time::Instant;

const COPY_LABEL: &[u8] = b"u:object_r:droidloom_native_leaf_apk_copy:s0";
const SEALS: i32 = libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE;
type Result<T> = std::result::Result<T, String>;

fn before(end: Instant) -> Result<()> {
    protocol::need(Instant::now() < end, "APK original absolute deadline elapsed")
}
fn label(file: &File) -> Result<Vec<u8>> {
    let mut bytes=[0_u8;256];
    let n=unsafe { libc::fgetxattr(file.as_raw_fd(),c"security.selinux".as_ptr(),bytes.as_mut_ptr().cast(),bytes.len()) };
    if n < 0 { return Err(io::Error::last_os_error().to_string()); }
    let value=&bytes[..n as usize];
    Ok(value.strip_suffix(b"\0").unwrap_or(value).to_vec())
}
fn open_apk(root: &File, path: &str) -> Result<File> {
    protocol::need(protocol::apk_path(path), "APK path outside the actual PM vocabulary")?;
    #[repr(C)]
    struct OpenHow { flags:u64, mode:u64, resolve:u64 }
    // IN_ROOT permits Android's ordinary /product and /system_ext links but
    // cannot escape this original root. Magic links and a symlink final APK
    // are rejected; no host /proc path or pathname authority is supplied.
    let how=OpenHow { flags:(libc::O_RDONLY|libc::O_CLOEXEC|libc::O_NOFOLLOW|libc::O_NONBLOCK) as u64,
        mode:0, resolve:0x10|0x02 };
    let name=CString::new(path).map_err(|e|e.to_string())?;
    let raw=unsafe { libc::syscall(libc::SYS_openat2,root.as_raw_fd(),name.as_ptr(),&how,std::mem::size_of::<OpenHow>()) };
    if raw<0 { return Err(io::Error::last_os_error().to_string()); }
    Ok(unsafe { File::from_raw_fd(raw as i32) })
}
fn identity(file: &File) -> Result<FileIdentity> {
    file.metadata().map(|m|FileIdentity::of(&m)).map_err(|e|e.to_string())
}
fn hash(file: &File, expected: &FileIdentity, end: Instant) -> Result<String> {
    before(end)?;
    protocol::need(identity(file)? == *expected, "APK held descriptor changed before full hash")?;
    let mut offset=0_u64;
    let mut digest=Sha256::new();
    let mut bytes=[0_u8;65_536];
    while offset<expected.bytes {
        before(end)?;
        let limit=bytes.len().min((expected.bytes-offset) as usize);
        let n=file.read_at(&mut bytes[..limit],offset).map_err(|e|e.to_string())?;
        protocol::need(n>0,"APK body became short")?;
        digest.update(&bytes[..n]);
        offset+=n as u64;
    }
    protocol::need(file.read_at(&mut bytes[..1],offset).map_err(|e|e.to_string())? == 0
        && identity(file)? == *expected,"APK complete bytes or held metadata changed")?;
    before(end)?;
    Ok(format!("{:x}",digest.finalize()))
}

struct HeldApk {
    file: File,
    observed: Original,
}
pub(super) struct HeldApkFiles {
    root: File,
    root_identity: (u64,u64),
    files: Vec<HeldApk>,
    packages: Vec<PackageFiles>,
}
impl HeldApkFiles {
    // This is called only after the helper has authenticated its original
    // broker PIDFD and received that broker's actual framework root descriptor.
    pub(super) fn capture(root: File, actual: &[ApplicationMetadata], begin: &Begin, end: Instant)
        -> Result<Self>
    {
        use std::os::unix::fs::MetadataExt;
        before(end)?;
        begin.validate()?;
        let roles=begin.scope().roles();
        protocol::need(actual.len()==roles.len(),"APK actual metadata omitted a fixed source role")?;
        let root_meta=root.metadata().map_err(|e|e.to_string())?;
        protocol::need(root_meta.is_dir(),"APK original framework root is not a directory")?;
        let root_identity=(root_meta.dev(),root_meta.ino());
        let mut files=Vec::new();
        let mut packages=Vec::with_capacity(roles.len());
        let mut group_bytes=0_u64;
        // Every pathname comes from the broker's freshly retired fixed PM
        // query, for the source-selected role in this exact order.
        for (metadata,role) in actual.iter().zip(roles) {
            protocol::need(metadata.package==role.package && metadata.user==0 && metadata.uid<100_000
                && metadata.version_code>0 && metadata.epoch==begin.main().epoch
                && !metadata.apks.is_empty() && metadata.apks.len()<=role.max_apks,
                "APK fresh actual role metadata differs")?;
            let mut originals=Vec::with_capacity(metadata.apks.len());
            let mut package_bytes=0_u64;
            for path in &metadata.apks {
                before(end)?;
                let file=open_apk(&root,&path.path)?;
                let node=identity(&file)?;
                node.original(node.bytes)?;
                package_bytes=package_bytes.checked_add(node.bytes).ok_or("APK role size overflow")?;
                group_bytes=group_bytes.checked_add(node.bytes).ok_or("APK group size overflow")?;
                protocol::need(package_bytes<=role.max_bytes
                    && group_bytes<=super::apk_scope::MAX_GROUP_BYTES
                    && files.len()<super::apk_scope::MAX_GROUP_APKS,"APK actual original group exceeds fixed bounds")?;
                let observed=Original { package:metadata.package.clone(),
                    apk:InstalledApk{name:path.name.clone(),path:path.path.clone(),bytes:node.bytes,
                        sha256:hash(&file,&node,end)?},
                    identity:node,selinux:String::from_utf8(label(&file)?).map_err(|e|e.to_string())? };
                observed.validate()?;
                originals.push(observed.clone());
                files.push(HeldApk{file,observed});
            }
            let application=ApplicationInspection{package:metadata.package.clone(),user:metadata.user,
                uid:metadata.uid,version_code:metadata.version_code,epoch:metadata.epoch.clone(),
                apks:originals.iter().map(|v|v.apk.clone()).collect()};
            packages.push(PackageFiles{application,originals});
        }
        protocol::validate_packages(begin,&packages)?;
        let value=Self{root,root_identity,files,packages};
        value.guard(false,end)?;
        Ok(value)
    }
    pub(super) fn packages(&self) -> Vec<PackageFiles> { self.packages.clone() }
    pub(super) fn len(&self) -> usize { self.files.len() }
    pub(super) fn guard(&self, full: bool, end: Instant) -> Result<()> {
        use std::os::unix::fs::MetadataExt;
        before(end)?;
        let root=self.root.metadata().map_err(|e|e.to_string())?;
        protocol::need(root.is_dir() && (root.dev(),root.ino()) == self.root_identity,"APK original root changed")?;
        for held in &self.files {
            before(end)?;
            let named=open_apk(&self.root,&held.observed.apk.path)?;
            protocol::need(identity(&named)? == held.observed.identity
                && identity(&held.file)? == held.observed.identity
                && label(&named)? == held.observed.selinux.as_bytes()
                && label(&held.file)? == held.observed.selinux.as_bytes(),"APK original named/held F9 or label changed")?;
            if full {
                protocol::need(hash(&held.file,&held.observed.identity,end)? == held.observed.apk.sha256,
                    "APK original whole SHA changed")?;
            }
        }
        before(end)
    }
    pub(super) fn copy(&self, ordinal:usize, end:Instant) -> Result<(Copy,File)> {
        self.guard(false,end)?;
        let held=self.files.get(ordinal).ok_or("APK copy ordinal outside held actual set")?;
        let name=CString::new(protocol::COPY_NAME).map_err(|e|e.to_string())?;
        let raw=unsafe { libc::memfd_create(name.as_ptr(),libc::MFD_CLOEXEC|libc::MFD_ALLOW_SEALING) };
        if raw<0 { return Err(io::Error::last_os_error().to_string()); }
        let write=unsafe {File::from_raw_fd(raw)};
        protocol::need(label(&write)? == COPY_LABEL,"APK public copy did not receive its fixed automatic label")?;
        let mut offset=0_u64;
        let mut digest=Sha256::new();
        let mut buffer=[0_u8;65_536];
        while offset<held.observed.apk.bytes {
            before(end)?;
            let limit=buffer.len().min((held.observed.apk.bytes-offset) as usize);
            let n=held.file.read_at(&mut buffer[..limit],offset).map_err(|e|e.to_string())?;
            protocol::need(n>0,"APK original short during copy")?;
            digest.update(&buffer[..n]);
            let mut written=0;
            while written<n {
                before(end)?;
                let amount=write.write_at(&buffer[written..n],offset+written as u64).map_err(|e|e.to_string())?;
                protocol::need(amount>0,"APK sealed copy short write")?;
                written+=amount;
            }
            offset+=n as u64;
        }
        protocol::need(held.file.read_at(&mut buffer[..1],offset).map_err(|e|e.to_string())?==0
            && format!("{:x}",digest.finalize())==held.observed.apk.sha256
            && identity(&held.file)?==held.observed.identity,"APK copy differs from original full bytes")?;
        if unsafe {libc::fchmod(write.as_raw_fd(),0o400)}!=0
            || unsafe {libc::fcntl(write.as_raw_fd(),libc::F_ADD_SEALS,SEALS)}!=0 {
            return Err(io::Error::last_os_error().to_string());
        }
        // Reopen only this held numeric descriptor to get a read-only OFD.
        // A writable description is never sent to the parent or host.
        let path=CString::new(format!("/proc/self/fd/{}",write.as_raw_fd())).map_err(|e|e.to_string())?;
        let raw=unsafe {libc::open(path.as_ptr(),libc::O_RDONLY|libc::O_CLOEXEC)};
        if raw<0 {return Err(io::Error::last_os_error().to_string());}
        let readonly=unsafe {File::from_raw_fd(raw)};
        let copy_node=identity(&readonly)?;
        protocol::need(copy_node==identity(&write)?
            && unsafe{libc::fcntl(readonly.as_raw_fd(),libc::F_GETFL)} & libc::O_ACCMODE==libc::O_RDONLY
            && unsafe{libc::fcntl(readonly.as_raw_fd(),libc::F_GET_SEALS)}==SEALS
            && label(&readonly)?==COPY_LABEL,"APK sealed readonly description changed")?;
        drop(write);
        let copy_hash=hash(&readonly,&copy_node,end)?;
        let comparison=Copy {ordinal:ordinal as u32,original:held.observed.clone(),sealed_copy:copy_node,
            sealed_copy_sha256:copy_hash,seals:SEALS};
        comparison.validate()?;
        self.guard(false,end)?;
        Ok((comparison,readonly))
    }
}
