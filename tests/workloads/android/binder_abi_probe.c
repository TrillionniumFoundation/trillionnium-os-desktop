// SPDX-License-Identifier: MIT
// A08 minimal, read-only protocol gate for Linux Binder UAPI.
// This is NOT a full Binder compatibility test: no transactions, death notices,
// security contexts, FD forwarding or cross-domain lifetime are exercised.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/android/binder.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

static int report(const char *gate, const char *status, int err) {
    printf("%s\t%s\terrno=%d\n",gate,status,err);
    return strcmp(status,"PASS") == 0 ? 0 : 1;
}
int main(void) {
    printf("# binder_abi_probe uapi_expected=%d type=%zu\n",
           BINDER_CURRENT_PROTOCOL_VERSION,sizeof(struct binder_write_read));
    int fd=open("/dev/binder",O_RDWR|O_CLOEXEC);
    if(fd<0) {
        report("binder_device_open","BLOCKED",errno);
        return 77; // POSIX/autoconf-style skip; gate remains BLOCKED
    }
    struct binder_version version={0};
    if(ioctl(fd,BINDER_VERSION,&version)<0) {
        report("binder_protocol_version","FAIL",errno);close(fd);return 1;
    }
    if(version.protocol_version!=BINDER_CURRENT_PROTOCOL_VERSION) {
        printf("binder_protocol_version\tFAIL\tgot=%d expected=%d\n",
               version.protocol_version,BINDER_CURRENT_PROTOCOL_VERSION);
        close(fd);return 1;
    }
    report("binder_protocol_version","PASS",0);
    unsigned int threads=2;
    if(ioctl(fd,BINDER_SET_MAX_THREADS,&threads)<0) {
        report("binder_set_max_threads","FAIL",errno);close(fd);return 1;
    }
    report("binder_set_max_threads","PASS",0);
    // Standard userspace Binder virtual memory mapping, never device MMIO.
    const size_t bytes=1024u*1024u;
    void *ptr=mmap(NULL,bytes,PROT_READ,MAP_PRIVATE|MAP_NORESERVE,fd,0);
    if(ptr==MAP_FAILED) {
        report("binder_mmap","FAIL",errno);close(fd);return 1;
    }
    report("binder_mmap","PASS",0);
    struct binder_write_read bwr={0};
    if(ioctl(fd,BINDER_WRITE_READ,&bwr)<0) {
        report("binder_empty_write_read","FAIL",errno);
        munmap(ptr,bytes);close(fd);return 1;
    }
    report("binder_empty_write_read","PASS",0);
    munmap(ptr,bytes);close(fd);
    puts("binder_transactions\tNOT_TESTED\terrno=0");
    puts("binder_identity_death_fd_MAC\tNOT_TESTED\terrno=0");
    return 0;
}
