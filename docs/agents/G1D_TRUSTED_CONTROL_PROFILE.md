# G1-d：固定受信角色的原生 CPU 管理与历史

本 profile 将 HOS2 的五个既有操作接到实际 `ProcessImageState`、原 `CpuBandwidthState` 和 `libs/os-control` 投递核心。同一个静态 ELF 的一次内核验证快照准备三个独立进程：manager、受控 workload、recovery。角色来自固定内核启动计划；PID、UID、路径、argv、启动页和调用者提供的 hash 均不产生授权。

本文记录实现与验收契约。候选 Rust 编译、内核回归和真实启动是否通过，以绑定该源码的云 CI 原始记录为准；源码、host 检查或 ktest 名单不代表 guest 成功。这是单 CPU、固定初始映像实验，明确不宣称 Hepta 磁盘持久性或硬件设备资格。

## 构建与来源

沿用项目既有云构建、固定 nightly、VDSO 和 lock：

```sh
HEPTA_G1D_TRUSTED_CONTROL=1 \
HEPTA_TRUSTED_INITIAL_ELF=/absolute/path/to/reviewed/g1d-init \
A01_RUN_DIR=/absolute/path/to/new-output \
support/build/kernel.sh kernel
```

wrapper 和 make overlay 都拒绝同时设置 `HEPTA_G1C_TRUSTED_OBSERVE=1` 与 G1-d flag。最终 make argv 额外包含 `HEPTA_G1D_TRUSTED_CONTROL=1`、`FEATURES=g1d-trusted-control` 两个 token；实际 OSDK 命令包含 `--features=g1d-trusted-control` 并回显在 `kernel.log`。Cargo 内部依赖 G1-c 的封存前置条件，不给 make 传第二个 profile。

实验只支持 `kernel` 目标；`kernel.sh run_kernel` 保留普通启动门禁。专用 [runner](../../tests/kernel/control/run_g1d_guest.py) 用同一内核分别启动精确 ELF、尾部篡改、截断输入的 initramfs；沿用 `rdinit=/test/g1d-init` 定位文件，路径不授予权限。

freezer 在新输出目录创建只读 `trusted-initial.elf`，内核实际 `include_bytes!` 指向该副本。`trusted-initial-manifest.json` 完整字段为：

| 字段 | 值 |
| --- | --- |
| schema / profile | `hepta-g1d-trusted-initial-v1` / `g1d-trusted-control` |
| source / embedded_input | 源文件与实际嵌入副本的绝对路径 |
| bytes / sha256 | 副本实际长度与摘要 |
| supported_ops / features | 62 / 0 |
| bootstrap_version / bootstrap_bytes | 2 / 192 |
| roles | `["manager", "workload", "recovery"]` |
| cap_ns / period_ns / lease_ns | 50,000,000 / 100,000,000 / 300,000,000,000 |

清单版本 1 与启动页版本 2 是不同格式。G1-d 不包含 G1-c 的单槽 slot/generation 字段；G1-c 默认清单保持原格式。两处 Cargo feature 由 `verify-source.py` 在原 G1-a/G1-c 精确插入规则后派生，其他上游清单字节、包版本和 lock 保留原检查。摘要用于构建证据绑定，不是用户授权证明。

## 一次快照与真实初始事务

`program_loader/elf/trusted_initial.rs::TrustedInitialSnapshot` 对打开的文件完成一次有界读取、EOF 与内核嵌入字节比较，沿用 [G1-c](G1C_TRUSTED_OBSERVE_PROFILE.md) 的静态 x86_64 ET_EXEC 限制。解释器、shebang、PIE、W+X、重叠 LOAD 页及不合法 entry 均拒绝。三个角色不能从稍后的 inode 内容分别读取。

