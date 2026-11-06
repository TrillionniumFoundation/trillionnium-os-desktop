# Pocket4 全 Launcher 升级检查点

记录时间：2026-11-06T11:19:02.361097+00:00。这是实际进度检查点，任务尚未完成。

## 当前结论

已核对原生 Launcher 目录中的全部 **45 个包**，现有 **3 个 App 完成实际升级并读回验证**。完整业务与长时、重启、故障恢复验收仍为 **0/45**；没有把下载、编译、安装或短时启动等同于 production ready。

当前目标是 Pocket4 DroidLoom Android 17 / SDK 37 / user 0。历史 reDroid 已退役，没有当前容器目标，本轮没有重建它或迁移旧测试结论。目录前后两次原生读取一致，但其缓存是否等同当前 Android MAIN/LAUNCHER resolver 尚未证明；须在重新绑定的 Android QA 中再枚举。

## 已有实际证据

- `reference/current-all-launcher-metadata.json`：45 包 PM 版本码、UID、代码路径、证书摘要和保存的权限记录；保存状态不冒充有效运行时授权。
- `reference/current-original-eight-inventory.json`：历史八包的完整当前 APK 字节核对；之后的成功升级以各安装回执覆盖旧版本。
- 独立安装 worker 通过既有 native sidecar 路径提交已验签、相同签名的精确 APK，读回新安装字节，并核对 UID、数据目录、其他七包身份和美团位置记录连续性。没有引入 ADB。
- `app_test_catalog.json`：全部 45 包、136 个具体核心 case；全部为 `UNKNOWN_NOT_RUN`。本地、电话/SMS、Thread、IME 与商业联网 App 各有实际适用路径，没有用 N/A 伪造网络通过。
- `framework_provider_repair/`：真实 provider 源修复，Rust builder 实编译及 16 个 focused tests 成功。normal04 的完整 Android/Soong 构建在实际内存准入前停止：15,927,521,280 B 小于固定 16,106,127,360 B 门限，未降低门限，也未把局部编译当作 framework 部署完成。
- `recovery/`：现有 cell 的正常原生 restart 候选和真实只读 preflight。该检查点时尚未执行 restart，新 QA 也尚未实构建/安装。

## 不能略过的边界与失败

Bilibili 的历史 guest Accept 只适用于 `p4-bili-m30-cell-20261010`，当前 Main 不获得 Accept 授权。此前 task 873 的 native ownership 冲突与不确定 launch 回执原样保留；不按 task ID 删除或夺取所有权。美团外卖不得主动开启位置权限；它当前重签名 APK 与官方签名不一致，不能通过重签名、卸载丢数据或绕完整性检查强行升级。

官方下载入口也存在旧包/错包：京东所取 APK 包名不匹配；携程 metadata 是 8.97.2、公开下载入口却返回名为 8.94.6 的包；抖音真实官方下载在 deadline 前未完成。这些都不算更新成功。国际商店登录、商业完整性、合法测试账号/受控通信对端或硬件缺口，需要真实条件才能验收。

## 逐包状态

“参考”版本名来自历史 manifest，不冒充本轮刚读取的当前 manifest。版本码来自本轮 PM 保存记录；成功安装行的版本与字节已实际读回。全部行的完整业务回归仍待执行。

