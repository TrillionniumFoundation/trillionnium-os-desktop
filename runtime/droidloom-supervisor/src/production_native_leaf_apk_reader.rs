//! One bounded, capability-free APK reader born by the original broker.
//! The ordinary query factory is unchanged. Large reads run in this child;
//! the broker services its one private packet per poll and keeps the PIDFD.
use super::{ApplicationError, Result, external, reject, require};
use super::apk_files::HeldApkFiles;
use super::apk_io;
use super::apk_protocol::{self as protocol, Begin, Copy, Operation, PackageFiles, Sequence};
use super::query_io as helper;
use crate::control::application_probe::ApplicationMetadata;
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::fs::MetadataExt;
use std::os::unix::net::UnixDatagram;
use std::sync::atomic::{AtomicBool,Ordering};
use std::time::{Duration,Instant};

const ARGUMENT: &std::ffi::CStr=c"__production-native-leaf-apk-reader";
pub(crate) const CONTEXT: &[u8]=b"u:r:droidloom_native_leaf_apk_reader:s0";
static RETIREMENT_UNPROVEN:AtomicBool=AtomicBool::new(false);
pub(crate) fn retirement_failed()->bool {RETIREMENT_UNPROVEN.load(Ordering::Acquire)}

#[derive(Serialize,Deserialize)]
#[serde(tag="kind",rename_all="snake_case",deny_unknown_fields)]
enum Request {
    Begin { nonce:[u8;16], begin:Begin, actual:Vec<ApplicationMetadata> },
    Continue { nonce:[u8;16], sequence:u32, operation:Operation },
    Release { nonce:[u8;16], sequence:u32 },
}
#[derive(Debug,Serialize,Deserialize)]
#[serde(tag="kind",rename_all="snake_case",deny_unknown_fields)]
pub(crate) enum Reply {
    Ready { nonce:[u8;16], packages:Vec<PackageFiles> },
    Copy { nonce:[u8;16], sequence:u32, comparison:Copy },
    Guarded { nonce:[u8;16], sequence:u32, full_hash:bool },
    FinishChecked { nonce:[u8;16], sequence:u32 },
    Released { nonce:[u8;16], sequence:u32 },
    Rejected { nonce:[u8;16], sequence:u32, reason:String },
}
impl Reply {
    fn nonce(&self)->[u8;16] {match self {
        Self::Ready{nonce,..}|Self::Copy{nonce,..}|Self::Guarded{nonce,..}
        |Self::FinishChecked{nonce,..}|Self::Released{nonce,..}|Self::Rejected{nonce,..}=>*nonce
    }}
}

