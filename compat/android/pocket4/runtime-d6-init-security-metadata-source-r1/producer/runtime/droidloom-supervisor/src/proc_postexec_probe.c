/* Fixed post-exec PID-1 probe. No libc, dynamic linker, command interpreter,
 * external pathname argument, namespace creation, or privilege acquisition.
 * The parent seals this normal-built ELF and authenticates its exact inode
 * through the already owned PIDFD before releasing the write-test barrier. */
#include <stdint.h>
#include <stddef.h>
#include <fcntl.h>
#include <sys/syscall.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <poll.h>
#include <linux/prctl.h>
#include <linux/capability.h>
#include <errno.h>

_Static_assert(sizeof(void *) == 8 && sizeof(long) == 8, "x86_64 LP64 only");
_Static_assert(sizeof(struct stat) == 144, "complete x86_64 kernel stat ABI");
_Static_assert(sizeof(struct statfs) == 120, "complete x86_64 statfs ABI");
_Static_assert(sizeof(struct msghdr) == 56, "x86_64 msghdr ABI");

enum { CONTROL_FD = 3, CAP_LAST = 40, SECUREBITS_ZERO = 0xef };
enum { READY = 51, CHECK = 52, CHECKED = 53, STOP = 6, FAILED = 7 };
static const uint64_t MAGIC = UINT64_C(0x444c4e5342524b31);
struct packet {
    uint64_t magic;
    unsigned char nonce[16];
    uint32_t phase;
    int32_t error;
    uint32_t pid;
    uint32_t reserved;
};
_Static_assert(sizeof(struct packet) == 40, "fixed broker packet ABI");
struct time_value { int64_t sec, nsec; };
static unsigned char nonce[16];
static uint32_t parent_pid;
static unsigned int stage;

static inline long call6(long n, long a, long b, long c, long d, long e, long f) {
    register long r10 __asm__("r10") = d;
    register long r8 __asm__("r8") = e;
    register long r9 __asm__("r9") = f;
    long result;
    __asm__ volatile("syscall" : "=a"(result)
        : "a"(n), "D"(a), "S"(b), "d"(c), "r"(r10), "r"(r8), "r"(r9)
        : "rcx", "r11", "memory");
    return result;
}
#define C0(n) call6((n),0,0,0,0,0,0)
#define C1(n,a) call6((n),(long)(a),0,0,0,0,0)
#define C2(n,a,b) call6((n),(long)(a),(long)(b),0,0,0,0)
#define C3(n,a,b,c) call6((n),(long)(a),(long)(b),(long)(c),0,0,0)
#define C4(n,a,b,c,d) call6((n),(long)(a),(long)(b),(long)(c),(long)(d),0,0)
#define C5(n,a,b,c,d,e) call6((n),(long)(a),(long)(b),(long)(c),(long)(d),(long)(e),0)
#define P0(n) C5(SYS_prctl,(n),0,0,0,0)

static int equal(const void *aa, const void *bb, unsigned long n) {
    const unsigned char *a=aa,*b=bb;
    for (unsigned long i=0;i<n;i++) if (a[i]!=b[i]) return 0;
    return 1;
}
static int string(const char *a, const char *b) {
    for (unsigned long i=0;i<128;i++) {
        if (a[i]!=b[i]) return 0;
        if (!a[i]) return 1;
    }
    return 0;
}
__attribute__((noreturn)) static void finish(int code) {
    C1(SYS_exit_group,code);
    __builtin_unreachable();
}
static void packet_fill(struct packet *p,unsigned int phase,int error) {
    p->magic=MAGIC;
    for (unsigned int i=0;i<16;i++) p->nonce[i]=nonce[i];
    p->phase=phase;p->error=error;p->pid=1;p->reserved=0;
}
static int send_record(unsigned int phase,int error) {
    struct packet p={0};packet_fill(&p,phase,error);
    struct iovec v={&p,sizeof(p)};
    struct msghdr m={0};m.msg_iov=&v;m.msg_iovlen=1;
    return C3(SYS_sendmsg,CONTROL_FD,&m,MSG_DONTWAIT|MSG_NOSIGNAL)==(long)sizeof(p);
}
__attribute__((noreturn)) static void failed_at(unsigned int line,long error) {
    unsigned int e=(error<0&&error>=-4095)?(unsigned int)-error:EPROTO;
    if (stage<1||stage>8||line==0||line>4095) finish(126);
    (void)send_record(FAILED,(int)(0x50000000u|(stage<<24)|(line<<12)|e));
    finish(127);
}
#define REQUIRE(x) do { if (!(x)) failed_at(__LINE__,-EPROTO); } while(0)
#define OK(x) do { long result_=(x); if(result_<0)failed_at(__LINE__,result_); } while(0)

