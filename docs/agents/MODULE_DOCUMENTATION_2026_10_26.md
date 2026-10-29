# 模块文档补充审计：2026-10-26

本补充清点绑定 Desktop 代码 `d3ae4b9a8bbf8adc9712d2d2fc5328915db66642`
（tree `5b84041ddd467ecc14f3991d139197941c0c46c3`）与只读核对的原 Hepta
`fef6a641228aad80b2716db05c7f265adf6511d7`（tree
`88f0bcfd1a55002d1e6e0f5002e67b905639e4d4`）。本次只增补文档与导航，未编译、运行
Rust、guest 或 GUI；下表引用的是先前实际收据，不把文档提交改记为已执行的代码版本。
[2026-10-22 审计](MODULE_DOCUMENTATION_AUDIT.md)及其原始矩阵保持不变。

结论是：A00–A10 均有可定位的实质技术内容和开发／验证入口；不少模块依赖共享手册。
**不能说每个 crate 都有独立、完整的开发手册和技术手册，也不能用文件存在证明功能完成。**
本次细读重点是调度权限／继承、Binder D1、Session／Notes、原 Root 装配和发布 owner。
其余模块核对入口及既有边界；上游全部 crate 和 Hepta 全部技术指南未获逐项语义审查通过。

## 资格必须按来源分开

可移植的[白名单收据摘要](../../results/goal-progress/2026-10-26-public-summaries/MODULE_DOCS_EVIDENCE.json)
仅含源码身份、计数、布尔和原收据哈希，不含配置、私钥、SQL、磁盘或完整载荷。

| 范围 | 实际来源与结果 | 不能外推的结论 |
| --- | --- | --- |
| 接收组合内核 | Desktop `d3ae4b9a`：20 组通过，Core 348/348，无过滤或跳过；普通产品、Binder、P1/P2/P3、affinity、FAIR、IPC、page、stop、seccomp、Unix47/shutdown131 在各自明确 CPU 配置下运行。7999 个跟踪文件逐步前后一致。 | Core 的独立 ktest ELF 与普通产品 ELF 分开；探针／断言计数不是全产品测试数。 |
| Linux host 版本组合 | Desktop `85425721e1f13e7f3e91911cc851c4d6fb602164`／Hepta `fef6a641…`：host 步骤通过，13 个原 owner 包执行 1709 项测试、54 项显式跳过。 | 不是 `d3ae4b9a` 的新 host source-pair 资格；1709 是 Hepta owning tests，不是 UI 全部测试的总数。 |
| 隔离真实 UI | 同一 `85425721`／`fef6a641`：Notes roundtrip、Notes crash/reopen、X11 三项选定测试通过。 | 使用独立测试 issuer/current-cut 输入；不是现役生产授权、通用应用业务完成、Asterinas 显示或手机资格。 |
| 原生原 owner | Hepta `fef6a641…`／Desktop kernel `5292faf2aa148304b1f2a544294878f339822e69` 的严格运行失败。Root 在 owner/frontier 初始化的进程凭据条件校验处拒绝。 | 具体失败字段、两次进程检查中的哪一次仍未证实；不能把后续 PeerDenied/init panic、警告或静态猜测写成确因。native、跨重启持久闭环和生产资格仍为 false。 |

本地 host／GUI 通过不代表全部 CI 或 CodeQL 通过；Hepta `fef6a641` 的 aggregate CodeQL 仍有失败调查，不能回填为绿色。

`d3ae4b9a` 没有整合另支 W2/W3/强制迁移；本补充也不修改 source map、current manifest 或生产配置。
普通内核默认权限与显式 native profile 必须分别读其合同。主任务后续的新接收树／发布清单须重新绑定真实运行。

## A00–A10 的实质覆盖与缺口

“共享覆盖”表示下列文件确有 owner、状态／错误边界和开发入口，不表示每个源码目录有双手册。
[机器摘要](MODULE_DOCUMENTATION_2026_10_26.json)列出同一来源、代码路径与覆盖分类。

