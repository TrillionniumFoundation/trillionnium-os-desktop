# HOS2 ABI codec

`hos2-os-abi` 是无第三方依赖的 `#![no_std]` Rust 字节编解码模块，供内核控制入口和客户端共享。入口是 [src/lib.rs](src/lib.rs)；协议定义与错误语义见 [原生控制 ABI 与恢复契约](../../docs/NATIVE_ABI.md)。HOS2 2.0 仍是实验协议。

## 技术边界

- 请求、响应使用固定 64 字节头和逐字段小端编码；32 字节 transport 单独验证。禁止把 Rust 结构体布局直接作为线协议。
- 支持 QueryAbi、ReadUsage、InstallBudget、QueryDelivery、RetireThrough 的格式及结构性检查，包括保留位、长度、关联 ID、投递序列、响应状态和容量。
- `decode_response_for` 校验请求关联；接收预分配缓冲区时使用 `decode_response_prefix_for`，只消费响应声明的范围。解析函数不执行用户地址访问，也不授予权限、提交预算或证明持久化。
- 五种格式可编解码不代表产品开放五种效果。ordinary 内核仍以实际 QueryAbi 宣告为准；`hepta.anon.*` 私有计费接口不属于这个 HOS2 wire codec。

## 开发与验证

修改字段、opcode 或语义时，同时更新协议文档、[独立固定样本](../../tests/golden/hos2.json)和 [Rust 回归](tests/)。不要从待测 codec 自动生成唯一预期样本。测试覆盖合法字节、畸形输入、transport 预检、语义边界、响应快照和 mutation 负控。

从仓库根目录运行：

```sh
cargo +nightly-2026-07-21 test --manifest-path libs/os-abi/Cargo.toml
cargo +nightly-2026-07-21 fmt --manifest-path libs/os-abi/Cargo.toml -- --check
python3 -I -B tests/abi/run_acceptance.py --output-dir /absolute/new/abi-evidence
```

完整验收入口会生成源码与执行证据，输出目录必须是新的目录；历史通过记录不能代替当前源码测试。[A02 验收说明](../../tests/abi/A02_REVIEW_CLOSURE_2026-10-17.md)解释固定样本、工具链和负控；[内核控制回归](../../tests/kernel/control/README.md)负责验证普通内核中的真实边界。
