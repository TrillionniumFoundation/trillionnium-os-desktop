//! Apply complete official framework corrections to the paired framework and services producer.
//! These are source and build records; device tests, DEX semantics and whole-CVE
//! acceptance remain separate from a successful ordinary build.
use super::*;
use std::os::unix::fs::MetadataExt;

pub(super) const TARGETS: &[&str] = &[
    "services",
    "framework-minus-apex",
    "WmTests",
    "FrameworksServicesTests",
    "UsbTests",
    "AudioServiceTests",
    "FrameworksUiServicesNotificationTests",
    "SystemUI",
    "FrameworksCoreTests",
    "module-info",
];
const COHERENT_TARGETS: &[&str] = &["services", "framework-minus-apex", "module-info"];
const INSTALLED_MODULES: &[(&str, &str, &str)] = &[
    (
        "framework-minus-apex",
        "frameworks/base",
        "system/framework/framework.jar",
    ),
    (
        "services",
        "frameworks/base/services",
        "system/framework/services.jar",
    ),
];
// The framework-only normal build keeps its own installed JAR pair. The focused
// ASB command also requests the separate platform SystemUI application.
const SYSTEM_UI_MODULE: (&str, &str, &str) = (
    "SystemUI",
    "frameworks/base/packages/SystemUI",
    "system_ext/priv-app/SystemUI/SystemUI.apk",
);
const ADDITIONAL_SOURCE_COMPONENTS: &[(&str, &str)] = &[
    ("CVE-2026-28588", "ExternalStorageProvider"),
    ("CVE-2026-58995", "libandroidfw"),
    ("CVE-2026-58997", "libhwui"),
];
const PROJECT: &str = "frameworks/base";
const PROJECT_PIN: &str = "94b4c163b7dfe5ce3607f7bb8456f9573f7de57d";
const CVES: &[&str] = &[
    "CVE-2026-58836",
    "CVE-2026-58866",
    "CVE-2026-28645",
    "CVE-2026-45514",
    "CVE-2026-58965",
    "CVE-2026-58970",
    "CVE-2026-49935",
    "CVE-2026-58934",
    "CVE-2026-59006",
    "CVE-2026-58957",
    "CVE-2026-58979",
    "CVE-2026-58969",
    "CVE-2026-58986",
    "CVE-2026-58955",
    "CVE-2026-59002",
    "CVE-2026-58837",
    "CVE-2026-58951",
    "CVE-2026-59015",
    "CVE-2026-58875",
    "CVE-2026-59008",
    "CVE-2026-59020",
    "CVE-2026-59021",
    "CVE-2026-58974",
    "CVE-2026-55287",
    "CVE-2026-58817",
    "CVE-2026-59000",
    "CVE-2026-55272",
    "CVE-2026-59004",
    "CVE-2026-28588",
    "CVE-2026-58995",
    "CVE-2026-58997",
];
const PATCHES: &[(&str, u64, &str, &str)] = &[
    (
        "android/security/framework-asb/9444f519c4e55123c11a7ce92a960bb38486dbab.patch",
        2875,
        "b088d7f1d355b08166ab02ef03f6615056c4c7be3d60ef7f610bcc198b5e5ddc",
        "9444f519c4e55123c11a7ce92a960bb38486dbab",
    ),
    (
        "android/security/framework-asb/8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54.patch",
        7886,
        "1466c54ca227db1466c241b5dd53200764211a459257ea4f472d84c2e93ae970",
        "8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54",
    ),
    (
        "android/security/framework-asb/7a1a896e52d35ee502fd7140d37bed53651a6daa.patch",
        8890,
        "a6a6923b720963c7cc59c7daedd1c057b5462b5cec97d8dbcee0df95796f3035",
        "7a1a896e52d35ee502fd7140d37bed53651a6daa",
    ),
    (
        "android/security/framework-asb/4d1f600cbcbbeb990e19bec4a386fb64f922ddd1.patch",
        6167,
        "3efaf6b185d90b0c711d3d738ed06e026ba8c0ab60f441d25ed59266996d8d1f",
        "4d1f600cbcbbeb990e19bec4a386fb64f922ddd1",
    ),
    (
        "android/security/framework-asb/2e373a0e5bc7d0b6feb0d5c461c44455c92e6805.patch",
        7378,
        "9cb931129b609df8b26a2ca413c1d9dc342b973e22b2ab2adad5fb17cdacc111",
        "2e373a0e5bc7d0b6feb0d5c461c44455c92e6805",
    ),
    (
        "android/security/framework-asb/a9f3330b0f82042931a896ed78ae588d049390eb.patch",
        1143,
        "37c99d7569176f56f6def4bfc8e0ef1389b798606349e099f41f8749e64751f5",
        "a9f3330b0f82042931a896ed78ae588d049390eb",
    ),
    (
        "android/security/framework-asb/45c98d34046991dd9d08fc6a32a47b2e8c2ceb98.patch",
        7487,
        "48e55830e93ae4ba7a86e6cabf96579dea4814703c936479fedf1b5b7654c1e6",
        "45c98d34046991dd9d08fc6a32a47b2e8c2ceb98",
    ),
    (
        "android/security/framework-asb/65d449f82c90589edf53546649a82ece1e8992b1.patch",
        3362,
        "d8368ebe335755e0e084e841ebcd87fcb894d04ff797421e220860f2c3c9a53f",
        "65d449f82c90589edf53546649a82ece1e8992b1",
    ),
    (
        "android/security/framework-asb/dfc1b5219ffbc682c0d328b27e026c549770c208.patch",
        1152,
        "3588298682736b58387f5602939f0161b4aede15efe16f517769ad6f555f31b2",
        "dfc1b5219ffbc682c0d328b27e026c549770c208",
    ),
    (
        "android/security/framework-asb/3b5efd2d2a846c7d319e03dd2dcb70e8fe773031.patch",
        3003,
        "0c23065f95d60a4fb0c9deab013b0e32de3f223e2ea26fe71ddd187f63aef5fc",
        "3b5efd2d2a846c7d319e03dd2dcb70e8fe773031",
    ),
    (
        "android/security/framework-asb/c6dfa8f425a6a6ebb68cabd63a5bf02276912375.patch",
        12065,
        "c6750d57c95e040344859f95cdfb3a379a58f3a36d207b9d75529dbfbe2ed26d",
        "c6dfa8f425a6a6ebb68cabd63a5bf02276912375",
    ),
    (
        "android/security/framework-asb/ca5297bdc95722cd294a1b0fc656dc5475fdf388.patch",
        11192,
        "7b0f4a06fb939de6b6bb427f68e78af14be2ed23d684ad2e8ff57fd4cf17b179",
        "ca5297bdc95722cd294a1b0fc656dc5475fdf388",
    ),
    (
        "android/security/framework-asb/97984663fccfaea9bce3098edd0ebdc53a893ab4.patch",
        6671,
        "cd6df728484a1238cbe983c7f9bdd6638843ae9d68dccb36d68899a9b06e094a",
        "97984663fccfaea9bce3098edd0ebdc53a893ab4",
    ),
    (
        "android/security/framework-asb/ed7053111ca5140539af6617ff86641fea267965.patch",
        2258,
        "cc5d91d12281f99c7e90ee578d54c397b4d300c4e3a4821e4fe112c0141fb1bf",
        "ed7053111ca5140539af6617ff86641fea267965",
    ),
    (
        "android/security/framework-asb/d01eb65a9c333d158d932f081ef2298ca789ebeb.patch",
        6872,
        "b4f8f4e4fd83046457c31734f4d24f3f3a9027d4a589f42ac7ad756c015ccc99",
        "d01eb65a9c333d158d932f081ef2298ca789ebeb",
    ),
    (
        "android/security/framework-asb/7ae3d28551aea0937e1ce6ad701edef2c9f04bcb.patch",
        2541,
        "6e0359dbb21cc59bdcddd1f1d8f7aa4b2ef092082a25c6f01466564c5caec0d7",
        "7ae3d28551aea0937e1ce6ad701edef2c9f04bcb",
    ),
    (
        "android/security/framework-asb/f064617cb9ccfa6f15490cb1d466fd68deebedf6.patch",
        1651,
        "5b7764c77bded168182c5b0da682e9d43c2324b4e2d62754b6098974b9fe85dd",
        "f064617cb9ccfa6f15490cb1d466fd68deebedf6",
    ),
    (
        "android/security/framework-asb/f4dc2337226ee49f258a9c284dcfa31e9271b7b9.patch",
        2004,
        "8999f02793a3ce57fd5c1b33d1c25ca292cc3e3ab7d43030537fe49422d60de1",
        "f4dc2337226ee49f258a9c284dcfa31e9271b7b9",
    ),
    (
        "android/security/framework-asb/6eaaa132ae6f9896489c43c36d6b4c046207ab75.patch",
        7660,
        "60c88a397607ca944b3ad43e2bfd7583dedac0a4e77c86056bd63d1b8346565d",
        "6eaaa132ae6f9896489c43c36d6b4c046207ab75",
    ),
    (
        "android/security/framework-asb/53971879271680b8f148370579e7c3639d79d6bd.patch",
        17461,
        "690dab6f9603160e0f9088b90289a336744fe72349a2805563a550be5731f346",
        "53971879271680b8f148370579e7c3639d79d6bd",
    ),
    (
        "android/security/framework-asb/71bdf162ba20528f7e74123ce826903550a35938.patch",
        14316,
        "3828eb7542ba5c9b8929d7d81982631b5316fadc0a1bb7ec36ab432c46b1e94c",
        "71bdf162ba20528f7e74123ce826903550a35938",
    ),
    (
        "android/security/framework-asb/d00f145f6aff61436eef0774bdae03415395e81b.patch",
        1370,
        "ebf61a49a6cefdf08c341922fd73e0eb0d604459b4448a0e97612b04da42ab6b",
        "d00f145f6aff61436eef0774bdae03415395e81b",
    ),
    (
        "android/security/framework-asb/99894bf304145a9852b07cc0a9842265228a3c18.patch",
        3857,
        "f7720be0d27f7da9c1e8d12caed39d31c61520e5f5c8e0a3c4660bb7033e38b8",
        "99894bf304145a9852b07cc0a9842265228a3c18",
    ),
    (
        "android/security/framework-asb/5c8495d4b8f59c043de6a2ead597c98f098f6a8e.patch",
        1529,
        "3929fe7f24d3fdf54e9d5d6014508acf8184871e7151afb8ffeae0b5b30a2d68",
        "5c8495d4b8f59c043de6a2ead597c98f098f6a8e",
    ),
    (
        "android/security/framework-asb/b13f68610604aad2bd4bef459bb2ed8398be2787.patch",
        2441,
        "7383ac2d4e69790176919357ca76f77077efa1103436d066177bd38f772c3f21",
        "b13f68610604aad2bd4bef459bb2ed8398be2787",
    ),
    (
        "android/security/framework-asb/27be977cd8056410cdbb68ea0491d59c0ef1445f.patch",
        2225,
        "96546d88596244345d3a103973fe684d99926be330e1930150b37854903e4cdd",
        "27be977cd8056410cdbb68ea0491d59c0ef1445f",
    ),
    (
        "android/security/framework-asb/431c43bd57cc0c02656219c28d59232632d6d095.patch",
        3733,
        "5a133f4f6fd22417dac52d915f49e5cc9fd829f52915c846f1131d9ad942a1bf",
        "431c43bd57cc0c02656219c28d59232632d6d095",
    ),
    (
        "android/security/framework-asb/0783388b667b6272c5b36bbfb3b53a01d7afc07e.patch",
        2117,
        "b4a9ab5ae1757021c1166ed81252d287e34daaecb72a61b8cf425ff5261f708d",
        "0783388b667b6272c5b36bbfb3b53a01d7afc07e",
    ),
    (
        "android/security/framework-asb/9644b7e34bb0156301cf36b6eb5f6cd542260e8f.patch",
        2902,
        "6526734654595b0d9f5629324e402be1ebb70038b516f89c5a4897c487cfc53a",
        "9644b7e34bb0156301cf36b6eb5f6cd542260e8f",
    ),
    (
        "android/security/framework-asb/3454f4991efb5bb38535c64788851a6c0d03933f.patch",
        32270,
        "de1d426644362ab01ce4c2ad32c3c1e4b9418820b2e86d2d23cd32b73b272cdd",
        "3454f4991efb5bb38535c64788851a6c0d03933f",
    ),
    (
        "android/security/framework-asb/250af57de977cbb4cbc1d425a64555fd1d89da2f.patch",
        6070,
        "c4ba8cdca82defef25335b11eb89a028c5258fb76dec4a3658527644ca9a90bf",
        "250af57de977cbb4cbc1d425a64555fd1d89da2f",
    ),
    (
        "android/security/framework-asb/365f2a1086deda76435eb8b82baee6eb1baab693.patch",
        3540,
        "903783caa91b8878afbaba2b0d189b28a97e197fdfd364b4a5e824bbc09b979f",
        "365f2a1086deda76435eb8b82baee6eb1baab693",
    ),
    (
        "android/security/framework-asb/14f77e2522151c169622f19e31b5daa6faee0282.patch",
        507,
        "712f701a4d3c31fe5480e9c2777b4b2735fb8d64b7abe3c1b99f318ee7175e46",
        "14f77e2522151c169622f19e31b5daa6faee0282",
    ),
];
const ALIASES_NOT_REPLAYED: &[(&str, &str)] = &[
    (
        "9444f519c4e55123c11a7ce92a960bb38486dbab",
        "ec56593e44df7847b614c1fbdb44feaf2d75623e",
    ),
    (
        "8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54",
        "a84ccbdd9c61336d8abe6ec15c766b9ce454483e",
    ),
    (
        "7a1a896e52d35ee502fd7140d37bed53651a6daa",
        "cabd39ad7bd18387802dcb9f2fd27a251d9966f2",
    ),
    (
        "4d1f600cbcbbeb990e19bec4a386fb64f922ddd1",
        "fb6a81e33d54baecf5b05ad81b4522433f710b94",
    ),
    (
        "2e373a0e5bc7d0b6feb0d5c461c44455c92e6805",
        "7925fecbf857e3463f71e26ca808d19848eaa994",
    ),
    (
        "a9f3330b0f82042931a896ed78ae588d049390eb",
        "e532173df93d6ffe6e38a5185b05450afd7f4bde",
    ),
    (
        "45c98d34046991dd9d08fc6a32a47b2e8c2ceb98",
        "35058d93a551f115a314a1b52e9a55c4745153d8",
    ),
    (
        "65d449f82c90589edf53546649a82ece1e8992b1",
        "1b9a78c1ed8dc1dfde7e1062e829890423d827aa",
    ),
    (
        "dfc1b5219ffbc682c0d328b27e026c549770c208",
        "e4cabe8de08637b0537067ad2101b759aa9a45f7",
    ),
    (
        "3b5efd2d2a846c7d319e03dd2dcb70e8fe773031",
        "dbab9c94338cd335363cb9665fe5346404fbc125",
    ),
    (
        "c6dfa8f425a6a6ebb68cabd63a5bf02276912375",
        "7c921ec9ebb02fa0a57bba1103051aef7ec3eaa0",
    ),
    (
        "ed7053111ca5140539af6617ff86641fea267965",
        "4d9170e117b17f37d69ba19f7b808a647c6d3a3f",
    ),
    (
        "d01eb65a9c333d158d932f081ef2298ca789ebeb",
        "9e7353b7d788125954eca6aaeb95f1dabb93eff2",
    ),
    (
        "7ae3d28551aea0937e1ce6ad701edef2c9f04bcb",
        "d5498e6af80f318d8a0eeb6c1db911de1483c04f",
    ),
    (
        "431c43bd57cc0c02656219c28d59232632d6d095",
        "bbf84d307ba6e1faf68df68407fa5b913dd6d97e",
    ),
    (
        "14f77e2522151c169622f19e31b5daa6faee0282",
        "215d0c49c0825b9e4a33c8ad840c9bae2a2e3089",
    ),
];
const ORIGINALS: &[(&str, u64, &str)] = &[
    (
        "services/accessibility/java/com/android/server/accessibility/AccessibilityWindowManager.java",
        102156,
        "e7c68f37e87a79eee3cbf408d2f963c9a1387d90fa0ee7a50c886e46fc2f24c5",
    ),
    (
        "services/core/java/com/android/server/pm/InstallPackageHelper.java",
        279969,
        "00a61a16e9a209f8c8be39bb997f63e3a7235c1214faab9a56157e619f1104ee",
    ),
    (
        "services/usb/java/com/android/server/usb/UsbService.java",
        89524,
        "7735afea26ad9b72bdb7d9ff9c18835dbd07b8b1ee093a42b0d1e244b6c6fc52",
    ),
    (
        "services/autofill/java/com/android/server/autofill/ui/SaveUi.java",
        35174,
        "72c58ec2e6292403c404ccf14676ed6e093ea8fc03ed5915cc9b0c4e3d1a7482",
    ),
    (
        "services/tests/servicestests/src/com/android/server/accessibility/AccessibilityWindowManagerTest.java",
        70025,
        "2bdbc4dd273f059a0e04c18f20d4edba1f9d559977ee49155e156eb4748a80ec",
    ),
    (
        "tests/UsbTests/src/com/android/server/usb/UsbServiceTest.java",
        15048,
        "03fcdb103b2ae24d03a92b6c05731d8617415c1451d5feab27ef702dfc864c0d",
    ),
    (
        "core/java/android/content/pm/PackageInstaller.java",
        254629,
        "4994cdfeb29aa136f6889c3d2ef4a531e9a05fc80f8a45387fa5e2da633b826f",
    ),
    (
        "services/Android.bp",
        18005,
        "01a1e03080a8d10e0344551fe75f067d94881d139c2c42c17b96ed702a898d5b",
    ),
    (
        "services/core/Android.bp",
        12364,
        "1c8e701380a377e034da9d5224d4040657666bedafeb862f4e6e7a0959a9717a",
    ),
    (
        "services/tests/servicestests/Android.bp",
        30725,
        "051e4d6be23025177ff185a189f58d93839cce47986fe409328aec2a322b2dae",
    ),
    (
        "tests/UsbTests/Android.bp",
        1706,
        "4cde9add294521d36a98c56ce0861745e2d0845e8448ec58bc5ff0a0d0263258",
    ),
    (
        "services/core/java/com/android/server/am/AppTimeTracker.java",
        5401,
        "404482615b4261b2cba0c09ed7bd9b31e42af8bb852a9640ec80742ed9cdabe9",
    ),
    (
        "services/core/java/com/android/server/audio/MusicFxHelper.java",
        18657,
        "e39364e9f8f0296b57d1ce824d1d53700877bfbaa867da476f9194e2d320fb7b",
    ),
    (
        "services/core/java/com/android/server/locales/LocaleManagerService.java",
        38680,
        "81fdae01625e752e1842a43da13728968a7b41239fe7ac28cc103be394c4fdaa",
    ),
    (
        "services/tests/audio/Android.bp",
        2359,
        "e0022a1fdfd254bdeb1321181d70dea354840a966f89193738ebbd4afd48de12",
    ),
    (
        "services/tests/audio/src/com/android/server/audio/MusicFxHelperTest.java",
        29700,
        "aa8e3626ccc79c7869cc0f861a33d0b281a82b818f4d4fde206cee858f471aa4",
    ),
    (
        "services/tests/servicestests/src/com/android/server/locales/LocaleManagerServiceTest.java",
        19313,
        "cca73e13e9bef811720213b3eeecc25c6f2f90ba59d10c456dcb46f8b18a3f64",
    ),
    (
        "services/core/java/com/android/server/wm/ActivityStarter.java",
        193865,
        "c1c1788181e60fead477ff7ad308b4cffe55fb7a38e162140f5cdeae231c8518",
    ),
    (
        "services/core/java/com/android/server/wm/WindowState.java",
        274963,
        "d3c8b8345a985f1d67cff37819244bc19887a4b6195460ab2780e877daec0909",
    ),
    (
        "services/tests/wmtests/Android.bp",
        51079,
        "23b4082ab5de81b25facce2629fcf65a34c01e057399fb385a13a825d269b87c",
    ),
    (
        "services/tests/wmtests/src/com/android/server/wm/ActivityStarterTests.java",
        103812,
        "950d66b224845b3486367af0b1971068b3e3ec56aadeeb79ef4d2c9c880070f9",
    ),
    (
        "services/tests/wmtests/src/com/android/server/wm/WindowStateTests.java",
        112874,
        "4635ec0dcf18c60e82f2b4ba9524aa4c89cbd232c31528f667cbec2a91c1fd67",
    ),
    (
        "services/core/java/com/android/server/media/quality/MediaQualityService.java",
        163123,
        "b1bc78b50bad3c45c02ae3887c071ebd26fd0a09e0d85c1a65610f8b3d2a9270",
    ),
    (
        "services/core/java/com/android/server/wm/PresentationController.java",
        12081,
        "4d12192ced169038a183cf0e556a8e2b13f64132f5e0c4d8f56ffb0722a785f7",
    ),
    (
        "services/tests/wmtests/src/com/android/server/wm/PresentationControllerTests.java",
        24472,
        "a7e21bc65a2c7e564623513db3cda3ffc8908aa5fb35be1622075895a307b553",
    ),
    (
        "services/core/java/com/android/server/notification/PreferencesHelper.java",
        149224,
        "9812c3b128b6ba0b64271d8de2cf439e651b00e4e10edab3962add2830626e5c",
    ),
    (
        "services/tests/uiservicestests/src/com/android/server/notification/PreferencesHelperTest.java",
        339433,
        "3ee4a0ab9a7c73bee843f97f2e7a4b72522280b2b5a6ef4852fe3b015d817aa9",
    ),
    (
        "services/tests/uiservicestests/Android.bp",
        5000,
        "5f6c17f31fa0408b4069d653b960ddf7dc2955bb2bcdbd6467afd3f7cde00c54",
    ),
    (
        "services/usb/java/com/android/server/usb/UsbDeviceManager.java",
        133999,
        "9091538e7f6c5fb0ecbf9b8e21d6e74f88c7bd2e97b274ced799f52c008d3f1d",
    ),
    (
        "core/java/android/app/admin/BundlePolicyValue.java",
        2618,
        "3c3837115cc44ff264ba8065447678ab524c977dde2d50de3d15b05fbb1f44e4",
    ),
    (
        "core/java/android/app/admin/DevicePolicyManager.java",
        899800,
        "24ea0ff2c2ff52e9e8acc63e8c6a51b65a87b11addc91dad4b8ffd6e39480906",
    ),
    (
        "core/java/android/app/admin/PackageSetPolicyValue.java",
        3524,
        "e43c6763381776dc91ef3a18e1ce8188aa20d7309d76360c810981f7817cdcab",
    ),
    (
        "core/java/android/companion/CompanionDeviceManager.java",
        117942,
        "2535d8ac09a2da80627d728354f5af937e468a135299a1beebea3e0ec651108b",
    ),
    (
        "core/java/android/companion/ICompanionDeviceManager.aidl",
        8761,
        "28277a07ff1a540b28031870fe9c7584a855839257968e886f68562b0921606d",
    ),
    (
        "core/java/android/os/Binder.java",
        53923,
        "502dcd0067b3603e321086917e8e2274a8fc7beae1e9a75b335c2a035707ea6e",
    ),
    (
        "services/companion/java/com/android/server/companion/CompanionDeviceManagerService.java",
        51301,
        "33a2b54cf8341dad86cbef5587145d59c6969dc05e882271c727d0299cde4094",
    ),
    (
        "services/companion/java/com/android/server/companion/datatransfer/SystemDataTransferProcessor.java",
        14842,
        "8ab96f8299ac8057ec87128e1808cdbcc0d9e10d9df5052c8fdb40dc59d7d459",
    ),
    (
        "services/core/java/com/android/server/wm/AppTaskImpl.java",
        25739,
        "512659a21a52a6772fc5917c0a9c279cbc02c1509d1bed49f096d7a26f1aa089",
    ),
    (
        "services/core/java/com/android/server/wm/Task.java",
        324800,
        "e2dba29e6d0ade21fe320a62a2356a3d1f07e9e19937250afc59d56c12c34fae",
    ),
    (
        "services/core/java/com/android/server/wm/WindowManagerService.java",
        505921,
        "e44c9d49211db4d4679e6833a87cef1209756415fa779ebae53186c055967508",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/BundlePolicySerializer.java",
        7672,
        "9c4a5da22162a667fc27df350439722e000b8fb746476f9baa3ecea305fc89d4",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyEngine.java",
        118704,
        "ebebee2d6df33b8427410d5cf2659917f074c4db487d4d57eadb516f5dfbe9c4",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyManagerService.java",
        1121389,
        "1207287f2d0e143bceb9dafeb6827a2be52669179a155da25d4fb8cd974c6ad2",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/LockTaskPolicySerializer.java",
        2572,
        "8de4a81f2edf5617e9177168502af37ba6b4d3804289784f37e61ae99efa141d",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/PackageSetPolicySerializer.java",
        2051,
        "3ba80ac8b8e8c5b04b31a7980eb0713a1978ac0e98553db57367f76c2a592e98",
    ),
    (
        "services/tests/servicestests/src/com/android/server/devicepolicy/DevicePolicyManagerTest.java",
        459946,
        "5327923e4ba06ccc6e246429ccea80ad0e38a14c27a4e21dc593fa3961211902",
    ),
    (
        "services/tests/servicestests/src/com/android/server/devicepolicy/PolicyValueTest.kt",
        2391,
        "530ca6a84ca869df3a1e2724766243553b949be797ccb18fc0aaa705a8469dad",
    ),
    (
        "Android.bp",
        28696,
        "9039665725aa013a88f222430e33a1a3e662e23ec87090f253592ee28ec2f545",
    ),
    (
        "core/java/Android.bp",
        32692,
        "bde0ed0b9eae4dda4170e84d700c2acf445938f107dd0c094e2cfd1535578fd4",
    ),
    (
        "services/companion/Android.bp",
        2034,
        "1c7a34df969c6422afbfffbd1b653e41dfb8ca7c15ea923c91d0db9c3147066f",
    ),
    (
        "services/devicepolicy/Android.bp",
        1327,
        "d4e81f5623f98c02eafc4f302f4def5beb6be9e90676422a8445f32600562769",
    ),
    (
        "core/java/android/accounts/GrantCredentialsPermissionActivity.java",
        8794,
        "77a39a1b4de9269039f260432acdba0f31b132f9b1c737ecdaac5ce40ba7afd7",
    ),
    (
        "core/java/android/app/ApplicationPackageManager.java",
        162241,
        "0574bb7121553823a9e23e9a05b1ca24a26497a9b670023314044411c8782a6e",
    ),
    (
        "core/java/android/app/admin/DeviceAdminInfo.java",
        25008,
        "58d5c018402e773fa88243db1456ce306e6690dfa68a1395457f2a649ef5d014",
    ),
    (
        "core/java/android/content/pm/ComponentInfo.java",
        17057,
        "f17aebbfa4add72b741518ab07121f62e33989f0f5285b23ab730e17426020ac",
    ),
    (
        "core/java/android/content/pm/LabeledIntent.java",
        6517,
        "3fe5e0031564d5cb1af7a16b9a01e593e14ada240d15879e8898b31bed907dd5",
    ),
    (
        "core/java/android/content/pm/LauncherActivityInfo.java",
        11219,
        "e05639d4a09cbedff4d39855274bdd956763e1d4b8a2c954b75b9b1ad75bb21e",
    ),
    (
        "core/java/android/content/pm/LauncherApps.java",
        121119,
        "81ea17a1cbf09264a545dd6427eb61a644c6326e5592d4b88f8f87c52192a2d0",
    ),
    (
        "core/java/android/content/pm/PackageItemInfo.java",
        19670,
        "0b2d994f73de73b2bda9a9bca33e8ddd9d0be0352c910fd69980d10d6247a483",
    ),
    (
        "core/java/android/content/pm/PackageManager.java",
        524683,
        "fefd48c61455289e8b33c3344e5509079b4169ee87cb1d17e950b273966eb0fa",
    ),
    (
        "core/java/android/content/pm/ResolveInfo.java",
        21018,
        "d4bb9e504c4a8a940a0659891ac9f1609499a2dfcb8a5119f8ab5e782f673658",
    ),
    (
        "core/java/android/content/res/Resources.java",
        116300,
        "1b4b7a234795f2e534bb3eceb9b39fbb7022a132e40127e9bde41323a2221faf",
    ),
    (
        "core/java/android/content/res/ResourcesImpl.java",
        71135,
        "3528dfd0e73f8802eb14ae970787e8b4db7e250ecb34791527107d635b8a9367",
    ),
    (
        "core/java/android/hardware/biometrics/PromptInfo.java",
        19409,
        "78a1ec0cbda5eba8970751d2dad89dd8b508ee91d9fbc7937e09d66363b42b88",
    ),
    (
        "core/java/com/android/internal/pm/pkg/parsing/ParsingUtils.java",
        8161,
        "4d18ce518c712d4a6788662c068d0b13cf1ef853aed50c44f3cf6436d6b904c1",
    ),
    (
        "core/tests/coretests/Android.bp",
        25691,
        "0da6ab7feda048ecd9b700d814ba0fcf9f7eecd594fedc13c060db1c3efc9007",
    ),
    (
        "core/tests/coretests/src/android/content/res/ResourcesDrawableTest.java",
        2907,
        "8e5179319b0220fba91c895676d5a5862125a4f43c0ca33057523c190c1be901",
    ),
    (
        "packages/SystemUI/Android.bp",
        49535,
        "fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3",
    ),
    (
        "packages/SystemUI/shared/Android.bp",
        3520,
        "1b7848310bff9d39ff1ff8391fc55d4b71c3619ae48f544c60391185c214980f",
    ),
    (
        "packages/SystemUI/shared/biometrics/src/com/android/systemui/biometrics/Utils.kt",
        10182,
        "3319f3da8c4b7070e5085ac73b394101f597bfe7e0a39183d73f69661d2e4569",
    ),
    (
        "packages/SystemUI/shared/biometrics/Android.bp",
        720,
        "35534ff0bd82694df2b2f983632eb47acacb9c84463a3829d65b9b9de3f4f8be",
    ),
    (
        "packages/ExternalStorageProvider/src/com/android/externalstorage/ExternalStorageProvider.java",
        39501,
        "9fed512df47d3de141288420cb4eb227ddf20ddff391b675e8c1b8c900210a8b",
    ),
    (
        "packages/ExternalStorageProvider/tests/src/com/android/externalstorage/ExternalStorageProviderTest.java",
        22974,
        "c982f681bae93aa4aa5d6e0256c2234b48ce2060a0e10ed0072bb21897bdcffd",
    ),
    (
        "packages/ExternalStorageProvider/Android.bp",
        639,
        "9ec233453456337d5cefb7b4a75a20a1d03511256024b51fece56dbe99291ff6",
    ),
    (
        "packages/ExternalStorageProvider/tests/Android.bp",
        924,
        "1e4574e51f73cb1fb8563a5d6e87d6148dfa1d6f8df0b08eabf0fbdec42b0387",
    ),
    (
        "libs/androidfw/Android.bp",
        9096,
        "cb5d1888ceadc63ce06fed36e4e4669c59c7d28504fc8ffd6f1d98bf815e93a2",
    ),
    (
        "libs/androidfw/ZipFileRO.cpp",
        8692,
        "3f68be57806237a07fdd2b7421039a861209562470cc885292b1176ab9ac550e",
    ),
    (
        "libs/androidfw/include/androidfw/ZipFileRO.h",
        6527,
        "4df1d85cf7134ac9f7424d400fc9e1f934fa1bce25ef9e40ca855f64ea2c0996",
    ),
    (
        "libs/hwui/jni/Bitmap.cpp",
        57274,
        "e8d5833d33b61274e6b08f9e5e5e6745516ba608589572333e5ac31b1d62afca",
    ),
    (
        "libs/hwui/Android.bp",
        24900,
        "37633298fdd6e1cf8a3d0acf59e715d8581dd0ba214384f480213d178a7f40c6",
    ),
];
const FIXED: &[(&str, u64, &str)] = &[
    (
        "services/accessibility/java/com/android/server/accessibility/AccessibilityWindowManager.java",
        102906,
        "95890fa47be8425e8ea0063487ad1e5418344124d0e3c83a1a9a542852af4376",
    ),
    (
        "services/core/java/com/android/server/pm/InstallPackageHelper.java",
        279425,
        "f9c83556d2ffc4f47dafd3a0db4d44eb288e5ba26bc7269c46db51bb45777fe3",
    ),
    (
        "services/usb/java/com/android/server/usb/UsbService.java",
        90577,
        "f9b730b03961f56461af5b1a7a1c621a4b2e4ad7eda688e00d6a4c15e3d9d946",
    ),
    (
        "services/autofill/java/com/android/server/autofill/ui/SaveUi.java",
        37086,
        "73b8331607e0f1581f6e94a4d0632c198a25a94d931ef16f3f643a33a5898655",
    ),
    (
        "services/tests/servicestests/src/com/android/server/accessibility/AccessibilityWindowManagerTest.java",
        74021,
        "0fb855b7db7ce6eaf4461f27dc934ff276afb1ce34dac199f8ea065c889c3722",
    ),
    (
        "tests/UsbTests/src/com/android/server/usb/UsbServiceTest.java",
        18540,
        "711222bcdcac6e6431be7869cc5c7a381041dbc38471dab5c533eb67b2966759",
    ),
    (
        "core/java/android/content/pm/PackageInstaller.java",
        254629,
        "4994cdfeb29aa136f6889c3d2ef4a531e9a05fc80f8a45387fa5e2da633b826f",
    ),
    (
        "services/core/java/com/android/server/am/AppTimeTracker.java",
        5847,
        "e64b2901c75c8db4bdc388417739c2744f20217266e04e72f43fe3d75fb5a7fb",
    ),
    (
        "services/core/java/com/android/server/audio/MusicFxHelper.java",
        19442,
        "3600c1e8d69f0ef9a53300c6318a29f5bd6887b75c29d8e7873bdc475773a3e8",
    ),
    (
        "services/core/java/com/android/server/locales/LocaleManagerService.java",
        39944,
        "5abcab5e1732b4b5609b96460ba8bb4985878467e10b3e20ea1b1f22985014f4",
    ),
    (
        "services/tests/audio/src/com/android/server/audio/MusicFxHelperTest.java",
        33309,
        "caf7ea07b2bbd814fe7e64da09347fbc8536ac92f681dfde340f015e47c9e8ee",
    ),
    (
        "services/tests/servicestests/src/com/android/server/locales/LocaleManagerServiceTest.java",
        23612,
        "cecbc779a16dff9a5d04640643932e2850dbde2b13f371c289ceefb0eafe4889",
    ),
    (
        "services/core/java/com/android/server/wm/ActivityStarter.java",
        194940,
        "f31abc0df54fa307ef07b81cb87806dfb66d2b774f7cef86488902ad0a23c190",
    ),
    (
        "services/core/java/com/android/server/wm/WindowState.java",
        275562,
        "d68d1620731b93685725e30a543b0e052c7157a32a93a9786e45387d9d7f869c",
    ),
    (
        "services/tests/wmtests/src/com/android/server/wm/ActivityStarterTests.java",
        111572,
        "3e309ca78086a2295efb9b6685a294080627ce614d712b39f4e469e3154863f6",
    ),
    (
        "services/tests/wmtests/src/com/android/server/wm/WindowStateTests.java",
        113746,
        "186e288812f1fda3d93f787a81e54df51cd1bcba378e3c67741bcbd1da613728",
    ),
    (
        "services/core/java/com/android/server/media/quality/MediaQualityService.java",
        167461,
        "48fa353b6dc2a4848bdf4341fd003c04feeb7a3b645c727bc6d3b0cfbd27373d",
    ),
    (
        "services/core/java/com/android/server/wm/PresentationController.java",
        12027,
        "b71e9a6c32c45049beac8a893e4add0a4bd7c1ca99aa9a689ec14d628022c963",
    ),
    (
        "services/tests/wmtests/src/com/android/server/wm/PresentationControllerTests.java",
        26726,
        "8908ea9f341c2b8471f496c1a54391aa5689fe4068cdb7ef4ee4934e0ce6d1af",
    ),
    (
        "services/core/java/com/android/server/notification/PreferencesHelper.java",
        149396,
        "de3aa20ae94c890ec2ab372ac60b86c2d58c3e30a3569276ec54ad3ba7d9a642",
    ),
    (
        "services/tests/uiservicestests/src/com/android/server/notification/PreferencesHelperTest.java",
        344024,
        "fb6562a46767d421585a34bee329c89fb936c028967ce4b06e177ec75277ddff",
    ),
    (
        "services/usb/java/com/android/server/usb/UsbDeviceManager.java",
        134610,
        "aba52ecc554202862ec2c5d5957b77de2b76afd9491916d3d9003f54480c72b0",
    ),
    (
        "core/java/android/app/admin/BundlePolicyTypeVerifier.java",
        3129,
        "37ee5ab946d732a18eebf5738bd76addc7953dd2145cf00727337f32c7d613a3",
    ),
    (
        "core/java/android/app/admin/BundlePolicyValue.java",
        2677,
        "d4e76ee1b52129298cca33e77b62282126a31013c81b9b9d96d8d367a2d1daaa",
    ),
    (
        "core/java/android/app/admin/DevicePolicyManager.java",
        899968,
        "46ea9b17aaeae19d0b4cdd2502019bff86130cfc32755512bea0608265675caf",
    ),
    (
        "core/java/android/app/admin/PackageSetPolicyValue.java",
        3670,
        "068f8166e7009d3b1ba346aa021a382b0b37f0ef0a32bed3ad4970e32ef864a4",
    ),
    (
        "core/java/android/companion/CompanionDeviceManager.java",
        117659,
        "208b06b8abd4d91c15de6464caaecb3a83c6fc9a4ccb1dea65878deb49c3cdf1",
    ),
    (
        "core/java/android/companion/ICompanionDeviceManager.aidl",
        8651,
        "4bf654b4a4fe4f89733d40cc932edbdd2f1e9b04a70ca20022bd294286cb689f",
    ),
    (
        "core/java/android/os/Binder.java",
        54394,
        "889aad9c5dca6e55f6beaef145c0b46bf7feecd0ea1d22acc176f9b5fd909564",
    ),
    (
        "services/companion/java/com/android/server/companion/CompanionDeviceManagerService.java",
        51976,
        "0630b48d02c25432a9de2ddad6e12cfe7d3ac6e66c7b4e5ae57b081b73bd1c9f",
    ),
    (
        "services/companion/java/com/android/server/companion/datatransfer/SystemDataTransferProcessor.java",
        15042,
        "a5d365bb792e4726193b10e7b8146833fef8f28d7aaa20351343365f9c75b036",
    ),
    (
        "services/core/java/com/android/server/wm/AppTaskImpl.java",
        25986,
        "94438d4f7adafd94d46dae23112418984e25e1ddbf38ce8af491950285ace49f",
    ),
    (
        "services/core/java/com/android/server/wm/Task.java",
        324967,
        "dffb2719c1150966c6d8f03e4c1d85953cbcff85dede3c07599494a9ffae0710",
    ),
    (
        "services/core/java/com/android/server/wm/WindowManagerService.java",
        505968,
        "bd509de4e9201f2549dde836fc0db5d8e77bbe7879ce45b6a788c0844def63d1",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/BundlePolicySerializer.java",
        7885,
        "107cb93f507864b8297bae5904d7da5e903bab2339cdecd12b133eb7014c51a3",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyEngine.java",
        118920,
        "096790207c8c24fe0280e1c8e947bb15895cc48618a987ad2fea041f74fbee28",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyManagerService.java",
        1123486,
        "82817715976e2266e0ca13bb682a2c6d120117d5f5cf278f7f66c4a5382e2c1c",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/LockTaskPolicySerializer.java",
        2829,
        "08979ae8451130d909c2c6f91f22939ba34a696afa5d7eedd921aed549131837",
    ),
    (
        "services/devicepolicy/java/com/android/server/devicepolicy/PackageSetPolicySerializer.java",
        2319,
        "3f8f188bcf1640c8b0a02357c1e325c420e4264fb9e5486829ae7f0da0e28237",
    ),
    (
        "services/tests/servicestests/src/com/android/server/devicepolicy/BundlePolicySerializerTest.kt",
        4370,
        "85383a2baf89c3a11e3a765631564fac62773335007d346bcdca684438ba7275",
    ),
    (
        "services/tests/servicestests/src/com/android/server/devicepolicy/DevicePolicyManagerTest.java",
        468045,
        "c3494314c9a96429cfae5a8e9276c235efa40675b9e2b694cda4ca0d82b1502e",
    ),
    (
        "services/tests/servicestests/src/com/android/server/devicepolicy/PolicyValueTest.kt",
        5527,
        "0b698a2dd4b31ebf1faee5a66912d8c8d61cc36511155e0166daccb453ec300d",
    ),
    (
        "core/java/android/accounts/GrantCredentialsPermissionActivity.java",
        9292,
        "ef9b27793add41dce40f9be6f2a2b175499af4fe5980bbe376965a4f858e488b",
    ),
    (
        "core/java/android/app/ApplicationPackageManager.java",
        162778,
        "0d0a0fcd96b80dacfe3160167b5840e631a34112102c92cf4a700bc6206ed091",
    ),
    (
        "core/java/android/app/admin/DeviceAdminInfo.java",
        25478,
        "945e4023dad20e00e634d6f7d8f184a247c7965f5257ce709868301584235269",
    ),
    (
        "core/java/android/content/pm/ComponentInfo.java",
        17774,
        "d5531463d8fbed4aba6276d2aec8df6ce2e26feacc84624c322963fa983c834a",
    ),
    (
        "core/java/android/content/pm/LabeledIntent.java",
        6714,
        "ecbd8d08a93295eaf3776cab4226729270d43cf77413a4dcc79f0c02039fb333",
    ),
    (
        "core/java/android/content/pm/LauncherActivityInfo.java",
        11583,
        "38b4fbada51477ed87b8d3060e2204d2826435c37cd4097862c3c1b582878f4b",
    ),
    (
        "core/java/android/content/pm/LauncherApps.java",
        121660,
        "7a1d73dd4d89f568860a9f31cb16561bf5945ab0d334174d5a4f6d7a5bfbf2af",
    ),
    (
        "core/java/android/content/pm/PackageItemInfo.java",
        20444,
        "aadcf0958e6617e2ad18ff26b603c77bab5961768ccf615846645c73f1b33183",
    ),
    (
        "core/java/android/content/pm/PackageManager.java",
        526673,
        "3e771f10893dbca6017d7d36b33a092e203c77601ec45617e6402e3314e5381f",
    ),
    (
        "core/java/android/content/pm/ResolveInfo.java",
        21264,
        "6bcb7db5e92c9070b45782776e6838ece1f689a6d10838fc7a34ca979eee65ad",
    ),
    (
        "core/java/android/content/res/Resources.java",
        117389,
        "8f10d4720426c14d7668cdd1bce7209bc6fdced33d98a62b0783df2d26b2e10b",
    ),
    (
        "core/java/android/content/res/ResourcesImpl.java",
        73509,
        "a0c6f095622685f9c6fa6739eb1c6562824b9058c649b738a4e3b9692152f41a",
    ),
    (
        "core/java/android/hardware/biometrics/PromptInfo.java",
        19484,
        "418e3fbeca8d94b9f96a806781b27f7778c5cb58e29c77bbdb511a35c3d294c9",
    ),
    (
        "core/java/com/android/internal/pm/pkg/parsing/ParsingUtils.java",
        8768,
        "3ce3d049bdb0866ba203ad408d3cd7adb699ecf4c4c597214155def89fc9add8",
    ),
    (
        "core/tests/coretests/src/android/content/res/ResourcesDrawableTest.java",
        6357,
        "08464fc7ebbcaa0285991cf2739f079016bf9d7a8e94021c6c9bf4457e1ac1aa",
    ),
    (
        "packages/SystemUI/shared/biometrics/src/com/android/systemui/biometrics/Utils.kt",
        10579,
        "c3a1e241bbe25b6c9c1b0bb0dd976bc0c70a91c429ff8a86e7775bddcfeda4d2",
    ),
    (
        "libs/androidfw/Android.bp",
        9132,
        "ba0336437989c9fe7e5c43ace8e4714df154d4fc0dbb098bcdcaf71ddd3076bf",
    ),
    (
        "libs/androidfw/ZipFileRO.cpp",
        8691,
        "f504c1dc00ead99378dbf9df76afe0fa07d9cfc2db3ae1574e479807ec28793e",
    ),
    (
        "libs/androidfw/include/androidfw/ZipFileRO.h",
        6600,
        "45ce16480f4daf38a82ddea7c324f26fa7401469fc873549ad0fa8cb8e128c9d",
    ),
    (
        "libs/androidfw/tests/ZipFileRO_test.cpp",
        1691,
        "b3abd49e22bfeac6f4928289b39aaff474a28854a88ebaf7cec99c50d204f4ca",
    ),
    (
        "libs/hwui/jni/Bitmap.cpp",
        57290,
        "9d3128ac199faac692b4b589098d5462074ed2555c9786737233fecbec2fbfa6",
    ),
    (
        "packages/ExternalStorageProvider/src/com/android/externalstorage/ExternalStorageProvider.java",
        41501,
        "1cd9f135f97e86d4a1e1524de240c559eec11f69d618fa69852d49a89437fbb7",
    ),
    (
        "packages/ExternalStorageProvider/tests/src/com/android/externalstorage/ExternalStorageProviderTest.java",
        24407,
        "261d13643f680ab349e6a785c54900af104286f13087bae212412a2a6f724268",
    ),
];
const PROVIDERS: &[(&str, u64, &str)] = &[
    (
        "services/Android.bp",
        18005,
        "01a1e03080a8d10e0344551fe75f067d94881d139c2c42c17b96ed702a898d5b",
    ),
    (
        "services/core/Android.bp",
        12364,
        "1c8e701380a377e034da9d5224d4040657666bedafeb862f4e6e7a0959a9717a",
    ),
    (
        "services/tests/servicestests/Android.bp",
        30725,
        "051e4d6be23025177ff185a189f58d93839cce47986fe409328aec2a322b2dae",
    ),
    (
        "tests/UsbTests/Android.bp",
        1706,
        "4cde9add294521d36a98c56ce0861745e2d0845e8448ec58bc5ff0a0d0263258",
    ),
    (
        "services/tests/audio/Android.bp",
        2359,
        "e0022a1fdfd254bdeb1321181d70dea354840a966f89193738ebbd4afd48de12",
    ),
    (
        "services/tests/wmtests/Android.bp",
        51079,
        "23b4082ab5de81b25facce2629fcf65a34c01e057399fb385a13a825d269b87c",
    ),
    (
        "services/tests/uiservicestests/Android.bp",
        5000,
        "5f6c17f31fa0408b4069d653b960ddf7dc2955bb2bcdbd6467afd3f7cde00c54",
    ),
    (
        "Android.bp",
        28696,
        "9039665725aa013a88f222430e33a1a3e662e23ec87090f253592ee28ec2f545",
    ),
    (
        "core/java/Android.bp",
        32692,
        "bde0ed0b9eae4dda4170e84d700c2acf445938f107dd0c094e2cfd1535578fd4",
    ),
    (
        "services/companion/Android.bp",
        2034,
        "1c7a34df969c6422afbfffbd1b653e41dfb8ca7c15ea923c91d0db9c3147066f",
    ),
    (
        "services/devicepolicy/Android.bp",
        1327,
        "d4e81f5623f98c02eafc4f302f4def5beb6be9e90676422a8445f32600562769",
    ),
    (
        "core/tests/coretests/Android.bp",
        25691,
        "0da6ab7feda048ecd9b700d814ba0fcf9f7eecd594fedc13c060db1c3efc9007",
    ),
    (
        "packages/SystemUI/Android.bp",
        49535,
        "fa1aaf330d580d6cefb74dc0ef1b52fcebbdd9b6bced5497a3bd29f9fb3647a3",
    ),
    (
        "packages/SystemUI/shared/Android.bp",
        3520,
        "1b7848310bff9d39ff1ff8391fc55d4b71c3619ae48f544c60391185c214980f",
    ),
    (
        "packages/SystemUI/shared/biometrics/Android.bp",
        720,
        "35534ff0bd82694df2b2f983632eb47acacb9c84463a3829d65b9b9de3f4f8be",
    ),
    (
        "libs/hwui/Android.bp",
        24900,
        "37633298fdd6e1cf8a3d0acf59e715d8581dd0ba214384f480213d178a7f40c6",
    ),
    (
        "packages/ExternalStorageProvider/Android.bp",
        639,
        "9ec233453456337d5cefb7b4a75a20a1d03511256024b51fece56dbe99291ff6",
    ),
    (
        "packages/ExternalStorageProvider/tests/Android.bp",
        924,
        "1e4574e51f73cb1fb8563a5d6e87d6148dfa1d6f8df0b08eabf0fbdec42b0387",
    ),
];

