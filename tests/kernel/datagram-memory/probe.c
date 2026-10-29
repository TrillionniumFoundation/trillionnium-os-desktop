// SPDX-License-Identifier: MPL-2.0
// Guest only: ordinary POSIX datagrams and their actual physical page owners.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#define ROOT "/sys/fs/cgroup/datagram-memory"
#define WORK ROOT "/work"
#define RECOVER ROOT "/recover"
#define PAGE 4096UL
#define MAX_PACKET 65536UL
static unsigned checks;
static unsigned char input[MAX_PACKET + 1], output[MAX_PACKET + PAGE];

static void check(const char *name, int passed) {
    printf("{\"case\":\"%s\",\"passed\":%s}\n", name, passed ? "true" : "false");
    if (!passed) { fprintf(stderr,"DATAGRAM FAIL %s errno=%d\n",name,errno); exit(1); }
    ++checks;
}
static int write_file(const char *path, const char *text) {
    int fd=open(path,O_WRONLY|O_CLOEXEC); if(fd<0) return -1;
    size_t size=strlen(text); ssize_t count=write(fd,text,size); int error=errno;
    close(fd); errno=error; return count==(ssize_t)size ? 0 : -1;
}
static unsigned long value(const char *group,const char *attr,const char *key) {
    char path[256],data[512]={0}; snprintf(path,sizeof(path),"%s/%s",group,attr);
    int fd=open(path,O_RDONLY|O_CLOEXEC); if(fd<0) return ~0UL;
    ssize_t count=read(fd,data,sizeof(data)-1); close(fd); if(count<=0) return ~0UL;
    if(!key) return strtoul(data,NULL,10);
    for(char *line=data;*line;) {
        if(!strncmp(line,key,strlen(key))&&line[strlen(key)]==' ') return strtoul(line+strlen(key)+1,NULL,10);
        char *next=strchr(line,'\n'); if(!next) break; line=next+1;
    }
    return ~0UL;
}
static void join(const char *group) {
    char path[256],pid[32]; snprintf(path,sizeof(path),"%s/cgroup.procs",group);
    snprintf(pid,sizeof(pid),"%d",getpid()); check("join_actual_group",write_file(path,pid)==0);
}
static void unlimited(const char *group) {
    char path[256]; snprintf(path,sizeof(path),"%s/hepta.page.max",group);
    check("restore_real_page_ceiling",write_file(path,"max")==0);
}
static void ceiling(const char *group,unsigned long limit) {
    char path[256],text[64]; snprintf(path,sizeof(path),"%s/hepta.page.max",group);
    snprintf(text,sizeof(text),"%lu",limit); check("set_real_page_ceiling",write_file(path,text)==0);
}
static unsigned long await_ipc(const char *group,unsigned long expected) {
    unsigned long actual=value(group,"hepta.page.stat","ipc"); unsigned attempts=0;
    while(actual!=expected&&attempts++<1000) {
        struct timespec delay={0,1000000}; nanosleep(&delay,NULL); actual=value(group,"hepta.page.stat","ipc");
    }
    printf("{\"ipc_observed\":%lu,\"ipc_expected\":%lu,\"observations\":%u}\n",actual,expected,attempts);
    return actual;
}
static void warm(void) {
    volatile unsigned char stack[64*1024]; for(size_t at=0;at<sizeof(stack);at+=PAGE) stack[at]=1;
    memset(input,0x53,sizeof(input)); memset(output,0xa7,sizeof(output));
    for(unsigned group=0;group<3;group++) {
        const char *path=group==0?WORK:group==1?ROOT:RECOVER;
        unlimited(path); check("physical_ipc_stat_available",value(path,"hepta.page.stat","ipc")!=~0UL);
        (void)value(path,"hepta.page.current",NULL); (void)value(path,"hepta.page.events","max");
    }
    fputs("datagram_measurement_paths_warmed\n",stderr);
}
static void pair(int fds[2]) {
    check("create_ordinary_datagram_pair",socketpair(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0,fds)==0);
}
static void close_pair(int fds[2]) {
    check("close_both_datagram_endpoints",close(fds[0])==0&&close(fds[1])==0);
}
static void empty_queue(int fd) {
    errno=0; ssize_t count=recv(fd,output,sizeof(output),MSG_DONTWAIT);
    check("no_unpublished_packet_or_prefix",count==-1&&errno==EAGAIN);
}
static void positive(void) {
    join(WORK); warm(); int fds[2]; pair(fds);
    check("empty_socket_has_no_payload_frames",value(WORK,"hepta.page.stat","ipc")==0);
    check("send_real_multi_page_packet",send(fds[0],input,PAGE+17,0)==(ssize_t)(PAGE+17));
    check("sender_and_ancestor_own_page_rounded_packet",value(WORK,"hepta.page.stat","ipc")==2*PAGE&&value(ROOT,"hepta.page.stat","ipc")==2*PAGE);
    ssize_t count=recv(fds[1],output,sizeof(output),MSG_PEEK);
    check("peek_returns_only_packet_bytes",count==(ssize_t)(PAGE+17)&&!memcmp(input,output,PAGE+17));
    check("page_tail_is_not_exposed",output[PAGE+17]==0xa7&&output[sizeof(output)-1]==0xa7);
    check("peek_retains_original_physical_charge",value(WORK,"hepta.page.stat","ipc")==2*PAGE);
    join(RECOVER);
    check("receiver_migration_does_not_transfer_payload_owner",value(WORK,"hepta.page.stat","ipc")==2*PAGE&&value(ROOT,"hepta.page.stat","ipc")==2*PAGE&&value(RECOVER,"hepta.page.stat","ipc")==0);
    count=recv(fds[1],output,sizeof(output),MSG_PEEK);
    check("migrated_receiver_peek_keeps_original_owner_and_bytes",count==(ssize_t)(PAGE+17)&&!memcmp(input,output,PAGE+17)&&value(WORK,"hepta.page.stat","ipc")==2*PAGE&&value(RECOVER,"hepta.page.stat","ipc")==0);
    count=recv(fds[1],output,13,MSG_TRUNC);
    check("truncation_returns_original_packet_length",count==(ssize_t)(PAGE+17)&&!memcmp(input,output,13));
    check("migrated_receiver_consumption_refunds_original_owner",await_ipc(WORK,0)==0&&value(RECOVER,"hepta.page.stat","ipc")==0);
    close_pair(fds);
}
static void negative(int ancestor) {
    join(WORK); warm(); int fds[2]; pair(fds);
    const char *limited=ancestor?ROOT:WORK;
    unsigned long before=value(limited,"hepta.page.current",NULL);
    unsigned long leaf_events=value(WORK,"hepta.page.events","max"),root_events=value(ROOT,"hepta.page.events","max");
    ceiling(limited,before+PAGE); errno=0;
    ssize_t count=send(fds[0],input,PAGE+1,0); int error=errno;
    check("two_page_payload_at_one_page_capacity_returns_enomem",count==-1&&error==ENOMEM);
    empty_queue(fds[1]);
    check("ancestor_failure_rolls_back_leaf_physical_charge",value(WORK,"hepta.page.stat","ipc")==0&&value(ROOT,"hepta.page.stat","ipc")==0);
    check("only_rejecting_account_records_first_denial",value(WORK,"hepta.page.events","max")==leaf_events+(ancestor?0:1)&&value(ROOT,"hepta.page.events","max")==root_events+(ancestor?1:0));
    check("empty_packet_uses_remaining_real_page",send(fds[0],input,0,0)==0);
    check("empty_packet_has_real_original_owner",value(WORK,"hepta.page.stat","ipc")==PAGE&&value(ROOT,"hepta.page.stat","ipc")==PAGE);
    errno=0; count=send(fds[0],input,0,0); error=errno;
    check("another_empty_packet_cannot_bypass_page_ceiling",count==-1&&error==ENOMEM);
    check("empty_packet_peek_does_not_consume_backing",recv(fds[1],output,sizeof(output),MSG_PEEK)==0&&value(WORK,"hepta.page.stat","ipc")==PAGE);
    check("consume_exactly_one_empty_packet",recv(fds[1],output,sizeof(output),0)==0);
    check("empty_packet_final_reference_refunds",await_ipc(WORK,0)==0);
    empty_queue(fds[1]);
    unlimited(limited);
    check("same_pair_retries_after_capacity_restored",send(fds[0],input,PAGE+1,0)==(ssize_t)(PAGE+1));
    check("retry_delivers_whole_original_packet",recv(fds[1],output,sizeof(output),0)==(ssize_t)(PAGE+1)&&!memcmp(input,output,PAGE+1));
    check("retry_refunds_all_payload_frames",await_ipc(WORK,0)==0); close_pair(fds);
}
static void leaf_negative(void) { negative(0); }
static void ancestor_negative(void) { negative(1); }
static void copy_fault(void) {
    join(WORK); warm(); int fds[2]; pair(fds);
    unsigned char *mapping=mmap(NULL,2*PAGE,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    check("allocate_real_user_copy_fixture",mapping!=MAP_FAILED); memset(mapping,0x61,2*PAGE);
    check("protect_second_copy_page",mprotect(mapping+PAGE,PAGE,PROT_NONE)==0);
    errno=0; ssize_t count=send(fds[0],mapping+PAGE-3,7,0); int error=errno;
    check("source_fault_returns_efault",count==-1&&error==EFAULT); empty_queue(fds[1]);
    check("source_fault_refunds_unpublished_physical_payload",value(WORK,"hepta.page.stat","ipc")==0);
    check("send_packet_before_receive_fault",send(fds[0],input,17,0)==17);
    errno=0; count=recv(fds[1],mapping+PAGE-3,17,0); error=errno;
    check("destination_fault_returns_efault",count==-1&&error==EFAULT);
    check("destination_fault_retains_whole_original_payload",value(WORK,"hepta.page.stat","ipc")==PAGE);
    check("receive_retry_delivers_whole_packet",recv(fds[1],output,sizeof(output),0)==17&&!memcmp(input,output,17));
    check("receive_retry_final_refund",await_ipc(WORK,0)==0);
    check("unmap_owned_copy_fixture",munmap(mapping,2*PAGE)==0); close_pair(fds);
}
static void byte_ceiling(void) {
    join(WORK); warm(); int fds[2]; pair(fds);
    errno=0; ssize_t count=send(fds[0],input,MAX_PACKET+1,0); int error=errno;
    check("original_oversize_packet_is_rejected",count==-1&&error==EMSGSIZE);
    check("oversize_has_no_payload_charge",value(WORK,"hepta.page.stat","ipc")==0); empty_queue(fds[1]);
    check("original_64k_packet_limit_is_preserved",send(fds[0],input,MAX_PACKET,0)==MAX_PACKET);
    check("full_packet_has_exact_actual_page_charge",value(WORK,"hepta.page.stat","ipc")==MAX_PACKET);
    errno=0; count=send(fds[0],input,1,0); error=errno;
    check("original_receive_byte_capacity_is_preserved",count==-1&&error==EAGAIN);
    check("full_packet_delivers_real_bytes",recv(fds[1],output,sizeof(output),0)==MAX_PACKET&&!memcmp(input,output,MAX_PACKET));
    check("full_packet_final_refund",await_ipc(WORK,0)==0); close_pair(fds);
}
static void child_status(pid_t child) {
    int status=0; check("wait_actual_child",waitpid(child,&status,0)==child);
    check("child_completed_all_checks",WIFEXITED(status)&&WEXITSTATUS(status)==0);
}
static void inherited_receiver(void) {
    join(RECOVER); warm(); int fds[2]; pair(fds);
    pid_t child=fork(); check("fork_actual_sender",child>=0);
    if(child==0) {
        join(WORK); check("sender_queues_before_exit",send(fds[0],input,17,0)==17);
        check("exiting_sender_owns_queued_payload",value(WORK,"hepta.page.stat","ipc")==PAGE);
        close_pair(fds); _exit(0);
    }
    child_status(child);
    check("sender_exit_does_not_refund_queued_payload",value(WORK,"hepta.page.stat","ipc")==PAGE);
    check("other_group_inherited_receiver_uses_original_payload",recv(fds[1],output,sizeof(output),0)==17&&!memcmp(input,output,17));
    check("inherited_final_consumption_refunds_sender",await_ipc(WORK,0)==0); close_pair(fds);
}
static void receiver_close(void) {
    join(WORK); warm(); int fds[2]; pair(fds);
    check("queue_two_real_payloads_before_receiver_close",send(fds[0],input,17,0)==17&&send(fds[0],input,0,0)==0);
    check("two_queued_packets_own_two_pages",value(WORK,"hepta.page.stat","ipc")==2*PAGE);
    check("close_receiver_with_queued_messages",close(fds[1])==0);
    check("closed_receiver_releases_all_payload_frames",await_ipc(WORK,0)==0);
    errno=0; ssize_t count=send(fds[0],input,1,0); int error=errno;
    check("retained_sender_cannot_publish_to_closed_queue",count==-1&&error==ECONNREFUSED);
    check("close_final_sender_reference",close(fds[0])==0);
}
static void run_case(void(*fn)(void)) {
    pid_t child=fork(); check("start_isolated_datagram_case",child>=0);
    if(child==0) { fn(); _exit(0); }
    child_status(child);
    check("case_final_physical_refunds",await_ipc(WORK,0)==0&&await_ipc(RECOVER,0)==0);
}
static void alarmed(int signal_number) { (void)signal_number; _exit(124); }
int main(void) {
    signal(SIGALRM,alarmed); alarm(45); setvbuf(stdout,NULL,_IONBF,0);
    check("guest_root_setup",geteuid()==0);
    check("activate_parent_memory_controller",write_file("/sys/fs/cgroup/cgroup.subtree_control","+memory")==0);
    check("create_owned_parent_group",mkdir(ROOT,0755)==0);
    check("activate_child_memory_controller",write_file(ROOT "/cgroup.subtree_control","+memory")==0);
    check("create_workload_and_recovery_groups",mkdir(WORK,0755)==0&&mkdir(RECOVER,0755)==0);
    run_case(positive); run_case(leaf_negative); run_case(ancestor_negative);
    run_case(copy_fault); run_case(byte_ceiling); run_case(inherited_receiver); run_case(receiver_close);
    printf("{\"passed\":true,\"parent_checks\":%u,\"scope\":\"actual_unix_datagram_payload_pages\",\"memory_max\":false}\n",checks);
    return 0;
}
