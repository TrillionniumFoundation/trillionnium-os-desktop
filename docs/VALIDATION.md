# 验证层次、判定器与审计跟踪

版本0.2。模型、codec、内核、设备、Hepta端到端结果严格分层，实际执行状态见STATUS。

## 1. 结果和分母

每项记录not_tested/pass/fail/timeout/skipped/unsupported及执行环境。运行模式native-control/linux_abi/android_runtime/VM与结果分开。报告执行总数、失败、跳过、未支持及原因；不删除失败用例制造全绿。

## 2. 三类接口测试

格式测试（计划）：HOS1/HOSR的64字节header、32字节transport与预算、Query48/Usage64/Install24响应；截断每一长度、尾随字节、flags/reserved/enum、id全零、generation/target、major/minor、过大payload、输出容量、revision溢出、错误响应无敏感payload。

规格模型：K查找后比较digest；D/CapSpace跨boot；revoke/admit两种线性顺序；停止后partial效果；相同预算反复更新保留用量；parent cap共同执行。模型证明选定解释的逻辑，不证明内核采用了该解释。

实际内核测试（待接合）：fork/exec/dup/SCM_RIGHTS/control fd打开身份、Linux/Android设备别名、并发CAS/撤销、copyout EFAULT后的原D重取、容量耗尽、真实CPU计费、硬件reset/DMA引用。模型和codec均不提供这些证据。

## 3. 第一个端到端闭环

固定kernel/rootfs/ELF/Hepta和设备身份；先普通客户端，后真实Hepta主工具链。启动两个CPU竞争任务与不随Hepta退出的观察器，取固定策略基线；安装cap并记录K/D、对象generation、revision、时间和内容；核对真实任务完成量与内核用量，而非只读模型文本。

测试同D变内容冲突、相同D丢响应重取、并发旧revision、cap同值刷新、fd跨域及撤销交错。然后停模型/桥/Hepta，核对独立应用、I/O、恢复资源。重启后旧会话无效、原K未决不重放。

独立进程读相同内核计数不是独立证明计数实现正确；用CPU工作量进度、文件实际内容或设备完成交叉校验。不宣称这些能证明已被攻陷内核的全部行为。

## 4. 差分允许集合

确定性字节/errno精确比较；并发用偏序、不丢结果、互斥和最终回收等不变量，而非强制相同调度总序。PID/地址/随机值按明确规范化规则处理。不同安全边界造成的permission_denied单独记录，不能把它当unsupported，也不以兼容名义复制已知漏洞。

## 5. 故障注入分层

应用kill验证进程丢失；客体reset验证内核丢失；VMM退出验证虚拟机进程消失；丢弃指定易失缓存/短写/乱序验证存储假设；实际设备断电另列。尤其kill QEMU不保证host cache被丢弃。

每层记录注入切点、失效范围、重启路径、预期原数据/事务/操作状态。S1原生块存储与host-backed路径分开验收。部分物理效果保留，不能靠取消ACK回写none。

## 6. 性能与AI价值

A：同新内核固定策略/非AI反馈/Hepta策略；B：同硬件Linux等价控制与新内核；C：原生/ABI/VM设备路径差异。固定负载、数据与资源上限，冷/热状态分别测，随机化次序并记录温度及后台负载。

报告成功率、吞吐、p50/p95/p99、样本量与区间；低样本尾分位不作强结论。计入模型推理、观测、策略安装和错误恢复成本。第一cap演示只证明接口有效，不证明AI或新内核更快。实验参数在看结果前固定；无可靠改进则保留基线。

## 7. F01–F22 文档落点与剩余验证

| 审计项 | 0.2规格落点 | 尚需真实验证 |
| --- | --- | --- |
| F01 | ARCHITECTURE/DECISIONS/upstream-lock：完整内核派生 | 构建导入/启动 |
| F02 | NATIVE_ABI §2：同对象策略、会话绑定、root边界 | 内核别名/fd/credential |
| F03 | NATIVE_ABI §7：admit/revoke同锁及桥TCB | 并发/硬件切点 |
| F04 | NATIVE_ABI §8：K与D、摘要不入查找键 | 持久owner/重启/copyout |
| F05 | NATIVE_ABI §10：执行、取消、效果、观测分离 | partial/reset/DMA |
| F06 | NATIVE_ABI §3–6：有限三操作完整wire | codec与驱动接入 |
| F07 | NATIVE_ABI §9：固定周期不充值、祖先与内存 | 真实调度/SMP/计费 |
| F08 | HEPTA_INTEGRATION：源码符号/profile | 实际owner装配/主链 |
| F09 | PROJECT/LINUX_COMPATIBILITY：W0–W5/rootfs | ELF和应用分场景 |
| F10 | ANDROID_COMPATIBILITY：product/VINTF/MAC/页/代理 | manifest锁定/AOSP/CTS |
| F11 | ARCHITECTURE/HARDWARE：锁/IRQ/DMA所有权 | 源码锁分析/设备测试 |
| F12 | ROADMAP/HARDWARE：并行风险调查 | 选定GPU/VMM路径 |
| F13 | SECURITY：S0输送/S1原生Ext2候选 | 存储与SQLite故障 |
| F14 | SECURITY：熵/时钟/boot/更新 | entropy/clone/休眠/回滚 |
| F15 | HEPTA/VALIDATION：有界控制器/三基线 | 净收益与稳定性 |
| F16 | HEPTA/VALIDATION：K/D/对象/完成关联 | 权限观测/计数交叉 |
| F17 | DESKTOP_UX：Wayland/分域Xwayland/Android面 | 实际UI/IME/共享 |
| F18 | PROJECT：原生控制≠独立用户态ABI | 当前定义无独立ABI承诺 |
| F19 | ROADMAP/upstream-lock：输入和缺项 | 容器/rootfs/firmware锁定 |
| F20 | VALIDATION：允许集合/故障层/独立性 | 实际差分与掉电 |
| F21 | ROADMAP：M1a/b/c -> M2a/b/c | 按依赖逐项交付 |
| F22 | INDEX/STATUS：共同原则与单一状态页 | 链接/状态一致维护 |

“规格已修订”不等于“问题在运行实现中已关闭”。本表是审计追踪，不是新的审批或授权数据库。

## 8. 最小证据

一次运行保留run_id、source/build/hash、host/guest、配置/镜像/设备、命令/退出码、日志hash、预期和实际。凭据/用户内容不进入公开日志。大镜像不入Git，仓库放复现入口与准确摘要。文档验证只检查文件/链接/字段算术，不冒充CI、kernel boot或兼容通过。
