# R9：Runtime 总年龄、真实 CLI 进程丢失与模块交接

本轮从实际 main `f9e306f76154590e096a42f70ce9de0a7c859e60` 继续，保留 #192 的原版接合与 #195 的 `cpu.max` 修复。新增工作聚焦于可重复的 Runtime 过期反例、实际可信提交 CLI 被终止时的边界，以及模块开发文档和原始材料的可核验交接。

**Runtime health 的三个年龄分量必须相加。** Session 样本已经 6,000 ms、IPC 往返 20 ms、UI 队列停留 1,991 ms 时，总龄是 8,011 ms；墙钟回拨后分别检查 wall age 和 receipt age 会错误保留 `OBSERVED`。本轮在真实 Desktop 消息队列和 egui 可见标题中先执行 RED，再修复完整采样与接收时钟链。

## 1. 实现与事实边界

| 增量 | 实际变化 | 完成判定的范围 |
| --- | --- | --- |
| Runtime 成功样本时钟 | Session 在完整 health/capabilities/events/closing-health poll 开始前记录时钟，仅完整成功后推进非零、不回绕的序号；失败或独立 known-run 读取不重置该样本。 | 实际 Rust Session 与 scripted UDS peer 回归；不是一次新的原版 Agentd 或设备运行。 |
| UI 保守总年龄 | Shell 计算 Session 样本年龄 + 完整 IPC RTT + 实际接收至绘制的单调时间；同来源同序号保留更大的推进后上界。Runtime 和 known-run 各自独立。 | 实际 Desktop 接收、绘制前过期路径、egui 可见文字与 layout 判定；没有新的 compositor 像素或 IME 验收。 |
| 无效/缺失状态 | 同 Session 暂时缺历史不能清空旧锚；缺 clock、零/倒退序号、反向/溢出时间保持 unknown。总龄 7,000 ms 正例继续有效。 | 明确负例和边界正例；不因新的消息、当前健康或墙钟回拨恢复旧事实。 |
| 真实 CLI 被终止 | 新增 stdin EOF 释放前与完整发送/回复前两个 SIGKILL/reap 回归，使用 channel 握手固定故障点。生产传输代码不变。 | 调用方测试进程保留准确原输入，实际子进程无输出回执、无自动重试；不代表产品已经提供 durable 请求保存或结果核对。 |
| 模块交接 | 全部 11 个模块入口复核；A04 新主干 handoff；A06 补 `cpu.max` 输入契约与实际 owner 路径。 | 源码和文档检查；A04 候选实现尚未整合，未新增 kernel/QEMU 运行。 |
| 历史材料 | R7 可恢复原文归档，R8 已完成 ARM 运行的独立读回。 | 各自保留原日期、源码和缺失项，不能转记为 R9 执行。 |

当前 Schema 在有 Runtime 历史时增加可选 `runtime_sample_clock`，即使没有 known run。新 Shell 可读取缺该字段的旧帧，但视其历史为 unknown；旧严格 decoder 拒绝新字段。Session、Shell 与 ctl 应匹配部署。Box 只改变本地布局，不改变 JSON 字段或绕过严格反序列化。

## 2. UI 的 RED、修复与完整验证

完整逐命令结果、最终源码闭包及实际二进制身份见 [UI 执行归档](ui/README.md)。执行使用官方校验过组件的 Rust 1.88.0，保留锁文件；工作区声明的 Rust 1.83 并未在本轮得到最低版本资格。

初始定向命令为：

```sh
cargo test --manifest-path ui/Cargo.toml --locked -p trill-shell runtime_total_age_ -- --nocapture
```

| 已发生阶段 | 原始事实 |
| --- | --- |
| RED-01 | 1 passed / 1 intended failed，exit 101；原生产新鲜度逻辑显示 `Hepta: OBSERVED · READ ONLY`。7,000 ms 对照通过。 |
| GREEN-01 | 同命令 3 passed，exit 0；新增 Runtime 与 known-run 独立性例。core 与 shell 实际重编译，测试 ELF 字节已变化。 |
| test-01 | 完整 workspace 的 core lib-test 编译失败 E0063；既有 conversation fixture 的完整 projection literal 未补新字段，尚未执行该轮测试。 |
| test-02 | 补该 fixture 后完整 UI workspace 137 passed / 0 failed / 2 既有 CJK ignored。此时仍是中间源码。 |
| clippy-01 | 严格 all-targets 检查报 `large_enum_variant`：新增时钟使 Response 最大/次大 variant 为至少 384/168 字节，exit 101。该失败保留；没有放宽 lint。 |
| 最终 test-03 | boxed clock 的最终源码完整 UI workspace 137 passed / 0 failed / 2 既有 CJK ignored；没有过滤项。 |
| 最终 fmt-02 / clippy-02 / build-01 | 同一最终源码的 fmt、workspace/all-targets 严格 Clippy `-D warnings`、四程序 bins 构建均 exit 0，来源前后不变。 |

