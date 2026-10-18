set pagination off
set confirm off
set language c
set breakpoint pending off
set remotetimeout 10
set tcp auto-retry on
set tcp connect-timeout 20
target remote 127.0.0.1:42627
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
if pc != 18446744071700621120 or observed != bytes.fromhex("50e84a37f2ff48c7c7e82c5488e89e4a060048c7c000e05e8848c7c178e65e88"):
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
