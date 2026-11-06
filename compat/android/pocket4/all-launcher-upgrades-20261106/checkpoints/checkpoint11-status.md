# Pocket4 全 Launcher App 修复：检查点 11（进行中）

工作尚未完成。范围为实机全部 45 个 Launcher App，原定八个只是其中子集。用户要求完成后清掉旧 Android/framework、旧 App 版本和相关产物，仅保留最新可工作版本、源码、配置与复现清单。真实可用验收仍是清理前提：目前 production ready 为 0 App，删除旧产物为 0 字节。

## 实际范围与升级

目标为 Pocket4 内置 DroidLoom Android 17 / SDK 37 / user 0。旧 reDroid 14/16 已先前退役，内置 Android 的结果不能代表旧 reDroid 验收通过。

| 项目 | 实际结果 | 限度 |
|---|---:|---|
| PackageManager 非 APEX APK 包 | 205 | 元数据枚举，不是全包业务验收 |
| MAIN/LAUNCHER 包 / 组件 | 45 / 45 | 两次解析相同，与原生目录逐组件一致 |
| 明确保护范围 | 47 包 / 87 APK | Launcher 45 包加 actions、当前 QA helper |
| 已同签名升级安装 | 11 App | 保留 UID/数据；安装不等于业务可用 |
| 与当前官方完整资产逐字节相同 | Fcitx、microG | 仍需功能和恢复回归 |
| 完整 APK 审计通过 | 45 App / 85 APK | 原 b01–04、新 b05 修复、原 b06–12 与新 b13 修复已独立完整关联 |
| 原 b13 | 已执行 3 App / 3 APK，整批 FAILED | fixture 版本字段解析拒绝，其他两个包的个体证据不冒充整批通过 |
| 完整业务验收 / 删除旧产物 | 0 App / 0 字节 | 长时、重启、故障恢复等未完成 |

范围枚举实际任务 `1a1b22e95d0-fc05-7cd4` durable exit 0；原件和逐包索引分别在 `successor_audit_requests/current_services_r4/actual/` 与 `current_pm_resolver_index-r1/`。

11 个实际升级的历史安装记录：贝壳 3.06.71、东方航空 9.5.16、国航 7.53.0、微信 8.0.80、拼多多 8.30.0、淘宝 10.69.0、滴滴 8.0.18、携程 8.97.4、哔哩哔哩 9.18.0、京东 16.1.50、抖音 41.0.0。美团官方候选与已装包签名不同，没有强制覆盖、重签或卸载数据。12306 仍缺完整合格新包；猪八戒 S41 完整新候选已经 S43 正常整包签名及 metadata 联合核验，实际 9.5.20/code 370，同厂商签名，尚未安装。

## 历史授权与有效约束

沿既有 sidecar、容器内 UI Automator、中文输入和真实节点定位推进，不新增 ADB。哔哩哔哩访客 Accept 仅限独立 `p4-bili-m30-cell-20261010`，不转移到 Main；美团外卖位置权限不主动开启。完整性、签名、运行时所有权与有效安全约束保持。

manifest 声明、PM 保存元数据、有效 grants、AppOps 与 roles 分开记录。`granted=false` 不自动归因于用户拒绝，INTERNET 权限不作为网络业务成功证据。

## 原 b05 的修复审计已实际通过

旧 b05 FAILED 与原 STOP 保留。官方 AAPT2 Calendar/Fcitx 对照及四份原始日志证明新版 badging 使用 `minSdkVersion`；Calendar 实际 min 37 / target 34 与 XML 一致。旧派生 min=null 保留，新严格解析器只接受 `sdkVersion` 或 `minSdkVersion` 单一字段，重复、冲突或多余内容仍拒绝。

新修复任务 `1a1b289b789-fc05-7e7e` durable exit 0，核验原 b05 同一四包六 APK：12306 5.9.4.5/code 275、Amazon 32.18.0.100/code 1243240206（三 APK）、Calendar 17/code 37、Camera 2.0.002/code 20002000。18 条正式命令全部正常退出 0，38 次工具布局观察完整，13,047 个观察 FD 全关闭；owned child 正常退出、pidfd 关闭、父 FD 恢复。

