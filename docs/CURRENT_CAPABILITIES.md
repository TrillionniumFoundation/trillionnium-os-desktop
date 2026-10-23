# 当前能力、源码与验收边界

本实施线在内核/证据检查点 `c4623788` 上接入 UI/Session 检查点 `6b16d38a`，来自 PR #257。内核原生验收固定在独立源码 `0187bd578f6786c40c812c13976e4889a1aba835` / tree `335007e4f94114c6a26506d9448faf0d43c4245c`；早期 `9ec0874c` 状态继续保留。当前整合尚未完成统一验收；下列每项结果只属于其明确来源，不给本次合并、远端 main 或部署环境转授资格。

**当前没有完整生产控制、完整原生 F1/G2、通用桌面控制或手机产品资格。** 文档与源码门禁通过只能关闭对应工程问题；不能把单个 host、guest 或设备场景的成功扩展为产品验收。

## 如何读取状态

- **候选已有实现**：指定源码内已有具体实现，可继续构建或集成；不是执行收据。
- **固定场景有记录**：手册或归档记录了某一 source/profile 的运行；应查对应原始收据，新组合不继承结果。
- **仍需完成**：实现、装配或真实执行缺口；不能用设计、脚本存在或开放 PR 标题标为完成。

[STATUS](STATUS.md) 保存按时间排列的证据；其中“当前”“未实现”、测试计数与 README 空文件要求只属于各段记录时点。[INDEX](INDEX.md) 提供模块入口；[ROADMAP](ROADMAP.md) 给出接续依赖。三者引用本表，不另造完成率。

## A00–A10

| 领域 | 候选已有实现与开发入口 | 固定场景记录与仍需完成 |
| --- | --- | --- |
| A00 来源与发布 | [跨仓 source profile](agents/ORGAN_RELEASE_PROFILE.md) 绑定原 owner、受保护 authority 输入接口及 Notes target v1/bootstrap v2/recovery v1；[根入口](../README.md) 和模块指南已存在。 | 10-22 的 OS `85d394f…` / Hepta `6d6097d…` 有独立历史组合记录；它的旧 golden 不覆盖当前 v2/recovery 组合。最终 pair 的 build、verify、原包测试、部署与 CI 必须分别记录。 |
| A01 内核构建与启动 | [固定源码构建](../support/build/README.md)、[ktest](../support/build/ktest/README.md)、[当前原生 runtime 构建器](../tests/workloads/hepta_agentd_runtime/README.md) 保留 OSDK 来源与产物身份。 | 已有多个固定 QEMU 切片；新整合源码必须重跑对应门禁。某个 ordinary ELF 的 store 成功不等于完整内核套件、SMP 或裸机通过。 |
| A02 wire ABI | [os-abi](../libs/os-abi/README.md) 与 [HOS2](NATIVE_ABI.md) 提供 no_std 五操作编解码、golden、错误与容量边界。 | codec 资格不开放内核权限。普通启动仍是 QueryAbi；G1-c/d 使用各自显式 profile。 |
| A03 控制核心 | [API 合同](../libs/os-control/API_CONTRACT.md)、[验证手册](../tests/control/VALIDATION.md) 说明原 owner、D、退役、锁与模型范围。 | host/Loom/no_std 模型不能替代内核 IRQ/SMP、原 Hepta 磁盘确认与整树组合验收。 |
| A04 Linux/存储 | [ELF/ABI 交接](agents/handoffs/A04_LINUX_HEPTA_ELF.md)、[只读](../tests/workloads/linux/readonly/README.md)、[remount](../tests/workloads/linux/remount/README.md)、[utimens](../tests/workloads/linux/utimens/README.md)、[UDP](../tests/workloads/linux/UDP_LOCAL_ERROR.md) 有具体实现和 runner。 | [原 CognitiveStore](../tests/workloads/hepta_cognitive_store/VALIDATION.md) 记录固定 OS `7d8906ef…` / Hepta `b3d3f2d…` 的 host/guest 各10检查；仅该 store 场景，完整 F1、授权恢复与物理掉电资格保持未完成。 |
| A05 内核控制 | [Process 映像](ASTERINAS_PROCESS_IMAGE_G1C.md)、[G1-c](agents/G1C_TRUSTED_OBSERVE_PROFILE.md)、[G1-d](agents/G1D_TRUSTED_CONTROL_PROFILE.md) 有固定角色、原 CPU/D owner 与权限接合。 | 真实 Agentd 最终 exec 身份、生产 authority、原 writer/outbox 持久 K↔D 和同 guest 的故障核对/退役仍须统一运行。 |
| A06 资源与恢复 | [CPU owner](ASTERINAS_CPU_OWNER_G1A.md)、[pids](../tests/kernel/control/G1D_PIDS_ISOLATION.md)、[共享用户数据页限额](../tests/kernel/control/G1D_USER_MEMORY.md) 和 [独立 timer watchdog](agents/G1D_WATCHDOG.md) 已有候选代码。 | `0187bd57` 原全套 core303/allocator20/ML15 和 OSTD229报告通过（原TCG跳过3），相同OSTD ELF另在实际KVM229/229无跳过。已覆盖原Frame/VMO及管道/FIFO、Unix stream/seqpacket物理缓冲最后引用计费；原分配器保护extent和显式fallible页表另有对应回归。它们仍不等于 `memory.max`、slab/其余socket计费或完整恢复保留。六boot watchdog属于 `10dae5ea`，可信用户暂停意图、完整资源保留、SMP与故障验证未闭合；284/286等旧失败完整保留。 |
| A07 Hepta 接合 | [observer/Objective/history/CPU adapter](../services/hepta-os/README.md) 和 [运行手册](../services/hepta-os/RUN.md) 有分开的 source 合同；[原 daemon runner](../tests/workloads/hepta_agentd_runtime/README.md) 保持原 FleetRegistry/Supervisor。 | 原包构建、no-turn daemon生命周期、UI目标提交、生产 FinalUse、持久效果与 G2 分别验收。原 `7d8906ef/b3d3f2d4` no-turn生命周期8项确已通过，较早配置拒绝另存；完整daemon静态207MiB仍超过可信profile界限。原device-owner独立入口构建/原strip后6.92MiB通过host结构检查，但未执行、不是完整daemon或G2。 |
| A08 Android | [AOSP与ABI](../support/android/README.md) 及 [物理设备 smoke](../compat/android/PHYSICAL_SMOKE.md) 分开构建、签名和验证限定测试APK。 | `f89023ac` 在用户指定 POCKET4 所连现有Android17手机已实际install/input/save/force-stop/relaunch/readback/cleanup通过，host196项在普通与优化模式各通过。[去设备标识收据](../results/integration/2026-10-23-audit-closure/mobile-app-f890/acceptance.json)仅证明限定APK场景，不提供Asterinas Android、ARM BSP或生产设备控制资格。 |
| A09 硬件/VMM | [平台调查](../support/hardware/DECISION.md)、[VMM gates](../support/vmm/GATES.md) 和 [生命周期模型](../support/vmm/device_lifecycle/README.md) 提供具体边界。 | 模型不执行真实 DMA/IOMMU/IRQ/reset。目标GPU、VMM、ARM设备的任务、撤销、静止、复位与恢复仍须真实实现和验收。 |
| A10 Rust UI | [五crate入口](../ui/README.md)、[Session期限/启动锁](../support/ui/BOUNDARIES.md)、[Notes双通道与持久owner接合](../support/ui/NOTES_ORGAN.md) 已有候选代码。 | 历史 egui/Weston/Notes只支持其固定 Linux host 场景。已接入 `6b16d38a` 原生Notes受控入口、AccessKit及主动动作/被动轮询独立队列；当前整合仍须执行严格IPC、慢速客户端、丢回执、原owner恢复与真实输入门禁。Notes内容仍是内存文档；通用设备target、完整IME/读屏、Asterinas显示输入、移动UI仍未资格化。 |

