// SPDX-License-Identifier: MIT
// Linux host / Asterinas userspace smoke. A PASS here is not Android compatibility.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/futex.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

static int failed;
static void result(const char *name, const char *state, int err) {
    printf("%s\t%s\terrno=%d\n", name, state, err);
    if (!strcmp(state, "FAIL") || !strcmp(state, "UNAVAILABLE_AT_COMPILE_TIME")) failed++;
}
static void test_mmap(void) {
    void *p=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if (p==MAP_FAILED) { result("mmap", "FAIL", errno); return; }
    *(volatile unsigned char *)p=0x5a;
    int ok=(*(volatile unsigned char *)p==0x5a && munmap(p,4096)==0);
    result("mmap",ok?"PASS":"FAIL",ok?0:errno);
}
static void test_memfd(void) {
#ifdef SYS_memfd_create
    int fd=(int)syscall(SYS_memfd_create,"a08-smoke",0);
    if (fd<0) { result("memfd_create", "FAIL", errno); return; }
    if (ftruncate(fd,4096)) { result("memfd_create", "FAIL", errno); close(fd); return; }
    char *p=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);
    if (p==MAP_FAILED) { result("memfd_create", "FAIL", errno); close(fd); return; }
    strcpy(p,"a08");
    char check[4]={0};
    ssize_t n=pread(fd,check,3,0);
    int ok=n==3 && !strcmp(check,"a08");
    munmap(p,4096); close(fd);
    result("memfd_create",ok?"PASS":"FAIL",0);
#else
    result("memfd_create","UNAVAILABLE_AT_COMPILE_TIME",0);
#endif
}
static void test_scm_rights(void) {
    int sv[2],fd=-1,received=-1;
    if (socketpair(AF_UNIX,SOCK_DGRAM,0,sv)) { result("SCM_RIGHTS","FAIL",errno); return; }
    fd=open("/dev/null",O_RDONLY);
    if(fd<0) { result("SCM_RIGHTS","FAIL",errno); goto done; }
    char byte='!'; struct iovec iov={&byte,1};
    union { struct cmsghdr align; char buf[CMSG_SPACE(sizeof(int))]; } control={0};
    struct msghdr message={0}; message.msg_iov=&iov; message.msg_iovlen=1;
    message.msg_control=control.buf; message.msg_controllen=sizeof(control.buf);
    struct cmsghdr *hdr=CMSG_FIRSTHDR(&message);
    hdr->cmsg_level=SOL_SOCKET; hdr->cmsg_type=SCM_RIGHTS; hdr->cmsg_len=CMSG_LEN(sizeof(int));
    memcpy(CMSG_DATA(hdr),&fd,sizeof(fd));
    if(sendmsg(sv[0],&message,0)!=1) { result("SCM_RIGHTS","FAIL",errno); goto done; }
    memset(&control,0,sizeof(control)); message.msg_controllen=sizeof(control.buf);
    if(recvmsg(sv[1],&message,0)!=1) { result("SCM_RIGHTS","FAIL",errno); goto done; }
    hdr=CMSG_FIRSTHDR(&message);
    if (!hdr || hdr->cmsg_level!=SOL_SOCKET || hdr->cmsg_type!=SCM_RIGHTS ||
        hdr->cmsg_len<CMSG_LEN(sizeof(int))) { result("SCM_RIGHTS","FAIL",0); goto done; }
    memcpy(&received,CMSG_DATA(hdr),sizeof(received));
    struct stat sent={0},got={0};
    int ok=received>=0 && fcntl(received,F_GETFD)>=0 &&
           fstat(fd,&sent)==0 && fstat(received,&got)==0 &&
           sent.st_dev==got.st_dev && sent.st_ino==got.st_ino;
    result("SCM_RIGHTS",ok?"PASS":"FAIL",ok?0:errno);
done:
    if(received>=0) close(received);
    if(fd>=0) close(fd);
    close(sv[0]); close(sv[1]);
}
static _Atomic int futex_ready=0;
static _Atomic int futex_state=0;
static int waiter_rc=-2;
static void *waiter(void *ignored) {
    (void)ignored;
    atomic_store(&futex_ready,1);
    struct timespec timeout={2,0};
    waiter_rc=(int)syscall(SYS_futex,&futex_state,FUTEX_WAIT_PRIVATE,0,&timeout,NULL,0);
    return NULL;
}
static void test_futex(void) {
#ifdef SYS_futex
    pthread_t thread;
    if(pthread_create(&thread,NULL,waiter,NULL)) { result("futex_wait_wake","FAIL",0); return; }
    struct timespec nap={0,1000000};
    for(int i=0;i<2000 && !atomic_load(&futex_ready);i++) nanosleep(&nap,NULL);
    nanosleep(&(struct timespec){0,20000000},NULL);
    atomic_store(&futex_state,1);
    long w=syscall(SYS_futex,&futex_state,FUTEX_WAKE_PRIVATE,1,NULL,NULL,0);
    pthread_join(thread,NULL);
    result("futex_wait_wake",w==1 && waiter_rc==0?"PASS":"FAIL",w<0?errno:0);
#else
    result("futex_wait_wake","UNAVAILABLE_AT_COMPILE_TIME",0);
#endif
}
static volatile sig_atomic_t signal_seen;
static void sig_handler(int sig) { if(sig==SIGUSR1) signal_seen=1; }
static void test_signal(void) {
    struct sigaction sa={0},old={0}; sa.sa_handler=sig_handler;
    if(sigaction(SIGUSR1,&sa,&old) || raise(SIGUSR1)) { result("signal","FAIL",errno); return; }
    sigaction(SIGUSR1,&old,NULL);
    result("signal",signal_seen?"PASS":"FAIL",0);
}
static void test_binder(void) {
    // Presence is NOT protocol conformance; full Binder needs BINDER_VERSION, mmap,
    // transactions, refs, death notifications, UID/security context, fd transfers.
    int fd=open("/dev/binder",O_RDWR|O_CLOEXEC);
    if(fd<0) { result("binder_device_open","BLOCKED",errno); return; }
    result("binder_device_open","PRESENT_UNVERIFIED",0); close(fd);
}
int main(void) {
    printf("# host=%s page_size=%ld uid=%ld\n", "syscall_probe",sysconf(_SC_PAGESIZE),(long)getuid());
    test_mmap(); test_memfd(); test_scm_rights(); test_futex(); test_signal(); test_binder();
    return failed?1:0;
}