/// No Deserialize/Clone/foreign constructor. The real clone3/PIDFD path below
/// is the only constructor; a received comparison cannot recreate this owner.
pub(crate) struct Reader {
    child: helper::Child,
    channel: UnixDatagram,
    original_owner: File,
    nonce:[u8;16],
    end:Instant,
    pending:Option<(Request,Vec<File>)>,
    waiting:bool,
    finished:bool,
    finish_sequence:Option<u32>,
}
pub(crate) struct Event {pub(crate) reply:Reply,pub(crate) files:Vec<File>}
#[derive(Debug,Serialize)]
pub(crate) struct Retirement {
    pid:u32,
    pidfd_device:u64,
    pidfd_inode:u64,
    waitid_code:i32,
    waitid_status:i32,
}
impl Retirement {
    pub(crate) fn comparison(&self)->protocol::RetiredComparison {
        protocol::RetiredComparison {pid:self.pid,pidfd_device:self.pidfd_device,
            pidfd_inode:self.pidfd_inode,waitid_code:self.waitid_code,waitid_status:self.waitid_status}
    }
}
impl Reader {
    // Inputs are source-owned [framework root, init, zygote, framework PIDFD].
    // Only the normal owner's dedicated method creates those four descriptors.
    pub(crate) fn spawn(begin:Begin,actual:Vec<ApplicationMetadata>,inputs:[File;4],nonce:[u8;16])->Result<Self> {
        if retirement_failed(){return Err(ApplicationError::RetirementUnproven);}
        begin.validate().map_err(external)?;
        let roles=begin.scope().roles();
        require(nonce != [0;16] && actual.len()==roles.len()
            && actual.iter().zip(&roles).all(|(m,r)|m.package==r.package && m.user==0 && m.epoch==begin.main().epoch)
            && actual[0].matches_inspection(begin.application()),"APK actual fixed group metadata or nonce differs")?;
        let end=begin.deadline().map_err(external)?;
        helper::own_root_credentials()?;
        helper::mac_context(b"u:r:droidloom_broker:s0")?;
        super::worker::require_wait_semantics()?;
        let executable=helper::above_reserved(&crate::production_host_admission::application_worker_executable().map_err(external)?)?;
        let (channel,child_channel)=apk_io::pair()?;
        let child_channel=helper::above_reserved(&File::from(std::os::fd::OwnedFd::from(child_channel)))?;
        let stdio=helper::fixed_stdio()?;
        let owner_raw=unsafe{libc::syscall(libc::SYS_pidfd_open,libc::getpid(),0_u32)};
        if owner_raw<0 {return Err(io::Error::last_os_error().into());}
        let original_owner=unsafe{File::from_raw_fd(owner_raw as RawFd)};
        let program=filter(Some(executable.as_raw_fd()));
        let fprog=libc::sock_fprog{len:program.len() as u16,filter:program.as_ptr().cast_mut()};
        let argv=[c"droidloom-native-leaf-apk-reader".as_ptr(),ARGUMENT.as_ptr(),std::ptr::null()];
        let environment=[c"LC_ALL=C".as_ptr(),std::ptr::null()];
        let parent=unsafe{libc::getpid()};
        let mut raw_pidfd=-1_i32;
        let args=super::worker::CloneArgs{flags:libc::CLONE_PIDFD as u64,
            pidfd:(&mut raw_pidfd as *mut i32) as u64,exit_signal:libc::SIGCHLD as u64,
            ..super::worker::CloneArgs::default()};
        let mut files=Vec::from(inputs);files.push(original_owner.try_clone()?);
        let mut mask=super::worker::SignalMask::block()?;
        let pid=unsafe{libc::syscall(libc::SYS_clone3,&args,mem::size_of_val(&args))};
        if pid<0 {return Err(io::Error::last_os_error().into());}
        if pid==0 {unsafe{
            helper::bootstrap(helper::HelperRole::NativeLeafApkReader,parent,executable.as_raw_fd(),
                child_channel.as_raw_fd(),stdio.as_raw_fd(),argv.as_ptr(),environment.as_ptr(),&fprog)
        }}
        if raw_pidfd<0 {RETIREMENT_UNPROVEN.store(true,Ordering::Release);return Err(ApplicationError::RetirementUnproven);}
        let child=helper::Child{pid:pid as u32,pidfd:Some(unsafe{File::from_raw_fd(raw_pidfd)}),terminal:None};
        drop(child_channel);
        let mut value=Self{child,channel,original_owner,nonce,end,
            pending:Some((Request::Begin{nonce,begin,actual},files)),waiting:false,finished:false,finish_sequence:None};
        let checked=(||{
            mask.restore()?;
            let actual=helper::pidfd_info(value.child.pidfd.as_ref().unwrap())?;
            require(actual.pid==value.child.pid && actual.ppid==parent as u32,"APK reader is not the original direct child")?;
            require(Instant::now()<end,"APK original end elapsed during birth")
        })();
        if let Err(error)=checked {value.retire()?;return Err(error);}
        Ok(value)
    }
    pub(crate) fn request(&mut self,sequence:u32,operation:Operation)->Result<()> {
        require(!self.finished && self.finish_sequence.is_none() && !self.waiting && self.pending.is_none() && sequence>0
            && sequence<=protocol::MAX_REQUESTS && Instant::now()<self.end,"APK concurrent, terminal or expired operation")?;
        self.pending=Some((Request::Continue{nonce:self.nonce,sequence,operation},Vec::new()));
        Ok(())
    }
    /// One nonblocking send or one nonblocking receive; never hashes APK bytes.
    pub(crate) fn poll(&mut self)->Result<Option<Event>> {
        require(Instant::now()<self.end,"APK original deadline elapsed")?;
        helper::alive(&self.original_owner)?;
        if let Some((request,files))=&self.pending {
            let fds=files.iter().map(AsRawFd::as_raw_fd).collect::<Vec<_>>();
            if apk_io::send(self.channel.as_raw_fd(),request,&fds)? {
                self.pending=None;self.waiting=true;
            }
            return Ok(None);
        }
        if !self.waiting {return Ok(None);}
        let packet=match apk_io::receive::<Reply>(self.channel.as_raw_fd())?{
            Some(packet)=>packet,
            None=>{
                if !self.child.observe()? {return Ok(None);}
                // A terminal child can have queued its final packet between
                // recv and waitid. Drain that one packet before rejecting it.
                apk_io::receive::<Reply>(self.channel.as_raw_fd())?
                    .ok_or_else(||reject("APK reader ended without its expected terminal response"))?
            }
        };
        require(packet.peer.pid==self.child.pid as i32 && packet.peer.uid==0 && packet.peer.gid==0
            && packet.value.nonce()==self.nonce,"APK private response is not the original child")?;
        require(packet.files.len()==usize::from(matches!(&packet.value,Reply::Copy{..})),"APK private response descriptor count")?;
        if let Reply::Copy{comparison,..}=&packet.value {comparison.validate().map_err(external)?;}
        if let Reply::FinishChecked{sequence,..}=&packet.value {self.finish_sequence=Some(*sequence);}
        if let Reply::Released{sequence,..}=&packet.value {
            require(Some(*sequence)==self.finish_sequence,"APK release sequence changed")?;
            self.finished=true;
        }
        self.waiting=false;
        Ok(Some(Event{reply:packet.value,files:packet.files}))
    }
    /// Called only after actual final normal PM/Main bookends. Original APK
    /// FDs remain in the child until this private, source-owned release.
    pub(crate) fn release(&mut self)->Result<()> {
        let sequence=self.finish_sequence.ok_or_else(||reject("APK finish hash is incomplete"))?;
        require(!self.finished && !self.waiting && self.pending.is_none() && Instant::now()<self.end,
            "APK final release is not in its original live interval")?;
        self.pending=Some((Request::Release{nonce:self.nonce,sequence},Vec::new()));
        Ok(())
    }
    pub(crate) fn reaped(&mut self)->Result<Option<Retirement>> {
        require(self.finished,"APK retirement cannot precede real full-hash finish")?;
        if !self.child.observe()? {return Ok(None);}
        require(self.child.terminal==Some((libc::CLD_EXITED,0)),"APK reader did not retire successfully")?;
        let node=self.child.pidfd.as_ref().ok_or(ApplicationError::RetirementUnproven)?.metadata()?;
        Ok(Some(Retirement{pid:self.child.pid,pidfd_device:node.dev(),pidfd_inode:node.ino(),
            waitid_code:libc::CLD_EXITED,waitid_status:0}))
    }
    pub(crate) fn retire(&mut self)->Result<()> {
        self.pending=None;
        if self.child.retire().is_err(){
            RETIREMENT_UNPROVEN.store(true,Ordering::Release);
            return Err(ApplicationError::RetirementUnproven);
        }
        Ok(())
    }
}
impl Drop for Reader {
    fn drop(&mut self) {
        if self.retire().is_err(){RETIREMENT_UNPROVEN.store(true,Ordering::Release);}
    }
}

