#include <sys/resource.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <sys/ucontext.h>
#include <sys/syscall.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <errno.h>
#include <cstdio>
#include <cstdint>
extern "C" const unsigned char owned_int80_probe[];
struct Record { long signal; long code; long trap; long error; long at_int80; long eax; long native_pid; long compat_pid; };
static int channel_fd = -1;
static pid_t expected_pid = -1;
static void Fault(int signal, siginfo_t* info, void* context) {
    const auto* value = static_cast<ucontext_t*>(context);
    Record record{signal, info->si_code, value->uc_mcontext.gregs[REG_TRAPNO],
                  value->uc_mcontext.gregs[REG_ERR],
                  value->uc_mcontext.gregs[REG_RIP] == reinterpret_cast<intptr_t>(owned_int80_probe),
                  value->uc_mcontext.gregs[REG_RAX], expected_pid, -1};
    const ssize_t bytes = write(channel_fd, &record, sizeof(record));
    _exit(bytes == sizeof(record) ? 100 + signal : 89);
}
static int64_t Now() { timespec t{}; if (clock_gettime(CLOCK_MONOTONIC,&t)) _exit(90); return int64_t{t.tv_sec}*1000+t.tv_nsec/1000000; }
int main() {
    struct sigaction old{};
    if (sigaction(SIGCHLD,nullptr,&old) || old.sa_handler != SIG_DFL || (old.sa_flags&SA_NOCLDWAIT)) return 64;
    int p[2]; if (pipe2(p,O_CLOEXEC)) return 65;
    const pid_t parent=getpid(), child=fork(); if (child<0) return 66;
    if (!child) {
        close(p[0]); channel_fd=p[1]; expected_pid=getpid();
        const rlimit core{0,0};
        if (prctl(PR_SET_PDEATHSIG,SIGKILL) || getppid()!=parent || setrlimit(RLIMIT_CORE,&core)) _exit(82);
        struct sigaction action{}; action.sa_sigaction=Fault; action.sa_flags=SA_SIGINFO;
        if (sigemptyset(&action.sa_mask) || sigaction(SIGSEGV,&action,nullptr) || sigaction(SIGILL,&action,nullptr) || sigaction(SIGSYS,&action,nullptr)) _exit(83);
        uint32_t result;
        asm volatile(".globl owned_int80_probe\nowned_int80_probe:\nint $0x80" : "=a"(result) : "0"(uint32_t{20}), "b"(uint32_t{0}) : "r8","r9","r10","r11","cc","memory");
        Record record{0,0,0,0,0,0,expected_pid,static_cast<int32_t>(result)};
        if(write(channel_fd,&record,sizeof(record))!=sizeof(record)) _exit(84);
        _exit(result==static_cast<uint32_t>(expected_pid)?0:85);
    }
    close(p[1]); int status=0; pid_t waited=0; bool killed=false;
    const int64_t deadline=Now()+2000;
    while ((waited=waitpid(child,&status,WNOHANG))!=child) {
        if(waited<0&&errno!=EINTR) break;
        if(Now()>=deadline){ killed=true; if(kill(child,SIGKILL)&&errno!=ESRCH)return 67; break; }
        timespec delay{0,1000000}; nanosleep(&delay,nullptr);
    }
    if(killed){const int64_t end=Now()+1000; while((waited=waitpid(child,&status,WNOHANG))!=child&&Now()<end){ if(waited<0&&errno!=EINTR)break;timespec delay{0,1000000};nanosleep(&delay,nullptr); }}
    if(waited!=child)return 68;
    Record record{}; const ssize_t bytes=read(p[0],&record,sizeof(record));char extra;const ssize_t tail=read(p[0],&extra,1);close(p[0]);
    const bool complete=bytes==sizeof(record)&&tail==0&&!killed;
    std::printf("{\"complete\":%s,\"reaped\":true,\"forced_kill\":%s,\"wait_status\":%d,\"record_bytes\":%zd,\"signal\":%ld,\"si_code\":%ld,\"trapno\":%ld,\"error\":%ld,\"fault_at_exact_int80\":%s,\"rax\":%ld,\"native_pid\":%ld,\"compat_pid\":%ld,\"compat_supported_observed\":%s,\"filters_installed\":0}\n",complete?"true":"false",killed?"true":"false",status,bytes,record.signal,record.code,record.trap,record.error,record.at_int80?"true":"false",record.eax,record.native_pid,record.compat_pid,complete&&record.signal==0&&record.compat_pid==record.native_pid?"true":"false");
    return complete?0:1;
}
