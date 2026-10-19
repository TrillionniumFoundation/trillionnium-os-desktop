# G1-c 开发与验证：原 Process 映像生命周期

更新：2026-10-19。技术对象、锁序和剩余授权接合点见 [技术手册](../../../docs/ASTERINAS_PROCESS_IMAGE_G1C.md)。
本手册描述候选源码和应执行的验证，不把预期测试数写成已通过结果。
基线为 `7c675e1d3efe46587edeebe14bd90ac1a842ffbf`，上一轮实际执行源码为 `4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930`。

## 1. 开发范围和回归分层

本切片直接修改原 Process、init 装载、exec／exit 和 `/dev/hepta-control`，新增同目录 image 状态。
现有 [test_util](../../../kernel/asterinas/kernel/core/src/process/test_util.rs) 扩展为可创建多个实际 POSIX Task；原单任务 helper 仍调用相同构造器。
fixture 不登记 PID、不调度空 UserContext；它持有的 Process、VMAR、Task 和原 TaskSet 均为真实对象。

| 验证 | 能够观察的事实 | 实际边界 |
| --- | --- | --- |
| 完整 aster-core／OSTD | 原状态函数、实际对象身份、计数边界、prepared token 消费／拒绝 | 新对象测试不执行 exec／exit syscall，也不运行 fixture UserContext |
| 普通 product boot 与 candidate guest | 原 loader → prepare → resume 真正启动；实际 ioctl、exec、fork、pthread 和非最后线程退出 | 无 native grant，没有 post-boundary fatal exec 注入，也不能在进程彻底退出后由自身发 ioctl |
| host source／parser checks | 原 nonce 不回绕的源码约束、Git 字节和 mode 固定、精确 serial 接受规则 | 不执行内核或模拟 ioctl，不算 guest 测试数 |

退出状态的 core 检查调用实际 Process 状态和原 TaskSet 标志，但不等于执行完整 group／last-thread syscall。
该接合还须审阅 [线程 exit](../../../kernel/asterinas/kernel/core/src/process/posix_thread/exit.rs) 的实际临界区与 [进程 exit](../../../kernel/asterinas/kernel/core/src/process/exit.rs) 的清理顺序。
原普通 guest、Linux32、SCM／RLIMIT 和 CPU probes 同时提供实际 fork／exec／线程／退出回归。

## 2. 新增 18 项 core 对象回归

基线完整 core 为 220 项；只增加以下 18 项时，新 core 分母预计 **238**。
实际分母、成功／失败、filtered 和 soft skip 必须从本候选原始串口独立枚举。
OSTD 的历史 221 reported 包含 3 个 VMX soft skip，不能全部计作执行通过。

### 原 image 状态：9 项

源码：[process/image.rs](../../../kernel/asterinas/kernel/core/src/process/process/image.rs)。
完整名称前缀为 `aster_core::process::process::image::tests::`。

| 测试名 | 关键观察 |
| --- | --- |
| `repeated_opens_share_one_process_image_namespace` | 同 Process 重复会话取得同一非零 key |
| `separately_allocated_process_rejects_foreign_image_key` | 两个独立 Process 不共用 nonce；外来 key 被拒绝 |
| `same_process_tasks_observe_one_live_image` | 两个实际 Task 的 Weak Process 指向同一分配，共享 key |
| `closing_fences_old_sessions_before_image_replacement` | Closing 后旧 key 与新 open 均拒绝；旧 nonce 不被回收 |
| `failed_irreversible_replacement_never_reopens_the_old_image` | Closed 后不能通过 begin／commit／open 恢复旧映像 |
| `successful_replacement_has_new_epoch_and_fresh_namespace` | 成功替换轮换 epoch／nonce，旧 key 失效，Started 不回退 |
| `epoch_exhaustion_closes_the_real_process_without_wraparound` | 原 Process 计数置于极值后调用生产 commit；`EOVERFLOW` 且不回绕 |
| `nonce_exhaustion_is_sticky_for_the_real_process_image` | 使用私有极值 allocator 调用同一生产分配方法，避免污染 boot-global counter；该实际 Process 后续仍拒绝 |
| `closed_image_cannot_be_prepared_or_scheduled_for_the_first_time` | Closed 同时阻止 prepared 和普通首次启动 claim |

### 私有 prepared 绑定：9 项

源码：[init_proc.rs](../../../kernel/asterinas/kernel/core/src/process/process/init_proc.rs)。
完整名称前缀为 `aster_core::process::process::init_proc::tests::`。

| 测试名 | 关键观察 |
| --- | --- |
| `initial_resume_claim_is_consumed_exactly_once` | 第一次消费成功，第二次与普通 first-run 入口均拒绝 |
| `prepared_initial_process_cannot_use_the_ordinary_first_run` | 已 prepared 状态不能重复准备，也不能从普通入口启动 |
| `dropping_unconsumed_preparation_closes_only_its_image` | 丢弃 token 后其映像的 open／旧 key 均失效 |
| `preparation_rejects_a_foreign_process_allocation` | Process 与 pinned VMAR／Task 不匹配时拒绝，不损坏外来 Process 的原 key |
| `preparation_rejects_a_foreign_main_task` | 初始准备拒绝其他 Process 的 Task |
| `resume_rejects_replaced_vmar_and_cancels_the_prepared_image` | 准备后替换 Process 当前 VMAR，消费失败，原 token 放弃关闭其匹配映像 |
| `resume_rejects_a_foreign_task_pin` | 准备后把 token 的 Task pin 换为外来 Task，消费失败 |
| `prepared_old_epoch_cannot_resume_or_close_a_replacement_image` | 旧 token 不能运行新 epoch，Drop 也不能关闭新 key |
| `prepared_exit_group_state_cannot_resume` | 实际 TaskSet group-exit 标志与 Process Closing 后拒绝消费 |