`process/process/init_proc/trusted_roles.rs` 分配三个真实 Process/VMAR，用同一快照分别初始化无文件 backend 的私有 RAM VMO。完成最终页面回读、权限/entry/启动页校验及 seal 后，各自的不可 Clone `LoadedInitialImage` token 在其实际 VMAR 上消费。workload 同样封存，但没有资源或历史槽。

只有 workload 进入实际 `hepta-g1d-{workload_image_nonce}` leaf。manager、recovery 留在原 root 资源域，其槽不能削减自己的恢复资源。两个管理 delegation 和两个独立 D namespace 建立后，三个原 first-run claim 全部成功，原 parent/process-group/PID 表关系发布，才调用任一 `Thread::run`。workload/recovery 是 manager 的正常子进程；readiness 文件只协调测试顺序。

manager 首先完成原 first-process 的组件、设备和 console 文件表初始化，再由绑定其实际 Task 的一次启动闭包释放两个已准备的 child Task。每个 child 在首条用户指令之前复用同一 console 初始化逻辑，分别打开自己的 fd 0/1/2；三个进程不共享可变文件表。启动闭包不从 fork/exec 继承，不产生角色或 grant。此顺序使 `AT_SECURE=1` 的静态 libc 在进入 `main` 前就能检查标准描述符，不依赖用户态 readiness 文件补做运行库之前的初始化。三次 image/role commit 与 activation 仍必须先于任何 `G1D_BOOT`。

精确输入有三次 loader 的 `trusted initial image committed`，并有下列三条角色记录，均先于 activation 和任何 `G1D_BOOT`：

```text
[hepta-g1d] trusted role committed: role=1 pid=...
[hepta-g1d] trusted role committed: role=2 pid=...
[hepta-g1d] trusted role committed: role=3 pid=...
[hepta-g1d] initial control activated: manager=... workload=... recovery=... cap_ns=50000000 period_ns=100000000 lease_ns=300000000000 hepta_durability=false
```

两种篡改都在任何角色准备前拒绝，精确 marker 分别为 `[hepta-g1d] rejected initial image: manifest-byte-mismatch` 与 `[hepta-g1d] rejected initial image: truncated-snapshot`。负控必须复用同一内核/嵌入 ELF，有具体拒绝、原始失败退出码且没有提交/activation/用户日志；任意 panic 或超时不算通过。

G1-c 的 VMAR/alien-access 限制保持：代码/vDSO/启动页不能替换或增权；允许 RELRO 减权；已开 proc-mem fd 在实际写入时再检查；禁止跨 Process 共享 VMAR；fork 是独立 COW 且无 grant。封存固定映像不证明程序内存安全或设备 DMA 安全。

## 发现页与角色

三个初始映像都有 `AT_HEPTA_BOOT=240`，地址由原 VMAR 分配器选择，页对齐、只读、非执行并封存。整数为 u64 little-endian，ID 为原始 16 字节。

| 偏移 | 内容 |
| --- | --- |
| 0 | 8 字节 `HOS2BOOT` |
| 8 / 16 / 24 | version=2 / role=1、2、3 / bytes=192 |
| 32 / 40 | observe slot / generation |
| 48 / 56 | manage slot / generation |
| 64 / 72 | manager history slot / generation |
| 80 / 88 | recovery history slot / generation |
| 96 / 112 / 128 | boot ID / manager CapSpace ID / recovery CapSpace ID |
| 144 / 152 / 160 | 实际 manager / workload / recovery PID |
| 168 / 176 / 184 | 最大 cap / 固定 period / lease |
| 192..4096 | 全零 |

| 角色 | 1:1 observe | 2:1 manage | 3:1 manager history | 4:1 recovery history |
| --- | --- | --- | --- | --- |
| manager | workload | workload | observe | 无 |
| workload | 无 | 无 | 无 | 无 |
| recovery | workload | workload，独立 delegation | observe + ack | observe + ack |

