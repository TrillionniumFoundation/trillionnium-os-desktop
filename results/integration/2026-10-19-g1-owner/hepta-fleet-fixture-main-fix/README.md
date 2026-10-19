# 独立 main PR：Fleet fixture admission assertion

## 冻结候选

- Worktree：`/workspace/scratch/499c7902de8e/r10-fleet-fixture-main-fix`
- 分支：`fix/fleet-fixture-admission-assert-main`
- Commit：`e770156ba8b35c77829d189fc053dc5f9eb69f8b`
- Tree：`15a3b89f59052368e28ce5ed4943dc2ab638844b`
- 直接父提交：固定 main `f8c9419df6ddeb36ff8b522a50219981fb8d9345`（tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45`）

此提交只 cherry-pick `3749e151fd1a39c4b568afdb9e03028974ad86be` 的单一 fixture 修复。相对 main，唯一变更为 `codex-rs/hepta-fleet/src/authority_port.rs`，+16 / −14。main 上原文件 blob 精确为 `55e117dafe84709451a638bb8f6bafa41c38bd5a`；修复后字节与前一候选相同。`ledger()` 捕获 `admit_host` 结果，再用带 Debug 结果的 `assert!(admission.is_ok(), ...)` 检查。所有 HostObservation 值、测试数量、lint 策略、依赖和产品行为保持原样。

本分支没有包含 #2815 的 Objective History 产品变化或 CI 超时变更。`baseline-comparison.json` 逐项记录上一 d32 候选与本 main 候选之间全部 29 处 Git 输入差异及对象 ID；相应完整 diff 无损保存在 `comparison-with-d32-candidate.diff.xz`。该对比中的删除表示换回 main 基线，**不是本 PR 相对 main 删除了这些文件**。PR 实际差异只有 `source.diff` 内的一个 helper。

## 新基线上的实际执行

本轮重新读取 f8 的 AGENTS，未发现三个窄域 crate 下有额外 AGENTS。没有新造测试。以下命令全都在上述新固定提交上执行，源码前后 clean、commit/tree/绑定文件哈希一致。

| 命令 | UTC 时间，2026-10-19 | 实际结果 |
| --- | --- | --- |
| `just fmt --base f8c9419df6ddeb36ff8b522a50219981fb8d9345` | 03:13:07.752–03:13:07.906 | exit 0，没有产生源码变更 |
| `just test -p codex-hepta-fleet --lib --locked --offline --cargo-profile dev-small -j 1` | 03:13:12.477–03:13:21.446 | **41 passed、0 failed、0 skipped** |
| `just clippy -p codex-hepta-fleet --lib --locked --offline --profile dev-small -j 1 -- -D clippy::unwrap_used -D clippy::expect_used` | 03:13:54.134–03:14:03.337 | exit 0；recipe 的 `--tests` 覆盖 helper |

唯一调用 `ledger()` 的既有 Unix 测试 `allocation_issue_consumes_exact_live_kernel_authority_lease` 再次真实通过。原 nextest 日志中的 scoped metadata package-ID warnings 保留在日志和 final-validation.json；不宣称零警告。Clippy 未出现 warning/error 诊断。

复用已验证的 Rust/Cargo 1.95.0、Clippy 0.1.95、rustfmt 1.9.0-stable、cargo-nextest 0.9.148、just 1.51.0，以及 Fleet 专用 isolated target 和 offline cache。没有修改 G1 工具或原工具链，没有全库构建；这不是冷缓存构建。Cargo 本轮日志显示从新 main worktree 检查/编译相关 crate。各 receipt 给出完整 argv、cwd、环境和 source 前后身份。`baseline-comparison.json` 另给出窄域 crate、配置、锁、runner 的输入清单；其中记录的输入与前一候选逐字节相同，但测试结果来自本轮新执行。

## 失败保留与交付边界

首次创建 worktree 时，partial clone 缺少 blob，在默认 sandbox 下连接代理失败，exit 128；其工具输出原文及时间精度边界保存在 `checkout-01.*`。随后使用已授权网络补取 Git 对象，checkout 与 cherry-pick 均 exit 0。没有通过改门禁处理此 setup 错误。

验证范围为 Linux x86_64 的 Cargo 窄域测试和 Clippy。没有运行 Bazel、macOS、ARM64 或 Windows；旧 CI 的 Windows sandbox 删除边界失败和 cargo-deny 安全债务均未被本补丁解决。原 d32 候选的 20 份材料逐字节复核通过且保持原样，本轮结果单独保存。没有远端发布、改 #2815、重新运行 CI 或合并。

`fixture-admission-assert-main.patch` 可用于发布这个单提交修复；`files-manifest.json` 绑定目录内所有交付文件，排除自身递归摘要、源码 checkout、工具安装、缓存和 target。
