# Hepta 的实际宿主接合

版本0.2。固定上游 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`；运行状态统一见 [STATUS](STATUS.md)。OS 层不复制第二套 Agent、Codex 主链或持久操作账本。

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

以上是来源映射，不是本项目已编译/调用的证明。核对来源：[宿主入口与限制](SOURCES.md#hepta-modules)。新增适配器文件尚不存在，不伪造调用点已合并。每一运行要报告二进制、构建 features、启动参数、装配 owner 与实际宣告能力。

## 2. 依赖必须先于 Hepta 闭环

先在原 Linux 固定真实 `codex-hepta-agentd`/App Server 和必要 owner 的 ELF、rootfs、锁/SQLite、futex、epoll、AF_UNIX、证书/NSS及 provider 配置。由实际 trace 得到最小系统依赖集，再移植到新内核。错误分类为 OS 行为缺失、Hepta 宿主装配缺失、外部 provider/设备前提，不通过放宽权限修复错误类别。

不要求一次启用所有可选 organ。声明的 profile 只覆盖实际装配路径；--help、mock HTTP、仅启动 daemon 都不算端到端。上游 native-host 文档保留的真实 provider 重启核对、设备容量等缺口继续如实记录。

## 3. 原生控制链与信任边界

用户目标 -> 现有目标/策略 owner -> 现有 Codex 工具主链 -> 最终内容授权 -> 受限 hepta-os 执行适配器 -> 新内核控制会话 -> 实际资源变更 -> 结果观测 -> 原操作 owner。

桥是受信任适配器，只有本工作区/任务资源封套内的能力，没有全部设备权限。内核对所有访问入口执行 [ABI 的统一对象规则](NATIVE_ABI.md)。高层授权不自动变成宿主 root；模型本身不持根句柄。桥受损时其已授权 envelope 仍可能被滥用，应将这一 TCB 风险纳入故障/攻击测试，而非宣称“内核校验权限”证明了意图正确。

构造 final-use canonical bytes 后保持不变；进程不再从可变模型字符串重建命令。内核先复制再核验，撤销与准入在资源对象短临界区线性化。无需将授权数据库、签名链或模型放进调度快速路径。

## 4. 三种版本不能混用

Hepta topology/body generation 冻结执行主链与资源 envelope；authority epoch 管理授权/撤销；OS resource revision 表示 envelope 内的一次实际预算安装。在既有 envelope 内调整 cap 不触发整套 topology 重建或 Agentd 重启；扩大权限或资源上界才走现有相应 owner 规则。

## 5. 身份和状态唯一所有者

| 身份/事实 | 来源 | 用途 |
| --- | --- | --- |
| run_id / objective / topology generation | 原 Hepta owner | 用户任务与策略上下文 |
| K=(principal,workspace,operation_id) 与 intent_digest | 原持久操作 owner | 跨进程/跨boot识别同一逻辑操作，先查K后比较摘要 |
| boot_id / process-start / exec_epoch / CapSpace | 内核 | 真实调用者与会话，不能用PID代替 |
| D=(boot,CapSpace,request_id) | 内核投递表 | 同次启动的写去重与copyout失败重取 |
| object generation / budget revision / queue generation | 实际内核或驱动 owner | 生效版本及完成关联 |

请求方可以提供关联ID，但不能自报授权主体、真实资源容量、完成结果或内核身份。摘要在记录中，不在查找键中。内核瞬时投递表不是第二份持久业务数据库。

## 6. 重试、恢复、取消

原 owner 在发出写请求前持久记录 K、意图和 D。同D同内容重取；同D不同内容冲突；进程或boot变化后保留K，未知效果禁止换ID重发。预算属于可观察的绝对状态设置，恢复时读取目标稳定身份、revision/状态，并区分“确认原安装发生”与“状态恰巧相同”；后者不能证明原操作完成。

revoke 关闭新准入但不取消已发生效果。停止桥/模型后 OS 恢复控制权回到本地 supervisor；独立应用不随桥生命周期退出。仅观察历史结果不恢复执行权限。详细双层状态、保留与容量规则以 NATIVE_ABI 为准。

## 7. 观测与控制器

关联 run/K -> D -> 内核对象/资源域 -> queue/completion，但仅按 read/observe 能力公开。统计包含采样时间、事件序号、丢失计数、revision、排队与执行时间。独立进程读相同计数只能减少自报错误，还须用工作负载完成量/实际数据核对计数正确性。

第一控制器试验配置：每1秒最多提案一次，观测年龄超过2秒或丢事件未恢复则不增加cap；每次变更不超过授权最大cap的10%，连续两次同向压力才改变，失败使用固定上次可用预算。此为待测保守实验参数，不是效果定理或最终默认。推理/观测本身单独计费；有界非AI反应式控制器是同等对照。

首个真实路径顺序：非AI客户端验证ABI -> 必需Linux依赖 -> 原Hepta实际profile -> 预算生效 -> revoke/kill/reboot。远程provider可用于早期主链实验但不得记为本地推理；后续另测本地CPU/GPU。
