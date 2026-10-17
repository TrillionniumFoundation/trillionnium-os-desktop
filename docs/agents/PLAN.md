# 多 Agent 并行开发执行方案（2026-10-16）

项目：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。初始规划绑定主干 `e4b2086b0ea28a20b6e721928b925555c0dc3bc8`；该快照的“仅规格”状态已经过时。2026-10-17 核对的 `146dedf75c5729ef1930c845eeb60e31e8111c60` 已有 Rust codec/control core、原生只读 QueryAbi 的 Process / exec 镜像隔离和实验 CPU 配额；G1/G2 仍未闭合。本文保留职责与依赖，开工进度以 [STATUS](../STATUS.md) 的固定源码与真实证据为准。README.md 根文件必须始终为 0 字节。所有成果提交到本仓库，按真实测试记录进度。

## 并发策略与依赖

建议 1 名集成负责人 A00 + 10 名专业执行 Agent A01–A10，不按 GitHub runner 数量硬拆工作。第一波可真正独立推进 **A01、A02、A03、A04、A08、A09、A10** 七个执行任务；A00 同步统筹。第二波 **A05、A06、A07** 的接口研究可提前，但写入共享内核源码须等待所依赖的基础被合并。

~~~text
A01 Asterinas source/QEMU --+
A02 HOS2 Rust codec --------+---> G0: 可启动基线 + 接口/状态核心
A03 HOS2 control core ------+                 |
A04 Linux/Hepta ELF baseline+--> W1 ------------+--> A07 Hepta adapter
                                                |
                                    A05 process/ioctl/capabilities
                                                |
                                    A06 scheduler/resources
                                                |
                                      G1: 非AI真实W0
                                                |
                                      G2: Hepta到内核W1
A08 Android 研究 ------------------------------> G3 扩展兼容
A09 GPU/VMM研究 -------------------------------> G3 实机计算
A10 Rust UI主机原型 ---------------------------> G3 UI新内核移植
~~~

G0 的“通过”必须区分源码编译、主机模型和内核启动：A01 原 Asterinas 最小构建/QEMU、A02 独立黄金数据驱动 Rust codec、A03 Rust 状态机对抗测试。A01 不需要下载发行版 ISO 才能启动小 initramfs。G1 是 A05+A06 在同一 Asterinas 派生内核上用普通客户端验证控制、权限、实际预算与故障。G2 是 A07 的真实 Hepta 操作 owner 与 G1 接合，必须覆盖持久确认、查询、退役、revoke、kill、reboot。G3 扩展 Linux/Android/GPU/桌面，不阻塞 G0/G1 研究。

## 文件独占与允许的交叉

| Agent | 主路径 | 同步条件 |
| --- | --- | --- |
| A00 | docs/agents/**、docs/INDEX.md、docs/STATUS.md、docs/NATIVE_ABI.md、.github/workflows/** | 唯一协调跨所有权改动 |
| A01 | support/build/**、support/upstream-lock.json、kernel/asterinas/** **初始导入/构建** | A05/A06 开始内核代码后 A01 不再改其核心源码 |
| A02 | libs/os-abi/**、tests/golden/**、tests/abi/** | HOS2 wire 改动须经 A00 统一 |
| A03 | libs/os-control/**、tests/control/** | 消费 wire 但不自改 codec/golden |
| A04 | compat/linux/**、support/rootfs/**、tests/workloads/linux/** | 兼容缺口先给内核 owner 最小复现 |
| A05 | kernel/asterinas/kernel/core/src/process/**、syscall/ioctl.rs 与邻近控制模块；tests/kernel/control/** | 取得 A01+A02+A03 的基线；A06 仅经约定 ResourceDomain 接口对接 |
| A06 | kernel/asterinas/kernel/core/src/sched/**、tests/kernel/scheduler/** | A05 先固定进程身份/资源句柄 API；OSTD 公共更改由 A00 协调 |
| A07 | services/hepta-os/**、tests/integration/hepta/** | 上游 Hepta 只读，必要修订单独小 PR |
| A08 | compat/android/**、support/android/**、tests/workloads/android/** | Android 与内核改动需 A00 指派所有者 |
| A09 | support/hardware/**、support/vmm/**、tests/hardware/** | 不接管现役设备或核心驱动 |
| A10 | ui/**、tests/ui/**、support/ui/** | 宿主 Linux 原型不是目标内核运行 |

上述源码位置定义所有权，不能用目录是否存在判断模块资格。当前主干已有完整 Asterinas 导入；A05/A06 共用该源码与同一个 cgroup 资源事实，不得各自维护一份上游。尚在 owner 分支的模块入口见 [INDEX](../INDEX.md)。

## 启动、提交与集成规则

1. 每个 Agent 从当时实际 main 建立独立 agents/Axx-* 分支。每个可验证 commit 都 push 远端并维护指向 main 的 PR；只让 A00 协调最终集成。不要同时在同一内核文件写入互斥补丁；遇到冲突交最小复现而非覆盖。
2. A00 合并共享 ABI、ResourceDomain、持久字段映射时，先检查对应 consumer 的实际编译与负面测试，再更新统一 docs/STATUS.md。任何人不得因“对照模型通过”宣称新内核运行。
3. 轻量 CI：空 README/文档链接、相关 crate 构建/单测、单一路径 QEMU smoke、必要 W1 对照；重型矩阵按改动范围运行。拥有大量 GitHub runner 并不等于强制无意义任务同时占满。
4. 每个 PR 记录：基线与 HEAD、实际变更、完成的测试命令/环境/分母、未完成项、下一条 blocker、是否更改 ABI/权限/持久化/设备。失败不隐藏，测试不要求人为逐层审批。
5. Hepta 的 Codex/Agentd/Operations 只有一条既有执行主链和持久 owner；禁止新建重复授权、效果账本、根权限后门。现役交易服务、模型工作流、系统盘和设备保持原样。
6. 与 HOS2 相关的已知债务必须有 owner：A02 修三份单 CPU 黄金样本和 mutation 漏检；A03 测挂起前缀/错误发布者；A05 实现能力交接/历史观察；A06 实现时间与调度限制；A07 完成持久 K↔D、ack、接替和前驱实测。

## 是否可以发布的定义

G0、G1、G2 分别作为清楚的**工程成果**而非行政认证。G0 没有真实 kernel QEMU 不能称内核可启动；G1 不包含实际 CPU 节流不能称原生控制；G2 只有模拟 provider 或没有持久历史/故障接替不能称真实 Hepta 端到端。Android APK、GPU 本地推理和 Rust GUI 通过也要分别记录其所在宿主，不能外推所有应用兼容。

## Agent 提示词

每份 [PROMPTS](PROMPTS.md) 对应独立可复制文字；正式交付以 [prompts/](prompts/) 内的每个 Agent 专用文件为准。这些 Prompt 定义职责，不会自动启动云端 Agent。
