# 2026-11-04 阻塞项与实际验收台账

本文记录本轮最终组合冻结前的事实，补充 [历史状态](../STATUS.md) 与 [模块文档审计](MODULE_DOCUMENTATION_AUDIT.md)。它不改写原始失败收据，不把不同提交的成功相加成一个新版本的成功，也不授予生产、设备、合并或发布资格。

## 1. 当前判定

目前已有可编译、可打包、可实际安装的 Linux 桌面开发组合；该组合的真实 Notes 交互仍失败。失败已定位到生产入口的检查点预算，源码修复尚须在新的完整安装组合上验收。原生 Asterinas G2、连续 successor、撤销后拒绝、Android 真实效果链和物理硬件仍各有未闭合门槛。

因此，不能把本项目记录为“所有 blocker 已闭合”，也不能宣称已经具备通用桌面或手机控制产品。继续在现有 Asterinas 派生与 Hepta 原 owner 上修复和验收；本轮没有得到足以要求重建完整 Rust kernel 的结构性反证。

## 2. 已实际执行的固定 Linux 组合

| 输入 | 固定身份 |
| --- | --- |
| Desktop | `6533247104f3cdbf9c9ef68ac5369eb097467244`，tree `b361240895b1a70ac1e9ae7ce4a114e7a28f4db0` |
| Hepta | `14e2d89b3367232ec5dbe6187f09feed0f2b68d3`，tree `0e12d53adf6a13721fdb2feef0e974d903b92e85` |
| 原始证据根 | Desktop 主机 `/data/trill-organ-owner-20261104-joint/pair-65332471-14e2d89b-v1` |
| 输入收据 SHA-256 | `cc9453591ff69cd0d5b8fb6a9f446c75de0d7a2b7c72842d24221fbaa7e2d5c9` |

