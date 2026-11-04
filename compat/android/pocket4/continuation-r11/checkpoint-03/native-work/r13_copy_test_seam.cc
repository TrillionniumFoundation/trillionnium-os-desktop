// HOST TEST ONLY. The workspace seccomp policy rejects self process_vm_*.
// This seam copies only harness-owned memory; it is never in the candidate or
// Android APK. It does not qualify kernel copy admission or arbitrary EFAULT.
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cerrno>
#include <cstdint>
#include <sys/syscall.h>
#include <sys/uio.h>
#include <unistd.h>
extern "C" long __real_syscall(long, ...);
extern "C" long __wrap_syscall(long number, ...) {
  unsigned count;
  switch(number) {
    case SYS_gettid: case SYS_getpid: count=0; break;
    case SYS_close: case SYS_unshare: case SYS_setfsuid: count=1; break;
    case SYS_capget: case SYS_pidfd_open: case SYS_memfd_create: count=2; break;
    case SYS_pidfd_getfd: case SYS_close_range: case SYS_dup3: count=3; break;
    case SYS_readlinkat: count=4; break;
    case SYS_futex: case SYS_process_vm_readv: case SYS_process_vm_writev: count=6; break;
    default: std::fprintf(stderr,"unknown test syscall %ld\n",number); std::abort();
  }
  uintptr_t a[6]{};
  va_list v;va_start(v,number);
  for(unsigned i=0;i<count;++i) a[i]=va_arg(v,uintptr_t);
  va_end(v);
  if(number==SYS_process_vm_readv || number==SYS_process_vm_writev) {
    if(a[0]!=static_cast<uintptr_t>(__real_syscall(SYS_gettid)) || a[2]!=1 || a[4]!=1 || a[5]!=0) {
      errno=EINVAL;return -1;
    }
    const auto* local=reinterpret_cast<const iovec*>(a[1]);
    const auto* remote=reinterpret_cast<const iovec*>(a[3]);
    if(reinterpret_cast<uintptr_t>(local->iov_base)<4096 ||
       reinterpret_cast<uintptr_t>(remote->iov_base)<4096) {errno=EFAULT;return -1;}
    const size_t size=local->iov_len<remote->iov_len?local->iov_len:remote->iov_len;
    if(number==SYS_process_vm_readv) std::memcpy(local->iov_base,remote->iov_base,size);
    else std::memcpy(remote->iov_base,local->iov_base,size);
    return static_cast<long>(size);
  }
  return __real_syscall(number,a[0],a[1],a[2],a[3],a[4],a[5]);
}

// Typed libc controls get the same explicitly declared host-only copy seam.
extern "C" ssize_t __wrap_process_vm_readv(pid_t pid,const struct iovec* local,unsigned long lc,const struct iovec* remote,unsigned long rc,unsigned long flags) {
  return __wrap_syscall(SYS_process_vm_readv,static_cast<long>(pid),local,lc,remote,rc,flags);
}
extern "C" ssize_t __wrap_process_vm_writev(pid_t pid,const struct iovec* local,unsigned long lc,const struct iovec* remote,unsigned long rc,unsigned long flags) {
  return __wrap_syscall(SYS_process_vm_writev,static_cast<long>(pid),local,lc,remote,rc,flags);
}