const ABSENT_ORIGINALS: &[&str] = &[
    "core/java/android/app/admin/BundlePolicyTypeVerifier.java",
    "services/tests/servicestests/src/com/android/server/devicepolicy/BundlePolicySerializerTest.kt",
    "libs/androidfw/tests/ZipFileRO_test.cpp",
];

/// The ordinary full TARGETS set contains services. This is not confined to an
/// otherwise unused security-only command.
pub(super) fn required_for_targets(targets: &[&str]) -> bool {
    targets.iter().any(|name| {
        matches!(
            *name,
            "services"
                | "framework-minus-apex"
                | "framework"
                | "services.core"
                | "services.companion"
                | "services.devicepolicy"
                | "services.accessibility"
                | "services.usb"
                | "services.autofill"
                | "WmTests"
                | "FrameworksServicesTests"
                | "UsbTests"
                | "AudioServiceTests"
                | "FrameworksUiServicesNotificationTests"
                | "FrameworksCoreTests"
                | "SystemUI"
        )
    })
}

pub(super) fn validate_request(request: FixedProductionRequest<'_>, product: &str) -> Result<()> {
    request.validate(product)?;
    if !request.uses_production_full_source()
        || request.source_mode() != SoongDependencyMode::Strict
        || !required_for_targets(request.requested_targets())
        || COHERENT_TARGETS.iter().any(|required| {
            request
                .requested_targets()
                .iter()
                .filter(|actual| *actual == required)
                .count()
                != 1
        })
    {
        return fail(
            "framework ASB production requires strict source and the actual services, framework-minus-apex and module-info targets together",
        );
    }
    Ok(())
}

