# 一手来源与精确基线

本页同时定位当前 Linux host 接合和保留的研究基线。后面的版本0.3来源固定在2026-10-16，不自动随产品 Cargo pin 变化；其原链接、哈希和未完成记录继续保留。研究来源支持相关外部事实；本项目方案与试验参数是设计选择。源码输入见 [upstream-lock](../support/upstream-lock.json)，其中缺失构建输入保持null。来源hash不是下载完成或运行证明。

<a id="hepta-native-organ"></a>
## 当前原生 organ 接合来源（2026-10-24）

当前 Desktop 三处实际 Cargo 入口为 [UI root](../ui/Cargo.toml)、[UI core](../ui/core/Cargo.toml) 和 [Session host](../services/hepta-session-host/Cargo.toml)，所有 Hepta Git 依赖与原补丁统一固定在 `52456c309f64ee80e7e377f774445c5dfe0523c9`，tree `9d0949a72d064cc2222859780c6ccd9a22c8e575`。UI root 同时显式固定四个原 AccessKit crate；依赖 workspace 的 patch 不会自动传递。`services/hepta-os/Cargo.toml` 没有 Hepta Git dependency，其原协议合同和各历史 pin 继续各自保存。

| 原 owner / 模块 | 同一固定 Hepta commit 的开发与技术入口 | Desktop 接合入口 |
| --- | --- | --- |
| 全局开发与 organ 架构 | [DEVELOPMENT](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/docs/DEVELOPMENT.md)、[CNS/organ](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/docs/cns/README.md) | [架构与原 owner](ARCHITECTURE.md)、[当前模块交接](agents/NATIVE_ORGAN_MODULE_HANDOFF.md) |
| Root / AuthBus / Agentd 文本 | [NATIVE_TEXT_SESSION](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/codex-rs/hepta-agentd/NATIVE_TEXT_SESSION.md) | [TextChatAdapter 开发/技术手册](../services/hepta-session-host/TEXT_SESSION.md) |
| 原 Makepad / ChatWorkspace | [NATIVE_COMPOSITION](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/apps/hepta-control-ui/rust/robrix-ui/NATIVE_COMPOSITION.md)、[UI README](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/apps/hepta-control-ui/rust/robrix-ui/README.md) | [Shell](../ui/shell/README.md)、[原窗口验收](../support/ui/NATIVE_MAKEPAD.md) |
| 原 AccessKit 与独立 clipboard SDK 候选 | [AccessKit patch](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/codex-rs/third_party/accesskit-0.17.1/HEPTA_PATCH.md)、[固定 SDK patch/feature](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/third_party/makepad-patches/README.md) | [默认/候选 profile 与 lock](../support/ui/PRODUCT.md#explicit-original-sdk-clipboard-candidate) |
| 原 Notes writer / 旧 incarnation 恢复 | [Notes qualification](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/codex-rs/hepta-agentd/NOTES_RECOVERY_QUALIFICATION.md) | [Notes durability](../support/ui/NOTES_DURABILITY.md) |
| 原 Android text target | [PRODUCTION_ANDROID_TEXT](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/52456c309f64ee80e7e377f774445c5dfe0523c9/codex-rs/hepta-memory/PRODUCTION_ANDROID_TEXT.md) | [原 receiver 的构建/签名/恢复合同](../support/android/receiver/README.md) |

链接定位已发布的固定源码，不授予生产或设备资格。[最新 v10/v11 scoped 收据](../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)与[当前能力](CURRENT_CAPABILITIES.md)区分原单包执行、默认 SDK 与独立候选、ignored/unselected 以及最终完整产品待验项。最终 Desktop source profile 还须记录完整本仓 commit/tree、实际 Cargo 生成的锁、features 和对应运行产物。

<a id="hepta-architecture"></a>
## Hepta架构

固定 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`：[架构注册表](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/architecture/ARCHITECTURE.json)。支持单一Codex主链、权限/学习分离及本地恢复边界，不代表裸机内核实现。

<a id="hepta-modules"></a>
## Hepta实际接合

[Agentd技术文档](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/modules/runtime.agentd/TECHNICAL.md)；[invocation provider源码](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/intelligence_ingress.rs)；[配置接口](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/config.rs)；[真实宿主及剩余工作](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/readiness/LANE_B_NATIVE_HOST.md)；[authority](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/modules/kernel.authority/TECHNICAL.md)；[operations](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/docs/modules/kernel.operations/TECHNICAL.md)。

规范智能能力需真实runner与宿主provider/owner装配，普通启动不自动提供；源码位置不代表本项目运行通过。

<a id="asterinas"></a>
## Asterinas锁定来源

[v0.19.0标签](https://github.com/asterinas/asterinas/releases/tag/v0.19.0)解析至 `c4b7ed575b7b32773475b194d2ad41fb6d03765b`，tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`。[精确工具链](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/rust-toolchain.toml)为nightly-2026-07-21；[sys_ioctl](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/kernel/core/src/syscall/ioctl.rs)提供真实FileLike分派点；[源码树](https://github.com/asterinas/asterinas/tree/c4b7ed575b7b32773475b194d2ad41fb6d03765b)。

官方release metadata给出x86_64 ISO 1442840576字节，SHA256 `7df9fafed4fe886e44bda501834937d893e12a05af911fabeb068c34379fb86e`。来源锁定阶段没有下载该ISO；0.3轮尝试下载但未完成，失败记录见results/reference-iso-probe.json。发布API时间为2026-10-12T21:37:46Z，[公告](https://asterinas.github.io/2026/10/13/announcing-asterinas-0.19.0.html)日期为2026-10-13，两者分别记录。软件图形与初步ARM进展不证明本项目GPU或实机支持。

<a id="ostd-vmm"></a>
## 虚拟化

[OSTD RFC-0003](https://asterinas.github.io/book/rfcs/0003-hypervisor-support.html)：底层虚拟化与VMM管理/设备模型不同，不将Intel机制外推为AMD/ARM实现。

<a id="ioctl"></a>
## Linux ioctl

[ioctl设计](https://docs.kernel.org/driver-api/ioctl.html)：固定宽度字段、显式padding、compat、有限大小字段、未知命令errno及版本演化。HOS的32字节transport和内部wire是本项目选择，尚无实际ioctl分配。

<a id="linux-abi"></a>
## Linux ABI和资源

[驱动接口稳定性](https://docs.kernel.org/process/stable-api-nonsense.html)区分用户态与内部驱动；[cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html)的cpu.max与层级限制供语义对照。HOS cap不是保底；本项目不能因采用相似概念就声称兼容所有cgroup行为。

<a id="dma"></a>
## DMA

[DMA guide](https://docs.kernel.org/core-api/dma-api-howto.html)：地址隔离、缓存同步、coherent内存与屏障分别处理。

<a id="vfio"></a>
## 设备隔离

[VFIO](https://docs.kernel.org/driver-api/vfio.html)：IOMMU分组、设备所有权及隔离条件；不是本项目现成驱动后端。

<a id="sqlite"></a>
## 持久化

[SQLite原子提交](https://www.sqlite.org/atomiccommit.html)：锁、同步与故障假设。应检查其rollback journal/WAL各自路径；本项目S1资格尚未测试。

<a id="aosp"></a>
## Android平台

[AOSP架构](https://source.android.com/docs/core/architecture)：保留Framework/ART/HAL用户态，不把APK兼容等同于syscall。

<a id="vintf"></a>
## VINTF

[VINTF](https://source.android.com/docs/core/architecture/vintf)：device manifest与framework compatibility matrix需对应实际产品。

<a id="aidl"></a>
## AIDL HAL

[AIDL HAL](https://source.android.com/docs/core/architecture/aidl/aidl-hals)：稳定版本/实例是产品接合输入。

<a id="android-cdd"></a>
## Android17 CDD

[9.7 Security Features](https://source.android.com/docs/compatibility/17/android-17-cdd#9_7_security_features)：C-2-1等效MAC；C-0-6多线程可配置系统调用过滤。[9.8.18 Agentic Functions Privacy](https://source.android.com/docs/compatibility/17/android-17-cdd#9_8_18_agentic_functions_privacy)：AppFunctions执行权限/预装、明确用户行动和告知；敏感环境数据用于主动提示另有要求。这些具体条款不能被一般长期OS授权自动替代。

<a id="lmkd"></a>
## Android压力控制

[lmkd](https://source.android.com/docs/core/perf/lmkd)：PSI、内存域等实际依赖需在选定AOSP版本核对。

<a id="pages"></a>
## 页大小

[16KiB页](https://source.android.com/docs/core/architecture/16kb-page-size/16kb)：页大小/ELF/native库列入profile，不永久硬编码4096。

<a id="android-native-bridge"></a>
## 指令翻译

[Native Bridge](https://android.googlesource.com/platform/art/+/refs/heads/main/libnativebridge/README.md)：接入机制不附送完整翻译器；主线链接不是构建锁定值。

<a id="play-integrity"></a>
## 外部完整性

[Play Integrity verdicts](https://developer.android.com/google/play/integrity/verdicts)：设备/服务判定与本地ABI兼容分开，不伪造证明。

<a id="x11"></a>
## 桌面信任

[X.Org安全模型](https://www.x.org/Development/Documentation/Security/)；[Wayland架构](https://wayland.freedesktop.org/docs/book/Introduction.html)。X11共享信任域不能自动当逐应用隔离。

<a id="starnix"></a>
## 兼容架构参照

[Starnix](https://fuchsia.dev/fuchsia-src/concepts/starnix)证明非Linux宿主可实现Linux用户态接口；不宣称可直接原样移植。

<a id="sched-ext"></a>
## 调度策略参照

[sched_ext](https://docs.kernel.org/scheduler/sched-ext.html)：可替换策略与故障回退参考，不是新Rust内核或AI收益证明。

## 0.3补充接合来源

[Asterinas固定调度类源码](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/kernel/core/src/sched/sched_class/mod.rs)和[固定x86计时入口](https://github.com/asterinas/asterinas/blob/c4b7ed575b7b32773475b194d2ad41fb6d03765b/ostd/src/arch/x86/mod.rs)：共同调度路径与TSC频率/单位需要实际接合，不能只改fair或把tick当ns。

[Hepta持久结构](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-operations/src/durable_model.rs)：与参考结构分开使用，owner_generation不是逻辑身份。HOS2是本项目设计，不是上游已实现接口。

[Asterinas NixOS安装说明](https://asterinas.github.io/book/distro/)将发布ISO作为安装介质；下载或启动安装器都不能自动计为本项目Rust内核运行。此次下载未完整，结果保留失败。
