# G1 下一内核切片：先固定真实 CPU owner 的 revision 与实例寿命

本工单基于 desktop `01225ab0a20a9f25dd8313a7fad7652dd9154e30` / tree `592e13cc526a247ec4246a4cfe8458e07392d0e1` 的只读源码审计；以下拟议 API、锁接合和测试尚未实现或运行。本轮未修改共享内核、未构建新 kernel、未开启新 ioctl。总路线与资格边界继续见 [R8_NEXT_SLICE](R8_NEXT_SLICE.md)、[NATIVE_ABI](../NATIVE_ABI.md)、[PLAN](PLAN.md)。

**决定：最小可先合入的切片是 A06 原 CPU owner 内的共享 revision 与不可逆实例失效，两者一起交付；可信 init 的 CapSpace 激活接在其后。** 先授权一个尚不能证明当前实例、CAS 与普通 `cpu.max` 写入一致的目标，会把既有缺口带进可执行路径。只增加 `resource.manage` 类型或授予函数不能关闭这些缺口。该决定不要求重建 kernel；现有 Process、cgroup、调度器与 A03 原语已经提供可接合的位置。

## 1. 已有入口与真实缺口

下表行号固定于上述提交，不代表新测试结果。路径链接使用固定提交，避免后续移动行号造成错误归因。

| 接缝 | 当前源码事实 | 下一切片的直接约束 |
| --- | --- | --- |
| A05 ioctl | [hepta_control.rs:84–123, 204–231][control]：打开时保存 `Weak<Process>`、exec epoch 与 space；调用核对同一 Process 分配；仅 QueryAbi，其余已知操作 EOPNOTSUPP | 保持 `supported_ops = 1 << QueryAbi`，不能用“已能解析”宣告四个效果/历史操作 |
| Process 身份 | [process/mod.rs:159–162, 329–367][process]：exec 与 CapSpace nonce 分配用同一小锁；[execve.rs:98–119][exec] 成功替换后递增 epoch，耗尽 fail-stop | 可以复用精确 Process/image 身份；尚无实际 grant 槽、lease、observe/history 或 init 激活入口 |
| codec | [core/src/lib.rs:44–49][corelib] 单源引入 A02；[os-abi/src/lib.rs][wire] 实现五操作格式与范围检查 | 不复制 wire；现有目标 slot/generation 是输入值，仍需内核权限表解析 |
| A03 namespace | [reserve_native:1867][namespace]、[execute_native_reserved:2377][execute]、[LockBackend][locking]、[NativeTarget][native] 已有原语 | `aster-core` 当前未消费 `os-control`；portable-spin 不屏蔽 IRQ、不禁抢占，不能直接当真实 kernel backend |
| 实际预算 owner | [cpu.rs:30–70][cpu]：`SubController<CpuController>` 中只有一份 `CpuControl.max: SpinLock<CpuMax, LocalIrqDisabled>`；[controller/mod.rs:172–200, 232–250][controller] 持有实际 RCU Arc | 将 metadata 放入这把实际预算锁；`NativeTarget` 必须保留该实际 `SubController` Arc，不能保留 Process 或新建第二预算 owner |
| 普通配置写 | [cpu.rs:444–506][cpu-write] 的 `cpu.max` 解析后直接 `max.reconfigure(...)`；无资源 revision；`cpu.weight` 当前存储但未强制执行 | 绑定后的 Linux 预算写必须推进同一 revision；不能只在 HOS2 路径推进 CAS |
| owner 替换 | [controller/mod.rs:402–414][replacement] 新建 CPU controller、复制统计后 RCU publish；[systree_node.rs:545–573][death] / [inode.rs:91–116][rmdir] 移除空 cgroup | Arc 保活不证明仍是当前 controller；替换、删除必须在旧预算锁中 fence，包含尚未绑定 metadata 的旧实例 |
| 真实计费 | [sched_class/mod.rs:414–475][scheduler] 先结算当前运行段，再判资格/补充节流队列；[cpu.rs:527–640][accounting] 逐祖先计费与退出尾段 lease | 能复用计费/节流，但 `cpu.max` 更新未经过这一结算入口，不能直接声称 InstallBudget 生效时间准确 |
| 时间与观察 | [cpu.rs:72–83, 302–344][cpu] 用 raw TSC 对齐带宽窗口，累计 `cpu.stat` 则是 Jiffies；[BootTimeClock:184–187][boottime] 来自 calibrated clocksource | 不可把 TSC 当 ns，也不可把不同计费路径的字段拼成 HOS2 同版本 ReadUsage |

### 需要显式处理的时间原点差异

