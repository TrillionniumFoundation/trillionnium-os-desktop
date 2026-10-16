# 架构决策 0.3

本页只记录选择和改变选择的条件；真实进展见STATUS，共同原则见INDEX。

## D01：完整Asterinas派生为首条主线

固定v0.19.0提交与nightly，复用任务/VFS/网络/ABI与OSTD，新增资源与能力接口附着已有对象。仅复用OSTD并重建上层不再与主线混用。重新选择必须提供不可解决的接口冲突、最小复现及修改成本；没有这些不分裂第二主线。

## D02：原生Hepta仍是用户态、原有执行主链

第一阶段保持Linux ELF，通过窄的内核控制接口提供真正原生系统能力。真实宿主profile必须包含现有runner/provider/owners，普通daemon启动不替代。独立应用ABI不属于初期交付。

## D03：有限协议优先于大量空操作

HOS2首期包含QueryAbi、ReadUsage、InstallBudget、QueryDelivery和RetireThrough，完整定义输入/输出/错误/身份/结果重取。资源域由可信init配置；动态迁移/Transfer/SubmitIo暂不提供wire，不分配未实现能力的编号。后续按真实需求增加并独立验收。

## D04：CPU上限而非保底

首期单CPU、固定100ms周期、不支持period变化和迁移；更新保留已使用量，父域限制聚合。需要SMP/预留/deadline时单独给并发算法和实际界限，不把cap当保底。

## D05：统一对象权限与两层身份

原生/Linux/Android入口共同受对象owner限制。control会话绑定打开进程，不以fd传递授管理权。K跨boot由原Hepta owner保存，D在本boot去重；digest存在记录中而不在查找键里。关闭新准入、停止硬件、零效果是不同事实。

## D06：保留AOSP与兼容用户态

Android平台构建、VINTF/MAC/内存压力/页大小作为明确任务。Rust原生UI不迫使ART/Xwayland等兼容组件也重写。外部完整性/服务认可分开记录，不伪造资格。

## D07：存储路线分层

开发输送S0不提供原生耐久承诺；S1选virtio-blk+上游Ext2作为待测候选，未通过前只用合成数据。发现不满足所需崩溃语义后，用最小复现决定修复或单次选型调整，不平行开多个永久存储栈。

## D08：调查前置、完整实现按依赖

GPU/VMM/Android product/首台实机可行性与M0并行；完整设备实现不阻断CPU接口。普通客户端先于Hepta，分离ABI和宿主装配失败。

## D09：AI必须可比较、可退出

保留固定与非AI反馈对照、Linux等价接口对照；观测过期不加大cap，推理成本纳入。没有可测净收益就保留可靠默认，不强制全部系统动作经过模型。

## 尚未完成的选择/输入

容器digest、rootfs构建清单、固件、实际AOSP tag/product、首台裸机和GPU后端尚需验证。记录缺项而非发明值；源commit固定只是可复现构建的一部分。运行状态不得因为选型写入而提升。

## D10：显式HOS2恢复协议

新有序写ID和恢复操作不重新解释HOS1。结果窗口以连续退役前沿防重放，DeliveryView独立于管理句柄；只有已持久确认的终局可退役。启动授权在最终exec后可信激活；旧效果不明与新授权目标收敛分别记录。
