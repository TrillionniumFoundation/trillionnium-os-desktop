# 模块文档覆盖审计（2026-10-22）

2026-10-23 补充：[57 个内核 workspace crate 手册](../modules/kernel-workspace/README.md) 已按 `10dae5ea4ae5c2f81e2e530b1eb74bd41a5c29cd` 逐包补充职责/API、owner、开发入口和具体未验证项，并附 manifest/源码 hash 清单。新手册是文档覆盖补齐，不转授运行资格；以下历史审计的源码、统计和结论保持其原时点。

原始清点实际观察的是本地提交 `b2b3e862bf568dab39bd8331be7def145f770408`，tree `7389c0a3f982983087953f75de7042fc058be088`。公开等价提交为 [`85d394f99c73ad3194d57c876712ac01b59d90ca`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/85d394f99c73ad3194d57c876712ac01b59d90ca)；发布时已核对 GitHub commit 元数据，两者具有相同 tree。两种提交身份见 [published-equivalence.json](../../results/integration/2026-10-22-module-docs/published-equivalence.json)，原始输入哈希与审计记录继续保留本地观察身份。复核应使用公开提交，本审计快照不升级到后来的 #240 合并提交。源码及机器清单中的路径相对仓库根；本次导航修正及其文件检查单独记录，不改变原运行证据的来源身份。

**结论：A00–A10 都有可定位的技术内容与开发／验证入口；不能据此说每个实际 crate 都有独立、完整的开发手册和技术手册。** UI 与不少内核 crate 使用共享手册、上游书籍及源码 API 注释。文档文件、脚本和 workflow 存在，不等于对应实现已经可运行或通过验收。

冻结清点只读核对源码路径、文档内容、入口与本地链接；本次文档交付仅修正导航与历史范围说明，没有执行模块测试、构建、Runtime 或设备操作。后续远端 B/D/整合运行不在这个冻结快照的清点范围内。

## 1. A00–A10 交付领域矩阵

表中路径均已实际检查存在；实现边界描述的是上述冻结源码。技术与开发内容可以合写在同一文件；不以文件名必须为 TECHNICAL/DEVELOPMENT 判定。后续运行和发布资格查阅现行 [STATUS](../STATUS.md)。

