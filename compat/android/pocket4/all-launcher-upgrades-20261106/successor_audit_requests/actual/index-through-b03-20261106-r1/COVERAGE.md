# APK audit coverage through batch 03

6 of 45 Launcher packages have complete actual APK audits; 39 remain pending.
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

## Remaining evidence gaps

These package names are expected by the fixed 45-package plan. Their reference APK hashes are retained in index.json; those references are not marked as new audit results.

- com.Hyatt.hyt
- com.enflick.android.TextNow
- com.szzc
- tv.danmaku.bili
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