`CpuMax::period_clocks` 把微秒换成 TSC tick，窗口为 `now / period * period`。[TSC 初始化][tsc] 的 `calibrate` 把当时 cycles 对应到初始 Instant；BOOTTIME 通过该 clocksource 读取。两个值即使都由同一 TSC 得出，也不能省掉原点与舍入处理。HOS2 的窗口固定为 `floor(sample_boottime_ns / 100_000_000) * 100_000_000`，且必须满足 N0 单 CPU 的累计/分窗上界。[ABI §5、§9][abi]

因此共享 revision/实例切片不输出 ReadUsage，也不发布 `consumed_at_apply_ns`。下一步统一结算路径后，才定义 BOOTTIME 原点、保留转换余数、跨窗拆分、累计与分窗的同一快照。`NativeResourceState::apply` 的 `consumed <= effective % period` 是结果一致性检查，不能帮 adapter 建立真实时钟或补记尚未结算的运行量。[metadata]

## 2. 首个可合入 PR 的范围

此 PR 只形成 A06 内核资源接缝。继续使用当前只读 QueryAbi；不安装生产 init 授权，不生成 K/D，不激活额外 supported_ops。

### 2.1 metadata 与实际预算同锁

将 `CpuControl.max` 的保护值扩展为包含现有 `CpuMax` 的 owner 状态。保留唯一预算和记账字段，复用 A03 `NativeResourceState`，不复制 revision/CAS 状态机。下面是拟议内部形状，名称不构成现有 API：

```rust,ignore
struct CpuBandwidthState {
    max: CpuMax,                         // 原来那一份预算/运行量
    native: Option<NativeResourceState>, // 未装配时为 None
    detached: bool,                     // 只允许 false -> true
}
```

`detached` 不能由 `native.is_some()` 代替：若替换先发生，旧 Arc 随后才被拿去初始化，`None` 不能成为重新绑定旧实例的机会。关闭时始终置位 detached；如已绑定 metadata，同锁调用 `invalidate()`。保留原 metadata/revision 供已保留的上下文识别，不重建成 revision 1。控制未启用的 `CpuController.control == None` 实例不能绑定；启用产生新的 controller 分配，旧分配永不就地激活。

受信任初始化只允许对当前、活动、未 detached、从未绑定的实际 controller 安装一次 metadata。最小切片中，这个入口仅由 kernel ktest 的既有资源 owner 驱动；产品启动不调用它。首次绑定前没有 D 或 grant 暴露，因此这段普通 Linux 配置历史不冒充已存在的外部 CAS 历史；绑定以当前真实预算为基线 revision 1。ID 由后续可信资源登记提供，构造函数不得相信 ioctl 自报值；ID 在这个资源实例的寿命内稳定，替换实例必须获得新身份。

绑定后，每次已验证的普通 `cpu.max` 更新在同锁调用 `apply_owner_configuration`，其闭包只修改原 `CpuMax`。即使同值更新也推进配置 revision，但不能清零 usage/debt 或充值。revision 耗尽、indeterminate、detached 必须在修改前拒绝。无绑定状态继续走原兼容配置行为；已 detached 的旧 owner 不接受配置。当前 `cpu.weight` 未强制执行，本切片的 revision 明确定义为带宽配置 revision；若以后让权重或其他字段影响此资源的受控语义，须同时纳入共享 revision 与授权边界。

依赖接入由 A00/A03 更新 `aster-core` 的实际 Cargo 依赖和派生锁。不得把 `resource_state.rs` 剪贴进 kernel，或通过另造一套同名状态规避 `os-control` 的导入。`NativeResourceState` 本身无锁/分配；若当前 crate feature 迫使编入默认 portable-spin 别名，只使用 metadata 不意味着这个 backend 已获 kernel 资格。后续 delivery namespace 必须显式选择真实 backend。

### 2.2 替换和删除同批关闭

CPU subtree-control 替换在已经持有 `CgroupMembership::write_lock()` 的原路径中执行：准备新 controller → 核对旧 controller → 锁住旧 CPU bandwidth state 并不可逆关闭 → 释放旧锁 → 发布新 RCU Arc。新 controller 默认未绑定，不能自动继承原管理能力或 metadata。旧预算/统计对象按原引用规则释放；旧 D 的已发布结果由 namespace 保留。

`mark_as_dead` 在现有空进程、CPU charge lease、空 children 检查均通过后，并在 `inner = None` 发布前，关闭该 node 当前 CPU controller。不得提前取消仍需尾段计费的 lease。预算的管理关闭不阻止已经发生的 CPU 运行继续结算到原 owner；否则会用生命周期处理抹掉最终用量。

