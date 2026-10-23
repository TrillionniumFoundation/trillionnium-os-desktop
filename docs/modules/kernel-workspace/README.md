# 57 个内核 workspace crate 的开发与技术手册

本手册绑定源码 **`10dae5ea4ae5c2f81e2e530b1eb74bd41a5c29cd`**。它补齐每个 crate 的职责、接口、状态所有权、错误边界、开发入口和具体待验证项；不把文档覆盖率计作运行完成率。本次改动仅编写、核对文档，没有执行编译、宿主 Rust 测试或 QEMU。

范围来自 [原 workspace manifest](../../../kernel/asterinas/Cargo.toml) 的全部 **57 个显式 members**。其中 **11 个**目录已有 Markdown，**46 个**没有同目录 Markdown。这和最初审计 `39c1d84ebf854958f5829c0118b0c8b92a6b4926` 的存在性统计一致，但本手册重新读取上述新基线的 manifest、入口注释和相关实现。没有为 vendored 目录机械添加 README；集中手册按包名逐条索引。

| 分册 | 数量 | 维护范围 |
| --- | ---: | --- |
| [内核装配、核心与设备组件](kernel-components.md) | 21 | boot/core、DRM、输入、块设备、网络、NVMe/PCI、时间、系统树 |
| [内核通用库](kernel-libraries.md) | 20 | 网络栈、FUSE、权利类型、DMA、I/O、容器与过程宏 |
| [OSTD、内存分配与构建测试工具](ostd-and-tooling.md) | 16 | 受信基础层、物理/heap allocator、boot 协议、POD、原测试框架 |
| [逐 crate 机器清单](inventory.json) | 57 | manifest/入口 SHA256、features、依赖、默认成员分类、源码摘要与手册位置 |

`cargo-osdk` 的宿主工作区、comp-sys 子工作区、仓库顶层 services/libs/UI 等不在这 57 个内核成员中。A00–A10 的跨模块功能仍由 [总体模块审计](../../agents/MODULE_DOCUMENTATION_AUDIT.md) 和 [总文档索引](../../INDEX.md) 管理，不能用这 57 条覆盖替代那些产品模块的交付合同。

## 如何使用与更新

先找到下表的 crate，阅读其 manifest、入口源码与列出的关键子模块；在修改前遵守 [内核 AGENTS](../../../kernel/asterinas/AGENTS.md) 和 [编码规范](../../../kernel/asterinas/book/src/to-contribute/coding-guidelines/README.md)。默认工具链为 `nightly-2026-07-21`；原 [Makefile](../../../kernel/asterinas/Makefile) 的 `check`、`test`、`ktest` 分别管理源码质量、non-default 宿主测试、default-member 内核测试。架构 cfg、宏展开和运行 profile 会改变实际测试分母。

每个条目的静态测试属性数仅是读取 `src/**/*.rs` 中 `#[ktest]`/`#[test]` 的观察，不包括 doctest、宏生成的全部用例、目标条件展开或 src 之外的集成测试；它既不能用作 native gate 的分母，也不能证明“没有测试”。真实分母必须以最终源码生成的测试清单和实际完整运行日志为准。

本项目 [严格 native 门禁](../../../support/build/ktest/README.md) 目前单独支持 `aster-core`、`ostd`、`osdk-frame-allocator` 三 crate，保留各自原 OSDK/test-base 锁、完整测试名称、真实 QEMU raw exit 33、零失败/零过滤和超时记录。其他 default-member 的原入口是 `make ktest` 或从该 crate 目录运行原 `cargo osdk test`；不能给严格封装 runner 填它不支持的 crate 名。不要以一次全 core 测试替代所有独立设备组件套件。

每次交付必须另行记录 source commit、实际 features/profile/架构、工具版本、输入与 ELF hash、完整分母、失败/过滤/软跳过和 raw 退出；源码注释、Rust 类型安全、宿主单测、QEMU 运行、真实设备运行是不同层次的证据。TCG 下未运行的 VMX/EPT 路径应继续列为未验证。这里不复制旧成功数给新基线；新 PT、fatal cleanup 等变更须由父级本轮冻结源独立验收。

文中仓库相对源码链接用于当前 checkout 导航；固定身份以清单的 `source_commit`、manifest/入口 hash 及 `source_files_sha256` 为准。若链接目标已变化，可用 `git show 10dae5ea4ae5c2f81e2e530b1eb74bd41a5c29cd:<仓库相对路径>` 读回基线。源码摘要逐行由排序后的 `路径 + NUL + SHA256(文件字节)` 组成，行间 LF、末尾 LF；仅计该 crate 下被 Git 跟踪的 `src/**/*.rs`。这不是由可信第三方签名的执行证明。

