# G1-b 开发与验证：原 CPU owner 的纳秒用量

更新：2026-10-19。技术结构见 [A06 G1-b 手册](../../docs/ASTERINAS_CPU_USAGE_G1B.md)。
本文是当前实现的开发和验收契约，**不是最终组合候选的成功收据**。
最终生产 commit/tree、全套客体、七个负控、普通产品和完整 Linux 32 项运行仍须分别登记。
HOS2 设备仍仅开放 QueryAbi，用户态 ReadUsage 与另外三个效果/事件操作未开放。

## 1. 开发对象、来源与当前状态

这次切片修改的是原 `CpuMax`、原 ClockSource 到 scheduler 的时间端点，以及原 owner 锁内的
私有快照。没有在 fixture 或 `os-control` 中另建可替代内核用量的账本。
生产接口和锁边界以 [cpu.rs](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs)、
[native.rs](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native.rs)和
[原 scheduler](../../kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs)为准。

| 测试源码切片 | 精确身份与范围 |
| --- | --- |
| 最初 16 项 | `da9ef955050c74b6f00822143ab03aff497f7a5f`，基于 `775061af51e6ee91fce290d5855e24a276292e14`；只新增 `usage_tests.rs` |
| CFS 回退与共享 owner 到达顺序，增加 3 项 | `772e35de2f2d95960eb0dccdc650cf1d889286db`，保留前 16 项 |
| 真实 Process/Task lease 清理修复 | `6004306b627e32de2f3ae7fb5fc757418e655c65`，保留全部 19 个名称及业务断言 |
| 最终测试文件 | 35,603 字节，SHA-256 `9199dee49d804bb3b217a417362ed78043bcb6ae7a23f3bb29191d8f7c304dcb`；Git blob `5bcc62c554b1f8ec074a66ed9fbbed3840c394e3` |

以上是独立测试交付身份。整合生产改动、负控补丁和本文之后，应重新冻结最终候选，不能用这几个
测试提交充当产品来源。文档中的命令供维护者在已冻结且干净的候选上执行；本文编写阶段没有执行
这些产品构建或客体命令。

原 [CPU_CLOCK_HANDOFF_CI](CPU_CLOCK_HANDOFF_CI.md) 在当时记录 201 个 core 测试。
完整整合这 19 项而无其他测试变化时，core 分母预期为 220。这个算术预期不是实际成功计数：
仍须从本次完整串口枚举名称、结果和 summary，并独立检查 OSTD。原文档的历史计数不改写。

## 2. 固定环境与构建输入

使用 [.github/workflows/a06-kernel.yml](../../.github/workflows/a06-kernel.yml) 的正常 A06 流程。
原构建约束见 [support/build](../../support/build/README.md)和
[ktest 手册](../../support/build/ktest/README.md)。

| 输入 | 本轮规则 |
| --- | --- |
| 工具链 | `nightly-2026-07-21`，由原 `prepare-host.sh` 配置；不换 Rust 版本来绕过构建问题 |
| OSDK | 从固定 vendored OSDK 源码以 `--locked` 安装，沿原编译路径生成测试 ELF；原 OSDK lock 不改 |
| 原 root lock seed | 从固定上游 Git blob 读取，SHA-256 `6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316`；不把工作副本当新 seed |
| 派生 lock | root 235 包、core test 200 包、OSTD test 97 包、ordinary run 204 包的既有派生关系；只有已批准的本地 `os-control` 依赖，外部版本/source/checksum 不漂移 |
| vDSO | 原 `asterinas/linux_vdso` 固定提交 `8af571775a3d3a1df3e84fc9709b9d6b160c771a`，保留其实际文件身份 |
| 原 ktest 客体 | q35、TCG、CPU max、1 vCPU、512 MiB、固定 SeaBIOS、serial/debug-exit；记录实际 QEMU/firmware 字节、版本与参数 |
| 普通产品与 workload | 固定普通 ELF、原 initramfs；新增 workload 只允许经过各原 runner 验证的注入或完整 image，不以 test ELF 替代 |
| 主机 | 普通 A06 使用一次性的 Ubuntu 24.04 x86_64 runner；完整 profile 还需 gcc-13、Python 3.12、SQLite、OpenSSL 等原 workflow 依赖 |

