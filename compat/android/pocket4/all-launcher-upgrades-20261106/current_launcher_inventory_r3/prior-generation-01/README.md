# 最近完整观察的 46 个 Launcher App 与当前已装包证据

本轮已完成 **12 次正常同签名升级**。最近一次完整 PackageManager resolver 与 native 目录观察为 **46 个 Launcher App、206 个非 APEX APK 包**；猪八戒此次升级后没有重新执行全局枚举。新的实际保护范围是 **48 包 / 88 APK**，包含这 46 项和两个 helper。

现在可将正常签名、manifest 和声明权限证据与这 **46 个 App / 86 个 APK** 的当前身份关联：44 项沿既有正常审计字节，NDK 新增直接审计，猪八戒以 S43 正常验签候选与实际安装字节完全一致关联。没有把旧猪八戒版本的审计移作新版证据。**生产验收 0，已删除旧产物 0 字节。**

以下 versionName 来自已装 APK 本身或经实际安装字节核同的候选 manifest。未声明版本保留为未声明；Android/PM 的有效 code 0 单独列示。签名有效、正常升级及版本较新均不代表最新版业务可用性已通过。

## 46 项清单

| App（历史标签） | 包名 | versionName / 有效 code | 当前证据 | 有效权限 |
|---|---|---|---|---|
| Hyatt | `com.Hyatt.hyt` | 26.9.0 / 26090096 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Railway 12306 | `com.MobileTicket` | 5.9.4.5 / 275 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Amazon Shopping | `com.amazon.mShop.android.shopping` | 32.18.0.100 / 1243240206 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Calendar | `com.android.calendar` | 17 / 37 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Camera | `com.android.camera2` | 2.0.002 / 20002000 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Contacts | `com.android.contacts` | 1.7.34 / 10734 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Clock | `com.android.deskclock` | 17 / 37 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Phone | `com.android.dialer` | 23.0 / 2900000 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Files | `com.android.documentsui` | 17 / 37 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Gallery | `com.android.gallery3d` | 1.1.40030 / 40030 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Messaging | `com.android.messaging` | 1.0.001 / 10001040 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Search | `com.android.quicksearchbox` | 17 / 37 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Settings | `com.android.settings` | 17 / 37 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| ThreadNetworkDemoApp | `com.android.threadnetwork.demoapp` | 17 / 37 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Best Buy | `com.bestbuy.android` | 26.9.20 / 2012312321 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| National | `com.ehi.national.mobile` | 6.15.0.9354 / 9354 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| TextNow | `com.enflick.android.TextNow` | 26.40.1.0 / 15733 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| NDK 测试入口（显示名称未提取） | `com.example.ndk_tests` | 未声明 / 0 | 当前字节与正常审计关联；来源仍 UNKNOWN | UNKNOWN（尚无已解释有效快照） |
| microG Settings | `com.google.android.gms` | 0.3.17.252432 / 252432034 | 当前字节与正常审计关联 | 既有实际快照已解释；功能行为待验 |
| Hertz | `com.hertz.android.digital` | 5.6.0 / 1389 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Hilton Honors | `com.hilton.android.hhonors` | 2026.9.29 / 1004 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| IHG | `com.ihg.apps.android` | 5.108.1 / 50023219 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| JD.COM | `com.jingdong.app.mall` | 16.1.50 / 102918 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| 贝壳找房 | `com.lianjia.beike` | 3.06.71 / 3067100 | 已正常升级；签名与当前字节关联 | 既有实际快照已解释；功能行为待验 |
| Marriott | `com.marriott.mrt` | 10.79.0 / 671 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| TextFree | `com.pinger.textfree` | 13.28 / 260172 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Air China | `com.rytong.airchina` | 7.53.0 / 75300 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| China Eastern Airlines (CEA) | `com.rytong.ceair` | 9.5.16 / 239 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| 美团外卖 | `com.sankuai.meituan.takeoutnew` | 8.83.2 / 800830002 | 当前字节与正常审计关联；升级候选签名冲突 | UNKNOWN（尚无已解释有效快照） |
| DiDi | `com.sdu.didi.psnger` | 8.0.18 / 1208001805 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| 抖音 | `com.ss.android.ugc.aweme` | 41.0.0 / 410001 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| 神州租车 | `com.szzc` | 9.6.1 / 327 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| 淘宝 | `com.taobao.taobao` | 10.69.0 / 866 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| WeChat | `com.tencent.mm` | 8.0.80 / 3220 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| Uber | `com.ubercab` | 4.651.10003 / 316108 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| United Airlines | `com.united.mobile.android` | 4.2.98 / 3617 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| 拼多多 | `com.xunmeng.pinduoduo` | 8.30.0 / 83000 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| ExpandableTextViewLibrary | `com.zhubajie.client` | 9.5.20 / 370 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| StreetEasy | `com.zillow.android.streeteasy` | 3.127.1 / 22850 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| 携程旅行 | `ctrip.android.view` | 8.97.4 / 2133 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |
| ANA | `jp.co.ana.android.tabidachi` | 7.6.0 / 339 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Sidecar Verification | `local.pocket4.fixture` | 未声明 / 0 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| WebView Browser Tester | `org.chromium.webview_shell` | 1.0 / 1 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Owned Editor Contract | `org.droidloom.qa.editorcontract` | 1.0 / 1 | 当前字节与正常审计关联 | UNKNOWN（尚无已解释有效快照） |
| Fcitx5 | `org.fcitx.fcitx5.android` | 0.1.3-0-g048f581c / 114 | 当前字节与正常审计关联 | 既有实际快照已解释；功能行为待验 |
| 哔哩哔哩 | `tv.danmaku.bili` | 9.18.0 / 9180300 | 已正常升级；签名与当前字节关联 | UNKNOWN（尚无已解释有效快照） |

