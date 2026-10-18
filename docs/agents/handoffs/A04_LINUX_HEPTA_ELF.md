# A04 Linux / Hepta ELF 开发与交接入口

路径核对基线：2026-10-18 的本轮候选 `09cf259676e2a81a998c14f1e1fddf4cc94b80df`，基于实际 main `f9e306f76154590e096a42f70ce9de0a7c859e60`；这两个输入均未包含下述 A04 实现目录。
A04 候选固定为 `25c681d944e4efa92f2772cf773e03ae811bc345`，来源为 [PR #8](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/8)。
本手册由 A00 协调，实现与测试工具 owner 为 A04；本次只核对源码、命令入口和既有材料，没有重新构建、运行 ELF 或启动 QEMU。

**主干尚无 `compat/linux/`、`support/rootfs/`、`tests/workloads/linux/` 三个目录。下文 A04 命令只能在固定候选的独立 checkout 根目录执行。**
主干已有 A01 构建入口、Asterinas 源码和 A05/A06 实现；这些模块的进展不能代替 A04 对相同 ELF 的差分验收。
完整规范仍见 [Linux 兼容规格](../../LINUX_COMPATIBILITY.md)，完整候选手册分别为：

- [工作负载、构建、Linux 参照与 guest 重放](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/tests/workloads/linux/README.md)。
- [rootfs 捕获、清单、USTAR 与严格提取](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/support/rootfs/README.md)。
- [按来源和 owner 分类的缺口与历史交接](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/compat/linux/GAPS.md)。

## 1. 实际源码及职责

以下表中的路径均相对**固定 A04 候选**，并非已存在于当前主干。

| 路径 | 实际职责与输出 |
| --- | --- |
| `tests/workloads/linux/probe.c`、`sqlite_probe.c`、`run.py` | 编译 `probe_dynamic`、`probe_static`、`sqlite_dynamic`、`sqlite_static` 四个 ELF，执行 28 个 C 工作负载；另运行三个 Python 案例和一个 Rust/Tokio 案例。报告记录 ELF SHA、`PT_INTERP`、`DT_NEEDED`、逐项事实、退出码与 `pass/fail/not_run`。 |
| `tests/workloads/linux/workload_catalog.json`、`catalog.py` | 固定 32 项名称、命令向量、接口与资源释放事实，并校验 Linux 参照的分母。 |
| `tests/workloads/linux/rust/{Cargo.toml,Cargo.lock,src/main.rs}` | 独立 Tokio 工作负载，验证线程、异步任务、AF_UNIX 和文件读写；不是原版 Agentd 或替代执行 owner。 |
| `support/rootfs/capture.py`、`manifest-debian13-x86_64.json` | 捕获可信 ELF 的 loader/已观察到的共享库、NSS、公共 CA 和合成配置；生成逐文件字节/模式清单及 USTAR，或严格验证、提取已有归档。 |
| `tests/workloads/linux/staged_rootfs.py`、`chroot_replay.py`、`host_guest_rehearsal.py` | 分别验证显式 loader、原 Linux chroot、实际生成的 guest shell 编排。宿主内核均仍为 Linux。 |
| `tests/workloads/linux/guest.py`、`replay_qemu.py` | 校验固定 A01 输入、封装新的 initramfs、实际启动 QEMU、解析 serial 与逐项观测；输出新运行的输入绑定和资格。 |
| `compat/linux/compare.py` | 比较相同 ELF、loader、退出码和完整可观察事实，输出 `match/partial_match/incomplete/fail` 及差异、阻塞项；不比较合法调度的全序。 |
| `compat/linux/hepta-profile.json`、`trace-hepta.sh`、`trace_summary.py` | 原版 Hepta 来源和历史 host composition/依赖调查；私有实际 trace 与可发布摘要分离。静态依赖记录不是完整 W1 闭包。 |
| `tests/workloads/linux/test_*.py`、`baselines/*.json` | 主机回归、严格解析与输入/清理负例，以及各次真实执行或阻塞的独立记录。 |

主干接合位置是 [A01 构建手册](../../../support/build/README.md)、[A05 实现手册](A05_KERNEL_CONTROL.md)、[A06 CPU owner](../../ASTERINAS_CPU_BANDWIDTH_N0.md)、[A07 Hepta 接合](../../HEPTA_INTEGRATION.md)。
A04 提供最小复现和差分事实，不在本模块复制内核、调度器、Agentd 或效果账本。

## 2. 依赖与固定输入

历史 Linux 参照绑定 Debian 13 / x86_64、Linux 6.18.44、GCC 14.2、glibc 2.41、SQLite 3.46.1。
A01 内核上游与工具链由主干 [upstream-lock](../../../support/upstream-lock.json) 固定为 Asterinas v0.19.0 / `c4b7ed575b7b32773475b194d2ad41fb6d03765b` / `nightly-2026-07-21`；当前派生源码与下表历史 ELF 仍需分别绑定。
构建需要 Python 3、GCC、`readelf`、可信输入上的 `ldd`、glibc/SQLite 的开发头及静态库；包来源记录使用 `dpkg-query`。
NSS/TLS 案例还使用本地 Python `sqlite3`/`ssl` 和 OpenSSL。它们没有请求外部模型或真实业务数据。
精确包版本及重建差异见 [原 rootfs 输入复核](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/tests/workloads/linux/baselines/exact-rootfs-input-recheck-20261017.json)。

Tokio 直接依赖固定为 `=1.47.1`，候选 `Cargo.lock` 的 SHA-256 为 `b38d7f2ae2d70dcd07bc58b5ecf050ae1d3ab19eb08acb4559f1a0c5929a1e42`。
`run.py` 使用 `cargo build --offline --locked --release`；必须先有匹配工具链和已准备的锁定依赖。
候选历史构建收据记载 Rust 1.99.1，但运行因宿主 AF_UNIX 策略被阻塞；不能用当前 UI 的工具链或一次编译成功替代该工作负载的实际运行。

固定重放还要求以下输入；这些 SHA 是历史 profile 的身份，不能仅为容纳新产物而改写：

| 输入 | 固定 SHA-256 |
| --- | --- |
| Linux 参照 `baselines/linux-debian13-x86_64.json` | `ea38aa903ead1f72683ab10dcefeb756ec8b1e115dfccf49d8a9823c8a968026` |
| rootfs 清单 `support/rootfs/manifest-debian13-x86_64.json` | `55aa8369d4f912267139ef7626c752814d7dc833e49accc337529f2545fb94cb` |
| 扩展的 17 文件 USTAR | `df8df2e3cdcd308ef62a59268a4519e2923c9ff78145e46f26a4092725e80797` |
| 该重放器接受的 A01 解压后 kernel ELF | `e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63` |
| 原 A01 `initramfs.cpio.gz` | `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3` |
| QEMU 可执行文件 | `8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854` |
| SeaBIOS | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |

当前主干保留 `support/build/evidence/2026-10-16/artifacts/{kernel.elf.gz,initramfs.cpio.gz}`；路径存在仍须核对原字节，不能换成最新 kernel ELF。
固定四个 C ELF 的 SHA 由清单和 Linux 参照双重绑定。2026-10-17 曾使用记录中的 Debian 包版本重建，四个 SHA 仍不相符；该收据明确 `full_replay_eligible=false`。
因此，“源码、发行版或版本相同”都不能替代缺失的原 ELF/rootfs 字节。

## 3. 在独立候选 checkout 构建和验证

从本项目的已有 checkout 获取固定对象并创建新 worktree；将示例绝对目录换成实际未使用的目录：

~~~sh
git fetch origin 25c681d944e4efa92f2772cf773e03ae811bc345
git worktree add --detach /absolute/new/a04-candidate 25c681d944e4efa92f2772cf773e03ae811bc345
cd /absolute/new/a04-candidate
git rev-parse HEAD
~~~

确认输出为固定候选 SHA，再在已准备依赖的原 Linux 测试环境执行以下命令。`a04_work` 是此次独立输出目录，不能复用旧收据：

~~~sh
a04_work=$(mktemp -d /tmp/a04-handoff.XXXXXX)
python3 tests/workloads/linux/run.py --rust auto \
  --binary-dir "$a04_work/elf" --output "$a04_work/linux-reference.json"
python3 -m unittest discover -s tests/workloads/linux -p 'test_*.py' -v
python3 -O -m unittest discover -s tests/workloads/linux -p 'test_*.py' -v
python3 compat/linux/compare.py \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --candidate "$a04_work/linux-reference.json" --proven-only \
  --output "$a04_work/linux-diff.json"
~~~

逐条保留实际命令、退出码、stdout/stderr、来源和产物摘要。`--rust auto` 可把缺 Cargo/离线依赖等记为 `not_run`；它不是补全 Tokio 的途径。
需要该案例的完整执行时使用 `--rust required` 并解决真实依赖/宿主权限；不得删除该项或缩小分母。
`--no-build` 只表示使用预先提供的四个 ELF，仍必须由独立参照验证字节。

使用本次可信 ELF 捕获**新候选 profile**：

~~~sh
python3 support/rootfs/capture.py --root "$a04_work/rootfs" \
  --manifest "$a04_work/rootfs-manifest.json" --tar "$a04_work/rootfs.tar" \
  --binary "$a04_work/elf/probe_dynamic" --binary "$a04_work/elf/probe_static" \
  --binary "$a04_work/elf/sqlite_dynamic" --binary "$a04_work/elf/sqlite_static"
python3 support/rootfs/capture.py --root "$a04_work/rootfs" \
  --manifest "$a04_work/rootfs-manifest.json" --verify
~~~

这只能证明本次文件与本次清单一致。若与第 2 节原摘要不同，就保存为新 profile，不能覆盖固定清单或喂给旧重放器冒充同一输入。
需要 chroot、guest shell 编排或 syscall trace 时使用上面的完整手册：`chroot(2)` 需要专用环境的相应权限，不能充当网络/PID 隔离；原 trace 可能包含路径和数据，保存在新的私有目录，Git 只归档经审查的摘要。

## 4. 固定输入的实际 QEMU 重放

只有取回第 2 节固定 USTAR、匹配的 A01 两份输入以及固定 QEMU/SeaBIOS 后，才能在**同一候选 checkout**运行：

~~~sh
python3 tests/workloads/linux/replay_qemu.py \
  --a01-kernel-gz /absolute/verified/A01/kernel.elf.gz \
  --a01-initramfs /absolute/verified/A01/initramfs.cpio.gz \
  --qemu /absolute/verified/qemu-system-x86_64 \
  --firmware /absolute/verified/bios-256k.bin \
  --rootfs-tar /absolute/verified/a04-rootfs.tar \
  --rootfs-manifest support/rootfs/manifest-debian13-x86_64.json \
  --reference tests/workloads/linux/baselines/linux-debian13-x86_64.json \
  --out-dir "$a04_work/qemu-evidence" --timeout 180
~~~

`--out-dir` 必须是新目录；`--rootfs` 与 `--rootfs-tar` 二选一。重放器校验清单、分母、QEMU 字节和固件，创建新的 initramfs，使用单 vCPU / TCG，不接宿主磁盘、网络或 KVM。
它保留本次 serial、raw QEMU exit、`run-status.json`、guest 观测和差分报告。输入/环境阻塞不能用旧 A01 serial 补齐。
该入口固定历史 A01 ELF，不是任意当前主干 kernel 的通用 runner；重放成功也只归属于实际使用的那个内核。

## 5. 输入、输出与错误契约

| 层次 | 接收、判定与错误含义 |
| --- | --- |
| 工作负载 | C ELF 接收固定 case 名和私有 scratch 路径；Python/Tokio 使用各自的合成输入。外部 ELF 案例通过要求限定时间内完成、预期退出、空 stderr、严格单行 JSON 和真实状态不变量；重复 JSON key、非有限数值或额外输出不能变成成功。Python 函数案例的返回事实与异常另由报告记录。 |
| Linux 报告 | `run.py` 的 `overall` 为 `passed/partial/failed`；`partial` 可返回 0，所以进程退出 0 不代表 32 项全部通过。报告的 `counts`、逐项 `facts`、`build_error`/catalog 错误须一起查看。 |
| 同 ELF 差分 | `compare.py` 对不同 ELF/loader、退出码或事实判为差异；遗漏/`not_run`/缺参照为阻塞。`fail` 返回 1，`incomplete` 返回 2；`--proven-only` 的 `partial_match` 返回 0，但不能被写成完整兼容通过。 |
| rootfs | `capture.py` 捕获/提取拒绝覆盖已有目标；校验拒绝未解析的 loader/库、错误类型/模式/摘要、重复或越界成员。`qualified_hepta=false`、`readonly_mount_verified=false`；`ldd` 不发现所有运行时 `dlopen`、文件和服务依赖。 |
| guest | 资格要求实际输入绑定、完整 boot/case 标记、raw exit 33 和全部封装 C 案例的精确事实。重放脚本只对 `c_elf_pass` 返回 0，其余为 2；完整 32 项比较仍需三个 Python 和一个 Tokio 的 guest 运行条件。 |
| errno 与资源释放 | 例如 futex 的 `EAGAIN`、关闭 fd 的 `EBADF`、fd 上限的 `EMFILE`、SCM_RIGHTS 的 close-on-exec 和 SQLite WAL 重开事实必须按具体案例比较。宿主策略 `EPERM`、缺 QEMU/工具/库或未配置 provider 分别记为环境/接合问题，不能自动归为目标内核 ABI 缺陷。 |

每条 guest 差异交付 Linux 原事实、guest 原事实、case、errno、ELF/rootfs/kernel 摘要、完整 serial 和 raw exit。
并发案例比较线程回收、锁互斥、EOF、记录集合等允许的结果，不强制 PID 或调度顺序相同。
进程组回收只覆盖其声明范围；若后代逃离原进程组并保留输出管道，现有 host 工具会报告清理不完整，不能写成所有后代均已回收。

## 6. 与原版 Hepta 及主干整合

原版 Hepta 固定 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`，其 fleet 身份、认证 issuer、ObjectiveStart、invocation provider、run/receipt 和效果 owner 仍由原有主链提供。
A04 只调查所需 Linux 行为、ELF/文件/服务依赖和可观察结果，不签发凭据、不新造 provider/账本，也不因为状态缺失重试 Objective 或换请求 ID。
实际工具效果需要原 owner 的结果与独立效果观察；进程 ready、只读状态、模型请求发出或 Objective admission 不能单独代替它。

候选 `hepta-profile.json` 的构建、Wiremock 失败、ptrace 阻塞是对应历史 host 输入的记录。它不能覆盖主干 [R8 原版 Objective 接合实录](../../../results/integration/2026-10-18-objective-desktop/README.md) 已建立的隔离 issuer / 原版 admission 与持续 Session 范围。
新工作复用 [现有原版复跑入口](../../../tests/integration/hepta/ORIGINAL_OBJECTIVE.md) 和 A07 契约；生产 issuer、完整 provider/工具效果、K↔D、持久核对及确认退役各自保持未闭合范围。

最小集成顺序如下：

1. 在独立整合分支比较固定候选与当时实际 main，由 A00/A04 带入三个 A04 owner 目录及必要文档连接；逐项处理差异，不用旧候选树覆盖已更新的 A01/A05/A06/A07/A10。
2. 在合并后的确切源码上执行相关 Python 正常/`-O` 回归和 Linux 同 ELF 参照，保留源码、依赖、case 分母、跳过和失败；旧候选通过数不转记为新组合结果。
3. 取得原四 ELF/USTAR 后可复跑历史 pinned gate；若原字节不能恢复，则先建立独立的新 Linux profile、完整 ELF/库清单和正负例审查，再引入新的绑定。新 profile 的结果不得填补旧证据空位。
4. 与 A01 为当前主干源码建立新的 kernel/build/firmware/runner 输入绑定，保留旧 gate，再实际运行 A04 guest 差分。仅改 hash 常量或引用旧 boot marker 不能构成当前内核验收。
5. 对实际 guest 差异按原 owner 分派：A05 进程/fd/IPC/文件，A06 线程/调度，A01 loader/启动，A07 原版应用接合；共同内核路径由 A00 协调。通过后再调查完整 Hepta 工作负载和真实运行依赖，不向其他模块外推资格。

## 7. 已记录范围和下一项未通过门禁

固定候选的主 Linux 参照记录 31/32：28 个 C ELF 案例及三个 Python 案例通过，Tokio 为明确 `not_run`；28 个 C 案例的 staged-loader/chroot 结果属于原 Linux。
候选另有 [13 项实际 guest capability 探针](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/25c681d944e4efa92f2772cf773e03ae811bc345/tests/workloads/linux/baselines/guest-qemu-probe-20261017.json)，记录 11 个预期结果和 SCM_RIGHTS / RLIMIT_NOFILE 两项差异；它使用另一次探针归档，不是固定四 ELF 的完整 28 项重放。
这些历史差异须针对当前主干重新定位和复跑，不直接声明当前主干仍有同样缺陷。

下一条完整门禁仍需原固定 rootfs/ELF 输入或独立的新 profile、完整 guest 重放与可审核差分。Python/Tokio guest 运行时、真实 Hepta 工具效果及运行文件/服务闭包也未由 A04 候选补齐。
initramfs 内 SQLite 进程崩溃重开不等于 virtio-blk/Ext2 的 S1 断电与 flush/fsync 持久化；通用 SMP、Android、物理设备或移动 UI 均不继承本手册的局部结果。