QEMU 8.2.2 的既有 native profile 与上游完整开发容器的其他版本不能混为同一环境资格。
真正用于本轮的可执行文件、BIOS、编译器及版本以运行前固定收据为准。

从仓库根目录进行初始化，所有输出为 checkout 外的新目录；以下变量只用于本次运行：

```sh
set -euo pipefail
test -z "$(git status --porcelain=v1 --untracked-files=all)"
test ! -s README.md
g1b_head=$(git rev-parse HEAD)
g1b_tree=$(git rev-parse HEAD^{tree})
g1b_out=$(mktemp -d /tmp/g1b-qualification.XXXXXX)

bash support/build/prepare-host.sh
python3 -I support/build/verify-source.py
python3 -I support/build/ktest/prepare-locks.py --output-dir "$g1b_out/prepared-locks"
cmp "$g1b_out/prepared-locks/aster-core.Cargo.lock" support/build/ktest/locks/aster-core.Cargo.lock
cmp "$g1b_out/prepared-locks/ostd.Cargo.lock" support/build/ktest/locks/ostd.Cargo.lock
```

所有编译和 kernel/QEMU 阶段串行执行，沿原 `out-kernel.lock` 和原 OSDK 绑定路径工作。
不要在同一原编译目录同时跑正控、负控、普通构建或另一代理的构建。
generated `Cargo.lock` 必须逐字等于已选 lock，前后 source gate 必须通过。
若出现暂存 manifest、源树漂移、编译错误或 QEMU 异常，保留该次原件并新建下一次输出目录；
不能补写成功 marker、编辑既有收据或把有问题的文件加入忽略规则来通过 source gate。

## 3. 19 项 kernel 回归的具体覆盖

全部新增测试在
[native/usage_tests.rs](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native/usage_tests.rs)。
它们创建原 Process、Task、CgroupNode、SubController 和原 owner 锁，使用受控 counter 或显式
1 cycle = 1 ns 的 fixture。它们不是 live userspace ReadUsage，也不是物理 scheduler 切换或
完整 SMP 运行证据。`CpuRuntimeFixture` 调用生产 runtime 算法，不注入第二套 scheduler。

完整名称都以此路径开头：

```text
aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::usage_tests::
```

### 时钟精度和两个 runtime 游标：4 项

| 测试名 | 必须保留的观察 |
| --- | --- |
| `fragmented_three_ghz_runtime_keeps_absolute_endpoint_precision` | 3 GHz 下逐 cycle 刷新，以独立未刷新 ClockSource 的绝对纳秒端点为对照；分片累计保留相位，不能逐段丢小数 |
| `sampled_configuration_preserves_the_separate_cycle_cursor` | `configure_sample` 在同一个采样点先结算带宽，再观察；下一次 CFS cycle 更新仍包含自己的完整未计区间 |
| `reliable_clock_samples_cannot_rewind_the_runtime_endpoint` | 即使 ClockSource 基点使较早 read 仍标为可靠，runtime 自己的已计端点也不能回退；后续恢复不清 native fault |
| `unreliable_clock_sample_cannot_rewind_or_replay_cycle_runtime` | 已读到 cycles 150 后，硬件 counter 50 早于 retained base 100；失败 sample 不得 panic 或把 cycle 游标回拨到 100，恢复 160/175 只计 10/15，native 永久拒绝 |

最后一项明确区分 CFS cycles 和带宽 ns：cycle 高水位可以继续推进，遗失区间却不能由恢复后的
时间补造。故障源的 reliability 不重置；受控健康参考源只用于给出后续确定性输入。

### 窗口、累计与配置：6 项

