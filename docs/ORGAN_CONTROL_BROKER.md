# Organ control broker contract

版本：0.1（契约草案，非运行实现）

本文固定桌面/移动交互层与 Hepta、HOS2、内核设备 owner 的边界。它不能把 UI、只读 organ 或网络客户端提升为权限 owner。当前仓库没有完成该 broker；本文是后续 A05/A06/A07 和 A10/A08 实现的共同接合面。

## 1. 目标拓扑

```
Desktop/Mobile UI
    -> authenticated policy gateway
    -> Hepta Agentd + existing durable owners
    -> local authenticated control bridge
    -> A05 CapSpace/exec_epoch session
    -> A06/A07 resource and effect owners
    -> device/result observation
    -> original Hepta owner
```

- `TrustedReadOnlyOrganV1` 只消费有界快照；不得持有 I/O、capability、签名密钥或 Final-use，也不得调用 HOS2 ioctl。
- UI 和移动客户端只看到投影、提案、请求状态和终局收据。
- HOS2 是本机 ioctl ABI。它含用户虚拟地址和本机 transport 语义，禁止通过网络原样转发。
- broker 是唯一允许把远程/桌面意图转换为本机 HOS2 调用的进程；它不能创建第二个 Hepta ledger。

## 2. 身份与状态

Hepta 持久身份 K 与本次内核投递 D 永远分开：

| 名称 | 形态 | 所有者 | 用途 |
| --- | --- | --- | --- |
| K | `(scope_id, operation_id)` | 原 Hepta operations owner | 持久业务主键、去重和历史定位 |
| payload_digest | 独立 `Digest32` | 原 Hepta operations owner | 不可变语义与最终使用授权绑定；**不是 K 主键** |
| D | `(boot_id, cap_space_id, sequence)` | A05 控制会话 | 一次启动内的有序投递和结果槽 |
| authority_epoch | 单调代际 | authority/final-use owner | 撤销和授权边界 |
| body_generation | 组合代际 | CNS/Organ owner | 组件和路由一致性 |
| resource_revision | CAS 版本 | A06/resource owner | 预算和资源目标版本 |
| bridge_generation | broker 会话代际 | broker | 重启和旧连接 fence |

任何一个代际、scope、digest 或 revision 不匹配都必须拒绝或返回明确的 `unknown/indeterminate`；不能分配新 K 来掩盖旧效果未知，也不能把通知到达当作效果完成。

UI 公开状态至少区分：

- `draft`
- `submitted`
- `partial`
- `unknown`
- `cancel_requested`
- `terminal_success`
- `terminal_failure`
- `indeterminate`
- `retired`

只有原 Hepta owner 在独立确认 Final-use、实际效果和持久账本后，才能生成 `terminal_success`。

## 3. UI 投影协议

UI API 必须是版本化、无指针、带长度上限的 typed JSON/CBOR 或等价 wire。最小对象如下：

```json
{
  "schema": "organ.ui.v1",
  "scope_id": "stable-id",
  "client_request_id": "nonce",
  "operation_id": "stable-id",
  "payload_digest": "sha256",
  "expected_resource_revision": 12,
  "body_generation": 7,
  "authority_epoch": 31,
  "kind": "proposal|stop|observe",
  "payload": {}
}
```

规则：

1. `client_request_id` 只用于客户端重试去重，不能替代 K 或 D。
2. 相同 `(scope_id, operation_id)` 和全部已验证语义（包括 digest、前驱/目标、revision、authority/body generation）保持不变时，新的 `client_request_id` 可取得原收据；同 K 任一语义字段变化必须拒绝。nonce 不纳入持久 K。
3. UI 不得提交 CapSpace、boot_id、原始用户地址、Final-use、签名或设备 fd；禁止这些字段嵌套于任意 payload 层级或用 camelCase/连字符绕过。入站结构/标识/代际与序列化字节必须有界，不能信任可变原始 payload 引用。
4. `stop` 只表示停止请求；停止请求的结果仍需由 owner 观察并确认。
5. UI 必须显示请求状态与实际终局的区别，不能以模型文本、进程退出码或 WebSocket 通知宣称设备效果。

## 4. 传输和重连

- 桌面本地：broker 使用 credential-bound local IPC；A10 renderer 不获得 Agentd UDS 路径。
- 移动端/远程：只连接 broker 的 `wss` gateway，使用短期、scope-bound、可撤销的配对凭据、nonce 和 replay fence。禁止明文非 loopback `ws` 携带 bearer token。
- App Server 事件流必须使用 bounded queue。队列满时断开连接，客户端先重新初始化，再从持久 K/任务状态执行 pull + reconcile；不能自动重放非幂等效果。
- 新 boot、新 bridge generation 或 authority epoch 后，所有旧 D 和未确认缓存都视为 stale；恢复 mutation 前必须重新读取 durable owner 状态。
- 离线模式只允许本地草稿和只读缓存，不允许盲目排队设备效果。

## 5. 权限分层

broker 可以读取：

- 经过 scope/目的绑定的 runtime health、任务、观测和收据投影；
- 经过用户确认和 policy allowlist 的 intent。

broker 不可以自行：

- 签发或扩大 authority；
- 调用 `FinalUseAuthority` 取得未绑定的授权；
- 直接写 Hepta authoritative store；
- 直接控制任意设备、窗口、键盘、摄像头、麦克风或 GPU；
- 将 raw App Server 的 shell/process/filesystem 方法暴露给移动端或 renderer。

设备、窗口、输入、文件、音频、摄像头和 GPU 必须各自通过已有 owner/portal/driver 的窄适配器接入。HOS2 五个操作本身只覆盖预算和投递历史，不能被解释为通用设备控制 API。

## 6. 放行门槛

在以下条件全部满足前，broker 只能运行 read-only/shadow：

1. A05 真实 CapSpace、process-start、exec_epoch、fork/exec/SCM_RIGHTS、EFAULT 和 revoke 测试在当前 main exact SHA 通过。
2. A06 真实 scheduler accounting、退出结算、节流和父域约束通过；不能用 `cpu.max` 配置回读替代。
3. A07 在原 Hepta owner 中完成 K↔D、CAS/signature、Final-use、CNS、Supervisor fence、WAL/SQLite、reboot 和 ambiguous recovery。
4. Agentd 提供显式、版本化、认证的 UI bridge；不能把 registry 中的 ModulePort 当作已有实现。
5. Desktop/mobile UI 的 exact-head CI、权限、重连、离线、取消和未知效果回归通过。
6. 目标主机完成 64/256/1024/4096 Cell 的 CPU、RSS、吞吐、p95/p99、WAL 和故障恢复测量。

