/* Real disposable-guest regression; retain the original A05 probe verbatim. */
#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* The original probe uses unbuffered stdout. libc puts may write its text and
 * newline separately, allowing the kernel's syscall trace between them. Keep
 * exact-line evidence by submitting each marker and newline in one syscall. */
static int candidate_puts(const char *text) {
    char line[256];
    size_t length = strnlen(text, sizeof line - 1);
    if (length == sizeof line - 1) { _exit(90); }
    memcpy(line, text, length);
    line[length] = '\n';
    ssize_t written;
    do {
        written = write(STDOUT_FILENO, line, length + 1);
    } while (written < 0 && errno == EINTR);
    if (written != (ssize_t)(length + 1)) { _exit(91); }
    return 0;
}

#define puts candidate_puts
#define main original_queryabi_main
#include "queryabi_guest.c"
#undef main
#undef puts

static int check_disabled_operations(void) {
    static const char *const markers[] = {
        "HEPTA_DISABLED_READ_USAGE_OK",
        "HEPTA_DISABLED_INSTALL_BUDGET_OK",
        "HEPTA_DISABLED_QUERY_DELIVERY_OK",
        "HEPTA_DISABLED_RETIRE_THROUGH_OK",
    };
    int fd = open("/dev/hepta-control", O_RDWR | O_CLOEXEC);
    unsigned char query[64], abi[112];
    if (fd < 0) { fail("candidate_open"); return 41; }
    prep(query, 40);
    if (run_query(fd, query, abi, sizeof abi) != 0 || !valid_reply(abi, query)) {
        fail("candidate_queryabi_only"); close(fd); return 42;
    }
    for (unsigned int opcode = 2; opcode <= 5; ++opcode) {
        unsigned char request[104] = {0}, response[128];
        unsigned int length = 64;
        prep(request, (int)(40 + opcode));
        u16le(request + 8, (uint16_t)opcode);
        u64le(request + 40, 1); /* nonzero target slot */
        u64le(request + 48, 1); /* nonzero target generation */
        if (opcode == 3) {
            length = 96;
            u32le(request + 16, 32);
            memset(request + 24, 0, 16);
            u64le(request + 24, 1); /* canonical InstallBudget sequence ID */
            u64le(request + 64, 1); /* expected revision */
            u64le(request + 72, 100000000); /* period ns */
            u64le(request + 80, 1000000); /* cap ns; reserved tail stays zero */
        } else if (opcode >= 4) {
            length = 104;
            u32le(request + 16, 40);
            memcpy(request + 64, abi + 40, 16); /* real returned boot identity */
            memcpy(request + 80, abi + 64, 16); /* real returned space identity */
            u64le(request + 96, 1); /* nonzero historical sequence */
        }
        errno = 0;
        if (run_request(fd, request, length, response, sizeof response) != -1 ||
            errno != EOPNOTSUPP) {
            fail(markers[opcode - 2]); close(fd); return (int)(43 + opcode);
        }
        candidate_puts(markers[opcode - 2]);
    }
    close(fd);
    candidate_puts("HEPTA_QUERYABI_CANDIDATE_OK disabled_operations=4");
    return 0;
}

int main(int argc, char **argv) {
    int result = original_queryabi_main(argc, argv);
    /* The exec child must finish only its original epoch check. */
    if (result != 0 ||
        (argc == 2 && strcmp(argv[1], "--exec-epoch-check") == 0)) {
        return result;
    }
    return check_disabled_operations();
}