| 测试名 | 必须保留的观察 |
| --- | --- |
| `crossed_windows_preserve_cumulative_usage_and_separate_debt` | 跨窗累计 1.5 ms、新窗真实执行 250 μs、旧窗欠额 250 μs；snapshot 不将 debt 混入 window consumption |
| `same_value_and_lowered_cap_never_refill_the_original_owner` | 同值或降低 cap 都保留原已用量，并按原 owner 修改推进共享 revision；不能通过重复写配置退还 quota |
| `returning_from_short_period_waits_for_a_complete_native_window` | 100→10→100 ms 后，在下一完整 100 ms 窗起点之前拒绝 snapshot；累计保留 |
| `returning_from_long_period_does_not_expose_pre_window_usage` | 1000→100 ms 的旧形状用量不作为成功 native 窗口暴露；到下一起点才接受完整窗，debt 和累计分别保留 |
| `ordinary_linux_caps_outside_n0_never_become_native_snapshots` | Linux 合法的非 N0 period/cap/unlimited 不自动得到 native 资格 |
| `late_same_value_reconfigure_preserves_window_usage_and_debt` | 底层收到晚到的 150 ms 配置、已有高水位 250 ms 时，不回拨 200 ms 窗口；保留 20 ms 用量、55 ms 累计和 5 ms debt |

底层晚到配置测试不通过 native 单 CPU 严格时间验收入口，与下文真实回退测试是不同层次的契约。

### 身份、关闭与观察入口：4 项

| 测试名 | 必须保留的观察 |
| --- | --- |
| `real_owner_wrapper_enforces_the_single_cpu_observation_profile` | wrapper 使用原时钟与原 owner；实际 CPU 数不是 1 时返回 UnsupportedProfile，不把局部结算当远端 rendezvous |
| `replacement_closes_the_old_snapshot_and_requires_a_new_binding` | controller 替换关闭旧实例；新实例不能继承旧 native 身份与 revision，需要独立绑定 |
| `deleted_owner_stays_closed_while_its_final_debit_is_retained` | 先结算并释放真实 Task lease，再通过原删除 gate；保留的旧 controller 可收原尾账但不能重新开放 snapshot |
| `indeterminate_metadata_cannot_produce_usage_after_detachment` | metadata 结果模糊的 fence 在 detach 之后仍保持，不能被普通 Closed 覆盖成可恢复状态 |

所有成功 `checked_sample` 一起检查身份、revision、sample time、100 ms period、
`event_sequence=0`、`dropped_events=0` 和 `user_paused=false`。0/0 只表示本片无事件生产者，
不是可靠事件流已完成的证明。

### 故障持久性与共享 owner：5 项

| 测试名 | 必须保留的观察 |
| --- | --- |
| `unavailable_clock_allows_only_unlimited_linux_recovery` | 缺失可靠时间后，有限配置拒绝；Linux `max` 可解除本地限额但不清 fault，native 始终拒绝 |
| `backwards_usage_observation_permanently_fences_the_owner` | 早于已采样端点的 usage read 锁定故障，之后较新时间不能恢复 |
| `backwards_same_value_configuration_cannot_reopen_an_old_window` | 单 CPU：已有 250 ms 高水位、200 ms 窗和 20 ms 用量，同值写入 Some(150 ms) 返回 ResourceUnavailable；max 恢复不回拨窗口。多 CPU 分支保留合法晚到配置，不伪造单 CPU 结论 |
| `cumulative_overflow_never_wraps_or_recovers_a_native_snapshot` | 累计溢出保持饱和与故障，不能回绕成低用量；改配置和恢复时间不清 fence |
| `overlapping_owner_intervals_accumulate_without_a_clock_fault` | 两个未启动的真实 task 向同一 owner 交付重叠/晚到区间，40+25+5+5 ms 全部累计为 75 ms，高水位 145 ms，不因全局到达顺序误报故障 |

最后一项只覆盖同一窗口内确定性的共享记账顺序。不接受用它声明并发执行、远端运行结算、
跨窗晚到尾账、IPI、CPU 热插拔或严格每窗 SMP 限额已经通过。

## 4. 真实 lease 清理与已发生的开发失败

