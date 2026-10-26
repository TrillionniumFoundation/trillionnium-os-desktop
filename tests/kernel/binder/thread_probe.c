// SPDX-License-Identifier: MPL-2.0
// Actual shared-open Binder threads. Execute only in the isolated guest.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/android/binder.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

#define MAP_BYTES (16u * 4096u)
static unsigned checks;
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"Binder threads FAIL line %d: %s errno=%d pid=%ld tid=%ld\n",__LINE__,#x,errno,(long)getpid(),syscall(SYS_gettid)); exit(1); } __atomic_fetch_add(&checks,1,__ATOMIC_RELAXED); } while(0)
struct endpoint { int fd; void *map; };
struct message { uint32_t kind; struct binder_transaction_data tr; };
static struct endpoint endpoint(void) {
    struct endpoint e = {.fd=open("/dev/binder",O_RDWR|O_CLOEXEC)};
    CHECK(e.fd>=0);
    struct binder_version v={0}; CHECK(ioctl(e.fd,BINDER_VERSION,&v)==0&&v.protocol_version==8);
    unsigned automatic_threads=0; CHECK(ioctl(e.fd,BINDER_SET_MAX_THREADS,&automatic_threads)==0);
    e.map=mmap(NULL,MAP_BYTES,PROT_READ,MAP_PRIVATE,e.fd,0); CHECK(e.map!=MAP_FAILED);
    return e;
}
static void close_endpoint(struct endpoint e) { CHECK(munmap(e.map,MAP_BYTES)==0); CHECK(close(e.fd)==0); }
static int commands(int fd,const void *p,size_t n) {
    struct binder_write_read w={.write_size=n,.write_buffer=(uintptr_t)p};
    int result=ioctl(fd,BINDER_WRITE_READ,&w);
    if(result==0) CHECK(w.write_consumed==n);
    return result;
}
static int send_data(int fd,uint32_t command,uint32_t code,uint64_t data) {
    unsigned char bytes[68];struct binder_transaction_data tr={.code=code,.data_size=8,.data.ptr.buffer=(uintptr_t)&data};
    memcpy(bytes,&command,4);memcpy(bytes+4,&tr,64);return commands(fd,bytes,sizeof bytes);
}
static int read_raw(int fd,void *out,size_t n,uint64_t *got) {
    struct binder_write_read w={.read_size=n,.read_buffer=(uintptr_t)out};int result=ioctl(fd,BINDER_WRITE_READ,&w);if(got)*got=w.read_consumed;return result;
}
static struct message receive(int fd) {
    unsigned char bytes[128]={0};uint64_t got=0;CHECK(read_raw(fd,bytes,sizeof bytes,&got)==0);CHECK(got>=4);
    struct message m={0};memcpy(&m.kind,bytes,4);
    if(m.kind==BR_TRANSACTION||m.kind==BR_REPLY){CHECK(got==68);memcpy(&m.tr,bytes+4,64);}else CHECK(got==4);
    return m;
}
static void free_buffer(int fd,binder_uintptr_t p) { unsigned char bytes[12];uint32_t c=BC_FREE_BUFFER;memcpy(bytes,&c,4);memcpy(bytes+4,&p,8);CHECK(commands(fd,bytes,sizeof bytes)==0); }
static void token(int fd) { char c='x';CHECK(write(fd,&c,1)==1); }
static void wait_token(int fd) { char c=0;CHECK(read(fd,&c,1)==1&&c=='x'); }
static void barrier(pthread_barrier_t *p) { int rc=pthread_barrier_wait(p);CHECK(rc==0||rc==PTHREAD_BARRIER_SERIAL_THREAD); }
static void no_readable_event(int fd) {
    int f=fcntl(fd,F_GETFL);CHECK(f>=0);CHECK(fcntl(fd,F_SETFL,f|O_NONBLOCK)==0);
    unsigned char b[128];errno=0;int rc=read_raw(fd,b,sizeof b,NULL);int error=errno;
    CHECK(fcntl(fd,F_SETFL,f)==0);CHECK(rc==-1&&error==EAGAIN);
}
static void shared_open_version(int fd,const char *role,unsigned index) {
    struct binder_version v={0};errno=0;int rc=ioctl(fd,BINDER_VERSION,&v);int error=errno;
    printf("binder_threads_actual_shared_open role=%s worker=%u pid=%ld tid=%ld fd=%d rc=%d error=%d\n",role,index,(long)getpid(),syscall(SYS_gettid),fd,rc,error);fflush(stdout);
    CHECK(syscall(SYS_gettid)!=(long)getpid());CHECK(rc==0&&v.protocol_version==8);
}
struct server {
    struct endpoint endpoint;
    pid_t client;
    pthread_barrier_t ready,incoming;
    int go[2],reverse[2],reply_ready;
};
struct server_arg { struct server *shared; unsigned index; };
static void *serve(void *p) {
    struct server_arg *a=p;struct server *s=a->shared;int fd=s->endpoint.fd;
    shared_open_version(fd,"server",a->index);
    uint32_t enter=BC_ENTER_LOOPER;CHECK(commands(fd,&enter,4)==0);barrier(&s->ready);
    struct message m=receive(fd);CHECK(m.kind==BR_TRANSACTION&&m.tr.sender_pid==s->client&&m.tr.data_size==8);
    uint64_t value=0;memcpy(&value,(void *)(uintptr_t)m.tr.data.ptr.buffer,8);CHECK(value==(uint64_t)m.tr.code);
    barrier(&s->incoming);wait_token(s->go[0]);
    if(a->index==0)wait_token(s->reverse[0]);
    CHECK(send_data(fd,BC_REPLY,m.tr.code+1000,value+10000)==0);
    token(s->reply_ready);
    if(a->index==1)token(s->reverse[1]);
    CHECK(receive(fd).kind==BR_TRANSACTION_COMPLETE);free_buffer(fd,m.tr.data.ptr.buffer);
    uint32_t leave=BC_EXIT_LOOPER;CHECK(commands(fd,&leave,4)==0);return NULL;
}
struct client {
    struct endpoint endpoint;
    pthread_barrier_t sent,read_go;
};
struct client_arg { struct client *shared; unsigned index; };
static void *call(void *p) {
    struct client_arg *a=p;struct client *s=a->shared;int fd=s->endpoint.fd;unsigned code=100+a->index;
    shared_open_version(fd,"client",a->index);CHECK(send_data(fd,BC_TRANSACTION,code,code)==0);
    CHECK(receive(fd).kind==BR_TRANSACTION_COMPLETE);barrier(&s->sent);barrier(&s->read_go);
    struct message m=receive(fd);CHECK(m.kind==BR_REPLY&&m.tr.code==code+1000&&m.tr.sender_pid==0&&m.tr.data_size==8);
    uint64_t value=0;memcpy(&value,(void *)(uintptr_t)m.tr.data.ptr.buffer,8);CHECK(value==code+10000);
    free_buffer(fd,m.tr.data.ptr.buffer);return NULL;
}
static void client_process(int start,int reply_ready,int inherited) {
    struct binder_version v={0};errno=0;CHECK(ioctl(inherited,BINDER_VERSION,&v)==-1&&errno==EPERM);CHECK(close(inherited)==0);
    struct client shared={.endpoint=endpoint()};wait_token(start);
    CHECK(pthread_barrier_init(&shared.sent,NULL,3)==0);CHECK(pthread_barrier_init(&shared.read_go,NULL,3)==0);
    pthread_t t[2];struct client_arg a[2];
    for(unsigned i=0;i<2;i++){a[i]=(struct client_arg){.shared=&shared,.index=i};CHECK(pthread_create(&t[i],NULL,call,&a[i])==0);}
    barrier(&shared.sent);wait_token(reply_ready);wait_token(reply_ready);
    // A third actual thread cannot consume either other caller's queued reply.
    no_readable_event(shared.endpoint.fd);barrier(&shared.read_go);
    for(unsigned i=0;i<2;i++)CHECK(pthread_join(t[i],NULL)==0);
    CHECK(pthread_barrier_destroy(&shared.sent)==0);CHECK(pthread_barrier_destroy(&shared.read_go)==0);
    close_endpoint(shared.endpoint);_exit(0);
}
int main(void) {
    setbuf(stdout,NULL);alarm(25);
    int start[2],reply_ready[2];CHECK(pipe(start)==0&&pipe(reply_ready)==0);
    struct server shared={.endpoint=endpoint(),.reply_ready=reply_ready[1]};
    CHECK(ioctl(shared.endpoint.fd,BINDER_SET_CONTEXT_MGR,0)==0);
    CHECK(pipe(shared.go)==0&&pipe(shared.reverse)==0);
    CHECK(pthread_barrier_init(&shared.ready,NULL,3)==0);CHECK(pthread_barrier_init(&shared.incoming,NULL,3)==0);
    pid_t child=fork();CHECK(child>=0);
    if(child==0)client_process(start[0],reply_ready[0],shared.endpoint.fd);
    shared.client=child;pthread_t t[2];struct server_arg a[2];
    for(unsigned i=0;i<2;i++){a[i]=(struct server_arg){.shared=&shared,.index=i};CHECK(pthread_create(&t[i],NULL,serve,&a[i])==0);}
    barrier(&shared.ready);token(start[1]);barrier(&shared.incoming);
    // This opener did not receive either request and may not reply for a worker.
    errno=0;CHECK(send_data(shared.endpoint.fd,BC_REPLY,777,777)==-1&&errno==EINVAL);
    no_readable_event(shared.endpoint.fd);token(shared.go[1]);token(shared.go[1]);
    for(unsigned i=0;i<2;i++)CHECK(pthread_join(t[i],NULL)==0);
    int status=0;CHECK(waitpid(child,&status,0)==child&&WIFEXITED(status)&&WEXITSTATUS(status)==0);
    CHECK(pthread_barrier_destroy(&shared.ready)==0);CHECK(pthread_barrier_destroy(&shared.incoming)==0);
    close_endpoint(shared.endpoint);
    for(unsigned i=0;i<2;i++){CHECK(close(start[i])==0);CHECK(close(reply_ready[i])==0);CHECK(close(shared.go[i])==0);CHECK(close(shared.reverse[i])==0);}
    puts("binder_threads_two_actual_callers_two_shared_open_workers_reverse_reply_ownership\tPASS");
    printf("binder_threads_parent_checks=%u\n",checks);return 0;
}
