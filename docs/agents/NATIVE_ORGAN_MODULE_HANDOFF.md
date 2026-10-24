# 原生 organ 模块开发与技术交接

本页只定位本轮模块的实际源码、命令和合同。运行状态由
[当前能力表](../CURRENT_CAPABILITIES.md) 与对应固定源码的原始收据记录。
开始构建前按 [跨仓 source profile](ORGAN_RELEASE_PROFILE.md) 固定完整
Desktop/Hepta commit；下方 Hepta 链接固定当前 `717778d928c747ebc43108af823178edb52a7af7`，tree `bf6bb3653d08aa6838bb48307877118998e3d89d`，与三处当前 Cargo 入口一致。[完整 source map](../SOURCES.md#hepta-native-organ)另列原全局/organ 合同、AccessKit 来源及独立 SDK 候选；固定链接仍不是运行证明。

| 模块 | 实际开发入口 | 构建/验证与技术合同 | 输入、输出及恢复边界 |
| --- | --- | --- | --- |
| 原文本会话 | [TextChatAdapter](../../services/hepta-session-host/src/text.rs)、[原 Makepad 接合](../../ui/shell/src/native_makepad.rs) | [Desktop 开发手册](../../services/hepta-session-host/TEXT_SESSION.md)、[Hepta NATIVE_TEXT_SESSION](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/717778d928c747ebc43108af823178edb52a7af7/codex-rs/hepta-agentd/NATIVE_TEXT_SESSION.md) | 已认证 Root hello 安装原 owner；同 App Server thread 提供流、工具、产物和分页。重连、取消、unknown 沿原签名身份恢复；本地草稿不成为授权。 |
| 安装/升级/卸载 | [desktop.py](../../support/ui/product/desktop.py)、[现有真实安装 harness](../../support/ui/product/smoke_installed.py)、[运行映像门禁](../../support/ui/product/acceptance_identity.py) | [PRODUCT](../../support/ui/PRODUCT.md) 包含 pack/install/doctor/stop/rollback/uninstall 和两真实包 CLI | 输入实际五 binary、source profile、原资源与 manifest pins；输出独立 release、专用 Session user unit 和诊断。升级需停止原 Session；回滚保留配置/草稿，卸载保留用户数据。 |
| 本地草稿 v4 | [DraftBook/checkpoint](../../ui/shell/src/conversation.rs)、[Recovery](../../ui/shell/src/local_drafts.rs)、[renderer 生命周期](../../ui/shell/src/draft_recovery.rs) | [Shell 开发命令](../../ui/shell/README.md#development)、[恢复合同](../../support/ui/PRODUCT.md#upgrade-rollback-and-uninstall)、[草稿/上下文合同](../../support/ui/CHAT_WORKSPACE.md) | 有界私有 checkpoint 保留各 workspace 和停放的 principal 文本；仅真实 owner 可激活原分区。v4 无效不降级、不覆盖；v3 迁移保留原字节。它不保存执行身份或 thread 历史。 |
| Notes 效果与恢复 | [NotesStore](../../ui/core/src/notes_store.rs)、[应用 worker](../../ui/app-window/src/notes_worker.rs)、[原恢复 helper](../../ui/app-window/src/bin/trill-notes-recovery.rs) | [wire/私有 bootstrap](../../support/ui/NOTES_ORGAN.md)、[持久性/实际进程 probe](../../support/ui/NOTES_DURABILITY.md)、[Hepta 原 owner crash recipe](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/717778d928c747ebc43108af823178edb52a7af7/codex-rs/hepta-agentd/NOTES_RECOVERY_QUALIFICATION.md) | 原 operation、revision CAS 和 exact receipt 进入应用 owner；独立回读后原 writer 发布终态。旧 app 必须被原 supervisor reap；helper 只观察/ACK 指定旧 incarnation，新 app 不自动接管旧效果。 |
| 原 Makepad/输入/辅助技术 | [Shell 原 renderer](../../ui/shell/README.md#original-makepad-renderer)、[原资源准备器](../../support/ui/prepare_native_makepad.py) | [NATIVE_MAKEPAD](../../support/ui/NATIVE_MAKEPAD.md)、[X11 IME](../../support/ui/X11_IME.md)、[辅助技术](../../support/ui/ACCESSIBILITY.md) | 输入完整原资源和对应 feature binary；真实窗口、IBus/AT-SPI、CJK/焦点各有独立 oracle。资源摘要或 egui 结果不替代原 Makepad 运行。 |
| Android 严格 receiver | [原 helper extension](../../support/android/receiver/organ_extension.py)、[原 Java runner 绑定](../../support/android/receiver/runner/OrganBinding.java)、[构建](../../support/android/receiver/build_receiver.py)、[资格检查](../../support/android/receiver/qualify_receiver.py) | [receiver 开发/技术手册](../../support/android/receiver/README.md)、[只读 adapter](../../support/android/DEVICE_ORGAN.md)、[Hepta PRODUCTION_ANDROID_TEXT](https://github.com/TrillionniumFoundation/hepta-private-ci/blob/717778d928c747ebc43108af823178edb52a7af7/codex-rs/hepta-memory/PRODUCTION_ANDROID_TEXT.md) | `organ-observe/set-text/readback` 绑定同 window/node/hash/应用/cell 代际；runner 动作前重读。原 signer、固定 host/peer 与原 FinalUse 接合分别验证；相同文本只说明状态匹配，丢因果 receipt 不推 Committed、不对新 cell 重放。 |

## 构建和交接材料

Desktop UI/host 使用 [RUN](../../support/ui/RUN.md) 中的 Rust 1.96.0 和
已锁定依赖；原 Makepad 另需 feature 与完整原资源。Hepta 的 crate 检查走
仓库 `just test`，原文本与 Android 手册各自列出实际包与测试入口。
默认 `hepta-native-makepad` 用原 SDK 与54文件资源；独立
`hepta-native-clipboard-sdk` 才接 `native-clipboard-read.patch` 与
`sdk-num-traits-path.patch` 两份精确补丁、全 crate override、独立锁
和61文件资源；[候选合同](../../support/ui/PRODUCT.md#explicit-original-sdk-clipboard-candidate)
逐项绑定原补丁字节、SDK tree 和资源清单。[v10/v11 scoped 结果](../../results/integration/2026-10-24-original-owner-product/text-native-v10-v11/README.md)
中的 native43/43 与 AccessKit54/54 只覆盖默认 SDK，未执行的完整 workspace、
release、真实窗口、安装后生产和 Android 同 signer 签名保持开放。
Android 的 `build_receiver.py --compile --reuse-original-resources` 只在原
SDK 和已验证原 APK 上生成保留原 binary manifest 的候选；同 signer 签名、
安装后 hash 与实际 receiver 回读属于后续原部署门禁。

交接时保留实际命令、两仓完整 commit/tree、Cargo.lock、binary/package
摘要、原始退出码和日志。安装证据另保留两个外部 manifest pin 与实际
运行映像身份；Android 另保留原 APK signer、helper hash 和 native 代际。
测试夹具的 issuer、provider 或模拟设备回复继续按各手册标为 fixture；
它们不补足生产 Root、原连接能力、真实平台或物理输入证据。

历史模块清点仍见 [MODULE_DOCUMENTATION_AUDIT](MODULE_DOCUMENTATION_AUDIT.md)；
本交接不重写那次清点的文件数或原运行结果。
