/* The authenticated stock sudo may enter this fixed program only.
 * Neither a caller pathname nor a caller-selected executable crosses this gate. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <openssl/evp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/syscall.h>
#include <sys/sysmacros.h>
#include <unistd.h>
#include "maintenance_inputs.h"

#define PREFIX "/usr/lib/droidloom/production/current/"
#define SCRIPT PREFIX "droidloom-maintenance.py"
#define SELF PREFIX "droidloom-maintenance"
#define PYTHON "/usr/bin/python3.14"
#define CONTEXT "u:system_r:p4_linux_maintenance_t:s0"

static int reject(const char *where) {
    int e = errno ? errno : EPERM;
    fprintf(stderr, "droidloom-maintenance: %s: %s\n", where, strerror(e));
    return 77;
}
static bool same(const struct stat *a, const struct stat *b) {
    return a->st_dev == b->st_dev && a->st_ino == b->st_ino &&
        a->st_mode == b->st_mode && a->st_uid == b->st_uid &&
        a->st_gid == b->st_gid && a->st_nlink == b->st_nlink &&
        a->st_size == b->st_size &&
        a->st_mtim.tv_sec == b->st_mtim.tv_sec &&
        a->st_mtim.tv_nsec == b->st_mtim.tv_nsec &&
        a->st_ctim.tv_sec == b->st_ctim.tv_sec &&
        a->st_ctim.tv_nsec == b->st_ctim.tv_nsec;
}
/* All components are exact root-owned non-writable directories. No resolve()
 * or caller link is accepted as a replacement for the originally opened inode. */