fn live_inputs(begin:&Begin,root:&File,processes:&[File;3],owner:&File,parent:i32)->Result<()> {
    helper::alive(owner)?;
    require(unsafe{libc::getppid()}==parent,"APK original parent changed")?;
    let root_meta=root.metadata()?;
    let main=begin.main();
    require(root_meta.is_dir() && (root_meta.dev(),root_meta.ino())==(main.framework.root.device,main.framework.root.inode),
        "APK original framework root descriptor differs")?;
    for (file,expected) in processes.iter().zip([&main.init,&main.zygote,&main.framework]) {
        helper::alive(file)?;
        let info=helper::pidfd_info(file)?;
        let meta=file.metadata()?;
        require(info.pid==expected.host_pid && info.ppid==expected.parent_host_pid
            && (meta.dev(),meta.ino())==(expected.pidfd.device,expected.pidfd.inode),
            "APK original Main PIDFD/parent differs")?;
    }
    require(Instant::now()<begin.deadline().map_err(external)?,"APK original deadline")
}


fn channel_kind()->Result<()>{
    for (option,expected) in [(libc::SO_TYPE,libc::SOCK_SEQPACKET),(libc::SO_DOMAIN,libc::AF_UNIX)]{
        let mut value=0_i32;
        let mut length=mem::size_of_val(&value) as libc::socklen_t;
        if unsafe{libc::getsockopt(3,libc::SOL_SOCKET,option,(&mut value as *mut i32).cast(),&mut length)}!=0{
            return Err(io::Error::last_os_error().into());
        }
        require(length as usize==mem::size_of_val(&value)&&value==expected,
            "APK private channel type or local domain differs")?;
    }
    let mut label=[0_u8;256];
    let mut length=label.len() as libc::socklen_t;
    if unsafe{libc::getsockopt(3,libc::SOL_SOCKET,libc::SO_PEERSEC,label.as_mut_ptr().cast(),&mut length)}!=0{
        return Err(io::Error::last_os_error().into());
    }
    // Selected 6.18 returns the first AppArmor getpeersec_stream hook without
    // NUL/LF. SELinux is checked separately before birth and in this reader;
    // the original SCM credentials and owner PIDFD are checked for each packet.
    const BROKER_PEERSEC:&[u8]=b"droidloom-production-broker (enforce)";
    require(length as usize==BROKER_PEERSEC.len() && &label[..length as usize]==BROKER_PEERSEC,
        "APK private channel does not have the exact normal broker AppArmor peer")
}

