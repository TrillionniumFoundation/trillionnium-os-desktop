# Pocket4 全 Launcher App 修复：检查点 14（进行中）

工作尚未完成。范围为实机全部 Launcher App，原定八个只是其中子集。新的完整实测确认 46 个 Launcher App、206 个非 APEX APK 包；新增 `com.example.ndk_tests/com.example.ndk_tests.NdkTestsActivity`。原 45 包清单保留为历史快照，不冒充当前全集。用户要求完成后清掉旧 Android/framework、旧 App 版本和相关产物，仅保留最新可工作版本、源码、配置与复现清单。真实可用验收仍是清理前提：目前 production ready 为 0 App，删除旧产物为 0 字节。

## 最新变化与当前执行位置

当前整合清单位于 `current_launcher_inventory_r3/`。根进程已阅读新证据关联实现，并以只读方式实际重跑：29 项原文输入、46 行 / 86 个 Launcher APK、48 包 / 88 APK 保护范围、12 次升级、3 份有效权限快照、0 个生产验收和 0 字节清理联合断言通过，生成内容与冻结文件逐字节一致。`INVENTORY.json` 为 1,703,185 B / `8932d7b7f18218717de09a2b05860f29d0f3d80f646127d89b6959bd60cc1ea9`。46 项成员关系来自最近完整 native46/PM206 观察；猪八戒升级后没有重新全局枚举。

最新单次搜索失败的独立 no-action 阶段 A 已在新进程实际完成：`1a1b33331ac-fc05-8102` durable exit0，完整 stdout15,528 B / `099a24caac0527f24a97417419cea432b57663cde227d7c844204b2896b08561`。它核实101份历史原件及原拒绝在点击分发前发生，再以原 Session 完成两轮 helper/task/full-foreground 检查，6条记录命令、8个传输、50份当前运行时原件通过；child2531797正常0退出、pidfd关闭、父FD身份恢复。candidate15,151 B / `80e722995f0c4304fa6b2d75d03cdb0c32a3fc382d31c4bb0c4781081553bde6` 保留阶段A本身不授权的语义，之后的独立阶段B已实际完成。

新 no-action 阶段 B `1a1b33fbae4-fc05-8172` durable exit0，完整 stdout19,805 B / `3a046f40503768c5e0411daee65c5b233e6245b32c0098c8fd4493a8915a9cbf`，terminal733 B / `29f4241e351442586e8080fa0d252c883075df864934add9657216cecde72ece`。它再次完成两轮原 Session 运行时检查，211份关联原件闭合，以独立 `owned-qa-no-action-commit` 生产器发布29,722 B / `306475d1ac5f9d03626c325653e9c158b3c6b06dc99baccabcc45808d53e1da4` 的 reconciliation。typed proof19,528 B / `120b57ddd5dcf5d5fd83b04452af4d04a05ff8a53a0cad2db297e9bfec8285ea`；owned child2559108正常0、pidfd关闭、父FD恢复，与完整durable terminal经根进程联合核验。原 FAILED/UNKNOWN 和原 consumer 保持，observation_step/postcondition均为null，不伪造业务后置条件、不重放点击。该结果支持重新基于现行身份和新鲜界面检查决策，不证明贝壳业务成功。

固定同进程搜索 helper r2 已完成实际源发布和普通 UID1000 宿主构建，尚未安装或执行界面动作。source-stage `1a1b338f888-fc05-812f` durable exit0，15份源码 readback匹配；build `1a1b339c056-fc05-8136` durable exit0，15条正常工具命令全部完整退出0，原 `qualified_build` 对完整39,246 B / `0d6a4e19388358032c9ba4ad4f034e714470d7d194c36599226bd0ba6745330f` 回执实际核验通过。APK41,104 B / `968c23aac929130a76dfa49d796fbe5264c073f805b7f048b68737e427d96372`，包名 `org.droidloom.qa.successor.p8f89f253350ba2fa.r2`，signer `f5eb5f24311fb19187b37219db272837d2d68632d9e8b855a89b2b6518904143`。testOnly=true、debuggable=false、无声明权限；仅state/inspect/fixed search_click，不增加ADB。新动作在同一进程/连接中执行三次完整新鲜树一致性检查后才允许一次指定搜索点击，旧helper及完整树校验保持。共存安装正在绑定实际build与阶段B，设备分配的新UID尚未知。

