# A07 — Hepta 原生操作与持久确认

**分支：** agents/A07-hepta-native  
**启动批次：** 接口前置可开始宿主测试，G1 后才做真实新内核路径  
**目录所有权：** services/hepta-os/**；tests/integration/hepta/**（Hepta 原仓库默认只读，必要修订另提小 PR）  
**依赖：** A02/A03 接口 + A04 W1 宿主 + A05/A06 真实入口  
**可验收产物：** 真正的 Hepta → OS 预算 → 持久结果闭环

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。当前主干已经包含 Rust codec/control core、原生只读 QueryAbi 和实验 CPU 配额；其余 HOS2 操作、G1/G2 与设备资格仍以 docs/STATUS.md 的实际源码和证据为准。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；Hepta 固定 f8c9419df6ddeb36ff8b522a50219981fb8d9345，除非 A00 基于证据统一升级。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 必须保持严格 0 字节。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A07 Hepta 原生集成 Agent。不能复制另一套 Agentd、Codex 执行主链或 SQLite 操作账本。在固定 Hepta commit 的实际 durable_model.rs / durable_store.rs / DestinationDedupeStore 与 ObjectiveStart 真实主链上，验证 scope_id、operation_id、expected_predecessor、destination、payload_digest、owner_generation 与 HOS2 的 K/D/资源 revision 分别如何映射。注意参考 OperationIntentV1 不等于 DurableOperationIntentV1。
先在原 Linux 的测试存储建立一个窄 adapter，支持相同准确意图重复请求、授权隔离、persistent K→D、实际 HOS2 客户端调用（内核未有时只做受控 host test 并明确标注）。真实内核 ready 后使用 A05 的控制设备和 A06 的预算，将响应与语义意图持久确认后再 RetireThrough；owner 接替需 fence 旧 history.ack，丢响应/结果冲突与沉默前缀不许假定零效果。
基于现有 Hepta 操作库实际测试 expected_predecessor 是否允许未决前驱，别凭名称宣布必须重构。当前状态恰好相同不是旧效果的历史证据；允许新授权绝对目标收敛但旧操作保持 unknown，不能将 irreversible I/O 套用该规则。测试 WAL 和 durable commit 的真实持久路径；只用 SQLite 假数据/单元测试不能宣称内核稳定。
验收：先准确提交可构建 host adapter+持久测试，之后在新内核完成 W1 真正执行、撤销、管理者退出、旧 K 不重放、历史只读查询/退役、独立服务继续运行的证据。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~

## 后端审计补充（真实 organ 宿主边界）

先读 ../../ASTERINAS_ORGAN_BACKEND.md。TrustedReadOnlyOrganV1禁止I/O、持有能力、启动工作或跨效果边界。系统快照在原owner采集；HOS写操作沿现有authority/operations与受限适配器执行，不能写进只读handle。无需另建organ宿主或业务账本。
