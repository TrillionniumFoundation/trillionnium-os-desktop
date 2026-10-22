# AF_UNIX 定向原生证据 — 2026-10-22

## 结论与适用源码

**固定源码 `b824d80d44456c131a6cb9d4fcc84be95c6af273` / tree `506d583455fa5ea2cf0c18fe10ed42c3874f7556` 的完整 aster-core、ordinary AF_UNIX 正控、真实调度正控和两个精确语义负控均已实际完成，并通过独立原文回放。** 这关闭本模块列明的定向回归门禁；原 Agentd 停机、HOS2/G2、完整 E、原 Hepta 持久恢复、UI 和物理设备仍须各自的原 owner 验收。

[模块开发与技术手册](../../../tests/kernel/network/UNIX_STREAM_REGRESSION.md) 解释三处生产源文件、shutdown 发布顺序、reader/aux 锁、`MSG_DONTWAIT` 与 typed `FIONREAD`。本目录只增加文档和证据，没有修改生产实现、probe、协议、oracle、超时或断言。后续文档提交不冒充上述实际运行的源码；本记录也不把并行 SysTree 分支的 core275 与这里的 core274 合并成一个已验收发布组合。

## 原始输入和独立复核范围

[primary 原文包](af-primary-evidence-v1.tar.xz) 为 **554,740 字节**，SHA-256 `e5f8fc0d1d2be66798fe5c3974728b461dfc821148510925b0ddb4761f6fec9e`。[primary manifest](primary-manifest.json) 为包内原 `manifest.json` 的逐字副本，SHA-256 `584256beaac7c477ebbe4e144b7984ec5cd1fe48101bb3e4c308ae2a439579d1`。独立复核逐一比较了209个受控文件与tar成员，加上manifest共210成员；没有用摘要生成串口回执。

包内保存当前v5四条syscall lane、历史v2失败和v3两条controls的原result、完整serial、ordinary首boot、命令/环境、before/after-boot/after-guest快照，另有core原serial与checker、两条原launch工具返回、prepared/results/restored记录，以及16个正向源文件和原历史/controls源字节。[independent-review.json](independent-review.json) 是实际执行离线回放后的完整结构化结果，SHA-256 `86f0e6d603740c46e0c8df7b9dd6f148dc6472200bc7fda297a1222293ee17b6`。

所有21份快照原文已重开；每条lane的三个完整内容相等。复核从每组7,716个tracked entry的路径、mode、Git blob重建了7棵Git tree，再与实际head/tree记录及原源字节交叉核对。三条当前control全树与正向相比只改变`connected.rs`。16个正向源文件、v2/v3各7个历史源文件，以及3个control后像的SHA-256、字节数和Git blob都与相应完整快照吻合。

[完整原文件manifest](full-original-file-manifest.json) 列出209个原执行文件，其中173个文本文件在primary中逐字重开；另36个probe/kernel/initrd/BIOS等二进制实例留在执行端，记录的大小/SHA与每次原result和ordinary首boot相互一致。primary还包含所选源字节和收集元数据，因此其受控文件数也为209，但两份manifest的成员集合不同。**本地没有重开这些36个二进制本体，也没有重新执行guest。** QEMU/cc可执行文件身份、core kernel身份按原执行记录核对；本次不声称重新验证执行端工具或重建ELF。

## 同源实际结果

| 当前lane | 完整原文结果 | syscall/core guest耗时 |
| --- | --- | --- |
| 完整aster-core | 274/274，0 failed/filtered/soft skip；274 starts、36 required names；QEMU33 | 2.421秒 |
| production `positive` / `all` | 8 cases、47 records、PID19、child0、QEMU33 | 1.443秒 |
| `race-fixed` / `shutdown_race` | 64 iterations、64真实窗口、131 records、child0、QEMU33 | 2.156秒 |
| `race-stale` / `shutdown_race` | iteration0，5 records、真实窗口1；成功96字节producer与reap、premature EOF且FIONREAD96，child1、QEMU33 | 1.385秒 |
| `aux-zero-progress` / `credential_only` | 6 records；已读13字节后3次真实零进展、原ELOOP条件，child1、QEMU33 | 1.318秒 |

四条syscall lane均为ordinary `ActionChoice::Run`：各自先完成原product wrapper exit0与首次QEMU33，再将同一最终static probe注入该次原initramfs，用同一kernel/QEMU/BIOS完成第二次boot。实际argv固定q35/TCG/max/1 CPU/512MiB，无host disk/network；`timed_out=false`、`excessive_output=false`，源和boot输入均未变化。负控的runner exit0表示**原oracle接受了指定缺陷**；其实际probe退出为1，不能误写为生产case成功。

