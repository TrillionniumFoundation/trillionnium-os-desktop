# 当前状态

## 2026-10-19 R10：真实 G1-a owner、普通产品、逐头 CI 与安全债务

**真实 CPU owner 的一次 metadata 绑定、同锁 cpu.max revision 和不可逆 detach 已有内核运行证据；生产仍未调用绑定，HOS2 保持 QueryAbi-only。** 原 0c 基线的最终 107afb 已完成六个普通 CI checks 与实际原始产物复核。主干随后通过 #196 前移到 e15，本轮已保留 Runtime/进程边界和 A04 新手册，机械合成 local `1ca738c6310c50565804c2ea2a5d413a74bbe80a` / remote `1c05412e2b340bbc8cd2b8a3389ae0ecce538991`，tree `2b873aa43445c8a02351f5900074a38c6fa4820d`；[新组合完整CI与实际产物](../results/integration/2026-10-19-g1-owner/g1-remote-ci-1c054/README.md)也已独立接受：六checks全部success、普通boot/QueryAbi的三个6,397文件快照逐Git一致。03:59:41 UTC已由另一维护者合入同tree主干 `71ce079c3218a8692476e4113b60c9d2c0d2a172`；[独立merge复核](../results/integration/2026-10-19-g1-owner/source-publication/main-sync/independent-merge-tree-review.json)不另计post-merge运行。

完整开发交接、失败、来源和可恢复原始材料见 [R10 报告](../results/integration/2026-10-19-g1-owner/README.md)。

