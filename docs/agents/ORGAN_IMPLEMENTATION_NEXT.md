# A–G 后续实施顺序：从已验收组合继续

更新于 2026-10-22。此页承接 [当前状态](../STATUS.md) 和
[实际组合证据](../../results/integration/2026-10-22-organ-qualified/README.md)，
不重复定义 HOS2，也不把文档、源码清单或 test issuer 当成生产资格。

## 已经固定的起点

桌面实际执行提交为 `85d394f99c73ad3194d57c876712ac01b59d90ca`，Hepta 为
`6d6097da843f5831dfaf9cee3530da512d072a15`。#240 的七项 CI 成功后，桌面按普通
merge 合入 `f85ccae8445f8d753572d41411d98ee28d253af5`；合并保留并行主干的证据和
ExFAT 测试增量。完整 core269、UI181/两个明确忽略、原 Agentd238/七跳过及另一次真实
GUI1、SQLite 四 boot、G1-d 三 boot 和真实 Agentd 普通 ABI preflight 各有自己的收据。

第一桌面切片已走通：原 writer → test issuer 授权 → 真实 Linux Session/Notes →
独立回读 → 原 writer committed。生产 issuer、原生 G2、原生桌面和实机仍需下面的
独立完成条件。普通 Session 不因此获得任意桌面控制权。

## 按依赖推进

| 优先次序 | 工作落点 | 必须拿到的完成证据 |
| --- | --- | --- |
| **1．收口 A 与 B 的发布输入** | 保留当前 green 基线；用 source profile 固定一对完整 head/tree；从原部署系统装配 provider、clock、frontier、keyring、revocation、current-cut、recovered writer。 | 真实原 owner 用同一组合提交；断连后只核对旧 K/D；未知保持 unknown。没有部署输入时 production 继续 disabled，不生成替代密钥或第二 writer。 |
| **2a．C 的生产 Linux Notes** | 沿现有 `services/hepta-os`、Session 私有 bootstrap 和 Notes receiver 替换测试 issuer 的装配来源，保留原 FinalUse/持久 owner。 | 一个实际应用完成观察→真实授权→动作→独立结果回读→原 owner 持久终态；过期样本、撤销、丢回复及重启均不误操作。之后再扩展第二应用，避免先铺无验收的大量 adapter。 |
| **2b．F1 最小原 daemon + D 原生接合，与 2a 并行** | 先测量实际优化构建及依赖，用原 FleetRegistry/Supervisor 完成无模型回合的 daemon/store 生命周期；结合 E 的最低隔离，再实现最终 exec 之后的可信 role/bootstrap，将真实 `AgentdHos2Device` 接到原 writer/outbox。 | 原 Agentd 真正在 guest 驱动原 CPU owner，原 outbox 保留不可变 K↔D 和完整 payload；终态持久确认后才允许连续 retire。丢回复、manager kill、重启均先 query/reconcile，不能凭当前 cap 推断旧操作终态。 |
| **3．E 的完整隔离与自主恢复** | 扩展已有低权限 workload、有限独立恢复和地址空间上限；按原契约实现可信暂停原因、公共 `RevokeGrant/ApplyRecovery`、独立 watchdog 与总进程树内存。 | manager 故障、租约过期、内存耗尽可恢复；合法用户暂停保持；fork/exec 不能逃逸累计资源控制；恢复者及祖先资源不受被管理域削减。 |
| **4．F2 的真实任务、app-server 与 UI** | 在 F1 原 daemon/store 和 D 接合已完成后，逐项补真实任务、app-server 与桌面的实际 Linux ABI/存储依赖。 | 真实任务、原终态和恢复发生在 Asterinas；同一 Rust UI 在 guest 有可测显示和输入，不把 host Weston 或 ABI 负向启动算作完成。 |
| **5．G 的固定硬件** | 先一台独立 x86 目标，再一块明确 SoC/板卡；固定 GPU、固件、IOMMU group、reset 方法、VMM 和 Android product/BSP。 | 实机执行任务、撤销、DMA 静止、复位、重启；ARM/Android 逐项验收启动、显示、触摸、存储、无线及电源。只读 inventory 和 x86 QEMU 不能转授这些资格。 |

F 应拆成 F1 与 F2：**原 Agentd 最小启动与原 store 生命周期是 D 的前置工作**；真实任务、app-server 与完整桌面则在 D 后继续。若把整个 F 排在 D 之后，D 就只能继续使用资格 C 程序，无法取得真实原 Agentd 驱动的 G2 完成证据。

A 的兼容回归和 B 的身份/授权检查必须贯穿后续切片。E 中真实 workload 隔离是 D/F
效果执行的前置条件；不能等所有产品功能完成后再补。GPU/ARM 的目标调查可并行，
完整设备开发不应阻断先完成一个 CPU 与一个应用的可恢复闭环。

## D：最先解决的不是再造协议，而是真实角色装配

