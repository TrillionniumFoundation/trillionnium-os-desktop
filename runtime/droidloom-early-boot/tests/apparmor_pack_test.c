// SPDX-License-Identifier: GPL-3.0-or-later
#include "board_policy.c"
#include <assert.h>

static void put32(unsigned char *p, uint32_t value)
{
    for (size_t i = 0; i < 4; ++i) p[i] = (unsigned char)(value >> (i * 8));
}

static void denied(unsigned char *data, size_t size)
{
    struct input pack = {.data = data, .size = size};
    struct droidloom_raw_profile selected[4] = {0};
    errno = 0;
    assert(apparmor_profiles(&pack, 0, selected) == -1);
    assert(errno == EBADMSG);
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    FILE *source = fopen(argv[1], "rb");
    assert(source && fseek(source, 0, SEEK_END) == 0);
    long extent = ftell(source);
    assert(extent > 12 && extent < 64 * 1024 * 1024);
    assert(fseek(source, 0, SEEK_SET) == 0);
    size_t size = (size_t)extent;
    unsigned char *body = malloc(size + 1), *bad = malloc(size + 1);
    assert(body && bad && fread(body, 1, size, source) == size);
    assert(fclose(source) == 0);
    struct input pack = {.data = body, .size = size};
    struct droidloom_raw_profile selected[4] = {0};
    assert(apparmor_profiles(&pack, 0, selected) == 0);
    const char *wanted[4] = {
        "droidloom-policy-loader", "droidloom-production-android", "droidloom-production-broker", "droidloom-camera-capture"
    };
    for (size_t i = 0; i < 4; ++i) {
        size_t match = DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES;
        for (size_t j = 0; j < DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES; ++j)
            if (!strcmp(wanted[i], droidloom_board_apparmor_profiles[j].name)) match = j;
        assert(match < DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES && selected[i].data);
        assert(apparmor_profile_bytes(selected[i].data, selected[i].size,
                                      &droidloom_board_apparmor_profiles[match]) == 0);
    }
    size_t offset[DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES], length[DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES];
    size_t pos = 12;
    for (size_t i = 0; i < DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES; ++i) {
        offset[i] = pos;
        length[i] = 4 + le32(body + pos);
        pos += length[i];
    }
    assert(pos == size);
    unsigned negative = 0;
    memcpy(bad, body, size); put32(bad + 8, DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES - 1);
    denied(bad, size); ++negative;
    memcpy(bad, body, size); put32(bad + 8, DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES + 1);
    denied(bad, size); ++negative;
    memcpy(bad, body, size); bad[0] ^= 1; denied(bad, size); ++negative;
    denied(body, 11); ++negative;
    denied(body, size - 1); ++negative;
    memcpy(bad, body, size); bad[size] = 0; denied(bad, size + 1); ++negative;
    memcpy(bad, body, size); put32(bad + 12, 0); denied(bad, size); ++negative;
    memcpy(bad, body, size); put32(bad + 12, UINT32_MAX); denied(bad, size); ++negative;
    for (size_t i = 0; i < DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES; ++i) {
        memcpy(bad, body, size);
        bad[offset[DROIDLOOM_BOARD_APPARMOR_UBUNTU_ENTRIES + i] + 4] ^= 1;
        denied(bad, size); ++negative;
    }
    // Reordering complete, individually valid records must not move identity slots.
    memcpy(bad, body, 12); pos = 12;
    for (size_t i = 0; i < DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES; ++i) {
        size_t from = i;
        if (i == DROIDLOOM_BOARD_APPARMOR_EPOCH_LOADER_INDEX) from = DROIDLOOM_BOARD_APPARMOR_EPOCH_BROKER_INDEX;
        else if (i == DROIDLOOM_BOARD_APPARMOR_EPOCH_BROKER_INDEX) from = DROIDLOOM_BOARD_APPARMOR_EPOCH_LOADER_INDEX;
        memcpy(bad + pos, body + offset[from], length[from]); pos += length[from];
    }
    assert(pos == size); denied(bad, size); ++negative;
    printf("real archive: %u entries, %u board digests, 3 original epoch roles plus independent camera; %u malformed inputs rejected\n",
           DROIDLOOM_BOARD_APPARMOR_PROFILE_ENTRIES, DROIDLOOM_BOARD_APPARMOR_BOARD_ENTRIES, negative);
    free(body); free(bad);
    return 0;
}
