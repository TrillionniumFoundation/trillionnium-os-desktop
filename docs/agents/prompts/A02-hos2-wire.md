# A02 — HOS2 no_std 编解码

**分支：** agents/A02-hos2-wire  
**启动批次：** 第一批立即  
**目录所有权：** libs/os-abi/**；tests/golden/**；tests/abi/**  
**依赖：** 不等内核；协议变化需 A00 批准  
**可验收产物：** Rust codec 与独立黄金样本互认

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/CURRENT_CAPABILITIES.md、docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。现有 Rust codec/control core、ordinary QueryAbi、G1-c/d 实验与接续候选的实现及资格按 docs/CURRENT_CAPABILITIES.md 和各自固定源码/证据读取，不把候选实现或历史测试自动当作当前 main 已验收。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；默认 Hepta 原合同保留 f8c9419df6ddeb36ff8b522a50219981fb8d9345；新的跨仓部署组合由 A00 通过 source profile 显式固定，不能覆盖历史合同或拼接各分支资格。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 保留为受版本管理的普通文件，允许维护项目导航，不得改成符号链接。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A02 HOS2 ABI 编解码 Agent。按 docs/NATIVE_ABI.md HOS2 major 2 minor 0 实现 no_std、无无关依赖的 Rust codec：32 字节 ioctl transport（只做字段，不调用内核）、64 字节 HOS2/HOSR header、五操作 QueryAbi/ReadUsage/InstallBudget/QueryDelivery/RetireThrough 的固定请求/响应布局，以及 status、长度、保留字节、ID、版本验证。对 opcode 3 的 16 字节 request_id 正确解释为低 8 字节有序 sequence 加高 8 字节全零。采用显式字节编解码，不依赖 Rust struct padding。
先修 tests/golden/hos2.json 的三个实际错误：read_usage_lowered_cap、install_budget_ok 和 query_delivery_terminal 的窗口用量比已过去时间更多，违反 N0 单 CPU 语义。保持合法的降 cap 后 consumed>cap 案例；提供独立可复现的 golden 生成器和机器可检查语义约束。
用独立黄金字节测试（不是只做自身 round-trip），建立 truncated/magic/minor/flag/reserved/payload/unknown opcode/overflow/序列高 8 字节/outer error response 等反例。专门做变异检查：把 cap 或 expected_revision 从同序列同目标请求里改掉，测试必须拒绝错误复用；报告测试是否真正抓住变异。协议当前有疑义先向 A00 提交准确 diff，不私改 HOS2 布局。
验收：cargo test --manifest-path libs/os-abi/Cargo.toml 与相应 golden/mutation 测试真实运行、0 失败，并提交源码而不是仅 Python 样本；没有 QEMU/驱动不可宣称系统调用或权限通过。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~