这些测试使用 `claim_resume` 验证原首次启动状态，不调度没有加载程序的测试任务。
真正 `resume` 的登记与调度由每次普通 boot 从实际 init 装载路径执行。

## 3. 普通 guest 的 18 个精确标记

新增四项为 exec 参数 EFAULT 保持会话、缺失路径 ENOENT 保持会话、另一 pthread 共享会话、非最后线程 join 后会话继续有效。
每次比较完整 16 字节 boot 和 space，检查旧 fd 与 fresh open，并验证完整 QueryAbi-only 响应。
具体请求和 marker 表见 [guest 手册](README.md)。

原 [queryabi_guest.c](queryabi_guest.c) 和 [run_queryabi_guest.py](run_queryabi_guest.py) 字节保持原样。
candidate wrapper 保留原七个身份／权限标记、原成功标记、四个有效资源请求的 `EOPNOTSUPP` 标记、candidate 完成标记和最终 boot 标记。
新增四项插在原成功标记之后、四个资源请求之前；exec 子进程只执行原 epoch check 后返回。
全部 **18** 个标记必须各出现一次并满足原 root completion 顺序；缺失、重复、倒序、panic、超时或非整数原始退出码 33 都拒绝。
候选 C 增加 `-pthread`，仍按原 `-std=c11 -O2 -Wall -Wextra -Werror -static` 编译。

## 4. 本地检查与固定 CI

在仓库根执行 host 检查，日志放在 checkout 外；这些命令不创建新的内核资格：

```sh
python3 -I -B -m unittest discover -s tests/spec -p 'test_*.py' -v
python3 -I -B -m unittest discover -s tests/kernel/control -p 'test_*.py' -v
python3 -I -B -O -m unittest discover -s tests/kernel/control -p 'test_*.py' -v
cc -std=c11 -O2 -Wall -Wextra -Werror -pedantic -pthread -static \
  tests/kernel/control/queryabi_candidate_guest.c -o /tmp/g1c-queryabi-probe
```

内核与普通产品沿原 [.github/workflows/a06-kernel.yml](../../../.github/workflows/a06-kernel.yml)，
使用固定 `nightly-2026-07-21`、source-built OSDK、固定 vDSO／SeaBIOS 和原锁文件派生。
准备命令见 [build](../../../support/build/README.md) 及 [ktest](../../../support/build/ktest/README.md)，完整 CPU 负控复跑见 [G1-b 开发手册](../../organ_backend/CPU_USAGE_G1B.md)。
不要在同一 checkout／共享 target 并行执行内核构建。
没有固定工具链的环境只能给出 host 或明确标为旧产品的探针预检，不能声称已编译当前 Rust 源码。

在已冻结、干净、带完整 Git head／tree 的候选执行：

```sh
python3 -I support/build/ktest/run.py --output /absolute/fresh/g1c-ktest
python3 -I tests/kernel/control/run_queryabi_candidate_guest.py \
  --expected-source-head REVIEWED_40_HEX_COMMIT \
  --expected-source-tree REVIEWED_40_HEX_TREE \
  --output /absolute/fresh/g1c-queryabi-candidate
```

CI 继续执行两套完整内核测试、七个原 CPU 生产缺陷负控、普通 boot／QueryAbi18、SCM27、RLIMIT37、Ubuntu full32 Linux／guest 同输入、四配置及有界 1／2 vCPU 原配额门槛。
本切片没有改负控预期失败集、过滤测试、增大超时或放宽 CPU 阈值。
七个负控必须完整运行当前 core，并保留原失败名称和与绿色全集完全一致的测试名称集合。

## 5. 可合入的证据和后续范围

最终验收保存实际执行 head／tree、原官方 artifact 身份、完整源文件字节／mode、工具链与 lock、普通／ktest ELF、QEMU argv、原始 serial 和进程退出码。
对绿色 core／OSTD 枚举实际结果，对七负控枚举精确预期失败，对普通 guest 验证 18 个标记，再交叉检查普通 Linux／CPU 所用 ELF。
旧产品的探针预检只证明新增 C 路径可运行；新产品必须有自己的原始 CI 产物。
首次失败或修复前日志保留，后一次通过不能改写前一次结果。

这批改动完成映像状态与原启动路径的接合。
静态最终映像认证、可写别名保护、canonical grant 与原 owner 同步、ReadUsage 正例及完整 HOS2／Hepta K↔D 仍是后续实施项。
关闭 image 不释放 CPU 尾账 owner，也不授予完整 SMP、物理设备、Android 或原生桌面资格。
