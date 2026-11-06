# Pocket4 旧产物与现行依赖保留计划

状态：**仅根据本地原始回执形成的观察方案；没有读取目标机，没有删除、移动、停进程或修改权限。**

当前生产回归通过的 App 数为 0，清理项为 0。APK 解析、签名验证、正常安装成功和系统目录枚举，分别证明其对应事实，不替代登录或访客、核心操作、网络、存储、权限拒绝恢复、长时间运行、重启及故障恢复的完整验收。

## 本次实际完成的本地工作

`build_local_catalog.py` 实际读取并校验 28 份固定本地来源，生成 865,191 B 的 `PATH_CATALOG.json`，SHA256 为 `6ba1391d24c056301612eb9d5fbc2ff5185c65a163dad79358d0fdcd402ac842`。所有来源均有完整文件大小、SHA256 和 JSON 字段索引，没有对大整数进行 JavaScript 数值往返。

原始提取包括 795 个绝对地址引用。随后 `prepare_observation_plan.py` 将其明确分为 **488 个宿主文件路径、305 个 Android root 路径、2 个非文件系统的 cgroup 地址**。`/init` 归属于已持有的 Android root；两个 `ControlGroup` 字符串不会作为宿主目录遍历。原提取文件保留，分层解释在 `TYPED_REFERENCES.json`。两次本地执行均 exit 0、stderr 0；完整 stdout/stderr 分别保存。

这些地址包含实际回执、现行源代码合同、已审计划及父目录引用。每项都保留来源类型，**目录出现在计划或源码中，不等于它现在存在，更不等于它已经不用**。尚未进行当前空间占用、挂载来源、硬链接或进程引用的现场观察。

## 已证实的保留对象

| 对象 | 具体路径或依据 | 当前处理 |
|---|---|---|
| 当前 Main 的 typed guard 与原始身份 | `/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/` | 保留原始 baseline、qualification、guard、transition、退出证明、source 闭包和回执；后续观察重新绑定实际角色 |
| 当前宿主配置 | `/etc/droidloom/cell.json`，7656 B，`f64a9f9a63e76ac2bf765e8f98bb2f9a91a326b38f86b6e3c4ac512d60303bdc` | 保留；本地只掌握 pin，没有据此猜测镜像或存储路径 |
| 现行生命周期 wrapper | `/usr/local/libexec/droidloom-compat/unshare`，6290 B，`df2365c026cc578048ce22ebd1b22bfefc25ccc144146683d845ec828c61bf1f` | 保留实测源码、部署回执、实际激活证据及旧版独立留存；不能只按新文件落盘宣称运行生效 |
| 当前 presenter | `/opt/pocket4-presenter-timing-20261104-r10/payload/droidloom-wayland`，7026568 B，`47f34d5f68783a372283cb63a42034d5899e270524cca40122bf28fd5e903f24` | 虽然目录含旧日期，仍是 baseline 的实际 executable；只观察精确文件，不扫描 `/opt` |
| 当前 native 工具 | `/usr/bin/droidloomd`、`/usr/bin/droidloomctl`、launcher 的 `/usr/bin/python3.14`，以及原源固定的 supervisor/native unshare 路径 | 按实际完整身份保留；CLI 的已证 UID/GID 1000 不被伪造为 root owner |
| 当前 Android framework 与翻译引擎 | 52 项 classpath 文件；`/system/lib64/libberberis_arm64.so`；init、composer、SurfaceFlinger、zygote/system_server executable | 路径坐标为 Android 根或对应进程 mount view，不能与同名宿主路径混用；保留原 pin 和挂载关系 |
| 旧显式 47 包范围 | `/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2/app-scope.private.json`，58854 B，`44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f` | 保护 87 个 APK 及 94 个 CE/DE 顶层数据目录；不遍历业务数据；该范围不是当前全部安装包 |
| 已升级 App 的旧 APK 留存 | 11 次正常升级的 12 个 `previous-*.apk`，完整路径和原 pin 见 `DEPENDENCY_PROTECTION.json` | 全部保留，等待各自生产回归；不能手动删除 PackageManager 管理的旧 `/data/app` 路径 |
| 11 次升级的最终 APK 与验签输入 | 原始成功回执中的已安装 APK、候选副本、下载和签名回执 | 保留最终版本可复现的完整 base/split 集、官方来源与签名证据；后续可评估重复副本，但现在没有删除资格 |
| 待安装猪八戒候选 | `/home/alex/work/pocket4-launcher-official-candidates-20261106-zbj-tail-s41-r2/com.zhubajie.client.apk`，166873622 B，`1822af13f666fea9814a7e571d50cc7def3aad72426d2e3eaa9101dcd6eaefa0` | 实际官方验签输入；本方案不将安装计划路径当成已安装产物 |
| 官方 AAPT2 工具及受控布局 | `/var/lib/pocket4-official-aapt2-host-tool-proof-20261106-r3/toolchain/platform/bin/aapt2`，6489808 B，`d0c30c343c61bfdc837abd02e195741dba7407bcb61ca34e037bcc1dc26ea06c` | 连同原 JAR、7 个静态 ELF 绑定、5 个 RUNPATH 目录和原 proof 保留；空 `lib64` 目录也参与合同，不可随意删除或搬动 |
| QA/helper/sidecar 的源和运行证据 | 当前重建的 recorder source contract、实际生成、build/install/state、业务后置条件及错误结算闭包 | 原 FAILED/UNKNOWN 不改写；仍被现行合同引用的旧 flow/source/receipt 路径继续保留 |

