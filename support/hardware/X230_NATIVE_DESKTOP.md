# Fixed native desktop candidate: X230

The 2026-11-03 read-only observation fixes one available machine for the P2
driver decision: Runtime host `x230`, Lenovo `23241W1`, Intel i5-3230M, BIOS
`G2ET86WW (2.06)`. The observed kernel is Linux `6.8.0-142-generic`; this is
not an Asterinas execution result. The exact inventory, source commit/tree,
Runtime job and unpassed gates are retained in
[the machine-readable observation](../../tests/hardware/evidence/2026-11-03-x230-readonly.json).

## Actual hardware and current source

| Gate | Observed machine | Current source and remaining work |
| --- | --- | --- |
| Boot | x86_64; the current Linux boot has no UEFI sysfs directory | Select a separate boot medium and verify its loader/framebuffer handoff. No firmware change, reboot or installation was performed. |
| Display | Intel `8086:0166`, Linux `i915` | [simpledrm](../../kernel/asterinas/kernel/comps/simpledrm/src/lib.rs) consumes a bootloader framebuffer. Verify format, stride, visible output and redraw on this machine; it is not an Intel modesetting or acceleration driver. |
| Input | PS/2 keyboard, Synaptics touchpad and TrackPoint | [i8042](../../kernel/asterinas/kernel/comps/i8042/src/lib.rs) is a source candidate. Verify physical key/pointer events, focus, Chinese composition and cancellation through the actual UI. |
| Storage | Intel `8086:1e03` AHCI; one 223.6 GiB SATA disk with existing partitions | No AHCI implementation was found in the selected kernel sources. VirtIO/NVMe guest success does not cover this controller. An actual block driver, flush/error propagation and restart recovery are required. |
| Network | Intel `8086:1502`, Linux `e1000e` | No matching native driver was found. Implement and verify the exact PCI device's DMA/interrupt/link lifecycle before an original Hepta session can depend on it. |
| Recovery | Existing Linux installation | No native watchdog, persistent restart or independent recovery run has been performed on this machine. Bind these to the same boot image and storage after the previous gates pass. |

Wi-Fi `10ec:8176`, USB host controllers, sound, suspend, GPU acceleration and
other hardware are outside the first fixed profile. They are neither emulated
by changing the profile label nor pre-counted as supported. The observed SATA
disk is the existing system disk, not a disposable test target; the boot medium
remains unset in the observation.

## Implementation order

1. Keep the original Asterinas/OSTD allocator, PCI, interrupt and block/network
   owners. Implement missing AHCI and exact-device Ethernet support as reviewed
   components with bounded DMA lifetime, real device completion and error
   propagation. Do not add a second Hepta permission or resource owner inside a
   driver. A QEMU device with a different PCI identity cannot qualify this card.
2. Build one immutable image, boot from an explicitly selected separate medium,
   and retain a recovery boot path. Record the image, firmware handoff and full
   console log. Exercise display and PS/2 input before enabling product actions.
3. Use an isolated storage area for real write, flush, close and independent
   readback. Verify link loss/reconnect on the actual wired interface and retain
   original operation identities while reconciling uncertain results.
4. Run the original Hepta owner/Notes protocol against this exact image. Verify
   restart and resource recovery with the legitimate pause state preserved.
   Only the joint display/input/storage/network/recovery result can close P2.

The present result closes hardware identification and driver-gap discovery.
Every native qualification flag remains false. It does not change the Linux
product pair, authorize writes to the installed disk, or establish mobile/BSP
support.
