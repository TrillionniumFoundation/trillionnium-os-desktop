# A06 G1-a：实际 CPU owner 的带宽 revision 与实例寿命

2026-10-19 接续：本文保留 G1-a 原切片的源码与运行边界。后续原账本的 BOOTTIME 纳秒端点、累计使用量和内部一致快照见 [G1-b 技术手册](ASTERINAS_CPU_USAGE_G1B.md) 及其配套开发手册；旧计数与原始 TSC 描述不代表当前新切片的资格。

本切片以 desktop `aab50f347deb53fc79ac13ea3b84f846fefc70a7` 为产品基线，落实
[G1 owner 工单](agents/R9_G1_OWNER_SEAM.md)中的第一阶段。代码和客体 ktest 已加入；
新增测试源码及 Cargo metadata 检查不代表客体执行通过，实际资格必须绑定后续同一候选的
提交、ELF、配置、QEMU serial 和计数收据。既有 quota/退出尾账证据继续保存在
[A06 N0 手册](ASTERINAS_CPU_BANDWIDTH_N0.md)，不得继承为本切片结果。

**本切片只为原 `cpu.max` 带宽 owner 接入一次性 metadata 绑定、共享 revision 和不可逆关闭。**
[HOS2 设备](../kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs)仍只支持 QueryAbi；
生产 bootstrap 不调用绑定入口，尚未安装 trusted-init、CapSpace grant、delivery namespace
或另外四个操作。绑定所得 `NativeTarget` 保留实际 owner Arc，不授予调用者执行权限。

## 1. 源码与依赖

| 文件 | 职责 |
| --- | --- |
| [cpu.rs](../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs) | 保留唯一 `CpuMax`、原 TSC 预算/债务和调度计费算法；`CpuControl.max` 改为保护完整 owner 状态 |
| [cpu/native.rs](../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs) | 一次绑定、普通带宽配置与原 `NativeResourceState` 的接合、不可逆 detached |
| [controller/mod.rs](../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/mod.rs) | 在原 subtree-control 替换路径中先关闭旧实例，再发布新 RCU Arc |
| [systree_node.rs](../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs)、[inode.rs](../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/inode.rs) | 删除要求 membership writer；原进程、charge lease、children 检查通过后才关闭管理 |
| [resource_state.rs](../libs/os-control/src/resource_state.rs) | 复用 A03 原 metadata/CAS/fence 状态机；只增加 `cfg(ktest)` 的极值构造入口 |
| [cpu/native/tests.rs](../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native/tests.rs) | 直接操作真实 cgroup、controller Arc、RCU 替换、删除和 Process/Task 计费 lease 的回归测试 |

`aster-core` 通过工作区依赖消费本地 `libs/os-control`，关闭默认 `std` feature，仅选择
`portable-spin` 以满足当前 A03 crate 的无 std 编译选择。这里使用的是无锁的
`NativeResourceState` 和实际 owner 的 `NativeTarget`；真实预算锁仍为 OSTD
`SpinLock<_, LocalIrqDisabled>`。没有实例化 portable-spin 的 namespace 或把它当作
kernel lock backend。`spin 0.9.9` 已在原始锁中，未新增外部版本或来源。

## 2. 同一预算与 revision

`CpuBandwidthState` 在原 `CpuControl.max` 锁内保存原 `CpuMax`、
`Option<NativeResourceState>` 和只允许 `false → true` 的 `is_detached`。
它没有第二套 CPU 累计、窗口、quota 或债务。普通 Linux 配置在尚未绑定时延续原行为；
绑定以当时实际预算作为 revision 1 的基线，不追认绑定前存在外部 CAS 历史。

绑定后，解析成功的每次 `cpu.max` 写入在同锁内调用原 `apply_owner_configuration`：
先设置 indeterminate fence，再由闭包调用原 `CpuMax::reconfigure`；闭包正常返回后才
提交新 revision 并清除 fence。异常保留旧 revision 和 indeterminate。同值写入也推进 revision，但不清零
已经消费的运行量或债务；原算法按实际经过的窗口结算仍然成立。无效文本、用户读取错误、
revision 耗尽和关闭状态均在预算修改前返回。所有用户读取、解析及格式化输出仍在预算锁外。

这里的 revision **只覆盖 `cpu.max` 带宽配置**。原 G1-a 基线中 `cpu.weight` 的 warning/AtomicU32
路径只存值，没有强制执行。当前[明确不支持的写合同](agents/CPU_WEIGHT_UNSUPPORTED.md)已删除该影子值：
合法写返回 `EOPNOTSUPP`，读保持 `100`；尚未实现 group-weight 调度。以后权重若影响这个受控资源，
必须一并设计授权和共享 revision，不能沿用当前范围宣称已经覆盖。

