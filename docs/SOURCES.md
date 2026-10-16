# 一手来源与精确基线

版本0.3，复核日期2026-10-16。研究来源支持相关外部事实；本项目方案与试验参数是设计选择。源码输入见 [upstream-lock](../support/upstream-lock.json)，其中缺失构建输入保持null。来源hash不是下载完成或运行证明。

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
