# R8：可信 ObjectiveStart、原版 run 投影与真实桌面

**本轮已实际完成：独立可信宿主 CLI → 固定原版 Hepta 的 ObjectiveStart 准入与 journal → 持续 Session → 同一个 Rust Shell 窗口的三个阶段。** 原版运行使用隔离测试 issuer；生产签发来源、模型 turn、Operations dispatch、设备效果和目标 OS 尚未因此取得资格。

交付为 [PR #192](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/192)。代码发布提交为 [`ca5e7d8473690df1bf7636de0808e58414c40abe`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/ca5e7d8473690df1bf7636de0808e58414c40abe)，与实际集成执行输入 `25298f5d87cf3db90deefe9c0405ecd241dc6581` 具有完全相同的 tree：`9584997da412dd10c0960f69011b40a4b26d2862`。后加的文档和证据不冒充一次新的编译。该代码提交的两个父节点是主干 #191 的 `89e06fa83b6614e9b20ea946b4399b0ac5293f4b` 与 [#190](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/190) 的 `c4d4224c9daf1a5b22997930000f43001525d531`，工作区候选的开发历史完整保留。

## 1. 实际结果与证据入口

| 项目 | 实际结果 | 原始记录 |
| --- | --- | --- |
| 原版 Agentd 新构建 | 原始 f8 checkout/manifest/lock 不变；Rust 1.95、locked、dev-small、jobs1，05:40:13–06:22:34 UTC 实际成功；最终 ELF 328,940,800 字节 | [native build](native-agentd-build.json)，原日志见 raw archive |
| 外部 Objective probe 新构建 | Rust 1.95 locked/offline 实际链接；736 个解析节点 = 735 个原版共享 package identities + 外部 root。06:15:12–06:33:16 的经过时间含等待原 Agentd 的 Cargo artifact lock，不能算作纯编译耗时 | [probe report](probe-build.json)、[执行绑定](probe-build-execution.json) |
| CLI/transport 回归 | 冻结服务输入上 41 passed：2 library、6 CLI、15 Objective socket、16 read-only socket、2 compile-fail docs；严格 Clippy、默认 feature-off check、fmt 通过 | [CLI 检查](cli-checks.json) |
| 实际运行使用的 CLI | 06:25:08–06:25:15，在集成源重新构建 hepta-observe / hepta-submit；源输入与原测试输入核对后用于原版运行 | [CLI 新构建](cli-build.json) |
| 最终整树 UI | 精确 25298 / UI tree `42857c1bda95681f0c482fef8eb8da0f53979020`；125 passed、0 failed、2 项既有 CJK ignored；workspace/all-target Clippy `-D warnings`、fmt、workspace bins build 全部通过 | [UI 构建与完整回归](ui-build.json) |
| 原版 core 运行 | 06:35:12–06:35:19 UTC，10 个核心检查、7 次明确提交尝试、20 个运行记录，exit 0 | [完整 report](core-runtime.json)、[构建来源与执行](core-execution.json) |
| 原版 Session/Shell 运行 | 06:36:27–06:36:46 UTC，另一次完整 10 检查/7 尝试；增加 3 个真实 Session 阶段与 2 个 Session 停止记录，共 25 个运行记录，exit 0 | [完整 report](session-runtime.json)、[执行绑定](session-execution.json) |
| 真实可见窗口 | 一个 Shell PID、一个 XID，三张实际 XGetImage PNG；阶段前后通过真实 UDS/SO_PEERCRED 读取快照，root 与独立 UI 审阅者逐图检查 | [capture receipt](capture-receipt.json)、[namespace](namespace.json)、[逐图人工结论](visual-review.json) |
| Python 判定器与新 CI 步骤 | 原 Objective receipt parser 12 项通过；从最终 A10 workflow 提取并实际执行的新 capture contract block 10 项通过 | raw archive 的 `receipt-contracts-01/`、`a10-ci-step-01/` |
| 文档与集成边界 | 2026-10-18 06:59:53 UTC 实际运行原 tests/spec，35/35 通过；UI 子树不变、根 README 0 字节，编译后 tracked delta 只有 Markdown | raw archive 的 `final-doc-validation/` |

这些分母分别描述 Rust 测试、Python 契约、原版场景及实际截图，不合并成一个“全系统测试数”。独立审查的输入核对项也不算新运行测试。

原版固定提交为 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`，tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45`，Cargo.lock SHA256 `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389`。整个构建和运行保持该 checkout 清洁。外部 probe 只省去相同目标且未使用的 SSH tungstenite patch 别名；保留实际 HTTPS patch/pin，原版 manifest/lock 未修改。解析清单和原始 metadata 输出随包保存。

## 2. 交付的产品行为

### 独立可信提交

`hepta-submit` 是默认关闭 `objective-transport` feature 下的独立可执行程序。可信宿主显式给定端点、AgentId、spawn generation、peer UID/PID 和 request ID，并从 stdin 提供既有 issuer 签发的原始紧凑信封。它保持信封原始字节，执行一次有界传输，输出一条有界 JSON 收据；结构校验不代替原 owner 认证。

程序不签发、分配新的 run ID、自动重试或持久保存请求。stdin 读取需要 EOF；调用者在首次发送前保留原请求，并对整个子进程设置期限，不能把传输的五秒上限误当作等待 stdin 的上限。已可能送达但缺少确定结果时保留 SubmitUnknown。stdout 丢失也不能据此重发；exit 74 只说明 CLI 无法交付输出。

默认观察库、hepta-observe、Session 和 Shell 不获得提交接口。工作区的 typed 本地草稿、上下文引用和私有 v2 导出仍是本地数据。#190 的工作区源码及其回归已纳入整树验证；本轮三张新图验收的是 Runtime 页面，不能外推为完整聊天、全部键盘交互或生产 objective 按钮验收。

完整接口、退出码、有限错误和上游身份字段见 [OBJECTIVE_TRANSPORT](../../../services/hepta-os/OBJECTIVE_TRANSPORT.md)、[运行手册](../../../services/hepta-os/RUN.md) 与 [当前 client 契约](../../../services/hepta-os/CONTRACT.md)。

### 指定 run 的观察

可信 launcher 可额外提供 `TRILL_HEPTA_RUN_ID`，限定为 1–128 字节 ASCII 标识；仍须具备原来四项可信 Hepta 连接配置。Session 使用既有持续 ObserverClient，在独立的 run 采样时钟上读取原版七字段投影。没有配置 run 时，整个可选 JSON 字段省略，保持旧快照格式。

run 卡片区分 observed、stale、projection_missing 等状态；断连保留最后成功观测和观测中断提示。原版当前内存中没有该 run 时，只能说当前投影缺失。该状态既不证明未受理，也不证明持久结果丢失、任务恢复或设备完成。

已知 run 的新鲜度使用保守总年龄：**Session 单调样本年龄 + 完整 IPC RTT + transport 真正收到响应后至绘制的经过时间**。总和必须不超过 7,000 ms，原始墙钟采样年龄也须通过检查；7,000 ms + 1 ns 已过期。相同 Session/run/sequence 的新锚点取推进后旧上界和新上界中的较大值，重复帧不能恢复年轻年龄；缺少年龄、倒置时间、序号回退、身份不匹配或溢出均保持未知。runtime health 仍保留其既有墙钟与真实本地 receipt 检查，不能将 run 的新规则泛化成所有字段均已同样改造。

源码和技术边界见 [HEPTA_OBSERVER](../../../support/ui/HEPTA_OBSERVER.md)、[OBSERVATION_FRESHNESS](../../../ui/shell/OBSERVATION_FRESHNESS.md) 与 [CHAT_WORKSPACE](../../../support/ui/CHAT_WORKSPACE.md)。

## 3. 原版核心检查：哪些结果确实发生

两次运行各执行以下同一组核心检查。首次不启动桌面；第二次加上持续 Session 与同一 Shell 三阶段。

| 检查 | 实际断言与解释 |
| --- | --- |
| compiled_original_admission | 原始签名通过原版认证并持久准入，run phase=admitted，terminal_observed=false，响应/运行代际与原 owner 相符 |
| exact_replay_same_publication | probe 的原请求生产者明确再次提供同一个保留信封；原 owner 返回 idempotent=true、相同 publication 与 journal。不是 CLI 自动重试 |
| explicit_abstain_durable_without_run | 原 owner 持久受理 explicit abstain，但 RunStatus 为空；证明受理与运行中投影不是同一事实 |
| invalid_signature_owner_rejected | 完整请求帧实际送达，原 owner 拒绝，journal 不变；CLI 如实返回 SubmitUnknown / owner_request_rejected，未把泛化错误改写为未发布 |
| body_generation_fenced_before_send | 信封 body 与可信 spawn 不符，在发送前拒绝，bytes_written=0，journal 不变 |
| revoked_issuer_owner_rejected | 隔离 issuer 的公钥登记被撤销；完整请求送达后被原 owner 拒绝，journal 不变；生产 issuer 未触碰 |
| owner_restart_retains_historical_journal | 原 Supervisor 替换 Agentd，PID/spawn/current 换代，持久 journal 保留；旧 run 的新内存投影为空 |
| old_spawn_not_accepted | 新 owner 仍 ready、身份不变；带旧 spawn 的完整请求得到明确 protocol_mismatch/unknown，且旧 run 仍为空。不是把无关 transport failure 当作代际隔离成功 |
| original_journal_matches_receipts | owner 受控停止后，用原公共 API 和只读 File/已确认 anchor 检查两个原始记录、零 conflict。原 append 的 exact replay 在写入前返回 IdempotentReplay，并绑定真实 publication/chain/sequence；一字符合法 hex 的负对照被拒绝；journal hash 不变 |
| controlled_stop | 原 Supervisor 管理的进程受控停止；Session 和图形测试各自保存独立的清理记录 |

原 journal 的一般 recover 可能持锁并截断未确认尾部。这次检查只在 owner 停止后使用只读文件；遇需要修复的尾部必须失败。它没有创造在线持久结果查询服务。固定 f8 的 RunStatus 仍只读当前内存，不提供 ObjectiveStart 持久结果查询 RPC。

## 4. 同一真实 Shell 的三阶段

Shell 始终为 **PID 323732 / XID 2097155**。第一次 Session 为 PID 323665、instance `5982ef6aeaa50d9ad7645cd2c5ebec56`；第三阶段显式替换为 PID 323923、instance `9e58476c6fb8dc00a30d46379a488460`，使用同一测试 runtime/socket 路径。两个 Session 的 worker/身份、每张图前后的 SO_PEERCRED、原版 PID 和阶段 ACK 均在原始记录中绑定。

| 阶段 | 实际 owner 与界面结果 | 原图 |
| --- | --- | --- |
| compiled_run_projected | Agentd PID 323523，spawn 1/current 2；指定 run 为 admitted/revision 1/generation 2/epoch 1/terminal false；界面显示 OBSERVED · READ ONLY | [阶段 1](phase-1-compiled_run_projected.png) |
| old_endpoint_run_stale | 原 owner 已被替换，旧 Session 保留最后成功来源和 run；显示 STALE · CURRENT RUN STATE UNKNOWN 与观测中断提示 | [阶段 2](phase-2-old_endpoint_run_stale.png) |
| replacement_run_projection_missing | Agentd PID 323803，spawn 5/current 6；新 Session 健康观测恢复，但旧 run 当前投影为空；界面显示 PROJECTION MISSING · CURRENT RUN STATE UNKNOWN，并说明受理与持久结果仍未知 | [阶段 3](phase-3-replacement_run_projection_missing.png) |

阶段 2 的 run last_observation 与 last_attempt 在截图前后保持一致，源年龄从 3,221 ms 推进到 5,939 ms；独立 health 轮询时间可继续推进。阶段 1 截图发生于持续采样之中，不能要求阶段 1/2 两张 PNG 的采样时间和 sequence 逐字相同。阶段 3 的新 Session 首次得到 null 时没有旧 last_observation、没有 sample age，gap=false；不会制造一条虚假的成功历史。

捕获使用本轮显式 `/usr` 依赖清单、私有 Xvfb/Xauthority，以及 user/mount/network/IPC/UTS 隔离，保留共享 PID namespace 供真实 peer 核对。无 cookie 的 display 客户端实际被拒绝。收尾记录 Shell 为受控 SIGTERM/reap（returncode -15），Xvfb returncode 0，外层 namespace exit 0。此证据只证明 helper 管理的子进程收尾，不授予任意后代进程的完整父死亡清理保证。

**实际可见限制：**三张图顶部 `Objective submission unavailable` 后的中文后缀出现缺字方框。关键英文 Runtime 卡片、状态、run ID、代际及未知语义可读且未被遮挡；本轮只通过 English Runtime 卡片的视觉范围。既有中文/IME 历史资格不转移到这个不同字体环境，也没有验证物理显示、GPU、Wayland 像素或移动设备。

## 5. 运行使用的真实 ELF

| ELF | 字节数 | SHA256 |
| --- | ---: | --- |
| original codex-hepta-agentd | 328940800 | `51b18242912ac9c4694d2174da8ed510070b7b6d6689f008177bc11349f6cc5a` |
| original-objective-probe | 36796104 | `37a46986eb9a66394d34d9331101ee2b37e9963737973ce5509b05aa5635a179` |
| hepta-observe | 14476304 | `7e04a64b79a4e66c07f1fb5ff861284d4b2c61b38b6fd0e48bedae67f3255c8a` |
| hepta-submit | 14271896 | `7f29927f783bba469d8f08bdd452b427ecf4edd75a43c34c0efd2928068bf94b` |
| trill-session | 18461416 | `67a283c1eb2211df7e5433a8ace2c0f8078f1cf0b92728232d85af2fdecb5b7e` |
| trill-ctl | 7982528 | `4cee100fb6839ccc0260a2a0f46a3b6086f6ed0397a667d6a07d92bfd7ede0ab` |
| trill-shell | 142690776 | `93ee96b6ad1d1bcf5d3ddfabff3eacc1b7e49a4d894274c8bcea888b7bab0fdb` |

UI receipt 记录运行所需的 Shell/Session/ctl 三个 ELF。完整 workspace bins 构建另包含 AppWindow，但本轮 receipt 的 helper 使用了错误的可选名称 `trill-app` 并跳过不存在的路径，所以没有给 AppWindow 生成第四条 hash 记录；不将“三个已记录 ELF”写成“四个均有 receipt”，也不授予未启动的 AppWindow 运行资格。早期 UI leaf build 的不同 ELF hash 保留在 raw archive，不能替换本表的新集成 ELF。

## 6. 修复和失败记录

- 旧 A10 CI 的自有子进程取消测试期望 Running，实际先收到 Failed。原日志没有记录 spawn errno，不能确定为 ETXTBSY 或声称子进程已经启动后退出。fixture 改为当前已编译 Rust test executable 与私有 UDS READY/peer PID 握手，随后沿真实 Session Launch/Cancel/kill/reap 走流程；生产启动语义未变。leaf 源上 12 轮、每轮 27 项的并发测试及最终整树回归均保留。
- CLI 首轮 non-UTF8 失败发生于源输入在编译期间变化的非冻结尝试，不能作为有效的冻结 RED。冻结 fbaa 的 41 项成功、源前后不变记录单列。
- UI 首轮编译、普通 sandbox 的 socket/信号权限失败、Clippy 的大枚举提示及实际授权环境中的通过日志全部保留。不是把环境拒绝改写成产品测试通过。
- 单调年龄修复后，一条旧边界测试先用固定 now 做 expire、再用稍后的真实 now 做 snapshot，确实越过 7 秒。测试改用相同受控 snapshot_at(now)，保留 7,000/7,001 ms 断言；没有放宽界限。
- 原版 native build 01 在 offline 阶段因缺少原来锁定的 Git runfiles 依赖退出；native build 02 取回相同 pinned 输入后完成。原版 5 条编译 warning、实际资源/缓存处理与完整构建日志均保留，不宣称零 warning、冷构建或最低机器配置。

## 7. CI、CPU 修复和后续资格

本轮 A10 workflow 新增的 10 项 capture 契约 run block 已在本机按精确脚本实际执行。ARM original-agentd workflow 保留旧只读/Session gate 的五 ELF artifact，并新增 ObjectiveStart + Session 六 ELF artifact；新增 bundle 校验 ELF64/LE/AArch64 machine 183、实际 runtime report 和来源 hash。两份 bundle 分别按自身 package outcome 上传，后一个 gate 失败不会吞掉前一个已成功的产物。该 ARM CI 不启动 Shell、不捕获像素。

本地 workflow shell/Python 语法检查、Linux x86-64 原版运行和远端 ARM 执行是不同结果。PR #192 的代码头、新文档头、merge 头各有自己的 GitHub CI；只有精确 head 的实际完成才能标记通过。发布时读取的状态见 [publication](publication.json)，后续状态可在 PR 的 Checks 查看。

独立 [PR #191](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/191) 已修复 A06 奇数周期的测试 oracle：正确剩余额度为 `period - period / 2`。只改 cfg(ktest)，生产函数字节保持一致。本轮完整客体框架报告 OSTD 221 passed，其中 3 条原 VMX/EPT 路径为显式 soft skip，至少 218 条实际执行；aster-core 160/160、零 filter/skip；各 raw exit 33。详见 [A06 原始验收](../../organ-backend/2026-10-18/a06-odd-period-oracle/README.md)。#191 merge `89e06fa8` 的 CodeQL、host-evidence、exact-kernel-ktest 三项后来已全部 completed/success，见 [后续 CI 读回](pr191-merge-ci-success.json)；较早 [queued 发布记录](pr191-publication.json) 原样保留。没有因为测试 oracle 修复再宣称重跑了生产 release ELF 或一般 SMP/设备场景。

下一切片已细化为 [R8_NEXT_SLICE](../../../docs/agents/R8_NEXT_SLICE.md)：S1 接已有可信 issuer 和首次发送前的原请求保存 owner；S2 由原 owner 提供准入历史与效果终态核对；S3 接原 Operations 的 K↔D 持久投递、最终使用授权与受限 OS adapter；S4 在同一 Asterinas 内核实际跑通五操作和单任务 CPU 预算；S5 再执行真实 Hepta 到该内核的 G2。当前 HOS2 QueryAbi 之外的四个效果/历史操作仍需闭合。

这次结果支持继续受控增量 Asterinas。是否另建 Rust kernel，应由具体不可修复接缝、受限原型的等价测试和迁移成本决定；桌面变成 AI 交互入口本身不是重写内核的依据。当前产物是 Linux host 上可运行、可观察原 Hepta 准入的交互基础，还不是能完整控制桌面/移动硬件的 AI native OS。

## 8. 文件、复跑与完整性

[acceptance-summary.json](acceptance-summary.json) 提供机器摘要；[raw-evidence.zip](raw-evidence.zip) 保留实际构建/测试日志、执行 helper、原始输入 hash、两轮 journal/封套/公钥登记、Session 快照、精确阶段 ACK、图形命令及独立审阅。实际运行的签名私钥未落入归档；Xauthority 私有 cookie 和庞大可再生构建缓存也未打包。三个 PNG 以单独文件交付。

[raw-evidence-manifest.json](raw-evidence-manifest.json) 给出每个 ZIP entry 的字节数/SHA256 与原 scratch-relative 路径；[artifact-manifest.json](artifact-manifest.json) 覆盖本目录除自身外的文件。原 receipt 保持原字节与原绝对执行路径；在另一台机器复跑应按手册替换本地路径，不能照搬 PID/UID/短期信封或历史授权。

构建与 original-owner 复跑入口见 [ORIGINAL_OBJECTIVE](../../../tests/integration/hepta/ORIGINAL_OBJECTIVE.md)；真实窗口复跑入口见 [ORIGINAL_OBJECTIVE_SHELL](../../../tests/ui/ORIGINAL_OBJECTIVE_SHELL.md)。预构建 probe 路径必须由调用者提供原 build receipt/source/ELF 绑定；本轮的实际 runtime helper已逐项核对，单独传入一个任意同名二进制不能获得相同资格。
