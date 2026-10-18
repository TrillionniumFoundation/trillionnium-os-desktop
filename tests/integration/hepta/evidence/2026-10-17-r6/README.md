# R6 交付索引：原版 Hepta 与原生 Rust Shell 的持续连接

本轮已实际闭合固定原版 Hepta → 持续 Session → 同一个真实 Rust Shell 窗口的只读运行链路，修复 Shell 过期观测误标成功和外部 probe 锁不稳定，并把新增捕获契约测试接入 A10 CI。本文汇总已冻结的代码、运行与审查入口；每份原始收据保留自己的实际执行来源。

## 可复核的交付

| 交付 | 实际结果 | 完整入口 |
| --- | --- | --- |
| 原版 native Agentd | 最终真实链接成功；前两次失败与缓存/资源迁移均保留 | [原版构建](../2026-10-17-native-agentd-build/README.md) |
| 外部原版 probe / observer | 首次锁失败、两次诊断、稳定锁与 733-package resolve graph、真实链接及 2 项 Rust stale 测试 | [消费者构建与锁诊断](../2026-10-17-original-session-build/README.md) |
| 原版持续 Session | 旧 R5 和新 GREEN03 两轮，每轮原版 8 项 + Session 8 项通过；首轮失败单独保留 | [三轮运行记录](../2026-10-17-original-session-runtime/README.md) |
| 同一个真实 Rust Shell | 两轮各 6 阶段、每轮同 Shell PID/XID，12 张成功 PNG 逐张三方复核；另保留首轮失败 PNG | [13 张原图、快照和审查](../../../../ui/evidence/2026-10-17-original-hepta-shell/README.md) |
| 可见观测新鲜度 | 真实 RED 为 1 pass / 5 fail；最终 GREEN 的 6 freshness + 2 layout、严格 Clippy、fmt、四程序构建通过 | [完整 RED/GREEN 与 ELF 来源](../../../../ui/evidence/2026-10-17-observation-freshness/README.md) |
| 最终源码 Python 门禁 | 5 项 manifest/lock + 6 项进程守卫 + 6 项 receipt，共 17 passed，23:09 UTC 原始日志 | [源码检查实录](../2026-10-17-original-session-checks/README.md) |
| CI 覆盖补齐 | A10 自动调用既有 8 项捕获契约；真实执行提交中的精确 run block 一次，8 passed | [CI 配置与本地命令实录](../../../../ui/evidence/2026-10-17-original-shell-ci/README.md) |

各项分母分别记录，不能把截图、ACK、测试断言或不同来源的重复执行混成一个完成度数字。新生产 UI 的两轮集成实录不代替定向的过期队列回归；CI 契约测试也不代替真实窗口运行。

## 六阶段的真实状态

1. Starting、Running、Draining 使用同一原版 Agentd PID/spawn、同一 Session PID/instance/worker。
2. 原版重启后旧 Session 继续响应 IPC，保留旧来源历史并显示 stale，不静默信任新的 spawn。首次 stale 后，后续失败样本的最后成功观测完整不变。
3. 显式启动绑定新可信配置的 Session，原来的 Shell 进程/窗口继续运行并恢复新原版 Running。
4. 原版停止后 Session 仍响应，UI 明确显示当前未知。旧轮最终保留 Running/current6，新轮最终保留实际退出前采到的 Draining/current7；时序差异不是 UI 修复的效果证明。

新旧两轮分别执行于本地 `28843c6632fe63db6b3fecb4d05888e90976fd16` 与 `145e94c364243789b88c23b1292f9d4d9ca9a0e9`。对应同树远端为 [`66dba7f40c2fa8fea2e7828ec2fd4db336bb681f`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/66dba7f40c2fa8fea2e7828ec2fd4db336bb681f) 和 [`299794f90d4557cec4ee9a7fc92c397031fced4f`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/299794f90d4557cec4ee9a7fc92c397031fced4f)。实际原版固定为 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`，源码/原版锁/ELF 在运行前后不变。

新 UI 真正构建于本地 `84f0070b6e7e01238a8dac6044748b15101c9497` / 同树远端 `88e9cdb124801c1d0fba5d2bb7e52a85a69a79f4`。observer/probe 真实构建来源另为本地 `c50d7b9b688135a22ced2f7f3cbe21c3028d8e17` / 远端 `028b664b4717c4dffc03dc638fa3e9a5d7a0b52a`。复用需要匹配编译输入、完整 UI 子树、Session 外部 A07 依赖以及每个 ELF；后续证据提交不冒充重新编译。

## CI 结果与所属源码

| 精确源码 | 已核验的 CI 结果 | 证据范围 |
| --- | --- | --- |
| `c0d5ee395cd76bcd29e8f1c912d048d19c97ce00` | A10 与 ARM 均 success；145 Rust passed / 2 ignored，另 6 guard；ARM 原版 8 项 | [前轮最终候选完成实录](../2026-10-17-candidate-ci/README.md)。A10 使用标识清楚的 fixture，ARM 是每次新 CLI |
| `f0924a6e48c68101ec09b01ef2f69aec330a3da7` | ARM 锁失败；A10 后续 success | [原始失败/排队快照](../2026-10-17-f092-ci/README.md)与[后续 A10 完成记录](../2026-10-17-f092-a10-completion/README.md)分别保留，不覆盖旧快照 |
| `84e08165d2e753fe1fc780e1972dbab4317e8499` | ARM 于 23:11:50 UTC success，原版 8 + Session 8，五个 ARM64 ELF 实际字节已核验 | [真实 ARM 持续 Session 运行](../2026-10-17-84e-arm-ci/README.md)。该 CI 未启动 Shell、未捕获像素；23:12 UTC 的 G0/源检查通过、A10 native 排队快照也按时间保留 |
| `9a9c4fac92c5b3e5595845efbea72efe869763b4` | 新 CI 步骤精确本地命令 8 passed | [命令实录](../../../../ui/evidence/2026-10-17-original-shell-ci/README.md)。不能据此宣称 GitHub 已运行该新提交或最终证据 HEAD |

## 源码、审查与范围

[publication-source-map.json](publication-source-map.json) 记录保持完整 tree 相同的正常 Git 发布映射；[source-closure-review.json](source-closure-review.json) 逐项核对最终来源与实际新 UI 运行的 11 个源码对象，并确认当前 main `f64c3d6b`、A10 owner `45552fbd`、旧/新运行来源及 CI hook 的祖先都保留。根 README 仍为 0 字节。

[reviews](reviews) 保存独立的构建、缓存保留和新鲜度复核；其中 `R6_SOURCE_REVIEW.md` 与 `SHELL_FRESHNESS_P2.md` 是修复前的发现记录，最终修复与实录以上述对应归档为准。`REVIEW_INPUTS.json` 与 `SHA256SUMS` 保留原始文件来源和摘要。实际 PNG 的 root/A10/独立逐图复核在 Shell 归档中，避免将机器 ACK 当成人工验图。

当前界面是 Rust eframe/egui/glow 的真实 Linux host 程序，原版 Hepta 数据已进入 UI。该切片仍为只读：objective submission 明确不可用；没有模型 turn、可信 issuer 替换、authority/账本替换或设备效果。`TrustedReadOnlyOrganV1` 不是操作系统沙箱。可信 ObjectiveStart、durable K↔D、撤销与结果 owner 的桌面接合是下一条执行主线；Asterinas、移动显示/触控、Wayland 输入、GPU 和物理设备资格仍待各自验收。
