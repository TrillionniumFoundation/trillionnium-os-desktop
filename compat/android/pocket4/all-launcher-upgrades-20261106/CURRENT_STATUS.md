# Pocket4 全 Launcher App 修复：检查点 06

本检查点记录已经取得的实际结果，工作尚未完成。目标保持为所有 Launcher App；原定八个应用只是历史子集。

## 实际范围与边界

当前目标是 Pocket4 内置 DroidLoom Android 17 / SDK 37 / user 0。旧 reDroid 14/16 已在此前退役；本轮不复活它们，也没有将内置 Android 的测试当作 reDroid 测试。

原生应用目录实际列出 45 个包，旧安装保护范围另含 local.pocket4.actions.v2。新 QA helper 已真实安装，因此后续全范围保护还要明确纳入它。45 是已取得的原生目录数量；完整 Android MAIN/LAUNCHER resolver 枚举仍待独立核对，不能据此宣称所有入口已无遗漏。

原始八包及全部目录见 [app_test_catalog.json](app_test_catalog.json)。继续使用现有 sidecar、容器内 UI Automator、中文输入与节点定位，不引入 ADB。哔哩哔哩 Accept 的历史授权仅属于原独立测试 cell，不转用于 Main；美团外卖位置权限不主动开启；不绕过完整性、签名或运行时所有权约束。

## 计数与完成定义

| 项目 | 已有实际结果 | 尚未完成 |
|---|---:|---|
| 原生目录包 | 45 | Android resolver 完整性及差集 |
| 完成同签名、保留 UID/数据的升级安装 | 11 | 其余官方适用交付与实际升级 |
| 已与当前官方完整资产逐字节一致 | 2：Fcitx、microG | 不等于业务回归通过 |
| 完整通过原审计批次的 App | 10 / 45，14 APK | b05 失败；b06 未启动 |
| production ready | 0 | 每包核心业务、权限实态、长运行、重启与恢复 |
| 删除旧框架/App/中间产物 | 0 字节 | 最终可工作版本验收后执行 |

656 个权限条目是已审 APK 的声明记录，不是有效授权、AppOps 或角色的现状。

11 个实际升级包括贝壳、东方航空、国航、微信、拼多多、淘宝、滴滴、携程、哔哩哔哩、京东、抖音。其逐次实际安装与原始结果保留在 successor_install；后续版本列表和剩余来源情况见 [remaining34-source-actions.json](reference/remaining34-source-actions.json)。公开商店版本信息不能代替可安装、签名一致且实际可用的交付包。

## 贝壳新 QA 身份与真实 UI 进展

新 helper 包为 org.droidloom.qa.successor.p8f89f253350ba2fa.r1，UID 10157。37,008 字节 APK 的 SHA-256 是 006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9。它是新的自有测试 helper，没有借用旧 Bili helper 的身份或授权。

| 实际阶段 | durable job | 结果 |
|---|---|---|
| helper 构建 | 1a1b18fedb3-fc05-7998 | exit 0；13 构建命令、70 控制通过；尚非 Android 业务验收 |
| 新 flow 准入 | 1a1b1a1c13b-fc05-79f2 | exit 0；当前 runtime/App 身份通过 |
| helper 安装与新进程 state | 1a1b1a29797-fc05-79fc | exit 0；UID 10157，未授予额外权限 |
| 贝壳 native 启动 | 1a1b1a97f43-fc05-7a25 | exit 0；新自有 task 876 |
| 第一次 UI 读取 | 1a1b1ad5cb6-fc05-7a38 | exit 0；真实 popup 控件 |
| 关闭入口 popup | 1a1b1bceb2f-fc05-7a8f | exit 0；click acknowledged，原业务 outcome_unknown 保留 |
| 独立后置 UI 读取 02 | 1a1b1caee35-fc05-7ad5 | exit 0；窗口前后稳定，状态恢复通过 |
| 固定两步原证据读取 | 1a1b1d1ec94-fc05-7af6 | exit 0；177 文件，888,207 原始字节，FD identity 完整恢复 |

原独立后置读取 01 的 job 1a1b1c54169-fc05-7abf 保持 launch_unknown：同 key 精确对账仍未知；实际两次 job 目录未找到，system/user unit 均 not-found。没有重放 popup 点击；读取 02 是随后独立的只读观察。

读取 02 的真实非密码 UI 显示贝壳首页及搜索入口。点击与读取后的 helper 连接已经退出，辅助功能状态与操作前一致。下一次业务操作仍需新 helper 的明确后置条件证明；此检查点尚未执行该证明发布器，没有将原 UNKNOWN 手工改写为成功。

公开执行 metadata 见 [successor_qa/actual](successor_qa/actual)。完整 UI 节点、两步原始 private bundle 及签名私钥不进入 Git。实际生成源已从成功 binding 与固定参考源确定性重建，26 个源文件和两份原 manifest 均逐字节匹配；见 [reconstructed/source-generation-r2](successor_qa/reconstructed/source-generation-r2)。该来源标注为确定性重建，不冒称直接下载全部源文件。

## 两个仍然明确失败的路径

**日历审计 b05** 的旧 aapt badging 返回非零，原错误和文件摘要均已保留；其余 17 个工具调用成功不能把整个 b05 改成通过。后续已在宿主实际观察系统 aapt2 的 dpkg 来源、19 个静态依赖、version 与 help：version 成功，help 正常输出用法但 exit 1，原要求两命令 exit 0 的诊断因此仍为失败。独立 Calendar/Fcitx 新旧解析对照尚待执行。原始失败日志与候选见 [diagnostics](successor_audit_requests/diagnostics)。

**猪八戒 s34** job 1a1b19cedcf-fc05-79de 实际 exit 1，三个新 1 MiB 分片完整；第 4 次请求因 DNS 不能解析 s.shouji.qihucdn.com 而返回 curl 6，HTTP 0、下载 0 字节，后续 37 段未发送。4 个自有 curl 全部正常回收，没有自动重试或最终 APK。旧失败片段没有拼入有效前缀。详见 [s34_zbj_tail/actual-r1](official_source_scripts/s34_zbj_tail/actual-r1)。

## Framework 修复现状

normal05 原失败仍保留：SystemUI 的真实根 provider 缺失导致严格 Soong 失败，未生成可部署的新框架。

normal06 candidate-r3 恢复 SystemUI 19 个、WindowManager/Shell 9 个完整上游模块。新 provider3 源码锁保留原 225 个项目的提交、顺序、8 个链接与策略，加入同一已固定 superproject 的 17 个项目并扩展 9 处稀疏路径；新锁共 242 项。DeviceState 已找到同提交中真实定义，两条消费者引用保持原样，不创建空 alias。

根进程与独立代理已审查实际 diff 和来源。15 项离线源码/锁控制通过不等于 Rust 或 Soong 通过。宿主 builder470 的 source-stage / Rust 资格请求独立封包；r1 冻结未执行，r2 恢复原严格空子进程成功门禁，并保存全部实际独立测试 gate。此检查点没有 builder470 实编通过或 framework 部署的声明。

材料见 [framework_provider_repair/normal06](framework_provider_repair/normal06)。实际受限编译结果与包含新 helper 的新范围观察将写入后续检查点。

## 清理规则

按用户指示，结束后删除旧 Android/framework、App 旧版本和实验/中间产物，保留最终可工作源代码、配置与复现清单。当前尚无通过全部验收的最终版本，故没有提前删除回退、原始失败证据或构建。后续清理必须以实际文件和运行中依赖核对为基础，记录删除路径与实测释放空间；不会以“编译完成”或“安装完成”替代 production ready。
