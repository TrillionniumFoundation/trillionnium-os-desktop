# 按实际依赖推进的开发路线

技术依赖沿用0.3，当前实施起点见 [能力表](CURRENT_CAPABILITIES.md)。调查、上游复现、新增实现和真实验收分别记录，不以文档通过代替代码或设备结果。

## 当前接续顺序

1. 固定最终两仓source/tree、features与部署输入，重建/验证新的source profile；历史10-22清单不覆盖当前Notes bootstrap v2/recovery v1。
2. 沿原authority/writer运行UI目标到限定target，再做真实回读、持久终态与未知态恢复；已有transport/owner源码分别按所属包验收。
3. 在同一ordinary内核上执行原Agentd生命周期与store门禁，再接最终exec身份和原生G2。单独的store guest成功不关闭daemon或生产效果。
4. 对已加入的用户数据页限制、独立timer watchdog、Session期限和Notes恢复重跑相同profile的正反门禁；继续实现完整资源保留和可信暂停，不把局部机制当完整恢复。
5. 按确定的桌面/手机/硬件目标完成输入、观测、授权、撤销与恢复。Android兼容、物理限定APK测试、远程手机控制和移动客户端是不同交付。

以下M0–M6描述技术依赖，已有部分实现不应重复重建。末节保留10-17基线，不能作为当前缺口清单。

## 1. 主路径

```text
M0a 固定完整上游/构建输入 ──> M1a 复现上游启动
M0b ABI/对象规格 ──────────> M1b 编解码库/普通客户端
M0c Hepta真实Linux依赖盘点 ─> M1c 必需兼容子集/存储资格
M1a + M1b ────────────────> M2a 新内核资源实现+非AI控制客户端
M2a + M1c ────────────────> M2b 真实Hepta宿主profile接合
M2b ─────────────────────> M2c cap/历史查询/退役/revoke/kill/reboot闭环
M2c ──> M3 扩展Linux工作负载 / M4 Android平台 / M5裸机本地AI
M3 + M4 + M5需要的子集 ────> M6 Rust桌面与指定应用产品化
```

M1a是上游复现，不是宣称新增内核代码。M1c只需Hepta实际用到的线程/IPC/锁/SQLite等，不等待全部Linux功能；这些必要子集不再排到Hepta闭环之后。各平台工作按真实接口依赖并行，不能将完整Android/GPU列成首个CPU接口的前提。

## 2. M0–M2 技术工作与验收条件

| 项目 | 下一条具体工作 | 完成标准 |
| --- | --- | --- |
| M0a | 使用support/upstream-lock.json锁定源码；验证完整上游tree、Cargo.lock及许可来源 | 源码checkout与依赖输入可重现，不只写版本号 |
| M1a | 固定构建容器digest、QEMU/firmware、rootfs manifest与内核配置，按上游入口构建启动 | 实际kernel产物hash、完整serial日志、退出结果 |
| M1b | 维护已实现的五操作no_std codec；统一待决语义并保持独立负例/编译变异验收 | 固定头/请求/响应、截断/溢出/unknown/保留位/容量覆盖；证据绑定实际源码与工具链 |
| M1c | 原Linux构建真实Hepta profile与trace；建立W1必要接口清单 | 明确到ELF、依赖、实际owner装配，不把上游缺口误归OS |
| M2a | 在上游FileLike/ioctl/进程/调度对象接入CapSpace、单CPU预算与投递表 | 非AI客户端真实安装/观察；fd绑定、CAS、同值更新不充值、copyout重取 |
| M2b | 接现有Agentd invocation provider/主工具链，保持K/D身份与状态owner | 实际Hepta请求到新内核，非mock结果 |
| M2c | 受控revoke、停桥/模型、重启及未知操作核对 | 独立应用/I/O继续；不放大权限、不新ID重放 |

