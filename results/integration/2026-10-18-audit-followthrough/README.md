# 2026-10-18 审计后实现、集成与实际验证

本记录对应审计后的代码推进：修复独立 HOS2 判定器和 namespace receipt 生命周期，修复未回收 zombie 的最终 CPU 配额扣费，将原生 Rust 桌面及既有原版 Hepta 观察链路合入主干，并更新当前模块入口。它记录本地真实执行和固定来源的证据复核；GitHub Actions 的结果另列，历史运行没有改记成新执行。

## 发布与源码身份

| 部分 | 实际本地源码 / tree | 远端对应与集成 |
| --- | --- | --- |
| A02/A03 组合 | `a0adc97b35264510fb2056bed93d46c155ffe5ff` / `2f391cae63211e7d607d188205cf91b997077b3e` | [PR #185](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/185)，发布 `1c3241f81b5d319968ab46d3e3aa9329fed04068` 与 main `4339acedd2d433f838c7b5fd445709c539043a77` 均为相同 tree |
| A06 最终修复 | `e97a30c923b1a27e1578eaaf6b39d85fe1aa5591` / `c70e97c30b6a7808586c1a2a7db4a6860ede004e` | [PR #188](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/188)，发布 `9265235c4b4f375844c923cf0b0f517d119d9937` 为相同 tree，已合入 main `8ea35f55a38949f511f0855cd168dfd1d672acc8` |
| A07/A10 完整本地门禁 | `be335eba60f9a511a78ff8e3af90a043d50855e2` / `58fa519a927624c2cc091f295e337492d31b68a6` | 后续 `0d873e1d2d280d228f9f5a136d7d85c0912a2662` 仅添加六行 CI paths；本地 `adf17fc7c2c90caca44b9267aec528c8bc5870ca` 仅再合入 main 的三份文档 |
| A07/A10 发布与主干 | 最终集成 tree `d7daa0984b6ca59bb59c93e5659fc67affebdc33` | [PR #187](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/187)，发布 `36067459b464a11818e4cf47ca47d54557cd2306` 与 main `9a858dceb3a0ede6c3a021b9d16f3bf41e8503d5` 均为相同 tree |
| 全部代码的本地组合 | `236c996bf407f0c8be286037022c31b8964884ec` / `6eb10ba7fa117a6669350be6be9467a7052feae8` | 对 A02/A03、A06、A07/A10 的 15 个目录或文件 Git 对象逐项核对，全部保持各自已验证输入；组合后另实际执行 35 项规格/源码回归，全部通过 |

相同 tree 证明文件内容与模式相同，不表示 commit、父提交或执行时刻相同。A10 owner `45552fbd8f79ea713509908ac4b08a3fd44a95bc` 和 R6 `89aa8fa62d30b00259cb33174260c134edf1a70b` 的历史均保留。#3 已随主干集成标记 merged；#157 的完整内容经 #187 进入 main 后关闭，其原 owner 分支未覆写。[文档 #186](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/186) 的模块盘点与原始 R6 记录也保留。

本节整合之后只增加当前文档和本次文本证据。文档提交不授予新的二进制运行资格，根 `README.md` 按既有约定仍为 0 字节。

## A02

主干 #181 已修复 Rust codec，但独立 Python 判定器仍接受六类已知反例：遗漏 prior-window CPU 上界、接受尚未预约的“不可能终态”，以及允许保留最大序号进入不合法状态。本次补齐独立判定器并增加合法边界与拒绝回归；没有用 Rust 的输出替换独立 oracle。

新增测试首先在旧 oracle 上得到 8 项预期失败；修复后，最初六个固定 wire 反例全部被拒绝。最终完整 `tests/abi/run_acceptance.py` 在 `nightly-2026-07-21` 下实际完成 **13/13 检查**，`success=true`、`not_executed=[]`、原始输入前后不变。包括 golden/edge/transport、Python 发现与普通/优化执行、Python 变异、Rust 发现与真实执行、fmt、严格 Clippy、bare no_std 和实际编译变异。Python ABI 普通与优化模式各 **62 项**；13 是验收步骤数，不能解释为 Rust 用例数。

压缩包内 `implementation-a02-acceptance/report.json` 保留命令、工具链、输入 hash、检查输出和错误；`mutations.json` 保留实际变异矩阵。原 G0 中复用这些结果前，对 28 个 A02 输入逐项比对；并非在每次文档或合并提交都重新跑相同任务。

## A03

原 receipt 用 namespace 的分配地址作为实例身份。`HistoryAck` 是可复制的值，不保留原 namespace 的生命周期；旧对象全部释放、分配器复用地址后，即使 boot/space/owner 字段相同，旧 ACK 仍可能配合新实例的合法 authority 错误退役新 terminal。

本次使用**进程内不复用的 namespace instance tag**：全局原子计数器提供非零身份，计数耗尽时拒绝创建，不回绕、不回收。保留已有 original-owner authority 边界与 Copy API。真实 Rust 回归覆盖旧 namespace 释放并重新创建的情况；旧实现曾返回成功退役，新实现拒绝。

| 实际检查 | 结果 |
| --- | --- |
| std / portable-spin | 两种后端各 **225 passed** |
| 两种后端严格 Clippy、fmt | 通过 |
| 既有 Loom 原模型 | **19 个模型 / 27,253 个调度**；模型和生产输入保持不变 |
| 既有锁内分配探针 | **19 个实际场景**，alloc/realloc/dealloc 全为 0 |
| `x86_64-unknown-none` portable-spin rlib | 实际交叉构建通过 |

压缩包内 `implementation-receipt-evidence/loom/`、`lock-alloc/` 是原探针结果；`implementation-tools/integration-control.log` 和 G0 日志补齐组合代码的执行记录。集成复用 Loom 的 12 个输入、allocation 的 9 个输入均核对一致。宿主 receipt 绑定没有实现原版 durable K/fsync，也不构成密码学签名、跨进程授权或原生设备效果证明。

## G0 与组合验证

原 `.github/workflows/g0-contracts.yml` 的 **16 个 run block 全部有有效结果**：13 个新执行、3 个在输入相同条件下复用已执行结果。`implementation-g0-evidence/summary.json` 记录 `success=true`、`source_unchanged=true`、原脚本与逐项来源。

实际范围包括：62 项 Python ABI、35 项规格回归，archive 安全模型普通/优化各 5 项，A05 真实 host wire、`/dev/null` ENOTTY、注入 EFAULT、固定 replay 普通/优化、x86_64 静态 guest probe 编译，以及 A03 两种后端的构建/lint/交叉构建。**编译 guest probe 不等于运行 guest**；这一轮 G0 不能替代原生驱动或设备效果验收。

新增 CPU 修复与已通过的桌面主干组合后，`implementation-final-evidence/composition.json` 独立比对 15 个源码输入对象，全部相同；35 项规格/源码回归实际通过。无需将未变化的所有 Rust/内核构建重复执行一遍来生成相同记录。

## A06

缺陷位于 `charge_task_cpu`：退出已清空 Process cgroup，但父进程仍保留 zombie `Arc`，Weak 升级成功，旧逻辑会回落 root，漏记旧叶子及中间祖先的最终 quota/debt。现在先读取 RCU binding，再读取 zombie 状态；**有 Process binding 时保留原归属**，只有已 detach 的 zombie 或已回收 Process 才使用线程保留的 lease。这样同时保留迁移发布窗口内已有的归属行为。

没有向 scheduler/IRQ 路径添加 membership mutex，没有创建第二份账本。`cpu.stat` 的 jiffies usage 是另一条路径，本修复不宣称已修复或验证该路径。

六项新增 ktest 使用真实、尚未启动的 Process/Task 对象和真实 cgroup membership 调用生产扣费入口，覆盖未回收/已回收尾账、存活迁移、旧快照、退出但未 detach 的非空绑定，以及跨窗口正债务。

| 最终源码实际运行 | 结果 |
| --- | --- |
| 完整 aster-core 正向 | **159 passed / 0 failed / 0 filtered / 0 soft skipped**；159 个实际 test start；QEMU raw exit 33 |
| 仅恢复旧生产条件的负对照 | **157 passed / 2 intended failed / 0 filtered**；只有未回收 zombie 尾账与跨窗口债务用例失败，新增非空绑定用例通过；QEMU raw exit 65，无 timeout |
| 正向 ELF SHA256 | `50e78cb6284ae6d7a54e49d34e944a3f072c8cedac05b60ce634be9a9f5de0b6` |
| 负对照 ELF SHA256 | `700e3b3750fa42aa05b7e90e80af12f7e1e431720dbc8a2a1a04c084c9f0428e` |
| 非 ktest 生产内核 | 实际 release 链接通过，SMP 构建参数 2，耗时 6m22s；8,305,512 字节，ELF SHA256 `edce11ac22903da6b7b65295fb75bf07f364f227a5f7e327b489381df9500399` |
| 现有 1 vCPU 探针 | 两次实测 CPU 0.769% / 1.000%，均 complete、无 panic、raw QEMU 33，runner exit 0 |
| 现有 2 vCPU / 2 pthread 探针 | 两次实测 CPU 0.550% / 0.960%，均 complete、无 panic、raw QEMU 33，runner exit 0；未限额并行基线满足原有 >145% 条件 |

四次 probe 使用同一个固定生产 ELF，保持原有 `1000/100000 us` 的 1% 配额配置与 3.0% 接受上界。收据仍明确 `smp_qualified=false`、`hepta_hos2_qualified=false`，不修改宿主 cgroup；这些有限样本没有升级为一般 SMP 或完整 Hepta/HOS2 资格。原始结果为包内 `implementation-a06-evidence/probe-1vcpu/result.json` 和 `probe-2vcpu/result.json`。

双核未限额样本按原始 getrusage / wall-clock 数值得到约 184% / 213%；本轮沿用的是 >145% 并行基线条件，不据此提供精确 CPU usage、`cpu.stat` 校准或严格 1% 硬上限保证。原始纳秒读数完整保留，计时精度和一般 SMP 计费需要独立验收。

负对照前后测试文件 SHA 不变，自动恢复钩子在结果分析前恢复生产源码并检查 tracked tree 干净。此前较宽的 158 项实现、受控失败和一次 E0599 编译失败分别保留：编译失败没有启动 guest，不能算负对照通过；较早 158/158 结果没有转记为修订后 159 项的执行。

生产构建另有一个已记录的清理观察：wrapper 返回 0 后，执行环境中仍可见一份未跟踪的 `kernel/OSDK.toml`，与固定临时模板逐字节相同。本轮先保存残留内容和 hash，再手动移除；后续切换执行环境时旧 mtime 的相同文件与 pycache 又可见。源码追踪尚未证实是 wrapper 或 probe 重新生成，不能据此断言脚本存在删除缺陷。`production-build/temporary-manifest-cleanup.json` 及后续双环境检查保留事实；手动清理与自动 cleanup 的结果分别记录。

上述 ktest 在固定 x86_64 QEMU q35/TCG、1 vCPU、512 MiB 下运行。它们不调用完整用户态 exit syscall，也不穷尽 SMP 迁移/退出交错。最后非主线程移出 TaskSet 后与迁移交错的线性化合同仍需单独处理；新测试不授予一般 IRQ/SMP 生命周期或 rmdir lease 资格。

OSTD、OSDK、ktest 支持、生产 lock 和工具链输入与既有 A06 基线相同，见 `source-scope.json`。本轮没有重跑未变化的 OSTD。历史 [run 39089584115](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39089584115) 的 221 个声明通过包含 3 个 VMX soft skip，实际执行下界为 218；这组历史数字与本轮 159 项不相加。

## A07-A10

当前主干包含全 Rust Shell、persistent Session、CLI、独立 AppWindow，以及原版 Hepta 只读观察接合和随附手册。实际完整本地门禁在 `be335eba` 上执行，使用 Rust 1.88.0；后续只有 CI 路径和主干三份文档变化。

| 实际门禁 | 结果及限定范围 |
| --- | --- |
| `tests/ui/check-host.sh` | **151 passed / 0 failed / 2 ignored**：UI workspace 87，Hepta client 17，消费最新 HOS2 的 support/ui 39，UI 契约 8 |
| 原版 process / capture 契约 | Python **6 + 8 passed** |
| 真实 host 边界 | runtime/lock owner、双向 SO_PEERCRED、伪造 Session、8 类非法 IPC、真实 child reap、socket 代际、打包正反例及真实 ELF 解包重放通过 |
| `tests/ui/headless-weston.sh` | Weston 13 下 Shell/3 个 app 的首次布局、Shell 重启、观察到的取消通过；真实 compositor 重启后同一 Session、socket epoch 更新及新 client 首次布局通过 |
| 实际 X11 | 私有 Xvfb 下 Shell 与 3 个独立应用均 IsViewable，重启/lifecycle 通过；本机未安装 scrot，没有新增 X11 framebuffer PNG 资格 |
| 格式、严格 lint、lock | 四个 manifest fmt、all-target locked/offline Clippy `-D warnings`、332 packages 的 locked/offline metadata 均通过，锁文件不变 |
| 六行 workflow 修复 | YAML 解析、20 个实际依赖路径/事件选择通过；active workflow 与历史模板缺失的路径补齐 |

两个 ignored 是原有需要 `TRILL_UI_TEST_CJK_FONT` 的真实字体测试。软件 Wayland 没有证明 compositor 像素呈现、物理显示、GPU、IME 或移动端能力。compositor 丢失后旧 client 失败，没有证明原窗口 surface 无损重连；本轮 Hepta 页布局采用明示的 scripted UDS fixture，没有新启动原版 Agentd。

首轮 `435eb3b` 的同进程 flock 恢复测试失败被保留。确定性 pipe barrier 复现证实：fork 后、exec 前的子进程可暂持继承的 open file description；只 drop 父进程 File 并不等于全部描述符关闭。新测试在独立 Rust owner 完成 exec 后取得真实锁，验证活 owner 拒绝、SIGKILL、wait/reap 和重取。变更仅在 `cfg(test)`，生产前缀 22,703 字节未变；保持普通并行测试，生产锁语义没有改变。

四个本轮实际重建的生产 ELF，在测试修正前后逐字节相同：

| ELF | SHA256 |
| --- | --- |
| Session | `f53896a56a3fbc3227ae6f59e7151b532ec2a0d50995dea9fee7f38453ef8793` |
| Shell | `b1386de379a9b961d7de044f9b57c01f642d222d665ed4b4b38665617e1679f8` |
| CLI | `4efe6a720cd6ef61f4a2871ff7dbe980572e55ce3e431e21bcf9c6c77d09152b` |
| AppWindow | `f433b7a684318592c4c9dfbff01e9bf28bdabbd834e3bb719654e64c20c1fc11` |

完整字段、日志、源码对应关系见包内 `implementation-hepta-review/a10-integration-summary.json`。本轮测试源文件改变后，不能再宣称旧 M0 的 11 个完整 Git 对象全部相同；生产前缀/闭包和本轮重建 ELF 的相同性单独记录。

### 原版 Hepta M0 的历史复核

本轮对固定原版 `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 的既有 R6 归档做独立复核：**324 项文件 SHA、两轮六阶段、12 张成功 PNG、24 份前后 Session 快照**全部核对，另保留一次失败 PNG。每轮在同一 Rust Shell PID/XID 下观察原版启动、运行、排空、原版重启后的 stale、显式新 Session 恢复，以及原版停止后的 stale。

资格为 Linux x86_64 私有 Xvfb 中，固定原版 Hepta → 持续 Session → 同一 Rust Shell 的只读生命周期观察。没有本轮原版 ELF 重建、模型 turn、ObjectiveStart 或设备效果执行。新旧六阶段的最后 Running/Draining 样本不同属于原始运行时序，不能当作 UI 修复造成的效果。固定历史入口：[R6](../../../tests/integration/hepta/evidence/2026-10-17-r6/README.md)、[同 Shell 原图与快照](../../../tests/ui/evidence/2026-10-17-original-hepta-shell/README.md)。

## 原始证据、CI 与剩余边界

- [原始文本证据包](audit-followthrough-text-evidence.zip)与 [SHA256](audit-followthrough-text-evidence.zip.sha256)：包含原命令、stdout/stderr、失败、来源清单和 JSON；包内 `MANIFEST.json` 对每个文件给出大小与 SHA256。验证时同时检查 ZIP CRC 与逐文件 hash。没有重复放入 ELF、构建目录或已有的原版 PNG。
- [机器索引](execution-index.json)：关联来源、实际结果、最终主干代码、压缩包与 GitHub 读回。原始日志中的本地路径是执行位置，不能当作另一个人机器上可直接使用的安装路径。
- 实际复跑入口沿用 `.github/workflows/a02-pinned-host-acceptance.yml`、`.github/workflows/a03-native-models.yml`、`.github/workflows/a06-kernel.yml`、`.github/workflows/a10-host.yml` 及对应 RUN 文档。压缩包保留执行时的精确命令与环境，不引入第二套产品运行流程。

**GitHub 快照：2026-10-18 04:32:48 UTC。**原始 API 读回保存在包内 `implementation-final-evidence/github-final-snapshot.json`；下面只对应三个精确 PR head，不把结果转记为之后的 merge 或文档提交。

| 精确 PR head | 线上结果 |
| --- | --- |
| #185 `1c3241f8` | [A02](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39094060165)、[A03](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39094060158)、[G0](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39094060159)、[CodeQL](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39094058499) 均 completed / success |
| #187 `36067459` | [A10](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39095995767) queued；[原版 ARM](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39095995747) in_progress；[CodeQL](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39095993913) queued |
| #188 `9265235c` | [A06](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39096189453)、[A01](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39096189401)、[G0](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39096189388)、[CodeQL](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39096188023) 均 queued |

全部实现已合入 main `8ea35f55a38949f511f0855cd168dfd1d672acc8`，tree `6eb10ba7fa117a6669350be6be9467a7052feae8`，与本地组合验证 tree 相同。本地测试与 GitHub workflow conclusion 分开记录；未改变分支保护、required checks 或 workflow 门禁以换取合入。后续的文档与证据提交不改这组代码输入。

下一条产品主线仍是既有 Hepta owner 下的可信 ObjectiveStart 与真实任务工作区，并以既有 issuer、状态/持久 owner 接合确认、撤销和结果；不创建第二套授权或效果账本。完整 HOS2 设备执行、原版 durable K↔D 的端到端桌面接合、Android guest、物理驱动、Asterinas 显示/输入、IME 与移动端另设实际验收。内核继续采用固定 Asterinas/OSTD 的受控修改路径，本次工作没有启动一套自研 Rust kernel 重写。
