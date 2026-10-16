# 按实际依赖推进的开发路线

版本0.2。调查、上游复现、新增实现和真实验收分别记录；状态以STATUS为准。不以文档通过代替代码或设备结果。

## 1. 主路径

```text
M0a 固定完整上游/构建输入 ──> M1a 复现上游启动
M0b ABI/对象规格 ──────────> M1b 编解码库/普通客户端
M0c Hepta真实Linux依赖盘点 ─> M1c 必需兼容子集/存储资格
M1a + M1b ────────────────> M2a 新内核资源实现+非AI控制客户端
M2a + M1c ────────────────> M2b 真实Hepta宿主profile接合
M2b ─────────────────────> M2c cap/revoke/kill/reboot闭环
M2c ──> M3 扩展Linux工作负载 / M4 Android平台 / M5裸机本地AI
M3 + M4 + M5需要的子集 ────> M6 Rust桌面与指定应用产品化
```

M1a是上游复现，不是宣称新增内核代码。M1c只需Hepta实际用到的线程/IPC/锁/SQLite等，不等待全部Linux功能；这些必要子集不再排到Hepta闭环之后。各平台工作按真实接口依赖并行，不能将完整Android/GPU列成首个CPU接口的前提。

## 2. 本轮之后的具体开工任务

| 项目 | 下一条具体工作 | 完成标准 |
| --- | --- | --- |
| M0a | 使用support/upstream-lock.json锁定源码；验证完整上游tree、Cargo.lock及许可来源 | 源码checkout与依赖输入可重现，不只写版本号 |
| M1a | 固定构建容器digest、QEMU/firmware、rootfs manifest与内核配置，按上游入口构建启动 | 实际kernel产物hash、完整serial日志、退出结果 |
| M1b | 实现NATIVE_ABI三个操作的no_std编解码与客户端格式测试 | 固定头/请求/响应、截断/溢出/unknown/保留位/容量全部覆盖 |
| M1c | 原Linux构建真实Hepta profile与trace；建立W1必要接口清单 | 明确到ELF、依赖、实际owner装配，不把上游缺口误归OS |
| M2a | 在上游FileLike/ioctl/进程/调度对象接入CapSpace、单CPU预算与投递表 | 非AI客户端真实安装/观察；fd绑定、CAS、同值更新不充值、copyout重取 |
| M2b | 接现有Agentd invocation provider/主工具链，保持K/D身份与状态owner | 实际Hepta请求到新内核，非mock结果 |
| M2c | 受控revoke、停桥/模型、重启及未知操作核对 | 独立应用/I/O继续；不放大权限、不新ID重放 |

文档检查或旧规格模型成功不能推进M1b代码状态；具体执行失败记录在STATUS，不改变本节技术依赖。

## 3. 构建输入与自动化

研究source pin不等于build lock齐全。support/upstream-lock.json记录真实kernel/Hepta commit、上游nightly和已核查release asset digest；rootfs manifest、容器digest、firmware缺项用null和ready=false，不能臆造。ISO hash是发布元数据，不声称已下载验证本地字节。

导入时固定工具链target/Cargo.lock/依赖来源/内核配置/QEMU/固件/rootfs。host辅助codec的Rust可以独立于上游内核nightly，但都必须记录实际版本，不偷偷用host stable替代kernel nightly。

最小自动化：空README与本地链接、相关库单测、单一kernel build/QEMU smoke、变更涉及的兼容回归。源码尚未落地不添加假的绿灯workflow。GitHub原有权限与分支规则按实际状态使用，不为避测试修改仓库安全设置。

## 4. 与主线并行的风险消除

R-GPU：选定一台候选设备，列驱动/固件/队列/共享/复位所需机制，比较原生/服务域/VM并选择优先路线。

R-Android：固定可获取的AOSP manifest/product和VINTF/MAC/页大小需求，先做接口差异，完整实现后续。

R-VMM：按目标CPU分别核对VMX/SVM/EL2和VMM/设备模型，不以Intel上游例子保证AMD可用。

R-Hardware：实际只读枚举首台候选机/恢复介质，不刷BIOS、不覆盖系统盘；调查完成不算支持验收。

调查可先于M5，实际危险硬件写入是后续明确任务。所有实验保护现役服务与数据。

## 5. 判定与选择

ABI问题使用普通客户端缩小；兼容问题使用原ELF差分；Hepta装配问题在原Linux复现。AI策略未优于普通反馈时保留可靠对照，不能为了产品标签强制使用AI。发现核心上游冲突时提交具体复现与改动成本，才调整派生边界。

下一份提交应以真实M1b编解码或M1a构建结果为中心，不再次单纯扩张原则文件。
