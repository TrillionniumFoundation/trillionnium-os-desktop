# 最终 e15 + G1 组合：1c054 精确头 CI 与实际产物

**此包是本轮最新源码的实际运行资格。**远端 `1c05412e2b340bbc8cd2b8a3389ae0ecce538991` / tree `2b873aa43445c8a02351f5900074a38c6fa4820d`，与本地 `1ca738c6310c50565804c2ea2a5d413a74bbe80a` 同树，执行基线为 e15。远端 parents 为 107/e15，保留新 Runtime/进程边界、A04 主干手册及 G1 改动；不能使用旧 107 的 5,851 文件计数。

[精确头审查](exact-head-ci-review.json)在 03:56:00 UTC 实读确认六个普通 checks 全 completed/success。其 03:59:00 PR 快照仍为 open/unmerged/clean；随后 **03:59:41 UTC 已由另一位维护者合入 main `71ce079c3218a8692476e4113b60c9d2c0d2a172`**，parents 为 e15/1c，tree 与本包完全相同。[后续真实 merge 收据](../source-publication/main-sync/observed-merge-receipt.json)单独追加，没有将冻结 CI 快照中的旧 PR 状态改写。该观察不是一次新的 post-merge CI 或产品运行。

## 本头实际门禁

| 门禁 | 真实结果 |
| --- | --- |
| G0 host-contracts | run `39196471000` / job `117880228265`，20 步全部成功。实际 checkout `5f5e5bfc6e6679a2328c86914455b458676826e7` 的 tree 精确相同。八个候选 host 回归在普通与优化模式各执行一次；原日志、source 和检查见 [host-artifact-review](host-artifact-review.json)。 |
| A03 exact-native-models | run `39196471043` / job `117880228851`，10 步成功。13 default-shim + 6 public-backend Loom 模型、严格 Clippy 通过；allocator 实际执行，26 个原事件包含 19 条不同的零分配 scenario，另有 4 controls、1 failure_control、1 summary、1 acceptance。原 A03 小 ZIP 及成员摘要均直接交付。 |
| A06 exact-kernel-ktest | run `39196471075`，attempt 1，job `117880228659`，03:49:09–03:55:04 UTC，12 步成功。[完整 A06 审查](a06-artifact-review.json)已核对真实 ZIP、源码、ELF、锁、initramfs、串口和 QEMU。 |
| A01 host-evidence、CodeQL、Analyze python | 均 success；它们不另计为 guest、设备或内核测试。 |

A06 有 **8 次真实 x86 QEMU guest 调用**：OSTD、core、普通非 ktest boot、同一产品的 QueryAbi，以及原 1/2 vCPU quota 各两次。core **179 passed**，OSTD **221 reported passed**，其中 3 个 VMX/EPT 路径明确 soft skip；总报告 400、实际执行下界 **397**。10 项新 G1-a owner 回归和 14 个精确 QueryAbi/BOOT 标记各通过一次。四项合法形状的其他 HOS2 操作仍拒绝为 `EOPNOTSUPP`，生产 private bind 未启用。

本次 1 vCPU 受限值 **1.000%、0.910%**，2 vCPU **0.905%、1.000%**，满足原 3% 上界。四次短时 leaf profile 没有建立完整 SMP、运行任务跨 controller 代际归账、BOOTTIME/N0、完整五操作、Hepta K↔D 或真实设备控制资格。宿主 Loom/allocator 与这些 guest 结果分别报告。

## 当前 6,397 文件与 source gate 范围

最终 source tree 与普通 boot/QueryAbi 的三个归档 snapshot 均有 **6,397 个 tracked 文件**，三份 byte stream 相同，SHA256 `ec4f3e78113bdca4e64f174f7553a9ef004b62a70f2d1748c509ec35fc16a3ae`。独立审查逐文件核对 Git 对象和 mode，重新计算 **5,188 个唯一 blob、100,508,712 字节**。该闭合区间严格 source gate 接受，结束时 clean，未重现本地 OSDK 残留。

snapshot 取得于 ktest 之后的普通 boot/QueryAbi 前后；它不代表每次 ktest 或后续四个 quota 区间都做了完整 source snapshot。最后 Actions cleanup success 不另充当所有步骤之后的新 Git clean 测量。ktest 的实际生成锁原件已归档并逐字比较；普通产品 204 包生成锁仅由固定 runner 测量及 committed minimal lock 比较，没有独立 raw 副本。原本地残留的写者仍 unknown；正常 CI 成功没有否定旧 attempt01/02 的失败。

## 原材料及 12 片恢复

[原冻结清单](1c054-frozen-files.json)的 19 份材料与 manifest 自身共 **20 个文件、20,854,647 字节**。[复制收据](../review/g1-remote-ci-1c054-copy.json)逐文件核对 source 前后及副本。原 A06 artifact `12162515747` 为 **18,446,493 字节**，SHA256 `d9623e880bf559392f92c6bc9359a02629b6ff548e853e9f05cf1598b711fbbd`，有 **76 个成员、44,759,885 字节未压缩内容**，包含 7 个 ELF 成员、6 组不同 ELF 字节。

Git tree 只发布大 ZIP 的 12 个连续字节分片；producer manifest 保持原字节，原 A03 小 ZIP 16,550 字节直接交付。恢复原 A06 ZIP：

```bash
python3 -I results/integration/2026-10-19-g1-owner/review/restore-r10-archives.py \
  --manifest results/integration/2026-10-19-g1-owner/g1-remote-ci-1c054/archive-parts.json \
  --output-root /tmp/r10-ci-1c054
```

原 ZIP 位于该输出目录的 `a06-exact-kernel-ktest-39196471075.zip`；解压后从原 `_temp/` 和工作区相对结构读取完整串口、snapshot、ELF 与收据。primary 旁边没有冒造对应 raw 路径。[运输收据](publication-transport.json)记录实际空目录恢复，原 ZIP 整体和全部 76 成员 size/SHA/CRC 均复核一致，无重新压缩或产品执行。

f744、463f 的失败、107 的旧基线成功，以及本轮合并后的观察继续按各自固定来源保存。本包只接受上述精确 tree 的已运行范围，不授予后来提交、post-merge workflow、一般硬件或移动设备资格。
