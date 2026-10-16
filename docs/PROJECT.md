# 产品范围、工作负载与原生能力

版本0.2。目标是独立Rust内核+Hepta原生控制+现有Linux/Android应用兼容，不是旧Linux桌面包装。状态只由 [STATUS](STATUS.md) 记录。

## 1. 保留的硬目标

核心内核以Rust实现并可在明确支持的实机独立启动；Hepta沿现有单一模型/工具主链调用真实OS资源与设备能力；现有ELF/APK尽量不改源码不重编译；应用同时标注native-control、linux_abi、android_runtime、VM等实际执行路径。Hepta失效不能阻断独立应用、基本I/O、撤销和本地恢复。

长期覆盖目标不缩成“只支持自行重编译程序”。阶段验收固定软件版本/哈希、CPU ISA、用户态镜像、功能场景、硬件及外部服务，不能对未定义应用集合报全兼容。内核模块、设备ABI、指令翻译与外部服务认可分别验收。

## 2. 首期profile

N0：完整Asterinas派生，x86_64/QEMU，单CPU资源控制实验，现有Linux ELF与宿主工具链；仅QueryAbi/ReadUsage/InstallBudget控制。物理硬件、SMP、迁移、GPU、Android均有后续工作但不伪装为N0实现。

A0：Android平台研究/后续原型，初期x86_64、4KiB页、保留AOSP用户态；精确product和manifest尚需实际源码构建锁定。ARM64与16KiB为独立profile，禁止将4096固化成永久wire常量。

D0：Rust原生桌面、Wayland与分信任域Xwayland、先完整Android显示面后逐应用窗口。UI原生Rust不要求所有旧应用兼容组件同时改写Rust。

## 3. 工作负载优先级与交付边界

| 优先级 | 工作负载 | 必需结果 |
| --- | --- | --- |
| W0 | 普通HOS控制客户端+两个CPU竞争任务 | 可观察budget生效、越权拒绝、原投递重取 |
| W1 | 真实Hepta/Agentd/App Server的选定profile | 对应ELF依赖与owner装配、现有工具主链到W0接口 |
| W2 | SQLite、Rust/Tokio、编译/脚本工具 | 线程/IPC/锁/持久化/子进程完整场景 |
| W3 | Linux图形/浏览器 | 显示、输入法、D-Bus/portal、音频、字体和文件选择 |
| W4 | AOSP及实际目标APK | 安装、前后台、native库、权限、媒体与服务依赖 |
| W5 | 本地CPU/GPU推理及特殊内核依赖 | 本机真实计算、数值正确、恢复；特殊模块另列VM或替代 |

W0客户端改写为使用新接口不影响W1/W2对未修改Linux ELF兼容的判定。模型和应用许可按各自来源处理，不擅自改变上游许可。应用安装路径先用固定只读rootfs和清单，不立即重写一个包管理器。

## 4. “原生”的两个含义

首期原生系统集成指内核特有能力+用户态Hepta服务；即使Hepta仍使用Linux ELF也成立。独立原生应用ABI另需装载/TLS/异常/运行时/工具链设计，未列为首期交付。不以控制ioctl成功冒充完整独立用户态生态。

## 5. 首个真实闭环

固定新内核+ELF+依赖 -> 普通客户端验证 -> 真实Hepta现有主链安装cap -> 独立工作量和内核计数交叉核验 -> revoke/kill -> 独立应用恢复 -> reboot后原逻辑操作核对。先CPU，不等待GPU；远程provider只标记远程，不代替本地模型证明。

评估成功率、延迟、吞吐、资源成本、恢复，而非代码量。固定策略、普通反馈与Hepta比较，不让AI只战胜刻意弱的静态基线。Linux等价控制对照帮助分开策略收益与新内核收益。
