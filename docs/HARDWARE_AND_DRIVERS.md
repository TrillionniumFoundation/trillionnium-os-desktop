# 硬件、DMA与关键风险

版本0.2。支持状态见STATUS；候选设备调查不等于设备已支持。

## 1. 平台顺序与早期风险调查

N0先x86_64/QEMU/virtio单CPU控制闭环，SMP后续；固定实机枚举再确认裸机资格。ARM64先QEMU virt，再独立设备。现有PC/AMD APU/手机/Apple Silicon名称不是支持清单。

GPU、Android构建产品、VMM和首台实机的可行性调查与M0并行：每条路径记录驱动/固件来源、所需协议、内存映射、队列、复位、许可、最小验证及阻塞。实施可后置，不能等CPU原型完成后才问“GPU有没有路”。只选一条有证据的优先路径，不同时做三套长期后端。

## 2. 设备owner和访问入口

同一物理设备只能有一个执行owner。native/Linux设备fd、VM与Android HAL不能各自绕过它写MMIO。设备直通需实际IOMMU组、复位及中断隔离条件；共享桥需显式buffer和queue协议。没有隔离的设备不向不可信多域共享。[VFIO参考](SOURCES.md#vfio)

驱动放内核态时属于TCB，Rust不使设备逻辑故障自动进程隔离。用户态服务域可研究但不伪称已实现。

## 3. DMA所有权状态

buffer状态：CPU-owned -> prepared/synced-for-device -> device-owned/in-flight -> completion/quiesced -> synced-for-CPU -> CPU-owned/released。禁止CPU或另一个设备在未授权方向写device-owned缓冲。每次提交绑定稳定对象、offset/len、direction和queue generation，不接受任意物理地址。

IOMMU负责可达范围，缓存一致性/顺序另处理。streaming DMA按设备/API做同步，coherent buffer仍需描述符内容与doorbell之间的适当内存屏障。共享ring producer发布用release、consumer消费用acquire；MMIO/DMA屏障与语言原子不是随意互换。[DMA](SOURCES.md#dma)

IRQ仅记录有界完成并唤醒worker；unregister/close等待引用与静止，不在spinlock里阻塞。热移除或reset先禁止新准入，等待/隔离in-flight；提升queue generation，旧completion不得完成新操作。复位确认静止只允许资源回收，不证明未产生部分磁盘写入。

## 4. CPU和内存机制

上游页表/异常/SMP/中断机制先保留。新资源域cap接在真实运行记账点，不能用用户态sleep模拟内核限额。多CPU启用前实现全路径额度预留、timer/调度延迟误差界和runqueue同步；迁移未实现则明确不支持。TLB shootdown完成且CPU引用消失后才复用物理页。

## 5. GPU/NPU路径决策

图形显示、硬件渲染、计算API、本地推理、数值一致、长期恢复分别验收。选定设备要说明内核内存管理、命令提交、同步fence、用户态运行时/编译器、固件与reset。能打开桌面或Mesa软件OpenGL不证明GPU计算。

三种候选：原生Rust驱动；受限协议服务域；Linux驱动VM。后两种须记录数据复制/共享内存开销、真实计算所在内核、设备owner和失效隔离，不能改个名称算原生支持。首个本地推理可CPU完成，不因此取消GPU后续目标。

## 6. VMM不是免费备选

OSTD虚拟化基础与完整VMM/虚拟中断/设备模型/KVM兼容接口分开；Intel VMX、AMD SVM、ARM EL2分别核对源码和硬件前提。当前固定上游不等于本项目已支持任意后端。[OSTD RFC](SOURCES.md#ostd-vmm)

只把VM列为允许路径，未完成具体后端/设备验证前不承诺“全Linux/Android可用”。调试用Linux/KVM宿主与最终由新内核托管VM是不同实验。

## 7. 首台实机和电源

实测记录CPU/主板/固件/启动模式、PCI/USB IDs、IOMMU组、磁盘布局、恢复介质、网络/显示/输入。首次用隔离测试盘，不覆盖工作盘。热保护保留，传感器不可用采用保守限额。休眠恢复后核对lease时间、DMA、queue generation、未完成I/O与电源状态，不把用户态awake当全部设备恢复。
