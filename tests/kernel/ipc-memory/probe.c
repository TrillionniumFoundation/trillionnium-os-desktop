// SPDX-License-Identifier: MPL-2.0
// Guest-only physical IPC-buffer admission and lifetime checks.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/resource.h>
#include <sys/mman.h>
#include <sys/eventfd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define ROOT "/sys/fs/cgroup/ipc-memory"
#define WORK ROOT "/work"
#define RECOVER ROOT "/recover"
#define PAGE 4096UL
#define RING (16*PAGE)
static unsigned checks;
static void check(const char *name,int ok) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n",name,ok?"true":"false");
    if(!ok) {fprintf(stderr,"IPC FAIL %s errno=%d\n",name,errno);exit(1);} ++checks;
}
static int write_file(const char *path,const char *text) {
    int fd=open(path,O_WRONLY|O_CLOEXEC);if(fd<0)return -1;
    size_t size=strlen(text);ssize_t n=write(fd,text,size);int error=errno;close(fd);errno=error;
    return n==(ssize_t)size?0:-1;
}
static unsigned long value(const char *group,const char *attr,const char *key) {
    char path[256],data[512]={0};snprintf(path,sizeof(path),"%s/%s",group,attr);
    int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0)return ~0UL;
    ssize_t n=read(fd,data,sizeof(data)-1);close(fd);if(n<=0)return ~0UL;
    if(!key)return strtoul(data,NULL,10);
    for(char *line=data;*line;) {
        if(!strncmp(line,key,strlen(key))&&line[strlen(key)]==' ')return strtoul(line+strlen(key)+1,NULL,10);
        char *next=strchr(line,'\n');if(!next)break;line=next+1;
    }
    return ~0UL;
}
static void join(const char *group) {
    char path[256],pid[32];snprintf(path,sizeof(path),"%s/cgroup.procs",group);
    snprintf(pid,sizeof(pid),"%d",getpid());check("join_actual_group",write_file(path,pid)==0);
}
static void ceiling(const char *group,unsigned long limit) {
    char path[256],text[64];snprintf(path,sizeof(path),"%s/hepta.page.max",group);
    snprintf(text,sizeof(text),"%lu",limit);check("set_actual_page_ceiling",write_file(path,text)==0);
}
static void unlimited(const char *group) {
    char path[256];snprintf(path,sizeof(path),"%s/hepta.page.max",group);
    check("restore_page_ceiling",write_file(path,"max")==0);
}
static unsigned long await_ipc(const char *group,unsigned long expected) {
    unsigned long actual=value(group,"hepta.page.stat","ipc");unsigned observations=0;
    while(actual!=expected&&observations++<1000) {
        struct timespec delay={0,1000000};nanosleep(&delay,NULL);actual=value(group,"hepta.page.stat","ipc");
    }
    printf("{\"ipc_observed\":%lu,\"ipc_expected\":%lu,\"observations\":%u}\n",actual,expected,observations);
    return actual;
}
__attribute__((noinline)) static void warm(void) {
    volatile unsigned char stack[64*1024];for(size_t i=0;i<sizeof(stack);i+=PAGE)stack[i]=1;
    check("ipc_stat_available",value(WORK,"hepta.page.stat","ipc")!=~0UL);
    (void)value(WORK,"hepta.page.current",NULL);(void)value(WORK,"hepta.page.events","max");
    (void)value(ROOT,"hepta.page.current",NULL);(void)value(ROOT,"hepta.page.events","max");
    unlimited(WORK);unlimited(ROOT);fputs("ipc_measurement_paths_warmed\n",stderr);errno=0;
}
static void pair_create(int kind,int pair[2]) {
    int result=kind==0?pipe2(pair,O_CLOEXEC):socketpair(AF_UNIX,kind==1?SOCK_STREAM:SOCK_SEQPACKET,0,pair);
    check("create_actual_pipe_or_socketpair",result==0);
}
static void pair_positive(int kind) {
    join(WORK);warm();int pair[2];pair_create(kind,pair);
    unsigned long bytes=kind==0?RING:2*RING;
    check("physical_backing_has_exact_ipc_charge",value(WORK,"hepta.page.stat","ipc")==bytes);
    check("ancestor_has_same_ipc_charge",value(ROOT,"hepta.page.stat","ipc")==bytes);
    join(RECOVER);
    char input[128],output[128];memset(input,0x57,sizeof(input));
    check("migrated_holder_uses_original_buffer",write(pair[1],input,sizeof(input))==(ssize_t)sizeof(input)&&read(pair[0],output,sizeof(output))==(ssize_t)sizeof(output)&&!memcmp(input,output,sizeof(input)));
    check("migration_does_not_transfer_original_owner",value(WORK,"hepta.page.stat","ipc")==bytes&&value(RECOVER,"hepta.page.stat","ipc")==0);
    check("close_first_endpoint",close(pair[0])==0);
    check("peer_reference_retains_all_real_frames",value(WORK,"hepta.page.stat","ipc")==bytes);
    check("close_final_endpoint",close(pair[1])==0);
    check("last_endpoint_refunds_original_owner",await_ipc(WORK,0)==0&&value(ROOT,"hepta.page.stat","ipc")==0);
}
static void pair_negative(int kind,int ancestor) {
    join(WORK);warm();
    int probe=open("/dev/null",O_RDWR|O_CLOEXEC);check("open_fd_observer",probe>=0);
    int expected=fcntl(probe,F_DUPFD_CLOEXEC,32);check("capture_unused_fd",expected>=32);check("release_observer_fd",close(expected)==0);
    unsigned long leaf_events=value(WORK,"hepta.page.events","max"),root_events=value(ROOT,"hepta.page.events","max");
    const char *limited=ancestor?ROOT:WORK;
    unsigned long before=value(limited,"hepta.page.current",NULL);
    // A stream pair admits one real ring, then refuses the second. A pipe
    // refuses its one full ring at one page below its physical requirement.
    unsigned long extra=kind==0?RING-PAGE:RING;
    ceiling(limited,before+extra);
    int pair[2]={12345,23456};errno=0;
    int result=kind==0?pipe2(pair,O_CLOEXEC):socketpair(AF_UNIX,kind==1?SOCK_STREAM:SOCK_SEQPACKET,0,pair);
    int error=errno;
    check("insufficient_backing_returns_enomem",result==-1&&error==ENOMEM);
    check("failed_creation_does_not_publish_user_fds",pair[0]==12345&&pair[1]==23456);
    int next=fcntl(probe,F_DUPFD_CLOEXEC,32);
    check("failed_creation_has_no_fd_reservation_leak",next==expected);
    check("release_fd_after_denial",close(next)==0);
    check("failed_creation_rolls_back_all_ipc_frames",value(WORK,"hepta.page.stat","ipc")==0&&value(ROOT,"hepta.page.stat","ipc")==0);
    check("only_rejecting_level_records_denial",value(WORK,"hepta.page.events","max")==leaf_events+(ancestor?0:1)&&value(ROOT,"hepta.page.events","max")==root_events+(ancestor?1:0));
    unlimited(limited);pair_create(kind,pair);
    check("same_process_can_retry_after_capacity_restored",value(WORK,"hepta.page.stat","ipc")== (kind==0?RING:2*RING));
    check("close_retried_pair",close(pair[0])==0&&close(pair[1])==0);check("close_fd_observer",close(probe)==0);
    check("retry_final_backing_refund",await_ipc(WORK,0)==0);
}
static void byte_send(int fd) {char byte='x';check("send_sync_byte",write(fd,&byte,1)==1);}
static void byte_recv(int fd) {char byte=0;check("receive_sync_byte",read(fd,&byte,1)==1&&byte=='x');}
static void child_status(pid_t child) {int status=0;check("wait_actual_child",waitpid(child,&status,0)==child);check("child_completed_all_checks",WIFEXITED(status)&&WEXITSTATUS(status)==0);}
static void inherited_reference(void) {
    join(WORK);warm();int pair[2];pair_create(1,pair);
    int release=eventfd(0,EFD_CLOEXEC);check("create_reference_release_barrier",release>=0);
    pid_t child=fork();check("create_inherited_descriptor_holder",child>=0);
    if(child==0) {
        join(RECOVER);uint64_t signal_value=0;
        check("wait_for_origin_descriptor_close",read(release,&signal_value,sizeof(signal_value))==(ssize_t)sizeof(signal_value)&&signal_value==1);
        check("other_group_inherited_fd_keeps_original_charge",value(WORK,"hepta.page.stat","ipc")==2*RING&&value(RECOVER,"hepta.page.stat","ipc")==0);
        check("inherited_first_close",close(pair[0])==0);check("inherited_final_close",close(pair[1])==0);close(release);_exit(0);
    }
    check("origin_closes_descriptors",close(pair[0])==0&&close(pair[1])==0);
    check("origin_close_does_not_refund_inherited_frames",value(WORK,"hepta.page.stat","ipc")==2*RING);
    uint64_t signal_value=1;check("release_inherited_holder",write(release,&signal_value,sizeof(signal_value))==(ssize_t)sizeof(signal_value));
    child_status(child);check("inherited_final_reference_refunds_origin",await_ipc(WORK,0)==0);close(release);
}
static void fifo_negative(void) {
    join(WORK);warm();char path[128];snprintf(path,sizeof(path),"/tmp/ipc-budget-fifo-%d",getpid());
    check("create_named_fifo",mkfifo(path,0600)==0);
    unsigned long before=value(WORK,"hepta.page.current",NULL);ceiling(WORK,before+RING-PAGE);
    errno=0;int fd=open(path,O_RDWR|O_NONBLOCK|O_CLOEXEC);int error=errno;
    check("named_pipe_open_propagates_enomem",fd==-1&&error==ENOMEM);
    check("named_pipe_failure_has_no_backing",value(WORK,"hepta.page.stat","ipc")==0);
    unlimited(WORK);fd=open(path,O_RDWR|O_NONBLOCK|O_CLOEXEC);check("named_pipe_retry_succeeds",fd>=0);
    char byte='n',readback=0;check("named_pipe_retry_transfers_real_bytes",write(fd,&byte,1)==1&&read(fd,&readback,1)==1&&readback==byte);
    check("named_pipe_real_backing_charge",value(WORK,"hepta.page.stat","ipc")==RING);
    check("close_named_pipe",close(fd)==0);check("named_pipe_final_refund",await_ipc(WORK,0)==0);check("unlink_owned_fifo",unlink(path)==0);
}

