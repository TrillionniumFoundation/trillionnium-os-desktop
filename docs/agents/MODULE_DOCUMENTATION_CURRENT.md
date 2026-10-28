# 当前 Desktop／Hepta 模块开发与技术导航

本页绑定XKB CI依赖修复后的V5代码基点 `8b825fb742b4722259a7fd7b962565adf21d2fff`（tree `a4df7550ee172cd91535ce980a299526fb67c09f`，8088路径）。
本次更新五个文档路径：`docs/agents/MODULE_DOCUMENTATION_CURRENT.md`、
`docs/agents/MODULE_DOCUMENTATION_CURRENT.json`、`support/release/README.md`、
`docs/agents/ORGAN_RELEASE_PROFILE.md`、`support/ui/RUN.md`。
[机器清单](MODULE_DOCUMENTATION_CURRENT.json)的 `desktop_code` 是写入文档前的代码基点；
`documentation_delta_paths` 内的来源记录对应文档successor实际字节，不声称新文档blob存在于代码基点的tree。
最终文档提交HEAD/tree由外置source收据绑定，避免自引用；其余Desktop记录绑定此8b825代码基点。
当前manifest仍保留6487组合声明，须在文档提交后另行完成新tuple的typed source重绑定；本文不称新组合已完成门禁。
8b825相对冻结6487只在两个workflow的三个Linux apt列表追加XKB X11开发包；V5固定map、CLI producer和产品源码未改。
从f4cd旧261-role快照补齐CLI producer的682代码和6487文档／manifest保留原来源；后文b6a／231、682实际QA也保留历史身份。
Desktop从原Unix组合纳入六个原OOM提交，基点27c5043d，再逐字采用4018门禁组件并新增固定V5。
Hepta目标是 `7673ea62fc019f97ad17d205ee1f81f96e0f47a0`，tree `ff2372f10656d2e8f652b6ca1e6de03a075b9219`（9214路径）。

**当前资格仍是源码与发布工具验证；最终版本组合、GUI、native持久链和生产授权尚需各自同源收据。**
更正后的V5固定396 OS／271 Hepta角色、5对golden和19个Hepta owning packages。七项生产输入保持关闭。
原V1–4地图、显式历史验证、旧失败和原收据保留；新commit不自动继承组件运行资格。

## 文档与来源如何阅读

[2026-10-26 审计](MODULE_DOCUMENTATION_2026_10_26.md)及其 JSON／公开摘要保持原样。
其中 d3ae/fef6、348 Core、13 owners 和1709 host测试是历史来源，不能替换成本页代码的执行结果。
4d4原文档提交的十二路径中，十一已在cec3/e7ed逐mode/blob相同；其余release README已有后续更新。
当前页补充源组合、开发入口和具体缺口，不复制一套模板来宣称每个crate都有完整双手册。

每行的技术文档说明实际接口／状态／错误边界；开发入口说明代码与验证位置。源码、模型测试、
真实Linux host、GUI、内核guest、原生Hepta持久owner、生产授权和真实硬件分别记录资格。
下文产品／GUI／guest命令是**待执行入口**，本次文档刷新未执行它们。发布工具的实际fixture结果单列于后文；机器清单保存相应路径、Git mode/blob和SHA256。

## A00–A10 当前入口与边界

