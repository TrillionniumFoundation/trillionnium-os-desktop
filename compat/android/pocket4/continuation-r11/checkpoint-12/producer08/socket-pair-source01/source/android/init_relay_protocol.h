/* Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0 */
#ifndef DROIDLOOM_INIT_RELAY_PROTOCOL_H
#define DROIDLOOM_INIT_RELAY_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
#define DIR_WIRE_SIZE 128u
#define DIR_HELLO_RIGHTS 12u
#define DIR_MAX_RIGHTS 16u
#define DIR_HELLO 1u
#define DIR_PROJECT 2u
#define DIR_PROJECTED 3u
#define DIR_COMMIT 4u
#define DIR_DONE 5u
/* ABI 2 PROJECT carries a detached mount from the verified source namespace.
 * It is attached exactly once by move_mount onto the init-owned held target. */
#define DIR_ABI 2u
#define DIR_ABI_TEXT "2"
#define DIR_SOCKET_NAME "droidloom-lmkd-psi"
#define DIR_ABI_ENV "DROIDLOOM_INIT_RELAY_ABI"
#define DIR_REQUIRED_ENV "DROIDLOOM_INIT_RELAY_REQUIRED"
#define DIR_FD_ENV "DROIDLOOM_INIT_RELAY_FD"
#define DIR_NONCE_ENV "DROIDLOOM_INIT_RELAY_NONCE"
#define DIR_TIMEOUT_ENV "DROIDLOOM_INIT_RELAY_TIMEOUT_MS"
#define DIR_LIBRARY_PATH "/droidloom/lmkd-bootstrap/libdroidloom_init_relay.so"
struct dir_context {
  int control, peer_pidfd;
  uint64_t deadline, last_clock;
  unsigned char nonce[32];
};
struct dir_operations {
  int (*collect)(int rights[DIR_HELLO_RIGHTS], unsigned char hello[DIR_WIRE_SIZE], void *opaque);
  int (*project)(int socket_fd, const unsigned char ready[DIR_WIRE_SIZE], void *opaque);
  int (*finish)(void *opaque);
  void *opaque;
};
#endif
