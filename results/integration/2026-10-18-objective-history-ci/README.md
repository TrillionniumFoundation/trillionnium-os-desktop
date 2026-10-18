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

## 资格范围

该 transport job 验证客户端、受控 socket / CLI 与合同。它没有执行真实原 Agentd 的 15 个 history 场景，不能授予 ARM64 原 owner 运行、生产 issuer、Operations K↔D、设备效果或 Asterinas G1/G2 资格。

新的原版 ARM64 history 验收由 [独立 original-owner-history job](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39115155092/job/117655596136) 完成。只有其原 owner 构建、实际 probe 运行、来源和五 ELF 绑定的完整成功收据，才能补充该平台结果。Hepta 的 `Architecture required` / `CI required` 与 desktop 的原生 UI 检查也各有自己的判定范围。PR 的 Ready 或 auto-merge 配置只表示合并准备状态；实际合并须有 merged 状态和精确 commit。

实现与开发入口见 [OBJECTIVE_HISTORY.md](../../../services/hepta-os/OBJECTIVE_HISTORY.md) 和 [OBJECTIVE_HISTORY_PROBE.md](../../../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md)。