### 12 个旧 APK 的量级

原成功回执记录的逻辑字节合计为 **2,136,945,962 B，约 1.99 GiB**，分布在 11 个升级事务目录。京东原安装包含 base 与 ABI split，必须把两件完整留存作为一组；不能只数 `previous-base.apk`。

| 包 | 留存件数 | 原回执逻辑字节 |
|---|---:|---:|
| `com.jingdong.app.mall` | 2 | 294389107 |
| `com.lianjia.beike` | 1 | 227573032 |
| `com.rytong.airchina` | 1 | 206624542 |
| `com.rytong.ceair` | 1 | 220958172 |
| `com.sdu.didi.psnger` | 1 | 94582884 |
| `com.ss.android.ugc.aweme` | 1 | 360503779 |
| `com.taobao.taobao` | 1 | 95402496 |
| `com.tencent.mm` | 1 | 285283432 |
| `com.xunmeng.pinduoduo` | 1 | 26325737 |
| `ctrip.android.view` | 1 | 98783628 |
| `tv.danmaku.bili` | 1 | 226519153 |

这张表没有证明当前文件仍在，也没有测量 `st_blocks`、稀疏区、压缩、reflink、快照或硬链接，因此**不是可回收空间表**。

## 468/469 与当前 470 的真实依赖

当前已资格验证的 builder ELF 位于：

`/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106/compile01/cargo-target/debug/droidloom-update`

其实际大小为 34,817,256 B，SHA256 为 `e1d3dd7caf023e4709c2617318de97cc17906aae595b33c4c3290358e7d0dee5`。完整 498 文件源码在同根的 `builder-source`，源码清单是 `candidate-source-manifest.json`，99075 B，`f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd`。这些是当前构建资格的输入，不能把 `compile01`、`debug` 或旧日期当成删除理由。

当前 qualification 仍明确引用：

- `/home/alex/work/pocket4-native-typed-ingress-builder468-provider-closure-compile-03-20261106/attempt01/` 下的 `dependency-inputs-before.json`、`result.json`、`copied-builder-source-manifest.json`、`tool-inputs-before.json`。
- `/home/alex/work/pocket4-native-typed-ingress-builder469-native-provider-compile-01-20261106/` 下的 `qualify02/result.json`、`compile02/result.json`、`candidate-source-manifest.json`。
- `/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-work-01-20261105/` 及其中的 source/input、`package-build.lock`、`aosp-source-update.lock`。
- preparation 回执中固定的 Teto、Mesa、Python source/content manifests 和原输入 authority；它们属于构建复现的证据链。

旧 468 ELF 的缺失已经是历史事实；本方案不会补造或假定该 ELF 当前存在。旧回执中的失败、缺失与当前 470 的独立资格分别保存。

build08 的根是：

`/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-08-20261106`

其实际 outer fence 在 **MemAvailable 不足 15 GiB** 时拒绝，`inner_build_called=false`。因此 `android-out` 目前只是计划字段，不能把它列为已产生的新 framework，也不能估计该目录的空间。这里最先需要观察的是实际存在的 stage/资源回执和目录元数据。

上述结论的具体 JSON 字段和来源 hash 均在 `PATH_CATALOG.json` 与 `INPUT_CLOSURE.json`，不是按目录名称推断。

## 跨项目 JDK：只保护精确依赖，不扩入其他项目

已实际通过的 APK 审计使用以下前缀中的 9 个文件：

`/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/jdk/jdk21/linux-x86/`

- `bin/java`
- `conf/security/java.security`
- `lib/modules`
- `release`
- `lib/jvm.cfg`
- `lib/libjava.so`
- `lib/libjimage.so`
- `lib/libjli.so`
- `lib/server/libjvm.so`

12 项原工具 binding 中，这 9 项有完整 stat/hash；另 3 项是系统 aapt/apksigner/apksig。JDK 的实际所有者与模式按原回执保留，不更改权限。

观察范围仅包含这 9 个精确文件及解析其路径必需的父目录身份；**不列举、遍历、搬移或清理 `audio-target-build-r1` 及其上层项目**。若以后最终复现必须迁移这组工具，应另建完整、同字节、正常资格验证的依赖合同；在新合同实际通过前，现有精确路径仍然是必保留输入。

