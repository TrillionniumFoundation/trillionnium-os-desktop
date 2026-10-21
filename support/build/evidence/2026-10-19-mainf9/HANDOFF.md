# A01 → A00 / A05 / A06：main f9 Rust 内核基础交接

证据日期：2026-10-19 UTC。归档位置：`support/build/evidence/2026-10-19-mainf9/`。

本轮已完成固定完整 Asterinas 派生的空 target 源码构建、实际 QEMU 启动，以及 OSTD / aster-core 两组真实内核测试。**390 项报告通过，3 项能力跳过，实际执行通过下界为 387；0 失败、0 过滤。** 临时公共 manifest 再出现的写入者仍未识别，当前工作树不能称为完全干净。

完整构建、依赖与失败记录以 [REPORT.md](REPORT.md)、[report.json](report.json) 为准；本交接提供实际源码入口、所有权和验证范围。此文件由 A01 只读审计 Agent 根据已经核验的源码及主执行 Agent 提供的本轮真实结果编写；写作阶段没有重新运行构建或客体。

## 1. 唯一内核根与实际 producer

仓库内唯一内核根为 `kernel/asterinas/`，采用完整上游源码导入与小范围派生。实际执行工作树的内核根为：

```text
/workspace/scratch/d7da9e7650f0/a01-mainf9/kernel/asterinas
```

| 身份 | 固定值 |
| --- | --- |
| 实际源码 producer | `7758ffe294bb0e1eab46e20cba60e8af9d8bcd61` |
| 实际项目 Git tree | `98c7b099ff280f0804041dca13d691d431a8caf6` |
| 实际内核 Git subtree | `9b400ccf16c275935736e6e2b0b08aecbe20c40e` |
| 第一父提交：本轮采用的 main | `f9e306f76154590e096a42f70ce9de0a7c859e60` |
| 第二父提交：此前已发布 A01 | `71524be19383e2ff98f6abc90668c48988e7c8e2` |
| Asterinas 固定版本 | `v0.19.0` |
| Asterinas 固定 commit | `c4b7ed575b7b32773475b194d2ad41fb6d03765b` |
| Asterinas 固定 tree | `96605cf64aeae2d34f29b97e85eff9315fe10a8e` |
| 固定 Rust | `nightly-2026-07-21` |
| 裸目标 | `x86_64-unknown-none` |

producer 的整个 `kernel/asterinas/kernel`、OSTD、上游 `test`、ABI/control 与本轮 main 对应子树完全相同。A01 的 `support/build`、`upstream-lock.json` 和 OSDK 与此前 A01 提交对应子树完全相同。本轮 A01 没有修改 A05/A06 核心或 OSTD 源码。

内核共有 2,945 个 tracked 路径。2,938 个原始上游路径全部保留，其中 2,906 个未改、32 个存在派生修改，另有 7 个新增派生文件。受核验的 84 项上游许可证、README、AGENTS 及许可证检查配置保留原 blob/mode；项目根 `README.md` 仍为 0 字节。最终证据提交不替代上述实际构建 producer 身份。

## 2. 本轮实际构建、启动与回归

| 实际阶段 | 本轮结果 |
| --- | --- |
| `make kernel` | 从空 target 构建完成，退出 0；189.63256 秒，284 条 `Compiling` 记录 |
| 首次 `run_kernel` 尝试 | 启动前保护检查拒绝已有公共 manifest；该尝试没有启动 QEMU 客体 |
| 保全并移存 foreign manifest 后的启动重试 | driver 退出 0，QEMU 原始退出 33；实际进入新构建的完整 Asterinas 内核 |
| OSTD 实际内核测试 | 221 项报告通过，3 项 VMX/EPT 能力 soft skip，至少 218 项实际执行通过；0 失败、0 过滤，QEMU 原始退出 33 |
| aster-core 实际内核测试 | 169 项通过，0 soft skip、0 失败、0 过滤，QEMU 原始退出 33 |
| 两组内核测试合计 | 390 项报告通过，3 项 soft skip，实际执行通过下界 387 |
| 源码绑定 | 全部 3,014 个选定 tracked 输入在执行前后与 producer 匹配 |
| 独立证据复核 | 53/53 项证据检查成立；本轮新增 9 项 CPU 配置测试均在实际串口中恰好出现一次并报告 `ok` |

实际完整内核 ELF 为 **8,382,376 字节**，SHA256：

