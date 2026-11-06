# Pocket4 全 Launcher App 修复：检查点 08

工作尚未完成。范围是当前目标用户的全部 Launcher App，原定八个应用只是历史子集；最终还要验证业务、长时间运行、重启和故障恢复。此文件区分实际完成、实际失败和未执行的候选。

## 当前范围已经逐组件核实

目标仍是 Pocket4 内置 DroidLoom Android 17 / SDK 37 / user 0。旧 reDroid 14/16 已在先前退役，不能将内置 Android 的结果写成 reDroid 测试结果。

2026-11-06 的只读任务 `1a1b22e95d0-fc05-7cd4` 实际 exit 0，终态已持久化，完整 stdout 25,256 字节，SHA-256 `854e3e184b52e6f580ccf991b7bf6526786d89e64570e197b52559a9892df19d`。五条固定 PackageManager 命令包括实际 help，以及两轮包清单和 MAIN/LAUNCHER resolver 查询；三次原生查询完成前后核对。

| 当前实测项目 | 结果 | 证据边界 |
|---|---:|---|
| user 0 已安装 APK 包元数据 | 205 | 包含静态共享/SDK 库；不含 APEX 或已卸载包 |
| 可解析 MAIN/LAUNCHER 组件及其包 | 45 / 45 | 两次查询相同，逐组件与原生目录完全一致 |
| 明确绑定 APK/UID/数据身份的范围 | 47 包 / 87 APK | 45 个 Launcher 包，加 actions 与新 QA helper；其余 PM 行不继承字节或 UI 资格 |
| 实际升级安装 | 11 App | 同签名、保留原 UID/数据；不等于业务通过 |
| 与当前官方完整资产逐字节相同 | Fcitx、microG | 仍需业务回归 |
| 原审计批次通过 | 10 App / 14 APK | b05 保持失败，b06–b13 尚未完成 |
| production ready | 0 | 启动、登录/访客、核心操作、权限、网络/存储、长运行、重启/恢复未全通过 |
| 删除旧 framework/App/产物 | 0 字节 | 清理的最终验收条件尚未满足 |

PM 查询的 12,930 个观察 FD、20 个租约 FD 均完整关闭；持有的 namespace 目标与 action lock 已释放。自有子进程 1225420 正常退出，原 pidfd 观察退出并关闭，父进程 FD 身份恢复；无超时或 kill。原始数据见 [current_services_r4/actual](successor_audit_requests/current_services_r4/actual)。这是枚举证据，不是权限实态或业务验收。

11 个实际升级为贝壳、东方航空、国航、微信、拼多多、淘宝、滴滴、携程、哔哩哔哩、京东、抖音。官方版本元数据不能代替签名一致、ABI/SDK 适用且实际运行的完整交付包。美团已装包与官方候选签名不同，不能强行覆盖或重签；12306 与猪八戒的部分下载仍不是可安装交付。国际应用的剩余交付、全部应用的可用最新版判定及回归均未完成。

## 权限与历史授权

继续使用已有 sidecar、容器内 UI Automator、中文输入和节点定位，不引入 ADB。哔哩哔哩 Accept 仅属于历史独立测试 cell `p4-bili-m30-cell-20261010`，不能转移到 Main。美团外卖的位置权限不主动开启。完整性、签名、运行时所有权与进程退出约束保持有效。

当前 manifest 声明、保存的权限元数据和 205 包清单均不能证明有效授权。有效 grants、AppOps 与 roles 仍为 UNKNOWN；r4 没有查询或修改它们。r3 的 AppOps help 实际返回 255，该失败原样保留；r4 是独立的 PackageManager 五命令观察，并未将 255 改为成功。

## 贝壳 QA：原自有任务已经合法退出

新 helper `org.droidloom.qa.successor.p8f89f253350ba2fa.r1` 已实际构建与安装，UID 10157；原始 helper 构建、安装、准入和真实 UI 证据保留在先前检查点。关闭入口 popup 的旧操作仍为 UNKNOWN；没有重放点击或将旧结果改成成功。后续只读观察显示过首页，独立当前观察显示 IHG 位于前台，因此旧的当前上下文发布器正确拒绝发布。

