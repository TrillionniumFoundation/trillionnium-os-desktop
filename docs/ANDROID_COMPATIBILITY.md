# Android 应用兼容设计

版本：0.1。状态：计划；尚未启动本项目 Android 环境。

## 1. 路线

优先保留完整 AOSP 用户态，在新内核上实现必要 Linux/Binder 行为与 HAL 接合。不要在实现新内核的同时重新制造 Android Framework、ART 和应用商店生态。

AOSP 包含 Framework、ART、系统服务、native library 与 HAL 等不同层次；完整 AOSP 也不等于具备全部外部后端服务。[来源](SOURCES.md#aosp)

Android 17 CDD 是本轮兼容需求研究参照，实际构建需在 M0/M4 锁定具体 AOSP tag、manifest、设备类型及适用测试，不把“Android 17”标签当作可复现构建输入。[来源](SOURCES.md#android-cdd)

## 2. 必须分开的兼容层次

| 层次 | 核心问题 | 完成证据 |
| --- | --- | --- |
| 内核接合 | 进程、内存、Binder、文件、权限、设备 | 对照测试和系统启动日志 |
| Framework/ART | Zygote、system_server、JNI、包管理 | 原 APK 安装与功能场景 |
| 图形/媒体 | SurfaceFlinger、buffer、fence、音视频 | 实际画面、输入、播放和同步 |
| 指令集 | APK 中 native library 的 ISA | 每类 ABI 的真实 native 路径 |
| 设备 | 摄像头、定位、传感器、通信、功耗 | HAL 测试与实机功能 |
| 服务/认证 | 推送、服务端策略、完整性、DRM | 合法接入与独立结果，不伪造认证 |

上层功能成功不证明所有底层安全、时序或耐久语义正确。Android 能启动不能作为全部 APK 可用的证明。

## 3. Binder 与进程语义

Binder 工作包括对象引用与生命周期、同步/异步 transaction、线程池、嵌套调用、死亡通知、fd 转交、调用身份与安全上下文、取消、进程退出和资源配额。必须对已选 AOSP 版本的真实接口建立测试，不用普通消息队列替代全部语义。

进程身份、UID、权限和安全上下文由可信 OS 状态确定，不接受来自普通请求体的自报身份。跨 Android 用户或工作区的对象与文件访问必须保留隔离。

同时盘点 Bionic/ART 对 futex、mmap、信号、共享内存、属性系统、procfs、内存回收和调试机制的依赖。不要假设所有 Android 版本仍使用相同 ashmem/ION 等旧接口；依据锁定版本和真实 trace 实现。

## 4. 图形、媒体与桌面融合

先用明确标记的软件渲染验证上层窗口和输入；单独推进 GPU 支持。buffer 共享需要格式、stride、长度、生命周期、方向和 fence 语义一致。同步对象丢失或设备复位后不能继续使用失效缓冲区。

Android 窗口通过受限显示桥接入 Rust 桌面，处理键盘、触控、IME、焦点、返回/主页、通知和剪贴板。跨工作区传输需要显式权限，不全局暴露输入事件或内容。

音频需要确定采样格式、延迟与时钟；摄像头需要实际 HAL 与数据权限。软渲染跑通或存在虚拟摄像头不能算硬件解码、相机和实时媒体已支持。

## 5. 指令集与 native library

x86_64 与 ARM64 为不同 profile。纯字节码应用、带 x86_64 native 库、带 ARM64 native 库，以及旧 32 位 native 库分组测试。

Native Bridge 提供接入机制，但 AOSP 本身不附带完整二进制翻译器；x86 上 ARM native 代码需要单独的合法翻译实现与验证。[来源](SOURCES.md#android-native-bridge)

翻译器必须记录来源、版本、许可、指令覆盖、动态装载、信号/异常、线程、JIT/W^X 与性能。不能靠替换不同 APK 版本掩盖某类指令执行不正确。ARM64 目标也不自动证明旧 32 位代码可用。

## 6. 安全和外部服务

适用的 CDD/CTS/VTS 等要求与实际设备类型相匹配，不能通过删除测试、关闭隔离或伪造功能位取得通过。非 Linux 内核需要独立证明相应安全机制，而不是把 SELinux 字符串输出作为等效安全证明。

Play Integrity 的设备结果可以涉及认证设备、受信任启动和硬件证明；第三方应用可依赖这些结果。此类接入与内核 ABI 兼容分开处理，不保证单靠新内核即可通过外部服务判定，不伪造完整性、DRM 或硬件证明。[来源](SOURCES.md#play-integrity)

## 7. 实施顺序

A0：锁定 AOSP/ISA、建立原 Android 对照与合法 APK 样本。

A1：Bionic 测试与基础 native 程序，然后 init、Binder、Zygote、system_server；保留首个实际失败点。

A2：图形、输入、包安装和一个不依赖额外服务的 APK 完整场景；软渲染结果单列。

A3：并发进程、权限、持久化、原生库、后台与重启回归，运行适用测试集。

A4：GPU/媒体、实际设备、目标应用库与外部服务接入，建立版本化覆盖矩阵。

存在 VM 对照或 VM 补缺时，必须在结果中注明其客体内核、镜像和设备路径，不能计入 android_runtime 原生模式。

## 8. 每个 APK 的记录

记录 package/version、APK 与 split 哈希、来源、CPU ABI、权限配置、AOSP 构建、运行模式、硬件、外部服务依赖、完整场景、冷/热启动、后台/恢复、日志和结果。安装成功、打开首页、登录、消息、音视频、文件与通知分开评估；未测试不能写通过。