首次绑定与替换/删除都必须持 membership 排他锁。这样不会在旧 Arc 被关闭之后再通过“之前解析成功”的值重新初始化。只在 resolver 处比较一次 `Arc::ptr_eq`，然后脱离生命周期锁安装 metadata，不足以实现该条件。

### 2.3 A06 模块内部 API 草图

`SubController<T>` 当前是 cgroup owner 模块的私有类型，无需为 A05 改成全局公开。A06 自己下转真实类型并执行回调；对外仅交付已经存在的 `NativeTarget`/token/result 值。以下均是后续拟议函数，不是本次可调用入口：

```rust,ignore
// 在已有 membership guard 下，由可信资源 owner 一次性绑定；
// 在 cpu 模块内调用 NativeTarget::from_owner(actual_subcontroller_arc, ids)。
fn bind_native_once_for_owner(..., state: NativeResourceState)
    -> Result<NativeTarget, NativeCpuError>;

// 在 cpu 模块内 instantiate SubController<CpuController>；
// A05 不需要、也不能另包一个预算 owner 供 downcast。
fn execute_native_cpu<B: LockBackend>(
    core: &ControlCoreWith<B>, token: &ReserveTokenWith<B>, publisher: PublisherId,
) -> Result<DeliveryObservation, DeliveryError>;

// 调用者已在原生命周期路径排除了再次绑定。
fn close_native_incarnation(...);
```

第一 PR 仅交付一次绑定、普通配置共享 revision、实例关闭；`execute_native_cpu` 留到结算/权限装配齐全后实现，不能先返回伪 Success。

## 3. 锁序：本切片能确定的部分与后续待证明的部分

| 路径 | 当前/拟议顺序 | 禁止的反向动作 |
| --- | --- | --- |
| Linux `cpu.max` | 用户输入解析/校验 → `CpuControl.max` IRQ-disabled 锁 → 同一 metadata/预算变更 → 解锁 → 返回 | 持预算锁时 usercopy、分配、等待 delivery gate、回调 namespace |
| controller 替换 | membership 写锁 → 原 node 生命周期锁（已有处）→ 旧 CPU bandwidth 锁 → 关闭 → 解锁 → RCU publish | 预算锁内重新拿 membership；新实例继承旧 grant/identity |
| cgroup 删除 | membership 写锁 → node inner → children → CPU bandwidth 锁 → 关闭 → `inner = None` | 关闭代替 CPU charge lease 的排空证据；释放前遗漏最终计费 |
| 当前调度热路径 | per-CPU runqueue IRQ-disabled 锁 → process/cgroup RCU 读取 → 每个祖先独立的 CPU bandwidth 锁 | 从 bandwidth 锁进入 runqueue；IRQ 路径等待睡眠 mutex |
| 后续 HOS2 执行 | delivery execution gate（可等待）→ 稳定目标/生命周期约束 → 实际 runqueue 结算 → CPU bandwidth 锁中权限、CAS、预算变化 → 全部资源锁释放后发布 D 结果 | 只拿预算锁先改配置，再回头结算；持资源锁取得 namespace table |

当前祖先遍历每次只持一把 bandwidth 锁。它不是同时核对整条祖先授权/预算的事务。后续若要在子预算提交时核验祖先 epoch 与 parent cap，须定义同一 mutation 排序或一个明确的有界协调入口，并使 revoke 也采用该入口；不能拿各层历史快照逐个比较就宣称原子授权。

A03 四种 lock role 也不能全部替换为 IRQ-disabled spinlock：`SlotExecution` 跨 owner callback，`HistoryLoss` 要等待在途执行；盲目全程屏蔽 IRQ 会影响计费/唤醒甚至死锁。拟议 backend 使用可等待 gate 与短临界区状态锁的组合，GAT guard 留在获取它的 CPU/thread；在实际 IRQ/SMP 验证前仍不启用 namespace。原 OSTD `Mutex::lock` 使用 waitqueue，不能从 IRQ-disabled 资源回调取得。[locking]、[mutex]

## 4. 最小发布顺序与验收

这四阶段是 S4 内部的实施顺序，不新增产品完成百分比。

