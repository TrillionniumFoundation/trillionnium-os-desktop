# Hepta 最终有界状态补充

观察窗口：2026-10-19 04:44:15.398–04:45:54.800 UTC。每个原始 JSON 均保留自身请求开始、结束时间；这是跨端点有界快照，不是原子事务。

| PR | 精确 head | 实际状态 | CI required | Architecture required | 正常合并条件 |
|---|---|---|---|---|---|
| #2815 | d32e795f0d24df89fc57745f6fae70fbd0642eba | Ready / open / unmerged / blocked | failure | success | 未满足 |
| #2882 | b34cb44f06db0a66acb3d25b183a2a05c4cebc7e | Ready / open / unmerged / blocked | failure | success | 未满足 |
| #2883 | a8ce72907288d1836612446b87cb1d5c184993ac | Ready / open / unmerged / blocked | 当前精确 head 检查与 jobs 中尚未出现 | 当前精确 head 检查与 jobs 中尚未出现 | 未满足 |

#2815 保持正常 squash auto-merge；#2882、#2883 的 auto_merge 为 null。三个 PR 的 merged 均为 false、merged_at 均为 null。API 同时返回的 merge_commit_sha 不作为已合并证明。

#2883 检查合计 46：21 success、6 skipped、1 neutral、17 in_progress、1 failure。唯一已完成失败项是 cargo-deny job 117886607679：04:15:54 开始，04:17:17 结束；失败 step 6 为 Run cargo-deny，04:16:17–04:17:13。04:45:13–15 读取原日志再次得到 Transport closed，完整错误保存在 log-117886607679.json。本次远端实际拒绝包和策略诊断未知；没有用此前独立本地复现的 13 项替代此日志。

当前没有另外一个已完成的 #2883 Bazel / SDK failure 可取日志。原始 jobs 响应保留所有实际执行步骤；主要 Bazel 构建、Clippy、测试分片和 SDK 构建仍在运行。Architecture source-head job 117886436557 在 step 23 Compiled service lifecycle and actual process restart，该步骤从 04:35:30 开始；base-merge 成功不等于 source-head 或 Architecture required 成功。

#2883 scoped job 117886609136 为 skipped、0 steps。实际 Select blocking CI scope 日志明确 .github/workflows/blocking-ci.yml 唯一路径触发 full_repo=true，原始解码日志响应完整保留在 scope-log-response.json。因此本轮没有重新资格验证原 134 包 scoped 测试，不能据此称远端 ENOSPC 已解决。

branch-main.json 成功读取 main=f8c9419df6ddeb36ff8b522a50219981fb8d9345、protected=true，分支响应列出 CI required 与 Architecture required，enforcement_level=non_admins，app_id=15368。独立 /protection 仍返回 403 Resource not accessible by integration；只确认分支响应明确提供的有限信息，不推断保护已变更或完整管理配置可读。

本目录只新增原始 API 响应、错误、summary 和文件身份清单；无二进制归档、无重跑、无取消、无代码或 PR 变更。原已冻结报告与日志包未改写。
