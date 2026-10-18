# A01 → A00 / A05 / A06：当前完整 Rust 内核启动交接

本次执行源码为 `c22891b593f77c98ff4ea94d7aecb54f32222651`，分支 `agents/A01-asterinas-boot`。

源码构建、QEMU 启动与本次两个 crate 的回归均实际执行于上述源码 commit。后续用于归档收据的证据 commit 具有另一 SHA；不能将其表述为已经在该最终 HEAD 重新编译或重新测试。
Project tree：`af19f57a5e275fb8712363d90e72eca88477ec3e`；内核子树：`6c2904e53e79cedbbaf013a73a6173f4afa57010`。
独立复核结果见同目录 `independent-review.json`：已完成的源码、构建、产物、QEMU 与串口收据关联通过；本复核没有额外启动客体或测试矩阵。

## 本轮已经实际完成

完整 Asterinas 派生内核从源码执行 `make kernel`，随后 `make run_kernel` 成功。
原上游固定为 v0.19.0 / commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b` / tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`；commit → tree 已读取真实 Git 对象核对。
工具链为 `nightly-2026-07-21`：rustc `1.99.0-nightly (87e5904f5 2026-07-20)`，Cargo `1.99.0-nightly (3efb1f477 2026-07-17)`。

| 执行 / 输入 | 本轮结果 |
| --- | --- |
| 源码清单 | 3,010 个 tracked 内核、外部 ABI、构建输入；构建前、构建后、启动后字节与 mode 均对应同一 Git 对象，清单 SHA256 `36d3f324138eb079ceb994d0a190828b202bacd4c29e162ff14272313123a832` |
| 编译 | 2026-10-18 03:02:50–03:05:53 UTC；make / driver / 日志捕获 / manifest cleanup 均 exit 0；日志包含 OSTD、aster-core、asterinas 和完整 OSDK 内核 assembler 的真实编译 |
| 启动 | 2026-10-18 03:06:50–03:06:52 UTC；make / driver / cleanup 均 exit 0；QEMU raw exit 33，无超时 |
| 实际 profile | QEMU 8.2.2，x86_64、q35、TCG、CPU max、1 vCPU、512 MiB、SeaBIOS、串口、isa-debug-exit |
| boot ELF | 8,310,560 bytes；SHA256 `208caf5126c94f660292aacd36040ec62c9d317b116b9a861634f08cb02cd8f3` |
| 小 initramfs | 1,107,990 bytes；SHA256 `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`；25 个 newc 条目，含静态 x86_64 BusyBox、项目 init 和原上游 smoke |
| BIOS | 262,144 bytes；SHA256 `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| 完整串口 | 72,331 bytes；SHA256 `b661e07581dc7e7f9caa0ba104c6e5f3c3ef844dc24a28e278ee772896903b53`；五个必要启动标记各一次，无 fatal panic |
| 当前 OSTD 回归 | harness 报告 221 passed、0 failed、0 filtered；其中 3 项因能力不可用软跳过（2 × VMX unavailable，1 × VMX/EPT invalidation unavailable），实际执行通过下界为 218；原始 QEMU 退出码 33 |
| 当前 aster-core 回归 | 153 passed、0 failed、0 filtered、0 软跳过；原始 QEMU 退出码 33 |
| 回归总计 | 驱动退出码 0；374 项报告通过，扣除 3 项软跳过后实际执行通过下界为 371。仅选择上述两个 crate；未宣称完整上游设备/用户态矩阵或 VMX/SMP 已通过 |

本次回归原始收据：`support/build/out/2026-10-18-current-main/ktest/result.json`、各 crate 的 `guests/guest-001/{serial.log,qemu.json}`；独立审计重新核对了原始串口的测试数量与软跳过原因、产物/串口 SHA256、固定 QEMU 参数和实际退出码。

这是一次初始内核 target 不存在的源码构建，加一次使用该新构建缓存的启动。构建后冻结 ELF 与 QEMU 实际加载的私有 ELF 副本逐字节一致。依赖与工具链已事先准备，不将后续缓存启动表述为第二次冷构建。

## 构建和启动入口

唯一内核根目录为 `kernel/asterinas/`。在配置好本次记录的 native 工具环境后，从仓库根执行：

```bash
bash support/build/kernel.sh kernel
bash support/build/kernel.sh run_kernel
```

入口通过 `support/build/minimal.mk` 调用原上游 developer targets，保留完整内核、OSTD、OSDK 和上游许可。正常最小 profile 固定 1 vCPU / 512 MiB；无需 NixOS 安装 ISO、Docker/Nix daemon 或 KVM。
本轮 private-prefix 固件与 ROM 路径使用 `A01_QEMU_BIOS` 和 `A01_QEMU_DATA_DIR`；Cargo、Rustup、vDSO 和 PATH 的精确取值在每阶段 `environment.log`。

原执行根为 `/workspace/scratch/d7da9e7650f0/trillionnium-os-desktop/support/build/out/2026-10-18-current-main/`。
`kernel/command.sh` 与 `run_kernel/command.sh` 保存完整 make 命令；`run_kernel/qemu.json` 保存实际 QEMU argv、加载副本、源路径映射、hash、退出状态和串口摘要；`run_kernel/serial.log` 是完整原始串口。
QEMU 命令没有 ISO、数据盘或网络设备。客体 `/proc/version` 中的 Linux 5.13.0 来自固定上游 `kernel/core/src/net/uts_ns.rs` 为 glibc 定义的兼容 UTS 值；实际加载对象是上述源码构建出的 Asterinas ELF。宿主 Linux uname 只属于 `environment.log` 的环境记录。

## A05 可继续开发的具体接口

以下内核路径相对 `kernel/asterinas/`：

| 路径 / 符号 | 当前事实与下一接合 |
| --- | --- |
| `kernel/core/src/process/process/mod.rs` / `Process`、`hepta_capspace_session()`、`hepta_exec_epoch()`、`advance_hepta_exec_epoch()` | 已有真实 Process / exec epoch / boot 内受检 nonce 身份；继续扩展可信授予，沿用唯一进程对象 |
| `kernel/core/src/process/execve.rs` / `do_execve()` | 成功 exec 轮转 epoch、旧 control fd 失效；最终新映像能力激活尚需实现 |
| `kernel/core/src/process/process/init_proc.rs` / `spawn_init_process()`、`create_init_process()`、`create_init_task()` | 可信 init 的具体接合位置，当前最终调用 `process.run()` |
| `kernel/core/src/syscall/ioctl.rs` / `sys_ioctl()` | 已取得 owned file 引用并在分派前释放 file-table 借用 |
| `kernel/core/src/device/misc/hepta_control.rs` / `HeptaControlDevice::open()`、`HeptaControlFile::check_session()`、`ioctl()` | `/dev/hepta-control`，实验 ioctl `0xC0204802`，目前只支持 QueryAbi；拒绝跨 Process 及旧 exec 会话 |
| `kernel/core/src/lib.rs` / `hos2_os_abi` | 通过 path module 编译仓库的唯一 `libs/os-abi/src/lib.rs`；该外部文件已纳入本轮源码清单 |

只读 QueryAbi 与身份隔离代码已在本次完整 ELF 中编译，但本次小 initramfs boot 没有调用 A05 专门的 ioctl 探针。
可信能力激活、管理/观察能力、撤销、`ReadUsage`、`InstallBudget`、`QueryDelivery`、`RetireThrough` 仍需真实接合；当前设备对四项未实现操作返回 `EOPNOTSUPP`。

## A06 可继续开发的具体接口

| 路径 / 符号 | 当前事实与下一接合 |
| --- | --- |
| `kernel/core/src/sched/sched_class/mod.rs` / `ClassScheduler`、`PerCpuClassRqSet`、`LocalRunQueue` | 共同调度资格、计费、节流和 timer 路径；`try_pick_next()` / `update_current()` 先结算运行量 |
| `kernel/core/src/sched/sched_class/{stop,real_time,fair,idle,time}.rs` | 既有调度类与时间设施，不能另建平行调度器 |
| `kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs` / `CpuController`、`task_cpu_eligible()`、`charge_task_cpu()` | 唯一 cgroup CPU 配额事实；未来 HOS2 应接这里，沿用祖先记账 |
| `kernel/core/src/process/posix_thread/mod.rs` / `cpu_cgroup()`、`set_cpu_cgroup()`、`CpuCgroupLease` | 最新 main 已保留 Process 销毁后的末次计费资源身份 |
| `kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs` / `retain_cpu_charge_lease()`、`release_cpu_charge_lease()`；邻近 `inode.rs` | cgroup 最终计费租约及删除边界已实现源码 |

本轮继承并编译了 main `b7a8388` 的末次 CPU debit 修复，没有回退该补丁。真实短生命周期任务、exit/reap/rmdir、迁移及 SMP 锁序仍需要 A06 定向客体验证；小 initramfs boot 不授予上述场景通过结论。

## 所有权和剩余范围

A01 保留 `support/build/**` 与上游锁/构建责任。A05/A06 已接手的 process、device、cgroup、scheduler 核心文件，以及 OSTD，与实际 main `b7a8388` 保持字节一致；共享 OSTD 修改由 A00 协调。上游 2,938 个原文件、许可证、README 与署名继续保留；项目根 README 为 0 字节。

A00 可据本轮新收据确认完整派生 Rust 内核源码构建和固定 QEMU 最小启动。A05 的四项效果/历史操作，A06 的完整生命周期与 SMP 资格，A07 沿原唯一持久 owner 的 K↔D/确认/退役/恢复，仍各归相应 owner。
完整上游用户态/设备矩阵、G1/G2、裸机、跨宿主字节复现和完整不可变宿主依赖锁未由本次启动关闭。