| 模块 | 技术契约与实际源码 | 开发／验证入口 | 当前缺口与不可外推项 |
| --- | --- | --- | --- |
| A00 集成／发布 | [发布合同](ORGAN_RELEASE_PROFILE.md)、[release开发](../../support/release/README.md)；固定V5 396／271 literal map | 新V5 caller／原V4历史caller，六互斥CI分区；source-only命令见release手册 | 396／271与19 owners仅固定装配。实际pair七步、GUI／native和七项生产输入仍分别验收。 |
| A01 上游／启动 | [构建手册](../../support/build/README.md)、[上游Book](../../kernel/asterinas/book/src/SUMMARY.md)；`kernel/asterinas/{kernel,ostd,osdk}` | [ktest手册](../../support/build/ktest/README.md)、`support/build/verify-source.py`、下方Core入口 | 新候选必须绑定自己的完整源码、OSDK、普通内核与各测试ELF。上游共享Book与源码注释不等于所有低层crate都有运行手册。 |
| A02 HOS2 codec | [ABI包入口](../../libs/os-abi/README.md)、[Native ABI](../NATIVE_ABI.md)；`libs/os-abi` | `python3 -I -B tests/abi/run_acceptance.py`，协议样本与拒绝断言见该目录 | 五种wire格式不等于ordinary内核开放五类效果；当前普通控制路径仍按QueryAbi门禁。 |
| A03 Control core | [API合同](../../libs/os-control/API_CONTRACT.md)；`libs/os-control`及真实后端接点 | [control验证手册](../../tests/control/VALIDATION.md)、[no_std验证](../../tests/control/backend_no_std/VALIDATION.md)，`bash tests/control/run-validation.sh` | host/Loom模型不能代替内核执行和原Hepta持久终态。`tests/control/loom`没有独立完整开发／技术手册。 |
| A04 Linux／存储／Unix信号 | [Linux缺口](../../compat/linux/GAPS.md)、[STREAM SIGPIPE合同](../../support/kernel-safety/UNIX_SOCKET_SIGPIPE.md)、[SQLite重启](../../tests/workloads/linux/SQLITE_GUEST_RESTART.md)；Unix `stream/{connected,socket}.rs`、syscall `{pwritev,sendmmsg}.rs` | [42-case真实guest](../../tests/kernel/unix-signal/README.md)、[fixed132 profile](../../tests/kernel/network/POST1138_UNIX_SIGNAL_PROFILE.md)、[Linux workload](../../tests/workloads/linux/README.md)；下方Unix命令 | 只对类型确认的Unix STREAM走单次writev/send路径；后来iovec故障保留已复制前缀。SEQPACKET、TCP、UDP、vsock保留原路径，不能宣传其完整信号／向量语义。小Tokio workload仍用共享手册。 |
| A05 进程／权限／映像 | [Process映像](../ASTERINAS_PROCESS_IMAGE_G1C.md)、[安全入口](../../support/kernel-safety/README.md)；`security/lsm/modules/capability.rs`、process、x86 VM retirement | [control探针](../../tests/kernel/control/README.md)、[safety探针](../../tests/kernel/safety/README.md)；`python3 -I -B tests/kernel/safety/run.py --help`后按手册选定真实probe | capability目标能力约束、namespace、exec与VM寿命按实际owner测试判定。已纳入六个原OOM floor／VM生命周期提交；[OOM合同](../../support/kernel-safety/OOM_ADJUSTMENT.md)和[真实guest手册](../../tests/kernel/oom-adjustment/README.md)给出开发入口。memory.max、OOM killer及MAC管理资格仍未建立。 |
| A06 调度／资源 | [FAIR运行](../../support/kernel-safety/FAIR_RUNTIME.md)、[组实体](../../support/kernel-safety/FAIR_GROUP_ENTITIES.md)、[CPU bandwidth](../ASTERINAS_CPU_BANDWIDTH_N0.md)、[调度权限](../../support/kernel-safety/SCHEDULING_PERMISSIONS.md) | [forced affinity](../../tests/kernel/forced-affinity/README.md)、[FAIR](../../tests/kernel/fair-runtime/README.md)、[page](../../tests/kernel/page-memory/README.md)；以手册原145%／3% quota和SMP配置运行 | 已有root route、route pin、强制affinity handoff、初次CPU选择与CPUNODE修复。SMP max仍缺remote rendezvous；c235 guard仅独立分支，未纳入当前kernel。普通`cpu.weight`仍拒绝；冷代／活跃更新9516另支未纳入。`hepta.anon.*`不是完整`memory.max`；无假启用。 |
| A07 Hepta原owner／装配 | [适配器合同](../../services/hepta-os/CONTRACT.md)、[RUN](../../services/hepta-os/RUN.md)；原Hepta19包与下表新专册 | `cargo +1.88.0 test --manifest-path services/hepta-os/Cargo.toml --features cpu-history --locked`；Hepta原19包Rust测试、SDK50、MCP验证见下方 | observer/history不签发授权、不拥有原writer。State启动、Root恢复、授权lease、OAuth与SDK各有独立owner；组件结果不自动成为本组合资格。 |
| A08 Android／Binder | [Binder字节](../../support/android/BINDER_BYTES.md)、[线程D1](../../support/android/BINDER_THREADS.md)、[seccomp](../../support/android/SECCOMP.md)；内核Binder owner | [Binder probe手册](../../tests/kernel/binder/README.md)、[Android入口](../../support/android/README.md)，`python3 -I -B tests/kernel/binder/thread_run.py --help`后按原手册执行 | 有界实际线程同步IPC不等于自动线程池、nested/oneway、FD arrays、Android boot／CTS／SELinux／BSP完成。 |
| A09 硬件／GPU／VMM | [硬件合同](../HARDWARE_AND_DRIVERS.md)、[DMA domains](../../support/kernel-safety/DMA_DOMAINS.md)、[VMM gates](../../support/vmm/GATES.md) | [硬件runbook](../../tests/hardware/RUN.md)、[lifecycle模型](../../support/vmm/device_lifecycle/README.md)，`cargo +1.88.0 test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked`只验证模型 | 共享IOMMU页表或枚举不证明设备间DMA隔离。现实现限Intel VT-d与root-bus/function-zero入口；AMD平台或同组多功能GPU不能据此证明设备间DMA隔离。模型、有限requester测试不证明GPU reset／真实手机支持；`kernel/asterinas/kernel/comps/README.md`仍仅标题。 |
| A10 Session／Notes／桌面交互 | [整帧期限](../../support/ui/SESSION_IPC.md)、[真实文档持久化](../../support/ui/NOTES_PERSISTENCE.md)、[X11合同](../../support/ui/DESKTOP_X11.md)；`ui/{session,core,app-window,broker,shell}` | [五包导航](../../ui/README.md)、[host runbook](../../support/ui/RUN.md)；下方UI／GUI入口 | 500ms是整帧总期限、至多32连接且每tick有界推进。Notes文本／revision／精确回执共同sync/rename/目录sync；回执ACK不替代文档或Hepta持久终态。8b825已补CI的XKB X11安装源，尚未新运行；通用第三方应用、文件选择器／设备控制仍未完成。 |

`--help`仅给出probe的实际CLI，不能当运行验收；具体参数、隔离fixture、fresh输出目录和原预算以链接手册为准。
Desktop清点仍是127份manifest、15个自有入口和5个UI成员，三输入manifest逐mode/blob相同；这不是依赖解析或完整手册审查。

## 开发与验证命令

UI与adapter沿用Rust1.88，Hepta沿用1.95和原dev-small profile；均用锁文件和真实原包名。
下面host命令只有在新source tuple及门禁正式绑定后才形成新收据；当前文档提交不运行它们。

```sh
cargo +1.88.0 build --manifest-path ui/Cargo.toml --workspace --bins --locked
cargo +1.88.0 test --manifest-path ui/Cargo.toml --workspace --locked
cargo +1.88.0 test --manifest-path services/hepta-os/Cargo.toml --features cpu-history --locked
python3 -I -B -m unittest discover -s support/release -p 'test_*.py'
python3 -I -B -O -m unittest discover -s support/release -p 'test_*.py'
```

最后两项是发布工具的完整CI union；本地本轮只执行旧54、原7 Workflow与全部新V5的必要增量，两模式实际结果见下表。4018其余typed组件证据保持原来源；不能把它改名为新全套或产品通过。
Hepta complete owning测试须在其仓库根使用原`just test`调度，固定两线程、零重试、原case预算；
18原包全部保留，再增加实际OAuth包`codex-rmcp-client`。包清单见机器清单的`hepta_owners`，不预填测试总数。
七步为UI build／UI tests／adapter tests／agentd＋正常CLI build／authority-host build／supervisor-recovery build／19-owner tests。
旧pair产品分别保留原hash；新stage4必须构建同源正常CLI，SDK也须绑定该新产品，不能将旧85f或7786 CLI改名为7673。

准备自己OSDK和普通内核后，Core与Unix验证入口为：

