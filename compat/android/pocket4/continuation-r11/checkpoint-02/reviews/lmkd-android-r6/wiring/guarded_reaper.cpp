#include <optional>
#include <variant>
extern "C" {
#include <sys/pidfd.h>
}
#include <unistd.h>
#include <signal.h>
struct CgroupKillFD { int fd; };
struct CgroupProcsFD { int fd; };

using CgroupFD = std::optional<std::variant<CgroupKillFD, CgroupProcsFD>>;

// Close the file descriptor in cgroupfd if one exists
void close(const CgroupFD& cgroupfd);


class Reaper { public:
    struct target_proc {
        int pidfd;
        CgroupFD cgroupfd;
        pid_t pid;
        uid_t uid;
    };
    enum class GuardedResult { Denied, Failed, Sent };
    using Effect = bool (*)(void*);
    struct EffectGate {
        void* context;
        GuardedResult (*perform)(void*, Effect, void*);
        bool (*validate_cgroup)(void*, int, uid_t, pid_t);
    };
GuardedResult kill_guarded(const target_proc&, const EffectGate&);
};
Reaper::GuardedResult Reaper::kill_guarded(const struct target_proc& target,
                                          const EffectGate& gate) {
    // This path contains no asynchronous work, priority side effects or PID
    // enumeration. There is no queued request that can outlive its evidence.
    if (!gate.perform || target.pidfd < 0 || target.pid <= 0) return GuardedResult::Denied;
    if (target.cgroupfd) {
        const auto* group = std::get_if<CgroupKillFD>(&*target.cgroupfd);
        // cgroup.procs needs a separately qualified per-member identity and
        // partial-effect contract. It cannot silently fall back in relay mode.
        if (!group || !gate.validate_cgroup ||
            !gate.validate_cgroup(gate.context, group->fd, target.uid, target.pid))
            return GuardedResult::Denied;
        int fd = group->fd;
        const auto written = gate.perform(gate.context, [](void* context) {
            const int target_fd = *static_cast<int*>(context);
            // One byte, one syscall; no hidden retries after an expired gate.
            return write(target_fd, "1", 1) == 1;
        }, &fd);
        if (written != GuardedResult::Failed) return written;
    }
    int pidfd = target.pidfd;
    return gate.perform(gate.context, [](void* context) {
        const int target_fd = *static_cast<int*>(context);
        return pidfd_send_signal(target_fd, SIGKILL, nullptr, 0) == 0;
    }, &pidfd);
}
#define main uncalled_session_control_main
#include "/workspace/scratch/94990735b266/lmkd-work/android-build-freeze-01/tests/test_session.cpp"
#undef main

static unsigned writes = 0, signals = 0, validations = 0;
static bool write_ok = true, group_ok = true;
static uint64_t advance_after_write = 0;
extern "C" ssize_t __wrap_write(int fd, const void* data, size_t length) {
    Need(fd == 51 && length == 1 && *static_cast<const char*>(data) == '1', "single cgroup effect shape");
    ++writes;
    if (advance_after_write) test_clock = advance_after_write;
    if (!write_ok) { errno = EACCES; return -1; }
    return 1;
}
extern "C" int __wrap_pidfd_send_signal(int fd, int signal, siginfo_t*, unsigned flags) {
    Need(fd == 61 && signal == SIGKILL && flags == 0, "held pidfd effect shape");
    ++signals; return 0;
}
static Reaper::GuardedResult Gate(void* context, Reaper::Effect effect, void* argument) {
    const auto result = static_cast<Session*>(context)->Perform([&]() { return effect(argument); });
    if (result == Dispatch::Denied) return Reaper::GuardedResult::Denied;
    if (result == Dispatch::Failed) return Reaper::GuardedResult::Failed;
    return Reaper::GuardedResult::Sent;
}
static bool Group(void*, int fd, uid_t uid, pid_t pid) {
    ++validations;
    Need(fd == 51 && uid == 10001 && pid == 123, "exact expected group check");
    return group_ok;
}
int main() {
    Fixture f;
    Reaper reaper;
    const Reaper::EffectGate gate{&f.session, Gate, Group};
    Reaper::target_proc target{61, {}, 123, 10001};
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && !signals,
          "real Reaper entry cannot signal from lease-only authority");
    f.FreezeClock(); const uint64_t observed = f.Fresh();
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Sent && signals == 1 && !writes,
          "pidfd-only effect is synchronous and finally gated");
    target.cgroupfd = CgroupKillFD{51}; signals = 0;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Sent && writes == 1 && !signals && validations == 1,
          "verified exact group uses one actual write without queued work");
    group_ok = false;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && writes == 1 && !signals,
          "unbound broad group is refused without fallback");
    group_ok = true; target.cgroupfd = CgroupProcsFD{51};
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && writes == 1 && !signals,
          "legacy numeric-PID cgroup loop is explicitly unsupported");
    target.cgroupfd = CgroupKillFD{51}; write_ok = false;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Sent && writes == 2 && signals == 1,
          "failed group write requires a separately gated held-pidfd fallback");
    signals = 0; advance_after_write = observed + 1000000000;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && writes == 3 && !signals,
          "window expiry during failed group write prevents fallback syscall");
    f.session.Stop(); writes = signals = 0;
    Check(reaper.kill_guarded(target, gate) == Reaper::GuardedResult::Denied && !writes && !signals,
          "revoked generation leaves no deferred worker effect");
    std::printf("RESULT %u actual Reaper source assertions passed; syscall I/O replaced\n", passed);
}
