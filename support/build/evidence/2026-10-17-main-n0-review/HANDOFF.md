# A01 构建基础交接 v3（当前 native producer）

执行源码为 `fd0a5ed637312b13efdbfb6b670d4af52bd2c2b0`，tree `676fcaf53cc094bdd5d1ede25b8f13c8221b5e6d`；合入 main `dfe0ed04b4789d37d41854191126e710782baa3a`。完整内核在 `kernel/asterinas/`。固定 Asterinas v0.19.0/c4b7ed575b7b32773475b194d2ad41fb6d03765b 与 nightly-2026-07-21，不自行升级。保留上游许可证、COPYRIGHT、子目录文档和署名；根 README 保持0字节。

## 可直接开始的源码接口

| Owner | 接口/路径 | 当前范围与下一步 |
| --- | --- | --- |
| A05 | `kernel/asterinas/kernel/core/src/process/process/mod.rs` | Process 身份及生命周期；trusted CapSpace、process-start/exec epoch 等由 A05 继续，A01 不改核心实现。 |
| A05 | `kernel/asterinas/kernel/core/src/process/posix_thread/mod.rs`、`process/posix_thread/exit.rs`、`process/exit.rs` | 线程/进程退出与身份生命周期；同 CPU final debit 交界需与 A06/A00 协调。 |
| A05 | `kernel/asterinas/kernel/core/src/syscall/ioctl.rs` | 通用 ioctl 分派入口。 |
| A05 | `kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs` | 现有 `/dev/hepta/control` QueryAbi-only 设备；advertised mask 只含 QueryAbi，不授予执行权限。 |
| A05 | `kernel/asterinas/kernel/core/src/fs/file/file_table.rs` | 文件对象、dup/fork/close 与权限生命周期交接点。 |
| A06 | `kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs`、`sched/sched_class/fair.rs` | 调度类和记账接点；保持已进入 main 的本地先扣账与只读 cpu.stat 修复。 |
| A06 | `kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs`、`fs/fs_impls/cgroupfs/systree_node.rs` | quota、层级成员、cpu.stat、issue #63 final debit 与严格矩阵。 |
| A00 协调 | `kernel/asterinas/ostd/src/task/scheduler/mod.rs` | OSTD 底层 scheduler，与 A05/A06 的修改边界先协调。 |
| A01 | `support/build/**`、`support/upstream-lock.json`、既有 OSDK 构建配置 | 源码导入/校验、构建/启动/证据、SDK 私有安装、回归基础；不越权修改 core。 |

A05 可在现有真实 QueryAbi 路径上推进权限与 effect operations。A06 首先审核 `cpu.rs` 两个 ktest oracle 的奇数 period 修正，再真实重跑，然后补 final-debit oracle、每100ms/1和2vCPU/fair和RT的严格矩阵。原失败比错误期望多1个TSC clock tick；单位不是ns。执行从floor(P/2)开始，production 的end-from实际得到ceil(P/2)，而测试旧oracle用了floor(P/2)。A01没有改核心、没有应用proposal、没有放宽容差。当前单个1.0%样本与historical long-run平均不替代严格断言。A07持久owner G1/G2仍须自己的真实验收。

外部 `owner-tests-only-proposal.patch` 只建议将两个测试期望改为：

```rust
assert_eq!(budget.carry_debt_clocks, period - period / 2 - quota);
let expected = period - period / 2 - quota + 4 * (period - quota);
```

该patch尚未应用，原core151通过/2失败/raw65的记录不变。整数triage在Python -I/-I -O各检验52701个case，相同结果；这是host数学复核，没有执行Rust/VM、没有穷尽u64边界。建议A00/A06在自己的权限范围审核应用，并用实际core guest重跑再验收。P/Q的具体数值来自失败整数与源码公式推断，不应冒充本次core VM实测TSC频率。另一次OSTD boot的频率不得代入。

## 在已配环境复现普通源码构建与启动

以下是复现命令说明，本文档任务未执行它们。用新 worktree 与新输出，勿改正在运行的 target：