## 仍需补齐的交付合同

这些手册为每个 crate 提供了可用的开发入口和维护合同；仍不能判断“每个模块已经文档完备”。具体 gaps 在各条目列出。尤其是：

- aster-core/OSTD/allocator 还要把物理预留、fallible 页表、上层 VMAR/heap/IPC、可信恢复 admission 接成同一真实路径；目前不得宣称全局恢复保证。
- DRM/simpledrm/framebuffer/input、NVMe/PCI/virtio、FDT/时钟等仍需逐平台、逐设备真实验证矩阵和失败恢复手册，不能由 x86 QEMU N0 扩展到桌面显卡或移动 BSP。
- MLSDisk 的底层 flush no-op 与公开 sync 错误 panic、随机 key/create 初始化属于具体未修复问题；普通 kernel/core 当前未链接它，但独立组件和公开 API 的持久性合同仍有缺口，详见 [专项](kernel-components.md#mlsdisk-专项真实持久化与装配边界)。
- 编译期权利、POD、系统树和设备注册只解决各自局部问题，不提供 Hepta 生产 grant、用户暂停意图、durable K/D 或完整设备控制能力。

新增 API 必须同时更新对应条目、源码注释和具体正反测试。修改现有行为应先明确原 owner 与失败回滚；不允许用复制资源账、放宽 gate、跳过失败用例或无条件返回成功来补“完成度”。

## 全部 crate 索引

| crate | workspace 路径 | 同目录 Markdown | 原执行分类 |
| --- | --- | ---: | --- |
| [osdk-frame-allocator](ostd-and-tooling.md#osdk-frame-allocator) | `osdk/deps/frame-allocator` | 1 | 内核 ktest |
| [osdk-heap-allocator](ostd-and-tooling.md#osdk-heap-allocator) | `osdk/deps/heap-allocator` | 1 | 内核 ktest |
| [osdk-test-kernel](ostd-and-tooling.md#osdk-test-kernel) | `osdk/deps/test-kernel` | 1 | 内核 ktest |
| [ostd](ostd-and-tooling.md#ostd) | `ostd` | 1 | 内核 ktest |
| [align_ext](ostd-and-tooling.md#align_ext) | `ostd/libs/align_ext` | 0 | 宿主 test |
| [id-alloc](ostd-and-tooling.md#id-alloc) | `ostd/libs/id-alloc` | 0 | 宿主 test |
| [int-to-c-enum](ostd-and-tooling.md#int-to-c-enum) | `ostd/libs/int-to-c-enum` | 1 | 宿主 test |
| [int-to-c-enum-derive](ostd-and-tooling.md#int-to-c-enum-derive) | `ostd/libs/int-to-c-enum/derive` | 0 | 宿主 test |
| [linux-boot-params](ostd-and-tooling.md#linux-boot-params) | `ostd/libs/linux-bzimage/boot-params` | 0 | 宿主 test |
| [linux-bzimage-builder](ostd-and-tooling.md#linux-bzimage-builder) | `ostd/libs/linux-bzimage/builder` | 0 | 宿主 test |
| [linux-bzimage-setup](ostd-and-tooling.md#linux-bzimage-setup) | `ostd/libs/linux-bzimage/setup` | 0 | setup 专用构建 |
| [ostd-macros](ostd-and-tooling.md#ostd-macros) | `ostd/libs/ostd-macros` | 0 | 宿主 test |
| [ostd-pod](ostd-and-tooling.md#ostd-pod) | `ostd/libs/ostd-pod` | 1 | 宿主 test |
| [ostd-pod-macros](ostd-and-tooling.md#ostd-pod-macros) | `ostd/libs/ostd-pod/macros` | 1 | 宿主 test |
| [ostd-test](ostd-and-tooling.md#ostd-test) | `ostd/libs/ostd-test` | 0 | 宿主 test |
| [padding-struct](ostd-and-tooling.md#padding-struct) | `ostd/libs/padding-struct` | 1 | 宿主 test |
| [asterinas](kernel-components.md#asterinas) | `kernel` | 0 | 内核 ktest |
| [aster-drm](kernel-components.md#aster-drm) | `kernel/comps/drm` | 0 | 内核 ktest |
| [aster-i8042](kernel-components.md#aster-i8042) | `kernel/comps/i8042` | 0 | 内核 ktest |
| [aster-simpledrm](kernel-components.md#aster-simpledrm) | `kernel/comps/simpledrm` | 0 | 内核 ktest |
| [aster-uart](kernel-components.md#aster-uart) | `kernel/comps/uart` | 0 | 内核 ktest |
| [aster-core](kernel-components.md#aster-core) | `kernel/core` | 0 | 内核 ktest |
| [aster-block](kernel-components.md#aster-block) | `kernel/core/comps/block` | 0 | 内核 ktest |
| [aster-cmdline](kernel-components.md#aster-cmdline) | `kernel/core/comps/cmdline` | 0 | 内核 ktest |
| [aster-console](kernel-components.md#aster-console) | `kernel/core/comps/console` | 0 | 内核 ktest |
| [aster-device](kernel-components.md#aster-device) | `kernel/core/comps/device` | 0 | 内核 ktest |
| [aster-framebuffer](kernel-components.md#aster-framebuffer) | `kernel/core/comps/framebuffer` | 0 | 内核 ktest |
| [aster-input](kernel-components.md#aster-input) | `kernel/core/comps/input` | 0 | 内核 ktest |
| [aster-logger](kernel-components.md#aster-logger) | `kernel/core/comps/logger` | 0 | 内核 ktest |
| [aster-mlsdisk](kernel-components.md#aster-mlsdisk) | `kernel/core/comps/mlsdisk` | 0 | 内核 ktest |
| [aster-network](kernel-components.md#aster-network) | `kernel/core/comps/network` | 0 | 内核 ktest |
| [aster-nvme](kernel-components.md#aster-nvme) | `kernel/core/comps/nvme` | 0 | 内核 ktest |
| [aster-pci](kernel-components.md#aster-pci) | `kernel/core/comps/pci` | 0 | 内核 ktest |
| [aster-softirq](kernel-components.md#aster-softirq) | `kernel/core/comps/softirq` | 0 | 内核 ktest |
| [aster-systree](kernel-components.md#aster-systree) | `kernel/core/comps/systree` | 0 | 内核 ktest |
| [aster-time](kernel-components.md#aster-time) | `kernel/core/comps/time` | 0 | 内核 ktest |
| [aster-virtio](kernel-components.md#aster-virtio) | `kernel/core/comps/virtio` | 0 | 内核 ktest |
| [aster-bigtcp](kernel-libraries.md#aster-bigtcp) | `kernel/libs/aster-bigtcp` | 0 | 内核 ktest |
| [aster-fuse](kernel-libraries.md#aster-fuse) | `kernel/libs/aster-fuse` | 1 | 内核 ktest |
| [aster-rights](kernel-libraries.md#aster-rights) | `kernel/libs/aster-rights` | 0 | 宿主 test |
| [aster-rights-proc](kernel-libraries.md#aster-rights-proc) | `kernel/libs/aster-rights-proc` | 0 | 宿主 test |
| [aster-util](kernel-libraries.md#aster-util) | `kernel/libs/aster-util` | 0 | 内核 ktest |
| [atomic-integer-wrapper](kernel-libraries.md#atomic-integer-wrapper) | `kernel/libs/atomic-integer-wrapper` | 0 | 宿主 test |
| [cpio-decoder](kernel-libraries.md#cpio-decoder) | `kernel/libs/cpio-decoder` | 0 | 宿主 test |
| [device-id](kernel-libraries.md#device-id) | `kernel/libs/device-id` | 0 | 内核 ktest |
| [dma-pool](kernel-libraries.md#dma-pool) | `kernel/libs/dma-pool` | 0 | 内核 ktest |
| [fdt-util](kernel-libraries.md#fdt-util) | `kernel/libs/fdt-util` | 0 | 内核 ktest |
| [io-util](kernel-libraries.md#io-util) | `kernel/libs/io-util` | 0 | 内核 ktest |
| [jhash](kernel-libraries.md#jhash) | `kernel/libs/jhash` | 0 | 宿主 test |
| [keyable-arc](kernel-libraries.md#keyable-arc) | `kernel/libs/keyable-arc` | 0 | 宿主 test |
| [logo-ascii-art](kernel-libraries.md#logo-ascii-art) | `kernel/libs/logo-ascii-art` | 1 | 宿主 test |
| [ring-buffer](kernel-libraries.md#ring-buffer) | `kernel/libs/ring-buffer` | 0 | 内核 ktest |
| [sparse-id-alloc](kernel-libraries.md#sparse-id-alloc) | `kernel/libs/sparse-id-alloc` | 0 | 内核 ktest |
| [short-vis-path](kernel-libraries.md#short-vis-path) | `kernel/libs/short-vis-path` | 1 | 宿主 test |
| [typeflags](kernel-libraries.md#typeflags) | `kernel/libs/typeflags` | 0 | 宿主 test |
| [typeflags-util](kernel-libraries.md#typeflags-util) | `kernel/libs/typeflags-util` | 0 | 宿主 test |
| [xarray](kernel-libraries.md#xarray) | `kernel/libs/xarray` | 0 | 内核 ktest |
