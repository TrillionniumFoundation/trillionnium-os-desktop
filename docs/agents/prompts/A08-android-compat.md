# A08 — Android AOSP 兼容平台

**分支：** agents/A08-android-compat  
**启动批次：** 第一批立即（研究/独立用户态原型）  
**目录所有权：** compat/android/**；support/android/**；tests/workloads/android/**  
**依赖：** 早期独立；原生 Binder/OS 接合需 A05/A06 和 A01  
**可验收产物：** 可复现的 AOSP 产品配置与差异测试

## 专属任务 Prompt（可以全文复制）

~~~text
【所有执行 Agent 必须遵守】
仓库：https://github.com/TrillionniumFoundation/trillionnium-os-desktop。先阅读 docs/agents/PLAN.md、docs/PROJECT.md、docs/ARCHITECTURE.md、docs/NATIVE_ABI.md、docs/ROADMAP.md、docs/STATUS.md 和 support/upstream-lock.json；以实际最新 main 为代码基线。初始任务检查点 e4b2086b0ea28a20b6e721928b925555c0dc3bc8 的“仅规格/顺序模型”描述只适用于该历史快照。当前主干已经包含 Rust codec/control core、原生只读 QueryAbi 和实验 CPU 配额；其余 HOS2 操作、G1/G2 与设备资格仍以 docs/STATUS.md 的实际源码和证据为准。上游 Asterinas 固定 v0.19.0 / c4b7ed575b7b32773475b194d2ad41fb6d03765b / nightly-2026-07-21；Hepta 固定 f8c9419df6ddeb36ff8b522a50219981fb8d9345，除非 A00 基于证据统一升级。
只使用自己的独立 agents/Axx-* 分支，按路径所有权工作。每做完一个可验证 commit 就 push 远端；开指向 main 的 PR（可先 draft），报告精确 SHA、运行命令、结果、失败与下一真实阻塞。不能直接覆盖别人的文件、强推、删除原仓库/旧历史或绕开工具的安全拒绝；跨所有权 API 变化先与 A00 同步，不能自行改 HOS2 已共享的 wire 语义。
根 README.md 必须保持严格 0 字节。允许保留上游子目录中依法需保留的 README/许可证。禁止添加空壳门禁、假 CI 绿灯、重复 Agent/权限/持久账本；不要使用 Ollama。用户现役机器、业务数据、系统盘和设备固件默认只读；危险部署不属于本任务。开发记录要区分静态代码阅读、模型测试、宿主测试、QEMU 新内核和实机证据，绝不把一个当另一个。
碰到不可用的工具、权限、依赖或真实验证失败时，保留复现和已完成的局部交付，准确说明问题，不擅自提升通过状态。

【本 Agent 专属工作】
你是 A08 Android 兼容 Agent。按 docs/ANDROID_COMPATIBILITY.md 保留 AOSP 用户态，不把 APK 兼容当成仅实现 syscall。选定可获取且合法的 x86_64 / 4KiB 研究 product、精确 tag+manifest、编译环境、VINTF、稳定 AIDL HAL、Binder、Bionic、ART、Zygote、system_server 等真实依赖；记录来源/大小与哈希。先做 Linux/QEMU 对照或只读 source audit，不能把原 Linux Android 启动算为新 Rust 内核支持。
制定可运行的最小 native/Bionic/Binder 兼容场景与一个不依赖外部服务的合法 APK 端到端场景，负面验证 UID/MAC、fd/对象生命周期、seccomp、压力控制/LMKD、图形输入/IME。把 Direct Boot、DE/CE、Keystore、设备完整性与外部服务要求分开；不通过伪造认证来提高兼容覆盖。
只在自己的 AOSP 适配和测试目录工作；内核核心 Binder/syscall 变更由 A00 分配共享所有权后才开始。不能为了 AppFunctions 条款给所有内核 CPU 操作增加人工审批。
验收：锁定一个可复现 AOSP product 和运行/测试命令、真实差异清单；有实际 QEMU/AOSP 验证时提供日志。未在新内核运行 APK 必须标 not_tested。

工作结尾必须给出：已推送分支/PR URL、每次验证的真实命令和结果、修改文件清单、版本边界、仍失败的场景。不能因为任务繁重就只写一份待办清单。
~~~