| 模块与实际代码 | 技术设计入口 | 开发／运行与验证入口 | 实现及证据边界 |
| --- | --- | --- | --- |
| **A00 集成与跨仓发布组合**：`.github/workflows`, `support/release` | [ARCHITECTURE.md](../ARCHITECTURE.md)；[DECISIONS.md](../DECISIONS.md)；[ORGAN_RELEASE_PROFILE.md](ORGAN_RELEASE_PROFILE.md) | [PLAN.md](PLAN.md)；[ORGAN_RELEASE_PROFILE.md](ORGAN_RELEASE_PROFILE.md)；验证：[VALIDATION.md](../VALIDATION.md)；[test_organ_release_profile.py](../../support/release/test_organ_release_profile.py) | source profile 固定源码与祖先关系；生产 grant、原 owner 运行和 native G2 需独立验收。 |
| **A01 上游源码、构建与启动**：`kernel/asterinas`, `support/build` | [ARCHITECTURE.md](../ARCHITECTURE.md)；[README.md](../../support/build/README.md) | [README.md](../../support/build/README.md)；[README.md](../../support/build/ktest/README.md)；验证：[verify-source.py](../../support/build/verify-source.py)；[run.py](../../support/build/ktest/run.py) | 有真实构建/guest 入口；E/F 原收据各绑定不同 source，不能相加为本树运行。 |
| **A02 HOS2 wire codec**：`libs/os-abi/src/lib.rs`, `tests/abi` | [NATIVE_ABI.md](../NATIVE_ABI.md) | [A02_REVIEW_CLOSURE_2026-10-17.md](../../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md)；验证：[run_acceptance.py](../../tests/abi/run_acceptance.py)；[a02-pinned-host-acceptance.yml](../../.github/workflows/a02-pinned-host-acceptance.yml) | codec、golden、host mutation 资格与内核操作开放不同。 |
| **A03 控制核心、投递与退役模型**：`libs/os-control`, `tests/control` | [API_CONTRACT.md](../../libs/os-control/API_CONTRACT.md) | [VALIDATION.md](../../tests/control/VALIDATION.md)；[VALIDATION.md](../../tests/control/backend_no_std/VALIDATION.md)；验证：[run-validation.sh](../../tests/control/run-validation.sh)；[a03-native-models.yml](../../.github/workflows/a03-native-models.yml) | 真实 host/Loom/no_std 检查不等于 kernel IRQ/SMP 或 Hepta fsync 资格。 |
| **A04 Linux ABI、ELF、rootfs 与存储**：`compat/linux`, `support/rootfs` | [LINUX_COMPATIBILITY.md](../LINUX_COMPATIBILITY.md)；[GAPS.md](../../compat/linux/GAPS.md) | [A04_LINUX_HEPTA_ELF.md](handoffs/A04_LINUX_HEPTA_ELF.md)；[README.md](../../support/rootfs/README.md)；[SQLITE_GUEST_RESTART.md](../../tests/workloads/linux/SQLITE_GUEST_RESTART.md)；验证：[FULL_UBUNTU_PROFILE.md](../../tests/workloads/linux/FULL_UBUNTU_PROFILE.md)；[run_sqlite_restart_guest.py](../../tests/workloads/linux/run_sqlite_restart_guest.py) | F 已有固定 ext2 filetype/SQLite guest restart 收据；不是原 Agentd/UI 已在 Asterinas 运行。 |
| **A05 内核控制与 Process 映像**：`kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs`, `kernel/asterinas/kernel/core/src/process` | [NATIVE_ABI.md](../NATIVE_ABI.md)；[ASTERINAS_PROCESS_IMAGE_G1C.md](../ASTERINAS_PROCESS_IMAGE_G1C.md)；[G1D_TRUSTED_CONTROL_PROFILE.md](G1D_TRUSTED_CONTROL_PROFILE.md) | [A05_KERNEL_CONTROL.md](handoffs/A05_KERNEL_CONTROL.md)；[PROCESS_IMAGE_G1C.md](../../tests/kernel/control/PROCESS_IMAGE_G1C.md)；[README.md](../../tests/kernel/control/README.md)；验证：[run_g1d_guest.py](../../tests/kernel/control/run_g1d_guest.py)；[g1d-trusted-control.yml](../../.github/workflows/g1d-trusted-control.yml) | ordinary QueryAbi、G1-c ReadUsage、G1-d 固定三角色五操作必须按 profile 区分。 |
| **A06 CPU owner、计费、隔离与有限恢复**：`kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs`, `tests/organ_backend` | [ASTERINAS_CPU_OWNER_G1A.md](../ASTERINAS_CPU_OWNER_G1A.md)；[ASTERINAS_CPU_USAGE_G1B.md](../ASTERINAS_CPU_USAGE_G1B.md)；[SECURITY_AND_RECOVERY.md](../SECURITY_AND_RECOVERY.md) | [CPU_USAGE_G1B.md](../../tests/organ_backend/CPU_USAGE_G1B.md)；[G1D_WORKLOAD_ISOLATION.md](../../tests/kernel/control/G1D_WORKLOAD_ISOLATION.md)；[G1D_BOUNDED_RECOVERY.md](../../tests/kernel/control/G1D_BOUNDED_RECOVERY.md)；验证：[CPU_CLOCK_HANDOFF_CI.md](../../tests/organ_backend/CPU_CLOCK_HANDOFF_CI.md)；[a06-kernel.yml](../../.github/workflows/a06-kernel.yml) | E 有 core266/三 boot/旧 root 负控；不含完整 watchdog、可信暂停原因或总进程树内存保证。 |
| **A07 Hepta observer、Objective、history、CPU adapter**：`services/hepta-os` | [CONTRACT.md](../../services/hepta-os/CONTRACT.md)；[OBJECTIVE_TRANSPORT.md](../../services/hepta-os/OBJECTIVE_TRANSPORT.md)；[OBJECTIVE_HISTORY.md](../../services/hepta-os/OBJECTIVE_HISTORY.md)；[CPU_DELIVERY.md](../../services/hepta-os/CPU_DELIVERY.md) | [README.md](../../services/hepta-os/README.md)；[RUN.md](../../services/hepta-os/RUN.md)；验证：[ORIGINAL_OBJECTIVE.md](../../tests/integration/hepta/ORIGINAL_OBJECTIVE.md)；[OBJECTIVE_HISTORY_PROBE.md](../../tests/integration/hepta/OBJECTIVE_HISTORY_PROBE.md) | 多个功能有分开的来源合同；cpu-history 是一次只读 QueryDelivery，不分配 D、不退役。 |
| **A08 Android 兼容与产品输入**：`compat/android`, `support/android` | [ANDROID_COMPATIBILITY.md](../ANDROID_COMPATIBILITY.md)；[INTERFACES.md](../../compat/android/INTERFACES.md) | [README.md](../../support/android/README.md)；验证：[verify_source_integrity.py](../../support/android/verify_source_integrity.py)；[a08-host.yml](../../.github/workflows/a08-host.yml) | host 源码/输入校验不证明 Binder/ART/APK、Asterinas Android 或手机；具体 ARM BSP 未形成。 |
| **A09 硬件、驱动接合与 VMM**：`support/hardware`, `support/vmm` | [HARDWARE_AND_DRIVERS.md](../HARDWARE_AND_DRIVERS.md)；[DECISION.md](../../support/hardware/DECISION.md)；[GATES.md](../../support/vmm/GATES.md)；[PROVENANCE.md](../../support/vmm/PROVENANCE.md) | [RUN.md](../../tests/hardware/RUN.md)；[README.md](../../support/vmm/device_lifecycle/README.md)；验证：[a09-hardware.yml](../../.github/workflows/a09-hardware.yml)；[acceptance.py](../../support/vmm/acceptance.py) | G 只有只读 inventory；Rust lifecycle 是模型，不实施 DMA pin、IOMMU、IRQ 或设备 reset。 |
| **A10 Rust UI 与 Linux Notes organ**：`ui/core`, `ui/session` | [DESKTOP_UX.md](../DESKTOP_UX.md)；[INTEGRATION_CONTRACTS.md](../../support/ui/INTEGRATION_CONTRACTS.md)；[CHAT_WORKSPACE.md](../../support/ui/CHAT_WORKSPACE.md)；[NOTES_ORGAN.md](../../support/ui/NOTES_ORGAN.md) | [RUN.md](../../support/ui/RUN.md)；[HEPTA_OBSERVER.md](../../support/ui/HEPTA_OBSERVER.md)；[NOTES_ORGAN.md](../../support/ui/NOTES_ORGAN.md)；验证：[TESTPLAN.md](../../tests/ui/TESTPLAN.md)；[check-host.sh](../../tests/ui/check-host.sh) | 最终 C 固定来源有 Linux host/Notes/Weston 证据；不是 Asterinas 桌面、通用桌面控制或手机。 |

