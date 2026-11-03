# 原 Makepad App 与 Desktop Session 的最小接合方案

状态：**源码设计，尚未实现或执行**。这是后续独立增量，不属于当前冻结的 21 文件 presenter 候选。本方案不把现有 egui 渲染、原纯状态测试或源文件核验计为 Makepad 渲染资格。

## 1. 结论与本片边界

最小真实切片应在 **原 `hepta-robrix-ui::app::App` 内接收唯一的聊天状态所有者**，通过同一个原 `ImeRouter` 把真实 Makepad 事件送给原 widgets；Console 使用 Desktop 已有 Session worker 的只读结果。不能另写一个 App，也不能让 Desktop `SharedComposer` 和原 App 的默认 `ChatWorkspace` 同时演进。

原 `native_host::run_native` 不是这个接口。它要求外部既有 runtime/recovery owner 提供状态、readiness witness 和安全关闭；其 `NativeHostView` 没有聊天状态或 Session 事件。把 Desktop Session 的字符串实例 ID 填成它的 generation/digest，或用无操作的 `observe_rendered`/`on_exit` 冒充 owner，均不成立。

建议把第一片做成明确的 **Linux host、固定一个 Desktop 本地工作区、原 Makepad Chat/Console 渲染候选**。启动时选定原有 Personal/Research/Build 中一个槽，整个窗口期间不跨槽切换；其余槽及本地归档仍由唯一 Desktop 状态对象保留。原 App 内部的本地 conversation 切换仍走原 presenter。这是可以独立编译、运行、否证的小片，不等于三个工作区的完整功能迁移、生产发送、裸机显示后端、Web/移动端或可访问性完成。

固定本地工作区不是永久设计。第 7 节给出恢复运行时跨工作区切换前必须完成的输入绑定；直接把三个原 `ChatWorkspace` 轮换成一个同名字段，会漏掉这一问题。

## 2. 已核验的实际来源

| 项目 | 固定身份 | 本次核验 |
|---|---|---|
| 原 Hepta #3067 | commit `56630b12b8a4c69fff2c47b95b36d88a7389c39f`；tree `15ff893b92898185ea709e847b244e4d66ae2bf4` | 25 个源码/清单文件逐个对 Git blob；原全树 Rust `NativeHost` 引用共 12 行，只有声明和 renderer 使用，没有实现或外部调用 |
| Desktop #251 | commit `64736996d310d597ffba513ee109264cd5f5f83f`；tree `363700005afb52d2ac88aab709c3e0d0f78bcc0a` | 9 个 Session/core/Shell/broker 原文件逐个对固定 UI tree blob |
| 当前共享 presenter 候选 | 同一固定 Hepta 两个 Git package；原 Makepad `ui` feature 关闭 | 21 产品文件与冻结 review manifest 相同；6 依赖文件未变；当前 UI lock 不含 Makepad package |
| Makepad 原 pin | `337566c8b25d47f7e4fff6a202157b65bf183330` | 从原 Cargo manifest/lock 核对；本轮没有获取 Makepad 源或编译 renderer |

具体命令、退出状态、文件 Git blob/SHA-256、固定 URL 和逐字源码副本在 [review-v2.json](review-v2.json) 及 `verified-upstream/`。它的 SHA-256 为 `097e17914894a933dc0a0de77db81c2853b900e04e1339fb4366c1f35e19bcb0`。脚本实际 exit 0 只表示上述源码检查通过。

### 关键现成接口

