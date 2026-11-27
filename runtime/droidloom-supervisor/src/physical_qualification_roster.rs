//! Exact normal gate roster, compared to the installed same-ELF producer.
//! Source: physical_gate_roster.rs H57a1158, registry27878/0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8.
pub(super) const REGISTRY_SHA: &str =
    "0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8";
pub(super) const COMMON: &[&str] = &[
    "data_permissions",
    "identity",
    "lifecycle",
    "release_scope",
    "stability",
    "ui_observation",
];
pub(super) const PACKAGES: &[(&str, &[&str])] = &[
    (
        "com.Hyatt.hyt",
        &[
            "hotel.account",
            "hotel.details",
            "hotel.query",
            "hotel.return",
        ],
    ),
    (
        "com.MobileTicket",
        &[
            "train.account",
            "train.details",
            "train.query",
            "train.return",
        ],
    ),
    (
        "com.amazon.mShop.android.shopping",
        &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
    ),
    (
        "com.android.calendar",
        &[
            "calendar.edit",
            "calendar.persist",
            "calendar.reminder",
            "calendar.sync",
        ],
    ),
    (
        "com.android.camera2",
        &[
            "camera.persist",
            "camera.photo",
            "camera.preview",
            "camera.recovery",
            "camera.video",
        ],
    ),
    (
        "com.android.contacts",
        &[
            "contacts.cleanup",
            "contacts.edit",
            "contacts.persist",
            "contacts.sync",
        ],
    ),
    (
        "com.android.deskclock",
        &["clock.alarm", "clock.persist", "clock.timer"],
    ),
    (
        "com.android.dialer",
        &["dialer.call", "dialer.history", "dialer.ui"],
    ),
    (
        "com.android.documentsui",
        &["documents.io", "documents.persist", "documents.provider"],
    ),
    (
        "com.android.gallery3d",
        &["gallery.enumeration", "gallery.open", "gallery.persist"],
    ),
    (
        "com.android.messaging",
        &[
            "messaging.compose",
            "messaging.delivery",
            "messaging.persist",
        ],
    ),
    (
        "com.android.quicksearchbox",
        &["search.failure", "search.open", "search.query"],
    ),
    (
        "com.android.settings",
        &[
            "settings.pages",
            "settings.permissions",
            "settings.roundtrip",
        ],
    ),
    (
        "com.bestbuy.android",
        &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
    ),
    (
        "com.ehi.national.mobile",
        &[
            "rental.account",
            "rental.details",
            "rental.query",
            "rental.return",
        ],
    ),
    (
        "com.google.android.gms",
        &["gms.consumer", "gms.failure", "gms.identity"],
    ),
    (
        "com.hertz.android.digital",
        &[
            "rental.account",
            "rental.details",
            "rental.query",
            "rental.return",
        ],
    ),
    (
        "com.hilton.android.hhonors",
        &[
            "hotel.account",
            "hotel.details",
            "hotel.query",
            "hotel.return",
        ],
    ),
    (
        "com.ihg.apps.android",
        &[
            "hotel.account",
            "hotel.details",
            "hotel.query",
            "hotel.return",
        ],
    ),
    (
        "com.jingdong.app.mall",
        &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
    ),
    (
        "com.lianjia.beike",
        &["housing.details", "housing.navigation", "housing.query"],
    ),
    (
        "com.marriott.mrt",
        &[
            "hotel.account",
            "hotel.details",
            "hotel.query",
            "hotel.return",
        ],
    ),
    (
        "com.rytong.airchina",
        &[
            "flight.account",
            "flight.details",
            "flight.query",
            "flight.return",
        ],
    ),
    (
        "com.rytong.ceair",
        &[
            "flight.account",
            "flight.details",
            "flight.query",
            "flight.return",
        ],
    ),
    (
        "com.sankuai.meituan.takeoutnew",
        &[
            "delivery.detail",
            "delivery.order_scope",
            "delivery.query",
            "delivery.start",
        ],
    ),
    (
        "com.sdu.didi.psnger",
        &["ride.lifecycle", "ride.location", "ride.quote"],
    ),
    (
        "com.ss.android.ugc.aweme",
        &[
            "video.controls",
            "video.playback",
            "video.reopen",
            "video.search",
        ],
    ),
    (
        "com.szzc",
        &[
            "rental.account",
            "rental.details",
            "rental.query",
            "rental.return",
        ],
    ),
    (
        "com.taobao.taobao",
        &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
    ),
    (
        "com.tencent.mm",
        &[
            "messaging.compose",
            "messaging.delivery",
            "messaging.persist",
        ],
    ),
    (
        "com.united.mobile.android",
        &[
            "flight.account",
            "flight.details",
            "flight.query",
            "flight.return",
        ],
    ),
    (
        "com.xunmeng.pinduoduo",
        &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
    ),
    (
        "com.zhubajie.client",
        &["services.account", "services.detail", "services.query"],
    ),
    (
        "com.zillow.android.streeteasy",
        &["housing.details", "housing.navigation", "housing.query"],
    ),
    (
        "ctrip.android.view",
        &["travel.account", "travel.details", "travel.query"],
    ),
    (
        "jp.co.ana.android.tabidachi",
        &[
            "flight.account",
            "flight.details",
            "flight.query",
            "flight.return",
        ],
    ),
    (
        "org.fcitx.fcitx5.android",
        &["ime.composition", "ime.editing", "ime.lifecycle"],
    ),
    (
        "org.mozilla.firefox",
        &[
            "browser.document",
            "browser.external_https",
            "browser.media",
            "browser.recovery",
            "browser.return",
        ],
    ),
    (
        "tv.danmaku.bili",
        &[
            "video.controls",
            "video.playback",
            "video.reopen",
            "video.search",
        ],
    ),
];

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeSet;
    #[test]
    fn physical_qualification_retains_exact_full_39_and_377_beyond_native_cases() {
        assert_eq!(PACKAGES.len(), 39);
        let mut packages = BTreeSet::new();
        let mut count = 0;
        for (package, business) in PACKAGES {
            assert!(packages.insert(*package));
            let gates: BTreeSet<_> = COMMON.iter().chain(business.iter()).collect();
            assert_eq!(gates.len(), COMMON.len() + business.len());
            count += gates.len();
        }
        assert_eq!(count, 377);
        assert_eq!(COMMON.len(), 6);
        use super::super::super::{CASE_COUNT, FAMILY_CASE_COUNT, NATIVE_CASE_COUNT, QualificationCase};
        assert_eq!(CASE_COUNT, NATIVE_CASE_COUNT + FAMILY_CASE_COUNT);
        let families = PACKAGES.iter()
            .filter(|(package, _)| QualificationCase::for_family(package).is_ok()).count();
        assert_eq!(families, FAMILY_CASE_COUNT);
        let all_cases = (0..CASE_COUNT).map(|ordinal| QualificationCase::from_ordinal(ordinal as u8).unwrap()).collect::<Vec<_>>();
        assert_eq!(all_cases.iter().filter(|case| case.native_route().is_some()).count(), NATIVE_CASE_COUNT);
        let covered: BTreeSet<_> = all_cases.iter().map(|case| case.package()).collect();
        assert_eq!(covered, packages);
        // Forty-five observed histories are still not any of the 377 opaque gate facts.
    }
}