| 模块 | 技术契约 | 开发／构建／验证入口 | 剩余边界 |
| --- | --- | --- | --- |
| A00 集成 | [发布组合契约](../../support/release/README.md)、[架构](../ARCHITECTURE.md) | [check_organ_pair.py](../../support/release/check_organ_pair.py)、[release tests](../../support/release/test_check_organ_pair.py) | source-only、host、GUI、native 分层；文档不完成新发布清单或七项生产输入。 |
| A01 上游／启动 | [构建手册](../../support/build/README.md)、[上游 Book](../../kernel/asterinas/book/src/SUMMARY.md) | [ktest 手册](../../support/build/ktest/README.md)、[source verifier](../../support/build/verify-source.py) | 复用上游／派生共享文档；旧手册数字保留其历史来源。 |
| A02 HOS2 codec | [包入口](../../libs/os-abi/README.md)、[ABI](../NATIVE_ABI.md) | [独立样本验收](../../tests/abi/run_acceptance.py) | 五种 wire 格式可解析，不代表 ordinary 产品开放五种效果。 |
| A03 control core | [API 合同](../../libs/os-control/API_CONTRACT.md) | [验证手册](../../tests/control/VALIDATION.md)、[no_std](../../tests/control/backend_no_std/VALIDATION.md) | host/Loom 模型、内核执行与原 Hepta 磁盘持久化分别验收；Loom 没有专属完整手册。 |
| A04 Linux／存储 | [Linux 缺口](../../compat/linux/GAPS.md)、[SQLite restart](../../tests/workloads/linux/SQLITE_GUEST_RESTART.md) | [rootfs](../../support/rootfs/README.md)、[Linux workload](../../tests/workloads/linux/README.md) | SQLite 或 ABI 通过不等于原 Agentd 启动成功；Tokio 小 workload 仍用共享说明。 |
| A05 权限／映像 | [Process image](../ASTERINAS_PROCESS_IMAGE_G1C.md)、[安全增量](../../support/kernel-safety/README.md) | [普通控制 gate](../../tests/kernel/control/README.md)、[安全 probe](../../tests/kernel/safety/README.md) | same-identity capability、进程映像和 trusted profile 按实际原门禁约束；MAC 管理入口不在本阶段。 |
| A06 调度／隔离 | [P2/P3 调度权限与继承](../../support/kernel-safety/SCHEDULING_PERMISSIONS.md)、[FAIR](../../support/kernel-safety/FAIR_RUNTIME.md)、[page budget](../../support/kernel-safety/PAGE_MEMORY.md) | [P1](../../tests/kernel/sched-policy-auth/README.md)、[P2](../../tests/kernel/sched-policy-limits/README.md)、[P3](../../tests/kernel/priority-inheritance/README.md)、[IPC budget](../../tests/kernel/ipc-memory/README.md) | `hepta.anon.*` 是有限物理页接口，非完整 `memory.max`；`cpu.weight` 写入拒绝，未实现组权重调度。 |
| A07 原 Hepta owner | [适配器合同](../../services/hepta-os/CONTRACT.md)、下节原库导航 | [适配器运行](../../services/hepta-os/RUN.md)、[13 owner 组合](../../support/release/README.md) | observer/history 不拥有原 writer 或签发权；原 Root 七项输入和真实部署另验。 |
| A08 Android IPC | [Binder A/B/C](../../support/android/BINDER_BYTES.md)、[实际线程 D1](../../support/android/BINDER_THREADS.md)、[seccomp](../../support/android/SECCOMP.md) | [Binder probe 手册](../../tests/kernel/binder/README.md)、[Android 入口](../../support/android/README.md) | D1 是 8 参与者／16 事件／16 缓冲的手动同步 IPC；自动线程池、nested/oneway、FD arrays、Android boot/CTS/SELinux/BSP 仍缺。 |
| A09 硬件／GPU／VMM | [硬件合同](../HARDWARE_AND_DRIVERS.md)、[DMA domains](../../support/kernel-safety/DMA_DOMAINS.md)、[VMM gates](../../support/vmm/GATES.md) | [硬件 runbook](../../tests/hardware/RUN.md)、[lifecycle 模型](../../support/vmm/device_lifecycle/README.md) | 限定 requester/topology 测试、共享页表或枚举不证明所有设备 DMA 隔离；GPU/reset/手机实机未完成。 |
| A10 Session／Notes | [Session 整帧期限](../../support/ui/SESSION_IPC.md)、[文档原子持久化／恢复](../../support/ui/NOTES_PERSISTENCE.md)、[X11](../../support/ui/DESKTOP_X11.md) | [UI workspace 导航](../../ui/README.md)、[host runbook](../../support/ui/RUN.md) | 五包有具体职责入口并共享手册；新建／可信重开与通用文件选择器不同，receipt ACK 不替代原 owner 终态。 |

