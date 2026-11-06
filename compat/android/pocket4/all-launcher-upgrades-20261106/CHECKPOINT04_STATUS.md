# Pocket4 全 Launcher 修复检查点 04

任务尚未完成。本检查点接续 Git `15e7060bbc199630d43e862ad8f548cbb8613e2a`，记录已经观察的结果。

## 已完成的实际工作

已有 11 个不同 App 完成正常升级、验签与安装字节读回。Fcitx5 和 microG 的现有 APK 与官方当前对应发布资产逐字节一致，无需重复安装。这两类结果均未当作业务可用性验收。

当前 45 个 Launcher App 中，前 10 个已完成独立 APK 审计：Fcitx5、microG、贝壳、东航、国航、微信、Hyatt、TextNow、神州租车、哔哩哔哩。已保存完整 APK/split 集合、实际版本/code、UID、签名、ABI、SDK 要求和 656 条原样权限声明。其余 35 个尚待该审计。有效权限仍为 UNKNOWN；manifest 声明不会被当成真实授权。

同一新 runtime 下的 native applications 查询实际返回 45 包，与历史目录相符。Android 服务级完整 MAIN/LAUNCHER resolver 仍待查询。生命周期 scope 中另有 local.pocket4.actions.v2，故不能把 46 项 scope 称为 46 个 Launcher。

## 实际失败与修复进展

贝壳 QA source generation r1 的整体结果仍为失败，原因是进程描述符数 4→5。它实际产生的 source 不具备后续 helper 构建、安装或 UI 资格。独立诊断进一步在加载 frozen core 的阶段，捕获到新出现的 libffi.so.8.2.0 文件描述符；诊断在任何 Main 操作前停止。原失败、原 nonce 和原始日志均保留。

独立 host probe 已实际成功（job 1a1b16bbf10-fc05-7891）：部署 Python 为 3.14.4；fresh child 在 import _ctypes 时仅新增准确的 libffi 文件描述符，此后 ctypes、frozen held_runtime 导入和 GC 均保持同一 FD 集。父进程持有的 pidfd 证明子进程正常退出，未发送信号，父 FD 集完全恢复。实际 Python/_ctypes/libffi 文件哈希与 build ID 已保存。未知描述符没有被擅自关闭，检查没有改成无条件允许额外描述符。后续窄 wrapper 会把库初始化、原 worker 检查和父进程退出收口共同作为资格；该 QA wrapper 尚未执行。

Framework normal05 已实际运行并在 Soong 依赖分析阶段失败：SystemUITests_defaults 缺少 systemui-non-platform-apis-defaults。没有生成或部署已合格的新 framework。normal06 的源码候选补回两个真实上游 defaults，保留完整 flags 和 Dagger 依赖；Rust/Soong 尚未运行，其他普通依赖边须结合实际加载图继续判断。

## 下一步和清理状态

继续剩余 Launcher App 的审计与适用最新版获取，修正并重新建立 QA 身份绑定，再执行真实 UI、登录或访客、核心功能、网络、存储、有效权限、长时、重启和故障恢复验证。所有原授权边界仍有效：不新增 ADB 依赖；Bili Main 不执行历史独立 cell 的 Accept；美团不主动开启位置；不绕过签名、完整性及其他有效安全约束。

完整 production-ready 仍为 0/45。旧 Android framework、App 及中间产物的删除尚未开始，实际回收 0 字节。按用户的先验收后清理要求，只有最终工作版本和实际回归证据齐全后才执行清理，并保留源代码、配置、source-lock 和复现清单。

## 复现证据入口

- `CHECKPOINT04_STATUS.json`：本检查点的状态与原文 SHA256。
- `current_status.json` / `CURRENT_STATUS.md`：检查点 03 的完整 45 包基础记录及 11 项实际升级收据链，保留原快照。
- `successor_audit_requests/actual/index-through-b04-20261106-r1/`：10 包实际审计、35 包缺口和逐条权限声明；索引由 `build_completed_audit_index.py` 调用现有严格 gate 重建。
- `successor_qa/actual/`：原始 source generation 和 FD diagnostic 失败原文；`successor_qa/fd-diagnostic-r1/` 保留实际执行源码、请求和主源引用。
- `framework_provider_repair/normal05/actual/`：实际编译失败日志、资源与进程收口；`normal06/` 为尚未构建的源码候选。

剩余 34 项的来源与实际下一动作见 `reference/remaining34-source-actions.json`：2 项官方字节相同、14 项 framework/自有构建、14 项国际商店元数据但无完整适用安装集、1 项美团签名冲突、2 项 partial 不可安装、1 项神州租车同 code 的正常 HTTPS 候选。候选与缺口不计作升级或可用性通过。