| 本轮范围 | 实际结果与边界 |
| --- | --- |
| 真实 G1-a owner | [具体手册](ASTERINAS_CPU_OWNER_G1A.md)记录 private once-bind、原 IRQ 预算锁、同值写 revision、无效输入不变、替换/删除不可逆 detached、极值和 indeterminate。cpu.weight 不在本轮 revision；Process/exec 可信授权、结算/BOOTTIME 与完整 G1 未闭合。 |
| 初始真实失败及修正 | be6 完整 core build 报 E0308、工作根锁被完整 component metadata 隐式改写；原失败无 guest。六个 no-deps 反证及完整 metadata 复现查明具体调用，保留原 Git seed 并引入明确工作派生锁和完整 --locked。47 项独立静态门禁为 7 正/40 拒绝，不计内核运行。 |
| 固定 12e 的两个内核目标 | core **179/179**、0 failed/filtered/soft skip，十项新 owner 回归各成功一次；OSTD **221 reported passed**，3 VMX/EPT soft skip，实际下界 218。两个目标共报告 400、实际下界397，四个2,980输入map逐Git/字节一致。没有执行完整上游crate矩阵。 |
| 普通产品三轮 | 85b attempt01 raw 中有13个HEPTA标记，但 C 输出分帧与严格完整行验收不匹配，另有 untracked OSDK 残留，整体failed。4e attempt02 build因File exists失败、无guest。4e attempt03封闭运行普通boot/QueryAbi接受、14标记各一次、三个5,851输入快照相同、当次结束clean。后续残留再现的写者仍unknown；原false字段不改。 |
| f744 → 463f → 107afb 普通 CI | [f744](../results/integration/2026-10-19-g1-owner/g1-remote-ci-f744/README.md) G0/A03失败、A06产物通过；[463f](../results/integration/2026-10-19-g1-owner/g1-remote-ci-463f/README.md) G0/A06通过、allocator前置Clippy失败；[107](../results/integration/2026-10-19-g1-owner/g1-remote-ci-107afb/README.md) 六checks全成功并实读原日志/ZIP。其A06有8真实guest、400报告含3skip/397下界、14标记和4个有限quota；严格source snapshot只覆盖普通boot/QueryAbi区间。 |
| 四处 host 契约修正 | [bccb 原始验证](../results/integration/2026-10-19-g1-owner/g1-ci-host-correction/README.md)：ABI78、std225、portable225，Loom13+6模型与26,675+578 schedules，19锁内零计数场景；fmt/严格Clippy/bare rlib通过。重叠backend分别计数；原锁变更负例、真实前置失败和离线环境失败保留，没有放宽lint或source gate。 |
| 并发 e15 主干 | [完整Git比较](../results/integration/2026-10-19-g1-owner/source-publication/main-sync/main-integration-source-review.json)覆盖567变化路径、22个非results；最终6,397tracked，33个G1路径仅N0手册需合并双方文字，其余产品/测试字节不变。INDEX保留对方新入口；本STATUS下方e15完整历史body原字节保留。 |
| Hepta 原 owner 普通 CI | d32/#2815在[04:09:45–46冻结观察](../results/integration/2026-10-19-g1-owner/hepta-fleet-main-remote-ci/final-observation.json)中49checks已全部终态：26success/8failure/6skip/9cancel；8红为6实际job+2汇总gate，CI required failure、Architecture required success，仍open/unmerged/blocked。原远端deny日志未恢复；本机同源13拒绝=8漏洞+5unmaintained/8包，不冒充远端13。三原Bazel日志另查明helper lint及Windows编译/路径/删除边界失败，安全与Windows债务未解决；旧03:10快照原样保留。 |
| Fleet 最小修复及真实远端失败 | 原parent-1b候选3749的20文件证据保留；单一helper修复重放main f8成e770，重新41tests/严格Clippy成功。[PR #2882](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2882) remote b34同树、仅一文件；其普通scoped CI编译134包时实际ENOSPC，03:52:59失败、CI required03:53:12失败，完整测试未完成，见[独立原失败包](../results/integration/2026-10-19-g1-owner/hepta-fleet-main-remote-ci/README.md)。该lane不跑Bazel Clippy。 |
| 独立 CI 存储修复 | [Ready PR #2883](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2883) remote a8ce/local71d9同tree4688d8d，基于f8仅一workflow五行env，禁用增量和dev/test debug、Cargo编译并发2；scope/134包/命令/锁/features/nextest/timeout/required不变。[原验证](../results/integration/2026-10-19-g1-owner/hepta-scoped-ci-storage-fix/README.md)有actionlint、102个不同Python契约、18个既有小crate测试及实际compiler flags；[04:17:21原API](../results/integration/2026-10-19-g1-owner/source-publication/hepta-scoped-disk/initial-ci-and-fleet-status.json)为45checks：17success/20running/6skip/1neutral/1cargo-deny failure。原策略实际skip scoped，134包尚未重跑；deny日志读取Transport closed，不能填入旧本地13项。PR未合并。 |
| 11 模块文档 | 固定207的R9 53/225历史审查不重记。e15新增具体164行[A04主干交接手册](agents/handoffs/A04_LINUX_HEPTA_ELF.md)，列源码、依赖、命令、错误与整合；旧三个候选目录/完整手册仍不在main。A01/A06已有本轮G1具体manual；本轮[独立检查](../results/integration/2026-10-19-g1-owner/module-documentation-delta.json)核对71个INDEX模块本地目标、实读15份新版手册并核对105个一跳目标，均无缺失，不将文档存在当成产品完成。 |

**继续受控 Asterinas fork。** 固定上游源码已有ARM64 Tier2及Aarch64 OSDK支持，本项目的G1仅验收x86 QEMU；Hepta ARM Linux host历史通过不授予ARM内核/手机/Binder/GPU/SoC资格。下一步按G1-b统一结算/BOOTTIME/N0、G1-c最终Process/exec可信授权、G1-d五操作/CAS/重放/退役，随后G2真实Hepta issuer、持久请求/anchor、K↔D与Linux ELF，再逐profile接设备和UI。当前可作为受控Linux host交互候选，尚无生产桌面/手机控制资格；若出现可复现结构性阻碍，再评估复用OSTD重建上层或更深替换。

以下是新主干 e15 合入时的完整状态与历史；其中日期、来源、计数和“当时未完成”保持各自范围。原R9的47报告与321素材archive不重打包，根README仍为0字节。

---

## 2026-10-19：整合 Runtime 修复与已合入的原 owner 历史扩展

本分支在已发布 Runtime 修复 `5060ac6976b56b32647c728991e489cdee1cce9d` 上，保留并合入实际 main `aab50f347deb53fc79ac13ea3b84f846fefc70a7`（[PR #193](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/193)）。源码自动合并，冲突仅在本状态页和文档索引；两条实现与历史原始证据均保留。随后普通合并仅含文档/证据的 main `0c2bf0fc1ba473325a0266c7bd476b1ddbf66383`（[PR #194](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/194)），协调索引、状态与 S1–S5 三份文档；60 个 Rust 输入及本次 Python 修复字节未变。下列两节 R9 记录来自不同执行输入，其测试计数不合并成整合后新 HEAD 的验收。

默认原版 Hepta 仍固定为 f8；新的 Objective 历史客户端仅针对独立 contract 指定的原 owner 扩展，并未替换默认 pin。它读取既有 owner 已恢复前缀中的历史 publication；当前 RunStatus、模型执行和 Operations/设备效果仍分别判断。既有 S1–S5 的在线查询子项按该明确扩展推进，生产请求持久保存、UI 历史投影、K↔D 与 G1/G2 仍需各自实现和实际验证。

| 整合后新证据 | 已核实结果与来源 |
| --- | --- |
| 本地完整 Rust 组合 | 2026-10-19 01:20–01:21 UTC，`5060ac6` + 实际 main `aab50f3` 的冻结合并输入，60 个 UI/Hepta/ABI 文件闭包 `1118965074d4dccff0377a27d2e5b27829c2b45860573a31f0386c9ae296f1f2` 前后不变：UI **137 passed / 2 既有字体 ignored**；Hepta **all-features 53 passed**；默认关闭 check、两组严格 Clippy、fmt 和七个实际 ELF 构建通过。不是下列旧 43/51 项结果的相加。 |
| 真实成功退出清理缺陷 | `5060ac6` 的 ARM run **39182491155 失败**：只读原版与 Session 各 8 项完成，但 Objective 外层在 `TemporaryDirectory` 清理 `plugins` 时失败，未达到最终六 ELF 绑定。真实 Python 反例证明 exit-0 leader 被回收后，同组 writer 仍能写文件。修复保留 WNOWAIT 身份锚，成功也经过原有 TERM/grace/KILL 后唯一回收；同一测试 **2 项 RED → 2 项 GREEN**，相关 suite **47/47** 通过。源码因果来自独立复现，CI 没有捕获实际 writer PID；不能把原日志里的 acceptance 标记转记为完整 Objective 通过。 |
| 两张真实 Rust 工作区原图 | 2026-10-19 对已发布 `5060ac6` 的固定四 ELF，实际 Xvfb/XTEST 完成 Chat 和嵌入 Console 两页；同一 Session、同一 Shell PID/XID，1440×1000 原始 PNG 保留。该次未配置 Hepta，没有提交或设备动作；字体像素不授予 IME、Wayland 输入、移动端或两项 ignored 测试资格。首次缺少 X11 依赖的失败也保留。 |
| 已合入 history 的真实 ARM 运行 | 独立复核 [run 39115155092](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092)：桌面 `46dcb2d` + 原 owner `2be5fc0`，实际 **15 检查 / 13 history 查询 / 5 请求尝试 / 4 publications / 0 重投**，传输 51 项 Rust 与 22 项 Python 通过。查询发生在运行中的原 owner，保持 RunStatus null 与历史 publication 的区别。原版 36 输入、锁和五 ELF 的完整绑定由 CI 执行；本轮另核对原始收据与桌面输入，未下载大 ELF 包。该结果不转记为整合后的新 HEAD。 |

完整原始日志、失败、来源绑定、独立审查和两张原图见 [2026-10-19 整合证据](../results/integration/2026-10-19-main-sync/README.md)。新的 Python 修复没有改变上述 60 个 Rust 输入。发布后的实际新 HEAD 仍需重新完成原版 f8、独立 history owner 与 A10 CI；此前成功运行各自保留固定身份。以下章节作为历史记录保留，早期“尚未执行”的描述不覆盖本节新取得的事实。

## 2026-10-18 R9：原 owner 准入历史实测与 G1 接缝

**原 Hepta owner 的在线历史查询已分别在 x86_64 与 ARM64 Linux 上通过真实进程验证：受控重启后，即使当前 `RunStatus: null`，仍可核对准确原请求的持久 publication。** 默认关闭的 `objective-history` 接受原请求 owner 保留的准确签名信封，当前端点身份由可信 launcher 提供；可携带以前保存的 anchor，查询不重投、不授予权限、不恢复 run。开发与技术契约见 [OBJECTIVE_HISTORY](../services/hepta-os/OBJECTIVE_HISTORY.md)，复跑入口见 [OBJECTIVE_HISTORY_PROBE](../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)，[R9 实际证据索引](../results/integration/2026-10-18-objective-history/README.md) 保留构建、运行、独立审查和失败尝试。原 owner 改动仍作为独立 [PR #2815](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2815)，原 f8 基线和旧 R8 契约保留。

| R9 交付 | 已执行结果与当前边界 |
| --- | --- |
| 桌面历史客户端 | 产品输入 `c080896189b6d5c1e411a28b7614c8fcdc33b188` / tree `bd80279318682a2a5d0db7e1b8e2315315276d02`：51 项 Rust 测试、严格 all-target Clippy、默认关闭 check、fmt、三个实际 CLI 构建通过。10 项新历史测试覆盖严格 wire、原身份/代际、anchor 及 4096 容量；脚本化 socket 回复不代替原 owner 认证。本轮 native 运行复用了这些有源码绑定的 CLI。 |
| 原 owner 协议与 journal 接口 | 只读匹配原 RunStart 认证/body/profile 和已恢复前缀；原 protocol/ledger 的 `just test` 实际 134 passed、1 既有 production growth skipped，来源 `ee0a2e5eee299fc0f272c3ceb09ef70f2cbfaf73`；Agentd `--lib` 实际 173 passed、0 failed/ignored，来源 `d1d40f64eadd0210f5f6abc003cd479a0e1ee010`，包含 4 项新查询测试。两轮测试各自前后源码一致；307 是两次不同固定源码执行的合计，不是最终发布 HEAD 的完整 suite。原仓库要求的 scoped `just fix` 与 `just fmt --base f8` 已完成；仅对新 Published metadata 做 Box 布局修正，保留 JSON wire，既有无关自动修改已撤回。最终源码的 native 构建与运行证据另列。 |
| 最终原 owner 构建 | [native-agentd-05 收据](../results/integration/2026-10-18-objective-history/native-agentd-build.json)：最终 `2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5`，Rust 1.95.0、`--locked --offline --profile dev-small --no-default-features -j1` 实际构建成功；Agentd ELF SHA-256 为 `a8f8aefa2199a2e41c22b8251145f064e3af767ff5357475ddb527beb86761cb`。使用已有 native cache，不是冷构建或最小资源资格；此前 01–04 失败与依赖缓存修复收据保留。 |
| 真实进程与存储故障 probe | [实际 report](../results/integration/2026-10-18-objective-history/history-runtime.json) 与 [独立复核](../results/integration/2026-10-18-objective-history/history-runtime-independent-review.json) 均 PASS。桌面固定 `207ff9da7dac83c57b0cbae46c4b03ecfba3baa9` / tree `8d5de807c41090e3d987764daec9c235ebd022a1`，最终原 owner `2be5fc05`；真实 x86_64 Linux、隔离测试 issuer、15 检查、13 history 查询、5 次独立 Objective 请求、4 条 durable publication、3 次 Supervisor 重启，恢复重投 0 次。compiled/explicit_abstain、覆盖 anchor、丢回复后查询、发布后提交结果未知、重启投影缺失、实际过期、issuer 撤销和存储故障均按各自判定器通过；model turn、Operations dispatch、设备效果与新 K/D 均为 0。22 项 synthetic receipt/source-contract 检查另计，不充作上述 native 检查。 |
| 最终提交的远端 CI | desktop `46dcb2d691827f7aa3ad7903dae09d39fd338126` 的 transport job 实际 51 Rust passed（49 可执行 + 2 预期编译失败 doc tests）、22 synthetic checks、严格 Clippy/default-off/fmt 全通过；独立 ARM64 history job 于 **2026-10-18 11:28:46 UTC success**，14 步全通过，真实 15 检查 / 13 查询 / 5 请求 / 4 publication / 3 受控重启 / 0 恢复重投。99 条目原始 ZIP 已归档，五 ARM ELF 的 342,466,280 字节已独立检查。[完整 CI 接续](../results/integration/2026-10-18-objective-history-ci/README.md) 明确原运行与 10-19 恢复复核的不同日期；早先 queued 快照留在原归档。 |
| 11 模块文档复核 | [固定 207 文档审查](../results/integration/2026-10-18-objective-history/module-documentation-review.json) 实读 A00–A10 的开发、技术与验证入口；53 个表内本地链接、225 个一跳手册本地目标均存在。A00/A01/A02/A05/A06 部分职责由共享架构、ABI 或构建手册承担。A04 的三份详细手册只存在于固定 `25c681d944e4efa92f2772cf773e03ae811bc345` / Draft #8 候选，不在本轮冻结树内；不能宣称本地主干手册全覆盖。该审查未重跑任何模块测试。 |
| Asterinas G1 前置审计 | [R9_G1_OWNER_SEAM](agents/R9_G1_OWNER_SEAM.md) 绑定主干 `01225ab0a20a9f25dd8313a7fad7652dd9154e30` 的实际 owner：先同锁 shared revision + controller incarnation/detached fence，再结算与时钟，随后 trusted init 和五操作。该项是源审计，无新 kernel build、ioctl、G1 或 G2 运行资格。 |

**2026-10-19 接续：**desktop #193 在七项 checks 全 success 后已普通合入 `aab50f347deb53fc79ac13ea3b84f846fefc70a7`，保留主干先前 #195 的 CPU parser 修复；文档 #194 已改以 main 为基底。Hepta 原 `2be` 的 Architecture required / CodeQL / 合同 / Blob policy 均 success，但 scoped native cancelled 导致 CI required failure，仍按正常流程修复与验收；不能称原 owner PR 已合并。R9 的原本机材料与远端运行证据均固定旧执行源码；新增 merge 不代替再次执行。G1-a 的 CPU owner shared revision / 不可逆实例失效另在独立切片推进，尚无本节新内核运行资格。

R9 原 owner 固定为已发布 [`2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5)，tree `f4ef891d43baf90d6eebd29921a5ed03222ef3ab`，与本地最终 `00aa11c961e0046d9027f6757ff03c15762a62ff` 同树。[独立 source contract](../services/hepta-os/OBJECTIVE_HISTORY_CONTRACT.json) 绑定 36 个已审输入、原 Cargo.lock 和 f8 祖先；独立运行复核还核对了原 owner 构建、8 个 probe 输入与 12 个 client 编译输入的绑定。native05 构建区间为 10:02:35–10:10:23 UTC，运行 wrapper 区间为 10:10:52–10:16:27 UTC；runner report 的 `recorded_at_utc` 是构建前初始化时间，不能当作运行完成时间。

**实际故障的范围：**丢回复由 qualification harness 使用原协议发送完整请求并丢弃响应，不是 `hepta-submit` CLI 的丢回复故障。另一次真实 `hepta-submit` 的已观测结果是 `submit_unknown / objective_owner_request_rejected`，同请求随后查到第 4 条 compiled publication、`RunStatus: null`；`CapacityExceeded` 仅是固定源码与默认容量路径的推论，未取得该具体原始错误字节。journal 回滚和尾部截断均发生于已确认的 controlled stop 之后，由原 Agentd 在重启时恢复；本轮没有中途 crash、断电或写入中断资格。

**结果语义：**`historical_publication/compiled` 只确认历史编译 publication；原 owner 可在发布后因后续准入检查失败，当前 run 仍不存在。`conflict` 不是准入，`explicit_abstain` 不是效果完成，unknown 或当前 `RunStatus: null` 均不证明未发布。查询必须保留所用 anchor 及其覆盖范围；原 owner 仅比对已恢复的内存前缀，即使携带外部 retained anchor 也不重新读取运行中的磁盘。这里的 anchor 缺失/不匹配测试不证明可检测 journal 与 caller anchor 同时回滚。

生产请求/签发 owner 接入、准确原请求与 anchor 的生产持久保存、UI 的新安全投影、原 Operations 效果终态与 K↔D、最终使用授权、完整 G1/G2、Android/移动设备控制仍按 [S1–S5](agents/R8_NEXT_SLICE.md) 分项推进。当前源审计继续支持在 Asterinas 真实资源 owner 上增量接合；尚无必须重建 Rust kernel 的可复现反证。下面历史节保留各自实际源码、时间与资格，不覆盖本节结果。

---

## 2026-10-18 R9：Runtime 总年龄与 CLI 进程丢失边界

**本轮已修复 Runtime health 在总年龄超过 7 秒后仍显示 Observed 的实际回归，并增加两个真实 CLI 被 SIGKILL 的发送边界测试。**代码从 main `f9e306f76154590e096a42f70ce9de0a7c859e60` 继续，保留 #192、#195 的全部已合入实现；UI 最终实际执行来源为 `09cf259676e2a81a998c14f1e1fddf4cc94b80df` 加当时冻结补丁，完整 UI/observer 闭包 SHA-256 为 `d720db71872f8c263b73ab3b5ad9702a856898a32b7cfde312cfe805156d0fe0`。后续文档/发布提交不改写原执行身份，完整来源与失败见 [R9 实际证据](../results/integration/2026-10-18-runtime-process-boundaries/README.md)。

| 本轮增量 | 已实际核实的结果 |
| --- | --- |
| Runtime 的完整时钟链 | Session 从完整 poll 开始前计时，仅成功后推进样本序号。Shell 使用样本年龄 + 完整 IPC RTT + 实际 receipt 至绘制时间的总上界；8,011 ms 的真实队列/egui RED 已复现并修复，7,000 ms 边界继续有效。 |
| 同来源历史与独立 run | 同 Session 临时缺历史、同序号年轻帧、失败尝试与墙钟回拨不重新刷新旧 Runtime；新的 Runtime clock 与 known-run clock 独立，过期互不冒充。实际 Session/scripted UDS 回归覆盖慢完整 poll、独立慢 run 和连续旧 spawn 失败。 |
| 最终 UI 验证 | 最终 boxed clock 源码完整 workspace **137 passed / 0 failed / 2 既有 CJK ignored**，无过滤；严格 workspace/all-targets Clippy、fmt、四程序 bins 构建均通过，四次闭包前后相同。保留 test-01 的 fixture 编译失败、clippy-01 的 enum 大小失败和全部中间结果。 |
| 真实 CLI 终止边界 | EOF 仍被持有时终止，以及 peer 已读完整原帧但回复尚未发送时终止，均实际 SIGKILL/reap、无回执、无重试。完整 objective feature **43 passed**，含新增两项；feature-off check、strict Clippy、fmt 通过。没有输出不能合成为 NotSent 或持久未受理。 |
| 文档与模块交接 | 固定基线 A00–A10 共 11 模块都有真实开发/技术入口，53 次本地链接/49 个目标通过。新增 A04 主干交接手册，明确固定候选独立 checkout 与同 ELF 条件；A04 实现仍在 Draft #8。补 A06 实际 cgroup owner 和 cpu.max 输入契约。 |
| 历史证据补全 | R7 可恢复原文与明确缺失清单已归档；R8 ARM run 39106645234 的最终成功、原始日志和来源已独立复核。它们保持历史身份，不能替代 R9 的运行或丢失原图。 |

Runtime clock 是新增可选 wire 字段：新 Shell 接收旧帧时对缺 clock 的 Runtime 历史显示 unknown，旧严格 decoder 会拒绝新字段，因此 **Session、Shell、ctl 必须匹配部署**。源码与完整规则见 [DESKTOP_UX 第 4.1 节](DESKTOP_UX.md#41-原版观测的可见新鲜度) 和 [当前新鲜度手册](../ui/shell/OBSERVATION_FRESHNESS.md)。

本轮新增的本地运行是 Rust/实际 CLI/Session/scripted UDS/egui 测试，没有新启动原版 Agentd、捕获 compositor 像素或执行设备效果。R8 真实原版与窗口证据继续有效但只属于其固定来源。当前仍是 Rust eframe/egui 的 Linux host 开发桌面；production issuer、首次发送前的原请求持久保存、原 owner 在线结果核对、K↔D、四个 HOS2 效果操作、Asterinas G1/G2、显示/输入与移动设备接合仍按 [既有 S1–S5 工单](agents/R8_NEXT_SLICE.md) 推进。

下列历史节保留各自源码、日期、计数与失败，其中“当前”“本轮”“尚未”等仅描述该轮。根 README 继续严格为 0 字节，上游 pins 未变。

---

## 2026-10-18 R8：已合入的可信提交、原版 run 与真实桌面

**当前增量已实际完成独立可信 CLI → 原版 ObjectiveStart 准入/journal → 持续 Session → 同一 Rust Shell 三阶段窗口。** 本节绑定实际本地输入 `25298f5d87cf3db90deefe9c0405ecd241dc6581` 与同树发布 [`ca5e7d8473690df1bf7636de0808e58414c40abe`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/ca5e7d8473690df1bf7636de0808e58414c40abe)，tree `9584997da412dd10c0960f69011b40a4b26d2862`；交付 [PR #192](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/192) 完整纳入 #190 工作区候选与 #191 主干修复的开发历史。固定原版 Hepta 仍为 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`，源码、manifest 和 lock 未改。详见 [本轮完整证据](../results/integration/2026-10-18-objective-desktop/README.md)。

| 当前交付 | 实际结果与边界 |
| --- | --- |
| Rust 聊天/任务工作区 | 纳入 typed 本地草稿、精确 Session/task 上下文和私有 v2 保存/恢复；新集成树完整 UI workspace 125 passed / 0 failed / 2 既有 CJK ignored，严格 Clippy、fmt 与实际 bins 构建通过。本轮新增 PNG 只验 Runtime 页，不外推全部工作区输入行为。 |
| 可信单次 ObjectiveStart | 默认关闭的 objective-transport feature 提供独立 hepta-submit CLI，显式信任端点/AgentId/spawn/UID/PID，原封套从 stdin 输入；有限收据、一次传输、不自动重试。冻结服务输入 41 项通过，随后新集成 CLI 实际重建并绑定原版运行。Shell/Session 仍无提交命令。 |
| 原版认证与持久准入 | 新构建的原版 Agentd 和外部 probe 实际执行两轮，每轮 10 核心检查 / 7 次明确提交尝试；包括合法准入、exact replay、explicit abstain、伪签名、body/spawn 隔离、测试 issuer 撤销、原版重启与原 journal/receipt 绑定。隔离测试 issuer 通过不等于生产签发来源已接通。 |
| 已知 run 到真实窗口 | 后一轮增加三个 Session 阶段；同一 Shell PID 323732 / XID 2097155 的三张真实 PNG 已逐图检查。界面从 observed 到保留旧历史的 stale，再到新 owner 的 projection_missing/unknown；不会把 RunStatus null 当作未受理或完成。 |
| run 新鲜度 | 使用 Session 单调样本年龄 + 实际 IPC RTT + 真正接收至绘制的时间上界，组合值须 ≤7,000 ms；首个排队旧帧与墙钟回拨不能让样本重新变新。既有 runtime health 仍按其原双时钟规则检查。 |
| A06 / CI 修复 | #191 只修 cfg(ktest) 奇数周期 oracle，生产函数字节不变。完整客体 aster-core 160/160；OSTD 框架报告 221 passed，其中原 VMX/EPT 有 3 个 soft skip，至少 218 个实际执行。#191 merge 的三项 CI 已 completed/success，原始记录见本轮索引；不将它们转记给 #192 的不同 head。 |

**R8 ARM 完成后的补充复核：**[run 39106645234](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39106645234) / job `117613820420` 已于 2026-10-18 07:36:49 UTC completed/success，实际 head 为 `05a7cd23f0a4b90b154ef0c45be89093b129f767`，tree `592e13cc526a247ec4246a4cfe8458e07392d0e1`。2026-10-18 下午独立读回 API、完整 job 日志与小证据 ZIP：原版只读 8 + Session 8（六阶段）、原版 Objective 10 核心检查 / 7 次明确提交 / 三个 Session 阶段通过，Python 前置 17 和 Objective receipt 12 通过；39 次哈希核对覆盖 33 个独立源码路径。五/六输入 ARM ELF 的包装记录与报告已核对，本次未下载大 ELF 包独立重算其字节。详见 [R8 ARM 完成证据](../results/integration/2026-10-18-runtime-process-boundaries/r8-arm-completion/README.md)。这是旧固定 head 的实际完成补充，不授予后来的 R9、内核或 Shell 像素资格。

**R8 已通过的范围：**这是一条 Linux host 上真实的原版准入与可见投影链路。截图的英文 Runtime 卡片通过；顶部中文后缀在该隔离字体环境出现缺字方框，CJK/IME 和整机显示资格未通过该轮验证。原版回执中的 admitted 不代表模型 turn 或设备完成。生产 issuer 接入、原 owner 在线持久结果核对、durable K↔D、最终使用授权、撤销/确认退役、HOS2 四个待实现操作、Asterinas G1/G2、显示/输入和移动适配继续推进，具体实现顺序与完成判据见 [R8_NEXT_SLICE](agents/R8_NEXT_SLICE.md)。

下面各历史节保留各自的实际源码、日期、计数和失败；其中“本轮”“当前”“尚未”只描述该历史轮次，不覆盖本节新增结果。根 README 继续为 0 字节。

---

## 2026-10-18 上一轮 audit-followthrough：集成与有效执行证据

本轮保留 [文档 #186](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/186) 在 main 66ade4cbbe1e8d8319652d870c6c773c5efd8206 建立的 R6 实录和 A00–A10 文档盘点。[A02/A03 #185](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/185) 已合入 4339acedd2d433f838c7b5fd445709c539043a77；[A07/A10 #187](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/187) 随后正式合入 main 9a858dceb3a0ede6c3a021b9d16f3bf41e8503d5，保留原 owner 和 #157 的完整开发历史。下面分别记录本轮实际执行、匹配输入后的证据复用、历史实录复核和 A06 的实际客体验证，完整来源见[本轮证据索引](../results/integration/2026-10-18-audit-followthrough/README.md)。

| 项目 | 已确定的结果与边界 |
| --- | --- |
| A02 独立判定器与完整 pinned 验收 | #185 补齐 Python oracle 的 prior-window 上界、不可能终态与保留序号检查；没有重写已在 #181 合入的 Rust codec 修复。nightly-2026-07-21 的完整 run_acceptance.py 已实际完成 13/13 检查，success=true、not_executed=[]、输入前后不变；Python ABI 普通及优化模式各 62 项。包含实际 Rust 测试、fmt、严格 all-target Clippy、bare no_std 和编译变异检查。13 是验收步骤数，不是 Rust 测试数。 |
| A03 HistoryAck 绑定与回归 | 退役 ACK 必须由既有 original-owner authority 生成并绑定具体 namespace 实例。以进程内不复用、溢出拒绝的 tag 取代可复用内存地址，阻止旧 ACK 在新 namespace 中再次获得授权。本轮 std 与 portable-spin 各 225 项测试通过；Loom 19 个模型、27,253 个调度通过；19 个实际锁内分配场景的 alloc/realloc/dealloc 均为零。宿主 receipt 绑定不等于 durable K/fsync 或内核设备授权。 |
| G0 本地有效门禁 | 在 a0adc97b35264510fb2056bed93d46c155ffe5ff / tree 2f391cae63211e7d607d188205cf91b997077b3e 上，原工作流 16 个 run block 全部有有效结果：13 个新执行、3 个明确复用相同输入的实际成功证据。A02 的 28 个输入、A03 Loom 的 12 个输入和 allocation 的 9 个输入均核对匹配。机器摘要 success=true、source_unchanged=true。裸目标构建和 guest probe 编译分别陈述，不计为新的 guest 或设备运行。 |
| 原版 Hepta → 持续 Session → 原生 Rust Shell | 本轮重新核对已归档 R6 的源码、原始收据、阶段快照和 12 张成功 PNG；既有两轮六阶段只读链路的资格保留。本轮没有重新启动原版 Agentd、运行模型或再捕获一组窗口。首轮失败图和失败收据继续保留；实际运行来源仍是 2026-10-17 的固定提交。 |
| UI 集成与完整 host 门禁 | 实际测试对象为 be335eba60f9a511a78ff8e3af90a043d50855e2；完整 host 151 passed / 2 既有 CJK ignored，严格 Clippy/fmt 与真实进程检查通过。锁恢复测试改用 exec 后获取锁的独立 owner，验证竞争者拒绝、真实 SIGKILL/reap 和同一锁文件恢复；生产锁实现未改。首轮同进程 drop 后立即重取失败与修复记录保留；2 个 ignored 字体测试不能写成通过。 |
| UI 软件 Wayland 生命周期 | Linux Weston 13 headless 下，真实 Rust Shell 首次布局与重启、3 个独立 app 首次布局及观察到的取消通过；另一次 compositor crash/restart 中同一 Session 存活、socket epoch 改变、新 Wayland client 首次布局并确认取消。旧 client 在 compositor 丢失后 failed，没有证明旧 surface 重连。本轮 Hepta 页布局使用 scripted UDS fixture 经真实 Session 投影，不是新原版 Agentd 运行；未检查 compositor 像素、物理显示、GPU、IME 或目标 OS。 |
| A06 zombie 尾段计费 | [PR #188](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/188) 的实际测试头为 e97a30c923b1a27e1578eaaf6b39d85fe1aa5591 / tree c70e97c30b6a7808586c1a2a7db4a6860ede004e，同树发布为 9265235c4b4f375844c923cf0b0f517d119d9937；已合入 main 8ea35f55a38949f511f0855cd168dfd1d672acc8。保留仍存在的 Process cgroup 归属，仅在已 detach 的 zombie 或 Weak 升级失败时使用线程保留 lease。完整 aster-core 正向 159/159 通过，零 skip/filter，QEMU raw exit 33；受控负对照为 157 passed / 2 expected fail，raw exit 65、无 timeout，命中两项预期回归。对象回归不自动证明完整迁移/退出交错。 |
| A06 生产内核 N0 probe | 恢复最终生产源码后，新 release 内核 ELF 的 SHA-256 为 edce11ac22903da6b7b65295fb75bf07f364f227a5f7e327b489381df9500399。沿用 1000/100000 us（1%）配置和 3% 上界，1 vCPU 两轮实测为 0.769% / 1.000%，2 vCPU 两轮为 0.550% / 0.960%；四轮均 complete、无 panic，QEMU raw exit 33、runner exit 0。双核未限额 baseline 超过 145%，确认实际并行。该限定配置的 probe 保留 smp_qualified=false、hepta_hos2_qualified=false，不据此授予一般 SMP 或 Hepta/HOS2 资格；原始收据及命令见本轮索引。 |

**发布与 CI：**#188 已普通合入 main 8ea35f55a38949f511f0855cd168dfd1d672acc8，tree 6eb10ba7fa117a6669350be6be9467a7052feae8；此前 #187 已将 A07/A10 合入 9a858dceb3a0ede6c3a021b9d16f3bf41e8503d5，#157 已按完整 incorporated 关闭，不再是尚待合入的产品分支。实际 A06 / UI 执行头仍分别为 e97a30c9 / be335eba，不替换成后来的 merge SHA。A06 构建期间未跟踪的临时 manifest / pycache 观察不改变已发布提交树，原始收据分别记录，不据此宣称整个工作区均无临时文件。#185 精确 head 的 A02（run 39094060165）、A03（39094060158）、G0（39094060159）和 CodeQL（39094058499）在 2026-10-18 04:32:48 UTC 均已读回 completed/success；#187/#188 各门禁的分项状态、精确时间、workflow run/job 和结论见本轮索引。本地成功与仓库其他提交的成功不授予尚未完成的 GitHub CI 通过。

当前已验证宿主模型、固定配置的 A06 客体 N0 配额，以及固定原版 Hepta 的只读可见链路。可信 ObjectiveStart、原版 durable K↔D、撤销/确认退役、HOS2 实际设备效果、Asterinas 显示/输入和移动设备适配仍需各自实现与验收。以下历史节保留各次原始源码、执行日期和失败，不作为本轮重新执行。

---

## R6 历史实录：2026-10-17 原版运行与 2026-10-18 文档归档

**本节文档基于 main `3551e1e0e017e2973da7e2b8ab811ece25c258c0`；R6 的实际本地执行日期为 2026-10-17 UTC。**本次仅更新 STATUS、INDEX、DESKTOP_UX，保留主干后来新增的 A06 `b7a8388726b67394398431e74d2e5d2079ff375f` 和 A02 `3551e1e0`。A07/A10 产品代码仍在 [Draft #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157)，固定已发布候选为 [`89aa8fa62d30b00259cb33174260c134edf1a70b`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/89aa8fa62d30b00259cb33174260c134edf1a70b)，完整 tree `5fa4057019ee044ed9bc3337ae78d90496f8b923`，A10 owner 仍为 `45552fbd8f79ea713509908ac4b08a3fd44a95bc`。主干文档合入不表示该产品候选已合入，R6 的 UI/原版运行不为后来新增的内核代码授予运行资格。

**本轮已实际闭合固定原版 Hepta → 持续 Session → 同一个真实 Rust Shell 窗口。**旧 R5 与新 GREEN03 分别完成一次完整六阶段运行；每轮原版 8 项、持续 Session 8 项通过，各有同 Shell PID/XID 的 6 张成功截图和 6 个协调 ACK。12 张成功 PNG 与首轮失败 PNG 均有 A10、独立审查和 root 的逐张人工记录；ACK 只证明协调，不能代替像素审查。完整入口见 [R6 完整交付索引](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-r6/README.md)、[三轮原版 / Session 运行](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-original-session-runtime/README.md) 和 [13 张原图、快照、ACK 与逐图审查](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-original-hepta-shell/README.md)。

| 本轮实际增量 | 结果与资格范围 |
| --- | --- |
| 原版真实构建 | 固定原版 `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 的 native Agentd 最终真实链接成功，ELF 为 329,001,344 字节，SHA256 `f476f9bb435c5127839c48ae7135d5a6fa7695ff5253460fdd8d19d7b084d4fa`。首次 E0460、第二次资源守卫停止、缓存迁移失败和最终成功均保留；不冒充冷构建或最低资源资格。见 [原版 native Agentd 构建](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-native-agentd-build/README.md) |
| 外部消费者锁与真实链接 | 首次 `--locked` 拒绝已复现；仅在外部 probe 省去同目标、未使用的 SSH patch 别名，原版 manifest/lock 不变。实际 resolve graph 仍为 733 packages、unused patch 6→5；连续两次 locked metadata 通过，随后 probe / observer 实际链接和 2 项 Rust stale 测试通过。见 [原版消费者构建与锁诊断](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-original-session-build/README.md) |
| 持续六阶段原版链路 | Starting → Running → Draining → 原版重启后旧 Session stale → 显式新可信 Session 恢复 Running → 原版停止后 stale。旧 Session 的 PID/instance/worker 在前四阶段不变，新 Session 在后两阶段不变，原 Shell 窗口始终保留；失去原版时 Session IPC 仍响应。见 [三轮原版 / Session 运行](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-original-session-runtime/README.md) |
| 真实 Shell 与旧历史保留 | 旧轮最终保留 Running/current6，新轮最终保留实际采到的 Draining/current7；这是原版退出采样时序差异，不能作为 UI 修复的效果证明。首次 stale 后，后续失败样本的完整最后成功观测保持不变；阶段前后的快照可夹住真实 PNG 采样，不要求与事后快照逐字相等。见 [13 张原图、快照、ACK 与逐图审查](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-original-hepta-shell/README.md) |
| 可见观测新鲜度修复 | 修复旧 Observed 队列响应在 UI 暂停后误刷新本地时钟的问题。原版样本年龄与本地单调 receipt 年龄均须 ≤7000ms，7001ms 已过期。真实 RED 为 1 pass / 5 intended fail；保留误复用旧缓存的 GREEN01 失败、GREEN02 严格 Clippy 失败，最终 GREEN03 的 6 freshness + 2 layout、Clippy、fmt、四程序构建通过。见 [完整 RED/GREEN 与编译来源](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-observation-freshness/README.md) |
| 捕获判定器修复 | 首次真实尝试因 Starting 的合法 readiness 变化被旧全 health 等值比较误拒绝：仅 1 张 Starting PNG、0 ACK，原 120 秒 deadline 真实 exit1。修复只允许安全且有界的同来源生命周期晋级，保留来源、代际、历史与新鲜度约束；最终 8 项 Python 契约通过。旧失败、源文件和收据不改写。见 [13 张原图、快照、ACK 与逐图审查](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-original-hepta-shell/README.md) |
| 最终源码检查 | 2026-10-17 23:09:05–23:09:07 UTC，5 项 manifest/lock + 6 项实际自有进程守卫 + 6 项 synthetic receipt，共 17 passed；原始日志与实际执行源码分别绑定，不计为新一轮 Rust、Agentd 或 Shell 执行。见 [17 项 Python 实录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-original-session-checks/README.md) |
| CI 覆盖补齐 | `.github/workflows/a10-host.yml` 自动调用既有 8 项捕获契约。实际从提交提取精确 run block 并本地执行一次，8 passed；实际 SIGKILL/reap 检查也保留。执行来源为本地 `632f5f0b27bc4c051f1b13dbb162e3c7cb9727ef` / 同树远端 `9a9c4fac92c5b3e5595845efbea72efe869763b4`。本地执行不等于 GitHub 已完成该新 HEAD。见 [CI 步骤与实际本地执行](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-original-shell-ci/README.md) |

### 实际编译、运行与发布身份

| 作用 | 实际本地源码 | 同树远端源码 |
| --- | --- | --- |
| 旧 R5 UI 构建 | `35f379101c0863027e971ccb91faf8da71cf929c` | `1974d9a94037440da358253e1f449b395daa4b64` |
| 新 GREEN03 UI 构建 | `84f0070b6e7e01238a8dac6044748b15101c9497` | `88e9cdb124801c1d0fba5d2bb7e52a85a69a79f4` |
| probe / observer 实际构建 | `c50d7b9b688135a22ced2f7f3cbe21c3028d8e17` | `028b664b4717c4dffc03dc638fa3e9a5d7a0b52a` |
| 旧 UI 六阶段，22:56:31–22:56:55 UTC | `28843c6632fe63db6b3fecb4d05888e90976fd16` | `66dba7f40c2fa8fea2e7828ec2fd4db336bb681f` |
| 新 UI 六阶段，22:59:44–23:00:08 UTC | `145e94c364243789b88c23b1292f9d4d9ca9a0e9` | `299794f90d4557cec4ee9a7fc92c397031fced4f` |
| R6 代码与证据组合 | `47f62d68626b3c142fc176370c6f8b400fe89670` | `89aa8fa62d30b00259cb33174260c134edf1a70b` |

新 Shell SHA256 为 `62d0f304d6a3a53db4bc605e374470a924a56bfeb63387b1c12f9f245f17536a`；Session 为 `f152e6413742baa3349aded2283f9aff41bfe1bc552586aa260ade6327d5d16d`；CLI 为 `ba85b891f91a88ac3ad5240535f5dd6261c47eadbcc1bb64593add0a0aa2b598`。AppWindow 构建产物仍为 R5 的 `08c3bbe84b5d6e773f367f9751a1432eaee327bf45a5b172150f34f165342510`，没有在这两轮六阶段链路中启动；四程序构建通过不表示四个二进制都重新编译或改变。源码闭包、实际 ELF 与对应执行收据共同绑定来源，后续证据提交不冒充重新编译。

### CI 按精确提交记录

2026-10-18 03:46:18 UTC 读回：旧 `84e08165d2e753fe1fc780e1972dbab4317e8499` 的 A10、ARM、G0 均已 success。A10 [run 39075838432](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39075838432) 于 2026-10-17 23:44:03 UTC 完成，native job 实际 Rust **151 passed / 2 CJK ignored**，另 **6 项 Python 进程守卫**；该旧 workflow 尚未调用后加的 8 项捕获契约。ARM [run 39075838558](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39075838558) 于 23:11:50 UTC success，真实原版 8 + Session 8、五个 ARM64 ELF 字节核验见 [84e 原版 ARM 持续 Session 实录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-84e-arm-ci/README.md)；该 ARM CI 没有启动 Shell 或捕获 UI 像素。先前归档的 queued 快照是其当时状态，保留原记录，由后来的实际完成补充。

新发布 `89aa8fa62d30b00259cb33174260c134edf1a70b` 的 [A10 39093714607](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39093714607)、[ARM 39093714699](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39093714699)、[G0 39093714602](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39093714602) 在上述读回时均为 queued / conclusion null，不能继承 `84e` 的成功。更早 c0 的成功、f092 的 ARM 锁失败及后续 A10 成功分别见 [R6 完整交付索引](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-r6/README.md) 中的固定实录。

### 主干的新变化与下一条产品主线

合入前主干已普通合入 [A02/A03 PR #185](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/185)，到达 `4339acedd2d433f838c7b5fd445709c539043a77`。本次三份文档继续保留这些新增历史：A02 的独立 Python wire 判定器补齐 prior-window 与不可能的终态/保留序号检查；A03 的 HistoryAck 需要既有 original-owner authority 生成的私有 namespace instance tag，并使用进程内不复用的计数器避免地址复用后旧 ACK 授权新 namespace。值解析器不因此获得退役权限。该变更仍是宿主模型的 receipt 绑定，未实现原版 durable K/fsync 或原生设备效果；本轮没有重跑其门禁，具体实现见 [固定 API 契约](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/4339acedd2d433f838c7b5fd445709c539043a77/libs/os-control/API_CONTRACT.md)。

主干 A02 `3551e1e0` 补充 N0 prior-window CPU 上界、QueryDelivery 保留序号与终态语义，以及对应源码/边界用例。本轮未重跑这些用例。A06 `b7a83887` 新增线程持有 cgroup 计费快照和删除租约；这是退出计费源码补强，不能宣称最终计费 / IRQ / SMP 已通过。复核发现仍需处理的具体边界：进程已 zombie 且 cgroup 被清空，但父进程尚持有 Process、Weak 仍可 upgrade 时，尾段计费可能回落到 root，而未使用保留的叶子快照。该源码发现与后续修复/客体验证分开记录。

当前 UI 是 Rust eframe/egui/glow 的 Linux host 原生程序，真实 Hepta 数据已进入可见界面。它仍是只读运行链路：没有 objective 提交、模型 turn、可信 issuer 替换、authority/账本替换或设备效果；`TrustedReadOnlyOrganV1` 也不是 OS 沙箱。下一步以全 Rust 聊天 / 任务 / 应用工作区承载真实上下文，运行监控和控制台作为工作区内页面；可信 ObjectiveStart 适配器位于只读 organ 外，原始封套来自既有 issuer，durable K↔D、撤销与结果仍由既有 owner 提供。具体设计与错误语义见 [DESKTOP_UX 第 6 节](DESKTOP_UX.md#6-以-hepta-为核心的-ai-原生-ui)。

本轮真实窗口环境是私有 Xvfb 与软件 GL，不授予物理输入/显示、GPU、Wayland text-input v3、Asterinas 或移动设备资格。R5 XIM 的差异中文输入保留原有通过项，候选窗偏离 caret 仍为失败。根 README 为 0 字节；Asterinas `c4b7ed575b7b32773475b194d2ad41fb6d03765b` 与原版 Hepta pin 不变，原版 tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45`、原版 lock SHA256 `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389` 均保留。以下历史节的“本轮”“最终”“尚未”仅描述各自当时的源码和执行。

---

## 2026-10-17 R5 历史快照：原版 Agentd ARM 运行、Rust XIM 输入与 UID 拒绝

**本节基于实际 main `eaabd20a2ae67573f76b3a6a8f64ca7a1ea8a9c2`。**该主干已普通合入 [文档 PR #167](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/167)；A07/A10 产品代码仍在 [Draft #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157)，没有随本文进入 main。本轮组合保留 A10 owner `45552fbd8f79ea713509908ac4b08a3fd44a95bc` 的 runtime UID 检查及输入效果边界，并合入上述 main 文档历史，处理冲突时未覆盖 owner 改动。

**本轮真实被测源码**为本地 `35f379101c0863027e971ccb91faf8da71cf929c` / 同树远端 [`1974d9a94037440da358253e1f449b395daa4b64`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/1974d9a94037440da358253e1f449b395daa4b64)，tree `48433c4f1e55de53e8c298193765949996eb18a0`。构建、4 条定向回归和 UID 对照均绑定这份源码与各自原始收据，见 [构建/UID/定向回归完整归档](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/83b6a514164e29d536c5d2d4e078e04da4eeddb1/tests/ui/evidence/2026-10-17-owner-input/README.md)。UI-05 的执行 harness 另绑定本地 `02cf552485f899cfbb9cba7eeae663c7f0e8bb9c` / 同树远端 `698d1bf47fadbdd0fc18fad191b3bd5f9744101f`，tree `3a46eb76dd667a0fe54fa7b9936df93a7080d430`；其生产 UI 子树与上述构建相同，使用同一组四 ELF。不能把这些实录转记成后续最终证据 HEAD 的重新执行。本轮最终固定候选为 [`c0d5ee395cd76bcd29e8f1c912d048d19c97ce00`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/c0d5ee395cd76bcd29e8f1c912d048d19c97ce00)，与本地 `152e11969ec3981b43b1813321aa7b4ee0f051e9` 完整 tree 同为 `18bb74651753640289296ff872ee2db7e1bd6fe4`。[UI-05 及前序输入实录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/2ec3e7ab3e472b19a350d309ee2d0338d62daeb3/tests/ui/evidence/2026-10-17-real-xim/README.md) 与 [原版 ARM 运行、日志、三 ELF 核验](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/27fdf0a87b0bee3c13d1fccb876615aa5f27d9db/tests/integration/hepta/evidence/2026-10-17-original-agentd-arm/README.md) 分别保留自己的运行来源。

| 本轮实际增量 | 结果与资格范围 |
| --- | --- |
| 集成编译故障修复 | 首次真实 UI build 在 `b04a9e5c` exit101，三个新 UID 检查报 `E0433`：`host_peer` 只在测试模块导入，Linux 生产作用域缺失。`35f37910` 恢复生产导入，保留 owner 的 UID 检查；原始编译失败、格式失败及修正记录分别保留 |
| 完整 UI workspace 构建 | 13:28:31–13:28:37 UTC，Rust 1.88 执行 `cargo build --manifest-path ui/Cargo.toml --workspace --locked --offline`，exit0，生成新的 Shell、Session、CLI、AppWindow 四个 ELF；复用暖缓存的这次完整 workspace 构建不证明冷构建耗时或最低资源 |
| 四条定向回归 | Shell 3 条：synthetic 中文 IME commit、聚焦 host effect 按钮的 Enter/Space 不伪造主指针、聚焦 `Save local draft` / `Export drafts to local file` / `Restore local export` 三个按钮的候选确认不触发相应保存、导出或恢复动作；AppWindow 1 条：聚焦 Run 的 Enter 不伪造指针点击。共 4 passed、0 failed/ignored；两次执行分别 filtered 25/11。这不是旧 137 项重跑或真实系统输入法结果 |
| 严格源码检查 | 同 `35f37910` 的 UI workspace / all-targets Clippy `-D warnings` 与 workspace fmt 均 exit0；不以成功编译替代其他生命周期、字体、IME、设备或原版 Agentd 运行门禁 |
| 非 root 真实权限对照 | 两次测试脚本调用者均为 UID 1000，使用同一个新 `35f37910` Session ELF。旧 `45552fbd` 脚本因准备 foreign child directory 的权限不足而 RED；这不是旧生产 Session 的漏洞复现。修正后的脚本 GREEN：root Session 分别拒绝外属 UID 的 `0700` runtime、`0700` 子目录和 `0600` lock，同 UID 正例提供 `0600` socket；没有降低目录权限或改变系统策略来放过检查 |
| 真实 XIM 中文输入与交互 | 14:09:30–14:09:55 UTC，UI-05 记录 PASS、namespace exit0，共 23 个输入/控制动作：私有 Xvfb + IBus/libpinyin 的 XIM 路径，由 XTEST 只注入 ASCII；Shell 的 `nihao` 和 Notes 的 `zhongwen` 经候选、空格确认后，两次 Clipboard 分别严格等于 `你好` / `中文`。Shell 正常 Save/Export 产生权限 `0600` 的精确 JSON `{"version":1,"drafts":["你好"]}`；Notes 焦点跨窗往返后保留 `中文`，Session 经 fenced 取消后实际观察到同一 Notes task 为 cancelled，自有进程清理完成。23 条动作不是 23 条 Rust 单元测试，也不是物理键盘证据 |
| 原版 Agentd ARM 链接与 live gate | 精确桌面 `1974d9a9`、固定原版 `f8c9419d`，原版 Rust 1.95 / observer Rust 1.88 完成三个 ELF 的真实链接。`live_agentd_acceptance=passed`，8 项进程/只读检查全部通过：Starting、Running、有界 capabilities/events、不存在 run 读取、同进程 Draining、原版重启、旧 spawn 拒绝、受控停止。原版 source/tree/lock 前后干净且不变；未提交 objective、调用模型或执行设备效果 |
| A07 live-source 与提交语义 | 已核对固定 `f8c9419d` 的原版 Supervisor 启动、私有目录、生命周期和读协议，未发现必须先改的确定错配。实际 ObjectiveStart 由 `state_control` 调用 `objective_runtime` 中的 `ObjectiveRuntimeHost::submit`；持久发布后的失败可能是 SubmitUnknown，RunStatus 的内存投影 `null` 不证明未接收。本轮[仅修正契约与真实装配说明](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/8d81d5546b50e5cfaa611e68cb3a11a7b3a731ce/tests/integration/hepta/LIVE_SOURCE_REVIEW.md)，未装配 issuer 或新授权路径 |

四个实际 ELF 的 SHA256 分别为 Shell `81e9bcbf79c4060c3047ad0c80df711bfd855f2f47c3900522927d37404d776f`、Session `5c29cfd7f11455000d7c3d9c0cc2c58fb7fe8761ab326da34c794d0f3481924f`、CLI `920093314640ad1dd721425ec78457f4ca74c83f9c1a0a878d4ddfee4924a882`、AppWindow `08c3bbe84b5d6e773f367f9751a1432eaee327bf45a5b172150f34f165342510`。上一轮中文截图复用旧 `865ecf3` Session/CLI 的事实仍只属于历史截图，不描述这四个新产物。

**原版 ARM 运行与产物已核验。**精确 `1974d9a9` 的 [run 39037037916 / job 117408854785](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39037037916/job/117408854785) 于 14:28:31 UTC 完成且 success。15:06 UTC 下载后逐字节核验通过：456,519 字节 evidence ZIP、80,692,154 字节 ELF artifact ZIP，以及内部清单、执行 report 和 SHA256SUMS 相互一致；没有在下载端重新启动 ARM 程序。三个真实 ELF 均为 AArch64、ELF64、`e_machine=183`、archive mode `0755`。原版 Agentd 为 268,391,592 字节 / SHA256 `3e0753ab7b544ae4a76dee7df4d5c918eb7c766fc271ac9f7111bdb1979ebd6f`；probe 为 22,375,664 字节 / `60a950fe8eb7d85a65ffb16917c2a9088e89b9b13c0cd2c62e94e1a83f08c7ee`；observer 为 13,681,224 字节 / `3acf4a86268480ca481cf17a5e85205968bf8cd0e9fe2affdc37b9db8eddb48f`。它们与上面的四个本地 UI ELF 属于不同产物和执行环境。原版 source tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45`、Cargo.lock SHA256 `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389` 保持固定。

**15:17:06–15:17:09 UTC 的发布读回。**main 仍为 `eaabd20a`、A10 owner 为 `45552fbd`；PR #157 已推进到最终 head `c0d5ee39` / base `45552fbd`，open、Draft、mergeable。该最终 HEAD 的新 [A10 run 39044366490](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39044366490) 与 [ARM run 39044366482](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39044366482) 均为 queued / conclusion null。原 `1974d9a9` 的 [UI run 39037037912](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39037037912) 也仍 queued；上述原版 ARM PASS 只绑定该旧被测源码。最终候选的 UI/A07 生产源码、锁及原版 gate 与 `35f37910` 字节相同，这不表示在最终 HEAD 重跑全部 CI 通过。完整原始 ARM evidence ZIP 已固定入 Git；大型 ELF 包保留在原 workflow artifact 中，14 天保留期至 2026-10-31，不能当作永久发布包。

**失败与剩余输入边界。**真实 UI-01、UI-02 的失败分别保留；UI-02 已出现中文预编辑/候选的局部结果，不能改写成该次完整 PASS。UI-03 的脚本 PASS 保留原记录，其两个 Clipboard 同为 `你好`，不能独立排除 Notes 沿用 Shell 旧值。UI-04 的实际记录已出现 `你好` / `中文` 两个不同值，但旧 harness 未严格断言 Shell Clipboard；UI-05 补齐该断言与执行脚本字节绑定后重新执行。UI-03、UI-04、UI-05 的执行 harness 与原始输出各自保留，UI-05 的资格不转记给前两次。UI-05 仍没有解决候选窗定位：候选窗出现在 Shell 与 Notes 各自窗口的左下角，偏离文本 caret，该项仍为 failed。锁定的 [winit XIM PreeditCallbacks 路径](https://github.com/rust-windowing/winit/blob/e9809ef54b18499bb4f2cac945719ecc2a61061b/src/platform_impl/linux/x11/ime/context.rs#L344-L378)仍发送 spot 坐标，但源码注明 libX11 预编辑回调下定位不生效；[egui-winit 已转发 caret 位置](https://github.com/emilk/egui/blob/1669e52a7ccfc3489c1b0999b9ed48894a0b3887/crates/egui-winit/src/lib.rs#L866-L890)；下一步应解决匹配的输入法协议/profile，不能把该缺口误归字体或写成 IME 全面通过。UI-03、UI-04、UI-05 的被动 IBus D-Bus trace 各自只有 29 次空 `UpdatePreeditText`，没有中文 `CommitText`，也没有逐条 winit `Event::Ime` 记录；当前证据来自受限 ASCII 输入路径、前后 PNG 及应用保存/读取，不能称完整 wire trace 通过。XTEST 经真实 XIM 服务的结果不授予 Wayland text-input v3、物理输入 seat、键盘/触控、GPU、Asterinas 或移动端资格。

**原版 Hepta 的当前边界。**历史 `cargo check` 成功保留原来源；本轮原版 ARM 独立 executable link / live gate 已通过并核对实际产物。每次只读观测使用新 CLI；连续 Session worker 连接原版 Agentd 并驱动 Shell 的链路仍未验收。可信 objective ingress、原版 durable K↔D 的桌面接合、撤销、确认退役和 HOS2 设备效果链仍未闭合，不能从独立原版 gate 推定 Shell 已使用原版数据源、发生模型推理或执行设备控制。

根 README 保持 0 字节；Asterinas 与 Hepta pin 不变。下列旧“本轮”“最终”“尚未”等表述均保留其各自固定源码和当时结果，不能自动继承到本轮 HEAD。

---

## 2026-10-17 历史快照：中文软件像素、原版 Hepta 编译检查与单 ARM 门禁

**主干与候选分开记录。**本次文档基于 main `561f1e276cc02fd7a257b8f804488546ab3d2a83`；A08 已合入，A07/A10 仍在 [Draft #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157)，没有随本次文档进入 main。下面新增结果各自绑定实际源码；旧 137 项、no-op Weston、6 项清理回归及原始失败继续保留在下一节，不转记为新候选的完整验收。

本轮最终发布候选为 [`5beb3fab54fe7dd60072864276ece1ced38150ab`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/5beb3fab54fe7dd60072864276ece1ced38150ab)，完整 tree `5f44dfef259819727ab5a9b7f6011a67097ed3c4`，与本地组合 `50fa836e064f67268aafcc6d64835426f89cc90b` 相同。该候选保留 owner `566267f6` 的真实历史，PR 仍为 Draft；这个最终组合身份不替换下面各项真实执行的源码身份。 最终只读 Git 差异核对确认 `ui/**` 与实际 `a601a10` 被测源码字节一致，A07 gate/probe/services 和 ARM workflow 与 `755c635a` 检查源码字节一致；源码一致性不等于在最终 HEAD 重新执行完整门禁。

**中文切片的固定源码**为远端 [`397db55e34a3a65d50635dec6a6aae7bcd573803`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/397db55e34a3a65d50635dec6a6aae7bcd573803)，与实际执行的本地 `a601a1066f7b825ec62de57c64fbe94771429ba2` 完整 Git tree 同为 `e244dbb04f482c15cfe6b6015197fbdce7238b83`。其父组合已保留 A10 owner `566267f6cfb8861bddaeddb9423f8db0dd2dc759` 的窗口 epoch 与按键行为。新增共享 Rust 字体加载器仅进入 Shell/AppWindow；显式宿主字体、face index、32 MiB 上限、实际字形校验与可见失败诊断见[开发/技术说明](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/397db55e34a3a65d50635dec6a6aae7bcd573803/support/ui/CJK_RENDERING.md)。本轮没有打包字体或改变 Session/Hepta 协议。实际 [15 条定向测试、源码/产物收据与新旧 PNG](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/661c958650e187cf677e4d5351d87e8bc8badbc5/tests/ui/evidence/2026-10-17-cjk-pixman/README.md) 已归档，旧失败图与新图保持各自来源。

原版 Cargo 实录也保留实际工具源码：metadata 执行时桌面 commit 为 `160e11b1402a3ba6b91a50fa4c99f4a2fd100f18`；probe 和 Agentd 本体检查为 `755c635a141739c292c7a5f9755d08361feff78e`，其同树远端为 `78de7ea57cfbede31e2a9572a294a72553067884`，tree `27b31d06f822cfc7aafe5d8ddaa0802230c326dc`。原始收据不替换成后来的证据 HEAD；其中的 gate/probe 文件摘要另行核对，不能据此宣称整个新候选已运行。 [完整原版 Cargo 证据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/tests/integration/hepta/evidence/2026-10-17-original-probe/README.md) 保留 14 份原始文件和 5 份源码绑定记录，[BUILD_REVIEW](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/tests/integration/hepta/BUILD_REVIEW.md) 列出实际命令、失败、资源观察和剩余门禁。

| 本轮实际增量 | 已完成结果与限定范围 |
| --- | --- |
| 新 Shell 与 Notes 中文像素 | 两个客户端从固定 `a601a10` 以 Rust 1.88 构建；在新建私有 Weston/Pixman 上实际捕获 1440×900 PNG。Shell 的中文标签/草稿提示、Notes 的中文 TextEdit 提示经人工查看可读；保留修改前 `865ecf3` Shell 的真实 tofu 图。自动截图检查不是 OCR，人工复核单独记录 |
| 源码和产物绑定 | 新 Shell SHA256 `c8ccdf38bf5190d473d17459adddc492a8ab2eb7b9cd5ad15df97ee7d4dd9f91`；新 AppWindow `07e5cd03a43dba3f302745f695a8df3bade41bb194fe1eb1ced10710529ca8c0`。Session `3d52f8c3d61c81975a13f518810d4170e84c2c28a070684e91014567764d39c5` 与 CLI `d8adf74b743389c70d606c36ab6faaf4f1f992013a9cc593385868577b633ffd` 复用旧 `865ecf3` 产物，未改记为新构建；捕获前后四个 ELF hash 不变 |
| 15 条定向测试与严格检查 | Shell/AppWindow 字体各 4 条、Shell owner 规则 4 条、Shell synthetic IME 1 条、AppWindow synthetic IME/主指针规则各 1 条，合计 15 次真实测试执行，0 失败/忽略；两个真实字体测试显式执行 `--include-ignored`。两客户端 `--all-targets` Clippy `-D warnings`、workspace fmt 检查均 exit0；源码无漂移。没有重新运行完整 137 项或全部生命周期脚本 |
| 窗口恢复与效果按钮 | 新窗口须 Session 在线、任务 Running、PID 非零、已有 first layout，且已观察的 socket epoch **严格大于**启动 epoch；相等和倒退均拒绝。Shell 进程按钮只接受主指针激活，Enter/Space 不触发启动/新窗口/终止。该规则的测试不等于真实键盘、焦点或输入法验收 |
| 原版 probe 构建前置 | 生成 manifest 显式继承固定原版 resolver 2；缺失或未知 resolver 在创建目录前失败，原始 RED 与改后 3 项回归保留。固定 Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 的真实外部 probe metadata 为 733 packages / 733 resolve nodes，原锁 identity/checksum 子集核验通过；Rust 1.95 `cargo check --locked --profile dev-small -j1` 实际 exit0，日志 5m28s，保留原库 5 个警告。733 是无 `--filter-platform` 的 metadata 结果，不是已编译单元数或 Agentd 最小构建图 |
| 原版 Agentd 本体 | 12:39:47–12:46:37 UTC，原版 workspace 实际执行 Rust 1.95 `cargo check --locked --profile dev-small --no-default-features -p codex-hepta-agentd --bin codex-hepta-agentd -j1`，exit0，日志 6m48s；原版 source/tree/lock 前后相同且干净。与 probe 分开记录本体编译检查；尚未链接 ELF、启动原版进程或执行 `live_agentd_acceptance` |
| 原版专属 ARM CI | 候选增加一个 `ubuntu-24.04-arm` job，精确 checkout、匿名只读固定原版、隔离工具链/目录，执行原版 `run_original_agentd.py --execute`。原 8 GiB 完整门禁估计、失败退出及实际生命周期断言保留；只有完整 live gate 通过才打包三个真实 ELF。没有 matrix/fanout，也未把此 workflow 单独带入缺 A07 源码的 main |

**失败与云端状态。**首个 [ARM workflow run 39032341629](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39032341629) 在 Actions 语义校验时失败，`jobs=[]`，没有执行构建。原因是 job-level `env` 引用了不允许的 `runner` context；改为第一步从 `$RUNNER_TEMP` 分配目录并写入 `GITHUB_ENV`。真实 actionlint 先 exit1，修后 exit0；YAML、8 段 Bash 和 3 段 Python 静态检查通过，[工具来源、原始输出和两个 run 的独立收据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/5beb3fab54fe7dd60072864276ece1ced38150ab/.github/evidence/hepta-original-agentd-20261017/README.md) 已保留。修复后的 [run 39032688536 / ARM job 117396196504](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39032688536/job/117396196504) 绑定修复源码 `78de7ea57cfbede31e2a9572a294a72553067884`，已创建真实 PR job；该次已读取快照仍为 queued、runner_id 0、无 steps。这不是最终 `5beb3fab` 的运行记录，也不是 ARM 构建或运行通过。发布读回时，按精确最终 HEAD 查询 Actions runs 返回空列表，尚未观测到新 run；不将尚未出现的运行标成 queued 或 passed。原版首次 metadata 的 `rustc` 启动失败与第一次编译包装器的前置 `AssertionError` 分别保留；后者由执行端定位为 CMake 分发选择歧义，不冒称 Cargo 编译失败。后续成功记录没有覆盖它们。

**仍需实际闭合。**本次软件截图中的 Weston registry 只有 text-input v1，没有 v3 和 `wl_seat`；锁定的 `winit 0.30.13` 使用 v3，因此可读中文提示与 synthetic egui 提交测试均不授予真实 IME、候选窗、键盘/触控或焦点资格。物理 GPU/显示器、Asterinas UI、移动端、全量当前生命周期门禁仍待执行。原版源与锁前后不变，受限 metadata/check 没有降低完整 gate 的 8 GiB 判据，也没有建立冷构建资源下限。本桌面/A07 的原版 Agentd live 验证、可信 objective ingress 接合，以及接入原版 durable K↔D、撤销、确认退役与 HOS2 效果链仍未闭合；UI 沿既有 authority/operations owner 接入，不另建 issuer、授权 epoch 或效果账本。

根 README 保持 0 字节；Asterinas 与 Hepta pin 不变。下面是此前固定源码的历史结果，其中“本轮”“最终”“尚未”等措辞仅指各段当时的版本。

---

## 2026-10-17 历史快照：137 项 Rust 主机回归与 no-op Weston 布局

**主干实际交付：**[A08 PR #161](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/161) 已普通合并，merge `e962cefbb9c364e0e346aa7327919f1b0eef16c6`；其树与已核对的最终集成树 `20b2cb84087a0b90f1ac1766ad2ef1b221b8df14` 相同。[#156](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/156) 作为已被该集成承接的修复历史关闭，A08 owner 分支未改写。A08 的 184 项正常/优化模式及真实 JNI 结果和 Android 阻塞见下节。

**该历史快照的 A07/A10 组合在 [Draft #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157)。**当时保留 A10 owner `d4eeeb5e868724f9400b34e1f0c3960723ac94dd` 和协作者新增文本清洗 `a7379fa9b04a4e82b6936a84170c18f418bf3525` 的真实远端历史。实际完成该轮全部 UI 门禁的本地源码是 `9b13dfbcb006a7f8af7cccd338e03174df74bad5`，已发布同树源码为 `865ecf381dc8ddb70470ee173add9bd3b4a6a29a`，完整 Git tree `00923201e6550280e68a5ca662a8a3c3a165a29c`。

该快照最终发布 HEAD 为 `e743ee1a06956b51f86c16887f04cd4f518bcccd`，tree `c19e0e318414d24cabe4f9b70c1a1ccc55ead077`。从该轮被测源码到该 HEAD 的增量只增加原版启动门禁、进程清理回归、既有 CI 步骤和文档/证据；当时实际生产 UI/observer 与既有 fixture/源码契约检查字节未改变。完整 137 项、Weston 与 Clippy 仍绑定上面的被测源码，不伪称在最后证据提交重新执行。入口：[137 项完整记录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/e743ee1a06956b51f86c16887f04cd4f518bcccd/tests/ui/evidence/2026-10-17-rust188-owner-sync)、[该轮最终组合收据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/e743ee1a06956b51f86c16887f04cd4f518bcccd/tests/ui/evidence/2026-10-17-final-integration)、[原版门禁与清理证据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/e743ee1a06956b51f86c16887f04cd4f518bcccd/tests/integration/hepta/evidence/2026-10-17-process-guard)。

| 本轮完成的实际验证 | 结果与边界 |
| --- | --- |
| 固定 Rust 1.88 完整 host | 137 项 Rust 测试：UI 73、A07 17、support/ui 39、tests/ui 8；0 失败/忽略。实际 Session/只读 fixture、断连 stale 保留、8 个畸形 IPC、双向 SO_PEERCRED、伪造 server 零请求字节拒绝、验证后的临时进程清理、四 ELF 打包与独立回放全部完成 |
| 同源码 Weston | 真实 Shell、三个独立应用进程首 layout、取消、合成器 crash/restart、新客户端 layout，以及 Session → A07 fixture → Hepta 页的新鲜投影完成；renderer 为 no-op，不是像素/GPU 验收 |
| 同源码严格检查 | UI workspace/all-targets Clippy `-D warnings`、四 manifest rustfmt、四份锁不变、332 包 locked/offline metadata 均 exit0；没有继承旧候选的云端绿灯 |
| 本轮具体修复 | 正常生命周期代次 Starting=spawn、Running=spawn+1、Draining=spawn+2；正常晋级保留历史；实际 Hepta 页布局门禁；非默认 Cargo target 路径；窗口恢复的 Running/PID/first-layout 判据；显示文本 bidi/换行过滤；headless child 已退出时不伪称取消成功 |
| 原版 Agentd 启动工具 | 固定原版 Supervisor/Fleet/UnixProcessDriver 的构建和进程门禁已形成代码；清理改为 Linux WNOWAIT 保留身份到最后一次组信号之后再回收，6 项独立守卫回归通过，旧实现的 ECHILD 缺陷安全复现通过；没有原版 Agentd 运行资格 |
| 最终 harness / CI 组合 | 本地 `5f14fde` / 同树远端 `7e7f4d3` 再跑 6 项子进程回归，0 失败/跳过、0.199 秒；YAML 和 8 段 Bash 语法通过。既有 A10 workflow 增加固定 1.88 Clippy 与该 6 项检查；没有加入原版 Agentd 大构建 |

发布时读取的 [Actions 39030185678](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39030185678) 对应最终 HEAD，状态为 queued、无 conclusion。上面的本地执行不代表远端 CI 已通过。

失败证据原样保留。新组合首轮真实 exit101，Session 启动报 EACCES；后续采集的同 inode ELF 为 0644，修改行为方与最初发生时刻**未定位**。保留原产物后移出共享构建缓存，由 Cargo 重新生成；新 ELF 是 0755 且与旧 ELF 字节 SHA-256 相同，完整门禁随后通过。格式门禁捕获的新增测试字符串换行问题以独立提交修复。此前的 Cancel 竞态、严格 lint 和缺失 crate archive 失败亦保留，未把失败日志改成成功。

**尚未跨过的工程边界：**原版 Agentd live gate 仍是 `not_run`；11:12 UTC 的实际预检记录缺 Rust 1.95/cmake 和不足原版构建预算的磁盘，其数值只代表该时点。6 项守卫测试不是原版库编译或原版进程运行。当前 UI 是 Rust `eframe 0.31.1` 的 Linux host 原型，尚无中文字体/真实 IME、像素/GPU、Asterinas UI、移动端或可信 ObjectiveStart/设备效果资格。G1/G2、durable K↔D、授权/撤销/退役等既有缺口没有因主机 UI 通过而关闭。具体实现顺序见 [DESKTOP_UX](DESKTOP_UX.md#6-以-hepta-为核心的-ai-原生-ui)；开发与证据入口见 [INDEX](INDEX.md)。

---

## 2026-10-17：A08 源码及主机工具整合到 main

本次 A00 集成以实际 main `18d9fca65381f0e84f130c76fa289d5186894d85` 为父提交，纳入 A08 已发布修复 `25c76c1f294a3bf0ccf541f0063b0278899bf979`。整合源码提交为 `194c41d0b2c8f1fabb7b6de4fac8967b862518a6`，与本地实际执行提交 `5a5f03390901c8393d0336f6b5e194e2dfc5eb3e` 的完整 Git tree 同为 `836d3907854eb125eba1fdb492e6baff65ad4c45`。采用独立 A00 主干集成路径，保留两边历史，未改写 A08 owner 分支。

| 本轮闭合项 | 实际结果与证据 |
| --- | --- |
| 来源审计绑定 | 指定 `--project-ref` 后从该 Git tree 读取不可变 blob，忽略工作区脏文件与后续提交；每项记录 Git blob、SHA-256、大小、mode，并给出完整 Rust 清单摘要 |
| 实际锁文件核验 | schema 3 分开记录预期 pin 与被审计提交内的真实 `support/upstream-lock.json`；缺失、损坏、tag/commit/reuse 不符均明确阻断，不能靠复述常量得到通过 |
| main 组合验收 | 完整 host 聚合 exit0 / `host_passed_only`，normal 184 项与 optimized 184 项通过；63 必需 / 71 检查文件通过；真实 OpenJDK 17 Java/JNI 编译与加载成功 |
| 固定源码检查 | main 组合的 `support/build/verify-source.py` exit0，118 项输入核验通过；root README 严格 0 字节，两个上游 pin 与内核源码均未由本集成改变 |
| 证据与开发入口 | [组合收据及原始日志](../results/integration/a08-host-main-20261017/README.md)、[A08 开发手册](../support/android/README.md)、[184 项及来源绑定负例](../tests/workloads/android/evidence/2026-10-17-commit-bound-audit/README.md) |

**资格仍为 Linux host 工具。** 实际 Binder device probe 返回 77 / BLOCKED；Asterinas 源码审计仍有 Binder、seccomp、MAC 三项阻塞。没有 AOSP 产品构建、Android guest/APK、新内核或移动端运行资格。云端排队不作为通过依据；上表来自本轮实际执行。A07/A10 的后续主机与 Weston 验证仍在独立候选中收口，原版 Agentd 运行状态须单独核对。

下面保留此前审计修复快照；其中 176 项、旧 HEAD 和“A08 未合 main”只描述当时版本。

---

## 2026-10-17：审计修复与 Hepta 只读 UI 接合

本节记录本轮实际增量。起始核对 main 为 `88f859bd2da13aa9e43a321edd172bdf0f7bfcf8`；发布前整合到 `146dedf75c5729ef1930c845eeb60e31e8111c60`，保留期间已合入的 G0 [#105](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/105)、A09 [#142](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/142) 与 A05 [#148](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/148)；A05 的新进程 / 镜像隔离实证完整保留在下段。本轮没有重新编译或启动 Asterinas，既有 kernel/QEMU 结果仍绑定其原始源码。

| 交付 | 本轮结果 | 集成状态与资格 |
| --- | --- | --- |
| A08 源码完整性 | 恢复 39 个遗漏文件、4 份变化的历史内容和 2 个执行位；从历史 Git tree 核对，没有损坏基线独有的新文件被覆盖。新增 63 项必需输入清单和 10 项回归；修复只解析第一份 Shell 文件的语法检查；A00 补上执行完整 host suite 的定向 CI | [stacked Draft #156](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/156)，基于 owner `41a8c32`，未合 main |
| A08 实际 host 验证 | 原始发现 25 项并有 3 个导入错误；历史完整恢复后 166/166 通过；新源码 normal/optimized 各 176/176、0 跳过。真实 Java/JNI 编译与加载通过，完整聚合 exit0 / `host_passed_only` | Binder device 为 BLOCKED/77；Asterinas Binder/seccomp/MAC 源码门槛仍失败；无 Android guest/APK/实机资格 |
| A07 只读 Agentd client | 固定 Hepta v2 的 Health/Capabilities/Events/RunStatus 白名单、5 秒总期限、64 KiB 帧限额、实际 SO_PEERCRED 与代际核对、受限事件投影。1 个阻塞线程取消回归与 13 个 Linux UDS 测试通过，11 个来源文件及从原源抽取的协议定义核对通过 | [stacked Draft #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157)，A07 与 A10 同一组合候选，未合 main；是 organ 外的主机 client，不是新 Agent/authority/effect owner，也未改变只读 organ 合约 |
| A10 Session / Rust Shell | Session 独立 worker 执行只读观测，Shell 接收有界 DTO；新增 Runtime 页，断连保留旧观测并标 stale；修复原 Shell inspector 的 Rust E0382 借用错误 | 66 项 UI workspace + 14 项 facade Rust 测试通过；严格 Clippy、fmt 与真实 Session IPC probe 通过，见[证据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/dfffb4a89b2094d08ea89210097fcc208e98ff68/tests/ui/evidence/2026-10-17-hepta-observer)；实际链路使用协议 fixture，未启动原版 Agentd、未提交 objective、未执行设备效果 |
| 文档交接 | 纠正架构/路线/验收/CPU 手册及初始 Agent prompts 的过期状态；[INDEX](INDEX.md) 增加逐模块开发/技术/测试映射；新增 [A05 实现与调试手册](agents/handoffs/A05_KERNEL_CONTROL.md) | 只更新文档与交接入口，不变更 HOS2 wire、上游版本或既有 gate 判据 |

A08 已发布修复 HEAD 为 `3ac85d8672e3afcfb70c0ee323108294ef883239`，tree `839a47c23cb457eed3c5a88c8c0dec160bdc87f7`。原始失败、恢复来源、逐文件 hash、normal/optimized 结果及补齐 JDK 前后的真实聚合均保存在 [证据目录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/3ac85d8672e3afcfb70c0ee323108294ef883239/tests/workloads/android/evidence/2026-10-17-source-integrity)。API 发布 commit metadata 与本地不同，PR 逐提交记录相同 Git tree 的映射，不将不同源码的结果混用。最后追加的 A00 workflow 与手册提交不改变已测 Android 执行源码；YAML 与 Shell 步骤检查通过，云端 runner 是否通过仍须读取实际结果。

**下一条工程边界：**只读观测成功不授予目标提交权限。实际 ObjectiveStart 必须由 Hepta 已有可信 ingress/issuer 和 authority/operations owner 接受原始认证封套，UI 不自签、不生成 authority epoch、不用兼容 RunStart 绕开入口。A05 已合入的只读进程 / 镜像隔离之上的可信能力授予与其余四项 HOS2 操作、A06 exit/reap 最终 CPU 计费与 SMP、A07 durable K↔D/撤销/未知历史/退役仍未闭合；G1/G2、原生设备控制和移动端资格仍未通过。

根 README 保持 0 字节；Asterinas v0.19.0 / `nightly-2026-07-21`、Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 保持不变。下面按时间保留历史执行记录，其中“当前”“尚未进入 main”等语句只适用于该段绑定的源码，不是本节的现状。

---

## 2026-10-17：A05 进程身份与 QueryAbi nonce 已合入主干

- **代码已真实合并：**[PR #148](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/148) merge `d8293465bcbbeb192bc53b252df10b9ddcce7a20`。将现有只读 `/dev/hepta-control` QueryAbi 会话绑定实际打开的 Process：fork 继承旧 fd 拒绝、exec 后旧镜像 fd ESTALE、同进程 dup 稳定；进程/镜像用启动内单调且溢出拒绝的64位 nonce 避免 PID+低32位jiffies身份复用。配套 [PR #155](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/155) 增加7项关键客体标记逐项、恰好一次核验和原始串口SHA256，已依次合入 #154/#148，**没有开启HOS2写权限**。
- **最新 main＋修复的真实编译与客体验收：**先在主干 `976c5abc19f59abeb2549c4e3e9da14ce03df8d2` 上叠加精确8个A05文件，组合Git tree `4b486eba185dad538e8578fb6c33916907a82cdf`，固定 `nightly-2026-07-21` 全内核从源码构建exit0、ELF SHA256 `96b12e32ac4db1b65ff026f4576b673643cdf0d18b0836713d67ca689a4a673c`。用原已验证的 nonce 客体 initramfs 新启动 QEMU raw33：QueryAbi、fork/exec/nonce/非root/dup等9项标记各一次，无 FAIL。相同内核的 CPU 1%×2为1.000%/1.000%；10%普通10.478%、SCHED_FIFO10.288%、父域10.043%，**5/5** 原始cpu.stat测试全部raw33；`aster-core` 真正内核QEMU ktest **153/153通过**、0软跳过、raw33。此项仅验证单vCPU N0，未承诺严格逐窗、SMP或裸机。机器收据：[a05-main-combined-acceptance-20261017.json](../results/kernel/control/a05-main-combined-acceptance-20261017.json)。合并期间另有A09工具提交，与8个A05文件没有交集。
- **仍缺的主要产品能力：**可信capabilities的启动后授权、HOS2 `ReadUsage/InstallBudget/QueryDelivery/RetireThrough` 实际效果接口、撤销与幂等/历史确认、Hepta唯一durable owner、SMP生命周期（包括 A06 [PR #138](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/138) 的退出末次CPU借记及cgroup租约）。现在仅有**只读QueryAbi身份隔离**。G1/G2、生产部署仍未完成，根README继续0字节。旧状态快照不应覆盖本段新增实证。

---

## 历史执行记录

## 2026-10-17：A03 原生锁后端已经合入主干

- **正式主干合并：**[PR #146](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/146) 提供公开 `LockBackend`/`ControlMutex` 和 `ControlCoreWith<B>` 后端，让 A05/A06 原生内核锁集成不再需要复制控制源码；已合并至 `main`，合并提交 `10e467b3775bc6f041f520bb33e0395c8b6793e1`。
- **独立 exact-head 回归：**已针对最终 PR HEAD `d3bbaf8d5baed636647e529d8475f65e7f8199a5`，在本机固定 nightly-2026-07-21 执行 `tests/control/run-validation.sh` 全量宿主矩阵，包括 std/portable-spin、严格 Clippy、fmt、x86_64-unknown-none `no_std` 构建、公共后端 API 兼容性、Loom 有界并发模型和锁内零分配，**执行结束通过**。最早的失败来自默认 Rust 1.95 未安装 `x86_64-unknown-none` 以及浅克隆缺失固定历史 Git 对象；改用已安装目标的固定 nightly、抓取必要基线提交后复跑通过。
- **不能外推的边界：**以上是 Rust 库及其宿主模型的真实回归，尚未证明 Asterinas 多核 IRQ 锁安全、A05 ioctl/exec/fork 身份隔离、A06 zombie 最终 CPU 借记、A07 Hepta durable owner 的实体效果与故障恢复。最近相关候选 PR 仍分别处于 Draft，需要真实内核与 QEMU 证据而非只靠这次 host pass。

---

## 2026-10-17：最终计费编译修复与 A09 严格测试恢复

- **A06 真实修复但尚未主干放行：**在 [Draft #132](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/132) 的实际固定 nightly 内核构建中，发现两处 `Option<ArcRef<T>>.cloned()` 编译错误 E0599；以明确的 `.map(|value| (*value).clone())` 保持真实 `Arc<T>` 引用。独立 [PR #141](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/141) 已合入 #132 开发分支，合并提交 `ee6c278f9468c4633bed94d0bc3563b9601df0a4`，**不是合并 main**。原源码编译失败；修复后完整 Asterinas 编译 exit0，ELF SHA256 `48bea33a39614004a17aeae9159f0ea57a73a6fd4db64c3c3b2fd43c6dee934f`。固定 QEMU 1-vCPU 原始 `cpu.stat` 客体验证 **4/4 raw33**：leaf1%＝1.0%、1.1%；RT10%＝9.965%；parent10%＝10.096%；同源码 **aster-core 153/153 真实内核测试通过**、0失败/过滤/软跳过。机器证据见 [A06 验收收据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/e0060a06ac11a30ad7472c65e0d9da852cc03d50/results/organ-backend/2026-10-17/a06-final-debit-arc-ref-compile-and-guest.json)。尚未专门证明 zombie exit/reap 最后一段 CPU debit，不能据此宣告 G1 或 SMP 合格。
- **A05 防复用候选独立验收边界：**精确候选 `7a9b4919402fe43b88866da2c2aab2aa5b589e28` 的宿主 nonce 契约 **4/4 通过**，原 QueryAbi host smoke 通过；固定 nightly 全内核编译 exit0，ELF SHA256 `dfac10ce6909ac99321e4768e41f8ff5c70edd7e496d51d735ffd6e3577213ee`，普通隔离 QEMU initramfs 启动 raw33/boot marker 成立。**本轮未执行该候选的实际 fork/exec/QueryAbi identity 客体探针**，原同进程身份曾有失败；继续保持其 Draft，不得因编译和普通启动成功就签发真实效果权限。
- **本轮已合并主干的代码与实测流程：**[A03 PR #134](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/134) 将实际成功的 exact-source Loom／锁分配模型加入 CI，merge `c0ffb9e736869da577fed12d9fa46df086bcd858`；[A09 PR #143](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/143) 修复已合并 DMA 元数据模型的两处严格 Clippy 问题和 Rust 格式，merge `7d6c9d426e7920fc17bb723de9e2a671fcc91b5e`，本地真实 **55 单元＋4 compile-fail doctest＋7 Linux ECHILD/worker 负例**均通过、Clippy `-D warnings` 与 fmt 均通过。**A09 仍只是 no_std/host 元数据模型**，未进行真实 GPU DMA、IOMMU 或物理硬件测试。
- **下一条实质阻塞：**A06 从主干当前版本对齐完整最后计费生命周期 QEMU 场景（真实 fork/exit/reap、cgroup lease/rmdir、SMP 迁移/锁序）；A05 通过精确进程 nonce/exec/fork 客体权限验收后才可接 HOS2 ReadUsage/InstallBudget；A07 只沿既有 Hepta owner 实现持久 K↔D 结果确认和退役，不把只读 organ host 变为效果执行器。**G1/G2、真实硬件和生产资格仍未闭合。**

---

## 2026-10-17：A03/A02 已独立验证并合并，A05 进程会话完成真实客体验证

- **合并到 main 的真实源码：**[A03 PR #123](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/123) merge `df8e2decbb1f4efb501d03f6141f81c7a128ac1a`，减少 native delivery 预约／退役／历史丢失时的内部锁下分配；[A02 PR #119](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/119) merge `eabf5fb169a1d477ff3b3059a7a2aaa89746cdc8`，为 N0 `ReadUsage` 编码和解码补上 `cumulative_cpu_ns <= sample_boottime_ns` 的不变量。均是精确预期 HEAD 的普通合并，未改其他 Agent 分支。
- **A03 独立实测：**精确 `25f809623f22b205189a1ad3fa995667189a45b6` 的 std 与 portable-spin Rust 测试、双方严格 Clippy、fmt、`x86_64-unknown-none` 编译均通过；12 项 Loom 模型通过、18 个锁分配检测场景在已测同步模型中无锁内分配。合并后在精确 main `df8e2dec...` 重新运行两套 Rust 测试、两套 Clippy 和格式检查全部通过。**只证明宿主与有界模型行为，不是内核 IRQ/SMP 终验。**
- **A02 独立实测：**在固定 `nightly-2026-07-21` 上完整执行未修改的 `tests/abi/run_acceptance.py`，**13/13 验收检查全部通过，20/20 编译型错误变异被抓到**；原样输入与 0 字节 README 校验通过。合并后精确 `eabf5fb...` 的 Rust ABI 测试、严格 Clippy 和 Python 57 项测试亦通过。GitHub 云端排队的任务不能冒称绿灯；这些是授权本机独立执行证据。
- **A05 原生只读 QueryAbi 真实 QEMU：**[Draft PR #125](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/125) 精确源码 `48303eb68582f32639f555f54ccab1d5355753d2` 从源码固定 nightly 编译成功，ELF SHA256 `8198458eb4039717465595952213dbb2a981f77c38f25acc4e171b2caf6c2581`；同一独立 1-vCPU 客体中 pre-exec QueryAbi、post-exec `ESTALE`、fork 继承 fd 拒绝和启动完成标志均成立、QEMU raw33。Host C/Werror 与六项回放负面测试也通过。
- **未合并的 A05 对抗实验：**为了避免 PID+截断32位启动 jiffies 重用公开 CapSpace wire ID，独立本地候选 `2e87e8fe7a42032e97edb440b170206c53c28069` 尝试单调进程 serial。该候选虽然编译，但真实客体报 `HEPTA_QUERYABI_FAIL at=same_process_session`、QEMU raw65，**明确失败，未推送或合并**；原 A05 owner 分支保持不变，失败已报告 PR #125。
- **当前剩余主门槛：**A06 zombie/exit 最终 CPU debit [PR #129](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/129)、A05 真正不重用且稳定的 CapSpace ID 和 exec/fork 授权、HOS2 其余四项效果接口、Hepta 原有 durable K→D/历史/退役均未完成端到端资格。A06/N0、A05/QueryAbi 已有实证，但 **G1/G2 和 SMP/硬件生产放行仍然不成立**。

---

## 2026-10-17：A05 QueryAbi＋A06 CPU 带宽已合并 N0 实验内核

**真实主干合并：**[PR #121](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/121) merge `3538ec23570733a8b48678f9f24fcd0949dabd84`；主干包含此前 A05 的只读 /dev/hepta-control QueryAbi 与 A06 的实际 cgroup CPU 限额／调度器。测试源码本地合并提交 `b913202b2e487126319e60813a54163666b9a2ad` 与远端集成提交 `eaf5242233b799356b7daa73898a14d240832abb` **Git tree 相同**（`b852e0037af8f84c22a8fc7347fa55d8183e07e6`）；后续 PR 仅添加结果 JSON，三条核心内核文件 Git blob 已在合并后再核对一致。唯一文件冲突 `support/build/kernel.sh` 采用已验证的 main A01 新版（保留 manifest 身份及 --live-artifacts），没有回滚 A01 修复。

**实际执行证据（非报告拼接）：**固定 Asterinas v0.19.0 / nightly-2026-07-21 从同一源码树完整构建、在 q35/TCG／1 vCPU／512 MiB 运行 initramfs，raw QEMU=33、构建／启动脚本 exit=0。候选完整 ELF SHA256 `06cf42337d266a486d3ac98caa3f9b0021f0f7679c7130e48224cb35fedb90ab`。在这个内核上，**10/10** 原始 `cpu.stat` 探针客体成功（单 CPU 1% x3＝1.100%、1.000%、0.999%；单 CPU 10%=10.352%、RT10%=9.824%、parent10%=10.226%；双 CPU／双工作线程 1%=0.957%、10%=10.112%、parent10%=10.396%、RT10%=10.187%，全 raw33／无panic）。**3/3** 真实 A05 QueryAbi ioctl 客体通过，包含权限拒绝与格式拒绝测试，raw33。**真实 QEMU 内核回归：**OSTD 报告 221 passed/0 failed，其中3个VMX/EPT软跳过；aster-core 153 passed/0 failed/0软跳过；实际执行通过下界**371**，两套raw33。A05 host smoke、archive负测与bash语法亦通过。机器证据见 [a05-a06-integrated-acceptance.json](../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json)。

**严格边界：**这只是 **N0 实验性开发主干**，不能称为已生产可用OS。QEMU双核／双线程有限样本不是 SMP、CPU热插拔、迁移/IRQ锁序或逐100ms硬上限的充分证明；QueryAbi只读，per-open observation space ID不是可信CapSpace。**HOS2 InstallBudget/ReadUsage/QueryDelivery/RetireThrough、exec_epoch与启动能力授权、A07现有Hepta owner的持久K↔D、撤销／历史确认退役尚未集成**；G1/G2仍不合格。root README严格0字节，无现役机器内核部署与生产服务修改。A06原 owner Draft #18 保留独立开发记录；新后续补丁须从当前 main 对齐、避免重复集成或覆盖。

**下一条产品实现：**优先将 A03 `ManagementGrantState`／ResourceDomain 与 A05 Asterinas 的真实进程/CapSpace 身份接合，把 `ReadUsage` 与 `InstallBudget` 接到已合入的**唯一 cgroup/调度资源事实**；完成普通进程无权、exec/fork泄权防护、cap=0独立恢复、同K/D效果幂等，再由 A07通过现有durable authority/operations owner完成效果对账和退役。策略继续在Hepta用户态，IRQ/调度快路径不调用模型。

---


## 2026-10-17：原生 QueryAbi 进入主干，G0 验证收敛

本段为已执行事实的最新摘要；历史条目中“ A05 尚未进入 main ”的表述只适用于其旧版本快照。状态文档更新前的主干 HEAD 为 162707a0e6ccccc768c0f1abd3263f3ff4c647a1。

- A05 原生实验设备：PR [#87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87) 已合并，merge 2e1d592c25335f3cd97f312e4f73545f305d6e61。Asterinas 主干新增 /dev/hepta-control，只允许 root 打开、只读、且仅支持实验 QueryAbi ioctl；用户态复用项目唯一 HOS2 Rust codec。精确 owner 源码 224fcdde44b9c68163298623fd908e3009b1b2a6 从固定 nightly-2026-07-21 编译成功，ELF SHA256 f667b468940af56070d8a7a1909fe68e863d6a0d095fca8de894e71ff9acd077。独立QEMU单vCPU 3/3 次 raw33，QueryAbi OK、非 root 打开拒绝、dup-fd会话一致、无panic；本源码 aster-core 真正 QEMU ktest 141/141通过，0失败/过滤/软跳过。代码 blob 与main一致。
- A05 host负测：同 exact owner SHA 下 run-host-smoke.sh exit0，16个请求结构负例、21个异常HOSR响应、ENOTTY/EFAULT及6 normal/6 optimized 归档用例成功。客体的3次通过与host结果分别统计，不能互相替代。
- A03 G0 portable target：PR [#103](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/103) 合并为 751d5448b6e92e8902b89bcd1d337c5d61872393。独立运行实际Rust标准/portable-spin宿主测试、严格Clippy和x86_64-unknown-none rlib全部通过。这不代表该 crate 已接入新内核或验证 IRQ 锁序；GitHub Actions exact-head此前仍 queued。
- A02 编译型反例：PR [#101](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/101) 合并为 d2173e21ca902fa304d5d6edacbc329c9484a570。对其精确 SHA c6139994f4cc97b8cdc804e906d532ca04167ad2 运行正式 pinned acceptance，13/13 组检查通过，16/16 编译变异被测试抓住；输入文件哈希保持不变。合入 A05 后在main重新执行 A02 Cargo测试亦成功（首次临时手工加 --locked 但新 checkout 未生成 Cargo.lock 导致的失败不属于代码失败，正式 acceptance 以隔离快照生成锁）。
- A01 构建命令修复：PR [#110](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/110) 合并为 162707a0e6ccccc768c0f1abd3263f3ff4c647a1；support/build/kernel.sh 去掉 make/gcc --version 的早关闭 head 管道，避免 set -o pipefail 因 SIGPIPE返回141。此缺陷在本轮 A05首次源码构建中真实出现；隔离环境仅临时采用不提前关闭消费者后完整构建成功，工具脚本已恢复，再将两行永久修复合入主干。不声称 PR #110 已完成独立 GitHub runner验收。
- 明确不能外推：QueryAbi 的 per-open session ID 不是可信 CapSpace；正式 ioctl号、exec_epoch、ReadUsage、InstallBudget、QueryDelivery、RetireThrough、A06 SMP/严格CPU cap、A07 Hepta 唯一 owner K↔D 效果/持久确认及退役仍未闭合。G1/G2 未通过，A06 [Draft #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 还不是 main。根 README.md 保持严格0字节，未操作任何现役业务设备。

---
## 2026-10-17 UTC：A05 原生 QueryAbi 已在真实 Asterinas 客体执行（仍为 Draft）

- **真实内核 HOS2 ioctl 首次执行成功，纠正下方历史记录的“尚未在 guest 运行”描述**：[A05 Draft #87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87) 原源码提交 `5fc3887dfc5833b61d11280eb1421bb7fd78648f`，经过实际 `make kernel` 编译的候选完整 Asterinas ELF SHA256 `54c8a7a798cbbd80f1a8ce5f0144328815e63b413e79b0133206bcaaba607e4a`。四份 A05 实际修改文件的 Git blob 与远端 PR 精确吻合。独立调用固定原始 C probe，在 QEMU q35/TCG x86_64 **1 vCPU/512MiB、无网卡数据盘** 中真正打开 `/dev/hepta-control` 执行 QueryAbi ioctl，校验 HOSR/版本/唯一开放会话 ID/QueryAbi-only 位图、非法 magic EINVAL、NULL transport EFAULT、未知 ioctl ENOTTY。首次 QEMU raw33、`HEPTA_QUERYABI_OK` 与 A01 boot marker，无 panic；同一预校验内核 ELF/一次性 initramfs 又复跑 **3/3 次 raw33**，合计 **4/4** 成功。该轮复用了源构建内核 ELF，没有把这4次 guest replay 说成4次内核重编译。
- **真实内核回归：**从与 A05 四份改动路径逐字节一致的隔离源码工作树，运行固定 `nightly-2026-07-21` / `support/build/ktest/run.py --crate aster-core --skip-osdk-install`，实际 QEMU 内核测试 **141/141 passed、0 failed、0 filtered、0 soft skipped、raw33**。该轮重新构建内核测试 ELF，SHA256 `5e1d40b86b4717a645f3cc089f746b7fa0c90e84bf0bdb72615e25d47b402746`，不等同完整 Asterinas/OSTD/SMP 矩阵。
- **客体回复校验反例同步通过：**独立对 [已并入 A05 分支的 PR #90](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/90)（merge `db0a77263218b7d4cd4d3994a93edcf4d7da9590`）精确源提交 `e925bdfcc59b2f7f7d606eb964447ffd8b741283` 执行 `sh tests/kernel/control/run-host-smoke.sh` exit0，真正编译原 C guest 校验器并验证 **1合法＋21非法 HOSR 响应**、另16帧结构负测及 ENOTTY/EFAULT 拒绝。其加固后 guest C blob `58cc000c81501185aa0d328bc8701cec92a2dea0` 在同一 A05 内核 ELF 的 QEMU 中也返回 raw33/QueryAbi OK、无 panic。**这是 host 负例与 guest 正例的分别验证**，并非全部恶意 transport 都已在 guest 测试；#90 远端 CI `host-contracts` 仍 queued，不能报绿。
- **证据已进入 A05 owner 分支：**[PR #91](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/91) 已合至 `agents/A05-native-queryabi-bootstrap`，后续验证以 A05 分支下 [a05-queryabi-real-guest-20261017.json](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/agents/A05-native-queryabi-bootstrap/results/kernel/control/a05-queryabi-real-guest-20261017.json) 追加完整 QEMU/重复测试和141项内核验收机器结果。原始串口、具体QEMU命令和编译日志保存在授权隔离实验区，公共仓库仅保留脱敏的哈希与结果。
- **尚未放行：**A05 主 PR 仍为 Draft，**只实现只读 QueryAbi**；查询中的 per-open observation space ID **不是真实可信 CapSpace**，未完成 exec_epoch/启动授权/InstallBudget/ReadUsage/QueryDelivery/RetireThrough 与 Hepta 持久 owner K↔D。HOS2 G1/G2、SMP、裸机、持久副作用均不合格。禁止把 `TrustedReadOnlyOrganV1` 当作硬件效果执行器；保持原 authority/operations 真正执行 owner。

---

## 2026-10-16：A00 A03 生命周期主干合并、HOS2 语义边界和 A05 客体验收防假阳性

- **A03 真正源码已合 main**：[PR #86](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/86) merge `9113b3cfc2822d86f32e3dcfc78c6e2b8c123ecd`，仅改 A03 自有 `libs/os-control/**` / `tests/control/**`。修复末次 `Arc` 释放后父资源域不应保留已销毁子域 cap、外部 execute 回调期间不能卡死 QueryDelivery/retire/history audit、资源域过深递归释放风险，增加层级最大64约束。精确 HEAD [G0 run 38986007642](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38986007642) **success**：真实 A02/A03 Cargo、fmt、strict Clippy 均通过，A03 129/129 宿主 Rust 用例通过。原 owner 另外记录 portable-spin/no_std build 与第二后端 129/129。**仍是 Linux host model，不是 A05 内核设备/持久 Hepta 效果**。
- **HOS2 独立语义黄金边界已并主干**：[PR #77](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/77) merge `82ef86a9d48851c17de2df0699b16f032be7dd3e`，现有 G0 增加独立24帧 HOS2 semantic edge oracle 必需源/非软链接检查与 Python `--check`，修正“源/测试同时删除仍绿色”假阳性。精确 HEAD [G0 run 38986254820](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38986254820) **success**，不含 QEMU 或内核效果运行。
- **A09 安全代码已经进入堆叠开发分支**：[PR #75](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/75) merge `e9f61ca4f0ceca82fc4cd20e4c5ec3a856ee7827`，目标 `agents/A00-a09-native-worker-supervisor`，**非 main**。对其精确 HEAD 的 [host-device-model run 38985469497](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38985469497) 为 success；保留 WNOWAIT/未回收 leader 身份锚，避免复用 PGID 后误杀他组，异常 worker/group 拒绝伪造成功。A09 owner 已分别吸收并继续强化 worker 报告；GPU/IOMMU/复位/物理 passthrough 没有完成。
- **A05 真实 QueryAbi 尚未执行，但验收假阳性已修源码**：[Draft #90](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/90) head `ff8162a06f755c206c79b9d0b7d053c60f40c1c0` 堆叠在 A05 原生设备 [Draft #87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87) 上，仅改 A05 `tests/kernel/control/**`：HOSR minor/header-reserved/payload-reserved 必须逐字节验证，新增1有效+21个失效 HOSR 帧对抗，并接入现有 C11 宿主 smoke（文件缺失/符号链接时硬失败）。源代码已推送，**本 A00 环境未实际执行新 C 负测**；[PR #90 G0 run 38988044867](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38988044867) 当时仍 queued。现有 A05 内核 QueryAbi ELF 虽已从源码构建，但真实 QEMU ioctl 尚未运行，不能因 C 负测宣称 G1。
- **固定边界与剩余阻塞**：G0 先前 #69 merge 的严格 Clippy 红灯由 A02 owner [#76](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/76) 中 `as_chunks::<2>()` 修复；A00 独立重复 #84 已关闭未合，避免覆盖 owner 后续测试。A05 真正 CapSpace/process-start/exec-epoch/QueryAbi QEMU、A06 [#63](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/63) 退出 Task 最终 CPU 借记、A07 唯一 Hepta durable K↔D/效果确认/退役均未闭合，G1/G2 未通过。根 README 0 字节、Asterinas v0.19.0/`nightly-2026-07-21` 与 Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 不变。

---


## 2026-10-16：A02 全量实测合主干；A05 QueryAbi 内核候选（未验收）

- **A02 已真实合入 `main`**：[PR #76](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/76)，merge `8f3bb49ab161104063a6ebea25428c40aa884ac0`。在授权执行宿主固定 `nightly-2026-07-21`（Rust 1.99.0-nightly）对精确 owner 代码源和与 main 同步的提交 `338bd37b471cb0c94f2dbd251d4c98fd6180342c` 运行 `tests/abi/run_acceptance.py`，**13/13 必需检查通过**，无失败和遗漏，含 no_std 编解码、12基本 + 24语义黄金字节、32B transport、负面案例、独立 Rust/Python 编译变异测试、fmt、严格Clippy、no_std target。合并后 `libs/os-abi/src/lib.rs` Git blob `dc32e002cfbfc63c456e071958b167ad24f50cf5` 与被测代码逐字节一致。最初执行宿主未安装固定 Clippy，验收按规则拒绝；仅安装固定工具链 Clippy 后重跑通过。实际 Github Actions 另看其独立结论，不能把 queued 状态报为通过。
- **A03 同一源码进一步复核**：使用 `RUSTUP_TOOLCHAIN=nightly-2026-07-21` 对 `tests/control/run-validation.sh` 运行真正 Rust host / portable-spin / no_std 编译、测试与严格 lint，最终 exit0。首次错误使用默认 Rust 1.95 导致 `x86_64-unknown-none` 目标缺失，保留为执行环境问题，不能算产品测试失败或掩盖后续修复。
- **首次 A05 真实内核源码候选（仍为 Draft）**：[PR #87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87)，commit `5fc3887dfc5833b61d11280eb1421bb7fd78648f`。沿 Asterinas 既有 char registry/devtmpfs/PerOpenFileOps，新增仅只读 `/dev/hepta-control` 的实验 HOS2 QueryAbi；输入/输出调用**同一份** `libs/os-abi/src/lib.rs`，boot/临时会话 ID 独立标识，**不授予** CPU、设备、管理/历史退役效果权。内核在独立工作树从固定 Asterinas 源码成功 `make kernel` 构建，ELF SHA256 `54c8a7a798cbbd80f1a8ce5f0144328815e63b413e79b0133206bcaaba607e4a`；静态 Linux ELF QueryAbi 对抗探针用 `cc -Wall -Wextra -Werror -static` 编译通过，但**尚未在 guest 真正运行 ioctl**。
- **明确剩余阻塞：**尝试创建 QueryAbi 客体 runner 及独立运行 QEMU 被授权执行工具拒绝；没有声称新内核的 QueryAbi 设备已运行/boot 通过。原 main 的 A01 构建脚本有 `set -o pipefail` 与 `head -1` 偶发 exit141，候选编译中仅在隔离工作树暂时把 `head` 换成 `sed -n '1p'`，在提交 A05 前完全恢复；PR #87 不改 A01 所有文件。正式 ioctl 编号、可信 CapSpace/process-start/exec_epoch、A06 真正的 ResourceDomain/G1、A07 Hepta 唯一持久 owner 效果/撤销/历史查询和退役/G2 均未放行。根 README 保留严格0字节，未修改生产机器。

---

## 2026-10-16：A00 持久 K 主键纠偏与 G0 严格 CI 交付

- **已合并真正 CI 源码**：[PR #69](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/69)，merge `5aeff7b60e8c96aa14676e1642efddc6ad63a607`，现有 `.github/workflows/g0-contracts.yml` 对 A02/A03 Cargo+fmt+strict Clippy、A05 QueryAbi/ENOTTY 改为必需检查，`tests/control/**` 纳入 PR/push 触发。A00 在独立 Bash fixture 实际测 **9/9** 文件缺失保护场景通过；**当前新主干 GitHub Actions 仍需自身真实完成，不能报通过**。
- **重要 Hepta 事实校正（取代下方 A00 历史错误 K 描述）：** 固定 `hepta-private-ci@f8c9419d...` 的 `kernel.operations` 持久 `OperationIntentV1` 含独立的 `scope_id: StableId`、`operation_id: StableId`、`payload_digest: Digest32`，其固定 SQL 主键是 `PRIMARY KEY(scope_id, operation_id)`；摘要不是主键，参与 `semantic_digest` 和权限/最终效果的独立校验。此前 A00 草稿 #35/#48 曾把 `model.rs::OperationKey {id,payload_digest}` **参考模型**误当该持久账本的 K，两个草稿均未合主干；这一定义现明确撤回。A03 owner 的两个无损 StableId 字段方向正确，不能被旧草稿覆盖。A07 仍要在原唯一 Hepta owner 里分别验证摘要、授权、代际和 K→D 绑定。
- **当前真实限制：** A03 仍为 Rust **host model**、A05 五操作真实 CapSpace/ioctl 与 A07 持久执行/恢复仍未闭环，G1/G2 不合格；A06 CPU 配额实测不能替代生命周期/权限/严格窗口验收，A09 GPU/VMM 仍需隔离执行及物理硬件验证。固定 Asterinas/Hepta/toolchain 未升级，根 README 0 字节。

---


## 2026-10-16：HOS2 ABI 独立复核与主干合并

- **已完成：**[PR #72](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/72) 的 `no_std` HOS2 transport snapshot/preflight/typed codec 修复已独立测试并合入 `main`，merge `02a0e4f6e11ed04039179165726ae43a0caab78a`。独立对精确 PR HEAD `eef96afd4c3fcdc5bcdc2b8ba00260e1fb116b91` 在 Linux host 执行 `cargo test --offline`、`cargo clippy --offline --all-targets -- -D warnings`、`cargo fmt -- --check`、`cargo check --offline --no-default-features` 和 `python3 -m unittest discover -s tests/abi -p test_*.py -v`，全部返回 0；Python ABI 30/30 通过。这是**真实源码宿主测试**，不是内核 HOS2 功能验收。
- **A06 最新开发：**A06 Draft [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 已有多轮真实 QEMU 1vCPU/2vCPU 探针和修复进展，当前仍为 Draft、未进主干。其精确提交对应的 SMP 证据包括已修复的已退出 Process 生命周期问题，但不能从两线程、2vCPU 样本推广到完整 SMP、CPU 热插拔或所有内核锁序。未验证严格逐窗 CPU 上限。
- **真实下一步：**A05 必须将已合入的 ABI/控制核心接进内核设备/进程授权与 `QueryAbi`，随后最小 `InstallBudget/ReadUsage` 调用进入唯一实际调度/配额状态；A07 沿现有 Hepta owner 完成真实效果确认、历史查询与有界退役。A06 先独立整树回归和 owner 审核，再申请合并；不能因 host ABI 测试绿灯自动放行 G1/G2。

---

## 2026-10-16：A00 Hepta K/HOS2 严格合并与 CUDA 原生超时真实反例

- **A03 真实 Rust 源码交接（尚未合 main）：**[Draft #48](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/48) 最新 A00 head `040eb1b352308debc763c7c9cb86106ffb1e11dc`：在 A03 owner 的 ResourceDomain/投递/原 owner 权限模型上，统一固定 Hepta 真正的 K=`StableId+Digest32` 和 `DeliveryObservation::hos2_saved_status_code()->Result<u16,DeliveryError>`。拒绝终局结果缺失、伪造元数据、`previous_revision=0`、以及 `consumed > effective % 100ms`，对齐主干 A02 Rust decoder。**44项 Rust 集成测试已编写但本环境没有 cargo/rustc，不能宣称 44/44 通过**；独立 Python 时间/修订数学 oracle 5/5 通过，仅属算术模型。A03 owner 正持续更新，禁止强推或覆盖 owner，合入前需精确头部 Cargo/Clippy/fmt 与现有 Hepta 持久 owner 接合。
- **A09 精确原生超时负例：**[Draft #62](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/62) commit `4d0f19f62e349a78c7126bcb838ec732a9407646` 新增可执行 `test_cuda_native_timeout.py`，经本地 Git blob `2e7060ba59bca45af20ec90fffb04cdcc104b587` 与远端逐字节匹配。独立 Linux Python3.13/GCC14.2 实测：当前 `SIGALRM` Python handler 所谓30ms硬截止，在0.8秒不返回的 C FFI 上约 **800ms 后**才触发，相关测试预期失败；OS `subprocess.run(timeout=0.03)` 子进程回收对照通过。因此 A09 [#57](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/57) 的 `timeout_enforced=true` 不可作为可靠 CUDA/NVRTC 硬限期证据，必须改为独立子进程强制 kill/reap/未知效果后复跑，不涉及真实 GPU 或生产硬件。
- **A02 实际主干增量：**[PR #53](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/53) 经其他 Agent 合并，新增 no_std transport 地址算术溢出拒绝、InstallBudget 顺序 ID/前驱 revision 校验及密集 golden 截断负测。本轮 A00 对最新 `main` 仓库真实 12 份 golden 执行独立 JS 字节 oracle **1,232/1,232**（12正例、1,160前缀、12尾字节、48头变异），不是 Rust codec 执行；另外已有独立真实 Cargo/Clippy/fmt 测试结果记录在本页此前主干状态中。相关最新 GitHub Actions 仍为 queued，不能当作绿灯。
- **A06 新 G1 生命周期风险：**[issue #63](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/63) 来自实际源码：`charge_task_cpu` 在 `Weak<Process>` 无法升级时直接返回，可能遗失最后未结算的 `[from,until)` CPU 时间，尽管已修复 SMP panic。此项是**源码层面潜在欠账，尚无 QEMU exploit 证明**；要求 owner 绑定原始资源域至最后一次扣账，执行短生命周期线程/退出与配额对照，不引入第二套 ResourceDomain。A06 已有153/153 kernel 与2vCPU QEMU历史验收仍有效，但不证明每个 task 的最终借记或严格100ms硬配额。
- **范围与安全边界：**本轮新 G1/G2 内核 CapSpace/ioctl/原 Hepta 持久实际效果仍未验收；主干 README 0字节，Asterinas `c4b7ed575b7b32773475b194d2ad41fb6d03765b`、`nightly-2026-07-21`、Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 固定不变，不接触现役服务、系统盘或 GPU。

---


## 2026-10-16：A06 当前整树编译故障修复与双CPU独立回归

- **最新实际阻塞及代码修复：**A06 owner 提交 `31e49a3c29d5e19d30976cdfb55accba1d786aea` 的独立完整内核构建在 `cpu.rs:700` 因 `quota_debt_regressions` 结尾被截断而失败，报 `unclosed delimiter`。使用先前经过真实QEMU验证的准确测试尾部，只追加缺失代码，不修改运行时路径。修复 [PR #61](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/61) 已合并到 A06 owner，merge `becd1fe3a106afd02d755cefebb4dc139704e390`，**尚未进入 main**。
- **重新从源码构建及 SMP 回归：**修复后精确提交 `db3a8a36951041f6016a7d7ed870d1d9d014fdc5` 以固定 `nightly-2026-07-21` 完整编译成功，内核 ELF SHA256 `1bc49d2bd5995ad9d73457b310be1f0a9dcad8e3c36589b5f2741088db071572`。相同新内核运行 q35/TCG、2vCPU/双pthread共享cgroup **6/6 QEMU客体完成、无panic**：1% x2 =0.871/0.879%；10% x2=10.573/10.413%；SCHED_FIFO10%=10.104%；父域10%=10.221%。另外真实 `aster-core` 内核测试 **153/153通过**、无失败/软跳过、rawQEMU33。验收数据已提交到 A06 的 [机器结果](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/bbb5b87b81ef1a310b098c6b66aa4058018f678b/results/organ-backend/2026-10-16/a06-repaired-head-acceptance.json)，原始日志保留于隔离执行主机 `/home/qian-qi/.local/state/trillionnium-os-organ-next-20261016/evidence/a06-repaired-*`。
- **范围边界：**已验证的是指定 x86_64 双vCPU/双线程、父域及RT测试，**不是**SMP普遍正确性、任意多核热插拔/迁移、逐100ms硬限额、长周期回归或 HOS2/Hepta原生执行。A06 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 仍应保持Draft直到多机、权限和端到端门槛达到，不应仅因153内核测试通过就批准生产系统切换。

---

## 2026-10-16：SMP 双线程配额、退出进程防 panic、ABI 主干加固

- **A06 双CPU实际新故障与修复**：[PR #59](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/59) 已合入 A06 owner 开发分支，merge `31e49a3c29d5e19d30976cdfb55accba1d786aea`；**未合入 main**，其主PR #18 仍为 Draft。修改后 Asterinas ELF SHA256 `5c73b7fb84b6d8f160b5b037be8b5bca7d8e5507a2cf7b779405d054918819bf`。原修改后内核在 2vCPU/双 pthread/共享1%配额下发生 `PosixThread::process().unwrap(None)` panic（已退出的 Task 暂时仍在调度器中，原Process的 Weak 不再能升级）；未修改 Asterinas 对照同负载未panic，但 `cpu.max` 不执行，实际约100%。
- **真实QEMU修复验收**：对已销毁进程进行有界的 Weak upgrade 检查，仅允许已退出线程继续清理；原始读数和运行路径在有进程owner时不变。真实双vCPU双线程同cgroup **7/7** 次 guest raw33、无panic：1% x3 `0.792/0.896/0.950%`；10% x2 `10.392/9.914%`；FIFO 10% `10.279%`；父域10%/子域不限额 `10.262%`。每次配额前不限额总CPU约197–200%，因此确有两CPU同时运行，而不是单CPU假SMP。单vCPU原1%探针 **2/2** `0.999/1.000%`；固定 `nightly-2026-07-21` 编译及实际 `aster-core` QEMU **153/153通过、0失败/过滤/软跳过**。可复跑 [SMP测试源](../tests/organ_backend/smp2/run_parallel_candidate.py) 和[机器结果](../results/organ-backend/2026-10-16/a06-smp-posix-exit-guard.json)均位于 A06 PR #59/owner 分支，**不是 main**。
- **ABI主干实际交付**：[PR #53](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/53) 已合并，merge `a1c61d50fe281361ca04ad4bc3c6b3aba2c2260f`，强化 HOS2 `no_std` transport 越界、错误响应的有序 request_id 与 InstallBudget 版本校验。本轮修复测试源码的三处Rustfmt末尾换行后形成 `ee13b2d05f18c17b01ff10c1e487b9c3cba54290`；从该合并后的精确主干源独立执行 Cargo test、严格Clippy、fmt、12/12 golden及19项Python ABI测试全部通过。**这仍不是已实现的 HOS2 内核 ioctl、权限和真实效果。**
- **仍需攻克**：退出后最后一段CPU运行时间若失去持久所属资源，仍需正确结算；未测CPU热插拔/跨CPU迁移/长期并发锁序、严格每100ms窗口上限。A05真实 HOS2 CapSpace/ioctl、A07沿既有Hepta owner完成可信K↔D持久确认/退役均未闭环；不因双CPU测试就升格 G1/G2 或production。

---

## 2026-10-16：A00 归档 CI 防假阳性、A06 实际内核修复及 A03 接口收敛

- **main 已合并实际 CI 代码**：[PR #49](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/49) merge `7b1e183951121c5e16618ef046612053b146e6bc`，仅修改已有 `.github/workflows/a01-boot-evidence.yml`，用 PR base/push before 的实际 Git commit 检查归档源码与回归测试是否被同时删除。A00 独立 Linux Bash/Git fixture **9/9 通过**，包括 source+test 同删、符号链接、非法 base SHA、缺项和真正失败测试。合法首次 bootstrap 只说 source 缺失，**不**计归档测试 pass；GitHub Actions 队列未当作成功。
- **A06 owner 开发分支代码已实际集成**：[PR #44](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/44) 合并进 `agents/A06-cpu-bandwidth-n0`，merge `94b48dd38098475f92c3849b974c9170e0b57307`（**不是 main**）。`cpu.stat` read-only period 观察改动 Git blob `dd1a8cfe65c60028500b88bf897e1ae7e47c8afb` 与独立固定 nightly 的被测内核源码相同；证据保留 [ktest](../results/organ-backend/2026-10-16/a06-cpustat-readonly-independent-ktest.json) **153/153 QEMU 内核测试**和 [guest](../results/organ-backend/2026-10-16/a06-cpustat-readonly-independent-qemu.json) **7/7**（1%/10%/FIFO/parent，raw guest exit33）。这是被测修复源码证据，A06 合并后整树未在本轮重跑，严格每窗上限、SMP、真实 HOS2/ioctl 仍未通过；A06 #18 保持 Draft。
- **A03 owner 目标整合，仍未合 main**：[Draft #48](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/48) 已经安全双父非强制合并至 `2262e85b98463c93e9de9b2c8bb314bf1852aed3`，以 A03 当时最新 owner `9e5d8007be915c981e665bae3ed0397b0564b94a` 为整合基础，保留原 original-owner authority、ResourceDomain 层级与 clock regression，加入固定 Hepta 完整 `StableId + Digest32` K 和 fail-closed `Option<u16>` status 变换。仅 3 个 A03 所有权文件，编写的集成测试合计 36 项，但 **本轮 Rust Cargo/fmt/Clippy/QEMU 均未运行**，不可代替 owner 持久 ACK 或内核 G1/G2。旧不同分支不得互相覆盖。
- **真实未解问题：**A05 仍只有 Linux 宿主 QueryAbi/ENOTTY 和 QEMU 拒绝证据，无五个原生内核控制操作；A07 仍须沿现有 Hepta durable operation owner 完成授权/撤销/unknown/reboot/retirement；裸机 CPU/GPU/Android/UI 也没有本轮验收。固定 Asterinas v0.19.0/`nightly-2026-07-21` 与 Hepta `f8c9419d` 未修改，根 README 始终严格0字节。

---


## 2026-10-16：A06 只读 cpu.stat 内核实测

- **跨周期超额结转已存在真实源码与测试记录：**A06 1kHz Draft [#18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 已包含 positive-overshoot debt 的 N0 实验；其此前独立证据显示原始完整 cpu.stat probe 在10秒1%场景约1.01–1.1%，较不结转时约2%更精确。该能力仍为单vCPU实验，非严格窗口上限或生产资格。
- **此次新增真实验收：**针对 [#44](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/44) 提出的 `CpuMax::observed_nr_periods(&self)`，将 `cpu.stat` 从会提前推进quota周期的 mutating `advance` 改成只读投影。使用精确源码 `ad55fecd95857f3e3c7cb5997118f7a44e5f5555`，固定 Rust nightly-2026-07-21 从源构建成功；完整内核ELF SHA256 `41cd6283facb4bf4ce1c7f60284c4433ba6d2777e73e54a58eaf5e1a4169fe43`。
- **独立客体结果：**保留原完整 `cpu.stat` 探针，QEMU q35/TCG x86_64 1vCPU 512MiB，无宿主网络/数据盘，**7/7** QEMU返回raw33：1%普通任务三次1.1%、1.1%、1.0%；10%普通任务两次10.392%、9.902%；SCHED_FIFO 10%=10.379%；父域10%/子域不限额=10.141%。此外 **aster-core实际内核测试153/153 pass**、0失败/过滤/软跳过、raw33。[证据与精确SHA](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/52) 已通过 [#52](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/52) 合并至 #44 的开发分支，**不是合入main**。
- **尚未闭合：**#44仍为Draft，需要A06把只读投影整合到自己的最新内核来源，处理cpu.max同时写入、周期迁移与锁序；SMP、多CPU复现、物理机及Hepta OS原生HOS2 ioctl、授权/持久K↔D/效果退役均未实测。不要把这里的N0 guest结果记为G1/G2放行。

---

## 2026-10-16：A00 本轮源码安全修复与真实验证增量

- **已合并测试源码（实际 main）**：[A05 PR #45](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/45) 合并 commit `54d5197bf66be23ea8b1f3ff5a3d2c40a82694b7`，修复 `tests/kernel/control/hos2_queryabi_probe.c` 将 EFAULT 等非 ENOTTY 错误误判为真实 `/dev/null` 拒绝的假阳性。A00 在独立 Linux x86_64 / GCC 14.2.0 宿主重建三份源码并逐文件比对精确 Git blob：`ae59693d54c375812dd522a1568c520a41c87e70`、`862a50fb8d9affd361510a2a2d9b29b6307f66ea`、`53aba3d3433b92a2d10b74136231db61f892ebb4`。`sh -n`、严格 C11 GCC、原生 `sh run-host-smoke.sh`、UBSan 和静态链接 selftest 均通过；旧处理在新负测下退出1，修复版通过。这仅是 **Linux 宿主** HOS2 负面探针，不是新内核 QueryAbi 实现。
- **A03 安全源码已推送、未合主干**：[Draft #48](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/48) commit `a10f0b8ddea9c1627469ab79b2f2e1ed551f3e79`，把 #35 真正 Hepta K（StableId+Digest32）和 #30 的 `OriginalOwnerAuthority`/伪造 ACK 回归整合为**两文件、19个无冲突精确补丁块**。源码/对象静态检查通过，但 Cargo、fmt、Clippy 和 QEMU 在本轮未运行，原 Hepta owner 的持久核验仍缺失；不得合入或宣称 G2。后续 #36/#37/#39 必须串行审查；#37 当前 stale `ReadUsage` 返回 `sample < window_start` 与 ABI 所要求的 `window_start=floor(sample/100ms)*100ms` 冲突，已向 owner 反馈，暂不捆绑。
- **A06 真实测试证据关联**：[Draft #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 当前 cgroup CPU blob `bce4cabfcc933af4107f7d892e735027b4acbd1e` 与 scheduler blob `a9767b2d037ba2e85243b5b498de814353f95178` 精确匹配此前独立构建的 #41 修复源码；其历史产物有 151 个实际 aster-core QEMU ktest、12 次正式 guest quota 检查及2次唤醒测试。**本轮未重新编译内核/QEMU**；cpu.stat 读可提前滚动未结算窗口的缺陷待 [Draft #44](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/44) 修复后实际内核复测。尚无真实 HOS2 CapSpace/ioctl、Hepta 持久退役、SMP/物理硬件验收。
- **CI 的真实状态：**G0 host-contracts 和 A01 host-evidence 的最新相关 GitHub job 持续 `queued`（issue [#33](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/33)）；不能当作通过。本轮 A05 小范围宿主修复以精确 Git blob 的独立实际执行作为合并依据，没有修改仓库保护规则、固定 Asterinas/Hepta 版本、根空 README 或生产服务。

---


## 2026-10-16：A00 合并定向 A01 回归、清理过时 ABI Draft，并核对真实 G1/G2 阻塞

- **本轮新增主干代码：**[PR #23](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/23) 已合并，merge `7d5121a41090dc74521de8a6a14d923d9dfc34db`，只新增 `.github/workflows/a01-boot-evidence.yml`，在相关路径变化时执行现有 A01 启动证据与 runner 的 Python 宿主对抗用例、空根 README 和上游锁校验；**不**把宿主 fixture 冒充内核构建或 QEMU。该提交的 [Actions run 38904246724](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38904246724) 最近一次读取为 **queued / conclusion=null**，未记录为通过。
- **A02 现有事实：**完整 no_std Wire codec 已经由 [#13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13) 合入；旧初始 Draft #4 与之冲突，已保留历史并关闭（未合并）。主干 12 个黄金样本中读用量 sample=150ms/window_start=100ms/consumed=35ms，InstallBudget 和 terminal history 共用 effective=140ms/consumed=33ms；`tests/abi/test_mutations.py` 已包含针对 cap/expected_revision 的六项对抗测试。A00 对这些仓库字节执行 17 项独立 JS 结构/时间/漂移断言均通过，但**未在本轮执行 Rust Cargo、CI 或 QEMU**。
- **A03 单一资源域与安全边界：**主干源码检索只存在 `libs/os-control/src/lib.rs::ResourceDomain` 这一宿主模型定义；A05/A06 真实内核共享资源域未实现，不能声称已验收。主干已有悬挂前缀、错误 publisher 和连续退役负测；然而 `retire_through` 仍允许没有可信 original-owner 能力的 syntactically valid receipt，详见 [issue #28](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/28)。修复在未通过 exact-head Cargo 的 Draft [#30](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/30)，真实 Hepta StableId+Digest32 K 的主干类型纠正在 Draft [#35](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/35)；与 #36/#37/#39 的 A03 所有权补丁须串行整合。
- **G1/G2 保持未完成：**A06 真正的单 vCPU 1kHz 配额旧版曾有 QEMU 客体证据，跨100ms边界漏记/抢占计费的新修复 #41 仍需固定 nightly 的内核 ktest 和原始负载 QEMU；不得将 Draft #40 的不同欠账算法直接叠加。A05 仅有已合并 QueryAbi **Linux 宿主 ELF/ENOTTY** 探针，尚无 CapSpace/ioctl kernel；A07 尚未把 `kernel.authority` 的原 Hepta 持久 owner 与 D/撤销/重启验收接合。无本轮实机或新内核端到端验收。当前定向 CI 排队问题跟踪 [#33](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/33)。

---


## 2026-10-16：跨周期 CPU charge 漏记修复待内核验收

- **可复现的源码问题：**当前 A06 1kHz 超额结转代码先执行 `CpuMax::advance(until)`，再按照已经更新的窗口起点记账，可能丢失线程跨越一个或多个100ms周期时旧窗口尚未记入的 CPU 时间。原有平滑负载 QEMU 结果不证明此极端时间交错正确。
- **回归代码：**[Draft PR #40](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/40)，分支 `agents/A06-cross-period-charge`，基于 A06 `4e23125a006dca5ce90d32cbab41c079b8da9a1d`，新增两项内核 `#[ktest]` 对抗案例，并在推进窗口前补记 `[from,until)` 中已完成周期的运行时间；修复提交 `03f1caed0f35aaed98d20cb12bce758e22a51124`。不变更 1kHz 全局定时器、HOS2 wire、Hepta owner 或 cgroup 资源结构。
- **实际验证分层：**从相应真实内核 `CpuMax` 实现提取纯状态机、以固定 1MHz TSC 仿真进行独立 `rustc --test`：**修复前 4通过、2新增测试失败（exit101），修复后 6/6通过（exit0）**；这是宿主数学/源码测试，尚非改后 Asterinas 的内核编译或 QEMU 通过。
- **实机验收阻塞：**尝试执行固定内核源码构建时，与另一个 A06 并发工作树的 OSDK/Cargo 生成锁出现 package collision；后续恢复验证时，执行机远程 tunnel 暂不可用，无法权威读取后续构建结果。**PR #40 保持 Draft，不会仅凭宿主测试合并或宣布配额精度已合格。** 同类实际 QEMU/ktest 验收应由 A06 owner 在受控环境复跑；原 A06 已验收的 9/9 QEMU 和145/145内核测试仍仅证明此前版本自身。
- **后续唯一修复路径：**同一个源码快照应完成 Asterinas nightly-2026-07-21 `make kernel`、`aster-core` 的新增 ktest 以及原始完整 `cpu.stat` 的 1%/10%/SCHED_FIFO/父域 QEMU；保留源/产物SHA与失败证据，审查当前预算窗口已被其他入口提前滚动时的延迟计费条件。完成前不合入 A06 或 main。

---

## 2026-10-16：1000Hz CPU 超额结转已通过客体验证并进入 A06

- **源代码与合并：**[PR #38](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/38) 已合并进 A06 **开发分支**，merge `d5741c7b7e2e17bb733d2d810408433da721b5a5`；原 `CpuControl.max` 的本地 IRQ 安全锁保留，OSTD 全局 `TIMER_FREQ=1000` 未改。对上一周期实际超额 CPU 消耗只结转正向欠额，并在后续周期抵扣，不储存未用额度；内核真实 `used_clocks` 与结转欠额独立。A06 主 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) **仍是 Draft，未合并 main**。
- **正式源码与客体：**最终代码已重新编译，release ELF SHA256 `9e3c106b88198a5dc1aef81c25392ab89aa3777831d17a852f869ab9747a0b59`；使用原始完整 `cpu.stat` 探针、q35/TCG、1 vCPU、512MiB。**9/9 QEMU 客体测试正常完成**：1% CPU 配额三次1.100/1.200/1.200%，10% 三次9.995/10.204/10.502%，SCHED_FIFO 10%=9.645%，父域10%=10.749%，50% 单次53.477%（不掩盖固定周期边界突发）。
- **长窗口对照与可复跑入口：**10秒实际QEMU对照中，原1%配额为2.000%，新方案为1.109%；原50%为51.146%，新方案为50.238%。新增 `tests/organ_backend/run_candidate_matrix.py --duration-seconds 10 --max-cpu-percent 1.5`，正式 ELF再次跑通1%场景，观测 **1.100%**。**Asterinas真实 `aster-core` 内核测试145/145通过**，含4项新增的超额结转/不存信用/不充值回归。原始数据见 [机器结果](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/agents/A06-cpu-bandwidth-n0/results/organ-backend/2026-10-16/a06-quota-debt-n0.json)。
- **去除并行路线：**5kHz全局升频实验 [PR #34](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/34) 已保留结果并关闭，不作为默认优化；无需提高所有工作负载的定时器频率。
- **仍未放行：**上述结果只支持单vCPU N0在观察窗口内的平均限制与无死锁；**不保证每个100ms周期的严格上限**。多CPU聚合与迁移、跨周期运行时间切分、资源控制器生命周期、硬件/能耗/尾延迟、HOS2 CapSpace ioctl、Hepta真实持久效果与Android/GPU仍待实际验证。不要将这次A06开发分支成果计作新内核已在main生产放行。

---

## 2026-10-16：N0 精度实验和 K↔D 主干接合

- **A03 本轮真实合并：**[PR #25](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/25)，merge `62d63809ee683402a90e7d15031e6d51a6eac133`。将 value-only 的 Hepta K↔D 绑定类型加入 Rust 宿主控制库；独立对 HEAD `755bbbe7eb6b492d21f69da80f41d93af97fba06` 完成 **21/21 Cargo 测试（1单元+20集成）、严格Clippy和fmt**，均通过。它不是 HOS2 真实内核持久操作，也不能凭 value-only identity 宣告已完成不可变摘要或 owner 认证；对应后续 PR 仍有单独验证。
- **A06 1kHz精度现状：**已经确认 IRQ-safe 锁合入 A06 自己的分支，修改后 q35/TCG、1 vCPU 原始 `cpu.stat` 探针不再死锁，但 1% 配置实测约1.9–2.0%，尚非严格1%保证；A06主 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 仍处 Draft，**未合并 main**。
- **5kHz 并行实验：**[PR #34](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/34) 在同类真实QEMU客体测试中，1%配置观测约1.100%、1.217%、1.163%；10%配置约10.152–10.355%。其对照中无限额1s循环迭代次数较1kHz约降低15.8%（非随机化TCG样本，不能推出真实硬件因果性能/能耗）。**不将全局tick直接从1kHz提高到5kHz作为生产默认。** 已向 PR 反馈更窄的跨周期超额欠账（overshoot debt）方案和原始探针的验收要求；这项方案**尚未写入内核源码**，曾遇到执行通道源码写入拒绝，不计已实现。
- **后续实际门槛：**A06 需保留1kHz基线，验证周期边界费用结算、降额不充值、低配额精度、静态/实时/父级预算及恢复；之后 A05 接权限与 HOS2 内核控制，A07 才能完成真实 Hepta K↔D 原有 owner 的持久确认/退役。不要把宿主状态模型或5kHz实验结果冒充生产OS能力。

---

## 2026-10-16：IRQ 重入修复已进入 A06（未合并主干）

- **修复位置和版本：**[PR #29](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/29) 已合入 A06 开发分支，实际合并提交 `6b7a4580f74add2b640b6ea948797bd87733faac`。原 `CpuControl.max: SpinLock<CpuMax>` 默认只禁止抢占；同一把锁会被定时器 IRQ 的 CPU 计费/资格检查路径获取。改为 `SpinLock<CpuMax, LocalIrqDisabled>`，保证持锁期间本地 IRQ 不重入。**A06 主 PR #18 仍是 Draft，未合入 main。**
- **真实 QEMU 证据：**在 A06 最新合并源码的相同 Git tree 上从源码构建 Asterinas 内核 ELF，SHA256 `8ff3629163438f86abe755aa5a61f3e8d53d2ab44994f41d006d04e3415d80a5`。使用固定 A01 initramfs、原始完整 `cpu.stat` 探针，q35/TCG、1 vCPU、512 MiB、无宿主网络/数据盘。**6/6 客体运行成功（raw33、无 panic）**：普通任务1%重复3次分别2.001%、2.000%、1.911%；普通任务10%=11.100%；SCHED_FIFO 10%=10.989%；父域10%/子域不限额=10.296%。[机器结果](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/f3bf18cfce246e48b985235bf7af1a45df987bcf/results/organ-backend/2026-10-16/a06-irq-safe-merged-matrix.json)。
- **受控对照：**原 WIP ELF 在1%下含 `cpu.stat` 读会超时；相同 ELF 的一次性探针仅跳过 `cpu.stat` 则 QEMU 正常退出、约2.1%。加上 IRQ 安全锁后，完整探针正常通过；N0 同时复跑了此前 8 次客体测试。历史失败记录保留下方，不再代表最新 A06 分支仍必然卡死。
- **尚未完成：**1% 实测仍约1.9–2.0%，不可宣称精确配额；SMP、cgroup迁移/生命周期、严格 lock order、HOS2 CapSpace/ioctl、Hepta 持久效果和物理硬件均未验收。main 尚无实际新内核 CPU 限额放行资格。只有继续修正 tick 超额和其他实机回归后才考虑合入 A06 主 PR。

---

## 2026-10-16 A06 实机配额阻塞与 A03 集成更新

- **新近主干改动：**A03 跨周期 `ResourceDomain::usage` 修复 [PR #16](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/16) 已合并，commit `04aacbefe037618229d4f2f0b1d4c92979abcf21`。在独立 Linux Rust 1.95.0 环境对该精确 PR HEAD `44b0cbd4ad2b88fa9dfe47aeb4f2c71803f641fd` 测得 **19/19 Cargo 测试通过**、Clippy `-D warnings` 通过、fmt 检查通过。属于宿主控制模型测试，不是内核节流实现。
- **A06 真实客体失败：**当前 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 为 Draft，HEAD `512e45d02b4ff544189b104cb36994f2edc588f4`。在它已编译的**修改后内核** `a2f72e2bc75d0490b658898697ced0532fe36395067939e3959f88dab051676e` 上，QEMU q35/TCG/1CPU/512MiB，运行一次性 guest cgroup 探针。基线 CPU `977ms / 1000.58ms`；`cpu.max=1000 100000` 写读成功、`/proc/self/cgroup` 归属正确，但客体在后续 `SYS_OPENAT/SYS_READ` 后停止前进；独立的 **45秒** 与 **15秒** 两次运行均超时。没有受限负载样本、没有 `ORGAN_PROBE_COMPLETE`、没有关机标记，故明确为 **failed_timeout**，不能计算配额符合率或认定 CPU cap 生效。
- **实测证据与沟通：**两个完整原始串口、精确 kernel SHA/guest argv、结果在授权执行宿主 `/home/qian-qi/.local/state/trillionnium-os-organ-next-20261016/a06-independent-probe/run/`，已在 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 留下失败细节与复现路径。源码定位首先检查节流队列何时在 tick 重新准入、idle 与被限线程的唤醒路径、锁顺序及未来周期唤醒；这只是待证实的故障归因，不宣称已经找到唯一根因。内核源码没有在本轮成功修改，PR #18 未合并。
- **下一真实闭环：**A06 在自己的分支修复任务长期不恢复的问题，先用同一 QEMU 探针取得受限 CPU 样本与正常关机，再测父子层级、CPU 调额不充值、非 fair 调度类、能力撤销与恢复；之后接 HOS2 ioctl 与真实 Hepta owner。独立应用和恢复服务不应受 Hepta 故障影响。

- **A06 官方 runner 的交叉复核**：独立拉取最新官方测试器 commit `7f5a3962c24d10deb8514b217a84e7c608185d45`，对同一修改后内核 ELF `a2f72e2bc75d0490b658898697ced0532fe36395067939e3959f88dab051676e` 执行 `run_candidate_matrix.py --mode leaf --quota-us 1000 --repeat 1`，得到 `qemu_exit=124`、`guest_complete=false`、`cpu_percent=null`；这是第三项独立超时。A06 的 10% 普通/FIFO/父域成功样本不能覆盖 1% 失效；该 PR 仍应保持 Draft。完整证据位于独立实验目录 `a06-official-1pct-independent/{result.json,serial-1.log}`，详细复现在 PR #18 评论。

---


## A01/A02/A03 已集成 — 2026-10-16

**主干代码基线（本段提交前）：** `c757c709652f9a9701765ff8a9e7c3026fc1019e`。这是源码与可复现验收的状态快照；不要把模块源码合入等同于 Hepta 原生 OS 可用。

| 范围 | 实际状态 |
| --- | --- |
| Asterinas 完整内核源码 | **已合入 main**：[A01 PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)，固定 v0.19.0、OSTD 和上游许可文件。 |
| QEMU 客体启动 | **已验证**：单 vCPU、q35/TCG、512 MiB、原始内核 ELF SHA256 `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63`，原产物独立重放 raw exit=33，BOOT_OK 和 CPU=1 标记成立；本次独立重放**没有**重新从源码构建。 |
| A01 OSDK 宿主回归 | **已合入 main**：[PR #15](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/15)，隔离 OSDK daemon 生命周期修复，按保留日志所列宿主单测 23/23、选定集成 13/13 通过；内核客体 362 reported、3 VMX/EPT soft skips，不代表 SMP/裸机/HOS2 验收。 |
| A03 Rust 控制模型 | **已合入 main**：[PR #12](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/12)。在合入前及合入后实际运行：1 单元测试 + 17 集成测试全部通过，严格 Clippy 通过。这是 `std` 宿主模型，**不是**内核 CapSpace/ioctl。 |
| Python HOS2 规格 | **14/14 通过**，是顺序模型，不是内核并发证明。 |
| A02 Rust no_std Wire ABI | **已合入 main**：[PR #13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13)，HOS2 2.0 no_std 字节编解码与固定 golden/negative 测试；对应 HEAD `5e3d56e0d15662b9d31f99ddf5e346796a5f6f82` 的 G0 scoped host CI 已成功，不代表内核 ioctl、CapSpace 或调度通过。 |
| 实际 CPU quota | **未执行**：一次性 Asterinas 客体内 `cpu.max=1000 100000` 写入/读回后，约 1s 墙钟仍消耗 998ms CPU。失败复现、日志和测试源码在 [PR #11](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/11) 与 [结果](../results/organ-backend/2026-10-16/)。 |
| HOS2 内核驱动/CapSpace/真实 ResourceDomain | **未实现**。A05/A06 应共用实际内核对象与调度限制，不能包装未执行的 `cpu.max`。 |
| A06/A09 实现与验收 | [A06 #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 为 Draft、尚无新内核真实 CPU 1% 配额验收；[A09 #9](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/9) 为独立 GPU/VMM 模型 PR，真实 Rust 单测仍待 GH Actions 完成。[A00 #17](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/17) 已合入硬件范围的 Rust/CPU fixture CI。 |
| Hepta 的 OS 效果 organ | **未实现**。现有 `TrustedReadOnlyOrganV1` 禁止持有控制能力或执行 I/O；观测采集和效果执行需保持在既有 owner 接合。 |
| Linux / Android / GPU / UI | 各 Agent 继续维护独立 PR；宿主测试、硬件调查、用户态原型均不计新内核端到端通过。 |

**下一条真实工作：**以主干已合入的 A02 no_std Wire ABI 与 A03 控制模型为唯一参考实现；A05 接 CapSpace/ioctl、A06 在 ClassScheduler 公共计费/资格/节流/timer 层实现真正的 CPU cap（含非 fair 类与恢复），用完全相同的已提交客体探针证伪或验证；随后 A07 沿原 Hepta authority/operations/持久 owner 完成 K↔D、历史查询/退役及故障恢复。A01 的少量测试环境问题（OSDK daemon descendant、`/proc/self/exe`）与 CPU 机制缺失分别跟踪，不以形式化总关卡阻断无关开发。

---

## 历史状态快照（保留原有记录）

## A00 实际集成快照（2026-10-16，main = c1a22de12f3d95fd49227787601169b9f42fdf12）

- **已合并源码/回归**：[PR #11](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/11)，merge c1a22de12f3d95fd49227787601169b9f42fdf12：固定 A01 内核产物的 QEMU 客体运行了真实 CPU cgroup 反例（`cpu.max=1000 100000` 写/读成功；配置后 1.000 秒使用 998ms CPU），结论 **NOT_ENFORCED**，不是成功的 CPU quota。探针只改一次性 initramfs，不修改宿主 cgroup；原始客体串口与结果在 [results/organ-backend](../results/organ-backend/2026-10-16/)。对应 Python newc/archive 测试普通和 -O 各 5/5 通过。该 PR 不实现内核节流。
- **主干真实边界**：当前 main 尚未导入 `kernel/asterinas`，也无 `libs/os-abi` 或 `libs/os-control`（A01 [PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)、A02 [PR #13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13)、A03 [PR #12](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/12) 仍未合并）。A01 分支拥有 Rust 源码构建、QEMU boot 和 OSTD/aster-core 客体测试证据，但主干不继承分支验收。A02/A03 的 host Rust 测试不得记作内核 ioctl、权限或调度验证。
- **未解决**：A01 lock/source 验证与 OSDK 主机测试失败；A02 capability bit 依赖；A03 owner-ack 与跨周期核算；真实 A05/A06 CPU 限额执行及 A07 Hepta owner 到内核效果闭环。原 Hepta 操作 owner 仍是唯一持久事实来源；不得建立第二份 K 账本。
- **CI**：原定向 G0 工作流 GitHub Actions 仍处于排队状态，不能标记 pass。本轮仅在同一工作流中增加已合并的 `tests/organ_backend` 宿主安全回归，绝不将其视作 QEMU 验收。根 `README.md` 保持严格 0 字节，Asterinas/Hepta pin 未改。

---


> **A00 集成增量（2026-10-16，原文历史记录保留）**：从实际 main 3cc2f810eda93dab7411b62ef2f8f3830fbb1500 验证并合并 [A02 PR #1](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/1)，合并提交 3cc2f810eda93dab7411b62ef2f8f3830fbb1500；三份 N0 单 CPU 黄金样本时间修正：ReadUsage 125ms 时 consumed=25ms（降低后的 cap=20ms），InstallBudget 与 QueryDelivery 在 123ms 生效点 consumed=23ms。独立 Python struct 生成器 --check 检验 12 份样本，宿主 Python 格式/变异测试 6/6 通过；此前 14 场景顺序模型仍是模型，不是内核。A00 增加单条按路径触发的宿主契约 CI，Rust 项仅在对应 crate 存在时执行；记录的执行结果以真实 GitHub Actions 为准。尚无 Rust ABI / ResourceDomain 内核实现、项目 QEMU 新内核启动或 Hepta 端到端结果。原 Hepta 持久 operation owner 不变。根 README 0 字节。

2026-10-16；修订基线 `46a0e9f9ffa0e8289d0a1324d5dd8c9e6d6b7544`。本轮交付为 **recovery_contracts_and_spec_tests**，不是Rust内核实现。

## 已实际完成

围绕V201–V217修订关键文档，HOS2明确启动授权交接、CapSpace全局投递预约、独立DeliveryView、只读历史查询、有序写序列与连续结果退役。预算目标收敛不伪造旧操作终态；恢复责任不依赖Hepta自身健康；真实调度类、计时和计费点列为下一实现接合。

新增Python顺序规格场景，工作容器与执行主机分别运行同一源码SHA256 `8162883270a153ebf81f2cd4e0e05392c957fb439cfbb481239b35d75cab68de`，均为14测试、0失败、0错误、0跳过。10,000写/退役发生在模型内，不是内核benchmark；模型不提供并发或实际权限证明。[结果](../results/spec-recovery-v03.json)

新增12份独立Python struct生成的HOS2十六进制黄金样本，覆盖五操作请求/响应、历史退役和CAS拒绝；只核算布局，没有Rust codec消费这些样本。[样本](../tests/golden/hos2.json)

## 未完成与本轮实际阻塞

Rust库源码写入再次被执行通道安全检查拦截，工具仅报告无法确定请求安全状态。没有重放同一源码写入，也没有改权限或绕过检查。已确认无`.rs`文件；此前成功创建但没有实现对应的临时Cargo.toml已移除，不把空工程算交付。规格测试是独立的文档模型，不是被拒Rust编解码库的替代实现。

官方v0.19.0安装ISO下载在180秒上限内只获得74,026,432/1,442,840,576字节，curl退出28。完整文件未校验，未启动QEMU；部分文件的大小/摘要已记录后清理。执行主机检测到QEMU 8.2.2及可访问KVM，但这些不构成客体启动。[失败记录](../results/reference-iso-probe.json)

## 能力状态

| 范围 | 实际状态 |
| --- | --- |
| 文档恢复契约 | revised，待代码实现 |
| 顺序规格模型 | 14 passed；非内核/非并发 |
| 固定字节样本 | 12份；codec未测试 |
| Rust ABI库/普通客户端 | not_implemented；source_write_blocked |
| Asterinas源码导入/源码构建 | not_executed |
| 官方ISO完整下载/校验 | failed_timeout/not_verified |
| QEMU/裸机内核启动 | not_executed |
| Hepta端到端/Linux/Android/GPU/UI | not_tested |
| CI与生产资格 | not_claimed |

根README保持0字节；不再次删除仓库，不改hepta-private-ci、现役服务或硬件。source pin仍不等于完整build lock；upstream-lock中缺项和false保留。

## 下一项真实交付

优先完成获得执行允许的Rust源码写入及黄金向量测试，或补齐固定上游源码构建与真实串口启动结果；不能因这些规格场景通过就推进M1a/M1b实现状态。并行/设备/前驱恢复仍需对应真实环境，未决项不标为关闭。
