# A05 — 内核 CapSpace 与 HOS2 ioctl 接合

**分支：** agents/A05-kernel-control  
**启动批次：** 第二批 G0 之后  
**目录所有权：** kernel/asterinas/kernel/core/src/process/**、kernel/asterinas/kernel/core/src/syscall/ioctl.rs 及紧邻新 HOS 控制设备模块；tests/kernel/control/**  
**依赖：** A01 源码/启动 + A02 wire + A03 核心，A00 明确 API 才开始修改公共文件  
**可验收产物：** 真实新内核内的受限控制入口

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。此任务起始检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8。当前只有 HOS2 0.3 规格/顺序模型，无项目内核或 Rust ABI 实机验收。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；Hepta 固定 f8c9419df6ddeb36ff8b522a50219981fb8d9345，除非 A00 基于证据统一升级。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 必须保持严格 0 字节。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A05 新内核权限与 ioctl Agent。只有当 A00 确认 A01、A02、A03 的共享接口和源码位置后，才修改 Asterinas 的进程、FileLike、sys_ioctl 与启动/执行路径。复用上游 Task/VFS/文件对象，不建平行进程与文件系统。实现实际调用身份与 exec_epoch 的 CapSpace、可信 init 的最终 ELF 装载后激活受限 grant、控制 fd 同进程绑定、子进程/SCM_RIGHTS/exec 不能放大权限。
使用 A02 codec 与 A03 控制状态核心，实现 QueryAbi/QueryDelivery/RetireThrough 及 InstallBudget 的授权、预约、结果返回路径；实际预算更新调用 A06 唯一导出的 ResourceDomain 接口，不自己再写一个 scheduler。保证跨目标相同 D 不重复产生效果，结果缓存与 copyout EFAULT 顺序正确，revoked 后观察仍受真实历史权限限制；历史不能被调用者自报 ID 读取。统一设备别名、Linux root 和控制路径的权限界限。
和 A06 的唯一共享契约是 ResourceDomain 句柄、稳定对象 identity、revision CAS、ReadUsage 快照以及恢复内部回退钩子。你拥有进程和 ioctl 路径，A06 拥有 sched 目录，不互相覆盖。遇到锁序冲突，用最小源码示例提交给 A00。
验收：在真实 Asterinas QEMU 上跑非 AI 控制客户端，证明权限/版本/回复及进程退出；host-only mock 只能报部分完成。特别覆盖 fork/exec、旧 fd、copyout、序列退役、已撤销观察、重启旧句柄失效。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~

## 后端审计补充（本次真实客体观测）

先读 ../../ASTERINAS_ORGAN_BACKEND.md。HOS、cgroup与可信恢复不得拥有平行资源事实；cpu.max写入成功不证明调度执行。A05负责真实身份与对象入口，实际限额由A06公共机制实施。不要在只读organ宿主中隐藏ioctl或控制能力。