文件系统跨 A04/A05 的新增专题另有 [docs/INODE_PERMISSION_TRANSACTIONS.md](../INODE_PERMISSION_TRANSACTIONS.md)、[docs/EXFAT_PERMISSION_MODE.md](../EXFAT_PERMISSION_MODE.md)、[tests/workloads/linux/PERMISSIONS.md](../../tests/workloads/linux/PERMISSIONS.md) 和 [tests/workloads/linux/SQLITE_GUEST_RESTART.md](../../tests/workloads/linux/SQLITE_GUEST_RESTART.md)。冻结源码的 INDEX 未直接链接两份技术设计；本次已补上 [INDEX 专题导航](../INDEX.md)。原问题是导航缺口，文件原已存在。

## 2. 实际 package 与 workspace 清单

已排除 `results/**` 和任意 `/evidence/**` 的历史源码副本，避免把归档的 Hepta upstream seed 当作当前 workspace。

| 冻结源码中的非上游 Cargo 入口 | 目录 Markdown | 具体开发／技术内容所在位置 |
| --- | --- | --- |
| `libs/os-abi/Cargo.toml` — hos2-os-abi | **无** | [docs/NATIVE_ABI.md](../NATIVE_ABI.md)；[tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md](../../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md) |
| `libs/os-control/Cargo.toml` — os-control | `API_CONTRACT.md` | [libs/os-control/API_CONTRACT.md](../../libs/os-control/API_CONTRACT.md)；[tests/control/VALIDATION.md](../../tests/control/VALIDATION.md) |
| `services/hepta-os/Cargo.toml` — hepta-os-observer | `CONTRACT.md`；`CPU_DELIVERY.md`；`OBJECTIVE_HISTORY.md`；`OBJECTIVE_TRANSPORT.md`；`README.md`；`RUN.md` | [services/hepta-os/README.md](../../services/hepta-os/README.md)；[services/hepta-os/RUN.md](../../services/hepta-os/RUN.md) |
| `support/ui/Cargo.toml` — trill-ui-boundary | `BOUNDARIES.md`；`CHAT_WORKSPACE.md`；`CJK_RENDERING.md`；`HEPTA_OBSERVER.md`；`INTEGRATION_CONTRACTS.md`；`NOTES_ORGAN.md`；`ORIGINAL_HEPTA_SHELL.md`；`RUN.md`；`X11_IME.md` | [support/ui/BOUNDARIES.md](../../support/ui/BOUNDARIES.md)；[support/ui/INTEGRATION_CONTRACTS.md](../../support/ui/INTEGRATION_CONTRACTS.md) |
| `support/vmm/device_lifecycle/Cargo.toml` — a09-device-lifecycle | `README.md` | [support/vmm/device_lifecycle/README.md](../../support/vmm/device_lifecycle/README.md)；[support/vmm/GATES.md](../../support/vmm/GATES.md) |
| `tests/control/backend_no_std/Cargo.toml` — os-control-backend-no-std | `VALIDATION.md` | [tests/control/backend_no_std/VALIDATION.md](../../tests/control/backend_no_std/VALIDATION.md)；[tests/control/VALIDATION.md](../../tests/control/VALIDATION.md) |
| `tests/control/loom/Cargo.toml` — os-control-loom | **无** | [tests/control/VALIDATION.md](../../tests/control/VALIDATION.md) |
| `tests/ui/Cargo.toml` — trillionnium-ui-contracts | `ORIGINAL_OBJECTIVE_SHELL.md`；`TESTPLAN.md` | [tests/ui/TESTPLAN.md](../../tests/ui/TESTPLAN.md)；[support/ui/RUN.md](../../support/ui/RUN.md) |
| `tests/workloads/linux/rust/Cargo.toml` — a04-tokio-workload | **无** | [tests/workloads/linux/README.md](../../tests/workloads/linux/README.md)；[support/rootfs/README.md](../../support/rootfs/README.md) |
| `ui/Cargo.toml` — virtual workspace | **无** | [support/ui/RUN.md](../../support/ui/RUN.md)；[support/ui/CHAT_WORKSPACE.md](../../support/ui/CHAT_WORKSPACE.md) |
| `ui/app-window/Cargo.toml` — trill-app-window | **无** | [support/ui/NOTES_ORGAN.md](../../support/ui/NOTES_ORGAN.md)；[support/ui/RUN.md](../../support/ui/RUN.md) |
| `ui/broker/Cargo.toml` — trill-ui-broker | **无** | [support/ui/NOTES_ORGAN.md](../../support/ui/NOTES_ORGAN.md)；[support/ui/RUN.md](../../support/ui/RUN.md) |
| `ui/core/Cargo.toml` — trill-ui-core | **无** | [support/ui/CHAT_WORKSPACE.md](../../support/ui/CHAT_WORKSPACE.md)；[support/ui/NOTES_ORGAN.md](../../support/ui/NOTES_ORGAN.md) |
| `ui/session/Cargo.toml` — trill-session | **无** | [support/ui/HEPTA_OBSERVER.md](../../support/ui/HEPTA_OBSERVER.md)；[support/ui/NOTES_ORGAN.md](../../support/ui/NOTES_ORGAN.md) |
| `ui/shell/Cargo.toml` — trill-shell | `OBSERVATION_FRESHNESS.md` | [ui/shell/OBSERVATION_FRESHNESS.md](../../ui/shell/OBSERVATION_FRESHNESS.md)；[support/ui/CHAT_WORKSPACE.md](../../support/ui/CHAT_WORKSPACE.md) |

