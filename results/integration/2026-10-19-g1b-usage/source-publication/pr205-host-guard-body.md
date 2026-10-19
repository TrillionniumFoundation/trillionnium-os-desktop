## 当前候选（2026-10-19 10:53 UTC）

head `4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930` / tree `8eb809136a402cc54ba049b1e40dd174308c923f`，本地同树 `58c705eb1648acd83abe5b0872a41b3c910aa6c1`。相对首个 f966 候选，只更新既有 host source guard：限定原 settle_bandwidth 函数、核对 paired ns 端点和 retained owner，并要求原 owner 的 charge 在重新绑定前。全部内核、ABI、锁、工作流及七个生产负控输入逐字不变。

首个 f966 的 G0 [run 39239994115](https://github.com/TrillionniumFoundation/trillionnium-os-desktop/actions/runs/39239994115) 真实失败于旧 TSC 调用文本断言（spec 36 中 1 failure）。恢复环境首次本地复跑另有两项缺原 upstream Git lock 的准备错误；恢复固定 `96605cf:Cargo.lock` / 原 SHA `6b5de5d7…` 后，原 spec **36/36** 与 organ-backend **26/26** 成功。失败日志保留为各自实际记录，未改原 pin/lock 或放宽删除/计费判据。

新的远端 head 必须取得自己的正常检查和原 A06 完整产物；首个 head 的正在执行结果不自动转记给本候选。

---

## 问题与行为

原 CPU owner 的窗口仍使用原始 TSC，无法直接提供 BOOTTIME 纳秒累计和同一 revision 的可信内部用量；运行段、配置写入和观察点也必须共享原 owner 的同一次结算。本 PR 在已经正常合入 #203、#204 的主线 `00e2652c62ce6e34337d8f5bc3f3366b089c3d9c` 上实现这一 G1-b 切片。

唯一原 `CpuMax` 改用校准 BOOTTIME 纳秒窗口，增加累计用量、高水位与持久记账故障。CFS 保留独立的 cycles 游标。配置与私有 usage wrapper 先在原本地 runqueue 结算，再在原 owner 同一锁内观察身份、revision 和计数；继续保留旧控制器和祖先的运行段尾账。短/长周期回到 N0 时等待新的完整窗口起点，同值写入和降额不充值。时钟缺失、单核倒退、溢出与不一致历史拒绝 native 观察；有限 quota 拒绝，经过原 metadata gate 的 `max` 可解除限制但不清除故障。

新增 19 项真实 core 回归，覆盖 3 GHz 分数相位 oracle、cycles/ns 分离、跨窗口累计与欠额、周期重设、owner 关闭与替换、可靠/失效时钟倒退、溢出以及共享 owner 合法的迟到和重叠记账。测试夹具按原 zombie/process/task 寿命释放实际 lease，保留原严格删除检查。七个原生产缺陷反向控制继续运行完整 core；仅调整三份补丁的源码上下文和对应 hash，并给相位缺陷增加一个预期失败名称。

## 文档

新增技术与开发手册，给出唯一状态 owner、锁序、字段/错误语义、19 项回归、七个反向控制及普通产品复跑命令。INDEX/STATUS 补当前来源与历史范围；A04 三份详细手册已经随 #202 合入主线，旧 Debian 输入缺失与新 Ubuntu full32 资格分开记录。根 README 为 0 字节。

## 已取得的验证

- 本地固定工具链原入口 `wip-core-03`：完整 core **220/220，0 failed、0 filtered、0 soft skip；原始 QEMU 33，run.py 进程 0**。raw serial SHA-256：`ab7ae20b3dafef9250d74e829fed703698f673061d47950eaa8e96fb12ef705e`。
- 独立逐测试串口解析确认上述 220 个唯一名称/终态和全部 19 项新增回归。该运行属于本地 WIP，尚不是本 PR 远端 head 的资格。
- 七份生产补丁严格 apply/check/reverse、原反向入口的全部函数 AST 保持原版；固定 Rust 格式检查、diff check 和 301 个手册本地目标通过。
- 首次旧 217 项版本的真实 EBUSY 失败及单项过滤诊断记入开发手册，未放宽删除检查、断言或 gate。

本 PR 必须取得同一远端 head 的完整 A06：core/OSTD、七组精确反向失败集合、普通 QueryAbi14、SCM27、RLIMIT37、同一冻结 Ubuntu image 的 Linux32 差分、四个 CPU 配置门槛和有限 1/2 vCPU 配额/退出门禁，并独立核对原产物后再正常合入。

## 固定来源与未开放范围

远端 head：`f9669912e2886190429187e14753d62b2060bd5f`  
tree：`659736e494be76de1d29e2e80972b126071e5cfe`  
本地同树提交：`83e122d40e5427f84efebb4b7a224f7131580e63`。

HOS2 仍仅 QueryAbi；ReadUsage、InstallBudget、QueryDelivery、RetireThrough 四项用户态操作未开放，生产 bootstrap 未绑定 native owner。可信 Process/exec 授权、原 Hepta K↔D 持久交付、物理 context-switch 原子性、完整 SMP、原 Hepta W1 和手机/物理设备继续单独验收。内部 snapshot 不授予权限，也不宣称整个 G1-b 或 AI-native OS 已完成。

## 临时工作区维护后的证据范围

2026-10-19 10:46 UTC 恢复检查发现会话维护已移除本地工作树与尚未发布的 R11 原始日志/审计文件。已发布的本 PR head/tree 和旧 #203/#204 主线内容完整保留，并已重新从 GitHub 核验。上面的本地 220、EBUSY 与源码终审属于维护前已观察事实；原本地日志目前不可下载，不以记录中的哈希或摘要代替原始字节。正式合入仍需本 PR 精确 head 新产生的完整 A06 原始产物和独立复核。报告将逐项记录恢复与缺失范围。