```sh
python3 -I -B support/build/ktest/run.py --crate aster-core --skip-osdk-install --output /absolute/fresh-core-evidence
python3 -I -B -m unittest discover -s tests/kernel/network -p 'test_*.py'
python3 -I -B -O -m unittest discover -s tests/kernel/network -p 'test_*.py'
python3 -I -B -m unittest discover -s tests/kernel/unix-signal -p 'test_*.py'
python3 -I -B -O -m unittest discover -s tests/kernel/unix-signal -p 'test_*.py'
python3 -I -B tests/kernel/network/run_unix_stream_oom_guest.py \
  --expected-source-head FULL_HEAD --expected-source-tree FULL_TREE \
  --target-dir /absolute/owned-kernel-target --output /absolute/fresh-unix-evidence \
  --source-profile post-1138-oom-adjustment-v2 --variant positive --selection all
```

不得用占位HEAD/tree运行。参数须来自当前真实clean源，Unix guest还须绑定独立验证的同一普通产品ELF。
repeat `shutdown_race`、原38正向／7负向、SMP1/2/4、quota145%/3%、Binder／clock／handoff等原检查保持其预算和断言。
本次源码组装已逐mode/blob保留fixed132；当前OOM增量已有独立strict182 `post-1138-oom-adjustment-v2`；旧fixed132仍绑定原e7ed历史字节，不能用于当前ELF，详见[新profile合同](../../tests/kernel/network/POST1138_OOM_ADJUSTMENT_PROFILE.md)。

三项owned GUI必须在新host成功后依原runbook运行：Notes实际授权fixture往返、crash/reopen与X11。
原issuer/current-cut fixture属于测试授权；真实生产签发、受保护时钟／frontier、公钥／撤销、恢复writer和Current
仍是七项关闭输入。超时或崩溃后不确定结果必须观察并保留unknown，禁止据此自动重发。

## 原Hepta19包：新增开发／技术入口

Hepta路径相对其仓库根、固定7673目标。机器清单列出十九个实际Cargo package／manifest、邻接Markdown与共享技术入口。
18原owner是agentd、memory、cognitive-store、contracts、state、agent-protocol、learning-ledger、git-utils、
memory-extension、automation、fleet、supervisor、arg0、app-server-protocol、thread-store、core-plugins、rollout、file-system；
新增第19包为`codex-rmcp-client`，不能用SDK测试替代其Rust owning tests。

| 当前变更／owner | 具体技术文档 | 开发／回归位置 |
| --- | --- | --- |
| State五库启动 | `codex-rs/state/STARTUP_INITIALIZATION.md` | `codex-rs/state/src/runtime.rs`、`runtime/startup_tests.rs`；原primary gate后四独立库并行join，全完成／失败清理；不是已证明的唯一timeout修复。 |
| Root／fixture生命周期 | `codex-rs/hepta-agentd/{ROOT_COMPOSITION.md,ROOT_SERVICE.md}`、`codex-rs/rollout/TEST_FIXTURES.md` | 实际agentd／fleet／supervisor owning cases、完整原预算与终态。 |
| authority lease并发 | `codex-rs/hepta-contracts/AUTHORITY_LEASE_CONCURRENCY.md` | contracts真实授权lease／Root检查及原rollback边界。 |
| OAuth discovery | `codex-rs/rmcp-client/OAUTH_DISCOVERY.md` | `codex-rmcp-client`原包测试及SDK OAuth链；不能仅依共享MCP模型。 |
| SDK子进程／fixture | `sdk/typescript/CHILD_LIFECYCLE.md`、`sdk/typescript/tests/FIXTURE_LIFECYCLE.md` | 其原SDK50／7 suites／0skip调度，保留新源／CLI绑定。 |
| MCP profile／vendor | `scripts/mcp_conformance/{README.md,CONFORMANCE_PROFILES.md,EXECUTION_IDENTITY.md}`、`third_party/MCP_CONFORMANCE.md` | 274项原Python/vendor/profile检查及各真实conformance profile；原已知失败／跳过保持原来源，不称all-MCP green。 |

cognitive-store、agent-protocol、memory-extension、automation、fleet、arg0、core-plugins、file-system这八包
没有包内Markdown，仍需共享模块／源码入口与具体运维缺口说明；相邻Markdown存在也不能证明完整双手册。
State现在有专册，旧13-owner审计将它列为仅共享／源码入口的结论不再适用于其原7786，当前7673继续保留专册。
40模块指南曾作结构清点，未逐篇完成语义／API审查；本文不补写不存在的通过记录。

## 逐包开发与技术合同

以下每包给出当前用途、真实源码、接口／状态／错误边界、开发验证命令和缺口。命令均未在本次文档任务执行。
Desktop路径相对本仓库根；Hepta路径和命令相对固定7673的仓库根。Hepta命令沿原`just test`调度、
Rust1.95、dev-small、两线程、零重试和原case预算；离线依赖未具备时应停止并保留失败，不能静默改用其他源码或ELF。

### Desktop自有入口

#### hos2-os-abi

HOS2五类wire格式的有界codec与golden拒绝检查。

- 源码：`libs/os-abi/src/lib.rs`。
- 技术合同：字节长度、版本、保留字段、状态和payload必须按codec验证；Rust内存布局不充当wire。
- 开发验证：`python3 -I -B tests/abi/run_acceptance.py`。
- 当前缺口：codec或golden成功不开放普通内核的效果操作。

#### os-control

boot-local delivery D的状态机和原owner/native adapter seam。

- 源码：`libs/os-control/src/lib.rs`。
- 技术合同：reserve/execute/query/retire保持instance/target/ancestor/CAS绑定；HistoryLost/NotSeen不授予重发，持久K仍由Hepta拥有。
- 开发验证：`bash tests/control/run-validation.sh`。
- 当前缺口：host与portable-spin/Loom证据不代替IRQ、真实内核owner与跨重启终态。

#### hepta-os-observer

读取原Hepta runtime/history并映射给Desktop的observer适配器。

- 源码：`services/hepta-os/src/lib.rs`、`services/hepta-os/src/bin/hepta-observe.rs`、`services/hepta-os/src/bin/hepta-submit.rs`、`services/hepta-os/src/bin/hepta-history.rs`。
- 技术合同：只读观察不签名、不拥有writer；本地传输错误/历史未知不得合成效果成功或新grant。
- 开发验证：`cargo +1.88.0 test --manifest-path services/hepta-os/Cargo.toml --features cpu-history --locked`。
- 当前缺口：需同源原Agentd产品与真实授权装配验证；fixture peer不是部署。