static uint64_t clock_ns(void) {
    struct time_value t={0};long r=C2(SYS_clock_gettime,1,&t);
    if(r<0) failed_at(__LINE__,r);
    REQUIRE(t.sec>=0 && t.nsec>=0 && t.nsec<1000000000);
    return (uint64_t)t.sec*UINT64_C(1000000000)+(uint64_t)t.nsec;
}
static void command(unsigned int expected) {
    const uint64_t deadline=clock_ns()+UINT64_C(3000000000);
    struct pollfd event={CONTROL_FD,POLLIN,0};
    for (;;) {
        uint64_t now=clock_ns();
        if(now>=deadline) failed_at(__LINE__,-ETIMEDOUT);
        int timeout=(int)((deadline-now+999999)/1000000);
        event.revents=0;
        long r=C3(SYS_poll,&event,1,timeout);
        if(r==-EINTR) continue;
        if(r<0) failed_at(__LINE__,r);
        if(r==0) failed_at(__LINE__,-ETIMEDOUT);
        REQUIRE(r==1 && !(event.revents&(POLLERR|POLLNVAL)) && (event.revents&POLLIN));
        break;
    }
    struct packet p={0};struct iovec v={&p,sizeof(p)};
    unsigned long ancillary[16]={0};struct msghdr m={0};
    m.msg_iov=&v;m.msg_iovlen=1;m.msg_control=ancillary;m.msg_controllen=sizeof(ancillary);
    long r=C3(SYS_recvmsg,CONTROL_FD,&m,MSG_DONTWAIT|MSG_CMSG_CLOEXEC);
    if(r==0) finish(0);
    if(r<0) failed_at(__LINE__,r);
    /* Any received FD is closed by exit on rejection, never interpreted. */
    REQUIRE(r==(long)sizeof(p) && !(m.msg_flags&(MSG_TRUNC|MSG_CTRUNC)) && m.msg_controllen==0);
    REQUIRE(p.magic==MAGIC && equal(p.nonce,nonce,16) && p.reserved==0 && p.error==0 && p.pid==parent_pid);
    if(p.phase==STOP) finish(0);
    REQUIRE(p.phase==expected && clock_ns()<deadline);
}

static struct stat metadata(int fd) {
    struct stat s={0};OK(C2(SYS_fstat,fd,&s));return s;
}
static struct statfs filesystem(int fd) {
    struct statfs s={0};OK(C2(SYS_fstatfs,fd,&s));return s;
}
static int opened(int dir,const char *name,int flags,unsigned int mode) {
    long r=C4(SYS_openat,dir,name,flags|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,mode);
    if(r<0) failed_at(__LINE__,r);
    REQUIRE(r<=0x7fffffff);return (int)r;
}
static void closed(int fd) { OK(C1(SYS_close,fd)); }

