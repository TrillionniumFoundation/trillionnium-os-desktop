# 全46项来源缺口与 IHG 公开交付候选

选择 **IHG 5.110.0 / code50023496** 作为下一条公开交付候选。它是第三方公开分发页面列出的单体 APK，当前未下载、未验签、未安装。厂商官网和 Play 只用于核对应用身份；没有声称厂商授权 APKMirror。

当前已装 IHG 为 **5.108.1 / code50023219 / UID10137**，单APK44,999,052B、SHA256 `c12bb3bae3514c94caaca0a4ef6e8f1ad4491cbce57fd2a15be48b83b4c85b90`。页面候选47,668,450B、SHA256 `f6be54a948d96c34579f280b75d3e139bc3d430847173e14197e208331351f2f`，列出 ARM64及另外四ABI。页面证书摘要与当前PM记录相同，只构成待核线索。

官方先前S22记录为5.110.0，但本地只保留S44/原矩阵的派生引用，没有重取S22原文；本次新打开的Play正文只显示2026-11-03更新，不显示版本号/code。不能据此宣称官方全球最新版或目标上可用最新版已经证明。

## 精确来源链

- https://www.ihg.com.cn/content/cn/zh/support/mobile
- https://play.google.com/store/apps/details?id=com.ihg.apps.android
- https://www.apkmirror.com/apk/ihg-mobile/ihg-hotel-deals-rewards/ihg-one-rewards-book-hotels-5-110-0-release/
- https://www.apkmirror.com/apk/ihg-mobile/ihg-hotel-deals-rewards/ihg-one-rewards-book-hotels-5-110-0-release/ihg-one-rewards-book-hotels-5-110-0-android-apk-download/

官网→Play 是官方身份链；variant→普通下载中间页是独立的第三方分发链。现已见的临时key不会进入执行请求。

## 待审唯一宿主请求

`exact-page-process-request.review-only.json` 固定普通UID1000、两次HTML GET、每次2MiB、总120秒/外层180秒、256MiB、nice10。先从variant完整HTML选唯一literal中间页链接，至少等15秒，再取该HTML；只记录其中唯一here链接，不抓APK。默认urllib身份/系统TLS，不跟重定向、不自动重试，403/挑战/过期/格式歧义即失败保留。最终原始stdout、durable exit0和完整FD身份恢复共同证明这个有限观察完成，不能用页面result单独升级候选资格。

实际最终URL未知，因此当前没有伪造一个可执行的APK下载URL。待新literal返回后才能封单次完整GET与普通验签；该后续请求仍为独立新来源范围，旧ALLOWED和Main/安装权限不变。

## 46项完整来源差距

以下“直链未核实”不等同于“无法获得任何合法公开同包签名包”。12项已实际正常升级仍缺业务验收；17项尚未升级的商业应用中，IHG是本轮新增的具体公开单体候选。11个AOSP组件/演示、WebView测试壳、两个自有QA、NDK未知来源和两个开源服务/输入法分别保留各自构建或发布约束。