IHG独立公共分发页面观察 `1a1b3437276-fc05-818f` durable failed1。第一条默认urllib请求返回HTTP403、`Cf-Mitigated: challenge`，第二页未请求。完整stdout4,757 B / `acf3430ad2b4c759e54afe06a17c0b3ff71da0cbd945fcf13e4972a16db63260` 与terminal728 B / `9ba6041290ae4b9479fa5edc16040f9aa32849af8115fcd143da719ad6e3eff0` 已核验，原FD身份恢复。0 APK下载、0 Main/Android/UI/安装/权限修改；该交付路径停止，不改身份、挑战、代理、DNS、TLS或端点重试。网页5.110.0/code50023496与证书元数据仍只是候选信息，未取得真实可安装的新包。

独立发现任务 `1a1b307f521-fc05-807a` 已 durable exit 0，完整 stdout 31,226 B / `474893612abaf6192653b31d16adb808a2d46e92cf6e1683760e532684d5fe5d`，原始 artifact 112,546 B / `69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400`。两轮完整 PM/resolver 与 native 目录一致，仅新增上述 NDK 包，旧 47 包保护身份全部不变。新增包实测 UID 10162、code 0、单 APK 1,397,258 B / `b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164`。PM 的 versionName 字面值为 null，来源仍未知，未据此声称 APK manifest 或正常验签已通过。六条 Android、四条 native 查询正常 0；16,571 个观察 FD 和 20 个 lease 全闭、进程 FD 5→5、owned child 正常 0、pidfd 收口。独立 scope48 任务随后实际通过，旧 scope 和 STOP 保留；新增 APK 的正常验签也已完成，见下文。

贝壳单次搜索点击 case `1a1b30305de-fc05-8072` 实际 failed 1，原 case `EXACT_SUCCESSFUL_FINISH_REQUIRED` / UNKNOWN 保留。一次固定只读诊断 `1a1b30c6205-fc05-8083` durable exit 0：101 份原件共 782,840 B 完整验证，10 条 command / 13 条 transport 正常 0，原 helper 拒绝仍为 `INSPECTED_TREE_OR_WINDOW_CHANGED`，发生在 performAction 之前，helper action_attempted=false / outcome_unknown=false。before、inspect、after 均成功，但没有 postcondition，未重复点击，未发布新 reconciliation。完整私有 bundle 1,102,634 B / `85b3b9801685a427a484cc81b80de64e66df49ceb477efa99901ac2dfb01cee4` 保持 root-private；公开诊断 15,496 B / `c6b1396ac512fe5730497a2de75642cce3d6c0c24bccbc5a9a83a41b37002e9b`。

22:45:19 UTC 的新单次 RAM 观察 `1a1b309af4f-fc05-807d` durable exit 0，MemAvailable 15,556,583,424 B，仍距原 15 GiB 门槛差 549,543,936 B（约 524.09 MiB）。未启动 build09。清理依赖目录正在只读核对，历史 12 件旧 APK 合计 2,136,945,962 B 只是逻辑字节记录，尚非实测可释放空间。

最新 48 包范围已实际完成，并通过固定原文回读。NDK 正常审计 `1a1b3224c52-fc05-80b6` durable exit 0，三条普通工具命令全部正常，完整 stdout 27,424 B / `2ce6ac7f77fe71955ccad5c3a6a85eb9d5ff1b1827ef306cee86968353cba3a3`，artifact 62,533 B / `c6fec2589cf3df6dfdd65c88d14d39c041c1a2449d707618fe4c7f5d6a9639c3`。真实 XML 的三个版本属性均未声明，declared version 保留 null，Android effective code 为 0；min 14 / target 24 / ARM64。v1/v2/v3 正常签名通过并与 PM 证书一致，来源和最新版仍 UNKNOWN。声明 WRITE_EXTERNAL_STORAGE、INTERNET，尚未取得有效授权或功能证据。3,087 个观察 FD 全闭、进程 5→5、owned child 正常 0、pidfd 与父 FD 收口。