static void zero_authority(void) {
    uint32_t u[3]={1,1,1},g[3]={1,1,1};
    OK(C3(SYS_getresuid,&u[0],&u[1],&u[2]));
    OK(C3(SYS_getresgid,&g[0],&g[1],&g[2]));
    REQUIRE(u[0]==0&&u[1]==0&&u[2]==0&&g[0]==0&&g[1]==0&&g[2]==0);
    REQUIRE(C0(SYS_getpid)==1 && C0(SYS_getppid)==0 && C0(SYS_getuid)==0 && C0(SYS_geteuid)==0);
    REQUIRE(C0(SYS_getgid)==0 && C0(SYS_getegid)==0 && C2(SYS_getgroups,0,0)==0);
    REQUIRE(P0(PR_GET_NO_NEW_PRIVS)==1 && P0(PR_GET_SECCOMP)==2 && P0(PR_GET_SECUREBITS)==SECUREBITS_ZERO);
    struct __user_cap_header_struct h={_LINUX_CAPABILITY_VERSION_3,0};
    struct __user_cap_data_struct d[2]={{0,0,0},{0,0,0}};
    OK(C2(SYS_capget,&h,d));
    for(unsigned int i=0;i<2;i++) REQUIRE(d[i].effective==0 && d[i].permitted==0 && d[i].inheritable==0);
    for(unsigned int i=0;i<=CAP_LAST;i++) {
        REQUIRE(C5(SYS_prctl,PR_CAPBSET_READ,i,0,0,0)==0);
        REQUIRE(C5(SYS_prctl,PR_CAP_AMBIENT,PR_CAP_AMBIENT_IS_SET,i,0,0)==0);
    }
    REQUIRE(C5(SYS_prctl,PR_CAPBSET_READ,CAP_LAST+1,0,0,0)==-EINVAL);
    int death=0;OK(C5(SYS_prctl,PR_GET_PDEATHSIG,&death,0,0,0));REQUIRE(death==9);
}
static void descriptors(void) {
    for(int i=0;i<3;i++) {
        struct stat s=metadata(i);
        REQUIRE((s.st_mode&S_IFMT)==S_IFCHR && s.st_rdev==259 && C2(SYS_fcntl,i,F_GETFD)==0);
    }
    REQUIRE((metadata(CONTROL_FD).st_mode&S_IFMT)==S_IFSOCK && C2(SYS_fcntl,CONTROL_FD,F_GETFD)==0);
    int kind=0;unsigned int n=sizeof(kind);
    OK(C5(SYS_getsockopt,CONTROL_FD,SOL_SOCKET,SO_TYPE,&kind,&n));
    REQUIRE(n==sizeof(kind)&&kind==SOCK_SEQPACKET);
    int dir=opened(AT_FDCWD,"/proc/1/fd",O_RDONLY|O_DIRECTORY,0);
    REQUIRE(dir==4);
    unsigned int seen=0;unsigned char data[4096];
    for(;;) {
        long count=C3(SYS_getdents64,dir,data,sizeof(data));
        if(count<0)failed_at(__LINE__,count);
        if(count==0)break;
        REQUIRE(count<=(long)sizeof(data));
        unsigned long pos=0;
        while(pos<(unsigned long)count) {
            REQUIRE((unsigned long)count-pos>=20);
            unsigned int length=(unsigned int)data[pos+16]|((unsigned int)data[pos+17]<<8);
            REQUIRE(length>=20 && length<=(unsigned long)count-pos);
            unsigned long end=pos+19;while(end<pos+length&&data[end])end++;
            REQUIRE(end<pos+length);
            unsigned long size=end-(pos+19);const unsigned char *name=&data[pos+19];
            if(!((size==1&&name[0]=='.')||(size==2&&name[0]=='.'&&name[1]=='.'))) {
                REQUIRE(size==1 && name[0]>='0' && name[0]<='4');
                unsigned int bit=1u<<(name[0]-'0');REQUIRE(!(seen&bit));seen|=bit;
            }
            pos+=length;
        }
    }
    REQUIRE(seen==31);closed(dir);
}

static void same_oom_value(void) {
    int proc=opened(AT_FDCWD,"/proc",O_PATH|O_DIRECTORY,0);
    struct statfs fs=filesystem(proc);struct stat proot=metadata(proc);
    REQUIRE(fs.f_type==0x9fa0 && (fs.f_flags&15)==14);
    int score=opened(AT_FDCWD,"/proc/1/oom_score_adj",O_RDWR,0);
    struct stat s=metadata(score);
    REQUIRE(s.st_mode==(S_IFREG|0644) && s.st_uid==0 && s.st_gid==0 && s.st_dev==proot.st_dev);
    unsigned char before[32]={0},after[32]={0};
    long n=C3(SYS_read,score,before,sizeof(before));
    if(n<0)failed_at(__LINE__,n);
    REQUIRE(n>1 && n<(long)sizeof(before) && before[n-1]=='\n');
    unsigned long pos=before[0]=='-'?1:0;int value=0;
    REQUIRE(pos<(unsigned long)n-1);
    for(;pos<(unsigned long)n-1;pos++) {
        REQUIRE(before[pos]>='0'&&before[pos]<='9');value=value*10+(before[pos]-'0');REQUIRE(value<=1000);
    }
    REQUIRE(C3(SYS_lseek,score,0,SEEK_SET)==0);
    long written=C3(SYS_write,score,before,n);
    if(written<0)failed_at(__LINE__,written);
    REQUIRE(written==n && C3(SYS_lseek,score,0,SEEK_SET)==0);
    long reread=C3(SYS_read,score,after,sizeof(after));
    if(reread<0)failed_at(__LINE__,reread);
    REQUIRE(reread==n&&equal(before,after,(unsigned long)n));
    closed(score);closed(proc);
    const char *protected[2]={"/proc/sys/kernel/hostname","/proc/sysrq-trigger"};
    for(unsigned int i=0;i<2;i++) {
        long r=C4(SYS_openat,AT_FDCWD,protected[i],O_WRONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK,0);
        if(r>=0) {closed((int)r);failed_at(__LINE__,-EPROTO);}
        REQUIRE(r==-EROFS||r==-EACCES||r==-EPERM);
    }
}

