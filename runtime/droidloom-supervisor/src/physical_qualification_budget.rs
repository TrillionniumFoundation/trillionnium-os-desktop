//! One source-owned time/resource contract shared by the normal supervisor
//! and the independent cold fixture. This file has no crate dependencies.
//! It authorizes no action; actual factories and the same original deadline
//! remain required for every case and for the final 39/377 Complete.
pub const NATIVE_CASE_COUNT: usize = 14;
pub const FAMILY_CASE_COUNT: usize = 31;
pub const CASE_COUNT: usize = NATIVE_CASE_COUNT + FAMILY_CASE_COUNT;
// Complete preparation work from the finite normal factories, charged once
// to the actual PID1 parent start. NativeLeafRun reserves post work from each
// call; only its caller executes that PM/Main bookend, so it is counted once.
pub const PREPARATION_LOCAL_SECONDS: u64 = 120;
pub const PREPARATION_IDENTITY_SECONDS: u64 = 38 * 250 + 330;
pub const PREPARATION_MAIN_SECONDS: u64 = 70;
pub const PREPARATION_BASELINE_SECONDS: u64 = 8 * 1_200;
pub const PREPARATION_CHILD_SECONDS: u64 = 11_520;
pub const PREPARATION_BOOKEND_SECONDS: u64 = 15_232;
pub const PREPARATION_HELPER_POST_SECONDS: u64 = 250;
pub const SOURCE_AND_CAPTURE_SECONDS: u64 = PREPARATION_LOCAL_SECONDS
    + PREPARATION_IDENTITY_SECONDS
    + PREPARATION_MAIN_SECONDS
    + PREPARATION_BASELINE_SECONDS
    + PREPARATION_CHILD_SECONDS
    + PREPARATION_BOOKEND_SECONDS
    + PREPARATION_HELPER_POST_SECONDS;
pub const MAIN_SECONDS: u64 = 70;
pub const INSPECT_SECONDS: u64 = 250;
pub const FAMILY_WORK_SECONDS: u64 = 2_615;
pub const FAMILY_CASE_SECONDS: u64 = INSPECT_SECONDS + FAMILY_WORK_SECONDS;
pub const NATIVE_CASE_WINDOWS: [u64; NATIVE_CASE_COUNT] = [
    1690, 1450, 1260, 1180, 2100, 1570, 1960, 1960, 2290, 2290, 2290, 2290, 1660, 1440,
];
const fn native_seconds() -> u64 {
    let mut sum = 0;
    let mut index = 0;
    while index < NATIVE_CASE_COUNT {
        sum += NATIVE_CASE_WINDOWS[index];
        index += 1;
    }
    sum
}
pub const NATIVE_SECONDS: u64 = native_seconds();
// The previous 33,440 already included all thirty-one 250-second inspections.
// The family work window includes its 680-second stability reserve; neither
// the inspections nor stability reserve may be counted a second time.
pub const SUITE_SECONDS: u64 = SOURCE_AND_CAPTURE_SECONDS
    + 2 * MAIN_SECONDS
    + NATIVE_SECONDS
    + FAMILY_CASE_COUNT as u64 * FAMILY_CASE_SECONDS;
pub const RETIREMENT_SECONDS: u64 = 180;
pub const SERVICE_SECONDS: u64 = SUITE_SECONDS + RETIREMENT_SECONDS;
pub const NOFILE_LIMIT: u64 = 32_768;