外层完整 stdout 36,287 B / `75b1114536b0cc3079e13a4d1ca7463b37f756bb0d6b2b24e051b6395fd5722a`；解码 worker 276,704 B / `b0c876c40165fc10c515fa0db8f8b7a916e969a92fba531375a7a226e97ad8d7`。资料在 `successor_audit_requests/revisions/b05-official-tool-repair-r1/actual/`。

这次 b05 逐包重验范围为四包，47 包记录只是固定范围引用；不代表其他 43 包在该次重新通过。后续显式接续门禁已分别核对原 b01–04 成功、原 b05 failed/STOP 与新 b05 独立修复成功，并在同一原 ledger 中按原顺序执行 b06–13。

## b06–12 通过，b13 的真实解析失败保持

| 原批次 | 实际 job | App / APK | 结果 |
|---|---|---:|---|
| b06 | `1a1b29d3379-fc05-7eef` | 4 / 4 | durable exit 0；12 命令正常返回，接续门禁通过 |
| b07 | `1a1b29f8bb9-fc05-7efe` | 4 / 4 | durable exit 0；12 命令正常返回，接续门禁通过 |
| b08 | `1a1b2a04bff-fc05-7f03` | 4 / 12 | durable exit 0；36 命令正常返回，接续门禁通过 |
| b09 | `1a1b2a29563-fc05-7f13` | 4 / 9 | durable exit 0；27 命令正常返回，接续门禁通过 |
| b10 | `1a1b2a4d290-fc05-7f1c` | 4 / 7 | durable exit 0；21 命令正常返回，接续门禁通过 |
| b11 | `1a1b2a76798-fc05-7f29` | 4 / 16 | durable exit 0；48 命令正常返回，接续门禁通过 |
| b12 | `1a1b2a90ea8-fc05-7f31` | 4 / 10 | durable exit 0；30 命令正常返回，接续门禁通过 |
| b13 | `1a1b2ab7980-fc05-7f3a` | 3 / 3 | durable failed 1；原门禁 STOP 保留 |

最后一批的九条工具命令均正常退出 0，三个 APK 正常签名与 PM 证书一致，只有 `local.pocket4.fixture` 的 manifest 解析被 `AAPT_PACKAGE_VERSION_REQUIRED` 拒绝。`org.chromium.webview_shell` 与 `org.droidloom.qa.editorcontract` 的个体 manifest/签名记录成功，但不冒充整批已通过。

b13 完整 stdout 26,729 B / `d278f4418e86306b34961a20600c8320af22dafc520f7c9b40ca2e909d443858`；worker 72,536 B / `db979e50d6bfa1e0c83fd7ae876239b48bdca3b4be80bfb5cce6e24f30948d33`。owned child 2266668 正常以 1 退出，pidfd 已观察退出并关闭，父 FD 身份恢复、无 timeout/kill。生命周期收口不改变解析失败。固定 reader `1a1b2ae8cd7-fc05-7f48` 已 durable exit 0，读取完整 686 B badging 与 1,244 B XML：两版号字符串为空，XML 三个 version 属性确实未声明，PM code 为 0。官方 Android 默认语义与此一致，独立窄范围解析修复 `1a1b2ba9875-fc05-7f80` 已 durable exit 0；完整 stdout 29,446 B / `b49af29667adb5774191a6e800cbdb52909a53c492a3719adedfe2ec527e953d`，artifact 79,075 B / `abe92b4b425e3c5dfccb67b90bd742070ebd91a0e43d294b889695b87352aa20`。三包三 APK 的九条命令正常通过，原失败保留。全45关联验证器已冻结；根进程完整阅读新实现、核对175份输入及14份输出，并实际只读执行，结果与冻结 COVERAGE.actual.json 逐字节相同：45 App / 85 APK / 255条正常命令，FD 4→4。资料在 revisions/b13-linked-coverage-r1/；原账本 STOP 与冻结矩阵 r1 不改，新增结果明确接续。

