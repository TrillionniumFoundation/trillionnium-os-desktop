# Hepta #2885：Architecture 已闭环，原 UI 传输失败已取得时间线

观测截止 **2026-10-19 14:03:44 UTC**。本节只对应 Hepta PR #2885 候选 `89933fdc84ed1151f04609a1881ab24aaef119b4`；根代理已发布的候选源码、原浏览器和原六用例均未在本次取证中改变，也没有重跑 workflow。候选父提交为 `43a638d4e25ebc5a8b06babcd1c75c9acac53179`，tree 为 `25b2a7b559549fba0d22fa7d62d78c76c13cd5ce`。这是架构 fixture 修复与 UI 被动诊断的正式结果，尚不足以放行整个 PR。[候选提交](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/89933fdc84ed1151f04609a1881ab24aaef119b4)

## 1. 原 Architecture 门禁已正式通过

原 run `39253698625` 的三个 job 已全部结束，结果如下。[官方 run](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39253698625)

| 执行项 | Job ID | 正式结果 | 完成时间 UTC |
|---|---:|---|---|
| Architecture source-head | 118063553066 | success | 13:44:36 |
| Architecture base-merge | 118063553205 | success | 13:12:34 |
| Architecture required 汇总 | 118094370103 | success | 13:54:23 |

四行修复把 fixture 实际依赖的 `hepta_ci_module_paths.py` 复制进临时仓库。原先失败的 `test_shell_preserves_test_targets_and_strict_lint_arguments` 和 `test_shell_test_failure_has_no_lint_pass_receipt` 在两条 lane 的原始日志中均为 `ok`。原 `test_hepta_ci_exec*.py` 共 45 例：source 为 **45 pass、0 fail、0 error、0 skip，8.275s**；base 为 **45 pass、0 fail、0 error、0 skip，7.575s**。本地移除官方日志行首时间戳后提取的每份测试输出都是 7,126 字节，SHA-256 与该次 CI command receipt 完全相等：

- source：`2476c93661252100d2438014849f7cd8dff927e0d56909f995195b06aafece9c`
- base：`b9dffc1956d8ff27583071700472c9e29e57f0aff49d1c5d54aadfa4c787a244`

source 的原始记录明确 `native_execution_required=true`，其实际 native 命令均成功。base 的 Architecture 合成提交为 `04b6f3b75fc6e4e728a9f2a7393c19a2b6cc5740`，tree 与 source 相等；该 lane 明确 `native_execution_required=false`、`requires_source_head_success=true`。因此这里记录的是两次独立的 45 例 Python 执行，以及一次 source native 执行和一次有 source 成功条件的相同 tree 复用。31 份 source 命令收据及 4 份 base 命令收据已保存；各命令的测试集合可能重叠，不汇总成一个“唯一测试总数”。[完整 Architecture 结构化证据](./architecture-final-review.json)

本次修复依赖 PR 已引入的模块路径 helper，不能把这四行直接当成独立适用 main 的补丁。本地此前还记录过一个原 deadline 测试清理阶段的 `ProcessLookupError`，不把它归为本补丁已修复的问题。[本地 Architecture 记录](./architecture-local-review.json) `just fmt` 已真实尝试，环境缺少 `just`、退出 127；截止本次观测，原 Rust format CI 仍在队列中。[本地格式命令记录](./just-fmt-attempt.json)

## 2. 原 UI 六用例的正式结果

原 run `39253698771` 已取得两条 lane 的官方产物和正式 job 结果。[官方 run](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39253698771)

| 执行项 | Job ID | 正式结果 | 原六用例 |
|---|---:|---|---|
| Rust UI foundation / source-head | 118063553356 | failure | 5 pass；640 timeout 用例 timedOut；0 skipped、0 flaky |
| Rust UI foundation / base-merge | 118063553876 | success | 6 pass；0 skipped、0 flaky |
| Generate UI dependency lock for review | 118063554284 | success | 依赖锁审查 job，不计入上述用例 |

source 唯一失败步骤是原 `Exercise real gateway unavailable status and cancellation`。1280 的 timeout/navigation/background 和 640 的 navigation/background 均通过，640 timeout 在原 90,000ms 整例期限超时。`page.unrouteAll` 关闭异常出现在后续清理阶段。这里是原 Rust UI 与 source-built gateway 的真实运行；此前本地以合成 WASM 回调做的 12 个传输诊断另存，不能代替这批门禁。[原 source job](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39253698771/job/118063553356)；[原 base job](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39253698771/job/118063553876)

官方原始 ZIP 的大小、API digest 和本地实际 SHA-256 已全部核对，ZIP CRC 校验通过：

