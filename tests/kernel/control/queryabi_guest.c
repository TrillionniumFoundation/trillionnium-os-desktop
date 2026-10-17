/* An isolated Asterinas guest-only HOS2 QueryAbi probe. Does not modify CPU quotas. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <sys/wait.h>
#include <sys/types.h>
#include <stdlib.h>
#include <limits.h>

#define HOS_QUERY_IOCTL 0xC0204802U
static void fail(const char *at){ printf("HEPTA_QUERYABI_FAIL at=%s errno=%d\n",at,errno); }
static void u16le(unsigned char *buf, uint16_t x){buf[0]=(unsigned char)x;buf[1]=(unsigned char)(x>>8);}
static void u32le(unsigned char *buf, uint32_t x){for(int i=0;i<4;i++)buf[i]=(unsigned char)(x>>(i*8));}
static void u64le(unsigned char *buf, uint64_t x){for(int i=0;i<8;i++)buf[i]=(unsigned char)(x>>(i*8));}
static uint32_t read32(const unsigned char *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static uint64_t read64(const unsigned char *p){uint64_t n=0;for(int i=7;i>=0;i--)n=n*256+p[i];return n;}
static void prep(unsigned char *req, int seq){
    memset(req,0,64);
    memcpy(req,"HOS2",4);u16le(req+4,2);u16le(req+6,0);
    u16le(req+8,1);u32le(req+12,64);
    for(int i=0;i<16;i++)req[24+i]=(unsigned char)(i+1+seq);
}
static int run_request(int fd, unsigned char *request, unsigned int request_len,
                       unsigned char *response, unsigned int response_cap){
    unsigned char tr[32]={0};
    u64le(tr,(uint64_t)(uintptr_t)request);
    u64le(tr+8,(uint64_t)(uintptr_t)response);
    u32le(tr+16,request_len);u32le(tr+20,response_cap);
    memset(response,0,response_cap);
    return ioctl(fd,HOS_QUERY_IOCTL,tr);
}
static int run_query(int fd, unsigned char *request, unsigned char *response, unsigned int response_cap){
    return run_request(fd,request,64,response,response_cap);
}
static int valid_reply(const unsigned char *r,const unsigned char *q){
    static const unsigned char zeros[16]={0};
    return memcmp(r,"HOSR",4)==0 && r[4]==2 && r[5]==0 &&
        r[6]==0 && r[7]==0 && /* experimental major=2, minor=0 */
        r[8]==1 && r[9]==0 && r[10]==0 && r[11]==0 &&
        read32(r+12)==64 && read32(r+16)==48 && read32(r+20)==0 &&
        memcmp(r+24,q+24,16)==0 &&
        memcmp(r+40,zeros,16)!=0 &&
        read64(r+56)==0 && memcmp(r+64,zeros,16)!=0 &&
        read32(r+80)==4096 && read32(r+84)==0 &&
        read32(r+88)==48 && read32(r+92)==0 && /* HOS2 payload reserved */
        read64(r+96)==2 && read64(r+104)==0;
}
<<<<<<< HEAD
=======
static void space_hex(const unsigned char *space, char out[33]){
    static const char digits[] = "0123456789abcdef";
    for(int i=0;i<16;i++){
        out[2*i]=digits[space[i]>>4];
        out[2*i+1]=digits[space[i]&15];
    }
    out[32]='\0';
}
>>>>>>> origin/main
static int run_exec_epoch_check(const char *fd_text){
    char *end = NULL;
    long parsed = strtol(fd_text, &end, 10);
    if (end == fd_text || *end != '\0' || parsed < 0 || parsed >  INT_MAX) {
        fail("exec_fd_parse"); return 25;
    }
    int fd = (int)parsed;
    unsigned char q[64], r[112];
    prep(q, 12);
    errno = 0;
    if (run_query(fd, q, r, sizeof r) != -1 || errno != ESTALE) {
        fail("exec_old_fd_not_fenced"); return 26;
    }
    puts("HEPTA_EXEC_EPOCH_DENIED");
<<<<<<< HEAD
=======
    const char *old_space = getenv("HEPTA_PREEXEC_SPACE");
    if(old_space==NULL || strlen(old_space)!=32){fail("exec_space_missing");return 34;}
    int reopened=open("/dev/hepta-control",O_RDWR|O_CLOEXEC);
    if(reopened<0){fail("exec_reopen");return 35;}
    prep(q,13);
    if(run_query(reopened,q,r,sizeof r)!=0 || !valid_reply(r,q)){
        fail("exec_new_image_query");close(reopened);return 36;
    }
    char current_space[33];
    space_hex(r+64,current_space);
    close(reopened);
    if(strcmp(old_space,current_space)==0){fail("exec_capspace_reused");return 37;}
    puts("HEPTA_EXEC_CAPSPACE_ROTATED");
>>>>>>> origin/main
    return 0;
}

