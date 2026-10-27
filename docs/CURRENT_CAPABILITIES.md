# 当前能力、源码与验收边界

<a id="2026-10-26-产品整改的当前来源"></a>
## 2026-10-27 当前配对与产品整改

当前选定 Hepta 来源为 [`de0ddaa41bd91c4f46a2f1b6034d25fa84c4469c`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/de0ddaa41bd91c4f46a2f1b6034d25fa84c4469c) / tree `004702e28244eb15a90ac0fa5d5a94e259dace8b`。本轮源 pin 收敛基线为 Desktop `1813bac14a829cd83ef3d5fdda4e96e71955190e` / tree `db199ec4e58bc645f0a10c13852950a7a3f7439e`；实际 Cargo 重新生成六根锁并验证后，再统一冻结最终 Desktop commit/tree，由实际 selection 与构建收据绑定。显式 preedit SDK prepared tree 保持 `6b422b3120f5f9b5c7ada579b55f647d51bd7fcf`，不改用默认 SDK 或 clipboard profile。

原 `baf73bf0` / Hepta FD 配对的 Cargo 14 条实际命令均 exit 0，五个普通 Cargo 根与独立 SDK stage/prepared lock 已完成六根完整核验；123 份必需来源、219 个原 Hepta manifest 及六根依赖图检查通过。这些结果不转授当前 de0 配对；当前六根锁仍须真实生成。原 AWS、owner/bridge、SDK helper 与来源角色继续使用同一合同。依赖与更新步骤见 [DEPENDENCIES](../support/ui/DEPENDENCIES.md) 和 [SOURCES](SOURCES.md)。这些结果不包含新组合的编译、运行或安装资格。

桌面 Shell 使用 Rust/Makepad，Notes 窗口使用 Rust/egui；会话与工具执行接原 Hepta Core/App Server。AI 界面的状态来自原 thread 的事件、授权结果和文档回读。输入框文本、模型回答、原操作收据和当前文档分别展示，模型说“已保存”不能替代 Notes 效果证据。[模块索引](modules/README.md)提供开发步骤和技术合同；[原生交接表](agents/NATIVE_ORGAN_MODULE_HANDOFF.md)对应各模块的实现与交接入口。

