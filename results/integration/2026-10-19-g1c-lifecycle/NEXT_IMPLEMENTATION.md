# G1-c 之后的具体施工单

基线为 #207 的 Process 映像生命周期。此文件是后续实施约束与验收计划，不提供已经开放的能力。

## 1. 先完成可信静态映像，再开放最小 ReadUsage

第一可交付 profile 限定为 x86_64、单 CPU、固定静态用户 ELF、一个由原 native CPU owner 持有的 N0 100 ms observe 目标。使用原 loader 与 PreparedInitialProcess，在实际 Task 首次 resume 之前建立映像认证和授权绑定。

认证对象必须是实际映射的同一批不可变字节及装载形态。路径、UID0、PID1、环境变量、调用了 NativeGrant 构造函数或者仅计算出一个 hash，都不足以证明可信身份。可信描述及其根应来自明确固定并验证的启动输入；准备阶段需绑定真实 Process／VMAR／Task／image key、受准入的入口与段布局。初始 profile 不接受 PT_INTERP／shebang 的可信形态，避免把解释器与被解释内容的授权问题隐藏在路径检查里。

| 现有入口 | 下一步工作 | 必须拒绝／关闭的具体情况 |
| --- | --- | --- |
| `process/process/init_proc.rs` 原 create_init／PreparedInitialProcess | 在实际 loader 与首次 resume 之间建立不可变映像认证；消费对象绑定后才能授予 scoped grant | 外国 Process／Task／VMAR、旧 image key、prepared 重复使用、未认证字节 |
| `process/execve.rs` 与 `process/process/image.rs` | 保留前边界失败语义；不可逆替换先撤销旧映像的资格；新映像独立准入 | 从旧 fd、旧 token、失败替换或代际耗尽恢复授权 |
| `/proc/[pid]/mem` 原打开及写路径 | 覆盖已打开句柄的写入，并与最终身份／撤销同步 | 先开句柄后赋权，再从旧句柄写受信任代码或状态 |
| ptrace 状态及 syscall | 处理 TRACEME、已经存在的 tracer、数据及寄存器修改；初期拒绝不支持的受信任形态 | 仅阻止新的 attach，却保留已有 debugger 改写能力 |
| `vm/vmar/vm_mapping.rs` | 证明实际映像内容和权限不能经 MAY_WRITE、forced alien fault／COW 重新变为可写 | 只把页表标成 RX，仍允许强制写、别名或权限升级 |
| `process/clone.rs` | 处理独立 Process 共享 VMAR 的 `CLONE_VM` 路径 | 子进程无 grant 却可通过共享地址空间篡改已授权父进程 |
| 原 `cgroupfs/controller/cpu/native.rs` | 在原 membership／owner 上保存 canonical scoped grant，并在原一致快照处读取 usage | 另建影子 owner／重复账本；对象或 membership 已替换但旧授权仍有效 |

最终授权检查必须在实际资源使用的同步点完成。先把用户请求复制到有界内核缓冲，再检查 request、原对象、完整映像身份与 canonical grant；撤销与最终使用要有可说明的线性化顺序。不要把长期 image 锁延伸到用户复制、阻塞 I/O 或 scheduler。新增跨对象锁序须对现有 VMAR → TaskSet → image 及资源 owner 顺序做具体审查，不以多次互相独立的检查代替原子关系。

ReadUsage 第一正例应由实际已装载并首次调度的静态用户 ELF 发出 HOS2 帧，读取真实原 owner 的 usage。负例至少包含外国对象、继承旧 fd、exec 后旧 key、已撤销 grant、已打开写别名、ptrace、CLONE_VM、重复 prepared 消费及代际耗尽。原普通 guest、完整 core／OSTD、七负控和 Linux 工作负载继续在同一源码上验收。取得这些结果之后，才把 ReadUsage 加入 QueryAbi 宣告。

## 2. 接原 Hepta Operations 的持久交付

Hepta 保持原 Authority／Operations 为效果所有者。内核 backend 不另造一个独立任务中心、命令 outbox 或效果账本。接合继续使用原逻辑操作键 `K = (scope, operation)` 和原内核投递身份 `D = (boot, CapSpace, sequence)`。

