# #203 历史 ELF 身份纠正

**旧 #203 的 1/2 vCPU 原 probe 收据绑定同一普通内核。** 此小包纠正 R11 报告中“旧 SMP2 使用不同 ELF”的表述，保留三份身份收据的原 ZIP member bytes；另将旧四项 CPU 占比核对到四份现有结果收据及其记录的样本。

## 1. 固定来源与纠正结论

原来源为 PR #203 的 head `775061af51e6ee91fce290d5855e24a276292e14`、tree `afeb331293025ca7a63678167211de109e997110`，A06 run `39219341861` / artifact `12172041618`。官方原 ZIP 为 **153,302,416 字节**，SHA-256 `7ec32457b02fe4fa897b32ce937f2c34d9cd0bfae034da4c5f74626ecfc539bf`。这一整包身份沿用已冻结的 [官方恢复收据](../pr203-restored-artifact/archive-recovery.json)；本纠正核对当前大小、成员数和指定成员，不冒称新做全部归档散列或 CRC 扫描。

| 原始收据 | 身份字段 | 值 |
| --- | --- | --- |
| [ordinary QueryAbi](raw/_temp/a06-queryabi-candidate/result.json) | `kernel_elf_sha256` | `e1d5ec0f294d0fffe1c887f92e2b564aa9d967753e0d6f815894ca6490c779c5` |
| [1 vCPU probe](raw/_temp/a06-probe-1vcpu/result.json) | `candidate_sha256` | 同上 |
| [2 vCPU probe](raw/_temp/a06-probe-2vcpu/result.json) | `candidate_sha256` | 同上；`configured_vcpus=2` |

本次从原 ZIP 流式读取 `_temp/a06-queryabi-candidate/product-kernel.elf`，得到 **8,288,528 字节**及上述相同 SHA-256。它与三份原收据的身份一致。建议报告采用：

> 旧 #203 的 1/2 vCPU 原 probe 收据绑定同一 e1d5ec0f… 普通内核；共享 target ELF 不能替代这些原输入记录。这些有限配额结果仍不提供完整 SMP 资格。

## 2. 共享 target 文件不代表原 quota 输入

同一归档内的 `trillionnium-os-desktop/trillionnium-os-desktop/kernel/asterinas/target/osdk/aster-core/aster-core-osdk-bin.elf` 流式结果为 **9,842,424 字节**、SHA-256 `5b01239ef330608a6faba9814707a04a34fc0a174eb3ec6cd810446466f197f3`，确实不同于已保存的普通内核。

共享路径在归档时保留哪份输出，不能独立证明某次较早的 quota 调用用了它。这里不指认其具体生产构建，也不证明另一次 SMP=2 构建产物本体与 ordinary 相等；只纠正实际 probe 收据和已保存 ordinary ELF 的身份对应。两份 quota 原收据仍明确 `smp_qualified=false`、`hepta_hos2_qualified=false`。

## 3. 旧四项 CPU 值的有限核对

这部分只读取现有 `result.json` 的 `cpu_ns`、`wall_ns` 与 `cpu_percent`，用 `100 × cpu_ns / wall_ns` 核对报告保留的六位小数；没有重新解析串口或重跑计时 oracle。

| period / 模式 | 收据样本核对后的占比 | 原上限 | 原收据 |
| --- | ---: | ---: | --- |
| 100000 µs / read-only | 0.899889% | 1.2% | [result.json](raw/_temp/a06-cpu-config-100000-read-only/result.json) |
| 100000 µs / same-value | 0.878188% | 1.2% | [result.json](raw/_temp/a06-cpu-config-100000-same-value/result.json) |
| 2000 µs / read-only | 46.246698% | 52% | [result.json](raw/_temp/a06-cpu-config-2000-read-only/result.json) |
| 2000 µs / same-value | 46.298188% | 52% | [result.json](raw/_temp/a06-cpu-config-2000-same-value/result.json) |

四份收据均记录 quota 1000 µs、duration 4 s，内核 SHA 同为 `e1d5ec0f…`。本次只验证数字及输入身份一致，不扩展原 CPU、完整 SMP、严格 1% SLA、physical-switch、HOS2 或 Hepta 资格，也不扩展其他旧 core/OSTD、七负控、full32 或设备审查。

## 4. 文件与范围

[review.json](review.json) 给出原成员路径、大小、SHA-256、两份 ELF 的流式身份、四组记录样本及明确限制；[files-manifest.json](files-manifest.json) 绑定本包除清单自身以外的全部文件。`raw/` 保留七份 JSON 的原 ZIP 成员字节，没有重新序列化或改换末尾换行。

本包没有复制大型 ZIP 或 ELF，也没有修改报告、旧冻结包或 Git 工作树。它是新做的有限历史纠正，不是假装恢复旧派生审查文件，也不是新产品测试。
