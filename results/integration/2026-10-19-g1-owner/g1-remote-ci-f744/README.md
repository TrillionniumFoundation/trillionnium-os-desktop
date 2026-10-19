# PR #197 首个远端头 f744：失败门禁与 A06 原始产物

此目录只描述固定远端 `f744fb248a6d264676d0b892d21d6c4582d72d0f`，tree `4e42c3833746cd2684d0a75020d73286820457e6`，与本地普通候选 4e 同树。[原始冻结清单](f744-frozen-files.json)的 14 份材料和清单自身共 **15 个文件、20,360,877 字节**均按原字节保存。大 ZIP 在交付 Git 树中以 12 个连续字节分片保存，原清单仍描述恢复后的完整包，未改成新的内容清单。

## 实际门禁

| 门禁 | 真实结果与证据 |
| --- | --- |
| G0 host-contracts | **failure**。35 项 Python wire/spec 检查出现 1 failure、1 error。旧 preflight 测试仍调用已移除的 `prefetch_locked_upstream`；旧 ELF 输出测试将源码出现次数固定为 2，而新增实际 ELF 留存后为 3。原 [job log](g0-job-117870536000.log) 保留。后续 Rust/Clippy、其余 spec、A05、候选 runner host fixtures 等步骤没有因这些失败而执行。 |
| A03 exact-native-models | **failure**。default_shim 的 13 个 Loom 模型真实通过；其后严格 Clippy 因生成/引用的 `resource_state.rs` 使用 `#[cfg(ktest)]`，但宿主 manifest 未登记该名字而 exit 101。其余 backend 和 allocator 阶段没有完成。原 [job log](a03-job-117870537020.log) 保留。 |
| A06 exact-kernel-ktest | **success**。run `39193294713`、job `117870536573`，03:09:02–03:15:53 UTC，12 个步骤均成功。已取得原 ZIP 和 [完整 job log](a06-job-117870536573.log)，并独立核验实际字节，不能只凭绿勾作运行结论。 |

[首头 CI 审查](original-head-ci-review.json)保留具体错误、未执行步骤和观测时间。G0 job 实际 checkout 为 `pull/197/merge` 的 `0451679b4745e6136a043e0f0605039f0765c653`；对应 check head 是 f744。A03/A06 的源码身份分别按其原日志、收据和产物核对，不把 prospective merge commit 当成 PR 已合并。

## A06 原始产物独立审查

[a06-artifact-review.json](a06-artifact-review.json)完整复核原 artifact `12161280823`。原 ZIP 为 **18,333,821 字节**，SHA256 `bf5f89c4ef49d1be7c2e98240737982d9c38e5a3c787dc9428f475ae9f526135`，含 **76 个成员、44,268,904 字节未压缩内容**；[成员清单](a06-artifact-members.json)逐项固定 size、SHA256 和 CRC。审查取得 7 个 ELF 成员、6 组不同的 ELF 字节，核对真实源码、锁、串口、QEMU 和 initramfs；最终 blocking findings 为空。

| 实际客体 | 得到的证据及限制 |
| --- | --- |
| OSTD | 报告 221 passed、0 failed/filtered；3 项 VMX/EPT 路径提前 soft skip，实际执行下界为 218。 |
| aster-core | 179 passed、0 failed/filtered/soft skip；10 项 G1-a owner 回归各执行一次。 |
| 普通非 ktest boot | wrapper 0，raw QEMU 33；固定实际产品 ELF 启动成功。 |
| 同一产品的 QueryAbi | raw QEMU 33，14 个完整行标记各一次；四项合法形状的禁用操作仍返回 `EOPNOTSUPP`。能力授予及设备效果不启用。 |
| 原 1 vCPU quota profile，两次 | 受限结果 1.0%、1.0%，unlimited 约 99.69%、99.68%，均满足原 3% 上界。 |
| 原 2 vCPU quota profile，两次 | 受限结果 0.85%、0.953%，并行 unlimited 约 198.55%、198.70%，均满足原 3% 上界。 |

