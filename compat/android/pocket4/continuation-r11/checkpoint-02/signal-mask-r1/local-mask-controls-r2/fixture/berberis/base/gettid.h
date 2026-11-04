
#pragma once
#include <sys/syscall.h>
#include <unistd.h>
namespace berberis {
inline pid_t GetpidSyscall() { return syscall(SYS_getpid); }
inline pid_t GettidSyscall() { return syscall(SYS_gettid); }
}
