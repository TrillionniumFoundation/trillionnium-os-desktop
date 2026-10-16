# Linux兼容与应用交付

版本0.2。Linux ABI是用户态行为承诺，不是兼容任意内核模块。目标与状态见PROJECT/STATUS。

## 1. 一个实际运行profile

每个应用记录：ELF/hash、ISA、动态loader、libc与共享库、rootfs清单、locale/时区、证书/NSS/DNS、UID/namespace/MAC、挂载/设备、服务依赖、完整场景与期望结果。仅源码能编译、--help或进程启动不算该应用工作负载通过。

先从W1真实Hepta生成trace和依赖闭包；固定manifest里每个包的版本/来源。初期通过只读镜像提供依赖、分离可写工作区；部署新应用先构建新清单和可回滚镜像，而非在用户机器任意安装。后续包更新/卸载不得删除仍被运行任务或持久状态引用的内容。

## 2. 必要接口子集先于完整Hepta

L0装载/auxv/TLS/内存保护 -> L1文件/管道/时间 -> L2线程/clone/futex/信号 -> L3socket/epoll/AF_UNIX/fd传递 -> L4锁/SQLite/文件映射与持久化。L2–L4中真实Hepta所需子集必须在其端到端验收前具备，不再把它们全部放到后续M3。

procfs/sysfs、namespace/cgroup、io_uring、ptrace、seccomp和特定ioctl按真实需求扩展。内核权限隔离不能作为可选兼容功能关闭。ENOSYS、ENOTTY、EOPNOTSUPP和EPERM分别代表不同层面的不存在/不支持/拒绝，影响应用回退；每个接口按其契约选择，不能统一成功空响应或EIO。

## 3. 同对象权限执行

原生CapSpace不绕过Linux权限，Linux root/fd不绕过宿主资源域。文件、设备、调试、映射和cgroup入口最终检查同一个对象owner与授权范围。普通fd保持Linux dup/fork/exec语义；control fd有设备专属打开身份绑定。跨进程传递原始fd不复制发送者管理能力。细节以NATIVE_ABI为单一来源。

## 4. 真实桌面依赖

W3除syscall外还需D-Bus/session、portal、PipeWire或选定音频路径、字体/渲染、Wayland/Xwayland、IME、文件选择、证书和浏览器sandbox接合。不能因为窗口显示就宣称屏幕分享、后台通知或相机正常。保留合适上游用户态组件，不强制全系统C/C++兼容组件重写Rust。

## 5. 持久化与安装恢复

开发host-backed文件共享只用于输送与调试；独立S1=virtio-blk+上游Ext2候选路径验证锁、fsync/fdatasync、rename/unlink/目录、mmap写回、short I/O、flush和原SQLite/WAL。测试数据合成，S1未过前不迁移真实Hepta业务状态。文件系统恢复、数据库事务恢复和原操作效果核对是三项独立结果。

## 6. 差分判定器

固定Linux参照与相同输入。确定性返回/errno/文件内容可精确比较；并发测试比较允许的偏序和结果集合，如每条已提交记录恰好可见、锁互斥、不越权、线程退出最终被等待。PID、随机值、地址与合法调度顺序按规则规范化，不能统统忽略差异或要求不可能的全序一致。

新增修复附最小复现与期望；ABI兼容不要求复制已知安全漏洞。应用probe遇到unsupported与denied需要分别测其回退路径。适用LTP、libc/应用测试的执行、失败、超时、跳过及未支持数分别给出分母；上游通过率不自动归入本项目。

## 7. 首批场景

W0 cap变更/丢响应；W1 authenticated ObjectiveStart与实际工具调用；W2并发SQLite写入、WAL重启、fd耗尽、AF_UNIX半关闭、futex退出竞态；W3输入法/焦点/媒体/文件；特殊.ko依赖软件独立记为VM或尚未支持。版本和ELF hash从真实构建获得，尚缺输入在upstream-lock或运行清单标空，不能用“最新版”代替。