M1b 已有真实 Rust 编码/解码和独立验收，入口为 `tests/abi/run_acceptance.py`。文档检查或旧规格模型成功不能替代该代码证据；具体执行失败记录在STATUS，不改变本节技术依赖。

## 3. 构建输入与自动化

研究source pin不等于build lock齐全。support/upstream-lock.json记录真实kernel/Hepta commit、上游nightly和已核查release asset digest；rootfs manifest、容器digest、firmware缺项用null和ready=false，不能臆造。ISO hash是发布元数据，不声称已下载验证本地字节。

导入时固定工具链target/Cargo.lock/依赖来源/内核配置/QEMU/固件/rootfs。host辅助codec的Rust可以独立于上游内核nightly，但都必须记录实际版本，不偷偷用host stable替代kernel nightly。

最小自动化：README普通文件与本地链接、相关库单测、单一kernel build/QEMU smoke、变更涉及的兼容回归。定向 CI 只在真正源码存在且运行完成时计入实测，不将 queued/仅 CodeQL 视为 Rust 编译通过。GitHub原有权限与分支规则按实际状态使用，不为避测试修改仓库安全设置。

## 4. 与主线并行的风险消除

R-GPU：选定一台候选设备，列驱动/固件/队列/共享/复位所需机制，比较原生/服务域/VM并选择优先路线。

R-Android：固定可获取的AOSP manifest/product和VINTF/MAC/页大小需求，先做接口差异，完整实现后续。

R-VMM：按目标CPU分别核对VMX/SVM/EL2和VMM/设备模型，不以Intel上游例子保证AMD可用。

R-Hardware：实际只读枚举首台候选机/恢复介质，不刷BIOS、不覆盖系统盘；调查完成不算支持验收。

调查可先于M5，实际危险硬件写入是后续明确任务。所有实验保护现役服务与数据。

## 5. 判定与选择

ABI问题使用普通客户端缩小；兼容问题使用原ELF差分；Hepta装配问题在原Linux复现。AI策略未优于普通反馈时保留可靠对照，不能为了产品标签强制使用AI。发现核心上游冲突时提交具体复现与改动成本，才调整派生边界。

接续实现保留已存在的 Process/exec 镜像、原CPU/D owner及Hepta接缝，依据当前能力表选择尚未闭合的真实装配与执行。Linux host UI与原生guest可以并行；可运行宿主客户端不改变G1/G2定义。

## 6. 历史基线与当时缺口（2026-10-17）

本节完整保留 `146dedf…` 时点描述；下面“下一实际阻塞”“未合并分支”等不再代表当前候选。当前实现与下一验收以 [能力表](CURRENT_CAPABILITIES.md) 为准。

截至核对的主干 `146dedf75c5729ef1930c845eeb60e31e8111c60`，完整 Asterinas 派生源码、固定 QEMU 启动、A02 no_std ABI、A03 可替换锁后端、A05 只读 QueryAbi 及 Process / exec_epoch / nonce 身份隔离、A06 实际 cgroup CPU 配额均已合并。A03 的 host/Loom 结果仍不是内核 IRQ/SMP 证明；A06 的[已集成实测](../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json)包含 10 次一/双 vCPU 配额探针，不能继续将当前主干写为 `NOT_ENFORCED`，也不能外推逐窗口硬上限或完整 SMP 资格。

下一实际阻塞为 A05 在已实现的只读进程 / 镜像隔离上接可信能力授予、管理 / 观察权限和四项剩余设备操作、A06 exit/reap 最终 CPU 计费与资源域生命周期、A07 沿原 Hepta 持久 owner 的 K↔D/确认/退役/重启闭环。A04、A08、A10 的具体实现仍须按各自未合并分支验收；GPU/Android/自研内核 GUI 未获得实机资格。模块手册与源码入口见 [INDEX](INDEX.md)。官方 ISO 未完整下载不妨碍已有独立 initramfs QEMU boot，但不得据此声称裸机。
