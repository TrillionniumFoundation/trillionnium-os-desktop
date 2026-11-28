//! Actual authenticated original-broker APK custody client.
//! Wire records compare the live session. Only this Inspector method can mint
//! the opaque owner; original APK FDs never enter a working host process.
use super::*;
use crate::production_application::apk_protocol::{self as protocol,Begin,Bookend,Copy,FileIdentity,Operation,Original,PackageFiles,Request,Response};
use crate::production_application::apk_transport::{Reading,Writing};
use crate::production_application::apk_scope::Scope;
use protocol::{PackageReadKind,PackageReadComparison};
use sha2::{Digest,Sha256};
use std::os::unix::fs::FileExt;

fn rejected(reason:impl Into<String>)->ControlError {ControlError::Invalid(reason.into())}
fn same(ok:bool,reason:&str)->Result<(),ControlError>{
    if ok {Ok(())}else{Err(rejected(reason))}
}
fn poll_before(fd:RawFd,events:i16,end:Instant)->Result<(),ControlError>{
    check_deadline(Some(end))?;
    let left=end.saturating_duration_since(Instant::now());
    let mut item=libc::pollfd{fd,events,revents:0};
    let n=unsafe{libc::poll(&mut item,1,left.as_millis().clamp(1,20) as i32)};
    if n<0 {
        let e=io::Error::last_os_error();
        if e.kind()!=io::ErrorKind::Interrupted{return Err(io_error("wait original APK peer",e));}
    }
    same(item.revents&(libc::POLLERR|libc::POLLNVAL)==0,"APK original peer failed")?;
    // A normal final close may accompany already-buffered response bytes.
    // Consume those bytes before interpreting HUP as an incomplete response.
    same(item.revents&libc::POLLHUP==0 || item.revents&events!=0,
        "APK original peer closed before its complete response")?;
    check_deadline(Some(end))
}
fn nonce()->Result<[u8;16],ControlError>{
    let mut value=[0_u8;16];let mut used=0;
    while used<value.len(){
        let n=unsafe{libc::getrandom(value[used..].as_mut_ptr().cast(),value.len()-used,0)};
        if n<0 {
            let e=io::Error::last_os_error();
            if e.kind()==io::ErrorKind::Interrupted{continue;}
            return Err(io_error("create actual APK session nonce",e));
        }
        same(n>0,"APK session nonce made no progress")?;used+=n as usize;
    }
    same(value!=[0;16],"APK session nonce is empty")?;Ok(value)
}
fn copy_label(file:&fs::File)->Result<(),ControlError>{
    let mut bytes=[0_u8;256];
    let n=unsafe{libc::fgetxattr(file.as_raw_fd(),c"security.selinux".as_ptr(),
        bytes.as_mut_ptr().cast(),bytes.len())};
    if n<0{return Err(io_error("read sealed APK copy label",io::Error::last_os_error()));}
    let value=&bytes[..n as usize];
    same(value.strip_suffix(b"\0").unwrap_or(value)==b"u:object_r:droidloom_native_leaf_apk_copy:s0",
        "received APK is not the fixed public copy object")
}
fn verify_copy(file:&fs::File,comparison:&Copy,end:Instant,full:bool)->Result<(),ControlError>{
    check_deadline(Some(end))?;
    comparison.validate().map_err(rejected)?;
    same(FileIdentity::of(&file.metadata().map_err(|e|io_error("stat actual sealed APK",e))?)==comparison.sealed_copy,
        "actual sealed APK identity differs from its original-reader comparison")?;
    let flags=unsafe{libc::fcntl(file.as_raw_fd(),libc::F_GETFL)};
    let descriptor=unsafe{libc::fcntl(file.as_raw_fd(),libc::F_GETFD)};
    same(flags>=0 && flags&libc::O_ACCMODE==libc::O_RDONLY
        && descriptor>=0 && descriptor&libc::FD_CLOEXEC!=0
        && unsafe{libc::fcntl(file.as_raw_fd(),libc::F_GET_SEALS)}==comparison.seals,
        "APK received copy is not readonly, CLOEXEC and fully sealed")?;
    copy_label(file)?;
    if full {
        let mut buffer=[0_u8;65_536];let mut offset=0_u64;let mut digest=Sha256::new();
        while offset<comparison.sealed_copy.bytes {
            check_deadline(Some(end))?;
            let count=buffer.len().min((comparison.sealed_copy.bytes-offset) as usize);
            let n=file.read_at(&mut buffer[..count],offset).map_err(|e|io_error("hash actual sealed APK",e))?;
            same(n>0,"actual sealed APK became short")?;
            digest.update(&buffer[..n]);offset+=n as u64;
        }
        same(file.read_at(&mut buffer[..1],offset).map_err(|e|io_error("check sealed APK EOF",e))?==0
            && format!("{:x}",digest.finalize())==comparison.original.apk.sha256,
            "actual complete sealed APK does not match its original descriptor hash")?;
    }
    same(FileIdentity::of(&file.metadata().map_err(|e|io_error("bookend actual sealed APK",e))?)==comparison.sealed_copy,
        "sealed APK metadata changed during receive/hash")?;
    check_deadline(Some(end))
}

