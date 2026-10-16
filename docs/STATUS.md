# 当前状态

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
