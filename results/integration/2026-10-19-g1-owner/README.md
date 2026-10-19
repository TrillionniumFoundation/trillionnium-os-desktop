# R10：真实 CPU owner 接合、内核运行与 Hepta 安全债务

**交付范围固定到 main `7e859b98c58053b88ea2baabc3e5f645fd38dca5` / tree `354adb549b064c78477932ca943309694eb54356`，以及 Hepta 的 04:44:15–04:45:54 UTC 状态快照。**发布前主干另合入了 [PR #198](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/198) 的 SCM_RIGHTS/CLOEXEC 增量；本报告保留它的全部源码、工作流、文档与既有证据。G1-a 的完整运行资格继续绑定下述 1c054 / tree2b873，#198 的新 Linux/客体对照独立列明，不把旧运行授予当前354树。见[主干交付整合说明](source-publication/report-main-sync/README.md)及[Hepta 最后有界快照](hepta-final-status/README.md)。

本轮已经把 Asterinas G1-a 从固定源码审计推进到真实内核测试：原 `cpu.max` owner 具有一次 metadata 绑定、同一预算锁内的共享 revision，以及替换和删除后的不可逆实例关闭。固定 `12e0547d2e6394548b15764b06346422c4fff31e` 上，完整 aster-core 目标实际 **179 passed / 0 failed / 0 filtered**；OSTD 目标报告 **221 passed**，其中三项因 VMX/EPT 不可用而提前 soft skip，实际执行下界为 **218**。十项新 G1-a owner 回归均在真实客体中各执行一次并成功。 本地 ordinary 产品候选 `4e077aef4913179a68aa0d814018ce1a9d87cafc` 的第三次封闭执行也已接受：普通非 ktest boot 成功，同一 ELF 的 QueryAbi 客体取得 14 个精确 marker 各一次，包括四个合法形状但仍禁用的操作均返回 `EOPNOTSUPP`。

这组结果支持继续在受控 Asterinas 派生上接合真实资源 owner。生产启动尚未调用绑定入口，HOS2 仍只提供 QueryAbi，另外四个操作保持不可用。当前没有完成全 G1、Hepta K↔D、完整 Linux ELF 或桌面/移动设备控制资格。Hepta 普通 CI 仍有依赖安全和 Windows 边界失败；独立 Fleet 修复又遇到真实 ENOSPC，针对构建存储的五行 workflow 修复已单独发布但尚未获得原 134 包远端完成收据。已有隔离历史查询通过，不代表它已成为可生产部署的控制桌面。

**代码已经合入主干。**[PR #197](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/197)的最终 e15+G1 组合 `1c05412e2b340bbc8cd2b8a3389ae0ecce538991` / tree `2b873aa43445c8a02351f5900074a38c6fa4820d` 已完成六个普通 CI checks，G0/A03/A06 的原日志和实际 artifact 均已独立接受；[这一固定 G1 组合的完整证据](g1-remote-ci-1c054/README.md)保留其运行入口。**03:59:41 UTC**，另一位维护者将它合入 main `71ce079c3218a8692476e4113b60c9d2c0d2a172`，parents 为 e15/1c，tree 与本地 1ca 和已验收 1c 精确相同，[原 API 与独立 merge 复核](source-publication/main-sync/independent-merge-tree-review.json)单独保存。这里核对了已经发生的合并，没有再次请求 merge，也不声称新 post-merge workflow 已运行。

初始 0c 基线上的 f744/463f 失败与 107 成功各保持原始包。期间主干通过 #196 前移 e15，加入 Runtime/进程边界修复和具体 A04 handoff；本轮完整保留并三方协调文档，再用 **6,397 文件**的新组合独立运行和审查，没有将旧 5,851 文件的证据冒充新来源。

本地 03 当次结束为 clean、三个 source snapshot 相同；恢复其他工具后又观察到 canonical OSDK.toml 残留，写入来源仍 unknown。正常远端 A06 的普通 boot/QueryAbi 区间严格 source gate 已独立通过，未重现该本地残留，但没有查明原写者，也没有把旧失败改成成功。

## 1. 阅读入口与来源身份

| 内容 | 入口及范围 |
| --- | --- |
| G1-a 开发与技术手册 | [ASTERINAS_CPU_OWNER_G1A](../../../docs/ASTERINAS_CPU_OWNER_G1A.md)：源码、依赖、输入/返回、锁序、错误和十项测试。该手册随 G1 源码切片集成，本证据分支不复制一份同名影子手册。 |
| A01 构建与测试 | [构建手册](../../../support/build/README.md)、[客体测试手册](../../../support/build/ktest/README.md)：固定 Git seed、明确工作锁、完整 metadata、环境和客体判定器。 |
| G1 环境来源 | [原始环境报告](g1-evidence/g1-env/REPORT.md) 和 [就绪收据](g1-evidence/g1-env/ready.json)。原报告中的六个补充链接仅在 G1 raw archive 的 `g1-env/` 内，解压位置见第 8 节；paused QMP 不计为 guest 执行。 |
| G1 独立源码检查 | [最终 source review](g1-evidence/g1-review/source-review-final-12e0547d.json)、[47 项静态门禁](g1-evidence/g1-review/static-gates.json)。这些是源码和字节检查，未重复执行 Cargo 或 QEMU。 |
| 已实际执行的内核 | [core 收据](g1-evidence/g1-a-ktest-02/receipt.json)、[OSTD 收据](g1-evidence/g1-a-ostd-01/receipt.json)、[独立运行/ELF/输入复核](g1-evidence/g1-review/runtime-review-12e0547d.json)。 |
| 普通产品与用户态 QueryAbi | [03 实际通过收据](g1-evidence/g1-queryabi-candidate-03/receipt.json)；[01 原始失败](g1-evidence/g1-queryabi-candidate-01/receipt.json)、[02 原始失败](g1-evidence/g1-queryabi-candidate-02/receipt.json)、[三次运行独立复核](g1-evidence/g1-queryabi-review/queryabi-candidate-runtime-review.json) 保留。最终候选 [Git 对象来源包](source/ordinary-candidates.bundle) / [收据](source/receipt.json) 与原 be6/12e source bundle 分开。 |
| G1 的已验收组合及实际合并 | [1c054 完整普通 CI](g1-remote-ci-1c054/README.md)、[精确头接受](g1-remote-ci-1c054/exact-head-ci-review.json)、[已观察 merge 原收据](source-publication/main-sync/observed-merge-receipt.json)。六检查通过，该次 6,397 输入/8 guest 与同树主干 71ce 分别绑定。 |
| 本次交付的当前主干 | [#198 增量与交付整合](source-publication/report-main-sync/README.md)、[完整源码范围证明](source-publication/report-main-sync/source-integration-review.json)、[原始 API 观察](source-publication/report-main-sync/api-observation.json)。main7e/tree354 的 37 个变化路径全部保留；原 G1 runtime 仍固定 1c/tree2b。 |
| 原 0c 基线的逐头 CI | [f744 首次失败与完整 A06](g1-remote-ci-f744/README.md)、[463f 中间失败与有界复核](g1-remote-ci-463f/README.md)、[107afb 精确头接受](g1-remote-ci-107afb/README.md)。每组原 ZIP/日志、原 manifest 和 source 身份各自冻结。 |
| 四处 host 契约修正 | [独立 host 执行](g1-ci-host-correction/README.md)、[完整最终验证](g1-ci-host-correction/final-validation.json)、[两提交源 bundle](source/ci-host-contract-candidates/receipt.json)。实际测试/模型与内核 guest 分开计数。 |
| 并发主干及最终源码集成 | [main 全部 Git 输入复核](source-publication/main-sync/main-integration-source-review.json)、[真实发布收据](source-publication/main-sync/publication.json)、[单一 merge 的源 bundle](source/main-sync-candidate/receipt.json)。保留 e15 新工作，INDEX/STATUS 三方协调。 |
| 首次真实失败与因果复现 | [首次失败收据](g1-evidence/g1-a-ktest-01/receipt.json)、[完整 metadata 写锁复现](g1-evidence/g1-metadata-repro/component-writer-reproduction.json)、[独立因果复核](g1-evidence/g1-review/component-metadata-reproduction-review.json)。 |
| Hepta 依赖安全 | [完整中文诊断](hepta-security/deny-repro-01/SECURITY_DEBT_DIAGNOSIS.md)、[执行收据](hepta-security/deny-repro-01/execution.json)、[13 条拒绝](hepta-security/deny-repro-01/error-summary.json)、[原始包索引](hepta-security/README.md)。 |
| Hepta Bazel 原始失败日志 | [独立追加中文诊断](hepta-bazel-followup/BAZEL_FAILURE_DIAGNOSIS.md)、[30 个固定源码比较](hepta-bazel-followup/source-comparison.json)、[02:24 CI 快照](hepta-bazel-followup/final-status.json)。三份原 job 日志取得成功，与未恢复远端 deny 日志的情况分开。 |
| Fleet helper 后续最小修复 | [独立修复说明](hepta-fleet-fixture-fix/README.md)、[单提交 patch](hepta-fleet-fixture-fix/fixture-admission-assert.patch)、[41 tests 与严格 Clippy 收据](hepta-fleet-fixture-fix/final-validation.json)。这是实际 Linux x86_64 窄域验证，未改写原远端失败日志。 |
| Fleet 在实际 main 上的独立修复 | [main 候选手册](hepta-fleet-fixture-main-fix/README.md)、[新基线上重跑的 41 tests / Clippy](hepta-fleet-fixture-main-fix/final-validation.json)、[Ready PR #2882 发布收据](source-publication/final-source-and-fleet-publication.json)。旧 parent-1b 的 20 文件包不改。 |
| Fleet 远端 ENOSPC 与独立环境修复 | [原失败完整证据](hepta-fleet-main-remote-ci/README.md)、[CI 存储配置修复与实际窄域验证](hepta-scoped-ci-storage-fix/README.md)、[Ready PR #2883 发布收据](source-publication/hepta-scoped-disk/publication.json)。原 134 包尚未在该配置下完成远端重跑。 |
| A04 主干交接与独立实现手册 | [164 行 A04 handoff](../../../docs/agents/handoffs/A04_LINUX_HEPTA_ELF.md)保留源码/命令/错误/整合说明，7e 更新其中两行并加入 [59 行 SCM_RIGHTS/CLOEXEC 手册](../../../tests/workloads/linux/SCM_RIGHTS_CLOEXEC.md)及具体实现。原三份完整候选手册与完整四 ELF/rootfs 仍属 25c，旧 PR 状态按[03:39 原 API](source-publication/upstream-and-a04-current-api.json)解释。 |
| 文档覆盖基线 | [R9 固定 207ff9da 的文档审查](../2026-10-18-objective-history/module-documentation-review.json)保留历史 53/225 范围；[本轮 delta](module-documentation-delta.json)另保留 e15 的 13 份 Markdown 变化审查，追加 7e 的 A04/SCM 手册 delta，并核对当前目标，不将历史审查称为新执行。 |
| Hepta 最新有界状态 | [04:44–04:45 UTC 原状态](hepta-final-status/summary.json)、[18 文件冻结清单](hepta-final-status/files-manifest.json)。三个 PR 仍 Ready/open/unmerged/blocked，#2883 的 scoped 为 skipped，未取得原 134 包重跑完成。 |
| 原交付的 pre-sync 独立 QA | [bc309 固定 QA](review/pre-main-sync/independent-receipt.json)、[原 delivery manifest](review/pre-main-sync/delivery-manifest.json)、[原 checker](review/pre-main-sync/receipt-reviewer.py)。这些只证明旧 tree477，不证明新354或此次更新后的交付树。 |
| R9 既有运行 | [原 R9 47 份报告](../2026-10-18-objective-history/README.md)、[真实远端 transport / ARM history 接续](../2026-10-18-objective-history-ci/README.md)。原报告和原 321 素材归档保持不变。 |

| 身份 | 固定值与意义 |
| --- | --- |
| R9 desktop 产品合并 | [#193](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/193)，merge `aab50f347deb53fc79ac13ea3b84f846fefc70a7`；保留此前 [#195](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/195) 的无效 `cpu.max` parser 修复。 |
| R9 报告/CI 证据合并 | [#194](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/194)，merge `0c2bf0fc1ba473325a0266c7bd476b1ddbf66383`；本证据 worktree 的初始主干基线；随后依次集成 e15/71ce/7e。 |
| G1 首次失败本地源码 | `be6d8408878dc25fce3188e1fc759aa227bf8678` / tree `9992584208a8b03a97454e654ed603a47058f5fa`。实际编译失败、未启动 QEMU。 |
| G1 两个已执行客体源码 | `12e0547d2e6394548b15764b06346422c4fff31e` / tree `6b03c4827a28c9dc34456e7aa5f855b2f1f4b72f`。core 与 OSTD 均固定这个提交。 |
| 本地 G1 与 R9 证据集成 | `8cfea7a98d4cf0eaf689dcab4830992063962ec1` / tree `7e5632e9d7d9b45351e81913937235b64dddc321`，parents 为 12e 与 0c。集成只增加 R9 docs/results；它自己的 commit 身份不冒充前述已执行来源。最终候选身份另记。 |
| 首次普通产品/QueryAbi 候选 | `85b6ebf5647067f9811dbe14794cf80720bee3fa` / tree `d2a537689cfb7199291cc3af75d5d3d71e67b568`。kernel/asterinas、libs/os-control、support/build 与 12e 相同，新增独立候选 probe、手册和 CI 保存规则；第一次整体失败，原始收据保持。 |
| 修正的普通产品/QueryAbi 候选 | `4e077aef4913179a68aa0d814018ce1a9d87cafc` / tree `4e42c3833746cd2684d0a75020d73286820457e6`。仅修候选 C 的完整行输出和对应手册，保留 exact-line 判据；02 在 build 阶段失败，03 同源封闭运行接受。kernel/asterinas、libs/os-control、support/build 仍与 12e 全部字节一致。 |
| 首个普通远端代码发布 | Ready [PR #197](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/197)，远端 `f744fb248a6d264676d0b892d21d6c4582d72d0f` / tree `4e42c3833746cd2684d0a75020d73286820457e6`，base 0c，03:08:56 UTC 发布，29 个变更文件。tree 与本地 4e 相同，不含 untracked 残留；首轮普通 CI 的失败与后续修正分别追加。 |
| 原基线的最终 host 修正 | 本地 `bccb817e0d3f1987f59c1b9e7d94e939d2e6d1d3` / remote `107afb7436ca17177262fdfef2e6b5dfee13597a`，tree `65ddb50cd303f3c43a8226141c5298dca369db5d`。相对 4e 只有四个 host 测试/manifest 路径变化；107 的六 checks 与原 artifact 已独立接受。 |
| 并发主干与最终 G1 组合 | main `e15ae6a63edb5d4e7c475a001be82111d451b653` / tree `ee83cc9b2df092a09db596d23ad1391df03fe503`，与 bccb 合成 local 1ca / remote 1c054，tree `2b873aa43445c8a02351f5900074a38c6fa4820d`。local parents 为 bccb/e15，remote parents 为 107/e15；6,397 tracked，G1 33 路径除合并双方文字的 N0 手册外全部产品/测试字节不变。 |
| G1 已合入的主干身份 | `71ce079c3218a8692476e4113b60c9d2c0d2a172`，parents e15/1c054，tree `2b873aa43445c8a02351f5900074a38c6fa4820d`；03:59:41 UTC 实际 merge。1c PR 检查及产物已经接受；merge 后新 workflow 不转计为已执行。 |
| 本次报告整合的主干身份 | `7e859b98c58053b88ea2baabc3e5f645fd38dca5` / tree `354adb549b064c78477932ca943309694eb54356`，parents 为 71ce 与 #198 head `dafa1eba79cb1e17f880b5f0c5d57a80510d5d68`；04:29:28 UTC 实际合入。源码资格与 #198 原 Actions 产物另行绑定，不改写 G1 旧运行身份。 |
| Hepta 历史查询产品来源 | `2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5` / tree `f4ef891d43baf90d6eebd29921a5ed03222ef3ab`。原 f8 基线、原请求和历史语义保持原来源。 |
| Hepta CI 修订与安全诊断来源 | 远端 `d32e795f0d24df89fc57745f6fae70fbd0642eba`，本地等价 `1b0fedb8c2b510106848f6feaf530c9b3698399d`，tree 同为 `a3e718280a7e17b8c4a226a0232bf18c23fd3586`。普通 [PR #2815](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2815) 的状态按带时间的 CI 快照解释。 |
| Fleet fixture 独立修复 | 本地 `3749e151fd1a39c4b568afdb9e03028974ad86be` / tree `eb9dc083dfb6f4f57a98f0380683444aba98326a`，parent 为 1b；只改 `authority_port.rs` 的测试 helper。其 41 项测试和严格 Clippy 固定该提交，不冒充 d32 的远端 CI 结果。 |
| Fleet 的独立 main 来源 | local `e770156ba8b35c77829d189fc053dc5f9eb69f8b` / remote `b34cb44f06db0a66acb3d25b183a2a05c4cebc7e`，tree `15a3b89f59052368e28ce5ed4943dc2ab638844b`，parent 为真实 main f8；Ready [PR #2882](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2882)仅改一个 helper，未带入 #2815 的产品/CI 差异。 |
| 独立 scoped CI 存储修复 | local `71d9db8fd48a317fe5930392799522f186188d6a` / remote `a8ce72907288d1836612446b87cb1d5c184993ac`，tree `4688d8dfc139f990b3d770c8c081050a5ace1d26`，parent 为 f8；[Ready PR #2883](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2883)于 04:15:05 UTC 发布，只有一个 workflow 的五行 job env，不含 Fleet 或 Objective History 产品改动。 |

不同 commit、tree、输入集合、ELF 和执行记录分开列明。源内文档在测试前写下的“尚未运行”描述的是当时的准备状态；后续通过应引用本轮实际收据，而不是改写旧 handoff 记录。

## 2. G1-a 实际改变了什么

原 `CpuControl.max` 的 IRQ-disabled SpinLock 现在保护同一个 `CpuBandwidthState`：原 `CpuMax`、可选的原 `NativeResourceState` 和单向 detached 标记。预算、窗口、债务与调度计费仍由原 owner 管理，没有引入第二套累计或 CAS owner。`libs/os-control` 以关闭默认 std、仅启用 `portable-spin` 的方式满足 crate 编译；真实锁仍由 OSTD 提供，未实例化 portable namespace，也未把该 feature 当成已经通过的内核锁 backend。

一次绑定核对当前安装的真实 controller Arc、membership writer 和非零身份，只能发生一次。绑定起始 revision 为 1，保留当时预算；它没有追认绑定前存在外部配置历史。正常 `cpu.max` 写入在用户读取和解析成功后进入同一原预算锁，先设置 indeterminate fence，再执行原配置闭包，正常返回后提交新 revision 并清除 fence。同值写入也推进 revision，但不会清空已消费时间和债务。无效配置、revision 耗尽、已关闭或不确定状态会在预算变更前失败。

控制器替换先准备新对象，再关闭旧对象，最后发布新 RCU Arc。旧对象无论是否已绑定都会永久 detached；新对象不继承旧身份、revision 或权限。删除只有在原进程、尾账 lease 和 children 检查全部通过后才关闭管理，然后将 node 标记 dead。EBUSY 不提前失效；旧引用仍可计入已经发生的尾账，不把资源管理关闭变成计费清零。

本轮 revision **只覆盖 `cpu.max` 带宽配置**。`cpu.weight` 仍是原 AtomicU32/warning 路径，尚未实施权重强制执行，也未纳入共享 revision。生产 bootstrap 没有调用私有绑定入口；极值构造只存在于 `cfg(ktest)`。这些边界在开发手册和源码审查中明确保留。

| 新 owner 回归 | 实际执行对象及关键断言 |
| --- | --- |
| 一次绑定 | 当前真实预算保持；无效 ID 和重复绑定不改变身份/revision。 |
| 同值普通配置 | 真实 cgroup `cpu.max` 写入 revision 1→2，保留 usage/debt；旧 CAS 不执行 mutation callback。 |
| 无效配置 | 七种文本/范围错误均不消耗已绑定 revision、不修改预算。 |
| 替换已绑定 Arc | 原 RCU 路径先关闭旧实例，新实例无 metadata，统计保持。 |
| 替换未绑定 Arc | `native == None` 的旧 Arc 也不能晚到绑定或配置。 |
| 删除未绑定 Arc | node 仍保留同一个 Arc 时，也由 detached 拒绝晚到绑定。 |
| 删除已绑定 Arc | 身份、revision、原预算保持，后续管理拒绝。 |
| revision 极值 | 实际配置 MAX-1→MAX；此后的普通写入溢出失败，无回绕。 |
| mutation 不确定结果 | 可捕获 panic 后保留 indeterminate；删除不清除该 fence。 |
| 真实尾账 lease | 原未调度 Process/Task 的 zombie lease 阻止删除；生产计费入口保留 debit，释放后才允许删除。 |

上述是实际 controller、RCU、锁与 lease 路径测试。时间来自受控 fixture，Process/Task 没有实际调度；slice-backed `VmReader` 文本负例不等于 unmapped-user-address 的 EFAULT 实测。这些测试没有建立 BOOTTIME 对齐、运行任务跨 controller 代际归账、通用 SMP 或实际单窗口误差资格。

## 3. 实际失败、修复与锁定输入

第一次完整 core 构建在 01:33:26–01:34:58 UTC 真实失败：`Arc::ptr_eq` 收到 `ArcRef` 而不是显式借用的 `&Arc`，编译器报告 E0308。QEMU 没有启动，没有客体通过计数。同时，运行前后 2,980 个选定输入的比较发现工作根 `Cargo.lock` 被隐式更新。失败日志、两个原始 source map、改写后的锁和 diff 都保留，成功候选没有覆盖这次失败。

因果定位经历了可核对的反证：六次 OSDK 风格 `cargo metadata --no-deps` 查询没有改写原锁，因此早期对 OSDK util 的猜测被排除。实际写入来自 `parse_metadata!` 经 `component_generate()` / `get_component_toml_path()` 共用的完整 metadata 调用；`#[init_component]` 本身不调用该 metadata。隔离目录中，原 seed 加完整 metadata 成功并生成精确 observed lock；原 seed 加 `--locked` 返回 101 且不写锁；明确工作派生锁加完整 `--locked` 成功且保持字节，完整解析输出与第一次成功复现相同，均有 226 个 resolved packages。

修正保留完整组件图，给该调用增加 `--locked`，不改为 `--no-deps`。原 upstream seed 仍从固定 Git tree/blob 读取，SHA256 为 `6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316`；它没有被工作锁替换成一个新的“固定基线”。工作锁由该 seed 精确导出，仅增加本地 `os-control` 记录及 aster-core 依赖边，原有 spin 记录与所有其他包记录相同。

| 锁定输入 | 本轮固定内容 |
| --- | --- |
| 原 upstream Git seed | 234 packages；tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e`，blob `77d8f4be4cdc7365cd73a2e9f7638d46f3608b40`。 |
| 明确工作根锁 | 235 packages；SHA256 `af94d71680ecf3b9631e21c958263d5e41229033214f88dcff858bb14765a666`。 |
| core 测试派生锁 | 200 packages；SHA256 `85ccdcd1283d42af82ee8dca2faac2ee5401631ff150b35e43be46e1fc9c2150`。 |
| OSTD 测试锁 | 97 packages，原锁字节未变；SHA256 `bd2fa3a12577a44f4730de7228a7ceb1fb77cda68d45835825a219c62e2c5ec6`。 |
| 普通产品 run-base 锁 | 204 packages；SHA256 `e54bc99b3df5e21a1fdcd88d89b32ac478e73c7b4bf69ae0b1084f59d56fc506`。 |

独立检查逐项核对实际包记录，没有 external version/source/checksum 漂移。47 项静态门禁包含 7 个允许案例和 40 个拒绝案例，预期均满足；检查没有执行 Cargo，没有增加内核运行次数。`--pristine` 的原始路径未放宽；本轮只检查该路径的实现，没有重新导入整个 pristine 树运行完整导入测试。

## 4. 已执行的内核、普通产品与环境边界

| 执行 | 时间 UTC | 实际结果 | 资格边界 |
| --- | --- | --- | --- |
| 第一次 aster-core 构建 | 01:33:26–01:34:58 | exit 1；E0308、根锁改写；未启动客体。 | 固定 be6，失败完整保留。 |
| 修正后的完整 aster-core 目标 | 01:55:03–01:56:48 | 179/179，0 failed、0 filtered、0 soft skip；十项新 G1-a 回归各成功一次。 | 固定 12e；注册表 542 tests/16 crates 不是执行计数，本次未执行的其他 crate 不加总。 |
| 完整 OSTD 目标 | 01:59:14–01:59:39 | 221 reported passed；3 VMX/EPT soft skip，实际下界 218。 | 固定 12e；不可用硬件路径没有运行。 |
| 首次普通非 ktest 产品与 QueryAbi 候选 | 02:15:12–02:17:31 | 普通 kernel build/boot 的 wrapper 为 0、raw QEMU 为 33，204 包 run-base 锁精确匹配；整体候选 exit 1、未被接受。 | 固定 85b6。第二 guest raw 33、BOOT_OK 一次，原串口含全部 13 个 HEPTA marker；exact-line 验收计数为 0，末次 source gate 观察到 untracked OSDK.toml 残留而失败。原 false/0 字段不改。 |
| 修订候选的第二次普通运行 | 02:30:54–02:30:55 | build wrapper 1；`ln` 报 File exists，未启动 guest，整体未接受。 | 固定 4e；残留 canonical OSDK.toml 的原字节和发生时序保留，写入来源未确定。 |
| 同一修订候选的第三次封闭运行 | 02:32:59–02:33:05 | ordinary wrapper 0/raw 33；第二 guest raw 33、14 exact markers 各一次，顺序正确、无 timeout/guest failure；204 包锁一致，overall accepted。 | 固定 4e；三个 5,851 输入 snapshot 相同、当次结束 git clean；复用暖 target。恢复其他工具后残留再次出现，未据此确定先前写者。 |

首次普通候选的失败收据必须结合原 serial 阅读：C probe 使用 unbuffered `puts`，marker 正文与下一次 SYS_WRITE trace 粘在同一行，原 runner 的 `lines.count` 未把它们接受为精确独立行。这是候选标记输出分帧与严格逐行验收不匹配，raw 中的 marker 正文实际存在；同时还存在真正的 untracked `kernel/asterinas/kernel/OSDK.toml` 残留。两类问题独立保留，不能只因 QEMU raw 33 或原字符串可见就把整体结果改成 pass。修订仅在新的候选 include wrapper 中把 marker 和换行合成一次有界 write，处理 EINTR、短写失败；exact-line 接受规则和原 A05 C/runner 两个文件不改。第二次因 build 所需 OSDK.toml 已存在而失败；第三次全 workspace 无并发本地工具的封闭执行在相同 4e 上完整接受。原 attempt01/02 的 false/0 字段不重写。后续 canonical 残留再现仍是独立未决观察，不能写成已经证明了工具同步或某个程序是写者。

前述 12e 上的 aster-core 与 OSTD 两轮 ktest 客体共报告 400 个测试函数成功返回，其中 3 个是明确 soft skip，实际执行下界为 397。两个 wrapper 运行前后均核对 2,980 个选定输入，四份 source map 相同；独立复核进一步匹配固定 Git blob、文件 mode 与实际 ELF。未把静态 47 个门禁、注册 inventory、旧 R9/R8 测试或本轮两个不同目标的 metadata 查询混入 guest 计数。

环境为固定 Rust `nightly-2026-07-21`、源内 OSDK 0.19.0、QEMU 8.2.2、q35 / TCG / CPU max / 1 vCPU / 512 MiB / SeaBIOS，网络和数据盘关闭。实际没有 KVM，也没有可用 VMX/EPT。这是 x86_64 QEMU profile，不是完整上游矩阵、ARM 内核、实机、GPU 或手机运行。环境预检中的 paused QMP 只证明 QEMU 预启动可用，不算 guest 运行。

第三次普通产品使用的 ELF SHA256 为 `27c60a34e0a67e839d885ada14b43719131f8ec2e527d65e3f1dd6290f014a89`，与第一次普通 build 的产物相同；这次执行复用已绑定的暖构建缓存，不是冷构建耗时或在新 4e 上重编译全部 Rust crate 的证明。新的静态 probe SHA256 为 `f9cd1d3aca3364f4b446849f5b31ef5b5f8034a9bc08f37ef4ea670847e5da3a`，注入 initramfs SHA256 为 `f65ca64ef10220d91e5b0f4b7d81b3f0b751debe4c191e2e28f2c07f15be59c4`。13 个 HEPTA marker 加一个 BOOT marker 是不同语义的串口判据，不是新增 14 条 Rust 单元测试。

[三次运行独立复核](g1-evidence/g1-queryabi-review/queryabi-candidate-runtime-review.json)逐项重算现有 source snapshot 的 5,851 个路径、Git blob、mode、字节数和 SHA，核对实际 QEMU 参数、ELF、initramfs 的成员与属性、probe 字节和串口顺序。代码 blocker 为空；唯一保留的 blocking 观察是 ENV-1，即后续当前工作区残留再现、写者未知。03 的封闭执行接受为 true，01/02 仍为 false。八项宿主 fixture 收据是已实际执行的候选 runner 检查，本次独立复核没有再运行 Cargo、QEMU 或 fixture。

普通产品的 generated run-base lock 精确匹配，由固定 runner 在实际执行时读取并在结果中保存 SHA、包数与匹配结果。**这三次普通候选材料没有另存 generated lock 的原始副本**，独立审查也没有从后来变化的 target 目录补读它。独立检查可重读固定 Git 中的 committed minimal lock，并核对不可变 runner 与原结果，但不能声称第二次独立比较过该 generated lock 的原字节。core/OSTD 测试的实际 generated lock 副本则另有保留。此范围不改变原门禁，也不把缺少的副本冒充现有材料。

两份实际被 QEMU 使用的测试 ELF 均完整保留：core 为 9,628,168 字节，SHA256 `e9e08a0103173cf8e6bef67ebfe9ef41204b97f23f6b2aff5bad7574c68044e3`；OSTD 为 2,002,472 字节，其精确 SHA 与 ELF 字段见独立运行复核。它们是 ELF64 little-endian，但 QEMU multiboot 包装按固定 `make_elf_for_qemu` 写入 `e_machine=3`，不能误报为头字段 `EM_X86_64=62`。

### 普通 GitHub CI：失败、修正、再运行分别固定

[f744 原头](g1-remote-ci-f744/README.md)的 G0 在 35 项 Python wire/spec 中出现 1 failure、1 error：旧 preflight 测试仍调用已移除的函数，旧 A06 测试把同一生成 ELF 的文本使用次数固定为两次。它们使后续步骤未执行。A03 的 13 个 default-shim Loom 模型先成功，随后严格 Clippy 因未知 `cfg(ktest)` 失败，不能把该 partial 结果称为 A03 全过。A06 则独立成功；原 ZIP 的 76 个成员、实际 source/ELF/锁/串口与八次 guest 全部重新核对。

[463f 中间头](g1-remote-ci-463f/README.md)修正了上述三处，G0/A06 success，两组 19 个 Loom 模型成功；随后另一个 allocator 生成 manifest 暴露相同 cfg 登记遗漏，build/fmt 成功、Clippy exit 101，allocator runtime 没有执行。这项真实失败促成第四处最小修正。两个 known-name 登记均保留 `warn` 和外层 `-D warnings`，没有启用 ktest 或新增 lint allow；A06 测试改为分别检查实际 hash/probe/artifact 用途，prefetch fixture 调用真实 seed/package 审计并只替代 Cargo 命令，另有锁变更必须在 metadata 前失败的负例。

独立 [bccb host 原始验证](g1-ci-host-correction/final-validation.json)实际得到 ABI 78，control std 225、portable-spin 225，两组 Loom 13/26,675 schedules 与 6/578 schedules，19 个完整 allocator 场景 alloc/realloc/dealloc 均零；fmt、严格 Clippy 和 bare rlib 构建通过。两个 backend 的 225 有重叠，不加总为 450 个独立场景。root 的原 36 项 spec 日志另按自己的 bc778 来源保存，独立审查只核对原日志计数。初始 allocator、offline 缓存和额外 `--locked` 参数失败也全部保留，不转成内核运行错误或静默删除。

[107afb 精确头](g1-remote-ci-107afb/exact-head-ci-review.json)于 03:45:11 UTC 实读确认六 checks 全 success；G0 20 个步骤、A03 10 个步骤和 A06 12 个步骤全部成功，原产物独立接受。该 A06 的 **8 次 guest**包含两个 ktest、普通 boot、QueryAbi 与四次 quota；400 reported passed 含 3 soft skip，实际下界 397，10 项 G1-a 回归、14 个精确 marker 和原 1/2 vCPU 各两次 quota 均通过。四次受限值分别为 0.900%、0.819%、0.826%、0.875%，仍只授予原 3% 上界的短时 leaf profile。

f744 和 107 的完整 source 复核均只覆盖 **ktest 之后的普通 boot/QueryAbi 区间**：三个 5,851 文件 snapshot 与其精确 Git source 相同、该区间结束 clean。它不是每次 ktest 或后续四次 quota 的全树快照，最后 Actions cleanup success 也不是另一份最终 Git clean 测量。ktest 实际生成锁原件已保留；普通产品 204 包生成锁只有固定 runner 测量与 committed minimal lock 比较，没有原始生成锁副本。463f 的中间产物审查范围更窄，不借用其他头的完整逐 Git/ELF 审查。

其后主干并发更新为 e15。本轮从 Git 全量比较 567 个变化路径（其中 22 个非 results，不能依赖 GitHub API 截断的前 300 项），保留 Runtime/CLI/process guard 和新 A04 handoff，机械合入 G1。唯一交叠文件是 N0 manual，双方独立段落都保留。新 1ca/1c054 的源码、6,397 个 tracked 输入与正常 CI 已另外绑定并接受，详见下一段；107 的旧基线成功继续留在自己的独立包中。

**1c054 固定 G1 组合的独立接受：**[1c054 原始审查](g1-remote-ci-1c054/exact-head-ci-review.json)在 03:56:00 UTC 确认六 checks 全 success；A06 run `39196471075` 的 12 步于 03:55:04 完成，实际原 ZIP 18,446,493 字节、76 成员均已审查。新普通 boot/QueryAbi 的三份 **6,397 文件 / 5,188 唯一 blob / 100,508,712 字节**快照与该次 1c054 Git 对象一致，该闭合区间结束 clean。该头实际八个 guest、400报告含3skip/397下界、十个G1回归、14精确标记与四个quota分别核对；本次受限值为1 vCPU 1.000%/0.910%，2 vCPU 0.905%/1.000%。这些是新运行，不是累计旧轮计数。其 source gate、生成锁与有限profile范围与上文同样明确，合入同tree主干71ce不扩张这些资格。

### 交付前主干 #198：单独核对 SCM_RIGHTS/CLOEXEC

04:29:28 UTC 合入的 #198 相对 main71ce 有 **37 个变化路径**，实际生产改动为五个 Unix socket / message flags / recvmsg 文件。最终 FD flags 在 `FileTable::insert` 前构造，`MSG_CMSG_CLOEXEC` 沿原 ancillary 写入链传递，使接收 FD 首次可见时已经带有 CLOEXEC。本轮交付合并保留新 main 的全部 blob/mode；G1-a 的 CPU owner、os-control 与 HOS2 产品输入没有被这五个 socket 文件改写，见[源码整合核对](source-publication/report-main-sync/source-integration-review.json)。

[新主干的独立说明](source-publication/report-main-sync/README.md)将实际 Actions 产物与历史 RED 分开。run `39198594211` / artifact `12162813771` 中，Linux **6.17.0-1022-azure** 与新普通内核使用同一 probe ELF `9b80de2b…5fb1`；Linux 与 x86_64 / QEMU 8.2.2 / TCG / 1 vCPU guest 均完成 **27 PASS / probe exit 0**，guest raw exit 33。新内核 ELF 为 `1145311a…3737b`，客体记录耗时约 0.916 秒。原完整摘要、成员身份和独立审查由新增说明链接，原 ZIP 继续引用 Actions artifact，本轮不将它重打进 R10 的旧 14 份归档。

Git 中历史 probe `0723be7d…eb56` 使用的是 Linux **6.18.55** 参考：该 ELF 在 Linux 上 27 PASS，在旧普通内核 `f8785d93…4681` 上 3 PASS / 24 FAIL，27 项全部完成并返回 probe exit 1。PR 正文另称该历史 ELF 曾在新内核 GREEN，但这次已取得的 CI artifact 只包含 `9b80…` 的新运行；这里没有取得 `0723…` 在新内核上的那次原件，不能将两份 ELF 拼成一次同输入 RED/GREEN。该材料缺口不是新实现的已知阻塞。

源码支持插入时原子设置 flags；27 项中的 fork/exec 验证是继承语义检查，**没有执行并发 exec 竞态压力测试**。这份独立 profile 也不授予完整 A04 四 ELF/rootfs、Hepta K↔D、SMP、硬件或移动设备资格。本次#198的独立收据另核对九个guest调用、core179与OSTD221报告（含3softskip/397下界）、十个G1测试和14个QueryAbi标记，均属于本头新运行，不能与原1c八客体相加。全树6,426文件快照只覆盖普通product/QueryAbi区间，SCM之后没有另一份全树快照；四份quota只核对原收据/serial身份，未重复旧oracle。原1c完整包继续保留自己的资格范围。

## 5. Hepta 普通 CI 与依赖安全债务

当前 owner PR 的 CI 修订只把 scoped 外层时间预算从 40 分钟改为 75 分钟，并显式保留内层 3,600 秒 timeout；依赖选择、`just test`、`--locked`、产物和 required 汇聚规则保留。该 workflow 变更按原策略实际选择 `full_repo=true`，scoped lane 按规则跳过。旧 2be 的 cancelled 不是新 d32 的测试结果，71 项本地 Python CI 回归也不是 Hepta Rust 或新内核资格。

安全包冻结观察时间是 **2026-10-19 01:56:31–01:56:32 UTC**。在该精确 d32 头，Architecture source-head 于 01:53:04 成功，Architecture required 于 01:53:09 成功；cargo-deny 失败，blocking-ci 仍有 15 个 SDK/Bazel job 运行，`CI required` 尚未生成。PR #2815 是 Ready / open / unmerged / blocked，保持普通 squash auto-merge。后续 CI 状态需要另外保存更新的带时快照，不能改写这个冻结包。

**[后续 root 原始快照](owner-ci-updates/root-ci-snapshot-20261019.json)为 02:16:30 UTC：**精确 d32 的 47 checks 为 24 success、6 skipped、1 neutral、4 failure、12 in_progress。除 cargo-deny 外，Ubuntu Clippy job `117846024935`（02:01:02 完成）、macOS ARM Clippy job `117846024963`（02:10:10 完成）、Windows test shard 2/4 job `117846025117`（02:07:07 完成）也失败。Architecture required 仍成功，CI required 尚未生成，PR 仍 blocked。新增原始快照和具体失败诊断在独立追加材料中保留；安全包中“唯一失败”只描述原 01:56 观察，不能当作本轮最新状态。

远端 cargo-deny 的原始日志读取失败，未恢复。完整仓库同源同锁同 policy 的隔离本机诊断则独立取得 **13 errors、85 warnings**：8 个包对应 **8 条漏洞公告 + 5 条停止维护公告**，advisories FAILED，bans/licenses/sources OK。本机工具版本和 flags 与固定 action 对齐，另加 `--locked`，但主机环境和执行时刻不同；本报告不声称远端恰好产生同样 13 条错误。

| 修复范围 | 已核对事实 | 实施要求与未完成项 |
| --- | --- | --- |
| rustls 0.23.45 | 四条漏洞公告要求 >=0.23.46；该 patch 的 MSRV 1.71 可被当前 Rust 1.95 满足。 | 目标明确的 patch 更新、实际锁 diff、TLS/HTTP/WebSocket 和依赖方回归；尚未更新或编译。 |
| zip 2.4.2 | 三条漏洞公告要求 >=9.0.0。自写提取器读取 `unix_mode()`，直接设置输出权限；没有直接调用 `ZipArchive::extract`。9.0.5 的 `ZipFile` 泛型 API 和权限处理已核对。 | 适配 API，用真实归档验证特殊权限位、逃逸、链接、已有路径、损坏与失败不激活。库版本修复范围不代替应用路径实际验证。 |
| unsafe-libyaml 0.2.11 | 停止维护，经 serde_yaml 进入多个插件/技能/迁移路径；相似 fork 名称不保证去掉该底层。 | 选择受维护解析器并回归实际 frontmatter、Value、scalar、错误和序列化语义。 |
| zbus_names / zvariant / zvariant_derive | 三条停止维护记录来自 Linux secret-service 后端；同版 keyring 3.6.3 有保持持久化能力的同步后端候选。 | 验证凭证读写删除、service/account、锁定会话与 async 调用边界，不以关闭持久化规避门禁。 |
| matrix-sdk-crypto / anymap2 | crypto >=0.19 的 MSRV 为 Rust 1.96；0.19.1 仍依赖 anymap2。SQLite 还存在 rusqlite/libsqlite3-sys 与 SQLx 已锁区间不相交。 | Matrix/anymap/SQLite/工具链与现有 patch 联合迁移，覆盖加密缺键、数据库迁移/WAL/恢复；没有已验证的仅改一个版本即可全绿组合。 |

实际 x86_64 与 aarch64 Linux 的 `codex-hepta-agentd --no-default-features` normal 依赖图均不含 anymap2/matrix-sdk-crypto，但包含其余所列链路；rustls 所列 features 没有 brotli，zvariant_derive 是 proc-macro。静态图中的存在不证明实际漏洞触发，未出现也不证明整个仓库没有该依赖。没有执行攻击、读取凭证或操作生产设备；原 15 项 history 场景没有在安全诊断里重跑。

完整修复还要保持 Cargo/Bazel 工具链和派生锁一致，运行正常 required 门禁。本轮没有更改 deny policy、增加忽略、更新依赖或豁免合并；安全包是一份具备具体版本、源码和执行依据的迁移工单。

### 原始 Bazel 日志追加：两个 lint 与真实 Windows 边界失败

02:18:45–02:18:46 UTC 成功取得 Ubuntu/macOS Clippy 与 Windows shard 2 三份原 job 解码日志。实际 checkout 是 CI prospective merge `60a3376902982d79e85173d6aaf6bd631b4c4cf3`，tree 与 d32 相同；该 merge 不是已合入主干的事实。30 个失败位置、支撑源码与构建策略文件在 f8 / 2be / 当前等价树的 Git blob 相同，证明这些具体文件不属于本 PR 新改动；本轮没有重跑 f8 来证明每个动态失败的完整因果。

| 新诊断范围 | 已取得的原始事实 | 修复边界 |
| --- | --- | --- |
| 两平台 Clippy | 同一个 hepta-fleet `authority_port.rs` 测试 helper 的 `admit_host(...).unwrap()` 被 `-D clippy::unwrap-used` 拒绝。 | 原诊断建议显式 `assert!(admission.is_ok(), ...)`，直接换 expect 也被现有 policy 拒绝。后续独立修复及 Linux 窄域实测见下节；原两份远端失败记录不改。 |
| Windows 编译目标 | process_wrapper 复制 `.temp-archive-*.a` 时 os error 2；既有临时输出 patch 未覆盖这个命名。 | 需精确临时文件分类与稳定库复制的真实 Windows 验证；具体消失原因尚未独立追踪。 |
| Windows shard 2 | 最终 Bazel target 摘要：103/142 执行，89 pass、1 fails to build、14 fail locally、38 skipped。包含 non-Unix registry stub、目录句柄/持久化、绝对路径、runfiles、fixture 迁移与 Session 状态问题。 | 逐 target 的日志和因果限制见追加报告，不能归结为一个超时、网络或字符串问题。 |
| Windows 删除隔离 | 受限 token 的外部写/创建被拒绝，但外部文件/目录删除返回成功。另一个 legacy process 后，sentinel 读取结果为 `None`、受保护目录 `is_dir=false`，未满足原断言；`None` 不能独立区分已删除与不可读。 | token 测试显示固定 CI native fixture 的实际删除拒绝边界失败，当前 Windows 删除隔离/控制门禁不能接受。legacy 的未满足断言另保留，不扩大为独立证明物理删除。需要 token/ACL/DELETE 与 parent-delete 修复及实际 sentinel 回归，不能弱化预期。 |

这里没有把固定 fixture 的失败扩大为所有用户设备已经被利用，也没有调用真实用户设备。它足以阻止将当前项目宣称为 Windows 生产控制工具。上述原 job 诊断与本机 cargo-deny 13 条拒绝分别保存，没有互相替代。

**Bazel 追加包冻结快照为 02:24:28–02:24:29 UTC：**47 checks 为 24 success、6 skipped、1 neutral、6 failure、10 in_progress；新增 Windows shard 1 和 shard 3 失败，只取得状态，没有取得其日志，也未推断与 shard 2 同因。Architecture required success，当时 CI required 尚未生成，owner PR #2815 Ready/open/unmerged/blocked。旧 01:56 和 02:16 快照保持各自原字节。

**[03:10:54 UTC 的后续原始快照](owner-ci-updates/current-status-after-g1-publication.json)已追加：**同一 d32 头共有 **49 checks：8 failure、24 success、6 skipped、1 neutral、9 cancelled、1 in_progress**，最后一项是 Analyze rust。8 个红色 check 包含 **6 个实际 job**（cargo-deny、两平台 Clippy、Windows shards 1/2/3）和 **2 个汇总 gate**，不能称为 8 个独立缺陷。Windows aggregate 于 02:25:11 failure，`CI required` 于 02:25:23 failure；原 blocking run 列出 37 jobs。PR #2815 仍 Ready/open/unmerged/blocked，base 为 f8，不能继续写成“CI required 尚未生成”或将该 owner PR 记为已通过/合并。九项 cancelled 的具体原因没有由这份状态快照独立建立。

**[04:09:45–04:09:46 UTC 的后续冻结观察](hepta-fleet-main-remote-ci/final-observation.json)**确认 #2815 的同一 d32 头 49 checks 已全部终态：**26 success、8 failure、6 skipped、9 cancelled**，没有剩余 running。CI required 和 Architecture required 分别保持 failure / success，Ready/open/blocked、未合并。原 CI required 日志拒绝 `bazel: failure, cargo-deny: failure, sdk: cancelled`；该状态追加在独立 Fleet/CI 诊断包，没有覆盖 03:10 快照，也没有把其安全和 Windows 根因归给后来 Fleet 的 ENOSPC。

### 后续独立修复：Fleet admission fixture

冻结后另有一个具体修复，保存在 [hepta-fleet-fixture-fix](hepta-fleet-fixture-fix/README.md)，没有回写两个诊断包。固定本地 `3749e151fd1a39c4b568afdb9e03028974ad86be` 只将 `ledger()` 的 `admit_host(...).unwrap()` 改为保存返回值并显式断言成功；所有 HostObservation 输入保持原值。失败仍使测试失败，并显示完整结果。没有增加 lint allow、改依赖或 deny policy，也没有将 expect 当成绕过办法。

在 Linux x86_64 / Rust 1.95.0 上，02:42:24–02:43:03 UTC 实际运行原 `just test -p codex-hepta-fleet --lib --locked --offline --cargo-profile dev-small -j 1`，**41 passed / 0 failed / 0 skipped**，包括使用该 helper 的既有 authority lease 测试。02:45:18–02:45:38 的原 `just clippy` recipe 包含 `--tests`，并显式 `-D clippy::unwrap_used -D clippy::expect_used`，exit 0。两次实际测试/Clippy 前后源码 commit、tree 和字节一致；此前 fmt 在提交冻结前执行。详见 [final-validation.json](hepta-fleet-fixture-fix/final-validation.json) 和原 command logs。

nextest 日志仍保留 13 条 scoped metadata package-ID warning；这与 cargo-deny 的 13 条安全拒绝完全不同，不能称为“零警告”。该补丁没有执行 Bazel、macOS、ARM64 或 Windows，没有解决 Windows 删除边界和依赖安全债务，也不把原 d32 的失败改为成功。

随后将同一 helper 修复独立重放到实际 main f8，形成 e770 / tree15a3b89；[新基线原验证](hepta-fleet-fixture-main-fix/final-validation.json)于 03:13:12–03:13:21 UTC 再次实际得到 **41 passed / 0 failed / 0 skipped**，03:13:54–03:14:03 的原 Clippy recipe 含 tests、显式 deny unwrap/expect，exit 0，fmt 和所有源码前后检查也通过。它没有包含 #2815 的 Objective History 或超时修改；两候选之间 29 个输入差异与完整压缩 diff 保留，不能把换回 main 的差异称为本 PR 相对 main 删除了产品。

[发布收据](source-publication/final-source-and-fleet-publication.json)记录 03:35:50 UTC Ready/open 的独立 [PR #2882](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2882)，remote b34cb44 与 local e770 同树。后续普通 CI 的真实 ENOSPC 失败在下一节独立追加；本地 Cargo 通过不等于两平台 Bazel 或 Windows 已修复，也不代替 #2815 的失败状态。

### Fleet 原 CI 的 ENOSPC 与独立存储修复

[原远端失败包](hepta-fleet-main-remote-ci/README.md)绑定 PR #2882 的 b34 精确头。正常 dependency-impact 选择 **134 个包**，原 `just test --locked` 命令在编译 app-server/core 的测试目标时用尽 runner 文件系统。03:52:53 UTC 原日志出现 LLVM 的 `No space left on device`，随后 runner 自己写诊断也失败；scoped job 于 03:52:59 failure，`CI required` 于 03:53:12 正常拒绝。原日志和下载 artifact 都保留，这次执行没有取得 134 包测试完成收据。该 scoped lane 本来不运行 Bazel Clippy，因此不能把本机 41 tests / 严格 Clippy 填成远端 lint 成功。

[独立 CI 配置修复](hepta-scoped-ci-storage-fix/README.md)基于真实 main f8，只在 `hepta-scoped` job 新增五行 `env`：`CARGO_INCREMENTAL=0`、`CARGO_BUILD_JOBS=2`、`CARGO_PROFILE_TEST_DEBUG=0`、`CARGO_PROFILE_DEV_DEBUG=0`。它沿用仓库现有 native qualification 的配置，减少可丢弃构建的增量缓存和调试信息，限定 Cargo 编译并发。scope 选择、134 包集合与完整命令向量、锁、features、nextest profile 和测试并发规则、timeout、必需 job 失败传播保持原样。未通过删包、缩小 scope 或放宽 required gate 隐去原失败。

该固定本地 71d9 的 actionlint 1.7.12 和 scoped fmt 通过；去除新增 env 后 YAML 与原 workflow 相同。**102 个不同的既有 Python 契约测试**在记录的调用中通过，覆盖选择、真实 feature 失败传播，以及失败、零测试、输出上限、source drift 和 timeout 拒绝。已有 `codex-utils-string` 的 **18 项库测试**在四项环境设置下实际通过；捕获的编译命令无 incremental/debuginfo 参数，包含 `strip=debuginfo`，构建输出记录 `NUM_JOBS=2`、`OPT_LEVEL=0`。这是实际小 crate 的配置效果，不能外推为 134 包已经完成。错误模块导入路径和错误 nextest verbosity 两次本地调用失败均原样保留，修正调用后没有改测试或产品源码。本地 nextest 0.9.148 与原 workflow pin 0.9.103 也分别记录。

[PR #2883](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2883)于 **04:15:05 UTC** Ready/open 发布，remote a8ce 与 local 71d9 精确同 tree；[原 API 与源码发布收据](source-publication/hepta-scoped-disk/publication.json)固定该事实。当前尚未合并，原 134 包没有在新配置下完成远端重跑，不能称 ENOSPC 已闭合。workflow 改动仍按现有策略进入 full-repo CI，没有增加 scope 例外；后续需要集成被验收的配置，再以完整 impact plan 实跑 Fleet 并取得真实完成收据。安全债务和 Windows 门禁继续作为独立未完成项，原 #2815、#2882 的失败不改写。

**[04:17:21 UTC 的当时原始 CI 观察](source-publication/hepta-scoped-disk/initial-ci-and-fleet-status.json)**另明确了两个 PR 的实际状态。#2883 的 a8ce 有 **45 checks：17 success、20 in_progress、6 skipped、1 neutral、1 failure**；唯一当时已失败的 check 是 cargo-deny job `117886607679`，04:17:17 failure。scoped native job `117886609136` 实际 skipped，符合 workflow 改动进入 full-repo 的原策略，不能算作一次 134 包重跑。新 deny 原日志读取再次返回 `Transport closed`，见[原失败收据](source-publication/hepta-scoped-disk/cargo-deny-log-attempt.json)；这里仅确认精确头 check 失败，不能把此前本地 13 条安全拒绝改记为本次远端日志的 13 项。

同一观察中，#2882 的 b34 有 **24 checks：12 success、2 failure、8 skipped、1 neutral、1 in_progress**；两项红色是已述 scoped job 和 `CI required`，不是两个独立根因。Architecture required 已于 04:01:02 success，PR 仍 open/blocked。剩余运行项与新 PR 的后续结果不在这份冻结观察中，既有失败、原 manifest 和来源都保持各自时点。

### 最后有界状态：04:44:15–04:45:54 UTC

[18 个原始/派生文本文件](hepta-final-status/README.md)保存每次请求的起止时间。这是跨 API 端点的有界快照，不是原子事务；之后本轮停止扩大观察窗口。

| PR / 固定头 | 该窗口实际 checks | 普通合并状态与未闭合项 |
| --- | --- | --- |
| #2815 / d32 | 49：26 success / 8 failure / 6 skipped / 9 cancelled | Ready/open/unmerged/blocked；CI required failure，Architecture required success。8 红仍为 6 实际 jobs 加 2 汇总 gate，原安全/Windows 债务未关闭。 |
| #2882 / b34 | 24：12 success / 2 failure / 8 skipped / 1 neutral / 1 running | Ready/open/unmerged/blocked；CI required failure，Architecture required success。scoped 原 ENOSPC 保留，未取得完整测试完成收据。 |
| #2883 / a8ce | 46：21 success / 1 failure / 6 skipped / 1 neutral / 17 running | Ready/open/unmerged/blocked；两个 required 汇总在该精确头尚未出现。已失败 cargo-deny 的原日志再次 Transport closed，远端实际拒绝明细未知。 |

#2883 的原 scoped job 为 **skipped / 0 steps**；实际 scope 日志明确唯一 workflow 路径触发 `full_repo=true`。该次没有重新资格验证原 134 包，不能据此说远端 ENOSPC 已解决。API 的 `merged=false` / `merged_at=null` 优先于非空 prospective `merge_commit_sha`；三个 PR 都没有合入。branch 响应列出两个 required gate，但独立 protection 端点仍为 403；不据此推断完整管理配置或保护变更。旧 04:17、Fleet 原失败和两份安全诊断包均未回写。

## 6. A00–A10 文档覆盖与产品进度

下表以 R9 在固定 `207ff9da7dac83c57b0cbae46c4b03ecfba3baa9` 上实读的 11 模块、47 手册、57 本地材料为历史基线。其 53 个 INDEX 本地链接和 225 个一跳目标是 **R9 当时执行的存在性检查**。R10 增量只核对本轮改动的具体手册、当前目标存在与引用，不把历史审查重新记成一次全量测试，也不以文档数量估算完成百分比。

[本轮独立 delta](module-documentation-delta.json)另检查当前 INDEX 模块表的 **72 个本地目标**，实读 **16 份新增或修改的手册**，核对这些手册的 **106 个一跳本地目标**，缺失均为 0。历史 57 份材料逐字节比较为 45 份不变、12 份已改变、0 份缺失；改变者包括新主干的 Runtime/进程与本轮 G1 文档。这些数字描述文档和引用范围，没有重新执行历史测试，也不替代各模块运行验收。

| 模块 | 开发与技术文档是否具体 | R10 增量及当前不足 |
| --- | --- | --- |
| A00 集成 | PLAN/STATUS 提供交接；ARCHITECTURE、DECISIONS、VALIDATION 为共享技术文档。 | 增加本轮独立来源、失败和下一门禁；仍不是单独可执行产品模块。 |
| A01 源码与启动 | 构建与 ktest 手册包含固定源、环境、命令、输入输出、退出码和回放限制。 | 增加 immutable Git seed / 明确工作派生锁、完整 locked metadata，连接 G1-a manual；真实新 kernel tests 已取得。普通产品候选 03 当次封闭执行接受，后续残留未决观察独立记录。 |
| A02 HOS2 codec | ABI 开发验收、证据完整性手册与共享 NATIVE_ABI；有具体 Rust codec。 | 本轮在 bccb/107 的明确 host 门禁上取得 ABI 78；旧 pinned 13/13 与 Python 62 保持自己的来源。wire 完成不代表五个内核操作完成。 |
| A03 control core | API_CONTRACT 与 VALIDATION 提供具体 owner/CAS/namespace/并发契约。 | 本轮将原 NativeResourceState 接入实际 CPU owner；bccb 的两 backend/19 Loom/19 allocation 实际复跑与远端 CI 分别保存。durable K/fsync 和完整 IRQ/SMP 仍未闭合。 |
| A04 Linux / Hepta ELF | e15 新增 [164 行交接手册](../../../docs/agents/handoffs/A04_LINUX_HEPTA_ELF.md)，7e 更新其中两行并新增 [59 行 SCM_RIGHTS/CLOEXEC 独立手册](../../../tests/workloads/linux/SCM_RIGHTS_CLOEXEC.md)：具体实现、命令、错误、27 项判据、历史 RED 与资格边界均明确。 | 主干已有交接与这一独立实现；`tests/workloads/linux/` 不再整体缺失。原三份完整候选手册和四 ELF/rootfs 仍在固定25c，SCM profile 不替代它们；PR #8 状态只按03:39原API解释。 |
| A05 内核控制 | A05_KERNEL_CONTROL 与共享 ABI/构建文档具体描述入口和身份。 | QueryAbi 保持；trusted-init、最终 Process/exec 授权和其余四操作未闭合。4e 的普通用户态 QueryAbi / 四项禁用操作在 03 当次通过，能力授予和效果操作仍不启用。 |
| A06 CPU owner | 原 N0 / backend manual 加本轮独立 G1-a manual，开发与技术交接具体。 | 同锁 revision、不可逆 detach 和十项实际回归完成；cpu.weight、BOOTTIME/结算、运行任务代际归账和完整 G1 继续推进。 |
| A07 Hepta 用户态 | client README/CONTRACT/RUN、Objective transport/history、probe 和源码契约均有实际入口。 | R9 x86/ARM Linux host 历史查询真实通过；本轮 owner CI 超时预算已修订，依赖安全、Bazel lint 与 Windows 失败仍阻塞普通 CI。生产 issuer、准确请求/anchor 持久保存、K↔D 和设备效果未闭合。 |
| A08 Android | 宿主开发手册、INTERFACES、kernel gaps 与来源/验证文档存在。 | Binder、seccomp/MAC 和 Android guest/手机控制没有因本轮结果获得资格。 |
| A09 硬件/VMM | device lifecycle、GATES、PROVENANCE 与共享硬件文档存在。 | 元数据/宿主模型不能代替 DMA、IOMMU/GPU 或实机复位资格；本轮未新增这类运行。 |
| A10 Rust UI | RUN、聊天/任务工作区、Session、新鲜度、字体/IME 与窗口 probe 手册具体。 | e15 的 Runtime 总年龄、同来源样本、真实 CLI 被杀/成功 leader 回收修复及新手册已保留；其 137 UI / 53 all-features 与原图各属自己的固定执行。匹配部署 Session/Shell/ctl；history 新投影、CJK/IME/Wayland/GPU、Asterinas UI 与移动适配仍需验证。 |

当前 11 模块都有具体开发/技术入口，允许合写或共享契约；e15 的 A04 handoff 和 7e 的独立 SCM 实现/手册已在主干。原三份完整候选手册、完整四 ELF/rootfs 仍未整合，所以“每个模块的实现和专属完整手册均已齐全”仍不能作为结论。此前对 0c/4e 和 e15 的 A04 缺口观察保留历史时点，不继续冒充当前7e的现状。R10 的 `INDEX` 直接连接 A01/A06 新手册和本轮实际证据，避免仅从旧 R8/R9 表格推断最新实现。

## 7. 是否能作为 Hepta 主导 AI native OS 的 Organ

与已经实测的固定 Hepta owner 候选配对时，当前 desktop 可以继续作为 **受控 Linux host 交互候选**：默认只读观测、显式一次可信 Objective 提交、准确原请求的持久 publication 历史查询，以及已有 Rust Session/Shell 投影。owner PR #2815 尚未合并，不能因为 desktop 客户端已在主干，就推定 Hepta 主干已经具备该历史查询接口。历史 `compiled` 是 publication，不是现在仍存在 run、执行已获准或设备效果完成；当前 `RunStatus: null` 也不等于从未受理。生产请求 owner、issuer 和 retained anchor 的持久责任不能交给普通 UI 自动补齐。

Asterinas 可继续承担该系统的内核 Organ 候选。G1-a 的实测说明已有真实 owner 上可以采用局部修改接入 metadata、revision 与生命周期；本轮没有发现迫使重写 kernel 的结构性反例。构建锁的真实失败与 Hepta 依赖安全债务都是具体工程问题，不能用它们推导“换新 Rust kernel 就会消失”。

**平台支持要分源码能力与本项目验收。**固定 [vendor README](../../../kernel/asterinas/README.md)将 x86-64 列为 Tier 1，ARM64、Intel TDX 和 RISC-V 64 列为 Tier 2，LoongArch 64 列为 Tier 3；[OSDK 架构实现](../../../kernel/asterinas/osdk/src/arch.rs)明确具有 `Arch::Aarch64`、`aarch64-unknown-none-softfloat` 与 aarch64 QEMU 入口，原字节身份见 [架构范围收据](source-publication/main-sync/asterinas-architecture-scope.json)。不能称为“Asterinas 没有 ARM64 内核支持”。本项目的 G1 仅验收 x86 QEMU，Hepta ARM Linux host 的历史通过也不授予 Asterinas ARM/手机、Binder、GPU、SoC、功耗或设备驱动资格。[本轮上游 API](source-publication/upstream-and-a04-current-api.json)仍将最新 release 记录为 2026-10-12 发布的 v0.19.0，项目固定 source pin 没有因查询而升级。

Asterinas 的 framekernel 将 unsafe Rust 收敛到 Framework/OSTD，OS services 使用 safe Rust；这降低内存安全 TCB 的审查范围，不能自动证明权限逻辑、预算计费、持久化或硬件隔离正确。Hepta 应沿已有 issuer/Objective/run/Operations 主链承担智能和工具编排，内核负责确定性的最终授权、资源状态、调度与恢复；普通 UI 和模型输出都不能替代资源 owner 的最终检查。若未来出现可复现结构性阻碍，可优先复用 OSTD 重建上层服务；不能因为仍有应用/CI/设备缺口就先抛弃已取得的内核能力。

| 次序 | 必须完成的实现 | 接受门禁 |
| --- | --- | --- |
| G1-a 发布收敛 | 已取得本地 4e、原基线 107 的普通产品与严格 source/实际 artifact 接受；保留全部失败和残留观察，新 e15+G1 组合已取得六项普通 CI、完整产物审查并同树合入71ce；后续从 G1-b 开始新的精确源验收。 | 旧 pins 保持可复跑，新候选独立绑定；严格 source gate 不放宽，四个未实现操作仍明确不可用。 |
| G1-b | 原 CPU owner 统一结算与 usage 读取、TSC/BOOTTIME 时钟域转换、N0 受限 profile。 | 真实调度的单 CPU / 100 ms 窗口预算与计费误差、quota 更新/退出/债务/边界交错。 |
| G1-c | trusted init 将资源身份和授权绑定到最终 Process / exec_epoch，区分观察、管理和历史授权。 | 进程/exec 换代、撤销、最终使用检查、错误 owner 和过期 authority 拒绝。 |
| G1-d | 完成五操作接合：revision/CAS、delivery 去重与重放、copyout 不确定结果、1024 保留窗口和 RetireThrough。 | 单对象锁序、IRQ/SMP、撤销/退役/重启边界，以及不依赖模型的本地客户端验收。 |
| G2 | 接真实 Hepta issuer、准确请求/anchor 持久保存、Operations K↔D、稳定资源身份与 CPU adapter。 | 原版 Hepta ELF 在明确 Linux ABI 上的受控执行；UDS/peer、epoll/futex、SQLite WAL/fsync/目录持久化、恢复与效果终态。 |
| 设备与 UI | 在上述闭合后逐 profile 接显示、输入、存储/网络和移动设备桥。 | 真实硬件权限/撤销、设备生命周期、CJK/IME/Wayland/GPU、Android 边界与用户可见终态。 |

继续受控 Asterinas fork 是当前默认路线。只有在固定 W0/W1 和目标 profile 上出现可复现、无法以局部修改修正的结构性问题，才重新评估内核替换。优先考虑保留可用 OSTD、替换上层模型；若内存、IRQ 或 scheduler 的实证限制要求替换 OSTD，新的 Rust kernel 必须满足同一套源码/构建、驱动与恢复、ABI 与授权门禁，并提供迁移路径。选 Rust、改 kernel 名称或让模型下发命令都不构成 AI native OS 资格。

## 8. 原始材料、解压位置与完整性

`hepta-security/` 完整保留原冻结包的 19 个 primary entry、两份 manifest、原 archive 和打包脚本，共 23 个文件，字节不改。其 `raw-evidence.tar.xz` 为 **2,752,828 字节**，SHA256 `8f46f3080bd9645a57ed44c8910c616b9035d4ddaf84e6cd6fb3d4bd7e1311ac`；有 128 个 archive members，包括 manifest 和 127 个证据文件。复制时独立核对了成员顺序、类型、大小、SHA 和 primary 与 archive 的逐字节相等，原输入前后不变。

原安全报告中的 `official-advisories/`、实际依赖树全文、Cargo metadata、action 原文与部分上游源码只在 raw archive 内；主目录的 primary 不是这些文件的完整副本。应将 archive 解压到一个新的审查目录，再从解压目录内的 README/报告开始阅读。**不能因为 primary 中不存在某个 raw 路径，就把一个指向归档内材料的说明当作已经可点击的本地文件链接。** 完整本地 cargo-deny log 以 `.xz` 无损压缩保留，原 13,717,460 字节和 SHA 的 roundtrip 证据在 preservation 收据中。

G1 的 `g1-evidence/` 以 [files-manifest.json](g1-evidence/files-manifest.json) 固定 **256 份材料、57,791,537 字节原文件**的每个相对路径、size 和 SHA；直接复制 49 份 primary，便于阅读关键收据与审查。完整确定性 tar.xz 为 **10,602,828 字节**，SHA256 `6a20eefe453be83e04ad74ac99e79206d20034025c30a743f9a95ce2e6b370fd`，有 **257 个 regular members**，包括 manifest 和全部 256 份材料。为避免发布接口的大 blob 限制，**Git 树只交付该 archive 的七个分片，读取完整材料前须恢复原 archive**，具体见 [publication-transport.json](publication-transport.json) 与下方步骤。原 files/artifact manifests 按完整恢复包保留，没有为省略本体而改写。原打包检查已核对源前后逐文件 size/SHA、所有 archive 成员和 primary equality，全部一致；没有重新执行产品。

该包完整保留环境、首轮失败、metadata 反证/正向复现、源码 handoff、两个实际 ktest guest 的串口和完整 ELF，以及普通产品三次 attempt、对应产物、残留取证、修订和独立审查。未执行的旧 review 草稿与仅用于宿主编译检查的临时二进制明确排除。完整 ELF、部分原始 source snapshot 和其他大体积材料只在 archive 内；解压到新的 `r10-evidence/` 目录，可恢复原 JSON 中相对材料路径的尾部结构。原收据里的绝对执行路径是历史来源，不能当作另一台机器上已存在的路径。

原 `g1-env/REPORT.md` 中的六个相对链接——`fixed-nightly.json`、`apt-install.json`、`qemu-paused.json`、`qemu-paused-qmp.log`、`tool-inspection.json`、`osdk-root-manifest-concurrent-product-diff.patch`——均只在 G1 raw archive 的 `g1-env/` 内。先由七片恢复 archive，再解压并从该目录的原 REPORT 打开；primary 目录本身没有这六份副本。它们各自的 size/SHA 已在 G1 manifest 中核对，原报告字节没有为“修好链接”而改写。

G1 原始 be6/12e Git 对象另外在 27,694 字节的 `source-candidates.bundle` 中保留，SHA256 `2aac07c0e2a813d7858bfc837a12ac9bb49e8a0b9506f08a1f3897d3105afd9c`。导入/验证它要求拥有 `aab50f347deb53fc79ac13ea3b84f846fefc70a7` 这个 prerequisite；该 bundle 不冒充完整仓库或最终发布 commit。普通本地源码另有 [ordinary-candidates.bundle](source/ordinary-candidates.bundle)，43,704 字节，SHA256 `d969edf78728bf69c24b4d6b1901c61c072102ac37b6f2e487aea98d66bde2cd`；prerequisite 是 0c，包含 be6→12e→8c→1cb→85b→4e 六个 commit，已通过 git bundle verify。它只读取冻结 Git 对象，不包含当前未追踪残留，也不包含另外创建的远端 f744 发布 commit；同树发布和后续 CI 修正各按自己的来源收据解释。

`hepta-bazel-followup/` 是独立追加的 15 文件原包（11 primary 与四个包级文件），archive 为 969,644 字节，SHA256 `d53aaa52bbf7a905ecfc83caa81a1a623bdfaccbed3fa3b7c2fa077588e96cdb`，47 个 regular members。其原日志 `.xz` 和 source-review 复制件在 archive 内，按自己的 manifest 解压阅读；复制时已核对全部成员与 primary，同样没有覆盖旧安全包。

`hepta-fleet-fixture-fix/` 完整复制后续最小修复的 20 份独立文件，共 990,483 字节，没有新增压缩或重打原包。[原 manifest](hepta-fleet-fixture-fix/files-manifest.json) 为 3,511 字节，SHA256 `c42b3bc1774bd150d15ea563ce8fc088dd47c23cf0b1919350d912fa495c4232`；[复制收据](review/hepta-fleet-fixture-copy.json)同时核对 manifest 本身、19 个列明材料、源前后字节及全部副本。单提交 patch、实际验证、原日志和工具校验都可直接阅读，没有纳入 target、工具二进制或缓存。

`hepta-fleet-fixture-main-fix/` 另完整复制 **25 个原文件、127,904 字节**；原 manifest SHA256 `679cc06b07a26e9783ac5fde2d711383fe356763c4d6e1dac73390053d4ba868`，逐文件 source 前后及副本一致，见[复制收据](review/hepta-fleet-fixture-main-fix-copy.json)。原 parent-1b 的 20 文件包保持不变。

`g1-ci-host-correction/` 保留 **15 个交付文件**，原 tar.xz **74,564 字节**、SHA256 `e5ba4f7543934283b7e649c48bef0f08de073aa311f9030ffa07ef12bb5f13e2`，106 个 regular members（105 份材料及原 manifest）。[独立复制与成员核验](review/g1-ci-host-correction-copy.json)涵盖全部成员和 primary equality；实际 stdout/stderr、失败、生成 manifest 和完整命令在原 archive 内，primary 中的相对原路径应在解压目录阅读。

最后两组 Hepta 原包保持独立：`hepta-fleet-main-remote-ci/` 完整复制 **9 个交付文件、523,110 字节**，raw manifest 列 **62 份原材料、4,556,486 字节**，含 manifest 的 archive 共 63 个 regular members。原 tar.xz **422,776 字节**、SHA256 `8ced940d49cbe4e89cf38e05cf7840679b123e92e40d9a1dc8e64020cd82b27c`；原 Fleet artifact ZIP **37,960 字节**、SHA256 `2d6965266359d5c7e1951b6f52cb5e0b0fa11b435e914c5506f73cad6ed17ad2` 也直接交付。`hepta-scoped-ci-storage-fix/` 完整复制 **13 个交付文件、92,003 字节**，raw manifest 列 **30 份材料、259,834 字节**，含 manifest 共 31 个 regular members；原 tar.xz **33,016 字节**、SHA256 `62dabfda36da09a3c8df59dafcd570959fe79b05142c87ca62c39e0edd8682b9`。

两包的[原冻结索引](review/hepta-fleet-scoped-producer-freeze.json)、[Fleet 逐文件复制收据](review/hepta-fleet-main-remote-ci-copy.json)与[配置候选复制收据](review/hepta-scoped-ci-storage-fix-copy.json)均保留；最终交付复核还逐成员重新检查顺序、size/SHA 和 primary equality。完整原 API、job log、编译参数与调用失败主要在各自 raw archive 内，先解压至各自新的目录，再按原 README/JSON 的原相对结构阅读。原 primary 中的历史绝对执行路径及 producer 包名不是当前读者机器上的现成路径。PR #2883 发布及04:17:21状态快照另存 `source-publication/hepta-scoped-disk/`；最后04:44–04:45快照按原18文件/2,682,840字节复制到 `hepta-final-status/`，见[原manifest](hepta-final-status/files-manifest.json)与[复制收据](review/hepta-final-status-copy.json)。没有回写先前冻结包。

首个 f744、中间 463f、原基线最终 107 的 CI 分别保留自己的 15、12、21 份原文件，原 A06 ZIP 分别为 **18,333,821 / 18,334,024 / 18,335,208 字节**，各有 76 成员。每份大 ZIP 各提供 12 片；原 producer manifest 原字节保留，完整 ZIP 本体不进入交付 Git tree。各目录 README 与 `archive-parts.json` 提供独立恢复命令，运输收据记录实际空目录恢复和所有成员 size/SHA/CRC 核验。463f 与 107 的 A03 小 ZIP 直接交付。不同 CI 的字节、检查范围和失败状态不互换。

最终 e15+G1 的 `g1-remote-ci-1c054/` 再保留 **20 个原文件、20,854,647 字节**，原 A06 ZIP **18,446,493 字节**、SHA256 `d9623e880bf559392f92c6bc9359a02629b6ff548e853e9f05cf1598b711fbbd`，同样以12片恢复76成员。四组 CI 一共48片，加原两份 tar.xz 的9片，现有 **57 个传输分片**；每份原archive、manifest、source与失败/接受状态各自固定。最终Git index/tree明确排除五个大原件本体（G1 tar与四个A06 ZIP），即使本地工具后续又观察到原件副本，也不把它们意外纳入交付。

新增源对象继续分开：[host 修正 bundle](source/ci-host-contract-candidates/receipt.json)为 2,902 字节、SHA256 `8aba49e7d2ed6f5061026b2cbca4022ee411aec0a4a8ce673cc4f62b3f1c7991`，要求 4e，含 bc/bcc 两提交；[main 集成 bundle](source/main-sync-candidate/receipt.json)为 1,410 字节、SHA256 `d4eacf3af0657dfa82a2f74f41e5ae07e7a9a8d1c1981a9a15749bee4a491e5f`，要求 bcc 与 e15，含单一 1ca merge。两者均实际通过 git bundle verify，只含冻结 Git 对象，没有当前未追踪文件，也不冒充完整仓库或远端 commit 对象。

### 分片与恢复

原两份 tar.xz archive 提供共九个传输分片：G1 七片、Hepta 安全包两片，每片最多 1,572,864 字节。分片只是连续切分原始 archive 字节，没有改成员或重新压缩。**G1 原 archive 本体不在交付 Git 树中，必须由七片恢复；Hepta 安全包的原 archive 本体仍直接交付，同时保留两片作为另一种恢复入口。** [archive-parts.json](archive-parts.json) 固定九片的顺序、大小、SHA 和两份完整 archive 的身份。[恢复脚本](review/restore-r10-archives.py)先检查各片，再检查拼合后的整体 SHA；已存在的目标必须精确匹配，不会覆盖不同文件。[原实际空目录恢复收据](review/archive-restoration-review.json)是在选择此发布布局之前取得，确认两份 archive 均可由分片完整恢复；[传输布局收据](publication-transport.json)另证明移出的 G1 本体保持原字节，内部 manifests 与七片均未改变。

选定该布局后又完成一次[实际恢复复核](review/published-transport-roundtrip.json)：交付目录中 G1 archive 本体在运行前后都不存在，恢复脚本只凭已交付的 manifest 和分片在新目录中创建两份 archive，整体 size/SHA 与保留的原件一致。此步骤验证文件交付方式，没有运行 Cargo、QEMU 或任何产品测试。

从仓库根目录检查全部分片及直接交付的安全包 archive；此命令只校验，不恢复缺省的 G1 本体：

```bash
python3 -I results/integration/2026-10-19-g1-owner/review/restore-r10-archives.py \
  --manifest results/integration/2026-10-19-g1-owner/archive-parts.json \
  --verify-only
```

要读取完整 G1 材料，把最后一项改为 `--output-root /tmp/r10-restored`，即可在该目录下恢复 `g1-evidence/raw-evidence.tar.xz` 和 `hepta-security/raw-evidence.tar.xz`。Bazel archive 小于分片阈值，直接读取原包即可。各 archive 应解压到自己的新目录；安全包和 Bazel 包内部的 README/报告用其原相对路径阅读，G1 中的 `g1-env/`、`g1-review/` 与各 attempt 目录也保持原尾部结构。

打包和复制收据见 [G1](review/g1-package-final-execution.json)、[Hepta 安全包](review/hepta-security-copy.json)、[Bazel 追加包](review/hepta-bazel-copy.json)。[打包脚本](review/package-r10-evidence.py)、[选定材料清单与排除说明](review/g1-package-final-config.json)、[分片脚本](review/split-r10-archives.py)与[分片执行收据](review/archive-parts-execution.json)随交付保存。重建 G1 archive 需要先按选定材料清单准备原结构；脚本不能凭 primary 自动补出只在 archive 内的原始材料。

包内不包含 Cargo/Rustup cache、target 目录、凭证、模型数据或新生产设备内容。具体排除项、选定材料、构建 archive 的脚本、源前后检查和最终成员验证随交付保存。旧 R9 47 份报告与 321 素材 archive 未重打包或覆盖。归档 SHA 证明材料身份和传输完整性；它不把失败改成成功，不将未执行项转为运行资格。

交付级 `delivery-manifest.json` 逐项绑定这次新增文件及 `docs/INDEX.md`、`docs/STATUS.md` 的最终字节；为避免递归摘要，它与记录其 SHA 的 `review/final-delivery-review.json` 由最后 Git 提交共同绑定。该复核另检查 R9 两个既有结果目录的 74 个文件仍匹配原 Git blob/mode、e15 合入时的完整 STATUS 历史 body 逐字保留、根 README 为 0 字节。`review/delivery-links.json` 区分当前可读文件、固定源码目标、须先解压的 archive 成员及未重查的外部链接，不把这些状态合写成“所有链接都已存在于当前主干”。

初次 stage 的通用 `git diff --cached --check` 还暴露了一个交付工具的范围错误：它将 30 份原始材料中的串口 CRLF、patch 空上下文行、Git 输出空格和既有报告 EOF 空行判作新文案格式错误。[原失败与逐路径保留依据](review/whitespace-preservation.json)及 [454,933 字节原诊断输出](review/staging-whitespace-unfiltered.stdout.log)均保留，初次清单另作历史快照。25 份材料由原 producer manifest 固定，5 份原 Git diff/bundle 输出由此前清单固定；加上这份原诊断输出共 31 个精确路径，按 size/SHA 验证后保持原字节。其他全部选定提交路径仍接受空白检查，所有文件继续接受 manifest、Git blob 和 mode 校验；没有忽略整个 results 目录、修剪原日志或修改产品测试门禁。

### 本次 main7e 交付整合的文本追加

此前固定交付 bc309 / tree477 的独立 QA、原 manifest、原终态复核和文档 delta 归档在 `review/pre-main-sync/`，由[复制收据](review/report-main-sync-fixed-inputs-copy.json)绑定；旧 QA 只证明旧树。本次[条目继承与升级清单](review/main-sync-entry-preservation.json)逐一对照原405个 manifest 条目，保留原始 producer 文件，单独列明随当前主干升级的顶层报告、索引和 helper。最终新 commit 还需独立 Git 字节审查；该外部终态收据随发布记录提供，不写入它自身正在审核的 Git 树。

报告外的产品、测试、工作流和主干既有证据均须与 main7e/tree354 精确相同，详见[完整源码边界证明](source-publication/report-main-sync/source-integration-review.json)。本次不增加二进制归档，原72个二进制和57分片保持原字节；新增 #198 原artifact身份与审查是文本收据，不把其整个ZIP复制进旧运输包。审计范围固定后，后续主干或 PR 状态变化由下一轮独立来源记录，不能回写这批原始证据。