/// One source-observed public copy. It contains no original APK descriptor and
/// is deliberately neither Clone nor Deserialize. Callers stream and drop it.
pub(crate) struct NativeLeafApkCopy {
    file:fs::File,
    comparison:Copy,
}
impl NativeLeafApkCopy {
    pub(crate) fn file(&self)->&fs::File{&self.file}
    pub(crate) fn comparison(&self)->&Copy{&self.comparison}
    pub(crate) fn verify(&self,end:Instant)->Result<(),ControlError>{
        verify_copy(&self.file,&self.comparison,end,false)
    }
}

/// One actual query output. No public/serde constructor exists. The complete
/// byte body is released after it has reached the original child's journal.
pub(crate) struct NativeLeafApkPackageRead {
    comparison:PackageReadComparison,
    output:std::process::Output,
}
impl NativeLeafApkPackageRead {
    pub(crate) fn output(&self)->&std::process::Output{&self.output}
    pub(crate) fn comparison(&self)->Result<serde_json::Value,ControlError>{
        serde_json::to_value(&self.comparison).map_err(|e|rejected(e.to_string()))
    }
}
/// Retain actual receipt and full-output digests, not 4096 duplicated stdout
/// bodies. Only package_read, after authenticated normal output validation,
/// constructs this private history entry.
#[derive(serde::Serialize)]
struct PackageReadHistory {
    kind:PackageReadKind,
    ordinal:u8,
    stdout_bytes:usize,
    stdout_sha256:String,
    stderr_bytes:usize,
    stderr_sha256:String,
    receipt:serde_json::Value,
}
impl PackageReadHistory {
    fn require(&self,scope:Scope)->Result<(),ControlError>{
        PackageReadKind::require_role(scope,self.ordinal).map_err(rejected)?;
        same(self.stdout_bytes<=65_536 && self.stderr_bytes==0
            && protocol::sha256(&self.stdout_sha256)
            && self.stderr_sha256==format!("{:x}",Sha256::digest(b""))
            && self.receipt.get("output_bytes").and_then(serde_json::Value::as_u64)==Some(self.stdout_bytes as u64)
            && self.receipt.get("output_sha256").and_then(serde_json::Value::as_str)==Some(self.stdout_sha256.as_str())
            && self.receipt.get("query_waitid_code").and_then(serde_json::Value::as_i64)==Some(i64::from(libc::CLD_EXITED))
            && self.receipt.get("query_waitid_status").and_then(serde_json::Value::as_i64)==Some(0),
            "actual completed PM query history differs")
    }
}

