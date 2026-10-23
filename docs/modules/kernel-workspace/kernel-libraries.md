# 内核通用库（20 crate）

源码基线 `10dae5ea4ae5c2f81e2e530b1eb74bd41a5c29cd`。阅读前先看 [范围、共同开发流程与证据规则](README.md)。下列“待验证”是具体后续门禁，不是已完成声明。

## aster-bigtcp

[manifest](../../../kernel/asterinas/kernel/libs/aster-bigtcp/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/aster-bigtcp/src/lib.rs) · [socket_table.rs](../../../kernel/asterinas/kernel/libs/aster-bigtcp/src/socket_table.rs) · [iface/iface.rs](../../../kernel/asterinas/kernel/libs/aster-bigtcp/src/iface/iface.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 封装 smoltcp TCP，重组 Ethernet/IP 分派、interface、socket 与 socket table，以支持通用 OS 的更多 socket。

**状态、所有权与失败边界。** 接口、socket table 和 socket 状态是协议栈 owner；设备 I/O 通过 device 层接入，时间由适配接口供给。协议状态正确性不等于进程权限或跨租户网络隔离。

**开发与回归。** 修改分派/端口复用/重传时同时检查 iface、socket_table 与 TCP 状态，验证包边界、超时、连接关闭和资源回收。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 现有源码测试声明不能证明 TCP 互通、拥塞性能或恶意包压力；需真实网络 namespace/进程上下文中的 Linux API 和网络故障测试。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=7`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-fuse

[manifest](../../../kernel/asterinas/kernel/libs/aster-fuse/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/aster-fuse/src/lib.rs) · [operation.rs](../../../kernel/asterinas/kernel/libs/aster-fuse/src/operation.rs) · [header.rs](../../../kernel/asterinas/kernel/libs/aster-fuse/src/header.rs) · [error.rs](../../../kernel/asterinas/kernel/libs/aster-fuse/src/error.rs)。既有文档：[README.md](../../../kernel/asterinas/kernel/libs/aster-fuse/README.md)。

**职责与接口。** FUSE 7.38 的传输无关 request/reply header、opcode、flags 和类型化 FuseOperation 编解码定义。

**状态、所有权与失败边界。** 仅拥有 wire 类型与编码/解码验证；连接、请求 ID 生命周期、daemon 信任和实际文件权限归 transport/调用方。POD 结构不自动证明未信任 reply 有效。

**开发与回归。** 新增 operation 同步请求、回复、长度、对齐和错误码；检查 short reply、未知 flag、变长数据与版本协商。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需真实 virtio-fs/FUSE server 互通及坏 reply 的端到端拒绝；协议定义不能证明挂载或持久性。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-rights

[manifest](../../../kernel/asterinas/kernel/libs/aster-rights/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/aster-rights/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 定义动态 `Rights` 位集合和 `TRights`/`TRightSet` 类型级读写执行/复制/信号权利。

**状态、所有权与失败边界。** 本 crate 只描述权利；注释明确具体语义由 capability 设计者决定。类型集合不存主体、有效期、撤销或 Hepta grant，也不自动约束所有 syscall。

**开发与回归。** 新增权利要同步动态 bit 与类型宏，追踪每个消费者的检查位置；同时补允许/拒绝的编译期例子和动态降权测试。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p aster-rights`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需要调用链级 capability 不可扩权/撤销验证；不能凭 Full/Write 类型名声称生产授权已闭合。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-rights-proc

[manifest](../../../kernel/asterinas/kernel/libs/aster-rights-proc/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/aster-rights-proc/src/lib.rs) · [require_attr.rs](../../../kernel/asterinas/kernel/libs/aster-rights-proc/src/require_attr.rs) · [require_item.rs](../../../kernel/asterinas/kernel/libs/aster-rights-proc/src/require_item.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** `#[require]` 将类型级包含/包含集合约束注入函数，支持多个约束；依赖 typeflags/typeflags-util。

**状态、所有权与失败边界。** 宏只控制编译生成的 trait bound，不拥有运行时资源或 grant；必须审查泛型参数、where 子句及多个约束是否保留。

**开发与回归。** 新增语法同时扩展 require_attr/require_item 的解析与展开，补 compile-pass/compile-fail 示例；宿主宏测试成功仍需消费者编译。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p aster-rights-proc`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 尚需所有实际 capability 调用者的负编译测试与动态权利一致性；宏不验证用户身份。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-util

[manifest](../../../kernel/asterinas/kernel/libs/aster-util/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/aster-util/src/lib.rs) · [safe_ptr.rs](../../../kernel/asterinas/kernel/libs/aster-util/src/safe_ptr.rs) · [mem_obj_slice.rs](../../../kernel/asterinas/kernel/libs/aster-util/src/mem_obj_slice.rs) · [per_cpu_counter.rs](../../../kernel/asterinas/kernel/libs/aster-util/src/per_cpu_counter.rs) · [slot_vec.rs](../../../kernel/asterinas/kernel/libs/aster-util/src/slot_vec.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 内核实用类型集：FixedPoint/系数、FixedStr、MemObjSlice、SafePtr、PerCpuCounter、SlotVec 等。

**状态、所有权与失败边界。** 没有统一资源 owner；各子模块对借用、范围、引用或 per-CPU 聚合有独立合同。安全指针也不赋予访问对象的业务权限。

**开发与回归。** 按改动的子模块维护边界/溢出/容量/并发测试，修改 SafePtr 或 Slice 时追踪 VM I/O 的底层错误传播；不要因工具库名统一放宽行为。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需要逐消费者验证：计数器汇总不等于原子账目快照，容器容量/分配失败不等于恢复 reserve。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=11`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## atomic-integer-wrapper

[manifest](../../../kernel/asterinas/kernel/libs/atomic-integer-wrapper/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/atomic-integer-wrapper/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 过程宏为可转换为整数的类型生成对应 atomic wrapper。

**状态、所有权与失败边界。** 底层 Atomic 整数拥有状态；转换失败和内存序语义取决于生成代码与调用者，枚举包装不自动形成合法状态机。

**开发与回归。** 新增支持类型时核对 Into/From/TryFrom 转换、compare_exchange 返回值及 Ordering 传递；补非法整数和泛型/可见性编译例子。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p atomic-integer-wrapper`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 仍需各状态机的竞争/发布顺序测试；宏生成成功不能证明跨线程生命周期正确。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## cpio-decoder

[manifest](../../../kernel/asterinas/kernel/libs/cpio-decoder/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/cpio-decoder/src/lib.rs) · [error.rs](../../../kernel/asterinas/kernel/libs/cpio-decoder/src/error.rs) · [test.rs](../../../kernel/asterinas/kernel/libs/cpio-decoder/src/test.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 安全 Rust 的 newc CPIO decoder，通过 LendingIterator 逐条借用读取 archive。

**状态、所有权与失败边界。** decoder 拥有 reader 位置；CpioEntry 借用同一 decoder，当前条目内容与 padding 的消费影响下一条。解析成功不负责将路径安全地安装到根文件系统。

**开发与回归。** 改 header/文件类型解析时覆盖截短、非法 hex、对齐、尾标记和大长度；安装方需另查路径穿越、symlink 与权限。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p cpio-decoder`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需坏 initramfs 和真实启动回归；archive 格式测试不等于解包后的文件权限或可信映像证明。 当前 `src/**/*.rs` 的静态测试属性声明：`test=5`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## device-id

[manifest](../../../kernel/asterinas/kernel/libs/device-id/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/device-id/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** Linux major/minor 设备号的封装和 u64 编码/解码，使用范围受限的 MajorId/MinorId。

**状态、所有权与失败边界。** DeviceId 是值类型；实际编号唯一性和注册回收归设备模型/driver，编码本身不分配设备或授予访问权。

**开发与回归。** 变更布局要对照现有 mknod/stat ABI，覆盖最大编号、跨高低位和 round-trip；禁止只改编码而遗漏消费者。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需真实用户态节点/stat 互通；没有证明所有 driver 的设备号分配都不冲突。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## dma-pool

[manifest](../../../kernel/asterinas/kernel/libs/dma-pool/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/dma-pool/src/lib.rs) · [arena.rs](../../../kernel/asterinas/kernel/libs/dma-pool/src/arena.rs) · [buffer.rs](../../../kernel/asterinas/kernel/libs/dma-pool/src/buffer.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 按固定小块分配 streaming DMA segment，提供 DmaPool、DmaSegment、DmaArena/Pool 与 DmaBuffer。

**状态、所有权与失败边界。** DmaSegment Drop 归还池；源码要求 pool 活得更久，否则 segment Drop 会 panic。方向、coherence、同步和 device 完成顺序须由调用方遵守，通常使 pool 为静态寿命。

**开发与回归。** 变更水位/回收/arena 时覆盖空池扩容、最后 segment 归还及持有未完成 DMA 的 teardown；跨 CPU 同时检查 BottomHalfDisabled 锁。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需实体非一致性 DMA 和 IOMMU 测试；内存分配正常不证明设备已停止访问，不构成恢复专用预留池。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=8`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## fdt-util

[manifest](../../../kernel/asterinas/kernel/libs/fdt-util/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/fdt-util/src/lib.rs) · [io_mem.rs](../../../kernel/asterinas/kernel/libs/fdt-util/src/io_mem.rs) · [irq_line.rs](../../../kernel/asterinas/kernel/libs/fdt-util/src/irq_line.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 扩展 FdtNode，获取设备描述的 IoMem 和部分架构 IRQ line。

**状态、所有权与失败边界。** 只在 riscv64/loongarch64/aarch64 编译主体；IRQ 扩展限 RISC-V/ARM。IoMem/IrqLine 资源经 OSTD 取得，设备树描述不自动可信。

**开发与回归。** 更改 reg/interrupt 解析时覆盖父地址/大小 cell、区间溢出、缺属性与架构 IRQ 编码，使用对应目标的 build/boot。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** x86 默认测试不能覆盖该 crate 实现；仍需真实板级 DTB、MMIO 冲突和 IRQ 接线验证。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## io-util

[manifest](../../../kernel/asterinas/kernel/libs/io-util/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/io-util/src/lib.rs) · [batch.rs](../../../kernel/asterinas/kernel/libs/io-util/src/batch.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** IoError 和异步 `IoCompletion`/`IoBatch`，支持收集 completion 后 wait_all。

**状态、所有权与失败边界。** completion Arc 通常由 submitter 与 driver 同持；IoBatch 只记录对象，不跟踪 readiness，len 不是剩余未完成数。底层 wait 的终止与错误语义归实现。

**开发与回归。** 修改 batch 时覆盖空批、混合同步/异步、多个错误和重复等待；确保调用方只为真正异步操作插入记录。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需要底层设备故障/取消时 wait 不永久阻塞的实际测试；此抽象自身不提供超时或持久化保证。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## jhash

[manifest](../../../kernel/asterinas/kernel/libs/jhash/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/jhash/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 实现 Linux 变体 Jenkins 32-bit hash，提供字节 slice、u32 数组及 1/2/3 值接口。

**状态、所有权与失败边界。** 纯函数无共享状态；initval 由调用方提供。该 hash 用于查表，不能作为密码学身份、完整性、capability 或证据签名。

**开发与回归。** 改混合/尾部代码必须保留长度与字节序语义，用已知向量及各种余数长度对照原结果。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p jhash`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需调用方的抗哈希洪泛策略和实际分布性能；本库测试不证明网络输入 DoS 防护。 当前 `src/**/*.rs` 的静态测试属性声明：`test=5`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## keyable-arc

[manifest](../../../kernel/asterinas/kernel/libs/keyable-arc/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/keyable-arc/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** KeyableArc/KeyableWeak 将 Arc/Weak 引用按对象身份用于集合 key。

**状态、所有权与失败边界。** 共享引用拥有对象生命周期，Weak 不延长对象寿命；集合语义是引用身份，不能把内容相同的两个独立对象当同一资源。

**开发与回归。** 修改 Eq/Hash/转换/upgrade 时覆盖 clone、不同分配、Weak 过期和集合插入删除；不得让 key 在集合内改变 hash。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p keyable-arc`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需具体注册表的移除/末引用行为测试；pointer identity 不是持久 ID 或跨重启身份。 当前 `src/**/*.rs` 的静态测试属性声明：`test=4`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## logo-ascii-art

[manifest](../../../kernel/asterinas/kernel/libs/logo-ascii-art/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/logo-ascii-art/src/lib.rs)。既有文档：[README.md](../../../kernel/asterinas/kernel/libs/logo-ascii-art/README.md)。

**职责与接口。** 提供黑白和彩色 Asterinas logo 静态字符串，含演示 main 和可选 color feature。

**状态、所有权与失败边界。** 无运行时资源 owner；返回静态字符串，终端颜色是否支持由输出端决定。

**开发与回归。** 修改图案检查每行宽度、ANSI 颜色重置与无色 feature；分别查看实际终端的渲染。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p logo-ascii-art`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 尚无所有终端/字符宽度实测；该 crate 不影响 Organ 控制权限或内核能力判定。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## ring-buffer

[manifest](../../../kernel/asterinas/kernel/libs/ring-buffer/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/ring-buffer/src/lib.rs) · [test.rs](../../../kernel/asterinas/kernel/libs/ring-buffer/src/test.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 基于 Segment<()> 的无锁单生产者/单消费者 FIFO，T: Pod，容量必须为 2 的幂。

**状态、所有权与失败边界。** split 通过 Arc 共享 ring，Producer 与 Consumer 分别独占写/读角色；不是 MPMC。构造路径对乘法/分配使用 unwrap，不能当成已可返回 NoMemory 的恢复 IPC。

**开发与回归。** 修改 head/tail 的 Acquire/Release 或批量提交时覆盖环绕、满/空和跨线程可见性；不要复制 producer 或暴露并行写者。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需真实跨核长时间环绕/并发测试，以及恢复 IPC 的 fallible 分配设计；现有 ktest 不给它自动授予 reserve。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=3`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## sparse-id-alloc

[manifest](../../../kernel/asterinas/kernel/libs/sparse-id-alloc/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/sparse-id-alloc/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** SparseIdAlloc 在可配置 inclusive u32 范围内分配最小空闲 ID 并支持归还。

**状态、所有权与失败边界。** allocator 自身拥有 ID 可用集合，调用者拥有实际对象；ID 被归还前必须保证旧引用不会误命中新对象。

**开发与回归。** 修改区间或复用策略时覆盖空区间、u32 边界、耗尽、重复释放与碎片；调用处单独设计锁和 generation。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需消费者的并发/ABA 防护；本库的 ID 可复用不构成 capability 不可伪造证明。 当前 `src/**/*.rs` 的静态测试属性声明：`test=7`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## short-vis-path

[manifest](../../../kernel/asterinas/kernel/libs/short-vis-path/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/short-vis-path/src/lib.rs) · [args.rs](../../../kernel/asterinas/kernel/libs/short-vis-path/src/args.rs) · [tests.rs](../../../kernel/asterinas/kernel/libs/short-vis-path/src/tests.rs)。既有文档：[README.md](../../../kernel/asterinas/kernel/libs/short-vis-path/README.md)。

**职责与接口。** 属性宏 `#[short_vis_path::add]` 为受限可见性路径生成辅助结构，已有专门 README。

**状态、所有权与失败边界。** 只改变编译期路径/可见性表达；必须保留 Rust 实际模块祖先约束，re-export 路径不能随意当 pub(in …) 的合法路径。

**开发与回归。** 改参数解析/输出时沿 args/tests 补合法祖先、非法路径、嵌套模块与冲突名字的编译案例。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p short-vis-path`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 宿主宏用例之外需真实内核消费者编译；语法可见性不是运行时授权。 当前 `src/**/*.rs` 的静态测试属性声明：`test=5`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## typeflags

[manifest](../../../kernel/asterinas/kernel/libs/typeflags/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/typeflags/src/lib.rs) · [flag_set.rs](../../../kernel/asterinas/kernel/libs/typeflags/src/flag_set.rs) · [type_flag.rs](../../../kernel/asterinas/kernel/libs/typeflags/src/type_flag.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 过程宏生成类型级 flag 集合声明，配合 typeflags-util 的集合运算。

**状态、所有权与失败边界。** 编译器类型关系是唯一状态；各 bit 的业务含义、动态值验证和运行时主体归消费者。

**开发与回归。** 增加集合语法或展开时检查重复 flag/bit、类型名卫生、可见性与生成的 trait；补合法和拒绝编译案例。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p typeflags`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需消费者类型与动态 flags 一致性；宏不提供持久 grant 或撤销。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## typeflags-util

[manifest](../../../kernel/asterinas/kernel/libs/typeflags-util/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/typeflags-util/src/lib.rs) · [bool.rs](../../../kernel/asterinas/kernel/libs/typeflags-util/src/bool.rs) · [set.rs](../../../kernel/asterinas/kernel/libs/typeflags-util/src/set.rs) · [same.rs](../../../kernel/asterinas/kernel/libs/typeflags-util/src/same.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 类型级布尔、相同、分支、集合包含/扩展等 trait，供 typeflags 与 aster-rights-proc 生成代码使用。

**状态、所有权与失败边界。** 无资源存储；trait 实现表示编译期关系，不能代替动态检查或原对象 owner。

**开发与回归。** 变更递归集合/布尔实现时补类型等价与不满足约束的编译测试，并连编下游宏和 Rights 消费者。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p typeflags-util`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 尚需生成代码在真实 capability API 上的负向使用测试；仅类型算例不足以验证完整授权。 当前 `src/**/*.rs` 的静态测试属性声明：`test=3`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## xarray

[manifest](../../../kernel/asterinas/kernel/libs/xarray/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/libs/xarray/src/lib.rs) · [cursor.rs](../../../kernel/asterinas/kernel/libs/xarray/src/cursor.rs) · [node.rs](../../../kernel/asterinas/kernel/libs/xarray/src/node.rs) · [test.rs](../../../kernel/asterinas/kernel/libs/xarray/src/test.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** RCU 的稀疏数组，存放 Arc/Box 等 NonNullPtr；读者可并发，写者通过 lock 和 CursorMut 单独修改。

**状态、所有权与失败边界。** LockedXArray 管写锁，移除节点/最终引用的释放可能延后至 RCU grace。drop(vmar) 后即时计数不为零不能直接判漏，也不能跳过最终退款断言。

**开发与回归。** 修改节点/游标/mark 时覆盖插入、替换、删除、遍历和并发读；涉及 Frame/VMO account 必须等待真实 RCU 完成再核对末引用退款。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需 SMP 读写压力、grace 有界性与实际消费者生命周期测试；单任务 ktest 不能证明所有引用都及时回收。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=20`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。
