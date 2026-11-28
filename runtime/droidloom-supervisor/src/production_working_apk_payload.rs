//! Five fixed normal public helpers copied by one original-broker-owned creator.
//! The broker never creates, opens for write, or relabels an APK payload.
//! Only the separately exec'd, capability-free creator has that default FILE type.
use super::{ApplicationError,Result,external,reject,require};
use super::{apk_io,query_io as helper};
use crate::control::apk_payload;
use crate::native_leaf_fixture_material::{NativeLeafFixtureKind,NativeLeafFixtureMaterial};
use crate::prebuilt_native_helpers::PrebuiltIhgMaterial;
use serde::{Deserialize,Serialize};
use serde_json::{Value,json};
use sha2::{Digest,Sha256};
use std::{fs::File,io,mem,os::{fd::{AsRawFd,FromRawFd,RawFd},unix::fs::{FileExt,MetadataExt}},
    sync::atomic::{AtomicBool,Ordering},time::{Duration,Instant}};

const ARGUMENT:&std::ffi::CStr=c"__production-working-apk-payload-creator";
const CONTEXT:&[u8]=b"u:r:droidloom_working_apk_payload_creator:s0";
const LIMIT:Duration=Duration::from_secs(120);
const RETIRE_RESERVE:Duration=Duration::from_secs(3);
pub(super) const MAX_MATERIAL_BYTES:u64=139532;
static RETIREMENT_UNPROVEN:AtomicBool=AtomicBool::new(false);
pub(crate) fn retirement_failed()->bool{RETIREMENT_UNPROVEN.load(Ordering::Acquire)}

