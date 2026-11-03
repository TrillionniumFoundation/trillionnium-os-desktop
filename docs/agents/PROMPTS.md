# 独立可复制的 Agent Prompts

下列每个文件已经包含公共约束、自己的所有权、依赖、交付与验收。只需给对应 Agent 发送它自己的文件全文，不需要额外拼接通用提示词。先阅读 [并行计划](PLAN.md)。根 README.md 提供项目导航并保持普通文件；开工状态以 [当前能力表](../CURRENT_CAPABILITIES.md) 的来源与资格边界为准。

- [A00 — 总集成与接口协调](prompts/A00-integration.md)（全程）
- [A01 — Asterinas 内核源码与启动](prompts/A01-asterinas-boot.md)（第一批立即）
- [A02 — HOS2 no_std 编解码](prompts/A02-hos2-wire.md)（第一批立即）
- [A03 — 资源控制状态机与对抗测试](prompts/A03-control-core.md)（第一批立即）
- [A04 — Linux ELF 与 Hepta 依赖基线](prompts/A04-linux-hepta-baseline.md)（第一批立即）
- [A05 — 内核 CapSpace 与 HOS2 ioctl 接合](prompts/A05-kernel-control.md)（第二批 G0 之后）
- [A06 — 真实 CPU 调度与资源计费](prompts/A06-scheduler-budget.md)（第二批 G0/G1 接口具备后）
- [A07 — Hepta 原生操作与持久确认](prompts/A07-hepta-native.md)（接口前置可开始宿主测试，G1 后才做真实新内核路径）
- [A08 — Android AOSP 兼容平台](prompts/A08-android-compat.md)（第一批立即（研究/独立用户态原型））
- [A09 — GPU/NPU/VM 硬件路径](prompts/A09-gpu-vmm.md)（第一批立即（风险前置））
- [A10 — Rust Wayland 桌面原型](prompts/A10-rust-desktop.md)（第一批立即（独立原型））

这些是任务委托，不代表已经启动或运行。