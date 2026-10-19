# Hepta scoped 原生 CI 磁盘配置候选

候选提交：`71d9db8fd48a317fe5930392799522f186188d6a`，树：`4688d8dfc139f990b3d770c8c081050a5ace1d26`，直接父提交为 main `f8c9419df6ddeb36ff8b522a50219981fb8d9345`。

独立工作树为 `/workspace/scratch/499c7902de8e/r10-hepta-scoped-disk-fix`。产品与测试源码未修改。发布载荷是 `publication/blocking-ci.yml`，只有 `.github/workflows/blocking-ci.yml` 新增的 5 行；`change.patch` 保留精确补丁。`PR_DESCRIPTION.md` 是可直接审查的独立 PR 说明。

## 原因及方案

Fleet PR #2882 的 b34 源码在 2026-10-19 03:52:53 UTC 遇到编译器 ENOSPC，随后 runner 自身的日志写入也失败。实际 artifact 保存了 134 包选择及尚未完成的 `status=running` 执行收据。错误发生在 app-server/core 集成测试二进制编译阶段，没有成功完成整套测试的证据。原始完整材料单独冻结在 `fleet-main-remote-ci`，没有改写既有 Fleet 修复或安全债务证据。

本候选精确采用已有 `hepta-consolidated-source.yml` 原生作业的四项环境设置：关闭 incremental、dev/test debuginfo，构建 jobs=2。原失败命令明确带有 `-C debuginfo=1` 和 `-C incremental=...target/debug/incremental`。原工作流没有磁盘使用量采样，不能从这些日志推定磁盘总量、各缓存占用或 SDK 可释放字节。固定主干的相关工作流也没有 SDK 删除先例，因此候选没有添加清理或删除逻辑。

编译 jobs 与 nextest 测试并发分别由原有配置控制。本候选不修改测试并发、选包、feature、锁、nextest profile、命令、target 位置、失败判定或时间预算；现有 40 分钟外层作业和默认 3600 秒执行器预算保留。debug_assertions 和优化级别也未修改。`dev-small` 仅作为已存在配置的比较对象，没有切换到该 profile。

## 实际验证范围

| 验证 | 实际结果与材料 |
| --- | --- |
| 完整工作流 Actions 语法 | actionlint 1.7.12，exit 0，`actionlint-01` |
| 原格式检查 | `just fmt --base f8 --check`，exit 0；该 YAML 变更没有需运行的源码格式器 |
| 原 134 包选择 | 候选原脚本重读 Fleet 同树 e770，完整选择和原 `just test --locked` 参数与远端 artifact 相同；`semantic-review.json` |
| 既有 Python 契约 | 102 个不同测试通过；第一次 72 pass、2 个导入错误，随后原 discovery 45/45 pass，其中 15 项与第一次重叠；没有 skip |
| 实际编译参数小范围证明 | 原 `codex-utils-string` 的 18 个库测试通过、0 skip；`cargo-flags-proof-02` |
| 参数证据 | 实际 rustc 测试命令无 incremental/debuginfo 参数，含 `strip=debuginfo`；build-script 输出 `NUM_JOBS=2`、`OPT_LEVEL=0` |

Python 包导入方式和 nextest `-vv` 的初次调用错误均保留原日志、exit、时间和源身份。修正调用后通过，没有放宽测试或门禁。下一次调用方式来自仓库原 discovery 命令和已安装 nextest 的实际帮助页。所有成功和失败记录使用同一个固定候选源码，前后输入一致。

使用已有工具，未安装或升级依赖。Rust/Cargo 为 1.95.0，just 为 1.51.0；本机 nextest 为已装 0.9.148，远端工作流的 0.9.103 固定值保留。小 crate 的隔离 target 总量为 28,596,657 字节，未归档缓存或二进制。

## 发布与剩余边界

工作流变更仍由原策略路由到 `full_repo=true`。本候选没有把原 #2815 的 CI 修改或产品修改带入，也不包含 Fleet helper 的单文件修复。正常远端门禁仍必须按实际结果验收。

这里的 102 个 Python 契约与 18 个小 crate 测试不是 134 包完整 CI 的通过收据。原 scoped CI 没有重跑；候选解决 ENOSPC 的最终效果尚待实际远端执行。没有新增本机 kernel、QEMU、设备测试，没有修改安全 ignore、依赖或保护设置。

`files-manifest.json` 枚举本批证据所有成员（不包含自身）；可交付包中的 `artifact-manifest.json` 另绑定原始归档与主文件。原 API/日志诊断位于独立的 `fleet-main-remote-ci` 包。