#### trill-ui-boundary

renderer与host之间的默认拒绝边界模型。

- 源码：`support/ui/src/lib.rs`。
- 技术合同：typed observation/offline draft与capability保持分离；效果提交默认拒绝，不能把状态缓存当原持久账本。
- 开发验证：`cargo +1.88.0 test --manifest-path support/ui/Cargo.toml --locked`。
- 当前缺口：shared边界文档存在；host模型不证明显示、通用设备输入或授权。

#### a09-device-lifecycle

设备域生命周期与归属转换模型。

- 源码：`support/vmm/device_lifecycle/src/lib.rs`。
- 技术合同：按既有lifecycle状态/错误边界建模请求者与退役；模型数据不等于硬件DMA页表实际隔离。
- 开发验证：`cargo +1.88.0 test --manifest-path support/vmm/device_lifecycle/Cargo.toml --locked`。
- 当前缺口：真实IOMMU requester、GPU reset和手机BSP仍需物理设备验收。

#### os-control-backend-no-std

外部no_std后端编译fixture，验证公开LockBackend/ControlMutex接入。

- 源码：`tests/control/backend_no_std/src/lib.rs`。
- 技术合同：guard保持!Send，owner/view/token保持Send+Sync；类型检查native seam，不运行真实allocator/IRQ/scheduler。
- 开发验证：`cargo +1.88.0 build --locked --manifest-path tests/control/backend_no_std/Cargo.toml --target x86_64-unknown-none`。
- 当前缺口：仅编译fixture；与Asterinas实际锁纪律分开。

#### os-control-loom

default/public backend两路并发模型。

- 源码：`tests/control/loom/Cargo.toml`。
- 技术合同：models与models_public必须沿run-models脚本保留生产模块和backend替换边界，不能直接编译残缺fixture声称模型已跑。
- 开发验证：`python3 -I -B tests/control/loom/run-models.py /absolute/fresh-model-evidence --offline --variant all`。
- 当前缺口：只有共享验证手册；Loom状态探索不提供真实内核SMP/IRQ或持久化证明。

#### trillionnium-ui-contracts

UI契约与host边界回归包。

- 源码：`tests/ui/src/lib.rs`。
- 技术合同：模型/序列化用例与真实Session、GUI呈现、CJK/IME证据各自记录，不把布局等同pixels。
- 开发验证：`cargo +1.88.0 test --manifest-path tests/ui/Cargo.toml --locked`。
- 当前缺口：需新整组host及隔离GUI实测；硬件输入和第三方应用仍未完成。

#### a04-tokio-workload

有锁依赖的Tokio Linux兼容workload。

- 源码：`tests/workloads/linux/rust/src/main.rs`。
- 技术合同：固定Tokio direct dependency与runtime场景；构建、原生Linux reference和guest syscall结果分开。
- 开发验证：`cargo +1.88.0 build --manifest-path tests/workloads/linux/rust/Cargo.toml --locked`。
- 当前缺口：共享workload手册；构建通过不能替代pathname AF_UNIX及guest运行。

#### UI workspace（无独立package）

五个UI成员的独立Cargo workspace入口。

- 源码：`ui/Cargo.toml`。
- 技术合同：Cargo workspace只组合真实core/broker/session/shell/app-window，build/test的源码tuple和产品hash分别保留。
- 开发验证：`cargo +1.88.0 test --manifest-path ui/Cargo.toml --workspace --locked`。
- 当前缺口：workspace没有单独package；实际图形、Notes持久owner和原授权仍需后续门禁。

#### trill-app-window

Notes、Calculator与固定allowlist terminal的GUI进程。

- 源码：`ui/app-window/src/main.rs`。
- 技术合同：Notes document/revision/receipt原子持久化；private effect/recovery交给GUI线程；新incarnation可观察旧回执但不能重放旧效果。
- 开发验证：`cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-app-window --locked -j 2`。
- 当前缺口：legacy无store探针仍仅内存；真实GUI crash/reopen与文档选择器尚需整组验收。

#### trill-ui-broker

renderer默认拒绝broker，以及独立private Notes/X11 destination。

- 源码：`ui/broker/src/lib.rs`。
- 技术合同：renderer不持有效果handle；private exact-byte I/O和XTEST/XGetImage回执不替代原Hepta授权、journal或应用业务终态。
- 开发验证：`cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-ui-broker --locked -j 2`。
- 当前缺口：第三方应用/显示域授权与真实生产owner仍需独立验证。

#### trill-ui-core

Session/frame/task、观察、会话草稿、Notes与display的共享typed协议。

- 源码：`ui/core/src/lib.rs`。
- 技术合同：frame与task有界；Notes exact bytes/revision/receipt和bootstrap v1/v2保持身份绑定，objective draft不自动成为签名request。
- 开发验证：`cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-ui-core --locked -j 2`。
- 当前缺口：protocol/持久化单测不代替真实Session/GUI和原Hepta终态。

#### trill-session

单一host进程状态owner、Launch/Cancel/reap与private bootstrap。

- 源码：`ui/session/src/main.rs`。
- 技术合同：同effective UID先验peer；整帧500ms不随字节续期，最多32连接、每tick有界推进；generation绑定child incarnation。
- 开发验证：`cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-session --locked -j 2`。
- 当前缺口：同UID不是互不信任应用隔离；parsed command仍须保持有界，新组合需真实慢连接/child reaping回归。

#### trill-shell

egui workspace、local drafts、tasks/context/console与原runtime观察。

- 源码：`ui/shell/src/main.rs`。
- 技术合同：Session拥有process，Shell只发有界host请求；signed-request页传已有envelope，普通启动不配置authority，draft不自动提交。
- 开发验证：`cargo +1.88.0 test --manifest-path ui/Cargo.toml -p trill-shell --locked -j 2`。
- 当前缺口：实际pixels/IME/通用第三方应用和设备控制未由layout或单包tests证明。

### 原Hepta owning packages

#### codex-hepta-agentd

每个workspace的原AgentId进程宿主，组合原App Server、writer与受保护Root通道。

