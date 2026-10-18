# 开发文档入口

文档入口更新于 2026-10-18；ABI 契约文档修订仍为 0.3，HOS2 wire 仍为 2.0。根 README.md 保持 0 字节；开发内容只在 docs 与明确源码/支持目录中。当前实现与执行证据见 [STATUS](STATUS.md)，历史记录只适用于各自固定的源码。

## 共同原则

新Rust内核管理硬件，Hepta沿现有单一智能/工具主链成为用户态原生系统服务。Linux/Android是兼容生态，VM明确标记补缺。模型不持根权限，内核快速路径与本地恢复不等待模型/远程控制。

本文中的契约和算法是实现规格，不是运行证据。source pin、格式检查、规格模型、codec、内核/硬件与产品验收分层报告。已有授权范围内自动执行，不增加重复审批、证据服务或空壳workflow；权限、资源、结果和恢复检查属于实际运行机制。

## 阅读与实施顺序

| 文档 | 主要内容 |
| --- | --- |
| [PROJECT](PROJECT.md) | 原生定义、profile、W0–W5应用与交付 |
| [ARCHITECTURE](ARCHITECTURE.md) | 完整Asterinas派生、真实源码接合、同对象与并发 |
| [NATIVE_ABI](NATIVE_ABI.md) | HOS2五操作、启动交接、全局预约、历史观察与退役的唯一规格 |
| [HEPTA_INTEGRATION](HEPTA_INTEGRATION.md) | 真实源码符号/profile、状态owner、控制器 |
| [SECURITY_AND_RECOVERY](SECURITY_AND_RECOVERY.md) | TCB、熵/时钟、S0/S1存储、更新与故障 |
| [LINUX_COMPATIBILITY](LINUX_COMPATIBILITY.md) | 必需接口、rootfs和应用交付、差分 |
| [ANDROID_COMPATIBILITY](ANDROID_COMPATIBILITY.md) | 产品/VINTF/MAC/Binder/页大小与代理边界 |
| [HARDWARE_AND_DRIVERS](HARDWARE_AND_DRIVERS.md) | DMA/队列/复位与提前风险调查 |
| [DESKTOP_UX](DESKTOP_UX.md) | Rust/Wayland/分域Xwayland/Android桥 |
| [ROADMAP](ROADMAP.md) | 明确M0/M1/M2依赖及下一次真实实现 |
| [VALIDATION](VALIDATION.md) | 判定器、注入层级、22项审计映射 |
| [DECISIONS](DECISIONS.md) | 默认路线与重议条件 |
| [STATUS](STATUS.md) | 本轮实际执行、未完成项 |
| [SOURCES](SOURCES.md) | 一手来源与固定快照 |
| [upstream-lock](../support/upstream-lock.json) | 已核查源码与参考资产、显式缺失构建输入 |

每次后续改动直接修改对应契约和状态，不重复复制ABI字段或完成度。旧仓库重建历史保留在Git初始提交；不混入永久产品要求。

最初的[恢复规格场景](../tests/spec/test_recovery_contract.py)、[固定字节样本](../tests/golden/hos2.json)与[规格模型结果](../results/spec-recovery-v03.json)是历史规格证据。当前主干另有真实 [Rust codec](../libs/os-abi/src/lib.rs)、[control core API](../libs/os-control/API_CONTRACT.md)、原生 QueryAbi 和 CPU 配额实现；对应宿主或 QEMU 证据分别见下表。规格版本不表示整个系统的完成比例。

## 按模块开始开发

