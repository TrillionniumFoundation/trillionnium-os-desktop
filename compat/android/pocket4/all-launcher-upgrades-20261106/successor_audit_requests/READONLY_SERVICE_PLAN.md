# 新 successor 的 Launcher 与有效权限只读采集计划

## 当前可执行基础与证据边界

本计划绑定已真实 qualified 的 runtime epoch `a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9`。guard 路径为 `/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py`，3213 B，SHA256 `d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3`。后续正常升级结束后，全部操作须绑定最后一份实际 versioned App scope；初始 scope 不能冒充升级后的事实。

这是一份待协调执行的计划。本文没有执行目标机命令，没有生成新的 UI、安装或权限授予 authority，也没有声称有效权限已经验证。原 r1 restart UNKNOWN 与旧 Bili launch UNKNOWN 原样保留。

已审的 `successor_qa/reference/r5/recorder.py` 提供 `Flow.android(argv, timeout, mutation=False)`、`Flow.admission()`、`Flow.guard()`、`Flow.begin()` 和 `Flow.close()`。`successor_qa/templates/flow_methods.py.in` 将 Flow 绑定到真实 successor guard、每个目标包的实际 UID/APK/data 身份和新 source manifest；旧 r9 的源、epoch、flow scope 不能沿用。

`Flow.android` 经 `MainBinding` 和 `bound_android_transport.py` 进入已经持有的容器 namespace，逐次记录 command/transport intent 与结果，并执行原 classpath、进程、UID、source 和 guard 检查。它是已有的传输能力，不是对任意 Android 服务命令存在性的证明。

## 1. 先取得 fresh native Launcher catalog

由唯一协调进程在无未决安装时持有原全局 action lock，检查最新 guard、46 包实际 scope、固定 CLI/daemon 字节与当前 native owner。用既有 UID1000 caller 和环境读取 native status 与 applications；两个调用须使用相同 caller 和 socket，不能用一个 caller 的 status 代替另一个 caller 的目标选择。

已有实际成功使用的 catalog 命令形状为：

```text
/usr/bin/sudo -n -u #1000 -- /usr/bin/env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus /usr/bin/droidloomctl --json applications
```

这是 argv 数组的显示形式；实际执行必须传递数组，`#1000` 不是 shell 注释。socket 参数若显式加入，必须沿已经实际确认的 CLI 接口，并在 status 和 applications 中一致使用。

已读 `install_path_review/control-prefix.rs` / `control-install.rs` 的 `list_applications` 路径：校验 Android user、解析 caller 所属 active cell，等待 Android init，取得真实 system_server，然后调用 framework 内 application catalog 的 `list --user USER`。它不调用 native launch。当前材料没有闭合整个源码树与 live ELF 的完全同构，因此仍以真实返回、owner/guard 前后检查和当前解析结果作为运行证据。

原样保存 native response、完整 package/component 列表及源码/命令/terminal pins。另行计算规范化集合 digest，不能覆盖原始 component 字符串。与此前 45 包清单比较；新增、消失或默认入口改变均作为事实报告，不把旧名单强压成当前结果。新增入口需要明确扩展审计 scope 后再执行其 QA。

## 2. 通过新 per-App Flow 做真实默认入口解析

每个包使用新生成并固定的 source contract 和独立 flow，精确 target package/UID/data/APK scope。先执行 `Flow.admission()` 验证容器内 `cmd package list packages -U --user 0 PACKAGE` 的 UID 与当前 scope 一致，然后在新的只读 step 中调用以下已有路径中的查询：

```python
raw = flow.android([
    '/system/bin/cmd', 'package', 'resolve-activity', '--brief',
    '-a', 'android.intent.action.MAIN',
    '-c', 'android.intent.category.LAUNCHER',
    flow.scope['package'],
], timeout=8, mutation=False)
```

此 argv 来自既有 `android_app.py` 的解析部分。既有 `op=launch` 随后会调用 `am start -W`，所以不得为了查询入口而调用旧 helper 的 launch 操作。这里只提取查询 argv，经新绑定的 `Flow.android` 执行。执行前还须确认该 scope 的 Android user 是 0；如果使用显式 `--user 0` 变体，先由同一 bound transport 的真实 `cmd package help` 确认其接口。

结果按 UTF-8 严格解码，只接受一个属于目标包的真实 component。无结果、多结果、resolver activity 属于别的包或无法解码均保留原文并标记未确定；不能在失败时自动启动 App、移除 task 或采纳另一个包。解析到的 component 与 fresh native catalog 对照并记录二者，作为后续新 QA source 的输入。

## 3. 有效权限：先确认真实服务接口

目前已有资料仅证明 saved permission flags 和 XML/ABX records；`runtime-permissions.xml` 不是全部权限的权威覆盖，缺记录也不等于拒绝。现有 ActionRunner 只有 state/inspect/click/text 等操作，没有已实现的 permission 查询操作。原 helper 的 state 不连接 UiAutomation，但它也不提供 PackageManager permission grant 结果。

因此新的只读 observer 首先经已经 admission 的 Flow 采集：

```python
package_help = flow.android(['/system/bin/cmd', 'package', 'help'], timeout=8, mutation=False)
appops_help = flow.android(['/system/bin/cmd', 'appops', 'help'], timeout=8, mutation=False)
role_help = flow.android(['/system/bin/cmd', 'role', 'help'], timeout=8, mutation=False)
```

