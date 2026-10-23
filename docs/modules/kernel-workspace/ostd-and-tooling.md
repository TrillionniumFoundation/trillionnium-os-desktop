# OSTD、内存分配与构建测试工具（16 crate）

源码基线 `10dae5ea4ae5c2f81e2e530b1eb74bd41a5c29cd`。阅读前先看 [范围、共同开发流程与证据规则](README.md)。下列“待验证”是具体后续门禁，不是已完成声明。

## osdk-frame-allocator

[manifest](../../../kernel/asterinas/osdk/deps/frame-allocator/Cargo.toml) · [入口源码](../../../kernel/asterinas/osdk/deps/frame-allocator/src/lib.rs) · [reserve.rs](../../../kernel/asterinas/osdk/deps/frame-allocator/src/reserve.rs) · [reserve/tests.rs](../../../kernel/asterinas/osdk/deps/frame-allocator/src/reserve/tests.rs) · [cache.rs](../../../kernel/asterinas/osdk/deps/frame-allocator/src/cache.rs) · [pools/mod.rs](../../../kernel/asterinas/osdk/deps/frame-allocator/src/pools/mod.rs)。既有文档：[README.md](../../../kernel/asterinas/osdk/deps/frame-allocator/README.md)。

**职责与接口。** 原全局 FrameAllocator：buddy/pools/per-CPU cache；opt-in physical-reserve 在同一分配 owner 内保护一个物理 extent。

**状态、所有权与失败边界。** reserve token 是显式分配权，普通分配不消耗保留区；close 先拒绝新分配，活页末引用归还后才放回普通池。只允许一个 active extent，旧 token 不可跨代复用。free counter 不是预留承诺。

**开发与回归。** 修改 reserve 必须保留原 alloc/dealloc 与分区退款，覆盖普通耗尽、碎片、任务交错、token close/stale、callback claim/别名及末引用。使用该 crate 独立锁/完整 20-name 门禁。 使用 [严格 native runner](../../../support/build/ktest/README.md) 的 `--crate osdk-frame-allocator`，保留完整名称/分母、原锁、真实 QEMU raw 33 和无超时。

**实际覆盖与待验证。** 物理机制仍 `global_recovery_guarantee=false`；未打通 heap、socket、生产 recovery admission 和完整 IPC。N0 的交错测试不授予 SMP，默认无 feature 行为不应改变。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=20`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## osdk-heap-allocator

[manifest](../../../kernel/asterinas/osdk/deps/heap-allocator/Cargo.toml) · [入口源码](../../../kernel/asterinas/osdk/deps/heap-allocator/src/lib.rs) · [allocator.rs](../../../kernel/asterinas/osdk/deps/heap-allocator/src/allocator.rs) · [cpu_local_allocator.rs](../../../kernel/asterinas/osdk/deps/heap-allocator/src/cpu_local_allocator.rs) · [slab_cache.rs](../../../kernel/asterinas/osdk/deps/heap-allocator/src/slab_cache.rs)。既有文档：[README.md](../../../kernel/asterinas/osdk/deps/heap-allocator/README.md)。

**职责与接口。** 全局 heap/slab 分配器与 CpuLocalBox，按 layout 分类并统计 slab 使用。

**状态、所有权与失败边界。** slab/cache 拥有对象槽与底层页；普通 Vec/Arc 等 heap 分配走这里，不因某进程有 PhysicalReserve token 就自动使用预留。统计是观测，不是可兑现恢复预算。

**开发与回归。** 修改 size-class、对齐或 per-CPU 分配时覆盖跨 CPU free、最后对象、超大 layout 和分配失败；审查 allocator 锁内递归分配。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 尚无显式恢复 heap token/fallible IPC 全链；不能用物理 reserve 测试推定任何 Box/Vec 在 OOM 下仍成功。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=2`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## osdk-test-kernel

[manifest](../../../kernel/asterinas/osdk/deps/test-kernel/Cargo.toml) · [入口源码](../../../kernel/asterinas/osdk/deps/test-kernel/src/lib.rs) · [tree.rs](../../../kernel/asterinas/osdk/deps/test-kernel/src/tree.rs) · [path.rs](../../../kernel/asterinas/osdk/deps/test-kernel/src/path.rs)。既有文档：[README.md](../../../kernel/asterinas/osdk/deps/test-kernel/README.md)。

**职责与接口。** OSDK 为 `#[ostd::ktest]` 生成的真实测试内核入口，组织测试树、捕获预期 panic 并退出 QEMU。

