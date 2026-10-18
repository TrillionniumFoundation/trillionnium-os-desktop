# R7 历史材料恢复与缺失清单

本目录保存工作区维护后能够逐字节恢复的 R7 材料。**这是历史证据恢复，不是新一轮构建、原版 Hepta 运行或截图验收。** R7 产品源码已经随 [PR #192](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/192) 的祖先历史合入；[PR #190](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/190) 已关闭并标记 merged。当前产品事实应读取 [STATUS](../../../docs/STATUS.md) 和 [R8 实际 Objective/Desktop 证据](../2026-10-18-objective-desktop/README.md)，不要把 ZIP 内旧文档覆盖到新主干。

## 恢复结果

| 材料 | 可直接核验的结果 | 仍缺失的部分 |
| --- | --- | --- |
| R7 最后一个本地证据提交 | [retained-r7-text.zip](retained-r7-text.zip) 保留 864 个原 UTF-8 文件，共 5,026,251 原字节；832 条可用的原 SHA 清单记录全部相符 | 原 899 文件提交中的 35 个二进制路径、32 个独立 Git blob 未恢复，其中 22 个 PNG 路径和 13 个 gzip 路径 |
| A06 独立历史交叉检查 | [六份原始 JSON 的压缩包](a06-retained-source-payloads.zip) 保留 cc1/64f/d22 三份完整 Git-data payload、原独立审查和恢复收据；三份 payload 的旧字节 SHA 全部相符 | 另有 13 个 gzip 路径、11 个独立 blob 未恢复；没有重新构建或合并第二份内核实现 |
| R7 ARM 官方 CI | [ARM 恢复目录](arm/README.md) 找回同一 artifact `12125674093` 的原 ZIP、完整 job 原字节和日志 gzip；28 条源码 SHA / 25 个固定文件重新只读核对通过 | 旧归档整理文件不全，使用明确标注的新恢复索引；87 MB ELF 包未下载，也未独立复验其中的 ELF 字节 |

上述两组缺失合计为 **48 个不同路径、43 个独立 blob**。具体原路径、Git SHA、大小和可用的原摘要分别见 [R7 逐文件恢复清单](recovery-manifest.json)、[二进制原来源绑定](metadata/blob-preupload-source-binding.json) 和 [A06 恢复清单](a06-recovery-manifest.json)。新截图、重新压缩出的替代日志或新的测试结果均不能填充这些历史空位。

## R7 原文与截图边界

最后一个未发布的本地证据 commit 为 `00b0db70a31028012b5e00a2b14dc1d1249bb933`，预期 tree 为 `b518a9c491568ae82d0dd8c1e4a7e97db7fe15c0`，父提交为 `560f16c26dce32b50379dbfd26ffc291b658d303`。本目录没有重建该完整 Git tree。原发布 payload 的元数据保存在 [root-payload-meta.json](metadata/root-payload-meta.json)。ZIP 的每个成员由原 payload 的字符串直接编码为 UTF-8 字节，没有经文本补丁工具重写换行。

`retained-r7-text.zip` 为 **1,550,587 字节**，SHA-256 为 `7719dc40f5a6bf32bde432e80ba271d3b897234802419ae1e292fd8c438a0013`。恢复时逐个重新读取全部 864 个 ZIP 成员并校验 SHA 和 CRC。这里的“832 条原 SHA 相符”是原始清单中可用记录的分母；其余文字材料不凭此数字冒充已有独立原始摘要。

R7 105 项 UI 测试、可信传输测试、实际工作区输入/导出及 capture03 的当时记录与审查文本都保留在 ZIP 中。**其中 R7 原 PNG 目前不可供重新打开验图。** [恢复的 A10 审查说明](metadata/a10-final-doc-review-recovered-notes.json) 是诚实标注的恢复记录，不是当时未成功写出的最终审查 JSON。后续 R8 的三张原版 Runtime PNG 已在主干单独归档，绑定 R8 自己的实际源码、ELF 与进程；不能拿它们充当缺失的 R7 工作区图片。

[预上传状态](metadata/blob-preupload-recovery-status.json) 保留没有已确认上传二进制的事实；[首个 blob 读回](metadata/first-blob-readback.json) 返回 404。此前长时间没有返回的 GitHub 写请求不能称为成功，也没有收到“自动审批拒绝”的结果。

## A06 历史材料

[a06-retained-source-payloads.zip](a06-retained-source-payloads.zip) 为 **242,341 字节**，SHA-256 为 `5e39da0f59ff43103e5f8f61efbee4cf4bfddd5ad6df0a04235f5f0c4b01803b`。其六个文件各自摘要见 [a06-recovery-manifest.json](a06-recovery-manifest.json)。三份原 JSON 包含完整源字符串、父提交/tree 关系与原缺失二进制引用；保存这些 JSON 不等于这些本地 commit 已发布到远端。

另将原 d22 payload 中的 [64f 客体 serial.log](a06/original-64f-guest-serial.log) 直接按原 UTF-8 字节展开：17,532 字节，SHA-256 `631c794425ca8d6326cc9b1479f7e01243b5aa4a02041ddc588ed64f0e1410de`。[原独立主干去重审查](a06/a06-main-dedup-independent-review.json) 和 [恢复收据](a06/recovery-receipt.json) 保留来源与资格。可选文本补丁展开目录中两个日志发生过 CRLF 归一化，因此该目录没有被纳入本包；原始 JSON 中的原换行仍完整。

该历史 A06 157 项客体结果属于其实际 64f 源码和有限测试对象。主干先后已有 #188 尾账修复、#191 奇数周期测试 oracle 与 #195 非法 `cpu.max` 输入修复。恢复这组历史材料不倒退主干、不重新合并替代实现，也不授予生产调度、SMP 或 Hepta/HOS2 效果链新资格。

## 核验与使用

在本目录执行以下命令可核对当前恢复包的物理文件：

```sh
sha256sum -c SHA256SUMS
python3 verify-recovery.py
```

核验程序只读取当前归档，检查 ZIP 成员、逐文件摘要及缺失清单的一致性。它不下载来源、不运行产品，也不会把缺失材料标为通过。若需查看旧源码/文档，应将 ZIP 解压到单独的历史目录；恢复清单中没有原件的路径保持缺失。
