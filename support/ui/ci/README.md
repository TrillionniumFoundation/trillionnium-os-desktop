# A00-owned GitHub CI handoff

The strict source format check is never silently bypassed. On failure,
the workflow additionally saves an ephemeral `rustfmt.patch` file so A10
can review/apply actual formatter output in a subsequent owned commit,
even if Cargo compilation failed before reaching the formatter gate.

本目录保留 A10 的历史 CI handoff 模板；当前实际自动执行入口是已入仓库的 [.github/workflows/a10-host.yml](../../../.github/workflows/a10-host.yml)，由 A00 维护。修改门禁时以该真实入口及它调用的脚本为准；不要将本目录模板再次覆盖到 canonical workflow，也不要把仅存在模板视为完成 CI。

The workflow records compiler, unit-test, and rustfmt output (including
failures), the tracked ui/Cargo.lock, and software-Wayland logs in a
downloadable a10-host-evidence Actions artifact. The artifact deliberately
excludes runtime sockets and ephemeral app process directories.

UI workspace 的 [Cargo.lock](../../../ui/Cargo.lock) 已提交，实际 host 工具链和依赖条件见 [RUN](../RUN.md)；不存在“当前没有锁文件、等待首次生成”的前置缺口。依赖锁、编译成功与完整运行资格分别判断。工作流必须保留真实 Cargo build/test、严格 Clippy、fmt 与环境版本输出；本地执行、历史 CI 和当前 head 的 GitHub 结果分别记录，queued 不表示通过。

On a Linux runner with Weston, Mesa/llvmpipe, and Rust, run
`bash tests/ui/headless-weston.sh`. It starts/stops its own Weston compositor
inside a private runtime, then calls `bash tests/ui/smoke-wayland.sh`.
The handoff CI workflow includes both Cargo host tests and this smoke step.
When Weston is absent the script explicitly fails, not skips/claims success.

On an already running Wayland workstation, execute
`bash tests/ui/smoke-wayland.sh` directly. This smoke checks three native app child
PIDs, their first-egui-update markers, Shell restart and cancellation. It
does NOT attest compositor-mapped surfaces, real CJK candidate UI, GPU
reset, permissions or new kernel boot. Never collapse host GUI checks into
the HOS2/N0 OS gate.

Even when A00 installs a workflow variant without a separate formatter-patch
step, the A10-owned `tests/ui/check-host.sh` produces
`$RUNNER_TEMP/a10/rustfmt.patch` on a formatting failure and exits nonzero.
The existing `a10-host-evidence` artifact path includes this patch.

If CI fails, preserve real logs, patch the Rust code, regenerate a reviewed
lockfile, rerun; do not silently remove tests or call no-run code VERIFIED.

The A10-owned `check-host.sh` now performs an EXIT-stage format check even
if Cargo compilation or Rust tests fail earlier. It writes both
`rustfmt-check.log` and, when needed, `rustfmt.patch` to the already
configured `$RUNNER_TEMP/a10/` artifact directory. The hook never converts
an earlier build/test failure into a success or invokes a GUI.
