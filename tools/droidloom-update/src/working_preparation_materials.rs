//! Five byte-exact public source documents for the normal apps41 application roster.
//! These inputs carry source provenance only. Fresh Main, PM and APK custody
//! remain necessary at preparation and again at physical execution.
use std::{
    fs::{self, File, OpenOptions},
    io::{self, Write},
    os::unix::fs::{DirBuilderExt, FileExt, MetadataExt, OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
};
use serde_json::{Value,json};
use sha2::{Digest,Sha256};

#[path = "working_preparation_apks.rs"]
mod apk_materials;
pub use apk_materials::{WorkingApkMaterials, WorkingApplicationApks, WORKING_APK_ROOT};

pub const INSTALLED_ROOT:&str="/usr/libexec/droidloom/native-application-leaves/materials/apps41";

#[derive(Clone,Copy,Debug,Eq,PartialEq)]
pub enum PreparationMaterial {Selection,SignatureReceipt,ImportReceipt,NormalVerification,GateRegistry}
const MATERIALS:[PreparationMaterial;5]=[
    PreparationMaterial::Selection,PreparationMaterial::SignatureReceipt,
    PreparationMaterial::ImportReceipt,PreparationMaterial::NormalVerification,
    PreparationMaterial::GateRegistry,
];
impl PreparationMaterial {
    pub fn name(self)->&'static str {
        match self {
            Self::Selection=>"SELECTED41.json",
            Self::SignatureReceipt=>"SIGNATURE-HANDOFF.json",
            Self::ImportReceipt=>"IMPORT.json",
            Self::NormalVerification=>"NORMAL-INPUT-VERIFICATION.json",
            Self::GateRegistry=>"APP-RELEASE-GATES.json",
        }
    }
    fn expected(self)->(usize,&'static str) {
        match self {
            Self::Selection=>(592108,"4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0"),
            Self::SignatureReceipt=>(309985,"1d44a6f5cb247de704bd64a0973226612672619545ecd328e4536bdda0236731"),
            Self::ImportReceipt=>(1005,"1f06db0be3a790bad7a4ba61507b06024289b145cfe3de8f27cea3ca890b091d"),
            Self::NormalVerification=>(129848,"26d54f559e30291af178fd113c53761d23b2f1294f134987a82411ba30651cc8"),
            Self::GateRegistry=>(32688,"f99217aa675c23b8cb671e36af7b3c1d8aa068eeba719a4b985f47d1539c5bb5"),
        }
    }
    fn body(self)->&'static [u8] {
        match self {
            Self::Selection=>include_bytes!("../resources/working-preparation/apps41/SELECTED41.json"),
            Self::SignatureReceipt=>include_bytes!("../resources/working-preparation/apps41/SIGNATURE-HANDOFF.json"),
            Self::ImportReceipt=>include_bytes!("../resources/working-preparation/apps41/IMPORT.json"),
            Self::NormalVerification=>include_bytes!("../resources/working-preparation/apps41/NORMAL-INPUT-VERIFICATION.json"),
            Self::GateRegistry=>include_bytes!("../resources/working-preparation/apps41/APP-RELEASE-GATES.json"),
        }
    }
    fn checked(self)->io::Result<&'static [u8]> {
        let body=self.body();let (bytes,digest)=self.expected();
        if body.len()!=bytes || sha(body)!=digest {
            return Err(invalid("normal apps41 source document differs from its fixed whole-byte pin"));
        }
        Ok(body)
    }
    pub fn reference(self)->Value {
        let (bytes,digest)=self.expected();
        json!({"path":format!("{INSTALLED_ROOT}/{}",self.name()),"bytes":bytes,"sha256":digest})
    }
}
fn invalid(s:&str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,s)}
fn sha(b:&[u8])->String {format!("{:x}",Sha256::digest(b))}
fn f9(m:&fs::Metadata)->io::Result<[u64;9]> {
    let ns=|s:i64,n:i64|u64::try_from(i128::from(s)*1_000_000_000+i128::from(n))
        .map_err(|_|invalid("material inode time is out of range"));
    Ok([m.dev(),m.ino(),u64::from(m.mode()),u64::from(m.uid()),u64::from(m.gid()),
        m.nlink(),m.len(),ns(m.mtime(),m.mtime_nsec())?,ns(m.ctime(),m.ctime_nsec())?])
}
fn directory(path:&Path)->io::Result<File> {
    // Ancestor custody needs only held inode metadata. Directory enumeration
    // uses its separate fixed read_dir call, never these O_PATH descriptions.
    OpenOptions::new().read(true).custom_flags(0x200000|0x20000|0x10000|0x80000).open(path)
}
struct Input {kind:PreparationMaterial,file:File,identity:[u64;9]}
/// No Deserialize/Clone. Holds all actual installed normal source files.
pub struct WorkingPreparationMaterials {
    root:PathBuf,
    inputs:Vec<Input>,
    parents:Vec<(PathBuf,File,[u64;5])>,
}
impl WorkingPreparationMaterials {
    pub fn capture()->io::Result<Self> {
        let root=PathBuf::from(INSTALLED_ROOT);
        if root.canonicalize()?!=root {return Err(invalid("normal material path is aliased"));}
        let mut parents=Vec::new();
        for path in root.ancestors() {
            let file=directory(path)?;let identity=f9(&file.metadata()?)?;
            if identity[2]&0o170000!=0o040000 || identity[2]&0o022!=0 || identity[3..5]!=[0,0] {
                return Err(invalid("normal materials need protected root parents"));
            }
            parents.push((path.into(),file,identity[..5].try_into().map_err(|_|invalid("directory identity"))?));
        }
        let mut inputs=Vec::new();
        for kind in MATERIALS {
            kind.checked()?;
            let file=OpenOptions::new().read(true).custom_flags(0x20000|0x80000).open(root.join(kind.name()))?;
            let identity=f9(&file.metadata()?)?;
            if identity[2]!=0o100444 || identity[3..6]!=[0,0,1] || identity[6]!=kind.expected().0 as u64 {
                return Err(invalid("normal material is not its exact installed root read-only inode"));
            }
            inputs.push(Input{kind,file,identity});
        }
        let value=Self{root,inputs,parents};value.guard()?;Ok(value)
    }
    pub fn guard(&self)->io::Result<()> {
        let names=fs::read_dir(&self.root)?.map(|r|r.map(|e|e.file_name()))
            .collect::<io::Result<std::collections::BTreeSet<_>>>()?;
        let expected=MATERIALS.map(|k|std::ffi::OsString::from(k.name())).into_iter().collect();
        if names!=expected {return Err(invalid("normal apps41 material roster differs"));}
        for (path,file,identity) in &self.parents {
            if f9(&file.metadata()?)?[..5]!=*identity
                || f9(&directory(path)?.metadata()?)?[..5]!=*identity {
                return Err(invalid("normal material parent changed"));
            }
        }
        for input in &self.inputs {
            let named=OpenOptions::new().read(true).custom_flags(0x20000|0x80000)
                .open(self.root.join(input.kind.name()))?;
            if f9(&named.metadata()?)?!=input.identity || f9(&input.file.metadata()?)?!=input.identity {
                return Err(invalid("normal material held/named inode changed"));
            }
            let mut raw=vec![0;input.identity[6] as usize];
            input.file.read_exact_at(&mut raw,0)?;
            if raw!=input.kind.checked()? || input.file.read_at(&mut [0],input.identity[6])?!=0
                || f9(&input.file.metadata()?)?!=input.identity || f9(&named.metadata()?)?!=input.identity {
                return Err(invalid("normal material full source bytes changed"));
            }
        }
        Ok(())
    }
    pub fn bytes(&self,kind:PreparationMaterial)->io::Result<&'static [u8]> {
        self.guard()?;kind.checked()
    }
    pub fn reference(&self,kind:PreparationMaterial)->io::Result<Value> {
        self.guard()?;Ok(kind.reference())
    }
}

