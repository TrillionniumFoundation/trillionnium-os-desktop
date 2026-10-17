# Rust桌面与应用协议

版本0.3。原生桌面以Rust实现，对话/任务/应用工作区是主界面，终端/日志只是任务内选项；恢复入口可以简化但不能代替日常UI。状态见STATUS。

## 1. 协议路线

原生Rust聊天/任务shell与compositor/session连接所有者分进程设计；后者承载Wayland客户端；X11程序通过按信任域分离的Xwayland接入；Android先以完整SurfaceFlinger显示面桥接，之后再拆逐应用窗口。

当前 [A10/A07 候选 #157](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/157) 采用 Rust `eframe = 0.31.1`（egui、glow、Wayland/X11），分别生成 Shell、Session、CLI 和 AppWindow 原生 ELF，尚未合入 main；本轮最终固定候选为 `5beb3fab54fe7dd60072864276ece1ced38150ab`。此前完整 [137 项测试与 no-op Weston 布局](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/tree/e743ee1a06956b51f86c16887f04cd4f518bcccd/tests/ui/evidence/2026-10-17-rust188-owner-sync) 绑定远端 `865ecf381dc8ddb70470ee173add9bd3b4a6a29a`；后续源码不能继承该完整测试数量。workspace 声明的 `rust-version = 1.83` 不代表实际验证过该最低版本。

本轮中文渲染源码为远端 `397db55e34a3a65d50635dec6a6aae7bcd573803` / 本地 `a601a1066f7b825ec62de57c64fbe94771429ba2`，完整 tree 同为 `e244dbb04f482c15cfe6b6015197fbdce7238b83`。新的 Shell/AppWindow 在固定 Rust 1.88 下构建，真实 Weston/Pixman 的 Shell 和 Notes 截图已人工确认中文标签与 TextEdit 提示可读；同期 [15 条定向测试、两客户端严格 Clippy、fmt 与实际截图](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/661c958650e187cf677e4d5351d87e8bc8badbc5/tests/ui/evidence/2026-10-17-cjk-pixman/README.md) 已形成源码绑定实录。Session/CLI 仍使用旧 `865ecf3` ELF，具体 hash、命令和结果分母见 [STATUS](STATUS.md)。该切片运行在 Linux host，Asterinas 的完整显示/输入栈、原生 Rust compositor 和移动端移植仍未完成。

Rust是原生组件要求，不强制把兼容用户态的Xwayland/Android系统重写Rust。原生UI、合成、兼容X服务和Android显示桥分别拥有职责，不能让UI直接成为任意设备owner。

## 2. 信任域与输入

Wayland/可信输入服务决定焦点。X11可信客户端之间有共享模型，不能把同一X server的全部客户端宣称相互严格隔离；按工作区/信任域分离Xwayland，禁止跨域任意输入抓取与共享。X SECURITY扩展是参考，不是免验证的万能隔离。[X.Org](SOURCES.md#x11)

授权提示与恢复控制具有系统可信来源；普通窗口不得伪造焦点或截取另一个工作区按键。执行桥/权限管理不暴露到任意应用可调试的同UID上下文。

## 3. 平台服务

明确提供或复用D-Bus/session、文件/截图portal、PipeWire等选定音频路径、字体/文本渲染、IME、通知、剪贴板和屏幕共享；选择组件前记录依赖与跨域访问边界。文件选择返回被选对象而非整个目录授权；drag/drop与clipboard需显式共享。Hepta已有自动化授权不隐含永久全屏录制、键盘监听或Android敏感环境数据许可。

当前共享 Rust 字体加载器由 Shell 和 AppWindow 使用，显式字体路径和 face index 是受信任的宿主配置；检查真实字形覆盖、格式和 32 MiB 大小上限，失败保留内建字体并显示原因，不悄悄改用另一个显式配置。实际合成截图验证了选定字体中的中文样本，不表示字体已随产品打包、全部 Unicode 可用或 IME 已接通。配置、失败语义与复跑入口见 [CJK_RENDERING](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/397db55e34a3a65d50635dec6a6aae7bcd573803/support/ui/CJK_RENDERING.md)。

## 4. 真实状态交互

任务详情显示真实运行模式、软件/硬件渲染、资源revision及观测时间；模型生成说明与执行状态分开。submitted、partial、unknown、cancel_requested和实际完成不能都显示为“成功”。执行中停止按钮报告请求与真实停止结果的区别。

Hepta/模型失效时仍可启动应用、切换窗口、使用文件和停止任务；shell重启不应带走compositor持有的独立应用连接；compositor崩溃和GPU reset另行验证，不承诺所有旧Wayland/X11应用都能无损重连。仅保留PID不等于窗口和未保存数据可恢复。

## 5. 验证

中文候选窗、焦点、键盘/触控、缩放/旋转、多窗口、跨域clipboard、通知、音频、文件选择、shell崩溃、Android输入坐标与复位后的buffer/fence逐项测试。初期一个Android完整显示面成功不计逐应用融合通过。Web端可共享Rust领域模型/协议，但不是本机桌面启动前提。

本轮观察到 Weston 13 仅提供 text-input v1、没有 v3 或 `wl_seat`；锁定的 `winit 0.30.13` 客户端使用 text-input v3。已有真实软件像素和 synthetic egui 中文提交回归，仍须在支持匹配协议且有实际输入 seat 的合成器上验证预编辑、候选选择、提交、焦点切换与输入设备。像素验收也不授予物理 GPU/显示器资格；修改为 Pixman 的完整 headless 生命周期脚本尚未在该新源码上整套重跑。

## 6. 以 Hepta 为核心的 AI 原生 UI

当前可执行切片是：固定原版协议的 A07 只读 client 在 Session 独立 worker 中轮询，Session 投影有界状态，Rust Shell 的 Hepta 页已有固定旧源码上的 widget layout 证据。数据源是明确配置的 socket、AgentId、spawn generation 与 UID；原版 Agentd live gate 仍为 `not_run`，既有连接运行证据来自真实 Session/Shell 与明确标识的 scripted fixture。本轮原版外部 probe 已完成真实 Cargo metadata/锁核验与 API 编译检查，原版 Agentd 本体也通过单独的 Cargo check；尚未链接可执行文件或启动原版 daemon。中文截图是 Shell/Notes 的软件像素切片，也没有重新赋予 Hepta 页原版数据源资格。主机应用启动/取消仍由 Session 管理它自己创建的子进程，不等于 Hepta objective 已提交或设备效果已完成。

| 界面对象 | 事实来源与实现规则 | 当前接合状态 |
| --- | --- | --- |
| 连接与健康 | Health、实际 peer credentials、AgentId、PID、spawn/current generation；断连保留旧样本并明确 stale | A07 client → Session → Rust Hepta 页候选已有真实 fixture/进程验证 |
| 能力与事件 | 固定协议白名单、有界数量/帧长/文本；能力标签不授予调用权；正常 Starting/Running/Draining 晋级保留同一来源历史 | 只读候选；已加入 bidi 控制字符和伪造换行过滤，保留正常中文、阿拉伯文与 Emoji |
| 用户意图与草稿 | Shell 收集并显示用户输入；执行前的草稿是本地数据；最终提交结果只能来自原有 Hepta owner | 已有本地草稿；可信 objective ingress adapter 尚未接通 |
| 任务与效果结果 | 复用 Hepta 已有 authority/operations owner 的真实状态；unknown、partial、cancel_requested 和终态分别显示 | 本桌面/A07 接入原版 durable K↔D、撤销、确认退役与 HOS2 效果链仍待闭合 |
| 窗口、输入与恢复 | Session/合成器持有进程和连接；新窗口要求 Session 在线、Running/非零 PID/已有 first layout，且已观察 socket epoch 严格大于启动 epoch。模型不可伪造焦点、资源权限或完成状态 | Linux host owner 规则已做定向回归；中文软件像素已验证，真实 IME/GPU、跨域输入与移动显示仍待验收 |

Shell 的启动、新窗口和终止按钮只接受主指针激活，聚焦后的 Enter/Space 不触发这些进程效果；这保留候选输入与进程操作的明确边界。该规则已有定向测试，键盘导航、无障碍操作与真实 IME 的产品交互仍需独立设计和实际验证。

下一条执行接口必须接到 Hepta 原有可信 `AuthBusObjectiveIngress` / issuer / authority owner，携带原始认证封套并由该 owner 给出接受和结果事实。UI 不生成 authority epoch，不自签 objective，也不通过兼容 RunStart 绕开入口。带 socket I/O 的 client 与将来的效果 adapter 位于 `TrustedReadOnlyOrganV1` 外；这个只读 organ 合约不能充当操作系统沙箱。

原生 AI UI 的开发顺序由这些真实接口决定：先在原版 Agentd 上证明只读生命周期观测，再接可信意图入口和既有持久结果 owner，由同一状态模型支持实际桌面/移动显示与输入。真实字体、像素和输入可独立改进；它们不授予执行权限。每一步单独交付源码、运行命令、故障语义和真实执行记录；控件布局、中文软件像素、原版 API 编译与原版运行各自陈述，不能升级为模型推理、设备操作或整个原生系统已完成。
