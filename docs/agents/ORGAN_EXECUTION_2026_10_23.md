# Organ 全量施工：2026-10-23 执行与阻塞记录

本页记录本次实际变更和验收边界。它不是发布资格，也不把未完成检查、测试 issuer、旧源码运行或设备枚举改记为完整产品通过。主线、候选代码、执行结果及尚缺输入分别绑定到下面的提交和原记录。

## 已闭合的主线增量

[#245](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/245) 于 **2026-10-23 05:42:28 UTC** 合入 `39c1d84ebf854958f5829c0118b0c8b92a6b4926`。合并树 `87bc4e4d72697a7583fb0afafe4db4b41582941c` 与验证提交 `c5c88794bf227b1d862b2f914b02809a0090e854` 完全一致，最终七项 GitHub checks 均成功。

原 A06 产物中的 `object_ownership_survives_inode_and_view_reconstruction` 实际通过；aster-core 为 275 passed、0 failed、0 filtered、0 soft-skipped。OSTD 报告 222 passed，其中 3 项 VMX soft-skip，实际执行下界为 219。原 G1-d 记录验证第 17 个 retained TID 被 `EAGAIN` 拒绝、15 个 zombie 加 parent 仍计 16、`WNOWAIT` 不退款、真正 reap 后可重用，以及四项 pids 控制写入被 `EACCES` 拒绝。原有 manager/recovery 仍有独立的进程创建空间。

最终 old-root 负控在不改变 probe 的情况下出现两个明确权限失败，且没有 timeout；它不是此前 thread/zombie/SysTree 语义变异的最终提交重跑。独立核验原件保存在 [A06 review](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/b2d20015f4d4fbc4db3754359ab1ddbf70e5d6ab/results/integration/2026-10-23-native-runtime/review-inputs/pr245-a06-independent-review.json) 和 [G1-d review](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/b2d20015f4d4fbc4db3754359ab1ddbf70e5d6ab/results/integration/2026-10-23-native-runtime/review-inputs/pr245-g1d-independent-review.json)。这项完成只覆盖 retained-task 与 SysTree owner 修复。

[#249](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/249) 于 **2026-10-23 09:06:23 UTC** 合入 `38227d33fd3ed668f0424bc153e0d3d811731597`；合并树 `26c89107d5b7da3e9b4dd8522dfe86546327bcf6` 与最终验证 head `cfe28e3efb5e025d58a9d663d1dd6a681c224892` 完全相同。四项真实 CI（exact-kernel-ktest、trusted-initial-control、trusted-initial-observe、host-evidence）全部通过，G1-d 负控也实际完成。最终树与原 native product `e0b5caa5100c7f9fb4b3219a4359642e5e791448` 的全部 kernel/build-wrapper 文件相同；与通过 19 项边界检查的 probe `8f2ea44317a9f5205fe09cc1f2fb87021cd18bfe` 的所有非证据文件相同。[独立合入核验](../../results/integration/2026-10-23-exec-budget-review/README.md) 保存完整 CI 日志、差异表及合并回读。它关闭 argv/envp 字符串、指针槽、execveat 与 shebang 替换的 aggregate exec-copy admission；不关闭总 memory、全局恢复 reserve 或 watchdog。

## 用户优先级与完成条件

| 优先级 / 工作 | 本次已落实的源码与证据 | 尚未闭合的完成条件 |
| --- | --- | --- |
| P0：#245 | 上述最终提交已同树合入；七项 checks、完整 core、严格 guest 正反记录已复核。 | 该修复增量已闭合；不转授完整资源隔离。 |
| P0：生产 Hepta / Notes | [Hepta #3383](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3383) 接入原 worker / issuer provider；[#3398](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3398) 已实现原 recovered writer、保护时钟、FinalUse 与原 Notes handoff 的生产组合候选。provider 7 项真实 socket 回归、authority 5 项独立组件回归及各自 Clippy 已执行。 | 原 Agentd 包的 7 条 factory + 5 条 Notes 测试尚未执行；独立生产 issuer operation / 部署、七项原输入、完整授权/回读/撤销/断连/重启验收仍缺。 |
| P0：聊天进入原 Hepta | [#255](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/255) 的原 Session 64 项、transport 52 项及对应 Clippy 已通过；[Hepta #3444](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3444) 在原 CognitiveStore/writer 中实现 durable sender，原 memory 库最终 322 passed、8 skipped；[Desktop #256](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/256) 已装配具体 original-owner host，最终 14 项真实原 owner/socket 测试通过，并有 3 项 ACK 负控失败和恢复后 14 项通过。 | 原 Agentd bridge/factory/Notes/issuer 的 owning-package CI、生产签名 Objective、受保护 current-cut 服务、原 RunCancel 和产品 UI command 仍需完成；产品 Send 保持关闭。原 sender 和具体 host 不再记为缺代码。 |
| P0：F1 daemon / 最终 exec / G2 | [#253](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/253) 新增 x86_64 native CI；复用原 FleetRegistry / Supervisor / UnixProcessDriver，固定真实 A06 kernel 和三份原 userspace ELF。38 项 host 测试、11 项旧拒绝测试、实际 artifact 导入已通过。 | 固定 c5 kernel 存在 [#254](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/254) 已定位的 UDP stop 路径风险。需修复 kernel 的新 ordinary A06 资格与 source/hash 绑定，再实际构建、运行原生命周期；crash/restart、writer-lock、最终 exec 可信 role 和 G2 持久退役仍缺。 |
| P0：总资源与自主恢复 | #245 retained tasks 与 #249 aggregate exec-copy 均已同树验收合入主线；[#252](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/252) 是 64 MiB sealed-family 用户数据帧候选，带自身原生证据。其 G1-d credential 前像漂移已在 `610181d5c3a8fd615ebab6e379de5d99e1d686f8` 修正；真实源码的 host 正常/`-O` 各 26 项通过，旧 runner 各有 1 error、1 fail。 | #252 修复后新的原生正向与 old-root 负控尚排队；host 变异回归不能替代 guest。kernel heap/slab、page tables、网络元数据、全局 reserve、完整 memory 控制、可信暂停、watchdog 和公共恢复仍缺。 |
| P1：Makepad / Robrix | [#258](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/258) 已把原 Hepta ChatWorkspace / Robrix presenter 接入既有 Desktop draft 与 Session/broker；原 core/presenter/Desktop core 共 129 项、共享 Shell 87 项和默认 Shell 82 项全部执行通过，含真实 CJK 字体 raster。 | 该候选的 renderer 仍为 eframe/egui。原 Makepad App 的一次性状态注入与实际 renderer 接合正在实现，尚未编译/运行；真实 IME、触摸、辅助技术、关闭生命周期与安装包仍需分别验收。 |
| P1：Asterinas app-server / 桌面 | 原内核与 host UI 有各自构建/运行记录。 | 原 app-server、真实任务与应用生命周期、实际 guest 图形和输入；host Weston 不是 Asterinas 桌面通过。 |
| P1：固定 x86 / 手机目标 | 既有硬件 inventory；[#250](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/250) 为原 Droidloom cell 的只读身份 adapter 候选。 | 指定实际设备上的受权效果、独立回读、重启/恢复。Android x86 cell 不是物理手机或 ARM/BSP 验收。 |
| 持续：文档与状态 | [#247](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/247) 补七个就近模块手册、九个 workflow / 两个入口的 README gate 修复和本执行记录；[原 Objective owner 设计](OBJECTIVE_SENDER_OWNER_NEXT.md) 的后续实现已分别绑定 #3444 与 #256；另有 #254 独立证据核验。旧 runner 的新回归失败，新实现的针对性回归通过。 | 新组合的完整 CI；设计文档本身不能替代实现与执行。每次合入后按真实 source pair 更新下表及当前 blocker，不复制旧通过数字。 |

本次记录时，尚未取得上述新候选的完整 CI 通过结果。排队没有执行日志时，仅记录 queued/pending；不推断编译失败，也不授予完成资格。

截至 **10:16 UTC** 的再次回读，#252 的五项、#258 的三项以及 #3444 的新 owning-package job 均仍 queued，未产生新的执行结论；#3444 的旧 branch-guard job 为 skipped。排队原因尚未取得证据，不猜测为编译、权限或额度故障，也不通过 rerun queued job 将其冒称已经重新执行。

## 原系统生产装配的七项输入

七项输入沿 [原实施契约](ORGAN_IMPLEMENTATION_NEXT.md) 保持原 owner，不由 UI、测试 fixture 或 convenience constructor 自行补齐。

| 输入 | 原所有者 / 约束 | 缺失时的行为 |
| --- | --- | --- |
| Grant provider / issuer | 独立 issuer；已认证私有描述符与固定 peer UID/PID；明确支持 `runtime.agentd.production_operation`。 | 不激活效果；不得用测试签名者替代，不自动重连/重派不确定请求。 |
| Clock | 原保护时钟；grant 有效期使用原验证路径。 | 拒绝生产装配或 FinalUse。 |
| Frontier | 外部 durable CAS frontier；防止本地回滚后复用权限。 | 不创建本地替代 frontier，不将内存计数当持久单调状态。 |
| Issuer keyring | 原受信部署提供的 keyring，使用原 production 构造器。 | 不生成替代 key，不把收到的未验证 key 当 trust root。 |
| Revocation head | 已认证且足够新鲜的原撤销状态。 | provider 的未签名 reply 不能更新 trusted revocation head。 |
| Current-cut | 独立保留、认证且仍 current 的原 `CognitiveRecoveryAnchor`，绑定 profile / owner / schema_digest / state_digest；它与 authority lease 是不同输入。 | 不从可疑或回滚后的 store 自行捕获 witness 再称为可信 current-cut；旧、错误 owner 或 digest 不匹配时拒绝恢复。 |
| Recovered writer | 原 exact-cut 恢复的唯一 CognitiveStore / outbox / ProductionDurableWriter 与原 target；同时要求原 authority lease、opaque token、live verifier 及匹配的 owner / lease id / generation。 | 不创建第二份任务或 effect ledger；不删除恢复痕迹来假装事务回滚，不以一个有效 lease 替代独立 current-cut。 |

[#3383 的最终源码证据](https://github.com/TrillionniumFoundation/hepta-private-ci/tree/507b46749dea0cece820c4997208f20464362d75/docs/modules/runtime.agentd/evidence/2026-10-23-final-use-issuer) 使用真实私有 socket 和原 contracts 源码，但 isolated harness 有 32 项 registry lock 条目不同于原 workspace；它不能替代 Agentd owning-package 的 `--locked` CI。worker 的 permit 随同步工作保留，取消等待者不会提前释放容量；I/O 总 deadline 从 provider 实际执行时开始，不包含 Tokio blocking pool 排队时间。

Notes [#248](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/248) 与 Hepta [#3366](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3366) 的原记录覆盖同一存活应用、保留私有 recovery descriptor、丢回复后的查询及原 SQLite Committed 后 ACK。生产 issuer、应用/Agentd 进程重启后的描述符重新获得和真实应用内容持久化分别继续验收。

## 新增接合源码与执行范围

| 候选 | 固定 head / tree | 已执行与尚未执行 |
| --- | --- | --- |
| Desktop #255 | head `2c88b9d3929ec64e7a2bb20ee2f869d87bea7792`；tree `3ed98b4c408bc681be8d12d7e3a565aeda518dbf` | 最终 Rust 1.88 的原 Session 64 项测试和 Clippy `-D warnings` 通过，包含最后的原 owner `mark_send_started` 门禁及旧顺序失败对照。同一未修改 transport 的 52 项测试和 Clippy 在 Rust 1.88/1.95 通过。上述旧 offline 缺缓存记录保留为历史，已不是当前执行 blocker。最终 11 个发布文件已逐 Git blob 和内容回读。 |
| Hepta #3398 | head `a5bf15516e744fd86d6564bda5a60e8b942a2eb6`；tree `0c8a9a833bc20fe920c7c688f62f7905eed2bf05`；源码与 `16418ddc3416a38a122b883cee46e2d3583cbd41` 相同，新增 22 个执行证据文件。 | 5 项 protected-authority 组件测试和 Clippy 通过；原 193-member workspace / 9111 Git blobs 已完整还原，`Cargo.lock` 未修改。原包 7 条 factory + 5 条 Notes 测试实际启动构建，但尚未执行测试：系统 OpenSSL 发现错误修正后，后续尝试由 1.5 GiB 内存 / 256 MiB 空间门禁停止。缺 `aws-auth` 和 offline 缓存仅是早期历史。完整原始执行 JSON 的 20 个片段可按索引无损拼回，不是抽样日志。 |
| Hepta #3444 原 owner | 已执行的 memory / Desktop host 依赖 pin `db91f9ec316ba1472e7adf97f8415949de012469`；tree `81c03af04be56659d3eb4da71bf61aeac34c949f`。基础源码 `4869044893f114bcb1d7235830c7313638df8254`，checked append `7f86518d7f179c068d60c6cf26d41710d3540579`，ACK 恢复分别保留独立提交。后续 CI `5a3ffeb70afaa56c4390551f740073b68ec539e3`；修正 Agentd bridge 的当前 head `45f1e7d471c9e0720ce2c149da92629f785a01a4` / tree `62e0c4a173763426a0a6d4e5c3d1fb8df7ce653d`。 | 原完整 workspace / 原锁、Rust 1.95、原 `just test` / `dev-small` / memory `--lib`：三个阶段分别 317、319、322 passed，各 8 skipped；该 memory 源码的 `just fmt` 和 scoped `just fix` 退出 0，源未变。Clippy 仍有 28 条 lib-test warnings、2 条 lib duplicate warnings，不能称 `-D warnings`。bridge 两处原本引用未声明的 legacy `objective_ingress`，现改用现有 active `objective_runtime::objective_payload` 并传原 spawn_generation，函数体和断言未改。该 bridge 修正只有实际 Rust 1.88 rustfmt parse/等字节检查，尚未由原 Agentd 编译/执行，不能转用 memory 322 的通过。92 个完整原始证据、10 份 CI 静态证据及 3 份 bridge 修正证据已发布，远端全部 9,251 叶节点核对一致。 |
| Desktop #256 具体 host | source `bf0a0a0a582d7c93c191488e762c12bd6d75561a`；source tree `ad26a0b6396a02ad5b5ff47e3f9fa7ed47da1c61`；带证据 head `8aab02dced7590516d62808c506e491c6eeb453d` / tree `8ba7619d344b1df46bc0115df1da2d84a73e766f`。基于 #255，所有原 Hepta Git 依赖固定 db91。 | 真实 Git 图 628 packages、30 个原 Hepta packages；前后完整验证 9,145 个原 Git files 与 1,239 tree objects。最终 host 14 passed、0 ignored/filtered，fmt 与 Clippy `-D warnings` 退出 0。单处恢复调用退回 generic snapshot 后 3 项预期 ACK assertion failed（Cargo 101，11 filtered），精确恢复后 14 项全过。69 个完整 raw 成员（其中 62 validation）无损归档；远端全部 7,863 个叶节点匹配。 |
| Desktop #258 共享原 presenter | source `0618dc8154e8b78cb91c5aa5558c597232d68023` / tree `306a8f134adb59ebe1bfbb37b69a6ab329b276de`；带证据 head `2f8e73df3d626c8a2dfde07f188ac0ad80781c35` / tree `af16a3df27554ada0f28dc8e40e63dc60f3daf55`。原 Hepta UI pin `56630b12b8a4c69fff2c47b95b36d88a7389c39f`。 | 26 个源码文件和 12 个证据文件已发布；原 Hepta core 64 + Robrix presenter 23 + Desktop core 42 = 129；共享 Shell 87、默认 Shell 82，各自最终含 CJK 且 0 ignored/filtered。实际 fmt 与默认/feature/observer Clippy `-D warnings` 通过。此基线的 Session 45 / transport 51 不能换称 #255 的 64 / 52。52 项 wire corpus 中 51 项值及其他输出字节严格相同，只允许一项 MAX f32 等值指数写法；不是整个浮点输入域资格。269 个完整 raw 成员无损归档，全部 7,762 个远端叶节点核对。 |
| Desktop #254 独立审查 | 审查 head `18d400a2c112c4bd3b7d69209729640378e7db71`；实际诊断 runtime `c8f0c88ecb640117686ff05f850a73e60688eac7` | 76 个文本证据逐 size/SHA256、89 个 Git text blob、3 段 nonce/hex serial 与原 guest 文件已核对。原 Linux 与 native UDP 6 cases / 43 checks 对齐；9 阶段 lifecycle 是 diagnostic-only。新 portable A06 runner 的当前 CI 尚未运行。 |

#255 的 Session 接合只调用原 owner port。它在任何 transport 结果之后都不重新授予发送许可，未知恢复路径不包含 transport；原 history 按同一个 AgentId 查询并保留原始 observation。发送前本地取消可以丢弃许可；发送后必须走原 run owner 的取消流程，不能据此声明任务已取消。原 sender 的持久域、永久发送 fence、跨进程恢复和 current-cut ACK 接口已进入独立原 owner 候选；其真实执行范围与具体 host 接合不能由 Session 的 64 项测试代替。[最初设计约束](OBJECTIVE_SENDER_OWNER_NEXT.md) 保留为历史设计输入，不能单独证明实现或生产资格。

#3444 的 migration 0017 在原库中新增 sender 域与永久 duplicate fence；`retain_observation_checked` 在同一原 `BEGIN IMMEDIATE` 中完成状态核对与 append，避免两个独立连接先各自核对再提交冲突 publication。`snapshot_acknowledged` 在原写事务中读取 snapshot、取得完整 current-cut、等待独立 checkpoint ACK 并执行最终 live check；仅有本地已提交行不能被恢复 facade 提升成 confirmed。两连接真实竞争、ACK 拒绝/timeout、本地取消恢复和锁在 ACK 期间保持均有原 memory 测试；generic observation API 仍允许 opaque observation，可信 publication 写入必须使用 checked invariant。

#256 复用原 Session/transport/history 和唯一 writer；不创建 runtime、worker、scheduler、ledger 或 issuer。它从原 embedding 注入已有 multi-thread Tokio handle，原 `mark_send_started` 在 I/O 前消耗机会。恢复不授予 Send/Cancel。三项负控均在首个 REFUSE 迭代失败，HOLD timeout 由最终绿测覆盖，不能说负控也执行了 HOLD。测试使用真实原 store/owner 与私有 UDS，但 verifier/checkpoint/签名形状输入是测试 fixture；facade drop/recovery 不是 host 进程崩溃或掉电验证。独立 current-cut 服务和可信旧 schema 升级路径仍缺；同步 callback 与 checkpoint poll 必须有界、非阻塞，Tokio timeout 不能抢占阻塞回调。完整原件见 [host 证据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/8aab02dced7590516d62808c506e491c6eeb453d/services/hepta-session-host/evidence/2026-10-23-original-owner)。

原 HOS2 `owner-candidate` 工作流限制旧 head branch，因此 #3444 该 job 实际为 skipped，不能当作原包验证。新的 [source-head owning-package gate](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/5a3ffeb70afaa56c4390551f740073b68ec539e3/.github/workflows/hepta-objective-owner.yml) 保留原完整 workspace/锁、Rust 1.95 和原 `just` recipes，串行执行完整 memory/Agentd libraries，检查 checked/ACK、3 bridge、7 factory、5 Notes、5 authority、7 issuer 的实际新鲜 JUnit，并逐文件核源码/锁未变。它不修改原分支 guard 或授予生产输入。YAML、12 Bash、4 Python 静态语法检查实过；截至 09:22 UTC，`45f1` 的[当前真实 job](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39929829763/job/120335071214) 为 queued，尚无执行步骤或通过。原 nextest 一次 retry 保留，scoped `just fix` 的 exit 0 不是零 warning。

#3398 使用相同原 protected clock 覆盖恢复与运行期，并在全部 metadata callback / await 之后、两个配置 handle 连续赋值之前执行最后一次同步验证。Notes 复用原 `with_notes_from_session`；只有安装成功后才返回 identity。原 `attached` ACK 可以先于最后授权拒绝发生，因此 ACK 只证明 descriptor handoff；失败时返回 `Err`、配置为空、effect FD 关闭，不授予 installed/runtime/effect 完成资格。[最终原始测试与源码身份](https://github.com/TrillionniumFoundation/hepta-private-ci/tree/a5bf15516e744fd86d6564bda5a60e8b942a2eb6/docs/modules/runtime.agentd/evidence/2026-10-23-production-composition) 保留了隔离 harness、原包失败阶段与实际命令。

#254 的 [独立审查原件](../../results/integration/2026-10-23-udp-review/review.json) 证明：当前修复路径的六个 UDP 文件与 c8 runtime 相同，#253 固定 c5 的同六个文件则与未修复 b824 baseline 相同。在相同 resolver 条件下这是已知 stop 风险；没有冒称已经运行 #253 clean 原 fixture 并观察到失败。诊断使用的二进制没有补回原 build exit receipt，`original_agentd_lifecycle_qualified`、production authority、HOS2 control、power-loss recovery 均为 false。76 个归档没有独立完整 A06 QueryAbi 资格收据，不能把它作为 #253 新 kernel 导入凭据。必须取得修复源码的 ordinary A06 build / boot / QueryAbi / hash 记录，再更新 pin 并运行 clean 原 6d fixture。

## 每个模块的开发、技术与执行绑定

下表使用现有模块所有者，不引入平行实现。开发入口含构建/运行/测试命令；技术入口规定输入输出、权限、状态、并发或持久性。固定历史执行只证明其记录的 profile。

| 模块 | 源码 / 开发入口 | 技术与 profile | 本轮执行 / 当前 blocker |
| --- | --- | --- | --- |
| A00 集成 | `support/release`；[跨仓 source profile](ORGAN_RELEASE_PROFILE.md) | [架构](../ARCHITECTURE.md)、[原实施顺序](ORGAN_IMPLEMENTATION_NEXT.md) | #247 文档/source-gate 迁移；各候选尚未组成新的已验收整树。 |
| A01 源码 / 启动 | `kernel/asterinas`、`support/build`；[构建](../../support/build/README.md) | 固定 upstream / nightly；[完整 ktest](../../support/build/ktest/README.md) | #245 A06 已核验；不能把 kernel ktest 当原 daemon 或桌面执行。 |
| A02 HOS2 codec | `libs/os-abi`；[模块手册](../../libs/os-abi/README.md) | [NATIVE_ABI](../NATIVE_ABI.md) | ordinary 仍 QueryAbi-only；G1-c/G1-d 的效果仅属于各自 profile。 |
| A03 Control owner | `libs/os-control`；[验证入口](../../tests/control/VALIDATION.md) | [API_CONTRACT](../../libs/os-control/API_CONTRACT.md) | 原 D / 终态 / 退役 owner；Hepta durable ACK 与 native G2 仍需真实接合。 |
| A04 Linux / ELF | `compat/linux`、workloads；[开发手册](../../tests/workloads/linux/README.md) | [Linux gaps](../../compat/linux/GAPS.md)、[SQLite guest restart](../../tests/workloads/linux/SQLITE_GUEST_RESTART.md) | #253 原始动态 ELF guest CI；#249 exec-copy 已经四项检查通过、同树合入。 |
| A05 映像 / 内核控制 | `device/misc/hepta_control.rs`、process loader；[handoff](handoffs/A05_KERNEL_CONTROL.md) | [G1-c](G1C_TRUSTED_OBSERVE_PROFILE.md)、[G1-d](G1D_TRUSTED_CONTROL_PROFILE.md) | 最终 exec 身份、动态 Agentd 可信 role 与生产 grant 未闭合。 |
| A06 隔离 / 恢复 | 原 cgroup / CPU / VM 对象；[CPU usage](../../tests/organ_backend/CPU_USAGE_G1B.md) | [安全与恢复](../SECURITY_AND_RECOVERY.md) | #245/#249 已合；#252 窄域候选的负控 runner 已修复并完成正常/`-O` host 正反回归，新 native 正负检查排队；完整总资源/watchdog/公共恢复仍开放。 |
| A07 Hepta 接合 | `services/hepta-os` 与 #256 的 `services/hepta-session-host`；[开发](../../services/hepta-os/README.md)、[运行](../../services/hepta-os/RUN.md)、[具体 host 手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/bf0a0a0a582d7c93c191488e762c12bd6d75561a/services/hepta-session-host/README.md) | [Objective transport](../../services/hepta-os/OBJECTIVE_TRANSPORT.md)、[history](../../services/hepta-os/OBJECTIVE_HISTORY.md) | #3383/#3398/#255/#3444/#256 分别绑定原 issuer、生产组合、Session、CognitiveStore sender 与具体 host；memory 322 与 host 14 分别通过。原 issuer 部署、受保护 current-cut 服务、真实七项输入和原 RunCancel 仍缺；原 Agentd 组合/bridge owning-package 尚未执行。 |
| A08 Android | `support/android`、`compat/android`；[开发](../../support/android/README.md) | [接口](../../compat/android/INTERFACES.md)、[Android 边界](../ANDROID_COMPATIBILITY.md) | #250 只读 cell 候选；真实 effect owner、物理手机、ARM/BSP 未取得。 |
| A09 硬件 / VMM | `support/vmm`、`tests/hardware`；[运行](../../tests/hardware/RUN.md) | [硬件决定](../../support/hardware/DECISION.md)、[VMM gates](../../support/vmm/GATES.md) | 真实平台访问与 device-specific IOMMU / reset / recovery 仍需实现和执行。 |
| A10 UI / Session / Notes | [workspace](../../ui/README.md)、[core](../../ui/core/README.md)、[Session](../../ui/session/README.md)、[Shell](../../ui/shell/README.md)、[app-window](../../ui/app-window/README.md)、[broker](../../ui/broker/README.md) | [UI contracts](../../support/ui/INTEGRATION_CONTRACTS.md)、[Notes](../../support/ui/NOTES_ORGAN.md)、[UI 技术](../DESKTOP_UX.md) | #251 纯 Rust policy 13 tests；#255 Session 64 / transport 52；#258 原共享呈现 core 129、共享 Shell 87、默认 Shell 82（含 CJK）。各数字绑定不同 source/profile。Makepad renderer 接合正在实现，尚无实际窗口；辅助技术和 Asterinas 图形仍待完成。 |

## 并行收敛分支与新增执行链缺口

独立发现的 [Desktop #257](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/257) 固定 head `6322f403729af5f221b00cd29d84d6425b6cff8e`，已包含 #247 的旧文档/source-gate、#253、#254，并新增 Session 500 ms 连接总期限及原 ordinary kernel 从源码 build / boot / QueryAbi 的准备路径。16 个提交和 159 个变更文件清单已读取；它没有自动包含后来合入的 #249，也没有包含 #255/#256/#258。Session deadline 与 #255 owner-before-I/O 必须同时保留；不能用该分支报告的 Session 50 项替代 #255 的 64 项或新组合整树验证。

后续只读回读已看到 #257 继续推进到 `ce8378b71c426e6f5e0227b65624895cb81212cd` / tree `8fe94570ea0ad5d63c44c6c02e5872fa532abcca`，包含 live read-only remount 的 fail-closed 候选；新的 workflow source pair 已改为 Desktop `7d8906ef9fbb5f3af4e6bb0843b79ac666394833` / Hepta `b3d3f2d4b01f123d7ac17575c27fb54d00094f7f`，并把 kernel target 移到证据目录之外。旧 6322 审查不等于这些新源码通过，也不能把先前只读 syscall 的旧通过数字授予新 remount 策略。

[#259](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/259) 是基于 ce837 的单 workflow 修正：source `c120d6c92d9de4b2bfb96bc97512c066953f565d`，证据 head `0f0d9402fa7da409dfddfa7ce4041c08a04af5ac` / tree `59b94cd30018e56b06174c7ad27859b73c503b1e`。把既有 Rustup proxy bootstrap 移到两次 toolchain install 之前，原 source pin、profile、build/guest 命令不变。候选原样 stanza 在真实官方 Rustup/既有 1.95 上执行：sanitized PATH 下 rustc/cargo/rustup 三个查询先各 exit 127，bootstrap 后各 exit 0；8 Bash、YAML 与内嵌 Python 静态检查通过。没有实际重现 fresh-install 失败，也没有执行下载、kernel 或 guest。完整 22 成员原件与全部 8,160 远端叶节点回读一致，native/F1/G2 仍需原 workflow 实跑。

对应 [Hepta #3452](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3452) 固定 `0689cd115e92e6c01f982e1e1987bf945e0c2719`，原 PR 明确将本轮 Notes recovery / issuer / production-composition 栈留作独立审查；它不能自动继承 #3383/#3398/#3444 的实现或执行证据。其原 owning-package 执行仍有 timing failures 报告；这里没有自行把它们改写为通过。#257 的新的 native source pair 固定 Desktop `2da18c78cedc831b88d5e8e28e653b58f001cf20` / Hepta `0689cd11`，本次回读的 [原 native job](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39928169346/job/120329584292) 仍 queued，无步骤或执行日志。

原 `db91` 执行桥还有两项具体源码缺口。`hepta-infer-worker` 的 `--generation` 进入 `NativeWorkerConfig.generation` 并用于 Agentd spawn 鉴权；原 state 的 Running generation 是 spawn + 1，Objective runtime 也使用该值。然而 `run_intelligence` 在 `run_mark_dispatched` 后把原任务 receipt generation 与 spawn 比较，可能在真正 `turn/start` 前失败关闭。其次，原 `RunCancel` 更新进程内 coordinator，而 worker 的 observe loop 尚未消费外部同任务的 Cancelling；现有本地取消 token 与 `TurnInterrupt` 路径不能证明外部取消已停止执行。原 intelligence handoff 现有单测只核 payload digest，实体 driver fixture 走不含 intelligence 的 `.run` 分支，不能充作此链路通过。正在实施保留原完整 run binding 的修复及实际分支测试；尚未编译或执行。

取消的拒绝也不是“原 owner 确定未变更”：`cancel_run` 先核 expected revision，后执行 deadline expiry；过期的 Cancelling 可先变成 Indeterminate / revision + 1，再返回 InvalidTransition。后继接合必须保持 unknown、只读重核，不能因 request_rejected 重授发送权。跨崩溃取消还缺原持久 typed cancel 域和重放阻断；UI 的显示用 RunObservation 不包含完整 fence/context，不能用于制造取消 authority 或写入终态。

## Makepad 统一的实现约束

Hepta 候选的 `apps/hepta-control-ui/rust/robrix-ui/src/presentation.rs` 已从同一个 `ChatWorkspace` 借用呈现；`RequestSend` 当前返回 `SendUnavailable`。`native_host` 定义观察、绘制确认与关闭协议，但原树没有 `NativeHost` 实现，`run_native` 本身没有补齐 Makepad renderer。固定 `56630b12` 的原 `App` 中 `ChatWorkspace`/`ImeRouter` 仍是 private；新片正在原 App 中增加一次采用的 ChatSource 与真实 Desktop composition，保留同一个 ImeRouter 和事件循环。#258 已共享原 presenter，但 Desktop 当前真实 renderer 仍是 eframe/egui；不能从一个草稿或窗口状态推断原任务已完成。

Desktop 的 Personal/Research/Build 三个本地 workspace 必须复用既有 Session/broker 与原状态对象。不同 `ChatWorkspace` 的 `RoomKey {epoch, local_id}` 可能相同，简单更换 borrow 会让迟到 IME event 错投；需要在原 App/ImeRouter 内建立独立 local input binding 并正确移动现有状态，不能再造第二个 App、第二份 IME router 或第二条效果通道。共享 presentation 通过不等于上述 Makepad renderer/输入装配已完成。

统一时应沿这两个真实接合点施工：原 Makepad/Robrix widgets 复用现有 presentation；Desktop Session / broker 保持应用生命周期、私有 IPC 和权限职责；新 Objective adapter 仅传递原授权请求、原身份与原 history observation。不要在 UI 再造 scheduler、签名者或 effect ledger。渲染层迁移、权限装配和辅助技术执行必须分别有原始结果；增加依赖或复制 widgets 并不完成统一。

#258 的 TextEdit 提交事务会在 paste / IME 内容被拒绝时恢复光标和 undo，并对迟到确认 Enter 保持 fence；这仍不等于真实平台输入法生命周期通过。其最终 CJK 测试使用固定 Noto Sans SC Regular（8,331,336 bytes），核 glyph coverage 和非零 raster ink；早期正常测试留下的 1 ignored 已在最终 `--include-ignored` 完整运行中执行。真实负例保留了中间 f64 数值 shim 对两个整数的 double-round 错误（原 6 项全绿、shim 4 过 2 失败），最终字段 Visitor 对 i64/u64 直接转换 f32 后 6 项全绿；默认 wire 兼容范围由固定 52 案例和严格比较器限定。完整 [269 成员原件](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/2f8e73df3d626c8a2dfde07f188ac0ad80781c35/results/integration/2026-10-23-hepta-shared-presenter) 包含此前失败与最终输出，归档 SHA256 为 `057d56a77cad0806cbcd581b7d5ad9e463d387875f51f13fc7f5e2d169cbca4e`。

新原生接合按原 Hepta source commit 先发布、Desktop 三个 UI package 再共同固定同一真实 Git rev 的顺序施工，不对旧 pin 声称有新 API。首片限定固定一个 Personal / Research / Build workspace，移动整本既有 DraftBook 与 bridge/reducer；运行期三工作区切换仍需 local input binding / IME epoch。原 Makepad 依赖固定 `337566c8b25d47f7e4fff6a202157b65bf183330` / root tree `c6e18be7754f9634492ec5251bac3e8b4f7e09b7`，实际资源、关闭与 signal 接口的 8 个原文件已逐 Git blob 核验。源码准备不能充作 Rust 1.95 编译、GUI、辅助技术或 actual device 通过。

## 更新规则

缺代码与缺执行条件分开处理。受保护 current-cut 服务、原 RunCancel 接合、完整 memory / watchdog、实际 Makepad renderer 和 Asterinas app-server 仍有实现工作；排队 runner、独立生产 issuer 与保护输入、实际 x86 / 手机访问是执行或部署条件。新 sender 已实现的存储域和已经实际通过的测试不再重复记为缺代码，完整原 Agentd 测试的容量限制也不再误记为仓库缺模块。不能把尚缺实现统称为环境问题，也不能以环境无法执行为由宣称这些完成。

每个 blocker 只在其完成条件的真实记录出现后关闭。提交新 head 时保留旧失败，记录新 source/head/tree、原 profile、实际命令、原始结果及与上次执行的差异。代码审查、host 单测、artifact 回放、native guest、Linux GUI 和实际设备是不同证据层，不互相替代。禁止通过缩小测试分母、跳过 owning-package、默认赋予生产信任或把不确定结果写成成功来收口。
