# R9：最终提交的远端 CI 接续证据

这份接续保留最终 desktop 提交 `46dcb2d691827f7aa3ad7903dae09d39fd338126` 的实际 CI 产物。原本机 x86_64 的 native 构建、15 场景 history 运行、模块文档审计与 321 份原始材料继续固定在 [原验收报告](../2026-10-18-objective-history/README.md)，该目录及其归档没有修改。

## 最终提交的客户端 transport 检查

| 项目 | 实际证据 |
| --- | --- |
| 源码 | `46dcb2d691827f7aa3ad7903dae09d39fd338126`；tree `8d5de807c41090e3d987764daec9c235ebd022a1` |
| 作业 | [history-transport，117639353718](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092/job/117639353718)，attempt 1，Ubuntu 24.04 x86_64 |
| 实际检查区间 | 2026-10-18 10:47:53.101930–10:48:38.944438 UTC；整个 job 于 10:48:42 UTC 成功结束 |
| 工具链 | Rust / Cargo 1.88.0；原有 desktop Cargo.lock |
| Rust 结果 | 51 passed / 0 failed / 0 ignored：49 项可执行测试、2 项预期编译失败的文档测试 |
| Python 合同结果 | 22 passed：18 项 synthetic receipt contracts、4 项 source contracts |
| 其他检查 | 严格 all-target Clippy、default-off check、fmt 均 exit 0 |
| 来源不变 | checks.before == checks.after == identity/before；29 个源码摘要均与固定 commit 的 Git blob 匹配；最终 checkout 干净 |
| 上传归档 | artifact `12134590062`；8,945 bytes；9 个条目；SHA-256 `d3585d52ffd97d0e2ad88575fc1aeb38675b500331e1ee16fa9ca97e146c29d3` |

此次 51 项与本机早先 `c0808961…` 的 51 项分别记录。现在有了最终发布 head 的实际远端结果；不能将两次运行相加描述成 102 个不同测试。22 项 Python 检查使用 synthetic 数据验证收据与来源判据，不属于另一轮真实原 owner 运行。

已下载的 ZIP 与 GitHub artifact 元数据摘要相符。独立审查核对全部 9 条目的目录结构、CRC、长度和 SHA，逐个比较全部 29 个源码 Git blob，确认五个固定命令及其原始日志、最终 checkout 身份，以及保存的 jobs API 中全部 9 个步骤的成功状态。审查没有重跑测试或执行归档中的命令。

### 文件与复核入口

- [transport-evidence.zip](transport-evidence.zip)：实际下载的原始 CI ZIP，含日志、源码身份与执行收据。
- [transport-checks.json](transport-checks.json)：从 ZIP 原样提取的 checks.json，SHA `9c50b9fe45c173f8fafe1f7545aaa2008e6e6cc24bc7e26f6d9a46da4a75de87`。
- [transport-artifact-review.json](transport-artifact-review.json)：独立复核、逐文件摘要与原始日志分母，SHA `3081ef4ff3efde7407ba3f8296eb3384efec12cb33fea4847896079cdef76983`。
- [transport-artifact-github-metadata.json](transport-artifact-github-metadata.json)：原 artifact ID、大小、远端 digest 与下载身份。
- [artifact-manifest.json](artifact-manifest.json)：本目录文件摘要，自身由 Git commit 绑定而不自引用。

## ARM64 原 owner 实际运行

[original-owner-history job 117655596136](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092/job/117655596136) 已于 **2026-10-18 11:28:46 UTC completed/success**，attempt 1，14 个步骤全部成功。desktop 固定为 `46dcb2d691827f7aa3ad7903dae09d39fd338126` / tree `8d5de807c41090e3d987764daec9c235ebd022a1`，原 Hepta owner 独立扩展为 `2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5` / tree `f4ef891d43baf90d6eebd29921a5ed03222ef3ab`。本节记录的是该固定版本在 ARM64 Linux 上的原始构建与运行。

| 项目 | 实際结果 |
| --- | --- |
| job / runner | 11:05:32–11:28:46 UTC，ARM64 runner `1000165073` |
| 原 Agentd | Rust 1.95.0，`--locked --profile dev-small --no-default-features -j1`，11:06:03.940376–11:23:06.822717 UTC，exit 0 |
| 三个真实 CLI | Rust 1.88.0，`objective-history --bins -j1`，11:23:06.823293–11:23:24.094478 UTC，exit 0 |
| probe 构建与运行 | job step 11:23:24–11:28:16 UTC，包含 metadata、实际编译与运行，不是纯运行时长 |
| 原始事件 | 38 条：4 owner 启动、4 个 SubmitCLI 观测、13 次 history 查询、15 项检查、1 次 harness 丢回复、1 份 acceptance |
| 请求与恢复 | 5 个不同 Objective 请求、4 条 publication、3 次受控重启、恢复重投 0 次；其中 4 次由真实 SubmitCLI 发出、1 次由原协议 harness 发出 |
| 查询 | 13 次中 8 次 historical publication、5 次 unknown；原请求历史可与当前 `RunStatus: null` 并存 |
| 真实过期 | 等待 24,360 ms；原期限 11:28:13.326 UTC，实际查询观察时钟 11:28:13.335 UTC，已超过 9 ms；peer UID 1001 |
| 来源与锁 | 35 个 desktop 文件、36 个 owner 文件、8 个 probe 输入逐个匹配固定 Git blob；735 个共享依赖身份通过验证，两份 metadata 的 736 包记录相同 |

