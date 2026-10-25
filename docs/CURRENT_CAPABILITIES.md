# 当前能力、源码与验收边界

独立内核线的既有归档检查点来自 PR #257：源码为 `39c1eaf89a211b91e5e687ceaf86fd033567e536` / tree `41afddf4360f18ad50d62f9647de6f2e4f602a0e`，其[Process successor内核两套实测](../results/integration/2026-10-24-asterinas-integration/kernel-process-successor/publication.json)通过，整流水455.040秒：普通core373/required134，G2 core387=完整373+原Root3+新增11，两套均无失败、过滤或软跳过，原始QEMU退出33。新增G2内核回归覆盖launcher准备与取消、子进程allocation释放门槛、世代重放与精确Root ACK门槛、history-only原namespace保留，以及原watchdog receipt在同一owner最终切换点的保存；原CPU连续性3项与successor prepare/commit5项在两套中继续逐项通过。799744字节旧静态ELF仍仅作G2编译输入，本流水未执行原Hepta owner或原生launcher用户态闭环。[f6e837c6两套CPU successor证据](../results/integration/2026-10-24-asterinas-integration/kernel-cpu-successor/publication.json)独立保留；本轮未运行allocator、MLSDisk、OSTD、ordinary产品QueryAbi/socket或watchdog六轮，它们最近的[完整同源证据仍属于824720ea](../results/integration/2026-10-24-asterinas-integration/kernel-owner-continuity/publication.json)，不转授39c1eaf8。原生daemon/writer/FinalUse与Supervisor/pidfd闭环、Root先持久保存再AckSaved、失回复与跨boot恢复、300秒有限grant后续续约及长期持久CPU控制仍待各自最终源码实测。0f6300e4、824720ea、f6e837c6及更早档案全部保留。

较早 `d5a21bb7` 的[缺页准入与 fallible 页表组合](../results/integration/2026-10-23-audit-closure/kernel-vmar-d5a21/publication.json)及其[首次 fixture 失败](../results/integration/2026-10-23-audit-closure/kernel-vmar-689c-failure/publication.json)继续保留。`0187bd57` / Hepta `b3d3f2d4` 另有原 daemon/store 和 Linux32 实测，`f3d54e5b` 有原 A10 十一项 Linux-host 执行体。每项结果只属于其明确来源，不给后续分支、远端 main 或部署环境转授资格。F1 CI 的源码选择现由同一份 `source-review.json` 提供，已修复旧 workflow pin 与 review 不一致；[68 项 host 回归和真实环境输出核对](../results/integration/2026-10-24-asterinas-integration/f1-source-pair/validation.json)只证明来源选择修复。

原生输入门禁现绑定 compiler manifest 与显式 V8 配对归档，并对 store 缓存执行跨进程独占锁；[runtime89/store27项实际 host 回归](../results/integration/2026-10-24-asterinas-integration/native-cache-profile/result.json)通过。普通 F1 拒绝所有可信 G1/G2 profile；这些输入检查不转授 guest 资格。

**当前没有完整生产控制、完整原生 F1/G2、通用桌面控制或手机产品资格。** 文档与源码门禁通过只能关闭对应工程问题；不能把单个 host、guest 或设备场景的成功扩展为产品验收。

## 2026-10-24 Linux 产品集成增量

当前 UI、Session host 和原 Hepta 依赖补丁统一指向已发布 [Hepta `22e87e0dd6560a7b925e716a33011378ae07a9a2`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/22e87e0dd6560a7b925e716a33011378ae07a9a2)，完整 tree 为 `7e376f5d3509cf38e13b513ca2b87d9eecd7dc47`，产品工具链为 Rust 1.96.0。UI 根显式将 `accesskit`、`accesskit_consumer`、`accesskit_atspi_common`、`accesskit_unix` 四包固定到相同 Hepta SHA，避免依赖 workspace 的 patch 不向上继承。`services/hepta-os` 是本地 wire/transport crate，没有虚构新增 Hepta Git pin。完整 Desktop HEAD/tree、真实 Cargo 解析生成的锁和 features 仍由最终 source-profile 及构建收据绑定。