猪八戒 r4/full48 正常安装 `1a1b32567fe-fc05-80c6` 已 durable exit 0，并完整联合核验；stdout 15,948 B / `23998b1f6ccd501379f207e0e6534ecaf2a88ede7cdb21702a4bbdbb357fc3d2`。实际从 9.5.11/code369 升至 9.5.20/code370，UID10144、CE/DE inode152967/152970 保留，现装 166,873,622 B / `1822af13f666fea9814a7e571d50cc7def3aad72426d2e3eaa9101dcd6eaefa0` 与 S43 正常同签名候选逐字节一致。四条命令正常0，1,293 个观察 FD 与 51 个 lease 全闭。其他47包完整行相同、美团保存的位置投影与旧 Bili UNKNOWN 保留。升级总数现在为12；没有业务成功或清理结论。

新安装后 scope 固定 reader `1a1b328a3ae-fc05-80d9` durable exit0，完整原文59,259 B / `9aeb555bbc287e168d1bb8f1df09e33f8fd37777ee01a58fe2c563e2725cf01a`；48包/88APK/4,978,910,205逻辑字节。其他47行与升级前原文逐字段一致，ZBJ行等于真实安装后读取，7/7 FD与全进程身份恢复。该范围是安装事务的实际身份范围；本次安装后没有再做全局 resolver 枚举，最近完整 Launcher 枚举仍是46项。

清理依赖元数据观察 `1a1b31db305-fc05-80a6` 已 durable exit0，stdout22,176 B / `8666712057ba0e42bf0ab3e61f4907f92e5cd3afc440f8b391ef2f4e4c3b7e07`。797固定引用中776观测到、20缺失、1未解析；14/16树完整，shared framework work 在38,712条目触达原产物预算，build08树未遍历，均明确INCOMPLETE。观测124,867 FD与20lease全闭，owned生命周期正常。去重元数据的10,889,973,760分配字节包含现行依赖，不是可释放空间。该采样早于新ZBJ升级，原12旧APK之后又新增保留1个旧ZBJ APK；0删除。

贝壳最新失败 bundle 已完整固定回读，101原件核验通过。新预检与两次历史成功预检比较：228个可见路径及搜索按钮字段一致，只有同一非交互TextView的文字/边界/节点hash变化；窗口hash一致。pre-inspect至action捕获约1.6秒，但拒绝瞬间新树未导出，触发字段仍不能确定。正在准备保持完整安全校验的同进程新操作和单独no-action对账，旧FAILED/UNKNOWN未改。

23:23:14 UTC 新只读 RAM 任务 `1a1b32c62a1-fc05-80ee` durable exit0，MemAvailable15,376,605,184 B，仍距原15GiB门槛差729,522,176 B（约695.73MiB）；没有build09，没有降低门槛或停止其他服务。已产生的固定空间原件摘要 `1a1b32ae582-fc05-80e4` 也已durable exit0，完整stdout31,019 B / `b567e93c585d31102fe54db71b37de967f0b99c68b012d1b8fc95cb9aa901230`。原12个旧APK在pre-ZBJ采样中的完整stat均与历史保留回执一致、12个不同inode、nlink各1，实际分配合计2,137,006,080 B；新ZBJ另保留166,858,796逻辑字节的旧APK，其当前分配量未在前次样本中测量。两个固定读取均未修改目标或删除文件；磁盘分配量不等于可回收空间。

以下保留此前步骤及其当时限制，不改写历史结果。

原权限 b03 `1a1b2eccc8a-fc05-8033` 已 durable failed 1：原生目录从 45 变为 46，新增上述 NDK 测试组件、缺少组件为零。旧全 47 包身份及 runtime 前置检查仍匹配；两条 native 读取正常 0，但尚未执行 Android 权限查询即停止。4,557 个观察 FD 全闭、进程 FD 5→5、owned child 正常以 1 退出、pidfd 关闭。原失败和串行 STOP 保留，未 claim b04；新的完整范围需实测后显式接续。

