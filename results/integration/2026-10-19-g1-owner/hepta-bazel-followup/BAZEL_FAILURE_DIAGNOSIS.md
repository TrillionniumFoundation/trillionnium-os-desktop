# R10：Bazel 三个新增失败的原始日志追加诊断

## 结论与审计范围

本次成功取得了三个指定失败 job 的**原始远端解码日志**，读取时间为 **2026-10-19 02:18:45.651–02:18:46.907 UTC**。这与前一份 cargo-deny 安全诊断的“原日志读取失败、本地独立复现”不同，三份 Bazel 结论均来自实际失败 job。没有把安全报告中的 13 条 advisory 套用于 Bazel 失败，没有构建、重试、取消或修改任何源码、依赖、策略、CI 或 PR。此前冻结的 `security-debt-package` 未改动。

两个 Clippy job 是同一个既有测试 helper 的 `unwrap()` lint 错误。Windows shard 2 的最终摘要则是 **103 / 142 个测试目标执行，89 pass、1 fails to build、14 fail locally、38 skipped**。其中存在真实 Windows sandbox 删除边界负例失败，不能把 Windows 设备控制能力判为已通过。广泛 Windows 遗留修复不应混入 owner 的 Objective History PR。

## 精确源码和日志身份

GitHub checks 绑定 owner head `d32e795f0d24df89fc57745f6fae70fbd0642eba`。三个日志都显示实际 checkout 为 prospective merge **`60a3376902982d79e85173d6aaf6bd631b4c4cf3`**；其父提交为 f8 基线与 d32。独立 GitHub commit API 确认 merge tree 为 **`a3e718280a7e17b8c4a226a0232bf18c23fd3586`**，与 d32 及本地 `1b0fedb8c2b510106848f6feaf530c9b3698399d` 完全相同。它是 CI 的测试 merge，未被称为实际已合并提交。[source-and-jobs.json](source-and-jobs.json)

已复制并核对 **30 个失败位置、支撑实现及构建策略文件**：其 Git blob 在 **f8 / 2be / 当前本地等价树** 均相同，工作树 clean。[source-comparison.json](source-comparison.json) 同时保留整个 PR 的 29 个 changed paths。文件相同能确认这些具体位置不是本 PR 新增改动；没有重新运行 f8 CI，不能据此声称每项动态失败的全部因果均已由基线执行证明。

| Job | 实际失败步骤 | 步骤开始 → 失败完成 UTC | Job 最终完成 UTC |
|---|---|---|---|
| [Ubuntu GNU Clippy 117846024935](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39185139893/job/117846024935) | Step 4：bazel build --config=clippy lint targets | 01:24:35 → 02:00:50 | 02:01:02，failure |
| [macOS ARM Clippy 117846024963](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39185139893/job/117846024963) | Step 4：bazel build --config=clippy lint targets | 01:24:37 → 02:09:39 | 02:10:10，failure |
| [Windows shard 2/4 117846025117](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39185139893/job/117846025117) | Step 6：bazel test shard | 01:24:55 → 02:06:56 | 02:07:07，failure |

完整日志逐字节保存，并各自生成经过解压同字节检查的 `.log.xz`。大小、SHA-256、工具读取时刻和 decoded UTF-8 保留边界见 [log-preservation.json](log-preservation.json)；代表性原文行号见 [failure-excerpts.json](failure-excerpts.json)。这些是实际 failure，不是 timeout、cancelled 或推测的排队问题。

## 1. 两平台 Clippy：同一 helper，最小修改不需要放松 lint

两份日志明确拒绝 `//codex-rs/hepta-fleet:hepta-fleet-unit-tests-bin`，定位到 `hepta-fleet/src/authority_port.rs:197–210` 的 `ledger()` helper：`admit_host(...).unwrap()`。错误请求来自命令行 `-D clippy::unwrap-used`。Ubuntu 原日志 8814–8833 行、macOS 原日志 8680–8699 行给出同一位置。

`clippy.toml` 已有 `allow-unwrap-in-tests = true`，但此处是普通 helper，不是带 `#[test]` 的函数。**不能简单替换为 `.expect("...")`：Cargo.toml:586 与 .bazelrc:126 也 deny `clippy::expect_used`。** 无需新增 allow、改全仓 lint 或删目标。

保持原 HostObservation 和所有调用者，最小可审查建议是把返回值作为测试断言：