## 3. 内部输入、返回与关闭

私有 `Controller::bind_native_cpu_once_for_owner` 接收当前 controller 的实际
`Arc<SubController<CpuController>>`、可信资源登记应提供的两个非零身份，以及
`&mut CgroupMembership`。本轮只有客体 ktest 调用；没有从 ioctl 或普通用户输入取这些 ID。
它持有 membership writer 核对当前 Arc，再在原预算锁中安装一次 metadata。
返回的 `NativeTarget` 保留同一 Arc 和身份，不建立独立预算 owner。

| 输入/状态 | 结果 | 预算、身份与 revision |
| --- | --- | --- |
| 当前活动、未绑定且未关闭的 owner，两个非零 ID | 绑定成功，返回 `NativeTarget` | 预算保持；建立 revision 1 |
| 当前 owner 已绑定 | `AlreadyExists` | 不重绑、不更换身份 |
| ID 无效 | `InvalidOperation` | 无状态变化 |
| 指定 Arc 已被替换，或当前 Arc 已 detached | `IsDead` | 不重新打开旧实例 |
| 当前 controller 未启用 CPU 控制 | `AttributeError` | `control == None` 不能绑定；以后启用创建新 Arc |
| 普通带宽配置 revision 已到 `u64::MAX` | `Overflow` | 不回绕、不修改预算 |
| 尚未 detached 的 owner，其原 metadata 处于 indeterminate | `ResourceUnavailable` | 不清除模糊结果、不继续配置 |
| cpu.max 文本/范围无效 | `InvalidOperation` | 不消耗 revision，不改变预算 |

上述错误属于内部 `aster_systree` API；不是新 HOS2 wire 错误。已有用户内存读取错误
继续沿原路径传播。普通 Linux 写入不产生 delivery ID，也不能被表述成 HOS2 成功结果。

替换先准备并分配新 controller，再在旧预算锁下置 detached；若旧 owner 已绑定则调用
原 `invalidate()`。随后才发布新 RCU Arc。新实例默认无 metadata，不能自动继承旧身份、
revision 或权限。没有绑定 metadata 的旧 Arc 同样永久 detached，覆盖 `native == None`
时晚到绑定的漏洞。旧 metadata 如果已经 indeterminate，关闭后仍保留该 fence。
已 detached 后普通 `cpu.max` 优先返回 `IsDead`；原 metadata 自身的 `apply` 仍返回
`Indeterminate`，没有把模糊结果转换成已知失败。

删除在原“空进程、无 CPU charge lease、空 children”检查全部通过后，并在
`inner = None` 之前关闭当前 CPU owner。持有尾账 lease 时仍返回 EBUSY，不能提前关闭或
取消 lease。调度计费仍可通过保留的原引用记入已经发生的 CPU 时间；管理关闭不清空
计费对象。现有 thread lease 固定的是 cgroup node，本切片没有重设计 subtree 替换与
正在运行任务之间的代际归账协议。

## 4. 锁顺序与中断边界

| 路径 | 顺序 |
| --- | --- |
| 绑定/替换 | membership writer → 当前 Arc 核对/准备 → 原 CPU bandwidth IRQ-disabled 锁；解锁后 RCU publish |
| 删除 | membership writer → node inner/children 原检查 → 原 CPU bandwidth IRQ-disabled 锁 → 标记 node dead |
| 普通 cpu.max | 用户读取和解析 → 原 CPU bandwidth IRQ-disabled 锁 → 原 metadata 与预算变更 |
| 调度计费 | 原 runqueue IRQ-disabled 锁 → cgroup RCU 读取 → 每个祖先独立的 bandwidth 锁 |

预算锁内没有用户拷贝、堆分配、sleeping mutex、namespace 回调或重新取得 membership。
新 controller 的 Arc 在不可逆关闭前分配。`NativeTarget` 的 Arc clone 也在预算锁外完成。
本切片没有证明未来 delivery gate、runqueue 和权限撤销之间的完整锁序，未开启对应执行路径。

## 5. 构建和客体验证

按 [A01 构建手册](../support/build/README.md)准备固定 `nightly-2026-07-21`、源内 OSDK、
vDSO 和 QEMU，然后从项目根执行：

```sh
python3 -I support/build/verify-source.py
python3 -I support/build/ktest/prepare-locks.py --crate aster-core
python3 -I support/build/ktest/run.py --crate aster-core --skip-osdk-install --output /absolute/fresh/g1a-ktest
```

`--skip-osdk-install` 只适用于已经按同一源路径构建的 patched OSDK；否则删去该选项。
完整 suite 不传测试过滤器。固定 native 入口实际使用 q35/TCG/CPU max、单 vCPU、512 MiB
和 SeaBIOS，构建和原始串口判据见 [ktest 手册](../support/build/ktest/README.md)。