core原`environment.json`直接记录b824、干净Git状态、default profile、test_name=null、vcpus1、features空，原core build-input hashes与完整正向快照一致。原launch命令在准备/提交源码后依次执行core与positive，每步原results保留开始/结束时间、exit0、完整logSHA和source_unchanged。core原checker逐字段重放与原result完全一致：serial **35,205字节**、SHA `f665e28b02a7f3aa4e89bb445143a3c109f080ea031b5771c44d07151d1449bf`，core kernel记录SHA `e3f0ec57cb54288a6c11ebb58bb0726ac2d18014c51dca596f368cba0114281a`。这不是由positive摘要倒推出的core版本。

### 每次实际源码

| Lane | Head | Tree |
| --- | --- | --- |
| `v5-positive` | `b824d80d44456c131a6cb9d4fcc84be95c6af273` | `506d583455fa5ea2cf0c18fe10ed42c3874f7556` |
| `v5-race-fixed` | `d35d5b13be0ebae830bab1d546a7f8ac75dc892a` | `1d254fcfd61acbe9cba64c0f4c860f2187e6cc02` |
| `v5-race-stale` | `b9df3b7cc3ff9cd28b3141a62c743ac817e59593` | `300db376d0dda63527f6ba54c75ebd680b9526da` |
| `v5-aux-zero-progress` | `5f25b73a7daaf03e2997107a88ab139a1ebe3a23` | `05f74c39ebdd51d534a03e8ccf0e56b4eebbe790` |

所有current controls完成后，原`unix-stream-controls-v5/restored.json`记录回到生产b824的原分支；稍后原collection记录再次确认同tree且干净。独立复核保留原命令和时序，不用收集时的状态替代执行时的source检查。

### Payload、工具和锁身份

| 输入 | SHA-256 |
| --- | --- |
| final C probe source | `bb7e334a76c4e201b3ef33842be7f87a235a6940d783c8c741d63839519ab747` |
| final static probe ELF (recorded) | `701821798ff6b052aa7e2b0dd0da238ef517adf0313ad9d50175f40ebecaa56e` |
| unchanged original oracle | `eefb0f272d2c396ea6fa87c0af827f795b115ca7607c6746abf80975fe544489` |
| unchanged protocol | `6577cd26c72c80f370cd4a654463316bf7fa5227a33a0e9ff3ade0e05eb9e680` |
| final native runner | `81d84a3c3d2a476c7b1eb467f04254b1613a4b5b7f82066ab4b5c9e839d9f1c0` |
| QEMU (recorded) | `8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854` |
| C compiler (recorded) | `1b99826121ae6682a634e5efe09bd3e3df58ce58e0b28f849114ab5b89139c26` |
| BIOS (recorded) | `1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735` |
| ordinary generated lock | `e54bc99b3df5e21a1fdcd88d89b32ac478e73c7b4bf69ae0b1084f59d56fc506` |
| core generated lock | `85ccdcd1283d42af82ee8dca2faac2ee5401631ff150b35e43be46e1fc9c2150` |

| 当前lane | Kernel ELF记录SHA-256 | 完整serial SHA-256 |
| --- | --- | --- |
| `v5-positive` | `956438a6f2cad39a2d73093004909e34cf66e9b7d4bdccda67287cf62bb2d14d` | `5625eaa1960686c3b7da4033476490424118c6ef20992bf881989054481ab79e` |
| `v5-race-fixed` | `b44c692c36cb332f40b4ecdaa234e2e05080fdf4dc24d496d9fe0b8163a46b50` | `73ff289c172c11c000fd86192c42aea8a982c2467f40b03835c2ac809e70eb6d` |
| `v5-race-stale` | `8cc2cab9efaae5d28cbd9bdaed7c4ac1d2a56fe8774f7d33bff56fee95ab3b43` | `b0a50d18579bcdcf2146c75940a84f5fab590b57df1349372ece299fd22e9f4e` |
| `v5-aux-zero-progress` | `6bdccb7df65af499b47584f8533f067a6af77fe7f757ee5d967663362adba8dc` | `61343dee49246f05c09799bedec1a5ee2b7ee82a8ed3ddeb5bb490d1fe832825` |

每次nonce、serial字节数、initrd身份、完整oracle字段和原文件路径均在独立review与primary原件中。协议/oracle未因观察到失败而放宽。最终C probe增加了FIONREAD assertions，旧probe源码`476a7ad3…` / ELF `052f016f…`与最终`bb7e334a…` / `70182179…`分开记录；不能把不同payload结果拼成同一实验。

## Controls及实际缺陷条件

`race-fixed`在实际空长度观察后让真实producer写入并shutdown，保留早期shutdown快照；全64次均出现真实窗口并正确完成。`race-stale`在相同调度场景把shutdown快照移回旧位置，实际读到0后producer已成功写96并被reap，FIONREAD仍报告96；原oracle只接受这一完整条件，不接受一般失败。

`aux-zero-progress`恢复原缺少zero-read退出的行为，在已累积13字节、无剩余payload且shutdown可见时观察3次真实不变循环，输出精确`UNIX_STREAM_AUX_ZERO_PROGRESS count=3 read_bytes=13 remaining=0`，随后原probe报告`recv_credential_only expected=13 observed=-1 errno=40`。它采用有界诊断退出，没有以挂起或任意errno替代旧缺陷。