pub(super) fn entry()->Result<()> {
    helper::own_root_credentials()?;
    helper::verify_fixed_stdio()?;
    helper::native_leaf_apk_context()?;
    helper::empty_capabilities()?;
    require(unsafe{libc::prctl(libc::PR_GET_NO_NEW_PRIVS,0,0,0,0)}==1,"APK reader lost NNP")?;
    drop(crate::production_host_admission::application_worker_executable().map_err(external)?);
    channel_kind()?;
    // Remove the sole fresh-image exec exception before any plan is consumed.
    helper::install_filter(&filter(None))?;
    let parent=unsafe{libc::getppid()};
    require(parent>1,"APK reader has no normal parent")?;
    let packet=apk_io::receive_before::<Request>(3,Instant::now()+Duration::from_secs(5))?;
    let Request::Begin{nonce,begin,actual}=packet.value else {return Err(reject("APK first private phase differs"));};
    require(nonce !=[0;16] && packet.files.len()==5,"APK private start descriptors differ")?;
    let mut files=packet.files;
    let owner=files.pop().unwrap();let framework=files.pop().unwrap();let zygote=files.pop().unwrap();
    let init=files.pop().unwrap();let root=files.pop().unwrap();
    helper::parent_identity(&owner,packet.peer,parent)?;
    begin.validate().map_err(external)?;
    let end=begin.deadline().map_err(external)?;
    let processes=[init,zygote,framework];
    live_inputs(&begin,&root,&processes,&owner,parent)?;
    let body_end=end.min(Instant::now()+protocol::BODY_CAP);
    let held=HeldApkFiles::capture(root.try_clone()?,&actual,&begin,body_end).map_err(external)?;
    let mut sequence=Sequence::begin(nonce,held.len()).map_err(external)?;
    apk_io::send_before(3,&Reply::Ready{nonce,packages:held.packages()},&[],end)?;
    let mut finish_sequence=None;
    loop {
        let packet=apk_io::receive_before::<Request>(3,end)?;
        helper::parent_identity(&owner,packet.peer,parent)?;
        require(packet.files.is_empty(),"APK subsequent phase cannot accept descriptors")?;
        if let Some(number)=finish_sequence {
            let Request::Release{nonce:received,sequence:released}=packet.value else {
                return Err(reject("APK final hashes permit only the original parent release"));
            };
            require(received==nonce && released==number,"APK final release binding differs")?;
            live_inputs(&begin,&root,&processes,&owner,parent)?;
            held.guard(false,end).map_err(external)?;
            apk_io::send_before(3,&Reply::Released{nonce,sequence:number},&[],end)?;
            return Ok(());
        }
        let Request::Continue{nonce:received,sequence:number,operation}=packet.value else {
            return Err(reject("APK private begin cannot be replayed"));
        };
        let result=(||->Result<(Reply,Option<File>)>{
            let ordinal=sequence.accept(received,number,operation).map_err(external)?;
            live_inputs(&begin,&root,&processes,&owner,parent)?;
            let body_end=end.min(Instant::now()+protocol::BODY_CAP);
            let body_end=operation.package_end().map_err(external)?.map_or(body_end,|v|v.min(body_end));
            let out=match operation {
                Operation::NextCopy=>{
                    let (comparison,file)=held.copy(ordinal.ok_or_else(||reject("APK ordinal absent"))?,body_end).map_err(external)?;
                    (Reply::Copy{nonce,sequence:number,comparison},Some(file))
                }
                Operation::Guard|Operation::Refresh|Operation::PackageRead{..}=>{
                    let full_hash=operation==Operation::Refresh;
                    held.guard(full_hash,body_end).map_err(external)?;
                    (Reply::Guarded{nonce,sequence:number,full_hash},None)
                }
                Operation::Finish=>{
                    held.guard(true,body_end).map_err(external)?;
                    (Reply::FinishChecked{nonce,sequence:number},None)
                }
            };
            live_inputs(&begin,&root,&processes,&owner,parent)?;
            Ok(out)
        })();
        match result {
            Ok((reply,file))=>{
                let fds=file.iter().map(AsRawFd::as_raw_fd).collect::<Vec<_>>();
                apk_io::send_before(3,&reply,&fds,end)?;
                drop(file);
                if operation==Operation::Finish {finish_sequence=Some(number);}
            }
            Err(error)=>{
                sequence.fail();
                let reason=error.to_string().chars().take(2048).collect();
                apk_io::send_before(3,&Reply::Rejected{nonce,sequence:number,reason},&[],end)?;
                return Err(error);
            }
        }
    }
}