fn original_path(root: &Path, relative: &str) -> Result<PathBuf> {
    if !root.is_absolute() || root.canonicalize()? != root {
        return fail(
            "framework ASB source and recipe roots must be canonical absolute directories",
        );
    }
    let mut path = root.to_path_buf();
    for component in Path::new(relative).components() {
        if !matches!(component, std::path::Component::Normal(_)) {
            return fail("framework ASB input path must have only original relative components");
        }
        path.push(component.as_os_str());
        let meta = fs::symlink_metadata(&path)?;
        if meta.file_type().is_symlink() {
            return fail("framework ASB original or patch path is an alias");
        }
    }
    Ok(path)
}

fn exact(root: &Path, relative: &str, bytes: u64, expected: &str) -> Result<PathBuf> {
    let path = original_path(root, relative)?;
    let before = fs::symlink_metadata(&path)?;
    if !before.is_file() || before.nlink() != 1 || before.len() != bytes || hash(&path)? != expected
    {
        return fail(format!(
            "framework ASB exact original or official fixed input differs: {relative}"
        ));
    }
    let after = fs::symlink_metadata(&path)?;
    let identity = |m: &fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.uid(),
            m.gid(),
            m.nlink(),
            m.len(),
            (m.mtime(), m.mtime_nsec()),
            (m.ctime(), m.ctime_nsec()),
        )
    };
    if identity(&before) != identity(&after) {
        return fail("framework ASB input changed during complete verification");
    }
    Ok(path)
}

