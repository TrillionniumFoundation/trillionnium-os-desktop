# 架构决策 0.3

本页只记录选择和改变选择的条件；真实进展见STATUS，共同原则见INDEX。

## D01：完整Asterinas派生为首条主线

固定v0.19.0提交与nightly，复用任务/VFS/网络/ABI与OSTD，新增资源与能力接口附着已有对象。仅复用OSTD并重建上层不再与主线混用。重新选择必须提供不可解决的接口冲突、最小复现及修改成本；没有这些不分裂第二主线。

## D02：原生Hepta仍是用户态、原有执行主链

第一阶段保持Linux ELF，通过窄的内核控制接口提供真正原生系统能力。真实宿主profile必须包含现有runner/provider/owners，普通daemon启动不替代。独立应用ABI不属于初期交付。

## D03：有限协议优先于大量空操作

HOS2首期包含QueryAbi、ReadUsage、InstallBudget、QueryDelivery和RetireThrough，完整定义输入/输出/错误/身份/结果重取。资源域由可信init配置；动态迁移/Transfer/SubmitIo暂不提供wire，不分配未实现能力的编号。后续按真实需求增加并独立验收。

## D04：CPU上限而非保底

首期单CPU、固定100ms周期、不支持period变化和迁移；更新保留已使用量，父域限制聚合。需要SMP/预留/deadline时单独给并发算法和实际界限，不把cap当保底。

## D05：统一对象权限与两层身份

原生/Linux/Android入口共同受对象owner限制。control会话绑定打开进程，不以fd传递授管理权。K跨boot由原Hepta owner保存，D在本boot去重；digest存在记录中而不在查找键里。关闭新准入、停止硬件、零效果是不同事实。

## D06：保留AOSP与兼容用户态

Android平台构建、VINTF/MAC/内存压力/页大小作为明确任务。Rust原生UI不迫使ART/Xwayland等兼容组件也重写。外部完整性/服务认可分开记录，不伪造资格。

## D07：存储路线分层

开发输送S0不提供原生耐久承诺；S1选virtio-blk+上游Ext2作为待测候选，未通过前只用合成数据。发现不满足所需崩溃语义后，用最小复现决定修复或单次选型调整，不平行开多个永久存储栈。

## D08：调查前置、完整实现按依赖

GPU/VMM/Android product/首台实机可行性与M0并行；完整设备实现不阻断CPU接口。普通客户端先于Hepta，分离ABI和宿主装配失败。

## D09：AI必须可比较、可退出

保留固定与非AI反馈对照、Linux等价接口对照；观测过期不加大cap，推理成本纳入。没有可测净收益就保留可靠默认，不强制全部系统动作经过模型。

## 尚未完成的选择/输入

容器digest、rootfs构建清单、固件、实际AOSP tag/product、首台裸机和GPU后端尚需验证。记录缺项而非发明值；源commit固定只是可复现构建的一部分。运行状态不得因为选型写入而提升。

## D10：显式HOS2恢复协议

新有序写ID和恢复操作不重新解释HOS1。结果窗口以连续退役前沿防重放，DeliveryView独立于管理句柄；只有已持久确认的终局可退役。启动授权在最终exec后可信激活；旧效果不明与新授权目标收敛分别记录。

## D11：原 owner 的映像预算单独版本化

2026-11-03 的原 Hepta owner 保持原 Cargo release profile、默认 features 和锁文件，实际编译和原版 strip 均已完成。其 ELF 为 20,138,584 bytes，页对齐 LOAD 合计 20,168,704 bytes；旧实验 profile 的 8 MiB 文件 / 16 MiB LOAD 上限仍然拒绝该产物。[后续证据](../results/integration/2026-11-03-organ-followup/README.md) 分开记录原失败和已修复的打包问题。这是原用户态产物与早期实验映像预算不匹配，不构成重建 Rust kernel 的理由。

