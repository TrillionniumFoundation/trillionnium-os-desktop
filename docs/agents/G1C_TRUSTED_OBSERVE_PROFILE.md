# G1-c：受信初始静态映像的观察切片

本实验把真实初始 ELF 装载、唯一首次运行令牌、实际 `ProcessImageState` 与既有 CPU 带宽 owner 接在一起。默认构建仍只实现 `QueryAbi`；显式 `g1c-trusted-observe` 构建在所有进程中统一声明 `QueryAbi | ReadUsage`，只有经受信初始事务激活的原进程映像持有观察槽位。

本文件记录实现契约。是否已通过真实 guest，以候选源码绑定的 A06 原始输出及独立复核结果为准；新增源码或 ktest 名单本身不代表真实内核已通过。

## 构建输入与启动选择

使用项目已有云环境、固定 Rust 工具链和构建入口：

```sh
HEPTA_G1C_TRUSTED_OBSERVE=1 \
HEPTA_TRUSTED_INITIAL_ELF=/absolute/path/to/reviewed/g1c-init \
A01_RUN_DIR=/absolute/path/to/new-build-output \
support/build/kernel.sh kernel
```

`prepare-trusted-image.py` 有界读取已审查的静态 ELF，在新的输出目录中创建只读 `trusted-initial.elf` 和带字节数、SHA-256、固定策略的 `trusted-initial-manifest.json`。内核的 `include_bytes!` 实际指向这份副本。SHA-256 用于构建证据绑定，运行时授权比较的是内核嵌入字节与实际打开输入的一次快照；不接受调用者提交的 hash、路径或 UID 作为信任证明。

`minimal.mk` 会覆盖上游 `CARGO_OSDK_BUILD_ARGS`，因此本实验在该最终覆盖点显式加入 feature，不能仅依赖上游 `FEATURES`。不引入新包、版本、工具链或 lock 变更。两处 Cargo feature 声明由 `verify-source.py` 从固定上游 blob 精确派生，其他清单字节继续受原检查保护。

实验构建仅支持 `kernel` 目标。普通 `run_kernel` 保留原启动 gate；专用 guest runner 使用相同内核单独启动有受信 ELF 的 initramfs。选取初始文件沿用现有 `rdinit=/test/g1c-init`，后续参数沿用 OSDK `init_args`。这个路径只定位文件，不产生权限。

篡改负控必须复用同一内核及嵌入 ELF，只改变另一次启动的 initramfs 输入。输入不匹配明确拒绝启动，不降级到一个继续运行的“受信”事务。精确诊断为：

```text
[hepta-g1c] rejected initial image: manifest-byte-mismatch
[hepta-g1c] rejected initial image: truncated-snapshot
```

不得以任意 panic、超时或缺少用户日志作为负控通过。必须核对具体拒绝原因，且没有映像提交、观察槽激活或 guest 开始运行记录。

## 映像身份与封存

受信入口只在 `create_init_task` 的实验初始装载路径调用。普通 Linux `execve` 继续使用一般 ELF/shebang 装载器，包括执行同一个受信 ELF 文件时。

实验 profile 限定 x86_64、小端、静态 `ET_EXEC`，文件最多 8 MiB，最多 64 个 program headers、16 个 LOAD segments、总 LOAD 映射最多 16 MiB。拒绝 shebang、`PT_INTERP`、`ET_DYN`、不可读 LOAD、W+X、重叠的页对齐 LOAD 范围，以及不在可执行 LOAD 内的 entry。

装载器先按内核嵌入文件长度完成一次有界快照，并检查 EOF；同一份字节用于解析和初始化无文件 backend、无用户导出句柄的私有 RAM VMO。BSS 和页尾清零。所有 ELF、vDSO、启动页、栈及堆映射完成后，再回读最终 ELF 和启动页字节、检查实际权限，然后封存 VMAR，返回无公开构造器、不可 Clone 的 `LoadedInitialImage`。后续缺页不再从原 ELF 文件重读。

`PreparedInitialProcess` 消费该 token，验证原 Process、VMAR、唯一主 task 和 image key，再激活槽位，最后消费原 first-run claim 并 Resume。当前实现不以 PID 1、root、文件名、文件元数据或可伪造摘要代替这个事务。

封存信息是原 `VmarInner` 内的映射限制，不是第二份 grant liveness。其生命周期持续到旧 VMAR 被销毁：

| 路径 | 封存后行为 |
| --- | --- |
| 对映像或启动页做 `MAP_FIXED` 替换、`munmap`、`MADV_DONTNEED` | EPERM，先检查后修改 |
| 给原映像加权限，或给其他映射增加执行权限 | EPERM |
| 新建可执行映射 | EPERM |
| 降低映像权限，例如静态 libc 的 RELRO | 允许；不能再增加回来 |
| `mremap` / resize alias | 本实验 VMAR 全部拒绝 |
| 通过已打开或已传递的 proc-mem fd 写入 | `write_alien` 使用时再次拒绝；现有 procfs 将零字节失败映射为 EIO |
| 跨进程 attach 级 alien access | EPERM；现有 proc-mem open 对外映射为 EACCES |
| 跨 Process 的 `CLONE_VM` / vfork | EPERM |
| 普通 fork | 独立 COW VMAR；不继承 seal 或观察授权 |
| 同一 Process 的线程 | 共享原 Process/CapSpace；仍受同一 VMAR 限制 |

