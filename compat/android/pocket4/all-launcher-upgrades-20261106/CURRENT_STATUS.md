# Pocket4 全 Launcher App 修复：检查点 09

工作尚未完成。用户将原定八个应用扩大为全部 Launcher App，并要求最终清理所有旧 Android/framework、旧 App 版本和相关产物。清理仍以前述真实可用验收为前提；当前 production ready 为 0，删除旧产物为 0 字节。本检查点区分真实成功、失败、UNKNOWN 与未执行候选。

## 当前范围和安装进度

目标为 Pocket4 内置 DroidLoom Android 17 / SDK 37 / user 0。旧 reDroid 14/16 已先前退役；内置 Android 的结果不代表 reDroid 通过。

| 实际项目 | 结果 | 限度 |
|---|---:|---|
| PackageManager 已安装非 APEX APK 包 | 205 | 不是 205 包完整字节、权限或业务验收 |
| MAIN/LAUNCHER 组件 / 包 | 45 / 45 | 两次 resolver 查询相同，与原生目录逐组件一致 |
| 明确保护范围 | 47 包 / 87 APK | 45 个 Launcher 包及 actions、QA helper |
| 已同签名升级安装 | 11 App | 保留原 UID/数据；安装不等于业务可用 |
| 已与当前官方完整资产逐字节相同 | Fcitx、microG | 仍需业务回归 |
| 原串行审计通过 | b01–b04，10 App / 14 APK | b05 原 FAILED 保留，b06–b13 未完成 |
| 新官方工具独立对照 | Calendar、Fcitx，2 APK | 不冒充原 b05 已解锁 |
| 完整业务验收 / 旧产物删除 | 0 App / 0 字节 | 长运行、重启、恢复等仍未完成 |

范围枚举实际任务 1a1b22e95d0-fc05-7cd4 durable exit 0；原件在 successor_audit_requests/current_services_r4/actual/，逐包索引在 current_pm_resolver_index-r1/。205 行元数据与 47 包完整保护范围不是同一资格。

11 个实际升级：贝壳 3.06.71、东方航空 9.5.16、国航 7.53.0、微信 8.0.80、拼多多 8.30.0、淘宝 10.69.0、滴滴 8.0.18、携程 8.97.4、哔哩哔哩 9.18.0、京东 16.1.50、抖音 41.0.0。美团官方候选与已装包签名不同，不强行覆盖、重签或卸载数据；12306、猪八戒仍只有部分下载，不能安装。剩余最新版适用判定、交付和各 App 回归未完成。

## 历史授权与有效约束

沿用 sidecar、容器内 UI Automator、中文输入与真实节点定位，不新增 ADB。哔哩哔哩 Accept 仅属于 p4-bili-m30-cell-20261010，不转移到 Main；美团外卖位置权限不主动开启。完整性、签名、运行时所有权和有效安全约束不被绕过。

manifest 声明和 PM 保存元数据不等于运行时有效授权。effective grants、AppOps 与 roles 尚未完成逐 App 查询。r3 AppOps help 的真实返回 255 保留。新 Beike 单包权限只读 pilot 仍是未提交候选，不包含 grant/set。

## 贝壳新 QA 进程与真实失败

新 helper 已实际构建、安装，UID 10157、固定 APK 和签名已绑定。旧自有 task 876 经原 cleanup 路径实际移除，177 份旧原件、UNKNOWN 和 task 875/877 保留；未删除 App 数据或构建。

新 flow b6de2bd4f04bcd572a074ef984ba7dbe 已 init；native launch 1a1b240f7fd-fc05-7d2d durable exit 0，获得 task 878。inspect 1a1b2537fa5-fc05-7d8c durable exit 0，核对同一 task/helper/前台和状态恢复。只读历史 reader 1a1b262379a-fc05-7dd2 exit 0，核对 21 原件，观察到活动弹窗的 7 个可见非密码节点，无可编辑节点。private UI 不入 Git。

两步 case 1a1b272ec9d-fc05-7e0d **failed 1**。完整 stdout 5920 字节，SHA-256 78ab558a72b5cb14ad00d6d74c978a935272d9252cd13e6a66215dbac1a3abe2。第一步关闭后，独立新 inspect 成功匹配首页搜索节点，产生 step 0 postcondition。第二步报 ProtocolError: EXACT_SUCCESSFUL_FINISH_REQUIRED；原 case 返回 2，action_attempted=true、outcome_unknown=true 保留。子进程正常以 1 退出，pidfd 观察退出并关闭，父 FD 恢复，无超时/kill；生命周期收口不等于 case 成功。

下一步读取该 case 的实际 nonce/commands/transport/失败输出，不能重放点击或用新 flow 逃过 UNKNOWN。run_case、qa_adapter、Flow consumer 未改。成功 case 的后置证明只有设计，不能套到这个失败 case。实际资料在 successor_qa/explore_home_search_case_r1/actual/。

