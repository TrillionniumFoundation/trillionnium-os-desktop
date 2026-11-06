# APK audit coverage through batch 04

10 of 45 Launcher packages have complete actual APK audits; 35 remain pending.
Effective grants remain UNKNOWN_NOT_QUERIED. Production ready: 0. Cleanup: 0.

## Settled package evidence

| Package | UID | Actual version / code | min / target SDK | ABI | Exact APK SHA256 | Requested / defined permission names |
| --- | ---: | --- | --- | --- | --- | --- |
| org.fcitx.fcitx5.android | 10150 | 0.1.3-0-g048f581c / 114 | 23 / 36 | x86_64 | aaeb569fc3e9e8ec532b0ea33be39ce77b143c8add824d172f17356ddc3b9ed2 | 3 / 2 |
| com.google.android.gms | 10118 | 0.3.17.252432 / 252432034 | 19 / 29 | x86_64 | e5e6cba078bdec812b5450599350e5c1a12c8b7438da5bf77123af170f8c1a35 | 65 / 25 |
| com.lianjia.beike | 10143 | 3.06.71 / 3067100 | 23 / 31 | arm64-v8a | c7985ed41b91c782af8acb04b1868419cca8bc1fc52862bf6c89fa86b65c81fb | 63 / 6 |
| com.rytong.ceair | 10145 | 9.5.16 / 239 | 24 / 33 | arm64-v8a | a6da8d746f98cae884f6b0137b5c7e8412836adf75530b763dae1536c75522ce | 60 / 6 |
| com.rytong.airchina | 10132 | 7.53.0 / 75300 | 24 / 36 | arm64-v8a, armeabi-v7a | 5c15462878b578d774f3a1e66c93329158791280c2a94237ac59224c019384e3 | 63 / 6 |
| com.tencent.mm | 10114 | 8.0.80 / 3220 | 24 / 34 | arm64-v8a | 9d9b6c516e8e07e437c81485fde21fe13ce4f61b37d19e793fff40c71be39c0e | 100 / 18 |
| com.Hyatt.hyt | 10138 | 26.9.0 / 26090096 | 35 / 36 | arm64-v8a | 418dbf6fd2a42f87b79cc4d0a806c1d13baec34b8f85f48104a6c855b6f7d5e2, 9fd69f616d5a20d549647690ffc0adc50631bf040400b7d0309ad1454dd1680f, 74892b430c50b442d3f9b19dd28083a6912bc96c229227bda7af1c82e62c3d12 | 25 / 1 |
| com.enflick.android.TextNow | 10127 | 26.40.1.0 / 15733 | 29 / 36 | x86_64 | 28dda0ea2cbc2902f072fff365000cdadb712085fcea98b89d7dabf9f3a5cd95, 5ca97c3583d864190631597c93c1a25968c18b9de52826db956eeb2b5f38028c, 4b343a643d8f668bd35678051a96c62cd1b9fa9c487342db52a692b27ca008ab | 82 / 2 |
| com.szzc | 10146 | 9.6.1 / 327 | 23 / 33 | arm64-v8a, armeabi-v7a | 997067da78cb0d8d0fde2adb58e26c90815de1daec4c1ee02beae39ce2ceda24 | 39 / 4 |
| tv.danmaku.bili | 10117 | 9.18.0 / 9180300 | 24 / 35 | arm64-v8a | 33b302b285bdbb5ee1e3030c5d65a88b8229ff3d7bbf78df105600e968109bfc | 76 / 6 |

## Remaining evidence gaps

These package names are expected by the fixed 45-package plan. Their reference APK hashes are retained in index.json; those references are not marked as new audit results.

- com.MobileTicket
- com.amazon.mShop.android.shopping
- com.android.calendar
- com.android.camera2
- com.android.contacts
- com.android.deskclock
- com.android.dialer
- com.android.documentsui
- com.android.gallery3d
- com.android.messaging
- com.android.quicksearchbox
- com.android.settings
- com.android.threadnetwork.demoapp
- com.bestbuy.android
- com.ehi.national.mobile
- com.hertz.android.digital
- com.hilton.android.hhonors
- com.ihg.apps.android
- com.jingdong.app.mall
- com.marriott.mrt
- com.pinger.textfree
- com.sankuai.meituan.takeoutnew
- com.sdu.didi.psnger
- com.ss.android.ugc.aweme
- com.taobao.taobao
- com.ubercab
- com.united.mobile.android
- com.xunmeng.pinduoduo
- com.zhubajie.client
- com.zillow.android.streeteasy
- ctrip.android.view
- jp.co.ana.android.tabidachi
- local.pocket4.fixture
- org.chromium.webview_shell
- org.droidloom.qa.editorcontract

Network operation, effective grants, login or visitor flow, long running behaviour, restart recovery, and production readiness are not established by this APK-only index.
The declared-permissions index preserves every observed name and raw attribute; it does not strip names or infer a permission decision.