pub(super) fn validate_original(repo: &Path, source: &Path) -> Result<()> {
    for (relative, bytes, expected) in ORIGINALS {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    for (relative, bytes, expected, _) in PATCHES {
        exact(repo, relative, *bytes, expected)?;
    }
    for relative in ABSENT_ORIGINALS {
        absent_original(source, &format!("{PROJECT}/{relative}"))?;
    }
    Ok(())
}

fn absent_original(root: &Path, relative: &str) -> Result<()> {
    let name = Path::new(relative);
    if name
        .components()
        .any(|component| !matches!(component, std::path::Component::Normal(_)))
    {
        return fail("framework ASB new-file path must have only original relative components");
    }
    let parent = name
        .parent()
        .and_then(Path::to_str)
        .ok_or("new-file input lacks a parent")?;
    let parent = original_path(root, parent)?;
    if !fs::symlink_metadata(&parent)?.is_dir() {
        return fail("framework ASB new-file parent is not an original directory");
    }
    let path = parent.join(name.file_name().ok_or("new-file input lacks a name")?);
    match fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error.into()),
        Ok(_) => fail("framework ASB official new-file destination already exists"),
    }
}

fn validate_fixed(source: &Path) -> Result<()> {
    for (relative, bytes, expected) in FIXED.iter().chain(PROVIDERS) {
        exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
    }
    Ok(())
}

pub(super) fn project(projection: &mut Projection, repo: &Path, source: &Path) -> Result<()> {
    validate_original(repo, source)?;
    let originals: Vec<_> = FIXED
        .iter()
        .filter(|fixed| !ORIGINALS.iter().any(|original| original == *fixed))
        .map(|(relative, _, _)| source.join(PROJECT).join(relative))
        .collect();
    projection.save_many(&originals)?;
    for (relative, _, _, _) in PATCHES {
        projection.patch(source, PROJECT, &repo.join(relative))?;
    }
    validate_fixed(source)
}

/// Keep the selected user/cp2a build and dependency enforcement explicit for
/// both the normal full producer and the ordinary services/WmTests producer.
pub(super) fn configure_command(
    request: FixedProductionRequest<'_>,
    product: &str,
    command: &mut Command,
) -> Result<()> {
    validate_request(request, product)?;
    enforce_strict_soong_dependencies(command);
    command.env("SELINUX_IGNORE_NEVERALLOWS", "false");
    Ok(())
}

pub(super) fn input_receipt(
    repo: &Path,
    source: &Path,
    lock: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
    projection: &Projection,
) -> Result<PathBuf> {
    validate_request(request, product)?;
    validate_fixed(source)?;
    for relative in ABSENT_ORIGINALS {
        let path = source.join(PROJECT).join(relative);
        let saved: Vec<_> = projection
            .originals
            .iter()
            .filter(|item| item.path == path)
            .collect();
        if saved.len() != 1
            || saved[0].bytes.is_some()
            || saved[0].permissions_mode.is_some()
            || saved[0].modified.is_some()
        {
            return fail(
                "framework ASB new-file absence is not held by the actual projection journal",
            );
        }
    }
    let mut inputs = request.description(product)?;
    let mut effective = Vec::new();
    for (relative, bytes, expected) in FIXED.iter().chain(PROVIDERS) {
        let path = exact(source, &format!("{PROJECT}/{relative}"), *bytes, expected)?;
        effective.push(serde_json::json!({"path": path, "bytes": bytes, "sha256": expected}));
    }
    let mut patches = Vec::new();
    for (relative, bytes, expected, commit) in PATCHES {
        let path = exact(repo, relative, *bytes, expected)?;
        patches.push(serde_json::json!({
            "path": path, "bytes": bytes, "sha256": expected, "commit": commit,
            "url": format!("https://android.googlesource.com/platform/frameworks/base/+/{commit}"),
        }));
    }
    inputs["schema"] = "droidloom-framework-asb-security-inputs-v2".into();
    inputs["CVE_rows"] = serde_json::json!(CVES);
    inputs["additional_fixed_source_components"] = serde_json::json!(ADDITIONAL_SOURCE_COMPONENTS);
    inputs["additional_component_outputs_bound"] = false.into();
    inputs["source_lock"] = serde_json::json!({"path": lock, "sha256": hash(lock)?});
    inputs["original_frameworks_base_pin"] = PROJECT_PIN.into();
    inputs["official_complete_patches"] = patches.into();
    inputs["same_fix_aliases_not_replayed"] = serde_json::json!(ALIASES_NOT_REPLAYED);
    let official_test_modules: Vec<_> = [
        "FrameworksCoreTests",
        "FrameworksServicesTests",
        "UsbTests",
        "AudioServiceTests",
        "WmTests",
        "FrameworksUiServicesNotificationTests",
    ]
    .into_iter()
    .filter(|module| request.requested_targets().contains(module))
    .collect();
    inputs["official_test_modules"] = serde_json::json!(official_test_modules);
    inputs["effective_upstream_files_and_providers"] = effective.into();
    inputs["required_coherent_targets"] = serde_json::json!(COHERENT_TARGETS);
    inputs["required_installed_modules"] = serde_json::json!(INSTALLED_MODULES);
    inputs["original_absent_files_journaled"] = serde_json::json!(ABSENT_ORIGINALS);
    inputs["effective_projection"] = projection.effective_inventory(repo, source)?;
    inputs["strict_allow_missing_dependencies"] = "false".into();
    inputs["selinux_ignore_neverallows"] = "false".into();
    inputs["artifact_identity_qualified"] = false.into();
    inputs["official_device_tests_executed"] = false.into();
    inputs["binary_semantic_fix_qualified"] = false.into();
    inputs["production_signing_qualified"] = false.into();
    inputs["SystemUI_requested_separately"] = request
        .requested_targets()
        .contains(&SYSTEM_UI_MODULE.0)
        .into();
    inputs["SystemUI_required_installed_module"] = serde_json::json!(SYSTEM_UI_MODULE);
    inputs["SystemUI_signing_qualified"] = false.into();
    inputs["SystemUI_runtime_qualified"] = false.into();
    inputs["whole_security_bulletin_qualified"] = false.into();
    inputs["runtime_qualified"] = false.into();
    inputs["production_ready"] = false.into();
    let path = out.join("droidloom-framework-asb-security-inputs.json");
    write(&path, serde_json::to_vec_pretty(&inputs)?)?;
    Ok(path)
}

pub(super) fn normal_result(
    repo: &Path,
    source: &Path,
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
) -> Result<()> {
    validate_request(request, product)?;
    validate_original(repo, source)?;
    let artifacts = completed_artifacts(out, product, request)?;
    let input = out.join("droidloom-framework-asb-security-inputs.json");
    write(
        &out.join("droidloom-framework-asb-security-normal-result.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "schema": "droidloom-framework-asb-security-normal-result-v2",
            "CVE_rows": CVES,
            "additional_fixed_source_components": ADDITIONAL_SOURCE_COMPONENTS,
            "additional_component_outputs_bound": false,
            "inputs": {"path": input, "sha256": hash(&input)?},
            "requested_targets": request.requested_targets(),
            "product": product,
            "normal_command_returned_success": true,
            "actual_output_files": artifacts,
            "required_coherent_targets": COHERENT_TARGETS,
            "required_installed_modules": INSTALLED_MODULES,
            "same_fix_aliases_not_replayed": ALIASES_NOT_REPLAYED,
            "original_source_files_and_providers_restored": true,
            "source_release": PRODUCTION_TARGET_RELEASE,
            "build_variant": PRODUCTION_BUILD_VARIANT,
            "strict_allow_missing_dependencies": "false",
            "selinux_ignore_neverallows": "false",
            "QPR1_source_identity_claim": false,
            "artifact_identity_qualified": false,
            "official_device_tests_executed": false,
            "binary_semantic_fix_qualified": false,
            "production_signing_qualified": false,
            "SystemUI_requested_separately": request.requested_targets().contains(&SYSTEM_UI_MODULE.0),
            "SystemUI_required_installed_module": SYSTEM_UI_MODULE,
            "SystemUI_signing_qualified": false,
            "SystemUI_runtime_qualified": false,
            "whole_security_bulletin_qualified": false,
            "runtime_qualified": false,
            "production_ready": false,
        }))?,
    )?;
    Ok(())
}

/// Bind outputs produced by this successful normal command. Device execution and
/// DEX semantic review are deliberately not inferred from artifact existence.
fn output_file(out: &Path, path: &Path) -> Result<serde_json::Value> {
    let relative = path
        .strip_prefix(out)
        .map_err(|_| "framework output escaped its owned output root")?;
    let text = relative
        .to_str()
        .ok_or("framework output path is not UTF-8")?;
    let original = original_path(out, text)?;
    let before = fs::symlink_metadata(&original)?;
    if !before.is_file() || before.nlink() != 1 || before.len() == 0 {
        return fail("normal framework command did not produce a nonempty single-link artifact");
    }
    let digest = hash(&original)?;
    exact(out, text, before.len(), &digest)?;
    let after = fs::symlink_metadata(&original)?;
    let identity = |m: &fs::Metadata| {
        (
            m.dev(),
            m.ino(),
            m.mode(),
            m.uid(),
            m.gid(),
            m.nlink(),
            m.len(),
            m.mtime(),
            m.mtime_nsec(),
            m.ctime(),
            m.ctime_nsec(),
        )
    };
    if identity(&before) != identity(&after) {
        return fail("framework output changed during complete hashing");
    }
    Ok(
        serde_json::json!({"path": original, "bytes": after.len(), "sha256": digest,
        "device": after.dev(), "inode": after.ino(), "mode": after.mode(),
        "uid": after.uid(), "gid": after.gid(), "nlink": after.nlink(),
        "mtime_seconds": after.mtime(), "mtime_nanoseconds": after.mtime_nsec(),
        "ctime_seconds": after.ctime(), "ctime_nanoseconds": after.ctime_nsec()}),
    )
}

// Pinned Make 5ce6f787 core/tasks/module-info.mk exposes the `module-info`
// phony goal and writes PRODUCT_OUT/module-info.json. Pinned Soong 6722dd88
// retains the absolute OUT_DIR through InstallPath.fullPath and serializes
// katiInstalls.InstallPaths().Strings() unchanged. This producer always passes
// a canonical absolute OUT_DIR; a relative path is not an alternate identity.
fn installed_artifact(
    out: &Path,
    product_out: &Path,
    info: &serde_json::Value,
    module: &str,
    provider: &str,
    relative: &str,
) -> Result<serde_json::Value> {
    let row = info
        .get(module)
        .ok_or("framework component module metadata is missing")?;
    let paths = row
        .get("path")
        .and_then(|value| value.as_array())
        .ok_or("framework component source provider metadata is missing")?;
    if paths.len() != 1 || paths[0].as_str() != Some(provider) {
        return fail("framework component module has a different or ambiguous source provider");
    }
    let installed = row
        .get("installed")
        .and_then(|value| value.as_array())
        .ok_or("framework component module has no installed output metadata")?;
    let expected = product_out.join(relative);
    let mut names = std::collections::BTreeSet::new();
    let extension = expected
        .extension()
        .and_then(|value| value.to_str())
        .filter(|value| matches!(*value, "jar" | "apk"))
        .ok_or("framework component has an unsupported fixed artifact extension")?;
    let mut matching_artifacts = 0;
    for value in installed {
        let name = value
            .as_str()
            .ok_or("framework component output path is not a string")?;
        let path = Path::new(name);
        if !names.insert(name)
            || !path.is_absolute()
            || !path.starts_with(product_out)
            || path.components().any(|part| {
                matches!(
                    part,
                    std::path::Component::ParentDir | std::path::Component::CurDir
                )
            })
        {
            return fail(
                "framework component metadata escaped its exact product output or repeated a path",
            );
        }
        if path.extension().and_then(|extension| extension.to_str()) == Some(extension) {
            if path != expected {
                return fail("framework component metadata names a different installed artifact");
            }
            matching_artifacts += 1;
        }
    }
    if matching_artifacts != 1 {
        return fail(
            "framework component metadata must identify exactly one expected installed artifact",
        );
    }
    Ok(
        serde_json::json!({"module": module, "provider": provider, "artifact": output_file(out, &expected)?}),
    )
}

