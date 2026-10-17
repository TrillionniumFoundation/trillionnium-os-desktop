/* Linux-host-only test of the actual guest reply checker; NO kernel ioctl. */
#define main hepta_queryabi_guest_entry_never_run
#include "queryabi_guest.c"
#undef main

static int checked;
static void expect(const char *label, int cond) {
    if (!cond) {
        fprintf(stderr, "QUERYABI_REPLY_CONTRACT_FAIL %s\n", label);
        _exit(1);
    }
    checked++;
}
int main(void) {
    unsigned char request[64], reply[112], mutated[112];
    prep(request, 0);
    memset(reply, 0, sizeof(reply));
    memcpy(reply, "HOSR", 4);
    reply[4] = 2;
    u16le(reply + 8, 1);
    u32le(reply + 12, 64);
    u32le(reply + 16, 48);
    memcpy(reply + 24, request + 24, 16);
    reply[40] = 0x11; /* stable nonzero boot ID */
    reply[64] = 0x22; /* nonzero per-open observation space */
    u32le(reply + 80, 4096);
    u32le(reply + 88, 48);
    u64le(reply + 96, 1ULL << 1); /* QueryAbi is the only supported op */

    expect("valid_response", valid_reply(reply, request));

    /* The original guest accepted all of these invalid version/reserved
     * bytes, so a guest-only QEMU report could give a false OK. */
    const size_t mandatory_zero[] = {6, 7, 20, 21, 22, 23, 92, 93, 94, 95};
    for (size_t i = 0; i < sizeof(mandatory_zero)/sizeof(mandatory_zero[0]); i++) {
        memcpy(mutated, reply, sizeof(mutated));
        mutated[mandatory_zero[i]] = 0xa5;
        expect("minor_or_reserved_nonzero", !valid_reply(mutated, request));
    }

    /* Existing checks remain active after the hardening. */
    const size_t existing_fields[] = {0, 8, 10, 24, 40, 64, 80, 84, 88, 96, 104};
    for (size_t i = 0; i < sizeof(existing_fields)/sizeof(existing_fields[0]); i++) {
        memcpy(mutated, reply, sizeof(mutated));
        /* Boot and per-open space IDs are intentionally opaque: the guest
         * verifies nonzero here, and compares stability across opens above.
         * Corrupt those identities to ZERO rather than another valid ID. */
        if (existing_fields[i] == 40 || existing_fields[i] == 64) {
            mutated[existing_fields[i]] = 0;
        } else {
            mutated[existing_fields[i]] ^= 0x7f;
        }
        expect("other_field_corruption", !valid_reply(mutated, request));
    }

    puts("PASS QueryAbi guest verifier: valid frame + 21 invalid mutations rejected (Linux host only)");
    return checked == 22 ? 0 : 1;
}
