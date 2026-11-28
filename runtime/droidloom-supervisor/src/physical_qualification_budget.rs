//! One source-owned time/resource contract shared by the normal supervisor
//! and the independent cold fixture. This file has no crate dependencies.
//! It authorizes no action; actual factories and the same original deadline
//! remain required for every case and for the final 41/401 Complete.
pub const NATIVE_CASE_COUNT: usize = 14;
pub const FAMILY_CASE_COUNT: usize = 33;
pub const PHOTO_CASE_COUNT: usize = 1;
pub const SETTINGS_CASE_COUNT: usize = 1;
pub const CASE_COUNT: usize = NATIVE_CASE_COUNT + FAMILY_CASE_COUNT + PHOTO_CASE_COUNT + SETTINGS_CASE_COUNT;
pub const SOURCE_AND_CAPTURE_SECONDS: u64 = 120;
pub const MAIN_SECONDS: u64 = 70;
pub const INSPECT_SECONDS: u64 = 250;
// Original Gallery InspectApplication transport is 330 s (300 s service
// plus its original retirement/response allowance), with no extra RPC.
pub const GALLERY_INSPECT_SECONDS: u64 = 330;
// Six late-born fixture intervals share the existing normal factory limits.
// Source capture on both sides is separately bounded; the independent payload
// creator has 120 s plus its 3 s reap reserve. Each PM install/remove command
// retains 110 s. Complete helper inspection retains its normal 240 s cap.
pub const NATIVE_FIXTURE_BEGIN_SECONDS: u64 = 2 * SOURCE_AND_CAPTURE_SECONDS
    + 120 + 3 + 2 * MAIN_SECONDS + 2 * 30 + 8 + 3 * 110 + 240;
pub const NATIVE_FIXTURE_GUARD_SECONDS: u64 = 2 * MAIN_SECONDS + 2 * 30 + 8 + 240;
pub const NATIVE_FIXTURE_RETIRE_SECONDS: u64 = NATIVE_FIXTURE_GUARD_SECONDS + 110 + 8;
pub const NATIVE_FIXTURE_ADDITIONAL_SECONDS: u64 = NATIVE_FIXTURE_BEGIN_SECONDS + NATIVE_FIXTURE_RETIRE_SECONDS;
pub const NATIVE_DOCUMENTS_WORK_SECONDS: u64 = 1200 + NATIVE_FIXTURE_ADDITIONAL_SECONDS;
pub const NATIVE_GALLERY_WORK_SECONDS: u64 = 1530 + NATIVE_FIXTURE_ADDITIONAL_SECONDS;
// The standalone Gallery controller also contains its complete normal PM/Main
// pre/post checks and original APK custody. Use the same largest actual route.
pub const NATIVE_GALLERY_CONTROLLER_SECONDS: u64 = NATIVE_CASE_WINDOWS[8];
// Fixed complete source roles for the fourteen existing native rows. The Clock
// pair has two separate intervals, each containing its same two fixed roles.
pub const NATIVE_APK_GROUP_ROLES: [u64; NATIVE_CASE_COUNT] =
    [3, 3, 3, 3, 2, 2, 3, 3, 3, 2, 2, 2, 2, 2];
pub const fn native_apk_begin_seconds(ordinal: usize) -> u64 {
    70 * NATIVE_APK_GROUP_ROLES[ordinal] + 60
}
pub const fn native_apk_finish_seconds(ordinal: usize) -> u64 {
    70 * NATIVE_APK_GROUP_ROLES[ordinal] + 70
}
pub const fn native_apk_interval_seconds(ordinal: usize) -> u64 {
    native_apk_begin_seconds(ordinal) + native_apk_finish_seconds(ordinal)
}
pub const FAMILY_UI_WORK_SECONDS: u64 = 6_490;
// PM, AppOps and registered-account samples enclose each actual family UI case.
// They are partial preservation evidence, not full data or credential acceptance.
pub const FAMILY_PM_PERMISSION_SECONDS: u64 = 2 * 70;
pub const FAMILY_APPOPS_SECONDS: u64 = 2 * 70;
pub const FAMILY_ACCOUNT_SECONDS: u64 = 2 * 70;
pub const FAMILY_WORK_SECONDS: u64 = FAMILY_UI_WORK_SECONDS
    + FAMILY_PM_PERMISSION_SECONDS + FAMILY_APPOPS_SECONDS + FAMILY_ACCOUNT_SECONDS;
pub const FAMILY_CASE_SECONDS: u64 = INSPECT_SECONDS + FAMILY_WORK_SECONDS;
pub const RETAIL_CASE_COUNT: usize = 5;
// These five fixed packages keep the complete common pair. Their business
// observer adds two distinct normal sessions, source-bounded retail requests,
// four scoped captures, and a separate six-query permission/account window.
pub const RETAIL_BUSINESS_SECONDS: u64 =
    (26 + 12) * (15 + 70 + 15) + 4 * (2 * 15 + 2 * 15 + 2 * 15 + 20) + 4 * 60;
