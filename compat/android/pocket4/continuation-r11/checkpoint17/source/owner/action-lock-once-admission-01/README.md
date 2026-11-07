# One action-lock admission

This candidate performs one nonblocking exclusive acquisition of the existing
`/run/lock/android-digitalis-actions.lock`, whose required device/inode is
28/8312, root UID/GID, regular mode 0600 and one link. It opens a new owned FD
with `O_RDWR | O_NOFOLLOW | O_CLOEXEC`; it does not use `O_CREAT`.

There is exactly one `LOCK_EX | LOCK_NB` attempt. Only a successful acquisition
is followed by `LOCK_UN`, immediately, with no intervening identity reads,
sleep, child or Android work. The owned FD is closed on every path. An
acquisition error, unlock error, ambiguous close or final guard failure keeps
the result unsuccessful and preserves the first error.

The original five input hashes, original Main guard, boot identity and exact
held/named lock identity remain required before and after the operation.
The unchanged identity support and the actual Ticket zero-action EAGAIN
receipt are exact packet inputs. No Android context is opened, no child is
started, no process/FD directory is scanned, and no lock is replaced or
deleted. This is a lock operation, not a read-only collector.

A successful result proves this single admission and its own release/close.
It does not identify a historical holder, prove the lock will remain free,
or authorize bypassing an App's normal lock gate. The first unexecuted App
attempt must still obtain its original lock itself.

The local six controls use only a temporary owned file: actual free and busy
OFD cases, non-EAGAIN preservation, identity rejection, unlock failure, and
first-error preservation across a close diagnostic. They do not call collect,
read Main, contact Hepta, or qualify a device/App.

Execution is not submitted by the generator. The request is fixed to one
CPU, 128 MiB, 30 seconds; source collection has a 15-second deadline and a
128-KiB complete-output limit. Default PLAN performs no device operation.
