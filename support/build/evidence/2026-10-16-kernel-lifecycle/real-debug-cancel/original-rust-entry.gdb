set pagination off
set confirm off
set language c
set breakpoint pending off
set remotetimeout 10
set tcp auto-retry on
set tcp connect-timeout 20
target remote 127.0.0.1:59587
hbreak *__ostd_main
continue
if (unsigned long)$pc != (unsigned long)&__ostd_main
  echo A01_GDB_WRONG_PC\n
  quit 1
end
printf "A01_GDB_RUST_ENTRY_HIT pc=0x%lx entry=0x%lx\n", (unsigned long)$pc, (unsigned long)&__ostd_main
python
import gdb
pc = int(gdb.parse_and_eval("$pc"))
observed = bytes(gdb.selected_inferior().read_memory(pc, 32))
if pc != 18446744071700621376 or observed != bytes.fromhex("50e83a91f1ff48c7c7a8545488e8ee49060048c7c000105f8848c7c178165f88"):
    raise gdb.GdbError("A01_GDB_ENTRY_BYTES_MISMATCH")
gdb.write("A01_GDB_RUST_ENTRY_BYTES pc=0x%x size=32 bytes=%s\n" % (pc, observed.hex()))
end
bt
info source
info line *__ostd_main
info registers rip
disable breakpoints
detach
echo A01_GDB_DETACHED\n
quit 0