夹具退出顺序属于测试正确性，原删除 gate 必须保留。所有 runtime 先释放；随后
`test_util::mark_zombie(process)`、`move_process_to_root`、释放 Process/TaskSet、释放最后的 Task；
最后才执行 `mark_as_dead().unwrap()` 和移除子节点。第二个 Process 的 RAII 同样遵循此顺序。
原 [native 生命周期测试](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/native/tests.rs)
和 [membership](../../kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs) 提供真实路径。

对 live task 写入 `cpu_cgroup=None` 会通过原
[RcuOption](../../kernel/asterinas/ostd/src/sync/rcu/mod.rs) 将旧 CpuCgroupLease 加入 `delay_drop`。
随后只 drop task 不能保证这个已退役 lease 立即回收。zombie 迁移保留当前 lease，最后的
Task 析构才同步释放当前 RCU slot；不得手工触发 grace、重置 lease 数或删除 EBUSY 检查。

本轮已保留以下真实开发失败，不能隐藏在最终成功之后：

| 尝试 | 当时实际范围与结果 |
| --- | --- |
| `wip-core-02` | 旧 16 项版本，core 目标 217；部分 usage 项 FAILED，随后客体在删除用例附近提前结束，无完整失败 summary，不算通过 |
| `diagnostic-unavailable-02` | 仅定位 `unavailable_clock_allows_only_unlimited_linux_recovery`；0 passed / 1 failed / 216 filtered，raw QEMU 65；在 `mark_as_dead().unwrap()` 得到 EBUSY，消息为 `the cgroup has deferred CPU accounting leases` |
| `6004306` 修复 | 只修夹具真实对象释放顺序，19 名与业务断言保留；pinned rustfmt 和 diff 检查通过，不能据此填入 runtime pass |
| `wip-core-03` | 修复并整合 19 项后的本地完整 core：220 passed / 0 failed / 0 filtered / 0 soft skip，raw QEMU 33、无超时，原 `run.py` 汇总 passed；仅此 WIP core 范围 |

原始材料由本轮 `r11-evidence/g1b-build` 保存；这是工作阶段证据位置，尚不是已发布结果目录的链接。
诊断用例之前的时钟/快照断言已执行，但过滤运行不能替代完整 core，更不能替代 OSTD 或普通产品。
`wip-core-03` 原串口 27,372 字节，SHA-256
`ab7ae20b3dafef9250d74e829fed703698f673061d47950eaa8e96fb12ef705e`。
这次本地运行有 WIP 文件快照，尚不是干净发布提交的 exact-head CI；最终候选必须用新目录运行
整套 core/OSTD 和后续各门禁。失败与成功各自关联源码、构建命令、实际 ELF 和串口。

## 5. 完整 core / OSTD 正控

```sh
A01_KTEST_TIMEOUT=300 python3 -I support/build/ktest/run.py \
  --output "$g1b_out/ktest"
```

正常资格不传 `--crate` 或 `--test-name`；必须有 core 与 OSTD 两个完整、非空的独立客体。
原 checker 要求实际 raw QEMU 33、无超时、原 serial SHA 匹配、目标 crate summary 一致、
零失败、完整运行零 filtered，并有最终 `All crates tested`。预期 panic 用例仍由原 ktest 判定。

逐项记录 OSTD 打印的 soft skip。TCG 下返回成功但明确跳过的 VMX/EPT 用例不能算成执行通过。
报告同时给出原 reported passes、soft skip 数与实际执行的通过下界，不能合并不同 commit 或
不同阶段的计数。完成源码改动后的完整 core 分母应反映全部 19 新项，不能停留在最初 217。

## 6. 七个固定生产负控

控制目录以 [run_cpu_owner_negative.py](run_cpu_owner_negative.py) 中固定补丁 SHA、生产路径
和完整失败名集合为准。测试源、原完整 checker 和断言不变；每轮只有一个被审查的生产变异。

