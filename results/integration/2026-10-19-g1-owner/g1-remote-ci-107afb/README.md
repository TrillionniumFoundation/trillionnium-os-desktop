# 原 0c 基线的最终头 107afb：六门禁及实际产物接受

此目录绑定 `107afb7436ca17177262fdfef2e6b5dfee13597a` / tree `65ddb50cd303f3c43a8226141c5298dca369db5d`，与本地 bccb 同树，执行基线为 0c。[精确头审查](exact-head-ci-review.json)在 03:45:11 UTC 的原 API 上确认六个 check 均 completed/success；[host 原始产物审查](host-artifact-review.json)与 [A06 全面产物审查](a06-artifact-review.json)分别完成，blocking findings 均为空。

| 实际门禁 | 结论 |
| --- | --- |
| G0 host-contracts | run `39195437870` / job `117877088393`，20 个步骤全部成功。实际 checkout 为 `1f6d2ea7d1ba1e0044d3d9dce8f36247b884be81`，tree 与 107 相同。八个候选 runner 宿主回归在正常/优化模式各出现一次；实际原 [job log](g0-job-117877088393.log)保留所有 suite 和 Rust/Clippy/rlib 输出。 |
| A03 exact-native-models | run `39195437840` / job `117877088641`，10 步成功。13 个 default-shim 和 6 个 public-backend 模型通过，严格 Clippy 保留；allocator 确实进入运行，26 个原事件包含 19 条不同的零分配 scenario，另有 4 controls、1 failure_control、1 summary、1 acceptance，没有再把“进入驱动”当成运行成功。原 [A03 ZIP](a03-native-models-39195437840.zip)及 [成员清单](a03-artifact-members.json)直接交付。 |
| A06 exact-kernel-ktest | run `39195437891` / job `117877088598`，03:35:56–03:43:01 UTC，12 步成功。原 artifact `12162141476`、[完整日志](a06-job-117877088598.log)和逐字节复核保留。 |
| A01 host-evidence、CodeQL、Analyze python | 原 API 均 success；不把这些检查计为新增 QEMU、设备或独立内核测试。 |

A06 有 **8 次真实 x86 QEMU guest**：OSTD、core、普通 boot、QueryAbi，以及原 1/2 vCPU quota 各两次。core 179、OSTD 221，报告共 400 passed；其中 3 个 VMX/EPT 路径 soft skip，实际执行下界 **397**。10 项新 G1 owner 回归和 14 个精确 QueryAbi/BOOT marker 各通过一次。四个合法形状的其他操作继续 `EOPNOTSUPP`，生产授权未启用。

本次 1 vCPU 受限值 **0.900%、0.819%**，2 vCPU **0.826%、0.875%**，均满足原 3% 上界。它们只证明四次短时 leaf profile；不授予一般 SMP、BOOTTIME/N0、持续负载或 Hepta 设备效果资格。原 ZIP 中有 7 个 ELF 成员、6 组不同 ELF 字节，均按本次来源核对。

三个 **5,851 文件**全量 source snapshot 在普通 boot/QueryAbi 区间相同，独立逐 Git 对象复核且该区间结束 clean。它们不覆盖每次 ktest 或后续所有 quota 的全树区间；最后 cleanup success 不另记为独立 Git clean 测量。ktest 实际生成锁原件已归档并比较；普通产品 204 包生成锁只有固定 runner 测量，没有独立原始副本。旧本地残留的写者仍未知，f744/463f 的原失败记录保持不变。

## 冻结材料与原 ZIP 恢复

[原冻结清单](107afb-frozen-files.json)的 20 份材料与清单自身共 **21 个文件、20,572,542 字节**；[复制收据](../review/g1-remote-ci-107afb-copy.json)逐份核对原 source 前后及副本。原 A06 ZIP 为 **18,335,208 字节**、SHA256 `593abd9f59ece10daebe4926f6c6cfc8965c622f62dadb94c04feaaadad375bd`，含 **76 个成员、44,269,138 字节未压缩内容**。

Git tree 以 12 个分片交付大 ZIP，原清单保持恢复包的身份。恢复命令为：

```bash
python3 -I results/integration/2026-10-19-g1-owner/review/restore-r10-archives.py \
  --manifest results/integration/2026-10-19-g1-owner/g1-remote-ci-107afb/archive-parts.json \
  --output-root /tmp/r10-ci-107afb
```

从该输出目录的 `a06-exact-kernel-ktest-39195437891.zip` 解压后，按原 `_temp/` 和工作区尾部结构阅读 raw 收据、串口和 ELF。[运输收据](publication-transport.json)证明实际空目录恢复的整 ZIP 字节相同，前后所有 76 成员 size/SHA/CRC 独立验证。恢复程序不会覆盖不匹配的目标。

交付 helper 首轮使用旧成员清单的 `members` 字段；本组原清单使用 `files`，因此在 ZIP 成员校验前出现 [KeyError 原日志](transport-initial-member-schema-failure.log)。修正只接受两种已观察 schema 的同义列表，重新校验已经生成的原分片，再实际恢复并完成全部成员验证。原 manifest、分片、ZIP 均未修改；这次交付工具失败不是产品或 CI 失败。

随后 e15 主干更新与 G1 合成 remote 1c054。**本包的六项成功仅属于 107/原基线，不代替新组合的 CI 或 PR merge。** 新组合的 6,397 文件源与产物另有独立记录。
