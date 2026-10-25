# Hepta 的实际宿主接合

当前 Linux host 集成固定在 Hepta `7ea3df4e2ebaaa1052f8e01169ef0b5763beeda9` / tree `cf53a7c0e7ad57772238b614b673d176386ddfe5`，三处 Cargo 入口与四个 UI AccessKit patch 见[当前 source map](SOURCES.md#hepta-native-organ)。实际已有 [Session host](../services/hepta-session-host/README.md)、[原文本 adapter](../services/hepta-session-host/TEXT_SESSION.md) 和 [原 Makepad Shell 组合](../ui/shell/README.md#original-makepad-renderer)。它们借用原 ChatWorkspace、Root/Agentd、App Server 及 writer，不复制第二套 Agent、Codex 主链或持久操作账本。

[当前能力](CURRENT_CAPABILITIES.md)和 [v10/v11 scoped 收据](../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)记录已执行的包与过滤范围。默认原 SDK、独立 clipboard SDK、完整两仓 workspace、release、真实窗口、安装后生产运行和 Android 签名分别验收。下文保留版本0.4在 `44d98ca5501188b06c3df63fe57575d62c2ca8dd` 核查的 writer/ABI 映射与固定链接；它们是各自来源的合同对照，不改写为本轮运行收据。

## 1. 已核查源码到产品入口

| 位置 / 符号 | 已有职责 | 本项目接合 / 待补 |
| --- | --- | --- |
| `codex-rs/hepta-agentd/src/intelligence_ingress.rs` / `AgentdIntelligenceInvocationProviderV1::build` | 宿主从真实身份与 RunStartRecordV1 构建七 owner 输入；validate 校验 run、objective digest、authority epoch、generation | OS 资源观测由可信适配器送入原 owner；禁止 wire 自报当前 owner 输入 |
| `codex-rs/hepta-agentd/src/config.rs` / `with_intelligence_invocation_provider` | 安装宿主 provider；单有 runner 不表示完整产品 profile | 配置真实 provider、runner 和原状态 owners；普通 CLI 启动不算完成 |
| `codex-rs/hepta-agentd/src/objective_runtime.rs` / authenticated ObjectiveStart 路径 | 接入现有运行生命周期 | 保持 canonical 与 compatibility RunStart 分开，不用后者冒充规范链 |
| `codex-rs/hepta-agentd/src/lane_b_runtime.rs` / `state_control.rs` / `client.rs` | 生命周期、现有认证控制入口和客户端 | OS 适配器通过现有 composition 接合 |
| `codex-rs/hepta-contracts/src/final_use.rs` | 最终效果授权契约 | 授权不可变 OS 操作内容，不直接驱动寄存器 |
| `codex-rs/hepta-agentd/src/production_writer_host.rs` | 显式 durable writer 宿主接缝 | 正常启动不自动安装；只在实际所需产品 profile 装配 |
| `hepta-infer-worker --profile native-app-server` | 使用 owner 的 App Server provider；不是新模型主链 | 可作为真实模型路径观测，不能代替工具执行/OS资源接口 |

以上是原来源映射，不能单独当作运行证明。较早的[宿主入口与限制](SOURCES.md#hepta-modules)保留其研究基线；当前实际 adapter、命令和原 owner 合同从[本轮模块交接](agents/NATIVE_ORGAN_MODULE_HANDOFF.md)进入。每一运行仍要报告二进制、构建 features、启动参数、装配 owner 与实际宣告能力。

## 2. 依赖必须先于 Hepta 闭环

先在原 Linux 固定真实 `codex-hepta-agentd`/App Server 和必要 owner 的 ELF、rootfs、锁/SQLite、futex、epoll、AF_UNIX、证书/NSS及 provider 配置。由实际 trace 得到最小系统依赖集，再移植到新内核。错误分类为 OS 行为缺失、Hepta 宿主装配缺失、外部 provider/设备前提，不通过放宽权限修复错误类别。

不要求一次启用所有可选 organ。声明的 profile 只覆盖实际装配路径；--help、mock HTTP、仅启动 daemon 都不算端到端。上游 native-host 文档保留的真实 provider 重启核对、设备容量等缺口继续如实记录。

## 3. 原生控制链与信任边界

用户目标 -> 现有目标/策略 owner -> 现有 Codex 工具主链 -> 最终内容授权 -> 受限 hepta-os 执行适配器 -> 新内核控制会话 -> 实际资源变更 -> 结果观测 -> 原操作 owner。

桥是受信任适配器，只有本工作区/任务资源封套内的能力，没有全部设备权限。内核对所有访问入口执行 [ABI 的统一对象规则](NATIVE_ABI.md)。高层授权不自动变成宿主 root；模型本身不持根句柄。桥受损时其已授权 envelope 仍可能被滥用，应将这一 TCB 风险纳入故障/攻击测试，而非宣称“内核校验权限”证明了意图正确。

构造 final-use canonical bytes 后保持不变；进程不再从可变模型字符串重建命令。内核先复制再核验，撤销与准入在资源对象短临界区线性化。无需将授权数据库、签名链或模型放进调度快速路径。

## 4. 三种版本不能混用

Hepta topology/body generation 冻结执行主链与资源 envelope；authority epoch 管理授权/撤销；OS resource revision 表示 envelope 内的一次实际预算安装。在既有 envelope 内调整 cap 不触发整套 topology 重建或 Agentd 重启；扩大权限或资源上界才走现有相应 owner 规则。

## 5. 映射到实际持久操作结构

### 原宿主与唯一事务 owner

实际装配链为 `AgentdProductionOperationRuntimeConfig` → `AgentdProductionWriterHost` → `Arc<ProductionDurableWriter>` → 同一 `CognitiveStore` 中的 `LocalLeaseOutbox`。类型和调用分别位于 [production_writer_host.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/44d98ca5501188b06c3df63fe57575d62c2ca8dd/codex-rs/hepta-agentd/src/production_writer_host.rs) 与 [production_writer.rs](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/44d98ca5501188b06c3df63fe57575d62c2ca8dd/codex-rs/hepta-memory/src/production_writer.rs)。该配置显式接收原 authority/verifier、lease/generation、FinalUse、目的适配器和外部 grant provider；普通启动不会自行签发授权或制造 writer。

`hepta-operations` 的独立 `DurableOperationStore` 仍是该仓库已有 API，但不是上述 Agentd 生产路径实际使用的 journal。版本0.3把它的 `(scope_id, operation_id)` SQL 主键写成了生产宿主接合键，本节纠正这一映射；接合时不能再打开第二个 store 来迁就旧表述。

实际 SQL 是 [hepta-memory/migrations/0011_kernel_operations.sql](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/44d98ca5501188b06c3df63fe57575d62c2ca8dd/codex-rs/hepta-memory/migrations/0011_kernel_operations.sql)：`cognitive_operation_ledger` 在本库以 `operation_id` 为主键，`semantic_sha256` 唯一；`(lease_id, event_id)` 和 `(lease_id, outbox_id)` 唯一且外键关联原 event/outbox。记录不可更新或删除，原 dispatch claim 链继续负责尝试次数、进入边界、代际和 fence。K 的作用域与摘要必须按这个实际 owner 校验，不能把参考类型、SQL 键或内核 D 混成一个值。

| 实际 `ProductionDispatchRequest` 字段 | OS 接合规则 |
| --- | --- |
| `occurrence_key`、`idempotency_key` | 对应原逻辑 `operation_id`；进程或 boot 变化不能自动换 K 重放 |
| `operation_subject_id`、`operation_scope_sha256` | 原已认证主体和 scope 摘要；OS 不另建主体或 scope 数据库 |
| `operation_destination_id` | 原稳定目的身份；PID、fd、slot 只是调用时还须验证的句柄 |
| `payload_json`、`payload_sha256` | 原 outbox 中已持久化的最终操作字节及摘要，完整绑定 D、目标、cap 与资源前提 |
| `operation_semantic_sha256`、`operation_digest` | 分别沿用原语义意图和 FinalUse 请求摘要；适配器必须从字段重新核对，不能只相信自报 hash |
| `expected_predecessor_sha256` | **目的端自身状态的 CAS 预期**，不是“前一个 K 已终态”的依赖关系；D 的顺序和未决前驱必须由原 owner 另行明确表达 |
| `operation_policy_generation` | 原操作策略代际；与 OS resource revision、authority epoch、writer generation 分别校验 |
| `lease_id`、writer 的 generation/fencing token | 原唯一 writer 的持久所有权；不能当作改变逻辑操作身份的手段 |

### 效果入口和恢复规则

目的端实现原 `FinalUseProductionOutboxTarget`。HOS2 的有界同步 ioctl 必须在 `with_verified_use` 的同步 consumer-entry 闭包中完成，之后才返回 outcome future；把实际 ioctl 放到未 poll 的 future 或后台任务会失去该边界。该 API 的授权线性化点在进入消费者前，闭包执行时并不一直持有签发器锁，不能描述成跨 SQLite、授权服务与内核的一次原子事务。

投递前持久化同 K 的完整 D 和最终请求。复制回复失败、超时、进程退出或仅得到 `QueryDelivery::NotSeen` 都不能自动重发。只有实际同步入口拒绝分支能够证明本次尚未进入目的消费者；如需重新授权，必须在原 claim/event 事务内持久化与精确 Entered head、操作摘要和 fence 绑定的内部证明，并以新的外部授权重取原 K/D。证明提交丢失、owner 变化或并发终态先提交时保持未知。

`observe_terminal` 必须返回与原 D、目标和 revision 匹配的完整终态，普通传输 ACK、当前 cap 相同或裸 `Committed` 标志都不足以许可退役。原 owner 要先持久保存完整连续终态证据，再向持有原 history-ack 能力的恢复器产生退役许可；退役回复丢失后只核对或幂等重取同一前沿。不得伪造前驱终态、用空操作烧掉 D、创建第二 writer，或由 OS 适配器自行签发 FinalUse。

以上是实际宿主映射及接合验收要求。G1-d 的原生管理和内存历史 profile 见 [G1D_TRUSTED_CONTROL_PROFILE](agents/G1D_TRUSTED_CONTROL_PROFILE.md)；其恢复器内存确认不构成 Hepta SQLite 持久确认，真实 Hepta owner 接合与断电恢复仍须单独执行。

## 6. 历史核对、持续运行和目标收敛

原owner在投递前持久记录逻辑身份、意图与D。HOS2用CapSpace内有序sequence防止已退役的旧请求再次执行；同D变内容冲突，已记录拒绝也不可变成后来的执行。结果持久确认后原owner用RetireThrough确认连续终局，释放内核结果但保留拒绝迟到请求的前沿。1024限制是未退役窗口，不是终身写配额。

只读QueryDelivery的DeliveryView与原管理句柄分开，由可信init授予同scope观察者。原manager退出后仍可保留历史；boot重启或历史确实丢失则保持未知，不凭ReadUsage当前cap相同证明原执行。历史查询不恢复manage权。

旧效果不可确定时，先fence旧执行者、观察稳定资源对象、取得新授权，再建立明确的新目标收敛操作；旧K继续indeterminate。新目标达成与旧操作终态分别记录。若原owner的前驱规则不能表达该分离，必须修改和验证原owner接缝后才使用，不能另建账本或伪造前驱终态。绝对CPU预算可以评估此策略，不可逆设备动作不可照搬。

进程退出、cap=0和管理租约到期由独立OS恢复职责处理；不是在受限桥内再启动一套模型。用户明确暂停从可信意图记录识别，不从cap数值推断。迟到旧管理者请求在新授权之前先被fence。

## 7. 观测与控制器

关联 run/K -> D -> 内核对象/资源域 -> queue/completion，但仅按 read/observe 能力公开。统计包含采样时间、事件序号、丢失计数、revision、排队与执行时间。独立进程读相同计数只能减少自报错误，还须用工作负载完成量/实际数据核对计数正确性。

第一控制器试验配置：每1秒最多提案一次，观测年龄超过2秒或丢事件未恢复则不增加cap；每次变更不超过授权最大cap的10%，连续两次同向压力才改变，失败使用固定上次可用预算。此为待测保守实验参数，不是效果定理或最终默认。推理/观测本身单独计费；有界非AI反应式控制器是同等对照。

首个真实路径顺序：非AI客户端验证ABI -> 必需Linux依赖 -> 原Hepta实际profile -> 预算生效 -> revoke/kill/reboot。远程provider可用于早期主链实验但不得记为本地推理；后续另测本地CPU/GPU。

### 提交时再验证观测

开始推理时样本有效不意味着提交时仍有效。提交前重新检查内核初始时钟域的样本年龄、当前授权/资源revision及目标身份；过时提案丢弃或重新观察，不在队列中累积。CAS仅检测版本竞争，不证明负载当前性。ReadUsage尚不表达祖先节流/I/O/锁等待，缺乏可信原因时不自动把低进度解释为CPU不足；需要对应观测实现后才启用相关调优。对齐周期quota也不是滑动窗口或交互延迟保证。

## 只读 organ 不是设备效果适配器

固定Hepta的TrustedReadOnlyOrganV1禁止I/O和能力持有，不能在handle中调用HOS控制ioctl。观测由既有owner采集后投影为有界快照；效果通过原有authority/operations执行边界。图路由、driver摘要和Ready状态不授予效果权。详见[后端边界与实测](ASTERINAS_ORGAN_BACKEND.md)。