**状态、所有权与失败边界。** runner 拥有测试遍历和结果汇总；crate/test whitelist 会改变分母。串口 ok/最终 marker 之外还必须核对真实 QEMU 退出状态、超时、完整名称和软跳过。

**开发与回归。** 改 runner 必须做 host 反伪造测试并运行真实 guest；新增 suite 保留原 suite，不得用过滤/缺失测试冒充完整通过。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 它只证明所选架构/profile/测试；TCG VMX 软跳过不是 VMX 成功，程序 COMPLETE 后卡死也不算通过。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=8`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## ostd

[manifest](../../../kernel/asterinas/ostd/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/src/lib.rs) · [mm/frame/allocator.rs](../../../kernel/asterinas/ostd/src/mm/frame/allocator.rs) · [mm/page_table/mod.rs](../../../kernel/asterinas/ostd/src/mm/page_table/mod.rs) · [mm/vm_space.rs](../../../kernel/asterinas/ostd/src/mm/vm_space.rs) · [user.rs](../../../kernel/asterinas/ostd/src/user.rs)。既有文档：[README.md](../../../kernel/asterinas/ostd/README.md)。

**职责与接口。** framekernel 的受信基础层：架构、启动、MM/Frame/PageTable/VmSpace、任务、IRQ、同步、timer、用户态切换和虚拟化。

**状态、所有权与失败边界。** unsafe 限定在此受审边界；Frame/UniqueFrame 元数据拥有物理页生命周期，PageTable 拥有映射节点，Task/SigKill pre-entry hook 只允许致命信号内核清理。Rust 内存安全与硬件 DMA/特权隔离分别验证。

**开发与回归。** 修改 unsafe 必须写 Safety 不变量并检查并发/中断上下文；PhysicalReserve 的显式 VmSpace/RecoveryCursor 路径须在发布 PTE 前预分配全部必要页并通过原 owner 回滚，不得自动传给 fork/共享子树。 使用 [严格 native runner](../../../support/build/ktest/README.md) 的 `--crate ostd`，保留完整名称/分母、原锁、真实 QEMU raw 33 和无超时。

**实际覆盖与待验证。** 新 PT 路径的 same-source native 验收仍以完整 OSTD 门禁为准；heap/IPC/VMAR 上层 admission 未闭合，VMX/多架构/实机不从 x86 N0 推导。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=235`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## align_ext