实际原件均在 `successor_audit_requests/actual/batches-final-r1/`；冻结接续源及只在本地运行的收集辅助在 `revisions/linked-official-continuation-r2/`。完整布局原文保留并无损编码，512 KiB 上限及每命令工具/目录检查保持，没有以计数代替证据。

## 贝壳 QA 身份、失败路径与独立观察

新 helper 已真实构建安装，UID 10157，APK 与签名绑定。旧自有 task 876 经原 cleanup 实际移除，旧 UNKNOWN、177 份原件及 task 875/877 保留；未删 App 数据或构建。新 flow `b6de2bd4f04bcd572a074ef984ba7dbe` 取得 task 878。

两步 case `1a1b272ec9d-fc05-7e0d` 保持 **failed 1**。第一步关闭弹窗后独立 inspect 匹配首页搜索节点；第二步报 `EXACT_SUCCESSFUL_FINISH_REQUIRED`，原 case action_attempted=true、outcome_unknown=true 保留。

固定失败 reader `1a1b27f06b8-fc05-7e46` durable exit 0，核对 268 份原件，诊断第二步原始拒绝为 **INSPECTED_TREE_OR_WINDOW_CHANGED**。该次 helper action_attempted=false、outcome_unknown=false；检查位于 `performAction` 之前，搜索点击没有发出。连接内窗口 ID 的变化不足以确定具体变化字段。

后续只读 inspect `1a1b285c279-fc05-7e67` durable exit 0，同一 task/helper/前台、状态恢复匹配，无点击输入。其固定历史 reader `1a1b295db9e-fc05-7ec9` durable exit 0，核对 21 原件共 600,436 B；完整树 245 节点，228 个可见非密码节点。首页搜索入口唯一可见可点击，没有可编辑节点。完整私有输出 243,223 B / `0b84a4a9df176ce1bc0ceffa1cb2600e6e96dc7bf1dc2426333cd577febb89f1` 不入 Git；公开派生摘要在 `successor_qa/inspect_after_search_rejection_reader_r1/actual-public/`。

历史读取不等于新行动许可或搜索业务成功。原 Flow、consumer、helper 未放松。失败 case 的部分完成证明 host-only 核验 `1a1b2b679c3-fc05-7f6e` 已 durable exit 0，完整 stdout 3,405 B / `0033cfad5c04b9ed1b5ff8691c59a983ae790ed35a91282fc916a0c197240c4e`。逐条验证原 case 29 命令 / 38 transport 与后来 observer 9 命令 / 12 transport，原文件 bytes/stat 不变、进程 FD 身份相同。历史证明 52,310 B / `2fc36b4de281ae511aff58d9fae7dc849b478fe07e1ccd5b3b7bc06a247507c3`；私有 observer 归档不入 Git。没有 Main 调用或发布 reconciliation，原失败和 UNKNOWN 保留；继续行动仍需现行运行时及原 Flow 条件。

## 贝壳阶段 A 新运行时证明已实际完成

`successor_qa/partial_case_runtime_commit_r1/stage-a-candidate-r1/` 的新只读进程 `1a1b2d13973-fc05-7fe2` 已 durable exit 0。完整 stdout 15,030 B / `6891adc64b25707ce078b2e57ec24f10afb5ca74a80d0dc2e89632104c38aec4`，terminal 733 B / `720ab02fbee47261645eee5312d577f73b010f50788728150bdcb4698e338f37`。

它重新核实原历史证明，使用原 adapter/Session 做两轮 helper/task/full-foreground 检查；6条记录命令、2条私有前台传输，共8 transport及50份原文件按原解析器完整重验。全部正常0，child2349898正常退出、held pidfd闭合、父FD身份恢复，Main authority已关闭。新 candidate 16,972 B / `c9624a3f6d896a07cdfad5958a35df5c5abe6e810b3eabc3a2c25e7ee94d6873`；joint 13,954 B / `cee87a9dc0fb21851aa21a38dffa1030774f4b3e181f896b0487f3db159ad3ac`。

