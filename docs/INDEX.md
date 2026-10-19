# 开发文档入口

文档入口更新于 2026-10-19；ABI 契约文档修订仍为 0.3，HOS2 wire 仍为 2.0。根 README.md 保持 0 字节；开发内容只在 docs 与明确源码/支持目录中。当前实现与执行证据见 [STATUS](STATUS.md)，历史记录只适用于各自固定的源码。

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
| [R8_NEXT_SLICE](agents/R8_NEXT_SLICE.md) | 已有 issuer、持久核对、受限 OS adapter 与 Asterinas G1/G2 的具体下一工单 |
| [R9_G1_OWNER_SEAM](agents/R9_G1_OWNER_SEAM.md) | 固定实际 CPU owner 的共享 revision、控制器 incarnation、锁序和 BOOTTIME 接缝；源审计，不是新内核运行资格 |
| [Objective history 开发与技术契约](../services/hepta-os/OBJECTIVE_HISTORY.md) | 独立原 owner 历史查询、保留请求与 anchor、有限结果、CLI 和验证边界 |
| [SOURCES](SOURCES.md) | 一手来源与固定快照 |
| [upstream-lock](../support/upstream-lock.json) | 已核查源码与参考资产、显式缺失构建输入 |

每次后续改动直接修改对应契约和状态，不重复复制ABI字段或完成度。旧仓库重建历史保留在Git初始提交；不混入永久产品要求。

最初的[恢复规格场景](../tests/spec/test_recovery_contract.py)、[固定字节样本](../tests/golden/hos2.json)与[规格模型结果](../results/spec-recovery-v03.json)是历史规格证据。当前主干另有真实 [Rust codec](../libs/os-abi/src/lib.rs)、[control core API](../libs/os-control/API_CONTRACT.md)、原生 QueryAbi 和 CPU 配额实现；对应宿主或 QEMU 证据分别见下表。规格版本不表示整个系统的完成比例。

## 按模块开始开发

当前 R9 补齐 Runtime 的成功样本时钟与 Shell 总年龄判定，最终 UI workspace 137 passed / 0 failed / 2 CJK ignored、严格检查和四程序构建通过；新增两个真实 CLI 终止边界，完整 objective feature suite 43 passed。A04 增加主干交接手册，A06 补实际 cpu.max 与 owner 入口，见 [R9 源码与原始证据](../results/integration/2026-10-18-runtime-process-boundaries/README.md)。Schema 新字段需要 Session/Shell/ctl 配套部署；原版、像素和设备资格仍按下述独立来源判定。

2026-10-19 合入实际 main 的原 owner history 扩展后，完整组合重新得到 UI 137 passed / 2 既有 ignored、Hepta all-features 53 passed、严格检查和七 ELF 构建通过。另修复成功进程 leader 提前回收后仍遗留同组 writer 的实际缺陷，保留双 RED、GREEN 与 47 项 Python 结果；归档旧 HEAD 的 ARM 清理失败、实际两页 Rust 工作区原图，以及独立固定 history owner 的已执行 CI。来源和新旧资格见 [整合证据](../results/integration/2026-10-19-main-sync/README.md)，新发布 HEAD 的 CI 不沿用旧结论。

R9 在原 owner 独立扩展上增加已知请求的在线准入历史查询；模块开发与技术入口见 [history 契约](../services/hepta-os/OBJECTIVE_HISTORY.md)，真实故障复跑见 [history probe](../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)。当前实际测试与未完成门禁以 [STATUS](STATUS.md) 最上方轮次为准。内核侧按 [G1 owner 接缝审计](agents/R9_G1_OWNER_SEAM.md) 先统一 revision 与控制器身份，再接可信初始化。以下 R8/R6 保留自己的固定证据。

A06 的 [本地 CPU 配置前结算](../tests/organ_backend/CPU_CONFIG_SETTLEMENT.md) 给出原 runqueue/owner 锁序、带宽游标、四个确定性内核回归，以及 100 ms / 2 ms 两个周期的只读和同值写入客体验证命令。该增量保留原计费 owner；文档分别列出实际执行要求与尚未完成的 BOOTTIME、同版本使用量、控制器代际和 SMP 接合，不据此宣告全部 G1-b 完成。

