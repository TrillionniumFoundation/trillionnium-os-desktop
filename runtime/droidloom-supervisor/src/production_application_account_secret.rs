//! Live original-owner account anonymization key. No serde, Debug, Clone,
//! public bytes, path, argv, environment or caller descriptor can supply it.
//! Each use borrows the already admitted request's absolute deadline; this key
//! never creates or extends a work lease.
use super::{Result, reject, require};
use crate::control::application_probe::RuntimeEpoch;
use std::cell::RefCell;
use std::fs::File;
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::fs::MetadataExt;
use std::sync::atomic::{compiler_fence, Ordering};
use std::time::Instant;

pub(crate) struct AccountAnonymityKey {
    bytes: Box<[u8;32]>,
    owner: u32,
    epoch: RefCell<Option<RuntimeEpoch>>,
}
impl Drop for AccountAnonymityKey {
    fn drop(&mut self) {
        for byte in self.bytes.iter_mut() { unsafe { std::ptr::write_volatile(byte,0); } }
        compiler_fence(Ordering::SeqCst);
    }
}
impl AccountAnonymityKey {
    /// Called only when the actual normal broker has bound its owned listener.
    pub(crate) fn new(end:Instant) -> Result<Self> {
        crate::production_host_admission::check_observation_before(end)?;
        require(unsafe { libc::geteuid()==0 && libc::getegid()==0 && libc::getpid()>1 },
            "account key requires its actual original broker")?;
        let mut value=Self { bytes:Box::new([0;32]),owner:unsafe{libc::getpid()} as u32,
            epoch:RefCell::new(None) };
        let mut at=0;
        while at<value.bytes.len() {
            crate::production_host_admission::check_observation_before(end)?;
            let count=unsafe{libc::getrandom(value.bytes[at..].as_mut_ptr().cast(),
                value.bytes.len()-at,libc::GRND_NONBLOCK)};
            if count<0 {
                let error=io::Error::last_os_error();
                if error.kind()==io::ErrorKind::Interrupted { continue; }
                return Err(reject("account comparison key generation failed"));
            }
            require(count>0,"account comparison key generation made no progress")?;
            at+=count as usize;
        }
        crate::production_host_admission::check_observation_before(end)?;
        Ok(value)
    }
    fn owner_before(&self,end:Instant) -> Result<()> {
        crate::production_host_admission::check_observation_before(end)?;
        require(unsafe{libc::getpid()} as u32==self.owner
            && unsafe{libc::geteuid()==0 && libc::getegid()==0},
            "account comparison key owner changed")
    }
    /// The epoch is supplied only by the current actual Ready owner. It cannot
    /// be rebound after framework replacement within the same live listener.
    pub(super) fn bind_epoch(&self,actual:&RuntimeEpoch,end:Instant)->Result<()> {
        self.owner_before(end)?;
        let mut slot=self.epoch.try_borrow_mut()
            .map_err(|_|reject("account comparison key is already borrowed"))?;
        match slot.as_ref() {
            Some(epoch)=>require(epoch==actual,"account comparison key epoch changed")?,
            None=>*slot=Some(actual.clone()),
        }
        Ok(())
    }
    pub(super) fn require_epoch(&self,actual:&RuntimeEpoch,end:Instant)->Result<()> {
        self.owner_before(end)?;
        require(self.epoch.try_borrow().map_err(|_|reject("account comparison key is borrowed"))?
            .as_ref()==Some(actual),"account comparison key has no matching actual epoch")
    }
    pub(super) fn write_creator_pipe(&self,reader:&File,writer:File,end:Instant)->Result<()> {
        self.owner_before(end)?;
        require(self.epoch.try_borrow().map_err(|_|reject("account comparison key is borrowed"))?
            .is_some(),"account comparison key has no actual epoch")?;
        write_one_key(&self.bytes,reader,writer,end)
    }
}
fn write_one_key(bytes:&[u8;32],reader:&File,writer:File,end:Instant)->Result<()> {
    crate::production_host_admission::check_observation_before(end)?;
    let r=reader.metadata()?;let w=writer.metadata()?;
    let rf=unsafe{libc::fcntl(reader.as_raw_fd(),libc::F_GETFL)};
    let wf=unsafe{libc::fcntl(writer.as_raw_fd(),libc::F_GETFL)};
    let mut fs:libc::statfs=unsafe{std::mem::zeroed()};
    require(r.mode()&libc::S_IFMT==libc::S_IFIFO && w.mode()&libc::S_IFMT==libc::S_IFIFO
        && r.dev()==w.dev() && r.ino()==w.ino() && r.nlink()==1 && w.nlink()==1
        && rf>=0 && wf>=0 && rf&libc::O_ACCMODE==libc::O_RDONLY && rf&libc::O_NONBLOCK==0
        && wf&libc::O_ACCMODE==libc::O_WRONLY && wf&libc::O_NONBLOCK!=0
        && unsafe{libc::fstatfs(reader.as_raw_fd(),&mut fs)}==0 && fs.f_type==0x50495045,
        "account key requires an empty original creator pipe")?;
    // No extra pipe ioctl permission: temporarily use nonblocking read while
    // the normal creator is already retired and no query child exists yet.
    require(unsafe{libc::fcntl(reader.as_raw_fd(),libc::F_SETFL,rf|libc::O_NONBLOCK)}==0,
        "account private stdin cannot be checked")?;
    let mut sentinel=0_u8;
    let n=unsafe{libc::read(reader.as_raw_fd(),(&mut sentinel as *mut u8).cast(),1)};
    let error=if n<0 {Some(io::Error::last_os_error().kind())}else{None};
    let restored=unsafe{libc::fcntl(reader.as_raw_fd(),libc::F_SETFL,rf)}==0;
    require(restored && n<0 && error==Some(io::ErrorKind::WouldBlock),
        "account private stdin was not empty")?;
    loop {
        crate::production_host_admission::check_observation_before(end)?;
        // Thirty-two bytes are below PIPE_BUF; no partial streaming or retry
        // after any successful write is permitted.
        let n=unsafe{libc::write(writer.as_raw_fd(),bytes.as_ptr().cast(),bytes.len())};
        if n<0 && io::Error::last_os_error().kind()==io::ErrorKind::Interrupted { continue; }
        require(n==32,"account comparison key could not enter its one private stdin")?;
        break;
    }
    drop(writer); // EOF is part of the exact Java stdin contract.
    crate::production_host_admission::check_observation_before(end)?;
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::{Read,Write};
    use std::os::fd::FromRawFd;
    use std::time::Duration;
    fn pipes()->(File,File) {
        let mut f=[-1;2];assert_eq!(unsafe{libc::pipe2(f.as_mut_ptr(),libc::O_CLOEXEC)},0);
        let writer=unsafe{File::from_raw_fd(f[1])};
        let flags=unsafe{libc::fcntl(writer.as_raw_fd(),libc::F_GETFL)};
        assert_eq!(unsafe{libc::fcntl(writer.as_raw_fd(),libc::F_SETFL,flags|libc::O_NONBLOCK)},0);
        (unsafe{File::from_raw_fd(f[0])},writer)
    }
    #[test]
    fn account_secret_stdin_is_exact_once_and_eof_without_an_apk_pump() {
        let(mut reader,writer)=pipes();let fixture=[0x5a_u8;32];
        write_one_key(&fixture,&reader,writer,Instant::now()+Duration::from_secs(2)).unwrap();
        let mut actual=Vec::new();reader.read_to_end(&mut actual).unwrap();assert_eq!(actual,fixture);
    }
    #[test]
    fn account_secret_stdin_rejects_nonempty_unrelated_or_expired_descriptors() {
        let(reader,mut writer)=pipes();writer.write_all(&[1]).unwrap();
        assert!(write_one_key(&[0;32],&reader,writer,Instant::now()+Duration::from_secs(2)).is_err());
        let(a,_aw)=pipes();let(_b,bw)=pipes();
        assert!(write_one_key(&[0;32],&a,bw,Instant::now()+Duration::from_secs(2)).is_err());
        let(r,w)=pipes();assert!(write_one_key(&[0;32],&r,w,Instant::now()).is_err());
        let(r,w)=pipes();let flags=unsafe{libc::fcntl(w.as_raw_fd(),libc::F_GETFL)};
        assert_eq!(unsafe{libc::fcntl(w.as_raw_fd(),libc::F_SETFL,flags&!libc::O_NONBLOCK)},0);
        assert!(write_one_key(&[0;32],&r,w,Instant::now()+Duration::from_secs(2)).is_err());
    }
}