此阶段没有 UI动作、instrumentation、安装、权限修改或 reconciliation发布；原case FAILED/UNKNOWN保持。根进程全文审阅新源、stager与8份冻结依赖的39个方法，并核对19份冻结文件。阶段B需以上述实际终态为输入独立审阅和执行；阶段A candidate本身不开放后续动作。

## 贝壳有效权限 pilot 已实际完成

任务 `1a1b279845c-fc05-7e2e` durable exit 0，实际执行 `cmd package help`、`cmd package dump-package com.lianjia.beike`、`cmd appops get --user 0 com.lianjia.beike`。47 包保护范围前后检查一致，美团原位置状态、哔哩哔哩历史 UNKNOWN 保持。

固定 reader `1a1b27e6086-fc05-7e44` 已取回两份原始日志；私有原文不入 Git。公开派生文件为 `successor_audit_requests/beike_permission_pilot_r1/EFFECTIVE_PERMISSION_OBSERVATION.derived.json`。实测 63 个 requested 名称、26 项 install grants、15 项 user 0 runtime rows，仅 ACCESS_LOCAL_NETWORK=true，其余 14 项为 false，包括位置、通知、相机、录音与媒体。58 项 AppOps 保留精确 mode，不把无前缀行全部说成 UID 范围；roles 仍 UNKNOWN。

没有 grant/set、权限开启或业务操作。该 pilot 不证明网络可达、存储可用或其他 App 的有效权限。

## 全部 Launcher 有效权限读取

固定 13 批 / 45 包 / 103 条只读命令候选已复核，121 件 source/input pin 相符，原 pilot 的 transport、owned child 及 full47 守卫保持。第 1 批 Fcitx `1a1b2b86eb1-fc05-7f76` 已 durable exit 0，完整 stdout 19,618 B / `fc7e559fc17876dd313e862771451a0e336fa8d386d31b6920732ec9ca98acdc`；三条命令及 owned 生命周期联合通过。其固定私有读取及冻结 parser 已完成：requested 3、install grants 2、user0 POST_NOTIFICATIONS=false、51项 AppOps literal mode，roles UNKNOWN。第2批 microG 因完整 dump 超过原256 KiB采集上限失败，原 STOP保留；独立更正仅该条 stdout 使用明确2 MiB预算，其余原边界不变；新任务1a1b2d790f2-fc05-7ffb已完整成功，原失败与STOP仍保留，后续分批等待独立关联核验。原始 PM/AppOps 日志保存私有，逐包解释须在完整原件、正常终态与生命周期联合通过后进行。没有 grant/revoke/set、角色推断、ADB 或业务成功结论。

独立 microG 更正 `1a1b2d790f2-fc05-7ffb` durable exit 0；完整stdout21,301 B / `e9cebfcf091c930cb063f7a7ae50af51e795e34c42b42dfbbaa8f2d3cfad96b1`，artifact40,751 B / `60006128ea7afdfd2fe81b3f408147d948cbedf2a0a4c5a4011b03f34989a5e3`。实际PM dump为1,478,016 B、AppOps为1,478 B；三条命令正常0、双流EOF完整、没有终止动作。full47前后检查通过，10,350个观察FD及20个lease全部关闭，进程FD5→5，owned child2367620正常0与pidfd闭合、父FD身份恢复联合成立。仅第二条microG stdout采用2 MiB固定上限，help/AppOps及全部stderr仍256 KiB；原30s/25s/900s和1GiB资源边界保持。完整服务原文仍在私有目录，尚不推导其有效授权。

## 官方交付的实际进度与缺口

神州完整官方候选 220,579,134 B / `6c796f5073658d6f541ebbae5723d80645e6fbf6060ca816def6c3ec173e31d6` 已下载，正常 v1/v2 验证通过、原厂证书与已装包一致。实际 metadata 为 9.6.1/code 327，与当前版本相同、文件 SHA 不同，未当更新安装。S35/S37/S39 原失败保留，S39 工具成功但解析器拒绝与后续本地解释分别记录。