本阶段新增[产品阶段执行报告](../results/integration/2026-10-24-product-closure/README.md)。已发布Desktop代码为 `0a268d8928d76682a59c8cc0be88428845f40ce3`，tree `d7c0d61a1519db8f4b0a7178b9f6867f85719b48`；本地 `cb34422` 和远端 UI v3 `5f8244bd` 与其精确同树，提交身份分别保留。Hepta仍为上述 `22e87e0` / tree `7e376f5d`。前三份证据清单分别约束35个历史阶段文件、24个UI/Notes/独立material文件和20个最终Python文件，失败记录未覆盖。新增[v3清单](../results/integration/2026-10-24-product-closure/closure-evidence-v3/inventory.json)归档71个原文件及inventory/plan，六项后续native/static输入仍按收集时点标为deferred。canonical实际执行Desktop为 `a7621d8022f52add679bd6edba5d0bad6772dabc`，审阅提交为 `1f94c4b11ed7a71ec7bb9344a40c8f284da5c7e4`，两者tree均为 `e9026801f2686b7ea3f89759609c326f72fb2cfa`；与较早UI v3的tree不同，不能重写历史回执。后续文档提交的HEAD也不替换这些已执行代码身份。 新[native/Android终态清单](../results/integration/2026-10-24-product-closure/closure-evidence-v4-native-android/inventory.json)另归档58个原文件及inventory/plan，16706753个原字节逐项核对；两条原paired路径记为`not_executed`。新清单不改写v3历史deferred或Orca v4的独立21文件失败组，也不把本批a762/22、a37/7ecc结果转授后续619e/717 IME或native优化源码。

| 本阶段执行项 | 实际结果 | 来源与限制 |
| --- | --- | --- |
| UI v2 core + app | 99 passed / 1 ignored；真实CJK字体另单独1 passed | tree `c6fe2020`；默认忽略的字体测试通过显式真实字体gate执行，不把ignored直接计为通过。 |
| 最终 UI v3 app | 48 passed / 1 ignored；strict all-target Clippy与3 ELF build均exit0 | tree `d7c0d61a`；三个程序是Session、Notes app-window、Notes recovery；不是完整UI workspace/release或Makepad资格。 |
| 最终普通 Notes v5窗口 | 5/5 passed | 三ELF摘要与v3完全匹配；新PID1831275/1831516分别经XRes1.2核验，原Session内新task/incarnation恢复只复制文本，继续编辑到revision2，旧pending receipt和checkpoint保持。真实OS剪贴板与AT-SPI，仍非物理IME或原writer生产终态。 |
| 最终Python gates | spec普通/`-O`各53，source mutation普通/`-O`各10，Android24，产品工具65，source verifier全部通过 | 发布`0a268d89`代码树，所有接受的gate 0失败/错误/skip；产品sandbox首轮63+2error保留，相同未修改65项经已授权本地主机执行后全通过。 |
| Clipboard SDK canonical | UI workspace release/all-targets：318 passed、0 failed、2 ignored；strict Clippy和五程序build均exit0 | 清洁源码、Rust1.96.0、`--locked --offline`、独立锁/config、102个同树SDK package及61资源均由原回执绑定；复用existing target cache，未证明空缓存或新OS cleanroom。两个ignored是app-window和Shell各一次显式真实字体测试。 |
| 实际产品包与可信安装 | pack通过；真实A1→B2→A3→B4和两项flock竞争拒绝通过 | B有72文件/61资源；stripped Shell `080ad7e9…`，而窗口使用unstripped `e315c61f…`；全部原record/immutable inventory已归档。没有启动原Root或实际安装UI，不授予生产认领。 |
| 原Makepad v3窗口 | atomic EditableText七项通过，包含request-scoped PasteText；整体失败于真实IBus preedit guard | 使用canonical原ELF和匹配资源，XRes绑定PID2272477；物理键盘、Wayland IME、完整Orca及真实生产thread均未资格化。v1/v2失败记录保留。 |
| 原Makepad v4焦点诊断 | 整体仍失败于同一真实IBus preedit guard；全部已记录X11焦点查询保持窗口12582916，而Message的AT-SPI焦点丢失 | 同canonical unstripped ELF，新XRes PID2305860；只收到两次VisibilityNotify，无FocusIn/FocusOut。原Orca确有speech初始化及焦点事件处理，但consumer/human qualification仍false。[21文件原证据](../results/integration/2026-10-24-product-closure/closure-evidence-v4/orca-v4-evidence-inventory.json)不授予完整Orca/IME资格，也不包含后续native/Android终态。 |
| 独立Hepta `7ecc` host增量 | 首轮八库1059 passed/4 failed/3 timed out/99 skipped；原七项换durable `/data` fixture后7 passed/979 skipped，95.731秒；新Root material4 passed/400 skipped，13.514秒 | 七项只改TMPDIR/TMP/TEMP，原期限和八份测试ELF前后摘要不变；Root4使用独立sealed ELF `12c607ce…`、前后clean同源50文件gate。两者都不替代完整八库、static admission或guest F1/G2；后续实际终态见下两行。 |
| 完整八库full03/full04 | 03为1049 passed/16 failed/1 timeout/99 skipped；短路径04为1065 passed/1 timeout/99 skipped，736.657秒 | 同7ecc与八测试ELF、原单线程/零retry/期限。03过长harness路径导致Unix socket失败，04的16项失败消失；唯一容量测试仍60.006秒timeout。两个原wrapper均未执行paired步骤，完整suite exit100。 |
| 原static入口02 | 原build+strip均成功；实际ELF13243416 bytes超过8388608-byte（8MiB）上限，原runner exit1 | 独立Desktop a37 / Hepta7ecc，两份21621条source快照逐字相同；原features、profile与8/16MiB门槛未改。built/packaged=true、static_profile=false，未执行原生ELF或guest，不授予F1/G2。 |
| Android a762原receiver新构建 | SDK35、Java/DEX/zipalign和原APK资源复用通过；9source文件及工具/JDK/JAR前后相等，unsigned APK19402 bytes | 新a762实际执行，原二进制Manifest已保留。signed/deployed=false、设备动作0、unsigned验签false，原signer证书不是私钥；仍需原签名、strict部署、原peer/live verifier及原owner验收。 |

