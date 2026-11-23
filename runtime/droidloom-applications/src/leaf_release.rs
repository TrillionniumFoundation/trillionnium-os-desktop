//! Root-adopted pairing of the compiled source catalog and the actual CLI OFD.
//!
//! The compiled catalog/selector remain the source trust anchor. This detached
//! record removes the source-preparation -> executable -> source hash cycle;
//! it grants no runtime or whole-application qualification. Its preimage is an
//! actual preserved whole CURRENT, not a postimage with a field removed.
use std::collections::BTreeMap;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{FileExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use droidloom_supervisor::control::NativeApplicationSourceLocks;
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

use super::FilePin;

pub(super) const CURRENT: &str = "/home/alex/work/pocket4-android-final/CONTINUATION_CURRENT.json";
pub(super) const ROOT: &str = "/etc/droidloom/native-application-leaves";
pub(super) const CLI: &str = "/usr/bin/droidloom-applications";
pub(super) const PROTOCOL: &str = "droidloom-gallery-image-custody-v1";
// Linux O_NOFOLLOW/O_DIRECTORY. OpenOptions sets O_CLOEXEC itself. Keeping
// safe std APIs preserves this crate's forbid(unsafe_code) and Rust 1.85 MSRV.
const NOFOLLOW: i32 = 0x20000;
const DIRECTORY: i32 = 0x10000;

fn require(ok: bool, why: &str) -> Result<(), String> {
    if ok { Ok(()) } else { Err(why.into()) }
}

fn now() -> Result<u64, String> {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|x| x.as_secs()).map_err(|e| e.to_string())
}

