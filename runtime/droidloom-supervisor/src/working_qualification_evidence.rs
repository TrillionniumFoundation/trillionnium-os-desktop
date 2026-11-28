//! Protected records of this actual normal owner. These files preserve outcomes;
//! they are never accepted as constructors for runtime or Complete authority.
use super::boot::BootOwner;
use crate::native_hardware_label as held;
use serde_json::{Value,json};
use sha2::{Digest,Sha256};
use std::{ffi::CString,fs::{File,OpenOptions},io::{self,Write},
    os::{fd::AsRawFd,unix::fs::{FileExt,MetadataExt,OpenOptionsExt}},
    path::{Path,PathBuf}};
const LABEL:&[u8]=b"u:object_r:p4_linux_working_evidence_t:s0";
fn reject(s:&str)->io::Error{io::Error::new(io::ErrorKind::PermissionDenied,s)}
fn node(f:&File)->io::Result<[u64;5]> {
    let m=f.metadata()?;Ok([m.dev(),m.ino(),u64::from(m.mode()),u64::from(m.uid()),u64::from(m.gid())])
}
pub(super) struct Evidence { root:PathBuf, file:File, identity:[u64;5] }
impl Evidence {
    pub(super) fn open(boot:&BootOwner)->io::Result<Self> {
        boot.guard()?;
        let root=boot.config().runtime_evidence_directory();
        let mut parent=held::path_at(libc::AT_FDCWD,c"/")?;
        held::directory(&parent)?;
        for component in root.components().skip(1) {
            let std::path::Component::Normal(name)=component else{return Err(reject("working evidence path differs"));};
            use std::os::unix::ffi::OsStrExt;
            parent=held::path_at(parent.as_raw_fd(),&CString::new(name.as_bytes()).map_err(io::Error::other)?)?;
            held::directory(&parent)?;
        }
        let file=OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY|libc::O_NOFOLLOW|libc::O_CLOEXEC).open(&root)?;
        let identity=node(&file)?;
        if identity!=node(&parent)? || identity[2..]!=[u64::from(libc::S_IFDIR|0o700),0,0]
            || held::label(&file)?!=LABEL {
            return Err(reject("working evidence is not the prepared root-only directory"));
        }
        let value=Self{root,file,identity};value.guard()?;Ok(value)
    }
    pub(super) fn guard(&self)->io::Result<()> {
        let named=OpenOptions::new().read(true).custom_flags(libc::O_DIRECTORY|libc::O_NOFOLLOW|libc::O_CLOEXEC).open(&self.root)?;
        // Record births change nlink/times legitimately. The source-owned stage
        // retains the root inode/mode/owner, not an obsolete cold full F9.
        if node(&named)?!=self.identity || node(&self.file)?!=self.identity
            || held::label(&named)?!=LABEL || held::label(&self.file)?!=LABEL {
            return Err(reject("working evidence root identity or label changed"));
        }
        Ok(())
    }
    pub(super) fn root(&self)->&Path { &self.root }
    pub(super) fn create(&self,name:&str)->io::Result<File> {
        if !matches!(name,"OWNER-START.json"|"OWNER-FAILURE.json"|"PREPARATION-OWNER-RESULT.json"
            |"PREPARATION.stdout"|"PREPARATION.stderr"|"PHYSICAL-OWNER-RESULT.json") {
            return Err(reject("working evidence output is not a fixed source name"));
        }
        self.guard()?;
        let path=format!("/proc/self/fd/{}/{}",self.file.as_raw_fd(),name);
        let file=OpenOptions::new().read(true).write(true).create_new(true).mode(0o600)
            .custom_flags(libc::O_NOFOLLOW|libc::O_CLOEXEC).open(path)?;
        let m=file.metadata()?;
        if m.mode()!=libc::S_IFREG|0o600 || m.uid()!=0 || m.gid()!=0 || m.nlink()!=1
            || held::label(&file)?!=LABEL {
            return Err(reject("working output is not a new protected normal inode"));
        }
        self.guard()?;Ok(file)
    }
    pub(super) fn sync(&self)->io::Result<()> {self.file.sync_all()?;self.guard()}
    pub(super) fn record(&self,name:&str,value:&Value)->io::Result<Value> {
        let mut raw=serde_json::to_vec_pretty(value)?;raw.push(b'\n');
        if raw.len()>1024*1024{return Err(reject("working owner record exceeds fixed bound"));}
        let mut f=self.create(name)?;f.write_all(&raw)?;f.sync_all()?;
        let mut actual=vec![0;raw.len()];
        f.read_exact_at(&mut actual,0)?;
        let m=f.metadata()?;
        let named=std::fs::symlink_metadata(self.root.join(name))?;
        if actual!=raw || f.read_at(&mut [0],raw.len()as u64)?!=0 || m.len()!=raw.len()as u64
            || (m.dev(),m.ino(),m.mode(),m.uid(),m.gid(),m.nlink(),m.len(),m.mtime(),m.mtime_nsec(),m.ctime(),m.ctime_nsec())
                !=(named.dev(),named.ino(),named.mode(),named.uid(),named.gid(),named.nlink(),named.len(),named.mtime(),named.mtime_nsec(),named.ctime(),named.ctime_nsec()) {
            return Err(reject("working owner record full readback or inode changed"));
        }
        self.sync()?;
        Ok(json!({"path":self.root.join(name),"bytes":raw.len(),"sha256":format!("{:x}",Sha256::digest(&raw))}))
    }
}