| 控制 | 精确预期失败集合的数量 | 本轮变化 |
| --- | --- | --- |
| `owner-current-slot` | 3 | 保留原 retained-owner 失败名 |
| `clocksource-drop-fraction` | 4 | 保留原 3 个 phase 失败，新增下面 1 个 usage 精度失败 |
| `vdso-drop-fraction` | 3 | 原集合保留 |
| `vdso-skip-fault-mode` | 1 | 原集合保留 |
| `handoff-drop-tail` | 4 | 原四个 handoff 失败保留 |
| `handoff-eligibility-first` | 1 | 原共享祖先窗口/debt 失败保留 |
| `dequeue-drop-owner` | 2 | 原 wait/exit retention 失败保留 |

唯一新增的预期失败全名为：

```text
aster_core::fs::fs_impls::cgroupfs::controller::cpu::native::usage_tests::fragmented_three_ghz_runtime_keeps_absolute_endpoint_precision
```

这些是固定验收预期，实际运行必须逐项证明。夹具 EBUSY、编译错误、非预期 panic、缺 summary、
timeout 或额外失败不能加入“预期失败”来让控制通过。

```sh
python3 -I -B tests/organ_backend/test_cpu_owner_negative.py
python3 -I -B tests/organ_backend/run_cpu_owner_negative.py \
  --green-evidence "$g1b_out/ktest" \
  --worktree "$g1b_out/owner-negative-source" \
  --output "$g1b_out/owner-negative"

for g1b_control in clocksource-drop-fraction vdso-drop-fraction vdso-skip-fault-mode \
    handoff-drop-tail handoff-eligibility-first dequeue-drop-owner; do
  python3 -I -B tests/organ_backend/run_cpu_owner_negative.py \
    --control "$g1b_control" \
    --green-evidence "$g1b_out/ktest" \
    --green-kernel "$g1b_out/owner-negative/green-core-kernel.elf" \
    --worktree "$g1b_out/source-$g1b_control" \
    --output "$g1b_out/negative-$g1b_control"
done
```

第一轮在重建之前，必须核对并保留原成功 QEMU 实际加载的 green ELF。后六轮只能引用这份副本，
不能将共享 target 中已被负控替换的 ELF 重新称为 green。每轮执行完整 core，名字集合和分母
必须等于原正控；固定目录中的历史最低分母不是允许删掉新测试的豁免。
原 QEMU 必须为真实失败 65，原 OSDK 与 checker 均失败，实际 FAILED 名集合恰好等于对应固定集合。
还应保留变异 commit、patch、前后源身份、两份 ELF、原锁、命令、QEMU record 和完整串口。
runner 恢复原候选后再运行普通产品，不 `--force` 丢弃未知改动。

## 7. 普通产品、配置与实际配额

所有普通产品阶段在完整正控和七个负控之后运行。先构建一个普通产品 ELF，并独立验证 boot 和
QueryAbi guest：

```sh
python3 -I tests/kernel/control/run_queryabi_candidate_guest.py \
  --expected-source-head "$g1b_head" --expected-source-tree "$g1b_tree" \
  --target-dir "$g1b_out/product-target" --output "$g1b_out/product"
g1b_kernel_sha=$(python3 -I -B -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["kernel_elf_sha256"])' \
  "$g1b_out/product/result.json")
```

取证链以 [QueryAbi candidate runner](../kernel/control/run_queryabi_candidate_guest.py) 的原判据为准：
普通源码前后校验、生成锁逐字一致、实际 ELF、两个 guest、14 个严格逐行标记，以及四个非 QueryAbi
操作拒绝。raw exit 33 不能独立证明 probe 通过，更不能说明 ReadUsage 已实现。

复用这个实际产品 ELF，运行 [CPU_CONFIG_SETTLEMENT](CPU_CONFIG_SETTLEMENT.md) 的四组合：

```sh
python3 -B tests/organ_backend/test_cpu_config_settlement.py
python3 -B -O tests/organ_backend/test_cpu_config_settlement.py
for g1b_period in 100000 2000; do
  for g1b_mode in read-only same-value; do
    python3 -B tests/organ_backend/run_cpu_config_settlement.py \
      --kernel "$g1b_out/product/product-kernel.elf" --expected-sha256 "$g1b_kernel_sha" \
      --initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
      --bios /usr/share/seabios/bios-256k.bin --qemu /usr/bin/qemu-system-x86_64 \
      --out "$g1b_out/config-$g1b_period-$g1b_mode" \
      --period-us "$g1b_period" --mode "$g1b_mode"
  done
done
```

