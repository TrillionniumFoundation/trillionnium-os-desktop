/* Copyright 2026 Droidloom contributors
 * SPDX-License-Identifier: Apache-2.0 */
#include "memory_cgroup.h"

#include <algorithm>
#include <cerrno>
#include <charconv>
#include <climits>
#include <cstdio>
#include <fcntl.h>
#include <linux/magic.h>
#include <iterator>
#include <sys/vfs.h>
#include <unistd.h>

namespace droidloom::lmkd {
namespace {
std::string_view Trim(std::string_view s) {
    while (!s.empty() && (s.front() == ' ' || s.front() == '\t' || s.front() == '\n')) s.remove_prefix(1);
    while (!s.empty() && (s.back() == ' ' || s.back() == '\t' || s.back() == '\n')) s.remove_suffix(1);
    return s;
}

uint64_t Sub(uint64_t a, uint64_t b) { return a > b ? a - b : 0; }

bool MulDivCeil(uint64_t a, uint64_t b, uint64_t divisor, uint64_t* out) {
    if (!divisor) return false;
    __uint128_t value = (static_cast<__uint128_t>(a) * b + divisor - 1) / divisor;
    if (value > INT64_MAX) return false;
    *out = static_cast<uint64_t>(value);
    return true;
}

struct Field { std::string_view name; uint64_t MemoryStat::*member; };
constexpr Field fields[] = {
    {"anon", &MemoryStat::anon}, {"file", &MemoryStat::file},
    {"shmem", &MemoryStat::shmem}, {"swapcached", &MemoryStat::swapcached},
    {"active_anon", &MemoryStat::active_anon}, {"inactive_anon", &MemoryStat::inactive_anon},
    {"active_file", &MemoryStat::active_file}, {"inactive_file", &MemoryStat::inactive_file},
    {"unevictable", &MemoryStat::unevictable}, {"slab_reclaimable", &MemoryStat::slab_reclaimable},
    {"slab_unreclaimable", &MemoryStat::slab_unreclaimable},
    {"kernel_stack", &MemoryStat::kernel_stack}, {"pagetables", &MemoryStat::pagetables},
    {"file_dirty", &MemoryStat::file_dirty},
    {"workingset_refault_file", &MemoryStat::workingset_refault_file},
    {"pgscan_kswapd", &MemoryStat::pgscan_kswapd}, {"pgscan_direct", &MemoryStat::pgscan_direct},
    {"pgrefill", &MemoryStat::pgrefill},
};

template <typename Callback> bool Lines(std::string_view text, Callback callback) {
    while (!text.empty()) {
        size_t end = text.find('\n');
        auto line = Trim(text.substr(0, end));
        if (!line.empty() && !callback(line)) return false;
        if (end == std::string_view::npos) break;
        text.remove_prefix(end + 1);
    }
    return true;
}
}  // namespace

bool ParseNumber(std::string_view text, uint64_t* value) {
    text = Trim(text);
    if (text.empty() || text.front() < '0' || text.front() > '9') return false;
    uint64_t parsed;
    auto r = std::from_chars(text.data(), text.data() + text.size(), parsed);
    if (r.ec != std::errc{} || r.ptr != text.data() + text.size() || parsed > INT64_MAX) return false;
    *value = parsed;
    return true;
}

bool ParseLimit(std::string_view text, uint64_t* value, bool* unlimited) {
    if (Trim(text) == "max") { *value = 0; *unlimited = true; return true; }
    if (!ParseNumber(text, value)) return false;
    *unlimited = false;
    return true;
}

bool ParseStat(std::string_view text, MemoryStat* stat) {
    MemoryStat parsed{};
    uint32_t seen = 0;
    bool ok = Lines(text, [&](std::string_view line) {
        size_t split = line.find_first_of(" \t");
        if (split == std::string_view::npos) return false;
        auto name = line.substr(0, split);
        for (size_t i = 0; i < std::size(fields); ++i) {
            if (name != fields[i].name) continue;
            if ((seen & (1U << i)) || !ParseNumber(line.substr(split + 1), &(parsed.*fields[i].member))) return false;
            seen |= 1U << i;
            break;
        }
        return true;
    });
    if (!ok || seen != ((1U << std::size(fields)) - 1)) return false;
    *stat = parsed;
    return true;
}

bool ParseHighEvents(std::string_view text, uint64_t* high_events) {
    uint64_t parsed = 0;
    bool seen = false;
    bool ok = Lines(text, [&](std::string_view line) {
        size_t split = line.find_first_of(" \t");
        if (split == std::string_view::npos) return false;
        if (line.substr(0, split) != "high") return true;
        if (seen || !ParseNumber(line.substr(split + 1), &parsed)) return false;
        seen = true;
        return true;
    });
    if (!ok || !seen) return false;
    *high_events = parsed;
    return true;
}

bool ParseHostMemory(std::string_view text, HostMemory* host) {
    HostMemory parsed{};
    uint32_t seen = 0;
    constexpr std::string_view names[] = {"MemTotal:", "MemFree:", "SwapTotal:", "SwapFree:"};
    uint64_t* targets[] = {&parsed.total, &parsed.free, &parsed.swap_total, &parsed.swap_free};
    bool ok = Lines(text, [&](std::string_view line) {
        size_t split = line.find_first_of(" \t");
        if (split == std::string_view::npos) return false;
        for (size_t i = 0; i < std::size(names); ++i) {
            if (line.substr(0, split) != names[i]) continue;
            auto amount = Trim(line.substr(split + 1));
            if ((seen & (1U << i)) || amount.size() < 3 || amount.substr(amount.size() - 2) != "kB") return false;
            uint64_t kib;
            if (!ParseNumber(amount.substr(0, amount.size() - 2), &kib) || kib > INT64_MAX / 1024) return false;
            *targets[i] = kib * 1024;
            seen |= 1U << i;
        }
        return true;
    });
    if (!ok || seen != 15 || !parsed.total || parsed.free > parsed.total || parsed.swap_free > parsed.swap_total) return false;
    *host = parsed;
    return true;
}

bool Validate(const Snapshot& s, uint64_t page_size) {
    if (!page_size || (page_size & (page_size - 1)) || page_size > 65536) return false;
    if (s.max < page_size || s.max > INT64_MAX || s.max > s.host.total) return false;
    if (!s.high_unlimited && (s.high < page_size || s.high > s.max)) return false;
    if (s.current > INT64_MAX || s.swap_current > INT64_MAX || s.swap_max > INT64_MAX) return false;
    // Kernel counters are not an atomic accounting identity. Do not reject a
    // valid sample for small charge/stat races; saturating arithmetic below is
    // intentional. A lowered limit can also temporarily be below current.
    return s.host.free <= s.host.total && s.host.swap_free <= s.host.swap_total;
}

bool CountersMonotonic(const Snapshot& a, const Snapshot& b) {
    return b.high_events >= a.high_events &&
           b.stat.workingset_refault_file >= a.stat.workingset_refault_file &&
           b.stat.pgscan_kswapd >= a.stat.pgscan_kswapd &&
           b.stat.pgscan_direct >= a.stat.pgscan_direct && b.stat.pgrefill >= a.stat.pgrefill;
}

bool HighThrottlingProgressed(const Snapshot& a, const Snapshot& b) {
    // memory.events.high counts actual high-boundary throttling, including
    // reclaim attempts that have no scannable pages. A changed budget or an
    // old cumulative event is not evidence of current pressure.
    return !a.high_unlimited && !b.high_unlimited && a.high == b.high &&
           a.max == b.max && a.swap_max == b.swap_max &&
           a.swap_unlimited == b.swap_unlimited && b.current > b.high &&
           b.high_events > a.high_events;
}

uint64_t FreeBytes(const Snapshot& s) { return std::min(Sub(s.max, s.current), s.host.free); }
uint64_t SwapTotalBytes(const Snapshot& s) { return s.swap_unlimited ? s.host.swap_total : std::min(s.swap_max, s.host.swap_total); }
uint64_t SwapFreeBytes(const Snapshot& s) { return std::min(s.host.swap_free, Sub(SwapTotalBytes(s), s.swap_current)); }

bool ScaleWatermarks(const Snapshot& s, const Watermarks& host, uint64_t page_size, Watermarks* cell) {
    if (!Validate(s, page_size) || !host.high || !host.min || host.min > host.low || host.low > host.high) return false;
    Watermarks result{};
    uint64_t scaled_high;
    if (!MulDivCeil(host.high, s.max, s.host.total, &scaled_high)) return false;
    uint64_t high_reserve = s.high_unlimited ? 0 : (Sub(s.max, s.high) / page_size);
    result.high = std::max(scaled_high, high_reserve);
    if (!result.high || result.high >= s.max / page_size) return false;
    if (!MulDivCeil(host.low, result.high, host.high, &result.low) ||
        !MulDivCeil(host.min, result.high, host.high, &result.min)) return false;
    *cell = result;
    return true;
}

Reader::~Reader() {
    for (int fd : fds_) if (fd >= 0) close(fd);
    if (root_fd_ >= 0) close(root_fd_);
}

bool Reader::Open(const char* root) {
    if (root_fd_ >= 0) { error_ = EALREADY; return false; }
    root_fd_ = open(root, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW);
    struct statfs fs{};
    if (root_fd_ < 0) { error_ = errno; return false; }
    if (fstatfs(root_fd_, &fs) || fs.f_type != CGROUP2_SUPER_MAGIC) { error_ = ENODEV; return false; }
    constexpr const char* names[] = {"memory.current", "memory.max", "memory.high",
                                    "memory.swap.current", "memory.swap.max", "memory.stat",
                                    "memory.events"};
    for (int i = 0; i < kHostMem; ++i) {
        fds_[i] = openat(root_fd_, names[i], O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
        if (fds_[i] < 0) { error_ = errno; return false; }
    }
    fds_[kHostMem] = open("/proc/meminfo", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fds_[kHostMem] < 0) { error_ = errno; return false; }
    opened_ = true;
    return true;
}

bool Reader::ReadFile(File file, char* buffer, size_t size, std::string_view* text) {
    ssize_t n;
    do { n = pread(fds_[file], buffer, size - 1, 0); } while (n < 0 && errno == EINTR);
    if (n <= 0 || static_cast<size_t>(n) == size - 1) { error_ = n < 0 ? errno : EOVERFLOW; return false; }
    *text = {buffer, static_cast<size_t>(n)};
    return true;
}

bool Reader::Read(Snapshot* out) {
    // A failed sample breaks the event interval. Retain the last counters for
    // rollback detection, but never reuse its events as fresh pressure later.
    const bool compare_high = high_baseline_valid_;
    high_baseline_valid_ = false;
    if (!opened_ || counters_faulted_) { error_ = counters_faulted_ ? EUCLEAN : EBADF; return false; }
    Snapshot s{};
    char buffer[8192];
    std::string_view text;
    bool max_unlimited;
    auto number = [&](File file, uint64_t* v) { return ReadFile(file, buffer, sizeof(buffer), &text) && ParseNumber(text, v); };
    auto limit = [&](File file, uint64_t* v, bool* unlimited) { return ReadFile(file, buffer, sizeof(buffer), &text) && ParseLimit(text, v, unlimited); };
    error_ = EINVAL;
    if (!limit(kMax, &s.max, &max_unlimited) || max_unlimited ||
        !limit(kHigh, &s.high, &s.high_unlimited) ||
        !limit(kSwapMax, &s.swap_max, &s.swap_unlimited) ||
        !number(kCurrent, &s.current) || !number(kSwapCurrent, &s.swap_current) ||
        !ReadFile(kStat, buffer, sizeof(buffer), &text) || !ParseStat(text, &s.stat) ||
        !ReadFile(kEvents, buffer, sizeof(buffer), &text) || !ParseHighEvents(text, &s.high_events) ||
        !ReadFile(kHostMem, buffer, sizeof(buffer), &text) || !ParseHostMemory(text, &s.host)) return false;
    // Do not combine an old budget with new usage across a concurrent change.
    uint64_t second;
    bool unlimited;
    if (!limit(kMax, &second, &unlimited) || unlimited || second != s.max ||
        !limit(kHigh, &second, &unlimited) || unlimited != s.high_unlimited || second != s.high ||
        !limit(kSwapMax, &second, &unlimited) || unlimited != s.swap_unlimited || second != s.swap_max) { error_ = EAGAIN; return false; }
    long page_size = sysconf(_SC_PAGESIZE);
    if (page_size <= 0 || !Validate(s, static_cast<uint64_t>(page_size))) return false;
    if (previous_valid_ && !CountersMonotonic(previous_, s)) {
        counters_faulted_ = true;
        error_ = EUCLEAN;
        return false;
    }
    s.high_throttling_progressed = compare_high && HighThrottlingProgressed(previous_, s);
    previous_ = s;
    previous_valid_ = true;
    high_baseline_valid_ = true;
    *out = s;
    error_ = 0;
    return true;
}

int Reader::OpenPressureMonitor(bool full, uint64_t stall_us, uint64_t window_us) const {
    if (!opened_ || window_us < 500000 || window_us > 10000000 || !stall_us || stall_us > window_us) { errno = EINVAL; return -1; }
    int fd = openat(root_fd_, "memory.pressure", O_RDWR | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW);
    if (fd < 0) return -1;
    char trigger[96];
    int n = snprintf(trigger, sizeof(trigger), "%s %llu %llu", full ? "full" : "some",
                     static_cast<unsigned long long>(stall_us), static_cast<unsigned long long>(window_us));
    ssize_t written;
    do { written = write(fd, trigger, static_cast<size_t>(n)); } while (written < 0 && errno == EINTR);
    if (written != n) { int error = written < 0 ? errno : EIO; close(fd); errno = error; return -1; }
    return fd;
}
}  // namespace droidloom::lmkd
