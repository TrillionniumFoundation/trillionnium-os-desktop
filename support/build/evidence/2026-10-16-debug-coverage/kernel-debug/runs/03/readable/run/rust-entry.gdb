set pagination off
set confirm off
set language c
set breakpoint pending off
set remotetimeout 10
set tcp auto-retry on
set tcp connect-timeout 20
target remote 127.0.0.1:43781
hbreak *__ostd_main
continue
if (unsigned long)$pc != (unsigned long)&__ostd_main
  echo A01_GDB_WRONG_PC\n
  quit 1
end
printf "A01_GDB_RUST_ENTRY_HIT pc=0x%lx entry=0x%lx\n", (unsigned long)$pc, (unsigned long)&__ostd_main
bt
info source
info line *__ostd_main
info registers rip
disable breakpoints
detach
echo A01_GDB_DETACHED\n
quit 0
