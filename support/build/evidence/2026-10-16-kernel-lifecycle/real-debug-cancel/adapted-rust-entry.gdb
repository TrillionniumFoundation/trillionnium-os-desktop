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
import json, os, time
gdb.flush(gdb.STDOUT)
hold_record = {"kind": "real_native_gdb_hold_after_original_live_entry_validation", "gdb_pid": os.getpid(), "group": os.getpgrp(), "pc": hex(pc), "entry_bytes": observed.hex(), "entry_size": len(observed), "hold_seconds": 60}
with open('/workspace/scratch/ae1a8cf05419/next6-real-debug-cancel-controller-03/native-gdb-ready.json', "x") as hold_output:
    json.dump(hold_record, hold_output, indent=2)
    hold_output.write(chr(10))
gdb.write("A01_REAL_CANCEL_HOLD_READY" + chr(10))
gdb.flush(gdb.STDOUT)
time.sleep(60)
end
bt
info source
info line *__ostd_main
info registers rip
disable breakpoints
detach
echo A01_GDB_DETACHED\n
quit 0