贝壳阶段 B `1a1b2e8d3ff-fc05-802d` 已完整成功并经根进程联合核验，旧 FAILED/UNKNOWN 未改写。新的只读 inspect `1a1b2f182c1-fc05-803d` 也已 durable exit 0：同一 task 878、目标 UID 10143、helper UID 10157、完整前台前后相同，独立状态恢复成功，未点击输入；当前节点原文待固定回读。万豪 S44 `1a1b2f15943-fc05-803c` 第一公开页面返回 HTTP 403，durable failed 1；一次请求、零重定向，第二页未请求、未重试，没有下载 APK 或访问 Main。

该 inspect 的固定 reader `1a1b2f97545-fc05-8050` 随后 durable exit 0：21 原文件共 600,424 B 完整核验，进程 FD 身份恢复；完整私有 stdout 243,205 B / `6a1c770b862a47a5a64021392e58e9b36a9bc583a261a7412333bf9355513790` 未入 Git。原树 245 节点、228 个可见非密码节点；唯一搜索 TextView 入口仍可见可点击，没有可编辑节点。下一点击仍需原内部 fresh inspect 和 tree/window 检查，尚未发送新的点击。

## 实际范围与升级

目标为 Pocket4 内置 DroidLoom Android 17 / SDK 37 / user 0。旧 reDroid 14/16 已先前退役，内置 Android 的结果不能代表旧 reDroid 验收通过。

| 项目 | 实际结果 | 限度 |
|---|---:|---|
| 当前 PackageManager 非 APEX APK 包 | 206 | 新独立发现任务两轮一致；历史为 205 |
| 当前 MAIN/LAUNCHER 包 / 组件 | 46 / 46 | 新任务两次解析相同，与原生目录逐组件一致 |
| 新增 NDK 测试组件 | 1 | UID 10162、effective code 0；正常签名和实际 manifest 已验证，来源/最新版未知 |
| 当前实际身份保护范围 | 48 包 / 88 APK | 最近46个Launcher包加 actions、当前QA helper；ZBJ升级后原文已回读 |
| 已同签名升级安装 | 12 App | 保留 UID/数据；安装不等于业务可用 |
| 与当前官方完整资产逐字节相同 | Fcitx、microG | 仍需功能和恢复回归 |
| 正常 APK 审计 | 原45 App /85 APK，加NDK 1 APK | ZBJ新版本另由S43正常验签与实际安装后相同字节关联；原证据保留 |
| 原 b13 | 已执行 3 App / 3 APK，整批 FAILED | fixture 版本字段解析拒绝，其他两个包的个体证据不冒充整批通过 |
| 完整业务验收 / 删除旧产物 | 0 App / 0 字节 | 长时、重启、故障恢复等未完成 |

范围枚举实际任务 `1a1b22e95d0-fc05-7cd4` durable exit 0；原件和逐包索引分别在 `successor_audit_requests/current_services_r4/actual/` 与 `current_pm_resolver_index-r1/`。

此前11个实际升级的历史安装记录：贝壳 3.06.71、东方航空 9.5.16、国航 7.53.0、微信 8.0.80、拼多多 8.30.0、淘宝 10.69.0、滴滴 8.0.18、携程 8.97.4、哔哩哔哩 9.18.0、京东 16.1.50、抖音 41.0.0。美团官方候选与已装包签名不同，没有强制覆盖、重签或卸载数据。12306 仍缺完整合格新包；猪八戒 S41 完整新候选已经 S43 正常整包签名及 metadata 联合核验，实际9.5.20/code370，同厂商签名；新的r4/full48已实际安装，见顶部最新记录。

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

此阶段没有 UI动作、instrumentation、安装、权限修改或 reconciliation发布；原case FAILED/UNKNOWN保持。根进程全文审阅新源、stager与8份冻结依赖的39个方法，并核对19份冻结文件。阶段A candidate本身不开放后续动作；阶段B已基于上述实际终态独立审阅和执行。

