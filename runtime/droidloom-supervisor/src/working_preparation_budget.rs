//! Fixed preparation work before the physical suite. No caller selects a
//! package, command count, interval, or deadline from this comparison ledger.
//!
//! Each normal factory retains its original finite end. The whole owner starts
//! once before Main/preparation; unused preparation does not enlarge a case.
pub const BOOTSTRAP_SECONDS: u64 = 120;
pub const MAIN_SECONDS: u64 = 70;
pub const CATALOG_SECONDS: u64 = 250;
pub const ORDINARY_PACKAGE_COUNT: u64 = 40;
pub const PACKAGE_SECONDS: u64 = 250;
pub const GALLERY_PACKAGE_SECONDS: u64 = 330;
pub const SOURCE_AND_PLAN_SECONDS: u64 = 120;
pub const NATIVE_BASELINE_COUNT: u64 = 14;
pub const BASELINE_STEP_SECONDS: u64 = 1200;
pub const IDENTITY_ROLE_COUNT: u64 = 23;
pub const APK_BEGIN_SECONDS: u64 = 130;
pub const APK_FINISH_SECONDS: u64 = 140;
pub const HOST_COMMAND_SECONDS: u64 = 1200;
pub const STEP_SOURCE_SECONDS: u64 = 120;
pub const IDENTITY_STEP_SECONDS: u64 = PACKAGE_SECONDS
    + APK_BEGIN_SECONDS + HOST_COMMAND_SECONDS + APK_FINISH_SECONDS
    + PACKAGE_SECONDS + MAIN_SECONDS + STEP_SOURCE_SECONDS;
pub const PLAN_STEP_COUNT: u64 = 17;
pub const PLAN_STEP_SECONDS: u64 =
    HOST_COMMAND_SECONDS + PACKAGE_SECONDS + MAIN_SECONDS + STEP_SOURCE_SECONDS;
pub const IHG_MODE_COUNT: u64 = 6;
pub const IHG_MODE_SECONDS: u64 = 1800;
pub const GALLERY_PLAN_COUNT: u64 = 4;
pub const GALLERY_PLAN_SECONDS: u64 = 120;
pub const RUNTIME_BINDING_SECONDS: u64 = BOOTSTRAP_SECONDS
    + MAIN_SECONDS + CATALOG_SECONDS
    + ORDINARY_PACKAGE_COUNT * PACKAGE_SECONDS + GALLERY_PACKAGE_SECONDS
    + MAIN_SECONDS + MAIN_SECONDS + SOURCE_AND_PLAN_SECONDS;
// Self-contained constants: the normal cold fixture includes this same source.
pub const ORIGINAL_APK_CAPTURE_SECONDS: u64 = 600;
pub const ORIGINAL_APK_PACKAGE_SECONDS: u64 = 120 + 120 + 2 * 70 + 110 + 70;
pub const ORIGINAL_INSTALL_SECONDS: u64 = ORIGINAL_APK_CAPTURE_SECONDS
    + ORDINARY_PACKAGE_COUNT * ORIGINAL_APK_PACKAGE_SECONDS;
pub const WORK_SECONDS: u64 = ORIGINAL_INSTALL_SECONDS + RUNTIME_BINDING_SECONDS
    + NATIVE_BASELINE_COUNT * BASELINE_STEP_SECONDS
    + IDENTITY_ROLE_COUNT * IDENTITY_STEP_SECONDS
    + PLAN_STEP_COUNT * PLAN_STEP_SECONDS
    + IHG_MODE_COUNT * IHG_MODE_SECONDS
    + GALLERY_PLAN_COUNT * GALLERY_PLAN_SECONDS;
pub const RETIREMENT_SECONDS: u64 = 180;
pub const TOTAL_SECONDS: u64 = WORK_SECONDS + RETIREMENT_SECONDS;

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preparation_has_separate_original_factory_and_retirement_windows() {
        assert_eq!(RUNTIME_BINDING_SECONDS, 11_030);
        assert_eq!(IDENTITY_STEP_SECONDS, 2160);
        assert_eq!(PLAN_STEP_SECONDS, 1640);
        assert!(IDENTITY_STEP_SECONDS < 3000);
        assert_eq!(ORIGINAL_INSTALL_SECONDS, 23_000);
        assert_eq!(WORK_SECONDS, 139_670);
        assert_eq!(TOTAL_SECONDS, 139_850);
        assert_eq!(HOST_COMMAND_SECONDS, 1200);
        assert_eq!(IHG_MODE_SECONDS, 1800);
    }
}