无权 handle 字段为零。复制页、传 fd 或修改 argv 不创建槽。两个管理/观察 lease 从同一真实 bootstrap cut 起固定 300 秒，到期点排除，无自动续约。history 权限依赖当前实际映像和精确 namespace，独立于旧管理 lease；recovery 可继续读/退役已结束管理映像的结果。

## 五操作、计量与错误

wire 沿用 [NATIVE_ABI](../NATIVE_ABI.md)，无新 ioctl/opcode。G1-d 所有进程统一声明 ops=62、max_request=40、max_response=64、features=0；普通构建为 2/0/48，G1-c 为 6/0/64。权限分别解析，QueryAbi 不授能力。

| 路径 | 实际职责 |
| --- | --- |
| `device/misc/hepta_control.rs` | exact Process/image 会话、完整有界 copyin、原 codec/capacity、调用后有界 copyout |
| `process/process/image.rs`、`trusted_control.rs` | 原映像私有 slot 与 process-context final-use gate，只有固定初始事务安装 |
| `process/process/control_lock.rs` | 原 `ControlCoreWith` 的 OSTD sleeping mutex backend |
| `libs/os-control` | 原连续 D、1024 窗口、完整内容绑定、执行一次、不可变结果及受权连续退役 |
| `controller/cpu/native/trusted_control.rs` | 实际 typed owner pin、canonical grant、N0/lease/clock/身份检查 |
| `controller/cpu.rs`、`native.rs` | 原 `CpuMax` 资格/计量、同锁 revision/CAS、周期/累计用量/正债务 |

InstallBudget 先在原 core 预约完整 D/NativeRequestBinding，释放 table 锁后执行 typed 原 owner callback。同 D 改 cap/expected_revision 为 conflict；原请求重取返回原终态，不再次更新 CPU。有效槽上的超 ceiling、旧 revision、lease/计量故障成为不可变终态；codec/capacity、未知槽或跳序失败不烧下一序号。copyout EFAULT 可能发生在效果与终态保存后，必须用原 D/原内容恢复，不能撤销已应用预算或用新 D 盲目重发。

`CpuMax` 仅增加同 quota 的 0..999 ns 余数。原资格和正债务计算使用精确纳秒 cap，1/999/1001 ns 不向上舍入。Linux cpu.max 文本只是微秒投影。更新按旧 quota 结算，保留窗口、已用量、累计量、正债务和节流状态；新 D 同值写推进 revision，不充值。

无初始控制槽返回 permission_denied(2)，已授权但 slot/generation 不匹配为 stale_handle(3)；失效/删除/替换 owner 或到期为 revoked(4)，不可靠 clock/profile/accounting 为 indeterminate(8)。gap=10，满窗=6，冲突=5，已退役=11，未终局/退役遇 pending 前缀=9，退役越过 NotSeen=10。manager 没有 ack 权限返回2。QueryDelivery/RetireThrough outer revision=0；非零 status payload 为空且 revision=0。旧 image fd 为 ESTALE，异 Process 使用原 fd 为 EPERM。

受控 leaf 有效 Linux cpu.max 写、迁入、迁出、父域禁用 cpu 均在原 cgroup 路径拒绝，现有 systree 映射为 EACCES；无效输入仍按原 parser 报错。内部失败准备/退出清理使用原生命周期入口。未受信 leaf 的 Linux 行为保留。这四条限制不是整机 root/信号/文件/内存/设备隔离证明。

## 锁序与映像结束

初始核对保持 VMAR → TaskSet → image，CPU 创建保持 membership → runqueue/原带宽锁。ELF I/O、页校验、core/slot 分配及用户 copy 在 IRQ/CPU 锁外。

运行操作在 image mutex 取私有 slot Arc 后释放 image，取得该 slot 的 operation gate，重新检查 exact live image 并释放 image，再进入原 D execution gate → 本 CPU runqueue → 原 CPU owner。CPU callback 核对单 CPU、可靠 BOOTTIME、lease、当前 controller Arc、reservation pin、canonical grant、原计量与 revision。namespace/table 锁不跨实际 mutation，CPU 锁内不创建 D/复制用户数据。

