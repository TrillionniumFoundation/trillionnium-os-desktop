# 开发文档入口

文档入口更新于 2026-10-17；ABI 契约文档修订仍为 0.3，HOS2 wire 仍为 2.0。根 README.md 保持 0 字节；开发内容只在 docs 与明确源码/支持目录中。当前实现与执行证据见 [STATUS](STATUS.md)，历史记录只适用于各自固定的源码。

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

本次文档基于 main `561f1e276cc02fd7a257b8f804488546ab3d2a83`，已包含普通合并的 [A08 #161](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/161)；其源码组合与执行身份见 [组合收据](../results/integration/a08-host-main-20261017/README.md)。A07/A10 最终固定候选为 `5beb3fab54fe7dd60072864276ece1ced38150ab`，仍在 [Draft #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157)；新中文切片与原版编译检查分别绑定自己的源码，见 [STATUS](STATUS.md)。下表将开发入口、技术契约和验收来源放在一起；标为候选的代码及文档尚未合入 main，不能从主干的相对路径假定它们已存在。

| 模块 / owner | 开发与验证入口 | 技术契约 / 实际范围 |
| --- | --- | --- |
| A00 集成 | [PLAN](agents/PLAN.md)、[STATUS](STATUS.md) | [ARCHITECTURE](ARCHITECTURE.md)、[DECISIONS](DECISIONS.md)；统一接口与集成 |
| A01 源码 / 启动 | [构建手册](../support/build/README.md)、[内核测试入口](../support/build/ktest/README.md) | [固定来源](../support/upstream-lock.json)；固定 Asterinas、OSDK、initramfs 与证据 |
| A02 HOS2 codec | [验收收敛与实际命令](../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md)、[证据完整性](../tests/abi/A02_EVIDENCE_INTEGRITY_2026-10-17.md) | [NATIVE_ABI](NATIVE_ABI.md)、[codec 源码](../libs/os-abi/src/lib.rs)；wire 实现不等于全部内核操作实现 |
| A03 control core | [验证手册](../tests/control/VALIDATION.md)、[运行脚本](../tests/control/run-validation.sh) | [API_CONTRACT](../libs/os-control/API_CONTRACT.md)；真实 Rust 库 / 宿主模型，内核 IRQ/SMP 接合仍需验证 |
| A04 Linux / Hepta ELF | [固定候选开发手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/tests/workloads/linux/README.md)、[rootfs 手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/support/rootfs/README.md) | [LINUX_COMPATIBILITY](LINUX_COMPATIBILITY.md)、[候选缺口](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/compat/linux/GAPS.md)；代码在 [Draft #8](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/8) |
| A05 内核控制 | [实现、构建与调试手册](agents/handoffs/A05_KERNEL_CONTROL.md) | [NATIVE_ABI](NATIVE_ABI.md)；main 已有 QueryAbi 的 Process / exec 镜像身份隔离；能力授予和其余四操作未闭合 |
| A06 CPU 预算 | [CPU 实现及客体验证](ASTERINAS_CPU_BANDWIDTH_N0.md)、[已集成收据](../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json) | [资源 backend 接合](ASTERINAS_ORGAN_BACKEND.md)；N0 配额已执行，最终计费 / IRQ / SMP 不能继承有限样本资格 |
| A07 Hepta 用户态接合 | [client 开发入口](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/services/hepta-os/README.md)、[技术契约](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/services/hepta-os/CONTRACT.md)、[运行与验证](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/services/hepta-os/RUN.md)、[原版 Agentd 门禁](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/tests/integration/hepta/ORIGINAL_AGENTD.md)、[原版编译检查与14份原始记录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/tests/integration/hepta/evidence/2026-10-17-original-probe/README.md)、[构建来源与资源边界](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/tests/integration/hepta/BUILD_REVIEW.md)，[候选 #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157) | [HEPTA_INTEGRATION](HEPTA_INTEGRATION.md)；历史只读 observer 17 项与进程守卫 6 项分别保留原源码；本轮 resolver 3 项、原版 probe metadata/锁核验与 probe/Agentd 本体 Cargo check 已完成。链接 ELF、原版 live gate 和 durable owner 效果接合未完成；新实录见 [STATUS](STATUS.md) |
| A08 Android | [开发手册](../support/android/README.md)、[来源绑定与 184 项回归](../tests/workloads/android/evidence/2026-10-17-commit-bound-audit/README.md)、[main 组合实际验收](../results/integration/a08-host-main-20261017/README.md) | [ANDROID_COMPATIBILITY](ANDROID_COMPATIBILITY.md)、[接口技术契约](../compat/android/INTERFACES.md)、[内核缺口](../compat/android/kernel-gaps.json)；已整合源码和 Linux host 工具，Binder/seccomp/MAC 与 Android guest 资格未通过 |
| A09 硬件 / VMM | [device lifecycle 开发手册](../support/vmm/device_lifecycle/README.md)、[GATES](../support/vmm/GATES.md) | [HARDWARE_AND_DRIVERS](HARDWARE_AND_DRIVERS.md)、[来源](../support/vmm/PROVENANCE.md)；宿主元数据模型不等于真实 DMA/GPU |
| A10 Rust UI | [运行手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/support/ui/RUN.md)、[Session/Hepta 接合手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/support/ui/HEPTA_OBSERVER.md)、[字体/像素/输入开发手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/support/ui/CJK_RENDERING.md)、[15 条定向测试与实际中文 PNG](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/661c958650e187cf677e4d5351d87e8bc8badbc5/tests/ui/evidence/2026-10-17-cjk-pixman/README.md)、[历史 137 项与 no-op Weston](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/e743ee1a06956b51f86c16887f04cd4f518bcccd/tests/ui/evidence/2026-10-17-rust188-owner-sync)，[候选 #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157) | [DESKTOP_UX](DESKTOP_UX.md)；Rust 1.88 / eframe 0.31.1 的 Linux host 原型。新 Shell/Notes 中文软件像素通过，Session/ctl 仍复用旧产物；原版 Agentd 数据源、真实 IME/GPU、Asterinas 和移动端未通过 |

模块有文档链接不等于模块已经完成。每个新可交接增量至少给出实际源码位置、依赖与固定版本、构建/运行命令、输入输出和错误语义、权限与状态 owner、真实测试及未通过项。只列 Agent prompt 或未来架构图不能代替这些内容。A05 已补上实现手册；A07/A10 候选已有实际连接配置、协议边界、断连与窗口恢复语义、可复跑 socket fixture、原版 Agentd 预检/启动门禁及其进程清理回归；本轮另有字体配置/失败语义/真实像素复跑手册，以及原版 probe 和 Agentd 本体的实际 Cargo 检查。原生 AI UI 的事实来源、可信意图入口和逐阶段交付见 [DESKTOP_UX 第 6 节](DESKTOP_UX.md#6-以-hepta-为核心的-ai-原生-ui)；后续原生效果与设备适配仍需对应实现文档。

## 多 Agent 并行开发

[并行开发执行方案](agents/PLAN.md) · [独立可复制的各 Agent Prompts](agents/PROMPTS.md)。职责与验收以这些文档为准，不改变现有内核实现状态。