| Control | 源内冻结patch SHA-256 | 实际执行Git diff SHA-256 |
| --- | --- | --- |
| `race-fixed` | `d262cc32b91f9b1bbdb494db6048c8a6f8a67229b465260d23fc4ddbf44e9a2a` | `010b267c3c8851fc53602c7f21e3831f1fd5bb5adbda637599d07255590a87c0` |
| `race-stale` | `3fadd31c117b5a2f4732a592e7261eccbef94b5652b171a48207551d20e3f544` | `dbd2905a076c7bdd4f608c288a052b57322b81541620a65c153cdfcd89d4f097` |
| `aux-zero-progress` | `d9eb294d03b16df8bc8749f1927d87e2fe63a29399518d868a7c2ec03c5387e5` | `2c366b769943d7146ad35020cce0cede6faba17a3acc13c23ea338c4eca59f0c` |

两列不同是保留文件形式不同；复核分别在隔离临时目录执行原`git apply --check`和apply，得到与archived source及完整control tree完全相同的后像。三项control没有进入生产正向源码。主review同时保留两种patch身份，不将其伪写成逐字相同。

## 历史失败保持原结果

| 历史阶段 | 原始观察 | 结论 |
| --- | --- | --- |
| v2 positive `a2779f07…` | open_empty的before_recv之后，原20秒alarm导致shell exit124；21.414秒，QEMU33。原oracle完整重放为`independent probe exit or identity mismatch`。 | 保留为失败；不是合格语义负控。 |
| v3 race-fixed `598b4076…` | 旧probe下64 iterations/64窗口/131 records通过。 | 仅属于旧probe和旧source，未替代v5重跑。 |
| v3 race-stale `7b5166c0…` | 真实producer96/shutdown/reap后读0，但`race_fionread`返回-1/errno25；原oracle完整重放为`noncanonical failed iteration`。 | 必需queued-byte witness缺失，保持未合格。 |
| v4 pre-execution | 原format.log给出socket.rs listener arm的rustfmt差分；后来找回原job exit1、no timeout、完整446B stderr，明确两source的`rustfmt --check --edition 2024`返回1。 | 在commit/native执行前退出，无native guest结果，不算负控。 |

v4旁路补件见[独立补充核验](v4-supplement-review.json)、[原命令选择字段副本](history-v4/source-command.json)、[原exit](history-v4/exit.json)及[原stderr](history-v4/stderr.log)。命令选择字段已与留存原request逐一相等核对，并保存其SHA；完整Runtime request/started metadata不在本仓库证据中。这里没有重新启动历史job，也没有事后制造失败回执。

主`independent-review.json`和原primary在补件找回前已完成并冻结，其v4字段准确描述“primary内只有format输出”；现在原字节仍保持，v4补充核验单独增加原退出证据。最终v5格式检查为空输出且后续prepared/core/positive均真实完成。host相容性原log与results也完整保留，但从未计入native gate。

## 离线复核与后续开发

以下只读取证据并在临时目录apply已固定的controls；不会build kernel或调用Runtime。Python需要3.11或以上及本地Git。`AF_RECORD`指本目录的绝对路径，`AF_REPLAY`为新的临时目录：

```sh
AF_RECORD=/absolute/path/to/results/integration/2026-10-22-unix-stream
AF_REPLAY=$(mktemp -d)
mkdir "$AF_REPLAY/raw"
tar -xJf "$AF_RECORD/af-primary-evidence-v1.tar.xz" -C "$AF_REPLAY/raw"
python3 -B "$AF_RECORD/replay_native_evidence.py"   --root "$AF_REPLAY/raw"   --archive "$AF_RECORD/af-primary-evidence-v1.tar.xz"   --index "$AF_RECORD/evidence-index.json"   --output "$AF_REPLAY/independent-review.json"
cmp "$AF_RECORD/independent-review.json" "$AF_REPLAY/independent-review.json"
```

[replay脚本](replay_native_evidence.py)锁定本primary SHA与原oracle/checker，完整重放7条syscall原oracle、1条core原checker、21份快照和7棵tree，复核普通启动/原launch/core来源、两类control patch及restore。v4补件保留独立hash和原失败退出；它不改变current gate。原request未发布，第三方可复核选择字段副本与原stderr/exit，但不能从仓库重开未发布request本体。

继续改内核时，保持同一实际源码/探针/工具组合，重跑完整core、production positive、scheduled positive和两个原精确负控；随后再执行对应完整仓库CI与跨仓组合门禁。本包未执行完整A06/OSTD/SMP或并行分支合并后的新组合。原Agentd停机仍须以原daemon、原runtime和原writer的实际生命周期与恢复观测单独闭合，AF_UNIX定向成功不能替代它。
