# Pocket4 全 Launcher 升级检查点 03

记录时间：2026-11-06T14:07:33.791321+00:00。任务尚未完成。

## 当前实际状态

已经有 **11 个不同 App 完成真实升级和字节读回**：JD.COM 16.1.50 / 102918、贝壳找房 3.06.71 / 3067100、Air China 7.53.0 / 75300、China Eastern Airlines (CEA) 9.5.16 / 239、DiDi 8.0.18 / 1208001805、抖音 41.0.0 / 410001、淘宝 10.69.0 / 866、WeChat 8.0.80 / 3220、拼多多 8.30.0 / 83000、携程旅行 8.97.4 / 2133、哔哩哔哩 9.18.0 / 9180300。其中原正常运行 epoch 下完成 4 项，新 successor 下有 7 个已验证成功安装 job，覆盖 7 个包。完整业务、长时、重启和故障恢复验收仍为 **0/45**，清理与回收空间均为 **0**。

这 45 包是历史已观察的 launcher 参考目录；当前 runtime 的完整 MAIN/LAUNCHER resolver 仍需实测。生命周期的 46 项 scope 包含 45 个参考 launcher 和 local.pocket4.actions.v2。不能据此把任务范围写成 46 个 launcher，或遗漏之后 resolver 新发现的包。当前 reDroid 已退役，没有可迁移旧 PASS 的新容器目标。

## 生命周期修复与新资格

原 native restart r1 的 job **1a1b0a21e45-fc05-71db** 保持 failed/UNKNOWN 原文。之后 exact orphan retirement 独立成功，只对旧 init 的精确 held pidfd 发一次信号，没有重写 r1 或补造它的原始 pidfd 证据。

新的独立 r2 **stop → 原六角色与中间 parent 退出 → 唯一 start → 新资格** 已实际成功，job **1a1b0f80e39-fc05-7479** durable success / exit 0。旧/中间两个 namespace 两次均无成员；原 r2 pre-stop pidfd 证明六角色及 parent 死亡。两次 native 生命周期命令均正常结束，收据与实际新 owner **3268774** 一致；精确 owned init 信号共 **1 次**。新进程、classpath、配置和 46 包 bytes/data 身份形成实际 successor baseline。3 次观测跨约 **10.257 秒**，观察 FD **3489/3489**、lease FD **116/116** 全部关闭。

- Runtime epoch：`a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9`
- Framework epoch：`7d927812392d30ab8cca43da87c0785e24695ca724da93b3b465122502b8045c`
- 新 guard：`d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3`
- Qualification：`4bdfe7dd1e275bc4727f37c630dc2498b3dc31c528b03a4028e42c1cf8fc4fc6`
- Baseline：`7c52723c372b9f486067456e720709ef401bcebe1a7aad158f6b8c099f67fcc8`

修复后的 Python wrapper 已在真实新 lineage 激活，实际 unshare 参数是 `--kill-child=KILL`；同一源码的真实隔离 host PID namespace 控制证明 parent-death 链。报告未声称从生产 /proc 读得 PDEATHSIG。

当前仅 **identity_qualified=true**。真实 baseline 仍明确记录 framework_exit_cause_resolved=false、future_runtime_stop_regression_proved=false、native_framework_incarnation_fix_deployed=false，没有把短时资格当完整 framework 或长期稳定性验收。UI/install blanket admission 仍为 false；已成功的安装使用独立明确的当前 App scope。后续每项安装或 QA 都要新 scope 与实际 guard 校验。旧 epoch worker 和旧 guard 不可复用。

## 实际安装与候选

原四项升级的原始收据和终态保留；其 APK/data 身份在 r2 新 scope 中再次固定。新增安装逐项核对原始 bootstrap/final 两行 stdout、durable terminal、真实新 guard、安装前后 UID/签名/data 与完整候选字节、其他包不变、美团位置观察不变、正常 native install 只有一次，以及全部 FD 收口。successor_install/actual 下的新成功收据会由同一入口验证后累加，不按计划或口头数量增加。

未计入成功的实际记录：**com.jingdong.app.mall: REJECTED_BEFORE_INSTALL**。无动作拒绝不会被计成升级，未来成功也不会改写该拒绝。任何执行后 UNKNOWN 仍单列保留。

本地已完整验签的 successor 候选工作集合：com.jingdong.app.mall, com.sdu.didi.psnger, com.ss.android.ugc.aweme, com.taobao.taobao, com.xunmeng.pinduoduo, ctrip.android.view, tv.danmaku.bili。候选验证与成功安装分别记录；网页版本、国际商店 metadata 或下载未完成不升级为完整 APK 事实。尚未发现可取得且可安装的适用最新版时继续 UNKNOWN。

Bili 当前 Main 没有 Accept 授权，独立历史 cell p4-bili-m30-cell-20261010 的 guest Accept 不迁移；原 task873 launch UNKNOWN 原样保留。美团外卖不主动开启位置权限，现有重签名与正式发行方签名冲突继续阻断合法覆盖升级。商业完整性、正常签名/UID、合法账号和受控通信对端、真实硬件均须保留有效约束。

## 全量回归入口

原八包 evaluator/manifest 保持原字节。新增 `readiness_all_launcher/evaluate_all.py` 固定这些源并接入 **45 包 / 136 core case / 12 profile**；本地 **14 项**边界控制通过，UNKNOWN 模板实际判定为 0 production。它只审阅提供的证据，没有执行设备 QA。

