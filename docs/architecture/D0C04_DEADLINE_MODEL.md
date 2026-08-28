# D0C-04 deadline model

The server ceiling is captured as a monotonic deadline at connection
acceptance. A request wall-clock deadline, when present, is converted once using
the acceptance wall/monotonic pair. The earlier deadline governs handler
admission, handler completion and response commit. A late result is discarded;
it is not converted into success and is not retried automatically.
