# R9：主干 history 整合、真实进程清理修复与工作区原图

本目录保存 2026-10-19 UTC 完成的整合验证和对早期固定版本的独立复核。合并输入是已发布 Runtime 修复 `5060ac6976b56b32647c728991e489cdee1cce9d` 与实际 main `aab50f347deb53fc79ac13ea3b84f846fefc70a7`（PR #193）。只有 `docs/INDEX.md`、`docs/STATUS.md` 发生内容冲突；两条实现、默认原版 pin 和各自历史证据均保留。

发布提交用于固定源码与归档。下表分别给出真正执行的源码；旧运行的成功或失败不移记到新的合并 HEAD。新发布 HEAD 的完整 CI 仍须实际执行。

## 结果与实际输入

| 证据 | 实际源码与结果 | 范围 |
| --- | --- | --- |
| [完整 Rust 整合](rust-integration/root-summary.json) | `5060ac6` + `aab50f3` 冻结合并输入，60 文件闭包 `1118965074d4dccff0377a27d2e5b27829c2b45860573a31f0386c9ae296f1f2`；UI 137 pass / 2 既有字体 ignored，Hepta all-features 53 pass，九条命令均 exit 0 | 本地 Linux x86_64、Rust 1.88；含严格 Clippy、fmt、默认关闭检查及七 ELF 构建，无本次原版 Agentd/窗口/内核运行 |
| [原 A10 CI](ci-5060-a10/README.md) | run 39182491046，实际 `5060ac6`，source-guard 和 native-rust-wayland 成功 | 完整原始日志及固定源复核；真实 Weston 生命周期，Hepta 页面使用 scripted UDS fixture；未下载 17.6 MB ELF artifact |
| [原 ARM CI 失败](ci-5060-arm/README.md) | run 39182491155，实际 `5060ac6`，整体 failure | 只读原版 8 + Session 8 与五 ELF 绑定通过；Objective 外层清理失败，最终六 ELF 绑定未执行，不能判为 Objective 资格通过 |
| [成功退出清理修复](process-cleanup/README.md) | 旧生产字节双 RED，最小修复后 focused 2/2 与相关 47/47；两阶段使用同一测试字节 | 真实自有 Python leader/writer；保留 exit 0、WNOWAIT 身份锚与唯一回收，不扩大原版运行资格 |
| [实际 Chat / Console 原图](workspace-5060/README.md) | 固定 `5060ac6` 对应四 ELF，私有 X11 显示中同一 Session / Shell PID / XID，两张原始 PNG | 实际 XTEST 点击；Hepta 未配置，无任务提交、IME、设备或移动资格 |
| [原 owner history CI](ci-history-46/README.md) | run 39115155092，桌面 `46dcb2d691827f7aa3ad7903dae09d39fd338126`，原 owner `2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5`；15 检查 / 13 查询 / 5 请求尝试 / 4 publications / 0 重投 | 实际 ARM owner 与三个 CLI；传输 51 Rust + 22 Python，保留原运行日期和版本；不是整合后的 53 项或新 HEAD CI |

## 一、Rust 组合与七个实际 ELF

实际执行时间为 **2026-10-19 01:20:22–01:21:08 UTC**。`rust-integration/source-before.json` 和 `source-after.json` 绑定全部 60 个 UI、Hepta service、ABI 输入；九条命令后逐文件字节一致。`receipt.json` 保存命令、真实返回值与 ELF 摘要，`source.patch` 保存当时的合并输入；源 HEAD 加补丁才是执行来源，不能只写 HEAD 代表所有脏工作区内容。

UI 137 是完整 workspace 的通过数，另有两项既有 CJK 字体测试 ignored；Hepta 53 是本次完整 all-features 的新结果，包含 lib 2、CLI 8、history 10、transport 15、socket 16、doc 2。它们不与旧 43/51、Python 收据测试或源码审查计数混合。

