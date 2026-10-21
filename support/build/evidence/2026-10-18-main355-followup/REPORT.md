# A01：合并 main355 后的构建、启动与 ABI 验收

**实际源码 `40c901c6e189058bdd6f42bb43bf46b3bbcf8ffa` 已完成增量 `make kernel` → `make run_kernel`，QEMU raw exit 33；A02 现有 ABI 统一验收 13/13 通过。**

本轮工作期间 main 从 `b7a8388726b67394398431e74d2e5d2079ff375f` 前进到 `3551e1e0e017e2973da7e2b8ab811ece25c258c0`。新增 A02 响应语义会进入内核实际编译的外部 ABI 文件，因此 A01 先提交已经核验的冷构建证据 `b328b4176520ec96176bf8aa2db9c52318d95a04`，再普通合并这个 main 提交，并单独执行本报告的验证。

固定完整 Asterinas 源码获取、隔离依赖安装、第一次从空 target 构建和真实启动的完整链路见 [初次报告](../2026-10-18-current-main/REPORT.md)。本次原生工具沿用该报告的已安装环境；没有下载 NixOS ISO。本次 target 已存在，明确记录为增量构建。

## 源码和不可混用的执行范围

| 对象 | 本次事实 |
| --- | --- |
| 分支 / PR | `agents/A01-asterinas-boot` / [PR #22 → main](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22) |
| 本次实际执行源码 | `40c901c6e189058bdd6f42bb43bf46b3bbcf8ffa` |
| Project tree | `74641cbc46cd1213756e8128fab26928d374335a` |
| 两个父提交 | `b328b4176520ec96176bf8aa2db9c52318d95a04`；`3551e1e0e017e2973da7e2b8ab811ece25c258c0` |
| 唯一内核目录 | `kernel/asterinas/` |
| 内核 subtree | `6c2904e53e79cedbbaf013a73a6173f4afa57010` |
| 固定上游 | Asterinas v0.19.0，commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`，tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e` |
| 工具链 | `nightly-2026-07-21`；rustc commit `87e5904f5eb6398af6b22eac2802c78934260c48` |
| 实际外部 ABI SHA256 | `libs/os-abi/src/lib.rs`：`826e6533bd7ed2f6527db819e9f0400867ca1e607cd0581a03970444c3e4b60f` |
| 3,010 个 tracked 输入清单 SHA256 | `410b73b50cd2572d2afefda4ea73a8af884e204ba3d634996d58127677b942e8` |

合并的九个文件全部使用 main 的既有 Git blobs，没有自行修改 A02/A05/A06 的源码。`kernel/asterinas/kernel`、`kernel/asterinas/ostd` 和 `libs/os-abi/src` 均与 main355 一致。内核子树仍与初次报告相同，外部 ABI 已与旧 b7 不同；不能仅凭内核子树相同就把旧测试归入本次 producer。

本目录随后才作为证据提交，**其提交 SHA 不等于实际执行源码 SHA**。最终的证据、说明和锁文件更新不代表在最终证据 HEAD 又执行一次构建。上游许可证、署名和说明继续保留，项目根 README 为 0 字节。

## 实际构建与启动

```bash
cd /workspace/scratch/d7da9e7650f0/trillionnium-os-desktop
source /workspace/scratch/d7da9e7650f0/a01-runtime/env.sh
export CARGO_BUILD_JOBS=2
export A01_SMP=1
export A01_QEMU_TIMEOUT=300

A01_RUN_DIR="$PWD/support/build/out/2026-10-18-main355-followup/kernel" \
  support/build/kernel.sh kernel
A01_RUN_DIR="$PWD/support/build/out/2026-10-18-main355-followup/run_kernel" \
  support/build/kernel.sh run_kernel
```

新运行应选择不存在的输出目录。wrapper 实际调用上游 `make kernel` / `make run_kernel`，完整命令和环境保存在 [kernel/command.sh](kernel/command.sh)、[run_kernel/command.sh](run_kernel/command.sh) 及各阶段 `environment.log`，没有换成宿主 Linux 或安装器。

| 阶段 | UTC 时间 | 结果 |
| --- | --- | --- |
| 增量 `make kernel` | 03:29:03.859–03:30:07.512 | driver/make/log/cleanup 全部 0，实际重新编译 aster-core 及完整内核依赖 |
| `make run_kernel` | 03:30:08.011–03:30:11.007 | driver/make/log/cleanup 全部 0 |
| 实际 QEMU 客体 | 记录时长 0.967 秒 | raw/recorder exit **33**，无超时 |

完整原始日志： [构建](kernel/kernel.log)、[启动构建输出](run_kernel/run_kernel.log)、[串口](run_kernel/serial.log)。[execution.json](execution.json) 保存各阶段实际外层命令与时间。[qemu.json](run_kernel/qemu.json) 保存精确 argv、实际可执行文件与加载副本指纹、退出状态。QEMU 配置仍为 x86_64、q35、TCG、CPU max、**1 vCPU、512 MiB**、SeaBIOS、串口、isa-debug-exit，没有 ISO、数据盘或网络设备。

完整串口 72,331 字节，SHA256 `028f5736ac0a175f2b9409907f6cdc629cb70dfa9bcf0755abbe98c0bcf34d00`。以下标记各一次，无 fatal panic：

```text
OSTD initialized. Preparing components.
TRILLIONNIUM_A01_INIT_BEGIN
TRILLIONNIUM_A01_CPU_COUNT=1
Successfully booted.
TRILLIONNIUM_A01_BOOT_OK
```

| 实际输入 | 原始 bytes | SHA256 |
| --- | ---: | --- |
| 完整 boot ELF | 8,303,048 | `1eb66b33baef6b338c232598d25f743dc83526a2715811b430e5a7208e249ecd` |
| 小 initramfs | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

构建后冻结 ELF 与 QEMU 加载的私有 ELF 逐字节一致。[artifacts/README.md](artifacts/README.md) 说明保留的实际字节；ELF 与 BIOS 使用无损 gzip。来源映射见 [archive-source-map.json](archive-source-map.json)。这些 hash 与初次冷构建的 ELF hash 分别保留，没有把不同 producer 的产物混用。

## A02 现有验收入口

```bash
CARGO_BUILD_JOBS=2 python3 -B tests/abi/run_acceptance.py \
  --repo-root /workspace/scratch/d7da9e7650f0/trillionnium-os-desktop \
  --toolchain nightly-2026-07-21 \
  --output-dir /workspace/scratch/d7da9e7650f0/a01-runtime/review/a02-after-main-3551e1e \
  --timeout 60 --mutation-timeout 900
```

该入口不能加 `-I`，因为需要导入同目录模块。03:32:23–03:32:41 UTC 一次运行通过，外层退出 0。

| 既有检查 | 本次实际结果 |
| --- | --- |
| 统一 gate | 13/13 通过 |
| Python | 普通 60/60；独立优化模式 60/60 |
| Rust | 78/78，含 1 个 doctest，0 failed/ignored/filtered |
| 编译后变异 | 20/20 全部实际编译并触发预期测试失败 |
| Golden | HOS2 12、semantic edges 24、transport 1 个向量 |
| 格式 / Clippy / no_std | rustfmt、Clippy `-D warnings`、x86_64-unknown-none 全部通过 |

Python 的 9 项 mutation 子集包含在普通 60 项中，不再相加。Rust discovery 和 mutation 重跑也不另增普通测试分母。28 个 gate 输入前后相同、都与 producer 的 Git blobs 对应；原始快照明确只断言 **tracked clean**。结果见 [abi-summary.json](abi-summary.json)，完整命令、子命令输出、输入快照、变异结果和环境在 [abi-owner-gate.tar.gz](abi-owner-gate.tar.gz)。

旧 `c22891b` 的 OSTD/core 374 项报告通过（3 项 VMX/EPT 软跳过，实际执行通过下界 371）、86 项 host 构建测试与 45 项 OSDK host 通过继续属于 [初次报告](../2026-10-18-current-main/REPORT.md) 标明的源码范围。本次 main 增量没有重跑这两个内核测试 crate，不把旧计数归给 `40c901c6`。

## 测试后重新出现的临时 manifest

在构建前、构建后和启动后，3,010 个输入均相同且工作区记录干净，48 项 [独立核验](independent-review.json) 对此再次核对。随后 root 的 `source/after-abi.json.gz` 仍显示 tracked 输入完全对应 `40c901c6`，但完整 Git 状态记录了一个未跟踪的 `kernel/asterinas/kernel/OSDK.toml`。此状态原样保留，不能改称整个时段工作区都干净。

[原始观察](late-manifest/observation.json) 的该文件 inode 为 2003533，ctime 为 03:30:13.909 UTC；它不同于 kernel 阶段实际持有并清理的 inode 2003528，也不同于 run_kernel 的 inode 2003500。两个 wrapper 的 `manifest-cleanup.json` 均为 `owned_removed`；启动后的源码捕获于 03:30:11.5 完成。观察文件与默认 minimal manifest 字节相同，其 mtime 为 03:29:04.476 UTC。mtime/ctime 均早于 ABI gate 开始时间；这些事实不能单独识别创建者。

03:37:05 UTC，root 取得共享 native 构建锁，用稳定 FD 核对观察到的 inode 和 hash，然后将该未跟踪文件 **rename 到专用证据目录**；同一 inode 与原始字节保留，没有删除或覆盖它。实际事务见 [quarantine.json](late-manifest/quarantine.json)，脚本及原始文件也已归档。隔离后捕获的工作区干净，tracked 输入仍然相同。这恢复了本次工作区的构建入口，但**未知写入者的根因尚未查明**，不能据此声称执行环境已不可变或永远不会重现。

## 交接与真实剩余事项

当前 A05/A06 可用的完整接口表见 [HANDOFF.md](HANDOFF.md)。内核核心和 OSTD 保留 main355 原字节；本次仅合并 main 的 ABI 响应校验，不改变进程对象、ioctl 入口或调度器责任划分。

A01 所要求的完整固定源码 → 安装依赖 → Rust 构建 → QEMU 启动已真实完成，且新 main 合并后再次通过。仍需交接的实际范围为：A05 可信 capability 激活和四项效果/历史操作；A06 exit/reap/rmdir、迁移及 SMP final-debit 定向验证；A07 唯一持久 owner 与恢复；全项目 G1/G2。VMX/EPT、全量上游用户态/设备矩阵、裸机以及完整不可变宿主锁/跨宿主逐字节复现未验收。本工作区测试后出现的未知 manifest 写入者也未定位。

离线执行 `sha256sum -c SHA256SUMS` 检查本目录；解压 `artifacts/kernel.elf.gz` 后的 hash 应与上表一致。两个执行 producer、每次产物、原始工作区观察、失败记录与能力边界均独立保留。
