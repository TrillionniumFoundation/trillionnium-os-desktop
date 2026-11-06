# Pocket4 全 Launcher 升级检查点

记录时间：2026-11-06T12:02:58.757701+00:00。这是实际进度检查点，任务尚未完成。

## 当前结论

已核对原生 Launcher 目录中的全部 **45 个包**，现有 **4 个 App 完成实际升级并读回验证**：贝壳 **3.06.71 / 3067100**、东航 **9.5.16 / 239**、国航 **7.53.0 / 75300**、微信 **8.0.80 / 3220**。完整业务与长时、重启、故障恢复验收仍为 **0/45**，旧版本清理及回收空间均为 **0**。

**单次正常原生 restart 已实际执行，其原始结果仍为 UNKNOWN。** `1a1b0a21e45-fc05-71db` 的 fresh preflight 通过，native 返回 `ok:true / running`；随后原始 pidfd 退出检查未能证明全部旧角色退出，记录 `OLD_CELL_OR_NATIVE_OWNER_STILL_ALIVE`，durable terminal 为 `failed / exit 1`。失败后的第一次只读观察见原 Android init PID **3588093**、start ticks **80797014**、状态 **S**，确认为原进程身份。

**随后独立的精确 orphan 退休已成功结算。** job `1a1b0b7efb4-fc05-7259` durable success / exit 0，只向 held pidfd 固定的旧 init 发送 **1 次 SIGKILL**；新的修复 pidfd 证明旧 init **3588093** 和旧 parent **3588092** 均退出，旧 PID namespace 成员为 **0**。new launcher **2747275**、new init **2747279**、daemon 与 presenter 的身份保持不变；6/6 观察 FD 和 104/104 lease FD 关闭。它的 `outcome_unknown=false`，没有再次 restart。该独立成功记录**不改写原 restart r1 的 failed/UNKNOWN，也不补造原始重启前 pidfd 证据**。新的合格 baseline/guard 仍未发布。

因此当前 runtime 操作继续冻结，**旧 guard 已不可再用于 runtime，旧 epoch 的安装、观察或 UI worker 不得复用**。native status 当前报告的新 host PID **2747275** 仅是状态回执，不构成完整身份资格。下列安装版本是最后已验证的实际安装记录，尚未获得重启后的新身份复验。

最后已核实的目标是 Pocket4 DroidLoom Android 17 / SDK 37 / user 0。历史 reDroid 已退役，没有当前容器目标，本轮没有重建它或迁移旧测试结论。重启前目录两次原生读取一致，但其缓存是否等同 Android MAIN/LAUNCHER resolver 尚未证明；须在合格的新身份下再枚举。

## 已有实际证据

