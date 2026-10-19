# PR #205 最终 A06 产物独立复核

本包核对官方 GitHub Actions 已产生的原始字节，没有重新构建内核、启动 QEMU、重跑测试或改变门禁。源提交是 `4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930`，树是 `8eb809136a402cc54ba049b1e40dd174308c923f`。

## 已证实的结果

完整绿色套件为 **aster-core 220 项通过、OSTD 221 项报告通过**。OSTD 保留 3 项 VMX 条件不可用的软跳过，因此合计报告数为 441，**实际执行下界为 438**。新增 19 项 usage 测试全部出现一次并通过；绿色测试名集合严格等于 #203 的原 201 项加这 19 项，未删原测试。原始串口中的测试开始、唯一终态、汇总、零过滤与 QEMU 退出 33 均已独立读取。

7054 个源文件逐项核对路径、模式、Git blob、大小和 SHA256，并独立重新计算 Git tree；普通启动前、启动后、guest 后及七次负控前后的候选快照一致。七个负控各运行完整 220 项，精确失败数为 **3 / 4 / 3 / 1 / 4 / 1 / 2**，每项失败名字均与固定源码中的预期相同，没有额外失败、跳过或过滤。每个负控仅改变声明的一个生产文件。声明 patch 与产物中的实际 applied diff 均只应用到临时文本副本，所得 blob、大小、SHA256 与负控快照一致；七个负控 tree 也重新计算相符。

绿色 core、OSTD、ordinary 的 3 个内核 ELF 与七组保留的绿色/负控共 14 个 ELF 均经过流式字节哈希。负控保留原 QEMU 65 与原 gate 1，没有超时。ordinary QueryAbi 的 14 个记录标记和四个 disabled 操作均与原始 serial 一致。未执行任何产物中的代码或 ELF。

## 官方执行与原始失败

2026-10-19 **11:17:31 UTC** 的精确读取显示最终 4d 的五项检查全部成功；A06 run `39240728276`、job `118020615962` 于 **10:53:58—11:13:24 UTC** 执行，23 个记录步骤全部成功。当时 PR 已 Ready、open、未合并且 mergeable_state 为 clean；这只是有时间界限的快照，不冒称之后的合并状态。

唯一官方 artifact 为 `12182038203`，**154,979,607 字节**，SHA256：

`ef5d93159c1663fb30d3cf8e39e969525bbfa03b4fedc4db10ef4c87b035d655`

ZIP 的 1172 个成员无重复或不安全路径，CRC 全部通过。原 ZIP 不进入本次 Git 交付；精简选集保留可复核的原始 JSON/serial/patch 无损压缩字节及源、ELF、成员身份。

首个 f966 提交的 G0 失败仍保留：原日志为 36 项 host spec 测试、1 项旧 source-string 断言失败。该断言仍要求旧调用，而新 typed ns 路径调用 `owner.charge(from, until)`。最终 4d 相对 f966 只调整该 host source guard，生产、工作流与七个 patch 没有改变，最终成功来自 4d 自己的新执行。

## 范围与入口

本包不替代另一位审查者对 full32 / SCM27 / NOFILE37 / CPU 数值与阈值的独立语义报告。内核 fixture 的通过也不扩大为真实跨 CPU 物理调度、A10、原 Objective/Operations owner、G1-c/d、ARM/移动设备或原始 Asterinas W1 资格。QueryAbi 中 native grants、native resource effects 与 Hepta durability 仍为 false。

`SUMMARY.json` 是简明机器摘要；`green-independent-review/review.json` 与 `negative-independent-review/review.json` 给出完整复核方法、失败集合与边界。`publication-selection.json` 列出允许复制的文件，`files-manifest.json` 对每份成员绑定大小与 SHA256。`publication-raw/` 是原件的无损 XZ 副本，内部身份和上游源字节均可复核。临时签名下载 URL、file_uri/file_id、下载配置、ZIP/partial 和 ELF 均排除。
