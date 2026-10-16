# 系统架构与上游接合

版本0.2。共享原则与真实进展见 [INDEX](INDEX.md) / [STATUS](STATUS.md)。

## 1. 默认路线已经收敛

选择完整 Asterinas v0.19.0 内核派生，而非只取 OSTD 后重建所有上层。源码 commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`，tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`，上游工具链 `nightly-2026-07-21`，首期 target `x86_64-unknown-none`。固定输入见 [upstream-lock.json](../support/upstream-lock.json)。这项选型不是已经导入或启动内核。

第一实现以最小可审阅差异扩展上游进程、文件对象与调度器；不新增平行 Task/VFS/权限数据库。只在具体接口冲突与最小复现证明全内核派生成本不合适时重新评估 OSTD-only，不并行维持两套产品。

## 2. 分层与“原生”定义

Hepta作为用户态原生系统服务，现有Codex主链调用窄的控制ABI。Linux ELF及其用户态环境依旧是初期可执行形态；独立原生程序ABI（装载、TLS、信号、运行时、工具链）是明确未实施的后续目标，不因控制ioctl存在就宣告完成。

从上至下为：Rust桌面/应用 -> Hepta或普通客户端 -> Linux兼容/原生控制入口 -> 同一个内核对象与权限/资源执行者 -> OSTD及驱动 -> 硬件。Android保留AOSP用户态并接到同一底层；VM只作独立标记补缺，不成为默认唯一应用运行方式。

在QEMU内运行的新内核并不依赖Linux syscall实现，但QEMU测试仍非裸机支持证据。最终至少一台固定实机独立启动；本轮不修改现役机器。

## 3. 实际上游路径与新增点

| 已核对上游路径 | 本项目预期改动 | 对应验证 |
| --- | --- | --- |
| `kernel/core/src/syscall/ioctl.rs` / `sys_ioctl` | 注册受限control file的处理；沿用真实调用Context与get_file流程 | fd别名、copyin/out、并发关闭 |
| `kernel/core/src/fs/file/file_table.rs` | 复用文件对象引用；CapSpace附着进程，fd不等于授权 | dup/fork/SCM_RIGHTS/exec |
| `kernel/core/src/process/process/mod.rs` | 绑定start identity、exec_epoch、资源域 | PID重用、启动前资源归属 |
| `kernel/core/src/sched/mod.rs` 与 `sched_class/fair.rs` | 增加有界资源域cap执行与记账 | 同值更新不充值、父域约束 |
| `kernel/core/src/fs/fs_impls/ext2/impl_for_vfs/inode.rs` | 固定S1持久化候选接口并验证flush/锁/目录语义 | SQLite/短写/崩溃回归 |
| `ostd/src/task/scheduler/mod.rs` | 仅在上层机制确实不足时改底层，不平行重写调度器 | 原有调度与IRQ回归 |

路径来自固定git tree；其中仅 sys_ioctl 调用流程本轮逐段核对，其他行是位置绑定，不宣称已完成逐函数代码审计或修改。sys_ioctl会在调用FileLike::ioctl前释放file-table借用，应延续此结构；其CLOEXEC注释包含竞态待办，故管理权限不能只依靠CLOEXEC位，必须有exec_epoch核验。[来源](SOURCES.md#asterinas)

## 4. 对象所有权

Task/Thread/AddressSpace/VFS沿用上游；ResourceDomain拥有本域/祖先预算与统计；进程元数据拥有CapSpace；文件对象只承载transport生命周期；每个设备/队列拥有generation、引用和静止状态。K及持久效果事实属于原Hepta owner；D及结果槽属于本boot内核。cap、namespace、Linux credentials、Android MAC都是同一对象检查的输入，不另存一份权限真相。

## 5. 同步与执行上下文

先复制用户缓冲和分配有界结果槽；取得CapSpace/文件对象强引用后释放查表锁；然后获取目标mutation锁。不得持有查表借用跨驱动回调。短mutation锁保护grant epoch、准入、revision和同对象结果；持锁不睡眠、不做文件I/O、不调用模型。

层级资源锁按root到leaf顺序；未来跨树迁移需最小共同祖先与稳定对象ID顺序，首期直接不支持迁移。runqueue和domain的具体同步接合在源码导入后按上游锁约束确定：不能发明一个抽象锁序就称已排除所有死锁。先单CPU验证，再扩多CPU；多CPU准入需要额度预留，不能多个CPU各自读取同一余额后同时花费。

IRQ仅登记有界完成/唤醒，复杂清理交给worker。unmap后需等相关CPU TLB shootdown及引用回收才可复用物理页。shared queue使用明确acquire/release与设备屏障；IOMMU访问隔离不替代DMA缓存同步。设备所有权详见HARDWARE_AND_DRIVERS。

## 6. 启动序列

bootloader交接与范围验证 -> 异常/页表/内存/时钟/IRQ -> 最小线程与文件/设备 -> entropy readiness、boot identity -> 独立init/恢复 -> 可信CapSpace/资源配置 -> 满足资格的存储/原Hepta owners -> 受限桥/真实Agentd profile -> 应用。

未有熵或可信存储时允许受限诊断，不伪造安全会话；不用模型才能启动系统。租约、休眠与更新遵循SECURITY_AND_RECOVERY。恢复服务与最低系统I/O有独立预算，不能被普通cap饿死。

## 7. AI控制闭环

快速路径固定执行机制；策略循环仅能调整envelope内的CPU cap，不变更页表、权限、热保护或内核代码。Hepta body/topology generation与OS budget revision不同，避免每个cap变化触发全局重启。通用任务依赖、取消传播、资源归属和可信结果比模型专用KV内核对象更重要。

先做普通客户端再接真实Hepta，以分离ABI、兼容层和宿主装配故障。固定策略、非AI反馈、Hepta三种控制器加Linux等价控制对照，所有推理/采样成本计入；接口演示不宣称收益。

## 8. 本轮源码边界

`libs/os-abi/` 为计划中的无依赖no_std编解码库，是否已实现仅见STATUS。文档检查和规格模型不冒充内核、驱动或独立native应用runtime。未来导入上游保留其实际目录，不为目录图搬动或复制源码。
