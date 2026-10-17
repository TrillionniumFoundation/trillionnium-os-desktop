# 精确候选 c0d5ee39：A10 与原版 Agentd CI 实际验收

本目录记录 **2026-10-17** 对已完成 GitHub Actions 结果、原始日志与实际下载文件的独立复核。它修正上一轮“最终候选 CI 排队”的时点状态；不把新开发的持续 Session / Shell 门禁记为已经执行。

## 固定来源

- 桌面源码：[`c0d5ee395cd76bcd29e8f1c912d048d19c97ce00`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/c0d5ee395cd76bcd29e8f1c912d048d19c97ce00)，完整 tree `18bb74651753640289296ff872ee2db7e1bd6fe4`。
- 原版 Hepta：[`f8c9419df6ddeb36ff8b522a50219981fb8d9345`](https://github.com/TrillionniumFoundation/hepta-private-ci/commit/f8c9419df6ddeb36ff8b522a50219981fb8d9345)，完整 tree `15c9d6ea07bf3832de82825a6cc1e8c958dd3d45`。运行前后源码与 Cargo.lock 保持干净。
- [source-bindings.json](source-bindings.json) 记录构建、门禁、封装和消费路径的 Git blob 与 SHA256；根 README 仍为 0 字节。日志内的实际 checkout 与 API 的 head SHA 一致。

## 两条 CI 的实际结果

| 执行 | 精确结果 | 当前证据范围 |
| --- | --- | --- |
| [A10 39044366490](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39044366490) | source guard 与 native job 均 success；实际 native job 在 18:11:57–18:14:27 UTC 执行 | Rust 构建与测试、真实主机 IPC／权限拒绝、Weston 首布局与 compositor 重启、独立可执行文件重放 |
| [ARM 39044366482](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39044366482) | original-agentd job success；15:42:44–16:05:11 UTC | 固定原版 Agentd + 原版 Supervisor/Fleet + 只读 CLI，共 8 项真实进程验收 |

### A10 的实际测试分母

| Rust suite | passed | ignored |
| --- | ---: | ---: |
| UI workspace | 81 | 2 |
| A07 observer | 17 | 0 |
| support/ui | 39 | 0 |
| tests/ui contracts | 8 | 0 |
| 合计 | **145** | **2** |

两条 ignored 均是 Shell / AppWindow 的真实字体覆盖测试，要求显式提供 `TRILL_UI_TEST_CJK_FONT`。它们不算通过。另有 6 条 process-guard 检查；ARM 前置步骤也重复执行这 6 条以及 3 条 manifest 检查，不能把重复执行计为新增用例。

实际 runtime-owner、双向 SO_PEERCRED、伪造 Session server 拒绝、8 个严格 IPC 负面帧、无显示 ELF 重放均通过。Weston 通过 Shell 和三个应用首布局，以及同一 Session 的 compositor 崩溃／重启后新客户端首布局；旧客户端仍存活不等于恢复原窗口。

[Session observer 记录](a10/session-observer-probe.json)和 [Hepta page 布局记录](a10/hepta-layout.json)明确使用 scripted UDS fixture。**本条 A10 CI 没有运行原版 Agentd、没有截图像素或实际中文输入资格。**X11 mapping 明确为 `NOT VERIFIED`，因为 runner 缺少可选 X11 工具。历史真实 XIM 的独立证据继续保留原来的构建与执行来源。

### ARM 原版实际进程验收

[report.json](arm/report.json)与[原版进程日志](arm/original_agentd_process_probe.log)包含：Starting、Running、有界 capabilities/events、缺失 run 读取、同进程 Draining、原版重启、旧 spawn 拒绝、受控停止。实际 spawn 为 1 → 5，PID 为 23837 → 23931；旧进程的 current generation 按 1 / 2 / 3 变化，新进程 Running 为 6。

每次查询由新的 observer CLI 发起，因此该次 ARM 运行的 **持续 Session、Shell、objective、model turn 与设备效果资格均未通过本门禁取得**。报告中的 objective / model / effect 字段均为 false。

## 实际下载文件与执行字节的关系

所有三个下载 ZIP 均核对 API 公布的字节数和 SHA256；内层 tar 采用流式读取，未把下载的 ELF 解包执行。[artifact-verification.json](artifact-verification.json)记录核验结论。

| 下载文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| A10 evidence ZIP | 17,397,212 | `7e5be6de0d4b2231b3015944cbb35f4a9ce6d1a51fda727dcb8771fbda8ce6f6` |
| 原版 Agentd evidence ZIP | 456,651 | `6d06b0f8ff338f9b76dd8568432f62c70074790259983630b644a1bd2ea14cfc` |
| 原版 Agentd ELF ZIP | 80,667,136 | `8296a3e573f375ca18d0fee262cee730098f230b841aa0c593f5aa7ad8aa4874` |

ARM 内三份实际 ELF64 little-endian AArch64 程序，逐一匹配运行报告及 [binary-manifest.json](arm/binary-manifest.json) 的哈希和大小。

A10 内四份实际 ELF64 x86_64 程序匹配 [SHA256SUMS](a10/SHA256SUMS) 与 [PROVENANCE.txt](a10/PROVENANCE.txt)。封装脚本对复制品执行 `strip --strip-debug`；它们通过独立无显示重放。真实 Session fixture／Wayland 执行报告记录的是未 strip 的 Session `6a4090c0…` 和 Shell `a482d599…`，不能把封装后的哈希直接当作图形执行哈希。两类字节均来自同一精确源码，区别保留在 [summary.json](summary.json)。

## 归档和未验证项

本目录保留原版小体积 evidence ZIP、可直接阅读的关键报告、API JSON、每个成员的哈希，以及三份原始 job log 的确定性 gzip 包。解压日志可恢复接收的 UTF-8 API 日志文本，保留 BOM 与最终换行；[raw-artifacts.json](raw-artifacts.json)同时记录压缩前后哈希。

17 MB / 80 MB 的包含 ELF 的 ZIP 未加入 Git；工作流 artifact 的实际到期日见 [A10 artifact 元数据](runs/a10-artifacts.json)与 [ARM artifact 元数据](runs/arm-artifacts.json)。本目录的报告、执行哈希、来源绑定和小证据 ZIP 不依赖这些大文件继续保留。

尚未被本目录证明的项目：原版 Agentd → 持续 Session → Shell 的联合运行；中文输入法完整体验；物理显示与 GPU；Asterinas 或移动设备；可信目标提交和设备效果。后续新门禁与新源码必须保留自己的运行记录，不能继承本次成功状态。