fn completed_artifacts(
    out: &Path,
    product: &str,
    request: FixedProductionRequest<'_>,
) -> Result<Vec<serde_json::Value>> {
    validate_request(request, product)?;
    let product_out = out.join("target/product").join(product);
    let mut outputs = Vec::new();
    let info_path = product_out.join("module-info.json");
    let info_ref = output_file(out, &info_path)?;
    if fs::metadata(&info_path)?.len() > 128 * 1024 * 1024 {
        return fail("normal framework module metadata exceeds its bounded reader");
    }
    let info: serde_json::Value = serde_json::from_reader(fs::File::open(&info_path)?)?;
    for (module, provider, relative) in INSTALLED_MODULES {
        outputs.push(installed_artifact(
            out,
            &product_out,
            &info,
            module,
            provider,
            relative,
        )?);
    }
    if request.requested_targets().contains(&SYSTEM_UI_MODULE.0) {
        let (module, provider, relative) = SYSTEM_UI_MODULE;
        outputs.push(installed_artifact(
            out,
            &product_out,
            &info,
            module,
            provider,
            relative,
        )?);
    }
    if outputs[0]["artifact"]["device"] == outputs[1]["artifact"]["device"]
        && outputs[0]["artifact"]["inode"] == outputs[1]["artifact"]["inode"]
    {
        return fail("paired framework modules alias one artifact inode");
    }
    if request.requested_targets().iter().any(|target| {
        matches!(
            *target,
            "WmTests"
                | "FrameworksServicesTests"
                | "UsbTests"
                | "AudioServiceTests"
                | "FrameworksUiServicesNotificationTests"
                | "FrameworksCoreTests"
        )
    }) {
        for (module, provider) in [
            (
                "FrameworksCoreTests",
                "frameworks/base/core/tests/coretests",
            ),
            ("WmTests", "frameworks/base/services/tests/wmtests"),
            (
                "FrameworksServicesTests",
                "frameworks/base/services/tests/servicestests",
            ),
            ("UsbTests", "frameworks/base/tests/UsbTests"),
            ("AudioServiceTests", "frameworks/base/services/tests/audio"),
            (
                "FrameworksUiServicesNotificationTests",
                "frameworks/base/services/tests/uiservicestests",
            ),
        ] {
            if !request.requested_targets().contains(&module) {
                continue;
            }
            let row = info
                .get(module)
                .ok_or("requested official test missing from actual module metadata")?;
            let source_paths = row
                .get("path")
                .and_then(|x| x.as_array())
                .ok_or("test provider metadata missing")?;
            if !source_paths.iter().any(|p| p.as_str() == Some(provider)) {
                return fail("official test output is bound to a different source provider");
            }
            let installed = row
                .get("installed")
                .and_then(|x| x.as_array())
                .ok_or("official test has no installed artifact metadata")?;
            let mut apks = 0;
            for value in installed {
                let name = value.as_str().ok_or("invalid installed artifact path")?;
                let path = Path::new(name);
                if path.extension().and_then(|x| x.to_str()) != Some("apk") {
                    continue;
                }
                if !path.is_absolute() || !path.starts_with(&product_out) {
                    return fail(
                        "official test APK metadata does not identify this exact absolute product output",
                    );
                }
                let artifact = output_file(out, path)?;
                outputs.push(serde_json::json!({"module": module, "provider": provider, "artifact": artifact}));
                apks += 1;
            }
            if apks == 0 {
                return fail("requested official test produced no actual installed APK");
            }
        }
    }
    for (index, (module, provider, relative)) in INSTALLED_MODULES.iter().enumerate() {
        if installed_artifact(out, &product_out, &info, module, provider, relative)?
            != outputs[index]
        {
            return fail("paired framework artifact changed while binding the complete output set");
        }
    }
    let mut identities = std::collections::BTreeSet::new();
    for output in &outputs {
        let artifact = &output["artifact"];
        let path = artifact["path"]
            .as_str()
            .ok_or("framework component artifact lacks its actual path")?;
        let identity = (
            artifact["device"]
                .as_u64()
                .ok_or("artifact device is missing")?,
            artifact["inode"]
                .as_u64()
                .ok_or("artifact inode is missing")?,
        );
        if !identities.insert(identity) || output_file(out, Path::new(path))? != *artifact {
            return fail("framework component output is aliased or changed while binding the set");
        }
    }
    if output_file(out, &info_path)? != info_ref {
        return fail("module metadata changed while binding actual framework and test artifacts");
    }
    outputs.push(serde_json::json!({"module_info": info_ref}));
    Ok(outputs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    fn fixture(root: &Path) -> (PathBuf, PathBuf) {
        let repo = root.join("recipe");
        let source = root.join("source");
        for (name, bytes) in [
            ("services/accessibility/java/com/android/server/accessibility/AccessibilityWindowManager.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/accessibility/java/com/android/server/accessibility/AccessibilityWindowManager.java").as_slice()),
            ("services/core/java/com/android/server/pm/InstallPackageHelper.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/pm/InstallPackageHelper.java").as_slice()),
            ("services/usb/java/com/android/server/usb/UsbService.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/usb/java/com/android/server/usb/UsbService.java").as_slice()),
            ("services/autofill/java/com/android/server/autofill/ui/SaveUi.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/autofill/java/com/android/server/autofill/ui/SaveUi.java").as_slice()),
            ("services/tests/servicestests/src/com/android/server/accessibility/AccessibilityWindowManagerTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/servicestests/src/com/android/server/accessibility/AccessibilityWindowManagerTest.java").as_slice()),
            ("tests/UsbTests/src/com/android/server/usb/UsbServiceTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/tests/UsbTests/src/com/android/server/usb/UsbServiceTest.java").as_slice()),
            ("core/java/android/content/pm/PackageInstaller.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/PackageInstaller.java").as_slice()),
            ("services/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/Android.bp").as_slice()),
            ("services/core/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/Android.bp").as_slice()),
            ("services/tests/servicestests/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/servicestests/Android.bp").as_slice()),
            ("tests/UsbTests/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/tests/UsbTests/Android.bp").as_slice()),
            ("services/core/java/com/android/server/am/AppTimeTracker.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/am/AppTimeTracker.java").as_slice()),
            ("services/core/java/com/android/server/audio/MusicFxHelper.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/audio/MusicFxHelper.java").as_slice()),
            ("services/core/java/com/android/server/locales/LocaleManagerService.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/locales/LocaleManagerService.java").as_slice()),
            ("services/tests/audio/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/audio/Android.bp").as_slice()),
            ("services/tests/audio/src/com/android/server/audio/MusicFxHelperTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/audio/src/com/android/server/audio/MusicFxHelperTest.java").as_slice()),
            ("services/tests/servicestests/src/com/android/server/locales/LocaleManagerServiceTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/servicestests/src/com/android/server/locales/LocaleManagerServiceTest.java").as_slice()),
            ("services/core/java/com/android/server/wm/ActivityStarter.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/wm/ActivityStarter.java").as_slice()),
            ("services/core/java/com/android/server/wm/WindowState.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/wm/WindowState.java").as_slice()),
            ("services/tests/wmtests/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/wmtests/Android.bp").as_slice()),
            ("services/tests/wmtests/src/com/android/server/wm/ActivityStarterTests.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/wmtests/src/com/android/server/wm/ActivityStarterTests.java").as_slice()),
            ("services/tests/wmtests/src/com/android/server/wm/WindowStateTests.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/wmtests/src/com/android/server/wm/WindowStateTests.java").as_slice()),
            ("services/core/java/com/android/server/media/quality/MediaQualityService.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/media/quality/MediaQualityService.java").as_slice()),
            ("services/core/java/com/android/server/wm/PresentationController.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/wm/PresentationController.java").as_slice()),
            ("services/tests/wmtests/src/com/android/server/wm/PresentationControllerTests.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/wmtests/src/com/android/server/wm/PresentationControllerTests.java").as_slice()),
            ("services/core/java/com/android/server/notification/PreferencesHelper.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/notification/PreferencesHelper.java").as_slice()),
            ("services/tests/uiservicestests/src/com/android/server/notification/PreferencesHelperTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/uiservicestests/src/com/android/server/notification/PreferencesHelperTest.java").as_slice()),
            ("services/tests/uiservicestests/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/uiservicestests/Android.bp").as_slice()),
            ("services/usb/java/com/android/server/usb/UsbDeviceManager.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/usb/java/com/android/server/usb/UsbDeviceManager.java").as_slice()),
            ("core/java/android/app/admin/BundlePolicyValue.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/app/admin/BundlePolicyValue.java").as_slice()),
            ("core/java/android/app/admin/DevicePolicyManager.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/app/admin/DevicePolicyManager.java").as_slice()),
            ("core/java/android/app/admin/PackageSetPolicyValue.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/app/admin/PackageSetPolicyValue.java").as_slice()),
            ("core/java/android/companion/CompanionDeviceManager.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/companion/CompanionDeviceManager.java").as_slice()),
            ("core/java/android/companion/ICompanionDeviceManager.aidl", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/companion/ICompanionDeviceManager.aidl").as_slice()),
            ("core/java/android/os/Binder.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/os/Binder.java").as_slice()),
            ("services/companion/java/com/android/server/companion/CompanionDeviceManagerService.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/companion/java/com/android/server/companion/CompanionDeviceManagerService.java").as_slice()),
            ("services/companion/java/com/android/server/companion/datatransfer/SystemDataTransferProcessor.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/companion/java/com/android/server/companion/datatransfer/SystemDataTransferProcessor.java").as_slice()),
            ("services/core/java/com/android/server/wm/AppTaskImpl.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/wm/AppTaskImpl.java").as_slice()),
            ("services/core/java/com/android/server/wm/Task.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/wm/Task.java").as_slice()),
            ("services/core/java/com/android/server/wm/WindowManagerService.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/core/java/com/android/server/wm/WindowManagerService.java").as_slice()),
            ("services/devicepolicy/java/com/android/server/devicepolicy/BundlePolicySerializer.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/devicepolicy/java/com/android/server/devicepolicy/BundlePolicySerializer.java").as_slice()),
            ("services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyEngine.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyEngine.java").as_slice()),
            ("services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyManagerService.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyManagerService.java").as_slice()),
            ("services/devicepolicy/java/com/android/server/devicepolicy/LockTaskPolicySerializer.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/devicepolicy/java/com/android/server/devicepolicy/LockTaskPolicySerializer.java").as_slice()),
            ("services/devicepolicy/java/com/android/server/devicepolicy/PackageSetPolicySerializer.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/devicepolicy/java/com/android/server/devicepolicy/PackageSetPolicySerializer.java").as_slice()),
            ("services/tests/servicestests/src/com/android/server/devicepolicy/DevicePolicyManagerTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/servicestests/src/com/android/server/devicepolicy/DevicePolicyManagerTest.java").as_slice()),
            ("services/tests/servicestests/src/com/android/server/devicepolicy/PolicyValueTest.kt", include_bytes!("../../../android/security/framework-asb/fixtures/services/tests/servicestests/src/com/android/server/devicepolicy/PolicyValueTest.kt").as_slice()),
            ("Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/Android.bp").as_slice()),
            ("core/java/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/Android.bp").as_slice()),
            ("services/companion/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/companion/Android.bp").as_slice()),
            ("services/devicepolicy/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/services/devicepolicy/Android.bp").as_slice()),
            ("core/java/android/accounts/GrantCredentialsPermissionActivity.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/accounts/GrantCredentialsPermissionActivity.java").as_slice()),
            ("core/java/android/app/ApplicationPackageManager.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/app/ApplicationPackageManager.java").as_slice()),
            ("core/java/android/app/admin/DeviceAdminInfo.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/app/admin/DeviceAdminInfo.java").as_slice()),
            ("core/java/android/content/pm/ComponentInfo.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/ComponentInfo.java").as_slice()),
            ("core/java/android/content/pm/LabeledIntent.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/LabeledIntent.java").as_slice()),
            ("core/java/android/content/pm/LauncherActivityInfo.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/LauncherActivityInfo.java").as_slice()),
            ("core/java/android/content/pm/LauncherApps.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/LauncherApps.java").as_slice()),
            ("core/java/android/content/pm/PackageItemInfo.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/PackageItemInfo.java").as_slice()),
            ("core/java/android/content/pm/PackageManager.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/PackageManager.java").as_slice()),
            ("core/java/android/content/pm/ResolveInfo.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/pm/ResolveInfo.java").as_slice()),
            ("core/java/android/content/res/Resources.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/res/Resources.java").as_slice()),
            ("core/java/android/content/res/ResourcesImpl.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/content/res/ResourcesImpl.java").as_slice()),
            ("core/java/android/hardware/biometrics/PromptInfo.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/android/hardware/biometrics/PromptInfo.java").as_slice()),
            ("core/java/com/android/internal/pm/pkg/parsing/ParsingUtils.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/java/com/android/internal/pm/pkg/parsing/ParsingUtils.java").as_slice()),
            ("core/tests/coretests/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/core/tests/coretests/Android.bp").as_slice()),
            ("core/tests/coretests/src/android/content/res/ResourcesDrawableTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/core/tests/coretests/src/android/content/res/ResourcesDrawableTest.java").as_slice()),
            ("packages/SystemUI/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/packages/SystemUI/Android.bp").as_slice()),
            ("packages/SystemUI/shared/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/packages/SystemUI/shared/Android.bp").as_slice()),
            ("packages/SystemUI/shared/biometrics/src/com/android/systemui/biometrics/Utils.kt", include_bytes!("../../../android/security/framework-asb/fixtures/packages/SystemUI/shared/biometrics/src/com/android/systemui/biometrics/Utils.kt").as_slice()),
            ("packages/SystemUI/shared/biometrics/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/packages/SystemUI/shared/biometrics/Android.bp").as_slice()),
            ("packages/ExternalStorageProvider/src/com/android/externalstorage/ExternalStorageProvider.java", include_bytes!("../../../android/security/framework-asb/fixtures/packages/ExternalStorageProvider/src/com/android/externalstorage/ExternalStorageProvider.java").as_slice()),
            ("packages/ExternalStorageProvider/tests/src/com/android/externalstorage/ExternalStorageProviderTest.java", include_bytes!("../../../android/security/framework-asb/fixtures/packages/ExternalStorageProvider/tests/src/com/android/externalstorage/ExternalStorageProviderTest.java").as_slice()),
            ("packages/ExternalStorageProvider/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/packages/ExternalStorageProvider/Android.bp").as_slice()),
            ("packages/ExternalStorageProvider/tests/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/packages/ExternalStorageProvider/tests/Android.bp").as_slice()),
            ("libs/androidfw/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/libs/androidfw/Android.bp").as_slice()),
            ("libs/androidfw/ZipFileRO.cpp", include_bytes!("../../../android/security/framework-asb/fixtures/libs/androidfw/ZipFileRO.cpp").as_slice()),
            ("libs/androidfw/include/androidfw/ZipFileRO.h", include_bytes!("../../../android/security/framework-asb/fixtures/libs/androidfw/include/androidfw/ZipFileRO.h").as_slice()),
            ("libs/hwui/jni/Bitmap.cpp", include_bytes!("../../../android/security/framework-asb/fixtures/libs/hwui/jni/Bitmap.cpp").as_slice()),
            ("libs/hwui/Android.bp", include_bytes!("../../../android/security/framework-asb/fixtures/libs/hwui/Android.bp").as_slice()),
        ] { write(&source.join(PROJECT).join(name), bytes).unwrap(); }
        for (name, bytes) in [
            ("android/security/framework-asb/9444f519c4e55123c11a7ce92a960bb38486dbab.patch", include_bytes!("../../../android/security/framework-asb/9444f519c4e55123c11a7ce92a960bb38486dbab.patch").as_slice()),
            ("android/security/framework-asb/8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54.patch", include_bytes!("../../../android/security/framework-asb/8e0e0f7728ff147c2aecc24fca1a6b53e3b62b54.patch").as_slice()),
            ("android/security/framework-asb/7a1a896e52d35ee502fd7140d37bed53651a6daa.patch", include_bytes!("../../../android/security/framework-asb/7a1a896e52d35ee502fd7140d37bed53651a6daa.patch").as_slice()),
            ("android/security/framework-asb/4d1f600cbcbbeb990e19bec4a386fb64f922ddd1.patch", include_bytes!("../../../android/security/framework-asb/4d1f600cbcbbeb990e19bec4a386fb64f922ddd1.patch").as_slice()),
            ("android/security/framework-asb/2e373a0e5bc7d0b6feb0d5c461c44455c92e6805.patch", include_bytes!("../../../android/security/framework-asb/2e373a0e5bc7d0b6feb0d5c461c44455c92e6805.patch").as_slice()),
            ("android/security/framework-asb/a9f3330b0f82042931a896ed78ae588d049390eb.patch", include_bytes!("../../../android/security/framework-asb/a9f3330b0f82042931a896ed78ae588d049390eb.patch").as_slice()),
            ("android/security/framework-asb/45c98d34046991dd9d08fc6a32a47b2e8c2ceb98.patch", include_bytes!("../../../android/security/framework-asb/45c98d34046991dd9d08fc6a32a47b2e8c2ceb98.patch").as_slice()),
            ("android/security/framework-asb/65d449f82c90589edf53546649a82ece1e8992b1.patch", include_bytes!("../../../android/security/framework-asb/65d449f82c90589edf53546649a82ece1e8992b1.patch").as_slice()),
            ("android/security/framework-asb/dfc1b5219ffbc682c0d328b27e026c549770c208.patch", include_bytes!("../../../android/security/framework-asb/dfc1b5219ffbc682c0d328b27e026c549770c208.patch").as_slice()),
            ("android/security/framework-asb/3b5efd2d2a846c7d319e03dd2dcb70e8fe773031.patch", include_bytes!("../../../android/security/framework-asb/3b5efd2d2a846c7d319e03dd2dcb70e8fe773031.patch").as_slice()),
            ("android/security/framework-asb/c6dfa8f425a6a6ebb68cabd63a5bf02276912375.patch", include_bytes!("../../../android/security/framework-asb/c6dfa8f425a6a6ebb68cabd63a5bf02276912375.patch").as_slice()),
            ("android/security/framework-asb/ca5297bdc95722cd294a1b0fc656dc5475fdf388.patch", include_bytes!("../../../android/security/framework-asb/ca5297bdc95722cd294a1b0fc656dc5475fdf388.patch").as_slice()),
            ("android/security/framework-asb/97984663fccfaea9bce3098edd0ebdc53a893ab4.patch", include_bytes!("../../../android/security/framework-asb/97984663fccfaea9bce3098edd0ebdc53a893ab4.patch").as_slice()),
            ("android/security/framework-asb/ed7053111ca5140539af6617ff86641fea267965.patch", include_bytes!("../../../android/security/framework-asb/ed7053111ca5140539af6617ff86641fea267965.patch").as_slice()),
            ("android/security/framework-asb/d01eb65a9c333d158d932f081ef2298ca789ebeb.patch", include_bytes!("../../../android/security/framework-asb/d01eb65a9c333d158d932f081ef2298ca789ebeb.patch").as_slice()),
            ("android/security/framework-asb/7ae3d28551aea0937e1ce6ad701edef2c9f04bcb.patch", include_bytes!("../../../android/security/framework-asb/7ae3d28551aea0937e1ce6ad701edef2c9f04bcb.patch").as_slice()),
            ("android/security/framework-asb/f064617cb9ccfa6f15490cb1d466fd68deebedf6.patch", include_bytes!("../../../android/security/framework-asb/f064617cb9ccfa6f15490cb1d466fd68deebedf6.patch").as_slice()),
            ("android/security/framework-asb/f4dc2337226ee49f258a9c284dcfa31e9271b7b9.patch", include_bytes!("../../../android/security/framework-asb/f4dc2337226ee49f258a9c284dcfa31e9271b7b9.patch").as_slice()),
            ("android/security/framework-asb/6eaaa132ae6f9896489c43c36d6b4c046207ab75.patch", include_bytes!("../../../android/security/framework-asb/6eaaa132ae6f9896489c43c36d6b4c046207ab75.patch").as_slice()),
            ("android/security/framework-asb/53971879271680b8f148370579e7c3639d79d6bd.patch", include_bytes!("../../../android/security/framework-asb/53971879271680b8f148370579e7c3639d79d6bd.patch").as_slice()),
            ("android/security/framework-asb/71bdf162ba20528f7e74123ce826903550a35938.patch", include_bytes!("../../../android/security/framework-asb/71bdf162ba20528f7e74123ce826903550a35938.patch").as_slice()),
            ("android/security/framework-asb/d00f145f6aff61436eef0774bdae03415395e81b.patch", include_bytes!("../../../android/security/framework-asb/d00f145f6aff61436eef0774bdae03415395e81b.patch").as_slice()),
            ("android/security/framework-asb/99894bf304145a9852b07cc0a9842265228a3c18.patch", include_bytes!("../../../android/security/framework-asb/99894bf304145a9852b07cc0a9842265228a3c18.patch").as_slice()),
            ("android/security/framework-asb/5c8495d4b8f59c043de6a2ead597c98f098f6a8e.patch", include_bytes!("../../../android/security/framework-asb/5c8495d4b8f59c043de6a2ead597c98f098f6a8e.patch").as_slice()),
            ("android/security/framework-asb/b13f68610604aad2bd4bef459bb2ed8398be2787.patch", include_bytes!("../../../android/security/framework-asb/b13f68610604aad2bd4bef459bb2ed8398be2787.patch").as_slice()),
            ("android/security/framework-asb/27be977cd8056410cdbb68ea0491d59c0ef1445f.patch", include_bytes!("../../../android/security/framework-asb/27be977cd8056410cdbb68ea0491d59c0ef1445f.patch").as_slice()),
            ("android/security/framework-asb/431c43bd57cc0c02656219c28d59232632d6d095.patch", include_bytes!("../../../android/security/framework-asb/431c43bd57cc0c02656219c28d59232632d6d095.patch").as_slice()),
            ("android/security/framework-asb/0783388b667b6272c5b36bbfb3b53a01d7afc07e.patch", include_bytes!("../../../android/security/framework-asb/0783388b667b6272c5b36bbfb3b53a01d7afc07e.patch").as_slice()),
            ("android/security/framework-asb/9644b7e34bb0156301cf36b6eb5f6cd542260e8f.patch", include_bytes!("../../../android/security/framework-asb/9644b7e34bb0156301cf36b6eb5f6cd542260e8f.patch").as_slice()),
            ("android/security/framework-asb/3454f4991efb5bb38535c64788851a6c0d03933f.patch", include_bytes!("../../../android/security/framework-asb/3454f4991efb5bb38535c64788851a6c0d03933f.patch").as_slice()),
            ("android/security/framework-asb/250af57de977cbb4cbc1d425a64555fd1d89da2f.patch", include_bytes!("../../../android/security/framework-asb/250af57de977cbb4cbc1d425a64555fd1d89da2f.patch").as_slice()),
            ("android/security/framework-asb/365f2a1086deda76435eb8b82baee6eb1baab693.patch", include_bytes!("../../../android/security/framework-asb/365f2a1086deda76435eb8b82baee6eb1baab693.patch").as_slice()),
            ("android/security/framework-asb/14f77e2522151c169622f19e31b5daa6faee0282.patch", include_bytes!("../../../android/security/framework-asb/14f77e2522151c169622f19e31b5daa6faee0282.patch").as_slice()),
        ] { write(&repo.join(name), bytes).unwrap(); }
        for name in ABSENT_ORIGINALS {
            fs::create_dir_all(source.join(PROJECT).join(name).parent().unwrap()).unwrap();
        }
        (repo, source)
    }
    #[test]
    fn framework_four_official_patches_restore_complete_original_bytes_and_metadata() {
        for interrupted in [false, true] {
            let d = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(d.path());
            let mut before = Vec::new();
            for (relative, _, _) in ORIGINALS {
                let path = source.join(PROJECT).join(relative);
                fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
                let meta = fs::metadata(&path).unwrap();
                before.push((path, meta.permissions().mode(), meta.modified().unwrap()));
            }
            let journal = d.path().join("source-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            project(&mut projection, &repo, &source).unwrap();
            assert_eq!(projection.originals.len(), 64);
            validate_fixed(&source).unwrap();
            if interrupted {
                std::mem::forget(projection);
                recover(&journal, &source).unwrap();
            } else {
                projection.restore().unwrap();
            }
            validate_original(&repo, &source).unwrap();
            for (path, mode, modified) in before {
                let after = fs::metadata(path).unwrap();
                assert_eq!(after.permissions().mode(), mode);
                assert_eq!(after.modified().unwrap(), modified);
            }
            assert!(!journal.exists());
        }
    }

    #[test]
    fn framework_locale_two_stage_projection_recovers_originals_after_interruption() {
        // Exercise actual official patch application and journal recovery at
        // both Locale stages. No Java/DEX execution or attack input is used.
        // The first stage alone must not satisfy the complete producer pin.
        for last_patch in [6_usize, 7_usize] {
            let directory = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(directory.path());
            let mut original_metadata = Vec::new();
            for (relative, _, _) in ORIGINALS {
                let path = source.join(PROJECT).join(relative);
                fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
                let metadata = fs::metadata(&path).unwrap();
                original_metadata.push((
                    path,
                    metadata.permissions().mode(),
                    metadata.modified().unwrap(),
                ));
            }
            validate_original(&repo, &source).unwrap();
            let journal = directory.path().join("locale-stage-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            for (relative, _, _, _) in &PATCHES[..=last_patch] {
                projection
                    .patch(&source, PROJECT, &repo.join(relative))
                    .unwrap();
            }
            // The follow-up modifies the same two files. Their original
            // bytes must be journaled once, before the first official patch.
            assert_eq!(projection.originals.len(), 11);
            assert_eq!(projection.applied_patches.len(), last_patch + 1);
            if last_patch == 6 {
                for (relative, bytes, expected) in [
                    (
                        "services/core/java/com/android/server/locales/LocaleManagerService.java",
                        39851,
                        "a568f36de1e0f130450126f8d4f2677a70b7db1a5b1448d581ea0e495ff4e907",
                    ),
                    (
                        "services/tests/servicestests/src/com/android/server/locales/LocaleManagerServiceTest.java",
                        22494,
                        "c57c32981c90a7007ca9c428e893f6c2108d42e7982b67bb20c9caeb140760ef",
                    ),
                ] {
                    let path =
                        exact(&source, &format!("{PROJECT}/{relative}"), bytes, expected).unwrap();
                    let (_, _, final_expected) =
                        FIXED.iter().find(|(name, _, _)| *name == relative).unwrap();
                    // The independent Locale pin must reject stage one even
                    // while the later WM projection has not yet been applied.
                    assert_ne!(hash(&path).unwrap(), *final_expected);
                }
                assert!(validate_fixed(&source).is_err());
            } else {
                for relative in [
                    "services/core/java/com/android/server/locales/LocaleManagerService.java",
                    "services/tests/servicestests/src/com/android/server/locales/LocaleManagerServiceTest.java",
                ] {
                    let (_, bytes, expected) =
                        FIXED.iter().find(|(name, _, _)| *name == relative).unwrap();
                    exact(&source, &format!("{PROJECT}/{relative}"), *bytes, expected).unwrap();
                }
                // Both Locale files are final, but the complete producer
                // still requires the later WM, presentation, media, notification and USB patches.
                assert!(validate_fixed(&source).is_err());
                // The independent 11-original Locale boundary above is complete.
                // Journal only the remaining genuine mutations in one batch
                // before continuing the complete official patch sequence.
                let remaining: Vec<_> = FIXED
                    .iter()
                    .filter(|fixed| !ORIGINALS.iter().any(|original| original == *fixed))
                    .map(|(relative, _, _)| source.join(PROJECT).join(relative))
                    .filter(|path| {
                        !projection
                            .originals
                            .iter()
                            .any(|original| original.path.as_path() == path.as_path())
                    })
                    .collect();
                assert_eq!(remaining.len(), 53);
                projection.save_many(&remaining).unwrap();
                assert_eq!(projection.originals.len(), 64);
                for (relative, _, _, _) in &PATCHES[8..] {
                    projection
                        .patch(&source, PROJECT, &repo.join(relative))
                        .unwrap();
                }
                assert_eq!(projection.originals.len(), 64);
                assert_eq!(projection.applied_patches.len(), 33);
                validate_fixed(&source).unwrap();
            }
            std::mem::forget(projection);
            recover(&journal, &source).unwrap();
            validate_original(&repo, &source).unwrap();
            for (path, permissions, modified) in original_metadata {
                let actual = fs::metadata(path).unwrap();
                assert_eq!(actual.permissions().mode(), permissions);
                assert_eq!(actual.modified().unwrap(), modified);
            }
            assert!(!journal.exists());
        }
    }

    #[test]
    fn framework_wm_staged_projection_recovers_originals_after_interruption() {
        // Apply only complete public patches to original source fixtures.
        // These ordinary journal checks execute no Java, DEX or device input.
        for (last_patch, journaled) in [(8_usize, 12_usize), (9, 13), (10, 15)] {
            let directory = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(directory.path());
            let mut original_metadata = Vec::new();
            for (relative, _, _) in ORIGINALS {
                let path = source.join(PROJECT).join(relative);
                fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
                let metadata = fs::metadata(&path).unwrap();
                original_metadata.push((
                    path,
                    metadata.permissions().mode(),
                    metadata.modified().unwrap(),
                ));
            }
            validate_original(&repo, &source).unwrap();
            let window_relative = "services/core/java/com/android/server/wm/WindowState.java";
            let window = source.join(PROJECT).join(window_relative);
            let original_window_bytes = fs::read(&window).unwrap();
            let journal = directory.path().join("wm-stage-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            for (relative, _, _, _) in &PATCHES[..=last_patch] {
                projection
                    .patch(&source, PROJECT, &repo.join(relative))
                    .unwrap();
            }
            assert_eq!(projection.originals.len(), journaled);
            assert_eq!(projection.applied_patches.len(), last_patch + 1);
            // The two WindowState corrections must preserve the same first
            // preimage, not replace it with the intermediate patched bytes.
            let saved_windows: Vec<_> = projection
                .originals
                .iter()
                .filter(|item| item.path == window)
                .collect();
            assert_eq!(saved_windows.len(), 1);
            assert_eq!(
                saved_windows[0].bytes.as_deref(),
                Some(original_window_bytes.as_slice())
            );
            drop(saved_windows);
            let (bytes, expected) = if last_patch == 8 {
                (
                    275120,
                    "a4bf39fe8482ebd0e6b01d9d7c87b886bd50a31e63f918e715dfaa91a1617dae",
                )
            } else {
                (
                    275562,
                    "d68d1620731b93685725e30a543b0e052c7157a32a93a9786e45387d9d7f869c",
                )
            };
            exact(
                &source,
                &format!("{PROJECT}/{window_relative}"),
                bytes,
                expected,
            )
            .unwrap();
            for (relative, is_fixed) in [
                (
                    "services/tests/wmtests/src/com/android/server/wm/WindowStateTests.java",
                    last_patch >= 9,
                ),
                (
                    "services/core/java/com/android/server/wm/ActivityStarter.java",
                    last_patch == 10,
                ),
                (
                    "services/tests/wmtests/src/com/android/server/wm/ActivityStarterTests.java",
                    last_patch == 10,
                ),
            ] {
                let pins = if is_fixed { FIXED } else { ORIGINALS };
                let (_, bytes, expected) =
                    pins.iter().find(|(name, _, _)| *name == relative).unwrap();
                exact(&source, &format!("{PROJECT}/{relative}"), *bytes, expected).unwrap();
            }
            // The complete WM sequence precedes the presentation/media fixes.
            assert!(validate_fixed(&source).is_err());
            if last_patch == 10 {
                // Preserve the original 15-file WM recovery boundary. Check
                // every original WM9 final pin and unchanged provider, then
                // recover before applying any presentation or media patch.
                for (relative, bytes, expected) in FIXED[..16].iter().chain(PROVIDERS) {
                    exact(&source, &format!("{PROJECT}/{relative}"), *bytes, expected).unwrap();
                }
                assert_eq!(projection.originals.len(), 15);
                assert_eq!(projection.applied_patches.len(), 11);
            }
            std::mem::forget(projection);
            recover(&journal, &source).unwrap();
            validate_original(&repo, &source).unwrap();
            for (path, permissions, modified) in original_metadata {
                let actual = fs::metadata(path).unwrap();
                assert_eq!(actual.permissions().mode(), permissions);
                assert_eq!(actual.modified().unwrap(), modified);
            }
            assert!(!journal.exists());
        }
    }

    #[test]
    fn framework_presentation_media_stages_restore_one_original_per_file() {
        // Apply complete official source patches and test journal recovery at
        // each media and notification boundary. This executes no Java, DEX or device input.
        for (last_patch, journaled) in [(11_usize, 17_usize), (12, 18), (13, 18), (14, 20)] {
            let directory = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(directory.path());
            let mut original_metadata = Vec::new();
            for (relative, _, _) in ORIGINALS {
                let path = source.join(PROJECT).join(relative);
                fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
                let metadata = fs::metadata(&path).unwrap();
                original_metadata.push((
                    path,
                    metadata.permissions().mode(),
                    metadata.modified().unwrap(),
                ));
            }
            validate_original(&repo, &source).unwrap();
            let media_relative =
                "services/core/java/com/android/server/media/quality/MediaQualityService.java";
            let media_path = source.join(PROJECT).join(media_relative);
            let media_original = fs::read(&media_path).unwrap();
            let journal = directory.path().join("presentation-media-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            for (relative, _, _, _) in &PATCHES[..=last_patch] {
                projection
                    .patch(&source, PROJECT, &repo.join(relative))
                    .unwrap();
            }
            assert_eq!(projection.originals.len(), journaled);
            assert_eq!(projection.applied_patches.len(), last_patch + 1);
            for relative in [
                "services/core/java/com/android/server/wm/PresentationController.java",
                "services/tests/wmtests/src/com/android/server/wm/PresentationControllerTests.java",
            ] {
                let (_, bytes, expected) =
                    FIXED.iter().find(|(name, _, _)| *name == relative).unwrap();
                exact(&source, &format!("{PROJECT}/{relative}"), *bytes, expected).unwrap();
            }
            let (bytes, expected) = match last_patch {
                11 => (
                    163123,
                    "b1bc78b50bad3c45c02ae3887c071ebd26fd0a09e0d85c1a65610f8b3d2a9270",
                ),
                12 => (
                    166882,
                    "d412de5c1e3d4533108e09f98262029d586f5ff7d83d73113941399b50ce38f2",
                ),
                13 | 14 => (
                    167461,
                    "48fa353b6dc2a4848bdf4341fd003c04feeb7a3b645c727bc6d3b0cfbd27373d",
                ),
                _ => unreachable!(),
            };
            exact(
                &source,
                &format!("{PROJECT}/{media_relative}"),
                bytes,
                expected,
            )
            .unwrap();
            let saved_media: Vec<_> = projection
                .originals
                .iter()
                .filter(|item| item.path == media_path)
                .collect();
            assert_eq!(saved_media.len(), usize::from(last_patch >= 12));
            if last_patch >= 12 {
                assert_eq!(
                    saved_media[0].bytes.as_deref(),
                    Some(media_original.as_slice())
                );
            }
            drop(saved_media);
            for relative in [
                "services/core/java/com/android/server/notification/PreferencesHelper.java",
                "services/tests/uiservicestests/src/com/android/server/notification/PreferencesHelperTest.java",
            ] {
                let pins = if last_patch == 14 { FIXED } else { ORIGINALS };
                let (_, bytes, expected) =
                    pins.iter().find(|(name, _, _)| *name == relative).unwrap();
                exact(&source, &format!("{PROJECT}/{relative}"), *bytes, expected).unwrap();
            }
            if last_patch == 14 {
                // Preserve the original notification recovery boundary. All
                // previously qualified final pins and providers are checked
                // before applying the later USB timeout correction.
                for (relative, bytes, expected) in FIXED[..21].iter().chain(PROVIDERS) {
                    exact(&source, &format!("{PROJECT}/{relative}"), *bytes, expected).unwrap();
                }
                let usb_relative = "services/usb/java/com/android/server/usb/UsbDeviceManager.java";
                let (_, original_bytes, original_sha) = ORIGINALS
                    .iter()
                    .find(|(name, _, _)| *name == usb_relative)
                    .unwrap();
                let usb = exact(
                    &source,
                    &format!("{PROJECT}/{usb_relative}"),
                    *original_bytes,
                    original_sha,
                )
                .unwrap();
                let (_, _, fixed_sha) = FIXED
                    .iter()
                    .find(|(name, _, _)| *name == usb_relative)
                    .unwrap();
                assert_ne!(hash(&usb).unwrap(), *fixed_sha);
                assert_eq!(projection.originals.len(), 20);
                assert_eq!(projection.applied_patches.len(), 15);
            }
            assert!(validate_fixed(&source).is_err());
            std::mem::forget(projection);
            recover(&journal, &source).unwrap();
            validate_original(&repo, &source).unwrap();
            for (path, permissions, modified) in original_metadata {
                let metadata = fs::metadata(path).unwrap();
                assert_eq!(metadata.permissions().mode(), permissions);
                assert_eq!(metadata.modified().unwrap(), modified);
            }
            assert!(!journal.exists());
        }
    }

    #[test]
    fn framework_usb_timeout_projection_preserves_preimage_through_save_apply_and_recovery() {
        // Only the original source and complete official patch are processed.
        // A saved-only interruption and both applied retirement branches must
        // restore the one original file, including its nanosecond timestamp.
        for (apply, interrupted) in [(false, true), (true, false), (true, true)] {
            let directory = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(directory.path());
            let relative = "services/usb/java/com/android/server/usb/UsbDeviceManager.java";
            let usb = source.join(PROJECT).join(relative);
            let original_bytes = fs::read(&usb).unwrap();
            fs::set_permissions(&usb, fs::Permissions::from_mode(0o640)).unwrap();
            let modified =
                std::time::UNIX_EPOCH + std::time::Duration::new(1_700_000_000, 123_456_789);
            fs::File::open(&usb)
                .unwrap()
                .set_modified(modified)
                .unwrap();
            let before = fs::metadata(&usb).unwrap();
            assert_eq!(before.modified().unwrap(), modified);
            validate_original(&repo, &source).unwrap();

            let journal = directory.path().join("usb-timeout-projection.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            projection.save(&usb).unwrap();
            assert!(journal.is_file());
            assert_eq!(projection.originals.len(), 1);
            assert!(projection.applied_patches.is_empty());
            if apply {
                let (patch, _, _, commit) = PATCHES
                    .iter()
                    .find(|(_, _, _, commit)| *commit == "7ae3d28551aea0937e1ce6ad701edef2c9f04bcb")
                    .unwrap();
                assert_eq!(*commit, "7ae3d28551aea0937e1ce6ad701edef2c9f04bcb");
                projection
                    .patch(&source, PROJECT, &repo.join(patch))
                    .unwrap();
                assert_eq!(projection.applied_patches.len(), 1);
                let (_, bytes, expected) =
                    FIXED.iter().find(|(name, _, _)| *name == relative).unwrap();
                exact(&source, &format!("{PROJECT}/{relative}"), *bytes, expected).unwrap();
                assert_ne!(fs::read(&usb).unwrap(), original_bytes);
            } else {
                assert_eq!(fs::read(&usb).unwrap(), original_bytes);
            }
            // save() followed by patch() must keep the first preimage once.
            assert_eq!(projection.originals.len(), 1);
            let saved = &projection.originals[0];
            assert_eq!(saved.path, usb);
            assert_eq!(saved.bytes.as_deref(), Some(original_bytes.as_slice()));
            assert_eq!(saved.permissions_mode, Some(before.permissions().mode()));
            assert_eq!(saved.modified, Some(modified));
            if interrupted {
                std::mem::forget(projection);
                recover(&journal, &source).unwrap();
            } else {
                projection.restore().unwrap();
            }
            validate_original(&repo, &source).unwrap();
            assert_eq!(fs::read(&usb).unwrap(), original_bytes);
            let after = fs::metadata(&usb).unwrap();
            assert_eq!(after.permissions().mode(), before.permissions().mode());
            assert_eq!(after.modified().unwrap(), modified);
            assert!(!journal.exists());
        }
    }

    fn preserve_fixture_metadata(source: &Path) -> Vec<(PathBuf, u32, std::time::SystemTime)> {
        let mut before = Vec::new();
        for (index, (relative, _, _)) in ORIGINALS.iter().enumerate() {
            let path = source.join(PROJECT).join(relative);
            let modified = std::time::UNIX_EPOCH
                + std::time::Duration::new(1_700_000_000, 123_456_789 + index as u32);
            fs::set_permissions(&path, fs::Permissions::from_mode(0o640)).unwrap();
            fs::File::open(&path)
                .unwrap()
                .set_modified(modified)
                .unwrap();
            let meta = fs::metadata(&path).unwrap();
            assert_eq!(meta.modified().unwrap(), modified);
            before.push((path, meta.permissions().mode(), modified));
        }
        before
    }

    fn assert_recovered_fixture(
        repo: &Path,
        source: &Path,
        journal: &Path,
        before: Vec<(PathBuf, u32, std::time::SystemTime)>,
    ) {
        validate_original(repo, source).unwrap();
        for (path, mode, modified) in before {
            let actual = fs::metadata(path).unwrap();
            assert_eq!(actual.permissions().mode(), mode);
            assert_eq!(actual.modified().unwrap(), modified);
        }
        assert!(!journal.exists());
    }

    #[test]
    fn framework_companion_client_aidl_server_projection_recovers_each_original_once() {
        for applied in 0..=3 {
            for interrupted in [false, true] {
                let directory = tempfile::tempdir().unwrap();
                let (repo, source) = fixture(directory.path());
                let before = preserve_fixture_metadata(&source);
                let service = source.join(PROJECT).join(
                    "services/companion/java/com/android/server/companion/CompanionDeviceManagerService.java",
                );
                let original_service = fs::read(&service).unwrap();
                let journal = directory.path().join("companion-projection.json");
                let mut projection = Projection::new(journal.clone()).unwrap();
                validate_original(&repo, &source).unwrap();
                projection.save(&service).unwrap();
                for (patch, _, _, _) in &PATCHES[16..16 + applied] {
                    projection
                        .patch(&source, PROJECT, &repo.join(patch))
                        .unwrap();
                }
                assert_eq!(projection.originals.len(), [1, 1, 3, 6][applied]);
                assert_eq!(projection.applied_patches.len(), applied);
                let saved: Vec<_> = projection
                    .originals
                    .iter()
                    .filter(|item| item.path == service)
                    .collect();
                assert_eq!(saved.len(), 1);
                assert_eq!(saved[0].bytes.as_deref(), Some(original_service.as_slice()));
                for relative in [
                    "core/java/android/companion/CompanionDeviceManager.java",
                    "core/java/android/companion/ICompanionDeviceManager.aidl",
                    "services/companion/java/com/android/server/companion/datatransfer/SystemDataTransferProcessor.java",
                ] {
                    let pins = if applied == 3 { FIXED } else { ORIGINALS };
                    let (_, bytes, digest) =
                        pins.iter().find(|(name, _, _)| *name == relative).unwrap();
                    exact(&source, &format!("{PROJECT}/{relative}"), *bytes, digest).unwrap();
                }
                if applied == 1 || applied == 2 {
                    let (_, _, final_digest) = FIXED.iter().find(|(name, _, _)| *name ==
                        "services/companion/java/com/android/server/companion/CompanionDeviceManagerService.java").unwrap();
                    assert_ne!(hash(&service).unwrap(), *final_digest);
                }
                if interrupted {
                    std::mem::forget(projection);
                    recover(&journal, &source).unwrap();
                } else {
                    projection.restore().unwrap();
                }
                assert_recovered_fixture(&repo, &source, &journal, before);
            }
        }
    }

    fn assert_policy_saved_preimages(projection: &Projection, source: &Path, temporary: &Path) {
        for relative in [
            "services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyManagerService.java",
            "services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyEngine.java",
        ] {
            let path = source.join(PROJECT).join(relative);
            let saved: Vec<_> = projection
                .originals
                .iter()
                .filter(|item| item.path == path)
                .collect();
            assert!(saved.len() <= 1);
            if let Some(original) = saved.first() {
                let (_, bytes, digest) = ORIGINALS
                    .iter()
                    .find(|(name, _, _)| *name == relative)
                    .unwrap();
                let body = original.bytes.as_ref().unwrap();
                assert_eq!(body.len() as u64, *bytes);
                let copy = temporary.join("saved-original.bin");
                write(&copy, body).unwrap();
                assert_eq!(hash(&copy).unwrap(), *digest);
            }
        }
    }

    fn assert_existing_new_files_reject_before_projection() {
        // Even a dangling link rejects before a journal may replace an
        // official new-file destination. The unrelated node is preserved.
        for kind in 0..3 {
            let directory = tempfile::tempdir().unwrap();
            let (repo, source) = fixture(directory.path());
            let path = source.join(PROJECT).join(ABSENT_ORIGINALS[0]);
            match kind {
                0 => write(&path, b"pre-existing unrelated bytes").unwrap(),
                1 => fs::create_dir(&path).unwrap(),
                _ => std::os::unix::fs::symlink(directory.path().join("missing"), &path).unwrap(),
            }
            let journal = directory.path().join("must-not-exist.json");
            let mut projection = Projection::new(journal.clone()).unwrap();
            assert!(project(&mut projection, &repo, &source).is_err());
            assert!(projection.originals.is_empty());
            assert!(!journal.exists());
            assert!(fs::symlink_metadata(path).is_ok());
        }
    }

    #[test]
    fn framework_policy_new_files_and_two_stage_engine_recover_exact_original_state() {
        // Keep this policy-only recovery boundary independent of new files
        // added by unrelated later official patches.
        let policy_absent: &[&str] = &[
            "core/java/android/app/admin/BundlePolicyTypeVerifier.java",
            "services/tests/servicestests/src/com/android/server/devicepolicy/BundlePolicySerializerTest.kt",
        ];
        assert!(
            policy_absent
                .iter()
                .all(|path| ABSENT_ORIGINALS.contains(path))
        );
        for applied in 0..=5 {
            for interrupted in [false, true] {
                let directory = tempfile::tempdir().unwrap();
                let (repo, source) = fixture(directory.path());
                let before = preserve_fixture_metadata(&source);
                validate_original(&repo, &source).unwrap();
                let journal = directory.path().join("device-policy-projection.json");
                let mut projection = Projection::new(journal.clone()).unwrap();
                for relative in policy_absent {
                    projection
                        .save(&source.join(PROJECT).join(relative))
                        .unwrap();
                }
                for (patch, _, _, _) in &PATCHES[19..19 + applied] {
                    projection
                        .patch(&source, PROJECT, &repo.join(patch))
                        .unwrap();
                }
                assert_eq!(projection.originals.len(), [2, 5, 8, 8, 12, 12][applied]);
                assert_eq!(projection.applied_patches.len(), applied);
                for relative in policy_absent {
                    let path = source.join(PROJECT).join(relative);
                    let saved: Vec<_> = projection
                        .originals
                        .iter()
                        .filter(|item| item.path == path)
                        .collect();
                    assert_eq!(saved.len(), 1);
                    assert!(saved[0].bytes.is_none());
                    assert!(saved[0].modified.is_none());
                    assert!(saved[0].permissions_mode.is_none());
                    if applied == 0 {
                        assert!(
                            fs::symlink_metadata(&path)
                                .is_err_and(|error| error.kind() == std::io::ErrorKind::NotFound)
                        );
                    } else {
                        let (_, bytes, digest) = FIXED
                            .iter()
                            .find(|(name, _, _)| *name == *relative)
                            .unwrap();
                        exact(&source, &format!("{PROJECT}/{relative}"), *bytes, digest).unwrap();
                    }
                }
                assert_policy_saved_preimages(&projection, &source, directory.path());
                if applied >= 4 {
                    let relative = "services/devicepolicy/java/com/android/server/devicepolicy/DevicePolicyEngine.java";
                    let (_, bytes, final_digest) =
                        FIXED.iter().find(|(name, _, _)| *name == relative).unwrap();
                    if applied == 4 {
                        let intermediate = exact(
                            &source,
                            &format!("{PROJECT}/{relative}"),
                            118751,
                            "3314de14df76e403eb0829a0dbae896b07cc4e54e6cf6d4875075b6667a14b82",
                        )
                        .unwrap();
                        assert_ne!(hash(&intermediate).unwrap(), *final_digest);
                    } else {
                        exact(
                            &source,
                            &format!("{PROJECT}/{relative}"),
                            *bytes,
                            final_digest,
                        )
                        .unwrap();
                    }
                }
                if interrupted {
                    std::mem::forget(projection);
                    recover(&journal, &source).unwrap();
                } else {
                    projection.restore().unwrap();
                }
                assert_recovered_fixture(&repo, &source, &journal, before);
            }
        }
        assert_existing_new_files_reject_before_projection();
    }

    fn paired_output_fixture(out: &Path, product: &str) -> serde_json::Value {
        let product_out = out.join("target/product").join(product);
        let mut info = serde_json::json!({});
        for (module, provider, relative) in INSTALLED_MODULES {
            let path = product_out.join(relative);
            write(
                &path,
                format!("ordinary identity fixture for {module}; no Android execution"),
            )
            .unwrap();
            info[*module] = serde_json::json!({"path": [provider], "installed": [path]});
        }
        let (module, provider, relative) = SYSTEM_UI_MODULE;
        let path = product_out.join(relative);
        write(
            &path,
            b"ordinary SystemUI identity fixture; no executable APK",
        )
        .unwrap();
        info[module] = serde_json::json!({"path": [provider], "installed": [path]});
        for (module, provider) in [
            (
                "FrameworksCoreTests",
                "frameworks/base/core/tests/coretests",
            ),
            ("WmTests", "frameworks/base/services/tests/wmtests"),
            (
                "FrameworksServicesTests",
                "frameworks/base/services/tests/servicestests",
            ),
            ("UsbTests", "frameworks/base/tests/UsbTests"),
            ("AudioServiceTests", "frameworks/base/services/tests/audio"),
            (
                "FrameworksUiServicesNotificationTests",
                "frameworks/base/services/tests/uiservicestests",
            ),
        ] {
            let path = product_out
                .join("testcases")
                .join(module)
                .join(format!("{module}.apk"));
            write(
                &path,
                b"ordinary output-identity fixture; not an executable APK",
            )
            .unwrap();
            info[module] = serde_json::json!({"path": [provider], "installed": [path]});
        }
        write(
            &product_out.join("module-info.json"),
            serde_json::to_vec(&info).unwrap(),
        )
        .unwrap();
        info
    }

    fn assert_missing_or_aliased_pair_rejected(
        out: &Path,
        product: &str,
        request: FixedProductionRequest<'_>,
    ) {
        let framework = out
            .join("target/product")
            .join(product)
            .join("system/framework/framework.jar");
        let saved = out.join("original-framework.jar");
        fs::rename(&framework, &saved).unwrap();
        assert!(completed_artifacts(out, product, request).is_err());
        std::os::unix::fs::symlink(&saved, &framework).unwrap();
        assert!(completed_artifacts(out, product, request).is_err());
        fs::remove_file(&framework).unwrap();
        fs::hard_link(&saved, &framework).unwrap();
        assert!(completed_artifacts(out, product, request).is_err());
        fs::remove_file(&framework).unwrap();
        fs::rename(saved, framework).unwrap();
        completed_artifacts(out, product, request).unwrap();
    }

    fn assert_bad_pair_metadata_rejected(
        out: &Path,
        product: &str,
        request: FixedProductionRequest<'_>,
        info: &serde_json::Value,
    ) {
        let product_out = out.join("target/product").join(product);
        let info_path = product_out.join("module-info.json");
        for mutation in 0..6 {
            let mut bad = info.clone();
            match mutation {
                0 => {
                    let original = bad
                        .as_object_mut()
                        .unwrap()
                        .remove("framework-minus-apex")
                        .unwrap();
                    bad["framework"] = original;
                }
                1 => {
                    bad["framework-minus-apex"]["path"] = serde_json::json!(["frameworks/foreign"])
                }
                2 => {
                    bad["framework-minus-apex"]["path"] =
                        serde_json::json!(["frameworks/base", "frameworks/base"])
                }
                3 => {
                    bad["framework-minus-apex"]["installed"] =
                        serde_json::json!([product_out.join("system/framework/other.jar")])
                }
                4 => {
                    bad["framework-minus-apex"]["installed"] = serde_json::json!([
                        out.join("target/product/foreign/system/framework/framework.jar")
                    ])
                }
                _ => {
                    let original = bad["framework-minus-apex"]["installed"][0].clone();
                    bad["framework-minus-apex"]["installed"] =
                        serde_json::json!([original.clone(), original]);
                }
            }
            write(&info_path, serde_json::to_vec(&bad).unwrap()).unwrap();
            assert!(
                completed_artifacts(out, product, request).is_err(),
                "mutation {mutation}"
            );
        }
    }

    #[test]
    fn framework_actual_client_and_services_outputs_require_one_coherent_provider_pair() {
        let product = "droidloom_x86_64";
        let full = FixedProductionRequest::Existing(SoongDependencyMode::Strict, COHERENT_TARGETS);
        let directory = tempfile::tempdir().unwrap();
        let out = directory.path().canonicalize().unwrap();
        let product_out = out.join("target/product").join(product);
        let info_path = product_out.join("module-info.json");
        let info = paired_output_fixture(&out, product);
        for request in [
            full,
            FixedProductionRequest::FrameworkAsbOnProductionSource,
            FixedProductionRequest::WmSecurityOnProductionSource,
        ] {
            let artifacts = completed_artifacts(&out, product, request).unwrap();
            assert_eq!(artifacts[0]["module"], "framework-minus-apex");
            assert_eq!(artifacts[1]["module"], "services");
            assert_ne!(
                artifacts[0]["artifact"]["inode"],
                artifacts[1]["artifact"]["inode"]
            );
            assert_eq!(
                artifacts.last().unwrap()["module_info"]["sha256"],
                hash(&info_path).unwrap()
            );
            let expected = match request {
                FixedProductionRequest::FrameworkAsbOnProductionSource => 10,
                FixedProductionRequest::WmSecurityOnProductionSource => 4,
                _ => 3,
            };
            assert_eq!(artifacts.len(), expected);
            if matches!(
                request,
                FixedProductionRequest::WmSecurityOnProductionSource
            ) {
                assert_eq!(artifacts[2]["module"], "WmTests");
            }
        }
        let mut missing_wm = info.clone();
        missing_wm.as_object_mut().unwrap().remove("WmTests");
        write(&info_path, serde_json::to_vec(&missing_wm).unwrap()).unwrap();
        assert!(
            completed_artifacts(
                &out,
                product,
                FixedProductionRequest::WmSecurityOnProductionSource
            )
            .is_err()
        );
        write(&info_path, serde_json::to_vec(&info).unwrap()).unwrap();
        for targets in [
            &["services", "module-info"][..],
            &["framework-minus-apex", "module-info"],
            &["services", "framework", "module-info"],
            &["services", "framework-minus-apex"],
            &[
                "services",
                "services",
                "framework-minus-apex",
                "module-info",
            ],
        ] {
            let request = FixedProductionRequest::Existing(SoongDependencyMode::Strict, targets);
            assert!(validate_request(request, product).is_err());
            assert!(completed_artifacts(&out, product, request).is_err());
        }
        assert!(!required_for_targets(
            FixedProductionRequest::VendorImageOnProductionSource.requested_targets()
        ));
        assert!(
            validate_request(
                FixedProductionRequest::VendorImageOnProductionSource,
                product
            )
            .is_err()
        );
        assert_bad_pair_metadata_rejected(&out, product, full, &info);
        write(&info_path, serde_json::to_vec(&info).unwrap()).unwrap();
        assert_missing_or_aliased_pair_rejected(&out, product, full);
        fs::remove_file(&info_path).unwrap();
        assert!(completed_artifacts(&out, product, full).is_err());
    }

    #[test]
    fn framework_system_ui_apk_binding_is_separate_from_framework_pair() {
        let product = "droidloom_x86_64";
        let directory = tempfile::tempdir().unwrap();
        let out = directory.path().canonicalize().unwrap();
        let info = paired_output_fixture(&out, product);
        let product_out = out.join("target/product").join(product);
        let info_path = product_out.join("module-info.json");
        let full = FixedProductionRequest::Existing(SoongDependencyMode::Strict, COHERENT_TARGETS);
        let focused = FixedProductionRequest::FrameworkAsbOnProductionSource;
        assert!(
            !completed_artifacts(&out, product, full)
                .unwrap()
                .iter()
                .any(|row| row["module"] == "SystemUI")
        );
        let outputs = completed_artifacts(&out, product, focused).unwrap();
        let ui: Vec<_> = outputs
            .iter()
            .filter(|row| row["module"] == "SystemUI")
            .collect();
        assert_eq!(ui.len(), 1);
        assert_eq!(ui[0]["provider"], SYSTEM_UI_MODULE.1);
        assert_eq!(
            ui[0]["artifact"]["path"],
            product_out.join(SYSTEM_UI_MODULE.2).to_str().unwrap()
        );
        for mutation in 0..5 {
            let mut bad = info.clone();
            match mutation {
                0 => {
                    bad.as_object_mut().unwrap().remove("SystemUI");
                }
                1 => {
                    bad["SystemUI"]["path"] = serde_json::json!(["frameworks/foreign"]);
                }
                2 => {
                    bad["SystemUI"]["installed"] = serde_json::json!([
                        product_out.join("system/priv-app/SystemUI/SystemUI.apk")
                    ]);
                }
                3 => {
                    let original = bad["SystemUI"]["installed"][0].clone();
                    bad["SystemUI"]["installed"] = serde_json::json!([original.clone(), original]);
                }
                _ => {
                    bad["SystemUI"]["installed"] = serde_json::json!([
                        product_out.join(SYSTEM_UI_MODULE.2),
                        product_out.join("system_ext/priv-app/Other/Other.apk")
                    ]);
                }
            }
            write(&info_path, serde_json::to_vec(&bad).unwrap()).unwrap();
            assert!(
                completed_artifacts(&out, product, focused).is_err(),
                "mutation {mutation}"
            );
            assert!(completed_artifacts(&out, product, full).is_ok());
        }
        write(&info_path, serde_json::to_vec(&info).unwrap()).unwrap();
        let actual_ui = product_out.join(SYSTEM_UI_MODULE.2);
        fs::remove_file(actual_ui).unwrap();
        assert!(completed_artifacts(&out, product, focused).is_err());
        assert!(completed_artifacts(&out, product, full).is_ok());
    }

    #[test]
    fn framework_focused_selects_complete_production651_lock_and_original_providers() {
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .canonicalize()
            .unwrap();
        let request = FixedProductionRequest::FrameworkAsbOnProductionSource;
        let selected = request.source_lock(&repo).unwrap();
        assert_eq!(selected, repo.join(production_source::LOCK_PATH));
        assert_ne!(
            selected,
            FixedProductionRequest::NativePair
                .source_lock(&repo)
                .unwrap()
        );
        let lock = droidloom_source::load_lock(&selected).unwrap();
        let plan = droidloom_source::production_car::build_plan(&lock).unwrap();
        assert_eq!(plan.projects.len(), 653);
        let original = droidloom_source::load_lock(
            &repo.join("android/manifest/production-full-source-lock.json"),
        ).unwrap();
        let original_plan = droidloom_source::production_full::build_plan(&original).unwrap();
        assert_eq!(original_plan.projects.len(), 651);
        let mut expected_projects = original_plan.projects.clone();
        expected_projects.iter_mut()
            .find(|project| project.path == Path::new(droidloom_source::production_lint::HEALTH_PATH))
            .unwrap().sparse_paths.push(droidloom_source::production_lint::LINT_PATH.into());
        for &(path, _, cone) in droidloom_source::production_apex_tests::PROVIDERS {
            expected_projects.iter_mut()
                .find(|project| project.path == Path::new(path))
                .unwrap().sparse_paths.push(cone.into());
        }
        for &(path, _, cone) in droidloom_source::production_car::PROVIDERS {
            expected_projects.iter_mut()
                .find(|project| project.path == Path::new(path))
                .unwrap().sparse_paths.push(cone.into());
        }
        assert_eq!(&plan.projects[..651], expected_projects.as_slice());
        assert_eq!(plan.links.len(), 8);
        assert!(!plan.unrestricted_repo_sync);
        assert_eq!(request.projection_targets(), TARGETS);
        assert_eq!(request.requested_targets(), TARGETS);
        assert_eq!(TARGETS.last(), Some(&"module-info"));
        assert_eq!(CVES.len(), 31);
        assert_eq!(PATCHES.len(), 33);
        assert_eq!(ORIGINALS.len(), 80);
        assert_eq!(FIXED.len(), 65);
        assert_eq!(PROVIDERS.len(), 18);
        assert_eq!(ABSENT_ORIGINALS.len(), 3);
        assert!(TARGETS.contains(&"framework-minus-apex"));
        for (module, provider, _) in INSTALLED_MODULES {
            assert!(TARGETS.contains(module));
            let blueprint = if *provider == "frameworks/base" {
                "Android.bp"
            } else {
                "services/Android.bp"
            };
            assert!(PROVIDERS.iter().any(|(name, _, _)| *name == blueprint));
        }
        assert!(TARGETS.contains(&"UsbTests"));
        assert!(PROVIDERS.contains(&(
            "tests/UsbTests/Android.bp",
            1706,
            "4cde9add294521d36a98c56ce0861745e2d0845e8448ec58bc5ff0a0d0263258",
        )));
        assert!(TARGETS.contains(&"AudioServiceTests"));
        assert!(TARGETS.contains(&"WmTests"));
        assert!(TARGETS.contains(&"FrameworksUiServicesNotificationTests"));
        assert!(PROVIDERS.contains(&(
            "services/tests/uiservicestests/Android.bp",
            5000,
            "5f6c17f31fa0408b4069d653b960ddf7dc2955bb2bcdbd6467afd3f7cde00c54",
        )));
        assert!(PROVIDERS.contains(&(
            "services/tests/wmtests/Android.bp",
            51079,
            "23b4082ab5de81b25facce2629fcf65a34c01e057399fb385a13a825d269b87c",
        )));
        assert!(
            PROVIDERS
                .iter()
                .any(|(name, _, _)| *name == "services/tests/audio/Android.bp")
        );
        assert!(!TARGETS.contains(&"module-info.json"));
        assert_eq!(request.source_mode(), SoongDependencyMode::Strict);
        assert_eq!(hash(&selected).unwrap(), production_source::LOCK_SHA);
    }

    #[test]
    fn framework_default_full_and_focused_services_commands_use_strict_user_source() {
        for request in [
            FixedProductionRequest::Existing(SoongDependencyMode::Strict, crate::android::TARGETS),
            FixedProductionRequest::FrameworkAsbOnProductionSource,
            FixedProductionRequest::WmSecurityOnProductionSource,
        ] {
            assert!(required_for_targets(request.requested_targets()));
            validate_request(request, "droidloom_x86_64").unwrap();
            let d = tempfile::tempdir().unwrap();
            let selected = request.soong_targets(d.path(), "droidloom_x86_64").unwrap();
            let mut command = production_soong_command(
                d.path(),
                d.path(),
                d.path(),
                "droidloom_x86_64",
                1,
                &selected,
            )
            .unwrap();
            request
                .configure_dependencies(&mut command, "droidloom_x86_64")
                .unwrap();
            configure_command(request, "droidloom_x86_64", &mut command).unwrap();
            for (key, value) in [
                ("TARGET_BUILD_VARIANT", "user"),
                ("TARGET_RELEASE", "cp2a"),
                ("ALLOW_MISSING_DEPENDENCIES", "false"),
                ("SELINUX_IGNORE_NEVERALLOWS", "false"),
            ] {
                assert!(
                    command
                        .get_envs()
                        .any(|(k, v)| k == key && v == Some(std::ffi::OsStr::new(value))),
                    "{key}"
                );
            }
            let mut args = vec![
                std::ffi::OsString::from("--make-mode"),
                std::ffi::OsString::from("-j1"),
            ];
            args.extend(selected.iter().map(|p| p.as_os_str().to_owned()));
            assert_eq!(
                command.get_args().map(|v| v.to_owned()).collect::<Vec<_>>(),
                args
            );
        }
    }
}