```rust
let admission = ledger.admit_host(HostObservation {
    // 原有 fixture 字段保持相同
});
assert!(
    admission.is_ok(),
    "valid host fixture must be admitted: {admission:?}",
);
```

这保留原先“fixture 准入失败则测试失败”的语义和具体诊断，避开 helper 内 unwrap / expect，两处构建策略都不用修改。本轮仅提出建议，**未实施、未编译或宣称修复后通过**。该 helper 文件的 f8 / 2be / 当前 Git blob 均为 `55e117dafe84709451a638bb8f6bafa41c38bd5a`。

## 2. Windows 编译目标：临时 archive 文件的复制失败

`//codex-rs/exec:exec-all-test` 在原日志 4762–4788 行失败。直接错误不是 Rust 类型诊断，也没有证据指向磁盘不足；`process_wrapper` 要把 `codex-exec.lib.temp-archive-*.a` 复制进 unified dependency directory 时，得到 **os error 2：找不到文件**。

仓库现有 `patches/rules_rust_windows_process_wrapper_skip_temp_outputs.patch` 只排除文件名包含 `.tmp` 或以 `.rcgu.o` 结尾的对象，**不覆盖实际失败名中的 `.temp-archive-`**。MODULE.bazel 明确加载这份 patch。源与日志支持“临时文件类别遗漏，随后复制时文件已不存在”的窄候选；并发消失的具体原因尚无独立追踪，不能直接写成已证实 host 故障。

未来独立修复可精确补齐临时 archive 分类，并检查稳定 `.lib` / `.rlib` 仍被复制；不能把所有复制错误或真实依赖缺失一律忽略。需要实际 Windows wrapper / Bazel 验证后才可判定修复。本轮不修改该 patch。

## 3. Windows 的 14 个失败测试目标

下表以最终 Bazel target 摘要为计数口径，避免把内部分片、既有自动重试和日志重放重复计数。`windows-test-blocks.json` 保存分片输出和实际 panic；CLI 的输出停在未换行测试名后，解析器明确标识边界，不把后续 app-server panic 错配给 CLI。

| 失败 target | 原日志中的实际现象 | 源码定位 / 结论边界 |
|---|---|---|
| cli:sandbox_cloud_config | Exit 101；只有开始的测试名，缺少进一步失败原因 | 原文 13159–13164；本次不足以确定原因，不从其他测试推断 |
| core:responses_headers | 等待 event 超时 `Elapsed(())` | `core/tests/common/lib.rs:353`；具体事件缺失原因未证实 |
| hepta-agentd:cognitive-write-qualification | 三个 fixture 构建失败，`RegistryOpen("UnsafeStateDirectory")` | `runtime_tests.rs:113`；prompt registry 的 non-Unix 分支直接返回该错误，不是已完整实现 Windows 持久 owner |
| hepta-authbus:unit-tests | `PermissionDenied`，os error 5 | `authority_schema_tests.rs:29` 使用 `File::open(...).sync_all()`；需核对 Windows 句柄访问/同步语义，不应吞错 |
| hepta-automation:automation | schema rewind 的 `ALTER TABLE` 失败：trigger `automation_timer_lifecycle_drain` 引用不存在的 outcomes 表 | `automation.rs:978` 先 drop 表，1036–1039 后改列；0018 migration 中仍有引用该表的 trigger，fixture 逆依赖清理不完整 |
| hepta-bao-adapter:unit-tests | 七个 lifecycle 测试得到 `Unavailable` | `persist()` 包含父目录 `File::open(...).sync_all()`；错误映射抹掉细节，Windows 原生持久化句柄路径是需进一步验证的候选 |
| hepta-codex-adapter:unit-tests | 三个恢复 fixture 解析失败：`AbsolutePathBuf deserialized without a base path` | `lib_tests.rs:127` 硬编码 `cwd: "/tmp"`；需要平台有效的绝对 fixture 路径 |
| hepta-infer-worker-host:unit-tests | `physical turn start` 文本定位 expect 失败 | 测试仍找 `client.request_typed::<TurnStartResponse>(ClientRequest::TurnStart`，当前实现已通过 `send_authorized_turn_start`；旧源码字符串断言失配，不证明 final-use 顺序实际错误 |
| hepta-intelligence:unit-tests | 19 个失败，主要为目录 `File::open` 的 os error 5 与 `UnsafeStateDirectory` | `evaluated_shadow_tests.rs:129` 等及 prompt registry non-Unix stub；应实现平台等价的真实持久化边界后验证 |
| hepta-memory:unit-tests | 六个失败，含 `root is redirected`、pointer rename Access denied、预期错误类别不匹配、迁移断言不符 | 当前 recovery 比较 canonical root 与原 root，且使用 Unix 风格文件/目录同步；需真实 Windows 路径、句柄和恢复边界验证，不能认定全部只是字符串问题 |
| windows-sandbox-rs:helper_manifest | helper 路径 `_main/.../codex-windows-sandbox-setup.exe` 不存在，os error 3 | 测试直接把 Cargo/Bazel 注入路径作为本地路径；先修复 runfiles 定位并保留真实 Win32 manifest 验证 |
| windows-sandbox-rs:unit-tests | 三个真实 native 断言失败，包含预期拒绝的删除成功 | 详见下一节，作为 Windows 控制边界阻断记录 |
| app-server:unit-tests | SQLite home 错误文本中 `/tmp/...` 与 Windows `D:\\tmp\\...` 不一致 | `app-server/src/lib.rs:1832–1842` 的硬编码预期；不是实际 SQLite links 冲突 |
| app-server:all-test | 原结果 `FAILED in 43 out of 45`，涉及多个内部分片/尝试；多处 `NotIdle`、terminalizing、rollback-in-progress，另有 Bedrock 未实现、header / mock 断言 | 不把 MCP 404 和请求超时自动认定为全部根因。需要实际 session 生命周期 / capability feature 配置分析；本轮未证明精确根因，不应通过重试 turn/start 或放松 fence 消除失败 |