static int xattr_observation(void) {
    int dev=opened(AT_FDCWD,"/dev",O_PATH|O_DIRECTORY,0);
    struct stat parent=metadata(dev);struct statfs fs=filesystem(dev);
    /* This proves only the actual private tmpfs and mount flags, not SELinux
     * support. The precise setxattr errno is returned without a success rule. */
    REQUIRE(fs.f_type==0x01021994 && (fs.f_flags&15)==10);
    int fd=opened(dev,"selinux-xattr-private-observation",O_RDWR|O_CREAT|O_EXCL,0600);
    struct stat s=metadata(fd);
    REQUIRE(s.st_dev==parent.st_dev && s.st_mode==(S_IFREG|0600) && s.st_nlink==1 && s.st_uid==0 && s.st_gid==0 && s.st_size==0);
    static const char label[]="u:object_r:boot_status_prop:s0";
    long r=C5(SYS_fsetxattr,fd,"security.selinux",label,sizeof(label),0);
    int observed=0;
    if(r==0) {
        unsigned char value[64]={0};long n=C4(SYS_fgetxattr,fd,"security.selinux",value,sizeof(value));
        if(n<0)failed_at(__LINE__,n);
        REQUIRE(n==(long)sizeof(label)&&equal(value,label,sizeof(label)));
    } else {
        REQUIRE(r<0&&r>=-4095);observed=(int)-r;
    }
    OK(C3(SYS_unlinkat,dev,"selinux-xattr-private-observation",0));
    closed(fd);closed(dev);return observed;
}

__attribute__((noreturn,used)) void probe_main(uintptr_t *stack) {
    /* Refuse every ordinary host invocation before changing even this
     * process's dumpability. The real probe must be the sealed same PID 1. */
    if(C0(SYS_getpid)!=1||C0(SYS_getppid)!=0)finish(125);
    uintptr_t argc=stack[0];char **argv=(char **)&stack[1];
    if(argc!=3||argv[3]!=0||argv[4]!=0||!string(argv[0],"droidloom-private-proc-postexec-v1"))finish(125);
    for(unsigned int i=0;i<32;i++) {
        unsigned char c=(unsigned char)argv[1][i];unsigned int v;
        if(c>='0'&&c<='9')v=c-'0';else if(c>='a'&&c<='f')v=c-'a'+10;else finish(125);
        if(!(i&1))nonce[i/2]=(unsigned char)(v<<4);else nonce[i/2]|=(unsigned char)v;
    }
    if(argv[1][32]!=0)finish(125);
    parent_pid=0;unsigned int digits=0;
    while(argv[2][digits]) {
        unsigned char c=(unsigned char)argv[2][digits];
        if(digits>=10||c<'0'||c>'9'||parent_pid>214748364u)finish(125);
        parent_pid=parent_pid*10+(c-'0');if(parent_pid>2147483647u)finish(125);digits++;
    }
    if(digits==0||parent_pid<=1)finish(125);
    stage=1;zero_authority();
    /* Only a stricter setting is allowed. No PR_SET_DUMPABLE=1/2 path exists. */
    OK(C5(SYS_prctl,PR_SET_DUMPABLE,0,0,0,0));REQUIRE(P0(PR_GET_DUMPABLE)==0);
    stage=2;descriptors();
    REQUIRE(send_record(READY,0));
    stage=3;command(CHECK);
    /* The parent's held-exe/PIDFD/namespace/status checks precede this gate. */
    zero_authority();REQUIRE(P0(PR_GET_DUMPABLE)==0);
    stage=4;same_oom_value();
    stage=5;int observed=xattr_observation();
    stage=6;descriptors();zero_authority();REQUIRE(P0(PR_GET_DUMPABLE)==0);
    REQUIRE(send_record(CHECKED,observed));
    stage=7;command(STOP);finish(0);
}

__asm__(".pushsection .text\n.global _start\n.type _start,@function\n_start:\nmov %rsp,%rdi\nand $-16,%rsp\ncall probe_main\nud2\n.size _start,.-_start\n.popsection\n");
