# Networking & Sockets

<!--
Put system calls such as

socket, socketpair, bind, listen, accept, connect, getsockname, getpeername,
sendto, recvfrom, sendmsg, recvmsg, shutdown, setsockopt, getsockopt,
sendmmsg, recvmmsg, accept4, recvmsg, and socketcall
under this category.
-->

## Socket creation

### `socket`

Supported functionality in SCML:

```c
{{#include socket.scml}}
```

For more information,
see [the man page](https://man7.org/linux/man-pages/man2/socket.2.html).

### `socketpair`

Supported functionality in SCML:

```c
{{#include socketpair.scml}}
```

For more information,
see [the man page](https://man7.org/linux/man-pages/man2/socketpair.2.html).

## Socket setup

### `bind`

Supported functionality in SCML:

```c
{{#include bind.scml}}
```

For more information,
see [the man page](https://man7.org/linux/man-pages/man2/bind.2.html).

### `connect`

Supported functionality in SCML:

```c
{{#include connect.scml}}
```

For more information,
see [the man page](https://man7.org/linux/man-pages/man2/connect.2.html).

### `accept` and `accept4`

Supported functionality in SCML:

```c
{{#include accept_and_accept4.scml}}
```

For more information,
see [the man page](https://man7.org/linux/man-pages/man2/accept.2.html).

## Socket communication

### `sendto`, `sendmsg` and `sendmmsg`

Supported functionality in SCML:

```c
{{#include sendto_and_sendmsg.scml}}
```

Unsupported flags:
* `MSG_CONFIRM`
* `MSG_DONTROUTE`
* `MSG_DONTWAIT`
* `MSG_EOR`
* `MSG_MORE`
* `MSG_CONFIRM`
* `MSG_OOB`
* `MSG_FASTOPEN`

Partially-supported flags:
* `MSG_NOSIGNAL` is implemented for `AF_UNIX` stream and sequenced-packet sockets.
  A Unix stream send that fails with `EPIPE` before making progress
  queues `SIGPIPE` to the calling thread unless this flag is present.
  The flag preserves the `EPIPE` return and changes only this send operation.
  Sequenced-packet sends preserve Linux's behavior without the stream `SIGPIPE` rule.
  TCP and vsock signal delivery remain incomplete.

The SCML rules above remain conservative for all socket families:
SCML cannot infer a connected descriptor's domain and type from `sockfd` alone.
They do not declare global `MSG_NOSIGNAL` coverage for every protocol.

For more information,
see [the man page](https://man7.org/linux/man-pages/man2/sendto.2.html).

### `recvfrom` and `recvmsg`

Supported functionality in SCML:

```c
{{#include recvfrom_and_recvmsg.scml}}
```

For more information,
see [the man page](https://man7.org/linux/man-pages/man2/recvfrom.2.html).

## Socket options

### `getsockopt` and `setsockopt`

Supported functionality in SCML:

```c
{{#include getsockopt_and_setsockopt.scml}}
```

For more information,
see [the man page](https://man7.org/linux/man-pages/man2/getsockopt.2.html).
