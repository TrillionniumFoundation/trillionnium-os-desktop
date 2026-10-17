# 固定原版 Hepta → 持续 Session 的真实六阶段运行

两轮真实运行均通过原版 Agentd 的 8 项进程/只读断言和持续 Session 的 8 项断言。`runtime-02` 使用保留的 R5 UI ELF，`runtime-03` 使用已完成新鲜度修复并真实重新编译的 GREEN03 UI ELF。每轮先让同一个 Session PID、instance 和 worker 贯穿 Starting、Running、Draining、旧 spawn 失效；然后显式建立绑定新 spawn 的 Session，验证恢复 Running 和受控 stop 后继续响应 IPC。Shell 的同进程/窗口及实际像素由[独立 Shell 归档](../../../../ui/evidence/2026-10-17-original-hepta-shell/README.md)提供。

## 实际尝试与源码

| 运行 | 时间（UTC） | 结果 | 实际执行来源 |
| --- | --- | --- | --- |
| `runtime-01` | 首次尝试，结束于 22:44:40 | failed；仅 Starting，0 ACK，等待真实 120 秒截止后 exit1 | 本地 `c50d7b9b688135a22ced2f7f3cbe21c3028d8e17`；同树远端 [`028b664b4717c4dffc03dc638fa3e9a5d7a0b52a`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/028b664b4717c4dffc03dc638fa3e9a5d7a0b52a) |
| `runtime-02` | 22:56:31–22:56:55 | passed；原版 8 + Session 8，6 phase / 6 ACK | 本地 `28843c6632fe63db6b3fecb4d05888e90976fd16`；同树远端 [`66dba7f40c2fa8fea2e7828ec2fd4db336bb681f`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/66dba7f40c2fa8fea2e7828ec2fd4db336bb681f)，tree `759c42b36d965174dc00a39b7f28e962ed667d85` |
| `runtime-03` | 22:59:44–23:00:08 | passed；原版 8 + Session 8，6 phase / 6 ACK | 本地 `145e94c364243789b88c23b1292f9d4d9ca9a0e9`；同树远端 [`299794f90d4557cec4ee9a7fc92c397031fced4f`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/299794f90d4557cec4ee9a7fc92c397031fced4f)，tree `98dee80a7ec855a84c777b350fed8ef675e31fc1` |

原版 Hepta 固定为 `f8c9419df6ddeb36ff8b522a50219981fb8d9345`，tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45`，原版锁 SHA256 `8354b4cbdf14389db7aa5508e2ed5b524fc2d4c4ea0ecb475955c933f8bea389`。运行前后均核对原版工作树干净、源码/锁/原版 Agentd ELF 不变。首轮失败原因来自 Shell 捕获判定器：原版 Starting 中合法发生 promotion readiness 与事件前进，旧判定器错误要求整份 health 相同；capture 没有写 ACK。原始失败收据没有被改成通过。`RUNTIME_SUMMARY.json` 另外记录归档时三轮私有运行目录均已不存在，不回写首轮原始失败收据。

## 两轮实际进程轨迹

| 身份 | 旧 UI `runtime-02` | 新 UI `runtime-03` |
| --- | --- | --- |
| 原版 Agentd PID | `615532 → 615755` | `616327 → 616535` |
| 原版 spawn | `1 → 5` | `1 → 5` |
| 第一 Session PID / worker TID | `615562 / 615564` | `616357 / 616359` |
| 第一 Session instance | `b4122eb42acae07a5d5b97c1c496e2fd` | `1726d69f559ede7d224e8bc0f12c282b` |
| 显式新 Session PID / worker TID | `615926 / 615929` | `616715 / 616717` |
| 显式新 Session instance | `b4b8c3aa629eeac9d5968a060d2b0559` | `7df3d71d043233ca8649ad3560f57432` |
| 原版重启后的旧绑定 | `stale / protocol_mismatch`，保留旧 PID、spawn1/current3 和 Draining 历史 | 同样拒绝跨 spawn 静默重绑并保留原历史 |
| 原版停止后的最后样本 | `stale / unavailable`，保留 Running/current6 | `stale / unavailable`，保留实际退出前采到的 Draining/current7 |

两种停止前的最后样本都符合原版真实生命周期；时序差异不能归因于 UI 新鲜度修复。失效阶段会再次观测，确认旧历史未清空、未把失败变成新的成功观测，并检查 Session 仍能响应。Shell 每轮保持同一进程和窗口，替换的是被显式信任的新 Session，而不是在旧 Session 中改写 spawn。

## 可追溯构建与协调边界

原版 Agentd ELF 来自[原版 native build03](../2026-10-17-native-agentd-build/README.md)；observer 和原版库 probe 来自[consumer build02](../2026-10-17-original-session-build/README.md)。运行并未重新构建这些三个 ELF，只有在 gate、两份 Rust probe 源码、observer 源码/manifest/lock/上游契约的 Git 对象逐项一致时才能复用。`consumer_source_reuse` 明确记录 `recompiled_for_runtime_source=false`。Session 与 ctl 另外核对各自 UI build receipt、UI 完整子树、A07 外部依赖闭包及实际 ELF 摘要；Shell 则在独立捕获收据中核对。旧四 UI ELF 保留不变，新 UI 构建及 RED/GREEN 见[新鲜度归档](../../../../ui/evidence/2026-10-17-observation-freshness/README.md)。

`helper-v2` 对应原始失败；`helper-v3` 在两轮通过前冻结，执行前后摘要一致。v3 的 abort 请求仅是测试协调：私有同 UID、`0600`、单链接、非符号链接、最多 1 KiB 的精确 JSON，只能让工具清理自己持有的进程。读取使用非阻塞打开后检查普通文件，避免 FIFO 先阻塞再验证。`helper-v3-guard-check-01` 保存实际 FIFO 拒绝和一次性自有子进程收到 TERM 并被 reap 的原始记录。它不是 Hepta 授权、phase ACK 或任意命令入口。

复跑参数、原版 Supervisor/Session 装配与断言见 [ORIGINAL_SESSION](../../ORIGINAL_SESSION.md) 和 [ORIGINAL_AGENTD](../../ORIGINAL_AGENTD.md)。ACK 是最多等待 120 秒的捕获协调信号，不能自身授予像素通过资格；必须同时查看 capture receipt、PNG 和人工复核。

## 归档与资格

`MANIFEST.json` 覆盖 52 个原始输入：426,152 原始字节、369,420 归档字节。每份输入均与原文件重新核对；gzip 解压回读摘要也一致。`RUNTIME_SUMMARY.json` 另提供三轮对照；本目录 `SHA256SUMS` 覆盖所有其他文件。原始 PID、路径、source、命令、phase、ACK、日志和失败原因均保留。该目录不保存 ELF、缓存或原版私有运行状态。

资格限于 Linux x86_64 host 中固定原版运行时与真实持续 Session 的只读连接。未提交 objective、调用模型、创建新 issuer/authority 或替换持久账本，也未执行设备效果。`TrustedReadOnlyOrganV1` 是只读 organ 合约，不是操作系统沙箱；Asterinas、Android guest、移动输入/显示、GPU 和物理设备控制仍须分别验收。
