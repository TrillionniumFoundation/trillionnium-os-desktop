# Fleet admission fixture 最小 lint 修复

## 结果与提交

独立提交 `3749e151fd1a39c4b568afdb9e03028974ad86be`，tree `eb9dc083dfb6f4f57a98f0380683444aba98326a`，分支 `fix/fleet-fixture-admission-assert`。父提交为本地 `1b0fedb8c2b510106848f6feaf530c9b3698399d`，该父树与远端 owner `d32e795f0d24df89fc57745f6fae70fbd0642eba` 完全相同。仓库位于 `/workspace/scratch/499c7902de8e/r10-fleet-fixture-fix`，冻结后 clean。

单一变化位于 `codex-rs/hepta-fleet/src/authority_port.rs` 的测试辅助函数 `ledger()`：保存 `admit_host` 的返回值，用 `assert!(admission.is_ok(), "valid host fixture must be admitted: {admission:?}")` 确认准入。所有 HostObservation 输入保持原值。失败仍使测试失败，且诊断包含返回结果；未增加 `allow`、未替换为同样被禁的 `expect`，未改变产品行为、策略、依赖或测试数量。格式化使该单文件差异为 +16 / −14。

## 已执行验证

| 验证 | UTC 时间（2026-10-19） | 结果与范围 |
| --- | --- | --- |
| `just fmt --base 1b0fedb8c2b510106848f6feaf530c9b3698399d` | 02:41:48.808–02:41:48.994 | exit 0；只格式化变更文件，随后提交冻结 |
| `just test -p codex-hepta-fleet --lib --locked --offline --cargo-profile dev-small -j 1` | 02:42:24.948–02:43:03.626 | exit 0；41 passed，0 failed，0 skipped；冻结源码前后一致 |
| `just clippy -p codex-hepta-fleet --lib --locked --offline --profile dev-small -j 1 -- -D clippy::unwrap_used -D clippy::expect_used` | 02:45:18.392–02:45:38.594 | exit 0；recipe 包含 `--tests`，检查实际辅助函数；冻结源码前后一致 |
| `git diff --check` | 见 final-validation.json | exit 0；单文件差异 |

调用范围已读回：`ledger()` 仅由现有 Unix 测试 `allocation_issue_consumes_exact_live_kernel_authority_lease` 调用，该测试真实通过。没有新造测试或重新实现 ledger。现有仓库 `just test` 调用其 nextest 包装器；原日志保留了 scoped metadata 的 13 条 package-ID warning，不能将本次结果描述为“零警告”。严格 Clippy 本次未出现 warning/error 诊断。

工具为 Rust/Cargo 1.95.0、Clippy 0.1.95、rustfmt 1.9.0-stable、cargo-nextest 0.9.148、just 1.51.0。缺少的 formatter/Clippy/nextest 使用官方预编译发行物，下载 URL、官方校验、安装后二进制 SHA 和版本保存在 `tools-installation.json`。未声称 nextest 与旧 CI 的动态安装版本相同。Cargo 使用独立 target、独立 Cargo home、offline/locked、jobs 1、禁用 incremental；仅复用先前取得的 registry/git 字节，不改 G1 工具目录或原 Rust 工具链。

## 为什么独立发布

原 helper 的 Git blob 在 f8 基线、Objective History 产品头 2be 和 CI 修复后 d32 等价树上都为 `55e117dafe84709451a638bb8f6bafa41c38bd5a`。Ubuntu 与 macOS ARM 的既有真实 Clippy 日志均定位到此处；它是已有 fixture 的 lint 不符合项，不应混入 Objective History 产品 API 的语义变更或依赖迁移。可将本单一提交/patch 独立 cherry-pick 到适当分支；本轮未发布远端分支、PR、merge 或 rerun。

本次验证仅为 Linux x86_64 的 Cargo 窄域测试和 Clippy。没有重放 Bazel、macOS、ARM64 或 Windows。原 Windows sandbox 删除边界失败、其他 Windows 构建/测试失败以及 13 条 cargo-deny 安全债务都保持未解决；此补丁不能被记为全仓 CI 通过或 Windows 设备控制隔离已验收。

## 证据使用

`fixture-admission-assert.patch` 为可审阅的单提交 patch；`source.diff` 为父提交到冻结提交的精确差异。每条实际命令的 argv、工作目录、环境、UTC、退出码、源码前后身份及原日志哈希在各子目录 receipt 中。`final-validation.json` 绑定最终提交、修改文件、未变的锁和策略，并只读复核两个已冻结诊断包的所有交付字节。`files-manifest.json` 是当前目录逐文件 size/SHA 清单，排除自身递归摘要，不含工具安装、构建产物或大缓存。两个旧诊断包没有被修改。