上述路径是受控执行主机上的证据位置，不是本仓库附带的可下载文件。源提交可通过 [Desktop PR #297](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/297) 核对；该 PR 的成功不自动覆盖后续候选。

| 实际检查 | 结果 | 准确边界 |
| --- | --- | --- |
| 原 UI 与 Root 构建 | PASS | 原默认并行 Root 测试 64 passed / 4 ignored；随后分别实际执行这 4 个 privileged fixture。 |
| Root 私有 Supervisor 诊断 fixture | PASS | 原测试 ELF 的精确复制件在 Root 私有目录实际运行；不是 Agentd 生产成功。 |
| 原 live-session 与 stale-socket 两个 fixture | PASS | 各 1 passed / 0 failed / 0 ignored，原测试条件不变。 |
| 原 seed start/resume fixture | PASS | 1 passed / 0 failed / 0 ignored；实际 App Server、首信号退出与两个 seed socket 退役均核对。 |
| 原打包、验证、安装 | PASS | 压缩包 SHA-256 `1541b2ed30dfa6a42f5ca2515db57ca97c121ca72a34d268b0c9d5934931c805`；安装器不启动服务，不授予 production-ready。 |
| GitHub host-contracts / original-owner-session / native UI | PASS | 该 Desktop 源提交的三个实际 CI 结果；不能转授后续源码。 |
| 实际 Notes GUI 操作 | **FAIL** | 仅写入 prompt intent 1 次；Send intent 与 Send ACK 均 0，没有完成效果或回读。 |
| 原进程退出核对 | PASS | Root、Session、Agentd、Shell、App Server 的 5 个实际出生身份最终均已退出；没有操作者直接杀 Rust PID。 |

关键执行收据：

- Root build：`03922b8164e892468825062c8d2334997220fb10948756b19ce2b59c98d95798`。
- Pack：`99b44687ea06cf12ac7e90c9f98358a13d7163ea83e8266903cf0d10cefa1e79`。
- Install：`739bfc70c1ca46a1bf462b97e2cce63235dacde401740b5d67749920a088ad52`。
- Seed fixture：`682a0dda682ef38f7199213acf1d3a2e98b6acea1c2054534686b0febea23c99`。
- Notes 真实失败：`8a82f88e27b1b4334596924139f5cb968dd5e4f6e268f3e87820eea353fc380e`。
- 私有 Supervisor 终态：`f1ba41c2bdced7cf3073d17fc19434d686101c0f024c03d133e11fc9fba82b0d`。

Supervisor 实际观察到 Agentd 退出码 1，以及 `original Objective sender unavailable: Objective sender input exceeds its retention profile`。对照固定来源的构造器与三个生产调用点，入口传入 10 秒，而检查点构造器接受的上限为 5 秒。候选修复保留入口的原 10 秒总预算，只把单个检查点预算取为调用方传入预算与 5 秒的较小值；没有扩大原 1,024 请求 / 32 MiB 保留上限。真实新安装组合通过前，此项状态仍为“已修源码、运行待验”。

私有诊断仅证明原有有界 ring 实际观察到的内容；不能把未记录的历史管道字节或 ring 丢失量写成零。

## 3. 本轮源码修复与各自证据

| 项目 | 已取得的证据 | 仍需完成 |
| --- | --- | --- |
| Root recovery flock | 原 dup/OFD 回归先实际 RED，显式最后 guard unlock 后原并行测试、严格 Clippy 与三个 CI 实际 GREEN；见 PR #297。 | 后续 early-error guard 在最终组合上的原测试与真实恢复。 |
| Root 私有 Supervisor 诊断 | [PR #294](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/294)，原有界 stderr/exit 观察与 6533 后继实际失败诊断。 | 最终产品启动成功；诊断文件不是成功条件。 |
| Objective 检查点预算 | 候选 `2aa218b0505a0b6f764d19c8e8aebcd445813600` 的源码及格式已审；最终集成前保持单独来源。 | 同一新 Root → launcher → adapter 的真实 Notes 和 joint round trip。 |
| V8 原供给链 | [Hepta PR #4803](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/4803) 接原 resolver；实际 Codex release 361445880 的 archive、binding、checksum 字节核对成功。 | 原 helper/App Server 真实测试；官方资产准备不等于测试成功。 |
| Bazel Rama bindgen | [Hepta PR #4804](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/4804)，`9ae63c54043fd5a5fc3e30073a675a092a8bc9f8` 实际完成 libclang 编译、SDK build/lint/test/clean-worktree。原 lock 工作流完整成功，锁文件无漂移。 | 整体 Bazel 仍有独立的旧测试依赖图、fixture action inputs 与辅助函数 lint 错误，不能记为全绿。 |
| Joint 文档契约 | 原 owner 的两份技术/开发文档已明确 fresh v1、recovery v2、完整 Current cut、持久 retirement ACK、same-ID issuer renewal 与撤销语义。 | 源码与实际安装后的行为必须一致；文档不代替运行。 |
| CI 与分支规则 | [PR #295](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/295) 补 Root 验证范围；[PR #296](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/296) 保证必需检查触发；[PR #298](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/298) 给出具体 main 规则提案。 | 代码合并与规则实际启用、读取有效规则验证，是独立未完成动作。提案文件不代表规则已生效。 |

原 `04a42923aaf8c562ad161a17a4bbf35fe883a1b5` 的 MODULE 使用了不可用的 `json.encode`，实际在依赖求值前失败；该失败保留。9ae 改用两个闭合 GNU target triple 的字面 JSON，原 lock 两次生成结果一致，不能为消除错误提示而伪造锁文件更新。

2026-11-04 后续平台核验：9ae 的 Linux SDK 与原 lock PASS 保留；同一候选的 macOS Clippy 在分析阶段仍沿 Rama build script 引入 Linux-only `kernel_headers` 而失败。原 `data/tools/env` 已有 GNU select，不能把原因简化为“忘记加条件”。后继 `c6ad59c90d80ce1f1c8932bed949ee7db71c9906` 对其余八个平台显式给出空 data/tools 集合，原 renderer 回归与格式通过，完整平台 CI 仍待验证。相关 fixture/action-input/lint 修复与 checkout 获取问题也各自保留原失败，尚不记录为整个 Bazel 验收通过。

## 4. 原生镜像优化必须同时守住语义与容量

原已接受 A39 profile 的最大值继续固定为：文件 20,138,584 字节、LOAD 20,168,704 字节、段 15,323,136 字节。旧 builder 的 8/16 MiB 门槛与 A39 闭合 profile 的门槛分别记录；不能把测量脚本退出 0 写成 builder 或客体通过。

| 候选 | 实际观察 | 决定 |
| --- | --- | --- |
| 原 `6b715d2c92ce8ab74f0829ce6926fe8dfc8d7f5f`，GNU 工具链对齐后 | 文件 20,179,992 / LOAD 20,209,664 / 段 15,351,808，仍超 A39 上限。 | 保留失败；原原子 socket 发布和 startup 阶段诊断继续按源码与运行分别验收。 |
| `1b390853e50aa2fdae2e6c68793f94742d2d667c` | 单独 inline hint 几乎没有消除重复 poll 代码，容量仍失败。 | 不把它作为有效容量修复。 |
| `02af45bf1624b4b8ce0ea8d981b903e33ec0cc07` | 文件 19,508,312 / LOAD 19,537,920 / 段 14,770,176；但真实类型诊断为原 Future 11,016 字节、wrapper 22,056 字节，越过 Tokio release 16,384 字节装箱阈值。 | **容量通过、分配行为失败，停止集成。** 诊断收据 `8010943a69636ddb6daa45ff4e25e762d80ba9a687688439fac6ce959e4a489a` 保留。 |
| `49625ed36deab3a5b9069b067aa4eaf11d6011bf` | 源码候选按锁定 Tokio 1.53.3 的 debug 2,048 / release 16,384 阈值分支；大 Future 继续原 block_on，小 Future 栈 pin 后共享普通 poll shim。 | 源码已审，真实类型布局、代码生成、栈帧、容量与最终客体尚待完成；不提前授予有效性。 |

### 2026-11-04 20:31 UTC 后续候选实测

上表保留起草时的判断。此后，候选 `49625ed36deab3a5b9069b067aa4eaf11d6011bf`、tree `c5e81e8f9ebd99260049ce4692e737b2412fe07e` 在与原 Desktop 逐文件对齐的 84 项 GNU 输入下完成了独立测量。其文件为 19,358,744 字节、LOAD 为 19,386,368 字节、最大段为 14,659,584 字节，4 个 LOAD 均在原 A39 的对应容量以内。原 legacy builder 仍退出 1，新的容量测量成功没有覆盖或改写这个旧 profile 的失败。

实际类型探针只推导函数项类型，没有创建原 owner 或运行 future：原 Future 为 11,016 字节，借用栈 pin 的转发 Future 为 8 字节；release 下两者均未进入原 Tokio 的装箱分支。实际代码生成从三个大型 poll 副本收敛为一个 50,844 字节的原 poll 与 14 字节 shim，`execute` 源码逐字保持。机器帧观察也已完成，但它只描述单函数 unwind CFA 与机器指令，不能证明整个调用栈峰值；原每角色 8 MiB 栈仍不变。

| 独立原始记录 | SHA-256 |
| --- | --- |
| 496 容量测量 | `7baa79cd0dcd92b6b0a787b0ee5480ed2694924151e549298c7b54477c00d012` |
| 实际代码生成比较 | `846c2b12d7bfba5ebf6f8174720db7023067e4a6deec93952caf59f13a5668a3` |
| 真实类型布局 | `556cd259d7cff8adc05dd7f59db07d7dcf7954af93c13ac237bf11cb034563ef` |
| 单函数帧观察 v2 | `151bb811075c55a0010465b9a056825a9138f5b1dc7be6ad3a3f3f55af859d18` |

这组记录位于 rog 主机本任务 `trill-g2-native-rog-20261104-v1/receipts`，不作为仓内附带的可下载文件。有效的净源码差分可以进入最终候选；02af 的 owning-async wrapper 仍不采用。最终 Hepta 还要重新量自己的 ELF、布局和容量，再据实际结果生成独立的闭合 profile；不能把 496 的中间 ELF 哈希、大小或测量结果填进最终组合。

后续源码生命周期审查另提出一个尚在验证的边界：496 的小 Future 借用转发可能让原 Future 在 Tokio 内部 runtime-enter guard 退出后析构，与原 owned `block_on` 的上下文不同。该问题正在用独立小 Future 做真实 Drop 对照；上面的容量和布局结果保留，不能先将它们写成析构语义已闭合或据此冻结最终 Hepta。最终修正如有发生，必须取得自己的源码与运行证据。

最终组合必须生成自己的 ELF 与闭合输入，并在原限制下完成 6 个 Root fixture、原 5 boot 正反场景。中间候选的尺寸或启动结果不能转授最终 Hepta/Desktop 源码；两条正向路径和三个负控必须保留原判定器。

## 5. 未闭合门槛及实际完成条件

| 阻塞项 | 关闭所需的实际结果 |
| --- | --- |
| 最终跨仓来源 | 一个干净的 Desktop/Hepta 组合、原 main 祖先、实际 source profile 和精确工具链/输入；全部变更冻结后再构建。 |
| 原 package / helper / App Server | 原 `just fix`、`just test`、默认 profile、功能开关、断言和 nextest 设置；真实失败先定位再修，不能凭旧 26a 失败推断新 14e 行为。 |
| 安装后的 Notes/Calculator | 同一真实生产 Root/issuer/Agentd/Core/Session 执行与独立回读；修复 10 秒与 5 秒预算后重新取得 GREEN。 |
| 两次连续 successor | 同一原 seed、fleet、signer、key 和有限 profile；两次真实恢复保持完整 Current、原请求/操作身份和持久 retirement ACK。 |
| 撤销 | Gen3 exact revoke/CAS 后原实际调用不得提交；Gen4 对已撤销原对象必须在新 authority/spawn 前拒绝。 |
| 原生 G2 | 最终 ELF、同版本 kernel/闭合 profile、原 6 fixture 与 5 boot；真实 K↔D、FinalUse、持久终态和退役。 |
| F 完整原生运行 | 原 FleetRegistry/Supervisor 的 daemon、原 store/锁/socket、实际任务和恢复；不能用进入 Rust main 或配置拒绝替代。 |
| E / A06 完整隔离与故障 | 总进程树内存、slab/reclaim/OOM、SMP/clock 故障、watchdog 与可信暂停；`cpu.weight` 的 EOPNOTSUPP 不是公平调度实现。 |
| Android 实际效果链 | 原 signer 与真实接收端，实际 retained Agentd MCP → EffectLease → FinalUse → Receiver 的任务、撤销和恢复；unsigned APK、SDK 编译和 ChatGPT connector 调用不能替代。 |
| 物理设备 / VMM / UI | 选定硬件的 IRQ/DMA/IOMMU/ACS/reset/power-loss、真实显示输入/IME、读屏 stride 与 bpp；host 模型与设备存在不能替代。 |
| 主干与仓库规则 | 按实际 CI 与合并门槛发布；启用已审规则后读回有效结果。当前规则提案不等于行政变更完成。 |
| 模块文档完整性 | 每个实际交付模块须有具体 owner、状态/接口、锁与权限、构建/运行/故障/验收入口；冻结的历史共享文档覆盖统计不等于每个 crate 都有独立完整双手册。 |

2026-11-04 候选文档复核：五个 UI crate 与 OS ABI 的六份独立入口已经具备，固定 `b7c50344a5069b0efe11ec4c28d6cf2d2bafefab` 的全部文件字节与 Git blob 一致，99 个本地目标和锚点有效。来源、各文件 SHA 与原审查收据见 [模块文档审计的本日补充](MODULE_DOCUMENTATION_AUDIT.md#2026-11-04-候选六模块入口复核)。这项覆盖证据不改写旧 main 的历史缺失统计；最终同版 runtime 另验。

同一原请求结果未知时，仅核对其原身份，不换 ID 重发效果。原 retained cut 为 1,024 请求 / 32 MiB，session 与 grant 时间边界保持不变；两个 successor 成功也不等于无限历史、自动回收、跨版本数据库迁移或断电恢复资格。

本轮最终 Rust 变更包明确包含 `codex-hepta-contracts`、`codex-hepta-memory`、`codex-hepta-agentd`、`codex-hepta-supervisor` 与 `codex-hepta-fleet`。其中 Supervisor 与 Fleet 的真实 fixture 修复也须进入各自原 `just test -p` / `just fix -p` 验证；不能仍只报三个包，也不能借原 14e 的通过结果替代新源码。

## 6. 执行资源与证据纪律

Desktop 原 35 GiB data / 20 GiB home / 48 GiB 可用内存准入继续保留。将组件测试映射到 ai395 的单一实际文件系统时，磁盘保留合计 55 GiB，内存仍为 48 GiB；没有把同一磁盘的 free 数重复计数。其他任务的进程和缓存不属于本任务清理范围。

ai395 原 helper/App runner 使用固定 Ubuntu 24.04 image、Rust 1.96.0、原版本 just/nextest、原 V8 字节及实际 source pin。其工作截止时间仍为 10,800 秒；外层监督仅保留原正常终止和收据发布缓冲。同 CID、label、image 与实际容器 State 建立终态，不以 Docker client 退出替代。准备、启动请求、运行和真实终态分别记录。

已删除的少量本任务旧 cache ELF 均先逐字归档、核对 SHA/CRC、持有原 TargetLease 并核对实际 process 引用；保护最新测试/产品及失败证据。没有降低 admission 门槛，也没有用清理缓存冒充模块验收。

后续每个 GREEN 应追加自己的源提交、输入、真实命令、退出/终态、原始日志摘要和剩余范围。历史 RED 永久保留，即使对应缺陷已修复。