```bash
git -C /workspace/scratch/ae1a8cf05419/trillionnium-os-desktop worktree add --detach \
  /tmp/a01-native-reproduce-fd0 fd0a5ed637312b13efdbfb6b670d4af52bd2c2b0
source /workspace/scratch/ae1a8cf05419/round-current/env.sh
cd /tmp/a01-native-reproduce-fd0
export A01_RUN_DIR=/workspace/scratch/ae1a8cf05419/reproduce-fd0-build
bash support/build/kernel.sh kernel
export A01_RUN_DIR=/workspace/scratch/ae1a8cf05419/reproduce-fd0-boot
bash support/build/kernel.sh run_kernel
python3 -B -I support/build/check-boot.py \
  /workspace/scratch/ae1a8cf05419/reproduce-fd0-boot --live-artifacts
```

两个 A01_RUN_DIR 必须尚不存在，不预先 mkdir。worker 持有稳定 `out-kernel.lock`；busy 时不会创建 output。`kernel.sh` 调用实际上游 `make kernel` / `make run_kernel`，叠加单一 minimal.mk，不要求完整 NixOS ISO。

环境只修改任务 shell。CARGO_HOME/RUSTUP_HOME 指向该任务 `toolchains/cargo` / `toolchains/rustup`；依赖前缀为 `env-recovery/native-tools/root`；vDSO 为 `env-recovery/linux-vdso`。A01_QEMU_BIOS 与 A01_QEMU_DATA_DIR 分别指向私有 SeaBIOS 和 QEMU ROM 数据目录，QEMU 必须实际带 `-L`。如环境恢复后路径改变，应重做依赖身份/源码验证和 native 证据，不能仅替换日志中的路径。

实际普通 ELF 来自 `kernel/asterinas/target/osdk/asterinas/asterinas-osdk-bin.elf`，由同目录 bundle.toml 确认；不要使用不存在的 `target/x86_64-unknown-none/release/asterinas`。本轮 ed469 完整哈希及完整 argv 已在 REPORT/ordinary 原始记录中给出。`actual-ordinary-qemu-command.txt` 是完成运行的原始命令快照，不是承诺旧临时路径永久存在。

## debug、ktest、OSDK 入口

```bash
python3 -B -I support/build/debug/run.py --output /absolute/new-debug-output \
  --nm /usr/bin/x86_64-linux-gnu-nm
python3 -B -I support/build/ktest/run.py --output /absolute/new-ktest-output
python3 -B -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb \
  --output /absolute/new-osdk-output
```

本轮debug已command0/GDB0/detach/raw33/source-clean，入口PC `0xffffffff8841ed80` 的32字节绑定完整符号与实际启动ELF；详见REPORT。ktest已完成但仍失败：OSTD221报告通过/3软跳过/218实际通过下界/raw33；core151通过、2失败/raw65，child和外层均1，异常后的源码postguard未执行。OSDK本轮22项报告通过/0失败/0blocked/1VMX软跳过，child/外层0且postGit干净，11次示例guest raw33；这是工具/示例矩阵，不替代完整Asterinas验收。不要添加 `--skip-osdk-install`。normal/debug/ktest使用本次output的私有SDK root，不接受另一个checkout编译的全局cargo-osdk冒充。

debug 使用 TCP GDB；AF_UNIX EPERM 仍开放。normal/debug/repro 的进程组清理持有 leader WNOWAIT identity，最终组信号后才 reap；worker EXIT cleanup 的2s预算有限，超限残留由下一次构建拒绝覆盖。外层 controller 的取消 grace 应大于2s，实际本轮为5s，避免先杀掉仍在收尾的嵌套 supervisor。任意脱离 owned group 的后代 containment 未建立。

## QueryAbi 复现与 owner 限制

本轮root controller将未改动 `tests/kernel/control/queryabi_guest.c` 的断言运行在新ed469 ELF上；owner C源码SHA256为 `399bb7c815ea6dd2dc908e6f621bfc39c031b50f854f0fba43511f045dbb0544`。编译命令保留 `-std=c11 -O2 -Wall -Wextra -Werror -static`，guest注入最小initramfs，TCG/1vCPU/512M，三次raw33。QueryAbi retry phase child0/controller passed=true/source-clean；enclosing combined tool session44537因之后CPU probe失败最终为1，不能把phase成功写为enclosing tool0。

可在保留完成 ordinary 证据的任务环境使用 root 的源码绑定 controller：

