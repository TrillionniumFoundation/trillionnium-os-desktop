# Servo embedder compile probe

This directory carries the compile-only API sentinel for the exact Servo commit
recorded in `manifests/servo-api-requirements.v1.json`.

Reproduction:

```bash
git clone https://github.com/servo/servo .servo-source
git -C .servo-source checkout 670ae8a70801b162e186f81cbb5bdd2d59c39108
python3 tools/verify_servo_compatibility.py \
  --servo-root .servo-source \
  --requirements manifests/servo-api-requirements.v1.json \
  --output target/servo-compatibility
```

The verifier generates `src/main.rs` from public API paths proven by `cargo
check`. The checked-in source is evidence for the current pin, not a stable
upstream ABI promise. It starts no Servo runtime, creates no window and opens no
listener.
