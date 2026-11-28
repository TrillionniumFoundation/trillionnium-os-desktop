//! Fixed external build inputs for the four state fixtures and the IHG helper.
//! APKs/certificates are release assets, not repository binaries. This module
//! accepts no caller path and holds every input through the complete stage.
use droidloom_supervisor::prebuilt_native_helpers::{HelperKind, SourceMember, MEMBERS, ALL_KINDS};
use std::{collections::BTreeSet, ffi::{CStr,CString}, fs::{self,File}, io,
    os::{fd::{AsRawFd,FromRawFd},unix::fs::{FileExt,MetadataExt}}, path::Path};

pub(super) const ROOT:&str="/var/lib/droidloom-public-build-inputs/prebuilt-helpers/20261128-r2";
fn bad(s:&str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,s)}
fn f9(m:&fs::Metadata)->[i128;9]{[m.dev().into(),m.ino().into(),m.mode().into(),m.uid().into(),m.gid().into(),
    m.nlink().into(),m.len().into(),i128::from(m.mtime())*1_000_000_000+i128::from(m.mtime_nsec()),
    i128::from(m.ctime())*1_000_000_000+i128::from(m.ctime_nsec())]}
fn opened(parent:&File,name:&CStr,flags:i32)->io::Result<File>{
    let fd=unsafe{libc::openat(parent.as_raw_fd(),name.as_ptr(),flags|libc::O_NOFOLLOW|libc::O_CLOEXEC)};
    if fd<0{Err(io::Error::last_os_error())}else{Ok(unsafe{File::from_raw_fd(fd)})}
}
fn directory(f:&File)->io::Result<[i128;5]>{
    let m=f.metadata()?;
    if !m.is_dir() || m.uid()!=0 || m.gid()!=0 || m.mode()&0o022!=0 {
        return Err(bad("fixed helper build input ancestor must be root-owned and nonwritable"));
    }
    Ok(f9(&m)[..5].try_into().expect("five directory fields"))
}
fn names(f:&File)->io::Result<BTreeSet<Vec<u8>>>{
    let copy=opened(f,c".",libc::O_RDONLY|libc::O_DIRECTORY)?;
    let fd=unsafe{libc::fcntl(copy.as_raw_fd(),libc::F_DUPFD_CLOEXEC,3)};
    if fd<0{return Err(io::Error::last_os_error());}
    let d=unsafe{libc::fdopendir(fd)};
    if d.is_null(){let e=io::Error::last_os_error();unsafe{libc::close(fd)};return Err(e);}
    let mut result=BTreeSet::new();
    loop{
        unsafe{*libc::__errno_location()=0;}
        let row=unsafe{libc::readdir(d)};
        if row.is_null(){let code=unsafe{*libc::__errno_location()};unsafe{libc::closedir(d)};
            return if code==0{Ok(result)}else{Err(io::Error::from_raw_os_error(code))};}
        let n=unsafe{CStr::from_ptr((*row).d_name.as_ptr())}.to_bytes();
        if n==b"." || n==b".."{continue;}
        if result.len()>=8 || !result.insert(n.to_vec()){
            unsafe{libc::closedir(d)};return Err(bad("fixed helper build input directory exceeds its closed roster"));
        }
    }
}
struct Directory{file:File,identity:[i128;5],parent:Option<usize>,name:CString,expected:Option<BTreeSet<Vec<u8>>>}
struct Input{file:File,identity:[i128;9],parent:usize,source:&'static SourceMember}
pub(super) struct ExternalInputs{directories:Vec<Directory>,inputs:Vec<Input>}
impl ExternalInputs{
    pub(super) fn capture()->io::Result<Self>{
        let fd=unsafe{libc::open(c"/".as_ptr(),libc::O_PATH|libc::O_DIRECTORY|libc::O_NOFOLLOW|libc::O_CLOEXEC)};
        if fd<0{return Err(io::Error::last_os_error());}
        let root=unsafe{File::from_raw_fd(fd)};
        let mut directories=vec![Directory{identity:directory(&root)?,file:root,parent:None,name:CString::new("/")?,expected:None}];
        let mut parent=0;
        for n in ROOT.trim_start_matches('/').split('/'){
            let name=CString::new(n)?;let file=opened(&directories[parent].file,&name,libc::O_PATH|libc::O_DIRECTORY)?;
            let identity=directory(&file)?;
            directories.push(Directory{file,identity,parent:Some(parent),name,expected:None});parent=directories.len()-1;
        }
        let cohort=parent;
        let kinds=ALL_KINDS;
        directories[cohort].expected=Some(kinds.iter().map(|k|k.name().as_bytes().to_vec()).collect());
        let mut inputs=Vec::new();
        for kind in kinds{
            let name=CString::new(kind.name())?;let file=opened(&directories[cohort].file,&name,libc::O_PATH|libc::O_DIRECTORY)?;
            let identity=directory(&file)?;
            directories.push(Directory{file,identity,parent:Some(cohort),name,
                expected:Some([b"helper.apk".to_vec(),b"signer.der".to_vec()].into())});
            let parent=directories.len()-1;
            for source in MEMBERS.iter().filter(|m|m.kind==kind && matches!(m.relative,"helper.apk"|"signer.der")){
                if source.embedded_body()?.is_some(){return Err(bad("helper APK/certificate must remain external build material"));}
                let file=opened(&directories[parent].file,&CString::new(source.relative)?,libc::O_RDONLY|libc::O_NONBLOCK)?;
                let identity=Self::file_identity(&file,source.bytes)?;
                inputs.push(Input{file,identity,parent,source});
            }
        }
        if inputs.len()!=10{return Err(bad("exactly five external APK/certificate pairs are required"));}
        let value=Self{directories,inputs};value.guard()?;Ok(value)
    }
    fn file_identity(f:&File,bytes:u64)->io::Result<[i128;9]>{
        let m=f.metadata()?;
        if m.mode()!=0o100444 || m.uid()!=0 || m.gid()!=0 || m.nlink()!=1 || m.len()!=bytes || bytes==0 || bytes>262144 {
            return Err(bad("fixed helper input must be the complete root-owned single-link readonly member"));
        }
        Ok(f9(&m))
    }
    fn read(&self,input:&Input)->io::Result<Vec<u8>>{
        let named=opened(&self.directories[input.parent].file,&CString::new(input.source.relative)?,libc::O_RDONLY|libc::O_NONBLOCK)?;
        if Self::file_identity(&input.file,input.source.bytes)?!=input.identity
            || Self::file_identity(&named,input.source.bytes)?!=input.identity{
            return Err(bad("fixed helper input held/named inode changed"));
        }
        let mut body=vec![0;input.source.bytes as usize];input.file.read_exact_at(&mut body,0)?;
        input.source.verify_body(&body)?;
        if input.file.read_at(&mut[0],input.source.bytes)?!=0
            || Self::file_identity(&input.file,input.source.bytes)?!=input.identity
            || Self::file_identity(&named,input.source.bytes)?!=input.identity{
            return Err(bad("fixed helper input changed during complete source readback"));
        }
        Ok(body)
    }
    pub(super) fn body(&self,source:&SourceMember)->io::Result<Vec<u8>>{
        self.guard()?;
        let input=self.inputs.iter().find(|i|std::ptr::eq(i.source,source))
            .ok_or_else(||bad("external helper source is outside the compiled ten-member roster"))?;
        self.read(input)
    }
    pub(super) fn guard(&self)->io::Result<()>{
        for d in &self.directories{
            if directory(&d.file)?!=d.identity{return Err(bad("fixed helper input ancestor changed"));}
            if let Some(p)=d.parent{
                let named=opened(&self.directories[p].file,&d.name,libc::O_PATH|libc::O_DIRECTORY)?;
                if directory(&named)?!=d.identity{return Err(bad("fixed helper input named ancestor changed"));}
            }
            if let Some(expected)=&d.expected{if names(&d.file)?!=*expected{return Err(bad("fixed helper input missing or foreign member"));}}
        }
        for input in &self.inputs{self.read(input)?;}
        Ok(())
    }
}

#[cfg(test)]
mod tests{
    use super::*;
    use std::os::unix::fs::{OpenOptionsExt,PermissionsExt,symlink};
    #[test]
    fn external_input_directory_rejects_alias_and_roster_scan_preserves_cursor(){
        let temp=tempfile::tempdir().unwrap();let p=temp.path();fs::create_dir(p.join("actual")).unwrap();
        symlink("actual",p.join("alias")).unwrap();
        let root=File::open(p).unwrap();
        assert!(opened(&root,c"alias",libc::O_PATH|libc::O_DIRECTORY).is_err());
        let first=names(&root).unwrap();assert_eq!(first,names(&root).unwrap());
        fs::write(p.join("unexpected"),b"unrelated").unwrap();assert_ne!(first,names(&root).unwrap());
    }
    #[test]
    fn source_member_guard_rejects_wrong_digest_and_mutated_bytes(){
        let source=MEMBERS.iter().find(|m|m.kind==HelperKind::Saf && m.relative=="helper.apk").unwrap();
        assert!(source.embedded_body().unwrap().is_none());
        assert!(source.verify_body(&vec![0;source.bytes as usize]).is_err());
        let temp=tempfile::tempdir().unwrap();let p=temp.path().join("member");
        fs::write(&p,b"input").unwrap();fs::set_permissions(&p,fs::Permissions::from_mode(0o444)).unwrap();
        let f=fs::OpenOptions::new().read(true).custom_flags(libc::O_NOFOLLOW).open(&p).unwrap();
        let before=f9(&f.metadata().unwrap());fs::rename(&p,temp.path().join("retained")).unwrap();
        fs::write(&p,b"input").unwrap();assert_ne!(before,f9(&fs::metadata(&p).unwrap()));
    }
}
