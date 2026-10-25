# Hepta host observer, ObjectiveStart and admission history

`hepta-os-observer` is the first concrete A10 Session → Hepta client slice. It
speaks the existing, fixed Agentd v2 JSON-over-UDS control wire. Its default API exposes only
`health`, `capabilities`, `events`, and `run_status`. The public API projects
bounded metadata and omits the upstream workspace paths, signing inputs,
session-ingress address, and arbitrary payloads.

**R9 历史查询接合：**默认关闭的 `objective-history` feature 增加独立
`ObjectiveHistoryClient` / `hepta-history`，向原 owner 查询已保存请求的持久
publication，支持调用者保留的 anchor 和 owner 重启后的新端点身份。当前产品
输入的 51 项 Rust 测试与严格检查通过；真实 owner 的运行资格单独以实际收据为准。
完整模块开发入口、协议、信任/存储边界、退出码及后续接合见
[OBJECTIVE_HISTORY](OBJECTIVE_HISTORY.md)。它不推进当前 run 或效果终态。

**R8 已完成证据（2026-10-18 UTC）：**固定原版 Hepta `f8c9419df6ddeb36ff8b522a50219981fb8d9345` 已实际完成两轮隔离测试 issuer 的签名 ObjectiveStart 进程门禁，每轮执行 7 次明确提交尝试，10 项核心检查通过。后一轮还完成已知 run 的三个持续 Session 阶段：当前 `admitted` 非终态、旧端点失效后的完整 stale 历史、显式替换 Session 后的 `projection_missing`；同一个真实 Rust Shell 保留 3 张 PNG。准入收据与停止 owner 后以只读文件经原始公共 API 校验的 journal 记录绑定，实际源码、ELF、日志与逐图审查见[本轮原版目标与桌面实录](../../results/integration/2026-10-18-objective-desktop/README.md)。这是 Linux host 上测试 issuer 的原版认证与持久准入资格；生产 issuer、在线持久结果核对和设备效果仍未闭合。

**R6 历史证据：**Linux host client 的真实 Unix socket fixture、负例和固定协议核验保留各自记录；固定原版 Hepta → 持续 Session worker → 同一个真实 Rust Shell 窗口在 R6 完成两轮六阶段只读运行。每轮保留原版 8 项与 Session 8 项断言、6 张成功 PNG、精确进程/代际来源与逐图审查，见 [R6 完整交付索引](../../tests/integration/hepta/evidence/2026-10-17-r6/README.md)、[持续 Session 实录](../../tests/integration/hepta/evidence/2026-10-17-original-session-runtime/README.md) 和[真实 Shell 窗口归档](../../tests/ui/evidence/2026-10-17-original-hepta-shell/README.md)。独立 ARM gate 及 ARM 持续 Session 的历史记录仍保留自己的架构、被测源码与产物来源。

上述 R6 运行发生于 2026-10-17 UTC。PR #189 归档的后续工作对源码、快照和像素作了独立复核，没有重新启动原版运行时。R6 源码已通过 [PR #187](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/187) 进入主干，该次 host/软件 Wayland 验证另见[集成索引](../../results/integration/2026-10-18-audit-followthrough/README.md)；其中 scripted fixture 的 Hepta 页布局不能写成原版 Agentd 新运行。原始 receipt 中的 ELF 摘要与该次审查可取得的文件分别记录，不把源码/归档复核写成一次新的 ELF 执行。