原 Asterinas `Cargo.lock` 的 **Git 种子** SHA256 保持
`6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316`。
它取自固定 tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e` 的 blob
`77d8f4be4cdc7365cd73a2e9f7638d46f3608b40`，不取自工作文件。工作根锁从该种子
逐字导出，仅增加 `aster-core → os-control` 和依赖既有 `spin` 的本地包记录，
由 234 变为 235 包；其 SHA256 为
`af94d71680ecf3b9631e21c958263d5e41229033214f88dcff858bb14765a666`。
源码门禁只允许这两处锁插入和两个 manifest 增量，其余字节/模式/pin 仍核对原 tree；
`--pristine` 继续只接受原上游文件。没有把构建中观测到的变化直接改设为新种子。

测试派生锁先以经过逐包核对的 committed lock 执行 `cargo fetch --locked`，随后从原 Git 种子
离线重新 normalize 并再执行 `metadata --offline --locked`。新增本地项只有 OSDK test-base
和 `os-control`；所有外部 name/version/source/checksum 均来自原锁。归档的
[派生报告](../support/build/ktest/locks/aster-core.json)同时记录本地路径和实际 feature 集合。
run-base 的 [minimal 锁](../support/build/minimal/Cargo.lock)也只增加该本地包与依赖关系；
实际产品构建仍由原 OSDK 生成 workspace 并强制 `--locked`。

首次候选 `be6d8408878dc25fce3188e1fc759aa227bf8678` 的真实完整 aster-core 构建在
`Arc::ptr_eq` 参数缺少对 `ArcRef` 的显式借用处失败，QEMU 未启动，没有客体通过计数。
同轮还发现工作根锁被隐式写入。隔离复现确认来源是 `parse_metadata!` 调用的
`component_generate()` / `get_component_toml_path()` 共用的完整 metadata；
`#[init_component]` 本身不调用 metadata。原 OSDK 的 `metadata --no-deps` 查询没有改锁。
修订保留完整组件图并加 `--locked`，使用由原种子明确导出的工作锁；两次成功复现的完整
metadata 输出相同（226 个已解析包，不等于工作锁的 235 包）。以后编译必须保持这些
工作/生成锁字节不变。此修订及 metadata 复现不能代替修订后客体测试结果。

### 新增的十个真实 owner ktest

| 回归 | 直接断言 |
| --- | --- |
| 一次绑定 | 保留当前真实预算；无效 ID 拒绝，重复绑定不改身份/revision |
| 普通同值配置 | 真实 cgroup cpu.max 写入推进到 revision 2，保留 usage/debt；旧 revision 失败且无回调 |
| 无效配置 | 七种文本/范围错误均不消费已绑定 revision |
| 替换已绑定 Arc | 原 subtree-control RCU 替换使旧 Arc 永久关闭；新 Arc 不继承 metadata，原统计保留 |
| 替换未绑定 Arc | 旧 Arc 的 `native == None` 不允许晚到绑定或配置 |
| 删除未绑定 Arc | 被保留 node 中仍指向同一 Arc 时也由 detached 拒绝晚到绑定 |
| 删除已绑定 Arc | 身份、revision、原预算保留，后续管理失败 |
| revision 极值 | 真实配置完成 `MAX-1 → MAX`；以后所有写入均失败，无回绕 |
| 模糊 metadata 变更 | 原 mutation callback 的可捕获 panic 留下 indeterminate；删除不能清除它 |
| 真实退出尾账 lease | EBUSY 不提前关闭；原 Process/Task zombie lease 经过生产计费入口保留 debit，释放后才能删除 |

这些测试直接使用实际 controller，不复制 `CpuMax` 模型。revision 极值构造仅在
`cfg(ktest)` 中存在，没有产品 reset/restore。用于 no-refill 和尾账断言的时间间隔是受控
fixture，Process/Task 未实际调度；它们不建立 BOOTTIME 对齐、单窗口误差或 SMP 资格。
保留旧 Arc 后直接续账也不等于 controller toggle 与运行任务并发的实测。

文本负例的 `VmReader` 来自有效 slice；本轮未增加真实 unmapped-user-address 的页错
ktest，不能把该负例列为 EFAULT 实测。源码中失败的用户读取仍先于任何锁内 metadata
变更；完整新候选还需保留普通用户态 QueryAbi/错误入口回归。后续 G1-b 才处理统一结算、
BOOTTIME 和 ReadUsage；G1-c/d 负责可信授权及四操作闭合。移动设备、物理硬件和跨 CPU
资格均不从本切片外推。