static void publication_failure(void) {
    join(WORK);warm();int probe=open("/dev/null",O_RDWR|O_CLOEXEC);check("open_publication_fd_observer",probe>=0);
    int expected=fcntl(probe,F_DUPFD_CLOEXEC,0);check("capture_publication_fd_slot",expected>=0);close(expected);
    int *bad=mmap(NULL,PAGE,PROT_NONE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);check("create_unwritable_output_mapping",bad!=MAP_FAILED);
    errno=0;int result=socketpair(AF_UNIX,SOCK_STREAM,0,bad);
    check("socketpair_bad_output_returns_efault",result==-1&&errno==EFAULT);
    check("bad_output_releases_real_socket_buffers",value(WORK,"hepta.page.stat","ipc")==0);
    int next=fcntl(probe,F_DUPFD_CLOEXEC,0);check("bad_output_releases_reserved_fd_slots",next==expected);close(next);
    errno=0;result=pipe2(bad,O_CLOEXEC);
    check("pipe_bad_output_returns_efault",result==-1&&errno==EFAULT);
    check("bad_output_releases_real_pipe_buffer",value(WORK,"hepta.page.stat","ipc")==0);
    check("release_unwritable_output_mapping",munmap(bad,PAGE)==0);
    struct rlimit saved,limited;check("read_original_fd_limit",getrlimit(RLIMIT_NOFILE,&saved)==0);
    limited=saved;limited.rlim_cur=(rlim_t)expected+1;
    check("allow_exactly_one_new_fd_slot",setrlimit(RLIMIT_NOFILE,&limited)==0);
    int pair[2]={12345,23456};errno=0;result=socketpair(AF_UNIX,SOCK_STREAM,0,pair);
    check("second_fd_reservation_returns_emfile",result==-1&&errno==EMFILE);
    check("second_fd_failure_never_publishes_user_pair",pair[0]==12345&&pair[1]==23456);
    check("second_fd_failure_refunds_both_buffers",value(WORK,"hepta.page.stat","ipc")==0);
    check("restore_original_fd_limit",setrlimit(RLIMIT_NOFILE,&saved)==0);
    next=fcntl(probe,F_DUPFD_CLOEXEC,0);check("second_fd_failure_rolls_back_first_slot",next==expected);close(next);close(probe);
}

