# Android平台接合与APK兼容

版本0.3。保留完整AOSP用户态，适配内核/Binder/HAL；设备合规、应用行为、外部服务认可分开验证。实际状态见STATUS。

## 1. 必须锁定的产品输入

初期研究profile为x86_64/4KiB/software graphics，Android 17 CDD是需求参照而非已锁定源码。实际构建前固定AOSP tag、repo manifest SHA、lunch product、system/vendor分区、system_server/ART/Bionic版本、VINTF device manifest/framework compatibility matrix、AIDL HAL版本及实例、SELinux策略/等效MAC映射、声明feature列表。任何必需输入未定都不能称可复现AOSP构建。

VINTF描述设备/框架互相要求；稳定AIDL HAL需版本和实例一致，不是写一个HAL名称就完成。[VINTF](SOURCES.md#vintf) [AIDL](SOURCES.md#aidl)

## 2. 内核与安全接合

Binder对象/引用、线程池、同步/oneway、嵌套、死亡通知、fd转交、身份/MAC和退出资源清理逐项对照。UID/security context来自可信内核，不能信任payload自报调用者。property service/init/共享内存、futex、mmap、信号、进程组、seccomp/线程同步和procfs按所选AOSP实际依赖实现。

Android17 CDD 9.7/C-2-1要求相应非Linux或无SELinux实现提供等效强制访问控制；9.7/C-0-6要求多线程可配置系统调用过滤。把策略编成真实对象权限/系统调用检查并执行负向测试，打印SELinux标签不证明MAC。相关要求是实现工作，不是要求原型开发先获得商业认证。[CDD](SOURCES.md#android-cdd)

## 3. 内存压力与页大小

盘点lmkd使用的PSI/cgroup/内存统计、oom_score_adj与杀进程行为，适配真实资源域；不能虚报压力或禁用回收掩盖启动失败。app freezer、前后台切换及解除冻结后Binder/时钟/权限需回归。密钥和/data持久状态只在存储资格通过后接入真实数据。[lmkd](SOURCES.md#lmkd)

page_size通过系统接口获得。A0限定4KiB不等于永远4096；ARM64/16KiB独立验证ELF段对齐、mmap/保护粒度、NDK/native库与翻译器行为。wire只用字节长度且受检，不嵌入页数量的隐式4096倍数。[页大小](SOURCES.md#pages)

## 4. 图形与桌面

先验证软件渲染和完整Android显示面接入Rust桌面，后续逐应用窗口。SurfaceFlinger/HWC/gralloc的数据格式、stride/offset/长度、共享buffer所有权及fence生命周期明确匹配；reset后旧fence/queue失效。软件图形不算GPU、视频硬解或相机支持。

按Android窗口焦点处理触控、IME、返回/主页、通知；跨域剪贴板、摄像头/麦克风/屏幕共享走受限服务与权限，不自动向Hepta暴露全部环境数据。

## 5. 指令与第三方服务

DEX-only、x86_64 native、ARM64 native、旧32位native分别测。Native Bridge只是接入机制，翻译器实现、来源、许可、动态装载/JIT/信号/线程需单独确定。即使ARM64内核，也不能默认全部32位可用。[Native Bridge](SOURCES.md#android-native-bridge)

Play Integrity、DRM、厂商API、推送和服务端设备判断单独列前提，不以伪造证明/绕过完整性取得兼容成绩。关闭安全测试不是等效实现。

## 6. AI代理专属边界

Android17 CDD 9.8.18对AppFunctions执行者权限/预装身份以及明确用户触发和展示有额外要求。Hepta长期资源管理授权不能自动代替Android AppFunction的这类触发条件；核实调用类别，OS CPU预算接口不是AppFunction。系统环境敏感数据及其衍生信息也不可任意用于主动提示。仅在实际实现相应能力时按适用CDD条款接合，不宣告全系统认证。[CDD agentic functions](SOURCES.md#android-cdd)

## 7. 实施与判定

固定AOSP输入/原Android对照 -> Bionic/native测试 -> init/Binder -> Zygote/system_server -> graphics/输入/PackageManager -> 原APK完整场景 -> native库/后台/重启/权限 -> 适用CTS/VTS/设备功能。VM对照独立标记客体kernel/镜像，不计原生android_runtime通过。

每个APK记录package/version/split哈希、来源/ISA、权限/服务依赖、AOSP manifest、运行模式、硬件和分场景结果。安装、首页、登录、消息、媒体、文件、通知和恢复分别验收；未测不通过。

## 8. 用户解锁与存储边界

固定product后独立设计Direct Boot、DE/CE数据、用户解锁、Keystore及密钥备份恢复路径。S1基础文件系统耐久测试不提供Android加密存储或硬件密钥证明；原型仍可用可丢弃合成数据启动，不把完整设备合规当首次APK验证的共同前提。AppFunctions要求仅用于实际对应调用，不扩大为所有OS预算动作必须手动确认。