```text
4625a5ddf9e82aee2ce01bdfb23127f88a5200565ce2a0645a09e181073ab6d4
```

首个空 target 构建产物与启动时真正加载的私有副本一致。成功的启动重试使用这次源码构建的产物；它不是另一次空 target 构建。

实际启动 profile 为 **x86_64、q35、TCG、1 vCPU、512 MiB**。使用小型 initramfs，完整 NixOS 安装 ISO 不是该开发路线的前提。完整 QEMU argv、输入文件绑定和退出结果见 [boot/qemu.json](boot/qemu.json)；完整原始串口见 [boot/serial.log](boot/serial.log)。两组测试的机器结果见 [ktest/result.json](ktest/result.json)，完整客体串口分别见：

- [OSTD guest serial](ktest/ostd/guests/guest-001/serial.log)
- [aster-core guest serial](ktest/aster-core/guests/guest-001/serial.log)

完整 boot 串口 SHA256 为 `b585103e6b898bbd1c804b554cb66876ab7d2463872247f98d0def6bd3cc057f`。53 项证据检查数与 390 项内核测试报告数分别统计。

上面只列本轮实际执行。此前 OSDK 全矩阵、宿主 ABI gate、native HOS2 探针和其他历史结果保留其原有源码身份，本轮没有重跑它们。

## 3. 实际构建与启动入口

从已按本轮报告准备好的固定隔离 native 环境执行：

```bash
cd /workspace/scratch/d7da9e7650f0/a01-mainf9

export RUSTUP_TOOLCHAIN=nightly-2026-07-21
export CARGO_BUILD_JOBS=2
export A01_SMP=1

support/build/kernel.sh kernel
support/build/kernel.sh run_kernel

# 不指定 --crate 或 --test-name：执行 OSTD 与 aster-core 完整测试集
python3 -B -I support/build/ktest/run.py
```

`support/build/kernel.sh` 是维护入口：它经 `support/build/minimal.mk` 和既有生成锁，调用上游 `make kernel` / `make run_kernel`。固定上游 Makefile 的对应 recipe 进入 `kernel` 子目录，执行 `cargo osdk build` / `cargo osdk run`。OSDK、kernel Cargo.lock、工具链和 initramfs 输入应继续采用同一套 A01 配置。

上述命令是入口说明；准确的本次执行参数、输出目录和环境收据以 [REPORT.md](REPORT.md) / [report.json](report.json) 为准。尤其在当前公共 manifest 尚保全的情况下，已有保护检查可能再次拒绝启动；不能将该路径的当前状态假定为可直接重试。

当前 host OSDK 派生 manifest / lock 与已有批准输入匹配。历史 `kernel.osdk_cargo_lock_sha256` 记录上游锁值；实际派生锁的身份由 `kernel.approved_host_osdk_inputs` 描述，不能混用。内核本体与 Rust pin 没有升级。

## 4. A05：Process、ioctl 与启动接合

下表路径相对 `kernel/asterinas/`。它们均绑定上述 producer，且与本轮 main 对应源码相同。

| 路径 | 具体入口与用途 |
| --- | --- |
| `kernel/core/src/process/process/mod.rs` | `Process`；`hepta_capspace_session()`；`hepta_exec_epoch()`；`advance_hepta_exec_epoch()`；进程镜像身份与会话 fence |
| `kernel/core/src/process/execve.rs` | `do_execve()` / `do_execve_no_return()`；成功替换镜像后推进 exec epoch，耗尽时终止进程 |
| `kernel/core/src/process/process/init_proc.rs` | `spawn_init_process()`、`create_init_process()`、`create_init_task()`，以及最终 `process.run()`；后续可信启动接合应复用这些真实对象 |
| `kernel/core/src/syscall/ioctl.rs` | `sys_ioctl()`；先保留 owned file 引用，再释放 file-table borrow，随后调用真实 `FileLike::ioctl` |
| `kernel/core/src/device/misc/hepta_control.rs` | `HeptaControlDevice::open()`；`HeptaControlFile::check_session()`；`PerOpenFileOps::ioctl()`；真实 Process 与镜像会话检查 |
| `kernel/core/src/lib.rs` | path 引入仓库唯一的 `libs/os-abi/src/lib.rs`；继续共用 A02 wire 实现 |
| `kernel/core/src/process/posix_thread/mod.rs` | `cpu_cgroup()`、`set_cpu_cgroup()` 和 `CpuCgroupLease`；与 A06 的尾段计费接口共同维护 |

