# R9：原 owner Objective 历史查询、真实故障资格与模块文档复核

**本轮已在本机 x86_64 Linux 上完成最终原 Hepta owner 的 native 构建与真实 history 运行：15 项检查、13 次 history CLI 查询、5 个不同 Objective 请求、4 个 durable publication、3 次受控重启，恢复重投为 0。** 两路独立审查核对原始日志、签名输入、journal 字节、来源和执行 ELF，未发现阻塞项。

这只关闭了 S2 中“已知准确 Objective 请求的原 owner publication 查询”这一增量。生产请求/anchor 保存入口、当前运行接纳、Operations 效果终态、最终授权、Asterinas G1/G2 和移动设备控制分别验收。编译 publication 不等于当前 run 已接纳，更不等于效果已发生。

## 交付与来源

| 对象 | 精确输入 / 来源 |
| --- | --- |
| Desktop 实际执行输入 | `207ff9da7dac83c57b0cbae46c4b03ecfba3baa9`，tree `8d5de807c41090e3d987764daec9c235ebd022a1` |
| Desktop 同树发布 | [`46dcb2d691827f7aa3ad7903dae09d39fd338126`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/46dcb2d691827f7aa3ad7903dae09d39fd338126)，[PR #193](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/193) |
| 最终原 owner 扩展 | [`2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5)，tree `f4ef891d43baf90d6eebd29921a5ed03222ef3ab`，[PR #2815](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2815) |
| 原 f8 基线 | `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 保持只读；原 Cargo.lock SHA `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389` 未改 |
| 独立历史合同 | [OBJECTIVE_HISTORY_CONTRACT.json](../../../services/hepta-os/OBJECTIVE_HISTORY_CONTRACT.json)，SHA `f0fc1110233dc38542097c6f9f7ef2e3f6ca5eb215fa2b4447e556cd7ac46981`；36 个明确 owner 输入，整体源码另由 commit/tree 固定 |
| Native 实际区间 | 2026-10-18 10:02:35.148191–10:10:23.714016 UTC；Rust 1.95.0、locked/offline、dev-small、j1、实际 Agentd lib/bin features=[] |
| Probe 构建与执行区间 | 2026-10-18 10:10:52.988105–10:16:27.620004 UTC；runner 实际新建 probe，没有使用旧 R8 probe 二进制 |

开发、协议、CLI、授权与存储边界见 [OBJECTIVE_HISTORY.md](../../../services/hepta-os/OBJECTIVE_HISTORY.md)；复跑命令、15 场景判据与原依赖锁复用规则见 [OBJECTIVE_HISTORY_PROBE.md](../../../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)。8 个 probe 输入和合同摘要编入真实 probe；735 个 shared package identity 通过既有锁验证。原 owner Cargo manifest/lock 未改，外部 runner 保留有记录的 unused duplicate patch omission。

## 实际验收

| 范围 | 已执行结果 | 精确边界 |
| --- | --- | --- |
| Desktop 客户端 | 51 passed；严格 all-target Clippy、default-off check、fmt、3 个真实 CLI 构建通过 | 源码 `c080896189b6d5c1e411a28b7614c8fcdc33b188`；后续 207 的 12 个实际编译输入同字节，绑定真实 ELF 后复用 |
| 原 protocol / ledger | 134 passed / 1 既有 ignored | 源码 `ee0a2e5eee299fc0f272c3ceb09ef70f2cbfaf73`，`--lib`；原 production growth 测试仍 ignored |
| 原 Agentd | 173 passed / 0 failed / 0 ignored，含 4 项新增查询测试 | 源码 `d1d40f64eadd0210f5f6abc003cd479a0e1ee010`，仅 `--lib` |
| 最终 owner 源码 | scoped `just fix` 与 `just fmt --base f8` 完成；最终 native05 和本轮真实 runtime 通过 | 最终发布 2be 在 d1 后的有效变化为 Published metadata Box 布局及文档排版；JSON wire 不变；既有无关自动修改已撤回 |
| 真实 history | 15 checks / 13 queries / 5 Objective attempts / 4 publications / 3 restarts / 0 recovery retries | 本机 x86_64、隔离测试 issuer；4 次真实 hepta-submit CLI + 1 次原协议 harness 请求 |
| CI 静态校验 | 实际 actionlint 1.7.12、YAML、12 个 Bash block 与 8 个 Python block 通过 | 不等于远端任务运行通过；没有执行 shellcheck 或 pyflakes |

134 与 173 是两次不同固定源码的 scoped suite，不能表述为“最终 HEAD 全套 307 项重跑”。尽管这两轮命令使用 no-default 参数，测试 dev-dependency 图仍统一了 default/production-cognitive-write；它们不是完整 no-default 图的证明。最终 native05 的实际 rustc lib/bin 命令分别经独立复核，features=[]。

| # | 实际检查 | 观察结果 |
| --- | --- | --- |
| 1 | `live_compiled_publication` | 准确原请求查得 compiled publication #1，与实际提交 receipt 对应。 |
| 2 | `live_abstain_publication` | 查得 explicit_abstain #2，当前 RunStatus 为空。 |
| 3 | `retained_anchor_covers_publication` | 以前收到的 #2 anchor 覆盖原 #1 publication。 |
| 4 | `harness_lost_response_then_history` | 原协议 harness 完整发送后读取 0 回复字节，history 查得 #3；未重投。 |
| 5 | `postpublication_submit_unknown_history_published` | 实际 CLI 返回 submit_unknown / objective_owner_request_rejected，历史存在 compiled #4，当前 RunStatus 为空。 |
| 6 | `wrong_anchor_unknown` | anchor_mismatch；保留 unknown。 |
| 7 | `earlier_anchor_unknown` | publication_outside_anchor；保留 unknown。 |
| 8 | `changed_signed_request_unknown` | 仅修改签名后 no_matching_publication；保留 unknown。 |
| 9 | `restart_projection_missing_history_published` | 更换当前 PID/spawn 后仍读出原 #3 publication；当前 RunStatus 为空，无旧 run 恢复。 |
| 10 | `expired_request_history_still_published` | 真实等待 22,434 ms，观察时钟比原 expiry 晚 3 ms；原 #2 publication 仍可读。 |
| 11 | `rollback_retained_anchor_unknown` | 停止 owner 后回滚为原第一完整前缀 4,203 B；重启后原 #4 anchor_missing。 |
| 12 | `truncated_tail_retained_anchor_unknown` | 停止 owner 后注入 16,589 B 原完整 journal 去掉末字节；原 owner 恢复为第三完整前缀 12,410 B；#4 anchor_missing。 |
| 13 | `revoked_issuer_history_still_published` | 当前 issuer 撤销后，旧 #1 publication 仍可核对。 |
| 14 | `revoked_new_submission_rejected` | 第 5 个不同的新请求返回泛化拒绝，journal 不追加。 |
| 15 | `controlled_stop` | 原 Supervisor 确认 inactive，旧控制端点不可用。 |

最关键的第 5 项直接说明：提交出现泛化错误、当前 RunStatus 为空时，不能推定请求没有持久发布。原 owner 的第 4 个 compiled publication 已保存。具体容量耗尽原因来自固定默认预算和两个前序 admitted run 的源码推论；CLI 没有保存 `CapacityExceeded` 的具体错误字节，报告没有把它写成直接观察。

两次存储注入都在 owner 已确认停止之后进行。保存的 publication 前缀是 4,203 / 8,264 / 12,410 / 16,589 B；回滚和截断的注入/恢复文件已逐字节核对。截断由原 owner 的正常恢复处理；产品 history 客户端没有打开活跃 journal。当前查询从 owner 已恢复的内存前缀读取；外部 retained anchor 能约束该前缀，不能证明在线磁盘未被修改，也不能检测 journal 与调用者 anchor 一同回滚。

## 五个实际执行文件

| 程序 | Bytes | SHA-256 |
| --- | --- | --- |
| probe | 36,935,872 | `65ec78d80d2a54960564b42f36d14fef423b4419e408022d122b858ba03f0d63` |
| agentd | 329,024,000 | `a8f8aefa2199a2e41c22b8251145f064e3af767ff5357475ddb527beb86761cb` |
| observer | 15,046,512 | `a79114fc2e04e2ee226e225c7f5da8da7bc395878e5a67eff0a347aa85fed728` |
| submitter | 14,842,384 | `c0155afd9f450006e85b5c8e5957a8db2b5aaa12fd0aa0dacabf213255d75233` |
| history | 15,181,152 | `10f24fce4c681fce18890b338c879bbbeb0f3bae61335c7de3d88f5b2d4ce6eb` |

Agentd 的执行输入是从实际 native05 产物保留的独立 ELF 副本；构建输出路径和执行路径分别记录，大小和 SHA 相同。所有五个文件都在执行完成与归档时再次核对。ELF、工具安装包和普通构建缓存不放入原始证据归档，省略项带原因及相应身份；必要的失败诊断 ZIP 作为原始字节完整保留。

## 模块开发与技术文档

[静态模块文档审查](module-documentation-review.json) 固定于执行源码 207：11 个模块、53 个 INDEX 本地链接，以及 47 份入口手册中的 225 个本地目标均存在，57 份本地材料保留 Git blob、SHA、大小与标题信息。该审查检查开发依赖、构建运行、输入输出/错误、owner/权限、证据绑定和文档范围；不产生新的模块运行资格。

| 模块 | 具体开发入口 | 技术入口 | 文档判断 |
| --- | --- | --- | --- |
| A00 集成与架构 | [docs/agents/PLAN.md](../../../docs/agents/PLAN.md)、[docs/STATUS.md](../../../docs/STATUS.md) | [docs/ARCHITECTURE.md](../../../docs/ARCHITECTURE.md)、[docs/DECISIONS.md](../../../docs/DECISIONS.md) | 有具体协调/架构/验收文档；不应描述成 A00 单独拥有一套独立产品开发 API 手册。 |
| A01 Asterinas 源码、构建与启动 | [support/build/README.md](../../../support/build/README.md)、[support/build/ktest/README.md](../../../support/build/ktest/README.md) | [support/upstream-lock.json](../../../support/upstream-lock.json)、[docs/ARCHITECTURE.md](../../../docs/ARCHITECTURE.md) | 开发与技术内容合写在构建手册/ktest手册，加机器可读固定来源；可形成具体交接。 |
| A02 HOS2 Rust codec | [tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md](../../../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md)、[tests/abi/A02_EVIDENCE_INTEGRITY_2026-10-17.md](../../../tests/abi/A02_EVIDENCE_INTEGRITY_2026-10-17.md) | [libs/os-abi/src/lib.rs](../../../libs/os-abi/src/lib.rs)、[docs/NATIVE_ABI.md](../../../docs/NATIVE_ABI.md) | 开发交接由验收手册、源码API和共享ABI组合提供，有具体内容；没有单独命名的模块开发README并不等于无文档。 |
| A03 HOS2 control core | [tests/control/VALIDATION.md](../../../tests/control/VALIDATION.md)、[tests/control/run-validation.sh](../../../tests/control/run-validation.sh) | [libs/os-control/API_CONTRACT.md](../../../libs/os-control/API_CONTRACT.md)、[docs/NATIVE_ABI.md](../../../docs/NATIVE_ABI.md) | 专属开发验证手册和细粒度技术契约齐备，覆盖远超占位prompt；文档同时保留较长历史增量。 |
| A04 Linux / Hepta ELF 兼容候选 | [tests/workloads/linux/README.md（候选）](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/tests/workloads/linux/README.md)、[support/rootfs/README.md（候选）](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/support/rootfs/README.md) | [compat/linux/GAPS.md（候选）](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/compat/linux/GAPS.md)、[docs/LINUX_COMPATIBILITY.md](../../../docs/LINUX_COMPATIBILITY.md) | 三份详细手册仅在固定 Draft #8 候选，未合入被审树 |
| A05 内核控制与进程镜像身份 | [docs/agents/handoffs/A05_KERNEL_CONTROL.md](../../../docs/agents/handoffs/A05_KERNEL_CONTROL.md) | [docs/agents/handoffs/A05_KERNEL_CONTROL.md](../../../docs/agents/handoffs/A05_KERNEL_CONTROL.md)、[docs/NATIVE_ABI.md](../../../docs/NATIVE_ABI.md) | 实现、构建、调试、错误与owner有专属手册；字段规格通过共享ABI维护。 |
| A06 CPU预算与计费owner | [docs/ASTERINAS_CPU_BANDWIDTH_N0.md](../../../docs/ASTERINAS_CPU_BANDWIDTH_N0.md) | [docs/ASTERINAS_CPU_BANDWIDTH_N0.md](../../../docs/ASTERINAS_CPU_BANDWIDTH_N0.md)、[docs/ASTERINAS_ORGAN_BACKEND.md](../../../docs/ASTERINAS_ORGAN_BACKEND.md) | CPU开发/技术/复现文档具体，构建工具由A01共享。 |
| A07 Hepta用户态客户端与原owner接合 | [services/hepta-os/README.md](../../../services/hepta-os/README.md)、[services/hepta-os/RUN.md](../../../services/hepta-os/RUN.md) | [services/hepta-os/CONTRACT.md](../../../services/hepta-os/CONTRACT.md)、[services/hepta-os/OBJECTIVE_TRANSPORT.md](../../../services/hepta-os/OBJECTIVE_TRANSPORT.md) | 专属开发、运行和分功能技术文档齐全；R9新增history入口在INDEX表前及README/RUN中。 |
| A08 Android兼容与宿主验收工具 | [support/android/README.md](../../../support/android/README.md) | [compat/android/INTERFACES.md](../../../compat/android/INTERFACES.md)、[compat/android/kernel-gaps.json](../../../compat/android/kernel-gaps.json) | 专属开发与接口文档全面；旧日期段落保留原checkpoint，须由最新header与STATUS解释当前资格。 |
| A09 硬件、VMM与设备生命周期模型 | [support/vmm/device_lifecycle/README.md](../../../support/vmm/device_lifecycle/README.md)、[support/vmm/GATES.md](../../../support/vmm/GATES.md) | [support/vmm/PROVENANCE.md](../../../support/vmm/PROVENANCE.md)、[support/vmm/device_lifecycle/README.md](../../../support/vmm/device_lifecycle/README.md) | 专属开发与技术契约存在，实际实现范围明确标作元数据模型。 |
| A10 Rust桌面、Session与交互原型 | [support/ui/RUN.md](../../../support/ui/RUN.md)、[support/ui/CHAT_WORKSPACE.md](../../../support/ui/CHAT_WORKSPACE.md) | [ui/shell/OBSERVATION_FRESHNESS.md](../../../ui/shell/OBSERVATION_FRESHNESS.md)、[support/ui/CHAT_WORKSPACE.md](../../../support/ui/CHAT_WORKSPACE.md) | 专属开发/技术/输入/验证手册具体，包含真实产品流程和公开限制；移动适配不是文档存在即已实现。 |

**A04 是明确例外：**`tests/workloads/linux/README.md`、`support/rootfs/README.md`、`compat/linux/GAPS.md` 三份文件均不在被审 207 树中，只在固定候选 `25c681d944e4efa92f2772cf773e03ae811bc345`；审查时 [Draft #8](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/8) 仍 open、draft、unmerged。主干有共享 Linux 技术要求和候选链接，不能称全部详细手册已经合入。

A00 的协调文档、A02/A05 的共享 ABI、A06 的共享构建手册是明确的职责分配；不要求复制成名称不同而内容重复的两套文件。此轮更新 [INDEX](../../../docs/INDEX.md)、[STATUS](../../../docs/STATUS.md) 与 [S1–S5](../../../docs/agents/R8_NEXT_SLICE.md) 的最新入口；静态审查文件仍保留对修改前 207 文档的原始观察，历史计数不转记。

## 实际失败与诊断

native-agentd-01 失败于 StableCrateId/旧 archive 与新 metadata 混用迹象；针对 Agentd 包的 scoped clean 后，该报错消失。native-agentd-02/03/04 仍出现三个明确依赖缺少 rlib format 的错误。已保存原始 build.log、执行收据、实际 extern 路径、相关 fingerprint/rmeta 诊断和限定包清理前后清单。

一次独立工具调用的清理之后，旧缓存路径又以旧 mtime、新 ctime 出现；本轮没有建立其重新出现的行为主体或原因。最后在同一执行中做严格三包清理并立即 native05 构建，构建完成后保留独立执行 ELF，最终构建及真实运行通过。清理预览的两次 scope guard 停止、早期测试/Clippy 失败和 sandbox TCP listener 拒绝都原样保存，未被成功日志覆盖。本轮不是 clean-cache 或最低资源资格测试。

## 远端门禁与下一实现

归档内 `r9-evidence/ci/final-heads-checks-101140.json` 保存 10:11:40–10:12:01 UTC 的精确状态：desktop #193 的 46dc 有 4 checks queued；新 history 的 transport job 已生成但其 ARM64 原 owner 依赖任务未生成。owner #2815 的 2be 有 6 checks queued；blocking CI 与 Architecture run 为 pending / 0 jobs。已生成的 10 jobs 均未获 runner，原因未建立。

`r9-evidence/ci/root-ready-remote-observation.json` 的稍后 branches/main 响应确认 owner 主干保护含 `CI required`、`Architecture required`，desktop 主干未设 required contexts；独立 `/protection` 端点均返回 403。分支返回的有限保护信息与不可读取的完整端点分别保留。PR 发布/ready 状态的后续更新以对应 PR 和 [publication-status.json](publication-status.json) 为准；本机 x86_64 通过不能替代该新 ARM64 工作流，也不把 R8 成功转记给 R9。

内核决策仍是沿实际 Asterinas owner 做受控增量。固定 [G1 源审计](../../../docs/agents/R9_G1_OWNER_SEAM.md) 针对 `01225ab0a20a9f25dd8313a7fad7652dd9154e30`，本轮没有修改、构建或运行新内核：

1. **G1-a：**普通 Linux cpu.max 与 native CAS 共用既有 CPU budget 锁内的 revision，并引入 controller incarnation 与不可逆 detached fence；旧 RCU Arc 存活不能继续代表当前授权。
2. **G1-b：**在同一真实 scheduler/资源 owner 接通运行结算、时钟域与统一 usage snapshot；保持 membership → node → budget 锁序，budget 锁内不等待 runqueue、不复制用户数据、不分配。
3. **G1-c：**最终 Process / exec 镜像身份确定后，由可信 init 绑定管理权限和独立观察权限；open、继承 FD、普通 exec 不增权。
4. **G1-d：**同一固定内核实现并验证 QueryAbi、ReadUsage、InstallBudget、QueryDelivery、RetireThrough 及撤销、去重、copyout 故障、退役；随后才进入真实 Hepta 的 G2。

当前源树只实现 QueryAbi，另外四个已知 HOS2 操作仍返回 EOPNOTSUPP。现有有限 cgroup 配额证据不能把 G1/G2 升格为通过。若固定 W0/W1/profile 出现局部修复无法解决的可复现结构反例，再比较 OSTD 上层替换；只有 OSTD 本身也存在被证明不可修复的边界冲突，才进入完整自建 Rust kernel 的独立论证。AI native 的名称本身不构成重写理由。

## 证据入口与校验

- [acceptance-summary.json](acceptance-summary.json)：本页的机器可读索引与明确未执行项。
- [history-runtime.json](history-runtime.json) / [history-execution.json](history-execution.json)：真实运行的 38 条记录及外层执行收据。
- [history-runtime-independent-review.json](history-runtime-independent-review.json) / [history-runtime-contract-review.json](history-runtime-contract-review.json)：两路独立复核；后者附原始日志行与公开测试 key 签名核对。
- [native-agentd-build.json](native-agentd-build.json) / [native-agentd-review.json](native-agentd-review.json)：实际最终构建和 rustc/ELF 身份。
- [owner-final-validation.json](owner-final-validation.json) / [owner-final-review.json](owner-final-review.json)：各次 scoped 测试、最终 fix/fmt 与最终源码差异。
- [archive-parts.json](archive-parts.json) 与 [archive-parts](archive-parts/) 保存完整归档的 16 个有序分卷：[restore-evidence.py](restore-evidence.py) 可恢复 `raw-evidence.tar.xz`，共 321 份原始材料、24,308,524 B；SHA-256 `4f8ae8d38933ff594d1e3c84db30f8a9efe2457276f08d1ea84ab4e1e85c2e4f`。
- [raw-evidence-manifest.json](raw-evidence-manifest.json)：每个归档成员、20 份 primary 副本、来源及省略项的摘要；[artifact-manifest.json](artifact-manifest.json) 校验本目录交付文件，自身明确排除以避免自引用。

归档采用 tar.xz，以原样保留所有诊断 ZIP 并压缩重复内容；完整 blob 上传遇到传输错误后，改以 16 个有序分卷保存。每个分卷的 Git blob SHA 已与远端回执匹配，完整内容已实际恢复并核对原 SHA；[archive-transfer.json](archive-transfer.json) 保留这一交付过程。包装过程先重新核对固定来源、真实运行记录和五 ELF，再解读归档逐项核对顺序、文件类型、长度、SHA，并核对 primary 副本。成功后才原子放入结果目录。原始保留请求是一次性隔离测试 fixture，未包含生产 issuer、生产密钥或实际设备数据。

在仓库检出中执行下列命令即可恢复完整归档；脚本逐份检查大小与 SHA，最终核对完整 SHA，使用新输出路径以免覆盖文件：

```bash
python3 -B results/integration/2026-10-18-objective-history/restore-evidence.py \
  --output /tmp/r9-raw-evidence.tar.xz
```

[publication-status.json](publication-status.json) 的实际观察区间为 10:38:28–10:39:34 UTC：两个代码 PR 均 Ready/open。Desktop 46dc 当时为 4 success / 2 queued；旧固定 f8 的 original-agentd ARM64 任务已成功，但新 history ARM64 任务仍未生成。Owner 2be 为 5 success / 1 neutral / 2 skipped / 5 queued / 1 in_progress；两个 required 聚合检查尚未生成，正常 auto-merge 已启用，仓库选用 squash，合并尚未发生。该快照在原始归档完成后生成，由 artifact manifest 另行绑定；成功的旧 f8 任务不转记为新历史协议 ARM 资格。

未执行项包括：生产 issuer 接合、真实 hepta-submit CLI 的 lost-reply 场景、突发进程 crash/断电、调用者 anchor 联合回滚、原 Operations 效果核对、G1/G2、Android/移动设备控制，以及这一新 history 状态的 Session/Shell 渲染。新 CLI 的真实运行不是这些项的替代证据。