static int fixed_open(const char *path, mode_t mode, uint64_t bytes, const char *hash) {
    char copy[PATH_MAX], *part, *save = NULL;
    if (strlen(path) >= sizeof(copy) || path[0] != '/') { errno=EINVAL; return -1; }
    strcpy(copy,path+1);
    int dir=open("/",O_PATH|O_DIRECTORY|O_CLOEXEC), fd=-1;
    if(dir<0) return -1;
    part=strtok_r(copy,"/",&save);
    while(part) {
        char *next=strtok_r(NULL,"/",&save);
        if(next) {
            int n=openat(dir,part,O_PATH|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);
            struct stat st;
            if(n<0 || fstat(n,&st) || !S_ISDIR(st.st_mode) ||
               st.st_uid || st.st_gid || (st.st_mode&0022)) {
                if(n>=0) close(n);
                close(dir); errno=EPERM; return -1;
            }
            close(dir);dir=n;
        } else {
            fd=openat(dir,part,O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK);
        }
        part=next;
    }
    close(dir);
    struct stat a,b;
    if(fd<0) return -1;
    if(fstat(fd,&a) || !S_ISREG(a.st_mode) || a.st_uid || a.st_gid ||
       a.st_nlink!=1 || (a.st_mode&07777)!=mode ||
       (bytes && (uint64_t)a.st_size!=bytes)) goto bad;
    if(hash) {
        unsigned char block[65536], digest[EVP_MAX_MD_SIZE];
        unsigned int size=0; ssize_t n;
        EVP_MD_CTX *ctx=EVP_MD_CTX_new();
        if(!ctx) goto bad;
        int ok=EVP_DigestInit_ex(ctx,EVP_sha256(),NULL)==1;
        while(ok && (n=read(fd,block,sizeof(block)))!=0) {
            if(n<0) {if(errno==EINTR) continue;ok=0;break;}
            ok=EVP_DigestUpdate(ctx,block,(size_t)n)==1;
        }
        ok=ok && EVP_DigestFinal_ex(ctx,digest,&size)==1 && size==32;
        EVP_MD_CTX_free(ctx);
        if(!ok) goto bad;
        char actual[65];
        for(size_t i=0;i<32;i++) snprintf(actual+2*i,3,"%02x",digest[i]);
        if(!ok || strcmp(actual,hash) || lseek(fd,0,SEEK_SET)<0) goto bad;
    }
    if(fstat(fd,&b) || !same(&a,&b)) goto bad;
    return fd;
bad: close(fd);errno=EPERM;return -1;
}
static bool text_is(const char *path,const char *expected) {
    char body[256];
    int f=open(path,O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(f<0) return false;
    ssize_t n=read(f,body,sizeof(body));close(f);
    if(n<0 || n==(ssize_t)sizeof(body)) return false;
    while(n>0 && (body[n-1]=='\0'||body[n-1]=='\n')) --n;
    return (size_t)n==strlen(expected) && !memcmp(body,expected,(size_t)n);
}
/* x86_64 Linux 6.18 UAPI, include/uapi/linux/lsm.h and syscall_64.tbl.
 * Select SELinux explicitly; never fall back to the first legacy proc hook. */
struct maintenance_lsm_context {
    uint64_t id, flags, len, ctx_len;
    unsigned char data[256];
};
_Static_assert(sizeof(struct maintenance_lsm_context) == 288, "LSM context ABI");
static bool selinux_context_is(void) {
#if !defined(__x86_64__)
#error "The admitted maintenance executable is x86_64 only"
#endif
    struct maintenance_lsm_context context = { .id = 101 };
    uint32_t size = sizeof(context);
    long count = syscall(459, (unsigned int)100, &context, &size, (uint32_t)1);
    if (count != 1 || context.id != 101 || context.flags != 0 ||
        context.ctx_len != sizeof(CONTEXT) ||
        context.len != ((32 + context.ctx_len + 7) & ~7ULL) ||
        size != context.len || size > sizeof(context) ||
        memcmp(context.data, CONTEXT, sizeof(CONTEXT))) {
        if (count >= 0) errno = EPROTO;
        return false;
    }
    for (uint64_t i = context.ctx_len; i < context.len - 32; ++i)
        if (context.data[i] != 0) { errno = EPROTO; return false; }
    return true;
}
static bool release_id(const char *s) {
    if(strlen(s)!=64) return false;
    for(size_t i=0;i<64;i++)
        if(!((s[i]>='0'&&s[i]<='9')||(s[i]>='a'&&s[i]<='f'))) return false;
    return true;
}
static bool root_mapping(void) {
    char buf[128];unsigned long long inside,outside,count;char extra;
    int fd=open("/proc/self/uid_map",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    if(fd<0) return false;
    ssize_t n=read(fd,buf,sizeof(buf)-1);close(fd);
    if(n<=0 || n==(ssize_t)sizeof(buf)-1) return false;
    buf[n]=0;
    return sscanf(buf,"%llu %llu %llu %c",&inside,&outside,&count,&extra)==3 &&
           inside==0 && outside==0 && count==4294967295ULL;
}
int main(int argc,char **argv) {
    bool verify=argc==3 && !strcmp(argv[1],"verify") && release_id(argv[2]);
    bool fixed=argc==2 && (!strcmp(argv[1],"status") || !strcmp(argv[1],"collect") ||
                         !strcmp(argv[1],"rollback") || !strcmp(argv[1],"reboot"));
    if(!verify && !fixed) {
        fputs("usage: droidloom-maintenance {status|collect|rollback|reboot|verify RELEASE_SHA256}\n",stderr);
        return 64;
    }
    if(getuid()!=0 || geteuid()!=0 || getgid()!=0 || getegid()!=0 ||
       !root_mapping() || !selinux_context_is() ||
       !text_is("/sys/fs/selinux/enforce","1")) return reject("authenticated native maintenance context required");
    int own=fixed_open(SELF,0755,0,NULL), proc=open("/proc/self/exe",O_RDONLY|O_CLOEXEC);
    struct stat a,b;
    if(own<0 || proc<0 || fstat(own,&a) || fstat(proc,&b) || !same(&a,&b))
        return reject("normal published self inode");
    close(proc);close(own);
    int script=fixed_open(SCRIPT,0444,DROIDLOOM_MAINTENANCE_SCRIPT_BYTES,DROIDLOOM_MAINTENANCE_SCRIPT_SHA256);
    int python=fixed_open(PYTHON,0755,DROIDLOOM_MAINTENANCE_PYTHON_BYTES,DROIDLOOM_MAINTENANCE_PYTHON_SHA256);
    if(script<0 || python<0) return reject("normal source/interpreter pin");
    int sf=fcntl(script,F_DUPFD_CLOEXEC,16),pf=fcntl(python,F_DUPFD_CLOEXEC,16);
    if(sf<0 || pf<0) return reject("hold original executable inputs");
    close(script);close(python);
    if(dup3(pf,3,O_CLOEXEC)<0 || dup3(sf,4,0)<0) return reject("fixed executable descriptors");
    int null=open("/dev/null",O_RDONLY|O_CLOEXEC|O_NOFOLLOW);
    struct stat ns;
    if(null<0 || fstat(null,&ns) || !S_ISCHR(ns.st_mode) || ns.st_rdev!=makedev(1,3))
        return reject("native null stdin");
    if(dup2(null,0)<0) return reject("null stdin");
    if(null>4) close(null);
    if(close_range(5,~0U,0)<0 || chdir("/") || prctl(PR_SET_NO_NEW_PRIVS,1,0,0,0))
        return reject("fixed interpreter confinement");
    umask(077);
    char *args[]={PYTHON,"-I","-B","/proc/self/fd/4","--maintenance",argv[1],verify?argv[2]:NULL,NULL};
    char *env[]={"PATH=/usr/sbin:/usr/bin:/sbin:/bin","LC_ALL=C","LANG=C","PYTHONNOUSERSITE=1",NULL};
    execveat(3,"",args,env,AT_EMPTY_PATH);
    return reject("fixed interpreter exec");
}