vDSO 的可执行映射也纳入封存。vDSO 数据继续由内核维护；不把动态数据伪称为固定 ELF 字节。

## CapSpace、CPU owner 与锁

唯一观察槽存在于实际 `ProcessImageState` 中，固定 slot=1、generation=1，不提供公开创建、复制或转授权 API。句柄发现页不包含权限凭证。`begin_close`、失败替换和成功 exec 都关闭旧映像的准入；新 exec 映像没有观察槽。普通 fork、新开 fd、dup 或 SCM_RIGHTS 都不会创建权限。

初始 CPU leaf 使用原 cgroup 树、原 `SubController<CpuController>` 和原 `CpuBandwidthState`，初始配置为 50,000,000 ns / 100,000,000 ns。`NativeResourceState`、revision、累计用量和窗口用量仍在原带宽锁保护下，不新增调度器、CPU 计数器或投递账本。只读 adapter 保留原 owner 的 Arc 和 target 身份；更换或删除该 owner 后，旧 pin 不能读取一个新 incarnation。

观察租期从 bootstrap 的真实 BOOTTIME 签发点起固定 300,000,000,000 ns。签发时刻可用，到期时刻不可用；出现早于签发点的采样报告不确定性。

锁序保持：

1. 初始 Process/token 核对采用既有 VMAR mutex → TaskSet mutex → image mutex；不在 image mutex 内进入 cgroup 或调度器。
2. 初始 CPU 绑定沿用 membership → 本 CPU runqueue/原带宽锁路径。固定配置走原 `reconfigure_at`，没有通过格式化 `cpu.max` 字符串实现另一路原生更新。
3. ReadUsage 先在 image mutex 内解析真实槽并取得只读 owner pin，释放锁，再由 `with_current_cpu_bandwidth_settled` 结算实际当前运行量；在同一 BOOTTIME cut 上先检查租期，过期或回退时不进入 owner 样本读取，再采样。
4. 返回前再在 image mutex 内核对同一 image key、槽、owner pin 和租期。该 image key 不可关闭后复活，因此只读样本具有合法线性化点；并发 exec/exit 导致拒绝。
5. 用户 copyin/copyout、ELF 文件 I/O、页面验证均不在 IRQ/runqueue/CPU 带宽锁内执行。

## 启动发现页及 HOS2

HOS2/HOSR 编码、实验 ioctl `0xC0204802` 和 32-byte transport 保持 [NATIVE_ABI](../NATIVE_ABI.md) 的定义。实验新编译内核统一报告 supported_ops=6、max_request_payload=0、max_response_payload=64、features=0。management/history 三个操作继续 EOPNOTSUPP，不宣称 Hepta 写入或历史闭合。

仅实验初始装载设置 `AT_HEPTA_BOOT=240`，指向 VMAR 普通空闲地址分配所得的只读、非执行页。开头 32 字节是：

| 偏移 | 内容 |
| --- | --- |
| 0..8 | ASCII `HOS2BOOT` |
| 8..16 | version=1，u64 little-endian |
| 16..24 | observe slot=1，u64 little-endian |
| 24..32 | generation=1，u64 little-endian |
| 32..4096 | 全零 |

普通 exec 没有此 auxv 项。复制或篡改用户发现页不改变内核授权。

ReadUsage 成功返回原 owner 的 revision 和八个标准 u64。无观察槽返回 HOSR permission_denied(2)；已有槽但非零 slot/generation 不匹配返回 stale_handle(3)；资源关闭或租期到期返回 revoked(4)；时钟、profile 或计量无法给出可信样本返回 indeterminate(8)。非零 status 的 revision=0、payload 为空。旧映像 fd 沿用 ESTALE，异进程使用同一 fd 沿用 EPERM。

本切片保留既有 Linux cgroup 管理接口。legacy root 仍可配置或迁移资源，因此这里不宣称对 legacy root 的完整管理隔离。成功的同值 `cpu.max` 写也推进原 revision，不清空原计量；25/50 ms 的配置变化与原生读取必须落在同一 owner。`cpu.stat` 的 jiffies 计数不等同于原生纳秒累计，不可用伪精确等式替代实际 owner 关联验证。

## 验收范围

新增九个默认 ktest 覆盖封存后的替换/减权边界、预先持有 VMAR pin 的写入拒绝、fork COW 隔离、真实 CPU owner 替换与删除、观察租期两端边界，以及 owner 采样前拒绝过期/回退 cut。原 full-core checker 保留全部旧断言，要求至少 247 项且九个新测试名各出现一次；历史 238 项成功输出不能满足当前 gate。它们使用原 VMAR/CPU 对象，但不替代普通用户态 syscall 执行。

专用真实 guest 必须证明：初始真实授权成功、无权 fork/SCM/伪启动页、已打开 proc-mem fd 的使用时拒绝、同 Process thread/dup 的预期共享、同一个已授权 PID 最终 exec 后旧 fd 和新槽都不能继续使用，以及同内核的篡改 initramfs 确切拒绝。原普通 Linux、权限、SCM_RIGHTS、NOFILE 和 CPU gates 保留。

封存可执行映像解决的是本实验的启动身份和后续代码替换路径。它不证明任意 AI 运行时没有内存安全缺陷、任意设备可安全 DMA，或完整 Hepta resource.manage/history 链已经实现。