| 顺序 | 应有行为 | 崩溃／重试验收 |
| --- | --- | --- |
| 首次发送前 | 持久记录原请求及 K↔D 映射 | 落盘前不得发送；重启后不得生成第二个 D 当作同一操作的重试 |
| 投递 | 向同一原 owner、同一映像／授权及同一 D 执行请求 | transport timeout 不能推断资源效果失败 |
| 不确定结果 | 保持 Unknown，使用同一 D 查询交付状态 | 重复请求不产生第二次效果；boot／CapSpace 变化进入明确恢复分支 |
| 终局确认 | 原 Operations 持久记录终局证据 | 未持久确认时不得提前丢弃内核 receipt |
| 退役 | 只推进已确认的连续 RetireThrough 前缀 | 洞、乱序确认、重复 retire 和重启后重放均保留正确语义 |

ReadUsage 之后分别实现 InstallBudget、QueryDelivery、RetireThrough 的真实 guest 效果与恢复语义。报文 codec、host 模型、Linux 外部模拟器和 Asterinas 实际资源效果分别留证。

## 3. 真实 W1 与交互设备 organ

原 Hepta 静态进程需要在 Asterinas 上实际装载、运行并访问所需文件、IPC、子进程与 SQLite／持久存储路径。现有 Ubuntu32、SCM27 和 RLIMIT37 提供具体兼容基础，但不能代替原二进制 W1。原 W1 所需 syscall／库／rootfs 应逐项固定，只对实测缺口扩展内核。

桌面／移动端设备交互沿原 Hepta 工具与设备权限模型接入。用户态设备 agent 负责平台 API、窗口／输入／辅助功能、设备状态和结果观察；Hepta 原 Operations 负责授权、审批、执行身份及故障恢复。OS kernel 提供进程、内存、调度、设备隔离与受限 native resource 接口。每个设备 profile 要同时验证真实观测、真实动作、取消、断线、重试和用户撤销。

先完成现有 Linux host profile 的实际闭环，再按固定输入验收 Asterinas 本机图形、Android Binder／ART／图形／APK、ARM64／页大小与具体 BSP。跨设备后端共享逻辑契约，但不能相互继承运行资格。

## 4. Hepta UI 与依赖失败的具体修复顺序

Architecture fixture 修复已经通过原完整必需门禁。UI `89933fdc…` 的 source 原六例仍有一个 native completion 失败；同 tree 的 base 六例成功不足以形成修复结果。

1. 保留原 source 的 503／79 字节／SDK503／`loadingFailed`／随后 `finished()` 等待这一失败时间线，以及 base 成功对照。固定原 Playwright、实际浏览器 version／revision、SDK 与 WASM 输入；CI 的 hash 声明和实际下载重算分别注明。
2. 以 Chromium 提交 `62473ad0f747e245e514c93e741bb8e168a2a207` 为候选根因，确认准备采用的正式浏览器构建实际包含该修复。若需要背移补丁，单列浏览器源码及构建，不把诊断用较新浏览器的一次成功写成原生产通过。
3. 同时重跑原六例和截断、显式取消、声明超限、流式超限负控；保留有效响应和取消请求各自的原完成语义。换浏览器版本属于实际依赖变更，应记录修复前后的具体构建、原错误消失及所有错误边界保留。
4. 若只改测试完成通知，必须把已发生的 `requestfailed` 收敛为明确失败，不能把它解释为成功响应、移除原生完成要求或依赖延长90秒消失。`Response.finished()` 不结束的问题与浏览器为何报取消是两个需要各自验证的层次。
5. 在最终头全部原必需检查通过后再正常合并 #2885。新 `cargo-deny` 的根因必须来自新头原日志、注解或原报告；没有取得具体依赖诊断之前，不继承旧头失败原因，也不关闭安全检查。

## 5. 何时评估替换内核部分

继续使用现有可构建、可审查、可运行的 Asterinas fork。在每个阶段记录具体失败路径、原始工作负载、可接受目标、测量误差、候选修改及其结果。

只有发现下列实际证据后，才建立替换提案：原隔离模型无法表示所需 authority 边界；原地址空间／调度结构使已定义工作负载持续无法满足要求；关键硬件缺少可实现的 owner／DMA／IRQ 生命周期；或特定兼容成本在实测后显著超过有界替代层。首先比较局部替换与继续复用，原 ABI 和回归保留为两条实现的共同判据。

自建 Rust kernel 的初步实验应围绕这个已测量的阻塞形成可证伪原型，证明该单点确实改善，再考虑扩展；不能以启动成功、打印日志、一个 LLM demo 或语言一致作为整机替换的接受条件。没有上述证据时，持续推进原 native owner、可信映像、Hepta 持久交付及设备 profile 的成本和结果更容易评估。