static void run_case(void(*fn)(void)) {
    pid_t child=fork();check("start_isolated_case",child>=0);
    if(child==0){fn();_exit(0);}child_status(child);
    check("case_released_ipc_frames",await_ipc(WORK,0)==0&&value(RECOVER,"hepta.page.stat","ipc")==0);
}
static void pipe_positive(void){pair_positive(0);}static void stream_positive(void){pair_positive(1);}static void seqpacket_positive(void){pair_positive(2);}
static void pipe_leaf(void){pair_negative(0,0);}static void pipe_ancestor(void){pair_negative(0,1);}
static void stream_leaf(void){pair_negative(1,0);}static void stream_ancestor(void){pair_negative(1,1);}
static void seq_leaf(void){pair_negative(2,0);}static void seq_ancestor(void){pair_negative(2,1);}

static void connect_admission(void) {
    int listener=socket(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
    check("create_original_listener",listener>=0);
    struct sockaddr_un address={.sun_family=AF_UNIX};
    snprintf(address.sun_path+1,sizeof(address.sun_path)-1,"ipc-budget-%d",getpid());
    socklen_t length=(socklen_t)(offsetof(struct sockaddr_un,sun_path)+1+strlen(address.sun_path+1));
    check("bind_owned_abstract_listener",bind(listener,(struct sockaddr*)&address,length)==0);
    check("listen_original_backlog",listen(listener,4)==0);
    int ready[2],go[2];check("create_root_owned_control_pipes",pipe2(ready,O_CLOEXEC)==0&&pipe2(go,O_CLOEXEC)==0);
    pid_t child=fork();check("start_connecting_process",child>=0);
    if(child==0) {
        close(listener);close(ready[0]);close(go[1]);join(WORK);warm();
        int client=socket(AF_UNIX,SOCK_STREAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);check("create_retryable_client",client>=0);
        unsigned long before=value(WORK,"hepta.page.current",NULL),events=value(WORK,"hepta.page.events","max");
        ceiling(WORK,before+RING);errno=0;
        int rc=connect(client,(struct sockaddr*)&address,length),error=errno;
        check("second_connect_ring_denial_returns_enomem",rc==-1&&error==ENOMEM);
        check("failed_connect_refunds_unpublished_buffers",value(WORK,"hepta.page.stat","ipc")==0&&value(WORK,"hepta.page.events","max")==events+1);
        byte_send(ready[1]);byte_recv(go[0]);unlimited(WORK);
        check("same_socket_retries_original_connect",connect(client,(struct sockaddr*)&address,length)==0);
        check("successful_connect_has_two_real_rings",value(WORK,"hepta.page.stat","ipc")==2*RING);
        byte_send(ready[1]);char request='q',reply=0;
        check("connected_client_sends_actual_payload",write(client,&request,1)==1);
        // The socket is nonblocking; wait for a real response without altering
        // the admission budget or interpreting EAGAIN as successful I/O.
        int n=-1;for(unsigned i=0;i<1000;++i) {
            n=(int)read(client,&reply,1);if(n==1||errno!=EAGAIN)break;
            struct timespec delay={0,1000000};nanosleep(&delay,NULL);
        }
        check("connected_client_receives_actual_payload",n==1&&reply=='a');byte_recv(go[0]);
        check("acceptor_close_keeps_client_backing_owned",value(WORK,"hepta.page.stat","ipc")==2*RING);
        check("close_original_client",close(client)==0);check("connect_last_reference_refund",await_ipc(WORK,0)==0);
        close(ready[1]);close(go[0]);_exit(0);
    }
    close(ready[1]);close(go[0]);byte_recv(ready[0]);errno=0;
    int accepted=accept4(listener,NULL,NULL,SOCK_CLOEXEC);
    check("failed_connect_does_not_publish_backlog_entry",accepted==-1&&errno==EAGAIN);
    byte_send(go[1]);byte_recv(ready[0]);accepted=accept4(listener,NULL,NULL,SOCK_CLOEXEC);
    check("retry_publishes_one_accepted_connection",accepted>=0);
    char request=0,reply='a';check("acceptor_reads_actual_client_bytes",read(accepted,&request,1)==1&&request=='q');
    check("acceptor_writes_actual_reply",write(accepted,&reply,1)==1);
    check("close_accepted_peer",close(accepted)==0);byte_send(go[1]);child_status(child);
    close(ready[0]);close(go[1]);check("close_original_listener",close(listener)==0);
    check("connect_case_final_ipc_refund",await_ipc(WORK,0)==0);
}

static void alarmed(int signal_number){(void)signal_number;_exit(124);}
int main(void) {
    signal(SIGALRM,alarmed);alarm(45);setvbuf(stdout,NULL,_IONBF,0);
    check("guest_root_setup",geteuid()==0);
    check("activate_parent_memory_controller",write_file("/sys/fs/cgroup/cgroup.subtree_control","+memory")==0);
    check("create_owned_parent_group",mkdir(ROOT,0755)==0);
    check("activate_child_memory_controller",write_file(ROOT "/cgroup.subtree_control","+memory")==0);
    check("create_workload_and_recovery_groups",mkdir(WORK,0755)==0&&mkdir(RECOVER,0755)==0);
    run_case(pipe_positive);run_case(stream_positive);run_case(seqpacket_positive);
    run_case(pipe_leaf);run_case(pipe_ancestor);run_case(stream_leaf);run_case(stream_ancestor);run_case(seq_leaf);run_case(seq_ancestor);
    run_case(inherited_reference);run_case(fifo_negative);run_case(publication_failure);connect_admission();
    printf("{\"passed\":true,\"parent_checks\":%u,\"scope\":\"actual_ipc_buffer_frames\",\"memory_max\":false}\n",checks);
    return 0;
}