| 本轮工作 | 已取得的证据 | 尚未完成的验收 |
| --- | --- | --- |
| 当前依赖与来源 | 当前源 pin 选定上述 de0 / SDK 组合；原 `baf73bf0` / Hepta FD 的14条 Cargo命令、六根图与123份来源/219个manifest检查均已实际通过，但只属于该旧配对。 | 为 de0 真实生成与验证六根锁，冻结最终 Desktop，再绑定最终构建、安装与运行收据。 |
| 历史静态检查 | Desktop `e9642b55` 的普通/优化脚本各103项、fresh-cache各26项、来源合同各24项、84份模块文档/858链接通过，见[逐源记录](../results/integration/2026-10-27-current-blockers/desktop-e964-static.json)。 | 这些计数仅属于 e964 / H8d 旧静态来源，不移继给 fd 或最终 Desktop。 |
| 原 App 退出后的回读 | `8467f0dd` 保留同一只读恢复端点；原 App 被其 owner 确认退出后只启动固定字节 helper。旧组件六项、Session52项及同8d747的 Root 严格 Clippy 见[组件交接](../results/integration/2026-10-26-product-readiness/app-only-component-handoff.json)与[原始回执](../results/integration/2026-10-26-product-readiness/root-8467-8d747-clippy.json)。当前选源包含这条后继代码。 | 旧组件结果不证明新最终包；真实 Root/人类会话/模型中的 App 退出与原身份回读仍待执行。 |
| 回读来源合同 | `adf609b8` 增加 Session回读、固定helper和Root会话三个必需来源角色；旧普通/优化各24项见[回执](../results/integration/2026-10-26-product-readiness/desktop-adf-source-profile.json)。当前合同继续保留这些来源。 | 来源清单不会建立效果权限或恢复旧写者。 |
| Root 生命周期 | 原 FD `fd6d8d3f` 的 type、严格 Clippy、26项 custody/流/恢复、4项原 Supervisor、完整475项普通Agentd及17项Memory已实际通过；另两个原 ignored Root preparation 测试在真实UID0分别通过。当前后继保留同File custody、两条流的私有非等待准入及原 strong_count/身份/期限规则。 | 这些执行收据仍绑定原FD；当前后继的构建、安装、生产Root和真实Notes闭环另验。历史 H8d / `bb5677f6` [负控失败](../results/integration/2026-10-27-current-blockers/root-session-bb567-negative-selected.json)仅证明两个owner状态并存、effects=0，不证明重复效果。 |
| Linux 产品 | 旧 a9/H8d 原生 UI 流水全部16条实际命令均已 exit 0，已结束；只属于旧配对。旧 runtime 控制器遗失不能用日志 Finished 补成退出码，旧 Root 队列在未编译时取消的记录保留。 | 最终当前配对的 UI/runtime/Root 产品构建、最终安装包，以及真实人类和模型的一次授权 Notes 保存、原 thread 回读、丢回复/撤销/退出/重连/并发编辑、物理输入和读屏仍待同源完成。 |
| Windows | `37831e03` 原91项保持83 PASS、7 FAIL、1 LEAK；另两组各3/3、backend独立8/9，见[原分类](../results/integration/2026-10-26-product-readiness/windows-378-qualification.json)。`773d34e1` [原生诊断](../results/integration/2026-10-27-current-blockers/NATIVE-REPORT.md)保留原私有签名文件完整身份/DACL与LF输出事实。 | 773整体FAIL与未到backend断言的junction失败保留。独立 `0ba5adf2` 候选的严格GNU检查通过，真实Windows [run40460595505](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/40460595505)已构建真实helper，原91与独立4+4+2控制按其实际终态记录；尚未取得本次功能结果。collector1 PASS不证明功能，不提高原91计数，不继承Linux资格。 |
| Android / Asterinas | 原 Android APK/cert 已核实；严格 receiver 保留原 signer 要求。Asterinas继续提取唯一原 owner 的必要闭包。 | 原 Android 私钥未恢复、候选未安装；Native 最终 ELF 文件8MiB/LOAD16MiB门禁、完整F1/G2、资源恢复与真实驱动仍未闭链。 |

历史收据见[精选组件证据](../results/integration/2026-10-26-product-readiness/evidence-index.json)。`production_ready` 仍为 false；当前源码选择、静态检查或正在执行的任务都不构成完整产品验收。下文保留较早来源的历史实测，不把旧结果转授本轮。

Desktop `5b2f2db2` / FD 的实际 UI builder 与云端 native UI CI 均在 Session 的两处格式检查失败，未进入 UI 编译。后继 `1813bac1` 只按原 workspace edition 2021 格式化该文件，整个 UI workspace 的原格式检查已实际 exit 0；原 runtime 与 Root cache warm 自然结束后的真实结果仍由各自收据记录。

原 FD 云端 contract gate 的失败原因是历史 implementation-map 观察锚点与当前祖先/源码不符。`00d173380e2d1425f83040fae848773ac0a440aa` 只迁移37份导航/状态元数据，原 production qualification 两段实际 exit 0，未修改 Rust、Cargo 或校验脚本。当前 de0 再对一个测试夹具显式声明待测能力，保留生产撤回状态与原拒绝校验；Lane D 20项实际全部通过，完整后继资格收尾仍由其原收据记录。以上均不授予安装、生产效果或输入法资格。

## 历史归档与较早边界

