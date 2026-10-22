# 开发与技术文档入口

## 2026-10-22 项目入口与支持边界

本仓库以 Asterinas 派生 Rust 内核、HOS2 控制接口、Hepta 原用户态 owner 和 Rust 桌面构成 organ 开发主线。当前可复核范围包括固定 x86_64/QEMU 内核实验、Linux host 上的 Rust UI/Notes 目的端，以及各自固定来源的兼容/持久性测试。完整生产 G2、Asterinas 上的 Hepta/桌面、GPU/VMM 与手机仍有明确缺口；以 [A–G 当前状态和固定证据](STATUS.md) 为准。

**根 README 保持 0 字节。** 这是 [source gate](../support/build/verify-source.py) 的当前约束，本页承担项目阅读入口。`docs/agents` 的分工提示不能代替下面实际模块手册，历史测试数字也不代表当前整合 tree 已通过。

### 从这里开始

先读 [PROJECT](PROJECT.md) 的目标和 profile、[ARCHITECTURE](ARCHITECTURE.md) 的唯一 owner/接合方式，再按 [STATUS](STATUS.md) 区分已测分支与整合候选。进入代码前使用各模块构建手册中的固定工具链、依赖和验收命令。内核采用 Asterinas 固定来源及 `nightly-2026-07-21`；UI 的阻断 host gate 使用 Rust 1.88.0。C 初版保留的 Rust 1.95.0 运行是独立证据，不能替代 1.88 门禁。

三种内核启动范围须分开：ordinary 产品仅 QueryAbi；G1-c 固定受信映像另有 ReadUsage；G1-d 的五操作只在明确开启的三角色实验 profile 内成立。Notes 正常 Session 启动仍默认不注册原 owner；显式 private bootstrap 的 offer/ACK 也不自产生 FinalUse 授权或持久结果。

### A00–A10 模块交接入口

| 模块 | 开发/运行/验证入口 | 技术契约与当前边界 |
| --- | --- | --- |
| A00 集成 | [实施分工](agents/PLAN.md)、[状态与顺序](STATUS.md)、[跨仓 source profile](agents/ORGAN_RELEASE_PROFILE.md)、[验证总则](VALIDATION.md) | [架构](ARCHITECTURE.md)、[路线决策](DECISIONS.md)；同一源码组合必须有自己的验收。 |
| A01 源码/启动 | [构建](../support/build/README.md)、[完整 ktest](../support/build/ktest/README.md) | [上游 pin](../support/upstream-lock.json)、[source verifier](../support/build/verify-source.py)；E820/timerfd/runner修复已合入，合并 E/F 后的 core269/required31/SMP272仍待实跑。 |
| A02 HOS2 codec | [验收收口](../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md)、[codec 源码](../libs/os-abi/src/lib.rs) | [NATIVE_ABI](NATIVE_ABI.md)；五操作 wire 不等于 ordinary 产品开放全部效果。 |
| A03 control core | [验证手册](../tests/control/VALIDATION.md)、[运行脚本](../tests/control/run-validation.sh) | [API_CONTRACT](../libs/os-control/API_CONTRACT.md)；原 D/终态/退役 owner，内存历史与 Hepta 磁盘持久性分别验收。 |
| A04 Linux/Hepta ELF | [主干交接](agents/handoffs/A04_LINUX_HEPTA_ELF.md)、[完整 Ubuntu32](../tests/workloads/linux/FULL_UBUNTU_PROFILE.md)、[SQLite guest restart](../tests/workloads/linux/SQLITE_GUEST_RESTART.md)、[rootfs](../support/rootfs/README.md) | [Linux 兼容契约](LINUX_COMPATIBILITY.md)、[实际缺口](../compat/linux/GAPS.md)；F 的 ext2 `filetype`/SQLite结果不等于原 Agentd 已在 guest 运行。 |
| A05 内核控制/映像 | [普通产品手册](agents/handoffs/A05_KERNEL_CONTROL.md)、[普通 guest](../tests/kernel/control/README.md)、[G1-c profile](agents/G1C_TRUSTED_OBSERVE_PROFILE.md)、[G1-d profile](agents/G1D_TRUSTED_CONTROL_PROFILE.md) | [HOS2](NATIVE_ABI.md)、[Process image 生命周期](ASTERINAS_PROCESS_IMAGE_G1C.md)；固定初始角色与动态生产 grant 分开。 |
| A06 CPU/隔离/恢复 | [CPU usage](../tests/organ_backend/CPU_USAGE_G1B.md)、[workload 隔离](../tests/kernel/control/G1D_WORKLOAD_ISOLATION.md)、[有限恢复](../tests/kernel/control/G1D_BOUNDED_RECOVERY.md) | [原 CPU owner](ASTERINAS_CPU_OWNER_G1A.md)、[usage 技术](ASTERINAS_CPU_USAGE_G1B.md)、[安全与恢复](SECURITY_AND_RECOVERY.md)；E 已测非零一次恢复，不具备完整 watchdog/暂停原因/总内存保证。 |
| A07 Hepta 接合 | [client](../services/hepta-os/README.md)、[运行](../services/hepta-os/RUN.md)、[原 Objective](../tests/integration/hepta/ORIGINAL_OBJECTIVE.md)、[history probe](../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)、[CPU delivery](../services/hepta-os/CPU_DELIVERY.md) | [集成契约](HEPTA_INTEGRATION.md)、[Objective transport](../services/hepta-os/OBJECTIVE_TRANSPORT.md)、[history 契约](../services/hepta-os/OBJECTIVE_HISTORY.md)、[CPU source pin](../services/hepta-os/CPU_UPSTREAM_CONTRACT.json)；B 跨仓组合、生产 grant/recovered writer 与 D native recovery 仍待统一验收。 |
| A08 Android | [开发手册](../support/android/README.md)、[已有 host 证据](../results/integration/a08-host-main-20261017/README.md) | [Android 兼容](ANDROID_COMPATIBILITY.md)、[接口](../compat/android/INTERFACES.md)、[内核缺口](../compat/android/kernel-gaps.json)；Binder/seccomp/MAC、BSP/APK/实机未完成。 |
| A09 硬件/VMM | [硬件运行手册](../tests/hardware/RUN.md)、[平台决策](../support/hardware/DECISION.md)、[VMM gates](../support/vmm/GATES.md)、[lifecycle 模型](../support/vmm/device_lifecycle/README.md) | [硬件技术契约](HARDWARE_AND_DRIVERS.md)、[只读 inventory](../tests/hardware/evidence/2026-10-21-development-host-inventory.json)；枚举及模型不授予 GPU compute/DMA/reset/VMM 资格。 |
| A10 Rust UI/Notes | [构建与运行](../support/ui/RUN.md)、[工作区](../support/ui/CHAT_WORKSPACE.md)、[Notes 开发与私有 bootstrap](../support/ui/NOTES_ORGAN.md)、[严格 IPC](../tests/ui/test-strict-request-ipc.py)、[bootstrap probe](../tests/ui/test-notes-bootstrap-ipc.py)、[最终 C 原收据](../results/integration/2026-10-22-organ-combination/c-qualified-receipts.json) | [UI 技术目标](DESKTOP_UX.md)、[接合契约](../support/ui/INTEGRATION_CONTRACTS.md)、[Notes wire fixture](../tests/ui/notes-target-v1.json)、[bootstrap fixture](../tests/ui/notes-bootstrap-v1.json)；最终 C 的181项、Clippy与 owned Weston C5属于 Linux host，生产原 owner终态、Asterinas显示/输入与移动适配未完成。 |

