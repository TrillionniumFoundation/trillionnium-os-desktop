// Compile the complete preimage or candidate translation unit with explicitly
// declared generated-policy/logging fixtures. Capture the actual sock_fprog at
// its install boundary without installing a filter in this process.
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <vector>

static std::vector<sock_filter> captured;
static int CapturePrctl(int operation, ...) {
    va_list ap;
    va_start(ap, operation);
    const int mode = va_arg(ap, int);
    const auto* prog = va_arg(ap, const sock_fprog*);
    va_end(ap);
    if (operation != PR_SET_SECCOMP || mode != SECCOMP_MODE_FILTER ||
        prog == nullptr || prog->len == 0 || prog->len > 4096) std::abort();
    captured.assign(prog->filter, prog->filter + prog->len);
    return 0;
}
#define prctl CapturePrctl
#include SOURCE_FILE
#undef prctl

static_assert(SYS_setfsuid == __x86_64_setfsuid);
static_assert(SYS_setfsgid == __x86_64_setfsgid);
static_assert(SYS_setresuid == __x86_64_setresuid);
static_assert(SYS_setresgid == __x86_64_setresgid);

static void Emit(const char* name, bool (*build)(), bool comma) {
    captured.clear();
    if (!build() || captured.empty()) std::abort();
    std::printf("%s\"%s\":[", comma ? "," : "", name);
    for (size_t i = 0; i < captured.size(); ++i) {
        const auto& insn = captured[i];
        std::printf("%s[%u,%u,%u,%u]", i ? "," : "", insn.code,
                    insn.jt, insn.jf, insn.k);
    }
    std::printf("]");
}
int main() {
    std::printf("{");
    Emit("app", set_app_seccomp_filter, false);
    Emit("app_zygote", set_app_zygote_seccomp_filter, true);
    Emit("system", set_system_seccomp_filter, true);
#if CANDIDATE
    Emit("app_zygote_fs_queries_v1", set_droidloom_app_zygote_seccomp_filter_v1, true);
#endif
    std::printf("}\n");
    return 0;
}
