// A05 independent Linux ELF HOS2 QueryAbi consumer, not a kernel driver.
// The experimental ioctl request number is deliberately NOT invented here.
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#if !defined(__linux__) || !defined(__x86_64__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "HOS2 N0 probe requires Linux x86_64 little-endian"
#endif
_Static_assert(sizeof(uintptr_t) == 8, "HOS2 transport requires 64-bit user pointers");

enum { HEADER = 64, QUERY_RESPONSE = 112, TRANSPORT = 32 };
static const uint8_t request_id[16] = {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16};
static void w16(uint8_t *p, uint16_t n) {p[0]=(uint8_t)n; p[1]=(uint8_t)(n>>8);}
static void w32(uint8_t *p, uint32_t n) {for(int i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
static void w64(uint8_t *p, uint64_t n) {for(int i=0;i<8;i++)p[i]=(uint8_t)(n>>(8*i));}
static uint16_t r16(const uint8_t *p) {return (uint16_t)p[0]|((uint16_t)p[1]<<8);}
static uint32_t r32(const uint8_t *p) {return (uint32_t)r16(p)|((uint32_t)r16(p+2)<<16);}
static uint64_t r64(const uint8_t *p) {return (uint64_t)r32(p)|((uint64_t)r32(p+4)<<32);}
static int any16(const uint8_t *p) {for(int i=0;i<16;i++)if(p[i])return 1;return 0;}

static void query(uint8_t request[HEADER]) {
    memset(request,0,HEADER);
    memcpy(request,"HOS2",4);
    w16(request+4,2); w16(request+8,1); w32(request+12,HEADER);
    memcpy(request+24,request_id,16);
}

// Strictly validates the 64-byte HOSR header plus the exact QueryAbi body.
// Never casts wire bytes to an in-memory packed C/Rust structure.
static int check_query(const uint8_t *p, size_t len) {
    if(len!=QUERY_RESPONSE || memcmp(p,"HOSR",4) || r16(p+4)!=2 || r16(p+6)!=0 ||
       r16(p+8)!=1 || r16(p+10)!=0 || r32(p+12)!=HEADER || r32(p+16)!=48 ||
       r32(p+20)!=0 || memcmp(p+24,request_id,16) || !any16(p+40) || r64(p+56)!=0)
        return -1;
    const uint8_t *body=p+HEADER;
    uint32_t page=r32(body+16), maxreq=r32(body+20), maxresp=r32(body+24);
    uint64_t ops=r64(body+32);
    if(!any16(body) || !page || (page&(page-1)) || r32(body+28) ||
       r64(body+40) || (ops&~UINT64_C(62)) || !(ops&2) ||
       ((ops&8) && ((ops&(4|16|32))!=(4|16|32))) ||
       ((ops&32) && !(ops&16)) || maxreq>65536 || maxresp>65536 ||
       ((ops&(8|16|32)) && maxreq<40) || maxresp<48 ||
       ((ops&(4|16)) && maxresp<64)) return -1;
    return 0;
}

static int selftest(void) {
    uint8_t req[HEADER], resp[QUERY_RESPONSE];
    query(req);
    if(memcmp(req,"HOS2",4) || r32(req+12)!=64 || r16(req+8)!=1 ||
       memcmp(req+24,request_id,16)) return 1;
    memset(resp,0,sizeof(resp)); memcpy(resp,"HOSR",4);
    w16(resp+4,2);w16(resp+8,1);w32(resp+12,64);w32(resp+16,48);
    memcpy(resp+24,request_id,16);memset(resp+40,0x33,16);
    memset(resp+64,0x22,16);w32(resp+80,4096);w32(resp+84,65536);
    w32(resp+88,65536);w64(resp+96,62);
    if(check_query(resp,sizeof(resp))) return 2;
    const struct {size_t off; uint8_t xor_byte;} flips[] = {
      {0,1},{4,1},{8,1},{10,1},{12,1},{16,1},{20,1},
      {24,1},{56,1},{80,1},{92,1},{104,1}
    };
    for(size_t i=0;i<sizeof(flips)/sizeof(flips[0]);i++) {
        uint8_t copy[QUERY_RESPONSE];memcpy(copy,resp,sizeof(copy));
        copy[flips[i].off]^=flips[i].xor_byte;
        if(!check_query(copy,sizeof(copy))) {
            fprintf(stderr,"mutation at offset %zu escaped validation\n",flips[i].off);
            return 3;
        }
    }
    uint8_t mutated[QUERY_RESPONSE];memcpy(mutated,resp,sizeof(mutated));
    memset(mutated+40,0,16);
    if(!check_query(mutated,sizeof(mutated)))return 4;
    memcpy(mutated,resp,sizeof(mutated));memset(mutated+64,0,16);
    if(!check_query(mutated,sizeof(mutated)))return 4;
    memcpy(mutated,resp,sizeof(mutated));
    w64(mutated+96,2|32); // RetireThrough without QueryDelivery is illegal.
    if(!check_query(mutated,sizeof(mutated)))return 4;
    if(!check_query(resp,sizeof(resp)-1))return 5;
    puts("PASS HOS2 QueryAbi transport/header/response + 16 invalid frames (host only)");
    return 0;
}

int main(int argc, char **argv) {
    if(argc==2 && !strcmp(argv[1],"--selftest"))return selftest();
    if(argc!=5 || strcmp(argv[1],"--device") || strcmp(argv[3],"--ioctl-cmd")) {
        fprintf(stderr,"usage: %s --selftest | --device PATH --ioctl-cmd HEX\n",argv[0]);
        return 64;
    }
    char *end=NULL;
    errno=0;unsigned long number=strtoul(argv[4],&end,0);
    if(errno || !end || *end || number>UINT32_MAX || number==0) {
        fputs("ioctl command must be the separately assigned nonzero HOS2 value\n",stderr);
        return 64;
    }
    uint8_t req[HEADER],resp[QUERY_RESPONSE],desc[TRANSPORT];
    query(req);memset(resp,0,sizeof(resp));memset(desc,0,sizeof(desc));
    w64(desc,(uint64_t)(uintptr_t)req);w64(desc+8,(uint64_t)(uintptr_t)resp);
    w32(desc+16,sizeof(req));w32(desc+20,sizeof(resp));
    int fd=open(argv[2],O_RDONLY|O_CLOEXEC);
    if(fd<0){perror("HOS2 device unavailable");return 77;}
    int rc=ioctl(fd,number,desc),saved_errno=errno;
    close(fd);
    if(rc!=0){
        // A transport fault (EFAULT, EBADF, EPERM, etc.) is not proof that
        // /dev/null rejected an unsupported ioctl with ENOTTY. Preserve the
        // old generic exit code for callers, but emit an unambiguous marker
        // only for the actual ENOTTY classification used by the host smoke.
        if(rc==-1 && saved_errno==ENOTTY)
            fputs("HOS2_IOCTL_ENOTTY\n",stderr);
        else
            fprintf(stderr,"HOS2_IOCTL_OTHER_ERROR rc=%d errno=%d\n",rc,saved_errno);
        errno=saved_errno;
        perror("HOS2 QueryAbi ioctl failed");
        return 77;
    }
    if(check_query(resp,sizeof(resp))){fputs("invalid HOS2 QueryAbi response\n",stderr);return 2;}
    printf("PASS actual HOS2 QueryAbi: page=%" PRIu32 ", supported_ops=0x%" PRIx64 "\n",
           r32(resp+HEADER+16),r64(resp+HEADER+32));
    return 0;
}
