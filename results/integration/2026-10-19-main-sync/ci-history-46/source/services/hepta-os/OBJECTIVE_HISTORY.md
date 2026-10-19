# 已知 Objective 的持久准入历史

`objective-history` 是默认关闭的可信 Linux host 功能。它接受请求 owner 已保存的
原始签名 ObjectiveStart 信封，通过原 Hepta 的窄读接口查询一条历史 publication。
`ObjectiveHistoryClient` 只有一次查询方法；`hepta-history` 提供对应命令行入口。
请求签发、原始意图保存、运行投影和实际操作效果继续由各自既有 owner 负责。

## 版本与当前资格

新接口是原 Hepta 的独立小改动，见
[owner PR #2815](https://github.com/TrillionniumFoundation/hepta-private-ci/pull/2815)。
[OBJECTIVE_HISTORY_CONTRACT.json](OBJECTIVE_HISTORY_CONTRACT.json) 固定实际扩展提交、
原始基线、Cargo.lock 摘要和所审查源文件。默认 observer 与 ObjectiveStart 的
`UPSTREAM_CONTRACT.json` / `OBJECTIVE_UPSTREAM_CONTRACT.json` 继续绑定原 `f8c9419d`；
这两个旧契约不被改成新接口已经存在于原基线。

桌面产品源码 `c080896189b6d5c1e411a28b7614c8fcdc33b188` 的 Linux host 验证已执行：
51 项 Rust 测试、严格 all-target Clippy、默认关闭构建检查、fmt 和三个实际 CLI
构建通过。其中 10 项专门检查历史读取，其余保留原只读/提交与编译失败约束。
这些 socket 测试使用脚本化响应，不能代替真实 owner 的签名、持久化和重启资格。
新 owner/probe 的实际运行结果由 [STATUS](../../docs/STATUS.md) 与独立原始收据记录。

## 模块开发入口

| 文件 / owner | 职责与修改边界 |
| --- | --- |
| `src/objective/history.rs` | 公开有界历史类型、anchor、一次查询及结果分类；无提交方法、存储或通用 RPC |
| `src/objective/history_wire.rs` | 仅 `ObjectiveAdmission` 的固定请求/回复子集，严格未知字段拒绝及请求身份核对 |
| `src/objective/mod.rs` | 与既有 ObjectiveStart 共用私有 `exchange_raw`，保留端点、peer、帧与超时约束 |
| `src/bin/hepta-history.rs` | 从显式参数及 stdin 收取可信输入，只输出有限元数据和明确退出码 |
| `tests/objective_history.rs` | 真实 Linux UDS 的线协议、漂移、anchor、容量及一次读取负例 |
| 原 `hepta-agent-protocol` | 定义查询、published / unknown 类型与方法分派 |
| 原 `hepta-agentd::objective_runtime` | 在既有 owner mutex 内匹配原认证记录、canonical body 和 profile |
| 原 `hepta-learning-ledger` | 在已恢复的原 journal 前缀中读取 publication 与核对 retained anchor |

客户端镜像只保留原公开控制协议的所需子集，不引入 Hepta 全 workspace 依赖。
feature 依赖已有 `objective-transport` 以共享 transport；`ObjectiveHistoryClient`
本身不导出 submit、raw-send 或 journal 操作。默认 `ObserverClient` 仍只有原四个
读方法，Session IPC 与 Shell 在本切片中没有历史查询或提交命令。

## 三类状态必须独立

| 观察 | 可以确认 | 不能据此确认 |
| --- | --- | --- |
| `historical_publication` / `compiled` | 原 owner 找到匹配请求的不可变 compiled publication | 当前 run 存在、曾进入运行时、模型已执行、最终使用授权或设备效果 |
| `historical_publication` / `explicit_abstain` | 原 owner 曾写入明确 abstain disposition | 任务效果成功 |
| `historical_publication` / `conflict` | 原 owner 曾写入与请求绑定的 conflict publication | 该请求获得准入 |
| `RunStatus` 非空 | 当前 owner 提供一个已知 run 的内存投影 | 所有关联操作的持久终态 |
| `RunStatus: null` | 当前内存投影不存在 | 原请求从未被接受或 publication 从未落盘 |
| 历史 `unknown` | 本次读取不能给出匹配且受约束的正面历史证据 | 未准入、NotApplied、安全重投或清除先前未知 |
| `query_not_sent` | 本次历史读查询发送了零字节 | 原 ObjectiveStart 未发送或未发布 |

原 owner 可以先持久发布 RunStart，再在后续运行时准入检查中返回错误。
因此新接口采用 `historical_publication`，不把所有 compiled 历史编码为 admitted。
效果恢复继续以原 Operations 的 `K=(scope_id, operation_id)` 和目的端证据为准。
Objective 的 request ID、message ID、run ID 与 publication sequence 都不是 K 或 HOS2 D。

## 输入、信任与代际

可信调用者提供两组不同来源的数据：

1. 原请求 owner 保留的准确原始 `AuthBusObjectiveIngress`，包括 issuer/key epoch、
   message ID、sequence、expiry、signature 及完整 typed body；读取不改写原 body spawn。
2. 可信 launcher/supervisor 提供当前端点的 AgentId、spawn、UID、PID 和本次 request ID；
   重启后的外层 spawn 与旧信封的 body spawn 可以不同。

`ProvidedObjective` 仅作结构与容量检查，不验证当前签名有效期，也不签发或改签。
原 owner 对照 journal 中完整 `RunStartAuthenticationV1`，包括原 signature 字节、
owner 推导的主体 scope、canonical typed body 摘要、run 与已配置 profile 摘要。
只有完整匹配的既有记录可返回 publication。历史读取不要求旧 issuer 仍未撤销或
旧信封仍在有效期内；新的 ObjectiveStart 仍走原当前权限与期限检查。

客户端核对返回的原请求身份、原 spawn、publication sequence 和摘要形状；它不
独立重算 canonical body、publication 或 chain，也不重新认证签名。可信 owner
与其已恢复 journal 是正面证据来源，不能把 socket fixture 当成密码学认证测试。

## Anchor 与存储故障

`HistoryAnchor` 是调用者从以前可信 owner 回复中保留的 `{ sequence, chain_digest }`。
sequence 必须在 **1..=4096**，摘要须符合固定 64 字符小写非零十六进制形状；构造、
反序列化后的查询入口和回复三个位置均检查。现有 ObjectiveStart 收据没有 publication
sequence，调用者不能猜测 sequence，也不能拿待验证的当前文件自行生成可信 anchor。

无 anchor 时，正面结果只描述当前可信 owner 保留的记录。带 anchor 时，原 owner
先确认该 sequence/chain 存在于已恢复前缀，再确认目标 publication 在此前缀内。
早于目标的 anchor 不能覆盖后续记录；同序号摘要不同、已保存的 anchor 缺失或
目标不在覆盖范围内都保持 unknown。客户端额外检查目标序号上界及同序号摘要。

查询在原 owner mutex 内使用已经恢复、独占持有的 journal 投影，不打开文件，
不 append、recover、truncate，也不推进 replay frontier。原启动恢复可能截去
未完整写入的尾部；保留在原 journal 之外的可信 anchor 可识别恢复后的覆盖缺失。
这不提供运行中磁盘篡改检测；文件和外部 anchor 一起回滚也不在本机制检测范围内。
存储损坏可能使 owner 启动失败，此时 transport 失败同样保留原提交未知。

原请求和 anchor 的可靠保存仍属于既有请求 owner。客户端没有另一份数据库，
也不会把 Shell 草稿当成请求账本。查询成功不会恢复运行、补发目标或触发效果。

## 固定线协议

外层沿用 Agentd control schema **2**，每个连接只交换一条 LF 结尾 JSON 帧。
请求保留 `schema_version`、`request_id`、当前 `spawn_generation`，方法为：

```text
method = {
  "type": "objective_admission",
  "query": { "request": <原始信封 JSON 对象>, "anchor": null 或已保留的 anchor 对象 }
}
```

请求与回复最大 **65,536 字节（含 LF）**；原 source 最多 32 KiB，canonical body
最多 48 KiB。即使原信封自身可解析，包裹新查询后超过帧界仍在连接前拒绝。

回复 outer schema/request/AgentId/current spawn 必须与可信调用绑定；当前 generation
必须在原 serving offset 范围内。published 含原身份、body/profile 摘要、publication
sequence/digest/chain 和三种明确 disposition。unknown 只接受以下七个原 reason：

| reason | 解释 |
| --- | --- |
| `invalid_query` | 原请求或 anchor 结构不符合 owner 的查询条件 |
| `owner_unavailable` | 没有已配置的 Objective owner |
| `journal_unavailable` | 原 journal 当前不可读取 |
| `no_matching_publication` | 当前 owner 没有找到完整匹配的 publication |
| `anchor_missing` | 已提供的历史 sequence 不在当前恢复前缀 |
| `anchor_mismatch` | 对应序号的 chain 与保留值不同 |
| `publication_outside_anchor` | 目标 publication 比提供的可信 anchor 更新 |

这些 reason 都不构成否定准入或效果的证明。未知字段、额外帧、缺少 EOF、错误
peer、request/身份/代际不符、非法摘要或超限序号都拒绝；原错误文本不向调用者转发。

## 单次 CLI 与 API

```sh
cargo +1.88.0 build --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-history --bins
```

```text
hepta-history <absolute-socket> <agent-uuid> <current-spawn> <peer-uid> <peer-pid> <request-id> [<anchor-sequence> <anchor-chain-digest>]
```

stdin 提供完整原始信封直到 EOF，外层不附换行；调用者关闭 stdin 并限制整个子进程。
获取 stdin 发生在 socket 的五秒 deadline 之前。命令只执行一次读，最多一个连接，
没有自动重试、端点发现、PID 推导或从回复反向建立信任。

```rust,ignore
let config = EndpointConfig::new(socket, agent_uuid, current_spawn, uid)?;
let history = ObjectiveHistoryClient::new(config, expected_pid, request_id)?;
let attempt = history.query_once(retained_original, retained_anchor);
```

在普通 blocking worker 中使用；Tokio runtime 内调用得到有限的执行上下文错误。
端点及其 canonical 非 symlink 私有父目录须匹配期望 UID，无 group/other 权限；
Linux `SO_PEERCRED` 必须与期望 UID 和准确 PID 相符。路径、连接、全帧写入和
回复/EOF 使用共享五秒 deadline，保留真实写入字节数；不重绑定到重启后的进程。
同 UID 的恶意程序和特权进程仍在主机信任边界内，这些检查不提供二进制认证。
原 server 没有因新增本接口获得 peer 身份认证；私有目录/socket 与原代际 fence
仍是它的接入边界，准确 UID/PID 核对由此桌面客户端执行。

stdout 为一条 schema 1 JSON 收据（`--help` 除外）。请求解析成功后的收据包含
本次 current identity、原请求身份、anchor、实际写入数与预期帧长；成功还含 publication、response generation
及 `anchor_coverage`。无 anchor 为 `current_owner_journal`，带 anchor 为 `retained_anchor`。
收据不含信封源码、签名、socket 路径或原错误文本。
参数、端点、anchor 或 stdin 预解析失败只输出最小收据：schema/status/有限 issue
与 `bytes_written=0`，不伪造尚未取得的 identity、anchor 或帧长。

| 退出码 | status / 处理 |
| --- | --- |
| `0` | `historical_publication`，继续读取 disposition；conflict 不代表准入 |
| `10` | `query_not_sent`，仅表示本次读查询零发送 |
| `12` | `unknown`，保留原提交未知以及准确原始请求 |
| `74` | stdout 无法完整交付；调用者没有完整本次收据 |
| `2` | 非 Linux 的 `unsupported_platform` |

任何退出码都不授权重新签发或重新提交目标。后续显式历史读取仍由可信调用者决定。

## 验证与下一步

轻量检查同时覆盖旧 observer/ObjectiveStart 共享 transport：

```sh
cargo +1.88.0 test --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-history
cargo +1.88.0 clippy --locked --manifest-path services/hepta-os/Cargo.toml \
  --features objective-history --all-targets -- -D warnings
cargo +1.88.0 check --locked --manifest-path services/hepta-os/Cargo.toml \
  --no-default-features
cargo +1.88.0 fmt --manifest-path services/hepta-os/Cargo.toml -- --check
```

真实 owner 资格另用 `tests/integration/hepta/run_objective_history.py`，从上述独立
合同读取准确源码，不改旧 R8 PIN。它复用原 Fleet/Supervisor、Objective profile
和隔离签发 fixture，经实际 CLI 读取，保留进程身份、原文件前后摘要与结构化收据。
`--prepare-only` 只生成/核对构建输入，不能记为运行通过；`--execute` 的真实结果
须与原始日志、源码、lock、实际 ELF 和明确故障检查共同审查。runner 中的内嵌
source binding 与 ELF 前后哈希检查不独自证明二进制如何生成；预构建输入还须
与调用者的准确源码/构建命令/产物哈希收据配对，CI 则从固定源码直接构建。

本切片的闭合目标是 S2 中“已知原始请求的在线准入历史查询”。生产请求 owner 的
保存/签发接入、Session/Shell 安全投影、原 Operations 效果恢复与 K↔D、最终使用
授权、Asterinas G1/G2 和移动适配仍按 [下一切片](../../docs/agents/R8_NEXT_SLICE.md)
分别验收。开发变更同时更新原 owner 协议、独立 source contract、客户端窄类型、
真实故障判定器与本说明；不通过扩张默认 observer 方法来隐式获得新权限。
