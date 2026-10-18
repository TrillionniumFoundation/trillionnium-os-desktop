//! UI observation age, not a lifecycle or authority decision.
//! Callers supply both clocks; reading a queued response does not renew its sample.

use std::time::Duration;

pub const MAX_OBSERVATION_AGE: Duration = Duration::from_secs(7);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FreshnessFailure {
    SampleMissing,
    ReceiptTimeInvalid,
    ReceiptExpired,
    SampleTimeInvalid,
    SampleExpired,
}

/// The 7,000 ms boundary is inclusive. Missing/future clocks are unknown;
/// a changed clock must never be saturated into a zero-age success.
pub fn freshness_failure(
    sampled_unix_ms: Option<u64>,
    received_age: Option<Duration>,
    now_unix_ms: u64,
) -> Option<FreshnessFailure> {
    let Some(sampled) = sampled_unix_ms else {
        return Some(FreshnessFailure::SampleMissing);
    };
    let Some(received_age) = received_age else {
        return Some(FreshnessFailure::ReceiptTimeInvalid);
    };
    if received_age > MAX_OBSERVATION_AGE {
        return Some(FreshnessFailure::ReceiptExpired);
    }
    let Some(sample_age_ms) = now_unix_ms.checked_sub(sampled) else {
        return Some(FreshnessFailure::SampleTimeInvalid);
    };
    if sample_age_ms > MAX_OBSERVATION_AGE.as_millis() as u64 {
        return Some(FreshnessFailure::SampleExpired);
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn both_clocks_are_bounded_without_rejuvenating_queued_samples() {
        let ms = |n| Some(Duration::from_millis(n));
        assert_eq!(freshness_failure(Some(10_000), ms(7_000), 17_000), None);
        assert_eq!(
            freshness_failure(Some(10_000), ms(0), 17_001),
            Some(FreshnessFailure::SampleExpired)
        );
        assert_eq!(
            freshness_failure(Some(17_001), ms(7_001), 17_001),
            Some(FreshnessFailure::ReceiptExpired)
        );
        assert_eq!(
            freshness_failure(Some(18_000), ms(0), 17_001),
            Some(FreshnessFailure::SampleTimeInvalid)
        );
        assert_eq!(
            freshness_failure(Some(10_000), None, 10_000),
            Some(FreshnessFailure::ReceiptTimeInvalid)
        );
        assert_eq!(
            freshness_failure(None, ms(0), 10_000),
            Some(FreshnessFailure::SampleMissing)
        );
    }
}
