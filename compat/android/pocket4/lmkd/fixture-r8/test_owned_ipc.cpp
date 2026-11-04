/* Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0 */
// Compile the actual helper. Tests call only owned fork/socket/pidfd routines;
// the namespace/cgroup/LMKD entry point is never entered.
#define main fixture_entry_not_called
#include "fixture_init.cpp"
#undef main

static int passed;
static void require_test(bool ok,const char* label) {
    if(!ok){std::fprintf(stderr,"FAIL %s\n",label);std::exit(2);}
    ++passed;std::printf("PASS %s\n",label);
}
static Child fork_pause() {
    Child c;c.label="owned-test";c.uid=getuid();pid_t parent=getpid();c.pid=fork();
    check(c.pid>=0,"owned fork");
    if(!c.pid){prctl(PR_SET_PDEATHSIG,SIGKILL);if(getppid()!=parent)_exit(92);for(;;)pause();}
    require_test(true,"owned fork");
    c.pidfd=syscall(SYS_pidfd_open,c.pid,0);c.start=start_ticks(c.pid);
    require_test(c.pidfd>=0,"owned pidfd pinned");return c;
}
static void reap_owned(Child& c,int signal) {
    signal_owned(c.pidfd,signal);pollfd f{c.pidfd,POLLIN,0};
    require_test(poll(&f,1,1000)==1,"owned signal exit bounded");
    auto first=observe_child_exit(c),second=observe_child_exit(c);
    require_test(first.result==0&&first.pid==c.pid&&first.code==CLD_KILLED&&first.status==signal,
                 "exact signal exit observed through pidfd");
    require_test(first.code==second.code&&first.status==second.status&&first.pid==second.pid,
                 "WNOWAIT leaves exit repeatably observable");
    int status;require_test(waitpid(c.pid,&status,0)==c.pid&&WIFSIGNALED(status)&&WTERMSIG(status)==signal,
                            "later owned waitpid still receives same signal");close(c.pidfd);
}
static void queue_test(bool pump) {
    int pair[2],ack[2];check(!socketpair(AF_UNIX,SOCK_DGRAM|SOCK_CLOEXEC,0,pair)&&!pipe2(ack,O_CLOEXEC),"test IPC");
    int limit=2048;check(!setsockopt(pair[1],SOL_SOCKET,SO_SNDBUF,&limit,sizeof(limit)),"small owned log queue");
    log_socket=pair[0];log_file=memfd_create("owned-fixture-logs",MFD_CLOEXEC);check(log_file>=0,"owned log memfd");
    log_bytes=0;log_text.clear();
    Child c;pid_t parent=getpid();c.pid=fork();check(c.pid>=0,"owned log sender");
    if(!c.pid){
        prctl(PR_SET_PDEATHSIG,SIGKILL);if(getppid()!=parent)_exit(92);
        close(pair[0]);close(ack[0]);close(log_file);char block[512];memset(block,'L',sizeof(block));
        for(int i=0;i<200;i++)if(send(pair[1],block,sizeof(block),MSG_NOSIGNAL)!=sizeof(block))_exit(91);
        unsigned count=200;write_all(ack[1],&count,sizeof(count));_exit(0);
    }
    close(pair[1]);close(ack[1]);c.pidfd=syscall(SYS_pidfd_open,c.pid,0);check(c.pidfd>=0,"sender pidfd");
    if(!pump) {
        pollfd f{ack[0],POLLIN,0};require_test(poll(&f,1,150)==0,"legacy ACK-only wait leaves log queue stalled");
        require_test(alive_fd(c.pidfd),"legacy negative control still owns live blocked sender");
        signal_owned(c.pidfd,SIGKILL);int status;check(waitpid(c.pid,&status,0)==c.pid,"negative control reap");
    } else {
        wait_reply_with_logs(ack[0],2000);unsigned count=0;
        require_test(read(ack[0],&count,sizeof(count))==sizeof(count)&&count==200,"ACK arrives while actual helper drains log queue");
        drain_log();require_test(log_bytes==200*512,"all owned log bytes persisted before ACK completion");
        struct stat st{};check(!fstat(log_file,&st),"log size");
        require_test(st.st_size==200*(512+sizeof(uint32_t)),"length-delimited log evidence complete");
        int status;check(waitpid(c.pid,&status,0)==c.pid,"sender reap");
        require_test(WIFEXITED(status)&&WEXITSTATUS(status)==0,"positive sender exits normally");
    }
    close(c.pidfd);close(ack[0]);close(log_socket);close(log_file);log_socket=log_file=-1;
}
int main() {
    setvbuf(stdout,nullptr,_IOLBF,0);
    queue_test(false);queue_test(true);
    int ack[2];check(!pipe2(ack,O_CLOEXEC),"silent pipe");bool timed_out=false;U began=now_ms();
    try{wait_reply_with_logs(ack[0],80);}catch(const std::runtime_error& e){timed_out=std::string(e.what()).find("fixture response timeout")!=std::string::npos;}
    require_test(timed_out&&now_ms()-began>=80&&now_ms()-began<500,"silent ACK retains finite original-style deadline");
    close(ack[0]);close(ack[1]);
    Child c=fork_pause();auto info=observe_child_exit(c);
    require_test(info.result==0&&info.pid==0&&alive_fd(c.pidfd),"live process does not invent exit info");
    signal_owned(c.pidfd,SIGSTOP);siginfo_t stop{};check(!waitid(P_PIDFD,c.pidfd,&stop,WSTOPPED|WNOWAIT),"owned stop");
    require_test(stop.si_code==CLD_STOPPED&&alive_fd(c.pidfd)&&start_ticks(c.pid)==c.start,"stopped state preserves live start identity");
    signal_owned(c.pidfd,SIGCONT);
    require_test(alive_fd(c.pidfd)&&start_ticks(c.pid)==c.start,"continued state preserves live start identity");
    reap_owned(c,SIGKILL);
    c=fork_pause();reap_owned(c,SIGTERM);
    c.pid=fork();check(c.pid>=0,"normal exit fork");if(!c.pid)_exit(7);
    c.pidfd=syscall(SYS_pidfd_open,c.pid,0);check(c.pidfd>=0,"normal pidfd");pollfd f{c.pidfd,POLLIN,0};check(poll(&f,1,1000)==1,"normal exit readiness");
    info=observe_child_exit(c);require_test(info.result==0&&info.pid==c.pid&&info.code==CLD_EXITED&&info.status==7,"normal exit code distinguished from signal");
    int status;check(waitpid(c.pid,&status,0)==c.pid,"normal reap");close(c.pidfd);c.pidfd=-1;
    info=observe_child_exit(c);require_test(info.result==-1&&(info.error==EINVAL||info.error==EBADF),"invalid pidfd does not fall back to numeric PID");
    std::printf("RESULT %d passed; owned IPC only, no cgroup or LMKD run\n",passed);
}
