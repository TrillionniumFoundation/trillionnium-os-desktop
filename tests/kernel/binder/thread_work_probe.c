// SPDX-License-Identifier: MPL-2.0
// Process-wide ref/death work survives an actual preparing thread's exit.
// Execute only in the isolated guest.
#include "thread_fixture.h"

struct owner_work {
    struct endpoint endpoint;
    int ready[2],client_start[2],prepared[2],exit_go[2],second_go[2],client_go[2],done[2];
};
static void export_node(int fd,uint32_t code){
    struct flat_binder_object object={.hdr.type=BINDER_TYPE_BINDER,.binder=NODE_POINTER,.cookie=NODE_COOKIE};uint64_t offset=0;
    CHECK(send_payload(fd,BC_REPLY,0,code,0,&object,sizeof object,&offset,1)==0);
}
static uint32_t imported_node(struct endpoint e,struct message m){
    CHECK(m.kind==BR_REPLY&&m.tr.data_size==24);struct flat_binder_object object;memcpy(&object,(void *)(uintptr_t)m.tr.data.ptr.buffer,sizeof object);CHECK(object.hdr.type==BINDER_TYPE_HANDLE);handle_command(e.fd,BC_ACQUIRE,object.handle);free_buffer(e.fd,m.tr.data.ptr.buffer);return object.handle;
}
static void *owner_first(void *arg){
    struct owner_work *s=arg;command(s->endpoint.fd,BC_ENTER_LOOPER);token(s->ready[1]);struct message m=receive(s->endpoint.fd);CHECK(m.kind==BR_TRANSACTION&&m.tr.code==21);
    export_node(s->endpoint.fd,21);
    // Local-node ref work precedes this worker's own completion. It is prepared
    // once, then copyout fails before the owner sees the pointer/cookie pair.
    errno=0;CHECK(read_raw(s->endpoint.fd,(void *)1,128)==-1&&errno==EFAULT);token(s->prepared[1]);wait_token(s->exit_go[0]);return NULL;
}
static void *owner_second(void *arg){
    struct owner_work *s=arg;command(s->endpoint.fd,BC_ENTER_LOOPER);token(s->ready[1]);wait_token(s->second_go[0]);
    unsigned char bytes[128]={0};struct binder_write_read w={.read_size=sizeof bytes,.read_buffer=(uintptr_t)bytes};CHECK(ioctl(s->endpoint.fd,BINDER_WRITE_READ,&w)==0&&w.read_consumed==20);
    uint32_t kind=0;struct binder_ptr_cookie object;memcpy(&kind,bytes,4);memcpy(&object,bytes+4,sizeof object);CHECK(kind==BR_INCREFS&&object.ptr==NODE_POINTER&&object.cookie==NODE_COOKIE);
    uint32_t done=BC_INCREFS_DONE;memcpy(bytes,&done,4);CHECK(commands(s->endpoint.fd,bytes,20,NULL)==0);errno=0;CHECK(commands(s->endpoint.fd,bytes,20,NULL)==-1&&errno==EINVAL);
    // Remaining ACQUIRE work is handled by the ordinary exact acknowledgement
    // helper. The old worker's directed completion must not be delivered here.
    struct message m=receive(s->endpoint.fd);CHECK(m.kind==BR_TRANSACTION&&m.tr.code==22&&m.tr.target.ptr==NODE_POINTER&&m.tr.cookie==NODE_COOKIE);send_number(s->endpoint.fd,BC_REPLY,0,22);CHECK(receive(s->endpoint.fd).kind==BR_TRANSACTION_COMPLETE);free_buffer(s->endpoint.fd,m.tr.data.ptr.buffer);return NULL;
}
static void owner_client(struct owner_work *s){
    CHECK(close(s->endpoint.fd)==0);struct endpoint e=endpoint();send_number(e.fd,BC_TRANSACTION,0,21);CHECK(receive(e.fd).kind==BR_TRANSACTION_COMPLETE);uint32_t handle=imported_node(e,receive(e.fd));wait_token(s->client_go[0]);send_number(e.fd,BC_TRANSACTION,handle,22);CHECK(receive(e.fd).kind==BR_TRANSACTION_COMPLETE);struct message m=receive(e.fd);CHECK(m.kind==BR_REPLY&&m.tr.code==22);free_buffer(e.fd,m.tr.data.ptr.buffer);handle_command(e.fd,BC_RELEASE,handle);token(s->done[1]);close_endpoint(e);_exit(0);
}
static void node_work_handoff(void){
    struct owner_work s={.endpoint=endpoint()};CHECK(ioctl(s.endpoint.fd,BINDER_SET_CONTEXT_MGR,0)==0);int *pipes[]={s.ready,s.client_start,s.prepared,s.exit_go,s.second_go,s.client_go,s.done};for(unsigned i=0;i<7;i++)CHECK(pipe(pipes[i])==0);
    pid_t child=fork();CHECK(child>=0);if(child==0){wait_token(s.client_start[0]);owner_client(&s);}pthread_t first,second;CHECK(pthread_create(&first,NULL,owner_first,&s)==0);CHECK(pthread_create(&second,NULL,owner_second,&s)==0);wait_token(s.ready[0]);wait_token(s.ready[0]);token(s.client_start[1]);wait_token(s.prepared[0]);
    unsigned char bytes[128];errno=0;CHECK(read_raw(s.endpoint.fd,bytes,sizeof bytes)==-1&&errno==EBUSY);token(s.exit_go[1]);CHECK(pthread_join(first,NULL)==0);token(s.second_go[1]);token(s.client_go[1]);wait_token(s.done[0]);CHECK(pthread_join(second,NULL)==0);wait_child(child);close_endpoint(s.endpoint);for(unsigned i=0;i<7;i++)CHECK(close(pipes[i][0])==0&&close(pipes[i][1])==0);
    puts("binder_threads_EFAULT_prepared_node_work_real_thread_exit_exact_pointer_cookie_ack_handoff\tPASS");
}
struct death_work {struct endpoint endpoint;uint32_t handle;int ready[2],prepared[2],exit_go[2],second_go[2];};
static void *death_first(void *arg){struct death_work *s=arg;token(s->ready[1]);errno=0;CHECK(read_raw(s->endpoint.fd,(void *)1,128)==-1&&errno==EFAULT);token(s->prepared[1]);wait_token(s->exit_go[0]);return NULL;}
static void *death_second(void *arg){
    struct death_work *s=arg;wait_token(s->second_go[0]);struct message m=receive(s->endpoint.fd);CHECK(m.kind==BR_DEAD_BINDER&&m.cookie==0x22334455);death_done(s->endpoint.fd,m.cookie);death_command(s->endpoint.fd,BC_CLEAR_DEATH_NOTIFICATION,s->handle,m.cookie);struct message done=receive(s->endpoint.fd);CHECK(done.kind==BR_CLEAR_DEATH_NOTIFICATION_DONE&&done.cookie==m.cookie);handle_command(s->endpoint.fd,BC_RELEASE,s->handle);return NULL;
}
static void death_client(int inherited,int armed){
    CHECK(close(inherited)==0);struct death_work s={.endpoint=endpoint()};send_number(s.endpoint.fd,BC_TRANSACTION,0,31);CHECK(receive(s.endpoint.fd).kind==BR_TRANSACTION_COMPLETE);s.handle=imported_node(s.endpoint,receive(s.endpoint.fd));death_command(s.endpoint.fd,BC_REQUEST_DEATH_NOTIFICATION,s.handle,0x22334455);
    int *pipes[]={s.ready,s.prepared,s.exit_go,s.second_go};for(unsigned i=0;i<4;i++)CHECK(pipe(pipes[i])==0);pthread_t first,second;CHECK(pthread_create(&first,NULL,death_first,&s)==0);CHECK(pthread_create(&second,NULL,death_second,&s)==0);wait_token(s.ready[0]);token(armed);wait_token(s.prepared[0]);unsigned char bytes[128];errno=0;CHECK(read_raw(s.endpoint.fd,bytes,sizeof bytes)==-1&&errno==EBUSY);token(s.exit_go[1]);CHECK(pthread_join(first,NULL)==0);token(s.second_go[1]);CHECK(pthread_join(second,NULL)==0);close_endpoint(s.endpoint);_exit(0);
}
static void death_work_handoff(void){
    struct endpoint manager=endpoint();CHECK(ioctl(manager.fd,BINDER_SET_CONTEXT_MGR,0)==0);command(manager.fd,BC_ENTER_LOOPER);int armed[2];CHECK(pipe(armed)==0);pid_t child=fork();CHECK(child>=0);if(child==0)death_client(manager.fd,armed[1]);struct message m=receive(manager.fd);CHECK(m.kind==BR_TRANSACTION&&m.tr.code==31);export_node(manager.fd,31);CHECK(receive(manager.fd).kind==BR_TRANSACTION_COMPLETE);free_buffer(manager.fd,m.tr.data.ptr.buffer);wait_token(armed[0]);close_endpoint(manager);wait_child(child);CHECK(close(armed[0])==0&&close(armed[1])==0);
    puts("binder_threads_EFAULT_prepared_death_real_thread_exit_cookie_done_clear_handoff\tPASS");
}
int main(void){setbuf(stdout,NULL);alarm(25);node_work_handoff();death_work_handoff();printf("binder_thread_work_parent_checks=%u\n",checks);return 0;}