本实施线来自 PR #257。最新已归档源码为 `39c1eaf89a211b91e5e687ceaf86fd033567e536` / tree `41afddf4360f18ad50d62f9647de6f2e4f602a0e`，其[Process successor内核两套实测](../results/integration/2026-10-24-asterinas-integration/kernel-process-successor/publication.json)通过，整流水455.040秒：普通core373/required134，G2 core387=完整373+原Root3+新增11，两套均无失败、过滤或软跳过，原始QEMU退出33。新增G2内核回归覆盖launcher准备与取消、子进程allocation释放门槛、世代重放与精确Root ACK门槛、history-only原namespace保留，以及原watchdog receipt在同一owner最终切换点的保存；原CPU连续性3项与successor prepare/commit5项在两套中继续逐项通过。799744字节旧静态ELF仍仅作G2编译输入，本流水未执行原Hepta owner或原生launcher用户态闭环。[f6e837c6两套CPU successor证据](../results/integration/2026-10-24-asterinas-integration/kernel-cpu-successor/publication.json)独立保留；本轮未运行allocator、MLSDisk、OSTD、ordinary产品QueryAbi/socket或watchdog六轮，它们最近的[完整同源证据仍属于824720ea](../results/integration/2026-10-24-asterinas-integration/kernel-owner-continuity/publication.json)，不转授39c1eaf8。原生daemon/writer/FinalUse与Supervisor/pidfd闭环、Root先持久保存再AckSaved、失回复与跨boot恢复、300秒有限grant后续续约及长期持久CPU控制仍待各自最终源码实测。0f6300e4、824720ea、f6e837c6及更早档案全部保留。

较早 `d5a21bb7` 的[缺页准入与 fallible 页表组合](../results/integration/2026-10-23-audit-closure/kernel-vmar-d5a21/publication.json)及其[首次 fixture 失败](../results/integration/2026-10-23-audit-closure/kernel-vmar-689c-failure/publication.json)继续保留。`0187bd57` / Hepta `b3d3f2d4` 另有原 daemon/store 和 Linux32 实测，`f3d54e5b` 有原 A10 十一项 Linux-host 执行体。每项结果只属于其明确来源，不给后续分支、远端 main 或部署环境转授资格。F1 CI 的源码选择现由同一份 `source-review.json` 提供，已修复旧 workflow pin 与 review 不一致；[68 项 host 回归和真实环境输出核对](../results/integration/2026-10-24-asterinas-integration/f1-source-pair/validation.json)只证明来源选择修复。

原生输入门禁现绑定 compiler manifest 与显式 V8 配对归档，并对 store 缓存执行跨进程独占锁；[runtime89/store27项实际 host 回归](../results/integration/2026-10-24-asterinas-integration/native-cache-profile/result.json)通过。普通 F1 拒绝所有可信 G1/G2 profile；这些输入检查不转授 guest 资格。

**当前没有完整生产控制、完整原生 F1/G2、通用桌面控制或手机产品资格。** 文档与源码门禁通过只能关闭对应工程问题；不能把单个 host、guest 或设备场景的成功扩展为产品验收。

## 2026-10-25 审计整改与当前配对

