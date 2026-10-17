# A10 — Rust Wayland 桌面原型

**分支：** agents/A10-rust-desktop  
**启动批次：** 第一批立即（独立原型）  
**目录所有权：** ui/**；tests/ui/**；support/ui/**  
**依赖：** 宿主 Linux 原型独立；目标新内核集成在 G2 后  
**可验收产物：** 可运行的聊天式 Rust shell 与清晰的 compositor 边界

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。当前主干已经包含 Rust codec/control core、原生只读 QueryAbi 和实验 CPU 配额；其余 HOS2 操作、G1/G2 与设备资格仍以 docs/STATUS.md 的实际源码和证据为准。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；Hepta 固定 f8c9419df6ddeb36ff8b522a50219981fb8d9345，除非 A00 基于证据统一升级。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 必须保持严格 0 字节。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A10 Rust 原生桌面 Agent。按 docs/DESKTOP_UX.md，目标是聊天软件式 Shell（类似 Robrix 的任务/对话/应用工作区），不是把控制台当首页。用 Rust 制作可构建、可在可用 Linux/Wayland 测试主机运行的最小桌面 shell：对话/任务列表、应用卡片、控制台选项卡、真实任务状态与未知/部分效果区分。
把 shell 与 compositor/session 生命周期设计为两个隔离职责；Linux Wayland 客户端、按信任域隔离的 Xwayland 和 Android 全屏显示桥保留明确接口；初期可使用受控演示进程测试 UI，不声称完成 Android 合成或 GPU 显示。中文输入与焦点、窗口切换、剪贴板权限及进程重启是主要验收。不能用不可信窗口伪造系统权限提示，也不要请求全局键盘监控作为默认能力。
保持单一 Rust UI 主线，不引入 Node 作为主桌面运行时；不要为视觉效果先做大量假的交互按钮。需要真实 HOS2 状态接口时与 A02/A07 对齐，不独立发明授权协议。
验收：可编译 Rust UI、可运行的短 demo、shell 崩溃与 session 连接存活的真实结果或明确尚未具备的限制。Linux 宿主运行不算新内核桌面已通过。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~