exec/exit 在 TaskSet → image 下标记 Closing，释放二者后等待 operation gate。先前已准入的同步操作连同原结果保存完成，再在原 CPU 锁内 revoke 该 delegation；不撤销另一 recovery delegation，不重置 cap/计量或删除历史。old-image slot/pin 的有意义析构在 image 锁外。

同 Process 线程共享槽/gate；fork、SCM_RIGHTS、新开 fd 不安装授权。普通 exec 即便执行相同 ELF 也不获得 auxv/slot；旧 fd 失效，新 fd 能 QueryAbi，但无旧资源/history 权限。recovery 的独立实际映像仍持 old manager namespace 的受限 view。

## 历史与 Hepta 边界

两个 namespace 各自使用原 1024 槽 core。满窗拒绝新 D，旧结果继续可查；query/retire 不占新槽。manager 只有 history.observe；recovery 持有 non-Clone 原 owner authority。退役仅连续 terminal 前缀、保留 suffix、旧 D 永久 retired，不因容量释放重新执行。

固定 C 映像是**资格实验的 ack holder**。`G1DQUAL1` 标签绑定 namespace/frontier 并调用原 authority；它不是 SQLite/fsync/业务终态收据。无权 manager 不能凭同标签获权。实验明确 `hepta_durability=false`；生产 Hepta 进入该角色前，必须由其现有 durable owner 在受信 adapter 中核对和持久保存 K↔D/真实终态，再允许 RetireThrough。

实际已核 Hepta 主路为 ProductionDurableWriter → LocalLeaseOutbox → 原 CognitiveStore。K 的 operation_id/scope_digest/语义由原 owner 保存，原完整 payload 可承载 D，不在内核存 K、不另开 DurableOperationStore。真实 ioctl 必须位于原 FinalUse 验证包围的同步 target dispatch 内，不能仅放进 grant 检查后才 poll 的 future。

仅被 outbox 规划、在 ioctl 前可靠证明未进入的 D 尚未占内核序列；本协议没有 reserve/no-op/cancel opcode。后续能否用原计划，取决于同一 durable owner 的 K 状态/fence。NotSeen、超时或断线不证明未进入；不得伪造 no-op/terminal 烧序号来绕过未知效果。

## 验收和范围

默认 core gate 保留历史238及 G1-c 9项具名回归，追加8项实际 owner 回归，最低255，17个 required names 各出现一次。新测试用原 cgroup/production OSTD D backend，覆盖精确纳秒资格、消费/正债务保持、拒绝/replay、独立撤销恢复、lease/clock/fault、Linux 别名、1024 窗口/退役。显式时间 cut 是 fixture，不替代 calibrated clock/真实 syscall。

[g1d_init.c](../../tests/kernel/control/g1d_init.c) 在真实 guest 验证三角色、用量/heartbeat、D1..D11、实际 copyout EFAULT、replay/conflict、cap=0 停止并独立恢复、1/999/1001ns、四条 Linux 别名、1024窗口、部分/最终退役、fork/SCM 与同一个已授权 PID 最终 exec。仅有一个有效 manage target，不能把无效 slot 当作两个有效资源间冲突证明；原 core 跨目标测试保留。

三 boot 必须绑定相同源码、protected inputs、实际 make/OSDK 命令、kernel/probe/initramfs/QEMU/串口/退出。原 A06 全量 OSTD/core、反向控制、ordinary QueryAbi、Linux32、权限32、SCM27、NOFILE37、CPU 和 SMP gates 不降低。

尚未提供动态 runtime 授权/更新、自动续约、一般 ancestry/迁移、完整 SMP 原生预算、Hepta durable receipt、用户暂停原因、设备/DMA。lease 到期不会自动恢复 cap=0；固定实验须在300秒内由 recovery 恢复，生产故障策略另行闭合。