## 尚未取得的产品资格

| 资格 | 本检查点状态 | 完成条件 |
| --- | --- | --- |
| 生产授权与效果 | 未通过 | 原 provider、protected clock、external frontier、keyring、revocation、recovered writer、current-cut 按实际部署装配并执行；source manifest始终保留 `production.activation: disabled` / `effects_authorized: false`。 |
| 完整原生 F1 | 未通过 | 同一新内核/Hepta二进制运行原daemon、store、任务与恢复；原库store测试与no-turn生命周期都是子集。 |
| 原生生产 G2 | 未通过 | 真实 FinalUse→原 writer/outbox→内核效果→故障核对→持久终态→连续退役，包含丢回复、撤销、kill/reboot。 |
| 完整资源恢复 | 未通过 | 计入剩余内核/设备资源，可信暂停意图与原分配器物理保留、自主恢复、耗尽/碎片/SMP/时钟故障全部按相同profile验证。 |
| 通用桌面、移动与硬件 | 未通过 | 每个明确平台的配对、授权、输入/观测、动作、撤销和恢复；限定APK或Notes演示不能代替通用能力。 |

这里的“未通过”不抹除已经实现或已有局部收据的工作。后续关闭某一行时，记录完整 source/tree、工具链、feature、二进制/输入、实际命令、原始结果和剩余边界；没有执行就写未执行，不以新文档回填历史。

## 开发与文档交接

进入模块先读其 README 和共享合同，使用明确的工具链与最小相关门禁。每个变更要说明状态/权限 owner、I/O/错误、恢复和下一项验收。底层通用 crate 可复用 rustdoc/book，无需复制空模板。

根 README 允许导航内容，但必须是普通文件。`support/build/verify-source.py` 继续核对固定上游源、锁与枚举的派生；A02 继续把 README 字节和哈希纳入不可变输入快照。历史 `results/**` / `**/evidence/**`、旧快照及其验证器按原身份保留，不因新 README 规则而重写旧成功或失败。
