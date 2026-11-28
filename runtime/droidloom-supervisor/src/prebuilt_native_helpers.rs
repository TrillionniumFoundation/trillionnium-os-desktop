//! Fixed public artifacts from the normal source-owned helper producers.
//! APKs and public certificates are external release inputs, never Git binaries.
//! Source material alone grants no installation, application or Main authority.
use std::{collections::{BTreeMap,BTreeSet}, ffi::{CStr,CString}, fs::{self,File},
 io, os::{fd::{AsRawFd,FromRawFd},unix::fs::{FileExt,MetadataExt}},time::Instant};
use serde_json::{Value,json};
use sha2::{Digest,Sha256};

pub const DOCUMENTS_ROOT:&str="/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1";
pub const IHG_ROOT:&str="/usr/libexec/droidloom/native-application-leaves/prebuilt-ihg";

#[derive(Clone,Copy,Debug,Eq,PartialEq)]
pub enum DocumentsHelperKind {Saf,Features}
#[derive(Clone,Copy,Debug,Eq,PartialEq)]
pub enum HelperKind {Saf,Features,Ihg,Rotation,Video}
impl HelperKind {
    pub const fn name(self)->&'static str {match self {Self::Saf=>"saf",Self::Features=>"features",Self::Ihg=>"ihg",Self::Rotation=>"rotation",Self::Video=>"video"}}
    pub const fn root(self)->&'static str {match self {
        Self::Saf=>"/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1/saf",
        Self::Features=>"/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1/features",
        Self::Ihg=>IHG_ROOT,
        Self::Rotation=>"/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1/rotation",
        Self::Video=>"/usr/libexec/droidloom/native-application-leaves/prebuilt-state-fixtures/20261128-r1/video",
    }}
    pub const fn package(self)->&'static str {match self {
        Self::Saf=>"org.droidloom.qa.saf.r12.na7f1de49e707c7a9",
        Self::Features=>"org.droidloom.qa.documents.r12.n98116f3fbefcfc95",
        Self::Ihg=>"org.droidloom.qa.ihg.finalmain.r1",
        Self::Rotation=>"org.droidloom.qa.galleryrotation.r12.nd24b61ed8f7c9a03",
        Self::Video=>"org.droidloom.qa.media.r12.nc92c3d79180955ef",

    }}
    pub const fn certificate_sha256(self)->&'static str {match self {
        Self::Saf=>"b5ed86bf8873ade11e2304965288d19f0ee0dc84da5a5f3e4411d4535b015ea7",
        Self::Features=>"06c090f9bcca6c214621b85222ddc86d672aee3085c1e3bc278a40f8c5d8ef11",
        Self::Ihg=>"5def0263df5a79b37e189cda939794dcf96be8c85f5a659af0f98c7509302347",
        Self::Rotation=>"f122e9201c86a547b8cbaa37cbe2cd7962bb96eabe3c07365204d392b580244f",
        Self::Video=>"011632c9e2a1693585594df2bcc4b4fdb4cd074a05ccbdc5aa951aa1de9ad0b2",

    }}
}