实际 UI workspace 有 **5** 个成员：`core`、`session`、`shell`、`app-window`、`broker`。5 个 crate 均没有独立 README；`ui/shell/OBSERVATION_FRESHNESS.md` 是已有专项技术文档，不能忽略。其余角色、状态归属和运行命令集中在 `support/ui`，尤其 Notes 手册已逐项列出 core/broker/session/app-window/shell 的职责。

Asterinas 主内核 workspace 有 **57** 个显式成员，其中 **11** 个有 crate 同目录 Markdown，**46** 个没有；**48** 个入口源文件有 crate 级说明或 include README。这是文件分布统计，不是质量百分比，也不表示剩余 crate 没有任何 API 注释。完整逐 crate 结果见 `cargo-inventory.csv` / `cargo-inventory.json`。

上游共享资料包括 [Book 目录](../../kernel/asterinas/book/src/SUMMARY.md)、[Framekernel 架构](../../kernel/asterinas/book/src/kernel/the-framekernel-architecture.md)、[代码组织](../../kernel/asterinas/book/src/to-contribute/code-organization.md)、[OSDK 使用](../../kernel/asterinas/osdk/README.md) 和项目的 build/ktest 手册。这些资料有实际内容，但不能代替每个驱动的本项目硬件、故障恢复与验收手册。`kernel/asterinas/kernel/comps/README.md` 只有一个标题（31 字节）。

