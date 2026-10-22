# ext2 初始 RDONLY 原生执行证据独立复核

## 结论

**现有证据支持收口这次 ext2 初始 RDONLY 自动 atime 修复；未发现该限定范围内的证据阻断。** 本复核只读取留存文件并重放纯 host oracle，没有新增 QEMU／内核运行，没有调用 Runtime，也未执行 host Agentd、修改源码或发布。

复核对象为源码 `9076f1ae6ebe29e2fdb78475e7f3157ce2f1d2dd` / tree `eeae4dc1ef546d408b55c98310e99e3156f08207`，parent `f85ccae8445f8d753572d41411d98ee28d253af5`。完整机器记录见配套 JSON 复核记录；下列相对路径指 99 文件留存包内对应条目。

## 已核对的执行结果

| 项目 | 独立复核结果 | 主要证据 |
| --- | --- | --- |
| 完整 core 正控 | **274 passed / 0 failed / 0 filtered / 0 soft-skip**；274 个唯一名称，36 个 required；原 `check_guest` 重放通过；QEMU 33 | `positive/core-ktest/aster-core/guests/guest-001/{serial.log,qemu.json}` |
| 权限 SMP | **277 declared / 3 passed / 0 failed / 274 filtered**；三项固定 race 的 CPU 0／1、锁占用和权限结果均符合原 parser；QEMU 33 | `positive/permission-smp/aster-core/guests/guest-001/{serial.log,qemu.json}` |
| ordinary QueryAbi | 原 `evaluate_guest` 重放通过，**18 个 marker 各一次**，顺序正确；QEMU 33；记录为 ordinary `ActionChoice::Run` | `positive/ordinary-queryabi/{result.json,serial.log}` |
| 旧 atime 行为负控 | 与正控**同一组、同一顺序的 274 个名称**；271 passed / **仅 3 failed** / 0 filtered；原 gate exit 1、QEMU **65**，不是“成功 guest” | `negative/{result.json,invocation.json}` 及 `negative/gate/aster-core/guests/guest-001/` |
| 冻结原 Agentd ABI | 原 oracle／child parser 纯函数重放通过；空 stdout，精确缺 `HEPTA_FLEET_ROOT` 的 stderr，child exit 1、harness 0；QEMU 33 来自原记录 | `abi/{result.json,serial.log,invocation.json}`、`abi-runner/run_agentd_abi.py` |

三个负控失败精确为 `readonly_buffered_read_keeps_atime_without_writes`、`readonly_direct_read_keeps_atime_without_writes`、`readonly_readdir_keeps_atime_without_writes`；均在测试文件第 130 行的 atime 相等断言失败。`writable_reads_persist_atime` 与 `readonly_flag_does_not_discard_preexisting_dirty_data` 仍通过。由于失败发生在后续 dirty／BIO 断言之前，**负控不能宣称观测到了非零 Write BIO**；原 receipt 的 `negative_bio_write_count_claimed:false` 正确。

正负两次原 OSDK 命令、cwd、生成的 Cargo lock、记录的 QEMU 二进制和 kernel 输出路径一致，kernel 摘要不同。正控 ELF `9b4e0bae271bdc1e84b142284afa01917bf5c808f8e033b87938e63f247fcb9c` 在后续 profile 覆写输出路径前已独立保留；负控 ELF 为 `efc151fbb04bf41e74258f88f7475cc016cb1a04ff3888f02470400b29622f54`。这里核对的是原始执行记录与保留身份，未在本地重新读取这些大 ELF。

## 源码与恢复证据

对 7,630 个路径的记录 mode/blob 重算 Git tree，正向得到 `eeae4dc1…`，负控得到 `c5f7bdc874fddeb709b09ad545ae07e9b179d250`。两组完整快照仅 `kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/inode/attrs.rs` 不同；五个 ktest、三个 caller、sync 及所有其他路径保留。负控补丁 SHA256 `a3d95ad68f9e8f69d7aec68c1346a4ab559d9051dc1b4195e8dee15b30a238de` 与之前审查版本一致。

候选 before/after 快照逐字节相同，ordinary 的 before／after boot／after guest 三份快照也相同；负控运行前后及独立归档的 files 表一致。恢复后的身份确为 `9076f1a… / eeae4dc…`。从记录的 blob/mode 重算 tree 不等于包内保留了全部 7,630 个源文件字节；两者在 JSON 中明确区分。

留存包 `native-execution.tar.xz` 为 703,464 bytes，SHA256 `6602d188cf1f236e6e60a84ce36184f8a9560ca766f95e61524702e9a16a5e2d`。独立重开 archive，99 个常规成员的名称、size、SHA256 以及已解包内容全部一致。

## Agentd 完整关机日志