这是真实 **8 次 guest 调用**，不是 8 套完整内核测试。两个 ktest 目标共报告 400 passed，含 3 soft skip，实际执行下界为 397。注册图中的 542/240 项不是本轮执行分母。四次 quota 运行是短时 leaf profile，没有建立一般 SMP、跨代际归账、BOOTTIME/N0、Hepta 授权或持续负载资格。

普通产品 ELF SHA256 为 `f8785d9371f27b1f5e9ccd40da66ea25823ca50bfc7c431a89f20f88a45c4681`；实际 CI probe SHA256 为 `54cdac38140b65dc376cf3564a1f4689e6f9fbe0661af0397c3db959d875b6f4`。注入 initramfs SHA256 为 `e2a3a01b0a1e4ae1d92e3ae6305fdf6abd14bd9cd0657b16d7367bc9c8fbc047`；25→26 个成员，只改 init 并加入 `bin/hos2-queryabi`，原 initramfs 未改。它们是本次 CI 产物，不能以相同来源 tree 把本地 4e 的另一组 ELF/probe 哈希替换过来。

### Source gate 的精确范围

普通 boot 与 QueryAbi 区间的三个 source snapshot 各有 **5,851 个文件**，逐字相同。独立审查将它们与远端 Git 对象逐文件核对，重新计算 4,818 个唯一 blob、89,415,162 个 tracked 字节。该区间的严格 source gate 接受且结束时 clean，未重现本地 canonical OSDK 残留。

这些 snapshot 是 **ktest 完成之后、普通 boot/QueryAbi 前后**取得，不是每次 ktest 或后续四次 quota 运行的全树快照。另有 11 个 ktest 构建输入逐 Git 核对。最后 Actions cleanup 显示 success，也不另充当所有后续步骤结束后的独立 Git clean 测量。CI 未重现本地残留，并未查明原本地写入者，旧 attempt01/02 和 ENV-1 观察继续保留。

core/OSTD 的实际生成锁在 ZIP 中，可逐字比较。普通产品 204 包生成锁只取得固定 runner 的测量及 committed minimal lock 比较，**没有对应生成锁原件 ZIP 成员**，不能声称对不存在的原件做了独立复核。独立审查初版仅 LF 的计数正则未接受 OSTD 的 CRLF；修正解析后完整审查通过，原串口和产物未改，也未重新运行产品。

## 恢复原 ZIP 与交付核对

[archive-parts.json](archive-parts.json)固定 12 片的顺序、大小、SHA 和完整原 ZIP 身份。原 ZIP 本体不纳入交付 Git tree；恢复后它与冻结清单中的文件完全相同，没有重新压缩。请从仓库根目录执行：

```bash
python3 -I results/integration/2026-10-19-g1-owner/review/restore-r10-archives.py \
  --manifest results/integration/2026-10-19-g1-owner/g1-remote-ci-f744/archive-parts.json \
  --output-root /tmp/r10-ci-f744
```

实际 ZIP 位于该输出目录的 `a06-exact-kernel-ktest-39193294713.zip`，然后可在新的审查目录解压。原 JSON 内的 `_temp/`、工作区和 artifact 成员路径在解压后的目录下阅读，不假定 primary 旁边已经存在这些文件。恢复程序不会覆盖不匹配的目标。

[复制收据](../review/g1-remote-ci-f744-copy.json)证明原 15 文件的 source 前后与副本一致。[运输与实际恢复收据](publication-transport.json)记录封闭命令中仅凭分片从空目录重建原 ZIP，并在恢复前后独立核对所有 76 成员 size/SHA/CRC。后续工具调用中在本地 delivery 又观察到原 ZIP 副本，原因未知；此 [独立环境观察](../review/transport-body-reappearance-observation.json)不改原冻结材料，最终以显式 Git index/tree 选择确保仅发布分片。

后续 463f 和最终 107afb 的检查各在独立目录记录。此包不宣称 PR 全绿或已合并，也不把新头修正追记为 f744 的成功。