本轮使用原 recorder 已有的 cleanup 例外和原任务所有权机制处理测试创建的 task 876，未改 `Flow.begin`、guard、运输层或清理代码。

| 实际任务 | 结果 |
|---|---|
| 固定当前前台观察 `1a1b206d887-fc05-7c16` | exit 0；当时 IHG 在前台，贝壳 task 876 身份仍一致 |
| 原自有 task 清理 `1a1b2307f12-fc05-7cdd` | exit 0；一次 remove 876，一次后置读取证实缺席，其余 task 875/877 保留 |
| 原证据保全 | 177 个文件、888,207 原始字节及文件身份保持不变；旧 UNKNOWN 保留 |
| 清理进程生命周期 | 子进程 1229651 正常退出，原 pidfd 退出/关闭、父 FD 身份恢复；namespace、原 flow lock 随正常退出收口 |

清理实际结束于 2026-11-06T18:48:11.546832Z。完整 stdout 8,920 字节，SHA-256 `14a32088291f748d2d894783d4a27566dbe2f5b4a41dba0ffe54dc42ecd22224`；见 [owned_cleanup_r1/actual](successor_qa/owned_cleanup_r1/actual)。它只结束自有测试任务，没有删除 App 数据、旧构建或文件产物。新的独立 flow/launch 仍待执行，不能把清理通过当作贝壳业务通过。

完整 private UI bundle、截图、节点树和签名私钥不进入 Git；公开资料仅保留来源、结构性身份、摘要和回执。

## Calendar 资源解析与官方工具

Calendar/Fcitx 的实际 manifest/签名对照任务已执行，但 Calendar 的系统 aapt2 stderr 存在 **23,800 条 E 级资源诊断**。虽然部分命令退出 0，资源健康仍未通过；原 b05 失败保留。错误包括 offset 对齐/范围与 entry 边界问题，不能仅凭错误文本推断旧工具不支持新格式。

通过 Google 官方 Maven 元数据实际查询，当前最高稳定版 AAPT2 为 `9.5.1-16666295`；metadata 的 latest/release 为 alpha 版，不以它替代稳定版。官方 Linux JAR 已在任务 `1a1b220b4d3-fc05-7c7f` 完整下载，2,451,278 字节，SHA-256 `fa1014cb1431622d292ef55ba870e75882ea19987bec541698b912f446a2d08f` 与单独获取的官方 checksum 一致，HTTPS 正常验证、无重定向，ZIP CRC 与成员约束通过。此检查点仅证明下载及文件验证，尚未解包或运行新版工具，也没有修改 APK。后续须在宿主完成工具资格验证，再对同一已绑定 Calendar APK 做对照。

## Framework 构建仍未成功

真实 SystemUI/WindowManager provider 和源码锁的修复、builder470 源代码和实际 Rust 资格结果已保存在检查点 07。builder470 实编/控制通过不等于 Soong/framework 产物通过，更不等于 Main 部署或业务可用。

build07 `1a1b20bbc0a-fc05-7c2e` 实际 failed 1，前后 Main 范围与资源约束检查通过，但内层准备在编译器启动前遇到缺失输入。独立只读诊断 `1a1b2240691-fc05-7c96` 定位到旧 builder468 的固定 ELF 路径缺失：

`/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/cargo-target/debug/droidloom-update`

该诊断也因 ctypes 引入的 libffi FD 与最初 census 不同而整体 failed 1；只有缺失文件和调用链是实际观察，不能将诊断整体标记 PASS。旧身份契约包含 inode 与时间等字段，新复制相同 SHA 的文件不能冒充原身份。后续恢复/重新资格验证必须保留原收据和有效约束；此检查点未启动新的 framework 编译或部署。

## 后续验收与最终清理

继续完成官方适用交付、真实新进程 QA、各 App 核心操作和权限实态，随后执行长运行、重启与故障恢复。达到用户要求的真实可用状态后，才按实际运行依赖清理过期 Android/framework、旧 App 包、实验残留和中间版本，保留最终工作源码、配置与复现清单，并记录实际删除路径与释放空间。当前不删除仍用于复现、恢复或未完成验收的原始证据和构建。