| 来源 | 实际行为 | 后续使用方式 |
|---|---|---|
| [原 App:43–56、118–136](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/56630b12b8a4c69fff2c47b95b36d88a7389c39f/apps/hepta-control-ui/rust/robrix-ui/src/app.rs#L43-L56) | 私有 `ChatWorkspace` 和私有 `ImeRouter`；原 widget 注册与实际事件分发 | 修改这个原 App 的状态来源，保留它和整个注册/dispatch 路径 |
| [NativeHost:65–93](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/56630b12b8a4c69fff2c47b95b36d88a7389c39f/apps/hepta-control-ui/rust/robrix-ui/src/native_host/mod.rs#L65-L93) | 状态、渲染 witness、关闭，不提供聊天组合 | 原 owner 模式保留；新的只读 presentation 模式不伪造它 |
| [run_native:30–68](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/56630b12b8a4c69fff2c47b95b36d88a7389c39f/apps/hepta-control-ui/rust/robrix-ui/src/native_host/render.rs#L30-L68) | Linux runner；一次资源回调、原 App 启动、一次 host 采用 | 共用单事件循环启动与资源入口；不能创建第二个平台窗口循环 |
| [ImeRouter:25–37、89–96、184–243](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/56630b12b8a4c69fff2c47b95b36d88a7389c39f/apps/hepta-control-ui/rust/robrix-ui/src/ime_router.rs#L25-L37) | 真实 TextInput composition/epoch、pointer capture、候选键过滤、输入法期间冻结布局 | 继续只由原 App 调用；第一片固定本地工作区不增加另一套 IME policy |
| [原 HomeScreen:119–154](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/56630b12b8a4c69fff2c47b95b36d88a7389c39f/apps/hepta-control-ui/rust/robrix-ui/src/robrix/home.rs#L119-L154) | 原 widgets 经 `Scope` 借用 `ChatWorkspace`；Console 从私有 `RuntimeDisplay` 读文本 | 复用同一 Console widget；在原包内增加实际 native observation 更新入口 |
| [Desktop Bridge:92–160](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/64736996d310d597ffba513ee109264cd5f5f83f/ui/shell/src/main.rs#L92-L160) | 8 action / 1 coalesced poll / 16 reply 的原 worker；socket 工作在线程，原接收时间在入队前记录 | 原样抽取复用，不写新 transport，不在 UI 出队时刷新观测年龄 |
| [Desktop receive:344–448](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/64736996d310d597ffba513ee109264cd5f5f83f/ui/shell/src/main.rs#L344-L448) | 原 Session identity、完整 snapshot、不可重新绑定的 task/history、原收据时钟 | 提取 renderer 无关状态更新，再供 egui/Makepad 使用同一实现 |
| [core::request_at:428–445](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/64736996d310d597ffba513ee109264cd5f5f83f/ui/core/src/lib.rs#L428-L445) | 原同 UID 校验、bounded frame、原 `Request/Response` | 保留；只有原 worker 调它，原 App 不直接持有 socket 地址 |
| [原 Session:486–525](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/blob/64736996d310d597ffba513ee109264cd5f5f83f/ui/session/src/main.rs#L486-L525) | 既有 Snapshot/Launch/Cancel 和 expected_instance fence | Session 进程/协议/原 broker 不因更换 renderer 而重写 |

原 [MAIN_INTEGRATION.md:34、90](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/56630b12b8a4c69fff2c47b95b36d88a7389c39f/apps/hepta-control-ui/MAIN_INTEGRATION.md#L34) 明确没有导入 product native host。不能从旧文档的历史构建推断 #3067 已安装宿主。

## 3. 在原包新增的实际组合边界

以下代码是**拟新增 API 的签名设计**，不是当前包已经提供的方法。实施必须在原 Hepta 包完成，再由 Desktop Git pin 指向该提交；不在 Desktop 复制这些类型或原 App。

```rust
// New in original hepta-robrix-ui, behind an explicit native presentation feature.
// All methods run on the UI thread. No signer, authority or operation port.
pub trait NativeChatComposition {
    fn workspace(&self) -> &ChatWorkspace;
    fn workspace_mut(&mut self) -> &mut ChatWorkspace;

    fn set_waker(&mut self, wake: Arc<dyn Fn() + Send + Sync>);
    fn poll_console(&mut self) -> NativeConsoleObservation;
    fn request_refresh(&mut self); // only coalesces an existing read-only poll
    fn on_ui_exit(&mut self);      // closes UI worker, never cancels a Hepta run
}

pub struct NativeConsoleObservation {
    // Display-only text already produced from the original Session reducer.
    // Explicitly bounded by the original package before widget setters.
    pub text: String,
    pub refresh_pending: bool,
}

pub fn run_native_presentation(
    composition: Box<dyn NativeChatComposition>,
    resources: Box<dyn FnOnce(&mut Cx)>,
) -> Result<(), PresentationLoopError>;
```

这不是只留下 trait 的交付。与原包改变同片验证的 Desktop 实现必须有以下具体映射：

```rust
impl NativeChatComposition for DesktopNativePresentation {
    fn workspace(&self) -> &ChatWorkspace {
        self.state.drafts.composer(self.fixed_workspace).original_workspace()
    }

    fn workspace_mut(&mut self) -> &mut ChatWorkspace {
        self.state.drafts.composer_mut(self.fixed_workspace)
            .original_workspace_mut()
    }

    fn set_waker(&mut self, wake: Arc<dyn Fn() + Send + Sync>) {
        self.bridge.set_waker(wake);
    }

    fn poll_console(&mut self) -> NativeConsoleObservation {
        // Same extracted receive_and_refresh logic, with original receipt clocks.
        self.state.receive_and_refresh(&self.bridge);
        self.state.console_observation()
    }

    fn request_refresh(&mut self) {
        self.bridge.poll();
    }

    fn on_ui_exit(&mut self) {
        self.bridge.close_ui_client();
    }
}
```

这里 `DesktopNativePresentation`、`original_workspace[_mut]`、`set_waker`、`console_observation`、`close_ui_client` 和提取后的 reducer 也都是**要实施的具体改点**，不是已有 API。`original_workspace[_mut]` 仅在新 renderer feature 下暴露给可信原 renderer；当前 presenter feature 的窄 API 与关闭默认值保持原状。更宽的借用并不提供 SourceEnvelope、签名、Agentd socket 或 owner handle。

### App 内部只保留一个状态来源

把原 `App.workspace` 改为内部 `ChatSource`：

```rust
enum ChatSource {
    Standalone(ChatWorkspace),
    Embedded(Box<dyn NativeChatComposition>),
}
```

原 App 通过 `ChatSource::workspace[_mut]` 取得同一个原类型。原 `ImeRouter` 仍在 App 中，`dispatch(cx, &self.ui, event, chat.workspace_mut())` 仍是唯一事件入口。`Standalone` 用于现有 Web/独立预览；`Embedded` 用于本次 Desktop 候选。不要同时保留两个可编辑字段，也不要用后台线程同步两个草稿副本。

采用必须发生在原 `AppMain::after_new_from_script` 这个既有生命周期入口、第一次 event/draw 之前；使用一次 `Option::take` 领取 composition。实施可把内部未初始化态存成 `Option<ChatSource>`，使内嵌模式根本不创建第二个默认草稿。原 `ui-fixtures` 初始化同样移动到这个确定入口，保持独立预览模式原数据；内嵌 composition 与 fixtures 同时启用必须明确拒绝，不能覆盖真实草稿。

原启动设置应使用一个内部 mode enum，所有模式共用原单线程 loop admission/resource callback：

- `OwnerHost`：现有 `run_native`，继续遵守真实 `NativeHost` 的 witness/关闭规则。
- `Presentation`：本设计的 composition；没有 `NativeViewIdentity`、readiness ACK 或 owner shutdown，正常关闭只退出 UI。

不能用 `NativeHost` 的空实现包装后一种模式。`PresentationLoopError` 必须说明 renderer 初始化/循环失败；正常 UI 退出也不证明任何 runtime 操作、Owner ACK 或任务完成。

## 4. Desktop 的提取范围与实例所有权

先把既有代码**移动**到 renderer 无关模块，不复制：

| 现位置 | 提取目标 | 保留的不变量 |
|---|---|---|
| Shell main 的 `Bridge`、`BridgeReply` 与队列测试 | `ui/shell/src/session_bridge.rs` | 原 queue caps、poll 合并、动作优先、接收时间、单 worker、原 `core::request` |
| `Desktop::receive/receive_and_refresh_hepta`、相关状态字段 | `ui/shell/src/session_projection.rs` | 完整 Snapshot 才能更新 live card；generation 改变失效；不能把出队时间当收到时间 |
| `RuntimeReceiptClock` / `RunReceiptClock` 的无渲染部分 | 同一 projection 模块 | 不从旧样本、保存引文或迟到响应更新时效 |
| DraftBook/Composer/归档/Context 的非 egui 方法 | `ui/shell/src/draft_state.rs` | 原三个槽、容量/验证/清除顺序；archive 不变成原 owner history |
| 当前 egui Desktop | 使用上述共同字段/模块 | 默认 renderer 不变，已有测试仍运行 |
| 新 Desktop Makepad 入口 | `DesktopNativePresentation` 真实实现 | 启动时整体 move 同一 DraftBook/projection/Bridge；不再创建 egui Desktop 或第二 worker |

`fixed_workspace` 在 launch 时设为原 `Workspace` 枚举值，结构中没有运行期修改它的方法。其他两个 Composer 随唯一 DraftBook 一并进入 composition，但不参与当前窗口的编辑。保存的 `Vec<LocalDraft>` 和 Context 继续是本地资料，不调用原 `install_owner`、`receive_history` 或 `receive_delta`。

第一片只显示 Session Console 观察，不接入 Launch/Cancel 或 local archive 操作按钮；这些已有数据/通道保留在共同状态中，后续按钮接合不重建通道。用户不能从候选外观推断目前已有完整 Desktop 操作功能。实际 renderer 默认值保持 egui，开发入口显式选择 Makepad。

### Worker 通知和关闭需要实际实现

`Bridge::set_waker` 不改 transport。原 worker 完成 bounded reply 之后，调用已安装的 `Arc<dyn Fn()>`；Makepad 提供原 `SignalToUI::set_ui_signal`，原 egui 路径使用现有 repaint/poll 规则。仍保留有界周期 poll 作为 completion signal 先于消息可读的回退，不忙轮询。

`close_ui_client` 只关闭这个 UI 的 channels/通知引用；不向 Session 发 Cancel、不杀 Session、不运行 Hepta RunCancel。Worker 的既有 socket deadline 保持原值。不能在 UI 线程阻塞 `join`；若需要 join，由原 bounded worker 生命周期异步收尾。必须用真实 UDS 测试证明关闭期间不会永久卡在回传队列或 socket 工作上。

## 5. Console 与渲染路径

原 `RuntimeDisplay` 保持为原包私有类型，增加实际 native observation 的受限更新方法，由原 App 在 **非 Draw 回调**更新。原 `HomeScreen`、Chat/Console dock、theme、responsive layout 和 widgets 均复用，不新画一个相似 Console。

第一片最小 observation 是有界显示文本与 refresh-pending 状态。Desktop 的实际 adapter 必须把现有 `NotConfigured`、Connecting、Unavailable、Stale、可观察状态和 source/session 信息诚实转成文本。它没有修改原 runtime owner 状态的能力。

原 Console 的 refresh button 可在 native composition 存在时启用，点击只调用 `request_refresh` 合并一次原 Snapshot poll。接收失败/消息队列满都不能显示“刷新成功”。Web 仍使用原 RuntimeClient，只共用最终 RuntimeDisplay/widget，不把 HTTP provider 换成新的 Desktop daemon。

`poll_console`、callback 安装和 projection 更新都不得在持有 `&mut ChatWorkspace` 时回调宿主；先完成/释放借用，再 dispatch 输入，避免 UI 内重入借用。Draw 回调只借用现有模型绘制，不启动 socket I/O、不读取 owner ledger。

Chat Send 继续由原 `presentation::apply_action(RequestSend)` 返回 `SendUnavailable`；本片不增加任何发送按钮的 authority handler。原 [`ChatWorkspace::request_send`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/56630b12b8a4c69fff2c47b95b36d88a7389c39f/apps/hepta-control-ui/rust/core/src/chat.rs#L443-L452) 只更新 unavailable 状态，不清空文本、不写入消息、不生成传输成功。

## 6. 依赖、资源与门禁

原 [`run-desktop.py:41–44`](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/56630b12b8a4c69fff2c47b95b36d88a7389c39f/apps/hepta-control-ui/tools/run-desktop.py#L41-L44) 使用 `cargo +1.95.0 run --locked`。当前 1.88 presenter 通过不能代替这个 renderer 构建；如决定与 Desktop 1.88 同图构建，必须真的解析并构建证明兼容，不能只根据 Edition 2024 推断 MSRV。Web packaging 的 `nightly-2026-10-02` 是另一条原 packaging 合约，不是 native runner 的工具链要求。

原 UI workspace lock 有 164 包，其中 102 个 package 来自同一个 Makepad Git revision；这包括 optional/平台包，**不是已计算的 Linux 实际编译闭包**。新 renderer 候选正常由 Cargo 解析、生成独立新锁，再记录对现有锁的最小差异；不能修改当前冻结的 6 文件锁片或手造条目。

资源工作不能省略：

- 原两个 Noto SC 文件清单合计 16,874,504 bytes，`prepare-fonts.py` 校验固定下载源、精确字节/SHA、OFL 和 NOTICE，再由原 staging runner 放入资源完整的临时 workspace。
- `NATIVE-ASSETS.json` 记录 29 项合计 67,578,261 bytes，但 #3067 没有导入 product embedding 实现。清单不是字体二进制，也不是已经验证的打包产物。
- 原 `native-host` feature 会跳过独立预览的 build.rs CJK 文件检查；不能借此跳过资源准备。新 presentation mode 必须执行原资源 loader 与真实已载入资源检查，再运行窗口。
- 编译需要原 Wayland/X11/GL/EGL 等系统依赖；设备输入、AT 和视觉结果仍需真实运行。清单哈希本身不证明 CJK 实际显示或 IME 候选窗正常。

最小 gate 必须同时覆盖原包和实际 Desktop composition，不接受只有 trait 单元测试：

1. 原 core/presenter/IME policy 原测试，以及原 App 两种模式的构造/一次采用/fixtures 冲突/无第二 workspace 测试。
2. Desktop 默认 egui 原测试与新的 fixed-scope Makepad composition 构造，确保只有一条原 Bridge、原 DraftBook 实例与原 workspace allocation；反向写入 Session task 不能形成 chat history。
3. 真实 UDS 的 snapshot、generation change、queued-old-sample、断线、超时、退出释放；保持原 Request/Response wire golden。
4. 真实 `ui`/新 native presentation feature 编译、fmt、Clippy；旧 `native-host` 模式保留并独立编译。
5. Weston/X11 下原 App 真正绘制 Chat/Console、CJK 资源、focus、paste、真实 widgets 的 IME commit/confirmation split/coalesced、resize-during-composition、窗口退出。截图与回执绑定实际 source/lock/资源。
6. Send 始终不可用，不能清空原草稿、创建 timeline、签名 Objective、调用 Agentd 或触发 RunCancel；正反用例分别检查正常编辑、显式拒绝与所有 I/O counters。

物理 IME/可访问性、Web 原打包、Android/iOS 输入、Trillionnium 裸机 compositor/input 是后续各自门禁。Linux-host software render 通过也不能宣称这些通过。

## 7. 三个本地工作区的后续切换条件

当前 Desktop `DraftBook` 有三个原 `ChatWorkspace` 实例，每个仅是对应本地 Composer 的唯一所有者。原 presenter 的 `RoomKey` 只有 `epoch` 和 `local_id`；不同 workspace 的默认值可能相同。原 `ImeRouter::Owner` 也是 `epoch` + WidgetUid + TextInputRef。因此不能仅改变 `workspace_mut()` 指向另一个槽，然后认为原 room epoch 已经隔离迟到输入。

在运行中恢复三槽切换前，须在**同一原包**实现本地 presentation binding，明确它不是主体验证或运行 authority：

- 绑定包含本地槽标识与单调 presentation generation；不存在把它转换成 AgentId/RunId/NativeViewIdentity 的 API。
- 原 widget 产生的本地 action 携带当时 binding；应用前须同时匹配当前 binding 和原 RoomKey，迟到 action 拒绝。
- 原 ImeRouter 识别 binding 变化；切换期间保留原候选取消、pointer capture 清理与 focus 规则，不复制 router。
- active composition 期间拒绝工作区切换；切换之后旧 scope 的 delayed Commit、Confirm/Release、pointer up、semantic action 均不得编辑或清空新 scope。
- 新 scope 首次真实 draw 前保持输入绑定未就绪；只有已核验的新绑定可以产生用户动作。该 UI 就绪状态不升级成 GPU/owner readiness ACK。

完成该门禁后才能移除第一片的 fixed-scope 限制，再把既有本地归档/Context 与 host task 控制逐个接回原 widgets。生产 Chat 提交还须独立对接原 authenticated SourceEnvelope/AuthBus issuer、原 sender retain/start、原 transport 与 admission/history；这些不是 presentation binding 或 NativeHost trait 能提供的权限。

## 8. 建议的提交划分

1. **原 Hepta：**原 App state-source + 一次 presentation launch mode + native Console update；原 widgets/ImeRouter 保留；加原包构造/拒绝门禁。没有 Desktop 反向依赖。
2. **Desktop：**移动原 Bridge/reducer/draft state，增加真实 `DesktopNativePresentation`；正常 Cargo 生成锁，feature 默认关闭；同时保留并测试 egui。
3. **组合验收：**固定两个源码提交、原 Makepad ref、资源清单/实际资源与真实 Linux-host renderer 回执。明确 fixed-scope、SendUnavailable、无 AT/mobile/bare-metal 资格。
4. **后续独立增量：**原包输入 binding 与三工作区切换，再接原任务/Context/归档交互及已完成 authority 的发送桥。

目前只完成来源核验与这份设计，没有新增上述 API、运行窗口或 renderer 回执；当前 21 文件 P1 presenter 候选继续按原定 1.88 / default+feature egui / wire gates 独立收尾。