| 阶段 | 产品可见变化 | 必須通过的真实证据 |
| --- | --- | --- |
| G1-a：本工单首个 PR | 只读 QueryAbi 不变；原 CPU owner 支持一次 metadata 绑定和实例关闭 | 同树 ktest：真实 controller 的普通配置推进 revision；同值不充值；耗尽/失效拒绝；RCU 替换和删除后旧 Arc 不能重新绑定/修改；原 QueryAbi 客体负例回归 |
| G1-b：统一结算/观察 | 新内核内部能生成符合 wire 的真实 N0 使用快照，仍无产品写 grant | 单 vCPU、100 ms、预声明误差；运行中读取/降额/同值/跨窗/退出都先结算；对齐 BOOTTIME；Jiffies 只作独立低分辨率对照；同核 guest CPU 工作量证据 |
| G1-c：可信 init + 独立观察权限 | 最终 exec 的 Process/image 获得限定 observe；manage/history 仍按装配逐项保持关闭 | 错 Process、fork、SCM_RIGHTS、旧 exec、PID 复用、旧 controller、跨 scope、过期、祖先 revoke 均不越权；未配置来源失败；普通 root/open 不补授 |
| G1-d：五操作闭合 | 完整装配后才一次宣告 InstallBudget 及其必需 ReadUsage/QueryDelivery/RetireThrough | 同 D 准确重取/改内容冲突、CAS、copyout 后查询、1024 窗口、连续确认退役、revoked 后独立历史观察、受控 IRQ/锁交错、reboot 旧 D fencing；非 AI 客户端在同一内核执行 |

首个 PR 的负例必须命中原资源 owner，不以另一份 Rust `CpuMax` 模型冒充 controller 生命周期：

1. 保存旧真实 controller Arc，替换并发布新 controller；旧对象绑定/普通配置/HOS2 元数据操作均关闭，新对象未被自动授权。
2. 在未绑定时先关闭旧实例，再尝试绑定；必须拒绝，专门覆盖 `native == None` 漏洞。
3. 同一已绑定 owner 先做普通 `cpu.max` 更新，再用旧 revision；必须 conflict，预算/usage/debt 不因失败改变。
4. 预先保留 canonical state 的测试入口把 revision 推到最后合法边界；最后一次成功、后续全部写失败，无回绕。不新增产品 reset/restore API。
5. 删除仍有 CPU charge lease 的 node 必须保持 EBUSY；最后实际 debit 后才删除和关闭管理；累计用量不能丢失。
6. 参数解析、用户地址失败发生在任何 metadata/配置变更前；新的配置错误不能被记为成功或消费 D。

本轮只读取源码，没有执行上述计划测试。后续构建必须使用固定 nightly 与实际派生锁，在同一个候选内核记录代码/tree、ELF、initramfs、profile、serial 和正负分母。已有 A06 单项 quota/ktest 或 A03 宿主测试可作为回归基线，不能复用成新 G1 验收。

## 5. 附带发现与本工单边界

`cpu.max` 当前 parser 对“提供但无法解析”的 period 退回原 period，且未显式拒绝多余 token；源码范围为 [cpu.rs:482–504][cpu-write]。这是静态读取发现，未在本轮客体复现，需单列最小 parser 负例和兼容决定后修复；不要把它包装成本轮 G1 已修复。它也说明 native adapter 不能通过拼字符串调用 Linux 文件写入口来替代已校验的 typed CAS。

当前未发现必须丢弃 Asterinas/OSTD 的结构性证据。缺口可定位到原 owner 生命周期、统一计费、权限激活与 lock backend 的明确位置；先按这些位置接合。只有同一 W0/W1/profile 下可重现且局部修复不能满足要求的隔离、延迟或维护反例，才进入替换 OSTD 上层或独立 Rust kernel 的比较，不因尚未装配的接口启动第二套产品内核。

[control]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs#L84-L231
[process]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/process/process/mod.rs#L159-L367
[exec]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/process/execve.rs#L98-L119
[corelib]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/lib.rs#L44-L49
[wire]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/libs/os-abi/src/lib.rs
[namespace]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/libs/os-control/src/lib.rs#L1867
[execute]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/libs/os-control/src/lib.rs#L2377-L2409
[locking]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/libs/os-control/src/locking.rs
[native]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/libs/os-control/src/native.rs#L18-L40
[cpu]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs#L30-L344
[controller]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/mod.rs#L172-L250
[cpu-write]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs#L444-L506
[replacement]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/mod.rs#L402-L414
[death]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs#L545-L573
[rmdir]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/inode.rs#L91-L116
[scheduler]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs#L414-L475
[accounting]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs#L527-L640
[boottime]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/src/time/clocks/system_wide.rs#L184-L187
[tsc]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/kernel/core/comps/time/src/tsc.rs#L24-L46
[abi]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/docs/NATIVE_ABI.md
[metadata]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/libs/os-control/src/resource_state.rs#L130-L297
[mutex]: https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/01225ab0a20a9f25dd8313a7fad7652dd9154e30/kernel/asterinas/ostd/src/sync/mutex.rs#L12-L38
