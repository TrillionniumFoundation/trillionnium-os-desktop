# 13 批 APK 审计的固定串行执行

最终请求在 `final-upgrades-r1/`，绑定抖音最后一次正常升级后实际读回的完整 46 包 scope：57340 B，SHA256 `489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4`。45 个 Launcher 包共 85 件完整 base/split APK，合计 4,977,440,266 B；全部 13 批的实际容量已从该原文计算，每批最多四包且不超过 4 GiB，每件不超过 512 MiB。另一个 scoped 包为 `local.pocket4.actions.v2`，不冒充 Launcher。

`REQUEST_MANIFEST.json` 为 17548 B，SHA256 `d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139`。13 个请求逐项经固定 29242 B / `faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a` collector 的实际 `validate_request` 验证。source、request 和 output root 均有明确 pin/唯一名称。旧 `initial-reference-r1/`、`initial-reference-r2/` 原样保留。

## 协调方式

使用现有 durable process executor 提交 13 个独立 job。唯一协调者是 root agent。每批由原 collector 独立获取和释放 `/run/lock/android-digitalis-actions.lock`；外层不跨批持锁、不并行、不改变 worker、不另写强杀/恢复逻辑。

每批最多 840 秒是 collector 的内部工作预算；建议 durable job deadline 为 960 秒。总 job 数上限是 13，发生 failed、UNKNOWN、缺少原文、未关闭 FD/child 或未释放锁时立即停止推进。一次 start 返回未知时，只核对其原有 idempotency key 的提交状态；不能换新 key 重发该批。

`audit_serial_gate.py` 仅在本地读证据、保存唯一 claim 并输出下一批具体 argv/key。它没有 subprocess、网络、ADB、Android、安装或 UI 调用；它不会自行提交 job。实际执行只能由协调者按它给出的固定 argv，在现有 root host runner 下进行。

先将最终 13 个 request 原字节发布到 manifest 中对应的 root-private 路径，验证原 collector source pin。worker 需要 root caller；manifest 中的 `coordinator_only_argv` 是 root 环境中的 argv。现有普通 UID1000 host executor 可继续沿已授权的 `sudo -n` 前缀，不得省去 root-owned request/source 检查。

## gate 调用

以下 `STATE_DIR` 为协调者新建的本地证据目录，不是 target App data 目录。使用绝对路径。`status` 不创建 claim：

```text
python -I -B audit_serial_gate.py status --plan final-upgrades-r1/REQUEST_MANIFEST.json --plan-sha256 d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139 --state-dir STATE_DIR
```

只有状态 `NEXT_READY` 才能使用 `claim-next`，它 O_EXCL 创建 `batch-01/intent.json`，给出固定 request pin、命令和唯一 idempotency key。目录/文件创建与父目录 fsync 完成后，再由协调者提交一次真实 job。

```text
python -I -B audit_serial_gate.py claim-next --plan final-upgrades-r1/REQUEST_MANIFEST.json --plan-sha256 d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139 --state-dir STATE_DIR
```

一次 batch claim 之后，没有完整终态证据时只会得到 `STOP_UNSETTLED_BATCH`。不存在 retry、skip、force、ignore-failure 或复用其他批 scope 的选项。

## 每批需保留的实际证据

在该批已有的 state 目录保存以下三份文件，原 intent 不得覆盖：

- `submitted-job.json`：闭合四字段 `job_id`、`idempotency_key`、`request_sha256`、`plan_sha256`。job ID 必须取真实 process_start 回执。完整 start 原文另外归档；此文件只绑定实际 job 与固定计划。
- `terminal.original.json`：实际 process_status 返回的平坦 terminal JSON 原文，包含 job_id/state/exit_code/output_complete/output_durable/terminal_publication_confirmed/timed_out/automatic_retry/cancelled/log_truncated/log_errors 等实际字段。
- `stdout.original.json`：原 collector 输出的完整 `zlib-base64` envelope 原文。若 bootstrap 先打印了自己的元数据，应另外完整归档 process stdout，并提取唯一 worker envelope 的原始行；不得 parse/stringify 权威内层 JSON 后再冒充原始字节。工具输出分页必须完整取回。

gate 会验证 terminal 的实际 job ID、正常且 durable 结束、没有 timeout/retry/truncation，再有界解码 envelope 并检查完整 artifact SHA。Python 解析保留大于 2^53 的整数，纳秒级 stat 不经过 JavaScript 数值往返。

只有以下条件全部满足才推进下一批：完整 package/APK 数量、3 条 host tool 命令/每 APK、manifest/package/version/当前 PM signer 全部一致、前后 typed guard 和 scope 相同、命令/工具子进程全部 joined、action lock 已释放、FD acquired==closed/remaining=0/errors=[]，且无任何 Android/UI/install/permission 操作。每个 App 的实际签名和声明权限仍由固定 collector 的原始工具回执支持。

collector 的 stdout artifact 比其 durable `result.json` 多 `final_receipt` 和 `owned_descriptors_final` 两个最终字段。gate 按已固定源码移除这两个字段并用同一 Python canonical 规则验证公布的 durable result 字节数/SHA。它明确标为从原 stdout 还原并匹配 published pin，不冒充一次新的远端 readback；collector 在写入时已经实际执行过 readback。

13 批全部结算只说明已完成 APK 身份、manifest 和签名审计。有效权限仍为 `UNKNOWN_NOT_QUERIED`，业务 QA、长时间运行、重启/恢复和 production readiness 必须另有实际运行证据，不能因此清理旧 App/framework 产物。

## 离线控制

`test_audit_serial_gate.py` 验证固定 45/86 初始集合、唯一 claim、未知/失败终态阻断、乱序阻断、签名/FD/child/锁门槛、纳秒整数精度损失拒绝、有界解压、完整 13 批串行结算。除初始 pinned scope 的实际只读字节统计外，终态与 App 结果都明确为临时 synthetic fixtures，不构成任何真实 Android 审计 PASS。测试不读取 Main，也不提交 job。
