# 当前状态

## A01/A03 已集成 — 2026-10-16

**主干代码基线（本段提交前）：** `c757c709652f9a9701765ff8a9e7c3026fc1019e`。这是源码与可复现验收的状态快照；不要把模块源码合入等同于 Hepta 原生 OS 可用。

| 范围 | 实际状态 |
| --- | --- |
| Asterinas 完整内核源码 | **已合入 main**：[A01 PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)，固定 v0.19.0、OSTD 和上游许可文件。 |
| QEMU 客体启动 | **已验证**：单 vCPU、q35/TCG、512 MiB、原始内核 ELF SHA256 `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63`，原产物独立重放 raw exit=33，BOOT_OK 和 CPU=1 标记成立；本次独立重放**没有**重新从源码构建。 |
| A03 Rust 控制模型 | **已合入 main**：[PR #12](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/12)。在合入前及合入后实际运行：1 单元测试 + 17 集成测试全部通过，严格 Clippy 通过。这是 `std` 宿主模型，**不是**内核 CapSpace/ioctl。 |
| Python HOS2 规格 | **14/14 通过**，是顺序模型，不是内核并发证明。 |
| A02 Rust no_std Wire ABI | [PR #13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13) **仍待合并**。独立测试、`cargo check --no-default-features`、12 黄金字节与 12 项 Python 反例通过；严格 Clippy 仍有 `possible_missing_else`，`cargo fmt --check` 仍失败，已在 PR 反馈。不要冒称完全 green。 |
| 实际 CPU quota | **未执行**：一次性 Asterinas 客体内 `cpu.max=1000 100000` 写入/读回后，约 1s 墙钟仍消耗 998ms CPU。失败复现、日志和测试源码在 [PR #11](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/11) 与 [结果](../results/organ-backend/2026-10-16/)。 |
| HOS2 内核驱动/CapSpace/真实 ResourceDomain | **未实现**。A05/A06 应共用实际内核对象与调度限制，不能包装未执行的 `cpu.max`。 |
| Hepta 的 OS 效果 organ | **未实现**。现有 `TrustedReadOnlyOrganV1` 禁止持有控制能力或执行 I/O；观测采集和效果执行需保持在既有 owner 接合。 |
| Linux / Android / GPU / UI | 各 Agent 继续维护独立 PR；宿主测试、硬件调查、用户态原型均不计新内核端到端通过。 |

**下一条真实工作：**完成 A02 已验证问题的窄修复并集成；A05 接 CapSpace/ioctl、A06 在 ClassScheduler 公共计费/资格/节流/timer 层实现真正的 CPU cap（含非 fair 类与恢复），用完全相同的已提交客体探针证伪或验证；随后 A07 沿原 Hepta authority/operations/持久 owner 完成 K↔D、历史查询/退役及故障恢复。A01 的少量测试环境问题（OSDK daemon descendant、`/proc/self/exe`）与 CPU 机制缺失分别跟踪，不以形式化总关卡阻断无关开发。

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
