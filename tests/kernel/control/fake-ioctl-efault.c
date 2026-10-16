#define _GNU_SOURCE
#include <errno.h>
#include <sys/ioctl.h>
// Test-only shim; does not touch devices. The real target must refuse ENOTTY.
int ioctl(int fd, unsigned long request, ...) {
    (void)fd;
    (void)request;
    errno = EFAULT;
    return -1;
}
