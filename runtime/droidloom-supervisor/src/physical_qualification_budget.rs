//! One source-owned time/resource contract shared by the normal supervisor
//! and the independent cold fixture. This file has no crate dependencies.
//! It authorizes no action; actual factories and the same original deadline
//! remain required for every case and for the final 39/377 Complete.
pub const NATIVE_CASE_COUNT: usize = 14;
pub const FAMILY_CASE_COUNT: usize = 31;
pub const RETAIL_CASE_COUNT: usize = 5;
pub const PHOTO_CASE_COUNT: usize = 1;
pub const SETTINGS_CASE_COUNT: usize = 1;
pub const CASE_COUNT: usize =
    NATIVE_CASE_COUNT + FAMILY_CASE_COUNT + PHOTO_CASE_COUNT + SETTINGS_CASE_COUNT;
// Complete preparation work from the finite normal factories, charged once
// to the actual PID1 parent start. NativeLeafRun reserves post work from each
// call; only its caller executes that PM/Main bookend, so it is counted once.
pub const PREPARATION_LOCAL_SECONDS: u64 = 120;
pub const PREPARATION_IDENTITY_SECONDS: u64 = 38 * 250 + 330;
pub const PREPARATION_MAIN_SECONDS: u64 = 70;
// Initial local admission and the one actual Main bootstrap share these
// existing preparation components. This is a prefix, never another allowance.
pub const PREPARATION_BOOTSTRAP_SECONDS: u64 = PREPARATION_LOCAL_SECONDS + PREPARATION_MAIN_SECONDS;
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
pub const FAMILY_UI_WORK_SECONDS: u64 = 6_490;
// PM, AppOps and registered-account samples enclose each actual family UI case.
// They are partial preservation evidence, not full data or credential acceptance.
pub const FAMILY_PM_PERMISSION_SECONDS: u64 = 2 * 70;
pub const FAMILY_APPOPS_SECONDS: u64 = 2 * 70;
pub const FAMILY_ACCOUNT_SECONDS: u64 = 2 * 70;
pub const FAMILY_WORK_SECONDS: u64 = FAMILY_UI_WORK_SECONDS
    + FAMILY_PM_PERMISSION_SECONDS
    + FAMILY_APPOPS_SECONDS
    + FAMILY_ACCOUNT_SECONDS;
pub const FAMILY_CASE_SECONDS: u64 = INSPECT_SECONDS + FAMILY_WORK_SECONDS;
// Only the five compiled retail cases execute the finite business sequence:
// 26 first + 12 second UI requests, four scoped captures and their local
// processing, then one separate normal opening/finish. No other family borrows it.
pub const RETAIL_BUSINESS_SECONDS: u64 =
    (26 + 12) * (15 + 70 + 15) + 4 * (2 * 15 + 2 * 15 + 2 * 15 + 20) + 4 * 60;
pub const RETAIL_REOPEN_SECONDS: u64 =
    (250 + 3 * 15 + 250 + 250 + 2 * 15 + 70) + (250 + 70 + 250 + 70 + 60);
pub const RETAIL_BASE_UI_WORK_SECONDS: u64 = 2_615;
pub const RETAIL_WORK_SECONDS: u64 = RETAIL_BASE_UI_WORK_SECONDS
    + FAMILY_PM_PERMISSION_SECONDS
    + FAMILY_APPOPS_SECONDS
    + FAMILY_ACCOUNT_SECONDS
    + RETAIL_BUSINESS_SECONDS
    + RETAIL_REOPEN_SECONDS;
pub const RETAIL_CASE_SECONDS: u64 = INSPECT_SECONDS + RETAIL_WORK_SECONDS;
pub const FAMILY_SECONDS: u64 = (FAMILY_CASE_COUNT - RETAIL_CASE_COUNT) as u64
    * FAMILY_CASE_SECONDS
    + RETAIL_CASE_COUNT as u64 * RETAIL_CASE_SECONDS;
// The supplementary real single-shutter/reopen case retains the old Camera leaf.
// Its normal pre-inspection is separate from the two-session factory's window.
pub const CAMERA_PHOTO_WORK_SECONDS: u64 = 4_040;
pub const CAMERA_PHOTO_CASE_SECONDS: u64 = INSPECT_SECONDS + CAMERA_PHOTO_WORK_SECONDS;
// The fixed Settings permission/account/negative-lookup case adds no grants.
pub const SETTINGS_PERMISSION_WORK_SECONDS: u64 = 6_050;
pub const SETTINGS_PERMISSION_CASE_SECONDS: u64 =
    INSPECT_SECONDS + SETTINGS_PERMISSION_WORK_SECONDS;
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
    + FAMILY_SECONDS
    + PHOTO_CASE_COUNT as u64 * CAMERA_PHOTO_CASE_SECONDS
    + SETTINGS_CASE_COUNT as u64 * SETTINGS_PERMISSION_CASE_SECONDS;
pub const RETIREMENT_SECONDS: u64 = 180;
pub const SERVICE_SECONDS: u64 = SUITE_SECONDS + RETIREMENT_SECONDS;
pub const NOFILE_LIMIT: u64 = 32_768;
