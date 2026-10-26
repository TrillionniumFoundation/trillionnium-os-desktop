// SPDX-License-Identifier: MPL-2.0
// Actual Binder thread exit, FD/object lifetime and capacity in an isolated guest.
#include "thread_fixture.h"

struct lifecycle {
    struct endpoint endpoint;
    _Atomic int source_fd,hidden_fd;
    _Atomic binder_uintptr_t incoming_buffer;
    int start[2],client_start[2],prepared[2],exit_go[2],worker_one[2],pending[2],dead_seen[2],third_done[2],owner_closed[2];
    int explicit_exit,fault;
};
static void *first_worker(void *data){
    struct lifecycle *s=data;int fd=s->endpoint.fd;command(fd,BC_ENTER_LOOPER);token(s->start[1]);
    struct message boot=receive(fd);CHECK(boot.kind==BR_TRANSACTION&&boot.tr.code==10);
    s->source_fd=open("/tmp/binder-d1-live",O_CREAT|O_TRUNC|O_RDWR,0600);CHECK(s->source_fd>=0);CHECK(unlink("/tmp/binder-d1-live")==0);CHECK(write(s->source_fd,"ABC",3)==3&&lseek(s->source_fd,0,SEEK_SET)==0);
    struct {struct flat_binder_object node;struct binder_fd_object file;} payload={.node={.hdr.type=BINDER_TYPE_BINDER,.flags=FLAT_BINDER_FLAG_ACCEPTS_FDS,.binder=NODE_POINTER,.cookie=NODE_COOKIE},.file={.hdr.type=BINDER_TYPE_FD,.fd=(uint32_t)s->source_fd}};
    uint64_t offsets[2]={0,sizeof payload.node};CHECK(send_payload(fd,BC_REPLY,0,10,0,&payload,sizeof payload,offsets,2)==0);CHECK(receive(fd).kind==BR_TRANSACTION_COMPLETE);free_buffer(fd,boot.tr.data.ptr.buffer);
    if(s->fault){
        errno=0;CHECK(read_raw(fd,(void *)1,128)==-1&&errno==EFAULT);
        struct binder_fd_object hidden;memcpy(&hidden,s->endpoint.map,sizeof hidden);CHECK(hidden.hdr.type==BINDER_TYPE_FD);s->hidden_fd=(int)hidden.fd;
        CHECK(fcntl(s->hidden_fd,F_GETFD)==-1&&errno==EBADF);s->incoming_buffer=(uintptr_t)s->endpoint.map;
        errno=0;CHECK(read_raw(fd,(void *)1,128)==-1&&errno==EFAULT);struct binder_fd_object again;memcpy(&again,s->endpoint.map,sizeof again);CHECK(again.fd==hidden.fd&&fcntl((int)again.fd,F_GETFD)==-1&&errno==EBADF);
    }else{
        struct message m=receive(fd);CHECK(m.kind==BR_TRANSACTION&&m.tr.code==11&&m.tr.target.ptr==NODE_POINTER&&m.tr.cookie==NODE_COOKIE);s->incoming_buffer=m.tr.data.ptr.buffer;
    }
    token(s->prepared[1]);wait_token(s->exit_go[0]);
    if(s->fault==2){
        struct message received=receive(fd);CHECK(received.kind==BR_TRANSACTION&&received.tr.code==11);struct binder_fd_object installed;memcpy(&installed,(void *)(uintptr_t)received.tr.data.ptr.buffer,sizeof installed);CHECK((int)installed.fd==s->hidden_fd);CHECK((fcntl((int)installed.fd,F_GETFD)&FD_CLOEXEC)!=0);CHECK(write((int)installed.fd,"Q",1)==1);CHECK(close((int)installed.fd)==0);send_number(fd,BC_REPLY,0,11);CHECK(receive(fd).kind==BR_TRANSACTION_COMPLETE);free_buffer(fd,received.tr.data.ptr.buffer);
    }
    if(s->explicit_exit){CHECK(ioctl(fd,BINDER_THREAD_EXIT,0)==0);uint64_t number=11;errno=0;CHECK(send_payload(fd,BC_REPLY,0,11,0,&number,8,NULL,0)==-1&&errno==EINVAL);}
    // Return through real pthread exit, while the process/open/second worker live.
    return NULL;
}
static void *second_worker(void *data){
    struct lifecycle *s=data;int fd=s->endpoint.fd;command(fd,BC_ENTER_LOOPER);token(s->start[1]);wait_token(s->worker_one[0]);
    struct message m=receive(fd);CHECK(m.kind==BR_TRANSACTION&&m.tr.code==12&&m.tr.target.ptr==NODE_POINTER&&m.tr.cookie==NODE_COOKIE);
    char b=0;CHECK(read(s->source_fd,&b,1)==1&&b=='B');send_number(fd,BC_REPLY,0,12);CHECK(receive(fd).kind==BR_TRANSACTION_COMPLETE);free_buffer(fd,m.tr.data.ptr.buffer);command(fd,BC_EXIT_LOOPER);return NULL;
}
static void lifecycle_client(struct lifecycle *s){
    CHECK(close(s->endpoint.fd)==0);struct endpoint e=endpoint();send_number(e.fd,BC_TRANSACTION,0,10);CHECK(receive(e.fd).kind==BR_TRANSACTION_COMPLETE);
    struct message boot=receive(e.fd);CHECK(boot.kind==BR_REPLY&&boot.tr.data_size==48);
    struct flat_binder_object node;struct binder_fd_object file;memcpy(&node,(void *)(uintptr_t)boot.tr.data.ptr.buffer,sizeof node);memcpy(&file,(void *)(uintptr_t)(boot.tr.data.ptr.buffer+24),sizeof file);CHECK(node.hdr.type==BINDER_TYPE_HANDLE&&file.hdr.type==BINDER_TYPE_FD);
    uint32_t handle=node.handle;handle_command(e.fd,BC_ACQUIRE,handle);death_command(e.fd,BC_REQUEST_DEATH_NOTIFICATION,handle,0x12345678);free_buffer(e.fd,boot.tr.data.ptr.buffer);
    char b=0;CHECK(read((int)file.fd,&b,1)==1&&b=='A');int pipefd[2]={-1,-1};
    if(s->fault){CHECK(pipe(pipefd)==0);struct binder_fd_object transfer={.hdr.type=BINDER_TYPE_FD,.fd=(uint32_t)pipefd[1]};uint64_t offset=0;CHECK(send_payload(e.fd,BC_TRANSACTION,handle,11,0,&transfer,sizeof transfer,&offset,1)==0);CHECK(close(pipefd[1])==0);}else send_number(e.fd,BC_TRANSACTION,handle,11);
    CHECK(receive(e.fd).kind==BR_TRANSACTION_COMPLETE);token(s->pending[1]);int64_t before=now_ns();struct message terminal=receive(e.fd);CHECK(terminal.kind==(s->fault==2?BR_REPLY:BR_DEAD_REPLY));int64_t elapsed=now_ns()-before;CHECK(elapsed>=0&&elapsed<1000000000LL);token(s->dead_seen[1]);
    if(s->fault==2){CHECK(terminal.tr.code==11);free_buffer(e.fd,terminal.tr.data.ptr.buffer);CHECK(read(pipefd[0],&b,1)==1&&b=='Q');}
    if(s->fault){CHECK(read(pipefd[0],&b,1)==0);CHECK(close(pipefd[0])==0);}
    // Worker death is not owner death: the live original handle has no death event.
    no_work(e.fd);send_number(e.fd,BC_TRANSACTION,handle,12);CHECK(receive(e.fd).kind==BR_TRANSACTION_COMPLETE);struct message reply=receive(e.fd);CHECK(reply.kind==BR_REPLY&&reply.tr.code==12);free_buffer(e.fd,reply.tr.data.ptr.buffer);
    CHECK(read((int)file.fd,&b,1)==1&&b=='C');CHECK(close((int)file.fd)==0);token(s->third_done[1]);wait_token(s->owner_closed[0]);
    struct message death=receive(e.fd);CHECK(death.kind==BR_DEAD_BINDER&&death.cookie==0x12345678);death_done(e.fd,death.cookie);death_command(e.fd,BC_CLEAR_DEATH_NOTIFICATION,handle,death.cookie);CHECK(receive(e.fd).kind==BR_CLEAR_DEATH_NOTIFICATION_DONE);
    send_number(e.fd,BC_TRANSACTION,handle,13);CHECK(receive(e.fd).kind==BR_TRANSACTION_COMPLETE&&receive(e.fd).kind==BR_DEAD_REPLY);handle_command(e.fd,BC_RELEASE,handle);close_endpoint(e);_exit(0);
}
static void lifecycle_case(int explicit_exit,int fault){
    struct lifecycle s={.endpoint=endpoint(),.source_fd=-1,.hidden_fd=-1,.explicit_exit=explicit_exit,.fault=fault};CHECK(ioctl(s.endpoint.fd,BINDER_SET_CONTEXT_MGR,0)==0);
    int *pipes[]={s.start,s.client_start,s.prepared,s.exit_go,s.worker_one,s.pending,s.dead_seen,s.third_done,s.owner_closed};for(unsigned i=0;i<9;i++)CHECK(pipe(pipes[i])==0);
    pid_t child=fork();CHECK(child>=0);if(child==0){wait_token(s.client_start[0]);lifecycle_client(&s);}
    pthread_t first,second;CHECK(pthread_create(&first,NULL,first_worker,&s)==0);CHECK(pthread_create(&second,NULL,second_worker,&s)==0);
    // Consume both worker admissions, then release the independent process.
    wait_token(s.start[0]);wait_token(s.start[0]);token(s.client_start[1]);wait_token(s.prepared[0]);wait_token(s.pending[0]);
    if(fault){unsigned char bytes[128];errno=0;CHECK(read_raw(s.endpoint.fd,bytes,sizeof bytes)==-1&&errno==EBUSY);uint32_t enter=BC_ENTER_LOOPER;uint64_t used=99;errno=0;CHECK(commands(s.endpoint.fd,&enter,4,&used)==-1&&errno==EBUSY&&used==0);}
    token(s.exit_go[1]);CHECK(pthread_join(first,NULL)==0);
    // No new Binder operation occurs before the old caller observes its dead reply.
    wait_token(s.dead_seen[0]);
    if(fault){
        int64_t before=now_ns();for(;;){errno=0;int next=fcntl(s.endpoint.fd,F_DUPFD_CLOEXEC,s.hidden_fd);CHECK(next>=0);int64_t elapsed=now_ns()-before;CHECK(elapsed>=0&&elapsed<1000000000LL);CHECK(close(next)==0);if(next==s.hidden_fd)break;usleep(1000);}
        const unsigned char *page=s.endpoint.map;for(unsigned i=0;i<24;i++)CHECK(page[i]==0);unsigned char bytes[12];uint32_t c=BC_FREE_BUFFER;binder_uintptr_t address=s.incoming_buffer;memcpy(bytes,&c,4);memcpy(bytes+4,&address,8);errno=0;CHECK(commands(s.endpoint.fd,bytes,sizeof bytes,NULL)==-1&&errno==EINVAL);
    }else free_buffer(s.endpoint.fd,s.incoming_buffer);
    token(s.worker_one[1]);wait_token(s.third_done[0]);CHECK(pthread_join(second,NULL)==0);CHECK(close(s.source_fd)==0);close_endpoint(s.endpoint);token(s.owner_closed[1]);wait_child(child);
    for(unsigned i=0;i<9;i++){CHECK(close(pipes[i][0])==0);CHECK(close(pipes[i][1])==0);}
    printf("binder_threads_exit explicit=%d prepared_EFAULT=%d original_node_and_FD_survive_other_worker caller_dead_refund_and_real_owner_death\tPASS\n",explicit_exit,fault);
}

