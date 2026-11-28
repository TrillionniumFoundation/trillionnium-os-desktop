// SPDX-License-Identifier: GPL-3.0-or-later
// Exercise the actual fixed packet/status parser; never load a policy or VM.
#include "board_policy.c"
#include <assert.h>

static unsigned checks;
static void result(const unsigned char *text, size_t size, const uint32_t status[5], int okay)
{
    assert((epoch_packet(text, size, status) == 0) == okay);
    ++checks;
}
int main(void)
{
    const uint32_t current[5] = {1, 8, 1, 1, 1};
    unsigned char packet[1024], changed[1024];
    int n = snprintf((char *)packet, sizeof(packet),
        "DLAAREV3\n00000000-0000-0000-0000-000000000000 174 1 2 3\n"
        "loader witness\nandroid witness\nbroker witness\nSELINUX1 %s 8 1 1\n",
        DROIDLOOM_BOARD_SELINUX_SHA256);
    assert(n > 128 && (size_t)n < sizeof(packet));
    size_t size = (size_t)n;
    result(packet, size, current, 1);
    for (size_t i = 0; i < 5; i++) {
        uint32_t state[5];
        memcpy(state, current, sizeof(state));
        state[i] = i == 1 ? 10 : 0;
        result(packet, size, state, 0);
    }
    uint32_t odd[5] = {1, 9, 1, 1, 1};
    result(packet, size, odd, 0);
    uint32_t second[5] = {1, 8, 1, 2, 1};
    result(packet, size, second, 0);
    memcpy(changed, packet, size);
    changed[2] = 'X'; result(changed, size, current, 0);
    memcpy(changed, packet, size);
    changed[20] = 0; result(changed, size, current, 0);
    memcpy(changed, packet, size);
    changed[size - 3] = '0'; result(changed, size, current, 0);
    memcpy(changed, packet, size);
    unsigned char *digest = (unsigned char *)strstr((char *)packet, "SELINUX1 ") + 9;
    changed[(size_t)(digest - packet)] = digest[0] == 'a' ? 'b' : 'a';
    result(changed, size, current, 0);
    memcpy(changed, packet, size);
    changed[size] = '\n'; result(changed, size + 1, current, 0);
    memcpy(changed, packet, size);
    changed[size] = 'x'; result(changed, size + 1, current, 0);
    result(packet, size - 1, current, 0);
    result(packet, sizeof("DLAAREV3\n") - 1, current, 0);
    struct stat before = {.st_dev = 1, .st_ino = 2, .st_mode = S_IFREG | 0400,
        .st_uid = 0, .st_gid = 0, .st_nlink = 1, .st_size = (off_t)size};
    struct stat after = before;
    after.st_atim.tv_nsec = 1; assert(epoch_same(&before, &after)); ++checks;
    after.st_ctim.tv_nsec = 1; assert(!epoch_same(&before, &after)); ++checks;
    after = before; after.st_ino++; assert(!epoch_same(&before, &after)); ++checks;
    after = before; after.st_mode |= 0200; assert(!epoch_same(&before, &after)); ++checks;
    after = before; after.st_nlink++; assert(!epoch_same(&before, &after)); ++checks;
    assert(checks == 21);
    printf("{\"fixed_epoch_parser_checks\":%u,\"runtime_qualified\":false}\n", checks);
    return 0;
}
