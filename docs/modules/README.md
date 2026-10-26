# 当前模块开发与技术交接

本页与 [catalogue.json](catalogue.json) 面向当前 checkout。它们补充
[10-22 固定文档审计](../agents/MODULE_DOCUMENTATION_AUDIT.md)，不改写历史清点、
原始收据或运行计数。模块有实质手册和链接有效，分别是文档事实；构建、原 owner
授权、实际设备效果和持久恢复仍需本轮实际执行。当前跨仓来源以
[SOURCES](../SOURCES.md#hepta-native-organ) 和实际 Cargo lock 为准。
当前 Desktop/Hepta 依赖装配、两份 lock 与来源检查命令见
[DEPENDENCIES](../../support/ui/DEPENDENCIES.md)；此前固定组合保留其历史资格。

## 产品与支持模块

以下覆盖全部 **15 个第一方 Cargo package、1 个 UI virtual workspace**。每个入口
都有本模块的职责、实际源码、构建/验证方式及错误或恢复边界；共享规范保持一份，
避免多份技术合同漂移。机器目录另列各模块的原 owner、失败恢复与当前范围。

| 模块 | 就近开发入口 | 技术合同 | 主要交接点 |
| --- | --- | --- | --- |
| HOS2 codec | [os-abi](../../libs/os-abi/README.md) | [NATIVE_ABI](../NATIVE_ABI.md) | 有界 wire、独立 golden、profile 与权限分开 |
| 控制状态核心 | [os-control](../../libs/os-control/README.md) | [API_CONTRACT](../../libs/os-control/API_CONTRACT.md) | 原资源 owner、CAS、delivery、连续退役与不确定结果 |
| Hepta 观察与有限 transport | [hepta-os](../../services/hepta-os/README.md)、[RUN](../../services/hepta-os/RUN.md) | [CONTRACT](../../services/hepta-os/CONTRACT.md)、[Objective](../../services/hepta-os/OBJECTIVE_TRANSPORT.md)、[history](../../services/hepta-os/OBJECTIVE_HISTORY.md)、[CPU](../../services/hepta-os/CPU_DELIVERY.md) | 默认只读、可信端点、一次尝试、原 history 回查 |
| 原 Hepta host 接合 | [hepta-session-host](../../services/hepta-session-host/README.md) | [原文本会话](../../services/hepta-session-host/TEXT_SESSION.md) | 原 writer、Root 认证、永久 send fence、同身份恢复 |
| UI 共同模型与支持工具 | [support/ui](../../support/ui/README.md) | [BOUNDARIES](../../support/ui/BOUNDARIES.md)、[接合合同](../../support/ui/INTEGRATION_CONTRACTS.md) | 进程/显示/权限投影与真实平台 owner 分开 |
| 设备生命周期模型 | [device_lifecycle](../../support/vmm/device_lifecycle/README.md) | [VMM gates](../../support/vmm/GATES.md) | 撤销/静止/复位顺序，真实 DMA/IOMMU 尚需适配 |
| Rust UI workspace | [ui](../../ui/README.md) | [接合合同](../../support/ui/INTEGRATION_CONTRACTS.md) | 五成员、工具链、features/lock/资源组合 |
| UI 类型、wire 与 Notes store | [core](../../ui/core/README.md) | [Notes 持久性](../../support/ui/NOTES_DURABILITY.md) | 精确身份、独占 incarnation、同步存储与回读 |
| 进程及 UI 会话 | [session](../../ui/session/README.md) | [Objective bridge](../../ui/session/OBJECTIVE_BRIDGE.md)、[submission](../../ui/session/OBJECTIVE_SUBMISSION.md) | reap/generation、单连接期限、真实 Notes 预留/激活 |
| 原生 Rust 展示 | [shell](../../ui/shell/README.md) | [freshness](../../ui/shell/OBSERVATION_FRESHNESS.md)、[Makepad](../../support/ui/NATIVE_MAKEPAD.md) | egui/原 Makepad、原 ChatWorkspace、草稿与操作恢复分开 |
| 应用窗口及恢复 helper | [app-window](../../ui/app-window/README.md) | [Notes organ](../../support/ui/NOTES_ORGAN.md)、[durability](../../support/ui/NOTES_DURABILITY.md) | worker 串行编辑、落盘、独立回读、旧 incarnation 恢复 |
| admission 与私有目的端 | [broker](../../ui/broker/README.md) | [Notes organ](../../support/ui/NOTES_ORGAN.md) | 有限会话、双通道 bootstrap、失联不重发 |
| 下游 no_std fixture | [backend_no_std](../../tests/control/backend_no_std/VALIDATION.md) | [API_CONTRACT](../../libs/os-control/API_CONTRACT.md) | 公共 backend/handle 编译契约与 !Send guard |
| 并发调度验证 | [Loom](../../tests/control/loom/README.md) | [control validation](../../tests/control/VALIDATION.md) | 原模块 staging、公共 backend、保留失败 interleaving |
| UI 验证层 | [tests/ui](../../tests/ui/README.md) | [TESTPLAN](../../tests/ui/TESTPLAN.md) | 纯模型、真实进程、compositor/输入及实机范围 |
| Linux Rust/Tokio probe | [workload](../../tests/workloads/linux/rust/README.md) | [Linux ABI](../LINUX_COMPATIBILITY.md) | threads/UDS/fs/tasks、精确 guest ELF 与失败清理 |

## 跨模块开发领域

没有 Cargo manifest 的构建、兼容、设备和交付代码同样需要具体开发资料。下表保留
A00–A10 职责；`catalogue.json` 管理实际 Rust 入口，不能用 package 数代替产品范围。

| 领域 | 开发与技术入口 | 需要记录的失败或未闭合范围 |
| --- | --- | --- |
| A00 跨仓组合与发布 | [release profile](../agents/ORGAN_RELEASE_PROFILE.md)、[PRODUCT](../../support/ui/PRODUCT.md) | 相同源码/lock/资源；安装升级回滚不转授原生产 grant |
| A01 源码、构建与启动 | [build](../../support/build/README.md)、[strict ktest](../../support/build/ktest/README.md)、[57 成员手册](kernel-workspace/README.md) | 原工具链/ELF/feature；完整分母、raw exit、超时与过滤 |
| A02 HOS2 | [codec 入口](../../libs/os-abi/README.md)、[验收](../../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md) | malformed wire 与原生 profile 权限分别验证 |
| A03 控制模型 | [API](../../libs/os-control/API_CONTRACT.md)、[开发](../../libs/os-control/README.md) | 未知 callback、namespace loss、history fence 与锁适配 |
| A04 Linux ABI/rootfs/存储 | [Linux](../LINUX_COMPATIBILITY.md)、[rootfs](../../support/rootfs/README.md)、[SQLite 重启](../../tests/workloads/linux/SQLITE_GUEST_RESTART.md) | 本次精确 guest ELF、文件系统写回/重启失败；Agentd 全栈另验 |
| A05 内核控制 | [handoff](../agents/handoffs/A05_KERNEL_CONTROL.md)、[G1-c](../agents/G1C_TRUSTED_OBSERVE_PROFILE.md)、[G1-d](../agents/G1D_TRUSTED_CONTROL_PROFILE.md) | ordinary/G1-c/G1-d、实际受信映像、copyout 与权限生命周期 |
| A06 CPU/内存及有限恢复 | [CPU owner](../ASTERINAS_CPU_OWNER_G1A.md)、[内存 admission](../agents/CGROUP_MEMORY_ADMISSION.md)、[watchdog](../agents/G1D_WATCHDOG.md) | 原 scheduler/accounting owner；SMP、物理保留与全局恢复分别验 |
| A07 Hepta 原链接合 | [observer](../../services/hepta-os/README.md)、[host](../../services/hepta-session-host/README.md)、[文本](../../services/hepta-session-host/TEXT_SESSION.md) | 原 writer/checkpoint/Root 认证；unknown 不补发 |
| A08 Android | [开发](../../support/android/README.md)、[device adapter](../../support/android/DEVICE_ORGAN.md)、[严格 receiver](../../support/android/receiver/README.md)、[兼容规格](../ANDROID_COMPATIBILITY.md) | host 只读、receiver 构建/签名、真实设备/窗口与生产效果资格分开 |
| A09 硬件与 VMM | [硬件技术](../HARDWARE_AND_DRIVERS.md)、[平台决策](../../support/hardware/DECISION.md)、[运行](../../tests/hardware/RUN.md)、[gates](../../support/vmm/GATES.md) | inventory/模型与实际 DMA/IOMMU/IRQ/复位分开 |
| A10 原生 AI UI/Notes | [UI](../../ui/README.md)、[原文本](../../services/hepta-session-host/TEXT_SESSION.md)、[Notes](../../support/ui/NOTES_DURABILITY.md)、[产品](../../support/ui/PRODUCT.md) | 渲染不拥有授权；保存与原 owner 终态分开，崩溃后按原身份回查 |

## 57 个主内核成员

[kernel-workspace](kernel-workspace/README.md) 按全部显式 members 提供三册逐 crate
手册；每条包含职责/接口、状态/所有权/失败边界、开发/回归及当前验证缺口，并连接
自己的 manifest 和入口源码。该形式为 vendored 内核提供本项目具体交接，不向每个
上游目录复制一份相同 README。底层库不签发 Hepta grant；其调用者必须落实各条目
列出的值域、设备、内存或权限检查。

原 inventory 的 commit/hash 仍保持其不可变快照语义；本轮检查直接读取当前 manifest、
各条目和链接，不把历史 `source_commit` 归为未提交源码。独立 OSDK/comp-sys、上游
book 示例与测试 fixture 不计入这 57 成员，其维护说明由
[上游 Book](../../kernel/asterinas/book/src/SUMMARY.md) 和
[OSDK](../../kernel/asterinas/osdk/README.md) 提供。

## 可机器复核的交接要求

从仓库根目录运行（仅 Python 标准库，不联网）：

```sh
python3 -I -B support/docs/check_modules.py --report /tmp/trill-module-docs.json
python3 -I -B -m unittest discover -s support/docs -p 'test_*.py'
```

[检查器](../../support/docs/check_modules.py) 将 Git 跟踪和未忽略的新 Cargo manifest
与目录逐项比对，排除内核、results/evidence 和 target；校验包名、具体 owner/恢复/范围、
开发与技术文档，读取当前内核 members 逐条检查四项合同与本模块源码链接，并验证
11个跨模块领域的真实源码/交接合同，以及这些入口文档中的直接本地文件及
Markdown 标题锚点。报告给出实际输入 SHA256 和
工作树是否有变动；`execution_evidence=false` 明确表示没有执行其中的构建/运行命令。
外部 URL 不访问、链接不递归展开、一般 Rust/JSON 的代码锚点不解释。

修改模块时同时更新实际手册与目录。新增 Cargo 模块未建映射、旧模块名/路径变化、
删除一条内核合同或留下坏锚点都应失败。检查通过仍需执行本次改动对应的原测试，
记录真实工具链、源码组合、失败/忽略及范围。不要用标题、模板、历史测试数字或
架构图代替具体实现和验收。
