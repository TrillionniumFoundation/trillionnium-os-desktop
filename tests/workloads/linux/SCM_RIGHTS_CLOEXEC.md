# SCM_RIGHTS / MSG_CMSG_CLOEXEC 开发和验证

Owner：A04 实现 Linux FD/ancillary 语义，A00 接合现有 A06 内核 CI。
这是独立的 27 项兼容回归 profile；完整 A04 固定 Debian 13 四 ELF、rootfs 和 28 个 C 案例仍由原规格验收。

## 行为和实现边界

`recvmsg(..., MSG_CMSG_CLOEXEC)` 必须在收到 `SCM_RIGHTS` 描述符时，直接在原进程文件表发布带 `FD_CLOEXEC` 的条目。普通接收不继承发送 FD 的 CLOEXEC 标志。接收调用返回的 `msg_flags` 回显 `MSG_CMSG_CLOEXEC`，包括本次没有 ancillary 的情况。

flags 沿原调用链传入：`sys_recvmsg` → `CUserMsgHdr::write_control_messages_to_user` → `ControlMessage::write_all_to` → `UnixControlMessage::write_to` → `FileMessage::write_to`。最终复用原 `FileTable::insert`，在插入时设置 `FdFlags::CLOEXEC`，不在发布后调用 `fcntl`。凭据消息编码保持原路径。

该改动不开放 HOS2 效果操作、不修改授权发行者或 Hepta pin。`RLIMIT_NOFILE`、FD 分配上限及其回滚是另一个兼容任务，不由这里的 CLOEXEC 通过结果代替。

## 固定分母和错误含义

`scm_rights_cloexec_probe.c` 对 stream、datagram、seqpacket 各运行以下九项，共 27 项：普通接收、三个 FD、多次 PEEK 的两种标志顺序、截断控制缓冲、丢弃 ancillary、无 ancillary、凭据和 FD 同时接收、fork/exec 后的 FD 继承和子进程回收。

探针必须以绝对路径运行，fork/exec 案例调用它自身。每项输出一行 `SCM_CLOEXEC_CASE`；任一失败返回进程 exit 1，全部通过才输出 `SCM_CLOEXEC_COMPLETE total=27 passed=27 failed=0` 并返回 0。探针含 30 秒 alarm，guest runner 另有最多 120 秒的外层 QEMU 期限。

runner 严格校验 27 个不同的固定 case、顺序、每项 PASS、精确完成标记、真实 probe exit 0、普通启动标记、无 kernel panic 和 raw QEMU exit 33。缺项、重复、假成功摘要、超时或被杀都不能通过。诊断性失败会记录真实 probe exit，并允许 init 正常关机，以保留完整失败分母；这不改变失败 verdict。

## 从相同 ELF 建立 Linux / guest 对照

在已配置的 Linux 构建宿主，创建新的外部输出目录并只编译一次：

```sh
scm_work=$(mktemp -d /tmp/a04-scm.XXXXXX)
cc -O2 -std=c11 -Wall -Wextra -Werror -static \
  tests/workloads/linux/scm_rights_cloexec_probe.c -o "$scm_work/probe.elf"
"$scm_work/probe.elf" > "$scm_work/linux.stdout" 2> "$scm_work/linux.stderr"
sha256sum "$scm_work/probe.elf"
```

记录真实命令、编译器/宿主版本、退出码和完整 stdout/stderr。验证 Linux 为 27/27 且 stderr 为空。若宿主策略拒绝 `SO_PASSCRED`，保留该次错误并修复测试环境；不删除凭据案例。

候选内核先通过原 `tests/kernel/control/run_queryabi_candidate_guest.py` 的普通 build/boot gate。它要求干净的确切 Git head/tree、所有受控文件的前后字节与 mode 一致、固定 Asterinas/toolchain/lock、普通内核和 QueryAbi 两次真实启动。历史 pinned QueryAbi runner 不变。

然后使用已冻结的同一 ELF；`product-evidence` 指向该 gate 的完整输出目录，head/tree 必须来自独立审查的候选：

```sh
python3 -I -B tests/workloads/linux/run_scm_rights_cloexec_guest.py \
  --product-evidence /absolute/reviewed/a06-queryabi-candidate \
  --expected-source-head REVIEWED_HEAD --expected-source-tree REVIEWED_TREE \
  --probe-elf "$scm_work/probe.elf" --expected-probe-sha256 PROBE_SHA256 \
  --a01-initramfs support/build/evidence/2026-10-16/artifacts/initramfs.cpio.gz \
  --output "$scm_work/guest"
```

`--qemu` 和 `--bios` 可指向已验证的隔离安装。环境为 QEMU 8.2.2、原 SHA 固定的 SeaBIOS、q35/TCG/单 vCPU/512 MiB；无宿主磁盘和网络。原 initramfs SHA 固定，重打包仅修改原 init 并加入该 ELF，保留其他成员。caller 给出的 head/tree 需要独立 Git 审查；receipt 的自报身份和文件 hash 本身不能代替该审查。

输出保存实际 kernel/probe/BIOS/initramfs、串口、命令、退出、时间和 SHA256，并绑定原普通内核 build receipt、runner 和 CPIO helper。保留修复前后的结果；新 kernel 的通过结果不能填入历史 kernel 的记录。

## CI 和当前实测

`.github/workflows/a06-kernel.yml` 保留原完整 OSTD/core、普通产品/QueryAbi 和 quota/lifecycle 门禁，新增 Linux 单次静态编译与 27 项对照，并把同一 ELF 放进普通候选 kernel 重放。每次保存 Linux 和 guest 原始证据，guest 未通过则整项 job 失败。

本轮原 Linux 6.18.55 x86_64 对 ELF `0723be7d0ba01f6a94fd4766e4aaf98bc6590de4bbfe431455aefcba8e8eeb56` 实测 27/27。修复前普通 G1-a kernel `f8785d9371f27b1f5e9ccd40da66ea25823ca50bfc7c431a89f20f88a45c4681` 使用相同 ELF 实测 3 PASS、24 FAIL，完整 27 项结束、probe exit 1、raw QEMU exit 33。该 kernel 来源为独立审查的 #197 A06 artifact；修复后的通过情况以新候选实际 CI/产物为准。

本回归不代替固定 Debian 13 profile、Python/Tokio 运行时、完整 Hepta 工具效果、文件系统断电持久化、通用 SMP 或物理/移动设备验收。