| ELF | 字节数 | SHA-256 |
| --- | ---: | --- |
| shell | 24,552,760 | `f24fefa390141bfecce3a39b29a3b64c587307be0528190c826e072a24288d93` |
| session | 3,665,352 | `c0677cf8347019d73cd6e6c905a0d187d2a6c41422e4387811b04e3e42a57e6b` |
| ctl | 1,620,672 | `30b1d049de5d9f9a609288045e48d1d9183326c16e20c93afaf42d1dee683ddf` |
| app-window | 22,607,968 | `298b5d8eeaa60a9100071ca3ca6df0a4a1fbbe85c18e42b57d8bd687a559b0b8` |
| hepta-observe | 2,582,072 | `d4aaac8a3512a61702f182fee9a02342bcd5fab70115a9fa1bfe0df3f4451f9e` |
| hepta-submit | 2,305,976 | `1a055aed788cc0cc4c3b180685985def4422afeb40031b5ad3b4a94b94987da6` |
| hepta-history | 2,590,576 | `5f4297b5041e3e1198febed510bceaba38bc78e727df7fa8326cdac86ca78b51` |

七个文件都实际检查为 ELF64 little-endian x86_64。本目录记录其构建与摘要，未打包这些本地 ELF。下文截图使用先前固定四 ELF，不能将截图改标为这七个新构建产物。

## 二、ARM 失败与真实修复

旧 [run 39182491155](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39182491155) 在 Step 11 的 `run_original_objective.py` 临时目录退出阶段发生 `[Errno 39] Directory not empty: 'plugins'`。虽然内部 runtime.log 已出现 10 objective checks、7 submissions、3 Session phases 与 acceptance 标记，外层没有到达 `verify_records`、最终 report runtime_records 和六 ELF 后置绑定，因此整体失败保持为失败。

源码审查定位到公共 `bounded_command` 的 exit-0 路径：原代码直接回收 leader，遗漏同组后代清理。独立确定性反例创建真实 exit-0 leader 和同组 writer；有界 Unix socket 握手及 SO_PEERCRED/PGID 检查确认身份。旧代码回收边界仍有活 writer，收到明确握手后实际写出 `plugins/after-leader-exit`。这支持清理缺陷的源码因果；CI 没有留下实际 writer PID，不能假称该反例就是那一个 CI 子进程。

修复仅使成功完成也经过既有 `terminate_group`：在未回收的 WNOWAIT 身份锚下 TERM、限定宽限期、KILL，然后唯一 `waitpid` 回收，保留原 leader 的真实零退出状态。没有 broad pkill、重试删除目录、原版源码修改或资格豁免。原 ChildGroup、ECHILD 永久撤销与信号先于回收的规则未修改。

`red-01` 保存最初 socket bind 被 sandbox EPERM 阻止的失败，不能算完整 RED。`red-02` 是真实两项预期断言失败；`green-01` 同一测试源码两项通过。`related-01` 实际 47 项全部通过：7 process guard、6 Session receipts、12 Objective receipts、22 history contracts。五项需要完整原版 checkout 的 build-manifest 测试未在本地执行，也没有用 skip 掩盖。新 HEAD 的真实原版 CI 负责重新验证组合路径。

独立源码与原始结果复核见 [root review](reviews/root-process-cleanup-review.json) 和 [A06 review](process-cleanup/review.json)。该有限进程组机制不证明已主动逃离进程组的任意 daemon 都被清理。

## 三、实际 Rust 工作区

成功捕获时间约 **2026-10-19 01:06:36–01:08:07 UTC**。Shell PID 10、XID 4194307；Session PID 7、instance `4673be60fa79a390b65a827836b94d16`，六个快照保持同一 Session。真实 XTEST 主指针选择 Console，随后保存原始 root-frame PNG；未作裁剪、重绘或合成。图片为 1440×1000，包含实际应用窗外的黑色区域。