机器清单共记录 **127** 份非归档 Cargo manifest，含上游测试/fixture、工具和虚拟 workspace；它们不是 127 个独立产品模块。非上游部分为 10 个产品/支持 package、1 个 UI virtual workspace 和4个测试 package。

## 3. 冻结源码中的缺口与本次文档修正

下列位置及行号来自上述冻结源码。机器清单保留原检查事实；最后一列区分本次已经完成的导航修正与仍存在的模块专属文档缺口。

| 位置 | 冻结源码中的实际问题 | 本次处理与剩余缺口 |
| --- | --- | --- |
| `libs/os-abi/`；`ui/{core,session,shell,app-window,broker}/` | 没有各自独立完整开发/技术手册；但共享 ABI/UI 文档存在 | 可增加指向现有实质手册的模块入口，并补真实特有内容。不要复制空模板凑数。 |
| `kernel/asterinas/kernel/comps/README.md`；kernel workspace 清单中46个无同目录 Markdown 的 crate | 高层组件入口只是标题，底层文档主要依赖共享 book 与源码注释 | 先为要实际接合的 GPU/IRQ/IOMMU/输入/存储设备补具体 owner、锁、构建目标、硬件、失败与测试契约；不宣称所有 crate 已有双手册。 |
| `docs/INDEX.md` | 未直接链接已存在的 `docs/INODE_PERMISSION_TRANSACTIONS.md` 与 `docs/EXFAT_PERMISSION_MODE.md` | 本次已在 INDEX 补权限事务、ExFAT 与权限回放入口；不新增实现资格。 |
| `support/build/README.md:76,90,167,203` | core141、only G1-a derivative、A01 交接和全未测句仍是早期范围 | 已应用三文件修正中的 dated reading note，链接当前 STATUS 与固定 E/F 收据；原文保留。 |
| `support/ui/BOUNDARIES.md:51` | Hepta is unconnected 是早期原型表述，未反映 opt-in observer 与 private bootstrap | 已增加 observer/private bootstrap 接合范围、固定 C 收据及生产授权边界；原历史句保留。 |
| `tests/hardware/RUN.md:16,72` | latest87/no GPU/scorecard 是10-16容器观察；新 inventory 导航不显著 | 已在顶部链接10-21 DECISION/inventory；旧容器事实保留，不授予 compute/reset 资格。 |
| `docs/VALIDATION.md:84,88,93,98` | 当前 #147 待决和 V201/V206/V211 待做表是早期检查点 | 已增加历史范围说明并链接 NATIVE_ABI、Process、CPU、G1-d profile 与 STATUS；旧表格和结果保留。 |
| `services/hepta-os/README.md`、`services/hepta-os/RUN.md` | 未链接 `CPU_DELIVERY.md`；README 的 Device control/HOS2 not provided 一行未区分默认接口和新增只读 cpu-history | 已在 README/RUN 增加 CPU_DELIVERY 导航，并明确默认不启用设备控制、可选只读 QueryDelivery 和普通 Session 边界；CPU 专册、source pin 和测试原已存在。 |
| `tests/{golden,spec}/`、`tests/control/loom/`、`tests/workloads/{linux/rust,android}/` | 没有各目录独立 README；技术/执行说明集中在共享验证、control、Linux、Android 手册 | 标为共享覆盖，而不是完全无文档。需要新开发者入口时补链接和该测试层级的独有维护信息。 |
| `support/release/` / `.github/workflows/` | 发布工具有实质手册和19项测试；冻结 HEAD 尚无专用 release gate | 此条记录冻结源码中的状态。专用 workflow 的后续纳入及其执行结果应另记，不能回填到本清点或当作生产发布资格。 |

