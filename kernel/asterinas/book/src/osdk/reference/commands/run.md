# cargo osdk run

## Overview

`cargo osdk run` is used to run the kernel with QEMU.
The usage is as follows:

```bash
cargo osdk run [OPTIONS]
```

## Options

Most options are the same as those of `cargo osdk build`.
Refer to the [documentation](build.md) of `cargo osdk build`
for more details.

Additionally, when running the kernel using QEMU, we can setup the QEMU as a
debug server using option `--gdb-server`. This option supports an additional
comma separated configuration list:

 - `addr=ADDR`: the network or unix socket address on which the GDB server listens
    (default: `.osdk-gdb-socket`, a local UNIX socket);
 - `wait-client`: let the GDB server wait for the GDB client before execution;
 - `vscode`: generate a '.vscode/launch.json' for debugging with Visual Studio Code
    (Requires [CodeLLDB](https://marketplace.visualstudio.com/items?itemName=vadimcn.vscode-lldb)).

Besides, to collect coverage data, we can use option `--coverage`. This option
enables the coverage feature and collect coverage data to `coverage.profraw` when exit.

OSDK uses a temporary UNIX socket for its managed QEMU monitor by default.
Use `--qemu-monitor-transport=tcp` to select an ephemeral IPv4 loopback connection.
OSDK creates both ends of a private connection on `127.0.0.1`, closes the
listener before spawning QEMU, and passes QEMU its connected socket descriptor.
An unrelated client arriving during setup is rejected.
This option selects only the transport;
the managed monitor still requires its usual configuration,
such as `--coverage` together with a configured QEMU `log_file`.
It does not change the guest shutdown behavior or guarantee coverage export.
For example:

```bash
cargo osdk run --coverage --qemu-monitor-transport=tcp
```

See [Debug Command](debug.md) to interact with the GDB server in terminal.

## Examples

Launch a debug server via QEMU with an unix socket stub, e.g. `.debug`:

```bash
cargo osdk run --gdb-server addr=.debug

```bash
cargo osdk run --gdb-server --gdb-server-addr .debug
```

Launch a debug server via QEMU with a TCP stub, e.g., `localhost:1234`:

```bash
cargo osdk run --gdb-server addr=:1234
```

Launch a debug server via QEMU and use VSCode to interact with:

```bash
cargo osdk run --gdb-server wait-client,vscode,addr=:1234
```

Launch a debug server via QEMU and use VSCode to interact with:

```bash
cargo osdk run --gdb-server --gdb-vsc --gdb-server-addr :1234
```