## 一次有界只读观察的具体范围

机器可审计划在 `OBSERVATION_PLAN.review-only.json`，它不是 process 请求，也没有执行入口。具体 host worker 和固定 process packet 仍需根代理在真正执行前审阅。

1. 沿已通过的 typed guard、原持有 FD reader 和 owned FFI 生命周期，重新绑定当前 8 个角色及原 action coordinator。PID 数字只用作已证身份参考，不作为单独权限。既有 UI、安装、生命周期和构建工作不会被打断。
2. 仅读取 held 进程的 mountinfo、8 角色 maps/fdinfo 元数据，以及已明确路径的 stat/hash 合同。通过实际 mount ID、dev/inode、root 与 executable 关系定位运行依赖。未知 overlay/loop/image backing 路径只报告为待审依赖，不自动跨目录读取。
3. 逐项检查 488 个宿主和 305 个 Android 根的精确元数据引用。外部 JDK 只查 9 件；CE/DE 只查顶层身份；私有业务文件内容不读。
4. 仅对 `TREE_SCOPES.review-only.json` 固定的 16 个任务目录作无 symlink、无跨 mount 的有界元数据遍历：11 个旧 APK 事务目录，468/469/470 三个 builder 根，现行 shared framework work 和失败 build08 根。不会遍历整个 `/home/alex/work`、`/opt`、`/var/lib`。
5. 逐个 root 报告完整性、文件计数、稳定 before/after、`st_size` 与 `st_blocks*512`。按真正 `(dev, inode)` 归并硬链接，列出已知 inode 与现行引用的交叉关系。未见的 alias、reflink、快照和其他进程仍标 UNKNOWN。
6. 前后复核、关闭全部观察/lease FD、正常结算 owned child 与 pidfd，再结合原始 stdout 和权威 durable terminal 接受结果。任一界限触发或目录变化，保留 INCOMPLETE 与实见原因，不产生清理资格。

建议一次外层 240 秒、内层 180 秒，其中树遍历 90 秒、总 100000 条、深度 32；公共摘要最多 512 KiB，完整 metadata artifact 最多 32 MiB。CPU25%、MemoryMax512 MiB、nice10；既有 typed guard 自身的 hash/身份界限不放宽。最终精确资源参数随 host worker 一起审，不把这份规划当成已经执行的限制证明。

8 角色 maps/fd 样本能证明某个对象正在使用，不能证明所有 App、其他进程或别的项目都没有引用。只看 `nlink=1` 也不够证明当前文件可删。

## 明确未解决的部分

- 原生目录已观察到第 46 个 Launcher：`com.example.ndk_tests/com.example.ndk_tests.NdkTestsActivity`。权限批次 b03 因此正常 FAILED/STOP3；原 47 包保护范围没有被篡改。新的实际 PM、resolver、UID、版本、完整 APK 与签名仍由独立发现工作确定。本清单不冒称当前全集。
- 运行 image/rootfs 的宿主 backing 文件、overlay 层及完整挂载图尚未在这些本地来源中闭合。不会猜测 Docker 或 reDroid 的存储位置。
- 当前或已退休 reDroid 的精确 container/image ID 与存储路径尚未在本次选定证据中找到。没有据此扫描容器总目录，更没有 prune 计划。
- 原始旧版回执、观察工具、QA source contract 和构建 source lock 仍互相引用；不能只保留一个“最新”目录就删掉其输入。
- 存量文件的空间与 inode 现况尚未观察；`reclaimable_bytes` 始终为 null。

## 让最终源码、配置与复现真正脱离可删中间目录

最终留存应包含 owned 源码和补丁、锁定的 provider/source/dependency 清单、正常构建命令与资源前提、实际构建产物和运行配置、官方签名完整 APK 集、签名与来源回执、sidecar/UIAutomator/中文输入定位方案、每 App 的真实验收记录，以及独立保留的失败与修复关联。

保留策略有两个可核对的结果：**仍被最终合同引用的路径继续保护；需要回收的中间目录必须先不再被最终合同引用。** 迁移时不能重写旧回执、篡改旧 guard 或把旧 PASS 指到新 inode。应建立新的明确源/配置/工具路径合同，按原安全约束正常构建和绑定，证明最终复现不再读取拟清理目录，再做逐 App 与 framework 的生产回归。

最终配置中必须保留用户选择与授权边界：Main 不借用独立 Bili Accept 授权，美团外卖位置权限不主动开启，正常签名与完整性检查不绕过，仍沿原 sidecar 和容器内 UI Automator，无新增 ADB 依赖。私有业务 UI、账号、凭据和权限原文不进入公共 Git 复现包。

直到这些条件成为实际回执，本计划没有任何删除命令，也没有“已释放空间”或“生产就绪”的结论。
