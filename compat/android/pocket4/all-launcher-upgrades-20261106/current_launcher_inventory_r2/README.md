# 当前全部 Launcher App 清单与修复状态

工作尚未完成。新实测为 **46 个 Launcher App、206 个非 APEX APK 包**；原定八个是其中子集。已完成 11 次同签名升级，原 45 App / 85 APK 的正常验签与 manifest 审计已独立联合通过。新增 NDK 测试包仅已核定实际身份，验签待完成。**生产验收通过 0，已删除旧产物 0 字节。**

这份清单的版本列来自已装 APK 的 manifest，新增包另标 PM 观测；不能将其读成所有 App 都已是最新可用版。完整包名、组件、UID、versionCode、签名和 APK hash、声明权限、有效权限来源、真实失败路径及 12 个回归领域状态均在同目录 INVENTORY.json。

## 全量清单

| App（历史标签） | 包名 | 已装 versionName / code | 升级与审计 | 有效权限 |
|---|---|---|---|---|
| Hyatt | `com.Hyatt.hyt` | 26.9.0 / 26090096 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Railway 12306 | `com.MobileTicket` | 5.9.4.5 / 275 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Amazon Shopping | `com.amazon.mShop.android.shopping` | 32.18.0.100 / 1243240206 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Calendar | `com.android.calendar` | 17 / 37 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Camera | `com.android.camera2` | 2.0.002 / 20002000 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Contacts | `com.android.contacts` | 1.7.34 / 10734 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Clock | `com.android.deskclock` | 17 / 37 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Phone | `com.android.dialer` | 23.0 / 2900000 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Files | `com.android.documentsui` | 17 / 37 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Gallery | `com.android.gallery3d` | 1.1.40030 / 40030 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Messaging | `com.android.messaging` | 1.0.001 / 10001040 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Search | `com.android.quicksearchbox` | 17 / 37 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Settings | `com.android.settings` | 17 / 37 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| ThreadNetworkDemoApp | `com.android.threadnetwork.demoapp` | 17 / 37 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Best Buy | `com.bestbuy.android` | 26.9.20 / 2012312321 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| National | `com.ehi.national.mobile` | 6.15.0.9354 / 9354 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| TextNow | `com.enflick.android.TextNow` | 26.40.1.0 / 15733 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| NDK 测试入口（标签尚未读取） | `com.example.ndk_tests` | UNKNOWN / 0 | 新身份已绑定；验签待完成 | UNKNOWN（尚未完成有效权限解释） |
| microG Settings | `com.google.android.gms` | 0.3.17.252432 / 252432034 | 已装包正常验签通过 | 实际快照已解释；功能行为待验 |
| Hertz | `com.hertz.android.digital` | 5.6.0 / 1389 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Hilton Honors | `com.hilton.android.hhonors` | 2026.9.29 / 1004 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| IHG | `com.ihg.apps.android` | 5.108.1 / 50023219 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| JD.COM | `com.jingdong.app.mall` | 16.1.50 / 102918 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| 贝壳找房 | `com.lianjia.beike` | 3.06.71 / 3067100 | 已升级；正常验签通过 | 实际快照已解释；功能行为待验 |
| Marriott | `com.marriott.mrt` | 10.79.0 / 671 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| TextFree | `com.pinger.textfree` | 13.28 / 260172 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Air China | `com.rytong.airchina` | 7.53.0 / 75300 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| China Eastern Airlines (CEA) | `com.rytong.ceair` | 9.5.16 / 239 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| 美团外卖 | `com.sankuai.meituan.takeoutnew` | 8.83.2 / 800830002 | 已装包正常验签通过；升级候选签名冲突 | UNKNOWN（尚未完成有效权限解释） |
| DiDi | `com.sdu.didi.psnger` | 8.0.18 / 1208001805 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| 抖音 | `com.ss.android.ugc.aweme` | 41.0.0 / 410001 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| 神州租车 | `com.szzc` | 9.6.1 / 327 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| 淘宝 | `com.taobao.taobao` | 10.69.0 / 866 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| WeChat | `com.tencent.mm` | 8.0.80 / 3220 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Uber | `com.ubercab` | 4.651.10003 / 316108 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| United Airlines | `com.united.mobile.android` | 4.2.98 / 3617 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| 拼多多 | `com.xunmeng.pinduoduo` | 8.30.0 / 83000 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| ExpandableTextViewLibrary | `com.zhubajie.client` | 9.5.11 / 369 | 已装包正常验签通过；9.5.20 候选已验签、未安装 | UNKNOWN（尚未完成有效权限解释） |
| StreetEasy | `com.zillow.android.streeteasy` | 3.127.1 / 22850 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| 携程旅行 | `ctrip.android.view` | 8.97.4 / 2133 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| ANA | `jp.co.ana.android.tabidachi` | 7.6.0 / 339 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Sidecar Verification | `local.pocket4.fixture` | 未声明 / 0 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| WebView Browser Tester | `org.chromium.webview_shell` | 1.0 / 1 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Owned Editor Contract | `org.droidloom.qa.editorcontract` | 1.0 / 1 | 已装包正常验签通过 | UNKNOWN（尚未完成有效权限解释） |
| Fcitx5 | `org.fcitx.fcitx5.android` | 0.1.3-0-g048f581c / 114 | 已装包正常验签通过 | 实际快照已解释；功能行为待验 |
| 哔哩哔哩 | `tv.danmaku.bili` | 9.18.0 / 9180300 | 已升级；正常验签通过 | UNKNOWN（尚未完成有效权限解释） |