## 已确认的边界与失败路径

猪八戒已从 code 369 正常升级到 9.5.20 / code 370，同厂商签名、UID10144 和 CE/DE inode152967/152970 保留；旧包另外留存。其他 47 个保护包的完整记录未变。业务启动、登录或访客、核心操作和长期回归仍待验。

NDK 包的完整 APK 已通过普通验签及 manifest 审计；XML 未声明 versionCode、versionCodeMajor、versionName，原 badging 空串和派生 null 保留，有效 code 0 与 PM 一致。其 minSdk14、targetSdk24、arm64-v8a 及 WRITE_EXTERNAL_STORAGE、INTERNET 是声明观察，来源、有效授权和业务能力仍未知。

贝壳最新公开比较显示：既有 preinspection 与两次历史观察的稳定窗口 hash、搜索节点相同，可见路径集相同；有一个其他可见节点的文本/边界/hash 变化，整树 hash 不同。但被拒动作当时的当前树没有导出，因此具体拒绝差异和根因仍 UNKNOWN。原 helper 明确未执行该点击，整个 FAILED/UNKNOWN 仍保留；没有降低一致性检查，也没有推断搜索成功。

美团升级候选与已装包签名冲突，未绕过、重签或卸载，位置权限未主动开启。12306 尚缺合格完整新包。14 个国际 App 的完整新包仍未全部取得；万豪普通公开入口的 HTTP403 失败保留。NDK 来源未知不因验签成功而升级为官方来源。

本报告继承的 RAM 观察时间为 2026-11-06T22:45:19.864634+00:00，MemAvailable 15,556,583,424 B，距原 15 GiB 门槛差 549,543,936 B；本生成器没有发起新 RAM 观察或构建。Builder 资格不等于 framework 编译、部署或生产通过。

## 权限、回归与清理

