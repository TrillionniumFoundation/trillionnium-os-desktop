# Exact-f092 CI：真实失败与排队快照

本目录单独保存桌面候选 `f0924a6e48c68101ec09b01ef2f69aec330a3da7`（tree `651ff86f8814218bab71b19a550a1d84aa3a1d41`）的实际结果。它与本地冻结 `9d2ef72a4183460b1b4f1cdad97c1c013fa9d8dd` 整棵 Git tree 相同；逐文件输入哈希见 [source-binding.json](source-binding.json)。既有 exact-c0 成功记录属于另一来源，保持在独立目录。

| 工作流 | 本次可核实结果 | 限制 |
| --- | --- | --- |
| [ARM 39073273434](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39073273434) | 2026-10-17 22:20:01 UTC 最终 failure。实际 Session/ctl、observer、固定原版 Agentd 编译成功；外部 probe 的初次 metadata 成功，随后的 locked build 退出101。 | 在 rustc 编译新增 probe 和任何运行期验收之前失败。原版 Agentd、persistent Session 的运行验收均 `not_run`，五 ELF 包装与上传跳过。 |
| [A10 39073273425](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39073273425) | 本归档查询时仍 queued。source guard 22:18:36–22:18:52 UTC 成功；native job 无任何已开始的 steps。 | 此快照不声称 Rust 测试、Weston 或原版 Hepta UI 执行成功；排队状态可能在后续发生变化。 |

## 失败原因与证据

[真实 probe 构建日志](arm/probe-build.log)显示 Cargo 拒绝在 `--locked` 下更新生成的锁文件。完整 [report.json](arm/report.json)明确记录 `runtime_probe_attempted: false`。保留的失败 ZIP 为478,603字节，SHA256 `2be1fb4be12200caca4a63c2def42fb5e5e682bc1492fb9525f53e25c6b6f1c2`；28个原始成员含日志、生成 manifest/lock、真实源文件和结束时的干净 checkout 身份。ZIP经下载并验证摘要；本归档没有可执行文件，也没有执行其中的源文件。

[跨运行锁比较](probe-lock-comparison.json)证明本次失败锁与此前成功 ARM运行39044366482的锁完全同字节：SHA256 `9d1de5fab85aa6400a1d178e1791b3b01453b1b2b37e2b986bbe97cad55ceec1`，733个package条目及其依赖没有差异。生成manifest也仅有临时根路径差别。不能把这次失败归因为已经观察到的Rust源码编译错误或原版运行期回归。

后续独立本地诊断在新的诊断目录中复现了重复unused tungstenite项的顺序漂移；该诊断及修复后的新来源有独立收据，不回写本次失败。Cargo1.95的实现将unused patches按现有顺序序列化，并在locked比较中保留顺序：见官方 [encode.rs](https://github.com/rust-lang/cargo/blob/rust-1.95.0/src/cargo/core/resolver/encode.rs)、[resolve.rs](https://github.com/rust-lang/cargo/blob/rust-1.95.0/src/cargo/core/resolver/resolve.rs)和[lockfile.rs](https://github.com/rust-lang/cargo/blob/rust-1.95.0/src/cargo/ops/lockfile.rs)。任何修复仍须保持原版f8c源码、锁与pin不变，并保留最终locked验证。

## 归档校验

`api/`保存原样API JSON；`logs/`保存工具解码后UTF-8原始文本的确定性gzip，保留BOM和最终换行。这些gzip不是GitHub最初压缩格式的复制。压缩及解码后摘要见 [raw-artifacts.json](raw-artifacts.json)。`SHA256SUMS`校验目录内其余所有文件。

本目录不证明objective提交、模型调用、设备效果、移动端验收、真实显示器输入或发布就绪。