## 当前实际阻塞

贝壳已启动并取得首页节点，搜索动作两次被原 helper 的树/窗口一致性检查拒绝。新单击的 helper 明确未调用 performAction；整个 case 的 FAILED/UNKNOWN 保留，没有重放，也没有把首页截图当作搜索成功。

美团新候选与已装包签名不同；没有强制覆盖、重新签名或卸载数据，位置权限也没有主动开启。12306 仍缺可安装的完整官方新包。猪八戒 9.5.20/code 370 已正常验签，与已装 9.5.11 同厂商签名，安装等待新的完整保护范围。14 个国际 App 尚未取得合格的完整新包；万豪普通公开入口实际 HTTP 403，原失败保留。

Framework 最新 RAM 观察为 2026-11-06T22:45:19.864634+00:00，MemAvailable 15,556,583,424 B，原 15 GiB 门槛差 549,543,936 B；尚未重启构建。已有 builder 的资格验证不等于 framework 已编译或部署。

## 回归与清理

逐 App 的启动、登录或访客、核心操作、网络、存储、权限行为、长时间运行、App 重启、运行时重启和故障恢复尚未完整通过。已知结果保留原任务和文件 hash；未做的检查保留 UNKNOWN。旧 reDroid 已退役，当前内置 Android 的结果不转移为 reDroid 通过。

完成对应生产验收后再删除旧 Android/framework、旧 APK、实验残留和中间产物。已识别 11 次升级留存的 12 个旧 APK，历史逻辑字节合计 2,136,945,962 B，但尚未测得当前可释放空间。旧 builder/tool 目录仍有现行依赖；最终源码、配置、正常签名 APK 集和复现清单必须先脱离拟删除目录。

继续使用既有 sidecar、容器内 UI Automator、中文输入和节点定位。Bili Accept 只沿历史独立 cell 授权；美团位置权限不主动开启；完整性和签名检查保持。

## 证据入口

- `audit_matrix_r1/snapshots/c79b953103d9d432fcbe/EVIDENCE_MATRIX.json` — SHA-256 `b6777aaa1e4922ca4ed43f0b6ac9f469c9dbb1f364b41b8ee1896d876d431207`
- `successor_audit_requests/revisions/b13-linked-coverage-r1/COVERAGE.actual.json` — SHA-256 `2b66031b946de01f7ecbd19d26a44858ce1df84f2d869bc47a2658a87551c39a`
- `successor_audit_requests/native46_discovery_r1/actual/artifact.original.json` — SHA-256 `69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400`
- `successor_audit_requests/native46_discovery_r1/actual/root-validation.actual.json` — SHA-256 `0a9c6e397790adce9e064aa445b13929f44bddbfc616820eee8693df70bc11cc`
- `successor_audit_requests/beike_permission_pilot_r1/EFFECTIVE_PERMISSION_OBSERVATION.derived.json` — SHA-256 `aec1bf7e8df82e73f87f7392bf42321a70633980798a7f2b370cd4fdb9dce47a`
- `successor_audit_requests/effective_permissions_private_readback_r1/batch-01-p00/actual-public/PERMISSIONS.derived.json` — SHA-256 `32c17c1c34bc43c707ab8d9a661e54b4cfea4f98a27d8c3a4f6a1ddf2d7371f0`
- `successor_audit_requests/effective_permissions_microg_parser_r1/actual/PERMISSIONS.derived.json` — SHA-256 `ee8347af686deb9ce08bd2f1e3ce5aebe7e10302268c7069e6c4bd536713645d`
- `successor_qa/search_click_failure_reader_r1/actual-public/stdout.original.json` — SHA-256 `c6b1396ac512fe5730497a2de75642cce3d6c0c24bccbc5a9a83a41b37002e9b`
- `framework_provider_repair/normal06/current470-authorization-r1/memory-observation-after-native46-r1/actual/summary.derived.json` — SHA-256 `9810f1d0a98e4723fe147efbdd6a682ecb1785e0ef42e3d309c09d5f0699b3d4`
- `official_source_scripts/s44_international_delivery_metadata/international14-delivery-evidence.json` — SHA-256 `eb1777bbd1db0aedec55ad55fca5089206d73361ada603543349c04a198ea3d9`
- `official_source_scripts/s44_international_delivery_metadata/candidate-r1/actual/root-validation.actual.json` — SHA-256 `1aa25aecd0da092be284b98b3f6a7f5ccf566628b294ac7a0b5c9527b02785b2`