继续完整 Asterinas 派生主线。下一候选为原 owner 建立独立版本的实验映像 profile，绑定实际 ELF 摘要、文件长度、LOAD 总量和最大段页范围。保留旧 G1-c、G1-d 与 G2 profile 的原始限制、输入检查和失败记录；新候选不能使用旧 profile 名称宣布通过。普通 exec 的通用装载路径也不因此改变。

新 profile 继续复用[原可信映像装载器](../kernel/asterinas/kernel/core/src/process/program_loader/elf/trusted_initial.rs)的一次性不可变快照、完整字节匹配、独立 RAM VMO、映像读回和封印，不增加用户态自行选择的尺寸或权限。原 writer/outbox、授权核验和持久终态语义保持原 owner 所有。依赖与单态化优化可以另行测量；不能删除这些原闭环代码或改变 panic 语义来冒充同一产物满足旧预算。

这里记录实现方向，不声明新 profile 已编译、已在 guest 执行或取得生产资格。后续每个结果必须携带确切源码、profile、产物与内存范围。

## D12：镜像准入与恢复资源保证分别验收

当前[四角色启动事务](../kernel/asterinas/kernel/core/src/process/process/init_proc/trusted_daemon.rs)共享一次原映像快照，但 root、manager、workload、recovery 分别建立私有 LOAD 映射。workload 已显式附加 UserMemoryAccount；其余三个角色及其后继路径尚未具备等价的完整总内存准入保证。映像通过尺寸检查不能推导四角色运行时资源均已隔离。

内存核算需要覆盖内核中嵌入的 ELF、长期快照、四份 LOAD、逐段写入/读回临时缓冲、实际栈、initramfs/cache、页表与内核分配、SQLite/线程/堆，以及重启时旧实例与新实例的短暂重叠。固定 512 MiB guest 的实际低水位和恢复期间峰值必须单独记录；静态映像算式不替代运行时测量。

继续沿同一进程/VMO/资源域做进程树计账和准入，并明确控制面、恢复者及其 I/O 所需的保留资源。已有用户页限制、64 页 allocator 保留和独立 watchdog 证据分别保留其范围，不能合并为全内核物理资源保证。job-control stop 与可信用户主动暂停也分别处理；在可信暂停入口完成前，不把前者的保持测试扩写成后者已合格。

## D13：跨应用准入以原持久 sender/writer 为准

当前 v1 双应用候选继续要求同一原 turn 最多一个受控效果。Notes 与 Calculator 共用原 sender 对该 turn 的持久准入约束，沿原 writer/outbox 保存操作、独立回读和终态；目标、工具名或 callback ID 的不同不产生额外执行机会。未来若支持一个 turn 内的多步骤，需要在原 owner 内定义步骤顺序和持久恢复合同，另行版本化与验收。

这个选择来自原 `a39` 的具体接口语义。[Core 动态工具入口](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/a39a0871d9601ffccb5e0d95d8f39d54b3a63360/codex-rs/core/src/tools/handlers/dynamic.rs)先登记 pending response，再发送 ItemStarted。[Session 事件路径](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/a39a0871d9601ffccb5e0d95d8f39d54b3a63360/codex-rs/core/src/session/mod.rs)先尝试追加 rollout，但该普通追加函数只记录错误和失败代际，仍可能继续投递事件；它与要求 append/flush 成功的 strict 路径有不同语义。[ThreadItemsList](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/a39a0871d9601ffccb5e0d95d8f39d54b3a63360/codex-rs/app-server/src/request_processors/thread_items_legacy.rs)在 legacy 分支还会合并活动 turn 状态。因此，原连接上的 callback 和列表回读可以核对来源与当时的顺序，但不能单独证明列表已经持久化或具有完整的持久顺序。

