# 原生控制 ABI 与恢复契约

文档版本0.3。实验协议 **HOS2 major=2/minor=0**，未发布为稳定ABI。HOS1的随机写request_id、三操作恢复限制不再作为当前运行契约；新编号尚未分配，不能在同一已发布ioctl下默默重新解释旧请求。实际实现状态见[STATUS](STATUS.md)。本文件定义接口，不代表存在内核实现。

## 1. 首期与可信启动交接

仍使用Linux ELF。N0为单CPU控制实验；动态资源迁移、通用设备提交和公开Transfer不在本版。公开操作限定QueryAbi、ReadUsage、InstallBudget、QueryDelivery、RetireThrough；后两项仅补写接口的恢复与有限存储闭环。

可信init按以下顺序执行内部启动事务（不是普通应用API）：CreateStoppedTask先建立Task、稳定资源对象ID及ResourceDomain归属；LoadAndCommitExec完成最终ELF/loader映射、exec_epoch和新CapSpace；ActivateGrant核对可信启动记录、最终映像/依赖身份、进程仍暂停且exec_epoch未变，装入衰减的管理和观察能力；PublishBootHandles将句柄交给受限只读启动页；最后Resume。启动页是句柄发现方式，不是授权来源。用户代码首次运行前已受资源限额约束。

失败时销毁未激活任务及其引用，不恢复旧exec权限。普通后续exec撤销原管理权，不自动重新执行ActivateGrant。桥重启先fence旧管理者及未执行预约，再由init对新映像独立激活；不能仅依据相同PID或可执行文件名恢复权限。

open(`/dev/hepta-control`,O_CLOEXEC)创建绑定process-start/exec_epoch/boot/CapSpace的会话，不签发新权限。QueryAbi自举使用固定transport及HOS2头。资源域和观察命名空间由可信启动记录建立，不允许请求体自报workspace获得权限。

## 2. 单一对象与生命周期

所有native/Linux/Android入口落到同一个底层对象策略；DAC、MAC、能力和资源上限取交集。普通POSIX文件打开沿用该对象既有访问权，不要求未使用HOS控制的Linux程序额外提交新wire句柄。兼容域UID0不等于机器所有者。设备别名、调试、process_vm、/proc fd、Binder/cgroup入口均不能绕过边界。

| 行为 | 规则 |
| --- | --- |
| 同进程线程/dup | 共享CapSpace，仍查实际调用者与当前授权 |
| fork | 普通fd保持Linux继承；子进程新CapSpace，继承control fd不能调用父会话 |
| exec | 增加exec_epoch，撤销旧管理委托；只有可信启动事务可向最终新身份授新权限 |
| SCM_RIGHTS(control fd) | fd可以传递，但不能转移打开者身份或管理权限 |
| 关闭/slot重用 | generation变化，溢出则退役；强引用只保内存寿命，不延长操作权限 |
| 进程退出 | 关闭新准入；未决/已完成投递的寿命不由进程对象单独决定 |

管理句柄指向ResourceDomain。**历史观察句柄DeliveryView指向特定boot/CapSpace投递命名空间**，不使用原管理slot替代。可信init把DeliveryView授予同工作区的原持久owner或其被认证的接替者；观察权不含执行权，retire另需history.ack。进程退出可释放CapSpace进程引用，但DeliveryView仍可保留只读历史。没有有效观察能力时不通过payload中的boot/space泄露历史。

旧命名空间完全释放后查询只能报告history_lost；其旧会话永久失效，不因新进程创建而复活。是否能继续证明历史由原Hepta owner决定，不能以lost解释为零效果。活动命名空间/保留历史都有限额；新准入可拒绝，但停止与基础恢复不依赖新建命名空间。

## 3. transport与解析顺序