默认配置和 Session 仍使用只读观察客户端。R7 新增默认关闭的 `objective-transport` feature，R8 增加使用该 feature 的 `hepta-submit` 可执行程序；可信调用者从 stdin 提供外部已签发的原始 ObjectiveStart 信封，并独立给定端点、AgentId、spawn、UID/PID 与 request ID。程序输出一条有界的结构化收据，不签发信封、不重试。已知 run 可由可信 launcher 通过 `TRILL_HEPTA_RUN_ID` 交给 Session 的独立只读投影。原始 owner 准入的隔离进程门禁及复跑命令见 [ORIGINAL_OBJECTIVE](../../tests/integration/hepta/ORIGINAL_OBJECTIVE.md)，实际执行资格绑定上述本轮实录。模型 turn、生产 issuer 接入、durable K↔D 的桌面接合、HOS2 delivery、设备效果和 Asterinas 运行仍需各自验收。[剩余门禁](../../tests/integration/hepta/EVIDENCE.md#remaining-acceptance-gates)和 [S1–S5 下一切片](../../docs/agents/R8_NEXT_SLICE.md)继续分别记录。

| Surface | Current behavior |
| --- | --- |
| Linux Session worker | Explicit trusted endpoint; real UDS client with peer UID/PID checks |
| Shell renderer | Receives safe observation projection through Session IPC; no Agentd endpoint or generic RPC API |
| Health/capabilities | Observations and advertisements; neither grants effect authority |
| Events | Bounded process-local lifecycle metadata with exact cursor/gap validation |
| Known run lookup | Existing owner state; an explicitly launcher-selected run has an independent Session/Shell freshness clock, preserves stale history, and distinguishes a missing current projection from non-admission; no task listing |
| Objective input | UI drafts remain local; a separately trusted caller can provide an already signed envelope to the bounded CLI |
| Optional `objective-transport` feature | Separate trusted-host, one-attempt UDS API and `hepta-submit` CLI; default disabled for this service; Session explicitly includes it only for a trusted startup inbox (no default owner or envelopes) |
| Optional `objective-history` feature | Separate `hepta-history` read of one retained original request through the separately pinned owner extension; publication, live run and effect remain distinct |
| Default device control/HOS2 profile | No device startup, discovery or control; the default observer sends no HOS2 requests |
| Optional `cpu-history` feature | One `QueryDelivery` per `query_once` for an original owner's retained D, through a trusted host-supplied transport; default disabled, with no effect submission or UI entry |
| Windows/Android/Asterinas | No qualified transport here; non-Linux builds return `unsupported_platform` |

## Placement and ownership

The trusted Session process owns `ObserverClient` on a dedicated background
worker. The renderer consumes an application projection, never this crate's
endpoint configuration. The observer has no raw JSON request API. The crate has no process
launcher, no discovery of sockets or credentials, no signing code, and no
persistent state. It does not copy Agentd, a policy owner, or an operation
ledger.

The separate [ObjectiveStart transport](OBJECTIVE_TRANSPORT.md) accepts only the
original ingress shape and performs structural checks, not authentication.
It preserves raw issuer/source inputs, consumes one transport attempt, and
retains `SubmitUnknown` after any unresolved delivery. Its real local socket
tests use scripted fixtures and provide no original-owner admission evidence.
The separate original process probe uses a disposable explicitly enrolled test
issuer and the unchanged original Fleet/Supervisor/Agentd. Its admission,
durable-journal and restart assertions passed in the two actual process runs
linked above. Parser tests or successful compilation alone do not qualify
those assertions. Stopped-owner journal inspection is an isolated evidence
check, not an online product reconciliation service.

This observer performs host I/O outside the organ boundary. It is **not** an
implementation of `TrustedReadOnlyOrganV1`, whose handler must not perform I/O or
hold capabilities. A future organ can consume a bounded owner-produced snapshot;
an effect must still follow the original authority/operations owners and the
separate restricted OS adapter.

The host configuration must identify the expected Agent UUID, spawn generation,
and OS UID from a separately trusted supervisor record. Reusing values returned
by an arbitrary socket to configure that same socket would defeat identity
checking. The same configured UID, privileged host processes, and the Session
process remain in the host trust boundary. Socket permissions and `SO_PEERCRED`
do not authenticate a binary, defeat an attacker under the same UID, or sandbox
a renderer that is otherwise able to access the UDS through its OS credentials.
The Session must be launched with the intended process isolation and access
policy; this client is not a complete sandbox.

## Public API

```rust,ignore
let endpoint = EndpointConfig::new(socket_path, agent_uuid, generation, peer_uid)?;
let mut observer = ObserverClient::new(endpoint)?;
let observation = observer.poll(after_cursor, 16)?;
let known_run = observer.run_status("a-known-owner-run-id")?;
```

These methods block their calling worker. Calling them inside a Tokio runtime
returns `invalid_execution_context`. Keep one client per Session observer;
repeatedly creating new clients after timeouts would bypass the per-client
bound on outstanding metadata work. A poll has one five-second asynchronous
deadline for filesystem validation and all four socket exchanges. It returns
no partial successful observation. The Session must independently expire its
last-success timestamp so a stalled worker or host scheduler cannot leave a
green status indefinitely.

The filesystem job owns a one-slot permit until its actual syscalls finish.
Timing out the waiter does not interrupt a syscall. While that job remains
outstanding, later polls return `unavailable` without queuing more jobs. Client
drop does not wait for such a worker. The process may still contain that one
blocked job until the OS returns it.

Read [RUN.md](RUN.md) for reproducible commands, [CONTRACT.md](CONTRACT.md) for
wire and projection rules, and [UPSTREAM_CONTRACT.json](UPSTREAM_CONTRACT.json)
for the reviewed source hashes. Root `README.md` remains intentionally empty.
The optional feature's complete wire, typed outcomes and remaining owner
integration requirements are in [OBJECTIVE_TRANSPORT.md](OBJECTIVE_TRANSPORT.md).
The separately pinned history feature has its own complete development and
technical contract in [OBJECTIVE_HISTORY.md](OBJECTIVE_HISTORY.md).
The independent, default-off CPU history adapter is documented in
[CPU_DELIVERY.md](CPU_DELIVERY.md), including original outbox binding, transport
requirements and unresolved outcomes. It provides no device startup or discovery,
effect, retry, new K/D allocation, acknowledgement or retirement. It has no CLI or
UI entry, and the ordinary Session does not enable it.

The explicit Linux Shell signed-request flow is documented in
[`OBJECTIVE_INBOX.md`](../../support/ui/OBJECTIVE_INBOX.md). It reuses these
original ObjectiveStart/ObjectiveAdmission APIs, not the Notes/desktop FinalUse
effect protocol. Local drafts cannot manufacture signed requests.