- `reference/current-all-launcher-metadata.json`：45 包 PM 版本码、UID、代码路径、证书摘要和保存的权限记录；保存状态不冒充有效运行时授权。
- `reference/current-original-eight-inventory.json`：重启前原八包完整 APK 字节核对；之后的成功升级以各安装回执覆盖早期观察。
- `reference/completed-native-upgrades-20261106.json`：四项实际升级的完整交接索引。四项均有 durable success、完整原始输出和 terminal；新 APK 字节、UID 与数据目录核对通过，`install_verified=true / outcome_unknown=false`，各自 666/666 FD 关闭、锁释放。普通原八包升级比较其他七包；微信新增明确九包投影，完整比较原八包身份，没有修改旧 collector 的 HISTORY。美团位置保存观察不变，没有引入 ADB。
- `app_test_catalog.json`：全部 45 包、136 个具体核心 case；全部为 `UNKNOWN_NOT_RUN`。本地、电话/SMS、Thread、IME 与商业联网 App 各有实际适用路径，没有用 N/A 伪造网络通过。
- `framework_provider_repair/`：真实 provider 源修复，Rust builder 实编译及 16 个 focused tests 成功。normal04 的完整 Android/Soong 构建在实际内存准入前停止：15,927,521,280 B 小于固定 16,106,127,360 B 门限，未降低门限，也未把局部编译当作 framework 部署完成。
- `successor_qa/actual/stage-r2.stdout.raw.jsonl`：QA r2 **生成器源码闭包已在目标机部署并读回**，job `1a1b09dad9f-fc05-71bb` durable success。4 项实际 root host Stage 文件测试全部通过、没有跳过，总 FD 数不变；涵盖真实写入/读回、完整或 owner 拒绝、部分写入失败、读回失败时的三个 FD 收口。它们没有打开 Android 路径。实际 successor 绑定生成数 **0**、helper 安装数 **0**、UI 动作 **0**；source generation 未执行，不能视为新身份 QA 或 App 业务通过。
- `recovery/execute-r1-result.json` 与 `recovery/execute-r1-terminal.json`：一次原生 restart 的实际未知结果。907/907 观察 FD 和 104/104 lease FD 已关闭，剩余为 0；关闭 FD 不等于重启成功。恢复范围的 46 项是 45 个 Launcher 加 `local.pocket4.actions.v2`，不会把它写成 46 个 Launcher。
- `recovery/failed-r1-diagnostic.stdout.raw.json`：失败后的独立只读观察，没有发信号、重启、安装或 UI。旧 launcher、composer、zygote64、system_server、surfaceflinger 的原 PID 在该观察时已缺失，原 init 在当时仍存活；新观察不能代替原始 pidfd 的退出证据，也未改写原 UNKNOWN。
- `recovery/orphan-retirement-r1-result.json`、原始 stdout 和 terminal：随后独立的精确旧 orphan 退休。远端结果 **3043 B / SHA-256 `4c322a72ea61f3e7ff7e9c369c7996256beed8c74be1cd8c4b10524da285008d`**，目标进程退出与非目标进程身份保持已实际核对；这一步没有安装、UI、权限修改、namespace entry 或新 guard 发布。

## 不能略过的边界与失败

Bilibili 的历史 guest Accept 只适用于 `p4-bili-m30-cell-20261010`，当前 Main 不获得 Accept 授权。此前 task 873 的 native ownership 冲突与不确定 launch 回执原样保留；不按 task ID 删除或夺取所有权。美团外卖不得主动开启位置权限；它当前重签名 APK 与官方签名不一致，不能通过重签名、卸载丢数据或绕完整性检查强行升级。

京东最初取到的错包已保留为拒绝记录；随后通过官方动态入口取得 **16.1.50 / 102918**，完整下载与签名校验通过。拼多多 **8.30.0 / 83000**、淘宝 **10.69.0 / 866** 也已完成完整 APK 验签，均比历史已安装版本新、签名与历史 PM 参考一致。这三个新候选尚未安装，须在新的合格 runtime 下重新核对当前包身份。携程官方 metadata 是 **8.97.2**、公开下载入口实际 APK manifest 仍为 **8.94.6 / 2100**；抖音真实官方下载在 deadline 前未完成。国际商店登录、商业完整性、合法测试账号/受控通信对端或硬件缺口，需要真实条件才能验收。

旧 orphan 退休后的独立只读 job `1a1b0b9ff7a-fc05-7262` 已成功：当前 init、zygote、system_server、SurfaceFlinger 和 composer 在两个样本中身份一致。它没有执行 UI、安装或 namespace entry，也没有发布新 guard；这些短时观察不会被计作生产稳定性通过。

## 逐包状态