- 源码：`codex-rs/hepta-agentd/src/lib.rs`、`codex-rs/hepta-agentd/src/production_root_composition.rs`、`codex-rs/hepta-agentd/src/root_authority_session.rs`、`codex-rs/hepta-agentd/src/root_observation_worker.rs`、`codex-rs/hepta-agentd/src/operations_host.rs`。
- 技术合同：AgentdRootProductionInputs接收既有bootstrap与五条固定通道；Root观测过期、peer寿命或proof不匹配会fence。持有原writer并等待close；发送后Unknown按原operation身份核对，不能重新授权重发。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-agentd --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：本源码组合没有完整host/native/生产验收；七项原信任装配未验证。Root组件通过不能转移为这个整组通过。

#### codex-hepta-memory

原CognitiveStore的授权写入、受保护checkpoint和只读历史观察接点。

- 源码：`codex-rs/hepta-memory/src/lib.rs`、`codex-rs/hepta-memory/src/cognitive_checkpoint.rs`、`codex-rs/hepta-memory/src/cognitive_current.rs`、`codex-rs/hepta-memory/src/production_writer.rs`。
- 技术合同：ProtectedCognitiveCheckpoint绑定原owner与独立Current cut；sole recovered store先完成pool关闭再绑定writer/READONLY观察池。不确定publication或取消永久fence当前generation；lost acknowledgement保持Unknown。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-memory --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：独立部署的受保护Current、恢复anchor和原publisher fence仍需实际装配；SQLite摘要不能替代外部受信cut。

#### codex-hepta-cognitive-store

追加式认知账本、修正与tombstone lineage，以及受控durable SQLite存储。

- 源码：`codex-rs/hepta-cognitive-store/src/lib.rs`、`codex-rs/hepta-cognitive-store/src/durable.rs`、`codex-rs/hepta-cognitive-store/src/production.rs`、`codex-rs/hepta-cognitive-store/src/v2.rs`。
- 技术合同：DurableCognitiveStore通过CognitiveAccess/CognitiveRecoveryRequirement区分访问与恢复；写入返回CognitiveWriteReceipt，恢复错误由CognitiveRecoveryError表达。不能把内存qualification ledger当持久原owner或效果执行器。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-cognitive-store --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：无包内Markdown；本节补开发技术入口，跨重启真实授权、外部cut与产品writer压力仍需整组验证。

#### codex-hepta-contracts

原身份、FinalUse、lease、Root时钟/frontier与typed授权线协议。

- 源码：`codex-rs/hepta-contracts/src/lib.rs`、`codex-rs/hepta-contracts/src/final_use.rs`、`codex-rs/hepta-contracts/src/authority_lease.rs`、`codex-rs/hepta-contracts/src/authority_trust.rs`、`codex-rs/hepta-contracts/src/authority_root_frontier.rs`。
- 技术合同：FinalUse校验绑定subject/destination/policy与原issuer；lease并发及protected frontier受原门禁约束。HostAuthorityClock与RootFinalUseFrontierClient是受信观察接点，wire或公钥的存在本身不授予执行。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-contracts --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：原issuer keyring、撤销head、clock与frontier需要实部署证明；测试签名fixture不提供生产授权。

#### codex-state

rollout元数据、projects/queue等原SQLite状态和五库启动/恢复。

- 源码：`codex-rs/state/src/lib.rs`、`codex-rs/state/src/runtime.rs`、`codex-rs/state/src/runtime/startup_tests.rs`、`codex-rs/state/src/sqlite.rs`、`codex-rs/state/src/sqlite_recovery.rs`。
- 技术合同：原primary初始化成功后启动其余四库，join全部结果并等待失败清理；commit hook接入protected Dirty invalidation，replacement连接也安装hook。失败返回原错误，不宣称跨库原子rollback。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-state --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：五库启动修改尚未证明解决当前整组四个timeout；必须按原60s/180s预算重新跑产品用例。

#### codex-hepta-agent-protocol

agentd与supervisor共享的有界本地控制请求、能力协商和历史结果类型。

- 源码：`codex-rs/hepta-agent-protocol/src/lib.rs`、`codex-rs/hepta-agent-protocol/src/capabilities.rs`、`codex-rs/hepta-agent-protocol/src/authbus.rs`、`codex-rs/hepta-agent-protocol/src/objective_history.rs`。
- 技术合同：AGENTD_CONTROL_SCHEMA_VERSION=2，MAX_CONTROL_FRAME_BYTES=65536；能力协商与ObjectiveAdmissionUnknownReason保留拒绝/未知。HostTurnAuthorityBinding是transport witness，不能作为grant或默认启用runtime consumer。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-agent-protocol --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：无包内Markdown；typed编码不证明peer身份、真实授权或执行效果，必须由原宿主鉴权与持久终态验证。

#### codex-hepta-learning-ledger

追加式因果学习事实、独立outcome及撤销lineage。

- 源码：`codex-rs/hepta-learning-ledger/src/lib.rs`、`codex-rs/hepta-learning-ledger/src/durable.rs`、`codex-rs/hepta-learning-ledger/src/error.rs`、`codex-rs/hepta-learning-ledger/src/production.rs`、`codex-rs/hepta-learning-ledger/src/production_growth_tests.rs`。
- 技术合同：纯core没有环境I/O或执行权；opt-in durable adapter只经host授权文件句柄记录事实，错误和恢复受原journal/lock协议约束。记录不授予model/tool/network/selection/promotion/release权。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-learning-ledger --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：原容量压力timeout仍保留；需要新整组下的原预算和持久恢复验证，不能删容量用例换通过。

#### codex-git-utils

共享Git子进程、status/diff、patch与受信repo处理。

- 源码：`codex-rs/git-utils/src/lib.rs`、`codex-rs/git-utils/src/git_process.rs`、`codex-rs/git-utils/src/trust.rs`、`codex-rs/git-utils/src/status.rs`、`codex-rs/git-utils/src/errors.rs`。
- 技术合同：GitToolingError保留命令失败；SAFE_BARE_REPOSITORY_CONFIG限制隐式bare repo，FsmonitorOverride管理外部fsmonitor边界。Git查询/patch接口不提供Hepta原owner历史证明或授权。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-git-utils --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：单元Git fixture与跨repo真实source admission分开；不能将status干净当全部实际字节/模式或历史完整。

#### codex-hepta-memory-extension

把原memory观察/认知接点接到extension，保留本地开发owner与shadow边界。

