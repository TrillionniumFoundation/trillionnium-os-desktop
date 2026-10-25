# A06 — 真实 CPU 调度与资源计费

**分支：** agents/A06-scheduler-budget  
**启动批次：** 第二批 G0/G1 接口具备后  
**目录所有权：** kernel/asterinas/kernel/core/src/sched/**；tests/kernel/scheduler/**；需碰 OSTD/进程公共文件时交 A00 协调  
**依赖：** A01 可启动，A05 提供进程 ResourceDomain 接口  
**可验收产物：** 真实单 CPU 配额与恢复节流

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/CURRENT_CAPABILITIES.md、docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。现有 Rust codec/control core、ordinary QueryAbi、G1-c/d 实验与接续候选的实现及资格按 docs/CURRENT_CAPABILITIES.md 和各自固定源码/证据读取，不把候选实现或历史测试自动当作当前 main 已验收。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；默认 Hepta 原合同保留 f8c9419df6ddeb36ff8b522a50219981fb8d9345；新的跨仓部署组合由 A00 通过 source profile 显式固定，不能覆盖历史合同或拼接各分支资格。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 保留为受版本管理的普通文件，允许维护项目导航，不得改成符号链接。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A06 Asterinas CPU ResourceDomain Agent。固定 N0 一颗 vCPU、100ms 周期、max cap 非保底；不要只改 sched_class/fair.rs。审阅 ClassScheduler 的 stop/real_time/fair/idle 公共路径、tick/update/block/exit 和 TSC 单位，选择统一的可运行资格/计费钩子。受控任务不得通过 FIFO/RR/其他 Linux 调度接口逃过限额；如果某类暂不支持，明确拒绝切换。
设计实现 ResourceDomain 与父域合计记账（不双计）、窗口原点、u64 溢出、降额后 consumed>cap 合法、同值更新不充值、当前运行中的计费结算。raw TSC tick 不等于纳秒，使用上游可验证的时钟换算；被节流的任务无需发 syscall，也能由独立 timer 在新周期唤醒。父域耗尽、cap=0、短量子/长不可抢占、线程退出、突发跨窗口分别实测。
严格保留内核 stop/idle 和受保护恢复域的必要运行路径，明确其计费豁免范围但不允许普通应用伪装此身份。与 A05 对接的 API 只用于原子 InstallBudget CAS、ReadUsage 同版本快照、可信恢复调整。不要自行修改 wire；需要新的节流原因数据先提交证据给 A00 而不是加未知字段。
验收：同一真实新内核中的 CPU-bound 负载呈现可测预算、父域约束与节流生效；报告偏差/超支窗口、延迟、调用命令与串口日志。仅单元模型结果不得标为 kernel scheduler 通过。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~

## 后端审计补充（本次真实客体观测）

先读 ../../ASTERINAS_ORGAN_BACKEND.md。固定Asterinas客体cpu.max=1000/100000读回成功后，约1秒内仍耗CPU998ms。已有CPU统计值得复用，但weight/max未真正执行；memory属性也不能算已有强制上限。使用tests/organ_backend的失败基线，补同一资源机制的实际计费、节流、唤醒及多入口一致性，不包装未执行配置假报通过。
