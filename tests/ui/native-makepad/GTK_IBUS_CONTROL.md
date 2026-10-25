# Focused GTK control for IBus startup

`probe_gtk_ibus.py` investigates a real IBus engine activation failure before
any Makepad input. It starts its own authenticated Xvfb, private D-Bus, IBus and
actual GTK 3 Entry. It uses the original qualification's private schema
overrides and original waitable-child cleanup guard. No user display or bus is
reused; no installed settings or Cargo sources are changed.

Run with existing, frozen source checkouts and a new output directory:

```sh
python3 -B tests/ui/native-makepad/probe_gtk_ibus.py \
  --desktop-source /absolute/frozen-desktop \
  --hepta-source /absolute/frozen-hepta \
  --output /absolute/evidence/new-gtk-ibus-control
```

The source paths supply only the existing child guard, XGetImage capture and
server-side XRes PID helper; their actual hashes are recorded. The GTK child
must have an active GLib loop, a mapped window owned by its actual PID, the
actual X focus and a focused Entry before selecting `libpinyin`. It records
the original 8-second activation bound and, on timeout, observes that same
command for at most 30 seconds solely for diagnosis. A slower activation
cannot pass the original bound. `observe_exit` is decoded as `os.waitid_result`
without reaping its leader before group cleanup.

Only XTEST ASCII `nihao` followed by the `space` key enters the Entry. The
control requires actual GTK preedit, an unchanged empty committed Entry until
confirmation, and the exact Chinese result `你好`. Expected Chinese is never
passed to an input API. The receipt, live widget observations, process wait
channels, actual pixels, command logs and cleanup results are preserved.

`--gtk-im-module xim` is a separate explicit GTK XIM control and must use a new
output directory. The default is the native GTK IBus module. Neither result
qualifies the Makepad preedit/cancellation/checkpoint/undo tests. Re-run the
unchanged original production window gate after diagnosing the service.

The local status-decoder regressions use actual child exit/signal statuses:

```sh
python3 -B -m unittest discover -s tests/ui/native-makepad -p test_probe_gtk_ibus.py -v
```