“参考”版本名来自历史 manifest，不冒充本轮刚读取的当前 manifest。版本码来自最后有身份资格的 PM 保存记录；四个成功安装行的版本与字节在各自安装结束时已实际读回。**所有行都尚未在此次未结算重启后的 runtime 重新验证**，完整业务回归仍待执行。

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
| JD.COM | `com.jingdong.app.mall` | 参考 16.0.50 / 102810 | 16.1.50 | VERIFIED_NEW_CANDIDATE_AWAITING_NEW_RUNTIME_INSTALL |
| 贝壳找房 | `com.lianjia.beike` | 3.06.71 / 3067100 | 3.06.71 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| Marriott | `com.marriott.mrt` | 参考 10.79.0 / 671 | 待核实 | LATEST_USABLE_UNPROVEN |
| TextFree | `com.pinger.textfree` | 参考 13.28 / 260172 | 待核实 | LATEST_USABLE_UNPROVEN |
| Air China | `com.rytong.airchina` | 7.53.0 / 75300 | 7.53.0 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| China Eastern Airlines (CEA) | `com.rytong.ceair` | 9.5.16 / 239 | 9.5.16 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| 美团外卖 | `com.sankuai.meituan.takeoutnew` | 参考 8.83.2 / 800830002 | 8.84.2 | BLOCKED_OFFICIAL_SIGNER_DIFFERS_FROM_CURRENT_RESIGNED_APP |
| DiDi | `com.sdu.didi.psnger` | 参考 8.0.14 / 1208001404 | 待核实 | LATEST_USABLE_UNPROVEN |
| 抖音 | `com.ss.android.ugc.aweme` | 参考 40.8.0 / 400801 | 待核实 | LATEST_USABLE_UNPROVEN |
| 神州租车 | `com.szzc` | 参考 9.6.1 / 327 | 待核实 | LATEST_USABLE_UNPROVEN |
| 淘宝 | `com.taobao.taobao` | 参考 10.66.40 / 863 | 10.69.0 | VERIFIED_NEW_CANDIDATE_AWAITING_NEW_RUNTIME_INSTALL |
| WeChat | `com.tencent.mm` | 8.0.80 / 3220 | 8.0.80 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| Uber | `com.ubercab` | 参考 4.651.10003 / 316108 | 待核实 | LATEST_USABLE_UNPROVEN |
| United Airlines | `com.united.mobile.android` | 参考 4.2.98 / 3617 | 待核实 | LATEST_USABLE_UNPROVEN |
| 拼多多 | `com.xunmeng.pinduoduo` | 参考 8.26.0 / 82600 | 8.30.0 | VERIFIED_NEW_CANDIDATE_AWAITING_NEW_RUNTIME_INSTALL |
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

`build_checkpoint.py` 只汇总已经存在的 JSON 回执，不运行 Android。它读取四项实际升级索引并逐项校验原始 stdout、terminal、安装字节和数据身份，读取 QA r2 的真实 host Stage 回执，并保持原失败恢复与诊断回执原样；大整数由 Python 直接解析。报告以临时文件完整写入并 fsync 后原子替换，避免空间不足时截断已有报告。

`GIT_CHECKPOINT_FILES_NEXT.json` 是交给 root 的下次 Git checkpoint 必要文件清单，记录实际文件哈希及现有前次 commit。生成清单不会提交 Git，也不会重写冻结 source manifest。另一个 agent 的 `recovery/NATIVE_RESTART_FINDINGS.md` 等待其本人冻结后再纳入，当前脚本不读写该文件。

全部 45 包的 APK manifest/完整签名审计源码仅在本地 `/dev/shm/pocket4-sidecar-next-20261106` 准备，并通过 8 项本地边界测试；未在目标机运行。其输入必须是真实新 typed guard 与同 runtime 的 versioned App scope。当前无合格 successor guard，不能启动该采集或借用旧资格。

`evaluate_readiness.py` 是离线证据审计器，当前 `regression_manifest.json` 的具体逐包策略仍只覆盖原八包；新 45 包适用性目录还需显式接入后才可作为最终审计入口，不能把模板当作已测结果。

所有升级、恢复和 QA worker 都按具体来源、版本、runtime 和单次操作绑定。成功回执是已经执行的记录；不能重新执行旧 flow 或改旧 PASS 的 PID、epoch、版本来伪造新授权。此次 restart 已有实际副作用及 UNKNOWN，不能自动重试或把事后 status、后续 orphan 退休改写成原步骤成功。精确 orphan 退休已独立结算，接下来仍需为新 runtime 建立实际的新资格和 App scope；细节见 `recovery/README.md`。

## 结束后的空间清理

用户已授权在最终可用版本验收之后删除所有旧 Android framework、旧 App、实验产物和中间构建。此检查点尚未达到条件，**没有执行旧版本清理，回收空间为 0**。最终保留可工作的源代码、精确 source-lock、当前配置、最终包/签名/来源清单、复现入口和轻量验收/故障结算回执。实际清理必须对待删路径逐一与正在运行、最后可用版本及未结算操作依赖核对，不用通配删除推测旧版本。