- 源码：`codex-rs/ext/hepta-memory/src/lib.rs`、`codex-rs/ext/hepta-memory/src/extension.rs`、`codex-rs/ext/hepta-memory/src/advisory_observation.rs`、`codex-rs/ext/hepta-memory/src/local_lifecycle.rs`、`codex-rs/ext/hepta-memory/src/local_turn_writer.rs`。
- 技术合同：ShadowAdvisoryObservationInput经observe_shadow_advisory等typed接口校验；shadow常量明确external-effects/KG-write边界。workspace/domain digest用于绑定，不能凭摘要创建受信writer或生产grant。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-memory-extension --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：无包内Markdown；本地development lifecycle和advisory观测不等于生产Root恢复/跨host控制。

#### codex-hepta-automation

每Agent持久automation queue、timer materialization与TaskFlow生命周期。

- 源码：`codex-rs/hepta-automation/src/lib.rs`、`codex-rs/hepta-automation/src/authorized_effect.rs`、`codex-rs/hepta-automation/src/dispatch_recovery.rs`、`codex-rs/hepta-automation/src/taskflow.rs`、`codex-rs/hepta-automation/src/taskflow_execution_boundary.rs`。
- 技术合同：Core queue admission与terminal execution分离；AuthorizedEffectIntent绑定operation/subject/destination/policy与依赖。AuthorizedEffectOutcome/DriverError保留效果查询和失败边界，下游效果仍需原final-use与terminal observer。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-automation --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：无包内Markdown；timer触发不等于效果完成，原retirement/recovery与unknown provider-effect必须在真实owner链验收。

#### codex-hepta-fleet

supervisor拥有的独立Agent注册、release、allocation与持久control状态。

- 源码：`codex-rs/hepta-fleet/src/lib.rs`、`codex-rs/hepta-fleet/src/registry.rs`、`codex-rs/hepta-fleet/src/error.rs`、`codex-rs/hepta-fleet/src/allocation.rs`、`codex-rs/hepta-fleet/src/lease_ledger.rs`。
- 技术合同：FleetRegistryError区分WorkspaceConflict、StaleGeneration、StaleReleaseGeneration、ReleaseRevoked与InvalidTransition；registry不执行turn、不转发消息。allocation只计算claim，不能证明内核已强制CPU/内存限额。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-fleet --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：无包内Markdown；五/六Agent真实产品生命周期超时未在新组合闭合，计算或registry单测不能替代。

#### codex-hepta-supervisor

原Agent进程生命周期、restart budget、release handoff与签名intent恢复。

- 源码：`codex-rs/hepta-supervisor/src/lib.rs`、`codex-rs/hepta-supervisor/src/daemon.rs`、`codex-rs/hepta-supervisor/src/recovery.rs`、`codex-rs/hepta-supervisor/src/restart_budget.rs`、`codex-rs/hepta-supervisor/src/process_deadline.rs`、`codex-rs/hepta-supervisor/src/authority_signer.rs`。
- 技术合同：SupervisordClient/daemon协议管理进程；restart journal/budget与result fence独立于turn执行。ExternalSignerError保留原外签名失败，私钥输入经既有FD/path seam，不由Desktop生成替代issuer。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-hepta-supervisor --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：paired process和crash recovery须保留原产品ELF、watchdog与实际终态；进程重启成功不等于旧effects可重发。

#### codex-arg0

原CLI/宿主的隐式helper分派与child re-exec稳定路径。

- 源码：`codex-rs/arg0/src/lib.rs`。
- 技术合同：Arg0DispatchPaths显式保留当前Codex executable与helper路径；arg0_dispatch_or_else经原dispatch进入宿主。不能以test harness的current_exe冒充CLI，也不能更换helper后继承旧ELF资格。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-arg0 --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：无包内Markdown；平台helper/权限和真实CLI消费仍需新源build与SDK验证，本包单测不能代替。

#### codex-app-server-protocol

原App Server RPC类型、线程history投影及JSON/TS schema导出。

- 源码：`codex-rs/app-server-protocol/src/lib.rs`、`codex-rs/app-server-protocol/src/rpc.rs`、`codex-rs/app-server-protocol/src/precomputed_exports.rs`、`codex-rs/app-server-protocol/src/schema_fixtures.rs`。
- 技术合同：generate_json/generate_ts及precomputed exports使用既有协议类型；schema fixture和生成输出必须绑定同源并保留序列化拒绝条件。协议值或生成schema不证明网络peer/production authority。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-app-server-protocol --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：完整协议兼容与真实consumer需本包测试及整组/SDK；schema测试不能替代效果或持久恢复。

#### codex-thread-store

以ThreadId为持久handle的存储无关thread/queue接口与local实现。

- 源码：`codex-rs/thread-store/src/lib.rs`、`codex-rs/thread-store/src/store.rs`、`codex-rs/thread-store/src/error.rs`、`codex-rs/thread-store/src/local/mod.rs`、`codex-rs/thread-store/src/queue_store.rs`。
- 技术合同：ThreadStoreResult使用ThreadNotFound、InvalidRequest、Conflict、Unsupported和Internal；backend解析ThreadId到rollout或其他store。Paginated模式按现有Unsupported拒绝，不可悄悄当完整history返回。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-thread-store --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：local/in-memory实现语义与实际断电/跨kernel不可达历史分开；本组合没有全链恢复资格。

#### codex-core-plugins

插件manifest、marketplace、安装状态、remote bundle与工具路由。

- 源码：`codex-rs/core-plugins/src/lib.rs`、`codex-rs/core-plugins/src/manifest.rs`、`codex-rs/core-plugins/src/loader.rs`、`codex-rs/core-plugins/src/manager.rs`、`codex-rs/core-plugins/src/store.rs`、`codex-rs/core-plugins/src/git_policy.rs`。
- 技术合同：LoadedPlugin/PluginLoadOutcome来自原plugin实现；loader/store和Git policy分别约束来源、解析与安装状态。可发现/加载插件不等于用户授权工具效果，remote bundle也不自动成为受信Root。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-core-plugins --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：无包内Markdown；需逐provider/平台审实际安装与失败恢复，本节不授权安装、更新或外部消息。

#### codex-rollout

原session文件的rollout持久记录、压缩、发现与state DB接点。

