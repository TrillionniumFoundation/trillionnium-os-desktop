// Independent local narrow control: exact frozen cleanup statement.
// No namespace, cgroup, pressure, Android, host connection or external PID.
#define main frozen_fixture_main
#include "/workspace/scratch/94990735b266/lmkd-work/host-pressure-freeze-05/owned-relay/fixture_init.cpp"
#undef main
int main() {
    Child victim; victim.label="foreground"; victim.uid=getuid();
    victim.pid=fork(); if(victim.pid<0)return 90;
    if(victim.pid==0){for(;;)pause();}
    victim.pidfd=syscall(SYS_pidfd_open,victim.pid,0);
    if(victim.pidfd<0){kill(victim.pid,SIGKILL);waitpid(victim.pid,nullptr,0);return 91;}
    if(syscall(SYS_pidfd_send_signal,victim.pidfd,SIGKILL,nullptr,0)<0)return 92;
    pollfd exitfd{victim.pidfd,POLLIN,0}; if(poll(&exitfd,1,1000)!=1)return 93;
    std::vector<Child> children{victim}; int st=0; bool accepted=false;
    try {
        for(auto& c:children) {if(alive_fd(c.pidfd)){child_command(c,'Q');await_exit(c.pid,c.pidfd,&st,2000);check(WIFEXITED(st)&&WEXITSTATUS(st)==0,"normal fixture cleanup");}close(c.command);close(c.reply);close(c.pidfd);}
        accepted=true;
    } catch(const std::exception&) {}
    // Parent still owns and reaps only its exact local child.
    if(waitpid(victim.pid,&st,0)!=victim.pid)return 94;
    bool killed=WIFSIGNALED(st)&&WTERMSIG(st)==SIGKILL;
    printf("{\"kind\":\"actual-frozen-cleanup-statement-local-owned-child-control\",\"unexpected_foreground_SIGKILL\":%s,\"cleanup_accepted\":%s,\"child_reaped\":true,\"Android_or_PSI_executed\":false}\n",killed?"true":"false",accepted?"true":"false");
    return accepted&&killed?0:1;
}