猪八戒 S34 原 DNS 失败保留。三份成功 receipt 共 7,103 B 已版本锁读取；三个 1 MiB 正文的 SHA、完整 stat、owner 与 receipt 一致。此次未传输正文、未重新读取此前 124,370,944 B 前缀，续传时仍须重验完整旧输入链。

正常系统 DNS 单次观察 `1a1b2983a9d-fc05-7ed3` durable exit 0，UID 1000，一次 getaddrinfo 用时 10.099 秒取得四条 IPv4，前后 FD 一致。stdout 2,313 B / `61ecdfd852260204ef324d4fbd518eae55f9e9660bd7788bce110f6f99173c95`。该探针没有 HTTP、下载或配置变更。

新的有限剩余 39,356,950 B 续传 S41 r2 `1a1b2aad530-fc05-7f38` 已 durable exit 0，38 个分段全部 COMPLETE。完整 stdout 90,411 B / `87ff7fb49fe8ce2570dbba9c777fd1944c7fcc8fbdf09dc49ecd4a61e7e9cea8`。完整 APK 166,873,622 B / `1822af13f666fea9814a7e571d50cc7def3aad72426d2e3eaa9101dcd6eaefa0`，固定路径 file_info 的 size/hash 一致。沿原 S34 curl URL/UA/TLS/206 范围与 pidfd 所有权，38 段顺序各一次，失败停止后续请求。S36 仅借用 nofollow/身份/发布方式，其原网络实现实际是 urllib，不声称其为 curl。无 ETag 如实保留，不伪造 If-Range。S42正常工具执行之后因三类标准badging语法未被识别而整次失败，原失败保留；更正解析器 S43 `1a1b2c8fc38-fc05-7fc4` 已 durable exit 0。完整 stdout 52,573 B / `96c6931181555e575bffa3e626d704b93254298441095f318691d9d3ab70cb11`，三条工具正常0、完整采集/退出，13/13 held FD闭合且原进程FD身份恢复。正常v2签名与现装相同，metadata为9.5.20/code370，高于现装9.5.11/code369；完整六份工具原文与S42相同。候选可进入fresh-scope正常安装审阅，运行兼容与业务可用仍未知。

12306 已装 5.9.4.5/code 275 已由新 b05 实测。公开商店出现 5.9.6.8，完整可用官方交付仍未取得。原 TLS EOF 失败保留，不用其他包名代替，不绕过下载访问策略。

## Framework 在真实 RAM 准入处停止

现存 builder470 显式资格 `1a1b26092d9-fc05-7dc7` 已通过 34 条命令、28 项测试、15 项门禁，source/dependency 绑定及 owned 生命周期完整。旧 builder468 固定 ELF 缺失、build07 原失败保留，不伪造旧文件身份。

显式合同 `explicit-current470-34commands-28tests-v1` 与封包经核验后，实际 build08 `1a1b2831982-fc05-7e59` **failed 1**。前序检查后在 fresh 15 GiB MemAvailable 准入处停止，编译器尚未启动。当时 MemAvailable 15,642,164 KiB，短缺约 84.45 MiB；owned 10 GiB cap、swap 0、CPU 200% 保持，Main 前后检查通过、memory event delta 全 0、没有 OOM。

随后一次只读内存观察 `1a1b28d4100-fc05-7e98` durable exit 0，MemAvailable 15,440,691,200 B，仍少 665,436,160 B（约 634.61 MiB）。没有自动重试、降低门槛、将 swap 当预算、释放其他进程或清缓存。此结果不是 framework 编译或部署成功。

全部 APK 审计进程与 S41 下载均结束后，一次新只读观察 `1a1b2b4e35b-fc05-7f66` durable exit 0：21:12:42 UTC 的 MemAvailable 为 15,425,761,280 B，仍少 680,366,080 B（约 648.85 MiB）。此后没有启动 build09。原两次采样实际早于 b06–13，现有证据不能将内存差额归因于这些批次。

