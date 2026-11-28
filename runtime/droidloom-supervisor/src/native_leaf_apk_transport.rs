//! Bounded stream framing for the dedicated APK session on the original
//! authenticated control socket. Each poll transfers at most 16 KiB.
use super::apk_protocol as protocol;
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{AsRawFd,FromRawFd,RawFd};

const CHUNK:usize=16_384;
fn invalid(reason:&str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,reason)}
pub(crate) fn is_apk(socket:RawFd)->io::Result<bool>{
    let mut byte=0_u8;
    let n=unsafe{libc::recv(socket,(&mut byte as *mut u8).cast(),1,libc::MSG_PEEK|libc::MSG_DONTWAIT)};
    if n<0 {return Err(io::Error::last_os_error());}
    if n==0 {return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"APK classify EOF"));}
    Ok(byte==protocol::MAGIC[0])
}
pub(crate) struct Received {pub(crate) bytes:Vec<u8>,pub(crate) files:Vec<File>}
pub(crate) struct Reading {
    header:[u8;12],
    header_used:usize,
    body:Vec<u8>,
    body_used:usize,
    files:Vec<File>,
    allow_copy:bool,
    failed:bool,
}
impl Reading {
    pub(crate) fn request()->Self {Self::new(false)}
    pub(crate) fn response()->Self {Self::new(true)}
    fn new(allow_copy:bool)->Self {Self{header:[0;12],header_used:0,body:Vec::new(),body_used:0,
        files:Vec::new(),allow_copy,failed:false}}
    pub(crate) fn poll(&mut self,socket:RawFd)->io::Result<Option<Received>>{
        if self.failed{return Err(invalid("APK failed frame cannot be resumed"));}
        let result=self.read_once(socket);
        if result.is_err(){self.failed=true;self.files.clear();}
        result
    }
    fn read_once(&mut self,socket:RawFd)->io::Result<Option<Received>>{
        if self.header_used==12 && self.body_used==self.body.len() {
            return Err(invalid("APK complete frame cannot be consumed twice"));
        }
        let target=if self.header_used<12 {&mut self.header[self.header_used..]}
            else {let count=(self.body.len()-self.body_used).min(CHUNK);&mut self.body[self.body_used..self.body_used+count]};
        let mut iov=libc::iovec{iov_base:target.as_mut_ptr().cast(),iov_len:target.len()};
        let mut ancillary=[0_usize;32];
        let mut msg:libc::msghdr=unsafe{mem::zeroed()};
        msg.msg_iov=&mut iov;msg.msg_iovlen=1;
        msg.msg_control=ancillary.as_mut_ptr().cast();msg.msg_controllen=mem::size_of_val(&ancillary);
        let n=unsafe{libc::recvmsg(socket,&mut msg,libc::MSG_DONTWAIT|libc::MSG_CMSG_CLOEXEC)};
        if n<0 {
            let e=io::Error::last_os_error();
            if matches!(e.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::Interrupted){return Ok(None);}
            return Err(e);
        }
        let mut unexpected=false;
        let mut h=unsafe{libc::CMSG_FIRSTHDR(&msg)};
        while !h.is_null(){
            let c=unsafe{&*h};let base=unsafe{libc::CMSG_LEN(0)} as usize;
            if c.cmsg_len<base {unexpected=true;break;}
            let length=c.cmsg_len-base;
            if c.cmsg_level==libc::SOL_SOCKET && c.cmsg_type==libc::SCM_RIGHTS {
                if length%mem::size_of::<RawFd>()!=0 {unexpected=true;}
                for i in 0..length/mem::size_of::<RawFd>() {
                    let raw=unsafe{std::ptr::read_unaligned(libc::CMSG_DATA(h).cast::<RawFd>().add(i))};
                    if raw<0 {unexpected=true;} else {self.files.push(unsafe{File::from_raw_fd(raw)});}
                }
            } else {unexpected=true;}
            h=unsafe{libc::CMSG_NXTHDR(&msg,h)};
        }
        if unexpected || msg.msg_flags&(libc::MSG_TRUNC|libc::MSG_CTRUNC)!=0
            || self.files.len()>usize::from(self.allow_copy) {return Err(invalid("APK stream cannot accept these ancillary descriptors"));}
        if n==0{return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"APK original peer disconnected"));}
        if self.header_used<12 {
            self.header_used+=n as usize;
            if self.header_used==12 {
                if &self.header[..8]!=protocol::MAGIC {return Err(invalid("APK magic differs"));}
                let length=u32::from_be_bytes(self.header[8..12].try_into().unwrap()) as usize;
                if length==0 || length>protocol::MAX_FRAME {return Err(invalid("APK frame length differs"));}
                self.body.resize(length,0);
            }
        }else{self.body_used+=n as usize;}
        if self.header_used==12 && self.body_used==self.body.len() {
            self.failed=true; // consumed exactly once; caller creates a new frame
            return Ok(Some(Received{bytes:mem::take(&mut self.body),files:mem::take(&mut self.files)}));
        }
        Ok(None)
    }
}
pub(crate) struct Writing {
    bytes:Vec<u8>,used:usize,copy:Option<File>,failed:bool,
}
impl Writing {
    pub(crate) fn new(body:&[u8],copy:Option<File>)->io::Result<Self>{
        if body.is_empty() || body.len()>protocol::MAX_FRAME {return Err(invalid("APK outgoing frame bound"));}
        let mut bytes=Vec::with_capacity(12+body.len());
        bytes.extend_from_slice(protocol::MAGIC);
        bytes.extend_from_slice(&(body.len() as u32).to_be_bytes());
        bytes.extend_from_slice(body);
        Ok(Self{bytes,used:0,copy,failed:false})
    }
    pub(crate) fn poll(&mut self,socket:RawFd)->io::Result<bool>{
        if self.failed{return Err(invalid("APK failed output cannot be resumed"));}
        let result=self.write_once(socket);
        if result.is_err(){self.failed=true;self.copy.take();}
        result
    }
    fn write_once(&mut self,socket:RawFd)->io::Result<bool>{
        if self.used==self.bytes.len(){return Ok(true);}
        let left=(self.bytes.len()-self.used).min(CHUNK);
        let mut iov=libc::iovec{iov_base:self.bytes[self.used..].as_ptr().cast_mut().cast(),iov_len:left};
        let mut ancillary=[0_usize;8];let mut msg:libc::msghdr=unsafe{mem::zeroed()};
        msg.msg_iov=&mut iov;msg.msg_iovlen=1;
        if let Some(file)=&self.copy {
            msg.msg_control=ancillary.as_mut_ptr().cast();
            msg.msg_controllen=unsafe{libc::CMSG_SPACE(mem::size_of::<RawFd>() as u32)} as usize;
            let h=unsafe{libc::CMSG_FIRSTHDR(&msg)};
            unsafe{
                (*h).cmsg_level=libc::SOL_SOCKET;(*h).cmsg_type=libc::SCM_RIGHTS;
                (*h).cmsg_len=libc::CMSG_LEN(mem::size_of::<RawFd>() as u32) as usize;
                std::ptr::write_unaligned(libc::CMSG_DATA(h).cast::<RawFd>(),file.as_raw_fd());
            }
        }
        let n=unsafe{libc::sendmsg(socket,&msg,libc::MSG_DONTWAIT|libc::MSG_NOSIGNAL)};
        if n<0 {
            let e=io::Error::last_os_error();
            if matches!(e.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::Interrupted){return Ok(false);}
            return Err(e);
        }
        if n==0{return Err(io::Error::new(io::ErrorKind::WriteZero,"APK output made no progress"));}
        self.used+=n as usize;
        // A positive stream send transferred the one copy FD even when its
        // body is partial. Never attach that FD again to a later chunk.
        self.copy.take();
        Ok(self.used==self.bytes.len())
    }
}