[manifest](../../../kernel/asterinas/ostd/libs/align_ext/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/align_ext/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 为无符号整数提供 AlignExt::align_up/align_down。

**状态、所有权与失败边界。** 纯值运算；实现要求 alignment 为至少 2 的 2 次幂，调用者负责对上溢等边界作正确前置处理，不能将其当 checked allocation API。

**开发与回归。** 改运算需测试所有支持位宽、合法幂、临界最大值和非法 alignment；保留已有调用者的 panic/溢出行为合同。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p align_ext`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需 allocation/layout 各调用方对长度溢出的处理；普通数值测试不证明设备内存范围安全。 当前 `src/**/*.rs` 的静态测试属性声明：`test=2`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## id-alloc

[manifest](../../../kernel/asterinas/ostd/libs/id-alloc/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/id-alloc/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 位图 IdAlloc：单个、指定 ID 和连续区间分配/释放，耗尽返回 None。

**状态、所有权与失败边界。** BitVec 与 first_available_id 拥有可用状态；free/alloc_specific 的越界可 panic，重复释放只依赖 debug_assert 的检查，调用方必须保证归还有效的自有 ID。

**开发与回归。** 变更连续分配扫描时覆盖碎片、0长度、满容量、指定占用与释放后最小可用更新；并发同步归上层。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p id-alloc`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需消费者的 stale ID/重复归还/跨线程一致性测试，不能把裸 ID 当不可伪造 handle。 当前 `src/**/*.rs` 的静态测试属性声明：`test=1`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## int-to-c-enum

[manifest](../../../kernel/asterinas/ostd/libs/int-to-c-enum/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/int-to-c-enum/src/lib.rs)。既有文档：[README.md](../../../kernel/asterinas/ostd/libs/int-to-c-enum/README.md)。

**职责与接口。** 为 C 风格枚举提供整数转换错误类型并默认重导出 TryFromInt derive。

**状态、所有权与失败边界。** 转换只验证枚举 discriminant；业务可接受的状态/权限仍由调用者检查。default derive feature 与不含宏的使用方式要分别维护。

**开发与回归。** 改错误或 trait 导出时连同 derive crate 编译，覆盖有效/未知数值和所有指定 repr。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p int-to-c-enum`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需要 syscall/设备 wire 消费者的边界验证；合法枚举值不等于合法操作。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## int-to-c-enum-derive

[manifest](../../../kernel/asterinas/ostd/libs/int-to-c-enum/derive/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/int-to-c-enum/derive/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** `TryFromInt` 过程宏解析 C 风格枚举并生成转换。

**状态、所有权与失败边界。** 宏拥有代码生成，不存运行时状态；repr 和 discriminant 的解释必须与协议布局一致。

**开发与回归。** 新增支持语法时覆盖缺 repr、非整数 repr、显式/隐式 discriminant 和非法 enum 形态，检查诊断定位。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p int-to-c-enum-derive`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需各架构整数宽度及真实协议使用的编译回归；母 crate 宿主通过不替代内核调用测试。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## linux-boot-params

[manifest](../../../kernel/asterinas/ostd/libs/linux-bzimage/boot-params/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/linux-bzimage/boot-params/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 定义 Linux Boot Protocol 的 BootParams、SetupHeader、E820、EFI 与 ScreenInfo 布局。

**状态、所有权与失败边界。** bootloader 传入的结构地址与字段来自启动环境；本库描述 ABI，不负责验证所有指针/区间，也不保证 boot 信息完整。

**开发与回归。** 修改字段必须检查 repr/packed、offset/size 和 bootloader ABI，保持原布局测试；新增显示字段同步 OSTD boot 与 framebuffer 消费者。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p linux-boot-params`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需 BIOS/UEFI 与不同 bootloader 的真实启动；布局测试不能证明内存图、framebuffer pitch 或 secure boot。 当前 `src/**/*.rs` 的静态测试属性声明：`test=4`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## linux-bzimage-builder

[manifest](../../../kernel/asterinas/ostd/libs/linux-bzimage/builder/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/linux-bzimage/builder/src/lib.rs) · [encoder.rs](../../../kernel/asterinas/ostd/libs/linux-bzimage/builder/src/encoder.rs) · [mapping.rs](../../../kernel/asterinas/ostd/libs/linux-bzimage/builder/src/mapping.rs) · [pe_header.rs](../../../kernel/asterinas/ostd/libs/linux-bzimage/builder/src/pe_header.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 宿主工具库，将 setup ELF、内核 ELF 和 PE/COFF header/编码组合为 bzImage。

**状态、所有权与失败边界。** 生成产物由调用者管理；builder 的输入文件、目标类型与 payload encoding 决定镜像，不能混用旧 kernel ELF 验新源码。

**开发与回归。** 改 header/映射/压缩时保存输入输出 hash，验证入口与 section 对齐，并分别启动 UEFI 和 legacy 产物。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p linux-bzimage-builder`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需要成品镜像的 boot 结果；cargo test 无测试或仅格式通过不构成可启动证明。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## linux-bzimage-setup

[manifest](../../../kernel/asterinas/ostd/libs/linux-bzimage/setup/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/linux-bzimage/setup/src/main.rs) · [loader.rs](../../../kernel/asterinas/ostd/libs/linux-bzimage/setup/src/loader.rs) · [x86/amd64_efi/mod.rs](../../../kernel/asterinas/ostd/libs/linux-bzimage/setup/src/x86/amd64_efi/mod.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** bzImage 内的早期初始化、解压与内核加载程序；UEFI x86_64 与 legacy 32-bit 使用不同目标。

**状态、所有权与失败边界。** 执行时尚未进入完整 OSTD/heap 环境；loader 拥有镜像布局与跳转前机器状态。UEFI 与 legacy 不是同一个二进制同时支持的路径。

**开发与回归。** 沿 builder/OSDK 原入口构建对应 setup target，改 loader 同时检查地址/长度、解压失败和内核入口；不要用普通宿主 cargo test 替代。 按 [原 Makefile](../../../kernel/asterinas/Makefile) 与 builder/OSDK 的 setup 构建入口验证；它被原 `make test` 明确排除，不提供虚构的 host 单测命令。

**实际覆盖与待验证。** 原 Makefile test 明确排除此 crate；需要两种实际启动协议分别验收，且不推出 ARM/移动平台支持。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## ostd-macros

[manifest](../../../kernel/asterinas/ostd/libs/ostd-macros/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/ostd-macros/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 生成 main/test_main、全局 frame/heap allocator、panic handler、early cmdline 和 ktest 注册代码。

**状态、所有权与失败边界。** 宏建立 linker 符号/section 与唯一全局 owner 的连接；错误展开可能破坏启动或测试发现，不能仅看 proc-macro 自身通过。

**开发与回归。** 改属性解析同时检查消费者签名、重复注册诊断、链接 section 与每架构入口；ktest 宏修改要核对原完整测试 inventory。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p ostd-macros`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需要最终链接产物和真实启动/测试枚举；宿主宏单元测试不能证明全局 allocator 唯一或所有 tests 被执行。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=3`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## ostd-pod

[manifest](../../../kernel/asterinas/ostd/libs/ostd-pod/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/ostd-pod/src/lib.rs) · [array_helper.rs](../../../kernel/asterinas/ostd/libs/ostd-pod/src/array_helper.rs)。既有文档：[README.md](../../../kernel/asterinas/ostd/libs/ostd-pod/README.md)。

**职责与接口。** 基于 zerocopy 的 Pod trait 与数组助手，默认重导出 derive、pod_union、padding_struct。

**状态、所有权与失败边界。** Pod 要求字节可读写、KnownLayout、Immutable、Copy 等；它解决表示层安全，用户输入字段的值域/长度/权限仍需运行时验证。

**开发与回归。** 新增 POD 类型先检查 padding、alignment、repr 和无效 bit pattern；wire 变更核对字节序，分别测试读写/zeroed 和跨架构布局。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p ostd-pod`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** POD 不构成协议校验或授权；仍需 Linux/FUSE/设备 ABI 调用者的 malformed-input 回归。 当前 `src/**/*.rs` 的静态测试属性声明：`test=13`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## ostd-pod-macros

[manifest](../../../kernel/asterinas/ostd/libs/ostd-pod/macros/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/ostd-pod/macros/src/lib.rs) · [pod_union.rs](../../../kernel/asterinas/ostd/libs/ostd-pod/macros/src/pod_union.rs) · [pod_derive.rs](../../../kernel/asterinas/ostd/libs/ostd-pod/macros/src/pod_derive.rs)。既有文档：[README.md](../../../kernel/asterinas/ostd/libs/ostd-pod/macros/README.md)。

**职责与接口。** 生成 POD derive 及安全 union 包装；pod_union 要求 repr(C)，基于 zerocopy 生成字段 accessor/初始化。

**状态、所有权与失败边界。** 生成的透明 wrapper 拥有存储，accessor 借用底层 bytes；宏必须保持大小/对齐与无 padding 信息泄漏的约束。

**开发与回归。** 变更 union/derive 时覆盖不同字段大小、泛型、错误 repr、初始化与可变访问，联测 ostd-pod README 用法。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p ostd-pod-macros`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需多目标 layout 与编译拒绝用例；正常展开并不保证 wire 字段业务有效。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## ostd-test

[manifest](../../../kernel/asterinas/ostd/libs/ostd-test/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/ostd-test/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 内核测试描述符、panic 信息、KtestItem/Iter 和 linker `.ktest_array` 遍历，亦读取 crate/test whitelist。

**状态、所有权与失败边界。** 本库拥有注册项与执行封装，底层 runner 决定启动/退出；whitelist 会筛掉测试，结果不能省略过滤数。

**开发与回归。** 变更 item ABI 或迭代检查 section 边界、should_panic、路径和过滤行为，同时重跑 test-kernel 真实 discovery。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p ostd-test`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需要完整 guest 的实际分母与 raw exit；host 单测、空白 test 列表或 soft skip 都不是设备/内核功能合格。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=5`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## padding-struct

[manifest](../../../kernel/asterinas/ostd/libs/padding-struct/Cargo.toml) · [入口源码](../../../kernel/asterinas/ostd/libs/padding-struct/src/lib.rs)。既有文档：[README.md](../../../kernel/asterinas/ostd/libs/padding-struct/README.md)。

**职责与接口。** `#[padding_struct]` 将 repr(C) named-field struct 的隐式 padding 显式化，并生成 layout 断言。

**状态、所有权与失败边界。** 编译生成的参考结构用于计算字段 offset/总尺寸；添加的 padding 字段仍需正确初始化，不能承载未定义/敏感残留。

**开发与回归。** 改宏时覆盖尾 padding、中间 padding、泛型、对齐和非法输入诊断；与 Pod 宏联测，检查 ABI size/align 未变化。 在 `kernel/asterinas` 运行原宿主入口 `cargo +nightly-2026-07-21 test -p padding-struct`（属于原 `make test` 的 non-default 分组）；有宏展开/ABI 影响时还须连编实际消费者。

**实际覆盖与待验证。** 需目标架构实际 layout 和序列化回归；宏存在不证明所有跨边界结构都已使用它。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。
