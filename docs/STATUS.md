# 当前状态

## 2026-10-17：A08 源码及主机工具整合到 main

本次 A00 集成以实际 main `18d9fca65381f0e84f130c76fa289d5186894d85` 为父提交，纳入 A08 已发布修复 `25c76c1f294a3bf0ccf541f0063b0278899bf979`。整合源码提交为 `194c41d0b2c8f1fabb7b6de4fac8967b862518a6`，与本地实际执行提交 `5a5f03390901c8393d0336f6b5e194e2dfc5eb3e` 的完整 Git tree 同为 `836d3907854eb125eba1fdb492e6baff65ad4c45`。采用独立 A00 主干集成路径，保留两边历史，未改写 A08 owner 分支。

| 本轮闭合项 | 实际结果与证据 |
| --- | --- |
| 来源审计绑定 | 指定 `--project-ref` 后从该 Git tree 读取不可变 blob，忽略工作区脏文件与后续提交；每项记录 Git blob、SHA-256、大小、mode，并给出完整 Rust 清单摘要 |
| 实际锁文件核验 | schema 3 分开记录预期 pin 与被审计提交内的真实 `support/upstream-lock.json`；缺失、损坏、tag/commit/reuse 不符均明确阻断，不能靠复述常量得到通过 |
| main 组合验收 | 完整 host 聚合 exit0 / `host_passed_only`，normal 184 项与 optimized 184 项通过；63 必需 / 71 检查文件通过；真实 OpenJDK 17 Java/JNI 编译与加载成功 |
| 固定源码检查 | main 组合的 `support/build/verify-source.py` exit0，118 项输入核验通过；root README 严格 0 字节，两个上游 pin 与内核源码均未由本集成改变 |
| 证据与开发入口 | [组合收据及原始日志](../results/integration/a08-host-main-20261017/README.md)、[A08 开发手册](../support/android/README.md)、[184 项及来源绑定负例](../tests/workloads/android/evidence/2026-10-17-commit-bound-audit/README.md) |

**资格仍为 Linux host 工具。** 实际 Binder device probe 返回 77 / BLOCKED；Asterinas 源码审计仍有 Binder、seccomp、MAC 三项阻塞。没有 AOSP 产品构建、Android guest/APK、新内核或移动端运行资格。云端排队不作为通过依据；上表来自本轮实际执行。A07/A10 的后续主机与 Weston 验证仍在独立候选中收口，原版 Agentd 运行状态须单独核对。

下面保留此前审计修复快照；其中 176 项、旧 HEAD 和“A08 未合 main”只描述当时版本。

---

## 2026-10-17：审计修复与 Hepta 只读 UI 接合

