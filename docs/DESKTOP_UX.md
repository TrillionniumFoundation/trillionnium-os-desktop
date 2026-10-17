# Rust桌面与应用协议

版本0.3。原生桌面以Rust实现，对话/任务/应用工作区是主界面，终端/日志只是任务内选项；恢复入口可以简化但不能代替日常UI。状态见STATUS。

## 1. 协议路线

原生Rust聊天/任务shell与compositor/session连接所有者分进程设计；后者承载Wayland客户端；X11程序通过按信任域分离的Xwayland接入；Android先以完整SurfaceFlinger显示面桥接，之后再拆逐应用窗口。

当前 [A10/A07 候选 #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157) 采用 Rust `eframe = 0.31.1`（egui、glow、Wayland/X11），分别生成 Shell、Session、CLI 和 AppWindow 原生 ELF，尚未合入 main。本轮实际被测并发布的源码为 `1974d9a94037440da358253e1f449b395daa4b64` / 本地 `35f379101c0863027e971ccb91faf8da71cf929c`，tree `48433c4f1e55de53e8c298193765949996eb18a0`；保留 A10 owner `45552fbd` 和 main `eaabd20a` 的历史后，真实构建发现并修复了生产作用域缺失 `host_peer` 导入的编译错误。本轮最终固定候选为 [`c0d5ee395cd76bcd29e8f1c912d048d19c97ce00`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/c0d5ee395cd76bcd29e8f1c912d048d19c97ce00)，tree `18bb74651753640289296ff872ee2db7e1bd6fe4`；该文档/证据组合不替换实际构建、UI 输入和原版进程运行各自的来源。

`35f37910` 已以固定 Rust 1.88 完整构建 UI workspace 的四个新 ELF，实际执行 Shell 3 条和 AppWindow 1 条定向测试，并通过 workspace/all-targets Clippy `-D warnings` 与 fmt。非 root 调用者 UID 1000 的真实脚本对照使用同一个新 Session，验证三个外属 UID 路径拒绝及同 UID `0600` socket 正例；旧脚本 RED 是 fixture 准备权限问题，不是旧 Session 的漏洞复现。命令、hash、失败与结果分母见 [构建/UID/定向回归实录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/83b6a514164e29d536c5d2d4e078e04da4eeddb1/tests/ui/evidence/2026-10-17-owner-input/README.md) 和 [STATUS](STATUS.md)。这些是 Linux host 结果，Asterinas 的完整显示/输入栈、原生 Rust compositor 和移动端移植仍未完成。

历史中文渲染源码为远端 `397db55e34a3a65d50635dec6a6aae7bcd573803` / 本地 `a601a1066f7b825ec62de57c64fbe94771429ba2`，tree `e244dbb04f482c15cfe6b6015197fbdce7238b83`。该次 Shell/AppWindow 的真实 Weston/Pixman 截图已人工确认中文标签与 TextEdit 提示可读，同期 [15 条定向测试与截图](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/661c958650e187cf677e4d5351d87e8bc8badbc5/tests/ui/evidence/2026-10-17-cjk-pixman/README.md) 保留自己的来源；其中 Session/CLI 复用旧 `865ecf3` ELF，不描述本轮新构建。更早完整 [137 项与 no-op Weston 布局](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/e743ee1a06956b51f86c16887f04cd4f518bcccd/tests/ui/evidence/2026-10-17-rust188-owner-sync) 仍只绑定 `865ecf381dc8ddb70470ee173add9bd3b4a6a29a`，本轮未重跑该完整集合。workspace 声明的 `rust-version = 1.83` 也不代表实际验证过该最低版本。

Rust是原生组件要求，不强制把兼容用户态的Xwayland/Android系统重写Rust。原生UI、合成、兼容X服务和Android显示桥分别拥有职责，不能让UI直接成为任意设备owner。

## 2. 信任域与输入

Wayland/可信输入服务决定焦点。X11可信客户端之间有共享模型，不能把同一X server的全部客户端宣称相互严格隔离；按工作区/信任域分离Xwayland，禁止跨域任意输入抓取与共享。X SECURITY扩展是参考，不是免验证的万能隔离。[X.Org](SOURCES.md#x11)

授权提示与恢复控制具有系统可信来源；普通窗口不得伪造焦点或截取另一个工作区按键。执行桥/权限管理不暴露到任意应用可调试的同UID上下文。

本轮 Session 在打开运行路径时核对 runtime 目录、UI 子目录及 lock 的实际 owner UID，而不只检查 `0700`/`0600` 模式。真实 Linux host 回归分别拒绝三类外属 owner，保留同 UID socket 正例；这不授予新内核 CapSpace、跨工作区输入隔离或多用户产品资格。

## 3. 平台服务

明确提供或复用D-Bus/session、文件/截图portal、PipeWire等选定音频路径、字体/文本渲染、IME、通知、剪贴板和屏幕共享；选择组件前记录依赖与跨域访问边界。文件选择返回被选对象而非整个目录授权；drag/drop与clipboard需显式共享。Hepta已有自动化授权不隐含永久全屏录制、键盘监听或Android敏感环境数据许可。

当前共享 Rust 字体加载器由 Shell 和 AppWindow 使用，显式字体路径和 face index 是受信任的宿主配置；检查真实字形覆盖、格式和 32 MiB 大小上限，失败保留内建字体并显示原因，不悄悄改用另一个显式配置。实际合成截图验证了选定字体中的中文样本，不表示字体已随产品打包、全部 Unicode 可用或 IME 已接通。配置、失败语义与复跑入口见 [CJK_RENDERING](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/397db55e34a3a65d50635dec6a6aae7bcd573803/support/ui/CJK_RENDERING.md)。

## 4. 真实状态交互

任务详情显示真实运行模式、软件/硬件渲染、资源revision及观测时间；模型生成说明与执行状态分开。submitted、partial、unknown、cancel_requested和实际完成不能都显示为“成功”。执行中停止按钮报告请求与真实停止结果的区别。

Hepta/模型失效时仍可启动应用、切换窗口、使用文件和停止任务；shell重启不应带走compositor持有的独立应用连接；compositor崩溃和GPU reset另行验证，不承诺所有旧Wayland/X11应用都能无损重连。仅保留PID不等于窗口和未保存数据可恢复。

## 5. 验证

中文候选窗、焦点、键盘/触控、缩放/旋转、多窗口、跨域clipboard、通知、音频、文件选择、shell崩溃、Android输入坐标与复位后的buffer/fence逐项测试。初期一个Android完整显示面成功不计逐应用融合通过。Web端可共享Rust领域模型/协议，但不是本机桌面启动前提。

此前 Weston 13 软件像素环境只提供 text-input v1、没有 v3 或 `wl_seat`；锁定的 `winit 0.30.13` 客户端使用 text-input v3，该环境不能据已有中文像素升级真实输入法资格。本轮 UI-05 在独立私有 Xvfb + IBus/libpinyin/XIM 环境实际完成 23 条输入/控制动作，namespace exit0。执行 harness 为本地 `02cf552485f899cfbb9cba7eeae663c7f0e8bb9c` / 同树远端 `698d1bf47fadbdd0fc18fad191b3bd5f9744101f`，生产客户端仍是 `35f37910` 的四个 ELF；[复跑方法、精确输入与来源校验](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/698d1bf47fadbdd0fc18fad191b3bd5f9744101f/support/ui/X11_IME.md) 已形成技术手册，[UI-05 实录与九张原始 PNG](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/2ec3e7ab3e472b19a350d309ee2d0338d62daeb3/tests/ui/evidence/2026-10-17-real-xim/README.md) 保留完整实际输出。XTEST 只注入 ASCII：Shell 的 `nihao` 经候选和空格确认后为 `你好`，Notes 的 `zhongwen` 为 `中文`，两个 Clipboard 均作精确且不同值断言。Shell 经正常 Save/Export 得到 `0600` JSON 草稿；Notes 跨窗焦点往返文本保留，Session 的 fenced 取消到达实际 cancelled 终态，自有进程清理完成。23 条动作与四条 Rust 定向回归分开计，XTEST 是虚拟输入。

UI-01/02 的真实失败继续保留；UI-03、UI-04、UI-05 各自保留执行 harness 与原始输出，不能将 UI-05 的严格差异文本结果转记给前两次。UI-03 的两个 Clipboard 同为 `你好`，不能独立排除 Notes 沿用旧值；UI-04 已实录两个不同值，但旧 harness 未严格断言 Shell Clipboard。UI-05 补齐两端精确断言与执行脚本字节绑定后重新执行。UI-03、UI-04、UI-05 的被动 IBus D-Bus trace 各自只有 29 次空 `UpdatePreeditText`，没有中文 `CommitText` 或逐条 winit `Event::Ime` 记录；ASCII 输入路径、PNG 与应用精确输出共同构成当前证据，不是完整 wire trace。UI-05 也没有解决候选窗定位：候选窗在 Shell 与 Notes 各自窗口的左下角，偏离 caret，仍为失败项；锁定的 [winit XIM PreeditCallbacks 路径](https://github.com/rust-windowing/winit/blob/e9809ef54b18499bb4f2cac945719ecc2a61061b/src/platform_impl/linux/x11/ime/context.rs#L344-L378)仍发送 spot 坐标，但源码注明 libX11 预编辑回调下定位不生效；[egui-winit 已转发 caret 位置](https://github.com/emilk/egui/blob/1669e52a7ccfc3489c1b0999b9ed48894a0b3887/crates/egui-winit/src/lib.rs#L866-L890)。该缺口和匹配输入法 profile 的后续工作须明确保留。此次 XIM 路径不授予 Wayland text-input v3、物理 seat、键盘/触控、GPU、Asterinas、移动端或完整 headless 生命周期资格。

## 6. 以 Hepta 为核心的 AI 原生 UI

当前可执行切片是：固定原版协议的 A07 只读 client 在 Session 独立 worker 中轮询，Session 投影有界状态，Rust Shell 的 Hepta 页已有固定旧源码上的 widget layout 证据。数据源是明确配置的 socket、AgentId、spawn generation 与 UID；精确 `1974d9a9` 的[原版 Agentd ARM gate 与产物实录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/27fdf0a87b0bee3c13d1fccb876615aa5f27d9db/tests/integration/hepta/evidence/2026-10-17-original-agentd-arm/README.md) 已完成真实链接和 8 项进程/只读观测检查，三个 ARM64 ELF 的实际字节也已与执行收据交叉核验；连续 Session worker 与 Shell 的既有连接运行证据仍来自明确标识的 scripted fixture。此前原版外部 probe 已完成真实 Cargo metadata/锁核验与 API 编译检查，原版 Agentd 本体也通过单独的 Cargo check；本轮[原版源码复核](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/8d81d5546b50e5cfaa611e68cb3a11a7b3a731ce/tests/integration/hepta/LIVE_SOURCE_REVIEW.md)进一步确认真实启动与只读协议的装配边界。历史 Cargo check 保留自己的来源；本轮原版 gate 启动原版 Supervisor 管理的 Agentd，完成 Starting/Running/Draining、重启后旧 spawn 拒绝和受控停止。该 gate 每次启动新只读 CLI 观测，未连接持续 Session worker 或渲染 Hepta 页；持续 Session/原版 Agentd/Shell 链路仍待独立验收。中文软件像素与本轮四个 UI ELF 构建也不赋予 Hepta 页原版数据源资格。主机应用启动/取消仍由 Session 管理它自己创建的子进程，不等于 Hepta objective 已提交或设备效果已完成。

| 界面对象 | 事实来源与实现规则 | 当前接合状态 |
| --- | --- | --- |
| 连接与健康 | Health、实际 peer credentials、AgentId、PID、spawn/current generation；断连保留旧样本并明确 stale | 原版 Agentd → A07 CLI 的独立 ARM gate 已通过；A07 → 持续 Session → Rust Hepta 页仍只有 fixture/进程验证 |
| 能力与事件 | 固定协议白名单、有界数量/帧长/文本；能力标签不授予调用权；正常 Starting/Running/Draining 晋级保留同一来源历史 | 只读候选；已加入 bidi 控制字符和伪造换行过滤，保留正常中文、阿拉伯文与 Emoji |
| 用户意图与草稿 | Shell 收集并显示用户输入；执行前的草稿是本地数据；最终提交结果只能来自原有 Hepta owner | 已有本地草稿；可信 objective ingress adapter 尚未接通 |
| 任务与效果结果 | 复用 Hepta 已有 authority/operations owner 的真实状态；unknown、partial、cancel_requested 和终态分别显示 | 本桌面/A07 接入原版 durable K↔D、撤销、确认退役与 HOS2 效果链仍待闭合 |
| 窗口、输入与恢复 | Session/合成器持有进程和连接；新窗口要求 Session 在线、Running/非零 PID/已有 first layout，且已观察 socket epoch 严格大于启动 epoch。模型不可伪造焦点、资源权限或完成状态 | 本轮 UID、按钮规则及 UI-05 XIM 差异文本/焦点流程通过；候选 caret 定位仍失败，Wayland 输入、GPU、跨域输入与移动显示仍待验收 |

Shell 的启动、新窗口、终止以及 `Save local draft`、`Export drafts to local file`、`Restore local export` 按钮只接受主指针激活。后面三个动作分别为本地内存保存、文件导出和恢复，不能统称为已经提交 Hepta 的任务。Terminal 的 `Run` 和 `Clear output` 源码也要求主指针。本轮 focused_ 回归实际覆盖 Shell host effect、三个草稿按钮的 Enter/Space，以及 AppWindow `Run` 的 Enter；没有单独运行 `Clear output` 的真实输入验收。键盘导航、无障碍操作与真实 IME 的产品交互仍需各自的设计和实际验证。

下一条执行接口由 Hepta 既有、已配置的可信 issuer 提供原始认证封套，交给 `state_control → objective_runtime::ObjectiveRuntimeHost::submit` 路径；接受、发布和效果结果分别来自原有 owner。UI 不生成 authority epoch，不自签 objective，也不通过兼容 RunStart 绕开入口。带 socket I/O 的 client 与将来的效果 adapter 位于 `TrustedReadOnlyOrganV1` 外；这个只读 organ 合约不能充当操作系统沙箱。

实际原版入口为 [state_control 的 ObjectiveStart 分支](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state_control.rs#L206-L228) 调用 `objective_runtime` 中的 `ObjectiveRuntimeHost::submit`，不是未在原版模块表声明的 `objective_ingress.rs`。原 owner [先持久发布，再检查最新 trust 与 runtime 准入](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/objective_runtime.rs#L206-L327)。请求可能送达后的断连或错误若缺少明确未接收证据，UI 必须保留 SubmitUnknown；[RunStatus](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state_control.rs#L523-L531) 只查询内存中的 runs 投影，`null` 不证明未持久接收。不能因此换 run ID、自动重签或跨 spawn 重试。Admitted/Conflict 仅表示原版发布结果，explicit abstention 可以被接收而没有运行中的 run；真实设备完成仍需原效果 owner 的结果事实。

原生 AI UI 的下一步是将已通过的原版 Agentd 只读进程观测接到持续 Session worker 和 Rust Hepta 页，实际验证新鲜状态、断连、原 spawn 拒绝和显式新来源接合；随后接可信意图入口和既有持久结果 owner，由同一状态模型支持实际桌面/移动显示与输入。真实字体、像素和输入可独立改进；它们不授予执行权限。每一步单独交付源码、运行命令、故障语义和真实执行记录；控件布局、中文软件像素、原版 API 编译与原版运行各自陈述，不能升级为模型推理、设备操作或整个原生系统已完成。
