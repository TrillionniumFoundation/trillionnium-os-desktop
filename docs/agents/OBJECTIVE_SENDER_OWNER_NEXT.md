# Objective sender：原持久 owner 的下一片实施设计

**状态：下一片设计，尚未实现或验收。** 本文说明如何在现有 Hepta owner 内补齐 Objective 发送前的持久保留、唯一发送许可和恢复查询。它没有新增生产 API、数据库迁移、issuer、发送入口或通过记录，也不把 Session 接口、host 单测、接收端入队或一次 SQLite commit 记作生产恢复完成。

## 1. 固定审查基线与当前缺口

原 Hepta 源码固定为 [6d6097da843f5831dfaf9cee3530da512d072a15](https://github.com/TrillionniumFoundation/hepta-private-ci/tree/6d6097da843f5831dfaf9cee3530da512d072a15)，tree 为 f722fbe5f24275c324089be720559a40901105f3。下文的 Hepta 文件行号均属于这个提交；实施时必须重新绑定实际候选 head/tree，不能沿用本页的历史源码身份或通过数字。

Desktop [#255](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/255) 的候选固定为 [940313d876481c6effc14ad783444e9e7b9d275a](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/940313d876481c6effc14ad783444e9e7b9d275a)，tree 为 2e94a12b8500ddca1d775712f0ffa7fbe86046d8。其 [OriginalObjectiveRequestOwner 端口](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/940313d876481c6effc14ad783444e9e7b9d275a/ui/session/src/objective_submission.rs#L34-L92) 要求保留原 bytes、身份和观察，但**不提供 production 实现**。其实现文件 Git blob 为 9b32303afffc2ecfb8395bc4b34b166d7f905f97。

当前准确结论：

- 原 Hepta 已有排他 CognitiveStore、生产 writer、原事务、append-only event/outbox、精确 current-cut 恢复和独立 RunStart journal。
- 原 AgentdClient 的 ObjectiveStart 直接进入 socket 发送，没有 sender retain-before-send 调用。
- Desktop #255 仅将“先由原 owner 保留，再允许一次发送”的依赖显式化；没有真实持久 owner 注入时，不能启用产品 Send。
- 还缺同一原 owner 内的 typed sender lifecycle、实际 production adapter、独立 current-cut 保留协议的接合，以及原包/真实 Agentd/崩溃恢复执行。下面的新类型和方法名称均为**提议**。

## 2. 已存在的能力：逐路径区分

| 原源码与位置 | 已存在的事实 | 不足以证明的事项 |
| --- | --- | --- |
| [AgentdClient::objective_start / objective_admission](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/src/client.rs#L136-L179)；[send](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/src/client.rs#L739-L785) | ObjectiveStart 构造请求后直接 send；send 序列化、连接并 write_all；请求计数器是客户端进程内计数。history 是独立只读方法。 | 没有发送前持久记录、跨进程唯一发送许可或可恢复的原 request bytes。进程内 request_id 不能单独充当持久业务身份。 |
| [objective_runtime::submit](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/src/objective_runtime.rs#L143-L284) | ObjectiveStart 接收后核原身份、签名、期限和 replay，再由原 learning.ledger owner 发布 RunStart；随后才进入相应运行接合。 | 这是接收后的认证和发布，不能补回客户端发出前已经遗失的请求。 |
| [objective_ingress::submit](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/src/objective_ingress.rs#L309-L346)；[objective_dispatch](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/src/objective_dispatch.rs#L1-L104) | 另一条 durable AuthBus ingress 路径在收到消息后调用 Evidence outbox，并由原 worker 交付。 | 不能把这条路径概括为所有 ObjectiveStart 的实现，更不能把接收端 outbox 记作 sender 的预先保留。 |
| [HeptaEvidenceStore::enqueue_authbus_message](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-evidence/src/authbus_outbox.rs#L18-L127)；[原 schema](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-evidence/migrations/0010_authbus_outbox.sql) | 同一 BEGIN IMMEDIATE 事务验证消息、消费 incoming replay sequence，并保留 claims/signature/payload；此 profile 的 payload 上限为 16,384 bytes。 | 这不是保留整个 sender 原始 JSON frame 的 API；不能预先消费接收方 replay frontier 来冒充客户端保留，也不能擅自将容量改成另一个 profile。 |
| [AuthBus replay frontier](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-evidence/src/authbus_recovery.rs#L420-L470)；[QuotaReservation](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-authbus/src/quota.rs#L41-L72) | 前者绑定 replay_sequences 与 retired_epochs；后者持久保存 quota、effect/dispatch digest 和结算状态。 | replay checkpoint、quota reservation 或 dispatch digest 都不是完整原 Objective request，也不是 RunStart 的 acknowledgement anchor。 |
| [ProductionDurableWriter::open_with_live_verifier / verify_current_authority](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-memory/src/production_writer.rs#L638-L671)；[prepare_operation](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-memory/src/production_writer.rs#L741-L767) | 原 writer 保留 live verifier；prepare_operation 可在原事务内保留完整 operation/event/outbox。 | prepare_operation 是现有 kernel-operation 语义，不是现成的 Objective sender admission API。仅调用它并不会自动得到本页要求的 sender 状态机。 |
| [LocalLeaseOutbox::admit_operation / transaction](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-memory/src/local_lease_outbox.rs#L1376-L1483)；[原 bytes 与绑定检查](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-memory/src/local_lease_outbox.rs#L1495-L1517)；[同事务 event/outbox/operation 写入](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-memory/src/local_lease_outbox.rs#L1611-L1722) | 原 owner 有可复用的事务、lease fence、不可变 payload、摘要与链式写入机制；payload_json 按 UTF-8 原 bytes 计算摘要，上限 65,536 bytes。 | 新 sender 领域必须有独立类型和路由边界。不能把普通 Objective 请求伪装成一个允许 FinalUse dispatcher 执行的 operation。 |
| [LocalLeaseOutbox::claim_dispatch](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-memory/src/local_lease_outbox.rs#L1823-L1849) | 现有 Queued → Indeterminate 是 effect 入口前的一次性 durable fence。 | Objective 请求是否发送、是否发布、是否运行，是另一种生命周期；不得直接借这个状态名和 FinalUse grant 表示 admission。 |
| [CognitiveRecoveryAnchor / requirement](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-memory/src/cognitive_store_recovery.rs#L55-L76)；[open_with_recovery](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-memory/src/cognitive_store_recovery.rs#L113-L177) | 原 host 必须提供独立认证且 CURRENT 的 owner/schema/state cut，另提供 authority lease/token/live verifier；原恢复入口取得排他 fence，在私有副本上恢复。 | 从待恢复数据库现场 capture 一个摘要不能认证该数据库；不能在 UI 再 open 一份 store，或把 lease 当作 current-cut。 |
| [RunStart receipt / anchor](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-learning-ledger/src/run_start.rs#L126-L148)；[原 append + sync](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-learning-ledger/src/run_start.rs#L375-L416)；[history 的精确匹配与 anchor 覆盖](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/src/objective_history.rs#L43-L88) | 原 journal 的 durable receipt 才产生 sequence/chain_digest；history 比较原认证字段，校验独立保留的 anchor 及其覆盖范围。 | 普通 admission reply、RunStatus、sender 自造 nonce 或现场 journal head 都不能补造这个 anchor。 |

## 3. 实施位置：复用一个原 owner，新增一个 sender 领域

**提议：**在 Hepta 原 CognitiveStore / ProductionDurableWriter 内增加 typed Objective sender 保留接口，由已经装配好的原 host 把该能力注入 Session 的端口。Session、Shell 和 renderer 不取得数据库路径、原 pool、issuer 私钥、CognitiveStore::open 或第二个 writer 构造器。

最小合理改动位置是 hepta-memory 的原 owner 事务层及 hepta-agentd 的 host 适配层：

1. 由原 ProductionDurableWriter 负责校验当前 owner、generation、lease、token、live verifier 和保护时钟，再进入原 SQLite BEGIN IMMEDIATE 事务。复用现有排他打开/恢复路径与事务基础设施，不把它复制进 Desktop。
2. 在同一 CognitiveStore schema 内增加不可变 sender request 与 append-only sender observation/fence 的 typed 领域，或提取原事务内通用 append 原语供它调用。具体 schema/method 名称须由 owning package 实现；本页不宣称已有 objective_sender 表或方法。
3. 不直接将新请求塞进现有可执行 FinalUse operation/outbox，再依靠 topic 字符串约定不要执行。若共享底层表，必须有编译期类型与持久 kind 区分，并由原读取/dispatch 路径拒绝跨领域解释。选择必须在 PR 中说明。
4. 新领域必须进入原 schema oracle、完整性审查和 CognitiveRecoveryAnchor 的逻辑状态覆盖。更新后的恢复不得遗漏 sender permit、取消、观察或 tombstone；旧 schema 的迁移/重新认证须走明确的原 owner 协议，不能自动丢弃不确定请求来通过检查。
5. 由原 host 导出同一已恢复 writer 的受限 typed sender 能力，再由 Desktop 接合层实现其本地 #255 OriginalObjectiveRequestOwner 端口，把调用转交该原能力。Hepta owning package 不反向依赖 Desktop；接合层只转换类型和错误，不拥有第二份状态。不得在每次 retain/reconcile 时按路径重开数据库，不得以 test-only owner、内存 map、UI 文件或新的 SQLite 数据库代替生产 owner。

原 prepare_operation/admit_operation 证明已有事务能力，但它们的公开语义不能直接当作新 sender API。建议的新方法职责是：保留并发放唯一发送许可、只读恢复原请求、追加原提交观察、读取/追加原 history witness、记录尚未发送的本地许可取消。命名和签名均属于下一片实现，不是当前可调用 API。

## 4. 必须保留的原始数据与身份

| 数据 | 提议的保留与验证规则 |
| --- | --- |
| 原签名 envelope bytes | 完整保留传入的原 UTF-8 JSON bytes，包括 source_envelope_json 与 signature；不得先 parse/serialize 后把重编码内容称作原 bytes。解析只用于结构和身份检查。 |
| raw digest 与 signed-body digest | 分别保存。raw digest 标识原 bytes；signed-body digest 遵循原 AuthBus typed-body canonicalization。两者用途不同，不能互换，也不能用摘要代替原 bytes。 |
| 原 Objective 身份 | 保留 issuer_id、key_epoch、message_id、sequence、expires_at_ms、原 body spawn、run_id、objective revision 及原 body 的全部绑定字段。恢复时逐字段与原 bytes 对应，禁止为了新 daemon generation 改写旧 body。 |
| sender/owner 身份 | 绑定原 store owner、原 writer generation/lease/fence 和实际持有许可的 host incarnation；后继 owner 只能按原恢复要求读取旧许可，不得自动发行新发送许可。 |
| 首次传输身份 | 保留原 agent_id、外层 spawn、request_id、期望 peer UID/PID，以及来自受信部署的 endpoint 绑定。UID/PID 是当次连接的身份输入，不是跨重启永久身份。 |
| 去重身份 | 用原 issuer/epoch/message/sequence 及完整原 payload 的绑定做原子唯一检查。仅以进程内 request_id 或 UI task id 为主键不够；同 key 改 bytes/owner/目标应拒绝，相同请求的第二个 facade 也不能得到新发送许可。 |
| 原请求到历史的关联 | 每条后续观察都引用同一不可变 request digest 和原 Objective 身份。后来的 query 可以使用独立认证的新外层 spawn/PID/request_id，但 query 中保留原签名 request。 |
| 有界存储 | 原 control frame 为 65,536 bytes，source 为 32 KiB，canonical body 为 48 KiB；见 [原 history 契约](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/OBJECTIVE_HISTORY.md#L41-L55)。raw、metadata、events 和总容量应分别设界，不能将 JSON 转义后变大的副本静默截断，也不能借 Evidence 的 16 KiB profile 吞掉较大请求。 |

保留原 bytes 本身不等于认证。原 issuer/签名由既有受信入口提供，原接收端继续执行签名、期限、spawn、profile 与 replay 检查。sender 不能生成替代签名或用 fixture credential 补齐缺失输入。历史匹配则不得因“现在已经过期或撤销”而删掉先前发布的原事实。

## 5. 提议的 typed sender lifecycle

以下状态只描述原请求的发送许可与观察，不表示 Objective 执行权，也不表示模型/设备效果。它们不复用 FinalUse 的 Queued/Indeterminate/Committed 作为 admission 状态。

| 提议状态 / 事实 | 持久含义 | 允许的下一步 |
| --- | --- | --- |
| OriginalRetained | 原 bytes、完整身份和 owner fence 已在原事务中保留；尚未发放任何发送许可的阶段如有实现，必须可证明它没有把 transport 暴露给调用者。 | 原子地发放一个唯一许可，或确定拒绝；不能先联网后补写。 |
| SendPermitIssued | 原 owner 已原子消费该请求唯一的发送机会，并返回不可克隆/不可重新取得的 opaque ticket。许可发放不证明发生了 write。 | 当前存活持有者最多调用一次原 transport；重启恢复一律没有新 send capability。 |
| SubmissionObserved | 保留原 transport 的 typed observation，包括 Admitted、Conflict、确定的本地拒绝或 SubmitUnknown；完整结果与原 request 对应。 | 只追加/幂等重交同一观察；不重发原 Objective。 |
| PublicationObserved | 通过原 owner history 获得并保留原 publication、认证字段和可验证的原 journal witness；compiled、explicit_abstain、conflict 分别保留。 | 继续独立读取当前 run/effect 状态。publication 不能被解释为执行完成。 |
| LocalPermitCancelled | 仅当前存活进程尚未消费的唯一本地 send permission 被撤销，并由原 owner 确认记录。 | 不能重新发放同一请求的许可；不自动发送 RunCancel。 |
| RecoveredUnknown | 许可已发放或崩溃点不明，缺少可靠的后续观察。 | 只查询同一原 request 的 history、原 run owner 或原取消接口；无自动重试。 |

为适配 #255 现有 retain_before_send 端口，**提议把 OriginalRetained 和 SendPermitIssued 的持久写入合在一次原 owner commit 中**，成功返回时才给唯一 ticket。该端口成功以后，即使进程尚未连接 socket 就崩溃，恢复也必须保守地视为未知，不能根据“没有 submission observation”发第二张许可。#255 的进程内 begin_send 栅栏不能替代跨进程的这份原 owner fence。

如果原 host 希望把保留与发放许可拆成两步，必须另外设计真正的 durable CAS claim API 并修改相应接合；不能悄悄假设 #255 已调用一个不存在的 begin-attempt 持久 API。

### 事务与返回顺序

1. 验证原 owner/current generation/live authority、原 endpoint 配置与输入界限，尚不连接 socket。
2. 在原事务中核唯一身份、保存 exact raw/metadata、写不可逆的唯一许可 fence；失败不得把 transport 暴露给 sender。
3. 完成原 owner 要求的 durable commit，并接合宿主独立 current-cut acknowledgement。只有该原协议允许对外确认后，才返回 opaque ticket。
4. 当前持有者调用一次原 transport；任何 panic、超时、partial write、响应丢失或记录失败都不重新发放许可。
5. 原 submission/history observation 只在同一原 owner 追加，完成其 durable acknowledgement 后才向 UI 标记 recorded。保留失败时可显式重交同一个 immutable observation，不能重新执行网络提交。

第三步是额外的真实集成要求：CognitiveStore 的 recovery_anchor 是只读 witness，**不会自动替宿主持久保存、认证或证明 currentness**。若原 host 还没有 sender 变更后独立保留 current-cut 的协议，该项就是阻塞。不能把数据库和“证明它当前”的 anchor 一起从同一可回滚位置读取后宣布恢复可信。

## 6. unknown、取消与 history anchor 的边界

### Unknown 只触发查询

原请求在许可发放后遇到断连、写入进度不明、daemon 退出、响应超时或 sender 崩溃，均保留 unknown。即使后来 RunStatus 返回 null、没有找到 publication，或 issuer 已过期，也不能推导从未接收、从未发布或可以安全重发。

原 history 的 unknown 原因与限制见 [OBJECTIVE_HISTORY.md](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/OBJECTIVE_HISTORY.md#L21-L49)。新的 unknown observation 不能清除此前已保留的 publication；最新查询结果、已知 publication、当前 run 状态和外部 effect 状态应分别投影。

### 本地取消与原 run 取消

本地取消仅撤销尚未使用的当前 send permission。取消记录若失败，UI 可以显示“本地许可已消费，持久记录未确认”，不能显示原任务已取消；重启后的 unknown 不能退回本地可取消的未发送状态。

已经进入 send 或已恢复为 unknown 后，若用户要求取消，必须调用原 run owner 的独立取消路径。原 [AgentdClient::run_cancel](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/src/client.rs#L404-L423) 接收 run_id、expected_revision 与 reason；其响应仍需原身份、当前 generation 和结果校验。sender 不从 request_id 推导 run_id，不把关闭窗口、清空草稿或 LocalPermitCancelled 转成 RunCancel，也不把取消请求的 ACK 当作已发生效果的撤销。

### Anchor 来自原 journal acknowledgement

RunStartAnchor 由原 journal 的 sequence 与 chain_digest 组成。ObjectiveStart 普通 [admission reply](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/6d6097da843f5831dfaf9cee3530da512d072a15/codex-rs/hepta-agentd/src/objective_runtime.rs#L321-L329) 没有 publication sequence，因此不能仅凭其中的 chain_digest 合成 anchor。

新请求发送前可以保留一个此前独立可信的 prefix anchor，也可以明确没有 anchor；不能声称此时已有尚未发生的本次 publication anchor。原 owner 的可信 history response 返回真实 publication sequence/chain 后，可以由同一 sender owner 追加该原 acknowledgement witness。anchor 绑定原 agent/journal/profile 及 exact request，不能只保存一个没有来源的数字。

恢复查询时保持原 signed body 不变，使用独立认证的新 outer endpoint。原 history 会检查 anchor 是否存在、链是否匹配、publication 是否处于被覆盖的前缀；比目标 publication 更早的 anchor 不会证明这个更晚的 publication。joint journal/anchor rollback 不由当前契约解决，见上述原文，部署和测试不得夸大。

## 7. 最小实施交付物

| 交付物 | 提议修改位置 | 必须呈现的证据 |
| --- | --- | --- |
| Typed sender domain 与原事务集成 | 原 hepta-memory owner/schema/完整性与 recovery 层 | request/fence/event 一致性、唯一约束、精确 raw、容量、无可执行 FinalUse 路由；新 schema/cut 的绑定。 |
| 原 host 的受限能力与 production adapter | 原 hepta-agentd host 导出能力；Desktop 接合层实现本地 #255 OriginalObjectiveRequestOwner | 依赖方向仍为 Desktop → Hepta；只复用原 recovered writer；live authority/保护时钟贯穿 retain/record/recovery；无新 pool、无 fallback owner。 |
| 独立 sender checkpoint 接合 | 已有受信宿主的 current-cut/acknowledgement 系统 | commit 到对外确认之间的失败协议、独立 witness 来源与保留结果、rollback 拒绝；没有现成协议就明确保持阻塞。 |
| Session 线性接合 | #255 端口与原 host 的实际实例注入 | 默认未装配不发送；原 request/endpoint/peer 身份贯穿；仅显式用户提交产生一次网络请求。 |
| 原包、真实 owner 与真实 daemon 验收 | Hepta owning-package tests 与 Desktop feature CI，随后同 source pair 原生 runner | 完整命令、source head/tree、原始日志、崩溃点、数据库与外部 witness 身份；真实失败保留。 |

生产 adapter 的构造器应只接收已经建立的原 owner 能力及受信输入，不能靠环境变量、数据库路径或 convenience constructor 自动获得 authority。原签名入口、实际 endpoint、current-cut/live verifier 和持久 owner 未装配齐时，产品 Send 继续不可用。

## 8. 最小正反与崩溃验收矩阵

以下均为**待执行的验收要求**。测试中允许明确标注的 fixture issuer/target 来检查有限代码路径，但它们不能成为生产信任来源，也不能替代真实 original-owner 与 native 资格。

| 场景 / 注入点 | 期望结果 | 不可省略的见证 |
| --- | --- | --- |
| 正向：原 request 保留后首次发送 | 原 commit 与许可 fence 先完成，后出现唯一一次原 socket write；exact bytes 不变。 | 原 owner 事务记录、独立 checkpoint、真实 socket 原字节及各自身份。 |
| 两进程并发保留同一请求 | 最多一个获得发送许可；另一方拒绝，不连接、不写。 | 两个实际进程、同一原 store、原唯一约束和两边日志。 |
| 相同 key 改 raw、签名、peer/agent、body spawn 或 run identity | 拒绝；原行和摘要不改。 | 逐字段负例、原 bytes 比较、原 store 前后 witness。 |
| 拒绝/过期/撤销的 writer 或失效保护时钟 | retain/record 失败；不发许可、不提交请求。 | 原 live verifier/clock 的实际拒绝，原记录未增加。 |
| 原 request 写入后、许可 fence 写入前事务失败 | 原事务整体未获确认；无可用 ticket、无网络字节。 | 原事务 fault point 与真实 rollback；不得仅测内存状态。 |
| 原 commit 后、ticket 返回前 sender 被杀 | 重启找到原记录；恢复为 unknown，不能再次保留并获得许可。 | 实际进程退出、原 durable record、恢复拒绝第二发送。 |
| ticket 返回后、socket connect/write 前被杀 | 同样恢复为 unknown；不从缺少 observation 推导“从未发送”。 | 同一持久请求与后继 owner，零重发。 |
| 实际 partial write、写超时或进程退出 | unknown；唯一许可保持消费。 | 原 transport 写进度/退出记录，第二连接被拒绝。 |
| 原 Agentd 已 durable publish、回复丢失 | sender unknown；原 history 可查到原 publication，不重新 compile/start。 | 原 Agentd/RunStart journal、丢回复点、exact original history 查询。 |
| 回复到达后、sender observation commit 前崩溃 | 原 request/许可保留；重启只读查询；没有响应的本地副本不被补造。 | 原 receiver 事实与 sender 崩溃 cut 分开保存。 |
| 观察保留返回失败，随后重交观察 | 只幂等写同一个观察；没有新 submit/history 网络 I/O，直到用户明确请求下一次只读查询。 | 原 observation identity、owner 记录与 socket 计数。 |
| unused 本地许可取消成功/持久记录失败 | 当前本地发送能力都被消费；只有原确认后标记 cancellation recorded；无 RunCancel。 | 原取消事件或失败收据、零发送与零原 run-cancel 请求。 |
| 已发送/已恢复 unknown 后请求本地取消 | 拒绝本地未发送取消；必要时走独立原 run owner。 | 阶段 fence；原 run_cancel 的 request/revision/响应另验。 |
| 新 owner spawn/PID 的 history 查询 | 原 signed request 和旧 body spawn 不变；outer endpoint 使用独立可信新身份。 | 旧原 bytes、受信新 peer、原 owner 正向历史响应。 |
| wrong/missing/rollback anchor、publication 在 anchor 之后 | 保持原 finite unknown/error；不清已有事实，不重发。 | 原 journal verify_anchor 结果，独立保留的原 witness。 |
| 后续 unknown 跟在先前 publication 之后 | 保留先前原 publication；最新观察仍可显示 unknown。 | 两条 append-only 观察及独立 UI 字段，不合并成单一成功/失败布尔值。 |
| sender store/current-cut 任一回滚，或两者来源无法独立认证 | 原恢复拒绝或保持 unavailable/unknown；不 capture 新 cut 认证旧备份。 | 原 exact-cut recovery 结果、独立 witness 来源、suspect source 未被改写。 |
| 同时打开第二 writer、路径换向或错误 owner/generation | 原 owner fence 拒绝；无新 ledger 和 fallback open。 | 真实文件/进程锁与原恢复负例。 |
| 容量、边界与大量未决请求 | 在明确上限拒绝新保留；不删未知请求或许可 tombstone 来释放容量并允许重发。 | 边界前后事务、保留量、原包资源记录。 |

至少按三层分别交付：原 owning package 的事务/恢复正反测试；真实 Agentd + 原 history 的传输/崩溃测试；固定 Desktop/Hepta/kernel source pair 的 native guest 执行。Linux host 或 SIGKILL 只证明对应过程，不能写成设备断电、硬件持久性或完整 G2 通过。

## 9. 合入与状态更新条件

Desktop #255 的纯 policy 测试和 scripted UDS 测试属于接口验证；其 [执行记录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/940313d876481c6effc14ad783444e9e7b9d275a/results/integration/2026-10-23-objective-session/local-execution.json) 必须按原记录解读，不能外推 original authentication、production owner 或 crash durability。feature 默认关闭时，CI 必须显式启用 objective-submission 编译和运行新模块。

下一片只有在真实 production adapter 已注入、上述原 owner 正反/崩溃路径有原始结果、完整 applicable CI 在最终 head 成功后，才可以关闭“sender durable retention implementation”这一项。原 issuer 部署、实际 run/model/device 效果、原生 F1/G2 与硬件验收仍各自按自身条件更新。

本页不改变任何 blocker 为完成，也不授权用新 UI ledger、fake ELF、重写 fleet 状态、削弱原 oracle 或缩小测试分母来取得通过。