目前解释了贝壳、Fcitx、microG 三份实际权限快照，角色仍 UNKNOWN，AppOps 按原文字面作用域保存。它们是既有采样，未在猪八戒升级后重新采集，也不等于实际拒绝、恢复或核心功能行为测试。其余 App 不虚构有效 grants。

逐 App 的启动、登录或访客、核心操作、网络、存储、权限行为、长时间运行、App 重启、运行时重启和故障恢复尚未全面通过。缺少运行证据的格子保留 UNKNOWN。当前内置 Android 证据不转移为已退役 reDroid 的通过结果。

空间观察采样在猪八戒此次升级之前：797 个固定引用中 776 已观察、20 缺失、1 未解析；16 个限定目录树完成 14 个，共享工作树因原预算停止，build08 树未遍历。记录的 10,889,973,760 B inode 去重已分配量是有限观察，不是可释放空间。

该次观察对应此前 11 次升级留存的 12 份旧 APK，历史逻辑量 2,136,945,962 B。猪八戒随后又留存 166,858,796 B 旧 APK；12 次升级的 13 份留存回执逻辑量合计 2,303,804,758 B。这不是一次新的完整物理占用扫描，也不是可释放量。旧 builder/tool 与外部项目的 9 个精确 JDK 依赖继续保留。最终源码、配置、签名 APK 和复现清单未脱离旧目录依赖、生产回归未通过之前，不删除。

继续沿既有 sidecar、容器内 UI Automator、中文输入与节点定位。Bili Accept 仅沿历史独立测试 cell 授权；不主动开启美团位置权限；不绕过签名或其他完整性检查。

## 证据入口