本次集成在 main 66ade4cbbe1e8d8319652d870c6c773c5efd8206 的文档盘点上继续更新，保留 A08、既有 A06/A02 和 [A02/A03 #185](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/185) 的完整历史。A02 的完整 pinned 验收、A03 两种后端与有界并发/分配验证、G0 原 run block 的执行和复用记录见[本轮证据索引](../results/integration/2026-10-18-audit-followthrough/README.md)；当前源码与实际执行身份分别列出，不以文档提交替代测试来源。

A07/A10 的源码与开发手册已通过 [PR #187](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/187) 合入 main 9a858dceb3a0ede6c3a021b9d16f3bf41e8503d5。实际 UI 测试对象为 be335eba60f9a511a78ff8e3af90a043d50855e2，完整 host 151 passed / 2 既有 CJK ignored，严格检查和软件 Wayland 生命周期通过；具体资格见 [STATUS](STATUS.md)，不等于物理设备或原生目标 OS 验收。#157 已因源码完整纳入主干而关闭，和 R6 固定候选 89aa8fa62d30b00259cb33174260c134edf1a70b 一起保留为历史开发与归档入口。A06 最终代码的完整 aster-core 正向、受控负对照和固定配置的 1/2 vCPU N0 probe 已执行，具体源码与资格见下表及本轮索引。

R6 的两轮原版 → 持续 Session → 同一 Rust Shell 六阶段链路是 2026-10-17 的真实执行，本轮只独立复核其归档，见 [R6 完整交付索引](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-r6/README.md)。下表保留全部 A00–A10 的开发入口、技术契约和资格边界；历史证据的固定提交链接继续保留。

| 模块 / owner | 开发与验证入口 | 技术契约 / 实际范围 |
| --- | --- | --- |
| A00 集成 | [PLAN](agents/PLAN.md)、[STATUS](STATUS.md) | [ARCHITECTURE](ARCHITECTURE.md)、[DECISIONS](DECISIONS.md)；统一接口与集成 |
| A01 源码 / 启动 | [构建手册](../support/build/README.md)、[内核测试入口](../support/build/ktest/README.md) | [固定来源](../support/upstream-lock.json)；固定 Asterinas、OSDK、initramfs 与证据 |
| A02 HOS2 codec | [验收收敛与实际命令](../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md)、[证据完整性](../tests/abi/A02_EVIDENCE_INTEGRITY_2026-10-17.md)、[本轮 pinned 验收](../results/integration/2026-10-18-audit-followthrough/README.md#a02) | [NATIVE_ABI](NATIVE_ABI.md)、[codec 源码](../libs/os-abi/src/lib.rs)；#181/#185 已闭合 N0 prior-window、QueryDelivery 终态/保留序号与独立 Python 判定器边界。本轮完整 pinned 验收 13/13，Python ABI 62 项；wire 实现不等于全部内核操作实现。 |
| A03 control core | [验证手册](../tests/control/VALIDATION.md)、[运行脚本](../tests/control/run-validation.sh)、[本轮双后端与证据复核](../results/integration/2026-10-18-audit-followthrough/README.md#a03) | [API_CONTRACT](../libs/os-control/API_CONTRACT.md)；#185 已合入 original-owner authority 绑定的 namespace receipt 与不复用 instance tag。本轮 std / portable-spin 各 225 项，Loom 19 个模型 / 27,253 个调度，19 个锁内分配场景的 alloc/realloc/dealloc 均为零；durable K/fsync 和内核 IRQ/SMP 接合仍未因此通过。 |
| A04 Linux / Hepta ELF | [固定候选开发手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/tests/workloads/linux/README.md)、[rootfs 手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/support/rootfs/README.md) | [LINUX_COMPATIBILITY](LINUX_COMPATIBILITY.md)、[候选缺口](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/compat/linux/GAPS.md)；代码在 [Draft #8](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/8) |
| A05 内核控制 | [实现、构建与调试手册](agents/handoffs/A05_KERNEL_CONTROL.md) | [NATIVE_ABI](NATIVE_ABI.md)；main 已有 QueryAbi 的 Process / exec 镜像身份隔离；能力授予和其余四操作未闭合 |
| A06 CPU 预算 | [CPU 实现及客体验证](ASTERINAS_CPU_BANDWIDTH_N0.md)、[既有集成收据](../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json)、[本轮实际执行与来源](../results/integration/2026-10-18-audit-followthrough/README.md) | [资源 backend 接合](ASTERINAS_ORGAN_BACKEND.md)；[#188](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/188) 的 zombie 尾账修复已在 e97a30c923b1a27e1578eaaf6b39d85fe1aa5591 / tree c70e97c30b6a7808586c1a2a7db4a6860ede004e 实测，同树发布为 9265235c4b4f375844c923cf0b0f517d119d9937，已合入 main 8ea35f55a38949f511f0855cd168dfd1d672acc8。完整 aster-core 159/159；负对照 157 passed / 2 expected fail。新生产 ELF 的 1/2 vCPU 各两轮固定 1% 配额 probe 均通过既有 3% 上界，双核并行 baseline 通过；一般迁移/退出交错、IRQ/SMP 和 Hepta/HOS2 不随上述有限运行自动取得资格。 |
| A07 Hepta 用户态接合 | [client 开发](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/services/hepta-os/README.md)、[技术契约](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/services/hepta-os/CONTRACT.md)、[运行与验证](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/services/hepta-os/RUN.md)、[持续原版 Session](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/ORIGINAL_SESSION.md)、[外部锁稳定性](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/PROBE_LOCK_STABILITY.md)、[实际入口与错误语义](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/LIVE_SOURCE_REVIEW.md)、[三轮原版 / Session 运行](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-original-session-runtime/README.md)、[原版消费者构建与锁诊断](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-original-session-build/README.md)、[84e 原版 ARM 持续 Session 实录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-84e-arm-ci/README.md) | [HEPTA_INTEGRATION](HEPTA_INTEGRATION.md)；固定原版 → 持续 Session → 真实 Shell 两轮各六阶段已验收，ARM 持续 Session 另有 8 + 8 实录。可信 ObjectiveStart 尚未接通，SubmitUnknown / RunStatus null 边界已核对；durable K↔D、撤销、退役和设备效果仍待闭合；上述两轮六阶段为 2026-10-17 原始运行，本轮完成归档独立复核，没有新的原版运行时执行。 |
| A08 Android | [开发手册](../support/android/README.md)、[来源绑定与 184 项回归](../tests/workloads/android/evidence/2026-10-17-commit-bound-audit/README.md)、[main 组合实际验收](../results/integration/a08-host-main-20261017/README.md) | [ANDROID_COMPATIBILITY](ANDROID_COMPATIBILITY.md)、[接口技术契约](../compat/android/INTERFACES.md)、[内核缺口](../compat/android/kernel-gaps.json)；已整合源码和 Linux host 工具，Binder/seccomp/MAC 与 Android guest 资格未通过 |
| A09 硬件 / VMM | [device lifecycle 开发手册](../support/vmm/device_lifecycle/README.md)、[GATES](../support/vmm/GATES.md) | [HARDWARE_AND_DRIVERS](HARDWARE_AND_DRIVERS.md)、[来源](../support/vmm/PROVENANCE.md)；宿主元数据模型不等于真实 DMA/GPU |
| A10 Rust UI | [运行手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/support/ui/RUN.md)、[Session / Hepta 接合](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/support/ui/HEPTA_OBSERVER.md)、[原版真实窗口复跑](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/support/ui/ORIGINAL_HEPTA_SHELL.md)、[新鲜度开发与技术契约](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/ui/shell/OBSERVATION_FRESHNESS.md)、[字体与渲染](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/support/ui/CJK_RENDERING.md)、[XIM 复跑与边界](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/support/ui/X11_IME.md)、[13 张原图、快照、ACK 与逐图审查](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-original-hepta-shell/README.md)、[完整 RED/GREEN 与编译来源](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-observation-freshness/README.md)、[CI 步骤与实际本地执行](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-original-shell-ci/README.md) | [DESKTOP_UX](DESKTOP_UX.md)；Rust 1.88 / eframe 0.31.1 的 Linux host 原生程序。两轮原版六阶段窗口与可见新鲜度修复已通过；历史 UID、中文软件像素、XIM 输入保留各自来源。聊天 / 任务工作区继续迭代；候选 caret 定位仍失败，Wayland 输入、GPU、Asterinas 和移动端未通过；#187 已合入，本轮 be335eba 的完整 host 151 passed / 2 既有 CJK ignored，严格检查及软件 Wayland 布局/生命周期通过；未验证 compositor 像素、IME、物理显示/GPU 或目标 OS，不从 R6 历史成功推定。 |

模块有文档链接不等于模块已经完成。每个可交接增量至少给出实际源码位置、依赖与固定版本、构建/运行命令、输入输出和错误语义、权限与状态 owner、真实测试及未通过项。只列 Agent prompt 或未来架构图不能代替这些内容。A05 已有实现手册；A07/A10 已合入的源码与随附手册已有连接配置、持续 worker、来源换代和断连语义、原版进程门禁、真实窗口复跑、外部锁诊断、观测过期、字体/输入与进程清理文档，附实际失败和成功记录。文档覆盖全部模块，内核效果、Android guest、硬件与移动 UI 的运行资格仍按各自证据判定。原生 AI UI 的事实来源、可信意图入口和下一步工作区设计见 [DESKTOP_UX 第 6 节](DESKTOP_UX.md#6-以-hepta-为核心的-ai-原生-ui)。

## 多 Agent 并行开发

[并行开发执行方案](agents/PLAN.md) · [独立可复制的各 Agent Prompts](agents/PROMPTS.md)。职责与验收以这些文档为准，不改变现有内核实现状态。