fn hex(value: &str, length: usize) -> bool {
    value.len() == length && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

fn pin(value: &FilePin, maximum: u64) -> Result<(), String> {
    let path = value.path.to_str().ok_or("release path is not UTF-8")?;
    require(path.starts_with('/') && !path.contains('\0')
        && path[1..].split('/').all(|part| !part.is_empty() && part != "." && part != "..")
        && value.bytes > 0 && value.bytes <= maximum && hex(&value.sha256, 64),
        "bounded exact release file pin required")
}

/// serde_json::Value otherwise accepts duplicate object keys. Reject them at
/// every level before either typed manifests or whole CURRENT are compared.
struct UniqueValue(Value);
impl<'de> Deserialize<'de> for UniqueValue {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = UniqueValue;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result { f.write_str("JSON with unique object keys") }
            fn visit_bool<E: de::Error>(self, v: bool) -> Result<Self::Value,E> { Ok(UniqueValue(Value::Bool(v))) }
            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Self::Value,E> { Ok(UniqueValue(Value::Number(v.into()))) }
            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Self::Value,E> { Ok(UniqueValue(Value::Number(v.into()))) }
            fn visit_f64<E: de::Error>(self, v: f64) -> Result<Self::Value,E> {
                serde_json::Number::from_f64(v).map(|n| UniqueValue(Value::Number(n)))
                    .ok_or_else(|| E::custom("nonfinite release JSON number"))
            }
            fn visit_str<E: de::Error>(self, v: &str) -> Result<Self::Value,E> { Ok(UniqueValue(Value::String(v.into()))) }
            fn visit_string<E: de::Error>(self, v: String) -> Result<Self::Value,E> { Ok(UniqueValue(Value::String(v))) }
            fn visit_none<E: de::Error>(self) -> Result<Self::Value,E> { Ok(UniqueValue(Value::Null)) }
            fn visit_unit<E: de::Error>(self) -> Result<Self::Value,E> { Ok(UniqueValue(Value::Null)) }
            fn visit_seq<A: SeqAccess<'de>>(self, mut sequence: A) -> Result<Self::Value,A::Error> {
                let mut values=Vec::new(); while let Some(UniqueValue(v))=sequence.next_element()? { values.push(v); }
                Ok(UniqueValue(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value,A::Error> {
                let mut values=serde_json::Map::new();
                while let Some(key)=map.next_key::<String>()? {
                    if values.contains_key(&key) { return Err(de::Error::custom("duplicate release JSON key")); }
                    let UniqueValue(v)=map.next_value()?; values.insert(key,v);
                }
                Ok(UniqueValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(V)
    }
}

pub(super) fn json(raw: &[u8]) -> Result<Value, String> {
    serde_json::from_slice::<UniqueValue>(raw).map(|v| v.0).map_err(|e| e.to_string())
}

#[derive(Clone, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(deny_unknown_fields)]
pub(super) struct Owner {
    acquisition: String,
    acquisition_id: String,
    active_until_utc: String,
    generation: String,
    name: String,
    scope: String,
}

fn utc_seconds(value: &str) -> Result<u64,String> {
    let raw = value.as_bytes();
    require((raw.len()==20 && raw[19]==b'Z') || (raw.len()==25 && &raw[19..]==b"+00:00"), "exact UTC owner expiry required")?;
    require(raw[4]==b'-' && raw[7]==b'-' && raw[10]==b'T' && raw[13]==b':' && raw[16]==b':', "owner expiry punctuation differs")?;
    let number = |start: usize,end: usize| -> Result<u64,String> {
        require(raw[start..end].iter().all(u8::is_ascii_digit), "numeric UTC owner expiry required")?;
        value[start..end].parse().map_err(|_| "invalid UTC component".into())
    };
    let (year,month,day,hour,minute,second)=(number(0,4)?,number(5,7)?,number(8,10)?,number(11,13)?,number(14,16)?,number(17,19)?);
    require((1970..=9999).contains(&year) && (1..=12).contains(&month) && hour<24 && minute<60 && second<60, "bounded UTC owner expiry required")?;
    let leap = year%4==0 && (year%100!=0 || year%400==0);
    let months=[31,if leap {29} else {28},31,30,31,30,31,31,30,31,30,31];
    require(day>0 && day<=months[(month-1) as usize], "real calendar owner expiry required")?;
    let before = year-1;
    let days=(year-1970)*365 + before/4-1969/4 - (before/100-1969/100) + before/400-1969/400
        + months[..(month-1) as usize].iter().sum::<u64>() + day-1;
    Ok(days*86400 + hour*3600 + minute*60 + second)
}

impl Owner {
    pub(super) fn expiry(&self) -> Result<u64,String> {
        require([&self.acquisition,&self.acquisition_id,&self.active_until_utc,&self.generation,&self.name,&self.scope]
            .iter().all(|value| !value.is_empty() && value.len()<=4096), "bounded six-field foreground owner required")?;
        require([&self.acquisition_id,&self.generation,&self.name].iter().all(|value|
            value.len()<=256 && value.bytes().all(|c| c.is_ascii_alphanumeric() || b"_.-".contains(&c))),
            "exact owner generation and acquisition names required")?;
        utc_seconds(&self.active_until_utc)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Preimage {
    pub path: PathBuf,
    pub bytes: u64,
    pub sha256: String,
    pub f9: [u64;9],
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Manifest {
    pub schema: String,
    pub protocol: String,
    pub binary: FilePin,
    pub selection: FilePin,
    pub catalog: FilePin,
    pub foreground_owner: Owner,
    pub owner_expires_unix_seconds: u64,
    pub before_current: Preimage,
    pub before_current_copy: FilePin,
    pub source_tree: String,
    pub ci_commit: String,
    pub ci_run_id: u64,
    pub runtime_qualified: bool,
    pub production_ready: bool,
}

impl Manifest {
    pub(super) fn validate(&self) -> Result<(),String> {
        require(self.schema=="pocket4-native-application-leaf-release-v1" && self.protocol==PROTOCOL
            && !self.runtime_qualified && !self.production_ready, "source/binary release pairing grants no runtime acceptance")?;
        pin(&self.binary,64*1024*1024)?; pin(&self.selection,1024*1024)?;
        pin(&self.catalog,65536)?; pin(&self.before_current_copy,2*1024*1024)?;
        require(self.binary.path==Path::new(CLI)
            && self.catalog.path==PathBuf::from(format!("{ROOT}/catalogs/{}.json",self.catalog.sha256))
            && self.before_current_copy.path==PathBuf::from(format!("{ROOT}/current-preimages/{}.json",self.before_current_copy.sha256)),
            "only canonical binary and root-owned content-addressed release inputs allowed")?;
        require(self.before_current.path.to_str()==Some(CURRENT)
            && self.before_current.f9[2..6]==[0o100600,1000,1000,1]
            && self.before_current.f9[6]==self.before_current.bytes
            && self.before_current.bytes==self.before_current_copy.bytes
            && self.before_current.sha256==self.before_current_copy.sha256,
            "actual full pre-CAS CURRENT copy must preserve its original identity")?;
        require(self.foreground_owner.expiry()?==self.owner_expires_unix_seconds
            && hex(&self.source_tree,40) && hex(&self.ci_commit,40) && self.ci_run_id>0,
            "typed source build and original UTC owner window required")
    }
}

pub(super) fn f9(meta: &fs::Metadata) -> Result<[u64;9],String> {
    let ns=|seconds:i64,nanos:i64| u64::try_from(i128::from(seconds)*1_000_000_000+i128::from(nanos))
        .map_err(|_| "negative input timestamp".to_string());
    Ok([meta.dev(),meta.ino(),u64::from(meta.mode()),u64::from(meta.uid()),u64::from(meta.gid()),
        meta.nlink(),meta.len(),ns(meta.mtime(),meta.mtime_nsec())?,ns(meta.ctime(),meta.ctime_nsec())?])
}

pub(super) fn body(file: &File, size:u64) -> Result<Vec<u8>,String> {
    let mut raw=vec![0;usize::try_from(size).map_err(|e|e.to_string())?];
    let mut offset=0;
    while offset<raw.len() {
        let count=file.read_at(&mut raw[offset..],offset as u64).map_err(|e|e.to_string())?;
        require(count>0,"short held release file")?; offset+=count;
    }
    require(file.read_at(&mut [0_u8;1],size).map_err(|e|e.to_string())?==0,"long held release file")?;
    Ok(raw)
}

struct DirectoryPin { path: PathBuf, file: File, identity: [u64;6], root: bool }
struct FileHold { reference: FilePin, file: File, identity: [u64;9] }

pub(super) struct Inputs { directories:BTreeMap<PathBuf,DirectoryPin>, files:Vec<FileHold> }
impl Inputs {
    pub(super) fn new() -> Self { Self {directories:BTreeMap::new(),files:Vec::new()} }
    pub(super) fn anchored(&self,path:&Path) -> Result<PathBuf,String> {
        if path==Path::new("/") { return Ok(path.into()); }
        let parent=self.directories.get(path.parent().ok_or("input parent absent")?)
            .ok_or("input parent OFD not held")?;
        // The kernel's own FD path provides openat semantics through safe std
        // APIs. Every user-controlled component was separately opened with
        // O_NOFOLLOW; the final child is also O_NOFOLLOW and compared by F9.
        Ok(PathBuf::from(format!("/proc/self/fd/{}",parent.file.as_raw_fd()))
            .join(path.file_name().ok_or("input name absent")?))
    }

    pub(super) fn sync_parent(&self,path:&Path) -> Result<(),String> {
        self.directories.get(path.parent().ok_or("input parent absent")?)
            .ok_or("input parent OFD not held")?.file.sync_all().map_err(|e|e.to_string())
    }
    fn directory(&mut self,path:&Path,root:bool) -> Result<(),String> {
        if let Some(held)=self.directories.get_mut(path) {
            if root {
                require(held.identity[3..5]==[0,0] && held.identity[2]&0o022==0,"root-only release parent required")?;
                held.root=true;
            }
            return Ok(());
        }
        if let Some(parent)=path.parent() { self.directory(parent,root)?; }
        let anchored=self.anchored(path)?;
        let file=OpenOptions::new().read(true).custom_flags(NOFOLLOW|DIRECTORY).open(&anchored).map_err(|e|e.to_string())?;
        let identity:[u64;6]=f9(&file.metadata().map_err(|e|e.to_string())?)?[..6].try_into().map_err(|_|"directory identity".to_string())?;
        require(f9(&fs::symlink_metadata(path).map_err(|e|e.to_string())?)?[..6]==identity
            && f9(&fs::symlink_metadata(&anchored).map_err(|e|e.to_string())?)?[..6]==identity
            && identity[2]&0o170000==0o040000,"held no-link directory identity required")?;
        if root { require(identity[3..5]==[0,0] && identity[2]&0o022==0,"root-only release directory required")?; }
        self.directories.insert(path.into(),DirectoryPin {path:path.into(),file,identity,root});
        Ok(())
    }

    pub(super) fn read(&mut self,path:&Path,expected:Option<&FilePin>,maximum:u64,root:bool,executable:bool) -> Result<Vec<u8>,String> {
        require(path.is_absolute() && path.canonicalize().map_err(|e|e.to_string())?==path,"canonical release file required")?;
        if let Some(reference)=expected { pin(reference,maximum)?; require(reference.path==path,"release pin path differs")?; }
        self.directory(path.parent().ok_or("release file has no parent")?,root)?;
        let anchored=self.anchored(path)?;
        let file=OpenOptions::new().read(true).custom_flags(NOFOLLOW).open(&anchored).map_err(|e|e.to_string())?;
        let identity=f9(&file.metadata().map_err(|e|e.to_string())?)?;
        require(identity[2]&0o170000==0o100000 && identity[5]==1 && identity[6]>0 && identity[6]<=maximum,"bounded single-link release file required")?;
        if root { require(identity[3..5]==[0,0] && identity[2]&0o022==0,"root-owned release input required")?; }
        if executable { require(identity[2]&0o111!=0 && identity[2]&0o6000==0,"ordinary installed native CLI required")?; }
        if path==Path::new(CURRENT) { require(identity[2..6]==[0o100600,1000,1000,1],"original CURRENT custody required")?; }
        let raw=body(&file,identity[6])?;
        let reference=FilePin {path:path.into(),bytes:raw.len() as u64,sha256:hex::encode(Sha256::digest(&raw))};
        require(expected.is_none_or(|value| value==&reference),"full held release input differs from its exact pin")?;
        require(f9(&file.metadata().map_err(|e|e.to_string())?)?==identity
            && f9(&fs::symlink_metadata(&anchored).map_err(|e|e.to_string())?)?==identity
            && f9(&fs::symlink_metadata(path).map_err(|e|e.to_string())?)?==identity,"release input changed during admission")?;
        self.files.push(FileHold {reference,file,identity});
        Ok(raw)
    }

    pub(super) fn identity(&self,path:&Path) -> Result<[u64;9],String> {
        self.files.iter().find(|value|value.reference.path==path).map(|value|value.identity).ok_or("file is not held".into())
    }

    pub(super) fn guard(&self) -> Result<(),String> {
        for held in self.directories.values() {
            require(f9(&held.file.metadata().map_err(|e|e.to_string())?)?[..6]==held.identity
                && f9(&fs::symlink_metadata(self.anchored(&held.path)?).map_err(|e|e.to_string())?)?[..6]==held.identity
                && f9(&fs::symlink_metadata(&held.path).map_err(|e|e.to_string())?)?[..6]==held.identity,
                "held release parent replaced or changed")?;
        }
        for held in &self.files {
            require(f9(&held.file.metadata().map_err(|e|e.to_string())?)?==held.identity
                && f9(&fs::symlink_metadata(self.anchored(&held.reference.path)?).map_err(|e|e.to_string())?)?==held.identity
                && f9(&fs::symlink_metadata(&held.reference.path).map_err(|e|e.to_string())?)?==held.identity,
                "held release input replaced or changed")?;
            require(hex::encode(Sha256::digest(body(&held.file,held.identity[6])?))==held.reference.sha256
                && f9(&held.file.metadata().map_err(|e|e.to_string())?)?==held.identity
                && f9(&fs::symlink_metadata(&held.reference.path).map_err(|e|e.to_string())?)?==held.identity,
                "held release input changed during final full-body bookend")?;
        }
        Ok(())
    }
}

fn forward_relation(before:&Value,current:&Value,reference:&FilePin) -> Result<(),String> {
    let mut allowed=before.clone();
    allowed.as_object_mut().ok_or("original CURRENT is not an object")?.insert(
        "native_application_leaf_release".into(),serde_json::to_value(reference).map_err(|e|e.to_string())?);
    // Value equality is type-aware: Boolean true never equals Number 1.
    require(&allowed==current,"CURRENT is not the complete single-field release-adoption successor")
}

pub(super) struct NativeRelease {
    locks:NativeApplicationSourceLocks,
    inputs:Inputs,
    manifest:Manifest,
    self_exe:File,
    self_identity:[u64;9],
    pid:u32,
}

impl NativeRelease {
    pub(super) fn cover_window(&self, seconds: u64) -> Result<(),String> {
        self.guard()?;
        require(self.manifest.owner_expires_unix_seconds>now()?.saturating_add(seconds),
            "original owner window cannot cover the complete owned controller and retirement")
    }

    pub(super) fn bind_current(selection:&FilePin,catalog:&str,preparation:&FilePin,entry:&FilePin) -> Result<Self,String> {
        let _locks=NativeApplicationSourceLocks::acquire().map_err(|e|e.to_string())?;
        let mut discovery=Inputs::new();
        let current=json(&discovery.read(Path::new(CURRENT),None,2*1024*1024,false,false)?)?;
        let reference:FilePin=serde_json::from_value(current.get("native_application_leaf_release")
            .ok_or("canonical native release has not been adopted")?.clone()).map_err(|e|e.to_string())?;
        let result=Self::bind(&reference,selection,catalog,preparation,entry)?;
        discovery.guard()?;
        Ok(result)
    }

    pub(super) fn bind(reference:&FilePin,selection:&FilePin,catalog:&str,preparation:&FilePin,entry:&FilePin) -> Result<Self,String> {
        pin(reference,65536)?;
        require(reference.path==PathBuf::from(format!("{ROOT}/releases/{}.json",reference.sha256)),"only adopted content-addressed root release path allowed")?;
        let locks=NativeApplicationSourceLocks::acquire().map_err(|e|e.to_string())?;
        let mut inputs=Inputs::new();
        let current=json(&inputs.read(Path::new(CURRENT),None,2*1024*1024,false,false)?)?;
        require(current.get("native_application_leaf_release")==Some(&serde_json::to_value(reference).map_err(|e|e.to_string())?),"detached release is not selected by canonical CURRENT")?;
        let manifest:Manifest=serde_json::from_value(json(&inputs.read(&reference.path,Some(reference),65536,true,false)?)?).map_err(|e|e.to_string())?;
        manifest.validate()?;
        require(manifest.owner_expires_unix_seconds>now()?.saturating_add(1530+60),"original owner window must cover the whole leaf and retirement")?;
        let owner=serde_json::to_value(&manifest.foreground_owner).map_err(|e|e.to_string())?;
        require(current.get("foreground_owner")==Some(&owner) && manifest.selection==*selection
            && current.get("application_qualification_preparations")==Some(&serde_json::to_value(selection).map_err(|e|e.to_string())?),"CURRENT owner or compiled source selection differs from release")?;
        let before=json(&inputs.read(&manifest.before_current_copy.path,Some(&manifest.before_current_copy),2*1024*1024,true,false)?)?;
        require(before.get("foreground_owner")==Some(&owner),"preserved original CURRENT owner differs")?;
        forward_relation(&before,&current,reference)?;
        inputs.read(&selection.path,Some(selection),1024*1024,true,false)?;
        let catalog_pin=FilePin {path:PathBuf::from(format!("{ROOT}/catalogs/{}.json",hex::encode(Sha256::digest(catalog)))),
            bytes:catalog.len() as u64,sha256:hex::encode(Sha256::digest(catalog))};
        require(manifest.catalog==catalog_pin,"root release catalog differs from independently compiled source anchor")?;
        require(inputs.read(&catalog_pin.path,Some(&catalog_pin),65536,true,false)?==catalog.as_bytes(),"compiled catalog body differs")?;
        inputs.read(&preparation.path,Some(preparation),1024*1024,true,false)?;
        inputs.read(&entry.path,Some(entry),262144,true,false)?;
        inputs.read(Path::new(CLI),Some(&manifest.binary),64*1024*1024,true,true)?;
        // This deliberate kernel magic-link open captures the running image's
        // actual OFD, not argv[0], current_exe() or a pathname-only assertion.
        let self_exe=File::open("/proc/self/exe").map_err(|e|e.to_string())?;
        let self_identity=f9(&self_exe.metadata().map_err(|e|e.to_string())?)?;
        require(self_identity==inputs.identity(Path::new(CLI))?,"actual /proc/self/exe OFD differs from canonical installed release binary")?;
        let result=Self {locks,inputs,manifest,self_exe,self_identity,pid:std::process::id()};
        result.guard()?; Ok(result)
    }

    pub(super) fn guard(&self) -> Result<(),String> {
        require(self.pid==std::process::id() && self.manifest.owner_expires_unix_seconds>now()?.saturating_add(30),"same-process live native release owner required")?;
        self.locks.validate().map_err(|e|e.to_string())?;
        self.inputs.guard()?;
        let actual=File::open("/proc/self/exe").map_err(|e|e.to_string())?;
        require(f9(&actual.metadata().map_err(|e|e.to_string())?)?==self.self_identity
            && f9(&self.self_exe.metadata().map_err(|e|e.to_string())?)?==self.self_identity
            && hex::encode(Sha256::digest(body(&self.self_exe,self.self_identity[6])?))==self.manifest.binary.sha256
            && f9(&self.self_exe.metadata().map_err(|e|e.to_string())?)?==self.self_identity,
            "actual native executable identity/body changed")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn duplicate_keys_and_nonfinite_numbers_are_rejected_at_every_depth() {
        for raw in [r#"{"x":1,"x":2}"#,r#"{"nested":{"x":1,"x":2}}"#,r#"{"x":NaN}"#,r#"{"x":Infinity}"#] {
            assert!(super::json(raw.as_bytes()).is_err());
        }
        assert_eq!(super::json(br#"{"a":[true,1,null,"x"]}"#).unwrap(),json!({"a":[true,1,null,"x"]}));
    }

    #[test]
    fn whole_current_relation_allows_only_the_explicit_forward_adoption() {
        let before=json!({"arbitrary":1,"nested":{"x":false},"native_application_leaf_release":"old"});
        let reference=FilePin {path:"/fixture/manifest.json".into(),bytes:1,sha256:"a".repeat(64)};
        let mut after=before.clone(); after["native_application_leaf_release"]=json!(reference);
        forward_relation(&before,&after,&reference).unwrap();
        for altered in [json!(true),json!(2),json!(null)] {
            let mut changed=after.clone(); changed["arbitrary"]=altered;
            assert!(forward_relation(&before,&changed,&reference).is_err());
        }
        let mut extra=after.clone(); extra["unrelated"]=json!(false);
        assert!(forward_relation(&before,&extra,&reference).is_err());
    }

    #[test]
    fn owner_expiry_is_an_exact_real_utc_instant() {
        assert_eq!(utc_seconds("2030-01-01T00:00:00Z").unwrap(),1893456000);
        assert_eq!(utc_seconds("2030-01-01T00:00:00+00:00").unwrap(),1893456000);
        assert!(utc_seconds("2028-02-29T00:00:00Z").is_ok());
        for value in ["2030-02-29T00:00:00Z","2030-01-01T01:00:00+01:00","2030-01-01T00:00:60Z",""] {
            assert!(utc_seconds(value).is_err(),"{value}");
        }
    }

    #[test]
    fn pin_numeric_booleans_extra_fields_and_noncanonical_paths_are_rejected() {
        for value in [json!({"path":"/a","bytes":true,"sha256":"a".repeat(64)}),
            json!({"path":"/a","bytes":1,"sha256":"a".repeat(64),"extra":false})] {
            assert!(serde_json::from_value::<FilePin>(value).is_err());
        }
        for path in ["/a//b","/a/../b","/a/./b","relative", "/"] {
            assert!(pin(&FilePin {path:path.into(),bytes:1,sha256:"a".repeat(64)},65536).is_err());
        }
    }

    #[test]
    fn held_parent_prevents_path_rebinding_from_redirecting_mutations() {
        let root=tempfile::tempdir().unwrap();
        let original=root.path().join("parent"); fs::create_dir(&original).unwrap();
        let path=original.join("input.json"); fs::write(&path,b"{}\n").unwrap();
        let reference=FilePin {path:path.clone(),bytes:3,sha256:hex::encode(Sha256::digest(b"{}\n"))};
        let mut held=Inputs::new(); held.read(&path,Some(&reference),64,false,false).unwrap();
        let moved=root.path().join("moved"); fs::rename(&original,&moved).unwrap();
        fs::create_dir(&original).unwrap(); fs::write(&path,b"{}\n").unwrap();
        assert!(held.guard().is_err());
        let intended=original.join("only-owned-new-file");
        let file=OpenOptions::new().write(true).create_new(true).custom_flags(NOFOLLOW)
            .open(held.anchored(&intended).unwrap()).unwrap();
        assert!(moved.join("only-owned-new-file").is_file());
        assert!(!intended.exists());
        drop(file);
    }
}
