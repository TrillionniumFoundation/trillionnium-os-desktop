// SPDX-License-Identifier: Apache-2.0
// x86_64 Linux Binder UAPI layout baseline. No device open, no transactions.
// Compile this source in the AOSP toolchain separately before claiming an
// Android-to-Asterinas ABI. Host Linux headers alone are NOT target proof.
#include <linux/android/binder.h>
#include <linux/ioctl.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#if !defined(__x86_64__) || __SIZEOF_POINTER__ != 8
#error A08 layout probe targets x86_64 LP64 only
#endif

_Static_assert(BINDER_CURRENT_PROTOCOL_VERSION == 8, "64-bit Binder protocol must be v8");
_Static_assert(sizeof(binder_size_t) == 8, "binder_size_t must be u64");
_Static_assert(sizeof(binder_uintptr_t) == 8, "binder_uintptr_t must be u64");
_Static_assert(sizeof(struct binder_write_read) == 48, "write/read size");
_Static_assert(offsetof(struct binder_write_read, write_size) == 0, "write_size offset");
_Static_assert(offsetof(struct binder_write_read, write_consumed) == 8, "write_consumed offset");
_Static_assert(offsetof(struct binder_write_read, write_buffer) == 16, "write_buffer offset");
_Static_assert(offsetof(struct binder_write_read, read_size) == 24, "read_size offset");
_Static_assert(offsetof(struct binder_write_read, read_consumed) == 32, "read_consumed offset");
_Static_assert(offsetof(struct binder_write_read, read_buffer) == 40, "read_buffer offset");
_Static_assert(sizeof(struct binder_version) == 4, "version size");
_Static_assert(sizeof(struct binder_transaction_data) == 64, "transaction size");
_Static_assert(offsetof(struct binder_transaction_data, sender_euid) == 28, "UID offset");
_Static_assert(offsetof(struct binder_transaction_data, data_size) == 32, "data_size offset");
_Static_assert(offsetof(struct binder_transaction_data, offsets_size) == 40, "offsets_size offset");
_Static_assert(offsetof(struct binder_transaction_data, data) == 48, "data payload offset");
_Static_assert(sizeof(struct binder_transaction_data_secctx) == 72, "secctx transaction size");
_Static_assert(sizeof(struct binder_transaction_data_sg) == 72, "scatter/gather transaction size");
_Static_assert(sizeof(struct flat_binder_object) == 24, "flat Binder object size");
_Static_assert(sizeof(struct binder_handle_cookie) == 12, "packed handle cookie size");
_Static_assert(BINDER_WRITE_READ == 0xc0306201UL, "BINDER_WRITE_READ ioctl");
_Static_assert(BINDER_VERSION == 0xc0046209UL, "BINDER_VERSION ioctl");
_Static_assert(BINDER_SET_MAX_THREADS == 0x40046205UL, "BINDER_SET_MAX_THREADS ioctl");
_Static_assert(BINDER_SET_CONTEXT_MGR_EXT == 0x4018620dUL, "context manager ioctl");
_Static_assert(BC_TRANSACTION == 0x40406300UL, "BC_TRANSACTION opcode");
_Static_assert(BR_TRANSACTION == 0x80407202UL, "BR_TRANSACTION opcode");

int main(void) {
    // A host static ABI proof only. Never emit runtime-compatible or Binder PASS.
    printf("{\"schema\":1,\"scope\":\"host_linux_uapi_layout_only\","
           "\"arch\":\"x86_64_lp64\",\"protocol_version\":%d,"
           "\"write_read_size\":%zu,\"transaction_size\":%zu,"
           "\"transaction_secctx_size\":%zu,\"flat_object_size\":%zu,"
           "\"handle_cookie_size\":%zu,\"sender_uid_offset\":%zu,"
           "\"ioctls\":{\"BINDER_WRITE_READ\":%lu,\"BINDER_VERSION\":%lu,"
           "\"BINDER_SET_MAX_THREADS\":%lu,\"BINDER_SET_CONTEXT_MGR_EXT\":%lu},"
           "\"binder_driver_verified\":false,\"android_asterinas_verified\":false}\n",
           BINDER_CURRENT_PROTOCOL_VERSION,
           sizeof(struct binder_write_read), sizeof(struct binder_transaction_data),
           sizeof(struct binder_transaction_data_secctx), sizeof(struct flat_binder_object),
           sizeof(struct binder_handle_cookie),
           offsetof(struct binder_transaction_data, sender_euid),
           (unsigned long)BINDER_WRITE_READ, (unsigned long)BINDER_VERSION,
           (unsigned long)BINDER_SET_MAX_THREADS, (unsigned long)BINDER_SET_CONTEXT_MGR_EXT);
    return 0;
}
