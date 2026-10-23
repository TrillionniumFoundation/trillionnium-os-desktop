# RamFs / Ext2 setgid 创建合同

原生 Hepta Root 服务要求控制套接字实际属于 `root:60001`。父目录已经是
`root:60001/02710`，但原 RamFs 与 Ext2 创建子 inode 时始终使用调用者组，
导致 socket 实际 GID0，原服务正确拒绝启动。修复属于文件系统创建语义；
服务的 ownership 检查保持不变。

## 接口、所有者与锁

[共同 child_creation_attrs](../../kernel/asterinas/kernel/core/src/fs/utils/mod.rs)
从原线程凭据读取 fsuid/fsgid；内核线程保留原 root fallback。setgid 父目录
使所有子 inode 继承父 GID，子目录同时继承 setgid 位。非目录同时请求
setgid 和组执行位时，调用者必须具有该文件组或原 `CAP_FSETID`，否则清除
setgid。非可执行文件的 setgid 位保留。它不创建新的凭据或 capability 所有者。

[RamFs](../../kernel/asterinas/kernel/core/src/fs/fs_impls/ramfs/fs.rs) 在同一原
metadata 锁中取得父 mode/GID，释放 IRQ 锁后执行凭据与 LSM 检查，再创建
原 inode。create、mknod 与 tmpfile 共用该规则；权限设置不发生在发布之后。
[Ext2](../../kernel/asterinas/kernel/core/src/fs/fs_impls/ext2/inode/dir/mod.rs)
在原父 inode 写锁范围取属性，将完整 uid/gid/mode 传入原唯一分配路径，
再发布目录项。原磁盘 owner 字段和写回路径保留。

## 开发与实际回归

新增两个真实 ktest 保留在原 RamFs 和 Ext2 测试中，覆盖 socket、普通文件、
目录/嵌套目录、FIFO、符号链接、零链接 tmpfile，以及非 setgid 父目录对照。
Ext2 还实际 sync 并 reopen 检查持久属性。严格检查器要求完整名称存在。

固定源 `15ec98c23edb6ebb1682c959324efb05a201cb9f` /
tree `3d241d864465b46cb94138d5c2f8b8978dfe2a92` 的
[原完整四套与 ordinary](../../results/integration/2026-10-23-audit-closure/sgid-kernel-15ec/publication.json)
已通过：core318/required79、allocator20、ML15；OSTD229 保留三个原 TCG
软跳过，四个 raw33。新 ordinary18 标记通过，全部9198个 tracked 输入不变。
它不代表后续 IPC 图组合源码已通过。

[同一 C 探针及实际运行器](../../results/integration/2026-10-23-audit-closure/sgid-authority-qualification-inputs/inputs.json)
通过了 [Linux15项](../../results/integration/2026-10-23-audit-closure/sgid-linux-reference-02/publication.json)，
再在同一普通产品 ELF `a531d96063b2a0be853e5265e43212b5f70843a0a35f2b4fba01ea063ed05ac8`
上通过 [RamFs15 / Ext2 15](../../results/integration/2026-10-23-audit-closure/sgid-native-15ec/publication.json)。
用例实际 fork、切换 UID/GID、清空能力、设置真实附加组和 NNP，并验证
专用组 stream/datagram 连接与数据收取。旧293b同探针30项失败28项；
首次新 Linux 非可执行 setgid 预期错误和首次内核编译缺 import 均单独保留。

## Hepta 启动边界

[原 df901 静态服务的原生记录](../../results/integration/2026-10-23-audit-closure/native-authority-df901-15ec-kvm-prefetch/publication.json)
使用实际 Root CLI、独立 UID60001、固定公钥、空附加组、零能力与 NNP。
在 KVM/warn 日志、授权初始化前读完两份真实 ELF 的启动配置中通过，
feed52ms、Objective1→FinalUse2、整次2.343秒。原1秒时钟窗口、500ms feed
和所有请求期限未改变。此前04/05/06的 Unavailable 失败全部保留；
独立32次时钟与 fsync 诊断不能代替服务验收，也不能证明唯一延迟根因。

客户端 checkpoint 没有收到 ACK；服务退出1的原始错误为 PeerDenied，
因此不推断 checkpoint handler 已执行。旧 launcher 的历史输出标签
`expected_unavailable_checkpoint` 仅对应其非零退出要求，不是该错误的证据。
本次只资格化原 V1 无效果基础授权路径；后续 V2、认证 current cut、生产
writer、CPU 效果、故障恢复、冷启动 SLA 和物理掉电仍需各自实际验收。