#[derive(Clone,Copy,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(rename_all="snake_case")]
pub(crate) enum WorkingPayloadKind{
    DocumentsSaf,DocumentsFeatures,Ihg,GalleryRotation,GalleryVideo,
}
impl WorkingPayloadKind{
    fn fixture(self)->Option<NativeLeafFixtureKind>{
        Some(match self{
            Self::DocumentsSaf=>NativeLeafFixtureKind::DocumentsSaf,
            Self::DocumentsFeatures=>NativeLeafFixtureKind::DocumentsFeatures,
            Self::GalleryRotation=>NativeLeafFixtureKind::GalleryRotation,
            Self::GalleryVideo=>NativeLeafFixtureKind::GalleryVideo,
            Self::Ihg=>return None,
        })
    }
    pub(crate) fn apk_bytes(self)->u64{
        self.fixture().map_or(crate::native_ihg_helper::APK_BYTES,NativeLeafFixtureKind::apk_bytes)
    }
    pub(crate) fn apk_sha256(self)->&'static str{
        self.fixture().map_or(crate::native_ihg_helper::APK_SHA256,NativeLeafFixtureKind::apk_sha256)
    }
}
enum Material{Fixture(NativeLeafFixtureMaterial),Ihg(PrebuiltIhgMaterial)}
impl Material{
    fn capture(kind:WorkingPayloadKind,retention_end:Instant,operation_end:Instant)->Result<Self>{
        Ok(match kind.fixture(){
            Some(fixture)=>Self::Fixture(NativeLeafFixtureMaterial::capture_before(fixture,retention_end,operation_end)?),
            None=>Self::Ihg(PrebuiltIhgMaterial::capture_before(retention_end,operation_end)?),
        })
    }
    fn guard(&self,end:Instant)->Result<()>{
        match self{Self::Fixture(v)=>v.guard(end)?,Self::Ihg(v)=>v.guard(end)?};Ok(())
    }
    fn file(&self,end:Instant)->Result<&File>{
        Ok(match self{Self::Fixture(v)=>v.apk_file(end)?,Self::Ihg(v)=>v.apk_file(end)?})
    }
    fn comparison(&self)->Value{
        match self{Self::Fixture(v)=>v.comparison(),Self::Ihg(v)=>v.comparison()}
    }
}
#[derive(Clone,Copy,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(rename_all="snake_case")]
enum Phase{Create,Created}
#[derive(Clone,Copy,Debug,Eq,PartialEq,Serialize,Deserialize)]
#[serde(deny_unknown_fields)]
struct Wire{phase:Phase,kind:WorkingPayloadKind,nonce:[u8;16],deadline_ns:u64}
fn remaining_end(wire:Wire)->Result<Instant>{
    require(wire.nonce!=[0;16],"payload original nonce absent")?;
    let started=Instant::now();
    let left=wire.deadline_ns.checked_sub(super::protocol::monotonic_ns()?)
        .ok_or_else(||reject("payload original end expired"))?;
    require(left>0&&u128::from(left)<=LIMIT.as_nanos(),"payload original end exceeds source limit")?;
    Ok(started+Duration::from_nanos(left))
}
fn before(end:Instant)->Result<()>{
    require(Instant::now()<end,"payload original creation or owner deadline elapsed")
}
fn identity(file:&File)->Result<[u64;11]>{
    let m=file.metadata()?;
    Ok([m.dev(),m.ino(),m.mode()as u64,m.uid()as u64,m.gid()as u64,m.nlink(),m.len(),
        m.mtime()as u64,m.mtime_nsec()as u64,m.ctime()as u64,m.ctime_nsec()as u64])
}
fn full_hash(file:&File,bytes:u64,end:Instant)->Result<String>{
    before(end)?;
    let original=identity(file)?;
    require(original[6]==bytes&&bytes>4&&bytes<=MAX_MATERIAL_BYTES,"fixed payload length differs")?;
    let mut buffer=[0_u8;65536];let mut done=0;let mut hash=Sha256::new();
    while done<bytes{
        before(end)?;
        let n=(bytes-done).min(buffer.len()as u64)as usize;
        file.read_exact_at(&mut buffer[..n],done)?;hash.update(&buffer[..n]);done+=n as u64;
    }
    require(file.read_at(&mut[0_u8],bytes)?==0&&identity(file)?==original,
        "fixed payload has extra bytes or changed its original inode")?;
    before(end)?;Ok(format!("{:x}",hash.finalize()))
}
fn source(file:&File,kind:WorkingPayloadKind,end:Instant)->Result<()>{
    let m=file.metadata()?;
    let flags=unsafe{libc::fcntl(file.as_raw_fd(),libc::F_GETFL)};
    require(m.is_file()&&m.nlink()==1&&m.uid()==0&&m.gid()==0&&m.mode()&0o6022==0
        &&m.mode()&0o111==0&&flags>=0&&flags&(libc::O_ACCMODE|libc::O_PATH)==libc::O_RDONLY,
        "payload source is not the fixed protected readonly public material")?;
    require(full_hash(file,kind.apk_bytes(),end)?==kind.apk_sha256(),
        "payload original bytes are not this source-owned helper")?;
    Ok(())
}
fn payload(file:&File,kind:WorkingPayloadKind,end:Instant)->Result<()>{
    apk_payload::validate(file,&[kind.apk_bytes()]).map_err(external)?;
    apk_payload::validate_production_context(file).map_err(external)?;
    require(full_hash(file,kind.apk_bytes(),end)?==kind.apk_sha256(),"complete readonly payload differs")?;
    Ok(())
}

