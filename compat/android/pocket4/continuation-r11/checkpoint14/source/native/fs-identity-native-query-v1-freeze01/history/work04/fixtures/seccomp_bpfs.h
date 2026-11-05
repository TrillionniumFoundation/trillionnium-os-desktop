// Explicit, small generated-table fixtures, not the full Android allowlists.
// Both preimage and candidate use these exact same fixture bytes. Native and
// compat public setters, old16 compat setters and x32 are deliberately denied
// so kernel negative controls cannot pass via an untested default-ALLOW path.
#pragma once
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <stddef.h>
#define FIXTURE_POLICY(name, fsuid, fsgid, olduid, oldgid, special) \
    inline constexpr sock_filter name[] = { \
        BPF_JUMP(BPF_JMP | BPF_JGE | BPF_K, 0x40000000U, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_TRAP), \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, fsuid, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_TRAP), \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, fsgid, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_TRAP), \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, olduid, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_TRAP), \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, oldgid, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_TRAP), \
        BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, special, 0, 1), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ERRNO | 13), \
        BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW), \
    }; \
    inline constexpr size_t name##_size = sizeof(name) / sizeof(name[0]);
FIXTURE_POLICY(x86_64_app_filter, 122, 123, 0xffffffffU, 0xffffffffU, 4000)
FIXTURE_POLICY(x86_64_app_zygote_filter, 122, 123, 0xffffffffU, 0xffffffffU, 4001)
FIXTURE_POLICY(x86_64_system_filter, 122, 123, 0xffffffffU, 0xffffffffU, 4002)
FIXTURE_POLICY(x86_app_filter, 215, 216, 138, 139, 4000)
FIXTURE_POLICY(x86_app_zygote_filter, 215, 216, 138, 139, 4001)
FIXTURE_POLICY(x86_system_filter, 215, 216, 138, 139, 4002)
#undef FIXTURE_POLICY