pub const RETAIL_SESSION_SECONDS: u64 = 2 * (
    (250 + 3 * 15 + 250 + 250 + 2 * 15 + 70) + (250 + 70 + 250 + 70 + 60));
pub const RETAIL_PERMISSION_SECONDS: u64 = 2 * (70 + 70 + 70);
pub const RETAIL_ADDITIONAL_SECONDS: u64 = RETAIL_BUSINESS_SECONDS
    + RETAIL_SESSION_SECONDS + RETAIL_PERMISSION_SECONDS;
pub const RETAIL_WORK_SECONDS: u64 = FAMILY_WORK_SECONDS + RETAIL_ADDITIONAL_SECONDS;
pub const RETAIL_CASE_SECONDS: u64 = INSPECT_SECONDS + RETAIL_WORK_SECONDS;
// Toutiao keeps the whole original common pair. The separate public news
// executor has 48+6 bounded native requests, 8+1 decoded scoped captures,
// two normal sessions and an independent permission/account interval.
// Its three pending gates do not receive a pass from this source budget.
pub const NEWS_CASE_COUNT: usize = 1;
pub const NEWS_BUSINESS_SECONDS: u64 = (48 + 6) * (15 + 70 + 15)
    + (8 + 1) * (2 * 15 + 2 * 15 + 2 * 15 + 20 + 60);
pub const NEWS_ADDITIONAL_SECONDS: u64 = NEWS_BUSINESS_SECONDS
    + RETAIL_SESSION_SECONDS + RETAIL_PERMISSION_SECONDS;
pub const NEWS_WORK_SECONDS: u64 = FAMILY_WORK_SECONDS + NEWS_ADDITIONAL_SECONDS;
pub const NEWS_CASE_SECONDS: u64 = INSPECT_SECONDS + NEWS_WORK_SECONDS;
pub const FAMILY_SECONDS: u64 = (FAMILY_CASE_COUNT - RETAIL_CASE_COUNT - NEWS_CASE_COUNT) as u64
    * FAMILY_CASE_SECONDS + RETAIL_CASE_COUNT as u64 * RETAIL_CASE_SECONDS
    + NEWS_CASE_COUNT as u64 * NEWS_CASE_SECONDS;
// The supplementary real single-shutter/reopen case retains the old Camera leaf.
// Its normal pre-inspection is separate from the two-session factory's window.
// One intentional normal Photo0 preparation before the Camera business preimage.
pub const CAMERA_PHOTO_PREPARATION_SECONDS: u64 = 895;
pub const CAMERA_PHOTO_WORK_SECONDS: u64 = 4_040 + CAMERA_PHOTO_PREPARATION_SECONDS;
pub const CAMERA_PHOTO_CASE_SECONDS: u64 = INSPECT_SECONDS + CAMERA_PHOTO_WORK_SECONDS;
// The fixed Settings permission/account/negative-lookup case adds no grants.
pub const SETTINGS_PERMISSION_WORK_SECONDS: u64 = 6_050;
pub const SETTINGS_PERMISSION_CASE_SECONDS: u64 = INSPECT_SECONDS + SETTINGS_PERMISSION_WORK_SECONDS;
const fn native_ordinary_seconds(ordinal: usize, business: u64, inspect: u64) -> u64 {
    business + 2 * inspect + 2 * MAIN_SECONDS + SOURCE_AND_CAPTURE_SECONDS
        + native_apk_interval_seconds(ordinal)
}
pub const NATIVE_CASE_WINDOWS: [u64; NATIVE_CASE_COUNT] = [
    native_ordinary_seconds(0, 930, INSPECT_SECONDS),
    native_ordinary_seconds(1, 690, INSPECT_SECONDS),
    native_ordinary_seconds(2, 500, INSPECT_SECONDS),
    native_ordinary_seconds(3, 420, INSPECT_SECONDS),
    2 * 510 + 3 * INSPECT_SECONDS + 3 * MAIN_SECONDS + SOURCE_AND_CAPTURE_SECONDS
        + 2 * native_apk_interval_seconds(4),
    native_ordinary_seconds(5, 810, INSPECT_SECONDS),
    native_ordinary_seconds(6, NATIVE_DOCUMENTS_WORK_SECONDS, INSPECT_SECONDS),
    native_ordinary_seconds(7, NATIVE_DOCUMENTS_WORK_SECONDS, INSPECT_SECONDS),
    native_ordinary_seconds(8, NATIVE_GALLERY_WORK_SECONDS, GALLERY_INSPECT_SECONDS),
    native_ordinary_seconds(9, NATIVE_GALLERY_WORK_SECONDS, GALLERY_INSPECT_SECONDS),
    native_ordinary_seconds(10, NATIVE_GALLERY_WORK_SECONDS, GALLERY_INSPECT_SECONDS),
    native_ordinary_seconds(11, NATIVE_GALLERY_WORK_SECONDS, GALLERY_INSPECT_SECONDS),
    native_ordinary_seconds(12, 900, INSPECT_SECONDS),
    native_ordinary_seconds(13, 680, INSPECT_SECONDS),
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
// Each of the thirty-three family cases has one 250-second inspection.
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