A04 的 [RLIMIT_NOFILE 开发与技术手册](../tests/workloads/linux/RLIMIT_NOFILE.md) 说明原 FileTable 的 FD 预约、调用进程 soft limit、并发/错误语义、37 项差分 probe 和严格同 ELF 运行命令；[固定 Linux 成功与旧内核失败归档](../results/compat/2026-10-19-rlimit-nofile/README.md) 保留完整原始字节、实际退出码和早期失败。该新增 profile 与旧 Debian 13 全套资格分别记录，修复后的普通内核必须在同一组合源码上重新验收。

已合入 R8 的实际集成输入为 `25298f5d87cf3db90deefe9c0405ecd241dc6581`，同树发布 `ca5e7d8473690df1bf7636de0808e58414c40abe` / tree `9584997da412dd10c0960f69011b40a4b26d2862`，[PR #192](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/192) 纳入 #190 工作区候选及 #191 主干修复的完整历史。[R8 实际证据](../results/integration/2026-10-18-objective-desktop/README.md) 记录独立 CLI、两次原版准入运行、后一次的三个 Session/同一 Shell 阶段与三张实际截图；[R8 ARM 完成复核](../results/integration/2026-10-18-runtime-process-boundaries/r8-arm-completion/README.md) 另绑定 `05a7cd23` / run `39106645234` 的实际 success。默认 observer/Session/Shell 继续只读；隔离测试 issuer 的通过不代替生产 issuer 或设备效果。

上一轮 #185/#187/#188/#189 的 A02 完整 pinned 验收、A03 双后端及有界并发、G0 和 A06 客体 1/2 vCPU 有限配置证据见 [audit-followthrough 索引](../results/integration/2026-10-18-audit-followthrough/README.md)。R6 两轮原版只读六阶段窗口属于 2026-10-17 实际运行，见 [R6 历史归档](../tests/integration/hepta/evidence/2026-10-17-r6/README.md)；旧测试计数和源码不转记给本轮。下面保留全部 A00–A10 的当前开发入口、技术契约和各自资格。

下表的 control core 验证属于宿主模型与有界并发检查；其 durable K/fsync 接合尚未闭合，内核 IRQ/SMP 接合仍需验证。A05 的实际内核入口仍按 QueryAbi 与各项效果操作分别判定，不能从宿主通过推定内核效果可用。

| 模块 / owner | 开发与验证入口 | 技术契约 / 实际范围 |
| --- | --- | --- |
| A00 集成 | [PLAN](agents/PLAN.md)、[STATUS](STATUS.md) | [ARCHITECTURE](ARCHITECTURE.md)、[DECISIONS](DECISIONS.md)；统一接口与集成 |
| A01 源码 / 启动 | [构建手册](../support/build/README.md)、[内核测试入口](../support/build/ktest/README.md) | [固定来源](../support/upstream-lock.json)；固定 Asterinas、OSDK、initramfs 与证据 |
| A02 HOS2 codec | [验收收敛与实际命令](../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md)、[证据完整性](../tests/abi/A02_EVIDENCE_INTEGRITY_2026-10-17.md)、[本轮 pinned 验收](../results/integration/2026-10-18-audit-followthrough/README.md#a02) | [NATIVE_ABI](NATIVE_ABI.md)、[codec 源码](../libs/os-abi/src/lib.rs)；#181/#185 已闭合 N0 prior-window、QueryDelivery 终态/保留序号与独立 Python 判定器边界。本轮完整 pinned 验收 13/13，Python ABI 62 项；wire 实现不等于全部内核操作实现。 |
| A03 control core | [验证手册](../tests/control/VALIDATION.md)、[运行脚本](../tests/control/run-validation.sh)、[本轮双后端与证据复核](../results/integration/2026-10-18-audit-followthrough/README.md#a03) | [API_CONTRACT](../libs/os-control/API_CONTRACT.md)；#185 已合入 original-owner authority 绑定的 namespace receipt 与不复用 instance tag。本轮 std / portable-spin 各 225 项，Loom 19 个模型 / 27,253 个调度，19 个锁内分配场景的 alloc/realloc/dealloc 均为零；durable K/fsync 和内核 IRQ/SMP 接合仍未因此通过。 |
| A04 Linux / Hepta ELF | [构建、验证与主干交接](agents/handoffs/A04_LINUX_HEPTA_ELF.md)、[SCM_RIGHTS/CLOEXEC 实现及 27 项验证](../tests/workloads/linux/SCM_RIGHTS_CLOEXEC.md)、[固定候选开发手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/tests/workloads/linux/README.md)、[rootfs 手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/support/rootfs/README.md) | [LINUX_COMPATIBILITY](LINUX_COMPATIBILITY.md)、[候选缺口](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/compat/linux/GAPS.md)；实现仍在 [Draft #8](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/8)，主干交接手册不代表代码或完整同 ELF guest 验收已合入。 |
| A05 内核控制 | [实现、构建与调试手册](agents/handoffs/A05_KERNEL_CONTROL.md) | [NATIVE_ABI](NATIVE_ABI.md)；main 已有 QueryAbi 的 Process / exec 镜像身份隔离；能力授予和其余四操作未闭合 |
| A06 CPU 预算 | [CPU 实现及客体验证](ASTERINAS_CPU_BANDWIDTH_N0.md)、[cpu.max 输入契约与复跑](../tests/organ_backend/CPU_MAX_CONFIG.md)、[既有集成收据](../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json)、[本轮实际执行与来源](../results/integration/2026-10-18-audit-followthrough/README.md) | [资源 backend 接合](ASTERINAS_ORGAN_BACKEND.md)；[#188](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/188) 的 zombie 尾账修复已在 e97a30c923b1a27e1578eaaf6b39d85fe1aa5591 / tree c70e97c30b6a7808586c1a2a7db4a6860ede004e 实测，同树发布为 9265235c4b4f375844c923cf0b0f517d119d9937，已合入 main 8ea35f55a38949f511f0855cd168dfd1d672acc8。完整 aster-core 159/159；负对照 157 passed / 2 expected fail。新生产 ELF 的 1/2 vCPU 各两轮固定 1% 配额 probe 均通过既有 3% 上界，双核并行 baseline 通过；一般迁移/退出交错、IRQ/SMP 和 Hepta/HOS2 不随上述有限运行自动取得资格。 另 [#191 奇数周期 oracle](../results/organ-backend/2026-10-18/a06-odd-period-oracle/README.md) 仅改 cfg(ktest)，生产函数字节不变；新完整 aster-core 160/160，OSTD 报告 221 passed 含 3 soft skip。其 merge 三项 CI 已成功，不新增生产 ELF/SMP 资格。 |
| A07 Hepta 用户态接合 | [client 开发](../services/hepta-os/README.md)、[只读契约](../services/hepta-os/CONTRACT.md)、[运行手册](../services/hepta-os/RUN.md)、[可信 ObjectiveStart / CLI](../services/hepta-os/OBJECTIVE_TRANSPORT.md)、[原版 Objective 复跑](../tests/integration/hepta/ORIGINAL_OBJECTIVE.md)、[原版持续 Session](../tests/integration/hepta/ORIGINAL_SESSION.md)、[外部锁稳定性](../tests/integration/hepta/PROBE_LOCK_STABILITY.md)、[历史查询开发与技术契约](../services/hepta-os/OBJECTIVE_HISTORY.md)、[原 owner 历史故障复跑](../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)、[R9 实际证据](../results/integration/2026-10-18-objective-history/README.md)、[最终提交 transport / ARM64 CI](../results/integration/2026-10-18-objective-history-ci/README.md)、[R8 固定历史](../results/integration/2026-10-18-objective-desktop/README.md) | [HEPTA_INTEGRATION](HEPTA_INTEGRATION.md)；默认 observer/Session/Shell 只读，单次提交和历史查询各为独立 default-off CLI。R9 在固定原 owner `2be5fc05` 上实际通过 x86_64 的 15 检查 / 13 history 查询 / 5 次 Objective 请求，4 条 publication、3 次受控重启；重启后当前 run 缺失仍可查准确原请求的历史，损坏或未覆盖 anchor 保持 unknown。查询不恢复 run、不重投、不创建 K/D；生产 issuer、原请求/anchor 持久保存、Session/Shell 新投影、K↔D、确认退役和设备效果继续按 [S1–S5](agents/R8_NEXT_SLICE.md) 实现。R8 两轮固定 f8 准入/Session 和 R6/历史 ARM 结果保留各自源码；新 desktop `46dc` / owner `2be` 的 ARM64 history 已于 11:28:46 UTC success，独立取得同一 15 项隔离历史判据和五 ELF 字节绑定。#193 已普通合入 `aab50f3`；两平台收据不授予 Asterinas 或移动设备资格。 |
| A08 Android | [开发手册](../support/android/README.md)、[来源绑定与 184 项回归](../tests/workloads/android/evidence/2026-10-17-commit-bound-audit/README.md)、[main 组合实际验收](../results/integration/a08-host-main-20261017/README.md) | [ANDROID_COMPATIBILITY](ANDROID_COMPATIBILITY.md)、[接口技术契约](../compat/android/INTERFACES.md)、[内核缺口](../compat/android/kernel-gaps.json)；已整合源码和 Linux host 工具，Binder/seccomp/MAC 与 Android guest 资格未通过 |
| A09 硬件 / VMM | [device lifecycle 开发手册](../support/vmm/device_lifecycle/README.md)、[GATES](../support/vmm/GATES.md) | [HARDWARE_AND_DRIVERS](HARDWARE_AND_DRIVERS.md)、[来源](../support/vmm/PROVENANCE.md)；宿主元数据模型不等于真实 DMA/GPU |
| A10 Rust UI | [运行手册](../support/ui/RUN.md)、[聊天/任务工作区](../support/ui/CHAT_WORKSPACE.md)、[Session / known-run](../support/ui/HEPTA_OBSERVER.md)、[run 新鲜度](../ui/shell/OBSERVATION_FRESHNESS.md)、[真实 Objective 窗口复跑](../tests/ui/ORIGINAL_OBJECTIVE_SHELL.md)、[字体](../support/ui/CJK_RENDERING.md)、[XIM](../support/ui/X11_IME.md)、[本轮实录](../results/integration/2026-10-18-objective-desktop/README.md) | [DESKTOP_UX](DESKTOP_UX.md)；Rust 1.88 / eframe 0.31.1 Linux host 原生程序。25298 整树 125 passed / 0 failed / 2 CJK ignored，严格检查及实际构建通过；同一 Shell 三阶段真实英文 Runtime 卡片逐图通过，顶部中文后缀缺字保留为显示限制。typed 草稿/上下文仍是本地数据。旧 caret 定位失败、Wayland 输入、GPU、Asterinas、移动适配与设备效果未因本轮通过而闭合。 |

2026-10-18 对固定 main `f9e306f76154590e096a42f70ce9de0a7c859e60` 的复核确认：A00–A10 共 11 个模块都有真实开发与技术入口，53 次本地链接对应 49 个不同目标；这些计数属于该固定基线。本轮补入 A04 的主干交接手册，逐项列出候选真实入口、依赖、输入输出、错误、固定重放与后续整合，三份完整候选文档及实现仍在 Draft #8。该基线已包含的 [#195](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/195) 补上 `cpu.max` 显式非法周期、溢出与多余字段的写入前拒绝；其实际源码与复跑见上表新增入口，旧 159/160 项结果不转记为该修复的新验收。

模块有文档链接不等于模块已经完成。每个可交接增量至少给出实际源码位置、依赖与固定版本、构建/运行命令、输入输出和错误语义、权限与状态 owner、真实测试及未通过项。只列 Agent prompt 或未来架构图不能代替这些内容。A04/A05 已有主干交接/实现手册；A07/A10 已合入的源码与随附手册已有连接配置、持续 worker、来源换代和断连语义、原版进程门禁、真实窗口复跑、外部锁诊断、观测过期、字体/输入与进程清理文档，附实际失败和成功记录。[固定 207 的独立文档审查](../results/integration/2026-10-18-objective-history/module-documentation-review.json) 确认 11 个模块均有具体入口，但不是每个模块各有一套独立手册：A00/A01/A02/A05/A06 复用共享架构、ABI 或构建文档；A04 的三份详细手册仅属上表固定外部候选，本地主干存在覆盖例外。53 个表内本地链接和 225 个一跳手册本地目标存在性检查不代替新模块运行；内核效果、Android guest、硬件与移动 UI 的运行资格仍按各自证据判定。原生 AI UI 的事实来源、已实现的可信意图入口和下一步产品接合见 [DESKTOP_UX 第 6 节](DESKTOP_UX.md#6-以-hepta-为核心的-ai-原生-ui)。

[R7 可恢复材料归档](../results/integration/2026-10-18-r7-recovery/README.md) 单独保存原文字节、固定源摘要与明确缺失清单。它没有重建丢失 PNG/gzip，不能凭保留的文本、哈希或历史审查记录授予原图可用性或一次新的运行资格。

## 多 Agent 并行开发

[并行开发执行方案](agents/PLAN.md) · [独立可复制的各 Agent Prompts](agents/PROMPTS.md)。职责与验收以这些文档为准，不改变现有内核实现状态。