| Lane | Artifact ID | 官方产物名 | 字节数 |
|---|---:|---|---:|
| source | 12191530387 | product-gateway-source-head-89933fdc84ed1151f04609a1881ab24aaef119b4 | 2,117,670 |
| base | 12190760861 | product-gateway-base-merge-a1411851e988155fe3ca45c70e7fc31fdc09dd5c | 2,123,165 |

- source ZIP SHA-256：`e6dc4efc5dde4049e4f9084b9468e997e4bf4d6d30dcb247e1894eb12d5f3461`
- base ZIP SHA-256：`e41f6e581c991262fc1b71019b267631e09e1289cfc8d1d0b653b9c2cb6a4594`

两份 artifact 均绑定 run `39253698771` 和 head `89933f…`。UI base 测试提交为 `a1411851e988155fe3ca45c70e7fc31fdc09dd5c`，与 Architecture 的合成提交不同，但二者的 tree 都是 `25b2a7…`。两条 UI lane 各六个 case 所附完整 build manifest，合计 12 份，**逐字节相等**；实际重算的公共 manifest SHA-256 为 `026de9ca6037800af4df12c53aee250f700b4e20ead41fa8d68679b4324bf410`，UI source identity 为 `5b3ffd2bdcd76285cccd7602ab8a101f6034b4bfb7809fd8d6c5002fe6953efb`。[官方 artifact 元数据](./candidate-ui-artifacts-metadata.json)；[公共 manifest 原字节](./candidate-ui-shared-build-manifest.json)

manifest 记录的 SDK 为 87,890 字节，SHA-256 `b70442ed46ab0663323a1d7debd5676cc1dc281ec57d0be2a86f81b9eec078fc`；WASM 为 `7cd40149f2ecd787e24baefbd9892aa05add6351ab93cbe5789d4db05be306d5`。这些 executable digest 由 CI manifest 记录；ZIP 没有包含对应可执行文件，本次没有把它们声称为本地重算结果。原 source 全文 job 日志确认安装了 Playwright 1.63.0 对应的 Chromium / Headless Shell **153.0.8010.12、revision 1243**；单个 case 的审计记录没有独立 browser binary hash。[最终 UI 结构化证据](./candidate-ui-final-review.json)

## 3. 640 timeout 的精确事件关系

下表 `ms` 均来自同一个失败 case 的观察时钟。source runtime 请求是 CDP `21200.22`；预期被取消的 owner 请求是另一个 ID `21200.21`。

| 观察时间 ms | source runtime 的实际事件 |
|---:|---|
| 18149.770 | `requestWillBeSent`，GET `/api/hepta/runtime` |
| 18152.954 | `responseReceived`：503、HTTP/1.1、`Content-Length: 79`、`Cache-Control: no-store`，无内容编码，未命中磁盘缓存或 Service Worker |
| 18152.966 | `dataReceived`：`dataLength=79` |
| 18153.312 | SDK 的 `sdk-http-status-failure`，原控制台记录 503 runtime 响应 |
| 18153.487 | `Network.loadingFailed`：`net::ERR_ABORTED`、`canceled=true` |
| 18955.793 | 原 `timeout-runtime.finished` 等待开始 |
| 后续 | 没有 `finished` 完成标记，也没有进入 `held-owner.finish`；整例到原 90s 期限失败 |

**native failure 已在 `.finished()` 等待开始前 802.306ms 出现。** 该值用同一观察时钟相减，未跨 lane、跨机器或混用 CDP 内部 timestamp。90s 是整例期限，不代表这次 `.finished()` 调用本身持续了完整 90s。因而原生提前失败这一事实已经成立，不能把后来页面关闭的清理报错当成起因。[source 原始 request audit](./candidate-ui-source-640-timeout-raw-request-audit.json)

预期 owner 请求的 SDK abort 为 18149.560ms，owner 原生失败为 18149.806ms，ID 始终是 `21200.21`。runtime 的 `21200.22` 是额外失败。相同产品 tree 和 manifest 的 base 640 case 中，runtime `19525.22` 在 14933.035ms 收到相同 503/79/no-store 头，14933.404ms 收到 79 字节，14933.409ms 产生 `loadingFinished`；原 `.finished()` 在 15595.118ms 开始、15595.431ms 返回，随后 held-owner 完成流程通过。[base 原始 request audit](./candidate-ui-base-640-timeout-raw-request-audit.json)

