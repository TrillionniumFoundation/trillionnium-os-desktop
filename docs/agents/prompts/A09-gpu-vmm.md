# A09 — GPU/NPU/VM 硬件路径

**分支：** agents/A09-gpu-vmm  
**启动批次：** 第一批立即（风险前置）  
**目录所有权：** support/hardware/**；support/vmm/**；tests/hardware/**  
**依赖：** 研究独立；驱动/真实 VM 接入需 A01、A05 与特定设备  
**可验收产物：** 选定一条有真实证据的加速路线

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。当前主干已经包含 Rust codec/control core、原生只读 QueryAbi 和实验 CPU 配额；其余 HOS2 操作、G1/G2 与设备资格仍以 docs/STATUS.md 的实际源码和证据为准。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；Hepta 固定 f8c9419df6ddeb36ff8b522a50219981fb8d9345，除非 A00 基于证据统一升级。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 必须保持严格 0 字节。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A09 GPU/NPU 与虚拟化 Agent，任务是消除硬件路线的不确定性，而不是新建三套平行驱动。结合项目可访问的实际设备，只读枚举一次候选目标（如有权访问的 AMD AI MAX 主机或 RTX 4060；没有就明确 unknown），记录设备ID、IOMMU、固件、用户态计算栈、队列/共享内存、同步、复位、授权要求。分别评估 Rust 原生驱动、受限设备服务域、Linux 驱动 VM，择一优先的最小路径并说明未选原因。
区分显示、软件图形、硬件图形、计算 API、本机模型执行和数值正确性。提出一组实际可运行的小矩阵运算/推理输入输出校验，测量发生在哪个 host/guest 内核。虚拟化分清 Intel VMX、AMD SVM、ARM EL2，不能因为 OSTD 上游有 VMX 例子就声称目标 AMD 可用。
只能用隔离实验/只读枚举；不得改动运行中的 H3、GPU 驱动、BIOS、功耗/热保护、主系统分区。没有硬件访问时交付可复现的接口探测命令和明确 blocker，不编造性能与支持状态。
验收：一份设备依赖闭包、最小驱动/VM 目标、可重跑代码或只读测试及真实证据；不得把 Linux GPU 结果冒充 Rust 内核原生 GPU 通过。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~
