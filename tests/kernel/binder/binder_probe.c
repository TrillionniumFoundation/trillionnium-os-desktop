// SPDX-License-Identifier: MPL-2.0
// Actual cross-process limited Binder v8 IPC. Never execute on the host.
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
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#define MAP_BYTES (16u * 4096u)
static unsigned checks;
static volatile sig_atomic_t interrupted;
static void interrupt_reader(int sig) { (void)sig; interrupted=1; }
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"Binder FAIL line %d: %s errno=%d\n",__LINE__,#x,errno); exit(1); } ++checks; } while(0)
struct endpoint { int fd; void *map; };
struct message { uint32_t kind; struct binder_transaction_data transaction; };
static struct endpoint endpoint(void) {
    struct endpoint e = {.fd=open("/dev/binder",O_RDWR|O_CLOEXEC)};
    CHECK(e.fd>=0);
    struct binder_version version={0};
    CHECK(ioctl(e.fd,BINDER_VERSION,&version)==0 && version.protocol_version==8);
    unsigned threads=1;
    CHECK(ioctl(e.fd,BINDER_SET_MAX_THREADS,&threads)==0);
    e.map=mmap(NULL,MAP_BYTES,PROT_READ,MAP_PRIVATE,e.fd,0);
    CHECK(e.map!=MAP_FAILED);
    return e;
}
static void close_endpoint(struct endpoint *e) {
    CHECK(munmap(e->map,MAP_BYTES)==0);
    CHECK(close(e->fd)==0);
    e->fd=-1;
}
static int write_commands(int fd,const void *buffer,size_t size,uint64_t *consumed) {
    struct binder_write_read wire={.write_size=size,.write_buffer=(uintptr_t)buffer};
    int rc=ioctl(fd,BINDER_WRITE_READ,&wire);
    if(consumed) *consumed=wire.write_consumed;
    return rc;
}
static void enter(int fd) { uint32_t command=BC_ENTER_LOOPER; CHECK(write_commands(fd,&command,4,NULL)==0); }
static void make_manager(struct endpoint *e) {
    CHECK(ioctl(e->fd,BINDER_SET_CONTEXT_MGR,0)==0);
    enter(e->fd);
}
static int read_bytes(int fd,void *bytes,size_t size,uint64_t *consumed) {
    struct binder_write_read wire={.read_size=size,.read_buffer=(uintptr_t)bytes};
    int rc=ioctl(fd,BINDER_WRITE_READ,&wire);
    if(consumed) *consumed=wire.read_consumed;
    return rc;
}
static struct message receive(int fd) {
    unsigned char bytes[128]={0}; uint64_t consumed=0;
    CHECK(read_bytes(fd,bytes,sizeof bytes,&consumed)==0);
    struct message result={0};
    CHECK(consumed>=4);
    memcpy(&result.kind,bytes,4);
    if(result.kind==BR_TRANSACTION || result.kind==BR_REPLY) {
        CHECK(consumed==68); memcpy(&result.transaction,bytes+4,64);
    } else CHECK(consumed==4);
    return result;
}
static void send_data(int fd,uint32_t kind,uint32_t code,const void *data,size_t size) {
    unsigned char stream[68];
    struct binder_transaction_data transaction={.code=code,.data_size=size,.data.ptr.buffer=(uintptr_t)data};
    memcpy(stream,&kind,4); memcpy(stream+4,&transaction,64);
    uint64_t consumed=0;
    CHECK(write_commands(fd,stream,sizeof stream,&consumed)==0 && consumed==sizeof stream);
}
static void transport_fault_send(int fd) {
    unsigned char stream[68];uint32_t kind=BC_TRANSACTION;
    struct binder_transaction_data tr={.code=0x1234,.data_size=12,.data.ptr.buffer=(uintptr_t)"request-one"};
    memcpy(stream,&kind,4);memcpy(stream+4,&tr,64);
    struct binder_write_read *wire=mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    CHECK(wire!=MAP_FAILED);
    *wire=(struct binder_write_read){.write_size=sizeof stream,.write_buffer=(uintptr_t)stream};
    CHECK(mprotect(wire,4096,PROT_READ)==0);
    CHECK(ioctl(fd,BINDER_WRITE_READ,wire)==-1&&errno==EFAULT);
    CHECK(wire->write_consumed==0);
    // The command was accepted before the final transport copyout fault. Do
    // not resend it: receive the actual completion and reply with fresh reads.
    CHECK(munmap(wire,4096)==0);
}
static void free_buffer(int fd,binder_uintptr_t address) {
    unsigned char stream[12]; uint32_t kind=BC_FREE_BUFFER;
    memcpy(stream,&kind,4);memcpy(stream+4,&address,8);
    CHECK(write_commands(fd,stream,sizeof stream,NULL)==0);
    CHECK(write_commands(fd,stream,sizeof stream,NULL)==-1 && errno==EINVAL);
}
static void expect_completion(int fd) { CHECK(receive(fd).kind==BR_TRANSACTION_COMPLETE); }
static void wait_child(pid_t pid) { int status=0; CHECK(waitpid(pid,&status,0)==pid); CHECK(WIFEXITED(status)&&WEXITSTATUS(status)==0); }
static void byte(int fd) { char value='x';CHECK(write(fd,&value,1)==1); }
static void await_byte(int fd) { char value=0;CHECK(read(fd,&value,1)==1&&value=='x'); }
static void unsupported(struct endpoint *e) {
    uint64_t consumed=42;
    struct binder_write_read empty={0}; CHECK(ioctl(e->fd,BINDER_WRITE_READ,&empty)==0);
    int flags=fcntl(e->fd,F_GETFL);CHECK(flags>=0);
    CHECK(fcntl(e->fd,F_SETFL,flags|O_NONBLOCK)==0);
    unsigned char empty_read[128];
    CHECK(read_bytes(e->fd,empty_read,sizeof empty_read,NULL)==-1&&errno==EAGAIN);
    CHECK(fcntl(e->fd,F_SETFL,flags)==0);
    struct sigaction action={.sa_handler=interrupt_reader};sigemptyset(&action.sa_mask);
    CHECK(sigaction(SIGUSR1,&action,NULL)==0);
    pid_t interrupter=fork();CHECK(interrupter>=0);
    if(interrupter==0) { usleep(20000);kill(getppid(),SIGUSR1);_exit(0); }
    CHECK(read_bytes(e->fd,empty_read,sizeof empty_read,NULL)==-1&&errno==EINTR&&interrupted);
    wait_child(interrupter);
    unsigned threads=2; CHECK(ioctl(e->fd,BINDER_SET_MAX_THREADS,&threads)==-1&&errno==EOPNOTSUPP);
    struct flat_binder_object object={0};
    CHECK(ioctl(e->fd,BINDER_SET_CONTEXT_MGR_EXT,&object)==-1&&errno==EOPNOTSUPP);
    unsigned char stream[68]={0}; uint32_t command=BC_TRANSACTION;
    struct binder_transaction_data tr={.offsets_size=8};
    memcpy(stream,&command,4);memcpy(stream+4,&tr,64);
    CHECK(write_commands(e->fd,stream,sizeof stream,&consumed)==-1&&errno==EOPNOTSUPP&&consumed==0);
    tr.offsets_size=0;tr.flags=TF_ONE_WAY;memcpy(stream+4,&tr,64);
    CHECK(write_commands(e->fd,stream,sizeof stream,NULL)==-1&&errno==EOPNOTSUPP);
    tr.flags=0;tr.target.handle=1;memcpy(stream+4,&tr,64);
    CHECK(write_commands(e->fd,stream,sizeof stream,NULL)==-1&&errno==EOPNOTSUPP);
    tr.target.handle=0;tr.data_size=4097;memcpy(stream+4,&tr,64);
    CHECK(write_commands(e->fd,stream,sizeof stream,NULL)==-1&&errno==EMSGSIZE);
    tr.data_size=1;tr.data.ptr.buffer=1;memcpy(stream+4,&tr,64);
    CHECK(write_commands(e->fd,stream,sizeof stream,NULL)==-1&&errno==EFAULT);
    CHECK(write_commands(e->fd,stream,67,NULL)==-1&&errno==EINVAL);
    command=BC_REQUEST_DEATH_NOTIFICATION;memcpy(stream,&command,4);
    CHECK(write_commands(e->fd,stream,4,NULL)==-1&&errno==EOPNOTSUPP);
    CHECK(mprotect(e->map,4096,PROT_NONE)==0);
    CHECK(mprotect(e->map,4096,PROT_READ)==0);
    CHECK(mprotect(e->map,MAP_BYTES,PROT_READ|PROT_WRITE)==-1&&errno==EACCES);
    CHECK(mprotect(e->map,MAP_BYTES,PROT_READ|PROT_EXEC)==-1&&errno==EACCES);
    CHECK(mremap(e->map,MAP_BYTES,MAP_BYTES,MREMAP_MAYMOVE|MREMAP_FIXED,(void *)0x40000000)==MAP_FAILED&&errno==EINVAL);
    CHECK(mmap(e->map,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_FIXED,e->fd,0)==MAP_FAILED&&errno==EACCES);
    struct binder_version still_live={0};CHECK(ioctl(e->fd,BINDER_VERSION,&still_live)==0);
    CHECK(mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE,e->fd,0)==MAP_FAILED&&errno==EACCES);
    CHECK(mmap(NULL,4096,PROT_READ,MAP_PRIVATE,e->fd,0)==MAP_FAILED&&errno==EBUSY);
}
static void *foreign_thread(void *arg) {
    struct binder_version version={0}; int fd=*(int *)arg;
    CHECK(ioctl(fd,BINDER_VERSION,&version)==-1&&errno==EPERM);
    return NULL;
}
static void roundtrip(void) {
    struct endpoint server=endpoint(); make_manager(&server); unsupported(&server);
    pthread_t thread;CHECK(pthread_create(&thread,NULL,foreign_thread,&server.fd)==0);CHECK(pthread_join(thread,NULL)==0);
    int ready[2];CHECK(pipe(ready)==0);
    pid_t client=fork();CHECK(client>=0);
    if(client==0) {
        close(ready[0]);
        struct binder_version version={0};
        CHECK(ioctl(server.fd,BINDER_VERSION,&version)==-1&&errno==EPERM);
        pid_t reader=fork();CHECK(reader>=0);
        if(reader==0) { volatile unsigned char value=*(volatile unsigned char *)server.map;(void)value;_exit(99); }
        int status=0;CHECK(waitpid(reader,&status,0)==reader&&WIFSIGNALED(status)&&WTERMSIG(status)==SIGSEGV);
        close(server.fd);
        struct endpoint own=endpoint();CHECK(setuid(1001)==0);
        transport_fault_send(own.fd);
        expect_completion(own.fd);byte(ready[1]);
        struct message response=receive(own.fd);
        CHECK(response.kind==BR_REPLY && response.transaction.data_size==10);
        CHECK(response.transaction.sender_pid==0&&response.transaction.sender_euid==0);
        CHECK(memcmp((void *)(uintptr_t)response.transaction.data.ptr.buffer,"reply-one",10)==0);
        free_buffer(own.fd,response.transaction.data.ptr.buffer);
        send_data(own.fd,BC_TRANSACTION,0x5678,"will-close",11);
        expect_completion(own.fd);
        CHECK(receive(own.fd).kind==BR_DEAD_REPLY);
        close_endpoint(&own);close(ready[1]);_exit(0);
    }
    close(ready[1]);await_byte(ready[0]);
    unsigned char small[4];uint64_t consumed=9;
    CHECK(read_bytes(server.fd,small,sizeof small,&consumed)==-1&&errno==ENOSPC&&consumed==0);
    CHECK(read_bytes(server.fd,(void *)1,128,&consumed)==-1&&errno==EFAULT&&consumed==0);
    struct message request=receive(server.fd);
    CHECK(request.kind==BR_TRANSACTION && request.transaction.code==0x1234);
    CHECK(request.transaction.sender_pid==client&&request.transaction.sender_euid==1001);
    CHECK(request.transaction.data_size==12 && request.transaction.offsets_size==0);
    CHECK(memcmp((void *)(uintptr_t)request.transaction.data.ptr.buffer,"request-one",12)==0);
    free_buffer(server.fd,request.transaction.data.ptr.buffer);
    send_data(server.fd,BC_REPLY,0,"reply-one",10);expect_completion(server.fd);
    request=receive(server.fd);CHECK(request.kind==BR_TRANSACTION&&request.transaction.code==0x5678);
    // Unmapping even a subset closes the endpoint and wakes the real caller.
    CHECK(munmap(server.map,4096)==0);
    struct binder_version version={0};CHECK(ioctl(server.fd,BINDER_VERSION,&version)==-1&&errno==ECONNREFUSED);
    CHECK(munmap((char *)server.map+4096,MAP_BYTES-4096)==0);CHECK(close(server.fd)==0);
    wait_child(client);close(ready[0]);
    puts("binder_cross_process_reply_identity_readonly_copyfault_close\tPASS");
}
static void killed_manager(void) {
    int ready[2],seen[2];CHECK(pipe(ready)==0&&pipe(seen)==0);
    pid_t server=fork();CHECK(server>=0);
    if(server==0) {
        close(ready[0]);close(seen[0]);
        struct endpoint own=endpoint();make_manager(&own);byte(ready[1]);
        struct message request=receive(own.fd);CHECK(request.kind==BR_TRANSACTION);
        byte(seen[1]);for(;;) pause();
    }
    close(ready[1]);close(seen[1]);await_byte(ready[0]);
    struct endpoint own=endpoint();send_data(own.fd,BC_TRANSACTION,77,"exit",5);expect_completion(own.fd);
    await_byte(seen[0]);CHECK(kill(server,SIGKILL)==0);
    CHECK(receive(own.fd).kind==BR_DEAD_REPLY);
    int status=0;CHECK(waitpid(server,&status,0)==server&&WIFSIGNALED(status)&&WTERMSIG(status)==SIGKILL);
    close_endpoint(&own);close(ready[0]);close(seen[0]);
    // The new manager cannot inherit the old manager's request/identity.
    struct endpoint next=endpoint();make_manager(&next);close_endpoint(&next);
    puts("binder_manager_SIGKILL_wakeup_and_new_context\tPASS");
}
static pid_t pending_client(uint32_t code,int ready) {
    pid_t child=fork();CHECK(child>=0);
    if(child==0) {
        struct endpoint own=endpoint();send_data(own.fd,BC_TRANSACTION,code,"queued",7);
        expect_completion(own.fd);byte(ready);
        if(code==101) for(;;) pause();
        struct message reply=receive(own.fd);CHECK(reply.kind==BR_REPLY);
        free_buffer(own.fd,reply.transaction.data.ptr.buffer);close_endpoint(&own);_exit(0);
    }
    return child;
}
static void prepared_sender_exit(void) {
    struct endpoint server=endpoint();make_manager(&server);
    int ready[2];CHECK(pipe(ready)==0);
    pid_t first=pending_client(101,ready[1]);await_byte(ready[0]);
    CHECK(read_bytes(server.fd,(void *)1,128,NULL)==-1&&errno==EFAULT);
    CHECK(kill(first,SIGKILL)==0);int status=0;
    CHECK(waitpid(first,&status,0)==first&&WIFSIGNALED(status));
    pid_t second=pending_client(102,ready[1]);await_byte(ready[0]);
    struct message saved=receive(server.fd);
    CHECK(saved.kind==BR_TRANSACTION&&saved.transaction.code==101);
    free_buffer(server.fd,saved.transaction.data.ptr.buffer);
    unsigned char stream[68];uint32_t command=BC_REPLY;
    struct binder_transaction_data tr={0};memcpy(stream,&command,4);memcpy(stream+4,&tr,64);
    uint64_t consumed=99;CHECK(write_commands(server.fd,stream,sizeof stream,&consumed)==-1&&errno==EINVAL&&consumed==0);
    struct message current=receive(server.fd);
    CHECK(current.kind==BR_TRANSACTION&&current.transaction.code==102);
    free_buffer(server.fd,current.transaction.data.ptr.buffer);
    send_data(server.fd,BC_REPLY,0,"ok",3);expect_completion(server.fd);
    wait_child(second);close_endpoint(&server);close(ready[0]);close(ready[1]);
    puts("binder_prepared_copyout_survives_sender_exit_without_queue_mix	PASS");
}
static void receive_capacity(void) {
    struct endpoint server=endpoint();make_manager(&server);
    pid_t client=fork();CHECK(client>=0);
    if(client==0) {
        struct endpoint own=endpoint();
        for(unsigned i=0;i<17;++i) {
            send_data(own.fd,BC_TRANSACTION,200+i,"capacity",9);expect_completion(own.fd);
            struct message reply=receive(own.fd);CHECK(reply.kind==BR_REPLY);
            free_buffer(own.fd,reply.transaction.data.ptr.buffer);
        }
        close_endpoint(&own);_exit(0);
    }
    binder_uintptr_t addresses[16];
    for(unsigned i=0;i<17;++i) {
        if(i==16) {
            unsigned char bytes[128];uint64_t consumed=99;
            CHECK(read_bytes(server.fd,bytes,sizeof bytes,&consumed)==-1&&errno==ENOSPC&&consumed==0);
            free_buffer(server.fd,addresses[0]);
        }
        struct message request=receive(server.fd);
        CHECK(request.kind==BR_TRANSACTION&&request.transaction.code==200+i);
        CHECK(memcmp((void *)(uintptr_t)request.transaction.data.ptr.buffer,"capacity",9)==0);
        if(i<16) addresses[i]=request.transaction.data.ptr.buffer;
        else CHECK(request.transaction.data.ptr.buffer==addresses[0]);
        send_data(server.fd,BC_REPLY,0,"ok",3);expect_completion(server.fd);
    }
    wait_child(client);close_endpoint(&server);
    puts("binder_receive_capacity_backpressure_free_and_reuse\tPASS");
}
static void queue_capacity(void) {
    struct endpoint server=endpoint();make_manager(&server);
    pid_t children[16];int ready[2];CHECK(pipe(ready)==0);
    for(unsigned i=0;i<16;++i) {
        children[i]=fork();CHECK(children[i]>=0);
        if(children[i]==0) {
            struct endpoint own=endpoint();
            unsigned char stream[68];uint32_t command=BC_TRANSACTION;
            struct binder_transaction_data tr={.code=300+i,.data_size=1,.data.ptr.buffer=(uintptr_t)"q"};
            memcpy(stream,&command,4);memcpy(stream+4,&tr,64);uint64_t consumed=0;
            if(i==15) CHECK(write_commands(own.fd,stream,sizeof stream,&consumed)==-1&&errno==EAGAIN&&consumed==0);
            else { CHECK(write_commands(own.fd,stream,sizeof stream,&consumed)==0&&consumed==68);expect_completion(own.fd); }
            byte(ready[1]);
            if(i<15) { struct message reply=receive(own.fd);CHECK(reply.kind==BR_REPLY);free_buffer(own.fd,reply.transaction.data.ptr.buffer); }
            close_endpoint(&own);_exit(0);
        }
        await_byte(ready[0]);
    }
    for(unsigned i=0;i<15;++i) {
        struct message request=receive(server.fd);CHECK(request.kind==BR_TRANSACTION&&request.transaction.code==300+i);
        free_buffer(server.fd,request.transaction.data.ptr.buffer);
        // Completion is queued behind older incoming transactions. The reserved
        // slot must permit replying even at the maximum request occupancy.
        send_data(server.fd,BC_REPLY,0,"ok",3);
    }
    for(unsigned i=0;i<15;++i) expect_completion(server.fd);
    for(unsigned i=0;i<16;++i) wait_child(children[i]);
    close_endpoint(&server);close(ready[0]);close(ready[1]);
    puts("binder_request_queue_bound_reserves_reply_progress\tPASS");
}
static void exec_boundary(void) {
    pid_t child=fork();CHECK(child>=0);
    if(child==0) {
        struct endpoint own=endpoint();CHECK(fcntl(own.fd,F_SETFD,0)==0);
        char fd[24];snprintf(fd,sizeof fd,"%d",own.fd);
        execl("/bin/safety-binder","safety-binder","--old-fd",fd,(char *)NULL);
        _exit(98);
    }
    wait_child(child);puts("binder_exec_old_image_fd_rejected\tPASS");
}
#define BUDGET_BASE "/sys/fs/cgroup/binder-map-budget"
#define BUDGET_WORK BUDGET_BASE "/worker"
static void budget_write(const char *path,const char *value) {
    int fd=open(path,O_WRONLY|O_CLOEXEC);CHECK(fd>=0);
    size_t size=strlen(value);ssize_t wrote=write(fd,value,size);
    if(wrote!=(ssize_t)size)fprintf(stderr,"Binder budget write path=%s value=%s returned=%zd errno=%d\n",path,value,wrote,errno);
    CHECK(wrote==(ssize_t)size);CHECK(close(fd)==0);
}
static unsigned long budget_value(const char *attribute,const char *key) {
    char path[256],data[512]={0};snprintf(path,sizeof path,"%s/%s",BUDGET_WORK,attribute);
    int fd=open(path,O_RDONLY|O_CLOEXEC);CHECK(fd>=0);
    ssize_t n=read(fd,data,sizeof(data)-1);CHECK(n>0);CHECK(close(fd)==0);
    if(!key)return strtoul(data,NULL,10);
    for(char *line=data;*line;) {
        if(!strncmp(line,key,strlen(key))&&line[strlen(key)]==' ')
            return strtoul(line+strlen(key)+1,NULL,10);
        char *next=strchr(line,'\n');if(!next)break;line=next+1;
    }
    CHECK(0);return 0;
}
__attribute__((noinline)) static void budget_warm(void) {
    volatile unsigned char stack[64*1024];
    for(size_t i=0;i<sizeof stack;i+=4096)stack[i]=1;
    (void)budget_value("hepta.page.current",NULL);
    (void)budget_value("hepta.page.stat","private");
    (void)budget_value("hepta.page.stat","page_table");
    (void)budget_value("hepta.page.events","max");
    // Keep failure reporting and errno's TLS page out of the measured budget.
    fputs("binder_mapping_budget_measurement_warmed\n",stderr);errno=0;
    budget_write(BUDGET_WORK "/hepta.page.max","max");usleep(1000);
}
static void budget_mapping_child(void) {
    char pid[32];snprintf(pid,sizeof pid,"%d",getpid());
    budget_write(BUDGET_WORK "/cgroup.procs",pid);budget_warm();
    int fd=open("/dev/binder",O_RDWR|O_CLOEXEC);CHECK(fd>=0);
    struct binder_version version={0};CHECK(ioctl(fd,BINDER_VERSION,&version)==0);
    unsigned long private_before=budget_value("hepta.page.stat","private");
    unsigned long tables_before=budget_value("hepta.page.stat","page_table");
    unsigned long denied_before=budget_value("hepta.page.events","max");
    unsigned long before=budget_value("hepta.page.current",NULL);
    char ceiling[32];snprintf(ceiling,sizeof ceiling,"%lu",before+MAP_BYTES+3*4096UL);
    budget_write(BUDGET_WORK "/hepta.page.max",ceiling);
    // The first page needs three fresh tables. Crossing a PML4 boundary then
    // needs another path, after all 16 receive frames have been reserved.
    void *target=(void *)(((uintptr_t)1<<40)-4096);
    errno=0;void *mapped=mmap(target,MAP_BYTES,PROT_READ,MAP_PRIVATE|MAP_FIXED_NOREPLACE,fd,0);
    CHECK(mapped==MAP_FAILED&&errno==ENOMEM);
    CHECK(budget_value("hepta.page.events","max")>denied_before);
    CHECK(budget_value("hepta.page.stat","page_table")>=tables_before+3*4096UL);
    // Failure may retain charged empty table nodes. All receive data frames,
    // including the briefly published prefix, must lose their final reference.
    unsigned observations=0;unsigned long held;
    do { held=budget_value("hepta.page.stat","private");if(held<=private_before)break;usleep(1000); }
    while(++observations<1000);
    CHECK(held==private_before);
    budget_write(BUDGET_WORK "/hepta.page.max","max");
    // No receive area or VMA may be published by the failed mmap. Reuse both
    // the same endpoint and exactly the same requested range successfully.
    mapped=mmap(target,MAP_BYTES,PROT_READ,MAP_PRIVATE|MAP_FIXED_NOREPLACE,fd,0);
    CHECK(mapped==target);
    CHECK(((volatile unsigned char *)mapped)[0]==0&&((volatile unsigned char *)mapped)[MAP_BYTES-1]==0);
    CHECK(munmap(mapped,MAP_BYTES)==0);CHECK(close(fd)==0);
    puts("binder_partial_mapping_budget_failure_refund_and_retry\tPASS");
    _exit(0);
}
static void budget_mapping(void) {
    budget_write("/sys/fs/cgroup/cgroup.subtree_control","+memory");
    CHECK(mkdir(BUDGET_BASE,0755)==0);
    budget_write(BUDGET_BASE "/cgroup.subtree_control","+memory");
    CHECK(mkdir(BUDGET_WORK,0755)==0);
    pid_t child=fork();CHECK(child>=0);
    if(child==0)budget_mapping_child();
    wait_child(child);
}
static void alarmed(int sig) { (void)sig;_exit(124); }
int main(int argc,char **argv) {
    if(argc==3 && strcmp(argv[1],"--old-fd")==0) {
        int fd=atoi(argv[2]);struct binder_version version={0};
        CHECK(ioctl(fd,BINDER_VERSION,&version)==-1&&errno==EPERM);CHECK(close(fd)==0);return 0;
    }
    signal(SIGALRM,alarmed);alarm(20);setbuf(stdout,NULL);
    if(argc==2&&strcmp(argv[1],"--budget-only")==0) {
        budget_mapping();printf("{\"passed\":true,\"checks\":%u,\"scope\":\"binder_mapping_budget\"}\n",checks);return 0;
    }
    budget_mapping();
    roundtrip();killed_manager();prepared_sender_exit();receive_capacity();queue_capacity();exec_boundary();
    printf("{\"passed\":true,\"checks\":%u,\"scope\":\"synchronous_handle0_bytes\",\"objects\":false,\"fd_transfer\":false,\"death_notifications\":false,\"android_boot\":false}\n",checks);
    return 0;
}