`hepta_capspace_session()` 在进程身份锁内返回一致的 epoch/nonce；控制文件保留打开时 Process 弱引用及 epoch，调用时核对真实 Process 身份与当前镜像。继承 fd 并不等于继承调用权限。

实际设备为 `/dev/hepta-control`，实验 ioctl 为 `0xC0204802`。现有实现仅开放 **QueryAbi**；`ReadUsage`、`InstallBudget`、`QueryDelivery`、`RetireThrough` 仍返回 `EOPNOTSUPP`。open、dup 和 QueryAbi 不授予管理能力。当前 main 已有只读进程/exec 会话基础，可信 grant、效果操作、撤销与历史生命周期仍需要 A05 接合和专门客体验证。

本轮没有运行 dedicated native HOS2 guest probe。通用启动成功、core 测试通过不能作为新增 HOS2 效果权限或 G1/G2 通过的证据。

**可修改范围：**A05 继续负责 `kernel/core/src/process/**`、`syscall/ioctl.rs`、已归属 A05 的控制设备邻近模块，以及仓库 `tests/kernel/control/**`。涉及 A06 CPU cgroup 事实的变更应沿既有共享接口协调；wire 变化由 A02/A00 统一。A01 不接管这些核心文件。

## 5. A06：调度器、CpuMax 与资源配置入口

下表路径相对 `kernel/asterinas/`。

| 路径 | 具体入口与用途 |
| --- | --- |
| `kernel/core/src/sched/sched_class/mod.rs` | `ClassScheduler`、`PerCpuClassRqSet`；`LocalRunQueue::{try_pick_next, update_current, dequeue_current}`；共同资格、计费与调度路径 |
| `kernel/core/src/sched/sched_class/mod.rs` | `pick_next_entity()`、`replenish_throttled()`；选择任务与重新检查节流任务 |
| `kernel/core/src/sched/sched_class/{stop,real_time,fair,idle,time}.rs` | 既有调度类与 runtime 时间设施 |
| `kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs` | `CpuController`、`CpuMax`、`task_cpu_eligible()`、`charge_task_cpu()`、层级 bandwidth 资格与计费 |
| `kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs` | `CpuController::write_attr()`；Linux `cpu.max` 文本写入与现有预算锁接合 |
| `kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/max_config.rs` | 新 `CpuMaxConfig::parse()`；在 owner mutation lock 前解析 cgroup 配置，类型和方法均为内部 `pub(super)` 接口 |
| `kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/config_regressions.rs` | 两个真实 `CpuController::write_attr` / `VmReader` 回归 |
| `kernel/core/src/process/process/mod.rs` | `cgroup()`、`set_cgroup()`、`set_cpu_cgroup_for_tasks()`；只能在现有 cgroup/membership 约束内接合，文件归 A05 |
| `kernel/core/src/process/posix_thread/mod.rs` | 线程最终计费快照及 `CpuCgroupLease`；文件归 A05，共享修改需协调 |
| `kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs` | `retain_cpu_charge_lease()`、`release_cpu_charge_lease()`；与 `inode.rs` 中删除/membership 边界配合 |

`charge_task_cpu()` 优先使用仍存在的 process cgroup 绑定；仅对已经 detach 的 zombie 或不能升级的 Process 弱引用，使用线程保留的 lease 完成尾段计费。quota bandwidth/debt 与 `cpu.stat` 的 tick usage 是既有不同字段，不能用其中一个冒充另一个。此次 main parser 修复没有改变 CpuMax 计费实现、层级资格/计费、最终计费或 scheduler 的实际字节。

新 parser 拒绝显式非数字/溢出 period 和多余字段，成功后才取得原 `SpinLock<CpuMax, LocalIrqDisabled>`。合法单 quota 在锁内继承当前 owner period；合法 quota+period 继续使用已有 `CpuMax::reconfigure()`。畸形输入的严格拒绝是项目明确选择，没有承诺与 Linux parser 的所有畸形输入处理逐字节等同。

`CpuMaxConfig` 是 cgroup 微秒文本入口，支持现有 quota/period 范围；它不是新的 HOS2 public API。未来 typed HOS2 预算仍需接到唯一实际资源 owner，并遵守 HOS2 自身的单位和 cap/period 规则，不能直接把 cgroup 文本解析器的范围当作 HOS2 wire 契约。已有 `cpu.weight` 接受但未执行的 warning 也仍存在，本轮 bandwidth 验证不授予 weight 调度资格。