quota 固定 1000 μs，测量 4 秒，100 ms 周期上限 1.2%，2 ms 周期上限 52%，unlimited 样本至少
70%。原参数、marker 顺序、进程 exit、raw QEMU 33、全部输入不变检查仍保留。
这里的 `getrusage` 是独立低分辨率交叉检查；不能据此声称 native 纳秒误差界已经测得。

原 A06 还需要独立 SMP=2 配置 ELF：

```sh
A01_SMP=2 A01_RUN_DIR="$g1b_out/smp2-build" CARGO_TARGET_DIR="$g1b_out/smp2-target" \
  bash support/build/kernel.sh kernel
g1b_smp_kernel="$g1b_out/smp2-target/osdk/asterinas/asterinas-osdk-bin.elf"
sha256sum "$g1b_smp_kernel" > "$g1b_out/smp2-kernel.sha256"
read -r g1b_smp_sha g1b_smp_name < "$g1b_out/smp2-kernel.sha256"
python3 tests/organ_backend/run_candidate_matrix.py \
  --a01-tree "$PWD" --kernel "$g1b_smp_kernel" --expected-sha256 "$g1b_smp_sha" \
  --out "$g1b_out/probe-1vcpu" --quota-us 1000 --mode leaf \
  --repeat 2 --duration-seconds 1 --max-cpu-percent 3
python3 tests/organ_backend/smp2/run_parallel_candidate.py \
  --a01-tree "$PWD" --kernel "$g1b_smp_kernel" --expected-sha256 "$g1b_smp_sha" \
  --out "$g1b_out/probe-2vcpu" --quota-us 1000 --mode leaf \
  --repeat 2 --duration-seconds 1 --max-cpu-percent 3
```

使用 OSDK 输出、QEMU 可加载的 ELF64/EM_386 文件，不使用原 Cargo 符号 ELF。
这两组各重复 2 次的低配额/退出生命周期观测，与普通一 CPU 产品是同源码、不同构建配置；
各自固定 SHA，不能混用。3% 判据也不等于严格 1% SLA、完整 SMP 限额或手机设备资格。

## 8. 保留 A04 的同 ELF 与完整 Linux 32 门禁

不能因本切片主要修改 CPU 记账而删去原 syscall/workload 回归。
[A06 workflow](../../.github/workflows/a06-kernel.yml) 还应执行：

| 门禁 | 输入和完整结果 |
| --- | --- |
| SCM_RIGHTS / CLOEXEC | 编译一次并在 Linux 之前固定 probe ELF SHA；要求 Linux 27 项与同一普通 kernel 内的同 ELF 27 项全部通过；原 [runner](../workloads/linux/run_scm_rights_cloexec_guest.py) 和 normal/`-O` verifier 测试保留 |
| RLIMIT_NOFILE | 编译一次 static pthread probe，原 Linux reference 37 项；guest 复用经过 reference 验证的同一副本/原 SHA 和相同普通 kernel；原 [runner](../workloads/linux/run_rlimit_nofile_guest.py) 的正常/`-O` 测试保留 |
| Ubuntu full32 | 原 28 C + 3 Python + 1 个真实 locked Tokio 工作负载，全部具体事实、JSON 类型、次序、stdout/stderr 和进程 exit 原样验证 |

完整 profile 规范见 [FULL_UBUNTU_PROFILE](../workloads/linux/FULL_UBUNTU_PROFILE.md)和
[固定 contract](../../compat/linux/profiles/ubuntu24.04-x86_64-20261019.json)。
它不是“28 项加 Rust/Python skip”，也不接受单个 generic success 替换原具体结果。

