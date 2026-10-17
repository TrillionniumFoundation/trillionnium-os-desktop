# A01 — Asterinas 内核源码与启动

**分支：** agents/A01-asterinas-boot  
**启动批次：** 第一批立即  
**目录所有权：** support/build/**；support/upstream-lock.json；kernel/asterinas/** 的初始导入及构建文件（A05/A06 接手后不再改其核心源码）  
**依赖：** 独立开始；给 A05/A06 提供实际基线  
**可验收产物：** 固定源码到最小 QEMU 串口启动

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。当前主干已经包含 Rust codec/control core、原生只读 QueryAbi 和实验 CPU 配额；其余 HOS2 操作、G1/G2 与设备资格仍以 docs/STATUS.md 的实际源码和证据为准。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；Hepta 固定 f8c9419df6ddeb36ff8b522a50219981fb8d9345，除非 A00 基于证据统一升级。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 必须保持严格 0 字节。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A01 Rust 内核基础 Agent。使用当前 support/upstream-lock.json 锁定的 Asterinas 完整内核 v0.19.0（commit c4b7ed575b7b32773475b194d2ad41fb6d03765b），不自行换成 OSTD-only 或 Linux。首先从源码构建官方最小 initramfs 路线，而不是再次把 1.44GB 安装 ISO 当先决条件；上游开发路线为 make kernel / make run_kernel。核对官方构建说明、夜版 Rust 工具链、Docker/Nix 依赖、Cargo.lock、QEMU、启动固件、rootfs 与许可。
在你的分支建立单一被 A00 认可的源码导入/派生形式（优先固定 kernel/asterinas/ 目录，保留上游许可和署名；禁止在多个位置复制内核）。如环境不能进行导入，先提交可运行的获取/验证脚本、工具链与构建清单，记录准确 blocker。严禁为了“README 为空”删掉上游必须保留的署名。
在 QEMU 显式设置 1 vCPU，运行最小内核，保存构建命令、工具版本、源码 SHA、构建产物 SHA256、串口日志、成功/失败信号。区分未修改上游启动与本项目 HOS2 改动启动，不得将 ISO 安装器启动或宿主 Linux 结果冒充项目内核通过。仅使用测试镜像，不触碰现役磁盘和固件。
完成后告诉 A00 内核根路径、精确构建/启动入口、工作区大小和后续 A05/A06 各自可修改的源码位置。验收：干净环境复现一条上游源码编译+QEMU 路径；若未做到，提交明确错误日志和复现脚本而非空模板。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~