```bash
source /workspace/scratch/ae1a8cf05419/round-current/env.sh
export A01_NATIVE_CHECKOUT=/tmp/trillionnium-a01-native-fd0
export A01_NATIVE_OUTPUT_ROOT=/workspace/scratch/ae1a8cf05419/native-isolated
python3 -B -I /workspace/scratch/ae1a8cf05419/round-current/queryabi-native.py \
  --producer fd0a5ed637312b13efdbfb6b670d4af52bd2c2b0 \
  --output /absolute/new-queryabi-output
```

该 controller 校验完成 ordinary receipt 与 ELF 字节；新的环境需先建立自己的对应记录。它与 owner 原来硬固定旧 ELF 的 replay 入口分开；不修改 owner 断言、不扩展设备支持的 operations。A06 当前 candidate runner 的 isolated sibling import、workflow ELF 路径与私有 ROM 入口还需 owner 修复；不得写成严格 CPU 矩阵已通过。

## 固定 QEMU 的 owner probe v2 复现

本轮已使用未改动的两个owner脚本，在新普通ELF上各运行两次：1CPU raw33两次、1.001%/1.1%；2CPU raw33两次、0.822%/0.9%。配置quota1000us/period100000us、CLI请求 `--duration-seconds 1`、显式max3%。restricted实测wall interval单CPU为1099269967/1000225763ns，双CPU为2797054263/1999040082ns；未建立实际固定1秒窗口。四次均显式Python adapter exec固定真实QEMU并带 `-L`，完整launcher/adapter/原owner source/C/helper前后guard与实际argv已保留，controller postGit干净。该工作绕开临时文件执行位，不依赖PATH fallback；没有修改owner源码。

在已保留普通构建证据的环境中，外部root controller入口为：

```bash
source /workspace/scratch/ae1a8cf05419/round-current/env.sh
export A01_NATIVE_CHECKOUT=/tmp/trillionnium-a01-native-fd0
export A01_NATIVE_OUTPUT_ROOT=/workspace/scratch/ae1a8cf05419/native-isolated
python3 -B -I /workspace/scratch/ae1a8cf05419/round-current/run-native-v6-pinned-owner.py \
  --producer fd0a5ed637312b13efdbfb6b670d4af52bd2c2b0 \
  --phase probes --label reproduce-probes-pinned
```

label必须是未使用的新basename。唯一pinned-probe controller入口为上述 `run-native-v6-pinned-owner.py`，SHA256 `7e3bb794d423169f7e5d7c123704502a6273db2202ad22b30aff9a2a40d1bcd4`，与实际完成记录对应。它绑定已完成 `ordinary/first-kernel.elf`，经 `owner-probe-launch-v2.py` 保持两个原owner入口字节/断言不变，仅适配确切的QEMU subprocess调用。launcher SHA256为 `ab209ea699a525c8b453518c8db1e3a65c63ddd2c5dc560383d86d9a4508ac23`；adapter template为 `a5f31f89726370860758d8675f44132d5fa8908b8997cd339b76a63d373fa189`。

上述结果只通过原owner在实测wall interval上的显式3%有限比例界，CLI请求1s不等于实际固定1秒窗口；四条串口均明确输出 `ORGAN_CPU_VERDICT=INCONCLUSIVE_REQUIRES_TIMING_VALIDATION`。1.1%并不能证明严格1%。保持 `smp_qualified=false`、`hepta_hos2_qualified=false`，每100ms严格上限、RT、最终记账与G1/G2仍由owner验收。正常SystemExit0不是失败，四次launch无timeout。原owner workflow中的 `-I` sibling import和错误ELF路径尚未因此被改好。

## 交接验收记录

本轮ordinary、QueryAbi retry、TCP debug、OSDK工具/示例矩阵及固定QEMU的四次有限owner诊断已通过；ktest仍保留151/2/raw65真实失败，尚无应用oracle proposal后的guest重跑。源码CAS桥/独审/host数学和fixture独立记录。旧D1/K、跨实例R/A4/C4及main内owner results作为各自原producer的历史证据保留。执行源码fd0已非强制推送；后续证据/metadata提交SHA与新exact-head CI只记PR最终回读，不能用旧head190次host CI或原owner日志替换。A00/A06具体交接已发布：[PR22评论](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6230648819)。全项目blocker未全部关闭。
