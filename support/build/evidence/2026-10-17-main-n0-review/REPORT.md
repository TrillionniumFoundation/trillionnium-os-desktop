# A01 当前轮构建与启动报告 v3

本轮已在项目专属云环境完成固定源码、私有依赖恢复、真正 Rust 内核冷构建及 QEMU 启动，并用该新内核通过未改动的 A05 QueryAbi 客体断言三次；随后 TCP GDB 命中真实 Rust 入口、核对运行字节、detach 并继续启动通过。OSDK 工具及示例矩阵22项报告通过。完整内核 ktest 为 OSTD 通过、aster-core 151通过/2失败；独审将两项失败定位为奇数 period 的 test oracle 舍入错误，差值为1个 TSC clock tick。owner 补丁尚未应用，也未重跑，因此该 native suite 仍失败，全项目 blocker 未全部闭合。

v2纠正最初稿将差值写为“1ns”的单位错误；v3进一步区分QueryAbi成功phase与随后失败的enclosing tool，并区分CLI请求duration1s与实际测得wall interval。v1/v2及其校验清单保留，原始失败不改写。

## 固定源码及所有权

| 项 | 精确标识 |
| --- | --- |
| 仓库、分支、PR | TrillionniumFoundation/trillionnium-os-desktop；[agents/A01-asterinas-boot](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/agents/A01-asterinas-boot)；[PR #22 → main](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22) |
| 本轮 native producer | `fd0a5ed637312b13efdbfb6b670d4af52bd2c2b0` |
| producer tree | `676fcaf53cc094bdd5d1ede25b8f13c8221b5e6d` |
| 有序父提交 | `42c0fbda192e61fbfad638e16aa74b67cf989bba`；`dfe0ed04b4789d37d41854191126e710782baa3a` |
| 本轮同步的 main | `dfe0ed04b4789d37d41854191126e710782baa3a` |
| 完整 kernel/core 子树 | producer 与上述 main 均为 `d76da7294b51cfa591e7af1ccd99616b29637ca7` |
| 固定上游 | Asterinas v0.19.0，commit `c4b7ed575b7b32773475b194d2ad41fb6d03765b`，tree `96605cf64aeae2d34f29b97e85eff9315fe10a8e` |
| Rust | `nightly-2026-07-21`；rustc `87e5904f5eb6398af6b22eac2802c78934260c48`，Cargo `3efb1f477e99b42974b982d939fd100303cdf7db` |
| 内核根目录 | `kernel/asterinas/`，保留完整派生内核、上游文档、许可证及署名 |
| 发布及 CI | 执行源码fd0已非强制推送；后续证据/metadata提交SHA及新head CI只在PR最终回读记录，避免证据提交自引用；旧42c成功不替代新head验收 |

源码 CAS 桥保存原始 commit/tree/blob，并验证完整 core 与 main 的 Merkle 子树相同。A01 未改写 A05/A06 接管的核心实现。118 个受保护构建输入逐项核对；完整内核根 Cargo.lock SHA256 仍为 `6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316`。派生的 host OSDK manifest/lock 明确记为批准差异；不能把其 lock 称为原始上游 lock。最终证据提交应继续引用实际执行的 producer，不能用稍后的文档提交替换源码 SHA。

## 环境与真实 native 结果

已向任务私有前缀恢复 57 个固定依赖包，未安装到系统路径、未执行包维护脚本。恢复固定 Rust/Cargo 及所需组件、cargo-binutils、vDSO；实际可用 QEMU 8.2.2、GDB、Clang/LLD、BusyBox、cpio 和 SeaBIOS。Docker/Nix 未提供，已用可用的原生开发者路线完成构建。最小启动没有下载完整 NixOS 安装 ISO。

宿主观测为 hostname `24f0ea2620fe`、boot ID `952006db-88a3-4a56-8049-0adbbe2acfb2`、Linux 6.18.55。没有 `/dev/kvm`，VMX/SVM 未暴露；AF_UNIX socket 创建 EPERM，IPv4 loopback 可用。这些观测不等于不可变环境或云提供商证明。

| 本轮阶段 | 已完成的真实证据 | 范围 |
| --- | --- | --- |
| ordinary 冷构建 | target 预先不存在；`kernel.sh kernel` 返回 0 | 完整固定 Asterinas 派生 Rust 内核 |
| ordinary 启动 | `kernel.sh run_kernel` 返回 0；QEMU raw33；未超时；live-artifacts 检查 0 | x86_64、1 vCPU、512 MiB、q35/TCG/max、SeaBIOS、串口、小型 initramfs，无磁盘/网络 |
| 内核产物绑定 | 首次构建 ELF 与实际启动 ELF 完整字节相同，8266592 字节 | SHA256 `ed469d2ff7636b7d60c52a011b1d9685d8b3096bd79f7c94ef813bdb023e6dc9` |
| QueryAbi retry | owner C probe编译0；phase child0/controller passed=true；三个真实guest raw33、未超时、phase源码状态干净 | enclosing tool session44537最终为1，原因是随后的CPU probe失败；QueryAbi-only |
| debug | command0、GDB0/detach、QEMU raw33、未超时、source-clean，5个 owned leaders 均 reap | 新 fd0 producer 的完整符号 ELF、实际启动 ELF 与32个运行入口字节匹配 |
| 内核 ktest | OSTD221报告通过/3软跳过/218实际通过下界/raw33；core151通过/2失败/raw65；child1、外层1 | 未超时，但整轮失败；异常退出后的源码postguard未执行，不宣称source-clean或374项全通过 |
| OSDK integration | child0/外层0、22报告通过、0失败/blocked、1个VMX软跳过；postGit干净 | 工具/示例矩阵；9个case产生11次实际示例guest raw33，其余13个case没有guest；与完整Asterinas内核验收分开 |
| 固定QEMU owner probe v2 | 两个owner command0并reap、外层0；1CPU两guest raw33、1.001%/1.1%；2CPU两guest raw33、0.822%/0.9%；pre/post guards及postGit干净 | 配置1% quota、CLI请求duration1s、显式3%有限比例界；未建立实际固定1秒窗口，非严格1%或完整矩阵验收 |

ordinary initramfs 为 1107990 字节，SHA256 `86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3`；实际冻结 SeaBIOS 为 262144 字节，SHA256 `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735`。QEMU 二进制 SHA256 为 `8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854`。ordinary 完整串口为 72239 字节，SHA256 `72892ac2510c257a0c23c057222e763633a81bb231811c24102b69c39f32a2dd`。完整实际 argv 与串口必须随证据打包保留。

QueryAbi retry 的三个串口 SHA256 分别为 `2e4f85985200e4098ee0d181c44296af84874e001ee48c4238e0957b01aa8cee`、`d738432de19079cc7368d91444f080f34f370ff3f60893e39e4e7b6697a43eca`、`7b18f110287b7a6cf829f2eb93f825c7ffca2bf3cdf252366bd528ba16638324`。该设备的 advertised mask 只有 QueryAbi；没有因此取得 trusted CapSpace、权限投递、完整 effect operations 或 G1/G2 的验收。

debug 命中 `__ostd_main` 的 PC 为 `0xffffffff8841ed80`。完整符号 ELF 为111763360字节、SHA256 `e14bcc8b93ab47c29e9676c5c6f98e717d528780cf3b9cc339b9124ad8f48762`；实际启动 ELF 为5947048字节、SHA256 `929c7b652e8bee198e8eca40bc13fd4426e0adff35fa93a69868bca6888b7b73`。两者及 GDB 实际读取的32字节相同：`50e8aad2eaff48c7c758f45388e87e4a060048c7c000a05e8848c7c178a65e88`。完整符号已由 controller 单独保存并核对其 SHA；debug 串口 SHA256 为 `17c5e839fd4ad0a9b24b8f777e67ed2721cc294f146e0ae284d3de8c2d90694c`。这是独立 debug 构建产物，不应与 ordinary ed469 ELF 描述为同一产物。

ktest 中 OSTD 的3次软跳过原因为 VMX unavailable 两次、VMX/EPT invalidation unavailable 一次。core 的两个真实失败均位于 `kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs`：`idle_skipped_periods_never_subsidize_late_burst` 原期望126985880、实测126985881；`long_continuous_interval_has_constant_time_bounded_debt_accounting` 原期望1153239116、实测1153239117。差值均为1个 TSC clock tick。OSTD/core完整串口 SHA256 分别为 `2dc234da655a703c688b1ea010bbc0bc9ab3914b5f58dbd93696b5e8fb7c784b`、`3b6c8b34ae3282d38b870697f73b00cf5f5fb269e86c35e76457d09d78db8bcd`。聚合 result 的 crates 为空是异常提前返回，不能抹去独立 OSTD 结果，也不能当作整个 suite 已通过。

令 period 为 P、quota 为 Q。测试从 `start + floor(P/2)` 开始，直到该 period 末尾的工作量实际为 `P - floor(P/2) = ceil(P/2)`。production 用真实 `end - from` 端点计算正确保留该 tick，两个 oracle 却减去了 `floor(P/2)`，在 P 为奇数时恰少1。应由 A00/A06 审核的测试期望是 `period - period/2 - quota`，long case 再加 `4*(period-quota)`，不是改 production 或增加±1容差。

`us_to_clocks = floor(F*us/1000000)`，P 的奇偶会随真实校准 F 变化。两组失败整数与源码公式可推得 P=259154857、Q=2591548，正确期望精确等于两次实测；这属于数学推断，不是 core VM 实测 TSC 频率。不可代入另一次 OSTD boot 的频率。纯 Python 整数复核在 `-I` 和 `-I -O` 各完成52701个 case，两份结果相同；它验证有限整数样本及奇偶公式，没有运行 Rust/VM，也未穷尽所有u64溢出边界。`owner-tests-only-proposal.patch` 仅修两个测试期望及注释，尚未应用；owner 必须用真实 core kernel suite 重跑后才能关闭本项。issue63 的最终记账 owner 风险独立保留。

OSDK 的 profile 为 `osdk-native-local-tcp-gdb-capture-v2`，使用 loopback TCP、q35/TCG/max、1vCPU/512MiB。22个工具/示例 case 全部返回0；11条guest记录均 raw33、未超时。hypervisor 示例报告“VMX unavailable; hypervisor example accepted upstream fallback”这一软跳过，不能把它计为硬件 VMX 验证。该矩阵包括 CLI、项目生成、示例内核等；完整 Asterinas 的真正构建、QueryAbi、debug 和 kernel ktest 由上面的独立证据承担。

最后一次 `probes-pinned` 修复了临时adapter依赖执行位的入口问题：四次均用显式Python adapter exec固定SHA的真实QEMU，并显式带私有 `-L` 数据目录。原owner源码、C probe、helper及adapter的entry/prelaunch/postlaunch/final guards均保持；没有改宿主cgroup。1CPU/2CPU各两次真实guest已完成且无panic，CPU诊断百分比如表。四条真实串口均包含 `ORGAN_CPU_VERDICT=INCONCLUSIVE_REQUIRES_TIMING_VALIDATION`，结果仍标记 `smp_qualified=false`、`hepta_hos2_qualified=false`。CLI请求 `--duration-seconds 1`，但restricted实测wall interval单CPU分别为1099269967/1000225763ns、双CPU分别为2797054263/1999040082ns。通过的是原owner在这些实测区间上的显式3%有限比例界，未建立固定1秒窗口。1.1%本身不能证明严格1%上限，这些诊断不能关闭每100ms严格矩阵、RT、退出尾账或issue63。launcher的正常SystemExit0不是失败异常；各launch没有timeout。此前缺-ROM/timeout sentinel失败仍原样保留，不能被本次通过抹去。

## 修复、失败与重试保留

本轮源码修复覆盖 monitor readiness/协议回应、chardev ID 冲突、OSDK unsafe 边界、integration 失败清理、recorder 参数校验顺序，以及 debug/repro 锁与取消生命周期。各自的 host 模型、原反例、独审与精确源码由相应冻结证据包支持；host 通过与 native 通过分别记账。

debug/repro 先获取共享 workspace flock，再创建 output；busy 不消耗 output 或其父目录。同一已锁文件描述符经私有 `A01_KERNEL_LOCK_FD` 协议交给 worker，public supervisor 同时转交 GDB listener，standalone 路线保留。repro 复用 debug 的锚定进程组 owner，取消后先清理组、再 reap、写回执。独审追加发现原 250 ms/private 与 100 ms/public 会打断慢 EXIT cleanup；最终均为 2 s 有界 grace，WNOWAIT 轮询 leader 完成后提前停止等待，再清残余组并 reap。0.6 s helper 的真实 shell fixture、原始 37、取消 143 均通过；3 s 超预算会留 manifest，下一 runner 拒绝覆盖，不能描述为无限清理保证。

所有以下失败保留原命令、外层状态、环境与日志：

| 事件 | 真实状态与处理 |
| --- | --- |
| 首次产物捕获路径错误 | Rust kernel command 已返回 0；controller 错找 `target/x86_64-unknown-none/release/asterinas` 后返回 1，尚未尝试 QEMU。修正为读取 OSDK bundle.toml 的 `target/osdk/asterinas/asterinas-osdk-bin.elf`，在新隔离 worktree 重新冷构建和启动。 |
| 原 workspace manifest 重现 | cleanup 曾报告 owned_removed/0，随后该路径出现同内容文件；保留 inode/stat/字节并移至证据。writer 未识别。后续使用精确 producer 的隔离 worktree；这不是永久 containment 的证明。 |
| QueryAbi 首次外层失败与retry | 首次三个guest实际已raw33，但 `python -I` 仍生成未跟踪 `__pycache__`，source-clean postcheck失败、外层1。保留cache后改用显式 `-B -I`，retry的QueryAbi phase child0/controller passed=true、三个guest raw33且source-clean；包含它的combined tool session44537因随后CPU probe失败最终为1，不能写成retry外层0。 |
| CPU probe 首次缺 QEMU 数据目录 | 私有 QEMU 无 `-L`，缺 kvmvapic.bin/multiboot_dma.bin，串口进入 SeaBIOS No bootable device；项目内核与 quota probe 未运行。owner 捕获 TimeoutExpired 后填写 sentinel124；不是已观测 QEMU raw124。 |
| CPU probe retry 不完整 | 第一轮是真 raw33、guest_complete、无 panic，单样本报告 1.0%。第二轮缺 ROM、未完成；owner 填 sentinel124，真实 QEMU raw exit 未保留；owner command2、外层1。当前 adapter 为0644、ctime 位于首轮期间，结合 PATH/缺-ROM日志指向后续绕过 adapter 的 fallback；第二次实际 argv 未留，writer 不归因。严格矩阵未通过。 |
| 当前 core ktest 两项失败 | OSTD独立通过；core151通过、2失败，QEMU raw65，OSDK1、ktest child1、外层1。原始失败保留；末尾source postguard因异常未执行。独审诊断奇数P的测试oracle少1tick；proposal未应用、未重跑，owner blocker仍开放。 |

本轮早期单样本及最终四次有限诊断均不能关闭issue63、严格每100ms上限、退出尾账或SMP公平性项。独审定位dead Weak分支跳过尾账、退出前迁root的源码风险；尚未证明实际undercharge或配额绕过。既有panic修复和有限SMP客体证据已进入main，应保留其有效范围，不能重新描述为“CPU从未进入main”。

## 仍开放与交接

完整状态见 `blockers.json`；可修改接口与复现步骤见 `HANDOFF.md`。A01 构建/启动、有限 QueryAbi 验证与其他 owner 的 trusted CapSpace、effect operations、CPU 严格矩阵、final debit、持久 G1/G2 分开验收。`/dev/kvm`/AF_UNIX、不可变云环境、未知写入者亦未关闭。A06 workflow 的 `-I` sibling import 和错误 ELF 路径属于 owner 修复项。本轮未修改它们的源码或 workflow。

已向A00/A06给出具体原始失败、oracle推导、未应用的tests-only proposal及剩余验收：[PR22交接评论](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6230648819)。A01代码修复和有限native验证已与owner仍开放项分别记账，`all_project_blockers_closed=false`。

root完成native后，metadata只追加 `cloud_main_n0_validation_2026_10_17` 这一新key。初版metadata SHA477acdc5…时，root记录删除该key后旧JSON全等、根README0字节和118项固定源码核对通过，原记录在 `round-current/post-metadata-review.json` 与 `post-metadata-source-check.json`。随后仅在新key内将duration明确为requested并加入actual restricted wall数组，最终metadata SHA256为 `e87d098480984d482c8638904bda5d98bdd600e9939e2401e8a248f658af3208`，`actual_fixed_one_second_window_established=false`；变更由 `round-current/metadata-duration-clarification.json` 保留old→new。原118项检查指向初版477，不声称对最终e87另跑一次118检查；固定源码输入及新key外旧JSON保持不变。metadata增量不改变实际运行producer fd0，不把最后文档提交写成执行源码。

历史跨实例字节相等证明仍只适用于其原 R/A4/C4 producer、固定路径/工具链与有限两个实例；本轮 ed469 内核包含 main 的 owner 集成，不把旧哈希或旧测试数字搬作当前通过。冻结 GitHub 回读观测于2026-10-17T06:16:58.803Z：旧42c的 host-evidence、Analyze(python)、CodeQL 三个checks均completed/success。实际 host job 使用 synthetic commit `c6024b2f60ceec774688e73d241d80bce5afc486`，父提交为 `e59f8b2fce1287f1ea706dc94880824a9b586ae3` 与42c，执行190次host测试；未运行项目内核或QEMU。CodeQL直接checkout42c。该成功不能挪作 fd0 或最终证据head的CI通过。legacy combined-status 另返回 pending/0/[]，不代表存在待完成的legacy context，也不抹去三个明确成功checks。本轮最终 CI、PR 状态与证据提交仍需新 exact-head 回读。

同一 GitHub 回读的 main 为 `0d4f51a51666972279db3425b6b21d4febbeead8`，相对选定 dfe 为ahead23/behind0、23提交/153路径，只涉及workflow/docs/os-abi/os-control/tests，没有 `kernel/asterinas/`、`support/build/` 或 `support/upstream-lock.json`；这是路径比较，未合入或执行更新main。PR22当时open/non-draft/unmerged、branch/head为42c，API base SHA为47288，mergeable null/state unknown；这些原值保留。A05 PR87 merged=true/draft=false，A06 PR18 merged=true且API仍报draft=true；issue63开放。A07 PR108 draft/open/unmerged、issue111开放，A04 PR8 draft/open。回读包25个文件的清单SHA256为 `1ae11000af1470f304b7a1b3edd359baabc7b7b9a3fd8fe81436c1e1d431cafa`，完整raw receipt在 `current-final-ci-readback/`。后续最终发布状态另行追加，不改写本快照。