当前产品的唯一 Hepta 来源及 27 份关键文件身份由 [依赖合同](../support/ui/DEPENDENCIES.md)和 [source map](SOURCES.md#hepta-native-organ)绑定。三处 Cargo 入口与两产品锁同步更新；原生输入 SDK 只在显式 preedit profile 使用，默认 Git SDK 和 clipboard 候选各自保留独立合同。新的 ComposerTransaction 拒绝发布活动 preedit，确认后沿原 ChatWorkspace 更新；焦点补丁只处理同一窗口真实 gain/loss 转换，四项原 SDK 生命周期回归先复现再修复。

真实窗口在 Desktop `f7d36b32` / Hepta `1a76b508` 配对下通过 AT-SPI 七项、原子编辑五项和输入法前三项后，因中文提交不能一次撤销而失败；该失败保留，完整输入法资格未通过。后续显式 SDK 将组词预览隔离为事务，提交只产生一次净撤销，取消恢复原选区，检查点只含已提交文本；合法区外编辑保持精确 UTF-8 范围。补丁树 `6b422b3120f5f9b5c7ada579b55f647d51bd7fcf` 的原绘制 TextInput 实际事件测试 35 项及窗口焦点四项通过，并经独立源码审查；新产品仍须在最终配对上重新完成构建、原完整 IBus 窗口和 Notes 恢复验收，不能继承旧配对的窗口资格。详见[显式输入配置](../support/ui/PREEDIT_TEXT_PROFILE.md)。

[模块索引](modules/README.md)覆盖 16 个第一方 Cargo 入口、11 个开发域和原内核 57 个成员，提供各自开发步骤、技术合同、验证入口和当前限制。Notes 原生动作、独立只读文档观察与未知结果核对见 [Notes organ](../support/ui/NOTES_ORGAN.md)；保存、关闭、冲突和 recovery-only helper 见 [durability](../support/ui/NOTES_DURABILITY.md)。

[Desktop PR #267](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/267)、[Hepta 集成 PR #3938](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3938)和[输入事务修复 #3960](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3960)保留本轮源码与验证范围。早先 Desktop `0b19344a` / Hepta `1b980b0b` 的完整原生工作区 346 项、独立 host 23 项、Notes 普通关闭重开和真实 App/原 SQLite owner 崩溃恢复已有执行证据；后续最终配对必须各自绑定构建收据及实际运行结果，不能因为依赖重新固定而继承全部窗口或生产资格。完整 A06/移动设备、生产 Root authority 和掉电仍按各自门禁验收。

## 2026-10-24 Linux 产品集成增量

当前 UI、Session host 和原 Hepta 依赖补丁统一指向已发布 [Hepta `489f7096b0e5754968a30fa4477bb4417d24834f`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/489f7096b0e5754968a30fa4477bb4417d24834f)，完整 tree 为 `4731de9117065bd773b2fcee92c815ff896b8488`，产品工具链为 Rust 1.96.0。UI 根显式将 `accesskit`、`accesskit_consumer`、`accesskit_atspi_common`、`accesskit_unix` 四包固定到相同 Hepta SHA，避免依赖 workspace 的 patch 不向上继承。`services/hepta-os` 是本地 wire/transport crate，没有虚构新增 Hepta Git pin。完整 Desktop HEAD/tree、真实 Cargo 解析生成的锁和 features 仍由最终 source-profile 及构建收据绑定。

原始 [v10/v11 scoped 收据](../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)保留每次实际输入、命令、完整日志和退出码；下面计数只表示对应包/过滤范围，不合并计算为整仓通过。v8/v9 的原编译失败、文本失败和资源测试 panic 继续保存在[各自历史档案](../results/integration/2026-10-24-original-owner-product/text-native-v8-v9/README.md)，未被后续结果覆盖。

| 最新 scoped 执行项 | 实际结果 | 范围与未运行部分 |
| --- | --- | --- |
| 原 Agentd 库 | 349 passed / 34 ignored | ignored 未计为通过；包含未运行的专用 Root/FIFO 条件项。 |
| 原 Agentd/App Server 文本集成 | 8/8 passed | 实际原进程/协议路径，签名与模型输入仍有 fixture；不证明生产身份或真实模型装配。 |
| Legacy history 专用 API | 3/3 passed | 另有 1015 项 unselected；这不是完整 App Server 套件。 |
| 原 client 定向套件 | 29/29 passed | 仅所执行 client 包。 |
| 原协议包 | 306 passed / 1 ignored | ignored 未运行；不扩展为所有 runtime 接口验收。 |
| 原 Hepta native UI 单包 | 43/43 passed | 默认原 SDK `337566c8`；不是 Desktop 完整 workspace 或真实窗口。 |
| 原 AccessKit 保留源码包 | 54/54 passed | 默认原 SDK 组合；不授予候选 SDK 的 PasteText 或实际读屏资格。 |

以上最后两项属于默认 `hepta-native-makepad` / 原 `native-presentation`，不是 `hepta-native-clipboard-sdk` 候选。默认 renderer 仍是 egui；显式 Makepad profile 复用原 Makepad/Robrix、唯一 ChatWorkspace、原 IME router 和上述 owner。默认 SDK 用原 Git 锁和 54 文件资源包，无需外部 SDK config；独立 clipboard feature 才引用新 API、宣告 `PasteText` 并要求两份精确 patch、全 crate override、独立候选锁及 61 文件资源包。新增路径补丁保持原 Git SDK 解析到的 `num-traits` 0.2.20 来源，原 clipboard 补丁字节不变。原 SDK baseline 的 PasteText 返回 false 且不排队。两种源码/feature 错配由 preparer 拒绝；[候选流程与锁共存规则](../support/ui/PRODUCT.md#explicit-original-sdk-clipboard-candidate)不修改主线默认 SDK pin。

| 产品项 | 已执行结果 | 仍须完成 |
| --- | --- | --- |
| 原授权接纳及文本 thread | 上表 scoped 执行覆盖原文本接纳、历史、恢复、审批及其 client/protocol；adapter 借同一个原 ChatWorkspace，并保持原 thread/签名引用的身份。 | 实际部署 Root、人类身份、真实模型、原生产 writer 与安装后的恢复仍须端到端验收；fixture 不升级为生产授权。 |
| 原 writer 与 Notes 恢复 | 原 store 两项通过；实际 Session/App/helper 崩溃测试通过：一次效果、原 writer 关闭重开、独立回读至 Committed、退休回复丢失后 helper 重启返回 already_released，无旧效果重放。 | 原生产 authority 装配、Root/整机重启和最终安装包同源运行仍须验收。 |
| 原 Makepad、输入与辅助技术 | 原 native UI 43/43、AccessKit 54/54 scoped 测试通过，loader 测试已按原 `init_cx_os` 初始化。候选 clipboard API 另有显式 feature，默认组合不依赖它。 | 最终 Desktop 完整 workspace、release 构建、真实 Makepad 窗口、IME/CJK、读屏和候选 PasteText 各自待验；单包测试不替代这些门禁。 |
| 安装、升级和本地恢复 | 单入口、专属 Session 服务、配置诊断、v4 草稿、原资源包、停止后升级/回滚及保留数据卸载已落代码；安装器与 Android 期限源测试另有记录。 | 真实五程序包的系统服务/窗口/恢复/升级/回滚/卸载收据仍须按最终组合执行。 |
| Android 原 receiver | 既有组件档保留实际 Java 编译、DEX/zipalign 以及原 APK 验签；unsigned candidate 的签名拒绝按原结果保存。 | 当前候选仍须原 signer 签名、安装及实际 receiver/原 owner 回读；没有生成新 signer，也未取得生产设备控制资格。 |

完整原始失败、成功日志及范围见[原 owner 产品组件收据](../results/integration/2026-10-24-original-owner-product/README.md)。**最终两仓完整 workspace、release、真实原窗口、安装后生产运行与 Android 同 signer 签名仍未闭合。** 固定来源和导航见[本轮 Hepta source map](SOURCES.md#hepta-native-organ)及[模块交接](agents/NATIVE_ORGAN_MODULE_HANDOFF.md)。这组结果不改变下文 Asterinas、生产 G2、GPU/ARM 与手机平台的独立资格。

## 如何读取状态

- **候选已有实现**：指定源码内已有具体实现，可继续构建或集成；不是执行收据。
- **固定场景有记录**：手册或归档记录了某一 source/profile 的运行；应查对应原始收据，新组合不继承结果。
- **仍需完成**：实现、装配或真实执行缺口；不能用设计、脚本存在或开放 PR 标题标为完成。

[STATUS](STATUS.md) 保存按时间排列的证据；其中“当前”“未实现”、测试计数与 README 空文件要求只属于各段记录时点。[INDEX](INDEX.md) 提供模块入口；[ROADMAP](ROADMAP.md) 给出接续依赖。三者引用本表，不另造完成率。

## Linux host 产品入口与两仓组合

[`hepta-private-ci`](https://github.com/TrillionniumFoundation/hepta-private-ci) 保持原 Agentd、authority、writer/outbox 与 operation history；本仓的 Shell 提交用户意图并显示原观察，Session 管理本地应用进程，Notes 管理自己的文档和回执。安装器与本地草稿恢复不接管这些执行权威。

[安装与恢复手册](../support/ui/PRODUCT.md) 定义同一个 `trillionnium-desktop` 入口：安装、`run`、`doctor --live`、`stop`、升级、`rollback`、`uninstall`。包清单包含五个原 Rust 程序、完整文件哈希、两个完整 commit 以及原 source profile；release id 随整个文件清单变化。安装使用专属 user systemd unit，先确认 Session 停止再切换 release，配置及用户数据始终在独立稳定目录。Python 标准库用于安装与启动；UI 的 Rust 实现不因此变成 Web UI。

本地恢复 schema v4 已有具体代码：保存三个 workspace 的本地 composer rooms、匿名及最多四个 parked principal 的文本分区、已存草稿、context、tab 与选中项；原共享 ChatWorkspace 重建匿名文本，只有真实安装原 owner 后才取回对应分区。它不恢复 Hepta owner、发送状态、timeline 或任务新鲜度。仅当 v4 不存在时迁移 v3，保留旧文件；损坏 v4 不回退覆盖。自动文件上限64 MiB，手动 v1/v2 导出仍为4 MiB。私有目录与文件、单写者锁、完整验证、后台原子替换/fsync、损坏或新版本保留均有对应行为测试。IME 未完成时暂缓，非共享 composer 拒绝截断共享 archive 或多 room 文件。正常退出等待最新已排队检查点；强制终止仍可能丢失上次成功检查点之后的编辑。

这些是候选源码提供的产品流程，不是已通过生产控制资格的声明。最终 source/tree、Cargo features、实际五个二进制、配置及完整两仓验证收据必须与真实 systemd/GUI/恢复执行一起归档；单纯包校验或文件系统 fixture 不替代它。最终组合 pin 由整合收据给出，不能把这里的历史场景 source 自动复用为新包资格。

## A00–A10

| 领域 | 候选已有实现与开发入口 | 固定场景记录与仍需完成 |
| --- | --- | --- |
| A00 来源与发布 | [跨仓 source profile](agents/ORGAN_RELEASE_PROFILE.md) 绑定原 owner、受保护 authority 输入接口及 Notes target v1/bootstrap v2/recovery v1；[根入口](../README.md) 和模块指南已存在。 | 10-22 的 OS `85d394f…` / Hepta `6d6097d…` 有独立历史组合记录；它的旧 golden 不覆盖当前 v2/recovery 组合。最终 pair 的 build、verify、原包测试、部署与 CI 必须分别记录。 |
| A01 内核构建与启动 | [固定源码构建](../support/build/README.md)、[ktest](../support/build/ktest/README.md)、[当前原生 runtime 构建器](../tests/workloads/hepta_agentd_runtime/README.md) 保留 OSDK 来源与产物身份。 | 已有多个固定 QEMU 切片；新整合源码必须重跑对应门禁。某个 ordinary ELF 的 store 成功不等于完整内核套件、SMP 或裸机通过。 |
| A02 wire ABI | [os-abi](../libs/os-abi/README.md) 与 [HOS2](NATIVE_ABI.md) 提供 no_std 五操作编解码、golden、错误与容量边界。 | codec 资格不开放内核权限。普通启动仍是 QueryAbi；G1-c/d 使用各自显式 profile。 |
| A03 控制核心 | [API 合同](../libs/os-control/API_CONTRACT.md)、[验证手册](../tests/control/VALIDATION.md) 说明原 owner、D、退役、锁与模型范围。 | host/Loom/no_std 模型不能替代内核 IRQ/SMP、原 Hepta 磁盘确认与整树组合验收。 |
| A04 Linux/存储 | [ELF/ABI 交接](agents/handoffs/A04_LINUX_HEPTA_ELF.md)、[只读](../tests/workloads/linux/readonly/README.md)、[remount](../tests/workloads/linux/remount/README.md)、[utimens](../tests/workloads/linux/utimens/README.md)、[UDP](../tests/workloads/linux/UDP_LOCAL_ERROR.md) 有具体实现和 runner。 | [原 CognitiveStore](../tests/workloads/hepta_cognitive_store/VALIDATION.md) 记录原store场景；新[OS `0187bd57` / Hepta `b3d3f2d` 原生10检查](../results/integration/2026-10-23-audit-closure/native-runtime-0187-b3/publication.json)及[同核ordinary/完整Ubuntu32](../results/integration/2026-10-23-audit-closure/full32-0187/publication.json)已实际通过；仅该 store 场景，完整 F1、授权恢复与物理掉电资格保持未完成。 |
| A05 内核控制 | [Process 映像](ASTERINAS_PROCESS_IMAGE_G1C.md)、[G1-c](agents/G1C_TRUSTED_OBSERVE_PROFILE.md)、[G1-d](agents/G1D_TRUSTED_CONTROL_PROFILE.md) 有固定角色、原 CPU/D owner 与权限接合。 | 真实 Agentd 最终 exec 身份、生产 authority、原 writer/outbox 持久 K↔D 和同 guest 的故障核对/退役仍须统一运行。 |
| A06 资源与恢复 | [CPU owner](ASTERINAS_CPU_OWNER_G1A.md)、[pids](../tests/kernel/control/G1D_PIDS_ISOLATION.md)、[共享用户数据页限额](../tests/kernel/control/G1D_USER_MEMORY.md) 和 [独立 timer watchdog](agents/G1D_WATCHDOG.md) 已有候选代码。 | `0187bd57` 原全套 core303/allocator20/ML15 和 OSTD229报告通过（原TCG跳过3），相同OSTD ELF另在实际KVM229/229无跳过。已覆盖原Frame/VMO及管道/FIFO、Unix stream/seqpacket物理缓冲最后引用计费；原分配器保护extent和显式fallible页表另有对应回归。后续 [cgroup memory admission](agents/CGROUP_MEMORY_ADMISSION.md) 已把 `memory.max/current/events` 接到原层级用户数据与选定 IPC 帧 owner；它仍不覆盖 slab、其余 socket/设备资源、回收/OOM 或完整恢复保留。六boot watchdog属于 `10dae5ea`，可信用户暂停意图、完整资源保留、SMP与故障验证未闭合；284/286等旧失败完整保留。 |
| A07 Hepta 接合 | [observer/Objective/history/CPU adapter](../services/hepta-os/README.md) 和 [运行手册](../services/hepta-os/RUN.md) 有分开的 source 合同；[原 daemon runner](../tests/workloads/hepta_agentd_runtime/README.md) 保持原 FleetRegistry/Supervisor。 | 原包构建、no-turn daemon生命周期、UI目标提交、生产 FinalUse、持久效果与 G2 分别验收。新 `0187bd57/b3d3f2d4` no-turn生命周期8项及store10项确已通过，原构建器生成新kernel receipt；旧7d记录单独保留。较早配置拒绝另存；完整daemon静态207MiB仍超过可信profile界限。原device-owner独立入口构建/原strip后6.92MiB通过host结构检查，但未执行、不是完整daemon或G2。 |
| A08 Android | [AOSP与ABI](../support/android/README.md) 及 [物理设备 smoke](../compat/android/PHYSICAL_SMOKE.md) 分开构建、签名和验证限定测试APK。 | `f89023ac` 在用户指定 POCKET4 所连现有Android17手机已实际install/input/save/force-stop/relaunch/readback/cleanup通过，host196项在普通与优化模式各通过。[去设备标识收据](../results/integration/2026-10-23-audit-closure/mobile-app-f890/acceptance.json)仅证明限定APK场景，不提供Asterinas Android、ARM BSP或生产设备控制资格。 |
| A09 硬件/VMM | [平台调查](../support/hardware/DECISION.md)、[VMM gates](../support/vmm/GATES.md) 和 [生命周期模型](../support/vmm/device_lifecycle/README.md) 提供具体边界。 | 模型不执行真实 DMA/IOMMU/IRQ/reset。目标GPU、VMM、ARM设备的任务、撤销、静止、复位与恢复仍须真实实现和验收。 |
| A10 Rust UI | [五crate入口](../ui/README.md)、[Session期限/启动锁](../support/ui/BOUNDARIES.md)、[Notes双通道与持久owner接合](../support/ui/NOTES_ORGAN.md) 已有候选代码。 | 历史 egui/Weston/Notes只支持其固定 Linux host 场景。已接入 `6b16d38a` 原生Notes受控入口、AccessKit及主动动作/被动轮询独立队列；[`f3d54e5b`完整原A10十一执行体](../results/integration/2026-10-23-audit-closure/a10-f3d54e5b/publication.json)已通过，含实际X11像素、AT-SPI、Weston、共享presenter与最终清洁；原临时目录及pyc失败另保留。后续Session/Shell重启、持久owner、慢客户端与真实输入新阶段仍须按最终组合验收。新产品线包含本地composer恢复及Notes应用持久化/回读helper；通用设备target、完整IME/读屏、Asterinas显示输入、移动UI仍未资格化。 |

## 尚未取得的产品资格

当前 CPU 权重合同已收紧：原 `cpu.weight` 没有 group-weight 调度实现，因此合法写明确
返回 `EOPNOTSUPP`，非法输入保留原错误，读保持中性默认 `100`；详见
[真实属性边界与回归要求](agents/CPU_WEIGHT_UNSUPPORTED.md)。这项修复不将权重执行、
SMP公平性或完整恢复保留标为完成；新增测试必须按最终源码保留实际 guest 证据。

| 资格 | 本检查点状态 | 完成条件 |
| --- | --- | --- |
| 生产授权与效果 | 未通过 | 原 provider、protected clock、external frontier、keyring、revocation、recovered writer、current-cut 按实际部署装配并执行；source manifest始终保留 `production.activation: disabled` / `effects_authorized: false`。 |
| 完整原生 F1 | 未通过 | 同一新内核/Hepta二进制运行原daemon、store、任务与恢复；原库store测试与no-turn生命周期都是子集。 |
| 原生生产 G2 | 未通过 | 真实 FinalUse→原 writer/outbox→内核效果→故障核对→持久终态→连续退役，包含丢回复、撤销、kill/reboot。 |
| 完整资源恢复 | 未通过 | 计入剩余内核/设备资源，可信暂停意图与原分配器物理保留、自主恢复、耗尽/碎片/SMP/时钟故障全部按相同profile验证。 |
| 通用桌面、移动与硬件 | 未通过 | 每个明确平台的配对、授权、输入/观测、动作、撤销和恢复；限定APK或Notes演示不能代替通用能力。 |

这里的“未通过”不抹除已经实现或已有局部收据的工作。后续关闭某一行时，记录完整 source/tree、工具链、feature、二进制/输入、实际命令、原始结果和剩余边界；没有执行就写未执行，不以新文档回填历史。

## 开发与文档交接

进入模块先读其 README 和共享合同，使用明确的工具链与最小相关门禁。每个变更要说明状态/权限 owner、I/O/错误、恢复和下一项验收。底层通用 crate 可复用 rustdoc/book，无需复制空模板。

根 README 允许导航内容，但必须是普通文件。`support/build/verify-source.py` 继续核对固定上游源、锁与枚举的派生；A02 继续把 README 字节和哈希纳入不可变输入快照。历史 `results/**` / `**/evidence/**`、旧快照及其验证器按原身份保留，不因新 README 规则而重写旧成功或失败。
