# R7 ARM 历史 CI 证据恢复

**原始执行证据已恢复并重新核对；本次没有重跑任何构建、测试、原版 daemon、issuer、objective 或 UI。** 工作区维护清除了旧 `next-tools` 与 worktree。本目录在 2026-10-18 14:38 UTC 后重新整理，保留的是此前已经完成的同一次 ARM CI。

## 固定的历史执行

| 项目 | 原始记录 |
| --- | --- |
| [Run](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39099387901) / [Job](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39099387901/job/117592347821) | `39099387901` / `117592347821`，attempt `1` |
| Desktop head | `c4d4224c9daf1a5b22997930000f43001525d531` |
| Desktop tree | `59e925797887187b902125ea2a162f71a5eabed4` |
| 固定原版 Hepta | `f8c9419df6ddeb36ff8b522a50219981fb8d9345` |
| Run 开始 / 完成状态更新时间 | `2026-10-18T05:06:11Z` / `2026-10-18T05:29:42Z` |
| 原始结果 | `completed/success`；原版 8 项 + 持续 Session 8 项通过 |

[原 run API](readback/run-api.json)、[job/step API](readback/jobs-api.json)、[artifact API](readback/artifacts-api.json)从此前保留的 functions store 值恢复，没有把本次恢复时间替代为原 CI 时间。[原始报告](selected/report.json)与 ZIP 内 `logs/gate.log` 逐字节一致；[原始 JSONL](selected/work/original_agentd_process_probe.log)的 17 条记录与报告完全一致，原 [exit code](selected/gate-exit-code.txt)为 `0`。`report.recorded_at_utc` 是原门禁开始记录时间，不能视为结束时间。

第一段 Session instance `3323c492e65879acea1ad0fd6383d6ef`（PID `23499` / worker `23501`）连续经过 Starting、Running、Draining 和 old-spawn stale。原版 Agentd PID `23471` / spawn `1` 重启为 PID `23598` / spawn `5` 后，旧 Session 保留旧来源历史并返回 `protocol_mismatch`。显式替换 Session 后，instance `055275f4bf1782162c444f538c9175c4`（PID `23694` / worker `23696`）恢复 Running，并在原版停止后返回 `unavailable` stale。两个 stale 阶段都有相隔的失败采样与精确保留的最后观测，Session IPC 的资源样本继续前进；任务列表为空。

本轮最后保留的是 Running / generation `6` 的历史。这不表示原版停止之后还在运行，也不排除受控停止内部经过 Draining。[新恢复阶段核对](review/phase-summary.json)保留六阶段、原版八项、Session 八项及两个 Session cleanup 记录。它是对旧 JSONL 的新解析，不是新的运行结果。

## 精确恢复的材料

[原始 evidence ZIP](evidence-12125674093.zip)来自同一官方 artifact `12125674093`：**1,040,029 字节**，SHA-256 **`aaed616d85f52cd0c51672bd2bd22f43746bbf9c06c4c325002be3269594506c`**，与此前记录和官方 digest 完全相等。[33 成员清单](review/zip-members.json)逐个记录 SHA、CRC 和大小；所有成员 CRC 通过，均为常规 UTF-8 文件，无 ELF、嵌套下载包或运行 socket。有限凭据形态扫描没有匹配；下载签名 URL 未写入归档。

[完整 job 日志](readback/job-117592347821.log.gz)从原 functions store 恢复。原 UTF-8 字节为 **145,349**，SHA **`b2580573da0adea34417cc2b2cc0210dcdc79295c1e1af28426286d07c94cd69`**；`gzip(mtime=0)` 后 **25,995** 字节，SHA **`563751ef8be61cb1f1639ae0634e6f5849a1ccd036eecf286554dda7a557b9e7`**，原字节与压缩字节都匹配先前记录。

旧文件引用 `file_00000000c72c82309af87c8898fb47e5` 的临时链接已失效。恢复使用同一 artifact 的新引用 `file_0000000033348230b36d78c77a86d2ac`，并在下载后验证原 SHA。[新读回/恢复收据](readback/readback-receipt.json)记录实际恢复时间、来源与新旧文件引用，不把新下载解释为重跑 CI。

固定 `c4d` 的 25 个源码文件也重新只读取回：28 条原 SHA 记录与固定 Git tree 的 blob ID 全部匹配，两份实际复制进 linked probe 的 Rust 文件与 ZIP 内容相等。[新源码恢复核对](review/source-binding.json)记录这些检查。原版源与锁文件的前后 clean 状态来自[原始最终收据](selected/identity/final-checkouts.json)；本次没有重新创建或运行原版 checkout。原两次 `--locked metadata` 日志仍逐字节相同，原 probe 锁 SHA 为 `72cb7346158f4c3514922cc7b9020f9b9d290aec78e047264a738d52afe6ed68`。

## 原归档缺失与新记录

**不能声称原 27 文件归档已按完整旧 SHA 恢复。** 原始 ZIP、API、job 字节、固定源码与 ZIP 成员副本已恢复；旧独立 review、README、MANIFEST、SHA256SUMS 等整理材料没有完整原字节缓存。此处同样整理为 27 个文件，其中 16 个是从原材料恢复的文件，11 个是明确标注的新恢复程序、说明、审查和索引。原材料与新整理的逐文件来源见 [MANIFEST](MANIFEST.json)。

以下旧摘要只用于记录已知历史，不是本目录当前 SHA：旧独立 review `9916620950b891a0e027b5c3e2429caa3e9eb44eb6cc094d9823d8e9d8f60fdb`；旧 MANIFEST `cd93d719d0f291ddbeaabca8ff9d07e39102c7a5e9aff7e57f2c7b79337f03d3`；旧 SHA256SUMS `15a07378222714e9b6349fa37bb8d8ba24b2599172a8eb479523a96740c3ea34`。没有猜测旧生成时间来匹配这些哈希。

[本次独立恢复核对](review/independent-review.json)采用实际恢复时间。[恢复程序源码](verify_readback.py)是本次外部恢复目录中实际执行程序的副本，其输入是原材料与固定源码数据，操作仅为读、校验和写恢复文件；它没有产品/测试执行能力。当前文件摘要以新的 [SHA256SUMS](SHA256SUMS)为准。

## 五 ELF 及资格范围

[五 ELF 绑定恢复核对](review/five-elf-binding-review.json)保存原 runtime report 中五个 SHA、成功 step 10 的 ELF64 little-endian AArch64 (`e_machine=183`) 和逐文件哈希断言。[规范化命令摘录](review/binding-step-as-logged.txt)匹配[固定 workflow](source/.github/workflows/hepta-original-agentd.yml)与原 job 日志。

**87,286,055 字节的大型 ELF artifact `12126585987` 没有下载。实际 ELF 没有在本地复读或重新散列；大包内单独的 `binary-manifest.json` 也没有直接读取。** 其官方 metadata/digest 与原报告哈希被保留，不能改称本地二进制复验。

原 CI 资格仍仅为 **Linux ARM64 原版 Agentd + 持续 Session 只读生命周期**。原版 FleetHandle 控制本次私有测试进程的生命周期；observer 和 Session 只读。原记录的 `objective_submission`、`model_turn`、`device_effect` 均为 `false`，Shell pixels 为 `not_run`。恢复工作不增加 ObjectiveStart 原版接纳、durable admission、模型执行、物理/移动设备控制或新版本源码的资格。
