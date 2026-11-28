//! Original-thread single APK session. One source role per admitted owner
//! step; all file hashing/copying remains in the independently held reader.
use super::*;
use crate::production_application::{apk_protocol as protocol,apk_reader,apk_session_owner};
use crate::production_application::apk_transport::{Reading,Writing};
use crate::production_mac::KernelFirstApkStream;
use crate::production_selection::early_generation::EarlyApplicationAuthority;
use protocol::{Begin,Operation,Request,Response,Sequence};
use std::os::fd::AsRawFd;

const INTAKE:Duration=Duration::from_secs(15);
const BOOKEND:Duration=Duration::from_secs(70);
enum Phase {Reading,NeedBegin,Reader,NeedPackageRead,NeedFinal,Reaping,Sending,Done}
pub(super) enum Progress {Idle,NeedOwner(Instant),Done}
enum Peer {
    Physical(crate::control::package::NativeUiPeer),
    Preparation(crate::control::package::PreparationPeer),
}
impl Peer {
    fn bind(stream:&UnixStream,end:Instant)->Result<Self,ControlError>{
        if let Ok(peer)=crate::control::package::NativeUiPeer::bind(stream,end) {
            return Ok(Self::Physical(peer));
        }
        crate::control::package::PreparationPeer::bind(stream,end).map(Self::Preparation)
            .map_err(|e|io_error("bind original APK physical/preparation peer",e))
    }
    fn revalidate(&self,stream:&UnixStream,end:Instant)->Result<(),ControlError>{
        let checked=match self {
            Self::Physical(peer)=>peer.revalidate(stream,end),
            Self::Preparation(peer)=>peer.revalidate(stream,end),
        };
        checked.map_err(|e|io_error("original APK peer changed",e))
    }
    fn accepts(&self,begin:&Begin)->bool{
        matches!(self,Self::Preparation(_))==begin.scope().is_preparation()
    }
}
pub(super) struct Slot {
    reader:Option<apk_reader::Reader>,
    stream:Option<KernelFirstApkStream>,
    peer:Peer,
    begin:Option<Begin>,
    nonce:[u8;16],
    sequence:Option<Sequence>,
    current:Option<(u32,Operation)>,
    phase:Phase,
    reading:Reading,
    writing:Option<Writing>,
    end:Instant,
    stage_end:Option<Instant>,
    group_end:Option<Instant>,
    before:Vec<protocol::Bookend>,
    after:Vec<protocol::Bookend>,
    packages:Vec<protocol::PackageFiles>,
    completed:bool,
}
fn invalid(reason:impl Into<String>)->ControlError{ControlError::Invalid(reason.into())}
fn actual_error(e:crate::production_application::ApplicationError)->ControlError{
    invalid(e.to_string())
}
impl Slot {
    pub(super) fn accept(stream:KernelFirstApkStream)->Result<Self,ControlError>{
        let end=Instant::now()+INTAKE;
        let peer=Peer::bind(stream.stream().map_err(selected_socket_control)?,end)?;
        Ok(Self{reader:None,stream:Some(stream),peer,begin:None,nonce:[0;16],sequence:None,
            current:None,phase:Phase::Reading,reading:Reading::request(),writing:None,
            end,stage_end:None,group_end:None,before:Vec::new(),after:Vec::new(),
            packages:Vec::new(),completed:false})
    }
    fn socket(&self)->Result<&UnixStream,ControlError>{
        self.stream.as_ref().ok_or_else(||invalid("APK accepted stream retired"))?
            .stream().map_err(selected_socket_control)
    }
    fn revalidate_peer(&self)->Result<(),ControlError>{self.peer.revalidate(self.socket()?,self.end)}
    fn operation_end(&self)->Result<Instant,ControlError>{
        let now=Instant::now();
        let end=self.end.min(self.group_end.ok_or_else(||invalid("APK original group stage absent"))?);
        if now>=end{return Err(invalid("APK original group stage elapsed"));}
        Ok(end.min(now+BOOKEND))
    }
    fn queue(&mut self,response:Response,copy:Option<fs::File>)->Result<(),ControlError>{
        let bytes=response.bytes().map_err(invalid)?;
        self.writing=Some(Writing::new(&bytes,copy).map_err(|e|io_error("frame actual APK comparison",e))?);
        self.phase=Phase::Sending;
        Ok(())
    }
    fn no_disconnect(&self)->Result<(),ControlError>{
        let mut byte=0_u8;
        let n=unsafe{libc::recv(self.socket()?.as_raw_fd(),(&mut byte as *mut u8).cast(),1,libc::MSG_PEEK|libc::MSG_DONTWAIT)};
        if n==0{return Err(invalid("APK original client disconnected"));}
        if n<0 {
            let e=io::Error::last_os_error();
            if !matches!(e.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::Interrupted){
                return Err(io_error("observe original APK connection",e));
            }
        }
        Ok(())
    }
    pub(super) fn poll(&mut self)->Result<Progress,ControlError>{
        if Instant::now()>=self.end{return Err(invalid("APK original session deadline elapsed"));}
        self.no_disconnect()?;
        match self.phase {
            Phase::NeedBegin|Phase::NeedFinal|Phase::NeedPackageRead=>{
                let end=match self.stage_end {Some(end)=>end,None=>{
                    let end=self.operation_end()?;self.stage_end=Some(end);end
                }};
                if Instant::now()>=end{return Err(invalid("APK actual role deadline elapsed"));}
                return Ok(Progress::NeedOwner(end));
            }
            Phase::Reading=>{
                let fd=self.socket()?.as_raw_fd();
                let Some(frame)=self.reading.poll(fd).map_err(|e|io_error("read fixed APK request",e))? else {
                    return Ok(Progress::Idle);
                };
                if !frame.files.is_empty(){return Err(invalid("APK host request supplied descriptors"));}
                self.revalidate_peer()?;
                let request=Request::parse(&frame.bytes).map_err(invalid)?;
                if self.begin.is_none() {
                    let Request::Begin{nonce,begin}=request else{return Err(invalid("APK first message is not begin"));};
                    if !self.peer.accepts(&begin){return Err(invalid("APK peer cannot use this source scope"));}
                    self.end=begin.deadline().map_err(invalid)?;self.nonce=nonce;
                    self.group_end=Some(self.end.min(Instant::now()+begin.scope().metadata_cap()));
                    self.begin=Some(begin);self.phase=Phase::NeedBegin;
                    self.stage_end=Some(self.operation_end()?);
                    return Ok(Progress::NeedOwner(self.stage_end.unwrap()));
                }
                let Request::Continue{nonce,sequence,operation}=request else{return Err(invalid("APK begin cannot be replayed"));};
                self.sequence.as_mut().ok_or_else(||invalid("APK actual group sequence absent"))?
                    .accept(nonce,sequence,operation).map_err(invalid)?;
                if let Operation::PackageRead{ordinal,deadline_ns,..}=operation {
                    let begin=self.begin.as_ref().ok_or_else(||invalid("APK actual slot has no begin"))?;
                    protocol::PackageReadKind::require_role(begin.scope(),ordinal).map_err(invalid)?;
                    if ordinal as usize>=self.packages.len() || deadline_ns>begin.deadline_ns(){
                        return Err(invalid("APK PM role or absolute end differs from its original slot"));
                    }
                    let request_end=operation.package_end().map_err(invalid)?.unwrap();
                    self.stage_end=Some(request_end.min(self.end));
                }
                self.current=Some((sequence,operation));
                self.reader.as_mut().ok_or_else(||invalid("APK real reader absent"))?
                    .request(sequence,operation).map_err(actual_error)?;
                self.phase=Phase::Reader;
            }
            Phase::Reader=>{
                let Some(event)=self.reader.as_mut().ok_or_else(||invalid("APK reader absent"))?
                    .poll().map_err(actual_error)? else{return Ok(Progress::Idle);};
                self.revalidate_peer()?;
                match event.reply {
                    apk_reader::Reply::Ready{nonce,packages}=>{
                        if self.current.is_some() || nonce!=self.nonce || !event.files.is_empty(){
                            return Err(invalid("APK actual begin response differs"));
                        }
                        let begin=self.begin.as_ref().ok_or_else(||invalid("APK begin absent"))?;
                        protocol::validate_bookends(begin,&packages,&self.before).map_err(invalid)?;
                        let copies=packages.iter().map(|v|v.originals.len()).sum();
                        self.sequence=Some(Sequence::begin(nonce,copies).map_err(invalid)?);
                        self.packages=packages.clone();
                        let before=std::mem::take(&mut self.before);
                        self.queue(Response::Begun{nonce,begin:begin.clone(),packages,bookends:before},None)?;
                    }
                    apk_reader::Reply::Copy{nonce,sequence,comparison}=>{
                        if nonce!=self.nonce || self.current!=Some((sequence,Operation::NextCopy)) || event.files.len()!=1 {
                            return Err(invalid("APK actual copy phase differs"));
                        }
                        comparison.validate().map_err(invalid)?;
                        let mut files=event.files;
                        self.queue(Response::Copied{nonce,sequence,comparison},files.pop())?;
                    }
                    apk_reader::Reply::Guarded{nonce,sequence,full_hash}=>{
                        if let Some((expected_sequence,Operation::PackageRead{..}))=self.current {
                            if nonce!=self.nonce || sequence!=expected_sequence || full_hash || !event.files.is_empty(){
                                return Err(invalid("APK PM prerequisite actual FD guard differs"));
                            }
                            let end=self.stage_end.ok_or_else(||invalid("APK PM original command end absent"))?;
                            if Instant::now()>=end{return Err(invalid("APK PM command expired before normal owner"));}
                            self.phase=Phase::NeedPackageRead;
                            return Ok(Progress::NeedOwner(end));
                        }
                        let expected=if full_hash{Operation::Refresh}else{Operation::Guard};
                        if nonce!=self.nonce || self.current!=Some((sequence,expected)) || !event.files.is_empty(){
                            return Err(invalid("APK actual guard phase differs"));
                        }
                        self.queue(Response::Guarded{nonce,sequence,full_hash},None)?;
                    }
                    apk_reader::Reply::FinishChecked{nonce,sequence}=>{
                        if nonce!=self.nonce || self.current!=Some((sequence,Operation::Finish)) || !event.files.is_empty(){
                            return Err(invalid("APK actual finish phase differs"));
                        }
                        let begin=self.begin.as_ref().ok_or_else(||invalid("APK begin absent"))?;
                        self.group_end=Some(self.end.min(Instant::now()+begin.scope().metadata_cap()));
                        self.phase=Phase::NeedFinal;self.stage_end=Some(self.operation_end()?);
                        return Ok(Progress::NeedOwner(self.stage_end.unwrap()));
                    }
                    apk_reader::Reply::Released{nonce,sequence}=>{
                        if nonce!=self.nonce || self.current!=Some((sequence,Operation::Finish)) || !event.files.is_empty(){
                            return Err(invalid("APK actual release phase differs"));
                        }
                        self.stage_end=Some(self.end.min(Instant::now()+protocol::RETIRE));
                        self.phase=Phase::Reaping;
                    }
                    apk_reader::Reply::Rejected{reason,..}=>return Err(invalid(format!("actual APK reader rejected: {reason}"))),
                }
            }
            Phase::Reaping=>{
                if Instant::now()>=self.stage_end.ok_or_else(||invalid("APK retirement deadline absent"))? {
                    return Err(invalid("APK bounded real retirement elapsed"));
                }
                let Some(retirement)=self.reader.as_mut().ok_or_else(||invalid("APK reader absent"))?
                    .reaped().map_err(actual_error)? else{return Ok(Progress::Idle);};
                self.revalidate_peer()?;
                let (sequence,operation)=self.current.ok_or_else(||invalid("APK final sequence absent"))?;
                if operation!=Operation::Finish{return Err(invalid("APK final operation differs"));}
                let retired=retirement.comparison();retired.validate().map_err(invalid)?;
                self.completed=true;
                let bookends=std::mem::take(&mut self.after);
                self.queue(Response::Finished{nonce:self.nonce,sequence,bookends,retirement:retired},None)?;
            }
            Phase::Sending=>{
                let fd=self.socket()?.as_raw_fd();
                if self.writing.as_mut().ok_or_else(||invalid("APK outgoing response absent"))?
                    .poll(fd).map_err(|e|io_error("send actual APK comparison",e))? {
                    self.writing=None;
                    if self.completed {self.phase=Phase::Done;return Ok(Progress::Done);}
                    self.reading=Reading::request();self.phase=Phase::Reading;
                }
            }
            Phase::Done=>return Ok(Progress::Done),
        }
        Ok(Progress::Idle)
    }
    pub(super) fn with_owner(&mut self,owner:&EarlyApplicationAuthority<'_>,end:Instant)->Result<(),ControlError>{
        if self.stage_end!=Some(end) || Instant::now()>=end || end>self.end {
            return Err(invalid("APK owner does not borrow the exact pending role deadline"));
        }
        self.revalidate_peer()?;
        let begin=self.begin.as_ref().ok_or_else(||invalid("APK source begin absent"))?;
        match self.phase {
            Phase::NeedBegin=>{
                let actual=apk_session_owner::observe_begin(owner,begin,self.before.len(),end).map_err(actual_error)?;
                self.before.push(actual);
                if self.before.len()==begin.scope().roles().len() {
                    self.reader=Some(apk_session_owner::spawn(owner,begin,&self.before,self.nonce,end).map_err(actual_error)?);
                    self.phase=Phase::Reader;
                }
            }
            Phase::NeedPackageRead=>{
                let (sequence,Operation::PackageRead{kind,ordinal,..})=self.current
                    .ok_or_else(||invalid("APK pending PM command absent"))? else {
                    return Err(invalid("APK normal owner received a different fixed PM operation"));
                };
                let actual=apk_session_owner::read_package(owner,begin,&self.packages,kind,ordinal,end)
                    .map_err(actual_error)?;
                let comparison=actual.comparison().clone();
                self.queue(Response::PackageRead{nonce:self.nonce,sequence,comparison},None)?;
            }
            Phase::NeedFinal=>{
                let actual=apk_session_owner::observe_finish(owner,begin,&self.packages,self.after.len(),end).map_err(actual_error)?;
                self.after.push(actual);
                if self.after.len()==self.packages.len() {
                    protocol::validate_bookends(begin,&self.packages,&self.after).map_err(invalid)?;
                    self.reader.as_mut().ok_or_else(||invalid("APK original reader absent at final bookend"))?
                        .release().map_err(actual_error)?;
                    self.phase=Phase::Reader;
                }
            }
            _=>return Err(invalid("APK owner was supplied at an unrequested phase")),
        }
        self.revalidate_peer()?;
        self.stage_end=None;
        Ok(())
    }
    pub(super) fn retire(&mut self)->Result<(),ControlError>{
        if let Some(reader)=self.reader.as_mut(){reader.retire().map_err(actual_error)?;}
        self.reader.take();self.writing.take();self.stream.take();
        Ok(())
    }
}
impl Drop for Slot {
    fn drop(&mut self){
        if self.retire().is_err(){
            if let Some(reader)=self.reader.take(){std::mem::forget(reader);}
            if let Some(stream)=self.stream.take(){std::mem::forget(stream);}
        }
    }
}