P2/P3 的同一短锁快照服务策略查询、nice 和 proc stat；clone 只把快照装入新、未发布的调度属性。
技术文档明确 target Process／namespace 权限、RLIMIT、部分成功和错误语义。D1 明确真实 Thread
身份、退役钩子、回程预留、失败退款及 prepared EFAULT 的单槽阻塞，不能宣传为完整自动线程池。

Session 把整个输入帧限制为 500 ms，而不是每次读取续期；至多 32 条连接，每 tick 有界推进。
Notes 将文本、revision 与精确应用回执一起 file-sync／rename／directory-sync 后才返回 Applied；
失败后 writer 中毒，须显式重开观察，不能据超时自动重发。原 Hepta 在自己的 SQLite 终态和 Root
Current 得到确认后才退役应用回执。三者属于不同状态 owner，不能用一张操作回执替代已保存文档。

## 实际 Cargo 清点

使用固定 Git 的跟踪文件和 TOML 解析，排除 `target`、`results`、`evidence`、`outputs` 等历史／生成副本。
没有运行 Cargo metadata 或依赖解析，因此 workspace 数字指**显式成员模式展开**，不是解析后的依赖闭包。
完整逐 manifest 机器清单留在本次任务证据中，最终输出由主任务汇总。

| 清点 | 结果与解释 |
| --- | --- |
| Desktop 自有入口 | 15 份 manifest：14 个 package 和 1 个 UI virtual workspace。包括测试／support crate，不全是产品模块。 |
| Desktop 上游派生 | 112 份 manifest；含 Asterinas、OSDK、测试／模板工具的多个 workspace。总计 127 份 manifest：118 个 package、8 个 virtual workspace、1 个有意不完整的测试 fixture。已排除 14 份历史副本。 |
| 主 workspace | Asterinas 根显式 57 成员，UI 显式 5 成员；上游另外的示例／测试 workspace 不能算新产品领域。 |
| Hepta | 204 份 manifest、203 个 package、1 个 virtual workspace；`codex-rs` 显式 187 成员。40 个注册模块有 40 份技术指南，51 条 Cargo 归属绑定都能定位到实际 manifest。 |
| Hepta 补充范围 | browser worker 和两个 fuzz manifest 未落在这 51 条绑定里；不能把命名统计直接升级为所有权结论或全部包完整手册资格。40 指南仅核结构／导航，未逐篇完成语义／API 一致性审查。 |

自有包使用实质共享文档的对应关系：

| 入口 | 实质手册与仍缺内容 |
| --- | --- |
| `libs/os-abi`／`libs/os-control` | ABI 包 README／共享 ABI；control API_CONTRACT＋tests/control/VALIDATION。control 无独立双手册，API 合同不能替代全部实际后端运行说明。 |
| `services/hepta-os` | README、RUN 与 transport/history/CPU 专册；生产部署输入与 native 失败另列。 |
| `support/ui`／`tests/ui` | UI integration/边界／TESTPLAN；为模型与契约测试，不自产生 GUI 或授权资格。 |
| `support/vmm/device_lifecycle` | 有操作／拒绝／资源／构建合同，仍是 no_std 模型，非实际驱动。 |
| `tests/control/backend_no_std`／`tests/control/loom` | 共享 control 验证；Loom 依赖真实 run-models 工作流，旁置 README 缺口保留。 |
| `tests/workloads/linux/rust` | 共享 Linux/rootfs runbook；小 Tokio package 没有独立故障恢复手册。 |
| `ui` 的 5 成员 | 五个 README 均有具体源文件职责、权限边界和包测试入口；Session/Notes/交互协议仍共享专册，未为每包复制两份手册。 |

上游组件的 `kernel/asterinas/kernel/comps/README.md` 仍只是标题；不少底层 crate 没有旁置文档。
共享 Book 和 crate 注释可作架构／API 入口，但实际接合硬件前仍需对应设备、owner、锁序、失败恢复和
硬件验收手册。目录内有 Markdown、字数或 README 数量都不作完整度百分比。

## 原 Hepta 的 Root 与 13 owner 入口

以下路径均相对原 Hepta 仓库根，固定到 `fef6a641…`，本次未跨库修改。
需在保有该 Git 对象的原库 checkout 中读取；不假设此本地候选已有可访问的公开 blob URL。
模块总导航（`docs/modules/README.md`）
解释注册模块、共享实现要求和开发验证边界。发布工具的 13 个 owning packages 是执行依赖闭包，
不是另建 13 个顶层模块，也不是 13 个独立权限 owner。