最终使用局部 boxed clock 避免扩大公共 Response 变更；最终四项检查的完整 UI/observer 闭包 SHA-256 均为 `d720db71872f8c263b73ab3b5ad9702a856898a32b7cfde312cfe805156d0fe0`，各自前后来源完全相同。test-03 原始日志 SHA-256 为 `4d8c27555128a8e44b646d7e97c3f65f28d250b84ea7e00f0e98ec428541b3f9`，实际 Shell 测试 ELF 为 `e79e327e1d55a6c30f860baf64952b338c18be516f9b7b0b98cee68d14a82685`。中间通过不替换最终执行，也不将失败命令改写为成功。实际命令包含本轮低调试信息、关闭增量与有界并行配置；它们不是冷构建或最低资源资格。

初始 RED 的实际来源是 `777196f826f45183f43a6c74c630f70df4adf4cc` 加测试/字段 scaffold patch；后续提交 `00796f6f6e10027e12b83d37d9ab4b8ab913f72e` 才固定这份源码。初始 GREEN 与完整 UI 阶段均记录各自的 `09cf259676e2a81a998c14f1e1fddf4cc94b80df` 加当时 patch，不能改称执行了事后的证据提交。

RED 闭包 SHA-256 为 `9c96a99db736cb023333a3e79738ddc807b806975ac7dc74e99f40aef4c1a930`；RED 测试 ELF 为 `0fd8a217c728c8fa6a892ddeb1886085d5e794daf91c8943dffd530a215fa747`。最终 closure、profile、原始 stdout/stderr、全部失败和实际 ELF 摘要由各自收据记录，不凭 Cargo 文件名推定复用了同一个测试二进制。

代码与技术说明见当前 [Runtime / run 新鲜度](../../../ui/shell/OBSERVATION_FRESHNESS.md)、[Session 接合](../../../support/ui/HEPTA_OBSERVER.md)、[工作区事实来源](../../../support/ui/CHAT_WORKSPACE.md) 和 [桌面设计](../../../docs/DESKTOP_UX.md)。

[最终独立源码审查](reviews/r9-a07-runtime-clock-final-source-review.json) 对 8 个变更路径与 34 项实际执行闭包逐字节核对，未发现源级阻断项，并独立读取上述完整测试/lint/build 原始日志。审查员没有另行执行 UI、原版或设备测试。

## 3. 实际 CLI 进程丢失

[CLI 完整归档](hepta-cli/README.md) 保留 2026-10-18 14:59:47–15:00:24 UTC 的执行。新增测试实际启动 `hepta-submit`，精确验证请求帧，持有 EOF/回复 channel，随后 SIGKILL 并回收子进程；清理 guard 在断言失败路径也先回收再释放 hold。

| 命令组 | 实际结果 |
| --- | --- |
| 新增两项定向 CLI 终止回归 | 2 passed，已包含在下行总数中 |
| 完整 objective feature suite | 43 passed：library 2、CLI 8、objective UDS 15、只读 socket 16、compile-fail docs 2 |
| feature-off all-targets check | 通过 |
| 严格 Clippy 与 fmt | 通过 |

实际执行身份为 `00796f6f6e10027e12b83d37d9ab4b8ab913f72e` + test-only patch，patch SHA-256 为 `077347ec84b75f57f7a73e0944772a94027549f0adb4e487ee4c8c97b86c7a56`。执行前后 20 项服务输入一致。随后 `09cf259676e2a81a998c14f1e1fddf4cc94b80df` 保留所有这些 Rust、manifest、lock 和 fixture 字节，只额外更新执行后的技术文档；没有声称对该整个后续 HEAD 重新执行过 CLI suite。

执行的 `objective_cli.rs` 为 18,082 字节，Git blob `4136d3d78da1e7dbf7b36b046e6cad6cccda56f0`，SHA-256 `f1cafe25930066e92f93e0b8b8ec06fbe218a353dfa180c421a513fb8e4d684b`。

EOF 仍被持有的 fixture 可独立证明当次尚未连接；完整帧已被 peer 读到的 fixture 可证明当次已经发送。**仅有“CLI 没输出”不能成为 CLI 自己签发的 `NotSent`、`NotApplied` 或持久未受理证据。** 输入保留发生在调用方测试进程内；S1 的首次发送前持久保存和 S2 的原 owner 在线核对仍需原有 owner 完成，见 [后续工单](../../../docs/agents/R8_NEXT_SLICE.md)。

## 4. 11 模块的开发与技术文档

[固定 main 文档审查](reviews/a07-main-f9e306-module-doc-review.json) 核对 A00–A10 共 11 个模块，53 次本地链接对应 49 个不同目标；这些计数属于实际基线 `f9e306f76154590e096a42f70ce9de0a7c859e60`，不是加入新 handoff 后的链接计数。