## 贝壳阶段 B 恢复记录已实际发布

阶段 B `1a1b2e8d3ff-fc05-802d` durable exit 0；完整 stdout 19,859 B / `2085de33d6716f20578dba5c8f06bc93b93565f98defd76d0837e8df631f422c`。根进程核对 21 份冻结文件、15 个原样继承函数、8 份原源及 39 个方法，全文审阅新实现及 stager 差异，之后只提交一次。新进程完成两轮原 helper/task/full-foreground 检查，6 条只读命令、8 个传输及 50 份运行时原件完整通过。

新兼容记录 62,432 B / `bd2b8b9e82fcdcb1f5a2af9a8a9ae222a951367458b3602acae6614e72b2710c` 绑定 460 份证据；typed proof 21,321 B / `dae3a4d6e8101f427b13279b914cb267f52e864af7811ec7eaa32517b98a2deb`。原 no-replace 发布函数、Flow consumer、helper 和安全检查未改；child 2397744 正常 0 退出、held pidfd 已退出并关闭、父 FD 身份恢复。root 已验证完整 stdout 与 durable terminal，后续仍必须 fresh inspect。旧 case FAILED/UNKNOWN 保持；该步骤没有 UI、安装、权限修改或业务成功结论。实际证据在 `successor_qa/partial_case_runtime_commit_r1/stage-b-candidate-r1/actual/`。

## 贝壳有效权限 pilot 已实际完成

任务 `1a1b279845c-fc05-7e2e` durable exit 0，实际执行 `cmd package help`、`cmd package dump-package com.lianjia.beike`、`cmd appops get --user 0 com.lianjia.beike`。47 包保护范围前后检查一致，美团原位置状态、哔哩哔哩历史 UNKNOWN 保持。

固定 reader `1a1b27e6086-fc05-7e44` 已取回两份原始日志；私有原文不入 Git。公开派生文件为 `successor_audit_requests/beike_permission_pilot_r1/EFFECTIVE_PERMISSION_OBSERVATION.derived.json`。实测 63 个 requested 名称、26 项 install grants、15 项 user 0 runtime rows，仅 ACCESS_LOCAL_NETWORK=true，其余 14 项为 false，包括位置、通知、相机、录音与媒体。58 项 AppOps 保留精确 mode，不把无前缀行全部说成 UID 范围；roles 仍 UNKNOWN。

没有 grant/set、权限开启或业务操作。该 pilot 不证明网络可达、存储可用或其他 App 的有效权限。

## 全部 Launcher 有效权限读取

固定 13 批 / 45 包 / 103 条只读命令候选已复核，121 件 source/input pin 相符，原 pilot 的 transport、owned child 及 full47 守卫保持。第 1 批 Fcitx `1a1b2b86eb1-fc05-7f76` 已 durable exit 0，完整 stdout 19,618 B / `fc7e559fc17876dd313e862771451a0e336fa8d386d31b6920732ec9ca98acdc`；三条命令及 owned 生命周期联合通过。其固定私有读取及冻结 parser 已完成：requested 3、install grants 2、user0 POST_NOTIFICATIONS=false、51项 AppOps literal mode，roles UNKNOWN。第2批 microG 因完整 dump 超过原256 KiB采集上限失败，原 STOP保留；独立更正仅该条 stdout 使用明确2 MiB预算，其余原边界不变；新任务1a1b2d790f2-fc05-7ffb已完整成功，原失败与STOP仍保留，后续分批等待独立关联核验。原始 PM/AppOps 日志保存私有，逐包解释须在完整原件、正常终态与生命周期联合通过后进行。没有 grant/revoke/set、角色推断、ADB 或业务成功结论。