- 源码：`codex-rs/rollout/src/lib.rs`、`codex-rs/rollout/src/recorder.rs`、`codex-rs/rollout/src/compression.rs`、`codex-rs/rollout/src/reverse_jsonl_scanner.rs`、`codex-rs/rollout/src/state_db.rs`。
- 技术合同：decode_rollout_line保留serde_json解析错误；RolloutLineReader/recorder与state_db保持文件和元数据职责。TEST_FIXTURES要求真实fixture寿命；JSONL存在不证明protected Current或effect terminal。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-rollout --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：需新源真实文件与重启验证；fixture同步修正不自动成为原生产文档/Notes持久化证明。

#### codex-file-system

typed文件操作、受控permission profile转换及有界walk接口。

- 源码：`codex-rs/file-system/src/lib.rs`、`codex-rs/file-system/src/find_up.rs`。
- 技术合同：ReadFileOptions/WriteFileOptions与ExecPermissionProfile保留typed参数和io::Error；walk设MAX_WALK_DEPTH=64、directories=10000、entries=50000、response=4MiB，WalkError与截断结果必须显式处理。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-file-system --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：无包内Markdown；路径访问、远端实现/平台策略与真实设备隔离需各自验证；文件API不能签发Hepta效果授权。

#### codex-rmcp-client

原MCP transport、认证状态和OAuth metadata discovery/登录client。

- 源码：`codex-rs/rmcp-client/src/lib.rs`、`codex-rs/rmcp-client/src/auth_status.rs`、`codex-rs/rmcp-client/src/oauth_client_registration.rs`、`codex-rs/rmcp-client/src/perform_oauth_login.rs`、`codex-rs/rmcp-client/src/http_client_adapter.rs`。
- 技术合同：discover_streamable_http_oauth与OAuthDiscoveryTimeout保留metadata/issuer验证；fallback用无token compatibility initialization并限制body至1MiB，结束自建session后再进入原PKCE/state/resource绑定。metadata失败不静默选资源origin的/register。
- 开发验证：`RUSTUP_TOOLCHAIN=1.95.0 just test --locked --offline -p codex-rmcp-client --test-threads 2 --retries 0 --cargo-profile dev-small`。
- 当前缺口：这是新增第19实际owning包，须本包Rust tests＋原SDK50与新CLI同源证明；已知MCP profile失败/skip保留，不能称全MCP通过。

## 历史收据与当前状态

| 真实来源 | 已保存结果 | 对本组合的限制 |
| --- | --- | --- |
| e7ed内核 | 38正向／7原负向；Core410／410，OSTD235实际通过＋3原soft skips；42-case Unix guest在1／2CPU下通过；源8069前后一致 | 本组合源码纳入了其内核增量，但新整个HEAD／工具路径／ELF仍需新绑定；不是新host或native通过。 |
| cec3／97c host | 原2821＝2817PASS／4TIMEOUT，55旧skip；三60s生命周期＋一180s ledger超时；七产品已构建 | 原失败保留，未重试／放宽预算／判flake；不能说新组合已解决或可交付。 |
| Hepta7673目标 | State＋Root＋SDK原提交来源与全源码组合已核对 | 最终新tuple资格尚未完成；原组件、早期检查与保留native失败不能自动转移为整组通过。 |
| 当前文档 | 逐入口、契约、源码mode/blob、差异和剩余缺口 | 只是文档与源码身份，未产生产品、授权或硬件资格。 |

固定V5保留原draft354／260的全部路径，再对strict182缺失依赖与OOM20变更并集逐路径补39角色，
追加V5地图／oracle／原V4 current archive三角色，得到396；先前Hepta增加Root failure report一角色得到261；本轮再补10个CLI producer依赖，当前固定271。
机器清单逐新增角色记录用途和strict182／delta来源，不接受任意可选shape。V4的18-owner dispatch保持原样，
V5显式增加rmcp-client成为19。历史V4工作流必须手动给完整40位OS commit，并读取该历史checkout自己的匹配manifest／Hepta pin。

## 旧261角色V5的发布工具增量验证

| 模式 | 实际分组 | 原始源HEAD／tree | 实际用例 | 结果 |
| --- | --- | --- | --- | --- |
| normal | legacy | `b6a989148ce68560bb642c009d2c760eacbe6345`／`3f50bc18963340ce11faa74c60334932df11acec` | 54 | exit 0，0skip／0retry，原始完整8088源前后相同 |
| normal | historical-workflows | `b6a989148ce68560bb642c009d2c760eacbe6345`／`3f50bc18963340ce11faa74c60334932df11acec` | 7 | exit 0，0skip／0retry，原始完整8088源前后相同 |
| normal | v5 | `231a22c17192aa68a6488043696c2abda90039e8`／`bbbf08a8c220b2de555ac22973c496739324cb1c` | 24 | exit 0，0skip／0retry，原始完整8088源前后相同 |
| optimized | legacy | `231a22c17192aa68a6488043696c2abda90039e8`／`bbbf08a8c220b2de555ac22973c496739324cb1c` | 54 | exit 0，0skip／0retry，原始完整8088源前后相同 |
| optimized | historical-workflows | `231a22c17192aa68a6488043696c2abda90039e8`／`bbbf08a8c220b2de555ac22973c496739324cb1c` | 7 | exit 0，0skip／0retry，原始完整8088源前后相同 |
| optimized | v5 | `231a22c17192aa68a6488043696c2abda90039e8`／`bbbf08a8c220b2de555ac22973c496739324cb1c` | 24 | exit 0，0skip／0retry，原始完整8088源前后相同 |

这只验证发布工具及其真实临时Git／有界子进程fixture。新完整CI仍为原116加所有V5的互斥union；
旧七项CurrentWorkflowTests执行的是保留历史V4块，新Schema5WorkflowTests实际执行当前V5读取／调度／生产拒绝。
正常54／7来自b6a，正常新24与优化54／7／24来自231；不合成六阶段同源231。原b6a新24中1FAIL／1ERROR保留，优化当时未执行。
原4018两模式各116通过的组件收据不重命名，typed核心与三个旧test源逐字保留。最终source-only manifest及pair收据另绑最终HEAD/tree。

## 真实授权协议缺口