原始 report 与 history-gate.log 字节相同；runtime.log 的 38 条 JSON 与 report 逐条相同。独立复核验证五份原请求的 Ed25519 签名有效、改签名负例无效，并解码四个 journal frame，核对长度互补、checksum、publication digest、chain digest、原认证字段及 deny-all authority flags。这里的 15 项具名判据与本机验收相同，两个平台各保留自己实际运行的输入、进程身份、时间和 ELF，不能相加成为 30 个不同场景。

compiled / explicit_abstain、覆盖 anchor、harness 丢回复、发布后 SubmitCLI unknown、错误或过早 anchor、修改签名、进程重启后的投影缺失、实际过期、撤销后历史查询、新提交被拒绝，以及受控停机后的 journal 回滚与截断，均按各自判据通过。回滚恢复为首个 4,203-byte 完整前缀；16,588-byte 截断文件恢复为前三条 12,410-byte 完整前缀，原第 4 条 retained anchor 均返回 `unknown / anchor_missing`。

第 4 条 compiled publication 与通用 `submit_unknown / objective_owner_request_rejected`、当前 `RunStatus: null` 同时成立。具体 CapacityExceeded 只作为固定源码路径支持的推论，没有声称捕获该原始错误字节。丢回复由原协议 harness 实现，未执行真实 SubmitCLI 丢回复故障；存储故障在确认 owner 停止后注入，不增加写入中途 crash 或断电资格。model turn、Operations dispatch、新 K/D、设备效果、历史 run 恢复和生产 issuer 均未执行；共同回滚 caller anchor、效果核对和内核 G1/G2 保留为未执行项。

### 原始归档与五个实际 ELF

[arm-history-evidence.zip](arm-history-evidence.zip) 是实际 GitHub artifact `12134664375` 的原始 ZIP：**852,554 bytes / 99 条目**，SHA-256 `2717d25e42c9a1329e07bce92459db89a3109f72313ebac3e6010ddc8f1accd4`。所有条目的安全路径、CRC、大小和 SHA 均通过独立复核。

五 ELF artifact `12135470347` 的原始 ZIP 亦已恢复并核验：**90,606,774 bytes**，SHA-256 `1a145400d57620ecbcdcf533134ce4f2c45a47d58c5e95735c4192adb993bb63`。root 独立流式读取全部 4 个外层成员与 8 个内层成员，核验下表的每一个字节；均为 ELF64 little-endian、`e_machine=183`（AArch64）。内层 report / manifest / SHA256SUMS 与运行证据及外层文件完全一致，gzip footer、ZIP CRC 和内层压缩归档 SHA 均通过；没有展开或执行这些二进制。

| 实际 ELF | 字节数 | SHA-256 |
| --- | ---: | --- |
| codex-hepta-agentd | 268,457,128 | `622687b607c4f8aa983f082e169b06f2b7a89b12917e16384245965b156c7549` |
| hepta-objective-history-probe | 29,411,712 | `22c3b394861c847b551a476bd1924b682363a07097cae9946036f336cefdd665` |
| hepta-observe | 14,911,296 | `4da1165dd5bd925dff732edace85b4c2289faf735d640310ff8b1bd408a22f92` |
| hepta-submit | 14,664,856 | `c8e1df3fbc707c368133a2751bb1877b5ce96bd9c24c4322ab8cbc533ccdf5e3` |
| hepta-history | 15,021,288 | `671abf2c3e73032a7b89c262f8fdea5e00d2251423e52697c5deca47e773c88f` |

合计 **342,466,280 bytes**。约 90.6 MB 的完整 ELF ZIP 没有纳入 Git 证据目录；其原字节下载与上述实际复核分别留有收据。GitHub 元数据给出的到期时间为 `2026-11-01T11:28:38Z`，这里不保证此后仍可下载完整二进制，也不把 manifest 当作 ELF 本体。完整 852,554-byte 原始运行 ZIP 已纳入本目录。

### 2026-10-19 恢复与复核来源

