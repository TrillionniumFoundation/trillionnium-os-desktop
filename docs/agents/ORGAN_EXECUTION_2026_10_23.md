# Organ 全量施工：2026-10-23 执行与阻塞记录

本页记录本次实际变更和验收边界。它不是发布资格，也不把未完成检查、测试 issuer、旧源码运行或设备枚举改记为完整产品通过。主线、候选代码、执行结果及尚缺输入分别绑定到下面的提交和原记录。

## 已闭合的主线增量

[#245](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/245) 于 **2026-10-23 05:42:28 UTC** 合入 `39c1d84ebf854958f5829c0118b0c8b92a6b4926`。合并树 `87bc4e4d72697a7583fb0afafe4db4b41582941c` 与验证提交 `c5c88794bf227b1d862b2f914b02809a0090e854` 完全一致，最终七项 GitHub checks 均成功。

原 A06 产物中的 `object_ownership_survives_inode_and_view_reconstruction` 实际通过；aster-core 为 275 passed、0 failed、0 filtered、0 soft-skipped。OSTD 报告 222 passed，其中 3 项 VMX soft-skip，实际执行下界为 219。原 G1-d 记录验证第 17 个 retained TID 被 `EAGAIN` 拒绝、15 个 zombie 加 parent 仍计 16、`WNOWAIT` 不退款、真正 reap 后可重用，以及四项 pids 控制写入被 `EACCES` 拒绝。原有 manager/recovery 仍有独立的进程创建空间。

最终 old-root 负控在不改变 probe 的情况下出现两个明确权限失败，且没有 timeout；它不是此前 thread/zombie/SysTree 语义变异的最终提交重跑。独立核验原件保存在 [A06 review](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/b2d20015f4d4fbc4db3754359ab1ddbf70e5d6ab/results/integration/2026-10-23-native-runtime/review-inputs/pr245-a06-independent-review.json) 和 [G1-d review](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/b2d20015f4d4fbc4db3754359ab1ddbf70e5d6ab/results/integration/2026-10-23-native-runtime/review-inputs/pr245-g1d-independent-review.json)。这项完成只覆盖 retained-task 与 SysTree owner 修复。

## 用户优先级与完成条件

| 优先级 / 工作 | 本次已落实的源码与证据 | 尚未闭合的完成条件 |
| --- | --- | --- |
| P0：#245 | 上述最终提交已同树合入；七项 checks、完整 core、严格 guest 正反记录已复核。 | 该修复增量已闭合；不转授完整资源隔离。 |
| P0：生产 Hepta / Notes | [Hepta #3383](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3383) 接入原 worker / issuer provider；[#3398](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3398) 已实现原 recovered writer、保护时钟、FinalUse 与原 Notes handoff 的生产组合候选。provider 7 项真实 socket 回归、authority 5 项独立组件回归及各自 Clippy 已执行。 | 原 Agentd 包的 7 条 factory + 5 条 Notes 测试尚未执行；独立生产 issuer operation / 部署、七项原输入、完整授权/回读/撤销/断连/重启验收仍缺。 |
| P0：聊天进入原 Hepta | [#255](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/255) 已实现 feature-gated Session adapter，复用原 Objective transport/history、保留完整原身份与 raw bytes，消耗一次性发送许可后才开始 I/O；8 项纯 policy 回归通过。 | `OriginalObjectiveRequestOwner` 尚无生产持久实现；10 条真实 UDS adapter 测试及 1 条 transport preview 测试未执行。原签名/身份/任务状态/unknown/取消仍需真实端到端接合，不能启用产品 Send。 |
| P0：F1 daemon / 最终 exec / G2 | [#253](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/253) 新增 x86_64 native CI；复用原 FleetRegistry / Supervisor / UnixProcessDriver，固定真实 A06 kernel 和三份原 userspace ELF。38 项 host 测试、11 项旧拒绝测试、实际 artifact 导入已通过。 | 固定 c5 kernel 存在 [#254](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/254) 已定位的 UDP stop 路径风险。需修复 kernel 的新 ordinary A06 资格与 source/hash 绑定，再实际构建、运行原生命周期；crash/restart、writer-lock、最终 exec 可信 role 和 G2 持久退役仍缺。 |
| P0：总资源与自主恢复 | #245 retained tasks 已进主线。[#249](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/249) 是 aggregate exec-copy 候选；[#252](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/252) 是 64 MiB sealed-family 用户数据帧候选，带自身原生证据。 | 两候选的当前 CI/整合审查；kernel heap/slab、page tables、网络元数据、全局 reserve、完整 memory 控制、可信暂停、watchdog 和公共恢复。 |
| P1：Makepad / Robrix | [Hepta #3067](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/3067) 保留原共享 Rust/Makepad Chat/Console 候选；[#251](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/251) 修复现有 egui 的 IME 与键盘激活。 | Desktop 仍使用 egui；共享 renderer 与 Session/broker 真实接合尚未完成。输入法实测、触摸、AccessKit/辅助技术与安装包验收分别缺失。 |
| P1：Asterinas app-server / 桌面 | 原内核与 host UI 有各自构建/运行记录。 | 原 app-server、真实任务与应用生命周期、实际 guest 图形和输入；host Weston 不是 Asterinas 桌面通过。 |
| P1：固定 x86 / 手机目标 | 既有硬件 inventory；[#250](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/250) 为原 Droidloom cell 的只读身份 adapter 候选。 | 指定实际设备上的受权效果、独立回读、重启/恢复。Android x86 cell 不是物理手机或 ARM/BSP 验收。 |
| 持续：文档与状态 | [#247](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/247) 补七个就近模块手册、九个 workflow / 两个入口的 README gate 修复和本执行记录；新增 [原 Objective owner 设计](OBJECTIVE_SENDER_OWNER_NEXT.md) 与 #254 独立证据核验。旧 runner 的新回归失败，新实现的针对性回归通过。 | 新组合的完整 CI；owner 设计仍是实现约束，不能作为已完成代码。每次合入后按真实 source pair 更新下表及当前 blocker，不复制旧通过数字。 |

本次记录时，尚未取得上述新候选的完整 CI 通过结果。排队没有执行日志时，仅记录 queued/pending；不推断编译失败，也不授予完成资格。

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
| Desktop #255 | head `940313d876481c6effc14ad783444e9e7b9d275a`；tree `2e94a12b8500ddca1d775712f0ffa7fbe86046d8` | 最终 8 项 policy 与 Rust 1.95 格式检查通过；本地原锁 offline 尝试在 dependency resolution 缺 `eframe`，原 transport 缺 `bytes 1.12.1`，故 10 UDS + 1 preview 测试尚未执行。原 lock 未改；规定的 Rust 1.88 UI 门禁仍未执行。 |
| Hepta #3398 | head `16418ddc3416a38a122b883cee46e2d3583cbd41`；tree `43fde98e9ea789b81b941e48bb65300c76c4292c`；source/test commit `dcdc9bdecfb401b1dd16f6ca9f57d7390e43142f` | 5 项 protected-authority 组件测试和 Clippy 通过；factory 7 + Notes 5 条已写但未执行。本地 partial workspace 在编译前缺 `aws-auth/Cargo.toml`，不是原仓库缺模块。原包 CI queued，不能转录为 running / passed。 |
| Desktop #254 独立审查 | 审查 head `18d400a2c112c4bd3b7d69209729640378e7db71`；实际诊断 runtime `c8f0c88ecb640117686ff05f850a73e60688eac7` | 76 个文本证据逐 size/SHA256、89 个 Git text blob、3 段 nonce/hex serial 与原 guest 文件已核对。原 Linux 与 native UDP 6 cases / 43 checks 对齐；9 阶段 lifecycle 是 diagnostic-only。新 portable A06 runner 的当前 CI 尚未运行。 |

#255 的 Session 接合只调用原 owner port。它在任何 transport 结果之后都不重新授予发送许可，未知恢复路径不包含 transport；原 history 按同一个 AgentId 查询并保留原始 observation。发送前本地取消可以丢弃许可；发送后必须走原 run owner 的取消流程，不能据此声明任务已取消。生产 sender 持久域、跨进程 permit fence 与 current-cut ACK 仍需在原 owner 中实现，见 [具体源码约束和 19 条待验收要求](OBJECTIVE_SENDER_OWNER_NEXT.md)。

#3398 使用相同原 protected clock 覆盖恢复与运行期，并在全部 metadata callback / await 之后、两个配置 handle 连续赋值之前执行最后一次同步验证。Notes 复用原 `with_notes_from_session`；只有安装成功后才返回 identity。原 `attached` ACK 可以先于最后授权拒绝发生，因此 ACK 只证明 descriptor handoff；失败时返回 `Err`、配置为空、effect FD 关闭，不授予 installed/runtime/effect 完成资格。[最终原始测试与源码身份](https://github.com/TrillionniumFoundation/hepta-private-ci/tree/16418ddc3416a38a122b883cee46e2d3583cbd41/docs/modules/runtime.agentd/evidence/2026-10-23-production-composition) 保留了隔离 harness、原包失败阶段与实际命令。

#254 的 [独立审查原件](../../results/integration/2026-10-23-udp-review/review.json) 证明：当前修复路径的六个 UDP 文件与 c8 runtime 相同，#253 固定 c5 的同六个文件则与未修复 b824 baseline 相同。在相同 resolver 条件下这是已知 stop 风险；没有冒称已经运行 #253 clean 原 fixture 并观察到失败。诊断使用的二进制没有补回原 build exit receipt，`original_agentd_lifecycle_qualified`、production authority、HOS2 control、power-loss recovery 均为 false。76 个归档没有独立完整 A06 QueryAbi 资格收据，不能把它作为 #253 新 kernel 导入凭据。必须取得修复源码的 ordinary A06 build / boot / QueryAbi / hash 记录，再更新 pin 并运行 clean 原 6d fixture。

## 每个模块的开发、技术与执行绑定

下表使用现有模块所有者，不引入平行实现。开发入口含构建/运行/测试命令；技术入口规定输入输出、权限、状态、并发或持久性。固定历史执行只证明其记录的 profile。

| 模块 | 源码 / 开发入口 | 技术与 profile | 本轮执行 / 当前 blocker |
| --- | --- | --- | --- |
| A00 集成 | `support/release`；[跨仓 source profile](ORGAN_RELEASE_PROFILE.md) | [架构](../ARCHITECTURE.md)、[原实施顺序](ORGAN_IMPLEMENTATION_NEXT.md) | #247 文档/source-gate 迁移；各候选尚未组成新的已验收整树。 |
| A01 源码 / 启动 | `kernel/asterinas`、`support/build`；[构建](../../support/build/README.md) | 固定 upstream / nightly；[完整 ktest](../../support/build/ktest/README.md) | #245 A06 已核验；不能把 kernel ktest 当原 daemon 或桌面执行。 |
| A02 HOS2 codec | `libs/os-abi`；[模块手册](../../libs/os-abi/README.md) | [NATIVE_ABI](../NATIVE_ABI.md) | ordinary 仍 QueryAbi-only；G1-c/G1-d 的效果仅属于各自 profile。 |
| A03 Control owner | `libs/os-control`；[验证入口](../../tests/control/VALIDATION.md) | [API_CONTRACT](../../libs/os-control/API_CONTRACT.md) | 原 D / 终态 / 退役 owner；Hepta durable ACK 与 native G2 仍需真实接合。 |
| A04 Linux / ELF | `compat/linux`、workloads；[开发手册](../../tests/workloads/linux/README.md) | [Linux gaps](../../compat/linux/GAPS.md)、[SQLite guest restart](../../tests/workloads/linux/SQLITE_GUEST_RESTART.md) | #253 原始动态 ELF guest CI；#249 exec-copy 候选。 |
| A05 映像 / 内核控制 | `device/misc/hepta_control.rs`、process loader；[handoff](handoffs/A05_KERNEL_CONTROL.md) | [G1-c](G1C_TRUSTED_OBSERVE_PROFILE.md)、[G1-d](G1D_TRUSTED_CONTROL_PROFILE.md) | 最终 exec 身份、动态 Agentd 可信 role 与生产 grant 未闭合。 |
| A06 隔离 / 恢复 | 原 cgroup / CPU / VM 对象；[CPU usage](../../tests/organ_backend/CPU_USAGE_G1B.md) | [安全与恢复](../SECURITY_AND_RECOVERY.md) | #245 已合；#249/#252 为窄域候选；完整总资源/watchdog/公共恢复仍开放。 |
| A07 Hepta 接合 | `services/hepta-os`；[开发](../../services/hepta-os/README.md)、[运行](../../services/hepta-os/RUN.md) | [Objective transport](../../services/hepta-os/OBJECTIVE_TRANSPORT.md)、[history](../../services/hepta-os/OBJECTIVE_HISTORY.md) | #3383 issuer、#3398 production/Notes composition、#255 Session 接合均有候选；原 issuer 部署和 Objective sender 持久 owner 缺失，原包门禁未执行。 |
| A08 Android | `support/android`、`compat/android`；[开发](../../support/android/README.md) | [接口](../../compat/android/INTERFACES.md)、[Android 边界](../ANDROID_COMPATIBILITY.md) | #250 只读 cell 候选；真实 effect owner、物理手机、ARM/BSP 未取得。 |
| A09 硬件 / VMM | `support/vmm`、`tests/hardware`；[运行](../../tests/hardware/RUN.md) | [硬件决定](../../support/hardware/DECISION.md)、[VMM gates](../../support/vmm/GATES.md) | 真实平台访问与 device-specific IOMMU / reset / recovery 仍需实现和执行。 |
| A10 UI / Session / Notes | [workspace](../../ui/README.md)、[core](../../ui/core/README.md)、[Session](../../ui/session/README.md)、[Shell](../../ui/shell/README.md)、[app-window](../../ui/app-window/README.md)、[broker](../../ui/broker/README.md) | [UI contracts](../../support/ui/INTEGRATION_CONTRACTS.md)、[Notes](../../support/ui/NOTES_ORGAN.md)、[UI 技术](../DESKTOP_UX.md) | #251 最终纯 Rust policy 13 tests，#255 Session policy 8 tests；完整 Rust 1.88 / UDS / Wayland CI 待执行。原 Makepad host bridge、辅助技术和 Asterinas 图形待完成。 |

## Makepad 统一的实现约束

Hepta 候选的 `apps/hepta-control-ui/rust/robrix-ui/src/presentation.rs` 已从同一个 `ChatWorkspace` 借用呈现；`RequestSend` 当前返回 `SendUnavailable`。`native_host` 接口承担现有 host 的观察、绘制确认和安全关闭，没有赋予 Objective 提交或设备控制权。Desktop 的 egui Shell 也不能从一个草稿或窗口状态推断原任务已完成。

统一时应沿这两个真实接合点施工：原 Makepad/Robrix widgets 复用现有 presentation；Desktop Session / broker 保持应用生命周期、私有 IPC 和权限职责；新 Objective adapter 仅传递原授权请求、原身份与原 history observation。不要在 UI 再造 scheduler、签名者或 effect ledger。渲染层迁移、权限装配和辅助技术执行必须分别有原始结果；增加依赖或复制 widgets 并不完成统一。

## 更新规则

缺代码与缺执行条件分开处理。原 Objective sender 持久 owner、完整 memory / watchdog、共享 Makepad 呈现接合和 Asterinas app-server 是实现工作；原包依赖缓存 / 排队 runner、独立生产 issuer 与保护输入、实际 x86 / 手机访问是执行或部署条件。不能把尚缺实现统称为环境问题，也不能以环境无法执行为由宣称这些完成。

每个 blocker 只在其完成条件的真实记录出现后关闭。提交新 head 时保留旧失败，记录新 source/head/tree、原 profile、实际命令、原始结果及与上次执行的差异。代码审查、host 单测、artifact 回放、native guest、Linux GUI 和实际设备是不同证据层，不互相替代。禁止通过缩小测试分母、跳过 owning-package、默认赋予生产信任或把不确定结果写成成功来收口。