新 ordinary kernel `8bda1c4876cbfbca0c441adb2d3ac4a91c4b3ff2e9faadedcb3d43503a0b6c09` 与 QueryAbi 的记录一致。冻结原 Agentd 为 `228d2e07583d0d27cf5750a6ba169254380fb4d49f1fdc21adcc04001fc3252f`，484,463,504 bytes，Hepta 源码 `6d6097da843f5831dfaf9cee3530da512d072a15` / tree `f722fbe5f24275c324089be720559a40901105f3`。新 runner 仅更新 kernel head/tree/SHA 和一条对应诊断；逆向还原后精确得到原 runner SHA `0994e2452596ca8a4c3b59f6a6234d070c4ba5cb2edde4232271a7eefb1f535c`，其余三个伴随源码字节不变。

完整 `abi/serial.log` 为 **7,298,680 bytes、21,569 行**，SHA256 `7b9f6ecea33141173f2e4dc683ac131bb85e2ec34ea0bb43c011188b34a61399`。逐全日志检查得到：Write 请求 **0**、Submitted Write BIO **0**、`IoError` **0**、block write error **0**、writeback error **0**。尾段保留 `SYS_SYNC`（21,566 行）→ Flush（21,567 行）→ `SYS_REBOOT`（21,569 行）。这证明本次原 Agentd 读取及关机路径没有再次出现旧三条写盘错误；它不是物理设备独立 trace 或完整只读语义证明。

去除 ANSI 控制码后仍有 **25 条精确的 `Unimplemented syscall number: 334` 警告**（`rseq`），以及 `NoIommu`、framebuffer not found、simpledrm unavailable 三条警告。进程在这些条件下到达预期早期配置拒绝，只证明这次回退路径继续运行，不能声称 `rseq`、GPU/IOMMU 或显示功能已实现。

`abi/frozen-input-manifest.json` 是 runner 用 `sort_keys=True, indent=2` 重序列化后的快照，实际 SHA 为 `0b464e10…`。主代理随后补入 `agentd-original-input-manifest.json` sidecar；本复核已实际读取其 **2,074 bytes**，重算 SHA256 **`999e632d8e82cc71b58436a5c0a63b50312cf83ccfcfdb35b28b947b0eb12728`**，与 producer 原输入 pin 精确一致，并确认与归档快照的解析值完全相同、字节不同。两份原件分别保留，99 文件 archive 未替换。这个原始 manifest 的可复现性遗漏已关闭；原 ELF、payload、库、initramfs、BIOS/QEMU 等大输入仍留在 producer，本次没有重新计算缺席二进制的摘要。

## Source profile 与发布状态

已实际读取既有 `support/release/profiles/2026-10-22-organ-source.json`，7,372 bytes，SHA256 **`260139110c06921db6a156c1f072c55d0a3218f4b8da523b509adad4471e5667`**，与 `positive/source-profile-verification.json` 精确一致。12 个 OS source 和两个 OS golden 的本地字节及源码快照身份匹配。source-map 使用原工具的 canonical JSON 摘要 `83371d35…`；原 JSON 的排版字节摘要不同，不构成不一致。

Profile 和 receipt 一致绑定最终 Hepta `6d6097d… / f722fbe…`；OS 身份由 receipt 显式绑定 `9076f1a… / eeae4dc…`。`qualification: source-only`、`activation: disabled`、`effects_authorized:false` 及七项未配置（grant provider、protected clock、external frontier、issuer keyring、revocation head、recovered writer、current cut）全部保留。

完整干净两仓验证、Hepta fixture 逐字节相等和原 history owner `995b6fb9…` 的 ancestry 由**实际 producer verification receipt**支持；本地没有完整私有 checkout，未重复该验证。原 manifest 已在预定证据 PR 的 #242 基线中，99 文件 archive 未包含它不再构成 repo 上下文下的缺失；独立搬运 archive 时需同时带上原 manifest。

`positive/source-identity.json` 中 `published:false` 是创建时快照。后续 `source-publication.json` 与 `source-push.log` 记录同一 head/tree/parent 的分支发布，两者不矛盾。源代码发布不代表生产激活、合并或 GitHub CI 通过。本复核没有查询实时 GitHub；主代理说明源码 PR #243 仍以 `9076f1a…` 开放，证据 PR 将独立基于 #242 的 `182dd` head。

## 未扩大结论

SMP 的完整 artifact-reading checker 因缺少 producer 留存的大二进制没有在本地全量重放；已重放原 serial parser 并核对固定两 CPU profile、原记录参数与所有观察值。QEMU 退出码也来自原始执行回执，并非本次重新观察的进程退出。

本结论只覆盖初始 filesystem-wide RDONLY 的 buffered/direct/readdir 自动 atime。它不证明全部 VFS 修改拒绝、virtio RO 协商、显式时间设置、NOATIME、并发 RW→RO remount 线性化、crash durability 或实体硬件。Agentd 没有启动 daemon 或原 owner runtime；production、G2、F completion 均仍为 false。