这些是拟提交的只读能力核验调用，本文未声称本机都支持它们。保存完整 stdout/stderr 与 terminal；任何命令未正常结束、出现 guard 差异或 held child 未 joined，应停止该 step 并保留原结果，不能自行切换 epoch 或重试未知状态。

若本机实际 help 明确给出 `check-permission PERMISSION PACKAGE [USER_ID]` 的格式，则仅对已经实际 APK manifest 审计取得的精确原始 permission name，在相同 target scope 中逐项执行：

```python
raw = flow.android([
    '/system/bin/cmd', 'package', 'check-permission',
    permission_name_exact, flow.scope['package'], '0',
], timeout=8, mutation=False)
```

这个接口格式尚待本机能力核验；不能直接将上述计划写成“已验证命令”。只将实际明确的 granted/denied 服务响应记录为该精确名称的 PackageManager 查询结果。未知命令、异常、额外不可解释输出、不可传递的空/NUL 名称都保持 UNKNOWN。

原 manifest 与 saved records 中的名称绝不 strip/纠正，例如此前贝壳权限名前的空格须完整保留。非规范名称的响应单独记录；不能将它映射成去空格后标准 permission 的授权。声明权限、saved flags、PackageManager result、AppOps mode、role holder 和实际功能结果使用不同字段。

若实际 shell interface 不提供查询，应先停在明确的能力缺口。可在独立新 revision 中给现有 owned self-instrumentation 增加固定目标的只读 PackageManager 查询，继续原 UiAutomator/sidecar 路径；这需要新的源码/manifest/身份绑定和实际响应验证。它不是当前 helper 的既有功能。不得借用别的包 scope、添加危险权限、调用 adoptShellPermissionIdentity、引入 ADB 或通过改变权限来获得观察结果。

## 4. AppOps、role 与实际功能分别取证

在真实帮助输出确认语法后，AppOps 只读 `get` 查询限定目标包与需要解释的操作，例如 fine/coarse/background location、camera、microphone、media/storage 和通知。禁止 set/reset/start/stop 等改变状态的命令。优先逐项查询需要的操作，避免导出不必要的使用历史或位置内容。

role 仅查询实际有关的系统 role holders，解释默认拨号/短信等系统 App 的权限来源；不得 add/remove/clear role holders。未证明相关性或未取得实际服务结果时为 UNKNOWN，不把一般 App 的权限全部归因于 role。

PackageManager grant 不等于功能一定可用：仍需实际 App 核心操作、网络/存储成功或拒绝路径、foreground/background 条件、长时间运行及故障恢复证据。全局定位开关若需要，只读其状态，不读取坐标或主动打开。美团外卖 location grant 和开关均维持原边界；读取失败不能触发授权修复。

## 5. 只读 observer 的执行封装

新封装须显式固定自身源码、生成后的 recorder/source manifest 和 current scope，持有原 flow lock 与全局 action lock，以唯一 step 名写 durable read-only intent。只允许本计划的闭集查询 argv；没有任意 shell、任意 service 子命令或 fallback launch。

`recorder.py` 原 CLI 的 choices 没有新 service 查询操作，不能把一个自定义 operation 直接丢给原 main dispatch。应使用经审查的独立 wrapper 调用已有 Flow API，或另建明确 source revision 的只读 dispatch；不能把旧未知 launch 的 step 改成新查询 step。

结算顺序为：新 Flow/admission → 能力或服务查询 → guard 与 scope 再检查 → `Flow.close()` 的 held binding 关闭 → 原样 durable result →进程退出释放原 flow lock。保留原 recorder 的单进程、command join、异常和证据发布规则。parent 在 authoritative terminal 证明完成、输出 durable 且无在途子进程后，才继续下一包或 UI 操作。

最终每包记录至少包含：package/component/UID/user、runtime/framework/source/scope pins、实际 manifest 权限名称、每次服务查询 argv 与 raw response pins、未解释项与原因、saved permission flags 前后对照、descriptor/child/lock 结算，以及核心业务与拒绝/恢复测试的独立证据。未完成这些项目的 App 不得标为 production ready，不能清理其旧构建或实验产物。

## 已固定的 APK 审计请求

`initial-reference-r1/` 已保存 13 个请求，覆盖 45 个唯一 Launcher 包；导入 SHA256 `faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a` 的已审 collector 后，13 个 request schema 和分区一致性通过。它们仅是初始引用；实际全量升级完成后由 `prepare_requests.py --phase post-upgrades` 生成另一组 request/output roots，并绑定最后一份实际 scope。每批最多四包、4 GiB，单 APK 最多 512 MiB，完整 base/split 集必须全部审计。

初始 scope 原文曾在环境重置前核实为 57713 B / `19d742f98193a09403990ed3ee6944d4624a26690fb953d66cac4361af6f6d77`；当前准备记录没有声称每批字节合计已在重置后的本地计算。执行 collector 时仍会从实际 pinned scope 强制检查容量边界。Fcitx 和 microG 的前两批只读审计；官方 release SHA 对照可追加实际 staged evidence pin，不要求重装或更换输入法。