// No namespace entry, process/socket creation or arbitrary exec. Source read
// paths use openat2(IN_ROOT). Dedicated MAC permits writes only to the copy.
fn filter(executable:Option<RawFd>)->Vec<libc::sock_filter> {
    let ins=|code,jt,jf,k|libc::sock_filter{code,jt,jf,k};
    let deny=0x0005_0000|libc::EPERM as u32;let allow=0x7fff_0000;
    let mut f=vec![ins(0x20,0,0,4),ins(0x15,1,0,0xc000_003e),ins(0x06,0,0,0x8000_0000),
        ins(0x20,0,0,0),ins(0x35,0,1,0x4000_0000),ins(0x06,0,0,deny)];
    let mut narrow=|syscall:libc::c_long,args:&[(u32,u64)]|{
        let mut body=Vec::new();
        for (index,value) in args {
            for (offset,part) in [(16+index*8,*value as u32),(20+index*8,(*value>>32) as u32)] {
                body.extend([ins(0x20,0,0,offset),ins(0x15,1,0,part),ins(0x06,0,0,deny)]);
            }
        }
        body.push(ins(0x06,0,0,allow));
        f.push(ins(0x15,0,body.len() as u8,syscall as u32));f.extend(body);f.push(ins(0x20,0,0,0));
    };
    // Existing typed MAC self observer: CURRENT100, LSM_FLAG_SINGLE only.
    // The closed EXEC setter runs in bootstrap before this filter is installed.
    narrow(459,&[(0,100),(3,1)]);
    narrow(libc::SYS_recvmsg,&[(0,3)]);
    narrow(libc::SYS_sendmsg,&[(0,3)]);
    narrow(libc::SYS_ioctl,&[(1,0xc050_ff0b)]);
    narrow(libc::SYS_memfd_create,&[(1,(libc::MFD_CLOEXEC|libc::MFD_ALLOW_SEALING) as u64)]);
    if let Some(fd)=executable {narrow(libc::SYS_execveat,&[(0,fd as u64),(4,libc::AT_EMPTY_PATH as u64)]);}
    for syscall in [
        libc::SYS_read,libc::SYS_write,libc::SYS_close,libc::SYS_fstat,libc::SYS_newfstatat,
        libc::SYS_statx,libc::SYS_fstatfs,libc::SYS_openat,libc::SYS_openat2,libc::SYS_readlink,
        libc::SYS_readlinkat,libc::SYS_mmap,libc::SYS_mprotect,libc::SYS_munmap,libc::SYS_brk,
        libc::SYS_madvise,libc::SYS_rt_sigaction,libc::SYS_rt_sigprocmask,libc::SYS_rt_sigreturn,
        libc::SYS_arch_prctl,libc::SYS_prlimit64,libc::SYS_getrlimit,libc::SYS_getrandom,
        libc::SYS_set_tid_address,libc::SYS_set_robust_list,libc::SYS_rseq,libc::SYS_access,
        libc::SYS_faccessat,libc::SYS_faccessat2,libc::SYS_futex,libc::SYS_clock_gettime,
        libc::SYS_clock_nanosleep,libc::SYS_nanosleep,libc::SYS_poll,libc::SYS_ppoll,libc::SYS_fcntl,
        libc::SYS_getpid,libc::SYS_gettid,libc::SYS_getppid,libc::SYS_getuid,libc::SYS_geteuid,libc::SYS_getgid,
        libc::SYS_getegid,libc::SYS_getgroups,libc::SYS_capget,libc::SYS_prctl,libc::SYS_getsockopt,
        libc::SYS_fgetxattr,libc::SYS_lseek,libc::SYS_pread64,libc::SYS_pwrite64,libc::SYS_fchmod,
        libc::SYS_sched_getaffinity,libc::SYS_exit_group,libc::SYS_exit,
    ] {f.extend([ins(0x15,0,1,syscall as u32),ins(0x06,0,0,allow)]);}
    f.push(ins(0x06,0,0,deny));f
}

