# A04 — Linux ELF 与 Hepta 依赖基线

**分支：** agents/A04-linux-hepta-baseline  
**启动批次：** 第一批立即  
**目录所有权：** compat/linux/**；support/rootfs/**；tests/workloads/linux/**  
**依赖：** 可独立开始；为 A07 提供 W1/profile  
**可验收产物：** 真实 ELF 依赖和兼容缺口清单

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/CURRENT_CAPABILITIES.md、docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。现有 Rust codec/control core、ordinary QueryAbi、G1-c/d 实验与接续候选的实现及资格按 docs/CURRENT_CAPABILITIES.md 和各自固定源码/证据读取，不把候选实现或历史测试自动当作当前 main 已验收。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；默认 Hepta 原合同保留 f8c9419df6ddeb36ff8b522a50219981fb8d9345；新的跨仓部署组合由 A00 通过 source profile 显式固定，不能覆盖历史合同或拼接各分支资格。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 保留为受版本管理的普通文件，允许维护项目导航，不得改成符号链接。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A04 Linux 用户态兼容 Agent。先不要从零重写 Linux syscall。固定 Hepta commit f8c9419df6ddeb36ff8b522a50219981fb8d9345，在可用的原 Linux 环境选一条真实可执行的 Agentd/Codex/App Server profile，明确完整 ELF、动态 loader、libc、SQLite WAL/锁、AF_UNIX、futex、epoll、文件系统、证书/NSS/DNS 等依赖；用实际 trace、调用结果与文件哈希建 W1 兼容 profile。
交付一个可复跑的静态/动态 ELF、Rust Tokio 和 SQLite 最小工作负载集，记录允许结果集合与异常用例；区分“程序启动”“真实调用”“持久写入和重启”。依赖缺失不能写成 ABI 已失败；上游宿主没有配置好也不能冒充内核问题。测试脚本只使用合成数据和可丢弃镜像。
不得私自修改 kernel/common ABI/Hepta 私库。A01 基线 QEMU 就绪后，在新内核复跑相同 ELF，按缺失 syscall、文件、权限、调度、应用自身前提分类。验收：真实构建/trace/回归基线；如果当前环境缺 provider 凭据，准确标明哪些路径用本地受控 provider 以及未跑的真实外部请求。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~
