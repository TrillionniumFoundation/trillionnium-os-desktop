/* Test only: successful real closes deliberately overwrite errno. Production
 * must preserve the first failure before closing its owned descriptors. */
#define _GNU_SOURCE
#include <errno.h>
#include <unistd.h>
static int dir_test_close_overwrites_errno(int fd) {
  int result=close(fd);errno=EBADF;return result;
}
#define close dir_test_close_overwrites_errno