本轮新增 [A04 构建与交接](../../../docs/agents/handoffs/A04_LINUX_HEPTA_ELF.md)，从固定候选 `25c681d944e4efa92f2772cf773e03ae811bc345` 的实际 CLI 源码和三份手册提取依赖、命令、错误、固定输入与整合顺序。A04 的 `compat/linux/`、`support/rootfs/`、`tests/workloads/linux/` 仍未进入 main；候选命令只可在独立候选 checkout 中执行。31/32 Linux 参照、28 个 C ELF 与另一次 13 项 guest 探针使用不同分母；原固定 ELF/USTAR 缺失不能用同版本重新构建的不同字节补位。

A06 的 [CPU 预算说明](../../../docs/ASTERINAS_CPU_BANDWIDTH_N0.md) 与 [PLAN](../../../docs/agents/PLAN.md) 补入实际 cgroup CPU owner 和 [cpu.max 输入契约](../../../tests/organ_backend/CPU_MAX_CONFIG.md)。#195 已在本轮基线中；本次只核对其解析失败在既有 owner 锁和状态修改前返回的源码与入口，没有重新运行 kernel。旧 159/160 项客体结果不能转记为 #195 新生产源码的测试结果。

完整模块入口继续维护在 [INDEX](../../../docs/INDEX.md)。有手册、源码、宿主测试、客体运行和产品完成分别记录，不以文档数量估算伪完成百分比。

## 5. 历史来源的补全

### R8 ARM 已完成

[R8 ARM completion](r8-arm-completion/README.md) 是对 run `39106645234` / job `117613820420` 的独立只读核对。它实际于 07:11:37–07:36:49 UTC 执行并成功，head `05a7cd23f0a4b90b154ef0c45be89093b129f767` / tree `592e13cc526a247ec4246a4cfe8458e07392d0e1`。

原版只读 8 + Session 8（六阶段）、原版 Objective 10 核心检查 / 7 次明确提交 / 三个 Session 阶段、Python 17 + 12 均有原始日志。39 次来源核对覆盖 33 个不同源码路径；证据 ZIP 的 GitHub digest、83 个成员 CRC 及报告/进程日志对应关系通过。原版 Hepta f8 的源码与 lock 前后 clean。此次未下载两个大 ELF 包独立重算二进制字节，也没有新启动 Agentd 或 Shell。

这项结果可以补充此前排队快照，但不能替代新 R9 提交的云端运行。ARM 运行没有 Shell 像素、production issuer、模型回合、operations dispatch 或设备效果。

### R7 可恢复原文

[R7 独立恢复包](../2026-10-18-r7-recovery/README.md) 已保存 864 个原 UTF-8 文件、A06 六份原 JSON、同一个 R7 ARM artifact 与日志。该恢复包的 42 个文件及 ZIP 原成员已独立核验，见 [独立审查](reviews/r7-recovery-archive-independent-review.json)。

R7/A06 两组仍缺 48 个不同二进制路径、43 个独立 Git blob；原 899 文件的完整本地 tree 没有恢复。保留的旧截图审查文本、SHA 或新 R8 图片均不能填补丢失的原 PNG。没有将新压缩日志冒充原 gzip，也没有将历史未成功发布的本地 commit 写成已发布。

## 6. 验证、发布与当前产品范围

所有归档子目录保留各自独立的原收据、清单和执行来源；根级清单只核验本次组织后的字节，不新增运行资格。

[发布前字节核对](source-publication-binding.json) 逐项确认 34 项最终 UI 执行输入及 CLI 的 Rust/manifest/lock/fixture 与本候选相同，单列 CLI 执行后更新的技术文档。[此前同树发布关系](prior-publication-map.json) 保存三个本地/远端提交的准确映射；Git commit 元数据不同不改变其相同 tree，实际执行 HEAD + patch 仍以原收据为准。

```sh
sha256sum -c SHA256SUMS
```

[workflow 与字段消费者检查](reviews/r9-workflow-and-projection-compatibility.json) 确认本轮代码命中现有 A10 和原版 ARM workflow，A10 的 `check-host.sh` 包含 objective feature 完整 suite。原版 gate 按命名字段读取，新增 runtime clock 不要求放宽现有断言；这只是兼容性源码审查，新增时钟语义由本轮 Rust 测试验证。

当前 UI 是编译后的 Rust eframe/egui Linux host 程序，已有 Workspace/Chat、typed 本地草稿、上下文、Tasks、Console 和独立 Runtime 视图。本轮没有接入 production issuer、原 owner 在线持久查询、K↔D、HOS2 四个效果操作、Asterinas 显示/输入或移动设备运行。默认 Session/Shell 继续只读观察原 Hepta；宿主子进程动作保留其自身 owner。固定原版 Hepta、Asterinas 基线与工具链 pin 未变，根 `README.md` 为 0 字节。
