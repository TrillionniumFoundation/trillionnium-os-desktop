# 执行证据与历史归档索引

更新于 2026-11-04。当前实施起点、当前能力和待验门禁统一见
[CURRENT_CAPABILITIES](CURRENT_CAPABILITIES.md#current-product-pair)；
[模块目录](modules/README.md) 定位开发与技术手册。本页只整理既有证据的位置和
使用边界，不迁移、删减或改写原日志、失败、摘要及来源身份。

## 按问题查找证据

| 要核对的问题 | 保留的入口 | 使用边界 |
| --- | --- | --- |
| 当前 `f5/14` 的依赖声明和锁是否已实际收敛 | [canonical 源码与 Cargo 收据](../results/integration/2026-11-03-organ-followup/joint-desktop-canonical14-source-20261104/README.md) | 39 处声明、三份 Cargo 生成锁、其余三锁和六个 fresh locked/offline 图已核对；普通/优化依赖回归各 41 项通过。发布树等值与 clean canonical 切换另留原件，未给新 pair 构建、安装或效果资格 |
| a286 是否已经完整构建内核 | [kernel v4 完整原日志与 validator](../results/integration/2026-11-03-organ-followup/g2-a286-kernel-v4-20261104/README.md) | 原 OSDK/kernel 均 exit 0，kernel 28,908,256 bytes，来源未变；旧 v3 失败保留。完整编译不替代 guest、原 writer/outbox 持久 G2 或整机资源保证 |
| 第一次原 native 执行是否到达 QEMU | [a286 native v1 主机准备失败](../results/integration/2026-11-03-organ-followup/g2-a286-native-preflight-v1-20261104/README.md) | inputs_frozen 阶段 archive exceeds limit、exit 1；QEMU 未启动，controls/scenarios 为空，不推断 guest 成功或失败 |
| 专用归档后继是否保持旧门槛 | [00d1 源码、6/6 host 检查与原 ELF roundtrip](../results/integration/2026-11-03-organ-followup/g2-exact-archive-source-20261104/README.md) | 仅固定原 owner/base、两个有限 plan 的 22,268,496-byte envelope；共享 codec 16 MiB 默认和旧 profile 不变。无新 guest 或丢回复恢复资格 |
| 2026-11-03 两仓固定版本和本轮实际执行 | [fd/e1 与 a39 检查点](../results/integration/2026-11-03-organ-convergence/README.md) | 原 Session、UI、F1 daemon、Store、内核、Android 和当前 CI 失败按各自来源分开；尚未取得完整 Notes/F1/G2/手机产品资格 |
| Notes/build 后继、Calculator 和原 Memory 的执行结果 | [2026-11-03 后续证据](../results/integration/2026-11-03-organ-followup/README.md) | bf15 的 9 项 CI、5a 的组件通过与 A10 失败、Hepta stage 2 定向通过及 Memory 原失败分别绑定来源；未闭合最终双应用原 Root 和 Notes 生产链 |
| fd/a39 原 Root 是否已真正构建、测试和安装 | [product-linux 原始收据及完整日志](../results/integration/2026-11-03-organ-followup/owner-p0-fd-v5/README.md) | 原构建、55 个不同测试、打包/校验/安装通过；前次 dev-small 超限失败保留。安装没有启动服务，真实 Notes 闭环与连续授权尚未由此取得资格 |
| 原 App Server 信号修复是否真正构建并使 seed 正常退役 | [19 命令组件构建与完整归档](../results/integration/2026-11-03-organ-followup/original-appserver-signal-component/README.md)、[原 seed 实际生命周期](../results/integration/2026-11-03-organ-followup/original-seed-lifecycle-857d/README.md) | 五项信号/drain 首次通过，实际 seed 1 passed、job exit 0；原 10 秒子进程边界及 socket/mount 退役保持。明确混合组件来源，不授予最终产品、用户提交或效果恢复资格 |
| 联合 Hepta 候选的四个 owning package 是否全过 | [26a 完整原测试与日志](../results/integration/2026-11-03-organ-followup/joint-hepta-26a-tests/README.md) | Objective 66/0/2、Memory 399/1/13、Agentd 546/1/60、App Server 1,315/16/2；完整原 job 失败，保留 retries。14 helper 相关失败和两项实际行为失败分别处理 |
| Agentd custody 失败与后继发布如何关联 | [47 原精确选测](../results/integration/2026-11-03-organ-followup/joint-hepta-47-custody/README.md)、[Hepta 14e2 canonical 发布](../results/integration/2026-11-03-organ-followup/joint-hepta-canonical-publication/README.md) | 47 单文件测试修复在原期限内首次通过；原完整 Agentd 红灯保留。发布 tree 与最终本地文档后继一致，不冒称 canonical 上重新执行或联合产品通过 |
| a286 是否已实际编译到内核代码 | [kernel v3 完整失败记录](../results/integration/2026-11-03-organ-followup/g2-a286-kernel-v3-20261104/README.md) | 实际编译到 aster-core，三处原 metadata 宏失败；kernel exit 2、job exit 1，无超时/取消。该次未获得完整内核或原生 G2；后续 v4 另有成功收据 |
| a286 是否已经真正重建原 owner 和 OSDK | [28 文件源码/构建/缓存记录](../results/integration/2026-11-03-organ-followup/g2-a286-build-and-cache-evidence-20261103/README.md)、[19 文件读恢复/标准库缓存记录](../results/integration/2026-11-03-organ-followup/g2-a286-read-recovery-evidence-20261103/README.md) | 独立 source、原 ELF 与原 source-built OSDK 通过；kernel 因固定 nightly 标准库缺包失败。这些较早记录的生成锁一致不替代后续 v4 或原生 G2 |
| 原 G2 owner 为何没有进入新 guest | [原镜像、旧门禁拒绝及内存核算](../results/g2-original-owner-size-20261103/README.md) | 原编译/strip 成功，20,138,584-byte ELF 被旧 8 MiB / 16 MiB profile 拒绝；派生内存算式不是 512 MiB guest 的实测峰值或恢复保留保证 |
| 新 G2 来源是否已独立装配并重建原 owner | [fe55 原源码、构建与入口失败](../results/integration/2026-11-03-organ-followup/g2-canonical-source-owner/README.md)、[独立字节复核](../results/integration/2026-11-03-organ-followup/g2-canonical-source-owner/independent-review.json) | 无 alternates 的 depth-1 源及原 owner 构建通过；空日志使首次 kernel 入口失败。a286 的窄修和 50/17 host 检查不替代其后续内核、实际 204 图或 guest 资格 |
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

本轮还纠正了 `d27ae5de` 的总索引路径错误：新增 67 文件已在 Git 中，误写到顶层 `evidence-index.json` 的 387 项现已重核并归回既有 [index.json](../results/integration/2026-11-03-organ-followup/index.json)，README 摘要同步更新。原 d27 中的误放派生索引仍可追溯，四个子组各自的 `evidence-index.json` 和全部原始日志保持原样。

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
