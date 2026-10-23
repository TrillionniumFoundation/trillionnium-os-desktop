# 内核装配、核心与设备组件（21 crate）

源码基线 `10dae5ea4ae5c2f81e2e530b1eb74bd41a5c29cd`。阅读前先看 [范围、共同开发流程与证据规则](README.md)。下列“待验证”是具体后续门禁，不是已完成声明。

## asterinas

[manifest](../../../kernel/asterinas/kernel/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 内核装配 crate；`#[ostd::main]` 进入 `aster_core::boot`，显式链接 DRM、simpledrm、UART，以及 x86_64 的 i8042。

**状态、所有权与失败边界。** 这里不拥有进程或设备运行状态；依赖清单与 `extern crate … as _` 必须同步，否则仅加 Cargo 依赖可能没有链接组件注册与初始化代码。

**开发与回归。** 增加组件时同时审查 manifest、显式链接、组件初始化顺序和对应架构 cfg；先检查普通 profile，再分别检查 G1-c/d feature 传播。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 启动成功只证明该镜像的装配；未证明全部设备驱动、桌面 shell 或移动设备控制可用。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-drm

[manifest](../../../kernel/asterinas/kernel/comps/drm/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/comps/drm/src/lib.rs) · [device.rs](../../../kernel/asterinas/kernel/comps/drm/src/device.rs) · [file.rs](../../../kernel/asterinas/kernel/comps/drm/src/file.rs) · [gem/object.rs](../../../kernel/asterinas/kernel/comps/drm/src/gem/object.rs) · [ioctl/mod.rs](../../../kernel/asterinas/kernel/comps/drm/src/ioctl/mod.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** Linux DRM 字符设备框架；`register_device(Arc<dyn DrmDevice>)` 接入设备，`gem` 管对象，`kms` 管显示对象与模式，`ioctl` 分派 ABI。

**状态、所有权与失败边界。** 框架拥有公共 file/minor/GEM/KMS 生命周期与权限检查；具体显存、扫描输出、硬件操作归 `DrmDevice` 实现。不能把注册一个 DRM 设备等同于 GPU compute 或隔离。

**开发与回归。** 新增 ioctl 应同时走 file 权限、对象 ID/引用生命周期和用户缓冲区错误路径；新增设备先实现明确支持的 operation traits，再用真实用户态调用覆盖。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 尚需逐 ioctl 的权限/坏指针/并发关闭回归和同源 compositor 实测；simpledrm 不授予 GPU DMA、reset 或多租户隔离资格。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-i8042

[manifest](../../../kernel/asterinas/kernel/comps/i8042/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/comps/i8042/src/lib.rs) · [controller.rs](../../../kernel/asterinas/kernel/comps/i8042/src/controller.rs) · [keyboard.rs](../../../kernel/asterinas/kernel/comps/i8042/src/keyboard.rs) · [mouse.rs](../../../kernel/asterinas/kernel/comps/i8042/src/mouse.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** x86 PS/2 控制器的键盘和鼠标输入，拆分 controller、ps2 协议及 keyboard/mouse 解码。

**状态、所有权与失败边界。** 控制器/中断处理持有硬件交互状态；输入事件交给 aster-input。按键事件来源不是 Hepta capability，也不是用户对高权限动作的同意。

**开发与回归。** 修改扫描码或鼠标包时检查控制器命令/响应、IRQ 与解析状态机；保留不完整序列及设备缺失的处理，联测 evdev 消费者。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 真实键盘布局、组合键、热插拔/丢包与多个设备竞争未由本文验证；该驱动不覆盖触屏或 Android 输入注入。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-simpledrm

[manifest](../../../kernel/asterinas/kernel/comps/simpledrm/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/comps/simpledrm/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 使用 bootloader framebuffer 的显示驱动，从 aster-framebuffer 取得资源并向 aster-drm 注册。

**状态、所有权与失败边界。** 显示内存归 framebuffer 的 IoMem；本 crate 适配 DRM 操作，不能凭软件显示缓冲拥有独立 GPU 引擎或恢复控制权。

**开发与回归。** 变更模式、pitch、GEM 或 mmap 时沿单文件实现核对长度和像素格式，联测 DRM 设备打开、framebuffer 映射及真实屏幕输出。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 尚需固件提供不同 pitch/格式、无 framebuffer、并发显示与会话切换实测；没有硬件加速、GPU reset 或完整桌面运行的本轮证据。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-uart

[manifest](../../../kernel/asterinas/kernel/comps/uart/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/comps/uart/src/lib.rs) · [console.rs](../../../kernel/asterinas/kernel/comps/uart/src/console.rs) · [arch/x86/mod.rs](../../../kernel/asterinas/kernel/comps/uart/src/arch/x86/mod.rs) · [arch/arm/mod.rs](../../../kernel/asterinas/kernel/comps/uart/src/arch/arm/mod.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 按 x86、ARM、RISC-V、LoongArch 分架构的 UART 驱动，并经 console 模块接入通用控制台。

**状态、所有权与失败边界。** 各架构驱动拥有寄存器、IRQ 和接收状态；控制台 callback 的线程/中断上下文需与调用者一致。串口日志本身不构成可信授权通道。

**开发与回归。** 新平台先确认寄存器布局、时钟/波特率和 IRQ 接线，再实现 console 接口；保留无设备和接收错误路径，联测启动日志与输入。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** QEMU 串口成功不覆盖实体串口时序、突发流量、背压、丢字节或 suspend/resume。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-core

[manifest](../../../kernel/asterinas/kernel/core/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/src/lib.rs) · [process/mod.rs](../../../kernel/asterinas/kernel/core/src/process/mod.rs) · [fs/fs_impls/cgroupfs/controller/cpu.rs](../../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs) · [fs/fs_impls/cgroupfs/controller/memory.rs](../../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/memory.rs) · [device/misc/hepta_control.rs](../../../kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** Linux ABI 与核心内核机制：syscall、Process/Thread、调度、VFS/文件系统、VMAR/VMO、socket/IPC 与设备。fork 在这些原 owner 上接 HOS2 和受信 profile。

**状态、所有权与失败边界。** Process 持有原身份/作业停止事实，cgroup CPU owner 持有 cap/consumed/debt/revision；VMO account 与底层物理 allocator 分层。HOS2 不能制造第二份资源账或把调用者标签当用户意图。普通构建仍 QueryAbi-only。

**开发与回归。** 按具体 owner 进入子模块；修改 syscall 同时检查权限、已打开 FD、别名、失败回滚与并发边界。完整 core gate 之外，用原 Linux workload 和固定角色 guest 验证用户可见行为。 使用 [严格 native runner](../../../support/build/ktest/README.md) 的 `--crate aster-core`，保留完整名称/分母、原锁、真实 QEMU raw 33 和无超时。

**实际覆盖与待验证。** 固定 G1-d 角色不等于生产动态 grant；memory.max 总量控制、全局恢复链、可信用户 pause intent、全设备控制仍各有缺口。live RDONLY 转换目前明确拒绝，不能称为动态 remount 实现。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=291`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-block

[manifest](../../../kernel/asterinas/kernel/core/comps/block/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/block/src/lib.rs) · [bio.rs](../../../kernel/asterinas/kernel/core/comps/block/src/bio.rs) · [request_queue.rs](../../../kernel/asterinas/kernel/core/comps/block/src/request_queue.rs) · [partition.rs](../../../kernel/asterinas/kernel/core/comps/block/src/partition.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 块设备注册、查找、分区扫描，以及 `BlockDevice::enqueue`、`Bio`/`SubmittedBio` 异步块 I/O 模型。

**状态、所有权与失败边界。** 设备 driver 拥有队列与请求完成，Bio 持有传输 segment；完成成功、排队成功和持久化成功是不同状态。`BLOCK_SIZE` 与 512-byte sector 的单位不得混用。

**开发与回归。** 新增设备实现 metadata/id/name/enqueue，审查最大 segment、边界和 flush 完成语义；从提交失败到最终 completion 必须只有一个明确结果。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需真实设备读写/flush/超时/掉电与请求并发测试；内存后端成功不证明介质持久性或故障恢复。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-cmdline

[manifest](../../../kernel/asterinas/kernel/core/comps/cmdline/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/cmdline/src/lib.rs) · [parse.rs](../../../kernel/asterinas/kernel/core/comps/cmdline/src/parse.rs) · [dispatch.rs](../../../kernel/asterinas/kernel/core/comps/cmdline/src/dispatch.rs) · [early.rs](../../../kernel/asterinas/kernel/core/comps/cmdline/src/early.rs) · [types.rs](../../../kernel/asterinas/kernel/core/comps/cmdline/src/types.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 通过 inventory 收集 `define_kv_param!`、重复键和 flag 的注册项，在早期启动将文本解析为类型化参数。

**状态、所有权与失败边界。** `KernelParam` 注册与 `ParamStorage` 是参数 owner；解析影响 init 参数和各组件配置，不是运行时授权系统。早期参数与常规分派路径有不同初始化前提。

**开发与回归。** 新增参数同时给出默认值、重复键规则、非法值行为和消费时机；在 parse/types/dispatch 的原测试中补合法、重复和非法输入。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 还需每个实际消费者的启动组合回归；参数能解析不表示该设备、隔离 feature 或恢复策略已被验证。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=26`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-console

[manifest](../../../kernel/asterinas/kernel/core/comps/console/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/console/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** `AnyConsoleDevice` 抽象及以名字注册/列举设备的全局控制台登记表；接收回调传 `VmReader<Infallible>`。

**状态、所有权与失败边界。** 登记表保有 Arc 设备引用；具体硬件和 I/O 状态归 UART/virtio-console 等实现。持有登记表锁时不得随意引入会反向注册或阻塞的回调。

**开发与回归。** 变更注册/输出/输入接口时同步所有 console 实现和日志调用者，明确回调上下文与缓冲区借用期限。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需要多 console 选择、并发注册/打印、突发输入及设备消失的集成测试；这里没有安全终端认证。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-device

[manifest](../../../kernel/asterinas/kernel/core/comps/device/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/device/src/lib.rs) · [common/registration.rs](../../../kernel/asterinas/kernel/core/comps/device/src/common/registration.rs) · [bus/mod.rs](../../../kernel/asterinas/kernel/core/comps/device/src/bus/mod.rs) · [class/mod.rs](../../../kernel/asterinas/kernel/core/comps/device/src/class/mod.rs) · [hooks.rs](../../../kernel/asterinas/kernel/core/comps/device/src/hooks.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 总线/驱动匹配、设备父子关系、class 与 sysfs 视图的通用设备模型。

**状态、所有权与失败边界。** 本 crate 拥有 `/sys/devices`、`/sys/bus`、`/sys/class`、`/sys/dev` 的模型节点；注册 handle、observer 与底层硬件 owner 分离，不能把 sysfs 可见性当设备权限。

**开发与回归。** 新增 bus/class 时沿 registration 和 hooks 建立节点与回收，检查失败回滚、重复注册及父子移除；沿原 test 目录扩展 lifecycle 用例。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 现有模型测试不能替代真实热插拔、driver unbind 后 DMA 停止和用户 FD 存活边界。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=17`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-framebuffer

[manifest](../../../kernel/asterinas/kernel/core/comps/framebuffer/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/framebuffer/src/lib.rs) · [framebuffer.rs](../../../kernel/asterinas/kernel/core/comps/framebuffer/src/framebuffer.rs) · [pixel.rs](../../../kernel/asterinas/kernel/core/comps/framebuffer/src/pixel.rs) · [mode.rs](../../../kernel/asterinas/kernel/core/comps/framebuffer/src/mode.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** boot framebuffer 的 IoMem、分辨率/像素转换、调色表与文本绘制支持。

**状态、所有权与失败边界。** `FRAMEBUFFER` Once 持有 Arc；`FrameBuffer` 持有 IoMem，调用者负责绘制同步。源码仍按 bpp 猜像素格式、按 width×像素字节数推算 line_size；boot pitch 信息缺失是具体兼容边界。

**开发与回归。** 修改 boot 信息到 FrameBuffer 的转换时必须传递真实 pitch/格式，核对页对齐和长度溢出；修改字体/像素单元后联测 simpledrm 的 mmap 和输出。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 当前没有证明不同固件 pitch、旋转、多显示器与实体面板正确；不应以存在 framebuffer 推断具备桌面产品能力。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=3`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-input

[manifest](../../../kernel/asterinas/kernel/core/comps/input/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/input/src/lib.rs) · [input_core.rs](../../../kernel/asterinas/kernel/core/comps/input/src/input_core.rs) · [input_dev.rs](../../../kernel/asterinas/kernel/core/comps/input/src/input_dev.rs) · [input_handler.rs](../../../kernel/asterinas/kernel/core/comps/input/src/input_handler.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 输入事件经 `InputDevice → InputCore → InputHandler` 分派；设备注册返回 `RegisteredInputDevice`。

**状态、所有权与失败边界。** 注册生命周期与 handler 连接由 InputCore 管理，硬件状态归 driver，用户态消费由 evdev 等 handler 负责。事件路由不授予任意输入注入或远程控制权。

**开发与回归。** 新增设备先声明 event type/code 和能力；检查注册 handle 释放、handler attach/detach、事件序列及回调锁序。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需要真实输入队列溢出、拔出时 FD 存活、触摸坐标/多点协议和会话隔离；本文没有移动端实机结果。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-logger

[manifest](../../../kernel/asterinas/kernel/core/comps/logger/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/logger/src/lib.rs) · [aster_logger.rs](../../../kernel/asterinas/kernel/core/comps/logger/src/aster_logger.rs) · [console.rs](../../../kernel/asterinas/kernel/core/comps/logger/src/console.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 实现 log facade，按全局级别过滤，可选彩色输出，保证多核日志整条不交错。

**状态、所有权与失败边界。** 打印期间关闭 IRQ；日志锁/控制台是共享资源，长消息和高频 timer 日志可能延迟关键路径。日志不是持久审计账本。

**开发与回归。** 调整格式或 sink 时保留并发完整性，避免在持有同一 console/IRQ 锁时递归打印；性能变更应测最坏 IRQ 关闭时间。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 没有实体高负载延迟或掉电持久日志的本轮证据；debug 输出不得作为 Hepta durable receipt。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-mlsdisk

[manifest](../../../kernel/asterinas/kernel/core/comps/mlsdisk/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/mlsdisk/src/lib.rs) · [layers/0-bio/block_set.rs](../../../kernel/asterinas/kernel/core/comps/mlsdisk/src/layers/0-bio/block_set.rs) · [layers/5-disk/mlsdisk.rs](../../../kernel/asterinas/kernel/core/comps/mlsdisk/src/layers/5-disk/mlsdisk.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 提供 `MlsDisk`、加密/log/事务层和 BlockSet 适配；集成入口目前查固定设备 255:0，随机生成 root key 后调用 create。

**状态、所有权与失败边界。** `RawDisk` 持有底层 `Arc<dyn BlockDevice>` 与区间；当前 `RawDisk::flush` 直接返回 Ok，未提交底层 Flush。随机 key/create 路径没有提供持久密钥管理或重启自动 open 合同。

**开发与回归。** 先核对当前 kernel/core manifest 是否链接此组件，再沿 MlsDisk 的 sync/BlockSet flush 到 BlockDevice/BioType::Flush 做真实传播；不可仅因内存盘测试成功就宣称落盘。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 阻断：flush 的虚假成功需要修复或 fail-closed，且须查公开 MlsDisk API/可选驱动装配的可达性；密钥保存、非破坏性设备选择、掉电恢复独立开放。见本册 MLSDisk 专项。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=1, test=34`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-network

[manifest](../../../kernel/asterinas/kernel/core/comps/network/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/network/src/lib.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 网卡登记表和 send/receive softirq 回调，把 AnyNetworkDevice 连接到协议栈。

**状态、所有权与失败边界。** 设备引用为带 BottomHalfDisabled 的 SpinLock/Arc；收发回调与 softirq 协同，硬件队列仍属网卡 driver。注册名字不提供网络隔离或包认证。

**开发与回归。** 变更 callback/锁顺序时检查 IRQ、softirq 和协议栈调用上下文；新增网卡需明确完成通知、队列满与设备失败处理。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需包丢失、洪泛、断链、并发 teardown 与实体网卡测试；登记成功不等于网络安全策略闭合。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-nvme

[manifest](../../../kernel/asterinas/kernel/core/comps/nvme/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/nvme/src/lib.rs) · [device/block_device.rs](../../../kernel/asterinas/kernel/core/comps/nvme/src/device/block_device.rs) · [nvme_queue.rs](../../../kernel/asterinas/kernel/core/comps/nvme/src/nvme_queue.rs) · [prp.rs](../../../kernel/asterinas/kernel/core/comps/nvme/src/prp.rs) · [msix.rs](../../../kernel/asterinas/kernel/core/comps/nvme/src/msix.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** NVMe PCI 存储驱动，含 namespace、admin/I/O 队列、PRP 数据映射和 MSI-X；向上提供 NvmeBlockDevice。

**状态、所有权与失败边界。** driver 持有队列、命令槽、DMA/PRP 与中断完成状态；上层请求不得在硬件仍访问时回收其内存。设备规范版本声明不等于完整命令支持。

**开发与回归。** 新增命令沿 nvme_cmd/spec → queue → completion → BlockDevice 映射，检查错误码、边界、flush 和超时；修改 PRP 必须覆盖跨页/多段。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需要实盘 flush 持久性、队列饱和、reset/热拔插、坏介质和 IOMMU 约束证据；QEMU 正常读写不覆盖这些路径。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=7`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-pci

[manifest](../../../kernel/asterinas/kernel/core/comps/pci/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/pci/src/lib.rs) · [bus.rs](../../../kernel/asterinas/kernel/core/comps/pci/src/bus.rs) · [common_device.rs](../../../kernel/asterinas/kernel/core/comps/pci/src/common_device.rs) · [capability/msix.rs](../../../kernel/asterinas/kernel/core/comps/pci/src/capability/msix.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** PCI 枚举、配置空间、BAR/capability 和驱动匹配框架；`PCI_BUS` 为全局 Mutex<PciBus>。

**状态、所有权与失败边界。** bus 保有已构造设备引用，driver construct/probe 管具体设备；PCI 标识和可访问 BAR 不表示 DMA 已被安全隔离。

**开发与回归。** 新 driver 使用精确 ID 匹配，核对 capability 链、BAR 长度/类型、MSI-X 表和 probe 失败回滚；避免全局 bus 锁与 driver 锁反转。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 真实热插拔、复位后的 BAR/IRQ 重建、IOMMU 域和跨设备 DMA 隔离仍需平台级验证。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-softirq

[manifest](../../../kernel/asterinas/kernel/core/comps/softirq/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/softirq/src/lib.rs) · [lock.rs](../../../kernel/asterinas/kernel/core/comps/softirq/src/lock.rs) · [taskless.rs](../../../kernel/asterinas/kernel/core/comps/softirq/src/taskless.rs) · [softirq_id.rs](../../../kernel/asterinas/kernel/core/comps/softirq/src/softirq_id.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 提供 SoftIrqLine、底半部禁用 guard、taskless 路径与每 CPU daemon 执行软件中断。

**状态、所有权与失败边界。** pending 状态与回调调度归该组件；上层 network 等只触发对应 line。BottomHalfDisabled 不等于任意上下文都能阻塞或取得睡眠锁。

**开发与回归。** 新增 line 先声明 ID/处理上下文，检查重复 raise、pending 合并、重新触发和 daemon 唤醒；锁封装变更应覆盖嵌套与退出恢复。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需要真实多核饱和/公平性与中断风暴下延迟结果；单 vCPU ktest 的交错不能作为 SMP 资格。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=5, test=1`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-systree

[manifest](../../../kernel/asterinas/kernel/core/comps/systree/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/systree/src/lib.rs) · [tree.rs](../../../kernel/asterinas/kernel/core/comps/systree/src/tree.rs) · [node.rs](../../../kernel/asterinas/kernel/core/comps/systree/src/node.rs) · [attr.rs](../../../kernel/asterinas/kernel/core/comps/systree/src/attr.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 以 SysTree/节点/属性表达系统状态；主树供 sysfs，其他子系统可有独立树。

**状态、所有权与失败边界。** 树是模型，文件系统是其 view；Node/Tree 的引用与锁管理层级，不替代 cgroup 或硬件真实资源 owner。树上有值不说明实际资源已经变化。

**开发与回归。** 新增节点或属性检查名字、父子关系、移除、读写 callback 和错误码；避免在树锁内递归进入消费者。沿 tree/node/attr 的原测试扩展。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需要具体消费者的并发读写与删除集成；共享模型不能代替每个属性的权限和 side-effect 合同。 当前 `src/**/*.rs` 的静态测试属性声明：`ktest=16`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-time

[manifest](../../../kernel/asterinas/kernel/core/comps/time/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/time/src/lib.rs) · [clocksource.rs](../../../kernel/asterinas/kernel/core/comps/time/src/clocksource.rs) · [tsc.rs](../../../kernel/asterinas/kernel/core/comps/time/src/tsc.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** RTC 启动时间和 monotonic clocksource/Instant，向 vDSO 暴露高精度更新钩子。

**状态、所有权与失败边界。** ClockSourceSample 是带来源信息的采样；wall time 与 monotonic Duration 不可互换。`try_read_monotonic_sample` 可 None，依赖限期/预算的调用者必须处理未知或倒退时间。

**开发与回归。** 修改 clocksource/校准时核对单位、溢出、跨 CPU 一致性和 vDSO 更新顺序；计费/到期策略必须继续在其原 owner 中执行。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 需实体多核漂移、虚拟机暂停/恢复、RTC 错值和架构时钟切换测试；时钟存在不证明 watchdog 全链故障有界。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## aster-virtio

[manifest](../../../kernel/asterinas/kernel/core/comps/virtio/Cargo.toml) · [入口源码](../../../kernel/asterinas/kernel/core/comps/virtio/src/lib.rs) · [device/mod.rs](../../../kernel/asterinas/kernel/core/comps/virtio/src/device/mod.rs) · [queue.rs](../../../kernel/asterinas/kernel/core/comps/virtio/src/queue.rs) · [dma_buf.rs](../../../kernel/asterinas/kernel/core/comps/virtio/src/dma_buf.rs)。既有文档：同目录没有 Markdown；本条结合入口/子模块注释补充维护合同。

**职责与接口。** 实现 block、console、entropy、filesystem、input、network、socket 设备以及 queue/transport/DMA 支持。

**状态、所有权与失败边界。** 每个 device 保有协商 feature、virtqueue descriptor 与传输内存；完成通知后才能退还 buffer。枚举包含 Gpu/Iommu ID 不代表已有对应 driver 模块。

**开发与回归。** 新增设备从 transport feature negotiation 和 queue 生命周期开始，检查长度、设备返回值、队列满、断链与重置；分别联测其上层 block/input/socket 接口。 原工作区 `make ktest` 覆盖 default-members；定向开发可从此 crate 目录使用原 `cargo osdk test`。项目严格封装 runner 目前只接受 core/OSTD/frame-allocator 三 crate，不能把本 crate 填入其 `--crate`。

**实际覆盖与待验证。** 没有本轮 virtio-GPU 加速或 IOMMU device 合格证明；恶意设备响应、reset 与跨 VM 共享边界需独立验证。 当前 `src/**/*.rs` 的静态测试属性声明：`0`；它不计宏展开、跨架构 cfg 或 doctest，不是 native 分母或通过数。本次仅文档校验，未执行该 crate 的编译/测试。

## MLSDisk 专项：真实持久化与装配边界

本基线的 [RawDisk 实现](../../../kernel/asterinas/kernel/core/comps/mlsdisk/src/lib.rs) 中，`flush()` 无条件 `Ok(())`，而 read/write 会提交 Bio 并等待完成。它不能把底层易失缓存已经落盘的事实传给上层事务。`MlsDisk`/`BlockSet` 的公开接口和独立组件装配必须分别检查；本基线的 [core manifest](../../../kernel/asterinas/kernel/core/Cargo.toml) 和 [assembler manifest](../../../kernel/asterinas/kernel/Cargo.toml) 均未依赖 aster-mlsdisk；当前普通镜像没有因工作区包含它就提供该块设备。独立 crate/可选装配仍可调用公开 API，不能因此忽略错误合同。

具体链路在 [MlsDisk 实现](../../../kernel/asterinas/kernel/core/comps/mlsdisk/src/layers/5-disk/mlsdisk.rs)：`BlockDevice::enqueue(Flush)` 调用公开 `MlsDisk::sync`，后者取得 write_sync_region 写锁后对 `inner.sync()` 使用 `unwrap()`；DiskInner 会 flush data buffer、metadata/事务日志，再调用底层 `BlockSet::flush`。所以还存在底层 I/O 错误被公开 sync 升级为 panic 的问题；只补 RawDisk 的真实 flush 而不修错误传播是不完整的。

修复验收须沿实际 sync → BlockSet::flush → BlockDevice 的 `BioType::Flush` 链路，验证完成成功、设备拒绝、完成 I/O 错误都返回正确结果，并增加真实存储集成/掉电恢复门禁。若底层不支持 flush，应明确返回错误，不能用 no-op 成功代替。`MlsDisk::create`、随机 root key 与固定 255:0 选择是另外的实验性初始化边界；flush 修复不自动完成密钥持久管理或启动后重开。本文只记录问题，未修改或验收这些实现。
