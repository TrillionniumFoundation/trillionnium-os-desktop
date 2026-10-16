# Linux 应用兼容设计

版本：0.1。状态：计划，未执行任何本项目 Linux 兼容测试。

## 1. 兼容对象

目标是尽量运行未经修改和重新编译的 Linux ELF，提供其所需用户态依赖与行为环境。按 ISA、ELF ABI、动态加载器、libc、内核接口集合和应用版本建立 profile。源码能编译和原 ELF 能运行必须分别记账。

Linux 的稳定用户态接口与内核内部驱动接口不是同一承诺；`.ko`、特定 eBPF/kprobe 行为和专用驱动依赖单独列入矩阵，不能从 ELF 兼容推导其可用。[来源](SOURCES.md#linux-abi)

Starnix 提供非 Linux 内核承载 Linux ABI 的参考，但本项目不宣称能原样移植或继承其全部兼容结果。[来源](SOURCES.md#starnix)

## 2. 行为优先于 syscall 数量

相同调用名的返回值、errno、阻塞点、信号中断、并发顺序、资源释放和失败后的状态都属于契约。单纯统计“实现了多少 syscall”不能代表覆盖率。对正常和异常路径都与固定 Linux 基线做差分。

应用 profile 至少固定：加载器路径、依赖 rootfs 哈希、共享库版本、locale、时区、证书、DNS 配置、用户身份、挂载与设备暴露。兼容层只应对实际支持的功能做能力宣告。

## 3. 实现顺序

| 批次 | 接口范围 | 代表场景与负面用例 |
| --- | --- | --- |
| L0 | ELF、映射、栈、auxv、TLS、退出 | 静态程序、动态 hello；坏 ELF、非法段重叠 |
| L1 | fd、文件、目录、管道、TTY、时间 | shell/coreutils；短读写、fd 耗尽、管道关闭 |
| L2 | 线程、clone、futex、信号、等待 | Rust/Tokio；线程取消、退出竞态、信号中断 |
| L3 | socket、epoll、Unix socket、传 fd | Hepta IPC、HTTP；半关闭、超时、backpressure |
| L4 | mmap/COW、共享页、文件锁、持久化 | SQLite、Python；并发 mmap、锁、fsync 与断电 |
| L5 | procfs/sysfs、权限、namespace、cgroup | 真实运行时和容器；隔离泄漏与权限变化 |
| L6 | io_uring、ptrace、seccomp、驱动 ioctl 等 | 由实际应用需求排序，复杂设施逐项验证 |

这些是依赖顺序而非绝对阶段隔离。Hepta 真实依赖可能要求提前实现某项；使用观测来排序，不为符合表格延迟真实 blocker。

## 4. 重点语义

### 进程与内存

维护 task/thread/process group/session 的不同身份，正确处理 exec 线程组行为、僵尸进程和 wait。futex 必须验证共享地址、超时、唤醒竞争与退出清理；先声明不支持的扩展，不能假装 robust/PI 语义已经完成。

mmap、mprotect、munmap、fork/COW、文件映射写回及共享内存需联合测试。访问坏地址必须按 ABI 产生预期错误或信号，不让用户地址成为内核崩溃入口。

### 文件系统与持久化

先实现足以支撑真实用户态的单一路径，避免同时开发多个不可靠文件系统。目录 rename、硬链接/软链接、锁、fd 生命周期、fsync/fdatasync 与块设备 flush 必须有明确持久化模型。

SQLite 打开数据库不代表耐久性通过；在 WAL、事务提交、目录操作和设备 flush 前后注入重启，核对原事务和文件一致性。

### I/O 与网络

同时覆盖阻塞和非阻塞、边沿/水平触发、关闭后事件、fd 重用、SCM_RIGHTS、背压与资源耗尽。不会实现的 ioctl 返回适合该接口的错误，不能用成功空响应欺骗应用。

## 5. 初始应用矩阵

| 对象 | 目标模式 | 首批验收 | 当前状态 |
| --- | --- | --- | --- |
| 固定静态/动态 ELF、BusyBox | linux_abi | 装载、进程、文件与管道 | not_tested |
| Rust 多线程/Tokio 测试程序 | linux_abi | 线程、futex、epoll、信号 | not_tested |
| SQLite + 文件锁测试 | linux_abi | 事务、并发、重启恢复 | not_tested |
| hepta-agentd 及依赖闭包 | linux_abi | 真实启动、IPC、明确功能路径 | not_tested |
| Codex + Hepta 目标到工具主链 | linux_abi + native control | 一次真实原生资源操作 | not_tested |
| Python / 编译工具链 | linux_abi | 包加载、子进程、磁盘与网络 | not_tested |
| 图形应用 / 浏览器 | linux_abi + graphics | 输入、窗口、渲染、音视频 | not_tested |
| 依赖特定内核模块的软件 | vm 或单独实现 | 模块与硬件路径独立验证 | unsupported |

应用版本与哈希在 M0 获取真实样本后填写，不使用臆造版本。

## 6. 差分与回归

固定 Linux 内核、rootfs 和 CPU 模型作为参照。同一测试输入分别运行于 Linux 与新内核，比较规范化结果、退出码、文件状态、事件顺序和必要的时间边界。不能只比较 stdout。

使用适用的 LTP、libc/应用自测和文件系统测试；记录执行、通过、失败、跳过、超时各自数量与分母。跳过项必须解释，不从总数里悄悄移除。Asterinas 上游已有测试资产可参考，但结果不能自动算到本项目。[来源](SOURCES.md#asterinas)

新增兼容修复必须包含最小复现；不通过伪造硬件能力、忽略失败或放宽原测试来提升通过率。kernel panic、数据损坏和跨域访问属于阻断问题，其他缺失接口按真实应用优先级推进。