现有参考Model authority只接受 `runtime.codex.turn_start`，destination必须是 `codex-app-server:<positive u64>`，
subject必须是已admit的Fleet peer；参考Secrets authority只接受 `secrets.read`。这两者不能充当Notes／Device
`runtime.agentd.production_operation`签发服务。参考源码也没有证明部署的精确commit。
因此签发provider、protected clock、durable frontier、trusted keyring、revocation head、recovered writer和current-cut
仍是七项未闭合输入。源码／fixture成功不开放生产，未知效果不自动重发；本文不复制敏感配置路径。

OOM原组件的Core420、OSTD235及3原VMX skip、普通产品、SMP1／2各12＋61和Unix原8项／64重复结果
保留在05f自己的来源。新Desktop已纳入其源码，不把这些结果改成最终V5／Hepta组合资格。
Hepta新增Root诊断只是保留首次失败原因的有界标签；旧native失败仍失败，不能以新源码追溯判定未知故障原因。


## 当前CLI producer装配与源码门禁

原Hepta7673完整19-owner实际3088项＝3085 PASS＋3项streamable_http_remote失败；原三项build通过。
真实test support第338行用原cargo-bin resolver启动正常`codex exec-server`，但旧V5 stage4没有构建codex-cli/bin codex。
新stage4在同一正常Cargo命令显式选择agentd＋codex-cli及对应两bin，保持七步、19测试owner、原profile／预算／零重试。
CLI是集成必需的真实产品producer，不是替代fixture、不新增第20测试owner，也不修改Hepta源码。
十个新增明确role覆盖CLI Cargo/build/main/lib/exec-server lifecycle、RMCP Cargo/原三项test/support和Cargo binary resolver Cargo/lib；
因此Hepta固定role数由261变271，OS仍396、golden仍5对。具体开发命令与技术路径见release README的Required CLI producer节。

旧source-only V5快照f4cd及其原261 map／60b7清单／原工具／收据保持原来源：必须用f4cd原工具按原pins验证。
新current固定271不接受旧261降级，也不声称新工具兼容旧V5；V1–4原路线／argv／map字节不变。
原3088三失败保持失败；单独构建CLI或独立三项转阳都不能替代最终完整七步／19-owner资格。

| 原682模式 | 分组 | 实际源HEAD／tree | 实际项数 | 结果 |
| --- | --- | --- | --- | --- |
| normal | legacy | `682d66ed563434064e9ce5e0afcd173a76091117`／`27abb11ac649efdb752022429f81bf3374462185` | 54 | exit 0，0skip／0retry，完整8088源前后相同 |
| normal | historical-workflows | `682d66ed563434064e9ce5e0afcd173a76091117`／`27abb11ac649efdb752022429f81bf3374462185` | 7 | exit 0，0skip／0retry，完整8088源前后相同 |
| normal | v5 | `682d66ed563434064e9ce5e0afcd173a76091117`／`27abb11ac649efdb752022429f81bf3374462185` | 24 | exit 0，0skip／0retry，完整8088源前后相同 |
| optimized | legacy | `682d66ed563434064e9ce5e0afcd173a76091117`／`27abb11ac649efdb752022429f81bf3374462185` | 54 | exit 0，0skip／0retry，完整8088源前后相同 |
| optimized | historical-workflows | `682d66ed563434064e9ce5e0afcd173a76091117`／`27abb11ac649efdb752022429f81bf3374462185` | 7 | exit 0，0skip／0retry，完整8088源前后相同 |
| optimized | v5 | `682d66ed563434064e9ce5e0afcd173a76091117`／`27abb11ac649efdb752022429f81bf3374462185` | 24 | exit 0，0skip／0retry，完整8088源前后相同 |

这些是发布工具实际临时Git／有界child验证；原4018 typed组件与早期mixed QA保留原身份。当前文档不执行Rust／GUI／native，七项生产输入继续关闭。最终source-only清单和外置收据另绑文档successor实际HEAD/tree。


## 当前XKB CI依赖修复、环境失败与源码边界

8b825在`a10-host.yml`的一处和`organ-current-pair.yml`的V5／历史V4两处apt列表
加入`libxkbcommon-x11-dev`，保留`libxkbcommon-dev`；[RUN](../../support/ui/RUN.md)同步X11 counterpart和Ubuntu包名。
这是两个workflow／三个安装列表的源码修复，尚未安装依赖或重新运行CI。固定396／271角色、5对golden、19 owners和stage4正常CLI producer均未改。

冻结6487／7673的原七步attempt01真实停在首步UI build：Rust1.88的原locked／offline命令因缺
`ab_glyph 0.2.32` archive而Cargo exit101，wrapper exit1。阶段2–7未执行，新测试0项、保留产品0个，SDK／GUI／native未启动，完整源码前后相同。
独立审计SHA256：`1a4a2ed45adaa503727e43d7a274209d8376f29b22f9c0889375e0eece0f009e`。

独立cache repair attempt01也真实exit1：报告已完成43次archive发布，第44项`icu_properties_data 2.3.0`
下载保留后，向已消失的默认Cargo cache目录发布时FileNotFoundError。目录消失原因未知，保留字节的checksum不证明发布或离线解析通过。
其独立binding SHA256：`b2f23e8f3533d95f41115ce303c4f585b2d76a035ea2600a10ab310cff46d78c`。
两次失败保持原身份，不能改写成新组合七步通过。后续private cache须先按原flags实际解析UI含dev图、Hepta正常producer图和exact19 owner图；本文不预填其结果。

| 8b825实际模式 | legacy原案例 | 历史Workflow原案例 | V5原案例 | 边界 |
| --- | --- | --- | --- | --- |
| normal | 54，exit0 | 7，exit0 | 24，exit0 | 每lane600s／0skip／0retry，完整8088源前后相同 |
| optimized | 54，exit0 | 7，exit0 | 24，exit0 | 每lane600s／0skip／0retry，原case IDs严格相同 |

本轮Python completion SHA256：`76c46b6498a0a4de14a92f897c08a99b8ad17d70b0f024b8d3e62ccde6b2e33b`。这是原发布工具的临时Git／有界child实际验证，
不是全140项／mode的完整CI union，也不是文档successor的Rust／GUI／native／生产资格。
新source-only typed清单和最终HEAD/tree收据由后续步骤绑定；完整七步、Notes真实授权／持久化／恢复及GUI／native仍分别验收。
七项生产装配输入继续关闭，不引入新的生产authority。历史2026-10-26审计、旧README结果与失败均保留。
