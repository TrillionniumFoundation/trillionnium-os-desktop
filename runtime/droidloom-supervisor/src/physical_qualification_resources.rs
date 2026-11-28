//! Whole physical-suite descriptor accounting. These are capacity bounds, not
//! execution authority. Actual input owners enforce their respective finite caps.
//! Retained native engine PIDFDs and source/case OFDs are not closed to make a
//! family-only resource estimate appear sufficient.
pub const NATIVE_ENGINE_OBSERVATIONS: usize = 4096;
pub const UI_JOURNAL_MEMBERS: usize = 4096;
pub const SOURCE_INPUT_DESCRIPTORS: usize = 256;
pub const CASE_INPUT_DESCRIPTORS: usize = 256;
pub const PLAN_DOCUMENTS: usize = 128;
pub const PLAN_DOCUMENT_DESCRIPTORS: usize = 32;
pub const SOURCE_CHAIN_DESCRIPTORS: usize = 6; // fixed four ancestors + / + file
pub const FAMILY_JOURNAL_DESCRIPTORS: usize = 32_800 + 30_288 + 2_912;
// Reviewed maximal family case: four UI journal roots (5 each), four
// engine PIDFDs, two permission journal roots (5 each), twelve permission/
// AppOps/account PIDFDs, one 26-FD resource fence, two exit observations,
// four common and forty business scoped-image owners (2 FDs each), the
// original APK interval peer and the outer pre-PM PIDFD. IdentityObservation
// and NativeInspectionPeer have only comparison values, with no descriptors.
// Each image owner holds its own PNG and cloned directory even when the
// finished journal separately retains PNG/comparison members. Count both.
// The family common bound already includes four original pixel descriptors;
// counting all eight here conservatively duplicates four, without dropping
// live owners. The finite 192 bound leaves 28 descriptors above reviewed 164.
pub const MAX_BUSINESS_SCOPED_CAPTURES: usize = 40;
pub const REVIEWED_FAMILY_AUX_DESCRIPTORS: usize =
    4 * 5 + 4 + 2 * 5 + 2 * 6 + 26 + 2 + 4 * 2
        + MAX_BUSINESS_SCOPED_CAPTURES * 2 + 1 + 1;
pub const CASE_AUX_DESCRIPTORS: usize = 192;
// One source witness/parent/Boot, control peer, channel, published material
// documents, plan root, and fixed inherited standard descriptors.
pub const SHARED_DESCRIPTORS: usize = 512;
// Temporary directory/name bookends and one in-flight normal RPC/source
// acquisition. Each Inputs/CaseInputs owner separately enforces <=256.
pub const TRANSIENT_DESCRIPTORS: usize = 1024;
pub const fn retained_and_transient_bound(native_cases: usize, cases: usize) -> usize {
    let native_intervals = native_cases + 1; // Clock pair retains two intervals
    native_intervals * NATIVE_ENGINE_OBSERVATIONS
        + (native_cases + 1) * (SOURCE_INPUT_DESCRIPTORS + 2 * SOURCE_CHAIN_DESCRIPTORS + 1)
        // Clock also retains its independent pair-request CaseInputs.
        + (native_cases + 2) * CASE_INPUT_DESCRIPTORS
        + PLAN_DOCUMENTS * PLAN_DOCUMENT_DESCRIPTORS
        + FAMILY_JOURNAL_DESCRIPTORS
        + 3 * UI_JOURNAL_MEMBERS // Camera first/reopen and Settings
        + cases * CASE_AUX_DESCRIPTORS
        + SHARED_DESCRIPTORS
        + TRANSIENT_DESCRIPTORS
}
pub const fn nofile_limit(native_cases: usize, cases: usize) -> u64 {
    retained_and_transient_bound(native_cases, cases).next_power_of_two() as u64
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn whole_suite_bound_includes_native_pidfds_and_minimal_power_of_two_limit() {
        let peak = retained_and_transient_bound(14, 49);
        assert_eq!(peak, 162_899);
        assert_eq!(FAMILY_JOURNAL_DESCRIPTORS,66_000);
        assert_eq!(REVIEWED_FAMILY_AUX_DESCRIPTORS,164);
        assert_eq!(CASE_AUX_DESCRIPTORS-REVIEWED_FAMILY_AUX_DESCRIPTORS,28);
        let limit = nofile_limit(14, 49);
        assert_eq!(limit, 262_144);
        assert!(FAMILY_JOURNAL_DESCRIPTORS > 32_768);
        assert!(15 * NATIVE_ENGINE_OBSERVATIONS > 32_768);
        assert!(peak as u64 <= limit && peak as u64 > limit / 2);
    }
}
