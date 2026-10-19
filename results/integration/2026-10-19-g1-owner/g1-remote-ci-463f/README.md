# PR #197 中间头 463f：G0/A06 成功，allocator 前置 Clippy 失败

固定远端 `463f70e36df6571faf6db45975d433ca10b0ddf6`，tree `0218fa196b3ebb7a3f91c77906ab4ce30a67afe8`，与本地 `bc778b6b8114e5017a467c0566f5777d85abafaf` 同树。它修复了首个 f744 上的两个过时宿主契约，以及 Loom manifest 的已知 `cfg(ktest)` 登记；原内核、os-control 和 build 输入保持前一候选字节。

[原冻结清单](463f-frozen-files.json)固定 11 份材料及清单自身，共 **12 个文件、19,145,449 字节**，未改写第一头 f744 的记录。完整结果见 [intermediate-head-review.json](intermediate-head-review.json)。

| 门禁 | 本次实际结论 |
| --- | --- |
| G0 host-contracts | **success**。保留 [job log](g0-job-117874197565.log) 和精确头检查状态；不把这项成功倒写给首个 f744。 |
| A03 exact-native-models | **failure**。13 个 default_shim 与 6 个 public_backend 模型均真实通过，12 个 Loom 输入逐 Git 核对。随后 allocator fixture build/fmt 通过，严格 Clippy exit 101：其独立生成的 os-control manifest 仍未登记 `cfg(ktest)`。原 [job log](a03-job-117874197619.log) 及 [A03 原小 ZIP](a03-native-models-39194495110.zip) 均保留。 |
| A06 exact-kernel-ktest | **success**。已取得原 [job log](a06-job-117874197488.log) 与原 A06 ZIP，核对 archive 安全、CRC、所有成员 SHA、实际 QueryAbi 标记及三个 source snapshot 的字节相等。 |

allocator 的报告中 `current_check_executed=true` 只表示进入检查驱动。其运行前 Clippy 已失败，**`current/execution.json` 没有 `run` 记录，也没有 current_zero 结果**；这不是一次预期的 allocator 负对照。随后最终源码另在生成 manifest 补齐已知 cfg 登记，没有关闭严格警告门禁，其结果应查最终头记录。

A06 原 ZIP 报告 core 179、OSTD 221（3 soft skip、实际下界 218）、14 个精确 QueryAbi/BOOT 标记各一次。QueryAbi 三个 5,851 文件 snapshot 相同，SHA256 `91caf62fd96a0837c2ed224fbe200666bc8c3ed61138af72439bdb71556d21ad`；绑定 remote 463f/tree0218，产品 ELF SHA256 `f8785d9371f27b1f5e9ccd40da66ea25823ca50bfc7c431a89f20f88a45c4681`。

**本中间头的独立复核范围有限：**它完成实际 marker/report、snapshot 字节相等和所有 ZIP 成员完整性；没有把 f744 的完整逐 Git 源文件/ELF/锁审查资格借给该头。完整最终头复核另行追加，原 A03 failure 保持不变。

## 完整 ZIP 的传输与恢复

原 A06 ZIP `a06-exact-kernel-ktest-39194495150.zip` 为 **18,334,024 字节**，SHA256 `f5d8ac6cad22e90fc1ce3102447b1487eb6962ae95a4971c118edd9513115018`，有 **76 个成员、44,268,900 字节未压缩内容**。交付 Git tree 只保存它的 12 个连续字节分片，原 ZIP 清单按恢复后的完整原件保持；原 A03 小 ZIP 15,017 字节则直接交付。

从仓库根目录恢复 A06 原 ZIP：

```bash
python3 -I results/integration/2026-10-19-g1-owner/review/restore-r10-archives.py \
  --manifest results/integration/2026-10-19-g1-owner/g1-remote-ci-463f/archive-parts.json \
  --output-root /tmp/r10-ci-463f
```

[A06 成员清单](a06-exact-kernel-ktest-39194495150.members.json)与 [A03 成员清单](a03-native-models-39194495110.members.json)分别对应自己的原 ZIP；内部材料在各自解压目录阅读，不是 primary 旁边已存在的本地路径。[复制收据](../review/g1-remote-ci-463f-copy.json)证明原 12 文件逐字相同，[运输收据](publication-transport.json)记录实际空目录恢复和前后 76 个 A06 成员 size/SHA/CRC 独立核验，没有执行任何产品。

后续本地又可见原大 ZIP 副本的 [环境观察](../review/transport-body-reappearance-observation.json)单独保留，写者未知；最终以明确 Git index/tree 清单排除本体，原分片和 producer manifest 均不改变。