/// Called by normal host publication while constructing its private stage.
/// It publishes exactly these five public documents, outside the 478 leaf
/// source cohort. Every member must also enter that release's installer roster.
pub fn stage_working_preparation_materials(host_root:&Path)->io::Result<Vec<PathBuf>> {
    let relative=Path::new(INSTALLED_ROOT).strip_prefix("/").map_err(io::Error::other)?;
    let root=host_root.join(relative);
    let mut current=host_root.to_path_buf();
    if !current.is_dir() {return Err(invalid("normal host stage root absent"));}
    for component in relative.components() {
        let std::path::Component::Normal(name)=component else{return Err(invalid("normal material path is not relative"));};
        current.push(name);
        if current.try_exists()? {
            let m=fs::symlink_metadata(&current)?;
            if !m.is_dir() || m.mode()&0o022!=0 {return Err(invalid("normal material stage parent differs"));}
        } else {
            fs::DirBuilder::new().mode(0o755).create(&current)?;
        }
    }
    if fs::read_dir(&root)?.next().is_some() {return Err(invalid("normal material stage must be create-only"));}
    let mut paths=Vec::new();
    for kind in MATERIALS {
        let bytes=kind.checked()?;
        let path=root.join(kind.name());
        let mut out=OpenOptions::new().read(true).write(true).create_new(true).mode(0o600)
            .custom_flags(0x20000|0x80000).open(&path)?;
        out.write_all(bytes)?;out.sync_all()?;
        out.set_permissions(fs::Permissions::from_mode(0o444))?;out.sync_all()?;
        let m=out.metadata()?;let mut actual=vec![0;bytes.len()];
        out.read_exact_at(&mut actual,0)?;
        if actual!=bytes || m.len()!=bytes.len() as u64 || m.mode()&0o7777!=0o444 || m.nlink()!=1 {
            return Err(invalid("normal material stage readback differs"));
        }
        paths.push(relative.join(kind.name()));
    }
    // Staging must flush its newly written directory. This writable build
    // phase owns a distinct read description; runtime ancestor custody is O_PATH.
    OpenOptions::new().read(true).custom_flags(0x20000|0x10000|0x80000)
        .open(&root)?.sync_all()?;
    verify_staged_working_preparation_materials(host_root)?;
    Ok(paths)
}
/// Exact installed normal source roster, checked before and after normal tar
/// creation and again by the real runtime holder. Build stages retain the
/// ordinary compiler user; the normal archive/install owns the root transition.
pub(crate) fn verify_staged_working_preparation_materials(host_root:&Path)->io::Result<()> {
    let root=host_root.join(INSTALLED_ROOT.trim_start_matches('/'));
    let names=fs::read_dir(&root)?.map(|r|r.map(|e|e.file_name()))
        .collect::<io::Result<std::collections::BTreeSet<_>>>()?;
    let expected=MATERIALS.map(|k|std::ffi::OsString::from(k.name())).into_iter().collect();
    if names!=expected {return Err(invalid("normal apps41 source stage roster differs"));}
    for kind in MATERIALS {
        let path=root.join(kind.name());
        let file=OpenOptions::new().read(true).custom_flags(0x20000|0x80000).open(&path)?;
        let before=f9(&file.metadata()?)?;
        if before[2]!=0o100444 || before[5]!=1 || before[6]!=kind.expected().0 as u64 {
            return Err(invalid("normal apps41 source stage metadata differs"));
        }
        let mut raw=vec![0;before[6] as usize];
        file.read_exact_at(&mut raw,0)?;
        if raw!=kind.checked()? || f9(&file.metadata()?)?!=before
            || f9(&fs::symlink_metadata(&path)?)?!=before {
            return Err(invalid("normal apps41 source stage bytes/inode changed"));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn working_preparation_parent_custody_is_metadata_only_and_rejects_aliases() {
        let root=tempfile::tempdir().unwrap();
        let mut held=directory(root.path()).unwrap();
        assert_eq!(f9(&held.metadata().unwrap()).unwrap(),
            f9(&fs::symlink_metadata(root.path()).unwrap()).unwrap());
        assert_eq!(std::io::Read::read(&mut held,&mut[0_u8;1]).unwrap_err().raw_os_error(),Some(9));
        let alias=root.path().join("alias");
        std::os::unix::fs::symlink(root.path(),&alias).unwrap();
        assert!(directory(&alias).is_err());
        assert!(held.metadata().unwrap().is_dir());
    }
    #[test]
    fn working_preparation_fixed_materials_are_the_exact_apps41_source_documents() {
        assert_eq!(MATERIALS.len(),5);
        for kind in MATERIALS {kind.checked().unwrap();}
        let selection:Value=serde_json::from_slice(PreparationMaterial::Selection.checked().unwrap()).unwrap();
        assert_eq!(selection["package_count"],41);
        assert_eq!(selection["applications"].as_array().unwrap().len(),41);
        assert_eq!(PreparationMaterial::Selection.reference()["sha256"],
            "4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0");
    }
    #[test]
    fn working_preparation_material_stage_rejects_changed_bytes_and_extra_members() {
        let dir=tempfile::tempdir().unwrap();
        let paths=stage_working_preparation_materials(dir.path()).unwrap();
        let selected=dir.path().join(&paths[0]);
        fs::set_permissions(&selected,fs::Permissions::from_mode(0o600)).unwrap();
        let mut wrong=fs::read(&selected).unwrap();
        wrong[0]^=1;
        fs::write(&selected,wrong).unwrap();
        fs::set_permissions(&selected,fs::Permissions::from_mode(0o444)).unwrap();
        assert!(verify_staged_working_preparation_materials(dir.path()).is_err());
        let clean=tempfile::tempdir().unwrap();
        stage_working_preparation_materials(clean.path()).unwrap();
        fs::write(clean.path().join(INSTALLED_ROOT.trim_start_matches('/')).join("SELECTED39.json"),b"stale").unwrap();
        assert!(verify_staged_working_preparation_materials(clean.path()).is_err());
    }
    #[test]
    fn working_preparation_material_stage_is_complete_and_create_only() {
        let dir=tempfile::tempdir().unwrap();
        let paths=stage_working_preparation_materials(dir.path()).unwrap();
        assert_eq!(paths.len(),5);
        for (path,kind) in paths.iter().zip(MATERIALS) {
            assert_eq!(fs::read(dir.path().join(path)).unwrap(),kind.checked().unwrap());
        }
        assert!(stage_working_preparation_materials(dir.path()).is_err());
    }
}
