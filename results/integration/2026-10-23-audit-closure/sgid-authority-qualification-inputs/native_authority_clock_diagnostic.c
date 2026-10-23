#define _GNU_SOURCE
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

struct sample { uint64_t before, wall, after; };
static uint64_t read_ns(clockid_t id, int direct)
{
    struct timespec t;
    int rc=direct?(int)syscall(SYS_clock_gettime,id,&t):clock_gettime(id,&t);
    if(rc || t.tv_sec<0 || t.tv_nsec<0 || t.tv_nsec>=1000000000)exit(2);
    return (uint64_t)t.tv_sec*1000000000u+(uint64_t)t.tv_nsec;
}
static struct sample sample(int direct)
{
    struct sample s;
    s.before=read_ns(CLOCK_BOOTTIME,direct);
    s.wall=read_ns(CLOCK_REALTIME,direct);
    s.after=read_ns(CLOCK_BOOTTIME,direct);
    return s;
}
int main(int argc,char **argv)
{
    if(argc!=2 || mkdir(argv[1],0700))return 2;
    int dir=open(argv[1],O_RDONLY|O_DIRECTORY|O_CLOEXEC);
    if(dir<0)return 2;
    for(int direct=0;direct<2;direct++)for(int i=0;i<8;i++){
        struct sample first=sample(direct);
        int fd=openat(dir,"new",O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);
        if(fd<0 || write(fd,"clock-diagnostic",16)!=16 || fsync(fd) || close(fd) || renameat(dir,"new",dir,"head") || fsync(dir))return 2;
        struct sample next=sample(direct);
        uint64_t elapsed=next.after-first.before;
        int64_t ahead=(int64_t)(next.wall-first.wall)-(int64_t)elapsed;
        printf("CLOCK_DIAGNOSTIC direct=%d case=%d io_ns=%" PRIu64 " sample_ns=%" PRIu64 " wall_ahead_ns=%" PRId64 " original_horizon_ok=%d original_projection_ok=%d\n",direct,i,elapsed,next.after-next.before,ahead,elapsed<=1000000000u,ahead<=0);
        fflush(stdout);
    }
    close(dir);
    puts("CLOCK_DIAGNOSTIC_COMPLETE cases=16 qualification=0");
    return 0;
}