Fresh resolver 新增/缺失包、无效结构、旧 helper、缺账号/对端、缺硬件、N/A、短于3600秒、少于3次 App重启或适用故障恢复、Bili Accept、美团主动位置授权、完整性绕过等都阻断。离线/电话/Thread/IME 根据真实本地或服务契约取证，不硬填商业 App 的自有 DNS/TLS。3600秒与3/3次是本轮提出的下限，不是历史已通过事实。

已有 QA source Stage 4 项 host 文件控制保留。当前新 helper 的实际生成、构建、安装与逐包 UI 资格仍需独立实际回执；不把旧 Stage 测试或 source closure 当新的 helper/App PASS。

## 逐包当前记录

版本名有完整候选 bytes 对应时才继承其已验签 manifest；否则明确是历史参考或待读取。当前 UID/code/APK/data scope 经 r2 与后续成功安装链核对，仍未代替新的完整 launcher resolver 或业务回归。

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
| JD.COM | `com.jingdong.app.mall` | 16.1.50 / 102918 | 16.1.50 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| 贝壳找房 | `com.lianjia.beike` | 3.06.71 / 3067100 | 3.06.71 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| Marriott | `com.marriott.mrt` | 参考 10.79.0 / 671 | 待核实 | LATEST_USABLE_UNPROVEN |
| TextFree | `com.pinger.textfree` | 参考 13.28 / 260172 | 待核实 | LATEST_USABLE_UNPROVEN |
| Air China | `com.rytong.airchina` | 7.53.0 / 75300 | 7.53.0 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| China Eastern Airlines (CEA) | `com.rytong.ceair` | 9.5.16 / 239 | 9.5.16 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| 美团外卖 | `com.sankuai.meituan.takeoutnew` | 参考 8.83.2 / 800830002 | 8.84.2 | BLOCKED_OFFICIAL_SIGNER_DIFFERS_FROM_CURRENT_RESIGNED_APP |
| DiDi | `com.sdu.didi.psnger` | 8.0.18 / 1208001805 | 8.0.18 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| 抖音 | `com.ss.android.ugc.aweme` | 41.0.0 / 410001 | 41.0.0 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| 神州租车 | `com.szzc` | 参考 9.6.1 / 327 | 待核实 | LATEST_USABLE_UNPROVEN |
| 淘宝 | `com.taobao.taobao` | 10.69.0 / 866 | 10.69.0 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| WeChat | `com.tencent.mm` | 8.0.80 / 3220 | 8.0.80 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| Uber | `com.ubercab` | 参考 4.651.10003 / 316108 | 待核实 | LATEST_USABLE_UNPROVEN |
| United Airlines | `com.united.mobile.android` | 参考 4.2.98 / 3617 | 待核实 | LATEST_USABLE_UNPROVEN |
| 拼多多 | `com.xunmeng.pinduoduo` | 8.30.0 / 83000 | 8.30.0 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| ExpandableTextViewLibrary | `com.zhubajie.client` | 参考 9.5.11 / 369 | 待核实 | LATEST_USABLE_UNPROVEN |
| StreetEasy | `com.zillow.android.streeteasy` | 参考 3.127.1 / 22850 | 待核实 | LATEST_USABLE_UNPROVEN |
| 携程旅行 | `ctrip.android.view` | 8.97.4 / 2133 | 8.97.4 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |
| ANA | `jp.co.ana.android.tabidachi` | 参考 7.6.0 / 339 | 待核实 | LATEST_USABLE_UNPROVEN |
| Sidecar Verification | `local.pocket4.fixture` | 未读取 manifest / 0 | 待核实 | LATEST_USABLE_UNPROVEN |
| WebView Browser Tester | `org.chromium.webview_shell` | 未读取 manifest / 1 | 待核实 | LATEST_USABLE_UNPROVEN |
| Owned Editor Contract | `org.droidloom.qa.editorcontract` | 参考 1.0 / 1 | 待核实 | LATEST_USABLE_UNPROVEN |
| Fcitx5 | `org.fcitx.fcitx5.android` | 参考 0.1.3-0-g048f581c / 114 | 待核实 | LATEST_USABLE_UNPROVEN |
| 哔哩哔哩 | `tv.danmaku.bili` | 9.18.0 / 9180300 | 9.18.0 | INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING |

## 复现、保留与清理

`python3 -B build_checkpoint.py` 只读取已有回执、原始字节和 source pins，再原子写出进度；不执行 Android、Git 或删除。nanosecond/monotonic 整数由 Python 原样解析。缺终态、日志不完整、版本/UID/数据/epoch不一致、出错或未知不会计入成功。

`GIT_CHECKPOINT_FILES_NEXT.json` 列出已有分支下一 checkpoint 的来源/配置/复现入口和公开元数据收据；排除 pycache、APK/二进制及私人 UI/凭据内容。root-private 命名的有限资格元数据按明确清单保留，不据文件名丢掉生命周期证据。此清单不提交 Git、不删除排除对象、不改冻结 manifest。

整个当前 launcher 集合、最终 framework、所有实际功能与长期/恢复检查达到 production ready 后，才进入已授权的旧 framework/App/实验/中间版本清理。当前没有执行该清理，回收 0 字节。最终保留可工作的源、精确 source-lock、配置/安全边界、实际包/签名/来源清单和复现/故障结算收据。