**可修改范围：**A06 继续负责 `kernel/core/src/sched/**`、已经归属 A06 的 cgroup CPU 控制器与相关回归，以及仓库 `tests/kernel/scheduler/**` 和已有 A06 CPU 探针路径。不要扩大为自行接管整个 VFS/process 源码。共享 OSTD、跨 A05 进程生命周期或 wire 变更由对应 owner 与 A00 协调。

## 6. 本轮 main 新增的 CPU 配置回归入口

本次 main 相对上一轮增加 7 个 parser ktest 和 2 个 controller ktest；本轮完整 core 报告由 160 增至 169。独立 native review 已逐项核对下面 9 个测试名在实际 guest 串口中恰好出现一次且均报告 `ok`。它们已包含在本轮 169 项 core 结果中，不重复加入总计。

`kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/max_config.rs`：

```text
single_quota_preserves_the_current_period
accepts_valid_quota_period_and_range_boundaries
rejects_invalid_or_overflowing_quota
rejects_numeric_period_outside_the_supported_range
rejects_explicit_invalid_period_instead_of_preserving_the_old_period
rejects_overflowing_period_instead_of_preserving_the_old_period
rejects_extra_fields_instead_of_applying_a_valid_prefix
```

`kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/config_regressions.rs`：

```text
invalid_cpu_max_write_does_not_change_budget_or_accounting
single_quota_write_keeps_the_current_owner_period
```

controller 回归通过实际 `VmReader` 调用原 `write_attr()`。畸形输入检查覆盖原 CpuMax 的 quota、period、window start、used clocks、carry debt、period/throttle 计数、throttled-since 与 throttled clocks 全部不变；合法单 quota 检查原 owner period 被保留。

仓库 `tests/organ_backend/cpu_max_config_host.rs` 可直接引用同一 production parser 运行宿主用例，但本轮不宣称新执行了该独立 host 入口。上游 `test/initramfs/src/regression/process/cgroup.sh` 已同步畸形输入拒绝及预算保留的期待；最小 boot initramfs 不自动代表整套用户态 cgroup 回归已执行。

## 7. 当前真实 blocker 与 A00 后续整合

**公共 manifest 的再出现仍是未解决的构建环境问题。** 首次启动在保护检查处失败，保留 foreign manifest 并移存后启动成功。成功 boot 后公共路径再次出现 manifest；第二次锁内 rename 处理的即时观察为 absent，随后又观察到第三个 inode `26590`，其 mtime 为旧值。该当前条目保留在原路径用于取证，写入者和根因仍未知。

因此本轮只能陈述“3,014 个选定 tracked 输入前后与 producer 匹配”，不能陈述“当前整个工作树干净”。未跟踪 manifest 的存在不改变这些已核验的 tracked 源码字节，但可能继续阻断正常构建入口。下一次执行应沿报告中的实际失败收据处理其保全与隔离，保持现有身份、锁和启动前保护；不得把它当作已自动清理或已根治。

已完成的 1 vCPU / TCG boot 与内核测试也没有覆盖以下独立资格：

- dedicated native HOS2/ioctl 效果、可信 grant/revoke、原生 G1/G2；
- 完整 exit/reap/rmdir/迁移/scheduler 交错与一般 SMP 资格；
- VMX/EPT、裸机、KVM、物理设备或整机显示/输入；
- 新一轮 OSDK 全矩阵、host ABI gate、完整上游用户态/设备矩阵；
- 跨宿主逐字节复现和完整不可变宿主配置；
- 原 owner durable K↔D、确认/退役与故障接替闭环。

STATUS 顶部 R8 已记录 Linux host 上的可信 ObjectiveStart 准入与原版 run 到 Rust Shell 的可见投影，不应再引用历史段落声称该整条 host 功能尚未实现。该 host 进展不扩大本轮 Asterinas 原生效果资格。

A00 可按 producer 的真实构建和测试证据协调集成；固定版本、共享 OSTD 和跨 owner 改动继续由 A00 统一。A01 继续维护 `support/build/**`、`support/upstream-lock.json` 及构建配置，保留完整上游与许可证，避免复制第二套内核或授权/资源事实。所有后续 CI 与执行结果都应绑定其真实源码提交，不能继承别的 HEAD 的测试状态。
