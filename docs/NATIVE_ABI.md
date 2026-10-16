# 原生控制 ABI 与资源契约

文档版本 0.2；实验协议 HOS1 major=1/minor=0。协议未发布为稳定 ABI。实际实现范围见 [STATUS](STATUS.md)。本文件是字段、身份、生命周期和预算语义的唯一规格入口；内核、设备和权限机制不能由编解码单测替代。

## 1. 首期范围与自举

第一阶段继续使用 Linux ELF/调用约定。原生指 Hepta 可以使用新内核资源能力，不意味着已建立独立可执行格式或另一套 libc。首期 wire 操作仅有 QueryAbi、ReadUsage、InstallBudget；通用设备提交、跨进程转授、迁移、动态资源域创建不是这版公开 wire 功能。以前列出的这些名称是后续设计需求，不分配假接口或宣告支持。

init 使用可信启动配置创建测试资源域、任务及委托，把能力槽位装入实际进程的 CapSpace；应用不能通过自报 PID 或 workspace 获取第一个能力。CapSpace 附着已有内核进程对象，不复制第二套 Task/VFS。普通应用可无控制权限运行。

open(`/dev/hepta-control`, O_CLOEXEC) 创建一个绑定当前 process-start identity、exec_epoch、boot_id、CapSpace 的控制会话；open 本身不授予资源操作权。每次 ioctl 检查实际调用者与打开绑定，不能只检查 fd 存在。QueryAbi 使用固定 V1 transport/头部完成自举，不要求预先协商；不认识 V1 ioctl 的系统返回 ENOTTY。新的不兼容 ABI 使用新 ioctl 命令，不重新解释已发布命令。

## 2. 一个底层对象、所有入口共同检查

原生、Linux、Android 的访问入口必须落到同一对象的权限与资源执行者。域内 Linux UID 0 不是机器所有者；DAC、MAC、原生能力及资源上限取交集，而非任一通过即可放行。device node 别名、raw block、ptrace、process_vm、/proc fd、cgroup 管理和 Binder 转交不能绕过宿主域边界。

| 入口/生命周期 | 规则 |
| --- | --- |
| 线程 / dup(control_fd) | 同进程共享 CapSpace 与绑定；每次仍查当前授权 |
| fork | 普通 fd 按 Linux 语义继承；子进程使用新 CapSpace，继承来的 control fd 因打开者绑定不匹配而不可调用 |
| exec | 递增 exec_epoch、失效旧管理委托；普通 fd 依其 CLOEXEC 规则处理，遗留 control fd 也不能保留权力 |
| SCM_RIGHTS(control_fd) | 可传递 fd 本身，但接收进程不能使用发送者的会话；设备专属拒绝不改变普通 fd 传递语义 |
| 调试/读取 fd 别名 | 检查实际调用身份、域与 MAC，不能读取或盗用受限桥的权限 |
| 普通 device fd | 打开及需要持续授权的提交点执行相同域/对象规则；不是只有控制 ioctl 受限 |
| 进程退出 / close | 释放进程引用，不等于设备已静止或语义效果被撤回 |

slot 与 generation 只能在匹配的 CapSpace 内解析；generation 溢出退役槽位。域内 root 不能创建宿主根能力。M0 的控制会话不支持跨进程转授，因此不会发生同编号误认接收者另一个合法对象。未来 Transfer 必须创建接收端新条目并绑定目标身份/授权上界；不能简单复制两个整数。

## 3. ioctl 传输层

V1 transport 描述符为固定 32 字节，原生端序的四个固定宽度字段加显式保留位：offset 0 `request_addr:u64`，8 `response_addr:u64`，16 `request_bytes:u32`，20 `response_capacity:u32`，24 `reserved:u64=0`。它是用户地址的唯一传输层表示；内部 wire 不包含地址。首期 target 为 x86_64 little-endian；ARM64/32 位 compat 单独验收，不能因布局固定就声明已支持。