struct quota {int fd,ready;int release[2];int admitted;};
static void *quota_worker(void *data){
    struct quota *q=data;uint32_t enter=BC_ENTER_LOOPER;uint64_t used=99;errno=0;int rc=commands(q->fd,&enter,4,&used);int error=errno;
    if(q->admitted)CHECK(rc==0&&used==4);else CHECK(rc==-1&&error==ENOSPC&&used==0);
    token(q->ready);if(q->admitted)wait_token(q->release[0]);return NULL;
}
static void participant_quota(void){
    struct endpoint e=endpoint();int ready[2];CHECK(pipe(ready)==0);struct quota q[10];pthread_t t[10];
    for(unsigned i=0;i<8;i++){q[i]=(struct quota){.fd=e.fd,.ready=ready[1],.admitted=1};CHECK(pipe(q[i].release)==0);CHECK(pthread_create(&t[i],NULL,quota_worker,&q[i])==0);}
    for(unsigned i=0;i<8;i++){wait_token(ready[0]);}
    q[8]=(struct quota){.fd=e.fd,.ready=ready[1],.admitted=0};CHECK(pthread_create(&t[8],NULL,quota_worker,&q[8])==0);wait_token(ready[0]);CHECK(pthread_join(t[8],NULL)==0);
    token(q[0].release[1]);CHECK(pthread_join(t[0],NULL)==0);q[9]=(struct quota){.fd=e.fd,.ready=ready[1],.admitted=1};CHECK(pipe(q[9].release)==0);CHECK(pthread_create(&t[9],NULL,quota_worker,&q[9])==0);wait_token(ready[0]);
    for(unsigned i=1;i<8;i++){token(q[i].release[1]);CHECK(pthread_join(t[i],NULL)==0);}token(q[9].release[1]);CHECK(pthread_join(t[9],NULL)==0);
    for(unsigned i=0;i<10;i++){if(i!=8){CHECK(close(q[i].release[0])==0);CHECK(close(q[i].release[1])==0);}}
    CHECK(close(ready[0])==0&&close(ready[1])==0);close_endpoint(e);
    puts("binder_threads_eight_actual_participants_ninth_zero_consumption_reject_exit_refund\tPASS");
}
struct budget {struct endpoint endpoint;int sent,go;unsigned code;};
static void *budget_caller(void *data){
    struct budget *b=data;send_number(b->endpoint.fd,BC_TRANSACTION,0,b->code);token(b->sent);wait_token(b->go);CHECK(receive(b->endpoint.fd).kind==BR_TRANSACTION_COMPLETE);CHECK(receive(b->endpoint.fd).kind==BR_DEAD_REPLY);return NULL;
}
static void budget_client(int inherited,int all_sent,int release,int all_dead,int new_ready){
    CHECK(close(inherited)==0);struct endpoint e=endpoint();int sent[2],go[2];CHECK(pipe(sent)==0&&pipe(go)==0);struct budget a[8];pthread_t t[8];
    for(unsigned i=0;i<8;i++){a[i]=(struct budget){.endpoint=e,.sent=sent[1],.go=go[0],.code=400+i};CHECK(pthread_create(&t[i],NULL,budget_caller,&a[i])==0);}for(unsigned i=0;i<8;i++)wait_token(sent[0]);token(all_sent);wait_token(release);for(unsigned i=0;i<8;i++)token(go[1]);for(unsigned i=0;i<8;i++)CHECK(pthread_join(t[i],NULL)==0);
    token(all_dead);wait_token(new_ready);send_number(e.fd,BC_TRANSACTION,0,499);CHECK(receive(e.fd).kind==BR_TRANSACTION_COMPLETE);struct message m=receive(e.fd);CHECK(m.kind==BR_REPLY&&m.tr.code==1499);free_buffer(e.fd,m.tr.data.ptr.buffer);close_endpoint(e);_exit(0);
}
static void terminal_budget(void){
    struct endpoint manager=endpoint();CHECK(ioctl(manager.fd,BINDER_SET_CONTEXT_MGR,0)==0);command(manager.fd,BC_ENTER_LOOPER);int sent[2],release[2],dead[2],new_ready[2];CHECK(pipe(sent)==0&&pipe(release)==0&&pipe(dead)==0&&pipe(new_ready)==0);
    pid_t child=fork();CHECK(child>=0);if(child==0)budget_client(manager.fd,sent[1],release[0],dead[1],new_ready[0]);wait_token(sent[0]);close_endpoint(manager);token(release[1]);wait_token(dead[0]);
    manager=endpoint();CHECK(ioctl(manager.fd,BINDER_SET_CONTEXT_MGR,0)==0);command(manager.fd,BC_ENTER_LOOPER);token(new_ready[1]);struct message m=receive(manager.fd);CHECK(m.kind==BR_TRANSACTION&&m.tr.code==499);send_number(manager.fd,BC_REPLY,0,1499);CHECK(receive(manager.fd).kind==BR_TRANSACTION_COMPLETE);free_buffer(manager.fd,m.tr.data.ptr.buffer);wait_child(child);close_endpoint(manager);
    int *pipes[]={sent,release,dead,new_ready};for(unsigned i=0;i<4;i++)CHECK(close(pipes[i][0])==0&&close(pipes[i][1])==0);
    puts("binder_threads_eight_outgoing_calls_sixteen_real_complete_dead_events_and_refund\tPASS");
}
int main(void){setbuf(stdout,NULL);alarm(35);lifecycle_case(0,0);lifecycle_case(1,0);lifecycle_case(0,1);lifecycle_case(1,1);lifecycle_case(0,2);lifecycle_case(1,2);participant_quota();terminal_budget();printf("binder_thread_lifetime_parent_checks=%u\n",checks);return 0;}
