# Rust桌面与应用协议

版本0.3。原生桌面以Rust实现，对话/任务/应用工作区是主界面，终端/日志只是任务内选项；恢复入口可以简化但不能代替日常UI。状态见STATUS。

## 1. 协议路线

原生Rust聊天/任务shell与compositor/session连接所有者分进程设计；后者承载Wayland客户端；X11程序通过按信任域分离的Xwayland接入；Android先以完整SurfaceFlinger显示面桥接，之后再拆逐应用窗口。

当前 [A10/A07 候选 #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157) 采用全 Rust `eframe = 0.31.1`（egui、glow、Wayland/X11），产出 Shell、Session、CLI 和 AppWindow 原生 ELF，产品代码尚未合入 main。R6 固定候选为 [`89aa8fa62d30b00259cb33174260c134edf1a70b`](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/commit/89aa8fa62d30b00259cb33174260c134edf1a70b)，tree `5fa4057019ee044ed9bc3337ae78d90496f8b923`。新 UI 实际构建来源为本地 `84f0070b6e7e01238a8dac6044748b15101c9497` / 同树远端 `88e9cdb124801c1d0fba5d2bb7e52a85a69a79f4`；新六阶段原版运行来源另为本地 `145e94c364243789b88c23b1292f9d4d9ca9a0e9` / 远端 `299794f90d4557cec4ee9a7fc92c397031fced4f`。源码、四程序构建结果、真实 Shell/Session/CLI 运行及后续证据提交分别记录，见 [R6 完整交付索引](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-r6/README.md)。这已经是 Rust 原生 Linux host UI；完整原生 Rust compositor、Asterinas 显示/输入和移动适配仍需实现与验收。

**R5 历史构建与输入基线：**`35f37910` 已以固定 Rust 1.88 完整构建 UI workspace 的四个新 ELF，实际执行 Shell 3 条和 AppWindow 1 条定向测试，并通过 workspace/all-targets Clippy `-D warnings` 与 fmt。非 root 调用者 UID 1000 的真实脚本对照使用同一个新 Session，验证三个外属 UID 路径拒绝及同 UID `0600` socket 正例；旧脚本 RED 是 fixture 准备权限问题，不是旧 Session 的漏洞复现。命令、hash、失败与结果分母见 [构建/UID/定向回归实录](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/83b6a514164e29d536c5d2d4e078e04da4eeddb1/tests/ui/evidence/2026-10-17-owner-input/README.md) 和 [STATUS](STATUS.md)。这些是 Linux host 结果，Asterinas 的完整显示/输入栈、原生 Rust compositor 和移动端移植仍未完成。

历史中文渲染源码为远端 `397db55e34a3a65d50635dec6a6aae7bcd573803` / 本地 `a601a1066f7b825ec62de57c64fbe94771429ba2`，tree `e244dbb04f482c15cfe6b6015197fbdce7238b83`。该次 Shell/AppWindow 的真实 Weston/Pixman 截图已人工确认中文标签与 TextEdit 提示可读，同期 [15 条定向测试与截图](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/661c958650e187cf677e4d5351d87e8bc8badbc5/tests/ui/evidence/2026-10-17-cjk-pixman/README.md) 保留自己的来源；其中 Session/CLI 复用旧 `865ecf3` ELF，不描述本轮新构建。更早完整 [137 项与 no-op Weston 布局](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/e743ee1a06956b51f86c16887f04cd4f518bcccd/tests/ui/evidence/2026-10-17-rust188-owner-sync) 仍只绑定 `865ecf381dc8ddb70470ee173add9bd3b4a6a29a`，R6 本地未重跑该完整集合；不同精确 HEAD 的后续 CI 计数另见 STATUS。workspace 声明的 `rust-version = 1.83` 也不代表实际验证过该最低版本。

Rust是原生组件要求，不强制把兼容用户态的Xwayland/Android系统重写Rust。原生UI、合成、兼容X服务和Android显示桥分别拥有职责，不能让UI直接成为任意设备owner。

## 2. 信任域与输入

Wayland/可信输入服务决定焦点。X11可信客户端之间有共享模型，不能把同一X server的全部客户端宣称相互严格隔离；按工作区/信任域分离Xwayland，禁止跨域任意输入抓取与共享。X SECURITY扩展是参考，不是免验证的万能隔离。[X.Org](SOURCES.md#x11)

授权提示与恢复控制具有系统可信来源；普通窗口不得伪造焦点或截取另一个工作区按键。执行桥/权限管理不暴露到任意应用可调试的同UID上下文。

R5 已验证的 Session 在打开运行路径时核对 runtime 目录、UI 子目录及 lock 的实际 owner UID，而不只检查 `0700`/`0600` 模式。真实 Linux host 回归分别拒绝三类外属 owner，保留同 UID socket 正例；这不授予新内核 CapSpace、跨工作区输入隔离或多用户产品资格。

## 3. 平台服务

明确提供或复用D-Bus/session、文件/截图portal、PipeWire等选定音频路径、字体/文本渲染、IME、通知、剪贴板和屏幕共享；选择组件前记录依赖与跨域访问边界。文件选择返回被选对象而非整个目录授权；drag/drop与clipboard需显式共享。Hepta已有自动化授权不隐含永久全屏录制、键盘监听或Android敏感环境数据许可。

当前共享 Rust 字体加载器由 Shell 和 AppWindow 使用，显式字体路径和 face index 是受信任的宿主配置；检查真实字形覆盖、格式和 32 MiB 大小上限，失败保留内建字体并显示原因，不悄悄改用另一个显式配置。实际合成截图验证了选定字体中的中文样本，不表示字体已随产品打包、全部 Unicode 可用或 IME 已接通。配置、失败语义与复跑入口见 [CJK_RENDERING](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/397db55e34a3a65d50635dec6a6aae7bcd573803/support/ui/CJK_RENDERING.md)。

## 4. 真实状态交互

任务详情显示真实运行模式、软件/硬件渲染、资源revision及观测时间；模型生成说明与执行状态分开。submitted、partial、unknown、cancel_requested和实际完成不能都显示为“成功”。执行中停止按钮报告请求与真实停止结果的区别。

Hepta/模型失效时仍可启动应用、切换窗口、使用文件和停止任务；shell重启不应带走compositor持有的独立应用连接；compositor崩溃和GPU reset另行验证，不承诺所有旧Wayland/X11应用都能无损重连。仅保留PID不等于窗口和未保存数据可恢复。

### 4.1 原版观测的可见新鲜度

Session 已收到回复不表示里面的原版样本仍新鲜。Shell 在实际绘制前，对原版 `sampled_unix_ms` 与本地单调 receipt 时钟分别检查年龄：两者均须 ≤7000ms，7001ms 已失效；未来时间、无法计算或缺失 receipt 不能保持 Observed。存在 observation 时 `sampled_unix_ms` 是必需的 u64；整个 `last_observation` 缺失则是没有成功历史，不能虚构成一个缺时间字段的样本。源码与定向复跑见 [OBSERVATION_FRESHNESS](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/ui/shell/OBSERVATION_FRESHNESS.md)。

有历史而过期时显示 **STALE / CURRENT STATE UNKNOWN**；没有历史时显示 **UNAVAILABLE / CURRENT STATE UNKNOWN**。保留完整最后成功观测和 Session 尝试时间，Session IPC 的连接状态单独报告。已有非 Observed 状态保留原诊断；Observed 因过期或无效时间降级时显示新的过期/时间错误诊断。随后合法的新 Snapshot 可以恢复 Observed，旧队列响应不能仅凭本地刚收到就变成新鲜。可见控件和 LayoutProbe 使用同一判定。

该缺陷已在真实接收队列与 egui 可见标题回归中复现：RED 为 1 pass / 5 intended fail，其中真实 egui 标题明确错误显示 OBSERVED；最终 GREEN 为 6 freshness + 2 layout 通过，严格 Clippy、fmt 与四程序构建通过。中间误复用旧缓存与测试 helper 的 Clippy 失败均保留，见 [完整 RED/GREEN 与编译来源](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-observation-freshness/README.md)。这是 synthetic 队列/控件回归；另以新二进制实际跑完整六阶段原版窗口，见 [13 张原图、快照、ACK 与逐图审查](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-original-hepta-shell/README.md)。旧 R5 四 ELF 在当时验证中保留，旧轮仅启动 Shell、Session 和 CLI；新旧六阶段都未启动 AppWindow，不据此扩展它的运行资格。

## 5. 验证

中文候选窗、焦点、键盘/触控、缩放/旋转、多窗口、跨域clipboard、通知、音频、文件选择、shell崩溃、Android输入坐标与复位后的buffer/fence逐项测试。初期一个Android完整显示面成功不计逐应用融合通过。Web端可共享Rust领域模型/协议，但不是本机桌面启动前提。

此前 Weston 13 软件像素环境只提供 text-input v1、没有 v3 或 `wl_seat`；锁定的 `winit 0.30.13` 客户端使用 text-input v3，该环境不能据已有中文像素升级真实输入法资格。R5 UI-05 在独立私有 Xvfb + IBus/libpinyin/XIM 环境实际完成 23 条输入/控制动作，namespace exit0。执行 harness 为本地 `02cf552485f899cfbb9cba7eeae663c7f0e8bb9c` / 同树远端 `698d1bf47fadbdd0fc18fad191b3bd5f9744101f`，生产客户端仍是 `35f37910` 的四个 ELF；[复跑方法、精确输入与来源校验](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/698d1bf47fadbdd0fc18fad191b3bd5f9744101f/support/ui/X11_IME.md) 已形成技术手册，[UI-05 实录与九张原始 PNG](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/2ec3e7ab3e472b19a350d309ee2d0338d62daeb3/tests/ui/evidence/2026-10-17-real-xim/README.md) 保留完整实际输出。XTEST 只注入 ASCII：Shell 的 `nihao` 经候选和空格确认后为 `你好`，Notes 的 `zhongwen` 为 `中文`，两个 Clipboard 均作精确且不同值断言。Shell 经正常 Save/Export 得到 `0600` JSON 草稿；Notes 跨窗焦点往返文本保留，Session 的 fenced 取消到达实际 cancelled 终态，自有进程清理完成。23 条动作与四条 Rust 定向回归分开计，XTEST 是虚拟输入。

UI-01/02 的真实失败继续保留；UI-03、UI-04、UI-05 各自保留执行 harness 与原始输出，不能将 UI-05 的严格差异文本结果转记给前两次。UI-03 的两个 Clipboard 同为 `你好`，不能独立排除 Notes 沿用旧值；UI-04 已实录两个不同值，但旧 harness 未严格断言 Shell Clipboard。UI-05 补齐两端精确断言与执行脚本字节绑定后重新执行。UI-03、UI-04、UI-05 的被动 IBus D-Bus trace 各自只有 29 次空 `UpdatePreeditText`，没有中文 `CommitText` 或逐条 winit `Event::Ime` 记录；ASCII 输入路径、PNG 与应用精确输出共同构成当前证据，不是完整 wire trace。UI-05 也没有解决候选窗定位：候选窗在 Shell 与 Notes 各自窗口的左下角，偏离 caret，仍为失败项；锁定的 [winit XIM PreeditCallbacks 路径](https://github.com/rust-windowing/winit/blob/e9809ef54b18499bb4f2cac945719ecc2a61061b/src/platform_impl/linux/x11/ime/context.rs#L344-L378)仍发送 spot 坐标，但源码注明 libX11 预编辑回调下定位不生效；[egui-winit 已转发 caret 位置](https://github.com/emilk/egui/blob/1669e52a7ccfc3489c1b0999b9ed48894a0b3887/crates/egui-winit/src/lib.rs#L866-L890)。该缺口和匹配输入法 profile 的后续工作须明确保留。此次 XIM 路径不授予 Wayland text-input v3、物理 seat、键盘/触控、GPU、Asterinas、移动端或完整 headless 生命周期资格。

## 6. 以 Hepta 为核心的 AI 原生 UI

R6 的实际可执行切片已是：固定原版 Hepta 的 A07 只读 client → Session 独立持续 worker → 同一个真实 Rust Shell 窗口。数据源为显式配置的 socket、AgentId、spawn generation 与 UID。旧 R5 和新 GREEN03 两轮分别完成 Starting、Running、Draining、旧 spawn 拒绝、显式新可信 Session 恢复和原版停止后的 stale；每轮原版 8 + Session 8 通过，保留 6 张成功 PNG，见 [三轮原版 / Session 运行](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/integration/hepta/evidence/2026-10-17-original-session-runtime/README.md) 与 [13 张原图、快照、ACK 与逐图审查](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/89aa8fa62d30b00259cb33174260c134edf1a70b/tests/ui/evidence/2026-10-17-original-hepta-shell/README.md)。新旧源码、ELF、同 Shell PID/XID 和人工验图分别绑定，不再把该链路仅描述为 scripted fixture。ARM 上另有持续 Session 的实际 8 + 8 运行，但该 CI 不启动 Shell。主机应用启动/取消仍由 Session 管理它自己创建的子进程，不等于 Hepta objective 已提交或设备效果已完成。

| 界面对象 | 事实来源与实现规则 | 当前接合状态 |
| --- | --- | --- |
| 连接与健康 | Health、实际 peer credentials、AgentId、PID、spawn/current generation；断连保留旧样本并明确 stale | 固定原版 → 持续 Session → 同一真实 Shell 两轮六阶段已通过；失去原版后保留历史并明确当前未知，Session IPC 仍可响应 |
| 能力与事件 | 固定协议白名单、有界数量/帧长/文本；能力标签不授予调用权；正常 Starting/Running/Draining 晋级保留同一来源历史 | 只读原版窗口链路已通过；保留有界字段、bidi/伪造换行过滤和合法生命周期晋级，能力显示不等于授予执行权限 |
| 用户意图与草稿 | Shell 收集并显示用户输入；执行前的草稿是本地数据；最终提交结果只能来自原有 Hepta owner | 已有本地草稿；可信 objective ingress adapter 尚未接通 |
| 任务与效果结果 | 复用 Hepta 已有 authority/operations owner 的真实状态；unknown、partial、cancel_requested 和终态分别显示 | 本桌面/A07 接入原版 durable K↔D、撤销、确认退役与 HOS2 效果链仍待闭合 |
| 窗口、输入与恢复 | Session/合成器持有进程和连接；新窗口要求 Session 在线、Running/非零 PID/已有 first layout，且已观察 socket epoch 严格大于启动 epoch。模型不可伪造焦点、资源权限或完成状态 | R5 UID、按钮规则及 UI-05 XIM 差异文本/焦点流程保留原有通过项；候选 caret 定位仍失败，Wayland 输入、GPU、跨域输入与移动显示仍待验收 |

Shell 的启动、新窗口、终止以及 `Save local draft`、`Export drafts to local file`、`Restore local export` 按钮只接受主指针激活。后面三个动作分别为本地内存保存、文件导出和恢复，不能统称为已经提交 Hepta 的任务。Terminal 的 `Run` 和 `Clear output` 源码也要求主指针。R5 focused_ 回归实际覆盖 Shell host effect、三个草稿按钮的 Enter/Space，以及 AppWindow `Run` 的 Enter；没有单独运行 `Clear output` 的真实输入验收。键盘导航、无障碍操作与真实 IME 的产品交互仍需各自的设计和实际验证。

下一条执行接口由 Hepta 既有、已配置的可信 issuer 提供原始认证封套，交给 `state_control → objective_runtime::ObjectiveRuntimeHost::submit` 路径；接受、发布和效果结果分别来自原有 owner。UI 不生成 authority epoch，不自签 objective，也不通过兼容 RunStart 绕开入口。带 socket I/O 的 client 与将来的效果 adapter 位于 `TrustedReadOnlyOrganV1` 外；这个只读 organ 合约不能充当操作系统沙箱。

实际原版入口为 [state_control 的 ObjectiveStart 分支](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state_control.rs#L206-L228) 调用 `objective_runtime` 中的 `ObjectiveRuntimeHost::submit`，不是未在原版模块表声明的 `objective_ingress.rs`。原 owner [先做 readiness、过期、签名认证及发布前检查，再持久发布，并重查最新 readiness/trust 与 runtime 准入](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/objective_runtime.rs#L206-L327)。请求可能送达后的断连或错误若缺少明确未接收证据，UI 必须保留 SubmitUnknown；[RunStatus](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/f8c9419df6ddeb36ff8b522a50219981fb8d9345/codex-rs/hepta-agentd/src/state_control.rs#L523-L531) 只查询内存中的 runs 投影，`null` 不证明未持久接收。不能因此换 run ID、自动重签或跨 spawn 重试。Admitted/Conflict 仅表示原版发布结果，explicit abstention 可以被接收而没有运行中的 run；真实设备完成仍需原效果 owner 的结果事实。

### 6.1 聊天与任务工作区

下一步主界面采用全 Rust 的聊天 / 任务 / 应用与文件工作区，参考 Robrix 的聊天组织方式；运行监控、终端和日志作为工作区内的页面。科幻视觉风格使用清晰的信息层级、颜色与动效表达实际状态，不能靠装饰性的模型回复伪造执行进度。当前 R6 完成的是原版运行信息接入与真实状态显示，完整工作区改版仍待下一切片交付。

聊天草稿应使用 typed 本地模型，并能引用实际任务和来源上下文。宿主任务引用由 `(session_instance, task_id)` 标识；Session 换代后保留旧引用为历史，不按同名 task_id 静默重绑。原版 Hepta 观测另以 AgentId / spawn 标识，不能把宿主 TaskRecord 命名为原版 objective。任务状态变化时间不等于观测时间：上下文卡是否仍为当前事实，应检查 Snapshot 的采样时间与本地 receipt 年龄。草稿保存、导出、恢复与原版接收 / 执行分别显示。

| 工作区对象 | 应显示的内容 | 事实 owner |
| --- | --- | --- |
| 聊天与本地草稿 | 用户文字、明确引用的任务/来源、未提交状态 | 本地 UI 草稿模型 |
| 宿主任务上下文 | 精确 Session/task identity、任务状态、观测时间、当前或历史 | 持续 Session 的 Snapshot |
| Hepta 上下文 | AgentId、spawn、健康/能力/事件、失效原因 | 固定原版只读协议 |
| 原版执行结果 | 原始提交身份、接收/不确定/运行/终态，以及实际效果 | 既有可信 issuer 与原 authority/operations/result owner |

### 6.2 可信意图入口与平台接合

先实现位于 `TrustedReadOnlyOrganV1` 外的单次有界 ObjectiveStart 适配器，接收既有可信 issuer 的原始封套。结构检查不替代原版认证；传输一旦可能发出请求而没有明确结果，就保留 SubmitUnknown 及原请求身份。通用错误可能发生在持久发布之后，不能当作“没有提交”；不自动换 ID、重签或跨 spawn 重发。该入口接通之前，Shell 的本地草稿和任务上下文不应发送 objective。

随后接既有持久结果 owner、durable K↔D、撤销与确认退役；cancel_requested 与真实停止分开显示。UI 不创建新的 authority/operations owner，也不直接持有设备效果权限。桌面、Web 和移动端可以共享 Rust 领域模型、类型与协议，但 compositor、显示/输入、IME、触控、缩放旋转和设备效果必须分别验收。字体、像素、交互、原版只读运行与设备执行各自交付真实记录；某项通过不等于整个原生系统完成。
