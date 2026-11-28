//! Complete original APK source cohort for the twelve public travel cases.
//! Split filenames are observed from the real PM subject, never guessed from
//! the source archive. Whole-byte membership and uniqueness remain exact.
use super::Kind;
use droidloom_supervisor::control::application_probe::ApplicationInspection;
use std::collections::BTreeSet;
pub(super) const SELECTION_SHA256: &str =
    "4abd5c5d0a8ac89e739b2ba6dd508435a1d355b9ce975ba5ceacb50c1ee4a4a0";
pub(super) struct ApkSource {
    pub(super) base: bool,
    pub(super) bytes: u64,
    pub(super) sha256: &'static str,
}
pub(super) struct Source {
    pub(super) package: &'static str,
    pub(super) profile: &'static str,
    pub(super) version: u64,
    pub(super) routes: &'static [Kind],
    pub(super) apks: &'static [ApkSource],
}
pub(super) const SOURCES: &[Source] = &[
    Source {
        package: "com.Hyatt.hyt",
        profile: "hotel",
        version: 26111078,
        routes: &[Kind::Hotel],
        apks: &[
            ApkSource {
                base: true,
                bytes: 139558005,
                sha256: "54a149900ca20516b476932b8921f8e4e4f08c3927896ef5686d78f920028e9d",
            },
            ApkSource {
                base: false,
                bytes: 1200874,
                sha256: "68a0ea963323231a15d2920ed4dbf45cf5f1315908b7f1ceb26bfe5a6012e4a0",
            },
            ApkSource {
                base: false,
                bytes: 654090,
                sha256: "966087663b904b2be84cbe6835fc7ad0c6ea419c4c5a57e878071c183e3ea7b6",
            },
        ],
    },
    Source {
        package: "com.MobileTicket",
        profile: "train",
        version: 280,
        routes: &[Kind::Train],
        apks: &[ApkSource {
            base: true,
            bytes: 179817557,
            sha256: "f817658541a12bc4405b47ff68d457dca5462ab0bc2ad4471d9021485a0fe83a",
        }],
    },
    Source {
        package: "com.ehi.national.mobile",
        profile: "rental",
        version: 9403,
        routes: &[Kind::Rental],
        apks: &[
            ApkSource {
                base: true,
                bytes: 59416960,
                sha256: "78fc62db288612350a2c3c5b990dbd3dfd3d1acc9fcf55bf605cf7cebba7e637",
            },
            ApkSource {
                base: false,
                bytes: 70041,
                sha256: "1297bbcfae6c88510cb24c7feedc207ed0ef21199860b429abd8910f617519e1",
            },
            ApkSource {
                base: false,
                bytes: 31435286,
                sha256: "dce80c9358549ae86eca557f9d9e2cd3dcb86fec25dc2f95b94898066abc1573",
            },
            ApkSource {
                base: false,
                bytes: 107320,
                sha256: "96020c5b19c2384cf4e20c0ccec6f4541170a72643b825472053ef8918c5d19b",
            },
        ],
    },
    Source {
        package: "com.hertz.android.digital",
        profile: "rental",
        version: 1393,
        routes: &[Kind::Rental],
        apks: &[
            ApkSource {
                base: true,
                bytes: 92139405,
                sha256: "f3c308a85062fb84b21d926995e1567a6b796d527f0347cda6f8f9470a7ae23e",
            },
            ApkSource {
                base: false,
                bytes: 34421661,
                sha256: "0d9415e4ca05dc0518ff6d737352d562412722aa0733393d7c3d796097b76bf3",
            },
            ApkSource {
                base: false,
                bytes: 209305,
                sha256: "2bac8412ebf14c7e37b5e616ee1d60e65c59fc76a01137ea418d2f91a0e8d7d3",
            },
            ApkSource {
                base: false,
                bytes: 2283241,
                sha256: "f0cf576727bbb4a51530af0c2a31985afb897bbfc526052578dd752e1d3ba95d",
            },
        ],
    },
    Source {
        package: "com.hilton.android.hhonors",
        profile: "hotel",
        version: 1040,
        routes: &[Kind::Hotel],
        apks: &[
            ApkSource {
                base: true,
                bytes: 113890198,
                sha256: "bcf29dc4bbdd5a3903e1a46e2f037124ec929e24a542d9cbc2daefd245566263",
            },
            ApkSource {
                base: false,
                bytes: 31466355,
                sha256: "c8ca68efced5ee84d7dbedf92474258f5aed85a0fbdb60a5140cfc7022d3343f",
            },
            ApkSource {
                base: false,
                bytes: 319897,
                sha256: "8b920ec0c0b6d9c35de98aa8f2c25225024f2f2fef85f0ac46cb94a8ed913f4d",
            },
            ApkSource {
                base: false,
                bytes: 2396352,
                sha256: "c64cf23f5a7f2886c626d7a0c8ee9b295540dc259de266f7a792caa83c1256ca",
            },
        ],
    },
    Source {
        package: "com.marriott.mrt",
        profile: "hotel",
        version: 681,
        routes: &[Kind::Hotel],
        apks: &[
            ApkSource {
                base: true,
                bytes: 78189335,
                sha256: "1d67c71f0948143a5cdafd0eda6d20f1db74b203eed4a8dca12827a42a620e95",
            },
            ApkSource {
                base: false,
                bytes: 23282757,
                sha256: "b6ba58315cd45915138bcfbbaf598409af359cfb4c6e4378fc62ce10654472d7",
            },
            ApkSource {
                base: false,
                bytes: 34545959,
                sha256: "302920239a07dc061effccc98a198f7c59ed3c25577f3b68c9f567b42f240f8e",
            },
        ],
    },
    Source {
        package: "com.rytong.airchina",
        profile: "flight",
        version: 75304,
        routes: &[Kind::Flight],
        apks: &[ApkSource {
            base: true,
            bytes: 207028842,
            sha256: "ae12f9a79ce842f43b6d15e51cd282dec0231b468bdc9df82dfae43ad8e4bed0",
        }],
    },
    Source {
        package: "com.rytong.ceair",
        profile: "flight",
        version: 239,
        routes: &[Kind::Flight],
        apks: &[ApkSource {
            base: true,
            bytes: 220804847,
            sha256: "a6da8d746f98cae884f6b0137b5c7e8412836adf75530b763dae1536c75522ce",
        }],
    },
    Source {
        package: "com.szzc",
        profile: "rental",
        version: 330,
        routes: &[Kind::Rental],
        apks: &[ApkSource {
            base: true,
            bytes: 220498418,
            sha256: "1461b66c3dc3497989eb4a71361b56584dca1caa6b8120ebc5c4c1f240782c03",
        }],
    },
    Source {
        package: "com.united.mobile.android",
        profile: "flight",
        version: 3622,
        routes: &[Kind::Flight],
        apks: &[
            ApkSource {
                base: true,
                bytes: 251946034,
                sha256: "48b303481e2e47964780055e452e923a6c5e97bd216e6175418fe30abed4d26c",
            },
            ApkSource {
                base: false,
                bytes: 88511671,
                sha256: "853cb1f2e6cb861a46d0a346bcefdd31517f98a2b7a6c3b33004832308e64c41",
            },
            ApkSource {
                base: false,
                bytes: 590233,
                sha256: "57d86a59d3c9d83fae72b9a65b4faaf8a8a14e22aca3aac7f4f6d9c1b26d8deb",
            },
            ApkSource {
                base: false,
                bytes: 9993541,
                sha256: "c14f61ca9f62aa6f9d9bfe99a64530950614aa20771a5241077610cba167a3c6",
            },
        ],
    },
    Source {
        package: "ctrip.android.view",
        profile: "travel",
        version: 2140,
        routes: &[Kind::Hotel, Kind::Flight, Kind::Train],
        apks: &[ApkSource {
            base: true,
            bytes: 105120228,
            sha256: "ff50a7309183b258639b24185ac218d632feb0078f4a89484ad8bea2c8d07536",
        }],
    },
    Source {
        package: "jp.co.ana.android.tabidachi",
        profile: "flight",
        version: 344,
        routes: &[Kind::Flight],
        apks: &[
            ApkSource {
                base: true,
                bytes: 52121003,
                sha256: "2b3417c42a8fe9104a3c0a073d8105ba39e75df0601e35b656de28219ddf0883",
            },
            ApkSource {
                base: false,
                bytes: 10827107,
                sha256: "e5199ca7e9e4de1d132fc857ab8e16f7d5c757d017b1e61e73d1f0f1b637b045",
            },
            ApkSource {
                base: false,
                bytes: 139673,
                sha256: "1520c573808060a6acfae57dd4ca741ddc131ec0d3ba6108c2de0f7b8eeff4b1",
            },
            ApkSource {
                base: false,
                bytes: 4851591,
                sha256: "c113c9ae391914dfffd872cf1fe52b3a2a71d675d12b63eda2f2a10950210295",
            },
        ],
    },
];
pub(super) fn source(package: &str) -> Result<&'static Source, String> {
    SOURCES
        .iter()
        .find(|s| s.package == package)
        .ok_or_else(|| "travel package outside the twelve fixed original sources".into())
}
pub(super) fn require_application(a: &ApplicationInspection) -> Result<(), String> {
    let s = source(&a.package)?;
    let names = a
        .apks
        .iter()
        .map(|r| r.name.as_str())
        .collect::<BTreeSet<_>>();
    let hashes = a
        .apks
        .iter()
        .map(|r| r.sha256.as_str())
        .collect::<BTreeSet<_>>();
    let ok = a.user == 0
        && (10_000..20_000).contains(&a.uid)
        && a.version_code == s.version
        && a.apks.len() == s.apks.len()
        && names.len() == a.apks.len()
        && hashes.len() == a.apks.len()
        && a.apks.iter().all(|r| {
            r.path.starts_with("/data/app/")
                && r.path.rsplit('/').next() == Some(r.name.as_str())
                && !r.name.starts_with('.')
                && r.name.ends_with(".apk")
                && r.name
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
        })
        && s.apks.iter().all(|expected| {
            a.apks
                .iter()
                .filter(|actual| {
                    actual.bytes == expected.bytes
                        && actual.sha256 == expected.sha256
                        && (actual.name == "base.apk") == expected.base
                })
                .count()
                == 1
        });
    if ok {
        Ok(())
    } else {
        Err("travel needs the actual complete current PM APK set, version and source-bound Android user".into())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use droidloom_supervisor::control::application_probe::{InstalledApk, RuntimeEpoch};
    fn sample(s: &Source) -> ApplicationInspection {
        ApplicationInspection {
            package: s.package.into(),
            user: 0,
            uid: 10125,
            version_code: s.version,
            epoch: RuntimeEpoch {
                boot_id: "source-comparison-only".into(),
                cell_host_pid: 1,
                framework_host_pid: 2,
                framework_start_ticks: 3,
            },
            apks: s
                .apks
                .iter()
                .enumerate()
                .map(|(n, a)| {
                    let name = if a.base {
                        "base.apk".into()
                    } else {
                        format!("actual_observed_split_{n}.apk")
                    };
                    InstalledApk {
                        name: name.clone(),
                        path: format!("/data/app/actual-observed/{name}"),
                        bytes: a.bytes,
                        sha256: a.sha256.into(),
                    }
                })
                .collect(),
        }
    }
    #[test]
    fn complete_travel_apk_sets_reject_missing_extra_changed_and_wrong_subject() {
        assert_eq!(SOURCES.len(), 12);
        assert_eq!(SOURCES.iter().map(|s| s.routes.len()).sum::<usize>(), 14);
        assert_eq!(SELECTION_SHA256.len(), 64);
        for s in SOURCES {
            let a = sample(s);
            require_application(&a).unwrap();
            let mut reordered = a.clone();
            reordered.apks.reverse();
            require_application(&reordered).unwrap();
            for kind in 0..9 {
                let mut bad = a.clone();
                match kind {
                    0 => {
                        bad.apks.pop();
                    }
                    1 => bad.apks.push(bad.apks[0].clone()),
                    2 => bad.apks[0].sha256 = "0".repeat(64),
                    3 => bad.apks[0].bytes += 1,
                    4 => bad.version_code += 1,
                    5 => bad.user = 10,
                    6 => bad.uid = 2000,
                    7 => bad.apks[0].path = "/unrelated/base.apk".into(),
                    _ => bad.package = "com.ihg.apps.android".into(),
                }
                assert!(require_application(&bad).is_err(), "{}", s.package);
            }
        }
    }
}