六个 case 合计，source 有 20 个被观察的 API 请求、13 个原生完成、6 个场景要求的 owner 取消和 1 个额外 runtime 失败；base 有 20 个请求、14 个原生完成、6 个 owner 取消和 0 个 runtime 失败。所有 case 的诊断溢出计数均为 0，fault 数组均为空。失败 source 的 Timed Out OCR proof 已通过，但迟到 owner proof 和完整 cancellation receipt 没有执行完，因此该 case 的取消隔离验收仍失败。[最终 UI 结构化证据](./candidate-ui-final-review.json)

## 4. Chromium 归因是有依据的推断，下一步应修终态生命周期

上述提前 `ERR_ABORTED` 是原始产品产物中的事实。将它归因到 Chromium 的特定 C++ 缺陷仍是推断：目前没有该 case 的 C++ 调用栈，不能排他性确认唯一原生原因。

与事实相符的上游修复是 Chromium `62473ad0f747e245e514c93e741bb8e168a2a207`。该变更把 `HandleResult(result)` 提前到 `bytes_consumer_client_->OnStateChange()` 之前，先发布读取结果/终态再允许客户回调重入，并加入 `CancelAfterDone`、`CancelAfterError` 测试。这直接涉及自然 EOF 到达后，内部状态尚未变成完成就被重入取消的问题。[Chromium 原始提交及 diff](https://github.com/chromium/chromium/commit/62473ad0f747e245e514c93e741bb8e168a2a207)

固定 Makepad revision `337566c8b25d47f7e4fff6a202157b65bf183330` 的 HTTP reader 自然 EOF 路径没有无条件 `cancel` / `AbortController.abort`；有界读取、主动取消及超限/截断处理需要保留。因此没有证据支持通过猜测删除 SDK 取消操作来修复。Playwright 1.63.0 客户端的 request-failed 路径保存并发出失败，但不会像 request-finished 一样结算 response 的 finished promise，这解释了为何原生失败先发生，原等待仍可拖到整例期限。[固定 SDK 原始源码](https://github.com/kevinaboos/makepad/blob/337566c8b25d47f7e4fff6a202157b65bf183330/platform/src/os/web/web.js)；[Playwright 事件处理](https://github.com/microsoft/playwright/blob/v1.63.0/packages/playwright-core/src/client/browserContext.ts)；[Playwright Response.finished](https://github.com/microsoft/playwright/blob/v1.63.0/packages/playwright-core/src/client/network.ts)

具体下一步是评审一个独立候选：回移该终态状态机修复，或正式审定含该修复的浏览器基线，再让原 source/merge 六用例各自完成。原 153 失败产物保留为回归输入；先前 157 的独立诊断只能辅助定位。接受边界继续要求原 27 个断言、原 90s 整例期限、`no-store`、现有流式字节上限、真实中止与截断/超限失败、活动 owner 取消，以及 runtime 的原生完成。改 route 释放顺序、吞掉错误、跳用例或把 SDK/OCR 成功当作 native completion，均不能说明此缺陷已经修复。只要缺少正式产品成功证据，这一门禁继续保持失败。

## 5. 全局 CI 尚待终态，新增 cargo-deny 失败原因未取得

14:03:44 的 API 快照返回全部 **49 个当时已创建的 check runs**：21 success、6 skipped、1 neutral、2 failure、14 in_progress、5 queued。全局仍未收齐终态。两项实际失败分别是上述 UI source，以及 blocking run `39253698846` 中的 `cargo-deny / cargo-deny`，job `118078508737`；后者失败步骤为 `Run cargo-deny`。

cargo-deny 的两次官方全文日志读取均返回 `Transport closed`；小型 step 接口已确认失败步骤，check output 没有给出原因，独立 check 详情接口返回不受当前连接器支持，annotation 正文未取得。没有取得能定位其原因的小型产物，所以本节保持“实际失败、原因未取得”，不沿用旧头的原因，不增加忽略项，也未重跑。后续由全局 CI 收尾继续读取其真实日志。[blocking 原 job](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39253698846/job/118078508737)；[完整状态快照](./ci-observation-20261019T140344Z.json)；[读取限制原始记录](./cargo-deny-read-limit.json)

## 6. 无截图证据交付

可复制文件及逐文件字节数、SHA-256 见 `final-text-evidence-manifest.json`，包含本报告、两份最终 review JSON、原测试 JSON、两份原 request audit、公共 manifest、Architecture 两条原 45 例输出、官方 job 日志的无损 xz 压缩件和状态快照。原始 product-gateway ZIP 保留，清单单列其出处、大小和 digest；此次没有抽取或新增截图。早期报告、原失败 ZIP 与本地 12 个诊断结果仍保留其原始名称和内容。
