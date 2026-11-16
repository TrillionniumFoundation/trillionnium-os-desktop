# 交付给主线：三个剩余 host support 绑定修复

唯一候选目录：`/workspace/scratch/347ef2dfe9ad/runtime-acceptance-audit/late-app-host-support-candidate/`。

该目录可作为源码与 CI capsule 发布。未修改 `pub`、远端 canonical、CURRENT 或现有 frozen preparation；未上传 Git。目录冻结后请以 `PACKAGE-MANIFEST.json` 核对完整文件列表和摘要。

## 改动边界

- QuickSearch 当前 r2：18 个生产源，只有 `app_common.py` 改变。
- Settings 当前 r1：17 个生产源，只有 `app_common.py` 改变。
- WebView 当前 r1：22 个生产源，`app_common.py` 和 `webview_entry.py` 改变；entry 仅 R9→HOST 错误文案。
- 总计 57 个生产文件，4 个改变、53 个原字节。完整路径、大小和 SHA 在 `source-manifest.json` / `PRODUCTION-INVENTORY.md`。
- 三个新 common 都是已在当前 business-app r4 使用的原字节 `6003e96be02cd0c6328340865bbb2962d39967f2b823656af258ed5a48f598d0`。去掉 SUPPORT、SUPPORT_REF、CLOCK_SUPPORT_REF 三个赋值后，三个 common 与旧原件 AST 完全一致。未调整条件、预算、业务操作、任务归属或清理算法。

明确 blocker 是 identity 分支在 `collect_identity` 前把 qualification.source_manifest 与旧 SUPPORT_REF 比较。最新 host baseline 因此必然被拒绝。plan/execute 路径也通过同一个 common 选择 support。不是仅搜索到了旧目录名。

## 本轮实际验证

`validation/local-controls.json` 对应本地执行 chunk `ad7282`，exit 0，15/15。每份适配器各 5 项：原件拒绝新 host、候选接受正确 host 的全部角色、拒绝旧/clock/篡改 ref、真实本地 inspect-source CLI 成功、真实 bootstrap 拒绝 pin 后被篡改的 common。

身份采集器和 bootstrap 只在 identity 控制中替换为明确 mock，校验与分支使用原 entry 代码。inspect-source 则执行真实入口，但 preparation 是临时本地源码控制构造的包。没有构造 BusinessBaseline，没有启动 Main/Android，没有执行真实身份采集或应用业务。此结果不能写成 Pocket4 实机应用通过。

单条可重放命令（任意 cwd）：

```sh
python3 -B -m unittest discover -s /workspace/scratch/347ef2dfe9ad/runtime-acceptance-audit/late-app-host-support-candidate/tests -p 'test_*.py' -v
```

## 原件与资产

三个原 packet 的 preparation 完整引用、全部生产原件引用和 origins 在 `source-manifest.json`。只发布原始源码内容、精确依赖元数据与紧凑控制结果；代码回归 fixture 仅旧 common 和旧 WebView entry，不含资格数据。

生产 files 列表没有独立非 Python 文本资产。WebView 文本资产在两个 assets Python 中原字节保留。外部原 WebM 视频只留路径/大小/hash，未读取或复制二进制。源码资产与实际设备必须提供的支撑、原件、权限/租约/新 baseline 详见 README 和 `runtime-dependencies.json`。

QuickSearch/Settings 原 preparation 的 r9 manifest origin 仍是合法出处。封存新 preparation 时请保留原 origins 检查及现有迁移的 provenance 规则。不要把原 source-manifest 中额外 audit/provenance 条目删成仅生产文件列表。旧过程产物的最终清理由主线在证据闭合后处理，本候选不解除任何 source pin。

## 主线最小后续顺序

1. 核对 PACKAGE-MANIFEST / patch，选择三个独立 host migration 目的目录；复制本 capsule 对应 source/quicksearch、source/settings、source/webview 的完整生产文件。
2. 按现有冻结迁移模式重新生成目的路径对应 preparation/source manifest，保持原 schema、业务 scope、origin pin 和 publication 不授权 Android 的边界；旧 packet 原件保持可核查。此次候选不伪造或预先宣布设备封存完成。
3. 对每个实际封存包执行一次原入口 `inspect-source`，参数为新包的真实绝对 preparation 路径及实际摘要。入口文件分别是 `search_entry.py`、`settings_entry.py`、`webview_entry.py`。只读入口示例结构：`python3 -I -B <sealed-source>/<entry> --preparation <sealed-preparation> --expect-preparation-sha256 <actual-sha256> inspect-source`。这些是尚待填入真实封存回执的参数，不能复用本地 synthetic preparation。
4. 保存 compact 实际观测后，由主线通过 Mac 正常 Git 通道发布；后续业务运行仍使用 fresh Main-bound qualification 与原 gates。当前新增测试不改变原 45-app 已验收数。

## 扫描范围与非缺陷边界

`../support-sweep-readonly/sweep-source-observations.json` 保留 11:06:53Z 快照。business-app r4、business-system r4、SAF11 r4、documents-search-sort r4、Clock r3、Calendar r3 与五个最新 Gallery packet 的 active source 未命中 r9/r10，所选源码 hash 和 embedded refs 一致。原 six-composition actual inspection 记录也是 source-only；不是本轮新执行。

照片补查已成功完成：job `1a1bae28740-12894-1e0a`，exit 0，output_complete/durable/terminal publication 均 true。Photo app r4 的 17 个生产源与 active host/host-clock 引用符合。Photo display r4 当前 wrapper 固定的是这份 photo r4 preparation。其 display holder、display lease、capture lifecycle 三个外部源码依赖不在本次 qualification 子树选取范围，明确没有额外读取；这是未覆盖，不是 hash 失败。完整只读结果位于 `../support-sweep-readonly/photo-source-observations.json`。

`prep_manifest_files_equal=false` 的三项来自 manifest 包含额外 provenance/audit，prep 只列生产源；未作为缺陷。`skip_out_of_source_scope` 也未被解释为校验失败。Editor/Probe 已由主线修复封存，Camera video 由另一代理负责，本候选没有重复改动。