独立 microG 更正 `1a1b2d790f2-fc05-7ffb` durable exit 0；完整stdout21,301 B / `e9cebfcf091c930cb063f7a7ae50af51e795e34c42b42dfbbaa8f2d3cfad96b1`，artifact40,751 B / `60006128ea7afdfd2fe81b3f408147d948cbedf2a0a4c5a4011b03f34989a5e3`。实际PM dump为1,478,016 B、AppOps为1,478 B；三条命令正常0、双流EOF完整、没有终止动作。full47前后检查通过，10,350个观察FD及20个lease全部关闭，进程FD5→5，owned child2367620正常0与pidfd闭合、父FD身份恢复联合成立。仅第二条microG stdout采用2 MiB固定上限，help/AppOps及全部stderr仍256 KiB；原30s/25s/900s和1GiB资源边界保持。完整服务原文仍在私有目录，尚不推导其有效授权。

## microG 完整回读与有效权限

microG 完整私有回读 `1a1b2ea0995-fc05-8030` durable exit 0，压缩 stdout 57,363 B / `c1f9673a46de3b5272a38d84470ad8db6c53cf3e09a177fa9e5d7af3c300a9da`；完整解压后逐文件 SHA 匹配、FD 4→4。独立窄范围 parser 只对该实际 PM pin 允许 2 MiB，原 8 个解析函数保持。实际解释结果 62,052 B / `ee8347af686deb9ce08bd2f1e3ce5aebe7e10302268c7069e6c4bd536713645d`：requested 73、install grants 33、user0 runtime 22，其中仅 POST_NOTIFICATIONS 和 ACCESS_LOCAL_NETWORK 为 true，20 项 false；requested 汇总 35 已授予、20 未授予、18 UNKNOWN。AppOps 53 项保留字面 mode，只有一项有显式 UID prefix，其余 scope 不推断；roles UNKNOWN。没有权限修改、拒绝原因或业务成功推断。公开结果在 `successor_audit_requests/effective_permissions_microg_parser_r1/actual/`。

## 官方交付的实际进度与缺口

猪八戒安装 revision3 candidate2 的 host 源准备 `1a1b2defc61-fc05-8011` 已 durable exit 0：六份源码/输入精确匹配，host 控制正常 0、FD 4→4，零 Main/Android 调用，尚未安装。旧 47 包候选不会被当作新增组件后的当前全集；完成新增包身份和显式范围核对之后再审安装保护范围。

国际 14 App 的正常官方交付路径已另存 S44 调查。万豪官网链接到同包名应用宝，公开页面显示 11.15.0，但目标机普通入口实际 403，未取得完整包，不能据公开 versionName 断言适用新版本。S44 原失败保留，不改 UA、DNS、IP、TLS 或地区条件重试。

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

固定九 PID 的只读归属观察 `1a1b2e0972a-fc05-8016` 已 durable exit 0：八个完整身份属于其他既有服务，一个进程在读取时已不在。未找到本升级任务所有、可回收的运行进程；未读命令行或环境、未发信号、未改变服务。原 cwd/exe/cgroup 正文保留私有，仅公开摘要与完整 SHA。没有 build09，也没有以删除旧产物代替内存准入。

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
- 检查点 11 已提交并推送：`366f94b69b65aa122b10e80ad5e2e8097a75f294`，tree `4cedec3ccd1f57fa23a3de9e26827f9b51489540`。它冻结 45/85/255 完整关联、microG 独立采集更正、贝壳阶段 A 和猪八戒 S43 的实际结果；本检查点继续保留所有原失败与历史快照。
- 检查点 12 已提交并推送：`c79a17933966b5c61c76adfb0b4995f2ce5b7c25`，tree `1bd49d4168c0232ffad9f48d4c17e6c227a81b10`。它冻结 microG 有效权限解释、原 b03 因 native46 停止、贝壳阶段 B 与 fresh inspect/reader、猪八戒 source-stage 和万豪 S44 HTTP 403；之后的新发现与搜索失败由检查点 13 接续。
- 检查点 13 已提交并推送：`fdff6f219713ab53696059b9d55599c5bcc504c5`，tree `6a96da0e562d21a3457b73dbae94d165dcead288`。它冻结完整native46发现、NDK正常签名/manifest审计、ZBJ同签名升级和实际48包身份原文、r3清单、旧产物空间观察、原15GiB RAM不足及最新搜索失败的no-action阶段A。阶段B、新helper实际构建和IHG403由检查点14接续；没有删除旧产物。