### Windows sandbox 的具体边界失败

原 `token_tests.rs:280` 在受限 token 下依次尝试外部文件写入、创建、删除文件、删除目录。日志的实际值是前两项 `PermissionDenied`，**后两项为 None（删除返回成功）**，预期是四项均拒绝。该结果不是单纯测试显示差异。

原 `unified_exec/tests.rs:775` 的真实 legacy process 完成后，原预期外部 sentinel 内容仍为 `Some("outside")`、受保护目录仍存在；实际分别为 **None 与 false**。`token_tests.rs:213` 还发现 deny ACE 修复的重复调用结果不符合预期。详细原值保存在 failure-excerpts 与完整日志，不能用测试 target 总数或其他平台成功掩盖。

这些是固定 Windows CI fixture 下已观察的负例失败；没有开展真实用户设备测试，也没有把它扩大为所有部署环境的可利用性断言。它足以说明 **本轮不能验收 Windows 的删除隔离 / 设备控制边界**。应在独立 native Windows 整改中核对 token、ACL 继承和 DELETE / parent-delete 权限关系，并重验真实外部 sentinel。不得弱化预期或忽略拒绝失败。

## 4. 最后一次精确 head 状态

[final-snapshot.json](final-snapshot.json) / [final-status.json](final-status.json) 的读取时间为 **2026-10-19 02:24:28–02:24:29 UTC**：

- owner PR #2815 的 head 仍是 d32，Ready / open / unmerged / blocked，普通 squash auto-merge 保持。
- 47 checks：**24 success、6 skipped、1 neutral、6 failure、10 in_progress**。
- **Architecture required success；CI required 尚未生成**，blocking-ci 仍运行中。
- 相对本次三日志范围，新增 Windows shard 1（117846025091，02:19:51）和 shard 3（117846025094，02:20:34）失败。本次只记录它们的 API 状态，**未读取日志、未推断与 shard 2 同因**。
- Windows Clippy / shard 4 的 job 当时仍在 post cleanup，未以步骤状态推断 job 终态。

本轮至此停止轮询，不改 owner 活跃头。最小 helper lint 修改可独立提出；Windows 的广泛平台和边界问题保留为后续明确工作，不能用无关依赖升级或门禁例外替代。

## 5. 保存与交接

原始三份 `.log` 与 connector response wrapper 均保留在工作证据目录；提交包纳入其验证过的 `.xz`，并以清单记录原字节数和 SHA，避免重复发布大日志。source-review 是 30 份固定 Git blob 的复制件，没有 cache、工具安装目录、产品 ELF、私钥或工作树。失败原文未删，原安全包未覆盖。所有候选修复均未执行，没有新增通过声明。