只读进程内存清单 `1a1b2c7e4d8-fc05-7fb9` 已 durable exit 0，完整stdout 37,727 B / `2d0df61ea80f0adb948f7d25ff0b15145f884ddcf3bd31ecc7e3bf83606b5335`，仅PID/父PID/UID/进程名/RSS，没有执行参数或环境变量。该清单不能单独证明某进程属于本任务或可以结束，没有停止任何进程。控制器历史任务首页仅128/5653条且不含PID，未当作完整活动进程清单。

实际资料在 `framework_provider_repair/normal06/current470-authorization-r1/actual-build08/` 与 `memory-observation-after-build08-r1/`。两目标构建、部署和整机验收仍待完成。

## 回归与最终清理

继续全部 Launcher App 的完整版本/交付/签名、有效权限、启动、登录或访客、核心操作、网络/存储、长运行、重启和故障恢复。成功项保存可复现证据，未测试项标 UNKNOWN，环境与交付阻塞如实记录。

相应最新版本完成真实验收后，按最终运行依赖删除旧 Android/framework、旧 APK、实验残留和中间版本，记录实际路径及释放空间。保留最终可工作源码、配置、复现清单与必要验证证据。当前未达到清空旧版本条件。

## 逐包可复现矩阵

`audit_matrix_r1/snapshots/c79b953103d9d432fcbe/EVIDENCE_MATRIX.md` 与 JSON 由 171 份实际输入生成并逐 hash 复核：明确 45 App / 85 APK 已尝试，42 / 82 联合通过，11 升级、2 官方资产摘要同字节、1 签名冲突。该冻结快照保留 b13 原失败且只纳入此前贝壳有效权限快照；新增权限采集和 b13 更正须以后续明确快照接续。136 项核心用例、12 种网络 profile 是回归计划，未冒充已通过。

## 检查点 10 之后的实际新增结果

- 权限 b02 `1a1b2be17ec-fc05-7f8b` durable failed 1。microG `dump-package` 在 22.99 ms 达到 262,145 B，实际错误 CHILD_OUTPUT_BOUND，原外层错误名称为 HOST_COMMAND_TIMEOUT；不应据名称说真实耗时超时。该 child -9、joined、stdout 不完整，AppOps 未执行。owned 外层 child 正常以 1 退出、pidfd 关闭、7,137 个观察 FD 和 20 个 lease FD 均关闭；原串行 STOP 保留，不继续 claim 第三批。
- Fcitx 固定私有 reader `1a1b2c25ac5-fc05-7f9f` durable exit 0；两份原文完整取回且保持私有。冻结 parser 派生 20,074 B / `32c17c1c34bc43c707ab8d9a661e54b4cfea4f98a27d8c3a4f6a1ddf2d7371f0`：requested 3、install grants 2、runtime POST_NOTIFICATIONS=false、51 项 AppOps literal mode；roles UNKNOWN，未主动修改权限。
- 猪八戒 S42 `1a1b2bf6182-fc05-7f90` durable failed 1，完整 stdout 51,004 B / `996845dad5c91bd67f16706561d42417ed370ab000f26ac9b16a7d1832576e0c`。三条工具命令均正常 0，整包 v2 正常验证、厂商证书与已装一致，实测 9.5.20/code 370/min26/target30/ARM64+v7a。失败来自严格 badging 形状识别尚不支持 install-location、feature-group 中 uses-gl-es 与 requires-smallest-width；声明权限解析通过，原失败保留，未安装。
- 原实际 installer r2 的 38,684 B 源码从不可变 Git09 恢复，SHA `7fe3d12fd280539939c930970755e9f33ab7cda51f08a03cc54eb5f9c52508eb`；没有猜造缺失实现或读取设备私有数据。
- 检查点 10 已提交并推送：`c178b683e62158585788b871bd50a12b548d93a2`，tree `03e9848b474f579866e260c0c6156e661c2a15bd`。这份提交保留当时42/82联合通过及b13正在执行的真实快照；后续结果由新的检查点接续。