跨日接续时临时工作环境被重置。已发布的代码、原本机 321 项材料分卷、transport ZIP 和审查均从固定 Git 提交恢复；尚未发布的 ARM ZIP 从同一个有效 Actions artifact 下载，逐字节摘要与原观察相符。**新日期的 API 观察和数据复核使用新时间、新 SHA；没有把它们伪装成旧收据，也没有重跑 Rust 构建或 runtime。**

此前 144,684-byte 的独立运行审查完整文件未能恢复；其旧 SHA 只在新收据中作历史引用。两份实际复核脚本仍完整保留，已原样恢复，执行副本仅适配新 API 快照及输出位置。新的独立审查重验原 ZIP / 源码 / 锁 / 签名 / 日志 / journal，结果为 `passed_rebuilt_review_of_original_arm_history_artifact`、`blocking_findings=[]`。root 也重新读取恢复后的完整 ELF 字节，形成独立新收据。该数据恢复不增加新的运行资格。

- [arm-history-runtime.json](arm-history-runtime.json)、[arm-builds.json](arm-builds.json)、[arm-final-checkouts.json](arm-final-checkouts.json)、[arm-allocation.json](arm-allocation.json)：从原始 ZIP 原样提取的阅读副本。
- [原运行产物的新独立审查](arm-history-artifact-review-rebuilt-20261019.json)：146,541 bytes，SHA `b158afd612e0828610b15278fb9c0b93386b6147f0e03ce151bc4ed12a3d029f`。
- [五 ELF 新字节审查](arm-elf-artifact-review-20261019.json) 与 [原 manifest](arm-binary-manifest.json)：实际二进制与原 report / build receipt 绑定。
- [运行证据恢复下载](arm-history-recovery-acquisition-20261019.json)、[ELF 恢复下载](arm-elf-recovery-acquisition-20261019.json)、[新 API 元数据](arm-history-recovery-github-metadata-20261019.json)、[原 ARM job 完整步骤](arm-history-recovery-jobs-20261019.json)。
- [恢复的原源码审查脚本](review/recovered-review-arm-source-original.py)、[恢复的原运行审查脚本](review/recovered-review-arm-runtime-original.py)、[源码审查执行副本](review/review-arm-source-recovery-20261019.py)、[运行审查执行副本](review/review-arm-runtime-recovery-20261019.py)、[新收据组装程序](review/assemble-arm-history-recovery-review-20261019.py)、[新 ELF 复核程序](review/review-arm-elf-20261019.py)。这些程序保存本次使用的具体输入路径和复核方法。

## 合并与其他门禁

2026-10-19 00:53:44 UTC 的 [精确 PR/checks 观察](resume-gates-observation-20261019.json) 确认 desktop `46dc…` 七项 checks 全 success，包括 `native-rust-and-wayland`。其后 [#193](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/193) 已普通合入主干 **`aab50f347deb53fc79ac13ea3b84f846fefc70a7`**；[合并回执](desktop193-ordinary-merge-20261019.json) 记录实际 tree 与两个 parent。该 merge 同时保留主干此前独立合入的 [#195 CPU parser 修复](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/195)。原运行与测试仍绑定各自执行源码，不重标为 merge commit 的全套复跑。

Hepta source-head Architecture 的 26 success / 4 skipped、native 步骤 17–23 success，以及 `Architecture required` 的 success，见 [完整 jobs/steps 观察](owner-architecture-terminal-observation-20261019.json)。该文件含实际步骤数据，已补齐先前草稿只保存去重指针而无法独立支撑步骤计数的引用缺口。base-merge 的同树复用及 skip 不算新执行。

同一 Hepta `2be…` 的原 blocking run 中，scoped native 被 cancelled，`CI required` failure；合同、Blob policy、Architecture 和 CodeQL 已通过。此快照不宣称 Hepta PR 已合并。后续需要修复已经定位的执行预算冲突，并完成原仓库的正常 CI；修复与新执行分别记录，不能把这批 ARM history 成功用来替代剩余聚合门禁。

## 资格范围

该 transport job 验证客户端、受控 socket / CLI 与合同。它没有执行真实原 Agentd 的 15 个 history 场景，不能授予 ARM64 原 owner 运行、生产 issuer、Operations K↔D、设备效果或 Asterinas G1/G2 资格。

上节独立 ARM64 history job 已取得隔离测试 issuer 下的原 owner Objective history 资格；该平台不是 Asterinas 客体或移动设备。Hepta 的聚合 CI、Operations 最终效果、生产签发与原请求/anchor 保存、Session/Shell 新投影及 G1/G2 各有自己的后续实现与判定范围。

实现与开发入口见 [OBJECTIVE_HISTORY.md](../../../services/hepta-os/OBJECTIVE_HISTORY.md) 和 [OBJECTIVE_HISTORY_PROBE.md](../../../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)。