/// The only live handle to this original peer's retained APK reader.
pub(crate) struct NativeLeafApkCustody {
    stream:Option<UnixStream>,
    peer:NativeInspectionPeer,
    pidfd:fs::File,
    begin:Begin,
    nonce:[u8;16],
    next:u32,
    copied:usize,
    originals:Vec<Original>,
    packages:Vec<PackageFiles>,
    before:Vec<Bookend>,
    package_reads:Vec<PackageReadHistory>,
    end:Instant,
    failure:Option<String>,
}
/// Historical comparison after actual normal final bookends and real waitid.
/// It cannot create another live reader or prove custody after that interval.
pub(crate) struct FinishedNativeLeafApkCustody {
    peer:NativeInspectionPeer,
    pidfd:fs::File,
    begin:Begin,
    originals:Vec<Original>,
    copies_transferred:usize,
    packages:Vec<PackageFiles>,
    before:Vec<Bookend>,
    after:Vec<Bookend>,
    package_reads:Vec<PackageReadHistory>,
    retirement:protocol::RetiredComparison,
}
impl NativeApplicationInspector {
    pub(crate) fn begin_native_leaf_apk_until(
        &self,main:&MainCustodyObservation,application:&ActualApplicationObservation,scope:Scope,
        original_end:Instant,request_end:Instant,
    )->Result<NativeLeafApkCustody,ControlError>{
        same(request_end<=original_end,"APK initial request would extend original context")?;
        self.require_observations_local(main,application,request_end)?;
        let begin=Begin::from_owned(main.facts(),application.facts(),scope,original_end).map_err(rejected)?;
        let stream=progress::connect(Path::new(DEFAULT_CONTROL_SOCKET))
            .map_err(|e|io_error("connect original APK owner",e))?;
        let actual=peer_credentials_checked(&stream)?;
        let pidfd=peer_pidfd(&stream).map_err(|e|io_error("retain actual APK peer",e))?;
        let node=pidfd.metadata().map_err(|e|io_error("stat actual APK peer",e))?;
        let original=self.pidfd.metadata().map_err(|e|io_error("stat original APK peer",e))?;
        same(actual.pid as u32==self.peer_pid && (node.dev(),node.ino())==(original.dev(),original.ino()),
            "APK socket is not the original normal daemon")?;
        let nonce=nonce()?;
        let mut owner=NativeLeafApkCustody{stream:Some(stream),peer:self.observation()?,pidfd,
            begin:begin.clone(),nonce,next:1,copied:0,originals:Vec::new(),
            packages:Vec::new(),before:Vec::new(),package_reads:Vec::new(),end:original_end,failure:None};
        let received=owner.exchange(self,main,application,&Request::Begin{nonce,begin:begin.clone()},request_end)?;
        let Response::Begun{nonce:actual,begin:echo,packages,bookends}=received.0 else {
            return owner.reject("APK first actual reply is not begun");
        };
        if actual!=nonce || echo!=begin || !received.1.is_empty() {
            return owner.reject("APK actual begin subject or descriptor set differs");
        }
        if let Err(error)=protocol::validate_bookends(&begin,&packages,&bookends){
            return owner.reject(error);
        }
        owner.originals=packages.iter().flat_map(|v|v.originals.iter().cloned()).collect();
        owner.packages=packages;owner.before=bookends;
        owner.require_local(self,main,application,request_end)?;
        Ok(owner)
    }
}
impl NativeLeafApkCustody {
    pub(crate) fn source_scope(&self)->Result<Scope,ControlError>{
        check_deadline(Some(self.end))?;
        same(self.failure.is_none() && self.stream.is_some(),"APK source scope has no live original reader")?;
        live(&self.pidfd).map_err(|e|io_error("guard original APK scope peer",e))?;
        Ok(self.begin.scope())
    }
    fn reject<T>(&mut self,reason:impl Into<String>)->Result<T,ControlError>{
        let reason=reason.into();
        if self.failure.is_none(){self.failure=Some(reason.clone());}
        // A partial/invalid exchange is never replayed. The original broker
        // sees disconnect and owns PIDFD kill/wait retirement before release.
        if let Some(stream)=self.stream.take(){let _=stream.shutdown(std::net::Shutdown::Both);}
        Err(rejected(reason))
    }
    pub(crate) fn require_local(&self,inspector:&NativeApplicationInspector,
        main:&MainCustodyObservation,application:&ActualApplicationObservation,end:Instant
    )->Result<(),ControlError>{
        check_deadline(Some(end.min(self.end)))?;
        same(self.failure.is_none() && self.stream.is_some(),"APK actual session is poisoned or closed")?;
        inspector.require_observations_local(main,application,end)?;
        same(self.peer==inspector.observation()? && self.begin.main()==main.facts()
            && self.begin.application()==application.facts(),"APK session belongs to another whole subject")?;
        live(&self.pidfd).map_err(|e|io_error("observe original APK daemon PIDFD",e))?;
        let current=inspector.pidfd.metadata().map_err(|e|io_error("stat live APK daemon",e))?;
        let held=self.pidfd.metadata().map_err(|e|io_error("stat held APK daemon",e))?;
        same((current.dev(),current.ino())==(held.dev(),held.ino()),"APK actual peer PIDFD changed")
    }
    fn exchange(&mut self,inspector:&NativeApplicationInspector,
        main:&MainCustodyObservation,application:&ActualApplicationObservation,
        request:&Request,end:Instant,
    )->Result<(Response,Vec<fs::File>),ControlError>{
        let end=end.min(self.end);
        let result:Result<(Response,Vec<fs::File>),ControlError>=(||{
            self.require_local(inspector,main,application,end)?;
            let stream=self.stream.as_ref().ok_or_else(||rejected("APK original stream absent"))?;
            let fd=stream.as_raw_fd();
            let mut writing=Writing::new(&request.bytes().map_err(rejected)?,None)
                .map_err(|e|io_error("frame actual APK operation",e))?;
            loop {
                check_deadline(Some(end))?;
                if writing.poll(fd).map_err(|e|io_error("send one actual APK operation",e))?{break;}
                poll_before(fd,libc::POLLOUT,end)?;
            }
            let mut reading=Reading::response();
            let received=loop{
                check_deadline(Some(end))?;
                if let Some(frame)=reading.poll(fd).map_err(|e|io_error("receive actual APK operation",e))?{break frame;}
                poll_before(fd,libc::POLLIN,end)?;
            };
            let response=Response::parse(&received.bytes).map_err(rejected)?;
            self.require_local(inspector,main,application,end)?;
            Ok((response,received.files))
        })();
        match result {
            Ok(value)=>Ok(value),
            Err(error)=>self.reject(error.to_string()),
        }
    }
    fn operation(&mut self,inspector:&NativeApplicationInspector,main:&MainCustodyObservation,
        application:&ActualApplicationObservation,operation:Operation,end:Instant,
    )->Result<(u32,Response,Vec<fs::File>),ControlError>{
        let number=self.next;
        if number>protocol::MAX_REQUESTS{return self.reject("APK fixed request bound exceeded");}
        self.next+=1;
        let request=Request::Continue{nonce:self.nonce,sequence:number,operation};
        let (reply,files)=self.exchange(inspector,main,application,&request,end)?;
        Ok((number,reply,files))
    }
    pub(crate) fn package_read(&mut self,inspector:&NativeApplicationInspector,
        main:&MainCustodyObservation,application:&ActualApplicationObservation,
        kind:PackageReadKind,ordinal:u8,end:Instant,
    )->Result<NativeLeafApkPackageRead,ControlError>{
        PackageReadKind::require_role(self.begin.scope(),ordinal).map_err(rejected)?;
        if ordinal as usize>=self.packages.len(){return self.reject("APK PM role has no actual retained package");}
        let end=end.min(self.end).min(Instant::now()+protocol::PACKAGE_READ_CAP);
        // Compare serialized absolute clocks, then clip to the held begin's
        // original value; different Instant/clock samples cannot renew it.
        let deadline_ns=protocol::absolute(end).map_err(rejected)?.min(self.begin.deadline_ns());
        let operation=Operation::PackageRead{kind,ordinal,deadline_ns};
        let (sequence,response,files)=self.operation(inspector,main,application,operation,end)?;
        let Response::PackageRead{nonce,sequence:actual,comparison}=response else{
            return self.reject("APK fixed PM response has a different kind");
        };
        if nonce!=self.nonce || actual!=sequence || !files.is_empty(){
            return self.reject("APK fixed PM reply belongs to another slot or sequence");
        }
        let output=match comparison.output_for(&self.begin,&self.packages,kind,ordinal){
            Ok(value)=>value,Err(error)=>return self.reject(error),
        };
        self.require_local(inspector,main,application,end)?;
        self.package_reads.push(PackageReadHistory{
            kind,ordinal,stdout_bytes:output.stdout.len(),
            stdout_sha256:format!("{:x}",Sha256::digest(&output.stdout)),
            stderr_bytes:output.stderr.len(),
            stderr_sha256:format!("{:x}",Sha256::digest(&output.stderr)),
            receipt:comparison.receipt.clone(),
        });
        // Preserve the complete actual failure output for the original child
        // journal. It cannot be retried, and cannot produce finished history.
        if !output.status.success() || !output.stderr.is_empty(){
            self.failure=Some("actual fixed PM command failed or wrote stderr".into());
            if let Some(stream)=self.stream.take(){let _=stream.shutdown(std::net::Shutdown::Both);}
        }
        Ok(NativeLeafApkPackageRead{comparison,output})
    }
    pub(crate) fn originals(&self)->&[Original]{&self.originals}
    pub(crate) fn finish_reserve(&self)->Duration{self.begin.scope().finish_cap()}
    pub(crate) fn comparison(&self)->Result<serde_json::Value,ControlError>{
        same(self.failure.is_none() && self.stream.is_some(),"APK live comparison requires an actual retained owner")?;
        Ok(serde_json::json!({"schema":"droidloom.native-leaf-apk-custody.v2",
            "main":self.begin.main(),"application":self.begin.application(),"scope":self.begin.scope(),
            "packages":self.packages,"originals":self.originals,
            "before_bookends":self.before,"copies_transferred":self.copied,
            "package_reads":self.package_reads,
            "reader_retired":false,"comparison_only":true,
            "original_apk_descriptors_on_host":false,"business_accepted":false}))
    }
    pub(crate) fn next_copy(&mut self,inspector:&NativeApplicationInspector,main:&MainCustodyObservation,
        application:&ActualApplicationObservation,end:Instant)->Result<NativeLeafApkCopy,ControlError>{
        if self.copied>=self.originals.len(){return self.reject("APK complete copy set cannot be repeated");}
        let (sequence,response,mut files)=self.operation(inspector,main,application,Operation::NextCopy,end)?;
        let Response::Copied{nonce,sequence:actual,comparison}=response else {
            return self.reject("APK copy reply kind differs");
        };
        if nonce!=self.nonce || actual!=sequence || files.len()!=1
            || comparison.ordinal as usize!=self.copied || comparison.original!=self.originals[self.copied] {
            return self.reject("APK copy nonce, ordinal, original or descriptor set differs");
        }
        let file=files.pop().unwrap();
        let copy_end=end.min(Instant::now()+protocol::BODY_CAP);
        if let Err(error)=verify_copy(&file,&comparison,copy_end,true){return self.reject(error.to_string());}
        self.copied+=1;
        self.require_local(inspector,main,application,end)?;
        Ok(NativeLeafApkCopy{file,comparison})
    }
    pub(crate) fn guard(&mut self,inspector:&NativeApplicationInspector,main:&MainCustodyObservation,
        application:&ActualApplicationObservation,full:bool,end:Instant)->Result<(),ControlError>{
        if self.copied!=0 && self.copied!=self.originals.len(){return self.reject("APK copy set is partial");}
        let operation=if full{Operation::Refresh}else{Operation::Guard};
        let (sequence,response,files)=self.operation(inspector,main,application,operation,end)?;
        if !matches!(response,Response::Guarded{nonce,sequence:actual,full_hash}
            if nonce==self.nonce && actual==sequence && full_hash==full) || !files.is_empty(){
            return self.reject("APK actual guard response differs");
        }
        Ok(())
    }
    pub(crate) fn finish(mut self,inspector:&NativeApplicationInspector,
        main:&MainCustodyObservation,application:&ActualApplicationObservation,end:Instant,
    )->Result<FinishedNativeLeafApkCustody,ControlError>{
        if self.copied!=0 && self.copied!=self.originals.len(){return self.reject("APK final copy set is partial");}
        let (sequence,response,files)=self.operation(inspector,main,application,Operation::Finish,end)?;
        let Response::Finished{nonce,sequence:actual,bookends,retirement}=response else{
            return self.reject("APK final response is not actually retired");
        };
        if nonce!=self.nonce || actual!=sequence || !files.is_empty() {
            return self.reject("APK final sequence or descriptors differ");
        }
        if let Err(error)=protocol::validate_bookends(&self.begin,&self.packages,&bookends){
            return self.reject(error);
        }
        retirement.validate().map_err(rejected)?;
        self.require_local(inspector,main,application,end)?;
        self.stream.take();
        Ok(FinishedNativeLeafApkCustody{peer:self.peer,pidfd:self.pidfd,begin:self.begin,
            originals:self.originals,copies_transferred:self.copied,
            packages:self.packages,before:self.before,after:bookends,
            package_reads:self.package_reads,retirement})
    }
}
impl FinishedNativeLeafApkCustody {
    pub(crate) fn require_subject(&self,inspector:&NativeApplicationInspector,
        main:&MainCustodyObservation,application:&ActualApplicationObservation,end:Instant
    )->Result<(),ControlError>{
        inspector.require_observations_local(main,application,end)?;
        live(&self.pidfd).map_err(|e|io_error("retain actual completed APK peer",e))?;
        same(self.peer==inspector.observation()? && self.begin.main()==main.facts()
            && self.begin.application()==application.facts(),"APK historical subject differs")?;
        self.require_reads()?;
        self.retirement.validate().map_err(rejected)
    }
    fn require_reads(&self)->Result<(),ControlError>{
        same(self.package_reads.len()<=protocol::MAX_REQUESTS as usize,"APK PM history bound")?;
        for read in &self.package_reads{read.require(self.begin.scope())?;}
        Ok(())
    }
    pub(crate) fn comparison(&self)->serde_json::Value{
        serde_json::json!({"schema":"droidloom.native-leaf-apk-custody.v2",
            "main":self.begin.main(),"application":self.begin.application(),"scope":self.begin.scope(),
            "packages":self.packages,"originals":self.originals,"copies_transferred":self.copies_transferred,
            "before_bookends":self.before,"after_bookends":self.after,"retirement":self.retirement,
            "package_reads":self.package_reads,
            "reader_retired":true,"original_apk_descriptors_on_host":false,
            "comparison_only":true,"business_accepted":false})
    }
}

impl FinishedNativeLeafApkCustody {
    pub(crate) fn scope(&self) -> Scope { self.begin.scope() }
    pub(crate) fn require_immutable_subject(&self,
        main:&crate::main_custody::RuntimeMainCustody,
        application:&crate::control::application_probe::ApplicationInspection,
    )->Result<(),ControlError>{
        same(self.begin.main()==main && self.begin.application()==application,
            "completed APK interval belongs to a different actual subject")?;
        live(&self.pidfd).map_err(|e|io_error("guard completed APK original peer",e))?;
        protocol::validate_bookends(&self.begin,&self.packages,&self.before).map_err(rejected)?;
        protocol::validate_bookends(&self.begin,&self.packages,&self.after).map_err(rejected)?;
        self.require_reads()?;
        self.retirement.validate().map_err(rejected)
    }
}
