# R7 ObjectiveStart 有界传输：冻结源码轻量验证

**全部本地验证通过。** 执行源为 `19c2185d27c1d788354e14af27999406bc927c4f`，
tree `fc2019d43fcb06d7583e1d4904042e3ddcab229d`；运行前后 HEAD、tree、干净状态与
记录的源码/manifest/lock 文件摘要完全一致。执行时间为 **2026-10-18
04:17:27–04:17:50 UTC**，Linux x86_64，Rust **1.88.0**。后续归档或文档提交不
替换这份实际执行源码与原始收据。

本轮实现的是默认关闭的 `objective-transport` feature：在独立可信 host worker
中传输外部提供的原始 ObjectiveStart 封套，记录发送进度与有界 typed 结果。
**结构校验不等于认证**；这份实录没有启动原版 Agentd、安装 issuer、生成密码学
签名、向原版提交 Objective、运行模型或产生设备效果。完整实现、wire、错误边界与
剩余接线条件见[技术契约](../../../../../services/hepta-os/OBJECTIVE_TRANSPORT.md)。

## 实际运行结果

| 验证 | 结果与分母 | 原始记录 |
| --- | --- | --- |
| 默认 feature-off 全 targets 编译 | passed；`--no-default-features --locked --offline` | [日志](validation-01/feature-off-check.log) |
| feature-on 完整 Rust 测试 | **35 / 35 passed**；0 ignored、0 failed | [日志](validation-01/feature-on-tests.log.gz) |
| 既有 observer 基线 | 上述 35 项中的 **17 项**：16 个原 socket-contract 测试 + 1 个 metadata admission 单测 | 同一完整日志，未单独重复计数 |
| 新增 Objective 传输与结构测试 | **15 / 15 passed**；真实临时 UDS 交换、发送前拒绝与纯结构负面场景 | 同一完整日志的 `objective_transport.rs` 段 |
| 部分写入取消逻辑 | **1 / 1 passed**；3-byte Tokio duplex 强制部分写入，随后取消与写失败仍保留正数计数/Unknown | 同一完整日志的 `objective::tests` 段 |
| 编译期接口约束 | **2 / 2 passed**；禁止同一 transport 二次调用，原始封套无 Debug | 同一完整日志的 compile-fail 段 |
| 严格 Clippy / fmt | passed；全 targets，`-D warnings` | [Clippy](validation-01/strict-clippy.log)、[fmt](validation-01/format-check.log) |
| 固定原版源文件 | **14 / 14** Git blob、SHA-256、字节数完全匹配 | [提取日志](validation-01/original-declaration-extract.log) |
| 实际原声明 wire conformance | **7 项检查组通过**；编译原 serde 声明与 AgentId，运行本地断言程序 | [执行日志](validation-01/original-declaration-wire-run.log) |

新增 15 个测试并非 15 次真实原版入站：它们包含本地 UDS 与结构校验场景。
duplex 单测只证明取消与计数逻辑，不证明内核 UDS 或原版认证。7 项原声明检查是
独立的小型可执行程序断言组，不与 Rust test harness 的 35 项混算。

## 已验证的行为

输入由原 `AuthBusObjectiveIngress` 的七个字段和 body 的十个字段组成，保留原始
JSON 字节、issuer/message/run、sequence/revision/authority、signature 和 source。
原版协议的过期、全零签名 fixture 被明确复用为 wire-only 测试输入，没有 signer。
请求保持实际原 wire：`method.type = objective_start`，`method.request` 为原始对象；
原版 `objective_run` 是扁平 payload，不能误用客户端 `Admitted { receipt }` 的形状。

发送前验证 canonical 私有目录/socket、UID、配置的 peer PID 和 immutable spawn。
同一连接通过部分 write 完成一个 frame；任意已写入字节都进入可能已送达边界。
超时、断连、截断、多余帧、非 UTF-8、错误 request/source/run identity、通用
`request_rejected` 或未知 owner code 均保留 `SubmitUnknown` 和原输入。错误与状态
不返回原始 source、signature、socket path 或 owner diagnostic。

