# Fleet 独立修复远端 CI 核对及 ENOSPC 诊断

最终只读观察为 2026-10-19 04:09:45–46 UTC，具体请求起止时间保留在 `20261019T040945Z` 的原始 API 记录中。这里的源码和运行来自 GitHub，完整失败日志及 artifact 均单独保留，没有用本机结果替代远端 CI。

| 对象 | 固定源码 | 实际门禁状态 |
| --- | --- | --- |
| Fleet PR #2882 | `b34cb44f06db0a66acb3d25b183a2a05c4cebc7e` | Ready/open/blocked；Architecture required success，CI required failure；未合并 |
| Objective history PR #2815 | `d32e795f0d24df89fc57745f6fae70fbd0642eba` | Ready/open/blocked；Architecture required success，CI required failure；原普通 squash auto-merge 保留，未合并 |
| main | `f8c9419df6ddeb36ff8b522a50219981fb8d9345` | branch 响应 `protected=true`，required contexts 为 CI required、Architecture required |

独立完整 `/branches/main/protection` 端点返回 403（integration 无该访问权限）；不能用这个 403 否定成功 branch 响应，也不据此推断保护设置变化。`prospective_merge_sha` 是 PR API 的候选合并值，不是发生合并的证据。

## Fleet 实际失败

`Hepta scoped native checks` job `117877231475` 属于 run `39195438433`，03:36:31 开始，03:52:59 failure。第 8 步的实际命令从 03:37:13 运行到 03:52:54；后续证据上传成功。`CI required` job `117881115008` 在 03:53:12 failure，原日志明确拒绝 `hepta-scoped: failure`。

03:52:53.233 原编译日志明确：`rustc-LLVM ERROR: IO failure on output stream: No space left on device`。03:52:54.805 runner 自己的诊断文件写入也发生 ENOSPC。该故障发生在编译阶段，不是 40 分钟作业超时，也没有证据把它归因于新的 Fleet helper 源码。

原 artifact `12162530412`，名称 `hepta-cargo-impact-39195438433-1`，37,960 字节，SHA-256 `2d6965266359d5c7e1951b6f52cb5e0b0fa11b435e914c5506f73cad6ed17ad2`。下载 ZIP 与 GitHub digest 完全匹配，3 个成员逐字保留：

- `cargo-impact.json`：完整原始 134 包选择，base f8，tested/source b34。
- `impact-test.json`：`status=running`、`command_exit_code=null`，执行器没有写成成功或终态收据。
- 原生完整 command log：app-server/core 的 test `all` 编译遇到 ENOSPC，保留实际 Rust 参数和失败尾部。

执行收据仍 running 与 GitHub job 已 failure 是两层不同观测，不能自行补写一个进程 exit code，也不能将上传成功解释为测试成功。没有取得完整测试集成功的证据。

## 范围关系

原 scope 选择日志明确仅修改 `codex-rs/hepta-fleet/src/authority_port.rs`，`native=true/lifecycle=true/full_repo=false`。Cargo impact planner 保守纳入 build-script 输入和反向消费者，实际选择 134 个包；静态同树重算与原 artifact 除提交 ID 外全部相同。静态重算仅访问 Git，不是第二次 CI 执行。

这条固定 scoped 工作流仅通过 `--run` 调用原 `just test --locked`；它没有运行 Clippy。Bazel、rust-ci、cargo-deny 按原策略 skipped，不能写成这些门禁或原 macOS/Ubuntu Bazel helper Clippy 通过。本机 Fleet 严格 Clippy 与 41 项原测试的证据保持单列。

Fleet source-head Architecture job `117877090301` 在 04:00:56 success，Architecture required `117882974089` 在 04:01:02 success。最终 Fleet 24 个 checks：12 success、2 failure、8 skipped、1 neutral、1 in_progress（Rust CodeQL）。

#2815 d32 的 49 个检查已全部终态：26 success、8 failure、6 skipped、9 cancelled。它的 CI required 原日志拒绝 `bazel: failure, cargo-deny: failure, sdk: cancelled`；其安全债务、Bazel/Windows 诊断属于之前独立材料，不能套用到本次 Fleet ENOSPC，也没有因 Fleet helper 修复而自动消失。

## 磁盘配置证据及候选边界

失败时原 Cargo 使用 workspace 的 `target/debug`，rustc 带有 `-C debuginfo=1` 和 `-C incremental=.../target/debug/incremental`。固定 scoped workflow 未配置 Cargo target/cache 覆盖、无编译缓存恢复或磁盘清理步骤。V8 archive/binding 是当前实际构建依赖，不能当作未使用缓存随意删除。

原日志没有 df/du 或 SDK 占用采样；唯一明确的空间时间点是编译器和 runner 写入 ENOSPC，另有 apt 的 3080 kB 安装计划估算。不能据常见 GitHub runner 配置推定实际总盘、起始余量或某 SDK 可回收字节。

后续独立 main 候选 `71d9db8fd48a317fe5930392799522f186188d6a` 仅采用已维护原生 workflow 的四项 Cargo 环境设置。其验证在独立 `hepta-scoped-disk-fix` 包，未修改本批失败原件。该候选没有重跑这里的 134 包作业，也没有远端成功收据。

所有本批操作均只读；没有 rerun、cancel、dispatch、修改 PR/权限/策略或执行合并。归档排除 transient download URL、所有 target/cache/checkout 凭据和二进制，只保留公开源码绑定、API、日志和原始 CI artifact。