- `current_launcher_inventory_r2/build_inventory.py` — 13502 B / SHA-256 `887fa5c8b7821f100adb7735c0ccf4e105be94339c782e8088b887b0c4ab52cc`
- `audit_matrix_r1/snapshots/c79b953103d9d432fcbe/EVIDENCE_MATRIX.json` — 2409028 B / SHA-256 `b6777aaa1e4922ca4ed43f0b6ac9f469c9dbb1f364b41b8ee1896d876d431207`
- `successor_audit_requests/revisions/b13-linked-coverage-r1/COVERAGE.actual.json` — 45155 B / SHA-256 `2b66031b946de01f7ecbd19d26a44858ce1df84f2d869bc47a2658a87551c39a`
- `successor_audit_requests/native46_discovery_r1/actual/artifact.original.json` — 112546 B / SHA-256 `69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400`
- `successor_audit_requests/native46_discovery_r1/actual/root-validation.actual.json` — 5903 B / SHA-256 `0a9c6e397790adce9e064aa445b13929f44bddbfc616820eee8693df70bc11cc`
- `successor_audit_requests/beike_permission_pilot_r1/EFFECTIVE_PERMISSION_OBSERVATION.derived.json` — 23716 B / SHA-256 `aec1bf7e8df82e73f87f7392bf42321a70633980798a7f2b370cd4fdb9dce47a`
- `successor_audit_requests/effective_permissions_private_readback_r1/batch-01-p00/actual-public/PERMISSIONS.derived.json` — 20074 B / SHA-256 `32c17c1c34bc43c707ab8d9a661e54b4cfea4f98a27d8c3a4f6a1ddf2d7371f0`
- `successor_audit_requests/effective_permissions_microg_parser_r1/actual/PERMISSIONS.derived.json` — 62052 B / SHA-256 `ee8347af686deb9ce08bd2f1e3ce5aebe7e10302268c7069e6c4bd536713645d`
- `successor_qa/search_click_failure_reader_r1/actual-public/stdout.original.json` — 15496 B / SHA-256 `c6b1396ac512fe5730497a2de75642cce3d6c0c24bccbc5a9a83a41b37002e9b`
- `framework_provider_repair/normal06/current470-authorization-r1/memory-observation-after-native46-r1/actual/summary.derived.json` — 668 B / SHA-256 `9810f1d0a98e4723fe147efbdd6a682ecb1785e0ef42e3d309c09d5f0699b3d4`
- `official_source_scripts/s44_international_delivery_metadata/international14-delivery-evidence.json` — 40247 B / SHA-256 `eb1777bbd1db0aedec55ad55fca5089206d73361ada603543349c04a198ea3d9`
- `official_source_scripts/s44_international_delivery_metadata/candidate-r1/actual/root-validation.actual.json` — 602 B / SHA-256 `1aa25aecd0da092be284b98b3f6a7f5ccf566628b294ac7a0b5c9527b02785b2`
- `successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/app-scope-after.private.json` — 59259 B / SHA-256 `9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a`
- `successor_audit_requests/explicit48_scope_r1/actual-readback/app-scope.private.json` — 59957 B / SHA-256 `b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4`
- `successor_install/source-r4-zbj-full48/candidate-r1/actual-install/stdout.original.jsonl` — 15948 B / SHA-256 `23998b1f6ccd501379f207e0e6534ecaf2a88ede7cdb21702a4bbdbb357fc3d2`
- `successor_install/source-r4-zbj-full48/candidate-r1/actual-install/status-01.original.json` — 733 B / SHA-256 `dedccba067c70ef35d8bb51de41b98c2d0f8d8f66b3e46157c34c345e1526cf1`
- `successor_install/source-r4-zbj-full48/candidate-r1/actual-install/root-validation.actual.json` — 3721 B / SHA-256 `78bdda6caf7fbadaf2d26a0201c89776c69192054c11523787b0b46018f56a82`
- `successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/root-validation.actual.json` — 967 B / SHA-256 `ff656c7ccf09e9e6569850c0340ac499e8bea5b810ae0a491131ca20cc0dccd4`
- `successor_install/source-r4-zbj-full48/candidate-r1/post_install_scope_readback_r1/actual/terminal.original.json` — 733 B / SHA-256 `d291ad13e88dd37cb92d8c9ce1ec84dd7c091c89f6e827e9187e0ddd918d62a1`
- `official_source_scripts/s43_zbj_operator_verification/actual/stdout.original.json` — 52573 B / SHA-256 `96c6931181555e575bffa3e626d704b93254298441095f318691d9d3ab70cb11`
- `official_source_scripts/s43_zbj_operator_verification/actual/terminal.original.json` — 733 B / SHA-256 `c42a9fd1a5bbf4f6d6ac7e335e0f3d0545379ce754c54fd9f6c99f0ba96e9076`
- `successor_audit_requests/ndk_signature_metadata_r1/actual/artifact.original.json` — 62533 B / SHA-256 `c6fec2589cf3df6dfdd65c88d14d39c041c1a2449d707618fe4c7f5d6a9639c3`
- `successor_audit_requests/ndk_signature_metadata_r1/actual/root-validation.actual.json` — 17411 B / SHA-256 `24ee44259c543a51aa61c053bbcac31c5e53904d738c93f25436735b7b4e486f`
- `successor_qa/search_click_tree_analysis_r1/CURRENT_PREINSPECTION_COMPARISON.derived.json` — 4934 B / SHA-256 `f48077c3f0983a5b5ed3f8b342041f7d99326867d251fd44e1886bbac3408231`
- `retention_inventory_r1/observer-candidate-r2/actual-public/artifact.original.json` — 62484 B / SHA-256 `19ad825b48aef18d1e2c0264228c298c0e92311932347992c15877964a4b270c`
- `retention_inventory_r1/observer-candidate-r2/actual-public/root-validation.actual.json` — 17655 B / SHA-256 `52c683137a93d96c5d34b6fd4fa0159a74a8620d9eb15582b175e37641325a50`
- `retention_inventory_r1/DEPENDENCY_PROTECTION.json` — 16116 B / SHA-256 `b805f4349d343b873e8e08c5ce047134e3b9120e4b0e2e8a1bd80946d0ab068d`
