# Networking & Sockets

<!--
Put system calls such as

socket, socketpair, bind, listen, accept, connect, getsockname, getpeername,
sendto, recvfrom, sendmsg, recvmsg, shutdown, setsockopt, getsockopt,
sendmmsg, recvmmsg, accept4, recvmsg, and socketcall
under this category.
-->

## UNIX ownership and queue limits

The downstream kernel supports `AF_UNIX` stream, seqpacket and datagram sockets.
`SCM_RIGHTS` may transfer Unix socket descriptors when their persistent ownership remains acyclic,
including an effect stream and a recovery datagram passed through a bootstrap channel.
A send or later connection that would introduce a cycle returns `ELOOP` before publication.
There is no privileged exemption.
This admission policy does not implement Linux's in-flight socket garbage collector;
applications that intentionally construct such cycles are unsupported.

The global graph has 1,024 identities and 4,096 distinct directed edges.
Socket creation, socketpair, connect, listen, accept and descriptor transfer may return `ENOBUFS`
when the corresponding graph capacity is exhausted.
An unsuccessful accept retains its pending connection;
an unsuccessful datagram reconnection retains its old peer.
Closing the final actual owner and ancillary alias releases its graph capacity.
A peeked or received control alias may conservatively retain an admission until that alias is dropped.

Each Unix datagram and seqpacket receive queue accepts at most 128 messages, including empty messages.
Their existing 64 KiB payload-byte limit is unchanged.
A full queue makes a nonblocking send return `EAGAIN`; blocking send waits through the original socket wait path.
Peeking does not release a message slot.
Consumption wakes blocked senders, and peer close wakes them with the original peer-closure error.
Payload physical-page accounting and allocation rounding are separate from these message and graph limits.

SCML describes accepted arguments; it cannot encode the current ownership graph or its remaining capacity.
The limitations above therefore apply even when a call's arguments match a SCML rule.

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
* `MSG_NOSIGNAL`
* `MSG_OOB`
* `MSG_FASTOPEN`

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