| 原图 | SHA-256 | 实际内容 |
| --- | --- | --- |
| [initial.png](workspace-5060/capture-02/inside/initial.png) | `418ba2bdfd86234e80bb1376c82a6d48553bea538c0e565f4a3572105b1fbbad` | Workspace / Personal / Chat，本地未提交草稿，右侧 Tasks / Context / Console |
| [action-002-screenshot.png](workspace-5060/capture-02/inside/action-002-screenshot.png) | `2d64764cc883803bb2c908c4f1c1a3989e7a681e77e8e60e733e7ed5d100687f` | 同一窗口中的嵌入 Console 与只读宿主观测，保留左侧草稿 |

首次 `capture-01` 因 xdpyinfo 缺少 libXtst 运行依赖而失败，未启动 Session/Shell、无 PNG。修复仅补任务私有依赖，`capture-02` 才成功。来源、依赖、harness 原文与派生差异、四 ELF 摘要、前后快照、真正清理结果均保留。root 和 A07 分别查看两张原图；[A07 独立 review](reviews/a07-native-workspace-review.json) 在冻结截图归档后单独加入。

可见的中文像素来自任务私有固定 Noto 字体，未发生 IME 输入。此项不使两项 ignored 字体 Rust 测试、既有 XIM caret 失败、Wayland 输入、GPU、Asterinas 显示或 moto XT2363-4 移动验证变为通过。

## 四、原 Hepta 历史查询的资格

默认原版仍是 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`；f8 没有 ObjectiveAdmission RPC。已合入 PR #193 使用独立 [OBJECTIVE_HISTORY_CONTRACT](../../../services/hepta-os/OBJECTIVE_HISTORY_CONTRACT.json) 指定的原 owner `2be5fc0` / tree `f4ef891d43baf90d6eebd29921a5ed03222ef3ab`，其祖先是 f8。默认观察/提交 contract 保持原 pin。

[源审计](reviews/r9-main193-owner-history-review.json) 跟踪真实 state_control → ObjectiveRuntimeHost::admission_history → 既有 Mutex<ObjectiveHostState>::read_publication → DurableRunStartJournal 已恢复内存索引。查询不重新 open/recover/append/truncate，不要求停止正在服务的 owner；停止 owner 仅用于特定故障注入或离线核对。

[run 39115155092](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092) 的实际日期是 2026-10-18，复核日期是 2026-10-19。原日志和收据确认 15 检查、13 history 查询、5 请求尝试、4 publications、0 重投，运行中的 owner 跨四个明确 spawn。丢回复场景由 probe harness 制造，不冒充 submit CLI 被杀测试；publication 与当前 RunStatus null 同时存在。保留请求、anchor、查询输入输出及原 journal 字节；下载的两份小 ZIP 由 API 长度与 SHA 核对，未下载约 90.6 MB ELF 包。CI 完成原版 36 文件/锁及五 ELF 绑定；独立本地检查范围在该子目录 README 和 review 中逐项记录。

这证明已知准确请求的历史 publication 查询，不证明生产 issuer 接入、首次发送前原请求/anchor 存储、UI 历史投影、模型 turn、Operations K↔D、最终使用授权、G1/G2 或设备效果完成。后续仍按 [S1–S5](../../../docs/agents/R8_NEXT_SLICE.md) 实现。

## 归档规则

`import-bindings.json` 保留先前子归档的逐字节导入校验；子目录原 SHA256SUMS 未重写。根 `MANIFEST.json` 与 `SHA256SUMS` 覆盖最终归档内容，`publication-inputs.json` 绑定最终候选中的 Rust 闭包与 Python 修复。原始日志、JSON、补丁、ZIP 和 PNG 保留原始字节，不能为通过 whitespace 检查而规范化。整体归档可能包含旧 CRLF/空白 EOF；代码与新文档的 whitespace 检查单独记录。

`environment/rust-dist-cache-reclaim.json` 记录一次仅对已核验、可重新下载的 Rust 1.88 安装缓存的清理，以恢复被磁盘空间守卫停止的后续 A04 验证；已安装工具链、源码、原始结果与 ELF 均保留。A04 自身结果由其独立集成归档记录，不混入本目录测试计数。
