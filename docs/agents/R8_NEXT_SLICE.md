# R8 之后：可信目标到单任务 CPU 预算的下一切片

本页是下一实现工单；沿用 [ARCHITECTURE](../ARCHITECTURE.md)、[ROADMAP](../ROADMAP.md)、[PLAN](PLAN.md) 的 owner 与 G1/G2 定义，不重复总路线。
源码核对：desktop 候选 `cf2f61f73078f7310e60ea894c8ed83d51ef27b0`；Hepta 固定 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`；Asterinas 固定派生基线及工具链见 [upstream-lock](../../support/upstream-lock.json)。
**R8 已实际完成隔离测试 issuer 的原版准入与 known-run 桌面投影；本页维护后续产品接合，不能将这些新工单记为已通过。** 执行输入为 `25298f5d87cf3db90deefe9c0405ecd241dc6581`，同树远端 `ca5e7d8473690df1bf7636de0808e58414c40abe`；两轮各 10 核心检查 / 7 次提交尝试，后一轮另有 3 个 Session 阶段和同一 Shell 的 3 张实际图，见 [本轮证据](../../results/integration/2026-10-18-objective-desktop/README.md)。测试 issuer、停 owner 后的只读 journal 核对和英文 Runtime 卡片通过，生产 issuer、在线 durable reconciliation、设备控制与 G2 仍待实现。

## 交付目标与实施顺序

用户为一个已创建的后台任务指定授权封套内的绝对 CPU 预算；既有 issuer 签发，原 Hepta owner 接收并持久记录，窄适配器调用 HOS2，桌面显示原 owner 与内核的可核对结果。
首个目标固定为一个稳定资源对象、N0 单 vCPU、100 ms 对齐周期；控制器先用显式固定目标，随后再比较 Hepta 策略。通用设备、模型本地推理和移动端不包含在这份交付中。
进度记录只使用“接口待接合 / 已构建 / 已在指定宿主运行 / 负例通过 / 门禁闭合”，每项附实际源码、ELF 和日志身份。[ABI]、[D1]

| 工单 | 实施 owner | 可并行前提 | 闭合产物 |
| --- | --- | --- | --- |
| S1 既有 issuer 接入 | A07 + 原 issuer/Agentd 产品宿主；A10 仅展示 | 隔离原版 probe 已通过；需已有 issuer/provider 和原请求保存 owner | 真实签发来源、单次提交与原 owner receipt |
| S2 durable 与 unknown | A07 + 原 RunStart/Operations owners | S1 身份契约；可先做原 Linux 故障实验 | 原 owner 历史查询/核对、接替及禁止盲重放 |
| S3 受限效果适配 | A07 + 原 authority/Operations owners | S2 的持久投递接缝确定 | 单一目的端 adapter 与原 owner 确认 |
| S4 Asterinas G1 | A05 + A06，A02/A03 提供已实现库 | 独立于模型和 S1；同一内核树串行集成 | 普通客户端在客体执行五操作及故障负例 |
| S5 Asterinas G2 | A07 + A04 + A05/A06；A10 展示 | S1–S4 与必要 Linux/存储语义均通过 | 真实 Hepta owner 到该内核的 W1 证据 |

## S1：把测试 issuer 替换为已有可信签发来源

**固定事实 / API：** `AgentdConfig::with_authbus_trust_file`、`with_authbus_checkpoint_file`、`with_objective_profile_file` 接受明确的宿主配置；`TextTrust::load` 读取原 owner 的私有公钥登记并在准入阶段重新加载。CLI `hepta-submit` 只传输已存在的原始信封，不签发、不发现配置；ObjectiveStart 与最终效果授权是两个边界。[H1]、[H2]、[CLI]

最小实现放在 `services/hepta-os` 的独立可信宿主接合中，保持 `objective-transport` 显式启用；Session/Shell 继续消费投影，不持签名密钥、trust 文件或控制 FD。
由现有 issuer owner 提供明确的 issuer ID、key epoch、scope/主体和签发入口；可信 launcher 提供原 AgentId、spawn、peer UID/PID。无已配置来源时返回“未装配”，不生成测试密钥补位。
原 issuer/请求 owner 在首次发送前保存准确原始意图与信封；先确认其现有持久入口，未接通之前只能受控资格实验，不能开启产品提交按钮。桌面草稿存储不承担请求账本。
仅消费一个既有 ObjectiveStart，原始字段/签名字节不重写；收到 admitted 后显示原 receipt 的 disposition，分别表示 compiled、abstain 等语义，不展示为“任务效果完成”。

- 正验收：独立现有 issuer 签发的限定目标经真实原 owner 准入；信封身份、peer、run、publication/chain digest 与原始记录相符；桌面只投影这份结果。
- 负验收：未配置来源、伪签名、错误主体/scope、过期、撤销、旧 key epoch、body/spawn 不一致均不能产生越权准入；原 owner 泛化拒绝按 unknown 保留，不由测试脚本改写成未发布。
- 依赖 / 完成判定：既有 issuer 和请求保存入口的 owner 给出可调用契约，S2 能处理结果丢失；用这套真实来源完整执行后才标记生产接入通过。隔离测试 issuer 的成功单列。

## S2：分别核对准入历史与实际效果终态

**R9 已接通并实测的范围：**原 owner 独立的 `ObjectiveAdmission` 窄读接口与默认关闭的 `hepta-history` 客户端已通过本机 x86_64 Linux 真实运行。桌面输入 `207ff9da7dac83c57b0cbae46c4b03ecfba3baa9`、原 owner 最终 `2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5`，15 检查、13 history 查询、5 次独立 Objective 请求、4 条 durable publication、3 次 Supervisor 重启；恢复重投、model turn、Operations dispatch、设备效果及新 K/D 均为 0。[实际证据](../../results/integration/2026-10-18-objective-history/README.md) 和 [独立运行复核](../../results/integration/2026-10-18-objective-history/history-runtime-independent-review.json) 保留各输入与 ELF 绑定。精确扩展源码由 [独立合同](../../services/hepta-os/OBJECTIVE_HISTORY_CONTRACT.json) 固定，协议与存储边界见 [history 契约](../../services/hepta-os/OBJECTIVE_HISTORY.md)，复跑见 [故障 probe](../../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)。该增量完成的是准确 `原请求 → 历史 publication` 的 owner 查询；原请求/anchor 的生产持久保存入口与 `K → 效果终态` 仍未闭合。原 owner 的 134 项测试在 `ee0`、173 项在 `d1`，客户端 51 项在 `c080`；最终 native05 构建与本轮运行单独绑定 `2be`，不能重标为最终 HEAD 重跑了 307 项 owner 单测。随后 desktop `46dc…` / owner `2be…` 的 transport 与 ARM64 history 各自真实 success，51 Rust + 22 synthetic 与 ARM 15 场景 / 13 查询 / 5 请求 / 4 publication / 3 重启 / 0 重投分别记账；源码、原始 ZIP、签名、journal 和五 ELF 字节复核见 [CI 接续](../../results/integration/2026-10-18-objective-history-ci/README.md)。desktop #193 已合入 `aab50f3`；Hepta 自身剩余 CI 修复、原请求与 anchor 生产保存、UI 新投影及 Operations 效果链仍须各自闭合。

**原 f8 固定事实 / API：**原 `objective_runtime` 可能先发布 RunStart journal，再因后续检查返回错误；`AgentdClient::run_status` 读取当前内存投影。原 f8 客户端没有 ObjectiveStart 持久结果查询 RPC，新 `2be` 接口不改写该基线事实。`DurableRunStartJournal` 公开 `recover/get/authentication_records`，但恢复持文件锁且可能截断未确认尾部，不能把它当在线无副作用读取。[H3]、[H4]、[H10]
[R8 的停机 probe](../../tests/integration/hepta/original_objective_probe.rs) 使用只读 `File` 与已确认 anchor，遇到需要截断的尾部则失败；R9 的在线查询由活动原 owner 读取其已恢复的内存前缀，不旁路恢复或读取活跃账本。R9 存储故障均先确认 owner 已受控停止，再改变测试 journal 字节，重新启动后由原 Agentd 自身恢复。它们证明这两类字节故障的 reopen 行为，不证明写入中途 crash 或断电恢复。
原 `DurableOperationStore` 提供 `operation`、`unsettled_operations`、`mark_indeterminate`、`adopt_unsettled_generation`、`observe_terminal`；`ReconciliationReceiptV1` 的结构有效不等于来源可信，独立证据的主体与资源绑定仍由原宿主核验。[H5]

原 owner 查询精确匹配保留的原签名认证、canonical body、run/profile 与 publication；caller 给定的 anchor 必须匹配已恢复的链且覆盖目标 publication。更早的有效 anchor 不覆盖后续记录；已知 anchor 缺失、链不匹配或原请求变更保持 unknown。旧请求实际过期或隔离 issuer 撤销后仍可定位历史，不授予新的提交权；本轮撤销后的独立新请求被拒绝且 journal 不变。查询结果和所用 anchor/覆盖范围必须一同保留；查询不重新读磁盘，即使有 anchor 也不是实时磁盘篡改检测，caller anchor 与 journal 共同回滚未测试。无 anchor 或查询 unknown 均不能产生历史否定结论。

| 故障 / 边界 | R9 实际观测与后续资格 |
| --- | --- |
| 完整发送后丢响应 | 原协议 qualification harness 丢弃响应，随后准确原请求查到 publication，未重投；本 history 运行没有执行 `hepta-submit` CLI 丢回复故障；下方独立 CLI 被杀回归保持它自己的 scripted-peer 来源。 |
| 持久发布后提交返回错误 | 真实 `hepta-submit` 返回 `submit_unknown / objective_owner_request_rejected`，同请求查到第 4 条 compiled publication，`RunStatus: null`。`CapacityExceeded` 是固定源码/默认容量推论，具体原始错误字节未观测。 |
| 原 owner 受控重启，RunStatus 返回 null | retained anchor 覆盖原 publication，历史仍可查询；不恢复历史 run，也不伪造“未受理”。本轮三次受控重启不等于 crash/power-loss 资格。 |
| journal 回滚、尾部截断、错误或过早 anchor、原签名变更 | 对应 `anchor_missing`、`anchor_mismatch`、`publication_outside_anchor` 或 `no_matching_publication` 均保持 unknown；原始与故障字节、摘要和原 owner 恢复结果归档。 |
| 效果发生后源 owner 崩溃，随后接替 | 本轮未执行。后续保留旧 K、fence 旧 writer，再依独立原 D 终态恢复；旧 generation 的确认必须拒绝。 |

**后续实现与完成判定：**接入生产请求 owner 对准确原信封、身份、anchor 及覆盖范围的持久保存；Session/Shell 增加“提交结果未知”“历史已发布”“效果待核对”“已确认效果”的安全投影，只有对应 owner 的完整、匹配且新鲜的证据能推进状态。效果恢复通过原 Operations owner 读取旧 `K=(scope_id,operation_id)`，接替时沿 `adopt_unsettled_generation` fence 旧 writer，再用目的端独立证据结算；`NotSeen`、历史丢失、超时、当前 cap 恰好相同均不能生成 `NotApplied`。真实效果存储提交、写入中途 crash/reopen 与旧 K 接替仍需各自可复跑的收据，不能用本轮历史查询通过代替；观察权限不成为执行或重试权限，恢复者不新建 K、不盲重发、不清除未知。

**R9 已完成的有界增量：**[真实 CLI 进程丢失回归](../../results/integration/2026-10-18-runtime-process-boundaries/hepta-cli/README.md) 新增两个实际 `hepta-submit` SIGKILL/reap 用例：调用方持有 EOF 时终止，以及 peer 已读取完整原帧、尚未回复时终止。用 channel 握手固定故障点，保留准确原输入，断言没有输出回执、第二帧或自动重连。前者的独立 fixture 可证明当次没有连接，后者证明完整发送而结果未知；调用方仅看到 CLI 无输出时不能据此合成 `NotSent` 或 `NotApplied`。完整 feature suite 43 项通过，新增两项已包含其中。该 CLI 丢失实验本身未实现首次发送前的产品持久保存或 durable reconciliation；原 owner `2be` 在线查询已经由上方独立原版运行验证，生产请求/anchor 保存、UI 投影和效果核对仍按 S1/S2 判据推进。

## S3：从原 authority/Operations 接到一个受限 OS adapter

**固定事实 / API：** `DurableOperationIntentV1` 持有 scope、operation、predecessor、destination、payload digest 和 owner generation；`final_use_binding()` 由原实现生成。`DurableDispatcher::dispatch_claim` 经 `authorize_dispatch/execute_authorized` 进入实际效果；授权与 dispatching 状态先持久化，效果不确定则进入 Indeterminate。[H5]、[H6]、[H11]
既有产品装配点是 `AgentdProductionOperationRuntimeConfig`、外部 `AgentdFinalUseGrantProvider` 与 `FinalUseProductionOutboxTarget::{destination_id,observe_terminal}` / `ProductionOutboxTarget::dispatch`；必须绑定已恢复的同一个 writer authority/lease/generation，默认启动不自动安装这些 owner。[H7]、[H8]

先新增限定 CPU 操作的 adapter 契约和实现，再接原产品宿主；首个 `destination_id` 从可信资源登记解析为稳定 object ID，不接受任意 PID、文件路径、ioctl 号、shell 命令或用户自报 scope。
不可变语义内容包含对象、动作、period/cap、资源 revision 前提和授权封套；原 owner 生成 payload/semantic digest 与 final-use binding，adapter 验证完整内容后不再从可变草稿重建请求。
AuthBus 信封准入不能替代 `SignedFinalUseGrant`；最终授权由既有独立 grant provider 提供，固定信任环、受保护时间和撤销 frontier 由原 `FinalUseAuthority` 管理。[H9]
先打通下表的原 owner 持久接缝；`DurableOperationIntentV1` 本身没有 HOS2 D 字段，不能假定已经具备 K↔D 共提交。缺失的保存/查询入口须交原 owner 扩展，desktop 不开第二份 SQLite 或私有账本。[H6]、[D2]

| 必须绑定 | 保存或检查位置 |
| --- | --- |
| K、不可变语义摘要、目的对象 | 原 Operations owner 的既有意图/outbox 事务 |
| K↔D、准确请求、boot/CapSpace、写 sequence | 原 owner 的持久投递记录，在实际 ioctl 前提交；D 不取代 K |
| 当前 grant/祖先 epoch、对象实例、resource revision | A05/A06 实际资源 owner 的同一 mutation 临界区 |
| 原 D 终态、响应摘要、原 owner 持久确认 | 目的端独立观察 → 原 owner 提交；随后才允许连续 RetireThrough |

预算安装的原 owner 终态须依据匹配 D、对象、revision 的可信原 D 终态；实际 CPU 执行另做独立验收，不用当前用量代替历史。copyout 丢失查询原 D，禁止分配新 D 追求成功。设备效果与 SQLite 不在同一事务，不能借 `DestinationDedupeStore` 的数据库事务能力宣称 ioctl 原子共提交。[H12]、[ABI]

- 正验收：一个授权目标安装一次；准确重复的 K/D 返回原结果且 revision 不再增加；独立观察者核对对象、有效时间、预算和真实工作量；原 owner 持久确认后退役。
- 负验收：同 K/D 改内容、换对象、换 namespace、过期/撤销、旧 writer、错误 predecessor、copyout 故障、未确认前退役均拒绝或保留未知；目标外任务继续运行。
- 依赖 / 完成判定：S2 与 K↔D 持久入口就绪，在受控 Linux 目的端先验证 owner/adapter 协议；该结果不授予 Asterinas 资格。G1 前不启用真实 HOS2 写能力。

## S4：同一 Asterinas 派生内核闭合 G1

**固定事实 / API：** 当前 `hepta_control.rs` 仅宣告 QueryAbi，其他已知操作返回 EOPNOTSUPP；A06 已有真实 cgroup CPU controller，A03 的 native namespace/授权 receipt 接缝仍非实际内核效果路径。[D1]、[D3]、[D4]

**R9 源审计调整：**[固定 G1 owner 接缝](R9_G1_OWNER_SEAM.md) 已发现普通 `cpu.max` 与 native API 尚未共享 revision，RCU 替换后的旧 controller Arc 仍可能存活，raw TSC 计费窗口也尚未与 HOS2 BOOTTIME 纳秒对齐。因此先做同预算锁中的 shared revision + 不可逆 controller incarnation/detached fence，再做真实计费/时钟接合，最后才按下列逻辑依赖接入可信 init 和五操作；不能先授予尚未接到同一实际资源 owner 的写权限。该审计未修改或运行新内核。

A05/A06 在一个集成树串行完成以下接合（实际开发先后以上述 R9 前置项为准）：

1. 可信 init 在最终 exec 身份确定后激活单目标 resource.manage 和独立 resource.observe/history 权限；沿用真实 Process、exec_epoch、CapSpace 与 boot 绑定。open/dup/fork/传 FD 不增权，普通 exec 不自动重授。
2. A05 复用 A02 codec 与 `ControlCore::reserve_native` / `execute_native_reserved`；A06 在其 owner 模块提供窄入口，固定实际 `SubController<CpuController>`，不包装另一个预算 owner。
3. 先结算实际运行，再在原资源锁中检查当前权限、祖先、lease、revision 并安装预算；Linux cgroup 与 HOS2 抵达同一计费/节流/唤醒状态。同值更新不充值，cap 降低不抹掉已用量。
4. 接通 ReadUsage、InstallBudget、QueryDelivery、RetireThrough；仅完整实现后宣告相应 supported_ops。查询、copyout 重取与退役沿同一有界 D 窗口；公开 wire 和内部 bootstrap 分开。[ABI]、[D3]

第一 profile 强制一 vCPU、100 ms 周期，拒绝未支持的调度类/迁移；独立恢复线程及祖先资源不能受被管理目标削减。预算误差、timer 唤醒和最大不可抢占延迟的验收界须在运行前写入 profile，不能看到结果后调宽阈值。
正验收使用普通非 AI 客户端，真实安装/降额/同值更新/cap=0/新周期唤醒；同时读累计与分窗计费，以独立 CPU 负载完成量交叉核对，并保留实际生效时刻和 revision。
负验收包括 forged FD/旧 exec/PID 复用、跨 scope/对象、祖先 revoke、CAS 竞争、同 D 改内容、copyout 后准确重取、1024 未退役窗口耗尽、迟到已退役 D、退出尾段结算以及受控 IRQ/锁交错。
依赖 / 完成判定：上述客户端和 kernel ktest 在同一个固定 nightly 构建的真实 QEMU 内核上通过；原始 serial、kernel/initramfs/固件哈希、profile 和每项正负结果齐全。既有宿主/Loom 或单一 cgroup 配额探针只能复用其限定证据，不能替代五操作闭合。

## S5：在 G1 内核上闭合真实 Hepta W1 / G2

**固定事实：** 原 Linux 上的 Agentd/Session/Shell 资格与 Asterinas 客体资格不同；现有 G2 定义要求真实操作 owner、持久确认、历史查询/退役以及 revoke/kill/reboot。[PLAN]、[D2]

A04 先从 S1–S3 的真实固定 ELF/profile trace 列出最小依赖；对实际所用的 AF_UNIX/peer credentials、epoll/futex、锁、SQLite WAL、fsync/目录持久化分别做 Linux 与候选内核差分。缺哪个实现哪个，不将模型配置故障改记成内核缺陷。
A07 在 G1 同树内核/固定 rootfs 中装配原 owner 与同一窄 adapter，执行一次持久预算操作，随后执行准确重复、权限撤销、管理者退出和重启恢复；Session/Shell 只显示绑定到该运行的原 owner/内核投影。
受控 reboot 后旧 boot 的 D 不能执行；目的历史缺失保留 Indeterminate。若需要新的绝对目标收敛，必须先 fence 旧执行者、核验稳定对象并取得新授权，建立明确的新 K，旧 K 仍 unknown；不用于不可逆设备动作。[D2]
正验收同时包含原 owner durable 提交、内核实际资源变化、独立观察、确认后退役与目标外服务存活。负验收在提交前后、效果前后和结果提交前后注入退出/断电，核对旧 generation/ACK、重复和沉默历史。
完成判定：一份关联 `run → K → D → object/revision → 终态确认 → retire` 的真实跨进程证据，所有必要依赖与故障例均在指定 Asterinas profile 通过；这才关闭 G2。软件窗口、ARM 宿主 CI、Android 或裸机资格仍分别记账。

## Asterinas 增量与独立 Rust kernel 的决策门槛

默认继续完整 Asterinas 派生，在既有对象、FileLike 和调度 owner 上做窄接合；预算配置缺失、单个回归或 UI 进展不构成重建内核的理由。[架构](../ARCHITECTURE.md)
重新评估必须提交可重复反例：固定 W0/W1 与硬件/profile 下，现有对象/权限或故障隔离结构无法满足明确要求，且已比较局部修复、用户态服务隔离与 OSTD 上层替换的实际代价。
性能理由必须使用同一负载、预先声明的延迟/预算界和资源成本；维护理由必须列出持续冲突的真实补丁与回归。无这些证据，继续增量，不能凭“AI native”命名触发重写。
只有针对该反例的 OSTD 最小原型已通过同一正负测试，且迁移/回退方案保留 HOS2、Linux 必需子集、原 Hepta owner/K/D 语义和可启动恢复镜像，才批准替换相关上层；先替换被证实冲突的部分。
连 OSTD 都需替换时，再单独证明其内存/IRQ/调度边界的具体不可修复冲突，并交付等价启动、隔离、驱动和恢复测试；未满足前不并行维护第二套产品内核，也不估计伪完成率或交付日期。

## 工单收口材料

每个工单提交实现、模块开发说明、API/状态与故障契约、可复跑命令和原始正负日志；引用实际执行的 commit/tree、features、ELF、存储与运行 profile。编译通过、运行通过及证据复用分别记录。
原始失败、unknown 和未运行项不可删改；GitHub queued/cancelled 不记为代码失败或通过。本轮 R8 的原版/桌面实际收据已归档到 [STATUS](../STATUS.md) 与 [本轮证据](../../results/integration/2026-10-18-objective-desktop/README.md)；本页只维护后续 S1–S5 的实现依赖，不改变历史失败或原版/目标 OS 的资格边界。

[PLAN]: PLAN.md
[ABI]: ../NATIVE_ABI.md
[D1]: ../../kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs
[D2]: ../HEPTA_INTEGRATION.md
[D3]: ../../libs/os-control/API_CONTRACT.md
[D4]: ../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs
[CLI]: ../../services/hepta-os/OBJECTIVE_TRANSPORT.md
[H1]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/config.rs
[H2]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/authbus_trust.rs
[H3]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/objective_runtime.rs
[H4]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-learning-ledger/src/run_start.rs
[H5]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-operations/src/durable_store.rs
[H6]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-operations/src/durable_model.rs
[H7]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/production_writer_host.rs
[H8]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-memory/src/production_writer.rs
[H9]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-contracts/src/final_use.rs
[H10]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/client.rs
[H11]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-operations/src/dispatcher.rs
[H12]: https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-operations/src/destination_dedupe.rs
