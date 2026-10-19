# R12：G1-c Process 映像生命周期与 Hepta 失败收敛

本轮把上一轮审计提出的 G1-c 接合点推进为实际内核代码、两份具体手册和真实运行证据。[desktop PR #207](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/207) 已于 2026-10-19 14:15:35 UTC 正常合并为 `9f66434889cc3bce31cfcccda950f0c48d6fa1b3`。最终执行源码为 `104204016dcdea57ab73c091b1edd13008ae9a19`，tree 为 `179b076747d19c3e07ee19a665e3968c33c598ce`。本报告记录本地执行与远端检查各自的状态，不将先前 #205 的运行资格转记到新源码。

## 1. 已兑现的进展

原 `Process` 现在统一管理映像的 epoch、boot-local nonce、Live／Closing／Closed 与首次启动状态。不可逆 exec 和退出入口先关闭旧会话；可恢复的前边界 exec 失败以及非最后线程退出保持原会话。初始装载通过私有、不可 Clone 的 `PreparedInitialProcess` 绑定真实 Process／VMAR／Task／image key，验证并消费一次后才进入原登记和调度路径。

最终源码已在固定 `nightly-2026-07-21` 下完成原完整 ktest：core 238/238；OSTD 221 reported，含 3 个明确 VMX soft skip，实际执行通过下界 218；两个 QEMU 均退出 33，无过滤或超时。随后原普通内核 fresh run 完整通过，boot 与 QueryAbi guest 都退出 33，18 个精确标记各一次，7346 个 tracked 文件的三次原源码快照一致。独立审查分别保存并核验首轮、最终轮次的实际串口、源码身份、锁和 ELF。

HOS2 仍只开放 QueryAbi。ReadUsage、InstallBudget、QueryDelivery、RetireThrough 的有效帧仍返回 `EOPNOTSUPP`。Prepared 绑定没有建立不可变映像认证，也没有生成资源授权。四个真实操作、Hepta 原 Operations K↔D 持久交付和 Asterinas 内真实 W1 仍是后续工程范围。[技术手册](../../../docs/ASTERINAS_PROCESS_IMAGE_G1C.md)、[开发与验证手册](../../../tests/kernel/control/PROCESS_IMAGE_G1C.md)

## 2. 固定源码与审查边界

| 对象 | 固定身份 | 本轮采用的范围 |
| --- | --- | --- |
| 本轮起始 main | `7c675e1d3efe46587edeebe14bd90ac1a842ffbf`；tree `3d5902c8503e7b5fa79552d9fa657023f3f3520c` | 已合 #205 产品及 #206 审计基线 |
| G1-c 首提交 | `72c8dff3f0145a7e16b7095d48a3e7faaf192685`；tree `e2089e2350772a6cb965b3131820abea499f767d` | 第一轮实际完整 ktest；不能替代最终提交 |
| G1-c 最终执行头 | `104204016dcdea57ab73c091b1edd13008ae9a19`；tree `179b076747d19c3e07ee19a665e3968c33c598ce` | 三 Rust 文件的固定 nightly 格式及 checked-add 源码正则空白适配后，重新执行原完整门禁 |
| Hepta #2885 新执行头 | `89933fdc84ed1151f04609a1881ab24aaef119b4`；tree `25b2a7b559549fba0d22fa7d62d78c76c13cd5ce` | 原分支上两文件修正；Architecture fixture 和 UI 被动网络诊断 |
| Hepta 原失败头 | `43a638d4e25ebc5a8b06babcd1c75c9acac53179` | 旧 52 项结果和原 UI 失败用于定位；不转记为新头结果 |

core／OSTD 原 runner 的 `source-inputs.json` 验证 118 个上游构建／manifest 输入，并保存干净 Git head、工具与实际 generated locks。完整 7346 文件的前后字节快照来自普通产品 runner；两种证据的保证范围分别记录。官方普通构建的204包生成锁本体未包含在ZIP中：原wrapper记录的摘要等于固定Git锁，不能把这条记录写成独立重读了缺失的生成锁。官方主机QEMU／OSDK二进制本体也未上传，其hash按原环境记录保留。

## 3. 实际实现与解决的问题

### 3.1 会话绑定原 Process 和完整映像身份

设备先核对 Weak 升级与 exact `Arc<Process>`，再在同一 image mutex 下核对完整 key、Live 状态与非零 nonce。epoch 和 nonce 使用 checked arithmetic；空间耗尽会关闭当前映像，不回绕、不恢复旧身份。

argv／env、文件查找、权限和 loader 的前边界失败保留当前 Live 映像。在原 `TaskSet::start_execve` 接受不可逆替换后，先进入 Closing，再终止其他线程。成功提交建立新的 epoch 和尚未分配的 namespace；不可逆失败或溢出关闭映像并沿用原致命退出路径。`exit_group`、最后线程退出以及最终 VMAR 释放分别接入原生命周期。

### 3.2 首次调度前的一次性对象绑定

私有 loader／Task builder 把同一个 VMAR 交给实际装载、PosixThreadBuilder 和 prepared 对象。运行时再核对当前 Process VMAR、唯一 main Task、Task 的 Weak Process、退出／exec 状态和完整 image key。首次运行性来自私有、尚未公布且尚未调度的构造路径及显式首次运行状态；仅检查 `is_exited == false` 不能建立这一事实。

`resume(self)` 消费 prepared 状态、释放相关锁，然后执行原 session／group／PID 登记及调度。未消费对象 Drop 只关闭自己匹配的 Prepared 映像；旧 epoch token 无权关闭替换后的新映像。普通 fork 路径仍使用原 `Process::run`，并通过 Unprepared → Started 的一次性声明防止 prepared 绕过。

### 3.3 锁序和真实回归

完整绑定采用 **VMAR → TaskSet → image**，与原 `/proc/[pid]/mem`、maps 的访问方向相容。image 方法不反取外层资源或 scheduler 锁；用户复制、PID 登记和调度不在 image 临界区进行。CPU owner、结算尾账、BOOTTIME、原七项生产负控与固定构建输入没有因本轮改变。

18 个新增 ktest 操作真实但未调度的 Process／Task／VMAR，包括外国对象、旧 key、不可逆失败、代际与 nonce 耗尽、一次消费、Drop、替换 VMAR 和退出组状态。它们不等于完整执行所有 fatal exec syscall；普通 guest 另外实际执行 EFAULT／ENOENT exec、同进程 pthread 共享和非最后线程退出。[18 项逐名开发表](../../../tests/kernel/control/PROCESS_IMAGE_G1C.md)

## 4. 验证状态与首轮失败记录

最终运行与检查明细由本目录的执行证据和独立收据补充。未取得本轮实际结果的门禁继续保持未完成，不使用 #205 的历史结果代替。

| 层次 | 已实际取得的结果 | 范围 |
| --- | --- | --- |
| 最终源码格式／host 契约 | 固定 nightly 9 Rust 文件 rustfmt 通过；原 spec 36 项通过；原 control 正常／优化各 16 项通过 | control 两种模式有重叠，不相加为 32 个不同测试 |
| 最终完整 core | 238 passed；0 failed／filtered／soft skip；QEMU33 | 包含 18 个新增测试，逐名独立核验 |
| 最终完整 OSTD | 221 reported；3 soft skip；218 执行通过下界；QEMU33 | VMX／EPT 未取得硬件执行资格 |
| 普通产品与 QueryAbi | fresh run 原 gate 通过；7346 源码三快照一致；18 标记各一次；boot／guest QEMU33 | ActionChoice::Run；四资源操作仍关闭 |
| SCM_RIGHTS 原 Linux 对照 | 同一冻结 ELF 27/27，通过原精确 stdout／空 stderr 条件 | 第一次默认 sandbox 的权限失败另存 |
| SCM_RIGHTS 普通 guest | 同一 ELF、同一普通 kernel 27/27；QEMU33 | stream／datagram／seqpacket、CLOEXEC 与 exec 继承 |
| RLIMIT_NOFILE 原 Linux／普通 guest | 同一冻结 ELF 两端 37/37；guest QEMU33 | 第一次默认 sandbox 的权限失败另存 |
| Ubuntu full32 原 Linux／普通 guest | 同一预冻结 image 的 32 项两端全通过；逐项 stdout 字节相同、stderr 为空、进程退出 0 | 原 28 ELF 场景、3 Python 场景和 1 locked Tokio 场景全部执行 |
| CPU 原四组配置 | 本地 0.94999%、0.82946%、46.77474%、45.29887%；原上界分别 1.2%、1.2%、52%、52% | 原 4 秒、先执行未限流活跃基线、无输入改变 |
| 1／2 vCPU 原探针 | 本地 1 vCPU 0.910%／0.800%；2 vCPU 0.875%／0.815%，均低于原 3% | 2 vCPU 未限流 196.92%／198.10%，超过原 145% 活跃下界；不产生 full SMP 资格 |
| 七个原生产负控 | 全部实际完成；238 项的失败数依次 3／4／3／1／4／1／2；原 gate 退出 1，QEMU65 | 成功检出指定错误；18 项新增 G1-c 测试保留通过，原负控源码和 commit bundle 保存 |
| 最终远端五项检查 | GitHub 在最终 `10420401…` 上全部 success | G0、A01、A06、Analyze (python)、CodeQL；普通合并状态另记 |
| 官方 A06 原运行包 | run `39256580996`、job `118073271911`、artifact `12190114844` | 156126595 B；SHA-256 `984adcb6fd87dbef0c4b68223e8bde1811a5e00a31a447c597e20810b073067d`；1172 成员 CRC 全过 |

第一轮普通产品执行中的 boot 和 guest 均正常，但最后的 source snapshot 发现一个 untracked `kernel/asterinas/kernel/OSDK.toml`，原 runner 整体失败。该文件字节与原 minimal manifest 相同；原件、stat 和失败结果已经保留。移出该已知构建临时文件、确认干净源码后，原 runner 在新输出目录完整重跑成功。文件具体产生／恢复机制尚未确认，因此没有声称修复了一个已定位的产品清理 bug，也没有删除首次失败历史。

SCM 首轮默认 sandbox 在 3 个 credentials-with-rights 场景触发 `SO_PASSCRED` 的 EPERM；RLIMIT 首轮在 5 个 listener bind 场景触发 EPERM。获得正常宿主 syscall 访问后，同一个执行前冻结、没有重编译的 ELF 分别通过 27 和 37 项。原失败、权限上下文、两次输出和 hash 分开保留；不是修改 expected facts 或跳过失败测试。

### 4.1 官方结果与本地结果各自绑定

官方普通 kernel ELF 为 `c407eb788ba660642e4e4dfe245e2be48a6723bc8e91b9311b9593861e007159`；本地普通 ELF 为 `1bdc27f45afb2789447473cdf100a8fd67c84111bcec650a1fa96c18edb6163b`。构建宿主／路径不同，本报告不声称两者可逐字节复现；在各自轮次内部，普通启动、SCM、RLIMIT、full32、CPU 和 SMP 探针使用的实际 ELF 链均一致。

官方四组 CPU 读数为 0.92499%、0.92702%、47.09100%、47.44758%；1 vCPU 两次 0.900%／0.900%，2 vCPU 为 0.900%／0.905%。官方两线程未限流基线为 198.928% 和 198.849%，证明样本实际使用两个 vCPU。以上数值从原串口的 CPU 时间／墙钟时间重算；没有放宽原阈值。它们验证粗粒度配额不失效，不代表严格 1% SLA、完整 SMP、真实物理切换原子性或原生 HOS2 效果。

本地 full32 frozen input 为 `96aa95ba2105fc9092c860f301d78454b2cb92db6e8124858c109bb83b25f20a`，在 Linux reference 前形成；其 669 个运行库文件与官方运行的 673 个运行库文件属于不同宿主产生的独立冻结镜像，各自在同次 Linux／guest 比较中保持一致。不能把两轮镜像身份混用。退出进程组清理通过；本地原临时 chroot 目录仍可观察到且与原 image 相符，目录清理的具体机制尚未确证，未写成所有临时目录消失。

## 5. 文档覆盖与全模块进度

上一轮已形成 [A00–A10 模块矩阵](../2026-10-19-g1b-usage/module-matrix.json)及[完整模块审计](../2026-10-19-g1b-usage/README.md)。其中 62 个入口包括文档、契约和验证脚本，不能称为 62 本技术手册，也不能推定每个模块都有两本独占命名且覆盖全部未来功能的文档。

本轮逐项重新读取最终 `10420401…` 下的 64 个当前入口字节，核对 Git blob、mode、size 与 SHA-256，其中 60 个 Markdown、4 个契约／验证文件。当前各模块进度、下段施工与文档身份见[更新矩阵](module-matrix.json)。原 62 个入口的具体内容审查保留上一轮来源，新增两手册另对实际代码及执行结果审查；存在性计数不能代替手册覆盖质量。

本轮新增两份对应实际代码的专门手册，并接入 INDEX、STATUS 与原 kernel/control README：

| 文件 | 具体内容 |
| --- | --- |
| [ASTERINAS_PROCESS_IMAGE_G1C.md](../../../docs/ASTERINAS_PROCESS_IMAGE_G1C.md) | 真实代码入口、状态机、首次调度对象绑定、锁序、CPU 关系、现有边界与下一静态映像接合点 |
| [PROCESS_IMAGE_G1C.md](../../../tests/kernel/control/PROCESS_IMAGE_G1C.md) | 固定输入、18 个具体 ktest 与代码路径、普通 guest 标记、完整门禁命令、失败处理和验收范围 |

本轮主要改变 A05 的进度，并重新执行受影响的 A01／A04／A06 门禁。A02 的四项未开放操作、A07 的原 Operations 效果交付、A08 的 Android guest、A09 的实际设备／DMA／IRQ 资格，以及 A10 的 Asterinas 本机图形和移动端 profile，没有因这一生命周期切片自动完成。

## 6. Hepta #2885：已修部分与仍未闭合部分

Architecture 的临时 fixture 少拷贝了由 PR 分支新引入的 `hepta_ci_module_paths.py`。两文件候选中的四行补齐这一依赖后，原 Architecture 45 项本地全部通过；新头 base-merge CI 的原 `test_hepta_ci_exec*.py` 命令也取得 45 项、7.575 秒、OK 的真实日志，原两项 fixture 失败已消失。该 lane 声明 `native_execution_required=false`、`requires_source_head_success=true`；随后 source-head job 于 13:44:36 UTC 成功，Architecture required 汇总于 13:54:23 UTC 成功，完整 Architecture 必需门禁已经通过。依赖不在当前 main 的相同结构中，因此这四行不能脱离原分支直接 cherry-pick。

UI 修改仅在已有 CDP 连接上记录两条确切 API 路径的请求身份、原生完成／失败、有限响应头和原 `finished()` 等待起止。它不改变原六例、90 秒、27 条提取出的断言顺序、有界 body 读取或原浏览器接受条件。

固定 Makepad SDK 在 EOF 后只做状态与 timer 清理；不存在可直接删掉的“多余 EOF abort”。在相同 SDK、真实本地 HTTP 与合成 WASM 接收端的 12 场景独立诊断中，Chromium153 的两种完整 503 响应都出现 SDK 完整响应但原生 ERR_ABORTED；诊断用 157 正常结束。两版本的截断、显式取消、声明超限、流式超限共八个负控保持正确失败。该实验不是 Rust UI／gateway 的产品资格。[固定 SDK](https://github.com/kevinaboos/makepad/blob/337566c8b25d47f7e4fff6a202157b65bf183330/platform/src/os/web/web.js)

Chromium 官方提交 `62473ad0f747e245e514c93e741bb8e168a2a207` 的实际修复是在通知 client 之前记下完成／错误结果，避免关闭回调重入时把真正终态覆盖成取消。关键条件是 EOF 与最后一块数据分开到达，不是必须由服务端调用两次 write。上游同时增加 CancelAfterDone 与 CancelAfterError 等回归。[官方提交与 diff](https://github.com/chromium/chromium/commit/62473ad0f747e245e514c93e741bb8e168a2a207)

新 `89933fdc…` 的原产品产物已经取得。source-head 的原六例为 5 通过、640 timeout 1 失败；base-merge 的原六例全通过，两边 build manifest 的原始字节相同，其中记录的 SDK／WASM hash 相同。原浏览器产物未包含这些完整可执行字节，此处没有声称已在本地独立重算 SDK／WASM 二进制 hash。source 失败请求 `21200.22` 在 18152.954 ms 收到 503、Content-Length 79、no-store，18152.966 ms 收齐 79 字节，18153.312 ms SDK 记录 503，18153.487 ms 已发生原生 `loadingFailed ERR_ABORTED`。到 18955.793 ms 才开始原 `timeout-runtime.finished()` 等待，此后只有 start 没有 done，最后原 90 秒测试超时。原生失败早于等待开始约 802 ms，不能归因于 90 秒清理动作。

该实际事件序列与固定 SDK 的独立复现、上游已修复的完成状态重入问题一致；这是目前最有证据支持的归因，仍不等于在固定生产 Chromium 上做过带该补丁的修复前后对照。base lane 一次成功不能抹去 source lane 的失败。更改 JS 读取时序、合并服务端 write、忽略原生错误或延长超时，都没有获得根因修复的证据。浏览器补丁或正式版本更新必须保留原六例、取消／截断／超限负控及相同 SDK 语义，取得新的完整产品运行结果后才能形成修复结论。

最新已冻结的 14:10:06 UTC 快照返回 49 个已创建 checks：23 success、6 skipped、1 neutral、3 failure、14 in_progress、2 queued。三项实际失败为 UI source-head、`cargo-deny`、macOS ARM64 Bazel release build。后两项已从原 step 确认失败位置，详细原始原因尚未取得；cargo-deny 两次全文读取为 Transport closed，补读 check 注解端点不被连接器支持，没有把旧头原因写成新头根因。远端 Rust format 和 cargo shear 已成功，本地 `just` 不可用的旧尝试原样保留。#2885 仍为 Draft，未正常合并；Architecture 成功不等于整个 Hepta PR 可合。完整原件、具体时间线及后续修复方案见 [Hepta 专项报告](evidence/hepta/hepta-final-report-section.md) 和 [14:10 补充](evidence/hepta/ci-checks-update-20261019T141006Z.md)。

## 7. Asterinas 与自建 Rust kernel 的路线

当前继续受控 Asterinas fork。本轮已经直接在原 Process、VMAR、TaskSet、loader、exec 和退出路径上实现并运行关键切片，未出现只能重写整个内核才能解除的结构性障碍。下一步应把可信映像与 canonical resource owner 接通，再让 Hepta 原 Operations 控制这一真实后端。

设备控制产品还需要 Hepta 的授权、用户交互、设备 agent／平台适配、实际效果和故障恢复闭环。Linux host 上的 UI、QEMU 中的 CPU 控制和手机设备资格分别验收。内核不承载 LLM 推理、对话规划和交互工作流；这些组件保留在可更新、可隔离的用户态。

只有在具体驱动、隔离、持久性或关键调度需求经过原路径实现和测量后仍不能满足，并有可复现的结构证据，才评估替换特定 OSTD／kernel 子系统。全新 kernel 需要重新承担地址空间、进程／线程、文件与 IPC、ELF、驱动、中断／DMA、SMP、调试和兼容回归的成本；目前没有证据证明这种投入更快实现 Hepta organ。下一阶段的具体入口、接受条件与替代路线触发条件见[施工单](NEXT_IMPLEMENTATION.md)。

产品正常合并收据见 [normal-merge.json](evidence/local-and-review/pr207-runtime-review/normal-merge.json)。执行 head 与正常 merge 的 tree 完全相同；本报告的文件发布不新增内核运行资格。

## 8. 原件、校验与报告入口

- [固定结果摘要](SUMMARY.json)；[当前模块矩阵](module-matrix.json)；[后续施工单](NEXT_IMPLEMENTATION.md)。
- [产品正常合并收据](evidence/local-and-review/pr207-runtime-review/normal-merge.json)；[官方 green／普通源码独立审查](evidence/local-and-review/g1c-review/official-green-core-ordinary-review.json)；[官方 A04／CPU 审查](evidence/local-and-review/pr207-runtime-review/ordinary-cpu-review/review.json)；[官方七负控审查](evidence/local-and-review/g1c-lifecycle/official-negative-sequence-review.json)。
- [官方原始串口与源码快照选集](evidence/official-raw-evidence.zip)保存85个原 ZIP 成员的逐字节 XZ 副本及清单；[A04／CPU 原件选集](evidence/local-and-review/pr207-runtime-review/ordinary-cpu-review/selected-evidence.zip)保存完整逐例字节与输入链。ZIP SHA、原件 hash、压缩 hash、具体路径都在清单中。
- [Hepta 专项审查](evidence/hepta/hepta-final-report-section.md)、[14:10 状态补充](evidence/hepta/ci-checks-update-20261019T141006Z.md)、[原始文本清单](evidence/hepta/final-text-evidence-manifest.json)。这些来源保留各自观察截止，不把 pending 写成终态。

完整单独交付包为 `Trillionnium_R12_G1c_20261019_Evidence.zip`，**246987878 B**，SHA-256 **`1119a36a958a45e5f732d557f085452e88adbb432a34debf98502d526fefe123`**。包内1436个原文件、1168个唯一内容对象，原文件内容合计587521665 B；每个文件在打包后再次核对摘要。包内 `manifest.json` 逐路径映射原件，`verify_evidence.py` 可离线校验全部对象并导出原文件，不执行任何捕获程序。[包身份收据](archive-receipt.json)和[实际离线校验结果](archive-verification.json)分别记录包身份与1168个对象的成功复核。

完整包保留本地 ELF／image／serial／原失败、七负控 patch 与 commit bundle、官方完整 A06 ZIP 和 Hepta 文本证据。可重建 Cargo/Python cache、安装的整个工具链、旧#205预检、重复的临时chroot和包含浏览器截图的Hepta ZIP不在此包中；每项排除及其理由列在包内清单。实际使用的冻结 ELF、原镜像、输出与原始失败没有因这些排除被删减。
