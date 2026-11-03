# 执行证据与历史归档索引

更新于 2026-11-03。当前实施起点、当前能力和待验门禁统一见
[CURRENT_CAPABILITIES](CURRENT_CAPABILITIES.md#current-product-pair)；
[模块目录](modules/README.md) 定位开发与技术手册。本页只整理既有证据的位置和
使用边界，不迁移、删减或改写原日志、失败、摘要及来源身份。

## 按问题查找证据

| 要核对的问题 | 保留的入口 | 使用边界 |
| --- | --- | --- |
| 一次原 Hepta 来源更新是否真正运行 Cargo | [4223 六根锁生成与核验](../results/integration/2026-10-27-source-pin/README.md) | 保留生成命令、前后锁摘要和原32项组件资格；只适用于记录中的 4223 来源，不证明 a39 的最终安装包 |
| 旧产品构建的成功与失败如何关联 | [942/de0 检查点](CURRENT_CAPABILITIES.md#2026-10-26-产品整改的当前来源)、[manifest 权限修复](../results/integration/2026-10-27-package-manifest-mode/result.json) | 三项旧 CI 与原优化 builder、随后归档拒绝分别记录；修复测试不能替代重新打包/安装 |
| 当前线程/文本/UI 合同从哪些旧执行延续 | [v10/v11 原包 scoped 记录](../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)、[App-only 恢复组件交接](../results/integration/2026-10-26-product-readiness/app-only-component-handoff.json) | 原包、默认 SDK、真实进程及 host 夹具各有范围；不继承为当前完整 workspace、prepared SDK、实际 Root/模型或设备通过 |
| 尚未闭合的历史失败在哪里 | [e964 静态、H8d Root 负控及 Windows 原始分类](../results/integration/2026-10-27-current-blockers/README.md) | 原失败和被选入的日志保留；该目录的 evidence-index 另列未复制的大文件及其原身份，不把“没有复制”解释成没有执行或已经通过 |
| GPT/EBR 解析器是否在 guest 执行 | [2026-10-27 partition validation](../results/integration/2026-10-27-partition-validation/README.md) | 固定 kernel-mode 解析场景，不覆盖真实磁盘、DMA、掉电或完整 Hepta guest |
| 原生 Process/CPU successor 的实际内核范围 | [39c1eaf8 Process successor](../results/integration/2026-10-24-asterinas-integration/kernel-process-successor/publication.json)、[824720ea 完整先前组合](../results/integration/2026-10-24-asterinas-integration/kernel-owner-continuity/publication.json) | 两套 core 与原四套/ordinary/socket/watchdog 的来源分开；原 Hepta 用户态闭环不由编译输入 ELF 代替 |
| 原 Agentd/store 和 Linux ABI 的既有 guest 证据 | [0187/b3 原 runtime/store](../results/integration/2026-10-23-audit-closure/native-runtime-0187-b3/publication.json)、[0187 完整 Linux32](../results/integration/2026-10-23-audit-closure/full32-0187/publication.json) | 原 no-turn 生命周期、CognitiveStore 与 Linux32 的固定场景，不转授新 pair、生产 writer 或 G2 |
| Rust 桌面的既有 compositor/辅助技术执行 | [f3d54e5b 原 A10 十一执行体](../results/integration/2026-10-23-audit-closure/a10-f3d54e5b/publication.json)、[UI 原始 evidence](../tests/ui/evidence) | Linux host、X11、AT-SPI、Weston 与共享 presenter 的实际来源分别保留；不是 Asterinas 显示输入或当前 preedit 最终包 |
| 限定 Android APK 是否曾在物理设备运行 | [f89023ac 去设备标识收据](../results/integration/2026-10-23-audit-closure/mobile-app-f890/acceptance.json) | 限定 APK 场景；不授原 signer 的严格 organ receiver、通用手机控制、Asterinas Android 或 ARM BSP 资格 |
| 早期模块和发布审计如何复核 | [固定模块审计](agents/MODULE_DOCUMENTATION_AUDIT.md)、[原 Hepta integration evidence](../tests/integration/hepta/evidence)、[日期账本](STATUS.md) | 保留当时数量、PR/CI 快照及其来源；当前模块集合由 catalogue 和现有 manifests 重新检查 |

## 原始目录与引用规则

综合运行和跨仓记录保存在 [results/integration](../results/integration)；专项测试的
原始收据仍在其 `tests/**/evidence` 或对应 `results` 子目录。上表是导航，不是对所有
大文件的重新收集，也不声明未列出的记录已经丢失。按原 README、publication/result
或 evidence-index 读取完整范围；外部归档只保留位置和摘要时，应如实记录可用性。

引用某次执行至少区分两类身份：被测 Desktop/Hepta 的完整 commit/tree 与发布证据的
文档提交。两者可以不同。构建还要绑定锁、features、SDK/资源、工具链和二进制；运行
要绑定环境、实际命令、退出码、日志及所选/忽略/未执行场景。dirty 工作树的摘要只能
证明那些实际输入字节，不能记作干净 HEAD 的执行。

旧记录中的“当前”、排队、失败、README 0字节约束和测试数量属于原日期。新的成功
记录追加精确来源并链接前次失败，不覆盖旧失败或把 skipped/ignored 算成通过。
文档/来源检查不启动产品，host 夹具不证明 guest 或实机，限定目的端不授予通用控制。

## 后续归档维护

新增证据沿现有 `results/integration/YYYY-MM-DD-purpose` 或模块 evidence 入口归档，
保留原始失败和最终结果，并在本页增加一个可复核入口。更新当前验收状态时同时链接
精确收据，说明尚未覆盖的场景；单纯修改文档不关闭产品门禁。

需要精简仓库时先制作文件级清单和摘要，保留原来源、外部可恢复位置及读回验证，
再由独立的维护变更决定搬移范围。本次索引不删除任何唯一证据，也不将归档目录
伪装成当前源码。开发入口、历史记录与可复现输入保持各自原有位置。
