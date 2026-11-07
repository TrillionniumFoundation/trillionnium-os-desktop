// Owned local kernel controls for the constructor's explicit table fixtures.
// No Android policy, role, app, namespace or system service is changed.
#include <sys/prctl.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <signal.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <time.h>
#include <cstdio>
#include <cstdlib>
#include <vector>

struct Record { int setup; long before; long observed; long after; int error; };
static int64_t Now() {
    timespec value{};
    if (clock_gettime(CLOCK_MONOTONIC, &value) != 0) std::abort();
    return int64_t{value.tv_sec} * 1000 + value.tv_nsec / 1000000;
}
static std::vector<sock_filter> Load(const char* path) {
    const int fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) std::abort();
    uint32_t count = 0;
    if (read(fd, &count, sizeof(count)) != sizeof(count) || count == 0 || count > 4096)
        std::abort();
    std::vector<sock_filter> result(count);
    const size_t bytes = result.size() * sizeof(result[0]);
    if (read(fd, result.data(), bytes) != static_cast<ssize_t>(bytes)) std::abort();
    char extra;
    if (read(fd, &extra, 1) != 0 || close(fd) != 0) std::abort();
    return result;
}
static bool Install(const std::vector<sock_filter>& program) {
    const sock_fprog data{static_cast<unsigned short>(program.size()),
                         const_cast<sock_filter*>(program.data())};
    return prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &data) == 0;
}
struct Case {
    const char* name;
    long syscall_nr;
    unsigned long argument;
    int first;
    int second;
    bool nofile;
    bool expect_sigsys;
};
int main(int argc, char** argv) {
    if (argc != 3) return 64;
    struct sigaction child_action{};
    if (sigaction(SIGCHLD, nullptr, &child_action) != 0 ||
        child_action.sa_handler != SIG_DFL || (child_action.sa_flags & SA_NOCLDWAIT) != 0) return 69;
    const auto original = Load(argv[1]);
    const auto candidate = Load(argv[2]);
    const std::vector<sock_filter>* programs[3] = {nullptr, &original, &candidate};
    const Case cases[] = {
        {"stock_fsuid_query_rejected", SYS_setfsuid, ~0UL, 1, 0, false, true},
        {"stock_fsgid_query_rejected", SYS_setfsgid, ~0UL, 1, 0, false, true},
        {"candidate_fsuid_query", SYS_setfsuid, ~0UL, 2, 0, false, false},
        {"candidate_fsgid_query", SYS_setfsgid, ~0UL, 2, 0, false, false},
        {"candidate_fsuid_mutation_rejected", SYS_setfsuid, 0UL, 2, 0, false, true},
        {"candidate_fsgid_mutation_rejected", SYS_setfsgid, 0UL, 2, 0, false, true},
        {"stock_then_candidate_still_rejected", SYS_setfsuid, ~0UL, 1, 2, false, true},
        {"candidate_then_stock_still_rejected", SYS_setfsuid, ~0UL, 2, 1, false, true},
        {"nofile0_fsuid_query", SYS_setfsuid, 0xffffffffUL, 2, 0, true, false},
        {"nofile0_fsgid_query", SYS_setfsgid, 0x12345678ffffffffUL, 2, 0, true, false},
    };
    const pid_t parent = getpid();
    bool all = true;
    std::printf("{\"scope\":\"local_owned_kernel_with_explicit_table_fixtures\",\"cases\":[");
    for (size_t index = 0; index < sizeof(cases) / sizeof(cases[0]); ++index) {
        const Case& item = cases[index];
        int channel[2];
        if (pipe2(channel, O_CLOEXEC) != 0) return 65;
        const pid_t child = fork();
        if (child < 0) return 66;
        if (child == 0) {
            close(channel[0]);
            Record row{-1, -999, -999, -999, 0};
            const rlimit no_core{0, 0};
            if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() != parent ||
                setrlimit(RLIMIT_CORE, &no_core) != 0) _exit(80);
            // Snapshot the same kernel identity before any test filter.
            row.before = syscall(item.syscall_nr, ~0UL);
            if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0) _exit(81);
            if (item.nofile) {
                const rlimit nofile{0, 0};
                if (setrlimit(RLIMIT_NOFILE, &nofile) != 0) _exit(82);
            }
            if (!Install(*programs[item.first])) _exit(83);
            if (item.second != 0 && !Install(*programs[item.second])) _exit(84);
            row.setup = 0;
            // The setup record distinguishes the deliberate filter trap from
            // an outer policy or a setup failure before this point.
            if (write(channel[1], &row, sizeof(row)) != sizeof(row)) _exit(85);
            errno = 137;
            row.observed = syscall(item.syscall_nr, item.argument);
            row.error = errno;
            row.after = syscall(item.syscall_nr, ~0UL);
            if (write(channel[1], &row, sizeof(row)) != sizeof(row)) _exit(86);
            _exit(0);
        }
        close(channel[1]);
        int status = 0;
        pid_t waited = 0;
        bool timed_out = false;
        const int64_t deadline = Now() + 2000;
        for (;;) {
            waited = waitpid(child, &status, WNOHANG);
            if (waited == child || (waited < 0 && errno != EINTR)) break;
            if (Now() >= deadline) {
                // This is the unreaped exact child in this single-threaded
                // dedicated harness; it cannot have been reused by the kernel.
                timed_out = true;
                if (kill(child, SIGKILL) != 0 && errno != ESRCH) return 67;
                const int64_t reap_deadline = Now() + 1000;
                do {
                    waited = waitpid(child, &status, WNOHANG);
                    if (waited == child || (waited < 0 && errno != EINTR)) break;
                    const timespec delay{0, 1000000};
                    nanosleep(&delay, nullptr);
                } while (Now() < reap_deadline);
                break;
            }
            const timespec delay{0, 1000000};
            nanosleep(&delay, nullptr);
        }
        if (waited != child) {
            close(channel[0]);
            return 68;
        }
        Record rows[2]{};
        const ssize_t bytes = read(channel[0], rows, sizeof(rows));
        char trailing;
        const ssize_t extra = read(channel[0], &trailing, 1);
        close(channel[0]);
        const bool setup = bytes >= static_cast<ssize_t>(sizeof(Record)) && rows[0].setup == 0;
        const bool expected = item.expect_sigsys
            ? WIFSIGNALED(status) && WTERMSIG(status) == SIGSYS && bytes == static_cast<ssize_t>(sizeof(Record))
            : WIFEXITED(status) && WEXITSTATUS(status) == 0 && bytes == static_cast<ssize_t>(sizeof(rows)) &&
              rows[1].observed == rows[0].before && rows[1].after == rows[0].before &&
              rows[1].error == 137;
        const bool pass = setup && waited == child && !timed_out && extra == 0 && expected;
        all = all && pass;
        std::printf("%s{\"name\":\"%s\",\"pass\":%s,\"setup\":%s,\"reaped\":%s,"
                    "\"timeout\":%s,\"wait_status\":%d,\"record_bytes\":%zd,"
                    "\"before\":%ld,\"observed\":%ld,\"after\":%ld,\"errno_after\":%d}",
                    index ? "," : "", item.name, pass ? "true" : "false", setup ? "true" : "false",
                    waited == child ? "true" : "false", timed_out ? "true" : "false", status,
                    bytes, rows[0].before, rows[1].observed, rows[1].after, rows[1].error);
    }
    std::printf("],\"pass\":%s}\n", all ? "true" : "false");
    return all ? 0 : 1;
}
