// Explicit, small generated-table fixtures. They block both FS setters, leave
// unrelated syscall decisions observable, and allow safe owned-child plumbing.
// These are not the device's full stock allowlists.
#pragma once
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#define FIXTURE_POLICY(name, fsuid, fsgid, special) \
    inline constexpr sock_filter name[] = { \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, fsuid, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_TRAP), \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, fsgid, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_TRAP), \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, special, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | 13), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW), \
    }; \
    inline constexpr size_t name##_size = sizeof(name) / sizeof(name[0]);
FIXTURE_POLICY(x86_64_app_filter, 122, 123, 4000)
FIXTURE_POLICY(x86_64_app_zygote_filter, 122, 123, 4001)
FIXTURE_POLICY(x86_64_system_filter, 122, 123, 4002)
FIXTURE_POLICY(x86_app_filter, 215, 216, 4000)
FIXTURE_POLICY(x86_app_zygote_filter, 215, 216, 4001)
FIXTURE_POLICY(x86_system_filter, 215, 216, 4002)
#undef FIXTURE_POLICY