/// This owner can only be obtained after its actual direct child was reaped.
pub(crate) struct Retirement{pid:u32,pidfd:File,node:(u64,u64),code:i32,status:i32}
impl Retirement{
    fn guard(&self)->Result<()>{
        let m=self.pidfd.metadata()?;
        require((m.dev(),m.ino())==self.node&&self.pid>1
            &&self.code==libc::CLD_EXITED&&self.status==0,"payload original retirement witness changed")
    }
    pub(crate) fn comparison(&self)->Value{
        json!({"pid":self.pid,"pidfd_device":self.node.0,"pidfd_inode":self.node.1,
            "waitid_code":self.code,"waitid_status":self.status,"actual_reaped":true})
    }
}
/// No Deserialize, Clone, public constructor or caller-selected input exists.
pub(crate) struct CreatedPayload{
    kind:WorkingPayloadKind,file:File,material:Material,retirement:Retirement,end:Instant,
}
impl CreatedPayload{
    pub(crate) fn guard(&self,end:Instant)->Result<()>{
        require(end<=self.end,"payload owner end cannot be renewed")?;before(end)?;
        self.retirement.guard()?;self.material.guard(end)?;
        payload(&self.file,self.kind,end)?;
        self.material.guard(end)?;self.retirement.guard()
    }
    pub(crate) fn payload_file(&self,end:Instant)->Result<&File>{self.guard(end)?;Ok(&self.file)}
    pub(crate) fn retirement(&self)->&Retirement{&self.retirement}
    pub(crate) fn comparison(&self)->Value{
        json!({"schema":"droidloom.working-apk-payload.v1","kind":self.kind,
            "apk_bytes":self.kind.apk_bytes(),"apk_sha256":self.kind.apk_sha256(),
            "material":self.material.comparison(),"creator":self.retirement.comparison(),
            "creation_limit_seconds":120,"retirement_reserve_seconds":3,
            "caller_path_accepted":false,"broker_created_payload":false})
    }
}
fn poison(child:&mut helper::Child)->ApplicationError{
    RETIREMENT_UNPROVEN.store(true,Ordering::Release);
    // Do not invoke the legacy helper's independent cleanup timer after this
    // source owner's end. Retain the actual PIDFD on unproven retirement.
    if let Some(fd)=child.pidfd.take(){mem::forget(fd);}
    ApplicationError::RetirementUnproven
}
fn retire_before(child:&mut helper::Child,end:Instant)->Result<()>{
    if child.terminal.is_some(){return Ok(());}
    match child.observe(){Ok(true)=>return Ok(()),Err(_)=>return Err(poison(child)),Ok(false)=>{}}
    let fd=child.pidfd.as_ref().ok_or(ApplicationError::RetirementUnproven)?.as_raw_fd();
    if unsafe{libc::syscall(libc::SYS_pidfd_send_signal,fd,libc::SIGKILL,std::ptr::null::<libc::siginfo_t>(),0_u32)}!=0
        &&io::Error::last_os_error().raw_os_error()!=Some(libc::ESRCH){return Err(poison(child));}
    loop{
        match child.observe(){Ok(true)=>return Ok(()),Err(_)=>return Err(poison(child)),Ok(false)=>{}}
        if Instant::now()>=end{return Err(poison(child));}
        let mut p=libc::pollfd{fd,events:libc::POLLIN,revents:0};
        let n=unsafe{libc::poll(&mut p,1,end.saturating_duration_since(Instant::now()).as_millis().clamp(1,10)as i32)};
        if n<0&&io::Error::last_os_error().kind()!=io::ErrorKind::Interrupted{return Err(poison(child));}
    }
}
pub(crate) fn create(kind:WorkingPayloadKind,original_end:Instant)->Result<CreatedPayload>{
    if retirement_failed(){return Err(ApplicationError::RetirementUnproven);}
    let end=original_end.min(Instant::now()+LIMIT);
    let body_end=end.checked_sub(RETIRE_RESERVE).ok_or_else(||reject("payload creation window is absent"))?;
    before(body_end)?;
    helper::own_root_credentials()?;helper::mac_context(b"u:r:droidloom_broker:s0")?;
    super::worker::require_wait_semantics()?;
    let material=Material::capture(kind,original_end,body_end)?;
    source(material.file(body_end)?,kind,body_end)?;
    let executable=helper::above_reserved(&crate::production_host_admission::application_worker_executable().map_err(external)?)?;
    let(channel,child_channel)=apk_io::pair()?;
    let child_channel=helper::above_reserved(&File::from(std::os::fd::OwnedFd::from(child_channel)))?;
    let stdio=helper::fixed_stdio()?;
    let owner_raw=unsafe{libc::syscall(libc::SYS_pidfd_open,libc::getpid(),0_u32)};
    if owner_raw<0{return Err(io::Error::last_os_error().into());}
    let owner=unsafe{File::from_raw_fd(owner_raw as RawFd)};helper::alive(&owner)?;
    let mut nonce=[0_u8;16];let mut offset=0;
    while offset<nonce.len(){
        let n=unsafe{libc::getrandom(nonce[offset..].as_mut_ptr().cast(),nonce.len()-offset,0)};
        if n<0{let e=io::Error::last_os_error();if e.kind()==io::ErrorKind::Interrupted{continue;}return Err(e.into());}
        require(n>0,"payload original nonce unavailable")?;offset+=n as usize;
    }
    require(nonce!=[0;16],"payload nonce cannot be all zero")?;
    before(body_end)?;
    let wire=Wire{phase:Phase::Create,kind,nonce,deadline_ns:super::protocol::monotonic_ns()?
        .checked_add(end.saturating_duration_since(Instant::now()).as_nanos()as u64)
        .ok_or_else(||reject("payload deadline overflow"))?};
    let program=filter(Some(executable.as_raw_fd()));
    let fprog=libc::sock_fprog{len:program.len()as u16,filter:program.as_ptr().cast_mut()};
    let argv=[c"droidloom-working-apk-payload-creator".as_ptr(),ARGUMENT.as_ptr(),std::ptr::null()];
    let environment=[c"LC_ALL=C".as_ptr(),std::ptr::null()];
    let parent=unsafe{libc::getpid()};let mut raw_pidfd=-1_i32;
    let args=super::worker::CloneArgs{flags:libc::CLONE_PIDFD as u64,pidfd:(&mut raw_pidfd as *mut i32)as u64,
        exit_signal:libc::SIGCHLD as u64,..super::worker::CloneArgs::default()};
    let mut mask=super::worker::SignalMask::block()?;
    let pid=unsafe{libc::syscall(libc::SYS_clone3,&args,mem::size_of_val(&args))};
    if pid<0{return Err(io::Error::last_os_error().into());}
    if pid==0{unsafe{helper::bootstrap(helper::HelperRole::WorkingApkPayloadCreator,parent,executable.as_raw_fd(),
        child_channel.as_raw_fd(),stdio.as_raw_fd(),argv.as_ptr(),environment.as_ptr(),&fprog)}}
    if raw_pidfd<0{RETIREMENT_UNPROVEN.store(true,Ordering::Release);return Err(ApplicationError::RetirementUnproven);}
    let mut child=helper::Child{pid:pid as u32,pidfd:Some(unsafe{File::from_raw_fd(raw_pidfd)}),terminal:None};
    drop(child_channel);
    let operation=(||->Result<CreatedPayload>{
        mask.restore()?;
        let actual=helper::pidfd_info(child.pidfd.as_ref().unwrap())?;
        require(actual.pid==child.pid&&actual.ppid==parent as u32,"payload actual direct child differs")?;
        material.guard(body_end)?;
        apk_io::send_before(channel.as_raw_fd(),&wire,&[material.file(body_end)?.as_raw_fd(),owner.as_raw_fd()],body_end)?;
        let reply=apk_io::receive_before::<Wire>(channel.as_raw_fd(),body_end)?;
        require(reply.peer.pid==pid as i32&&reply.peer.uid==0&&reply.peer.gid==0
            &&reply.value==Wire{phase:Phase::Created,..wire}&&reply.files.len()==1,
            "payload response is not the original creator, request or exact descriptor")?;
        child.finish(end)?;
        let file=reply.files.into_iter().next().ok_or_else(||reject("payload descriptor absent"))?;
        material.guard(end)?;payload(&file,kind,end)?;
        let(code,status)=child.terminal.ok_or(ApplicationError::RetirementUnproven)?;
        let fd=child.pidfd.take().ok_or(ApplicationError::RetirementUnproven)?;
        let node=fd.metadata()?;
        let retirement=Retirement{pid:child.pid,node:(node.dev(),node.ino()),pidfd:fd,code,status};
        retirement.guard()?;
        Ok(CreatedPayload{kind,file,material,retirement,end:original_end})
    })();
    if operation.is_err(){retire_before(&mut child,end)?;}
    operation
}
pub(super) fn entry()->Result<()>{
    helper::own_root_credentials()?;helper::verify_fixed_stdio()?;
    helper::mac_context(CONTEXT)?;
    if unsafe{libc::prctl(libc::PR_SET_DUMPABLE,0,0,0,0)}!=0{return Err(io::Error::last_os_error().into());}
    helper::empty_capabilities()?;
    drop(crate::production_host_admission::application_worker_executable().map_err(external)?);
    helper::channel_kind(3)?;
    helper::install_filter(&filter(None))?;
    let parent=unsafe{libc::getppid()};require(parent>1,"payload original broker parent absent")?;
    let packet=apk_io::receive_before::<Wire>(3,Instant::now()+Duration::from_secs(5))?;
    require(packet.value.phase==Phase::Create&&packet.files.len()==2,"payload initial closed phase or FD count differs")?;
    let [original,owner]:[File;2]=packet.files.try_into().map_err(|_|reject("payload source and owner count"))?;
    helper::parent_identity(&owner,packet.peer,parent)?;
    if unsafe{libc::prctl(libc::PR_SET_PDEATHSIG,libc::SIGKILL)}!=0{return Err(io::Error::last_os_error().into());}
    helper::parent_identity(&owner,packet.peer,parent)?;
    let end=remaining_end(packet.value)?;
    let body_end=end.checked_sub(RETIRE_RESERVE).ok_or_else(||reject("payload child retirement reserve absent"))?;
    source(&original,packet.value.kind,body_end)?;
    let readonly=apk_payload::prepare_held_until(&original,body_end).map_err(external)?;
    source(&original,packet.value.kind,body_end)?;payload(&readonly,packet.value.kind,body_end)?;
    helper::parent_identity(&owner,packet.peer,parent)?;helper::mac_context(CONTEXT)?;helper::empty_capabilities()?;
    apk_io::send_before(3,&Wire{phase:Phase::Created,..packet.value},&[readonly.as_raw_fd()],body_end)?;
    helper::parent_identity(&owner,packet.peer,parent)?;before(body_end)
}