/// A source-owned member description, never a runtime observation.
pub struct SourceMember {
    pub kind:HelperKind,pub relative:&'static str,pub bytes:u64,pub sha256:&'static str,
    body:Option<&'static [u8]>,
}
impl SourceMember {
    pub fn verify_body(&self,body:&[u8])->io::Result<()> {
        if body.len() as u64!=self.bytes || sha(body)!=self.sha256 {
            return Err(bad("normal helper source member changed"));
        }
        Ok(())
    }
    pub fn embedded_body(&self)->io::Result<Option<&'static [u8]>> {
        if let Some(body)=self.body {self.verify_body(body)?;}
        Ok(self.body)
    }
    pub fn installed_path(&self)->String {format!("{}/{}",self.kind.root(),self.relative)}
    pub fn reference(&self)->Value {json!({"path":self.installed_path(),"bytes":self.bytes,"sha256":self.sha256})}
}
macro_rules! member {
    ($kind:expr,$relative:literal,$resource:literal,$bytes:expr,$sha:literal)=>{
        SourceMember{kind:$kind,relative:$relative,bytes:$bytes,sha256:$sha,
          body:Some(include_bytes!(concat!("../../../tools/droidloom-update/resources/prebuilt-helpers/products/",$resource)))}
    };
}
pub const ALL_KINDS:[HelperKind;5]=[HelperKind::Saf,HelperKind::Features,HelperKind::Ihg,HelperKind::Rotation,HelperKind::Video];
pub static MEMBERS:&[SourceMember]=&[
    member!(HelperKind::Ihg, "MANIFEST.json", "ihg/MANIFEST.json", 5343, "43ae54d43a661191d90c9ff56887047a9c6cd159e825769479ad4be5220473a5"),
    member!(HelperKind::Ihg, "SOURCE.json", "ihg/SOURCE.json", 712, "8744f1fa7d06143b1e0a6bcc9c639ecce270ba350b1c663cfb1cab10c3c9357a"),
    SourceMember{kind:HelperKind::Ihg,relative:"helper.apk",bytes:24720,sha256:"c5e38378c6f61e989ecaa4177eed48039b836aa6311e18961824adfd238dde15",body:None},
    SourceMember{kind:HelperKind::Ihg,relative:"signer.der",bytes:1082,sha256:"5def0263df5a79b37e189cda939794dcf96be8c85f5a659af0f98c7509302347",body:None},
    member!(HelperKind::Ihg, "source/ActionRunner.java", "ihg/source/ActionRunner.java", 44009, "aa139d6a586fc8337bd744d027beb9270ab100dc1b7563cd7d0de61839b3dced"),
    member!(HelperKind::Ihg, "source/AndroidManifest.xml", "ihg/source/AndroidManifest.xml", 743, "1dbea60ecc696ed83d23eaffaf183dc5ed2bcbe58ea3181de09a911f7118e5a6"),
    member!(HelperKind::Saf, "MANIFEST.json", "state-r1/saf/MANIFEST.json", 16781, "5b965fdab8fd49af9686854fb65f7ce0442e83f716752802ede2f646cc429dbb"),
    member!(HelperKind::Saf, "SOURCE.json", "state-r1/saf/SOURCE.json", 2281, "a6ac2ec4a91930e573bca80b712738a7db647036a9ba86b3d2f169cd55b7123a"),
    member!(HelperKind::Saf, "STATE-SOURCE.json", "state-r1/saf/STATE-SOURCE.json", 15851, "d11880a5c19c7783b5d7b130f081740887e559891aee0fc3ebda0cb3f339cb2b"),
    SourceMember{kind:HelperKind::Saf,relative:"helper.apk",bytes:24838,sha256:"eb7bac9ede6b729829fbecb031db4ae7b7224634619154abe2f01b2b3be875d6",body:None},
    SourceMember{kind:HelperKind::Saf,relative:"signer.der",bytes:1083,sha256:"b5ed86bf8873ade11e2304965288d19f0ee0dc84da5a5f3e4411d4535b015ea7",body:None},
    member!(HelperKind::Saf, "source/AndroidManifest.xml", "state-r1/saf/source/AndroidManifest.xml", 1137, "a3adcf3764edcda1fb89526ea93669637e3513342788d4d681581695b77451b9"),
    member!(HelperKind::Saf, "source/SOURCE_PINS.json", "state-r1/saf/source/SOURCE_PINS.json", 2281, "a6ac2ec4a91930e573bca80b712738a7db647036a9ba86b3d2f169cd55b7123a"),
    member!(HelperKind::Saf, "source/contract.json", "state-r1/saf/source/contract.json", 1105, "146bba638a8875dd7b3eedc0d1fbbcd28e636975afd4a65cb145927abc7ac6cf"),
    member!(HelperKind::Saf, "source/res/values/ids.xml", "state-r1/saf/source/res/values/ids.xml", 273, "96b43d2d226700a9d1b99a9575b6ab73f5ca245776165d1a05ef783579e9c1f7"),
    member!(HelperKind::Saf, "source/src/org/droidloom/qa/saf/r12/na7f1de49e707c7a9/SafActivity.java", "state-r1/saf/source/src/org/droidloom/qa/saf/r12/na7f1de49e707c7a9/SafActivity.java", 16590, "b0e977a68c02d1e2d9be5509d2e705f4068480ab85bd7409e3fe9a625f0dd7fd"),
    member!(HelperKind::Saf, "state/FixedStateProvider.java", "state-r1/saf/state/FixedStateProvider.java", 11630, "f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545"),
    member!(HelperKind::Features, "MANIFEST.json", "state-r1/features/MANIFEST.json", 16943, "943aa4b47117d5a164dd8f69fecbc3be975d936bb78d17a2eef3d0d1c4823c0f"),
    member!(HelperKind::Features, "SOURCE.json", "state-r1/features/SOURCE.json", 2389, "f6c5426f1363bd16d259a14676696e9353efd630d52b562481975e1d2a7782c8"),
    member!(HelperKind::Features, "STATE-SOURCE.json", "state-r1/features/STATE-SOURCE.json", 15992, "55aa42d39f0659449b50ebd257e9e0b57a0d832a7ebb49ab7b1920060bf665bb"),
    SourceMember{kind:HelperKind::Features,relative:"helper.apk",bytes:24838,sha256:"368e9c52f391c0f11f78da4b1c3c9e72abe31f4d001fa593ebd46a59dcb7fab5",body:None},
    SourceMember{kind:HelperKind::Features,relative:"signer.der",bytes:1083,sha256:"06c090f9bcca6c214621b85222ddc86d672aee3085c1e3bc278a40f8c5d8ef11",body:None},
    member!(HelperKind::Features, "source/AndroidManifest.xml", "state-r1/features/source/AndroidManifest.xml", 721, "bf3848131b913324665cf85ce1648b388d1ba2deda6386487703a0b7ea3a3ebf"),
    member!(HelperKind::Features, "source/SOURCE_PINS.json", "state-r1/features/source/SOURCE_PINS.json", 2389, "f6c5426f1363bd16d259a14676696e9353efd630d52b562481975e1d2a7782c8"),
    member!(HelperKind::Features, "source/contract.json", "state-r1/features/source/contract.json", 3302, "68f18ac35676090c1a05fb7709bf90de475bc4c31cf0642ac6fe92aad4343828"),
    member!(HelperKind::Features, "source/res/values/ids.xml", "state-r1/features/source/res/values/ids.xml", 451, "2cb07cba41fa376ebc3d8f72f7e9491a8dc88ae87672d75ab1fcba1f0fb82083"),
    member!(HelperKind::Features, "source/src/org/droidloom/qa/documents/r12/n98116f3fbefcfc95/FeaturesActivity.java", "state-r1/features/source/src/org/droidloom/qa/documents/r12/n98116f3fbefcfc95/FeaturesActivity.java", 19190, "a3339fc610064e5b91a91e138cbb7707b04e4aa9fc62f5f4b7571f5ede22cfe9"),
    member!(HelperKind::Features, "state/FixedStateProvider.java", "state-r1/features/state/FixedStateProvider.java", 11630, "f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545"),
    member!(HelperKind::Rotation, "MANIFEST.json", "state-r1/rotation/MANIFEST.json", 16172, "69e35a784613abf7f63d1fe794d3b0cc47fd3d0b5b9d443f01534eabbf324a63"),
    member!(HelperKind::Rotation, "SOURCE.json", "state-r1/rotation/SOURCE.json", 924, "cf0fb33c74e066afcfc660bd9dadfafdd8cd5b77c361d649bf0680100c019193"),
    member!(HelperKind::Rotation, "STATE-SOURCE.json", "state-r1/rotation/STATE-SOURCE.json", 15995, "2c38c042ac2eea340faf0e2203b7c1cc6acd115fcccb0bcbb5f783df9d33c503"),
    SourceMember{kind:HelperKind::Rotation,relative:"helper.apk",bytes:24838,sha256:"d53ba35fdb2252126fef94ce7da2d43bff78560cc90111206b0c2c9e766777d3",body:None},
    SourceMember{kind:HelperKind::Rotation,relative:"signer.der",bytes:1084,sha256:"f122e9201c86a547b8cbaa37cbe2cd7962bb96eabe3c07365204d392b580244f",body:None},
    member!(HelperKind::Rotation, "state/FixedStateProvider.java", "state-r1/rotation/state/FixedStateProvider.java", 11630, "f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545"),
    member!(HelperKind::Video, "MANIFEST.json", "state-r1/video/MANIFEST.json", 16071, "ce4e38dd0c556987330d700a3130e22e898bd649fd50c2ceb4a352059031c13b"),
    member!(HelperKind::Video, "SOURCE.json", "state-r1/video/SOURCE.json", 1053, "c06e5e21187d5b5b3a813b9d70e23f20ac0a51092cc530b79b289fa01b7c7552"),
    member!(HelperKind::Video, "STATE-SOURCE.json", "state-r1/video/STATE-SOURCE.json", 16188, "1b3bb25444ed190edac68bb7ff95e72d2ff16ea271c192ca4349a185c7aa68c2"),
    SourceMember{kind:HelperKind::Video,relative:"helper.apk",bytes:41286,sha256:"f47d64fe943bb77fb8ad07288b4ae1c69e3db8cc8866b0e02230882134599820",body:None},
    SourceMember{kind:HelperKind::Video,relative:"signer.der",bytes:1083,sha256:"011632c9e2a1693585594df2bcc4b4fdb4cd074a05ccbdc5aa951aa1de9ad0b2",body:None},
    member!(HelperKind::Video, "state/FixedStateProvider.java", "state-r1/video/state/FixedStateProvider.java", 11630, "f64e47dd052a3dd60e912c69d79ce075fbd88baea1d4db29a3dab3ad02dd3545"),
];

