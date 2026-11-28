//! Bounded private seqpacket transport; only the original broker can supply
//! the initial root and PIDFDs. A copy reply carries exactly one readonly FD.
use super::apk_protocol as protocol;
use serde::{Serialize, de::DeserializeOwned};
use std::fs::File;
use std::io;
use std::mem;
use std::os::fd::{AsRawFd, FromRawFd, RawFd};
use std::os::unix::net::UnixDatagram;
use std::time::Instant;

pub(super) const MAX_FDS: usize = 5;
pub(super) struct Packet<T> { pub(super) value:T, pub(super) files:Vec<File>, pub(super) peer:libc::ucred }
fn failure(reason:&str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,reason)}
pub(super) fn pair()->io::Result<(UnixDatagram,UnixDatagram)> {
    let mut pair=[-1_i32;2];
    if unsafe{libc::socketpair(libc::AF_UNIX,libc::SOCK_SEQPACKET|libc::SOCK_CLOEXEC|libc::SOCK_NONBLOCK,0,pair.as_mut_ptr())}!=0 {
        return Err(io::Error::last_os_error());
    }
    let a=unsafe{UnixDatagram::from_raw_fd(pair[0])}; let b=unsafe{UnixDatagram::from_raw_fd(pair[1])};
    for socket in [&a,&b] {
        let one=1_i32;
        let size=(protocol::MAX_FRAME*2) as i32;
        for (option,value) in [(libc::SO_PASSCRED,one),(libc::SO_SNDBUF,size),(libc::SO_RCVBUF,size)] {
            if unsafe{libc::setsockopt(socket.as_raw_fd(),libc::SOL_SOCKET,option,(&value as *const i32).cast(),mem::size_of_val(&value) as u32)}!=0 {
                return Err(io::Error::last_os_error());
            }
        }
        let mut observed=0_i32;let mut length=mem::size_of_val(&observed) as u32;
        if unsafe{libc::getsockopt(socket.as_raw_fd(),libc::SOL_SOCKET,libc::SO_SNDBUF,(&mut observed as *mut i32).cast(),&mut length)}!=0
            || observed < protocol::MAX_FRAME as i32+4096 {return Err(failure("APK private socket capacity"));}
    }
    Ok((a,b))
}
pub(super) fn send<T:Serialize>(socket:RawFd,value:&T,files:&[RawFd])->io::Result<bool> {
    if files.len()>MAX_FDS {return Err(failure("APK private descriptor bound"));}
    let mut bytes=serde_json::to_vec(value).map_err(|e|failure(&e.to_string()))?;
    if bytes.is_empty() || bytes.len()>protocol::MAX_FRAME {return Err(failure("APK private frame bound"));}
    let mut iov=libc::iovec{iov_base:bytes.as_mut_ptr().cast(),iov_len:bytes.len()};
    let mut ancillary=[0_usize;64];
    let mut msg:libc::msghdr=unsafe{mem::zeroed()};
    msg.msg_iov=&mut iov;msg.msg_iovlen=1;
    if !files.is_empty() {
        msg.msg_control=ancillary.as_mut_ptr().cast();
        msg.msg_controllen=unsafe{libc::CMSG_SPACE(mem::size_of_val(files) as u32)} as usize;
        let h=unsafe{libc::CMSG_FIRSTHDR(&msg)};
        unsafe {
            (*h).cmsg_level=libc::SOL_SOCKET;(*h).cmsg_type=libc::SCM_RIGHTS;
            (*h).cmsg_len=libc::CMSG_LEN(mem::size_of_val(files) as u32) as usize;
            std::ptr::copy_nonoverlapping(files.as_ptr(),libc::CMSG_DATA(h).cast::<RawFd>(),files.len());
        }
    }
    let n=unsafe{libc::sendmsg(socket,&msg,libc::MSG_DONTWAIT|libc::MSG_NOSIGNAL)};
    if n<0 {
        let e=io::Error::last_os_error();
        if matches!(e.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::Interrupted){return Ok(false);}
        return Err(e);
    }
    if n as usize != bytes.len(){return Err(failure("APK private partial packet"));}
    Ok(true)
}
pub(super) fn receive<T:DeserializeOwned+Serialize>(socket:RawFd)->io::Result<Option<Packet<T>>> {
    let mut bytes=vec![0_u8;protocol::MAX_FRAME+1];
    let mut ancillary=[0_usize;64];
    let mut iov=libc::iovec{iov_base:bytes.as_mut_ptr().cast(),iov_len:bytes.len()};
    let mut msg:libc::msghdr=unsafe{mem::zeroed()};
    msg.msg_iov=&mut iov;msg.msg_iovlen=1;
    msg.msg_control=ancillary.as_mut_ptr().cast();msg.msg_controllen=mem::size_of_val(&ancillary);
    let n=unsafe{libc::recvmsg(socket,&mut msg,libc::MSG_DONTWAIT|libc::MSG_CMSG_CLOEXEC)};
    if n<0 {
        let e=io::Error::last_os_error();
        if matches!(e.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::Interrupted){return Ok(None);}
        return Err(e);
    }
    // Adopt every installed descriptor before evaluating flags or frame bytes.
    // Thus malformed, truncated or duplicate ancillary input cannot leak FDs.
    let mut files=Vec::new();let mut credentials=None;let mut malformed=false;
    let mut header=unsafe{libc::CMSG_FIRSTHDR(&msg)};
    while !header.is_null() {
        let h=unsafe{&*header};
        let base=unsafe{libc::CMSG_LEN(0)} as usize;
        if h.cmsg_len<base {malformed=true;break;}
        let length=h.cmsg_len-base;
        if h.cmsg_level==libc::SOL_SOCKET && h.cmsg_type==libc::SCM_RIGHTS {
            if length%mem::size_of::<RawFd>()!=0 {malformed=true;}
            for index in 0..length/mem::size_of::<RawFd>() {
                let raw=unsafe{std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<RawFd>().add(index))};
                if raw<0 {malformed=true;} else {files.push(unsafe{File::from_raw_fd(raw)});}
            }
        } else if h.cmsg_level==libc::SOL_SOCKET && h.cmsg_type==libc::SCM_CREDENTIALS
            && length==mem::size_of::<libc::ucred>() && credentials.is_none() {
            credentials=Some(unsafe{std::ptr::read_unaligned(libc::CMSG_DATA(header).cast::<libc::ucred>())});
        } else {malformed=true;}
        header=unsafe{libc::CMSG_NXTHDR(&msg,header)};
    }
    if malformed || msg.msg_flags&(libc::MSG_TRUNC|libc::MSG_CTRUNC)!=0
        || n<=0 || n as usize>protocol::MAX_FRAME || files.len()>MAX_FDS {
        return Err(failure("APK private ancillary/body/EOF differs"));
    }
    bytes.truncate(n as usize);
    let peer=credentials.ok_or_else(||failure("APK private credentials absent"))?;
    let unique=crate::native_application_ui_protocol::strict_json(&bytes,false).map_err(|e|failure(&e.to_string()))?;
    let value:T=serde_json::from_value(unique.clone()).map_err(|e|failure(&e.to_string()))?;
    if serde_json::to_value(&value).map_err(|e|failure(&e.to_string()))?!=unique {
        return Err(failure("APK private unknown or noncanonical fields"));
    }
    Ok(Some(Packet{value,files,peer}))
}
pub(super) fn wait(socket:RawFd,events:i16,end:Instant)->io::Result<()> {
    let left=end.saturating_duration_since(Instant::now());
    if left.is_zero(){return Err(io::Error::new(io::ErrorKind::TimedOut,"APK original deadline"));}
    let mut p=libc::pollfd{fd:socket,events,revents:0};
    let n=unsafe{libc::poll(&mut p,1,left.as_millis().clamp(1,20) as i32)};
    if n<0 {
        let e=io::Error::last_os_error();
        if e.kind()!=io::ErrorKind::Interrupted{return Err(e);}
    }
    if p.revents&(libc::POLLERR|libc::POLLNVAL|libc::POLLHUP)!=0 {
        return Err(io::Error::new(io::ErrorKind::BrokenPipe,"APK private channel lost"));
    }
    Ok(())
}
pub(super) fn send_before<T:Serialize>(socket:RawFd,value:&T,files:&[RawFd],end:Instant)->io::Result<()> {
    loop {
        if Instant::now()>=end {return Err(io::Error::new(io::ErrorKind::TimedOut,"APK original deadline"));}
        if send(socket,value,files)?{return Ok(());}
        wait(socket,libc::POLLOUT,end)?;
    }
}
pub(super) fn receive_before<T:DeserializeOwned+Serialize>(socket:RawFd,end:Instant)->io::Result<Packet<T>> {
    loop {
        if Instant::now()>=end {return Err(io::Error::new(io::ErrorKind::TimedOut,"APK original deadline"));}
        if let Some(value)=receive(socket)?{return Ok(value);}
        wait(socket,libc::POLLIN,end)?;
    }
}
