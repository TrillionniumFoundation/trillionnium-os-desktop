# A03 — 资源控制状态机与对抗测试

**分支：** agents/A03-control-core  
**启动批次：** 第一批立即  
**目录所有权：** libs/os-control/**；tests/control/**（不拥有 tests/golden 和 wire 定义）  
**依赖：** 可独立开发；与 A02 共用约定而非共改格式  
**可验收产物：** 可在宿主机执行的恢复与配额核心逻辑

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/CURRENT_CAPABILITIES.md、docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。现有 Rust codec/control core、ordinary QueryAbi、G1-c/d 实验与接续候选的实现及资格按 docs/CURRENT_CAPABILITIES.md 和各自固定源码/证据读取，不把候选实现或历史测试自动当作当前 main 已验收。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；默认 Hepta 原合同保留 f8c9419df6ddeb36ff8b522a50219981fb8d9345；新的跨仓部署组合由 A00 通过 source profile 显式固定，不能覆盖历史合同或拼接各分支资格。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 保留为受版本管理的普通文件，允许维护项目导航，不得改成符号链接。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A03 HOS2 资源控制核心 Agent，做不依赖内核的 Rust 参考核心与可测试状态机，不写另一个长期业务数据库。严格保留 HOS2 中逻辑 K 属于现有 Hepta owner、内核 D 属于本次 boot/CapSpace 的边界。实现抽象的能力空间 D 预约、跨目标唯一性、序列窗口、结果发布、QueryDelivery、RetireThrough、授权和撤销交错、权限/结果独立、预算 revision CAS 与不充值的单 CPU 计费原语。所有时间/计费使用显式受检单位。
优先覆盖上一轮规格模型没有捕获的缺口：同 sequence+target 但不同 cap/revision 必须 conflict；错误发布者不得提交 reserved；先占 seq1 不终结而后续终局会堵塞连续退役；满窗口仍可只读查询/有效退役；外部 owner 的“持久 ack”与单纯调用者布尔量不同；seq 退役以后迟到请求只能被拒绝。至少测试 10,000 次有界循环，再专门测试悬挂前缀、重启后的 history_lost、重新建立空间和代际隔离。
状态机对并发的结论不能由单线程测试冒充；有条件使用线程交错/loom 或其他可复现并发测试，锁、原子可见性和 owner fencing 明确验证。没有真实内核测试则标为 host model。不要改 ABI 字节字段，输出 Rust API 契约供 A05/A06 使用。
验收：可运行 Cargo 测试、命名的负向测试与状态不变量、最小 API 契约，附真实通过/失败数。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~