ioctl 编号在实际驱动导入时按上游分配规则选定；本轮 codec 不伪造可用设备号或 ioctl。只将 32 字节 transport 类型编码入 _IOWR，不能把 64 KiB payload 编码到 ioctl 大小字段。用户地址上限、compat 零扩展、整数溢出、页访问与 copyout 必须由驱动检查。[接口参考](SOURCES.md#ioctl)

输入头+payload 一次复制到有界内核快照，再解析；用户之后改写缓冲区不会改变待执行内容。指针检查和 copy 不能在 IRQ/spinlock 内发生。不论之前探测了输出地址，copyout 仍可能失败。

transport 系统调用失败分类：未知 ioctl 为 ENOTTY；无效长度/保留位为 EINVAL；不支持的协议为 EPROTONOSUPPORT；拷贝失败 EFAULT。语义拒绝在一个有效 HOSR 响应内返回 status。输出容量小于已知结果尺寸时在效果准入前拒绝 EMSGSIZE。**效果已发生后的 EFAULT 不保证零效果**；按原 request_id 重取结果，不新建操作身份。

## 4. 请求头：64 字节逐字段 little-endian

| offset | 字段 | 长度/约束 |
| --- | --- | --- |
| 0 | magic | 4，ASCII HOS1 |
| 4 / 6 | major / minor | u16 / u16，1 / 0 |
| 8 / 10 | opcode / flags | u16 / u16，flags=0 |
| 12 / 16 | header_len / payload_len | u32 / u32，64 / 实际长度 |
| 20 | reserved0 | u32=0 |
| 24 | request_id | 16 字节，不全零，仅关联与投递去重，不是权限 |
| 40 / 48 | target_slot / target_generation | u64 / u64；QueryAbi 两者为零；其他两者均非零 |
| 56 | reserved1 | u64=0 |

总 frame 恰好等于 64+payload_len；不接受尾随数据、非零 reserved、未知 opcode/flags/minor。最大 payload 65536 字节，最大 frame 65600；当前三种消息远小于此值。所有算术受检，禁止以 Rust struct padding 或 enum 内存布局代替 wire。ID 字节按原样保留，不作整数端序转换。

## 5. 响应头：64 字节逐字段 little-endian

| offset | 字段 | 长度/约束 |
| --- | --- | --- |
| 0 | magic | 4，ASCII HOSR |
| 4 / 6 | major / minor | u16 / u16，1 / 0 |
| 8 / 10 | opcode / status | u16 / u16 |
| 12 / 16 / 20 | header_len / payload_len / reserved | u32 / u32 / u32，64 / 实际长度 / 0 |
| 24 | request_id | 16，回显原请求且非零 |
| 40 | boot_id | 16，非零，来自内核而非调用者 |
| 56 | revision | u64；QueryAbi 为 0；成功 ReadUsage/InstallBudget 为实际非零资源 revision |

status 数值：0 ok；1 invalid_input；2 permission_denied；3 stale_handle；4 revoked；5 conflict；6 resource_exhausted；7 unsupported；8 indeterminate；9 busy。非零 status 的 payload 为空、revision=0，避免泄露域外状态；需读取当前 revision 的授权调用者另发 ReadUsage。unknown enum 值拒绝，不将未认识状态当成 ok。

客户端还要核对 opcode、request_id、已知 boot_id 与会话；编解码器只检查格式，不能验证来源可信。所有输出字节初始化，包括保留位。

## 6. 三个操作的完整布局

| opcode | 输入 | 成功输出 payload | 能力与效果 |
| --- | --- | --- | --- |
| 1 QueryAbi | 空，target=0 | 48 字节，见下 | 合法绑定会话；无副作用 |
| 2 ReadUsage | 空，target=资源域 | 64 字节，见下 | resource.observe；读取一个一致快照，无管理权 |
| 3 InstallBudget | 32 字节，见下 | 24 字节，见下 | resource.manage；CAS 安装，纳入投递去重 |

QueryAbi 输出 offset 0 CapSpace ID[16]（非零，内核生成），16 page_size:u32（非零二次幂），20 max_payload:u32，24 max_response_payload:u32（均不超过65536），28 reserved:u32=0，32 supported_ops:u64（bit1/2/3 对应当前三项），40 features:u64=0。它是报告能力，不授予能力；内核仅宣告已真实实现的子集。未知 feature 必须协商，不偷偷忽略。初期最小响应尺寸限制是当前支持集所需尺寸。

ReadUsage 输出八个 u64：sample_boottime_ns、cumulative_cpu_ns、window_start_ns、window_consumed_ns、charged_memory_bytes、memory_limit_bytes、event_sequence、dropped_events。响应头 revision 与这八项来自同一版本/序列快照；不能混拼不同预算版本。丢事件后做快照恢复，不推断没有效果。

InstallBudget 输入四个 u64：expected_revision、period_ns、cap_ns、reserved=0。expected_revision 必须非零且不能溢出递增；首期 period_ns 固定100000000（100ms），单CPU cap_ns∈[0,period_ns]，cap=0 表示本域暂停可运行时间，但恢复服务不在该域。没有 priority、affinity、weight 或 deadline 隐含字段。

InstallBudget 输出三个 u64：previous_revision、effective_boottime_ns、consumed_at_apply_ns；响应头 revision=previous_revision+1。相同投递重取原结果，不递增第二次。返回的是已安装 cap，而非最低资源保证；降低 cap 无法撤回已消耗时间。

## 7. 准入、撤销与 copyout

内核解析已复制快照，解析对象并取得强引用后释放 CapSpace 表锁；然后进入资源域的短 mutation 锁。**在同一临界区**检查当前调用身份、能力 generation、撤销/期限、目标范围、expected_revision、去重记录与结果容量，登记准入，并提交预算 revision/结果。该提交是 InstallBudget 的线性化点。先确保结果槽和计数递增可成功，失败不得产生半次效果。

revoke 在同一对象 mutation 锁递增 grant epoch 并关闭以后准入。L_revoke 先于 L_admit 则拒绝；L_admit 先于 L_revoke 则效果已准入，后续撤销处理在途状态，不抹除历史。撤销 ACK 只证明以后准入关闭，**不证明所有硬件已排空**。设备路线另有 admitted、issued、quiesced；已准入未 issued 可以尝试停止，但不能声称所有撤销后物理提交均不存在。

语义授权由 Hepta owner 对不可变操作内容产生，桥将相同 canonical bytes 及目标绑定提交。桥为受信任效果适配器、拥有受限 envelope，不是无权限的字符串转发器；受损桥仍可能在 envelope 内违规，这是明确 TCB 风险。内核不凭调用者自报 digest 授权；需要逐 payload 强隔离时由可信 issuer 预置一次性 payload-bound ticket，后续专门接口验收，不能宣称当前三操作已提供该功能。

## 8. 两级操作身份与去重

持久逻辑键 K=(authenticated_principal,workspace_id,operation_id)。原 Hepta 操作 owner 存 {intent_digest,opcode,稳定目标身份,效果状态,投递尝试[]}；**摘要不在查找键中**。先按 K 查找，再比较 canonical 内容/摘要：相同返回既有状态；不同冲突。跨 boot、桥重启、PID 重用仍是同一 K；不能换 boot_id 或 request_id 绕过未决操作。

内核投递键 D=(boot_id,CapSpace_id,request_id)，记录完整已复制请求字节和结果。相同 D 不同字节为 conflict；相同 D 已有结果只重取、不新执行；原准入仍未决则 indeterminate。D 查找先于 revision CAS，否则丢响应后的合法重试会被误判成 CAS 冲突。历史重取要求 observe 授权，不要求重新取得已撤销的 execute 权限，也不得产生新效果。

每个 CapSpace 首期最多保留1024条写投递记录，满时拒绝新写并保留旧结果；不静默 LRU 淘汰、到期清空或把 missing 当零效果。CapSpace 退出后瞬时表可释放，原 Hepta 持久 owner 必须保留未决 K，换进程后只查询/核对。查不到内核记录不授予重放权。持久未决记录保留小型 tombstone/身份，停止新准入可释放 GPU/CPU 会话但不能抹去效果不确定性。身份保留到能证明不会重放的 owner 规则，禁止为腾空间任意删除后重用 ID。

## 9. CPU 与内存记账

CPU 是累计运行时间上限，不是保底、权重或 deadline。首期固定 P=100ms、周期起点=本次启动的固定调度时间原点；使用 CLOCK_BOOTTIME 等价单调时钟定义窗口。U 为该域所有线程在当前窗口已运行时间之和。InstallBudget 立即改变 cap，但保留 U、原点和所有祖先计费；剩余额度 max(0,cap-U)。降低到 U 以下仅阻止后续运行，历史使用不回写。每个真实周期边界才重置窗口计数；同值更新也不充值。

每次运行同时扣本域及所有祖先额度，祖先耗尽即暂停后代；兄弟 cap 之和可超过父 cap，只要父总量真实执行。首期单 CPU，不提供迁移、period/CPU集变更或最小预留；这些请求明确 unsupported，不能静默绕过。未来多 CPU 必须先预留全路径额度再运行，以受界量子核对实际用量；超支上界与计费误差必须测量并报告，不宣称零误差。动态迁移需要保留原域历史计费、新域后续计费和稳定工作区祖先约束，不能通过循环迁移领取新 quota；未完成此机制不启用迁移。

内存目标规则：每个物理页/内核分配有稳定 charge_owner，祖先聚合；匿名页初次分配与 COW 新页向分配方计费；共享页、文件缓存页按第一次实际分配者计一次，其他映射另计页表/映射元数据。共享不擦除 owner，owner 退出但共享仍存活时账留存到最终释放。sockets/内核队列按创建方计费；固定 DMA 页仍计内存并另外占 pinned 子限额，两者不是总量重复收费。未授权跨域共享先拒绝，不因共享带来隐式赠予。

首期 ReadUsage 可以报告现有计数，但内存限额写接口不属于本版。未来降硬限额低于实际使用必须 rejected 或进入显式 reclaiming；未回收不得报已满足；不可强行回收设备仍用页。reparent/迁移及 charge transfer 要在旧/新祖先共同受限临界区验证，首期不支持。

## 10. 对象关闭、取消和后续设备路线

M0 资源域由 init 创建并在任务启动前归属；控制会话靠 close/进程退出释放，资源域靠 supervisor 在任务和子引用退出后销毁。动态 Create/Destroy/Transfer 不提供 wire 编号。对象强引用保证并发关闭不会造成 use-after-free，但强引用不延长已撤销的操作权限。

设备路线未来分别记录 execution={not_issued,in_flight,quiesced,completed}、cancel={none,requested,acknowledged}、effect={none,partial,complete,unknown}、observation={authoritative,missing}。硬件停止只证明未来不继续；8192字节写入在4096后停止应是 quiesced+partial，不是 none。通用“cancelled=零效果”被废止。不是所有设备都以字节衡量效果，设备契约给出适用计数/观察者。

页可回收条件是有独立的 quiescence/隔离证明且无活跃CPU引用；effect=unknown 并不必然永久保留页，反之请求超时也不允许释放 DMA 页。未能确认静止时保持隔离/有界 quarantine，拒绝后续危险共享而非无限分配。

## 11. 验证边界

codec 只验证格式；宿主规格模型验证选定反例；真实并发、调度、credential、copyout 和 DMA 需在内核接合后测。测试入口与 F02–F07 映射见 [VALIDATION](VALIDATION.md)。
