#ifndef BINDER_THREAD_FIXTURE_H
#define BINDER_THREAD_FIXTURE_H
// SPDX-License-Identifier: MPL-2.0
// Shared helpers for actual Binder thread guest fixtures.
// Only the isolated ordinary guest may execute this fixture.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/android/binder.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <stdatomic.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define MAP_BYTES (16u*4096u)
#define NODE_POINTER 0x1234abcdULL
#define NODE_COOKIE 0xabcddcbaULL
static unsigned checks;
#define CHECK(x) do { if(!(x)){fprintf(stderr,"Binder thread lifetime FAIL line=%d expr=%s errno=%d pid=%ld tid=%ld\n",__LINE__,#x,errno,(long)getpid(),syscall(SYS_gettid));exit(1);}__atomic_fetch_add(&checks,1,__ATOMIC_RELAXED);}while(0)
struct endpoint {int fd;void *map;};
struct message {uint32_t kind;struct binder_transaction_data tr;uint64_t cookie;};
static inline void token(int fd){char x='x';CHECK(write(fd,&x,1)==1);}
static inline void wait_token(int fd){char x=0;CHECK(read(fd,&x,1)==1&&x=='x');}
static inline int64_t now_ns(void){struct timespec t;CHECK(clock_gettime(CLOCK_MONOTONIC,&t)==0);return (int64_t)t.tv_sec*1000000000LL+t.tv_nsec;}
static inline int commands(int fd,const void *data,size_t n,uint64_t *used){struct binder_write_read w={.write_size=n,.write_buffer=(uintptr_t)data};int rc=ioctl(fd,BINDER_WRITE_READ,&w);if(used)*used=w.write_consumed;if(rc==0)CHECK(w.write_consumed==n);return rc;}
static inline void command(int fd,uint32_t c){CHECK(commands(fd,&c,4,NULL)==0);}
static inline int read_raw(int fd,void *data,size_t n){struct binder_write_read w={.read_size=n,.read_buffer=(uintptr_t)data};int rc=ioctl(fd,BINDER_WRITE_READ,&w);return rc;}
static inline struct message receive(int fd){
    for(;;){
        unsigned char b[128]={0};struct binder_write_read w={.read_size=sizeof b,.read_buffer=(uintptr_t)b};CHECK(ioctl(fd,BINDER_WRITE_READ,&w)==0&&w.read_consumed>=4);
        struct message m={0};memcpy(&m.kind,b,4);
        if(m.kind==BR_INCREFS||m.kind==BR_ACQUIRE||m.kind==BR_RELEASE||m.kind==BR_DECREFS){
            CHECK(w.read_consumed==20);
            if(m.kind==BR_INCREFS||m.kind==BR_ACQUIRE){uint32_t c=m.kind==BR_INCREFS?BC_INCREFS_DONE:BC_ACQUIRE_DONE;memcpy(b,&c,4);CHECK(commands(fd,b,20,NULL)==0);}continue;
        }
        if(m.kind==BR_TRANSACTION||m.kind==BR_REPLY){CHECK(w.read_consumed==68);memcpy(&m.tr,b+4,64);}
        else if(m.kind==BR_DEAD_BINDER||m.kind==BR_CLEAR_DEATH_NOTIFICATION_DONE){CHECK(w.read_consumed==12);memcpy(&m.cookie,b+4,8);}
        else CHECK(w.read_consumed==4);
        return m;
    }
}
static inline struct endpoint endpoint(void){
    struct endpoint e={.fd=open("/dev/binder",O_RDWR|O_CLOEXEC)};CHECK(e.fd>=0);struct binder_version v={0};CHECK(ioctl(e.fd,BINDER_VERSION,&v)==0&&v.protocol_version==8);
    unsigned automatic=0;CHECK(ioctl(e.fd,BINDER_SET_MAX_THREADS,&automatic)==0);automatic=1;errno=0;CHECK(ioctl(e.fd,BINDER_SET_MAX_THREADS,&automatic)==-1&&errno==EOPNOTSUPP);
    e.map=mmap(NULL,MAP_BYTES,PROT_READ,MAP_PRIVATE,e.fd,0);CHECK(e.map!=MAP_FAILED);return e;
}
static inline void close_endpoint(struct endpoint e){CHECK(munmap(e.map,MAP_BYTES)==0);CHECK(close(e.fd)==0);}
static inline int send_payload(int fd,uint32_t command,uint32_t handle,uint32_t code,uint32_t flags,const void *data,size_t n,const uint64_t *offsets,size_t count){
    unsigned char b[68];struct binder_transaction_data tr={.target.handle=handle,.code=code,.flags=flags,.data_size=n,.offsets_size=count*8,.data.ptr.buffer=(uintptr_t)data,.data.ptr.offsets=(uintptr_t)offsets};memcpy(b,&command,4);memcpy(b+4,&tr,64);return commands(fd,b,sizeof b,NULL);
}
static inline void send_number(int fd,uint32_t command,uint32_t handle,uint32_t code){uint64_t data=code;CHECK(send_payload(fd,command,handle,code,TF_ACCEPT_FDS,&data,8,NULL,0)==0);}
static inline void free_buffer(int fd,binder_uintptr_t p){unsigned char b[12];uint32_t c=BC_FREE_BUFFER;memcpy(b,&c,4);memcpy(b+4,&p,8);CHECK(commands(fd,b,sizeof b,NULL)==0);}
static inline void handle_command(int fd,uint32_t command,uint32_t handle){unsigned char b[8];memcpy(b,&command,4);memcpy(b+4,&handle,4);CHECK(commands(fd,b,8,NULL)==0);}
static inline void death_command(int fd,uint32_t command,uint32_t handle,uint64_t cookie){unsigned char b[16];memcpy(b,&command,4);memcpy(b+4,&handle,4);memcpy(b+8,&cookie,8);CHECK(commands(fd,b,sizeof b,NULL)==0);}
static inline void death_done(int fd,uint64_t cookie){unsigned char b[12];uint32_t c=BC_DEAD_BINDER_DONE;memcpy(b,&c,4);memcpy(b+4,&cookie,8);CHECK(commands(fd,b,sizeof b,NULL)==0);}
static inline void no_work(int fd){int old=fcntl(fd,F_GETFL);CHECK(old>=0&&fcntl(fd,F_SETFL,old|O_NONBLOCK)==0);unsigned char b[128];errno=0;int rc=read_raw(fd,b,sizeof b);int error=errno;CHECK(fcntl(fd,F_SETFL,old)==0);CHECK(rc==-1&&error==EAGAIN);}
static inline void wait_child(pid_t child){int status=0;CHECK(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0);}


#endif
