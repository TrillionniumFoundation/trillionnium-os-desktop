# Hepta #2885 最后状态补充（2026-10-19 11:15–11:18 UTC）

**main 和 #2885 的提交头均未变化；#2885 仍为 Draft、open、未合并，合并状态为 blocked。两项分支保护要求的汇总 checks 仍失败。**

本目录保存本轮限定范围的三次 GitHub GET 原始 API 内容、完整工具响应及派生状态记录。它补充原 [09:06–09:07 的恢复后审查](../hepta-current-review/recovery-review.json)，不改写旧包或已经通过文字审阅的 R11 三份正文。

## 1. 观察与身份

| 读取对象 | 开始 UTC | 完成 UTC | 固定结果 |
| --- | --- | --- | --- |
| main | 11:15:05.717 | 11:15:06.312 | `f8c9419df6ddeb36ff8b522a50219981fb8d9345`，tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45` |
| PR #2885 | 11:15:05.717 | 11:15:06.571 | head `43a638d4e25ebc5a8b06babcd1c75c9acac53179`，base `f8c9419df6ddeb36ff8b522a50219981fb8d9345` |
| 上述固定 head 的 checks | 11:18:04.629 | 11:18:05.491 | 返回 52 / 52 项，全部 `head_sha` 与请求头相同 |

[PR 原始 API](raw/pr2885.json) 明确 `state=open`、`draft=true`、`merged=false`、`merged_at=null`、`mergeable=true`、`mergeable_state=blocked`。`mergeable=true` 仅说明 Git 可机械合并；此时的 `merge_commit_sha` 字段不能当作已发生合并。

[main 原始 API](raw/main.json) 的分支保护明确要求 `CI required` 与 `Architecture required`。两项均不满足通过条件。

## 2. 精确头 checks

| 观察时点 UTC | success | failure | cancelled | skipped | neutral | in progress | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 原 09:07:23.616 | 22 | 14 | 8 | 6 | 1 | 1 | 52 |
| 新 11:18:05.491 | 24 | 14 | 8 | 6 | 0 | 0 | 52 |

| required 汇总 | Job ID | 结果 | 实际完成 UTC |
| --- | ---: | --- | --- |
| CI required | 117967511210 | failure | 08:41:30 |
| Architecture required | 117944379036 | failure | 07:39:39 |

新的 [52 项原始 checks](raw/pr2885_head_checks.json) 均已结束。14 个 failure 包含汇总 gate，不能当作 14 个独立缺陷。本次没有读取新的失败日志，也没有将其他提交头的本地 cargo-deny 13 个拒绝套用到当前远端结果。

## 3. 旧源码与日志结论的适用范围

main、head、base 与原审查相同，所以此前固定 `43a638d4` 的源码和两份实际日志结论继续适用，但只保留其原范围：真实 Rust UI / shared renderer 和只读 gateway 已有部分成功步骤；source-head 产品状态测试是 6 例中 5 成功、1 失败；Architecture 原日志是 45 项中 43 成功、2 失败。其具体失效及未审范围以旧 [recovery-review.json](../hepta-current-review/recovery-review.json) 为准。

本次读取没有增加可信 owner 效果授权、原 Objective/Operations 闭合、Asterinas W1、G1-c/d 或设备控制资格，也没有产生新运行资格。主线与 PR API 的读取在 11:15，checks 在 11:18；这是有明确时间边界的固定头观察，不声称原子仓库快照。

## 4. 文件与原始响应口径

- [review.json](review.json)：机器可读的身份比较、全部 checks、实际 required contexts 及保留边界。
- [request-observations.json](request-observations.json)：三次 GET 的 URL、开始/完成时间和文件映射。
- [files-manifest.json](files-manifest.json)：本目录除清单自身外所有交付文件的 byte size / SHA-256。
- `raw/*.json`：GitHub fetch 返回的原始 API UTF-8 字符串原字节，保存时不重新排序或添加末尾换行。
- `tool-responses/*.json`：完整返回工具对象的 JSON 序列化，包含工具包装字段；它不是 HTTP 线缆层字节捕获。原始 API 字符串与包装中的两处 content 均逐字节核对。

本补充没有覆盖旧恢复包的任何文件。根代理将新时点写入最终报告，报告原有本地 WIP、历史运行、官方归档恢复与最终 CI 的资格边界仍分别保留。
