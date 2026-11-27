//! Source-owned complete roster for one physical qualification boot.
//! The reviewed registry bytes are comparison input; callers cannot select a
//! smaller package/gate set or replace the executable case sequence.
use super::leaf_routes::Route;

pub(super) const REGISTRY_BYTES: u64 = 27_878;
pub(super) const REGISTRY_SHA256: &str =
    "0b21f963898308b082f3808dd48165c1397badd1fa8a753c3a766e135b3cb3c8";
pub(super) const CURRENT_SELECTION_BYTES: u64 = 423_460;
pub(super) const CURRENT_SELECTION_SHA256: &str =
    "6964ddaba93445caf98ccfab4787254c8e2886fc9e3869ef20da7f615e81266c";
pub(super) const PACKAGE_COUNT: usize = 39;
pub(super) const GATE_COUNT: usize = 377;
pub(super) const COMMON: [&str; 6] = [
    "data_permissions",
    "identity",
    "lifecycle",
    "release_scope",
    "stability",
    "ui_observation",
];

pub(super) struct PackageGates {
    pub(super) package: &'static str,
    pub(super) profile: &'static str,
    pub(super) business: &'static [&'static str],
    pub(super) cases: &'static [Route],
}

// Source of this table: the exact normal r6 APP-RELEASE-GATES.json above,
// joined to its actual source-admitted SELECTED39 roster. Its other seven
// package definitions do not become selected applications.
pub(super) const PACKAGES: &[PackageGates] = &[
    PackageGates {
        package: "com.Hyatt.hyt",
        profile: "hotel",
        business: &[
            "hotel.account",
            "hotel.details",
            "hotel.query",
            "hotel.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.MobileTicket",
        profile: "train",
        business: &[
            "train.account",
            "train.details",
            "train.query",
            "train.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.amazon.mShop.android.shopping",
        profile: "retail",
        business: &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.android.calendar",
        profile: "calendar",
        business: &[
            "calendar.edit",
            "calendar.persist",
            "calendar.reminder",
            "calendar.sync",
        ],
        cases: &[Route::CalendarCore, Route::CalendarReminder],
    },
    PackageGates {
        package: "com.android.camera2",
        profile: "camera",
        business: &[
            "camera.persist",
            "camera.photo",
            "camera.preview",
            "camera.recovery",
            "camera.video",
        ],
        cases: &[Route::CameraPhoto],
    },
    PackageGates {
        package: "com.android.contacts",
        profile: "contacts",
        business: &[
            "contacts.cleanup",
            "contacts.edit",
            "contacts.persist",
            "contacts.sync",
        ],
        cases: &[Route::ContactsSearch],
    },
    PackageGates {
        package: "com.android.deskclock",
        profile: "clock",
        business: &["clock.alarm", "clock.persist", "clock.timer"],
        cases: &[Route::ClockTimerPair, Route::ClockAlarm],
    },
    PackageGates {
        package: "com.android.dialer",
        profile: "dialer",
        business: &["dialer.call", "dialer.history", "dialer.ui"],
        cases: &[],
    },
    PackageGates {
        package: "com.android.documentsui",
        profile: "documents",
        business: &["documents.io", "documents.persist", "documents.provider"],
        cases: &[Route::DocumentsSaf, Route::DocumentsSearchSort],
    },
    PackageGates {
        package: "com.android.gallery3d",
        profile: "gallery",
        business: &["gallery.enumeration", "gallery.open", "gallery.persist"],
        cases: &[
            Route::GalleryRotation,
            Route::GalleryVideo,
            Route::GallerySeek,
            Route::GalleryAlbum,
        ],
    },
    PackageGates {
        package: "com.android.messaging",
        profile: "messaging",
        business: &[
            "messaging.compose",
            "messaging.delivery",
            "messaging.persist",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.android.quicksearchbox",
        profile: "search",
        business: &["search.failure", "search.open", "search.query"],
        cases: &[],
    },
    PackageGates {
        package: "com.android.settings",
        profile: "settings",
        business: &[
            "settings.pages",
            "settings.permissions",
            "settings.roundtrip",
        ],
        cases: &[Route::SettingsSupportedPages],
    },
    PackageGates {
        package: "com.bestbuy.android",
        profile: "retail",
        business: &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.ehi.national.mobile",
        profile: "rental",
        business: &[
            "rental.account",
            "rental.details",
            "rental.query",
            "rental.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.google.android.gms",
        profile: "gms",
        business: &["gms.consumer", "gms.failure", "gms.identity"],
        cases: &[],
    },
    PackageGates {
        package: "com.hertz.android.digital",
        profile: "rental",
        business: &[
            "rental.account",
            "rental.details",
            "rental.query",
            "rental.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.hilton.android.hhonors",
        profile: "hotel",
        business: &[
            "hotel.account",
            "hotel.details",
            "hotel.query",
            "hotel.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.ihg.apps.android",
        profile: "hotel",
        business: &[
            "hotel.account",
            "hotel.details",
            "hotel.query",
            "hotel.return",
        ],
        cases: &[Route::IhgLondon],
    },
    PackageGates {
        package: "com.jingdong.app.mall",
        profile: "retail",
        business: &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.lianjia.beike",
        profile: "housing",
        business: &["housing.details", "housing.navigation", "housing.query"],
        cases: &[],
    },
    PackageGates {
        package: "com.marriott.mrt",
        profile: "hotel",
        business: &[
            "hotel.account",
            "hotel.details",
            "hotel.query",
            "hotel.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.rytong.airchina",
        profile: "flight",
        business: &[
            "flight.account",
            "flight.details",
            "flight.query",
            "flight.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.rytong.ceair",
        profile: "flight",
        business: &[
            "flight.account",
            "flight.details",
            "flight.query",
            "flight.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.sankuai.meituan.takeoutnew",
        profile: "delivery",
        business: &[
            "delivery.detail",
            "delivery.order_scope",
            "delivery.query",
            "delivery.start",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.sdu.didi.psnger",
        profile: "ride",
        business: &["ride.lifecycle", "ride.location", "ride.quote"],
        cases: &[],
    },
    PackageGates {
        package: "com.ss.android.ugc.aweme",
        profile: "video",
        business: &[
            "video.controls",
            "video.playback",
            "video.reopen",
            "video.search",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.szzc",
        profile: "rental",
        business: &[
            "rental.account",
            "rental.details",
            "rental.query",
            "rental.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.taobao.taobao",
        profile: "retail",
        business: &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.tencent.mm",
        profile: "messaging",
        business: &[
            "messaging.compose",
            "messaging.delivery",
            "messaging.persist",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.united.mobile.android",
        profile: "flight",
        business: &[
            "flight.account",
            "flight.details",
            "flight.query",
            "flight.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.xunmeng.pinduoduo",
        profile: "retail",
        business: &[
            "retail.account",
            "retail.detail",
            "retail.navigation",
            "retail.search",
        ],
        cases: &[],
    },
    PackageGates {
        package: "com.zhubajie.client",
        profile: "services",
        business: &["services.account", "services.detail", "services.query"],
        cases: &[],
    },
    PackageGates {
        package: "com.zillow.android.streeteasy",
        profile: "housing",
        business: &["housing.details", "housing.navigation", "housing.query"],
        cases: &[],
    },
    PackageGates {
        package: "ctrip.android.view",
        profile: "travel",
        business: &["travel.account", "travel.details", "travel.query"],
        cases: &[],
    },
    PackageGates {
        package: "jp.co.ana.android.tabidachi",
        profile: "flight",
        business: &[
            "flight.account",
            "flight.details",
            "flight.query",
            "flight.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "org.fcitx.fcitx5.android",
        profile: "ime",
        business: &["ime.composition", "ime.editing", "ime.lifecycle"],
        cases: &[],
    },
    PackageGates {
        package: "org.mozilla.firefox",
        profile: "browser",
        business: &[
            "browser.document",
            "browser.external_https",
            "browser.media",
            "browser.recovery",
            "browser.return",
        ],
        cases: &[],
    },
    PackageGates {
        package: "tv.danmaku.bili",
        profile: "video",
        business: &[
            "video.controls",
            "video.playback",
            "video.reopen",
            "video.search",
        ],
        cases: &[],
    },
];

pub(super) fn package(name: &str) -> Result<&'static PackageGates, String> {
    PACKAGES
        .iter()
        .find(|row| row.package == name)
        .ok_or_else(|| format!("package {name} is outside the reviewed complete physical roster"))
}

pub(super) fn required(row: &PackageGates) -> std::collections::BTreeSet<&'static str> {
    COMMON
        .into_iter()
        .chain(row.business.iter().copied())
        .collect()
}
