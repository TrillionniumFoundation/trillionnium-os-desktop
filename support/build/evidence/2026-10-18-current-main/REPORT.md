# A01：当前 main 的完整 Asterinas 源码构建与真实 QEMU 启动

**2026-10-18，本轮已完成：固定完整源码获取与核验 → 隔离依赖安装 → Rust 内核构建 → 小 initramfs 的实际 QEMU 启动。**

实际执行源码是已推送的 `c22891b593f77c98ff4ea94d7aecb54f32222651`。`make kernel`、`make run_kernel` 均返回 0；QEMU 实际加载本轮生成的完整 Asterinas ELF，客体完成 initramfs smoke 后以 raw exit **33** 退出。随后两组内核态测试报告 374 项通过，其中 3 项因 VMX/EPT 能力不可用而提前跳过，实际执行通过下界为 **371**。

本目录是执行结束后添加的证据。其提交 SHA 与上述执行源码 SHA 不同；本报告不声称在后续证据提交上重新编译或重跑。这一边界也记录在 [source/summary.json](source/summary.json) 和 [独立复核](independent-review.json)。

## 1. 分支、来源及代码所有权

| 项目 | 核验结果 |
| --- | --- |
| 仓库 | [TrillionniumFoundation/trillionnium-os-desktop](https://github.com/TrillionniumFoundation/trillionnium-os-desktop) |
| 分支 / PR | `agents/A01-asterinas-boot` / [PR #22 → main](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22) |
| 本轮开始时实际远端 main | `b7a8388726b67394398431e74d2e5d2079ff375f` |
| 本轮执行源码 commit | `c22891b593f77c98ff4ea94d7aecb54f32222651` |
| 执行源码 project tree | `af19f57a5e275fb8712363d90e72eca88477ec3e` |
| 执行源码内核 subtree | `6c2904e53e79cedbbaf013a73a6173f4afa57010` |
| 单一完整源码根 | `kernel/asterinas/`，vendored Git tree |
| 固定上游 | Asterinas **v0.19.0** |
| 上游 commit | `c4b7ed575b7b32773475b194d2ad41fb6d03765b` |
| 上游 tree | `96605cf64aeae2d34f29b97e85eff9315fe10a8e` |
| 固定工具链 | `nightly-2026-07-21` |
| rustc | `1.99.0-nightly`，完整 commit `87e5904f5eb6398af6b22eac2802c78934260c48` |
| Cargo | `1.99.0-nightly (3efb1f477 2026-07-17)` |

本地分支从本轮取得的 main 创建，再普通合并远端既有 A01 历史 `bb34933fb2f7dc8bceffbce8f42e342799c96e6e`。执行源码提交的第一父提交为 main，第二父提交为既有 A01。推送使用预期旧 SHA 检查及非强制更新，保留两边历史。

合并仅需协调 `support/build/kernel.sh`：保留 main 的 `A01_SMP` 参数透传和 A01 既有的私有 OSDK、工作区锁与日志/清理行为。正常最小 profile 默认仍为 1 vCPU。本轮保留 main 的 OSDK `RUSTUP_TOOLCHAIN` 传递修复。`kernel/asterinas/kernel`、`kernel/asterinas/ostd`、`libs/os-abi/src` 与上述 main **字节及 mode 完全一致**，没有改动 A05/A06 已接手的核心源码。

完整 Git 对象核验见 [upstream-comparison.json](source/upstream-comparison.json)：原始导入提交 `7081fb9b34030af47b7a65d4e62a00fcf147de05` 的内核子树与上游 tree 完全相等；上游 2,938 个文件全部仍在，2,908 个未改、30 个派生修改，另有 3 个新增文件，没有原文件缺失或类型/mode 漂移。85 个按 LICENSE/COPYRIGHT/NOTICE/README/AGENTS 名称选择的许可与说明文件保持原字节。项目根 `README.md` 为 **0 字节**。

固定输入核验器通过全部 118 项，见 [kernel/source-inputs.json](kernel/source-inputs.json)。主内核 `Cargo.lock` SHA256 为 `6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316`；工具链文件 SHA256 为 `b2508d8c9cd57258fad2fc77737e07172846161f6a7dd726cbd8e974de69c6f7`。既有派生 OSDK 的 host FD 保留依赖继续使用批准的独立 manifest/lock 指纹，未升级上游内核或 Rust pin。

另保存 3,010 个内核、外部 ABI 和构建输入的完整清单。构建前、构建后、启动后和 ktest 后均干净并与同一 Git 对象对应，清单 SHA256 一致为 `36d3f324138eb079ceb994d0a190828b202bacd4c29e162ff14272313123a832`。其中核心实际通过 path module 编译的 `libs/os-abi/src/lib.rs` SHA256 为 `0de94affd479cecd692de000cc4ab97f5ce7453d81dc0dcd46c7db2e67fa35ec`。该清单独立于只检查固定构建输入的 118 项核验，具体选择范围和脚本均在 `source/`。

## 2. 实际依赖安装与构建路线

宿主为 Ubuntu 24.04 x86_64。本轮开始时缺少 Rust、QEMU、Docker、Nix 和 KVM。57 个原生 Ubuntu 包经 APT download-only 获取、核对签名源中的包 SHA256，再用 `dpkg-deb --extract` 解包到工作目录。没有对宿主执行包安装、系统盘操作或服务/固件修改。

| 实际输入 | 本轮版本 / 来源 |
| --- | --- |
| Rust | 固定 nightly；安装 rust-src、rustc-dev、llvm-tools-preview、rustfmt、clippy，以及 x86_64-unknown-none target |
| cargo-binutils | `0.4.0`，`cargo install --locked`；rust-strip 使用该 nightly 的 LLVM 22.1.8 |
| QEMU | `8.2.2`，Ubuntu 包 `1:8.2.2+ds-0ubuntu1.18` |
| SeaBIOS | `1.16.3-2`，256 KiB BIOS 文件 |
| BusyBox | 静态 x86_64，`1.36.1-6ubuntu3.1` |
| 原生工具 | clang/lld 18.1.3、GDB 15.1、cpio、pkg-config、OpenSSL 开发输入 |
| APT 源 | 已签名 Ubuntu snapshot `20260828T000000Z` |
| vDSO 依赖 | `asterinas/linux_vdso` commit `8af571775a3d3a1df3e84fc9709b9d6b160c771a`，tree `8e0a300d78c2a020ccc79f1253bc27a8301416e6` |
| Docker / Nix | 不可用；本次实际采用原生开发者路线 |
| initramfs | 25 个 newc 条目，静态 BusyBox + 项目 init + 原上游 `boot_hello.sh`；未下载 NixOS ISO |

安装脚本、原始安装日志、工具实际路径/版本/指纹、APT 签名与 Rust manifest 在 [runtime.tar.gz](runtime.tar.gz)，说明见 [RUNTIME.md](RUNTIME.md)。18 个运行环境检查成功，其中 QEMU `-S` 仅检查机器与动态依赖可加载；真正的项目内核启动在下节独立记录。宿主原有工具和部分共享库仍被使用，以上记录不是完整不可变宿主依赖锁。

## 3. 实际构建、启动命令及结果

本轮实际路径和环境入口如下。每个 `A01_RUN_DIR` 必须不存在；复跑应使用新的目录名。

```bash
cd /workspace/scratch/d7da9e7650f0/trillionnium-os-desktop
source /workspace/scratch/d7da9e7650f0/a01-runtime/env.sh
export CARGO_BUILD_JOBS=2
export A01_SMP=1
export A01_QEMU_TIMEOUT=300

A01_RUN_DIR="$PWD/support/build/out/2026-10-18-current-main/kernel" \
  support/build/kernel.sh kernel
A01_RUN_DIR="$PWD/support/build/out/2026-10-18-current-main/run_kernel" \
  support/build/kernel.sh run_kernel
```

入口确实执行原上游 developer targets；[kernel/command.sh](kernel/command.sh) 和 [run_kernel/command.sh](run_kernel/command.sh) 保存未缩写命令。其共同结构为：

```bash
make -C kernel/asterinas -f Makefile -f "$PWD/support/build/minimal.mk" \
  kernel  # 启动阶段为 run_kernel；各阶段的完整变量见 command.sh
```

`minimal.mk` 替换 initramfs 前置条件并提供固定最小启动配置。每阶段从同一 checkout 的 locked OSDK 源码安装到该运行目录的私有 prefix，随后由上游 OSDK 编译及启动完整内核。

| 阶段 | 时间 UTC | 实际状态 |
| --- | --- | --- |
| `make kernel` | 03:02:50–03:05:53 | 183 秒；make、driver、日志捕获、manifest cleanup 全部 exit 0 |
| `make run_kernel` | 03:06:50–03:06:52 | make、driver、cleanup 全部 exit 0；QEMU raw **33**，无超时 |
| QEMU 客体 | 记录时长 0.917 秒 | 完整 Asterinas + initramfs init + 上游 smoke + 关机 |

初始 `kernel/asterinas/target` 不存在，收据为 [source-before-root.json.gz](source-before-root.json.gz)。内核和 OSDK 日志包含真实编译；依赖/工具链已预先准备。`run_kernel` 使用刚生成的编译缓存。第一阶段冻结的 ELF 与 QEMU 实际加载的私有 ELF 副本完全一致；这是一次从空内核 target 构建并启动的链路。

完整原始日志是 [kernel/kernel.log](kernel/kernel.log)、[run_kernel/run_kernel.log](run_kernel/run_kernel.log) 和 [run_kernel/serial.log](run_kernel/serial.log)。编译警告保留，没有通过修改 owner 核心文件消除警告，也不声称全量 Clippy 零警告。

### 实际 QEMU 配置与启动证据

精确 argv、工作目录、可执行文件 hash、实际加载副本路径与前后指纹、退出码和超时字段保存在 [run_kernel/qemu.json](run_kernel/qemu.json)。固定配置为：

```text
x86_64 / q35 / TCG / CPU max / 1 vCPU / 512 MiB
SeaBIOS / multiboot ELF / small initramfs
-nodefaults -no-user-config -no-reboot
-nographic -display none -monitor none
-serial chardev:serial
-chardev stdio,id=serial,signal=off,logfile=qemu.log
-device isa-debug-exit,iobase=0xf4,iosize=0x04
```

没有 ISO、数据盘或网络设备。`A01_QEMU_BIOS` 指向工作目录中的 SeaBIOS，`A01_QEMU_DATA_DIR` 提供 QEMU ROM 搜索目录。原始 append 字符串含上游组合产生的重复 console/environment 项，收据按实际 argv 保留，没有事后归一化。

串口中以下五个标记各出现一次，没有 fatal panic：

```text
OSTD initialized. Preparing components.
TRILLIONNIUM_A01_INIT_BEGIN
TRILLIONNIUM_A01_CPU_COUNT=1
Successfully booted.
TRILLIONNIUM_A01_BOOT_OK
```

raw exit 33 是客体成功关机后的 isa-debug-exit 状态，OSDK 将它转换为 make exit 0。客体 `/proc/version` 的 Linux 5.13.0 文本来自上游为 glibc 兼容定义的 UTS 常量，源码位置是 `kernel/core/src/net/uts_ns.rs`；QEMU 加载对象明确是本轮 Rust 源码生成的 Asterinas ELF，宿主 uname 仅记录在环境日志中。

### 保留的实际启动产物

| 输入 | 原始 bytes | 原始 SHA256 |
| --- | ---: | --- |
| 完整 boot ELF | 8,310,560 | `208caf5126c94f660292aacd36040ec62c9d317b116b9a861634f08cb02cd8f3` |
| initramfs.cpio.gz | 1,107,990 | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| SeaBIOS | 262,144 | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| 完整串口 | 72,331 | `b661e07581dc7e7f9caa0ba104c6e5f3c3ef844dc24a28e278ee772896903b53` |

ELF、initramfs 和 BIOS 实际字节保存在 [artifacts/](artifacts/README.md)。ELF/BIOS 仅作无损 gzip；表内列出解压后的 hash。原文件与归档映射见 [archive-source-map.json](archive-source-map.json)。

## 4. 本轮实际回归

两组内核测试使用本轮 `c22891b`、固定工具链及源码 OSDK，未设置测试过滤。执行命令为：

```bash
export A01_KTEST_TIMEOUT=300
python3 -I support/build/ktest/run.py \
  --output "$PWD/support/build/out/2026-10-18-current-main/ktest"
```

| 回归 | 本轮结果 | 原始记录 |
| --- | --- | --- |
| OSTD 内核态 | 报告 221 pass，0 fail，0 filtered；3 项因 VMX/EPT 不可用而提前跳过；实际执行通过下界 218；raw33 | [结果](ktest/ostd/result.json)、[完整串口](ktest/ostd/guests/guest-001/serial.log) |
| aster-core 内核态 | 153 pass，0 fail，0 filtered，无软跳过；raw33 | [结果](ktest/aster-core/result.json)、[完整串口](ktest/aster-core/guests/guest-001/serial.log) |
| 合计 | 报告 374 pass，实际执行通过下界 371；driver exit 0；03:07:33–03:09:28 UTC | [ktest/result.json](ktest/result.json) |
| 构建工具 host 回归 | boot evidence 29、ktest private inputs 5、source inputs 10、kernel runner 42，共 **86 pass** | [host-results.json](host-results.json) |
| 派生 OSDK host 单元测试 | **45 pass，1 项原有 ignored，0 fail，0 filtered**；前后源码 HEAD 明确为 c22891b | [host-regressions.tar.gz](host-regressions.tar.gz) 内 `review/osdk-unit-c22891b/` |

86 项 host 回归是在提交前的 main + A01 合并工作树执行。原收据未记录当时 HEAD，不能追记成已经在 c22891b 执行；13 个当时已记录的输入 hash 与 c22891b 的对应 Git blobs 相等，范围见 [host-regressions-source-equivalence.json](host-regressions-source-equivalence.json)。单独的 optimized Python 模式 29 + 5 项也通过，不重复计入主 86 项。

最初默认沙箱下的 kernel-runner 测试在创建 socket 的宿主 fixture 中收到 `EPERM`，错误日志原样保留。经正常批准的执行环境重跑后 42/42 通过；没有修改测试断言或安全策略。OSDK 唯一既有 ignored 项是 opt-in 的真实 QEMU monitor transport probe，本轮未把它计为通过。更早 PR 中的 GDB/OSDK 集成、CPU/QueryAbi 探针和复现矩阵属于各自旧 producer 的历史证据，本轮没有将它们追记成当前源码的新结果。

## 5. A00 / A05 / A06 交接与真实边界

完整接口表、符号和责任范围见 [HANDOFF.md](HANDOFF.md)。A00 可以据本轮真实证据接收最小内核构建/启动入口；A05/A06 可直接在完整内核上继续工作。

- **A05：** `kernel/core/src/process/process/mod.rs` 的 `Process`、exec epoch/capspace session；`process/execve.rs`；`process/process/init_proc.rs` 的可信 init 接合位置；`syscall/ioctl.rs` 的分派；`device/misc/hepta_control.rs` 的 `/dev/hepta-control` 与实验命令 `0xC0204802`。目前只读 QueryAbi 路径已编译；本次小 init boot 未运行定向 ioctl 探针。可信能力激活及 `ReadUsage`、`InstallBudget`、`QueryDelivery`、`RetireThrough` 的真实效果仍未完成，四项当前返回 `EOPNOTSUPP`。
- **A06：** `kernel/core/src/sched/sched_class/`、`fs/fs_impls/cgroupfs/controller/cpu.rs`、`process/posix_thread/mod.rs` 的 `CpuCgroupLease` 及 `cgroupfs/systree_node.rs` 的末次计费租约。main 已有 final debit 源码，本轮完整保留并编译。exit/reap/rmdir、迁移、SMP 锁序与严格窗口需要 owner 定向客体验证；本轮通用 ktest 和小 init boot 不代替这些场景。
- **A01：** 继续负责 `support/build/**`、`support/upstream-lock.json` 和上游来源/构建配置；共享 OSTD 或固定上游版本变化由 A00 协调。

当前 **A01 最小构建/启动链路没有剩余 blocker**。项目层面的可信能力/效果操作、A06 完整生命周期/SMP 验收、A07 唯一持久 owner 的 K↔D/恢复，以及 G1/G2 仍未由本轮关闭。TCG 环境没有验证 KVM/VMX/EPT；全量上游用户态/设备矩阵、裸机、Android/GPU/生产服务、跨宿主逐字节复现和完整不可变宿主锁均不在本轮通过范围。

## 6. 离线核验与复跑

在本目录执行 `sha256sum -c SHA256SUMS` 核验归档文件。`gzip -dc artifacts/kernel.elf.gz | sha256sum` 应得到上表 ELF hash。`runtime.tar.gz` 与 `host-regressions.tar.gz` 都含自己的原始文件映射和内部 checksum 清单；解压时可选择独立临时目录。

需要精确复跑时使用执行源码 commit `c22891b593f77c98ff4ea94d7aecb54f32222651`、记录的 nightly 和依赖，设置新的输出目录，再执行第 3 节命令。`runtime.tar.gz` 中安装脚本和 env 使用本次绝对路径，是本次环境的实际记录；其他宿主需调整工作目录及包来源可用性，并重新记录实际输入。普通可用 Ubuntu 开发机也可使用仓库的 `support/build/prepare-host.sh` 准备依赖；`--apt` 选项只适用于明确选择安装系统包的 disposable host。本轮实际使用的是私有解包路线。

完整原始执行日志保留绝对路径与原退出码。`source/upstream-fetch.command.json` 明确记录了为持久证据重复获取同一上游 Git 对象的时间，未伪装成构建前的首次获取。独立审核对已有记录重新计算 hash 并验证关联，没有另行启动客体或将同一运行重复计数。