| App / 包名 | 当前版本 / 有效code | 来源现状与缺口 | 正常下一步 |
|---|---|---|---|
| Hyatt<br>`com.Hyatt.hyt` | 26.9.0 / 26090096 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| Railway 12306<br>`com.MobileTicket` | 5.9.4.5 / 275 | 5.9.6.8已知交付只有105119744B已验证前缀；两个TLS失败保留，未重试相同端点。 | 厂商新发布的正常完整同包交付，或正常商店/新公开分发路径；完整验签前不升级。 |
| Amazon Shopping<br>`com.amazon.mShop.android.shopping` | 32.18.0.100 / 1243240206 | 公开32.20.0.100候选为base+3 splits；普通下载页已报nonce失效，未重放。中国版包名不同。 | 新的正常公开交付需版本关联和完整split集合，不能用中国版替换。 |
| Calendar<br>`com.android.calendar` | 17 / 37 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Camera<br>`com.android.camera2` | 2.0.002 / 20002000 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Contacts<br>`com.android.contacts` | 1.7.34 / 10734 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Clock<br>`com.android.deskclock` | 17 / 37 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Phone<br>`com.android.dialer` | 23.0 / 2900000 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Files<br>`com.android.documentsui` | 17 / 37 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Gallery<br>`com.android.gallery3d` | 1.1.40030 / 40030 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Messaging<br>`com.android.messaging` | 1.0.001 / 10001040 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Search<br>`com.android.quicksearchbox` | 17 / 37 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Settings<br>`com.android.settings` | 17 / 37 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| ThreadNetworkDemoApp<br>`com.android.threadnetwork.demoapp` | 17 / 37 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Best Buy<br>`com.bestbuy.android` | 26.9.20 / 2012312321 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| National<br>`com.ehi.national.mobile` | 6.15.0.9354 / 9354 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| TextNow<br>`com.enflick.android.TextNow` | 26.40.1.0 / 15733 | 完整同包新包未取得；官方说明北美资格，目标真实账户/设备/地区资格未知，不规避。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| NDK测试入口（标签未提取）<br>`com.example.ndk_tests` | 未声明 / 0 | 实际NDK APK已正常审计，版本属性未声明/PM有效code0；所有者与原始来源仍未知。 | 先取得真实owner/source/build来源，不将测试入口误认商店产品。 |
| microG Settings<br>`com.google.android.gms` | 0.3.17.252432 / 252432034 | 本次公开latest导航仍是当前release；已装字节与原官方asset引用匹配，运行回归仍待完成。 | 保持当前服务，验证业务兼容性。 |
| Hertz<br>`com.hertz.android.digital` | 5.6.0 / 1389 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| Hilton Honors<br>`com.hilton.android.hhonors` | 2026.9.29 / 1004 | 已查中国官网/商店为cn.hilton.android.hhonors，不能更新当前com包；其他同包公开交付未知。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| IHG<br>`com.ihg.apps.android` | 5.108.1 / 50023219 | 公开单体候选5.110.0/code50023496；47,668,450B/ABI/签名标签仅页面声明。新Play正文未给code。 | 固定页面请求→一次fresh literal链接→独立完整下载与普通验签。 |
| JD.COM<br>`com.jingdong.app.mall` | 16.1.50 / 102918 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| 贝壳找房<br>`com.lianjia.beike` | 3.06.71 / 3067100 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| Marriott<br>`com.marriott.mrt` | 10.79.0 / 671 | S44普通UID1000页面请求HTTP403，已停且保留失败；其他合法交付未被排除。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| TextFree<br>`com.pinger.textfree` | 13.28 / 260172 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| Air China<br>`com.rytong.airchina` | 7.53.0 / 75300 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| China Eastern Airlines (CEA)<br>`com.rytong.ceair` | 9.5.16 / 239 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| 美团外卖<br>`com.sankuai.meituan.takeoutnew` | 8.83.2 / 800830002 | 已取得候选与当前合法签名不匹配；不能绕过检查、卸载替换或主动开位置权限。 | 正常同包当前合法签名/有效签名轮换交付；实际完整性仍必须通过。 |
| DiDi<br>`com.sdu.didi.psnger` | 8.0.18 / 1208001805 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| 抖音<br>`com.ss.android.ugc.aweme` | 41.0.0 / 410001 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| 神州租车<br>`com.szzc` | 9.6.1 / 327 | S36完整220579134B，S38实际同签名正常验签，S39原文解释为9.6.1/code327，与当前同版本且字节不同。 | 不为增加升级计数重装同版；等待正常新版本或按当前版本做真实回归。 |
| 淘宝<br>`com.taobao.taobao` | 10.69.0 / 866 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| WeChat<br>`com.tencent.mm` | 8.0.80 / 3220 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| Uber<br>`com.ubercab` | 4.651.10003 / 316108 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| United Airlines<br>`com.united.mobile.android` | 4.2.98 / 3617 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| 拼多多<br>`com.xunmeng.pinduoduo` | 8.30.0 / 83000 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| ExpandableTextViewLibrary<br>`com.zhubajie.client` | 9.5.20 / 370 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| StreetEasy<br>`com.zillow.android.streeteasy` | 3.127.1 / 22850 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| 携程旅行<br>`ctrip.android.view` | 8.97.4 / 2133 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |
| ANA<br>`jp.co.ana.android.tabidachi` | 7.6.0 / 339 | 厂商直链尚未核实；这不排除其他正常公开同包签名包。此前官方商店信息不是完整 APK。 | 正常官方商店交付，或另行审阅公开同包完整APK/split集合；逐件实际验签。 |
| Sidecar Verification<br>`local.pocket4.fixture` | 未声明 / 0 | 本地QA/fixture以固定源码、正常签名及真实身份合同为准，不虚构商店最新版。 | 保留当前复现源码和有效合同；只按明确QA需求生成后继。 |
| WebView Browser Tester<br>`org.chromium.webview_shell` | 1.0 / 1 | 需与当前Android/framework源码及签名/权限合同匹配；商店同名包不是替代证据。 | 继续原合法framework构建/资源准入与运行验证；当前没有合格替代产物。 |
| Owned Editor Contract<br>`org.droidloom.qa.editorcontract` | 1.0 / 1 | 本地QA/fixture以固定源码、正常签名及真实身份合同为准，不虚构商店最新版。 | 保留当前复现源码和有效合同；只按明确QA需求生成后继。 |
| Fcitx5<br>`org.fcitx.fcitx5.android` | 0.1.3-0-g048f581c / 114 | 本次公开latest导航仍是当前release；已装字节与原官方asset引用匹配，运行回归仍待完成。 | 保持当前x86_64 code114输入法；ARM64同release code112不是升级。 |
| 哔哩哔哩<br>`tv.danmaku.bili` | 9.18.0 / 9180300 | 已实际正常升级；来源/正常签名与安装身份有回执，最新版业务回归仍未完成。 | 按当前已装版本推进业务回归；保留原实际来源和旧版本。 |

## 保留的失败与语义边界

- Amazon中国版与已装Shopping包名不同；公开32.20候选为APKM集合且本次普通下载页nonce失效，没有重放。
- Hilton中国渠道包名不同。12306原不完整传输/TLS失败、Marriott原HTTP403、美团签名不匹配全部保留，不通过换身份或签名绕过。
- 神州完整同签名9.6.1/code327候选已由S38/S39实际证据说明，不能再写成只有不完整文件；它与当前同版本，不是已完成升级。
- 公开页面、来源标签、普通验签、安装成功和生产可用是不同层证据；本研究新增下载0、升级0、生产验收0、删除0。
- 此新目录不修改 `current_launcher_inventory_r3/`、`CURRENT_STATUS`、旧失败账本或任何已冻结安装器来源白名单。

详细当前身份、原证据pin、各渠道状态和限制见JSON；公开网页ref只作本次工具观察索引，未伪称raw HTTP正文。
