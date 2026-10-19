# Hepta 全仓依赖安全债务诊断（2026-10-19）

## 结论与证据边界

`d32e795f0d24df89fc57745f6fae70fbd0642eba` 的完整仓库 CI 已真实进入各平台构建与测试，`cargo-deny / cargo-deny` 任务失败。此次超时配置修复没有修改依赖清单、Cargo.lock 或 deny 策略；它按现有规则选择了 `full_repo=true`。不能把旧 `2be5fc05` 的超时结果当作这个新头的结果，也不能把 `rust-ci / CI results (required)` 成功当作仓库要求的 `CI required` 成功。

原始远端失败任务是 [117846024659](https://github.com/TrillionniumFoundation/hepta-private-ci/actions/runs/39185139893/job/117846024659)，在 2026-10-19 01:24:19–01:25:43 UTC 执行，失败步骤为 `Run cargo-deny`。本代理两次日志读取都返回 `Transport closed`；直接日志 URL 被 connector 的 URL allowlist 拒绝。根代理另报告独立读取也失败。这里没有恢复原任务日志，不能声称远端恰好报了下面相同的 13 条错误，也不能证明原日志过大就是传输错误原因。

为定位可修复范围，已按授权在隔离目录进行一次新的本地诊断。固定 action `82eb9f621fbc699dd0918f3ea06864c14cc84246` 的 Dockerfile 指定 **cargo-deny 0.19.0**；action 输入使用 **Rust 1.95.0、`--all-features check`**。本诊断采用官方校验和验证过的同版 cargo-deny musl 二进制、隔离安装的 Rust 1.95.0 GNU 主机工具链，并额外使用 `--locked`。Alpine 容器、执行时间与远端数据状态没有被完全重建，因此本机结果单独标识。

本机 `cargo metadata --locked --all-features` 在 01:36:39 UTC 完成并返回 0，解析 1,517 个包；随后 cargo-deny 在 01:36:52 UTC 返回 1：**advisories FAILED，bans、licenses、sources 均为 ok**。共有 **13 条 error、85 条 warning**。源码、Cargo.lock 与 policy 在每条命令前后完全相同，没有产品编译、依赖更新、ignore/allowlist 调整、CI 重跑或远端写入。

本地等价提交为 `1b0fedb8c2b510106848f6feaf530c9b3698399d`，与远端新头的 tree 均为 `a3e718280a7e17b8c4a226a0232bf18c23fd3586`。Cargo.lock SHA256 是 `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389`，deny.toml SHA256 是 `3713c011667dcbeda9edf1b2644a813f2b5253ebb7b2f3e98ea60aab69407352`，两者都与 `f8c9419d` 基线相同。原始收据见 [execution.json](execution.json)、[local-source-comparison.json](../local-source-comparison.json)。

## 全部 13 条拒绝

RustSec 数据库实际读取提交为 `999ec89d5d3f10f20be14750ec8c2d8b44e0ac9b`，tree 为 `7fab15e592b35835decefbb43f6578c70565e4d9`。13 条官方网页已逐条读取，固定数据库原文也保存在 `official-advisories/`；完整结构化字段、源码 SHA 与公告链接见 [error-summary.json](error-summary.json)。

| 包与锁定版本 | 官方条目 | 类型 | 官方修复范围 | 本仓库主要依赖入口 |
|---|---|---|---|---|
| anymap2 0.13.0 | [2026-0319](https://rustsec.org/advisories/RUSTSEC-2026-0319.html) | 停止维护 | 没有已修补版本；建议 anymap3 | matrix-sdk → hepta-matrix-sdk / hepta-matrixd |
| matrix-sdk-crypto 0.18.0 | [2026-0318](https://rustsec.org/advisories/RUSTSEC-2026-0318.html) | 漏洞 | >=0.19.0 | matrix-sdk-base / sqlite → Matrix 模块 |
| rustls 0.23.45 | [2026-0346](https://rustsec.org/advisories/RUSTSEC-2026-0346.html) | 漏洞 | >=0.23.46 | HTTP、WebSocket、代理、SQLx、Matrix 等 |
| rustls 0.23.45 | [2026-0347](https://rustsec.org/advisories/RUSTSEC-2026-0347.html) | 漏洞 | >=0.23.46 | 同上 |
| rustls 0.23.45 | [2026-0348](https://rustsec.org/advisories/RUSTSEC-2026-0348.html) | 漏洞 | >=0.23.46 | 同上；此条另要求 brotli 配置 |
| rustls 0.23.45 | [2026-0349](https://rustsec.org/advisories/RUSTSEC-2026-0349.html) | 漏洞 | >=0.23.46 | 同上；实际影响另取决于会话与服务器行为 |
| unsafe-libyaml 0.2.11 | [2024-0449](https://rustsec.org/advisories/RUSTSEC-2024-0449.html) | 停止维护 | 没有已修补版本；应迁移解析器 | serde_yaml → core-plugins、skills、external-agent-migration、ext/skills |
| zbus_names 3.0.0 | [2026-0371](https://rustsec.org/advisories/RUSTSEC-2026-0371.html) | 停止维护 | 独立包无修补版本；功能迁入 zbus 6 | keyring → secret-service → zbus |
| zip 2.4.2 | [2026-0367](https://rustsec.org/advisories/RUSTSEC-2026-0367.html) | 漏洞 | >=9.0.0 | core-plugins 的 curated archive 提取 |
| zip 2.4.2 | [2026-0368](https://rustsec.org/advisories/RUSTSEC-2026-0368.html) | 漏洞 | >=9.0.0 | 同上 |
| zip 2.4.2 | [2026-0369](https://rustsec.org/advisories/RUSTSEC-2026-0369.html) | 漏洞 | >=9.0.0 | 同上 |
| zvariant 4.2.0 | [2026-0370](https://rustsec.org/advisories/RUSTSEC-2026-0370.html) | 停止维护 | 独立包无修补版本；功能迁入 zbus 6 | keyring → secret-service → zbus |
| zvariant_derive 4.2.0 | [2026-0372](https://rustsec.org/advisories/RUSTSEC-2026-0372.html) | 停止维护 | 独立包无修补版本；功能迁入 zbus 6 | zvariant 的过程宏依赖 |

上述是 8 个包的 8 条漏洞记录和 5 条停止维护记录。停止维护记录不等于已经发现可利用漏洞。数据库 TOML 的 `date` 是报告日期，不应直接当作数据库新增日期。例如 `unsafe-libyaml` 的报告日期为 2024-03-25，但官方网页 `Issued` 为 **2026-10-12**；ZIP 与 zbus 系列网页的 `Issued` 为 **2026-10-17**。本次未取得原失败 job 使用的数据库 SHA，不能据此确定其全部实际拒绝项或第一次失败时间。

## Agentd 的实际依赖图边界

已额外执行两条不联网、不编译的锁定图查询：`cargo tree --locked --offline -p codex-hepta-agentd --no-default-features --edges normal --target <target>`，分别使用 `x86_64-unknown-linux-gnu` 与 `aarch64-unknown-linux-gnu`。两条命令均返回 0，源前后不变，根包输出 `features=[]`。命令、原输出 SHA、路径与 features 位于 [agentd-graph-execution.json](agentd-graph-execution.json) 和 [agentd-reachability.json](agentd-reachability.json)。

| 锁定包 | 两个 Linux 目标的 Agentd normal 图 | 结论范围 |
|---|---|---|
| anymap2、matrix-sdk-crypto | 未出现 | 仍在完整仓库的 Matrix 模块图内；不能称整个项目不受影响 |
| rustls | 出现 | 所列 features 没有 brotli；本配置不满足 0348 的该 feature 前提；其他三条的实际 API / 会话条件未建立 |
| zip、unsafe-libyaml、zbus_names、zvariant | 出现 | 静态 normal 依赖可达，不代表指定运行场景调用了相关 API |
| zvariant_derive | 出现，且标为 proc-macro | 过程宏编译依赖，不等于产品运行时加载或可利用 |

例如图中有 `Agentd → app-server → axum → tokio-tungstenite → rustls`，以及 `Agentd → app-server → agent-extension → core → core-plugins → zip`。这里的路径是 Cargo 输出中观察到的路径，不宣称列出的每条路径是所有可能路径中的全局最短路径。

这不是对原五个 ELF 的重新检查，也不是动态调用跟踪。先前 15 个 Objective History 场景没有在本诊断中重跑；**不能凭 all-features 的全仓拒绝，声称这些场景已证实可利用，也不能把图中未出现某包扩大为完整运行环境不存在该依赖**。

## 升级组合：哪些可以小改，哪些需要迁移

当前没有已证明可用、仅改 Cargo.lock 就能关闭全部 13 项的组合。以下是按实际源码与官方 registry / 发布源形成的实施顺序；尚未更改清单、生成新锁或验证升级后的编译结果。

### 1. rustls：最先处理兼容 patch 升级

官方 registry 中存在未撤回的 `0.23.46`，MSRV 仍为 1.71；当前 workspace 约束为 `0.23`。可优先进行目标明确的 patch 更新并检查实际锁差异，保持现有 crypto provider、TLS 配置和证书校验语义。该更新覆盖四条官方修复范围，但应以更新后 cargo-deny 的真实输出确认。

需要重验主要 HTTP / WebSocket / proxy 使用方、TLS 失败与会话行为，以及依赖这些路径的 Agentd / Objective History 验收。单纯版本存在和 semver 相容不是已完成这些验证的证据。

### 2. ZIP：库升级带来明确 API 变化，提取边界需要负例验证

当前自写提取器在 [startup_sync.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/d32e795f0d24df89fc57745f6fae70fbd0642eba/codex-rs/core-plugins/src/startup_sync.rs) 使用 `ZipArchive::new`、`by_index`、`enclosed_name`、`File::create` 与 `io::copy`，最后把 `entry.unix_mode()` 原样传入 `Permissions::from_mode`。它没有直接调用公告描述的 `ZipArchive::extract`；因此三条公告的具体利用机制不能直接搬到这个函数上。当前应用层确实没有单独屏蔽特殊权限位。

已按 registry checksum 检查 `zip 9.0.5` 的发布源码：`ZipFile` 已变为 `ZipFile<'a, R: Read + ?Sized>`，本仓库的 `ZipFile<'_>` 参数签名需要适配。更深入的源码读取还确认，新版 `unix_mode()` 经 `get_unix_mode` 调用 `clear_specials_bits`，会处理 SUID / SGID / sticky 位。因此不能声称升级后同一调用必然继续保留这些位；应在适配后用真实归档输入验证。应用边界显式保留允许的普通权限位是可审查的实现选项，不能拿静态猜测代替负例。

该函数的生产入口是 OpenAI curated GitHub zipball 和后备导出下载，写入新建 staging 目录，再检查 marketplace manifest 并激活。本次未证明攻击者可控制该生产输入，也未证明提取进程具有特权。建议针对特殊权限位、路径逃逸、符号链接及已存在路径、损坏归档、staging 清理与失败不激活进行具有效果的测试，并保持可执行脚本的正常权限行为。

### 3. YAML：替换底层不维护实现，覆盖真实文档语义

`unsafe-libyaml` 来自 `serde_yaml 0.9.34+deprecated`。官方公告明确指出 `serde_yaml_ng` 等 fork 仍可能使用该底层实现，所以不能把包名换成近似名称就判定修复。官方建议的安全 Rust 方案包括 serde-saphyr / saphyr；本次读取到 serde-saphyr 1.3.0 与 2.0.0 的 MSRV 为 1.89，与当前 1.95 工具链并不冲突，但没有声称它们与现有 API 即插即用。

实际使用方有 `from_str` / `from_slice`、`Value` 映射处理、`Error` 类型、技能 frontmatter 修复与 scalar 检查。迁移必须验证 plugins / commands / skills / agent migration 的有效文档、错误与边界语义，避免静默改变既有文档含义。所有 transitive 来源都应从实际更新图中确认已消除。

### 4. Linux 凭证后端：有比盲升 keyring 4 更小的候选

当前只有 `keyring-store` 与 `rmcp-client` 的 Linux manifest 显式启用 `linux-native-async-persistent`，它引入 `secret-service / zbus / zvariant`。已读取并保留 keyring 3.6.3 的官方发布清单：同一版本还有 `linux-native-sync-persistent`，保留 Linux native 与 persistent Secret Service 能力，改用 `dbus-secret-service`。其官方 README 说明 keyring API 本身始终同步，并建议此类应用使用同步后端。

因此，可先评估这两处 feature 选择的迁移，并验证完整 workspace 是否仍有其他 zbus 引入方。这是更换实现的候选，不能以关闭凭证持久化功能来规避门禁；需要确认既存凭证的读写删除、service/account 映射、锁定会话、错误语义、async 调用侧不阻塞 / 死锁，以及 Linux libdbus 与 Bazel 构建条件。macOS / Windows 原有 store 行为也需要保留。

直接升 keyring 4.2.0 并不能自动解决问题：它改成 keyring-core 与独立 backend 模式，原来的 feature 组合不兼容；当前 `zbus-secret-service-keyring-store 1.0.x` 与 `secret-service 5.x` 仍依赖 zbus 5，尚未到公告建议的 zbus 6。不能把“升级 keyring”当成已经关闭三条停止维护记录。

### 5. Matrix：工具链、anymap 与 SQLite 需要一起设计

官方 registry 和 checksum 验证的 `matrix-sdk 0.19.1` 发布清单均表明：0.19.0 / 0.19.1 要求 **Rust 1.96**，而且仍直接依赖 **anymap2 ^0.13.0**。所以升级到 crypto 公告的修复版本，只解决其中一项；当前 Rust 1.95 工具链也无法直接满足新 MSRV。

SQLite 还有独立的确定性约束：Matrix sqlite 0.19.x 要求 `rusqlite ^0.40.2`；该版本在 native 目标要求 `libsqlite3-sys ^0.38.2`。已锁 `sqlx-sqlite 0.9.0` 要求 `>=0.30.1,<0.38.0`，当前选择 0.37.0，且该包声明 `links=sqlite3`。版本区间不相交，不能只改 Matrix 版本并继续套用目前 `third_party/matrix-sdk-sqlite-0.18.0` 的约束补丁。证据见 [sqlite-upgrade-constraints.json](sqlite-upgrade-constraints.json)。

推荐把 Matrix 单独作为受控迁移：选择并统一 Rust 1.96 的 Cargo/Bazel/CI 工具链；核对 anymap3 替代的上游或受维护 patch；与 SQLx 共同确定 SQLite links 版本，迁移并审查原 sqlite / imbl 本地 patch；验证加密消息、缺 cross-signing keys 情况、数据库迁移、WAL / 恢复与凭证存储。若改用向旧系列回移修复的方案，需要真实修复来源和可验证的版本 / advisory 对应关系，不能通过改版本标签或隐藏依赖来源绕过检查。

## Cargo、Bazel 与最终验收

[MODULE.bazel](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/d32e795f0d24df89fc57745f6fae70fbd0642eba/MODULE.bazel) 的 `crate.from_cargo` 直接读取 workspace Cargo.toml 和 Cargo.lock，并枚举 Linux / macOS / Windows 各目标；工具链也固定在 1.95.0。仓库 `scripts/check-module-bazel-lock.sh` 使用 `mod deps --lockfile_mode=error`，提示通过 `just bazel-lock-update` 更新派生锁。因此未来真实依赖迁移必须检查 Cargo 与 Bazel 两套输入 / 派生锁的一致性，不能只让一个 cargo-deny 命令变绿。

建议保留五个独立修复范围的审查边界，在新的依赖修复分支完成实际解析、实现、针对性测试和全仓门禁；不继续向当前活跃 PR 头追加诊断性变更、反复重启其全部 CI。未生成升级锁、未编译升级版本，本报告中的候选组合不能用于宣称已经修复或允许普通合并。

## 原始证据与复核入口

- [execution.json](execution.json)：两条诊断命令、时间、退出码、源码身份前后、数据库 SHA。
- [tools-installation.json](tools-installation.json)：官方工具二进制、下载校验与版本输出。
- [cargo-deny.log.xz](cargo-deny.log.xz)：完整新诊断日志的无损压缩。原日志 13,717,460 字节，SHA256 `d91f5e6d8d9961b81aebaf6873d85a1dc7ac70e1a009e5e1036e026ebc179175`；压缩后 358,668 字节，SHA256 `8abd8f649025c16af81d7f83c97d82bae6b2e1fd3fbbbd646b3d749de4fff44f`。已解压复核同字节，原文件也保留。
- [preservation.json](preservation.json)：19 个仓库源文件复制件、Git blob 与 SHA、压缩复核。
- [dependency-scope.json](dependency-scope.json)：完整锁定 metadata 中受影响包的直接父依赖及 workspace 入口。
- [agentd-reachability.json](agentd-reachability.json)：两个目标上的 normal 图存在性、features 与作用范围。
- [upstream-sources/manifest.json](upstream-sources/manifest.json)：13 个官方 sparse-index、3 份 checksum 验证的候选 crate 源码、下载时间和原字节 SHA。
- `official-advisories/`、`rustsec-official-pages.json`：固定数据库原文及官方网页读取；网页读取时刻未单独捕获，文件保存时间不冒充观测时间。

补充保留件见 [preservation-supplement.json](preservation-supplement.json)：keyring 3.6.3 官方 crate 与当前 Cargo.lock checksum 相同，其中 README / Cargo 清单逐字节提取；rusqlite sparse-index 的原 cache 字节与已记录 SHA 相同；Matrix sqlite / imbl 的现有 patch 清单及固定 cargo-deny action Dockerfile / entrypoint 也已复制。工具缓存将被排除，关键分析证据仍能独立复核。

## 最后一轮普通 CI 观察

在 **2026-10-19 01:56:31.362–01:56:32.629 UTC** 对精确 d32 头进行有界读取，原响应见 [round-07-final.json](../round-07-final.json)，结构化结论与每个正在执行任务的开始时间 / 当前 step 见 [final-status.json](../final-status.json)。

- Architecture source-head 于 **01:53:04 UTC** 成功，实际 native 回归步骤执行成功；Architecture required 于 **01:53:09 UTC** 成功。base-merge 的成功及按条件跳过的 native 范围另外保留，不能替代 source-head 的执行证据。
- cargo-deny 仍是唯一失败检查。blocking-ci 还有 **15 个 SDK / Bazel job** 执行中，独立的 `CI required` 尚未生成；CodeQL Rust 也仍在执行。
- 精确头共 **47 个 checks：23 success、6 skipped、1 neutral、16 in_progress、1 failure**。这是观测时刻状态，不是完整 blocking-ci 终态。
- PR #2815 仍为 **Ready / open / unmerged / blocked**，保持普通 squash auto-merge。`branches/main` 的成功响应返回 `CI required`、`Architecture required`，enforcement 为 non_admins；本轮没有请求完整 `/protection` 配置，分支响应不能冒充完整权限审计。

本诊断与 CI 状态分开保留，没有继续无限轮询。可提交证据包的严格清单逐份绑定路径、字节数与 SHA256；失败读取和中间进度收据也保留。压缩原始日志会进入包，重复的未压缩本地副本、工具安装目录、Cargo / Rustup cache、工作树及编译对象不进入包。完整排除列表与生成收据另存。所有本机输入、工具和缓存位于专用隔离目录，原产品工作树与 G1 工具根没有改动。