只有严格匹配来源/请求、code、message 的原版 `objective_unavailable` 和
`unsupported_schema` 可标记**本次已发送但发布前拒绝**，不能写成 NotSent，不能
清除任何此前 unknown。`RunStatus { run:null }` 不是 ObjectiveStart 结果，不能
消除持久发布的不确定性；本 API 不提供这种 reconciliation 或自动重试。

完整帧发送后测试 peer 不回应，客户端在同一五秒 deadline 内返回 Unknown。peer
在确认客户端已返回后检查监听队列，实际拦截第二次连接/自动重试。普通线程构造、
误入 Tokio runtime 调用的路径也已验证：NotSent、零写入、无连接，Drop 不发生
嵌套 runtime panic。`shutdown_background` 仅避免调用线程无限等，不能强杀已经
阻塞的 filesystem syscall；原一槽 admission 仍由实际 worker 持有。

## 原声明与执行来源

[SOURCE_BINDING.json](validation-01/wire-reference/SOURCE_BINDING.json) 记录固定
原版 `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 的 14 份源文件身份、10 个
声明/fixture 函数的原提取行范围与摘要、唯一整文件 AgentId 拷贝、局部断言程序
摘要，以及所有生成文件的摘要。仅 request/payload enum 缩窄了 variant，原始
类型和字段没有被自定义服务器或 authority 代替。

小型项目的 [Cargo.toml](validation-01/wire-reference/Cargo.toml) 和
[Cargo.lock](validation-01/wire-reference/Cargo.lock) 复用 desktop 的轻量闭包，
只显式替换唯一根 package 名；实际 `--locked --offline` 构建/运行后 lock 摘要
仍一致。**没有构建 733-package 原版 Agentd crate，也没有运行任何原版 owner。**
原声明及测试程序本身保存在 [main.rs.gz](validation-01/wire-reference/src/main.rs.gz)，
其读取的 all-zero fixture 与原版既有 wire factory 的字段值相等。

[实际运行收据](validation-01/receipt.json) 包括各命令、开始/结束时刻、退出码、
执行进程 ID、原始日志摘要、工具链可执行文件路径/摘要/版本、执行源前后身份与
文件摘要。执行 helper 的前后摘要一致；所有步骤都有 120 秒上限，异常清理仅针对
本 helper 创建的 process group。没有借此接触常驻服务或设备。

## 归档、清理与尚未闭合项

[MANIFEST.json](MANIFEST.json) 保留 **14 个原始输入、54,119 字节**的逐文件来源
与 SHA-256，复制后逐字节复核。测试原日志和生成的 main.rs 使用无损 gzip（mtime=0），
解压字节及原 SHA-256 均保持；manifest 另记录压缩后字节数与 SHA-256。这样保留
原始末尾空行而不改写实录。`SHA256SUMS` 覆盖本目录除其自身外的全部文件，
包括原始 helper、完整日志、原声明提取结果及新写的说明。无 ELF、Cargo cache、
issuer 密钥或原版私有运行状态。只读的[清理检查](fixture-cleanup.json)在结束后
未发现本轮两种 fixture 前缀的残留目录；fixture 自身只删除其刚创建的私有目录。

实际部署仍需要原 owner 提供已安装的 issuer/trust、独立 replay checkpoint、
冻结的 objective profile、真正既有原始认证封套，以及既有 owner 对 pending/unknown
的持久恢复契约。当前 attempt 保留仅在内存，不宣称跨进程 exactly-once，也不
安装第二份账本。原版 durable publication 后故障、revoke、restart、同 identity
恢复及 HOS2 K/D、ack、retirement、真实设备效果仍须独立原版运行验收。

R6 的[原版 Agentd → 持续 Session / Shell 实录](../2026-10-17-original-session-runtime/README.md)
属于已完成的只读生命周期证据。本轮功能不会把该旧证据改写成认证 Objective
或设备控制通过，也不会给现有 UI、Session IPC 或 `TrustedReadOnlyOrganV1` 增加
提交入口。