原Root/AppServer retained authority、实际安装UI认领与旧/新活进程隔离、原Notes生产writer终态，以及Pocket4原签名、已部署strict helper/APK与原peer/live verifier依赖仍未满足。真实包的行政安装/升级/回退事务已通过其限定范围，不能替代这些生产身份与进程生命周期验收；host和Root fixture也不关闭独立内核线。

原始 [v10/v11 scoped 收据](../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)保留每次实际输入、命令、完整日志和退出码；下面计数只表示对应包/过滤范围，不合并计算为整仓通过。v8/v9 的原编译失败、文本失败和资源测试 panic 继续保存在[各自历史档案](../results/integration/2026-10-24-original-owner-product/text-native-v8-v9/README.md)，未被后续结果覆盖。

| 既有 v10/v11 scoped 执行项 | 实际结果 | 范围与未运行部分 |
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
| 原 writer 与 Notes 恢复 | 原 store 两项通过；实际 Session/App/helper 崩溃测试通过：一次效果、原 writer 关闭重开、独立回读至 Committed、退休回复丢失后 helper 重启返回 already_released，无旧效果重放。 本阶段另有最终代码树的普通文档恢复v5 5/5通过：只复制旧文本到新effect身份并继续本地CAS编辑，旧pending receipt未转移；该测试明确original_writer_terminal=false，不重新证明前述历史原writer终态。 | 原生产 authority 装配、Root/整机重启和最终安装包同源运行仍须验收。 |
| 原 Makepad、输入与辅助技术 | 默认SDK原native UI43/43、AccessKit54/54 scoped结果保留；另有选定clipboard SDK的完整UI workspace release318 passed/2 ignored、strict Clippy/五程序build，以及原atomic EditableText/PasteText七项通过。 | 真实Makepad v3/v4整体失败于IBus preedit未触发原composition guard；v4另记录OS窗口与Message焦点分歧，原Orca有限事件处理不授予完整资格；物理IME、Wayland、完整Orca和后续最终组合窗口仍须各自实际验收，不能由构建、默认SDK或Notes窗口代替。 |
| 安装、升级和本地恢复 | 单入口、Session服务、配置、v4草稿及保留数据流程已有代码；最终Python产品工具65项通过。新实际五程序包pack及Root sealed A1→B2→A3→B4、两项原flock拒绝通过，immutable路径/字节/权限/inode保持。 | 原Root/AppServer对实际安装UI的认领、活进程升级/回退隔离、该安装组合的真实系统服务/窗口/恢复/卸载尚需原生产输入和回执；本轮行政事务未启动安装UI。 |
| Android 原 receiver | 新a762 clean source原builder已实际完成SDK35 Java/DEX/zipalign和原APK资源复用，9receiver文件与工具图前后相同，原Manifest保留；[完整新执行回执](../results/integration/2026-10-24-product-closure/closure-evidence-v4-native-android/android-unsigned-a762-final/execution-receipt.json)及unsigned验签拒绝归档。 | 当前候选仍须原signer授权签名、strict helper/APK安装测量及实际receiver/原owner读回。没有新signer、部署或设备动作，runtime_host_binding_verified_by_wrapper=false原样保留；不是生产设备控制资格。 |

完整原始失败、成功日志及范围见[原 owner 产品组件收据](../results/integration/2026-10-24-original-owner-product/README.md)。**普通Notes窗口、本地Python gates、选定clipboard SDK的UI workspace release构建、真实包、行政安装事务及a762 unsigned receiver构建已在各自范围内通过；Makepad v3/v4真实IBus仍失败，独立native full04仍有容量timeout，static02仍被8MiB准入拒绝，两个原paired步骤未执行。原Root/AppServer生产认领、原Notes writer终态及Android原signer/strictreceiver/原peer依赖仍blocked；host结果不授予guest资格。** 具体状态见[阶段执行报告](../results/integration/2026-10-24-product-closure/README.md)，不从历史收据合并推算。 固定来源和导航见[本轮 Hepta source map](SOURCES.md#hepta-native-organ)及[模块交接](agents/NATIVE_ORGAN_MODULE_HANDOFF.md)。这组结果不改变下文 Asterinas、生产 G2、GPU/ARM 与手机平台的独立资格。

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