## 4. 有文档与可运行实现分开

- 生产 grant/provider、原 writer、K↔D 持久闭环：已有规范和接缝，不能用 source-only 工具或 transport 测试宣称 G2 完成。
- `RevokeGrant/ApplyRecovery`、完整 watchdog、总进程树内存：安全契约已写出；E 的有限恢复只证明自己的固定子集。
- 原 Agentd/app-server 与 UI 迁入 Asterinas：A04/F 有实际 ABI/rootfs/SQLite 入口；真实全栈原生部署仍需按实际依赖与 ELF 输入实现。
- GPU/IOMMU/VMM/ARM BSP/手机：设计、inventory 和 host gate 文档存在；具体设备运行、撤销、静止、复位、重启手册与资格尚依赖未完成的实现和目标选择。

这些属于实现及验收缺口，不应靠补一份文档改记为完成。后续状态与来源以 [docs/STATUS.md](../STATUS.md) 顶节及其固定 C/E/F/G 收据为准；本清点未重跑那些结果。

## 5. 检查范围与交付文件

原冻结清点与本次文档交付的检查分开记录：

- **冻结清点：** 124 份非归档手册及 Book 目录、894 个本地文件链接目标均存在；431 个外链未访问，通用锚点未验证。复用仓内纯链接解析 helper，没有执行历史 publication gate。
- **冻结清单：** canonical workflow 共 12 份；文件存在不表示该 HEAD 的 CI 已通过。后续增加的 workflow 不计入此历史数量。
- **本次交付：** 增补导航和历史范围说明，对新增／修改文档的本地链接及 diff 格式重新检查；不重跑模块测试、构建、Runtime 或设备操作。结果见 [delivery-check.json](../../results/integration/2026-10-22-module-docs/delivery-check.json)。

| 交付文件 | 内容与范围 |
| --- | --- |
| [证据包 README](../../results/integration/2026-10-22-module-docs/README.md) | 冻结来源、相对路径规则和 Git 对象复核命令 |
| [module-matrix.json](../../results/integration/2026-10-22-module-docs/module-matrix.json) | 11 个交付领域、源码路径、技术／开发／验证入口及当时边界 |
| [cargo-inventory.json](../../results/integration/2026-10-22-module-docs/cargo-inventory.json) / [CSV](../../results/integration/2026-10-22-module-docs/cargo-inventory.csv) | 127 份非归档 manifest 的逐项清单，可筛选 kernel 成员和旁置文档 |
| [link-check.json](../../results/integration/2026-10-22-module-docs/link-check.json) | 冻结源码本地链接检查明细及未检查范围 |
| [source-inputs.json](../../results/integration/2026-10-22-module-docs/source-inputs.json) | 277 个冻结输入的字节数和 SHA-256；应对照记录的 Git 提交复核 |
| [audit-validation.json](../../results/integration/2026-10-22-module-docs/audit-validation.json) | 原只读清点检查结果 |
| [doc-corrections.patch.gz](../../results/integration/2026-10-22-module-docs/doc-corrections.patch.gz) / [manifest](../../results/integration/2026-10-22-module-docs/doc-corrections-manifest.json) | 三份历史范围指引的原始补丁（无损 gzip）和准备阶段校验；本次已应用，原正文保持不变 |

2026-10-23：根 [README.md](../../README.md) 已加入项目与模块导航，`verify-source.py` 保留全部 118 项上游输入核验，移除了与上游完整性无关的空 README 限制。详细阅读入口为 [docs/INDEX.md](../INDEX.md) 和 [当前能力表](../CURRENT_CAPABILITIES.md)；本表中的无同目录手册统计仍只绑定10-22冻结源码，后续七份UI/ABI入口不回填该清单。本次没有为缺少独立手册的 crate 生成空模板，也没有把文档存在记成产品完成。