| 实际 owning package | 技术／开发入口（原库固定版本） |
| --- | --- |
| `codex-hepta-agentd` | ROOT_COMPOSITION（`codex-rs/hepta-agentd/ROOT_COMPOSITION.md`）、ROOT_LAUNCH（`codex-rs/hepta-agentd/ROOT_LAUNCH.md`）、Notes（`codex-rs/hepta-agentd/NOTES_DURABLE_ORGAN.md`）、native runbook（`codex-rs/hepta-agentd/NATIVE_OWNER_QUALIFICATION.md`） |
| `codex-hepta-contracts` | FinalUse（`codex-rs/hepta-contracts/FINAL_USE.md`）、Root contracts（`codex-rs/hepta-contracts/ROOT_CONTRACTS.md`） |
| `codex-hepta-memory` | Current publication（`codex-rs/hepta-memory/ORIGINAL_CURRENT_BOUNDARIES.md`）、SQLite（`codex-rs/hepta-memory/LANE_C_SQLITE.md`）、Root checkpoint（`codex-rs/hepta-memory/ROOT_CHECKPOINT.md`） |
| `codex-hepta-cognitive-store` | cognitive.store 技术指南（`docs/modules/cognitive.store/TECHNICAL.md`）与production closure（`docs/modules/cognitive.store/PRODUCTION_CLOSURE.md`）为共享模块说明，包内无独立 Markdown 手册。 |
| `codex-state` | 原 state 源入口（`codex-rs/state/src/lib.rs`）和 Root pool/commit-hook 合同（`codex-rs/hepta-agentd/ROOT_SERVICE.md`）；数据库包完整独立运维手册缺口保留。 |
| `codex-hepta-agent-protocol` | 原 wire 源入口（`codex-rs/hepta-agent-protocol/src/lib.rs`）＋Objective history（`codex-rs/hepta-agentd/OBJECTIVE_HISTORY.md`）；没有包专属双手册。 |
| `codex-hepta-learning-ledger` | DURABLE（`codex-rs/hepta-learning-ledger/DURABLE.md`）、LOCK_OWNERSHIP（`codex-rs/hepta-learning-ledger/LOCK_OWNERSHIP.md`）、INSPECTION（`codex-rs/hepta-learning-ledger/INSPECTION.md`） |
| `codex-git-utils` | 包 README（`codex-rs/git-utils/README.md`）说明 baseline/reset/diff API；不是完整生产运维手册。 |
| `codex-hepta-memory-extension` | 原扩展入口（`codex-rs/ext/hepta-memory/src/lib.rs`）＋runtime.codex 共享指南（`docs/modules/runtime.codex/TECHNICAL.md`）；扩展包无独立完整手册。 |
| `codex-hepta-automation` | TaskFlow 技术指南（`docs/modules/automation.taskflow/TECHNICAL.md`）与实际 store/migrations/tests 共享覆盖；包内无独立 Markdown 手册。 |
| `codex-hepta-fleet` | Fleet 技术指南（`docs/modules/runtime.fleet/TECHNICAL.md`）；immutable bundle 的运行与回归从发布工具源角色进入，包内无独立 Markdown 手册。 |
| `codex-hepta-supervisor` | Supervisor 指南（`docs/modules/runtime.supervisor/TECHNICAL.md`）、恢复与资格（`docs/modules/runtime.supervisor/RECOVERY_AND_QUALIFICATION.md`） |
| `codex-arg0` | 原 helper/runtime dispatcher（`codex-rs/arg0/src/lib.rs`）及 owning tests；缺少完整包级开发手册，不用返回成功或空 native path bundle 代替真实 helper 初始化。 |

五条私有 Root lane、真实 pidfd、原 issuer/revocation、受保护时钟、独立 consumer frontier 与
完整 SQLite Current／writer proof 属于原 Root service 合同（`codex-rs/hepta-agentd/ROOT_SERVICE.md`）。
本地摘要、Session 同 UID、fixture issuer 或文档齐备均不能替代七项生产输入的可信来源。

## 本次补充与后续缺口

本次新增此审计、机器摘要及 UI workspace 入口，修正 Binder 当前线程范围，补原 owner／调度导航。
原始证据、旧审计及旧 outputs 不重写。检查限于本地文件／锚点、固定原库路径、代码与命令入口、
JSON 和 diff；外部站点可达性、每个 Rust API 的语义一致性、全部 crate 专属手册、实际新构建均未补证。
后续应先补将要实际接合的驱动／部署 owner 的故障恢复与运维内容，再扩大实现和验收，不能靠空 README 凑完成率。