int main(int argc, char **argv){
    setvbuf(stdout,NULL,_IONBF,0);
    if (argc == 2 && strcmp(argv[1], "--exec-epoch-check") == 0) {
        const char *fd_text = getenv("HEPTA_INHERITED_FD");
        if (fd_text == NULL) { fail("exec_fd_env"); return 27; }
        return run_exec_epoch_check(fd_text);
    }
    int fd=open("/dev/hepta-control",O_RDWR|O_CLOEXEC);
    if(fd<0){fail("open");return 2;}
    unsigned char q[64],a[112],b[112],c[112];
    prep(q,0);
    if(run_query(fd,q,a,sizeof a)!=0||!valid_reply(a,q)){fail("query1");return 3;}
    prep(q,1);
    if(run_query(fd,q,b,sizeof b)!=0||!valid_reply(b,q)){fail("query2");return 4;}
    if(memcmp(a+40,b+40,16)||memcmp(a+64,b+64,16)){fail("stable_identity");return 5;}
    int fd2=open("/dev/hepta-control",O_RDWR|O_CLOEXEC);
    if(fd2<0){fail("second_open");return 6;}
    prep(q,2);
    if(run_query(fd2,q,c,sizeof c)!=0||!valid_reply(c,q)){fail("query3");return 7;}
    /* Multiple opens in one process share the same kernel-issued CapSpace;
     * the fork/exec checks below prove that possession alone does not cross
     * the process lifetime or image-generation boundary. */
    if(memcmp(a+40,c+40,16)!=0||memcmp(a+64,c+64,16)!=0){fail("same_process_session");return 8;}
    q[0]='X';errno=0;
    if(run_query(fd,q,c,sizeof c)!=-1||errno!=EPROTONOSUPPORT){
        fail("invalid_magic_protocol");return 9;
    }
    prep(q,3);u16le(q+4,3);errno=0;
    if(run_query(fd,q,c,sizeof c)!=-1||errno!=EPROTONOSUPPORT){
        fail("unknown_major_protocol");return 12;
    }
    prep(q,4);u16le(q+8,99);errno=0;
    if(run_query(fd,q,c,sizeof c)!=-1||errno!=EOPNOTSUPP){
        fail("unknown_opcode");return 13;
    }
    prep(q,5);errno=0;
    if(run_query(fd,q,c,111)!=-1||errno!=EMSGSIZE){
        fail("short_queryabi_copyout");return 14;
    }
    unsigned char d[128];
    prep(q,6);u16le(q+8,2);u64le(q+40,1);u64le(q+48,1);errno=0;
    if(run_query(fd,q,d,sizeof d)!=-1||errno!=EOPNOTSUPP){
        fail("known_readusage_disabled");return 15;
    }
    unsigned char q_budget[96];
    prep(q,7);memcpy(q_budget,q,64);
    u16le(q_budget+8,3);u32le(q_budget+16,32);u64le(q_budget+24,1);
    memset(q_budget+32,0,8);
    u64le(q_budget+40,1);u64le(q_budget+48,1);
    memset(q_budget+64,0,32);
    u64le(q_budget+64,1);u64le(q_budget+72,100000000);u64le(q_budget+80,1000000);
    errno=0;
    if(run_request(fd,q_budget,sizeof q_budget,d,sizeof d)!=-1||errno!=EOPNOTSUPP){
        fail("known_installbudget_disabled");return 16;
    }
    prep(q,8);u32le(q+16,1);errno=0;
    if(run_query(fd,q,c,sizeof c)!=-1||errno!=EINVAL){
        fail("inconsistent_query_length");return 17;
    }
    prep(q,9);errno=0;
    if(ioctl(fd,HOS_QUERY_IOCTL,NULL)!=-1||errno!=EFAULT){fail("null_transport");return 10;}
    errno=0;
    if(ioctl(fd,0xC0204803U,NULL)!=-1||errno!=ENOTTY){fail("unknown_command");return 11;}
    int dupfd = dup(fd);
    if (dupfd < 0) { fail("dup_fd"); return 18; }
    prep(q,10);
    if (run_query(dupfd,q,c,sizeof c)!=0 || !valid_reply(c,q) ||
        memcmp(a+40,c+40,16)!=0 || memcmp(a+64,c+64,16)!=0) {
        fail("dup_session_mismatch"); return 19;
    }
    close(dupfd);
    /* Exec-epoch isolation MUST be tested on a session which was valid
     * immediately before execve in the SAME process. A parent-opened fd
     * inherited through fork is already rejected by process_start_id with
     * EPERM; that would not exercise the exec-epoch ESTALE path. */
    pid_t exec_child = fork();
    if (exec_child < 0) { fail("exec_fork"); return 30; }
    if (exec_child == 0) {
        /* Open inside the child so the fd binds to this process lifetime.
         * O_CLOEXEC is intentionally absent: the same descriptor survives
         * execve and must then be rejected only by the image-generation fence. */
        int execfd = open("/dev/hepta-control", O_RDWR);
        if (execfd < 0) { fail("exec_child_open"); _exit(28); }
        unsigned char fresh_q[64], fresh_r[112];
        prep(fresh_q, 12);
        if (run_query(execfd, fresh_q, fresh_r, sizeof fresh_r) != 0 ||
            !valid_reply(fresh_r, fresh_q)) {
            fail("exec_child_preimage_not_valid"); _exit(33);
        }
        puts("HEPTA_EXEC_PREIMAGE_QUERYABI_OK");
<<<<<<< HEAD
=======
        char old_space[33];
        space_hex(fresh_r+64,old_space);
        if (setenv("HEPTA_PREEXEC_SPACE", old_space, 1) != 0) {
            fail("exec_space_env_set"); _exit(38);
        }
>>>>>>> origin/main
        char execfd_text[32];
        snprintf(execfd_text, sizeof execfd_text, "%d", execfd);
        if (setenv("HEPTA_INHERITED_FD", execfd_text, 1) != 0) {
            fail("exec_fd_env_set"); _exit(29);
        }
        execl("/bin/hos2-queryabi", "hos2-queryabi", "--exec-epoch-check", NULL);
        fail("execve_probe"); _exit(31);
    }
    int exec_status = 0;
    if (waitpid(exec_child, &exec_status, 0) != exec_child ||
        !WIFEXITED(exec_status) || WEXITSTATUS(exec_status) != 0) {
        fail("exec_epoch_child_error"); return 32;
    }
    pid_t child = fork();
    if (child < 0) { fail("fork_guest"); return 20; }
    if (child == 0) {
        /* The inherited fd is intentionally fenced at the process-start
         * boundary, even while the child still has uid 0. This proves that
         * fd possession after fork is not a CapSpace credential. */
        prep(q, 11);
        errno = 0;
        if (run_query(fd, q, c, sizeof c) != -1 ||
            (errno != EPERM && errno != ESTALE)) {
            fail("fork_inherited_fd_not_fenced"); _exit(24);
        }
        puts("HEPTA_FORK_INHERITED_FD_DENIED");
<<<<<<< HEAD
=======
        /* A freshly opened fd in the child MUST receive a distinct D
         * namespace even if the PID allocator or boot clock later wraps. */
        int childfd=open("/dev/hepta-control",O_RDWR|O_CLOEXEC);
        if(childfd<0){fail("fork_fresh_open");_exit(39);}
        prep(q,14);
        if(run_query(childfd,q,c,sizeof c)!=0 || !valid_reply(c,q) ||
           memcmp(a+40,c+40,16)!=0 || memcmp(a+64,c+64,16)==0){
            fail("fork_fresh_capspace_alias");close(childfd);_exit(40);
        }
        close(childfd);
        puts("HEPTA_FORK_CAPSPACE_DISTINCT");
>>>>>>> origin/main
        if (setuid(65534) != 0) { fail("setuid_guest"); _exit(21); }
        errno = 0;
        int guestfd = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
        if (guestfd >= 0) close(guestfd);
        if (guestfd >= 0 || (errno != EACCES && errno != EPERM)) {
            fail("unprivileged_open_granted"); _exit(22);
        }
        puts("HEPTA_NONROOT_OPEN_DENIED");
        _exit(0);
    }
    int child_status = 0;
    if (waitpid(child, &child_status, 0) != child ||
        !WIFEXITED(child_status) || WEXITSTATUS(child_status) != 0) {
        fail("nonroot_child_error"); return 23;
    }
    puts("HEPTA_DUP_SESSION_STABLE");
    close(fd2);close(fd);
    puts("HEPTA_QUERYABI_OK ops=QueryAbi_only, process_bound_session=yes, denied_invalid=yes");
    return 0;
}