```sh
/usr/bin/python3.12 -I -B tests/workloads/linux/test_full_ubuntu_profile.py
/usr/bin/python3.12 -I -B -O tests/workloads/linux/test_full_ubuntu_profile.py
cargo +nightly-2026-07-21 fetch --locked \
  --manifest-path tests/workloads/linux/rust/Cargo.toml
/usr/bin/python3.12 -I -B tests/workloads/linux/run_full_ubuntu_profile.py build \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --qemu /usr/bin/qemu-system-x86_64 \
  --expected-source-head "$g1b_head" --expected-source-tree "$g1b_tree" \
  --output "$g1b_out/full-bundle"

# 必须在任何 workload 执行之前，从 build 的原 digest 文件冻结该值。
read -r g1b_input_sha g1b_input_name < "$g1b_out/full-bundle/inputs.sha256"
test "$g1b_input_name" = inputs.json
sudo /usr/bin/python3.12 -I -B tests/workloads/linux/run_full_ubuntu_profile.py reference \
  --bundle "$g1b_out/full-bundle" --expected-input-sha256 "$g1b_input_sha" \
  --output "$g1b_out/full-linux"
/usr/bin/python3.12 -I -B tests/workloads/linux/run_full_ubuntu_profile.py guest \
  --bundle "$g1b_out/full-bundle" --expected-input-sha256 "$g1b_input_sha" \
  --linux-reference "$g1b_out/full-linux" --product-evidence "$g1b_out/product" \
  --expected-source-head "$g1b_head" --expected-source-tree "$g1b_tree" \
  --bios /usr/share/seabios/bios-256k.bin --qemu /usr/bin/qemu-system-x86_64 \
  --output "$g1b_out/full-guest"
```

Linux reference 只在一次性、无外部挂载的 chroot 中为 setup 使用 root，实际 workload 采用
UID/GID 65534 和原维护的进程组清理。guest 不重新编译或打包；两侧消费同一个在 Linux 执行前
固定的完整 image、5 个实际 ELF 和 runtime 文件集。原 inputs digest 不能在 reference 后
重新计算并作为新接受值。原 runner 的退出、字节 framing、类型、超时和输入不变检查全部保留。

## 9. 证据交接、状态更新与下一阶段

最后记录完整候选 commit/tree、测试/普通/SMP2 各 ELF 的实际 size/SHA、所有 source 快照、
命令和真实 exit、原串口、完整/失败/过滤/soft skip 分母、固定负控名集合、生成 lock 的实际副本、
QEMU/BIOS/编译器输入，以及 Linux/guest 的原 stdout/stderr 与冻结输入。
旧失败、诊断运行与成功重跑并列保留；不要只交最终汇总 JSON 或 CI 绿勾。

共享 target 经后续构建会替换，必须在替换前保留两套正控 ktest ELF，以及每个独立负控 ELF。
归档可去除可重新生成的 Cargo cache，但不能去掉 actual ELF、原 image、lock、编译日志或失败证据。
CI artifact 应保留原下载身份与成员清单；发布后的新 main tree 不能自动继承旧候选运行资格。

| 后续填写项 | 本手册创建时 |
| --- | --- |
| 最终组合生产 source 与已验证 test 文件 | 待最终固定身份 |
| core 220 集合、完整 OSTD、原 ELF 和 soft skips | 本地 WIP core 220 已通过；最终候选完整 core + OSTD 待验，旧 217/定向失败保留 |
| 七个完整原 core 负控与恢复 | 待实际执行结果 |
| 普通 boot / QueryAbi14 / SCM27 / RLIMIT37 / 配置四组合 | 待同一个实际 ordinary ELF 的收据 |
| 独立 SMP=2 配置的 1/2 vCPU 各两次 probe | 待对应 ELF 的实际收据 |
| full32 原 Linux 与相同 frozen image 的 guest | 待完整双方收据 |
| 正常 PR CI、远端精确 tree、合并或未合并 | 待发布与正常门禁，不能用本地状态代替 |

G1-c 继续处理最终 Process/exec 上的可信身份与授权；G1-d 再闭合五操作、CAS、重放、事件/交付退役
和撤销。G1-b 的私有 snapshot 只提供原 owner 同锁的表达与拒绝边界，不能替代这些步骤。
真实 Hepta K↔D、外部 provider、物理切换、完整 SMP、手机和其他设备均需独立资格。
