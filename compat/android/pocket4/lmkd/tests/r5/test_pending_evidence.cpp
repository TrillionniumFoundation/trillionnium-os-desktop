/* Copyright 2026 Droidloom contributors; SPDX-License-Identifier: Apache-2.0 */
// Appended to the existing real-Reader descriptor fixture by run_controls.py.
// Neither this test nor its clock/descriptor substitutes accesses a live cell.
#include <climits>
#include <time.h>
#include <vector>

static int64_t fake_ms = 1000;
static long extra_ns;
static bool fail_clock;
static int malformed_clock;
extern "C" int __wrap_clock_gettime(clockid_t clock, struct timespec* out) {
    if (clock != CLOCK_MONOTONIC || fail_clock) { errno = EIO; return -1; }
    *out = {fake_ms / 1000, (fake_ms % 1000) * 1000000 + extra_ns};
    if (malformed_clock == 1) out->tv_sec = -1;
    if (malformed_clock == 2) out->tv_nsec = -1;
    if (malformed_clock == 3) out->tv_nsec = 1000000000;
    if (malformed_clock == 4) out->tv_sec = INT64_MAX;
    return 0;
}
static void reset_clock() {
    fake_ms = 1000;
    extra_ns = 0;
    fail_clock = false;
    malformed_clock = 0;
}
static void seed(Reader& r, Snapshot& s) {
    reset(); reset_clock();
    require(r.Open("/owned-cell") && r.Read(&s, 1000), "fresh pinned Reader baseline");
    require(!r.ConsumeHighEvidence(1000), "cold cumulative counter is never pending evidence");
    events(51); fake_ms = 1100;
    require(r.Read(&s, 1000) && s.high_throttling_progressed, "new coherent high increment observed");
}
static void restored(Reader& r, Snapshot& s, unsigned first_count) {
    fake_ms += 1; events(first_count);
    require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "first recovered read cannot revive invalidated interval");
    events(first_count + 1); fake_ms += 1;
    require(r.Read(&s, 1000) && r.ConsumeHighEvidence(1000), "subsequent new coherent increment restores evidence");
}

