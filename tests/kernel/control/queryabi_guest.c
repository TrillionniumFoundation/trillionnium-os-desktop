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
        r[8]==1 && r[9]==0 && r[10]==0 && r[11]==0 &&
        read32(r+12)==64 && read32(r+16)==48 &&
        memcmp(r+24,q+24,16)==0 &&
        memcmp(r+40,zeros,16)!=0 &&
        read64(r+56)==0 && memcmp(r+64,zeros,16)!=0 &&
        read32(r+80)==4096 && read32(r+84)==0 &&
        read32(r+88)==48 && read64(r+96)==2 && read64(r+104)==0;
}
int main(void){
    setvbuf(stdout,NULL,_IONBF,0);
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
    if(memcmp(a+40,c+40,16)!=0||memcmp(a+64,c+64,16)==0){fail("space_isolation");return 8;}
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
    u16le(q_budget+8,3);u64le(q_budget+24,1);
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
    close(fd2);close(fd);
    puts("HEPTA_QUERYABI_OK ops=QueryAbi_only, independent_sessions=yes, denied_invalid=yes");
    return 0;
}