固定32字节原生端序transport：0 request_addr:u64，8 response_addr:u64，16 request_bytes:u32，20 response_capacity:u32，24 reserved:u64=0。首期仅x86_64小端；32位compat/其他架构独立验证。只把32字节描述符编码进_IOWR，payload不进ioctl大小位。用户地址检查不由codec代替。[ioctl来源](SOURCES.md#ioctl)

顺序：检查transport和有界地址算术 -> 一次复制完整输入 -> 验证magic/version/长度/保留位 -> 解析已知opcode与payload -> 确认输出容量 >= 该opcode成功响应所需尺寸 -> 会话与授权/投递处理 -> copyout。复制/缺页/分配不能在IRQ/spinlock内执行。输入与输出可重叠，因为先完整快照输入；之后修改原用户缓冲区不改变执行内容。

未知ioctl=ENOTTY；未知协议=EPROTONOSUPPORT；未知opcode=EOPNOTSUPP；头/长度/保留位错误=EINVAL；输入或输出访问错误=EFAULT；输出不足=EMSGSIZE。已知且格式正确的操作的权限、CAS和容量结果放入HOSR status。结构性失败不产生投递记录；已预约的语义拒绝必须固定为终局，不能之后同D变成执行成功。

成功ioctl返回0。调用者只解析返回header声明的64+payload_len字节，剩余response_capacity不属于结果；驱动仅copy实际结果长度。EFAULT后整个输出都不可当有效响应，即使效果可能已提交；使用原D重取或QueryDelivery，不生成新逻辑操作。返回错误码不普遍证明无效果。

## 4. 请求和响应头

两者均64字节、逐字段little-endian、禁止Rust struct内存布局直传。最大payload=65536、最大frame=65600，实际frame必须恰等于64+payload_len。

| offset | 请求 | 响应 |
| --- | --- | --- |
| 0 | magic[4]=HOS2 | magic[4]=HOSR |
| 4/6 | major:u16=2/minor:u16=0 | 同左 |
| 8/10 | opcode:u16/flags:u16=0 | opcode:u16/status:u16 |
| 12/16/20 | header_len:u32=64/payload_len:u32/reserved:u32=0 | 同左 |
| 24 | request_id[16]，非零 | 原request_id回显 |
| 40/48 | target_slot:u64/target_generation:u64 | boot_id[16]，非零 |
| 56 | reserved:u64=0 | revision:u64 |

QueryAbi目标两项为0；其他均非零。QueryDelivery/RetireThrough的目标为**当前**DeliveryView，而不是被查询请求的旧管理句柄。初次QueryAbi返回内核boot/space，客户端从受信任设备建立会话绑定；ID本身不证明来源。

status：0 ok，1 invalid_input，2 permission_denied，3 stale_handle，4 revoked，5 conflict，6 resource_exhausted，7 unsupported，8 indeterminate，9 busy，10 out_of_order，11 retired。非零status payload为空且revision=0。unknown status拒绝，不当ok。只有成功ReadUsage/InstallBudget头revision非零；其他成功头revision=0。

InstallBudget的request_id规定为sequence:u64的小端8字节加8个零字节，sequence∈[1,u64::MAX-1]。序列作用域由内核CapSpace提供。读请求/RetireThrough只要求非零关联ID，不参与写序列；未来新写opcode必须显式纳入同一序列或独立定义，不能自行复用序列。该变化是HOS2与HOS1不兼容的原因。

## 5. 五个操作

| opcode | 请求payload | 成功响应payload | 权限 |
| --- | --- | --- | --- |
| 1 QueryAbi | 空 | 48字节 | 合法打开绑定；不授能力 |
| 2 ReadUsage | 空 | 64字节 | resource.observe |
| 3 InstallBudget | 32字节 | 24字节 | resource.manage |
| 4 QueryDelivery | 40字节 | 64字节 | history.observe，精确命名空间 |
| 5 RetireThrough | 40字节 | 16字节 | history.ack，由持久owner使用 |

QueryAbi：0 space_id[16]非零；16 page_size:u32非零二次幂；20 max_request_payload:u32；24 max_response_payload:u32；28 reserved:u32=0；32 supported_ops:u64（bit1..5）；40 features:u64=0。支持bit1必需，未知bit拒绝。宣告InstallBudget必须同时宣告ReadUsage、QueryDelivery和RetireThrough；retire要求query历史。payload上限不超过65536且至少容纳宣告操作的最大请求/响应（完整集40/64）。只宣告格式支持不是运行能力，内核必须按已实现范围报告。

ReadUsage：八个u64依次sample_boottime_ns、cumulative_cpu_ns、window_start_ns、window_consumed_ns、active_cap_ns、active_period_ns、event_sequence、dropped_events。原点为内核初始时钟域boot起点0，period=100000000ns，window_start=向下取整(sample/period)*period。cumulative>=window_consumed、dropped<=event_sequence；降cap后consumed>cap合法，调度超支不得篡改统计隐藏。快照必须先结算当前运行量，再同版本读取所有字段。该接口只给局部CPU观测，不声称已经解释父域/I/O/锁等待原因。

InstallBudget请求：expected_revision、period_ns、cap_ns、reserved=0，四个u64。expected_revision∈[1,u64::MAX-1]、period固定100ms、cap∈[0,period]。响应三个u64：previous_revision、effective_boottime_ns、consumed_at_apply_ns；响应头revision=previous_revision+1。成功原D重取返回原值，不再增加revision。

QueryDelivery/RetireThrough请求相同40字节：0 history_boot[16]、16 history_space[16]、32 sequence:u64。三项非零且必须与DeliveryView授权范围匹配；不是凭引用取得查询权限。跨boot旧记录不能假装仍存在于新内核。

QueryDelivery响应64字节：0 state:u16；2 saved_status:u16；4 reserved:u32=0；8 sequence:u64；16 stable_object_id[16]；32 saved_revision:u64；40 previous_revision:u64；48 effective_ns:u64；56 consumed_ns:u64。state=0 reserved、1 terminal、2 retired、3 not_seen、4 history_lost。terminal+saved_status0是原成功：object_id非零且saved_revision=previous_revision+1。terminal+错误status保留原拒绝，其余元数据为0。其他state的saved_status及object/revision/time字段为0，仅保留sequence；retired/not_seen/lost均不授予重放权。outer request_id是本次查询ID，不能与被查询写序列混同。

RetireThrough响应16字节：retired_through:u64、next_sequence:u64。重复确认旧前沿返回当前前沿，要求retired_through>=请求sequence且next_sequence>retired_through。失败无半次推进。它只回收已经持久确认的连续终局，不允许跳过未决项。

## 6. CapSpace级预约、资源提交与锁

每个CapSpace只有一个写投递窗口，覆盖所有目标。N0采用严格有序写序列：new sequence必须等于next_sequence。next_sequence初始1；大于它为out_of_order；小于等于retired_through为retired，绝不重新执行。

先在**CapSpace投递表锁**原子预约D和完整canonical请求，预分配固定结果槽并增加next_sequence；不同目标不能各自预约同一D。已有D同内容且reserved返回busy/indeterminate；已有D不同内容为conflict；terminal只重取原结果。表满返回resource_exhausted且不消费序列、不产生效果。预解析失败也不消费序列。获得预约后的权限/CAS/目标拒绝必须记录为terminal错误，相同D以后不变为成功。

预约锁不跨资源效果持有。取得预约与grant强引用后释放表锁，进入资源mutation锁；在同一临界区检查grant当前状态/epoch、期限、目标稳定身份、revision和计费，执行预算变化并发布已预留的终局结果。该处是效果线性化点。结果单元只有预约所有者能从reserved变为terminal，读者以对应release/acquire或锁读取一致内容。不能持资源锁反向取得投递表锁；retire只处理已发布终局，不访问资源锁。

grant关闭/撤销通过与准入相同的资源mutation锁设置alive/epoch，CapSpace槽移除仅撤掉发现路径。强引用不能让已撤销grant继续通过。进程退出只在fence实际执行者并确认不会继续提交后，把未执行预约收敛为明确的无效果错误；无法确认的保留reserved/indeterminate，而非盲删。

revoke早于准入则拒绝；准入早于revoke按在途状态处理。撤销ACK只证明新准入关闭，不等于硬件排空。runqueue/domain锁的真实顺序仍须对固定上游源码验证；这个设计不冒充已排除内核死锁。

## 7. 有界结果、历史读取与退役

投递窗口首期最多1024条**未退役**写记录，不是进程终身1024次限制。原Hepta owner在其既有持久账本确认连续结果后调用RetireThrough。内核仅验证调用者history.ack能力、前沿连续且全为terminal；磁盘持久确认是可信owner义务，不能由请求体自报布尔值证明。

retire推进单调retired_through，释放对应大结果；迟到sequence<=前沿一律retired，不管请求字节是否一致。不得LRU淘汰后把missing当新操作。next_sequence严格连续使前沿可有界证明；序列将溢出时停止新写，排空并重新可信创建命名空间，不回绕。

history查询独立于旧管理句柄；管理权撤销/slot重用后，合法DeliveryView仍可读取。观察权限完全撤销时拒绝查询而非恢复执行权。进程退出后的保留有独立引用与上限；所有view丢失后的history_lost必须由持久owner保留未知K，不能自动重放。确认/历史读取不占新的写记录容量，满表仍能回收终局和停止新效果。

## 8. K、D与恢复目标

持久逻辑操作使用原Hepta scope_id/operation_id，其principal/workspace由原owner解析；摘要在记录中，不在查找键里。D=(boot,CapSpace,sequence)仅表示一次内核投递。稳定资源object_id来自可信启动/资源owner，与slot/generation不同。授权对象必须解析到该稳定身份。

旧K效果未知时，当前cap/revision相同不构成历史证明。先fence旧管理者、读取当前对象并取得新授权，可建立**新目标收敛操作**，在语义记录中关联旧K但不把旧K改成Applied/NotApplied。新操作的前驱与资源revision重新固定，由原owner处理未决前驱；不伪造原操作终态来绕过该约束。无法在现有owner契约表达时，报告上游接合缺口，不创建第二账本。

该收敛规则仅适用于已审核的绝对预算状态设置。磁盘写入、外发消息和设备不可逆动作不可照搬。旧结果不确定与当前目标已达成是两个事实。

## 9. 预算与调度接合

cap是固定对齐周期累计CPU运行时间上限，不是保底/deadline/滑动窗口保证。InstallBudget结算至生效时刻，保留窗口原点、已用U及祖先用量；余额max(0,cap-U)，相同值更新不充值。每段真实运行按所跨窗口分摊，只有真实周期切换重置窗口计数。

首期运行时必须核验单CPU。共同资格/记账层覆盖全部受控任务；未覆盖FIFO/RR等策略时明确拒绝受控任务切换，不允许经Linux sched接口绕过fair限制。保留内核必要stop/idle和独立恢复域，不向普通任务授此豁免。任务无syscall时也须由独立timer触发节流和下周期唤醒。

优先复用已校准上游时间设施；raw TSC是tick，不直接当ns。转换采用受检宽算术并保留舍入余数，覆盖tick、切换、阻塞、退出、更新、快照各结算点。单CPU也测量量子/不可抢占导致的超支与恢复延迟，不把误差只留给SMP。所有计数/序列禁止静默回绕；到上限停止相关新管理操作并保持恢复入口。

N0不支持CPU集/period变化、迁移、SMP资源控制。后续全路径祖先额度预留与锁序另验。内存wire不在本版：charge_owner残留对象、共享页压力与最终释放属于未来内存控制前置规则，不成为CPU格式原型的虚假前提。

## 10. 回退和后续设备边界

独立OS恢复职责由基础init/监督进程承载，而非仅依赖Hepta runtime.supervisor。用户明确暂停、管理租约失效、模型不可用和压力紧急状态有不同规则；cap=0不自动表示用户暂停。暂停原因来自可信控制记录，不由本版cap字段猜测。恢复资源及其祖先不在普通管理envelope内。

设备execution/cancel/effect/observation仍独立。quiesced+partial不等于none；可释放页必须有静止/隔离证明且无CPU引用。device-owned标志不自动撤销mmap别名，实际映射权限和DMA同步由驱动路径负责。通用设备opcode未实现，不宣称本版CPU协议解决设备恢复。

## 11. 验证边界

黄金向量只测格式；生命周期模型只验证指定交错；真实credential、锁、copyout、runqueue、timer及DMA均需内核实测。至少覆盖：exec后激活、同D跨目标预约、撤销后仅观察、连续写超过1024次并退役、旧序列迟到、拒绝结果不变、同观测不同历史、用户暂停与失效回退区分。