// Post-exec no namespace, socket/pipe/process creation, relabel, privilege or
// subsequent exec. The sole writable inode is its normal FILE-transition memfd.
fn filter(executable:Option<RawFd>)->Vec<libc::sock_filter>{
    let ins=|code,jt,jf,k|libc::sock_filter{code,jt,jf,k};
    let deny=0x0005_0000|libc::EPERM as u32;let allow=0x7fff_0000;
    let mut f=vec![ins(0x20,0,0,4),ins(0x15,1,0,0xc000_003e),ins(0x06,0,0,0x8000_0000),
        ins(0x20,0,0,0),ins(0x35,0,1,0x4000_0000),ins(0x06,0,0,deny)];
    let mut narrow=|syscall:libc::c_long,args:&[(u32,u64)]|{
        let mut body=Vec::new();
        for(index,value)in args{
            for(offset,part)in[(16+index*8,*value as u32),(20+index*8,(*value>>32)as u32)]{
                body.extend([ins(0x20,0,0,offset),ins(0x15,1,0,part),ins(0x06,0,0,deny)]);
            }
        }
        body.push(ins(0x06,0,0,allow));
        f.push(ins(0x15,0,body.len()as u8,syscall as u32));f.extend(body);f.push(ins(0x20,0,0,0));
    };
    narrow(459,&[(0,100),(3,1)]);
    narrow(libc::SYS_recvmsg,&[(0,3)]);narrow(libc::SYS_sendmsg,&[(0,3)]);
    narrow(libc::SYS_ioctl,&[(1,0xc050_ff0b)]);
    narrow(libc::SYS_memfd_create,&[(1,(libc::MFD_CLOEXEC|libc::MFD_ALLOW_SEALING|0x0008)as u64)]);
    if let Some(fd)=executable{narrow(libc::SYS_execveat,&[(0,fd as u64),(4,libc::AT_EMPTY_PATH as u64)]);}
    for syscall in[
        libc::SYS_read,libc::SYS_write,libc::SYS_close,libc::SYS_fstat,libc::SYS_newfstatat,
        libc::SYS_statx,libc::SYS_fstatfs,libc::SYS_openat,libc::SYS_readlink,libc::SYS_readlinkat,
        libc::SYS_mmap,libc::SYS_mprotect,libc::SYS_munmap,libc::SYS_brk,libc::SYS_madvise,
        libc::SYS_rt_sigaction,libc::SYS_rt_sigprocmask,libc::SYS_rt_sigreturn,libc::SYS_arch_prctl,
        libc::SYS_prlimit64,libc::SYS_getrlimit,libc::SYS_getrandom,libc::SYS_set_tid_address,
        libc::SYS_set_robust_list,libc::SYS_rseq,libc::SYS_access,libc::SYS_faccessat,libc::SYS_faccessat2,
        libc::SYS_futex,libc::SYS_clock_gettime,libc::SYS_clock_nanosleep,libc::SYS_nanosleep,
        libc::SYS_poll,libc::SYS_ppoll,libc::SYS_fcntl,libc::SYS_getpid,libc::SYS_gettid,libc::SYS_getppid,
        libc::SYS_getuid,libc::SYS_geteuid,libc::SYS_getgid,libc::SYS_getegid,libc::SYS_getgroups,
        libc::SYS_capget,libc::SYS_prctl,libc::SYS_getsockopt,libc::SYS_fgetxattr,
        libc::SYS_lseek,libc::SYS_pread64,libc::SYS_fsync,libc::SYS_sched_getaffinity,
        libc::SYS_exit_group,libc::SYS_exit,
    ]{f.extend([ins(0x15,0,1,syscall as u32),ins(0x06,0,0,allow)]);}
    f.push(ins(0x06,0,0,deny));f
}
#[cfg(test)]
mod tests{
    use super::*;
    fn decision(program:&[libc::sock_filter],nr:u32,args:[u64;6])->u32{
        let mut input=[0_u32;16];input[0]=nr;input[1]=0xc000_003e;
        for(i,a)in args.iter().enumerate(){input[4+2*i]=*a as u32;input[5+2*i]=(*a>>32)as u32;}
        let(mut pc,mut a)=(0_usize,0_u32);
        for _ in 0..program.len()+1{
            let i=program.get(pc).expect("bounded BPF instruction");
            match i.code{0x20=>{a=input[i.k as usize/4];pc+=1;},
                0x15=>pc+=1+if a==i.k{i.jt}else{i.jf}as usize,
                0x35=>pc+=1+if a>=i.k{i.jt}else{i.jf}as usize,
                0x06=>return i.k,_=>panic!("unexpected BPF opcode")}
        }panic!("BPF did not terminate")
    }
    #[test]
    fn working_payload_creator_fixed_five_materials_and_wire_reject_external_fields(){
        let kinds=[WorkingPayloadKind::DocumentsSaf,WorkingPayloadKind::DocumentsFeatures,WorkingPayloadKind::Ihg,
            WorkingPayloadKind::GalleryRotation,WorkingPayloadKind::GalleryVideo];
        let mut hashes=std::collections::BTreeSet::new();
        for kind in kinds{
            assert!(kind.apk_bytes()>4&&kind.apk_bytes()<=MAX_MATERIAL_BYTES);
            assert_eq!(kind.apk_sha256().len(),64);assert!(hashes.insert(kind.apk_sha256()));
            let wire=Wire{phase:Phase::Create,kind,nonce:[1;16],deadline_ns:1};
            let raw=serde_json::to_value(wire).unwrap();
            assert_eq!(serde_json::from_value::<Wire>(raw.clone()).unwrap(),wire);
            let mut altered=raw;altered["path"]=json!("/tmp/caller.apk");
            assert!(serde_json::from_value::<Wire>(altered).is_err());
        }
        for raw in [r#""any""#,r#"{"kind":"ihg","package":"other"}"#]{
            assert!(serde_json::from_str::<WorkingPayloadKind>(raw).is_err());
        }
    }
    #[test]
    fn working_payload_creator_filter_has_only_fixed_memfd_and_no_second_exec(){
        let p=filter(None);let allow=0x7fff_0000;let deny=0x0005_0000|libc::EPERM as u32;
        assert_eq!(decision(&p,libc::SYS_memfd_create as u32,[0,11,0,0,0,0]),allow);
        for flags in[0,1,3,7,11+(1_u64<<32)]{
            assert_eq!(decision(&p,libc::SYS_memfd_create as u32,[0,flags,0,0,0,0]),deny);
        }
        for nr in[libc::SYS_clone,libc::SYS_clone3,libc::SYS_fork,libc::SYS_vfork,libc::SYS_execve,
            libc::SYS_execveat,libc::SYS_socket,libc::SYS_socketpair,libc::SYS_pipe,libc::SYS_pipe2,
            libc::SYS_setns,libc::SYS_unshare,libc::SYS_capset,libc::SYS_fsetxattr,460]{
            assert_eq!(decision(&p,nr as u32,[0;6]),deny);
        }
        assert_eq!(decision(&p,459,[100,0,0,1,0,0]),allow);
        assert_eq!(decision(&p,459,[101,0,0,1,0,0]),deny);
        assert_eq!(decision(&p,libc::SYS_sendmsg as u32,[4,0,0,0,0,0]),deny);
        assert_eq!(decision(&p,libc::SYS_recvmsg as u32,[4,0,0,0,0,0]),deny);
    }
}
