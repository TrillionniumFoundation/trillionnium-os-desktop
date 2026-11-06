# 本地保留清单与观察候选更新

这份追加说明不覆盖原 catalog、原计划或任何原始回执。

## 地址计数的三层含义

| 层 | 宿主文件引用 | Android 文件引用 | 非文件系统 cgroup 地址 | 含义 |
|---|---:|---:|---:|---|
| 原始 `SUMMARY.json` 提取分类 | 491 | 304 | 尚未分离 | 795 个绝对地址字面量；其中 `/init` 最初与两个 ControlGroup 一起归到通用 host 桶 |
| `TYPED_REFERENCES.json` | 488 | 305 | 2 | 正确分层；793 个文件引用，2 个 cgroup 地址不作目录遍历；`/init` 位于 Android 根 |
| `observer-candidate-r2/scope.review-only.json` | 488 | 309 | 0 个扫描项 | 在原 793 文件引用上追加 NDK 实际 APK、codePath、CE/DE 共 4 项，合计 797 个文件引用 |

795 不是当前存在的文件数；797 也不是安装包数量。原始记录、分层解释和新增引用分别保留。

## 新 48 包身份范围的实际来源

根代理结算的单次身份观察为 `1a1b31300b9-fc05-8095`。完整实际 worker 原文在：

`successor_audit_requests/explicit48_scope_r1/actual/worker.stdout.original.json`

其为 10290 B，SHA256 `aaa24285be227f4ad52fe63e5a2a06af63f7bab571fb5cf4d99e6d0ab02f12d1`。根联合结算文件 `root-validation.actual.json` 为 1330 B，SHA256 `e66b00681144b4ba1049cab4e429c44f33ab5e1e1aa3e8c190776acb71b5f73b`。

实际 scope：

`/home/alex/work/pocket4-current-explicit-48-app-observation-20261106-r1/app-scope.private.json`

59957 B，SHA256 `b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4`；48 包、88 APK、4,978,895,379 个逻辑字节。原 47 包逐字段保持，新 NDK 包精确匹配此前独立发现。这个 scope 是身份观察，没有新增验签、UI 或安装资格，也没有声称覆盖 PM 的全部 206 包。

NDK 观察原文是 `native46_discovery_r1/actual/artifact.original.json`，112546 B，SHA256 `69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400`。实际 UID10162、PM code0、单 APK1397258 B，完整 SHA256 `b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164`。本次保留观察不会把 PM signer 摘要转换为新的 APK 验签结论。

## 可供一次执行审阅的候选

唯一拟执行版本在 `observer-candidate-r2/`。`observer-candidate-r1/` 保留未执行，区别是当时只绑定原 47 包保护范围。新 r2 使用实际 48 scope；797 个 metadata 引用及全部新观察函数保持一致。

根代理可审 `observe_retention.py`、`owned-against-actual-r4.diff`、`stager-against-actual-r4.diff`、`request.review-only.json` 和 `process-request.review-only.json`。本分支没有提交 process、领取 claim、读取目标机或执行 Main 操作。

- 新 worker 是独立 metadata 观察，不导入或扩大 Beike 的两包 Flow，不运行任何 Android、ADB、原生 lifecycle、安装、grant 或 UI 命令。
- typed guard、原 core、全 48 包身份检查和现有 action lock 保持实际实现。原 owned FFI bootstrap、持有 child pidfd 的正常退出收口不变；新内部预算180秒、owned child220秒、外层240秒。
- 元数据扫描只限 16 个已列根。不会遍历跨项目 JDK 的父目录；不会自动打开 mountinfo 或 cell config 新发现的 backing 路径。
- 原始 mountinfo/maps、进程 FD 元数据、目录条目和 alias 索引写入新的 root 私有目录，公共 stdout 只含固定引用、pin、计数和明确缺项。不会读取业务数据库、账号或凭据正文。
- `ok=true` 只表示这次有界观察正常完成且身份、FD、lease、owned child 收口通过。某个大目录达到条数、时间或输出预算时，该目录仍为 `INCOMPLETE`，可继续完成最终身份检查；不会伪装完整盘点。所有条目始终 `cleanup_eligible=0`、`reclaimable_bytes=null`。
- 已知磁盘使用报告与最终清理资格分开。`st_blocks` 去重后仍不解决 reflink、快照、压缩和外部进程引用，因此不能改称可回收字节。

## 实际本地控制及其限度

本地有效 UID 为1000。第一份控制在 metadata 遍历完成后，把 UID1000 新建的日志交给生产 root-only writer gate，实际被 `NEW_PRIVATE_METADATA_SHAPE` 拒绝；原 stderr 与未修改的初版控制保存。

随后只修改控制的预期，不改 observer 或 root gate。第二份实际控制 exit0，验证：真实硬链接去重且不遍历指向范围外的 symlink；真实条数上限产生 INCOMPLETE 并关闭迭代器；UID1000 无法通过生产 root-only 日志门禁，原 stream FD 正常关闭。35/35 显式 FD 关闭，全进程 FD 身份3→3。没有把本地 UID1000 伪造成 root，也没有宣称已做生产 root 写入正控。

原 r1 与 r2 worker 的所有函数体逐字一致；差异只有固定路径、scope pin 和48包列表等声明。该控制覆盖同一 metadata 实现；它不替代目标机实际终态。根代理接受并执行 r2 后，仍必须同时检查原始完整 stdout、worker artifact、owned pidfd、所有 FD/lease 及权威 durable terminal。

当前生产就绪仍为0，清理仍为0。
