//! Bounded, complete user-0 PackageManager name/UID comparison.
//!
//! The normal fixed command is `cmd package list packages -U --user 0`.
//! Its grammar is checked against PackageManagerShellCommand in the actual
//! selected CP3A services.jar (25716529 bytes, SHA256
//! bc5d11f4f09ec079c5804a01008e8317a0854231502550acaff89aa9f1083a86).
//! A parsed table conveys no package, process, Main or private-data authority.
use super::{Result, reject, require};
use std::collections::BTreeMap;
use std::time::Instant;

// Preserve the normal fixed-query byte cap; never return a partial table.
pub(super) const OUTPUT_BYTES: usize = super::OUTPUT_LIMIT;
const MAX_PACKAGES: usize = 2048;
const MAX_LINE_BYTES: usize = 512;

pub(super) struct UserZeroPackageInventoryRows {
    records: BTreeMap<String, u32>,
}
impl UserZeroPackageInventoryRows {
    pub(super) fn records(&self) -> &BTreeMap<String, u32> {
        &self.records
    }
}

fn package_name(name: &str) -> bool {
    // The framework package is a legitimate single-component exception.
    name == "android"
        || (!name.is_empty()
            && name.len() <= 255
            && name.contains('.')
            && name.split('.').all(|part| {
                !part.is_empty() && part.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
            }))
}

pub(super) fn parse(text: &str, deadline: Instant) -> Result<UserZeroPackageInventoryRows> {
    crate::production_host_admission::check_observation_before(deadline)?;
    require(
        !text.is_empty()
            && text.len() <= OUTPUT_BYTES
            && text.ends_with('\n')
            && text.is_ascii()
            && !text.bytes().any(|b| b.is_ascii_control() && b != b'\n'),
        "user-0 package inventory output is empty, truncated, or malformed",
    )?;
    let mut records = BTreeMap::new();
    for line in text.lines() {
        crate::production_host_admission::check_observation_before(deadline)?;
        require(
            !line.is_empty() && line.len() <= MAX_LINE_BYTES && records.len() < MAX_PACKAGES,
            "user-0 package inventory line or table bound",
        )?;
        let line = line
            .strip_prefix("package:")
            .ok_or_else(|| reject("user-0 package inventory has a non-package row"))?;
        let (name, uid) = line
            .split_once(" uid:")
            .ok_or_else(|| reject("user-0 package inventory UID is absent"))?;
        require(package_name(name), "invalid user-0 package inventory name")?;
        let value: u32 = uid
            .parse()
            .map_err(|_| reject("invalid user-0 package inventory UID"))?;
        require(
            value < 100_000 && value.to_string() == uid,
            "user-0 package inventory UID is noncanonical or belongs to another user",
        )?;
        require(
            records.insert(name.to_owned(), value).is_none(),
            "duplicate user-0 package inventory name",
        )?;
    }
    require(!records.is_empty(), "user-0 package inventory is absent")?;
    crate::production_host_admission::check_observation_before(deadline)?;
    Ok(UserZeroPackageInventoryRows { records })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    fn end() -> Instant {
        Instant::now() + Duration::from_secs(5)
    }

    #[test]
    fn user_zero_package_inventory_keeps_the_complete_table_and_shared_uids() {
        let text = "package:org.example.z uid:10432\npackage:android uid:1000\n\
                    package:com.android.settings uid:1000\npackage:org.example.a uid:10111\n";
        let table = parse(text, end()).unwrap();
        assert_eq!(table.records().len(), 4);
        assert_eq!(table.records().get("android"), Some(&1000));
        assert_eq!(table.records().get("com.android.settings"), Some(&1000));
        assert_eq!(table.records().get("org.example.z"), Some(&10432));
        assert_eq!(table.records().get("org.example.a"), Some(&10111));
        // This complete inventory is deliberately not filtered to selected39.
        assert!(table.records().contains_key("org.example.z"));
    }

    #[test]
    fn user_zero_package_inventory_rejects_duplicate_names_even_with_same_uid() {
        for other_uid in [1000, 10001] {
            let text = format!("package:android uid:1000\npackage:android uid:{other_uid}\n");
            assert!(parse(&text, end()).is_err());
        }
    }

    #[test]
    fn user_zero_package_inventory_rejects_partial_extra_or_noncanonical_rows() {
        for text in [
            "",
            "package:android uid:1000",
            "package:android uid:1000\n\n",
            "package:android uid:1000\r\n",
            "package:android uid:1000\0\n",
            "package:android\tuid:1000\n",
            "package:android  uid:1000\n",
            " package:android uid:1000\n",
            "package:android uid:1000 \n",
            "package:android uid:1000 uid:1000\n",
            "package:android versionCode:37 uid:1000\n",
            "package:android uid:1000 versionCode:37\n",
            "package:android uid:1000\nError: binder transaction failed\n",
            "Success\n",
            "package:android\n",
            "package:android uid:\n",
        ] {
            assert!(parse(text, end()).is_err(), "{text:?}");
        }
    }

    #[test]
    fn user_zero_package_inventory_rejects_foreign_or_ambiguous_user_numbers() {
        for uid in [
            "100000",
            "101000",
            "4294967295",
            "4294967296",
            "-1",
            "+1000",
            "01000",
            "1.0",
        ] {
            assert!(
                parse(&format!("package:android uid:{uid}\n"), end()).is_err(),
                "{uid}"
            );
        }
        // Numeric values are comparisons only. The parser does not promote a
        // low system UID (including zero) into process or filesystem authority.
        for uid in [0, 1000, 2000, 10000, 99999] {
            assert_eq!(
                parse(&format!("package:android uid:{uid}\n"), end())
                    .unwrap()
                    .records()
                    .get("android"),
                Some(&uid)
            );
        }
    }

    #[test]
    fn user_zero_package_inventory_validates_every_package_name() {
        for name in [
            "a",
            "",
            ".com.example",
            "com.example.",
            "com..example",
            "com/example",
            "com.example:remote",
            "com.example bad",
            "com.example-bad",
            "com.éxample",
        ] {
            assert!(
                parse(&format!("package:{name} uid:10001\n"), end()).is_err(),
                "{name}"
            );
        }
        let name = format!("com.{}", "a".repeat(252));
        assert!(parse(&format!("package:{name} uid:10001\n"), end()).is_err());
        assert!(parse("package:com.Example_1.App uid:10001\n", end()).is_ok());
    }

    #[test]
    fn user_zero_package_inventory_honors_bounds_and_the_original_absolute_end() {
        assert!(parse("package:android uid:1000\n", Instant::now()).is_err());
        let mut body = String::new();
        for i in 0..MAX_PACKAGES {
            body.push_str(&format!("package:a.p{i} uid:1\n"));
        }
        assert_eq!(parse(&body, end()).unwrap().records().len(), MAX_PACKAGES);
        body.push_str("package:com.example.extra uid:10001\n");
        assert!(parse(&body, end()).is_err());
        assert!(parse(&format!("{}\n", "a".repeat(OUTPUT_BYTES)), end()).is_err());
        assert!(parse(&format!("{}\n", "a".repeat(MAX_LINE_BYTES + 1)), end()).is_err());
    }
}
