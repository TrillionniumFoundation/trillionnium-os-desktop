//! Closed comparison protocol for one original-broker APK custody session.
//!
//! Wire values carry comparisons, never authority. The normal broker selects
//! paths from its fresh Package Manager observation and retains its real child.
//! Original APK descriptors remain in that child. Only a separately sealed
//! copy, with an explicitly different descriptor identity, reaches a host.
use crate::control::application_probe::{ApplicationInspection, ApplicationMetadata, InstalledApk};
use super::apk_scope::{Scope, MAX_GROUP_APKS, MAX_GROUP_BYTES};
use crate::main_custody::RuntimeMainCustody;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::fs::Metadata;
use std::os::unix::fs::MetadataExt;
use std::time::{Duration, Instant};

pub(crate) const MAGIC: &[u8; 8] = b"\x1dDLAPK1\n";
pub(crate) const MAX_FRAME: usize = 262_144;
pub(crate) const MAX_APKS: usize = 32;
// r7 actual 65 APK sizes were checked: largest 357,605,173 bytes.
pub(crate) const MAX_APK_BYTES: u64 = 512 * 1024 * 1024;
pub(crate) const MAX_TOTAL_BYTES: u64 = 1024 * 1024 * 1024;
pub(crate) const MAX_REQUESTS: u32 = 4096;
// The largest fixed row is Gallery rotation, including the complete group
// and both original Gallery inspection transports. This ceiling grants no
// extension of the actual deadline supplied by the normal parent.
pub(crate) const MAX_SESSION: Duration = Duration::from_secs(
    crate::control::physical_qualification_channel::budget::NATIVE_CASE_WINDOWS[8]);
pub(crate) const RETIRE: Duration = Duration::from_secs(3);
pub(crate) const BODY_CAP: Duration = Duration::from_secs(60);
pub(crate) const COPY_NAME: &str = "droidloom-native-leaf-apk-copy";
const SCHEMA: &str = "droidloom.native-leaf-apk-session.v2";

