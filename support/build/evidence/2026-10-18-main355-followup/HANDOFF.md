# A01 → A00 / A05 / A06：main355 集成交接

## 当前可使用的源码和入口

分支 `agents/A01-asterinas-boot`，PR [#22 → main](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22)。实际构建/启动/ABI gate 的 producer 为 `40c901c6e189058bdd6f42bb43bf46b3bbcf8ffa`，已合并 main `3551e1e0e017e2973da7e2b8ab811ece25c258c0`。随后提交的证据不构成另一次执行。

唯一内核根目录 `kernel/asterinas/`；完整固定 Asterinas v0.19.0 / `c4b7ed575b7b32773475b194d2ad41fb6d03765b`；Rust `nightly-2026-07-21`。

```bash
support/build/kernel.sh kernel
support/build/kernel.sh run_kernel
```

以上从仓库根运行，在已配置 native 依赖的环境中经 `support/build/minimal.mk` 调用原上游 make targets。默认 x86_64、1 vCPU、512 MiB、q35/TCG、SeaBIOS、串口、小 initramfs。完整命令、环境和产物见 [REPORT.md](REPORT.md)。

本次两阶段均 exit 0、QEMU raw33；实际 ELF SHA256 `1eb66b33baef6b338c232598d25f743dc83526a2715811b430e5a7208e249ecd`。A02 owner gate 13/13、Rust78、20 个 compiled mutants 全部通过。首次 cold pipeline 及 OSTD/core 374 reported / 3 capability skips / 371 exercised lower bound 保持绑定旧 `c22891b`，见 [原始完整交接](../2026-10-18-current-main/HANDOFF.md)。

## A05：进程对象、可信 init、ioctl

下列路径相对 `kernel/asterinas/`，与 main355 相同：

| 接口 | 具体路径与当前事实 |
| --- | --- |
| 进程事实 | `kernel/core/src/process/process/mod.rs`：`Process`、`hepta_capspace_session()`、`hepta_exec_epoch()`、`advance_hepta_exec_epoch()` |
| 成功 exec | `kernel/core/src/process/execve.rs`：`do_execve()` 轮转 epoch，使旧 control fd 会话失效 |
| 可信 init 接合 | `kernel/core/src/process/process/init_proc.rs`：`spawn_init_process()`、`create_init_process()`、`create_init_task()`，最终 `process.run()` |
| ioctl 分派 | `kernel/core/src/syscall/ioctl.rs`：`sys_ioctl()`，持有 owned file 引用并先释放 file-table 借用 |
| 设备边界 | `kernel/core/src/device/misc/hepta_control.rs`：`HeptaControlDevice::open()`、`HeptaControlFile::check_session()`、`PerOpenFileOps::ioctl()` |
| 唯一 ABI 模块 | `kernel/core/src/lib.rs` 的 path module 引入仓库 `libs/os-abi/src/lib.rs`；当前实际 SHA256 `826e6533bd7ed2f6527db819e9f0400867ca1e607cd0581a03970444c3e4b60f` |

`/dev/hepta-control` 实验 ioctl `0xC0204802` 当前只支持 QueryAbi，具有实际 Process/exec 会话边界。A05 可从这些位置继续接合可信能力授予、管理/观察能力及撤销。`ReadUsage`、`InstallBudget`、`QueryDelivery`、`RetireThrough` 当前仍返回 `EOPNOTSUPP`；本次最小 init boot 没有运行 A05 定向 ioctl 探针。ABI host gate 通过不代表四项设备效果已实现。

## A06：调度与最终计费

| 接口 | 具体路径与当前事实 |
| --- | --- |
| 共同调度路径 | `kernel/core/src/sched/sched_class/mod.rs`：`ClassScheduler`、`PerCpuClassRqSet`、`LocalRunQueue::{try_pick_next,update_current,dequeue_current}`、`pick_next_entity()`、`replenish_throttled()` |
| 调度类与时间 | 同目录 `stop.rs`、`real_time.rs`、`fair.rs`、`idle.rs`、`time.rs` |
| 配额事实 | `kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs`：`CpuController`、`CpuMax`、`task_cpu_eligible()`、`charge_task_cpu()` |
| 任务资源身份 | `kernel/core/src/process/posix_thread/mod.rs`：`cpu_cgroup()`、`set_cpu_cgroup()`、`CpuCgroupLease` |
| 最终计费/删除 | `kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs`：`retain_cpu_charge_lease()`、`release_cpu_charge_lease()`；邻近 `inode.rs` 删除边界 |

main 已有 final-debit 源码，本轮保留并编译。A06 继续负责短生命周期任务的 exit/reap/rmdir、迁移、SMP 锁序和严格窗口验证。本次 boot 与旧通用 ktest 不替代这些 owner 场景，也不需要平行调度器或第二套 CPU 配额事实。

## 所有权和未闭合问题

A01 维护 `support/build/**`、`support/upstream-lock.json` 及来源/构建配置。A05/A06 已接手的内核核心不由 A01 自行修改；共享 OSTD 和固定上游升级须 A00 协调。根 README 仍为 0 字节，上游许可/文档保留。

最小源码构建和启动已通过。可信效果操作、A06 完整生命周期/SMP、A07 持久 owner/恢复、G1/G2、VMX/EPT、裸机、完整上游矩阵、跨宿主逐字节复现及不可变 host lock 仍未验收。

本工作区在启动后另出现了一个未跟踪的 `kernel/OSDK.toml`。A01 已记录与本次 cleanup 不同的 inode，取得构建锁后将它原 inode/原字节隔离保存，当前入口恢复；创建者尚未定位。该后续观察和原始非空 Git 状态见本报告的 `late-manifest/`，不能把所有时段的工作区误称为干净。