| Launcher 名称 | 包名 | 已安装版本名 / code | 已取候选版本 | 状态 |
|---|---|---|---|---|
| Hyatt | `com.Hyatt.hyt` | 参考 26.9.0 / 26090096 | 待核实 | LATEST_USABLE_UNPROVEN |
| Railway 12306 | `com.MobileTicket` | 参考 5.9.4.5 / 275 | 待核实 | LATEST_USABLE_UNPROVEN |
| Amazon Shopping | `com.amazon.mShop.android.shopping` | 参考 32.18.0.100 / 1243240206 | 待核实 | LATEST_USABLE_UNPROVEN |
| Calendar | `com.android.calendar` | 未读取 manifest / 37 | 待核实 | LATEST_USABLE_UNPROVEN |
| Camera | `com.android.camera2` | 参考 2.0.002 / 20002000 | 待核实 | LATEST_USABLE_UNPROVEN |
| Contacts | `com.android.contacts` | 未读取 manifest / 10734 | 待核实 | LATEST_USABLE_UNPROVEN |
| Clock | `com.android.deskclock` | 未读取 manifest / 37 | 待核实 | LATEST_USABLE_UNPROVEN |
| Phone | `com.android.dialer` | 未读取 manifest / 2900000 | 待核实 | LATEST_USABLE_UNPROVEN |
| Files | `com.android.documentsui` | 参考 17 / 37 | 待核实 | LATEST_USABLE_UNPROVEN |
| Gallery | `com.android.gallery3d` | 未读取 manifest / 40030 | 待核实 | LATEST_USABLE_UNPROVEN |
| Messaging | `com.android.messaging` | 未读取 manifest / 10001040 | 待核实 | LATEST_USABLE_UNPROVEN |
| Search | `com.android.quicksearchbox` | 未读取 manifest / 37 | 待核实 | LATEST_USABLE_UNPROVEN |
| Settings | `com.android.settings` | 未读取 manifest / 37 | 待核实 | LATEST_USABLE_UNPROVEN |
| ThreadNetworkDemoApp | `com.android.threadnetwork.demoapp` | 未读取 manifest / 37 | 待核实 | LATEST_USABLE_UNPROVEN |
| Best Buy | `com.bestbuy.android` | 参考 26.9.20 / 2012312321 | 待核实 | LATEST_USABLE_UNPROVEN |
| National | `com.ehi.national.mobile` | 参考 6.15.0.9354 / 9354 | 待核实 | LATEST_USABLE_UNPROVEN |
| TextNow | `com.enflick.android.TextNow` | 参考 26.40.1.0 / 15733 | 待核实 | LATEST_USABLE_UNPROVEN |
| microG Settings | `com.google.android.gms` | 参考 0.3.17.252432 / 252432034 | 待核实 | LATEST_USABLE_UNPROVEN |
| Hertz | `com.hertz.android.digital` | 参考 5.6.0 / 1389 | 待核实 | LATEST_USABLE_UNPROVEN |
| Hilton Honors | `com.hilton.android.hhonors` | 参考 2026.9.29 / 1004 | 待核实 | LATEST_USABLE_UNPROVEN |
| IHG | `com.ihg.apps.android` | 参考 5.108.1 / 50023219 | 待核实 | LATEST_USABLE_UNPROVEN |
| JD.COM | `com.jingdong.app.mall` | 参考 16.0.50 / 102810 | 待核实 | CANDIDATE_REJECTED |
| 贝壳找房 | `com.lianjia.beike` | 3.06.71 / 3067100 | 3.06.71 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| Marriott | `com.marriott.mrt` | 参考 10.79.0 / 671 | 待核实 | LATEST_USABLE_UNPROVEN |
| TextFree | `com.pinger.textfree` | 参考 13.28 / 260172 | 待核实 | LATEST_USABLE_UNPROVEN |
| Air China | `com.rytong.airchina` | 7.53.0 / 75300 | 7.53.0 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| China Eastern Airlines (CEA) | `com.rytong.ceair` | 9.5.16 / 239 | 9.5.16 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| 美团外卖 | `com.sankuai.meituan.takeoutnew` | 参考 8.83.2 / 800830002 | 8.84.2 | BLOCKED_OFFICIAL_SIGNER_DIFFERS_FROM_CURRENT_RESIGNED_APP |
| DiDi | `com.sdu.didi.psnger` | 参考 8.0.14 / 1208001404 | 待核实 | LATEST_USABLE_UNPROVEN |
| 抖音 | `com.ss.android.ugc.aweme` | 参考 40.8.0 / 400801 | 待核实 | LATEST_USABLE_UNPROVEN |
| 神州租车 | `com.szzc` | 参考 9.6.1 / 327 | 待核实 | LATEST_USABLE_UNPROVEN |
| 淘宝 | `com.taobao.taobao` | 参考 10.66.40 / 863 | 待核实 | LATEST_USABLE_UNPROVEN |
| WeChat | `com.tencent.mm` | 参考 8.0.79 / 3200 | 8.0.80 | CANDIDATE_OBSERVED_NOT_INSTALLED |
| Uber | `com.ubercab` | 参考 4.651.10003 / 316108 | 待核实 | LATEST_USABLE_UNPROVEN |
| United Airlines | `com.united.mobile.android` | 参考 4.2.98 / 3617 | 待核实 | LATEST_USABLE_UNPROVEN |
| 拼多多 | `com.xunmeng.pinduoduo` | 参考 8.26.0 / 82600 | 待核实 | LATEST_USABLE_UNPROVEN |
| ExpandableTextViewLibrary | `com.zhubajie.client` | 参考 9.5.11 / 369 | 待核实 | LATEST_USABLE_UNPROVEN |
| StreetEasy | `com.zillow.android.streeteasy` | 参考 3.127.1 / 22850 | 待核实 | LATEST_USABLE_UNPROVEN |
| 携程旅行 | `ctrip.android.view` | 参考 8.94.6 / 2100 | 待核实 | LATEST_USABLE_UNPROVEN |
| ANA | `jp.co.ana.android.tabidachi` | 参考 7.6.0 / 339 | 待核实 | LATEST_USABLE_UNPROVEN |
| Sidecar Verification | `local.pocket4.fixture` | 未读取 manifest / 0 | 待核实 | LATEST_USABLE_UNPROVEN |
| WebView Browser Tester | `org.chromium.webview_shell` | 未读取 manifest / 1 | 待核实 | LATEST_USABLE_UNPROVEN |
| Owned Editor Contract | `org.droidloom.qa.editorcontract` | 参考 1.0 / 1 | 待核实 | LATEST_USABLE_UNPROVEN |
| Fcitx5 | `org.fcitx.fcitx5.android` | 参考 0.1.3-0-g048f581c / 114 | 待核实 | LATEST_USABLE_UNPROVEN |
| 哔哩哔哩 | `tv.danmaku.bili` | 参考 9.16.1 / 9161100 | 9.18.0 | VERIFIED_CANDIDATE_PENDING_PRIOR_LAUNCH_UNKNOWN_SETTLEMENT |

## 复现和继续执行

`build_checkpoint.py` 只汇总已经存在的 JSON 回执，不运行 Android。`evaluate_readiness.py` 是离线证据审计器，当前 `regression_manifest.json` 的具体逐包策略仍只覆盖历史八包；新 45 包适用性目录还需显式接入后才可作为最终审计入口，不能把其模板当作已测结果。

所有升级、恢复和 QA worker 都按具体来源、版本、runtime 和单次操作绑定。成功回执是已经执行的记录；不能重新执行旧 flow 或改旧 PASS 的 PID、epoch、版本来伪造新授权。恢复前先结算所有已知相关 jobs，取得新的协调 drain，重新检查当前 source/CLI/运行时，再提交具体单次操作；细节见 `recovery/README.md`。

## 结束后的空间清理

用户已授权在最终可用版本验收之后删除所有旧 Android framework、旧 App、实验产物和中间构建。此检查点尚未达到条件，**没有执行旧版本清理，回收空间为 0**。最终保留可工作的源代码、精确 source-lock、当前配置、最终包/签名/来源清单、复现入口和轻量验收/故障结算回执。实际清理必须对待删路径逐一与正在运行、最后可用版本及未结算操作依赖核对，不用通配删除推测旧版本。