fn bad(s:&str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,s)}
fn before(end:Instant)->io::Result<()> {
    if Instant::now()>=end {Err(bad("prebuilt helper original deadline expired"))}else{Ok(())}
}
fn sha(b:&[u8])->String {format!("{:x}",Sha256::digest(b))}
fn f9(m:&fs::Metadata)->io::Result<[u64;9]> {
    let ns=|s:i64,n:i64|u64::try_from(i128::from(s)*1_000_000_000+i128::from(n))
        .map_err(|_|bad("prebuilt helper inode time invalid"));
    Ok([m.dev(),m.ino(),u64::from(m.mode()),u64::from(m.uid()),u64::from(m.gid()),m.nlink(),m.len(),
        ns(m.mtime(),m.mtime_nsec())?,ns(m.ctime(),m.ctime_nsec())?])
}
fn opened(parent:i32,name:&CStr,flags:i32)->io::Result<File> {
    let fd=unsafe{libc::openat(parent,name.as_ptr(),flags|libc::O_CLOEXEC|libc::O_NOFOLLOW)};
    if fd<0 {Err(io::Error::last_os_error())}else{Ok(unsafe{File::from_raw_fd(fd)})}
}
fn protected(file:&File,exact:bool)->io::Result<[u64;5]> {
    let n=f9(&file.metadata()?)?;
    if n[2]&0o170000!=0o040000 || n[2]&0o022!=0 || n[3..5]!=[0,0] || (exact && n[2]!=0o040755) {
        return Err(bad("prebuilt helper directory is not the protected normal root"));
    }
    Ok(n[..5].try_into().map_err(|_|bad("directory identity width"))?)
}
fn names(file:&File)->io::Result<BTreeSet<Vec<u8>>> {
    let fd=unsafe{libc::fcntl(file.as_raw_fd(),libc::F_DUPFD_CLOEXEC,3)};
    if fd<0 {return Err(io::Error::last_os_error());}
    let dir=unsafe{libc::fdopendir(fd)};
    if dir.is_null() {let error=io::Error::last_os_error();unsafe{libc::close(fd)};return Err(error);}
    unsafe{libc::rewinddir(dir);}
    let mut out=BTreeSet::new();
    loop {
        unsafe{*libc::__errno_location()=0;}
        let p=unsafe{libc::readdir(dir)};
        if p.is_null() {
            let code=unsafe{*libc::__errno_location()};
            unsafe{libc::closedir(dir);}
            if code!=0 {return Err(io::Error::from_raw_os_error(code));}
            break;
        }
        let name=unsafe{CStr::from_ptr((*p).d_name.as_ptr())}.to_bytes();
        if name==b"." || name==b".." {continue;}
        if out.len()>=32 || !out.insert(name.to_vec()) {unsafe{libc::closedir(dir);}return Err(bad("prebuilt helper directory roster exceeds source"));}
    }
    Ok(out)
}
struct Directory {file:File,identity:[u64;5],parent:Option<usize>,name:CString,enumerated:bool,expected:BTreeSet<Vec<u8>>}
struct Input {file:File,identity:[u64;9],parent:usize,name:CString,source:&'static SourceMember}
struct Bundle {kind:HelperKind,directories:Vec<Directory>,inputs:Vec<Input>,end:Instant}
impl Bundle {
    fn capture_before(kind:HelperKind,retention_end:Instant,end:Instant)->io::Result<Self> {
        if end>retention_end {return Err(bad("helper capture operation exceeds original retention end"));}
        before(end)?;
        let root=opened(libc::AT_FDCWD,c"/",libc::O_PATH|libc::O_DIRECTORY)?;
        let mut directories=vec![Directory{identity:protected(&root,false)?,file:root,parent:None,name:CString::new("/")?,enumerated:false,expected:BTreeSet::new()}];
        let mut parent=0usize;
        // Ancestors are only identity/openat anchors; enumerate only the fixed bundle tree.
        let mut components=kind.root().trim_start_matches('/').split('/').peekable();
        while let Some(component)=components.next() {
            before(end)?;
            let name=CString::new(component)?;
            let enumerated=components.peek().is_none();
            let flags=if enumerated{libc::O_RDONLY}else{libc::O_PATH};
            let file=opened(directories[parent].file.as_raw_fd(),&name,flags|libc::O_DIRECTORY)?;
            let identity=protected(&file,false)?;
            directories.push(Directory{file,identity,parent:Some(parent),name,enumerated,expected:BTreeSet::new()});
            parent=directories.len()-1;
        }
        let bundle_root=parent;
        protected(&directories[bundle_root].file,true)?;
        let mut relative=BTreeMap::from([(String::new(),bundle_root)]);
        let selected:Vec<_>=MEMBERS.iter().filter(|m|m.kind==kind).collect();
        let mut inputs=Vec::new();
        for source in selected {
            before(end)?;source.embedded_body()?;
            let parts:Vec<_>=source.relative.split('/').collect();
            let mut prefix=String::new();let mut d=bundle_root;
            for component in &parts[..parts.len()-1] {
                directories[d].expected.insert(component.as_bytes().to_vec());
                if !prefix.is_empty(){prefix.push('/');}prefix.push_str(component);
                d=if let Some(index)=relative.get(&prefix){*index}else{
                    let name=CString::new(*component)?;
                    let file=opened(directories[d].file.as_raw_fd(),&name,libc::O_RDONLY|libc::O_DIRECTORY)?;
                    let identity=protected(&file,true)?;
                    directories.push(Directory{file,identity,parent:Some(d),name,enumerated:true,expected:BTreeSet::new()});
                    let index=directories.len()-1;relative.insert(prefix.clone(),index);index
                };
            }
            let name=CString::new(*parts.last().ok_or_else(||bad("missing helper name"))?)?;
            directories[d].expected.insert(name.as_bytes().to_vec());
            let file=opened(directories[d].file.as_raw_fd(),&name,libc::O_RDONLY|libc::O_NONBLOCK)?;
            let identity=f9(&file.metadata()?)?;
            if identity[2]!=0o100444 || identity[3..6]!=[0,0,1] || identity[6]!=source.bytes {
                return Err(bad("prebuilt helper installed file metadata differs"));
            }
            inputs.push(Input{file,identity,parent:d,name,source});
        }
        let value=Self{kind,directories,inputs,end:retention_end};value.guard(end)?;Ok(value)
    }
    fn guard(&self,end:Instant)->io::Result<()> {
        if end>self.end{return Err(bad("prebuilt helper deadline cannot be renewed"));}
        before(end)?;
        for dir in &self.directories {
            before(end)?;
            if protected(&dir.file,false)?!=dir.identity {return Err(bad("held helper parent changed"));}
            let flags=if dir.enumerated{libc::O_RDONLY}else{libc::O_PATH};
            let named=match dir.parent{
                Some(p)=>opened(self.directories[p].file.as_raw_fd(),&dir.name,flags|libc::O_DIRECTORY)?,
                None=>opened(libc::AT_FDCWD,c"/",flags|libc::O_DIRECTORY)?,
            };
            if protected(&named,false)?!=dir.identity {return Err(bad("named helper parent changed"));}
            if dir.enumerated && names(&dir.file)?!=dir.expected {
                return Err(bad("fixed prebuilt helper tree has missing or extra names"));
            }
        }
        for input in &self.inputs {
            before(end)?;
            let named=opened(self.directories[input.parent].file.as_raw_fd(),&input.name,libc::O_RDONLY|libc::O_NONBLOCK)?;
            if f9(&input.file.metadata()?)?!=input.identity || f9(&named.metadata()?)?!=input.identity {
                return Err(bad("prebuilt helper held/named inode changed"));
            }
            let mut raw=vec![0;input.source.bytes as usize];
            input.file.read_exact_at(&mut raw,0)?;
            input.source.verify_body(&raw)?;
            if input.file.read_at(&mut[0],input.source.bytes)?!=0
                || f9(&input.file.metadata()?)?!=input.identity || f9(&named.metadata()?)?!=input.identity {
                return Err(bad("prebuilt helper whole bytes changed"));
            }
        }
        before(end)
    }
    fn input(&self,name:&str)->io::Result<&Input> {self.inputs.iter().find(|i|i.source.relative==name).ok_or_else(||bad("fixed helper member absent"))}
    fn reference(&self,name:&str)->io::Result<Value> {Ok(self.input(name)?.source.reference())}
    fn comparison(&self)->Value {
        json!({"schema":"droidloom.held-prebuilt-helper-material.v2","kind":self.kind.name(),"package":self.kind.package(),
            "manifest":self.inputs.iter().find(|i|i.source.relative=="MANIFEST.json").map(|i|i.source.reference()),
            "members":self.inputs.iter().map(|i|json!({"source":i.source.reference(),"actual_inode":i.identity})).collect::<Vec<_>>(),
            "installation_authority":false,"Main_authority":false,"whole_app_business_accepted":false})
    }
}

/// Actual normal installed Docs bundle custody. Only the two compiled roots
/// can construct it. A successful installation still needs its own factory.
pub struct PrebuiltDocumentsMaterial {kind:DocumentsHelperKind,bundle:Bundle}
impl PrebuiltDocumentsMaterial {
    pub fn capture(kind:DocumentsHelperKind,end:Instant)->io::Result<Self> {
        Self::capture_before(kind,end,end)
    }
    pub(crate) fn capture_before(kind:DocumentsHelperKind,retention_end:Instant,operation_end:Instant)->io::Result<Self> {
        let source=match kind{DocumentsHelperKind::Saf=>HelperKind::Saf,DocumentsHelperKind::Features=>HelperKind::Features};
        Ok(Self{kind,bundle:Bundle::capture_before(source,retention_end,operation_end)?})
    }
    pub fn kind(&self)->DocumentsHelperKind {self.kind}
    pub fn package(&self)->&'static str {self.bundle.kind.package()}
    pub fn run_id(&self)->&'static str {match self.kind{DocumentsHelperKind::Saf=>"a7f1de49e707c7a9",DocumentsHelperKind::Features=>"98116f3fbefcfc95"}}
    pub fn version_code(&self)->u64 {1}
    pub fn apk_bytes(&self)->u64 {self.bundle.input("helper.apk").expect("compiled APK member").source.bytes}
    pub fn apk_sha256(&self)->&'static str {self.bundle.input("helper.apk").expect("compiled APK member").source.sha256}
    pub fn certificate_sha256(&self)->&'static str {self.bundle.kind.certificate_sha256()}
    pub fn guard(&self,end:Instant)->io::Result<()> {self.bundle.guard(end)}
    /// Borrow the actual O_RDONLY file; ownership and full content remain held.
    /// The caller must retain this material through its actual transaction.
    pub fn apk_file(&self,end:Instant)->io::Result<&File> {self.guard(end)?;Ok(&self.bundle.input("helper.apk")?.file)}
    pub fn manifest_reference(&self,end:Instant)->io::Result<Value> {self.guard(end)?;self.bundle.reference("MANIFEST.json")}
    pub fn source_reference(&self,end:Instant)->io::Result<Value> {self.guard(end)?;self.bundle.reference("SOURCE.json")}
    pub fn comparison(&self)->Value {self.bundle.comparison()}
}

/// The four current state fixtures use the same full protected bundle custody.
/// Only this source enum selects a root; no caller pathname is accepted.
pub(crate) struct PrebuiltStateMaterial {bundle:Bundle}
impl PrebuiltStateMaterial {
    pub(crate) fn capture_before(kind:HelperKind,retention_end:Instant,end:Instant)->io::Result<Self> {
        if kind==HelperKind::Ihg{return Err(bad("IHG is not a state fixture"));}
        Ok(Self{bundle:Bundle::capture_before(kind,retention_end,end)?})
    }
    pub(crate) fn guard(&self,end:Instant)->io::Result<()> {self.bundle.guard(end)}
    pub(crate) fn apk_file(&self,end:Instant)->io::Result<&File>{self.guard(end)?;Ok(&self.bundle.input("helper.apk")?.file)}
    pub(crate) fn comparison(&self)->Value{self.bundle.comparison()}
}

/// Separate fixed instrumentation material. No target Main is embedded.
pub struct PrebuiltIhgMaterial {bundle:Bundle}
impl PrebuiltIhgMaterial {
    pub fn capture(end:Instant)->io::Result<Self> {Self::capture_before(end,end)}
    pub(crate) fn capture_before(retention_end:Instant,operation_end:Instant)->io::Result<Self> {
        Ok(Self{bundle:Bundle::capture_before(HelperKind::Ihg,retention_end,operation_end)?})
    }
    pub fn package(&self)->&'static str {HelperKind::Ihg.package()}
    pub fn version_code(&self)->u64 {1}
    pub fn certificate_sha256(&self)->&'static str {HelperKind::Ihg.certificate_sha256()}
    pub fn apk_bytes(&self)->u64 {self.bundle.input("helper.apk").expect("compiled APK member").source.bytes}
    pub fn apk_sha256(&self)->&'static str {self.bundle.input("helper.apk").expect("compiled APK member").source.sha256}
    pub fn apk_file(&self,end:Instant)->io::Result<&File> {self.guard(end)?;Ok(&self.bundle.input("helper.apk")?.file)}
    pub fn guard(&self,end:Instant)->io::Result<()> {self.bundle.guard(end)}
    pub fn manifest_reference(&self,end:Instant)->io::Result<Value> {self.guard(end)?;self.bundle.reference("MANIFEST.json")}
    pub fn comparison(&self)->Value {self.bundle.comparison()}
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn prebuilt_helper_sources_bind_exact_public_products_and_original_static_scope() {
        assert_eq!(MEMBERS.len(),40);
        assert_eq!(MEMBERS.iter().filter(|m|m.body.is_none()).count(),10);
        for kind in ALL_KINDS {
            let rows:Vec<_>=MEMBERS.iter().filter(|m|m.kind==kind).collect();
            assert_eq!(rows.len(),if matches!(kind,HelperKind::Saf|HelperKind::Features){11}else{6});
            let source:BTreeMap<_,_>=rows.iter().map(|m|(m.relative,*m)).collect();
            for row in &rows {row.embedded_body().unwrap();if row.body.is_none(){assert!(matches!(row.relative,"helper.apk"|"signer.der"));}}
            let v:Value=serde_json::from_slice(source["MANIFEST.json"].body.unwrap()).unwrap();
            assert_eq!(v["schema"],if kind==HelperKind::Ihg{"droidloom.prebuilt-helper-bundle.v2"}else{"droidloom.prebuilt-state-helper-bundle.v1"});
            assert_eq!(v["contract"]["package"],kind.package());assert_eq!(v["contract"]["version_code"],1);
            assert_eq!(v["contract"]["min_sdk"],31);assert_eq!(v["contract"]["target_sdk"],33);
            assert_eq!(v["contract"]["test_only"],true);assert_eq!(v["contract"]["debuggable"],false);
            assert_eq!(v["actual_main_embedded_in_apk"],false);assert_eq!(v["private_signing_key_published"],false);
            assert_eq!(v["runtime_authority_created"],false);assert_eq!(v["installed"],false);
            assert_eq!(v["certificate_sha256"],kind.certificate_sha256());
            let declared=v["members"].as_object().unwrap();
            assert_eq!(declared.len(),rows.len()-1);
            for row in &rows {if row.relative!="MANIFEST.json" {
                assert_eq!(declared[row.relative]["bytes"],row.bytes);
                assert_eq!(declared[row.relative]["sha256"],row.sha256);
            }}
            assert_eq!(v["commands"].as_array().unwrap().len(),if kind==HelperKind::Ihg{11}else{12});
            if kind!=HelperKind::Ihg {
                assert_eq!(v["original_sources_recompiled"],false);
                assert_eq!(v["original_manifest_semantics_preserved"],true);
                assert_eq!(v["original_business_dex_resources_assets_preserved"],true);
                assert_eq!(v["contract"]["state_caller_uid"],2000);
            }
            for command in v["commands"].as_array().unwrap(){assert_eq!(command["returncode"],0);}
        }
    }
}
