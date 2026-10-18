// SPDX-License-Identifier: MPL-2.0

//! CPU bandwidth configuration parsing before the owner mutation lock.

/// A parsed `cpu.max` update in microseconds.
#[derive(Debug, Eq, PartialEq)]
pub(super) struct CpuMaxConfig {
    pub(super) quota_usec: u64,
    pub(super) period_usec: Option<u64>,
}

impl CpuMaxConfig {
    /// Parses the cgroup bandwidth limit without reading or changing its owner.
    pub(super) fn parse(content: &str) -> Result<Self, ()> {
        // The cgroup v2 CPU bandwidth limit is `$MAX $PERIOD`, where `$MAX` is
        // either `max` or at least 1ms and `$PERIOD` is in the range 1ms..=1s.
        // A single quota leaves the current period unchanged.
        //
        // Reference: <https://docs.kernel.org/admin-guide/cgroup-v2.html#cpu-interface-files>
        const MIN_QUOTA_USEC: u64 = 1_000;
        const MIN_PERIOD_USEC: u64 = 1_000;
        const MAX_PERIOD_USEC: u64 = 1_000_000;

        let mut tokens = content.split_whitespace();
        let quota_token = tokens.next().ok_or(())?;
        let period_token = tokens.next();
        if tokens.next().is_some() {
            return Err(());
        }

        let quota_usec = if quota_token == "max" {
            u64::MAX
        } else if let Ok(quota_usec) = quota_token.parse::<u64>() {
            if quota_usec < MIN_QUOTA_USEC {
                return Err(());
            }
            quota_usec
        } else {
            return Err(());
        };

        // Only omission preserves the current period. An explicitly supplied
        // malformed or overflowing period must not install a different quota.
        let period_usec = if let Some(period_token) = period_token {
            let period_usec = period_token.parse::<u64>().map_err(|_| ())?;
            if !(MIN_PERIOD_USEC..=MAX_PERIOD_USEC).contains(&period_usec) {
                return Err(());
            }
            Some(period_usec)
        } else {
            None
        };

        Ok(Self {
            quota_usec,
            period_usec,
        })
    }
}

#[cfg(any(test, ktest))]
mod tests {
    #[cfg(ktest)]
    use ostd::prelude::ktest;

    use super::CpuMaxConfig;

    #[cfg_attr(ktest, ktest)]
    #[cfg_attr(not(ktest), test)]
    fn single_quota_preserves_the_current_period() {
        for (input, quota_usec) in [("1000", 1_000), (" max\n", u64::MAX)] {
            assert_eq!(
                CpuMaxConfig::parse(input),
                Ok(CpuMaxConfig {
                    quota_usec,
                    period_usec: None,
                })
            );
        }
    }

    #[cfg_attr(ktest, ktest)]
    #[cfg_attr(not(ktest), test)]
    fn accepts_valid_quota_period_and_range_boundaries() {
        for (input, quota_usec, period_usec) in [
            ("1000 1000", 1_000, 1_000),
            ("10000 100000", 10_000, 100_000),
            ("max 1000000", u64::MAX, 1_000_000),
            ("\t2000  100000\n", 2_000, 100_000),
            ("18446744073709551615 1000", u64::MAX, 1_000),
        ] {
            assert_eq!(
                CpuMaxConfig::parse(input),
                Ok(CpuMaxConfig {
                    quota_usec,
                    period_usec: Some(period_usec),
                })
            );
        }
    }

    #[cfg_attr(ktest, ktest)]
    #[cfg_attr(not(ktest), test)]
    fn rejects_invalid_or_overflowing_quota() {
        for input in [
            "",
            " \n",
            "0",
            "999",
            "nope",
            "-1000",
            "18446744073709551616",
        ] {
            assert!(CpuMaxConfig::parse(input).is_err(), "accepted {input:?}");
        }
    }

    #[cfg_attr(ktest, ktest)]
    #[cfg_attr(not(ktest), test)]
    fn rejects_numeric_period_outside_the_supported_range() {
        for input in ["1000 0", "1000 999", "max 1000001"] {
            assert!(CpuMaxConfig::parse(input).is_err(), "accepted {input:?}");
        }
    }

    #[cfg_attr(ktest, ktest)]
    #[cfg_attr(not(ktest), test)]
    fn rejects_explicit_invalid_period_instead_of_preserving_the_old_period() {
        for input in [
            "1000 nope",
            "max nope",
            "1000 -100000",
            "1000 +",
            "1000 1_000",
        ] {
            assert!(CpuMaxConfig::parse(input).is_err(), "accepted {input:?}");
        }
    }

    #[cfg_attr(ktest, ktest)]
    #[cfg_attr(not(ktest), test)]
    fn rejects_overflowing_period_instead_of_preserving_the_old_period() {
        for input in [
            "1000 18446744073709551616",
            "max 99999999999999999999999999999",
        ] {
            assert!(CpuMaxConfig::parse(input).is_err(), "accepted {input:?}");
        }
    }

    #[cfg_attr(ktest, ktest)]
    #[cfg_attr(not(ktest), test)]
    fn rejects_extra_fields_instead_of_applying_a_valid_prefix() {
        for input in ["1000 100000 junk", "max 100000 1", "1000 100000 max 123"] {
            assert!(CpuMaxConfig::parse(input).is_err(), "accepted {input:?}");
        }
    }
}