int main() {
    {
        Reader r; Snapshot s{};
        require(!r.ConsumeHighEvidence(1000), "unopened Reader has no evidence");
        require(!r.Read(&s, 1000) && r.error() == EBADF, "unopened timed read fails closed");
        r.Close(); r.Close();
        require(!r.ConsumeHighEvidence(1000), "idempotent Close leaves no evidence");
    }
    {
        Reader r; Snapshot s{}; seed(r, s);
        fake_ms = 1200;
        require(r.Read(&s, 1000) && !s.high_throttling_progressed, "accounting baseline advances on an unchanged poll");
        require(r.ConsumeHighEvidence(1000), "unchanged poll preserves unconsumed fresh high evidence");
        require(!r.ConsumeHighEvidence(1000), "one token cannot serve two critical decisions");
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "same count after consumption cannot recreate token");
        events(52);
        require(r.Read(&s, 1000) && r.ConsumeHighEvidence(1000), "new real increment can create another token");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); fake_ms = 2099;
        require(r.ConsumeHighEvidence(1000), "token is valid just before existing window expires");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); fake_ms = 2100;
        require(!r.ConsumeHighEvidence(1000), "token expires exactly at existing window boundary");
        fake_ms = 2101;
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "expired historical count cannot be reused");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); fake_ms = 1600;
        require(r.Read(&s, 1000), "intermediate unchanged accounting read succeeds");
        fake_ms = 2100;
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "unchanged polls cannot extend evidence lifetime");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); fake_ms = 1800; events(52);
        require(r.Read(&s, 1000), "genuine additional high event observed before expiry");
        fake_ms = 2200;
        require(r.ConsumeHighEvidence(1000), "genuine new increment refreshes bounded lifetime");
    }
    for (int64_t invalid_window : {INT64_C(-1), INT64_C(0), INT64_C(499), INT64_C(10001)}) {
        Reader r; Snapshot s{}; seed(r, s);
        require(r.Read(&s, invalid_window) && !r.ConsumeHighEvidence(invalid_window), "invalid monitor window clears read-side evidence");
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "restoring window cannot reuse unchanged counter");
    }
    for (int64_t invalid_window : {INT64_C(-1), INT64_C(0), INT64_C(499), INT64_C(10001)}) {
        Reader r; Snapshot s{}; seed(r, s);
        require(!r.ConsumeHighEvidence(invalid_window) && !r.ConsumeHighEvidence(1000), "invalid consume window irrevocably clears token");
        restored(r, s, 52);
    }
    {
        Reader r; Snapshot s{}; seed(r, s); events(52);
        require(r.Read(&s, 1500) && !r.ConsumeHighEvidence(1500), "changed valid window discards even concurrent high increment");
        events(53);
        require(r.Read(&s, 1500) && r.ConsumeHighEvidence(1500), "new event under stable new window works");
    }
    {
        Reader r; Snapshot s{}; seed(r, s);
        require(!r.ConsumeHighEvidence(1500) && !r.ConsumeHighEvidence(1000), "consume cannot switch windows to extend a token");
        restored(r, s, 52);
    }
    for (int64_t valid_window : {INT64_C(500), INT64_C(10000)}) {
        reset(); reset_clock(); Reader r; Snapshot s{};
        require(r.Open("/owned-cell") && r.Read(&s, valid_window), "existing monitor window endpoint baseline");
        events(51);
        require(r.Read(&s, valid_window) && r.ConsumeHighEvidence(valid_window), "existing monitor window endpoint accepts genuine evidence");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); fake_ms = 1099; events(52);
        require(!r.Read(&s, 1000) && r.error() == ERANGE && s.high_events == 51, "read clock rollback rejects whole sample without publishing");
        require(!r.ConsumeHighEvidence(1000), "read clock rollback clears pending evidence");
        fake_ms = 1200; restored(r, s, 53);
    }
    {
        Reader r; Snapshot s{}; seed(r, s); fake_ms = 1099;
        require(!r.ConsumeHighEvidence(1000), "consume clock rollback clears token");
        fake_ms = 1200; restored(r, s, 52);
    }
    {
        Reader r; Snapshot s{}; seed(r, s); extra_ns = 500000;
        require(r.Read(&s, 1000), "submillisecond observation retains full clock precision");
        extra_ns = 499999;
        require(!r.Read(&s, 1000) && r.error() == ERANGE && !r.ConsumeHighEvidence(1000), "one nanosecond read clock rollback fails closed");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); extra_ns = 500000;
        require(r.Read(&s, 1000), "submillisecond observation before consume");
        extra_ns = 499999;
        require(!r.ConsumeHighEvidence(1000), "one nanosecond consume clock rollback fails closed");
    }
    for (long at_expiry : {499999L, 500000L}) {
        Reader r; Snapshot s{}; seed(r, s); extra_ns = 500000; events(52);
        require(r.Read(&s, 1000), "fresh event keeps exact submillisecond observation timestamp");
        fake_ms = 2100; extra_ns = at_expiry;
        require(r.ConsumeHighEvidence(1000) == (at_expiry < 500000), "expiry uses full precision at the existing window boundary");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); fail_clock = true; events(52);
        require(!r.Read(&s, 1000) && r.error() == EIO && s.high_events == 51, "read clock failure rejects sample and preserves output");
        require(!r.ConsumeHighEvidence(1000), "read clock failure cannot leave pending evidence");
        fail_clock = false; restored(r, s, 53);
    }
    {
        Reader r; Snapshot s{}; seed(r, s); fail_clock = true;
        require(!r.ConsumeHighEvidence(1000), "consume clock failure clears token");
        fail_clock = false; restored(r, s, 52);
    }
    for (int malformed = 1; malformed <= 4; ++malformed) {
        Reader r; Snapshot s{}; seed(r, s); malformed_clock = malformed;
        require(!r.Read(&s, 1000) && r.error() == ERANGE && !r.ConsumeHighEvidence(1000), "malformed or overflowing clock fails closed");
        malformed_clock = 0; restored(r, s, 52);
    }
    for (auto budget : std::vector<std::pair<std::string, std::string>>{
            {"memory.high", "419430400\n"}, {"memory.high", "385875968\n"},
            {"memory.max", "570425344\n"}, {"memory.swap.max", "16777216\n"},
            {"memory.swap.max", "max\n"}}) {
        Reader r; Snapshot s{}; seed(r, s); files[budget.first] = budget.second; events(52);
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "changed finite budget or swap mode invalidates old token and concurrent delta");
        events(53);
        require(r.Read(&s, 1000) && r.ConsumeHighEvidence(1000), "new stable budget and fresh increment can recover");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); files["memory.high"] = "max\n"; events(52);
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "unlimited high clears pending evidence");
        events(53);
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "event increase with unlimited high cannot create token");
        files["memory.high"] = "402653184\n"; events(54);
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "return to finite high establishes baseline only");
        events(55);
        require(r.Read(&s, 1000) && r.ConsumeHighEvidence(1000), "new finite high interval can create fresh evidence");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); files["memory.swap.max"] = "max\n";
        require(r.Read(&s, 1000), "unlimited swap establishes new budget");
        events(52);
        require(r.Read(&s, 1000), "fresh token under unchanged unlimited swap budget");
        files["memory.swap.max"] = "0\n"; events(53);
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "unlimited-to-finite swap change discards prior evidence and concurrent delta");
        events(54);
        require(r.Read(&s, 1000) && r.ConsumeHighEvidence(1000), "fresh event under restored finite swap budget is valid");
    }
    for (auto quiet_current : {"402653184\n", "398458880\n"}) {
        Reader r; Snapshot s{}; seed(r, s); files["memory.current"] = quiet_current;
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "usage at or below high clears token despite historical high count");
        files["memory.current"] = "442388480\n";
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "usage rise alone cannot restore historical evidence");
        events(52);
        require(r.Read(&s, 1000) && r.ConsumeHighEvidence(1000), "new actual event after below-high recovery is valid");
    }
    for (auto file : {"memory.current", "memory.max", "memory.high", "memory.swap.current",
                      "memory.swap.max", "memory.stat", "memory.events", "host"}) {
        Reader r; Snapshot s{}; seed(r, s); failed_file = file; events(52);
        require(!r.Read(&s, 1000) && s.high_events == 51 && !r.ConsumeHighEvidence(1000), "any required input failure clears token without publishing partial state");
        failed_file.clear(); restored(r, s, 53);
    }
    for (auto malformed : {"low 0\n", "high 52\nhigh 52\n", "high -1\n", "high 18446744073709551615\n"}) {
        Reader r; Snapshot s{}; seed(r, s); files["memory.events"] = malformed;
        require(!r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "malformed high event data clears pending token");
        restored(r, s, 53);
    }
    {
        Reader r; Snapshot s{}; seed(r, s); race_high = true; high_reads = 0;
        require(!r.Read(&s, 1000) && r.error() == EAGAIN && !r.ConsumeHighEvidence(1000), "concurrent budget change invalidates pending evidence");
        race_high = false; restored(r, s, 52);
    }
    {
        Reader r; Snapshot s{}; seed(r, s); events(49);
        require(!r.Read(&s, 1000) && r.error() == EUCLEAN && !r.ConsumeHighEvidence(1000), "high counter rollback rejects token and Reader");
        events(52);
        require(!r.Read(&s, 1000) && r.error() == EUCLEAN && !r.ConsumeHighEvidence(1000), "later increase cannot reopen faulted generation");
        r.Close(); reset(); reset_clock(); events(1000);
        require(r.Open("/owned-cell") && r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "new pinned generation treats cumulative counter only as baseline");
    }
    {
        Reader r; Snapshot s{}; seed(r, s); r.ClearHighEvidence();
        require(!r.ConsumeHighEvidence(1000), "monitor teardown or external input failure explicitly invalidates token");
        restored(r, s, 52);
    }
    {
        Reader r; Snapshot s{}; seed(r, s);
        require(r.Read(&s) && !r.ConsumeHighEvidence(1000), "untimed accounting read cannot preserve pressure evidence");
        require(r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "first timed read after untimed read cannot reuse same counter");
    }
    {
        Reader r; Snapshot s{}; seed(r, s);
        require(!r.Open("/owned-cell") && r.error() == EALREADY && !r.ConsumeHighEvidence(1000), "repeated Open failure clears pending evidence");
        restored(r, s, 52);
    }
    {
        Reader r; Snapshot s{}; seed(r, s); const int before_close = close_calls; r.Close();
        require(close_calls - before_close == 9, "Close releases all eight input descriptors and pinned root");
        r.Close();
        require(close_calls - before_close == 9, "repeated Close cannot close reused descriptor numbers");
        require(!r.ConsumeHighEvidence(1000) && !r.Read(&s, 1000), "Close invalidates current token and input descriptors");
        reset(); reset_clock(); events(51);
        require(r.Open("/owned-cell") && r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "same numeric FD after reopen cannot transfer old generation token");
        events(52);
        require(r.Read(&s, 1000) && r.ConsumeHighEvidence(1000), "reopened generation requires its own fresh interval");
    }
    {
        reset(); reset_clock(); files.erase("memory.events"); Reader r; Snapshot s{};
        require(!r.Open("/owned-cell") && !r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "partial Open failure cannot publish accounting or evidence");
        const int before_close = close_calls; r.Close();
        require(close_calls - before_close == 7, "partial Open cleanup releases only acquired descriptors");
        reset();
        require(r.Open("/owned-cell") && r.Read(&s, 1000) && !r.ConsumeHighEvidence(1000), "Close after partial Open permits only a new cold baseline");
    }
    {
        const int before_destructor = close_calls;
        { Reader r; Snapshot s{}; seed(r, s); }
        require(close_calls - before_destructor == 9, "destructor releases pinned generation even with pending evidence");
    }
    std::printf("RESULT %d passed\n", checks);
}
