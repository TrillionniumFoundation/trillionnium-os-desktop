# A01 GDB listener 跟进验收

最后一项 A01 review 问题已修复并实际复测：普通 GDB 与 VSCode 的本地 TCP 测试原先先挑选临时端口再释放，recorder 随后重新绑定，竞争者可造成 EADDRINUSE。现在两者直接请求127.0.0.1:0，recorder持有监听器至QEMU继承FD，再由专属readiness记录将实际端点交给原Rust测试。

源码提交 `f57d12f218223ce8287901652565f428941865d9`，tree `c9e7c8a0db9dfa9127fee01869a39cf6dc62c8ae`，唯一父提交 `fd0a5ed637312b13efdbfb6b670d4af52bd2c2b0`。只改support/build/osdk-integration下run.py、record-qemu.py、test_profiles.py、test_record_qemu.py四个文件。完整kernel/asterinas子树仍为 `d83c7720e8c5857cbfa4622e61e3b671a892ced0`，其他源码、模式和原metadata均与父提交一致；README为0字节。完整Asterinas冷构建、普通启动、QueryAbi和Rust入口调试的执行源码仍是fd0，[基线报告](../2026-10-17-main-n0-review/REPORT.md)和全部183,563,309字节归档不改写。

| 验证 | 实际结果 |
| --- | --- |
| 旧问题反例 | 原fd0函数在竞争端口被占用后返回EADDRINUSE；原结构失败和运行行为失败分别保留 |
| host回归 | 18条最终命令全部0，共220次测试执行；实际生成Rust reader的44个语义case通过；另有12项独立host核验通过 |
| 新源码真实集成 | tool session99138外层0、runner0、controller通过、postGit状态干净；22项通过、0失败、0blocked |
| 实际客体 | 11个示例guest全部raw33、无超时；1个VMX上游fallback软跳过 |
| 普通GDB/VSC | 两者请求port0，实际端口分别59717、43773；fd3持有至spawn、QEMU继承后父端关闭；专属ready marker已保存 |
| SDK/测试执行文件 | SDK SHA256 `039f795794fe18ef091f7375859bc4bae90edde6a4d9b021bd815feb741a2e70`，与基线一致；新harness SHA256 `946c704f7e720f108abb90398dba3882865156916b362af8397d69e265065501` |

这是复用已验证Cargo缓存的完整OSDK工具/示例矩阵复测，不是新的完整Asterinas冷构建。原guest断言、符号检查、取消/join和launch文件删除检查保留；独审验证相应Rust函数和断言尾部逐字节一致。readiness reader容忍尚未生成/半写入JSON，拒绝错误路径、schema、profile、PID、handoff、host和端口。显式非零端口及coverage的既有FD交接功能保留。没有因此宣称完整IDE或硬件虚拟化验收。

首次跟进尝试在编译或QEMU前被缓存路径guard拒绝，真实外层1及日志保留。随后将本任务旧缓存目录以同一dev27/inode150742迁入runner规定的support/build/out前缀，保留真实旧harness patch/lock记录；没有放松guard。旧地址的兼容symlink不是新runner使用的target，新的target本身为原真实目录。实际完成controller是 `run-native-v8-gdb-controlled-cache.py`，SHA256 `0b628db76d266d48277aa97f84ab3354c6067b341c252f9b243659cbb39d22fd`；v7失败中提前写出的reuse标记只表示请求，未实际复用或运行guest。

A01分支已以非强推从fd0推进到f57。PR22的18条review线程已依据具体源码、反例和测试逐条解决，最后端口lease线程在本次真实复测后关闭；这不是review approval。创建/回读、逐项映射和全部resolved状态由独立publication组保留。最后证据提交SHA和CI状态在PR最终回读记录，避免提交自引用；旧head绿色结果不代替新head验收。

仍未闭合：A06 core ktest为151通过、2项奇数period oracle失败/raw65，tests-only修正提案未应用或重跑；A06 issue63尾账与严格CPU矩阵、A05 trusted CapSpace/effect operations、A07 G1/G2、KVM/AF_UNIX能力及不可变环境/未知写入者均保留。A00/A06交接评论为 https://github.com/TrillionniumFoundation/trillionnium-os-desktop/pull/22#issuecomment-6230648819 。本次只关闭A01端口lease问题，全项目blocker未全部关闭。

本包保留所有新22项日志、串口、真实argv、source profile、适配Rust、反例和错误配置日志；保留两个受影响guest ELF与实际新harness。与基线相同SDK引用其已校验payload，其余示例ELF按manifest逐SHA/size列明未重复保留。具体retention/omission以manifest为准，不用哈希收据冒充完整字节。小CAS桥绑定f57唯一父提交、四个允许变化和完整内核子树相等；离线verify只读保存字节，不编译、启动VM或执行归档内容。

跟进捕获时，VSC已完成guest的kernel snapshot文件模式从launch记录的0400变为0644，inode/内容大小/mtime保持、ctime更新，稳定FD完整字节SHA仍与launch收据一致。此角色按“post-completion bytecapture、launchSHA相等、stat不匹配”明确标记，严格捕获首次拒绝与观察日志均保留；没有回写原文件模式，也没有识别权限写入者。功能回归结果与这一后续custody限制分别记账，不据此宣称不可变环境或关闭未知写入者。
