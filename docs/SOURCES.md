# 研究来源与基线

访问与复核日期：2026-10-16。仅列一手资料。来源描述不等于本项目已经实现相关功能。

本项目的架构、接口、资源参数、任务次序和验收规则是设计建议。以下资料用于支撑关键外部事实；动态网页不是构建锁文件，首次导入源码时仍须记录精确 commit、依赖与许可。

<a id="hepta-architecture"></a>
## Hepta 架构快照

固定 commit：`f8c9419df6ddeb36ff8b522a50219981fb8d9345`。本轮再次读取 main 后确认该快照。

[ARCHITECTURE.json](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/architecture/ARCHITECTURE.json)

支持的事实：现有单一 Codex 模型/工具执行主链、Agentd 组合职责、权限与效果边界、学习不能改变硬约束、本地恢复不应依赖中央智能可用。这里没有声称其模块已经实现裸机内核。

<a id="hepta-modules"></a>
## Hepta 模块和实际依赖

- [kernel.authority 技术文档](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/modules/kernel.authority/TECHNICAL.md)
- [kernel.operations 技术文档](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/modules/kernel.operations/TECHNICAL.md)
- [runtime.agentd 技术文档](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/modules/runtime.agentd/TECHNICAL.md)
- [hepta-agentd/Cargo.toml](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/Cargo.toml)

支持的事实：权限模块不是硬件驱动；操作持久实现与 CognitiveStore 有接合；Agentd 依赖现有宿主运行能力。目标契约注册和文档完成不能等同于产品运行完成。

<a id="asterinas"></a>
## Asterinas 候选基础

- [官方 v0.19.0 发布页](https://github.com/asterinas/asterinas/releases/tag/v0.19.0)
- [官方公告，2026-10-13](https://asterinas.github.io/2026/10/13/announcing-asterinas-0.19.0.html)
- [上游 RELEASES.md](https://github.com/asterinas/asterinas/blob/main/RELEASES.md)

截至复核，GitHub latest 返回 v0.19.0。发布 API 的 published_at 为 2026-10-12T21:37:46Z，而公告日期为 2026-10-13；两种日期分别记录，不混称。同版材料说明 DRM/KMS、软件 OpenGL、初步 AArch64、文件系统和 OSTD 虚拟化等进展。软件图形成果不能推出目标 GPU 计算能力，x86 与 ARM、guest 与 bare metal 也必须区分。

<a id="ostd-vmm"></a>
## OSTD 虚拟化边界

[RFC-0003: Hypervisor Support](https://asterinas.github.io/book/rfcs/0003-hypervisor-support.html)

支持的事实：底层虚拟化机制与上层 VM 控制、KVM 兼容接口和设备仿真分层。RFC 的批准和接口设计不等于本项目拥有完整 VMM，也不证明所有 CPU 虚拟化后端已实现。

<a id="starnix"></a>
## Starnix

[官方概念文档](https://fuchsia.dev/fuchsia-src/concepts/starnix)

支持的事实：Fuchsia 可以通过用户态 Starnix 提供 Linux ABI 运行未修改 Linux 程序。借鉴其架构不意味着将其直接移植到任意新内核即可获得全部兼容范围。

<a id="linux-abi"></a>
## Linux 用户态 ABI 与驱动接口

[The Linux Kernel Driver Interface](https://docs.kernel.org/process/stable-api-nonsense.html)

支持的事实：用户态接口与内核内部驱动接口有不同稳定性边界。Linux ELF 可运行不能推出现有内核模块、特定驱动或所有设备 ioctl 可直接复用。

<a id="aosp"></a>
## AOSP 架构

[Architecture overview](https://source.android.com/docs/core/architecture)

支持的事实：Android 平台由应用 API、Framework、系统服务、ART、HAL、native library 和内核等层构成；AOSP 本身不提供所有外部后端服务。兼容研究必须覆盖整个平台接合，而非只有 syscall。

<a id="android-cdd"></a>
## Android 17 CDD

[Android 17 Compatibility Definition](https://source.android.com/docs/compatibility/17/android-17-cdd)

用作本轮需求研究参照。其导言强调包括测试之外的行为兼容，设备类型部分也讨论替代 OS/内核的安全环境。具体适用要求要绑定所选设备类型与 AOSP 构建，不能只凭本文档声明 Android 兼容或认证通过。

<a id="android-native-bridge"></a>
## Android Native Bridge

[AOSP ART Native Bridge 文档](https://android.googlesource.com/platform/art/+/refs/heads/main/libnativebridge/README.md)

支持的事实：Native Bridge 提供不同 ISA/ABI 的接入机制，AOSP 不附带实际二进制翻译器。因此 ARM native 库在 x86 上执行属于独立实现和许可工作。

<a id="play-integrity"></a>
## Play Integrity

[Integrity verdicts](https://developer.android.com/google/play/integrity/verdicts)

支持的事实：设备完整性结果涉及认证、启动状态及某些版本上的硬件证明，应用服务端可以据此处理请求。本地 ABI 兼容与第三方服务是否接受设备必须分开记录。

<a id="vfio"></a>
## DMA 与设备隔离参考

[VFIO - Virtual Function I/O](https://docs.kernel.org/driver-api/vfio.html)

支持的事实：设备访问、IOMMU、设备分组和所有权共同影响直通与隔离设计。这里参考机制边界，不把 Linux VFIO 当作已可在新 Rust 内核使用的现成驱动服务。

<a id="sched-ext"></a>
## 可替换策略与回退参考

[Extensible Scheduler Class](https://docs.kernel.org/scheduler/sched-ext.html)

支持的事实：Linux sched_ext 为可替换调度策略提供错误时的回退行为。本项目借鉴策略/机制分离与可靠恢复；它既不是 AI 调度的效果证明，也不是最终 Rust 内核实现。
