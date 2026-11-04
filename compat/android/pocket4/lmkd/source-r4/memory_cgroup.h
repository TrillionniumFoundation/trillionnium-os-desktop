/*
 * Copyright 2026 Droidloom contributors
 * SPDX-License-Identifier: Apache-2.0
 *
 * Input adapter for AOSP LMKD. It contains no process selection or signal code.
 */
#pragma once

#include <cstddef>
#include <cstdint>
#include <string_view>

namespace droidloom::lmkd {

struct MemoryStat {
    uint64_t anon, file, shmem, swapcached;
    uint64_t active_anon, inactive_anon, active_file, inactive_file;
    uint64_t unevictable, slab_reclaimable, slab_unreclaimable;
    uint64_t kernel_stack, pagetables, file_dirty;
    uint64_t workingset_refault_file, pgscan_kswapd, pgscan_direct, pgrefill;
};

struct HostMemory {
    uint64_t total, free, swap_total, swap_free;
};

struct Snapshot {
    uint64_t current, max, high, swap_current, swap_max;
    bool high_unlimited, swap_unlimited;
    uint64_t high_events;
    // True only for a new high event between two successful, coherent reads
    // with the same budget, while current usage still exceeds finite high.
    bool high_throttling_progressed;
    MemoryStat stat;
    HostMemory host;
};

struct Watermarks {
    uint64_t min, low, high;
};

// Parsing is strict for required inputs and ignores unknown kernel fields.
// Units: memory amounts are bytes; reclaim/refault counters are pages/events.
bool ParseNumber(std::string_view text, uint64_t* value);
bool ParseLimit(std::string_view text, uint64_t* value, bool* unlimited);
bool ParseStat(std::string_view text, MemoryStat* stat);
bool ParseHighEvents(std::string_view text, uint64_t* high_events);
bool ParseHostMemory(std::string_view text, HostMemory* host);
bool Validate(const Snapshot& snapshot, uint64_t page_size);
bool CountersMonotonic(const Snapshot& previous, const Snapshot& current);
bool HighThrottlingProgressed(const Snapshot& previous, const Snapshot& current);

// Real capacity remaining, capped by physical free memory; never credits the
// host's total RAM as container capacity. Clean cache is not added here.
uint64_t FreeBytes(const Snapshot& snapshot);
uint64_t SwapTotalBytes(const Snapshot& snapshot);
uint64_t SwapFreeBytes(const Snapshot& snapshot);

// Keep kernel watermark proportions, rescale for the cell, and place the high
// watermark no later than memory.high. These are capacity thresholds, not a kill
// trigger: AOSP's PSI/reclaim/thrashing logic still decides whether to act.
bool ScaleWatermarks(const Snapshot& snapshot, const Watermarks& host_pages,
                     uint64_t page_size, Watermarks* cell_pages);

class Reader {
  public:
    Reader() = default;
    ~Reader();
    Reader(const Reader&) = delete;
    Reader& operator=(const Reader&) = delete;

    // The production caller uses the fixed, runtime-projected cell cgroup root.
    // Rejects non-cgroup2 directories. Test parsers do not require a live cgroup.
    bool Open(const char* root);
    bool Read(Snapshot* snapshot);
    int OpenPressureMonitor(bool full, uint64_t stall_us, uint64_t window_us) const;
    int error() const { return error_; }

  private:
    enum File { kCurrent, kMax, kHigh, kSwapCurrent, kSwapMax, kStat, kEvents, kHostMem, kCount };
    int root_fd_ = -1;
    int fds_[kCount] = {-1, -1, -1, -1, -1, -1, -1, -1};
    int error_ = 0;
    bool opened_ = false;
    bool counters_faulted_ = false;
    bool previous_valid_ = false;
    bool high_baseline_valid_ = false;
    Snapshot previous_{};
    bool ReadFile(File file, char* buffer, size_t size, std::string_view* text);
};

}  // namespace droidloom::lmkd
