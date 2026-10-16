# 原生 ABI 与对象契约

版本：0.1。状态：设计草案，尚无实现、已分配 syscall 编号或稳定发布 ABI。

## 1. 设计目标

为 Hepta 和原生应用提供明确的资源、能力和设备接口。内核不接受模型自然语言，不在 ABI 中交换 Rust 内存布局、trait object、裸引用或进程地址。所有编解码有独立的 no_std 测试目标。

第一版保留一个版本化的 control 入口；供 Linux ELF 使用的 `/dev/hepta-control` ioctl 适配和未来原生 syscall 入口复用同一解析器及权限检查。实际设备号、ioctl 编号和 syscall 编号在实现时分配，本文不占用 Linux 既有编号。Linux 宿主上的 mock/UDS 后端只能用于客户端测试，不能算新内核调用证据。

## 2. 内核对象

`TaskHandle`、`ResourceDomainHandle`、`MemoryHandle`、`DeviceHandle`、`QueueHandle` 和 `OperationHandle` 都是调用进程能力表内的槽位与代际，不是任意地址或可跨进程直接复制的权限。内核校验实际调用身份、对象类型、generation、rights、所属域和撤销 epoch。

句柄的不可伪造性来自内核拥有的映射和访问检查，不来自字段名、哈希或请求者声称已授权。关闭或复用槽位必须改变代际；代际溢出时退役该槽位，不循环使用。跨进程传递创建新的接收端条目，权限只减不增。

原生能力默认不经 fork/exec 继承；确需继承时必须显式声明。普通 Linux fd 的继承语义由兼容层保持，不能为方便实现而改变所有 fd 行为。设备能力跨 exec 必须重新检查映像与授权范围。

## 3. 请求头草案

V1 使用固定 **64 字节**小端请求头，逐字段解析，禁止依赖 Rust struct 的隐含 padding。

| 字段 | 字节 | 规则 |
| --- | --- | --- |
| magic | 4 | ASCII HOS1 |
| abi_major / abi_minor | 2 + 2 | major 不兼容拒绝；minor 仅允许已协商扩展 |
| opcode / flags | 2 + 2 | 未知关键标志拒绝 |
| header_len | 4 | V1 固定 64 |
| payload_len | 4 | 与实际缓冲区长度一致 |
| reserved0 | 4 | 必须为 0 |
| request_id | 16 | 调用关联；不是授权或全局唯一性的证明 |
| target_slot | 8 | 当前调用进程中的能力槽位 |
| target_generation | 8 | 与该槽位当前代际一致 |
| reserved1 | 8 | 必须为 0 |

初始试验上限：单个控制 payload 不超过 64 KiB，单次句柄转交不超过 16 个；这两个值是待实现的防放大设计参数，不是已测吞吐。实际数据面通过另行注册的内存对象与队列处理，不把大模型张量放入控制报文。

内核必须检查长度加法溢出、对齐、地址范围、对象类型和所有保留字段；复制完整控制描述符至内核后再授权及执行。不能校验用户态缓冲区后再重新读取可被修改的命令，从而留下 TOCTOU。

## 4. V0.1 操作集合

| 操作 | 必需权限 | 效果 |
| --- | --- | --- |
| QueryAbi | 已打开的受限控制端点 | 返回版本、支持操作与明确上限 |
| ReadUsage | resource.observe | 返回所属任务的有界计数与采样时间 |
| CreateResourceDomain | resource.delegate | 创建不超过父域上限的子域 |
| InstallBudget | resource.manage | 校验后原子安装预算版本 |
| RevokeDelegation | authority.revoke | 阻止后续授权使用，启动必要排空 |
| RegisterBuffer | memory.device_share | 固定合法页并绑定方向和设备 |
| SubmitIo | device.submit | 在已授权队列提交受控 I/O |
| QueryOperation | operation.observe | 返回真实已知状态，保留 unknown |
| CancelOperation | operation.cancel | 请求取消，不保证已发出操作可逆 |

启动器创建 Task 时配置 ResourceDomain，避免进程在纳入限额前先耗尽资源。跨域迁移在明确的调度同步点更新归属；迁移失败保留原归属，不能出现同时计费或不计费窗口。

## 5. 资源预算语义

CPU 初期使用 budget_us、period_us、允许 CPU 集合与优先级等级。预算是该域所有线程累计运行时间的上限，不是每个线程独立获得一份预算；验证 budget_us 与 CPU 数、period_us 的乘积时必须检查溢出。

InstallBudget 比较 expected_revision，成功只产生一个新 revision。并发安装只能有一个匹配旧版本；其余返回 conflict。旧授权不能扩大新版本上限。预算请求不得侵占预先保留的恢复/内核资源。

该接口最初只承诺有界份额，不承诺硬实时 deadline。多个预留任务的可调度性需独立 admission 分析；不能仅因每个预算独立合法就认定整体可调度。

内存使用软回收阈值与硬上限。降低上限时显式返回 applied、reclaiming 或 rejected，不能在内存尚未回收时报告完全生效。不可回收 DMA 页与共享页的计费规则必须明确，防止通过共享逃避限额。

## 6. 设备数据面

RegisterBuffer 绑定内存对象、长度、读写方向、设备、队列和 epoch。描述符使用句柄及 offset/length，不接受任意物理地址。DMA 必须限制在相应 IOMMU 映射中；缺少隔离的设备不得被当作强隔离多租户设备共享。[参考](SOURCES.md#vfio)

队列所有者校验 producer/consumer 索引、环长度和每个范围。复位后递增 queue generation，旧 completion 不能完成新操作。控制描述符以提交时的不可变副本为准；数据缓冲区允许怎样并发访问由操作方向明确规定。

## 7. 完成、取消与撤销

```text
created -> validated -> submitted -> completed / failed
                         |               |
                         +-> cancel_requested -> cancelled / completed / unknown
```

只有确认未提交或硬件已停止，才可报告 cancelled。撤销阻止新提交，不会让已写入磁盘的数据自动撤回。回收 DMA 内存前必须确认完成、排空或可信的设备复位；超时不能直接释放仍被设备使用的页。

去重键绑定调用身份、boot identity、操作 ID 和最终内容摘要。相同键不同内容必须冲突；查询缺失结果返回 unknown，不能推断零效果。去重与 journal 不提供对任意外部设备的普遍 exactly-once 保证。

## 8. 错误与可观测性

明确区分 unsupported_version、unsupported_operation、invalid_input、permission_denied、stale_handle、revoked、conflict、resource_exhausted、would_block、timed_out、device_lost 和 indeterminate。Linux 适配器按各操作契约映射 errno，不把所有失败压缩成 EIO。

返回 boot identity、request_id、对象代际、策略 revision、已知状态和有界统计。权限、秘钥和用户数据不进入一般事件流。事件流有序号与丢失计数，溢出后由当前状态查询恢复，不能把丢事件当成“没有发生”。

## 9. 首批测试

编解码 round-trip、64 字节布局、所有截断长度、超长请求、整数溢出、未知标志、伪句柄、关闭后复用、fork/exec 泄漏、并发预算 CAS、跨域资源逃逸、控制缓冲区变化、重复操作、旧队列 completion、撤销后提交和 DMA 排空。所有测试现在均为计划项。
