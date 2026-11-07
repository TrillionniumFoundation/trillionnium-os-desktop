// Owned relay/pressure canary, derived from the freeze04 PID namespace actor.
// It exports held descriptors to its exact host-namespace parent; the actual
// production droidloom-psi-owner executable handles enrollment and retirement.
// Never installed into Main. Budgets are fixed before lifecycle authority.
// This actor can register only its own forked children in its private LMKD socket.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/capability.h>
#include <linux/magic.h>
#include <poll.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <sstream>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <sys/mount.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
#include "include/lmkd.h"

using U = unsigned long long;
constexpr U MiB = 1024 * 1024;
constexpr U HARD = 512 * MiB, SOFT = 384 * MiB, FIRST_KILL_CAP = 432 * MiB;
const std::array<const char*, 6> NS = {"pid", "mnt", "cgroup", "ipc", "uts", "net"};
volatile sig_atomic_t stopped = 0;
int log_socket = -1, log_file = -1;
size_t log_bytes = 0;
std::string log_text;
U pressure_peak = 0;

[[noreturn]] void fail(const std::string& s) { throw std::runtime_error(s + ": " + strerror(errno)); }
void check(bool b, const std::string& s) { if (!b) fail(s); }
void on_stop(int) { stopped = 1; }
U now_ms() { timespec t{}; check(!clock_gettime(CLOCK_MONOTONIC, &t), "clock"); return U(t.tv_sec)*1000+t.tv_nsec/1000000; }
U now_ns() { timespec t{}; check(!clock_gettime(CLOCK_MONOTONIC, &t)&&t.tv_sec>=0&&t.tv_nsec>=0&&t.tv_nsec<1000000000,"monotonic clock");return U(t.tv_sec)*1000000000+U(t.tv_nsec); }
std::string read_text(const std::string& p, size_t bound=32768) {
    int fd=open(p.c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW); check(fd>=0,"open "+p);
    std::string s(bound+1,'\0'); ssize_t n=read(fd,s.data(),s.size()); int e=errno; close(fd); errno=e;
    check(n>=0 && size_t(n)<=bound,"read bounded "+p); s.resize(n); return s;
}
void write_all(int fd,const void* p,size_t n) {
    auto b=static_cast<const char*>(p);
    while(n) { ssize_t k=write(fd,b,n); if(k<0&&errno==EINTR)continue; check(k>0,"write"); b+=k;n-=k; }
}
void write_file(const std::string& p,const std::string& s,bool create=false,int extra=0) {
    int fd=open(p.c_str(),O_WRONLY|O_CLOEXEC|O_NOFOLLOW|extra|(create?(O_CREAT|O_EXCL):0),0600);
    check(fd>=0,"write open "+p); write_all(fd,s.data(),s.size());close(fd);
}
U number(const std::string& s) { size_t n=0; U v=std::stoull(s,&n); check(s.find_first_not_of(" \n\t",n)==std::string::npos,"decimal");return v; }
std::string link_text(const std::string& p) { char b[1024];ssize_t n=readlink(p.c_str(),b,sizeof(b));check(n>0&&n<ssize_t(sizeof(b)),"readlink");return {b,size_t(n)}; }
U inode(const std::string& p) { struct stat s{};check(!stat(p.c_str(),&s),"stat "+p);return s.st_ino; }
std::string self_cgroup() {
    std::string x=read_text("/proc/self/cgroup");check(x.rfind("0::",0)==0&&x.find('\n')==x.size()-1,"unified cgroup");
    x=x.substr(3,x.size()-4);check(!x.empty()&&x[0]=='/'&&x.find("..") == std::string::npos,"cgroup path");return x;
}
// The cgroup namespace root remains the systemd-owned delegation boundary.
// Its memory.pressure is not writable under nsdelegate. Keep the supervisor
// outside the measured workload and configure an owned child domain instead.
struct stat configure_memory_domain(const std::string& unit_path,bool pressure_phase) {
    check(self_cgroup()=="/","new namespace is rooted at owned unit");
    const std::string supervisor=unit_path+"/supervisor", domain=unit_path+"/domain";
    check(!mkdir(supervisor.c_str(),0755)&&!mkdir(domain.c_str(),0755),"fresh owned cgroup children");
    write_file(supervisor+"/cgroup.procs",std::to_string(getpid()));
    check(self_cgroup()=="/supervisor"&&read_text(unit_path+"/cgroup.procs").empty(),"empty delegation root");
    write_file(unit_path+"/cgroup.subtree_control","+memory +pids +cpu");
    write_file(domain+"/memory.max",std::to_string(HARD));
    const std::string high=pressure_phase?std::to_string(SOFT):"max";
    write_file(domain+"/memory.high",high);
    write_file(domain+"/memory.swap.max","0");
    write_file(domain+"/pids.max","64");
    write_file(domain+"/cpu.max","100000 100000");
    check(number(read_text(domain+"/memory.max"))==HARD&&read_text(domain+"/memory.high")==high+"\n"
          &&number(read_text(domain+"/memory.swap.max"))==0&&number(read_text(domain+"/pids.max"))==64
          &&read_text(domain+"/cpu.max")=="100000 100000\n","fixed child-domain limits");
    struct stat ds{};check(!lstat(domain.c_str(),&ds)&&S_ISDIR(ds.st_mode)&&ds.st_uid==0,
                          "owned memory domain identity");
    return ds;
}
U start_ticks(pid_t p) {
    std::string s=read_text("/proc/"+std::to_string(p)+"/stat",4096);auto pos=s.rfind(") ");check(pos!=std::string::npos,"proc stat");
    std::istringstream in(s.substr(pos+2));std::string f;for(int i=3;i<=22;i++)check(bool(in>>f),"proc stat fields");return number(f);
}
void close_from(unsigned int first) { check(syscall(SYS_close_range,first,~0U,0)==0,"close_range"); }
void keep_two(int a,int b) {
    int x=fcntl(a,F_DUPFD_CLOEXEC,100),y=fcntl(b,F_DUPFD_CLOEXEC,101);check(x>=100&&y>x,"duplicate owned pipes");
    check(syscall(SYS_close_range,3,99,0)==0,"close inherited fds");
    check(dup2(x,3)==3&&dup2(y,4)==4,"map owned pipes");close(x);close(y);close_from(5);
}
std::string quote(const std::string& x) {
    std::string s="\"";for(unsigned char c:x){if(c=='"'||c=='\\'){s+='\\';s+=char(c);}else if(c=='\n')s+="\\n";else if(c>=32&&c<127)s+=char(c);else{s+='?';}}return s+'"';
}
void drain_log() {
    if(log_socket<0)return;
    for(;;) { char b[4096];ssize_t n=recv(log_socket,b,sizeof(b),MSG_DONTWAIT);if(n<0&&errno==EAGAIN)break;
        check(n>0,"private log receive");check(log_bytes+size_t(n)<=128*1024,"private log bound");
        uint32_t sz=n;write_all(log_file,&sz,sizeof(sz));write_all(log_file,b,n);log_bytes+=n;
        log_text.append(b,n);
    }
}
void pause_ms(unsigned n) { U end=now_ms()+n;do {check(!stopped,"termination requested");drain_log();usleep(10000);}while(now_ms()<end); }
int make_socket(const char* path,int kind) {
    int fd=socket(AF_UNIX,kind|SOCK_CLOEXEC,0);check(fd>=0,"private socket");sockaddr_un a{};a.sun_family=AF_UNIX;
    check(strlen(path)<sizeof(a.sun_path),"socket path");strcpy(a.sun_path,path);
    check(!bind(fd,reinterpret_cast<sockaddr*>(&a),sizeof(a)),"bind private socket");return fd;
}
bool alive_fd(int fd) { pollfd p{fd,POLLIN,0};int r=poll(&p,1,0);check(r>=0,"pidfd poll");return r==0; }
void signal_owned(int fd,int signal) { if(alive_fd(fd))check(!syscall(SYS_pidfd_send_signal,fd,signal,nullptr,0),"owned pidfd signal"); }
void await_exit(pid_t p,int fd,int* status,unsigned ms) {
    U end=now_ms()+ms;while(alive_fd(fd)&&now_ms()<end)pause_ms(10);check(!alive_fd(fd),"owned child exit deadline");
    check(waitpid(p,status,0)==p,"owned waitpid");
}
void set_score(pid_t p,int score) {write_file("/proc/"+std::to_string(p)+"/oom_score_adj",std::to_string(score));}
int score(pid_t p) {return std::stoi(read_text("/proc/"+std::to_string(p)+"/oom_score_adj",32));}
void lower_lmkd_identity() {
    check(!prctl(PR_SET_KEEPCAPS,1),"keep caps");gid_t groups[]={1069,1000,3009};
    check(!setgroups(3,groups)&&!setgid(1069)&&!setuid(1069),"LMKD uid/gid");
    __user_cap_header_struct h{_LINUX_CAPABILITY_VERSION_3,0};__user_cap_data_struct d[2]{};
    for(int cap:{CAP_DAC_OVERRIDE,CAP_KILL,CAP_IPC_LOCK,CAP_SYS_NICE,CAP_SYS_RESOURCE}) {
        d[cap/32].effective|=1U<<(cap%32);d[cap/32].permitted|=1U<<(cap%32);d[cap/32].inheritable|=1U<<(cap%32);
    }
    check(!syscall(SYS_capset,&h,d),"LMKD caps");
    for(int cap:{CAP_DAC_OVERRIDE,CAP_KILL,CAP_IPC_LOCK,CAP_SYS_NICE,CAP_SYS_RESOURCE})check(!prctl(PR_CAP_AMBIENT,PR_CAP_AMBIENT_RAISE,cap,0,0),"ambient cap");
    check(!prctl(PR_SET_KEEPCAPS,0),"clear keepcaps");
}
struct Child {pid_t pid=0;int pidfd=-1,command=-1,reply=-1;uid_t uid=0;U start=0,allocated=0;std::string label;};
Child launch_lmkd(bool valid) {
    const char* path=valid?"/dev/socket/lmkd":"/dev/socket/lmkd-negative";
    int s=make_socket(path,SOCK_SEQPACKET),yes=1;check(!setsockopt(s,SOL_SOCKET,SO_PASSCRED,&yes,sizeof(yes)),"passcred");
    check(!chmod(path,0660)&&!chown(path,1000,1000),"socket ownership");
    Child c;c.label=valid?"lmkd":"negative-lmkd";c.uid=1069;c.pid=fork();check(c.pid>=0,"fork LMKD");
    if(c.pid==0) {
        try { if(s!=3)check(dup2(s,3)==3,"LMKD socket fd");check(fcntl(3,F_SETFD,0)==0,"LMKD inherited socket");close_from(4);
            set_score(getpid(),-1000);lower_lmkd_identity();clearenv();
            setenv("PATH","/system/bin",1);setenv("LD_LIBRARY_PATH","/system/lib64",1);setenv("ANDROID_SOCKET_lmkd","3",1);
            setenv("DROIDLOOM_CELL","1",1);if(valid) {
                setenv("DROIDLOOM_LMKD_CGROUP","/sys/fs/cgroup",1);
                setenv("DROIDLOOM_LMKD_PRESSURE","relay-required",1);
            }
            execl("/system/bin/lmkd","lmkd",static_cast<char*>(nullptr));fail("exec Android LMKD");
        } catch(const std::exception&e){dprintf(2,"LMKD child setup: %s\n",e.what());_exit(126);}
    }
    close(s);c.pidfd=syscall(SYS_pidfd_open,c.pid,0);check(c.pidfd>=0,"LMKD pidfd");c.start=start_ticks(c.pid);return c;
}
int connect_lmkd(Child& c) {
    U end=now_ms()+5000;while(now_ms()<end) {
        check(alive_fd(c.pidfd),"LMKD exited during connect");int s=socket(AF_UNIX,SOCK_SEQPACKET|SOCK_CLOEXEC,0);check(s>=0,"client socket");
        sockaddr_un a{};a.sun_family=AF_UNIX;strcpy(a.sun_path,"/dev/socket/lmkd");
        if(!connect(s,reinterpret_cast<sockaddr*>(&a),sizeof(a))) { return s; }
        close(s);pause_ms(20);
    }fail("LMKD connect timeout");
}
void send_packet(int s,LMKD_CTRL_PACKET p,size_t n) {check(send(s,p,n,MSG_NOSIGNAL)==ssize_t(n),"LMKD packet send");}
int killcount(int s) {
    LMKD_CTRL_PACKET p{};lmk_getkillcnt k{1001,1001};send_packet(s,p,lmkd_pack_set_getkillcnt(p,&k));
    pollfd f{s,POLLIN,0};check(poll(&f,1,1500)==1,"LMKD response timeout");ssize_t n=recv(s,p,sizeof(p),0);
    check(n==8&&lmkd_pack_get_cmd(p)==LMK_GETKILLCNT,"LMKD real response");return int(ntohl(p[1]));
}
struct ThreadFixture {int reply;std::atomic<bool>stop{false};};
void* thread_fixture(void* ptr) {
    auto t=static_cast<ThreadFixture*>(ptr);U tid=syscall(SYS_gettid);write_all(t->reply,&tid,sizeof(tid));
    while(!t->stop.load()) { usleep(10000); }
    return nullptr;
}
void owned_child(int command,int reply,uid_t uid) {
    keep_two(command,reply);set_score(getpid(),0);check(!setgroups(0,nullptr)&&!setgid(uid)&&!setuid(uid),"fixture identity");
    std::vector<std::pair<void*,size_t>>regions;U total=0;pthread_t thread{};bool threaded=false;ThreadFixture th{4};
    write_all(4,&total,sizeof(total));
    for(;;) {
        struct {char kind;U value;} request{};ssize_t n=read(3,&request,sizeof(request));if(n<0&&errno==EINTR)continue;
        check(n==sizeof(request),"fixture command");if(request.kind=='Q')break;
        if(request.kind=='T') {check(!threaded&&!pthread_create(&thread,nullptr,thread_fixture,&th),"fixture thread");threaded=true;continue;}
        if(request.kind=='F') {
            check(request.value==0,"owned release command has no allocation parameter");
            for(auto region:regions)check(!munmap(region.first,region.second),"release owned region");
            regions.clear();total=0;write_all(4,&total,sizeof(total));continue;
        }
        check(request.kind=='A'&&request.value<=216*MiB&&total+request.value<=216*MiB,"bounded allocation request");
        void* p=mmap(nullptr,request.value,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);check(p!=MAP_FAILED,"fixture mmap");
        auto b=static_cast<volatile char*>(p);for(U i=0;i<request.value;i+=4096)b[i]=1;regions.push_back({p,request.value});total+=request.value;write_all(4,&total,sizeof(total));
    }
    if(threaded){th.stop=true;check(!pthread_join(thread,nullptr),"fixture join");}for(auto r:regions)munmap(r.first,r.second);_exit(0);
}
Child new_child(const std::string& label,uid_t uid) {
    int cmd[2],ack[2];check(!pipe2(cmd,O_CLOEXEC)&&!pipe2(ack,O_CLOEXEC),"fixture pipes");Child c;c.uid=uid;c.label=label;
    c.pid=fork();check(c.pid>=0,"fork fixture");if(!c.pid){try{owned_child(cmd[0],ack[1],uid);}catch(const std::exception&e){dprintf(2,"fixture: %s\n",e.what());_exit(125);}}
    close(cmd[0]);close(ack[1]);c.command=cmd[1];c.reply=ack[0];c.pidfd=syscall(SYS_pidfd_open,c.pid,0);check(c.pidfd>=0,"fixture pidfd");c.start=start_ticks(c.pid);
    pollfd f{c.reply,POLLIN,0};check(poll(&f,1,1500)==1,"owned fixture startup");U ready=1;check(read(c.reply,&ready,sizeof(ready))==sizeof(ready)&&ready==0,"owned fixture startup acknowledgement");return c;
}
struct ExitObservation {int result,error;pid_t pid;int code,status;};
ExitObservation observe_child_exit(const Child& c) {
    siginfo_t info{};errno=0;
    int result=waitid(P_PIDFD,c.pidfd,&info,WEXITED|WNOHANG|WNOWAIT);
    return {result,result<0?errno:0,info.si_pid,info.si_code,info.si_status};
}
void verify_child(const Child& c) {
    check(c.pid>1,"owned child PID "+c.label);
    if(!alive_fd(c.pidfd)) {
        const auto info=observe_child_exit(c);
        std::ostringstream out;out<<"{\"label\":"<<quote(c.label)<<",\"pid\":"<<c.pid
          <<",\"start\":"<<c.start<<",\"pidfd_ready\":true,\"waitid_rc\":"<<info.result
          <<",\"waitid_errno\":"<<info.error<<",\"si_pid\":"<<info.pid
          <<",\"si_code\":"<<info.code<<",\"si_status\":"<<info.status<<"}";
        write_file("/evidence/exited-"+c.label+".json",out.str(),true);
        drain_log();
        throw std::runtime_error("owned child exited: "+out.str());
    }
    check(start_ticks(c.pid)==c.start,"owned start-time identity "+c.label);
    check(read_text("/proc/"+std::to_string(c.pid)+"/cgroup")=="0::/domain\n","fixture cgroup membership");
    const std::string expected="Uid:\t"+std::to_string(c.uid)+"\t"+std::to_string(c.uid)+"\t"+std::to_string(c.uid)+"\t"+std::to_string(c.uid)+"\n";
    check(read_text("/proc/"+std::to_string(c.pid)+"/status").find(expected)!=std::string::npos,"fixture UID identity");
}
void wait_reply_with_logs(int reply,unsigned timeout_ms) {
    const U end=now_ms()+timeout_ms;
    for(;;) {
        check(!stopped,"termination requested while waiting for fixture reply");
        drain_log();
        U now=now_ms();check(now<end,"fixture response timeout");
        pollfd f[]={{reply,POLLIN,0},{log_socket,POLLIN,0}};
        int result=poll(f,log_socket>=0?2:1,int(std::min<U>(50,end-now)));
        if(result<0&&errno==EINTR)continue;
        check(result>=0,"fixture reply/log poll");
        if(f[0].revents) {
            check((f[0].revents&POLLIN)!=0&&!(f[0].revents&(POLLERR|POLLNVAL)),"fixture reply pipe closed or invalid");
            drain_log();
            return;
        }
    }
}
U child_command(Child& c,char kind,U value=0) {
    verify_child(c);struct {char kind;U value;} request{kind,value};write_all(c.command,&request,sizeof(request));if(kind=='Q')return 0;
    wait_reply_with_logs(c.reply,8000);U r;check(read(c.reply,&r,sizeof(r))==sizeof(r),"fixture reply");if(kind=='A'||kind=='F')c.allocated=r;return r;
}
void register_child(int s,const Child& c,int adj,int ptype=PROC_TYPE_APP,bool lmkd_only=false) {
    verify_child(c);LMKD_CTRL_PACKET p{};lmk_procprio r{c.pid,c.uid,adj,static_cast<proc_type>(ptype),lmkd_only};send_packet(s,p,lmkd_pack_set_procprio(p,&r));
    check(killcount(s)==0,"unexpected protocol-phase kill");
}
std::string counters(const std::string& path) {return read_text(path);}
U counter(const std::string& raw,const std::string& key) {std::istringstream in(raw);std::string k;U v;while(in>>k>>v)if(k==key)return v;fail("missing counter "+key);}
U psi_total(const std::string& raw,const std::string& type) {std::istringstream in(raw);std::string l;while(std::getline(in,l))if(l.rfind(type+" ",0)==0){auto p=l.find("total=");check(p!=std::string::npos,"PSI total");return number(l.substr(p+6));}fail("missing PSI type");}
void sample(const std::string& label) {
    std::string p="/evidence/"+label+".json";
    std::ostringstream o;o<<"{\"monotonic_ms\":"<<now_ms()<<",\"current\":"<<number(read_text("/sys/fs/cgroup/memory.current"))
      <<",\"max\":"<<quote(read_text("/sys/fs/cgroup/memory.max"))<<",\"high\":"<<quote(read_text("/sys/fs/cgroup/memory.high"))
      <<",\"events\":"<<quote(counters("/sys/fs/cgroup/memory.events"))<<",\"stat\":"<<quote(counters("/sys/fs/cgroup/memory.stat"))
      <<",\"pressure\":"<<quote(counters("/sys/fs/cgroup/memory.pressure"))<<"}";write_file(p,o.str(),true);
}
void no_oom(const std::string& before) {
    std::string after=counters("/sys/fs/cgroup/memory.events");for(const char* k:{"max","oom","oom_kill","oom_group_kill"})check(counter(after,k)==counter(before,k),std::string("kernel event ")+k);
    check(number(read_text("/sys/fs/cgroup/memory.current"))<472*MiB,"fixture hard reserve");
}
void record_runtime(const Child& daemon,const std::string& stage) {
    check(stage=="startup"||stage=="post-registration","runtime record stage");
    const std::string output=stage=="startup"?"/evidence/lmkd-":"/evidence/lmkd-post-registration-";
    std::string p="/proc/"+std::to_string(daemon.pid);
    verify_child(daemon);
    write_file(output+"status.txt",read_text(p+"/status"),true);
    write_file(output+"maps.txt",read_text(p+"/maps",256*1024),true);
    DIR* dir=opendir((p+"/fd").c_str());check(dir!=nullptr,"LMKD FD inventory");
    std::ostringstream out;int sockets=0;struct stat pressure{};
    check(!stat("/sys/fs/cgroup/memory.pressure",&pressure),"own pressure inode");
    struct stat domain{};check(!stat("/sys/fs/cgroup",&domain),"own memory domain inode");
    write_file(output+"pressure-file.json","{\"pressure_device\":"+std::to_string(U(pressure.st_dev))+
        ",\"pressure_inode\":"+std::to_string(U(pressure.st_ino))+",\"cgroup_device\":"+std::to_string(U(domain.st_dev))+
        ",\"cgroup_inode\":"+std::to_string(U(domain.st_ino))+"}",true);
    for(dirent* de;(de=readdir(dir));) {
        if(de->d_name[0]=='.')continue;
        const std::string fdpath=p+"/fd/"+de->d_name;
        const std::string link=link_text(fdpath);out<<de->d_name<<" "<<link<<"\n";
        check(link.find("cgroup.kill")==std::string::npos&&link.find("cgroup.procs")==std::string::npos,
              "this phase must not claim the production group-kill route");
        check(link.find("memory.pressure")==std::string::npos,"Android must hold no host PSI FD");
        if(link.rfind("socket:[",0)==0)sockets++;
    }
    closedir(dir);check(sockets>=5,"real framework/relay notification sockets present");
    write_file(output+"fds.txt",out.str(),true);
}
void pressure_budget_unchanged() {
    check(number(read_text("/sys/fs/cgroup/memory.max"))==HARD&&
          number(read_text("/sys/fs/cgroup/memory.high"))==SOFT&&
          number(read_text("/sys/fs/cgroup/memory.swap.max"))==0,"immutable initial pressure budget");
}
U pressure_current(const std::string& events0) {
    pressure_budget_unchanged();no_oom(events0);
    U current=number(read_text("/sys/fs/cgroup/memory.current"));
    pressure_peak=std::max(pressure_peak,current);
    check(current<=FIRST_KILL_CAP,"first-kill current cap exceeded");return current;
}
void allocate_pressure_step(Child& allocator,const Child& cached,const Child& daemon,
                            const std::string& events0,U deadline_ms,U* cached_exit_ns) {
    constexpr U chunk=4*MiB,reserve=16*MiB;
    check(allocator.allocated+chunk<=216*MiB,"owned allocator hard cap");
    check(pressure_current(events0)+chunk+reserve<=FIRST_KILL_CAP,"per-step charge reserve");
    verify_child(allocator);verify_child(daemon);
    if(*cached_exit_ns)return;
    if(!alive_fd(cached.pidfd)){*cached_exit_ns=now_ns();return;}
    struct {char kind;U value;} request{'A',chunk};write_all(allocator.command,&request,sizeof(request));
    for(;;) {
        check(!stopped&&now_ms()<deadline_ms,"bounded pressure allocation deadline");
        drain_log();pressure_current(events0);verify_child(daemon);
        pollfd f[]={{allocator.reply,POLLIN,0},{*cached_exit_ns?-1:cached.pidfd,POLLIN,0}};
        int ready=poll(f,2,25);if(ready<0&&errno==EINTR)continue;check(ready>=0,"owned pressure reply/victim poll");
        if(!*cached_exit_ns&&f[1].revents) {
            check(!(f[1].revents&(POLLERR|POLLNVAL)),"owned cached pidfd health");
            if(!alive_fd(cached.pidfd))*cached_exit_ns=now_ns();
        }
        if(f[0].revents) {
            check((f[0].revents&POLLIN)&&!(f[0].revents&(POLLERR|POLLNVAL)),"owned allocator reply failed");
            U total=0;check(read(allocator.reply,&total,sizeof(total))==sizeof(total)&&
                total==allocator.allocated+chunk,"exact bounded allocator acknowledgement");
            allocator.allocated=total;return;
        }
    }
}
bool run_pressure_workload(const std::string& phase,Child& daemon,int control,std::vector<Child>& children) {
    const bool stale=phase=="stale";check(phase=="pressure"||stale,"fixed pressure qualification phase");
    pressure_budget_unchanged();
    const std::string events0=counters("/sys/fs/cgroup/memory.events");
    Child& cached=children[0];Child& allocator=children[4];
    int notification=connect_lmkd(daemon);LMKD_CTRL_PACKET packet{};
    send_packet(notification,packet,lmkd_pack_set_subscribe(packet,LMK_ASYNC_EVENT_KILL));
    child_command(cached,'A',63*MiB);child_command(children[1],'A',127*MiB);
    child_command(children[2],'A',15*MiB);child_command(children[3],'A',3*MiB);
    U cached_exit_ns=0;
    const U preload_deadline=now_ms()+8000;
    while(pressure_current(events0)<SOFT-32*MiB) {
        allocate_pressure_step(allocator,cached,daemon,events0,preload_deadline,&cached_exit_ns);
        check(!cached_exit_ns,"no victim during below-high preload");
    }
    check(pressure_current(events0)<SOFT,"quiet plateau stays below high");
    sample("quiet-before");const std::string quiet=counters("/sys/fs/cgroup/memory.pressure");
    const U quiet_started_ns=now_ns();
    pause_ms(2200);pressure_current(events0);check(killcount(control)==0,"live lease and occupancy alone cannot kill");
    const std::string quiet_after=counters("/sys/fs/cgroup/memory.pressure");
    check(psi_total(quiet,"some")==psi_total(quiet_after,"some")&&psi_total(quiet,"full")==psi_total(quiet_after,"full"),
          "quiet private PSI control inconclusive");
    check(counter(counters("/sys/fs/cgroup/memory.events"),"high")==counter(events0,"high"),"below-high plateau unexpectedly throttled");
    for(const auto& child:children)verify_child(child);
    const U quiet_completed_ns=now_ns();
    sample("quiet-after");
    U stopped_ns=0,resume_ns=0,quiet_end_ns=0;
    if(stale) {
        signal_owned(daemon.pidfd,SIGSTOP);const U stop_deadline=now_ms()+1000;
        while(read_text("/proc/"+std::to_string(daemon.pid)+"/status").find("State:\tT")==std::string::npos) {
            check(now_ms()<stop_deadline,"exact LMKD stop acknowledgement");pause_ms(10);
        }
        verify_child(daemon);stopped_ns=now_ns();
    }
    const U pressure_start_ns=now_ns(),pressure_deadline=now_ms()+8000;
    sample("pressure-before");
    while(!cached_exit_ns&&pressure_current(events0)<416*MiB&&now_ms()<pressure_deadline) {
        if(pressure_current(events0)+20*MiB>FIRST_KILL_CAP||allocator.allocated+4*MiB>216*MiB)break;
        allocate_pressure_step(allocator,cached,daemon,events0,pressure_deadline,&cached_exit_ns);
        if(stale)check(!cached_exit_ns,"stopped LMKD cannot kill cached target");
        for(size_t i=1;i<children.size();i++)verify_child(children[i]);
    }
    const U allocation_finished_ns=now_ns();
    if(stale) {
        check(!cached_exit_ns&&pressure_current(events0)>SOFT,"stale control needs a retained above-high allocation");
        const std::string before_age=counters("/sys/fs/cgroup/memory.pressure");
        pause_ms(2200);pressure_current(events0);
        const std::string after_age=counters("/sys/fs/cgroup/memory.pressure");
        check(psi_total(before_age,"some")==psi_total(after_age,"some")&&psi_total(before_age,"full")==psi_total(after_age,"full"),
              "stale interval has new pressure stalls");
        resume_ns=now_ns();signal_owned(daemon.pidfd,SIGCONT);
        check(killcount(control)==0,"aged queue did not cause a kill on resume");
        pause_ms(1200);quiet_end_ns=now_ns();pressure_current(events0);
        check(killcount(control)==0,"aged queue and quiet live lease do not kill");
        for(const auto& child:children)verify_child(child);
        verify_child(daemon);sample("stale-after");
    } else {
        const U exit_deadline=now_ms()+6000;
        while(!cached_exit_ns&&now_ms()<exit_deadline) {
            pressure_current(events0);verify_child(daemon);
            if(!alive_fd(cached.pidfd)){cached_exit_ns=now_ns();break;}
            for(size_t i=1;i<children.size();i++)verify_child(children[i]);
            pause_ms(25);
        }
        check(cached_exit_ns!=0,"no cached victim within original PSI bounds; trial incomplete");
        const auto exit=observe_child_exit(cached);
        check(exit.result==0&&exit.pid==cached.pid&&exit.code==CLD_KILLED&&exit.status==SIGKILL,"exact cached pidfd SIGKILL");
        write_file("/evidence/cached-exit.json","{\"pid\":"+std::to_string(exit.pid)+",\"start\":"+std::to_string(cached.start)+
            ",\"si_code\":"+std::to_string(exit.code)+",\"si_status\":"+std::to_string(exit.status)+
            ",\"observed_monotonic_ns\":"+std::to_string(cached_exit_ns)+"}",true);
        int status=0;check(waitpid(cached.pid,&status,0)==cached.pid&&WIFSIGNALED(status)&&WTERMSIG(status)==SIGKILL,"reap exact cached victim");
        const U release_deadline=now_ms()+500;
        while(pressure_current(events0)>=SOFT&&now_ms()<release_deadline)pause_ms(10);
        check(pressure_current(events0)<SOFT,"one cached victim must restore below-high headroom");
        check(killcount(control)==1,"exactly one cached victim");
        pollfd f{notification,POLLIN,0};check(poll(&f,1,1000)==1&&(f.revents&POLLIN),"actual native kill notification");
        ssize_t n=recv(notification,packet,sizeof(packet),MSG_DONTWAIT);
        check(n==16&&lmkd_pack_get_cmd(packet)==LMK_PROCKILL&&pid_t(ntohl(packet[1]))==cached.pid&&
              uid_t(ntohl(packet[2]))==cached.uid,"exact native kill-notification identity");
        write_file("/evidence/cached-kill-notification.json","{\"pid\":"+std::to_string(cached.pid)+
            ",\"uid\":"+std::to_string(cached.uid)+",\"bytes\":16,\"command\":"+std::to_string(LMK_PROCKILL)+
            ",\"rss_kib\":"+std::to_string(ntohl(packet[3]))+
            ",\"observed_monotonic_ns\":"+std::to_string(now_ns())+"}",true);
        drain_log();
        const auto kill_at=log_text.rfind("Kill '");
        check(kill_at!=std::string::npos,"actual native cached kill diagnostic");
        const auto kill_end=log_text.find('\0',kill_at);
        check(kill_end!=std::string::npos&&kill_end-kill_at<2048,"bounded owned native kill diagnostic");
        const std::string kill_line=log_text.substr(kill_at,kill_end-kill_at);
        check(kill_line.find("("+std::to_string(cached.pid)+"), uid "+std::to_string(cached.uid)+
            ", oom_score_adj 900 to free ")!=std::string::npos&&kill_line.find("; reason: ")!=std::string::npos,
            "actual native kill diagnostic identity/priority/reason");
        write_file("/evidence/cached-kill-diagnostic.json","{\"pid\":"+std::to_string(cached.pid)+
            ",\"uid\":"+std::to_string(cached.uid)+",\"oom_score_adj\":900,\"line\":"+quote(kill_line)+"}",true);
        for(size_t i=1;i<children.size();i++)verify_child(children[i]);
        verify_child(daemon);pause_ms(1200);quiet_end_ns=now_ns();pressure_current(events0);
        check(killcount(control)==1,"no second victim after pressure relief");
        for(size_t i=1;i<children.size();i++)verify_child(children[i]);
        sample("pressure-after");
    }
    check(score(daemon.pid)==-1000&&score(children[1].pid)==0&&score(children[2].pid)==-1000,"foreground/protected/LMKD scores retained");
    const std::string pressure_after=counters("/sys/fs/cgroup/memory.pressure");
    check(psi_total(pressure_after,"some")>psi_total(quiet_after,"some")&&
          counter(counters("/sys/fs/cgroup/memory.events"),"high")>counter(events0,"high"),"real scoped pressure counters required");
    close(notification);
    const U final_current=pressure_current(events0);
    std::ostringstream receipt;receipt<<"{\"phase\":"<<quote(phase)<<",\"workload_complete\":true,\"host_audit_required\":true,\"real_pressure_verified\":false"
        <<",\"max\":"<<HARD<<",\"high\":"<<SOFT<<",\"first_kill_current_cap\":"<<FIRST_KILL_CAP
        <<",\"peak_observed_current\":"<<pressure_peak<<",\"final_current\":"<<final_current
        <<",\"cached_bytes\":"<<cached.allocated<<",\"foreground_bytes\":"<<children[1].allocated
        <<",\"allocator_bytes\":"<<allocator.allocated<<",\"pressure_start_ns\":"<<pressure_start_ns
        <<",\"quiet_started_ns\":"<<quiet_started_ns<<",\"quiet_completed_ns\":"<<quiet_completed_ns
        <<",\"allocation_finished_ns\":"<<allocation_finished_ns<<",\"stopped_ns\":"<<stopped_ns
        <<",\"resume_ns\":"<<resume_ns<<",\"cached_exit_observed_ns\":"<<cached_exit_ns<<",\"quiet_end_ns\":"<<quiet_end_ns
        <<",\"some_before\":"<<psi_total(quiet_after,"some")<<",\"some_after\":"<<psi_total(pressure_after,"some")
        <<",\"full_before\":"<<psi_total(quiet_after,"full")<<",\"full_after\":"<<psi_total(pressure_after,"full")
        <<",\"events_before\":"<<quote(events0)<<",\"events_after\":"<<quote(counters("/sys/fs/cgroup/memory.events"))
        <<",\"kill_count\":"<<(stale?0:1)<<",\"protected_targets_alive\":true,\"budget_unchanged\":true}";
    write_file("/evidence/pressure-workload.json",receipt.str(),true);
    if(stale) {
        // The above-high stale observation is already complete. Release only
        // this owned allocator's pages before retirement I/O; keep every
        // target alive and keep all budget/threshold values unchanged.
        const U released=allocator.allocated;
        check(child_command(allocator,'F')==0,"release only owned pressure allocation");
        const U released_at=now_ns(),relieved=pressure_current(events0);
        check(relieved<SOFT,"owned allocator release restores below-high cleanup headroom");
        for(const auto& child:children)verify_child(child);
        check(killcount(control)==0,"no victim during owned post-observation relief");
        write_file("/evidence/pressure-relief.json","{\"released_bytes\":"+std::to_string(released)+
            ",\"monotonic_ns\":"+std::to_string(released_at)+",\"current\":"+std::to_string(relieved)+
            ",\"all_targets_alive\":true,\"kill_count\":0,\"budget_changed\":false}",true);
    }
    return !stale;
}
void run_phase(const std::string& phase) {
    check(phase=="protocol"||phase=="pressure"||phase=="stale","fixed native relay phase");
    log_socket=make_socket("/dev/socket/logdw",SOCK_DGRAM);check(!chmod("/dev/socket/logdw",0666),"private log mode");
    log_file=open("/evidence/logdw.records",O_CREAT|O_EXCL|O_WRONLY|O_CLOEXEC,0600);check(log_file>=0,"log output");
    Child negative=launch_lmkd(false);int st=0;await_exit(negative.pid,negative.pidfd,&st,5000);close(negative.pidfd);drain_log();
    check(WIFEXITED(st)&&WEXITSTATUS(st)==1,"marked container must fail nonzero");
    check(log_text.find("Marked Droidloom cell requires an explicit cgroup memory domain")!=std::string::npos,"marked-contract diagnostic");
    Child lmkd=launch_lmkd(true);int s=connect_lmkd(lmkd);check(killcount(s)==0,"startup round trip");drain_log();verify_child(lmkd);check(score(lmkd.pid)==-1000,"LMKD protected score");
    check(log_text.find("Using cell cgroup memory budget: max=536870912")!=std::string::npos,"actual cgroup budget diagnostic");
    record_runtime(lmkd,"startup");
    std::vector<Child> children;children.reserve(5);
    for(auto entry:std::vector<std::pair<const char*,uid_t>>{{"cached",10001},{"foreground",10002},{"protected",10003},{"sentinel",10004},{"allocator",10005}}) {
        children.push_back(new_child(entry.first,entry.second));child_command(children.back(),'A',MiB);
    }
    LMKD_CTRL_PACKET pack{};lmk_procs_prio batch{};int scores[]={900,0,-1000};
    for(int i=0;i<3;i++){verify_child(children[i]);batch.procs[i]={children[i].pid,children[i].uid,scores[i],PROC_TYPE_APP,false};}
    send_packet(s,pack,lmkd_pack_set_procs_prio(pack,&batch,3));check(killcount(s)==0,"batch protocol barrier");
    for(int i=0;i<3;i++)check(score(children[i].pid)==scores[i],"actual oom_score_adj update");
    register_child(s,children[0],1001);check(score(children[0].pid)==900,"reject upper score");
    register_child(s,children[0],-1001);check(score(children[0].pid)==900,"reject lower score");
    register_child(s,children[0],800,PROC_TYPE_COUNT);check(score(children[0].pid)==900,"reject process type");
    register_child(s,children[0],800,PROC_TYPE_APP,true);check(score(children[0].pid)==900,"lmkd-only kernel score preserved");
    register_child(s,children[0],900);
    U tid=child_command(children[1],'T');check(tid!=U(children[1].pid),"owned nonleader thread");
    check(read_text("/proc/"+std::to_string(children[1].pid)+"/task/"+std::to_string(tid)+"/status").find("Tgid:\t"+std::to_string(children[1].pid)+"\n")!=std::string::npos,"thread ownership");
    lmk_procprio wrong{pid_t(tid),children[1].uid,800,PROC_TYPE_APP,false};send_packet(s,pack,lmkd_pack_set_procprio(pack,&wrong));
    check(killcount(s)==0&&score(children[1].pid)==0,"reject nonleader registration");
    record_runtime(lmkd,"post-registration");
    sample("protocol-complete");
    std::ostringstream ids;ids<<"{\"lmkd_pid\":"<<lmkd.pid<<",\"lmkd_start\":"<<lmkd.start<<",\"children\":[";
    for(size_t i=0;i<children.size();i++){if(i)ids<<",";auto&c=children[i];ids<<"{\"label\":"<<quote(c.label)<<",\"pid\":"<<c.pid<<",\"uid\":"<<c.uid<<",\"start\":"<<c.start<<",\"pidfd\":"<<c.pidfd<<",\"oom_score_adj\":"<<score(c.pid)<<"}";}ids<<"]}";write_file("/evidence/identities.json",ids.str(),true);
    const std::string events0=counters("/sys/fs/cgroup/memory.events");
    pause_ms(1200);no_oom(events0);check(killcount(s)==0,"quiet live lease cannot invent pressure");
    const bool pressure_requested=phase=="pressure"||phase=="stale";
    const bool cached_killed=pressure_requested?run_pressure_workload(phase,lmkd,s,children):false;
    const int expected_kills=cached_killed?1:0;
    // Pipes 3/4 are owned only by this PID 1 and its exact namespace owner.
    // Host lifecycle retires the real broker while LMKD stays alive, then
    // returns R only after its joined-worker receipt and process exit.
    write_all(4,"D",1);pollfd retire{3,POLLIN,0};check(poll(&retire,1,10000)==1,"host retirement deadline");
    char retired=0;check(read(3,&retired,1)==1&&retired=='R',"actual host retirement certificate");
    const U hup_deadline=now_ms()+2500;
    while(now_ms()<hup_deadline&&log_text.find("Cell PSI relay lease invalid; pressure effects disabled until lifecycle restart")==std::string::npos)pause_ms(10);
    check(log_text.find("Cell PSI relay lease invalid; pressure effects disabled until lifecycle restart")!=std::string::npos,"actual Android lease HUP diagnostic");
    verify_child(lmkd);check(killcount(s)==expected_kills,"retired lease does not kill registered targets");
    for(size_t i=cached_killed?1:0;i<children.size();i++)verify_child(children[i]);
    no_oom(events0);if(pressure_requested)pressure_budget_unchanged();
    sample("after-relay-hup");close(3);close(4);
    signal_owned(lmkd.pidfd,SIGTERM);await_exit(lmkd.pid,lmkd.pidfd,&st,2000);close(s);close(lmkd.pidfd);
    // Recheck after LMKD's exact process exit. A late incorrect kill between
    // the prior HUP check and LMKD exit must never become a skipped cleanup.
    for(size_t i=cached_killed?1:0;i<children.size();i++)verify_child(children[i]);
    std::ostringstream cleanup;cleanup<<"{\"lmkd_reaped_before_nonvictim_check\":true,\"children\":[";
    for(size_t i=0;i<children.size();i++) {
        auto& c=children[i];if(i)cleanup<<",";
        const bool known_victim=cached_killed&&i==0;
        if(known_victim)check(!alive_fd(c.pidfd),"previously reaped cached pidfd remains dead");
        else {
            verify_child(c);child_command(c,'Q');await_exit(c.pid,c.pidfd,&st,2000);
            check(WIFEXITED(st)&&WEXITSTATUS(st)==0,"every nonvictim exits normally on owned Q");
        }
        cleanup<<"{\"label\":"<<quote(c.label)<<",\"pid\":"<<c.pid<<",\"uid\":"<<c.uid<<",\"start\":"<<c.start
            <<",\"known_cached_victim\":"<<(known_victim?"true":"false")
            <<",\"exit_code\":"<<(known_victim?-1:WEXITSTATUS(st))<<",\"exit_signal\":"<<(known_victim?SIGKILL:0)<<"}";
        close(c.command);close(c.reply);close(c.pidfd);
    }
    cleanup<<"]}";write_file("/evidence/target-cleanup.json",cleanup.str(),true);
    drain_log();write_file("/evidence/phase-result.json",std::string("{\"ok\":true,\"phase\":")+quote(phase)+",\"marked_contract_rejected\":true,\"real_protocol_verified\":true,\"actual_relay_hup_verified\":true,\"nonvictim_cleanup_verified\":true,\"pressure_workload_complete\":"+(pressure_requested?"true":"false")+",\"host_audit_required\":"+(pressure_requested?"true":"false")+",\"real_pressure_verified\":false,\"route\":\"PIDFD-only minimal root\",\"production_cgroup_kill_qualified\":false,\"pid_reuse_qualified\":false}",true);
}
void little_put(unsigned char* out,U value,size_t count) {for(size_t i=0;i<count;i++)out[i]=(value>>(8*i))&255;}
U little_get(const unsigned char* in,size_t count) {U value=0;for(size_t i=0;i<count;i++)value|=U(in[i])<<(8*i);return value;}
std::array<unsigned char,32> hex_pin(const std::string& text) {
    check(text.size()==64,"exact nonce/hash hex size");std::array<unsigned char,32> result{};
    auto digit=[](char c)->unsigned {if(c>='0'&&c<='9')return unsigned(c-'0');if(c>='a'&&c<='f')return unsigned(c-'a'+10);throw std::runtime_error("non-canonical hex pin");};
    for(size_t i=0;i<result.size();i++)result[i]=static_cast<unsigned char>((digit(text[2*i])<<4)|digit(text[2*i+1]));
    return result;
}
void host_packet(void* out,size_t length,unsigned timeout) {
    pollfd wait{3,POLLIN,0};check(poll(&wait,1,timeout)==1&&(wait.revents&POLLIN)&&!(wait.revents&(POLLHUP|POLLERR|POLLNVAL)),"exact host control readiness");
    iovec io{out,length};alignas(cmsghdr) unsigned char ancillary[512]{};msghdr msg{};
    msg.msg_iov=&io;msg.msg_iovlen=1;msg.msg_control=ancillary;msg.msg_controllen=sizeof(ancillary);
    ssize_t got=recvmsg(3,&msg,MSG_CMSG_CLOEXEC|MSG_DONTWAIT|MSG_TRUNC);bool extra=false;
    if(got>=0)for(cmsghdr*c=CMSG_FIRSTHDR(&msg);c;c=CMSG_NXTHDR(&msg,c)) {
        extra=true;if(c->cmsg_level==SOL_SOCKET&&c->cmsg_type==SCM_RIGHTS&&c->cmsg_len>=CMSG_LEN(0)) {
            size_t count=(c->cmsg_len-CMSG_LEN(0))/sizeof(int);for(size_t i=0;i<count;i++){int fd=-1;memcpy(&fd,CMSG_DATA(c)+i*sizeof(int),sizeof(fd));close(fd);}
        }
    }
    check(got==ssize_t(length)&&!extra&&!(msg.msg_flags&(MSG_TRUNC|MSG_CTRUNC)),"host packet framing/extra authority");
}
void export_bootstrap(const std::string& root,const std::string& state,const std::string& domain,pid_t child,int child_fd,
                      const std::string& nonce,const std::string& lmkd_sha,const std::string& init_sha) {
    std::array<unsigned char,128> wire{};memcpy(wire.data(),"P4BOOT1!",8);
    little_put(wire.data()+8,1,4);little_put(wire.data()+12,1069,4);little_put(wire.data()+16,1069,4);
    const auto token=hex_pin(nonce),lmkd_hash=hex_pin(lmkd_sha),init_hash=hex_pin(init_sha);
    memcpy(wire.data()+24,token.data(),32);memcpy(wire.data()+56,lmkd_hash.data(),32);memcpy(wire.data()+88,init_hash.data(),32);
    std::array<int,16> fds{};fds.fill(-1);
    try {
        fds[0]=open(domain.c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        fds[1]=syscall(SYS_pidfd_open,getpid(),0);fds[2]=fcntl(child_fd,F_DUPFD_CLOEXEC,0);
        fds[3]=open((root+"/system/bin/lmkd").c_str(),O_RDONLY|O_NOFOLLOW|O_CLOEXEC);
        fds[4]=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);
        fds[5]=open((state+"/relay").c_str(),O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
        constexpr const char* namespaces[]={"pid","pid_for_children","mnt","cgroup","user","net","ipc","uts","time","time_for_children"};
        for(size_t i=0;i<10;i++)fds[6+i]=open(("/proc/"+std::to_string(child)+"/ns/"+namespaces[i]).c_str(),O_RDONLY|O_CLOEXEC);
        for(int fd:fds)check(fd>=0,"held lifecycle export FD");
        check(alive_fd(child_fd),"held init alive before export");
        iovec io{wire.data(),wire.size()};alignas(cmsghdr) unsigned char ancillary[CMSG_SPACE(sizeof(fds))]{};msghdr msg{};
        msg.msg_iov=&io;msg.msg_iovlen=1;msg.msg_control=ancillary;msg.msg_controllen=sizeof(ancillary);
        cmsghdr* c=CMSG_FIRSTHDR(&msg);c->cmsg_level=SOL_SOCKET;c->cmsg_type=SCM_RIGHTS;c->cmsg_len=CMSG_LEN(sizeof(fds));memcpy(CMSG_DATA(c),fds.data(),sizeof(fds));
        check(sendmsg(3,&msg,MSG_NOSIGNAL)==ssize_t(wire.size()),"export exact lifecycle SCM_RIGHTS");
    } catch(...) {for(int fd:fds)if(fd>=0)close(fd);throw;}
    for(int fd:fds)close(fd);
}
void project_ready(const std::string& root,const std::string& state,const std::string& nonce) {
    std::array<unsigned char,64> wire{};host_packet(wire.data(),wire.size(),10000);
    const auto token=hex_pin(nonce);
    check(memcmp(wire.data(),"P4PROJ1!",8)==0&&memcmp(wire.data()+8,token.data(),32)==0&&little_get(wire.data()+56,4)==1&&little_get(wire.data()+60,4)==0,"exact READY projection token");
    const std::string source=state+"/relay/droidloom-lmkd-psi",target=root+"/dev/socket/droidloom-lmkd-psi";
    struct stat before{};check(!lstat(source.c_str(),&before)&&S_ISSOCK(before.st_mode)&&before.st_uid==1069&&before.st_gid==1069&&(before.st_mode&0777)==0600&&U(before.st_dev)==little_get(wire.data()+40,8)&&U(before.st_ino)==little_get(wire.data()+48,8),"actual broker socket inode and role");
    int file=open(target.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600);check(file>=0,"fresh private socket projection target");close(file);
    check(!mount(source.c_str(),target.c_str(),nullptr,MS_BIND,nullptr),"project only broker socket inode");
    check(!mount(nullptr,target.c_str(),nullptr,MS_BIND|MS_REMOUNT|MS_NOSUID|MS_NODEV|MS_NOEXEC,nullptr),"socket projection restrictions");
    struct stat after{};check(!lstat(target.c_str(),&after)&&after.st_dev==before.st_dev&&after.st_ino==before.st_ino&&S_ISSOCK(after.st_mode),"projected endpoint exact inode");
    write_file(state+"/evidence/relay-projection.json","{\"device\":"+std::to_string(U(after.st_dev))+",\"inode\":"+std::to_string(U(after.st_ino))+",\"uid\":1069,\"gid\":1069,\"mode\":384}",true);
}
int main(int argc,char**argv) {
    try {
        check(argc==14,"usage: root state bootstrap-or-protocol-or-pressure-or-stale unit nonce six-main-namespace-inodes lmkd-sha init-sha; inherited fd3");
        std::string root=argv[1],state=argv[2],phase=argv[3],unit=argv[4],nonce=argv[5];
        check(geteuid()==0&&unit.rfind("p4-lmkd-relay-",0)==0&&unit.ends_with(".service")&&unit.find("/")==std::string::npos&&unit.find("..") == std::string::npos,"root-owned unit");
        const std::string stem=unit.substr(0,unit.size()-8);
        check(root=="/opt/"+stem+"/root"&&state=="/run/"+stem,"fixed executable and state roots");
        struct stat evidence{},sockets{};struct statvfs state_mount{};
        check(!stat((state+"/evidence").c_str(),&evidence)&&S_ISDIR(evidence.st_mode)&&evidence.st_uid==0&&(evidence.st_mode&077)==0,"owned state directory");
        check(!statvfs(state.c_str(),&state_mount)&&(state_mount.f_flag&ST_NOEXEC),"state noexec retained");
        check(!stat((state+"/socket").c_str(),&sockets)&&S_ISDIR(sockets.st_mode)&&sockets.st_uid==0&&(sockets.st_mode&022)==0,"owned socket state directory");
        const bool pressure_phase=phase=="pressure"||phase=="stale";
        check((phase=="bootstrap"||phase=="protocol"||pressure_phase)&&nonce.size()==64,"only fixed relay phase/token");
        close_from(4);signal(SIGTERM,on_stop);signal(SIGINT,on_stop);signal(SIGPIPE,SIG_IGN);
        char host_ready=0;host_packet(&host_ready,1,5000);check(host_ready=='H',"host driver moved out of unit root");
        std::array<U,6> outer{},main{};for(size_t i=0;i<NS.size();i++){outer[i]=inode(std::string("/proc/self/ns/")+NS[i]);main[i]=number(argv[6+i]);}
        std::string cg=self_cgroup();check(cg=="/system.slice/"+unit,"exact private unit cgroup");
        std::string cgpath="/sys/fs/cgroup"+cg;struct stat cs{};struct statfs fs{};
        check(!stat(cgpath.c_str(),&cs)&&!statfs(cgpath.c_str(),&fs)&&fs.f_type==CGROUP2_SUPER_MAGIC,"owned cgroup2");
        check(number(read_text(cgpath+"/memory.max"))==HARD&&read_text(cgpath+"/memory.high")=="max\n"&&number(read_text(cgpath+"/memory.swap.max"))==0&&number(read_text(cgpath+"/pids.max"))==64,"fixed unit limits");
        check(read_text(cgpath+"/cpu.max")=="100000 100000\n","fixed cpu quota");
        set_score(getpid(),-1000);check(!unshare(CLONE_NEWNS|CLONE_NEWPID|CLONE_NEWCGROUP|CLONE_NEWIPC|CLONE_NEWUTS|CLONE_NEWNET),"new six namespaces");
        check(!mount(nullptr,"/",nullptr,MS_REC|MS_PRIVATE,nullptr),"private mounts");
        const struct stat domain_identity=configure_memory_domain(cgpath,pressure_phase);
        int gate[2],ready[2];check(!pipe2(gate,O_CLOEXEC)&&!pipe2(ready,O_CLOEXEC),"owned gate pipes");
        int owner_fd=syscall(SYS_pidfd_open,getpid(),0);check(owner_fd>=0,"pin own namespace owner before fork");
        pid_t child=fork();check(child>=0,"private PID1 fork");
        if(!child) {
            check(!prctl(PR_SET_PDEATHSIG,SIGKILL)&&alive_fd(owner_fd),"exact init parent-death contract");
            keep_two(gate[0],ready[1]);
            check(getpid()==1&&getppid()==0,"new namespace PID1");
            write_file(cgpath+"/domain/cgroup.procs",std::to_string(getpid()));
            // The bootstrap-only phase performs no PSI registration or
            // pressure write; LMKD's fixed path is an owned child bind.
            check(!mount("proc",(root+"/proc").c_str(),"proc",MS_NOSUID|MS_NODEV|MS_NOEXEC,nullptr),"fresh private procfs");
            check(!mount((cgpath+"/domain").c_str(),(root+"/sys/fs/cgroup").c_str(),nullptr,MS_BIND,nullptr),"bind only own child memory domain");
            check(!mount((state+"/evidence").c_str(),(root+"/evidence").c_str(),nullptr,MS_BIND,nullptr),"bind only owned state");
            check(!mount(nullptr,(root+"/evidence").c_str(),nullptr,MS_REMOUNT|MS_BIND|MS_NOSUID|MS_NODEV|MS_NOEXEC,nullptr),"state bind remains noexec");
            check(!mount((state+"/socket").c_str(),(root+"/dev/socket").c_str(),nullptr,MS_BIND,nullptr),"bind only owned sockets");
            check(!mount(nullptr,(root+"/dev/socket").c_str(),nullptr,MS_REMOUNT|MS_BIND|MS_NOSUID|MS_NODEV|MS_NOEXEC,nullptr),"socket state bind remains noexec");
            check(!chroot(root.c_str())&&!chdir("/"),"private root");
            struct stat inner_evidence{},inner_sockets{};struct statvfs inner_state_mount{};
            check(!stat("/evidence",&inner_evidence)&&inner_evidence.st_dev==evidence.st_dev&&inner_evidence.st_ino==evidence.st_ino,"same owned state inode");
            check(!statvfs("/evidence",&inner_state_mount)&&(inner_state_mount.f_flag&ST_NOEXEC),"private state noexec");
            check(!stat("/dev/socket",&inner_sockets)&&inner_sockets.st_dev==sockets.st_dev&&inner_sockets.st_ino==sockets.st_ino,"same owned socket state inode");
            check(!statvfs("/dev/socket",&inner_state_mount)&&(inner_state_mount.f_flag&ST_NOEXEC),"private socket state noexec");
            check(!statfs("/proc",&fs)&&fs.f_type==PROC_SUPER_MAGIC,"fresh procfs magic");
            for(const char* path:{"/proc/sys","/proc/sysrq-trigger","/proc/irq","/proc/bus"}) {
                check(!mount(path,path,nullptr,MS_BIND,nullptr),"bind private proc global control");
                check(!mount(nullptr,path,nullptr,MS_REMOUNT|MS_BIND|MS_RDONLY|MS_NOSUID|MS_NODEV|MS_NOEXEC,nullptr),"private proc global control read-only");
            }
            check(self_cgroup()=="/domain","owned child memory domain");
            struct stat inner{};check(!stat("/sys/fs/cgroup",&inner)
                &&inner.st_dev==domain_identity.st_dev&&inner.st_ino==domain_identity.st_ino,
                "fixed memory path is exact child domain inode");
            std::ostringstream o;o<<"{\"pid\":1,\"ppid\":0,\"cgroup_dev\":"<<U(inner.st_dev)<<",\"cgroup_ino\":"<<U(inner.st_ino)<<",\"ns\":{";
            for(size_t i=0;i<NS.size();i++){U v=inode(std::string("/proc/self/ns/")+NS[i]);check(v!=outer[i]&&v!=main[i],"namespace differs from host and Main");if(i)o<<",";o<<quote(NS[i])<<":"<<v;}
            o<<"},\"namespace_root_dev\":"<<U(cs.st_dev)<<",\"namespace_root_ino\":"<<U(cs.st_ino)<<",\"memory_mount_path\":\"/sys/fs/cgroup\",\"domain_relative\":\"/domain\",\"domain_dev\":"<<U(domain_identity.st_dev)<<",\"domain_ino\":"<<U(domain_identity.st_ino)<<",\"root_pressure_test_performed\":false,\"evidence_dev\":"<<U(evidence.st_dev)<<",\"evidence_ino\":"<<U(evidence.st_ino)<<",\"socket_dev\":"<<U(sockets.st_dev)<<",\"socket_ino\":"<<U(sockets.st_ino)<<",\"state_noexec\":true,\"closed_inherited_fds\":true,\"only_owned_gate_fds\":[3,4],\"lmkd_started\":false}";
            check(score(1)==-1000,"init protected score");write_file("/evidence/inner-preflight.json",o.str(),true);write_all(4,"R",1);
            pollfd f{3,POLLIN,0};check(poll(&f,1,20000)==1,"outer approval timeout");char token;check(read(3,&token,1)==1&&token=='G',"outer approval");
            try {
                if(phase!="bootstrap")run_phase(phase);
                else {
                    write_all(4,"D",1);pollfd retire{3,POLLIN,0};check(poll(&retire,1,10000)==1,"host bootstrap retirement deadline");
                    char certificate=0;check(read(3,&certificate,1)==1&&certificate=='R',"host bootstrap retirement certificate");
                    close(3);close(4);
                    write_file("/evidence/phase-result.json","{\"ok\":true,\"phase\":\"bootstrap\",\"lmkd_started\":false,\"psi_registered\":false,\"real_pressure_verified\":false}",true);
                }
            } catch(...) {
                try {drain_log();sample("phase-failure");}
                catch(const std::exception& e) {dprintf(2,"failure evidence capture: %s\n",e.what());}
                throw;
            }
            _exit(0);
        }
        close(owner_fd);close(gate[0]);close(ready[1]);int pfd=syscall(SYS_pidfd_open,child,0);check(pfd>=0,"private init pidfd");
        pollfd f{ready[0],POLLIN,0};check(poll(&f,1,10000)==1,"inner preflight timeout");char r;check(read(ready[0],&r,1)==1&&r=='R',"inner preflight complete");
        std::ostringstream o;o<<"{\"child_host_pid\":"<<child<<",\"child_start\":"<<start_ticks(child)<<",\"cgroup\":"<<quote(cg)<<",\"cgroup_dev\":"<<U(cs.st_dev)<<",\"cgroup_ino\":"<<U(cs.st_ino)<<",\"domain_relative\":\"/domain\",\"domain_dev\":"<<U(domain_identity.st_dev)<<",\"domain_ino\":"<<U(domain_identity.st_ino)<<",\"bootstrap_cgroup\":\"/supervisor\",\"bootstrap_host_pid\":"<<getpid()<<",\"lmkd_started\":false}";
        write_file(state+"/evidence/outer-preflight.json",o.str(),true);
        export_bootstrap(root,state,cgpath+"/domain",child,pfd,nonce,argv[12],argv[13]);
        project_ready(root,state,nonce);write_all(gate[1],"G",1);
        f={ready[0],POLLIN,0};check(poll(&f,1,pressure_phase?35000:20000)==1,"inner protocol/workload completion deadline");
        check(read(ready[0],&r,1)==1&&r=='D',"real protocol complete");check(send(3,"D",1,MSG_NOSIGNAL)==1,"notify host protocol complete");
        host_packet(&r,1,10000);check(r=='R',"host relay retired before fixture cleanup");write_all(gate[1],"R",1);close(gate[1]);close(ready[0]);
        U end=now_ms()+10000;while(alive_fd(pfd)&&now_ms()<end&&!stopped)usleep(25000);
        if(alive_fd(pfd)) { signal_owned(pfd,SIGKILL); }
        int status=0;check(waitpid(child,&status,0)==child,"private init wait");close(pfd);
        return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
    } catch(const std::exception&e) {dprintf(2,"private fixture stopped: %s\n",e.what());return 1;}
}
