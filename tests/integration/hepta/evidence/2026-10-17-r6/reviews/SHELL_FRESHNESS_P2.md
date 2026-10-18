# P2：延迟送达的 Hepta Snapshot 会重新获得可见“新鲜”状态

## 固定源码与影响

桌面候选 `c0d5ee395cd76bcd29e8f1c912d048d19c97ce00`，tree `18bb74651753640289296ff872ee2db7e1bd6fe4`。

- `ui/shell/src/main.rs` Git blob `b6af04060cc1d99e8d5c24444894b2435ffb7ef1`，SHA256 `403a6ddfe640fc06408fcf817fabdbbec1b3ed869c6f7976cfd6bad6b1715c2f`。
- `ui/shell/src/hepta_panel.rs` Git blob `f9522af251803888556b110644ae30389b3cc822`，SHA256 `6720f716556bfaa4b94e018c468fb1140509083f515177d0d1e461352e5577e1`。

这是可见运行状态的真实性缺陷，优先级 P2。它不构成目标提交、设备效果或授权绕过。旧 R5 生产 ELF 保留该行为；六阶段正常轮询验收本身不会自动覆盖 UI 停顿和延迟响应场景。

## 源码证明

1. `Bridge::with_transport` 将响应写入最多 16 槽的 `outgoing` channel，真实 UI 线程稍后通过 `receive()` 消费。排队时间不携带在响应类型外的单调时间字段中。
2. `Desktop::receive()` 第 377–382 行接受 `Response::Snapshot`，将 `self.hepta` 设置为响应内 projection，同时无条件将 `hepta_last_snapshot` 设置为 `Instant::now()`。
3. `Desktop::update()` 第 944–950 行只在**刚设置的接收时刻**距今超过 7 秒时降级 `Observed`。它没有校验 `last_observation.sampled_unix_ms`。
4. 同一 update 的第 1017–1020 行将 projection 直接交给实际页面；`hepta_panel::status` 只根据 `connection == Observed` 绘制绿色状态文字。可见页面因此可能显示已经过期的样本为 `OBSERVED · READ ONLY`。
5. `LayoutProbe::emit_after_runtime_layout` 的第 51–65 行已经同时检查接收年龄与样本年龄，并拒绝未来样本。所以现有 marker 检查可通过，仍无法覆盖真实页面的该缺陷。

以上是代码路径分析；本报告不声称已经执行 UI 暂停实验。

## 无真实等待的确定性回归场景

使用同一实际显示前状态处理入口和可注入的测试时钟，避免 sleep：

| 场景 | 样本 Unix ms | 当前 Unix ms | 本地接收年龄 | 预期显示状态 |
| --- | ---: | ---: | ---: | --- |
| 排队旧 Snapshot 刚送达 | 10,000 | 18,001 | 0 ms | Stale，完整保留旧 observation |
| 时间恰好到边界 | 10,000 | 17,000 | 0 ms | Observed，与现有 7 秒规则一致 |
| 接收期限超过边界 | 18,001 | 18,001 | 7,001 ms | Stale |
| 未来样本／本地时钟后退 | 18,002 | 18,001 | 0 ms | Stale，不能按零年龄处理 |
| Observed 却无 observation | 缺失 | 18,001 | 0 ms | Unavailable，不制造历史值 |
| 后续真实新样本 | 18,001 | 18,001 | 0 ms | 恢复 Observed，来源身份按正常 Session 协议处理 |
| 既有 Stale / Unavailable / NotConfigured | 任意 | 任意 | 任意 | 保持已有状态与诊断，不重新升级 |

关键红例要模拟**延迟的旧响应被 receive 路径接受**，在同一帧绘制前断言已不是 Observed，并确认历史 observation 的 PID、spawn、事件和原采样时间完全保留。至少加一个真实 egui 状态文字／状态处理调用的验证，确保只修 LayoutProbe 或一个没有被实际页面调用的辅助函数无法让测试变绿。

推荐将显示前的“接收年龄 + 样本年龄”逻辑集中为一个小函数，在 `Desktop::update()` 的 `receive()` 后、任何 `status` 或 `runtime` 绘制前调用。缺失时间、未来时间和超过期限都降级；不要自动重写采样时间，也不要让诊断 helper 自行恢复为 Observed。后续正常 Snapshot 到达才有资格恢复。

## 交付边界

先完成冻结 R6 harness 与旧 R5 ELF 的六阶段实际运行，准确保留旧代码来源；随后修 Rust 源码、构建新 Shell、执行针对性回归，并用正确的新生产源码／ELF 来源重跑六阶段。不得把旧 ELF 的哈希或截图重新归属于修复后的源码。
