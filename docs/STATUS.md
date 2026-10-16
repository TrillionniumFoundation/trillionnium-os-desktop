# 当前状态

## 2026-10-16：A00 本轮源码安全修复与真实验证增量

- **已合并测试源码（实际 main）**：[A05 PR #45](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/45) 合并 commit `54d5197bf66be23ea8b1f3ff5a3d2c40a82694b7`，修复 `tests/kernel/control/hos2_queryabi_probe.c` 将 EFAULT 等非 ENOTTY 错误误判为真实 `/dev/null` 拒绝的假阳性。A00 在独立 Linux x86_64 / GCC 14.2.0 宿主重建三份源码并逐文件比对精确 Git blob：`ae59693d54c375812dd522a1568c520a41c87e70`、`862a50fb8d9affd361510a2a2d9b29b6307f66ea`、`53aba3d3433b92a2d10b74136231db61f892ebb4`。`sh -n`、严格 C11 GCC、原生 `sh run-host-smoke.sh`、UBSan 和静态链接 selftest 均通过；旧处理在新负测下退出1，修复版通过。这仅是 **Linux 宿主** HOS2 负面探针，不是新内核 QueryAbi 实现。
- **A03 安全源码已推送、未合主干**：[Draft #48](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/48) commit `a10f0b8ddea9c1627469ab79b2f2e1ed551f3e79`，把 #35 真正 Hepta K（StableId+Digest32）和 #30 的 `OriginalOwnerAuthority`/伪造 ACK 回归整合为**两文件、19个无冲突精确补丁块**。源码/对象静态检查通过，但 Cargo、fmt、Clippy 和 QEMU 在本轮未运行，原 Hepta owner 的持久核验仍缺失；不得合入或宣称 G2。后续 #36/#37/#39 必须串行审查；#37 当前 stale `ReadUsage` 返回 `sample < window_start` 与 ABI 所要求的 `window_start=floor(sample/100ms)*100ms` 冲突，已向 owner 反馈，暂不捆绑。
- **A06 真实测试证据关联**：[Draft #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 当前 cgroup CPU blob `bce4cabfcc933af4107f7d892e735027b4acbd1e` 与 scheduler blob `a9767b2d037ba2e85243b5b498de814353f95178` 精确匹配此前独立构建的 #41 修复源码；其历史产物有 151 个实际 aster-core QEMU ktest、12 次正式 guest quota 检查及2次唤醒测试。**本轮未重新编译内核/QEMU**；cpu.stat 读可提前滚动未结算窗口的缺陷待 [Draft #44](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/44) 修复后实际内核复测。尚无真实 HOS2 CapSpace/ioctl、Hepta 持久退役、SMP/物理硬件验收。
- **CI 的真实状态：**G0 host-contracts 和 A01 host-evidence 的最新相关 GitHub job 持续 `queued`（issue [#33](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/33)）；不能当作通过。本轮 A05 小范围宿主修复以精确 Git blob 的独立实际执行作为合并依据，没有修改仓库保护规则、固定 Asterinas/Hepta 版本、根空 README 或生产服务。

---


## 2026-10-16：A00 合并定向 A01 回归、清理过时 ABI Draft，并核对真实 G1/G2 阻塞

- **本轮新增主干代码：**[PR #23](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/23) 已合并，merge `7d5121a41090dc74521de8a6a14d923d9dfc34db`，只新增 `.github/workflows/a01-boot-evidence.yml`，在相关路径变化时执行现有 A01 启动证据与 runner 的 Python 宿主对抗用例、空根 README 和上游锁校验；**不**把宿主 fixture 冒充内核构建或 QEMU。该提交的 [Actions run 38904246724](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38904246724) 最近一次读取为 **queued / conclusion=null**，未记录为通过。
- **A02 现有事实：**完整 no_std Wire codec 已经由 [#13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13) 合入；旧初始 Draft #4 与之冲突，已保留历史并关闭（未合并）。主干 12 个黄金样本中读用量 sample=150ms/window_start=100ms/consumed=35ms，InstallBudget 和 terminal history 共用 effective=140ms/consumed=33ms；`tests/abi/test_mutations.py` 已包含针对 cap/expected_revision 的六项对抗测试。A00 对这些仓库字节执行 17 项独立 JS 结构/时间/漂移断言均通过，但**未在本轮执行 Rust Cargo、CI 或 QEMU**。
- **A03 单一资源域与安全边界：**主干源码检索只存在 `libs/os-control/src/lib.rs::ResourceDomain` 这一宿主模型定义；A05/A06 真实内核共享资源域未实现，不能声称已验收。主干已有悬挂前缀、错误 publisher 和连续退役负测；然而 `retire_through` 仍允许没有可信 original-owner 能力的 syntactically valid receipt，详见 [issue #28](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/28)。修复在未通过 exact-head Cargo 的 Draft [#30](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/30)，真实 Hepta StableId+Digest32 K 的主干类型纠正在 Draft [#35](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/35)；与 #36/#37/#39 的 A03 所有权补丁须串行整合。
- **G1/G2 保持未完成：**A06 真正的单 vCPU 1kHz 配额旧版曾有 QEMU 客体证据，跨100ms边界漏记/抢占计费的新修复 #41 仍需固定 nightly 的内核 ktest 和原始负载 QEMU；不得将 Draft #40 的不同欠账算法直接叠加。A05 仅有已合并 QueryAbi **Linux 宿主 ELF/ENOTTY** 探针，尚无 CapSpace/ioctl kernel；A07 尚未把 `kernel.authority` 的原 Hepta 持久 owner 与 D/撤销/重启验收接合。无本轮实机或新内核端到端验收。当前定向 CI 排队问题跟踪 [#33](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/33)。

---


## 2026-10-16：跨周期 CPU charge 漏记修复待内核验收

- **可复现的源码问题：**当前 A06 1kHz 超额结转代码先执行 `CpuMax::advance(until)`，再按照已经更新的窗口起点记账，可能丢失线程跨越一个或多个100ms周期时旧窗口尚未记入的 CPU 时间。原有平滑负载 QEMU 结果不证明此极端时间交错正确。
- **回归代码：**[Draft PR #40](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/40)，分支 `agents/A06-cross-period-charge`，基于 A06 `4e23125a006dca5ce90d32cbab41c079b8da9a1d`，新增两项内核 `#[ktest]` 对抗案例，并在推进窗口前补记 `[from,until)` 中已完成周期的运行时间；修复提交 `03f1caed0f35aaed98d20cb12bce758e22a51124`。不变更 1kHz 全局定时器、HOS2 wire、Hepta owner 或 cgroup 资源结构。
- **实际验证分层：**从相应真实内核 `CpuMax` 实现提取纯状态机、以固定 1MHz TSC 仿真进行独立 `rustc --test`：**修复前 4通过、2新增测试失败（exit101），修复后 6/6通过（exit0）**；这是宿主数学/源码测试，尚非改后 Asterinas 的内核编译或 QEMU 通过。
- **实机验收阻塞：**尝试执行固定内核源码构建时，与另一个 A06 并发工作树的 OSDK/Cargo 生成锁出现 package collision；后续恢复验证时，执行机远程 tunnel 暂不可用，无法权威读取后续构建结果。**PR #40 保持 Draft，不会仅凭宿主测试合并或宣布配额精度已合格。** 同类实际 QEMU/ktest 验收应由 A06 owner 在受控环境复跑；原 A06 已验收的 9/9 QEMU 和145/145内核测试仍仅证明此前版本自身。
- **后续唯一修复路径：**同一个源码快照应完成 Asterinas nightly-2026-07-21 `make kernel`、`aster-core` 的新增 ktest 以及原始完整 `cpu.stat` 的 1%/10%/SCHED_FIFO/父域 QEMU；保留源/产物SHA与失败证据，审查当前预算窗口已被其他入口提前滚动时的延迟计费条件。完成前不合入 A06 或 main。

---

## 2026-10-16：1000Hz CPU 超额结转已通过客体验证并进入 A06

- **源代码与合并：**[PR #38](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/38) 已合并进 A06 **开发分支**，merge `d5741c7b7e2e17bb733d2d810408433da721b5a5`；原 `CpuControl.max` 的本地 IRQ 安全锁保留，OSTD 全局 `TIMER_FREQ=1000` 未改。对上一周期实际超额 CPU 消耗只结转正向欠额，并在后续周期抵扣，不储存未用额度；内核真实 `used_clocks` 与结转欠额独立。A06 主 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) **仍是 Draft，未合并 main**。
- **正式源码与客体：**最终代码已重新编译，release ELF SHA256 `9e3c106b88198a5dc1aef81c25392ab89aa3777831d17a852f869ab9747a0b59`；使用原始完整 `cpu.stat` 探针、q35/TCG、1 vCPU、512MiB。**9/9 QEMU 客体测试正常完成**：1% CPU 配额三次1.100/1.200/1.200%，10% 三次9.995/10.204/10.502%，SCHED_FIFO 10%=9.645%，父域10%=10.749%，50% 单次53.477%（不掩盖固定周期边界突发）。
- **长窗口对照与可复跑入口：**10秒实际QEMU对照中，原1%配额为2.000%，新方案为1.109%；原50%为51.146%，新方案为50.238%。新增 `tests/organ_backend/run_candidate_matrix.py --duration-seconds 10 --max-cpu-percent 1.5`，正式 ELF再次跑通1%场景，观测 **1.100%**。**Asterinas真实 `aster-core` 内核测试145/145通过**，含4项新增的超额结转/不存信用/不充值回归。原始数据见 [机器结果](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/agents/A06-cpu-bandwidth-n0/results/organ-backend/2026-10-16/a06-quota-debt-n0.json)。
- **去除并行路线：**5kHz全局升频实验 [PR #34](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/34) 已保留结果并关闭，不作为默认优化；无需提高所有工作负载的定时器频率。
- **仍未放行：**上述结果只支持单vCPU N0在观察窗口内的平均限制与无死锁；**不保证每个100ms周期的严格上限**。多CPU聚合与迁移、跨周期运行时间切分、资源控制器生命周期、硬件/能耗/尾延迟、HOS2 CapSpace ioctl、Hepta真实持久效果与Android/GPU仍待实际验证。不要将这次A06开发分支成果计作新内核已在main生产放行。

---

## 2026-10-16：N0 精度实验和 K↔D 主干接合

- **A03 本轮真实合并：**[PR #25](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/25)，merge `62d63809ee683402a90e7d15031e6d51a6eac133`。将 value-only 的 Hepta K↔D 绑定类型加入 Rust 宿主控制库；独立对 HEAD `755bbbe7eb6b492d21f69da80f41d93af97fba06` 完成 **21/21 Cargo 测试（1单元+20集成）、严格Clippy和fmt**，均通过。它不是 HOS2 真实内核持久操作，也不能凭 value-only identity 宣告已完成不可变摘要或 owner 认证；对应后续 PR 仍有单独验证。
- **A06 1kHz精度现状：**已经确认 IRQ-safe 锁合入 A06 自己的分支，修改后 q35/TCG、1 vCPU 原始 `cpu.stat` 探针不再死锁，但 1% 配置实测约1.9–2.0%，尚非严格1%保证；A06主 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 仍处 Draft，**未合并 main**。
- **5kHz 并行实验：**[PR #34](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/34) 在同类真实QEMU客体测试中，1%配置观测约1.100%、1.217%、1.163%；10%配置约10.152–10.355%。其对照中无限额1s循环迭代次数较1kHz约降低15.8%（非随机化TCG样本，不能推出真实硬件因果性能/能耗）。**不将全局tick直接从1kHz提高到5kHz作为生产默认。** 已向 PR 反馈更窄的跨周期超额欠账（overshoot debt）方案和原始探针的验收要求；这项方案**尚未写入内核源码**，曾遇到执行通道源码写入拒绝，不计已实现。
- **后续实际门槛：**A06 需保留1kHz基线，验证周期边界费用结算、降额不充值、低配额精度、静态/实时/父级预算及恢复；之后 A05 接权限与 HOS2 内核控制，A07 才能完成真实 Hepta K↔D 原有 owner 的持久确认/退役。不要把宿主状态模型或5kHz实验结果冒充生产OS能力。

---

## 2026-10-16：IRQ 重入修复已进入 A06（未合并主干）

- **修复位置和版本：**[PR #29](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/29) 已合入 A06 开发分支，实际合并提交 `6b7a4580f74add2b640b6ea948797bd87733faac`。原 `CpuControl.max: SpinLock<CpuMax>` 默认只禁止抢占；同一把锁会被定时器 IRQ 的 CPU 计费/资格检查路径获取。改为 `SpinLock<CpuMax, LocalIrqDisabled>`，保证持锁期间本地 IRQ 不重入。**A06 主 PR #18 仍是 Draft，未合入 main。**
- **真实 QEMU 证据：**在 A06 最新合并源码的相同 Git tree 上从源码构建 Asterinas 内核 ELF，SHA256 `8ff3629163438f86abe755aa5a61f3e8d53d2ab44994f41d006d04e3415d80a5`。使用固定 A01 initramfs、原始完整 `cpu.stat` 探针，q35/TCG、1 vCPU、512 MiB、无宿主网络/数据盘。**6/6 客体运行成功（raw33、无 panic）**：普通任务1%重复3次分别2.001%、2.000%、1.911%；普通任务10%=11.100%；SCHED_FIFO 10%=10.989%；父域10%/子域不限额=10.296%。[机器结果](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/f3bf18cfce246e48b985235bf7af1a45df987bcf/results/organ-backend/2026-10-16/a06-irq-safe-merged-matrix.json)。
- **受控对照：**原 WIP ELF 在1%下含 `cpu.stat` 读会超时；相同 ELF 的一次性探针仅跳过 `cpu.stat` 则 QEMU 正常退出、约2.1%。加上 IRQ 安全锁后，完整探针正常通过；N0 同时复跑了此前 8 次客体测试。历史失败记录保留下方，不再代表最新 A06 分支仍必然卡死。
- **尚未完成：**1% 实测仍约1.9–2.0%，不可宣称精确配额；SMP、cgroup迁移/生命周期、严格 lock order、HOS2 CapSpace/ioctl、Hepta 持久效果和物理硬件均未验收。main 尚无实际新内核 CPU 限额放行资格。只有继续修正 tick 超额和其他实机回归后才考虑合入 A06 主 PR。

---

## 2026-10-16 A06 实机配额阻塞与 A03 集成更新

- **新近主干改动：**A03 跨周期 `ResourceDomain::usage` 修复 [PR #16](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/16) 已合并，commit `04aacbefe037618229d4f2f0b1d4c92979abcf21`。在独立 Linux Rust 1.95.0 环境对该精确 PR HEAD `44b0cbd4ad2b88fa9dfe47aeb4f2c71803f641fd` 测得 **19/19 Cargo 测试通过**、Clippy `-D warnings` 通过、fmt 检查通过。属于宿主控制模型测试，不是内核节流实现。
- **A06 真实客体失败：**当前 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 为 Draft，HEAD `512e45d02b4ff544189b104cb36994f2edc588f4`。在它已编译的**修改后内核** `a2f72e2bc75d0490b658898697ced0532fe36395067939e3959f88dab051676e` 上，QEMU q35/TCG/1CPU/512MiB，运行一次性 guest cgroup 探针。基线 CPU `977ms / 1000.58ms`；`cpu.max=1000 100000` 写读成功、`/proc/self/cgroup` 归属正确，但客体在后续 `SYS_OPENAT/SYS_READ` 后停止前进；独立的 **45秒** 与 **15秒** 两次运行均超时。没有受限负载样本、没有 `ORGAN_PROBE_COMPLETE`、没有关机标记，故明确为 **failed_timeout**，不能计算配额符合率或认定 CPU cap 生效。
- **实测证据与沟通：**两个完整原始串口、精确 kernel SHA/guest argv、结果在授权执行宿主 `/home/qian-qi/.local/state/trillionnium-os-organ-next-20261016/a06-independent-probe/run/`，已在 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 留下失败细节与复现路径。源码定位首先检查节流队列何时在 tick 重新准入、idle 与被限线程的唤醒路径、锁顺序及未来周期唤醒；这只是待证实的故障归因，不宣称已经找到唯一根因。内核源码没有在本轮成功修改，PR #18 未合并。
- **下一真实闭环：**A06 在自己的分支修复任务长期不恢复的问题，先用同一 QEMU 探针取得受限 CPU 样本与正常关机，再测父子层级、CPU 调额不充值、非 fair 调度类、能力撤销与恢复；之后接 HOS2 ioctl 与真实 Hepta owner。独立应用和恢复服务不应受 Hepta 故障影响。

- **A06 官方 runner 的交叉复核**：独立拉取最新官方测试器 commit `7f5a3962c24d10deb8514b217a84e7c608185d45`，对同一修改后内核 ELF `a2f72e2bc75d0490b658898697ced0532fe36395067939e3959f88dab051676e` 执行 `run_candidate_matrix.py --mode leaf --quota-us 1000 --repeat 1`，得到 `qemu_exit=124`、`guest_complete=false`、`cpu_percent=null`；这是第三项独立超时。A06 的 10% 普通/FIFO/父域成功样本不能覆盖 1% 失效；该 PR 仍应保持 Draft。完整证据位于独立实验目录 `a06-official-1pct-independent/{result.json,serial-1.log}`，详细复现在 PR #18 评论。

---


## A01/A02/A03 已集成 — 2026-10-16

**主干代码基线（本段提交前）：** `c757c709652f9a9701765ff8a9e7c3026fc1019e`。这是源码与可复现验收的状态快照；不要把模块源码合入等同于 Hepta 原生 OS 可用。

| 范围 | 实际状态 |
| --- | --- |
| Asterinas 完整内核源码 | **已合入 main**：[A01 PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)，固定 v0.19.0、OSTD 和上游许可文件。 |
| QEMU 客体启动 | **已验证**：单 vCPU、q35/TCG、512 MiB、原始内核 ELF SHA256 `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63`，原产物独立重放 raw exit=33，BOOT_OK 和 CPU=1 标记成立；本次独立重放**没有**重新从源码构建。 |
| A01 OSDK 宿主回归 | **已合入 main**：[PR #15](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/15)，隔离 OSDK daemon 生命周期修复，按保留日志所列宿主单测 23/23、选定集成 13/13 通过；内核客体 362 reported、3 VMX/EPT soft skips，不代表 SMP/裸机/HOS2 验收。 |
| A03 Rust 控制模型 | **已合入 main**：[PR #12](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/12)。在合入前及合入后实际运行：1 单元测试 + 17 集成测试全部通过，严格 Clippy 通过。这是 `std` 宿主模型，**不是**内核 CapSpace/ioctl。 |
| Python HOS2 规格 | **14/14 通过**，是顺序模型，不是内核并发证明。 |
| A02 Rust no_std Wire ABI | **已合入 main**：[PR #13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13)，HOS2 2.0 no_std 字节编解码与固定 golden/negative 测试；对应 HEAD `5e3d56e0d15662b9d31f99ddf5e346796a5f6f82` 的 G0 scoped host CI 已成功，不代表内核 ioctl、CapSpace 或调度通过。 |
| 实际 CPU quota | **未执行**：一次性 Asterinas 客体内 `cpu.max=1000 100000` 写入/读回后，约 1s 墙钟仍消耗 998ms CPU。失败复现、日志和测试源码在 [PR #11](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/11) 与 [结果](../results/organ-backend/2026-10-16/)。 |
| HOS2 内核驱动/CapSpace/真实 ResourceDomain | **未实现**。A05/A06 应共用实际内核对象与调度限制，不能包装未执行的 `cpu.max`。 |
| A06/A09 实现与验收 | [A06 #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 为 Draft、尚无新内核真实 CPU 1% 配额验收；[A09 #9](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/9) 为独立 GPU/VMM 模型 PR，真实 Rust 单测仍待 GH Actions 完成。[A00 #17](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/17) 已合入硬件范围的 Rust/CPU fixture CI。 |
| Hepta 的 OS 效果 organ | **未实现**。现有 `TrustedReadOnlyOrganV1` 禁止持有控制能力或执行 I/O；观测采集和效果执行需保持在既有 owner 接合。 |
| Linux / Android / GPU / UI | 各 Agent 继续维护独立 PR；宿主测试、硬件调查、用户态原型均不计新内核端到端通过。 |

**下一条真实工作：**以主干已合入的 A02 no_std Wire ABI 与 A03 控制模型为唯一参考实现；A05 接 CapSpace/ioctl、A06 在 ClassScheduler 公共计费/资格/节流/timer 层实现真正的 CPU cap（含非 fair 类与恢复），用完全相同的已提交客体探针证伪或验证；随后 A07 沿原 Hepta authority/operations/持久 owner 完成 K↔D、历史查询/退役及故障恢复。A01 的少量测试环境问题（OSDK daemon descendant、`/proc/self/exe`）与 CPU 机制缺失分别跟踪，不以形式化总关卡阻断无关开发。

---

## 历史状态快照（保留原有记录）

## A00 实际集成快照（2026-10-16，main = c1a22de12f3d95fd49227787601169b9f42fdf12）

- **已合并源码/回归**：[PR #11](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/11)，merge c1a22de12f3d95fd49227787601169b9f42fdf12：固定 A01 内核产物的 QEMU 客体运行了真实 CPU cgroup 反例（`cpu.max=1000 100000` 写/读成功；配置后 1.000 秒使用 998ms CPU），结论 **NOT_ENFORCED**，不是成功的 CPU quota。探针只改一次性 initramfs，不修改宿主 cgroup；原始客体串口与结果在 [results/organ-backend](../results/organ-backend/2026-10-16/)。对应 Python newc/archive 测试普通和 -O 各 5/5 通过。该 PR 不实现内核节流。
- **主干真实边界**：当前 main 尚未导入 `kernel/asterinas`，也无 `libs/os-abi` 或 `libs/os-control`（A01 [PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)、A02 [PR #13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13)、A03 [PR #12](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/12) 仍未合并）。A01 分支拥有 Rust 源码构建、QEMU boot 和 OSTD/aster-core 客体测试证据，但主干不继承分支验收。A02/A03 的 host Rust 测试不得记作内核 ioctl、权限或调度验证。
- **未解决**：A01 lock/source 验证与 OSDK 主机测试失败；A02 capability bit 依赖；A03 owner-ack 与跨周期核算；真实 A05/A06 CPU 限额执行及 A07 Hepta owner 到内核效果闭环。原 Hepta 操作 owner 仍是唯一持久事实来源；不得建立第二份 K 账本。
- **CI**：原定向 G0 工作流 GitHub Actions 仍处于排队状态，不能标记 pass。本轮仅在同一工作流中增加已合并的 `tests/organ_backend` 宿主安全回归，绝不将其视作 QEMU 验收。根 `README.md` 保持严格 0 字节，Asterinas/Hepta pin 未改。

---


> **A00 集成增量（2026-10-16，原文历史记录保留）**：从实际 main 3cc2f810eda93dab7411b62ef2f8f3830fbb1500 验证并合并 [A02 PR #1](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/1)，合并提交 3cc2f810eda93dab7411b62ef2f8f3830fbb1500；三份 N0 单 CPU 黄金样本时间修正：ReadUsage 125ms 时 consumed=25ms（降低后的 cap=20ms），InstallBudget 与 QueryDelivery 在 123ms 生效点 consumed=23ms。独立 Python struct 生成器 --check 检验 12 份样本，宿主 Python 格式/变异测试 6/6 通过；此前 14 场景顺序模型仍是模型，不是内核。A00 增加单条按路径触发的宿主契约 CI，Rust 项仅在对应 crate 存在时执行；记录的执行结果以真实 GitHub Actions 为准。尚无 Rust ABI / ResourceDomain 内核实现、项目 QEMU 新内核启动或 Hepta 端到端结果。原 Hepta 持久 operation owner 不变。根 README 0 字节。

2026-10-16；修订基线 `46a0e9f9ffa0e8289d0a1324d5dd8c9e6d6b7544`。本轮交付为 **recovery_contracts_and_spec_tests**，不是Rust内核实现。

## 已实际完成

围绕V201–V217修订关键文档，HOS2明确启动授权交接、CapSpace全局投递预约、独立DeliveryView、只读历史查询、有序写序列与连续结果退役。预算目标收敛不伪造旧操作终态；恢复责任不依赖Hepta自身健康；真实调度类、计时和计费点列为下一实现接合。

新增Python顺序规格场景，工作容器与执行主机分别运行同一源码SHA256 `8162883270a153ebf81f2cd4e0e05392c957fb439cfbb481239b35d75cab68de`，均为14测试、0失败、0错误、0跳过。10,000写/退役发生在模型内，不是内核benchmark；模型不提供并发或实际权限证明。[结果](../results/spec-recovery-v03.json)

新增12份独立Python struct生成的HOS2十六进制黄金样本，覆盖五操作请求/响应、历史退役和CAS拒绝；只核算布局，没有Rust codec消费这些样本。[样本](../tests/golden/hos2.json)

## 未完成与本轮实际阻塞

Rust库源码写入再次被执行通道安全检查拦截，工具仅报告无法确定请求安全状态。没有重放同一源码写入，也没有改权限或绕过检查。已确认无`.rs`文件；此前成功创建但没有实现对应的临时Cargo.toml已移除，不把空工程算交付。规格测试是独立的文档模型，不是被拒Rust编解码库的替代实现。

官方v0.19.0安装ISO下载在180秒上限内只获得74,026,432/1,442,840,576字节，curl退出28。完整文件未校验，未启动QEMU；部分文件的大小/摘要已记录后清理。执行主机检测到QEMU 8.2.2及可访问KVM，但这些不构成客体启动。[失败记录](../results/reference-iso-probe.json)

## 能力状态

| 范围 | 实际状态 |
| --- | --- |
| 文档恢复契约 | revised，待代码实现 |
| 顺序规格模型 | 14 passed；非内核/非并发 |
| 固定字节样本 | 12份；codec未测试 |
| Rust ABI库/普通客户端 | not_implemented；source_write_blocked |
| Asterinas源码导入/源码构建 | not_executed |
| 官方ISO完整下载/校验 | failed_timeout/not_verified |
| QEMU/裸机内核启动 | not_executed |
| Hepta端到端/Linux/Android/GPU/UI | not_tested |
| CI与生产资格 | not_claimed |

根README保持0字节；不再次删除仓库，不改hepta-private-ci、现役服务或硬件。source pin仍不等于完整build lock；upstream-lock中缺项和false保留。

## 下一项真实交付

优先完成获得执行允许的Rust源码写入及黄金向量测试，或补齐固定上游源码构建与真实串口启动结果；不能因这些规格场景通过就推进M1a/M1b实现状态。并行/设备/前驱恢复仍需对应真实环境，未决项不标为关闭。