候选在选择本轮首个效果前查询原 sender 已保留的同 turn 请求；当前 callback 和原人类输入的来源核验仍有自己的只读前置步骤。通过这些核验并发现已有请求后，后续 callback 就按原操作只读核对；另一个 App 或另一个 call 的请求必须明确返回未执行。返回内容保留首个原 tool、destination、target、operation 和 receipt 的身份，UI 不把其他 App 的既有成功显示成本次执行成功。缺失列表、未知结果、断连或重启都不能清除这个持久约束，也不能据模型输出推定外部效果失败后再执行。

原 AuthBus/queue 的人类输入持久证明、Core callback 身份与原 writer 的外部效果终态各有范围。该候选不承诺“最早持久化的 Core 工具项必定先执行”；最终被原 sender 接受的请求以其持久事实为准。实现必须在真实 SQLite sender/writer 上验证两应用顺序反转、并发竞争、丢回复及重开后的只读核对，并单独完成真实授权与两应用窗口验收。这里记录合同和依据，不给尚未运行的联合候选授予通过资格。

## D14：有限原授权装配与长期运行分别交付

当前 `fd/a39` 的[实际优化构建、测试和安装](../results/integration/2026-11-03-organ-followup/owner-p0-fd-v5/README.md)已完成，但产品组合仍是最多 300 秒的原 authority 限时装配候选。[Root 输入](../services/hepta-session-host/src/product_root/config.rs)接受 120–300 秒，[人类会话 provider](../support/ui/product/native_human.py)、原 Hepta [launcher](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/a39a0871d9601ffccb5e0d95d8f39d54b3a63360/codex-rs/hepta-agentd/src/production_launcher_inputs.rs)及[authority 服务](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/a39a0871d9601ffccb5e0d95d8f39d54b3a63360/codex-rs/hepta-agentd/src/authority_host_runtime.rs)各有自己的有限窗口。安装通过或一次效果通过，均不证明常驻生产运行与自动续期。

[现有 writer 到期计算](../services/hepta-session-host/src/product_root/recovery_authority.rs)为 `now + min(180s, issuer_remaining - 60s)`；原 full-owner recovery 等待旧 writer 实际到期后再次使用同一公式。首 writer 创建时若 issuer 剩余不超过 240 秒，首 writer 会占用到 issuer 到期前 60 秒，届时没有正的 successor 窗口。计划完整恢复验收应从允许的 300 秒初始化，并记录实际到期值与准备耗时；这不是恢复一定成功的保证。不能事后改 config、改时钟或修改原 lease 冒充原授权仍然有效。

原 [ProtectedLease](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/a39a0871d9601ffccb5e0d95d8f39d54b3a63360/codex-rs/hepta-agentd/src/deployment_issuer_root.rs)同时固定 lease ID 和 revision，每次发行与观察都重新核对。底层注册表的 revision CAS 或 epoch 推进不等于产品续期：改变 revision 会使现存 issuer 拒绝旧绑定，推进 epoch 还会隔离旧授权。当前产品入口没有将这些原能力装配为连续运行事务。

长期运行应在原 owner 内增加显式、可中断后核对的重新授权与代际接续：先冻结旧代际的新效果准入，保留原请求、未知操作和已持久终态；原 Root 在新的真实人类会话授权下建立有限的新 issuer/writer proof 及受监督通道；原 consumer 前沿、Current、撤销和任务身份完成一致交接后才开放新动作。每一阶段必须记录持久状态，重启后核对同一事务，旧未知操作继续只读核对，不按新的 call、目标、prefix 或 thread 重发。该事务尚未实现或验收，不以放宽 300 秒常量替代。

真实人类准入还要求原同 UID 的活跃本地图形 logind、原 Shell 的存活身份及 AuthBus 已确认输入。私有 Xvfb 的窗口证据不替代该身份来源。若以后支持远程或无图形生产准入，应为原 Root 和 Hepta 实现独立版本的可信身份、会话寿命、撤销与原 route 绑定；当前版本不存在可以绕过这些前置的配置开关。