## Calendar 官方工具对照已通过

Google Maven 官方稳定 AAPT2 9.5.1-16666295 的完整 JAR 与官方 SHA 一致。宿主 r3 资格 1a1b257ba27-fc05-7da0 durable exit 0；原 ELF/RUNPATH 未改，工具位于受保护独立目录，7 个 ELF 静态依赖与受控搜索目录已绑定。version 成功不等于 App 兼容。

Calendar/Fcitx 独立对照 1a1b26bfb80-fc05-7dfa **durable exit 0**。外层 stdout 28018 字节 / 8288017c0c0e4e1f349951a81a468fcbbdcb6fa4d1065c4889f96327ba290a76；解码 worker 原件 132387 字节 / 8e577c9e4a6eb77e6ad94e9993ca91aa97af958a4c02491237b32600dd6f4dfe。

同一两份已装 APK，官方 badging 均 rc 0/stderr 0，签名通过且与 PM 证书相同，声明权限名解码完整。对照用旧 Calendar badging 仍 rc 1，因此 all_commands_succeeded=false 如实保留，而所有正式对照命令成功。18 次工具目录观察完整、所测 2 包实际身份和 Main runtime guard 前后一致、6399 观察 FD 全关闭，owned child 正常退出。47 包是固定范围引用，本次没有逐包重验其余 45 包。

这支持旧 Calendar badging 失败与解析器相关，不证明全部资源表、45 App 或业务健康，也不自动推进原 b05 门禁。新版 badging 的派生 min_sdk 当前为 null，仍须核对原始字段格式，不将旧字段冒充新版结果。旧 FAILED 保留；接下来正规修复原审计工具和接续门禁。

## 神州完整同版本官方候选

S35 下载部分失败；S36 一次有限范围续传验证 HTTP 206、精确范围和同一 Last-Modified 后获得 220579134 字节完整 APK，SHA-256 6c796f5073658d6f541ebbae5723d80645e6fbf6060ca816def6c3ec173e31d6。S37 在错误 JDK owner 假设处失败且未运行签名工具；原失败保留。

S38 1a1b25b668d-fc05-7dae durable exit 0，按实际 UID 1000 工具身份验证，v1/v2 通过，唯一证书 d85bed4d2a7c08e1b6b5f0097d6c66a79a5b12b58d97e794d3b5c5bff2aeaf44 与已装包一致。META-INF 警告保留，未改 APK。

S39 1a1b26844a3-fc05-7ded **failed 1**。两条 aapt 均 rc 0/stderr 0，严格 stdout shape parser 拒绝 20 行缩进 feature 与 bare main。原件完整保留；后续独立本地解释只接受已观测的精确语法，没有改原失败或新增远端执行。解析字段为 com.szzc 9.6.1/code 327、min 23/target 33、ARM64/armeabi-v7a、45 声明权限行，与历史已装版本相同但 APK SHA 不同，未当作更高版本安装。

## Framework 现存 builder470 已实测重新资格

旧 build07 1a1b20bbc0a-fc05-7c2e 和诊断 1a1b2240691-fc05-7c96 均 FAILED；旧 builder468 固定 ELF 缺失，不能用新复制文件冒充旧 inode/时间身份。

新显式 current470 使用现存 builder470 和完整真实来源链。stage 1a1b25fcb40-fc05-7dc4、qualification 1a1b26092d9-fc05-7dc7 均 durable exit 0。result 原件 121931 字节 / 3673f75b77a2133b5fbeecd26b13441d6c4625312c304f7dab8604e2efbfbd69 已版本锁分块取回验证。

34 条命令全部 0，19 项 updater 与 9 项实际编译的 source-resume 测试共 28 项通过，15 项门禁通过，498 份来源及绑定依赖前后稳定。峰值内存 904175616 字节、swap 0、memory events 全 0，无残留子进程或 cleanup 错误。资格没有运行 Soong、操作 Main 或部署 framework。

显式接入两目标 framework 构建的新合同仍在源码审查。原来源与收据、Main/47 包保护、fresh 15 GiB 准入、10 GiB cap、0 swap、保留两核/j1 等约束继续有效。builder 资格不能代替 framework 构建或整机可用。

## 后续验收和最终清理

继续完成全部 Launcher App 的版本/完整交付/签名、有效权限、登录或访客、核心操作、网络/存储、长运行、重启和故障恢复。修复 framework 及各个真实失败，形成可复现回归。

最新版通过对应真实验收后，才按最终运行依赖删除过期 Android/framework、旧 APK、实验残留和中间版本，记录实际路径及释放空间。保留最终工作源码、配置、复现清单和必要结果证据。当前未达到整机清空旧版本条件。