本节记录本轮实际增量。起始核对 main 为 `88f859bd2da13aa9e43a321edd172bdf0f7bfcf8`；发布前整合到 `146dedf75c5729ef1930c845eeb60e31e8111c60`，保留期间已合入的 G0 [#105](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/105)、A09 [#142](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/142) 与 A05 [#148](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/148)；A05 的新进程 / 镜像隔离实证完整保留在下段。本轮没有重新编译或启动 Asterinas，既有 kernel/QEMU 结果仍绑定其原始源码。

| 交付 | 本轮结果 | 集成状态与资格 |
| --- | --- | --- |
| A08 源码完整性 | 恢复 39 个遗漏文件、4 份变化的历史内容和 2 个执行位；从历史 Git tree 核对，没有损坏基线独有的新文件被覆盖。新增 63 项必需输入清单和 10 项回归；修复只解析第一份 Shell 文件的语法检查；A00 补上执行完整 host suite 的定向 CI | [stacked Draft #156](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/156)，基于 owner `41a8c32`，未合 main |
| A08 实际 host 验证 | 原始发现 25 项并有 3 个导入错误；历史完整恢复后 166/166 通过；新源码 normal/optimized 各 176/176、0 跳过。真实 Java/JNI 编译与加载通过，完整聚合 exit0 / `host_passed_only` | Binder device 为 BLOCKED/77；Asterinas Binder/seccomp/MAC 源码门槛仍失败；无 Android guest/APK/实机资格 |
| A07 只读 Agentd client | 固定 Hepta v2 的 Health/Capabilities/Events/RunStatus 白名单、5 秒总期限、64 KiB 帧限额、实际 SO_PEERCRED 与代际核对、受限事件投影。1 个阻塞线程取消回归与 13 个 Linux UDS 测试通过，11 个来源文件及从原源抽取的协议定义核对通过 | [stacked Draft #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157)，A07 与 A10 同一组合候选，未合 main；是 organ 外的主机 client，不是新 Agent/authority/effect owner，也未改变只读 organ 合约 |
| A10 Session / Rust Shell | Session 独立 worker 执行只读观测，Shell 接收有界 DTO；新增 Runtime 页，断连保留旧观测并标 stale；修复原 Shell inspector 的 Rust E0382 借用错误 | 66 项 UI workspace + 14 项 facade Rust 测试通过；严格 Clippy、fmt 与真实 Session IPC probe 通过，见[证据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/dfffb4a89b2094d08ea89210097fcc208e98ff68/tests/ui/evidence/2026-10-17-hepta-observer)；实际链路使用协议 fixture，未启动原版 Agentd、未提交 objective、未执行设备效果 |
| 文档交接 | 纠正架构/路线/验收/CPU 手册及初始 Agent prompts 的过期状态；[INDEX](INDEX.md) 增加逐模块开发/技术/测试映射；新增 [A05 实现与调试手册](agents/handoffs/A05_KERNEL_CONTROL.md) | 只更新文档与交接入口，不变更 HOS2 wire、上游版本或既有 gate 判据 |

A08 已发布修复 HEAD 为 `3ac85d8672e3afcfb70c0ee323108294ef883239`，tree `839a47c23cb457eed3c5a88c8c0dec160bdc87f7`。原始失败、恢复来源、逐文件 hash、normal/optimized 结果及补齐 JDK 前后的真实聚合均保存在 [证据目录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/3ac85d8672e3afcfb70c0ee323108294ef883239/tests/workloads/android/evidence/2026-10-17-source-integrity)。API 发布 commit metadata 与本地不同，PR 逐提交记录相同 Git tree 的映射，不将不同源码的结果混用。最后追加的 A00 workflow 与手册提交不改变已测 Android 执行源码；YAML 与 Shell 步骤检查通过，云端 runner 是否通过仍须读取实际结果。

**下一条工程边界：**只读观测成功不授予目标提交权限。实际 ObjectiveStart 必须由 Hepta 已有可信 ingress/issuer 和 authority/operations owner 接受原始认证封套，UI 不自签、不生成 authority epoch、不用兼容 RunStart 绕开入口。A05 已合入的只读进程 / 镜像隔离之上的可信能力授予与其余四项 HOS2 操作、A06 exit/reap 最终 CPU 计费与 SMP、A07 durable K↔D/撤销/未知历史/退役仍未闭合；G1/G2、原生设备控制和移动端资格仍未通过。

根 README 保持 0 字节；Asterinas v0.19.0 / `nightly-2026-07-21`、Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 保持不变。下面按时间保留历史执行记录，其中“当前”“尚未进入 main”等语句只适用于该段绑定的源码，不是本节的现状。

---

## 2026-10-17：A05 进程身份与 QueryAbi nonce 已合入主干

- **代码已真实合并：**[PR #148](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/148) merge `d8293465bcbbeb192bc53b252df10b9ddcce7a20`。将现有只读 `/dev/hepta-control` QueryAbi 会话绑定实际打开的 Process：fork 继承旧 fd 拒绝、exec 后旧镜像 fd ESTALE、同进程 dup 稳定；进程/镜像用启动内单调且溢出拒绝的64位 nonce 避免 PID+低32位jiffies身份复用。配套 [PR #155](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/155) 增加7项关键客体标记逐项、恰好一次核验和原始串口SHA256，已依次合入 #154/#148，**没有开启HOS2写权限**。
- **最新 main＋修复的真实编译与客体验收：**先在主干 `976c5abc19f59abeb2549c4e3e9da14ce03df8d2` 上叠加精确8个A05文件，组合Git tree `4b486eba185dad538e8578fb6c33916907a82cdf`，固定 `nightly-2026-07-21` 全内核从源码构建exit0、ELF SHA256 `96b12e32ac4db1b65ff026f4576b673643cdf0d18b0836713d67ca689a4a673c`。用原已验证的 nonce 客体 initramfs 新启动 QEMU raw33：QueryAbi、fork/exec/nonce/非root/dup等9项标记各一次，无 FAIL。相同内核的 CPU 1%×2为1.000%/1.000%；10%普通10.478%、SCHED_FIFO10.288%、父域10.043%，**5/5** 原始cpu.stat测试全部raw33；`aster-core` 真正内核QEMU ktest **153/153通过**、0软跳过、raw33。此项仅验证单vCPU N0，未承诺严格逐窗、SMP或裸机。机器收据：[a05-main-combined-acceptance-20261017.json](../results/kernel/control/a05-main-combined-acceptance-20261017.json)。合并期间另有A09工具提交，与8个A05文件没有交集。
- **仍缺的主要产品能力：**可信capabilities的启动后授权、HOS2 `ReadUsage/InstallBudget/QueryDelivery/RetireThrough` 实际效果接口、撤销与幂等/历史确认、Hepta唯一durable owner、SMP生命周期（包括 A06 [PR #138](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/138) 的退出末次CPU借记及cgroup租约）。现在仅有**只读QueryAbi身份隔离**。G1/G2、生产部署仍未完成，根README继续0字节。旧状态快照不应覆盖本段新增实证。

---

## 历史执行记录

## 2026-10-17：A03 原生锁后端已经合入主干

- **正式主干合并：**[PR #146](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/146) 提供公开 `LockBackend`/`ControlMutex` 和 `ControlCoreWith<B>` 后端，让 A05/A06 原生内核锁集成不再需要复制控制源码；已合并至 `main`，合并提交 `10e467b3775bc6f041f520bb33e0395c8b6793e1`。
- **独立 exact-head 回归：**已针对最终 PR HEAD `d3bbaf8d5baed636647e529d8475f65e7f8199a5`，在本机固定 nightly-2026-07-21 执行 `tests/control/run-validation.sh` 全量宿主矩阵，包括 std/portable-spin、严格 Clippy、fmt、x86_64-unknown-none `no_std` 构建、公共后端 API 兼容性、Loom 有界并发模型和锁内零分配，**执行结束通过**。最早的失败来自默认 Rust 1.95 未安装 `x86_64-unknown-none` 以及浅克隆缺失固定历史 Git 对象；改用已安装目标的固定 nightly、抓取必要基线提交后复跑通过。
- **不能外推的边界：**以上是 Rust 库及其宿主模型的真实回归，尚未证明 Asterinas 多核 IRQ 锁安全、A05 ioctl/exec/fork 身份隔离、A06 zombie 最终 CPU 借记、A07 Hepta durable owner 的实体效果与故障恢复。最近相关候选 PR 仍分别处于 Draft，需要真实内核与 QEMU 证据而非只靠这次 host pass。

---

## 2026-10-17：最终计费编译修复与 A09 严格测试恢复

- **A06 真实修复但尚未主干放行：**在 [Draft #132](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/132) 的实际固定 nightly 内核构建中，发现两处 `Option<ArcRef<T>>.cloned()` 编译错误 E0599；以明确的 `.map(|value| (*value).clone())` 保持真实 `Arc<T>` 引用。独立 [PR #141](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/141) 已合入 #132 开发分支，合并提交 `ee6c278f9468c4633bed94d0bc3563b9601df0a4`，**不是合并 main**。原源码编译失败；修复后完整 Asterinas 编译 exit0，ELF SHA256 `48bea33a39614004a17aeae9159f0ea57a73a6fd4db64c3c3b2fd43c6dee934f`。固定 QEMU 1-vCPU 原始 `cpu.stat` 客体验证 **4/4 raw33**：leaf1%＝1.0%、1.1%；RT10%＝9.965%；parent10%＝10.096%；同源码 **aster-core 153/153 真实内核测试通过**、0失败/过滤/软跳过。机器证据见 [A06 验收收据](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/e0060a06ac11a30ad7472c65e0d9da852cc03d50/results/organ-backend/2026-10-17/a06-final-debit-arc-ref-compile-and-guest.json)。尚未专门证明 zombie exit/reap 最后一段 CPU debit，不能据此宣告 G1 或 SMP 合格。
- **A05 防复用候选独立验收边界：**精确候选 `7a9b4919402fe43b88866da2c2aab2aa5b589e28` 的宿主 nonce 契约 **4/4 通过**，原 QueryAbi host smoke 通过；固定 nightly 全内核编译 exit0，ELF SHA256 `dfac10ce6909ac99321e4768e41f8ff5c70edd7e496d51d735ffd6e3577213ee`，普通隔离 QEMU initramfs 启动 raw33/boot marker 成立。**本轮未执行该候选的实际 fork/exec/QueryAbi identity 客体探针**，原同进程身份曾有失败；继续保持其 Draft，不得因编译和普通启动成功就签发真实效果权限。
- **本轮已合并主干的代码与实测流程：**[A03 PR #134](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/134) 将实际成功的 exact-source Loom／锁分配模型加入 CI，merge `c0ffb9e736869da577fed12d9fa46df086bcd858`；[A09 PR #143](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/143) 修复已合并 DMA 元数据模型的两处严格 Clippy 问题和 Rust 格式，merge `7d6c9d426e7920fc17bb723de9e2a671fcc91b5e`，本地真实 **55 单元＋4 compile-fail doctest＋7 Linux ECHILD/worker 负例**均通过、Clippy `-D warnings` 与 fmt 均通过。**A09 仍只是 no_std/host 元数据模型**，未进行真实 GPU DMA、IOMMU 或物理硬件测试。
- **下一条实质阻塞：**A06 从主干当前版本对齐完整最后计费生命周期 QEMU 场景（真实 fork/exit/reap、cgroup lease/rmdir、SMP 迁移/锁序）；A05 通过精确进程 nonce/exec/fork 客体权限验收后才可接 HOS2 ReadUsage/InstallBudget；A07 只沿既有 Hepta owner 实现持久 K↔D 结果确认和退役，不把只读 organ host 变为效果执行器。**G1/G2、真实硬件和生产资格仍未闭合。**

---

## 2026-10-17：A03/A02 已独立验证并合并，A05 进程会话完成真实客体验证

- **合并到 main 的真实源码：**[A03 PR #123](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/123) merge `df8e2decbb1f4efb501d03f6141f81c7a128ac1a`，减少 native delivery 预约／退役／历史丢失时的内部锁下分配；[A02 PR #119](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/119) merge `eabf5fb169a1d477ff3b3059a7a2aaa89746cdc8`，为 N0 `ReadUsage` 编码和解码补上 `cumulative_cpu_ns <= sample_boottime_ns` 的不变量。均是精确预期 HEAD 的普通合并，未改其他 Agent 分支。
- **A03 独立实测：**精确 `25f809623f22b205189a1ad3fa995667189a45b6` 的 std 与 portable-spin Rust 测试、双方严格 Clippy、fmt、`x86_64-unknown-none` 编译均通过；12 项 Loom 模型通过、18 个锁分配检测场景在已测同步模型中无锁内分配。合并后在精确 main `df8e2dec...` 重新运行两套 Rust 测试、两套 Clippy 和格式检查全部通过。**只证明宿主与有界模型行为，不是内核 IRQ/SMP 终验。**
- **A02 独立实测：**在固定 `nightly-2026-07-21` 上完整执行未修改的 `tests/abi/run_acceptance.py`，**13/13 验收检查全部通过，20/20 编译型错误变异被抓到**；原样输入与 0 字节 README 校验通过。合并后精确 `eabf5fb...` 的 Rust ABI 测试、严格 Clippy 和 Python 57 项测试亦通过。GitHub 云端排队的任务不能冒称绿灯；这些是授权本机独立执行证据。
- **A05 原生只读 QueryAbi 真实 QEMU：**[Draft PR #125](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/125) 精确源码 `48303eb68582f32639f555f54ccab1d5355753d2` 从源码固定 nightly 编译成功，ELF SHA256 `8198458eb4039717465595952213dbb2a981f77c38f25acc4e171b2caf6c2581`；同一独立 1-vCPU 客体中 pre-exec QueryAbi、post-exec `ESTALE`、fork 继承 fd 拒绝和启动完成标志均成立、QEMU raw33。Host C/Werror 与六项回放负面测试也通过。
- **未合并的 A05 对抗实验：**为了避免 PID+截断32位启动 jiffies 重用公开 CapSpace wire ID，独立本地候选 `2e87e8fe7a42032e97edb440b170206c53c28069` 尝试单调进程 serial。该候选虽然编译，但真实客体报 `HEPTA_QUERYABI_FAIL at=same_process_session`、QEMU raw65，**明确失败，未推送或合并**；原 A05 owner 分支保持不变，失败已报告 PR #125。
- **当前剩余主门槛：**A06 zombie/exit 最终 CPU debit [PR #129](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/129)、A05 真正不重用且稳定的 CapSpace ID 和 exec/fork 授权、HOS2 其余四项效果接口、Hepta 原有 durable K→D/历史/退役均未完成端到端资格。A06/N0、A05/QueryAbi 已有实证，但 **G1/G2 和 SMP/硬件生产放行仍然不成立**。

---

## 2026-10-17：A05 QueryAbi＋A06 CPU 带宽已合并 N0 实验内核

**真实主干合并：**[PR #121](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/121) merge `3538ec23570733a8b48678f9f24fcd0949dabd84`；主干包含此前 A05 的只读 /dev/hepta-control QueryAbi 与 A06 的实际 cgroup CPU 限额／调度器。测试源码本地合并提交 `b913202b2e487126319e60813a54163666b9a2ad` 与远端集成提交 `eaf5242233b799356b7daa73898a14d240832abb` **Git tree 相同**（`b852e0037af8f84c22a8fc7347fa55d8183e07e6`）；后续 PR 仅添加结果 JSON，三条核心内核文件 Git blob 已在合并后再核对一致。唯一文件冲突 `support/build/kernel.sh` 采用已验证的 main A01 新版（保留 manifest 身份及 --live-artifacts），没有回滚 A01 修复。

**实际执行证据（非报告拼接）：**固定 Asterinas v0.19.0 / nightly-2026-07-21 从同一源码树完整构建、在 q35/TCG／1 vCPU／512 MiB 运行 initramfs，raw QEMU=33、构建／启动脚本 exit=0。候选完整 ELF SHA256 `06cf42337d266a486d3ac98caa3f9b0021f0f7679c7130e48224cb35fedb90ab`。在这个内核上，**10/10** 原始 `cpu.stat` 探针客体成功（单 CPU 1% x3＝1.100%、1.000%、0.999%；单 CPU 10%=10.352%、RT10%=9.824%、parent10%=10.226%；双 CPU／双工作线程 1%=0.957%、10%=10.112%、parent10%=10.396%、RT10%=10.187%，全 raw33／无panic）。**3/3** 真实 A05 QueryAbi ioctl 客体通过，包含权限拒绝与格式拒绝测试，raw33。**真实 QEMU 内核回归：**OSTD 报告 221 passed/0 failed，其中3个VMX/EPT软跳过；aster-core 153 passed/0 failed/0软跳过；实际执行通过下界**371**，两套raw33。A05 host smoke、archive负测与bash语法亦通过。机器证据见 [a05-a06-integrated-acceptance.json](../results/organ-backend/2026-10-17/a05-a06-integrated-acceptance.json)。

**严格边界：**这只是 **N0 实验性开发主干**，不能称为已生产可用OS。QEMU双核／双线程有限样本不是 SMP、CPU热插拔、迁移/IRQ锁序或逐100ms硬上限的充分证明；QueryAbi只读，per-open observation space ID不是可信CapSpace。**HOS2 InstallBudget/ReadUsage/QueryDelivery/RetireThrough、exec_epoch与启动能力授权、A07现有Hepta owner的持久K↔D、撤销／历史确认退役尚未集成**；G1/G2仍不合格。root README严格0字节，无现役机器内核部署与生产服务修改。A06原 owner Draft #18 保留独立开发记录；新后续补丁须从当前 main 对齐、避免重复集成或覆盖。

**下一条产品实现：**优先将 A03 `ManagementGrantState`／ResourceDomain 与 A05 Asterinas 的真实进程/CapSpace 身份接合，把 `ReadUsage` 与 `InstallBudget` 接到已合入的**唯一 cgroup/调度资源事实**；完成普通进程无权、exec/fork泄权防护、cap=0独立恢复、同K/D效果幂等，再由 A07通过现有durable authority/operations owner完成效果对账和退役。策略继续在Hepta用户态，IRQ/调度快路径不调用模型。

---


## 2026-10-17：原生 QueryAbi 进入主干，G0 验证收敛

本段为已执行事实的最新摘要；历史条目中“ A05 尚未进入 main ”的表述只适用于其旧版本快照。状态文档更新前的主干 HEAD 为 162707a0e6ccccc768c0f1abd3263f3ff4c647a1。

- A05 原生实验设备：PR [#87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87) 已合并，merge 2e1d592c25335f3cd97f312e4f73545f305d6e61。Asterinas 主干新增 /dev/hepta-control，只允许 root 打开、只读、且仅支持实验 QueryAbi ioctl；用户态复用项目唯一 HOS2 Rust codec。精确 owner 源码 224fcdde44b9c68163298623fd908e3009b1b2a6 从固定 nightly-2026-07-21 编译成功，ELF SHA256 f667b468940af56070d8a7a1909fe68e863d6a0d095fca8de894e71ff9acd077。独立QEMU单vCPU 3/3 次 raw33，QueryAbi OK、非 root 打开拒绝、dup-fd会话一致、无panic；本源码 aster-core 真正 QEMU ktest 141/141通过，0失败/过滤/软跳过。代码 blob 与main一致。
- A05 host负测：同 exact owner SHA 下 run-host-smoke.sh exit0，16个请求结构负例、21个异常HOSR响应、ENOTTY/EFAULT及6 normal/6 optimized 归档用例成功。客体的3次通过与host结果分别统计，不能互相替代。
- A03 G0 portable target：PR [#103](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/103) 合并为 751d5448b6e92e8902b89bcd1d337c5d61872393。独立运行实际Rust标准/portable-spin宿主测试、严格Clippy和x86_64-unknown-none rlib全部通过。这不代表该 crate 已接入新内核或验证 IRQ 锁序；GitHub Actions exact-head此前仍 queued。
- A02 编译型反例：PR [#101](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/101) 合并为 d2173e21ca902fa304d5d6edacbc329c9484a570。对其精确 SHA c6139994f4cc97b8cdc804e906d532ca04167ad2 运行正式 pinned acceptance，13/13 组检查通过，16/16 编译变异被测试抓住；输入文件哈希保持不变。合入 A05 后在main重新执行 A02 Cargo测试亦成功（首次临时手工加 --locked 但新 checkout 未生成 Cargo.lock 导致的失败不属于代码失败，正式 acceptance 以隔离快照生成锁）。
- A01 构建命令修复：PR [#110](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/110) 合并为 162707a0e6ccccc768c0f1abd3263f3ff4c647a1；support/build/kernel.sh 去掉 make/gcc --version 的早关闭 head 管道，避免 set -o pipefail 因 SIGPIPE返回141。此缺陷在本轮 A05首次源码构建中真实出现；隔离环境仅临时采用不提前关闭消费者后完整构建成功，工具脚本已恢复，再将两行永久修复合入主干。不声称 PR #110 已完成独立 GitHub runner验收。
- 明确不能外推：QueryAbi 的 per-open session ID 不是可信 CapSpace；正式 ioctl号、exec_epoch、ReadUsage、InstallBudget、QueryDelivery、RetireThrough、A06 SMP/严格CPU cap、A07 Hepta 唯一 owner K↔D 效果/持久确认及退役仍未闭合。G1/G2 未通过，A06 [Draft #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 还不是 main。根 README.md 保持严格0字节，未操作任何现役业务设备。

---
## 2026-10-17 UTC：A05 原生 QueryAbi 已在真实 Asterinas 客体执行（仍为 Draft）

- **真实内核 HOS2 ioctl 首次执行成功，纠正下方历史记录的“尚未在 guest 运行”描述**：[A05 Draft #87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87) 原源码提交 `5fc3887dfc5833b61d11280eb1421bb7fd78648f`，经过实际 `make kernel` 编译的候选完整 Asterinas ELF SHA256 `54c8a7a798cbbd80f1a8ce5f0144328815e63b413e79b0133206bcaaba607e4a`。四份 A05 实际修改文件的 Git blob 与远端 PR 精确吻合。独立调用固定原始 C probe，在 QEMU q35/TCG x86_64 **1 vCPU/512MiB、无网卡数据盘** 中真正打开 `/dev/hepta-control` 执行 QueryAbi ioctl，校验 HOSR/版本/唯一开放会话 ID/QueryAbi-only 位图、非法 magic EINVAL、NULL transport EFAULT、未知 ioctl ENOTTY。首次 QEMU raw33、`HEPTA_QUERYABI_OK` 与 A01 boot marker，无 panic；同一预校验内核 ELF/一次性 initramfs 又复跑 **3/3 次 raw33**，合计 **4/4** 成功。该轮复用了源构建内核 ELF，没有把这4次 guest replay 说成4次内核重编译。
- **真实内核回归：**从与 A05 四份改动路径逐字节一致的隔离源码工作树，运行固定 `nightly-2026-07-21` / `support/build/ktest/run.py --crate aster-core --skip-osdk-install`，实际 QEMU 内核测试 **141/141 passed、0 failed、0 filtered、0 soft skipped、raw33**。该轮重新构建内核测试 ELF，SHA256 `5e1d40b86b4717a645f3cc089f746b7fa0c90e84bf0bdb72615e25d47b402746`，不等同完整 Asterinas/OSTD/SMP 矩阵。
- **客体回复校验反例同步通过：**独立对 [已并入 A05 分支的 PR #90](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/90)（merge `db0a77263218b7d4cd4d3994a93edcf4d7da9590`）精确源提交 `e925bdfcc59b2f7f7d606eb964447ffd8b741283` 执行 `sh tests/kernel/control/run-host-smoke.sh` exit0，真正编译原 C guest 校验器并验证 **1合法＋21非法 HOSR 响应**、另16帧结构负测及 ENOTTY/EFAULT 拒绝。其加固后 guest C blob `58cc000c81501185aa0d328bc8701cec92a2dea0` 在同一 A05 内核 ELF 的 QEMU 中也返回 raw33/QueryAbi OK、无 panic。**这是 host 负例与 guest 正例的分别验证**，并非全部恶意 transport 都已在 guest 测试；#90 远端 CI `host-contracts` 仍 queued，不能报绿。
- **证据已进入 A05 owner 分支：**[PR #91](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/91) 已合至 `agents/A05-native-queryabi-bootstrap`，后续验证以 A05 分支下 [a05-queryabi-real-guest-20261017.json](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/agents/A05-native-queryabi-bootstrap/results/kernel/control/a05-queryabi-real-guest-20261017.json) 追加完整 QEMU/重复测试和141项内核验收机器结果。原始串口、具体QEMU命令和编译日志保存在授权隔离实验区，公共仓库仅保留脱敏的哈希与结果。
- **尚未放行：**A05 主 PR 仍为 Draft，**只实现只读 QueryAbi**；查询中的 per-open observation space ID **不是真实可信 CapSpace**，未完成 exec_epoch/启动授权/InstallBudget/ReadUsage/QueryDelivery/RetireThrough 与 Hepta 持久 owner K↔D。HOS2 G1/G2、SMP、裸机、持久副作用均不合格。禁止把 `TrustedReadOnlyOrganV1` 当作硬件效果执行器；保持原 authority/operations 真正执行 owner。

---

## 2026-10-16：A00 A03 生命周期主干合并、HOS2 语义边界和 A05 客体验收防假阳性

- **A03 真正源码已合 main**：[PR #86](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/86) merge `9113b3cfc2822d86f32e3dcfc78c6e2b8c123ecd`，仅改 A03 自有 `libs/os-control/**` / `tests/control/**`。修复末次 `Arc` 释放后父资源域不应保留已销毁子域 cap、外部 execute 回调期间不能卡死 QueryDelivery/retire/history audit、资源域过深递归释放风险，增加层级最大64约束。精确 HEAD [G0 run 38986007642](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38986007642) **success**：真实 A02/A03 Cargo、fmt、strict Clippy 均通过，A03 129/129 宿主 Rust 用例通过。原 owner 另外记录 portable-spin/no_std build 与第二后端 129/129。**仍是 Linux host model，不是 A05 内核设备/持久 Hepta 效果**。
- **HOS2 独立语义黄金边界已并主干**：[PR #77](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/77) merge `82ef86a9d48851c17de2df0699b16f032be7dd3e`，现有 G0 增加独立24帧 HOS2 semantic edge oracle 必需源/非软链接检查与 Python `--check`，修正“源/测试同时删除仍绿色”假阳性。精确 HEAD [G0 run 38986254820](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38986254820) **success**，不含 QEMU 或内核效果运行。
- **A09 安全代码已经进入堆叠开发分支**：[PR #75](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/75) merge `e9f61ca4f0ceca82fc4cd20e4c5ec3a856ee7827`，目标 `agents/A00-a09-native-worker-supervisor`，**非 main**。对其精确 HEAD 的 [host-device-model run 38985469497](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38985469497) 为 success；保留 WNOWAIT/未回收 leader 身份锚，避免复用 PGID 后误杀他组，异常 worker/group 拒绝伪造成功。A09 owner 已分别吸收并继续强化 worker 报告；GPU/IOMMU/复位/物理 passthrough 没有完成。
- **A05 真实 QueryAbi 尚未执行，但验收假阳性已修源码**：[Draft #90](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/90) head `ff8162a06f755c206c79b9d0b7d053c60f40c1c0` 堆叠在 A05 原生设备 [Draft #87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87) 上，仅改 A05 `tests/kernel/control/**`：HOSR minor/header-reserved/payload-reserved 必须逐字节验证，新增1有效+21个失效 HOSR 帧对抗，并接入现有 C11 宿主 smoke（文件缺失/符号链接时硬失败）。源代码已推送，**本 A00 环境未实际执行新 C 负测**；[PR #90 G0 run 38988044867](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38988044867) 当时仍 queued。现有 A05 内核 QueryAbi ELF 虽已从源码构建，但真实 QEMU ioctl 尚未运行，不能因 C 负测宣称 G1。
- **固定边界与剩余阻塞**：G0 先前 #69 merge 的严格 Clippy 红灯由 A02 owner [#76](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/76) 中 `as_chunks::<2>()` 修复；A00 独立重复 #84 已关闭未合，避免覆盖 owner 后续测试。A05 真正 CapSpace/process-start/exec-epoch/QueryAbi QEMU、A06 [#63](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/63) 退出 Task 最终 CPU 借记、A07 唯一 Hepta durable K↔D/效果确认/退役均未闭合，G1/G2 未通过。根 README 0 字节、Asterinas v0.19.0/`nightly-2026-07-21` 与 Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 不变。

---


## 2026-10-16：A02 全量实测合主干；A05 QueryAbi 内核候选（未验收）

- **A02 已真实合入 `main`**：[PR #76](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/76)，merge `8f3bb49ab161104063a6ebea25428c40aa884ac0`。在授权执行宿主固定 `nightly-2026-07-21`（Rust 1.99.0-nightly）对精确 owner 代码源和与 main 同步的提交 `338bd37b471cb0c94f2dbd251d4c98fd6180342c` 运行 `tests/abi/run_acceptance.py`，**13/13 必需检查通过**，无失败和遗漏，含 no_std 编解码、12基本 + 24语义黄金字节、32B transport、负面案例、独立 Rust/Python 编译变异测试、fmt、严格Clippy、no_std target。合并后 `libs/os-abi/src/lib.rs` Git blob `dc32e002cfbfc63c456e071958b167ad24f50cf5` 与被测代码逐字节一致。最初执行宿主未安装固定 Clippy，验收按规则拒绝；仅安装固定工具链 Clippy 后重跑通过。实际 Github Actions 另看其独立结论，不能把 queued 状态报为通过。
- **A03 同一源码进一步复核**：使用 `RUSTUP_TOOLCHAIN=nightly-2026-07-21` 对 `tests/control/run-validation.sh` 运行真正 Rust host / portable-spin / no_std 编译、测试与严格 lint，最终 exit0。首次错误使用默认 Rust 1.95 导致 `x86_64-unknown-none` 目标缺失，保留为执行环境问题，不能算产品测试失败或掩盖后续修复。
- **首次 A05 真实内核源码候选（仍为 Draft）**：[PR #87](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/87)，commit `5fc3887dfc5833b61d11280eb1421bb7fd78648f`。沿 Asterinas 既有 char registry/devtmpfs/PerOpenFileOps，新增仅只读 `/dev/hepta-control` 的实验 HOS2 QueryAbi；输入/输出调用**同一份** `libs/os-abi/src/lib.rs`，boot/临时会话 ID 独立标识，**不授予** CPU、设备、管理/历史退役效果权。内核在独立工作树从固定 Asterinas 源码成功 `make kernel` 构建，ELF SHA256 `54c8a7a798cbbd80f1a8ce5f0144328815e63b413e79b0133206bcaaba607e4a`；静态 Linux ELF QueryAbi 对抗探针用 `cc -Wall -Wextra -Werror -static` 编译通过，但**尚未在 guest 真正运行 ioctl**。
- **明确剩余阻塞：**尝试创建 QueryAbi 客体 runner 及独立运行 QEMU 被授权执行工具拒绝；没有声称新内核的 QueryAbi 设备已运行/boot 通过。原 main 的 A01 构建脚本有 `set -o pipefail` 与 `head -1` 偶发 exit141，候选编译中仅在隔离工作树暂时把 `head` 换成 `sed -n '1p'`，在提交 A05 前完全恢复；PR #87 不改 A01 所有文件。正式 ioctl 编号、可信 CapSpace/process-start/exec_epoch、A06 真正的 ResourceDomain/G1、A07 Hepta 唯一持久 owner 效果/撤销/历史查询和退役/G2 均未放行。根 README 保留严格0字节，未修改生产机器。

---

## 2026-10-16：A00 持久 K 主键纠偏与 G0 严格 CI 交付

- **已合并真正 CI 源码**：[PR #69](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/69)，merge `5aeff7b60e8c96aa14676e1642efddc6ad63a607`，现有 `.github/workflows/g0-contracts.yml` 对 A02/A03 Cargo+fmt+strict Clippy、A05 QueryAbi/ENOTTY 改为必需检查，`tests/control/**` 纳入 PR/push 触发。A00 在独立 Bash fixture 实际测 **9/9** 文件缺失保护场景通过；**当前新主干 GitHub Actions 仍需自身真实完成，不能报通过**。
- **重要 Hepta 事实校正（取代下方 A00 历史错误 K 描述）：** 固定 `hepta-private-ci@f8c9419d...` 的 `kernel.operations` 持久 `OperationIntentV1` 含独立的 `scope_id: StableId`、`operation_id: StableId`、`payload_digest: Digest32`，其固定 SQL 主键是 `PRIMARY KEY(scope_id, operation_id)`；摘要不是主键，参与 `semantic_digest` 和权限/最终效果的独立校验。此前 A00 草稿 #35/#48 曾把 `model.rs::OperationKey {id,payload_digest}` **参考模型**误当该持久账本的 K，两个草稿均未合主干；这一定义现明确撤回。A03 owner 的两个无损 StableId 字段方向正确，不能被旧草稿覆盖。A07 仍要在原唯一 Hepta owner 里分别验证摘要、授权、代际和 K→D 绑定。
- **当前真实限制：** A03 仍为 Rust **host model**、A05 五操作真实 CapSpace/ioctl 与 A07 持久执行/恢复仍未闭环，G1/G2 不合格；A06 CPU 配额实测不能替代生命周期/权限/严格窗口验收，A09 GPU/VMM 仍需隔离执行及物理硬件验证。固定 Asterinas/Hepta/toolchain 未升级，根 README 0 字节。

---


## 2026-10-16：HOS2 ABI 独立复核与主干合并

- **已完成：**[PR #72](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/72) 的 `no_std` HOS2 transport snapshot/preflight/typed codec 修复已独立测试并合入 `main`，merge `02a0e4f6e11ed04039179165726ae43a0caab78a`。独立对精确 PR HEAD `eef96afd4c3fcdc5bcdc2b8ba00260e1fb116b91` 在 Linux host 执行 `cargo test --offline`、`cargo clippy --offline --all-targets -- -D warnings`、`cargo fmt -- --check`、`cargo check --offline --no-default-features` 和 `python3 -m unittest discover -s tests/abi -p test_*.py -v`，全部返回 0；Python ABI 30/30 通过。这是**真实源码宿主测试**，不是内核 HOS2 功能验收。
- **A06 最新开发：**A06 Draft [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 已有多轮真实 QEMU 1vCPU/2vCPU 探针和修复进展，当前仍为 Draft、未进主干。其精确提交对应的 SMP 证据包括已修复的已退出 Process 生命周期问题，但不能从两线程、2vCPU 样本推广到完整 SMP、CPU 热插拔或所有内核锁序。未验证严格逐窗 CPU 上限。
- **真实下一步：**A05 必须将已合入的 ABI/控制核心接进内核设备/进程授权与 `QueryAbi`，随后最小 `InstallBudget/ReadUsage` 调用进入唯一实际调度/配额状态；A07 沿现有 Hepta owner 完成真实效果确认、历史查询与有界退役。A06 先独立整树回归和 owner 审核，再申请合并；不能因 host ABI 测试绿灯自动放行 G1/G2。

---

## 2026-10-16：A00 Hepta K/HOS2 严格合并与 CUDA 原生超时真实反例

- **A03 真实 Rust 源码交接（尚未合 main）：**[Draft #48](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/48) 最新 A00 head `040eb1b352308debc763c7c9cb86106ffb1e11dc`：在 A03 owner 的 ResourceDomain/投递/原 owner 权限模型上，统一固定 Hepta 真正的 K=`StableId+Digest32` 和 `DeliveryObservation::hos2_saved_status_code()->Result<u16,DeliveryError>`。拒绝终局结果缺失、伪造元数据、`previous_revision=0`、以及 `consumed > effective % 100ms`，对齐主干 A02 Rust decoder。**44项 Rust 集成测试已编写但本环境没有 cargo/rustc，不能宣称 44/44 通过**；独立 Python 时间/修订数学 oracle 5/5 通过，仅属算术模型。A03 owner 正持续更新，禁止强推或覆盖 owner，合入前需精确头部 Cargo/Clippy/fmt 与现有 Hepta 持久 owner 接合。
- **A09 精确原生超时负例：**[Draft #62](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/62) commit `4d0f19f62e349a78c7126bcb838ec732a9407646` 新增可执行 `test_cuda_native_timeout.py`，经本地 Git blob `2e7060ba59bca45af20ec90fffb04cdcc104b587` 与远端逐字节匹配。独立 Linux Python3.13/GCC14.2 实测：当前 `SIGALRM` Python handler 所谓30ms硬截止，在0.8秒不返回的 C FFI 上约 **800ms 后**才触发，相关测试预期失败；OS `subprocess.run(timeout=0.03)` 子进程回收对照通过。因此 A09 [#57](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/57) 的 `timeout_enforced=true` 不可作为可靠 CUDA/NVRTC 硬限期证据，必须改为独立子进程强制 kill/reap/未知效果后复跑，不涉及真实 GPU 或生产硬件。
- **A02 实际主干增量：**[PR #53](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/53) 经其他 Agent 合并，新增 no_std transport 地址算术溢出拒绝、InstallBudget 顺序 ID/前驱 revision 校验及密集 golden 截断负测。本轮 A00 对最新 `main` 仓库真实 12 份 golden 执行独立 JS 字节 oracle **1,232/1,232**（12正例、1,160前缀、12尾字节、48头变异），不是 Rust codec 执行；另外已有独立真实 Cargo/Clippy/fmt 测试结果记录在本页此前主干状态中。相关最新 GitHub Actions 仍为 queued，不能当作绿灯。
- **A06 新 G1 生命周期风险：**[issue #63](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/63) 来自实际源码：`charge_task_cpu` 在 `Weak<Process>` 无法升级时直接返回，可能遗失最后未结算的 `[from,until)` CPU 时间，尽管已修复 SMP panic。此项是**源码层面潜在欠账，尚无 QEMU exploit 证明**；要求 owner 绑定原始资源域至最后一次扣账，执行短生命周期线程/退出与配额对照，不引入第二套 ResourceDomain。A06 已有153/153 kernel 与2vCPU QEMU历史验收仍有效，但不证明每个 task 的最终借记或严格100ms硬配额。
- **范围与安全边界：**本轮新 G1/G2 内核 CapSpace/ioctl/原 Hepta 持久实际效果仍未验收；主干 README 0字节，Asterinas `c4b7ed575b7b32773475b194d2ad41fb6d03765b`、`nightly-2026-07-21`、Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 固定不变，不接触现役服务、系统盘或 GPU。

---


## 2026-10-16：A06 当前整树编译故障修复与双CPU独立回归

- **最新实际阻塞及代码修复：**A06 owner 提交 `31e49a3c29d5e19d30976cdfb55accba1d786aea` 的独立完整内核构建在 `cpu.rs:700` 因 `quota_debt_regressions` 结尾被截断而失败，报 `unclosed delimiter`。使用先前经过真实QEMU验证的准确测试尾部，只追加缺失代码，不修改运行时路径。修复 [PR #61](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/61) 已合并到 A06 owner，merge `becd1fe3a106afd02d755cefebb4dc139704e390`，**尚未进入 main**。
- **重新从源码构建及 SMP 回归：**修复后精确提交 `db3a8a36951041f6016a7d7ed870d1d9d014fdc5` 以固定 `nightly-2026-07-21` 完整编译成功，内核 ELF SHA256 `1bc49d2bd5995ad9d73457b310be1f0a9dcad8e3c36589b5f2741088db071572`。相同新内核运行 q35/TCG、2vCPU/双pthread共享cgroup **6/6 QEMU客体完成、无panic**：1% x2 =0.871/0.879%；10% x2=10.573/10.413%；SCHED_FIFO10%=10.104%；父域10%=10.221%。另外真实 `aster-core` 内核测试 **153/153通过**、无失败/软跳过、rawQEMU33。验收数据已提交到 A06 的 [机器结果](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/bbb5b87b81ef1a310b098c6b66aa4058018f678b/results/organ-backend/2026-10-16/a06-repaired-head-acceptance.json)，原始日志保留于隔离执行主机 `/home/qian-qi/.local/state/trillionnium-os-organ-next-20261016/evidence/a06-repaired-*`。
- **范围边界：**已验证的是指定 x86_64 双vCPU/双线程、父域及RT测试，**不是**SMP普遍正确性、任意多核热插拔/迁移、逐100ms硬限额、长周期回归或 HOS2/Hepta原生执行。A06 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 仍应保持Draft直到多机、权限和端到端门槛达到，不应仅因153内核测试通过就批准生产系统切换。

---

## 2026-10-16：SMP 双线程配额、退出进程防 panic、ABI 主干加固

- **A06 双CPU实际新故障与修复**：[PR #59](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/59) 已合入 A06 owner 开发分支，merge `31e49a3c29d5e19d30976cdfb55accba1d786aea`；**未合入 main**，其主PR #18 仍为 Draft。修改后 Asterinas ELF SHA256 `5c73b7fb84b6d8f160b5b037be8b5bca7d8e5507a2cf7b779405d054918819bf`。原修改后内核在 2vCPU/双 pthread/共享1%配额下发生 `PosixThread::process().unwrap(None)` panic（已退出的 Task 暂时仍在调度器中，原Process的 Weak 不再能升级）；未修改 Asterinas 对照同负载未panic，但 `cpu.max` 不执行，实际约100%。
- **真实QEMU修复验收**：对已销毁进程进行有界的 Weak upgrade 检查，仅允许已退出线程继续清理；原始读数和运行路径在有进程owner时不变。真实双vCPU双线程同cgroup **7/7** 次 guest raw33、无panic：1% x3 `0.792/0.896/0.950%`；10% x2 `10.392/9.914%`；FIFO 10% `10.279%`；父域10%/子域不限额 `10.262%`。每次配额前不限额总CPU约197–200%，因此确有两CPU同时运行，而不是单CPU假SMP。单vCPU原1%探针 **2/2** `0.999/1.000%`；固定 `nightly-2026-07-21` 编译及实际 `aster-core` QEMU **153/153通过、0失败/过滤/软跳过**。可复跑 [SMP测试源](../tests/organ_backend/smp2/run_parallel_candidate.py) 和[机器结果](../results/organ-backend/2026-10-16/a06-smp-posix-exit-guard.json)均位于 A06 PR #59/owner 分支，**不是 main**。
- **ABI主干实际交付**：[PR #53](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/53) 已合并，merge `a1c61d50fe281361ca04ad4bc3c6b3aba2c2260f`，强化 HOS2 `no_std` transport 越界、错误响应的有序 request_id 与 InstallBudget 版本校验。本轮修复测试源码的三处Rustfmt末尾换行后形成 `ee13b2d05f18c17b01ff10c1e487b9c3cba54290`；从该合并后的精确主干源独立执行 Cargo test、严格Clippy、fmt、12/12 golden及19项Python ABI测试全部通过。**这仍不是已实现的 HOS2 内核 ioctl、权限和真实效果。**
- **仍需攻克**：退出后最后一段CPU运行时间若失去持久所属资源，仍需正确结算；未测CPU热插拔/跨CPU迁移/长期并发锁序、严格每100ms窗口上限。A05真实 HOS2 CapSpace/ioctl、A07沿既有Hepta owner完成可信K↔D持久确认/退役均未闭环；不因双CPU测试就升格 G1/G2 或production。

---

## 2026-10-16：A00 归档 CI 防假阳性、A06 实际内核修复及 A03 接口收敛

- **main 已合并实际 CI 代码**：[PR #49](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/49) merge `7b1e183951121c5e16618ef046612053b146e6bc`，仅修改已有 `.github/workflows/a01-boot-evidence.yml`，用 PR base/push before 的实际 Git commit 检查归档源码与回归测试是否被同时删除。A00 独立 Linux Bash/Git fixture **9/9 通过**，包括 source+test 同删、符号链接、非法 base SHA、缺项和真正失败测试。合法首次 bootstrap 只说 source 缺失，**不**计归档测试 pass；GitHub Actions 队列未当作成功。
- **A06 owner 开发分支代码已实际集成**：[PR #44](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/44) 合并进 `agents/A06-cpu-bandwidth-n0`，merge `94b48dd38098475f92c3849b974c9170e0b57307`（**不是 main**）。`cpu.stat` read-only period 观察改动 Git blob `dd1a8cfe65c60028500b88bf897e1ae7e47c8afb` 与独立固定 nightly 的被测内核源码相同；证据保留 [ktest](../results/organ-backend/2026-10-16/a06-cpustat-readonly-independent-ktest.json) **153/153 QEMU 内核测试**和 [guest](../results/organ-backend/2026-10-16/a06-cpustat-readonly-independent-qemu.json) **7/7**（1%/10%/FIFO/parent，raw guest exit33）。这是被测修复源码证据，A06 合并后整树未在本轮重跑，严格每窗上限、SMP、真实 HOS2/ioctl 仍未通过；A06 #18 保持 Draft。
- **A03 owner 目标整合，仍未合 main**：[Draft #48](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/48) 已经安全双父非强制合并至 `2262e85b98463c93e9de9b2c8bb314bf1852aed3`，以 A03 当时最新 owner `9e5d8007be915c981e665bae3ed0397b0564b94a` 为整合基础，保留原 original-owner authority、ResourceDomain 层级与 clock regression，加入固定 Hepta 完整 `StableId + Digest32` K 和 fail-closed `Option<u16>` status 变换。仅 3 个 A03 所有权文件，编写的集成测试合计 36 项，但 **本轮 Rust Cargo/fmt/Clippy/QEMU 均未运行**，不可代替 owner 持久 ACK 或内核 G1/G2。旧不同分支不得互相覆盖。
- **真实未解问题：**A05 仍只有 Linux 宿主 QueryAbi/ENOTTY 和 QEMU 拒绝证据，无五个原生内核控制操作；A07 仍须沿现有 Hepta durable operation owner 完成授权/撤销/unknown/reboot/retirement；裸机 CPU/GPU/Android/UI 也没有本轮验收。固定 Asterinas v0.19.0/`nightly-2026-07-21` 与 Hepta `f8c9419d` 未修改，根 README 始终严格0字节。

---


## 2026-10-16：A06 只读 cpu.stat 内核实测

- **跨周期超额结转已存在真实源码与测试记录：**A06 1kHz Draft [#18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 已包含 positive-overshoot debt 的 N0 实验；其此前独立证据显示原始完整 cpu.stat probe 在10秒1%场景约1.01–1.1%，较不结转时约2%更精确。该能力仍为单vCPU实验，非严格窗口上限或生产资格。
- **此次新增真实验收：**针对 [#44](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/44) 提出的 `CpuMax::observed_nr_periods(&self)`，将 `cpu.stat` 从会提前推进quota周期的 mutating `advance` 改成只读投影。使用精确源码 `ad55fecd95857f3e3c7cb5997118f7a44e5f5555`，固定 Rust nightly-2026-07-21 从源构建成功；完整内核ELF SHA256 `41cd6283facb4bf4ce1c7f60284c4433ba6d2777e73e54a58eaf5e1a4169fe43`。
- **独立客体结果：**保留原完整 `cpu.stat` 探针，QEMU q35/TCG x86_64 1vCPU 512MiB，无宿主网络/数据盘，**7/7** QEMU返回raw33：1%普通任务三次1.1%、1.1%、1.0%；10%普通任务两次10.392%、9.902%；SCHED_FIFO 10%=10.379%；父域10%/子域不限额=10.141%。此外 **aster-core实际内核测试153/153 pass**、0失败/过滤/软跳过、raw33。[证据与精确SHA](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/52) 已通过 [#52](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/52) 合并至 #44 的开发分支，**不是合入main**。
- **尚未闭合：**#44仍为Draft，需要A06把只读投影整合到自己的最新内核来源，处理cpu.max同时写入、周期迁移与锁序；SMP、多CPU复现、物理机及Hepta OS原生HOS2 ioctl、授权/持久K↔D/效果退役均未实测。不要把这里的N0 guest结果记为G1/G2放行。

---

## 2026-10-16：A00 本轮源码安全修复与真实验证增量

- **已合并测试源码（实际 main）**：[A05 PR #45](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/45) 合并 commit `54d5197bf66be23ea8b1f3ff5a3d2c40a82694b7`，修复 `tests/kernel/control/hos2_queryabi_probe.c` 将 EFAULT 等非 ENOTTY 错误误判为真实 `/dev/null` 拒绝的假阳性。A00 在独立 Linux x86_64 / GCC 14.2.0 宿主重建三份源码并逐文件比对精确 Git blob：`ae59693d54c375812dd522a1568c520a41c87e70`、`862a50fb8d9affd361510a2a2d9b29b6307f66ea`、`53aba3d3433b92a2d10b74136231db61f892ebb4`。`sh -n`、严格 C11 GCC、原生 `sh run-host-smoke.sh`、UBSan 和静态链接 selftest 均通过；旧处理在新负测下退出1，修复版通过。这仅是 **Linux 宿主** HOS2 负面探针，不是新内核 QueryAbi 实现。
- **A03 安全源码已推送、未合主干**：[Draft #48](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/48) commit `a10f0b8ddea9c1627469ab79b2f2e1ed551f3e79`，把 #35 真正 Hepta K（StableId+Digest32）和 #30 的 `OriginalOwnerAuthority`/伪造 ACK 回归整合为**两文件、19个无冲突精确补丁块**。源码/对象静态检查通过，但 Cargo、fmt、Clippy 和 QEMU 在本轮未运行，原 Hepta owner 的持久核验仍缺失；不得合入或宣称 G2。后续 #36/#37/#39 必须串行审查；#37 当前 stale `ReadUsage` 返回 `sample < window_start` 与 ABI 所要求的 `window_start=floor(sample/100ms)*100ms` 冲突，已向 owner 反馈，暂不捆绑。
- **A06 真实测试证据关联**：[Draft #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 当前 cgroup CPU blob `bce4cabfcc933af4107f7d892e735027b4acbd1e` 与 scheduler blob `a9767b2d037ba2e85243b5b498de814353f95178` 精确匹配此前独立构建的 #41 修复源码；其历史产物有 151 个实际 aster-core QEMU ktest、12 次正式 guest quota 检查及2次唤醒测试。**本轮未重新编译内核/QEMU**；cpu.stat 读可提前滚动未结算窗口的缺陷待 [Draft #44](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/44) 修复后实际内核复测。尚无真实 HOS2 CapSpace/ioctl、Hepta 持久退役、SMP/物理硬件验收。
- **CI 的真实状态：**G0 host-contracts 和 A01 host-evidence 的最新相关 GitHub job 持续 `queued`（issue [#33](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/33)）；不能当作通过。本轮 A05 小范围宿主修复以精确 Git blob 的独立实际执行作为合并依据，没有修改仓库保护规则、固定 Asterinas/Hepta 版本、根空 README 或生产服务。

---


## 2026-10-16：A00 合并定向 A01 回归、清理过时 ABI Draft，并核对真实 G1/G2 阻塞

- **本轮新增主干代码：**[PR #23](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/23) 已合并，merge `7d5121a41090dc74521de8a6a14d923d9dfc34db`，只新增 `.github/workflows/a01-boot-evidence.yml`，在相关路径变化时执行现有 A01 启动证据与 runner 的 Python 宿主对抗用例、空根 README 和上游锁校验；**不**把宿主 fixture 冒充内核构建或 QEMU。该提交的 [Actions run 38904246724](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/38904246724) 最近一次读取为 **queued / conclusion=null**，未记录为通过。
- **A02 现有事实：**完整 no_std Wire codec 已经由 [#13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13) 合入；旧初始 Draft #4 与之冲突，已保留历史并关闭（未合并）。主干 12 个黄金样本中读用量 sample=150ms/window_start=100ms/consumed=35ms，InstallBudget 和 terminal history 共用 effective=140ms/consumed=33ms；`tests/abi/test_mutations.py` 已包含针对 cap/expected_revision 的六项对抗测试。A00 对这些仓库字节执行 17 项独立 JS 结构/时间/漂移断言均通过，但**未在本轮执行 Rust Cargo、CI 或 QEMU**。
- **A03 单一资源域与安全边界：**主干源码检索只存在 `libs/os-control/src/lib.rs::ResourceDomain` 这一宿主模型定义；A05/A06 真实内核共享资源域未实现，不能声称已验收。主干已有悬挂前缀、错误 publisher 和连续退役负测；然而 `retire_through` 仍允许没有可信 original-owner 能力的 syntactically valid receipt，详见 [issue #28](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/28)。修复在未通过 exact-head Cargo 的 Draft [#30](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/30)，真实 Hepta StableId+Digest32 K 的主干类型纠正在 Draft [#35](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/35)；与 #36/#37/#39 的 A03 所有权补丁须串行整合。
- **G1/G2 保持未完成：**A06 真正的单 vCPU 1kHz 配额旧版曾有 QEMU 客体证据，跨100ms边界漏记/抢占计费的新修复 #41 仍需固定 nightly 的内核 ktest 和原始负载 QEMU；不得将 Draft #40 的不同欠账算法直接叠加。A05 仅有已合并 QueryAbi **Linux 宿主 ELF/ENOTTY** 探针，尚无 CapSpace/ioctl kernel；A07 尚未把 `kernel.authority` 的原 Hepta 持久 owner 与 D/撤销/重启验收接合。无本轮实机或新内核端到端验收。当前定向 CI 排队问题跟踪 [#33](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/issues/33)。

---


## 2026-10-16：跨周期 CPU charge 漏记修复待内核验收

- **可复现的源码问题：**当前 A06 1kHz 超额结转代码先执行 `CpuMax::advance(until)`，再按照已经更新的窗口起点记账，可能丢失线程跨越一个或多个100ms周期时旧窗口尚未记入的 CPU 时间。原有平滑负载 QEMU 结果不证明此极端时间交错正确。
- **回归代码：**[Draft PR #40](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/40)，分支 `agents/A06-cross-period-charge`，基于 A06 `4e23125a006dca5ce90d32cbab41c079b8da9a1d`，新增两项内核 `#[ktest]` 对抗案例，并在推进窗口前补记 `[from,until)` 中已完成周期的运行时间；修复提交 `03f1caed0f35aaed98d20cb12bce758e22a51124`。不变更 1kHz 全局定时器、HOS2 wire、Hepta owner 或 cgroup 资源结构。
- **实际验证分层：**从相应真实内核 `CpuMax` 实现提取纯状态机、以固定 1MHz TSC 仿真进行独立 `rustc --test`：**修复前 4通过、2新增测试失败（exit101），修复后 6/6通过（exit0）**；这是宿主数学/源码测试，尚非改后 Asterinas 的内核编译或 QEMU 通过。
- **实机验收阻塞：**尝试执行固定内核源码构建时，与另一个 A06 并发工作树的 OSDK/Cargo 生成锁出现 package collision；后续恢复验证时，执行机远程 tunnel 暂不可用，无法权威读取后续构建结果。**PR #40 保持 Draft，不会仅凭宿主测试合并或宣布配额精度已合格。** 同类实际 QEMU/ktest 验收应由 A06 owner 在受控环境复跑；原 A06 已验收的 9/9 QEMU 和145/145内核测试仍仅证明此前版本自身。
- **后续唯一修复路径：**同一个源码快照应完成 Asterinas nightly-2026-07-21 `make kernel`、`aster-core` 的新增 ktest 以及原始完整 `cpu.stat` 的 1%/10%/SCHED_FIFO/父域 QEMU；保留源/产物SHA与失败证据，审查当前预算窗口已被其他入口提前滚动时的延迟计费条件。完成前不合入 A06 或 main。

---

## 2026-10-16：1000Hz CPU 超额结转已通过客体验证并进入 A06

- **源代码与合并：**[PR #38](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/38) 已合并进 A06 **开发分支**，merge `d5741c7b7e2e17bb733d2d810408433da721b5a5`；原 `CpuControl.max` 的本地 IRQ 安全锁保留，OSTD 全局 `TIMER_FREQ=1000` 未改。对上一周期实际超额 CPU 消耗只结转正向欠额，并在后续周期抵扣，不储存未用额度；内核真实 `used_clocks` 与结转欠额独立。A06 主 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) **仍是 Draft，未合并 main**。
- **正式源码与客体：**最终代码已重新编译，release ELF SHA256 `9e3c106b88198a5dc1aef81c25392ab89aa3777831d17a852f869ab9747a0b59`；使用原始完整 `cpu.stat` 探针、q35/TCG、1 vCPU、512MiB。**9/9 QEMU 客体测试正常完成**：1% CPU 配额三次1.100/1.200/1.200%，10% 三次9.995/10.204/10.502%，SCHED_FIFO 10%=9.645%，父域10%=10.749%，50% 单次53.477%（不掩盖固定周期边界突发）。
- **长窗口对照与可复跑入口：**10秒实际QEMU对照中，原1%配额为2.000%，新方案为1.109%；原50%为51.146%，新方案为50.238%。新增 `tests/organ_backend/run_candidate_matrix.py --duration-seconds 10 --max-cpu-percent 1.5`，正式 ELF再次跑通1%场景，观测 **1.100%**。**Asterinas真实 `aster-core` 内核测试145/145通过**，含4项新增的超额结转/不存信用/不充值回归。原始数据见 [机器结果](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/agents/A06-cpu-bandwidth-n0/results/organ-backend/2026-10-16/a06-quota-debt-n0.json)。
- **去除并行路线：**5kHz全局升频实验 [PR #34](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/34) 已保留结果并关闭，不作为默认优化；无需提高所有工作负载的定时器频率。
- **仍未放行：**上述结果只支持单vCPU N0在观察窗口内的平均限制与无死锁；**不保证每个100ms周期的严格上限**。多CPU聚合与迁移、跨周期运行时间切分、资源控制器生命周期、硬件/能耗/尾延迟、HOS2 CapSpace ioctl、Hepta真实持久效果与Android/GPU仍待实际验证。不要将这次A06开发分支成果计作新内核已在main生产放行。

---

## 2026-10-16：N0 精度实验和 K↔D 主干接合

- **A03 本轮真实合并：**[PR #25](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/25)，merge `62d63809ee683402a90e7d15031e6d51a6eac133`。将 value-only 的 Hepta K↔D 绑定类型加入 Rust 宿主控制库；独立对 HEAD `755bbbe7eb6b492d21f69da80f41d93af97fba06` 完成 **21/21 Cargo 测试（1单元+20集成）、严格Clippy和fmt**，均通过。它不是 HOS2 真实内核持久操作，也不能凭 value-only identity 宣告已完成不可变摘要或 owner 认证；对应后续 PR 仍有单独验证。
- **A06 1kHz精度现状：**已经确认 IRQ-safe 锁合入 A06 自己的分支，修改后 q35/TCG、1 vCPU 原始 `cpu.stat` 探针不再死锁，但 1% 配置实测约1.9–2.0%，尚非严格1%保证；A06主 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 仍处 Draft，**未合并 main**。
- **5kHz 并行实验：**[PR #34](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/34) 在同类真实QEMU客体测试中，1%配置观测约1.100%、1.217%、1.163%；10%配置约10.152–10.355%。其对照中无限额1s循环迭代次数较1kHz约降低15.8%（非随机化TCG样本，不能推出真实硬件因果性能/能耗）。**不将全局tick直接从1kHz提高到5kHz作为生产默认。** 已向 PR 反馈更窄的跨周期超额欠账（overshoot debt）方案和原始探针的验收要求；这项方案**尚未写入内核源码**，曾遇到执行通道源码写入拒绝，不计已实现。
- **后续实际门槛：**A06 需保留1kHz基线，验证周期边界费用结算、降额不充值、低配额精度、静态/实时/父级预算及恢复；之后 A05 接权限与 HOS2 内核控制，A07 才能完成真实 Hepta K↔D 原有 owner 的持久确认/退役。不要把宿主状态模型或5kHz实验结果冒充生产OS能力。

---

## 2026-10-16：IRQ 重入修复已进入 A06（未合并主干）

- **修复位置和版本：**[PR #29](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/29) 已合入 A06 开发分支，实际合并提交 `6b7a4580f74add2b640b6ea948797bd87733faac`。原 `CpuControl.max: SpinLock<CpuMax>` 默认只禁止抢占；同一把锁会被定时器 IRQ 的 CPU 计费/资格检查路径获取。改为 `SpinLock<CpuMax, LocalIrqDisabled>`，保证持锁期间本地 IRQ 不重入。**A06 主 PR #18 仍是 Draft，未合入 main。**
- **真实 QEMU 证据：**在 A06 最新合并源码的相同 Git tree 上从源码构建 Asterinas 内核 ELF，SHA256 `8ff3629163438f86abe755aa5a61f3e8d53d2ab44994f41d006d04e3415d80a5`。使用固定 A01 initramfs、原始完整 `cpu.stat` 探针，q35/TCG、1 vCPU、512 MiB、无宿主网络/数据盘。**6/6 客体运行成功（raw33、无 panic）**：普通任务1%重复3次分别2.001%、2.000%、1.911%；普通任务10%=11.100%；SCHED_FIFO 10%=10.989%；父域10%/子域不限额=10.296%。[机器结果](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/f3bf18cfce246e48b985235bf7af1a45df987bcf/results/organ-backend/2026-10-16/a06-irq-safe-merged-matrix.json)。
- **受控对照：**原 WIP ELF 在1%下含 `cpu.stat` 读会超时；相同 ELF 的一次性探针仅跳过 `cpu.stat` 则 QEMU 正常退出、约2.1%。加上 IRQ 安全锁后，完整探针正常通过；N0 同时复跑了此前 8 次客体测试。历史失败记录保留下方，不再代表最新 A06 分支仍必然卡死。
- **尚未完成：**1% 实测仍约1.9–2.0%，不可宣称精确配额；SMP、cgroup迁移/生命周期、严格 lock order、HOS2 CapSpace/ioctl、Hepta 持久效果和物理硬件均未验收。main 尚无实际新内核 CPU 限额放行资格。只有继续修正 tick 超额和其他实机回归后才考虑合入 A06 主 PR。

---

## 2026-10-16 A06 实机配额阻塞与 A03 集成更新

- **新近主干改动：**A03 跨周期 `ResourceDomain::usage` 修复 [PR #16](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/16) 已合并，commit `04aacbefe037618229d4f2f0b1d4c92979abcf21`。在独立 Linux Rust 1.95.0 环境对该精确 PR HEAD `44b0cbd4ad2b88fa9dfe47aeb4f2c71803f641fd` 测得 **19/19 Cargo 测试通过**、Clippy `-D warnings` 通过、fmt 检查通过。属于宿主控制模型测试，不是内核节流实现。
- **A06 真实客体失败：**当前 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 为 Draft，HEAD `512e45d02b4ff544189b104cb36994f2edc588f4`。在它已编译的**修改后内核** `a2f72e2bc75d0490b658898697ced0532fe36395067939e3959f88dab051676e` 上，QEMU q35/TCG/1CPU/512MiB，运行一次性 guest cgroup 探针。基线 CPU `977ms / 1000.58ms`；`cpu.max=1000 100000` 写读成功、`/proc/self/cgroup` 归属正确，但客体在后续 `SYS_OPENAT/SYS_READ` 后停止前进；独立的 **45秒** 与 **15秒** 两次运行均超时。没有受限负载样本、没有 `ORGAN_PROBE_COMPLETE`、没有关机标记，故明确为 **failed_timeout**，不能计算配额符合率或认定 CPU cap 生效。
- **实测证据与沟通：**两个完整原始串口、精确 kernel SHA/guest argv、结果在授权执行宿主 `/home/qian-qi/.local/state/trillionnium-os-organ-next-20261016/a06-independent-probe/run/`，已在 [PR #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 留下失败细节与复现路径。源码定位首先检查节流队列何时在 tick 重新准入、idle 与被限线程的唤醒路径、锁顺序及未来周期唤醒；这只是待证实的故障归因，不宣称已经找到唯一根因。内核源码没有在本轮成功修改，PR #18 未合并。
- **下一真实闭环：**A06 在自己的分支修复任务长期不恢复的问题，先用同一 QEMU 探针取得受限 CPU 样本与正常关机，再测父子层级、CPU 调额不充值、非 fair 调度类、能力撤销与恢复；之后接 HOS2 ioctl 与真实 Hepta owner。独立应用和恢复服务不应受 Hepta 故障影响。

- **A06 官方 runner 的交叉复核**：独立拉取最新官方测试器 commit `7f5a3962c24d10deb8514b217a84e7c608185d45`，对同一修改后内核 ELF `a2f72e2bc75d0490b658898697ced0532fe36395067939e3959f88dab051676e` 执行 `run_candidate_matrix.py --mode leaf --quota-us 1000 --repeat 1`，得到 `qemu_exit=124`、`guest_complete=false`、`cpu_percent=null`；这是第三项独立超时。A06 的 10% 普通/FIFO/父域成功样本不能覆盖 1% 失效；该 PR 仍应保持 Draft。完整证据位于独立实验目录 `a06-official-1pct-independent/{result.json,serial-1.log}`，详细复现在 PR #18 评论。

---


## A01/A02/A03 已集成 — 2026-10-16

**主干代码基线（本段提交前）：** `c757c709652f9a9701765ff8a9e7c3026fc1019e`。这是源码与可复现验收的状态快照；不要把模块源码合入等同于 Hepta 原生 OS 可用。

| 范围 | 实际状态 |
| --- | --- |
| Asterinas 完整内核源码 | **已合入 main**：[A01 PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)，固定 v0.19.0、OSTD 和上游许可文件。 |
| QEMU 客体启动 | **已验证**：单 vCPU、q35/TCG、512 MiB、原始内核 ELF SHA256 `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63`，原产物独立重放 raw exit=33，BOOT_OK 和 CPU=1 标记成立；本次独立重放**没有**重新从源码构建。 |
| A01 OSDK 宿主回归 | **已合入 main**：[PR #15](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/15)，隔离 OSDK daemon 生命周期修复，按保留日志所列宿主单测 23/23、选定集成 13/13 通过；内核客体 362 reported、3 VMX/EPT soft skips，不代表 SMP/裸机/HOS2 验收。 |
| A03 Rust 控制模型 | **已合入 main**：[PR #12](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/12)。在合入前及合入后实际运行：1 单元测试 + 17 集成测试全部通过，严格 Clippy 通过。这是 `std` 宿主模型，**不是**内核 CapSpace/ioctl。 |
| Python HOS2 规格 | **14/14 通过**，是顺序模型，不是内核并发证明。 |
| A02 Rust no_std Wire ABI | **已合入 main**：[PR #13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13)，HOS2 2.0 no_std 字节编解码与固定 golden/negative 测试；对应 HEAD `5e3d56e0d15662b9d31f99ddf5e346796a5f6f82` 的 G0 scoped host CI 已成功，不代表内核 ioctl、CapSpace 或调度通过。 |
| 实际 CPU quota | **未执行**：一次性 Asterinas 客体内 `cpu.max=1000 100000` 写入/读回后，约 1s 墙钟仍消耗 998ms CPU。失败复现、日志和测试源码在 [PR #11](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/11) 与 [结果](../results/organ-backend/2026-10-16/)。 |
| HOS2 内核驱动/CapSpace/真实 ResourceDomain | **未实现**。A05/A06 应共用实际内核对象与调度限制，不能包装未执行的 `cpu.max`。 |
| A06/A09 实现与验收 | [A06 #18](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/18) 为 Draft、尚无新内核真实 CPU 1% 配额验收；[A09 #9](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/9) 为独立 GPU/VMM 模型 PR，真实 Rust 单测仍待 GH Actions 完成。[A00 #17](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/17) 已合入硬件范围的 Rust/CPU fixture CI。 |
| Hepta 的 OS 效果 organ | **未实现**。现有 `TrustedReadOnlyOrganV1` 禁止持有控制能力或执行 I/O；观测采集和效果执行需保持在既有 owner 接合。 |
| Linux / Android / GPU / UI | 各 Agent 继续维护独立 PR；宿主测试、硬件调查、用户态原型均不计新内核端到端通过。 |

**下一条真实工作：**以主干已合入的 A02 no_std Wire ABI 与 A03 控制模型为唯一参考实现；A05 接 CapSpace/ioctl、A06 在 ClassScheduler 公共计费/资格/节流/timer 层实现真正的 CPU cap（含非 fair 类与恢复），用完全相同的已提交客体探针证伪或验证；随后 A07 沿原 Hepta authority/operations/持久 owner 完成 K↔D、历史查询/退役及故障恢复。A01 的少量测试环境问题（OSDK daemon descendant、`/proc/self/exe`）与 CPU 机制缺失分别跟踪，不以形式化总关卡阻断无关开发。

---

## 历史状态快照（保留原有记录）

## A00 实际集成快照（2026-10-16，main = c1a22de12f3d95fd49227787601169b9f42fdf12）

- **已合并源码/回归**：[PR #11](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/11)，merge c1a22de12f3d95fd49227787601169b9f42fdf12：固定 A01 内核产物的 QEMU 客体运行了真实 CPU cgroup 反例（`cpu.max=1000 100000` 写/读成功；配置后 1.000 秒使用 998ms CPU），结论 **NOT_ENFORCED**，不是成功的 CPU quota。探针只改一次性 initramfs，不修改宿主 cgroup；原始客体串口与结果在 [results/organ-backend](../results/organ-backend/2026-10-16/)。对应 Python newc/archive 测试普通和 -O 各 5/5 通过。该 PR 不实现内核节流。
- **主干真实边界**：当前 main 尚未导入 `kernel/asterinas`，也无 `libs/os-abi` 或 `libs/os-control`（A01 [PR #5](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/5)、A02 [PR #13](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/13)、A03 [PR #12](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/12) 仍未合并）。A01 分支拥有 Rust 源码构建、QEMU boot 和 OSTD/aster-core 客体测试证据，但主干不继承分支验收。A02/A03 的 host Rust 测试不得记作内核 ioctl、权限或调度验证。
- **未解决**：A01 lock/source 验证与 OSDK 主机测试失败；A02 capability bit 依赖；A03 owner-ack 与跨周期核算；真实 A05/A06 CPU 限额执行及 A07 Hepta owner 到内核效果闭环。原 Hepta 操作 owner 仍是唯一持久事实来源；不得建立第二份 K 账本。
- **CI**：原定向 G0 工作流 GitHub Actions 仍处于排队状态，不能标记 pass。本轮仅在同一工作流中增加已合并的 `tests/organ_backend` 宿主安全回归，绝不将其视作 QEMU 验收。根 `README.md` 保持严格 0 字节，Asterinas/Hepta pin 未改。

---


> **A00 集成增量（2026-10-16，原文历史记录保留）**：从实际 main 3cc2f810eda93dab7411b62ef2f8f3830fbb1500 验证并合并 [A02 PR #1](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/1)，合并提交 3cc2f810eda93dab7411b62ef2f8f3830fbb1500；三份 N0 单 CPU 黄金样本时间修正：ReadUsage 125ms 时 consumed=25ms（降低后的 cap=20ms），InstallBudget 与 QueryDelivery 在 123ms 生效点 consumed=23ms。独立 Python struct 生成器 --check 检验 12 份样本，宿主 Python 格式/变异测试 6/6 通过；此前 14 场景顺序模型仍是模型，不是内核。A00 增加单条按路径触发的宿主契约 CI，Rust 项仅在对应 crate 存在时执行；记录的执行结果以真实 GitHub Actions 为准。尚无 Rust ABI / ResourceDomain 内核实现、项目 QEMU 新内核启动或 Hepta 端到端结果。原 Hepta 持久 operation owner 不变。根 README 0 字节。

2026-10-16；修订基线 `46a0e9f9ffa0e8289d0a1324d5dd8c9e6d6b7544`。本轮交付为 **recovery_contracts_and_spec_tests**，不是Rust内核实现。

## 已实际完成

围绕V201–V217修订关键文档，HOS2明确启动授权交接、CapSpace全局投递预约、独立DeliveryView、只读历史查询、有序写序列与连续结果退役。预算目标收敛不伪造旧操作终态；恢复责任不依赖Hepta自身健康；真实调度类、计时和计费点列为下一实现接合。

新增Python顺序规格场景，工作容器与执行主机分别运行同一源码SHA256 `8162883270a153ebf81f2cd4e0e05392c957fb439cfbb481239b35d75cab68de`，均为14测试、0失败、0错误、0跳过。10,000写/退役发生在模型内，不是内核benchmark；模型不提供并发或实际权限证明。[结果](../results/spec-recovery-v03.json)

新增12份独立Python struct生成的HOS2十六进制黄金样本，覆盖五操作请求/响应、历史退役和CAS拒绝；只核算布局，没有Rust codec消费这些样本。[样本](../tests/golden/hos2.json)

## 未完成与本轮实际阻塞

Rust库源码写入再次被执行通道安全检查拦截，工具仅报告无法确定请求安全状态。没有重放同一源码写入，也没有改权限或绕过检查。已确认无`.rs`文件；此前成功创建但没有实现对应的临时Cargo.toml已移除，不把空工程算交付。规格测试是独立的文档模型，不是被拒Rust编解码库的替代实现。

官方v0.19.0安装ISO下载在180秒上限内只获得74,026,432/1,442,840,576字节，curl退出28。完整文件未校验，未启动QEMU；部分文件的大小/摘要已记录后清理。执行主机检测到QEMU 8.2.2及可访问KVM，但这些不构成客体启动。[失败记录](../results/reference-iso-probe.json)

## 能力状态

| 范围 | 实际状态 |
| --- | --- |
| 文档恢复契约 | revised，待代码实现 |
| 顺序规格模型 | 14 passed；非内核/非并发 |
| 固定字节样本 | 12份；codec未测试 |
| Rust ABI库/普通客户端 | not_implemented；source_write_blocked |
| Asterinas源码导入/源码构建 | not_executed |
| 官方ISO完整下载/校验 | failed_timeout/not_verified |
| QEMU/裸机内核启动 | not_executed |
| Hepta端到端/Linux/Android/GPU/UI | not_tested |
| CI与生产资格 | not_claimed |

根README保持0字节；不再次删除仓库，不改hepta-private-ci、现役服务或硬件。source pin仍不等于完整build lock；upstream-lock中缺项和false保留。

## 下一项真实交付

优先完成获得执行允许的Rust源码写入及黄金向量测试，或补齐固定上游源码构建与真实串口启动结果；不能因这些规格场景通过就推进M1a/M1b实现状态。并行/设备/前驱恢复仍需对应真实环境，未决项不标为关闭。
