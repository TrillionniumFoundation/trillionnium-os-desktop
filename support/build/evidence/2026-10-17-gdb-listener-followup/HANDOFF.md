# A01 当前构建入口与交接

完整内核目录为kernel/asterinas/，固定Asterinas v0.19.0/c4b7ed575b7b32773475b194d2ad41fb6d03765b和nightly-2026-07-21。当前host修复源码为f57d12f218223ce8287901652565f428941865d9；整个kernel/asterinas仍与实际冷构建producer fd0完全相同。许可证、上游文档与根README0字节要求保留。

在已验证的任务环境，完整内核开发者入口仍为：

```bash
source /workspace/scratch/ae1a8cf05419/round-current/env.sh
bash support/build/kernel.sh kernel
bash support/build/kernel.sh run_kernel
```

使用尚未存在的新A01_RUN_DIR分别保存构建/启动记录；固定1vCPU/512MiB/q35/TCG与小initramfs。实际产物为kernel/asterinas/target/osdk/asterinas/asterinas-osdk-bin.elf，由bundle.toml绑定；不要使用不存在的release/asterinas路径。基线实际ELF SHA256为ed469d2ff7636b7d60c52a011b1d9685d8b3096bd79f7c94ef813bdb023e6dc9。

本次GDB修复的完整22项复现命令（下面是说明，不是额外测试记录）：

```bash
source /workspace/scratch/ae1a8cf05419/round-current/env.sh
export A01_NATIVE_CHECKOUT=/tmp/trillionnium-a01-native-fd0
export A01_NATIVE_OUTPUT_ROOT=/workspace/scratch/ae1a8cf05419/native-gdb-lease-followup
python3 -B -I /workspace/scratch/ae1a8cf05419/round-current/run-native-v8-gdb-controlled-cache.py \
  --producer f57d12f218223ce8287901652565f428941865d9 \
  --phase osdk --label NEW_UNIQUE_LABEL
```

旧目录名含fd0不表示当前HEAD：运行前必须核验该worktree是f57且状态干净。label必须未用。controller要求完整kernel子树与fd0相同，缓存为该checkout/support/build/out/fd0-integration-cache/target，属于实际旧缓存迁移；没有合格的旧缓存时，直接用runner的新output与默认新target，不伪造cache marker。独立入口为：

```bash
python3 -B -I support/build/osdk-integration/run.py --local-tcp --coverage-gdb \
  --output /absolute/new-output
```

TCP、UNIX及硬件能力分开验收；本轮22工具/示例通过不替代Asterinas core的两项失败。

| Owner | 可开始的具体接口 |
| --- | --- |
| A05 | kernel/asterinas/kernel/core/src/process/process/mod.rs；kernel/asterinas/kernel/core/src/syscall/ioctl.rs；kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs；QueryAbi已真实验证，trusted authority/effect操作仍需实现 |
| A06 | kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs；kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs；先处理奇数period测试oracle，再实际core回归及issue63尾账/严格矩阵 |
| A00协调 | OSTD scheduler、跨owner退出身份及最终main整合；A01不自行应用core提案 |
| A01 | support/build/**、support/upstream-lock.json、上游构建配置和证据；本次仅四个integration helper/test文件 |

原基线HANDOFF提供完整依赖恢复、Rust入口调试和QueryAbi复现；本包提供端口lease修复和新完整矩阵跟进。源码SHA、结果与最终证据提交SHA分开记录。