所有 A00–A10 模块都有可定位的开发/验证入口和技术契约，但并非每个模块都有独立成套手册：A00/A01/A02/A05/A06 仍复用共享架构、ABI、构建或 profile 文档。上表同时标出实际源码与运行边界；文档存在性不证明功能完成。新增模块交接必须包括固定版本、命令、输入输出、错误语义、权限/状态 owner 和真实未通过项。

逐模块与 crate 的实际文档分布、共享入口和缺口见 [2026-10-22 模块文档覆盖审计](agents/MODULE_DOCUMENTATION_AUDIT.md)。该清点绑定其记录的冻结源码；文档存在、链接有效和产品运行验收分别报告。

文件系统专项另有 [inode 权限事务技术契约](INODE_PERMISSION_TRANSACTIONS.md)、[ExFAT 权限模式修复与验收范围](EXFAT_PERMISSION_MODE.md) 和 [chmod/chown/mount 实际回放手册](../tests/workloads/linux/PERMISSIONS.md)。这些专题逐项说明原 inode owner、尚未迁移的后端和对应正反控制，不将某个后端或 profile 的结果扩展为全部文件系统资格。

### 当前证据入口

最新的 [组合验收与 #240 合并证据](../results/integration/2026-10-22-organ-qualified/README.md) 绑定实际 OS `85d394f…` 和 Hepta `6d6097d…`：七项 CI、完整组合 UI/kernel、原 writer 驱动的真实 Notes 回读和普通内核中的原 Agentd 配置拒绝门禁已执行。test issuer、ABI preflight 与生产/原生 G2/实机资格仍分别记录，具体下一步见 [按依赖实施](agents/ORGAN_IMPLEMENTATION_NEXT.md)。

[跨仓 source profile 手册](agents/ORGAN_RELEASE_PROFILE.md) 给出 build/verify 命令、原 history 祖先证明、两份 Notes golden 的逐字核对，以及源清单与执行资格的区别。它有19项临时 Git 回归，当前 [真实组合清单](../support/release/profiles/2026-10-22-organ-source.json) 也已独立 build/verify；工具不发 grant、不调用 runtime、不启用生产。新 head 必须显式重新核对，生产装配仍需原部署输入与独立端到端验收。

[原 Agentd 普通 ABI 开发/技术手册](../tests/workloads/hepta_agentd_abi/README.md) 和 [完整首跑证据](../results/integration/2026-10-22-agentd-ordinary-abi/README.md) 说明 disabled-default runner、精确拒绝 oracle、实际依赖、只读 ext2 写回缺陷及下一阶段原 FleetRegistry/Supervisor 启动要求。

- A #234 的固定 source A06 与旧 #231 的 ExFAT 归档分别见 [STATUS](STATUS.md) 和 [原 ExFAT 包](../results/integration/2026-10-21-exfat-qualified/README.md)。
- E `81897df4…` 的 core266/三 boot/旧 root 负控，以及 F `058c5e48…` 的 core265/SQLite 同 profile 正反结果见 [恢复的原收据](../results/integration/2026-10-22-organ-combination/ef-qualified-receipts.json)。
- C 最终实测 source `86528f7e933a1c6db2c9d31b47d8caa0fa047101` / tree `18d21dbeb7e7934cb4f7de21dc77a1b70db3c937` 已同树发布到 [PR #239](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/239) head `c645d2c85b80a8e93d9ecb78913f07bc29d6fc35`。[最终原收据](../results/integration/2026-10-22-organ-combination/c-qualified-receipts.json) 记录 workspace **181 passed / 0 failed / 2 ignored**、全 targets Clippy `-D warnings` 与完整 C5 owned Weston 通过；C5 同源重跑 private bootstrap、真实 Notes `applied`/独立回读，并验证同一 Session 下 compositor 重启后的新 client layout。它不证明旧 surface 连续性、生产原 owner、Asterinas 或显示像素。packet 中 `evidence-v2` 的 Xvfb/严格 IPC 仍属于中间 `8662dced…`；[公开初版](../tests/ui/evidence/2026-10-21-notes-target/README.md) 的172项也不转授最终版本。来源分界及当前整合树仍需独立门禁见 [STATUS](STATUS.md)。
- #235 的 [证据保存说明](../results/integration/2026-10-21-os-integration-evidence/README.md) 保留旧原件、实际来源和压缩载体路径，没有把旧成功改记为新整树运行。

## 历史入口与当时状态（保留原文）

以下原文中的“当前”、根 README 说明、测试数和模块完成度只适用于各段原记录时点。新的 A–G 整合状态以上节及 [STATUS](STATUS.md) 顶节为准；这里的原始链接、报告和统计不回写为新的验收。

2026-10-20 profile 接续：[G1-c 受信初始映像观察](agents/G1C_TRUSTED_OBSERVE_PROFILE.md) 已随 [#214](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/214) 合入，普通构建继续 QueryAbi-only；新增 [G1-d 开发与技术契约](agents/G1D_TRUSTED_CONTROL_PROFILE.md) 说明三实际角色、五操作、同 CPU/D owner、原锁序、1024 窗口和明确非 Hepta durability 的资格 ack。G1-d 编译/真实执行以其独立候选 CI 为准，不用下列历史测试数代替新验收。下面 R12/R11 的源码与计数保留其冻结时点。

当前 R12：[G1-c 生命周期产品 #207](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/207) 已于 14:15:35 UTC 正常同树合入 `9f664348…`。最终 `10420401…` 的五项检查全绿，完整 core238／OSTD221（3软跳过）、七负控、普通 QueryAbi18、SCM27／RLIMIT37／Ubuntu32 和 CPU 原门槛已独立核验。[本轮审计与实际证据](../results/integration/2026-10-19-g1c-lifecycle/README.md)、[当前 11 模块／64 入口矩阵](../results/integration/2026-10-19-g1c-lifecycle/module-matrix.json)、[具体后续施工](../results/integration/2026-10-19-g1c-lifecycle/NEXT_IMPLEMENTATION.md) 对应实际完成与未完成边界。G1-c 的[技术手册](ASTERINAS_PROCESS_IMAGE_G1C.md)和[开发／验证手册](../tests/kernel/control/PROCESS_IMAGE_G1C.md)已随产品合入。当前仍仅 QueryAbi；不可变映像认证、生产 grant、四资源操作、W1 和设备 profile 各自继续实现。下面 R11 的62个入口和计数保留其冻结时点。

R11 已完成状态（保留当时记录）：[#205](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/205) 已正常合入，实际执行 `4d3011cf…` 的完整 core220/OSTD221（3软跳过）、七完整负控、普通 Linux32 与 CPU 原门槛已独立核实。[全模块审计与内核路线](../results/integration/2026-10-19-g1b-usage/README.md) 给出 **A00–A10 的62个文档／契约／验证入口**、当前主干与历史资格，以及具体 G1-c/d、W1、桌面／Android／设备实施顺序；[机器矩阵](../results/integration/2026-10-19-g1b-usage/module-matrix.json) 固定文档身份和剩余门禁。当前仍只开放 QueryAbi，四项资源操作和生产授权未开放。以下轮次与旧计数保留各自时点，最新运行状态以 [STATUS](STATUS.md) 顶节及本轮报告为准。

此前接续（#205 完整验收前的记录）：[原 CPU owner 纳秒记账技术手册](ASTERINAS_CPU_USAGE_G1B.md)、[G1-b 开发与验证手册](../tests/organ_backend/CPU_USAGE_G1B.md)、[完整 Linux32 已合入的独立证据](../results/compat/2026-10-19-full-linux/README.md)、[CPU owner 已合并的独立证据](../results/organ-backend/2026-10-19-owner-retention/README.md)、[原时钟/调度交接 CI](../tests/organ_backend/CPU_CLOCK_HANDOFF_CI.md)、[当前状态](STATUS.md)。当时 G1-b 本地 WIP core 220 已通过，最终候选 CI 尚待验收；当前完整结果见上方。新内核与完整 Linux/Hepta/设备资格各自按实际执行闭合。

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
| [R10 实际 CPU owner 与证据](../results/integration/2026-10-19-g1-owner/README.md) | 真实 G1-a owner、首次编译/隐式写锁失败、两个完整内核目标、独立复核、普通产品候选与 Hepta 安全债务 |
| [G1-a 开发与技术手册](ASTERINAS_CPU_OWNER_G1A.md) | 同锁 cpu.max revision、一次绑定、不可逆 detached、锁序、错误与十项真实 owner 回归；生产授权未启用 |
| [G1-b 技术手册](ASTERINAS_CPU_USAGE_G1B.md)、[开发与验证手册](../tests/organ_backend/CPU_USAGE_G1B.md) | 原账本 BOOTTIME 纳秒累计、独立 CFS cycles、同次结算/同锁 usage、持久故障与原 owner 寿命；19 项新增回归及七个原生产反向控制；用户态四操作仍未开放 |
| [G1-c 技术手册](ASTERINAS_PROCESS_IMAGE_G1C.md)、[开发与验证手册](../tests/kernel/control/PROCESS_IMAGE_G1C.md) | 原 Process 同锁映像身份与关闭、VMAR → TaskSet → image 锁序、private prepared 一次性启动；18项新增 core 回归与普通 QueryAbi18；不可变映像与 grant 仍待接合 |
| [普通产品 QueryAbi 回归](../tests/kernel/control/README.md) | 保留旧 A05 fixed replay；新候选使用独立固定 source/tree，普通 boot 与四项禁用操作分别验证 |
| [R8_NEXT_SLICE](agents/R8_NEXT_SLICE.md) | 已有 issuer、持久核对、受限 OS adapter 与 Asterinas G1/G2 的具体下一工单 |
| [R9_G1_OWNER_SEAM](agents/R9_G1_OWNER_SEAM.md) | 固定实际 CPU owner 的共享 revision、控制器 incarnation、锁序和 BOOTTIME 接缝；源审计，不是新内核运行资格 |
| [Objective history 开发与技术契约](../services/hepta-os/OBJECTIVE_HISTORY.md) | 独立原 owner 历史查询、保留请求与 anchor、有限结果、CLI 和验证边界 |
| [SOURCES](SOURCES.md) | 一手来源与固定快照 |
| [upstream-lock](../support/upstream-lock.json) | 已核查源码与参考资产、显式缺失构建输入 |

每次后续改动直接修改对应契约和状态，不重复复制ABI字段或完成度。旧仓库重建历史保留在Git初始提交；不混入永久产品要求。

最初的[恢复规格场景](../tests/spec/test_recovery_contract.py)、[固定字节样本](../tests/golden/hos2.json)与[规格模型结果](../results/spec-recovery-v03.json)是历史规格证据。当前主干另有真实 [Rust codec](../libs/os-abi/src/lib.rs)、[control core API](../libs/os-control/API_CONTRACT.md)、原生 QueryAbi 和 CPU 配额实现；对应宿主或 QEMU 证据分别见下表。规格版本不表示整个系统的完成比例。

## 按模块开始开发

当前文档整合固定主干为 `7947f500848085199be55e8f4e6a2fe24390407b`；#199–#202 的本地CPU结算、运行段owner保留、FD限制与完整Linux工作负载入口保留在下文。具体来源与结果见 [STATUS](STATUS.md)，报告#204的冻结边界与合并规则见[本次整合说明](R11_REPORT_INTEGRATION.md)。下述R10/R9数字各属于原固定审查，不代替当前主干运行。

R10 的冻结入口是 [真实 CPU owner 与完整证据](../results/integration/2026-10-19-g1-owner/README.md)、[G1-a manual](ASTERINAS_CPU_OWNER_G1A.md) 和 [ordinary QueryAbi 开发手册](../tests/kernel/control/README.md)。12e 固定源的 aster-core 179 与 OSTD 221（含 3 soft skip）属于本轮真实内核运行；4e 普通候选 attempt03 已取得当次 boot/QueryAbi 接受；f744 的正常 A06 原始产物已完成独立复核，463f 的 G0/A06 成功与 A03 allocator 前置失败另存。最终 host 修正 bccb 已与新主干 e15 机械合入 1ca/同树远端 1c054，新组合1c的六checks及完整产物已独立接受，并于03:59:41 UTC同树合入main71ce，见[R10固定头证据](../results/integration/2026-10-19-g1-owner/g1-remote-ci-1c054/README.md)。后续本地残留的来源仍 unknown。Hepta d32 的普通 CI 状态与依赖安全债务见本轮报告，不以历史客户端通过推定 owner 已合并。原R10交付截止main7e/tree354并保留#198独立SCM增量，见[R10主干整合说明](../results/integration/2026-10-19-g1-owner/source-publication/report-main-sync/README.md)；旧G1运行仍绑定1c/tree2b。R10的Hepta观察固定在[04:44–04:45 UTC](../results/integration/2026-10-19-g1-owner/hepta-final-status/README.md)，三个PR仍未满足合并条件。下面R9/R8/R6计数保留其日期与源码，模块新入口在A01/A04/A05/A06/A07行补充。

当前 R9 补齐 Runtime 的成功样本时钟与 Shell 总年龄判定，最终 UI workspace 137 passed / 0 failed / 2 CJK ignored、严格检查和四程序构建通过；新增两个真实 CLI 终止边界，完整 objective feature suite 43 passed。A04 增加主干交接手册，A06 补实际 cpu.max 与 owner 入口，见 [R9 源码与原始证据](../results/integration/2026-10-18-runtime-process-boundaries/README.md)。Schema 新字段需要 Session/Shell/ctl 配套部署；原版、像素和设备资格仍按下述独立来源判定。

2026-10-19 合入实际 main 的原 owner history 扩展后，完整组合重新得到 UI 137 passed / 2 既有 ignored、Hepta all-features 53 passed、严格检查和七 ELF 构建通过。另修复成功进程 leader 提前回收后仍遗留同组 writer 的实际缺陷，保留双 RED、GREEN 与 47 项 Python 结果；归档旧 HEAD 的 ARM 清理失败、实际两页 Rust 工作区原图，以及独立固定 history owner 的已执行 CI。来源和新旧资格见 [整合证据](../results/integration/2026-10-19-main-sync/README.md)，新发布 HEAD 的 CI 不沿用旧结论。

R9 在原 owner 独立扩展上增加已知请求的在线准入历史查询；模块开发与技术入口见 [history 契约](../services/hepta-os/OBJECTIVE_HISTORY.md)，真实故障复跑见 [history probe](../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)。当前实际测试与未完成门禁以 [STATUS](STATUS.md) 最上方轮次为准。内核侧按 [G1 owner 接缝审计](agents/R9_G1_OWNER_SEAM.md) 先统一 revision 与控制器身份，再接可信初始化。以下 R8/R6 保留自己的固定证据。

A06 的 [本地 CPU 配置前结算](../tests/organ_backend/CPU_CONFIG_SETTLEMENT.md) 给出原 runqueue/owner 锁序、带宽游标、四个确定性内核回归，以及 100 ms / 2 ms 两个周期的只读和同值写入客体验证命令。该增量保留原计费 owner；文档分别列出实际执行要求与尚未完成的 BOOTTIME、同版本使用量、控制器代际和 SMP 接合，不据此宣告全部 G1-b 完成。

A06 的 [运行段原控制器保留](../tests/organ_backend/CPU_OWNER_RETENTION.md) 说明控制器代际、祖先 Arc、节点存活 lease、退出后重调度与双本地发布检查点。六个原内核回归和 [单一旧行为反向验证入口](../tests/organ_backend/run_cpu_owner_negative.py) 保留真实失败的源码、ELF、原 gate 与串口，不把负控成功识别记作产品通过；完整 BOOTTIME 与 SMP 仍分别验收。

A04 的 [RLIMIT_NOFILE 开发与技术手册](../tests/workloads/linux/RLIMIT_NOFILE.md) 说明原 FileTable 的 FD 预约、调用进程 soft limit、并发/错误语义、37 项差分 probe 和严格同 ELF 运行命令；[固定 Linux 成功与旧内核失败归档](../results/compat/2026-10-19-rlimit-nofile/README.md) 保留完整原始字节、实际退出码和早期失败。该新增 profile 与旧 Debian 13 全套资格分别记录，修复后的普通内核必须在同一组合源码上重新验收。

A04 的 [完整 Ubuntu 32 项工作负载](../tests/workloads/linux/FULL_UBUNTU_PROFILE.md) 给出实际运行时打包、动态链接依赖、非特权 Linux chroot、同一固定镜像客体验证及原始输出判据。本候选引入 #8 的 67 个原始源码/资料文件，在单独命名的 Ubuntu 24.04 profile 上保留 28 项 C、3 项 Python 和实际锁定 Tokio 工作负载；历史 Debian profile 与缺失的四个原 ELF 不因此补齐。[27 项门禁回归证据](../tests/workloads/linux/results/ubuntu-full-20261019-gates/README.md) 仅证明判定器边界，实际 Linux 32/32、普通内核 guest 32/32 与 Hepta W1 分别报告。

已合入 R8 的实际集成输入为 `25298f5d87cf3db90deefe9c0405ecd241dc6581`，同树发布 `ca5e7d8473690df1bf7636de0808e58414c40abe` / tree `9584997da412dd10c0960f69011b40a4b26d2862`，[PR #192](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/192) 纳入 #190 工作区候选及 #191 主干修复的完整历史。[R8 实际证据](../results/integration/2026-10-18-objective-desktop/README.md) 记录独立 CLI、两次原版准入运行、后一次的三个 Session/同一 Shell 阶段与三张实际截图；[R8 ARM 完成复核](../results/integration/2026-10-18-runtime-process-boundaries/r8-arm-completion/README.md) 另绑定 `05a7cd23` / run `39106645234` 的实际 success。默认 observer/Session/Shell 继续只读；隔离测试 issuer 的通过不代替生产 issuer 或设备效果。

上一轮 #185/#187/#188/#189 的 A02 完整 pinned 验收、A03 双后端及有界并发、G0 和 A06 客体 1/2 vCPU 有限配置证据见 [audit-followthrough 索引](../results/integration/2026-10-18-audit-followthrough/README.md)。R6 两轮原版只读六阶段窗口属于 2026-10-17 实际运行，见 [R6 历史归档](../tests/integration/hepta/evidence/2026-10-17-r6/README.md)；旧测试计数和源码不转记给本轮。下面保留全部 A00–A10 的当前开发入口、技术契约和各自资格。

下表的 control core 验证属于宿主模型与有界并发检查；其 durable K/fsync 接合尚未闭合，内核 IRQ/SMP 接合仍需验证。A05 的实际内核入口仍按 QueryAbi 与各项效果操作分别判定，不能从宿主通过推定内核效果可用。

| 模块 / owner | 开发与验证入口 | 技术契约 / 实际范围 |
| --- | --- | --- |
| A00 集成 | [PLAN](agents/PLAN.md)、[STATUS](STATUS.md) | [ARCHITECTURE](ARCHITECTURE.md)、[DECISIONS](DECISIONS.md)；统一接口与集成 |
| A01 源码 / 启动 | [构建手册](../support/build/README.md)、[内核测试入口](../support/build/ktest/README.md)、[G1-a 本地依赖与锁](ASTERINAS_CPU_OWNER_G1A.md)、[R10 实际证据](../results/integration/2026-10-19-g1-owner/README.md) | [固定来源](../support/upstream-lock.json)；原 Git seed 与明确工作派生锁分别固定，完整 component metadata 保持 --locked。R10 两个真实 kernel 目标保留原始失败、2,980 个输入和实际 ELF；4e 普通 boot/QueryAbi 另有当次接受收据，后续当前残留观察分开记录。 |
| A02 HOS2 codec | [验收收敛与实际命令](../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md)、[证据完整性](../tests/abi/A02_EVIDENCE_INTEGRITY_2026-10-17.md)、[2026-10-18 pinned 验收](../results/integration/2026-10-18-audit-followthrough/README.md#a02) | [NATIVE_ABI](NATIVE_ABI.md)、[codec 源码](../libs/os-abi/src/lib.rs)；#181/#185 已闭合 N0 prior-window、QueryDelivery 终态/保留序号与独立 Python 判定器边界。该固定历史验收为 13/13、Python ABI 62 项；R10 另在 bccb 实际执行 ABI 78 项，见[独立 host 修正验证](../results/integration/2026-10-19-g1-owner/g1-ci-host-correction/README.md)；wire 实现不等于全部内核操作实现。 |
| A03 control core | [验证手册](../tests/control/VALIDATION.md)、[运行脚本](../tests/control/run-validation.sh)、[2026-10-18 双后端与证据复核](../results/integration/2026-10-18-audit-followthrough/README.md#a03) | [API_CONTRACT](../libs/os-control/API_CONTRACT.md)；#185 已合入 original-owner authority 绑定的 namespace receipt 与不复用 instance tag。该固定历史运行的 std / portable-spin 各 225 项，Loom 19 个模型 / 27,253 个调度，19 个锁内分配场景的 alloc/realloc/dealloc 均为零，以上为原固定历史记录。R10 另在 bccb 实际完成 std/portable 各 225、两组 19 个 Loom 模型和 19 个零计数场景，保留前置失败，见[本轮 host 原始验证](../results/integration/2026-10-19-g1-owner/g1-ci-host-correction/README.md)；durable K/fsync 和内核 IRQ/SMP 接合仍未因此通过。 |
| A04 Linux / Hepta ELF | [构建、验证与主干交接](agents/handoffs/A04_LINUX_HEPTA_ELF.md)、[SCM_RIGHTS/CLOEXEC 实现及 27 项验证](../tests/workloads/linux/SCM_RIGHTS_CLOEXEC.md)、[固定候选开发手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/tests/workloads/linux/README.md)、[rootfs 手册](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/support/rootfs/README.md) | [LINUX_COMPATIBILITY](LINUX_COMPATIBILITY.md)、[候选缺口](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/compat/linux/GAPS.md)；[Draft #8](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/8) 的25c是历史候选来源。主干7947已经导入其67项源码/资料，包含[本地开发手册](../tests/workloads/linux/README.md)、[本地rootfs手册](../support/rootfs/README.md)和[本地缺口文档](../compat/linux/GAPS.md)，并增加独立Ubuntu32项profile；旧Debian四ELF/rootfs与该新profile分别保留资格。R10当时的文档覆盖与03:39:15 UTC [原API观察](../results/integration/2026-10-19-g1-owner/source-publication/upstream-and-a04-current-api.json)继续保留历史边界，不作为当前目录缺失或PR状态结论。 |
| A05 内核控制 | [实现、构建与调试手册](agents/handoffs/A05_KERNEL_CONTROL.md)、[R10 普通产品 QueryAbi 回归手册](../tests/kernel/control/README.md) | [NATIVE_ABI](NATIVE_ABI.md)；main 已有 QueryAbi 的 Process / exec 镜像身份隔离；新候选 runner 保留旧 fixed replay，分别验证普通 boot 和四项禁用操作。能力授予和其余四操作未闭合，实际结果按 R10 收据判断。 |
| A06 CPU 预算 | [R10 G1-a 开发与技术手册](ASTERINAS_CPU_OWNER_G1A.md)、[R10 实际证据](../results/integration/2026-10-19-g1-owner/README.md)、[CPU 实现及客体验证](ASTERINAS_CPU_BANDWIDTH_N0.md)、[cpu.max 输入契约与复跑](../tests/organ_backend/CPU_MAX_CONFIG.md)、[既有集成收据](../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json)、[本轮实际执行与来源](../results/integration/2026-10-18-audit-followthrough/README.md) | [资源 backend 接合](ASTERINAS_ORGAN_BACKEND.md)；R10 已接实际 owner 的同锁 cpu.max revision/不可逆 detached，真实 core 179、OSTD 221 含 3 soft skip；后续 [G1-b 技术手册](ASTERINAS_CPU_USAGE_G1B.md) 与 [开发手册](../tests/organ_backend/CPU_USAGE_G1B.md) 已接原 BOOTTIME 纳秒累计和内部一致快照，#205 实际 core220/OSTD221（3软跳过）、七完整负控及普通 Linux/CPU 同核门槛已通过，生产绑定、cpu.weight、用户态四操作及完整 G1 未闭合。以下保留历史源与运行：[#188](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/188) 的 zombie 尾账修复已在 e97a30c923b1a27e1578eaaf6b39d85fe1aa5591 / tree c70e97c30b6a7808586c1a2a7db4a6860ede004e 实测，同树发布为 9265235c4b4f375844c923cf0b0f517d119d9937，已合入 main 8ea35f55a38949f511f0855cd168dfd1d672acc8。完整 aster-core 159/159；负对照 157 passed / 2 expected fail。新生产 ELF 的 1/2 vCPU 各两轮固定 1% 配额 probe 均通过既有 3% 上界，双核并行 baseline 通过；一般迁移/退出交错、IRQ/SMP 和 Hepta/HOS2 不随上述有限运行自动取得资格。 另 [#191 奇数周期 oracle](../results/organ-backend/2026-10-18/a06-odd-period-oracle/README.md) 仅改 cfg(ktest)，生产函数字节不变；新完整 aster-core 160/160，OSTD 报告 221 passed 含 3 soft skip。其 merge 三项 CI 已成功，不新增生产 ELF/SMP 资格。 |
| A07 Hepta 用户态接合 | [R10 原 owner CI 与安全债务](../results/integration/2026-10-19-g1-owner/README.md)、[完整安全技术报告](../results/integration/2026-10-19-g1-owner/hepta-security/deny-repro-01/SECURITY_DEBT_DIAGNOSIS.md)、[原 Bazel / Windows 失败诊断](../results/integration/2026-10-19-g1-owner/hepta-bazel-followup/BAZEL_FAILURE_DIAGNOSIS.md)、[Fleet fixture main 独立修复与窄域实测](../results/integration/2026-10-19-g1-owner/hepta-fleet-fixture-main-fix/README.md)、[client 开发](../services/hepta-os/README.md)、[只读契约](../services/hepta-os/CONTRACT.md)、[运行手册](../services/hepta-os/RUN.md)、[可信 ObjectiveStart / CLI](../services/hepta-os/OBJECTIVE_TRANSPORT.md)、[原版 Objective 复跑](../tests/integration/hepta/ORIGINAL_OBJECTIVE.md)、[原版持续 Session](../tests/integration/hepta/ORIGINAL_SESSION.md)、[外部锁稳定性](../tests/integration/hepta/PROBE_LOCK_STABILITY.md)、[历史查询开发与技术契约](../services/hepta-os/OBJECTIVE_HISTORY.md)、[原 owner 历史故障复跑](../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)、[R9 实际证据](../results/integration/2026-10-18-objective-history/README.md)、[最终提交 transport / ARM64 CI](../results/integration/2026-10-18-objective-history-ci/README.md)、[R8 固定历史](../results/integration/2026-10-18-objective-desktop/README.md) | [HEPTA_INTEGRATION](HEPTA_INTEGRATION.md)；默认 observer/Session/Shell 只读，单次提交和历史查询各为独立 default-off CLI。R9 在固定原 owner `2be5fc05` 上实际通过 x86_64 的 15 检查 / 13 history 查询 / 5 次 Objective 请求，4 条 publication、3 次受控重启；重启后当前 run 缺失仍可查准确原请求的历史，损坏或未覆盖 anchor 保持 unknown。查询不恢复 run、不重投、不创建 K/D；生产 issuer、原请求/anchor 持久保存、Session/Shell 新投影、K↔D、确认退役和设备效果继续按 [S1–S5](agents/R8_NEXT_SLICE.md) 实现。R8 两轮固定 f8 准入/Session 和 R6/历史 ARM 结果保留各自源码；新 desktop `46dc` / owner `2be` 的 ARM64 history 已于 11:28:46 UTC success，独立取得同一 15 项隔离历史判据和五 ELF 字节绑定。#193 已普通合入 `aab50f3`；两平台收据不授予 Asterinas 或移动设备资格。 |
| A08 Android | [开发手册](../support/android/README.md)、[来源绑定与 184 项回归](../tests/workloads/android/evidence/2026-10-17-commit-bound-audit/README.md)、[main 组合实际验收](../results/integration/a08-host-main-20261017/README.md) | [ANDROID_COMPATIBILITY](ANDROID_COMPATIBILITY.md)、[接口技术契约](../compat/android/INTERFACES.md)、[内核缺口](../compat/android/kernel-gaps.json)；已整合源码和 Linux host 工具，Binder/seccomp/MAC 与 Android guest 资格未通过 |
| A09 硬件 / VMM | [device lifecycle 开发手册](../support/vmm/device_lifecycle/README.md)、[GATES](../support/vmm/GATES.md) | [HARDWARE_AND_DRIVERS](HARDWARE_AND_DRIVERS.md)、[来源](../support/vmm/PROVENANCE.md)；宿主元数据模型不等于真实 DMA/GPU |
| A10 Rust UI | [运行手册](../support/ui/RUN.md)、[聊天/任务工作区](../support/ui/CHAT_WORKSPACE.md)、[Session / known-run](../support/ui/HEPTA_OBSERVER.md)、[run 新鲜度](../ui/shell/OBSERVATION_FRESHNESS.md)、[真实 Objective 窗口复跑](../tests/ui/ORIGINAL_OBJECTIVE_SHELL.md)、[字体](../support/ui/CJK_RENDERING.md)、[XIM](../support/ui/X11_IME.md)、[本轮实录](../results/integration/2026-10-18-objective-desktop/README.md) | [DESKTOP_UX](DESKTOP_UX.md)；Rust 1.88 / eframe 0.31.1 Linux host 原生程序。25298 整树 125 passed / 0 failed / 2 CJK ignored，严格检查及实际构建通过；同一 Shell 三阶段真实英文 Runtime 卡片逐图通过，顶部中文后缀缺字保留为显示限制。typed 草稿/上下文仍是本地数据。旧 caret 定位失败、Wayland 输入、GPU、Asterinas、移动适配与设备效果未因本轮通过而闭合。 |

2026-10-18 对固定 main `f9e306f76154590e096a42f70ce9de0a7c859e60` 的复核确认：A00–A10 共 11 个模块都有真实开发与技术入口，53 次本地链接对应 49 个不同目标；这些计数属于该固定基线。本轮补入 A04 的主干交接手册，逐项列出候选真实入口、依赖、输入输出、错误、固定重放与后续整合，该固定审查时三份完整候选文档与四ELF/rootfs实现仍在 Draft #8，7e 已合入独立 SCM_RIGHTS/CLOEXEC 实现与手册。当前 #202 已把三份详细手册和新 Ubuntu full32 实现合入 main；旧 Debian 四 ELF/rootfs 原运行输入仍未恢复，二者资格不混用。该基线已包含的 [#195](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/195) 补上 `cpu.max` 显式非法周期、溢出与多余字段的写入前拒绝；其实际源码与复跑见上表新增入口，旧 159/160 项结果不转记为该修复的新验收。

模块有文档链接不等于模块已经完成。每个可交接增量至少给出实际源码位置、依赖与固定版本、构建/运行命令、输入输出和错误语义、权限与状态 owner、真实测试及未通过项。只列 Agent prompt 或未来架构图不能代替这些内容。A04/A05 已有主干交接/实现手册；A07/A10 已合入的源码与随附手册已有连接配置、持续 worker、来源换代和断连语义、原版进程门禁、真实窗口复跑、外部锁诊断、观测过期、字体/输入与进程清理文档，附实际失败和成功记录。[固定 207 的独立文档审查](../results/integration/2026-10-18-objective-history/module-documentation-review.json) 确认 11 个模块均有具体入口，但不是每个模块各有一套独立手册：A00/A01/A02/A05/A06 复用共享架构、ABI 或构建文档；该固定 207 审查时 A04 三份详细手册仍属外部候选；当前 #202 已导入 main，这项文档覆盖例外已消除。53 个表内本地链接和 225 个一跳手册本地目标存在性检查不代替新模块运行；内核效果、Android guest、硬件与移动 UI 的运行资格仍按各自证据判定。原生 AI UI 的事实来源、已实现的可信意图入口和下一步产品接合见 [DESKTOP_UX 第 6 节](DESKTOP_UX.md#6-以-hepta-为核心的-ai-原生-ui)。

[R7 可恢复材料归档](../results/integration/2026-10-18-r7-recovery/README.md) 单独保存原文字节、固定源摘要与明确缺失清单。它没有重建丢失 PNG/gzip，不能凭保留的文本、哈希或历史审查记录授予原图可用性或一次新的运行资格。

R10的[冻结目标与手册delta](../results/integration/2026-10-19-g1-owner/module-documentation-delta.json)将固定207的R9审查作为历史基线，保留该轮G1手册及e15的13份Markdown变化审查，再实读7e更新的A04 handoff与新增SCM手册。原冻结树的11模块共72个表内本地目标、16份手册的一跳106个目标全部存在。该时点三份完整候选手册仍外部；当前7947已导入这些文档，新profile与旧Debian四ELF的资格仍分别判断。历史53/225与f9的53/49各属原审查，不加总为本次新检查，原R10delta不回写。

R10截止时点的 Hepta 普通 CI 另保留 [Fleet 134 包 ENOSPC 原失败](../results/integration/2026-10-19-g1-owner/hepta-fleet-main-remote-ci/README.md)与[独立存储配置修复](../results/integration/2026-10-19-g1-owner/hepta-scoped-ci-storage-fix/README.md)。PR #2882 的本机41项/严格Clippy与远端失败分别记录；04:15:05 UTC发布的独立 [PR #2883](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2883)只改五行job env，已有102个不同Python契约与18项既有小crate实际验证。其04:17:21原API已有cargo-deny失败，scoped按原策略跳过，原134包尚无新远端完成收据；新deny日志未恢复，不能复用旧本地13项作为新远端计数。依赖安全、Windows边界和owner PR #2815门禁继续保留。

## 多 Agent 并行开发

[并行开发执行方案](agents/PLAN.md) · [独立可复制的各 Agent Prompts](agents/PROMPTS.md)。职责与验收以这些文档为准，不改变现有内核实现状态。