pub(crate) fn need(ok: bool, reason: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(reason.into()) }
}
pub(crate) fn sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
pub(crate) fn monotonic_ns() -> Result<u64, String> {
    let mut value: libc::timespec = unsafe { std::mem::zeroed() };
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut value) } != 0 {
        return Err(std::io::Error::last_os_error().to_string());
    }
    need(value.tv_sec >= 0 && (0..1_000_000_000).contains(&value.tv_nsec), "APK monotonic clock")?;
    (value.tv_sec as u64).checked_mul(1_000_000_000)
        .and_then(|v| v.checked_add(value.tv_nsec as u64)).ok_or("APK clock overflow".into())
}
pub(crate) fn absolute(end: Instant) -> Result<u64, String> {
    let clock = monotonic_ns()?;
    let now = Instant::now();
    let left = end.checked_duration_since(now).filter(|v| !v.is_zero())
        .ok_or("APK original deadline elapsed")?;
    need(left <= MAX_SESSION, "APK session exceeds the original legacy window ceiling")?;
    clock.checked_add(u64::try_from(left.as_nanos()).map_err(|_| "APK deadline overflow")?)
        .ok_or("APK deadline overflow".into())
}
pub(crate) fn deadline(value: u64) -> Result<Instant, String> {
    let now = Instant::now();
    let clock = monotonic_ns()?;
    let left = value.checked_sub(clock).filter(|v| *v > 0).ok_or("APK original deadline elapsed")?;
    need(u128::from(left) <= MAX_SESSION.as_nanos(), "APK absolute deadline exceeds source ceiling")?;
    now.checked_add(Duration::from_nanos(left)).ok_or("APK Instant overflow".into())
}
pub(crate) fn apk_path(path: &str) -> bool {
    let prefixes = ["/data/app/", "/system/", "/system_ext/", "/product/", "/vendor/", "/odm/", "/oem/", "/apex/"];
    path.len() <= 512 && path.ends_with(".apk") && prefixes.iter().any(|p| path.starts_with(p))
        && !path.bytes().any(|b| b.is_ascii_control() || b.is_ascii_whitespace())
        && path.split('/').skip(1).all(|s| !s.is_empty() && s != "." && s != "..")
}
pub(crate) fn validate_apks(apks: &[InstalledApk]) -> Result<(), String> {
    let paths: BTreeSet<_> = apks.iter().map(|v| &v.path).collect();
    let names: BTreeSet<_> = apks.iter().map(|v| &v.name).collect();
    let total = apks.iter().try_fold(0_u64, |a, b| a.checked_add(b.bytes)).ok_or("APK total overflow")?;
    need(!apks.is_empty() && apks.len() <= MAX_APKS && paths.len() == apks.len()
        && names.len() == apks.len() && apks.iter().filter(|v| v.name == "base.apk").count() == 1
        && total <= MAX_TOTAL_BYTES && apks.iter().all(|v| {
            apk_path(&v.path) && v.bytes > 0 && v.bytes <= MAX_APK_BYTES && sha256(&v.sha256)
                && !v.name.is_empty() && v.name.len() <= 255 && v.name.ends_with(".apk")
                && !v.name.bytes().any(|b| b.is_ascii_control() || b.is_ascii_whitespace() || b == b'/')
        }) && apks.windows(2).all(|pair| pair[0].name < pair[1].name),
        "APK complete sorted original comparison differs from the bounded legacy set")
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Begin {
    schema: String,
    main: RuntimeMainCustody,
    application: ApplicationInspection,
    scope: Scope,
    deadline_monotonic_ns: u64,
}
impl Begin {
    pub(crate) fn from_owned(main: &RuntimeMainCustody, application: &ApplicationInspection, scope: Scope, end: Instant)
        -> Result<Self, String>
    {
        let value = Self { schema: SCHEMA.into(), main: main.clone(), application: application.clone(), scope,
            deadline_monotonic_ns: absolute(end)? };
        value.validate()?;
        Ok(value)
    }
    pub(crate) fn validate(&self) -> Result<(), String> {
        self.scope.validate()?;
        need(self.schema == SCHEMA && self.application.user == 0 && self.application.uid < 100_000
            && self.application.version_code > 0 && self.main.epoch == self.application.epoch
            && self.application.package == self.scope.subject_package()
            && (self.scope.is_preparation() || crate::engine_custody::selected_package(&self.application.package)),
            "APK session subject/schema/epoch differs")?;
        self.main.validate(&self.application.epoch)?;
        validate_apks(&self.application.apks)?;
        self.deadline().map(|_| ())
    }
    pub(crate) fn scope(&self) -> Scope { self.scope }
    pub(crate) fn main(&self) -> &RuntimeMainCustody { &self.main }
    pub(crate) fn application(&self) -> &ApplicationInspection { &self.application }
    pub(crate) fn deadline(&self) -> Result<Instant, String> { deadline(self.deadline_monotonic_ns) }
    pub(crate) fn deadline_ns(&self) -> u64 { self.deadline_monotonic_ns }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub(crate) enum PackageReadKind { Identity, Paths, Launcher }
impl PackageReadKind {
    pub(crate) fn from_opcode(opcode:u8)->Option<Self>{
        match opcode {b'I'=>Some(Self::Identity),b'P'=>Some(Self::Paths),b'L'=>Some(Self::Launcher),_=>None}
    }
    /// The private leaf child supplies only I/P/L and an optional bounded
    /// ordinal. Package/path/UID/argv never cross this interface.
    pub(crate) fn request(bytes:&[u8])->Result<(Self,u8),String>{
        need(bytes.len()==1 || bytes.len()==2,"APK PM private request has extra or missing bytes")?;
        let kind=Self::from_opcode(bytes[0]).ok_or("APK PM private opcode is not I/P/L")?;
        let ordinal=if bytes.len()==1{0}else{bytes[1]};
        need(ordinal<3,"APK PM private ordinal is outside the fixed maximum")?;
        Ok((kind,ordinal))
    }
    pub(crate) fn require_role(scope:Scope,ordinal:u8)->Result<(),String>{
        need((ordinal as usize)<scope.roles().len()
            && (!scope.is_preparation() || ordinal==0),
            "APK PM ordinal does not belong to this source-owned slot")
    }
    /// Fixed comparison literals for the original source role roster. This is
    /// not a GatewayRequest: public UI admission retains its selected39 gate.
    pub(crate) fn literal_arguments(self,package:&str)->Result<Vec<String>,String>{
        need(super::apk_scope::known_package(package),
            "APK PM package is outside the fixed original role roster")?;
        let values=match self{
            Self::Identity=>vec!["/system/bin/cmd","package","list","packages","-U",
                "--show-versioncode","--user","0",package],
            Self::Paths=>vec!["/system/bin/cmd","package","path","--user","0",package],
            Self::Launcher=>vec!["/system/bin/cmd","package","resolve-activity","--brief",
                "--user","0","-a","android.intent.action.MAIN","-c",
                "android.intent.category.LAUNCHER",package],
        };
        Ok(values.into_iter().map(str::to_owned).collect())
    }
}
pub(crate) const PACKAGE_READ_CAP:Duration=Duration::from_secs(15);

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case",deny_unknown_fields)]
pub(crate) enum Operation {
    NextCopy, Guard, Refresh, Finish,
    PackageRead {kind:PackageReadKind,ordinal:u8,deadline_ns:u64},
}
impl Operation {
    pub(crate) fn package_end(self)->Result<Option<Instant>,String>{
        if let Self::PackageRead{ordinal,deadline_ns,..}=self{
            need(ordinal<3,"APK PM ordinal is outside the closed role group")?;
            let end=deadline(deadline_ns)?;
            need(end.saturating_duration_since(Instant::now())<=PACKAGE_READ_CAP,
                "APK fixed PM command exceeds its original 15-second cap")?;
            Ok(Some(end))
        }else{Ok(None)}
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub(crate) enum Request {
    Begin { nonce: [u8; 16], begin: Begin },
    Continue { nonce: [u8; 16], sequence: u32, operation: Operation },
}
impl Request {
    pub(crate) fn parse(bytes: &[u8]) -> Result<Self, String> {
        need(!bytes.is_empty() && bytes.len() <= MAX_FRAME, "APK frame bound")?;
        let value = crate::native_application_ui_protocol::strict_json(bytes, false).map_err(|e| e.to_string())?;
        let parsed: Self = serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
        need(serde_json::to_value(&parsed).map_err(|e| e.to_string())? == value, "APK noncanonical or unknown field")?;
        match &parsed {
            Self::Begin { nonce, begin } => {
                need(*nonce != [0; 16], "APK empty nonce")?;
                begin.validate()?;
            }
            Self::Continue { nonce, sequence, operation } => {
                need(*nonce != [0; 16] && *sequence > 0 && *sequence <= MAX_REQUESTS, "APK sequence/nonce")?;
                operation.package_end()?;
            }
        }
        Ok(parsed)
    }
    pub(crate) fn bytes(&self) -> Result<Vec<u8>, String> {
        let bytes = serde_json::to_vec(self).map_err(|e| e.to_string())?;
        let parsed = Self::parse(&bytes)?;
        need(parsed == *self, "APK serialization differs")?;
        Ok(bytes)
    }
}

/// Complete held-file metadata, including nanosecond ctime. Original and copy
/// records are separate fields, never interchangeable inode projections.
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct FileIdentity {
    pub(crate) dev: u64,
    pub(crate) ino: u64,
    pub(crate) mode: u32,
    pub(crate) uid: u32,
    pub(crate) gid: u32,
    pub(crate) nlink: u64,
    pub(crate) bytes: u64,
    pub(crate) mtime: i64,
    pub(crate) mtime_nsec: i64,
    pub(crate) ctime: i64,
    pub(crate) ctime_nsec: i64,
}
impl FileIdentity {
    pub(crate) fn of(m: &Metadata) -> Self {
        Self { dev:m.dev(), ino:m.ino(), mode:m.mode(), uid:m.uid(), gid:m.gid(), nlink:m.nlink(),
            bytes:m.len(), mtime:m.mtime(), mtime_nsec:m.mtime_nsec(), ctime:m.ctime(), ctime_nsec:m.ctime_nsec() }
    }
    pub(crate) fn original(&self, expected_bytes: u64) -> Result<(), String> {
        need(self.ino != 0 && self.mode & libc::S_IFMT == libc::S_IFREG && self.nlink == 1
            && self.mode & 0o6022 == 0 && self.bytes == expected_bytes && self.bytes > 0
            && self.bytes <= MAX_APK_BYTES && (0..1_000_000_000).contains(&self.mtime_nsec)
            && (0..1_000_000_000).contains(&self.ctime_nsec), "APK original inode identity differs")
    }
    pub(crate) fn copy(&self, expected_bytes: u64) -> Result<(), String> {
        need(self.ino != 0 && self.mode & libc::S_IFMT == libc::S_IFREG && self.nlink == 0
            && self.mode & 0o7777 == 0o400 && self.uid == 0 && self.gid == 0
            && self.bytes == expected_bytes && self.bytes > 0 && self.bytes <= MAX_APK_BYTES,
            "APK sealed copy identity differs")
    }
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Original {
    pub(crate) package: String,
    pub(crate) apk: InstalledApk,
    pub(crate) identity: FileIdentity,
    pub(crate) selinux: String,
}
impl Original {
    pub(crate) fn validate(&self) -> Result<(), String> {
        self.identity.original(self.apk.bytes)?;
        need(!self.package.is_empty() && self.package.len() <= 255 && self.selinux.len() <= 256 && self.selinux.starts_with("u:object_r:")
            && self.selinux.bytes().all(|b| b.is_ascii_alphanumeric() || b"_:,.-".contains(&b)),
            "APK original SELinux identity differs")
    }
}
#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Copy {
    pub(crate) ordinal: u32,
    pub(crate) original: Original,
    pub(crate) sealed_copy: FileIdentity,
    pub(crate) sealed_copy_sha256: String,
    pub(crate) seals: i32,
}
impl Copy {
    pub(crate) fn validate(&self) -> Result<(), String> {
        self.original.validate()?;
        self.sealed_copy.copy(self.original.apk.bytes)?;
        need(self.ordinal < MAX_GROUP_APKS as u32 && self.sealed_copy_sha256 == self.original.apk.sha256
            && sha256(&self.sealed_copy_sha256)
            && (self.original.identity.dev, self.original.identity.ino) != (self.sealed_copy.dev, self.sealed_copy.ino)
            && self.seals == (libc::F_SEAL_SEAL | libc::F_SEAL_SHRINK | libc::F_SEAL_GROW | libc::F_SEAL_WRITE),
            "APK original/copy provenance differs")
    }
}

/// Source-only ordering. This cannot create a custody observation or retire a
/// process. The owner advances it only after actual child and peer operations.
pub(crate) struct Sequence {
    nonce: [u8; 16],
    next: u32,
    copies: usize,
    copied: usize,
    failed: bool,
    finished: bool,
}
impl Sequence {
    pub(crate) fn begin(nonce: [u8; 16], copies: usize) -> Result<Self, String> {
        need(nonce != [0; 16] && (1..=MAX_GROUP_APKS).contains(&copies), "APK initial sequence")?;
        Ok(Self { nonce, next:1, copies, copied:0, failed:false, finished:false })
    }
    pub(crate) fn accept(&mut self, nonce:[u8;16], number:u32, operation:Operation) -> Result<Option<usize>, String> {
        let allowed = !self.failed && !self.finished && nonce == self.nonce && number == self.next
            && number <= MAX_REQUESTS && match operation {
                Operation::NextCopy => self.copied < self.copies,
                Operation::PackageRead {ordinal,..} => ordinal<3,
                Operation::Guard | Operation::Refresh | Operation::Finish => self.copied == 0 || self.copied == self.copies,
            };
        if !allowed { self.failed=true; return Err("APK phase, replay or sequence differs".into()); }
        self.next += 1;
        match operation {
            Operation::NextCopy => { let index=self.copied; self.copied+=1; Ok(Some(index)) }
            Operation::Finish => { self.finished=true; Ok(None) }
            _ => Ok(None),
        }
    }
    pub(crate) fn fail(&mut self) { self.failed=true; }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_leaf_apk_sequence_never_accepts_replay_or_missing_copy() {
        let mut state=Sequence::begin([7;16],2).unwrap();
        assert_eq!(state.accept([7;16],1,Operation::NextCopy).unwrap(),Some(0));
        assert_eq!(state.accept([7;16],2,Operation::NextCopy).unwrap(),Some(1));
        assert!(state.accept([7;16],3,Operation::Guard).is_ok());
        assert!(state.accept([7;16],3,Operation::Guard).is_err());
        assert!(state.accept([7;16],4,Operation::Finish).is_err());
        let mut partial=Sequence::begin([8;16],2).unwrap();
        partial.accept([8;16],1,Operation::NextCopy).unwrap();
        assert!(partial.accept([8;16],2,Operation::Finish).is_err());
        let mut original_only=Sequence::begin([9;16],2).unwrap();
        assert!(original_only.accept([9;16],1,Operation::Guard).is_ok());
        assert!(original_only.accept([9;16],2,Operation::Finish).is_ok());
    }
    #[test]
    fn native_leaf_apk_package_read_keeps_fixed_role_and_private_byte_shape(){
        use super::super::apk_scope::{NativeLeafApkRoute as R,NativeLeafPreparationMember as M,
            NativeLeafPreparationRole};
        for (byte,kind) in [(b'I',PackageReadKind::Identity),(b'P',PackageReadKind::Paths),
            (b'L',PackageReadKind::Launcher)]{
            assert_eq!(PackageReadKind::request(&[byte]).unwrap(),(kind,0));
            assert_eq!(PackageReadKind::request(&[byte,2]).unwrap(),(kind,2));
            assert!(PackageReadKind::request(&[byte,3]).is_err());
            assert!(PackageReadKind::request(&[byte,0,0]).is_err());
        }
        for bytes in [b"".as_slice(),b"G",b"E",b"C",b"Ipackage"]{
            assert!(PackageReadKind::request(bytes).is_err());
        }
        let contacts=Scope::Business{route:R::ContactsSearch};
        assert!(PackageReadKind::require_role(contacts,2).is_ok());
        assert!(PackageReadKind::require_role(Scope::Business{route:R::ClockPair},2).is_err());
        let role=NativeLeafPreparationRole::for_case(R::ContactsSearch,M::Provider).unwrap();
        let preparation=Scope::preparation(role);
        assert!(PackageReadKind::require_role(preparation,0).is_ok());
        assert!(PackageReadKind::require_role(preparation,1).is_err());
        assert_eq!(preparation.subject_package(),"com.android.providers.contacts");
        assert_ne!(preparation.subject_package(),contacts.subject_package());
    }
    #[test]
    fn native_leaf_apk_package_read_rejects_cross_slot_replay_and_new_deadline(){
        let operation=Operation::PackageRead{kind:PackageReadKind::Identity,ordinal:0,
            deadline_ns:absolute(Instant::now()+Duration::from_secs(5)).unwrap()};
        assert!(operation.package_end().unwrap().is_some());
        let mut state=Sequence::begin([1;16],2).unwrap();
        assert!(state.accept([2;16],1,operation).is_err());
        assert!(state.accept([1;16],1,operation).is_err());
        let mut partial=Sequence::begin([3;16],2).unwrap();
        partial.accept([3;16],1,Operation::NextCopy).unwrap();
        assert!(partial.accept([3;16],2,operation).is_ok());
        assert!(partial.accept([3;16],2,operation).is_err());
        assert!(partial.accept([3;16],3,Operation::NextCopy).is_err());
        let late=Operation::PackageRead{kind:PackageReadKind::Paths,ordinal:0,
            deadline_ns:absolute(Instant::now()+Duration::from_secs(16)).unwrap()};
        assert!(late.package_end().is_err());
        let expired=Operation::PackageRead{kind:PackageReadKind::Launcher,ordinal:0,deadline_ns:1};
        assert!(expired.package_end().is_err());
        let raw=br#"{"kind":"continue","nonce":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],"sequence":1,"operation":{"package_read":{"kind":"identity","ordinal":0,"ordinal":1,"deadline_ns":1}}}"#;
        assert!(Request::parse(raw).is_err());
    }
    #[test]
    fn native_leaf_apk_comparison_keeps_legacy_byte_and_path_bounds() {
        let mut apk=InstalledApk{name:"base.apk".into(),path:"/data/app/example/base.apk".into(),
            bytes:MAX_APK_BYTES,sha256:"1".repeat(64)};
        assert!(validate_apks(&[apk.clone()]).is_ok());
        apk.bytes+=1;
        assert!(validate_apks(&[apk.clone()]).is_err());
        apk.bytes=4;apk.path="/data/user/0/example/private.apk".into();
        assert!(validate_apks(&[apk.clone()]).is_err());
        apk.path="/data/app/../base.apk".into();
        assert!(validate_apks(&[apk]).is_err());
        assert!(Request::parse(br#"{"kind":"continue","nonce":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1],"sequence":1,"sequence":2,"operation":"guard"}"#).is_err());
    }
}

#[derive(Clone,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct RetiredComparison {
    pub(crate) pid:u32,
    pub(crate) pidfd_device:u64,
    pub(crate) pidfd_inode:u64,
    pub(crate) waitid_code:i32,
    pub(crate) waitid_status:i32,
}
impl RetiredComparison {
    pub(crate) fn validate(&self)->Result<(),String>{
        need(self.pid>1 && self.pidfd_inode!=0 && self.waitid_code==libc::CLD_EXITED
            && self.waitid_status==0,"APK actual reader retirement differs")
    }
}
#[derive(Debug,Serialize,Deserialize)]
#[serde(tag="kind",rename_all="snake_case",deny_unknown_fields)]
pub(crate) enum Response {
    Begun {nonce:[u8;16],begin:Begin,packages:Vec<PackageFiles>,bookends:Vec<Bookend>},
    Copied {nonce:[u8;16],sequence:u32,comparison:Copy},
    Guarded {nonce:[u8;16],sequence:u32,full_hash:bool},
    PackageRead {nonce:[u8;16],sequence:u32,comparison:PackageReadComparison},
    Finished {nonce:[u8;16],sequence:u32,bookends:Vec<Bookend>,retirement:RetiredComparison},
}
impl Response {
    pub(crate) fn bytes(&self)->Result<Vec<u8>,String>{
        let value=serde_json::to_vec(self).map_err(|e|e.to_string())?;
        need(!value.is_empty() && value.len()<=MAX_FRAME,"APK response frame bound")?;
        Ok(value)
    }
    pub(crate) fn parse(raw:&[u8])->Result<Self,String>{
        need(!raw.is_empty() && raw.len()<=MAX_FRAME,"APK response bound")?;
        let value=crate::native_application_ui_protocol::strict_json(raw,false).map_err(|e|e.to_string())?;
        let parsed:Self=serde_json::from_value(value.clone()).map_err(|e|e.to_string())?;
        need(serde_json::to_value(&parsed).map_err(|e|e.to_string())?==value,"APK response unknown fields")?;
        Ok(parsed)
    }
}

#[derive(Clone,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct MetadataRead {
    pub(crate) stdout:String,
    pub(crate) receipt:serde_json::Value,
}
/// The two metadata bookends retain the original ApplicationRead argument
/// order and 30-second normal Query cap. Legacy I/P/L has its separate exact
/// literals and 15-second cap; these comparison forms are not interchangeable.
pub(crate) fn metadata_arguments(package:&str,paths:bool)->Result<Vec<String>,String>{
    need(super::apk_scope::known_package(package),"APK metadata package is outside its fixed roles")?;
    let value=if paths{super::ApplicationRead::PackagePaths{package:package.into(),user:0}}
        else{super::ApplicationRead::PackageIdentity{package:package.into(),user:0}};
    value.arguments().map_err(|e|e.to_string())?.into_iter()
        .map(|value|value.into_string().map_err(|e|e.to_string())).collect()
}

/// Reparse the two actual complete PM outputs for comparison. This value
/// cannot construct an Inspector or reader; only authenticated transport can.
pub(crate) fn compare_metadata_reads(reads:&[MetadataRead],expected:&ApplicationMetadata)
    ->Result<ApplicationMetadata,String>
{
    need(reads.len()==2,"APK owner requires two actual retired PM reads")?;
    for (index,read) in reads.iter().enumerate() {
        crate::native_application_ui_gateway::validate_apk_metadata_read(
            &read.receipt,read.stdout.as_bytes(),&expected.package,index==1)?;
    }
    struct Compared<'a>{reads:&'a[MetadataRead],expected:&'a ApplicationMetadata,next:usize}
    impl crate::control::application_probe::AndroidProbe for Compared<'_>{
        fn epoch(&mut self)->Result<crate::control::application_probe::RuntimeEpoch,String>{
            Ok(self.expected.epoch.clone())
        }
        fn command(&mut self,args:&[String])->Result<String,String>{
            need(self.next<2,"APK compared PM command count")?;
            need(args==metadata_arguments(&self.expected.package,self.next==1)?,
                "APK compared PM argv differs")?;
            let raw=self.reads[self.next].stdout.clone();self.next+=1;Ok(raw)
        }
    }
    let mut probe=Compared{reads,expected,next:0};
    let value=crate::control::application_probe::inspect_metadata(&mut probe,&expected.package,0)?;
    need(probe.next==2 && value==*expected,"APK complete metadata comparison differs")?;
    Ok(value)
}

#[derive(Clone,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PackageFiles {
    pub(crate) application: ApplicationInspection,
    pub(crate) originals: Vec<Original>,
}
#[derive(Debug,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Bookend {
    pub(crate) main: RuntimeMainCustody,
    pub(crate) metadata: ApplicationMetadata,
    pub(crate) reads: Vec<MetadataRead>,
}

/// These functions validate comparison records only. They cannot create a
/// live reader, peer, ActualApplicationObservation, or finished custody token.
pub(crate) fn validate_packages(begin:&Begin, packages:&[PackageFiles])->Result<(),String> {
    let roles=begin.scope().roles();
    need(packages.len()==roles.len(),"APK group omitted or added a fixed source role")?;
    let mut paths=BTreeSet::new();
    let mut count=0_usize;
    let mut total=0_u64;
    for (index,(package,role)) in packages.iter().zip(roles).enumerate() {
        let app=&package.application;
        validate_apks(&app.apks)?;
        let bytes=app.apks.iter().try_fold(0_u64,|sum,apk|sum.checked_add(apk.bytes))
            .ok_or("APK source role bytes overflow")?;
        need(app.package==role.package && app.user==0 && app.uid<100_000
            && app.version_code>0 && app.epoch==begin.main().epoch
            && app.apks.len()<=role.max_apks && bytes<=role.max_bytes
            && package.originals.len()==app.apks.len(),"APK role subject or bound differs")?;
        if index==0 {need(app==begin.application(),"APK primary whole observed PM differs")?;}
        for (original,apk) in package.originals.iter().zip(&app.apks) {
            original.validate()?;
            need(original.package==app.package && original.apk==*apk && paths.insert(apk.path.clone()),
                "APK original role, inode comparison or duplicate path differs")?;
            count+=1;
        }
        total=total.checked_add(bytes).ok_or("APK group bytes overflow")?;
    }
    need(count<=MAX_GROUP_APKS && total<=MAX_GROUP_BYTES,"APK fixed group complete bound exceeded")
}
pub(crate) fn validate_bookends(begin:&Begin,packages:&[PackageFiles],bookends:&[Bookend])->Result<(),String>{
    validate_packages(begin,packages)?;
    need(bookends.len()==packages.len(),"APK group lacks an actual PM/Main bookend")?;
    for (package,bookend) in packages.iter().zip(bookends) {
        need(bookend.main==*begin.main() && bookend.metadata.matches_inspection(&package.application),
            "APK group actual Main/complete PM differs")?;
        need(compare_metadata_reads(&bookend.reads,&bookend.metadata)?==bookend.metadata,
            "APK group raw normal PM receipts differ")?;
    }
    Ok(())
}


/// A strict comparison of one actual retired query in the already-held role
/// group. Deserializing this record cannot create the original observation.
#[derive(Clone,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct PackageReadComparison {
    pub(crate) schema:String,
    pub(crate) kind:PackageReadKind,
    pub(crate) ordinal:u8,
    pub(crate) main_before:RuntimeMainCustody,
    pub(crate) main_after:RuntimeMainCustody,
    pub(crate) application:ApplicationInspection,
    pub(crate) stdout_base64:String,
    pub(crate) stderr_base64:String,
    pub(crate) stderr_bytes:usize,
    pub(crate) stderr_sha256:String,
    pub(crate) receipt:serde_json::Value,
}
impl PackageReadComparison {
    pub(crate) fn output_for(&self,begin:&Begin,packages:&[PackageFiles],kind:PackageReadKind,ordinal:u8)
        ->Result<std::process::Output,String>
    {
        validate_packages(begin,packages)?;
        let expected=packages.get(ordinal as usize).ok_or("APK PM role ordinal is absent")?;
        need(self.schema=="droidloom.native-leaf-package-read.v2" && self.kind==kind
            && self.ordinal==ordinal && self.main_before==*begin.main()
            && self.main_after==*begin.main() && self.application==expected.application,
            "APK PM response differs from the original slot, whole Main or actual role")?;
        let stdout=crate::native_application_ui_protocol::decode64_bounded(
            &self.stdout_base64,65_536,true,false).map_err(|e|e.to_string())?;
        let stderr=crate::native_application_ui_protocol::decode64_bounded(
            &self.stderr_base64,65_536,true,false).map_err(|e|e.to_string())?;
        use sha2::{Digest,Sha256};
        need(self.stderr_bytes==stderr.len()
            && self.stderr_sha256==format!("{:x}",Sha256::digest(&stderr)),
            "APK PM complete actual stderr differs")?;
        crate::native_application_ui_gateway::fixed_apk_package_output(
            &self.receipt,stdout,stderr,&self.application.package,kind)
    }
}