原链路已经具备 `ProductionDurableWriter`、`LocalLeaseOutbox`、`CognitiveStore`、
FinalUse 和同步 HOS2 target。新增 ReadUsage 仍经过 `AgentdHos2Device`，不会生成新 D，
不会写 outbox，也不把采样当作操作确认。继续使用这些原 owner。

当前固定映像 profile 只接受小型静态 x86_64 ET_EXEC，无解释器、PIE 或 W+X；映像文件
上限 8 MiB、页对齐 LOAD 总量上限 16 MiB。实际 dev Agentd 是动态 PIE，不能直接套入。
应先构建和测量目标优化 profile，列出真实依赖；dev ELF 的尺寸不足以判定 release
不可行，也不足以证明要重写内核。若目标必须动态装载，应设计并验收最终执行映像和
依赖封装的可信交接，而不是仅放宽尺寸或跳过映像核验。

control fd 绑定实际 Process 与最终映像身份。通过 C shim 打开 fd 后 exec Agentd、
通过 SCM_RIGHTS 把 fd 传给另一进程、或直接信任 ambient fd/auxv 指针，均不能替代
可信交接。manager、workload、recovery 的实际入口应装配在原运行链上，恢复者必须
拿到独立权限；资格程序中的非持久 ack 不能冒充原 SQLite 终态。

manager 故障后，后继 writer 需要经过认证的新 current-cut；先用原 store 查询旧 D、
完成原持久核对，再退役连续终态。测试至少覆盖：效果已发生但回复丢失、持久提交前后
崩溃、旧 boot 请求、重复相同 D、相同 D 不同 payload、窗口满、恢复者重启、前缀有洞。
每个场景都应核对实际效果次数、原 outbox/store 和原 CPU/D owner，而不仅检查错误码。

## F：初始只读 atime 已修复，继续原 daemon 生命周期

[实际修复与证据](../../results/integration/2026-10-22-ext2-rdonly/README.md) 绑定 #243 的
`9076f1a…`：初始 RDONLY 下 buffered/direct/readdir 自动 atime 不再置脏，完整 core274/274、
SMP实际3/277、ordinary18标记与旧行为精确3失败负控均完成。同一冻结原 Agentd ELF 在
新 ordinary 内核中仍准确拒绝缺失配置，完整 serial 不再出现旧只读写回错误。

五个新增真实内核测试使用**可写 CountingDisk 上的初始只读 ext2**检查 atime 不变、
Write BIO 为零，并保留 RW 自动 atime 与已有脏数据同步的正控。真实 Agentd 复跑继续
保留只读 QEMU 后端；两类证据的作用分开。源码已发布，但远端 CI 与合并不能由本地
原生通过代替。A 的下一步先收口该修复的 CI，再继续 B/C/D/F 的原 owner 装配。

不要把 RO 下 sync 简单改成返回成功：RW→RO remount 的旧脏数据仍须正确排空。
VFS write/resize/xattr/时间修改入口、bind/remount 与 virtio/block RO 协商是另外的
语义门槛。一次局部 atime 修复不得升级成完整只读权限保证。原 SQLite WAL/FULL 的
突然 guest 重启资格也不覆盖真实断电或设备易失缓存丢失。

下一 daemon gate 必须让原注册库和 supervisor 分配 identity、generation、cwd/home/run
环境，再启动原命令。不能手写 Starting 状态或伪造 generation 来满足测试。先用无模型
回合的原 fixture 验证实际启动/停止和 store，再接原任务与恢复；保留每一步真实失败。

## 什么时候才考虑替换 Asterinas

当前继续完整 Asterinas 派生，按固定 upstream/nightly 维护小而可审阅的 patch 队列，
把 Linux ABI、文件系统和设备缺陷落回原对象。Hepta 保持用户态策略、授权与持久历史
的原执行链；内核负责权限、资源执行和有界恢复，不依赖模型做快速路径决策。

只有可复现的接口、锁/调度结构或平台约束证明这条路线无法达到已明确的目标，且
修复/维护成本经过对比后明显不合适，才重议 [D01](../DECISIONS.md)。那时先考虑保留
OSTD 并逐个替换有证据的子系统，复用当前 ABI、Linux 差分、崩溃与设备验收集。完整
重建 Rust kernel 会同时承担内存、进程、信号/TLS、调度、VFS/持久性、网络、驱动和
工具链工作；目前没有新的结构性证据支持并行开启第二套产品内核。

## 文档交接要求

[模块审计](MODULE_DOCUMENTATION_AUDIT.md) 已清点 11 个交付领域及实际 Cargo 模块。
每个新切片应更新所属模块的技术与开发入口，至少记录源码 owner、输入/输出、权限、
状态迁移、并发/持久化、构建运行命令、负控、失败恢复和未通过边界。共享手册可以
继续使用；应补清真实缺口，不用空模板把“有文件”包装成可交接或已完成。