#[cfg(test)]
mod tests{
    use super::*;
    fn decision(program:&[libc::sock_filter],syscall:u32,attr:u64,flags:u64)->u32{
        let mut input=[0_u32;16];input[0]=syscall;input[1]=0xc000_003e;
        input[4]=attr as u32;input[5]=(attr>>32)as u32;
        input[10]=flags as u32;input[11]=(flags>>32)as u32;
        let mut pc=0_usize;let mut a=0_u32;
        for _ in 0..program.len()+1{
            let i=program.get(pc).expect("filter instruction bound");
            match i.code{
                0x20=>{assert_eq!(i.k%4,0);a=input[i.k as usize/4];pc+=1;}
                0x15=>pc+=1+if a==i.k{i.jt}else{i.jf} as usize,
                0x35=>pc+=1+if a>=i.k{i.jt}else{i.jf} as usize,
                0x06=>return i.k,
                _=>panic!("unrecognized filter instruction"),
            }
        }
        panic!("filter did not terminate")
    }
    #[test]
    fn native_leaf_apk_reader_filter_admits_only_typed_current_read(){
        let deny=0x0005_0000|libc::EPERM as u32;let allow=0x7fff_0000;
        for program in [filter(Some(64)),filter(None)]{
            assert_eq!(decision(&program,459,100,1),allow);
            assert_eq!(decision(&program,libc::SYS_gettid as u32,0,0),allow);
            for(attr,flags)in[(101,1),(102,1),(100,0),(100,2),(100+(1_u64<<32),1),(100,1+(1_u64<<32))]{
                assert_eq!(decision(&program,459,attr,flags),deny);
            }
            assert_eq!(decision(&program,460,101,1),deny);
            assert_eq!(decision(&program,459|0x4000_0000,100,1),deny);
        }
    }
}
