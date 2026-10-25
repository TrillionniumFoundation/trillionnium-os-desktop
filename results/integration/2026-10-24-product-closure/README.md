# Desktop / Hepta 产品阶段执行报告

执行证据日期：2026-10-24；本次补充整理于2026-10-25。范围：本次获授权的 P0-1—P0-4、P1-1—P1-3 实现与验证，以及独立内核线的边界。

**当前结论：选定clipboard SDK的完整UI workspace release测试、strict Clippy、五程序构建、真实产品包和行政安装/回退事务均已按原回执通过；尚不能宣称所有P0/P1或生产设备控制闭合。** 较早UI/Notes实现保留[Draft PR #262](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/262)身份；canonical候选的审阅发布为[PR #263](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/263)，执行commit与同tree审阅commit分别记录。普通Notes v5的5/5回执继续保留。[E10][E11][E12][E16][E17] 实际Makepad v3的atomic EditableText七项通过，但完整尝试失败于真实IBus preedit检查；v4保留同一失败，并记录X11焦点查询保持原窗口而Message界面/AT-SPI焦点丢失，未取得Orca资格。[E13][E21] 原Root/App Server保留身份、实际安装UI认领、Pocket4原signer/strict receiver/原peer等输入仍缺，未以新身份替代。Android在a762源码上的新unsigned build已通过，原二进制Manifest保留，签名/部署/设备动作仍未执行。[E22] 独立native完整八库短路径复验为1065 passed/1 timeout/99 skipped；原静态入口编译、打包成功后因13243416字节超过8MiB而拒绝，guest资格未开放。[E23][E24] 七项durable及Root4的通过范围继续独立保留。[E18][E19]

本报告记录本阶段的实现、实际执行和仍未满足的验收条件。`PENDING` / `in-progress` 表示对应作业或证据尚未完成，不表示通过。源码路径相对对应仓库根；下列证据目录与本文一同归档，原始失败和来源身份均保留。

## 1. 固定身份与证据完整性

| 对象 | 本次固定身份 | 解释 |
| --- | --- | --- |
| UI v3/Notes v5已发布实现 | commit [`0a268d8928d76682a59c8cc0be88428845f40ce3`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/0a268d8928d76682a59c8cc0be88428845f40ce3)；tree `d7c0d61a1519db8f4b0a7178b9f6867f85719b48` | PR #262；与本地`cb34422ba37a3d92d362c1efba2faa4da090a58a`及远端UI v3精确同树，保持该历史运行身份；不是后续canonical独立锁的tree |
| Desktop 工作起点 | `d8b2bc6fb715af8ed27dfec09e3dfa8b94fa5bd2` | 审计中的候选起点，不能继承其先前验收给新代码 |
| 选定 Hepta | commit `22e87e0dd6560a7b925e716a33011378ae07a9a2`；tree `7e376f5d3509cf38e13b513ca2b87d9eecd7dc47` | 三项已发布增量覆盖原 Runtime Android connector、原 Root deployment lock、原文本历史投影；见 [PR #3761](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3761)、[PR #3762](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3762)、[PR #3763](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3763) |
| Linux host Rust | `1.96.0` | 与独立内核 nightly、旧 F1 用户态 profile 分开 |
| Clipboard SDK canonical执行 / 审阅 | 执行 `a7621d8022f52add679bd6edba5d0bad6772dabc`；审阅 `1f94c4b11ed7a71ec7bb9344a40c8f284da5c7e4`；共同tree `e9026801f2686b7ea3f89759609c326f72fb2cfa` | [原build回执](closure-evidence-v3/sdk-final/canonical-build-v1/receipt.json)绑定a762；PR #263绑定1f94。同tree不等于同commit；旧回执不重标为审阅或文档HEAD |
| 独立native本批实际源码对 | Desktop `a37d366f8f826e1808ecd0a34d5ef75fbbf3716b` / tree `be21cd4914668a27140c68541e3637880a3e0c34`；Hepta `7ecc1d58d383e15f6f59646a371e837b64e49887` / tree `fc7112c4c2b9f83674f65a860e1f1be1cd1f518e` | static02与其完整源码前后快照；与产品a762/22、后续619e/717 IME候选分开，不互授结果 [E24] |
| 第一批证据包 | `closure-evidence-v1.tar.gz`；SHA-256 `3e33a32a87c19545ad12e7d081eec8bcf212c0e7ef74879ec854497d81c3786e` | 已按 [inventory](closure-evidence-v1/inventory.json) 独立逐项核对 **35 个文件**的字节数和 SHA-256，全部匹配；inventory 自身不计入 35 |
| 第二批证据包 | `closure-evidence-v2.tar.gz`；SHA-256 `56a63d64c5de0aadf11d0f6dbc075f638691e168e636e2cd7b166df41ec21bc3` | 已按[inventory](closure-evidence-v2/inventory.json)独立核对24文件，包括UI v2/v3、Notes v5和旧c821 Root material fixture |
| 第三批证据包 | `closure-evidence-v3.tar.gz`；740423 bytes；SHA-256 `de835eaf1b48e3d054a68d699900d31a049c0fcbd8f3e36b14584f212c219b76` | [inventory](closure-evidence-v3/inventory.json)列77路径：71原文件已逐项核对字节/SHA，另6项deferred未读取；加inventory/plan共73文件。8MiB范围内的原metadata仅在仓库保存一次；没有复制大型ELF或包archive |
| 第四批中的Makepad v4失败组 | `orca-window-v4-debug.tar.gz`；158354 bytes；SHA-256 `6b2c622cf172e8d5998c8dc3d485267a0f549072fab8b76cc8928471ebec2b9b` | [独立清单](closure-evidence-v4/orca-v4-evidence-inventory.json)绑定21个原文件，逐文件与原archive核对一致；两张失败状态截图已查看，未复制private Xauthority或凭据。这是独立的v4 Orca失败组；Android/native/static终态在另一个固定清单中归档 |
| 第四批native/Android终态组 | `closure-evidence-v4-native-android.tar.gz`；3595594 bytes；SHA-256 `912e305b02f12c45fbb184c3621da3c56bde458ecf46c6f8c4b1cf53623a6128` | [inventory](closure-evidence-v4-native-android/inventory.json)列60路径：58原文件16706753 bytes，另2条paired步骤明确`not_executed`；加inventory/plan共60实际文件。所有原文件与tar成员字节/SHA均核对，未复制ELF/APK/DEX/签名材料 [E25] |
| 最终本地 Python gates | [summary](final-python-gates/summary.json)、[inventory](final-python-gates/inventory.json) | **20 个受清单约束文件**及其 inventory；保留8次尝试，7条最终接受命令；原始失败不覆盖 |

证据包保留成功、失败和截图，不只挑选通过记录。它包含较早 Notes v4、最终输入修复前的失败负例、原锁 Clippy 对照实验、Hepta 定向测试等。第一批35文件保留原时点范围；第二批24文件已经补入 UI v2/v3 与 Notes v5 的独立原始证据，Python gates 使用自己的清单。第三批补入canonical成功、实际package/安装、Makepad失败及独立native host的原回执；E12通过、E13整体失败，均保留准确范围。六项后续native/static路径在v3收集时仍deferred，原v3清单不回填。新native/Android组补入其终态，其中full03/full04均在原library失败后停止，paired步骤仍未执行；收集exit0不代表这些步骤或产品资格通过。[E23][E24][E25]后续文档/证据提交会改变Desktop commit/tree，旧回执不改写成新HEAD执行。

## 2. P0/P1 闭合矩阵

“已实现”表示代码路径和合同存在；“已验证”只表示表中明确范围。完整条目的关闭条件仍包括其对应生产/平台验收。

| 项目 | 已实现与已验证 | 当前结论 / 未闭合条件 |
| --- | --- | --- |
| **P0-1：源码、feature、锁、资源、当前能力和失效spec收敛；同源构建** | 原Hepta声明/patch、双锁和source mutation收敛；canonical统一toolchain、config、feature、独立锁、SDK图及资源；旧Clippy转发错误和3项格式敏感spec已修复。最终Python gates保留原53/10/24/65及source verifier通过范围。[E14] | **选定canonical UI workspace release构建已验证。** 318 passed/2 ignored、strict all-target Clippy、五程序build和61资源绑定均通过。[E12] 使用clean source checkout、locked/offline和existing target cache；未证明empty-cache/全新OS cleanroom，更不等于完整Hepta workspace或native runtime资格。 |
| **P0-2：可信安装、原Root认领实际UI、升级/回退隔离** | 原部署锁和child fd边界、5项native定向/4项UID0锁测试及65项产品工具保留；新真实B包72文件/61资源通过原Root sealed installer执行A1→B2→A3→B4，原stage/rollback持锁拒绝、record不变与A/B immutable文件保持均有完整回执。[E6][E14][E16][E17] | **行政安装/回退与真实锁拒绝已通过；原生产链blocked。** 验收driver持锁不等于original Root serving lifetime；未启动原Root或安装UI，仍缺原daemon pidfd/registration、原human profile、实际child认领与原App Server route的活进程隔离验收。 |
| **P0-3：真实中文进入同一 App Server thread，流式/工具/产物/取消/重连同身份** | 原 `ChatWorkspace` 对混合 text/attachment 历史使用有界惰性占位，保留中文、item/thread/turn 身份；Desktop adapter 新增原类型历史/后续中文流回归。原 UI core 57 项通过；选定 Hepta 上 native-text adapter 9 项及 strict Clippy 通过。 | **源码与定向测试完成；真实生产对话 blocked。** 没有本次最终安装 UI 经原 retained authority 到真实模型的同线程完整回执；fixture 的中文流、历史和取消测试不能代替该运行。 |
| **P0-4：Notes 效果恢复与普通文档恢复** | 普通“重新打开已保存的笔记”可从原状态目录读取关闭文档，只复制文本到新 incarnation；原 pending receipt、旧 effect 身份和原 writer 所有权不转移。存储 CAS、故障保留、串行 worker 与独立恢复均保留。最终 v5 真窗口回执已确认 `passed=true`、5/5 检查通过。 | **普通文档恢复最终同源运行通过，回执与新窗口/二进制身份已归档。[E11]** 原生产授权修改→应用持久 receipt→独立读回→原 writer durable terminal→重开不重放的整条生产验收仍 blocked。v4/v5 的 seeded pending receipt 不证明原 writer 终态。 |
| **P1-1：选定renderer的实际IME、焦点、选区、undo、剪贴板、键盘和读屏** | Notes egui负例及最终v5保持原来源；新canonical Makepad原ELF/资源已实际运行，v3原AT-SPI smoke、atomic EditableText七项、request-scoped PasteText及private real speech voices阶段通过。v4只读诊断记录X11与Message焦点分歧，原Orca有speech初始化及事件处理。[E10][E11][E12][E13][E21] | **Makepad整套窗口资格未通过。** v3/v4均失败于真实IBus preedit未触发原composition guard；v4的`orca_consumer_qualified=false`保留。完整EditableText、Orca消费/人工评价、物理键盘与Wayland IME均未资格化。不能由方法检查或部分Orca活动推广成全窗口通过。 |
| **P1-2：生产 OriginalAndroidTextDevice，固定 owner/device/app 的真实中文动作与故障读回** | 原retained MCP peer/Tokio connector与12项定向测试、Desktop device-organ24项host测试保留。[E8][E14] 新a762原receiver已实际使用SDK35、原APK资源完成Java/DEX/zipalign，原Manifest保留；9个receiver文件及工具/JDK/JAR图前后相等，unsigned APK为19402 bytes，签名验证仍false。[E22] | **连接器、host测试和当前源码unsigned build完成；生产动作blocked。** 原binary Manifest已取得，剩余原signer授权签名、strict helper/APK部署与验签、原live peer/source verifier、device/cell/editor及目的专属FinalUse验收。`signed=false`、`deployed=false`、设备动作0；没有新signer或替代owner。 |
| **P1-3：新增桌面/移动动作的平台、权限、身份、取消与恢复合同** | 新 `docs/agents/ACTION_CAPABILITIES.md` 逐类列出本地 UI、chat、Objective、Notes、Android只读/strict set-text 和未开放动作；修正 Android intent 的 exact integer schema；文档关联原 owner 和执行边界。 | **合同增量完成。** 不据文档宣称新增通用控制能力；click/scroll/swipe/key/launch、Windows/macOS、物理 Android/iOS 等缺独立 backend/owner/后置条件/恢复验收时仍未支持为生产 organ。 |
| **独立内核线：Asterinas F1/G2、资源恢复、原生图形和硬件** | `7ecc`durable七项7/7、当前Root4/4保留host范围。[E18][E19] 完整八库03使用过长fixture路径，1049 passed/16 failed/1 timeout；同八ELF换短路径04为1065 passed/1 timeout/99 skipped，原期限未改。[E23] `a37/7ecc`原入口已build+strip，21,621条原source snapshot记录前后相等。[E24] | **完整suite与static admission仍未通过。** 04唯一容量测试60.006秒超时，两个原wrapper的paired步骤未执行。静态产物13243416 bytes超过原8388608-byte上限，未执行原生ELF或guest；原8/16MiB门槛未改。F1/G2、资源恢复及硬件不继承host结果。 |

## 3. 关键实现和已证实问题

### 3.1 同源构建与旧 Clippy 失败的实际原因

当前 source guard 会检查全部选定 Hepta 声明、必需原 patch 和两个真实 Cargo lock 的命名 packages，拒绝遗漏、替换或混用。最终发布代码树的通过回执记录7个 manifests、29个 Hepta 声明、UI 锁154个和 host 锁149个原 Hepta packages；该工具明确输出 `runtime_tests=not_run_by_this_tool`、`production_authority_verified=false`。[E14]

旧 SDK candidate 的 Clippy 失败**并非命令完全没写 `--config`**。实际旧命令把它放在 `cargo --config ... clippy` 的外层；Clippy 是外部 Cargo plugin，内层 Cargo 未得到同一 override，随后 `--locked` 拒绝另一份解析图。独立 probe 对原 `31bbb8c295546fb0ed5073292dd107e0dac49349` candidate 改为 `cargo +1.96.0 clippy --config ... --release --locked --all-targets --features trill-shell/hepta-native-clipboard-sdk -- -D warnings` 后实际 exit 0，lock 前后 SHA-256 均为 `b3fe18f7e75d80594ab5145ae5b192b6f8605c59d850a8264be5c8f775cf1d3a`，工作树仍干净。[E3]

新 `support/ui/verify_native_sdk_candidate.py` 把 metadata、全部 target tests、strict Clippy 和二进制 build 统一到相同 toolchain、feature、子命令后的 config、`--locked`、target directory 和 profile。每步前后检查源码/锁/config/SDK树与实际依赖边，失败保留日志并停止；不会删除 `--locked` 或自动改锁。它有**2个独立测试方法**：实际 Cargo external plugin 的新旧 argv A/B，以及真实 child 对 lock/config 两种输入变更的拒绝验证；不是3个测试，也不是只检查字符串排列。已导出的实际 Cargo 执行结果为2项通过。[E2]

baseline Makepad仍使用原`337566c8` SDK及54资源；本次clipboard candidate使用prepared SDK tree `e5ae930cc6a0a528719673deff44ec2830f4bdfa`，原source receipt验证102个SDK packages同树与依赖边。canonical UI lock SHA为`c3fc7793678ad269321fb32b4669d4ac37ab8a8ce63be600aea21b310decb132`，全crate config SHA为`d3b0461a6052499e66cb0687d593b68d124004195ee9634f6d53a015e13fa911`；metadata、test、Clippy和build均使用Rust1.96.0、`trill-shell/hepta-native-clipboard-sdk`、`--locked --offline`，release测试/Clippy覆盖整个UI workspace的all-targets，build覆盖其bins。[E12]

原test.stdout的20段结果合计318 passed、0 failed、2 ignored；两次ignored均是`host_fonts::tests::selected_real_font_covers_egui_proportional_and_monospace`，分别来自app-window和Shell，原因为需要显式`TRILL_UI_TEST_CJK_FONT`。较早v2字体单跑保留原来源，不把本次ignored算通过。源码工作树是clean；target使用既有`ui-release-target`缓存，CARGO_BUILD_JOBS=2。该记录不是空缓存或全新OS的cleanroom验证，也不是完整Hepta workspace测试。

61文件resource bundle与verified SDK/source profile相互绑定；SDK source与资源准备回执原有`compiled=false`保持，organ source-profile仍仅为`source-only`，这些原字段不改写。实际canonical build receipt另行记录`compiled=true`，`runtime_qualified=false`、`production_authority=false`保持。rustfmt、host-package和product pack随后全部exit0。[E16] 需要区分两种实际Shell：

| 用途 | 字节数 | SHA-256 |
| --- | ---: | --- |
| canonical/实际Makepad窗口，unstripped | 89419784 | `e315c61f4d28a097aaa461164a3ef4567e91cb7482b8b9dc0539cd9a388dd6a7` |
| B包/行政安装，stripped | 83702008 | `080ad7e93a85b2c1b564e7f382312c9be1609f3e1687a37cbe61a178063ad674` |

原qualifier与build receipt实际配对的是第一份；安装manifest及immutable inventory实际验证的是第二份。包和host archive的原回执SHA分别为`96e92963967bc9336f3eda04c74a5228090ee016c6b9a737aa1cfa76fa5ba660`与`e475ef2a01740b086a12331c25eae60f36ea185b92b3039e9655bf04273a3cc7`；本证据包未复制或重新hash大型archive。

HOS2 旧 spec 的3项失败来自旧 boot-ID owner 拼法和行折叠假设。新 lexical source guard忽略注释/排版，但保留 literal、cfg、语句顺序和原 Process owner 边界；负对照保留注释中的旧安全文字，同时变更真正 feature/authority/identity 仍被拒绝。该修复没有关闭原行为测试、放宽 errno/feature contract，也没有把 source checks 冒充内核运行。源码与详细命令：`docs/current/FOUNDATION.md`、`tests/spec/test_a05_capspace_nonce.py`、`tests/spec/test_a05_effect_path_fail_closed.py`。

### 3.2 普通 Notes 恢复与效果恢复保持各自身份

保存的 Notes 仍位于原 state root 下的 `<session>-<task>-<incarnation>/document.json`。新列表/恢复路径复用该目录句柄、原独占 incarnation lock 和唯一持久 snapshot；没有增加第二份 ledger。目录扫描有界；读取拒绝不安全 owner/mode、链接、非普通文件、损坏或过大的 snapshot。打开时重新获取源锁，复核选择时的完整 checkpoint摘要及revision；原文档还活着、snapshot已变或目标新文档已被编辑时拒绝。

目标必须是未编辑的新 incarnation，只经原 serial worker 的 `local_edit`复制文本。原 pending/retired receipt、grant、旧 operation、旧 target 不进入新 checkpoint；源文件保持原字节。旧 receipt 仍由独立 recovery helper 在旧 incarnation 下读回/精确 retirement，helper仍拒绝 effect。新目标的本地编辑与外部修改使用同一个 revision CAS；故障继续冻结写入并保留可独立恢复的信息。冲突不会因下一次键入静默消失，用户明确选择保留编辑或加载保存内容。源码：`ui/core/src/notes_catalog.rs`、`ui/core/src/notes_store.rs`、`ui/app-window/src/notes_worker.rs`、`ui/app-window/src/notes_organ.rs`、`support/ui/NOTES_DURABILITY.md`。

早期真窗口 v4 的原 Session 创建旧 task1 和新 task2，incarnation不同；真实中文通过 OS clipboard 进入 egui 并持久保存；普通 WM_DELETE_WINDOW 关闭并由原 Session reap；用户实际操作保存列表重新打开文本，继续编辑到新 revision2；旧 checkpoint hash保持不变，独立 helper读回原 pending receipt。两窗口分别以 XRes1.2 查询实际 server PID，AT-SPI只选择对应自身PID；共享 XID 被重用不被当成身份连续性。5项检查和3幅截图均保留。[E4]

该 v4使用旧 `trill-app-window` SHA-256 `f7957d5a478d62acf7c40b6ba2f260ece4ec6aa1522492fdc69200f1f59143c0`；它只证明当时普通 reopen路径。最终 v5另有5/5成功回执，其三份ELF摘要逐项与最终v3构建回执一致，harness与原Hepta XRes helper的摘要也已对当前固定源码核对。[E11]

| v5实际程序 | 字节数 | SHA-256 |
| --- | --- | --- |
| `trill-session` | 4634232 | `1003c2ff56f02ee93b8565125654da47236f8faec0f2d995562bd89942f354fb` |
| `trill-app-window` | 36435984 | `2ffe518c0bb3161931150e74b0442205bc226843a43760a832cd4e4959576ad9` |
| `trill-notes-recovery` | 1593552 | `699d030322e9111bd268f1601a417c3765248137521827d5d54a12d8f7a52d32` |

v5两窗口的实际PID为1831275与1831516，分别经XRes1.2核验；同一个6291459 XID被重用不构成进程身份继承。原Session `48242f162051eaa45b69d207a1fee73b` 内，旧task1/incarnation `fec4223e517d33975a87032f0c878c63`的文本，经实际保存列表打开为新task2/incarnation `756a539aab7516ed4fcc2af995a2e000`。继续编辑后新revision为2，旧checkpoint仍为 `ddd767497c390f02dbb7dce09e72c99828f2fadfb8fb1255ec6e164975cf03a2`，新checkpoint为 `b448fd5a5300cffe0c2e9eef2b13631f10821a0bcf3fb7b58ffc3be9a7c7364a`。三幅截图、session日志、runner日志和原回执均保存。图02标为“重开后的保存列表”：此刻尚未点击打开，不能用它证明已恢复文本；真实文本恢复及随后修改由原回执和图03“继续编辑”共同证实。测试明确记录 `production_authority=false`、`original_writer_terminal=false`、`physical_ime_qualified=false`，这些字段不因窗口成功改变。

### 3.3 IME/光标缺陷以真实 egui 负例收敛

原 egui Preedit会修改 TextBuffer，Disabled不会自动恢复已提交文本；caret改变也可能使 Commit报告changed却未插入确认文本。因此仅依据 `response.changed()`保存会把未确认的候选文本持久化。本次新增的真实 egui负例在修复前实际返回 `Some((4, "temporary"))`，测试失败并保留日志；不是先写实现再用同构 mock证明自己。[E5]

最终修复在 `raw_input_hook`、原 TextEdit及原 ActivationGuard之间保留事件顺序：同帧 Commit后来的新composition分帧处理；取消恢复原已提交文本、selection和深拷贝undo状态；own ACK只能推进精确匹配的本地revision，外部变更不能自动变成composition基线。同帧pointer+Commit先让原TextEdit在原anchor提交，再仅投递一次原pointer；跨帧pointer-only结束composition并恢复文本，晚到的真实Commit在新caret重新建立anchor。延后pointer仍由原ActivationGuard读取保留的原Commit语义进行effect fence；Commit不再交给TextEdit重放，确认键释放等待保持原规则。最终回归还检查guard fence、原事件向量不变以及下一raw frame清理标记。

最终v3远端提交为 `5f8244bda093588db907bde38643f43bc32a7add`，tree与发布代码0a268d89及本地cb34422相同。v3 app二进制测试48 passed/1 ignored、strict Clippy、3 ELF build均exit0。[E10] 实际字体测试使用 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`，SHA-256 `b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a`。默认被忽略的唯一字体测试是 `host_fonts::tests::selected_real_font_covers_egui_proportional_and_monospace`，原因是需要显式 `TRILL_UI_TEST_CJK_FONT`选择真实host字体；本次在v2 tree `c6fe202017c2b67373d5e6984344386268a4c9d0` 单独执行该gate，结果1 passed/48 filtered。v2→v3只改app的main、notes_input及其测试，`ui/host_fonts.rs`两树blob均为`f5ba4839b3360802fbf1eb82a4d86bf9bc5b55b1`；仍保留字体执行的v2来源，不能把v3默认ignored简单计为通过。[E10]

### 3.4 原 Root、文本和 Android 所有权边界

可信部署入口只把审核package变成Root-owned program/resource binding，不创造principal、lease、writer或human authorization。原launcher必须已持有原daemon pidfd、原registration与Root0600 profile；新UI还需被原Root认领实际child pidfd并绑定原App Server route。Root持有部署锁期间stage/rollback拒绝；结束后回退只选择已验证旧release，新启动仍需新进程的原认领。4项UID0真实lock测试证明fd锁边界，不能证明缺失的原生产上下文已注入。[E6]

新增真实安装事务另有原完整回执。[E17] Root sealed driver SHA `3fa4869829cbe8dc1ecf7f9b367b187a03f0cf68096f2e633c17db23d7e7c341`，三份原installer模块前后完全一致。部署prefix为`/var/lib/trillionnium-native-stage-20261024-01/deployment`，A release为`6ee49848a4da-b6a10e16adab`，B为`a7621d8022f5-7bb3f08ce5c1`；实际record依次为A1、B2(previous A)、A3(previous B)、B4(previous A)。A/B目录下分别有65/73个实际文件（含各自manifest；manifest本身列64/72项）。原driver逐步核对文件SHA、长度、权限、owner、inode/device、nlink、mtime/ctime及目录身份，回退复用原A路径、再升级复用原B路径。两次真实flock拒绝同时证明record字节/元数据及release entries不变，持锁者明确是验收driver。回执仍记录`original_root_claim=false`、`original_root_launched=false`、`installed_ui_executed=false`、`qualified=false`；行政事务不创造原authority或human profile。

原文本历史修复对外部客户端的image/audio/skill/mention等内容只展示惰性类型占位，不解析路径/URL或扩张权限；中文与原item/thread/turn继续保留。Desktop适配器9项和原core57项通过证明类型/流/恢复逻辑的定向行为。实际原模型、工具/产物回执、断线后同thread重连及原取消终态仍需要缺失的retained Root/App Server输入，不能通过构造另一个Root或新thread替代。[E7][E8]

Android连接器实现固定`pocket4`、原受审helper与原Runtime `process_start/status/read`协议；要求同一原peer/runtime及独立live verifier。apply只发一次原payload；readback必须新建独立只读调用且不得重用旧job。超时、取消、撤权或不确定结果永久关闭effect lane，保留原job诊断与原writer恢复身份；源码没有自动重连、刷新授权、重放、替代signer或第二操作数据库。12项定向测试保留了这些拒绝路径。[E8]

当前源码另有一份真实unsigned receiver构建回执。[E22] 原builder `build_receiver.py` SHA为`fab498c1d3d6b06b4f62518199d5fe11381e29062f8607c06c1381aa83302670`，执行Desktop `a7621d8` / tree `e902680` 的工作树在构建前后均clean。9个receiver source文件和工具、JDK payload、D8/APK signer JAR依赖图的两份原快照完全相等；十条实际命令记录均exit0、无超时或日志溢出，stdout/stderr摘要与归档逐项一致。原builder使用SDK35及`--reuse-original-resources`，没有签名参数。该次外层作业exit0、9.345秒，属于新a762执行，不能只凭产物与旧候选同hash替代这次回执。

原APK为20847 bytes、SHA `a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058`，原signer证书摘要为`7c36bafbdb2789384aeae9dabf69cca6b468f6c1a2d75952ab315288b77ff7f7`。原二进制`AndroidManifest.xml`已保留，SHA `8ee050bbc4bc9938ebcfbb1bf1d6cea3414de9e868ca9b141dfa0dd27e921494`；旧签名条目/签名块已由原builder移除，不能把旧签名当成新代码的授权。实际DEX为36048 bytes、SHA `8afb8f4d5d5fdc9196e5e07756a3511d180bd825118a666c5ed3aa6db0f83394`，unsigned APK为19402 bytes、SHA `e32995b4d135b78d704c0f43ef35337b7360cadcb85508c626c637a6f270f4a1`。本档只归档原回执及日志，没有本地重读APK/DEX二进制；这些产物摘要保持为原执行记录。

原回执明确`signed=false`、`deployed=false`、`device_mutation_attempts=0`、`unsigned_apk_signature_valid=false`、`signing_required_for_deployment=true`；`runtime_host_binding_verified_by_wrapper=false`也原样保留。已安装的ChatGPT Runtime工具可调用，不等于其authenticated client已经注入Agentd；原Manifest和旧helper/APK存在，也不等于strict receiver已用原签名部署。仍需原signer私钥或原授权签名服务、实际stricthelper/APK/signature测量、原peer live verifier、原device/cell/editor observation及目的专属FinalUse，生产效果验收维持blocked。具体合同：Hepta `codex-rs/hepta-memory/PRODUCTION_ANDROID_TEXT.md`、Desktop `support/android/receiver/README.md`、`docs/agents/ACTION_CAPABILITIES.md`。

### 3.5 实际Makepad v3/v4：原方法检查通过，真实IBus失败

v1/v2窗口失败及其wrapper/runner保留。v3使用canonical unstripped Shell和相同resource inventory，原XRes1.2将窗口绑定到PID2272477；原GStreamer preflight、AT-SPI smoke、atomic EditableText及private speech voices阶段exit0。七项atomic方法检查包括完整CJK/grapheme set、字节前缀与undo/redo、copy/cut/delete、UTF-8/范围拒绝、request-scoped PasteText及oversize拒绝、延迟clipboard跨room防护、stale EditableText对象跨room拒绝。[E13]

整体原回执`passed=false`：`original-real-ibus`退出1，原oracle报告真实IBus preedit未触发原composition guard。该次只用真实IBus/libpinyin及XTEST ASCII输入`nihao`，没有Unicode注入或合成IME事件；失败不被七项方法检查覆盖。`full_editable_text_qualified`、`physical_keyboard_qualified`、`wayland_ime_qualified`、`orca_human_evaluation`均为false。辅助observer记录两个事件且明确`is_orca_consumption_evidence=false`；不能用它代替原Orca消费或人工可用性。原Agentd没有启动，authenticated send也未资格化。后续修复/尝试须附各自新source/ELF/运行回执。

#### v4：X11窗口焦点与Message焦点分歧

v4的21个原文件已逐项与原archive核对，保留完整Orca log、原IBus错误、只读X11/AT-SPI事件、失败readback、checkpoint及两张实际截图。[E21] 原source仍为`a7621d8022f52add679bd6edba5d0bad6772dabc` / tree `e9026801f2686b7ea3f89759609c326f72fb2cfa`，unstripped Shell仍为89419784 bytes、SHA `e315c61f4d28a097aaa461164a3ef4567e91cb7482b8b9dc0539cd9a388dd6a7`，构建回执与资源inventory摘要与canonical/v3一致。新窗口在读回前后均经XRes1.2绑定PID2305860/XID12582916；不能把与v3相同的数值XID当成同一活进程。

原阶段记录仍是GStreamer、AT-SPI smoke、atomic EditableText、private speech voices退出0，`original-real-ibus`退出1；失败后的只读诊断退出0不改变`passed=false`。真实libpinyin接受的测试输入为XTEST ASCII `nihao`，没有Unicode注入或合成IME事件；原错误仍为`Real IBus preedit did not engage the original composition guard; last error: None`。v4没有宣称修复完成。

以下时间来自同一组原monotonic时间戳，以X11 observer初始记录为0；事件记录和查询共同限定了可得出的结论。

| 相对时间 | 原证据 | 实际观察 |
| --- | --- | --- |
| 0秒 | X11 initial-input-focus | 原窗口12582916拥有X11输入焦点；observer已订阅FocusChangeMask与VisibilityChangeMask。 |
| +2.360239615秒、+2.461818003秒 | 两条VisibilityNotify | 状态依次为1、0，事件中的当前input focus均为12582916；整份事件流没有FocusIn或FocusOut。 |
| +2.626008821秒、+2.631270134秒 | 原AT-SPI focused事件 | Hepta Conversations frame获得focused状态，随后Message / 消息 entry丢失focused状态。 |
| +20.748423011秒及observer最终查询 | 独立失败readback / summary | XGetInputFocus与最终查询仍为12582916；frame focused=true，Message focused=false、文本为空、caret=0，New draft仍enabled。 |

因此，**在本次已记录的事件和查询范围内，OS窗口焦点保持不变，Message的界面焦点状态却已丢失。** 这支持焦点状态分歧这一诊断，不能推广为未观测区间的连续证明，也不能单凭诊断归档认定某个源码修复已有效。独立XIM查询虽列出六种服务端style，但原字段`shell_selected_xic_style_observed=false`、`xic_created=false`；它没有观察到Shell实际选择的XIC style。

完整原Orca log还记录了speech factory初始化、对窗口与Message标签的语音输出尝试，以及原event manager收取、排队并处理上述焦点事件。这是实际的有限Orca行为，不是只有外部observer；但原`orca_consumer_qualified=false`和`orca_human_evaluation=false`保持。外部两类observer本身也明确不是Orca消费资格。真实IBus流程失败，物理键盘、Wayland IME、原Agentd和authenticated send均未资格化。截图只证明捕获到的空editor/失败状态，不能当作成功中文preedit或人工读屏评价。后续正式源码修复必须绑定新的source、ELF和原窗口gate结果；本组没有复制private Xauthority、私人音频配置或凭据，也没有授予新资格。

### 3.6 独立7ecc host复验与当前Root material

Hepta `7ecc1d58d383e15f6f59646a371e837b64e49887` / tree `fc7112c4c2b9f83674f65a860e1f1be1cd1f518e` 的原八库首轮1066次执行为1059 passed、4 failed、3 timed out、99 skipped；七项单线程/零retry隔离仍失败，原失败均保留。16次真实4096-byte pwrite+fsync测量显示当时`/tmp` ext4 median391.278ms/max2168.174ms，而`/data` ext4 median1.324ms/max1.752ms。这是当时环境测量，不是任意后续失败的统一诊断。[E18]

durable七项复验只改`TMPDIR/TMP/TEMP`到新私有`/data` ext4目录，不用tmpfs、不改SQLite配置、原测试期限或源码；八个原测试ELF前后SHA完全相同。原Nextest结果7 passed、979 skipped，95.731秒，单线程、零retry；其中claim-query测试实际55.337秒通过。该定向结果没有替代完整八库，也不声称系统I/O独占。v3的后续完整八库/static02六路径在收集时明确deferred；原记录不回填，现已另取终态。[E23][E24]

后续两次完整八库执行保留各自原result及完整stderr。[E23]

| 执行 | 原fixture路径与结果 | 当前边界 |
| --- | --- | --- |
| durable-long 03 | `.../native-full-libs-durable-data-03/fixtures`；1066执行，1049 passed、16 failed、1 timed out、99 skipped；719.064秒 | 过长的harness TMPDIR引入Unix socket路径错误：13处`SUN_LEN`、1处`AF_UNIX path too long`，另两项control错误种类断言失败。原结果全部保留，不把这组harness失败归为源码回归。 |
| durable-short 04 | `/data/h7-261024-04`，同一durable ext4设备；1066执行，1065 passed、1 timed out、99 skipped；736.657秒 | 同八测试ELF与原断言/期限，03的16项失败均转为pass；唯一剩余`qualification_tests::claim_query_rejects_more_than_512_references`在60.006秒timeout。完整suite仍为exit100。 |

两次均单线程、零retry，八个ELF在各次前后相等，也与E18 durable七项的ELF逐一相等；没有关闭fsync、换tmpfs或延长测试期限。原result的`failed_cases`字段沿用首轮七项名单，本节当前计数和唯一剩余失败按各自完整stderr统计。两个wrapper都在library失败后停止，原paired-regressions步骤**未执行**；清单将两条路径记为`not_executed`、`source_opened=false`，后续独立paired结果不能回填为这两次已经运行。

当前源码另重新执行四项原Root material测试。[E19] `source_before/source_after`均为clean `7ecc`，唯一parent为`d8badc4558fa872aaa37fb8aabe7c794f8d747db`，精确50个变更文件和base diff SHA `11dd42802fb65d44ec5d60741aefb3c48ba99c88ff5ad8ce140dfb57e813e84d`一致。原/封存测试ELF均为39043560 bytes、SHA `12c607cedac79990424ceec30552a877443d3812f7e4064189c82b815f49043e`，新owner namespace为`/var/lib/hepta-material-final-20261024-01`。四项覆盖真实owner cold-open/逐generation恢复、错误cut/原pointer拒绝、不同physical attempt保留partial与published predecessor、失败候选不阻止distinct successor；原just/Nextest以ignored-only精确filter、零retry、单线程执行4 passed/400 skipped，13.514秒。旧c821的4/396及另一ELF保留为E15，不转授本次。`native_qualification=false`和`power_loss_qualification=false`不变；该Root fixture ELF也不与durable七项的memory测试ELF混为同一产物。

### 3.7 原静态入口：编译和包装完成，8MiB准入拒绝

原`build_original_entry.py`在独立Desktop `a37d366f8f826e1808ecd0a34d5ef75fbbf3716b` / Hepta `7ecc1d58d383e15f6f59646a371e837b64e49887`组合上执行metadata、原`hepta-native-cpu` release build、原发布符号归档/strip和readelf，四条命令均exit0。[E24] 源码前后快照逐字一致：Desktop11194条、Hepta10427条，共21621条文件记录；entry源码摘要和Cargo.lock摘要也与原快照匹配。工具链1.96.0，原release保持thin LTO、4 codegen units及包装前line-tables-only debug，`features_disabled=false`、`profile_overridden=false`、`limits_changed=false`。

实际unstripped入口为65918184 bytes、SHA `6281816d911d3fe8f977f902a47fdfb11b7e6dd94496df485aa0e315e04815a7`；经原脚本剥离后为**13243416 bytes**、SHA `a76cd047ae38628338ac1931a7f5f8417792ac26f3a694fd77544c2c3a491eaf`。它仍超过原**8388608-byte（8MiB）**文件上限，原runner最终exit1，错误`static initial ELF size out of bounds`。`built=true`和`packaged=true`不覆盖`static_profile_passed=false`；原16MiB mapped LOAD门槛也未改。既有target cache的复用和原exclusive lease明确记录，未宣称cold build。

独立`nm`、`size`、`readelf`三条只读诊断均exit0，其完整stdout摘要与归档一致。其中`.text`为10596377 bytes、`.rodata`为1170860 bytes；readelf报告无dynamic section。这些只用于定位体积，不能当作原准入或guest成功。回执保持`executed_binary=false`、`native_role_verified=false`、`persistent_cpu_verified=false`、`recovery_verified=false`、`g2_complete=false`。本档未下载大型ELF，产物摘要来自原执行回执；后续native优化与新的619e/717 IME源码组合均须独立构建和运行，不继承本批a37/7ecc或a762/22结果。

## 4. 模块文档与 Rust / AI-native UI 的准确结论

当前模块入口已经覆盖11个非vendor产品/support Rust packages、UI virtual workspace和4个测试packages，57个内核workspace成员也有索引和共享/专项手册。新增`docs/current/MODULES.md`、`docs/current/FOUNDATION.md`与`docs/agents/ACTION_CAPABILITIES.md`把源码owner、开发命令、技术合同和未验证边界连到当前实现；原dated inventory继续保留原统计。**这不等于每个crate都有两份独立、完备且跨平台验证过的手册。** 各平台真实display/input、GPU/reset、存储介质/掉电恢复、移动receiver和原生owner运行矩阵仍需持续维护。

现有UI是Rust实现：ordinary Notes/应用窗口为egui，Shell另有原Hepta Makepad renderer及单独clipboard SDK candidate。它属于Rust原生程序、自绘UI路线，不能据此称为系统原生控件，也不等于Windows/macOS/Android/iOS的权限和设备控制已经落地。主机launcher使用Python不会把renderer变成Web UI。

以Hepta为核心的AI-native路径在本次改动中继续保持：原core/workspace承担统一语义状态，UI展示有界原历史与效果状态；提交、停止、审批、恢复各自保留原操作/线程/权限身份；模型文本和附件不能变成authority；新动作需具体backend、目标身份、原权限、后置条件和取消/恢复合同。普通恢复可恢复用户文本，不恢复旧效果权限。该结构是可继续开发的基础；生产能力仍取决于各条真实原owner接线和同源运行资格。

## 5. 已归档执行证据

| 引用 | 文件 / 实际结果 | 不支持的推论 |
| --- | --- | --- |
| **E0** | [inventory.json](closure-evidence-v1/inventory.json)：35文件byte/hash全部核对一致 | 不自动证明测试本身或最终源码已经通过 |
| **E1** | [desktop-test-v1-results.json](closure-evidence-v1/desktop-test-v1-results.json)、[测试日志](closure-evidence-v1/desktop-test-v1-0.log)、[Clippy日志](closure-evidence-v1/desktop-test-v1-1.log)：早期core/app-window 90 passed、1 ignored；strict all-target Clippy exit0 | 绑定其记录的patch，不是最终cb34422全量测试；字体ignored不算通过 |
| **E2** | [final-ui-v1-results.json](closure-evidence-v1/final-ui-v1-results.json)、[2项runner回归](closure-evidence-v1/final-ui-v1-0.log)、[source guard](closure-evidence-v1/final-ui-v1-1.log)：前两步exit0 | 同一作业随后caret负例失败，因此不能称整个v1通过 |
| **E3** | [sdk-config-forwarding.json](closure-evidence-v1/sdk-config-forwarding.json)、[实际Clippy日志](closure-evidence-v1/sdk-config-forwarding.log)：旧candidate原锁前后不变，配置转发修正后strictClippy exit0 | 只定位旧失败，不给最终22e87 SDK candidate build/window资格 |
| **E4** | [Notes v4回执](closure-evidence-v1/notes-window-v4/receipt.json)、[runner日志](closure-evidence-v1/notes-harness-v4/runner.log)、[原文档](closure-evidence-v1/notes-window-v4/01-original-note.png)、[重开后的保存列表](closure-evidence-v1/notes-window-v4/02-reopened-note.png)、[继续编辑](closure-evidence-v1/notes-window-v4/03-continued-note.png)：5/5 passed | 旧二进制、合成键盘/真实剪贴板/私有Xvfb；非物理IME、原writer terminal或最终v5 |
| **E5** | [final-ui-v1-2.log](closure-evidence-v1/final-ui-v1-2.log)：46 passed、1 failed、1 ignored；caret负例实际捕获旧preedit被作为local edit | 这是必要失败证据，不能删除或改为pass；修复结果须另附 |
| **E6** | [native-root-lock-tests-v2.json](closure-evidence-v1/native-root-lock-tests-v2.json)、[日志](closure-evidence-v1/native-root-lock-tests-v2.log)：同一测试ELF SHA绑定，UID0运行4项全部通过 | 不是原Root/AppServer的生产认领、安装升级或真实授权效果 |
| **E7** | [final-host-native-results.json](closure-evidence-v1/final-host-native-results.json)、[9项测试](closure-evidence-v1/final-host-native-0.log)、[strictClippy](closure-evidence-v1/final-host-native-1.log)：选定Hepta22e87，Desktop当时424ac288/tree db63d653；两条命令exit0 | host文本代码范围的验证；不能把该Desktop树身份写成最终cb34422，也不是模型/设备E2E |
| **E8** | [hepta-test-v1-results.json](closure-evidence-v1/hepta-test-v1-results.json)、[Android日志](closure-evidence-v1/hepta-test-v1-0.log)；[hepta-test-v2-results.json](closure-evidence-v1/hepta-test-v2-results.json)、[native日志](closure-evidence-v1/hepta-test-v2-0.log)、[core日志](closure-evidence-v1/hepta-test-v2-1.log)：Android12 passed/376未选，native5 passed/438未选，core57 passed/0未选；scoped fix/fmt/Bazel update exit0 | 定向filter未选测试不是通过；合成source/target与进程内MCP测试不是真设备，patch身份仍须与最终发布对象核对 |
| **E9** | Notes [v1](closure-evidence-v1/notes-window-v1/receipt.json)、[v2](closure-evidence-v1/notes-window-v2/receipt.json)、[v3](closure-evidence-v1/notes-window-v3/receipt.json)及对应runner日志：保留a11y未启用、错误Status路径、未聚焦新窗口导致guard拒绝的失败 | harness修复未降低PID/XRes/ActivationGuard要求；不把失败阶段重新描述为通过 |
| **E10** | [UI v2回执](closure-evidence-v2/final-ui-v2-results.json)、[v2测试](closure-evidence-v2/final-ui-v2-0.log)、[真实字体](closure-evidence-v2/final-ui-v2-1.log)；[最终UI v3回执](closure-evidence-v2/final-ui-v3-results.json)、[v3测试](closure-evidence-v2/final-ui-v3-0.log)、[strictClippy](closure-evidence-v2/final-ui-v3-1.log)、[build](closure-evidence-v2/final-ui-v3-2.log)：v2 core+app99 passed/1 ignored，字体单独1 passed；v3 app48 passed/1 ignored，Clippy及3 ELF build全0 | v2 tree c6fe202与v3 tree d7c0d61分别保留；v3不是完整UI workspace/release/Makepad qualification。字体ignored测试实际执行在v2，不重标为v3 |
| **E11** | [Notes v5回执](closure-evidence-v2/notes-window-v5/receipt.json)、[runner](closure-evidence-v2/notes-window-v5-runner.log)、[session](closure-evidence-v2/notes-window-v5/session.log)、[原文档](closure-evidence-v2/notes-window-v5/01-original-note.png)、[重开后的保存列表](closure-evidence-v2/notes-window-v5/02-reopened-note.png)、[继续编辑](closure-evidence-v2/notes-window-v5/03-continued-note.png)：`passed=true`，5/5 checks通过，三ELF摘要与v3完全一致 | 新PID1831275/1831516和新target/checkpoint独立核对；不借v4身份。真实OS剪贴板+合成键盘，不是物理IME或原writer生产terminal |
| **E12** | [canonical receipt](closure-evidence-v3/sdk-final/canonical-build-v1/receipt.json)、[test stdout](closure-evidence-v3/sdk-final/canonical-build-v1/test.stdout.log)、[strict Clippy](closure-evidence-v3/sdk-final/canonical-build-v1/clippy.stderr.log)、[build](closure-evidence-v3/sdk-final/canonical-build-v1/build.stderr.log)、[verified SDK](closure-evidence-v3/sdk-final/canonical-build-v1/verified-sdk-source.json)、[resource/source结果](closure-evidence-v3/sdk-final/resources-source-results.json)：318 passed/2 ignored、strict release/all-target Clippy及五bin build均exit0；102个同树SDK包、61资源 | 执行a762/tree e902与审阅1f94同树不同commit；clean source+locked/offline+existing target cache，不是空cache/新OS cleanroom或整个Hepta workspace；原build仍runtime_qualified=false |
| **E13** | 原[v1 receipt](closure-evidence-v3/sdk-final/orca-window-v1/receipt.json)、[v2 wrapper](closure-evidence-v3/sdk-final/orca-window-v2.wrapper.json)、[v3 receipt](closure-evidence-v3/sdk-final/orca-window-v3/receipt.json)、[provenance](closure-evidence-v3/sdk-final/orca-window-v3/provenance.json)、[EditableText七项](closure-evidence-v3/sdk-final/orca-window-v3/editable-text-receipt.json)、[真实IBus失败](closure-evidence-v3/sdk-final/orca-window-v3/ibus-receipt.json)、[Orca完整log](closure-evidence-v3/sdk-final/orca-window-v3/orca-debug.log)：v3方法七项通过、整体失败 | 原IBus preedit guard失败；unstripped e315c6和匹配资源，非安装stripped080ad7；不授予物理IME/Wayland/完整Orca/生产send，两个observer事件不是Orca消费证据 |
| **E14** | [最终 Python 汇总](final-python-gates/summary.json)、[命令与日志](final-python-gates/README.md)：发布 `0a268d89` / tree `d7c0d61`；spec普通/`-O`各53通过，source mutation普通/`-O`各10通过，source verifier passed，Android24通过，product65通过；7个接受的gate均exit0、0失败/错误/skip | 215是6条unittest命令的执行次数，含普通/`-O`重复，另1条是source verifier；sandbox首轮63 passed/2 errors原日志保留，相同未修改65项在已授权本地主机执行后全通过；不授予生产或设备资格 |
| **E15** | [Root material回执](closure-evidence-v2/material-root-01/root-material-result.json)、[原测试日志](closure-evidence-v2/material-root-01/material-original-and-distinct-attempts.log)、[构建输入](closure-evidence-v2/material-build-results.json)：独立Hepta源码c8211eb9/tree c8e707a3，主机UID0原fixture4/4 passed、396未选；原测试ELF SHA-256 `c69109d25079a88819db714b4404e651810a0270e4159ff3e33cc8b336634fa8` | 回执明确native_qualification=false、power_loss_qualification=false；不是产品Hepta22e87或新内核组合资格。原[preflight](closure-evidence-v2/kernel-final-preflight.json)及其[fix失败日志](closure-evidence-v2/kernel-final-fix.log)保留；当前7ecc host实测另见E18/E19，完整native/static终态另见E23/E24 |
| **E16** | [pack receipt](closure-evidence-v3/sdk-final/product-package-v1/receipt.json)、[host-package](closure-evidence-v3/sdk-final/product-package-v1/host-package.log)、[product-package](closure-evidence-v3/sdk-final/product-package-v1/product-package.log)、[实际manifest](closure-evidence-v3/sdk-final/product-package-v1/extracted/trillionnium-desktop/manifest.json)：rustfmt/host-package/pack均exit0，B为72文件/61资源 | manifest绑定a762/22e87；大型archive仅保留原回执摘要，本地没有重新读取其全部字节；effects_authorized=false、installed_ui_executed=false |
| **E17** | [真实安装result](closure-evidence-v3/trusted-install/upgrade-rollback-final-01/result.json)、[原plan](closure-evidence-v3/trusted-install/upgrade-rollback-final-01/reviewed-plan.json)、[A inventory](closure-evidence-v3/trusted-install/upgrade-rollback-final-01/A-immutable-inventory.json)、[B inventory](closure-evidence-v3/trusted-install/upgrade-rollback-final-01/B-immutable-inventory.json)：A1/B2/A3/B4、两项实际flock拒绝、immutable文件保持通过 | 持锁者为验收driver，未启动original Root或安装UI；生产claim/profile/authority没有创建，原活进程隔离仍须实际owner输入 |
| **E18** | [原八库失败](closure-evidence-v3/kernel-final-tests.json)、[全log](closure-evidence-v3/kernel-final-libs.log)、[七项隔离失败](closure-evidence-v3/native-failed-cases-isolated-01/result.json)、[durable诊断](closure-evidence-v3/durable-file-latency-diagnostic-01.json)、[durable七项result](closure-evidence-v3/native-failed-cases-durable-data-02/result.json)、[原log](closure-evidence-v3/native-failed-cases-durable-data-02/seven-original-cases.stderr.log)：首轮1059/4fail/3timeout/99skip；durable七项7pass/979skip | 同7ecc源码，原期限和八个测试ELF未改，仅换普通durable ext4 fixture环境；定向通过不替代全suite，六项后续static/full-suite输入在v3中deferred |
| **E19** | [当前Root material原result](closure-evidence-v3/material-root-final-01/root-material-result.json)、[log](closure-evidence-v3/material-root-final-01/material-original-and-distinct-attempts.log)、[wrapper](closure-evidence-v3/material-root-final-01.wrapper.json)：7ecc clean source前后相同、50文件与base diff锁定，新sealed ELF12c607…，4pass/400skip，13.514秒 | 当前原fixture的新执行，不继承E15；不是durable-seven同一memory ELF，不授予native或power-loss资格 |
| **E20** | [v3 inventory](closure-evidence-v3/inventory.json)、[原collection plan](closure-evidence-v3/collection-plan.json)、[跨receipt绑定](evidence-binding.json)：71原文件+2清单，字节/SHA与输入archive全部核对一致，原metadata只存一份 | 6个deferred未读取，`final_evidence_scope_complete=false`；收集exit0不表示test pass或后续native/static终态 |
| **E21** | [v4原receipt](closure-evidence-v4/sdk-final/orca-window-v4/receipt.json)、[真实IBus失败](closure-evidence-v4/sdk-final/orca-window-v4/ibus-receipt.json)、[X11事件](closure-evidence-v4/sdk-final/orca-window-v4/x11-focus-events.ndjson)、[AT-SPI事件](closure-evidence-v4/sdk-final/orca-window-v4/atspi-events.ndjson)、[独立readback](closure-evidence-v4/sdk-final/orca-window-v4/ibus-failure-readback.json)、[完整Orca log](closure-evidence-v4/sdk-final/orca-window-v4/orca-debug.log)、[窗口截图](closure-evidence-v4/sdk-final/orca-window-v4/ibus-failure-window.png)、[全display截图](closure-evidence-v4/sdk-final/orca-window-v4/ibus-failure-display.png)、[21文件清单](closure-evidence-v4/orca-v4-evidence-inventory.json)：v4整体失败；已记录OS焦点均为12582916，Message焦点丢失 | 同canonical unstripped ELF，新PID2305860；有限原Orca speech/事件行为不等于consumer/human资格，原false字段保留。两类observer、独立XIM查询和只读诊断exit0不覆盖失败；未收集private Xauthority，不替代E22–E25的独立范围 |
| **E22** | [a762 unsigned执行](closure-evidence-v4-native-android/android-unsigned-a762-final/execution-receipt.json)、[build-record](closure-evidence-v4-native-android/android-unsigned-a762-final/build/build-record.json)、[source前](closure-evidence-v4-native-android/android-unsigned-a762-final/source-before.json)/[后](closure-evidence-v4-native-android/android-unsigned-a762-final/source-after.json)、[tools前](closure-evidence-v4-native-android/android-unsigned-a762-final/tools-before.json)/[后](closure-evidence-v4-native-android/android-unsigned-a762-final/tools-after.json)、[实际命令](closure-evidence-v4-native-android/android-unsigned-a762-final/logs/unsigned-build.json)、[wrapper](closure-evidence-v4-native-android/android-unsigned-a762-final.wrapper.json)：原SDK35/Manifest复用构建通过，source/tools完全一致 | 新a762实际执行；原签名证书可核对不等于持有私钥。signed/deployed均false、设备动作0、unsigned验签false；未复制或本地重新hash APK/DEX，不授予原owner/生产设备资格 |
| **E23** | [full03 result](closure-evidence-v4-native-android/native-full-libs-durable-data-03/result.json)/[完整stderr](closure-evidence-v4-native-android/native-full-libs-durable-data-03/full-eight-libs.stderr.log)、[full04 result](closure-evidence-v4-native-android/native-full-libs-durable-short-04/result.json)/[完整stderr](closure-evidence-v4-native-android/native-full-libs-durable-short-04/full-eight-libs.stderr.log)：03为1049pass/16fail/1timeout/99skip；04为1065pass/1timeout/99skip | 同7ecc及八ELF、原断言/期限；03过长harness路径失败在04消失，但容量60.006秒超时仍在，两个full步骤exit100且paired均未执行。不能继承定向7/7或Root4的通过 |
| **E24** | [static02原result](closure-evidence-v4-native-android/native-original-entry-final-02/result.json)、[build](closure-evidence-v4-native-android/native-original-entry-final-02/build.log)、[source前](closure-evidence-v4-native-android/native-original-entry-final-02/source-before.json)/[后](closure-evidence-v4-native-android/native-original-entry-final-02/source-after.json)、[readelf](closure-evidence-v4-native-android/native-original-entry-final-02/original-readelf.log)、[完整size诊断](closure-evidence-v4-native-android/native-static-size-diagnostic-01/result.json)/[sections](closure-evidence-v4-native-android/native-static-size-diagnostic-01/sections.stdout.log)：a37/7ecc原build+strip成功，13243416-byte ELF被8MiB门槛拒绝 | 原features/profile/8与16MiB门槛未改；静态文件诊断不执行原生ELF。built/packaged=true，static_profile/native role/recovery/G2均未通过；不授予新优化源码资格 |
| **E25** | [新inventory](closure-evidence-v4-native-android/inventory.json)、[原plan](closure-evidence-v4-native-android/collection-plan.json)、[绑定](evidence-binding.json)：58原文件16706753 bytes，另2个not_executed；加两清单为60实际文件，tar/member/字节/SHA全部核对 | 固定两source roots，collector实际UID1000；未改来源权限、不收ELF/APK/签名材料、不重复v3/Orca-v4。required收集完成不表示paired或最终资格完成，final_evidence_scope_complete=false |

## 6. 最终接收条件与仍需原系统提供的输入

UI v3、Notes v5、Python gates与canonical SDK/资源/实际包/行政安装事务均已按各自原回执归档核对。canonical使用clean source与既有target cache，UI workspace release tests/strict Clippy/五bin build通过；Makepad v3/v4则实际失败于真实IBus preedit，方法检查通过及v4的有限Orca行为不能覆盖这个失败。v4进一步保留X11与Message焦点分歧的原始事件和readback。接续工作须修复并重新运行最终source/ELF/资源匹配的原窗口gate，并继续记录缺失的原生产上下文；不得把`compiled=true`或行政安装成功解释为`runtime_qualified=true`。独立native的durable七项和当前Root4通过保留范围；完整八库04仍有一项容量timeout，static02原build/packaging成功后8MiB admission拒绝，两个原paired步骤未执行。[E23][E24] Android的新a762 unsigned build和原Manifest保留已通过，仍未签名或部署，也未执行设备动作。[E22] 后续IME及native优化源码等待各自实际回执，不承接本批结果。

原Root/AppServer生产验收需要原系统已经保留的daemon pidfd/registration、Root0600 human/session/profile、实际UI认领、同一原AppServer route，以及真实模型/操作授权。原Notes效果验收另需原issuer、protected clock/current frontier、目的专属FinalUse、原writer持久恢复身份和终态回执。缺失输入当前维持blocked，不启动新Root、新signer、新thread或新ledger冒充恢复。

Pocket4验收已经具备本批原Manifest保留和unsigned编译记录；仍需要原authenticated peer及同一live runtime/source verifier、原signer授权签名、已部署stricthelper/APK/签名及Droidloom/cell/editor的实际测量，以及同一原owner的目的专属FinalUse。满足后才可在选定无害editor上做一次真实中文set-text、独立readback和失联/撤权/过期/切窗/重启等原身份故障验收；本轮实现不承诺通用移动控制。

独立F1/G2、资源恢复和原生图形/硬件继续按各自原profile与完整测试inventory执行。该线的真实ELF admission、guest运行、原owner、设备和持久性证据单独决定其状态；Linux host窗口通过不会使Asterinas原生桌面、Android-on-Asterinas或实体手机自动具备资格。

**阶段判定：E10/E11/E12/E14/E16/E17/E19/E22已按各自明确范围通过并归档；E13与E21整体仍失败，E18保留原失败与限定durable复验，E23完整suite仍timeout、E24静态准入仍拒绝；E25完整收集了required原文件，但两个paired步骤未执行。P0-2/P0-3/P0-4的原生产链和P1-2仍blocked，直到原系统提供原owner输入并完成实际验收。没有空缓存/全新OS cleanroom、完整物理IME/Orca或原生guest资格的扩张声明。**
